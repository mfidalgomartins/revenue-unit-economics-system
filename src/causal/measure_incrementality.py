"""Estimate experiment lift, descriptive attribution, and price elasticity."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.paths import PROJECT_ROOT, RAW_DATA_DIR

RAW_DIR = RAW_DATA_DIR
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "outputs" / "tables"
Z_95 = 1.959963984540054


def _normal_two_sided_p_value(z_score: float) -> float:
    return math.erfc(abs(z_score) / math.sqrt(2.0))


def _difference_in_means(
    treatment: np.ndarray,
    control: np.ndarray,
) -> tuple[float, float, float, float]:
    """Return difference, standard error, CI lower, and CI upper."""
    if len(treatment) < 2 or len(control) < 2:
        raise ValueError("both experiment arms require at least two observations")
    difference = float(treatment.mean() - control.mean())
    variance = float(treatment.var(ddof=1) / len(treatment) + control.var(ddof=1) / len(control))
    standard_error = math.sqrt(max(variance, 0.0))
    return (
        difference,
        standard_error,
        difference - Z_95 * standard_error,
        difference + Z_95 * standard_error,
    )


def build_incrementality_estimates(experiments: pd.DataFrame) -> pd.DataFrame:
    """Estimate randomized treatment lift with CUPED variance reduction."""
    required = {
        "experiment_id",
        "customer_id",
        "acquisition_channel",
        "assignment",
        "converted",
        "pre_period_contribution",
        "observed_contribution",
    }
    missing = sorted(required - set(experiments.columns))
    if missing:
        raise ValueError(f"marketing experiments missing columns: {missing}")

    rows: list[dict[str, object]] = []
    for experiment_id, group in experiments.groupby("experiment_id", sort=True):
        if set(group["assignment"]) != {"control", "treatment"}:
            raise ValueError(f"experiment {experiment_id!r} must contain both randomized arms")
        pre = group["pre_period_contribution"].to_numpy(dtype=float)
        outcome = group["observed_contribution"].to_numpy(dtype=float)
        pre_variance = float(np.var(pre, ddof=1))
        theta = (
            float(np.cov(outcome, pre, ddof=1)[0, 1]) / pre_variance if pre_variance > 0 else 0.0
        )
        adjusted = outcome - theta * (pre - pre.mean())
        treatment_mask = group["assignment"].eq("treatment").to_numpy()
        treated = adjusted[treatment_mask]
        control = adjusted[~treatment_mask]
        contribution_lift, contribution_se, ci_low, ci_high = _difference_in_means(treated, control)
        treated_pre = pre[treatment_mask]
        control_pre = pre[~treatment_mask]
        expected_arm_size = len(group) / 2
        srm_chi_squared = (len(treated) - expected_arm_size) ** 2 / expected_arm_size + (
            len(control) - expected_arm_size
        ) ** 2 / expected_arm_size
        srm_p_value = math.erfc(math.sqrt(srm_chi_squared / 2))
        pooled_pre_sd = math.sqrt(
            max(
                (float(treated_pre.var(ddof=1)) + float(control_pre.var(ddof=1))) / 2,
                0.0,
            )
        )
        pre_period_smd = (
            float(treated_pre.mean() - control_pre.mean()) / pooled_pre_sd
            if pooled_pre_sd > 0
            else 0.0
        )
        diagnostic_status = (
            "pass" if srm_p_value >= 0.01 and abs(pre_period_smd) <= 0.1 else "review_required"
        )
        treated_conversion = group.loc[treatment_mask, "converted"].astype(float).to_numpy()
        control_conversion = group.loc[~treatment_mask, "converted"].astype(float).to_numpy()
        conversion_lift, _conversion_se, conversion_ci_low, conversion_ci_high = (
            _difference_in_means(treated_conversion, control_conversion)
        )
        z_score = contribution_lift / contribution_se if contribution_se > 0 else math.inf
        rows.append(
            {
                "experiment_id": experiment_id,
                "acquisition_channel": str(group["acquisition_channel"].iloc[0]),
                "control_customers": len(control),
                "treatment_customers": len(treated),
                "control_conversion_rate": float(control_conversion.mean()),
                "treatment_conversion_rate": float(treated_conversion.mean()),
                "conversion_rate_lift": conversion_lift,
                "conversion_lift_ci_95_low": conversion_ci_low,
                "conversion_lift_ci_95_high": conversion_ci_high,
                "control_contribution_per_customer": float(control.mean()),
                "treatment_contribution_per_customer": float(treated.mean()),
                "incremental_contribution_per_treated_customer": contribution_lift,
                "incremental_contribution_ci_95_low": ci_low,
                "incremental_contribution_ci_95_high": ci_high,
                "incremental_contribution_total": contribution_lift * len(treated),
                "standard_error": contribution_se,
                "p_value": _normal_two_sided_p_value(z_score),
                "cuped_theta": theta,
                "sample_ratio_mismatch_p_value": srm_p_value,
                "pre_period_standardized_mean_difference": pre_period_smd,
                "diagnostic_status": diagnostic_status,
                "identification": "randomized_customer_holdout",
            }
        )
    result = pd.DataFrame(rows).sort_values("experiment_id", ignore_index=True)
    numeric = result.select_dtypes(include=["number"]).columns
    result[numeric] = result[numeric].round(6)
    return result


def _position_weights(touch_count: int) -> np.ndarray:
    if touch_count <= 0:
        raise ValueError("touch_count must be positive")
    if touch_count == 1:
        return np.array([1.0])
    if touch_count == 2:
        return np.array([0.5, 0.5])
    weights = np.full(touch_count, 0.2 / (touch_count - 2))
    weights[0] = 0.4
    weights[-1] = 0.4
    return weights


def build_multi_touch_attribution(
    touchpoints: pd.DataFrame,
    customer_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Allocate observed contribution with a fully reconciling position-based model."""
    required_touchpoints = {
        "touchpoint_id",
        "customer_id",
        "acquisition_channel",
        "touchpoint_order",
    }
    missing = sorted(required_touchpoints - set(touchpoints.columns))
    if missing:
        raise ValueError(f"marketing touchpoints missing columns: {missing}")
    required_metrics = {"customer_id", "contribution_margin"}
    missing_metrics = sorted(required_metrics - set(customer_metrics.columns))
    if missing_metrics:
        raise ValueError(f"customer metrics missing columns: {missing_metrics}")

    ordered = touchpoints.sort_values(
        ["customer_id", "touchpoint_order", "touchpoint_id"], ignore_index=True
    ).copy()
    ordered["attribution_weight"] = 0.0
    for _, positions in ordered.groupby("customer_id", sort=False).indices.items():
        ordered.loc[positions, "attribution_weight"] = _position_weights(len(positions))

    customer_contribution = customer_metrics.set_index("customer_id")["contribution_margin"]
    ordered["customer_contribution"] = ordered["customer_id"].map(customer_contribution)
    if ordered["customer_contribution"].isna().any():
        raise ValueError("touchpoints contain customers absent from customer metrics")
    ordered["attributed_contribution"] = (
        ordered["attribution_weight"] * ordered["customer_contribution"]
    )

    result = ordered.groupby("acquisition_channel", as_index=False, sort=True).agg(
        touchpoints=("touchpoint_id", "count"),
        customers_reached=("customer_id", "nunique"),
        attributed_customer_equivalents=("attribution_weight", "sum"),
        attributed_contribution=("attributed_contribution", "sum"),
    )
    total = float(result["attributed_contribution"].sum())
    result["attributed_contribution_share"] = np.where(
        total != 0,
        result["attributed_contribution"] / total,
        np.nan,
    )
    result["model"] = "position_based_40_20_40"
    result["claim_scope"] = "descriptive_allocation_not_incrementality"
    numeric = result.select_dtypes(include=["number"]).columns
    result[numeric] = result[numeric].round(6)
    if total != 0 and not result.empty:
        result.loc[result.index[-1], "attributed_contribution_share"] = round(
            1.0 - float(result.iloc[:-1]["attributed_contribution_share"].sum()), 6
        )
    return result


