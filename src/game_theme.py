"""
Read the commander's real Elite Dangerous HUD colours so the app can match them.

Two sources, tried in order:

1. **EDHM-UI** (`%USERPROFILE%\\EDHM_UI\\ODYSS\\EDHM\\EDHM-Ini\\ThemeSettings.json`)
   — the theme actually applied to the game. Colours are stored as signed 32-bit
   ARGB integers against ~150 named HUD elements; the palette is taken from the
   most-used ones.

2. **The game's own GUIColour matrix**
   (`…\\Frontier Developments\\Elite Dangerous\\Options\\Graphics\\GraphicsConfigurationOverride.xml`)
   — the classic re-tint: a 3x3 matrix multiplied against the default HUD orange.
   An identity matrix means the player hasn't re-tinted, so it is ignored.

Returns None when neither source says anything, and the UI keeps its built-in
palette. Standard library only.
"""

from __future__ import annotations

import colorsys
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter

# The HUD orange the GUIColour matrix multiplies against.
ED_BASE_HUD = (1.0, 0.44, 0.06)

# Near-white / near-grey entries carry no hue, so they say nothing about theme.
_MIN_SATURATION = 0.25


def _argb_to_rgb(value: int) -> tuple[int, int, int]:
    u = value + 4294967296 if value < 0 else value
    return ((u >> 16) & 255, (u >> 8) & 255, u & 255)


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _saturation(rgb) -> float:
    r, g, b = (c / 255 for c in rgb)
    return colorsys.rgb_to_hls(r, g, b)[2]


def _lightness(rgb) -> float:
    r, g, b = (c / 255 for c in rgb)
    return colorsys.rgb_to_hls(r, g, b)[1]


def _mix(rgb, target, t: float):
    return tuple(c + (o - c) * t for c, o in zip(rgb, target))


# --------------------------------------------------------------------------- #
#  Source 1 - EDHM-UI applied theme
# --------------------------------------------------------------------------- #
def _edhm_theme_path() -> str:
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(profile, "EDHM_UI", "ODYSS", "EDHM", "EDHM-Ini",
                        "ThemeSettings.json")


def _collect_colors(node, out: list) -> None:
    """EDHM nests colour entries a few different ways; walk the whole tree."""
    if isinstance(node, dict):
        if node.get("ValueType") == "Color" and isinstance(node.get("Value"), int):
            out.append(node["Value"])
        for v in node.values():
            _collect_colors(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_colors(v, out)


def read_edhm_theme(path: str | None = None) -> dict | None:
    path = path or _edhm_theme_path()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None

    raw: list[int] = []
    _collect_colors(data, raw)
    if not raw:
        return None

    # Ignore greys/whites, which every theme shares and which would drown out
    # the accent.
    ranked = [
        (rgb, n) for rgb, n in
        Counter(_argb_to_rgb(v) for v in raw).most_common()
        if _saturation(rgb) >= _MIN_SATURATION and 0.12 <= _lightness(rgb) <= 0.92
    ]
    if not ranked:
        return None

    # Group by hue and take the family the theme actually leans on. Every theme
    # keeps ED's fixed status colours (orange target, red warning), so simply
    # taking the two most-used colours can pair a purple theme with a stray
    # orange. The dominant family, weighted by use, is the real accent.
    families: dict[int, list] = {}
    for rgb, n in ranked:
        hue = colorsys.rgb_to_hls(*(c / 255 for c in rgb))[0]
        families.setdefault(int(hue * 12) % 12, []).append((rgb, n))
    family = max(families.values(), key=lambda members: sum(n for _, n in members))

    # Within the family: the most vivid colour leads. The supporting colour is
    # the next most-USED one, not simply the lightest - a theme's near-white
    # highlight is too pale to read as an accent.
    primary = max(family, key=lambda m: _saturation(m[0]))[0]
    rest = [(rgb, n) for rgb, n in family
            if rgb != primary and _lightness(rgb) <= 0.80]
    secondary = (max(rest, key=lambda m: m[1])[0]
                 if rest else _mix(primary, (255, 255, 255), 0.35))

    return _palette(primary, secondary, source="edhm",
                    name=os.path.basename(os.path.dirname(path)))


def _hue_gap(a, b) -> float:
    ha = colorsys.rgb_to_hls(*(c / 255 for c in a))[0]
    hb = colorsys.rgb_to_hls(*(c / 255 for c in b))[0]
    d = abs(ha - hb)
    return min(d, 1 - d)


# --------------------------------------------------------------------------- #
#  Source 2 - the game's GUIColour matrix
# --------------------------------------------------------------------------- #
def _graphics_override_path() -> str:
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local, "Frontier Developments", "Elite Dangerous",
                        "Options", "Graphics", "GraphicsConfigurationOverride.xml")


def _row(text: str | None) -> list[float]:
    if not text:
        return []
    return [float(x) for x in re.findall(r"-?\d*\.?\d+", text)][:3]


def read_gui_matrix(path: str | None = None) -> dict | None:
    path = path or _graphics_override_path()
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None

    node = root.find(".//GUIColour/Default")
    if node is None:
        return None
    m = [_row(node.findtext(t)) for t in ("MatrixRed", "MatrixGreen", "MatrixBlue")]
    if any(len(r) != 3 for r in m):
        return None

    identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    if all(abs(m[i][j] - identity[i][j]) < 1e-6 for i in range(3) for j in range(3)):
        return None          # not re-tinted - nothing to learn here

    # The matrix maps the base HUD colour to the player's chosen one.
    r, g, b = ED_BASE_HUD
    out = (
        (m[0][0] * r + m[1][0] * g + m[2][0] * b) * 255,
        (m[0][1] * r + m[1][1] * g + m[2][1] * b) * 255,
        (m[0][2] * r + m[1][2] * g + m[2][2] * b) * 255,
    )
    primary = tuple(max(0, min(255, c)) for c in out)
    if _saturation(primary) < 0.08:
        return None
    return _palette(primary, _mix(primary, (255, 255, 255), 0.35),
                    source="guicolour", name="GUIColour matrix")


# --------------------------------------------------------------------------- #
#  Palette construction
# --------------------------------------------------------------------------- #
def _palette(primary, secondary, source: str, name: str) -> dict:
    """Derive the handful of shades the stylesheet needs from two colours."""
    return {
        "source": source,
        "name": name,
        "primary": _hex(primary),
        "primaryRgb": [int(round(c)) for c in primary],
        "primaryLight": _hex(_mix(primary, (255, 255, 255), 0.45)),
        "primaryText": _hex(_mix(primary, (255, 255, 255), 0.65)),
        "secondary": _hex(secondary),
        "secondaryRgb": [int(round(c)) for c in secondary],
        "secondaryDim": _hex(_mix(secondary, (0, 0, 0), 0.40)),
        "text": _hex(_mix(primary, (255, 255, 255), 0.88)),
        "textDim": _hex(_mix(primary, (150, 150, 150), 0.72)),
    }


def detect(force_source: str | None = None) -> dict | None:
    """Best available game palette, or None to keep the app's built-in one."""
    if force_source in (None, "edhm"):
        pal = read_edhm_theme()
        if pal:
            return pal
    if force_source in (None, "guicolour"):
        return read_gui_matrix()
    return None


if __name__ == "__main__":
    pal = detect()
    if not pal:
        print("No game theme detected - the app keeps its built-in palette.")
    else:
        print(f"source   : {pal['source']} ({pal['name']})")
        for k in ("primary", "primaryLight", "primaryText",
                  "secondary", "secondaryDim", "text", "textDim"):
            print(f"{k:13s}: {pal[k]}")
