const { app, BrowserWindow, dialog, session, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { desktopEnvironment, isAxcessUrl, isSafeExternalUrl } = require("./runtime.cjs");

const STARTUP_TIMEOUT_MS = 60_000;
const HEALTH_POLL_MS = 200;
const repoRoot = path.resolve(__dirname, "../..");
const appIcon = path.join(__dirname, "../assets/axcess.png");
let mainWindow = null;
let backendProcess = null;
let backendOrigin = null;
let quitting = false;

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
        "Content-Security-Policy": [
          "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; " +
            "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'self'; " +
            "frame-ancestors 'none'",
        ],
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
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
      spellcheck: true,
    },
  });
  configureWindowSecurity(window);
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
