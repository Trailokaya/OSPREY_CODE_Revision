from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


for thread_env_var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(thread_env_var, "1")


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "monte_carlo" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import GRID_COLOR, OUTPUT_DPI, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402
from run_main_monte_carlo import (  # noqa: E402
    DATASETS,
    draw_sample_positions,
    load_dataset,
    summarize_estimates,
)
from run_finite_population_experiment import derive_phase_seed  # noqa: E402
from run_selection_strategy_experiment import STRATEGY_CONFIGS  # noqa: E402


RESULTS_ROOT = REPO_ROOT / "analysis" / "results" / "finite_population_experiments"
OUTPUT_DIR = RESULTS_ROOT / "reference_target_sensitivity"
REVIEW_PACKET = RESULTS_ROOT / "finite_population_review_packet"
PLOT_MIRROR = REPO_ROOT / "analysis" / "plots" / "finite_population_high_resolution_pdf"
DEFAULT_MASTER_SEED = 20260528
DEFAULT_INNER_DRAWS = 10_000
DEFAULT_TARGET_N_STAR = 50
SAMPLE_SIZES = [5, 10, 20]


RUN_CONFIGS = {
    "chicago_phase4_strategy_n50": {
        "city": "Chicago",
        "dataset_key": "chicago_lcs_corrected_no_collocation",
        "phase": 4,
        "phase_dir": RESULTS_ROOT / "phase4_chicago_selection_strategies",
        "target_N_star": 50,
        "full_N_label": "N=277",
        "strategy_column": True,
        "daily_existing_selected_summary": RESULTS_ROOT
        / "phase4_chicago_selection_strategies"
        / "aggregated"
        / "daily_strategy_summary_n50.csv",
    },
    "lucknow_phase3_random_n50": {
        "city": "Lucknow",
        "dataset_key": "lucknow_lcs",
        "phase": 3,
        "phase_dir": RESULTS_ROOT / "phase3_lucknow_downsampling",
        "target_N_star": 50,
        "full_N_label": "N=71",
        "strategy_column": False,
        "daily_existing_selected_summary": None,
    },
}


CITY_DATASET_KEYS = {
    "Chicago": "chicago_lcs_corrected_no_collocation",
    "Lucknow": "lucknow_lcs",
}


def resolve_n_jobs(requested: int) -> int:
    cpu_count = max(1, os.cpu_count() or 1)
    if requested in {0, -1}:
        return cpu_count
    if requested < -1:
        return max(1, cpu_count + requested + 1)
    return min(requested, cpu_count)


def selected_sensor_hash(sensor_ids: list[str]) -> str:
    return hashlib.sha256("\0".join(sensor_ids).encode("utf-8")).hexdigest()[:16]


def compute_estimates(values: np.ndarray, sample_positions: np.ndarray) -> np.ndarray:
    return values[sample_positions].mean(axis=1)


