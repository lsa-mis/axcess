# Axcess desktop application

Axcess has an Electron desktop shell. The desktop application does not
duplicate the product UI. It starts
the existing FastAPI service on an unused loopback port and displays the same
React workbench in a sandboxed Electron window.

## User experience

- Opening Axcess prepares the local database and opens the workbench.
- Scan evidence is stored in the operating system's application-data folder,
  never inside the installed application.
- Closing Axcess stops its private backend process.
- A second launch focuses the existing window instead of starting a second
  database writer.
- Public and login/2FA scanning retain the same UI and browser behavior as the
  local web version.
- Alfa can use Electron's bundled Node runtime. Users do not need a separate
  Node installation in a packaged build.
- The installer includes the matching Playwright Chromium, Siteimprove Alfa
  packages, Tesseract executable, and English OCR language data. Users do not
  need Python, Node.js, Chromium, or Tesseract installed separately.
- Ollama and its optional local language/vision models are not silently
  installed or downloaded. Model-assisted checks remain optional and clearly
  report when a separately configured loopback Ollama service is unavailable.

Typical data locations are:

| Operating system | Data root |
| --- | --- |
| macOS | `~/Library/Application Support/Axcess/data/` |
| Windows | `%APPDATA%/Axcess/data/` |
| Windows, portable zip | `Axcess data/data/`, beside `Axcess.exe` |
| Linux | `~/.config/Axcess/data/` |

### The Linux AppImage

`Axcess-<version>-x86_64.AppImage` is the whole app in one file. The release
builds it on Ubuntu 22.04 (`build-linux` in `desktop-build.yml`), so it runs
on distributions with glibc 2.35 or newer: Ubuntu 22.04, Debian 12, Fedora
36 and later. Forge packages the app; `scripts/make-linux-appimage.cjs` has
electron-builder wrap it, and `verify-packaged.cjs` then runs the bundled
backend's checks. Tesseract is bundled by `scripts/bundle-tesseract-linux.sh`:
the real executable, every library it needs except glibc's, and English
data, behind a `bin/tesseract` wrapper that points it at its own libraries.

It uses electron-builder's static AppImage runtime (`toolsets.appimage` in
`electron-builder.config.cjs`), which needs no libfuse2. Its launcher keeps
Chromium's sandbox on, and turns it off only when user namespaces are
unavailable (`unshare -Ur true` fails), as on Ubuntu 23.10 and later, where
AppArmor restricts them; otherwise the app would not start there. That was
a deliberate choice: there, a saved copy of a scanned page opened in the
Page inspector is not isolated by the sandbox, and the Get started page
says so. A DEB package could install an AppArmor profile and keep the
sandbox on Ubuntu as well.

Data is in `~/.config/Axcess`, as for any Linux build. The AppImage
runtime's own `--appimage-portable-config` puts it in a folder beside the
file instead (`Axcess-<version>-x86_64.AppImage.config`); Axcess needs no
code for that. Updates are offered as a download of the new AppImage
(`offerAppImageDownload` in `main.cjs`).

### The portable zip (Windows)

`Axcess-<version>-Windows-x64-portable.zip` is the same app without an
installer. It ships with a folder named `Axcess data` beside `Axcess.exe`,
and while that folder is there Axcess runs in portable mode
(`portableDataDir` in `desktop/src/runtime.cjs`): reports, stored images,
settings, logs, the browser profile, crash reports and temporary files
(`TEMP` and `TMP`, inherited by the backend, Playwright and Chromium) all
go into it, not into `%APPDATA%`. Moving the folder that holds both moves
Axcess with its reports. Deleting `Axcess data` makes the copy an ordinary
one that uses `%APPDATA%`.

What it cannot promise, and what the folder's `About this folder.txt`
tells people:

- Windows itself still records a little about any program it runs, such
  as recent apps and prefetch data.
- The reports database uses SQLite's WAL mode, which does not work on a
  network drive. A USB drive works, but unplugging it while Axcess is open
  can damage the database.
- Reports can hold screenshots of scanned pages, including pages behind a
  sign-in, so the folder needs the same care as those pages.

If Axcess cannot write to the folder (unzipped somewhere read-only), it
says so and stops, rather than writing to `%APPDATA%` after all. A zip copy
cannot update itself: its update dialog opens the new zip and says how to
move the `Axcess data` folder into it (`offerZipDownload` in `main.cjs`).
Only a copy with Setup's uninstaller beside it updates in place
(`windowsUpdateMethod`). A portable copy and an installed one can run at
the same time, each with its own reports.

