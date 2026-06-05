from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

from build_estimator_diagnostics import DATASETS, DatasetBundle, derive_seed, load_dataset, read_locations  # noqa: E402
from plot_style import GRID_COLOR, OUTPUT_DPI, REFERENCE_LINE_COLOR, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402


RESULTS_DIR = REPO_ROOT / "analysis/results/assumption_stress_tests"
PLOTS_DIR = REPO_ROOT / "analysis/plots/assumption_stress_tests"

MASTER_SEED = 20260526
MC_SEEDS = (20260522, 20260523, 20260524, 20260525, 20260526)
MC_DRAWS = (1_000, 5_000, 10_000)
MC_SAMPLE_SIZES = (2, 5, 10, 20, 30)
EXACT_COMBINATION_CAP = 1_000_000
SPATIAL_GRID_SIZE = 180


def markdown_table(frame: pd.DataFrame, float_digits: int = 3, max_rows: int | None = None) -> str:
    if max_rows is not None:
        frame = frame.head(max_rows)
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)

    def format_value(value: Any) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:.{float_digits}f}"
        return str(value).replace("\n", " ")

    rows = [
        "| " + " | ".join(str(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        rows.append("| " + " | ".join(format_value(row[column]) for column in columns) + " |")
    return "\n".join(rows)


def percent_delta(value: float, reference: float) -> float:
    if not np.isfinite(value) or not np.isfinite(reference) or reference == 0:
        return np.nan
    return float(100.0 * (value - reference) / reference)


def summarize_differences(diff: np.ndarray) -> dict[str, float]:
    valid = diff[np.isfinite(diff)]
    if valid.size == 0:
        return {
            "daily_days_compared": 0,
            "daily_mean_diff_ugm3": np.nan,
            "daily_median_diff_ugm3": np.nan,
            "daily_mae_ugm3": np.nan,
            "daily_p95_abs_diff_ugm3": np.nan,
            "daily_max_abs_diff_ugm3": np.nan,
        }
    return {
        "daily_days_compared": int(valid.size),
        "daily_mean_diff_ugm3": float(np.mean(valid)),
        "daily_median_diff_ugm3": float(np.median(valid)),
        "daily_mae_ugm3": float(np.mean(np.abs(valid))),
        "daily_p95_abs_diff_ugm3": float(np.quantile(np.abs(valid), 0.95)),
        "daily_max_abs_diff_ugm3": float(np.max(np.abs(valid))),
    }


def row_nanmean(values: np.ndarray) -> np.ndarray:
    valid_count = np.isfinite(values).sum(axis=1)
    row_sum = np.nansum(values, axis=1)
    return np.divide(
        row_sum,
        valid_count,
        out=np.full(values.shape[0], np.nan, dtype=float),
        where=valid_count > 0,
    )


def column_nanmean(values: np.ndarray) -> np.ndarray:
    valid_count = np.isfinite(values).sum(axis=0)
    column_sum = np.nansum(values, axis=0)
    return np.divide(
        column_sum,
        valid_count,
        out=np.full(values.shape[1], np.nan, dtype=float),
        where=valid_count > 0,
    )


def reference_construction(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_values = bundle.source_values.astype(float)
    daily_values = bundle.daily_values.astype(float)

    baseline_period = float(np.nanmean(column_nanmean(source_values)))
    source_observation_weighted = float(np.nanmean(source_values))
    source_time_equal = float(np.nanmean(row_nanmean(source_values)))
    daily_sensor_equal = float(np.nanmean(column_nanmean(daily_values)))
    daily_day_equal = float(np.nanmean(row_nanmean(daily_values)))
    daily_observation_weighted = float(np.nanmean(daily_values))

    period_rows = []
    for estimand_name, value, note in [
        ("sensor_equal_source_period", baseline_period, "Primary finite-population estimand"),
        ("source_observation_weighted", source_observation_weighted, "Each valid sensor-time cell has equal weight"),
        ("source_time_equal_network_mean", source_time_equal, "Each source timestamp has equal weight"),
        ("sensor_equal_daily_period", daily_sensor_equal, "Sensor-equal mean after daily aggregation"),
        ("day_equal_daily_network_mean", daily_day_equal, "Each daily network mean has equal weight"),
        ("daily_observation_weighted", daily_observation_weighted, "Each valid daily sensor-day has equal weight"),
    ]:
        period_rows.append(
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "estimand_variant": estimand_name,
                "period_mean_pm25_ugm3": value,
                "delta_vs_primary_ugm3": value - baseline_period,
                "delta_vs_primary_pct": percent_delta(value, baseline_period),
                "note": note,
            }
        )

    daily_two_step = row_nanmean(daily_values)
    daily_pooled = row_nanmean(daily_values)
    if bundle.spec.source_frequency == "hourly":
        source = pd.DataFrame(source_values, index=pd.to_datetime(bundle.source_timestamps).strftime("%Y-%m-%d"))
        daily_pooled = source.groupby(level=0, sort=True).apply(lambda frame: np.nanmean(frame.to_numpy(dtype=float))).to_numpy()
    daily_diff = daily_pooled - daily_two_step
    daily_row = {
        "dataset_key": bundle.spec.key,
        "city": bundle.spec.city,
        "daily_comparison": "pooled_valid_observations_minus_two_step_sensor_mean",
        **summarize_differences(daily_diff),
    }
    return pd.DataFrame(period_rows), pd.DataFrame([daily_row])


def project_locations(locations: pd.DataFrame) -> tuple[np.ndarray, float, float, float, float]:
    lat0 = float(locations["Latitude"].mean())
    lon0 = float(locations["Longitude"].mean())
    scale_x = 111.320 * math.cos(math.radians(lat0))
    scale_y = 110.574
    x = (locations["Longitude"].to_numpy(dtype=float) - lon0) * scale_x
    y = (locations["Latitude"].to_numpy(dtype=float) - lat0) * scale_y
    return np.column_stack([x, y]), lat0, lon0, scale_x, scale_y


def convex_hull(points: np.ndarray) -> np.ndarray:
    ordered = sorted(set(map(tuple, points.tolist())))
    if len(ordered) <= 2:
        return np.asarray(ordered)

    def cross(origin: tuple[float, float], left: tuple[float, float], right: tuple[float, float]) -> float:
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], dtype=float)


def approximate_voronoi_weights(locations: pd.DataFrame, grid_size: int = SPATIAL_GRID_SIZE) -> tuple[np.ndarray, int]:
    xy, *_ = project_locations(locations)
    if len(xy) == 1:
        return np.ones(1), 1
    hull = convex_hull(xy)
    if len(hull) < 3:
        return np.repeat(1.0 / len(xy), len(xy)), 0
    path = MplPath(hull)
    x_grid = np.linspace(float(hull[:, 0].min()), float(hull[:, 0].max()), grid_size)
    y_grid = np.linspace(float(hull[:, 1].min()), float(hull[:, 1].max()), grid_size)
    xx, yy = np.meshgrid(x_grid, y_grid)
    grid_points = np.column_stack([xx.ravel(), yy.ravel()])
    inside = path.contains_points(grid_points)
    inside_points = grid_points[inside]
    if len(inside_points) == 0:
        return np.repeat(1.0 / len(xy), len(xy)), 0
    tree = cKDTree(xy)
    nearest = tree.query(inside_points, k=1)[1]
    counts = np.bincount(nearest, minlength=len(xy)).astype(float)
    if counts.sum() == 0:
        return np.repeat(1.0 / len(xy), len(xy)), 0
    return counts / counts.sum(), int(counts.sum())


def weighted_nanmean(values: np.ndarray, weights: np.ndarray, axis: int = 1) -> np.ndarray:
    valid = np.isfinite(values)
    if axis == 1:
        numerator = np.nansum(np.where(valid, values * weights[None, :], 0.0), axis=1)
        denominator = np.sum(np.where(valid, weights[None, :], 0.0), axis=1)
    else:
        numerator = np.nansum(np.where(valid, values * weights[:, None], 0.0), axis=0)
        denominator = np.sum(np.where(valid, weights[:, None], 0.0), axis=0)
    return np.divide(numerator, denominator, out=np.full_like(numerator, np.nan, dtype=float), where=denominator > 0)


def spatial_weighting(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    locations = read_locations(bundle.spec)
    locations = locations.set_index("Sensor_ID").loc[list(bundle.sensor_ids)].reset_index()
    weights, grid_points = approximate_voronoi_weights(locations)
    equal_weights = np.repeat(1.0 / len(weights), len(weights))
    period_values = bundle.period_values.astype(float)
    daily_values = bundle.daily_values.astype(float)

    primary_period = float(np.nanmean(period_values))
    spatial_period = float(np.nansum(period_values * weights) / np.nansum(weights[np.isfinite(period_values)]))
    primary_daily = row_nanmean(daily_values)
    spatial_daily = weighted_nanmean(daily_values, weights, axis=1)
    daily_diff = spatial_daily - primary_daily

    summary = pd.DataFrame(
        [
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "sensor_count": len(bundle.sensor_ids),
                "grid_points_inside_hull": grid_points,
                "primary_equal_sensor_period_mean_ugm3": primary_period,
                "approx_voronoi_weighted_period_mean_ugm3": spatial_period,
                "period_delta_weighted_minus_equal_ugm3": spatial_period - primary_period,
                "period_delta_weighted_minus_equal_pct": percent_delta(spatial_period, primary_period),
                "max_sensor_weight_pct": float(100.0 * np.max(weights)),
                "min_sensor_weight_pct": float(100.0 * np.min(weights)),
                "median_sensor_weight_pct": float(100.0 * np.median(weights)),
                "effective_sensor_count_from_weights": float(1.0 / np.sum(weights**2)),
                **summarize_differences(daily_diff),
            }
        ]
    )
    daily = pd.DataFrame(
        {
            "dataset_key": bundle.spec.key,
            "city": bundle.spec.city,
            "date": bundle.daily_dates,
            "equal_sensor_daily_mean_ugm3": primary_daily,
            "approx_voronoi_weighted_daily_mean_ugm3": spatial_daily,
            "weighted_minus_equal_ugm3": daily_diff,
            "weighted_minus_equal_abs_ugm3": np.abs(daily_diff),
        }
    )
    sensor_weights = pd.DataFrame(
        {
            "dataset_key": bundle.spec.key,
            "city": bundle.spec.city,
            "sensor_id": bundle.sensor_ids,
            "station_name": bundle.station_names,
            "equal_weight_pct": equal_weights * 100.0,
            "approx_voronoi_weight_pct": weights * 100.0,
            "weight_ratio_vs_equal": weights / equal_weights,
            "period_mean_pm25_ugm3": period_values,
        }
    ).sort_values(["city", "approx_voronoi_weight_pct"], ascending=[True, False])
    return summary, daily, sensor_weights


def leave_one_influence(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = bundle.daily_values.astype(float)
    period = bundle.period_values.astype(float)
    baseline_period = float(np.nanmean(period))
    daily_sum = np.nansum(daily, axis=1)
    daily_count = np.isfinite(daily).sum(axis=1)
    baseline_daily = np.divide(
        daily_sum,
        daily_count,
        out=np.full(len(daily_count), np.nan, dtype=float),
        where=daily_count > 0,
    )
    rows: list[dict[str, Any]] = []
    for sensor_index, sensor_id in enumerate(bundle.sensor_ids):
        leave_period_values = np.delete(period, sensor_index)
        leave_period = float(np.nanmean(leave_period_values))
        sensor_daily = daily[:, sensor_index]
        valid_sensor_day = np.isfinite(sensor_daily)
        leave_count = daily_count - valid_sensor_day.astype(int)
        leave_sum = daily_sum - np.where(valid_sensor_day, sensor_daily, 0.0)
        leave_daily = np.divide(
            leave_sum,
            leave_count,
            out=np.full(len(leave_count), np.nan, dtype=float),
            where=leave_count > 0,
        )
        diff = leave_daily - baseline_daily
        rows.append(
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "sensor_id": sensor_id,
                "station_name": bundle.station_names[sensor_index],
                "period_mean_pm25_ugm3": float(period[sensor_index]),
                "primary_period_mean_pm25_ugm3": baseline_period,
                "leave_one_period_mean_pm25_ugm3": leave_period,
                "period_shift_when_removed_ugm3": leave_period - baseline_period,
                "period_abs_shift_when_removed_ugm3": abs(leave_period - baseline_period),
                "period_shift_when_removed_pct": percent_delta(leave_period, baseline_period),
                **summarize_differences(diff),
            }
        )
    sensor_influence = pd.DataFrame(rows).sort_values(
        ["city", "period_abs_shift_when_removed_ugm3"], ascending=[True, False]
    )
    city_summary = (
        sensor_influence.groupby(["dataset_key", "city"], as_index=False)
        .agg(
            sensors=("sensor_id", "count"),
            max_period_abs_shift_ugm3=("period_abs_shift_when_removed_ugm3", "max"),
            median_period_abs_shift_ugm3=("period_abs_shift_when_removed_ugm3", "median"),
            max_daily_mae_ugm3=("daily_mae_ugm3", "max"),
            median_daily_mae_ugm3=("daily_mae_ugm3", "median"),
            max_daily_p95_abs_diff_ugm3=("daily_p95_abs_diff_ugm3", "max"),
        )
    )
    return sensor_influence, city_summary


def mc_summary(values: np.ndarray, sample_size: int, draws: int, seed: int) -> dict[str, float]:
    valid = values[np.isfinite(values)]
    population_size = len(valid)
    reference = float(np.mean(valid))
    rng = np.random.default_rng(seed)
    random_keys = rng.random((draws, population_size), dtype=np.float64)
    positions = np.argpartition(random_keys, sample_size - 1, axis=1)[:, :sample_size]
    estimates = valid[positions].mean(axis=1)
    abs_error = np.abs(estimates - reference)
    ape = abs_error / reference * 100.0 if reference != 0 else np.full_like(abs_error, np.nan)
    return {
        "draws": draws,
        "mdape_pct": float(np.median(ape)),
        "q75_ape_pct": float(np.quantile(ape, 0.75)),
        "q95_ape_pct": float(np.quantile(ape, 0.95)),
        "median_abs_error_ugm3": float(np.median(abs_error)),
        "q95_abs_error_ugm3": float(np.quantile(abs_error, 0.95)),
    }


def exact_summary(values: np.ndarray, sample_size: int) -> dict[str, float]:
    valid = values[np.isfinite(values)]
    reference = float(np.mean(valid))
    abs_errors: list[float] = []
    for combo in itertools.combinations(range(len(valid)), sample_size):
        estimate = float(np.mean(valid[list(combo)]))
        abs_errors.append(abs(estimate - reference))
    abs_error = np.asarray(abs_errors, dtype=float)
    ape = abs_error / reference * 100.0 if reference != 0 else np.full_like(abs_error, np.nan)
    return {
        "exact_combination_count": int(len(abs_error)),
        "exact_mdape_pct": float(np.median(ape)),
        "exact_q95_ape_pct": float(np.quantile(ape, 0.95)),
        "exact_median_abs_error_ugm3": float(np.median(abs_error)),
        "exact_q95_abs_error_ugm3": float(np.quantile(abs_error, 0.95)),
    }


def monte_carlo_stability(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    values = bundle.period_values.astype(float)
    population_size = int(np.isfinite(values).sum())
    rows: list[dict[str, Any]] = []
    for sample_size in MC_SAMPLE_SIZES:
        if sample_size >= population_size:
            continue
        for draws in MC_DRAWS:
            for master_seed in MC_SEEDS:
                seed = derive_seed(master_seed, "assumption_stress", bundle.spec.key, sample_size, draws)
                rows.append(
                    {
                        "dataset_key": bundle.spec.key,
                        "city": bundle.spec.city,
                        "population_size": population_size,
                        "sample_size": sample_size,
                        "master_seed": master_seed,
                        "derived_seed": seed,
                        **mc_summary(values, sample_size, draws, seed),
                    }
                )
    mc_runs = pd.DataFrame(rows)
    stability = (
        mc_runs.groupby(["dataset_key", "city", "population_size", "sample_size", "draws"], as_index=False)
        .agg(
            mdape_mean_pct=("mdape_pct", "mean"),
            mdape_sd_pct=("mdape_pct", "std"),
            mdape_min_pct=("mdape_pct", "min"),
            mdape_max_pct=("mdape_pct", "max"),
            mdape_range_pct=("mdape_pct", lambda values: float(np.max(values) - np.min(values))),
            q95_ape_mean_pct=("q95_ape_pct", "mean"),
            q95_ape_range_pct=("q95_ape_pct", lambda values: float(np.max(values) - np.min(values))),
            median_abs_error_mean_ugm3=("median_abs_error_ugm3", "mean"),
            median_abs_error_range_ugm3=("median_abs_error_ugm3", lambda values: float(np.max(values) - np.min(values))),
        )
    )

    exact_rows: list[dict[str, Any]] = []
    for sample_size in range(1, min(population_size, max(MC_SAMPLE_SIZES)) + 1):
        combinations = math.comb(population_size, sample_size)
        if combinations > EXACT_COMBINATION_CAP:
            continue
        exact_rows.append(
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "population_size": population_size,
                "sample_size": sample_size,
                **exact_summary(values, sample_size),
            }
        )
    exact = pd.DataFrame(exact_rows)
    if not exact.empty:
        mc_10k = mc_runs.loc[mc_runs["draws"] == 10_000]
        mc_10k_summary = (
            mc_10k.groupby(["dataset_key", "city", "population_size", "sample_size"], as_index=False)
            .agg(
                mc_10k_mdape_mean_pct=("mdape_pct", "mean"),
                mc_10k_mdape_range_pct=("mdape_pct", lambda values: float(np.max(values) - np.min(values))),
                mc_10k_q95_ape_mean_pct=("q95_ape_pct", "mean"),
            )
        )
        exact = exact.merge(
            mc_10k_summary,
            on=["dataset_key", "city", "population_size", "sample_size"],
            how="left",
        )
        exact["mc_minus_exact_mdape_pct_points"] = exact["mc_10k_mdape_mean_pct"] - exact["exact_mdape_pct"]
        exact["mc_minus_exact_q95_ape_pct_points"] = exact["mc_10k_q95_ape_mean_pct"] - exact["exact_q95_ape_pct"]
    return mc_runs, stability, exact


def imputation_sensitivity(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = pd.DataFrame(bundle.daily_values.astype(float), index=pd.to_datetime(bundle.daily_dates), columns=bundle.sensor_ids)
    baseline_daily = daily.mean(axis=1, skipna=True)
    baseline_period = float(daily.mean(axis=0, skipna=True).mean())
    sensor_period = daily.mean(axis=0, skipna=True)

    linear = daily.interpolate(method="time", limit_direction="both")
    sensor_mean_filled = daily.fillna(sensor_period)
    monthly = daily.copy()
    for month, group_index in daily.groupby(daily.index.month).groups.items():
        monthly_means = daily.loc[group_index].mean(axis=0, skipna=True)
        monthly.loc[group_index] = daily.loc[group_index].fillna(monthly_means).fillna(sensor_period)

    rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    for variant, frame, note in [
        ("linear_time_interpolation", linear, "Per-sensor daily interpolation, both directions"),
        ("sensor_period_mean_fill", sensor_mean_filled, "Fill each missing sensor-day with that sensor period mean"),
        ("sensor_month_mean_then_period_fill", monthly, "Fill missing sensor-day with same-sensor month mean, fallback period mean"),
    ]:
        variant_daily = frame.mean(axis=1, skipna=True)
        variant_period = float(frame.mean(axis=0, skipna=True).mean())
        diff = variant_daily.to_numpy(dtype=float) - baseline_daily.to_numpy(dtype=float)
        rows.append(
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "imputation_variant": variant,
                "baseline_period_mean_ugm3": baseline_period,
                "variant_period_mean_ugm3": variant_period,
                "period_delta_variant_minus_baseline_ugm3": variant_period - baseline_period,
                "period_delta_variant_minus_baseline_pct": percent_delta(variant_period, baseline_period),
                "note": note,
                **summarize_differences(diff),
            }
        )
        daily_rows.append(
            pd.DataFrame(
                {
                    "dataset_key": bundle.spec.key,
                    "city": bundle.spec.city,
                    "date": bundle.daily_dates,
                    "imputation_variant": variant,
                    "baseline_daily_mean_ugm3": baseline_daily.to_numpy(dtype=float),
                    "variant_daily_mean_ugm3": variant_daily.to_numpy(dtype=float),
                    "variant_minus_baseline_ugm3": diff,
                    "variant_minus_baseline_abs_ugm3": np.abs(diff),
                }
            )
        )
    return pd.DataFrame(rows), pd.concat(daily_rows, ignore_index=True)


def plot_period_sensitivities(reference: pd.DataFrame, spatial: pd.DataFrame, imputation: pd.DataFrame) -> None:
    setup_matplotlib()
    panels = [
        (
            reference.loc[reference["estimand_variant"] != "sensor_equal_source_period"].copy(),
            "estimand_variant",
            "delta_vs_primary_ugm3",
            "Reference construction alternatives",
        ),
        (
            spatial.copy(),
            "city",
            "period_delta_weighted_minus_equal_ugm3",
            "Approx. spatial weighting",
        ),
        (
            imputation.copy(),
            "imputation_variant",
            "period_delta_variant_minus_baseline_ugm3",
            "Imputation alternatives",
        ),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    for ax, (frame, label_col, value_col, title) in zip(axes, panels, strict=True):
        y_positions = np.arange(len(frame))
        colors = [color_for_dataset(key) for key in frame["dataset_key"]]
        ax.barh(y_positions, frame[value_col], color=colors, alpha=0.85)
        labels = frame["city"].astype(str) + ": " + frame[label_col].astype(str)
        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels, fontsize=7)
        ax.axvline(0, color=REFERENCE_LINE_COLOR, linewidth=1.0)
        ax.grid(axis="x", color=GRID_COLOR, linewidth=0.6)
        ax.set_title(title)
        ax.set_xlabel("Period mean shift (µg/m³)")
    save_figure(fig, PLOTS_DIR / "assumption_stress_period_mean_shifts", dpi=OUTPUT_DPI)


def plot_mc_stability(stability: pd.DataFrame) -> None:
    setup_matplotlib()
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True, sharey=True)
    for ax, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        subset = stability.loc[(stability["city"] == city) & (stability["draws"] == 10_000)]
        ax.plot(
            subset["sample_size"],
            subset["mdape_range_pct"],
            marker="o",
            color=color_for_dataset(str(subset["dataset_key"].iloc[0])) if not subset.empty else "#111827",
        )
        ax.set_title(city)
        ax.set_xlabel("n")
        ax.grid(True, color=GRID_COLOR, linewidth=0.6)
    axes[0].set_ylabel("MdAPE range across 5 seeds (percentage points)")
    fig.suptitle("Monte Carlo seed stability at 10,000 draws")
    save_figure(fig, PLOTS_DIR / "assumption_stress_mc_seed_stability", dpi=OUTPUT_DPI)


