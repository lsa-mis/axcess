"""Shared building blocks for the Axcess diagram artboards.

Every artboard is a Claude Design ``.dc.html`` page whose layout lives in
inline ``style`` attributes. These helpers keep the six boards consistent:
one palette, one type scale, one arrow style, one icon set.
"""

from __future__ import annotations

# ---------------------------------------------------------------- palette
# Brand colours come from site/assets/site.css (:root). Pairs used for text
# are checked by contrast.py (4.5:1 minimum for text under 24px).
NAVY = "#00274C"
NAVY2 = "#0B3D73"
MAIZE = "#FFCB05"
MAIZE_SOFT = "#FFF4C2"
MAIZE_EDGE = "#8A6A00"  # border for maize-soft boxes (3:1 against white)
INK = "#111827"
TEXT2 = "#374151"
MUTED = "#4B5563"
LINE = "#7A8799"  # card borders, 3:1 against white and the page
LINE_SOFT = "#D5DCE5"  # decorative rules only
BG = "#F5F7FA"
PAPER = "#FFFFFF"
SOFT2 = "#EEF2F7"
SLATE_BG = "#E3E8EF"
GREEN = "#0F5132"
GREEN_BG = "#EFF7F2"
AI = "#6B3A00"
AI_BG = "#FFF1DC"
TEAL = "#0B4F6C"
TEAL_BG = "#E3F1F7"

SANS = "'Atkinson Hyperlegible Next',system-ui,sans-serif"
MONO = "'Atkinson Hyperlegible Mono',ui-monospace,monospace"

FONT_LINK = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Atkinson+Hyperlegible+Mono:wght@400..700&amp;"
    'family=Atkinson+Hyperlegible+Next:wght@400..800&amp;display=swap">'
)
PAGE_STYLE = (
    "<style>body{margin:0;font-family:'Atkinson Hyperlegible Next',system-ui,"
    f"sans-serif;background:{BG};color:{INK};-webkit-font-smoothing:antialiased}}"
    "</style>"
)


def css(**props: object) -> str:
    """Build an inline style string; snake_case keys become kebab-case."""
    parts = []
    for key, value in props.items():
        if value is None:
            continue
        name = key.rstrip("_").replace("_", "-")
        if isinstance(value, (int, float)) and name not in {
            "font-weight",
            "line-height",
            "flex-grow",
            "flex-shrink",
            "z-index",
            "opacity",
            "order",
        }:
            value = f"{value}px"
        parts.append(f"{name}:{value}")
    return ";".join(parts)


def tag(name: str, content: str = "", **props: object) -> str:
    style = css(**props)
    attr = f' style="{style}"' if style else ""
    return f"<{name}{attr}>{content}</{name}>"


def div(content: str = "", **props: object) -> str:
    return tag("div", content, **props)


def span(content: str = "", **props: object) -> str:
    return tag("span", content, **props)


def mono(text: str, size: int = 19, color: str = INK, weight: int = 500) -> str:
    return span(text, font_family=MONO, font_size=size, color=color, font_weight=weight)