## Development

Install the desktop dependencies once:

```bash
make desktop-setup
```

Start the desktop shell against the source checkout:

```bash
make desktop-run
```

Electron chooses an available loopback port. It does not use or expose port
8765, and it does not enable the LAN-hosting access-token mode.

Only one Axcess may run per user data folder. If an installed copy is already
open, `make desktop-run` (or a second installed copy) exits at once and brings
the running window forward instead of starting.

### "Axcess could not start"

The window shows this page when the local service exits, cannot be spawned,
or never answers `/health` within 60 seconds. The page prints the launcher's
reason and the service's last lines of output. The full record is in the
launcher log, next to the service's own log:

| Platform | Log file |
| --- | --- |
| macOS | `~/Library/Application Support/Axcess/data/logs/launcher.log` |
| Windows | `%APPDATA%\Axcess\data\logs\launcher.log` |
| Linux | `~/.config/Axcess/data/logs/launcher.log` |

Every launch appends the exact backend command, the version, its output, and
its exit code, so the file also shows which build failed. A development
checkout usually fails because dependencies are missing; run
`make desktop-setup` and retry.

## Build a local installer

The release build has five layers:

1. Build the React application.
2. Install the pinned Alfa runner.
3. Bundle the Python backend with PyInstaller.
4. Bundle the matching Playwright Chromium and a relocatable Tesseract OCR
   runtime with English language data.
5. Package the app with Electron Forge and create the installer, then launch
   every bundled runtime from inside the finished application as a release
   gate. macOS gets a DMG from Forge. Windows gets an NSIS installer from
   electron-builder, which wraps Forge's packaged folder without changing it
   (`npm run make:windows`; see `desktop/electron-builder.config.cjs`).

The Windows installer is a standard setup wizard. It asks whether to install
only for the current user (the default, no administrator needed) or for
everyone on the computer, then shows the install folder and lets people
change it. A per-user install goes to
`%LOCALAPPDATA%\Programs\Axcess` by default. Uninstalling keeps scans,
because they live in `%APPDATA%\Axcess\data`. For managed deployment, the
installer runs silently with `/S`; add `/allusers` to install for every
account or `/D=<folder>` (last on the command line) to choose the folder.

Run:

```bash
make desktop-package
```

Outputs are written beneath `desktop/out/`. Builds are operating-system and
CPU specific, so create macOS builds on macOS, Windows builds on Windows, and
Linux builds on Linux.

The macOS disk image is created directly with the operating system's
`hdiutil`; Axcess does not use the currently vulnerable third-party ICNS image
parser in the Electron Forge DMG maker. The build copies the application with
macOS `ditto` so Electron framework symlinks remain relative, then mounts the
finished DMG and rejects it if any app link is absolute/broken or its nested
code-signature integrity fails.

## Desktop branding

Desktop builds use the existing navy-and-maize **Ax** identity, adapted as a
rounded, padded app icon with outlined letters (no installed font required).
The canonical desktop artwork is `desktop/assets/axcess.svg`.

Committed native assets cover the macOS application/Dock (`axcess.icns`),
Windows executable and Setup installer (`axcess.ico`), and Linux window,
AppImage and DEB/RPM launcher (`axcess.png`). The same mark appears on startup and error
screens, and in the macOS development Dock. Packaging verifies all assets
are present; ordinary builds do not require an icon-generation toolchain.

After editing the SVG, regenerate the assets from the repository root using
the project's installed Playwright Chromium and Pillow:

```bash
uv run python desktop/scripts/generate-icons.py
```

Review the generated PNG and run `make desktop-test` before committing all
four assets together. Regeneration runs locally without fetching any images
or fonts.

## Security boundary

The main window has Node integration disabled, context isolation and the
Chromium sandbox enabled, browser permission requests denied, and navigation
restricted to the exact random loopback origin. New-window links may open only
ordinary HTTP or HTTPS URLs in the system browser; file, shell, mail, and
custom protocols are rejected.

The Electron `RunAsNode` fuse remains enabled solely so the Python sidecar can
invoke the packaged Siteimprove Alfa runner using Electron's embedded Node
runtime. Node APIs are never exposed to the React renderer. Other high-risk
Node flags are fused off, and the packaged application is required to load
from its integrity-checked ASAR archive.

