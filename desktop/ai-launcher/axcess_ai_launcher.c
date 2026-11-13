/*
 * axcess-ai-launcher: starts Axcess's private llama.cpp AI service on Windows
 * inside an operating-system sandbox, and checks that sandbox first.
 *
 * WHAT IT DOES
 *   check  Starts a copy of itself ("probe-inner") in exactly the sandbox
 *          the AI service gets. Inside, the copy shows that (1) a TCP
 *          connection to a public address is refused by Windows itself,
 *          (2) it cannot create a file in the program folder but can in the
 *          scratch folder, and (3) it can serve a UNIX socket file (AF_UNIX)
 *          that this launcher, outside the sandbox, can connect to. Prints
 *          AXCESS_NETWORK_BLOCKED <error>, AXCESS_FILES_LIMITED and
 *          AXCESS_SOCKET_OK, and exits 0 only if all three pass.
 *   serve  Starts one llama-server per model from a spec file, each in the
 *          same sandbox, each listening on its own UNIX socket file in the
 *          scratch folder. For each model it opens a TCP listener on
 *          127.0.0.1 and relays connections to that model's socket, but only
 *          from the one process named by --client-pid (the Axcess backend).
 *          Prints PORT <name> <port> per model, then READY. Stops everything
 *          when its standard input closes.
 *
 * WHY
 *   The model service reads files a person did not write (model files) and
 *   parses requests built from crawled web pages. If it were ever tricked
 *   into misbehaving, it must not be able to reach the network, read the
 *   person's files, or start other programs. Python cannot start an
 *   AppContainer process (subprocess has no SECURITY_CAPABILITIES) and
 *   cannot open AF_UNIX sockets on Windows, so a small native launcher does
 *   both. See docs/internal/windows-ai-sandbox.md.
 *
 * SECURITY BOUNDARY
 *   Sandboxed processes run as a "less privileged" AppContainer (LPAC,
 *   profile "Axcess.LocalAI") with no network capability, so Windows blocks
 *   all their network traffic, loopback included. They may read only what
 *   names the container in its access list: this launcher grants read and
 *   run on --runtime, read on --models and change on --scratch, and nothing
 *   else. They cannot start child processes, run in a job object that kills
 *   them when this launcher exits, inherit only the log file and an empty
 *   standard input, and see only SystemRoot, TEMP, TMP and PATH.
 *   --gpu adds only the "registryRead" and "lpacPnpNotifications"
 *   capabilities, never a network one. The TCP relay listens on 127.0.0.1
 *   only, with an exclusive port, and closes every connection that does
 *   not come from --client-pid.
 *   This launcher itself is NOT sandboxed: it runs as the user, and trusts
 *   its command line and spec file (written by the Axcess backend).
 *   It fails closed: any failed Windows call stops it before anything runs
 *   unsandboxed, and a process that is not in the job or not in an
 *   AppContainer after creation is killed before it runs.
 *
 * COMMAND LINE (all paths absolute)
 *   axcess-ai-launcher check --scratch DIR --runtime DIR --models DIR
 *                            [--gpu] --log FILE
 *   axcess-ai-launcher serve --scratch DIR --runtime DIR --models DIR
 *                            [--gpu] --log FILE --client-pid PID --spec FILE
 *   (internal) axcess-ai-launcher probe-inner SOCK --scratch DIR
 *                            --runtime DIR
 *
 * Build: desktop/ai-launcher/build.ps1 (MSVC, cl /W4 /WX).
 */

#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#ifndef NTDDI_VERSION
#define NTDDI_VERSION 0x0A000006
#endif

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <afunix.h>
#include <iphlpapi.h>
#include <userenv.h>
#include <aclapi.h>
#include <sddl.h>
#include <fcntl.h>
#include <io.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#ifndef PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES
#define PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES 0x00020009
#endif
#ifndef PROC_THREAD_ATTRIBUTE_JOB_LIST
#define PROC_THREAD_ATTRIBUTE_JOB_LIST 0x0002000D
#endif
#ifndef PROC_THREAD_ATTRIBUTE_CHILD_PROCESS_POLICY
#define PROC_THREAD_ATTRIBUTE_CHILD_PROCESS_POLICY 0x0002000E
#endif
#ifndef PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY
#define PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY 0x0002000F
#endif
#ifndef PROCESS_CREATION_CHILD_PROCESS_RESTRICTED
#define PROCESS_CREATION_CHILD_PROCESS_RESTRICTED 0x01
#endif
#ifndef PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT
#define PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT 0x01
#endif

#define PROFILE_NAME L"Axcess.LocalAI"
#define MIN_BUILD 17763u
#define MAX_MODELS 8
#define MAX_ARGS 64
#define MAX_SPEC_BYTES 65536
#define CMDLINE_CAP 32767
#define PROBE_TAG 0x10000000u
#define RELAY_BUFFER 65536

/* Exit codes. */
#define EXIT_FAILED 1
#define EXIT_API 2
#define EXIT_TOO_OLD 3
#define EXIT_USAGE 64

enum mode { MODE_CHECK, MODE_SERVE, MODE_INNER };
static enum mode g_mode = MODE_CHECK;
static CRITICAL_SECTION g_out_lock;
static volatile LONG g_stopping = 0;

/* ------------------------------------------------------------------ */
/* Output                                                              */
/* ------------------------------------------------------------------ */

/* One protocol line on stdout, flushed at once. Lines end in "\n" only. */
static void out_line(const char *fmt, ...)
{
    va_list ap;
    EnterCriticalSection(&g_out_lock);
    va_start(ap, fmt);
    vfprintf(stdout, fmt, ap);
    va_end(ap);
    fputc('\n', stdout);
    fflush(stdout);
    LeaveCriticalSection(&g_out_lock);
}

/* A failed Windows call: report it in this mode's form and stop. Exiting
 * closes the job handle, so KILL_ON_JOB_CLOSE ends anything started. */
static __declspec(noreturn) void fail(const char *api, DWORD err)
{
    if (g_mode == MODE_SERVE)
        out_line("AXCESS_ERROR %s %lu", api, err);
    else if (g_mode == MODE_CHECK)
        out_line("AXCESS_CHECK_FAILED %s_%lu", api, err);
    else
        out_line("probe-inner: %s failed with %lu", api, err);
    ExitProcess(EXIT_API);
}

/* A problem with the command line or spec, not with Windows. */
static __declspec(noreturn) void fail_usage(const char *reason, unsigned long detail)
{
    if (g_mode == MODE_SERVE)
        out_line("AXCESS_ERROR %s %lu", reason, detail);
    else
        out_line("AXCESS_CHECK_FAILED %s", reason);
    ExitProcess(EXIT_USAGE);
}

static void *xalloc(size_t n)
{
    void *p = calloc(1, n ? n : 1);
    if (!p)
        fail("calloc", ERROR_NOT_ENOUGH_MEMORY);
    return p;
}

static wchar_t *xwcsdup(const wchar_t *s)
{
    size_t n = wcslen(s) + 1;
    wchar_t *d = (wchar_t *)xalloc(n * sizeof(wchar_t));
    memcpy(d, s, n * sizeof(wchar_t));
    return d;
}

