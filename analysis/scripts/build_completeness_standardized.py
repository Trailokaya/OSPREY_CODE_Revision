from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

from build_estimator_diagnostics import (  # noqa: E402
    DATASETS,
    DatasetSpec,
    derive_seed,
    read_locations,
    read_pm_matrix,
    sha256_file,
)
from plot_style import (  # noqa: E402
    GRID_COLOR,
    OUTPUT_DPI,
    SCENARIO_COLORS,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


OUTPUT_DIR = REPO_ROOT / "analysis/results/completeness_standardized"
PLOT_DIR = REPO_ROOT / "analysis/plots/completeness_standardized"
DEFAULT_DRAWS = 10_000
DEFAULT_MASTER_SEED = 20260522
CITY_ORDER = ("Dhaka", "Lucknow", "Chicago")
DATASET_ORDER = ("dhaka_lcs", "lucknow_lcs", "chicago_lcs_corrected_no_collocation")
SUBSET_CANDIDATES = (1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200)


HOURLY_SPECS: dict[str, DatasetSpec] = {
    "dhaka_lcs": DATASETS["dhaka_lcs"],
    "lucknow_lcs": DATASETS["lucknow_lcs"],
    "chicago_lcs_corrected_no_collocation": DatasetSpec(
        key="chicago_lcs_corrected_no_collocation",
        city="Chicago",
        network="LCS corrected",
        pm_path="data/pm/Chicago_LCS_corrected_hourly_PM25.csv",
        location_path="data/locations/Chicago_LCS_corrected_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="corrected_pm25",
        exclude_collocated=True,
    ),
}


SCENARIOS: dict[str, dict[str, Any]] = {
    "S0_baseline": {
        "daily_min_hours": 1,
        "period_uptime_min": None,
        "drop_gap_gt_hours": None,
        "description": "Use all available daily values; retain all primary sensors.",
    },
    "S1_daily_18h": {
        "daily_min_hours": 18,
        "period_uptime_min": None,
        "drop_gap_gt_hours": None,
        "description": "Require at least 18 valid hourly records per sensor-day.",
    },
    "S2_daily_12h": {
        "daily_min_hours": 12,
        "period_uptime_min": None,
        "drop_gap_gt_hours": None,
        "description": "Require at least 12 valid hourly records per sensor-day.",
    },
    "S3_period_75pct": {
        "daily_min_hours": 1,
        "period_uptime_min": 0.75,
        "drop_gap_gt_hours": None,
        "description": "Retain only sensors with at least 75% hourly uptime over the study period.",
    },
    "S4_daily_18h_period_75pct": {
        "daily_min_hours": 18,
        "period_uptime_min": 0.75,
        "drop_gap_gt_hours": None,
        "description": "Combine the 18-hour daily rule with the 75% period-uptime rule.",
    },
    "S5_drop_gap_gt_30d": {
        "daily_min_hours": 1,
        "period_uptime_min": None,
        "drop_gap_gt_hours": 30 * 24,
        "description": "Drop sensors with any continuous missing gap longer than 30 days.",
    },
    "S6_period_50pct": {
        "daily_min_hours": 1,
        "period_uptime_min": 0.50,
        "drop_gap_gt_hours": None,
        "description": "Retain only sensors with at least 50% hourly uptime over the study period.",
    },
}

SCENARIO_COLOR_MAP = {
    **SCENARIO_COLORS,
    "S3_period_75pct": SCENARIO_COLORS.get("S3_annual_75pct", "#7c3aed"),
    "S4_daily_18h_period_75pct": SCENARIO_COLORS.get(
        "S4_daily_18h_annual_75pct", "#dc2626"
    ),
    "S6_period_50pct": "#0e7490",
}


@dataclass(frozen=True)
class PrimaryPanel:
    dataset_key: str
    city: str
    sensor_ids: tuple[str, ...]
    daily_values: pd.DataFrame
    daily_valid_hours: pd.DataFrame
    hourly_uptime: pd.Series
    max_gap_hours: pd.Series
    input_hashes: dict[str, str]
    preprocessing: dict[str, Any]


@dataclass(frozen=True)
class ScenarioTask:
    panel: PrimaryPanel
    scenario_name: str
    scenario: dict[str, Any]
    draws: int
    master_seed: int


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


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


def available_cpu_count() -> int:
    return max(1, os.cpu_count() or 1)


def resolve_jobs(requested: int) -> int:
    cpu_count = available_cpu_count()
    if requested in {0, -1}:
        return cpu_count
    if requested < -1:
        return max(1, cpu_count + requested + 1)
    return min(max(1, requested), cpu_count)


def local_timestamps(series: pd.Series) -> pd.Series:
    timestamp_text = series.astype(str).str.replace(r"(?:Z|[+-]\d{2}:?\d{2})$", "", regex=True)
    return pd.to_datetime(timestamp_text, errors="coerce")


def max_missing_run_hours(values: pd.DataFrame) -> pd.Series:
    rows: dict[str, int] = {}
    for sensor_id in values.columns:
        missing = values[sensor_id].isna().to_numpy()
        longest = 0
        current = 0
        for is_missing in missing:
            if is_missing:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        rows[str(sensor_id)] = int(longest)
    return pd.Series(rows, dtype=float)


def read_hourly_values(spec: DatasetSpec) -> tuple[pd.DataFrame, dict[str, Any]]:
    locations = read_locations(spec)
    location_sensor_ids = locations["Sensor_ID"].astype(str).tolist()
    pm = read_pm_matrix(spec, location_sensor_ids)
    sensor_ids = [sensor_id for sensor_id in location_sensor_ids if sensor_id in pm.columns]
    values = pm[sensor_ids].copy()
    all_nan = values.columns[values.isna().all(axis=0)].tolist()
    if all_nan:
        values = values.drop(columns=all_nan)
        sensor_ids = [sensor_id for sensor_id in sensor_ids if sensor_id not in all_nan]
    timestamps = local_timestamps(pm["Timestamp"])
    values = values.loc[timestamps.notna()].copy()
    values.index = timestamps.loc[timestamps.notna()]
    values = values.sort_index()
    metadata = {
        "hourly_pm_path": spec.pm_path,
        "location_path": spec.location_path,
        "source_rows": int(len(pm)),
        "valid_timestamp_rows": int(len(values)),
        "source_sensor_columns": int(len(pm.columns) - 1),
        "retained_sensor_count": int(len(sensor_ids)),
        "dropped_all_nan_sensor_count": int(len(all_nan)),
        "dropped_all_nan_sensors": all_nan,
        "hourly_timestamp_min": str(values.index.min()) if len(values) else None,
        "hourly_timestamp_max": str(values.index.max()) if len(values) else None,
        "hourly_pm_hash": sha256_file(REPO_ROOT / spec.pm_path),
        "locations_hash": sha256_file(REPO_ROOT / spec.location_path),
    }
    return values, metadata


def read_official_daily_values(spec: DatasetSpec, sensor_ids: list[str]) -> pd.DataFrame:
    pm = read_pm_matrix(spec, sensor_ids)
    timestamps = local_timestamps(pm["Timestamp"])
    values = pm[sensor_ids].loc[timestamps.notna()].copy()
    values.index = timestamps.loc[timestamps.notna()].dt.strftime("%Y-%m-%d")
    values = values.groupby(values.index, sort=True).mean()
    values.index = pd.to_datetime(values.index)
    return values.sort_index()


def build_primary_panel(dataset_key: str) -> PrimaryPanel:
    hourly_spec = HOURLY_SPECS[dataset_key]
    hourly_values, metadata = read_hourly_values(hourly_spec)
    sensor_ids = list(hourly_values.columns.astype(str))
    daily_valid_hours = hourly_values.notna().groupby(hourly_values.index.normalize()).sum()
    if dataset_key == "chicago_lcs_corrected_no_collocation":
        daily_spec = DATASETS[dataset_key]
        daily_values = read_official_daily_values(daily_spec, sensor_ids)
        daily_valid_hours = daily_valid_hours.reindex(daily_values.index)
        metadata["daily_pm_path"] = daily_spec.pm_path
        metadata["daily_pm_hash"] = sha256_file(REPO_ROOT / daily_spec.pm_path)
        metadata["daily_value_source"] = "official_daily_lcs_corrected"
    else:
        daily_values = hourly_values.groupby(hourly_values.index.normalize()).mean()
        metadata["daily_pm_path"] = hourly_spec.pm_path
        metadata["daily_pm_hash"] = metadata["hourly_pm_hash"]
        metadata["daily_value_source"] = "hourly_aggregated_mean"
    daily_values = daily_values[sensor_ids].sort_index()
    daily_valid_hours = daily_valid_hours[sensor_ids].reindex(daily_values.index).fillna(0)
    hourly_uptime = hourly_values.notna().mean(axis=0).reindex(sensor_ids).astype(float)
    max_gap_hours = max_missing_run_hours(hourly_values).reindex(sensor_ids).fillna(0)
    metadata.update(
        {
            "daily_date_min": str(daily_values.index.min().date()) if len(daily_values) else None,
            "daily_date_max": str(daily_values.index.max().date()) if len(daily_values) else None,
            "daily_rows": int(len(daily_values)),
        }
    )
    return PrimaryPanel(
        dataset_key=dataset_key,
        city=hourly_spec.city,
        sensor_ids=tuple(sensor_ids),
        daily_values=daily_values,
        daily_valid_hours=daily_valid_hours,
        hourly_uptime=hourly_uptime,
        max_gap_hours=max_gap_hours,
        input_hashes={
            "hourly_pm": metadata["hourly_pm_hash"],
            "daily_pm": metadata["daily_pm_hash"],
            "locations": metadata["locations_hash"],
        },
        preprocessing=metadata,
    )


def retained_sensors(panel: PrimaryPanel, scenario: dict[str, Any]) -> list[str]:
    retained = pd.Series(True, index=pd.Index(panel.sensor_ids, dtype=str))
    uptime_min = scenario["period_uptime_min"]
    if uptime_min is not None:
        retained &= panel.hourly_uptime.reindex(retained.index).fillna(0) >= float(uptime_min)
    gap_threshold = scenario["drop_gap_gt_hours"]
    if gap_threshold is not None:
        retained &= panel.max_gap_hours.reindex(retained.index).fillna(np.inf) <= float(gap_threshold)
    return retained[retained].index.astype(str).tolist()


def subset_sizes(n_sensors: int) -> list[int]:
    return [candidate for candidate in SUBSET_CANDIDATES if candidate <= n_sensors]


def mdape(values: np.ndarray, sample_size: int, draws: int, seed: int) -> float:
    values = values[np.isfinite(values)].astype(float)
    population_size = len(values)
    if population_size < sample_size or sample_size < 1:
        return np.nan
    reference_mean = float(np.mean(values))
    if not np.isfinite(reference_mean) or reference_mean == 0:
        return np.nan
    rng = np.random.default_rng(seed)
    keys = rng.random((draws, population_size), dtype=np.float64)
    indexes = np.argpartition(keys, sample_size - 1, axis=1)[:, :sample_size]
    estimates = values[indexes].mean(axis=1)
    ape = np.abs(estimates - reference_mean) / abs(reference_mean) * 100.0
    return float(np.nanmedian(ape))


def daily_fraction_mdape_le_10(
    daily_frame: pd.DataFrame,
    sample_size: int,
    draws: int,
    seed: int,
) -> tuple[float, int]:
    rng = np.random.default_rng(seed)
    successes = 0
    evaluated = 0
    for _, row in daily_frame.iterrows():
        values = row.to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        population_size = len(values)
        if population_size < sample_size:
            continue
        reference_mean = float(np.mean(values))
        if not np.isfinite(reference_mean) or reference_mean == 0:
            continue
        keys = rng.random((draws, population_size), dtype=np.float64)
        indexes = np.argpartition(keys, sample_size - 1, axis=1)[:, :sample_size]
        estimates = values[indexes].mean(axis=1)
        ape = np.abs(estimates - reference_mean) / abs(reference_mean) * 100.0
        successes += int(float(np.nanmedian(ape)) <= 10.0)
        evaluated += 1
    if evaluated == 0:
        return np.nan, 0
    return float(successes / evaluated), evaluated


def reference_series_for_scenario(
    panel: PrimaryPanel,
    scenario: dict[str, Any],
    sensors: list[str],
) -> pd.Series:
    if not sensors:
        return pd.Series(dtype=float)
    filtered = panel.daily_values[sensors].where(
        panel.daily_valid_hours[sensors] >= int(scenario["daily_min_hours"])
    )
    return filtered.mean(axis=1, skipna=True)


def run_scenario(task: ScenarioTask) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    panel = task.panel
    sensors = retained_sensors(panel, task.scenario)
    if not sensors:
        summary = {
            "dataset_key": panel.dataset_key,
            "city": panel.city,
            "scenario": task.scenario_name,
            "description": task.scenario["description"],
            "retained_sensors": 0,
            "period_required_n_mdape_le_5": np.nan,
            "daily_required_n_95pct_days_mdape_le_10": np.nan,
            "median_daily_valid_sensors": 0,
            "min_daily_valid_sensors": 0,
            "p05_daily_valid_sensors": 0,
            "mean_daily_missing_fraction": np.nan,
            "m5_seed": np.nan,
        }
        return summary, pd.DataFrame(), pd.DataFrame()

    daily_filtered = panel.daily_values[sensors].where(
        panel.daily_valid_hours[sensors] >= int(task.scenario["daily_min_hours"])
    )
    period_values = daily_filtered.mean(axis=0, skipna=True).dropna().to_numpy(dtype=float)
    daily_valid_counts = daily_filtered.notna().sum(axis=1)
    seed_base = derive_seed(
        task.master_seed,
        "standardized_completeness",
        panel.dataset_key,
        task.scenario_name,
    )

    first_period_n = np.nan
    first_daily_n = np.nan
    curve_rows: list[dict[str, Any]] = []
    max_n = len(period_values)
    for sample_size in subset_sizes(max_n):
        period_seed = derive_seed(seed_base, "period", sample_size)
        daily_seed = derive_seed(seed_base, "daily", sample_size)
        period_mdape = mdape(period_values, sample_size, task.draws, period_seed)
        daily_fraction, evaluated_days = daily_fraction_mdape_le_10(
            daily_filtered,
            sample_size,
            task.draws,
            daily_seed,
        )
        if np.isnan(first_period_n) and np.isfinite(period_mdape) and period_mdape <= 5.0:
            first_period_n = sample_size
        if (
            np.isnan(first_daily_n)
            and np.isfinite(daily_fraction)
            and daily_fraction >= 0.95
        ):
            first_daily_n = sample_size
        curve_rows.append(
            {
                "dataset_key": panel.dataset_key,
                "city": panel.city,
                "scenario": task.scenario_name,
                "n": sample_size,
                "period_mdape_pct": period_mdape,
                "daily_fraction_days_mdape_le_10": daily_fraction,
                "daily_valid_days_evaluated": evaluated_days,
                "period_seed": period_seed,
                "daily_seed": daily_seed,
            }
        )

    reference_series = reference_series_for_scenario(panel, task.scenario, sensors)
    daily_reference_rows = pd.DataFrame(
        {
            "dataset_key": panel.dataset_key,
            "city": panel.city,
            "scenario": task.scenario_name,
            "date": reference_series.index.strftime("%Y-%m-%d"),
            "reference_mean_ugm3": reference_series.to_numpy(dtype=float),
            "n_valid_sensors": daily_valid_counts.to_numpy(dtype=int),
            "missing_fraction": 1.0 - daily_valid_counts.to_numpy(dtype=float) / max(len(sensors), 1),
        }
    )
    summary = {
        "dataset_key": panel.dataset_key,
        "city": panel.city,
        "scenario": task.scenario_name,
        "description": task.scenario["description"],
        "retained_sensors": int(len(sensors)),
        "period_sensors_with_values": int(len(period_values)),
        "period_required_n_mdape_le_5": first_period_n,
        "daily_required_n_95pct_days_mdape_le_10": first_daily_n,
        "median_daily_valid_sensors": float(daily_valid_counts.median()),
        "min_daily_valid_sensors": int(daily_valid_counts.min()),
        "p05_daily_valid_sensors": float(daily_valid_counts.quantile(0.05)),
        "mean_daily_missing_fraction": float((1.0 - daily_valid_counts / max(len(sensors), 1)).mean()),
        "m5_seed": seed_base,
    }
    return summary, pd.DataFrame(curve_rows), daily_reference_rows


def run_tasks(tasks: list[ScenarioTask], jobs: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summaries: list[dict[str, Any]] = []
    curves: list[pd.DataFrame] = []
    daily_references: list[pd.DataFrame] = []
    if jobs <= 1:
        for task in tasks:
            summary, curve, daily_reference = run_scenario(task)
            summaries.append(summary)
            curves.append(curve)
            daily_references.append(daily_reference)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = [executor.submit(run_scenario, task) for task in tasks]
            for future in as_completed(futures):
                summary, curve, daily_reference = future.result()
                summaries.append(summary)
                curves.append(curve)
                daily_references.append(daily_reference)
    summary_frame = pd.DataFrame(summaries).sort_values(["dataset_key", "scenario"])
    curve_frame = pd.concat(curves, ignore_index=True).sort_values(["dataset_key", "scenario", "n"])
    daily_frame = pd.concat(daily_references, ignore_index=True).sort_values(
        ["dataset_key", "scenario", "date"]
    )
    return summary_frame, curve_frame, daily_frame


def build_reference_sensitivity(daily_reference: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dataset_key, group in daily_reference.groupby("dataset_key", sort=True):
        baseline = group[group["scenario"] == "S0_baseline"].set_index("date")[
            "reference_mean_ugm3"
        ]
        city = str(group["city"].iloc[0])
        for scenario, scenario_frame in group.groupby("scenario", sort=True):
            current = scenario_frame.set_index("date")["reference_mean_ugm3"]
            joined = pd.concat([baseline.rename("baseline"), current.rename("filtered")], axis=1)
            joined = joined.replace([np.inf, -np.inf], np.nan).dropna()
            diff = joined["filtered"] - joined["baseline"]
            if len(joined) == 0:
                pearson = np.nan
            elif joined["baseline"].std(ddof=1) == 0 or joined["filtered"].std(ddof=1) == 0:
                pearson = np.nan
            else:
                pearson = float(joined["baseline"].corr(joined["filtered"]))
            rows.append(
                {
                    "dataset_key": dataset_key,
                    "city": city,
                    "scenario": scenario,
                    "days_compared": int(len(joined)),
                    "baseline_mean_ugm3": float(joined["baseline"].mean()) if len(joined) else np.nan,
                    "filtered_mean_ugm3": float(joined["filtered"].mean()) if len(joined) else np.nan,
                    "bias_filtered_minus_baseline_ugm3": float(diff.mean()) if len(diff) else np.nan,
                    "mae_filtered_vs_baseline_ugm3": float(np.abs(diff).mean()) if len(diff) else np.nan,
                    "rmse_filtered_vs_baseline_ugm3": float(math.sqrt(np.mean(diff**2)))
                    if len(diff)
                    else np.nan,
                    "p95_abs_difference_ugm3": float(np.quantile(np.abs(diff), 0.95))
                    if len(diff)
                    else np.nan,
                    "max_abs_difference_ugm3": float(np.abs(diff).max()) if len(diff) else np.nan,
                    "pearson_r": pearson,
                }
            )
    return pd.DataFrame(rows).sort_values(["dataset_key", "scenario"])


def table(frame: pd.DataFrame, columns: list[str], max_rows: int = 50) -> str:
    subset = frame[columns].head(max_rows).copy()
    if subset.empty:
        return "_No rows._"
    for column in subset.columns:
        subset[column] = subset[column].map(
            lambda value: f"{value:.3f}" if isinstance(value, (float, np.floating)) else str(value)
        )
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in subset.astype(str).to_numpy()]
    return "\n".join([header, sep, *rows])


def plot_period_curves(curves: pd.DataFrame) -> None:
    setup_matplotlib()
    scenarios = ["S0_baseline", "S1_daily_18h", "S3_period_75pct", "S5_drop_gap_gt_30d"]
    selected = curves[curves["scenario"].isin(scenarios)].copy()
    y_max = float(np.nanmax(selected["period_mdape_pct"])) * 1.08
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True, constrained_layout=True)
    for axis, city in zip(axes, CITY_ORDER):
        city_frame = selected[selected["city"] == city]
        for scenario in scenarios:
            scenario_frame = city_frame[city_frame["scenario"] == scenario].sort_values("n")
            if scenario_frame.empty:
                continue
            axis.plot(
                scenario_frame["n"],
                scenario_frame["period_mdape_pct"],
                lw=1.4,
                color=SCENARIO_COLOR_MAP.get(scenario, color_for_dataset(str(scenario_frame["dataset_key"].iloc[0]))),
                label=scenario.replace("_", " "),
            )
        axis.set_title(city)
        axis.set_xlabel("Number of sensors")
        axis.set_ylim(0, y_max)
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("Study-period MdAPE (%)")
    axes[-1].legend(loc="upper right", frameon=False, fontsize=7)
    fig.suptitle("S07. Completeness-threshold sensitivity: study-period error")
    save_figure(fig, PLOT_DIR / "S07_completeness_period_mdape_curves", dpi=OUTPUT_DPI)


def plot_daily_fraction_curves(curves: pd.DataFrame) -> None:
    setup_matplotlib()
    scenarios = ["S0_baseline", "S1_daily_18h", "S3_period_75pct", "S5_drop_gap_gt_30d"]
    selected = curves[curves["scenario"].isin(scenarios)].copy()
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True, constrained_layout=True)
    for axis, city in zip(axes, CITY_ORDER):
        city_frame = selected[selected["city"] == city]
        for scenario in scenarios:
            scenario_frame = city_frame[city_frame["scenario"] == scenario].sort_values("n")
            if scenario_frame.empty:
                continue
            axis.plot(
                scenario_frame["n"],
                scenario_frame["daily_fraction_days_mdape_le_10"],
                lw=1.4,
                color=SCENARIO_COLOR_MAP.get(scenario, color_for_dataset(str(scenario_frame["dataset_key"].iloc[0]))),
                label=scenario.replace("_", " "),
            )
        axis.axhline(0.95, color="#6b7280", lw=0.8, ls="--")
        axis.set_title(city)
        axis.set_xlabel("Number of sensors")
        axis.set_ylim(0, 1.02)
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("Fraction of days with MdAPE ≤ 10%")
    axes[-1].legend(loc="lower right", frameon=False, fontsize=7)
    fig.suptitle("S07. Completeness-threshold sensitivity: daily target")
    save_figure(fig, PLOT_DIR / "S07_completeness_daily_fraction_curves", dpi=OUTPUT_DPI)


