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
from dataclasses import asdict, dataclass
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
    load_dataset,
)
from plot_style import (  # noqa: E402
    GRID_COLOR,
    OUTPUT_DPI,
    SAMPLE_SIZE_COLORS,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


OUTPUT_DIR = REPO_ROOT / "analysis/results/temporal_diagnostics"
PLOT_DIR = REPO_ROOT / "analysis/plots/temporal_diagnostics"
DEFAULT_DRAWS = 10_000
DEFAULT_MASTER_SEED = 20260522
DEFAULT_MAX_N = 30
COMMON_SAMPLE_SIZES = (5, 10, 20)
CITY_ORDER = ("Dhaka", "Lucknow", "Chicago")
DATASET_ORDER = ("dhaka_lcs", "lucknow_lcs", "chicago_lcs_corrected_no_collocation")


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


@dataclass(frozen=True)
class ConvergenceTask:
    dataset_key: str
    city: str
    period_type: str
    period_label: str
    period_sort: int
    n_days: int
    values: tuple[float, ...]
    draws: int
    master_seed: int
    max_n: int


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


def season_for_month(month: int) -> tuple[str, int]:
    if month in {12, 1, 2}:
        return "DJF", 1
    if month in {3, 4, 5}:
        return "MAM", 2
    if month in {6, 7, 8}:
        return "JJA", 3
    return "SON", 4


def parse_sample_sizes(value: str) -> tuple[int, ...]:
    sample_sizes = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not sample_sizes:
        raise argparse.ArgumentTypeError("at least one sample size is required")
    if any(sample_size < 2 for sample_size in sample_sizes):
        raise argparse.ArgumentTypeError("sample sizes must be >= 2")
    return sample_sizes


def build_hourly_matrix(spec: DatasetSpec) -> tuple[pd.DataFrame, dict[str, Any]]:
    locations = read_locations(spec)
    location_sensor_ids = locations["Sensor_ID"].astype(str).tolist()
    pm = read_pm_matrix(spec, location_sensor_ids)
    sensor_ids = [sensor_id for sensor_id in location_sensor_ids if sensor_id in pm.columns]
    values = pm[sensor_ids].copy()
    all_nan = values.columns[values.isna().all(axis=0)].tolist()
    if all_nan:
        values = values.drop(columns=all_nan)
        sensor_ids = [sensor_id for sensor_id in sensor_ids if sensor_id not in all_nan]
    frame = pd.concat([pm[["Timestamp"]], values], axis=1)
    timestamp_text = frame["Timestamp"].astype(str).str.replace(
        r"(?:Z|[+-]\d{2}:?\d{2})$", "", regex=True
    )
    timestamps = pd.to_datetime(timestamp_text, errors="coerce")
    frame = frame.loc[timestamps.notna()].copy()
    frame["Timestamp"] = timestamps.loc[timestamps.notna()].dt.tz_localize(None).to_numpy()
    frame = frame.sort_values("Timestamp")
    metadata = {
        "source_rows": int(len(pm)),
        "valid_timestamp_rows": int(len(frame)),
        "source_sensor_columns": int(len(pm.columns) - 1),
        "retained_sensor_count": int(len(sensor_ids)),
        "dropped_all_nan_sensor_count": int(len(all_nan)),
        "dropped_all_nan_sensors": all_nan,
        "timestamp_min": str(frame["Timestamp"].min()) if len(frame) else None,
        "timestamp_max": str(frame["Timestamp"].max()) if len(frame) else None,
        "pm_matrix_hash": sha256_file(REPO_ROOT / spec.pm_path),
        "locations_hash": sha256_file(REPO_ROOT / spec.location_path),
    }
    return frame, metadata


def build_hourly_profiles() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    network_rows: list[pd.DataFrame] = []
    sensor_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}

    for dataset_key in DATASET_ORDER:
        spec = HOURLY_SPECS[dataset_key]
        frame, frame_metadata = build_hourly_matrix(spec)
        metadata[dataset_key] = frame_metadata
        sensor_ids = [column for column in frame.columns if column != "Timestamp"]
        values = frame[sensor_ids]
        valid_counts = values.notna().sum(axis=1)
        network = pd.DataFrame(
            {
                "dataset_key": dataset_key,
                "city": spec.city,
                "timestamp": frame["Timestamp"],
                "hour": pd.to_datetime(frame["Timestamp"]).dt.hour,
                "network_mean_ugm3": values.mean(axis=1, skipna=True),
                "network_median_ugm3": values.median(axis=1, skipna=True),
                "valid_sensor_count": valid_counts,
                "missing_fraction": 1.0 - valid_counts / max(len(sensor_ids), 1),
            }
        )
        hourly_network = (
            network.groupby(["dataset_key", "city", "hour"], as_index=False)
            .agg(
                n_timestamps=("timestamp", "count"),
                network_mean_ugm3=("network_mean_ugm3", "mean"),
                network_median_ugm3=("network_median_ugm3", "mean"),
                network_p25_ugm3=("network_mean_ugm3", lambda values: float(np.nanquantile(values, 0.25))),
                network_p75_ugm3=("network_mean_ugm3", lambda values: float(np.nanquantile(values, 0.75))),
                mean_valid_sensor_count=("valid_sensor_count", "mean"),
                mean_missing_fraction=("missing_fraction", "mean"),
            )
        )
        network_rows.append(hourly_network)

        long_values = frame[["Timestamp", *sensor_ids]].melt(
            id_vars="Timestamp", var_name="sensor_id", value_name="pm25_ugm3"
        )
        long_values["hour"] = pd.to_datetime(long_values["Timestamp"]).dt.hour
        sensor_profile = (
            long_values.groupby(["sensor_id", "hour"], as_index=False)
            .agg(
                mean_pm25_ugm3=("pm25_ugm3", "mean"),
                median_pm25_ugm3=("pm25_ugm3", "median"),
                valid_observations=("pm25_ugm3", "count"),
            )
        )
        sensor_profile["dataset_key"] = dataset_key
        sensor_profile["city"] = spec.city
        sensor_rows.append(
            sensor_profile[
                [
                    "dataset_key",
                    "city",
                    "sensor_id",
                    "hour",
                    "mean_pm25_ugm3",
                    "median_pm25_ugm3",
                    "valid_observations",
                ]
            ]
        )

        city_profile = hourly_network.sort_values("hour")
        peak = city_profile.loc[city_profile["network_mean_ugm3"].idxmax()]
        trough = city_profile.loc[city_profile["network_mean_ugm3"].idxmin()]
        amplitude = float(peak["network_mean_ugm3"] - trough["network_mean_ugm3"])
        daily_mean = float(city_profile["network_mean_ugm3"].mean())
        summary_rows.append(
            {
                "dataset_key": dataset_key,
                "city": spec.city,
                "retained_sensor_count": len(sensor_ids),
                "source_rows": frame_metadata["source_rows"],
                "valid_timestamp_rows": frame_metadata["valid_timestamp_rows"],
                "timestamp_min": frame_metadata["timestamp_min"],
                "timestamp_max": frame_metadata["timestamp_max"],
                "diurnal_min_hour": int(trough["hour"]),
                "diurnal_max_hour": int(peak["hour"]),
                "diurnal_min_mean_ugm3": float(trough["network_mean_ugm3"]),
                "diurnal_max_mean_ugm3": float(peak["network_mean_ugm3"]),
                "diurnal_amplitude_ugm3": amplitude,
                "diurnal_amplitude_pct_of_hourly_mean": amplitude / daily_mean * 100.0
                if daily_mean > 0
                else np.nan,
                "mean_missing_fraction": float(network["missing_fraction"].mean()),
            }
        )

    return (
        pd.concat(network_rows, ignore_index=True),
        pd.concat(sensor_rows, ignore_index=True),
        pd.DataFrame(summary_rows),
        metadata,
    )