/* ------------------------------------------------------------------ */
/* Paths                                                               */
/* ------------------------------------------------------------------ */

static int is_absolute(const wchar_t *p)
{
    if (!p || !p[0])
        return 0;
    if (((p[0] >= L'A' && p[0] <= L'Z') || (p[0] >= L'a' && p[0] <= L'z')) && p[1] == L':' &&
        (p[2] == L'\\' || p[2] == L'/'))
        return 1;
    return p[0] == L'\\' && p[1] == L'\\';
}

/* The normalized absolute form of an absolute path ("." and ".." removed),
 * without a trailing backslash unless it is a drive root. NULL if the path is
 * not absolute. */
static wchar_t *full_path(const wchar_t *p)
{
    DWORD n;
    wchar_t *out;
    size_t len;
    if (!is_absolute(p))
        return NULL;
    n = GetFullPathNameW(p, 0, NULL, NULL);
    if (!n)
        fail("GetFullPathNameW", GetLastError());
    out = (wchar_t *)xalloc(((size_t)n + 1) * sizeof(wchar_t));
    if (!GetFullPathNameW(p, n + 1, out, NULL))
        fail("GetFullPathNameW", GetLastError());
    len = wcslen(out);
    while (len > 3 && out[len - 1] == L'\\')
        out[--len] = 0;
    return out;
}

