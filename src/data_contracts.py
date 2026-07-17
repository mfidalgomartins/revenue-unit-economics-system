"""Canonical schemas and categorical domains for the raw data layer."""

from __future__ import annotations

RAW_CONTRACT_VERSION = "1.0.0"

RAW_SCHEMAS: dict[str, tuple[str, ...]] = {
    "customers": (
        "customer_id",
        "signup_date",
        "segment",
        "region",
        "acquisition_channel",
    ),
    "transactions": (
        "transaction_id",
        "customer_id",
        "transaction_date",
        "revenue",
        "cost",
        "product_type",
    ),
    "marketing_spend": ("date", "acquisition_channel", "spend"),
    "marketing_touchpoints": (
        "touchpoint_id",
        "customer_id",
        "touchpoint_date",
        "acquisition_channel",
        "touchpoint_order",
        "is_conversion_touch",
    ),
    "marketing_experiments": (
        "experiment_id",
        "customer_id",
        "acquisition_channel",
        "assignment",
        "assigned_date",
        "outcome_window_days",
        "converted",
        "pre_period_contribution",
        "observed_contribution",
    ),
    "pricing_interventions": (
        "intervention_id",
        "week_start",
        "product_type",
        "region",
        "assignment",
        "reference_price",
        "observed_price",
        "units_sold",
        "revenue",
        "contribution_margin",
    ),
}

RAW_DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "customers": ("signup_date",),
    "transactions": ("transaction_date",),
    "marketing_spend": ("date",),
    "marketing_touchpoints": ("touchpoint_date",),
    "marketing_experiments": ("assigned_date",),
    "pricing_interventions": ("week_start",),
}

RAW_NUMERIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "customers": (),
    "transactions": ("revenue", "cost"),
    "marketing_spend": ("spend",),
    "marketing_touchpoints": ("touchpoint_order",),
    "marketing_experiments": (
        "outcome_window_days",
        "pre_period_contribution",
        "observed_contribution",
    ),
    "pricing_interventions": (
        "reference_price",
        "observed_price",
        "units_sold",
        "revenue",
        "contribution_margin",
    ),
}

RAW_NONNEGATIVE_COLUMNS: dict[str, tuple[str, ...]] = {
    "customers": (),
    "transactions": ("revenue", "cost"),
    "marketing_spend": ("spend",),
    "marketing_touchpoints": ("touchpoint_order",),
    "marketing_experiments": ("outcome_window_days",),
    "pricing_interventions": (
        "reference_price",
        "observed_price",
        "units_sold",
        "revenue",
    ),
}

SEGMENTS = ("Startup", "SMB", "Mid-Market", "Enterprise")
REGIONS = ("North America", "EMEA", "LATAM", "APAC")
ACQUISITION_CHANNELS = (
    "paid_search",
    "social_ads",
    "referral",
    "organic",
    "partners",
    "email",
)
PRODUCT_TYPES = ("Core", "Add-on", "Premium", "Services")

RAW_ALLOWED_VALUES: dict[tuple[str, str], frozenset[str]] = {
    ("customers", "segment"): frozenset(SEGMENTS),
    ("customers", "region"): frozenset(REGIONS),
    ("customers", "acquisition_channel"): frozenset(ACQUISITION_CHANNELS),
    ("transactions", "product_type"): frozenset(PRODUCT_TYPES),
    ("marketing_spend", "acquisition_channel"): frozenset(ACQUISITION_CHANNELS),
    ("marketing_touchpoints", "acquisition_channel"): frozenset(ACQUISITION_CHANNELS),
    ("marketing_touchpoints", "is_conversion_touch"): frozenset({"True", "False"}),
    ("marketing_experiments", "acquisition_channel"): frozenset(ACQUISITION_CHANNELS),
    ("marketing_experiments", "assignment"): frozenset({"control", "treatment"}),
    ("marketing_experiments", "converted"): frozenset({"True", "False"}),
    ("pricing_interventions", "product_type"): frozenset(PRODUCT_TYPES),
    ("pricing_interventions", "region"): frozenset(REGIONS),
    ("pricing_interventions", "assignment"): frozenset({"price_down_10", "control", "price_up_10"}),
}