def convergence_for_values(task: ConvergenceTask) -> list[dict[str, Any]]:
    values = np.asarray(task.values, dtype=float)
    values = values[np.isfinite(values)]
    population_size = len(values)
    if population_size < 2:
        return []
    reference_mean = float(np.mean(values))
    reference_sd = float(np.std(values, ddof=1)) if population_size > 1 else np.nan
    max_n = min(task.max_n, population_size - 1)
    if max_n < 2:
        return []
    seed = derive_seed(
        task.master_seed,
        "temporal_convergence",
        task.dataset_key,
        task.period_type,
        task.period_label,
    )
    rng = np.random.default_rng(seed)
    orders = np.argsort(rng.random((task.draws, population_size), dtype=np.float64), axis=1)[
        :, :max_n
    ]
    rows: list[dict[str, Any]] = []
    for sample_size in range(2, max_n + 1):
        sample = values[orders[:, :sample_size]]
        estimates = sample.mean(axis=1)
        absolute_error = np.abs(estimates - reference_mean)
        ape = np.where(reference_mean != 0, absolute_error / abs(reference_mean) * 100.0, np.nan)
        rows.append(
            {
                "dataset_key": task.dataset_key,
                "city": task.city,
                "period_type": task.period_type,
                "period_label": task.period_label,
                "period_sort": task.period_sort,
                "n_days": task.n_days,
                "sample_size": sample_size,
                "n_sensors_available": population_size,
                "n_draws_requested": task.draws,
                "n_draws_completed": task.draws,
                "seed_used": seed,
                "reference_mean_ugm3": reference_mean,
                "reference_sd_ugm3": reference_sd,
                "ape_median_pct": float(np.nanmedian(ape)),
                "ape_p75_pct": float(np.nanquantile(ape, 0.75)),
                "ape_p95_pct": float(np.nanquantile(ape, 0.95)),
                "absolute_error_median_ugm3": float(np.nanmedian(absolute_error)),
                "absolute_error_p75_ugm3": float(np.nanquantile(absolute_error, 0.75)),
                "absolute_error_p95_ugm3": float(np.nanquantile(absolute_error, 0.95)),
            }
        )
    return rows