static int is_dir(const wchar_t *p)
{
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

static int is_file(const wchar_t *p)
{
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

/* True when path is strictly inside dir (both from full_path). */
static int is_inside(const wchar_t *dir, const wchar_t *path)
{
    size_t d = wcslen(dir);
    if (wcslen(path) <= d + 1 || _wcsnicmp(dir, path, d) != 0)
        return 0;
    if (dir[d - 1] == L'\\')
        return 1;
    return path[d] == L'\\';
}

static wchar_t *dir_of(const wchar_t *path)
{
    wchar_t *d = xwcsdup(path);
    wchar_t *slash = wcsrchr(d, L'\\');
    if (slash) {
        if (slash - d == 2 && d[1] == L':')
            slash[1] = 0;
        else
            *slash = 0;
    }
    return d;
}

/* An AF_UNIX address for a socket path. Windows reads sun_path in the ANSI
 * code page, as llama-server (a narrow main) passes its --host argument. */
static int unix_address(const wchar_t *path, SOCKADDR_UN *addr)
{
    BOOL lossy = FALSE;
    int n;
    memset(addr, 0, sizeof(*addr));
    addr->sun_family = AF_UNIX;
    n = WideCharToMultiByte(CP_ACP, WC_NO_BEST_FIT_CHARS, path, -1, addr->sun_path,
                            (int)sizeof(addr->sun_path), NULL, &lossy);
    return n > 0 && !lossy;
}

/* ------------------------------------------------------------------ */
/* Options                                                             */
/* ------------------------------------------------------------------ */

struct options {
    wchar_t *scratch;
    wchar_t *runtime;
    wchar_t *models;
    wchar_t *log;
    wchar_t *spec;
    wchar_t *inner_sock;
    DWORD client_pid;
    int gpu;
};

static wchar_t *path_option(const wchar_t *value, const char *name)
{
    wchar_t *p = full_path(value);
    if (!p)
        fail_usage(name, 0);
    return p;
}

static void parse_options(int argc, wchar_t **argv, int first, struct options *o)
{
    int i;
    for (i = first; i < argc; i++) {
        const wchar_t *a = argv[i];
        const wchar_t *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (wcscmp(a, L"--gpu") == 0) {
            o->gpu = 1;
            continue;
        }
        if (!v)
            fail_usage("usage", (unsigned long)i);
        if (wcscmp(a, L"--scratch") == 0)
            o->scratch = path_option(v, "scratch_not_absolute");
        else if (wcscmp(a, L"--runtime") == 0)
            o->runtime = path_option(v, "runtime_not_absolute");
        else if (wcscmp(a, L"--models") == 0)
            o->models = path_option(v, "models_not_absolute");
        else if (wcscmp(a, L"--log") == 0)
            o->log = path_option(v, "log_not_absolute");
        else if (wcscmp(a, L"--spec") == 0)
            o->spec = path_option(v, "spec_not_absolute");
        else if (wcscmp(a, L"--client-pid") == 0) {
            wchar_t *end = NULL;
            unsigned long pid = wcstoul(v, &end, 10);
            if (!end || *end || pid == 0 || pid > 0xFFFFFFFFul)
                fail_usage("client_pid", 0);
            o->client_pid = (DWORD)pid;
        } else
            fail_usage("usage", (unsigned long)i);
        i++;
    }
}

static void require_dirs(const struct options *o, int need_models)
{
    if (!o->scratch || !is_dir(o->scratch))
        fail_usage("scratch_missing", 0);
    if (!o->runtime || !is_dir(o->runtime))
        fail_usage("runtime_missing", 0);
    if (need_models && (!o->models || !is_dir(o->models)))
        fail_usage("models_missing", 0);
}

/* ------------------------------------------------------------------ */
/* Windows version                                                     */
/* ------------------------------------------------------------------ */

typedef LONG(WINAPI *rtl_get_version_fn)(PRTL_OSVERSIONINFOW);

/* Windows 10 1809 (build 17763) or later: LPAC, process mitigations for
 * AppContainers and AF_UNIX all need it. RtlGetVersion, because
 * GetVersionEx reports what the program's manifest claims. */
static void require_windows_version(void)
{
    RTL_OSVERSIONINFOW v;
    rtl_get_version_fn get;
    HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    memset(&v, 0, sizeof(v));
    v.dwOSVersionInfoSize = sizeof(v);
    get = ntdll ? (rtl_get_version_fn)GetProcAddress(ntdll, "RtlGetVersion") : NULL;
    if (!get || get(&v) != 0 || v.dwMajorVersion < 10 ||
        (v.dwMajorVersion == 10 && v.dwBuildNumber < MIN_BUILD)) {
        if (g_mode == MODE_SERVE)
            out_line("AXCESS_ERROR windows_too_old %lu", v.dwBuildNumber);
        else
            out_line("AXCESS_CHECK_FAILED windows_too_old");
        ExitProcess(EXIT_TOO_OLD);
    }
}

/* ------------------------------------------------------------------ */
/* The sandbox                                                         */
/* ------------------------------------------------------------------ */

typedef BOOL(WINAPI *derive_capability_fn)(LPCWSTR, PSID **, DWORD *, PSID **, DWORD *);

struct sandbox {
    PSID container;
    SID_AND_ATTRIBUTES caps[2];
    DWORD cap_count;
    HANDLE job;
    HANDLE log;
    HANDLE nul;
    const struct options *opt;
};

/* The named capability's SID, as DeriveCapabilitySidsFromName gives it.
 * Looked up at run time: it lives in kernelbase.dll on every build we
 * support, but the import library that declares it varies by SDK. */
static PSID capability_sid(const wchar_t *name)
{
    derive_capability_fn derive;
    PSID *groups = NULL, *sids = NULL;
    DWORD group_count = 0, sid_count = 0, i;
    PSID keep;
    HMODULE kb = GetModuleHandleW(L"kernelbase.dll");
    derive = kb ? (derive_capability_fn)GetProcAddress(kb, "DeriveCapabilitySidsFromName") : NULL;
    if (!derive)
        fail("DeriveCapabilitySidsFromName", ERROR_PROC_NOT_FOUND);
    if (!derive(name, &groups, &group_count, &sids, &sid_count))
        fail("DeriveCapabilitySidsFromName", GetLastError());
    if (sid_count < 1)
        fail("DeriveCapabilitySidsFromName", ERROR_NOT_FOUND);
    keep = sids[0];
    for (i = 1; i < sid_count; i++)
        LocalFree(sids[i]);
    for (i = 0; i < group_count; i++)
        LocalFree(groups[i]);
    LocalFree(sids);
    LocalFree(groups);
    return keep;
}

/* Adds one inherited allow entry for sid to path's access list, keeping
 * every existing entry. GRANT_ACCESS merges with an entry the container
 * already has, so repeating this does not grow the list. */
static void grant(const wchar_t *path, PSID sid, DWORD mask)
{
    PACL old_dacl = NULL, new_dacl = NULL;
    PSECURITY_DESCRIPTOR sd = NULL;
    EXPLICIT_ACCESS_W ea;
    DWORD e;
    e = GetNamedSecurityInfoW(path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, NULL, NULL,
                              &old_dacl, NULL, &sd);
    if (e != ERROR_SUCCESS)
        fail("GetNamedSecurityInfoW", e);
    memset(&ea, 0, sizeof(ea));
    ea.grfAccessPermissions = mask;
    ea.grfAccessMode = GRANT_ACCESS;
    ea.grfInheritance = SUB_CONTAINERS_AND_OBJECTS_INHERIT;
    ea.Trustee.TrusteeForm = TRUSTEE_IS_SID;
    ea.Trustee.TrusteeType = TRUSTEE_IS_WELL_KNOWN_GROUP;
    ea.Trustee.ptstrName = (LPWSTR)sid;
    e = SetEntriesInAclW(1, &ea, old_dacl, &new_dacl);
    if (e != ERROR_SUCCESS)
        fail("SetEntriesInAclW", e);
    e = SetNamedSecurityInfoW((LPWSTR)path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, NULL, NULL,
                              new_dacl, NULL);
    if (e != ERROR_SUCCESS)
        fail("SetNamedSecurityInfoW", e);
    LocalFree(new_dacl);
    LocalFree(sd);
}

static HANDLE inheritable_file(const wchar_t *path, DWORD access, DWORD disposition)
{
    SECURITY_ATTRIBUTES sa;
    HANDLE h;
    memset(&sa, 0, sizeof(sa));
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;
    h = CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, &sa,
                    disposition, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        fail("CreateFileW", GetLastError());
    return h;
}

/* Everything shared by the processes this launcher starts: the container
 * identity, folder access, one job, the log and an empty stdin. */
static void sandbox_init(struct sandbox *sb, const struct options *o, DWORD process_count)
{
    HRESULT hr;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits;
    JOBOBJECT_BASIC_UI_RESTRICTIONS ui;
    char header[160];
    DWORD written;
    SYSTEMTIME now;

    memset(sb, 0, sizeof(*sb));
    sb->opt = o;

    hr = CreateAppContainerProfile(PROFILE_NAME, PROFILE_NAME, L"Axcess private AI service", NULL, 0,
                                   &sb->container);
    if (hr == HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS))
        hr = DeriveAppContainerSidFromAppContainerName(PROFILE_NAME, &sb->container);
    if (FAILED(hr))
        fail("CreateAppContainerProfile", (DWORD)hr);

    /* GPU drivers read the registry and watch for devices. Neither is a
     * network capability. */
    if (o->gpu) {
        sb->caps[0].Sid = capability_sid(L"registryRead");
        sb->caps[0].Attributes = SE_GROUP_ENABLED;
        sb->caps[1].Sid = capability_sid(L"lpacPnpNotifications");
        sb->caps[1].Attributes = SE_GROUP_ENABLED;
        sb->cap_count = 2;
    }

    grant(o->runtime, sb->container, FILE_GENERIC_READ | FILE_GENERIC_EXECUTE);
    if (o->models)
        grant(o->models, sb->container, FILE_GENERIC_READ);
    grant(o->scratch, sb->container,
          FILE_GENERIC_READ | FILE_GENERIC_WRITE | FILE_GENERIC_EXECUTE | DELETE);

    sb->job = CreateJobObjectW(NULL, NULL);
    if (!sb->job)
        fail("CreateJobObjectW", GetLastError());
    memset(&limits, 0, sizeof(limits));
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
                                              JOB_OBJECT_LIMIT_ACTIVE_PROCESS |
                                              JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION;
    limits.BasicLimitInformation.ActiveProcessLimit = process_count;
    if (!SetInformationJobObject(sb->job, JobObjectExtendedLimitInformation, &limits, sizeof(limits)))
        fail("SetInformationJobObject", GetLastError());
    memset(&ui, 0, sizeof(ui));
    ui.UIRestrictionsClass = JOB_OBJECT_UILIMIT_DESKTOP | JOB_OBJECT_UILIMIT_DISPLAYSETTINGS |
                             JOB_OBJECT_UILIMIT_EXITWINDOWS | JOB_OBJECT_UILIMIT_GLOBALATOMS |
                             JOB_OBJECT_UILIMIT_HANDLES | JOB_OBJECT_UILIMIT_READCLIPBOARD |
                             JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS | JOB_OBJECT_UILIMIT_WRITECLIPBOARD;
    if (!SetInformationJobObject(sb->job, JobObjectBasicUIRestrictions, &ui, sizeof(ui)))
        fail("SetInformationJobObject", GetLastError());

    sb->log = inheritable_file(o->log, FILE_APPEND_DATA | SYNCHRONIZE, OPEN_ALWAYS);
    sb->nul = inheritable_file(L"NUL", GENERIC_READ, OPEN_EXISTING);

    GetLocalTime(&now);
    _snprintf(header, sizeof(header),
              "\n--- axcess-ai-launcher %s, %04u-%02u-%02u %02u:%02u:%02u%s ---\n",
              g_mode == MODE_SERVE ? "serve" : "check", now.wYear, now.wMonth, now.wDay,
              now.wHour, now.wMinute, now.wSecond, o->gpu ? ", GPU capabilities" : "");
    header[sizeof(header) - 1] = 0;
    WriteFile(sb->log, header, (DWORD)strlen(header), &written, NULL);
}

/* Appends one argument, quoted the way CommandLineToArgvW and the C runtime
 * read it back. Returns 0 if the command line would be too long. */
static int append_arg(wchar_t *buf, size_t *len, const wchar_t *arg)
{
    size_t n = *len, slashes;
    const wchar_t *p;
    int quote = arg[0] == 0 || wcspbrk(arg, L" \t\n\v\"") != NULL;
    if (n && n < CMDLINE_CAP)
        buf[n++] = L' ';
    if (!quote) {
        size_t a = wcslen(arg);
        if (n + a >= CMDLINE_CAP)
            return 0;
        memcpy(buf + n, arg, a * sizeof(wchar_t));
        n += a;
    } else {
        if (n + 1 >= CMDLINE_CAP)
            return 0;
        buf[n++] = L'"';
        for (p = arg;; p++) {
            slashes = 0;
            while (*p == L'\\') {
                slashes++;
                p++;
            }
            if (*p == 0) {
                if (n + slashes * 2 + 1 >= CMDLINE_CAP)
                    return 0;
                while (slashes--)
                    { buf[n++] = L'\\'; buf[n++] = L'\\'; }
                break;
            }
            if (*p == L'"') {
                if (n + slashes * 2 + 2 >= CMDLINE_CAP)
                    return 0;
                while (slashes--)
                    { buf[n++] = L'\\'; buf[n++] = L'\\'; }
                buf[n++] = L'\\';
                buf[n++] = L'"';
            } else {
                if (n + slashes + 1 >= CMDLINE_CAP)
                    return 0;
                while (slashes--)
                    buf[n++] = L'\\';
                buf[n++] = *p;
            }
        }
        if (n + 1 >= CMDLINE_CAP)
            return 0;
        buf[n++] = L'"';
    }
    buf[n] = 0;
    *len = n;
    return 1;
}

static wchar_t *build_cmdline(wchar_t **args, int count)
{
    wchar_t *buf = (wchar_t *)xalloc((CMDLINE_CAP + 1) * sizeof(wchar_t));
    size_t len = 0;
    int i;
    for (i = 0; i < count; i++)
        if (!append_arg(buf, &len, args[i]))
            fail_usage("command_line_too_long", 0);
    return buf;
}

/* The child's whole environment, sorted as Windows expects. */
static wchar_t *child_environment(const wchar_t *exe_dir, const wchar_t *scratch)
{
    wchar_t sysroot[MAX_PATH + 1];
    size_t cap, n = 0;
    wchar_t *env;
    UINT len = GetSystemWindowsDirectoryW(sysroot, MAX_PATH + 1);
    if (!len || len > MAX_PATH)
        fail("GetSystemWindowsDirectoryW", GetLastError());
    cap = wcslen(exe_dir) + wcslen(sysroot) + 2 * wcslen(scratch) + 64;
    env = (wchar_t *)xalloc(cap * sizeof(wchar_t));
    n += (size_t)_snwprintf(env + n, cap - n, L"PATH=%ls", exe_dir) + 1;
    n += (size_t)_snwprintf(env + n, cap - n, L"SystemRoot=%ls", sysroot) + 1;
    n += (size_t)_snwprintf(env + n, cap - n, L"TEMP=%ls", scratch) + 1;
    n += (size_t)_snwprintf(env + n, cap - n, L"TMP=%ls", scratch) + 1;
    env[n] = 0;
    return env;
}

/* Starts exe in the sandbox, suspended; checks that Windows really put it
 * in the job and in an AppContainer; then lets it run. */
static void sandbox_start(struct sandbox *sb, const wchar_t *exe, wchar_t *cmdline,
                          PROCESS_INFORMATION *pi)
{
    SIZE_T size = 0;
    LPPROC_THREAD_ATTRIBUTE_LIST attrs;
    SECURITY_CAPABILITIES sc;
    DWORD lpac = PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT;
    DWORD child_policy = PROCESS_CREATION_CHILD_PROCESS_RESTRICTED;
    HANDLE jobs[1];
    HANDLE inherit[2];
    STARTUPINFOEXW si;
    wchar_t *exe_dir, *env;
    BOOL in_job = FALSE;
    HANDLE token = NULL;
    DWORD is_container = 0, got = 0;

    jobs[0] = sb->job;
    inherit[0] = sb->log;
    inherit[1] = sb->nul;
    memset(&sc, 0, sizeof(sc));
    sc.AppContainerSid = sb->container;
    sc.Capabilities = sb->cap_count ? sb->caps : NULL;
    sc.CapabilityCount = sb->cap_count;

    InitializeProcThreadAttributeList(NULL, 5, 0, &size);
    attrs = (LPPROC_THREAD_ATTRIBUTE_LIST)xalloc(size);
    if (!InitializeProcThreadAttributeList(attrs, 5, 0, &size))
        fail("InitializeProcThreadAttributeList", GetLastError());
    if (!UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, &sc,
                                   sizeof(sc), NULL, NULL))
        fail("UpdateProcThreadAttribute", GetLastError());
    if (!UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY,
                                   &lpac, sizeof(lpac), NULL, NULL))
        fail("UpdateProcThreadAttribute", GetLastError());
    if (!UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_CHILD_PROCESS_POLICY,
                                   &child_policy, sizeof(child_policy), NULL, NULL))
        fail("UpdateProcThreadAttribute", GetLastError());
    if (!UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_JOB_LIST, jobs, sizeof(jobs),
                                   NULL, NULL))
        fail("UpdateProcThreadAttribute", GetLastError());
    if (!UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherit,
                                   sizeof(inherit), NULL, NULL))
        fail("UpdateProcThreadAttribute", GetLastError());

    memset(&si, 0, sizeof(si));
    si.StartupInfo.cb = sizeof(si);
    si.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    si.StartupInfo.hStdInput = sb->nul;
    si.StartupInfo.hStdOutput = sb->log;
    si.StartupInfo.hStdError = sb->log;
    si.lpAttributeList = attrs;

    exe_dir = dir_of(exe);
    env = child_environment(exe_dir, sb->opt->scratch);
    memset(pi, 0, sizeof(*pi));
    /* DETACHED_PROCESS: no console, so Windows starts no console host for
     * it (which would count against the job's process limit). */
    if (!CreateProcessW(exe, cmdline, NULL, NULL, TRUE,
                        EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT |
                            CREATE_SUSPENDED | DETACHED_PROCESS,
                        env, sb->opt->scratch, &si.StartupInfo, pi))
        fail("CreateProcessW", GetLastError());
    DeleteProcThreadAttributeList(attrs);
    free(attrs);
    free(env);
    free(exe_dir);

    if (!IsProcessInJob(pi->hProcess, sb->job, &in_job) || !in_job) {
        TerminateProcess(pi->hProcess, 1);
        fail("IsProcessInJob", in_job ? GetLastError() : ERROR_ACCESS_DENIED);
    }
    if (!OpenProcessToken(pi->hProcess, TOKEN_QUERY, &token)) {
        DWORD e = GetLastError();
        TerminateProcess(pi->hProcess, 1);
        fail("OpenProcessToken", e);
    }
    if (!GetTokenInformation(token, TokenIsAppContainer, &is_container, sizeof(is_container), &got) ||
        !is_container) {
        DWORD e = is_container ? GetLastError() : ERROR_ACCESS_DENIED;
        TerminateProcess(pi->hProcess, 1);
        fail("TokenIsAppContainer", e);
    }
    CloseHandle(token);
    if (ResumeThread(pi->hThread) == (DWORD)-1) {
        DWORD e = GetLastError();
        TerminateProcess(pi->hProcess, 1);
        fail("ResumeThread", e);
    }
    CloseHandle(pi->hThread);
    pi->hThread = NULL;
}

