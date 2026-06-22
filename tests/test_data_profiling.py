"""Unit tests for raw-data profiling and quality checks."""

from __future__ import annotations

import pandas as pd
from src.data_profiling.profile_raw_data import (
    detect_candidate_key,
    evaluate_data_quality,
    load_tables,
    make_issue,
    summarize_tables,
)


def test_make_issue_computes_rate_and_guards_zero_rows() -> None:
    issue = make_issue("customers", "segment", "invalid", "medium", 5, 100, "desc")
    assert issue["issue_count"] == 5
    assert issue["issue_rate"] == 0.05
    assert issue["severity"] == "medium"

    empty = make_issue("customers", "segment", "invalid", "medium", 0, 0, "desc")
    assert empty["issue_rate"] == 0.0


def test_detect_candidate_key_identifies_unique_key() -> None:
    df = pd.DataFrame({"id": [1, 2, 3], "val": [9, 9, 9]})
    key, dupes = detect_candidate_key(df, [["id"]])
    assert key == "id"
    assert dupes == 0


def test_detect_candidate_key_flags_non_unique() -> None:
    df = pd.DataFrame({"id": [1, 1, 2], "val": [9, 9, 9]})
    key, dupes = detect_candidate_key(df, [["id"]])
    assert key.endswith("(not unique)")
    assert dupes == 1


def test_quality_checks_pass_on_committed_synthetic_data() -> None:
    tables = load_tables()
    issues = evaluate_data_quality(tables)

    # Only nonzero-count issues are returned. Integrity violations (duplicate or
    # orphan keys) are guaranteed absent by construction, so they must not appear.
    integrity_checks = {
        "duplicate_customer_id",
        "duplicate_transaction_id",
        "orphan_customer_id",
    }
    assert integrity_checks.isdisjoint(set(issues["check_name"]))
    assert (issues["issue_count"] > 0).all()
    # The intentional cost-to-serve exceptions are the expected reported issue.
    assert "cost_exceeds_revenue" in set(issues["check_name"])


def test_summarize_tables_reports_one_row_per_table() -> None:
    tables = load_tables()
    summary = summarize_tables(tables)
    assert set(summary["table_name"]) == {"customers", "transactions", "marketing_spend"}
    assert (summary["row_count"] > 0).all()
