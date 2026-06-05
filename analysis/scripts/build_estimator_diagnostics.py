from __future__ import annotations

import argparse
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
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import (  # noqa: E402
    GRID_COLOR,
    OUTPUT_DPI,
    REFERENCE_LINE_COLOR,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


DEFAULT_RESULTS_DIR = REPO_ROOT / "analysis/results/estimator_diagnostics"
DEFAULT_PLOTS_DIR = REPO_ROOT / "analysis/plots/estimator_diagnostics"
DEFAULT_DRAWS = 10_000
DEFAULT_MASTER_SEED = 20260522
DEFAULT_QCE_SAMPLE_SIZES = (5, 10, 15, 20)
DEFAULT_COVERAGE_LEVELS = (0.68, 0.90, 0.95)
RSE_TARGET = 0.10
BONFERRONI_ALPHA = 0.05


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    city: str
    network: str
    pm_path: str
    location_path: str
    source_frequency: str
    pm_value: str
    exclude_collocated: bool = False


@dataclass(frozen=True)
class DatasetBundle:
    spec: DatasetSpec
    sensor_ids: tuple[str, ...]
    station_names: tuple[str, ...]
    daily_dates: tuple[str, ...]
    daily_values: np.ndarray
    period_values: np.ndarray
    source_timestamps: tuple[str, ...]
    source_values: np.ndarray
    input_hashes: dict[str, str]
    preprocessing: dict[str, Any]


@dataclass(frozen=True)
class QceTask:
    dataset_key: str
    sample_size: int


DATASETS: dict[str, DatasetSpec] = {
    "dhaka_lcs": DatasetSpec(
        key="dhaka_lcs",
        city="Dhaka",
        network="LCS",
        pm_path="data/pm/Dhaka_hourly_PM25.csv",
        location_path="data/locations/Dhaka_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="inherited_calibrated_pm25",
    ),
    "lucknow_lcs": DatasetSpec(
        key="lucknow_lcs",
        city="Lucknow",
        network="LCS",
        pm_path="data/pm/Lucknow_hourly_PM25.csv",
        location_path="data/locations/Lucknow_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="inherited_calibrated_pm25",
    ),
    "chicago_lcs_corrected_no_collocation": DatasetSpec(
        key="chicago_lcs_corrected_no_collocation",
        city="Chicago",
        network="LCS corrected",
        pm_path="data/pm/Chicago_LCS_corrected_daily_PM25.csv",
        location_path="data/locations/Chicago_LCS_corrected_sensor_locations.csv",
        source_frequency="official_daily",
        pm_value="corrected_pm25",
        exclude_collocated=True,
    ),
}


def repo_path(path: str | Path) -> Path:
    return REPO_ROOT / Path(path)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_seed(master_seed: int, *parts: object) -> int:
    payload = json.dumps(
        {"master_seed": master_seed, "parts": [str(part) for part in parts]},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") % (2**32)


def available_cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def resolve_jobs(requested: int) -> int:
    cpu_count = available_cpu_count()
    if requested in {0, -1}:
        return cpu_count
    if requested < -1:
        return max(1, cpu_count + requested + 1)
    return min(requested, cpu_count)


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


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


def parse_sample_sizes(value: str) -> tuple[int, ...]:
    sizes = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not sizes:
        raise argparse.ArgumentTypeError("at least one sample size is required")
    if any(size < 2 for size in sizes):
        raise argparse.ArgumentTypeError("sample sizes must be >= 2")
    return sizes


def normal_quantile(probability: float) -> float:
    return NormalDist().inv_cdf(probability)


def t_critical_cornish_fisher(confidence: float, df: int) -> float:
    """Approximate two-sided Student-t critical value.

    SciPy is intentionally not required by this repository. This Cornish-Fisher
    expansion is accurate enough for screening plots and is recorded in metadata.
    """

    if df <= 0:
        return float("nan")
    z = normal_quantile((1.0 + confidence) / 2.0)
    df_float = float(df)
    return float(
        z
        + (z**3 + z) / (4.0 * df_float)
        + (5.0 * z**5 + 16.0 * z**3 + 3.0 * z) / (96.0 * df_float**2)
        + (3.0 * z**7 + 19.0 * z**5 + 17.0 * z**3 - 15.0 * z)
        / (384.0 * df_float**3)
    )


def finite_population_correction(population_size: int, sample_size: int) -> float:
    if population_size <= 1 or sample_size >= population_size:
        return 0.0
    return math.sqrt((population_size - sample_size) / (population_size - 1))


def mask_digest(sensor_ids: tuple[str, ...], indices: np.ndarray) -> str:
    selected = [sensor_ids[int(index)] for index in indices]
    return hashlib.sha256("\0".join(selected).encode("utf-8")).hexdigest()[:16]


def read_locations(spec: DatasetSpec) -> pd.DataFrame:
    locations = pd.read_csv(repo_path(spec.location_path), dtype={"Sensor_ID": str})
    required = {"Sensor_ID", "Latitude", "Longitude"}
    missing = required.difference(locations.columns)
    if missing:
        raise ValueError(f"{spec.location_path} missing required columns: {sorted(missing)}")
    if "Station_Name" not in locations.columns:
        locations["Station_Name"] = locations["Sensor_ID"]
    if spec.exclude_collocated:
        collocated = locations["Station_Name"].astype(str).str.contains(
            "collocation", case=False, na=False
        )
        locations = locations.loc[~collocated].copy()
    locations["Sensor_ID"] = locations["Sensor_ID"].astype(str)
    return locations.drop_duplicates("Sensor_ID", keep="first").sort_values("Sensor_ID")


def read_pm_matrix(spec: DatasetSpec, sensor_ids: list[str]) -> pd.DataFrame:
    header = pd.read_csv(repo_path(spec.pm_path), nrows=0)
    timestamp_col = header.columns[0]
    available = [sensor_id for sensor_id in sensor_ids if sensor_id in header.columns]
    if not available:
        raise ValueError(f"{spec.key}: no location sensor IDs found in PM matrix")
    frame = pd.read_csv(repo_path(spec.pm_path), usecols=[timestamp_col, *available])
    frame = frame.rename(columns={timestamp_col: "Timestamp"})
    frame["Timestamp"] = frame["Timestamp"].astype(str)
    for sensor_id in available:
        frame[sensor_id] = pd.to_numeric(frame[sensor_id], errors="coerce")
    return frame


def load_dataset(spec: DatasetSpec) -> DatasetBundle:
    locations = read_locations(spec)
    location_sensor_ids = locations["Sensor_ID"].astype(str).tolist()
    pm = read_pm_matrix(spec, location_sensor_ids)
    sensor_ids = [sensor_id for sensor_id in location_sensor_ids if sensor_id in pm.columns]
    locations = locations.set_index("Sensor_ID").loc[sensor_ids].reset_index()
    values = pm[sensor_ids]
    period = values.mean(axis=0, skipna=True)
    date_labels = pm["Timestamp"].astype(str).str.slice(0, 10)
    if spec.source_frequency == "hourly":
        daily = values.groupby(date_labels, sort=True).mean()
    elif spec.source_frequency == "official_daily":
        daily = values.copy()
        daily.index = date_labels
        daily = daily.groupby(daily.index, sort=True).mean()
    else:
        raise ValueError(f"unsupported source frequency: {spec.source_frequency}")
    all_nan = daily.columns[daily.isna().all(axis=0)].tolist()
    if all_nan:
        daily = daily.drop(columns=all_nan)
        period = period.drop(index=all_nan)
        sensor_ids = [sensor_id for sensor_id in sensor_ids if sensor_id not in all_nan]
        locations = locations[locations["Sensor_ID"].isin(sensor_ids)]
        locations = locations.set_index("Sensor_ID").loc[sensor_ids].reset_index()
        values = values[sensor_ids]
    daily = daily.sort_index()
    preprocessing = {
        "source_rows": int(len(pm)),
        "source_sensor_columns": int(len(pm.columns) - 1),
        "retained_sensor_count": int(len(sensor_ids)),
        "dropped_all_nan_sensor_count": int(len(all_nan)),
        "dropped_all_nan_sensors": all_nan,
        "date_count": int(len(daily)),
        "date_min": str(daily.index.min()),
        "date_max": str(daily.index.max()),
        "source_frequency": spec.source_frequency,
        "exclude_collocated": spec.exclude_collocated,
    }
    return DatasetBundle(
        spec=spec,
        sensor_ids=tuple(sensor_ids),
        station_names=tuple(locations["Station_Name"].astype(str).tolist()),
        daily_dates=tuple(str(date) for date in daily.index.tolist()),
        daily_values=daily[sensor_ids].to_numpy(dtype=np.float64),
        period_values=period.loc[sensor_ids].to_numpy(dtype=np.float64),
        source_timestamps=tuple(pm["Timestamp"].astype(str).tolist()),
        source_values=values.to_numpy(dtype=np.float64),
        input_hashes={
            "pm_matrix": sha256_file(repo_path(spec.pm_path)),
            "locations": sha256_file(repo_path(spec.location_path)),
        },
        preprocessing=preprocessing,
    )


def draw_sample_positions(
    population_size: int,
    sample_size: int,
    draws: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    random_keys = rng.random((draws, population_size), dtype=np.float64)
    return np.argpartition(random_keys, sample_size - 1, axis=1)[:, :sample_size].astype(
        np.int32,
        copy=False,
    )


def arithmetic_interval_coverage(
    values: np.ndarray,
    sample_positions: np.ndarray,
    reference_mean: float,
    confidence: float,
) -> tuple[float, float, float]:
    sample = values[sample_positions]
    sample_size = sample.shape[1]
    population_size = len(values)
    estimates = sample.mean(axis=1)
    sample_sd = sample.std(axis=1, ddof=1)
    critical = t_critical_cornish_fisher(confidence, sample_size - 1)
    fpc = finite_population_correction(population_size, sample_size)
    half_width = critical * sample_sd / math.sqrt(sample_size) * fpc
    covered = (reference_mean >= estimates - half_width) & (reference_mean <= estimates + half_width)
    absolute_error = np.abs(estimates - reference_mean)
    return float(covered.mean()), float(np.median(absolute_error)), float(np.quantile(absolute_error, 0.95))


def lognormal_interval_coverage(
    values: np.ndarray,
    sample_positions: np.ndarray,
    reference_mean: float,
    confidence: float,
) -> tuple[float, float, float]:
    sample = values[sample_positions]
    sample = np.where(sample > 0, sample, np.nan)
    log_sample = np.log(sample)
    sample_size = sample.shape[1]
    population_size = len(values)
    log_mean = np.nanmean(log_sample, axis=1)
    log_var = np.nanvar(log_sample, axis=1, ddof=1)
    estimates = np.exp(log_mean + 0.5 * log_var)
    eta_se = np.sqrt(np.maximum(log_var / sample_size + log_var**2 / (2.0 * (sample_size - 1)), 0.0))
    eta_se = eta_se * finite_population_correction(population_size, sample_size)
    critical = t_critical_cornish_fisher(confidence, sample_size - 1)
    lower = np.exp(log_mean + 0.5 * log_var - critical * eta_se)
    upper = np.exp(log_mean + 0.5 * log_var + critical * eta_se)
    valid = np.isfinite(lower) & np.isfinite(upper) & np.isfinite(estimates)
    if not valid.any():
        return float("nan"), float("nan"), float("nan")
    covered = (reference_mean >= lower[valid]) & (reference_mean <= upper[valid])
    absolute_error = np.abs(estimates[valid] - reference_mean)
    return float(covered.mean()), float(np.median(absolute_error)), float(np.quantile(absolute_error, 0.95))


def grouped_daily_indices(bundle: DatasetBundle, sample_size: int) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    valid_masks = np.isfinite(bundle.daily_values)
    for row_index, valid_mask in enumerate(valid_masks):
        available = np.flatnonzero(valid_mask)
        if len(available) < sample_size:
            continue
        digest = mask_digest(bundle.sensor_ids, available)
        if digest not in groups:
            groups[digest] = {"available_indices": available, "row_indices": []}
        groups[digest]["row_indices"].append(row_index)
    return groups


def run_qce_task(
    task: QceTask,
    bundle: DatasetBundle,
    draws: int,
    master_seed: int,
    coverage_levels: tuple[float, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    daily_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []
    sample_size = task.sample_size

    groups = grouped_daily_indices(bundle, sample_size)
    for digest, group in groups.items():
        available = group["available_indices"]
        population_size = len(available)
        seed = derive_seed(master_seed, "qce", bundle.spec.key, "daily", sample_size, digest)
        positions = draw_sample_positions(population_size, sample_size, draws, seed)
        for row_index in group["row_indices"]:
            values = bundle.daily_values[row_index, available]
            values = values[np.isfinite(values)]
            if len(values) < sample_size:
                continue
            reference_mean = float(values.mean())
            for confidence in coverage_levels:
                for estimator_name, coverage_fn in [
                    ("arithmetic_mean_ci", arithmetic_interval_coverage),
                    ("lognormal_delta_ci", lognormal_interval_coverage),
                ]:
                    empirical, med_abs, p95_abs = coverage_fn(values, positions, reference_mean, confidence)
                    qce = abs(confidence - empirical) * 100.0 if np.isfinite(empirical) else np.nan
                    daily_rows.append(
                        {
                            "dataset_key": bundle.spec.key,
                            "city": bundle.spec.city,
                            "time_aggregation": "daily",
                            "time_index": bundle.daily_dates[row_index],
                            "sample_size": sample_size,
                            "n_sensors_available": len(values),
                            "estimator": estimator_name,
                            "nominal_coverage": confidence,
                            "empirical_coverage": empirical,
                            "qce_pct_points": qce,
                            "absolute_error_median_ugm3": med_abs,
                            "absolute_error_p95_ugm3": p95_abs,
                            "draws": draws,
                            "seed_used": seed,
                            "valid_sensor_set_hash": digest,
                        }
                    )

    available_period = np.flatnonzero(np.isfinite(bundle.period_values))
    if len(available_period) >= sample_size:
        values = bundle.period_values[available_period]
        digest = mask_digest(bundle.sensor_ids, available_period)
        seed = derive_seed(master_seed, "qce", bundle.spec.key, "period", sample_size, digest)
        positions = draw_sample_positions(len(values), sample_size, draws, seed)
        reference_mean = float(values.mean())
        for confidence in coverage_levels:
            for estimator_name, coverage_fn in [
                ("arithmetic_mean_ci", arithmetic_interval_coverage),
                ("lognormal_delta_ci", lognormal_interval_coverage),
            ]:
                empirical, med_abs, p95_abs = coverage_fn(values, positions, reference_mean, confidence)
                qce = abs(confidence - empirical) * 100.0 if np.isfinite(empirical) else np.nan
                period_rows.append(
                    {
                        "dataset_key": bundle.spec.key,
                        "city": bundle.spec.city,
                        "time_aggregation": "period",
                        "time_index": "study_period",
                        "sample_size": sample_size,
                        "n_sensors_available": len(values),
                        "estimator": estimator_name,
                        "nominal_coverage": confidence,
                        "empirical_coverage": empirical,
                        "qce_pct_points": qce,
                        "absolute_error_median_ugm3": med_abs,
                        "absolute_error_p95_ugm3": p95_abs,
                        "draws": draws,
                        "seed_used": seed,
                        "valid_sensor_set_hash": digest,
                    }
                )
    return daily_rows, period_rows


def mad_std(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan")
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return 1.4826 * mad


def required_n_normal(values: np.ndarray, robust: bool) -> float:
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return float("nan")
    if robust:
        location = float(np.median(values))
        scale = mad_std(values)
    else:
        location = float(np.mean(values))
        scale = float(np.std(values, ddof=1))
    if not np.isfinite(location) or location <= 0 or not np.isfinite(scale):
        return float("nan")
    return float(math.ceil((scale / (RSE_TARGET * location)) ** 2))


def required_n_lognormal(values: np.ndarray, robust: bool) -> float:
    values = values[np.isfinite(values) & (values > 0)]
    if len(values) < 2:
        return float("nan")
    log_values = np.log(values)
    if robust:
        scale = mad_std(log_values)
    else:
        scale = float(np.std(log_values, ddof=1))
    if not np.isfinite(scale):
        return float("nan")
    return float(math.ceil((math.exp(scale**2) - 1.0) / RSE_TARGET**2))


def build_rse_daily(bundle: DatasetBundle) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row_index, date in enumerate(bundle.daily_dates):
        values = bundle.daily_values[row_index, :]
        valid = values[np.isfinite(values)]
        if len(valid) < 2:
            continue
        row = {
            "dataset_key": bundle.spec.key,
            "city": bundle.spec.city,
            "date": date,
            "n_sensors_available": int(len(valid)),
            "daily_reference_mean_ugm3": float(np.mean(valid)),
        }
        for model, fn in [("normal", required_n_normal), ("lognormal", required_n_lognormal)]:
            for scale_name, robust in [("standard", False), ("robust_mad", True)]:
                required = fn(valid, robust)
                row[f"{model}_{scale_name}_required_n"] = required
                row[f"{model}_{scale_name}_required_n_capped"] = (
                    min(required, len(valid)) if np.isfinite(required) else np.nan
                )
                row[f"{model}_{scale_name}_exceeds_available"] = (
                    bool(required > len(valid)) if np.isfinite(required) else False
                )
        records.append(row)
    return pd.DataFrame(records)


def build_rse_exceedance(rse_daily: pd.DataFrame, max_n: int = 60) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    methods = [
        ("normal", "standard", "normal_standard_required_n"),
        ("normal", "robust_mad", "normal_robust_mad_required_n"),
        ("lognormal", "standard", "lognormal_standard_required_n"),
        ("lognormal", "robust_mad", "lognormal_robust_mad_required_n"),
    ]
    for (dataset_key, city), city_frame in rse_daily.groupby(["dataset_key", "city"], sort=False):
        n_max = min(max_n, int(city_frame["n_sensors_available"].max()))
        for n in range(1, n_max + 1):
            for model, scale_name, column in methods:
                required = city_frame[column]
                records.append(
                    {
                        "dataset_key": dataset_key,
                        "city": city,
                        "n": n,
                        "model": model,
                        "scale_estimator": scale_name,
                        "days_evaluated": int(required.notna().sum()),
                        "days_rse_gt_10pct": int((required > n).sum()),
                        "fraction_days_rse_gt_10pct": float((required > n).mean()),
                    }
                )
    return pd.DataFrame(records)


def longest_missing_gap(values: np.ndarray) -> int:
    missing = ~np.isfinite(values)
    max_gap = 0
    current = 0
    for is_missing in missing:
        if bool(is_missing):
            current += 1
            max_gap = max(max_gap, current)
        else:
            current = 0
    return max_gap


def lag1_autocorrelation(values: np.ndarray) -> float:
    finite = np.isfinite(values)
    paired = finite[:-1] & finite[1:]
    if paired.sum() < 3:
        return 0.0
    left = values[:-1][paired]
    right = values[1:][paired]
    if np.std(left) == 0 or np.std(right) == 0:
        return 0.0
    rho = float(np.corrcoef(left, right)[0, 1])
    if not np.isfinite(rho):
        return 0.0
    return float(np.clip(rho, -0.95, 0.95))


def effective_sample_size_ar1(n_observed: int, rho: float) -> float:
    if n_observed <= 1:
        return float(n_observed)
    estimate = n_observed * (1.0 - rho) / (1.0 + rho)
    return float(np.clip(estimate, 2.0, n_observed))


def build_sensor_ci(bundle: DatasetBundle) -> pd.DataFrame:
    sensor_count = len(bundle.sensor_ids)
    z_bonf = normal_quantile(1.0 - BONFERRONI_ALPHA / (2.0 * sensor_count))
    period_values = bundle.period_values
    reference_mean = float(np.nanmean(period_values))
    ci_values = bundle.daily_values
    records: list[dict[str, Any]] = []
    for idx, sensor_id in enumerate(bundle.sensor_ids):
        values = ci_values[:, idx]
        valid = values[np.isfinite(values)]
        n_observed = int(len(valid))
        mean = float(np.nanmean(values)) if n_observed else np.nan
        sd = float(np.nanstd(values, ddof=1)) if n_observed > 1 else np.nan
        rho = lag1_autocorrelation(values)
        n_eff = effective_sample_size_ar1(n_observed, rho) if n_observed > 1 else np.nan
        se = sd / math.sqrt(n_eff) if np.isfinite(sd) and np.isfinite(n_eff) and n_eff > 0 else np.nan
        half_width = z_bonf * se if np.isfinite(se) else np.nan
        longest_gap_steps = longest_missing_gap(values)
        longest_gap_days = float(longest_gap_steps)
        daily_presence = n_observed / len(values) * 100.0 if len(values) else np.nan
        ci_low = mean - half_width if np.isfinite(half_width) else np.nan
        ci_high = mean + half_width if np.isfinite(half_width) else np.nan
        records.append(
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "sensor_id": sensor_id,
                "station_name": bundle.station_names[idx],
                "period_mean_pm25_ugm3": mean,
                "reference_mean_pm25_ugm3": reference_mean,
                "mean_minus_reference_ugm3": mean - reference_mean if np.isfinite(mean) else np.nan,
                "ci_basis": "daily_sensor_means",
                "daily_means_observed": n_observed,
                "daily_presence_pct": daily_presence,
                "lag1_autocorrelation": rho,
                "ar1_effective_n": n_eff,
                "sd_pm25_ugm3": sd,
                "bonferroni_z": z_bonf,
                "ci_low_ugm3": ci_low,
                "ci_high_ugm3": ci_high,
                "ci_excludes_reference": bool(reference_mean < ci_low or reference_mean > ci_high)
                if np.isfinite(ci_low) and np.isfinite(ci_high)
                else False,
                "longest_missing_gap_days": longest_gap_days,
                "long_gap_gt_30d": bool(longest_gap_days > 30.0),
            }
        )
    frame = pd.DataFrame(records)
    frame["rank_by_period_mean"] = frame.groupby("city")["period_mean_pm25_ugm3"].rank(
        method="first"
    )
    return frame


def build_sensor_ci_summary(sensor_ci: pd.DataFrame) -> pd.DataFrame:
    records = []
    for (dataset_key, city), frame in sensor_ci.groupby(["dataset_key", "city"], sort=False):
        records.append(
            {
                "dataset_key": dataset_key,
                "city": city,
                "sensors": int(len(frame)),
                "reference_mean_pm25_ugm3": float(frame["reference_mean_pm25_ugm3"].iloc[0]),
                "sensors_ci_excludes_reference": int(frame["ci_excludes_reference"].sum()),
                "sensors_long_gap_gt_30d": int(frame["long_gap_gt_30d"].sum()),
                "median_daily_presence_pct": float(frame["daily_presence_pct"].median()),
                "median_ar1_effective_n": float(frame["ar1_effective_n"].median()),
                "max_longest_gap_days": float(frame["longest_missing_gap_days"].max()),
            }
        )
    return pd.DataFrame(records)


def metric_mapping_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "metric": "MdAPE",
                "question_answered": "What is the typical subnetwork error under random sensor selection?",
                "current_output": "F2/F3 and Monte Carlo summary",
                "interpretation": "Median absolute percentage error across Monte Carlo draws.",
            },
            {
                "metric": "95th percentile APE",
                "question_answered": "How bad is the high-error tail for random subnetworks?",
                "current_output": "F2 dashed/95Q and best-worst diagnostics",
                "interpretation": "Risk-aware upper-tail error, not a typical case.",
            },
            {
                "metric": "Absolute error (µg/m³)",
                "question_answered": "How large is the error on the exposure scale?",
                "current_output": "NEW-G1/NEW-G2",
                "interpretation": "Policy/intervention interpretability across cities with different baseline PM2.5.",
            },
            {
                "metric": "RSE",
                "question_answered": "How many sensors are needed for expected relative uncertainty under a distributional model?",
                "current_output": "SI-F6/SI-F7/SI-F8 diagnostics",
                "interpretation": "Parametric expected-error calculation; separate from Monte Carlo MdAPE.",
            },
            {
                "metric": "QCE",
                "question_answered": "Do nominal confidence intervals actually cover the reference mean?",
                "current_output": "Table 1 coverage diagnostics",
                "interpretation": "Lower values mean better interval calibration.",
            },
            {
                "metric": "Relative bias",
                "question_answered": "Does an estimator systematically over- or underestimate the reference mean?",
                "current_output": "Lognormal estimator diagnostics",
                "interpretation": "Bias-variance tradeoff for distributional estimators.",
            },
        ]
    )


def summarize_qce(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby(["dataset_key", "city", "sample_size", "estimator", "nominal_coverage"], dropna=False)
        .agg(
            days_evaluated=("time_index", "nunique"),
            median_empirical_coverage=("empirical_coverage", "median"),
            mean_empirical_coverage=("empirical_coverage", "mean"),
            median_qce_pct_points=("qce_pct_points", "median"),
            mean_qce_pct_points=("qce_pct_points", "mean"),
            p75_qce_pct_points=("qce_pct_points", lambda values: float(np.nanquantile(values, 0.75))),
            median_absolute_error_ugm3=("absolute_error_median_ugm3", "median"),
        )
        .reset_index()
    )


def save_qce_plot(summary: pd.DataFrame, plots_dir: Path) -> None:
    setup_matplotlib()
    estimators = ["arithmetic_mean_ci", "lognormal_delta_ci"]
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(
        len(estimators),
        len(cities),
        figsize=(12.5, 6.8),
        sharex=True,
        sharey=True,
    )
    for row_index, estimator in enumerate(estimators):
        for col_index, city in enumerate(cities):
            axis = axes[row_index, col_index]
            subset = summary[(summary["city"] == city) & (summary["estimator"] == estimator)]
            for confidence, conf_frame in subset.groupby("nominal_coverage"):
                axis.plot(
                    conf_frame["sample_size"],
                    conf_frame["median_qce_pct_points"],
                    marker="o",
                    linewidth=1.7,
                    label=f"{int(confidence * 100)}%",
                )
            axis.set_title(f"{city} — {estimator.replace('_', ' ')}")
            axis.grid(alpha=0.35, color=GRID_COLOR)
            if row_index == len(estimators) - 1:
                axis.set_xlabel("Sensors n")
            if col_index == 0:
                axis.set_ylabel("Median QCE (percentage points)")
    axes[0, 0].legend(title="Nominal", frameon=False, fontsize=7)
    fig.suptitle("Table 1 diagnostic: interval calibration by city and estimator", y=0.995)
    fig.tight_layout()
    save_figure(fig, plots_dir / "Table1_QCE_daily_median_by_city_estimator", dpi=OUTPUT_DPI)


def save_rse_requirement_plot(rse_daily: pd.DataFrame, plots_dir: Path, model: str, output_name: str) -> None:
    setup_matplotlib()
    cities = ["Dhaka", "Lucknow", "Chicago"]
    columns = [f"{model}_standard_required_n", f"{model}_robust_mad_required_n"]
    fig, axes = plt.subplots(3, 1, figsize=(11, 7.8), sharex=False, sharey=False)
    for axis, city in zip(axes, cities):
        subset = rse_daily[rse_daily["city"] == city].copy()
        dates = pd.to_datetime(subset["date"])
        city_values = subset[columns].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float).ravel()
        city_values = city_values[np.isfinite(city_values)]
        if len(city_values):
            central_limit = float(np.nanpercentile(city_values, 95)) * 1.15
            if city == "Chicago":
                city_limit = min(max(central_limit, 10.0), 14.0)
            else:
                city_limit = max(central_limit, 30.0)
        else:
            city_limit = 30.0
        axis.plot(
            dates,
            subset[f"{model}_standard_required_n"],
            color=color_for_dataset(subset["dataset_key"].iloc[0]),
            linewidth=1.0,
            alpha=0.8,
            label="standard scale",
        )
        axis.plot(
            dates,
            subset[f"{model}_robust_mad_required_n"],
            color="#111827",
            linewidth=1.0,
            alpha=0.85,
            label="robust MAD scale",
        )
        axis.set_title(city, loc="left", fontweight="bold")
        axis.set_ylabel("Required n")
        axis.set_ylim(0, city_limit)
        axis.grid(alpha=0.35, color=GRID_COLOR)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.015), fontsize=8)
    axes[-1].set_xlabel("Date")
    fig.suptitle(f"Sensors needed for <10% RSE under {model} assumption", y=0.985)
    fig.tight_layout(rect=[0, 0.055, 1, 0.965])
    save_figure(fig, plots_dir / output_name, dpi=OUTPUT_DPI)


