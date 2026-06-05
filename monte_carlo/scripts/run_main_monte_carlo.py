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
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "monte_carlo/results/runs"
DEFAULT_MASTER_SEED = 20260522
DEFAULT_DRAWS = 10_000
DEFAULT_TOP_K = 5
DEFAULT_MAX_N = 30
SCENARIO_ID = "S0_baseline"
PLACEMENT = "random_srswor"
ESTIMATOR = "arithmetic_mean"


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
    role: str = "main"


@dataclass(frozen=True)
class DatasetBundle:
    spec: DatasetSpec
    sensor_ids: tuple[str, ...]
    station_names: tuple[str, ...]
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    daily_dates: tuple[str, ...]
    daily_values: np.ndarray
    period_values: np.ndarray
    valid_hour_counts: np.ndarray | None
    input_hashes: dict[str, str]
    preprocessing: dict[str, Any]


@dataclass(frozen=True)
class MonteCarloTask:
    dataset_key: str
    time_aggregation: str
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
    "lucknow_madhwal_lcs": DatasetSpec(
        key="lucknow_madhwal_lcs",
        city="Lucknow",
        network="LCS Madhwal validation",
        pm_path="data/pm/Lucknow_Madhwal_hourly_PM25.csv",
        location_path="data/locations/Lucknow_Madhwal_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="madhwal_validation_calibrated_pm25",
        role="sensitivity",
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
    "chicago_lcs_corrected_all": DatasetSpec(
        key="chicago_lcs_corrected_all",
        city="Chicago",
        network="LCS corrected",
        pm_path="data/pm/Chicago_LCS_corrected_daily_PM25.csv",
        location_path="data/locations/Chicago_LCS_corrected_sensor_locations.csv",
        source_frequency="official_daily",
        pm_value="corrected_pm25",
        role="sensitivity",
    ),
    "chicago_lcs_raw_no_collocation": DatasetSpec(
        key="chicago_lcs_raw_no_collocation",
        city="Chicago",
        network="LCS raw",
        pm_path="data/pm/Chicago_LCS_raw_daily_PM25.csv",
        location_path="data/locations/Chicago_LCS_raw_sensor_locations.csv",
        source_frequency="official_daily",
        pm_value="raw_pm25",
        exclude_collocated=True,
        role="sensitivity",
    ),
    "chicago_lcs_raw_all": DatasetSpec(
        key="chicago_lcs_raw_all",
        city="Chicago",
        network="LCS raw",
        pm_path="data/pm/Chicago_LCS_raw_daily_PM25.csv",
        location_path="data/locations/Chicago_LCS_raw_sensor_locations.csv",
        source_frequency="official_daily",
        pm_value="raw_pm25",
        role="sensitivity",
    ),
    "chicago_aqs": DatasetSpec(
        key="chicago_aqs",
        city="Chicago",
        network="AQS",
        pm_path="data/pm/Chicago_AQS_daily_PM25.csv",
        location_path="data/locations/Chicago_AQS_sensor_locations.csv",
        source_frequency="official_daily",
        pm_value="aqs_pm25",
        role="reference_context",
    ),
}


def repo_path(path: str | Path) -> Path:
    return REPO_ROOT / Path(path)


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


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def release_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return "<outside-repository>"


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


def resolve_n_jobs(requested: int) -> int:
    cpu_count = available_cpu_count()
    if requested in {0, -1}:
        return cpu_count
    if requested < -1:
        return max(1, cpu_count + requested + 1)
    return min(requested, cpu_count)


def compute_resource_metadata() -> dict[str, Any]:
    memory_bytes = total_memory_bytes()
    memory_gb = memory_bytes / 1024**3 if memory_bytes is not None else None
    return {
        "available_cpu_count": available_cpu_count(),
        "total_memory_gb": round(memory_gb, 3) if memory_gb is not None else None,
        "blas_thread_environment": {
            name: os.environ.get(name)
            for name in BLAS_THREAD_ENV_VARS
        },
        "blas_thread_policy": "one BLAS/native thread per worker process to avoid oversubscription",
    }


def parse_dataset_keys(value: str) -> list[str]:
    keys = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [key for key in keys if key not in DATASETS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown dataset key(s): {', '.join(unknown)}; choices: {', '.join(DATASETS)}"
        )
    return keys


def timestamp_dates(timestamp_series: pd.Series) -> pd.Series:
    return timestamp_series.astype(str).str.slice(0, 10)


