# Isolating llama-server on Windows

Research date: 2026-11-11. Nothing was installed or run on Windows. Every
claim below comes from a cited source or from reading source code. Claims
marked **Unconfirmed** need a test on a real Windows 10 and Windows 11
machine before we rely on them. Numbers in square brackets point to the
Sources list at the end.

## Summary

- **Use an AppContainer, ideally the stricter "less privileged" kind
  (LPAC), with no network capabilities.** Windows blocks all network
  traffic for an AppContainer that has no `internetClient`,
  `internetClientServer` or `privateNetworkClientServer` capability [3][9].
  This includes loopback in both directions [9][10]. It needs no admin
  rights: the profile is per user [5], and the user can change ACLs on
  folders they own [17].
- **Talk to it through a UNIX socket file (AF_UNIX), not TCP.**
  llama-server accepts `--host <path>.sock` [20]. Its HTTP library has
  compiled AF_UNIX support on Windows since cpp-httplib 0.20.1, when the
  Windows SDK header `afunix.h` is present [21][22][23]. llama.cpp's own
  Windows release build uses a current Windows SDK [25]. AF_UNIX exists on
  Windows 10 build 17063 and later [11].
- **Two gaps need a test before we commit.**
  1. **Unconfirmed:** that an AF_UNIX socket made inside an AppContainer can
     be reached by a normal process outside it. No Microsoft page covers
     this. Socket access is controlled by the socket file's ACL, and the
     connecting side needs write access [11][12].
  2. **Python cannot open AF_UNIX sockets on Windows.** CPython does not
     define `socket.AF_UNIX` on Windows; the pull request to add it is
     still open [13][14]. httpx's transport (httpcore) refuses UNIX sockets
     on Windows outright [15]. We need a small client shim (see the design).
- **Python cannot launch an AppContainer with `subprocess`.** Its
  `STARTUPINFO.lpAttributeList` supports only `handle_list` [16]. We need
  `ctypes` calls or a small native launcher. A native launcher is the
  better choice (reasons below).
- **A firewall rule is the wrong tool.** It needs admin rights to add, it
  does not limit files, and it can be switched off by a profile change or
  a third-party firewall [26][27][28].
- **Job objects do not block the network.** They limit processes, memory,
  CPU and bandwidth, but have no on/off switch for network access [29][30].
- **Windows Sandbox is too heavy.** It is a virtual machine, is not
  available on Windows Home, and must be turned on as an optional feature
  [31][32].
- **Strong prior art exists.** Chromium runs its on-device model service
  (which loads a local model and uses the GPU) in an LPAC with no network
  capability [33][34][35]. GitHub's Copilot desktop app and VS Code's agent
  sandbox use AppContainers too [37][38].
- **Fail closed:** any failed API call, a failed network probe, or a
  Windows version below 10 1809 means AI does not start. Saved results
  still work.

## Comparison