# ------------------------------------------------------------------ icons
# Stroke icons in the style of Lucide (ISC licence), drawn on a 24px grid.
ICONS = {
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    "laptop": '<rect x="4" y="4" width="16" height="11" rx="2"/><path d="M2 20h20"/><path d="M4 15l-2 5"/><path d="M20 15l2 5"/>',
    "route": '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "file_check": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/>',
    "window": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 9h20"/><path d="M6 6.5h.01"/><path d="M9.5 6.5h.01"/>',
    "list_checks": '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
    "cursor": '<path d="M9.04 9.69a.5.5 0 0 1 .65-.65l11 4.5a.5.5 0 0 1-.07.95l-4.35 1.04a1 1 0 0 0-.74.74l-1.04 4.35a.5.5 0 0 1-.95.07z"/><path d="M7.2 2.2 8 5.1"/><path d="m5.1 8-2.9-.8"/><path d="M14 4.1 12 6"/><path d="m6 12-1.9 2"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "octagon": '<path d="M15.31 2a2 2 0 0 1 1.42.59l4.68 4.68A2 2 0 0 1 22 8.69v6.62a2 2 0 0 1-.59 1.42l-4.68 4.68a2 2 0 0 1-1.42.59H8.69a2 2 0 0 1-1.42-.59l-4.68-4.68A2 2 0 0 1 2 15.31V8.69a2 2 0 0 1 .59-1.42l4.68-4.68A2 2 0 0 1 8.69 2z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "file_text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "git_merge": '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "package": '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 7.7 4.73a2 2 0 0 0 2 0L20.7 7"/><path d="m7.5 4.27 9 5.15"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "code": '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
    "flask": '<path d="M14 2v6a2 2 0 0 0 .25.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.76-2.96l5.51-10.08A2 2 0 0 0 10 8V2"/><path d="M6.45 15h11.1"/><path d="M8.5 2h7"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "unlock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>',
    "keyboard": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 8h.01"/><path d="M10 8h.01"/><path d="M14 8h.01"/><path d="M18 8h.01"/><path d="M8 12h.01"/><path d="M12 12h.01"/><path d="M16 12h.01"/><path d="M7 16h10"/>',
    "message": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "check_circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "log_in": '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="m10 17 5-5-5-5"/><path d="M15 12H3"/>',
    "eye_off": '<path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>',
}


def icon(name: str, size: int = 24, color: str = NAVY, width: float = 2) -> str:
    body = ICONS[name]
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" style="flex:none;display:block">'
        f"{body}</svg>"
    )


BRAND_MARK = (
    '<svg width="34" height="34" viewBox="0 0 32 32" fill="none" stroke="#00274C" '
    'stroke-width="2.5" stroke-linecap="round" aria-hidden="true" style="flex:none;display:block">'
    '<path d="M 20.31 4.16 A 12.6 12.6 0 1 0 26.45 8.95"/>'
    '<path d="M 17.438 21.016 C 16.989 21.141 16.515 21.208 16.026 21.208 C 13.135 21.208 '
    "10.792 18.865 10.792 15.974 C 10.792 13.083 13.135 10.74 16.026 10.74 C 18.917 10.74 "
    '21.26 13.083 21.26 15.974 C 21.26 17.37 21.26 18.97 21.26 21.016"/>'
    '<circle cx="20.31" cy="4.16" r="3.2" fill="#00274C" stroke="none"/></svg>'
)


# ----------------------------------------------------------------- arrows
ARROW_W = 3.5
HEAD_L = 15
HEAD_W = 16


def _head(x: float, y: float, direction: str, color: str) -> str:
    l, w = HEAD_L, HEAD_W / 2
    if direction == "right":
        pts = f"{x},{y} {x - l},{y - w} {x - l},{y + w}"
    elif direction == "left":
        pts = f"{x},{y} {x + l},{y - w} {x + l},{y + w}"
    elif direction == "down":
        pts = f"{x},{y} {x - w},{y - l} {x + w},{y - l}"
    else:  # up
        pts = f"{x},{y} {x - w},{y + l} {x + w},{y + l}"
    return f'<polygon points="{pts}" fill="{color}"/>'


def svg(w: float, h: float, body: str, **props: object) -> str:
    style = css(display="block", flex="none", overflow="visible", **props)
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true" '
        f'style="{style}">{body}</svg>'
    )


def line(points: list[tuple[float, float]], color: str = NAVY, dashed: bool = False) -> str:
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="9 7"' if dashed else ""
    return (
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{ARROW_W}" '
        f'stroke-linejoin="round"{dash}/>'
    )


def arrow_h(w: float, h: float = 32, direction: str = "right", color: str = NAVY,
            dashed: bool = False, **props: object) -> str:
    y = h / 2
    if direction == "right":
        body = line([(2, y), (w - HEAD_L + 1, y)], color, dashed) + _head(w - 1, y, "right", color)
    else:
        body = line([(w - 2, y), (HEAD_L - 1, y)], color, dashed) + _head(1, y, "left", color)
    return svg(w, h, body, **props)


