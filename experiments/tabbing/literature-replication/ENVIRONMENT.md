# Manager-verified environment and baseline

Observer: gpt-6-astra through Hermes terminal tools. These checks precede any new detector benchmark. They establish readiness and regression baseline only.

## Browser readiness

Prediction registered in chat: installed Chromium launches and one real Tab press focuses a native button on an in-memory page. The control was a page containing only `<button id=control>Control</button>`; the failure criterion was a launch error or active element other than `control` after Tab.

Command ran from repository root via `uv run --offline --no-sync python -c ...`, using Playwright `async_playwright`, `chromium.launch(headless=True)`, `page.set_content`, `page.keyboard.press("Tab")` and `page.evaluate` to read `document.activeElement`. Browser requests were routed to abort. No listener or external page was involved.

Observed:

```json
{"python":"3.14.7","platform":"Linux-6.12.0-211.54.1.el10_2.x86_64-x86_64-with-glibc2.44","playwright":"1.58.0"}
{"browser":"145.0.7632.6","before":"BODY","after":"control","passed":true}
```

Installed Playwright expected Chromium executable exists at `/var/home/me/.distrobox/home/arch-container/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome`. Expected Firefox (`firefox-1509/firefox/firefox`) and WebKit (`webkit-2248/pw_run.sh`) files do not exist under that cache. This is not an exhaustive check for all system browser installs. The installed browser is not KAFE's historical Firefox 68 or BAGEL's Firefox 92.

## Existing scoring/model/runner regression baseline

Prediction registered in chat: the relevant existing unit tests have no failures. A failure would be recorded as pre-existing rather than silently fixed during the new evaluation. Control: existing unit tests, before harness edits and before measurements.

Exact command:

```bash
uv run --offline --no-sync pytest tests/unit/test_kbdiff_scoring.py tests/unit/test_kbdiff_model.py tests/unit/test_kbdiff_runner.py tests/unit/test_kbdiff_bakeoff.py -q
```

Observed exit code 0; pytest reported `121 passed in 0.29s`. The duration is one test-run output, not a performance estimate. No real-world detector accuracy follows from these passing tests.

## Agent execution

Codex preflight used `codex-cli 0.154.0-alpha.6.2` with ChatGPT authentication and read-only sandbox, exited 0. Its conclusions remain claims unless independently corroborated; dispositions are in PREFLIGHT.md.

Claude Code CLI `2.1.270`, subscription-only `claude.ai` Team authentication. A first launch returned `Input must be provided either through stdin or as a prompt argument when using --print`; no inference result came back. A corrected launch inserted `--` before the positional prompt so variadic tool flags could not consume it. Corrected process `proc_de29ce9ea451`, Claude session `6614840f-564d-48d6-ab91-3b77bb26eb56`, reports model `claude-opus-5`. No bypass or sudo flags were used.
