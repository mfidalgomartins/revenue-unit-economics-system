"""Build the analytical case-study report (PDF).

Renders a single self-contained HTML report and prints it to PDF with
Chromium (via Playwright). The full chart pack is embedded as base64 so the
HTML carries no external image dependencies. Every figure quoted in the prose
is read at build time from the project's processed tables, not hard-coded.

Output: outputs/reports/revenue_unit_economics_report.pdf
"""

from __future__ import annotations

import base64
from functools import cache
from io import BytesIO
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from src.design.tokens import (
    ACCENT as SHARED_ACCENT,
)
from src.design.tokens import (
    HAIRLINE,
    INK,
    INK_2,
    MUTED,
    NEGATIVE_SOFT,
    POSITIVE_SOFT,
    SUBTLE,
    SURFACE_2,
    SURFACE_3,
)
from src.design.tokens import (
    NEGATIVE as NEG,
)
from src.design.tokens import (
    POSITIVE as ACCENT,
)
from src.design.tokens import (
    WARNING as WARN,
)
from src.governance.metric_registry import (
    EFFICIENCY_THRESHOLDS,
    MARGIN_QUALITY_FLOOR,
    PAYBACK_HORIZON_MONTHS,
)
from src.paths import PROJECT_ROOT

TABLES = PROJECT_ROOT / "outputs" / "tables"
PROCESSED = PROJECT_ROOT / "data" / "processed"
GRAPHS = PROJECT_ROOT / "outputs" / "charts"
OUT = PROJECT_ROOT / "outputs" / "reports"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# Report-only editorial palette. Semantic source tokens remain unchanged and
# continue to govern business meaning; these hues art-direct the PDF without
# changing the dashboard or the canonical chart pack on disk.
REPORT_NAVY = "#102A5C"
REPORT_CYAN = "#24B7E5"
REPORT_CYAN_SOFT = "#A8E3F3"
REPORT_MAGENTA = "#D72B72"
REPORT_MAGENTA_SOFT = "#F3B7CF"
REPORT_VIOLET = "#5B5FD6"
REPORT_YELLOW = "#E6D94F"
REPORT_ICE = "#EEF8FC"

RIBBON_SVG = """<svg class="ribbon-art" viewBox="0 0 720 430"
  preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
  <path class="ribbon ribbon-navy" d="M-90 446 C150 390 360 490 505 20"/>
  <path class="ribbon ribbon-cyan" d="M-96 426 C146 374 350 468 493 23"/>
  <path class="ribbon ribbon-violet" d="M-94 408 C142 359 340 448 481 26"/>
  <path class="ribbon ribbon-magenta" d="M-96 390 C138 346 330 429 469 29"/>
  <path class="ribbon ribbon-navy thin" d="M-99 373 C130 333 320 410 457 32"/>
  <path class="ribbon ribbon-cyan wide" d="M-101 353 C122 318 310 392 445 35"/>
  <path class="ribbon ribbon-violet thin" d="M-106 333 C118 305 300 374 433 38"/>
  <path class="ribbon ribbon-yellow" d="M-109 315 C108 291 290 356 421 41"/>
  <path class="ribbon ribbon-magenta thin" d="M-113 296 C97 279 280 338 409 44"/>
  <path class="ribbon ribbon-cyan" d="M-117 277 C88 267 270 320 397 47"/>
  <path class="ribbon ribbon-navy wide" d="M-120 258 C78 255 260 302 385 50"/>
  <path class="ribbon ribbon-violet" d="M-124 239 C69 243 250 284 373 53"/>
  <path class="ribbon ribbon-magenta" d="M-128 220 C59 231 240 266 361 56"/>
  <path class="ribbon ribbon-cyan thin" d="M-132 201 C50 219 230 248 349 59"/>
</svg>"""

# Stable substrings unique to each heading's rendered text, used to locate the
# real page each TOC entry lands on (Chromium's print engine has no
# target-counter() support, so page numbers are found by scanning the rendered
# PDF rather than guessed). Search starts after the cover + TOC pages so these
# don't match the TOC's own listing of the same titles.
TOC_SEARCH_KEYS: dict[str, str] = {
    "1": "Executive summary",
    "2": "Context and objectives",
    "3": "Data and methodology",
    "4": "Analytical framework",
    "5": "Findings\n5",
    "5.1": "Observed growth is fast and uneven",
    "5.2": "Margin quality is only holding, not improving",
    "5.3": "Growth is volume-led, not monetization-led",
    "5.4": "Activation and cohort activity weaken early",
    "5.5": "Two channels fail the unit-economics policy",
    "5.6": "Margin concentrates in the lowest-rate segment and product",
    "5.7": "Revenue is concentrated in a thin band of customers",
    "5.8": "Reallocation models",
    "6": "Risks, limitations, and caveats",
    "7": "Recommendations and action priorities",
    "8": "Decision controls and open questions",
    "9": "Appendix\n9",
}