| Option | Blocks network | Limits files | Needs admin | How the backend talks to it | Effort | Risks |
| --- | --- | --- | --- | --- | --- | --- |
| **AppContainer, no capabilities (recommended base)** | Yes. WFP blocks internet, LAN and loopback, in and out [3][9][10]. | Yes. Only paths whose ACL names the container (or ALL APPLICATION PACKAGES) [3]. | No [5][17]. | AF_UNIX socket file in a shared folder [20][11]. Loopback TCP is blocked [10]. llama-server has no named-pipe listener [20]. | Medium: launcher, ACLs, probe, Python socket shim. | AF_UNIX across the container boundary is **Unconfirmed**. Container can still read places open to ALL APPLICATION PACKAGES (Windows, Program Files) [3]. A container that can start some system programs could borrow their firewall allow rules [9]; block child processes [6]. |
| **LPAC (AppContainer that opts out of ALL APPLICATION PACKAGES)** | Same as above [3][4]. | Tighter: no registry, COM or shared system folders without extra capabilities [4]. | No [4][5]. | Same as above. | Medium, plus GPU testing. | Vulkan may fail: the Vulkan loader reads the registry, uses PnP APIs and DXGI to find drivers [39]. LPAC needs `registryRead` to read the registry [4]. **Unconfirmed** which capabilities Vulkan needs. Chromium's LPAC model service uses `lpacPnpNotifications` and D3D12/WebGPU, not Vulkan [34][35]. |
| **Loopback exemption for the AppContainer** (`CheckNetIsolation`) | Partly: removes the loopback block only. | Same as AppContainer. | **Yes** [10]. | Loopback TCP. Inbound needs `CheckNetIsolation -is`, which "must be running continuously" [10]. | Low code, high support cost. | Admin needed. Any local process, any user, could reach the server. Rejected. |
| **Windows Firewall block rule per program** | Partly. Rules are per full program path, no wildcards [26]. Loopback: Microsoft does not say clearly; forum reports say the firewall does not filter loopback (**Unconfirmed**) [28]. | No. | **Yes** for rule creation: Microsoft says rule creation at run time needs "administrative privilege" [26]. Codex needs admin setup for its firewall rules [41]. | Loopback TCP. | Low. | Silent failure if a profile is turned off or a third-party firewall takes over [27]. Does nothing for files. Path-bound, so every update or install folder change needs a new rule. |
| **Job object** | No. Only bandwidth rate and DSCP tagging [29]. | No. | No. | Any. | Low. | Not isolation. Still useful *with* an AppContainer: kill on close, one-process limit, memory cap [30]. |
| **Restricted token / low integrity only** (Firefox, Codex "unelevated") | No. Codex documents weaker network isolation in this mode [41]. | Partly (ACLs, integrity labels) [36]. | No. | Loopback TCP. | Medium. | Does not meet requirement 1. |
| **Windows Sandbox / Hyper-V** | Yes, if networking is turned off in the .wsb file [31]. | Yes (mapped folders) [31]. | **Yes** to turn on the feature [32]. Not on Windows Home [31]. Needs virtualization in BIOS [32]. | Mapped folder or network; one instance at a time [31]. | High. | Edition-limited, slow start, GPU only as virtual GPU [31]. Rejected. |
| **Microsoft Execution Containers (MXC)** | Policy-based, egress can default to deny [40]. | Yes (read, write, deny lists) [40]. | No admin setup [41]. | stdio documented; others **Unconfirmed** [40]. | Medium (Node or .NET SDK, not Python) [40]. | **Windows 11 only**, recent builds (24H2 build 26100.9278+) [41][42]. Fails requirement 4 for Windows 10. Worth revisiting later. |

## Recommended design

### The shape

```text
Axcess backend (Python, normal user)
  |  starts, holds stdin pipe
  v
axcess-ai-launcher.exe (native, normal user, outside the container)
  |  creates job object + AppContainer (LPAC), zero network capabilities
  v
llama-server.exe (inside LPAC, inside job, cannot start children)
  listens on  <scratch>\ai.sock  (AF_UNIX)
  ^
  |  Python connects to ai.sock with a small Winsock shim
Axcess backend
```

### Why a native launcher, not only ctypes

- Python's `subprocess` cannot pass `SECURITY_CAPABILITIES` [16].
- `ctypes` *can* call every API needed (`userenv.dll`, `kernel32.dll`,
  `advapi32.dll`) [1][5][6]. But the frozen desktop backend is a
  PyInstaller program (`desktop/backend.spec`). It cannot run
  `python -c <probe>` inside the sandbox the way `ai/sandbox.py` does
  today. The launcher can run its own probe mode instead.
- A small C or Rust program is easier to review and test as a security
  boundary. It also gives us "die with parent" for free (see step 9).
- It must be signed with the rest of the app once Windows signing exists
  (`docs/desktop-app.md` says Windows builds are not Authenticode signed
  yet). Managed machines may block unsigned helpers (**Unconfirmed** for
  our users).

### Step by step

1. **Check the Windows version.** Require Windows 10 1809 (build 17763) or
   later. Chromium uses the same floor: LPAC APIs are missing before 1703,
   and process mitigations cannot be applied to an AppContainer before
   1809 [35]. AF_UNIX needs build 17063 or later [11]. Lower: fail closed.

2. **Put the files where the user owns them.** Unpack or copy the
   SHA-256-checked `llama-server.exe` and its DLLs into the user's AI
   folder (for example `ai_dir\runtime\<build>`), not only the install
   folder. A per-machine install lives in Program Files, which a normal
   user cannot re-ACL [17]. A per-user install already lives under
   `%LOCALAPPDATA%\Programs\Axcess` (`docs/desktop-app.md`). Copying makes
   both cases the same and needs no admin.

