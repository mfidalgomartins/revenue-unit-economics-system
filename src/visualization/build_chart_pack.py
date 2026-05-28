"""Build the curated showcase chart pack written to outputs/Graphs/.

Six charts, deliberately chosen — no spam, one chart per executive question:

    1. growth_quality.png         — revenue and contribution margin trend
    2. margin_rate.png            — monthly contribution margin %
    3. cohort_retention.png       — median revenue retention by cohort age
    4. channel_economics.png      — LTV vs CAC scatter with efficiency thresholds
    5. segment_profitability.png  — contribution margin $ and margin % by segment
    6. scenario_envelope.png      — best / base / worst case scenario contribution

Palette stays in lock-step with the dashboard: ink + a single green for
margin signals and a single red for negative deltas or inefficient cuts.
Output is publication-ready (1600 × 960 @ 144 dpi) and the same look-and-feel
across the whole pack.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUT_DIR = PROJECT_ROOT / "outputs" / "Graphs"

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

INK = "#0a0a0a"
INK_2 = "#262626"
MUTED = "#737373"
SUBTLE = "#a3a3a3"
HAIRLINE = "#ececec"
POSITIVE = "#15803d"
NEGATIVE = "#b91c1c"
WARNING = "#b45309"
SURFACE_2 = "#fafafa"

FONT_STACK = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]


def _apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 144,
            "savefig.dpi": 144,
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.titlesize": 13,
            "axes.titleweight": 600,
            "axes.titlepad": 14,
            "axes.labelsize": 10,
            "axes.labelweight": 500,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": HAIRLINE,
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "xtick.major.pad": 6,
            "ytick.major.pad": 4,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "legend.labelcolor": INK_2,
            "lines.linewidth": 1.6,
            "lines.solid_capstyle": "round",
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "font.size": 10,
        }
    )


def _new_fig(width: float = 11.0, height: float = 6.0):
    fig, ax = plt.subplots(figsize=(width, height))
    return fig, ax


def _money(ax, *, axis: str = "y", short: bool = True) -> None:
    def fmt(x, _):
        if not np.isfinite(x):
            return ""
        a = abs(x)
        sign = "-" if x < 0 else ""
        if short:
            if a >= 1_000_000_000:
                return f"{sign}${a / 1e9:.1f}B"
            if a >= 1_000_000:
                return f"{sign}${a / 1e6:.1f}M"
            if a >= 1_000:
                return f"{sign}${a / 1e3:.0f}K"
        return f"{sign}${a:,.0f}"

    formatter = mticker.FuncFormatter(fmt)
    if axis == "y":
        ax.yaxis.set_major_formatter(formatter)
    else:
        ax.xaxis.set_major_formatter(formatter)


def _pct(ax, *, axis: str = "y", decimals: int = 0) -> None:
    fmt = mticker.PercentFormatter(xmax=1.0, decimals=decimals)
    if axis == "y":
        ax.yaxis.set_major_formatter(fmt)
    else:
        ax.xaxis.set_major_formatter(fmt)


def _suptitle(fig, title: str, subtitle: str) -> None:
    fig.text(
        0.045, 0.945, title,
        ha="left", fontsize=15, fontweight=600, color=INK,
    )
    fig.text(
        0.045, 0.895, subtitle,
        ha="left", fontsize=10, color=MUTED,
    )


def _footer(fig, text: str) -> None:
    fig.text(
        0.045, 0.025,
        text,
        ha="left", fontsize=8, color=SUBTLE, style="italic",
    )


def _save(fig, name: str, *, top: float = 0.83, bottom: float = 0.14) -> Path:
    out = OUT_DIR / f"{name}.png"
    fig.subplots_adjust(top=top, bottom=bottom, left=0.08, right=0.96)
    # No bbox_inches="tight" — it crops the title/footer text and squashes the layout.
    fig.savefig(out, dpi=144, facecolor="white")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def chart_growth_quality() -> Path:
    """Revenue and contribution margin on a shared monthly axis."""
    df = pd.read_csv(TABLES_DIR / "monthly_revenue_health.csv", parse_dates=["month"])
    fig, ax = _new_fig(11, 5.8)

    ax.plot(df["month"], df["total_revenue"], color=INK, linewidth=1.8, label="Revenue")
    ax.plot(
        df["month"],
        df["contribution_margin"],
        color=POSITIVE,
        linewidth=1.8,
        label="Contribution margin",
    )
    ax.fill_between(df["month"], df["contribution_margin"], color=POSITIVE, alpha=0.06)

    ax.set_ylim(bottom=0)
    _money(ax)
    ax.set_ylabel("USD per month")
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.0))

    _suptitle(
        fig,
        "Is growth converting into margin?",
        "Monthly revenue and contribution margin, full coverage window.",
    )
    _footer(fig, "Source: outputs/tables/monthly_revenue_health.csv  ·  synthetic data")
    return _save(fig, "01_growth_quality")


def chart_margin_rate() -> Path:
    """Contribution margin % over time with a quality-floor reference."""
    df = pd.read_csv(TABLES_DIR / "monthly_revenue_health.csv", parse_dates=["month"])
    fig, ax = _new_fig(11, 5.0)

    ax.plot(
        df["month"],
        df["contribution_margin_pct"],
        color=INK,
        linewidth=1.8,
    )

    ax.axhline(0.30, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.text(
        0.99, 0.30 + 0.005,
        "30% quality floor",
        transform=ax.get_yaxis_transform(),
        ha="right", va="bottom",
        color=POSITIVE, fontsize=9,
    )

    ax.set_ylim(0.20, 0.40)
    _pct(ax)
    ax.set_ylabel("Contribution margin / revenue")

    _suptitle(
        fig,
        "Margin quality across the window",
        "Monthly contribution margin rate vs the 30% quality floor.",
    )
    _footer(fig, "Source: outputs/tables/monthly_revenue_health.csv  ·  synthetic data")
    return _save(fig, "02_margin_rate")


def chart_cohort_retention() -> Path:
    """Median revenue retention by months since signup."""
    df = pd.read_csv(TABLES_DIR / "cohort_retention_summary.csv")
    df = df.sort_values("months_since_cohort")

    fig, ax = _new_fig(11, 5.0)

    ax.plot(
        df["months_since_cohort"],
        df["median_revenue_retention"],
        color=INK,
        linewidth=1.8,
        marker="o",
        markersize=3.5,
        markerfacecolor=INK,
        markeredgecolor="white",
        markeredgewidth=0.6,
    )

    # Annotate the 6- and 12-month marks if present.
    for m in (6, 12):
        if m in df["months_since_cohort"].values:
            y = float(df.loc[df["months_since_cohort"] == m, "median_revenue_retention"].iloc[0])
            ax.annotate(
                f"M{m}: {y:.0%}",
                xy=(m, y),
                xytext=(8, 8),
                textcoords="offset points",
                fontsize=9,
                color=INK_2,
                weight=500,
            )
            ax.scatter([m], [y], s=28, color=NEGATIVE, zorder=3)

    ax.set_ylim(0, 1.05)
    ax.set_xlim(0, df["months_since_cohort"].max())
    _pct(ax)
    ax.set_xlabel("Months since signup")
    ax.set_ylabel("Median revenue retention")

    _suptitle(
        fig,
        "How fast do cohorts decay?",
        "Median revenue retention across observed cohorts.",
    )
    _footer(fig, "Source: outputs/tables/cohort_retention_summary.csv  ·  synthetic data")
    return _save(fig, "03_cohort_retention")


def chart_channel_economics() -> Path:
    """LTV vs CAC scatter with efficiency thresholds."""
    df = pd.read_csv(TABLES_DIR / "unit_economics_channel_diagnostics.csv")

    fig, ax = _new_fig(11, 6.0)

    colors = {
        "efficient": POSITIVE,
        "borderline": WARNING,
        "inefficient": NEGATIVE,
    }
    df["_color"] = df["efficiency_status"].map(colors).fillna(MUTED)

    ax.scatter(
        df["CAC"],
        df["average_LTV"],
        s=110,
        c=df["_color"],
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )

    for _, row in df.iterrows():
        ax.annotate(
            row["acquisition_channel"],
            xy=(row["CAC"], row["average_LTV"]),
            xytext=(8, 6),
            textcoords="offset points",
            fontsize=9,
            color=INK_2,
            weight=500,
        )

    # 3× and 1× reference lines.
    cac_max = max(df["CAC"].max() * 1.15, 1.0)
    xs = np.linspace(0, cac_max, 100)
    ax.plot(xs, 3 * xs, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.plot(xs, xs, color=NEGATIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.text(cac_max * 0.98, 3 * cac_max * 0.98, "LTV / CAC = 3", ha="right", va="bottom", color=POSITIVE, fontsize=9)
    ax.text(cac_max * 0.98, cac_max * 0.98, "LTV / CAC = 1", ha="right", va="bottom", color=NEGATIVE, fontsize=9)

    ax.set_xlim(0, cac_max)
    ax.set_ylim(0, max(df["average_LTV"].max() * 1.15, 1.0))
    _money(ax, axis="x")
    _money(ax, axis="y")
    ax.set_xlabel("Customer Acquisition Cost (CAC)")
    ax.set_ylabel("Average LTV per acquired customer")

    _suptitle(
        fig,
        "Which acquisition channels deserve budget?",
        "Channel LTV against CAC, with efficiency thresholds at 1× and 3×.",
    )
    _footer(fig, "Source: outputs/tables/unit_economics_channel_diagnostics.csv  ·  synthetic data")
    return _save(fig, "04_channel_economics")


def chart_segment_profitability() -> Path:
    """Contribution margin $ and margin % by segment."""
    df = pd.read_csv(TABLES_DIR / "segment_profitability.csv")
    df = df[df["dimension_type"] == "segment"].copy()
    order = ["Startup", "SMB", "Mid-Market", "Enterprise"]
    df["dimension_value"] = pd.Categorical(df["dimension_value"], categories=order, ordered=True)
    df = df.sort_values("dimension_value").reset_index(drop=True)

    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(11, 5.4), gridspec_kw={"wspace": 0.32}
    )

    # Left: contribution margin $
    bars = ax_left.bar(
        df["dimension_value"].astype(str),
        df["contribution_margin"],
        color=INK,
        width=0.55,
    )
    _money(ax_left)
    ax_left.set_ylabel("Contribution margin (USD)")
    ax_left.set_title("Margin dollars by segment", loc="left", pad=10, fontsize=11, fontweight=600)
    for bar, value in zip(bars, df["contribution_margin"]):
        ax_left.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"${value / 1e6:.1f}M",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK_2,
            weight=500,
        )

    # Right: margin %
    colors = [POSITIVE if v >= 0.30 else (WARNING if v >= 0.20 else NEGATIVE) for v in df["margin_pct"]]
    bars = ax_right.bar(
        df["dimension_value"].astype(str),
        df["margin_pct"],
        color=colors,
        width=0.55,
    )
    ax_right.axhline(0.30, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax_right.set_ylim(0, max(df["margin_pct"].max() * 1.2, 0.4))
    _pct(ax_right)
    ax_right.set_ylabel("Margin rate")
    ax_right.set_title("Margin rate by segment", loc="left", pad=10, fontsize=11, fontweight=600)
    for bar, value in zip(bars, df["margin_pct"]):
        ax_right.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.0%}",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK_2,
            weight=500,
        )

    fig.text(0.045, 0.945, "Where does margin concentrate?",
             ha="left", fontsize=15, fontweight=600, color=INK)
    fig.text(0.045, 0.895,
             "Contribution margin dollars and margin rate by customer segment.",
             ha="left", fontsize=10, color=MUTED)
    _footer(fig, "Source: outputs/tables/segment_profitability.csv  ·  synthetic data")

    fig.subplots_adjust(top=0.81, bottom=0.14, left=0.07, right=0.97)
    out = OUT_DIR / "05_segment_profitability.png"
    fig.savefig(out, dpi=144, facecolor="white")
    plt.close(fig)
    return out


def chart_scenario_envelope() -> Path:
    """Baseline vs scenario contribution under best / base / worst stress cases."""
    stress = pd.read_csv(TABLES_DIR / "scenario_stress_test_summary.csv")
    baseline = pd.read_csv(TABLES_DIR / "scenario_outcomes_summary.csv")
    baseline_value = float(baseline["baseline_contribution_est"].iloc[0])

    stress["scenario_name"] = pd.Categorical(
        stress["scenario_name"],
        categories=["worst_case", "base_case", "best_case"],
        ordered=True,
    )
    stress = stress.sort_values("scenario_name").reset_index(drop=True)

    labels = ["Baseline"] + [s.replace("_", " ").title() for s in stress["scenario_name"].astype(str)]
    values = [baseline_value] + stress["scenario_contribution_est"].tolist()
    colors = [MUTED, NEGATIVE, INK, POSITIVE]

    fig, ax = _new_fig(11, 5.4)
    bars = ax.bar(labels, values, color=colors, width=0.55)
    ax.axhline(baseline_value, color=MUTED, linewidth=0.9, linestyle=(0, (4, 4)))

    for bar, value in zip(bars, values):
        delta = value - baseline_value
        label_top = f"${value / 1e6:.1f}M"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            label_top,
            ha="center",
            va="bottom",
            fontsize=10,
            color=INK,
            weight=600,
        )
        if delta != 0:
            sign = "+" if delta > 0 else "−"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 0.5,
                f"{sign}${abs(delta) / 1e6:.1f}M",
                ha="center",
                va="center",
                fontsize=10,
                color="white",
                weight=600,
            )

    ax.set_ylim(0, max(values) * 1.18)
    _money(ax)
    ax.set_ylabel("Contribution margin (USD)")

    _suptitle(
        fig,
        "Scenario envelope around the reallocation policy",
        "Contribution under the recommended reallocation, stress-tested by CAC and LTV elasticity.",
    )
    _footer(
        fig,
        "Source: outputs/tables/scenario_outcomes_summary.csv, scenario_stress_test_summary.csv  ·  synthetic data",
    )
    return _save(fig, "06_scenario_envelope")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _apply_style()

    paths = [
        chart_growth_quality(),
        chart_margin_rate(),
        chart_cohort_retention(),
        chart_channel_economics(),
        chart_segment_profitability(),
        chart_scenario_envelope(),
    ]

    index = OUT_DIR / "README.md"
    lines = [
        "# Chart pack",
        "",
        "Curated showcase charts. Each one answers a single executive question — no chart spam.",
        "",
    ]
    questions = [
        "Is growth converting into margin?",
        "Is the margin rate holding above the quality floor?",
        "How fast do cohorts decay after signup?",
        "Which acquisition channels deserve budget?",
        "Where does margin concentrate across segments?",
        "How wide is the scenario envelope around the reallocation policy?",
    ]
    for path, question in zip(paths, questions):
        lines.append(f"- `{path.name}` — {question}")
    lines.append("")
    lines.append("Regenerate with `python src/visualization/build_chart_pack.py`.")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Chart pack written:")
    for path in paths:
        print(f"  {path.relative_to(PROJECT_ROOT)}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