def save_rse_exceedance_plot(exceedance: pd.DataFrame, plots_dir: Path) -> None:
    setup_matplotlib()
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(1, 3, figsize=(13.8, 4.8), sharex=True, sharey=True)
    method_styles = {
        ("normal", "standard"): ("Normal, standard SD", "-", "#2563eb"),
        ("normal", "robust_mad"): ("Normal, robust MAD", "--", "#2563eb"),
        ("lognormal", "standard"): ("Lognormal, standard SD", "-", "#9f1239"),
        ("lognormal", "robust_mad"): ("Lognormal, robust MAD", "--", "#9f1239"),
    }
    for axis, city in zip(axes, cities):
        subset = exceedance[exceedance["city"] == city]
        for (model, scale), (label, linestyle, color) in method_styles.items():
            frame = subset[(subset["model"] == model) & (subset["scale_estimator"] == scale)]
            axis.plot(
                frame["n"],
                frame["fraction_days_rse_gt_10pct"] * 100,
                label=label,
                linestyle=linestyle,
                color=color,
                linewidth=1.8,
            )
        axis.axhline(5, color=REFERENCE_LINE_COLOR, lw=0.8, ls=":")
        axis.axhline(50, color=REFERENCE_LINE_COLOR, lw=0.8, ls=":")
        axis.set_title(city, fontweight="bold")
        axis.set_xlim(1, 40)
        axis.set_ylim(0, 102)
        axis.grid(axis="y", alpha=0.55, color=GRID_COLOR, linewidth=0.65)
    axes[0].set_ylabel("Days exceeding 10% RSE (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.supxlabel("Candidate subnetwork size, n", y=0.14)
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.035))
    fig.subplots_adjust(left=0.07, right=0.99, top=0.91, bottom=0.24, wspace=0.05)
    save_figure(fig, plots_dir / "SI_F8_RSE_exceedance_curves", dpi=OUTPUT_DPI)