3. **Create or reuse one AppContainer profile.** Call
   `CreateAppContainerProfile("Axcess.LocalAI", ...)` with **zero**
   capabilities. If it returns `HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)`,
   call `DeriveAppContainerSidFromAppContainerName` to get the SID [1][5].
   Use one stable name, so ACL entries stay valid. GitHub's Copilot app
   uses a new random container per process, which makes per-container
   settings impossible to manage [37].

4. **Set ACLs (no admin; the user owns these folders) [17].** Give the
   container SID:
   - runtime folder: read and execute, inherited;
   - models folder: read, inherited;
   - scratch folder (`ai_dir\scratch`): modify, inherited. The socket and
     temp files go here.

   Nothing else. Do not add the SID to the scan data folder. The container
   runs at Low integrity, but an explicit ACE still grants access to a
   Medium-labelled folder [1]. An LPAC reads nothing that lacks an ACE for
   it, so these three grants are close to the full list [1][4].

5. **Create a job object** [30]. Set:
   - `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`;
   - `JOB_OBJECT_LIMIT_ACTIVE_PROCESS` = 1;
   - a job memory limit from the model tier's memory guidance;
   - basic UI restrictions (no clipboard, desktop or global atoms).

6. **Build the attribute list** for `CreateProcessW` with
   `EXTENDED_STARTUPINFO_PRESENT` [1][6]:
   - `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`: the container SID,
     capability count 0 (add only non-network LPAC capabilities such as
     `registryRead` or `lpacPnpNotifications` if the GPU test proves they
     are needed [4][34]);
   - `PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY` =
     `PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT` (this makes it an
     LPAC) [1];
   - `PROC_THREAD_ATTRIBUTE_CHILD_PROCESS_POLICY` =
     `PROCESS_CREATION_CHILD_PROCESS_RESTRICTED` [6]. This closes the
     Project Zero bypass, where a container starts a system program that
     has its own firewall allow rule [9];
   - `PROC_THREAD_ATTRIBUTE_JOB_LIST` = the job from step 5 [6];
   - `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` = only the log file handle and a
     NUL stdin [6];
   - optionally `PROC_THREAD_ATTRIBUTE_MITIGATION_POLICY` (for example
     extension point disable). Add each one only after a GPU test, since
     driver DLLs may break [6].

7. **Run the probe first, in the identical sandbox.** The launcher starts
   a copy of itself in `--probe` mode with the same attribute list.
   Outside, the launcher opens a loopback TCP listener and an AF_UNIX
   listener in scratch. Inside, the probe must show:
   - TCP connect to a public address fails with an OS denial. Today's
     Linux rule stays: a timeout is not proof [`ai/sandbox.py`].
     **Unconfirmed:** the exact Winsock error for a WFP block (expected
     `WSAEACCES`, 10013). Inbound loopback drops are silent, so clients
     time out [9].
   - TCP connect to the outside loopback listener never arrives. The
     outside listener is the judge, not the inside error.
   - A TCP listener opened inside cannot be reached from outside.
   - Opening a file in the user's Documents folder fails; writing in the
     runtime folder fails; writing in scratch works.
   - The probe binds `scratch\probe.sock`; the outside launcher can
     connect to it and exchange one message. This proves the AF_UNIX
     channel (gap 1 in the summary).

   Any failure: exit with a reason code. Python raises `IsolationError`
   (`network_test_failed` or `sandbox_unavailable`) and AI does not start.

8. **Start llama-server** with a fixed argument list:

   ```text
   llama-server.exe -m <model.gguf> [--mmproj <proj.gguf>]
     --host <scratch>\ai.sock --offline --no-webui -c <ctx> -t <threads>
   ```

   - `--host <path>.sock` turns on AF_UNIX [20][24].
   - `--offline` "prevents network access" in llama.cpp's own downloader
     [24]. The sandbox blocks it anyway.
   - `--no-webui` turns off the built-in web page [24].
   - Never pass `-hf`, `--ui-mcp-proxy`, `--mcp-servers-*` or `--agent`
     [24].
   - **Do not use router mode** (`--models-dir`). It starts child
     `llama-server` processes and talks to them on loopback TCP ports
     [24][43]. That breaks the one-process limit, the child-process
     block and loopback isolation. Run one process per model instead.
   - Keep the socket path short. cpp-httplib refuses a path longer than
     `sun_path` [22].
   - Environment: only `SystemRoot`, `TEMP` and `TMP` (pointing to
     scratch), and `PATH` set to the runtime folder. No proxy variables.

