const { app, BrowserWindow, dialog, session, shell } = require("electron");

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const {
  OutputTail,
  contentSecurityPolicy,
  desktopEnvironment,
  historyStepFor,
  isAxcessUrl,
  isSafeExternalUrl,
  nextZoomLevel,
  portableDataDir,
  windowsUpdateMethod,
  zoomActionFor,
  startupFailureDetails,
  PORTABLE_DATA_FOLDER,
} = require("./runtime.cjs");
const {
  RELEASES_API_URL,
  describeRelease,
  displayVersion,
  isNewerRelease,
  isReleaseAssetUrl,
} = require("./updates.cjs");
const packageJson = require("../package.json");

// No macOS keychain prompt. Chromium asks the keychain for an "Axcess Safe
// Storage" key to encrypt saved cookies and passwords, and while the app is
// not signed by Apple, macOS asks people to allow that ("Axcess wants to use
// your confidential information"), again after updates. Axcess keeps nothing
// there: the desktop backend sets no access cookie (AUDIT_ACCESS_TOKEN is
// empty, runtime.cjs), the window keeps only display preferences in
// localStorage, and reports live in the backend's own database. The scan
// browsers already use a stand-in keychain (Playwright passes the same
// switch). Set before the app is ready, when Chromium reads its switches.
if (process.platform === "darwin") app.commandLine.appendSwitch("use-mock-keychain");

const STARTUP_TIMEOUT_MS = 60_000;
const HEALTH_POLL_MS = 200;
const UPDATE_FETCH_TIMEOUT_MS = 10_000;

// Portable mode (the Windows zip): with "Axcess data" beside Axcess.exe,
// everything Axcess writes goes there instead of %APPDATA%\Axcess: the
// reports and their images, settings, logs, the browser profile, crash
// reports, and temporary files (TEMP and TMP, which the backend, Playwright
// and Chromium inherit). Set before anything reads userData, the
// single-instance lock included, so a portable copy and an installed one
// each keep their own reports. Windows itself still records a few things
// about any program it runs (recent apps, prefetch).
const portableData = app.isPackaged
  ? portableDataDir({ execPath: process.execPath, platform: process.platform, exists: fs.existsSync })
  : null;
// A data folder Axcess cannot write to (unzipped somewhere read-only) stops
// it with a message, rather than quietly writing to %APPDATA% after all.
let portableDataUnwritable = null;
if (portableData) {
  app.setPath("userData", portableData);
  app.setPath("crashDumps", path.join(portableData, "crash reports"));
  const temporary = path.join(portableData, "temporary files");
  try {
    fs.mkdirSync(temporary, { recursive: true });
    fs.accessSync(portableData, fs.constants.W_OK);
    process.env.TEMP = temporary;
    process.env.TMP = temporary;
  } catch (error) {
    portableDataUnwritable = error;
  }
}
const repoRoot = path.resolve(__dirname, "../..");
const appIcon = path.join(__dirname, "../assets/axcess.png");
let mainWindow = null;
let backendProcess = null;
let backendOrigin = null;
let backendOutput = new OutputTail();
let backendExitCode = null;
// Backend output is copied into the launcher log only until /health answers;
// after that the service writes its own log and this one would just repeat it.
let backendReady = false;
const LAUNCHER_LOG_LIMIT = 1024 * 1024;
let quitting = false;
let updateOffered = false;
let failureShown = false;

// Packaged builds have no terminal, so the launcher keeps its own log next to
// the backend's. This is the first place to look when Axcess "could not start".
function launcherLogPath() {
  return path.join(app.getPath("userData"), "data", "logs", "launcher.log");
}

function logLauncher(line) {
  const entry = `${new Date().toISOString()} ${line}\n`;
  if (!app.isPackaged) process.stderr.write(`[Axcess launcher] ${entry}`);
  try {
    fs.mkdirSync(path.dirname(launcherLogPath()), { recursive: true });
    fs.appendFileSync(launcherLogPath(), entry);
  } catch {
    // Logging must never be the reason startup fails.
  }
}

function findOpenPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen({ host: "127.0.0.1", port: 0, exclusive: true }, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

function backendLaunch(port) {
  if (app.isPackaged) {
    const executable = process.platform === "win32" ? "axcess-server.exe" : "axcess-server";
    const command = path.join(
      process.resourcesPath,
      "backend-dist",
      "axcess-server",
      executable,
    );
    return { command, args: ["--host", "127.0.0.1", "--port", String(port)], cwd: path.dirname(command) };
  }

  const command = process.env.AXCESS_UV_EXECUTABLE || "uv";
  return {
    command,
    args: [
      "run",
      "python",
      "-m",
      "audit.desktop_server",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
    ],
    cwd: repoRoot,
  };
}

function startBackend(port) {
  const launch = backendLaunch(port);
  if (app.isPackaged && !fs.existsSync(launch.command)) {
    throw new Error(`The packaged Axcess backend is missing: ${launch.command}`);
  }
  const env = {
    ...process.env,
    ...desktopEnvironment({
      userDataPath: app.getPath("userData"),
      electronExecutable: process.execPath,
      resourcesPath: process.resourcesPath,
      packaged: app.isPackaged,
    }),
  };
  backendOutput = new OutputTail();
  backendExitCode = null;
  backendReady = false;
  try {
    if (fs.statSync(launcherLogPath()).size > LAUNCHER_LOG_LIMIT) {
      fs.renameSync(launcherLogPath(), `${launcherLogPath()}.1`);
    }
  } catch {
    // No log yet, or it cannot be rotated; appending still works or is skipped.
  }
  logLauncher(
    `starting backend: ${launch.command} ${launch.args.join(" ")} (cwd ${launch.cwd}, ` +
      `version ${buildLabel()}, packaged ${app.isPackaged})`,
  );
  backendProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env,
    shell: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const relay = (chunk) => {
    backendOutput.push(chunk);
    if (!app.isPackaged) process.stderr.write(`[Axcess backend] ${chunk}`);
    if (backendReady) return;
    try {
      fs.appendFileSync(launcherLogPath(), String(chunk));
    } catch {
      // Best effort; the in-memory tail still feeds the error page.
    }
  };
  backendProcess.stdout.on("data", relay);
  backendProcess.stderr.on("data", relay);
  backendProcess.once("exit", (code, signal) => {
    backendProcess = null;
    backendExitCode = code === null ? signal : code;
    logLauncher(`backend exited: code ${code} signal ${signal}`);
    if (!quitting && code !== 0) {
      showStartupFailure(new Error("Axcess backend stopped unexpectedly."));
    }
  });
  backendProcess.once("error", (error) => {
    logLauncher(`backend could not be spawned: ${error.message}`);
    showStartupFailure(error);
  });
}

function healthCheck(origin) {
  return new Promise((resolve) => {
    const request = http.get(`${origin}/health`, { timeout: 1_000 }, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.once("timeout", () => {
      request.destroy();
      resolve(false);
    });
    request.once("error", () => resolve(false));
  });
}

async function waitForBackend(origin) {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (!backendProcess) throw new Error("Axcess backend stopped during startup.");
    if (await healthCheck(origin)) {
      backendReady = true;
      logLauncher(`backend ready at ${origin}`);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, HEALTH_POLL_MS));
  }
  throw new Error(
    `Axcess took too long to start: ${origin}/health did not answer within ` +
      `${STARTUP_TIMEOUT_MS / 1000} seconds.`,
  );
}

