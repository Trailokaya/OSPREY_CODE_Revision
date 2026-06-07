from __future__ import annotations

import json
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
    DATA_ROOT,
    PRIMARY_NETWORKS,
    REPO_ROOT,
    CityNetwork,
    daily_sensor_availability,
    daily_sensor_means,
    haversine_km,
    read_locations,
    read_pm_matrix,
    retained_sensor_ids,
)


OUTPUT_DIR = REPO_ROOT / "analysis/results/three_city_comparative_analysis"
RANDOM_SEED = 20260524
N_PERMUTATIONS = 5_000
HIGH_MISSING_THRESHOLDS = (0.10, 0.25, 0.50)


@dataclass(frozen=True)
class PreparedNetwork:
    config: CityNetwork
    pm: pd.DataFrame
    locations: pd.DataFrame
    sensor_ids: list[str]
    daily: pd.DataFrame
    availability: pd.DataFrame


def pearson_r(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if len(x) < 3:
        return float("nan")
    x_centered = x - x.mean()
    y_centered = y - y.mean()
    denominator = np.sqrt(np.sum(x_centered**2) * np.sum(y_centered**2))
    if denominator == 0:
        return float("nan")
    return float(np.sum(x_centered * y_centered) / denominator)


def spearman_rho(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    return pearson_r(frame["x"].rank(method="average"), frame["y"].rank(method="average"))


def zscore(series: pd.Series) -> pd.Series:
    standard_deviation = series.std(ddof=0)
    if pd.isna(standard_deviation) or standard_deviation == 0:
        return pd.Series(np.nan, index=series.index)
    return (series - series.mean()) / standard_deviation


def ols_fit(frame: pd.DataFrame, y_column: str, x_columns: list[str]) -> tuple[np.ndarray, float]:
    y = frame[y_column].to_numpy(dtype=float)
    x = frame[x_columns].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(frame)), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    predicted = design @ beta
    total_sum_squares = float(np.sum((y - y.mean()) ** 2))
    residual_sum_squares = float(np.sum((y - predicted) ** 2))
    r_squared = 1 - residual_sum_squares / total_sum_squares if total_sum_squares else float("nan")
    return beta, r_squared


def prepare_networks() -> list[PreparedNetwork]:
    prepared = []
    for config in PRIMARY_NETWORKS:
        pm = read_pm_matrix(config.pm_path)
        _, locations = read_locations(config)
        sensor_ids = retained_sensor_ids(locations, pm)
        locations = locations[locations["Sensor_ID"].isin(sensor_ids)].set_index("Sensor_ID").loc[sensor_ids].reset_index()
        daily = daily_sensor_means(config, pm, sensor_ids)
        availability = daily_sensor_availability(config, pm, sensor_ids).reindex(daily.index)
        prepared.append(PreparedNetwork(config, pm, locations, sensor_ids, daily, availability))
    return prepared


def daily_metrics(network: PreparedNetwork) -> pd.DataFrame:
    daily = network.daily
    availability = network.availability
    frame = pd.DataFrame(
        {
            "dataset_key": network.config.dataset_key,
            "city": network.config.city,
            "date": daily.index,
            "daily_reference_mean_ugm3": daily.mean(axis=1, skipna=True),
            "daily_reference_median_ugm3": daily.median(axis=1, skipna=True),
            "daily_spatial_sd_ugm3": daily.std(axis=1, skipna=True),
            "daily_spatial_cv": daily.std(axis=1, skipna=True) / daily.mean(axis=1, skipna=True),
            "daily_valid_sensor_count": daily.notna().sum(axis=1),
            "daily_missing_fraction": 1 - availability.mean(axis=1, skipna=True),
        }
    ).reset_index(drop=True)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["time_index_days"] = (frame["date"] - frame["date"].min()).dt.days
    frame["month"] = frame["date"].dt.to_period("M").astype(str)
    return frame


def build_multivariable_daily_models(all_daily: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    predictor_map = {
        "daily_mean_pm25": "daily_reference_mean_ugm3",
        "daily_spatial_cv": "daily_spatial_cv",
        "calendar_time": "time_index_days",
    }
    records = []
    for city, city_frame in all_daily.groupby("city", sort=True):
        model_frame = city_frame[["daily_missing_fraction", *predictor_map.values()]].replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if len(model_frame) < 20:
            continue
        standardized = pd.DataFrame({"missing_pct": model_frame["daily_missing_fraction"] * 100})
        for name, column in predictor_map.items():
            standardized[name] = zscore(model_frame[column])
        standardized = standardized.dropna()
        x_columns = list(predictor_map)
        beta, r_squared = ols_fit(standardized, "missing_pct", x_columns)
        permutation_betas = np.empty((N_PERMUTATIONS, len(x_columns)), dtype=float)
        y_values = standardized["missing_pct"].to_numpy(dtype=float)
        for permutation_index in range(N_PERMUTATIONS):
            permuted = standardized.copy()
            permuted["missing_pct"] = rng.permutation(y_values)
            permutation_betas[permutation_index] = ols_fit(permuted, "missing_pct", x_columns)[0][1:]
        for predictor_index, predictor in enumerate(x_columns):
            coefficient = float(beta[predictor_index + 1])
            p_value = float(
                (np.sum(np.abs(permutation_betas[:, predictor_index]) >= abs(coefficient)) + 1)
                / (N_PERMUTATIONS + 1)
            )
            records.append(
                {
                    "city": city,
                    "model": "daily_missing_pct ~ daily_mean_pm25 + daily_spatial_cv + calendar_time",
                    "n_days": int(len(standardized)),
                    "predictor": predictor,
                    "coefficient_missing_pct_points_per_1sd": coefficient,
                    "permutation_p_value": p_value,
                    "model_r_squared": float(r_squared),
                }
            )
    return pd.DataFrame(records)


def build_lag_correlations(all_daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    variables = {
        "daily_mean_pm25": "daily_reference_mean_ugm3",
        "daily_spatial_cv": "daily_spatial_cv",
        "daily_spatial_sd": "daily_spatial_sd_ugm3",
    }
    records = []
    for city, city_frame in all_daily.groupby("city", sort=True):
        city_frame = city_frame.sort_values("date").set_index("date")
        for label, column in variables.items():
            for lag_days in range(-14, 15):
                shifted = city_frame[column].shift(lag_days)
                frame = pd.DataFrame(
                    {"x": shifted, "missing_fraction": city_frame["daily_missing_fraction"]}
                ).replace([np.inf, -np.inf], np.nan).dropna()
                records.append(
                    {
                        "city": city,
                        "x_variable": label,
                        "lag_days": lag_days,
                        "lag_interpretation": "positive means x from earlier dates; negative means x from later dates",
                        "n_days": int(len(frame)),
                        "spearman_rho": spearman_rho(frame["x"], frame["missing_fraction"]),
                    }
                )
    lag = pd.DataFrame(records)
    peaks = (
        lag.assign(abs_spearman_rho=lag["spearman_rho"].abs())
        .sort_values(["city", "x_variable", "abs_spearman_rho"], ascending=[True, True, False])
        .groupby(["city", "x_variable"], as_index=False)
        .head(1)
        .reset_index(drop=True)
    )
    return lag, peaks


def run_episodes(boolean_series: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    episodes = []
    start: pd.Timestamp | None = None
    previous: pd.Timestamp | None = None
    length = 0
    for timestamp, value in boolean_series.items():
        if bool(value):
            if start is None:
                start = timestamp
                length = 0
            previous = timestamp
            length += 1
        elif start is not None and previous is not None:
            episodes.append((start, previous, length))
            start = None
            previous = None
            length = 0
    if start is not None and previous is not None:
        episodes.append((start, previous, length))
    return episodes


def build_network_episodes(all_daily: pd.DataFrame) -> pd.DataFrame:
    records = []
    for city, city_frame in all_daily.groupby("city", sort=True):
        city_frame = city_frame.sort_values("date").set_index("date")
        for threshold in HIGH_MISSING_THRESHOLDS:
            is_high_missing = city_frame["daily_missing_fraction"] >= threshold
            for start, end, length in run_episodes(is_high_missing):
                episode = city_frame.loc[start:end]
                records.append(
                    {
                        "city": city,
                        "threshold_missing_pct": threshold * 100,
                        "start_date": start.date().isoformat(),
                        "end_date": end.date().isoformat(),
                        "duration_days": int(length),
                        "mean_missing_pct": float(episode["daily_missing_fraction"].mean() * 100),
                        "max_missing_pct": float(episode["daily_missing_fraction"].max() * 100),
                        "mean_pm25_ugm3": float(episode["daily_reference_mean_ugm3"].mean()),
                        "mean_spatial_cv": float(episode["daily_spatial_cv"].mean()),
                    }
                )
    if not records:
        return pd.DataFrame()
    return (
        pd.DataFrame(records)
        .sort_values(["city", "threshold_missing_pct", "duration_days", "max_missing_pct"], ascending=[True, True, False, False])
        .reset_index(drop=True)
    )


def build_sensor_gap_episodes(networks: list[PreparedNetwork]) -> pd.DataFrame:
    records = []
    for network in networks:
        missing_by_day = network.daily.isna()
        for sensor_id in network.sensor_ids:
            sensor_missing = missing_by_day[sensor_id]
            for start, end, length in run_episodes(sensor_missing):
                records.append(
                    {
                        "dataset_key": network.config.dataset_key,
                        "city": network.config.city,
                        "sensor_id": sensor_id,
                        "start_date": start.date().isoformat(),
                        "end_date": end.date().isoformat(),
                        "duration_days": int(length),
                    }
                )
    if not records:
        return pd.DataFrame()
    return (
        pd.DataFrame(records)
        .sort_values(["city", "duration_days", "sensor_id"], ascending=[True, False, True])
        .groupby("city", as_index=False)
        .head(30)
        .reset_index(drop=True)
    )


def hourly_network_configs() -> tuple[CityNetwork, ...]:
    return (
        PRIMARY_NETWORKS[0],
        PRIMARY_NETWORKS[1],
        CityNetwork(
            dataset_key="chicago_lcs_corrected_no_collocation_hourly",
            city="Chicago",
            display_name="Chicago corrected LCS hourly (collocation excluded)",
            pm_path=DATA_ROOT / "pm/Chicago_LCS_corrected_hourly_PM25.csv",
            location_path=DATA_ROOT / "locations/Chicago_LCS_corrected_sensor_locations.csv",
            source_frequency="hourly",
            pm_value="corrected_pm25",
            exclude_collocated=True,
        ),
    )


def build_hourly_profiles() -> tuple[pd.DataFrame, pd.DataFrame]:
    records = []
    for config in hourly_network_configs():
        pm = read_pm_matrix(config.pm_path)
        _, locations = read_locations(config)
        sensor_ids = retained_sensor_ids(locations, pm)
        values = pm[["Timestamp", *sensor_ids]].copy()
        values["hour"] = values["Timestamp"].dt.hour
        values["month"] = values["Timestamp"].dt.to_period("M").astype(str)
        for hour, hour_frame in values.groupby("hour", sort=True):
            matrix = hour_frame[sensor_ids]
            records.append(
                {
                    "dataset_key": config.dataset_key,
                    "city": config.city,
                    "hour": int(hour),
                    "timestamp_rows": int(len(hour_frame)),
                    "missing_fraction_pct": float((1 - matrix.notna().mean(axis=1)).mean() * 100),
                    "valid_sensor_count_median": float(matrix.notna().sum(axis=1).median()),
                }
            )
    hourly = pd.DataFrame(records)
    summary_records = []
    for city, city_hourly in hourly.groupby("city", sort=True):
        min_row = city_hourly.loc[city_hourly["missing_fraction_pct"].idxmin()]
        max_row = city_hourly.loc[city_hourly["missing_fraction_pct"].idxmax()]
        summary_records.append(
            {
                "city": city,
                "lowest_missing_hour": int(min_row["hour"]),
                "lowest_hour_missing_pct": float(min_row["missing_fraction_pct"]),
                "highest_missing_hour": int(max_row["hour"]),
                "highest_hour_missing_pct": float(max_row["missing_fraction_pct"]),
                "hourly_range_pct_points": float(max_row["missing_fraction_pct"] - min_row["missing_fraction_pct"]),
            }
        )
    return hourly, pd.DataFrame(summary_records)


def sensor_missingness_concentration(networks: list[PreparedNetwork]) -> pd.DataFrame:
    records = []
    for network in networks:
        missing_cells = network.pm[network.sensor_ids].isna().sum(axis=0).sort_values(ascending=False)
        total_missing = int(missing_cells.sum())
        sensor_count = len(missing_cells)
        top_10_count = max(1, int(np.ceil(sensor_count * 0.10)))
        top_20_count = max(1, int(np.ceil(sensor_count * 0.20)))
        record_uptime = network.pm[network.sensor_ids].notna().mean(axis=0)
        longest_gaps = network.daily.isna().apply(lambda series: max((length for _, _, length in run_episodes(series)), default=0))
        records.append(
            {
                "dataset_key": network.config.dataset_key,
                "city": network.config.city,
                "sensor_count": sensor_count,
                "total_missing_cells": total_missing,
                "top_10pct_sensors_missing_cell_share_pct": float(missing_cells.head(top_10_count).sum() / total_missing * 100)
                if total_missing
                else 0.0,
                "top_20pct_sensors_missing_cell_share_pct": float(missing_cells.head(top_20_count).sum() / total_missing * 100)
                if total_missing
                else 0.0,
                "sensors_below_90pct_uptime": int((record_uptime < 0.90).sum()),
                "sensors_below_75pct_uptime": int((record_uptime < 0.75).sum()),
                "sensors_below_50pct_uptime": int((record_uptime < 0.50).sum()),
                "sensors_with_gap_gt_30d": int((longest_gaps > 30).sum()),
                "sensors_with_gap_gt_90d": int((longest_gaps > 90).sum()),
            }
        )
    return pd.DataFrame(records)


def knn_weight_matrix(locations: pd.DataFrame, k: int = 5) -> np.ndarray:
    coords = locations[["Latitude", "Longitude"]].to_numpy(dtype=float)
    n = len(coords)
    weights = np.zeros((n, n), dtype=float)
    for index in range(n):
        distances = haversine_km(coords[index, 0], coords[index, 1], coords[:, 0], coords[:, 1])
        distances[index] = np.inf
        nearest = np.argsort(distances)[: min(k, n - 1)]
        weights[index, nearest] = 1.0
    return weights


def morans_i(values: np.ndarray, weights: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    values = values[valid]
    weights = weights[np.ix_(valid, valid)]
    n = len(values)
    if n < 3:
        return float("nan")
    centered = values - values.mean()
    denominator = float(np.sum(centered**2))
    weight_sum = float(weights.sum())
    if denominator == 0 or weight_sum == 0:
        return float("nan")
    return float(n / weight_sum * (centered @ weights @ centered) / denominator)


def build_sensor_spatial_moran(networks: list[PreparedNetwork], rng: np.random.Generator) -> pd.DataFrame:
    records = []
    for network in networks:
        weights = knn_weight_matrix(network.locations, k=5)
        record_missing_pct = (1 - network.pm[network.sensor_ids].notna().mean(axis=0)) * 100
        daily_missing_pct = (1 - network.daily.notna().mean(axis=0)) * 100
        longest_gap = network.daily.isna().apply(lambda series: max((length for _, _, length in run_episodes(series)), default=0))
        for label, values in [
            ("record_missing_pct", record_missing_pct),
            ("daily_missing_pct", daily_missing_pct),
            ("longest_missing_gap_days", longest_gap),
        ]:
            aligned_values = values.loc[network.sensor_ids].to_numpy(dtype=float)
            observed = morans_i(aligned_values, weights)
            permutation_values = np.empty(N_PERMUTATIONS, dtype=float)
            for index in range(N_PERMUTATIONS):
                permutation_values[index] = morans_i(rng.permutation(aligned_values), weights)
            p_two_sided = float(
                (np.sum(np.abs(permutation_values) >= abs(observed)) + 1) / (N_PERMUTATIONS + 1)
            )
            p_positive = float((np.sum(permutation_values >= observed) + 1) / (N_PERMUTATIONS + 1))
            records.append(
                {
                    "dataset_key": network.config.dataset_key,
                    "city": network.config.city,
                    "metric": label,
                    "k_nearest_neighbors": 5,
                    "morans_i": observed,
                    "permutation_p_two_sided": p_two_sided,
                    "permutation_p_positive_clustering": p_positive,
                }
            )
    return pd.DataFrame(records)


def build_reference_mean_sensitivity(networks: list[PreparedNetwork]) -> pd.DataFrame:
    records = []
    for network in networks:
        daily = network.daily
        baseline = daily.mean(axis=1, skipna=True)
        record_uptime = network.pm[network.sensor_ids].notna().mean(axis=0)
        daily_uptime = daily.notna().mean(axis=0)
        longest_gap = daily.isna().apply(lambda series: max((length for _, _, length in run_episodes(series)), default=0))
        filters = {
            "all_retained_sensors": pd.Series(True, index=network.sensor_ids),
            "record_uptime_ge_75pct": record_uptime >= 0.75,
            "record_uptime_ge_90pct": record_uptime >= 0.90,
            "daily_uptime_ge_75pct_and_gap_le_30d": (daily_uptime >= 0.75) & (longest_gap <= 30),
            "exclude_gap_gt_90d": longest_gap <= 90,
        }
        for filter_name, keep_series in filters.items():
            keep_ids = [sensor_id for sensor_id in network.sensor_ids if bool(keep_series.loc[sensor_id])]
            filtered_mean = daily[keep_ids].mean(axis=1, skipna=True) if keep_ids else pd.Series(np.nan, index=daily.index)
            paired = pd.DataFrame({"baseline": baseline, "filtered": filtered_mean}).dropna()
            difference = paired["filtered"] - paired["baseline"]
            records.append(
                {
                    "dataset_key": network.config.dataset_key,
                    "city": network.config.city,
                    "filter_name": filter_name,
                    "sensors_retained": int(len(keep_ids)),
                    "days_compared": int(len(paired)),
                    "baseline_mean_ugm3": float(paired["baseline"].mean()) if len(paired) else np.nan,
                    "filtered_mean_ugm3": float(paired["filtered"].mean()) if len(paired) else np.nan,
                    "bias_filtered_minus_baseline_ugm3": float(difference.mean()) if len(paired) else np.nan,
                    "mae_filtered_vs_baseline_ugm3": float(difference.abs().mean()) if len(paired) else np.nan,
                    "max_abs_difference_ugm3": float(difference.abs().max()) if len(paired) else np.nan,
                    "pearson_r": float(paired["baseline"].corr(paired["filtered"])) if len(paired) >= 3 else np.nan,
                }
            )
    return pd.DataFrame(records)


def markdown_table(frame: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> str:
    display = frame[columns].copy()
    if max_rows is not None:
        display = display.head(max_rows)
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def write_report(
    multivariable: pd.DataFrame,
    lag_peaks: pd.DataFrame,
    network_episodes: pd.DataFrame,
    sensor_gaps: pd.DataFrame,
    hourly_summary: pd.DataFrame,
    concentration: pd.DataFrame,
    spatial_moran: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> None:
    top_multivariable = (
        multivariable.assign(abs_coeff=multivariable["coefficient_missing_pct_points_per_1sd"].abs())
        .sort_values(["city", "abs_coeff"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(3)
    )
    top_lags = (
        lag_peaks.assign(abs_spearman_rho=lag_peaks["spearman_rho"].abs())
        .sort_values(["city", "abs_spearman_rho"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(3)
    )
    top_episodes = (
        network_episodes[network_episodes["threshold_missing_pct"].eq(25.0)]
        .sort_values(["city", "duration_days"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(3)
    )
    top_sensor_gaps = (
        sensor_gaps.sort_values(["city", "duration_days"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(6)
    )
    top_sensitivity = sensitivity[
        sensitivity["filter_name"].isin(
            ["record_uptime_ge_75pct", "daily_uptime_ge_75pct_and_gap_le_30d", "exclude_gap_gt_90d"]
        )
    ].copy()

    lines = [
        "# Missingness Deep-Dive Summary",
        "",
        "## Scope",
        "",
        "This extends the missingness screen with multivariable controls, lag checks, high-missing episodes, sensor-gap episodes, hourly missingness profiles where hourly data exist, sensor-level missingness concentration, spatial clustering of missingness, and reference-mean sensitivity to stricter sensor inclusion.",
        "",
        "These are diagnostics. They can identify likely data-quality structure, but they cannot prove a formal missing-data mechanism because unobserved values are unavailable when sensors are missing.",
        "",
        "## Multivariable Daily Missingness Model",
        "",
        "Coefficients are percentage-point changes in daily missingness per 1 SD increase in the predictor, controlling for the other listed predictors.",
        "",
        markdown_table(
            top_multivariable,
            [
                "city",
                "predictor",
                "coefficient_missing_pct_points_per_1sd",
                "permutation_p_value",
                "model_r_squared",
            ],
        ),
        "",
        "## Peak Lag Associations",
        "",
        "Lag convention: positive lag means the predictor is from earlier dates; negative lag means the predictor is from later dates.",
        "",
        markdown_table(top_lags, ["city", "x_variable", "lag_days", "n_days", "spearman_rho"]),
        "",
        "## Network-Level High-Missing Episodes",
        "",
        "Top episodes where daily network missingness is at least 25%.",
        "",
        markdown_table(
            top_episodes,
            [
                "city",
                "threshold_missing_pct",
                "start_date",
                "end_date",
                "duration_days",
                "mean_missing_pct",
                "max_missing_pct",
            ],
        ),
        "",
        "## Longest Sensor Gap Episodes",
        "",
        markdown_table(top_sensor_gaps, ["city", "sensor_id", "start_date", "end_date", "duration_days"]),
        "",
        "## Hourly Missingness Profile",
        "",
        markdown_table(
            hourly_summary,
            [
                "city",
                "lowest_missing_hour",
                "lowest_hour_missing_pct",
                "highest_missing_hour",
                "highest_hour_missing_pct",
                "hourly_range_pct_points",
            ],
        ),
        "",
        "## Sensor Missingness Concentration",
        "",
        markdown_table(
            concentration,
            [
                "city",
                "sensor_count",
                "top_10pct_sensors_missing_cell_share_pct",
                "top_20pct_sensors_missing_cell_share_pct",
                "sensors_below_75pct_uptime",
                "sensors_below_50pct_uptime",
                "sensors_with_gap_gt_30d",
                "sensors_with_gap_gt_90d",
            ],
        ),
        "",
        "## Spatial Clustering Of Sensor Missingness",
        "",
        markdown_table(
            spatial_moran,
            [
                "city",
                "metric",
                "morans_i",
                "permutation_p_two_sided",
                "permutation_p_positive_clustering",
            ],
        ),
        "",
        "## Reference-Mean Sensitivity To Sensor Inclusion",
        "",
        markdown_table(
            top_sensitivity,
            [
                "city",
                "filter_name",
                "sensors_retained",
                "days_compared",
                "bias_filtered_minus_baseline_ugm3",
                "mae_filtered_vs_baseline_ugm3",
                "max_abs_difference_ugm3",
                "pearson_r",
            ],
        ),
        "",
        "## Output Files",
        "",
        "- `missingness_deep_multivariable_daily_models.csv`",
        "- `missingness_deep_lag_correlations.csv`",
        "- `missingness_deep_peak_lag_summary.csv`",
        "- `missingness_deep_network_episodes.csv`",
        "- `missingness_deep_sensor_gap_episodes_top.csv`",
        "- `missingness_deep_hourly_profile.csv`",
        "- `missingness_deep_hourly_summary.csv`",
        "- `missingness_deep_sensor_concentration.csv`",
        "- `missingness_deep_sensor_spatial_moran.csv`",
        "- `missingness_deep_reference_mean_sensitivity.csv`",
        "- `missingness_deep_dive_summary.md`",
    ]
    (OUTPUT_DIR / "missingness_deep_dive_summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    networks = prepare_networks()
    all_daily = pd.concat([daily_metrics(network) for network in networks], ignore_index=True)

    multivariable = build_multivariable_daily_models(all_daily, rng)
    lag_correlations, lag_peaks = build_lag_correlations(all_daily)
    network_episodes = build_network_episodes(all_daily)
    sensor_gaps = build_sensor_gap_episodes(networks)
    hourly_profile, hourly_summary = build_hourly_profiles()
    concentration = sensor_missingness_concentration(networks)
    spatial_moran = build_sensor_spatial_moran(networks, rng)
    sensitivity = build_reference_mean_sensitivity(networks)

    outputs = {
        "missingness_deep_multivariable_daily_models.csv": multivariable,
        "missingness_deep_lag_correlations.csv": lag_correlations,
        "missingness_deep_peak_lag_summary.csv": lag_peaks,
        "missingness_deep_network_episodes.csv": network_episodes,
        "missingness_deep_sensor_gap_episodes_top.csv": sensor_gaps,
        "missingness_deep_hourly_profile.csv": hourly_profile,
        "missingness_deep_hourly_summary.csv": hourly_summary,
        "missingness_deep_sensor_concentration.csv": concentration,
        "missingness_deep_sensor_spatial_moran.csv": spatial_moran,
        "missingness_deep_reference_mean_sensitivity.csv": sensitivity,
    }
    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)

    metadata = {
        "purpose": "Deep missingness/data-quality diagnostics across Dhaka, Lucknow, and Chicago.",
        "random_seed": RANDOM_SEED,
        "n_permutations": N_PERMUTATIONS,
        "high_missing_thresholds": HIGH_MISSING_THRESHOLDS,
        "outputs": sorted([*outputs.keys(), "missingness_deep_dive_summary.md"]),
        "limitation": "Diagnostics use observed data only and cannot prove formal MCAR/MAR/MNAR mechanisms.",
    }
    (OUTPUT_DIR / "missingness_deep_metadata.json").write_text(json.dumps(metadata, indent=2))
    write_report(
        multivariable,
        lag_peaks,
        network_episodes,
        sensor_gaps,
        hourly_summary,
        concentration,
        spatial_moran,
        sensitivity,
    )
    print(f"Wrote missingness deep-dive summary to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        multivariable.assign(abs_coeff=multivariable["coefficient_missing_pct_points_per_1sd"].abs())
        .sort_values(["city", "abs_coeff"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(2)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
