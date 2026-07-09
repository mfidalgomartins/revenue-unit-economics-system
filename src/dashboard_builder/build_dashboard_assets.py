"""Build a self-contained executive HTML dashboard with embedded data."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from src.governance.metric_registry import to_payload_dict
from src.paths import PROJECT_ROOT

RAW_DIR = PROJECT_ROOT / "data" / "raw"
DASHBOARD_DIR = PROJECT_ROOT / "outputs" / "dashboard"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"])
    transactions = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["transaction_date"])
    marketing = pd.read_csv(RAW_DIR / "marketing_spend.csv", parse_dates=["date"])
    return customers, transactions, marketing


_EPOCH = pd.Timestamp("1970-01-01")


def _day_ints(dates: pd.Series) -> list[int]:
    return [int(d) for d in (dates - _EPOCH).dt.days]


def build_embedded_payload(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    marketing: pd.DataFrame,
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

    coverage_start = min(
        transactions["transaction_date"].min(), marketing["date"].min()
    ).strftime("%Y-%m-%d")
    coverage_end = max(
        transactions["transaction_date"].max(), marketing["date"].max()
    ).strftime("%Y-%m-%d")

    payload = {
        "meta": {
            "project_name": "Revenue Analytics & Unit Economics System",
            "dashboard_title": "Growth Quality Dashboard",
            "question": "Is the company growing sustainably, or is it relying on unprofitable growth?",
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
    return payload


def build_dashboard_html(payload: Mapping[str, object]) -> str:
    data_json = json.dumps(payload, separators=(",", ":"))

    template = (ASSETS_DIR / "dashboard.html").read_text(encoding="utf-8")

    return template.replace("__DATA_JSON__", data_json)


def run() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    customers, transactions, marketing = load_inputs()
    payload = build_embedded_payload(customers, transactions, marketing)
    html = build_dashboard_html(payload)

    out_path = DASHBOARD_DIR / "growth-quality-dashboard.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"Dashboard written: {out_path}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
