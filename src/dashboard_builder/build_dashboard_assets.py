"""Build a self-contained executive HTML dashboard with embedded data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.governance.metric_registry import to_payload_dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DASHBOARD_DIR = PROJECT_ROOT / "outputs" / "dashboard"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = pd.read_csv(RAW_DIR / "customers.csv", parse_dates=["signup_date"])
    transactions = pd.read_csv(RAW_DIR / "transactions.csv", parse_dates=["transaction_date"])
    marketing = pd.read_csv(RAW_DIR / "marketing_spend.csv", parse_dates=["date"])
    return customers, transactions, marketing


def build_embedded_payload(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    marketing: pd.DataFrame,
) -> dict:
    tx = transactions.copy()

    tx_records = []
    for row in tx.itertuples(index=False):
        tx_records.append(
            {
                "d": pd.Timestamp(row.transaction_date).strftime("%Y-%m-%d"),
                "cid": row.customer_id,
                "prod": row.product_type,
                "rev": round(float(row.revenue), 2),
                "cost": round(float(row.cost), 2),
            }
        )

    customer_records = []
    for row in customers.itertuples(index=False):
        customer_records.append(
            {
                "cid": row.customer_id,
                "sd": pd.Timestamp(row.signup_date).strftime("%Y-%m-%d"),
                "seg": row.segment,
                "reg": row.region,
                "ch": row.acquisition_channel,
            }
        )

    marketing_records = []
    for row in marketing.itertuples(index=False):
        marketing_records.append(
            {
                "d": pd.Timestamp(row.date).strftime("%Y-%m-%d"),
                "ch": row.acquisition_channel,
                "spend": round(float(row.spend), 2),
            }
        )

    coverage_start = min(min(t["d"] for t in tx_records), min(m["d"] for m in marketing_records))
    coverage_end = max(max(t["d"] for t in tx_records), max(m["d"] for m in marketing_records))

    payload = {
        "meta": {
            "project_name": "Revenue Analytics & Unit Economics System",
            "dashboard_title": "Executive Growth Quality Dashboard",
            "question": "Is the company growing sustainably, or is it relying on unprofitable growth?",
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "data_fingerprint": int(
                int(pd.util.hash_pandas_object(customers.assign(_table="customers")).sum())
                + int(pd.util.hash_pandas_object(transactions.assign(_table="transactions")).sum())
                + int(pd.util.hash_pandas_object(marketing.assign(_table="marketing")).sum())
            ),
            "values": {
                "segments": sorted(customers["segment"].dropna().unique().tolist()),
                "regions": sorted(customers["region"].dropna().unique().tolist()),
                "acquisition_channels": sorted(
                    customers["acquisition_channel"].dropna().unique().tolist()
                ),
                "product_types": sorted(transactions["product_type"].dropna().unique().tolist()),
            },
            "metric_policy": to_payload_dict(),
        },
        "customers": customer_records,
        "transactions": tx_records,
        "marketing_spend": marketing_records,
    }
    return payload


def build_dashboard_html(payload: dict) -> str:
    data_json = json.dumps(payload, separators=(",", ":"))

    template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Executive Growth Quality Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #edf2f7;
      --panel: #ffffff;
      --panel-soft: #f7f9fc;
      --panel-tint: #f2f6fb;
      --ink: #08111f;
      --sub: #4d5d76;
      --line: #d5dde8;
      --line-soft: #e8edf4;
      --brand: #1f4fbf;
      --brand-strong: #143983;
      --brand-soft: rgba(31, 79, 191, 0.10);
      --good: #0f9d58;
      --bad: #c62828;
      --warn: #b26a00;
      --good-soft: rgba(15, 157, 88, 0.12);
      --bad-soft: rgba(198, 40, 40, 0.10);
      --warn-soft: rgba(178, 106, 0, 0.12);
      --rev: #0b4f6c;
      --cost: #bf3b2f;
      --margin: #1f9d89;
      --accent: #e7a100;
      --bar: #2f3b5a;
      --header-grad-a: #fefefe;
      --header-grad-b: #edf3fb;
      --hero-ink: #08111f;
      --hero-sub: #53657f;
      --chip-bg: #eef2f9;
      --chip-border: #c8d3ea;
      --chip-ink: #2b3b63;
      --control-bg: #ffffff;
      --control-border: #c9d3e2;
      --table-head-bg: #f5f7fb;
      --table-row-hover: #f2f5fb;
      --chart-grid: #e2e8f0;
      --chart-axis: #8fa1b8;
      --chart-text: #2a3b52;
      --chart-muted: #60738c;
      --tooltip-bg: rgba(12, 18, 32, 0.94);
      --shadow: 0 16px 40px rgba(15, 23, 42, 0.12);
      --shadow-soft: 0 10px 26px rgba(15, 23, 42, 0.08);
      --shadow-lift: 0 22px 52px rgba(15, 23, 42, 0.16);
      --focus-ring: 0 0 0 3px rgba(31, 79, 191, 0.16);
    }

    body[data-theme="dark"] {
      color-scheme: dark;
      --bg: #071425;
      --panel: #0d1b31;
      --panel-soft: #112544;
      --panel-tint: #10233f;
      --ink: #e6eefb;
      --sub: #a8bddc;
      --line: #1e3658;
      --line-soft: #274166;
      --brand: #6ea8ff;
      --brand-strong: #9fc3ff;
      --brand-soft: rgba(110, 168, 255, 0.14);
      --good: #4ade80;
      --bad: #fb7185;
      --warn: #facc15;
      --good-soft: rgba(74, 222, 128, 0.16);
      --bad-soft: rgba(251, 113, 133, 0.16);
      --warn-soft: rgba(250, 204, 21, 0.14);
      --rev: #8bd4ff;
      --cost: #f8a29a;
      --margin: #6ee7cf;
      --accent: #facc15;
      --bar: #9db9ff;
      --header-grad-a: #0d1b31;
      --header-grad-b: #132647;
      --hero-ink: #eef5ff;
      --hero-sub: #abc0dd;
      --chip-bg: #142948;
      --chip-border: #2a4a76;
      --chip-ink: #d7e6ff;
      --control-bg: #132646;
      --control-border: #2c4b77;
      --table-head-bg: #132646;
      --table-row-hover: #132a4a;
      --chart-grid: #2b4569;
      --chart-axis: #6f8fb5;
      --chart-text: #c7d7f2;
      --chart-muted: #8fa7c6;
      --tooltip-bg: rgba(2, 6, 23, 0.96);
      --shadow: 0 18px 42px rgba(2, 6, 23, 0.48);
      --shadow-soft: 0 10px 26px rgba(2, 6, 23, 0.36);
      --shadow-lift: 0 26px 58px rgba(2, 6, 23, 0.52);
      --focus-ring: 0 0 0 3px rgba(110, 168, 255, 0.18);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI Variable", "SF Pro Display", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(31, 79, 191, 0.10), transparent 24%),
        radial-gradient(circle at top right, rgba(231, 161, 0, 0.08), transparent 18%),
        linear-gradient(180deg, rgba(255,255,255,0.5), rgba(255,255,255,0) 22%),
        var(--bg);
      color: var(--ink);
      transition: background 180ms ease, color 180ms ease;
    }

    body[data-theme="dark"] {
      background:
        radial-gradient(circle at top left, rgba(110, 168, 255, 0.10), transparent 24%),
        radial-gradient(circle at top right, rgba(250, 204, 21, 0.08), transparent 18%),
        linear-gradient(180deg, rgba(19, 38, 71, 0.38), rgba(19, 38, 71, 0) 22%),
        var(--bg);
    }

    .container {
      width: min(1520px, 95vw);
      margin: 24px auto 64px;
      display: grid;
      gap: 20px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 22px;
      position: relative;
      overflow: hidden;
    }

    .panel::before {
      content: "";
      position: absolute;
      inset: 0 0 auto 0;
      height: 1px;
      background: linear-gradient(90deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0));
      opacity: 0.7;
      pointer-events: none;
    }

    body[data-theme="dark"] .panel::before {
      background: linear-gradient(90deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0));
    }

    .panel > * {
      position: relative;
      z-index: 1;
    }

    .header-panel {
      display: grid;
      gap: 20px;
      background: linear-gradient(145deg, var(--header-grad-a), var(--header-grad-b));
      padding: 22px;
      overflow: hidden;
      position: relative;
    }

    .header-panel::after {
      content: "";
      position: absolute;
      inset: auto -8% -28% auto;
      width: 380px;
      height: 380px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(31, 79, 191, 0.13), transparent 65%);
      pointer-events: none;
    }

    .header-panel::before {
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(120deg, rgba(255,255,255,0.10), transparent 36%),
        radial-gradient(circle at 78% 22%, rgba(255,255,255,0.12), transparent 20%);
      pointer-events: none;
    }

    .header-top {
      display: flex;
      justify-content: flex-end;
      gap: 16px;
      align-items: flex-start;
      flex-wrap: wrap;
    }

    .header-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.8fr) minmax(320px, 0.95fr);
      gap: 18px;
      align-items: stretch;
      position: relative;
      z-index: 1;
    }

    .header-copy {
      display: grid;
      gap: 10px;
      align-content: start;
    }

    .eyebrow {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 999px;
      background: var(--brand-soft);
      color: var(--brand-strong);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    h1 {
      margin: 0;
      font-size: 34px;
      line-height: 1.05;
      color: var(--hero-ink);
      letter-spacing: -0.03em;
    }

    .subtitle {
      margin-top: 2px;
      color: var(--hero-sub);
      font-size: 16px;
      line-height: 1.5;
      max-width: 860px;
    }

    .header-tools {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .signal-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 4px;
    }

    .signal-pill {
      display: inline-flex;
      align-items: center;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.55);
      border: 1px solid var(--chip-border);
      color: var(--chip-ink);
      font-size: 12px;
      font-weight: 700;
      backdrop-filter: blur(8px);
    }

    body[data-theme="dark"] .signal-pill {
      background: rgba(13, 27, 49, 0.78);
    }

    .decision-brief {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: linear-gradient(180deg, var(--panel), var(--panel-tint));
      padding: 20px;
      display: grid;
      gap: 14px;
      box-shadow: var(--shadow-soft);
    }

    .decision-title {
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: var(--sub);
    }

    .decision-text {
      color: var(--ink);
      font-size: 14px;
      line-height: 1.5;
    }

    .rule-grid {
      display: grid;
      gap: 10px;
    }

    .rule-chip {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
      font-size: 12px;
      line-height: 1.35;
      color: var(--chart-text);
    }

    .rule-chip strong {
      color: var(--ink);
      font-size: 12px;
    }

    .print-coverage {
      display: none;
      margin-top: 6px;
      font-size: 12px;
      color: var(--sub);
    }

    .meta-chip {
      background: var(--chip-bg);
      border: 1px solid var(--chip-border);
      color: var(--chip-ink);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      white-space: nowrap;
    }

    .theme-btn,
    .print-btn {
      border: 1px solid var(--chip-border);
      background: rgba(255, 255, 255, 0.72);
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 13px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      white-space: nowrap;
      backdrop-filter: blur(8px);
      transition: transform 140ms ease, background 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
    }

    .theme-btn:hover,
    .print-btn:hover {
      background: var(--panel-soft);
      transform: translateY(-1px);
      box-shadow: var(--shadow-soft);
    }

    body[data-theme="dark"] .theme-btn,
    body[data-theme="dark"] .print-btn {
      background: rgba(13, 27, 49, 0.82);
    }

    .theme-btn:focus-visible,
    .print-btn:focus-visible,
    .btn:focus-visible,
    input[type="date"]:focus-visible,
    select:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }

    .filters-shell {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.66);
      backdrop-filter: blur(10px);
      padding: 16px;
      display: grid;
      gap: 14px;
      position: relative;
      z-index: 1;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
    }

    body[data-theme="dark"] .filters-shell {
      background: rgba(13, 27, 49, 0.72);
    }

    .filters-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
    }

    .filters-title {
      margin: 0 0 4px;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--sub);
    }

    .filters-note {
      margin: 0;
      max-width: 760px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--chart-text);
    }

    .filter-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }

    .filter-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(150px, 1fr));
      gap: 14px;
      align-items: end;
    }

    .filter-group {
      display: grid;
      gap: 8px;
      align-content: start;
      padding: 12px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,0.50), rgba(255,255,255,0.16));
      box-shadow: var(--shadow-soft);
    }

    body[data-theme="dark"] .filter-group {
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(0,0,0,0.04));
    }

    .filter-group label {
      font-size: 12px;
      color: var(--sub);
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    input[type="date"], select {
      width: 100%;
      border: 1px solid var(--control-border);
      border-radius: 12px;
      padding: 10px 11px;
      font-size: 13px;
      background: var(--control-bg);
      color: var(--ink);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.34);
      transition: border-color 120ms ease, box-shadow 120ms ease, background 120ms ease;
    }

    select[multiple] {
      min-height: 112px;
      padding: 8px 10px;
    }

    .btn {
      border: 1px solid var(--control-border);
      background: linear-gradient(180deg, var(--panel), var(--panel-soft));
      color: var(--ink);
      border-radius: 999px;
      padding: 9px 14px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: var(--shadow-soft);
      transition: transform 140ms ease, background 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
    }

    .btn:hover {
      background: var(--control-bg);
      transform: translateY(-1px);
      box-shadow: var(--shadow);
    }

    .summary-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(220px, 1fr));
      gap: 14px;
    }

    .summary-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px 16px;
      background: linear-gradient(180deg, var(--panel), var(--panel-tint));
      box-shadow: var(--shadow-soft);
      position: relative;
      overflow: hidden;
      display: grid;
      gap: 8px;
      transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
    }

    .summary-card::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      height: 4px;
      width: 100%;
      background: linear-gradient(90deg, var(--brand), var(--accent));
      opacity: 0.85;
    }

    .summary-card[data-tone="good"]::before { background: linear-gradient(90deg, var(--good), var(--brand)); }
    .summary-card[data-tone="warn"]::before { background: linear-gradient(90deg, var(--warn), var(--accent)); }
    .summary-card[data-tone="bad"]::before { background: linear-gradient(90deg, var(--bad), var(--accent)); }

    .summary-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }

    .summary-title {
      font-size: 12px;
      color: var(--sub);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .summary-badge {
      flex: 0 0 auto;
      padding: 5px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      background: var(--brand-soft);
      color: var(--brand-strong);
    }

    .summary-badge.good {
      color: var(--good);
      background: var(--good-soft);
    }

    .summary-badge.warn {
      color: var(--warn);
      background: var(--warn-soft);
    }

    .summary-badge.bad {
      color: var(--bad);
      background: var(--bad-soft);
    }

    .summary-text {
      font-size: 14px;
      line-height: 1.5;
      color: var(--ink);
    }

    .summary-card:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-lift);
    }

    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(7, minmax(145px, 1fr));
      gap: 12px;
    }

    .kpi-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: linear-gradient(180deg, var(--panel), var(--panel-tint));
      min-height: 132px;
      box-shadow: var(--shadow-soft);
      display: grid;
      gap: 6px;
      position: relative;
      overflow: hidden;
      transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
    }

    .kpi-card::before {
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 4px;
      background: linear-gradient(90deg, var(--brand), rgba(255,255,255,0));
      opacity: 0.88;
    }

    .kpi-card[data-tone="good"] {
      border-color: rgba(15, 157, 88, 0.22);
      background: linear-gradient(180deg, var(--panel), var(--good-soft));
    }

    .kpi-card[data-tone="warn"] {
      border-color: rgba(178, 106, 0, 0.24);
      background: linear-gradient(180deg, var(--panel), var(--warn-soft));
    }

    .kpi-card[data-tone="bad"] {
      border-color: rgba(198, 40, 40, 0.20);
      background: linear-gradient(180deg, var(--panel), var(--bad-soft));
    }

    .kpi-label {
      font-size: 12px;
      color: var(--sub);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .kpi-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
    }

    .kpi-label-wrap {
      display: grid;
      gap: 2px;
    }

    .kpi-state {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 8px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: var(--brand-soft);
      color: var(--brand-strong);
      white-space: nowrap;
    }

    .kpi-state.good {
      background: var(--good-soft);
      color: var(--good);
    }

    .kpi-state.warn {
      background: var(--warn-soft);
      color: #b26a00;
    }

    .kpi-state.bad {
      background: var(--bad-soft);
      color: var(--bad);
    }

    body[data-theme="dark"] .kpi-state.warn {
      color: var(--warn);
    }

    .kpi-state-dot {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: currentColor;
      box-shadow: 0 0 0 3px rgba(255,255,255,0.12);
    }

    .kpi-value {
      font-size: 30px;
      font-weight: 800;
      line-height: 1.1;
      color: var(--ink);
      margin-bottom: 2px;
      letter-spacing: -0.03em;
    }

    .kpi-delta { font-size: 12px; font-weight: 700; }
    .kpi-delta.positive { color: var(--good); }
    .kpi-delta.negative { color: var(--bad); }
    .kpi-delta.neutral { color: var(--sub); }
    .kpi-note { font-size: 11px; color: var(--sub); margin-top: 2px; line-height: 1.35; }

    .kpi-card:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-lift);
    }

    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 14px;
      gap: 12px;
    }

    .section-head h2 {
      margin: 0;
      font-size: 22px;
      color: var(--ink);
      letter-spacing: -0.02em;
    }

    .section-head p {
      margin: 0;
      font-size: 13px;
      color: var(--sub);
    }

    .chart-grid-primary {
      display: grid;
      grid-template-columns: repeat(2, minmax(300px, 1fr));
      gap: 12px;
    }

    .chart-grid-primary .chart-card:nth-child(5) {
      grid-column: span 2;
    }

    .chart-grid-diagnostic {
      display: grid;
      grid-template-columns: repeat(2, minmax(300px, 1fr));
      gap: 12px;
    }

    .chart-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: linear-gradient(180deg, var(--panel), var(--panel-tint));
      padding: 14px;
      min-height: 350px;
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 8px;
      box-shadow: var(--shadow-soft);
      transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
    }

    .chart-card.primary { border-color: rgba(31, 79, 191, 0.18); }
    .chart-card.diagnostic { border-color: rgba(47, 59, 90, 0.18); }

    .chart-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }

    .chart-tag {
      flex: 0 0 auto;
      padding: 5px 8px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: var(--chip-bg);
      color: var(--chip-ink);
      border: 1px solid var(--chip-border);
    }

    .chart-card.primary .chart-tag {
      background: var(--brand-soft);
      color: var(--brand-strong);
      border-color: rgba(31, 79, 191, 0.20);
    }

    .chart-card.diagnostic .chart-tag {
      background: rgba(96, 115, 140, 0.12);
      color: var(--chart-text);
    }

    .chart-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--ink);
      margin: 0;
      line-height: 1.35;
    }

    .chart-subtitle {
      margin: 0;
      font-size: 12px;
      color: var(--sub);
      line-height: 1.4;
    }

    .chart-surface {
      width: 100%;
      height: 272px;
      position: relative;
      border-radius: 14px;
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at top left, rgba(31, 79, 191, 0.08), transparent 30%),
        linear-gradient(180deg, var(--panel-soft), var(--panel));
      padding: 10px;
      overflow: hidden;
    }

    .chart-surface canvas {
      border-radius: 10px;
    }

    .chart-empty {
      width: 100%;
      height: 272px;
      display: grid;
      place-items: center;
      color: var(--chart-muted);
      font-size: 13px;
      border: 1px dashed var(--control-border);
      border-radius: 8px;
      background: var(--panel-soft);
    }

    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 14px;
      max-height: 264px;
      background: linear-gradient(180deg, var(--panel), var(--panel-tint));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.30);
    }

    table {
      border-collapse: collapse;
      width: 100%;
      font-size: 12px;
      background: var(--panel);
    }

    th, td {
      padding: 10px 11px;
      border-bottom: 1px solid var(--line-soft);
      text-align: left;
      vertical-align: top;
    }

    th {
      background: var(--table-head-bg);
      color: var(--chart-text);
      cursor: pointer;
      position: sticky;
      top: 0;
      z-index: 1;
      user-select: none;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    tr:hover td { background: var(--table-row-hover); }

    tbody tr:nth-child(even) td { background: var(--panel-soft); }

    td:first-child {
      font-weight: 700;
      color: var(--ink);
    }

    .risk-priority {
      display: grid;
      justify-items: start;
      gap: 8px;
    }

    .risk-score {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 56px;
      padding: 7px 10px;
      border-radius: 999px;
      font-weight: 800;
      background: var(--panel-soft);
      border: 1px solid var(--line);
      color: var(--ink);
    }

    .risk-badge {
      display: inline-flex;
      align-items: center;
      padding: 5px 8px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .risk-badge.high {
      color: var(--bad);
      background: var(--bad-soft);
    }

    .risk-badge.medium {
      color: var(--warn);
      background: var(--warn-soft);
    }

    .risk-badge.low {
      color: var(--good);
      background: var(--good-soft);
    }

    .footer-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(220px, 1fr));
      gap: 12px;
      font-size: 12px;
      color: var(--chart-text);
    }

    .foot-block {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      background: linear-gradient(180deg, var(--panel), var(--panel-tint));
      line-height: 1.45;
      transition: transform 160ms ease, box-shadow 160ms ease;
    }

    .foot-block strong {
      display: block;
      margin-bottom: 4px;
      color: var(--ink);
    }

    .foot-block:hover,
    .chart-card:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-lift);
    }

    .tooltip {
      position: fixed;
      pointer-events: none;
      background: var(--tooltip-bg);
      color: #fff;
      font-size: 12px;
      border-radius: 6px;
      padding: 6px 8px;
      z-index: 9999;
      display: none;
      max-width: 320px;
      line-height: 1.3;
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.25);
    }

    @media (max-width: 1280px) {
      .kpi-grid { grid-template-columns: repeat(4, minmax(130px, 1fr)); }
      .summary-strip { grid-template-columns: repeat(2, minmax(220px, 1fr)); }
      .filter-grid { grid-template-columns: repeat(3, minmax(160px, 1fr)); }
      .header-layout { grid-template-columns: 1fr; }
    }

    @media (max-width: 900px) {
      .chart-grid-primary,
      .chart-grid-diagnostic {
        grid-template-columns: 1fr;
      }
      .chart-grid-primary .chart-card:nth-child(5) { grid-column: span 1; }
      .kpi-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .summary-strip { grid-template-columns: 1fr; }
      .filter-grid { grid-template-columns: 1fr; }
      .footer-grid { grid-template-columns: 1fr; }
      .header-tools { width: 100%; justify-content: flex-start; }
      .filters-top { flex-direction: column; }
      h1 { font-size: 28px; }
    }

    @media print {
      :root { color-scheme: light; }
      body {
        background: #ffffff;
        color: #111827;
      }
      .container {
        width: 100%;
        margin: 0;
        gap: 12px;
      }
      .panel {
        box-shadow: none;
        border: 1px solid #d1d5db;
        page-break-inside: avoid;
      }
      .header-panel {
        background: #ffffff;
      }
      .theme-btn,
      .print-btn,
      .filter-actions,
      .meta-chip {
        display: none !important;
      }
      .filters-shell {
        border: 1px solid #d1d5db;
        background: #ffffff;
      }
      .print-coverage { display: block; }
      .chart-card,
      .kpi-card,
      .summary-card,
      .foot-block {
        box-shadow: none;
      }
      .tooltip {
        display: none !important;
      }
      .chart-surface,
      .chart-empty {
        height: 220px;
      }
      .table-wrap {
        max-height: none;
      }
      .signal-pill,
      .decision-brief {
        break-inside: avoid;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <section class="panel header-panel">
      <div class="header-top">
        <div class="header-tools">
          <button class="theme-btn" id="btn-theme" type="button" aria-label="Toggle theme"></button>
          <button class="print-btn" id="btn-print" type="button" aria-label="Print dashboard">Print</button>
          <div class="meta-chip" id="coverage-chip"></div>
        </div>
      </div>

      <div class="header-layout">
        <div class="header-copy">
          <div class="eyebrow">Executive Decision System</div>
          <div>
            <h1 id="dashboard-title">Executive Growth Quality Dashboard</h1>
            <div class="subtitle" id="dashboard-subtitle"></div>
            <div class="print-coverage" id="coverage-print"></div>
          </div>
          <div class="signal-row">
            <div class="signal-pill">Growth quality over top-line optics</div>
            <div class="signal-pill">Channel efficiency and payback focus</div>
            <div class="signal-pill">Cohort durability and margin discipline</div>
          </div>
        </div>

        <aside class="decision-brief">
          <div class="decision-title">What this view should help decide</div>
          <div class="decision-text">
            Read the KPI row first, then test where growth quality breaks across channels, cohorts, regions, and segment mix before reallocating budget or changing commercial focus.
          </div>
          <div class="rule-grid">
            <div class="rule-chip"><strong>Scale threshold</strong><span>LTV/CAC at or above 3.0</span></div>
            <div class="rule-chip"><strong>Capital discipline</strong><span>Payback at or below 12 months</span></div>
            <div class="rule-chip"><strong>Primary risk lens</strong><span>Margin deterioration, weak retention, expensive acquisition</span></div>
          </div>
        </aside>
      </div>

      <div class="filters-shell">
        <div class="filters-top">
          <div>
            <p class="filters-title">Decision Filters</p>
            <p class="filters-note">Adjust scope by period and commercial slice. KPI cards, charts, and ranked risks stay synchronized so the dashboard remains decision-consistent.</p>
          </div>
          <div class="filter-actions">
            <button class="btn" id="btn-select-all">Select All</button>
            <button class="btn" id="btn-reset">Reset</button>
          </div>
        </div>

        <div class="filter-grid">
          <div class="filter-group">
            <label for="filter-start">Start Date</label>
            <input id="filter-start" type="date" />
          </div>
          <div class="filter-group">
            <label for="filter-end">End Date</label>
            <input id="filter-end" type="date" />
          </div>
          <div class="filter-group">
            <label for="filter-segment">Segment</label>
            <select id="filter-segment" multiple></select>
          </div>
          <div class="filter-group">
            <label for="filter-region">Region</label>
            <select id="filter-region" multiple></select>
          </div>
          <div class="filter-group">
            <label for="filter-channel">Acquisition Channel</label>
            <select id="filter-channel" multiple></select>
          </div>
          <div class="filter-group">
            <label for="filter-product">Product Type</label>
            <select id="filter-product" multiple></select>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>Executive Summary Signals</h2>
        <p id="summary-context"></p>
      </div>
      <div class="summary-strip" id="summary-strip"></div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>KPI Pulse</h2>
        <p>Values are filter-aware and benchmarked against the immediately prior period of equal length.</p>
      </div>
      <div class="kpi-grid" id="kpi-grid"></div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>Primary Analysis</h2>
        <p>Read these first to decide whether growth is scaling with defensible economics.</p>
      </div>
      <div class="chart-grid-primary">
        <div class="chart-card primary">
          <div class="chart-head">
            <h3 class="chart-title">Revenue momentum across the selected window</h3>
            <span class="chart-tag">Primary</span>
          </div>
          <p class="chart-subtitle">Monthly total revenue</p>
          <div id="chart-revenue" class="chart-surface"></div>
        </div>
        <div class="chart-card primary">
          <div class="chart-head">
            <h3 class="chart-title">Contribution margin trend (quality signal)</h3>
            <span class="chart-tag">Primary</span>
          </div>
          <p class="chart-subtitle">Monthly contribution margin</p>
          <div id="chart-margin" class="chart-surface"></div>
        </div>
        <div class="chart-card primary">
          <div class="chart-head">
            <h3 class="chart-title">Revenue vs cost to expose leverage pressure</h3>
            <span class="chart-tag">Primary</span>
          </div>
          <p class="chart-subtitle">Monthly revenue and cost trend</p>
          <div id="chart-revenue-cost" class="chart-surface"></div>
        </div>
        <div class="chart-card primary">
          <div class="chart-head">
            <h3 class="chart-title">Cohort revenue retention decay</h3>
            <span class="chart-tag">Primary</span>
          </div>
          <p class="chart-subtitle">Median retention by months since signup</p>
          <div id="chart-cohort-retention" class="chart-surface"></div>
        </div>
        <div class="chart-card primary">
          <div class="chart-head">
            <h3 class="chart-title">Unit economics by channel (LTV vs CAC)</h3>
            <span class="chart-tag">Primary</span>
          </div>
          <p class="chart-subtitle">Average LTV versus CAC</p>
          <div id="chart-ltv-cac" class="chart-surface"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>Diagnostic Section</h2>
        <p>Use these cuts to localize the pockets where economics weaken first.</p>
      </div>
      <div class="chart-grid-diagnostic">
        <div class="chart-card diagnostic">
          <div class="chart-head">
            <h3 class="chart-title">Contribution margin by segment</h3>
            <span class="chart-tag">Diagnostic</span>
          </div>
          <p class="chart-subtitle">Concentration of margin dollars</p>
          <div id="chart-segment-margin" class="chart-surface"></div>
        </div>
        <div class="chart-card diagnostic">
          <div class="chart-head">
            <h3 class="chart-title">Average revenue per transaction</h3>
            <span class="chart-tag">Diagnostic</span>
          </div>
          <p class="chart-subtitle">Ticket size differences by segment</p>
          <div id="chart-arpt-segment" class="chart-surface"></div>
        </div>
        <div class="chart-card diagnostic">
          <div class="chart-head">
            <h3 class="chart-title">Customer revenue concentration</h3>
            <span class="chart-tag">Diagnostic</span>
          </div>
          <p class="chart-subtitle">Distribution of revenue by customer</p>
          <div id="chart-revenue-distribution" class="chart-surface"></div>
        </div>
        <div class="chart-card diagnostic">
          <div class="chart-head">
            <h3 class="chart-title">Regional profitability comparison</h3>
            <span class="chart-tag">Diagnostic</span>
          </div>
          <p class="chart-subtitle">Sortable table for margin quality by region</p>
          <div class="table-wrap">
            <table id="region-table"></table>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>Risk / Priority Ranking</h2>
        <p>Ranked issues translate the analysis into where management attention should go next.</p>
      </div>
      <div class="table-wrap" style="max-height:none;">
        <table id="risk-table"></table>
      </div>
    </section>

    <section class="panel">
      <div class="footer-grid">
        <div class="foot-block">
          <strong>How to read this dashboard</strong>
          Start with the KPI pulse, then test whether channel efficiency and cohort durability support the growth you are seeing. The ranking table is the action shortlist.
        </div>
        <div class="foot-block">
          <strong>Method caveat</strong>
          Results are based on synthetic data and observed in-window economics. Treat the scenario outputs as bounded policy simulations, not as forecast-grade financial guidance.
        </div>
        <div class="foot-block">
          <strong>Decision discipline</strong>
          Use the dashboard to decide where to scale, hold, or intervene. Do not treat isolated KPI improvements as sufficient if payback and retention are deteriorating.
        </div>
      </div>
    </section>
  </div>

  <div class="tooltip" id="tooltip"></div>

  <script>
    const DASHBOARD_DATA = __DATA_JSON__;
    const CUSTOMER_BY_ID = new Map((DASHBOARD_DATA.customers || []).map(c => [c.cid, c]));
    const METRIC_POLICY = DASHBOARD_DATA.meta.metric_policy || {};
    const EFF_THRESH = METRIC_POLICY.efficiency_thresholds || {
      ltv_cac_target: 3.0,
      payback_target_months: 12.0,
      ineff_ltv_cac: 1.0,
      ineff_payback_months: 24.0
    };
    const RISK_WEIGHTS = METRIC_POLICY.risk_score_weights || {
      low_efficiency_base: 90.0,
      borderline_base: 60.0,
      payback_cap_points: 40.0,
      segment_margin_floor: 0.35,
      segment_base: 60.0,
      cohort_base: 55.0
    };
    const THEME_KEY = 'exec_dashboard_theme';

    const state = {
      regionSort: { key: 'marginPct', dir: 'desc' },
      riskSort: { key: 'priorityScore', dir: 'desc' },
    };

    const tooltipEl = document.getElementById('tooltip');

    function cssVar(name, fallback) {
      const value = getComputedStyle(document.body).getPropertyValue(name).trim();
      return value || fallback;
    }

    function themeColors() {
      return {
        rev: cssVar('--rev', '#0b4f6c'),
        cost: cssVar('--cost', '#c44536'),
        margin: cssVar('--margin', '#2a9d8f'),
        accent: cssVar('--accent', '#ffb703'),
        bar: cssVar('--bar', '#264653'),
        good: cssVar('--good', '#059669'),
        bad: cssVar('--bad', '#b91c1c'),
        warn: cssVar('--warn', '#a16207'),
        grid: cssVar('--chart-grid', '#e5e7eb'),
        axis: cssVar('--chart-axis', '#94a3b8'),
        text: cssVar('--chart-text', '#334155'),
        muted: cssVar('--chart-muted', '#64748b'),
      };
    }

    function applyTheme(theme) {
      const normalized = theme === 'dark' ? 'dark' : 'light';
      document.body.setAttribute('data-theme', normalized);
      const btn = document.getElementById('btn-theme');
      btn.textContent = normalized === 'dark' ? 'Light Mode' : 'Dark Mode';
      btn.setAttribute(
        'aria-label',
        normalized === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
      );
    }

    function resolveInitialTheme() {
      const saved = window.localStorage.getItem(THEME_KEY);
      if (saved === 'dark' || saved === 'light') return saved;
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function toggleTheme() {
      const current = document.body.getAttribute('data-theme') || 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      window.localStorage.setItem(THEME_KEY, next);
      applyTheme(next);
      computeAndRender();
    }

    function fmtCurrency(value) {
      if (!Number.isFinite(value)) return 'n/a';
      const abs = Math.abs(value);
      if (abs >= 1_000_000) return '$' + (value / 1_000_000).toFixed(2) + 'M';
      if (abs >= 1_000) return '$' + (value / 1_000).toFixed(1) + 'K';
      return '$' + value.toFixed(0);
    }

    function fmtCurrencyFull(value) {
      if (!Number.isFinite(value)) return 'n/a';
      return '$' + value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    function fmtPct(value) {
      if (!Number.isFinite(value)) return 'n/a';
      return (value * 100).toFixed(1) + '%';
    }

    function fmtNum(value, digits = 2) {
      if (!Number.isFinite(value)) return 'n/a';
      return value.toLocaleString(undefined, { maximumFractionDigits: digits });
    }

    function dateToTs(dateStr) {
      return new Date(dateStr + 'T00:00:00').getTime();
    }

    function monthKey(dateStr) {
      return dateStr.slice(0, 7);
    }

    function monthLabel(monthStr) {
      const parts = monthStr.split('-');
      const d = new Date(Number(parts[0]), Number(parts[1]) - 1, 1);
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short' });
    }

    function diffMonths(startMonth, endMonth) {
      const sy = Number(startMonth.slice(0, 4));
      const sm = Number(startMonth.slice(5, 7));
      const ey = Number(endMonth.slice(0, 4));
      const em = Number(endMonth.slice(5, 7));
      return (ey - sy) * 12 + (em - sm);
    }

    function median(values) {
      if (!values.length) return NaN;
      const arr = [...values].sort((a, b) => a - b);
      const mid = Math.floor(arr.length / 2);
      return arr.length % 2 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
    }

    function quantile(values, q) {
      if (!values.length) return NaN;
      const arr = [...values].sort((a, b) => a - b);
      const pos = (arr.length - 1) * q;
      const base = Math.floor(pos);
      const rest = pos - base;
      if (arr[base + 1] !== undefined) return arr[base] + rest * (arr[base + 1] - arr[base]);
      return arr[base];
    }

    function setTooltip(target, html) {
      target.addEventListener('mouseenter', () => {
        tooltipEl.innerHTML = html;
        tooltipEl.style.display = 'block';
      });
      target.addEventListener('mousemove', (e) => {
        tooltipEl.style.left = (e.clientX + 14) + 'px';
        tooltipEl.style.top = (e.clientY + 14) + 'px';
      });
      target.addEventListener('mouseleave', () => {
        tooltipEl.style.display = 'none';
      });
    }

    function clearNode(id) {
      const el = document.getElementById(id);
      el.innerHTML = '';
      return el;
    }

    function renderNoData(id, message = 'No data for selected filters') {
      const container = clearNode(id);
      const div = document.createElement('div');
      div.className = 'chart-empty';
      div.textContent = message;
      container.appendChild(div);
    }

    function createSvg(container, height = 248) {
      const width = Math.max(340, container.clientWidth - 6);
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('width', width);
      svg.setAttribute('height', height);
      svg.style.width = '100%';
      svg.style.height = height + 'px';
      container.appendChild(svg);
      return { svg, width, height };
    }

    function addSvgLine(svg, x1, y1, x2, y2, color, width = 1, dash = null, opacity = 1) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x1); line.setAttribute('y1', y1);
      line.setAttribute('x2', x2); line.setAttribute('y2', y2);
      line.setAttribute('stroke', color);
      line.setAttribute('stroke-width', width);
      line.setAttribute('opacity', opacity);
      if (dash) line.setAttribute('stroke-dasharray', dash);
      svg.appendChild(line);
      return line;
    }

    function addSvgText(svg, x, y, text, opts = {}) {
      const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('x', x);
      t.setAttribute('y', y);
      t.setAttribute('fill', opts.color || cssVar('--chart-text', '#475569'));
      t.setAttribute('font-size', opts.size || '11');
      t.setAttribute('text-anchor', opts.anchor || 'start');
      t.setAttribute('font-weight', opts.weight || '400');
      t.textContent = text;
      svg.appendChild(t);
      return t;
    }

    function linePath(points) {
      if (!points.length) return '';
      let d = `M ${points[0].x} ${points[0].y}`;
      for (let i = 1; i < points.length; i += 1) d += ` L ${points[i].x} ${points[i].y}`;
      return d;
    }

    function renderLineChart(id, rows, series, yFormatter) {
      if (!rows.length) {
        renderNoData(id);
        return;
      }
      const palette = themeColors();

      const container = clearNode(id);
      const { svg, width, height } = createSvg(container);
      const m = { top: 14, right: 18, bottom: 36, left: 58 };
      const innerW = width - m.left - m.right;
      const innerH = height - m.top - m.bottom;

      const xVals = rows.map(r => r.x);
      const xMin = Math.min(...xVals);
      const xMax = Math.max(...xVals);

      let yMax = 0;
      series.forEach(s => {
        rows.forEach(r => { yMax = Math.max(yMax, Number(r[s.key]) || 0); });
      });
      yMax = yMax <= 0 ? 1 : yMax * 1.1;

      const sx = (x) => m.left + ((x - xMin) / Math.max(1, (xMax - xMin))) * innerW;
      const sy = (y) => m.top + innerH - (y / yMax) * innerH;

      for (let i = 0; i <= 5; i += 1) {
        const y = m.top + (i / 5) * innerH;
        addSvgLine(svg, m.left, y, width - m.right, y, palette.grid, 1);
        const value = yMax * (1 - i / 5);
        addSvgText(svg, m.left - 8, y + 4, yFormatter(value), { anchor: 'end', size: '10' });
      }

      const tickCount = Math.min(6, rows.length);
      for (let i = 0; i < tickCount; i += 1) {
        const idx = Math.round((i / Math.max(1, tickCount - 1)) * (rows.length - 1));
        const row = rows[idx];
        const x = sx(row.x);
        addSvgLine(svg, x, height - m.bottom, x, height - m.bottom + 4, palette.axis, 1);
        addSvgText(svg, x, height - m.bottom + 16, row.label, { anchor: 'middle', size: '10' });
      }

      addSvgLine(svg, m.left, m.top + innerH, width - m.right, m.top + innerH, palette.axis, 1.2);
      addSvgLine(svg, m.left, m.top, m.left, m.top + innerH, palette.axis, 1.2);

      series.forEach(s => {
        const pts = rows.map(r => ({ x: sx(r.x), y: sy(r[s.key]), raw: r[s.key], label: r.label }));
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', linePath(pts));
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', s.color);
        path.setAttribute('stroke-width', s.width || 2.3);
        svg.appendChild(path);

        pts.forEach(p => {
          const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          c.setAttribute('cx', p.x);
          c.setAttribute('cy', p.y);
          c.setAttribute('r', 3);
          c.setAttribute('fill', s.color);
          c.setAttribute('opacity', '0.95');
          svg.appendChild(c);
          setTooltip(c, `<strong>${s.label}</strong><br>${p.label}: ${yFormatter(p.raw)}`);
        });
      });

      if (series.length > 1) {
        let lx = m.left;
        const ly = m.top - 2;
        series.forEach(s => {
          addSvgLine(svg, lx, ly, lx + 18, ly, s.color, 2.4);
          addSvgText(svg, lx + 22, ly + 4, s.label, { size: '10' });
          lx += 100;
        });
      }
    }

    function renderScatterChart(id, rows) {
      if (!rows.length) {
        renderNoData(id);
        return;
      }
      const palette = themeColors();

      const container = clearNode(id);
      const { svg, width, height } = createSvg(container);
      const m = { top: 16, right: 18, bottom: 40, left: 60 };
      const innerW = width - m.left - m.right;
      const innerH = height - m.top - m.bottom;

      const xMax = Math.max(1, ...rows.map(r => r.CAC)) * 1.15;
      const yMax = Math.max(1, ...rows.map(r => r.avgLTV)) * 1.15;

      const sx = (x) => m.left + (x / xMax) * innerW;
      const sy = (y) => m.top + innerH - (y / yMax) * innerH;

      for (let i = 0; i <= 5; i += 1) {
        const x = m.left + (i / 5) * innerW;
        const v = xMax * (i / 5);
        addSvgLine(svg, x, m.top + innerH, x, m.top + innerH + 4, palette.axis, 1);
        addSvgText(svg, x, m.top + innerH + 16, fmtCurrency(v), { anchor: 'middle', size: '10' });
      }

      for (let i = 0; i <= 5; i += 1) {
        const y = m.top + (i / 5) * innerH;
        const v = yMax * (1 - i / 5);
        addSvgLine(svg, m.left - 4, y, m.left, y, palette.axis, 1);
        addSvgText(svg, m.left - 8, y + 4, fmtCurrency(v), { anchor: 'end', size: '10' });
      }

      addSvgLine(svg, m.left, m.top + innerH, width - m.right, m.top + innerH, palette.axis, 1.2);
      addSvgLine(svg, m.left, m.top, m.left, m.top + innerH, palette.axis, 1.2);

      const diagStart = { x: 0, y: 0 };
      const diagEnd = { x: Math.min(xMax, yMax), y: Math.min(xMax, yMax) };
      addSvgLine(svg, sx(diagStart.x), sy(diagStart.y), sx(diagEnd.x), sy(diagEnd.y), palette.axis, 1, '4 4', 0.9);

      rows.forEach(r => {
        const cx = sx(r.CAC);
        const cy = sy(r.avgLTV);
        const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        c.setAttribute('cx', cx);
        c.setAttribute('cy', cy);
        c.setAttribute('r', 6);
        c.setAttribute('fill', r.status === 'inefficient' ? palette.bad : (r.status === 'efficient' ? palette.good : palette.warn));
        c.setAttribute('opacity', '0.9');
        svg.appendChild(c);
        addSvgText(svg, cx + 7, cy - 8, r.channel, { size: '10', color: palette.text });
        setTooltip(c,
          `<strong>${r.channel}</strong><br>` +
          `CAC: ${fmtCurrencyFull(r.CAC)}<br>` +
          `Avg LTV: ${fmtCurrencyFull(r.avgLTV)}<br>` +
          `LTV/CAC: ${fmtNum(r.ltvToCac, 2)}<br>` +
          `Payback: ${Number.isFinite(r.payback) ? fmtNum(r.payback, 1) + ' months' : 'n/a'}`
        );
      });
    }

    function renderBarChart(id, rows, key, labelKey, yFormatter, color) {
      if (!rows.length) {
        renderNoData(id);
        return;
      }
      const palette = themeColors();

      const container = clearNode(id);
      const { svg, width, height } = createSvg(container);
      const m = { top: 16, right: 18, bottom: 44, left: 60 };
      const innerW = width - m.left - m.right;
      const innerH = height - m.top - m.bottom;

      const yMax = Math.max(1, ...rows.map(r => Number(r[key]) || 0)) * 1.15;
      const barW = innerW / rows.length * 0.65;
      const gap = innerW / rows.length;

      const sy = (y) => m.top + innerH - (y / yMax) * innerH;

      for (let i = 0; i <= 5; i += 1) {
        const y = m.top + (i / 5) * innerH;
        addSvgLine(svg, m.left, y, width - m.right, y, palette.grid, 1);
        const v = yMax * (1 - i / 5);
        addSvgText(svg, m.left - 8, y + 4, yFormatter(v), { anchor: 'end', size: '10' });
      }

      addSvgLine(svg, m.left, m.top + innerH, width - m.right, m.top + innerH, palette.axis, 1.2);
      addSvgLine(svg, m.left, m.top, m.left, m.top + innerH, palette.axis, 1.2);

      rows.forEach((r, idx) => {
        const x = m.left + idx * gap + (gap - barW) / 2;
        const y = sy(Number(r[key]) || 0);
        const h = m.top + innerH - y;

        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x);
        rect.setAttribute('y', y);
        rect.setAttribute('width', barW);
        rect.setAttribute('height', Math.max(1, h));
        rect.setAttribute('fill', color);
        rect.setAttribute('opacity', '0.9');
        svg.appendChild(rect);

        addSvgText(svg, x + barW / 2, m.top + innerH + 16, String(r[labelKey]), { anchor: 'middle', size: '10' });
        setTooltip(rect, `<strong>${r[labelKey]}</strong><br>${yFormatter(r[key])}` + (r.marginPct !== undefined ? `<br>Margin %: ${fmtPct(r.marginPct)}` : ''));
      });
    }

    function renderHistogram(id, values) {
      if (!values.length) {
        renderNoData(id);
        return;
      }
      const palette = themeColors();

      const clean = values.filter(v => Number.isFinite(v) && v > 0);
      if (!clean.length) {
        renderNoData(id, 'No positive revenue observations in selected scope');
        return;
      }

      const p99 = quantile(clean, 0.99);
      const clipped = clean.map(v => Math.min(v, p99));
      const bins = 24;
      const min = Math.min(...clipped);
      const max = Math.max(...clipped);
      const step = Math.max(1e-9, (max - min) / bins);
      const counts = new Array(bins).fill(0);
      clipped.forEach(v => {
        const idx = Math.min(bins - 1, Math.floor((v - min) / step));
        counts[idx] += 1;
      });

      const rows = counts.map((c, i) => ({
        bucketStart: min + i * step,
        bucketEnd: min + (i + 1) * step,
        count: c,
        label: i,
      }));

      const container = clearNode(id);
      const { svg, width, height } = createSvg(container);
      const m = { top: 16, right: 18, bottom: 40, left: 52 };
      const innerW = width - m.left - m.right;
      const innerH = height - m.top - m.bottom;

      const yMax = Math.max(1, ...rows.map(r => r.count)) * 1.1;
      const barW = innerW / rows.length;

      for (let i = 0; i <= 4; i += 1) {
        const y = m.top + (i / 4) * innerH;
        const v = yMax * (1 - i / 4);
        addSvgLine(svg, m.left, y, width - m.right, y, palette.grid, 1);
        addSvgText(svg, m.left - 8, y + 4, Math.round(v).toString(), { anchor: 'end', size: '10' });
      }

      addSvgLine(svg, m.left, m.top + innerH, width - m.right, m.top + innerH, palette.axis, 1.2);
      addSvgLine(svg, m.left, m.top, m.left, m.top + innerH, palette.axis, 1.2);

      rows.forEach((r, i) => {
        const h = (r.count / yMax) * innerH;
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', m.left + i * barW + 0.5);
        rect.setAttribute('y', m.top + innerH - h);
        rect.setAttribute('width', Math.max(1, barW - 1));
        rect.setAttribute('height', Math.max(1, h));
        rect.setAttribute('fill', palette.bar);
        rect.setAttribute('opacity', '0.88');
        svg.appendChild(rect);
        setTooltip(rect, `Revenue bucket: ${fmtCurrencyFull(r.bucketStart)} - ${fmtCurrencyFull(r.bucketEnd)}<br>Customers: ${r.count}`);
      });

      addSvgText(svg, m.left, height - 8, 'Distribution clipped at P99 to reduce outlier distortion', { size: '10', color: palette.muted });
    }

    function populateMultiSelect(id, values) {
      const select = document.getElementById(id);
      select.innerHTML = '';
      values.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        opt.selected = true;
        select.appendChild(opt);
      });
    }

    function getSelectedSet(id, allValues) {
      const options = Array.from(document.getElementById(id).options);
      const selected = options.filter(o => o.selected).map(o => o.value);
      if (!selected.length) return new Set(allValues);
      return new Set(selected);
    }

    function applyFilters(startDate, endDate, selected) {
      const startTs = dateToTs(startDate);
      const endTs = dateToTs(endDate);

      const filteredTx = [];
      for (const r of DASHBOARD_DATA.transactions) {
        const customer = CUSTOMER_BY_ID.get(r.cid);
        if (!customer) continue;
        const ts = dateToTs(r.d);
        if (ts < startTs || ts > endTs) continue;
        if (!selected.segments.has(customer.seg)) continue;
        if (!selected.regions.has(customer.reg)) continue;
        if (!selected.channels.has(customer.ch)) continue;
        if (!selected.products.has(r.prod)) continue;
        filteredTx.push({
          ...r,
          sd: customer.sd,
          seg: customer.seg,
          reg: customer.reg,
          ch: customer.ch,
        });
      }

      const filteredCustomers = [];
      for (const c of DASHBOARD_DATA.customers) {
        const ts = dateToTs(c.sd);
        if (ts < startTs || ts > endTs) continue;
        if (!selected.segments.has(c.seg)) continue;
        if (!selected.regions.has(c.reg)) continue;
        if (!selected.channels.has(c.ch)) continue;
        filteredCustomers.push(c);
      }

      const filteredSpend = [];
      for (const m of DASHBOARD_DATA.marketing_spend) {
        const ts = dateToTs(m.d);
        if (ts < startTs || ts > endTs) continue;
        if (!selected.channels.has(m.ch)) continue;
        filteredSpend.push(m);
      }

      return { tx: filteredTx, customers: filteredCustomers, spend: filteredSpend };
    }

    function aggregateMonthly(tx) {
      const map = new Map();
      tx.forEach(r => {
        const k = monthKey(r.d);
        if (!map.has(k)) map.set(k, { month: k, revenue: 0, cost: 0, customers: new Set() });
        const o = map.get(k);
        o.revenue += r.rev;
        o.cost += r.cost;
        o.customers.add(r.cid);
      });

      const rows = Array.from(map.values())
        .map(o => ({
          month: o.month,
          revenue: o.revenue,
          cost: o.cost,
          margin: o.revenue - o.cost,
          activeCustomers: o.customers.size,
        }))
        .sort((a, b) => a.month.localeCompare(b.month));
      return rows;
    }

    function computeSnapshot(tx, customers, spend, startDate, endDate) {
      const revenue = tx.reduce((s, r) => s + r.rev, 0);
      const cost = tx.reduce((s, r) => s + r.cost, 0);
      const margin = revenue - cost;
      const marginPct = revenue > 0 ? margin / revenue : NaN;

      const customerSet = new Set(customers.map(c => c.cid));
      const acquiredCount = customerSet.size;
      const spendTotal = spend.reduce((s, r) => s + r.spend, 0);
      const CAC = acquiredCount > 0 ? spendTotal / acquiredCount : NaN;

      let acquiredCm = 0;
      tx.forEach(r => {
        if (customerSet.has(r.cid)) acquiredCm += (r.rev - r.cost);
      });

      const avgLTV = acquiredCount > 0 ? acquiredCm / acquiredCount : NaN;
      const ltvToCac = (Number.isFinite(CAC) && CAC > 0) ? avgLTV / CAC : NaN;

      const monthStart = monthKey(startDate);
      const monthEnd = monthKey(endDate);
      const months = Math.max(1, diffMonths(monthStart, monthEnd) + 1);
      const monthlyCmPerCustomer = acquiredCount > 0 ? (acquiredCm / acquiredCount) / months : NaN;
      const payback = (Number.isFinite(monthlyCmPerCustomer) && monthlyCmPerCustomer > 0 && Number.isFinite(CAC))
        ? CAC / monthlyCmPerCustomer
        : NaN;

      return {
        revenue,
        cost,
        margin,
        marginPct,
        CAC,
        avgLTV,
        ltvToCac,
        payback,
        acquiredCount,
        spendTotal,
      };
    }

    function shiftDate(dateStr, days) {
      const d = new Date(dateStr + 'T00:00:00');
      d.setDate(d.getDate() + days);
      return d.toISOString().slice(0, 10);
    }

    function dayDiff(startDate, endDate) {
      const ms = dateToTs(endDate) - dateToTs(startDate);
      return Math.floor(ms / 86400000) + 1;
    }

    function computeUnitEconomicsByChannel(filtered, startDate, endDate, selected) {
      const channels = Array.from(selected.channels);
      const customerByChannel = new Map();
      channels.forEach(ch => customerByChannel.set(ch, new Set()));
      filtered.customers.forEach(c => {
        if (!customerByChannel.has(c.ch)) customerByChannel.set(c.ch, new Set());
        customerByChannel.get(c.ch).add(c.cid);
      });

      const spendByChannel = new Map();
      channels.forEach(ch => spendByChannel.set(ch, 0));
      filtered.spend.forEach(m => {
        spendByChannel.set(m.ch, (spendByChannel.get(m.ch) || 0) + m.spend);
      });

      const cmByChannel = new Map();
      channels.forEach(ch => cmByChannel.set(ch, 0));
      filtered.tx.forEach(t => {
        cmByChannel.set(t.ch, (cmByChannel.get(t.ch) || 0) + (t.rev - t.cost));
      });

      const months = Math.max(1, diffMonths(monthKey(startDate), monthKey(endDate)) + 1);

      const rows = channels.map(ch => {
        const cCount = (customerByChannel.get(ch) || new Set()).size;
        const spend = spendByChannel.get(ch) || 0;
        const cm = cmByChannel.get(ch) || 0;
        const CAC = cCount > 0 ? spend / cCount : NaN;
        const avgLTV = cCount > 0 ? cm / cCount : NaN;
        const ltvToCac = (Number.isFinite(CAC) && CAC > 0) ? avgLTV / CAC : NaN;
        const monthlyCmPerCustomer = cCount > 0 ? (cm / cCount) / months : NaN;
        const payback = (Number.isFinite(monthlyCmPerCustomer) && monthlyCmPerCustomer > 0 && Number.isFinite(CAC))
          ? CAC / monthlyCmPerCustomer
          : NaN;

        let status = 'borderline';
        if (!Number.isFinite(ltvToCac) || !Number.isFinite(payback)) status = 'undefined';
        else if (ltvToCac >= EFF_THRESH.ltv_cac_target && payback <= EFF_THRESH.payback_target_months) status = 'efficient';
        else if (ltvToCac < EFF_THRESH.ineff_ltv_cac || payback > EFF_THRESH.ineff_payback_months) status = 'inefficient';

        return { channel: ch, customersAcquired: cCount, totalSpend: spend, CAC, avgLTV, ltvToCac, payback, status };
      });

      return rows.sort((a, b) => (b.ltvToCac || -Infinity) - (a.ltvToCac || -Infinity));
    }

    function computeCohortRetention(tx) {
      const agg = new Map();
      tx.forEach(r => {
        const cohort = monthKey(r.sd);
        const activity = monthKey(r.d);
        const key = cohort + '|' + activity;
        if (!agg.has(key)) agg.set(key, { cohort, activity, revenue: 0, customers: new Set() });
        const o = agg.get(key);
        o.revenue += r.rev;
        o.customers.add(r.cid);
      });

      const rows = Array.from(agg.values()).map(o => ({
        cohort: o.cohort,
        activity: o.activity,
        revenue: o.revenue,
        activeCustomers: o.customers.size,
        monthsSince: diffMonths(o.cohort, o.activity),
      }));

      const baselineMap = new Map();
      rows.forEach(r => {
        if (r.monthsSince === 0) baselineMap.set(r.cohort, { revenue: r.revenue, customers: r.activeCustomers });
      });

      const byMonths = new Map();
      rows.forEach(r => {
        const base = baselineMap.get(r.cohort);
        if (!base || base.revenue <= 0 || base.customers <= 0) return;
        const revRet = r.revenue / base.revenue;
        const actRet = r.activeCustomers / base.customers;
        if (!byMonths.has(r.monthsSince)) byMonths.set(r.monthsSince, { rev: [], act: [] });
        byMonths.get(r.monthsSince).rev.push(revRet);
        byMonths.get(r.monthsSince).act.push(actRet);
      });

      const summary = Array.from(byMonths.entries())
        .map(([monthsSince, vals]) => ({
          monthsSince,
          medianRevenueRetention: median(vals.rev),
          medianActivityRetention: median(vals.act),
        }))
        .sort((a, b) => a.monthsSince - b.monthsSince);

      const decayByCohort = [];
      baselineMap.forEach((base, cohort) => {
        const m6 = rows.find(r => r.cohort === cohort && r.monthsSince === 6);
        if (m6) {
          decayByCohort.push({ cohort, month6RevenueRetention: m6.revenue / base.revenue });
        }
      });

      return { summary, decayByCohort };
    }

    function computeSegmentProfitability(tx) {
      const map = new Map();
      tx.forEach(r => {
        if (!map.has(r.seg)) map.set(r.seg, { segment: r.seg, revenue: 0, cost: 0, transactions: 0 });
        const o = map.get(r.seg);
        o.revenue += r.rev;
        o.cost += r.cost;
        o.transactions += 1;
      });
      return Array.from(map.values()).map(r => ({
        ...r,
        margin: r.revenue - r.cost,
        marginPct: r.revenue > 0 ? (r.revenue - r.cost) / r.revenue : NaN,
      })).sort((a, b) => b.margin - a.margin);
    }

    function computeRegionProfitability(tx) {
      const map = new Map();
      tx.forEach(r => {
        if (!map.has(r.reg)) map.set(r.reg, { region: r.reg, revenue: 0, cost: 0, transactions: 0 });
        const o = map.get(r.reg);
        o.revenue += r.rev;
        o.cost += r.cost;
        o.transactions += 1;
      });
      return Array.from(map.values()).map(r => ({
        ...r,
        margin: r.revenue - r.cost,
        marginPct: r.revenue > 0 ? (r.revenue - r.cost) / r.revenue : NaN,
      }));
    }

    function computeAvgRevenuePerTxBySegment(tx) {
      const map = new Map();
      tx.forEach(r => {
        if (!map.has(r.seg)) map.set(r.seg, { segment: r.seg, revenue: 0, txCount: 0 });
        const o = map.get(r.seg);
        o.revenue += r.rev;
        o.txCount += 1;
      });
      return Array.from(map.values()).map(r => ({
        segment: r.segment,
        avgRevTx: r.txCount > 0 ? r.revenue / r.txCount : NaN,
      })).sort((a, b) => b.avgRevTx - a.avgRevTx);
    }

    function computeRevenueByCustomer(tx) {
      const map = new Map();
      tx.forEach(r => {
        map.set(r.cid, (map.get(r.cid) || 0) + r.rev);
      });
      return Array.from(map.values());
    }

    function computeRiskRows(unitRows, segmentRows, cohortDecayRows) {
      const rows = [];
      const priorityBand = (score) => {
        if (score >= 95) return 'high';
        if (score >= 70) return 'medium';
        return 'low';
      };

      unitRows
        .filter(r => Number.isFinite(r.ltvToCac))
        .sort((a, b) => a.ltvToCac - b.ltvToCac)
        .slice(0, 3)
        .forEach(r => {
          const score = (r.ltvToCac < EFF_THRESH.ineff_ltv_cac ? RISK_WEIGHTS.low_efficiency_base : RISK_WEIGHTS.borderline_base)
            + (Number.isFinite(r.payback) ? Math.min(RISK_WEIGHTS.payback_cap_points, r.payback) : 15);
          rows.push({
            entity: `Channel: ${r.channel}`,
            metricValues: `LTV/CAC ${fmtNum(r.ltvToCac, 2)} | Payback ${Number.isFinite(r.payback) ? fmtNum(r.payback, 1) + 'm' : 'n/a'}`,
            riskInterpretation: r.ltvToCac < 1
              ? 'Customer value does not recover acquisition spend.'
              : 'Channel is borderline with slow capital recovery.',
            recommendedAction: r.ltvToCac < 1
              ? 'Reduce budget share and tighten bid/creative efficiency tests.'
              : 'Run CAC reduction plan before scaling spend.',
            priorityScore: score,
            priorityBand: priorityBand(score),
          });
        });

      segmentRows
        .filter(r => Number.isFinite(r.marginPct))
        .sort((a, b) => a.marginPct - b.marginPct)
        .slice(0, 2)
        .forEach(r => {
          const score = RISK_WEIGHTS.segment_base + Math.max(0, (RISK_WEIGHTS.segment_margin_floor - r.marginPct) * 100);
          rows.push({
            entity: `Segment: ${r.segment}`,
            metricValues: `Margin ${fmtPct(r.marginPct)} | Contribution ${fmtCurrency(r.margin)}`,
            riskInterpretation: 'Low margin rate weakens growth quality as segment scales.',
            recommendedAction: 'Improve packaging, pricing discipline, and service delivery cost controls.',
            priorityScore: score,
            priorityBand: priorityBand(score),
          });
        });

      cohortDecayRows
        .sort((a, b) => a.month6RevenueRetention - b.month6RevenueRetention)
        .slice(0, 2)
        .forEach(r => {
          const score = RISK_WEIGHTS.cohort_base + Math.max(0, (1 - r.month6RevenueRetention) * 100);
          rows.push({
            entity: `Cohort: ${r.cohort}`,
            metricValues: `Month-6 Revenue Retention ${fmtPct(r.month6RevenueRetention)}`,
            riskInterpretation: 'Fast cohort decay implies dependence on constant new acquisition.',
            recommendedAction: 'Strengthen early lifecycle activation and expansion motions for this cohort profile.',
            priorityScore: score,
            priorityBand: priorityBand(score),
          });
        });

      return rows.sort((a, b) => b.priorityScore - a.priorityScore);
    }

    function renderSummaryStrip(insights) {
      const wrap = document.getElementById('summary-strip');
      wrap.innerHTML = '';
      insights.forEach(item => {
        const card = document.createElement('div');
        card.className = 'summary-card';
        card.dataset.tone = item.tone || 'warn';
        card.innerHTML = `
          <div class="summary-head">
            <div class="summary-title">${item.title}</div>
            <div class="summary-badge ${item.tone || 'warn'}">${item.badge || 'Signal'}</div>
          </div>
          <div class="summary-text">${item.text}</div>
        `;
        wrap.appendChild(card);
      });
    }

    function renderKpis(cards) {
      const wrap = document.getElementById('kpi-grid');
      wrap.innerHTML = '';
      cards.forEach(card => {
        const deltaClass = !Number.isFinite(card.delta)
          ? 'kpi-delta neutral'
          : (card.delta >= 0 ? 'kpi-delta positive' : 'kpi-delta negative');
        const tone = card.tone || 'warn';
        const toneLabel = tone === 'good' ? 'Strong' : (tone === 'bad' ? 'Risk' : 'Watch');

        const el = document.createElement('div');
        el.className = 'kpi-card';
        el.dataset.tone = tone;
        el.innerHTML = `
          <div class="kpi-top">
            <div class="kpi-label-wrap">
              <div class="kpi-label">${card.label}</div>
            </div>
            <div class="kpi-state ${tone}">
              <span class="kpi-state-dot"></span>${toneLabel}
            </div>
          </div>
          <div class="kpi-value">${card.value}</div>
          <div class="${deltaClass}">${card.deltaText}</div>
          <div class="kpi-note">${card.note}</div>
        `;
        wrap.appendChild(el);
      });
    }

    function renderRegionTable(rows) {
      const table = document.getElementById('region-table');
      const sorted = [...rows].sort((a, b) => {
        const k = state.regionSort.key;
        const dir = state.regionSort.dir === 'asc' ? 1 : -1;
        return ((a[k] > b[k]) ? 1 : -1) * dir;
      });

      table.innerHTML = `
        <thead>
          <tr>
            <th data-key="region">Region</th>
            <th data-key="revenue">Revenue</th>
            <th data-key="cost">Cost</th>
            <th data-key="margin">Contribution Margin</th>
            <th data-key="marginPct">Margin %</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map(r => `
            <tr>
              <td>${r.region}</td>
              <td>${fmtCurrencyFull(r.revenue)}</td>
              <td>${fmtCurrencyFull(r.cost)}</td>
              <td>${fmtCurrencyFull(r.margin)}</td>
              <td>${fmtPct(r.marginPct)}</td>
            </tr>
          `).join('')}
        </tbody>
      `;

      table.querySelectorAll('th').forEach(th => {
        th.addEventListener('click', () => {
          const key = th.dataset.key;
          if (state.regionSort.key === key) {
            state.regionSort.dir = state.regionSort.dir === 'asc' ? 'desc' : 'asc';
          } else {
            state.regionSort.key = key;
            state.regionSort.dir = 'desc';
          }
          renderRegionTable(rows);
        });
      });
    }

    function renderRiskTable(rows) {
      const table = document.getElementById('risk-table');
      const sorted = [...rows].sort((a, b) => {
        const k = state.riskSort.key;
        const dir = state.riskSort.dir === 'asc' ? 1 : -1;
        return ((a[k] > b[k]) ? 1 : -1) * dir;
      });

      table.innerHTML = `
        <thead>
          <tr>
            <th data-key="entity">Entity</th>
            <th data-key="metricValues">Metric Values</th>
            <th data-key="riskInterpretation">Risk Interpretation</th>
            <th data-key="recommendedAction">Recommended Action</th>
            <th data-key="priorityScore">Priority Score</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map(r => `
            <tr>
              <td>${r.entity}</td>
              <td>${r.metricValues}</td>
              <td>${r.riskInterpretation}</td>
              <td>${r.recommendedAction}</td>
              <td>
                <div class="risk-priority">
                  <div class="risk-score">${fmtNum(r.priorityScore, 1)}</div>
                  <span class="risk-badge ${r.priorityBand}">${r.priorityBand}</span>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      `;

      table.querySelectorAll('th').forEach(th => {
        th.addEventListener('click', () => {
          const key = th.dataset.key;
          if (state.riskSort.key === key) {
            state.riskSort.dir = state.riskSort.dir === 'asc' ? 'desc' : 'asc';
          } else {
            state.riskSort.key = key;
            state.riskSort.dir = key === 'priorityScore' ? 'desc' : 'asc';
          }
          renderRiskTable(rows);
        });
      });
    }

    function computeAndRender() {
      const startDate = document.getElementById('filter-start').value;
      const endDate = document.getElementById('filter-end').value;

      const selected = {
        segments: getSelectedSet('filter-segment', DASHBOARD_DATA.meta.values.segments),
        regions: getSelectedSet('filter-region', DASHBOARD_DATA.meta.values.regions),
        channels: getSelectedSet('filter-channel', DASHBOARD_DATA.meta.values.acquisition_channels),
        products: getSelectedSet('filter-product', DASHBOARD_DATA.meta.values.product_types),
      };

      const current = applyFilters(startDate, endDate, selected);

      const duration = dayDiff(startDate, endDate);
      const priorEnd = shiftDate(startDate, -1);
      const priorStart = shiftDate(priorEnd, -(duration - 1));
      const prePriorEnd = shiftDate(priorStart, -1);
      const prePriorStart = shiftDate(prePriorEnd, -(duration - 1));

      const prior = applyFilters(priorStart, priorEnd, selected);
      const prePrior = applyFilters(prePriorStart, prePriorEnd, selected);

      const curSnap = computeSnapshot(current.tx, current.customers, current.spend, startDate, endDate);
      const priorSnap = computeSnapshot(prior.tx, prior.customers, prior.spend, priorStart, priorEnd);
      const prePriorSnap = computeSnapshot(prePrior.tx, prePrior.customers, prePrior.spend, prePriorStart, prePriorEnd);

      let growthRate = Number.isFinite(priorSnap.revenue) && priorSnap.revenue > 0
        ? (curSnap.revenue / priorSnap.revenue) - 1
        : NaN;
      let growthMethod = 'prior_period';
      if (!Number.isFinite(growthRate)) {
        const fallbackMonthly = aggregateMonthly(current.tx);
        if (fallbackMonthly.length >= 2) {
          const firstRevenue = fallbackMonthly[0].revenue;
          const lastRevenue = fallbackMonthly[fallbackMonthly.length - 1].revenue;
          if (Number.isFinite(firstRevenue) && Number.isFinite(lastRevenue) && firstRevenue > 0) {
            growthRate = (lastRevenue / firstRevenue) - 1;
            growthMethod = 'first_vs_last_month';
          }
        }
      }
      const priorGrowthRate = Number.isFinite(prePriorSnap.revenue) && prePriorSnap.revenue > 0
        ? (priorSnap.revenue / prePriorSnap.revenue) - 1
        : NaN;

      const delta = (cur, prev) => (Number.isFinite(prev) && prev !== 0 ? (cur / prev) - 1 : NaN);

      const kpis = [
        {
          label: 'Total Revenue',
          value: fmtCurrency(curSnap.revenue),
          delta: delta(curSnap.revenue, priorSnap.revenue),
          deltaText: Number.isFinite(delta(curSnap.revenue, priorSnap.revenue))
            ? `${delta(curSnap.revenue, priorSnap.revenue) >= 0 ? '▲' : '▼'} ${fmtPct(delta(curSnap.revenue, priorSnap.revenue))} vs prior`
            : 'No prior-period baseline',
          note: `Scope revenue from ${startDate} to ${endDate}`,
          tone: Number.isFinite(growthRate) ? (growthRate > 0 ? 'good' : 'bad') : 'warn',
        },
        {
          label: 'Contribution Margin',
          value: fmtCurrency(curSnap.margin),
          delta: delta(curSnap.margin, priorSnap.margin),
          deltaText: Number.isFinite(delta(curSnap.margin, priorSnap.margin))
            ? `${delta(curSnap.margin, priorSnap.margin) >= 0 ? '▲' : '▼'} ${fmtPct(delta(curSnap.margin, priorSnap.margin))} vs prior`
            : 'No prior-period baseline',
          note: `Margin rate ${fmtPct(curSnap.marginPct)}`,
          tone: Number.isFinite(curSnap.marginPct)
            ? (curSnap.marginPct >= 0.30 ? 'good' : (curSnap.marginPct >= 0.20 ? 'warn' : 'bad'))
            : 'warn',
        },
        {
          label: 'Growth Rate',
          value: fmtPct(growthRate),
          delta: growthMethod === 'prior_period' && Number.isFinite(growthRate) && Number.isFinite(priorGrowthRate)
            ? (growthRate - priorGrowthRate)
            : NaN,
          deltaText: growthMethod === 'prior_period' && Number.isFinite(growthRate) && Number.isFinite(priorGrowthRate)
            ? `${growthRate - priorGrowthRate >= 0 ? '▲' : '▼'} ${(Math.abs(growthRate - priorGrowthRate) * 100).toFixed(1)}pp trend shift`
            : (growthMethod === 'first_vs_last_month'
              ? 'Fallback: first vs last month in selected range'
              : 'No baseline available'),
          note: growthMethod === 'prior_period'
            ? 'Period-over-period top-line growth'
            : 'Fallback growth estimate within selected scope',
          tone: Number.isFinite(growthRate) ? (growthRate > 0.05 ? 'good' : (growthRate >= 0 ? 'warn' : 'bad')) : 'warn',
        },
        {
          label: 'CAC',
          value: fmtCurrency(curSnap.CAC),
          delta: delta(curSnap.CAC, priorSnap.CAC),
          deltaText: Number.isFinite(delta(curSnap.CAC, priorSnap.CAC))
            ? `${delta(curSnap.CAC, priorSnap.CAC) <= 0 ? '▲' : '▼'} ${fmtPct(Math.abs(delta(curSnap.CAC, priorSnap.CAC)))} efficiency move`
            : 'No prior-period baseline',
          note: `${fmtNum(curSnap.acquiredCount, 0)} acquired customers in scope`,
          tone: Number.isFinite(delta(curSnap.CAC, priorSnap.CAC))
            ? (delta(curSnap.CAC, priorSnap.CAC) <= 0 ? 'good' : 'bad')
            : 'warn',
        },
        {
          label: 'Average LTV',
          value: fmtCurrency(curSnap.avgLTV),
          delta: delta(curSnap.avgLTV, priorSnap.avgLTV),
          deltaText: Number.isFinite(delta(curSnap.avgLTV, priorSnap.avgLTV))
            ? `${delta(curSnap.avgLTV, priorSnap.avgLTV) >= 0 ? '▲' : '▼'} ${fmtPct(delta(curSnap.avgLTV, priorSnap.avgLTV))} vs prior`
            : 'No prior-period baseline',
          note: 'Observed contribution margin per acquired customer',
          tone: Number.isFinite(curSnap.avgLTV) ? (curSnap.avgLTV > curSnap.CAC ? 'good' : 'warn') : 'warn',
        },
        {
          label: 'LTV / CAC',
          value: fmtNum(curSnap.ltvToCac, 2),
          delta: delta(curSnap.ltvToCac, priorSnap.ltvToCac),
          deltaText: Number.isFinite(delta(curSnap.ltvToCac, priorSnap.ltvToCac))
            ? `${delta(curSnap.ltvToCac, priorSnap.ltvToCac) >= 0 ? '▲' : '▼'} ${fmtPct(delta(curSnap.ltvToCac, priorSnap.ltvToCac))} vs prior`
            : 'No prior-period baseline',
          note: `Higher is better; threshold target >= ${fmtNum(EFF_THRESH.ltv_cac_target, 1)}`,
          tone: Number.isFinite(curSnap.ltvToCac)
            ? (curSnap.ltvToCac >= EFF_THRESH.ltv_cac_target ? 'good' : (curSnap.ltvToCac >= EFF_THRESH.ineff_ltv_cac ? 'warn' : 'bad'))
            : 'warn',
        },
        {
          label: 'Approx. Payback',
          value: Number.isFinite(curSnap.payback) ? fmtNum(curSnap.payback, 1) + 'm' : 'n/a',
          delta: delta(curSnap.payback, priorSnap.payback),
          deltaText: Number.isFinite(delta(curSnap.payback, priorSnap.payback))
            ? `${delta(curSnap.payback, priorSnap.payback) <= 0 ? '▲' : '▼'} ${fmtPct(Math.abs(delta(curSnap.payback, priorSnap.payback)))} vs prior`
            : 'No prior-period baseline',
          note: 'Estimated CAC recovery period in months',
          tone: Number.isFinite(curSnap.payback)
            ? (curSnap.payback <= EFF_THRESH.payback_target_months ? 'good' : (curSnap.payback <= EFF_THRESH.ineff_payback_months ? 'warn' : 'bad'))
            : 'warn',
        },
      ];
      renderKpis(kpis);
      const palette = themeColors();

      const monthly = aggregateMonthly(current.tx);
      const monthlyRows = monthly.map(r => ({ x: dateToTs(r.month + '-01'), label: monthLabel(r.month), ...r }));

      renderLineChart('chart-revenue', monthlyRows, [{ key: 'revenue', label: 'Revenue', color: palette.rev }], fmtCurrency);
      renderLineChart('chart-margin', monthlyRows, [{ key: 'margin', label: 'Contribution Margin', color: palette.margin }], fmtCurrency);
      renderLineChart(
        'chart-revenue-cost',
        monthlyRows,
        [
          { key: 'revenue', label: 'Revenue', color: palette.rev },
          { key: 'cost', label: 'Cost', color: palette.cost },
        ],
        fmtCurrency
      );

      const cohort = computeCohortRetention(current.tx);
      const cohortRows = cohort.summary
        .filter(r => r.monthsSince <= 24)
        .map(r => ({ x: r.monthsSince, label: 'M' + r.monthsSince, retention: r.medianRevenueRetention || 0 }));
      renderLineChart('chart-cohort-retention', cohortRows, [{ key: 'retention', label: 'Revenue Retention', color: palette.bar }], fmtPct);

      const unitRows = computeUnitEconomicsByChannel(current, startDate, endDate, selected);
      renderScatterChart('chart-ltv-cac', unitRows);

      const segmentRows = computeSegmentProfitability(current.tx);
      renderBarChart('chart-segment-margin', segmentRows, 'margin', 'segment', fmtCurrency, palette.margin);

      const arptRows = computeAvgRevenuePerTxBySegment(current.tx);
      renderBarChart('chart-arpt-segment', arptRows, 'avgRevTx', 'segment', fmtCurrency, palette.accent);

      const customerRevenue = computeRevenueByCustomer(current.tx);
      renderHistogram('chart-revenue-distribution', customerRevenue);

      const regionRows = computeRegionProfitability(current.tx);
      renderRegionTable(regionRows.map(r => ({
        region: r.region,
        revenue: r.revenue,
        cost: r.cost,
        margin: r.margin,
        marginPct: r.marginPct,
      })));

      const risks = computeRiskRows(unitRows, segmentRows, cohort.decayByCohort);
      renderRiskTable(risks);

      const inefficient = unitRows.filter(r => r.status === 'inefficient').map(r => r.channel);
      const m6 = cohort.summary.find(r => r.monthsSince === 6);
      const m12 = cohort.summary.find(r => r.monthsSince === 12);
      const weakestSegment = [...segmentRows].sort((a, b) => a.marginPct - b.marginPct)[0];
      const revenueShareTop10 = (() => {
        const vals = [...customerRevenue].sort((a, b) => b - a);
        if (!vals.length) return NaN;
        const topN = Math.max(1, Math.floor(vals.length * 0.1));
        const total = vals.reduce((s, v) => s + v, 0);
        const top = vals.slice(0, topN).reduce((s, v) => s + v, 0);
        return total > 0 ? top / total : NaN;
      })();

      const insights = [
        {
          title: 'Growth vs Margin Quality',
          badge: Number.isFinite(curSnap.marginPct) && curSnap.marginPct >= 0.30 ? 'Healthy' : 'Watch',
          tone: Number.isFinite(curSnap.marginPct) && curSnap.marginPct >= 0.30 ? 'good' : 'warn',
          text: `Revenue changed ${fmtPct(growthRate)} vs prior period while margin rate sits at ${fmtPct(curSnap.marginPct)}. This is the first test of whether scale is creating value or just volume.`
        },
        {
          title: 'Channel Efficiency Risk',
          badge: inefficient.length ? 'Action' : 'Contained',
          tone: inefficient.length ? 'bad' : 'good',
          text: inefficient.length
            ? `Inefficient channels detected: ${inefficient.join(', ')} (LTV/CAC < ${fmtNum(EFF_THRESH.ineff_ltv_cac, 1)} or payback > ${fmtNum(EFF_THRESH.ineff_payback_months, 0)} months).`
            : 'No channels flagged as inefficient under current filters.'
        },
        {
          title: 'Cohort Durability',
          badge: m6 && Number.isFinite(m6.medianRevenueRetention) && m6.medianRevenueRetention >= 0.75 ? 'Stable' : 'Decay',
          tone: m6 && Number.isFinite(m6.medianRevenueRetention) && m6.medianRevenueRetention >= 0.75 ? 'good' : 'bad',
          text: `Median revenue retention is ${m6 ? fmtPct(m6.medianRevenueRetention) : 'n/a'} at month 6 and ${m12 ? fmtPct(m12.medianRevenueRetention) : 'n/a'} at month 12. Early decay here creates dependence on continual acquisition.`
        },
        {
          title: 'Profitability Concentration',
          badge: weakestSegment && Number.isFinite(weakestSegment.marginPct) && weakestSegment.marginPct < 0.25 ? 'Fragile' : 'Concentrated',
          tone: weakestSegment && Number.isFinite(weakestSegment.marginPct) && weakestSegment.marginPct < 0.25 ? 'bad' : 'warn',
          text: weakestSegment
            ? `${weakestSegment.segment} is the weakest-margin segment at ${fmtPct(weakestSegment.marginPct)}; top decile customers contribute ${fmtPct(revenueShareTop10)} of revenue.`
            : 'Segment profitability view unavailable for current filters.'
        },
      ];
      renderSummaryStrip(insights);

      document.getElementById('summary-context').textContent =
        `Current scope: ${fmtNum(current.tx.length, 0)} transactions | ${fmtNum(new Set(current.tx.map(r => r.cid)).size, 0)} active customers`;
    }

    function selectAllFilters() {
      ['filter-segment', 'filter-region', 'filter-channel', 'filter-product'].forEach(id => {
        Array.from(document.getElementById(id).options).forEach(o => { o.selected = true; });
      });
    }

    function resetFilters() {
      document.getElementById('filter-start').value = DASHBOARD_DATA.meta.coverage_start;
      document.getElementById('filter-end').value = DASHBOARD_DATA.meta.coverage_end;
      selectAllFilters();
      computeAndRender();
    }

    function init() {
      applyTheme(resolveInitialTheme());
      document.getElementById('dashboard-title').textContent = DASHBOARD_DATA.meta.dashboard_title;
      document.getElementById('dashboard-subtitle').textContent = DASHBOARD_DATA.meta.question;
      const coverageText = `Data coverage: ${DASHBOARD_DATA.meta.coverage_start} to ${DASHBOARD_DATA.meta.coverage_end}`;
      document.getElementById('coverage-chip').textContent = coverageText;
      document.getElementById('coverage-print').textContent = coverageText;
      populateMultiSelect('filter-segment', DASHBOARD_DATA.meta.values.segments);
      populateMultiSelect('filter-region', DASHBOARD_DATA.meta.values.regions);
      populateMultiSelect('filter-channel', DASHBOARD_DATA.meta.values.acquisition_channels);
      populateMultiSelect('filter-product', DASHBOARD_DATA.meta.values.product_types);

      document.getElementById('filter-start').value = DASHBOARD_DATA.meta.coverage_start;
      document.getElementById('filter-end').value = DASHBOARD_DATA.meta.coverage_end;
      document.getElementById('filter-start').min = DASHBOARD_DATA.meta.coverage_start;
      document.getElementById('filter-start').max = DASHBOARD_DATA.meta.coverage_end;
      document.getElementById('filter-end').min = DASHBOARD_DATA.meta.coverage_start;
      document.getElementById('filter-end').max = DASHBOARD_DATA.meta.coverage_end;

      ['filter-start', 'filter-end', 'filter-segment', 'filter-region', 'filter-channel', 'filter-product']
        .forEach(id => document.getElementById(id).addEventListener('change', () => {
          const start = document.getElementById('filter-start').value;
          const end = document.getElementById('filter-end').value;
          if (start > end) {
            document.getElementById('filter-end').value = start;
          }
          computeAndRender();
        }));

      document.getElementById('btn-select-all').addEventListener('click', () => {
        selectAllFilters();
        computeAndRender();
      });

      document.getElementById('btn-reset').addEventListener('click', resetFilters);
      document.getElementById('btn-theme').addEventListener('click', toggleTheme);
      document.getElementById('btn-print').addEventListener('click', () => window.print());

      computeAndRender();
      window.addEventListener('resize', () => computeAndRender());

      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', (event) => {
        const hasManualChoice = !!window.localStorage.getItem(THEME_KEY);
        if (!hasManualChoice) {
          applyTheme(event.matches ? 'dark' : 'light');
          computeAndRender();
        }
      });
    }

    init();
  </script>
</body>
</html>
"""

    return template.replace("__DATA_JSON__", data_json)


def run() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    customers, transactions, marketing = load_inputs()
    payload = build_embedded_payload(customers, transactions, marketing)
    html = build_dashboard_html(payload)

    out_path = DASHBOARD_DIR / "executive-revenue-unit-economics-command-center.html"
    out_path.write_text(html, encoding="utf-8")

    print("Executive dashboard assets built.")
    print(f"dashboard_html: {out_path}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
