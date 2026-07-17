"""Build the publication chart pack written to outputs/charts/.

One chart per analytical question, in the narrative order of the report:

    01 growth_quality            revenue and contribution margin trend
    02 margin_rate               monthly contribution margin %
    03 revenue_growth_mom        month-on-month revenue variance
    04 active_customers_arpu     active base and revenue per active customer
    05 revenue_decomposition     volume / monetization / mix waterfall
    06 cohort_retention          median revenue retention by cohort age
    07 cohort_heatmap            revenue retention triangle by cohort
    08 channel_economics         LTV vs CAC scatter with efficiency thresholds
    09 channel_ltv_cac_ranking   LTV/CAC ranked across channels
    10 channel_allocation_gap    spend share vs contribution share
    11 segment_profitability     contribution margin $ and margin % by segment
    12 region_profitability      contribution margin and rate by region
    13 product_margin            margin rate and revenue by product type
    14 revenue_concentration     Lorenz curve of customer revenue
    15 revenue_distribution      distribution of customer lifetime revenue
    16 revenue_lifetime_corr     revenue against transaction activity span
    17 reallocation_waterfall    contribution bridge of the reallocation policy
    18 scenario_envelope         contribution under three assumption sets
    19 scenario_seed_stability   uplift across deterministic seeds

Palette stays in lock-step with the dashboard: ink for the primary series, a
single green for margin / efficient signals, a single red for negative deltas
or value-destructive channels, amber for borderline. Output is publication
grade (1600 x 960 @ 144 dpi) with a uniform look across the whole pack.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

# Palette comes from the shared design tokens so the chart pack, dashboard,
# and PDF report consume the same Python palette.
from src.design.tokens import (
    HAIRLINE,
    INK,
    INK_2,
    MUTED,
    NEGATIVE,
    POSITIVE,
    POSITIVE_SOFT,
    SUBTLE,
    SURFACE_2,
    WARNING,
)
from src.governance.metric_registry import MARGIN_QUALITY_FLOOR
from src.paths import PROJECT_ROOT
from src.visualization.chart_manifest import CHART_METADATA, expected_chart_files

TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUT_DIR = PROJECT_ROOT / "outputs" / "charts"

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

FONT_STACK = [
    "SF Pro Display",
    "SF Pro Text",
    "Helvetica Neue",
    "Helvetica",
    "Arial",
    "DejaVu Sans",
]


def _apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 144,
            "savefig.dpi": 144,
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


def _new_fig(width: float = 11.0, height: float = 6.0) -> tuple[Figure, Axes]:
    fig, ax = plt.subplots(figsize=(width, height))
    return fig, ax


def _money(ax: Axes, *, axis: str = "y", short: bool = True) -> None:
    def fmt(x: float, _: object) -> str:
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
                thousands = a / 1e3
                decimals = 0 if np.isclose(thousands, round(thousands)) else 1
                return f"{sign}${thousands:.{decimals}f}K"
        return f"{sign}${a:,.0f}"

    formatter = mticker.FuncFormatter(fmt)
    if axis == "y":
        ax.yaxis.set_major_formatter(formatter)
    else:
        ax.xaxis.set_major_formatter(formatter)


def _pct(ax: Axes, *, axis: str = "y", decimals: int = 0) -> None:
    fmt = mticker.PercentFormatter(xmax=1.0, decimals=decimals)
    if axis == "y":
        ax.yaxis.set_major_formatter(fmt)
    else:
        ax.xaxis.set_major_formatter(fmt)


def _suptitle(fig: Figure, title: str, subtitle: str) -> None:
    fig.text(0.045, 0.945, title, ha="left", fontsize=15, fontweight=600, color=INK)
    fig.text(0.045, 0.895, subtitle, ha="left", fontsize=10, color=MUTED)


def _footer(fig: Figure, text: str) -> None:
    fig.text(0.045, 0.025, text, ha="left", fontsize=8, color=SUBTLE, style="italic")


def _save(
    fig: Figure,
    name: str,
    *,
    top: float = 0.83,
    bottom: float = 0.14,
    left: float = 0.08,
    right: float = 0.96,
) -> Path:
    out = OUT_DIR / f"{name}.png"
    fig.subplots_adjust(top=top, bottom=bottom, left=left, right=right)
    fig.savefig(out, dpi=144, facecolor="white")
    plt.close(fig)
    return out


def _read(name: str, **kw: object) -> pd.DataFrame:
    return pd.read_csv(TABLES_DIR / name, **kw)


# ---------------------------------------------------------------------------
# 01 — Growth quality
# ---------------------------------------------------------------------------


def chart_growth_quality() -> Path:
    df = _read("monthly_revenue_health.csv", parse_dates=["month"])
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
    _footer(fig, "Source: monthly_revenue_health.csv  ·  synthetic data")
    return _save(fig, "01_growth_quality")


# ---------------------------------------------------------------------------
# 02 — Margin rate
# ---------------------------------------------------------------------------


def chart_margin_rate() -> Path:
    df = _read("monthly_revenue_health.csv", parse_dates=["month"])
    fig, ax = _new_fig(11, 5.0)

    ax.plot(df["month"], df["contribution_margin_pct"], color=INK, linewidth=1.8)
    ax.axhline(MARGIN_QUALITY_FLOOR, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.text(
        0.99,
        MARGIN_QUALITY_FLOOR + 0.005,
        f"{MARGIN_QUALITY_FLOOR:.0%} quality floor",
        transform=ax.get_yaxis_transform(),
        ha="right",
        va="bottom",
        color=POSITIVE,
        fontsize=9,
    )

    ax.set_ylim(0.20, 0.40)
    _pct(ax)
    ax.set_ylabel("Contribution margin / revenue")

    _suptitle(
        fig,
        "Margin quality across the window",
        f"Monthly contribution margin rate vs the {MARGIN_QUALITY_FLOOR:.0%} quality floor.",
    )
    _footer(fig, "Source: monthly_revenue_health.csv  ·  synthetic data")
    return _save(fig, "02_margin_rate")


# ---------------------------------------------------------------------------
# 03 — Month-on-month revenue growth (variance)
# ---------------------------------------------------------------------------


def chart_revenue_growth_mom() -> Path:
    df = _read("monthly_revenue_health.csv", parse_dates=["month"])
    df = df.dropna(subset=["revenue_growth_mom"]).copy()
    fig, ax = _new_fig(11, 5.2)

    colors = [POSITIVE if v >= 0 else NEGATIVE for v in df["revenue_growth_mom"]]
    ax.bar(df["month"], df["revenue_growth_mom"], width=20, color=colors)
    ax.axhline(0, color=INK, linewidth=0.9)

    mean_g = df["revenue_growth_mom"].mean()
    ax.axhline(mean_g, color=MUTED, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.text(
        0.99,
        mean_g + 0.004,
        f"mean {mean_g:.1%}",
        transform=ax.get_yaxis_transform(),
        ha="right",
        va="bottom",
        color=MUTED,
        fontsize=9,
    )

    _pct(ax)
    ax.set_ylabel("Revenue growth, month on month")

    _suptitle(
        fig,
        "How steady is the growth?",
        "Month-on-month revenue change. Down months are the test of durability.",
    )
    _footer(fig, "Source: monthly_revenue_health.csv  ·  synthetic data")
    return _save(fig, "03_revenue_growth_mom")


# ---------------------------------------------------------------------------
# 04 — Active base and revenue per active customer
# ---------------------------------------------------------------------------


def chart_active_customers_arpu() -> Path:
    df = _read("monthly_revenue_health.csv", parse_dates=["month"])
    df["arpac"] = df["total_revenue"] / df["active_customers"]
    fig, ax = _new_fig(11, 5.6)

    ax.fill_between(df["month"], df["active_customers"], color=INK, alpha=0.08)
    ax.plot(df["month"], df["active_customers"], color=INK, linewidth=1.8, label="Active customers")
    ax.set_ylabel("Active customers per month")
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    ax2 = ax.twinx()
    ax2.plot(
        df["month"], df["arpac"], color=POSITIVE, linewidth=1.8, label="Revenue per active customer"
    )
    ax2.set_ylabel("Revenue per active customer", color=POSITIVE)
    ax2.tick_params(axis="y", colors=POSITIVE)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(POSITIVE)
    ax2.spines["top"].set_visible(False)
    ax2.grid(False)
    ax2.set_ylim(bottom=0)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(
        lines, [str(ln.get_label()) for ln in lines], loc="upper left", bbox_to_anchor=(0, 1.0)
    )

    _suptitle(
        fig,
        "Is the base growing faster than monetization?",
        "Active customers against revenue per active customer.",
    )
    _footer(fig, "Source: monthly_revenue_health.csv  ·  synthetic data")
    return _save(fig, "04_active_customers_arpu", right=0.90)


# ---------------------------------------------------------------------------
# 05 — Revenue decomposition waterfall (before vs after)
# ---------------------------------------------------------------------------


def chart_revenue_decomposition() -> Path:
    dec = _read("revenue_decomposition_effects.csv")

    def val(effect: str) -> float:
        return float(dec.loc[dec["effect"] == effect, "effect_value"].iloc[0])

    vol, avg, mix = val("customer_volume_effect"), val("average_revenue_effect"), val("mix_effect")
    total = val("total_revenue_change")

    labels = ["Customer\nvolume", "Revenue per\ncustomer", "Segment\nmix", "Total\nchange"]
    deltas = [vol, avg, mix]
    fig, ax = _new_fig(11, 5.6)

    running = 0.0
    for i, d in enumerate(deltas):
        ax.bar(i, d, bottom=running, width=0.6, color=POSITIVE if d >= 0 else NEGATIVE)
        sign = "+" if d >= 0 else "−"
        ax.text(
            i,
            running + d + total * 0.012,
            f"{sign}${abs(d) / 1e6:.1f}M",
            ha="center",
            va="bottom",
            fontsize=10,
            color=INK,
            weight=600,
        )
        ax.text(
            i,
            running + d / 2,
            f"{d / total:.0%}",
            ha="center",
            va="center",
            fontsize=9,
            color="white",
            weight=600,
        )
        running += d

    ax.bar(3, total, width=0.6, color=INK)
    ax.text(
        3,
        total + total * 0.012,
        f"${total / 1e6:.1f}M",
        ha="center",
        va="bottom",
        fontsize=10,
        color=INK,
        weight=600,
    )

    # connector lines
    cum = np.cumsum([0, *deltas])
    for i in range(3):
        ax.plot(
            [i + 0.3, i + 0.7],
            [cum[i + 1], cum[i + 1]],
            color=SUBTLE,
            linewidth=0.8,
            linestyle=(0, (3, 3)),
        )

    ax.set_xticks(range(4))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, total * 1.15)
    _money(ax)
    ax.set_ylabel("Revenue change, early vs recent six months")

    _suptitle(
        fig,
        "How the revenue change decomposes",
        "Directional decomposition into customer volume, monetization, and segment mix.",
    )
    _footer(fig, "Source: revenue_decomposition_effects.csv  ·  synthetic data")
    return _save(fig, "05_revenue_decomposition")


# ---------------------------------------------------------------------------
# 06 — Cohort retention curve
# ---------------------------------------------------------------------------


def chart_cohort_retention() -> Path:
    df = _read("cohort_retention_summary.csv")
    df = df.loc[df["months_since_cohort"] <= 24].sort_values("months_since_cohort")
    fig, ax = _new_fig(11, 5.2)

    ax.plot(
        df["months_since_cohort"],
        df["median_retained_from_month_0_rate"],
        color=SUBTLE,
        linewidth=1.6,
        label="Retained from month 0",
    )
    ax.plot(
        df["months_since_cohort"],
        df["median_revenue_retention"],
        color=INK,
        linewidth=1.9,
        marker="o",
        markersize=3.3,
        markerfacecolor=INK,
        markeredgecolor="white",
        markeredgewidth=0.6,
        label="Revenue retention",
    )

    for m in (6, 12):
        if m in df["months_since_cohort"].values:
            y = float(df.loc[df["months_since_cohort"] == m, "median_revenue_retention"].iloc[0])
            ax.annotate(
                f"M{m}: {y:.0%}",
                xy=(m, y),
                xytext=(8, 9),
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
    ax.set_ylabel("Median retention")
    ax.legend(loc="upper right")

    _suptitle(
        fig,
        "How do mature cohorts retain activity and revenue?",
        "Month-0-indexed activity and revenue retention through month 24.",
    )
    _footer(fig, "Source: cohort_retention_summary.csv  ·  synthetic data")
    return _save(fig, "06_cohort_retention")


# ---------------------------------------------------------------------------
# 07 — Cohort revenue retention heatmap
# ---------------------------------------------------------------------------


def chart_cohort_heatmap() -> Path:
    df = pd.read_csv(
        PROCESSED_DIR / "cohort_table.csv", parse_dates=["cohort_month", "activity_month"]
    )
    df["months_since"] = (df["activity_month"].dt.year - df["cohort_month"].dt.year) * 12 + (
        df["activity_month"].dt.month - df["cohort_month"].dt.month
    )
    base = df[df["months_since"] == 0][["cohort_month", "cohort_revenue"]].rename(
        columns={"cohort_revenue": "base_rev"}
    )
    df = df.merge(base, on="cohort_month")
    df["retention"] = df["cohort_revenue"] / df["base_rev"]

    pivot = df.pivot_table(index="cohort_month", columns="months_since", values="retention")
    pivot = pivot.sort_index()
    # keep first 18 months of age for readability
    max_age = 18
    pivot = pivot.loc[:, [c for c in pivot.columns if c <= max_age]]

    fig, ax = _new_fig(12, 7.0)
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("greens", ["#ffffff", POSITIVE_SOFT, POSITIVE])
    data = pivot.values.astype(float)
    im = ax.imshow(np.clip(data, 0, 1.2), aspect="auto", cmap=cmap, vmin=0, vmax=1.0)

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=8)
    ylabels = [d.strftime("%b %Y") for d in pivot.index]
    ax.set_yticks(range(len(ylabels)))
    ax.set_yticklabels(ylabels, fontsize=7)
    ax.set_xlabel("Months since signup")
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    cbar = fig.colorbar(im, ax=ax, fraction=0.030, pad=0.025)
    # matplotlib stubs type Colorbar.outline imprecisely; the call is valid.
    cbar.outline.set_visible(False)  # type: ignore[operator]
    cbar.ax.tick_params(labelsize=8, colors=MUTED)
    cbar.ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0, decimals=0))
    cbar.set_label("Revenue retention vs month 0", fontsize=9, color=INK_2)

    _suptitle(
        fig,
        "Every cohort tells the same story",
        "Revenue retention by cohort (rows) and age in months (columns).",
    )
    _footer(fig, "Source: cohort_table.csv  ·  synthetic data")
    return _save(fig, "07_cohort_heatmap", top=0.86, bottom=0.10, left=0.11, right=0.93)


# ---------------------------------------------------------------------------
# 08 — Channel economics scatter
# ---------------------------------------------------------------------------


def chart_channel_economics() -> Path:
    df = _read("unit_economics_channel_diagnostics.csv")
    fig, ax = _new_fig(11, 6.0)

    colors = {"efficient": POSITIVE, "borderline": WARNING, "inefficient": NEGATIVE}
    df["_color"] = df["efficiency_status"].map(colors).fillna(MUTED)
    sizes = 80 + (df["total_spend"] / df["total_spend"].max()) * 520

    ax.scatter(
        df["CAC"],
        df["average_LTV"],
        s=sizes,
        c=df["_color"],
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
        alpha=0.92,
    )

    for _, row in df.iterrows():
        ax.annotate(
            row["acquisition_channel"],
            xy=(row["CAC"], row["average_LTV"]),
            xytext=(10, 8),
            textcoords="offset points",
            fontsize=9,
            color=INK_2,
            weight=500,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.5},
        )

    cac_max = max(df["CAC"].max() * 1.15, 1.0)
    xs = np.linspace(0, cac_max, 100)
    ax.plot(xs, 3 * xs, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.plot(xs, xs, color=NEGATIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.text(
        cac_max * 0.98,
        3 * cac_max * 0.98,
        "LTV / CAC = 3",
        ha="right",
        va="bottom",
        color=POSITIVE,
        fontsize=9,
    )
    ax.text(
        cac_max * 0.98,
        cac_max * 0.98,
        "LTV / CAC = 1",
        ha="right",
        va="bottom",
        color=NEGATIVE,
        fontsize=9,
    )

    ax.set_xlim(0, cac_max)
    ax.set_ylim(0, max(df["average_LTV"].max() * 1.15, 1.0))
    _money(ax, axis="x")
    _money(ax, axis="y")
    ax.set_xlabel("Customer acquisition cost (CAC)")
    ax.set_ylabel("Average LTV per acquired customer")

    _suptitle(
        fig,
        "Which acquisition channels deserve budget?",
        "Channel LTV against CAC. Bubble size is total spend; lines mark 1x and 3x.",
    )
    _footer(fig, "Source: unit_economics_channel_diagnostics.csv  ·  synthetic data")
    return _save(fig, "08_channel_economics")


# ---------------------------------------------------------------------------
# 09 — LTV/CAC ranking
# ---------------------------------------------------------------------------


def chart_channel_ltv_cac_ranking() -> Path:
    df = _read("unit_economics_channel_diagnostics.csv").sort_values("LTV_to_CAC")
    colors = {"efficient": POSITIVE, "borderline": WARNING, "inefficient": NEGATIVE}
    bar_colors = df["efficiency_status"].map(colors).fillna(MUTED)

    fig, ax = _new_fig(11, 5.6)
    y = np.arange(len(df))
    ax.barh(y, df["LTV_to_CAC"], color=bar_colors, height=0.62)
    ax.axvline(3.0, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.axvline(1.0, color=NEGATIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.text(3.0, len(df) - 0.3, "3x target", color=POSITIVE, fontsize=9, ha="center")
    ax.text(1.0, len(df) - 0.3, "1x breakeven", color=NEGATIVE, fontsize=9, ha="center")

    ax.set_yticks(y)
    ax.set_yticklabels(df["acquisition_channel"])
    for spine in ("bottom",):
        ax.spines[spine].set_visible(False)
    for yi, v in zip(y, df["LTV_to_CAC"]):
        ax.text(v + 0.25, float(yi), f"{v:.1f}x", va="center", fontsize=9, color=INK_2, weight=600)

    ax.set_xlim(0, df["LTV_to_CAC"].max() * 1.12)
    ax.set_xlabel("LTV to CAC ratio")
    ax.grid(axis="y", visible=False)

    _suptitle(
        fig,
        "The efficiency gap is an order of magnitude",
        "LTV/CAC ranked across channels against the 1x and 3x reference lines.",
    )
    _footer(fig, "Source: unit_economics_channel_diagnostics.csv  ·  synthetic data")
    return _save(fig, "09_channel_ltv_cac_ranking", left=0.14)


# ---------------------------------------------------------------------------
# 10 — Spend share vs contribution share (allocation gap)
# ---------------------------------------------------------------------------


def chart_channel_allocation_gap() -> Path:
    df = _read("unit_economics_channel_diagnostics.csv").copy()
    df["spend_share"] = df["total_spend"] / df["total_spend"].sum()
    df["contrib_share"] = (
        df["total_channel_contribution_margin"] / df["total_channel_contribution_margin"].sum()
    )
    df = df.sort_values("contrib_share", ascending=True)

    fig, ax = _new_fig(11, 5.8)
    y = np.arange(len(df))
    h = 0.36
    ax.barh(y + h / 2, df["spend_share"], height=h, color=MUTED, label="Share of spend")
    ax.barh(y - h / 2, df["contrib_share"], height=h, color=POSITIVE, label="Share of contribution")

    ax.set_yticks(y)
    ax.set_yticklabels(df["acquisition_channel"])
    _pct(ax, axis="x")
    ax.set_xlabel("Share of total")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")

    for yi, (s, c) in enumerate(zip(df["spend_share"], df["contrib_share"])):
        ax.text(s + 0.005, yi + h / 2, f"{s:.0%}", va="center", fontsize=8, color=MUTED)
        ax.text(
            c + 0.005, yi - h / 2, f"{c:.0%}", va="center", fontsize=8, color=POSITIVE, weight=600
        )

    _suptitle(
        fig,
        "Spend and contribution are pointed in opposite directions",
        "Each channel's share of acquisition spend against its share of contribution margin.",
    )
    _footer(fig, "Source: unit_economics_channel_diagnostics.csv  ·  synthetic data")
    return _save(fig, "10_channel_allocation_gap", left=0.14)


# ---------------------------------------------------------------------------
# 11 — Segment profitability
# ---------------------------------------------------------------------------


def chart_segment_profitability() -> Path:
    df = _read("segment_profitability.csv")
    df = df[df["dimension_type"] == "segment"].copy()
    order = ["Startup", "SMB", "Mid-Market", "Enterprise"]
    df["dimension_value"] = pd.Categorical(df["dimension_value"], categories=order, ordered=True)
    df = df.sort_values("dimension_value").reset_index(drop=True)

    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(11, 5.4), gridspec_kw={"wspace": 0.32})

    bars = ax_left.bar(
        df["dimension_value"].astype(str), df["contribution_margin"], color=INK, width=0.55
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

    colors = [
        POSITIVE if v >= MARGIN_QUALITY_FLOOR else (WARNING if v >= 0.20 else NEGATIVE)
        for v in df["margin_pct"]
    ]
    bars = ax_right.bar(
        df["dimension_value"].astype(str), df["margin_pct"], color=colors, width=0.55
    )
    ax_right.axhline(MARGIN_QUALITY_FLOOR, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
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

    fig.text(
        0.045,
        0.945,
        "Where does margin concentrate?",
        ha="left",
        fontsize=15,
        fontweight=600,
        color=INK,
    )
    fig.text(
        0.045,
        0.895,
        "Contribution margin dollars and margin rate by customer segment.",
        ha="left",
        fontsize=10,
        color=MUTED,
    )
    _footer(fig, "Source: segment_profitability.csv  ·  synthetic data")

    fig.subplots_adjust(top=0.81, bottom=0.14, left=0.07, right=0.97)
    out = OUT_DIR / "11_segment_profitability.png"
    fig.savefig(out, dpi=144, facecolor="white")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 12 — Region profitability (geography)
# ---------------------------------------------------------------------------


def chart_region_profitability() -> Path:
    df = _read("region_profitability.csv")
    df = df[df["dimension_type"] == "region"].sort_values("contribution_margin", ascending=True)

    fig, ax = _new_fig(11, 5.4)
    y = np.arange(len(df))
    ax.barh(y, df["contribution_margin"], color=INK, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(df["dimension_value"])
    _money(ax, axis="x")
    ax.set_xlabel("Contribution margin (USD)")
    ax.grid(axis="y", visible=False)

    for yi, (cm, mp, share) in enumerate(
        zip(df["contribution_margin"], df["margin_pct"], df["revenue_share"])
    ):
        ax.text(
            cm + df["contribution_margin"].max() * 0.01,
            yi,
            f"${cm / 1e6:.1f}M   ·   {mp:.1%} margin   ·   {share:.0%} of revenue",
            va="center",
            fontsize=9,
            color=INK_2,
        )

    ax.set_xlim(0, df["contribution_margin"].max() * 1.45)
    _suptitle(
        fig,
        "Geography is not where the margin problem lives",
        "Contribution margin by region, with margin rate and revenue share.",
    )
    _footer(fig, "Source: region_profitability.csv  ·  synthetic data")
    return _save(fig, "12_region_profitability", left=0.16)


# ---------------------------------------------------------------------------
# 13 — Product margin
# ---------------------------------------------------------------------------


def chart_product_margin() -> Path:
    df = _read("product_profitability.csv").sort_values("margin_pct", ascending=True)
    colors = [
        POSITIVE if v >= MARGIN_QUALITY_FLOOR else (WARNING if v >= 0.20 else NEGATIVE)
        for v in df["margin_pct"]
    ]

    fig, ax = _new_fig(11, 5.4)
    y = np.arange(len(df))
    ax.barh(y, df["margin_pct"], color=colors, height=0.6)
    ax.axvline(MARGIN_QUALITY_FLOOR, color=POSITIVE, linewidth=1.0, linestyle=(0, (4, 4)))
    ax.text(
        MARGIN_QUALITY_FLOOR, len(df) - 0.35, "30% floor", color=POSITIVE, fontsize=9, ha="center"
    )

    ax.set_yticks(y)
    ax.set_yticklabels(df["dimension_value"])
    _pct(ax, axis="x")
    ax.set_xlabel("Margin rate")
    ax.grid(axis="y", visible=False)
    for yi, (mp, rev, share) in enumerate(
        zip(df["margin_pct"], df["total_revenue"], df["revenue_share"])
    ):
        ax.text(
            mp + 0.008,
            yi,
            f"{mp:.1%}   ·   ${rev / 1e6:.1f}M ({share:.0%})",
            va="center",
            fontsize=9,
            color=INK_2,
        )

    ax.set_xlim(0, df["margin_pct"].max() * 1.5)
    _suptitle(
        fig,
        "Services is the low-margin growth pocket",
        "Margin rate by product type, with revenue and revenue share.",
    )
    _footer(fig, "Source: product_profitability.csv  ·  synthetic data")
    return _save(fig, "13_product_margin", left=0.14)


# ---------------------------------------------------------------------------
# 14 — Revenue concentration (Lorenz curve)
# ---------------------------------------------------------------------------


def chart_revenue_concentration() -> Path:
    cust = pd.read_csv(PROCESSED_DIR / "customer_metrics.csv")
    rev = np.sort(cust["total_revenue"].values)
    cum = np.cumsum(rev) / rev.sum()
    x = np.arange(1, len(rev) + 1) / len(rev)
    # Gini
    n = len(rev)
    gini = (2 * np.sum((np.arange(1, n + 1)) * rev) / (n * rev.sum())) - (n + 1) / n

    # top-share read (customers ranked high to low)
    rev_desc = rev[::-1]
    cum_desc = np.cumsum(rev_desc) / rev_desc.sum()
    top10 = cum_desc[int(n * 0.1) - 1]
    top20 = cum_desc[int(n * 0.2) - 1]

    fig, ax = _new_fig(11, 5.8)
    ax.plot(
        [0, 1], [0, 1], color=SUBTLE, linewidth=1.0, linestyle=(0, (4, 4)), label="Perfect equality"
    )
    ax.plot(x, cum, color=INK, linewidth=2.0, label="Observed")
    ax.fill_between(x, cum, x, color=POSITIVE, alpha=0.06)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _pct(ax, axis="x")
    _pct(ax, axis="y")
    ax.set_xlabel("Share of customers (lowest to highest revenue)")
    ax.set_ylabel("Cumulative share of revenue")
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.99))

    ax.text(
        0.30,
        0.97,
        f"Gini {gini:.2f}\nTop 10% of customers = {top10:.0%} of revenue\nTop 20% = {top20:.0%}",
        transform=ax.transAxes,
        fontsize=9.5,
        color=INK_2,
        va="top",
        bbox={"facecolor": SURFACE_2, "edgecolor": HAIRLINE, "pad": 6},
    )

    _suptitle(
        fig,
        "Revenue is highly concentrated",
        "Lorenz curve of lifetime revenue across all 9,000 customers.",
    )
    _footer(fig, "Source: customer_metrics.csv  ·  synthetic data")
    return _save(fig, "14_revenue_concentration")


# ---------------------------------------------------------------------------
# 15 — Customer revenue distribution
# ---------------------------------------------------------------------------


def chart_revenue_distribution() -> Path:
    cust = pd.read_csv(PROCESSED_DIR / "customer_metrics.csv")
    rev = cust["total_revenue"].values
    pos = rev[rev > 0]

    fig, ax = _new_fig(11, 5.4)
    bins = np.logspace(np.log10(pos.min()), np.log10(pos.max()), 40)
    ax.hist(pos, bins=bins.tolist(), color=INK, alpha=0.85)
    ax.set_xscale("log")

    median = np.median(rev)
    mean = np.mean(rev)
    ax.axvline(median, color=POSITIVE, linewidth=1.2, linestyle=(0, (4, 4)))
    ax.axvline(mean, color=NEGATIVE, linewidth=1.2, linestyle=(0, (4, 4)))
    ax.text(
        median,
        ax.get_ylim()[1] * 0.92,
        f" median ${median / 1e3:.1f}K",
        color=POSITIVE,
        fontsize=9,
        ha="left",
        va="top",
    )
    ax.text(
        mean,
        ax.get_ylim()[1] * 0.80,
        f" mean ${mean / 1e3:.1f}K",
        color=NEGATIVE,
        fontsize=9,
        ha="left",
        va="top",
    )

    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x / 1e3:.0f}K" if x >= 1e3 else f"${x:.0f}")
    )
    ax.set_xlabel("Lifetime revenue per customer (log scale)")
    ax.set_ylabel("Number of customers")

    _suptitle(
        fig,
        "A long right tail of high-value customers",
        "Distribution of lifetime revenue per customer. Mean sits far above median.",
    )
    _footer(fig, "Source: customer_metrics.csv  ·  synthetic data")
    return _save(fig, "15_revenue_distribution")


# ---------------------------------------------------------------------------
# 16 — Revenue vs transaction activity span
# ---------------------------------------------------------------------------


def chart_revenue_lifetime_corr() -> Path:
    cust = pd.read_csv(PROCESSED_DIR / "customer_metrics.csv")
    d = cust[cust["total_revenue"] > 0].copy()
    r = d["transaction_span_days"].corr(d["total_revenue"])
    sample = d.sample(min(2500, len(d)), random_state=42)

    fig, ax = _new_fig(11, 5.8)
    ax.scatter(
        sample["transaction_span_days"],
        sample["total_revenue"],
        s=10,
        color=INK,
        alpha=0.18,
        edgecolor="none",
    )

    # binned median trend
    bins = np.linspace(0, d["transaction_span_days"].max(), 16)
    d["_bin"] = pd.cut(d["transaction_span_days"], bins)
    trend = (
        d.groupby("_bin", observed=True)
        .agg(x=("transaction_span_days", "median"), y=("total_revenue", "median"))
        .dropna()
    )
    ax.plot(
        trend["x"],
        trend["y"],
        color=POSITIVE,
        linewidth=2.0,
        label="Median revenue by activity span",
    )

    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x / 1e3:.0f}K" if x >= 1e3 else f"${x:.0f}")
    )
    ax.set_xlabel("Observed transaction activity span (days)")
    ax.set_ylabel("Observed customer revenue (log scale)")
    ax.legend(loc="lower right")
    ax.text(
        0.02,
        0.95,
        f"Pearson r = {r:.2f}",
        transform=ax.transAxes,
        fontsize=10,
        color=INK_2,
        va="top",
        bbox={"facecolor": SURFACE_2, "edgecolor": HAIRLINE, "pad": 6},
    )

    _suptitle(
        fig,
        "Revenue and transaction activity span move together",
        "Observed association; transaction span is not customer tenure or a causal estimate.",
    )
    _footer(fig, "Source: customer_metrics.csv  ·  synthetic data")
    return _save(fig, "16_revenue_lifetime_corr")


# ---------------------------------------------------------------------------
# 17 — Reallocation contribution bridge (waterfall)
# ---------------------------------------------------------------------------


def chart_reallocation_waterfall() -> Path:
    plan = _read("scenario_reallocation_plan.csv")
    out = _read("scenario_outcomes_summary.csv")
    baseline = float(out["baseline_contribution_est"].iloc[0])
    scenario = float(out["scenario_contribution_est"].iloc[0])

    plan = plan.sort_values("contribution_change_est", ascending=False)
    moves = plan[plan["contribution_change_est"].abs() > 1][
        ["acquisition_channel", "contribution_change_est"]
    ].values.tolist()

    labels = ["Baseline"] + [m[0] for m in moves] + ["Scenario"]
    fig, ax = _new_fig(12, 5.8)

    ax.bar(0, baseline, width=0.6, color=MUTED)
    ax.text(
        0,
        baseline + scenario * 0.012,
        f"${baseline / 1e6:.1f}M",
        ha="center",
        va="bottom",
        fontsize=9,
        color=INK,
        weight=600,
    )

    running = baseline
    for i, (_name, delta) in enumerate(moves, start=1):
        color = POSITIVE if delta >= 0 else NEGATIVE
        bottom = running if delta >= 0 else running + delta
        ax.bar(i, abs(delta), bottom=bottom, width=0.6, color=color)
        sign = "+" if delta >= 0 else "−"
        ax.text(
            i,
            max(running, running + delta) + scenario * 0.012,
            f"{sign}${abs(delta) / 1e6:.1f}M",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color=color,
            weight=600,
        )
        ax.plot(
            [i - 1 + 0.3, i + 0.3],
            [running, running],
            color=SUBTLE,
            linewidth=0.8,
            linestyle=(0, (3, 3)),
        )
        running += delta

    ax.bar(len(moves) + 1, scenario, width=0.6, color=INK)
    ax.text(
        len(moves) + 1,
        scenario + scenario * 0.012,
        f"${scenario / 1e6:.1f}M",
        ha="center",
        va="bottom",
        fontsize=9,
        color=INK,
        weight=600,
    )

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, scenario * 1.15)
    _money(ax)
    ax.set_ylabel("Modeled observed-window contribution")

    _suptitle(
        fig,
        "How the reallocation builds the uplift",
        "Contribution bridge from baseline to the reallocation scenario, by channel move.",
    )
    _footer(
        fig,
        "Source: scenario_reallocation_plan.csv, scenario_outcomes_summary.csv  ·  synthetic data",
    )
    return _save(fig, "17_reallocation_waterfall")


# ---------------------------------------------------------------------------
# 18 — Scenario envelope
# ---------------------------------------------------------------------------


def chart_scenario_envelope() -> Path:
    stress = _read("scenario_stress_test_summary.csv")
    baseline = _read("scenario_outcomes_summary.csv")
    baseline_value = float(baseline["baseline_contribution_est"].iloc[0])

    stress["scenario_name"] = pd.Categorical(
        stress["scenario_name"], categories=["worst_case", "base_case", "best_case"], ordered=True
    )
    stress = stress.sort_values("scenario_name").reset_index(drop=True)

    labels = ["Baseline"] + [
        s.replace("_", " ").title() for s in stress["scenario_name"].astype(str)
    ]
    values = [baseline_value, *stress["scenario_contribution_est"].tolist()]
    colors = [MUTED, NEGATIVE, INK, POSITIVE]

    fig, ax = _new_fig(11, 5.4)
    bars = ax.bar(labels, values, color=colors, width=0.55)
    ax.axhline(baseline_value, color=MUTED, linewidth=0.9, linestyle=(0, (4, 4)))

    for bar, value in zip(bars, values):
        delta = value - baseline_value
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"${value / 1e6:.1f}M",
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
        "Modeled contribution under three assumption sets",
        "Illustrative CAC and LTV sensitivities around the reallocation policy.",
    )
    _footer(
        fig,
        "Source: scenario_outcomes_summary.csv, scenario_stress_test_summary.csv  ·  synthetic data",
    )
    return _save(fig, "18_scenario_envelope")


# ---------------------------------------------------------------------------
# 19 — Seed stability (risk)
# ---------------------------------------------------------------------------


def chart_scenario_seed_stability() -> Path:
    seed = _read("scenario_seed_sensitivity.csv").sort_values("seed")
    summ = _read("scenario_seed_sensitivity_summary.csv")
    mean = float(summ["uplift_mean"].iloc[0])
    std = float(summ["uplift_std"].iloc[0])

    fig, ax = _new_fig(11, 5.4)
    x = np.arange(len(seed))
    ax.bar(x, seed["estimated_contribution_uplift"], width=0.55, color=POSITIVE)
    ax.axhline(mean, color=INK, linewidth=1.1, linestyle=(0, (4, 4)))
    ax.axhspan(mean - std, mean + std, color=POSITIVE, alpha=0.06)

    ax.text(-0.45, mean, f"mean ${mean / 1e6:.2f}M", color=INK, fontsize=9, va="bottom", ha="left")
    for xi, v in zip(x, seed["estimated_contribution_uplift"]):
        ax.text(
            float(xi),
            v + mean * 0.01,
            f"${v / 1e6:.2f}M",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK_2,
            weight=500,
        )

    ax.set_xticks(x)
    ax.set_xticklabels([f"seed {s}" for s in seed["seed"]])
    ax.set_ylim(0, seed["estimated_contribution_uplift"].max() * 1.18)
    _money(ax)
    ax.set_ylabel("Estimated contribution uplift")
    cv = std / mean
    ax.text(
        0.02,
        0.95,
        f"Coefficient of variation {cv:.1%}\nPositive in {len(seed)}/{len(seed)} seeds",
        transform=ax.transAxes,
        fontsize=9.5,
        color=INK_2,
        va="top",
        bbox={"facecolor": SURFACE_2, "edgecolor": HAIRLINE, "pad": 6},
    )

    _suptitle(
        fig,
        "Modeled uplift is stable across the sampled seeds",
        "Five deterministic draws from the same synthetic data-generating process.",
    )
    _footer(fig, "Source: scenario_seed_sensitivity.csv  ·  synthetic data")
    return _save(fig, "19_scenario_seed_stability")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

CHART_FUNCTIONS = [
    chart_growth_quality,
    chart_margin_rate,
    chart_revenue_growth_mom,
    chart_active_customers_arpu,
    chart_revenue_decomposition,
    chart_cohort_retention,
    chart_cohort_heatmap,
    chart_channel_economics,
    chart_channel_ltv_cac_ranking,
    chart_channel_allocation_gap,
    chart_segment_profitability,
    chart_region_profitability,
    chart_product_margin,
    chart_revenue_concentration,
    chart_revenue_distribution,
    chart_revenue_lifetime_corr,
    chart_reallocation_waterfall,
    chart_scenario_envelope,
    chart_scenario_seed_stability,
]


def write_chart_index(paths: list[Path]) -> None:
    lines = [
        "# Analytical Chart Pack",
        "",
        "Nineteen analytical charts generated by `src/visualization/build_chart_pack.py`.",
        "",
    ]
    for path, (_, question) in zip(paths, CHART_METADATA, strict=True):
        lines.append(f"- [`{path.name}`]({path.name}) — {question}")
    (OUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _apply_style()

    paths = []
    for fn in CHART_FUNCTIONS:
        paths.append(fn())
    if [path.name for path in paths] != expected_chart_files():
        raise RuntimeError("Generated chart filenames do not match the publication manifest.")
    write_chart_index(paths)

    print("Chart pack written:")
    for path in paths:
        print(f"  {path.relative_to(PROJECT_ROOT)}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
