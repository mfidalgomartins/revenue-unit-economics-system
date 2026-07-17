"""Cross-surface design-token consistency.

The chart pack and PDF report import src/design/tokens.py directly; the
dashboard defines the same palette as CSS custom properties in its template.
These tests pin all three surfaces to the same values so a color change in
one place either propagates everywhere or fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.design import tokens
from src.governance import build_analytical_report as report
from src.visualization import build_chart_pack as charts

DASHBOARD_TEMPLATE = (
    Path(__file__).resolve().parents[1] / "src" / "dashboard_builder" / "assets" / "dashboard.html"
)
REPORT_CSS = Path(__file__).resolve().parents[1] / "src" / "governance" / "assets" / "report.css"


def _custom_properties(css_block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", css_block))


def _block(css: str, start_marker: str) -> str:
    start = css.index(start_marker)
    return css[start : css.index("}", start)]


def test_dashboard_light_theme_matches_tokens() -> None:
    html = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    declared = _custom_properties(_block(html, ":root"))
    for name, expected in tokens.LIGHT.items():
        assert declared.get(name) == expected, f"--{name}: {declared.get(name)} != {expected}"


def test_dashboard_dark_theme_matches_tokens() -> None:
    html = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    declared = _custom_properties(_block(html, 'body[data-theme="dark"]'))
    for name, expected in tokens.DARK.items():
        assert declared.get(name) == expected, f"--{name}: {declared.get(name)} != {expected}"


def test_chart_pack_uses_the_shared_tokens() -> None:
    assert charts.INK is tokens.INK
    assert charts.POSITIVE is tokens.POSITIVE
    assert charts.NEGATIVE is tokens.NEGATIVE
    assert charts.WARNING is tokens.WARNING


def test_report_uses_the_shared_tokens() -> None:
    assert report.INK is tokens.INK
    assert report.ACCENT is tokens.POSITIVE
    assert report.NEG is tokens.NEGATIVE
    assert report.WARN is tokens.WARNING


def test_report_css_is_tokenized_not_hardcoded() -> None:
    css = REPORT_CSS.read_text(encoding="utf-8")
    assert "$INK" in css and "$POSITIVE" in css
    for hex_value in (tokens.INK, tokens.POSITIVE, tokens.NEGATIVE, tokens.WARNING):
        assert hex_value not in css, f"{hex_value} hardcoded in report.css"