def load_locations(spec: DatasetSpec) -> pd.DataFrame:
    locations = pd.read_csv(repo_path(spec.location_path), dtype={"Sensor_ID": str})
    required = {"Sensor_ID", "Latitude", "Longitude"}
    missing = required.difference(locations.columns)
    if missing:
        raise ValueError(f"{spec.location_path} missing columns: {sorted(missing)}")
    if "Station_Name" not in locations.columns:
        locations["Station_Name"] = locations["Sensor_ID"]
    if spec.exclude_collocated:
        collocated = locations["Station_Name"].astype(str).str.contains(
            "collocation", case=False, na=False
        )
        locations = locations.loc[~collocated].copy()
    locations["Sensor_ID"] = locations["Sensor_ID"].astype(str)
    locations = locations.drop_duplicates(subset=["Sensor_ID"], keep="first")
    return locations.sort_values("Sensor_ID").reset_index(drop=True)


def load_pm_matrix(spec: DatasetSpec, sensor_ids: list[str]) -> pd.DataFrame:
    pm_path = repo_path(spec.pm_path)
    header = pd.read_csv(pm_path, nrows=0)
    timestamp_column = header.columns[0]
    available_sensors = [sensor_id for sensor_id in sensor_ids if sensor_id in header.columns]
    if not available_sensors:
        raise ValueError(f"{spec.key} has no sensor columns in {spec.pm_path}")
    frame = pd.read_csv(pm_path, usecols=[timestamp_column, *available_sensors])
    frame = frame.rename(columns={timestamp_column: "Timestamp"})
    frame["Timestamp"] = frame["Timestamp"].astype(str)
    for sensor_id in available_sensors:
        frame[sensor_id] = pd.to_numeric(frame[sensor_id], errors="coerce")
    return frame


def load_dataset(spec: DatasetSpec) -> DatasetBundle:
    locations = load_locations(spec)
    location_sensor_ids = locations["Sensor_ID"].astype(str).tolist()
    pm_matrix = load_pm_matrix(spec, location_sensor_ids)
    sensor_ids = [sensor_id for sensor_id in location_sensor_ids if sensor_id in pm_matrix.columns]
    locations = locations[locations["Sensor_ID"].isin(sensor_ids)].copy()
    locations = locations.set_index("Sensor_ID").loc[sensor_ids].reset_index()

    values = pm_matrix[sensor_ids]
    period_values_by_sensor = values.mean(axis=0, skipna=True)
    date_labels = timestamp_dates(pm_matrix["Timestamp"])
    if spec.source_frequency == "hourly":
        daily = values.groupby(date_labels, sort=True).mean()
        valid_hour_counts = values.notna().groupby(date_labels, sort=True).sum()
        valid_hour_array: np.ndarray | None = valid_hour_counts.to_numpy(dtype=np.int16)
    elif spec.source_frequency == "official_daily":
        daily = values.copy()
        daily.index = date_labels
        daily = daily.groupby(daily.index, sort=True).mean()
        valid_hour_array = None
    else:
        raise ValueError(f"unsupported source frequency: {spec.source_frequency}")

    all_nan_columns = daily.columns[daily.isna().all(axis=0)].tolist()
    if all_nan_columns:
        daily = daily.drop(columns=all_nan_columns)
        period_values_by_sensor = period_values_by_sensor.drop(index=all_nan_columns)
        sensor_ids = [sensor_id for sensor_id in sensor_ids if sensor_id not in all_nan_columns]
        locations = locations[locations["Sensor_ID"].isin(sensor_ids)].copy()
        locations = locations.set_index("Sensor_ID").loc[sensor_ids].reset_index()
        if valid_hour_array is not None:
            valid_hour_counts = valid_hour_counts.drop(columns=all_nan_columns)
            valid_hour_array = valid_hour_counts.to_numpy(dtype=np.int16)

    daily = daily.sort_index()
    daily_values = daily.to_numpy(dtype=np.float64)
    preprocessing = {
        "source_rows": int(len(pm_matrix)),
        "source_sensor_columns": int(len(pm_matrix.columns) - 1),
        "retained_sensor_count": int(len(sensor_ids)),
        "dropped_all_nan_sensor_count": int(len(all_nan_columns)),
        "dropped_all_nan_sensors": all_nan_columns,
        "date_count": int(len(daily.index)),
        "date_min": str(daily.index.min()),
        "date_max": str(daily.index.max()),
        "source_frequency": spec.source_frequency,
        "exclude_collocated": spec.exclude_collocated,
    }
    return DatasetBundle(
        spec=spec,
        sensor_ids=tuple(sensor_ids),
        station_names=tuple(locations["Station_Name"].astype(str).tolist()),
        latitudes=tuple(pd.to_numeric(locations["Latitude"], errors="coerce").astype(float)),
        longitudes=tuple(pd.to_numeric(locations["Longitude"], errors="coerce").astype(float)),
        daily_dates=tuple(str(date) for date in daily.index.tolist()),
        daily_values=daily_values,
        period_values=period_values_by_sensor.loc[list(daily.columns)].to_numpy(dtype=np.float64),
        valid_hour_counts=valid_hour_array,
        input_hashes={
            "pm_matrix": sha256_file(repo_path(spec.pm_path)),
            "locations": sha256_file(repo_path(spec.location_path)),
        },
        preprocessing=preprocessing,
    )


