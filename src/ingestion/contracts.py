"""Normalized ingestion contracts shared by every external source adapter."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data_contracts import (
    RAW_ALLOWED_VALUES,
    RAW_CONTRACT_VERSION,
    RAW_DATE_COLUMNS,
    RAW_NONNEGATIVE_COLUMNS,
    RAW_NUMERIC_COLUMNS,
    RAW_SCHEMAS,
)

CONTRACT_VERSION = RAW_CONTRACT_VERSION


class ContractViolation(ValueError):
    """Raised when normalized source data violates its publication contract."""


@dataclass(frozen=True)
class SourceContract:
    """Schema, grain, and domain requirements for a normalized source table."""

    name: str
    version: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    date_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    nonnegative_columns: tuple[str, ...]
    allowed_values: dict[str, frozenset[str]]

    def validate(self, frame: pd.DataFrame, *, allow_empty: bool = False) -> pd.DataFrame:
        """Return a canonical copy or raise with all blocking contract defects."""
        errors: list[str] = []
        if tuple(frame.columns) != self.columns:
            errors.append(f"columns={tuple(frame.columns)!r}; expected={self.columns!r}")
        if frame.empty and not allow_empty:
            errors.append("table is empty")
        if errors:
            raise ContractViolation(f"{self.name}@{self.version}: " + "; ".join(errors))

        normalized = frame.copy()
        if normalized.empty:
            return normalized
        for column in self.date_columns:
            normalized[column] = pd.to_datetime(normalized[column], errors="coerce", utc=True)
            invalid = int(normalized[column].isna().sum())
            if invalid:
                errors.append(f"{column} has {invalid} invalid dates")
        for column in self.numeric_columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
            invalid = int((normalized[column].isna() | ~np.isfinite(normalized[column])).sum())
            if invalid:
                errors.append(f"{column} has {invalid} invalid or non-finite values")

        nulls = int(normalized.isna().sum().sum())
        if nulls:
            errors.append(f"table has {nulls} null values")
        duplicates = int(normalized.duplicated(list(self.primary_key)).sum())
        if duplicates:
            errors.append(f"primary key {self.primary_key!r} has {duplicates} duplicates")
        for column, allowed in self.allowed_values.items():
            unexpected = sorted(set(normalized[column].astype(str)) - set(allowed))
            if unexpected:
                errors.append(f"{column} has unexpected values {unexpected!r}")

        text_columns = set(self.columns) - set(self.date_columns) - set(self.numeric_columns)
        for column in sorted(text_columns):
            blank = int(normalized[column].astype(str).str.strip().eq("").sum())
            if blank:
                errors.append(f"{column} has {blank} blank values")

        for column in self.nonnegative_columns:
            if (normalized[column] < 0).any():
                errors.append(f"{column} contains negative values")

        if errors:
            raise ContractViolation(f"{self.name}@{self.version}: " + "; ".join(errors))

        for column in self.date_columns:
            normalized[column] = normalized[column].dt.tz_convert(None).dt.normalize()
        return normalized.sort_values(list(self.primary_key), ignore_index=True)


PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "customers": ("customer_id",),
    "transactions": ("transaction_id",),
    "marketing_spend": ("date", "acquisition_channel"),
    "marketing_touchpoints": ("touchpoint_id",),
    "marketing_experiments": ("experiment_id", "customer_id"),
    "pricing_interventions": ("intervention_id",),
}


NORMALIZED_CONTRACTS: dict[str, SourceContract] = {
    table_name: SourceContract(
        name=table_name,
        version=CONTRACT_VERSION,
        columns=columns,
        primary_key=PRIMARY_KEYS[table_name],
        date_columns=RAW_DATE_COLUMNS[table_name],
        numeric_columns=RAW_NUMERIC_COLUMNS[table_name],
        nonnegative_columns=RAW_NONNEGATIVE_COLUMNS[table_name],
        allowed_values={
            column: allowed
            for (source_table, column), allowed in RAW_ALLOWED_VALUES.items()
            if source_table == table_name
        },
    )
    for table_name, columns in RAW_SCHEMAS.items()
}
