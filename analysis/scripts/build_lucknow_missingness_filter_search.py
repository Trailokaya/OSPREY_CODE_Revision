from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_three_city_comparative_analysis import (  # noqa: E402
    PRIMARY_NETWORKS,
    REPO_ROOT,
    daily_sensor_availability,
    daily_sensor_means,
    haversine_km,
    read_locations,
    read_pm_matrix,
    retained_sensor_ids,
)


OUTPUT_DIR = REPO_ROOT / "analysis/results/three_city_comparative_analysis"
MIN_SENSORS_RETAINED = 30
REMOVE_K_VALUES = (1, 2, 3, 4, 5, 7, 10, 12, 15, 20, 25, 30, 35, 40)
PRESENCE_THRESHOLDS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90)
MAX_GAP_THRESHOLDS = (30, 45, 60, 90, 120, 150, 180, 240)
TARGETED_RHO_THRESHOLDS = (0.10, 0.20, 0.30, 0.40)


@dataclass(frozen=True)
class CandidateFilter:
    filter_name: str
    filter_family: str
    description: str
    kept_sensors: tuple[str, ...]
    removed_sensors: tuple[str, ...]
    targeted_to_outcome: bool


def pearson_r(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    return float(frame["x"].corr(frame["y"]))


def spearman_rho(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    return pearson_r(frame["x"].rank(method="average"), frame["y"].rank(method="average"))


def max_consecutive_true(values: pd.Series) -> int:
    longest = 0
    current = 0
    for value in values.astype(bool):
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def high_missing_episodes(series: pd.Series, threshold: float = 0.25) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    start = None
    previous = None
    for timestamp, value in series.sort_index().items():
        if pd.notna(value) and value >= threshold:
            if start is None:
                start = timestamp
            previous = timestamp
        elif start is not None and previous is not None:
            window = series.loc[start:previous]
            records.append(
                {
                    "start_date": start.date().isoformat(),
                    "end_date": previous.date().isoformat(),
                    "duration_days": int(len(window)),
                    "mean_missing_pct": float(window.mean() * 100),
                    "max_missing_pct": float(window.max() * 100),
                }
            )
            start = None
            previous = None
    if start is not None and previous is not None:
        window = series.loc[start:previous]
        records.append(
            {
                "start_date": start.date().isoformat(),
                "end_date": previous.date().isoformat(),
                "duration_days": int(len(window)),
                "mean_missing_pct": float(window.mean() * 100),
                "max_missing_pct": float(window.max() * 100),
            }
        )
    if not records:
        return pd.DataFrame(columns=["start_date", "end_date", "duration_days", "mean_missing_pct", "max_missing_pct"])
    return pd.DataFrame(records).sort_values(["duration_days", "max_missing_pct"], ascending=[False, False])


def knn_weights(locations: pd.DataFrame, k: int = 5) -> np.ndarray:
    coords = locations[["Latitude", "Longitude"]].to_numpy(dtype=float)
    n_sensors = len(coords)
    weights = np.zeros((n_sensors, n_sensors), dtype=float)
    if n_sensors < 3:
        return weights
    effective_k = min(k, n_sensors - 1)
    for index in range(n_sensors):
        distances = haversine_km(coords[index, 0], coords[index, 1], coords[:, 0], coords[:, 1])
        distances[index] = np.inf
        nearest = np.argsort(distances)[:effective_k]
        weights[index, nearest] = 1.0
    return weights


def morans_i(values: pd.Series, locations: pd.DataFrame) -> float:
    values = values.astype(float)
    locations = locations.set_index("Sensor_ID").loc[values.index].reset_index()
    weights = knn_weights(locations, k=5)
    valid = np.isfinite(values.to_numpy(dtype=float))
    x = values.to_numpy(dtype=float)[valid]
    weights = weights[np.ix_(valid, valid)]
    if len(x) < 3:
        return float("nan")
    centered = x - x.mean()
    denominator = float(np.sum(centered**2))
    weight_sum = float(weights.sum())
    if denominator == 0 or weight_sum == 0:
        return float("nan")
    return float(len(x) / weight_sum * (centered @ weights @ centered) / denominator)


def zscore(series: pd.Series) -> pd.Series:
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.nan, index=series.index)
    return (series - series.mean()) / std


def multivariable_coefficients(daily_metrics: pd.DataFrame) -> dict[str, float]:
    model = daily_metrics[
        ["daily_missing_fraction", "reference_mean_ugm3", "spatial_cv", "time_index_days"]
    ].replace([np.inf, -np.inf], np.nan).dropna()
    if len(model) < 20:
        return {
            "partial_time_coef_pct_per_1sd": np.nan,
            "partial_spatial_cv_coef_pct_per_1sd": np.nan,
            "partial_pm_coef_pct_per_1sd": np.nan,
            "partial_model_r_squared": np.nan,
        }
    frame = pd.DataFrame(
        {
            "missing_pct": model["daily_missing_fraction"] * 100,
            "pm": zscore(model["reference_mean_ugm3"]),
            "spatial_cv": zscore(model["spatial_cv"]),
            "time": zscore(model["time_index_days"]),
        }
    ).dropna()
    y = frame["missing_pct"].to_numpy(dtype=float)
    design = np.column_stack(
        [
            np.ones(len(frame)),
            frame["pm"].to_numpy(dtype=float),
            frame["spatial_cv"].to_numpy(dtype=float),
            frame["time"].to_numpy(dtype=float),
        ]
    )
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    predicted = design @ beta
    total = float(np.sum((y - y.mean()) ** 2))
    residual = float(np.sum((y - predicted) ** 2))
    return {
        "partial_pm_coef_pct_per_1sd": float(beta[1]),
        "partial_spatial_cv_coef_pct_per_1sd": float(beta[2]),
        "partial_time_coef_pct_per_1sd": float(beta[3]),
        "partial_model_r_squared": float(1 - residual / total) if total else np.nan,
    }


def build_ranked_sensor_scores(
    sensor_ids: list[str],
    daily: pd.DataFrame,
    availability: pd.DataFrame,
    pm: pd.DataFrame,
    baseline_spatial_cv: pd.Series,
    baseline_dates: pd.Series,
) -> dict[str, pd.Series]:
    record_missing = 1 - pm[sensor_ids].notna().mean(axis=0)
    daily_missing = 1 - daily[sensor_ids].notna().mean(axis=0)
    longest_gap = daily[sensor_ids].isna().apply(max_consecutive_true)
    late_period = (daily.index >= pd.Timestamp("2023-01-25")) & (daily.index <= pd.Timestamp("2023-03-31"))
    late_missing = 1 - availability.loc[late_period, sensor_ids].mean(axis=0)
    high_cv_days = baseline_spatial_cv >= baseline_spatial_cv.quantile(0.75)
    high_cv_missing = 1 - availability.loc[high_cv_days, sensor_ids].mean(axis=0)
    sensor_temporal_rho = pd.Series(
        {
            sensor_id: spearman_rho(baseline_dates, 1 - availability[sensor_id])
            for sensor_id in sensor_ids
        }
    )
    sensor_spatial_cv_rho = pd.Series(
        {
            sensor_id: spearman_rho(baseline_spatial_cv, 1 - availability[sensor_id])
            for sensor_id in sensor_ids
        }
    )
    return {
        "record_missing": record_missing,
        "daily_missing": daily_missing,
        "longest_gap": longest_gap,
        "late_period_missing": late_missing,
        "high_spatial_cv_missing": high_cv_missing,
        "sensor_temporal_rho": sensor_temporal_rho.fillna(-np.inf),
        "sensor_spatial_cv_rho": sensor_spatial_cv_rho.fillna(-np.inf),
    }


def make_candidate(
    name: str,
    family: str,
    description: str,
    all_sensors: list[str],
    removed: list[str],
    targeted: bool,
) -> CandidateFilter | None:
    removed_set = set(removed)
    kept = tuple(sensor_id for sensor_id in all_sensors if sensor_id not in removed_set)
    if len(kept) < MIN_SENSORS_RETAINED:
        return None
    return CandidateFilter(
        filter_name=name,
        filter_family=family,
        description=description,
        kept_sensors=kept,
        removed_sensors=tuple(sensor_id for sensor_id in all_sensors if sensor_id in removed_set),
        targeted_to_outcome=targeted,
    )


def build_candidates(
    sensor_ids: list[str],
    record_uptime: pd.Series,
    daily_presence: pd.Series,
    longest_gap: pd.Series,
    scores: dict[str, pd.Series],
) -> list[CandidateFilter]:
    candidates: list[CandidateFilter] = [
        CandidateFilter(
            filter_name="baseline_all_sensors",
            filter_family="baseline",
            description="All retained Lucknow sensors.",
            kept_sensors=tuple(sensor_ids),
            removed_sensors=tuple(),
            targeted_to_outcome=False,
        )
    ]

    ranking_specs = [
        ("remove_worst_record_missing", "record_missing", False),
        ("remove_worst_daily_missing", "daily_missing", False),
        ("remove_longest_gap", "longest_gap", False),
        ("remove_late_period_missing", "late_period_missing", True),
        ("remove_high_spatial_cv_missing", "high_spatial_cv_missing", True),
        ("remove_sensor_temporal_rho", "sensor_temporal_rho", True),
        ("remove_sensor_spatial_cv_rho", "sensor_spatial_cv_rho", True),
    ]
    for family, score_name, targeted in ranking_specs:
        ranked = scores[score_name].sort_values(ascending=False).index.astype(str).tolist()
        for remove_k in REMOVE_K_VALUES:
            candidate = make_candidate(
                f"{family}_k{remove_k}",
                family,
                f"Remove top {remove_k} sensors ranked by {score_name}.",
                sensor_ids,
                ranked[:remove_k],
                targeted,
            )
            if candidate:
                candidates.append(candidate)

    for threshold in PRESENCE_THRESHOLDS:
        kept_record = record_uptime[record_uptime >= threshold].index.astype(str).tolist()
        candidate = make_candidate(
            f"record_presence_ge_{int(threshold * 100)}pct",
            "record_presence_threshold",
            f"Keep sensors with hourly-record presence >= {threshold:.0%}.",
            sensor_ids,
            [sensor_id for sensor_id in sensor_ids if sensor_id not in kept_record],
            False,
        )
        if candidate:
            candidates.append(candidate)

        kept_daily = daily_presence[daily_presence >= threshold].index.astype(str).tolist()
        candidate = make_candidate(
            f"daily_presence_ge_{int(threshold * 100)}pct",
            "daily_presence_threshold",
            f"Keep sensors with daily presence >= {threshold:.0%}.",
            sensor_ids,
            [sensor_id for sensor_id in sensor_ids if sensor_id not in kept_daily],
            False,
        )
        if candidate:
            candidates.append(candidate)

    for threshold in MAX_GAP_THRESHOLDS:
        kept_gap = longest_gap[longest_gap <= threshold].index.astype(str).tolist()
        candidate = make_candidate(
            f"max_gap_le_{threshold}d",
            "max_gap_threshold",
            f"Keep sensors with longest daily gap <= {threshold} days.",
            sensor_ids,
            [sensor_id for sensor_id in sensor_ids if sensor_id not in kept_gap],
            False,
        )
        if candidate:
            candidates.append(candidate)

    for presence_threshold in (0.50, 0.60, 0.75):
        for gap_threshold in (30, 60, 90, 120):
            kept = set(record_uptime[record_uptime >= presence_threshold].index.astype(str)) & set(
                longest_gap[longest_gap <= gap_threshold].index.astype(str)
            )
            candidate = make_candidate(
                f"record_ge_{int(presence_threshold * 100)}pct_gap_le_{gap_threshold}d",
                "record_presence_plus_gap",
                f"Keep sensors with record presence >= {presence_threshold:.0%} and gap <= {gap_threshold} days.",
                sensor_ids,
                [sensor_id for sensor_id in sensor_ids if sensor_id not in kept],
                False,
            )
            if candidate:
                candidates.append(candidate)

            kept = set(daily_presence[daily_presence >= presence_threshold].index.astype(str)) & set(
                longest_gap[longest_gap <= gap_threshold].index.astype(str)
            )
            candidate = make_candidate(
                f"daily_ge_{int(presence_threshold * 100)}pct_gap_le_{gap_threshold}d",
                "daily_presence_plus_gap",
                f"Keep sensors with daily presence >= {presence_threshold:.0%} and gap <= {gap_threshold} days.",
                sensor_ids,
                [sensor_id for sensor_id in sensor_ids if sensor_id not in kept],
                False,
            )
            if candidate:
                candidates.append(candidate)

    temporal_ranked = scores["sensor_temporal_rho"].sort_values(ascending=False).index.astype(str).tolist()
    spatial_ranked = scores["sensor_spatial_cv_rho"].sort_values(ascending=False).index.astype(str).tolist()
    late_ranked = scores["late_period_missing"].sort_values(ascending=False).index.astype(str).tolist()
    high_cv_ranked = scores["high_spatial_cv_missing"].sort_values(ascending=False).index.astype(str).tolist()
    for remove_k in (3, 5, 7, 10, 15, 20):
        candidate = make_candidate(
            f"remove_temporal_and_spatial_rho_k{remove_k}",
            "targeted_temporal_spatial_rho_union",
            f"Remove union of top {remove_k} sensors by temporal rho and top {remove_k} by spatial-CV rho.",
            sensor_ids,
            sorted(set(temporal_ranked[:remove_k]) | set(spatial_ranked[:remove_k])),
            True,
        )
        if candidate:
            candidates.append(candidate)
        candidate = make_candidate(
            f"remove_late_and_high_cv_missing_k{remove_k}",
            "targeted_late_high_cv_union",
            f"Remove union of top {remove_k} sensors by late-period missingness and high-CV-day missingness.",
            sensor_ids,
            sorted(set(late_ranked[:remove_k]) | set(high_cv_ranked[:remove_k])),
            True,
        )
        if candidate:
            candidates.append(candidate)

    for threshold in TARGETED_RHO_THRESHOLDS:
        remove_temporal = scores["sensor_temporal_rho"][scores["sensor_temporal_rho"] >= threshold].index.astype(str).tolist()
        candidate = make_candidate(
            f"remove_sensor_temporal_rho_ge_{int(threshold * 100)}",
            "targeted_temporal_rho_threshold",
            f"Remove sensors whose missingness has temporal Spearman rho >= {threshold:.2f}.",
            sensor_ids,
            remove_temporal,
            True,
        )
        if candidate:
            candidates.append(candidate)
        remove_spatial = scores["sensor_spatial_cv_rho"][scores["sensor_spatial_cv_rho"] >= threshold].index.astype(str).tolist()
        candidate = make_candidate(
            f"remove_sensor_spatial_cv_rho_ge_{int(threshold * 100)}",
            "targeted_spatial_cv_rho_threshold",
            f"Remove sensors whose missingness has spatial-CV Spearman rho >= {threshold:.2f}.",
            sensor_ids,
            remove_spatial,
            True,
        )
        if candidate:
            candidates.append(candidate)

    seen_names = set()
    unique_candidates = []
    for candidate in candidates:
        if candidate.filter_name not in seen_names:
            seen_names.add(candidate.filter_name)
            unique_candidates.append(candidate)
    return unique_candidates


def summarize_filter(
    candidate: CandidateFilter,
    daily: pd.DataFrame,
    availability: pd.DataFrame,
    locations: pd.DataFrame,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    kept = list(candidate.kept_sensors)
    filtered_daily = daily[kept]
    filtered_availability = availability[kept]
    reference_mean = filtered_daily.mean(axis=1, skipna=True)
    spatial_sd = filtered_daily.std(axis=1, skipna=True)
    spatial_cv = spatial_sd / reference_mean
    missing_fraction = 1 - filtered_availability.mean(axis=1, skipna=True)
    valid_sensor_count = filtered_daily.notna().sum(axis=1)
    daily_metrics = pd.DataFrame(
        {
            "reference_mean_ugm3": reference_mean,
            "spatial_sd_ugm3": spatial_sd,
            "spatial_cv": spatial_cv,
            "daily_missing_fraction": missing_fraction,
            "time_index_days": baseline["time_index_days"],
        }
    )
    mean_difference = reference_mean - baseline["reference_mean"]
    abs_difference = mean_difference.abs()
    episodes = high_missing_episodes(missing_fraction, threshold=0.25)
    sensor_daily_missing = 1 - filtered_availability.mean(axis=0)
    retained_locations = locations[locations["Sensor_ID"].isin(kept)].set_index("Sensor_ID").loc[kept].reset_index()
    temporal_rho = spearman_rho(daily_metrics["time_index_days"], daily_metrics["daily_missing_fraction"])
    spatial_cv_rho = spearman_rho(daily_metrics["spatial_cv"], daily_metrics["daily_missing_fraction"])
    spatial_sd_rho = spearman_rho(daily_metrics["spatial_sd_ugm3"], daily_metrics["daily_missing_fraction"])
    pm_rho = spearman_rho(daily_metrics["reference_mean_ugm3"], daily_metrics["daily_missing_fraction"])
    partial = multivariable_coefficients(daily_metrics)
    return {
        "filter_name": candidate.filter_name,
        "filter_family": candidate.filter_family,
        "description": candidate.description,
        "targeted_to_outcome": candidate.targeted_to_outcome,
        "sensors_retained": int(len(candidate.kept_sensors)),
        "sensors_removed": int(len(candidate.removed_sensors)),
        "removed_sensor_ids": ";".join(candidate.removed_sensors),
        "daily_missing_mean_pct": float(missing_fraction.mean() * 100),
        "daily_missing_median_pct": float(missing_fraction.median() * 100),
        "daily_missing_p90_pct": float(missing_fraction.quantile(0.90) * 100),
        "days_missing_ge_25pct": int((missing_fraction >= 0.25).sum()),
        "longest_missing_ge_25pct_episode_days": int(episodes["duration_days"].max()) if not episodes.empty else 0,
        "daily_valid_sensor_min": int(valid_sensor_count.min()),
        "daily_valid_sensor_median": float(valid_sensor_count.median()),
        "missing_mean_improvement_pct_points": float((baseline["missing_fraction"] - missing_fraction).mean() * 100),
        "reference_mean_bias_ugm3": float(mean_difference.mean()),
        "reference_mean_mae_ugm3": float(abs_difference.mean()),
        "reference_mean_p95_abs_diff_ugm3": float(abs_difference.quantile(0.95)),
        "reference_mean_max_abs_diff_ugm3": float(abs_difference.max()),
        "reference_mean_pearson_r": pearson_r(baseline["reference_mean"], reference_mean),
        "daily_mean_pm25_spearman_rho": pm_rho,
        "temporal_spearman_rho": temporal_rho,
        "spatial_cv_spearman_rho": spatial_cv_rho,
        "spatial_sd_spearman_rho": spatial_sd_rho,
        "sensor_missing_morans_i": morans_i(sensor_daily_missing, retained_locations),
        "temporal_abs_reduction": abs(baseline["temporal_rho"]) - abs(temporal_rho),
        "spatial_cv_abs_reduction": abs(baseline["spatial_cv_rho"]) - abs(spatial_cv_rho),
        "spatial_sd_abs_reduction": abs(baseline["spatial_sd_rho"]) - abs(spatial_sd_rho),
        "pm_abs_reduction": abs(baseline["pm_rho"]) - abs(pm_rho),
        "joint_temporal_spatial_cv_reduction": (abs(baseline["temporal_rho"]) - abs(temporal_rho))
        + (abs(baseline["spatial_cv_rho"]) - abs(spatial_cv_rho)),
        **partial,
    }


def build_summary_tables(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    nonbaseline = results[results["filter_name"] != "baseline_all_sensors"].copy()
    practical = nonbaseline[
        (nonbaseline["sensors_retained"] >= 50)
        & (nonbaseline["reference_mean_mae_ugm3"] <= 1.0)
        & (~nonbaseline["targeted_to_outcome"])
    ].copy()
    strict_practical = nonbaseline[
        (nonbaseline["sensors_retained"] >= 50)
        & (nonbaseline["reference_mean_mae_ugm3"] <= 0.5)
        & (~nonbaseline["targeted_to_outcome"])
    ].copy()
    targeted = nonbaseline[
        (nonbaseline["sensors_retained"] >= 50)
        & (nonbaseline["reference_mean_mae_ugm3"] <= 1.0)
        & (nonbaseline["targeted_to_outcome"])
    ].copy()
    return {
        "top_temporal_all": nonbaseline.sort_values("temporal_abs_reduction", ascending=False).head(15),
        "top_spatial_cv_all": nonbaseline.sort_values("spatial_cv_abs_reduction", ascending=False).head(15),
        "top_joint_all": nonbaseline.sort_values("joint_temporal_spatial_cv_reduction", ascending=False).head(15),
        "top_temporal_practical": practical.sort_values("temporal_abs_reduction", ascending=False).head(15),
        "top_spatial_cv_practical": practical.sort_values("spatial_cv_abs_reduction", ascending=False).head(15),
        "top_joint_practical": practical.sort_values("joint_temporal_spatial_cv_reduction", ascending=False).head(15),
        "top_joint_practical_ref_mae_le_0p5": strict_practical.sort_values(
            "joint_temporal_spatial_cv_reduction", ascending=False
        ).head(15),
        "top_targeted_joint_low_distortion": targeted.sort_values(
            "joint_temporal_spatial_cv_reduction", ascending=False
        ).head(15),
    }


def markdown_table(frame: pd.DataFrame, columns: list[str], max_rows: int = 10) -> str:
    display = frame[columns].head(max_rows).copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def write_report(results: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> None:
    baseline = results[results["filter_name"] == "baseline_all_sensors"].iloc[0]
    practical_joint = tables["top_joint_practical"].iloc[0] if not tables["top_joint_practical"].empty else None
    strict_practical_joint = (
        tables["top_joint_practical_ref_mae_le_0p5"].iloc[0]
        if not tables["top_joint_practical_ref_mae_le_0p5"].empty
        else None
    )
    targeted_joint = (
        tables["top_targeted_joint_low_distortion"].iloc[0]
        if not tables["top_targeted_joint_low_distortion"].empty
        else None
    )
    columns = [
        "filter_name",
        "filter_family",
        "sensors_retained",
        "daily_missing_median_pct",
        "temporal_spearman_rho",
        "temporal_abs_reduction",
        "spatial_cv_spearman_rho",
        "spatial_cv_abs_reduction",
        "joint_temporal_spatial_cv_reduction",
        "reference_mean_mae_ugm3",
    ]
    lines = [
        "# Lucknow Temporal and Spatial Missingness Filter Search",
        "",
        "## Scope",
        "",
        "This searches multiple filtering strategies to see which rules reduce observed temporal missingness structure and missingness dependence on daily spatial variability. The search includes practical rules based on uptime/gap thresholds and diagnostic-targeted rules based on which sensors most contribute to temporal or spatial-CV missingness.",
        "",
        "Targeted rules are useful for diagnosis, but they should not be the primary manuscript rule unless we explicitly describe them as post hoc sensitivity checks.",
        "",
        "## Baseline MAR-Factor Screen",
        "",
        f"- Baseline temporal Spearman rho: {baseline['temporal_spearman_rho']:.3f}.",
        f"- Baseline spatial-CV Spearman rho: {baseline['spatial_cv_spearman_rho']:.3f}.",
        f"- Baseline median daily missingness: {baseline['daily_missing_median_pct']:.2f}%.",
        "",
        "## Practical Best Rule",
        "",
    ]
    if practical_joint is None:
        lines.append("No non-targeted practical rule met the retained-sensor and reference-MAE constraints.")
    else:
        lines.extend(
            [
                f"- Best non-targeted low-distortion joint rule: `{practical_joint['filter_name']}`.",
                f"- It retains {int(practical_joint['sensors_retained'])} sensors and has reference-mean MAE {practical_joint['reference_mean_mae_ugm3']:.2f} µg/m³.",
                f"- Temporal rho changes from {baseline['temporal_spearman_rho']:.3f} to {practical_joint['temporal_spearman_rho']:.3f}.",
                f"- Spatial-CV rho changes from {baseline['spatial_cv_spearman_rho']:.3f} to {practical_joint['spatial_cv_spearman_rho']:.3f}.",
            ]
        )
    if strict_practical_joint is not None:
        lines.extend(
            [
                "",
                "## Strict Low-Distortion Practical Rule",
                "",
                f"- Best non-targeted rule with reference-mean MAE <= 0.5 µg/m³: `{strict_practical_joint['filter_name']}`.",
                f"- It retains {int(strict_practical_joint['sensors_retained'])} sensors and has reference-mean MAE {strict_practical_joint['reference_mean_mae_ugm3']:.2f} µg/m³.",
                f"- Temporal rho changes from {baseline['temporal_spearman_rho']:.3f} to {strict_practical_joint['temporal_spearman_rho']:.3f}.",
                f"- Spatial-CV rho changes from {baseline['spatial_cv_spearman_rho']:.3f} to {strict_practical_joint['spatial_cv_spearman_rho']:.3f}.",
            ]
        )
    if targeted_joint is not None:
        lines.extend(
            [
                "",
                "## Diagnostic Targeted Best Rule",
                "",
                f"- Best targeted low-distortion joint rule: `{targeted_joint['filter_name']}`.",
                f"- It retains {int(targeted_joint['sensors_retained'])} sensors and has reference-mean MAE {targeted_joint['reference_mean_mae_ugm3']:.2f} µg/m³.",
                f"- Temporal rho changes from {baseline['temporal_spearman_rho']:.3f} to {targeted_joint['temporal_spearman_rho']:.3f}.",
                f"- Spatial-CV rho changes from {baseline['spatial_cv_spearman_rho']:.3f} to {targeted_joint['spatial_cv_spearman_rho']:.3f}.",
            ]
        )
    lines.extend(
        [
            "",
            "## Best Temporal Reductions: All Rules",
            "",
            markdown_table(tables["top_temporal_all"], columns),
            "",
            "## Best Spatial-CV Reductions: All Rules",
            "",
            markdown_table(tables["top_spatial_cv_all"], columns),
            "",
            "## Best Joint Reductions: Practical Non-Targeted Rules",
            "",
            markdown_table(tables["top_joint_practical"], columns),
            "",
            "## Best Joint Reductions: Practical Rules With Reference MAE <= 0.5 µg/m³",
            "",
            markdown_table(tables["top_joint_practical_ref_mae_le_0p5"], columns),
            "",
            "## Best Joint Reductions: Targeted Diagnostic Rules",
            "",
            markdown_table(tables["top_targeted_joint_low_distortion"], columns),
            "",
            "## Output Files",
            "",
            "- `lucknow_missingness_filter_search_all_results.csv`",
            "- `lucknow_missingness_filter_search_top_temporal_all.csv`",
            "- `lucknow_missingness_filter_search_top_spatial_cv_all.csv`",
            "- `lucknow_missingness_filter_search_top_joint_all.csv`",
            "- `lucknow_missingness_filter_search_top_joint_practical.csv`",
            "- `lucknow_missingness_filter_search_top_joint_practical_ref_mae_le_0p5.csv`",
            "- `lucknow_missingness_filter_search_top_targeted_joint_low_distortion.csv`",
            "- `lucknow_missingness_filter_search.md`",
        ]
    )
    (OUTPUT_DIR / "lucknow_missingness_filter_search.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    config = next(config for config in PRIMARY_NETWORKS if config.city == "Lucknow")
    pm = read_pm_matrix(config.pm_path)
    _, locations = read_locations(config)
    sensor_ids = retained_sensor_ids(locations, pm)
    locations = locations[locations["Sensor_ID"].isin(sensor_ids)].set_index("Sensor_ID").loc[sensor_ids].reset_index()
    daily = daily_sensor_means(config, pm, sensor_ids)
    availability = daily_sensor_availability(config, pm, sensor_ids).reindex(daily.index)
    reference_mean = daily[sensor_ids].mean(axis=1, skipna=True)
    spatial_sd = daily[sensor_ids].std(axis=1, skipna=True)
    spatial_cv = spatial_sd / reference_mean
    missing_fraction = 1 - availability[sensor_ids].mean(axis=1, skipna=True)
    time_index = pd.Series((pd.to_datetime(daily.index) - pd.to_datetime(daily.index).min()).days, index=daily.index)
    baseline = {
        "reference_mean": reference_mean,
        "missing_fraction": missing_fraction,
        "time_index_days": time_index,
        "temporal_rho": spearman_rho(time_index, missing_fraction),
        "spatial_cv_rho": spearman_rho(spatial_cv, missing_fraction),
        "spatial_sd_rho": spearman_rho(spatial_sd, missing_fraction),
        "pm_rho": spearman_rho(reference_mean, missing_fraction),
    }
    record_uptime = pm[sensor_ids].notna().mean(axis=0)
    daily_presence = daily[sensor_ids].notna().mean(axis=0)
    longest_gap = daily[sensor_ids].isna().apply(max_consecutive_true)
    scores = build_ranked_sensor_scores(sensor_ids, daily, availability, pm, spatial_cv, time_index)
    candidates = build_candidates(sensor_ids, record_uptime, daily_presence, longest_gap, scores)
    results = pd.DataFrame(
        [
            summarize_filter(candidate, daily, availability, locations, baseline)
            for candidate in candidates
        ]
    )
    results = results.sort_values(
        ["targeted_to_outcome", "filter_family", "joint_temporal_spatial_cv_reduction"],
        ascending=[True, True, False],
    ).reset_index(drop=True)
    tables = build_summary_tables(results)
    outputs = {"lucknow_missingness_filter_search_all_results.csv": results}
    outputs.update(
        {
            f"lucknow_missingness_filter_search_{name}.csv": table
            for name, table in tables.items()
        }
    )
    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)
    metadata = {
        "purpose": "Search multiple Lucknow filters for effects on temporal and spatial missingness factors.",
        "min_sensors_retained": MIN_SENSORS_RETAINED,
        "remove_k_values": REMOVE_K_VALUES,
        "presence_thresholds": PRESENCE_THRESHOLDS,
        "max_gap_thresholds": MAX_GAP_THRESHOLDS,
        "targeted_rho_thresholds": TARGETED_RHO_THRESHOLDS,
        "candidate_count": int(len(candidates)),
        "outputs": sorted([*outputs.keys(), "lucknow_missingness_filter_search.md"]),
    }
    (OUTPUT_DIR / "lucknow_missingness_filter_search_metadata.json").write_text(json.dumps(metadata, indent=2))
    write_report(results, tables)
    print(f"Wrote Lucknow missingness filter search to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        tables["top_joint_practical"][
            [
                "filter_name",
                "filter_family",
                "sensors_retained",
                "temporal_spearman_rho",
                "spatial_cv_spearman_rho",
                "joint_temporal_spatial_cv_reduction",
                "reference_mean_mae_ugm3",
            ]
        ].head(10).to_string(index=False)
    )


if __name__ == "__main__":
    main()
