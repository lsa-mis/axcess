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

The release build has five layers:

1. Build the React application.
2. Install the pinned Alfa runner.
3. Bundle the Python backend with PyInstaller.
4. Bundle the matching Playwright Chromium and a relocatable Tesseract OCR
   runtime with English language data.
5. Create an installer with Electron Forge, then launch every bundled runtime
   from inside the finished application as a release gate.

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

The build produces local, unsigned installers. Before institutional rollout:

- create final `.icns`, `.ico`, and Linux icon assets;
- configure Apple Developer ID signing and notarization;
- configure Windows Authenticode signing;
- bundle and verify an equivalent OCR runtime before enabling a Linux release
  job;
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
