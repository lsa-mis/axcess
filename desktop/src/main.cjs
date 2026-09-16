const { app, autoUpdater, BrowserWindow, dialog, session, shell } = require("electron");

// Squirrel.Windows relaunches the app with --squirrel-install / -updated /
// -obsolete flags while it installs or updates; those runs must exit at once
// instead of opening a window over the installer.
if (require("electron-squirrel-startup")) app.quit();

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const {
  contentSecurityPolicy,
  desktopEnvironment,
  isAxcessUrl,
  isSafeExternalUrl,
  nextZoomLevel,
  zoomActionFor,
} = require("./runtime.cjs");
const {
  RELEASES_API_URL,
  describeRelease,
  isNewerRelease,
  isReleaseAssetUrl,
} = require("./updates.cjs");
const packageJson = require("../package.json");

const STARTUP_TIMEOUT_MS = 60_000;
const HEALTH_POLL_MS = 200;
const UPDATE_FETCH_TIMEOUT_MS = 10_000;
const repoRoot = path.resolve(__dirname, "../..");
const appIcon = path.join(__dirname, "../assets/axcess.png");
let mainWindow = null;
let backendProcess = null;
let backendOrigin = null;
let quitting = false;
let updateOffered = false;

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
    throw new Error("The packaged Axcess backend is missing.");
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
  backendProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env,
    shell: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  backendProcess.stdout.on("data", (chunk) => {
    if (!app.isPackaged) process.stdout.write(`[Axcess backend] ${chunk}`);
  });
  backendProcess.stderr.on("data", (chunk) => {
    if (!app.isPackaged) process.stderr.write(`[Axcess backend] ${chunk}`);
  });
  backendProcess.once("exit", (code) => {
    backendProcess = null;
    if (!quitting && code !== 0) showStartupFailure();
  });
  backendProcess.once("error", () => showStartupFailure());
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
    if (await healthCheck(origin)) return;
    await new Promise((resolve) => setTimeout(resolve, HEALTH_POLL_MS));
  }
  throw new Error("Axcess took too long to start.");
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
  window.once("ready-to-show", () => window.show());
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = null;
  });
  void window.loadFile(path.join(__dirname, "../static/loading.html"));
  return window;
}

function showStartupFailure() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    void mainWindow.loadFile(path.join(__dirname, "../static/error.html"));
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
  return commit ? `${app.getVersion()} (${String(commit).slice(0, 7)})` : app.getVersion();
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

// Squirrel.Windows installs the new version in place; the user chooses when
// the restart that activates it happens.
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

  autoUpdater.once("update-downloaded", async () => {
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
    if (restart === 0) autoUpdater.quitAndInstall();
  });
  autoUpdater.once("error", (error) => {
    void dialog.showMessageBox(ownerWindow(), {
      type: "warning",
      title: "Update failed",
      message: "Axcess could not install the update.",
      detail: `${error.message}\n\nYou can download it from ${release.pageUrl} instead.`,
      buttons: ["OK"],
    });
  });
  autoUpdater.setFeedURL({ url: release.feedUrl });
  autoUpdater.checkForUpdates();
}

// Squirrel.Mac refuses to update an app that is not Developer ID signed, and
// the preview build is ad-hoc signed, so macOS gets the disk image instead.
async function offerMacDownload(release) {
  const { response } = await dialog.showMessageBox(ownerWindow(), {
    type: "info",
    title: "Update available",
    message: `Axcess ${release.version} is available.`,
    detail:
      `You are running ${buildLabel()}. Download opens the new disk image in ` +
      "your browser. Quit Axcess, open the image, and drag Axcess to " +
      "Applications to replace this copy. Until builds are notarized, macOS " +
      "may ask you to right-click Axcess and choose Open the first time.",
    buttons: ["Download", "Later"],
    defaultId: 0,
    cancelId: 1,
  });
  if (response === 0 && isReleaseAssetUrl(release.dmgUrl)) {
    void shell.openExternal(release.dmgUrl);
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
  if (process.platform === "win32" && release.feedUrl) {
    await offerWindowsUpdate(release);
  } else if (process.platform === "darwin" && release.dmgUrl) {
    await offerMacDownload(release);
  }
}

async function launch() {
  mainWindow = createWindow();
  if (!backendProcess || !backendOrigin) {
    const port = await findOpenPort();
    backendOrigin = `http://127.0.0.1:${port}`;
    startBackend(port);
  }
  await waitForBackend(backendOrigin);
  if (mainWindow && !mainWindow.isDestroyed()) {
    await mainWindow.loadURL(`${backendOrigin}/app/`);
  }
  void checkForUpdates().catch(() => {});
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    // Packaged macOS apps use the bundle's ICNS; brand the development Dock too.
    if (process.platform === "darwin" && !app.isPackaged) app.dock.setIcon(appIcon);
    return launch().catch(() => showStartupFailure());
  });
  app.on("activate", () => {
    if (!mainWindow) void launch().catch(() => showStartupFailure());
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
