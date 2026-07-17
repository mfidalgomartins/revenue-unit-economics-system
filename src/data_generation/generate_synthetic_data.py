"""Generate synthetic business datasets for unit economics analysis.

This script builds the raw synthetic source tables:
- customers
- transactions
- marketing_spend
- marketing_touchpoints
- marketing_experiments
- pricing_interventions

Key design assumptions are encoded in comments near each generation block.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data_contracts import ACQUISITION_CHANNELS, PRODUCT_TYPES, REGIONS, SEGMENTS
from src.paths import PROJECT_ROOT

SEED = int(os.getenv("SYNTHETIC_SEED", "42"))

RAW_DIR = PROJECT_ROOT / "data" / "raw"

START_DATE = pd.Timestamp("2023-01-01")
END_DATE = pd.Timestamp("2025-12-31")


@dataclass(frozen=True)
class ChannelConfig:
    signup_share: float
    quality_score: float
    avg_activity_span_days: int
    cost_pressure: float


CHANNEL_CONFIG = {
    "paid_search": ChannelConfig(0.26, 0.45, 240, 0.18),
    "social_ads": ChannelConfig(0.22, 0.38, 190, 0.24),
    "referral": ChannelConfig(0.18, 0.73, 520, 0.08),
    "organic": ChannelConfig(0.19, 0.68, 470, 0.06),
    "partners": ChannelConfig(0.10, 0.62, 400, 0.12),
    "email": ChannelConfig(0.05, 0.58, 320, 0.10),
}

# Segment behavior drives willingness to pay and recurring transaction cadence.
SEGMENT_REVENUE_BASE = {
    "Startup": 95.0,
    "SMB": 165.0,
    "Mid-Market": 380.0,
    "Enterprise": 920.0,
}

SEGMENT_TX_LAMBDA = {
    "Startup": 0.85,
    "SMB": 1.10,
    "Mid-Market": 1.40,
    "Enterprise": 1.90,
}

SEGMENT_MIX_BY_CHANNEL = {
    "paid_search": [0.35, 0.37, 0.22, 0.06],
    "social_ads": [0.43, 0.34, 0.18, 0.05],
    "referral": [0.22, 0.39, 0.28, 0.11],
    "organic": [0.24, 0.38, 0.28, 0.10],
    "partners": [0.14, 0.29, 0.39, 0.18],
    "email": [0.19, 0.43, 0.29, 0.09],
}

REGION_PROBS = [0.36, 0.31, 0.14, 0.19]

PRODUCT_MIX_BY_SEGMENT = {
    "Startup": [0.66, 0.21, 0.06, 0.07],
    "SMB": [0.55, 0.24, 0.12, 0.09],
    "Mid-Market": [0.44, 0.25, 0.20, 0.11],
    "Enterprise": [0.29, 0.19, 0.33, 0.19],
}

PRODUCT_PRICE_FACTOR = {
    "Core": 1.00,
    "Add-on": 0.55,
    "Premium": 1.85,
    "Services": 2.35,
}

# Cost ratios vary across products; services and premium bundles are more expensive to deliver.
PRODUCT_COST_RATIO = {
    "Core": 0.46,
    "Add-on": 0.40,
    "Premium": 0.62,
    "Services": 0.69,
}


def _build_signup_dates(
    n_customers: int,
    *,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample signup dates with growth over time (later dates more likely)."""
    all_days = pd.date_range(START_DATE, END_DATE, freq="D")
    t = np.linspace(0, 1, len(all_days))

    # Growth assumption: acquisition volume accelerates through time.
    growth_weight = np.exp(1.35 * t)
    seasonal_weight = 1 + 0.15 * np.sin(2 * np.pi * (all_days.dayofyear.to_numpy() / 365.25))
    final_weight = growth_weight * seasonal_weight
    final_weight = final_weight / final_weight.sum()

    sampled = rng.choice(all_days.to_numpy(), size=n_customers, p=final_weight)
    return np.asarray(pd.to_datetime(sampled).to_numpy())