def arrow_v(h: float, w: float = 32, direction: str = "down", color: str = NAVY,
            x: float | None = None, dashed: bool = False, **props: object) -> str:
    cx = w / 2 if x is None else x
    if direction == "down":
        body = line([(cx, 2), (cx, h - HEAD_L + 1)], color, dashed) + _head(cx, h - 1, "down", color)
    else:
        body = line([(cx, h - 2), (cx, HEAD_L - 1)], color, dashed) + _head(cx, 1, "up", color)
    return svg(w, h, body, **props)


def path_arrow(points: list[tuple[float, float]], direction: str, color: str = NAVY,
               dashed: bool = False) -> str:
    """A polyline whose last segment ends in an arrowhead at the final point."""
    *rest, (ex, ey) = points
    l = HEAD_L - 1
    stop = {"right": (ex - l, ey), "left": (ex + l, ey), "down": (ex, ey - l), "up": (ex, ey + l)}[direction]
    return line([*rest, stop], color, dashed) + _head(ex, ey, direction, color)


# ------------------------------------------------------------ components
def badge(n: str, size: int = 38, bg: str = NAVY, fg: str = "#FFFFFF") -> str:
    return div(
        n,
        width=size, height=size, border_radius="50%", background=bg, color=fg,
        font_weight=800, font_size=round(size * 0.55), display="flex",
        align_items="center", justify_content="center", flex="none", line_height=1,
    )


def pill(text: str, fg: str, bg: str, icon_name: str | None = None, border: str | None = None,
         size: int = 18) -> str:
    inner = (icon(icon_name, size=size + 1, color=fg) if icon_name else "") + span(text)
    return div(
        inner,
        display="inline-flex", align_items="center", gap=7, padding="4px 12px 4px 10px",
        border_radius=999, background=bg, color=fg, font_size=size, font_weight=700,
        line_height=1.2, border=border, white_space="nowrap", flex="none",
    )


def header(title: str, subtitle: str, sub_width: int = 1180) -> str:
    left = div(
        tag("h1", title, margin=0, font_size=46, line_height=1.1, font_weight=800,
            color=NAVY, letter_spacing="-0.02em")
        + tag("p", subtitle, margin="10px 0 0", font_size=22, line_height=1.45,
              color=TEXT2, max_width=sub_width),
    )
    right = div(
        BRAND_MARK + span("Axcess", font_size=24, font_weight=800, color=NAVY,
                          letter_spacing="-0.01em"),
        display="flex", align_items="center", gap=10, flex="none", padding_top=6,
    )
    return div(left + right, display="flex", justify_content="space-between",
               align_items="flex-start", gap=40)


def bullet_item(text: str, size: int = 20, color: str = INK, dot: str = NAVY,
                gap: int = 12, line_height: float = 1.35) -> str:
    dot_top = round(size * line_height / 2 - 4)
    return div(
        div("", width=8, height=8, border_radius="50%", background=dot, flex="none",
            margin_top=dot_top)
        + div(text, font_size=size, line_height=line_height, color=color, min_width=0),
        display="flex", align_items="flex-start", gap=gap,
    )


def icon_item(icon_name: str, text: str, size: int = 20, color: str = INK,
              icon_color: str = NAVY, gap: int = 12, line_height: float = 1.35,
              icon_size: int = 24) -> str:
    top = max(0, round((size * line_height - icon_size) / 2))
    return div(
        div(icon(icon_name, size=icon_size, color=icon_color), margin_top=top, flex="none")
        + div(text, font_size=size, line_height=line_height, color=color, min_width=0),
        display="flex", align_items="flex-start", gap=gap,
    )


def page(title: str, w: int, h: int, content: str, padding: str = "40px 56px 36px") -> str:
    root = div(
        content,
        width=w, height=h, box_sizing="border-box", padding=padding, position="relative",
        overflow="hidden", background=BG, font_family=SANS, color=INK,
    )
    props = '{"$preview":{"width":%d,"height":%d}}' % (w, h)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{title}</title>"
        '<script src="./support.js"></script></head><body><x-dc><helmet>'
        f"{FONT_LINK}{PAGE_STYLE}</helmet>{root}</x-dc>"
        f"<script type=\"text/x-dc\" data-dc-script data-props='{props}'>"
        "class Component extends DCLogic { renderVals() { return {}; } }</script>"
        "</body></html>\n"
    )