def plot_reference_shift(reference_sensitivity: pd.DataFrame) -> None:
    setup_matplotlib()
    selected = reference_sensitivity[reference_sensitivity["scenario"] != "S0_baseline"].copy()
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True, constrained_layout=True)
    y_max = float(np.nanmax(np.abs(selected["bias_filtered_minus_baseline_ugm3"]))) * 1.2
    y_max = max(y_max, 0.5)
    for axis, city in zip(axes, CITY_ORDER):
        city_frame = selected[selected["city"] == city].sort_values("scenario")
        color = color_for_dataset(str(city_frame["dataset_key"].iloc[0]))
        axis.bar(
            city_frame["scenario"].str.replace("_", "\n"),
            city_frame["bias_filtered_minus_baseline_ugm3"],
            color=color,
            alpha=0.78,
        )
        axis.axhline(0, color="#111827", lw=0.8)
        axis.set_title(city)
        axis.set_ylim(-y_max, y_max)
        axis.tick_params(axis="x", labelsize=6)
        axis.grid(True, axis="y", color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("Mean filtered-baseline reference shift (µg/m³)")
    fig.suptitle("S10. Reference-mean shift induced by completeness filters")
    save_figure(fig, PLOT_DIR / "S10_reference_mean_shift_by_filter", dpi=OUTPUT_DPI)


def write_markdown(
    summary: pd.DataFrame,
    reference_sensitivity: pd.DataFrame,
    output_path: Path,
    draws: int,
    master_seed: int,
    jobs: int,
) -> None:
    compact = summary[
        summary["scenario"].isin(
            ["S0_baseline", "S1_daily_18h", "S2_daily_12h", "S3_period_75pct", "S5_drop_gap_gt_30d"]
        )
    ].sort_values(["city", "scenario"])
    sensitivity_compact = reference_sensitivity[
        reference_sensitivity["scenario"].isin(
            ["S1_daily_18h", "S2_daily_12h", "S3_period_75pct", "S5_drop_gap_gt_30d"]
        )
    ].sort_values(["city", "scenario"])
    markdown = f"""# Standardized Completeness-Threshold Sensitivity

Generated by `analysis/scripts/build_completeness_standardized.py`.

## Scope

- This run uses the three primary finite populations only: Dhaka LCS, Lucknow LCS, and Chicago corrected LCS with collocation sensors excluded.
- Chicago daily PM2.5 values use the official daily corrected LCS matrix, with hourly valid-count data used only to apply completeness masks.
- Dhaka and Lucknow daily PM2.5 values are hourly means from the inherited hourly matrices.
- Monte Carlo settings: `{draws}` draws per network-scenario-sample-size, deterministic scenario seeds derived from master seed `{master_seed}`, and `{jobs}` worker process(es).

## Sensor-Count Sensitivity

{table(compact, [
    "city",
    "scenario",
    "retained_sensors",
    "period_required_n_mdape_le_5",
    "daily_required_n_95pct_days_mdape_le_10",
    "median_daily_valid_sensors",
    "min_daily_valid_sensors",
    "mean_daily_missing_fraction",
])}

## Reference-Mean Distortion

{table(sensitivity_compact, [
    "city",
    "scenario",
    "days_compared",
    "bias_filtered_minus_baseline_ugm3",
    "mae_filtered_vs_baseline_ugm3",
    "p95_abs_difference_ugm3",
    "max_abs_difference_ugm3",
    "pearson_r",
])}

## Interpretation

- Completeness filters should be reported as robustness checks because they can improve apparent missingness while changing the finite population and the daily reference mean.
- The daily valid-sensor distribution is as important as the retained-sensor count: a filter can retain many sensors but still reduce valid sensors on high-gap days.
- The reference-mean sensitivity table separates two effects: improvement in data completeness and distortion of the estimand being reproduced.
- Chicago is now aligned with the main no-collocation primary analysis population.
- Days with fewer than `n` valid sensors are skipped in the daily target calculation; this matters for Chicago because the official daily matrix includes an all-missing day.

## Output Inventory

- `completeness_standardized_summary.csv`
- `completeness_standardized_curves.csv`
- `completeness_standardized_daily_reference.csv`
- `completeness_standardized_reference_sensitivity.csv`
- `S07_completeness_period_mdape_curves.*`
- `S07_completeness_daily_fraction_curves.*`
- `S10_reference_mean_shift_by_filter.*`
"""
    output_path.write_text(markdown)


def build_metadata(
    args: argparse.Namespace,
    panels: dict[str, PrimaryPanel],
    started: float,
    jobs: int,
) -> dict[str, Any]:
    memory_bytes = total_memory_bytes()
    return {
        "script": display_path(Path(__file__)),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime_seconds": round(time.time() - started, 3),
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "draws": int(args.draws),
        "master_seed": int(args.master_seed),
        "requested_jobs": int(args.jobs),
        "effective_jobs": int(jobs),
        "available_cpu_count": available_cpu_count(),
        "total_memory_gb": round(memory_bytes / 1024**3, 3) if memory_bytes else None,
        "platform": platform.platform(),
        "scenarios": SCENARIOS,
        "panels": {
            key: {
                "city": panel.city,
                "sensor_count": len(panel.sensor_ids),
                "preprocessing": panel.preprocessing,
                "input_hashes": panel.input_hashes,
            }
            for key, panel in panels.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--jobs", type=int, default=0, help="0/-1 uses all available CPU cores")
    args = parser.parse_args()

    started = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = resolve_jobs(args.jobs)
    panels = {dataset_key: build_primary_panel(dataset_key) for dataset_key in DATASET_ORDER}
    tasks = [
        ScenarioTask(
            panel=panel,
            scenario_name=scenario_name,
            scenario=scenario,
            draws=args.draws,
            master_seed=args.master_seed,
        )
        for panel in panels.values()
        for scenario_name, scenario in SCENARIOS.items()
    ]
    summary, curves, daily_reference = run_tasks(tasks, jobs)
    reference_sensitivity = build_reference_sensitivity(daily_reference)

    summary.to_csv(OUTPUT_DIR / "completeness_standardized_summary.csv", index=False)
    curves.to_csv(OUTPUT_DIR / "completeness_standardized_curves.csv", index=False)
    daily_reference.to_csv(OUTPUT_DIR / "completeness_standardized_daily_reference.csv", index=False)
    reference_sensitivity.to_csv(
        OUTPUT_DIR / "completeness_standardized_reference_sensitivity.csv", index=False
    )
    plot_period_curves(curves)
    plot_daily_fraction_curves(curves)
    plot_reference_shift(reference_sensitivity)
    write_markdown(
        summary,
        reference_sensitivity,
        OUTPUT_DIR / "completeness_standardized.md",
        args.draws,
        args.master_seed,
        jobs,
    )
    metadata = build_metadata(args, panels, started, jobs)
    (OUTPUT_DIR / "completeness_standardized_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True)
    )
    print(f"Wrote standardized completeness outputs to {OUTPUT_DIR}")
    print(f"Wrote standardized completeness plots to {PLOT_DIR}")


if __name__ == "__main__":
    main()