def build_convergence_tasks(draws: int, master_seed: int, max_n: int) -> list[ConvergenceTask]:
    tasks: list[ConvergenceTask] = []
    for dataset_key in DATASET_ORDER:
        bundle = load_dataset(DATASETS[dataset_key])
        daily = pd.DataFrame(
            bundle.daily_values,
            index=pd.to_datetime(pd.Index(bundle.daily_dates), errors="coerce"),
            columns=bundle.sensor_ids,
        )
        daily = daily.loc[daily.index.notna()].sort_index()
        month_keys = daily.index.to_period("M")
        for month in sorted(month_keys.unique()):
            month_frame = daily.loc[month_keys == month]
            values = month_frame.mean(axis=0, skipna=True).to_numpy(dtype=float)
            tasks.append(
                ConvergenceTask(
                    dataset_key=dataset_key,
                    city=bundle.spec.city,
                    period_type="month",
                    period_label=str(month),
                    period_sort=int(month.year * 100 + month.month),
                    n_days=int(month_frame.shape[0]),
                    values=tuple(float(value) for value in values),
                    draws=draws,
                    master_seed=master_seed,
                    max_n=max_n,
                )
            )

        months = pd.Series(daily.index.month, index=daily.index)
        season_labels = months.map(lambda month: season_for_month(int(month))[0])
        season_sorts = months.map(lambda month: season_for_month(int(month))[1])
        for season_label in ["DJF", "MAM", "JJA", "SON"]:
            season_frame = daily.loc[season_labels == season_label]
            if season_frame.empty:
                continue
            values = season_frame.mean(axis=0, skipna=True).to_numpy(dtype=float)
            tasks.append(
                ConvergenceTask(
                    dataset_key=dataset_key,
                    city=bundle.spec.city,
                    period_type="season",
                    period_label=season_label,
                    period_sort=int(season_sorts.loc[season_labels == season_label].iloc[0]),
                    n_days=int(season_frame.shape[0]),
                    values=tuple(float(value) for value in values),
                    draws=draws,
                    master_seed=master_seed,
                    max_n=max_n,
                )
            )
    return tasks


def run_convergence(tasks: list[ConvergenceTask], jobs: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if jobs <= 1:
        for task in tasks:
            rows.extend(convergence_for_values(task))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = [executor.submit(convergence_for_values, task) for task in tasks]
            for future in as_completed(futures):
                rows.extend(future.result())
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["period_type", "dataset_key", "period_sort", "sample_size"]).reset_index(
        drop=True
    )