function configureWindowSecurity(window) {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    if (!backendOrigin || !isAxcessUrl(details.url, backendOrigin)) {
      callback({ responseHeaders: details.responseHeaders });
      return;
    }
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [contentSecurityPolicy()],
      },
    });
  });

  window.webContents.on("will-navigate", (event, target) => {
    if (backendOrigin && isAxcessUrl(target, backendOrigin)) return;
    event.preventDefault();
    if (isSafeExternalUrl(target)) void shell.openExternal(target);
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (isSafeExternalUrl(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 720,
    minHeight: 600,
    show: false,
    backgroundColor: "#f7f8fa",
    title: "Axcess",
    icon: appIcon,
    // Hide the File/Edit/View menu bar by default. `autoHideMenuBar` rather
    // than `Menu.setApplicationMenu(null)`: removing the menu outright would
    // also remove its accelerators, and a keyboard-only user would lose the
    // standard edit and window shortcuts. Hidden, the bar still appears on Alt
    // and every shortcut keeps working. No effect on macOS, where the menu
    // lives in the system bar and cannot be hidden per-window.
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
      spellcheck: true,
    },
  });
  configureWindowSecurity(window);
  // The View menu binds Zoom In to `CommandOrControl+Plus`, which matches only
  // a literal "+" -- Shift+= on most layouts -- while Zoom Out binds a key
  // that exists on its own. The app zoomed out but never in. Handling the
  // keystroke here catches every way a keyboard produces it, and
  // `preventDefault` also suppresses the menu's own accelerator, so the
  // remaining shortcuts cannot fire twice.
  window.webContents.on("before-input-event", (event, input) => {
    const action = zoomActionFor(input);
    if (!action) return;
    event.preventDefault();
    const contents = window.webContents;
    contents.setZoomLevel(nextZoomLevel(contents.getZoomLevel(), action));
  });
  // Mouse back/forward side buttons (Windows and Linux; see historyStepFor).
  // The app is a single-page app on browser history, so stepping the
  // window's history walks its routes. A two-finger touchpad swipe is
  // handled in the page itself (useSwipeNavigation), where it can tell a
  // swipe from scrolling a wide table sideways.
  window.on("app-command", (event, command) => {
    const step = historyStepFor(command);
    if (!step) return;
    event.preventDefault();
    const history = window.webContents.navigationHistory;
    if (step === "back" && history.canGoBack()) history.goBack();
    if (step === "forward" && history.canGoForward()) history.goForward();
  });
  window.once("ready-to-show", () => window.show());
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = null;
  });
  return window;
}

function showStartupFailure(error) {
  const details = startupFailureDetails({
    error,
    backendOutput: backendOutput.text(),
    exitCode: backendExitCode,
    logPath: launcherLogPath(),
    packaged: app.isPackaged,
  });
  logLauncher(`startup failed: ${details.reason}`);
  // The backend's exit and the health-check timeout can both report the same
  // failure; the first one carries the useful detail, so keep it on screen.
  if (failureShown) return;
  failureShown = true;
  if (mainWindow && !mainWindow.isDestroyed()) {
    void mainWindow.loadFile(path.join(__dirname, "../static/error.html"), {
      query: {
        reason: details.reason,
        output: details.output,
        log: details.logPath,
        packaged: details.packaged ? "1" : "0",
      },
    });
  }
}

function stopBackend() {
  if (!backendProcess) return;
  backendProcess.kill("SIGTERM");
  backendProcess = null;
}

function ownerWindow() {
  return mainWindow && !mainWindow.isDestroyed() ? mainWindow : undefined;
}

function buildLabel() {
  const commit = packageJson.config && packageJson.config.buildCommit;
  const version = displayVersion(app.getVersion());
  return commit ? `${version} (${String(commit).slice(0, 7)})` : version;
}

async function fetchLatestRelease() {
  const response = await fetch(RELEASES_API_URL, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": `Axcess/${app.getVersion()}`,
    },
    signal: AbortSignal.timeout(UPDATE_FETCH_TIMEOUT_MS),
  });
  if (!response.ok) return null;
  return response.json();
}

