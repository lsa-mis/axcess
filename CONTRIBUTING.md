# Contributing to Axcess

Thanks for helping build Axcess. This guide is for anyone who changes its code,
checks, documentation, or public site. If you want to scan a website instead,
start with the [README](README.md).

## Set up from source

You need Python 3.11 or newer, [uv](https://docs.astral.sh/uv/), Node.js 22.22
or newer, and Tesseract (the `tesseract` command) for reading text in images.

```bash
git clone https://github.com/lsa-mis/axcess.git
cd axcess
make setup            # Python packages, Playwright Chromium, data/ folders
make migrate          # create or upgrade data/audit.db
make frontend-build   # install and build the React review app
make alfa-install     # optional: the Siteimprove Alfa rule engine
make run              # http://127.0.0.1:8765/app/ with auto-reload
```

- `make run-stable` serves the same app without auto-reload. Use it for long
  login scans: the signed-in session lives only in the server's memory, so a
  reload interrupts the scan.
- Without `make frontend-build`, `/app/` shows a "Frontend bundle not built"
  notice.
- Local AI checks are optional and need [Ollama](https://ollama.com), which you
  install yourself. `make fetch-models` pulls the vision models, and
  `make fetch-analyzer-models` pulls the models recommended in
  `src/audit/rules/analyzer_models.yaml`.

## Quality gates

Run the narrowest gate while you work. Before handoff, `AGENTS.md` asks for
`make lint`, `make typecheck`, `make frontend-build`, and the unit and route
tests, plus `make test` when a change crosses the crawler, storage, or UI.

| Command | What it runs |
| --- | --- |
| `make lint` | `ruff check` and `ruff format --check` on `src`, `tests`, and `scripts`, then ESLint on the React app |
| `make typecheck` | Strict mypy on `src/audit`, then the TypeScript check |
| `make test` | The whole pytest suite, including integration and browser tests |
| `make test-unit` | `tests/unit` |
| `make test-integration` | `tests/integration` (real crawls of a local fixture site) |
| `make test-ui` | `tests/ui` (API routes, plus Playwright tests of the app) |
| `make frontend-build` | `npm ci` when the package files changed, then `tsc -b` and `vite build` |
| `make a11y-check` | The axe-core tests of the app's own UI (`pytest tests/ui -m ui -k axe`) |
| `make quality-gate` | Scores the labeled detection corpus against the false discovery rate gate, then `pytest tests/quality` |
| `make detection-evals` | Efficacy, efficiency, and scale evaluations, written to `artifacts/detection-evals/` |
| `make desktop-test` | The desktop launcher's Node tests, then the desktop server and Alfa engine unit tests |

A few things to know:

- `make lint` and `make typecheck` need the frontend packages, so run
  `make frontend-build` first. `make desktop-test` needs `make desktop-install`.
- Browser tests need Chromium from `make setup`, and the UI browser tests drive
  the built app. Integration tests that read image text skip themselves when
  `tesseract` is missing.
- The corpus gate scores frozen, labeled results and never runs a detector.
  [DETECTION_EFFICACY.md](DETECTION_EFFICACY.md) explains both quality lanes.

### What CI runs

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`, a daily
schedule, and manual dispatch.

| Job | What it runs |
| --- | --- |
| `python-static` | `ruff check`, `ruff format --check`, and `mypy` |
| `python-tests` | `pytest tests/unit tests/quality tests/ui -m "not browser"` |
| `frontend` | `npm run lint` and `npm run build` (the build is also the TypeScript check) |
| `desktop-node` | `npm test` in `desktop/` |
| `browser-suites` | `pytest tests/integration` and `pytest tests/ui -m browser` |

The `browser-suites` job runs only on the daily schedule, on manual dispatch,
or on a pull request labeled `run-browser-tests`. The axe-core tests of the app
are browser tests, so they run only there. If your change touches the crawler,
a browser check, or the UI, add the label so these suites run before merge.

Other workflows:

- `detection-evals.yml` runs the `make detection-evals` command on pull
  requests and pushes to `main` that touch detection code, weekly, and on
  demand.
- CI does not run the corpus scoring step of `make quality-gate`, but
  `tests/quality` runs in `python-tests`.
- CI runs Python 3.13, and ruff and mypy target 3.11 (the minimum version).
- `pages.yml` publishes the public site, and [Releases](docs/internal/releases.md)
  covers the desktop build.

## Rules from AGENTS.md that apply to everyone

[AGENTS.md](AGENTS.md) is the contract for coding agents, and these rules hold
for people too:

1. Run `git status` before you start. A checkout can hold unrelated work in
   progress, so keep it, and do not reformat or revert files you did not mean
   to change.
2. Make every schema change as a pair of files in `src/audit/db/migrations/`:
   a forward migration and a matching `.rollback.sql`. The
   [developer guide](docs/internal/developer-guide.md#add-a-migration) has the
   recipe.
3. Keep endpoint handlers thin. Put queries and checks in typed modules that
   unit tests can exercise without FastAPI or a live model.
4. Keep the React app's TypeScript types and API client in step with the API.
5. Do not change what existing scans, issues, exports, statuses, or blobs mean
   to make a new feature easier. Extend them compatibly.
6. Keep hosted or LAN use private or behind `AUDIT_ACCESS_TOKEN`
   ([hosting guide](docs/hosting.md)). Never expose the crawler as an open
   public URL.

## Documentation rules

- [docs/glossary.md](docs/glossary.md) is the single source of terms. Link to
  a term's heading instead of defining it again.
- Docs for people who use Axcess live in `docs/`. Docs for people who build and
  maintain it live in `docs/internal/`.
- Write plain English in short sentences, and use descriptive link text.
- Use no em dashes or en dashes. Commas, colons, periods, and parentheses work
  instead. This prints both counts, and both should be 0:
  `python3 -c "import sys;t=open(sys.argv[1],encoding='utf-8').read();print(t.count(chr(0x2014)),t.count(chr(0x2013)))" FILE`
- Never write that a scan proves WCAG conformance or legal compliance.
- Code, tests, or CI cite these paths, so a file must stay at each one:
  `docs/hosting.md`, `docs/coverage-tracker.md`, `docs/protected-scans.md`,
  `docs/architecture.md`, and `DETECTION_EFFICACY.md`. If content moves, leave
  a short pointer behind, as `docs/architecture.md` does.

## Editing the public site

The [public site](https://lsa-mis.github.io/axcess/) is generated.

- Page copy lives in `site/build.py`. Edit it, then run `make site` to
  regenerate `site/**/index.html`.
- Commit the regenerated HTML with your change. `.github/workflows/pages.yml`
  publishes the committed `site/` folder when a push to `main` changes it, and
  never runs the generator, so an edit to `site/build.py` alone never reaches
  the site.
- Coverage numbers come from `src/audit/rules/wcag_coverage.yaml` and
  `src/audit/web/coverage_status.py`, and the FAQ glossary is rendered from
  `docs/glossary.md`. Run `make site` after changing any of them.
- `tests/unit/test_site_build.py` pins the list of pages, so adding or removing
  a page means updating that test. It also checks page structure, coverage
  numbers, and the statement that Axcess does not certify WCAG conformance.

## Where to read next

The [internal docs index](docs/internal/README.md) lists every maintainer
guide. Good first reads are the [architecture](docs/internal/architecture.md)
and the [developer guide](docs/internal/developer-guide.md).