def full_daily_mean_and_sd(daily_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    valid = np.isfinite(daily_values)
    counts = valid.sum(axis=1)
    sums = np.where(valid, daily_values, 0.0).sum(axis=1)
    means = np.divide(sums, counts, out=np.full(len(counts), np.nan), where=counts > 0)
    sds = np.full(len(counts), np.nan)
    for row_index, count in enumerate(counts):
        if count > 1:
            sds[row_index] = float(np.nanstd(daily_values[row_index], ddof=1))
    return means, sds


def selected_daily_mean_vs_full(
    *,
    seeds: pd.DataFrame,
    sensor_ids: list[str],
    daily_values: np.ndarray,
    daily_dates: list[str],
    config: dict[str, Any],
) -> pd.DataFrame:
    sensor_index = {sensor_id: index for index, sensor_id in enumerate(sensor_ids)}
    full_mean, _ = full_daily_mean_and_sd(daily_values)
    rows: list[dict[str, Any]] = []
    for seed_row in seeds.to_dict("records"):
        selected_ids = [str(sensor_id) for sensor_id in json.loads(seed_row["selected_sensor_ids"])]
        selected_indices = np.asarray([sensor_index[sensor_id] for sensor_id in selected_ids], dtype=np.int32)
        selected_values = daily_values[:, selected_indices]
        valid = np.isfinite(selected_values)
        counts = valid.sum(axis=1)
        sums = np.where(valid, selected_values, 0.0).sum(axis=1)
        selected_mean = np.divide(sums, counts, out=np.full(len(counts), np.nan), where=counts > 0)
        absolute_error = np.abs(selected_mean - full_mean)
        percentage_error = np.where(
            np.isfinite(full_mean) & (full_mean != 0),
            absolute_error / np.abs(full_mean) * 100.0,
            np.nan,
        )
        for row_index, date in enumerate(daily_dates):
            if not np.isfinite(selected_mean[row_index]) or not np.isfinite(full_mean[row_index]):
                continue
            row = {
                "run_key": str(config["run_key"]),
                "phase": int(config["phase"]),
                "city": str(config["city"]),
                "dataset_key": str(config["dataset_key"]),
                "target_N_star": int(config["target_N_star"]),
                "outer_draw_index": int(seed_row["outer_seed_index"]),
                "outer_seed_value": int(seed_row["outer_seed_value"]),
                "selected_sensor_set_hash": str(seed_row["selected_sensor_set_hash"]),
                "time_index": str(date),
                "selected_network_mean_ugm3": float(selected_mean[row_index]),
                "full_network_mean_ugm3": float(full_mean[row_index]),
                "selected_mean_abs_error_vs_full_ugm3": float(absolute_error[row_index]),
                "selected_mean_ape_vs_full_pct": float(percentage_error[row_index]),
                "selected_valid_sensor_count": int(counts[row_index]),
                "full_valid_sensor_count": int(np.isfinite(daily_values[row_index]).sum()),
            }
            if "selection_strategy" in seed_row:
                row["selection_strategy"] = str(seed_row["selection_strategy"])
                row["selection_strategy_label"] = str(seed_row["selection_strategy_label"])
            else:
                row["selection_strategy"] = "random"
                row["selection_strategy_label"] = "Random"
            rows.append(row)
    return pd.DataFrame(rows)


def period_worker(args: tuple[dict[str, Any], dict[str, Any], list[str], np.ndarray, float, float, list[int], int]) -> pd.DataFrame:
    seed_row, config, sensor_ids, period_values, full_period_mean, full_period_sd, sample_sizes, n_inner_draws = args
    sensor_index = {sensor_id: index for index, sensor_id in enumerate(sensor_ids)}
    selected_ids = [str(sensor_id) for sensor_id in json.loads(seed_row["selected_sensor_ids"])]
    selected_indices = np.asarray([sensor_index[sensor_id] for sensor_id in selected_ids], dtype=np.int32)
    selected_values_all = period_values[selected_indices]
    valid_positions = np.flatnonzero(np.isfinite(selected_values_all))
    values = selected_values_all[valid_positions]
    population_size = len(values)
    selected_hash = selected_sensor_hash(selected_ids)
    rows: list[dict[str, Any]] = []
    for sample_size in range(2, 31):
        if sample_size > population_size:
            continue
        task_seed = derive_phase_seed(int(seed_row["inner_seed_value"]), "period", sample_size, selected_hash)
        sample_positions = draw_sample_positions(population_size, sample_size, n_inner_draws, task_seed)
        sample_estimates = compute_estimates(values, sample_positions)
        row = {
            "run_key": str(config["run_key"]),
            "phase": int(config["phase"]),
            "city": str(config["city"]),
            "dataset_key": str(config["dataset_key"]),
            "target_N_star": int(config["target_N_star"]),
            "outer_draw_index": int(seed_row["outer_seed_index"]),
            "outer_seed_value": int(seed_row["outer_seed_value"]),
            "inner_seed_value": int(seed_row["inner_seed_value"]),
            "selected_sensor_set_hash": selected_hash,
            "selected_sensor_count": len(selected_indices),
            "time_aggregation": "period",
            "reference_scope": "full_network_period_mean",
            "time_index": "study_period",
            "sample_size": sample_size,
            "n_sensors_available": population_size,
            "full_network_sensor_count": int(np.isfinite(period_values).sum()),
            "n_draws_requested": n_inner_draws,
            "n_draws_completed": n_inner_draws,
            "reference_mean_ugm3": float(full_period_mean),
            "reference_sd_ugm3": float(full_period_sd),
            "task_seed_used": int(task_seed),
        }
        if "selection_strategy" in seed_row:
            row["selection_strategy"] = str(seed_row["selection_strategy"])
            row["selection_strategy_label"] = str(seed_row["selection_strategy_label"])
        else:
            row["selection_strategy"] = "random"
            row["selection_strategy_label"] = "Random"
        row.update(
            summarize_estimates(
                sample_estimates=sample_estimates,
                reference_mean=float(full_period_mean),
                reference_sd=float(full_period_sd),
                sample_size=sample_size,
                population_size=population_size,
            )
        )
        rows.append(row)
    return pd.DataFrame(rows)


def daily_worker(
    args: tuple[
        dict[str, Any],
        dict[str, Any],
        list[str],
        np.ndarray,
        list[str],
        np.ndarray,
        np.ndarray,
        list[int],
        int,
    ],
) -> pd.DataFrame:
    seed_row, config, sensor_ids, daily_values, daily_dates, full_mean, full_sd, sample_sizes, n_inner_draws = args
    sensor_index = {sensor_id: index for index, sensor_id in enumerate(sensor_ids)}
    selected_ids = [str(sensor_id) for sensor_id in json.loads(seed_row["selected_sensor_ids"])]
    selected_indices = np.asarray([sensor_index[sensor_id] for sensor_id in selected_ids], dtype=np.int32)
    selected_hash = selected_sensor_hash(selected_ids)
    selected_values = daily_values[:, selected_indices]
    valid_masks = np.isfinite(selected_values)
    sample_position_cache: dict[tuple[int, int], tuple[int, np.ndarray]] = {}
    rows: list[dict[str, Any]] = []
    for sample_size in sample_sizes:
        groups: dict[tuple[int, ...], list[int]] = {}
        for row_index, mask in enumerate(valid_masks):
            valid_positions = tuple(np.flatnonzero(mask).astype(int).tolist())
            if len(valid_positions) >= sample_size and np.isfinite(full_mean[row_index]):
                groups.setdefault(valid_positions, []).append(row_index)
        for valid_positions_tuple, row_indices in groups.items():
            valid_positions = np.asarray(valid_positions_tuple, dtype=np.int32)
            population_size = len(valid_positions)
            cache_key = (sample_size, population_size)
            if cache_key not in sample_position_cache:
                task_seed = derive_phase_seed(
                    int(seed_row["inner_seed_value"]),
                    "daily",
                    sample_size,
                    population_size,
                )
                sample_position_cache[cache_key] = (
                    task_seed,
                    draw_sample_positions(population_size, sample_size, n_inner_draws, task_seed),
                )
            task_seed, sample_positions = sample_position_cache[cache_key]
            for row_index in row_indices:
                values = selected_values[row_index, valid_positions]
                sample_estimates = compute_estimates(values, sample_positions)
                row = {
                    "run_key": str(config["run_key"]),
                    "phase": int(config["phase"]),
                    "city": str(config["city"]),
                    "dataset_key": str(config["dataset_key"]),
                    "target_N_star": int(config["target_N_star"]),
                    "outer_draw_index": int(seed_row["outer_seed_index"]),
                    "outer_seed_value": int(seed_row["outer_seed_value"]),
                    "inner_seed_value": int(seed_row["inner_seed_value"]),
                    "selected_sensor_set_hash": selected_hash,
                    "selected_sensor_count": len(selected_indices),
                    "time_aggregation": "daily",
                    "reference_scope": "full_network_daily_mean",
                    "time_index": str(daily_dates[row_index]),
                    "sample_size": sample_size,
                    "n_sensors_available": population_size,
                    "full_network_valid_sensor_count": int(np.isfinite(daily_values[row_index]).sum()),
                    "n_draws_requested": n_inner_draws,
                    "n_draws_completed": n_inner_draws,
                    "reference_mean_ugm3": float(full_mean[row_index]),
                    "reference_sd_ugm3": float(full_sd[row_index]) if np.isfinite(full_sd[row_index]) else np.nan,
                    "task_seed_used": int(task_seed),
                }
                if "selection_strategy" in seed_row:
                    row["selection_strategy"] = str(seed_row["selection_strategy"])
                    row["selection_strategy_label"] = str(seed_row["selection_strategy_label"])
                else:
                    row["selection_strategy"] = "random"
                    row["selection_strategy_label"] = "Random"
                row.update(
                    summarize_estimates(
                        sample_estimates=sample_estimates,
                        reference_mean=float(full_mean[row_index]),
                        reference_sd=float(full_sd[row_index]) if np.isfinite(full_sd[row_index]) else np.nan,
                        sample_size=sample_size,
                        population_size=population_size,
                    )
                )
                rows.append(row)
    return pd.DataFrame(rows)


def quantile_envelope(frame: pd.DataFrame, group_cols: list[str], value_col: str) -> pd.DataFrame:
    grouped = frame.groupby(group_cols, dropna=False)[value_col]
    return grouped.agg(
        value_median="median",
        value_p5=lambda values: values.quantile(0.05),
        value_p25=lambda values: values.quantile(0.25),
        value_p75=lambda values: values.quantile(0.75),
        value_p95=lambda values: values.quantile(0.95),
        value_mean="mean",
        value_sd="std",
        n_outer_draws="count",
    ).reset_index()


def summarize_selected_reference(
    *,
    phase_dir: Path,
    target_n_star: int,
    strategy_column: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_draw_path = phase_dir / "aggregated" / "all_draw_summaries.parquet"
    compact_path = phase_dir / "aggregated" / f"selected_reference_draw_summaries_n{target_n_star}.parquet"
    selected_path = all_draw_path if all_draw_path.exists() else compact_path
    if not selected_path.exists():
        raise FileNotFoundError(
            "Missing selected-reference draw summaries. Expected "
            f"{compact_path.relative_to(REPO_ROOT)} in the review package, or the full "
            f"{all_draw_path.relative_to(REPO_ROOT)} from a full phase recomputation."
        )
    all_rows = pd.read_parquet(selected_path)
    subset = all_rows[(all_rows["target_N_star"] == target_n_star) & (all_rows["sample_size"] == 10)].copy()
    if not strategy_column:
        subset["selection_strategy"] = "random"
        subset["selection_strategy_label"] = "Random"
    group_cols = ["selection_strategy", "selection_strategy_label", "time_aggregation"]
    period = subset[subset["time_aggregation"] == "period"].copy()
    daily = subset[subset["time_aggregation"] == "daily"].copy()
    period_summary = (
        period.groupby(group_cols, dropna=False)
        .agg(
            selected_ref_mdape_pct=("ape_median_pct", "median"),
            selected_ref_abs_ugm3=("absolute_error_median_ugm3", "median"),
            selected_ref_rows=("ape_median_pct", "count"),
        )
        .reset_index()
    )
    daily_summary = (
        daily.groupby(group_cols, dropna=False)
        .agg(
            selected_ref_mdape_pct=("ape_median_pct", "median"),
            selected_ref_abs_ugm3=("absolute_error_median_ugm3", "median"),
            selected_ref_rows=("ape_median_pct", "count"),
            n_days=("time_index", "nunique"),
        )
        .reset_index()
    )
    return period_summary, daily_summary


def load_existing_daily_selected_summary(path: Path) -> pd.DataFrame:
    summary = pd.read_csv(path)
    summary = summary[summary["sample_size"] == 10].copy()
    return pd.DataFrame(
        {
            "selection_strategy": summary["selection_strategy"],
            "selection_strategy_label": summary["selection_strategy_label"],
            "time_aggregation": "daily",
            "selected_ref_mdape_pct": summary["daily_mdape_median_across_draw_days_pct"],
            "selected_ref_abs_ugm3": summary["daily_abs_error_median_across_draw_days_ugm3"],
            "selected_ref_rows": summary["n_outer_day_rows"],
            "n_days": summary["n_days"],
        }
    )


def summarize_full_reference(full_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    n10 = full_rows[full_rows["sample_size"] == 10].copy()
    group_cols = ["selection_strategy", "selection_strategy_label", "time_aggregation"]
    period = n10[n10["time_aggregation"] == "period"].copy()
    daily = n10[n10["time_aggregation"] == "daily"].copy()
    period_summary = (
        period.groupby(group_cols, dropna=False)
        .agg(
            full_ref_mdape_pct=("ape_median_pct", "median"),
            full_ref_abs_ugm3=("absolute_error_median_ugm3", "median"),
            full_ref_rows=("ape_median_pct", "count"),
        )
        .reset_index()
    )
    daily_summary = (
        daily.groupby(group_cols, dropna=False)
        .agg(
            full_ref_mdape_pct=("ape_median_pct", "median"),
            full_ref_abs_ugm3=("absolute_error_median_ugm3", "median"),
            full_ref_rows=("ape_median_pct", "count"),
            n_days=("time_index", "nunique"),
        )
        .reset_index()
    )
    return period_summary, daily_summary


def build_comparison(
    selected_summary: pd.DataFrame,
    full_summary: pd.DataFrame,
    *,
    run_key: str,
    city: str,
    target_n_star: int,
) -> pd.DataFrame:
    merged = selected_summary.merge(
        full_summary,
        on=["selection_strategy", "selection_strategy_label", "time_aggregation"],
        how="outer",
    )
    merged.insert(0, "run_key", run_key)
    merged.insert(1, "city", city)
    merged.insert(2, "target_N_star", target_n_star)
    merged.insert(3, "sample_size", 10)
    merged["mdape_increase_pctpt"] = merged["full_ref_mdape_pct"] - merged["selected_ref_mdape_pct"]
    merged["abs_increase_ugm3"] = merged["full_ref_abs_ugm3"] - merged["selected_ref_abs_ugm3"]
    return merged


def run_config(config_key: str, n_jobs: int, n_inner_draws: int) -> dict[str, pd.DataFrame]:
    base_config = dict(RUN_CONFIGS[config_key])
    base_config["run_key"] = config_key
    bundle = load_dataset(DATASETS[str(base_config["dataset_key"])])
    sensor_ids = list(bundle.sensor_ids)
    seeds = pd.read_csv(Path(base_config["phase_dir"]) / "config" / "outer_seeds.csv")
    seeds = seeds[seeds["target_N_star"] == int(base_config["target_N_star"])].copy()
    if seeds.empty:
        raise ValueError(f"No selected subsets found for {config_key}")

    full_period_values = bundle.period_values[np.isfinite(bundle.period_values)]
    full_period_mean = float(np.nanmean(full_period_values))
    full_period_sd = float(np.nanstd(full_period_values, ddof=1))
    full_daily_mean, full_daily_sd = full_daily_mean_and_sd(bundle.daily_values)

    period_args = [
        (
            row,
            base_config,
            sensor_ids,
            bundle.period_values,
            full_period_mean,
            full_period_sd,
            SAMPLE_SIZES,
            n_inner_draws,
        )
        for row in seeds.to_dict("records")
    ]
    daily_args = [
        (
            row,
            base_config,
            sensor_ids,
            bundle.daily_values,
            list(bundle.daily_dates),
            full_daily_mean,
            full_daily_sd,
            SAMPLE_SIZES,
            n_inner_draws,
        )
        for row in seeds.to_dict("records")
    ]
    frames: list[pd.DataFrame] = []
    with ProcessPoolExecutor(max_workers=n_jobs) as executor:
        futures = [executor.submit(period_worker, args) for args in period_args]
        futures.extend(executor.submit(daily_worker, args) for args in daily_args)
        for future in as_completed(futures):
            frames.append(future.result())
    full_rows = pd.concat(frames, ignore_index=True).sort_values(
        ["time_aggregation", "selection_strategy", "outer_draw_index", "time_index", "sample_size"]
    )

    selected_mean_daily = selected_daily_mean_vs_full(
        seeds=seeds,
        sensor_ids=sensor_ids,
        daily_values=bundle.daily_values,
        daily_dates=list(bundle.daily_dates),
        config=base_config,
    )
    selected_period_summary, selected_daily_summary = summarize_selected_reference(
        phase_dir=Path(base_config["phase_dir"]),
        target_n_star=int(base_config["target_N_star"]),
        strategy_column=bool(base_config["strategy_column"]),
    )
    existing_daily_selected_summary = base_config.get("daily_existing_selected_summary")
    if existing_daily_selected_summary and Path(existing_daily_selected_summary).exists():
        selected_daily_summary = load_existing_daily_selected_summary(
            Path(existing_daily_selected_summary)
        )
    full_period_summary, full_daily_summary = summarize_full_reference(full_rows)
    period_comparison = build_comparison(
        selected_period_summary,
        full_period_summary,
        run_key=config_key,
        city=str(base_config["city"]),
        target_n_star=int(base_config["target_N_star"]),
    )
    daily_comparison = build_comparison(
        selected_daily_summary,
        full_daily_summary,
        run_key=config_key,
        city=str(base_config["city"]),
        target_n_star=int(base_config["target_N_star"]),
    )

    selected_mean_daily_summary = (
        selected_mean_daily.groupby(["selection_strategy", "selection_strategy_label"], dropna=False)
        .agg(
            selected_mean_abs_error_vs_full_median_ugm3=(
                "selected_mean_abs_error_vs_full_ugm3",
                "median",
            ),
            selected_mean_abs_error_vs_full_p5_ugm3=(
                "selected_mean_abs_error_vs_full_ugm3",
                lambda values: values.quantile(0.05),
            ),
            selected_mean_abs_error_vs_full_p95_ugm3=(
                "selected_mean_abs_error_vs_full_ugm3",
                lambda values: values.quantile(0.95),
            ),
            selected_mean_ape_vs_full_median_pct=("selected_mean_ape_vs_full_pct", "median"),
        )
        .reset_index()
    )
    selected_mean_daily_summary.insert(0, "run_key", config_key)
    selected_mean_daily_summary.insert(1, "city", str(base_config["city"]))
    selected_mean_daily_summary.insert(2, "target_N_star", int(base_config["target_N_star"]))

    return {
        "full_rows": full_rows,
        "period_comparison": period_comparison,
        "daily_comparison": daily_comparison,
        "selected_mean_daily": selected_mean_daily,
        "selected_mean_daily_summary": selected_mean_daily_summary,
    }


def color_for_city(city: str) -> str:
    return color_for_dataset(CITY_DATASET_KEYS.get(city, city.lower()))


def apply_strategy_axis(axis: plt.Axes, positions: np.ndarray, labels: pd.Series) -> None:
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, rotation=25, ha="right")
    if len(positions) == 1:
        axis.set_xlim(-0.85, 0.85)
    elif len(positions) > 1:
        axis.set_xlim(-0.55, float(len(positions)) - 0.45)


def plot_reference_comparison(comparison: pd.DataFrame, output_base: Path, title: str) -> None:
    setup_matplotlib()
    frame = comparison.copy()
    order = frame.sort_values("full_ref_abs_ugm3")["selection_strategy"].tolist()
    frame["order"] = frame["selection_strategy"].map({strategy: index for index, strategy in enumerate(order)})
    frame = frame.sort_values("order")
    x = np.arange(len(frame))
    width = 0.28
    full_reference_color = color_for_city(str(frame["city"].iloc[0])) if "city" in frame and not frame.empty else "#111827"
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.8))
    axes[0].bar(x - width / 2, frame["selected_ref_mdape_pct"], width=width, color="#9ca3af", label="Selected N*=50 reference")
    axes[0].bar(x + width / 2, frame["full_ref_mdape_pct"], width=width, color=full_reference_color, label="Full-network reference")
    axes[0].set_ylabel("Median MdAPE at n=10 (%)")
    axes[1].bar(x - width / 2, frame["selected_ref_abs_ugm3"], width=width, color="#9ca3af", label="Selected N*=50 reference")
    axes[1].bar(x + width / 2, frame["full_ref_abs_ugm3"], width=width, color=full_reference_color, label="Full-network reference")
    axes[1].set_ylabel("Median absolute error at n=10 (µg/m³)")
    for axis in axes:
        apply_strategy_axis(axis, x, frame["selection_strategy_label"])
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    fig.suptitle(title)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=[0, 0.08, 1, 1])
    save_figure(fig, output_base, dpi=OUTPUT_DPI)