def finite_population_correction(population_size: int, sample_size: int) -> float:
    if population_size <= 1 or sample_size >= population_size:
        return 0.0
    return math.sqrt((population_size - sample_size) / (population_size - 1))


def summarize_estimates(
    sample_estimates: np.ndarray,
    reference_mean: float,
    reference_sd: float,
    sample_size: int,
    population_size: int,
) -> dict[str, float]:
    absolute_errors = np.abs(sample_estimates - reference_mean)
    if reference_mean == 0 or not np.isfinite(reference_mean):
        percentage_errors = np.full_like(absolute_errors, np.nan, dtype=np.float64)
    else:
        percentage_errors = absolute_errors / abs(reference_mean) * 100.0
    ape_quantiles = np.nanquantile(percentage_errors, [0.25, 0.5, 0.75, 0.95])
    abs_quantiles = np.nanquantile(absolute_errors, [0.25, 0.5, 0.75, 0.95])
    fpc = finite_population_correction(population_size, sample_size)
    rse_normal = np.nan
    if reference_mean != 0 and np.isfinite(reference_sd):
        rse_normal = reference_sd / math.sqrt(sample_size) * fpc / abs(reference_mean) * 100.0
    positive_estimates = sample_estimates[sample_estimates > 0]
    rse_lognormal = np.nan
    if len(positive_estimates) > 1:
        log_sd = float(np.nanstd(np.log(positive_estimates), ddof=1))
        rse_lognormal = math.sqrt(max(math.exp(log_sd**2) - 1.0, 0.0)) * fpc * 100.0
    estimate_quantiles = np.nanquantile(sample_estimates, [0.25, 0.5, 0.75, 0.95])
    bias_ugm3 = float(np.nanmean(sample_estimates) - reference_mean)
    bias_pct = np.nan
    if reference_mean != 0 and np.isfinite(reference_mean):
        bias_pct = bias_ugm3 / reference_mean * 100.0
    return {
        "ape_mean_pct": float(np.nanmean(percentage_errors)),
        "ape_p25_pct": float(ape_quantiles[0]),
        "ape_median_pct": float(ape_quantiles[1]),
        "ape_p75_pct": float(ape_quantiles[2]),
        "ape_p95_pct": float(ape_quantiles[3]),
        "ape_min_pct": float(np.nanmin(percentage_errors)),
        "ape_max_pct": float(np.nanmax(percentage_errors)),
        "absolute_error_mean_ugm3": float(np.nanmean(absolute_errors)),
        "absolute_error_p25_ugm3": float(abs_quantiles[0]),
        "absolute_error_median_ugm3": float(abs_quantiles[1]),
        "absolute_error_p75_ugm3": float(abs_quantiles[2]),
        "absolute_error_p95_ugm3": float(abs_quantiles[3]),
        "absolute_error_min_ugm3": float(np.nanmin(absolute_errors)),
        "absolute_error_max_ugm3": float(np.nanmax(absolute_errors)),
        "subnet_mean_mean_ugm3": float(np.nanmean(sample_estimates)),
        "subnet_mean_p25_ugm3": float(estimate_quantiles[0]),
        "subnet_mean_median_ugm3": float(estimate_quantiles[1]),
        "subnet_mean_p75_ugm3": float(estimate_quantiles[2]),
        "subnet_mean_p95_ugm3": float(estimate_quantiles[3]),
        "subnet_mean_sd_ugm3": float(np.nanstd(sample_estimates, ddof=1)),
        "bias_ugm3": bias_ugm3,
        "bias_pct": float(bias_pct) if np.isfinite(bias_pct) else np.nan,
        "rse_normal_pct": float(rse_normal) if np.isfinite(rse_normal) else np.nan,
        "rse_lognormal_pct": float(rse_lognormal) if np.isfinite(rse_lognormal) else np.nan,
    }


