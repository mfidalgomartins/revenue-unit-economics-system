"""Canonical design tokens shared by every visual surface.

The chart pack and the PDF report import these constants directly; the
dashboard defines the same values as CSS custom properties in its template,
and tests/test_design_tokens.py asserts the two stay identical. Change a
color here (and in the dashboard template) and every surface follows.
"""

from __future__ import annotations

# Core ink/neutral scale (light theme) — Apple-style warm near-black.
INK = "#1d1d1f"
INK_2 = "#424245"
MUTED = "#6e6e73"
SUBTLE = "#86868b"
HAIRLINE = "#e6e6ea"
HAIRLINE_STRONG = "#d2d2d7"
SURFACE = "#ffffff"
SURFACE_2 = "#f5f5f7"
SURFACE_3 = "#ececef"
CANVAS = "#fbfbfd"

# Semantic signal colors. POSITIVE clears WCAG AA (4.5:1) on white.
POSITIVE = "#1a7f37"
POSITIVE_SOFT = "#8fcfa3"
NEGATIVE = "#d70015"
NEGATIVE_SOFT = "#eaa6a6"
WARNING = "#b25000"
ACCENT = "#0071e3"

# CSS custom-property maps mirrored by the dashboard template's :root and
# [data-theme="dark"] blocks. The consistency test compares against these.
LIGHT: dict[str, str] = {
    "bg": CANVAS,
    "surface": SURFACE,
    "surface-2": SURFACE_2,
    "surface-3": SURFACE_3,
    "hairline": HAIRLINE,
    "hairline-strong": HAIRLINE_STRONG,
    "ink": INK,
    "ink-2": INK_2,
    "muted": MUTED,
    "subtle": SUBTLE,
    "accent": ACCENT,
    "positive": POSITIVE,
    "negative": NEGATIVE,
    "warning": WARNING,
}

DARK: dict[str, str] = {
    "bg": "#000000",
    "surface": "#1c1c1e",
    "surface-2": "#2c2c2e",
    "surface-3": "#3a3a3c",
    "hairline": "#38383a",
    "hairline-strong": "#48484a",
    "ink": "#f5f5f7",
    "ink-2": "#d1d1d6",
    "muted": "#98989d",
    "subtle": "#6e6e73",
    "accent": "#0a84ff",
    "positive": "#30d158",
    "negative": "#ff453a",
    "warning": "#ff9f0a",
}