9. **Tie lifetimes together.** The launcher holds the job handle and
   watches its own stdin, which the Python backend holds open. Stdin
   closed (backend gone): the launcher calls `TerminateJobObject`.
   Launcher gone: its job handle closes and `KILL_ON_JOB_CLOSE` kills the
   server [30]. This matches `bwrap --die-with-parent` on Linux.

10. **Connect from Python.** httpcore refuses UNIX sockets on Windows [15],
    and CPython has no `AF_UNIX` there [13][14]. Two choices:
    - **A (preferred, Unconfirmed):** a small `httpcore.NetworkBackend`
      that creates the socket with Winsock through `ctypes`
      (`socket(AF_UNIX=1, SOCK_STREAM, 0)`, `connect` with a
      `sockaddr_un`), then wraps the handle with
      `socket.socket(fileno=...)`. Whether CPython accepts an AF_UNIX
      handle this way on Windows is untested.
    - **B (fallback):** the launcher relays between the AF_UNIX socket and
      a named pipe whose ACL allows only the current user. Python opens
      the pipe as a file. Still no TCP listener anywhere.

11. **Health check and use.** `GET /health` over the socket, then the
    normal requests. Mark the runtime `isolated = True` only after steps
    7 to 11 pass, as `ai/runtime.py` does today.

12. **GPU fallback order, each still fully network-isolated.**
    1. LPAC + Vulkan build.
    2. Regular AppContainer + Vulkan build (more file reads allowed:
       places open to ALL APPLICATION PACKAGES [1]).
    3. LPAC + CPU build.

    Never fall back to "no sandbox". Which fallbacks to ship is a product
    decision (see open questions).

## Open questions

1. **Does AF_UNIX work across the AppContainer boundary?** Test: socket
   created inside an LPAC, connected from a Medium-integrity process
   outside, on Windows 10 22H2 and Windows 11 24H2. One Codex report shows
   AF_UNIX failing for tools started from a packaged sandbox, cause not
   known [44]. If it fails, the fallback is a launcher-side named pipe
   bridge plus a different in-container transport, which needs more design.
2. **Does the official Windows `llama-server.exe` include AF_UNIX?** The
   code is guarded by `CPPHTTPLIB_HAVE_AFUNIX_H` [21][22]. The release
   build uses a current Windows SDK [25], so it very likely does. Test:
   start it with `--host C:\t\a.sock` and look for `unix://` in the log
   [20]. If not, build our own.
3. **Does Vulkan work in an LPAC, and with which capabilities?** No source
   found. Test on AMD, Intel and NVIDIA. Try `registryRead` and
   `lpacPnpNotifications` first [4][34].
4. **Which Winsock error does a blocked connect return inside the
   container?** Needed so the probe accepts only an OS denial.
5. **Does AppContainer network blocking hold when a firewall profile is
   off or a third-party firewall is active?** Microsoft says the firewall
   service configures the filters [9] and should not be stopped [27]. The
   probe in step 7 covers this at run time either way.
6. **Python shim A or bridge B?** Decide after test 1 and a short spike.
7. **Which GPU fallbacks to ship** (step 12), and what the Settings page
   should say when only the CPU build can run.
8. **Windows 11 only, later:** MXC may replace our launcher once Windows 10
   support ends for Axcess. It has Node and .NET SDKs, not Python [40].
9. **Noticed while reading, not tested:** `test_network_boundary` in
   `src/audit/ai/sandbox.py` runs `sys.executable -I -S -c <probe>`. In the
   PyInstaller desktop build, `sys.executable` is the backend program
   (`desktop/backend_entry.py`), which does not accept `-c`. If that is
   right, the probe would always fail in the packaged macOS app, so AI
   would not start there (fail closed, but not working). Worth checking.
10. **Loopback on macOS:** the current macOS profile allows localhost
    connections (`ai/sandbox.py`). So "no listener anyone else can reach"
    differs by platform today. Not a Windows question, but relevant to
    matching behaviour across platforms.

## Sources

Some numbers are skipped; the list keeps the numbers used in the text.

