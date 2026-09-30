# Releases, updates, and the public site

This page is for anyone on the team who ships the Axcess desktop app or updates
the public site. It covers what the workflows do today, what they do not
check, and a checklist for shipping a release. For how the desktop shell
itself works, see the [desktop app guide](../desktop-app.md). For setup and
the test gates, see [CONTRIBUTING.md](../../CONTRIBUTING.md).

## How a desktop release ships today

![Diagram of a desktop release. A merge to main that changes app code starts the desktop build workflow, which builds the macOS, Windows and Linux apps in parallel, stamped with the next version, such as 0.2.1 after 0.2.0, and publishes a GitHub release marked latest with one file per platform. Installed apps check for it on launch: Windows can update in place, and macOS and Linux open the new file to download. No tests gate publishing, and builds are not notarized or signed; the public site ships separately through pages.yml.](../images/diagrams/release-flow.png)

In short: a merge to `main` that changes app code builds both installers and
publishes them as the latest GitHub release, and installed copies offer that
release the next time they start.

One workflow does all of this: `.github/workflows/desktop-build.yml`, shown as
"Desktop application build" in the Actions tab. Nobody tags a commit or
uploads an installer by hand.

### What starts a build

The workflow runs in three cases:

- a push to `main` that changes at least one of
  `.github/workflows/desktop-build.yml`, `desktop/**`, `src/**`,
  `pyproject.toml`, or `uv.lock`;
- a pull request that changes `.github/workflows/desktop-build.yml`,
  `desktop/**`, `pyproject.toml`, or `uv.lock`. It builds both installers as
  workflow artifacts and never publishes, so a packaging break shows before
  the merge. Changes under `src/` alone do not trigger it, since each run
  costs macOS and Windows minutes;
- a manual run (`workflow_dispatch`) from the Actions tab.

There is no tag trigger. A merge that only changes docs, the site, or tests
does not build a release. If you want a release anyway, run the workflow
manually on `main`.

Only runs on `main` publish a release. A manual run on any other branch still
builds both installers as workflow artifacts but skips the publish job, which
is a handy way to try a branch's installers before merging.

A new run on the same branch cancels a run that is still in progress
(`cancel-in-progress: true`). If two app-code merges land close together, the
second one can cancel the first one's release.

### The two build jobs

| Job | Runner | Workflow artifact (kept 14 days) |
| --- | --- | --- |
| `build-macos` ("Apple Silicon macOS desktop artifact") | `macos-15` | `axcess-macos-apple-silicon` |
| `build-windows` ("Windows x64 desktop artifact") | `windows-2022` | `axcess-windows-x64` |

Both jobs use Python 3.13 and Node 22 and run the same steps in this order:

1. Build the React review app in `src/audit/web/frontend`.
2. Install the pinned [Siteimprove Alfa](../glossary.md#siteimprove-alfa)
   runner in `src/audit/alfa_runner`, then the desktop dependencies.
3. Stamp the version (see [Version numbers and tags](#version-numbers-and-tags)).
4. Install the `desktop` Python dependency group with `uv sync --group desktop`.
5. Bundle Playwright's Chromium into `desktop/playwright-browsers`.
6. Bundle Tesseract [OCR](../glossary.md#ocr) into `desktop/ocr-runtime`.
   macOS installs it with Homebrew and runs
   `desktop/scripts/bundle-tesseract-macos.sh`. Windows installs it with
   Chocolatey and runs `desktop/scripts/bundle-tesseract-windows.ps1`.
7. Freeze the Python backend with PyInstaller (`desktop/backend.spec`) into
   `desktop/backend-dist`.
8. Package with Electron Forge. macOS runs `npm run make` with up to three
   attempts. Windows runs `npm run make:windows`: Forge packages the app,
   `scripts/make-windows-installer.cjs` has electron-builder wrap that folder
   in the NSIS installer and write `latest.yml`, and
   `scripts/verify-packaged.cjs` checks the packaged app.
9. On Windows, check the installer's accessibility:
   `desktop/scripts/check-installer-accessibility.ps1` installs Axcess on
   the runner, runs Microsoft's Axe.Windows (pinned by version and SHA-256)
   on each setup and uninstall screen through UI Automation, and removes
   it. An error fails the build, so that installer is not published. The
   `.a11ytest` files are uploaded as `axcess-windows-installer-accessibility`
   and open in Accessibility Insights for Windows. Like axe-core, it finds
   only what a tool can detect; the smoke test's screen-reader check stays.
10. Upload everything under `desktop/out/make/` as the workflow artifact.

The finished app carries the frozen backend (with the built review app, the
bundled [axe-core](../glossary.md#axe-core) script, and the Alfa runner's
packages), Chromium, and Tesseract with English language data. See the
[build layers in the desktop app guide](../desktop-app.md#build-a-local-installer)
for more.

### Checks inside the build

Apart from each build step having to succeed, these are the only automatic
checks between a merge and a published release:

- **Resource check.** `desktop/scripts/verify-resources.cjs` runs before
  packaging. It fails if an app icon, the frozen backend, the built review
  app, the axe-core script, the Alfa packages, the public-suffix snapshot,
  Chromium, or (on macOS and Windows) Tesseract and its English data is
  missing.
- **Disk image check (macOS).** `desktop/scripts/make-macos-dmg.cjs` builds
  the disk image with `hdiutil`. It rejects absolute or broken symlinks and
  runs `codesign --verify --deep --strict` on the app before building the
  image and again on the mounted image.
- **Packaged runtime check.** `desktop/scripts/verify-packaged.cjs` runs after
  packaging. It starts the packaged backend with `--verify-runtime` in a
  throwaway data folder. It fails unless `alfa`, `axe_core`, `chromium`,
  `frontend`, `python_backend`, `reports`, and `url_scope` report `available`
  and OCR reports Tesseract.
- **Required assets.** The publish job stops before creating a release if a
  required installer is missing (see [The publish job](#the-publish-job)).

On macOS, `npm run make` runs the resource and runtime checks through the
`premake` and `postmake` scripts in `desktop/package.json`.

### Version numbers and tags

- Versions are semver, three parts: `0.2.0`, then `0.2.1`, `0.2.2`, and so
  on. The first two parts are the release line, which the team chooses:
  `config.releaseLine` in `desktop/package.json`, now `0.2`. Every release
  published from `main` counts up the last part. Moving to `0.3.0` or `1.0.0`
  is a deliberate change of that one setting (and of `version` beside it),
  never the side effect of a merge.
- The workflow's first job, **Choose the release version**, reads the
  `desktop-v*` tags and runs `desktop/scripts/next-version.cjs`, which
  `nextReleaseVersion` in `desktop/src/updates.cjs` backs: one step after the
  highest `desktop-v0.2.N` tag, or `0.2.0` when the line has none. Tags of
  other lines and of the earlier schemes do not count. Its unit tests pin the
  steps.
- Each build stamps `desktop/package.json` with that version and puts the
  commit SHA in `config.buildCommit`. `desktop/scripts/stamp-version.cjs` does
  the stamp rather than `npm version`, which refuses to set the version a
  package already has.
- Everything a person sees shows the version as it is: the release tag
  `desktop-v0.2.3`, the release title `Axcess 0.2.3 (preview)`, the file
  names, the installer's footer, and the app's own label, `0.2.3 (abc1234)`,
  in its update dialogs and the launcher log (`displayVersion`).
- In git, `desktop/package.json` stays at the line's first version, `0.2.0`,
  so every local build shows `0.2.0`. `pyproject.toml`, `audit.__version__`
  and the review app's `package.json` say `0.2.0` too.
- Two schemes came before: `0.1.<run number>` (up to `desktop-v0.1.34`), then
  `0.60`, `0.61` ... (up to `desktop-v0.63`), which added 0.01 per merge, a
  build counter that looked like a version and would have reached `1.00` by
  itself. Installed copies of `0.60` to `0.63` are not offered `0.2.x`,
  because `0.2.0` is the lower number; those previews were not widely
  released, and their users install once from the Get started page.

### The publish job

The `publish` job ("Publish preview release") runs only on `main`, and only
after both build jobs succeed. It uses the workflow's built-in token, so no
repository secrets are involved.

1. **Collect the installers.** It copies the files named by
   `releaseFileName` in `desktop/src/updates.cjs`, in plain words, from the
   artifacts: `Axcess-0.2.3-Mac-Apple-Silicon.dmg`,
   `Axcess-0.2.3-Windows-Installer.exe` with its `.blockmap`,
   `Axcess-0.2.3-Windows-Portable.zip`, `Axcess-0.2.3-Linux.AppImage` and
   `latest.yml`: one file per platform, and the two the Windows updater
   reads. It stops if any is missing, or if there are more than these six.
   There is no second name for any file. The site's download links open
   `https://github.com/lsa-mis/axcess/releases/latest`, and `site/assets/site.js`
   points each at its file in that release by the part of the name after the
   version (`data-release-file` in `site/build.py`). If you rename a kind of
   file, change `releaseFileName` and those attributes in the same pull
   request.
2. **Create a draft, upload, then publish.** If no release exists for tag
   `desktop-v0.2.3` yet, it creates one as a draft at the built commit. It
   uploads every file with `--clobber`, then publishes the release and marks
   it latest. Publishing last keeps `releases/latest` pointing at a complete
   set of files.
3. **Prune.** It keeps the 10 newest `desktop-v*` releases and deletes older
   ones along with their tags.

### Release notes

The notes come from the message of the commit the workflow built:

- The first line reads "Preview build of `main` at", then the short commit
  SHA and the commit's subject line.
- If the commit message has a body, it appears under a "What changed"
  heading, without `Co-Authored-By:` or `Signed-off-by:` lines.
- A link to the workflow run follows, then a fixed note: installed copies
  offer this build on their next launch, and the macOS build is an ad-hoc
  signed preview that needs right-click and Open on first launch.

For a pull request merge commit, the subject is GitHub's "Merge pull request"
line, so the body you write when merging is what readers see. There is no
other changelog.

## What does not gate a release

The `publish` job needs only the two build jobs
(`needs: [build-macos, build-windows]`). Nothing in `desktop-build.yml` waits
for:

- the CI workflow (`.github/workflows/ci.yml`), which also runs on every push
  to `main`, but on its own;
- detection evaluations (`.github/workflows/detection-evals.yml`), which run
  on pull requests and pushes that touch detection code, rules, or quality
  tests, and weekly;
- the integration suites, which run only on CI's daily schedule, on a
  manual CI run, or when a pull request has the `run-browser-tests` label.
  (The accessibility and Playwright UI suites run on every pull request and
  push to `main`, but the desktop build does not wait for them either.)

So a commit on `main` that fails CI still ships, as long as it touches the
build paths and both installers build. **Make sure CI is green before you
merge.** See the [quality gates in CONTRIBUTING.md](../../CONTRIBUTING.md#quality-gates).

## Signing and notarization

### Status today

| Platform | Today | What it means |
| --- | --- | --- |
| macOS | Ad-hoc signed (identity `-`), hardened runtime off, not notarized | People approve the app on first launch. The app cannot update itself in place, because Squirrel.Mac refuses apps that are not Developer ID signed. |
| Windows | Unsigned | People approve it on first launch. The app can update in place through electron-updater and the NSIS installer. |
| Linux | Unsigned AppImage | People allow the file to run (file Properties, or `chmod +x`). The app offers the new AppImage to download; it does not update in place. |

The workflow sets none of the signing variables below and holds no
certificate. The desktop app guide's
[release work list](../desktop-app.md#release-work-still-required) says not to
distribute these preview builds as a production U-M application.

### Settings for when credentials exist

`desktop/forge.config.cjs` reads these environment variables. Signing and
notarization apply to macOS builds only.

| Variable | Effect |
| --- | --- |
| `AXCESS_MAC_SIGN_IDENTITY` | The signing identity. Unset means ad-hoc (`-`). When set, it must start with `Developer ID Application:`, and identity validation and hardened runtime turn on. |
| `APPLE_NOTARY_KEYCHAIN_PROFILE` | Notarize with a stored `notarytool` keychain profile. Checked first. `APPLE_NOTARY_KEYCHAIN` can name the keychain. |
| `APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` | Notarize with an API key. Checked second. All three are needed. |
| `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` | Notarize with an Apple ID. Checked third. All three are needed. |
| `AXCESS_REQUIRE_NOTARIZATION` | Set to `1` to fail the build when no notarization credentials are configured. |

The config stops the build with an error when:

- some Apple ID or API key values are set, but no set is complete and no
  keychain profile is set;
- notarization credentials are set without `AXCESS_MAC_SIGN_IDENTITY`;
- `AXCESS_MAC_SIGN_IDENTITY` names anything other than a
  `Developer ID Application:` identity, such as an Apple Development
  certificate;
- `AXCESS_REQUIRE_NOTARIZATION=1` is set without credentials.

For Windows, `desktop/electron-builder.config.cjs` sets the installer icon,
file name, and wizard options. There are no Authenticode signing settings
yet. Example signing commands
are in the desktop app guide's
[update channel section](../desktop-app.md#update-channel). Never commit Apple
credentials to the repository.

## How installed apps update

Two files hold the update logic. `desktop/src/updates.cjs` has the pure
decision helpers, and `desktop/src/main.cjs` runs the check and shows the
dialogs. This is the GitHub check mentioned under
[local-first](../glossary.md#local-first).

### When the check runs

- Only in packaged builds, and never when `AXCESS_DISABLE_UPDATE_CHECK=1` is
  set.
- At the end of `launch()`, after the backend answers `/health` and the review
  app has loaded in the window. It does not hold up startup.
- `launch()` runs when the app starts. On macOS it runs again when someone
  clicks the Dock icon after closing the window.
- Once a check finds a newer release, the app stops checking until it
  restarts (the `updateOffered` flag). There is no timer.
- It fetches `https://api.github.com/repos/lsa-mis/axcess/releases/latest`
  with a 10 second timeout. It sets an `Accept` header and a `User-Agent` of
  `Axcess/<version>`, and sends no scan data.
- Offline, rate-limited, or malformed responses are ignored silently.

Because the check waits for the backend, a build whose backend cannot start
never checks for updates. People on such a build have to download a fixed
release from the site.

### Which releases count

- The check reads the release GitHub marks as latest.
- Drafts and prereleases are ignored. So are tags that are not a plain dotted
  version, optionally prefixed with `desktop-v` or `v`.
- The app offers a release only when its version is strictly newer, compared
  as numbers (`0.2.10` is newer than `0.2.9`, and `0.2.0` than `0.1.34`).

### What people see on Windows

1. An "Update available" dialog with **Update now** and **Later**.
2. After **Update now**, electron-updater reads the release's `latest.yml`
   and downloads the installer it names in the background, checking its
   SHA-512. The app only offers this when the release has a `latest.yml`
   file.
3. When the download finishes, an "Update ready" dialog offers
   **Restart now** and **Later**. **Restart now** runs the installer silently
   into the same folder and starts Axcess again. **Later** installs it
   silently when Axcess quits, so the update takes effect the next time
   Axcess starts, as the dialog says.
4. If the update fails, an "Update failed" dialog shows the error and points
   to the latest release on GitHub.

### What people see on macOS

1. An "Update available" dialog with **Download** and **Later**. It lists the
   install steps and links to the site's
   [first-launch steps](https://lsa-mis.github.io/axcess/get-started/#first-launch).
2. **Download** opens the disk image that matches the Mac's CPU architecture
   (`-Mac-Apple-Silicon.dmg`) in the default browser. The app opens only HTTPS download
   links under this repository's releases.
3. The dialog tells them to quit Axcess, open the disk image, drag Axcess to
   Applications, and choose Replace.

**On both platforms, nothing downloads without a click.** The only automatic
part is the release check itself.

### Tests for the update logic

`desktop/test/updates.test.cjs` has 15 tests for the helpers in `updates.cjs`:

- version parsing, and comparing versions as numbers rather than text;
- mapping release tags to versions;
- the allowlist of download links the app may open;
- choosing the disk image for the running CPU architecture, and ignoring one
  hosted anywhere else;
- the Windows update location, which needs a `latest.yml` file, and
  ignoring a release that has only the old Squirrel `RELEASES` file;
- skipping drafts, prereleases, and unrelated tags;
- offering only strictly newer releases;
- the GitHub API URL.

They run with `npm test` in `desktop/`, which both CI's "Desktop launcher
tests" job and `make desktop-test` call. The flow in `main.cjs` (when the
check runs, the dialogs, the electron-updater calls, and opening the browser) has no
unit tests; `npm test` only checks that file's syntax. The
[smoke test](#smoke-test-both-platforms) covers it by hand.

## Ship a release

Nothing in the repository enforces these steps. They are the checks a person
has to make because the workflow does not.

### Before you merge

1. Confirm CI is green on the pull request. Five jobs run on every pull
   request: "Ruff and mypy", "Unit, quality and route tests", "Frontend lint
   and build", "Desktop launcher tests", and "Desktop release dry run". The
   dry run picks the next version from the published tags, stamps it into
   `desktop/package.json`, and checks the installer names against the ones
   the publish job requires, with the same scripts a release uses
   (`next-version.cjs`, `stamp-version.cjs`, `release-names.cjs` in
   `desktop/scripts/`). The first 0.60 build (of the earlier scheme) failed at the stamp step, which
   no pull request job ran before.
2. If the pull request changes the desktop app or its build, confirm the
   "Desktop application build" run on it built both installers.
3. Confirm the "Accessibility and Playwright UI suites" job passed. If the
   change touches the crawler or a
   [browser check](../glossary.md#browser-check), also add the
   `run-browser-tests` label, which runs the "Integration suites" job.
4. If "Detection evaluations" ran on the pull request, confirm it passed.
5. Write the merge commit message as release notes. Its body becomes the
   "What changed" section.

### Merge and watch

1. Merge to `main`. A merge that changes nothing in the
   [build trigger list](#what-starts-a-build) does not release. If you still
   want a release, run "Desktop application build" manually on `main`.
2. Watch the run in the Actions tab: the two build jobs, then "Publish preview
   release". Hold other app-code merges until it finishes, because a new run
   cancels the one in progress.
3. If a build job fails, nothing is published. Fix the cause and merge again,
   or run the workflow manually once the fix is on `main`.
4. If the publish job fails after creating the draft, the release stays a
   draft. Installed apps ignore drafts, so nobody is offered it. You can
   delete the leftover draft on the Releases page.
5. For a failure that looks flaky, such as a packaging step or an upload,
   try **Re-run failed jobs** on the same run first. A re-run keeps the
   version job's result, so the version and tag stay the same (and a draft is
   not a tag, so even a full re-run picks the same version). The publish job creates a
   draft only when none exists for the tag, uploads with `--clobber`, and
   then publishes, so it completes the existing draft. Start a new run only
   when the code has to change.

### Confirm the release

1. On the Releases page, confirm that "Axcess 0.2.3 (preview)" is marked
   Latest and has these files:
   - `Axcess-0.2.3-Mac-Apple-Silicon.dmg`;
   - `Axcess-0.2.3-Windows-Installer.exe`, its `.blockmap`, and `latest.yml`;
   - `Axcess-0.2.3-Windows-Portable.zip` and `Axcess-0.2.3-Linux.AppImage`;
   - nothing else, apart from the source code archives GitHub adds to every
     release.
2. Read the release notes and check that "What changed" makes sense to someone
   outside the team.

### Smoke test both platforms

Use an Apple Silicon Mac and a Windows x64 PC. These steps cover the
`main.cjs` flow that has no unit tests.

1. **Fresh install.** On a machine without Axcess, download from the
   [Get started page](https://lsa-mis.github.io/axcess/get-started/) and
   approve the first launch as its steps describe. Confirm the review app
   opens rather than the
   ["Axcess could not start" page](../desktop-app.md#axcess-could-not-start).
   On Windows, also check the setup wizard against the Get started steps:
   the "who to install for" choice, the folder screen, and **Open Axcess
   now** on the last screen, which also shows the install folder. Run it
   once with a screen reader (NVDA or Narrator) and confirm each screen and
   the finished message are read out.
2. **Version.** Confirm the launcher log's "starting backend" line shows
   `version 0.2.3 (<short SHA>)` for the new build. The desktop app guide
   lists the [launcher log locations](../desktop-app.md#axcess-could-not-start).
   - The review app has no screen that shows the version. The update dialog
     says "You are running 0.2.3 (<short SHA>)", but only when it offers a
     newer release, so support should ask a user for the launcher log line.
   - On macOS, also open **Axcess > About Axcess** and note whether it shows
     `0.2.3 (<short SHA>)`: the launcher sets the About panel's version to the
     version label. The desktop code never replaces Electron's default menu,
     which should include that item, but nobody has checked it on a Mac yet.
3. **A short scan.** Scan a small site you are authorized to test and open its
   report.
4. **Update from the previous release.** On a machine with the previous
   release installed (the Releases page keeps the ten newest), start Axcess.
   - Windows: choose **Update now**, wait for "Update ready", and choose
     **Restart now**.
   - macOS: choose **Download**, confirm the browser downloads the new
     `-Mac-Apple-Silicon.dmg` from this repository's releases, and replace the app.
   - On both, check the version as in step 2 and confirm your earlier reports
     are still listed.

### Confirm adoption

Axcess has no telemetry, so the only signal that an update reached people is
GitHub's download count for each release file. Record the counts before the
release is pruned, because deleting a release deletes its counts:

```bash
gh api repos/lsa-mis/axcess/releases/tags/desktop-v0.2.3 \
  --jq '.assets[] | [.name, .download_count] | @tsv'
```

Each file mostly counts one path. Anyone can also download any file from the
Releases page, so treat the numbers as estimates:

| File | Who downloads it |
| --- | --- |
| `latest.yml` and `Axcess-0.2.3-Windows-Installer.exe` | Windows apps after someone chooses **Update now** in the update dialog (they read `latest.yml`, then download the installer it names) |
| `Axcess-0.2.3-Mac-Apple-Silicon.dmg` | Mostly macOS apps after someone chooses **Download** in the update dialog, which opens this file |
| `Axcess-0.2.3-Windows-Portable.zip` | Zip copies of Axcess after someone chooses **Download** in their update dialog |
| `Axcess-0.2.3-Linux.AppImage` | Mostly Linux copies after someone chooses **Download** in their update dialog |

These counts miss:

- people who never relaunch the app (there is no timer);
- apps whose update check failed silently, for example when GitHub
  rate-limits unauthenticated requests from a shared campus address;
- macOS users who download the disk image but never replace the app;
- builds whose backend cannot start.

### Before an institutional rollout

Every release today is a preview. Before an institutional rollout, finish the
open items in
[Release work still required](../desktop-app.md#release-work-still-required):

- Apple Developer ID signing and notarization;
- Windows Authenticode signing;
- a signed update channel so macOS can update in place, or documented
  managed-software deployment;
- a U-M security and privacy review of the packaged binaries;
- install, upgrade, rollback, database retention, and uninstall tests on each
  supported operating system version.

## Build installers locally

Build on the operating system you are targeting. These are the `make` targets:

| Command | What it does |
| --- | --- |
| `make desktop-setup` | One-time setup. Installs the review app and Alfa runner dependencies, runs `make desktop-install`, and installs the `desktop` Python dependency group. |
| `make desktop-install` | Runs `npm ci --allow-git=all` in `desktop/` and fetches the Electron binary. |
| `make desktop-run` | Builds the review app, then starts the desktop shell against your checkout. |
| `make desktop-test` | Runs `npm test` in `desktop/`, then `tests/unit/test_desktop_server.py` and `tests/unit/test_alfa_scan_engine.py`. |
| `make desktop-backend` | Builds the review app, installs the Alfa runner, and freezes the backend into `desktop/backend-dist`. |
| `make desktop-browsers` | Installs Playwright's Chromium into `desktop/playwright-browsers`. |
| `make desktop-ocr` | Bundles Tesseract into `desktop/ocr-runtime`. Install Tesseract first: `brew install tesseract` on macOS; on Windows the script suggests `choco install tesseract`. |
| `make desktop-package` | Runs the install, backend, browsers, and OCR targets, then `npm run make` (`npm run make:windows` on Windows). Installers land under `desktop/out/make/`. |

A few things to know:

- On Linux, `make desktop-ocr` needs Tesseract installed first
  (`sudo apt-get install tesseract-ocr tesseract-ocr-eng`), and
  `make desktop-package` builds the AppImage (`npm run make:linux`).
- Local builds are version `0.2.0`, and local macOS builds are ad-hoc signed
  unless you set the
  [signing variables](#settings-for-when-credentials-exist).
- A packaged local build therefore offers the latest published release when
  it starts. Set `AXCESS_DISABLE_UPDATE_CHECK=1` to turn that off.
- The desktop app guide covers the
  [build layers and disk image checks](../desktop-app.md#build-a-local-installer).

## Publish the public site

The [Axcess public site](https://lsa-mis.github.io/axcess/) is static HTML
generated by `site/build.py`.

1. Edit the page copy in `site/build.py`. `PAGES` lists the nine pages, and
   each page has a function that returns its body. Coverage numbers and
   [WCAG](../glossary.md#wcag) criterion cards are rendered from
   `src/audit/rules/wcag_coverage.yaml` through `audit.coverage_matrix` and
   `audit.web.coverage_status`.
2. Run `make site`. It runs `uv run python site/build.py`, which rewrites
   `site/index.html` and `site/<page>/index.html`.
3. Commit the regenerated HTML together with your change.
4. Merge to `main`. `.github/workflows/pages.yml` ("Deploy GitHub Pages")
   runs on pushes to `main` that change `site/**` or the workflow itself, and
   on a manual run. It copies everything in `site/` except `build.py` and
   deploys it.

The deploy never runs `build.py`. A push that changes only `build.py` still
deploys, but it deploys the old HTML. A change to `wcag_coverage.yaml` or
`coverage_status.py` does not reach the site until someone runs `make site`
and commits the result.
The same is true of `docs/glossary.md`: the FAQ page renders its glossary from
that file, so run `make site` after editing a term.

`tests/unit/test_site_build.py` runs in CI with the unit tests. It pins the
list of nine pages, so adding or removing a page means updating the test. It
also checks that every page has one H1, a `lang` attribute, a title, a
`<main>` element, and the shared assets, and that coverage numbers match the
matrix. It checks that the `volume` page is unlisted and `noindex`, and that
every page says Axcess "does not certify WCAG conformance".

The unlisted volume page renders `site/data/volume.json` when that file
exists. `uv run python site/volume.py` writes it from your local
`data/audit.db` as aggregate totals. Like everything under `site/` except
`build.py`, it is published.

The download links need no site rebuild for a new release: they open the
newest release, and `site.js` finds its files (see
[The publish job](#the-publish-job)).

## Known gaps

- **No written release process before this page.** There is no changelog or
  release checklist; the commit message is the only release note.
- **Releases do not wait for CI.** See
  [What does not gate a release](#what-does-not-gate-a-release).
- **The update flow in `main.cjs` has no automated tests.** Only the helpers
  in `updates.cjs` are tested.
- **No rollback through the updater.** The app offers only strictly newer
  versions, and releases older than the ten newest are deleted. The way out
  of a bad release is a new, fixed release.
- **A build that cannot start its backend never checks for updates**, so it
  cannot offer its own fix.
- **No way to measure update adoption beyond download counts.** See
  [Confirm adoption](#confirm-adoption).
- **The review app does not show its own version.** The code writes it to
  the launcher log and shows it in the update dialog when a newer release is
  offered. The operating system may show it too (Electron's default **About
  Axcess** menu item on macOS, the installed app's properties on Windows);
  neither was checked, so confirm them in the smoke test before you rely on
  them.
- **Some statements say more than the code does:**
  - The header comment in `desktop/src/updates.cjs` and a comment at the top
    of `.github/workflows/ci.yml` say every push to `main` publishes a
    release. Only pushes that change the build paths do.
- **Three platforms are released:** Apple Silicon macOS, Windows x64 (the
  installer and the portable zip), and Linux x64 as an AppImage. The Forge
  config's DEB and RPM makers have no build job.
- **The site can drift from its source.** No test compares the committed HTML
  with the output of `site/build.py`, and the deploy publishes whatever is
  committed.
- **The deploy also publishes `site/volume.py` and `site/data/volume.json`**,
  because it excludes only `build.py`.
