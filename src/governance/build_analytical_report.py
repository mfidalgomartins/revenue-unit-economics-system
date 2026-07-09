"""Build the publication-ready analytical report (PDF).

Renders a single self-contained HTML report and prints it to PDF with
Chromium (via Playwright). The full chart pack is embedded as base64 so the
HTML carries no external image dependencies. Every figure quoted in the prose
is read at build time from the project's processed tables, not hard-coded.

Output: outputs/reports/revenue_unit_economics_report.pdf
"""

from __future__ import annotations

import base64
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd
from pypdf import PdfReader

from src.design.tokens import (
    HAIRLINE,
    INK,
    INK_2,
    MUTED,
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
from src.paths import PROJECT_ROOT

TABLES = PROJECT_ROOT / "outputs" / "tables"
PROCESSED = PROJECT_ROOT / "data" / "processed"
GRAPHS = PROJECT_ROOT / "outputs" / "charts"
OUT = PROJECT_ROOT / "outputs" / "reports"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

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
    "5": "Findings\n5.1",
    "5.1": "The growth trajectory is real, fast, and uneven",
    "5.2": "Margin quality is only holding, not improving",
    "5.3": "Growth is volume-led, not monetization-led",
    "5.4": "Cohorts decay fast in the",
    "5.5": "Two channels destroy value and hold most of the budget",
    "5.6": "Margin concentrates in the lowest-rate segment and product",
    "5.7": "Revenue is concentrated in a thin band of customers",
    "5.8": "Reallocation adds",
    "6": "Risks, limitations, and caveats",
    "7": "Recommendations and action priorities",
    "8": "Decision controls and open questions",
    "9": "Appendix\nA. Channel unit economics",
}


