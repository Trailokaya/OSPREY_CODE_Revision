from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
import os

BLAS_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
for _thread_env_var in BLAS_THREAD_ENV_VARS:
    os.environ.setdefault(_thread_env_var, "1")

import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import (  # noqa: E402
    GRID_COLOR,
    OUTPUT_DPI,
    REGRESSION_LINE_COLOR,
    SCENARIO_COLORS,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


DEFAULT_DATA_ROOT = REPO_ROOT / "data"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "missingness"
DEFAULT_BOOTSTRAPS = 10_000
DEFAULT_MC_ITERATIONS = 10_000
MASTER_SEED = 20260522


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    display_name: str
    city: str
    network: str
    pm_file: str
    location_file: str
    season_scheme: str


DATASETS = [
    DatasetConfig(
        key="dhaka_lcs",
        display_name="Dhaka LCS",
        city="Dhaka",
        network="LCS",
        pm_file="Dhaka_hourly_PM25.csv",
        location_file="Dhaka_sensor_locations.csv",
        season_scheme="igp",
    ),
    DatasetConfig(
        key="lucknow_lcs",
        display_name="Lucknow LCS",
        city="Lucknow",
        network="LCS",
        pm_file="Lucknow_hourly_PM25.csv",
        location_file="Lucknow_sensor_locations.csv",
        season_scheme="igp",
    ),
    DatasetConfig(
        key="chicago_aqs",
        display_name="Chicago AQS",
        city="Chicago",
        network="AQS",
        pm_file="Chicago_AQS_hourly_PM25.csv",
        location_file="Chicago_AQS_sensor_locations.csv",
        season_scheme="chicago",
    ),
    DatasetConfig(
        key="chicago_lcs_corrected",
        display_name="Chicago LCS corrected",
        city="Chicago",
        network="LCS corrected",
        pm_file="Chicago_LCS_corrected_hourly_PM25.csv",
        location_file="Chicago_LCS_corrected_sensor_locations.csv",
        season_scheme="chicago",
    ),
    DatasetConfig(
        key="chicago_lcs_raw",
        display_name="Chicago LCS raw",
        city="Chicago",
        network="LCS raw",
        pm_file="Chicago_LCS_raw_hourly_PM25.csv",
        location_file="Chicago_LCS_raw_sensor_locations.csv",
        season_scheme="chicago",
    ),
]


SCENARIOS = {
    "S0_baseline": {"daily_min_hours": 1, "annual_uptime_min": None, "drop_long_gaps": False},
    "S1_daily_18h": {"daily_min_hours": 18, "annual_uptime_min": None, "drop_long_gaps": False},
    "S2_daily_12h": {"daily_min_hours": 12, "annual_uptime_min": None, "drop_long_gaps": False},
    "S3_annual_75pct": {"daily_min_hours": 1, "annual_uptime_min": 0.75, "drop_long_gaps": False},
    "S4_daily_18h_annual_75pct": {
        "daily_min_hours": 18,
        "annual_uptime_min": 0.75,
        "drop_long_gaps": False,
    },
    "S5_drop_gap_gt_30d": {"daily_min_hours": 1, "annual_uptime_min": None, "drop_long_gaps": True},
}


DATASET_DISPLAY_NAMES = {config.key: config.display_name for config in DATASETS}


def display_name(network_key: str) -> str:
    return DATASET_DISPLAY_NAMES.get(network_key, network_key)


def save_plot(fig: plt.Figure, output_path: Path) -> None:
    save_figure(fig, output_path.with_suffix(""), dpi=OUTPUT_DPI)


def derive_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in (MASTER_SEED, *parts)).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "little") % (2**32)


def available_cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def total_memory_bytes() -> int | None:
    if sys.platform == "darwin":
        try:
            return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
        except Exception:
            return None
    if hasattr(os, "sysconf"):
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            page_count = int(os.sysconf("SC_PHYS_PAGES"))
            return page_size * page_count
        except Exception:
            return None
    return None


def resolve_jobs(requested: int) -> int:
    cpu_count = available_cpu_count()
    if requested in {0, -1}:
        return cpu_count
    if requested < -1:
        return max(1, cpu_count + requested + 1)
    return min(requested, cpu_count)


def compute_resource_metadata(requested_jobs: int, effective_jobs: int) -> dict[str, Any]:
    memory_bytes = total_memory_bytes()
    memory_gb = memory_bytes / 1024**3 if memory_bytes is not None else None
    return {
        "requested_jobs": requested_jobs,
        "effective_jobs": effective_jobs,
        "available_cpu_count": available_cpu_count(),
        "total_memory_gb": round(memory_gb, 3) if memory_gb is not None else None,
        "platform": platform.platform(),
        "blas_thread_environment": {
            name: os.environ.get(name)
            for name in BLAS_THREAD_ENV_VARS
        },
        "blas_thread_policy": "one BLAS/native thread per worker process to avoid oversubscription",
    }


def normal_cdf(value: float) -> float:
    return 0.5 * math.erfc(-value / math.sqrt(2))


def normal_two_sided_p_from_r(r_value: float, n: int) -> float:
    if not np.isfinite(r_value) or n < 4 or abs(r_value) >= 1:
        return float("nan")
    z_score = math.atanh(r_value) * math.sqrt(n - 3)
    return 2 * (1 - normal_cdf(abs(z_score)))


def normal_one_sided_upper_p(z_score: float) -> float:
    if not np.isfinite(z_score):
        return float("nan")
    return 1 - normal_cdf(z_score)


def pearson_corr(x_values: np.ndarray, y_values: np.ndarray) -> float:
    if len(x_values) < 3 or np.nanstd(x_values) == 0 or np.nanstd(y_values) == 0:
        return float("nan")
    return float(np.corrcoef(x_values, y_values)[0, 1])