@cache
def _img(name: str) -> str:
    """Embed a report-art-directed chart without mutating the chart pack."""
    image = Image.open(BytesIO((GRAPHS / name).read_bytes())).convert("RGBA")
    pixels = np.asarray(image).copy()
    source_rgb = pixels[:, :, :3].copy()
    color_map = {
        INK: REPORT_NAVY,
        INK_2: REPORT_NAVY,
        ACCENT: REPORT_CYAN,
        POSITIVE_SOFT: REPORT_CYAN_SOFT,
        SHARED_ACCENT: REPORT_CYAN,
        NEG: REPORT_MAGENTA,
        NEGATIVE_SOFT: REPORT_MAGENTA_SOFT,
        WARN: REPORT_YELLOW,
    }
    for source_hex, target_hex in color_map.items():
        source = np.array(
            [int(source_hex[index : index + 2], 16) for index in (1, 3, 5)], dtype=np.int16
        )
        target = np.array(
            [int(target_hex[index : index + 2], 16) for index in (1, 3, 5)], dtype=np.uint8
        )
        distance = np.max(np.abs(source_rgb.astype(np.int16) - source), axis=2)
        pixels[distance <= 12, :3] = target

    output = BytesIO()
    Image.fromarray(pixels, mode="RGBA").save(output, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _usd(x: float, dp: int = 0) -> str:
    return f"${x:,.{dp}f}"


def _format_payback(row: pd.Series) -> str:
    """Render payback while retaining censoring and maturity information."""
    status = str(row.get("payback_status", "insufficient_maturity"))
    if status == "not_recovered":
        horizon = int(row.get("payback_horizon_months", PAYBACK_HORIZON_MONTHS))
        return f"&gt;{horizon}"
    if status == "insufficient_maturity" or pd.isna(row["approximate_payback_period"]):
        return "n/a"
    return f"{float(row['approximate_payback_period']):.1f}"


def build_html(toc_pages: dict[str, int] | None = None) -> str:
    def toc_pg(key: str) -> str:
        return str(toc_pages[key]) if toc_pages else ""

    ue = pd.read_csv(TABLES / "unit_economics_channel_diagnostics.csv")
    seg = pd.read_csv(TABLES / "segment_profitability.csv")
    prod = pd.read_csv(TABLES / "product_profitability.csv")
    reg = pd.read_csv(TABLES / "region_profitability.csv")
    coh = pd.read_csv(TABLES / "cohort_retention_summary.csv")
    dec = pd.read_csv(TABLES / "revenue_decomposition_effects.csv")
    out = pd.read_csv(TABLES / "scenario_outcomes_summary.csv")
    stress = pd.read_csv(TABLES / "scenario_stress_test_summary.csv")
    seed = pd.read_csv(TABLES / "scenario_seed_sensitivity_summary.csv")
    seed_detail = pd.read_csv(TABLES / "scenario_seed_sensitivity.csv")
    plan = pd.read_csv(TABLES / "scenario_reallocation_plan.csv")
    incrementality = pd.read_csv(TABLES / "marketing_incrementality.csv")
    attribution = pd.read_csv(TABLES / "multi_touch_attribution.csv")
    elasticity = pd.read_csv(TABLES / "pricing_elasticity.csv")
    pricing_recommendations = pd.read_csv(TABLES / "pricing_recommendations.csv")
    val = pd.read_csv(TABLES / "raw_validation_summary.csv")
    profile = pd.read_csv(TABLES / "data_profile_summary.csv")
    quality = pd.read_csv(TABLES / "data_quality_issues.csv")
    monthly = pd.read_csv(TABLES / "monthly_revenue_health.csv", parse_dates=["month"])
    cust = pd.read_csv(PROCESSED / "customer_metrics.csv")

    n_transactions = int(profile.loc[profile["table_name"] == "transactions", "row_count"].iloc[0])
    n_spend_records = int(
        profile.loc[profile["table_name"] == "marketing_spend", "row_count"].iloc[0]
    )
    n_touchpoints = int(
        profile.loc[profile["table_name"] == "marketing_touchpoints", "row_count"].iloc[0]
    )
    n_experiment_rows = int(
        profile.loc[profile["table_name"] == "marketing_experiments", "row_count"].iloc[0]
    )
    n_pricing_rows = int(
        profile.loc[profile["table_name"] == "pricing_interventions", "row_count"].iloc[0]
    )
    cost_issue = quality.loc[quality["check_name"] == "cost_exceeds_revenue"]
    cost_exceeds_revenue_n = int(cost_issue["issue_count"].iloc[0]) if len(cost_issue) else 0
    cost_exceeds_revenue_rate = float(cost_issue["issue_rate"].iloc[0]) if len(cost_issue) else 0.0
    expansion_share_m6 = float(
        coh.loc[coh["months_since_cohort"] == 6, "revenue_expansion_share_m6"].iloc[0]
    )

    n_customers = len(cust)
    zero_txn = int((cust["transaction_count"] == 0).sum())
    zero_txn_pct = zero_txn / n_customers

    total_rev = float(seg["total_revenue"].sum())
    total_cm = float(seg["contribution_margin"].sum())
    margin_pct = total_cm / total_rev

    # --- monthly trajectory ---
    first_rev = float(monthly["total_revenue"].iloc[0])
    last_rev = float(monthly["total_revenue"].iloc[-1])
    early_avg = float(monthly["total_revenue"].head(6).mean())
    recent_avg = float(monthly["total_revenue"].tail(6).mean())
    rev_multiple = recent_avg / early_avg
    n_months = len(monthly)
    down_months = int((monthly["revenue_growth_mom"] < 0).sum())
    obs_growth = monthly["revenue_growth_mom"].dropna()
    mean_mom = float(obs_growth.mean())
    first_active = int(monthly["active_customers"].iloc[0])
    last_active = int(monthly["active_customers"].iloc[-1])
    arpac_first = first_rev / first_active
    arpac_last = last_rev / last_active
    margin_min = float(monthly["contribution_margin_pct"].min())
    margin_max = float(monthly["contribution_margin_pct"].max())

    # --- channels ---
    def chan(name: str) -> pd.Series:
        return ue[ue["acquisition_channel"] == name].iloc[0]

    organic, referral, partners = chan("organic"), chan("referral"), chan("partners")
    email, paid, social = chan("email"), chan("paid_search"), chan("social_ads")
    ineff_spend = float(paid["total_spend"] + social["total_spend"])
    total_spend = float(ue["total_spend"].sum())
    ineff_share = ineff_spend / total_spend
    payback_mature_share_min = float(ue["payback_mature_customer_share"].min())
    payback_mature_share_max = float(ue["payback_mature_customer_share"].max())
    total_contrib = float(ue["total_channel_contribution_margin"].sum())
    ineff_contrib_share = float(
        (paid["total_channel_contribution_margin"] + social["total_channel_contribution_margin"])
        / total_contrib
    )
    eff_contrib_share = float(
        (
            organic["total_channel_contribution_margin"]
            + referral["total_channel_contribution_margin"]
            + partners["total_channel_contribution_margin"]
        )
        / total_contrib
    )
    eff_spend_share = float(
        (organic["total_spend"] + referral["total_spend"] + partners["total_spend"]) / total_spend
    )

    # --- second-order concentration risk created by the reallocation itself ---
    eff_names = ["organic", "referral", "partners"]
    plan_eff = plan[plan["acquisition_channel"].isin(eff_names)]
    plan_total_spend = float(plan["scenario_spend"].sum())
    plan_total_contrib = float(plan["scenario_contribution_est"].sum())
    eff_scenario_spend_share = float(plan_eff["scenario_spend"].sum() / plan_total_spend)
    eff_scenario_contrib_share = float(
        plan_eff["scenario_contribution_est"].sum() / plan_total_contrib
    )
    largest_eff_channel = plan_eff.loc[plan_eff["scenario_spend"].idxmax()]
    largest_eff_spend_share = float(largest_eff_channel["scenario_spend"] / plan_total_spend)
    email_spend_share = float(email["total_spend"] / total_spend)

    # --- randomized measurement and descriptive attribution ---
    incrementality_channels = ", ".join(
        incrementality.sort_values(
            "incremental_contribution_per_treated_customer", ascending=False
        )["acquisition_channel"]
        .str.replace("_", " ")
        .str.title()
    )
    incrementality_low = float(incrementality["incremental_contribution_ci_95_low"].min())
    incrementality_high = float(incrementality["incremental_contribution_ci_95_high"].max())
    product_elasticity = elasticity.loc[elasticity["product_scope"] != "All products"]
    elasticity_min = float(product_elasticity["price_elasticity"].min())
    elasticity_max = float(product_elasticity["price_elasticity"].max())
    attributed_contribution = float(attribution["attributed_contribution"].sum())
    pricing_uplift = float(pricing_recommendations["predicted_weekly_contribution_uplift"].sum())

    # --- scenario ---
    base = stress[stress["scenario_name"] == "base_case"].iloc[0]
    best = stress[stress["scenario_name"] == "best_case"].iloc[0]
    worst = stress[stress["scenario_name"] == "worst_case"].iloc[0]
    baseline_cm = float(out["baseline_contribution_est"].iloc[0])
    scenario_cm = float(out["scenario_contribution_est"].iloc[0])
    base_cm = float(base["scenario_contribution_est"])
    uplift = base_cm - baseline_cm
    uplift_pct = uplift / baseline_cm

    # --- profitability ---
    seg_only = seg[seg["dimension_type"] == "segment"]
    ent = seg_only[seg_only["dimension_value"] == "Enterprise"].iloc[0]
    mm = seg_only[seg_only["dimension_value"] == "Mid-Market"].iloc[0]
    smb = seg_only[seg_only["dimension_value"] == "SMB"].iloc[0]
    services = prod[prod["dimension_value"] == "Services"].iloc[0]
    core = prod[prod["dimension_value"] == "Core"].iloc[0]
    premium = prod[prod["dimension_value"] == "Premium"].iloc[0]
    addon = prod[prod["dimension_value"] == "Add-on"].iloc[0]
    reg_only = reg[reg["dimension_type"] == "region"].sort_values(
        "contribution_margin", ascending=False
    )
    reg_top = reg_only.iloc[0]
    reg_bottom = reg_only.iloc[-1]
    reg_margin_spread = float(reg_only["margin_pct"].max() - reg_only["margin_pct"].min())
    margin_floor = MARGIN_QUALITY_FLOOR
    ent_floor_gap = max(
        0.0, margin_floor * float(ent["total_revenue"]) - float(ent["contribution_margin"])
    )
    services_floor_gap = max(
        0.0,
        margin_floor * float(services["total_revenue"]) - float(services["contribution_margin"]),
    )
    premium_floor_gap = max(
        0.0, margin_floor * float(premium["total_revenue"]) - float(premium["contribution_margin"])
    )
    product_floor_gap = services_floor_gap + premium_floor_gap
    active_multiple = last_active / first_active
    arpac_lift = arpac_last / arpac_first - 1

    # --- cohorts ---
    def coh_at(m: int, col: str) -> float:
        return float(coh.loc[coh["months_since_cohort"] == m, col].iloc[0])

    rev_ret_m3 = coh_at(3, "median_revenue_retention")
    rev_ret_m6 = coh_at(6, "median_revenue_retention")
    rev_ret_m12 = coh_at(12, "median_revenue_retention")
    activation_m0 = coh_at(0, "median_month_0_activation_rate")
    signup_activity_m6 = coh_at(6, "median_signup_activity_rate")
    signup_activity_m12 = coh_at(12, "median_signup_activity_rate")
    retained_m0_m6 = coh_at(6, "median_retained_from_month_0_rate")
    retained_m0_m12 = coh_at(12, "median_retained_from_month_0_rate")
    m3_m6_decay_pp = (rev_ret_m3 - rev_ret_m6) * 100
    m6_m12_decay_pp = (rev_ret_m6 - rev_ret_m12) * 100
    m24_cohorts = int(coh.loc[coh["months_since_cohort"] == 24, "cohorts_observed"].iloc[0])

    # --- decomposition ---
    def dval(effect: str) -> float:
        return float(dec.loc[dec["effect"] == effect, "effect_value"].iloc[0])

    def dshare(effect: str) -> float:
        return float(dec.loc[dec["effect"] == effect, "share_of_total_change"].iloc[0])

    vol_v, vol_s = dval("customer_volume_effect"), dshare("customer_volume_effect")
    avg_v, avg_s = dval("average_revenue_effect"), dshare("average_revenue_effect")
    mix_v, mix_s = dval("mix_effect"), dshare("mix_effect")
    tot_change = dval("total_revenue_change")

    # --- seed stability ---
    seed_mean = float(seed["uplift_mean"].iloc[0])
    seed_std = float(seed["uplift_std"].iloc[0])
    seed_cv = seed_std / seed_mean
    seed_min = float(seed["uplift_min"].iloc[0])
    seed_max = float(seed["uplift_max"].iloc[0])
    n_seeds = int(seed["seed_count"].iloc[0])
    n_checks = len(val)

    # --- concentration / distribution / correlation (from customer-level data) ---
    rev = np.sort(cust["total_revenue"].values)
    n = len(rev)
    rev_desc = rev[::-1]
    cum_desc = np.cumsum(rev_desc) / rev_desc.sum()
    top1 = cum_desc[int(n * 0.01) - 1]
    top10 = cum_desc[int(n * 0.1) - 1]
    top20 = cum_desc[int(n * 0.2) - 1]
    gini = (2 * np.sum(np.arange(1, n + 1) * rev) / (n * rev.sum())) - (n + 1) / n
    rev_median = float(cust["total_revenue"].median())
    rev_mean = float(cust["total_revenue"].mean())
    rev_max = float(cust["total_revenue"].max())
    mean_median_multiple = rev_mean / rev_median
    positive_revenue = cust["total_revenue"] > 0
    corr_transaction_span = float(
        cust.loc[positive_revenue, "transaction_span_days"].corr(
            cust.loc[positive_revenue, "total_revenue"]
        )
    )
    corr_txn = float(cust["transaction_count"].corr(cust["total_revenue"]))
    neg_margin_cust = int((cust["contribution_margin"] < 0).sum())
    neg_margin_cust_pct = neg_margin_cust / n_customers
    efficient_add = float(
        plan.loc[plan["efficiency_status"] == "efficient", "contribution_change_est"].sum()
    )
    inefficient_drag = float(
        plan.loc[plan["efficiency_status"] == "inefficient", "contribution_change_est"].sum()
    )
    freed_budget = ineff_spend * 0.35

    # ---------------- table rows ----------------
    ch_rows = ""
    order = ["organic", "referral", "partners", "email", "paid_search", "social_ads"]
    status_color = {"efficient": ACCENT, "borderline": WARN, "inefficient": NEG}
    for name in order:
        r = chan(name)
        c = status_color.get(r["efficiency_status"], INK)
        ch_rows += (
            f"<tr><td>{name}</td><td class='num'>{int(r['customers_acquired']):,}</td>"
            f"<td class='num'>{_usd(r['total_spend'])}</td>"
            f"<td class='num'>{_usd(r['CAC'])}</td>"
            f"<td class='num'>{_usd(r['average_LTV'])}</td>"
            f"<td class='num'>{_usd(r['median_LTV'])}</td>"
            f"<td class='num'>{r['LTV_to_CAC']:.2f}</td>"
            f"<td class='num'>{_format_payback(r)}</td>"
            f"<td style='color:{c};font-weight:600'>{r['efficiency_status']}</td></tr>"
        )

    seg_rows = ""
    for _, r in seg_only.sort_values("contribution_margin", ascending=False).iterrows():
        seg_rows += (
            f"<tr><td>{r['dimension_value']}</td>"
            f"<td class='num'>{int(r['record_count']):,}</td>"
            f"<td class='num'>{_usd(r['total_revenue'])}</td>"
            f"<td class='num'>{_usd(r['contribution_margin'])}</td>"
            f"<td class='num'>{r['margin_pct']:.1%}</td>"
            f"<td class='num'>{r['revenue_share']:.1%}</td></tr>"
        )

    reg_rows = ""
    for _, r in reg_only.iterrows():
        reg_rows += (
            f"<tr><td>{r['dimension_value']}</td>"
            f"<td class='num'>{_usd(r['total_revenue'])}</td>"
            f"<td class='num'>{_usd(r['contribution_margin'])}</td>"
            f"<td class='num'>{r['margin_pct']:.1%}</td>"
            f"<td class='num'>{r['revenue_share']:.1%}</td></tr>"
        )

    prod_rows = ""
    for _, r in prod.sort_values("margin_pct", ascending=False).iterrows():
        prod_rows += (
            f"<tr><td>{r['dimension_value']}</td>"
            f"<td class='num'>{_usd(r['total_revenue'])}</td>"
            f"<td class='num'>{_usd(r['contribution_margin'])}</td>"
            f"<td class='num'>{r['margin_pct']:.1%}</td>"
            f"<td class='num'>{r['revenue_share']:.1%}</td></tr>"
        )

    dec_rows = (
        f"<tr><td>Customer volume</td><td class='num'>{_usd(vol_v)}</td><td class='num'>{vol_s:.1%}</td></tr>"
        f"<tr><td>Revenue per customer</td><td class='num'>{_usd(avg_v)}</td><td class='num'>{avg_s:.1%}</td></tr>"
        f"<tr><td>Segment mix</td><td class='num'>{_usd(mix_v)}</td><td class='num'>{mix_s:.1%}</td></tr>"
        f"<tr style='font-weight:600'><td>Total change</td><td class='num'>{_usd(tot_change)}</td><td class='num'>100.0%</td></tr>"
    )

    plan_rows = ""
    plan_order = plan.sort_values("contribution_change_est", ascending=False)
    for _, r in plan_order.iterrows():
        c = status_color.get(r["efficiency_status"], INK)
        delta = float(r["contribution_change_est"])
        display_delta = 0.0 if abs(delta) < 0.5 else delta
        dcol = INK if display_delta == 0 else (ACCENT if display_delta > 0 else NEG)
        delta_text = (
            _usd(0.0)
            if display_delta == 0
            else f"{'+' if display_delta > 0 else '−'}{_usd(abs(display_delta))}"
        )
        plan_rows += (
            f"<tr><td>{r['acquisition_channel']}</td>"
            f"<td style='color:{c};font-weight:600'>{r['efficiency_status']}</td>"
            f"<td class='num'>{_usd(r['baseline_spend'])}</td>"
            f"<td class='num'>{_usd(r['scenario_spend'])}</td>"
            f"<td class='num'>{r['spend_change_pct']:+.0%}</td>"
            f"<td class='num' style='color:{dcol}'>{delta_text}</td></tr>"
        )

    stress_rows = ""
    for nm, row in [("Best case", best), ("Base case", base), ("Worst case", worst)]:
        up = float(row["estimated_uplift_vs_baseline"])
        stress_rows += (
            f"<tr><td>{nm}</td>"
            f"<td class='num'>{row['cac_multiplier']:.2f}x</td>"
            f"<td class='num'>{row['ltv_multiplier']:.2f}x</td>"
            f"<td class='num'>{_usd(float(row['scenario_contribution_est']))}</td>"
            f"<td class='num' style='color:{ACCENT}'>+{_usd(up)}</td></tr>"
        )

    seed_rows = ""
    for _, r in seed_detail.sort_values("seed").iterrows():
        seed_rows += (
            f"<tr><td class='num'>{int(r['seed'])}</td>"
            f"<td class='num'>{_usd(r['baseline_contribution_est'])}</td>"
            f"<td class='num'>{_usd(r['scenario_contribution_est'])}</td>"
            f"<td class='num' style='color:{ACCENT}'>+{_usd(r['estimated_contribution_uplift'])}</td>"
            f"<td>{r['top_scale_channel']}</td><td>{r['top_cut_channel']}</td></tr>"
        )

    monthly_rows = ""
    for _, r in monthly.iterrows():
        g = r["revenue_growth_mom"]
        gtxt = "" if pd.isna(g) else f"{g:+.1%}"
        gcol = INK if pd.isna(g) else (ACCENT if g >= 0 else NEG)
        monthly_rows += (
            f"<tr><td>{r['month'].strftime('%b')}&nbsp;{r['month'].year}</td>"
            f"<td class='num'>{_usd(r['total_revenue'])}</td>"
            f"<td class='num'>{_usd(r['contribution_margin'])}</td>"
            f"<td class='num'>{r['contribution_margin_pct']:.1%}</td>"
            f"<td class='num'>{int(r['active_customers']):,}</td>"
            f"<td class='num'>{int(r['transaction_count']):,}</td>"
            f"<td class='num' style='color:{gcol}'>{gtxt}</td></tr>"
        )

    coh_rows = ""
    for _, r in coh[coh["months_since_cohort"] <= 24].iterrows():
        coh_rows += (
            f"<tr><td class='num'>{int(r['months_since_cohort'])}</td>"
            f"<td class='num'>{r['median_signup_activity_rate']:.1%}</td>"
            f"<td class='num'>{r['median_retained_from_month_0_rate']:.1%}</td>"
            f"<td class='num'>{r['median_revenue_retention']:.1%}</td>"
            f"<td class='num'>{int(r['cohorts_observed'])}</td></tr>"
        )

    val_rows = ""
    for _, r in val.iterrows():
        status = str(r["status"])
        validation_status_color = ACCENT if status == "PASS" else NEG
        val_rows += (
            f"<tr><td>{r['check_name']}</td>"
            f"<td style='color:{validation_status_color};font-weight:600'>{status}</td>"
            f"<td class='muted' style='font-size:8.2pt'>{str(r['detail'])[:90]}</td></tr>"
        )

    css = Template((ASSETS_DIR / "report.css").read_text(encoding="utf-8")).substitute(
        INK=INK,
        INK_2=INK_2,
        MUTED=MUTED,
        SUBTLE=SUBTLE,
        HAIRLINE=HAIRLINE,
        SURFACE_2=SURFACE_2,
        SURFACE_3=SURFACE_3,
        POSITIVE=ACCENT,
        NEGATIVE=NEG,
        WARNING=WARN,
        REPORT_NAVY=REPORT_NAVY,
        REPORT_CYAN=REPORT_CYAN,
        REPORT_CYAN_SOFT=REPORT_CYAN_SOFT,
        REPORT_MAGENTA=REPORT_MAGENTA,
        REPORT_MAGENTA_SOFT=REPORT_MAGENTA_SOFT,
        REPORT_VIOLET=REPORT_VIOLET,
        REPORT_YELLOW=REPORT_YELLOW,
        REPORT_ICE=REPORT_ICE,
    )

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Revenue Analytics and Unit Economics — Synthetic Case Study</title><style>{css}</style></head><body>

<!-- ============================ COVER ============================ -->
<div class="cover">
  <div class="tag">Revenue Analytics &middot; Unit Economics Diagnostic</div>
  <h1>Is the growth sustainable, or just expensive?</h1>
  <div class="sub">A diagnostic of growth quality across channel unit economics, cohort
  activation and retention, randomized incrementality, observed price response, segment and product
  profitability, customer concentration, and a bounded spend-reallocation scenario.</div>
  <div class="meta">
    <p><b>Prepared by</b> &nbsp; Miguel Fidalgo Martins &middot; Revenue Analytics</p>
    <p><b>Coverage</b> &nbsp; {n_months} months, January 2023 to December 2025 &middot;
       {n_customers:,} customers &middot; {n_transactions:,} transactions &middot; {_usd(total_spend / 1e6, 1)}M acquisition spend</p>
    <p><b>Data</b> &nbsp; Deterministic synthetic case study; figures are not a real-company forecast</p>
  </div>
  <div class="cover-art">{RIBBON_SVG}</div>
  <div class="spacer"></div>
</div>

<!-- ============================ TOC ============================ -->
<section class="break">
<h2>Contents</h2><hr class="rule">
<div class="toc">
  <div class="row"><span class="n">1</span><span class="t">Executive summary</span><span class="fill"></span><span class="pg">{toc_pg("1")}</span></div>
  <div class="row"><span class="n">2</span><span class="t">Context and objectives</span><span class="fill"></span><span class="pg">{toc_pg("2")}</span></div>
  <div class="row"><span class="n">3</span><span class="t">Data and methodology</span><span class="fill"></span><span class="pg">{toc_pg("3")}</span></div>
  <div class="row"><span class="n">4</span><span class="t">Analytical framework</span><span class="fill"></span><span class="pg">{toc_pg("4")}</span></div>
  <div class="row"><span class="n">5</span><span class="t">Findings</span><span class="fill"></span><span class="pg">{toc_pg("5")}</span></div>
  <div class="subrow"><span class="t">5.1&nbsp;&nbsp;The growth trajectory</span><span class="fill"></span><span class="pg">{toc_pg("5.1")}</span></div>
  <div class="subrow"><span class="t">5.2&nbsp;&nbsp;Margin quality across the window</span><span class="fill"></span><span class="pg">{toc_pg("5.2")}</span></div>
  <div class="subrow"><span class="t">5.3&nbsp;&nbsp;What is driving the growth</span><span class="fill"></span><span class="pg">{toc_pg("5.3")}</span></div>
  <div class="subrow"><span class="t">5.4&nbsp;&nbsp;Cohort activation and retention</span><span class="fill"></span><span class="pg">{toc_pg("5.4")}</span></div>
  <div class="subrow"><span class="t">5.5&nbsp;&nbsp;Channel unit economics</span><span class="fill"></span><span class="pg">{toc_pg("5.5")}</span></div>
  <div class="subrow"><span class="t">5.6&nbsp;&nbsp;Segment, region, and product profitability</span><span class="fill"></span><span class="pg">{toc_pg("5.6")}</span></div>
  <div class="subrow"><span class="t">5.7&nbsp;&nbsp;Customer concentration and value</span><span class="fill"></span><span class="pg">{toc_pg("5.7")}</span></div>
  <div class="subrow"><span class="t">5.8&nbsp;&nbsp;The reallocation scenario</span><span class="fill"></span><span class="pg">{toc_pg("5.8")}</span></div>
  <div class="row"><span class="n">6</span><span class="t">Risks, limitations, and caveats</span><span class="fill"></span><span class="pg">{toc_pg("6")}</span></div>
  <div class="row"><span class="n">7</span><span class="t">Recommendations and action priorities</span><span class="fill"></span><span class="pg">{toc_pg("7")}</span></div>
  <div class="row"><span class="n">8</span><span class="t">Decision controls and open questions</span><span class="fill"></span><span class="pg">{toc_pg("8")}</span></div>
  <div class="row"><span class="n">9</span><span class="t">Appendix</span><span class="fill"></span><span class="pg">{toc_pg("9")}</span></div>
</div>
</section>

<!-- ============================ 1. EXECUTIVE SUMMARY ============================ -->
<section class="break executive">
<h2><span class="num">1</span>Executive summary</h2><hr class="rule">
<div class="callout"><b>Case conclusion.</b> Paid search and social ads hold {ineff_share:.0%} of the
acquisition budget while both return less than 1&times; CAC. Under the stated response assumptions, a
budget-neutral reallocation increases modeled observed-window contribution by {_usd(uplift / 1e6, 1)}M
({uplift_pct:.0%}). The result remains positive in the three defined stress cases.</div>
<p class="lead">Average monthly revenue in the final six months is {rev_multiple:.1f}&times; the first
six-month average. Customer volume explains most of the change, while the acquisition mix
concentrates spend in the two weakest channels. Section 5.8 models a bounded reallocation; it is a
decision scenario, not a forecast.</p>

<div class="kpis">
  <div class="kpi"><div class="v">{_usd(total_rev / 1e6, 1)}M</div><div class="l">Total revenue</div><div class="d">{n_months}-month window</div></div>
  <div class="kpi"><div class="v">{_usd(total_cm / 1e6, 1)}M</div><div class="l">Contribution margin</div><div class="d">{margin_pct:.1%} of revenue</div></div>
  <div class="kpi"><div class="v">{organic["LTV_to_CAC"]:.1f}&times;</div><div class="l">Best channel LTV/CAC</div><div class="d">organic &middot; {_format_payback(organic)}m payback</div></div>
  <div class="kpi"><div class="v neg">{social["LTV_to_CAC"]:.2f}&times;</div><div class="l">Worst channel LTV/CAC</div><div class="d neg">social ads &middot; loses money</div></div>
</div>

<p>Monthly revenue rose from {_usd(first_rev / 1e3)}K in
January 2023 to {_usd(last_rev / 1e6, 1)}M in December 2025, and contribution margin tracked it closely
in absolute dollars. The channel, cohort, decomposition, and margin views qualify that top-line
growth: acquisition allocation and early customer activity remain the material constraints in this
synthetic case.</p>

<p>First, channel economics split sharply with no middle ground. Organic, referral, and partners
return between {partners["LTV_to_CAC"]:.1f} and {organic["LTV_to_CAC"]:.1f} times their acquisition
cost and recover CAC in the mature-cohort curve within two months. Paid search and social ads return {paid["LTV_to_CAC"]:.2f}
and {social["LTV_to_CAC"]:.2f} times cost, so the average customer they buy is worth less than the
cost to acquire them. These two channels hold {_usd(ineff_spend / 1e6, 2)}M, or {ineff_share:.0%}, of
total acquisition spend, while generating only {ineff_contrib_share:.0%} of channel contribution.
The three efficient channels do the inverse: {eff_spend_share:.0%} of spend, {eff_contrib_share:.0%}
of contribution.</p>

<p>Second, growth is volume-led rather than monetization-led. Of the {_usd(tot_change / 1e6, 1)}M
revenue increase between the first and last six months, {vol_s:.0%} comes from acquiring more
customers and only {avg_s:.0%} from higher revenue per customer. Volume bought through channels that
lose money is the weakest form of growth, because holding the line depends on continued spend.</p>

<p>Third, activation and subsequent activity are weak. Median month-0 activation is
{activation_m0:.0%} of signups. Median signup activity is {signup_activity_m6:.0%} at month 6 and
{signup_activity_m12:.0%} at month 12. Among customers active in month 0, {retained_m0_m6:.0%} remain
active at month 6. Median cohort revenue retention is {rev_ret_m6:.0%} at month 6 and
{rev_ret_m12:.0%} at month 12. These cohort-level diagnostics do not identify a causal mechanism.</p>

<p>Fourth, margin concentrates in the least efficient places. Enterprise is the largest segment at
{ent["revenue_share"]:.0%} of revenue but carries the lowest margin rate at {ent["margin_pct"]:.1%},
the only segment below the 30% quality floor. The Services product line runs at just
{services["margin_pct"]:.1%} margin on {_usd(float(services["total_revenue"]) / 1e6, 1)}M of revenue,
and Premium also sits below the floor at {premium["margin_pct"]:.1%}. Regional margins, by contrast,
are banded within {reg_margin_spread * 100:.1f} points, so geography is not the problem. Mix and
cost-to-serve are.</p>

<p>Fifth, revenue is highly concentrated. The top 10% of customers account for {top10:.0%} of
revenue and the top 20% for {top20:.0%}, with a Gini coefficient of {gini:.2f}. That concentration
makes retention of high-value customers a first-order risk, and it makes the early cohort decay
more expensive than the median retention figure suggests.</p>

<p>The modeled response is a bounded reallocation, governed as a test-and-scale motion. Scaling
the three efficient channels within guardrails and pulling 35% from the two inefficient ones lifts
observed-window contribution from {_usd(baseline_cm / 1e6, 1)}M to {_usd(base_cm / 1e6, 1)}M, an uplift of
{_usd(uplift / 1e6, 1)}M ({uplift_pct:.0%}) at the same acquisition budget. It is positive in the defined stress cases,
from {_usd(float(worst["estimated_uplift_vs_baseline"]) / 1e6, 1)}M worst to
{_usd(float(best["estimated_uplift_vs_baseline"]) / 1e6, 1)}M best, and across {n_seeds} deterministic
seeds it averages {_usd(seed_mean / 1e6, 1)}M (coefficient of variation {seed_cv:.1%}). Full
recommendations are in Section 7, rollout controls in Section 8.</p>
</section>

<!-- ============================ 2. CONTEXT ============================ -->
<section>
<h2><span class="num">2</span>Context and objectives</h2><hr class="rule">
<p>Top-line revenue growth is the metric most often celebrated and least often interrogated. A
revenue line that bends upward can hide three separate problems at once: customers acquired below
the cost to serve them, cohorts that leak revenue faster than new cohorts replace it, and margin
diluted by an unfavorable product or segment mix. None of these appear in a revenue chart. All
three change what a business should do next.</p>

<p>This analysis exists to answer budget and pricing questions, not to populate a dashboard. The business is
spending {_usd(total_spend / 1e6, 1)}M across the observed period to acquire customers and wants to know whether that
spend is building a durable asset or renting a revenue line that stops the moment spend stops. The
question is asked through complementary descriptive, causal, and scenario methods.</p>

<table><thead><tr><th>Question</th><th>Method</th><th>Decision it informs</th></tr></thead><tbody><tr><td>Is growth converting into margin?</td><td>Monthly revenue and contribution margin trend, margin rate vs floor</td><td>Whether to defend or improve margin</td></tr>
<tr><td>What is driving the growth?</td><td>Decomposition into volume, monetization, and mix</td><td>Where to invest for durable growth</td></tr>
<tr><td>Do cohorts activate and hold value?</td><td>Month-0 activation, signup activity, retained month-0 customers, and revenue retention</td><td>Whether activation or retention needs diagnosis</td></tr>
<tr><td>Which channels deserve budget?</td><td>LTV/CAC, payback, and spend-to-contribution alignment per channel</td><td>How to allocate acquisition spend</td></tr>
<tr><td>Which marketing activity is incremental?</td><td>Randomized customer holdouts with CUPED-adjusted contribution lift</td><td>Which treatments merit a scaled experiment</td></tr>
<tr><td>How does demand respond to price?</td><td>Randomized weekly price assignments with fixed effects and week-clustered uncertainty</td><td>Which bounded price candidates to test</td></tr>
<tr><td>How should observed value be allocated across touches?</td><td>Fully reconciling position-based attribution</td><td>Descriptive journey allocation, not causal lift</td></tr>
<tr><td>What is the upside from reallocating spend?</td><td>Bounded scenario with stress and seed-stability tests</td><td>Size and confidence of the reallocation</td></tr></tbody></table>

<p>The scope is deliberately narrow. This is not a forecast or market sizing. It is a diagnostic of
growth quality with explicit causal and non-causal claim boundaries, built so that each finding either
confirms the current allocation or changes it. Where a finding cannot be settled with the data on
hand, Section 6 says so plainly rather than papering over the gap.</p>

<p>The decision standard is practical: a finding is strong enough to change budget only when it is
visible in at least two places, such as channel economics and spend mix, or cohort decay and customer
concentration. Findings supported by one view only are treated as monitoring items or experiments,
not as immediate allocation moves. That is why the report recommends a controlled reallocation, a
retention workstream, and a margin diagnostic rather than a single blanket growth call.</p>

<h3>Who should read this</h3>
<p>The primary audience is an executive or commercial owner reviewing acquisition allocation.
The secondary audience is the analytics or finance reviewer who needs to trust the numbers
before acting on them. The report is written for the first audience in the prose and for the second
in the methodology and appendix.</p>
</section>

<!-- ============================ 3. METHODOLOGY ============================ -->
<section>
<h2><span class="num">3</span>Data and methodology</h2><hr class="rule">
<p>The pipeline validates six raw contracts before building the analytical outputs. The commercial base has
{n_customers:,} customers, {n_transactions:,} transactions, and {n_spend_records:,} daily channel-spend
records from January 2023 to December 2025. The measurement layer adds {n_touchpoints:,} privacy-minimal
touchpoints, {n_experiment_rows:,} randomized marketing observations, and {n_pricing_rows:,} randomized
weekly pricing cells. dbt builds tested incremental facts and marts; pandas produces empirical payback,
completed cohort grids, causal estimates, scenarios, and publications. Final QA reconciles the warehouse,
Python, dashboard, and report outputs.</p>

<h3>Metric definitions</h3>
<p>Contribution margin is revenue minus direct delivery cost. Observed lifetime value is the mean
cumulative contribution margin per acquired customer, computed across the full base including the
{zero_txn:,} customers ({zero_txn_pct:.1%}) who never transacted, so the figure is not inflated by
survivorship. Customer acquisition cost is period-level channel spend divided by the customers
acquired in that channel. The LTV-to-CAC ratio divides the two. Payback uses customers mature enough
to reach {PAYBACK_HORIZON_MONTHS} acquisition-age months, includes mature zero-transaction customers,
and records the first month when cumulative contribution per mature customer recovers a time-aligned
CAC: spend between the first and last signup dates of that mature subset divided by its customers. A channel
that does not recover CAC is reported as &gt;{PAYBACK_HORIZON_MONTHS} months rather than assigned an
invented point estimate.</p>

<p>A channel is classified efficient when LTV/CAC is at least {EFFICIENCY_THRESHOLDS.ltv_cac_target:.1f}
and payback is {EFFICIENCY_THRESHOLDS.payback_target_months:.0f} months or less. It is inefficient when
LTV/CAC is below {EFFICIENCY_THRESHOLDS.ineff_ltv_cac:.1f}, observed payback exceeds
{EFFICIENCY_THRESHOLDS.ineff_payback_months:.0f} months, or CAC is not recovered inside the horizon.
Insufficient maturity remains undefined. The margin quality floor is {MARGIN_QUALITY_FLOOR:.0%}.
These thresholds live in one metric registry imported by the analysis, API, chart pack, and validation
gate. Cross-output checks fail when a consumer diverges from the registry.</p>

<h3>Causal and attribution methods</h3>
<p>Marketing incrementality uses randomized customer holdouts and CUPED adjustment from pre-period
contribution. Treatment-minus-control lift is reported per treated customer with a 95% confidence
interval. The tested channels are {incrementality_channels}; the combined interval bounds across the
two experiments run from {_usd(incrementality_low, 2)} to {_usd(incrementality_high, 2)} per treated
customer.</p>

<p>Price elasticity is estimated from randomized product-region-week assignments at price indices
0.90, 1.00, and 1.10. Log demand is regressed on log price with region and week-of-year fixed effects
and CR1 uncertainty clustered by intervention week. Product coefficients range from {elasticity_min:.2f} to {elasticity_max:.2f}.
Pricing candidates remain inside the observed range. Position-based multi-touch attribution separately
allocates {_usd(attributed_contribution)} of observed contribution and reconciles to the customer table;
it is descriptive and is not used as an incrementality estimate.</p>

<p>The report uses average and median LTV together because they answer different questions. Average
LTV is the right numerator for contribution economics because it reconciles to total contribution.
Median LTV is the buyer-quality check because it shows the typical customer experience underneath
the mean. When both measures point in the same direction, the channel conclusion is stronger; when
they diverge, the channel needs segmentation before scaling.</p>

<h3>Cohort construction</h3>
<p>Customers are grouped into monthly signup cohorts. Month-0 activation is active customers divided
by all signups. Signup activity at age m uses that same signup denominator. Retained-from-month-0
activity instead asks what share of month-0 active customers are also active at age m. Revenue
retention divides cohort revenue at age m by cohort revenue in month 0. Reported curves use the
median across cohorts at each age; later ages include only cohorts old enough to be observed.</p>

<h3>Revenue decomposition</h3>
<p>The growth decomposition compares the first six months of the window against the last six. The
total revenue change is split into a customer-volume effect, an average-revenue (monetization)
effect, and a segment-mix effect, with any unexplained difference carried as a residual. The
residual is zero here by construction, so the three terms reconcile the arithmetic change under this
specification; they do not exhaust its causal mechanisms. Segment is the mix
dimension; other definitions of mix, such as region or product, would allocate the mix term
differently, which Section 6 notes.</p>

<h3>Scenario engine</h3>
<p>The reallocation scenario is deliberately conservative. It applies bounded CAC and LTV
elasticities to each channel, caps any channel's scale-up at 100% of current spend, and holds back
budget rather than forcing it into channels that have run out of efficient headroom. The scenario is
stress-tested across best, base, and worst elasticity cases, and repeated across {n_seeds}
deterministic seeds to measure sensitivity to draws from the same generator. This does not establish
external validity. The acquisition budget is held constant in every case; other operating costs and
capacity constraints are outside the scenario.</p>

<p>The scenario is not allowed to create value by expanding the budget, deleting weak channels, or
assuming unlimited capacity in strong ones. It must earn the uplift through reweighting the existing
budget and absorbing weaker economics as spend scales. The base case is a modeled planning case and
the worst case is one specified downside case, not a guaranteed floor.</p>

<h3>Data quality gate</h3>
<p>All {n_checks} raw-data validation checks pass before any analysis runs: schema match, grain
uniqueness, referential integrity, date coverage, channel-domain alignment, and value-range sanity.
The gate flagged {cost_exceeds_revenue_n:,} transactions ({cost_exceeds_revenue_rate:.2%}) where cost
exceeds revenue. That share sits below the 1% review threshold, so the intentional synthetic
cost-to-serve exceptions are retained rather than filtered.
At the customer level, {neg_margin_cust:,} customers carry a negative lifetime contribution margin,
{neg_margin_cust_pct:.1%} of the base, which the LTV figures absorb rather than exclude. The full
gate is reproduced in Appendix F.</p>

<h3>Limitations of the data</h3>
<p>The data is synthetic. It is built to be realistic and internally consistent, which makes it
suitable for demonstrating method and for relative comparison between channels, segments, and
cohorts. It is not a forecast of any real market. Observed LTV reflects only the window available,
so long-horizon cohort reads draw on mature cohorts only. These limits are revisited in Section 6.</p>
</section>

<!-- ============================ 4. FRAMEWORK ============================ -->
<section>
<h2><span class="num">4</span>Analytical framework</h2><hr class="rule">
<p>Growth quality is not a single metric. It is the answer to whether the next dollar of revenue is
worth more, the same, or less than the average dollar already on the books. This report builds that
answer from four layers, each one narrowing the question the previous layer leaves open.</p>

<p>The first layer is the <b>aggregate trajectory</b>: does revenue growth carry margin growth, and
does the margin rate improve, hold, or erode as the business scales. A flat margin rate during rapid
growth is the first signal that incremental revenue is no better than average, and it sets up every
question that follows.</p>

<p>The second layer is <b>attribution of the growth</b>: whether the increase comes from more
customers, more revenue per customer, or a shift in mix. Volume-led growth and monetization-led
growth demand different responses. The decomposition separates them so the response can be matched
to the cause.</p>

<p>The third layer is <b>unit economics and durability</b>: whether the customers being acquired are
worth more than they cost, and whether they stay long enough to pay back. This is where channel
LTV/CAC, payback, and cohort evidence combine. A low CAC is not sufficient if cumulative cohort
contribution does not recover it inside the governed horizon.</p>

<p>The fourth layer is <b>concentration and structural risk</b>: where revenue and margin pool, and
how exposed the business is to a small set of customers, segments, or products. Concentration is not
inherently bad, but it changes which risks matter and which levers move the margin line.</p>

<p>The reallocation scenario sits on top of all four. It takes the channel economics from layer
three, applies conservative elasticities, and tests how much contribution a budget-neutral move can
add. The framework is built so that the scenario is a consequence of the findings, not an assertion
bolted onto them.</p>

<div class="callout">Read the findings as a single argument. Each section answers the question the
previous one raises, and the reallocation in Section 5.8 is the action the first seven findings
point to.</div>
</section>

<!-- ============================ 5. FINDINGS ============================ -->
<section class="break chapter">
<div class="chapter-head">
  <div class="chapter-visual">{RIBBON_SVG}</div>
  <h2><span class="num">5</span>Findings</h2><hr class="rule">
</div>

<h3>5.1&nbsp;&nbsp;Observed growth is fast and uneven</h3>
<p>Monthly revenue rose from {_usd(first_rev / 1e3)}K in January 2023 to {_usd(last_rev / 1e6, 1)}M in
December 2025. Comparing like with like, the last six months averaged {_usd(recent_avg / 1e6, 1)}M a
month against {_usd(early_avg / 1e3)}K in the first six, a {rev_multiple:.1f}-fold increase across
{n_months} months. Contribution margin also rises in absolute dollars, while the margin rate remains
close to its starting level.</p>
<figure class="figure">
<img class="chart" src="{_img("01_growth_quality.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 1.</b> Revenue and contribution margin rise together in absolute dollars. The
gap between the two lines, which is the margin rate, does not widen as the business scales.</p>
</figure>

<p>Month-on-month revenue change averages {mean_mom:.1%}, with {down_months} down months in the
observed window. The chart shows recurring dips, but three years of synthetic data are not enough to
separate seasonality from other generator effects.</p>
<figure class="figure">
<img class="chart" src="{_img("03_revenue_growth_mom.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 2.</b> Month-on-month revenue growth, including {down_months} observed down
months. No causal or seasonal model is fitted.</p>
</figure>

<p>The active base grew from {first_active:,}
customers in the opening month to {last_active:,} in the closing month, while revenue per active
customer moved from {_usd(arpac_first)} to {_usd(arpac_last)}. The decomposition in Section 5.3
quantifies the relative volume and monetization effects.</p>
<figure class="figure">
<img class="chart" src="{_img("04_active_customers_arpu.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 3.</b> The active base climbs steeply while revenue per active customer stays
in a narrow band. Growth is coming from more customers, not richer ones.</p>
</figure>
<p>The active base expanded
{active_multiple:.1f}&times; from the first month to the last; revenue per active customer rose only
{arpac_lift:.0%}. Channel CAC and cohort activity therefore need to accompany the top-line measure in
any allocation decision.</p>
</section>

<section>
<h3>5.2&nbsp;&nbsp;Margin quality is only holding, not improving</h3>
<p>Contribution margin holds between {margin_min:.0%} and {margin_max:.0%}, close to the governed
{MARGIN_QUALITY_FLOOR:.0%} review floor. Absolute margin grows, but the rate shows no material upward
movement in the observed series.</p>
<figure class="figure">
<img class="chart" src="{_img("02_margin_rate.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 4.</b> Monthly contribution margin rate against the 30% quality floor. The
rate oscillates around the floor for the full window and shows no upward drift.</p>
</figure>
<p>The aggregate rate alone cannot identify whether channel allocation, product mix, pricing, or
cost-to-serve explains the pattern. The channel and profitability cuts below locate the largest
diagnostic gaps without claiming causality.</p>
</section>

<section>
<h3>5.3&nbsp;&nbsp;Growth is volume-led, not monetization-led</h3>
<p>Decomposing the {_usd(tot_change / 1e6, 1)}M revenue change between the first and last six months
separates three effects: more customers, more revenue per customer, and a shift in segment mix.</p>
<figure class="figure">
<img class="chart" src="{_img("05_revenue_decomposition.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 5.</b> Volume accounts for {vol_s:.0%} of the revenue change, monetization
{avg_s:.0%}, and segment mix {mix_s:.0%}. The three terms reconcile the change under the chosen
segment-mix decomposition.</p>
</figure>
<table><thead><tr><th>Effect</th><th class="num">Contribution to change</th><th class="num">Share</th></tr></thead><tbody>{dec_rows}</tbody></table>
<p>Volume accounts for {vol_s:.0%} of the increase. Monetization adds {avg_s:.0%} and mix a further
{mix_s:.0%}. This decomposition does not attribute incremental customers to acquisition channels;
it establishes that volume, rather than per-customer revenue, dominates the window-to-window change.</p>
<p>The mix effect is small at {mix_s:.0%}, which is its own finding. The business is not growing into
a richer customer mix that would lift the rate on its own. If anything, the structural margin problem
documented in Section 5.6 means a larger mix shift toward the biggest segment would pull the rate
down, not up.</p>
<p>For planning, that makes buyer quality and acquisition efficiency material guardrails. The channel
view in Section 5.5 evaluates the current portfolio; it should not be read as causal attribution for
the historical decomposition.</p>
</section>

<section>
<h3>5.4&nbsp;&nbsp;Activation and cohort activity weaken early</h3>
<p>Median month-0 activation is {activation_m0:.0%} of signups. At month 6,
{signup_activity_m6:.0%} of all signups are active; among customers active in month 0,
{retained_m0_m6:.0%} are also active at month 6. The corresponding month-12 measures are
{signup_activity_m12:.0%} and {retained_m0_m12:.0%}. These denominators are kept separate to avoid
describing late activation as retention.</p>
<p>Median cohort revenue retention is {rev_ret_m3:.0%} at month 3, {rev_ret_m6:.0%} at month 6, and
{rev_ret_m12:.0%} at month 12. The change from month 3 to 6 is {m3_m6_decay_pp:.1f} percentage points;
the change from month 6 to 12 is {m6_m12_decay_pp:.1f} points.</p>
<figure class="figure">
<img class="chart" src="{_img("06_cohort_retention.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 6.</b> Median retained-from-month-0 activity and revenue retention through
month 24. Signup activity uses a different denominator and is reported in the text and appendix.</p>
</figure>
<p>{expansion_share_m6:.1%} of cohorts with a month-6 observation exceed their own month-0 revenue at
that age. Revenue retention above retained-customer activity can reflect higher spend among active
customers, reactivation, or composition change; this aggregate table does not distinguish those
mechanisms.</p>
<figure class="figure">
<img class="chart" src="{_img("07_cohort_heatmap.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 7.</b> Revenue retention by cohort (rows) and age (columns). The heatmap shows
both the recurring decay pattern and cross-cohort variation.</p>
</figure>
<p>The evidence supports a follow-up activation and retention diagnostic by channel, segment, and
product. The aggregate cohort curve is not joined to payback evidence at customer level, so it does
not prove that a particular activity drop causes a channel to miss payback.</p>
<p>The month-6 read is the most decision-useful point on the curve. It is mature enough to include
{int(coh.loc[coh["months_since_cohort"] == 6, "cohorts_observed"].iloc[0])} cohorts and early enough
to support a practical leading indicator. By contrast, the month-24 tail uses {m24_cohorts} mature
cohorts and carries greater sampling uncertainty.</p>
</section>

<section>
<h3>5.5&nbsp;&nbsp;Two channels fail the unit-economics policy and hold most of the budget</h3>
<p>Channel economics split sharply, while most acquisition spend sits in the two channels below
1&times; observed LTV/CAC.</p>
<figure class="figure">
<img class="chart" src="{_img("08_channel_economics.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 8.</b> Channel LTV against CAC, with bubble size showing total spend. Three
channels sit above the 3&times; line and two below 1&times;. The two largest bubbles, paid search and social
ads, are below the CAC-recovery line on observed LTV.</p>
</figure>
<table><thead><tr><th>Channel</th><th class="num">Customers</th><th class="num">Spend</th><th class="num">CAC</th>
<th class="num">Avg LTV</th><th class="num">Med LTV</th><th class="num">LTV/CAC</th><th class="num">Payback evidence (mo)</th><th>Status</th></tr></thead><tbody>{ch_rows}</tbody></table>
<p>The CAC column and LTV/CAC ratio use the full observed window. Payback uses a separate CAC aligned
to the mature subset's acquisition dates, preventing later spend from being compared with earlier
cohort contribution.</p>
<p>Organic, referral, and partners clear the 3&times; policy and recover CAC within two acquisition-age
months in the mature-customer curves. Paid search and social ads sit below the 1&times; line, meaning the average customer they buy
is worth less than the cost to acquire them. The efficiency gap is not marginal. It is more than an
order of magnitude between the best and worst channel. Payback uses the {payback_mature_share_min:.0%}
to {payback_mature_share_max:.0%} of each channel's customers mature enough for the full
{PAYBACK_HORIZON_MONTHS}-month horizon; social ads remains unrecovered at that boundary.</p>
<figure class="figure">
<img class="chart" src="{_img("09_channel_ltv_cac_ranking.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 9.</b> LTV/CAC ranked across channels. Organic returns {organic["LTV_to_CAC"]:.0f}&times;
its cost; social ads returns {social["LTV_to_CAC"]:.2f}&times;. Email is the only borderline case.</p>
</figure>
<p>The problem is not that the inefficient channels exist; it is their weight. Together they hold
{_usd(ineff_spend / 1e6, 2)}M of acquisition spend, {ineff_share:.0%} of the total, while returning
under a dollar of contribution per dollar spent. The misallocation is clearest when each channel's
share of spend is set against its share of contribution.</p>
<figure class="figure">
<img class="chart" src="{_img("10_channel_allocation_gap.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 10.</b> Share of spend against share of contribution by channel. Organic
takes {organic["total_spend"] / total_spend:.0%} of spend and produces {organic["total_channel_contribution_margin"] / total_contrib:.0%}
of contribution; paid search and social ads take {(paid["total_spend"] + social["total_spend"]) / total_spend:.0%}
of spend and produce {ineff_contrib_share:.0%} of contribution.</p>
</figure>
<p>Email is borderline at {email["LTV_to_CAC"]:.2f}&times; with a {email["approximate_payback_period"]:.0f}-month
payback. It is a hold-and-fix case rather than a scale-or-cut one. The median LTV column tells a
sharper version of the same story than the mean: social ads has a median LTV of {_usd(social["median_LTV"])}
against a CAC of {_usd(social["CAC"])}, so the typical customer it buys is deeply underwater even
before averaging in the rare high-value account.</p>
<p>The mean and median both matter here. Organic and referral have high average LTV and materially
higher median LTV than the paid channels, so the conclusion is not just being carried by a few large
winners. Social ads is the opposite: average LTV is already below CAC, and median LTV is only
{_usd(social["median_LTV"])}. That makes it a poor scaling candidate even before attribution risk is
considered.</p>
<div class="callout">Section 5.8 tests a bounded reduction in these two channels and reallocates the
released acquisition budget under explicit response and capacity assumptions.</div>
</section>

<section>
<h3>5.6&nbsp;&nbsp;Margin concentrates in the lowest-rate segment and product</h3>
<p>Profitability by segment carries a structural risk that a revenue view hides. The largest segment
is also the least efficient.</p>
<figure class="figure">
<img class="chart" src="{_img("11_segment_profitability.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 11.</b> Contribution margin dollars and margin rate by segment. Enterprise
carries the most margin dollars at the lowest rate, and it is the only segment below the 30% floor.</p>
</figure>
<table><thead><tr><th>Segment</th><th class="num">Customers</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr></thead><tbody>{seg_rows}</tbody></table>
<p>Enterprise is the largest segment at {ent["revenue_share"]:.0%} of revenue and
{_usd(float(ent["contribution_margin"]) / 1e6, 1)}M of margin dollars, yet it carries the lowest margin
rate at {ent["margin_pct"]:.1%}, below every smaller segment. Mid-Market, SMB, and Startup all run
between {smb["margin_pct"]:.0%} and {mm["margin_pct"]:.0%}. Nearly half the revenue base sits in the
least efficient segment, which is a concentration risk: pricing or cost-to-serve pressure in
Enterprise hits the margin line harder than its rate alone suggests. Closing Enterprise to the 30%
floor would be worth roughly {_usd(ent_floor_gap / 1e6, 1)}M of contribution before any volume response,
but that estimate should be treated as a sizing anchor, not an additive forecast.</p>
<p>Geography, by contrast, is not where the margin problem lives. Regional margin rates are banded
within {reg_margin_spread * 100:.1f} points of each other, from {reg_bottom["margin_pct"]:.1%} in
{reg_bottom["dimension_value"]} to {reg_top["margin_pct"]:.1%} in {reg_top["dimension_value"]}.
Regions differ in size, not in efficiency.</p>
<figure class="figure">
<img class="chart" src="{_img("12_region_profitability.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 12.</b> Contribution margin by region with margin rate and revenue share.
{reg_top["dimension_value"]} leads on dollars, but every region sits within a point of the others on
rate. Geography is a scale story, not a margin story.</p>
</figure>
<p>The product view sharpens the diagnosis. Services run at just {services["margin_pct"]:.1%} margin
on {_usd(float(services["total_revenue"]) / 1e6, 1)}M of revenue ({services["revenue_share"]:.0%} of the
total), the deepest low-margin growth pocket. Premium is also below the 30% floor at
{premium["margin_pct"]:.1%}, while Core and Add-on, the two highest-rate lines, run at
{core["margin_pct"]:.1%} and {addon["margin_pct"]:.1%}. The spread between the best and worst product
line is nearly {(addon["margin_pct"] - services["margin_pct"]) * 100:.0f} margin points.</p>
<figure class="figure">
<img class="chart" src="{_img("13_product_margin.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 13.</b> Margin rate by product type with revenue. Services is the deepest gap
to the floor, Premium is a secondary gap, and Core plus Add-on are the products protecting the blend.</p>
</figure>
<p>Taken together, the segment and product views say the margin problem is a mix and cost-to-serve
problem, not a pricing-everywhere problem. The fix is targeted: re-price or re-scope the Services
line and the Enterprise delivery model, rather than raising prices across a base that is already
running at or above the floor everywhere else.</p>
<p>Do not add the segment and product gaps together. They are different cuts of the same underlying
customers and transactions. Their value is diagnostic, not arithmetic: both cuts point to the same
commercial workstream, which is Enterprise delivery economics and Services/Premium margin design.
Within the product cut alone, closing Services and Premium to the 30% floor would address roughly
{_usd(product_floor_gap / 1e6, 1)}M of margin gap before any behavioral response.</p>
</section>

<section>
<h3>5.7&nbsp;&nbsp;Revenue is concentrated in a thin band of customers</h3>
<p>Revenue is far from evenly spread. The top 10% of customers account for {top10:.0%} of total
revenue, the top 20% for {top20:.0%}, and the top 1% alone for {top1:.0%}. The Gini coefficient of
lifetime revenue is {gini:.2f}, well into the territory where a small group of accounts carries the
business.</p>
<figure class="figure">
<img class="chart" src="{_img("14_revenue_concentration.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 14.</b> Lorenz curve of lifetime revenue across all {n_customers:,} customers.
The deep bow away from the equality line is the concentration: a fifth of customers hold four fifths
of revenue.</p>
</figure>
<p>The distribution behind the curve is a long right tail. Median observed-window revenue is
{_usd(rev_median)} while the mean is {_usd(rev_mean)}, {mean_median_multiple:.1f} times higher,
because a small number of customers reach up to {_usd(rev_max / 1e3)}K each. The {zero_txn:,} customers
who never transacted sit at the bottom of the same distribution and pull the median down further.</p>
<figure class="figure">
<img class="chart" src="{_img("15_revenue_distribution.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 15.</b> Distribution of observed-window revenue per customer on a log scale. The
mean sits far to the right of the median, the signature of a heavy tail.</p>
</figure>
<p>Concentration changes the risk profile because a small set of customers carries much of the
observed revenue. Transaction activity span has a Pearson correlation of {corr_transaction_span:.2f}
with observed customer revenue, and transaction count has a correlation of {corr_txn:.2f}. Both
associations are partly mechanical: more observed transactions create both a longer possible span
and more accumulated revenue.</p>
<figure class="figure">
<img class="chart" src="{_img("16_revenue_lifetime_corr.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 16.</b> Observed revenue against first-to-last transaction span, with the
median trend. This is an association, not customer tenure or a causal retention estimate.</p>
</figure>
<p>The operating follow-up is to join high-value-customer concentration to channel and cohort
evidence. The current aggregate views support that analysis but do not establish which channels
cause longer or higher-value relationships.</p>
<p>The concentration read also protects the analysis from a common mistake: optimizing for the
average customer when the business is carried by a small high-value tail. The right operating lens is
not just whether a channel buys customers cheaply; it is whether later cohort evidence confirms
durable contribution at the margin.</p>
</section>

<section>
<h3>5.8&nbsp;&nbsp;Reallocation models {_usd(uplift / 1e6, 1)}M uplift at the same acquisition budget</h3>
<p>The reallocation scenario scales organic, referral, and partners within guardrails, cuts paid
search and social ads by 35%, holds email, and reinvests the freed budget into the efficient channels
up to a 100% scale-up cap per channel. Total budget is unchanged; the modeled uplift comes from the
new allocation and the stated CAC/LTV response assumptions. The policy moves {_usd(freed_budget / 1e6, 1)}M of spend out of the two inefficient
channels and assigns it only to channels that currently clear the LTV/CAC and payback gates. This
does not model incremental operating costs outside acquisition spend.</p>
<figure class="figure">
<img class="chart" src="{_img("17_reallocation_waterfall.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 17.</b> Contribution bridge from baseline to scenario by channel move.
Scaling the three efficient channels adds the modeled uplift; trimming the two inefficient ones
sacrifices some baseline contribution while releasing acquisition budget.</p>
</figure>
<table><thead><tr><th>Channel</th><th>Status</th><th class="num">Baseline spend</th><th class="num">Scenario spend</th>
<th class="num">Spend change</th><th class="num">Contribution change</th></tr></thead><tbody>{plan_rows}</tbody></table>
<p>Modeled observed-window contribution rises from {_usd(baseline_cm / 1e6, 1)}M to {_usd(scenario_cm / 1e6, 1)}M
in the base case, an uplift of {_usd(uplift / 1e6, 1)}M, or {uplift_pct:.0%}. Uplift remains positive
at the three specified stress points; this is sensitivity evidence, not a general robustness claim.
CAC and LTV move against the policy in the worst case.</p>
<p>The economics of the bridge are concentrated. Scaling organic, referral, and partners contributes
{_usd(efficient_add / 1e6, 1)}M of gross uplift, while cutting paid search and social ads removes
{_usd(abs(inefficient_drag) / 1e6, 1)}M of contribution attached to weak traffic. That trade is still
attractive because the freed spend earns materially more in the efficient channels than it loses in
the inefficient ones.</p>
<figure class="figure">
<img class="chart" src="{_img("18_scenario_envelope.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 18.</b> Contribution under the reallocation across stress cases. Every case
clears the baseline; even the worst case, with CAC up 15% and LTV down 12% across the reallocated
portfolio, adds {_usd(float(worst["estimated_uplift_vs_baseline"]) / 1e6, 1)}M.</p>
</figure>
<table><thead><tr><th>Scenario</th><th class="num">CAC mult.</th><th class="num">LTV mult.</th>
<th class="num">Contribution</th><th class="num">Uplift vs baseline</th></tr></thead><tbody>{stress_rows}</tbody></table>
<p>The worst case, with CAC inflated 15% and LTV cut 12% across every channel in the plan, still
returns {_usd(float(worst["estimated_uplift_vs_baseline"]) / 1e6, 1)}M above baseline. A separate
same-generator sensitivity check repeats the workflow across {n_seeds} deterministic seeds. Uplift averages
{_usd(seed_mean / 1e6, 1)}M with a standard deviation of {_usd(seed_std / 1e3)}K, a coefficient of
variation of {seed_cv:.1%}, and it is positive in {n_seeds} of {n_seeds} seeds. The range runs from
{_usd(seed_min / 1e6, 1)}M to {_usd(seed_max / 1e6, 1)}M.</p>
<figure class="figure">
<img class="chart" src="{_img("19_scenario_seed_stability.png")}" alt="" aria-hidden="true">
<p class="cap"><b>Figure 19.</b> Estimated uplift across {n_seeds} deterministic draws from the same
synthetic generator. This checks internal sensitivity, not external validity.</p>
</figure>
<table><thead><tr><th class="num">Seed</th><th class="num">Baseline contrib.</th><th class="num">Scenario contrib.</th>
<th class="num">Uplift</th><th>Top scale-up</th><th>Top cut</th></tr></thead><tbody>{seed_rows}</tbody></table>
<p>The reallocation trades one concentration risk for another. Section 5.7
showed revenue concentrated in a thin band of customers; this policy concentrates spend in a thin band
of channels. Organic, referral, and partners hold {eff_spend_share:.0%} of acquisition spend today;
under the scenario they hold {eff_scenario_spend_share:.0%}, and their share of channel contribution
rises from {eff_contrib_share:.0%} to {eff_scenario_contrib_share:.0%}. {largest_eff_channel["acquisition_channel"].replace("_", " ").title()}
alone would carry {largest_eff_spend_share:.0%} of total spend post-reallocation. The plan is correct
given what LTV/CAC and payback say today, but it is a bet on three channels holding their economics at
roughly double their current scale, not a diversified portfolio move. Section 8 therefore
treats capacity and channel-level guardrails as live monitoring items rather than a one-time approval,
and it is the reason a fifth control, on channel concentration, is added there alongside the four
performance guardrails.</p>
<p>Any real rollout would need staged stop-loss rules: pause a scaled channel if LTV/CAC falls below
{EFFICIENCY_THRESHOLDS.ltv_cac_target:.1f}, if payback moves beyond
{EFFICIENCY_THRESHOLDS.payback_target_months:.0f} months, or if month-6 revenue retention for newly
acquired cohorts deteriorates versus the case baseline.</p>
</section>

<!-- ============================ 6. RISKS ============================ -->
<section>
<h2><span class="num">6</span>Risks, limitations, and caveats</h2><hr class="rule">
<p>The findings are only as good as the assumptions behind them. This section states the limits
plainly so the recommendations in Section 7 are read with the right confidence.</p>

<h3>The data is synthetic</h3>
<p>Every figure in this report comes from a synthetic dataset. It is internally consistent and passes
all {n_checks} validation checks, which makes it suitable for demonstrating method and for relative
comparison between channels, segments, and cohorts. It is not a forecast of any real market, and the
absolute dollar figures should not be read as predictions. The structure of the findings, the
direction of the channel split, and the mechanics of the reallocation are the transferable part.</p>

<h3>Observed LTV is window-limited</h3>
<p>Lifetime value is measured over the available window, not over a true customer lifetime. Channels
that acquire younger cohorts have had less time to accumulate LTV, which can understate their true
value. The observed ratios therefore support a case comparison, not a claim about full-lifetime
economics.</p>

<h3>Payback uses a mature-customer subset</h3>
<p>Only {payback_mature_share_min:.0%} to {payback_mature_share_max:.0%} of customers by channel are
old enough to contribute a complete {PAYBACK_HORIZON_MONTHS}-month curve. Mature zero-transaction
customers remain in the denominator. Social ads is right-censored at &gt;{PAYBACK_HORIZON_MONTHS}
months; this differs from insufficient maturity, which would leave the classification undefined.
The recovery threshold uses spend from the acquisition-date range represented by those mature
customers rather than full-window CAC.</p>

<h3>Attribution does not identify incrementality</h3>
<p>Period CAC retains one governed acquisition channel per customer. A separate position-based model
allocates observed contribution across pre-signup touches and reconciles the total, but its weights do
not identify counterfactual channel impact. Randomized holdouts provide incremental marketing evidence.
The reallocation remains bounded because those experiments cover specific treatments rather than every
channel-budget response.</p>

<h3>Product and segment gaps are diagnostic, not additive</h3>
<p>The Enterprise, Services, and Premium margin gaps are different cuts of the same economic base.
They should not be summed into one opportunity figure without a customer-product bridge. Their value
is to identify where margin work should start: delivery model, service scope, packaging, discounting,
and cost-to-serve in the slices that repeatedly sit below the floor.</p>

<h3>The decomposition depends on the mix dimension</h3>
<p>The growth decomposition uses segment as the mix dimension. Defining mix by region, product, or
channel would allocate the {mix_s:.0%} mix term differently. Volume is {vol_s:.0%} under the segment
specification; the decomposition should be rerun before asserting the same ordering under another mix
dimension.</p>

<h3>Channel response assumptions and measured price response are separate</h3>
<p>The spend-reallocation scenario still applies bounded CAC and LTV response assumptions. Its
{_usd(uplift / 1e6, 1)}M central value and {_usd(float(worst["estimated_uplift_vs_baseline"]) / 1e6, 1)}M
tested downside are not forecast bounds. Product price elasticity is measured from randomized weekly
assignments, but supports decisions only inside the observed 0.90&ndash;1.10 price index and synthetic design.</p>

<h3>Cohort maturity</h3>
<p>Long-horizon retention reads draw only on cohorts old enough to have reached that age. The month
24 figure rests on fewer cohorts than the month 6 figure, so the tail of the retention curve is
noisier than its head. The month 3 to 6 decay, which carries the recommendation, sits in the
best-observed part of the curve.</p>

<h3>Execution capacity is assumed</h3>
<p>The reallocation assumes efficient channels can absorb additional spend up to the stated cap while
remaining inside the modeled CAC and LTV penalties. That is plausible based on the observed gap, but
not guaranteed. Capacity would need to be evaluated during rollout with CAC, payback,
conversion quality, and cohort-retention checks rather than assumed for the full quarter.</p>
</section>

<!-- ============================ 7. RECOMMENDATIONS ============================ -->
<section class="break chapter">
<div class="chapter-head">
  <div class="chapter-visual">{RIBBON_SVG}</div>
  <h2><span class="num">7</span>Recommendations and action priorities</h2><hr class="rule">
</div>
<p>Within this synthetic case, the most direct decision is to test a bounded reallocation away from
the two channels below 1&times; observed LTV/CAC. Activation, retention, and low-margin product/segment
pockets require further diagnosis before intervention. The actions below separate modeled value from
unsized follow-up work.</p>

<p>Read across, not down: the matrix below is the executive decision lens, and the numbered detail
that follows is the substantiation for each row.</p>
<table><thead><tr><th>Recommendation</th><th class="num">Modeled case value</th><th>Evidence</th><th>Pilot timing</th><th>Reversibility</th></tr></thead><tbody><tr><td>P1 &middot; Reallocate spend</td>
<td class="num">{_usd(uplift / 1e6, 1)}M (range {_usd(float(worst["estimated_uplift_vs_baseline"]) / 1e6, 1)}M&ndash;{_usd(float(best["estimated_uplift_vs_baseline"]) / 1e6, 1)}M)</td>
<td>Positive in three stress cases and {n_seeds} same-process seed draws</td><td>Staged test</td>
<td>High &mdash; budget-neutral, reversible</td></tr>
<tr><td>P2 &middot; Diagnose activation and retention</td>
<td class="num">Not directly sized</td>
<td>Aggregate cohort pattern; driver not identified</td><td>1&ndash;2 cohorts to first read</td>
<td>Medium &mdash; onboarding and process change</td></tr>
<tr><td>P3 &middot; Diagnose Services/Enterprise margin</td>
<td class="num">~{_usd(product_floor_gap / 1e6, 1)}M to the floor (sizing anchor, not additive)</td>
<td>Gap identified; price-vs-cost split unknown</td><td>Cost-to-serve analysis first</td>
<td>Low-medium &mdash; pricing and contract change</td></tr>
<tr><td>P4 &middot; Hold email, run experiment</td>
<td class="num">Bounded &mdash; {email_spend_share:.0%} of total spend</td>
<td>High confidence in the test design, low in the outcome</td><td>1&ndash;2 quarters</td>
<td>High &mdash; small, contained test</td></tr>
<tr><td>P5 &middot; Run bounded product price tests</td>
<td class="num">{_usd(pricing_uplift, 0)} predicted weekly contribution</td>
<td>Randomized price elasticity; support limited to 0.90&ndash;1.10</td><td>4&ndash;8 weeks</td>
<td>High &mdash; candidates remain inside tested range</td></tr></tbody></table>

<ol class="rec">
<li><span class="priority p1">Priority 1</span><b>Pilot a staged reduction in paid search and social
ads.</b><br>Both return under {paid["LTV_to_CAC"]:.2f}&times; cost and together hold
{ineff_share:.0%} of acquisition spend. Cut each by 35% and redirect the freed
{_usd(ineff_spend * 0.35 / 1e6, 1)}M into organic, referral, and partners, holding each to its LTV/CAC and
payback guardrails. This is the {uplift_pct:.0%} contribution uplift modeled in Section 5.8, worth
{_usd(uplift / 1e6, 1)}M in the base case and at least
{_usd(float(worst["estimated_uplift_vs_baseline"]) / 1e6, 1)}M in the tested downside case. These values
are scenario outputs under assumed response curves, not forecast returns.</li>

<li><span class="priority p2">Priority 2</span><b>Separate activation, retained activity, and revenue
retention by acquisition slice.</b><br>Median revenue retention moves from
{coh_at(3, "median_revenue_retention"):.0%} at month 3 to {coh_at(6, "median_revenue_retention"):.0%} at
month 6, while only {activation_m0:.0%} of signups activate in month 0. Break these measures down by
channel, segment, and product before selecting an onboarding or lifecycle intervention.</li>

<li><span class="priority p3">Priority 3</span><b>Decompose the Services and Enterprise margin gap into
price, discount, scope, and cost-to-serve.</b><br>Services at {services["margin_pct"]:.1%} and Enterprise
at {ent["margin_pct"]:.1%} are where mix dilutes the blended rate. Re-price or re-scope the
lowest-margin product and delivery slices only after that bridge is available. Segment and product
gaps overlap and must not be added together.</li>

<li><span class="priority p4">Priority 4</span><b>Hold email flat and run a focused economics
experiment.</b><br>Email is borderline at {email["LTV_to_CAC"]:.2f}&times; with a
{email["approximate_payback_period"]:.0f}-month payback. Do not scale or cut it on the current
evidence. Run CAC and payback experiments for one or two quarters and decide its fate on the result.
Apply the same guardrails to the efficient channels as they scale, since the scenario assumes
diminishing returns and the rollout should respect them.</li>
</ol>

<div class="callout">The reallocation is the only recommendation directly sized by the scenario.
The other actions are evidence plans; their value is not estimated in this report.</div>

<h3>Sequencing</h3>
<p>A real implementation would begin with a limited reallocation tranche and a paid-channel holdout.
In parallel, instrument the activation/retention slices and build the price-versus-cost bridge. Scale,
hold, or reverse only after marginal cohort evidence is available.</p>
</section>

<!-- ============================ 8. DECISION CONTROLS ============================ -->
<section class="break">
<h2><span class="num">8</span>Decision controls and open questions</h2><hr class="rule">
<p>The recommendation is not to declare the efficient channels permanently efficient. It is to move
budget in a controlled way, then let observed cohort and payback evidence decide whether the next
move is scale, hold, or reverse. The control system below is the minimum needed to protect the
upside in Section 5.8.</p>

<h3>Controls for the reallocation</h3>
<table><thead><tr><th>Control</th><th>Trigger</th><th>Decision response</th></tr></thead><tbody><tr><td>LTV/CAC guardrail</td><td>Any scaled channel drops below 3.0&times;</td><td>Freeze incremental budget and inspect customer mix before further scale</td></tr>
<tr><td>Payback guardrail</td><td>Any scaled channel moves beyond 12 months</td><td>Reduce spend to the last clean level and review CAC inflation</td></tr>
<tr><td>Retention guardrail</td><td>Month-6 revenue retention deteriorates versus the current {rev_ret_m6:.0%} baseline</td><td>Shift focus from acquisition scale to onboarding and activation quality</td></tr>
<tr><td>Margin guardrail</td><td>Blended contribution margin remains pinned at the 30% floor after reallocation</td><td>Escalate Services, Premium, and Enterprise cost-to-serve work</td></tr>
<tr><td>Attribution guardrail</td><td>Paid search or social ads show material assist value in a multi-touch read</td><td>Reclassify from cut to constrained hold, with spend tied to assisted contribution</td></tr>
<tr><td>Channel concentration guardrail</td><td>Any single scaled channel exceeds {largest_eff_spend_share:.0%} of total spend, or the three-channel group shows synchronized softening in the same quarter</td><td>Cap further scale-up to that channel and hold the freed increment as unallocated budget rather than force it into the remaining two</td></tr></tbody></table>

<h3>Open questions that could change the decision</h3>
<p><b>How much incremental capacity do organic, referral, and partners really have?</b> The scenario
caps scale-up at 100%, but observed channel performance should be monitored by marginal cohort, not
only by blended historical channel averages. The key question is whether the next tranche of spend
keeps the same buyer quality as the existing base.</p>

<p><b>Do paid search and social ads remain below 1&times; after multi-touch attribution?</b> Their observed
LTV/CAC is weak enough to justify cuts, but multi-touch or assisted-conversion evidence could support
a smaller holdout budget. The current action should be a reduction with measurement, not an
irreversible shutdown.</p>

<p><b>Which customers are responsible for the early retention drop?</b> The cohort curve proves the
decay pattern; it does not yet isolate the exact product, segment, channel, or use-case driver.
Because revenue is concentrated, the follow-up should prioritize high-value customers with early
usage decay rather than treating all churn equally.</p>

<p><b>What part of the Enterprise and Services margin gap is price versus cost-to-serve?</b> The report
identifies where the gap sits, not the operating root cause. The next analysis should split gross
margin leakage into discounting, delivery effort, support load, fulfilment cost, and product scope
before changing price cards or service packages.</p>

<h3>90-day evidence plan</h3>
<p><b>Weeks 1-2:</b> move the first tranche, instrument channel-level CAC, payback, and new-cohort
quality, and create a holdout read for the reduced paid channels. <b>Weeks 3-6:</b> compare marginal
cohorts against current channel baselines, with a separate read for high-value and
Services-heavy journeys. <b>Weeks 7-12:</b> complete, pause, or reverse the full reallocation based on
guardrail performance, not spend delivery alone.</p>
</section>

<!-- ============================ 9. APPENDIX ============================ -->
<section class="break chapter appendix">
<div class="chapter-head">
  <div class="chapter-visual">{RIBBON_SVG}</div>
  <h2><span class="num">9</span>Appendix</h2><hr class="rule">
</div>

<h3>A. Channel unit economics (full)</h3>
<table><thead><tr><th>Channel</th><th class="num">Customers</th><th class="num">Spend</th><th class="num">CAC</th>
<th class="num">Avg LTV</th><th class="num">Med LTV</th><th class="num">LTV/CAC</th><th class="num">Payback evidence (mo)</th><th>Status</th></tr></thead><tbody>{ch_rows}</tbody></table>

<h3>B. Segment and region profitability</h3>
<table><thead><tr><th>Segment</th><th class="num">Customers</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr></thead><tbody>{seg_rows}</tbody></table>
<table style="margin-top:14px"><thead><tr><th>Region</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr></thead><tbody>{reg_rows}</tbody></table>

<h3>C. Product profitability</h3>
<table><thead><tr><th>Product type</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr></thead><tbody>{prod_rows}</tbody></table>

<h3>D. Monthly revenue health (full series)</h3>
<p class="muted" style="font-size:9pt">The {n_months}-month series behind Figures 1, 2, 3, and 4.</p>
<table><thead><tr><th>Month</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Active cust.</th><th class="num">Transactions</th>
<th class="num">Rev. growth</th></tr></thead><tbody>{monthly_rows}</tbody></table>

<h3>E. Cohort retention curve (months 0 to 24)</h3>
<p class="muted" style="font-size:9pt">Median signup activity, retained-from-month-0 activity, and
revenue retention across cohorts at each observed age.</p>
<table><thead><tr><th class="num">Months since signup</th><th class="num">Signup activity</th>
<th class="num">Retained from M0</th><th class="num">Revenue retention</th>
<th class="num">Cohorts observed</th></tr></thead><tbody>{coh_rows}</tbody></table>

<h3>F. Data validation gate</h3>
<p class="muted" style="font-size:9pt">All {n_checks} checks run on the raw tables before any
analysis. A failure blocks the pipeline.</p>
<table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{val_rows}</tbody></table>

<h3>G. Data dictionary and reproducibility</h3>
<table><thead><tr><th>Field</th><th>Definition</th></tr></thead><tbody><tr><td>contribution_margin</td><td>Revenue minus direct delivery cost</td></tr>
<tr><td>average_LTV</td><td>Mean cumulative contribution margin per acquired customer, including zero-transaction customers</td></tr>
<tr><td>median_LTV</td><td>Median cumulative contribution margin per acquired customer</td></tr>
<tr><td>CAC</td><td>Period channel spend divided by customers acquired in the channel</td></tr>
<tr><td>payback_CAC</td><td>Spend inside the mature customers' acquisition-date window divided by those mature customers; used only for the empirical payback curve</td></tr>
<tr><td>LTV_to_CAC</td><td>average_LTV divided by CAC; efficient at &ge; 3.0</td></tr>
<tr><td>approximate_payback_period</td><td>First acquisition-age month when cumulative contribution per mature customer recovers payback_CAC; unrecovered cases are right-censored at &gt;{PAYBACK_HORIZON_MONTHS} months</td></tr>
<tr><td>median_month_0_activation_rate</td><td>Median share of signups active in their signup month</td></tr>
<tr><td>median_signup_activity_rate</td><td>Median share of the original signup cohort active at age m</td></tr>
<tr><td>median_retained_from_month_0_rate</td><td>Median share of month-0 active customers also active at age m</td></tr>
<tr><td>median_revenue_retention</td><td>Median cohort revenue at month m relative to month 0</td></tr>
<tr><td>incremental_contribution_per_treated_customer</td><td>CUPED-adjusted treatment-minus-control contribution from a randomized holdout</td></tr>
<tr><td>price_elasticity</td><td>Log demand response to log price inside the randomized 0.90&ndash;1.10 price range</td></tr>
<tr><td>attributed_contribution</td><td>Observed contribution allocated by position-based journey weights; descriptive, not causal</td></tr>
<tr><td>Gini coefficient</td><td>Concentration of observed-window revenue across customers; 0 is even, 1 is fully concentrated</td></tr></tbody></table>
</section>

</body></html>"""
    return html


def render_pdf_bytes(html: str) -> bytes:
    """Render self-contained report HTML without filesystem or network intermediates."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(offline=True)
        page = context.new_page()
        page.set_content(html, wait_until="load")
        page.wait_for_function("Array.from(document.images).every((image) => image.complete)")
        page.emulate_media(media="print")
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            tagged=True,
        )
        context.close()
        browser.close()
    return pdf_bytes