def haversine_distances_km(latitudes: np.ndarray, longitudes: np.ndarray) -> np.ndarray:
    if len(latitudes) < 2:
        return np.array([], dtype=np.float64)
    lat_rad = np.radians(latitudes)
    lon_rad = np.radians(longitudes)
    distances: list[float] = []
    for i in range(len(latitudes) - 1):
        dlat = lat_rad[i + 1 :] - lat_rad[i]
        dlon = lon_rad[i + 1 :] - lon_rad[i]
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat_rad[i]) * np.cos(lat_rad[i + 1 :]) * (
            np.sin(dlon / 2.0) ** 2
        )
        distances.extend((6371.0088 * 2.0 * np.arcsin(np.sqrt(a))).tolist())
    return np.asarray(distances, dtype=np.float64)


def draw_sample_positions(
    population_size: int,
    sample_size: int,
    draws: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    random_keys = rng.random((draws, population_size), dtype=np.float64)
    positions = np.argpartition(random_keys, sample_size - 1, axis=1)[:, :sample_size]
    return positions.astype(np.int32, copy=False)


def compute_sample_estimates(values: np.ndarray, sample_positions: np.ndarray) -> np.ndarray:
    return values[sample_positions].mean(axis=1)


def base_summary_row(
    bundle: DatasetBundle,
    time_aggregation: str,
    time_index: str,
    sample_size: int,
    population_size: int,
    draws: int,
    seed_used: int,
    reference_mean: float,
    reference_sd: float,
    runtime_ms: float,
    mask_digest: str,
) -> dict[str, Any]:
    return {
        "dataset_key": bundle.spec.key,
        "city": bundle.spec.city,
        "network": bundle.spec.network,
        "scenario": SCENARIO_ID,
        "estimator": ESTIMATOR,
        "placement": PLACEMENT,
        "time_aggregation": time_aggregation,
        "time_index": time_index,
        "sample_size": sample_size,
        "n_sensors_available": population_size,
        "n_draws_requested": draws,
        "n_draws_completed": draws,
        "reference_mean_ugm3": reference_mean,
        "reference_sd_ugm3": reference_sd,
        "seed_used": seed_used,
        "seed_scope": "valid_sensor_set",
        "valid_sensor_set_hash": mask_digest,
        "runtime_ms": runtime_ms,
        "pm_value": bundle.spec.pm_value,
        "source_frequency": bundle.spec.source_frequency,
        "exclude_collocated": bundle.spec.exclude_collocated,
    }


def selected_extreme_indices(apes: np.ndarray, top_k: int) -> list[tuple[str, int, int]]:
    finite_order = np.argsort(np.nan_to_num(apes, nan=np.inf))
    finite_desc = finite_order[::-1]
    selected: list[tuple[str, int, int]] = []
    for rank, draw_index in enumerate(finite_order[:top_k], start=1):
        selected.append(("best", rank, int(draw_index)))
    for rank, draw_index in enumerate(finite_desc[:top_k], start=1):
        selected.append(("worst", rank, int(draw_index)))
    median_ape = float(np.nanmedian(apes))
    p95_ape = float(np.nanquantile(apes, 0.95))
    typical_index = int(np.nanargmin(np.abs(apes - median_ape)))
    p95_index = int(np.nanargmin(np.abs(apes - p95_ape)))
    selected.append(("typical_median", 1, typical_index))
    selected.append(("p95_representative", 1, p95_index))
    return selected


def extreme_rows(
    bundle: DatasetBundle,
    time_aggregation: str,
    time_index: str,
    sample_size: int,
    population_size: int,
    reference_mean: float,
    seed_used: int,
    mask_digest: str,
    available_global_indices: np.ndarray,
    sample_positions: np.ndarray,
    sample_estimates: np.ndarray,
    top_k: int,
) -> list[dict[str, Any]]:
    if reference_mean == 0 or not np.isfinite(reference_mean):
        apes = np.full(sample_estimates.shape, np.nan, dtype=np.float64)
    else:
        apes = np.abs(sample_estimates - reference_mean) / abs(reference_mean) * 100.0
    absolute_errors = np.abs(sample_estimates - reference_mean)
    sensor_ids = np.asarray(bundle.sensor_ids, dtype=object)
    station_names = np.asarray(bundle.station_names, dtype=object)
    latitudes = np.asarray(bundle.latitudes, dtype=np.float64)
    longitudes = np.asarray(bundle.longitudes, dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for extreme_type, rank, draw_index in selected_extreme_indices(apes, top_k):
        selected_global_indices = available_global_indices[sample_positions[draw_index]]
        selected_latitudes = latitudes[selected_global_indices]
        selected_longitudes = longitudes[selected_global_indices]
        distances = haversine_distances_km(selected_latitudes, selected_longitudes)
        rows.append(
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "network": bundle.spec.network,
                "scenario": SCENARIO_ID,
                "estimator": ESTIMATOR,
                "placement": PLACEMENT,
                "time_aggregation": time_aggregation,
                "time_index": time_index,
                "sample_size": sample_size,
                "n_sensors_available": population_size,
                "extreme_type": extreme_type,
                "rank": rank,
                "draw_index": draw_index,
                "seed_used": seed_used,
                "seed_scope": "valid_sensor_set",
                "valid_sensor_set_hash": mask_digest,
                "sensor_indices": json.dumps(selected_global_indices.astype(int).tolist()),
                "sensor_ids": json.dumps(sensor_ids[selected_global_indices].tolist()),
                "station_names": json.dumps(station_names[selected_global_indices].tolist()),
                "subnet_mean_ugm3": float(sample_estimates[draw_index]),
                "reference_mean_ugm3": float(reference_mean),
                "ape_pct": float(apes[draw_index]),
                "absolute_error_ugm3": float(absolute_errors[draw_index]),
                "centroid_lat": float(np.nanmean(selected_latitudes)),
                "centroid_lon": float(np.nanmean(selected_longitudes)),
                "mean_pairwise_distance_km": float(np.nanmean(distances))
                if len(distances)
                else np.nan,
                "min_pairwise_distance_km": float(np.nanmin(distances))
                if len(distances)
                else np.nan,
            }
        )
    return rows


def mask_hash(sensor_ids: tuple[str, ...], global_indices: np.ndarray) -> str:
    selected_ids = [sensor_ids[int(index)] for index in global_indices]
    return hashlib.sha256("\0".join(selected_ids).encode("utf-8")).hexdigest()[:16]


def run_period_task(
    task: MonteCarloTask,
    bundle: DatasetBundle,
    draws: int,
    top_k: int,
    master_seed: int,
    run_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    start = time.perf_counter()
    period_values = bundle.period_values
    available_global_indices = np.flatnonzero(np.isfinite(period_values))
    if task.sample_size > len(available_global_indices):
        return [], [], []
    values = period_values[available_global_indices]
    population_size = len(values)
    reference_mean = float(np.nanmean(values))
    reference_sd = float(np.nanstd(values, ddof=1)) if population_size > 1 else np.nan
    digest = mask_hash(bundle.sensor_ids, available_global_indices)
    seed = derive_seed(
        master_seed,
        run_id,
        bundle.spec.key,
        SCENARIO_ID,
        ESTIMATOR,
        PLACEMENT,
        "period",
        task.sample_size,
        digest,
    )
    sample_positions = draw_sample_positions(population_size, task.sample_size, draws, seed)
    sample_estimates = compute_sample_estimates(values, sample_positions)
    runtime_ms = (time.perf_counter() - start) * 1000.0
    row = base_summary_row(
        bundle=bundle,
        time_aggregation="period",
        time_index="study_period",
        sample_size=task.sample_size,
        population_size=population_size,
        draws=draws,
        seed_used=seed,
        reference_mean=reference_mean,
        reference_sd=reference_sd,
        runtime_ms=runtime_ms,
        mask_digest=digest,
    )
    row.update(
        summarize_estimates(
            sample_estimates=sample_estimates,
            reference_mean=reference_mean,
            reference_sd=reference_sd,
            sample_size=task.sample_size,
            population_size=population_size,
        )
    )
    seeds = [
        {
            "dataset_key": bundle.spec.key,
            "time_aggregation": "period",
            "time_index": "study_period",
            "sample_size": task.sample_size,
            "valid_sensor_set_hash": digest,
            "seed_used": seed,
        }
    ]
    extremes = extreme_rows(
        bundle=bundle,
        time_aggregation="period",
        time_index="study_period",
        sample_size=task.sample_size,
        population_size=population_size,
        reference_mean=reference_mean,
        seed_used=seed,
        mask_digest=digest,
        available_global_indices=available_global_indices,
        sample_positions=sample_positions,
        sample_estimates=sample_estimates,
        top_k=top_k,
    )
    return [row], extremes, seeds


def grouped_daily_indices(bundle: DatasetBundle, sample_size: int) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    valid_masks = np.isfinite(bundle.daily_values)
    for row_index, valid_mask in enumerate(valid_masks):
        available_global_indices = np.flatnonzero(valid_mask)
        if sample_size > len(available_global_indices):
            continue
        digest = mask_hash(bundle.sensor_ids, available_global_indices)
        if digest not in groups:
            groups[digest] = {
                "available_global_indices": available_global_indices,
                "row_indices": [],
            }
        groups[digest]["row_indices"].append(row_index)
    return groups


def run_daily_task(
    task: MonteCarloTask,
    bundle: DatasetBundle,
    draws: int,
    top_k: int,
    master_seed: int,
    run_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    all_summaries: list[dict[str, Any]] = []
    all_extremes: list[dict[str, Any]] = []
    all_seeds: list[dict[str, Any]] = []
    groups = grouped_daily_indices(bundle, task.sample_size)
    for digest, group in groups.items():
        available_global_indices = group["available_global_indices"]
        population_size = len(available_global_indices)
        seed = derive_seed(
            master_seed,
            run_id,
            bundle.spec.key,
            SCENARIO_ID,
            ESTIMATOR,
            PLACEMENT,
            "daily",
            task.sample_size,
            digest,
        )
        draw_start = time.perf_counter()
        sample_positions = draw_sample_positions(population_size, task.sample_size, draws, seed)
        draw_runtime_ms = (time.perf_counter() - draw_start) * 1000.0
        all_seeds.append(
            {
                "dataset_key": bundle.spec.key,
                "time_aggregation": "daily",
                "time_index": "valid_sensor_set",
                "sample_size": task.sample_size,
                "valid_sensor_set_hash": digest,
                "seed_used": seed,
                "date_count_reusing_seed": len(group["row_indices"]),
            }
        )
        for row_index in group["row_indices"]:
            start = time.perf_counter()
            values = bundle.daily_values[row_index, available_global_indices]
            reference_mean = float(np.nanmean(values))
            reference_sd = float(np.nanstd(values, ddof=1)) if population_size > 1 else np.nan
            sample_estimates = compute_sample_estimates(values, sample_positions)
            runtime_ms = (time.perf_counter() - start) * 1000.0 + draw_runtime_ms / max(
                len(group["row_indices"]), 1
            )
            time_index = bundle.daily_dates[row_index]
            row = base_summary_row(
                bundle=bundle,
                time_aggregation="daily",
                time_index=time_index,
                sample_size=task.sample_size,
                population_size=population_size,
                draws=draws,
                seed_used=seed,
                reference_mean=reference_mean,
                reference_sd=reference_sd,
                runtime_ms=runtime_ms,
                mask_digest=digest,
            )
            row.update(
                summarize_estimates(
                    sample_estimates=sample_estimates,
                    reference_mean=reference_mean,
                    reference_sd=reference_sd,
                    sample_size=task.sample_size,
                    population_size=population_size,
                )
            )
            all_summaries.append(row)
            all_extremes.extend(
                extreme_rows(
                    bundle=bundle,
                    time_aggregation="daily",
                    time_index=time_index,
                    sample_size=task.sample_size,
                    population_size=population_size,
                    reference_mean=reference_mean,
                    seed_used=seed,
                    mask_digest=digest,
                    available_global_indices=available_global_indices,
                    sample_positions=sample_positions,
                    sample_estimates=sample_estimates,
                    top_k=top_k,
                )
            )
    return all_summaries, all_extremes, all_seeds


def run_task(
    task: MonteCarloTask,
    bundle: DatasetBundle,
    draws: int,
    top_k: int,
    master_seed: int,
    run_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if task.time_aggregation == "period":
        return run_period_task(task, bundle, draws, top_k, master_seed, run_id)
    if task.time_aggregation == "daily":
        return run_daily_task(task, bundle, draws, top_k, master_seed, run_id)
    raise ValueError(f"unsupported aggregation: {task.time_aggregation}")


def write_preprocessed(bundle: DatasetBundle, output_dir: Path) -> None:
    daily = pd.DataFrame(
        bundle.daily_values,
        index=pd.Index(bundle.daily_dates, name="date"),
        columns=bundle.sensor_ids,
    )
    daily.reset_index().to_parquet(
        output_dir / f"{bundle.spec.key}_daily_sensor_means.parquet", index=False
    )
    sensors = pd.DataFrame(
        {
            "Sensor_ID": bundle.sensor_ids,
            "Station_Name": bundle.station_names,
            "Latitude": bundle.latitudes,
            "Longitude": bundle.longitudes,
        }
    )
    sensors.to_csv(output_dir / f"{bundle.spec.key}_sensor_inventory.csv", index=False)


def write_outputs(
    run_dir: Path,
    summary_rows: list[dict[str, Any]],
    extreme_rows_data: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
) -> None:
    summary_dir = run_dir / "mc_summary"
    extremes_dir = run_dir / "mc_extremes"
    config_dir = run_dir / "config"
    summary_dir.mkdir(parents=True, exist_ok=True)
    extremes_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(summary_rows)
    extremes = pd.DataFrame(extreme_rows_data)
    seeds = pd.DataFrame(seed_rows).drop_duplicates()
    summary.to_parquet(summary_dir / "p0_baseline_summary.parquet", index=False)
    summary.to_csv(summary_dir / "p0_baseline_summary.csv", index=False)
    extremes.to_parquet(extremes_dir / "p0_baseline_extremes.parquet", index=False)
    extremes.to_csv(extremes_dir / "p0_baseline_extremes.csv", index=False)
    seeds.to_json(config_dir / "seeds.json", orient="records", indent=2)


def write_validation_report(
    run_dir: Path,
    summary: pd.DataFrame,
    bundles: dict[str, DatasetBundle],
    args: argparse.Namespace,
) -> None:
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Monte Carlo Validation Report", ""]
    lines.append(f"- Run ID: `{run_dir.name}`")
    lines.append(f"- Draws per task: `{args.draws}`")
    lines.append(f"- Master seed: `{args.master_seed}`")
    lines.append(f"- Dataset keys: `{', '.join(args.dataset_keys)}`")
    lines.append(f"- Summary rows: `{len(summary)}`")
    lines.append("")
    lines.append("## Dataset Preprocessing")
    lines.append("")
    lines.append("| dataset | source | sensors | dates | date min | date max |")
    lines.append("|---|---|---:|---:|---|---|")
    for key, bundle in bundles.items():
        prep = bundle.preprocessing
        lines.append(
            f"| `{key}` | `{bundle.spec.source_frequency}` | "
            f"{prep['retained_sensor_count']} | {prep['date_count']} | "
            f"{prep['date_min']} | {prep['date_max']} |"
        )
    lines.append("")
    lines.append("## Output Counts")
    lines.append("")
    grouped = (
        summary.groupby(["dataset_key", "time_aggregation"])
        .agg(rows=("dataset_key", "size"), min_n=("sample_size", "min"), max_n=("sample_size", "max"))
        .reset_index()
    )
    lines.append("| dataset | aggregation | rows | min n | max n |")
    lines.append("|---|---|---:|---:|---:|")
    for _, row in grouped.iterrows():
        lines.append(
            f"| `{row['dataset_key']}` | `{row['time_aggregation']}` | "
            f"{int(row['rows'])} | {int(row['min_n'])} | {int(row['max_n'])} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Daily random draws are generated once per unique valid-sensor set and sample size, then reused for dates with the same valid-sensor set."
    )
    lines.append(
        "- This keeps each summary task reproducible while avoiding unnecessary random-number generation."
    )
    lines.append(
        "- The `seed_used`, `seed_scope`, and `valid_sensor_set_hash` columns record exactly which draw stream each row used."
    )
    (logs_dir / "validation_report.md").write_text("\n".join(lines) + "\n")


def build_tasks(bundles: dict[str, DatasetBundle], args: argparse.Namespace) -> list[MonteCarloTask]:
    tasks: list[MonteCarloTask] = []
    for key, bundle in bundles.items():
        retained_sensors = len(bundle.sensor_ids)
        max_daily_n = min(args.max_daily_n, retained_sensors - 1)
        max_period_n = min(args.max_period_n, retained_sensors - 1)
        for sample_size in range(args.min_sample_size, max_daily_n + 1):
            tasks.append(MonteCarloTask(dataset_key=key, time_aggregation="daily", sample_size=sample_size))
        for sample_size in range(args.min_sample_size, max_period_n + 1):
            tasks.append(MonteCarloTask(dataset_key=key, time_aggregation="period", sample_size=sample_size))
    return tasks


def make_run_id(priority: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{priority}"


def write_metadata(
    run_dir: Path,
    args: argparse.Namespace,
    bundles: dict[str, DatasetBundle],
    tasks: list[MonteCarloTask],
    start_time: str,
) -> None:
    config_dir = run_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_id": run_dir.name,
        "priority": args.priority,
        "scenario": SCENARIO_ID,
        "placement": PLACEMENT,
        "estimator": ESTIMATOR,
        "draws": args.draws,
        "top_k": args.top_k,
        "master_seed": args.master_seed,
        "seed_algorithm": "sha256(master_seed + run_id + task_parts) -> uint32",
        "min_sample_size": args.min_sample_size,
        "max_daily_n": args.max_daily_n,
        "max_period_n": args.max_period_n,
        "requested_n_jobs": getattr(args, "requested_n_jobs", args.n_jobs),
        "n_jobs": args.n_jobs,
        "compute_resources": compute_resource_metadata(),
        "dataset_keys": args.dataset_keys,
        "task_count": len(tasks),
        "started_at": start_time,
        "repo_root": "<repository-root>",
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "python": sys.version,
        "platform": platform.platform(),
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
    }
    (config_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))
    hashes = {
        key: {
            "spec": asdict(bundle.spec),
            "input_hashes": bundle.input_hashes,
            "preprocessing": bundle.preprocessing,
        }
        for key, bundle in bundles.items()
    }
    (config_dir / "data_hashes.json").write_text(json.dumps(hashes, indent=2))


def complete_metadata(run_dir: Path, completed_at: str, duration_seconds: float) -> None:
    metadata_path = run_dir / "config/run_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["completed_at"] = completed_at
    metadata["duration_seconds"] = duration_seconds
    metadata_path.write_text(json.dumps(metadata, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the active multicore design-based Monte Carlo baseline."
    )
    parser.add_argument("--priority", default="p0_baseline", choices=["p0_baseline"])
    parser.add_argument(
        "--datasets",
        type=parse_dataset_keys,
        default=parse_dataset_keys(
            "dhaka_lcs,lucknow_lcs,chicago_lcs_corrected_no_collocation"
        ),
        help="Comma-separated dataset keys.",
    )
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--min-sample-size", type=int, default=2)
    parser.add_argument("--max-daily-n", type=int, default=DEFAULT_MAX_N)
    parser.add_argument("--max-period-n", type=int, default=DEFAULT_MAX_N)
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=0,
        help=(
            "Worker processes. Use 0 or -1 for all available CPU cores; "
            "-2 leaves one core free. Values above CPU count are clamped."
        ),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def parse_args() -> argparse.Namespace:
    args = build_parser().parse_args()
    args.dataset_keys = args.datasets
    if args.draws < 1:
        raise SystemExit("--draws must be positive")
    if args.top_k < 1:
        raise SystemExit("--top-k must be positive")
    if args.min_sample_size < 1:
        raise SystemExit("--min-sample-size must be positive")
    if args.max_daily_n < args.min_sample_size:
        raise SystemExit("--max-daily-n must be >= --min-sample-size")
    if args.max_period_n < args.min_sample_size:
        raise SystemExit("--max-period-n must be >= --min-sample-size")
    args.requested_n_jobs = args.n_jobs
    args.n_jobs = resolve_n_jobs(args.n_jobs)
    return args


def main() -> None:
    args = parse_args()
    run_id = args.run_id or make_run_id(args.priority)
    run_dir = args.results_root / run_id
    if run_dir.exists() and not args.overwrite:
        raise SystemExit(f"Run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ["config", "preprocessed", "mc_summary", "mc_extremes", "logs"]:
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    bundles = {key: load_dataset(DATASETS[key]) for key in args.dataset_keys}
    for bundle in bundles.values():
        write_preprocessed(bundle, run_dir / "preprocessed")
    tasks = build_tasks(bundles, args)
    write_metadata(run_dir, args, bundles, tasks, started_at)

    print(
        f"Run {run_id}: {len(tasks)} tasks, draws={args.draws:,}, "
        f"top_k={args.top_k}, n_jobs={args.n_jobs}"
    )
    summary_rows: list[dict[str, Any]] = []
    extremes: list[dict[str, Any]] = []
    seeds: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.n_jobs) as executor:
        futures = {
            executor.submit(
                run_task,
                task,
                bundles[task.dataset_key],
                args.draws,
                args.top_k,
                args.master_seed,
                run_id,
            ): task
            for task in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            task_summaries, task_extremes, task_seeds = future.result()
            summary_rows.extend(task_summaries)
            extremes.extend(task_extremes)
            seeds.extend(task_seeds)
            if completed == 1 or completed % 10 == 0 or completed == len(futures):
                print(
                    f"[{completed:>4}/{len(futures)}] "
                    f"{task.dataset_key} {task.time_aggregation} n={task.sample_size} "
                    f"summary_rows={len(summary_rows):,}"
                )

    write_outputs(run_dir, summary_rows, extremes, seeds)
    summary = pd.DataFrame(summary_rows)
    write_validation_report(run_dir, summary, bundles, args)
    duration = time.perf_counter() - start
    complete_metadata(run_dir, datetime.now().isoformat(timespec="seconds"), duration)
    print(f"Wrote {run_dir}")
    print(f"Summary rows: {len(summary_rows):,}; extremes rows: {len(extremes):,}")
    print(f"Duration: {duration:.1f} seconds")


if __name__ == "__main__":
    main()