## Release work still required

Without signing credentials, the build produces preview installers: macOS
builds are ad-hoc signed (not Developer ID signed or notarized), and Windows
builds are unsigned. Before institutional rollout:

- configure Apple Developer ID signing and notarization;
- configure Windows Authenticode signing;
- sign the update channel so macOS can install updates in place (see
  below), or document managed-software deployment;
- run U-M security and privacy review on the packaged binaries;
- test installation, upgrade, rollback, database retention, and uninstall on
  each supported operating-system version.

Do not distribute these preview builds as a production U-M application.

## Update channel

`desktop-build.yml` runs on every push to `main` that changes `desktop/**`,
`src/**`, `pyproject.toml`, `uv.lock`, or the workflow file itself, and it can
also be started by hand. Each run takes the next two-part version after the
last release: `0.60`, then `0.61`, and on to `0.69`, then `0.70` (the git
commit is recorded in the package's `config.buildCommit`). On `main`, it then
publishes the macOS DMG and zip, the Windows `-Setup.exe` with its
`.blockmap`, and the Windows update feed `latest.yml` as GitHub Release
`desktop-v0.61`. The package itself carries the version as semver (`0.61.0`),
which npm and electron-updater need.

Each release also carries version-less copies,
`Axcess-macOS-AppleSilicon.dmg` and `Axcess-Windows-x64-Setup.exe`, so the
public site's download buttons can use the permanent links
`https://github.com/lsa-mis/axcess/releases/latest/download/<name>`. The ten
newest preview releases are kept; `https://github.com/lsa-mis/axcess/releases/latest`
always points at the most recent one and needs no GitHub sign-in. Workflow
artifacts are not a public download channel: GitHub requires a signed-in user
to fetch them and deletes them after 14 days.

Each time a packaged Axcess launches, it asks the GitHub API for the latest
release after the workbench has loaded, and compares it with its own version.
On macOS it also checks when the app is reopened with no window open. Once it
has offered an update, it does not check again until the app restarts.

Nothing happens offline, on a rate-limited response, or when the build is
current. When a newer build exists:

- **Windows** offers *Update now*. electron-updater reads `latest.yml` from
  the release's asset directory, downloads the installer it names (only the
  changed blocks when it still has the installed version's block map), and
  checks its SHA-512. *Restart now* runs the installer silently into the same
  folder and starts Axcess again; *Later* installs it when Axcess quits.
- **macOS** offers *Download*, which opens the new DMG in the browser. Apple's
  Squirrel.Mac updater refuses to update an app that is not Developer ID
  signed, so in-place installation on macOS waits for signing and
  notarization; once those are configured the same release assets serve it.

The check is skipped for unpackaged development runs and whenever
`AXCESS_DISABLE_UPDATE_CHECK=1` is set, which local packaged builds (always
version `0.60`) may want. Only HTTPS asset downloads under this repository's
releases are ever handed to the system browser.

For a release build on macOS, set `AXCESS_MAC_SIGN_IDENTITY` to the exact
Developer ID Application identity available in the build keychain. Without
that value, the build is intentionally ad-hoc signed for local testing and
does not enable hardened runtime; it cannot be treated as a distributable
institutional release.

For a warning-free direct download, configure notarization as well. Axcess
accepts any one of Electron Forge's supported credential strategies:

```bash
# Apple ID app-specific password
AXCESS_MAC_SIGN_IDENTITY="Developer ID Application: Organization (TEAMID)" \
APPLE_ID="developer@example.edu" \
APPLE_APP_SPECIFIC_PASSWORD="..." \
APPLE_TEAM_ID="TEAMID" \
AXCESS_REQUIRE_NOTARIZATION=1 \
make desktop-package

# Or a keychain profile created with `xcrun notarytool store-credentials`
AXCESS_MAC_SIGN_IDENTITY="Developer ID Application: Organization (TEAMID)" \
APPLE_NOTARY_KEYCHAIN_PROFILE="axcess-notary" \
AXCESS_REQUIRE_NOTARIZATION=1 \
make desktop-package
```

The build fails on partial credentials, on an Apple Development identity, or
when notarization is required but unavailable. Never commit Apple credentials
to this repository.