/* ------------------------------------------------------------------ */
/* check and probe-inner                                               */
/* ------------------------------------------------------------------ */

/* Network results, low 3 bits of the probe's exit code. */
#define NET_EACCES 1
#define NET_ENETUNREACH 2
#define NET_EHOSTUNREACH 3
#define NET_EADDRNOTAVAIL 4
#define NET_CONNECTED 5
#define NET_TIMEOUT 6
#define NET_OTHER 7

static const char *const net_names[] = {"",
                                        "WSAEACCES",
                                        "WSAENETUNREACH",
                                        "WSAEHOSTUNREACH",
                                        "WSAEADDRNOTAVAIL"};

static int classify(int err)
{
    switch (err) {
    case WSAEACCES:
        return NET_EACCES;
    case WSAENETUNREACH:
        return NET_ENETUNREACH;
    case WSAEHOSTUNREACH:
        return NET_EHOSTUNREACH;
    case WSAEADDRNOTAVAIL:
        return NET_EADDRNOTAVAIL;
    default:
        return NET_OTHER;
    }
}

/* Waits for one socket to become writable or to fail. fd_set filled by hand:
 * the FD_SET macro trips /W4's constant-condition warning on older MSVC. */
static int wait_socket(SOCKET s, int for_write, long seconds, int *error_set)
{
    fd_set ready, errors;
    struct timeval tv;
    int r;
    ready.fd_count = 1;
    ready.fd_array[0] = s;
    errors.fd_count = 1;
    errors.fd_array[0] = s;
    tv.tv_sec = seconds;
    tv.tv_usec = 0;
    r = select(0, for_write ? NULL : &ready, for_write ? &ready : NULL, &errors, &tv);
    *error_set = r > 0 && errors.fd_count > 0;
    return r;
}