def plot_top_influence(sensor_influence: pd.DataFrame) -> None:
    setup_matplotlib()
    top = (
        sensor_influence.sort_values("period_abs_shift_when_removed_ugm3", ascending=False)
        .groupby("city", group_keys=False)
        .head(8)
        .sort_values(["city", "period_abs_shift_when_removed_ugm3"])
    )
    labels = top["city"] + " " + top["sensor_id"].astype(str)
    fig, ax = plt.subplots(figsize=(8.5, max(4, 0.28 * len(top))))
    ax.barh(
        np.arange(len(top)),
        top["period_abs_shift_when_removed_ugm3"],
        color=[color_for_dataset(key) for key in top["dataset_key"]],
        alpha=0.85,
    )
    ax.set_yticks(np.arange(len(top)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("|Period mean shift if removed| (µg/m³)")
    ax.set_title("Most influential sensors under leave-one-out period mean")
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.6)
    save_figure(fig, PLOTS_DIR / "assumption_stress_top_leave_one_influence", dpi=OUTPUT_DPI)


def write_markdown(
    reference: pd.DataFrame,
    daily_reference: pd.DataFrame,
    spatial: pd.DataFrame,
    influence_city: pd.DataFrame,
    influence_sensor: pd.DataFrame,
    mc_stability: pd.DataFrame,
    exact: pd.DataFrame,
    imputation: pd.DataFrame,
) -> None:
    reference_display = reference.loc[reference["estimand_variant"] != "sensor_equal_source_period"].copy()
    top_influence = (
        influence_sensor.sort_values("period_abs_shift_when_removed_ugm3", ascending=False)
        .groupby("city", group_keys=False)
        .head(5)
        [
            [
                "city",
                "sensor_id",
                "station_name",
                "period_mean_pm25_ugm3",
                "period_abs_shift_when_removed_ugm3",
                "daily_mae_ugm3",
                "daily_p95_abs_diff_ugm3",
            ]
        ]
    )
    mc_10k = mc_stability.loc[mc_stability["draws"] == 10_000].copy()
    mc_key = (
        mc_10k.sort_values(["city", "sample_size"])
        [
            [
                "city",
                "sample_size",
                "mdape_mean_pct",
                "mdape_sd_pct",
                "mdape_range_pct",
                "q95_ape_range_pct",
                "median_abs_error_range_ugm3",
            ]
        ]
    )
    exact_display = exact[
        [
            "city",
            "sample_size",
            "exact_combination_count",
            "exact_mdape_pct",
            "mc_10k_mdape_mean_pct",
            "mc_minus_exact_mdape_pct_points",
            "exact_q95_ape_pct",
            "mc_minus_exact_q95_ape_pct_points",
        ]
    ].copy()
    lines = [
        "# Assumption Stress Tests",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Purpose",
        "",
        "This batch tests alternative assumptions that reviewers may ask about after the main analyses: reference-mean construction, approximate spatial weighting, leave-one-sensor influence, simple missing-data imputation, Monte Carlo seed stability, and exact enumeration where feasible.",
        "",
        "## Reference Construction Alternatives",
        "",
        markdown_table(
            reference_display[
                [
                    "city",
                    "estimand_variant",
                    "period_mean_pm25_ugm3",
                    "delta_vs_primary_ugm3",
                    "delta_vs_primary_pct",
                    "note",
                ]
            ]
        ),
        "",
        "## Daily Pooled-Observation Versus Two-Step Mean",
        "",
        markdown_table(daily_reference),
        "",
        "## Approximate Spatial Weighting Within Deployed Convex Hull",
        "",
        markdown_table(
            spatial[
                [
                    "city",
                    "sensor_count",
                    "grid_points_inside_hull",
                    "primary_equal_sensor_period_mean_ugm3",
                    "approx_voronoi_weighted_period_mean_ugm3",
                    "period_delta_weighted_minus_equal_ugm3",
                    "period_delta_weighted_minus_equal_pct",
                    "effective_sensor_count_from_weights",
                    "daily_mae_ugm3",
                    "daily_p95_abs_diff_ugm3",
                ]
            ]
        ),
        "",
        "## Leave-One-Sensor Influence",
        "",
        markdown_table(influence_city),
        "",
        "### Top Influential Sensors",
        "",
        markdown_table(top_influence),
        "",
        "## Imputation Alternatives",
        "",
        markdown_table(
            imputation[
                [
                    "city",
                    "imputation_variant",
                    "period_delta_variant_minus_baseline_ugm3",
                    "period_delta_variant_minus_baseline_pct",
                    "daily_mae_ugm3",
                    "daily_p95_abs_diff_ugm3",
                    "note",
                ]
            ]
        ),
        "",
        "## Monte Carlo Seed Stability At 10,000 Draws",
        "",
        markdown_table(mc_key),
        "",
        "## Exact Enumeration Where Feasible",
        "",
        markdown_table(exact_display),
        "",
        "## Interpretation",
        "",
        "- If reference-construction alternatives shift the period mean materially, the manuscript should emphasize that the primary target is a chosen finite-population estimand rather than a unique city truth.",
        "- Approximate Voronoi weighting is not a replacement for a population-weighted exposure model; it is a stress test for unequal spatial support within the deployed convex hull.",
        "- Leave-one-sensor influence identifies sensors that strongly affect the equal-sensor reference mean; it does not by itself justify exclusion.",
        "- Simple imputation checks whether the no-imputation choice is driving the reference mean. If imputation shifts are small, the current all-available-data approach is easier to defend.",
        "- Monte Carlo seed ranges at 10,000 draws quantify simulation noise. Exact enumeration rows show whether the Monte Carlo approximation is close where full enumeration is computationally feasible.",
        "",
        "## Output Inventory",
        "",
        "- `reference_construction_sensitivity.csv`",
        "- `daily_reference_construction_sensitivity.csv`",
        "- `spatial_weighting_sensitivity.csv`",
        "- `spatial_weighting_daily_differences.csv`",
        "- `spatial_weighting_sensor_weights.csv`",
        "- `leave_one_sensor_influence.csv`",
        "- `leave_one_city_summary.csv`",
        "- `missingness_imputation_sensitivity.csv`",
        "- `missingness_imputation_daily_differences.csv`",
        "- `monte_carlo_stability_runs.csv`",
        "- `monte_carlo_stability_summary.csv`",
        "- `monte_carlo_exact_enumeration_comparison.csv`",
        "",
    ]
    (RESULTS_DIR / "assumption_stress_tests.md").write_text("\n".join(lines))


def main() -> None:
    setup_matplotlib()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    bundles = {key: load_dataset(spec) for key, spec in DATASETS.items()}

    reference_rows: list[pd.DataFrame] = []
    daily_reference_rows: list[pd.DataFrame] = []
    spatial_rows: list[pd.DataFrame] = []
    spatial_daily_rows: list[pd.DataFrame] = []
    spatial_sensor_rows: list[pd.DataFrame] = []
    influence_rows: list[pd.DataFrame] = []
    influence_city_rows: list[pd.DataFrame] = []
    imputation_rows: list[pd.DataFrame] = []
    imputation_daily_rows: list[pd.DataFrame] = []
    mc_run_rows: list[pd.DataFrame] = []
    mc_stability_rows: list[pd.DataFrame] = []
    exact_rows: list[pd.DataFrame] = []
    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "master_seed": MASTER_SEED,
        "mc_master_seeds": MC_SEEDS,
        "mc_draws": MC_DRAWS,
        "mc_sample_sizes": MC_SAMPLE_SIZES,
        "exact_combination_cap": EXACT_COMBINATION_CAP,
        "spatial_grid_size": SPATIAL_GRID_SIZE,
        "datasets": {},
    }

    for bundle in bundles.values():
        reference, daily_reference = reference_construction(bundle)
        spatial, spatial_daily, spatial_sensor = spatial_weighting(bundle)
        influence, influence_city = leave_one_influence(bundle)
        imputation, imputation_daily = imputation_sensitivity(bundle)
        mc_runs, mc_stability, exact = monte_carlo_stability(bundle)

        reference_rows.append(reference)
        daily_reference_rows.append(daily_reference)
        spatial_rows.append(spatial)
        spatial_daily_rows.append(spatial_daily)
        spatial_sensor_rows.append(spatial_sensor)
        influence_rows.append(influence)
        influence_city_rows.append(influence_city)
        imputation_rows.append(imputation)
        imputation_daily_rows.append(imputation_daily)
        mc_run_rows.append(mc_runs)
        mc_stability_rows.append(mc_stability)
        exact_rows.append(exact)
        metadata["datasets"][bundle.spec.key] = {
            "city": bundle.spec.city,
            "source_frequency": bundle.spec.source_frequency,
            "input_hashes": bundle.input_hashes,
            "preprocessing": bundle.preprocessing,
        }

    reference = pd.concat(reference_rows, ignore_index=True)
    daily_reference = pd.concat(daily_reference_rows, ignore_index=True)
    spatial = pd.concat(spatial_rows, ignore_index=True)
    spatial_daily = pd.concat(spatial_daily_rows, ignore_index=True)
    spatial_sensor = pd.concat(spatial_sensor_rows, ignore_index=True)
    influence = pd.concat(influence_rows, ignore_index=True)
    influence_city = pd.concat(influence_city_rows, ignore_index=True)
    imputation = pd.concat(imputation_rows, ignore_index=True)
    imputation_daily = pd.concat(imputation_daily_rows, ignore_index=True)
    mc_runs = pd.concat(mc_run_rows, ignore_index=True)
    mc_stability = pd.concat(mc_stability_rows, ignore_index=True)
    exact = pd.concat(exact_rows, ignore_index=True)

    reference.to_csv(RESULTS_DIR / "reference_construction_sensitivity.csv", index=False)
    daily_reference.to_csv(RESULTS_DIR / "daily_reference_construction_sensitivity.csv", index=False)
    spatial.to_csv(RESULTS_DIR / "spatial_weighting_sensitivity.csv", index=False)
    spatial_daily.to_csv(RESULTS_DIR / "spatial_weighting_daily_differences.csv", index=False)
    spatial_sensor.to_csv(RESULTS_DIR / "spatial_weighting_sensor_weights.csv", index=False)
    influence.to_csv(RESULTS_DIR / "leave_one_sensor_influence.csv", index=False)
    influence_city.to_csv(RESULTS_DIR / "leave_one_city_summary.csv", index=False)
    imputation.to_csv(RESULTS_DIR / "missingness_imputation_sensitivity.csv", index=False)
    imputation_daily.to_csv(RESULTS_DIR / "missingness_imputation_daily_differences.csv", index=False)
    mc_runs.to_csv(RESULTS_DIR / "monte_carlo_stability_runs.csv", index=False)
    mc_stability.to_csv(RESULTS_DIR / "monte_carlo_stability_summary.csv", index=False)
    exact.to_csv(RESULTS_DIR / "monte_carlo_exact_enumeration_comparison.csv", index=False)
    (RESULTS_DIR / "assumption_stress_tests_metadata.json").write_text(json.dumps(metadata, indent=2))

    plot_period_sensitivities(reference, spatial, imputation)
    plot_mc_stability(mc_stability)
    plot_top_influence(influence)
    write_markdown(reference, daily_reference, spatial, influence_city, influence, mc_stability, exact, imputation)

    print(f"Wrote assumption stress tests to {RESULTS_DIR.relative_to(REPO_ROOT)}")
    print(f"Wrote assumption stress plots to {PLOTS_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