// electron-updater downloads the NSIS installer named in the release's
// latest.yml and runs it silently into the folder Axcess is installed in;
// the user chooses when the restart that activates it happens. Loaded here,
// not at the top, because macOS never uses it.
async function offerWindowsUpdate(release) {
  const { response } = await dialog.showMessageBox(ownerWindow(), {
    type: "info",
    title: "Update available",
    message: `Axcess ${release.version} is available.`,
    detail:
      `You are running ${buildLabel()}. The update downloads in the background; ` +
      "Axcess only restarts when you choose to.",
    buttons: ["Update now", "Later"],
    defaultId: 0,
    cancelId: 1,
  });
  if (response !== 0) return;

  const { NsisUpdater } = require("electron-updater");
  const updater = new NsisUpdater({ provider: "generic", url: release.feedUrl });
  updater.once("update-downloaded", async () => {
    const { response: restart } = await dialog.showMessageBox(ownerWindow(), {
      type: "info",
      title: "Update ready",
      message: `Axcess ${release.version} is ready.`,
      detail:
        "Finish or stop any running scan first. Restart now to switch to the " +
        "new version, or it takes effect the next time Axcess starts.",
      buttons: ["Restart now", "Later"],
      defaultId: 0,
      cancelId: 1,
    });
    // Silent, and start Axcess again once the new version is in place.
    if (restart === 0) updater.quitAndInstall(true, true);
  });
  updater.once("error", (error) => {
    void dialog.showMessageBox(ownerWindow(), {
      type: "warning",
      title: "Update failed",
      message: "Axcess could not install the update.",
      detail: `${error.message}\n\nYou can download it from ${release.pageUrl} instead.`,
      buttons: ["OK"],
    });
  });
  // The check downloads the update as soon as it finds it (autoDownload).
  // A failure also reaches the "error" handler above, which tells the user.
  updater.checkForUpdates().catch(() => {});
}

// Squirrel.Mac refuses to update an app that is not Developer ID signed, and
// the preview build is ad-hoc signed, so macOS gets the disk image instead.
async function offerMacDownload(release) {
  const { response } = await dialog.showMessageBox(ownerWindow(), {
    type: "info",
    title: "Update available",
    message: `Axcess ${release.version} is available.`,
    detail:
      `You are running ${buildLabel()}. To install it: click Download and wait ` +
      "for the download to finish, quit Axcess, double-click the downloaded " +
      "file, drag Axcess to Applications, choose Replace, and re-run Axcess.\n\n" +
      "Until Axcess is officially launched, macOS may prevent you from running " +
      "it. To get past this, follow the steps at " +
      "https://lsa-mis.github.io/axcess/get-started/#first-launch",
    buttons: ["Download", "Later"],
    defaultId: 0,
    cancelId: 1,
  });
  if (response === 0 && isReleaseAssetUrl(release.dmgUrl)) {
    void shell.openExternal(release.dmgUrl);
  }
}

// A copy from the zip cannot update itself: electron-updater's installer
// would put a second Axcess somewhere else. The dialog opens the new zip
// and says how to move to it; in portable mode that means carrying the
// data folder over, or the new copy starts with no reports.
async function offerZipDownload(release) {
  const folder = path.dirname(process.execPath);
  const steps = portableData
    ? `To update: choose Download and wait for it to finish. Quit Axcess. ` +
      `Unzip the new version into a new folder. Then move the "${PORTABLE_DATA_FOLDER}" ` +
      `folder from this copy (${folder}) into the new folder, replacing the one there, ` +
      "so your reports come with you. Open Axcess.exe in the new folder."
    : "To update: choose Download and wait for it to finish. Quit Axcess. " +
      "Unzip the new version into a new folder and open Axcess.exe there. " +
      "Your reports are in your user folder, so the new copy finds them.";
  const { response } = await dialog.showMessageBox(ownerWindow(), {
    type: "info",
    title: "Update available",
    message: `Axcess ${release.version} is available.`,
    detail: `You are running ${buildLabel()}. ${steps}`,
    buttons: ["Download", "Later"],
    defaultId: 0,
    cancelId: 1,
  });
  if (response === 0 && isReleaseAssetUrl(release.zipUrl)) {
    void shell.openExternal(release.zipUrl);
  }
}

// An AppImage is one file; the new version replaces it. Browsers save
// downloads without permission to run, hence the step that allows it. The
// reports are in ~/.config/Axcess, so the new file finds them.
async function offerAppImageDownload(release) {
  const current = process.env.APPIMAGE ? ` (${process.env.APPIMAGE})` : "";
  const { response } = await dialog.showMessageBox(ownerWindow(), {
    type: "info",
    title: "Update available",
    message: `Axcess ${release.version} is available.`,
    detail:
      `You are running ${buildLabel()}. To update: choose Download and wait for it to ` +
      `finish. Quit Axcess. Put the new file where the old one is${current} and delete ` +
      "the old one. Allow the new file to run: in your file manager, open its " +
      "Properties and turn on \"Allow executing file as program\", or run " +
      "chmod +x on it. Then open it. Your reports stay where they are.",
    buttons: ["Download", "Later"],
    defaultId: 0,
    cancelId: 1,
  });
  if (response === 0 && isReleaseAssetUrl(release.appImageUrl)) {
    void shell.openExternal(release.appImageUrl);
  }
}