def save_sensor_ci_plot(sensor_ci: pd.DataFrame, plots_dir: Path) -> None:
    setup_matplotlib()
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(3, 1, figsize=(12, 8.5), sharex=False)
    for axis, city in zip(axes, cities):
        subset = sensor_ci[sensor_ci["city"] == city].sort_values("period_mean_pm25_ugm3").reset_index(drop=True)
        x = np.arange(1, len(subset) + 1)
        y = subset["period_mean_pm25_ugm3"].to_numpy(dtype=float)
        low = subset["ci_low_ugm3"].to_numpy(dtype=float)
        high = subset["ci_high_ugm3"].to_numpy(dtype=float)
        lower_error = np.maximum(y - low, 0)
        upper_error = np.maximum(high - y, 0)
        colors = np.where(subset["long_gap_gt_30d"].to_numpy(dtype=bool), "#dc2626", color_for_dataset(subset["dataset_key"].iloc[0]))
        axis.errorbar(
            x,
            y,
            yerr=np.vstack([lower_error, upper_error]),
            fmt="none",
            ecolor="#9ca3af",
            elinewidth=0.45,
            alpha=0.55,
            zorder=1,
        )
        axis.scatter(x, y, s=10 if city != "Chicago" else 6, c=colors, alpha=0.85, zorder=2)
        reference = float(subset["reference_mean_pm25_ugm3"].iloc[0])
        axis.axhline(reference, color="#111827", linestyle="--", linewidth=1.1, label="reference mean")
        excluded = int(subset["ci_excludes_reference"].sum())
        long_gaps = int(subset["long_gap_gt_30d"].sum())
        axis.set_title(f"{city}: {excluded} CIs exclude reference; {long_gaps} sensors have >30d gap")
        axis.set_ylabel("PM2.5 (µg/m³)")
        axis.grid(alpha=0.3, color=GRID_COLOR)
    axes[-1].set_xlabel("Sensor rank by period mean")
    legend_handles = [
        Line2D([0], [0], color="#9ca3af", lw=1.0, label="Bonferroni CI"),
        Line2D([0], [0], color="#111827", lw=1.1, linestyle="--", label="Reference mean"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#6b7280", markeredgecolor="none", markersize=5, label="Sensor mean"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#dc2626", markeredgecolor="none", markersize=5, label=">30 d gap"),
    ]
    fig.legend(legend_handles, [handle.get_label() for handle in legend_handles], loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.015))
    fig.suptitle("Sensor period means with Bonferroni-adjusted AR(1) intervals", y=0.985)
    fig.tight_layout(rect=[0, 0.08, 1, 0.955])
    save_figure(fig, plots_dir / "SI_F11_period_sensor_means_bonferroni_ci", dpi=OUTPUT_DPI)