Microsoft Learn

1. Launch an AppContainer (AppContainer and LPAC launch steps, Low IL, ACL intersection, LPAC needs `registryRead`/`lpacCom`): https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer
3. AppContainer isolation (file, network, process isolation): https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation
4. Same page as [1], LPAC section: https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer#appcontainer-overview
5. CreateAppContainerProfile (per user, per app; ERROR_ALREADY_EXISTS; Windows 8+): https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile
6. UpdateProcThreadAttribute (SECURITY_CAPABILITIES, CHILD_PROCESS_POLICY, JOB_LIST, HANDLE_LIST, MITIGATION_POLICY): https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute
9. Google Project Zero, "Understanding Network Access in Windows AppContainers" (WFP enforcement, silent loopback drops, admin-only loopback exemption, spawned-program bypass): https://projectzero.google/2021/08/understanding-network-access-windows-app.html
10. Interprocess communication: Loopback (blocked by default; `CheckNetIsolation` needs admin; `-is` must keep running; named pipes): https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication#loopback
    Also: Troubleshooting UWP app connectivity (default block filters, loopback not received by default): https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/troubleshooting-uwp-firewall
11. Microsoft Command Line blog, "AF_UNIX comes to Windows" (build 17063; secured by file permissions; connecting process needs write permission): https://devblogs.microsoft.com/commandline/af_unix-comes-to-windows/
12. Lupus/izba experiment: Windows AF_UNIX connect needs write access on the socket file (third party, Windows 11 24H2): https://github.com/Lupus/izba/pull/277

Python and httpx

13. CPython issue gh-77589, "Enable AF_UNIX support in Windows" (open): https://github.com/python/cpython/issues/77589
14. CPython PR #137420 (open, not merged as of 2026-11-11): https://github.com/python/cpython/pull/137420
15. httpcore 1.0.9 sync backend raises "Attempted to connect to a UNIX socket on a Windows system": https://github.com/encode/httpcore/blob/1.0.9/httpcore/_backends/sync.py
16. Python `subprocess.STARTUPINFO.lpAttributeList` supports only `handle_list`: https://docs.python.org/3/library/subprocess.html#subprocess.STARTUPINFO.lpAttributeList
17. SetNamedSecurityInfoW (setting a DACL needs WRITE_DAC or ownership): https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow

llama.cpp (master at commit 956591f4570aa6636895d90439892fef7c075b17)

20. Server README, `--host` accepts "UNIX socket paths ending in .sock": https://github.com/ggml-org/llama.cpp/blob/956591f4570aa6636895d90439892fef7c075b17/tools/server/README.md#L194
    Server code sets AF_UNIX for `.sock` hosts and logs `unix://`: https://github.com/ggml-org/llama.cpp/blob/956591f4570aa6636895d90439892fef7c075b17/tools/server/server-http.cpp#L501-L524
21. Vendored cpp-httplib includes `<afunix.h>` on Windows when present: https://github.com/ggml-org/llama.cpp/blob/956591f4570aa6636895d90439892fef7c075b17/vendor/cpp-httplib/httplib.h#L336-L342
22. Vendored cpp-httplib AF_UNIX path, `sun_path` length check, Windows SO_REUSEADDR note: https://github.com/ggml-org/llama.cpp/blob/956591f4570aa6636895d90439892fef7c075b17/vendor/cpp-httplib/httplib.cpp#L2535-L2578
23. cpp-httplib PR #2115 "Add AF_UNIX support on windows" (merged 2025-03-24): https://github.com/yhirose/cpp-httplib/pull/2115
    llama.cpp PR #12613 "server : Support listening on a unix socket" (merged 2025-03-27): https://github.com/ggml-org/llama.cpp/pull/12613
24. Server README flags: `--offline` (L112), `--ui-mcp-proxy` / MCP / `--agent` (L205-L210), `--no-webui` (L211), router `--models-dir` (L231): https://github.com/ggml-org/llama.cpp/blob/956591f4570aa6636895d90439892fef7c075b17/tools/server/README.md#L112
25. Release workflow: Windows builds on `windows-2025` / `windows-2025-vs2026` runners; Vulkan zip takes `llama-server` from the windows-cpu build: https://github.com/ggml-org/llama.cpp/blob/956591f4570aa6636895d90439892fef7c075b17/.github/workflows/release.yml#L874-L940

