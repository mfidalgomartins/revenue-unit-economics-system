"""Build a self-contained executive HTML dashboard with embedded data."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.governance.metric_registry import to_payload_dict
from src.paths import PROJECT_ROOT, RAW_DATA_DIR

RAW_DIR = RAW_DATA_DIR
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
DASHBOARD_DIR = PROJECT_ROOT / "outputs" / "dashboard"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"])
    transactions = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["transaction_date"])
    marketing = pd.read_csv(RAW_DIR / "marketing_spend.csv", parse_dates=["date"])
    unit_economics = pd.read_csv(PROCESSED_DIR / "unit_economics.csv")
    return customers, transactions, marketing, unit_economics


_EPOCH = pd.Timestamp("1970-01-01")


def _day_ints(dates: pd.Series) -> list[int]:
    return [int(d) for d in (dates - _EPOCH).dt.days]


def build_embedded_payload(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    marketing: pd.DataFrame,
    plan: pd.DataFrame | None = None,
    unit_economics: pd.DataFrame | None = None,
) -> Mapping[str, object]:
    """Encode the three tables as compact parallel arrays.

    Dates become integer day offsets, dimensions become indexes into the
    meta.values lists, and customer ids become row indexes. The dashboard's
    decodePayload() expands this back into per-record objects, so the
    embedded JSON stays a fraction of the row-wise size at any data volume.
    """
    segments = sorted(customers["segment"].dropna().unique().tolist())
    regions = sorted(customers["region"].dropna().unique().tolist())
    channels = sorted(customers["acquisition_channel"].dropna().unique().tolist())
    products = sorted(transactions["product_type"].dropna().unique().tolist())

    seg_ix = {v: i for i, v in enumerate(segments)}
    reg_ix = {v: i for i, v in enumerate(regions)}
    ch_ix = {v: i for i, v in enumerate(channels)}
    prod_ix = {v: i for i, v in enumerate(products)}
    cid_ix = {cid: i for i, cid in enumerate(customers["customer_id"])}

    customer_cols = {
        "sd": _day_ints(customers["signup_date"]),
        "seg": customers["segment"].map(seg_ix).astype(int).tolist(),
        "reg": customers["region"].map(reg_ix).astype(int).tolist(),
        "ch": customers["acquisition_channel"].map(ch_ix).astype(int).tolist(),
    }
    transaction_cols = {
        "d": _day_ints(transactions["transaction_date"]),
        "ci": transactions["customer_id"].map(cid_ix).astype(int).tolist(),
        "prod": transactions["product_type"].map(prod_ix).astype(int).tolist(),
        "rev": transactions["revenue"].round(2).tolist(),
        "cost": transactions["cost"].round(2).tolist(),
    }
    marketing_cols = {
        "d": _day_ints(marketing["date"]),
        "ch": marketing["acquisition_channel"].map(ch_ix).astype(int).tolist(),
        "spend": marketing["spend"].round(2).tolist(),
    }

    coverage_start = min(transactions["transaction_date"].min(), marketing["date"].min()).strftime(
        "%Y-%m-%d"
    )
    coverage_end = max(transactions["transaction_date"].max(), marketing["date"].max()).strftime(
        "%Y-%m-%d"
    )

    payload = {
        "meta": {
            "project_name": "Revenue Analytics & Unit Economics System",
            "dashboard_title": "Growth Quality Dashboard",
            "question": "How do acquisition economics, cohort activity, and margin quality change as revenue scales?",
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "data_fingerprint": int(
                int(pd.util.hash_pandas_object(customers.assign(_table="customers")).sum())
                + int(pd.util.hash_pandas_object(transactions.assign(_table="transactions")).sum())
                + int(pd.util.hash_pandas_object(marketing.assign(_table="marketing")).sum())
            ),
            "values": {
                "segments": segments,
                "regions": regions,
                "acquisition_channels": channels,
                "product_types": products,
            },
            "metric_policy": to_payload_dict(),
        },
        "customers": customer_cols,
        "transactions": transaction_cols,
        "marketing_spend": marketing_cols,
    }

    if plan is not None:
        # Per-channel policy outputs for the what-if stress card. The browser
        # applies CAC/LTV multipliers with the same formula as the pipeline's
        # stress engine: sum(spend / (cac * m_c) * ltv * m_l) - baseline.
        payload["whatif"] = {
            "ch": [ch_ix[c] for c in plan["acquisition_channel"]],
            "spend": plan["scenario_spend"].round(2).tolist(),
            "cac": plan["scenario_cac_assumed"].round(4).tolist(),
            "ltv": plan["scenario_ltv_assumed"].round(4).tolist(),
            "baseline_total": round(float(plan["baseline_contribution_est"].sum()), 2),
        }
    if unit_economics is not None:
        unit_economics_sorted = unit_economics.sort_values("acquisition_channel", ignore_index=True)
        unit_records = (
            unit_economics_sorted.astype(object)
            .where(pd.notna(unit_economics_sorted), None)
            .to_dict(orient="records")
        )
        payload["unit_economics"] = unit_records
    return payload


def build_api_bootstrap_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    """Keep only aggregate configuration required before authenticated API loading."""
    bootstrap = {
        "meta": deepcopy(payload["meta"]),
        "customers": {"sd": [], "seg": [], "reg": [], "ch": []},
        "transactions": {"d": [], "ci": [], "prod": [], "rev": [], "cost": []},
        "marketing_spend": {"d": [], "ch": [], "spend": []},
    }
    for optional_key in ("whatif", "unit_economics"):
        if optional_key in payload:
            bootstrap[optional_key] = deepcopy(payload[optional_key])
    return bootstrap


def build_dashboard_html(
    payload: Mapping[str, object],
    *,
    api_mode: bool = False,
) -> str:
    data_json = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    for character, escaped in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        data_json = data_json.replace(character, escaped)

    template = (ASSETS_DIR / "dashboard.html").read_text(encoding="utf-8")

    connect_source = "'self'" if api_mode else "'none'"
    return (
        template.replace("__DATA_JSON__", data_json)
        .replace("__API_MODE__", "true" if api_mode else "false")
        .replace("__CONNECT_SRC__", connect_source)
    )


def run() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    customers, transactions, marketing, unit_economics = load_inputs()
    plan = pd.read_csv(TABLES_DIR / "scenario_reallocation_plan.csv")
    payload = build_embedded_payload(
        customers,
        transactions,
        marketing,
        plan=plan,
        unit_economics=unit_economics,
    )
    html = build_dashboard_html(payload)

    out_path = DASHBOARD_DIR / "growth-quality-dashboard.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"Dashboard written: {out_path}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