def spearman_corr(x_values: np.ndarray, y_values: np.ndarray) -> float:
    x_rank = pd.Series(x_values).rank(method="average").to_numpy()
    y_rank = pd.Series(y_values).rank(method="average").to_numpy()
    return pearson_corr(x_rank, y_rank)


def bootstrap_ci(
    x_values: np.ndarray,
    y_values: np.ndarray,
    corr_fn,
    rng: np.random.Generator,
    n_bootstrap: int,
) -> tuple[float, float]:
    if len(x_values) < 4:
        return float("nan"), float("nan")
    estimates = []
    indexes = np.arange(len(x_values))
    for _ in range(n_bootstrap):
        sample = rng.choice(indexes, size=len(indexes), replace=True)
        estimate = corr_fn(x_values[sample], y_values[sample])
        if np.isfinite(estimate):
            estimates.append(estimate)
    if not estimates:
        return float("nan"), float("nan")
    lower, upper = np.percentile(estimates, [2.5, 97.5])
    return float(lower), float(upper)


def correlation_result(
    x_series: pd.Series,
    y_series: pd.Series,
    rng: np.random.Generator,
    n_bootstrap: int,
) -> dict[str, float | int]:
    frame = pd.DataFrame({"x": x_series, "y": y_series}).replace([np.inf, -np.inf], np.nan).dropna()
    x_values = frame["x"].to_numpy(dtype=float)
    y_values = frame["y"].to_numpy(dtype=float)
    pearson = pearson_corr(x_values, y_values)
    spearman = spearman_corr(x_values, y_values)
    pearson_ci = bootstrap_ci(x_values, y_values, pearson_corr, rng, n_bootstrap)
    spearman_ci = bootstrap_ci(x_values, y_values, spearman_corr, rng, n_bootstrap)
    return {
        "n": int(len(frame)),
        "pearson_r": pearson,
        "pearson_p_approx": normal_two_sided_p_from_r(pearson, len(frame)),
        "pearson_ci_low": pearson_ci[0],
        "pearson_ci_high": pearson_ci[1],
        "spearman_rho": spearman,
        "spearman_p_approx": normal_two_sided_p_from_r(spearman, len(frame)),
        "spearman_ci_low": spearman_ci[0],
        "spearman_ci_high": spearman_ci[1],
    }


def season_label(month: int, scheme: str) -> str:
    if scheme == "igp":
        if month in {3, 4, 5}:
            return "pre_monsoon"
        if month in {6, 7, 8, 9}:
            return "monsoon"
        if month in {10, 11}:
            return "post_monsoon"
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    if month in {9, 10, 11}:
        return "fall"
    return "winter"