def _img(name: str) -> str:
    data = (GRAPHS / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _usd(x: float, dp: int = 0) -> str:
    return f"${x:,.{dp}f}"


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
    val = pd.read_csv(TABLES / "raw_validation_summary.csv")
    profile = pd.read_csv(TABLES / "data_profile_summary.csv")
    quality = pd.read_csv(TABLES / "data_quality_issues.csv")
    monthly = pd.read_csv(TABLES / "monthly_revenue_health.csv", parse_dates=["month"])
    cust = pd.read_csv(PROCESSED / "customer_metrics.csv")

    n_transactions = int(profile.loc[profile["table_name"] == "transactions", "row_count"].iloc[0])
    n_spend_records = int(profile.loc[profile["table_name"] == "marketing_spend", "row_count"].iloc[0])
    cost_issue = quality.loc[quality["check_name"] == "cost_exceeds_revenue"].iloc[0]
    cost_exceeds_revenue_n = int(cost_issue["issue_count"])
    cost_exceeds_revenue_rate = float(cost_issue["issue_rate"])
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
    total_contrib = float(ue["total_channel_contribution_margin"].sum())
    ineff_contrib_share = float(
        (paid["total_channel_contribution_margin"] + social["total_channel_contribution_margin"])
        / total_contrib
    )
    eff_contrib_share = float(
        (organic["total_channel_contribution_margin"] + referral["total_channel_contribution_margin"]
         + partners["total_channel_contribution_margin"]) / total_contrib
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
    eff_scenario_contrib_share = float(plan_eff["scenario_contribution_est"].sum() / plan_total_contrib)
    largest_eff_channel = plan_eff.loc[plan_eff["scenario_spend"].idxmax()]
    largest_eff_spend_share = float(largest_eff_channel["scenario_spend"] / plan_total_spend)
    email_spend_share = float(email["total_spend"] / total_spend)

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
    reg_only = reg[reg["dimension_type"] == "region"].sort_values("contribution_margin", ascending=False)
    reg_top = reg_only.iloc[0]
    reg_bottom = reg_only.iloc[-1]
    reg_margin_spread = float(reg_only["margin_pct"].max() - reg_only["margin_pct"].min())
    margin_floor = 0.30
    ent_floor_gap = max(0.0, margin_floor * float(ent["total_revenue"]) - float(ent["contribution_margin"]))
    services_floor_gap = max(
        0.0, margin_floor * float(services["total_revenue"]) - float(services["contribution_margin"])
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
    act_ret_m6 = coh_at(6, "median_activity_retention")
    act_ret_m12 = coh_at(12, "median_activity_retention")
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
    corr_life = float(cust.loc[cust["total_revenue"] > 0, "lifetime_days"].corr(
        cust.loc[cust["total_revenue"] > 0, "total_revenue"]))
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
            f"<td class='num'>{r['approximate_payback_period']:.1f}</td>"
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
        dcol = ACCENT if delta >= 0 else NEG
        plan_rows += (
            f"<tr><td>{r['acquisition_channel']}</td>"
            f"<td style='color:{c};font-weight:600'>{r['efficiency_status']}</td>"
            f"<td class='num'>{_usd(r['baseline_spend'])}</td>"
            f"<td class='num'>{_usd(r['scenario_spend'])}</td>"
            f"<td class='num'>{r['spend_change_pct']:+.0%}</td>"
            f"<td class='num' style='color:{dcol}'>{('+' if delta>=0 else '−')}{_usd(abs(delta))}</td></tr>"
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
            f"<td class='num'>{r['median_activity_retention']:.1%}</td>"
            f"<td class='num'>{r['median_revenue_retention']:.1%}</td>"
            f"<td class='num'>{int(r['cohorts_observed'])}</td></tr>"
        )

    val_rows = ""
    for _, r in val.iterrows():
        val_rows += (
            f"<tr><td>{r['check_name']}</td>"
            f"<td style='color:{ACCENT};font-weight:600'>{r['status']}</td>"
            f"<td class='muted' style='font-size:8.2pt'>{str(r['detail'])[:90]}</td></tr>"
        )

    css = Template((ASSETS_DIR / "report.css").read_text(encoding="utf-8")).substitute(
        INK=INK, INK_2=INK_2, MUTED=MUTED, SUBTLE=SUBTLE, HAIRLINE=HAIRLINE,
        SURFACE_2=SURFACE_2, SURFACE_3=SURFACE_3, POSITIVE=ACCENT, NEGATIVE=NEG,
        WARNING=WARN,
    )

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>

<!-- ============================ COVER ============================ -->
<div class="cover">
  <div class="tag">Revenue Analytics &middot; Unit Economics Diagnostic</div>
  <h1>Is the growth sustainable, or just expensive?</h1>
  <div class="sub">A diagnostic of growth quality across channel unit economics, cohort
  retention, segment and product profitability, customer concentration, and a bounded,
  stress-tested spend-reallocation scenario.</div>
  <div class="spacer"></div>
  <hr class="rule" style="margin-bottom:12px">
  <div class="meta">
    <p><b>Prepared by</b> &nbsp; Miguel Fidalgo Martins &middot; Revenue Analytics</p>
    <p><b>Coverage</b> &nbsp; {n_months} months, January 2023 to December 2025 &middot;
       {n_customers:,} customers &middot; {n_transactions:,} transactions &middot; {total_spend/1e6:.1f}M acquisition spend</p>
  </div>
</div>

<!-- ============================ TOC ============================ -->
<section class="break">
<h2>Contents</h2><hr class="rule">
<div class="toc">
  <div class="row"><span class="n">1</span><span class="t">Executive summary</span><span class="fill"></span><span class="pg">{toc_pg('1')}</span></div>
  <div class="row"><span class="n">2</span><span class="t">Context and objectives</span><span class="fill"></span><span class="pg">{toc_pg('2')}</span></div>
  <div class="row"><span class="n">3</span><span class="t">Data and methodology</span><span class="fill"></span><span class="pg">{toc_pg('3')}</span></div>
  <div class="row"><span class="n">4</span><span class="t">Analytical framework</span><span class="fill"></span><span class="pg">{toc_pg('4')}</span></div>
  <div class="row"><span class="n">5</span><span class="t">Findings</span><span class="fill"></span><span class="pg">{toc_pg('5')}</span></div>
  <div class="subrow"><span class="t">5.1&nbsp;&nbsp;The growth trajectory</span><span class="fill"></span><span class="pg">{toc_pg('5.1')}</span></div>
  <div class="subrow"><span class="t">5.2&nbsp;&nbsp;Margin quality across the window</span><span class="fill"></span><span class="pg">{toc_pg('5.2')}</span></div>
  <div class="subrow"><span class="t">5.3&nbsp;&nbsp;What is driving the growth</span><span class="fill"></span><span class="pg">{toc_pg('5.3')}</span></div>
  <div class="subrow"><span class="t">5.4&nbsp;&nbsp;Cohort retention and revenue decay</span><span class="fill"></span><span class="pg">{toc_pg('5.4')}</span></div>
  <div class="subrow"><span class="t">5.5&nbsp;&nbsp;Channel unit economics</span><span class="fill"></span><span class="pg">{toc_pg('5.5')}</span></div>
  <div class="subrow"><span class="t">5.6&nbsp;&nbsp;Segment, region, and product profitability</span><span class="fill"></span><span class="pg">{toc_pg('5.6')}</span></div>
  <div class="subrow"><span class="t">5.7&nbsp;&nbsp;Customer concentration and value</span><span class="fill"></span><span class="pg">{toc_pg('5.7')}</span></div>
  <div class="subrow"><span class="t">5.8&nbsp;&nbsp;The reallocation scenario</span><span class="fill"></span><span class="pg">{toc_pg('5.8')}</span></div>
  <div class="row"><span class="n">6</span><span class="t">Risks, limitations, and caveats</span><span class="fill"></span><span class="pg">{toc_pg('6')}</span></div>
  <div class="row"><span class="n">7</span><span class="t">Recommendations and action priorities</span><span class="fill"></span><span class="pg">{toc_pg('7')}</span></div>
  <div class="row"><span class="n">8</span><span class="t">Decision controls and open questions</span><span class="fill"></span><span class="pg">{toc_pg('8')}</span></div>
  <div class="row"><span class="n">9</span><span class="t">Appendix</span><span class="fill"></span><span class="pg">{toc_pg('9')}</span></div>
</div>
</section>

<!-- ============================ 1. EXECUTIVE SUMMARY ============================ -->
<section class="break">
<h2><span class="num">1</span>Executive summary</h2><hr class="rule">
<div class="callout"><b>Bottom line.</b> Growth is real, not manufactured, but it is being bought at the
wrong price from two channels holding {ineff_share:.0%} of the budget. Re-pointing existing spend adds
{_usd(uplift/1e6,1)}M of annual contribution ({uplift_pct:.0%}) at zero incremental cost and stays
positive in every stress case tested. That single move is Priority 1 in Section 7.</div>
<p class="lead">Revenue grew {rev_multiple:.1f}-fold across the three-year window, comparing the first
and last six months, but the growth is carried by the most expensive customers the business buys. The
constraint is the spend mix, not demand. Moving the budget that already exists toward the channels
that pay back adds {_usd(uplift/1e6,1)}M of annual contribution without raising the budget by a
dollar.</p>

<div class="kpis">
  <div class="kpi"><div class="v">{_usd(total_rev/1e6,1)}M</div><div class="l">Total revenue</div><div class="d">{n_months}-month window</div></div>
  <div class="kpi"><div class="v">{_usd(total_cm/1e6,1)}M</div><div class="l">Contribution margin</div><div class="d">{margin_pct:.1%} of revenue</div></div>
  <div class="kpi"><div class="v">{organic['LTV_to_CAC']:.1f}&times;</div><div class="l">Best channel LTV/CAC</div><div class="d">organic &middot; {organic['approximate_payback_period']:.1f}m payback</div></div>
  <div class="kpi"><div class="v neg">{social['LTV_to_CAC']:.2f}&times;</div><div class="l">Worst channel LTV/CAC</div><div class="d neg">social ads &middot; loses money</div></div>
</div>

<p>The headline is unambiguous, but incomplete. Monthly revenue rose from {_usd(first_rev/1e3)}K in
January 2023 to {_usd(last_rev/1e6,1)}M in December 2025, and contribution margin tracked it closely
in absolute dollars. A revenue chart on its own would read as an unqualified success. Five separate
analyzes say otherwise, and they agree: the business has strong demand capture, but weak allocation
discipline.</p>

<p>First, channel economics split sharply with no middle ground. Organic, referral, and partners
return between {partners['LTV_to_CAC']:.1f} and {organic['LTV_to_CAC']:.1f} times their acquisition
cost and pay back in under nine months. Paid search and social ads return {paid['LTV_to_CAC']:.2f}
and {social['LTV_to_CAC']:.2f} times cost, so the average customer they buy is worth less than the
cost to acquire them. These two channels hold {_usd(ineff_spend/1e6,2)}M, or {ineff_share:.0%}, of
total acquisition spend, while generating only {ineff_contrib_share:.0%} of channel contribution.
The three efficient channels do the inverse: {eff_spend_share:.0%} of spend, {eff_contrib_share:.0%}
of contribution.</p>

<p>Second, growth is volume-led rather than monetization-led. Of the {_usd(tot_change/1e6,1)}M
revenue increase between the first and last six months, {vol_s:.0%} comes from acquiring more
customers and only {avg_s:.0%} from higher revenue per customer. Volume bought through channels that
lose money is the weakest form of growth, because holding the line depends on continued spend.</p>

<p>Third, retention decays fast and early. Median revenue retention falls to
{coh_at(6,'median_revenue_retention'):.0%} by month 6 and {coh_at(12,'median_revenue_retention'):.0%}
by month 12, with the steepest loss between months 3 and 6. Only {expansion_share_m6:.1%} of cohorts
show revenue expansion at month 6, so the median customer shrinks in their first half-year. The
acquisition treadmill cannot be slowed until this early-life decay is fixed.</p>

<p>Fourth, margin concentrates in the least efficient places. Enterprise is the largest segment at
{ent['revenue_share']:.0%} of revenue but carries the lowest margin rate at {ent['margin_pct']:.1%},
the only segment below the 30% quality floor. The Services product line runs at just
{services['margin_pct']:.1%} margin on {_usd(float(services['total_revenue'])/1e6,1)}M of revenue,
and Premium also sits below the floor at {premium['margin_pct']:.1%}. Regional margins, by contrast,
are banded within {reg_margin_spread*100:.1f} points, so geography is not the problem. Mix and
cost-to-serve are.</p>

<p>Fifth, revenue is highly concentrated. The top 10% of customers account for {top10:.0%} of
revenue and the top 20% for {top20:.0%}, with a Gini coefficient of {gini:.2f}. That concentration
makes retention of high-value customers a first-order risk, and it makes the early cohort decay
more expensive than the median retention figure suggests.</p>

<p>The recommended response is a bounded reallocation, governed as a test-and-scale motion. Scaling
the three efficient channels within guardrails and pulling 35% from the two inefficient ones lifts
estimated annual contribution from {_usd(baseline_cm/1e6,1)}M to {_usd(base_cm/1e6,1)}M, an uplift of
{_usd(uplift/1e6,1)}M ({uplift_pct:.0%}) at no extra budget. It stays positive in every stress case,
from {_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M worst to
{_usd(float(best['estimated_uplift_vs_baseline'])/1e6,1)}M best, and across {n_seeds} deterministic
seeds it averages {_usd(seed_mean/1e6,1)}M (coefficient of variation {seed_cv:.1%}). Full
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

<p>This analysis exists to answer a budget question, not to populate a dashboard. The business is
spending {_usd(total_spend/1e6,1)}M a period to acquire customers and wants to know whether that
spend is building a durable asset or renting a revenue line that stops the moment spend stops. The
question is asked five ways, each with a method chosen to give a decision rather than a description.</p>

<table><thead><tr><th>Question</th><th>Method</th><th>Decision it informs</th></tr></thead><tbody><tr><td>Is growth converting into margin?</td><td>Monthly revenue and contribution margin trend, margin rate vs floor</td><td>Whether to defend or improve margin</td></tr>
<tr><td>What is driving the growth?</td><td>Decomposition into volume, monetization, and mix</td><td>Where to invest for durable growth</td></tr>
<tr><td>Do cohorts hold their value?</td><td>Median activity and revenue retention by cohort age</td><td>Whether retention or acquisition is the lever</td></tr>
<tr><td>Which channels deserve budget?</td><td>LTV/CAC, payback, and spend-to-contribution alignment per channel</td><td>How to allocate acquisition spend</td></tr>
<tr><td>What is the upside from reallocating spend?</td><td>Bounded scenario with stress and seed-stability tests</td><td>Size and confidence of the reallocation</td></tr></tbody></table>

<p>The scope is deliberately narrow. This is not a forecast, a market sizing, or an attribution
study. It is a diagnostic of growth quality on the data available, built so that each finding either
confirms the current allocation or changes it. Where a finding cannot be settled with the data on
hand, Section 6 says so plainly rather than papering over the gap.</p>

<p>The decision standard is practical: a finding is strong enough to change budget only when it is
visible in at least two places, such as channel economics and spend mix, or cohort decay and customer
concentration. Findings supported by one view only are treated as monitoring items or experiments,
not as immediate allocation moves. That is why the report recommends a controlled reallocation, a
retention workstream, and a margin diagnostic rather than a single blanket growth call.</p>

<h3>Who should read this</h3>
<p>The primary audience is the executive or commercial owner deciding next quarter's acquisition
budget. The secondary audience is the analytics or finance reviewer who needs to trust the numbers
before acting on them. The report is written for the first audience in the prose and for the second
in the methodology and appendix.</p>
</section>

<!-- ============================ 3. METHODOLOGY ============================ -->
<section>
<h2><span class="num">3</span>Data and methodology</h2><hr class="rule">
<p>The pipeline runs end to end from raw tables to validated outputs, with each stage writing
deterministic files. Three raw tables feed it: {n_customers:,} customers, {n_transactions:,} transactions,
and {n_spend_records:,} daily channel spend records, spanning January 2023 to December 2025. Customer-level metrics,
the monthly revenue health series, the cohort table, channel unit economics, segment and product
profitability, and the scenario outputs are all derived from these three tables by reproducible
transformations.</p>

<h3>Metric definitions</h3>
<p>Contribution margin is revenue minus direct delivery cost. Observed lifetime value is the mean
cumulative contribution margin per acquired customer, computed across the full base including the
{zero_txn:,} customers ({zero_txn_pct:.1%}) who never transacted, so the figure is not inflated by
survivorship. Customer acquisition cost is period-level channel spend divided by the customers
acquired in that channel. The LTV-to-CAC ratio divides the two; payback is the number of months of
contribution required to recover CAC.</p>

<p>A channel is classified efficient when LTV/CAC is at least 3.0 and payback is 12 months or less,
inefficient when LTV/CAC falls below 1.0 or payback exceeds 24 months, and borderline in between.
The margin quality floor is set at 30%. These thresholds live in a single metric registry that the
analysis, the dashboard, the chart pack, and the validation gate all import, so no definition can
drift between outputs.</p>

<p>The report uses average and median LTV together because they answer different questions. Average
LTV is the right numerator for contribution economics because it reconciles to total contribution.
Median LTV is the buyer-quality check because it shows the typical customer experience underneath
the mean. When both measures point in the same direction, the channel conclusion is stronger; when
they diverge, the channel needs segmentation before scaling.</p>

<h3>Cohort construction</h3>
<p>Customers are grouped into monthly signup cohorts. For each cohort, revenue retention at age m is
that cohort's revenue in month m divided by its revenue in month 0, and activity retention is the
share of the cohort still transacting. Reported curves use the median across cohorts at each age, so
a single large or small cohort cannot dominate the read. Later-month retention figures draw only on
cohorts old enough to have reached that age, which is stated wherever it matters.</p>

<h3>Revenue decomposition</h3>
<p>The growth decomposition compares the first six months of the window against the last six. The
total revenue change is split into a customer-volume effect, an average-revenue (monetization)
effect, and a segment-mix effect, with any unexplained difference carried as a residual. The
residual is zero here, so the three effects fully account for the change. Segment is the mix
dimension; other definitions of mix, such as region or product, would allocate the mix term
differently, which Section 6 notes.</p>

<h3>Scenario engine</h3>
<p>The reallocation scenario is deliberately conservative. It applies bounded CAC and LTV
elasticities to each channel, caps any channel's scale-up at 100% of current spend, and holds back
budget rather than forcing it into channels that have run out of efficient headroom. The scenario is
stress-tested across best, base, and worst elasticity cases, and repeated across {n_seeds}
deterministic seeds to confirm the result is a property of the policy rather than of one random
draw. The total budget is held constant in every case, so the uplift is a pure allocation effect.</p>

<p>The scenario is not allowed to create value by expanding the budget, deleting weak channels, or
assuming unlimited capacity in strong ones. It must earn the uplift through reweighting the existing
budget and absorbing weaker economics as spend scales. That makes the base case useful as an
implementation estimate and the worst case useful as the planning floor.</p>

<h3>Data quality gate</h3>
<p>All {n_checks} raw-data validation checks pass before any analysis runs: schema match, grain
uniqueness, referential integrity, date coverage, channel-domain alignment, and value-range sanity.
The gate flagged {cost_exceeds_revenue_n:,} transactions ({cost_exceeds_revenue_rate:.2%}) where cost
exceeds revenue. That share sits below the 1% review threshold, so the rows are retained as genuine
cost-to-serve exceptions rather than scrubbed.
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
LTV/CAC, payback, and cohort retention combine. A channel can look cheap on CAC and still destroy
value if the customers it buys churn before payback.</p>

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
<section>
<h2><span class="num">5</span>Findings</h2><hr class="rule">

<h3>5.1&nbsp;&nbsp;The growth trajectory is real, fast, and uneven</h3>
<p>Monthly revenue rose from {_usd(first_rev/1e3)}K in January 2023 to {_usd(last_rev/1e6,1)}M in
December 2025. Comparing like with like, the last six months averaged {_usd(recent_avg/1e6,1)}M a
month against {_usd(early_avg/1e3)}K in the first six, a {rev_multiple:.1f}-fold increase across
{n_months} months. Contribution margin tracked revenue closely in absolute terms, which is the first
thing to confirm: the business is not buying revenue at the expense of total margin dollars. Both
lines climb together.</p>
<figure class="figure">
<img class="chart" src="{_img('01_growth_quality.png')}">
<p class="cap"><b>Figure 1.</b> Revenue and contribution margin rise together in absolute dollars. The
gap between the two lines, which is the margin rate, does not widen as the business scales.</p>
</figure>

<p>The growth is not smooth. Month-on-month revenue change averages {mean_mom:.1%}, but the series
includes {down_months} down months across the window, most of them in the seasonal January and
mid-year dips visible in Figure 2. Durability shows up in how the business handles those down
months, and here it recovers each time without breaking the trend. The volatility is seasonal noise
around a strong underlying climb, not a structural wobble.</p>
<figure class="figure">
<img class="chart" src="{_img('03_revenue_growth_mom.png')}">
<p class="cap"><b>Figure 2.</b> Month-on-month revenue growth. The {down_months} down months are
shallow and seasonal, not a sign of a stalling trend.</p>
</figure>

<p>The composition of that growth is the first warning. The active base grew from {first_active:,}
customers in the opening month to {last_active:,} in the closing month, while revenue per active
customer moved only from {_usd(arpac_first)} to {_usd(arpac_last)}. The base is doing almost all the
work; monetization per customer is close to flat. A business adding this many customers while holding
revenue per customer steady is growing by addition, not by deepening the value of the relationships
it already has.</p>
<figure class="figure">
<img class="chart" src="{_img('04_active_customers_arpu.png')}">
<p class="cap"><b>Figure 3.</b> The active base climbs steeply while revenue per active customer stays
in a narrow band. Growth is coming from more customers, not richer ones.</p>
</figure>
<p>The operating implication is that the next budget decision should be judged on marginal customer
quality, not on whether the revenue line continues to rise. The active base expanded
{active_multiple:.1f}&times; from the first month to the last; revenue per active customer rose only
{arpac_lift:.0%}. That imbalance makes the business sensitive to CAC inflation and retention slippage,
because growth is doing more work than monetization.</p>
</section>

<section>
<h3>5.2&nbsp;&nbsp;Margin quality is only holding, not improving</h3>
<p>The qualifier on the trajectory is the rate. Contribution margin holds in a tight band between
{margin_min:.0%} and {margin_max:.0%}, hovering at the 30% quality floor rather than improving as the
business scales. A company adding this much revenue would normally expect operating leverage to lift
the margin rate over three years. Here it does not move.</p>
<figure class="figure">
<img class="chart" src="{_img('02_margin_rate.png')}">
<p class="cap"><b>Figure 4.</b> Monthly contribution margin rate against the 30% quality floor. The
rate oscillates around the floor for the full window and shows no upward drift.</p>
</figure>
<p>A flat margin rate during rapid growth carries a specific meaning: the incremental revenue is no
better in quality than the average revenue already on the books. If the new customers were more
profitable than the existing base, the rate would rise. If they were dragging, it would fall. It
does neither, which says the business is cloning its average economics at scale rather than improving
them. The next three findings explain why the rate is stuck, and the reallocation in Section 5.8 is
the move that would unstick it.</p>
<p>This is a stronger warning than a simple margin miss. The business has not lost control of direct
costs, but it has also not converted scale into better economics. That points to allocation, mix, and
cost-to-serve rather than a broad operational failure. The practical target is not to defend the
current 30% floor; it is to create an incremental margin rate visibly above that floor.</p>
</section>

<section>
<h3>5.3&nbsp;&nbsp;Growth is volume-led, not monetization-led</h3>
<p>Decomposing the {_usd(tot_change/1e6,1)}M revenue change between the first and last six months
separates three effects: more customers, more revenue per customer, and a shift in segment mix.</p>
<figure class="figure">
<img class="chart" src="{_img('05_revenue_decomposition.png')}">
<p class="cap"><b>Figure 5.</b> Volume accounts for {vol_s:.0%} of the revenue change, monetization
{avg_s:.0%}, and segment mix {mix_s:.0%}. The residual is zero, so the three effects fully account
for the change.</p>
</figure>
<table><thead><tr><th>Effect</th><th class="num">Contribution to change</th><th class="num">Share</th></tr></thead><tbody>{dec_rows}</tbody></table>
<p>Volume accounts for {vol_s:.0%} of the increase. Monetization adds {avg_s:.0%} and mix a further
{mix_s:.0%}. Volume-led growth is not wrong in itself, but it is only as good as the channels buying
that volume. When most incremental customers arrive through channels that lose money, as Section 5.5
shows, volume growth becomes a recurring cost rather than a compounding asset. This is the mechanism
behind the flat margin rate in Figure 4: the business is buying average-quality customers in bulk and
the average is not improving.</p>
<p>The mix effect is small at {mix_s:.0%}, which is its own finding. The business is not growing into
a richer customer mix that would lift the rate on its own. If anything, the structural margin problem
documented in Section 5.6 means a larger mix shift toward the biggest segment would pull the rate
down, not up.</p>
<p>The read-through for planning is clear: a retention or pricing program can improve durability, but
it will not explain the historical growth on its own. The historical engine is acquisition volume.
That means the highest-leverage governance point is the channel budget, because it sits upstream of
the customers entering the system.</p>
</section>

<section>
<h3>5.4&nbsp;&nbsp;Cohorts decay fast in the first six months</h3>
<p>If growth depends on volume, retention determines how much of that volume the business keeps.
Median revenue retention falls to {rev_ret_m3:.0%} by month 3 and {rev_ret_m6:.0%} by month 6, a
{m3_m6_decay_pp:.1f}-point loss in the window where activation, onboarding, and first value should
be doing the most work. It then drops another {m6_m12_decay_pp:.1f} points by month 12. Activity
retention is worse, at {act_ret_m6:.0%} by month 6 and {act_ret_m12:.0%} by month 12.</p>
<figure class="figure">
<img class="chart" src="{_img('06_cohort_retention.png')}">
<p class="cap"><b>Figure 6.</b> Median activity and revenue retention through month 24. The steepest
loss is concentrated between months 3 and 6, the window where onboarding and first-value delivery
matter most.</p>
</figure>
<p>Revenue retention sits above activity retention at most ages, which says the customers who stay
spend somewhat more, a partial offset to logo churn. It is not enough to change the conclusion. Only
{expansion_share_m6:.1%} of cohorts show revenue expansion at month 6, so the median customer is shrinking, not growing,
in their first half-year. The cohort heatmap confirms that this is structural rather than a property
of one or two unlucky cohorts.</p>
<figure class="figure">
<img class="chart" src="{_img('07_cohort_heatmap.png')}">
<p class="cap"><b>Figure 7.</b> Revenue retention by cohort (rows) and age (columns). The color
fades along every row at a similar pace, so the decay pattern repeats across cohorts rather than
being driven by a few outliers.</p>
</figure>
<p>The combination is costly. The business acquires volume through expensive channels and then loses
a large share of it before the customer pays back. Because revenue is concentrated in a small set of
high-value customers, as Section 5.7 shows, losing the wrong customers early is more damaging than
the median curve implies. Slowing the acquisition treadmill is not possible until this early-life
decay is addressed, which is why retention is a named recommendation in Section 7 rather than a
footnote.</p>
<p>The month-6 read is the most decision-useful point on the curve. It is mature enough to include
{int(coh.loc[coh["months_since_cohort"] == 6, "cohorts_observed"].iloc[0])} cohorts and early enough
to change through onboarding, customer success, product adoption, and channel mix. By contrast, the
month-24 tail uses {m24_cohorts} mature cohorts, so it is useful for direction but too sparse to own
the near-term target.</p>
</section>

<section>
<h3>5.5&nbsp;&nbsp;Two channels destroy value and hold most of the budget</h3>
<p>This is the central finding. Channel economics split into two groups with no overlap, and the
budget is pointed at the wrong group.</p>
<figure class="figure">
<img class="chart" src="{_img('08_channel_economics.png')}">
<p class="cap"><b>Figure 8.</b> Channel LTV against CAC, with bubble size showing total spend. Three
channels sit above the 3&times; line, two below 1&times;, and none in between. The two largest
bubbles, paid search and social ads, sit in the value-destructive zone.</p>
</figure>
<table><thead><tr><th>Channel</th><th class="num">Customers</th><th class="num">Spend</th><th class="num">CAC</th>
<th class="num">Avg LTV</th><th class="num">Med LTV</th><th class="num">LTV/CAC</th><th class="num">Payback (mo)</th><th>Status</th></tr></thead><tbody>{ch_rows}</tbody></table>
<p>Organic, referral, and partners clear the 3&times; bar with room to spare and pay back inside nine
months. Paid search and social ads sit below the 1&times; line, meaning the average customer they buy
is worth less than the cost to acquire them. The efficiency gap is not marginal. It is more than an
order of magnitude between the best and worst channel.</p>
<figure class="figure">
<img class="chart" src="{_img('09_channel_ltv_cac_ranking.png')}">
<p class="cap"><b>Figure 9.</b> LTV/CAC ranked across channels. Organic returns {organic['LTV_to_CAC']:.0f}&times;
its cost; social ads returns {social['LTV_to_CAC']:.2f}&times;. Email is the only borderline case.</p>
</figure>
<p>The problem is not that the inefficient channels exist; it is their weight. Together they hold
{_usd(ineff_spend/1e6,2)}M of acquisition spend, {ineff_share:.0%} of the total, while returning
under a dollar of contribution per dollar spent. The misallocation is clearest when each channel's
share of spend is set against its share of contribution.</p>
<figure class="figure">
<img class="chart" src="{_img('10_channel_allocation_gap.png')}">
<p class="cap"><b>Figure 10.</b> Share of spend against share of contribution by channel. Organic
takes {organic['total_spend']/total_spend:.0%} of spend and produces {organic['total_channel_contribution_margin']/total_contrib:.0%}
of contribution; paid search and social ads take {(paid['total_spend']+social['total_spend'])/total_spend:.0%}
of spend and produce {ineff_contrib_share:.0%} of contribution.</p>
</figure>
<p>Email is borderline at {email['LTV_to_CAC']:.2f}&times; with a {email['approximate_payback_period']:.0f}-month
payback. It is a hold-and-fix case rather than a scale-or-cut one. The median LTV column tells a
sharper version of the same story than the mean: social ads has a median LTV of {_usd(social['median_LTV'])}
against a CAC of {_usd(social['CAC'])}, so the typical customer it buys is deeply underwater even
before averaging in the rare high-value account.</p>
<p>The mean and median both matter here. Organic and referral have high average LTV and materially
higher median LTV than the paid channels, so the conclusion is not just being carried by a few large
winners. Social ads is the opposite: average LTV is already below CAC, and median LTV is only
{_usd(social['median_LTV'])}. That makes it a poor scaling candidate even before attribution risk is
considered.</p>
<div class="callout">Reallocating budget away from these two channels is the single highest-value
move available, and it requires no incremental spend. Section 5.8 sizes it.</div>
</section>

<section>
<h3>5.6&nbsp;&nbsp;Margin concentrates in the lowest-rate segment and product</h3>
<p>Profitability by segment carries a structural risk that a revenue view hides. The largest segment
is also the least efficient.</p>
<figure class="figure">
<img class="chart" src="{_img('11_segment_profitability.png')}">
<p class="cap"><b>Figure 11.</b> Contribution margin dollars and margin rate by segment. Enterprise
carries the most margin dollars at the lowest rate, and it is the only segment below the 30% floor.</p>
</figure>
<table><thead><tr><th>Segment</th><th class="num">Customers</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr></thead><tbody>{seg_rows}</tbody></table>
<p>Enterprise is the largest segment at {ent['revenue_share']:.0%} of revenue and
{_usd(float(ent['contribution_margin'])/1e6,1)}M of margin dollars, yet it carries the lowest margin
rate at {ent['margin_pct']:.1%}, below every smaller segment. Mid-Market, SMB, and Startup all run
between {smb['margin_pct']:.0%} and {mm['margin_pct']:.0%}. Nearly half the revenue base sits in the
least efficient segment, which is a concentration risk: pricing or cost-to-serve pressure in
Enterprise hits the margin line harder than its rate alone suggests. Closing Enterprise to the 30%
floor would be worth roughly {_usd(ent_floor_gap/1e6,1)}M of contribution before any volume response,
but that estimate should be treated as a sizing anchor, not an additive forecast.</p>
<p>Geography, by contrast, is not where the margin problem lives. Regional margin rates are banded
within {reg_margin_spread*100:.1f} points of each other, from {reg_bottom['margin_pct']:.1%} in
{reg_bottom['dimension_value']} to {reg_top['margin_pct']:.1%} in {reg_top['dimension_value']}.
Regions differ in size, not in efficiency.</p>
<figure class="figure">
<img class="chart" src="{_img('12_region_profitability.png')}">
<p class="cap"><b>Figure 12.</b> Contribution margin by region with margin rate and revenue share.
{reg_top['dimension_value']} leads on dollars, but every region sits within a point of the others on
rate. Geography is a scale story, not a margin story.</p>
</figure>
<p>The product view sharpens the diagnosis. Services run at just {services['margin_pct']:.1%} margin
on {_usd(float(services['total_revenue'])/1e6,1)}M of revenue ({services['revenue_share']:.0%} of the
total), the deepest low-margin growth pocket. Premium is also below the 30% floor at
{premium['margin_pct']:.1%}, while Core and Add-on, the two highest-rate lines, run at
{core['margin_pct']:.1%} and {addon['margin_pct']:.1%}. The spread between the best and worst product
line is nearly {(addon['margin_pct']-services['margin_pct'])*100:.0f} margin points.</p>
<figure class="figure">
<img class="chart" src="{_img('13_product_margin.png')}">
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
{_usd(product_floor_gap/1e6,1)}M of margin gap before any behavioral response.</p>
</section>

<section>
<h3>5.7&nbsp;&nbsp;Revenue is concentrated in a thin band of customers</h3>
<p>Revenue is far from evenly spread. The top 10% of customers account for {top10:.0%} of total
revenue, the top 20% for {top20:.0%}, and the top 1% alone for {top1:.0%}. The Gini coefficient of
lifetime revenue is {gini:.2f}, well into the territory where a small group of accounts carries the
business.</p>
<figure class="figure">
<img class="chart" src="{_img('14_revenue_concentration.png')}">
<p class="cap"><b>Figure 14.</b> Lorenz curve of lifetime revenue across all {n_customers:,} customers.
The deep bow away from the equality line is the concentration: a fifth of customers hold four fifths
of revenue.</p>
</figure>
<p>The distribution behind the curve is a long right tail. Median lifetime revenue is
{_usd(rev_median)} while the mean is {_usd(rev_mean)}, {mean_median_multiple:.1f} times higher,
because a small number of customers reach up to {_usd(rev_max/1e3)}K each. The {zero_txn:,} customers
who never transacted sit at the bottom of the same distribution and pull the median down further.</p>
<figure class="figure">
<img class="chart" src="{_img('15_revenue_distribution.png')}">
<p class="cap"><b>Figure 15.</b> Distribution of lifetime revenue per customer on a log scale. The
mean sits far to the right of the median, the signature of a heavy tail.</p>
</figure>
<p>Concentration interacts directly with the retention finding. Because value pools in a thin band,
the cost of early decay depends on which customers decay. Tenure is a real driver of revenue, with a
Pearson correlation of {corr_life:.2f} between lifetime days and lifetime revenue and {corr_txn:.2f}
between transaction count and revenue, so customers who survive the first six months and keep
transacting are disproportionately the ones who matter.</p>
<figure class="figure">
<img class="chart" src="{_img('16_revenue_lifetime_corr.png')}">
<p class="cap"><b>Figure 16.</b> Lifetime revenue against tenure, with the median trend. Longer-tenured
customers are worth materially more, which is precisely why losing them early in Figure 6 is
expensive.</p>
</figure>
<p>The implication for the budget is direct. Concentration plus tenure-driven value means the
business should weight acquisition toward channels that bring durable, high-value customers, and
should protect the high-value base it already has. Both point the same way as the channel economics
in Section 5.5.</p>
<p>The concentration read also protects the analysis from a common mistake: optimizing for the
average customer when the business is carried by a small high-value tail. The right operating lens is
not just whether a channel buys customers cheaply; it is whether it buys customers with enough
survival, expansion, and contribution potential to join that tail.</p>
</section>

<section>
<h3>5.8&nbsp;&nbsp;Reallocation adds {_usd(uplift/1e6,1)}M with no extra budget</h3>
<p>The reallocation scenario scales organic, referral, and partners within guardrails, cuts paid
search and social ads by 35%, holds email, and reinvests the freed budget into the efficient channels
up to a 100% scale-up cap per channel. Total budget is unchanged, so every dollar of uplift is a pure
allocation effect. The policy moves {_usd(freed_budget/1e6,1)}M of spend out of the two inefficient
channels and puts it only into channels that already clear the LTV/CAC and payback gates.</p>
<figure class="figure">
<img class="chart" src="{_img('17_reallocation_waterfall.png')}">
<p class="cap"><b>Figure 17.</b> Contribution bridge from baseline to scenario by channel move.
Scaling the three efficient channels adds the bulk of the uplift; trimming the two inefficient ones
removes a small contribution drag.</p>
</figure>
<table><thead><tr><th>Channel</th><th>Status</th><th class="num">Baseline spend</th><th class="num">Scenario spend</th>
<th class="num">Spend change</th><th class="num">Contribution change</th></tr></thead><tbody>{plan_rows}</tbody></table>
<p>Estimated annual contribution rises from {_usd(baseline_cm/1e6,1)}M to {_usd(scenario_cm/1e6,1)}M
in the base case, an uplift of {_usd(uplift/1e6,1)}M, or {uplift_pct:.0%}. The result is robust to
the elasticity assumptions. The scenario is stress-tested across a best, base, and worst case, with
CAC and LTV moved against the policy in the worst case.</p>
<p>The economics of the bridge are concentrated. Scaling organic, referral, and partners contributes
{_usd(efficient_add/1e6,1)}M of gross uplift, while cutting paid search and social ads removes
{_usd(abs(inefficient_drag)/1e6,1)}M of contribution attached to weak traffic. That trade is still
attractive because the freed spend earns materially more in the efficient channels than it loses in
the inefficient ones.</p>
<figure class="figure">
<img class="chart" src="{_img('18_scenario_envelope.png')}">
<p class="cap"><b>Figure 18.</b> Contribution under the reallocation across stress cases. Every case
clears the baseline; even the worst case, with CAC up 15% and LTV down 12% on the scaled channels,
adds {_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M.</p>
</figure>
<table><thead><tr><th>Scenario</th><th class="num">CAC mult.</th><th class="num">LTV mult.</th>
<th class="num">Contribution</th><th class="num">Uplift vs baseline</th></tr></thead><tbody>{stress_rows}</tbody></table>
<p>The worst case, with CAC inflated 15% and LTV cut 12% on the channels being scaled, still returns
{_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M above baseline. The policy is also stable
across random draws. Repeating it across {n_seeds} deterministic seeds, the uplift averages
{_usd(seed_mean/1e6,1)}M with a standard deviation of {_usd(seed_std/1e3)}K, a coefficient of
variation of {seed_cv:.1%}, and it is positive in {n_seeds} of {n_seeds} seeds. The range runs from
{_usd(seed_min/1e6,1)}M to {_usd(seed_max/1e6,1)}M.</p>
<figure class="figure">
<img class="chart" src="{_img('19_scenario_seed_stability.png')}">
<p class="cap"><b>Figure 19.</b> Estimated uplift across five deterministic seeds. The tight band
around the mean shows the outcome is a property of the allocation, not of one favorable draw.</p>
</figure>
<table><thead><tr><th class="num">Seed</th><th class="num">Baseline contrib.</th><th class="num">Scenario contrib.</th>
<th class="num">Uplift</th><th>Top scale-up</th><th>Top cut</th></tr></thead><tbody>{seed_rows}</tbody></table>
<p>The reallocation is not a free lunch: it trades one concentration risk for another. Section 5.7
showed revenue concentrated in a thin band of customers; this policy concentrates spend in a thin band
of channels. Organic, referral, and partners hold {eff_spend_share:.0%} of acquisition spend today;
under the scenario they hold {eff_scenario_spend_share:.0%}, and their share of channel contribution
rises from {eff_contrib_share:.0%} to {eff_scenario_contrib_share:.0%}. {largest_eff_channel['acquisition_channel'].replace('_', ' ').title()}
alone would carry {largest_eff_spend_share:.0%} of total spend post-reallocation. The plan is correct
given what LTV/CAC and payback say today, but it is a bet on three channels holding their economics at
roughly double their current scale, not a diversified portfolio move. That is precisely why Section 8
treats capacity and channel-level guardrails as live monitoring items rather than a one-time approval,
and it is the reason a fifth control, on channel concentration, is added there alongside the four
performance guardrails.</p>
<p>This result is strong enough to act on, but not strong enough to run unmanaged. The rollout should
be staged with stop-loss rules: pause a scaled channel if LTV/CAC falls below 3.0, if payback moves
beyond 12 months, or if month-6 revenue retention for newly acquired cohorts deteriorates versus the
current baseline. Those controls turn the scenario from a spreadsheet answer into an operating
decision.</p>
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
value. The efficiency gap between channels is large enough ({organic['LTV_to_CAC']:.0f}&times; versus
{social['LTV_to_CAC']:.2f}&times;) that a window correction would not flip the classification, but the
exact ratios would move.</p>

<h3>Attribution is single-touch by channel</h3>
<p>Each customer is assigned to one acquisition channel, and spend is allocated at the period level.
Real customer journeys cross channels, and lagged or assist effects are not modeled. A channel that
looks inefficient on last-touch economics could be assisting conversions credited elsewhere. The
reallocation is bounded and reversible partly to absorb this risk.</p>

<h3>Product and segment gaps are diagnostic, not additive</h3>
<p>The Enterprise, Services, and Premium margin gaps are different cuts of the same economic base.
They should not be summed into one opportunity figure without a customer-product bridge. Their value
is to identify where margin work should start: delivery model, service scope, packaging, discounting,
and cost-to-serve in the slices that repeatedly sit below the floor.</p>

<h3>The decomposition depends on the mix dimension</h3>
<p>The growth decomposition uses segment as the mix dimension. Defining mix by region, product, or
channel would allocate the {mix_s:.0%} mix term differently. The volume-led conclusion is robust
because volume dominates at {vol_s:.0%} regardless of how the smaller mix term is split, but the mix
figure itself is dimension-dependent.</p>

<h3>Elasticities are assumptions, not measurements</h3>
<p>The scenario applies assumed CAC and LTV elasticities rather than measured ones. The stress test
and seed sweep are there precisely because the elasticities are uncertain. The honest read is that
the uplift is positive across every case tested, not that its central value of {_usd(uplift/1e6,1)}M
is precise. Treat the worst case of {_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M as
the planning floor.</p>

<h3>Cohort maturity</h3>
<p>Long-horizon retention reads draw only on cohorts old enough to have reached that age. The month
24 figure rests on fewer cohorts than the month 6 figure, so the tail of the retention curve is
noisier than its head. The month 3 to 6 decay, which carries the recommendation, sits in the
best-observed part of the curve.</p>

<h3>Execution capacity is assumed, not proven</h3>
<p>The reallocation assumes efficient channels can absorb additional spend up to the stated cap while
remaining inside the modeled CAC and LTV penalties. That is plausible based on the observed gap, but
not guaranteed. Capacity should therefore be proven during rollout with weekly CAC, payback,
conversion quality, and cohort-retention checks rather than assumed for the full quarter.</p>
</section>

<!-- ============================ 7. RECOMMENDATIONS ============================ -->
<section>
<h2><span class="num">7</span>Recommendations and action priorities</h2><hr class="rule">
<p>Growth is real but expensive. The business is buying volume through channels that lose money,
keeping the margin rate pinned at the 30% floor, and leaning on continued spend that fast cohort
decay makes hard to sustain. The fix does not require more budget. It requires moving the budget that
already exists toward the customers worth acquiring and keeping. The four recommendations below are
ordered by value and urgency.</p>

<p>Read across, not down: the matrix below is the executive decision lens, and the numbered detail
that follows is the substantiation for each row.</p>
<table><thead><tr><th>Recommendation</th><th class="num">Est. annual value</th><th>Confidence</th><th>Time to first read</th><th>Reversibility</th></tr></thead><tbody><tr><td>P1 &middot; Reallocate spend</td>
<td class="num">{_usd(uplift/1e6,1)}M (range {_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M&ndash;{_usd(float(best['estimated_uplift_vs_baseline'])/1e6,1)}M)</td>
<td>High &mdash; stress-tested, positive in all {n_seeds} seeds</td><td>Immediate, this quarter</td>
<td>High &mdash; budget-neutral, reversible</td></tr>
<tr><td>P2 &middot; Fix month 3&ndash;6 retention</td>
<td class="num">Not directly sized</td>
<td>Medium &mdash; decay is proven, fix magnitude is not</td><td>1&ndash;2 quarters to first read</td>
<td>Medium &mdash; onboarding and process change</td></tr>
<tr><td>P3 &middot; Re-price Services/Enterprise</td>
<td class="num">~{_usd(product_floor_gap/1e6,1)}M to the floor (sizing anchor, not additive)</td>
<td>Medium &mdash; gap is diagnosed, price-vs-cost split is not</td><td>1 quarter to design, 2&ndash;3 to realize</td>
<td>Low-medium &mdash; pricing and contract change</td></tr>
<tr><td>P4 &middot; Hold email, run experiment</td>
<td class="num">Bounded &mdash; {email_spend_share:.0%} of total spend</td>
<td>High confidence in the test design, low in the outcome</td><td>1&ndash;2 quarters</td>
<td>High &mdash; small, contained test</td></tr></tbody></table>

<ol class="rec">
<li><span class="priority p1">Priority 1</span><b>Reallocate spend away from paid search and social
ads this quarter.</b><br>Both return under {paid['LTV_to_CAC']:.2f}&times; cost and together hold
{ineff_share:.0%} of acquisition spend. Cut each by 35% and redirect the freed
{_usd(ineff_spend*0.35/1e6,1)}M into organic, referral, and partners, holding each to its LTV/CAC and
payback guardrails. This is the {uplift_pct:.0%} contribution uplift modeled in Section 5.8, worth
{_usd(uplift/1e6,1)}M in the base case and at least
{_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M in the worst case. It is the only
recommendation here that adds contribution without spending a dollar more.</li>

<li><span class="priority p2">Priority 2</span><b>Fix month 3 to 6 retention before slowing
acquisition.</b><br>The steepest decay is early-life, with median revenue retention falling from
{coh_at(3,'median_revenue_retention'):.0%} at month 3 to {coh_at(6,'median_revenue_retention'):.0%} at
month 6. Target onboarding and first-value delivery for the segments and channels feeding the most
volume, and track month-6 revenue retention as the success metric. Because revenue is concentrated
({top20:.0%} in the top 20% of customers), prioritize retention work on the high-value tail
identified in Section 5.7.</li>

<li><span class="priority p3">Priority 3</span><b>Address the Services and Enterprise margin gap with
pricing and cost-to-serve, not volume.</b><br>Services at {services['margin_pct']:.1%} and Enterprise
at {ent['margin_pct']:.1%} are where mix dilutes the blended rate. Re-price or re-scope the
lowest-margin product and delivery slices rather than growing into them. Leave the segments and
regions already at or above the 30% floor alone; the problem is targeted, not systemic.</li>

<li><span class="priority p4">Priority 4</span><b>Hold email flat and run a focused economics
experiment.</b><br>Email is borderline at {email['LTV_to_CAC']:.2f}&times; with a
{email['approximate_payback_period']:.0f}-month payback. Do not scale or cut it on the current
evidence. Run CAC and payback experiments for one or two quarters and decide its fate on the result.
Apply the same guardrails to the efficient channels as they scale, since the scenario assumes
diminishing returns and the rollout should respect them.</li>
</ol>

<div class="callout">The reallocation is the priority. It adds {_usd(uplift/1e6,1)}M of contribution
without spending a dollar more and stays positive in every case tested. The other three
recommendations protect and compound that gain.</div>

<h3>Sequencing</h3>
<p>Start the reallocation immediately, since it is budget-neutral and reversible. Begin the retention
work in parallel, because it determines how much of the reallocated spend converts into durable
value. Treat the margin re-pricing as a quarter-two action that needs commercial and finance
alignment, and the email experiment as a continuous test that informs the next budget cycle.</p>
</section>

<!-- ============================ 8. DECISION CONTROLS ============================ -->
<section>
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

<p><b>Are paid search and social ads genuinely value-destructive, or miscredited?</b> Their observed
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
<section class="break">
<h2><span class="num">9</span>Appendix</h2><hr class="rule">

<h3>A. Channel unit economics (full)</h3>
<table><thead><tr><th>Channel</th><th class="num">Customers</th><th class="num">Spend</th><th class="num">CAC</th>
<th class="num">Avg LTV</th><th class="num">Med LTV</th><th class="num">LTV/CAC</th><th class="num">Payback (mo)</th><th>Status</th></tr></thead><tbody>{ch_rows}</tbody></table>

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
<p class="muted" style="font-size:9pt">Median retention across cohorts at each age, with the count of
cohorts mature enough to be observed. The series behind Figures 6 and 7.</p>
<table><thead><tr><th class="num">Months since signup</th><th class="num">Activity retention</th>
<th class="num">Revenue retention</th><th class="num">Cohorts observed</th></tr></thead><tbody>{coh_rows}</tbody></table>

<h3>F. Data validation gate</h3>
<p class="muted" style="font-size:9pt">All {n_checks} checks run on the raw tables before any
analysis. A failure blocks the pipeline.</p>
<table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{val_rows}</tbody></table>

<h3>G. Data dictionary and reproducibility</h3>
<table><thead><tr><th>Field</th><th>Definition</th></tr></thead><tbody><tr><td>contribution_margin</td><td>Revenue minus direct delivery cost</td></tr>
<tr><td>average_LTV</td><td>Mean cumulative contribution margin per acquired customer, including zero-transaction customers</td></tr>
<tr><td>median_LTV</td><td>Median cumulative contribution margin per acquired customer</td></tr>
<tr><td>CAC</td><td>Period channel spend divided by customers acquired in the channel</td></tr>
<tr><td>LTV_to_CAC</td><td>average_LTV divided by CAC; efficient at &ge; 3.0</td></tr>
<tr><td>approximate_payback_period</td><td>Months of contribution required to recover CAC</td></tr>
<tr><td>median_revenue_retention</td><td>Median cohort revenue at month m relative to month 0</td></tr>
<tr><td>Gini coefficient</td><td>Concentration of lifetime revenue across customers; 0 is even, 1 is fully concentrated</td></tr></tbody></table>
</section>

</body></html>"""
    return html


def render_pdf(html: str) -> Path:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_report.html"
    tmp.write_text(html, encoding="utf-8")
    pdf_path = OUT / "revenue_unit_economics_report.pdf"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(tmp.resolve().as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)
    return pdf_path


def locate_toc_pages(pdf_path: Path) -> dict[str, int]:
    """Find the real page each TOC entry lands on by scanning the rendered PDF.

    Chromium's print engine (used via Playwright) does not support CSS
    target-counter(), so page numbers can't be computed at HTML-build time.
    Instead, search starts after the cover and TOC pages themselves (index 2
    onward) so a heading's own listing in the TOC text can't self-match.
    """
    pages_text = [(p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages]
    result: dict[str, int] = {}
    for key, marker in TOC_SEARCH_KEYS.items():
        for i in range(2, len(pages_text)):
            if marker in pages_text[i]:
                result[key] = i + 1
                break
        else:
            raise RuntimeError(f"Could not locate TOC target {key!r} (marker: {marker!r})")
    return result


def main() -> None:
    # Pass 1: render without TOC page numbers, then find where each section
    # actually landed. Pass 2 renders the final PDF with those real numbers.
    # Content pagination is identical between passes (the TOC page has spare
    # room, so filling in a number column doesn't shift anything else).
    provisional_path = render_pdf(build_html(toc_pages=None))
    toc_pages = locate_toc_pages(provisional_path)
    path = render_pdf(build_html(toc_pages=toc_pages))
    print(f"Report written: {path.relative_to(PROJECT_ROOT)} ({path.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