def build_convergence_overview(convergence: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (dataset_key, city, period_type, sample_size), group in convergence.groupby(
        ["dataset_key", "city", "period_type", "sample_size"], sort=True
    ):
        rows.append(
            {
                "dataset_key": dataset_key,
                "city": city,
                "period_type": period_type,
                "sample_size": int(sample_size),
                "n_periods": int(group["period_label"].nunique()),
                "median_period_mdape_pct": float(group["ape_median_pct"].median()),
                "max_period_mdape_pct": float(group["ape_median_pct"].max()),
                "median_period_absolute_error_ugm3": float(
                    group["absolute_error_median_ugm3"].median()
                ),
                "max_period_absolute_error_ugm3": float(group["absolute_error_median_ugm3"].max()),
            }
        )
    return pd.DataFrame(rows)


def plot_diurnal_profiles(hourly_profile: pd.DataFrame) -> None:
    setup_matplotlib()
    y_max = float(np.nanmax(hourly_profile["network_p75_ugm3"])) * 1.08
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True, constrained_layout=True)
    for axis, city in zip(axes, CITY_ORDER):
        city_frame = hourly_profile[hourly_profile["city"] == city].sort_values("hour")
        color = color_for_dataset(str(city_frame["dataset_key"].iloc[0]))
        axis.fill_between(
            city_frame["hour"].to_numpy(dtype=float),
            city_frame["network_p25_ugm3"].to_numpy(dtype=float),
            city_frame["network_p75_ugm3"].to_numpy(dtype=float),
            color=color,
            alpha=0.18,
            linewidth=0,
            label="IQR across timestamps",
        )
        axis.plot(
            city_frame["hour"],
            city_frame["network_mean_ugm3"],
            color=color,
            lw=2.0,
            label="Mean",
        )
        axis.plot(
            city_frame["hour"],
            city_frame["network_median_ugm3"],
            color="#111827",
            lw=1.3,
            ls="--",
            label="Median",
        )
        axis.set_title(city)
        axis.set_xlabel("Local hour")
        axis.set_xlim(0, 23)
        axis.set_ylim(0, y_max)
        axis.set_xticks([0, 6, 12, 18, 23])
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("PM2.5 (µg/m³)")
    axes[-1].legend(loc="upper right", frameon=False)
    fig.suptitle("S19. Highest-resolution diurnal network profiles")
    save_figure(fig, PLOT_DIR / "S19_diurnal_network_profiles", dpi=OUTPUT_DPI)


def plot_diurnal_amplitude(summary: pd.DataFrame) -> None:
    setup_matplotlib()
    fig, axis = plt.subplots(figsize=(6.5, 4), constrained_layout=True)
    summary = summary.set_index("city").loc[list(CITY_ORDER)].reset_index()
    colors = [color_for_dataset(str(row.dataset_key)) for row in summary.itertuples()]
    axis.bar(summary["city"], summary["diurnal_amplitude_ugm3"], color=colors, alpha=0.82)
    axis.set_ylabel("Peak-trough amplitude (µg/m³)")
    axis.set_title("S19. Diurnal amplitude by city")
    axis.grid(True, axis="y", color=GRID_COLOR, lw=0.5)
    for index, row in enumerate(summary.itertuples()):
        axis.text(
            index,
            row.diurnal_amplitude_ugm3,
            f"{row.diurnal_amplitude_pct_of_hourly_mean:.0f}%",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    save_figure(fig, PLOT_DIR / "S19_diurnal_amplitude_by_city", dpi=OUTPUT_DPI)


def plot_monthly_convergence(convergence: pd.DataFrame, sample_sizes: tuple[int, ...]) -> None:
    setup_matplotlib()
    monthly = convergence[
        (convergence["period_type"] == "month") & convergence["sample_size"].isin(sample_sizes)
    ].copy()
    y_max = float(np.nanmax(monthly["ape_median_pct"])) * 1.08
    fig, axes = plt.subplots(len(sample_sizes), 1, figsize=(11, 8), sharex=True, sharey=True, constrained_layout=True)
    if len(sample_sizes) == 1:
        axes = np.asarray([axes])
    month_labels = sorted(monthly["period_label"].unique())
    x_lookup = {label: index for index, label in enumerate(month_labels)}
    for axis, sample_size in zip(axes, sample_sizes):
        size_frame = monthly[monthly["sample_size"] == sample_size]
        for city in CITY_ORDER:
            city_frame = size_frame[size_frame["city"] == city].sort_values("period_sort")
            if city_frame.empty:
                continue
            color = color_for_dataset(str(city_frame["dataset_key"].iloc[0]))
            x_values = [x_lookup[label] for label in city_frame["period_label"]]
            axis.plot(
                x_values,
                city_frame["ape_median_pct"],
                marker="o",
                lw=1.4,
                ms=3.5,
                color=color,
                label=city,
            )
        axis.set_ylabel(f"n={sample_size}\nMdAPE (%)")
        axis.set_ylim(0, y_max)
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].legend(loc="upper right", frameon=False, ncol=3)
    axes[-1].set_xticks(range(len(month_labels)))
    axes[-1].set_xticklabels(month_labels, rotation=45, ha="right")
    axes[-1].set_xlabel("Month")
    fig.suptitle("S20. Monthly subnetwork convergence by city")
    save_figure(fig, PLOT_DIR / "S20_monthly_convergence_selected_n", dpi=OUTPUT_DPI)