def _normalize_pdf_text(text: str) -> str:
    """Normalize extraction quirks caused by print line breaks and kerning."""
    return "".join(text.split()).casefold()


def locate_toc_pages(pdf_bytes: bytes) -> dict[str, int]:
    """Find the real page each TOC entry lands on by scanning the rendered PDF.

    Chromium's print engine (used via Playwright) does not support CSS
    target-counter(), so page numbers can't be computed at HTML-build time.
    Instead, search starts after the cover and TOC pages themselves (index 2
    onward) so a heading's own listing in the TOC text can't self-match.
    """
    pages_text = [
        _normalize_pdf_text(page.extract_text() or "")
        for page in PdfReader(BytesIO(pdf_bytes)).pages
    ]
    result: dict[str, int] = {}
    for key, marker in TOC_SEARCH_KEYS.items():
        normalized_marker = _normalize_pdf_text(marker)
        for i in range(2, len(pages_text)):
            if normalized_marker in pages_text[i]:
                result[key] = i + 1
                break
        else:
            raise RuntimeError(f"Could not locate TOC target {key!r} (marker: {marker!r})")
    return result


def finalize_pdf(pdf_bytes: bytes, toc_pages: dict[str, int]) -> bytes:
    """Normalize metadata and add stable top-level navigation bookmarks."""
    reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    writer = PdfWriter(reader, full=True, strict=True)
    if writer._info is not None:
        info = writer._info.get_object()
        if isinstance(info, DictionaryObject):
            info.pop(NameObject("/CreationDate"), None)
            info.pop(NameObject("/ModDate"), None)
    writer.add_metadata(
        {
            "/Title": "Revenue Analytics and Unit Economics — Synthetic Case Study",
            "/Author": "Miguel Fidalgo Martins",
            "/Subject": "Reproducible revenue analytics, unit economics, causal measurement, and scenario modeling",
            "/Keywords": "revenue analytics, unit economics, synthetic data, portfolio case study",
            "/Creator": "Revenue Analytics Unit Economics System",
            "/Producer": "Revenue Analytics Unit Economics System",
        }
    )
    writer._root_object[NameObject("/Lang")] = TextStringObject("en-US")

    outline_titles = {
        "1": "1. Executive summary",
        "2": "2. Context and objectives",
        "3": "3. Data and methodology",
        "4": "4. Analytical framework",
        "5": "5. Findings",
        "6": "6. Risks, limitations, and caveats",
        "7": "7. Recommendations and action priorities",
        "8": "8. Decision controls and open questions",
        "9": "9. Appendix",
    }
    for key, title in outline_titles.items():
        writer.add_outline_item(title, toc_pages[key] - 1)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def write_pdf(pdf_bytes: bytes) -> Path:
    """Write the single final report artifact."""
    OUT.mkdir(parents=True, exist_ok=True)
    pdf_path = OUT / "revenue_unit_economics_report.pdf"
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path


def main() -> None:
    # Pass 1: render without TOC page numbers, then find where each section
    # actually landed. Pass 2 renders the final PDF with those real numbers.
    # Content pagination is identical between passes (the TOC page has spare
    # room, so filling in a number column doesn't shift anything else).
    provisional_pdf = render_pdf_bytes(build_html(toc_pages=None))
    toc_pages = locate_toc_pages(provisional_pdf)
    rendered_pdf = render_pdf_bytes(build_html(toc_pages=toc_pages))
    path = write_pdf(finalize_pdf(rendered_pdf, toc_pages))
    print(f"Report written: {path.relative_to(PROJECT_ROOT)} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
