# Axcess desktop application

Axcess has an Electron desktop shell on the `feature/electron-desktop`
branch. The desktop application does not duplicate the product UI. It starts
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

Typical data locations are:

| Operating system | Data root |
| --- | --- |
| macOS | `~/Library/Application Support/Axcess/data/` |
| Windows | `%APPDATA%/Axcess/data/` |
| Linux | `~/.config/Axcess/data/` |

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

## Build a local installer

The release build has four layers:

1. Build the React application.
2. Install the pinned Alfa runner.
3. Bundle the Python backend with PyInstaller.
4. Bundle the matching Playwright Chromium and create an installer with
   Electron Forge.

Run:

```bash
make desktop-package
```

Outputs are written beneath `desktop/out/`. Builds are operating-system and
CPU specific, so create macOS builds on macOS, Windows builds on Windows, and
Linux builds on Linux.

The macOS disk image is created directly with the operating system's
`hdiutil`; Axcess does not use the currently vulnerable third-party ICNS image
parser in the Electron Forge DMG maker.

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

The branch produces local, unsigned installers. Before institutional rollout:

- create final `.icns`, `.ico`, and Linux icon assets;
- configure Apple Developer ID signing and notarization;
- configure Windows Authenticode signing;
- decide how Tesseract language data will be bundled for OCR on each platform;
- add a signed update channel or document managed-software deployment;
- run U-M security and privacy review on the packaged binaries;
- test installation, upgrade, rollback, database retention, and uninstall on
  each supported operating-system version.

Do not distribute unsigned builds as a production U-M application.

For a release build on macOS, set `AXCESS_MAC_SIGN_IDENTITY` to the exact
Developer ID Application identity available in the build keychain. Without
that value, the build is intentionally ad-hoc signed for local testing and
does not enable hardened runtime; it cannot be treated as a distributable
institutional release.