def plot_seasonal_convergence(convergence: pd.DataFrame) -> None:
    setup_matplotlib()
    seasonal = convergence[convergence["period_type"] == "season"].copy()
    y_max = float(np.nanmax(seasonal["ape_median_pct"])) * 1.08
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True, constrained_layout=True)
    season_colors = {"DJF": "#2563eb", "MAM": "#16a34a", "JJA": "#f97316", "SON": "#7c3aed"}
    for axis, city in zip(axes, CITY_ORDER):
        city_frame = seasonal[seasonal["city"] == city].sort_values(["period_sort", "sample_size"])
        for season, season_frame in city_frame.groupby("period_label", sort=False):
            axis.plot(
                season_frame["sample_size"],
                season_frame["ape_median_pct"],
                color=season_colors.get(str(season), "#111827"),
                lw=1.4,
                label=str(season),
            )
        axis.set_title(city)
        axis.set_xlabel("Number of sensors")
        axis.set_xlim(2, DEFAULT_MAX_N)
        axis.set_ylim(0, y_max)
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("MdAPE (%)")
    axes[-1].legend(loc="upper right", frameon=False)
    fig.suptitle("S20. Seasonal subnetwork convergence curves")
    save_figure(fig, PLOT_DIR / "S20_seasonal_convergence_curves", dpi=OUTPUT_DPI)


def plot_monthly_absolute_error(convergence: pd.DataFrame) -> None:
    setup_matplotlib()
    monthly = convergence[
        (convergence["period_type"] == "month") & (convergence["sample_size"] == 10)
    ].copy()
    y_max = float(np.nanmax(monthly["absolute_error_median_ugm3"])) * 1.12
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True, constrained_layout=True)
    for axis, city in zip(axes, CITY_ORDER):
        city_frame = monthly[monthly["city"] == city].sort_values("period_sort")
        color = color_for_dataset(str(city_frame["dataset_key"].iloc[0]))
        axis.plot(
            city_frame["period_label"],
            city_frame["absolute_error_median_ugm3"],
            marker="o",
            lw=1.5,
            color=color,
        )
        axis.set_title(city)
        axis.set_ylim(0, y_max)
        axis.tick_params(axis="x", rotation=45)
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("Median absolute error (µg/m³), n=10")
    fig.suptitle("S20. Monthly absolute-error sensitivity at n=10")
    save_figure(fig, PLOT_DIR / "S20_monthly_absolute_error_n10", dpi=OUTPUT_DPI)


def table(frame: pd.DataFrame, columns: list[str], max_rows: int = 30) -> str:
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