/* (1) A TCP connection to a public address. Passes only on an OS denial. */
static int probe_network(int *wsa_error)
{
    SOCKET s;
    struct sockaddr_in a;
    u_long nonblocking = 1;
    int err, r, error_set = 0, so_error = 0, so_len = (int)sizeof(so_error);
    *wsa_error = 0;
    s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) {
        *wsa_error = WSAGetLastError();
        out_line("probe-inner: socket() refused with %d", *wsa_error);
        return classify(*wsa_error);
    }
    ioctlsocket(s, FIONBIO, &nonblocking);
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(443);
    a.sin_addr.s_addr = htonl(0x01010101u); /* 1.1.1.1 */
    if (connect(s, (struct sockaddr *)&a, (int)sizeof(a)) == 0) {
        closesocket(s);
        out_line("probe-inner: connect to 1.1.1.1:443 succeeded at once");
        return NET_CONNECTED;
    }
    err = WSAGetLastError();
    if (err == WSAEWOULDBLOCK) {
        r = wait_socket(s, 1, 3, &error_set);
        if (r == 0) {
            closesocket(s);
            out_line("probe-inner: connect to 1.1.1.1:443 timed out after 3 s");
            return NET_TIMEOUT;
        }
        if (r == SOCKET_ERROR) {
            err = WSAGetLastError();
        } else if (error_set) {
            getsockopt(s, SOL_SOCKET, SO_ERROR, (char *)&so_error, &so_len);
            err = so_error;
        } else {
            closesocket(s);
            out_line("probe-inner: connect to 1.1.1.1:443 succeeded");
            return NET_CONNECTED;
        }
    }
    closesocket(s);
    *wsa_error = err;
    out_line("probe-inner: connect to 1.1.1.1:443 failed with %d", err);
    return classify(err);
}

/* (2) Writing in the program folder must fail; in scratch it must work. */
static int probe_files(const wchar_t *scratch, const wchar_t *runtime)
{
    wchar_t path[MAX_PATH * 2];
    HANDLE h;
    DWORD written = 0;
    int ok = 1;
    _snwprintf(path, MAX_PATH * 2 - 1, L"%ls\\axcess-probe-%lu.tmp", runtime,
               GetCurrentProcessId());
    path[MAX_PATH * 2 - 1] = 0;
    h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        CloseHandle(h);
        DeleteFileW(path);
        out_line("probe-inner: could create a file in the program folder");
        ok = 0;
    } else {
        out_line("probe-inner: program folder write refused with %lu", GetLastError());
    }
    _snwprintf(path, MAX_PATH * 2 - 1, L"%ls\\axcess-probe-%lu.tmp", scratch,
               GetCurrentProcessId());
    path[MAX_PATH * 2 - 1] = 0;
    h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        out_line("probe-inner: scratch folder write failed with %lu", GetLastError());
        return 0;
    }
    if (!WriteFile(h, "probe", 5, &written, NULL) || written != 5) {
        out_line("probe-inner: scratch folder write failed with %lu", GetLastError());
        ok = 0;
    }
    CloseHandle(h);
    if (!DeleteFileW(path))
        out_line("probe-inner: could not delete its scratch file (%lu)", GetLastError());
    return ok;
}

static int recv_exact(SOCKET s, char *buf, int n)
{
    int got = 0, r;
    while (got < n) {
        r = recv(s, buf + got, n - got, 0);
        if (r <= 0)
            return 0;
        got += r;
    }
    return 1;
}

static void set_timeouts(SOCKET s, DWORD ms)
{
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&ms, (int)sizeof(ms));
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char *)&ms, (int)sizeof(ms));
}

/* (3) Serve one ping on an AF_UNIX socket file. */
static int probe_socket(const wchar_t *sock_path)
{
    SOCKADDR_UN addr;
    SOCKET l, c;
    char buf[4];
    int error_set = 0;
    if (!unix_address(sock_path, &addr)) {
        out_line("probe-inner: socket path does not fit");
        return 0;
    }
    l = socket(AF_UNIX, SOCK_STREAM, 0);
    if (l == INVALID_SOCKET) {
        out_line("probe-inner: AF_UNIX socket() failed with %d", WSAGetLastError());
        return 0;
    }
    DeleteFileW(sock_path);
    if (bind(l, (struct sockaddr *)&addr, (int)sizeof(addr)) != 0 || listen(l, 1) != 0) {
        out_line("probe-inner: AF_UNIX bind/listen failed with %d", WSAGetLastError());
        closesocket(l);
        return 0;
    }
    if (wait_socket(l, 0, 10, &error_set) <= 0 || error_set) {
        out_line("probe-inner: no AF_UNIX connection within 10 s");
        closesocket(l);
        return 0;
    }
    c = accept(l, NULL, NULL);
    closesocket(l);
    if (c == INVALID_SOCKET) {
        out_line("probe-inner: AF_UNIX accept failed with %d", WSAGetLastError());
        return 0;
    }
    set_timeouts(c, 10000);
    if (!recv_exact(c, buf, 4) || memcmp(buf, "ping", 4) != 0 || send(c, "pong", 4, 0) != 4) {
        out_line("probe-inner: AF_UNIX exchange failed with %d", WSAGetLastError());
        closesocket(c);
        return 0;
    }
    shutdown(c, SD_SEND);
    recv(c, buf, 1, 0); /* wait for the other side to finish reading */
    closesocket(c);
    return 1;
}

