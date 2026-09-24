# Diagram sources

The six PNG diagrams in `docs/images/diagrams/` are generated from the files in
this folder. Edit the source, render again, and commit the source and the PNG
together.

## What is here

| Path | What it is |
| --- | --- |
| `render/boards.py` | The content of every diagram: titles, labels, and layout. Start here. |
| `render/kit.py` | Shared styles and building blocks (colors, fonts, icons, cards). |
| `render/build.py` | Turns each artboard into standalone HTML and screenshots it at 2x. |
| `project/*.dc.html`, `project/canvas.json` | The artboards in Claude Design canvas format, written by `boards.py`. |
| `fonts/` | Atkinson Hyperlegible Next and Mono (SIL Open Font License), used for rendering. |

## Change a diagram

1. Edit the text or layout in `render/boards.py`. Every label on a diagram must
   match the code, like any other documentation claim.
2. Regenerate the artboards: `python3 docs/images/diagrams/source/render/boards.py`.
3. Render the PNGs: `python3 docs/images/diagrams/source/render/build.py`, or pass
   board names (for example `ReportGroups`) to render only those. It needs a
   Chromium headless shell; set `AXCESS_DIAGRAM_BROWSER` to its path if it is
   not at the default Playwright location. It writes throwaway HTML files into
   `render/`; delete them before you commit.
4. If the change affects what a diagram shows, update its alt text everywhere
   the image is used (search the docs for the file name), and copy the report
   groups, login scan, and privacy PNGs into `site/assets/diagrams/` and run
   `make site`.

| PNG | Artboard |
| --- | --- |
| `system-architecture.png` | `Main` |
| `report-groups.png` | `ReportGroups` |
| `login-scan-flow.png` | `LoginScan` |
| `privacy-boundary.png` | `PrivacyBoundary` |
| `release-flow.png` | `ReleaseFlow` |
| `code-map.png` | `CodeMap` |
