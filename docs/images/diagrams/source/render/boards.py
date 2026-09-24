"""Generate the six Axcess diagram artboards as .dc.html canvas files.

Run:  python3 docs/images/diagrams/source/render/boards.py
Writes docs/images/diagrams/source/project/<Name>.dc.html and
docs/images/diagrams/source/project/canvas.json.
Every label here must match the code, like any other documentation claim.
Each image's alt text lives where the image is used: in the docs and, for the
three site diagrams, in site/build.py (REPORT_GROUPS_ALT and two inline alt
attributes). Find every use with `git grep -n "<png name>"` and update them all
when a diagram changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from kit import (
    AI, AI_BG, BG, GREEN, GREEN_BG, INK, LINE, LINE_SOFT, MAIZE, MAIZE_EDGE, MAIZE_SOFT,
    MONO, MUTED, NAVY, PAPER, SLATE_BG, SOFT2, TEXT2, arrow_h, arrow_v, badge, bullet_item,
    div, header, icon, icon_item, mono, page, path_arrow, pill, span, svg,
)

PROJECT = Path(__file__).resolve().parent.parent / "project"

CARD = dict(background=PAPER, border=f"2px solid {LINE}", border_radius=16,
            box_sizing="border-box")


def card(content: str, **props: object) -> str:
    return div(content, **{**CARD, **props})


def title_row(n: str | None, text: str, size: int = 24, icon_name: str | None = None) -> str:
    lead = badge(n) if n else (icon(icon_name, size=30) if icon_name else "")
    return div(
        lead + span(text, font_size=size, font_weight=800, color=NAVY, line_height=1.2),
        display="flex", align_items="center", gap=12,
    )


def col_heading(icon_name: str, text: str, color: str = NAVY) -> str:
    return div(
        icon(icon_name, size=22, color=color) + span(text),
        display="flex", align_items="center", gap=9, font_size=19, font_weight=800,
        color=color, padding_bottom=8, border_bottom=f"2px solid {LINE_SOFT}",
        margin_bottom=12, line_height=1.2,
    )


def optional(text: str = "(optional)") -> str:
    return span(text, color=MUTED, font_size=18, white_space="nowrap")


def labelled_arrow_v(width: int, height: int, x: int, label: str) -> str:
    return div(
        arrow_v(height, width, x=x, position="absolute", left=0, top=0)
        + span(label, position="absolute", left=x + 18, top=round(height / 2 - 13),
               font_size=18, color=TEXT2, font_weight=700, line_height=1.4),
        position="relative", width=width, height=height,
    )


# ====================================================================== 1
def board_main() -> str:
    w, h = 1600, 1100

    website = card(
        div(icon("globe", 30) + span("The website you scan", font_size=21, font_weight=800,
                                     color=NAVY, line_height=1.2),
            display="flex", align_items="flex-start", gap=10)
        + div("Outside your computer", font_size=18, color=TEXT2, margin_top=8, line_height=1.3),
        padding="16px 16px", height=124, display="flex", flex_direction="column",
        justify_content="center",
    )

    facts = [
        ("target", "Stays in scope"),
        ("link", "Follows links"),
        ("file_check", "Respects robots.txt by default"),
        ("window", "Renders each page in Chromium"),
    ]
    crawler = card(
        div(title_row("1", "Crawler", 26), width=180, flex="none")
        + div("", width=2, height=76, background=LINE_SOFT, flex="none")
        + "".join(div(icon_item(i, t, size=20), flex="1 1 0", min_width=0) for i, t in facts),
        height=124, padding="16px 26px", display="flex", align_items="center", gap=24,
    )

    col_a = div(
        col_heading("list_checks", "Rule engines")
        + div(bullet_item("axe-core rules")
              + bullet_item("Siteimprove Alfa " + optional()),
              display="flex", flex_direction="column", gap=10),
    )
    col_b = div(
        col_heading("keyboard", "Browser checks")
        + div(bullet_item("Keyboard trap")
              + bullet_item("Focus not hidden")
              + bullet_item("Reflow, zoom, and text spacing")
              + bullet_item("Menus, tabs, and dialogs: clicks them, then re-runs axe-core")
              + bullet_item("Motion " + optional()),
              display="flex", flex_direction="column", gap=10),
    )
    ai_box = div(
        div(icon("cpu", 22, AI) + span("Optional local AI, via Ollama"),
            display="flex", align_items="center", gap=8, font_size=18, font_weight=800,
            color=AI, margin_bottom=10, line_height=1.2)
        + div(bullet_item("Vision model reviews image text", dot=AI)
              + bullet_item("Reading order", dot=AI)
              + bullet_item("Language: links, headings, labels, transcripts", dot=AI),
              display="flex", flex_direction="column", gap=8),
        border=f"2px dashed {AI}", border_radius=12, background=AI_BG, padding="12px 14px",
        box_sizing="border-box", height=214, margin_top="auto",
    )
    col_c = div(
        col_heading("image", "Images and AI")
        + bullet_item("Text in images, read by OCR")
        + ai_box,
        display="flex", flex_direction="column", height="100%",
    )
    checks = card(
        title_row("2", "Checks on every rendered page")
        + div(col_a + col_b + col_c, display="grid",
              grid_template_columns="176px 258px 1fr", gap=22, flex="1 1 auto", min_height=0),
        width=846, height=430, padding="18px 22px 20px", display="flex",
        flex_direction="column", gap=16,
    )
    ollama = div(
        div(icon("cpu", 30, AI) + span("Ollama", font_size=24, font_weight=800, color=NAVY),
            display="flex", align_items="center", gap=10)
        + div("Optional local AI models on your computer", font_size=19, line_height=1.35,
              color=INK, margin_top=10)
        + div("Not installed by Axcess", font_size=18, line_height=1.35, color=TEXT2,
              margin_top=6),
        width=210, height=214, box_sizing="border-box", padding="16px 18px",
        border=f"2px dashed {AI}", border_radius=16, background=AI_BG, margin_bottom=22,
    )
    row3 = div(
        checks
        + div(arrow_h(64, 40, "left"), display="flex", flex_direction="column",
              justify_content="flex-end", padding_bottom=22 + 107 - 20, width=64,
              box_sizing="border-box")
        + div(ollama, display="flex", flex_direction="column", justify_content="flex-end"),
        display="flex", height=430,
    )

    def stage(n: str, title: str, items: list[tuple[str, str]]) -> str:
        return card(
            title_row(n, title)
            + div("".join(icon_item(i, t, size=20) for i, t in items),
                  display="flex", flex_direction="column", gap=10),
            width=330, height=188, padding="18px 22px", display="flex",
            flex_direction="column", gap=14,
        )

    store = stage("3", "Evidence store", [
        ("database", "SQLite database, " + mono("audit.db", 19)),
        ("image", "Image and screenshot files"),
    ])
    grouping = stage("4", "Issue grouping", [
        ("layers", "Report groups"),
        ("list_checks", "Priority"),
        ("wrench", "Fix guidance"),
    ])
    review = stage("5", "Review app and exports", [
        ("window", "Review app"),
        ("download", "Excel workbook, audit report, CSV, JSON"),
    ])
    row5 = div(
        store + div(arrow_h(65, 40), display="flex", align_items="center")
        + grouping + div(arrow_h(65, 40), display="flex", align_items="center") + review,
        display="flex", height=188,
    )

    grid = div(
        website
        + arrow_h(104, 124)
        + crawler
        + div("", grid_column="1 / 3")
        + labelled_arrow_v(1120, 44, 423, "Each rendered page")
        + div("", grid_column="1 / 3") + row3
        + div("", grid_column="1 / 3")
        + labelled_arrow_v(1120, 44, 165, "Results")
        + div("", grid_column="1 / 3") + row5,
        position="absolute", left=0, top=40, width=1440, display="grid",
        grid_template_columns="216px 104px 1120px",
        grid_template_rows="124px 44px 430px 44px 188px",
    )
    boundary = div(
        "", position="absolute", left=268, top=0, width=1220, height=890,
        border=f"3px dashed {GREEN}", border_radius=22, background=GREEN_BG,
        box_sizing="border-box",
    )
    boundary_tag = div(
        pill("Your computer", "#FFFFFF", GREEN, "laptop", size=19),
        position="absolute", left=298, top=-19,
    )
    body = div(boundary + boundary_tag + grid, position="relative", width=1488, height=890,
               margin_top=44)
    content = header(
        "How a scan flows through Axcess",
        "Everything except the website you scan runs on your computer. Local AI is optional.",
    ) + body
    return page("Scan flow", w, h, content, padding="40px 56px 34px")



# ====================================================================== 2
def board_groups() -> str:
    w, h = 1600, 900

    def column(name, icon_name, band_bg, band_fg, meaning, items, todo, note=""):
        band = div(
            div(icon(icon_name, 34, band_fg) + span(name, font_size=31, font_weight=800,
                                                     line_height=1.1),
                display="flex", align_items="center", gap=12)
            + div(meaning, font_size=20, margin_top=6, line_height=1.35, font_weight=600),
            background=band_bg, color=band_fg, padding="16px 24px",
        )
        note_html = div(note, font_size=18, color=TEXT2, line_height=1.4, margin_bottom=12,
                        padding_bottom=10, border_bottom=f"2px solid {LINE_SOFT}") if note else ""
        body = div(
            note_html
            + div("What lands here", font_size=18, font_weight=800, color=NAVY,
                  margin_bottom=8, letter_spacing="0.01em")
            + div("".join(bullet_item(t, size=19) for t in items), display="flex",
                  flex_direction="column", gap=6)
            + div(div("What to do", font_size=18, font_weight=800, color=NAVY)
                  + div(todo, font_size=20, font_weight=700, color=INK, margin_top=2,
                        line_height=1.35),
                  margin_top="auto", background=SOFT2, border_left=f"6px solid {NAVY}",
                  border_radius=10, padding="10px 16px"),
            padding="14px 24px 20px", display="flex", flex_direction="column", flex="1 1 auto",
        )
        return card(band + body, overflow="hidden", display="flex", flex_direction="column",
                    height=632)

    barrier = column(
        "Barrier", "octagon", NAVY, "#FFFFFF", "A rule engine reported a failure.",
        ["axe-core rule failures",
         "axe-core failures found after clicking menus, tabs, and dialogs, or after a "
         "configured search",
         "Siteimprove Alfa rules that failed"],
        "Confirm on the page, fix, then rescan.",
    )
    review = column(
        "Needs review", "search", MAIZE, NAVY, "A lead that a person must confirm.",
        ["Browser checks: reflow, zoom, text spacing, focus",
         "Keyboard trap check",
         "Motion checks",
         "Text in images whose alt text is missing or does not match",
         "AI checks: reading order, link purpose, headings, labels, transcripts",
         "Siteimprove Alfa “cannot tell” results"],
        "Test on the page and record a decision.",
        note="Called “Needs confirmation” on the issue page and “Review leads” on the "
             "dashboard.",
    )
    info = column(
        "Informational", "info", SLATE_BG, NAVY, "No barrier was detected.",
        ["Images whose alt text already matches the text in them",
         "Older records kept for history"],
        "Nothing required.",
    )
    cols = div(barrier + review + info, display="grid",
               grid_template_columns="repeat(3, 1fr)", gap=28, margin_top=26)
    footer = div(
        icon("user", 28, MAIZE)
        + span("Only rule-engine failures become Barriers. Anything that needs judgment "
               "waits for a person."),
        display="flex", align_items="center", gap=14, background=NAVY, color="#FFFFFF",
        font_size=22, font_weight=700, border_radius=14, padding="14px 26px", margin_top=18,
    )
    content = header(
        "Where each result goes",
        "Every issue group gets one of three labels, shown in the Type column of the "
        "Issues table.",
    ) + cols + footer
    return page("Report groups", w, h, content)


# ====================================================================== 3
def who(kind: str) -> str:
    if kind == "you":
        return pill("You", NAVY, MAIZE_SOFT, "user", border=f"2px solid {MAIZE_EDGE}")
    return pill("Axcess", "#FFFFFF", NAVY, "laptop", border=f"2px solid {NAVY}")


def step_card(n, kinds, title, body, width, height):
    return card(
        div(badge(n, 40) + "".join(who(k) for k in kinds), display="flex",
            align_items="center", gap=10)
        + div(title, font_size=22, font_weight=800, color=NAVY, margin_top=14, line_height=1.25)
        + div(body, font_size=19, line_height=1.42, color=INK, margin_top=8),
        width=width, height=height, padding="18px 20px", flex="none",
    )


def board_login() -> str:
    w, h = 1600, 900
    q = lambda t: "“" + t + "”"  # noqa: E731
    r1 = [
        step_card("1", ["you"], "Choose a login scan",
                  f"In New scan, choose {q('Site with a login or 2FA')} and enter the "
                  f"{q('Page to scan after you sign in')} (HTTPS).", 342, 276),
        step_card("2", ["you", "axcess"], "Open the sign-in browser",
                  f"Select {q('Open browser to sign in')}. Axcess opens a visible Chromium "
                  "window with a fresh temporary profile.", 342, 276),
        step_card("3", ["you"], "Sign in yourself",
                  "Sign in directly with the site, including SSO and any two-factor step. "
                  "Axcess never asks for or stores your password or codes.", 342, 276),
        step_card("4", ["you"], "Start the scan",
                  f"Select {q('I’m signed in, start scan')}.", 342, 276),
    ]
    arrow = div(arrow_h(40, 40), display="flex", align_items="center", width=40)
    row1 = div(arrow.join(r1), display="flex", margin_top=30)
    r2 = [
        step_card("5", ["axcess"], "The session moves in memory",
                  "Axcess copies the session (cookies and site storage) in memory to a hidden "
                  "scanning browser and closes the sign-in window. With "
                  f"{q('Show the scanning browser window')} on, it keeps scanning in the "
                  "visible window.", 468, 284),
        step_card("6", ["axcess"], "Scan from where you landed",
                  "The scan crawls from where you landed and stays in scope. Rendered pages "
                  "and screenshots are saved to the local report unless you choose "
                  f"{q('Don’t store rendered pages')}.", 468, 284),
        step_card("7", ["axcess"], "The session is destroyed",
                  "When the scan ends, the session is closed and the temporary profile is "
                  "deleted. Nothing reusable is saved.", 468, 284),
    ]
    arrow2 = div(arrow_h(42, 40), display="flex", align_items="center", width=42)
    row2 = div(arrow2.join(r2), display="flex")
    x4, x5 = 3 * 382 + 171, 234
    connector = div(
        svg(1488, 60, path_arrow([(x4, 0), (x4, 30), (x5, 30), (x5, 60)], "down"),
            position="absolute", left=0, top=0)
        + span("Then Axcess takes over", position="absolute", left=640, top=16,
               background=BG, padding="0 12px", font_size=18, font_weight=800, color=NAVY,
               line_height=1.4),
        position="relative", height=60,
    )
    note = div(
        icon("lock", 26, NAVY)
        + span("Login scans need an HTTPS site whose address resolves to a public IP address."),
        display="flex", align_items="center", gap=12, background=MAIZE_SOFT,
        border=f"2px solid {MAIZE_EDGE}", border_radius=14, padding="12px 22px",
        font_size=20, font_weight=700, color=INK, margin_top=20,
    )
    content = header(
        "How a login scan works",
        "You sign in yourself in a visible browser. Your password is typed into the site, "
        "never into Axcess.",
    ) + row1 + connector + row2 + note
    return page("Login scan", w, h, content)


# ====================================================================== 4
def board_privacy() -> str:
    w, h = 1600, 900

    def item(icon_name, title, text):
        return card(
            div(icon(icon_name, 28) + span(title, font_size=21, font_weight=800, color=NAVY,
                                           line_height=1.2),
                display="flex", align_items="center", gap=10)
            + div(text, font_size=19, line_height=1.4, color=INK, margin_top=10),
            padding="16px 18px", height=156,
        )

    items = [
        item("window", "Axcess app", "The scanner and the review app"),
        item("database", "Report database", "SQLite database, " + mono("audit.db", 18)),
        item("code", "Stored pages", "Rendered HTML, kept in the database"),
        item("image", "Images and screenshots", "Files in the " + mono("blobs", 18) + " folder"),
        item("file_text", "Logs", "Include page URLs and titles"),
        item("cpu", "Ollama " + optional(), "Local AI models, if you install them"),
    ]
    grid = div("".join(items), position="absolute", left=28, top=44, width=844,
               display="grid", grid_template_columns="repeat(3, 1fr)", gap=16)
    banner = div(
        icon("shield", 32, GREEN) + span("No account. No telemetry. No upload."),
        position="absolute", left=28, top=412, width=844, height=76, box_sizing="border-box",
        display="flex", align_items="center", justify_content="center", gap=14,
        background=PAPER, border=f"2px solid {GREEN}", border_radius=14, font_size=26,
        font_weight=800, color=GREEN,
    )
    boundary = div(
        "", position="absolute", left=0, top=0, width=900, height=548,
        border=f"3px dashed {GREEN}", border_radius=22, background=GREEN_BG,
        box_sizing="border-box",
    )
    btag = div(pill("Your computer", "#FFFFFF", GREEN, "laptop", size=19),
               position="absolute", left=28, top=-19)

    def out(icon_name, title, text, top, height, extra="", dashed=False):
        return card(
            div(icon(icon_name, 28) + span(title, font_size=21, font_weight=800, color=NAVY,
                                           line_height=1.2),
                display="flex", align_items="center", gap=10)
            + extra
            + div(text, font_size=19, line_height=1.42, color=INK, margin_top=8),
            position="absolute", left=1000, top=top, width=488, height=height,
            padding="14px 20px", border=f"2px {'dashed' if dashed else 'solid'} {LINE}",
        )

    q = lambda t: "“" + t + "”"  # noqa: E731
    outs = (
        div("Leaves your computer", position="absolute", left=1000, top=0, font_size=20,
            font_weight=800, color=NAVY, line_height=1.3)
        + out("globe", "The website you scan",
              "Crawling. Viewing a stored page can also load the site’s styles, fonts, "
              "and images.", 40, 124)
        + out("refresh", "GitHub update check",
              "One check per launch to " + mono("api.github.com", 18) + ". Sends no scan "
              f"data. Downloads only if you click {q('Update now')} or {q('Download')}. "
              "Turn it off with " + mono("AXCESS_DISABLE_UPDATE_CHECK=1", 18) + ".",
              180, 232,
              extra=div(pill("Desktop app only", NAVY, MAIZE_SOFT, None,
                             border=f"2px solid {MAIZE_EDGE}", size=17), margin_top=8))
        + out("cursor", "Only if you click a link",
              f"{q('Rule docs')} and {q('Give feedback')} open in your browser. Nothing about "
              "your scan is attached.", 428, 120, dashed=True)
    )
    arrows = (
        arrow_h(100, 40, position="absolute", left=900, top=102 - 20)
        + arrow_h(100, 40, position="absolute", left=900, top=296 - 20)
        + arrow_h(100, 40, dashed=True, position="absolute", left=900, top=488 - 20)
    )
    body = div(boundary + btag + grid + banner + arrows + outs, position="relative",
               height=548, margin_top=44)
    caveat = div(
        div(icon("alert", 30, NAVY) + span("Good to know", font_size=22, font_weight=800,
                                           color=NAVY),
            display="flex", align_items="center", gap=10, flex="none", width=210)
        + div(
            bullet_item("Files are stored unencrypted, including signed-in pages and "
                        f"screenshots unless you choose {q('Don’t store rendered pages')}.")
            + bullet_item("Deleting a report keeps its image and screenshot files."),
            display="grid", grid_template_columns="1.45fr 1fr", gap=32),
        display="flex", align_items="center", gap=24, background=MAIZE_SOFT,
        border=f"2px solid {MAIZE_EDGE}", border_radius=16, padding="18px 26px",
        margin_top=26,
    )
    content = header(
        "What stays on your computer",
        "Reports and evidence stay in local files. Only the connections on the right leave "
        "your computer.",
    ) + body + caveat
    return page("Privacy boundary", w, h, content)


# ====================================================================== 5
def chip(text: str) -> str:
    return span(text, font_family=MONO, font_size=18, font_weight=600, color=NAVY,
                background=SOFT2, border=f"1.5px solid {LINE}", border_radius=8,
                padding="2px 8px", white_space="nowrap", line_height=1.5)


def board_release() -> str:
    w, h = 1600, 900
    q = lambda t: "“" + t + "”"  # noqa: E731

    def step(n, icon_name, title, body, height=340, width=266):
        return card(
            div(badge(n, 38) + icon(icon_name, 28), display="flex", align_items="center",
                gap=10)
            + div(title, font_size=22, font_weight=800, color=NAVY, margin_top=12,
                  line_height=1.25)
            + div(body, font_size=19, line_height=1.42, color=INK, margin_top=8),
            width=width, height=height, padding="16px 18px", flex="none",
        )

    chips = lambda xs: div("".join(chip(x) for x in xs), display="flex",  # noqa: E731
                           flex_wrap="wrap", gap=6, margin="6px 0")
    s1 = step("1", "git_merge", "Merge to main",
              "With a change under:" + chips(["src/", "desktop/", "pyproject.toml", "uv.lock"])
              + "or the workflow file. A manual run also works.")
    s2 = step("2", "wrench", "Build both apps",
              chips(["desktop-build.yml"])
              + "macOS (Apple Silicon) and Windows (x64) build in parallel, stamped "
              + span(mono("0.1.&lt;run number&gt;", 18), white_space="nowrap") + ".")
    s3 = step("3", "package", "Publish job",
              "Creates GitHub release " + mono("desktop-v0.1.N", 18) + ", marked latest. "
              "Adds version-less download names. Keeps the 10 newest.")
    s4 = step("4", "refresh", "App checks on launch",
              "The installed app asks GitHub for the latest release and offers a newer one.")

    def platform(name, body):
        return card(
            div(name, font_size=22, font_weight=800, color=NAVY)
            + div(body, font_size=19, line_height=1.42, color=INK, margin_top=6),
            width=266, height=162, padding="14px 18px",
        )

    s5 = div(
        platform("Windows", f"{q('Update now')}, download, then {q('Restart now')}.")
        + platform("macOS", f"{q('Download')} opens the new disk image."),
        display="flex", flex_direction="column", gap=16, flex="none",
    )
    fork = svg(40, 340,
               path_arrow([(2, 170), (16, 170), (16, 81), (39, 81)], "right")
               + path_arrow([(16, 170), (16, 259), (39, 259)], "right"))
    arrow = div(arrow_h(40, 40), display="flex", align_items="center", width=40)
    lane = div(s1 + arrow + s2 + arrow + s3 + arrow + s4 + fork + s5, display="flex",
               margin_top=34, height=340)
    caveat = div(
        div(icon("alert", 30, NAVY) + span("Watch out", font_size=22, font_weight=800,
                                           color=NAVY),
            display="flex", align_items="center", gap=10, flex="none", width=190)
        + div(bullet_item("No tests gate the publish job.")
              + bullet_item("Builds are not notarized: macOS is ad-hoc signed, Windows is "
                            "unsigned."),
              display="grid", grid_template_columns="0.8fr 1.2fr", gap=32),
        display="flex", align_items="center", gap=24, background=MAIZE_SOFT,
        border=f"2px solid {MAIZE_EDGE}", border_radius=16, padding="18px 26px",
        margin_top=26,
    )

    def site_box(content, width):
        return card(content, width=width, height=96, padding="14px 18px", display="flex",
                    align_items="center", font_size=20, line_height=1.4, flex="none")

    sarrow = div(arrow_h(48, 40), display="flex", align_items="center", width=48)
    site = card(
        div(pill("Separate lane: the public site", NAVY, SOFT2, "globe",
                 border=f"2px solid {LINE}", size=18))
        + div(
            site_box(div("A change under " + mono("site/", 19) + " is pushed to main"), 360)
            + sarrow
            + site_box(div(mono("pages.yml", 19, NAVY, 700)
                           + div("GitHub Pages workflow", font_size=19, color=TEXT2)), 300)
            + sarrow
            + site_box(div("Publishes the committed " + mono("site/", 19) + " HTML"), 360)
            + div(
                div(icon("info", 24, NAVY), flex="none", margin_top=2)
                + div("It does not run " + mono("build.py", 18) + ". Run " + mono("make site", 18)
                      + " and commit the HTML first.", font_size=19, line_height=1.4),
                display="flex", gap=10, align_items="flex-start", margin_left=24,
                width=300),
            display="flex", align_items="center", margin_top=14),
        padding="16px 22px", margin_top=26, background=PAPER,
    )
    content = header(
        "How a desktop release ships",
        "Merging app code to main publishes a preview release. Installed apps offer it "
        "on their next launch.",
    ) + lane + caveat + site
    return page("Release flow", w, h, content)


# ====================================================================== 6
def board_code() -> str:
    w, h = 1600, 1100
    dot = span("\u00a0\u00b7 ", color=MUTED)

    def files(xs):
        return div(dot.join(xs), font_family=MONO, font_size=18, font_weight=500,
                   color=TEXT2, line_height=1.45, margin_top=8)

    def name_row(name, icon_name="folder", extra=""):
        return div(icon(icon_name, 26) + span(name, font_family=MONO, font_size=22,
                                              font_weight=700, color=NAVY) + extra,
                   display="flex", align_items="center", gap=10)

    def area(name, desc, body="", span_cols=1, icon_name="folder", **props):
        return card(
            name_row(name, icon_name)
            + (div(desc, font_size=20, line_height=1.35, color=INK, margin_top=8) if desc else "")
            + body,
            padding="14px 18px", grid_column=f"span {span_cols}", **props,
        )

    def sub(name, desc, name_w=150):
        return div(span(name, font_family=MONO, font_size=19, font_weight=700, color=NAVY,
                        width=name_w, flex="none", display="inline-block")
                   + span(desc, font_size=19, color=INK),
                   display="flex", align_items="baseline", gap=12, line_height=1.4)

    cells = [
        area("crawler/", "Scopes, fetches, renders, and queues pages",
             files(["orchestrator.py", "url_policy.py"])),
        area("extractor/", "Finds images and SVG text, stores blobs",
             files(["html_images.py", "svg_text.py", "pipeline.py"])),
        area("analyzer/", "Rule engines, browser probes, OCR, and AI checks",
             files(["axe.py", "alfa.py", "keyboard/", "focus/", "responsive/",
                    "interaction/", "visual/", "ocr/", "vlm/", "semantic/"]), span_cols=2),
        area("synthesizer/", "Image findings, priority, and scan diffs",
             files(["findings.py", "priority.py", "diff.py"])),
        area("db/", "SQLite schema, migrations, and job queue",
             files(["migrations/", "repo.py", "queue.py"])),
        card(
            name_row("web/", extra=span("Report API and review app", font_size=20,
                                        color=INK, margin_left=6))
            + div(sub("server.py", "FastAPI app and /api routes")
                  + sub("issues.py", "Issue groups, report groups, and priority")
                  + sub("frontend/", "React review app"),
                  display="flex", flex_direction="column", gap=4, margin_top=10),
            padding="14px 18px", grid_column="span 2",
        ),
        area("exports/", "Workbook, audit report, CSV, JSON, and more",
             files(["xlsx_export.py", "audit_report.py"])),
        area("protected/", "Login sessions and protected scans",
             files(["session.py", "egress.py", "companion.py"])),
        area("rules/", "YAML: fix text, coverage, AI models",
             files(["audit_report.yaml", "wcag_coverage.yaml"])),
        card(
            div("Also in src/audit/", font_size=20, font_weight=800, color=NAVY)
            + div(sub("cli.py", "Command line", 170)
                  + sub("config.py", "Settings", 170)
                  + sub("blob_store.py", "Stored files", 170)
                  + sub("alfa_runner/", "Alfa runner", 170),
                  display="flex", flex_direction="column", gap=2, margin_top=8),
            padding="14px 18px", background=SOFT2,
        ),
    ]
    package = div(
        div(icon("code", 30) + span("src/audit/", font_family=MONO, font_size=26,
                                    font_weight=700, color=NAVY)
            + span("The Python package", font_size=20, color=TEXT2),
            display="flex", align_items="center", gap=12)
        + div("".join(cells), display="grid", grid_template_columns="repeat(4, 1fr)",
              grid_auto_rows="178px", gap=14, margin_top=14),
        box_sizing="border-box", padding="18px 22px 22px", background="#E8EEF5",
        border=f"2px solid {LINE}", border_radius=20, margin_top=30,
    )
    beside = div(
        div(icon("folder", 30) + span("Next to src/", font_size=24, font_weight=800,
                                      color=NAVY),
            display="flex", align_items="center", gap=12)
        + div(
            area("desktop/", "Electron shell, packaging, and update check",
                 files(["src/main.cjs", "forge.config.cjs"]))
            + area("site/", "Public site: build.py writes the HTML",
                   files(["build.py", "assets/", "volume.py"]))
            + card(
                name_row("tests/", "flask", extra=span("Test suites", font_size=20,
                                                       color=INK, margin_left=6))
                + div(sub("unit/", "Domain logic and export goldens", 170)
                      + sub("integration/", "Crawl pipelines", 170)
                      + sub("ui/", "Server routes and UI", 170)
                      + sub("quality/", "Detection precision benchmark", 170),
                      display="flex", flex_direction="column", gap=2, margin_top=8),
                padding="14px 18px", grid_column="span 2",
            ),
            display="grid", grid_template_columns="repeat(4, 1fr)", grid_auto_rows="178px",
            gap=14, margin_top=12),
        margin_top=22, padding="0 24px",
    )
    content = header(
        "Where the code lives",
        "The Python package is src/audit/. The desktop app, public site, and tests sit "
        "beside it.",
    ) + package + beside
    return page("Code map", w, h, content)


# ============================================================ canvas files
BOARDS = [
    ("Main.dc.html", "How a scan flows through Axcess", 1600, 1100, board_main),
    ("ReportGroups.dc.html", "Where each result goes", 1600, 900, board_groups),
    ("LoginScan.dc.html", "How a login scan works", 1600, 900, board_login),
    ("PrivacyBoundary.dc.html", "What stays on your computer", 1600, 900, board_privacy),
    ("ReleaseFlow.dc.html", "How a desktop release ships", 1600, 900, board_release),
    ("CodeMap.dc.html", "Where the code lives", 1600, 1100, board_code),
]


def main() -> None:
    PROJECT.mkdir(parents=True, exist_ok=True)
    boards: dict[str, dict[str, object]] = {}
    order: list[str] = []
    x = y = 0
    row_h = 0
    for index, (name, title, w, h, build) in enumerate(BOARDS):
        html = build()
        (PROJECT / name).write_text(html, encoding="utf-8")
        if index and index % 2 == 0:
            x = 0
            y += row_h + 120
            row_h = 0
        boards[name] = {"x": x, "y": y, "w": w, "h": h, "title": title}
        order.append(name)
        x += w + 80
        row_h = max(row_h, h)
    canvas = {
        "v": 3,
        "createdOnFiles": {"v": 1, "at": "2026-09-24T12:00:00Z"},
        "title": "Axcess architecture diagrams",
        "launch": {"view": "canvas"},
        "pages": [],
        "boards": boards,
        "order": order,
        "notes": {
            "title": {"x": 0, "y": -300, "text": "Axcess architecture diagrams",
                      "kind": "title1", "maxW": 3280},
        },
        "designSystems": [],
    }
    (PROJECT / "canvas.json").write_text(json.dumps(canvas, indent=2) + "\n", encoding="utf-8")
    print("wrote", ", ".join(order))


if __name__ == "__main__":
    main()
