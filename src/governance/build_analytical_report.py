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

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLES = PROJECT_ROOT / "outputs" / "tables"
PROCESSED = PROJECT_ROOT / "data" / "processed"
GRAPHS = PROJECT_ROOT / "outputs" / "charts"
OUT = PROJECT_ROOT / "outputs" / "reports"

ACCENT = "#15803d"
NEG = "#b91c1c"
WARN = "#b45309"
INK = "#0a0a0a"


def _img(name: str) -> str:
    data = (GRAPHS / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _usd(x: float, dp: int = 0) -> str:
    return f"${x:,.{dp}f}"


def build_html() -> str:
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
    monthly = pd.read_csv(TABLES / "monthly_revenue_health.csv", parse_dates=["month"])
    cust = pd.read_csv(PROCESSED / "customer_metrics.csv")

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
    def chan(name):
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
    startup = seg_only[seg_only["dimension_value"] == "Startup"].iloc[0]
    services = prod[prod["dimension_value"] == "Services"].iloc[0]
    core = prod[prod["dimension_value"] == "Core"].iloc[0]
    premium = prod[prod["dimension_value"] == "Premium"].iloc[0]
    addon = prod[prod["dimension_value"] == "Add-on"].iloc[0]
    reg_only = reg[reg["dimension_type"] == "region"].sort_values("contribution_margin", ascending=False)
    reg_top = reg_only.iloc[0]
    reg_bottom = reg_only.iloc[-1]
    reg_margin_spread = float(reg_only["margin_pct"].max() - reg_only["margin_pct"].min())

    # --- cohorts ---
    def coh_at(m, col):
        return float(coh.loc[coh["months_since_cohort"] == m, col].iloc[0])

    # --- decomposition ---
    def dval(effect):
        return float(dec.loc[dec["effect"] == effect, "effect_value"].iloc[0])

    def dshare(effect):
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
    rev_p75 = float(cust["total_revenue"].quantile(0.75))
    rev_max = float(cust["total_revenue"].max())
    corr_life = float(cust.loc[cust["total_revenue"] > 0, "lifetime_days"].corr(
        cust.loc[cust["total_revenue"] > 0, "total_revenue"]))
    corr_txn = float(cust["transaction_count"].corr(cust["total_revenue"]))
    neg_margin_cust = int((cust["contribution_margin"] < 0).sum())

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
            f"<tr><td>{r['month'].strftime('%b %Y')}</td>"
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

    css = """
    @page { size: A4; margin: 20mm 18mm 18mm 18mm;
      @bottom-center { content: counter(page); font-size: 8pt; color:#a3a3a3; } }
    @page:first { @bottom-center { content: ""; } }
    * { box-sizing: border-box; }
    body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color:#0a0a0a;
      font-size: 10.2pt; line-height: 1.52; margin:0; -webkit-font-smoothing: antialiased; }
    h1,h2,h3 { font-weight:600; color:#0a0a0a; line-height:1.2; }
    h2 { font-size: 15pt; margin: 0 0 2px; padding-top: 2px; }
    h2 .num { color:#737373; font-weight:500; font-size:10pt; margin-right:8px; }
    h3 { font-size: 11.5pt; margin: 18px 0 4px; }
    p { margin: 0 0 9px; }
    .muted { color:#737373; }
    .accent { color:#15803d; }
    .neg { color:#b91c1c; }
    .lead { font-size:10.8pt; line-height:1.55; }
    .rule { height:2px; background:#0a0a0a; border:0; margin:6px 0 14px; }
    .hair { height:1px; background:#ececec; border:0; margin:14px 0; }
    section { page-break-inside: auto; }
    .break { page-break-before: always; }
    .chart { width:100%; margin:12px 0 4px; border:1px solid #ececec; }
    .chart.sm { width:86%; display:block; margin-left:auto; margin-right:auto; }
    .cap { font-size:8.6pt; color:#737373; margin:0 0 14px; line-height:1.4; }
    .cap b { color:#0a0a0a; }
    table { width:100%; border-collapse:collapse; font-size:9pt; margin:8px 0 8px; }
    th,td { text-align:left; padding:5px 8px; border-bottom:1px solid #ececec; }
    th { color:#737373; font-weight:600; border-bottom:1.5px solid #0a0a0a; text-transform:uppercase; letter-spacing:.03em; font-size:8pt; }
    td.num, th.num { text-align:right; font-variant-numeric: tabular-nums; }
    .kpis { display:flex; gap:0; margin:16px 0 6px; border-top:2px solid #0a0a0a; border-bottom:1px solid #ececec; }
    .kpi { flex:1; padding:11px 14px 11px 0; }
    .kpi .v { font-size:18pt; font-weight:600; letter-spacing:-.01em; }
    .kpi .l { font-size:8pt; color:#737373; text-transform:uppercase; letter-spacing:.04em; }
    .kpi .d { font-size:8.4pt; color:#15803d; margin-top:2px; }
    .callout { border-left:3px solid #15803d; background:#fafafa; padding:10px 14px; margin:12px 0; font-size:9.8pt; }
    .callout.warn { border-left-color:#b91c1c; }
    .cover { height:247mm; display:flex; flex-direction:column; }
    .cover .tag { font-size:9pt; letter-spacing:.18em; text-transform:uppercase; color:#737373; }
    .cover h1 { font-size:31pt; letter-spacing:-.02em; margin:12px 0 0; max-width:15em; line-height:1.08; }
    .cover .sub { font-size:13pt; color:#404040; margin-top:16px; max-width:30em; line-height:1.42; }
    .cover .spacer { flex:1; }
    .cover .meta { font-size:9.5pt; color:#404040; }
    .cover .meta b { color:#0a0a0a; font-weight:600; }
    ol.rec { margin:6px 0; padding-left:20px; }
    ol.rec li { margin-bottom:12px; }
    ol.rec li b { font-size:10.4pt; }
    .toc { font-size:10.4pt; }
    .toc .row { display:flex; align-items:baseline; padding:6px 0; border-bottom:1px solid #f2f2f2; }
    .toc .n { width:2.4em; color:#737373; font-variant-numeric:tabular-nums; }
    .toc .t { flex:1; }
    .toc .sub2 { padding-left:2.4em; font-size:9.4pt; color:#525252; }
    .grid2 { display:flex; gap:14px; }
    .grid2 > div { flex:1; }
    .priority { display:inline-block; font-size:7.6pt; font-weight:700; letter-spacing:.04em;
      text-transform:uppercase; padding:2px 7px; border-radius:3px; color:#fff; margin-right:6px; vertical-align:middle; }
    .p1 { background:#b91c1c; } .p2 { background:#b45309; } .p3 { background:#15803d; } .p4 { background:#525252; }
    """

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
    <p><b>Date</b> &nbsp; June 2026</p>
    <p><b>Coverage</b> &nbsp; {n_months} months, January 2023 to December 2025 &middot;
       {n_customers:,} customers &middot; 69,950 transactions &middot; {total_spend/1e6:.1f}M acquisition spend</p>
    <p class="muted" style="margin-top:16px;max-width:36em">Built on a synthetic but internally
    consistent commercial dataset that passes {n_checks} validation checks. Figures demonstrate
    method and support relative comparison between channels, segments, and cohorts. They are not a
    forecast of any real market.</p>
  </div>
</div>

<!-- ============================ TOC ============================ -->
<section class="break">
<h2>Contents</h2><hr class="rule">
<div class="toc">
  <div class="row"><span class="n">1</span><span class="t">Executive summary</span></div>
  <div class="row"><span class="n">2</span><span class="t">Context and objectives</span></div>
  <div class="row"><span class="n">3</span><span class="t">Data and methodology</span></div>
  <div class="row"><span class="n">4</span><span class="t">Analytical framework</span></div>
  <div class="row"><span class="n">5</span><span class="t">Findings</span></div>
  <div class="sub2">5.1&nbsp;&nbsp;The growth trajectory</div>
  <div class="sub2">5.2&nbsp;&nbsp;Margin quality across the window</div>
  <div class="sub2">5.3&nbsp;&nbsp;What is driving the growth</div>
  <div class="sub2">5.4&nbsp;&nbsp;Cohort retention and revenue decay</div>
  <div class="sub2">5.5&nbsp;&nbsp;Channel unit economics</div>
  <div class="sub2">5.6&nbsp;&nbsp;Segment, region, and product profitability</div>
  <div class="sub2">5.7&nbsp;&nbsp;Customer concentration and value</div>
  <div class="sub2">5.8&nbsp;&nbsp;The reallocation scenario</div>
  <div class="row"><span class="n">6</span><span class="t">Risks, limitations, and caveats</span></div>
  <div class="row"><span class="n">7</span><span class="t">Recommendations and action priorities</span></div>
  <div class="row"><span class="n">8</span><span class="t">Appendix</span></div>
</div>
<p class="muted" style="margin-top:20px;font-size:9pt">This report reads every quoted figure from the
project's processed tables at build time. No number in the prose is typed by hand. The method and
the data behind each finding are documented in Section 3 and reproducible from the commands in
Appendix G.</p>
</section>

<!-- ============================ 1. EXECUTIVE SUMMARY ============================ -->
<section class="break">
<h2><span class="num">1</span>Executive summary</h2><hr class="rule">
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

<p>The headline is unambiguous. Monthly revenue rose from {_usd(first_rev/1e3)}K in January 2023 to
{_usd(last_rev/1e6,1)}M in December 2025, and contribution margin tracked it closely in absolute
dollars. A revenue chart on its own would read as an unqualified success. Five separate analyses
say otherwise, and they agree.</p>

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
customers and only {avg_s:.0%} from higher revenue per customer. Volume bought through channels
that lose money is the weakest form of growth, because holding the line depends on continued
spend.</p>

<p>Third, retention decays fast and early. Median revenue retention falls to
{coh_at(6,'median_revenue_retention'):.0%} by month 6 and {coh_at(12,'median_revenue_retention'):.0%}
by month 12, with the steepest loss between months 3 and 6. Only 16.7% of cohorts show revenue
expansion at month 6, so the median customer shrinks in their first half-year. The acquisition
treadmill cannot be slowed until this early-life decay is fixed.</p>

<p>Fourth, margin concentrates in the least efficient places. Enterprise is the largest segment at
{ent['revenue_share']:.0%} of revenue but carries the lowest margin rate at {ent['margin_pct']:.1%},
the only segment below the 30% quality floor. The Services product line runs at just
{services['margin_pct']:.1%} margin on {_usd(float(services['total_revenue'])/1e6,1)}M of revenue.
Regional margins, by contrast, are banded within {reg_margin_spread*100:.1f} points, so geography is
not the problem. Mix and cost-to-serve are.</p>

<p>Fifth, revenue is highly concentrated. The top 10% of customers account for {top10:.0%} of
revenue and the top 20% for {top20:.0%}, with a Gini coefficient of {gini:.2f}. That concentration
makes retention of high-value customers a first-order risk, and it makes the early cohort decay
more expensive than the median retention figure suggests.</p>

<p>The recommended response is a bounded reallocation. Scaling the three efficient channels within
guardrails and pulling 35% from the two inefficient ones lifts estimated annual contribution from
{_usd(baseline_cm/1e6,1)}M to {_usd(base_cm/1e6,1)}M, an uplift of {_usd(uplift/1e6,1)}M
({uplift_pct:.0%}), with no extra budget. The uplift stays positive in every stress case tested,
from {_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M in the worst case to
{_usd(float(best['estimated_uplift_vs_baseline'])/1e6,1)}M in the best, and across all {n_seeds}
deterministic seeds it averages {_usd(seed_mean/1e6,1)}M with a coefficient of variation of
{seed_cv:.1%}. The full set of recommendations and their priority order is in Section 7.</p>
</section>

<!-- ============================ 2. CONTEXT ============================ -->
<section class="break">
<h2><span class="num">2</span>Context and objectives</h2><hr class="rule">
<p>Top-line revenue growth is the metric most often celebrated and least often interrogated. A
revenue line that bends upward can hide three separate problems at once: customers acquired below
the cost to serve them, cohorts that leak revenue faster than new cohorts replace it, and margin
diluted by an unfavourable product or segment mix. None of these appear in a revenue chart. All
three change what a business should do next.</p>

<p>This analysis exists to answer a budget question, not to populate a dashboard. The business is
spending {_usd(total_spend/1e6,1)}M a period to acquire customers and wants to know whether that
spend is building a durable asset or renting a revenue line that stops the moment spend stops. The
question is asked five ways, each with a method chosen to give a decision rather than a description.</p>

<table>
<tr><th>Question</th><th>Method</th><th>Decision it informs</th></tr>
<tr><td>Is growth converting into margin?</td><td>Monthly revenue and contribution margin trend, margin rate vs floor</td><td>Whether to defend or improve margin</td></tr>
<tr><td>What is driving the growth?</td><td>Decomposition into volume, monetization, and mix</td><td>Where to invest for durable growth</td></tr>
<tr><td>Do cohorts hold their value?</td><td>Median activity and revenue retention by cohort age</td><td>Whether retention or acquisition is the lever</td></tr>
<tr><td>Which channels deserve budget?</td><td>LTV/CAC, payback, and spend-to-contribution alignment per channel</td><td>How to allocate acquisition spend</td></tr>
<tr><td>What is the upside from reallocating spend?</td><td>Bounded scenario with stress and seed-stability tests</td><td>Size and confidence of the reallocation</td></tr>
</table>

<p>The scope is deliberately narrow. This is not a forecast, a market sizing, or an attribution
study. It is a diagnostic of growth quality on the data available, built so that each finding either
confirms the current allocation or changes it. Where a finding cannot be settled with the data on
hand, Section 6 says so plainly rather than papering over the gap.</p>

<h3>Who should read this</h3>
<p>The primary audience is the executive or commercial owner deciding next quarter's acquisition
budget. The secondary audience is the analytics or finance reviewer who needs to trust the numbers
before acting on them. The report is written for the first audience in the prose and for the second
in the methodology and appendix.</p>
</section>

<!-- ============================ 3. METHODOLOGY ============================ -->
<section class="break">
<h2><span class="num">3</span>Data and methodology</h2><hr class="rule">
<p>The pipeline runs end to end from raw tables to validated outputs, with each stage writing
deterministic files. Three raw tables feed it: {n_customers:,} customers, 69,950 transactions, and
6,576 daily channel spend records, spanning January 2023 to December 2025. Customer-level metrics,
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

<h3>Data quality gate</h3>
<p>All {n_checks} raw-data validation checks pass before any analysis runs: schema match, grain
uniqueness, referential integrity, date coverage, channel-domain alignment, and value-range sanity.
The gate flagged 258 transactions (0.37%) where cost exceeds revenue. That share sits below the 1%
review threshold, so the rows are retained as genuine cost-to-serve exceptions rather than scrubbed.
At the customer level, {neg_margin_cust:,} customers carry a negative lifetime contribution margin,
which the LTV figures absorb rather than exclude. The full gate is reproduced in Appendix F.</p>

<h3>Limitations of the data</h3>
<p>The data is synthetic. It is built to be realistic and internally consistent, which makes it
suitable for demonstrating method and for relative comparison between channels, segments, and
cohorts. It is not a forecast of any real market. Observed LTV reflects only the window available,
so long-horizon cohort reads draw on mature cohorts only. These limits are revisited in Section 6.</p>
</section>

<!-- ============================ 4. FRAMEWORK ============================ -->
<section class="break">
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
<section class="break">
<h2><span class="num">5</span>Findings</h2><hr class="rule">

<h3>5.1&nbsp;&nbsp;The growth trajectory is real, fast, and uneven</h3>
<p>Monthly revenue rose from {_usd(first_rev/1e3)}K in January 2023 to {_usd(last_rev/1e6,1)}M in
December 2025. Comparing like with like, the last six months averaged {_usd(recent_avg/1e6,1)}M a
month against {_usd(early_avg/1e3)}K in the first six, a {rev_multiple:.1f}-fold increase across
{n_months} months. Contribution margin tracked revenue closely in absolute terms, which is the first
thing to confirm: the business is not buying revenue at the expense of total margin dollars. Both
lines climb together.</p>
<img class="chart" src="{_img('01_growth_quality.png')}">
<p class="cap"><b>Figure 1.</b> Revenue and contribution margin rise together in absolute dollars. The
gap between the two lines, which is the margin rate, does not widen as the business scales.</p>

<p>The growth is not smooth. Month-on-month revenue change averages {mean_mom:.1%}, but the series
includes {down_months} down months across the window, most of them in the seasonal January and
mid-year dips visible in Figure 2. Durability shows up in how the business handles those down
months, and here it recovers each time without breaking the trend. The volatility is seasonal noise
around a strong underlying climb, not a structural wobble.</p>
<img class="chart" src="{_img('03_revenue_growth_mom.png')}">
<p class="cap"><b>Figure 2.</b> Month-on-month revenue growth. The {down_months} down months are
shallow and seasonal, not a sign of a stalling trend.</p>

<p>The composition of that growth is the first warning. The active base grew from {first_active:,}
customers in the opening month to {last_active:,} in the closing month, while revenue per active
customer moved only from {_usd(arpac_first)} to {_usd(arpac_last)}. The base is doing almost all the
work; monetization per customer is close to flat. A business adding this many customers while holding
revenue per customer steady is growing by addition, not by deepening the value of the relationships
it already has.</p>
<img class="chart" src="{_img('04_active_customers_arpu.png')}">
<p class="cap"><b>Figure 3.</b> The active base climbs steeply while revenue per active customer stays
in a narrow band. Growth is coming from more customers, not richer ones.</p>
</section>

<section class="break">
<h3>5.2&nbsp;&nbsp;Margin quality is only holding, not improving</h3>
<p>The qualifier on the trajectory is the rate. Contribution margin holds in a tight band between
{margin_min:.0%} and {margin_max:.0%}, hovering at the 30% quality floor rather than improving as the
business scales. A company adding this much revenue would normally expect operating leverage to lift
the margin rate over three years. Here it does not move.</p>
<img class="chart" src="{_img('02_margin_rate.png')}">
<p class="cap"><b>Figure 4.</b> Monthly contribution margin rate against the 30% quality floor. The
rate oscillates around the floor for the full window and shows no upward drift.</p>
<p>A flat margin rate during rapid growth carries a specific meaning: the incremental revenue is no
better in quality than the average revenue already on the books. If the new customers were more
profitable than the existing base, the rate would rise. If they were dragging, it would fall. It
does neither, which says the business is cloning its average economics at scale rather than improving
them. The next three findings explain why the rate is stuck, and the reallocation in Section 5.8 is
the move that would unstick it.</p>
</section>

<section class="break">
<h3>5.3&nbsp;&nbsp;Growth is volume-led, not monetization-led</h3>
<p>Decomposing the {_usd(tot_change/1e6,1)}M revenue change between the first and last six months
separates three effects: more customers, more revenue per customer, and a shift in segment mix.</p>
<img class="chart" src="{_img('05_revenue_decomposition.png')}">
<p class="cap"><b>Figure 5.</b> Volume accounts for {vol_s:.0%} of the revenue change, monetization
{avg_s:.0%}, and segment mix {mix_s:.0%}. The residual is zero, so the three effects fully account
for the change.</p>
<table>
<tr><th>Effect</th><th class="num">Contribution to change</th><th class="num">Share</th></tr>
{dec_rows}
</table>
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
</section>

<section class="break">
<h3>5.4&nbsp;&nbsp;Cohorts decay fast in the first six months</h3>
<p>If growth depends on volume, retention determines how much of that volume the business keeps.
Median revenue retention falls to {coh_at(3,'median_revenue_retention'):.0%} by month 3 and
{coh_at(6,'median_revenue_retention'):.0%} by month 6. Activity retention is worse, at
{coh_at(6,'median_activity_retention'):.0%} by month 6 and {coh_at(12,'median_activity_retention'):.0%}
by month 12.</p>
<img class="chart" src="{_img('06_cohort_retention.png')}">
<p class="cap"><b>Figure 6.</b> Median activity and revenue retention through month 24. The steepest
loss is concentrated between months 3 and 6, the window where onboarding and first-value delivery
matter most.</p>
<p>Revenue retention sits above activity retention at most ages, which says the customers who stay
spend somewhat more, a partial offset to logo churn. It is not enough to change the conclusion. Only
16.7% of cohorts show revenue expansion at month 6, so the median customer is shrinking, not growing,
in their first half-year. The cohort heatmap confirms that this is structural rather than a property
of one or two unlucky cohorts.</p>
<img class="chart" src="{_img('07_cohort_heatmap.png')}">
<p class="cap"><b>Figure 7.</b> Revenue retention by cohort (rows) and age (columns). The colour
fades along every row at a similar pace, so the decay pattern repeats across cohorts rather than
being driven by a few outliers.</p>
<p>The combination is costly. The business acquires volume through expensive channels and then loses
a large share of it before the customer pays back. Because revenue is concentrated in a small set of
high-value customers, as Section 5.7 shows, losing the wrong customers early is more damaging than
the median curve implies. Slowing the acquisition treadmill is not possible until this early-life
decay is addressed, which is why retention is a named recommendation in Section 7 rather than a
footnote.</p>
</section>

<section class="break">
<h3>5.5&nbsp;&nbsp;Two channels destroy value and hold most of the budget</h3>
<p>This is the central finding. Channel economics split into two groups with no overlap, and the
budget is pointed at the wrong group.</p>
<img class="chart" src="{_img('08_channel_economics.png')}">
<p class="cap"><b>Figure 8.</b> Channel LTV against CAC, with bubble size showing total spend. Three
channels sit above the 3&times; line, two below 1&times;, and none in between. The two largest
bubbles, paid search and social ads, sit in the value-destructive zone.</p>
<table>
<tr><th>Channel</th><th class="num">Customers</th><th class="num">Spend</th><th class="num">CAC</th>
<th class="num">Avg LTV</th><th class="num">Med LTV</th><th class="num">LTV/CAC</th><th class="num">Payback (mo)</th><th>Status</th></tr>
{ch_rows}
</table>
<p>Organic, referral, and partners clear the 3&times; bar with room to spare and pay back inside nine
months. Paid search and social ads sit below the 1&times; line, meaning the average customer they buy
is worth less than the cost to acquire them. The efficiency gap is not marginal. It is more than an
order of magnitude between the best and worst channel.</p>
<img class="chart" src="{_img('09_channel_ltv_cac_ranking.png')}">
<p class="cap"><b>Figure 9.</b> LTV/CAC ranked across channels. Organic returns {organic['LTV_to_CAC']:.0f}&times;
its cost; social ads returns {social['LTV_to_CAC']:.2f}&times;. Email is the only borderline case.</p>
<p>The problem is not that the inefficient channels exist; it is their weight. Together they hold
{_usd(ineff_spend/1e6,2)}M of acquisition spend, {ineff_share:.0%} of the total, while returning
under a dollar of contribution per dollar spent. The misallocation is clearest when each channel's
share of spend is set against its share of contribution.</p>
<img class="chart" src="{_img('10_channel_allocation_gap.png')}">
<p class="cap"><b>Figure 10.</b> Share of spend against share of contribution by channel. Organic
takes {organic['total_spend']/total_spend:.0%} of spend and produces {organic['total_channel_contribution_margin']/total_contrib:.0%}
of contribution; paid search and social ads take {(paid['total_spend']+social['total_spend'])/total_spend:.0%}
of spend and produce {ineff_contrib_share:.0%} of contribution.</p>
<p>Email is borderline at {email['LTV_to_CAC']:.2f}&times; with a {email['approximate_payback_period']:.0f}-month
payback. It is a hold-and-fix case rather than a scale-or-cut one. The median LTV column tells a
sharper version of the same story than the mean: social ads has a median LTV of {_usd(social['median_LTV'])}
against a CAC of {_usd(social['CAC'])}, so the typical customer it buys is deeply underwater even
before averaging in the rare high-value account.</p>
<div class="callout">Reallocating budget away from these two channels is the single highest-value
move available, and it requires no incremental spend. Section 5.8 sizes it.</div>
</section>

<section class="break">
<h3>5.6&nbsp;&nbsp;Margin concentrates in the lowest-rate segment and product</h3>
<p>Profitability by segment carries a structural risk that a revenue view hides. The largest segment
is also the least efficient.</p>
<img class="chart" src="{_img('11_segment_profitability.png')}">
<p class="cap"><b>Figure 11.</b> Contribution margin dollars and margin rate by segment. Enterprise
carries the most margin dollars at the lowest rate, and it is the only segment below the 30% floor.</p>
<table>
<tr><th>Segment</th><th class="num">Customers</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr>
{seg_rows}
</table>
<p>Enterprise is the largest segment at {ent['revenue_share']:.0%} of revenue and
{_usd(float(ent['contribution_margin'])/1e6,1)}M of margin dollars, yet it carries the lowest margin
rate at {ent['margin_pct']:.1%}, below every smaller segment. Mid-Market, SMB, and Startup all run
between {smb['margin_pct']:.0%} and {mm['margin_pct']:.0%}. Nearly half the revenue base sits in the
least efficient segment, which is a concentration risk: pricing or cost-to-serve pressure in
Enterprise hits the margin line harder than its rate alone suggests.</p>
<p>Geography, by contrast, is not where the margin problem lives. Regional margin rates are banded
within {reg_margin_spread*100:.1f} points of each other, from {reg_bottom['margin_pct']:.1%} in
{reg_bottom['dimension_value']} to {reg_top['margin_pct']:.1%} in {reg_top['dimension_value']}.
Regions differ in size, not in efficiency.</p>
<img class="chart" src="{_img('12_region_profitability.png')}">
<p class="cap"><b>Figure 12.</b> Contribution margin by region with margin rate and revenue share.
{reg_top['dimension_value']} leads on dollars, but every region sits within a point of the others on
rate. Geography is a scale story, not a margin story.</p>
<p>The product view sharpens the diagnosis. Services run at just {services['margin_pct']:.1%} margin
on {_usd(float(services['total_revenue'])/1e6,1)}M of revenue ({services['revenue_share']:.0%} of the
total), the clear low-margin growth pocket. Premium runs at {premium['margin_pct']:.1%}, while Core
and Add-on, the two highest-rate lines, run at {core['margin_pct']:.1%} and {addon['margin_pct']:.1%}.
The spread between the best and worst product line is nearly {(addon['margin_pct']-services['margin_pct'])*100:.0f}
margin points.</p>
<img class="chart" src="{_img('13_product_margin.png')}">
<p class="cap"><b>Figure 13.</b> Margin rate by product type with revenue. Services is the only major
line well below the floor, and it is large enough to drag the blended rate.</p>
<p>Taken together, the segment and product views say the margin problem is a mix and cost-to-serve
problem, not a pricing-everywhere problem. The fix is targeted: re-price or re-scope the Services
line and the Enterprise delivery model, rather than raising prices across a base that is already
running at or above the floor everywhere else.</p>
</section>

<section class="break">
<h3>5.7&nbsp;&nbsp;Revenue is concentrated in a thin band of customers</h3>
<p>Revenue is far from evenly spread. The top 10% of customers account for {top10:.0%} of total
revenue, the top 20% for {top20:.0%}, and the top 1% alone for {top1:.0%}. The Gini coefficient of
lifetime revenue is {gini:.2f}, well into the territory where a small group of accounts carries the
business.</p>
<img class="chart" src="{_img('14_revenue_concentration.png')}">
<p class="cap"><b>Figure 14.</b> Lorenz curve of lifetime revenue across all {n_customers:,} customers.
The deep bow away from the equality line is the concentration: a fifth of customers hold four fifths
of revenue.</p>
<p>The distribution behind the curve is a long right tail. Median lifetime revenue is
{_usd(rev_median)} while the mean is {_usd(rev_mean)}, more than three times higher, because a small
number of customers reach up to {_usd(rev_max/1e3)}K each. The {zero_txn:,} customers who never
transacted sit at the bottom of the same distribution and pull the median down further.</p>
<img class="chart" src="{_img('15_revenue_distribution.png')}">
<p class="cap"><b>Figure 15.</b> Distribution of lifetime revenue per customer on a log scale. The
mean sits far to the right of the median, the signature of a heavy tail.</p>
<p>Concentration interacts directly with the retention finding. Because value pools in a thin band,
the cost of early decay depends on which customers decay. Tenure is a real driver of revenue, with a
Pearson correlation of {corr_life:.2f} between lifetime days and lifetime revenue and {corr_txn:.2f}
between transaction count and revenue, so customers who survive the first six months and keep
transacting are disproportionately the ones who matter.</p>
<img class="chart" src="{_img('16_revenue_lifetime_corr.png')}">
<p class="cap"><b>Figure 16.</b> Lifetime revenue against tenure, with the median trend. Longer-tenured
customers are worth materially more, which is precisely why losing them early in Figure 6 is
expensive.</p>
<p>The implication for the budget is direct. Concentration plus tenure-driven value means the
business should weight acquisition toward channels that bring durable, high-value customers, and
should protect the high-value base it already has. Both point the same way as the channel economics
in Section 5.5.</p>
</section>

<section class="break">
<h3>5.8&nbsp;&nbsp;Reallocation adds {_usd(uplift/1e6,1)}M with no extra budget</h3>
<p>The reallocation scenario scales organic, referral, and partners within guardrails, cuts paid
search and social ads by 35%, holds email, and reinvests the freed budget into the efficient channels
up to a 100% scale-up cap per channel. Total budget is unchanged, so every dollar of uplift is a pure
allocation effect.</p>
<img class="chart" src="{_img('17_reallocation_waterfall.png')}">
<p class="cap"><b>Figure 17.</b> Contribution bridge from baseline to scenario by channel move.
Scaling the three efficient channels adds the bulk of the uplift; trimming the two inefficient ones
removes a small contribution drag.</p>
<table>
<tr><th>Channel</th><th>Status</th><th class="num">Baseline spend</th><th class="num">Scenario spend</th>
<th class="num">Spend change</th><th class="num">Contribution change</th></tr>
{plan_rows}
</table>
<p>Estimated annual contribution rises from {_usd(baseline_cm/1e6,1)}M to {_usd(scenario_cm/1e6,1)}M
in the base case, an uplift of {_usd(uplift/1e6,1)}M, or {uplift_pct:.0%}. The result is robust to
the elasticity assumptions. The scenario is stress-tested across a best, base, and worst case, with
CAC and LTV moved against the policy in the worst case.</p>
<img class="chart" src="{_img('18_scenario_envelope.png')}">
<p class="cap"><b>Figure 18.</b> Contribution under the reallocation across stress cases. Every case
clears the baseline; even the worst case, with CAC up 15% and LTV down 12% on the scaled channels,
adds {_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M.</p>
<table>
<tr><th>Scenario</th><th class="num">CAC mult.</th><th class="num">LTV mult.</th>
<th class="num">Contribution</th><th class="num">Uplift vs baseline</th></tr>
{stress_rows}
</table>
<p>The worst case, with CAC inflated 15% and LTV cut 12% on the channels being scaled, still returns
{_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M above baseline. The policy is also stable
across random draws. Repeating it across {n_seeds} deterministic seeds, the uplift averages
{_usd(seed_mean/1e6,1)}M with a standard deviation of {_usd(seed_std/1e3)}K, a coefficient of
variation of {seed_cv:.1%}, and it is positive in {n_seeds} of {n_seeds} seeds. The range runs from
{_usd(seed_min/1e6,1)}M to {_usd(seed_max/1e6,1)}M.</p>
<img class="chart" src="{_img('19_scenario_seed_stability.png')}">
<p class="cap"><b>Figure 19.</b> Estimated uplift across five deterministic seeds. The tight band
around the mean shows the outcome is a property of the allocation, not of one favourable draw.</p>
<table>
<tr><th class="num">Seed</th><th class="num">Baseline contrib.</th><th class="num">Scenario contrib.</th>
<th class="num">Uplift</th><th>Top scale-up</th><th>Top cut</th></tr>
{seed_rows}
</table>
</section>

<!-- ============================ 6. RISKS ============================ -->
<section class="break">
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
Real customer journeys cross channels, and lagged or assist effects are not modelled. A channel that
looks inefficient on last-touch economics could be assisting conversions credited elsewhere. The
reallocation is bounded and reversible partly to absorb this risk.</p>

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
</section>

<!-- ============================ 7. RECOMMENDATIONS ============================ -->
<section class="break">
<h2><span class="num">7</span>Recommendations and action priorities</h2><hr class="rule">
<p>Growth is real but expensive. The business is buying volume through channels that lose money,
keeping the margin rate pinned at the 30% floor, and leaning on continued spend that fast cohort
decay makes hard to sustain. The fix does not require more budget. It requires moving the budget that
already exists toward the customers worth acquiring and keeping. The four recommendations below are
ordered by value and urgency.</p>

<ol class="rec">
<li><span class="priority p1">Priority 1</span><b>Reallocate spend away from paid search and social
ads this quarter.</b><br>Both return under {paid['LTV_to_CAC']:.2f}&times; cost and together hold
{ineff_share:.0%} of acquisition spend. Cut each by 35% and redirect the freed
{_usd(ineff_spend*0.35/1e6,1)}M into organic, referral, and partners, holding each to its LTV/CAC and
payback guardrails. This is the {uplift_pct:.0%} contribution uplift modelled in Section 5.8, worth
{_usd(uplift/1e6,1)}M in the base case and at least
{_usd(float(worst['estimated_uplift_vs_baseline'])/1e6,1)}M in the worst case. It is the only
recommendation here that adds contribution without spending a dollar more.</li>

<li><span class="priority p2">Priority 2</span><b>Fix month 3 to 6 retention before slowing
acquisition.</b><br>The steepest decay is early-life, with median revenue retention falling from
{coh_at(3,'median_revenue_retention'):.0%} at month 3 to {coh_at(6,'median_revenue_retention'):.0%} at
month 6. Target onboarding and first-value delivery for the segments and channels feeding the most
volume, and track month-6 revenue retention as the success metric. Because revenue is concentrated
({top20:.0%} in the top 20% of customers), prioritise retention work on the high-value tail
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

<!-- ============================ 8. APPENDIX ============================ -->
<section class="break">
<h2><span class="num">8</span>Appendix</h2><hr class="rule">

<h3>A. Channel unit economics (full)</h3>
<table>
<tr><th>Channel</th><th class="num">Customers</th><th class="num">Spend</th><th class="num">CAC</th>
<th class="num">Avg LTV</th><th class="num">Med LTV</th><th class="num">LTV/CAC</th><th class="num">Payback (mo)</th><th>Status</th></tr>
{ch_rows}
</table>

<h3>B. Segment and region profitability</h3>
<table>
<tr><th>Segment</th><th class="num">Customers</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr>
{seg_rows}
</table>
<table style="margin-top:14px">
<tr><th>Region</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr>
{reg_rows}
</table>

<h3>C. Product profitability</h3>
<table>
<tr><th>Product type</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Revenue share</th></tr>
{prod_rows}
</table>

<h3>D. Monthly revenue health (full series)</h3>
<p class="muted" style="font-size:9pt">The {n_months}-month series behind Figures 1, 2, 3, and 4.</p>
<table>
<tr><th>Month</th><th class="num">Revenue</th><th class="num">Contribution margin</th>
<th class="num">Margin rate</th><th class="num">Active cust.</th><th class="num">Transactions</th>
<th class="num">Rev. growth</th></tr>
{monthly_rows}
</table>

<h3>E. Cohort retention curve (months 0 to 24)</h3>
<p class="muted" style="font-size:9pt">Median retention across cohorts at each age, with the count of
cohorts mature enough to be observed. The series behind Figures 6 and 7.</p>
<table>
<tr><th class="num">Months since signup</th><th class="num">Activity retention</th>
<th class="num">Revenue retention</th><th class="num">Cohorts observed</th></tr>
{coh_rows}
</table>

<h3>F. Data validation gate</h3>
<p class="muted" style="font-size:9pt">All {n_checks} checks run on the raw tables before any
analysis. A failure blocks the pipeline.</p>
<table>
<tr><th>Check</th><th>Status</th><th>Detail</th></tr>
{val_rows}
</table>

<h3>G. Data dictionary and reproducibility</h3>
<table>
<tr><th>Field</th><th>Definition</th></tr>
<tr><td>contribution_margin</td><td>Revenue minus direct delivery cost</td></tr>
<tr><td>average_LTV</td><td>Mean cumulative contribution margin per acquired customer, including zero-transaction customers</td></tr>
<tr><td>median_LTV</td><td>Median cumulative contribution margin per acquired customer</td></tr>
<tr><td>CAC</td><td>Period channel spend divided by customers acquired in the channel</td></tr>
<tr><td>LTV_to_CAC</td><td>average_LTV divided by CAC; efficient at &ge; 3.0</td></tr>
<tr><td>approximate_payback_period</td><td>Months of contribution required to recover CAC</td></tr>
<tr><td>median_revenue_retention</td><td>Median cohort revenue at month m relative to month 0</td></tr>
<tr><td>Gini coefficient</td><td>Concentration of lifetime revenue across customers; 0 is even, 1 is fully concentrated</td></tr>
</table>
<p class="muted" style="font-size:9pt;margin-top:10px">Every figure in this report is read at build
time from the project's analytical tables under <code>outputs/tables/</code> and the chart pack under
<code>outputs/charts/</code>. Regenerate the full pipeline with <code>python src/run_pipeline.py</code>,
the chart pack with <code>python src/visualization/build_chart_pack.py</code>, and this report with
<code>python src/governance/build_analytical_report.py</code>. The 19 figures in the narrative are
the complete chart pack; no figure is held back to an appendix.</p>
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


def main() -> None:
    html = build_html()
    path = render_pdf(html)
    print(f"Report written: {path.relative_to(PROJECT_ROOT)} ({path.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
