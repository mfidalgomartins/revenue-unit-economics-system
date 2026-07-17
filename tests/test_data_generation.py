"""Invariants and determinism for the synthetic data generator.

These tests exercise the generator on small customer counts so they stay fast
while still asserting the structural guarantees the rest of the pipeline relies
on: stable schemas, valid category domains, non-negative money, in-window dates,
and reproducibility under a fixed RNG seed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import src.data_generation.generate_synthetic_data as gen
from src.paths import PROJECT_ROOT


def _rng(seed: int = 7) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_build_signup_dates_are_in_window_and_complete() -> None:
    dates = pd.to_datetime(gen._build_signup_dates(200, rng=_rng()))
    assert len(dates) == 200
    assert dates.min() >= gen.START_DATE
    assert dates.max() <= gen.END_DATE


def test_generate_customers_schema_and_domains() -> None:
    customers, traits = gen.generate_customers(120, rng=_rng())

    assert list(customers.columns) == [
        "customer_id",
        "signup_date",
        "segment",
        "region",
        "acquisition_channel",
    ]
    assert len(customers) == 120
    assert customers["customer_id"].is_unique
    assert set(customers["segment"]).issubset(set(gen.SEGMENTS))
    assert set(customers["region"]).issubset(set(gen.REGIONS))
    assert set(customers["acquisition_channel"]).issubset(set(gen.CHANNEL_CONFIG))
    # Output is sorted ascending by signup_date.
    assert customers["signup_date"].is_monotonic_increasing

    # Traits align one-to-one with customers and stay in expected bounds.
    assert set(traits["customer_id"]) == set(customers["customer_id"])
    assert traits["quality"].between(0.05, 0.95).all()
    assert traits["is_high_value"].dtype == bool


def test_generate_transactions_are_valid_facts() -> None:
    rng = _rng()
    customers, traits = gen.generate_customers(150, rng=rng)
    transactions = gen.generate_transactions(customers, traits, rng=rng)

    assert list(transactions.columns) == [
        "transaction_id",
        "customer_id",
        "transaction_date",
        "revenue",
        "cost",
        "product_type",
    ]
    assert transactions["transaction_id"].is_unique
    assert (transactions["revenue"] > 0).all()
    assert (transactions["cost"] >= 0).all()
    assert set(transactions["product_type"]).issubset(set(gen.PRODUCT_TYPES))
    # Every transaction references a known customer and falls in the window.
    assert transactions["customer_id"].isin(customers["customer_id"]).all()
    assert transactions["transaction_date"].min() >= gen.START_DATE
    assert transactions["transaction_date"].max() <= gen.END_DATE


def test_generate_marketing_spend_is_complete_grid() -> None:
    marketing = gen.generate_marketing_spend(rng=_rng())
    n_days = len(pd.date_range(gen.START_DATE, gen.END_DATE, freq="D"))
    n_channels = 6

    assert len(marketing) == n_days * n_channels
    assert set(marketing["acquisition_channel"]) == set(gen.CHANNEL_CONFIG)
    # Spend floor of 30 is enforced for every row.
    assert (marketing["spend"] >= 30.0).all()


def test_generation_is_deterministic_and_isolated_by_seed() -> None:
    datasets_a = gen.generate_datasets(seed=123, n_customers=80)
    gen.generate_datasets(seed=999, n_customers=40)
    datasets_b = gen.generate_datasets(seed=123, n_customers=80)

    for frame_a, frame_b in zip(datasets_a, datasets_b, strict=True):
        pd.testing.assert_frame_equal(frame_a, frame_b)


def test_expansion_generators_create_governed_intervention_inputs() -> None:
    customers, _ = gen.generate_customers(300, rng=_rng(21))
    customers.loc[:49, "acquisition_channel"] = "paid_search"
    customers.loc[50:99, "acquisition_channel"] = "social_ads"
    rng = _rng(22)

    touchpoints = gen.generate_marketing_touchpoints(customers, rng=rng)
    experiments = gen.generate_marketing_experiments(
        customers, rng=rng, participants_per_channel=40
    )
    pricing = gen.generate_pricing_interventions(rng=rng)

    assert touchpoints["touchpoint_id"].is_unique
    assert touchpoints.groupby("customer_id")["is_conversion_touch"].sum().eq(1).all()
    touch_signup = touchpoints["customer_id"].map(customers.set_index("customer_id")["signup_date"])
    assert (touchpoints["touchpoint_date"] <= touch_signup).all()
    assert set(experiments["assignment"]) == {"control", "treatment"}
    assert experiments.groupby("experiment_id")["assignment"].nunique().eq(2).all()
    assert (experiments["observed_contribution"] >= 0).all()
    assert pricing["intervention_id"].is_unique
    assert pricing.groupby(["product_type", "region"])["assignment"].nunique().eq(3).all()
    ratios = pricing["observed_price"] / pricing["reference_price"]
    assert set(ratios.round(1)) == {0.9, 1.0, 1.1}


def test_expansion_generation_validates_participant_count() -> None:
    customers, _ = gen.generate_customers(10, rng=_rng())
    with pytest.raises(ValueError, match="positive"):
        gen.generate_marketing_experiments(customers, rng=_rng(), participants_per_channel=0)


def test_save_expansion_outputs_writes_stable_schemas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    customers, _ = gen.generate_customers(40, rng=_rng(31))
    customers.loc[:9, "acquisition_channel"] = "paid_search"
    customers.loc[10:19, "acquisition_channel"] = "social_ads"
    rng = _rng(32)
    monkeypatch.setattr(gen, "RAW_DIR", tmp_path)
    gen.save_expansion_outputs(
        gen.generate_marketing_touchpoints(customers, rng=rng),
        gen.generate_marketing_experiments(customers, rng=rng, participants_per_channel=5),
        gen.generate_pricing_interventions(rng=rng),
    )
    assert {path.name for path in tmp_path.glob("*.csv")} == {
        "marketing_touchpoints.csv",
        "marketing_experiments.csv",
        "pricing_interventions.csv",
    }


def test_seed_42_outputs_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path
    monkeypatch.setattr(gen, "RAW_DIR", output_dir)
    gen.save_outputs(*gen.generate_datasets(seed=42))

    for file_name in ("customers.csv", "transactions.csv", "marketing_spend.csv"):
        expected = (PROJECT_ROOT / "data" / "raw" / file_name).read_bytes()
        assert (output_dir / file_name).read_bytes() == expected
