"""Publication chart filenames and analytical questions."""

from __future__ import annotations

CHART_METADATA = [
    ("01_growth_quality.png", "Is revenue growth converting into contribution margin?"),
    ("02_margin_rate.png", "Is the margin rate holding above the 30% quality floor?"),
    ("03_revenue_growth_mom.png", "How steady is month-on-month revenue growth?"),
    ("04_active_customers_arpu.png", "Is the active base growing faster than monetization?"),
    ("05_revenue_decomposition.png", "Is growth driven by volume, monetization, or mix?"),
    ("06_cohort_retention.png", "How do mature cohorts retain activity and revenue?"),
    ("07_cohort_heatmap.png", "Do all cohorts decay the same way?"),
    ("08_channel_economics.png", "Which acquisition channels deserve budget?"),
    ("09_channel_ltv_cac_ranking.png", "How wide is the channel efficiency gap?"),
    ("10_channel_allocation_gap.png", "Is spend aligned with where contribution is created?"),
    ("11_segment_profitability.png", "Where does margin concentrate across segments?"),
    ("12_region_profitability.png", "Is geography a source of the margin problem?"),
    ("13_product_margin.png", "Where are the low-margin product pockets?"),
    ("14_revenue_concentration.png", "How concentrated is revenue across customers?"),
    ("15_revenue_distribution.png", "What does the customer revenue distribution look like?"),
    (
        "16_revenue_lifetime_corr.png",
        "How is revenue associated with observed transaction activity span?",
    ),
    ("17_reallocation_waterfall.png", "How does the reallocation build its uplift?"),
    ("18_scenario_envelope.png", "How wide is the scenario envelope?"),
    ("19_scenario_seed_stability.png", "How stable is modeled uplift across sampled seeds?"),
]


def expected_chart_files() -> list[str]:
    return [filename for filename, _ in CHART_METADATA]