def _build_design_matrix(frame: pd.DataFrame, *, product_scope: str | None) -> np.ndarray:
    columns = [np.ones(len(frame)), np.log(frame["observed_price"].to_numpy(dtype=float))]
    if product_scope is None:
        product_dummies = pd.get_dummies(frame["product_type"], drop_first=True, dtype=float)
        columns.extend(product_dummies[column].to_numpy() for column in product_dummies)
    region_dummies = pd.get_dummies(frame["region"], drop_first=True, dtype=float)
    columns.extend(region_dummies[column].to_numpy() for column in region_dummies)
    week_of_year = pd.to_datetime(frame["week_start"]).dt.isocalendar().week.astype(int)
    week_dummies = pd.get_dummies(week_of_year, drop_first=True, dtype=float)
    columns.extend(week_dummies[column].to_numpy() for column in week_dummies)
    return np.column_stack(columns)


def _fit_log_demand_model(
    frame: pd.DataFrame,
    *,
    product_scope: str | None,
) -> dict[str, float | int | str]:
    positive = frame.loc[(frame["observed_price"] > 0) & (frame["units_sold"] > 0)].copy()
    if len(positive) < 30:
        raise ValueError("elasticity model requires at least 30 positive observations")
    design = _build_design_matrix(positive, product_scope=product_scope)
    outcome = np.log(positive["units_sold"].to_numpy(dtype=float))
    coefficients, _, rank, _ = np.linalg.lstsq(design, outcome, rcond=None)
    if rank != design.shape[1]:
        raise ValueError("elasticity design matrix is rank deficient")
    xtx_inverse = np.linalg.inv(np.einsum("ni,nj->ij", design, design))
    residuals = outcome - np.einsum("ij,j->i", design, coefficients)
    n_obs, n_parameters = design.shape
    leverage_meat = np.einsum("ni,n,nj->ij", design, residuals**2, design)
    hc1 = (n_obs / max(n_obs - n_parameters, 1)) * np.einsum(
        "ij,jk,kl->il", xtx_inverse, leverage_meat, xtx_inverse
    )
    hc1_standard_error = math.sqrt(max(float(hc1[1, 1]), 0.0))

    cluster_labels = pd.to_datetime(positive["week_start"]).dt.normalize().to_numpy()
    unique_clusters = np.unique(cluster_labels)
    cluster_count = len(unique_clusters)
    if cluster_count < 2:
        raise ValueError("elasticity model requires at least two week clusters")
    cluster_meat = np.zeros((n_parameters, n_parameters), dtype=float)
    for cluster in unique_clusters:
        cluster_score = np.einsum(
            "ni,n->i",
            design[cluster_labels == cluster],
            residuals[cluster_labels == cluster],
        )
        cluster_meat += np.outer(cluster_score, cluster_score)
    cluster_correction = (cluster_count / (cluster_count - 1)) * (
        (n_obs - 1) / max(n_obs - n_parameters, 1)
    )
    cluster_covariance = cluster_correction * np.einsum(
        "ij,jk,kl->il",
        xtx_inverse,
        cluster_meat,
        xtx_inverse,
    )
    clustered_standard_error = math.sqrt(max(float(cluster_covariance[1, 1]), 0.0))
    elasticity = float(coefficients[1])
    total_sum_squares = float(((outcome - outcome.mean()) ** 2).sum())
    r_squared = 1.0 - float((residuals**2).sum()) / total_sum_squares
    z_score = elasticity / clustered_standard_error if clustered_standard_error > 0 else math.inf
    return {
        "product_scope": product_scope or "All products",
        "price_elasticity": elasticity,
        "robust_standard_error": clustered_standard_error,
        "clustered_standard_error": clustered_standard_error,
        "hc1_standard_error": hc1_standard_error,
        "standard_error_method": "CR1 clustered by week_start",
        "clusters": cluster_count,
        "residual_dof": n_obs - n_parameters,
        "condition_number": float(np.linalg.cond(design)),
        "ci_95_low": elasticity - Z_95 * clustered_standard_error,
        "ci_95_high": elasticity + Z_95 * clustered_standard_error,
        "p_value": _normal_two_sided_p_value(z_score),
        "r_squared": r_squared,
        "observations": n_obs,
        "price_variants": int(positive["assignment"].nunique()),
        "identification": "randomized_weekly_price_assignment",
        "valid_range": "observed price index 0.90-1.10",
    }