def write_summary(all_period: pd.DataFrame, all_daily: pd.DataFrame, selected_mean_summary: pd.DataFrame) -> None:
    lines = [
        "# Reference-Target Sensitivity",
        "",
        "This analysis keeps the same N*=50 selected populations and the same SRSWOR Monte Carlo sampling, but changes the reference target.",
        "",
        "- `selected_ref_*`: the original finite-population target, i.e., each selected N*=50 population's own mean.",
        "- `full_ref_*`: the larger deployed-network target, i.e., Chicago N=277 or Lucknow N=71.",
        "- Values below are medians at n=10.",
        "",
        "## Period comparison",
        "",
    ]
    for row in all_period.sort_values(["city", "selection_strategy_label"]).itertuples(index=False):
        lines.append(
            f"- {row.city}, {row.selection_strategy_label}: selected-ref `{row.selected_ref_mdape_pct:.2f}%` / `{row.selected_ref_abs_ugm3:.3f}` µg/m³; "
            f"full-ref `{row.full_ref_mdape_pct:.2f}%` / `{row.full_ref_abs_ugm3:.3f}` µg/m³."
        )
    lines.extend(["", "## Daily comparison", ""])
    for row in all_daily.sort_values(["city", "selection_strategy_label"]).itertuples(index=False):
        lines.append(
            f"- {row.city}, {row.selection_strategy_label}: selected-ref `{row.selected_ref_mdape_pct:.2f}%` / `{row.selected_ref_abs_ugm3:.3f}` µg/m³; "
            f"full-ref `{row.full_ref_mdape_pct:.2f}%` / `{row.full_ref_abs_ugm3:.3f}` µg/m³."
        )
    lines.extend(["", "## Selected N*=50 mean vs full-network daily mean", ""])
    for row in selected_mean_summary.sort_values(["city", "selection_strategy_label"]).itertuples(index=False):
        lines.append(
            f"- {row.city}, {row.selection_strategy_label}: median daily selected-mean error vs full network = "
            f"`{row.selected_mean_abs_error_vs_full_median_ugm3:.3f}` µg/m³."
        )
    (OUTPUT_DIR / "reference_target_sensitivity_summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    global RESULTS_ROOT, OUTPUT_DIR, REVIEW_PACKET, PLOT_MIRROR, RUN_CONFIGS

    parser = argparse.ArgumentParser()
    parser.add_argument("--inner-draws", type=int, default=DEFAULT_INNER_DRAWS)
    parser.add_argument("--n-jobs", type=int, default=0)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--plot-mirror", type=Path, default=PLOT_MIRROR)
    args = parser.parse_args()

    RESULTS_ROOT = args.results_root
    OUTPUT_DIR = args.output_dir or RESULTS_ROOT / "reference_target_sensitivity"
    REVIEW_PACKET = RESULTS_ROOT / "finite_population_review_packet"
    PLOT_MIRROR = args.plot_mirror
    RUN_CONFIGS = {
        **RUN_CONFIGS,
        "chicago_phase4_strategy_n50": {
            **RUN_CONFIGS["chicago_phase4_strategy_n50"],
            "phase_dir": RESULTS_ROOT / "phase4_chicago_selection_strategies",
            "daily_existing_selected_summary": RESULTS_ROOT
            / "phase4_chicago_selection_strategies"
            / "aggregated"
            / "daily_strategy_summary_n50.csv",
        },
        "lucknow_phase3_random_n50": {
            **RUN_CONFIGS["lucknow_phase3_random_n50"],
            "phase_dir": RESULTS_ROOT / "phase3_lucknow_downsampling",
        },
    }

    n_jobs = resolve_n_jobs(args.n_jobs)
    aggregated_dir = OUTPUT_DIR / "aggregated"
    plots_dir = OUTPUT_DIR / "plots"
    aggregated_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    outputs = {key: run_config(key, n_jobs=n_jobs, n_inner_draws=args.inner_draws) for key in RUN_CONFIGS}

    all_full_rows = pd.concat([value["full_rows"] for value in outputs.values()], ignore_index=True)
    all_period = pd.concat([value["period_comparison"] for value in outputs.values()], ignore_index=True)
    all_daily = pd.concat([value["daily_comparison"] for value in outputs.values()], ignore_index=True)
    selected_mean_summary = pd.concat(
        [value["selected_mean_daily_summary"] for value in outputs.values()],
        ignore_index=True,
    )
    all_full_rows.to_parquet(aggregated_dir / "full_reference_draw_summaries_n50.parquet", index=False)
    all_full_rows.to_csv(aggregated_dir / "full_reference_draw_summaries_n50.csv", index=False)
    all_period.to_csv(aggregated_dir / "period_selected_vs_full_reference_n50.csv", index=False)
    all_daily.to_csv(aggregated_dir / "daily_selected_vs_full_reference_n50.csv", index=False)
    selected_mean_summary.to_csv(aggregated_dir / "selected_mean_vs_full_daily_summary_n50.csv", index=False)

    plot_reference_comparison(
        all_period[all_period["city"] == "Chicago"],
        plots_dir / "chicago_period_selected_vs_full_reference_n50_seed20260528",
        "Chicago N*=50 period error: selected reference vs full N=277",
    )
    plot_reference_comparison(
        all_daily[all_daily["city"] == "Chicago"],
        plots_dir / "chicago_daily_selected_vs_full_reference_n50_seed20260528",
        "Chicago N*=50 daily error: selected reference vs full N=277",
    )
    plot_reference_comparison(
        all_period[all_period["city"] == "Lucknow"],
        plots_dir / "lucknow_period_selected_vs_full_reference_n50_seed20260528",
        "Lucknow N*=50 period error: selected reference vs full N=71",
    )
    plot_reference_comparison(
        all_daily[all_daily["city"] == "Lucknow"],
        plots_dir / "lucknow_daily_selected_vs_full_reference_n50_seed20260528",
        "Lucknow N*=50 daily error: selected reference vs full N=71",
    )

    packet_data = REVIEW_PACKET / "data"
    packet_plots = REVIEW_PACKET / "plots"
    packet_data.mkdir(parents=True, exist_ok=True)
    packet_plots.mkdir(parents=True, exist_ok=True)
    for source in [
        aggregated_dir / "period_selected_vs_full_reference_n50.csv",
        aggregated_dir / "daily_selected_vs_full_reference_n50.csv",
        aggregated_dir / "selected_mean_vs_full_daily_summary_n50.csv",
    ]:
        shutil.copy2(source, packet_data / source.name)
    PLOT_MIRROR.mkdir(parents=True, exist_ok=True)
    for source in plots_dir.glob("*"):
        if source.suffix.lower() in {".pdf", ".png"}:
            shutil.copy2(source, packet_plots / source.name)
            shutil.copy2(source, PLOT_MIRROR / source.name)

    write_summary(all_period, all_daily, selected_mean_summary)
    print(f"Wrote reference-target sensitivity outputs to {OUTPUT_DIR}")
    print("\nPeriod n=10")
    print(all_period.sort_values(["city", "full_ref_abs_ugm3"]).to_string(index=False))
    print("\nDaily n=10")
    print(all_daily.sort_values(["city", "full_ref_abs_ugm3"]).to_string(index=False))


if __name__ == "__main__":
    main()
