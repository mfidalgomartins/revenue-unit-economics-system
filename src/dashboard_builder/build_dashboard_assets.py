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
  <title>Growth Quality Dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap');

    :root {
      color-scheme: light;
      --bg: #ffffff;
      --surface: #ffffff;
      --surface-2: #fafafa;
      --surface-3: #f4f4f5;
      --hairline: #ececec;
      --hairline-strong: #d4d4d4;
      --ink: #0a0a0a;
      --ink-2: #262626;
      --muted: #737373;
      --subtle: #a3a3a3;
      --accent: #1d4ed8;
      --positive: #15803d;
      --negative: #b91c1c;
      --warning: #b45309;

      /* Chart palette — used by JS via getComputedStyle. Restrained: ink + muted. */
      --rev: #0a0a0a;
      --cost: #a3a3a3;
      --margin: #15803d;
      --bar: #0a0a0a;
      --good: #15803d;
      --bad: #b91c1c;
      --warn: #b45309;
      --chart-grid: #f0f0f0;
      --chart-axis: #a3a3a3;
      --chart-text: #404040;
      --chart-muted: #737373;
      --tooltip-bg: #0a0a0a;
      --tooltip-ink: #fafafa;
      --focus-ring: 0 0 0 3px rgba(29, 78, 216, 0.18);
    }

    body[data-theme="dark"] {
      color-scheme: dark;
      --bg: #0a0a0a;
      --surface: #0a0a0a;
      --surface-2: #111111;
      --surface-3: #1a1a1a;
      --hairline: #1f1f1f;
      --hairline-strong: #2a2a2a;
      --ink: #fafafa;
      --ink-2: #e5e5e5;
      --muted: #a3a3a3;
      --subtle: #525252;
      --accent: #60a5fa;
      --positive: #4ade80;
      --negative: #f87171;
      --warning: #fbbf24;

      --rev: #fafafa;
      --cost: #525252;
      --margin: #4ade80;
      --bar: #fafafa;
      --good: #4ade80;
      --bad: #f87171;
      --warn: #fbbf24;
      --chart-grid: #1f1f1f;
      --chart-axis: #525252;
      --chart-text: #d4d4d4;
      --chart-muted: #a3a3a3;
      --tooltip-bg: #fafafa;
      --tooltip-ink: #0a0a0a;
      --focus-ring: 0 0 0 3px rgba(96, 165, 250, 0.22);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-feature-settings: 'ss01', 'cv11';
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      background: var(--bg);
      color: var(--ink);
      font-size: 14px;
      line-height: 1.5;
      transition: background 160ms ease, color 160ms ease;
    }

    .skip-link {
      position: absolute;
      left: -9999px;
    }
    .skip-link:focus {
      left: 16px;
      top: 16px;
      background: var(--ink);
      color: var(--bg);
      padding: 8px 12px;
      border-radius: 4px;
      z-index: 10000;
      font-size: 12px;
    }

    .container {
      width: min(1320px, 92vw);
      margin: 0 auto;
      padding: 48px 0 80px;
    }

    /* MASTHEAD ----------------------------------------------------- */
    .masthead {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
      padding-bottom: 28px;
      border-bottom: 1px solid var(--hairline);
      margin-bottom: 28px;
    }
    .masthead-title {
      display: grid;
      gap: 6px;
      max-width: 720px;
    }
    .masthead h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 600;
      letter-spacing: -0.022em;
      color: var(--ink);
      line-height: 1.15;
    }
    .masthead .lede {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }
    .masthead-tools {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-shrink: 0;
    }
    .tool-meta {
      font-size: 12px;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.01em;
    }
    .tool-btn {
      font-family: inherit;
      background: var(--surface);
      border: 1px solid var(--hairline-strong);
      color: var(--ink-2);
      border-radius: 6px;
      padding: 7px 12px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
    }
    .tool-btn:hover {
      background: var(--surface-2);
      border-color: var(--ink-2);
      color: var(--ink);
    }
    .tool-btn:focus-visible,
    input[type="date"]:focus-visible,
    select:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
      border-color: var(--accent);
    }

    /* FILTERS ------------------------------------------------------ */
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 14px 18px;
      align-items: center;
      padding: 16px 0 28px;
      border-bottom: 1px solid var(--hairline);
      margin-bottom: 36px;
    }
    .filter-group {
      display: inline-flex;
      flex-direction: column;
      gap: 5px;
      min-width: 130px;
    }
    .filter-group label {
      font-size: 11px;
      font-weight: 500;
      color: var(--muted);
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    input[type="date"], select {
      font-family: inherit;
      background: var(--surface);
      border: 1px solid var(--hairline-strong);
      border-radius: 6px;
      padding: 7px 10px;
      font-size: 13px;
      color: var(--ink);
      transition: border-color 120ms ease;
    }
    input[type="date"]:hover, select:hover { border-color: var(--ink-2); }
    select[multiple] {
      min-height: 34px;
      max-height: 100px;
      padding: 4px 8px;
      font-size: 12px;
    }
    .filter-actions {
      margin-left: auto;
      display: flex;
      gap: 8px;
      align-items: center;
    }
    #btn-toggle-filters { display: none; }

    /* KPI BAND ----------------------------------------------------- */
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      border-top: 1px solid var(--hairline);
      border-bottom: 1px solid var(--hairline);
      margin-bottom: 36px;
    }
    .kpi-card {
      padding: 22px 22px 24px;
      border-right: 1px solid var(--hairline);
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-width: 0;
    }
    .kpi-card:last-child { border-right: none; }
    .kpi-label {
      font-size: 11px;
      color: var(--muted);
      font-weight: 500;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .kpi-value {
      font-family: 'Geist Mono', ui-monospace, 'SF Mono', Menlo, monospace;
      font-size: 30px;
      font-weight: 500;
      color: var(--ink);
      letter-spacing: -0.028em;
      line-height: 1;
      font-variant-numeric: tabular-nums;
      word-break: break-word;
    }
    .kpi-delta {
      font-family: 'Geist Mono', ui-monospace, monospace;
      font-size: 12px;
      font-weight: 500;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.01em;
    }
    .kpi-delta.positive { color: var(--positive); }
    .kpi-delta.negative { color: var(--negative); }

    /* DECISION STRIP ---------------------------------------------- */
    .decision {
      display: grid;
      grid-template-columns: 1.4fr 1fr 1fr 1fr;
      border: 1px solid var(--hairline);
      border-radius: 8px;
      background: var(--surface);
      margin-bottom: 48px;
      overflow: hidden;
    }
    .decision .cell {
      padding: 18px 22px 20px;
      border-right: 1px solid var(--hairline);
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .decision .cell:last-child { border-right: none; }
    .decision .cell.lead { background: var(--surface-2); }
    .decision .label {
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 500;
    }
    .decision .value {
      font-size: 15px;
      font-weight: 600;
      color: var(--ink);
      line-height: 1.3;
    }
    .decision .copy {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.5;
    }

    /* SECTION ------------------------------------------------------ */
    .section { margin-bottom: 56px; }
    .section-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }
    .section-head h2 {
      margin: 0;
      font-size: 12px;
      font-weight: 600;
      color: var(--ink);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .section-head .sub {
      font-size: 12px;
      color: var(--muted);
    }

    /* SUMMARY STRIP — narrative signals --------------------------- */
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      border: 1px solid var(--hairline);
      border-radius: 8px;
      background: var(--surface);
      overflow: hidden;
    }
    .summary-card {
      padding: 18px 22px 20px;
      border-right: 1px solid var(--hairline);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .summary-card:last-child { border-right: none; }
    .summary-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 10px;
    }
    .summary-title {
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 500;
    }
    .summary-badge {
      font-size: 11px;
      font-weight: 500;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    .summary-badge.good { color: var(--positive); }
    .summary-badge.warn { color: var(--warning); }
    .summary-badge.bad  { color: var(--negative); }
    .summary-text {
      font-size: 13px;
      color: var(--ink-2);
      line-height: 1.55;
    }

    /* CHARTS ------------------------------------------------------- */
    .chart-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 20px;
    }
    .chart-card {
      border: 1px solid var(--hairline);
      border-radius: 8px;
      background: var(--surface);
      padding: 20px 22px 22px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .chart-title {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
      color: var(--ink);
      letter-spacing: -0.005em;
    }
    .chart-subtitle {
      margin: 0 0 14px;
      font-size: 12px;
      color: var(--muted);
    }
    .chart-surface {
      width: 100%;
      height: 240px;
      position: relative;
    }
    .chart-surface canvas, .chart-surface svg {
      width: 100% !important;
      height: 100% !important;
    }
    .chart-insight {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--hairline);
      font-size: 12px;
      color: var(--ink-2);
      line-height: 1.55;
      min-height: 30px;
      font-variant-numeric: tabular-nums;
    }
    .chart-card.span-2 { grid-column: span 2; }
    .chart-empty {
      width: 100%;
      height: 240px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 12px;
      border: 1px dashed var(--hairline-strong);
      border-radius: 6px;
    }

    /* TABLES ------------------------------------------------------- */
    .table-wrap {
      border: 1px solid var(--hairline);
      border-radius: 8px;
      overflow: hidden;
      background: var(--surface);
    }
    .chart-card .table-wrap {
      border: none;
      border-radius: 0;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      font-size: 13px;
    }
    th, td {
      padding: 12px 16px;
      text-align: left;
      border-bottom: 1px solid var(--hairline);
    }
    th {
      background: var(--surface-2);
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      cursor: pointer;
      user-select: none;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    th:hover { color: var(--ink); }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: var(--surface-2); }
    td {
      font-variant-numeric: tabular-nums;
      color: var(--ink-2);
      vertical-align: middle;
    }
    td:first-child {
      color: var(--ink);
      font-weight: 500;
    }
    .table-wrap.expanded { max-height: none; }

    .risk-badge {
      display: inline-block;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px;
      border-radius: 4px;
      letter-spacing: 0.04em;
      font-variant-numeric: tabular-nums;
    }
    .risk-badge.high   { color: var(--negative); background: rgba(185, 28, 28, 0.08); }
    .risk-badge.medium { color: var(--warning);  background: rgba(180, 83, 9, 0.08); }
    .risk-badge.low    { color: var(--positive); background: rgba(21, 128, 61, 0.08); }
    body[data-theme="dark"] .risk-badge.high   { background: rgba(248, 113, 113, 0.14); }
    body[data-theme="dark"] .risk-badge.medium { background: rgba(251, 191, 36, 0.14); }
    body[data-theme="dark"] .risk-badge.low    { background: rgba(74, 222, 128, 0.14); }
    .risk-score {
      display: inline-block;
      min-width: 36px;
      font-family: 'Geist Mono', ui-monospace, monospace;
      font-weight: 500;
      color: var(--ink);
      font-variant-numeric: tabular-nums;
      text-align: right;
    }
    .risk-priority { display: flex; flex-direction: column; gap: 6px; }

    /* FOOTNOTE ----------------------------------------------------- */
    .footnote {
      font-size: 12px;
      color: var(--muted);
      padding-top: 28px;
      border-top: 1px solid var(--hairline);
      margin-top: 16px;
      line-height: 1.6;
    }
    .footnote code {
      font-family: 'Geist Mono', monospace;
      font-size: 11.5px;
      background: var(--surface-2);
      padding: 1px 6px;
      border-radius: 3px;
      color: var(--ink-2);
    }

    /* TOOLTIP ------------------------------------------------------ */
    .tooltip {
      position: fixed;
      pointer-events: none;
      background: var(--tooltip-bg);
      color: var(--tooltip-ink);
      font-size: 12px;
      font-family: 'Geist Mono', ui-monospace, monospace;
      border-radius: 4px;
      padding: 7px 10px;
      z-index: 9999;
      display: none;
      max-width: 320px;
      line-height: 1.45;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
      font-variant-numeric: tabular-nums;
    }

    /* RESPONSIVE --------------------------------------------------- */
    @media (max-width: 1180px) {
      .kpi-row { grid-template-columns: repeat(3, 1fr); }
      .kpi-card:nth-child(3n) { border-right: none; }
      .kpi-card:nth-child(n+4) { border-top: 1px solid var(--hairline); }
      .summary-grid { grid-template-columns: repeat(2, 1fr); }
      .summary-card:nth-child(2n) { border-right: none; }
      .summary-card:nth-child(n+3) { border-top: 1px solid var(--hairline); }
      .decision { grid-template-columns: 1fr 1fr; }
      .decision .cell:nth-child(2n) { border-right: none; }
      .decision .cell:nth-child(n+3) { border-top: 1px solid var(--hairline); }
    }
    @media (max-width: 860px) {
      .container { padding: 32px 0 64px; }
      .masthead { flex-direction: column; }
      .kpi-row { grid-template-columns: repeat(2, 1fr); }
      .kpi-card:nth-child(2n) { border-right: none; }
      .kpi-card:nth-child(n+3) { border-top: 1px solid var(--hairline); }
      .summary-grid { grid-template-columns: 1fr; }
      .summary-card { border-right: none; }
      .summary-card + .summary-card { border-top: 1px solid var(--hairline); }
      .decision { grid-template-columns: 1fr; }
      .decision .cell { border-right: none; }
      .decision .cell + .cell { border-top: 1px solid var(--hairline); }
      .chart-grid { grid-template-columns: 1fr; }
      .chart-card.span-2 { grid-column: span 1; }
      .filter-group { min-width: 0; flex: 1 1 calc(50% - 9px); }
    }

    /* PRINT -------------------------------------------------------- */
    @media print {
      :root { color-scheme: light; }
      body { background: #ffffff; color: #0a0a0a; }
      .filters, .tool-btn, .masthead-tools { display: none !important; }
      .container { width: 100%; padding: 16px; }
      .chart-card, .kpi-card, .summary-card, .table-wrap, .decision {
        box-shadow: none;
        page-break-inside: avoid;
      }
      .tooltip { display: none !important; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to dashboard</a>
  <main class="container" id="main-content">

    <header class="masthead">
      <div class="masthead-title">
        <h1 id="dashboard-title">Growth Quality Dashboard</h1>
        <p class="lede" id="dashboard-subtitle"></p>
      </div>
      <div class="masthead-tools">
        <span class="tool-meta" id="coverage-chip"></span>
        <button class="tool-btn" id="btn-theme" type="button" aria-label="Toggle theme"></button>
        <button class="tool-btn" id="btn-print" type="button">Print</button>
      </div>
    </header>

    <div class="filters" id="filters-bar">
      <div class="filter-group">
        <label for="filter-start">From</label>
        <input id="filter-start" type="date" />
      </div>
      <div class="filter-group">
        <label for="filter-end">To</label>
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
        <label for="filter-channel">Channel</label>
        <select id="filter-channel" multiple></select>
      </div>
      <div class="filter-group">
        <label for="filter-product">Product</label>
        <select id="filter-product" multiple></select>
      </div>
      <div class="filter-actions">
        <span class="tool-meta" id="filters-summary"></span>
        <button class="tool-btn" id="btn-reset" type="button">Reset</button>
        <button class="tool-btn" id="btn-select-all" type="button" style="display:none"></button>
        <button class="tool-btn" id="btn-toggle-filters" type="button" style="display:none" aria-expanded="true"></button>
      </div>
    </div>

    <div class="kpi-row" id="kpi-grid"></div>

    <div class="decision" id="decision-command" aria-live="polite"></div>

    <section class="section">
      <div class="section-head">
        <h2>Headline signals</h2>
        <span class="sub" id="summary-context"></span>
      </div>
      <div class="summary-grid" id="summary-strip"></div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Primary analysis</h2>
        <span class="sub">Revenue, margin, cost trajectory, cohort decay, channel efficiency.</span>
      </div>
      <div class="chart-grid">
        <div class="chart-card">
          <h3 class="chart-title">Is revenue momentum real?</h3>
          <p class="chart-subtitle">Monthly total revenue, filter-aware.</p>
          <div id="chart-revenue" class="chart-surface"></div>
          <div id="insight-revenue" class="chart-insight"></div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Is growth converting into margin?</h3>
          <p class="chart-subtitle">Monthly contribution margin in dollars.</p>
          <div id="chart-margin" class="chart-surface"></div>
          <div id="insight-margin" class="chart-insight"></div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Are costs scaling faster than revenue?</h3>
          <p class="chart-subtitle">Monthly revenue compared with direct cost.</p>
          <div id="chart-revenue-cost" class="chart-surface"></div>
          <div id="insight-revenue-cost" class="chart-insight"></div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">How fast do cohorts decay?</h3>
          <p class="chart-subtitle">Median revenue retention by months since signup.</p>
          <div id="chart-cohort-retention" class="chart-surface"></div>
          <div id="insight-cohort-retention" class="chart-insight"></div>
        </div>
        <div class="chart-card span-2">
          <h3 class="chart-title">Which acquisition channels deserve budget?</h3>
          <p class="chart-subtitle">Average LTV versus CAC, with efficiency thresholds.</p>
          <div id="chart-ltv-cac" class="chart-surface"></div>
          <div id="insight-ltv-cac" class="chart-insight"></div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Diagnostics</h2>
        <span class="sub">Localise where economics break first.</span>
      </div>
      <div class="chart-grid">
        <div class="chart-card">
          <h3 class="chart-title">Which segment contributes the most margin?</h3>
          <p class="chart-subtitle">Contribution margin dollars by segment.</p>
          <div id="chart-segment-margin" class="chart-surface"></div>
          <div id="insight-segment-margin" class="chart-insight"></div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Where is monetisation strongest per transaction?</h3>
          <p class="chart-subtitle">Average revenue per transaction by segment.</p>
          <div id="chart-arpt-segment" class="chart-surface"></div>
          <div id="insight-arpt-segment" class="chart-insight"></div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Is revenue concentrated in few customers?</h3>
          <p class="chart-subtitle">Customer revenue distribution, clipped at P99.</p>
          <div id="chart-revenue-distribution" class="chart-surface"></div>
          <div id="insight-revenue-distribution" class="chart-insight"></div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Which regions dilute profitability?</h3>
          <p class="chart-subtitle">Margin quality and revenue by region.</p>
          <div class="table-wrap">
            <table id="region-table"></table>
          </div>
          <div id="insight-region-table" class="chart-insight"></div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Risk ranking</h2>
        <span class="sub">Where management attention should go next.</span>
      </div>
      <div class="table-wrap expanded">
        <table id="risk-table"></table>
      </div>
    </section>

    <div class="footnote">
      Synthetic data. The pipeline demonstrates method, not market truth. Full methodology and validation in
      <code>outputs/reports/decision_brief.md</code> and <code>outputs/reports/pre_delivery_validation_report.md</code>.
    </div>
  </main>

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
    const FILTERS_COLLAPSED_KEY = 'exec_dashboard_filters_collapsed';

    const state = {
      regionSort: { key: 'marginPct', dir: 'desc' },
      riskSort: { key: 'priorityScore', dir: 'desc' },
      filtersCollapsed: false,
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

    function resolveFiltersCollapsed() {
      const saved = window.localStorage.getItem(FILTERS_COLLAPSED_KEY);
      if (saved === 'true') return true;
      if (saved === 'false') return false;
      return window.innerWidth >= 1180;
    }

    function setFiltersCollapsed(collapsed, persist = true) {
      state.filtersCollapsed = !!collapsed;
      const shell = document.querySelector('.filters-shell');
      const btn = document.getElementById('btn-toggle-filters');
      if (shell) shell.classList.toggle('compact', state.filtersCollapsed);
      if (btn) {
        btn.textContent = state.filtersCollapsed ? 'Show Filters' : 'Hide Filters';
        btn.setAttribute('aria-expanded', state.filtersCollapsed ? 'false' : 'true');
      }
      if (persist) {
        window.localStorage.setItem(FILTERS_COLLAPSED_KEY, state.filtersCollapsed ? 'true' : 'false');
      }
    }

    function summarizeSelectedValues(set, allValues, label) {
      const selected = allValues.filter(v => set.has(v));
      if (selected.length === allValues.length) return null;
      if (selected.length === 0) return `${label}: none`;
      if (selected.length === 1) return `${label}: ${selected[0]}`;
      return `${label}: ${selected.length}`;
    }

    function renderFilterSummary(startDate, endDate, selected) {
      const wrap = document.getElementById('filters-summary');
      if (!wrap) return;
      const parts = [
        summarizeSelectedValues(selected.segments, DASHBOARD_DATA.meta.values.segments, 'Segment'),
        summarizeSelectedValues(selected.regions, DASHBOARD_DATA.meta.values.regions, 'Region'),
        summarizeSelectedValues(selected.channels, DASHBOARD_DATA.meta.values.acquisition_channels, 'Channel'),
        summarizeSelectedValues(selected.products, DASHBOARD_DATA.meta.values.product_types, 'Product'),
      ].filter(Boolean);
      wrap.textContent = parts.length ? parts.join(' · ') : '';
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
      svg.setAttribute('aria-hidden', 'true');
      svg.setAttribute('focusable', 'false');
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
        // Leave unselected by default — empty selection is treated as "all".
        opt.selected = false;
        select.appendChild(opt);
      });
      select.size = Math.min(3, values.length);
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

      const avgLTV = acquiredCount > 0 ? margin / acquiredCount : NaN;
      const ltvToCac = (Number.isFinite(CAC) && CAC > 0) ? avgLTV / CAC : NaN;

      const monthStart = monthKey(startDate);
      const monthEnd = monthKey(endDate);
      const months = Math.max(1, diffMonths(monthStart, monthEnd) + 1);
      const monthlyCmPerCustomer = acquiredCount > 0 ? (margin / acquiredCount) / months : NaN;
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
            <div class="summary-badge ${item.tone || 'warn'}">${item.badge || ''}</div>
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
          ? 'kpi-delta'
          : (card.delta >= 0 ? 'kpi-delta positive' : 'kpi-delta negative');
        const el = document.createElement('div');
        el.className = 'kpi-card';
        el.dataset.tone = card.tone || 'warn';
        el.innerHTML = `
          <div class="kpi-label">${card.label}</div>
          <div class="kpi-value">${card.value}</div>
          <div class="${deltaClass}">${card.deltaText}</div>
        `;
        wrap.appendChild(el);
      });
    }

    function renderDecisionCommand(command) {
      const wrap = document.getElementById('decision-command');
      wrap.innerHTML = `
        <div class="cell lead">
          <div class="label">Decision now</div>
          <div class="value">${command.decision}</div>
          <div class="copy">${command.decisionText}</div>
        </div>
        <div class="cell">
          <div class="label">Scale</div>
          <div class="value">${command.scale}</div>
          <div class="copy">${command.scaleText}</div>
        </div>
        <div class="cell">
          <div class="label">Intervene</div>
          <div class="value">${command.intervene}</div>
          <div class="copy">${command.interveneText}</div>
        </div>
        <div class="cell">
          <div class="label">Impact</div>
          <div class="value">${command.impact}</div>
          <div class="copy">${command.impactText}</div>
        </div>
      `;
    }

    function setInsight(id, text) {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    }

    function renderRegionTable(rows) {
      const table = document.getElementById('region-table');
      if (!rows.length) {
        table.innerHTML = `
          <thead>
            <tr>
              <th>Region</th>
              <th>Revenue</th>
              <th>Cost</th>
              <th>Contribution Margin</th>
              <th>Margin %</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="5">No regional profitability view is available for the current filter scope.</td></tr>
          </tbody>
        `;
        return;
      }
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
      if (!rows.length) {
        table.innerHTML = `
          <thead>
            <tr>
              <th>Entity</th>
              <th>Metric Values</th>
              <th>Risk Interpretation</th>
              <th>Recommended Action</th>
              <th>Priority Score</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="5">No ranked risks are available for the current filter scope.</td></tr>
          </tbody>
        `;
        return;
      }
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
      renderFilterSummary(startDate, endDate, selected);

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
      const arrow = d => (d >= 0 ? '▲' : '▼');
      const deltaPct = (cur, prev) => {
        const d = delta(cur, prev);
        return Number.isFinite(d) ? `${arrow(d)} ${fmtPct(Math.abs(d))} vs prior` : '—';
      };
      const deltaPp = (cur, prev) => {
        if (!Number.isFinite(cur) || !Number.isFinite(prev)) return '—';
        const d = cur - prev;
        return `${arrow(d)} ${(Math.abs(d) * 100).toFixed(1)}pp vs prior`;
      };
      const deltaAbs = (cur, prev, fmt) => {
        if (!Number.isFinite(cur) || !Number.isFinite(prev)) return '—';
        const d = cur - prev;
        return `${arrow(-d)} ${fmt(Math.abs(d))} vs prior`;
      };

      const kpis = [
        {
          label: 'Revenue',
          value: fmtCurrency(curSnap.revenue),
          delta: delta(curSnap.revenue, priorSnap.revenue),
          deltaText: deltaPct(curSnap.revenue, priorSnap.revenue),
          tone: Number.isFinite(growthRate) ? (growthRate > 0 ? 'good' : 'bad') : 'warn',
        },
        {
          label: 'Contribution Margin',
          value: fmtCurrency(curSnap.margin),
          delta: delta(curSnap.margin, priorSnap.margin),
          deltaText: deltaPct(curSnap.margin, priorSnap.margin),
          tone: Number.isFinite(curSnap.marginPct)
            ? (curSnap.marginPct >= 0.30 ? 'good' : (curSnap.marginPct >= 0.20 ? 'warn' : 'bad'))
            : 'warn',
        },
        {
          label: 'Margin %',
          value: fmtPct(curSnap.marginPct),
          delta: Number.isFinite(curSnap.marginPct) && Number.isFinite(priorSnap.marginPct)
            ? curSnap.marginPct - priorSnap.marginPct : NaN,
          deltaText: deltaPp(curSnap.marginPct, priorSnap.marginPct),
          tone: Number.isFinite(curSnap.marginPct)
            ? (curSnap.marginPct >= 0.30 ? 'good' : (curSnap.marginPct >= 0.20 ? 'warn' : 'bad'))
            : 'warn',
        },
        {
          label: 'CAC',
          value: fmtCurrency(curSnap.CAC),
          delta: Number.isFinite(curSnap.CAC) && Number.isFinite(priorSnap.CAC)
            ? -(delta(curSnap.CAC, priorSnap.CAC)) : NaN,
          deltaText: deltaPct(curSnap.CAC, priorSnap.CAC).replace(/[▲▼]/, m => m === '▲' ? '▼' : '▲'),
          tone: Number.isFinite(delta(curSnap.CAC, priorSnap.CAC))
            ? (delta(curSnap.CAC, priorSnap.CAC) <= 0 ? 'good' : 'bad')
            : 'warn',
        },
        {
          label: 'LTV / CAC',
          value: fmtNum(curSnap.ltvToCac, 2),
          delta: delta(curSnap.ltvToCac, priorSnap.ltvToCac),
          deltaText: deltaPct(curSnap.ltvToCac, priorSnap.ltvToCac),
          tone: Number.isFinite(curSnap.ltvToCac)
            ? (curSnap.ltvToCac >= EFF_THRESH.ltv_cac_target ? 'good' : (curSnap.ltvToCac >= EFF_THRESH.ineff_ltv_cac ? 'warn' : 'bad'))
            : 'warn',
        },
        {
          label: 'Payback',
          value: Number.isFinite(curSnap.payback) ? fmtNum(curSnap.payback, 1) + 'm' : '—',
          delta: Number.isFinite(curSnap.payback) && Number.isFinite(priorSnap.payback)
            ? -(curSnap.payback - priorSnap.payback) : NaN,
          deltaText: deltaAbs(curSnap.payback, priorSnap.payback, x => x.toFixed(1) + 'm'),
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
      renderBarChart('chart-arpt-segment', arptRows, 'avgRevTx', 'segment', fmtCurrency, palette.bar);

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
      const efficient = unitRows.filter(r => r.status === 'efficient').map(r => r.channel);
      const m6 = cohort.summary.find(r => r.monthsSince === 6);
      const m12 = cohort.summary.find(r => r.monthsSince === 12);
      const weakestSegment = [...segmentRows].sort((a, b) => a.marginPct - b.marginPct)[0];
      const strongestSegment = [...segmentRows].sort((a, b) => b.margin - a.margin)[0];
      const weakestRegion = [...regionRows].sort((a, b) => a.marginPct - b.marginPct)[0];
      const bestChannel = unitRows.filter(r => Number.isFinite(r.ltvToCac))[0];
      const worstChannel = [...unitRows].filter(r => Number.isFinite(r.ltvToCac)).sort((a, b) => a.ltvToCac - b.ltvToCac)[0];
      const revenueShareTop10 = (() => {
        const vals = [...customerRevenue].sort((a, b) => b - a);
        if (!vals.length) return NaN;
        const topN = Math.max(1, Math.floor(vals.length * 0.1));
        const total = vals.reduce((s, v) => s + v, 0);
        const top = vals.slice(0, topN).reduce((s, v) => s + v, 0);
        return total > 0 ? top / total : NaN;
      })();

      const revenueTrendText = (() => {
        if (monthly.length < 2) return 'Not enough monthly observations to read momentum.';
        const first = monthly[0];
        const last = monthly[monthly.length - 1];
        const change = first.revenue > 0 ? (last.revenue / first.revenue) - 1 : NaN;
        return `Revenue moved ${fmtPct(change)} from ${monthLabel(first.month)} to ${monthLabel(last.month)}; inspect whether the same window also improves margin and payback.`;
      })();

      const marginTrendText = (() => {
        if (monthly.length < 2) return 'Not enough monthly observations to read margin direction.';
        const first = monthly[0];
        const last = monthly[monthly.length - 1];
        const firstRate = first.revenue > 0 ? first.margin / first.revenue : NaN;
        const lastRate = last.revenue > 0 ? last.margin / last.revenue : NaN;
        const shift = Number.isFinite(firstRate) && Number.isFinite(lastRate) ? (lastRate - firstRate) * 100 : NaN;
        return `Margin rate shifted ${Number.isFinite(shift) ? shift.toFixed(1) + 'pp' : 'n/a'} across the window; negative movement means growth is getting less valuable.`;
      })();

      const costLeverageText = (() => {
        if (monthly.length < 2) return 'Not enough monthly observations to compare cost leverage.';
        const first = monthly[0];
        const last = monthly[monthly.length - 1];
        const revChange = first.revenue > 0 ? (last.revenue / first.revenue) - 1 : NaN;
        const costChange = first.cost > 0 ? (last.cost / first.cost) - 1 : NaN;
        return `Revenue changed ${fmtPct(revChange)} while cost changed ${fmtPct(costChange)}; cost growing faster is the operating bottleneck to solve.`;
      })();

      const command = (() => {
        let decision = 'Hold broad scaling; reallocate by channel quality';
        let decisionText = `LTV/CAC is ${fmtNum(curSnap.ltvToCac, 2)} against a ${fmtNum(EFF_THRESH.ltv_cac_target, 1)} scale threshold and payback is ${Number.isFinite(curSnap.payback) ? fmtNum(curSnap.payback, 1) + 'm' : 'n/a'}.`;
        if (Number.isFinite(curSnap.ltvToCac) && curSnap.ltvToCac >= EFF_THRESH.ltv_cac_target && Number.isFinite(curSnap.payback) && curSnap.payback <= EFF_THRESH.payback_target_months) {
          decision = 'Scale selectively with guardrails';
          decisionText = 'Overall unit economics clear the scale rule, so the decision is where to add budget without importing weak retention or low-margin mix.';
        }
        if (inefficient.length) {
          decision = 'Cut weak acquisition before scaling winners';
          decisionText = `${inefficient.join(', ')} breach efficiency rules; reallocate spend only after CAC/payback recovery tests are defined.`;
        }
        return {
          decision,
          decisionText,
          scale: efficient.length ? efficient.join(', ') : 'No channel clears all guardrails',
          scaleText: bestChannel ? `${bestChannel.channel} leads with LTV/CAC ${fmtNum(bestChannel.ltvToCac, 2)} and payback ${fmtNum(bestChannel.payback, 1)}m.` : 'No channel-level efficiency signal is available.',
          intervene: inefficient.length ? inefficient.join(', ') : (worstChannel ? worstChannel.channel : 'No active breach'),
          interveneText: worstChannel ? `${worstChannel.channel} is weakest at LTV/CAC ${fmtNum(worstChannel.ltvToCac, 2)}; require a recovery plan before budget growth.` : 'No channel breach is visible under current filters.',
          impact: weakestSegment ? `${weakestSegment.segment} margin ${fmtPct(weakestSegment.marginPct)}` : 'No segment signal',
          impactText: weakestRegion ? `${weakestRegion.region} is the lowest-margin region at ${fmtPct(weakestRegion.marginPct)}; check pricing, support load, and delivery cost.` : 'Regional profitability is unavailable for this filter scope.',
        };
      })();
      renderDecisionCommand(command);

      setInsight('insight-revenue', revenueTrendText);
      setInsight('insight-margin', marginTrendText);
      setInsight('insight-revenue-cost', costLeverageText);
      setInsight('insight-cohort-retention', `Median revenue retention is ${m6 ? fmtPct(m6.medianRevenueRetention) : 'n/a'} at month 6 and ${m12 ? fmtPct(m12.medianRevenueRetention) : 'n/a'} at month 12; faster decay increases dependence on new acquisition.`);
      setInsight('insight-ltv-cac', bestChannel && worstChannel ? `${bestChannel.channel} is the best scaling candidate; ${worstChannel.channel} is the budget risk to cap or repair.` : 'No channel efficiency comparison is available.');
      setInsight('insight-segment-margin', strongestSegment && weakestSegment ? `${strongestSegment.segment} contributes the most margin; ${weakestSegment.segment} has the weakest margin rate at ${fmtPct(weakestSegment.marginPct)}.` : 'No segment profitability comparison is available.');
      setInsight('insight-arpt-segment', arptRows.length ? `${arptRows[0].segment} has the highest average transaction value at ${fmtCurrency(arptRows[0].avgRevTx)}; verify margin before prioritizing volume.` : 'No ticket-size comparison is available.');
      setInsight('insight-revenue-distribution', `Top-decile customers contribute ${fmtPct(revenueShareTop10)} of revenue; high concentration increases account-risk sensitivity.`);
      setInsight('insight-region-table', weakestRegion ? `${weakestRegion.region} has the lowest margin rate at ${fmtPct(weakestRegion.marginPct)}; treat it as the first regional operating review.` : 'No regional profitability comparison is available.');

      const insights = [
        {
          title: 'Growth vs Margin Quality',
          badge: Number.isFinite(curSnap.marginPct) && curSnap.marginPct >= 0.30 ? 'Healthy' : 'Watch',
          tone: Number.isFinite(curSnap.marginPct) && curSnap.marginPct >= 0.30 ? 'good' : 'warn',
          text: (() => {
            const phrase = growthMethod === 'prior_period'
              ? `Revenue changed ${fmtPct(growthRate)} vs the prior period of equal length`
              : (Number.isFinite(growthRate)
                  ? `Revenue grew ${fmtPct(growthRate)} from the first to the last month in scope`
                  : `Revenue trend cannot be measured for this scope`);
            return `${phrase}; margin rate is ${fmtPct(curSnap.marginPct)}. This is the first test of whether scale is creating value or just volume.`;
          })()
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

    function clearAllFilters() {
      ['filter-segment', 'filter-region', 'filter-channel', 'filter-product'].forEach(id => {
        Array.from(document.getElementById(id).options).forEach(o => { o.selected = false; });
      });
    }

    function resetFilters() {
      document.getElementById('filter-start').value = DASHBOARD_DATA.meta.coverage_start;
      document.getElementById('filter-end').value = DASHBOARD_DATA.meta.coverage_end;
      clearAllFilters();
      computeAndRender();
    }

    function init() {
      applyTheme(resolveInitialTheme());
      document.getElementById('dashboard-title').textContent = DASHBOARD_DATA.meta.dashboard_title;
      document.getElementById('dashboard-subtitle').textContent = DASHBOARD_DATA.meta.question;
      const coverageText = `Data coverage: ${DASHBOARD_DATA.meta.coverage_start} to ${DASHBOARD_DATA.meta.coverage_end}`;
      document.getElementById('coverage-chip').textContent = coverageText;
      const cp = document.getElementById('coverage-print');
      if (cp) cp.textContent = coverageText;
      populateMultiSelect('filter-segment', DASHBOARD_DATA.meta.values.segments);
      populateMultiSelect('filter-region', DASHBOARD_DATA.meta.values.regions);
      populateMultiSelect('filter-channel', DASHBOARD_DATA.meta.values.acquisition_channels);
      populateMultiSelect('filter-product', DASHBOARD_DATA.meta.values.product_types);
      setFiltersCollapsed(resolveFiltersCollapsed(), false);

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
      document.getElementById('btn-toggle-filters').addEventListener('click', () => {
        setFiltersCollapsed(!state.filtersCollapsed);
      });
      document.getElementById('btn-theme').addEventListener('click', toggleTheme);
      document.getElementById('btn-print').addEventListener('click', () => window.print());

      computeAndRender();
      let resizeTimer = null;
      window.addEventListener('resize', () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => computeAndRender(), 120);
      });

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

    out_path = DASHBOARD_DIR / "growth-quality-dashboard.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"Dashboard written: {out_path}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
