from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import src.governance.build_analytical_report as analytical_report
from PIL import Image

REPORT_CSS = (
    Path(__file__).resolve().parents[1] / "src" / "governance" / "assets" / "report.css"
)
CHARTS = Path(__file__).resolve().parents[1] / "outputs" / "charts"


def test_build_html_uses_current_payback_and_cohort_semantics() -> None:
    html = analytical_report.build_html()

    assert "Synthetic Case Study" in html
    assert "&gt;24" in html
    assert "Signup activity" in html
    assert "Retained from M0" in html
    assert "annual contribution" not in html
    assert "lifetime_days" not in html


def test_build_html_handles_absent_cost_exception_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_csv = analytical_report.pd.read_csv

    def read_csv_without_cost_exception(
        path: str | Path, *args: object, **kwargs: object
    ) -> pd.DataFrame:
        frame = original_read_csv(path, *args, **kwargs)
        if Path(path).name == "data_quality_issues.csv":
            return frame.loc[frame["check_name"] != "cost_exceeds_revenue"].copy()
        return frame

    monkeypatch.setattr(analytical_report.pd, "read_csv", read_csv_without_cost_exception)

    html = analytical_report.build_html()

    assert "0 transactions (0.00%) where cost" in html


def test_report_uses_consulting_grade_editorial_system() -> None:
    css = REPORT_CSS.read_text(encoding="utf-8")

    assert "size: letter" in css.lower()
    assert '"Iowan Old Style"' in css
    assert ".cover-art" in css
    assert ".chapter-head" in css
    assert "border-left:3px" not in css.replace(" ", "")
    assert ".chart {" in css and "border:0" in css.replace(" ", "")


def test_report_embeds_original_ribbon_visual_without_external_assets() -> None:
    html = analytical_report.build_html()

    assert html.count('class="ribbon-art"') == 4
    assert html.count("<path") >= 48
    assert "http://" not in analytical_report.RIBBON_SVG
    assert "https://" not in analytical_report.RIBBON_SVG


def test_report_recolors_charts_in_memory_without_modifying_chart_pack() -> None:
    chart_path = CHARTS / "01_growth_quality.png"
    original = chart_path.read_bytes()

    embedded = base64.b64decode(analytical_report._img(chart_path.name).split(",", 1)[1])

    assert embedded != original
    assert chart_path.read_bytes() == original
    with Image.open(BytesIO(embedded)) as image:
        assert image.format == "PNG"


def test_report_has_executive_and_chapter_pacing() -> None:
    html = analytical_report.build_html()

    assert 'class="break executive"' in html
    assert html.count('class="chapter-head"') == 3


def test_toc_text_normalization_survives_print_line_breaks_and_kerning() -> None:
    expected = analytical_report._normalize_pdf_text(
        "Recommendations and action priorities"
    )

    assert analytical_report._normalize_pdf_text(
        "Recommendations and\naction priorities"
    ) == expected
    assert analytical_report._normalize_pdf_text(
        "Recommendations andaction priorities"
    ) == expected


def test_chapter_toc_markers_include_the_visible_section_number() -> None:
    assert analytical_report.TOC_SEARCH_KEYS["5"] == "Findings\n5"
    assert analytical_report.TOC_SEARCH_KEYS["9"] == "Appendix\n9"
