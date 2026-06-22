"""Invariants and determinism for the synthetic data generator.

These tests exercise the generator on small customer counts so they stay fast
while still asserting the structural guarantees the rest of the pipeline relies
on: stable schemas, valid category domains, non-negative money, in-window dates,
and reproducibility under a fixed RNG seed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import src.data_generation.generate_synthetic_data as gen


def _reseed(seed: int = 7) -> None:
    """Reset the module-level RNG so a generation run is reproducible."""
    gen.RNG = np.random.default_rng(seed)


def test_build_signup_dates_are_in_window_and_complete() -> None:
    _reseed()
    dates = pd.to_datetime(gen._build_signup_dates(200))
    assert len(dates) == 200
    assert dates.min() >= gen.START_DATE
    assert dates.max() <= gen.END_DATE


def test_generate_customers_schema_and_domains() -> None:
    _reseed()
    customers, traits = gen.generate_customers(120)

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
    _reseed()
    customers, traits = gen.generate_customers(150)
    transactions = gen.generate_transactions(customers, traits)

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
    _reseed()
    marketing = gen.generate_marketing_spend()
    n_days = len(pd.date_range(gen.START_DATE, gen.END_DATE, freq="D"))
    n_channels = 6

    assert len(marketing) == n_days * n_channels
    assert set(marketing["acquisition_channel"]) == set(gen.CHANNEL_CONFIG)
    # Spend floor of 30 is enforced for every row.
    assert (marketing["spend"] >= 30.0).all()


def test_generation_is_deterministic_under_fixed_seed() -> None:
    _reseed(123)
    customers_a, traits_a = gen.generate_customers(80)
    transactions_a = gen.generate_transactions(customers_a, traits_a)

    _reseed(123)
    customers_b, traits_b = gen.generate_customers(80)
    transactions_b = gen.generate_transactions(customers_b, traits_b)

    pd.testing.assert_frame_equal(customers_a, customers_b)
    pd.testing.assert_frame_equal(transactions_a, transactions_b)