def chi_square_sf_approx(statistic: float, df: int) -> float:
    if not np.isfinite(statistic) or df <= 0:
        return float("nan")
    z_score = ((statistic / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return normal_one_sided_upper_p(z_score)


def ks_2sample_approx(values_a: np.ndarray, values_b: np.ndarray) -> tuple[float, float]:
    values_a = np.sort(values_a[np.isfinite(values_a)])
    values_b = np.sort(values_b[np.isfinite(values_b)])
    if len(values_a) == 0 or len(values_b) == 0:
        return float("nan"), float("nan")
    combined = np.sort(np.concatenate([values_a, values_b]))
    cdf_a = np.searchsorted(values_a, combined, side="right") / len(values_a)
    cdf_b = np.searchsorted(values_b, combined, side="right") / len(values_b)
    statistic = float(np.max(np.abs(cdf_a - cdf_b)))
    effective_n = len(values_a) * len(values_b) / (len(values_a) + len(values_b))
    p_value = min(1.0, 2 * math.exp(-2 * effective_n * statistic**2))
    return statistic, p_value


def parse_local_dates(timestamp: pd.Series) -> pd.Series:
    return pd.to_datetime(timestamp.astype(str).str.slice(0, 10), errors="coerce")


def load_panel(data_root: Path, config: DatasetConfig) -> dict[str, Any]:
    path = data_root / "pm" / config.pm_file
    frame = pd.read_csv(path, dtype={"Timestamp": str})
    timestamps = frame["Timestamp"].astype(str)
    values = frame.drop(columns=["Timestamp"]).apply(pd.to_numeric, errors="coerce")
    values.columns = values.columns.astype(str)
    dates = parse_local_dates(timestamps)
    daily_means = values.groupby(dates).mean()
    daily_valid_hours = values.notna().groupby(dates).sum()
    daily_slots = values.groupby(dates).size().rename("hourly_slots")
    daily_missing_cells = values.isna().groupby(dates).sum().sum(axis=1)
    daily_possible_cells = daily_slots * values.shape[1]
    daily_stats = pd.DataFrame(
        {
            "date": daily_slots.index.astype(str),
            "hourly_slots": daily_slots.to_numpy(dtype=int),
            "n_sensors": values.shape[1],
            "missing_cells": daily_missing_cells.to_numpy(dtype=int),
            "possible_cells": daily_possible_cells.to_numpy(dtype=int),
        },
        index=daily_slots.index,
    )
    daily_stats["frac_missing"] = daily_stats["missing_cells"] / daily_stats["possible_cells"]
    daily_stats["mean_conc"] = values.groupby(dates).mean().mean(axis=1).to_numpy(dtype=float)
    daily_stats["valid_sensor_count"] = (daily_valid_hours > 0).sum(axis=1).to_numpy(dtype=int)
    daily_stats["sd_conc"] = daily_means.std(axis=1, skipna=True).to_numpy(dtype=float)
    daily_stats["cv_conc"] = daily_stats["sd_conc"] / daily_stats["mean_conc"]
    daily_stats["season"] = [
        season_label(date.month, config.season_scheme) for date in daily_slots.index
    ]
    return {
        "config": config,
        "timestamps": timestamps,
        "dates": dates,
        "values": values,
        "daily_means": daily_means,
        "daily_valid_hours": daily_valid_hours,
        "daily_stats": daily_stats,
    }


def compute_gaps(panel: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    config: DatasetConfig = panel["config"]
    timestamps = panel["timestamps"].reset_index(drop=True)
    dates = panel["dates"].reset_index(drop=True)
    values: pd.DataFrame = panel["values"].reset_index(drop=True)
    network_mean = values.mean(axis=1, skipna=True)
    overall_network_mean = float(network_mean.mean(skipna=True))
    records = []
    for sensor_id in values.columns:
        missing = values[sensor_id].isna().to_numpy()
        start = None
        for index, is_missing in enumerate(missing):
            if is_missing and start is None:
                start = index
            is_end = start is not None and (not is_missing or index == len(missing) - 1)
            if is_end:
                end = index - 1 if not is_missing else index
                midpoint = start + (end - start) // 2
                gap_network_mean = float(network_mean.iloc[start : end + 1].mean(skipna=True))
                records.append(
                    {
                        "network": config.key,
                        "sensor_id": str(sensor_id),
                        "start_timestamp": timestamps.iloc[start],
                        "end_timestamp": timestamps.iloc[end],
                        "duration_hours": int(end - start + 1),
                        "season_midpoint": season_label(dates.iloc[midpoint].month, config.season_scheme),
                        "network_mean_during_gap": gap_network_mean,
                        "overall_network_mean": overall_network_mean,
                        "gap_minus_overall_network_mean": gap_network_mean - overall_network_mean,
                    }
                )
                start = None
    gaps = pd.DataFrame(records)
    if gaps.empty:
        summary = pd.DataFrame(
            [
                {
                    "network": config.key,
                    "gap_count": 0,
                    "mean_gap_hours": 0,
                    "median_gap_hours": 0,
                    "p75_gap_hours": 0,
                    "p95_gap_hours": 0,
                    "max_gap_hours": 0,
                    "missing_hours_le_24h_pct": 0,
                    "missing_hours_1_7d_pct": 0,
                    "missing_hours_7_30d_pct": 0,
                    "missing_hours_gt_30d_pct": 0,
                    "gap_gt_30d_count": 0,
                }
            ]
        )
        return gaps, summary
    durations = gaps["duration_hours"]
    total_missing_hours = durations.sum()
    summary = pd.DataFrame(
        [
            {
                "network": config.key,
                "gap_count": int(len(gaps)),
                "mean_gap_hours": float(durations.mean()),
                "median_gap_hours": float(durations.median()),
                "p75_gap_hours": float(durations.quantile(0.75)),
                "p95_gap_hours": float(durations.quantile(0.95)),
                "max_gap_hours": int(durations.max()),
                "missing_hours_le_24h_pct": float(durations[durations <= 24].sum() / total_missing_hours * 100),
                "missing_hours_1_7d_pct": float(
                    durations[(durations > 24) & (durations <= 7 * 24)].sum()
                    / total_missing_hours
                    * 100
                ),
                "missing_hours_7_30d_pct": float(
                    durations[(durations > 7 * 24) & (durations <= 30 * 24)].sum()
                    / total_missing_hours
                    * 100
                ),
                "missing_hours_gt_30d_pct": float(
                    durations[durations > 30 * 24].sum() / total_missing_hours * 100
                ),
                "gap_gt_30d_count": int((durations > 30 * 24).sum()),
            }
        ]
    )
    return gaps, summary


def sensor_max_gap_hours(gaps: pd.DataFrame, sensor_ids: list[str]) -> pd.Series:
    if gaps.empty:
        return pd.Series(0, index=sensor_ids, dtype=float)
    max_gap = gaps.groupby("sensor_id")["duration_hours"].max()
    return pd.Series(sensor_ids, index=sensor_ids).map(max_gap).fillna(0).astype(float)


def scenario_retained_sensors(
    panel: dict[str, Any],
    gaps: pd.DataFrame,
    scenario: dict[str, Any],
) -> list[str]:
    values: pd.DataFrame = panel["values"]
    retained = pd.Series(True, index=values.columns)
    if scenario["annual_uptime_min"] is not None:
        retained &= values.notna().mean(axis=0) >= scenario["annual_uptime_min"]
    if scenario["drop_long_gaps"]:
        max_gaps = sensor_max_gap_hours(gaps, list(values.columns))
        retained &= max_gaps <= 30 * 24
    return retained[retained].index.tolist()


def subset_sizes(n_sensors: int) -> list[int]:
    candidates = [1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200]
    return [value for value in candidates if value <= n_sensors]


def mc_mdape(values: np.ndarray, n: int, rng: np.random.Generator, iterations: int) -> float:
    values = values[np.isfinite(values)]
    if len(values) < n or n == 0:
        return float("nan")
    reference = float(values.mean())
    if reference == 0:
        return float("nan")
    keys = rng.random((iterations, len(values)))
    indexes = np.argpartition(keys, n - 1, axis=1)[:, :n]
    estimates = values[indexes].mean(axis=1)
    ape = np.abs((estimates - reference) / reference) * 100
    return float(np.median(ape))


def daily_fraction_mdape_le_10(
    daily_frame: pd.DataFrame,
    n: int,
    rng: np.random.Generator,
    iterations: int,
) -> tuple[float, int]:
    successes = 0
    evaluated = 0
    for _, row in daily_frame.iterrows():
        values = row.dropna().to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if len(values) < n:
            continue
        reference = float(values.mean())
        if reference == 0:
            continue
        keys = rng.random((iterations, len(values)))
        indexes = np.argpartition(keys, n - 1, axis=1)[:, :n]
        estimates = values[indexes].mean(axis=1)
        ape = np.abs((estimates - reference) / reference) * 100
        successes += int(np.median(ape) <= 10)
        evaluated += 1
    if evaluated == 0:
        return float("nan"), 0
    return float(successes / evaluated), evaluated


def run_m5_scenario(
    panel: dict[str, Any],
    gaps: pd.DataFrame,
    scenario_name: str,
    scenario: dict[str, Any],
    iterations: int,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config: DatasetConfig = panel["config"]
    values: pd.DataFrame = panel["values"]
    daily_means: pd.DataFrame = panel["daily_means"]
    daily_valid_hours: pd.DataFrame = panel["daily_valid_hours"]
    rng = np.random.default_rng(seed)
    curve_records = []

    retained = scenario_retained_sensors(panel, gaps, scenario)
    if not retained:
        return (
            {
                "network": config.key,
                "scenario": scenario_name,
                "retained_sensors": 0,
                "period_required_n_mdape_le_5": np.nan,
                "daily_required_n_95pct_days_mdape_le_10": np.nan,
                "median_daily_valid_sensors": 0,
                "m5_seed": seed,
            },
            [],
        )

    period_values = values[retained].mean(axis=0, skipna=True).dropna().to_numpy(dtype=float)
    daily_filtered = daily_means[retained].where(
        daily_valid_hours[retained] >= scenario["daily_min_hours"]
    )
    daily_valid_counts = daily_filtered.notna().sum(axis=1)
    first_period_n = np.nan
    first_daily_n = np.nan
    for n in subset_sizes(len(period_values)):
        period_mdape = mc_mdape(period_values, n, rng, iterations)
        daily_fraction, valid_days = daily_fraction_mdape_le_10(
            daily_filtered,
            n,
            rng,
            iterations,
        )
        if np.isnan(first_period_n) and np.isfinite(period_mdape) and period_mdape <= 5:
            first_period_n = n
        if np.isnan(first_daily_n) and np.isfinite(daily_fraction) and daily_fraction >= 0.95:
            first_daily_n = n
        curve_records.append(
            {
                "network": config.key,
                "scenario": scenario_name,
                "n": n,
                "period_mdape_pct": period_mdape,
                "daily_fraction_days_mdape_le_10": daily_fraction,
                "daily_valid_days_evaluated": valid_days,
                "m5_seed": seed,
            }
        )
    return (
        {
            "network": config.key,
            "scenario": scenario_name,
            "retained_sensors": int(len(retained)),
            "period_required_n_mdape_le_5": first_period_n,
            "daily_required_n_95pct_days_mdape_le_10": first_daily_n,
            "median_daily_valid_sensors": float(daily_valid_counts.median()),
            "min_daily_valid_sensors": int(daily_valid_counts.min()),
            "p05_daily_valid_sensors": float(daily_valid_counts.quantile(0.05)),
            "m5_seed": seed,
        },
        curve_records,
    )


def run_m5_worker(
    task: tuple[str, dict[str, Any], pd.DataFrame, str, dict[str, Any], int, int]
) -> tuple[str, str, pd.DataFrame, pd.DataFrame]:
    key, panel, network_gaps, scenario_name, scenario, iterations, seed = task
    summary, curves = run_m5_scenario(
        panel,
        network_gaps,
        scenario_name,
        scenario,
        iterations,
        seed,
    )
    return key, scenario_name, pd.DataFrame([summary]), pd.DataFrame(curves)


def haversine_matrix(latitudes: np.ndarray, longitudes: np.ndarray) -> np.ndarray:
    radius_km = 6371.0088
    lat = np.radians(latitudes)
    lon = np.radians(longitudes)
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2) ** 2
    return 2 * radius_km * np.arcsin(np.sqrt(a))


def moran_i_approx(values: np.ndarray, weights: np.ndarray) -> tuple[float, float, float]:
    mask = np.isfinite(values)
    values = values[mask]
    weights = weights[np.ix_(mask, mask)]
    n = len(values)
    s0 = weights.sum()
    if n < 5 or s0 == 0:
        return float("nan"), float("nan"), float("nan")
    z = values - values.mean()
    denominator = float((z**2).sum())
    if denominator == 0:
        return float("nan"), float("nan"), float("nan")
    moran_i = float(n / s0 * (z @ weights @ z) / denominator)
    expected = -1 / (n - 1)
    s1 = float(0.5 * ((weights + weights.T) ** 2).sum())
    s2 = float(((weights.sum(axis=1) + weights.sum(axis=0)) ** 2).sum())
    b2 = float(n * (z**4).sum() / denominator**2)
    variance_numerator = (
        n * ((n**2 - 3 * n + 3) * s1 - n * s2 + 3 * s0**2)
        - b2 * ((n**2 - n) * s1 - 2 * n * s2 + 6 * s0**2)
    )
    variance_denominator = (n - 1) * (n - 2) * (n - 3) * s0**2
    variance = variance_numerator / variance_denominator - expected**2
    if variance <= 0 or not np.isfinite(variance):
        return moran_i, float("nan"), float("nan")
    z_score = (moran_i - expected) / math.sqrt(variance)
    p_value = normal_one_sided_upper_p(z_score)
    return moran_i, float(z_score), p_value


def run_m6(data_root: Path, panel: dict[str, Any]) -> pd.DataFrame:
    config: DatasetConfig = panel["config"]
    locations = pd.read_csv(data_root / "locations" / config.location_file, dtype={"Sensor_ID": str})
    locations = locations.set_index("Sensor_ID")
    daily_means: pd.DataFrame = panel["daily_means"]
    daily_valid_hours: pd.DataFrame = panel["daily_valid_hours"]
    common_sensors = [sensor for sensor in daily_means.columns if sensor in locations.index]
    locations = locations.loc[common_sensors]
    distances = haversine_matrix(
        locations["Latitude"].to_numpy(dtype=float),
        locations["Longitude"].to_numpy(dtype=float),
    )
    records = []
    for daily_min_label, min_hours in {"baseline_ge_1h": 1, "filtered_ge_18h": 18}.items():
        filtered = daily_means[common_sensors].where(daily_valid_hours[common_sensors] >= min_hours)
        for band_km in [2, 5, 10]:
            weights = ((distances > 0) & (distances <= band_km)).astype(float)
            day_records = []
            for date, row in filtered.iterrows():
                moran_i, z_score, p_value = moran_i_approx(row.to_numpy(dtype=float), weights)
                if np.isfinite(moran_i):
                    day_records.append((date, moran_i, z_score, p_value))
            day_frame = pd.DataFrame(day_records, columns=["date", "moran_i", "z_score", "p_value"])
            records.append(
                {
                    "network": config.key,
                    "filter": daily_min_label,
                    "distance_band_km": band_km,
                    "days_evaluated": int(len(day_frame)),
                    "median_moran_i": float(day_frame["moran_i"].median()) if not day_frame.empty else np.nan,
                    "positive_moran_i_days_pct": float((day_frame["moran_i"] > 0).mean() * 100) if not day_frame.empty else np.nan,
                    "significant_positive_days_pct": float(
                        ((day_frame["p_value"] < 0.05) & (day_frame["moran_i"] > 0)).mean() * 100
                    )
                    if not day_frame.empty
                    else np.nan,
                }
            )
    return pd.DataFrame(records)


def plot_scatter_grid(daily_by_network: dict[str, pd.DataFrame], x_col: str, y_col: str, title: str, output_path: Path) -> None:
    setup_matplotlib()
    frames = {
        network: daily[[x_col, y_col]].replace([np.inf, -np.inf], np.nan).dropna()
        for network, daily in daily_by_network.items()
    }
    all_x = pd.concat([frame[x_col] * 100 for frame in frames.values() if not frame.empty], ignore_index=True)
    all_y = pd.concat([frame[y_col] for frame in frames.values() if not frame.empty], ignore_index=True)
    x_padding = (all_x.max() - all_x.min()) * 0.05 or 1.0
    y_padding = (all_y.max() - all_y.min()) * 0.05 or 1.0
    x_limits = (float(all_x.min() - x_padding), float(all_x.max() + x_padding))
    y_limits = (float(all_y.min() - y_padding), float(all_y.max() + y_padding))
    fig, axes = plt.subplots(2, 3, figsize=(11, 7))
    axes_flat = axes.flatten()
    for axis, (network, frame) in zip(axes_flat, frames.items()):
        axis.scatter(frame[x_col] * 100, frame[y_col], s=12, alpha=0.65, color=color_for_dataset(network))
        if len(frame) >= 3 and frame[x_col].nunique() > 1:
            slope, intercept = np.polyfit(frame[x_col] * 100, frame[y_col], deg=1)
            xs = np.linspace(float(frame[x_col].min() * 100), float(frame[x_col].max() * 100), 50)
            axis.plot(xs, slope * xs + intercept, color=REGRESSION_LINE_COLOR, linewidth=1)
        axis.set_title(display_name(network), fontsize=9)
        axis.set_xlabel("Missing sensor-hours (%)")
        axis.set_ylabel(y_col)
        axis.set_xlim(*x_limits)
        axis.set_ylim(*y_limits)
        axis.grid(alpha=0.35, color=GRID_COLOR)
    for axis in axes_flat[len(daily_by_network) :]:
        axis.axis("off")
    fig.suptitle(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    save_plot(fig, output_path)


def plot_seasonal(seasonal: pd.DataFrame, output_path: Path) -> None:
    labels = seasonal["network"].map(display_name) + "\n" + seasonal["season"]
    setup_matplotlib()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(labels, seasonal["missingness_pct"], color=[color_for_dataset(key) for key in seasonal["network"]])
    ax.set_ylabel("Missing sensor-hours (%)")
    ax.set_title("Seasonal Missingness by Network", fontweight="bold")
    ax.tick_params(axis="x", rotation=75, labelsize=7)
    ax.grid(axis="y", alpha=0.35, color=GRID_COLOR)
    fig.tight_layout()
    save_plot(fig, output_path)


def plot_gap_histograms(gaps: pd.DataFrame, output_path: Path) -> None:
    setup_matplotlib()
    fig, axes = plt.subplots(2, 3, figsize=(11, 7))
    axes_flat = axes.flatten()
    all_durations = gaps["duration_hours"].to_numpy(dtype=float)
    bins = np.logspace(0, max(1, np.log10(max(all_durations.max(), 2))), 35)
    max_count = 0
    for network in sorted(gaps["network"].unique()):
        durations = gaps.loc[gaps["network"] == network, "duration_hours"].to_numpy(dtype=float)
        counts, _ = np.histogram(durations, bins=bins)
        max_count = max(max_count, int(counts.max()) if len(counts) else 0)
    for axis, network in zip(axes_flat, sorted(gaps["network"].unique())):
        durations = gaps.loc[gaps["network"] == network, "duration_hours"].to_numpy(dtype=float)
        axis.hist(durations, bins=bins, color=color_for_dataset(network), alpha=0.85)
        axis.set_xscale("log")
        axis.set_title(display_name(network), fontsize=9)
        axis.set_xlabel("Gap duration (hours, log scale)")
        axis.set_ylabel("Gap count")
        axis.set_xlim(float(bins[0]), float(bins[-1]))
        axis.set_ylim(0, max_count * 1.08)
        axis.grid(alpha=0.35, color=GRID_COLOR)
    for axis in axes_flat[len(gaps["network"].unique()) :]:
        axis.axis("off")
    fig.suptitle("Gap-Length Distributions", fontsize=12, fontweight="bold")
    fig.tight_layout()
    save_plot(fig, output_path)


def plot_m5_curves(curves: pd.DataFrame, value_col: str, ylabel: str, output_path: Path) -> None:
    networks = list(curves["network"].drop_duplicates())
    setup_matplotlib()
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    axes_flat = axes.flatten()
    x_max = float(curves["n"].max())
    y_min = 0.0
    y_max = float(curves[value_col].max() * 1.08)
    if value_col == "daily_fraction_days_mdape_le_10":
        y_max = 1.05
    for axis, network in zip(axes_flat, networks):
        subset = curves[curves["network"] == network]
        for scenario, scenario_frame in subset.groupby("scenario"):
            axis.plot(
                scenario_frame["n"],
                scenario_frame[value_col],
                marker="o",
                linewidth=1,
                color=SCENARIO_COLORS.get(scenario, color_for_dataset(network)),
                label=scenario,
            )
        axis.set_title(display_name(network), fontsize=9)
        axis.set_xlabel("Subset size n")
        axis.set_ylabel(ylabel)
        axis.set_xlim(0, x_max)
        axis.set_ylim(y_min, y_max)
        axis.grid(alpha=0.35, color=GRID_COLOR)
    for axis in axes_flat[len(networks) :]:
        axis.axis("off")
    axes_flat[0].legend(fontsize=6, frameon=False, loc="upper left")
    fig.tight_layout()
    save_plot(fig, output_path)


def plot_m6(m6: pd.DataFrame, output_path: Path) -> None:
    filtered = m6[m6["distance_band_km"] == 5].copy()
    filtered["label"] = filtered["network"].map(display_name) + "\n" + filtered["filter"]
    setup_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(filtered["label"], filtered["significant_positive_days_pct"], color=[color_for_dataset(key) for key in filtered["network"]])
    ax.set_ylabel("Significant positive Moran's I days (%)")
    ax.set_title("Moran's I Missingness Sensitivity at 5 km", fontweight="bold")
    ax.tick_params(axis="x", rotation=75, labelsize=7)
    ax.grid(axis="y", alpha=0.35, color=GRID_COLOR)
    fig.tight_layout()
    save_plot(fig, output_path)


def markdown_table(frame: pd.DataFrame, columns: list[str], max_rows: int = 20) -> str:
    table = frame[columns].head(max_rows).copy()
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in table.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append("" if not np.isfinite(value) else f"{value:.3g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(
    output_root: Path,
    m1_m2: pd.DataFrame,
    seasonal: pd.DataFrame,
    seasonal_tests: pd.DataFrame,
    gap_summary: pd.DataFrame,
    long_gaps: pd.DataFrame,
    m5_summary: pd.DataFrame,
    m6: pd.DataFrame,
    mc_iterations: int,
    m5_jobs: int,
) -> None:
    report_path = output_root / "missingness_analysis.md"
    m1 = m1_m2[m1_m2["analysis"] == "M1_missingness_vs_mean_concentration"]
    m2_sd = m1_m2[m1_m2["analysis"] == "M2_missingness_vs_cross_sensor_sd"]
    with report_path.open("w") as file:
        file.write("# Missingness Analysis Report\n\n")
        file.write("This report is generated from the current canonical wide PM2.5 matrices in `data/pm/`. ")
        file.write("All generated figures are written as high-resolution PNG and PDF pairs under `missingness/plots/`. ")
        file.write("The Lucknow Kakori coordinate has been corrected in `data/locations/Lucknow_sensor_locations.csv`; this does not change PM2.5 missingness calculations, but it does affect M6 spatial diagnostics.\n\n")
        file.write("## M1 — Concentration vs Missingness\n\n")
        file.write(markdown_table(m1, ["network", "n", "pearson_r", "pearson_ci_low", "pearson_ci_high", "spearman_rho"]) + "\n\n")
        file.write("![M1 scatter](plots/M1_concentration_vs_missingness.png)\n\n")
        file.write("## M2 — Variability vs Missingness\n\n")
        file.write(markdown_table(m2_sd, ["network", "n", "pearson_r", "pearson_ci_low", "pearson_ci_high", "spearman_rho"]) + "\n\n")
        file.write("![M2 SD scatter](plots/M2_sd_vs_missingness.png)\n\n")
        file.write("![M2 CV scatter](plots/M2_cv_vs_missingness.png)\n\n")
        file.write("## M3 — Seasonal Missingness\n\n")
        file.write(markdown_table(seasonal, ["network", "season", "missingness_pct", "median_sensor_uptime_pct", "days"]) + "\n\n")
        file.write(markdown_table(seasonal_tests, ["network", "winter_vs_nonwinter_ks_stat", "winter_vs_nonwinter_ks_p_approx", "chi_square_stat", "chi_square_p_approx"]) + "\n\n")
        file.write("![Seasonal missingness](plots/M3_seasonal_missingness.png)\n\n")
        file.write("## M4 — Gap-Length Characterization\n\n")
        file.write(markdown_table(gap_summary, ["network", "gap_count", "median_gap_hours", "p95_gap_hours", "max_gap_hours", "gap_gt_30d_count"]) + "\n\n")
        if not long_gaps.empty:
            file.write("### Long Gaps > 30 Days\n\n")
            file.write(markdown_table(long_gaps, ["network", "sensor_id", "start_timestamp", "end_timestamp", "duration_hours", "season_midpoint", "gap_minus_overall_network_mean"], max_rows=30) + "\n\n")
        file.write("![Gap histograms](plots/M4_gap_length_histograms.png)\n\n")
        file.write("## M5 — Completeness-Threshold Sensitivity\n\n")
        file.write(
            "This run uses Monte Carlo subsampling on the current wide matrices with "
            f"{mc_iterations:,} period iterations and {mc_iterations:,} daily iterations per n. "
        )
        file.write(f"M5 was run with `{m5_jobs}` worker process(es) across independent network-scenario tasks, using deterministic per-network-scenario seeds derived from master seed `{MASTER_SEED}`. ")
        file.write("Use lower `--mc-iterations` values only for development/screening runs.\n\n")
        file.write(markdown_table(m5_summary, ["network", "scenario", "retained_sensors", "period_required_n_mdape_le_5", "daily_required_n_95pct_days_mdape_le_10", "median_daily_valid_sensors"], max_rows=40) + "\n\n")
        file.write("![M5 period](plots/M5_period_mdape_curves.png)\n\n")
        file.write("![M5 daily](plots/M5_daily_fraction_curves.png)\n\n")
        file.write("## M6 — Moran's I Completeness Sensitivity\n\n")
        file.write("Moran's I p-values use an analytical normal approximation for a fast screening run. ")
        file.write("The final SI run should use the same table structure and may increase rigor with permutation p-values if needed.\n\n")
        file.write(markdown_table(m6, ["network", "filter", "distance_band_km", "days_evaluated", "median_moran_i", "significant_positive_days_pct"], max_rows=40) + "\n\n")
        file.write("![M6 Moran](plots/M6_morans_i_sensitivity.png)\n\n")
        file.write("## Mechanistic Interpretation\n\n")
        file.write(
            "The observed gaps are most plausibly caused by infrastructure and deployment processes "
            "rather than by PM2.5-induced sensor failure. In Dhaka and Lucknow, plausible mechanisms "
            "include power interruptions, Wi-Fi/cellular dropouts, and staggered sensor operation. "
            "Chicago has a different infrastructure and climate profile, so the relevant failure modes "
            "are expected to differ. The concentration-missingness correlations above are the direct "
            "quantitative check used to evaluate whether missingness is likely to bias the network mean.\n"
        )


def run_analysis(
    data_root: Path,
    output_root: Path,
    n_bootstrap: int,
    mc_iterations: int,
    jobs: int,
    requested_jobs: int | None = None,
) -> None:
    results_dir = output_root / "results"
    plots_dir = output_root / "plots"
    results_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(MASTER_SEED)

    panels = {config.key: load_panel(data_root, config) for config in DATASETS}
    daily_by_network = {key: panel["daily_stats"] for key, panel in panels.items()}

    correlation_records = []
    for key, panel in panels.items():
        daily = panel["daily_stats"]
        for analysis_name, y_col in [
            ("M1_missingness_vs_mean_concentration", "mean_conc"),
            ("M2_missingness_vs_cross_sensor_sd", "sd_conc"),
            ("M2_missingness_vs_cross_sensor_cv", "cv_conc"),
        ]:
            record = {
                "network": key,
                "analysis": analysis_name,
                "x": "frac_missing",
                "y": y_col,
            }
            record.update(correlation_result(daily["frac_missing"], daily[y_col], rng, n_bootstrap))
            correlation_records.append(record)
    m1_m2 = pd.DataFrame(correlation_records)
    m1_m2.to_csv(results_dir / "M1_M2_missingness_correlations.csv", index=False)

    seasonal_records = []
    seasonal_test_records = []
    for key, panel in panels.items():
        daily = panel["daily_stats"].copy()
        values = panel["values"]
        dates = panel["dates"]
        for season, season_daily in daily.groupby("season"):
            season_dates = pd.to_datetime(season_daily["date"])
            season_mask = dates.isin(season_dates)
            season_values = values.loc[season_mask.to_numpy()]
            sensor_uptime = season_values.notna().mean(axis=0) * 100
            seasonal_records.append(
                {
                    "network": key,
                    "season": season,
                    "days": int(len(season_daily)),
                    "missingness_pct": float(
                        season_daily["missing_cells"].sum()
                        / season_daily["possible_cells"].sum()
                        * 100
                    ),
                    "median_sensor_uptime_pct": float(sensor_uptime.median()),
                }
            )
        winter = daily.loc[daily["season"] == "winter", "frac_missing"].to_numpy(dtype=float)
        nonwinter = daily.loc[daily["season"] != "winter", "frac_missing"].to_numpy(dtype=float)
        ks_stat, ks_p = ks_2sample_approx(winter, nonwinter)
        by_season = daily.groupby("season")[["missing_cells", "possible_cells"]].sum()
        total_missing = by_season["missing_cells"].sum()
        expected = by_season["possible_cells"] / by_season["possible_cells"].sum() * total_missing
        chi_stat = float(((by_season["missing_cells"] - expected) ** 2 / expected).sum())
        seasonal_test_records.append(
            {
                "network": key,
                "winter_vs_nonwinter_ks_stat": ks_stat,
                "winter_vs_nonwinter_ks_p_approx": ks_p,
                "chi_square_stat": chi_stat,
                "chi_square_df": int(len(by_season) - 1),
                "chi_square_p_approx": chi_square_sf_approx(chi_stat, int(len(by_season) - 1)),
            }
        )
    seasonal = pd.DataFrame(seasonal_records)
    seasonal_tests = pd.DataFrame(seasonal_test_records)
    seasonal.to_csv(results_dir / "M3_seasonal_missingness.csv", index=False)
    seasonal_tests.to_csv(results_dir / "M3_seasonal_tests.csv", index=False)

    all_gaps = []
    gap_summaries = []
    for panel in panels.values():
        gaps, gap_summary = compute_gaps(panel)
        all_gaps.append(gaps)
        gap_summaries.append(gap_summary)
    gaps = pd.concat(all_gaps, ignore_index=True)
    gap_summary = pd.concat(gap_summaries, ignore_index=True)
    long_gaps = gaps[gaps["duration_hours"] > 30 * 24].sort_values(
        ["network", "duration_hours"], ascending=[True, False]
    )
    gaps.to_csv(results_dir / "M4_gap_lengths.csv", index=False)
    gap_summary.to_csv(results_dir / "M4_gap_summary.csv", index=False)
    long_gaps.to_csv(results_dir / "M4_long_gaps_gt_30d.csv", index=False)

    m5_seed_map = {
        key: {
            scenario_name: derive_seed("M5", key, scenario_name, mc_iterations)
            for scenario_name in SCENARIOS
        }
        for key in panels
    }
    m5_tasks = [
        (
            key,
            panel,
            gaps[gaps["network"] == key].copy(),
            scenario_name,
            scenario,
            mc_iterations,
            m5_seed_map[key][scenario_name],
        )
        for key, panel in panels.items()
        for scenario_name, scenario in SCENARIOS.items()
    ]
    m5_results: list[tuple[str, str, pd.DataFrame, pd.DataFrame]] = []
    max_workers = max(1, min(jobs, len(m5_tasks)))
    if max_workers == 1:
        for task in m5_tasks:
            m5_results.append(run_m5_worker(task))
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_m5_worker, task) for task in m5_tasks]
            for future in as_completed(futures):
                m5_results.append(future.result())
    m5_summary = (
        pd.concat([result[2] for result in m5_results], ignore_index=True)
        .sort_values(["network", "scenario"])
        .reset_index(drop=True)
    )
    m5_curve = (
        pd.concat([result[3] for result in m5_results], ignore_index=True)
        .sort_values(["network", "scenario", "n"])
        .reset_index(drop=True)
    )
    m5_summary.to_csv(results_dir / "M5_completeness_sensitivity_summary.csv", index=False)
    m5_curve.to_csv(results_dir / "M5_completeness_sensitivity_curves.csv", index=False)

    m6 = pd.concat([run_m6(data_root, panel) for panel in panels.values()], ignore_index=True)
    m6.to_csv(results_dir / "M6_morans_i_completeness_sensitivity.csv", index=False)

    plot_scatter_grid(
        daily_by_network,
        "frac_missing",
        "mean_conc",
        "M1: Daily Mean PM2.5 vs Missingness",
        plots_dir / "M1_concentration_vs_missingness.png",
    )
    plot_scatter_grid(
        daily_by_network,
        "frac_missing",
        "sd_conc",
        "M2: Cross-Sensor SD vs Missingness",
        plots_dir / "M2_sd_vs_missingness.png",
    )
    plot_scatter_grid(
        daily_by_network,
        "frac_missing",
        "cv_conc",
        "M2: Cross-Sensor CV vs Missingness",
        plots_dir / "M2_cv_vs_missingness.png",
    )
    plot_seasonal(seasonal, plots_dir / "M3_seasonal_missingness.png")
    plot_gap_histograms(gaps, plots_dir / "M4_gap_length_histograms.png")
    plot_m5_curves(m5_curve, "period_mdape_pct", "Period MdAPE (%)", plots_dir / "M5_period_mdape_curves.png")
    plot_m5_curves(
        m5_curve,
        "daily_fraction_days_mdape_le_10",
        "Fraction of days with MdAPE ≤ 10%",
        plots_dir / "M5_daily_fraction_curves.png",
    )
    plot_m6(m6, plots_dir / "M6_morans_i_sensitivity.png")

    results_bundle = {
        "metadata": {
            "data_root": str(data_root),
            "output_root": str(output_root),
            "bootstrap_iterations": n_bootstrap,
            "monte_carlo_iterations_period": mc_iterations,
            "monte_carlo_iterations_daily": mc_iterations,
            "moran_p_value_method": "analytical normal approximation",
            "master_seed": MASTER_SEED,
            "m5_task_granularity": "network_x_scenario",
            "m5_tasks": len(m5_tasks),
            "m5_worker_processes": max_workers,
            "m5_requested_jobs": jobs if requested_jobs is None else requested_jobs,
            "m5_network_scenario_seeds": m5_seed_map,
            "compute_resources": compute_resource_metadata(
                jobs if requested_jobs is None else requested_jobs,
                max_workers,
            ),
            "plot_style": "analysis/src/plot_style.py",
            "plot_output_dpi": OUTPUT_DPI,
        },
        "M1_M2": m1_m2.to_dict(orient="records"),
        "M3_seasonal_missingness": seasonal.to_dict(orient="records"),
        "M3_tests": seasonal_tests.to_dict(orient="records"),
        "M4_gap_summary": gap_summary.to_dict(orient="records"),
        "M4_long_gaps_gt_30d": long_gaps.to_dict(orient="records"),
        "M5_summary": m5_summary.to_dict(orient="records"),
        "M6_morans_i": m6.to_dict(orient="records"),
    }
    with (results_dir / "missingness_results_bundle.json").open("w") as file:
        json.dump(results_bundle, file, indent=2)
    write_report(
        output_root,
        m1_m2,
        seasonal,
        seasonal_tests,
        gap_summary,
        long_gaps,
        m5_summary,
        m6,
        mc_iterations,
        max_workers,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run missingness diagnostics and write a Markdown report.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--bootstraps", type=int, default=DEFAULT_BOOTSTRAPS)
    parser.add_argument("--mc-iterations", type=int, default=DEFAULT_MC_ITERATIONS)
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help=(
            "Parallel worker count for independent network-scenario M5 Monte Carlo tasks. "
            "Use 0 or -1 for all available CPU cores; -2 leaves one core free."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    requested_jobs = args.jobs
    args.jobs = resolve_jobs(args.jobs)
    if requested_jobs != args.jobs:
        print(f"Resolved --jobs {requested_jobs} to {args.jobs} worker process(es).")
    run_analysis(
        args.data_root,
        args.output_root,
        args.bootstraps,
        args.mc_iterations,
        args.jobs,
        requested_jobs=requested_jobs,
    )
    print(f"Wrote missingness report to {args.output_root / 'missingness_analysis.md'}")
    print(f"Wrote results under {args.output_root / 'results'}")
    print(f"Wrote plots under {args.output_root / 'plots'}")


if __name__ == "__main__":
    main()