def write_markdown(
    hourly_summary: pd.DataFrame,
    convergence_overview: pd.DataFrame,
    convergence: pd.DataFrame,
    output_path: Path,
    master_seed: int,
) -> None:
    selected = convergence_overview[
        convergence_overview["sample_size"].isin(COMMON_SAMPLE_SIZES)
    ].sort_values(["period_type", "city", "sample_size"])
    monthly_n10 = (
        convergence[
            (convergence["period_type"] == "month") & (convergence["sample_size"] == 10)
        ]
        .sort_values(["city", "ape_median_pct"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(3)
        .sort_values(["city", "ape_median_pct"], ascending=[True, False])
    )
    markdown = f"""# Temporal Diagnostics

Generated by `analysis/scripts/build_temporal_diagnostics.py`.

## Scope

- Diurnal profiles use the highest-resolution available local file for each primary network: Dhaka hourly LCS, Lucknow hourly LCS, and Chicago corrected hourly LCS with collocation sensors excluded.
- Monthly and seasonal convergence use daily network matrices to construct month/season-specific finite populations and then run SRSWOR Monte Carlo on sensor means.
- Monte Carlo convergence uses deterministic seeds derived from master seed `{master_seed}`.

## Diurnal Summary

{table(hourly_summary, [
    "city",
    "retained_sensor_count",
    "timestamp_min",
    "timestamp_max",
    "diurnal_min_hour",
    "diurnal_max_hour",
    "diurnal_amplitude_ugm3",
    "diurnal_amplitude_pct_of_hourly_mean",
    "mean_missing_fraction",
])}

## Monthly / Seasonal Convergence Overview

{table(selected, [
    "city",
    "period_type",
    "sample_size",
    "n_periods",
    "median_period_mdape_pct",
    "max_period_mdape_pct",
    "median_period_absolute_error_ugm3",
    "max_period_absolute_error_ugm3",
], max_rows=40)}

## Highest Monthly MdAPE At n=10

{table(monthly_n10, [
    "city",
    "period_label",
    "n_days",
    "n_sensors_available",
    "reference_mean_ugm3",
    "ape_median_pct",
    "absolute_error_median_ugm3",
], max_rows=20)}

## Interpretation

- Diurnal amplitude is a descriptive temporal-feature diagnostic, not a replacement for the daily or study-period Monte Carlo estimand.
- Monthly/seasonal convergence curves test whether the sensor-count conclusion is stable across temporal regimes.
- Monthly bins are descriptive because some cities have fewer months or incomplete seasonal coverage in the active study period, especially Chicago.
- Larger monthly MdAPE generally indicates months where the cross-sensor finite population is more heterogeneous, not necessarily months with higher PM2.5 concentration.

## Output Inventory

- `hourly_network_profile.csv`
- `hourly_sensor_profile.csv`
- `hourly_diurnal_summary.csv`
- `monthly_seasonal_convergence_summary.csv`
- `monthly_seasonal_convergence_overview.csv`
- `S19_diurnal_network_profiles.*`
- `S19_diurnal_amplitude_by_city.*`
- `S20_monthly_convergence_selected_n.*`
- `S20_monthly_absolute_error_n10.*`
- `S20_seasonal_convergence_curves.*`
"""
    output_path.write_text(markdown)


def build_metadata(
    args: argparse.Namespace,
    hourly_metadata: dict[str, Any],
    started: float,
    effective_jobs: int,
) -> dict[str, Any]:
    memory_bytes = total_memory_bytes()
    return {
        "script": display_path(Path(__file__)),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime_seconds": round(time.time() - started, 3),
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "draws": int(args.draws),
        "master_seed": int(args.master_seed),
        "max_n": int(args.max_n),
        "requested_jobs": int(args.jobs),
        "effective_jobs": int(effective_jobs),
        "available_cpu_count": available_cpu_count(),
        "total_memory_gb": round(memory_bytes / 1024**3, 3) if memory_bytes else None,
        "platform": platform.platform(),
        "hourly_sources": hourly_metadata,
        "daily_sources": {
            key: {
                "pm_path": DATASETS[key].pm_path,
                "location_path": DATASETS[key].location_path,
                "source_frequency": DATASETS[key].source_frequency,
                "exclude_collocated": DATASETS[key].exclude_collocated,
            }
            for key in DATASET_ORDER
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--max-n", type=int, default=DEFAULT_MAX_N)
    parser.add_argument("--jobs", type=int, default=0, help="0/-1 uses all available CPU cores")
    parser.add_argument(
        "--monthly-plot-sample-sizes",
        type=parse_sample_sizes,
        default=COMMON_SAMPLE_SIZES,
    )
    args = parser.parse_args()
    started = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = resolve_jobs(args.jobs)

    hourly_profile, sensor_profile, hourly_summary, hourly_metadata = build_hourly_profiles()
    tasks = build_convergence_tasks(args.draws, args.master_seed, args.max_n)
    convergence = run_convergence(tasks, jobs)
    convergence_overview = build_convergence_overview(convergence)

    hourly_profile.to_csv(OUTPUT_DIR / "hourly_network_profile.csv", index=False)
    sensor_profile.to_csv(OUTPUT_DIR / "hourly_sensor_profile.csv", index=False)
    hourly_summary.to_csv(OUTPUT_DIR / "hourly_diurnal_summary.csv", index=False)
    convergence.to_csv(OUTPUT_DIR / "monthly_seasonal_convergence_summary.csv", index=False)
    convergence_overview.to_csv(
        OUTPUT_DIR / "monthly_seasonal_convergence_overview.csv", index=False
    )

    plot_diurnal_profiles(hourly_profile)
    plot_diurnal_amplitude(hourly_summary)
    plot_monthly_convergence(convergence, args.monthly_plot_sample_sizes)
    plot_monthly_absolute_error(convergence)
    plot_seasonal_convergence(convergence)
    write_markdown(
        hourly_summary,
        convergence_overview,
        convergence,
        OUTPUT_DIR / "temporal_diagnostics.md",
        int(args.master_seed),
    )
    metadata = build_metadata(args, hourly_metadata, started, jobs)
    (OUTPUT_DIR / "temporal_diagnostics_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True)
    )
    print(f"Wrote temporal diagnostics to {OUTPUT_DIR}")
    print(f"Wrote temporal plots to {PLOT_DIR}")


if __name__ == "__main__":
    main()