def markdown_table(frame: pd.DataFrame, max_rows: int = 30) -> str:
    if frame.empty:
        return "_No rows._\n"
    display = frame.head(max_rows).copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    lines = ["| " + " | ".join(display.columns) + " |", "| " + " | ".join(["---"] * len(display.columns)) + " |"]
    for _, row in display.iterrows():
        lines.append("| " + " | ".join(str(value) for value in row.tolist()) + " |")
    return "\n".join(lines) + "\n"


def write_report(
    results_dir: Path,
    plots_dir: Path,
    qce_summary: pd.DataFrame,
    qce_period: pd.DataFrame,
    rse_exceedance: pd.DataFrame,
    sensor_ci_summary: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    selected_qce = qce_summary[
        (qce_summary["nominal_coverage"] == 0.95)
        & (qce_summary["sample_size"].isin([5, 10, 20]))
    ][
        [
            "city",
            "sample_size",
            "estimator",
            "days_evaluated",
            "median_empirical_coverage",
            "median_qce_pct_points",
        ]
    ].sort_values(["city", "sample_size", "estimator"])
    exceedance_n20 = rse_exceedance[
        (rse_exceedance["n"] == 20)
        & (rse_exceedance["model"].isin(["normal", "lognormal"]))
    ][["city", "model", "scale_estimator", "fraction_days_rse_gt_10pct"]].copy()
    exceedance_n20["fraction_days_rse_gt_10pct"] *= 100
    exceedance_n20 = exceedance_n20.rename(
        columns={"fraction_days_rse_gt_10pct": "days_rse_gt_10pct_pct"}
    )
    lines = [
        "# Estimator Diagnostics",
        "",
        "## Scope",
        "",
        "This report adds the missing three-city estimator diagnostics needed before final manuscript figure promotion: QCE/coverage, RSE robust-scale plots, and SI-F11 per-sensor Bonferroni CI diagnostics.",
        "",
        "## Methods Caveat",
        "",
        "- Student-t critical values use a Cornish-Fisher approximation because SciPy is not a repository dependency.",
        "- Lognormal confidence intervals use a delta-method interval for `log(mean) = log_mu + log_sigma²/2` with finite-population correction.",
        "- SI-F11 CIs use daily sensor means with an AR(1) effective-sample-size approximation, not a full GLS fit.",
        "",
        "## Selected 95% Daily QCE",
        "",
        markdown_table(selected_qce, max_rows=40),
        "",
        "## Period QCE",
        "",
        markdown_table(qce_period.sort_values(["city", "sample_size", "estimator", "nominal_coverage"]), max_rows=40),
        "",
        "## RSE Exceedance At n=20",
        "",
        markdown_table(exceedance_n20.sort_values(["city", "model", "scale_estimator"]), max_rows=40),
        "",
        "## SI-F11 City Summary",
        "",
        markdown_table(sensor_ci_summary, max_rows=10),
        "",
        "## Plot Files",
        "",
        f"- `{plots_dir / 'Table1_QCE_daily_median_by_city_estimator.png'}` and `.pdf`",
        f"- `{plots_dir / 'SI_F6_RSE_normal_daily_sensor_requirement.png'}` and `.pdf`",
        f"- `{plots_dir / 'SI_F7_RSE_lognormal_daily_sensor_requirement.png'}` and `.pdf`",
        f"- `{plots_dir / 'SI_F8_RSE_exceedance_curves.png'}` and `.pdf`",
        f"- `{plots_dir / 'SI_F11_period_sensor_means_bonferroni_ci.png'}` and `.pdf`",
        "",
        "## Metadata",
        "",
        "```json",
        json.dumps(metadata, indent=2),
        "```",
    ]
    (results_dir / "estimator_diagnostics.md").write_text("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build three-city estimator/RSE/SI-F11 diagnostics.")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--plots-dir", type=Path, default=DEFAULT_PLOTS_DIR)
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--qce-sample-sizes", type=parse_sample_sizes, default=DEFAULT_QCE_SAMPLE_SIZES)
    parser.add_argument("--jobs", type=int, default=0)
    parser.add_argument("--skip-qce", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    requested_jobs = args.jobs
    jobs = resolve_jobs(args.jobs)
    started = datetime.now().isoformat(timespec="seconds")
    start = time.perf_counter()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    args.plots_dir.mkdir(parents=True, exist_ok=True)

    bundles = {key: load_dataset(spec) for key, spec in DATASETS.items()}
    qce_daily = pd.DataFrame()
    qce_period = pd.DataFrame()
    qce_summary = pd.DataFrame()

    if not args.skip_qce:
        tasks = [
            QceTask(dataset_key=key, sample_size=sample_size)
            for key, bundle in bundles.items()
            for sample_size in args.qce_sample_sizes
            if sample_size <= len(bundle.sensor_ids)
        ]
        daily_frames: list[pd.DataFrame] = []
        period_frames: list[pd.DataFrame] = []
        max_workers = min(jobs, len(tasks)) if tasks else 1
        if max_workers == 1:
            for task in tasks:
                daily_rows, period_rows = run_qce_task(
                    task,
                    bundles[task.dataset_key],
                    args.draws,
                    args.master_seed,
                    DEFAULT_COVERAGE_LEVELS,
                )
                daily_frames.append(pd.DataFrame(daily_rows))
                period_frames.append(pd.DataFrame(period_rows))
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        run_qce_task,
                        task,
                        bundles[task.dataset_key],
                        args.draws,
                        args.master_seed,
                        DEFAULT_COVERAGE_LEVELS,
                    ): task
                    for task in tasks
                }
                for completed, future in enumerate(as_completed(futures), start=1):
                    task = futures[future]
                    daily_rows, period_rows = future.result()
                    daily_frames.append(pd.DataFrame(daily_rows))
                    period_frames.append(pd.DataFrame(period_rows))
                    print(
                        f"[{completed:>2}/{len(tasks)}] QCE {task.dataset_key} n={task.sample_size} "
                        f"daily_rows={sum(len(frame) for frame in daily_frames):,}"
                    )
        qce_daily = pd.concat(daily_frames, ignore_index=True)
        qce_period = pd.concat(period_frames, ignore_index=True)
        qce_summary = summarize_qce(qce_daily)
        qce_daily.to_csv(args.results_dir / "qce_daily_by_day.csv", index=False)
        qce_period.to_csv(args.results_dir / "qce_period_summary.csv", index=False)
        qce_summary.to_csv(args.results_dir / "qce_daily_summary.csv", index=False)
        save_qce_plot(qce_summary, args.plots_dir)

    rse_daily = pd.concat([build_rse_daily(bundle) for bundle in bundles.values()], ignore_index=True)
    rse_exceedance = build_rse_exceedance(rse_daily)
    rse_daily.to_csv(args.results_dir / "rse_daily_sensor_requirements.csv", index=False)
    rse_exceedance.to_csv(args.results_dir / "rse_exceedance_summary.csv", index=False)
    save_rse_requirement_plot(rse_daily, args.plots_dir, "normal", "SI_F6_RSE_normal_daily_sensor_requirement")
    save_rse_requirement_plot(rse_daily, args.plots_dir, "lognormal", "SI_F7_RSE_lognormal_daily_sensor_requirement")
    save_rse_exceedance_plot(rse_exceedance, args.plots_dir)

    sensor_ci = pd.concat([build_sensor_ci(bundle) for bundle in bundles.values()], ignore_index=True)
    sensor_ci_summary = build_sensor_ci_summary(sensor_ci)
    sensor_ci.to_csv(args.results_dir / "si_f11_sensor_period_ci.csv", index=False)
    sensor_ci_summary.to_csv(args.results_dir / "si_f11_city_summary.csv", index=False)
    save_sensor_ci_plot(sensor_ci, args.plots_dir)

    metric_table = metric_mapping_table()
    metric_table.to_csv(args.results_dir / "metric_to_question_mapping.csv", index=False)

    duration = time.perf_counter() - start
    metadata = {
        "created_at": started,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_seconds": duration,
        "draws": args.draws,
        "master_seed": args.master_seed,
        "qce_sample_sizes": list(args.qce_sample_sizes),
        "coverage_levels": list(DEFAULT_COVERAGE_LEVELS),
        "rse_target": RSE_TARGET,
        "bonferroni_alpha": BONFERRONI_ALPHA,
        "requested_jobs": requested_jobs,
        "effective_jobs": jobs,
        "compute_resources": compute_resource_metadata(requested_jobs, jobs),
        "critical_value_method": "Cornish-Fisher Student-t approximation",
        "lognormal_ci_method": "delta method on lognormal mean with finite-population correction",
        "si_f11_ci_method": "Bonferroni normal critical value on daily sensor means with AR(1) effective sample size",
        "datasets": {
            key: {
                "spec": asdict(bundle.spec),
                "input_hashes": bundle.input_hashes,
                "preprocessing": bundle.preprocessing,
            }
            for key, bundle in bundles.items()
        },
        "git_commit": git_value(["rev-parse", "HEAD"]),
    }
    (args.results_dir / "estimator_diagnostics_metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str)
    )
    write_report(
        args.results_dir,
        args.plots_dir,
        qce_summary,
        qce_period,
        rse_exceedance,
        sensor_ci_summary,
        metadata,
    )
    print(f"Wrote estimator diagnostics to {display_path(args.results_dir)}")
    print(f"Wrote plots to {display_path(args.plots_dir)}")
    print(f"Duration: {duration:.1f} seconds")


if __name__ == "__main__":
    main()