// Best-effort and silent: offline, rate-limited, or malformed responses just
// mean no prompt this launch. Runs after the workbench is showing so it never
// delays startup.
async function checkForUpdates() {
  if (!app.isPackaged || process.env.AXCESS_DISABLE_UPDATE_CHECK === "1" || updateOffered) return;
  let release = null;
  try {
    release = describeRelease(await fetchLatestRelease(), {
      platform: process.platform,
      arch: process.arch,
    });
  } catch {
    return;
  }
  if (!isNewerRelease(release, app.getVersion())) return;
  updateOffered = true;
  if (process.platform === "win32") {
    const method = windowsUpdateMethod({ execPath: process.execPath, exists: fs.existsSync });
    if (method === "installer" && release.feedUrl) await offerWindowsUpdate(release);
    else if (method === "download" && release.zipUrl) await offerZipDownload(release);
  } else if (process.platform === "darwin" && release.dmgUrl) {
    await offerMacDownload(release);
  } else if (process.platform === "linux" && release.appImageUrl) {
    await offerAppImageDownload(release);
  }
}

// The first launch: no database yet, so the backend creates it and brings it
// to the current schema, and the system checks the new app (Gatekeeper on
// macOS, Defender on Windows). All of that makes the wait longer, and the
// loading screen says so (static/loading.html, #first-launch). Checked once,
// before the backend starts; a later window in the same run is not a first.
let firstLaunch = null;
function isFirstLaunch() {
  if (firstLaunch === null) {
    firstLaunch = !fs.existsSync(path.join(app.getPath("userData"), "data", "audit.db"));
  }
  return firstLaunch;
}

async function launch() {
  failureShown = false;
  mainWindow = createWindow();
  // When the backend is already running (Dock click after closing the window),
  // /health answers before loading.html finishes. Navigating to the workbench
  // then aborts that load, and Electron rejects the *new* loadURL with the old
  // page's ERR_ABORTED (-3). Let the loading page settle first.
  const loadingShown = mainWindow
    .loadFile(path.join(__dirname, "../static/loading.html"), isFirstLaunch() ? { hash: "first-launch" } : {})
    .catch(() => {});
  if (!backendProcess || !backendOrigin) {
    const port = await findOpenPort();
    backendOrigin = `http://127.0.0.1:${port}`;
    startBackend(port);
  }
  await waitForBackend(backendOrigin);
  firstLaunch = false;
  await loadingShown;
  if (mainWindow && !mainWindow.isDestroyed()) {
    await mainWindow.loadURL(`${backendOrigin}/app/`);
  }
  void checkForUpdates().catch(() => {});
}

if (portableDataUnwritable) {
  app.whenReady().then(() => {
    dialog.showErrorBox(
      "Axcess cannot save to its data folder",
      `Axcess keeps everything in "${portableData}", and it cannot write there ` +
        `(${portableDataUnwritable.message}).\n\nMove the Axcess folder to a place you can ` +
        "change, such as Documents or Desktop, and open it again.",
    );
    app.quit();
  });
} else if (!app.requestSingleInstanceLock()) {
  logLauncher("another Axcess is already running; handing this launch to it");
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    // Electron's About panel would show the packaged semver (0.61.0); show
    // the version people see everywhere else, with the build's commit.
    app.setAboutPanelOptions({ applicationName: "Axcess", applicationVersion: buildLabel() });
    // Packaged macOS apps use the bundle's ICNS; brand the development Dock too.
    if (process.platform === "darwin" && !app.isPackaged) app.dock.setIcon(appIcon);
    return launch().catch((error) => showStartupFailure(error));
  });
  app.on("activate", () => {
    if (!mainWindow) void launch().catch((error) => showStartupFailure(error));
  });
  app.on("before-quit", () => {
    quitting = true;
    stopBackend();
  });
  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
  process.on("uncaughtException", (error) => {
    dialog.showErrorBox("Axcess could not continue", error.message);
    app.quit();
  });
}