def estimate_price_elasticity(pricing: pd.DataFrame) -> pd.DataFrame:
    """Estimate log-log demand elasticity with region and week fixed effects."""
    required = {
        "week_start",
        "product_type",
        "region",
        "assignment",
        "observed_price",
        "units_sold",
    }
    missing = sorted(required - set(pricing.columns))
    if missing:
        raise ValueError(f"pricing interventions missing columns: {missing}")
    if pricing["assignment"].nunique() < 3:
        raise ValueError("elasticity identification requires all three randomized price variants")

    rows = [_fit_log_demand_model(pricing, product_scope=None)]
    rows.extend(
        _fit_log_demand_model(group, product_scope=str(product))
        for product, group in pricing.groupby("product_type", sort=True)
    )
    result = pd.DataFrame(rows)
    numeric = result.select_dtypes(include=["number"]).columns
    result[numeric] = result[numeric].round(6)
    return result


def build_elasticity_pricing_recommendations(
    pricing: pd.DataFrame,
    elasticity: pd.DataFrame,
) -> pd.DataFrame:
    """Select an in-range price index using estimated product elasticity."""
    product_elasticity = elasticity.loc[elasticity["product_scope"] != "All products"].set_index(
        "product_scope"
    )
    rows: list[dict[str, object]] = []
    candidates = (0.95, 1.0, 1.05)
    for product, group in pricing.groupby("product_type", sort=True):
        estimate = float(product_elasticity.loc[product, "price_elasticity"])
        baseline = group.loc[group["assignment"] == "control"]
        baseline_price = float(baseline["observed_price"].mean())
        baseline_units = float(baseline["units_sold"].mean())
        total_units = float(group["units_sold"].sum())
        variable_cost_per_unit = (
            float((group["revenue"] - group["contribution_margin"]).sum()) / total_units
        )
        candidate_rows: list[tuple[float, float, float, float]] = []
        for price_index in candidates:
            candidate_price = baseline_price * price_index
            predicted_units = baseline_units * price_index**estimate
            predicted_contribution = predicted_units * (candidate_price - variable_cost_per_unit)
            candidate_rows.append(
                (price_index, candidate_price, predicted_units, predicted_contribution)
            )
        selected = max(candidate_rows, key=lambda row: row[3])
        baseline_contribution = next(row[3] for row in candidate_rows if row[0] == 1.0)
        rows.append(
            {
                "product_type": product,
                "estimated_elasticity": estimate,
                "tested_price_index_min": 0.90,
                "tested_price_index_max": 1.10,
                "recommended_price_index": selected[0],
                "recommended_price": selected[1],
                "predicted_weekly_units": selected[2],
                "predicted_weekly_contribution": selected[3],
                "predicted_weekly_contribution_uplift": selected[3] - baseline_contribution,
                "decision_rule": "maximize contribution within randomized test range",
            }
        )
    result = pd.DataFrame(rows)
    numeric = result.select_dtypes(include=["number"]).columns
    result[numeric] = result[numeric].round(6)
    return result


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    experiments = pd.read_csv(RAW_DIR / "marketing_experiments.csv", parse_dates=["assigned_date"])
    touchpoints = pd.read_csv(
        RAW_DIR / "marketing_touchpoints.csv", parse_dates=["touchpoint_date"]
    )
    pricing = pd.read_csv(RAW_DIR / "pricing_interventions.csv", parse_dates=["week_start"])
    customer_metrics = pd.read_csv(PROCESSED_DIR / "customer_metrics.csv")
    return experiments, touchpoints, pricing, customer_metrics


def run() -> None:
    experiments, touchpoints, pricing, customer_metrics = load_inputs()
    incrementality = build_incrementality_estimates(experiments)
    attribution = build_multi_touch_attribution(touchpoints, customer_metrics)
    elasticity = estimate_price_elasticity(pricing)
    pricing_recommendations = build_elasticity_pricing_recommendations(pricing, elasticity)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    incrementality.to_csv(TABLES_DIR / "marketing_incrementality.csv", index=False)
    attribution.to_csv(TABLES_DIR / "multi_touch_attribution.csv", index=False)
    elasticity.to_csv(TABLES_DIR / "pricing_elasticity.csv", index=False)
    pricing_recommendations.to_csv(TABLES_DIR / "pricing_recommendations.csv", index=False)
    print("Causal measurement completed.")
    print(f"experiments: {len(incrementality):,}")
    print(f"attribution channels: {len(attribution):,}")
    print(f"elasticity models: {len(elasticity):,}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