def generate_customers(
    n_customers: int = 9000,
    *,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate customer master data plus hidden traits used for transactions."""
    if n_customers <= 0:
        raise ValueError("n_customers must be greater than zero")

    customer_ids = np.array([f"C{idx:07d}" for idx in range(1, n_customers + 1)])
    signup_dates = _build_signup_dates(n_customers, rng=rng)

    channels = list(ACQUISITION_CHANNELS)
    channel_probs = [CHANNEL_CONFIG[ch].signup_share for ch in channels]
    acquisition_channels = rng.choice(channels, size=n_customers, p=channel_probs)

    segments = np.empty(n_customers, dtype=object)
    for i, channel in enumerate(acquisition_channels):
        segments[i] = rng.choice(SEGMENTS, p=SEGMENT_MIX_BY_CHANNEL[channel])

    regions = rng.choice(REGIONS, size=n_customers, p=REGION_PROBS)

    # Hidden traits inject quality differences by channel and segment.
    segment_quality_shift = {
        "Startup": -0.10,
        "SMB": 0.00,
        "Mid-Market": 0.14,
        "Enterprise": 0.24,
    }

    quality = np.array(
        [
            CHANNEL_CONFIG[channel].quality_score + segment_quality_shift[segment]
            for channel, segment in zip(acquisition_channels, segments, strict=False)
        ]
    )
    quality += rng.normal(0, 0.08, size=n_customers)
    quality = np.clip(quality, 0.05, 0.95)

    # A small portion of accounts become high-value whales.
    whale_prob = np.clip(0.02 + 0.20 * quality, 0.03, 0.18)
    is_high_value = rng.random(n_customers) < whale_prob

    # Churn behavior: lower-quality channels churn faster.
    lifetime_means = np.array(
        [CHANNEL_CONFIG[channel].avg_activity_span_days for channel in acquisition_channels],
        dtype=float,
    )
    lifetime_means = lifetime_means * (0.78 + 0.70 * quality)
    churn_days = rng.geometric(1 / np.maximum(lifetime_means, 1))

    signup_series = pd.to_datetime(signup_dates)
    churn_dates = signup_series + pd.to_timedelta(churn_days, unit="D")
    churn_dates = churn_dates.where(churn_dates <= END_DATE, pd.NaT)

    customers = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "signup_date": signup_series,
            "segment": segments,
            "region": regions,
            "acquisition_channel": acquisition_channels,
        }
    ).sort_values("signup_date", ignore_index=True)

    traits = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "quality": quality,
            "is_high_value": is_high_value,
            "churn_date": churn_dates,
        }
    )

    return customers, traits


def generate_transactions(
    customers: pd.DataFrame,
    traits: pd.DataFrame,
    *,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate transactional ledger with skewed revenue and margin variability."""
    customer_frame = customers.merge(traits, on="customer_id", how="left")

    records: list[dict[str, object]] = []
    tx_id = 1

    for row in customer_frame.itertuples(index=False):
        signup_date = pd.Timestamp(row.signup_date)
        churn_date = pd.Timestamp(row.churn_date) if pd.notna(row.churn_date) else END_DATE

        if churn_date < signup_date:
            continue

        month_starts = pd.date_range(
            signup_date.replace(day=1), churn_date.replace(day=1), freq="MS"
        )

        for month_start in month_starts:
            month_end = min(month_start + pd.offsets.MonthEnd(0), churn_date)
            active_start = max(signup_date, month_start)
            if month_end < active_start:
                continue

            # Transaction propensity depends on segment and customer quality.
            active_prob = np.clip(
                0.34 + 0.27 * row.quality + 0.06 * (row.segment in {"Mid-Market", "Enterprise"}),
                0.18,
                0.91,
            )

            if rng.random() > active_prob:
                continue

            base_lambda = SEGMENT_TX_LAMBDA[row.segment] * (0.60 + 0.95 * row.quality)
            n_tx = max(1, int(rng.poisson(lam=base_lambda)))

            day_window = (month_end - active_start).days
            for _ in range(n_tx):
                offset = int(rng.integers(0, day_window + 1)) if day_window > 0 else 0
                tx_date = active_start + pd.Timedelta(days=offset)

                product = rng.choice(PRODUCT_TYPES, p=PRODUCT_MIX_BY_SEGMENT[row.segment])
                base_revenue = SEGMENT_REVENUE_BASE[row.segment] * PRODUCT_PRICE_FACTOR[product]

                # Skew assumption: right-tailed spend behavior across customers.
                revenue = base_revenue * float(rng.lognormal(mean=0.0, sigma=0.88))

                # High-value customers occasionally create very large transactions.
                if row.is_high_value and rng.random() < 0.30:
                    revenue *= float(rng.uniform(2.3, 5.8))

                # Very low-quality customers include low-ticket purchases.
                if row.quality < 0.28 and rng.random() < 0.45:
                    revenue *= float(rng.uniform(0.30, 0.74))

                channel_cost = CHANNEL_CONFIG[row.acquisition_channel].cost_pressure
                cost_ratio = (
                    PRODUCT_COST_RATIO[product] + channel_cost + float(rng.normal(0, 0.055))
                )
                if row.quality < 0.30:
                    cost_ratio += 0.10
                if row.segment == "Enterprise":
                    cost_ratio += 0.04

                cost_ratio = float(np.clip(cost_ratio, 0.28, 1.30))
                cost = revenue * cost_ratio

                records.append(
                    {
                        "transaction_id": f"T{tx_id:09d}",
                        "customer_id": row.customer_id,
                        "transaction_date": tx_date,
                        "revenue": round(revenue, 2),
                        "cost": round(cost, 2),
                        "product_type": product,
                    }
                )
                tx_id += 1

    transactions = pd.DataFrame(records)
    transactions = transactions.sort_values("transaction_date", ignore_index=True)
    return transactions


def generate_marketing_spend(*, rng: np.random.Generator) -> pd.DataFrame:
    """Generate daily marketing spend by acquisition channel."""
    all_days = pd.date_range(START_DATE, END_DATE, freq="D")

    spend_base = {
        "paid_search": 1450,
        "social_ads": 1280,
        "referral": 390,
        "organic": 210,
        "partners": 520,
        "email": 320,
    }

    rows: list[dict[str, object]] = []
    horizon = len(all_days) - 1

    for day_idx, date in enumerate(all_days):
        trend = 1 + 0.42 * (day_idx / horizon)
        week_factor = 0.84 if date.dayofweek >= 5 else 1.00
        quarter_factor = 1.10 if date.quarter == 4 else (0.94 if date.quarter == 1 else 1.00)

        for channel, base in spend_base.items():
            channel_adj = 1.08 if channel in {"paid_search", "social_ads"} else 0.96
            noise = float(rng.normal(0, 0.11))

            spend = base * trend * week_factor * quarter_factor * channel_adj * (1 + noise)
            spend = max(30.0, spend)

            rows.append(
                {
                    "date": date,
                    "acquisition_channel": channel,
                    "spend": round(spend, 2),
                }
            )

    marketing = pd.DataFrame(rows)
    marketing = marketing.sort_values(["date", "acquisition_channel"], ignore_index=True)
    return marketing


def generate_marketing_touchpoints(
    customers: pd.DataFrame,
    *,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate ordered pre-signup journeys for descriptive multi-touch attribution."""
    rows: list[dict[str, object]] = []
    channel_probabilities = np.array([0.25, 0.19, 0.15, 0.17, 0.11, 0.13])
    touchpoint_id = 1

    for customer in customers.itertuples(index=False):
        touch_count = int(rng.integers(1, 5))
        signup_date = pd.Timestamp(customer.signup_date)
        earlier_channels = rng.choice(
            ACQUISITION_CHANNELS,
            size=max(0, touch_count - 1),
            p=channel_probabilities,
        ).tolist()
        channels = [*earlier_channels, customer.acquisition_channel]
        gaps = sorted(
            rng.integers(8, 61, size=max(0, touch_count - 1)).tolist(),
            reverse=True,
        )
        gaps.append(int(rng.integers(0, 8)))
        for order, (channel, gap) in enumerate(zip(channels, gaps, strict=True), start=1):
            rows.append(
                {
                    "touchpoint_id": f"TP{touchpoint_id:09d}",
                    "customer_id": customer.customer_id,
                    "touchpoint_date": signup_date - pd.Timedelta(days=int(gap)),
                    "acquisition_channel": channel,
                    "touchpoint_order": order,
                    "is_conversion_touch": order == touch_count,
                }
            )
            touchpoint_id += 1

    return pd.DataFrame(rows).sort_values(["customer_id", "touchpoint_order"], ignore_index=True)


def generate_marketing_experiments(
    customers: pd.DataFrame,
    *,
    rng: np.random.Generator,
    participants_per_channel: int = 1500,
) -> pd.DataFrame:
    """Generate randomized channel holdouts with customer-level outcomes."""
    if participants_per_channel <= 0:
        raise ValueError("participants_per_channel must be positive")
    eligible_channels = ("paid_search", "social_ads")
    segment_base = {"Startup": 72.0, "SMB": 128.0, "Mid-Market": 290.0, "Enterprise": 640.0}
    segment_conversion = {"Startup": 0.22, "SMB": 0.29, "Mid-Market": 0.36, "Enterprise": 0.43}
    rows: list[dict[str, object]] = []

    for channel in eligible_channels:
        eligible = customers.loc[customers["acquisition_channel"] == channel].copy()
        sample_size = min(participants_per_channel, len(eligible))
        selected_positions = rng.choice(len(eligible), size=sample_size, replace=False)
        selected = eligible.iloc[selected_positions].sort_values("customer_id")
        assignment = np.where(rng.random(sample_size) < 0.5, "treatment", "control")
        treatment = assignment == "treatment"
        base_probability = selected["segment"].map(segment_conversion).to_numpy(dtype=float)
        conversion_probability = np.clip(base_probability + 0.055 * treatment, 0.01, 0.95)
        converted = rng.random(sample_size) < conversion_probability
        pre_period = np.array(
            [segment_base[value] for value in selected["segment"]], dtype=float
        ) * rng.lognormal(0.0, 0.28, sample_size)
        contribution = np.where(
            converted,
            pre_period * (0.78 + 0.18 * treatment) * rng.lognormal(0.0, 0.32, sample_size),
            0.0,
        )
        assigned_date = pd.Timestamp("2025-07-01") + pd.to_timedelta(
            rng.integers(0, 28, sample_size), unit="D"
        )
        experiment_id = f"EXP-{channel.upper().replace('_', '-')}-2025H2"
        for idx, customer in enumerate(selected.itertuples(index=False)):
            rows.append(
                {
                    "experiment_id": experiment_id,
                    "customer_id": customer.customer_id,
                    "acquisition_channel": channel,
                    "assignment": assignment[idx],
                    "assigned_date": assigned_date[idx],
                    "outcome_window_days": 90,
                    "converted": bool(converted[idx]),
                    "pre_period_contribution": round(float(pre_period[idx]), 2),
                    "observed_contribution": round(float(contribution[idx]), 2),
                }
            )

    return pd.DataFrame(rows).sort_values(["experiment_id", "customer_id"], ignore_index=True)


def generate_pricing_interventions(*, rng: np.random.Generator) -> pd.DataFrame:
    """Generate randomized weekly price interventions with observed demand."""
    weeks = pd.date_range("2024-01-01", "2025-12-29", freq="W-MON")
    reference_price = {"Core": 165.0, "Add-on": 92.0, "Premium": 305.0, "Services": 388.0}
    base_units = {"Core": 230.0, "Add-on": 155.0, "Premium": 82.0, "Services": 54.0}
    true_elasticity = {"Core": -1.25, "Add-on": -1.55, "Premium": -0.82, "Services": -0.58}
    region_factor = {"North America": 1.18, "EMEA": 1.00, "LATAM": 0.62, "APAC": 0.79}
    variants = np.array(["price_down_10", "control", "price_up_10"])
    multiplier = {"price_down_10": 0.9, "control": 1.0, "price_up_10": 1.1}
    rows: list[dict[str, object]] = []
    intervention_id = 1

    for week_index, week in enumerate(weeks):
        seasonal = 1.0 + 0.12 * np.sin(2 * np.pi * week_index / 52.0)
        for product in PRODUCT_TYPES:
            for region in REGIONS:
                assignment = str(rng.choice(variants))
                price = reference_price[product] * multiplier[assignment]
                expected_units = (
                    base_units[product]
                    * region_factor[region]
                    * seasonal
                    * (price / reference_price[product]) ** true_elasticity[product]
                    * float(rng.lognormal(0.0, 0.08))
                )
                units = int(rng.poisson(max(expected_units, 1.0)))
                revenue = units * price
                margin = revenue * (1.0 - PRODUCT_COST_RATIO[product])
                rows.append(
                    {
                        "intervention_id": f"PI{intervention_id:07d}",
                        "week_start": week,
                        "product_type": product,
                        "region": region,
                        "assignment": assignment,
                        "reference_price": round(reference_price[product], 2),
                        "observed_price": round(price, 2),
                        "units_sold": units,
                        "revenue": round(revenue, 2),
                        "contribution_margin": round(margin, 2),
                    }
                )
                intervention_id += 1

    return pd.DataFrame(rows).sort_values("intervention_id", ignore_index=True)


def generate_datasets(
    seed: int = SEED,
    n_customers: int = 9000,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate all public raw tables from one isolated random stream."""
    rng = np.random.default_rng(seed)
    customers, traits = generate_customers(n_customers, rng=rng)
    transactions = generate_transactions(customers, traits, rng=rng)
    marketing_spend = generate_marketing_spend(rng=rng)
    return customers, transactions, marketing_spend


def save_outputs(
    customers: pd.DataFrame, transactions: pd.DataFrame, marketing: pd.DataFrame
) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    customers_out = customers.copy()
    transactions_out = transactions.copy()
    marketing_out = marketing.copy()

    customers_out["signup_date"] = pd.to_datetime(customers_out["signup_date"]).dt.date
    transactions_out["transaction_date"] = pd.to_datetime(
        transactions_out["transaction_date"]
    ).dt.date
    marketing_out["date"] = pd.to_datetime(marketing_out["date"]).dt.date

    customers_out.to_csv(RAW_DIR / "customers.csv", index=False)
    transactions_out.to_csv(RAW_DIR / "transactions.csv", index=False)
    marketing_out.to_csv(RAW_DIR / "marketing_spend.csv", index=False)


def save_expansion_outputs(
    touchpoints: pd.DataFrame,
    experiments: pd.DataFrame,
    pricing_interventions: pd.DataFrame,
) -> None:
    """Publish causal-design inputs separately from the core commercial ledger."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    touchpoints_out = touchpoints.copy()
    experiments_out = experiments.copy()
    pricing_out = pricing_interventions.copy()
    touchpoints_out["touchpoint_date"] = pd.to_datetime(touchpoints_out["touchpoint_date"]).dt.date
    experiments_out["assigned_date"] = pd.to_datetime(experiments_out["assigned_date"]).dt.date
    pricing_out["week_start"] = pd.to_datetime(pricing_out["week_start"]).dt.date
    touchpoints_out.to_csv(RAW_DIR / "marketing_touchpoints.csv", index=False)
    experiments_out.to_csv(RAW_DIR / "marketing_experiments.csv", index=False)
    pricing_out.to_csv(RAW_DIR / "pricing_interventions.csv", index=False)


def main() -> None:
    customers, transactions, marketing_spend = generate_datasets(seed=SEED)
    expansion_rng = np.random.default_rng(np.random.SeedSequence([SEED, 2026]))
    touchpoints = generate_marketing_touchpoints(customers, rng=expansion_rng)
    experiments = generate_marketing_experiments(customers, rng=expansion_rng)
    pricing_interventions = generate_pricing_interventions(rng=expansion_rng)

    save_outputs(customers, transactions, marketing_spend)
    save_expansion_outputs(touchpoints, experiments, pricing_interventions)

    print("Synthetic data generated successfully.")
    print(f"customers: {len(customers):,}")
    print(f"transactions: {len(transactions):,}")
    print(f"marketing_spend rows: {len(marketing_spend):,}")
    print(f"marketing_touchpoints rows: {len(touchpoints):,}")
    print(f"marketing_experiments rows: {len(experiments):,}")
    print(f"pricing_interventions rows: {len(pricing_interventions):,}")
    print(f"output_dir: {RAW_DIR}")


if __name__ == "__main__":
    main()