/* Exit code: PROBE_TAG | net (bits 0-2) | files ok (bit 3) | socket ok
 * (bit 4) | Winsock error (bits 8-23). Anything without PROBE_TAG is a
 * crash or a failed call. */
static int run_inner(const struct options *o)
{
    WSADATA wsa;
    int net, files, sock, wsa_error = 0;
    if (!o->inner_sock || !o->scratch || !o->runtime)
        fail_usage("usage", 0);
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        fail("WSAStartup", (DWORD)WSAGetLastError());
    net = probe_network(&wsa_error);
    files = probe_files(o->scratch, o->runtime);
    sock = probe_socket(o->inner_sock);
    return (int)(PROBE_TAG | (unsigned)net | ((unsigned)files << 3) | ((unsigned)sock << 4) |
                 (((unsigned)wsa_error & 0xFFFFu) << 8));
}

/* The outside half of the socket test: wait for the file, connect, ping. */
static int outer_exchange(const wchar_t *sock_path, HANDLE probe)
{
    SOCKADDR_UN addr;
    SOCKET s;
    char buf[4];
    ULONGLONG deadline = GetTickCount64() + 30000;
    if (!unix_address(sock_path, &addr))
        return 0;
    for (;;) {
        if (GetFileAttributesW(sock_path) != INVALID_FILE_ATTRIBUTES) {
            s = socket(AF_UNIX, SOCK_STREAM, 0);
            if (s == INVALID_SOCKET)
                fail("socket", (DWORD)WSAGetLastError());
            if (connect(s, (struct sockaddr *)&addr, (int)sizeof(addr)) == 0) {
                int ok;
                set_timeouts(s, 10000);
                ok = send(s, "ping", 4, 0) == 4 && recv_exact(s, buf, 4) &&
                     memcmp(buf, "pong", 4) == 0;
                closesocket(s);
                return ok;
            }
            closesocket(s);
        }
        if (WaitForSingleObject(probe, 100) == WAIT_OBJECT_0 || GetTickCount64() > deadline)
            return 0;
    }
}

static int run_check(struct options *o)
{
    struct sandbox sb;
    WSADATA wsa;
    wchar_t self[MAX_PATH * 2];
    wchar_t *self_full, *sock, *cmdline;
    wchar_t *args[7];
    size_t n;
    PROCESS_INFORMATION pi;
    DWORD code = 0, wait;
    int exchanged, net, files, sock_in, wsa_error;
    const char *failure = NULL;
    char reason[64];

    require_dirs(o, 1);
    if (!o->log)
        fail_usage("log_missing", 0);
    n = GetModuleFileNameW(NULL, self, MAX_PATH * 2);
    if (!n || n >= MAX_PATH * 2)
        fail("GetModuleFileNameW", GetLastError());
    self_full = full_path(self);
    if (!self_full || !is_inside(o->runtime, self_full))
        fail_usage("launcher_outside_runtime", 0);
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        fail("WSAStartup", (DWORD)WSAGetLastError());

    n = wcslen(o->scratch) + 16;
    sock = (wchar_t *)xalloc(n * sizeof(wchar_t));
    _snwprintf(sock, n - 1, L"%ls\\probe.sock", o->scratch);
    {
        SOCKADDR_UN probe_addr;
        if (!unix_address(sock, &probe_addr))
            fail_usage("socket_path_too_long", 0);
    }
    DeleteFileW(sock);

    sandbox_init(&sb, o, 1);
    args[0] = self_full;
    args[1] = L"probe-inner";
    args[2] = sock;
    args[3] = L"--scratch";
    args[4] = o->scratch;
    args[5] = L"--runtime";
    args[6] = o->runtime;
    cmdline = build_cmdline(args, 7);
    sandbox_start(&sb, self_full, cmdline, &pi);

    exchanged = outer_exchange(sock, pi.hProcess);
    wait = WaitForSingleObject(pi.hProcess, 30000);
    if (wait != WAIT_OBJECT_0) {
        TerminateJobObject(sb.job, 1);
        WaitForSingleObject(pi.hProcess, 5000);
        DeleteFileW(sock);
        out_line("AXCESS_CHECK_FAILED probe_timeout");
        return EXIT_FAILED;
    }
    if (!GetExitCodeProcess(pi.hProcess, &code))
        fail("GetExitCodeProcess", GetLastError());
    DeleteFileW(sock);

    if ((code & 0xF0000000u) != PROBE_TAG) {
        out_line("AXCESS_CHECK_FAILED probe_exit_%lu", code);
        return EXIT_FAILED;
    }
    net = (int)(code & 7u);
    files = (int)((code >> 3) & 1u);
    sock_in = (int)((code >> 4) & 1u);
    wsa_error = (int)((code >> 8) & 0xFFFFu);

    if (net >= NET_EACCES && net <= NET_EADDRNOTAVAIL)
        out_line("AXCESS_NETWORK_BLOCKED %s", net_names[net]);
    if (files)
        out_line("AXCESS_FILES_LIMITED");
    if (sock_in && exchanged)
        out_line("AXCESS_SOCKET_OK");

    if (net == NET_CONNECTED)
        failure = "network_connected";
    else if (net == NET_TIMEOUT)
        failure = "network_timeout";
    else if (net == NET_OTHER || net == 0) {
        _snprintf(reason, sizeof(reason), "network_error_%d", wsa_error);
        reason[sizeof(reason) - 1] = 0;
        failure = reason;
    } else if (!files)
        failure = "files_not_limited";
    else if (!(sock_in && exchanged))
        failure = "socket_unreachable";
    if (failure) {
        out_line("AXCESS_CHECK_FAILED %s", failure);
        return EXIT_FAILED;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* serve                                                               */
/* ------------------------------------------------------------------ */

struct model {
    char name[64];
    wchar_t *socket;
    wchar_t *args[MAX_ARGS];
    int argc;
    SOCKADDR_UN addr;
    PROCESS_INFORMATION pi;
    SOCKET listener;
    u_short port_net; /* listener port, network byte order */
};

static struct model g_models[MAX_MODELS];
static int g_model_count = 0;
static DWORD g_client_pid = 0;

static int valid_name(const char *s)
{
    size_t i, n = strlen(s);
    if (n == 0 || n >= sizeof(g_models[0].name))
        return 0;
    for (i = 0; i < n; i++) {
        char c = s[i];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
              c == '.' || c == '_' || c == '-'))
            return 0;
    }
    return 1;
}

static wchar_t *utf8_to_wide(const char *s, unsigned long line)
{
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, NULL, 0);
    wchar_t *w;
    if (n <= 0)
        fail_usage("spec", line);
    w = (wchar_t *)xalloc((size_t)n * sizeof(wchar_t));
    if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, w, n) != n)
        fail_usage("spec", line);
    return w;
}