Windows Firewall, job objects, Windows Sandbox

26. Windows Firewall rules (full program path only, no wildcards; run-time rule creation needs admin; non-admin prompts create block rules): https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules
27. Manage Windows Firewall with the command line (profiles can be turned off; third-party firewalls can disable rule types; do not stop MpsSvc): https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/configure-with-command-line
28. Loopback and Windows Firewall: no Microsoft statement found. Forum claims only (**Unconfirmed**): https://www.wilderssecurity.com/threads/how-to-get-windows-firewall-to-successfully-block-ports.402427/
29. JOBOBJECT_NET_RATE_CONTROL_INFORMATION (bandwidth and DSCP only): https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_net_rate_control_information
30. Job Objects (limits, KILL_ON_JOB_CLOSE, child processes join the job): https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
31. Windows Sandbox overview (Pro/Enterprise/Education, not Home; one instance; networking on by default): https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/
32. Install Windows Sandbox (virtualization in BIOS; optional feature; PowerShell "as Administrator"): https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install

Prior art

33. Chromium, AppContainer names per sandbox type, including `cr.sb.odm` (on-device model): https://github.com/chromium/chromium/blob/cd162bfd0115951c6cb38d7493074a905e3525a8/sandbox/policy/win/sandbox_win.cc#L331-L350
34. Chromium, capabilities per sandbox: the on-device model service is an LPAC with only `lpacChromeInstallFiles`, `registryRead`, `lpacPnpNotifications` and an impersonation capability, and no network capability: https://github.com/chromium/chromium/blob/cd162bfd0115951c6cb38d7493074a905e3525a8/sandbox/policy/win/sandbox_win.cc#L380-L443
    Chromium's on-device model uses WebGPU (Dawn) for the GPU: https://github.com/chromium/chromium/blob/cd162bfd0115951c6cb38d7493074a905e3525a8/services/on_device_model/ml/gpu_blocklist.cc
35. Chromium, AppContainer sandbox needs Windows 10 RS5 (1809): https://github.com/chromium/chromium/blob/cd162bfd0115951c6cb38d7493074a905e3525a8/sandbox/features.cc#L13-L20
36. Chromium sandbox design (restricted token, job object, integrity levels): https://github.com/chromium/chromium/blob/cd162bfd0115951c6cb38d7493074a905e3525a8/docs/design/sandbox.md
    Firefox (restricted tokens, job objects, integrity levels, alternate desktop; no AppContainer listed): https://wiki.mozilla.org/Security/Sandbox
37. GitHub Copilot desktop app: per-process AppContainer; loopback to host silently dropped without an exemption: https://github.com/github/app/issues/4278
38. VS Code agent sandbox runs terminals in an AppContainer (bug report): https://github.com/microsoft/vscode/issues/345603
    VS Code extension host is a utility process, not an OS sandbox: https://code.visualstudio.com/blogs/2022/11/28/vscode-sandbox
39. Vulkan loader driver discovery on Windows (registry, PnP, DriverStore): https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderDriverInterface.md
40. Microsoft Execution Containers (MXC) repository (backends, policy, SDKs): https://github.com/microsoft/mxc
41. OpenAI Codex Windows sandbox modes (mxc needs no admin; elevated needs admin setup and firewall rules; unelevated has weaker network isolation): https://learn.chatgpt.com/docs/windows/windows-sandbox.md
42. Windows 365 support for MXC (process isolation, Windows 11): https://learn.microsoft.com/en-us/windows-365/process-isolation-on-cloud-pcs
43. llama.cpp router mode spawns child servers on a free TCP port: https://github.com/ggml-org/llama.cpp/blob/956591f4570aa6636895d90439892fef7c075b17/tools/server/server-models.cpp#L1219-L1270
44. Codex issue: tools launched from a sandboxed packaged context fail to use AF_UNIX endpoints in AppData (cause not established): https://github.com/openai/codex/issues/53886

Repository files read (not changed): `src/audit/ai/sandbox.py`,
`src/audit/ai/runtime.py`, `docs/internal/llama-cpp-plan.md`,
`docs/desktop-app.md`, `desktop/electron-builder.config.cjs`,
`desktop/backend.spec`, `desktop/backend_entry.py`.