/* Reads the spec: blocks of "MODEL <name>", "SOCKET <path>", then one
 * "ARG <value>" line per argument, separated by blank lines. Any other line,
 * or a value that breaks a rule, rejects the whole spec (AXCESS_ERROR spec
 * <line number>, 0 for a rule checked after reading). */
static void parse_spec(const struct options *o)
{
    HANDLE h;
    LARGE_INTEGER size;
    char *text, *line, *next;
    DWORD got = 0;
    unsigned long lineno = 0;
    struct model *cur = NULL;
    int i, j;

    h = CreateFileW(o->spec, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE)
        fail("CreateFileW", GetLastError());
    if (!GetFileSizeEx(h, &size))
        fail("GetFileSizeEx", GetLastError());
    if (size.QuadPart > MAX_SPEC_BYTES)
        fail_usage("spec", 0);
    text = (char *)xalloc((size_t)size.QuadPart + 1);
    if (!ReadFile(h, text, (DWORD)size.QuadPart, &got, NULL) || got != (DWORD)size.QuadPart)
        fail("ReadFile", GetLastError());
    CloseHandle(h);
    text[got] = 0;
    if (strlen(text) != got)
        fail_usage("spec", 0); /* a NUL byte */
    line = text;
    if ((unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB &&
        (unsigned char)line[2] == 0xBF)
        line += 3;

    for (; line; line = next) {
        size_t len;
        lineno++;
        next = strchr(line, '\n');
        if (next)
            *next++ = 0;
        len = strlen(line);
        if (len && line[len - 1] == '\r')
            line[--len] = 0;
        if (len == 0) {
            cur = NULL;
            continue;
        }
        if (strncmp(line, "MODEL ", 6) == 0) {
            if (cur || g_model_count >= MAX_MODELS || !valid_name(line + 6))
                fail_usage("spec", lineno);
            cur = &g_models[g_model_count++];
            strcpy(cur->name, line + 6);
        } else if (strncmp(line, "SOCKET ", 7) == 0) {
            wchar_t *w;
            if (!cur || cur->socket)
                fail_usage("spec", lineno);
            w = utf8_to_wide(line + 7, lineno);
            cur->socket = full_path(w);
            free(w);
            if (!cur->socket)
                fail_usage("spec", lineno);
        } else if (strncmp(line, "ARG ", 4) == 0 || strcmp(line, "ARG") == 0) {
            if (!cur || !cur->socket || cur->argc >= MAX_ARGS)
                fail_usage("spec", lineno);
            cur->args[cur->argc++] = utf8_to_wide(line[3] ? line + 4 : "", lineno);
        } else {
            fail_usage("spec", lineno);
        }
    }
    free(text);

    if (g_model_count == 0)
        fail_usage("spec", 0);
    for (i = 0; i < g_model_count; i++) {
        struct model *m = &g_models[i];
        size_t slen;
        wchar_t *exe;
        for (j = 0; j < i; j++)
            if (strcmp(g_models[j].name, m->name) == 0 ||
                _wcsicmp(g_models[j].socket, m->socket) == 0)
                fail_usage("spec_duplicate", (unsigned long)i);
        if (!m->socket || m->argc < 1)
            fail_usage("spec_incomplete", (unsigned long)i);
        slen = wcslen(m->socket);
        if (!is_inside(o->scratch, m->socket) || slen < 6 ||
            _wcsicmp(m->socket + slen - 5, L".sock") != 0 || !unix_address(m->socket, &m->addr))
            fail_usage("spec_socket", (unsigned long)i);
        exe = full_path(m->args[0]);
        if (!exe || !is_inside(o->runtime, exe) || !is_file(exe))
            fail_usage("spec_program", (unsigned long)i);
        free(m->args[0]);
        m->args[0] = exe;
    }
}

/* Who owns the other end of an accepted loopback connection: the row whose
 * local address is the client's and whose remote port is our listener. */
static DWORD owner_pid(const struct sockaddr_in *peer, u_short listen_port_net)
{
    DWORD size = 0, e, i, pid = 0;
    MIB_TCPTABLE_OWNER_PID *table = NULL;
    int attempt;
    for (attempt = 0; attempt < 5; attempt++) {
        e = GetExtendedTcpTable(table, &size, FALSE, AF_INET, TCP_TABLE_OWNER_PID_CONNECTIONS, 0);
        if (e == NO_ERROR)
            break;
        free(table);
        table = NULL;
        if (e != ERROR_INSUFFICIENT_BUFFER)
            return 0;
        size += 4096;
        table = (MIB_TCPTABLE_OWNER_PID *)xalloc(size);
    }
    if (!table || e != NO_ERROR) {
        free(table);
        return 0;
    }
    for (i = 0; i < table->dwNumEntries; i++) {
        const MIB_TCPROW_OWNER_PID *row = &table->table[i];
        if (row->dwLocalAddr == peer->sin_addr.s_addr &&
            (u_short)(row->dwLocalPort & 0xFFFFu) == peer->sin_port &&
            row->dwRemoteAddr == htonl(INADDR_LOOPBACK) &&
            (u_short)(row->dwRemotePort & 0xFFFFu) == listen_port_net) {
            pid = row->dwOwningPid;
            break;
        }
    }
    free(table);
    return pid;
}

struct connection {
    SOCKET client;
    SOCKET service;
    volatile LONG refs;
};

struct pump {
    SOCKET from;
    SOCKET to;
    struct connection *conn;
};

static int send_all(SOCKET s, const char *buf, int n)
{
    int sent = 0, r;
    while (sent < n) {
        r = send(s, buf + sent, n - sent, 0);
        if (r <= 0)
            return 0;
        sent += r;
    }
    return 1;
}

/* Copies one direction until end of stream (then half-closes the other
 * side) or an error (then shuts both sockets so the other pump stops too). */
static DWORD WINAPI pump_thread(LPVOID arg)
{
    struct pump *p = (struct pump *)arg;
    char *buf = (char *)xalloc(RELAY_BUFFER);
    int r;
    for (;;) {
        r = recv(p->from, buf, RELAY_BUFFER, 0);
        if (r == 0) {
            shutdown(p->to, SD_SEND);
            break;
        }
        if (r < 0 || !send_all(p->to, buf, r)) {
            shutdown(p->from, SD_BOTH);
            shutdown(p->to, SD_BOTH);
            break;
        }
    }
    free(buf);
    if (InterlockedDecrement(&p->conn->refs) == 0) {
        closesocket(p->conn->client);
        closesocket(p->conn->service);
        free(p->conn);
    }
    free(p);
    return 0;
}

static void abort_socket(SOCKET s)
{
    struct linger lg;
    lg.l_onoff = 1;
    lg.l_linger = 0;
    setsockopt(s, SOL_SOCKET, SO_LINGER, (const char *)&lg, (int)sizeof(lg));
    closesocket(s);
}

struct accepted {
    SOCKET client;
    struct model *model;
};

static DWORD WINAPI connection_thread(LPVOID arg)
{
    struct accepted *a = (struct accepted *)arg;
    struct connection *conn;
    struct pump *up, *down;
    HANDLE t;
    SOCKET svc = socket(AF_UNIX, SOCK_STREAM, 0);
    if (svc == INVALID_SOCKET ||
        connect(svc, (struct sockaddr *)&a->model->addr, (int)sizeof(a->model->addr)) != 0) {
        /* The model is still loading (no socket yet), or has stopped. */
        if (svc != INVALID_SOCKET)
            closesocket(svc);
        abort_socket(a->client);
        free(a);
        return 0;
    }
    conn = (struct connection *)xalloc(sizeof(*conn));
    conn->client = a->client;
    conn->service = svc;
    conn->refs = 2;
    up = (struct pump *)xalloc(sizeof(*up));
    down = (struct pump *)xalloc(sizeof(*down));
    up->from = a->client;
    up->to = svc;
    up->conn = conn;
    down->from = svc;
    down->to = a->client;
    down->conn = conn;
    free(a);
    t = CreateThread(NULL, 0, pump_thread, down, 0, NULL);
    if (!t) {
        shutdown(conn->client, SD_BOTH);
        shutdown(conn->service, SD_BOTH);
        pump_thread(down); /* releases its reference */
    } else {
        CloseHandle(t);
    }
    return pump_thread(up);
}

static DWORD WINAPI accept_thread(LPVOID arg)
{
    struct model *m = (struct model *)arg;
    for (;;) {
        struct sockaddr_in peer;
        int len = (int)sizeof(peer);
        struct accepted *a;
        HANDLE t;
        SOCKET c = accept(m->listener, (struct sockaddr *)&peer, &len);
        if (c == INVALID_SOCKET) {
            if (g_stopping)
                return 0;
            Sleep(50);
            continue;
        }
        if (len != (int)sizeof(peer) || peer.sin_family != AF_INET ||
            owner_pid(&peer, m->port_net) != g_client_pid) {
            abort_socket(c);
            continue;
        }
        a = (struct accepted *)xalloc(sizeof(*a));
        a->client = c;
        a->model = m;
        t = CreateThread(NULL, 0, connection_thread, a, 0, NULL);
        if (!t) {
            abort_socket(c);
            free(a);
            continue;
        }
        CloseHandle(t);
    }
}

static DWORD WINAPI exit_thread(LPVOID arg)
{
    struct model *m = (struct model *)arg;
    DWORD code = 0;
    WaitForSingleObject(m->pi.hProcess, INFINITE);
    GetExitCodeProcess(m->pi.hProcess, &code);
    if (!g_stopping)
        out_line("EXIT %s %lu", m->name, code);
    return 0;
}

/* A loopback-only listener on a port Windows picks, which no other program
 * can also bind (SO_EXCLUSIVEADDRUSE). */
static void open_listener(struct model *m)
{
    struct sockaddr_in a;
    int len = (int)sizeof(a);
    BOOL exclusive = TRUE;
    m->listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (m->listener == INVALID_SOCKET)
        fail("socket", (DWORD)WSAGetLastError());
    if (setsockopt(m->listener, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, (const char *)&exclusive,
                   (int)sizeof(exclusive)) != 0)
        fail("setsockopt", (DWORD)WSAGetLastError());
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    a.sin_port = 0;
    if (bind(m->listener, (struct sockaddr *)&a, (int)sizeof(a)) != 0)
        fail("bind", (DWORD)WSAGetLastError());
    if (listen(m->listener, SOMAXCONN) != 0)
        fail("listen", (DWORD)WSAGetLastError());
    if (getsockname(m->listener, (struct sockaddr *)&a, &len) != 0)
        fail("getsockname", (DWORD)WSAGetLastError());
    m->port_net = a.sin_port;
}

static int run_serve(struct options *o)
{
    struct sandbox sb;
    WSADATA wsa;
    HANDLE in, t;
    HANDLE waits[MAX_MODELS];
    char buf[256];
    DWORD got;
    int i;

    require_dirs(o, 1);
    if (!o->log || !o->spec || !o->client_pid)
        fail_usage("usage", 0);
    g_client_pid = o->client_pid;
    parse_spec(o);
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        fail("WSAStartup", (DWORD)WSAGetLastError());

    sandbox_init(&sb, o, (DWORD)g_model_count);
    for (i = 0; i < g_model_count; i++) {
        struct model *m = &g_models[i];
        wchar_t *cmdline = build_cmdline(m->args, m->argc);
        DeleteFileW(m->socket); /* a socket file left by an earlier run */
        sandbox_start(&sb, m->args[0], cmdline, &m->pi);
        free(cmdline);
    }
    for (i = 0; i < g_model_count; i++)
        open_listener(&g_models[i]);
    for (i = 0; i < g_model_count; i++)
        out_line("PORT %s %u", g_models[i].name, (unsigned)ntohs(g_models[i].port_net));
    out_line("READY");
    for (i = 0; i < g_model_count; i++) {
        t = CreateThread(NULL, 0, exit_thread, &g_models[i], 0, NULL);
        if (!t)
            fail("CreateThread", GetLastError());
        CloseHandle(t);
        t = CreateThread(NULL, 0, accept_thread, &g_models[i], 0, NULL);
        if (!t)
            fail("CreateThread", GetLastError());
        CloseHandle(t);
    }

    /* The backend holds our stdin open. When it closes (or the backend
     * dies), stop every model process. */
    in = GetStdHandle(STD_INPUT_HANDLE);
    if (in && in != INVALID_HANDLE_VALUE)
        while (ReadFile(in, buf, sizeof(buf), &got, NULL) && got > 0) {
        }
    InterlockedExchange(&g_stopping, 1);
    TerminateJobObject(sb.job, 1);
    for (i = 0; i < g_model_count; i++)
        waits[i] = g_models[i].pi.hProcess;
    WaitForMultipleObjects((DWORD)g_model_count, waits, TRUE, 10000);
    return 0;
}

/* ------------------------------------------------------------------ */

int wmain(int argc, wchar_t **argv)
{
    struct options o;
    InitializeCriticalSection(&g_out_lock);
    _setmode(_fileno(stdout), _O_BINARY);
    memset(&o, 0, sizeof(o));
    if (argc < 2)
        fail_usage("usage", 0);
    if (wcscmp(argv[1], L"check") == 0) {
        g_mode = MODE_CHECK;
        require_windows_version();
        parse_options(argc, argv, 2, &o);
        return run_check(&o);
    }
    if (wcscmp(argv[1], L"serve") == 0) {
        g_mode = MODE_SERVE;
        require_windows_version();
        parse_options(argc, argv, 2, &o);
        return run_serve(&o);
    }
    if (wcscmp(argv[1], L"probe-inner") == 0 && argc >= 3) {
        g_mode = MODE_INNER;
        o.inner_sock = full_path(argv[2]);
        parse_options(argc, argv, 3, &o);
        return run_inner(&o);
    }
    fail_usage("usage", 0);
}
