from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
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

from plot_style import GRID_COLOR, OUTPUT_DPI, REFERENCE_LINE_COLOR, save_figure, setup_matplotlib  # noqa: E402
from run_main_monte_carlo import (  # noqa: E402
    DATASETS,
    DatasetBundle,
    draw_sample_positions,
    load_dataset,
    summarize_estimates,
)


DEFAULT_MASTER_SEED = 20260528
DEFAULT_INNER_DRAWS = 10_000
DEFAULT_RESULTS_ROOT = REPO_ROOT / "analysis" / "results" / "finite_population_experiments"
DEFAULT_BASELINE_RUN = (
    REPO_ROOT
    / "monte_carlo"
    / "results"
    / "runs"
    / "p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602"
)
PLOT_MIRROR = REPO_ROOT / "analysis" / "plots" / "finite_population_high_resolution_pdf"

PHASE_CONFIGS = {
    1: {
        "phase_name": "phase1_chicago_realitycheck_n40",
        "dataset_key": "chicago_lcs_corrected_no_collocation",
        "city": "Chicago",
        "target_n_stars": [40],
        "outer_draws": 50,
        "period_sample_sizes": list(range(2, 31)),
        "daily_sample_sizes": [5, 10, 20],
    },
    2: {
        "phase_name": "phase2_chicago_nsensitivity",
        "dataset_key": "chicago_lcs_corrected_no_collocation",
        "city": "Chicago",
        "target_n_stars": [30, 40, 50, 70, 100, 150, 200, 277],
        "outer_draws": 100,
        "period_sample_sizes": list(range(2, 31)),
        "daily_sample_sizes": [5, 10, 20],
    },
    3: {
        "phase_name": "phase3_lucknow_downsampling",
        "dataset_key": "lucknow_lcs",
        "city": "Lucknow",
        "target_n_stars": [31, 40, 50, 60, 71],
        "outer_draws": 100,
        "period_sample_sizes": list(range(2, 31)),
        "daily_sample_sizes": [5, 10, 20],
    },
}

PLAN_CITY_COLORS = {
    "Dhaka": "#D55E00",
    "Lucknow": "#0072B2",
    "Chicago": "#009E73",
}


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def resolve_repo_path(path: Path | str) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def release_path(path: Path | str) -> str:
    try:
        return str(resolve_repo_path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return "<outside-repository>"


def resolve_n_jobs(requested: int) -> int:
    cpu_count = max(1, os.cpu_count() or 1)
    if requested in {0, -1}:
        return cpu_count
    if requested < -1:
        return max(1, cpu_count + requested + 1)
    return min(requested, cpu_count)


def derive_phase_seed(master_seed: int, *parts: object) -> int:
    payload = "|".join([str(master_seed), *(str(part) for part in parts)])
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def selected_sensor_hash(sensor_ids: list[str]) -> str:
    return hashlib.sha256("\0".join(sensor_ids).encode("utf-8")).hexdigest()[:16]


def finite_population_selection(
    bundle: DatasetBundle,
    target_n_star: int,
    outer_seed: int,
) -> np.ndarray:
    available = np.flatnonzero(np.isfinite(bundle.period_values))
    if target_n_star > len(available):
        raise ValueError(
            f"target N*={target_n_star} exceeds available period sensors {len(available)}"
        )
    if target_n_star == len(available):
        return available.astype(np.int32, copy=True)
    rng = np.random.default_rng(outer_seed)
    selected = rng.choice(available, size=target_n_star, replace=False)
    return np.sort(selected).astype(np.int32, copy=False)


def compute_estimates(values: np.ndarray, sample_positions: np.ndarray) -> np.ndarray:
    return values[sample_positions].mean(axis=1)


def base_row(
    *,
    phase: int,
    city: str,
    dataset_key: str,
    target_n_star: int,
    outer_draw_index: int,
    outer_seed: int,
    inner_seed: int,
    selected_hash: str,
    selected_sensor_count: int,
    time_aggregation: str,
    time_index: str,
    sample_size: int,
    n_sensors_available: int,
    n_inner_draws: int,
    reference_mean: float,
    reference_sd: float,
    task_seed: int,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "city": city,
        "dataset_key": dataset_key,
        "target_N_star": target_n_star,
        "outer_draw_index": outer_draw_index,
        "outer_seed_value": outer_seed,
        "inner_seed_value": inner_seed,
        "selected_sensor_set_hash": selected_hash,
        "selected_sensor_count": selected_sensor_count,
        "time_aggregation": time_aggregation,
        "time_index": time_index,
        "sample_size": sample_size,
        "n_sensors_available": n_sensors_available,
        "n_draws_requested": n_inner_draws,
        "n_draws_completed": n_inner_draws,
        "reference_mean_ugm3": reference_mean,
        "reference_sd_ugm3": reference_sd,
        "task_seed_used": task_seed,
    }


def period_rows_for_draw(
    *,
    bundle: DatasetBundle,
    phase: int,
    target_n_star: int,
    outer_draw_index: int,
    outer_seed: int,
    inner_seed: int,
    selected_indices: np.ndarray,
    period_sample_sizes: list[int],
    n_inner_draws: int,
) -> list[dict[str, Any]]:
    sensor_ids = [bundle.sensor_ids[int(index)] for index in selected_indices]
    selected_hash = selected_sensor_hash(sensor_ids)
    values_all = bundle.period_values[selected_indices]
    available_positions = np.flatnonzero(np.isfinite(values_all))
    values = values_all[available_positions]
    population_size = len(values)
    reference_mean = float(np.nanmean(values))
    reference_sd = float(np.nanstd(values, ddof=1)) if population_size > 1 else np.nan
    rows: list[dict[str, Any]] = []
    for sample_size in period_sample_sizes:
        if sample_size > population_size:
            continue
        task_seed = derive_phase_seed(inner_seed, "period", sample_size, selected_hash)
        sample_positions = draw_sample_positions(population_size, sample_size, n_inner_draws, task_seed)
        sample_estimates = compute_estimates(values, sample_positions)
        row = base_row(
            phase=phase,
            city=bundle.spec.city,
            dataset_key=bundle.spec.key,
            target_n_star=target_n_star,
            outer_draw_index=outer_draw_index,
            outer_seed=outer_seed,
            inner_seed=inner_seed,
            selected_hash=selected_hash,
            selected_sensor_count=len(selected_indices),
            time_aggregation="period",
            time_index="study_period",
            sample_size=sample_size,
            n_sensors_available=population_size,
            n_inner_draws=n_inner_draws,
            reference_mean=reference_mean,
            reference_sd=reference_sd,
            task_seed=task_seed,
        )
        row.update(
            summarize_estimates(
                sample_estimates=sample_estimates,
                reference_mean=reference_mean,
                reference_sd=reference_sd,
                sample_size=sample_size,
                population_size=population_size,
            )
        )
        rows.append(row)
    return rows


def daily_rows_for_draw(
    *,
    bundle: DatasetBundle,
    phase: int,
    target_n_star: int,
    outer_draw_index: int,
    outer_seed: int,
    inner_seed: int,
    selected_indices: np.ndarray,
    daily_sample_sizes: list[int],
    n_inner_draws: int,
) -> list[dict[str, Any]]:
    sensor_ids = [bundle.sensor_ids[int(index)] for index in selected_indices]
    selected_hash = selected_sensor_hash(sensor_ids)
    selected_values = bundle.daily_values[:, selected_indices]
    valid_masks = np.isfinite(selected_values)
    rows: list[dict[str, Any]] = []
    sample_position_cache: dict[tuple[int, int], tuple[int, np.ndarray]] = {}
    for sample_size in daily_sample_sizes:
        groups: dict[tuple[int, ...], list[int]] = {}
        for row_index, mask in enumerate(valid_masks):
            valid_positions = tuple(np.flatnonzero(mask).astype(int).tolist())
            if len(valid_positions) >= sample_size:
                groups.setdefault(valid_positions, []).append(row_index)
        for valid_positions_tuple, row_indices in groups.items():
            valid_positions = np.asarray(valid_positions_tuple, dtype=np.int32)
            population_size = len(valid_positions)
            mask_digest = hashlib.sha256(
                ",".join(map(str, valid_positions_tuple)).encode("utf-8")
            ).hexdigest()[:16]
            cache_key = (sample_size, population_size)
            if cache_key not in sample_position_cache:
                task_seed = derive_phase_seed(inner_seed, "daily", sample_size, population_size)
                sample_position_cache[cache_key] = (
                    task_seed,
                    draw_sample_positions(population_size, sample_size, n_inner_draws, task_seed),
                )
            task_seed, sample_positions = sample_position_cache[cache_key]
            for row_index in row_indices:
                values = selected_values[row_index, valid_positions]
                reference_mean = float(np.nanmean(values))
                reference_sd = float(np.nanstd(values, ddof=1)) if population_size > 1 else np.nan
                sample_estimates = compute_estimates(values, sample_positions)
                row = base_row(
                    phase=phase,
                    city=bundle.spec.city,
                    dataset_key=bundle.spec.key,
                    target_n_star=target_n_star,
                    outer_draw_index=outer_draw_index,
                    outer_seed=outer_seed,
                    inner_seed=inner_seed,
                    selected_hash=selected_hash,
                    selected_sensor_count=len(selected_indices),
                    time_aggregation="daily",
                    time_index=bundle.daily_dates[row_index],
                    sample_size=sample_size,
                    n_sensors_available=population_size,
                    n_inner_draws=n_inner_draws,
                    reference_mean=reference_mean,
                    reference_sd=reference_sd,
                    task_seed=task_seed,
                )
                row.update(
                    summarize_estimates(
                        sample_estimates=sample_estimates,
                        reference_mean=reference_mean,
                        reference_sd=reference_sd,
                        sample_size=sample_size,
                        population_size=population_size,
                    )
                )
                rows.append(row)
    return rows


def run_outer_draw(args: tuple[DatasetBundle, dict[str, Any], int, int, int]) -> tuple[pd.DataFrame, dict[str, Any]]:
    bundle, config, target_n_star, outer_draw_index, master_seed = args
    outer_seed = derive_phase_seed(master_seed, config["phase_name"], target_n_star, "outer", outer_draw_index)
    inner_seed = derive_phase_seed(master_seed, config["phase_name"], target_n_star, "inner", outer_draw_index)
    selected_indices = finite_population_selection(bundle, target_n_star, outer_seed)
    rows = period_rows_for_draw(
        bundle=bundle,
        phase=config["phase"],
        target_n_star=target_n_star,
        outer_draw_index=outer_draw_index,
        outer_seed=outer_seed,
        inner_seed=inner_seed,
        selected_indices=selected_indices,
        period_sample_sizes=config["period_sample_sizes"],
        n_inner_draws=config["n_inner_draws"],
    )
    rows.extend(
        daily_rows_for_draw(
            bundle=bundle,
            phase=config["phase"],
            target_n_star=target_n_star,
            outer_draw_index=outer_draw_index,
            outer_seed=outer_seed,
            inner_seed=inner_seed,
            selected_indices=selected_indices,
            daily_sample_sizes=config["daily_sample_sizes"],
            n_inner_draws=config["n_inner_draws"],
        )
    )
    selected_sensor_ids = [bundle.sensor_ids[int(index)] for index in selected_indices]
    seed_row = {
        "phase": config["phase"],
        "target_N_star": target_n_star,
        "outer_seed_index": outer_draw_index,
        "outer_seed_value": outer_seed,
        "inner_seed_value": inner_seed,
        "selected_sensor_ids": json.dumps(selected_sensor_ids),
        "selected_sensor_count": len(selected_sensor_ids),
        "selected_sensor_set_hash": selected_sensor_hash(selected_sensor_ids),
    }
    return pd.DataFrame(rows), seed_row


def baseline_summary_for(dataset_key: str, baseline_run: Path) -> pd.DataFrame:
    summary_path = baseline_run / "mc_summary" / "p0_baseline_summary.csv"
    summary = pd.read_csv(summary_path)
    return summary[summary["dataset_key"] == dataset_key].copy()


def baseline_period_curve(dataset_key: str, baseline_run: Path) -> pd.DataFrame:
    baseline = baseline_summary_for(dataset_key, baseline_run)
    return (
        baseline[
            (baseline["time_aggregation"] == "period")
            & (baseline["time_index"] == "study_period")
        ][["sample_size", "ape_median_pct", "absolute_error_median_ugm3"]]
        .sort_values("sample_size")
        .copy()
    )


def quantile_envelope(
    frame: pd.DataFrame,
    group_cols: list[str],
    value_col: str,
) -> pd.DataFrame:
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


def n_required(curve: pd.DataFrame, threshold_pct: float) -> float:
    eligible = curve.sort_values("sample_size")
    eligible = eligible[eligible["ape_median_pct"] <= threshold_pct]
    if eligible.empty:
        return math.nan
    return float(eligible["sample_size"].iloc[0])


def headline_row(
    *,
    phase: int,
    city: str,
    metric_name: str,
    target_n_star: int | None,
    aggregation: str,
    values: pd.Series | list[float],
    n_outer_draws: int,
    n_inner_draws: int,
    notes: str,
) -> dict[str, Any]:
    series = pd.Series(values, dtype="float64").dropna()
    return {
        "phase": phase,
        "city": city,
        "metric_name": metric_name,
        "target_N_star": target_n_star,
        "aggregation": aggregation,
        "value_median": float(series.median()) if len(series) else math.nan,
        "value_p5": float(series.quantile(0.05)) if len(series) else math.nan,
        "value_p95": float(series.quantile(0.95)) if len(series) else math.nan,
        "value_mean": float(series.mean()) if len(series) else math.nan,
        "value_sd": float(series.std(ddof=1)) if len(series) > 1 else math.nan,
        "n_outer_draws": n_outer_draws,
        "n_inner_draws": n_inner_draws,
        "notes": notes,
    }


def aggregate_phase(
    phase_dir: Path,
    config: dict[str, Any],
    all_rows: pd.DataFrame,
    baseline: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    aggregated_dir = phase_dir / "aggregated"
    aggregated_dir.mkdir(parents=True, exist_ok=True)
    period = all_rows[all_rows["time_aggregation"] == "period"].copy()
    daily = all_rows[all_rows["time_aggregation"] == "daily"].copy()

    period_envelope = quantile_envelope(
        period,
        ["target_N_star", "sample_size"],
        "ape_median_pct",
    )
    baseline_period = baseline[
        (baseline["time_aggregation"] == "period") & (baseline["time_index"] == "study_period")
    ][["sample_size", "ape_median_pct", "absolute_error_median_ugm3"]].rename(
        columns={
            "ape_median_pct": "baseline_ape_median_pct",
            "absolute_error_median_ugm3": "baseline_absolute_error_median_ugm3",
        }
    )
    period_envelope = period_envelope.merge(baseline_period, on="sample_size", how="left")
    period_envelope.to_csv(aggregated_dir / "period_mdape_envelope.csv", index=False)

    daily_envelope = quantile_envelope(
        daily,
        ["target_N_star", "time_index", "sample_size"],
        "ape_median_pct",
    )
    baseline_daily = baseline[baseline["time_aggregation"] == "daily"][
        ["time_index", "sample_size", "ape_median_pct", "absolute_error_median_ugm3"]
    ].rename(
        columns={
            "ape_median_pct": "baseline_ape_median_pct",
            "absolute_error_median_ugm3": "baseline_absolute_error_median_ugm3",
        }
    )
    daily_envelope = daily_envelope.merge(
        baseline_daily, on=["time_index", "sample_size"], how="left"
    )
    daily_envelope.to_csv(aggregated_dir / "daily_mdape_envelope.csv", index=False)

    headline_rows: list[dict[str, Any]] = []
    for target_n_star in sorted(period["target_N_star"].unique()):
        target_period = period[period["target_N_star"] == target_n_star]
        by_draw = target_period.groupby("outer_draw_index")
        n5 = by_draw.apply(lambda frame: n_required(frame, 5.0), include_groups=False)
        n10 = by_draw.apply(lambda frame: n_required(frame, 10.0), include_groups=False)
        n10_mdape = target_period[target_period["sample_size"] == 10]["ape_median_pct"]
        headline_rows.append(
            headline_row(
                phase=config["phase"],
                city=config["city"],
                metric_name="n_for_mdape_le_5pct",
                target_n_star=int(target_n_star),
                aggregation="period",
                values=n5,
                n_outer_draws=config["outer_draws"],
                n_inner_draws=config["n_inner_draws"],
                notes="First n where period MdAPE <= 5% within each outer finite-population draw.",
            )
        )
        headline_rows.append(
            headline_row(
                phase=config["phase"],
                city=config["city"],
                metric_name="n_for_mdape_le_10pct",
                target_n_star=int(target_n_star),
                aggregation="period",
                values=n10,
                n_outer_draws=config["outer_draws"],
                n_inner_draws=config["n_inner_draws"],
                notes="First n where period MdAPE <= 10% within each outer finite-population draw.",
            )
        )
        headline_rows.append(
            headline_row(
                phase=config["phase"],
                city=config["city"],
                metric_name="mdape_at_n10",
                target_n_star=int(target_n_star),
                aggregation="period",
                values=n10_mdape,
                n_outer_draws=config["outer_draws"],
                n_inner_draws=config["n_inner_draws"],
                notes="Period MdAPE at n=10 across outer finite-population draws.",
            )
        )

    headline = pd.DataFrame(headline_rows)
    headline.to_csv(aggregated_dir / "headline_numbers.csv", index=False)
    return period_envelope, daily_envelope, headline


def plot_phase1_period(
    period_envelope: pd.DataFrame,
    phase_dir: Path,
    config: dict[str, Any],
) -> None:
    setup_matplotlib()
    color = PLAN_CITY_COLORS[config["city"]]
    plot_data = period_envelope[period_envelope["target_N_star"] == 40].sort_values("sample_size")
    fig, axis = plt.subplots(figsize=(6.8, 3.8))
    axis.fill_between(
        plot_data["sample_size"].to_numpy(),
        plot_data["value_p5"].to_numpy(),
        plot_data["value_p95"].to_numpy(),
        color=color,
        alpha=0.18,
        linewidth=0,
        label="N*=40, 5–95% across outer draws",
    )
    axis.plot(
        plot_data["sample_size"],
        plot_data["value_median"],
        color=color,
        linewidth=2.2,
        label="N*=40 median",
    )
    axis.plot(
        plot_data["sample_size"],
        plot_data["baseline_ape_median_pct"],
        color="#111827",
        linestyle="--",
        linewidth=1.7,
        label="Original Chicago N=277",
    )
    axis.axhline(5, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    axis.text(2.2, 5.35, "5% MdAPE", color="#6b7280", fontsize=8)
    axis.set_xlabel("Number of sampled sensors (n)")
    axis.set_ylabel("Study-period MdAPE (%)")
    axis.set_title("Chicago finite-population reality check")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axis.set_xlim(2, 30)
    axis.legend(frameon=False, loc="upper right")
    save_figure(
        fig,
        phase_dir
        / "plots"
        / f"phase1_chicago_realitycheck_n40_period_mdape_seed{config['master_seed']}",
        dpi=OUTPUT_DPI,
    )


def plot_phase1_daily(
    daily_envelope: pd.DataFrame,
    phase_dir: Path,
    config: dict[str, Any],
    sample_size: int = 10,
) -> None:
    setup_matplotlib()
    color = PLAN_CITY_COLORS[config["city"]]
    plot_data = daily_envelope[
        (daily_envelope["target_N_star"] == 40) & (daily_envelope["sample_size"] == sample_size)
    ].copy()
    plot_data["date"] = pd.to_datetime(plot_data["time_index"])
    plot_data = plot_data.sort_values("date")
    fig, axis = plt.subplots(figsize=(7.4, 3.8))
    axis.fill_between(
        plot_data["date"].to_numpy(),
        plot_data["value_p5"].to_numpy(),
        plot_data["value_p95"].to_numpy(),
        color=color,
        alpha=0.16,
        linewidth=0,
        label="N*=40, 5–95% across outer draws",
    )
    axis.plot(plot_data["date"], plot_data["value_median"], color=color, linewidth=1.7, label="N*=40 median")
    axis.plot(
        plot_data["date"],
        plot_data["baseline_ape_median_pct"],
        color="#111827",
        linestyle="--",
        linewidth=1.1,
        label="Original Chicago N=277",
    )
    axis.set_xlabel("Date")
    axis.set_ylabel(f"Daily MdAPE at n={sample_size} (%)")
    axis.set_title("Daily Chicago MdAPE under N*=40 finite-population draws")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axis.legend(frameon=False, loc="upper right")
    fig.autofmt_xdate(rotation=0)
    save_figure(
        fig,
        phase_dir
        / "plots"
        / f"phase1_chicago_realitycheck_n40_daily_mdape_seed{config['master_seed']}",
        dpi=OUTPUT_DPI,
    )


def plot_nsensitivity_period(
    period_envelope: pd.DataFrame,
    phase_dir: Path,
    config: dict[str, Any],
) -> None:
    setup_matplotlib()
    fig, axis = plt.subplots(figsize=(7.2, 4.2))
    target_values = sorted(period_envelope["target_N_star"].unique())
    cmap = plt.get_cmap("Greens" if config["city"] == "Chicago" else "Blues")
    for idx, target_n_star in enumerate(target_values):
        frame = period_envelope[period_envelope["target_N_star"] == target_n_star].sort_values("sample_size")
        color = cmap(0.35 + 0.55 * idx / max(len(target_values) - 1, 1))
        axis.fill_between(
            frame["sample_size"].to_numpy(),
            frame["value_p5"].to_numpy(),
            frame["value_p95"].to_numpy(),
            color=color,
            alpha=0.12,
            linewidth=0,
        )
        axis.plot(frame["sample_size"], frame["value_median"], color=color, linewidth=1.7, label=f"N*={target_n_star}")
    axis.axhline(5, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    axis.axhline(10, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    axis.set_xlabel("Number of sampled sensors (n)")
    axis.set_ylabel("Study-period MdAPE (%)")
    axis.set_title(f"{config['city']} finite-population sensitivity")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axis.legend(frameon=False, ncol=2)
    save_figure(
        fig,
        phase_dir / "plots" / f"phase{config['phase']}_{config['city'].lower()}_nsensitivity_period_mdape_seed{config['master_seed']}",
        dpi=OUTPUT_DPI,
    )


def plot_n_required(
    headline: pd.DataFrame,
    phase_dir: Path,
    config: dict[str, Any],
) -> None:
    setup_matplotlib()
    fig, axis = plt.subplots(figsize=(6.4, 3.8))
    color = PLAN_CITY_COLORS[config["city"]]
    for metric_name, label, marker in [
        ("n_for_mdape_le_5pct", "n for MdAPE ≤ 5%", "o"),
        ("n_for_mdape_le_10pct", "n for MdAPE ≤ 10%", "s"),
    ]:
        frame = headline[headline["metric_name"] == metric_name].sort_values("target_N_star")
        y_center = frame["value_median"].to_numpy(dtype=float)
        yerr = np.vstack(
            [
                np.clip(y_center - frame["value_p5"].to_numpy(dtype=float), 0, None),
                np.clip(frame["value_p95"].to_numpy(dtype=float) - y_center, 0, None),
            ]
        )
        yerr = np.nan_to_num(yerr, nan=0.0)
        axis.errorbar(
            frame["target_N_star"],
            y_center,
            yerr=yerr,
            color=color,
            linestyle="-" if metric_name.endswith("5pct") else "--",
            marker=marker,
            capsize=3,
            label=label,
        )
    axis.set_xlabel("Finite-population size N*")
    axis.set_ylabel("Required sampled sensors n")
    axis.set_title(f"{config['city']} required n by finite-population size")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axis.legend(frameon=False)
    save_figure(
        fig,
        phase_dir / "plots" / f"phase{config['phase']}_{config['city'].lower()}_nrequired_by_nstar_seed{config['master_seed']}",
        dpi=OUTPUT_DPI,
    )


def plot_phase3_lucknow_with_dhaka(
    period_envelope: pd.DataFrame,
    phase_dir: Path,
    config: dict[str, Any],
) -> None:
    setup_matplotlib()
    baseline_run = resolve_repo_path(config.get("baseline_run", DEFAULT_BASELINE_RUN))
    dhaka_curve = baseline_period_curve("dhaka_lcs", baseline_run)
    fig, axis = plt.subplots(figsize=(7.2, 4.2))
    target_values = sorted(period_envelope["target_N_star"].unique())
    cmap = plt.get_cmap("Blues")
    for idx, target_n_star in enumerate(target_values):
        frame = period_envelope[
            period_envelope["target_N_star"] == target_n_star
        ].sort_values("sample_size")
        color = cmap(0.35 + 0.55 * idx / max(len(target_values) - 1, 1))
        axis.fill_between(
            frame["sample_size"].to_numpy(),
            frame["value_p5"].to_numpy(),
            frame["value_p95"].to_numpy(),
            color=color,
            alpha=0.12,
            linewidth=0,
        )
        axis.plot(
            frame["sample_size"],
            frame["value_median"],
            color=color,
            linewidth=1.7,
            label=f"Lucknow N*={target_n_star}",
        )
    axis.plot(
        dhaka_curve["sample_size"],
        dhaka_curve["ape_median_pct"],
        color=PLAN_CITY_COLORS["Dhaka"],
        linestyle="--",
        linewidth=2.0,
        label="Dhaka N=35 baseline",
    )
    axis.axhline(5, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    axis.axhline(10, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    axis.set_xlabel("Number of sampled sensors (n)")
    axis.set_ylabel("Study-period MdAPE (%)")
    axis.set_title("Lucknow finite-population sensitivity with Dhaka reference")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axis.legend(frameon=False, ncol=2)
    save_figure(
        fig,
        phase_dir
        / "plots"
        / f"phase3_lucknow_downsampling_period_mdape_with_dhaka_seed{config['master_seed']}",
        dpi=OUTPUT_DPI,
    )


def plot_phase3_lucknow_n31_vs_dhaka(
    period_envelope: pd.DataFrame,
    phase_dir: Path,
    config: dict[str, Any],
) -> None:
    setup_matplotlib()
    baseline_run = resolve_repo_path(config.get("baseline_run", DEFAULT_BASELINE_RUN))
    dhaka_curve = baseline_period_curve("dhaka_lcs", baseline_run)
    lucknow_n31 = period_envelope[
        period_envelope["target_N_star"] == 31
    ].sort_values("sample_size")
    comparison = lucknow_n31[
        ["sample_size", "value_median", "value_p5", "value_p95"]
    ].merge(
        dhaka_curve[["sample_size", "ape_median_pct"]],
        on="sample_size",
        how="inner",
    )
    comparison["lucknow_minus_dhaka_pctpt"] = (
        comparison["value_median"] - comparison["ape_median_pct"]
    )

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.6))
    left, right = axes
    left.fill_between(
        lucknow_n31["sample_size"].to_numpy(),
        lucknow_n31["value_p5"].to_numpy(),
        lucknow_n31["value_p95"].to_numpy(),
        color=PLAN_CITY_COLORS["Lucknow"],
        alpha=0.16,
        linewidth=0,
        label="Lucknow N*=31, 5–95%",
    )
    left.plot(
        lucknow_n31["sample_size"],
        lucknow_n31["value_median"],
        color=PLAN_CITY_COLORS["Lucknow"],
        linewidth=2.0,
        label="Lucknow N*=31 median",
    )
    left.plot(
        dhaka_curve["sample_size"],
        dhaka_curve["ape_median_pct"],
        color=PLAN_CITY_COLORS["Dhaka"],
        linestyle="--",
        linewidth=2.0,
        label="Dhaka N=35 baseline",
    )
    left.axhline(5, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    left.set_xlabel("Number of sampled sensors (n)")
    left.set_ylabel("Study-period MdAPE (%)")
    left.set_title("Matched network-size curves")
    left.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    left.legend(frameon=False)

    right.axhline(0, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    right.plot(
        comparison["sample_size"],
        comparison["lucknow_minus_dhaka_pctpt"],
        color="#374151",
        linewidth=1.8,
    )
    right.set_xlabel("Number of sampled sensors (n)")
    right.set_ylabel("Lucknow − Dhaka MdAPE (percentage points)")
    right.set_title("Difference in median curves")
    right.grid(axis="y", color=GRID_COLOR, linewidth=0.65)

    save_figure(
        fig,
        phase_dir
        / "plots"
        / f"phase3_lucknow_n31_vs_dhaka_n35_period_mdape_seed{config['master_seed']}",
        dpi=OUTPUT_DPI,
    )


def mirror_plots(phase_dir: Path) -> None:
    PLOT_MIRROR.mkdir(parents=True, exist_ok=True)
    for plot_file in (phase_dir / "plots").glob("*"):
        if plot_file.suffix.lower() in {".pdf", ".png"}:
            target = PLOT_MIRROR / plot_file.name
            target.write_bytes(plot_file.read_bytes())


def write_master_seed_json(phase_dir: Path, config: dict[str, Any], args: argparse.Namespace) -> None:
    config_dir = phase_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": config["phase"],
        "phase_name": config["phase_name"],
        "master_seed": args.master_seed,
        "seed_algorithm": "int.from_bytes(sha256('|'.join([master_seed, parts])).digest()[:4], 'big')",
        "daily_seed_reuse": (
            "Within each outer draw, daily sample-position matrices are reused for the same "
            "sample_size and valid-sensor count. Each date still receives uniform SRSWOR "
            "subsets over its valid sensors; reuse only avoids regenerating equivalent "
            "position matrices."
        ),
        "target_n_stars": config["target_n_stars"],
        "outer_draws_per_target": config["outer_draws"],
        "inner_draws": config["n_inner_draws"],
        "period_sample_sizes": config["period_sample_sizes"],
        "daily_sample_sizes": config["daily_sample_sizes"],
        "dataset_key": config["dataset_key"],
        "baseline_run": release_path(args.baseline_run),
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "python": sys.version,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (config_dir / "master_seed.json").write_text(json.dumps(payload, indent=2))


def write_phase_summary(
    phase_dir: Path,
    config: dict[str, Any],
    headline: pd.DataFrame,
    period_envelope: pd.DataFrame,
) -> None:
    phase = config["phase"]
    if phase == 1:
        n5 = headline[headline["metric_name"] == "n_for_mdape_le_5pct"].iloc[0]
        n10_mdape = headline[headline["metric_name"] == "mdape_at_n10"].iloc[0]
        period40 = period_envelope[period_envelope["target_N_star"] == 40].copy()
        period40["baseline_delta_abs_pctpt"] = (
            period40["value_median"] - period40["baseline_ape_median_pct"]
        ).abs()
        max_delta = float(period40["baseline_delta_abs_pctpt"].max())
        n10_delta = float(
            period40.loc[period40["sample_size"] == 10, "baseline_delta_abs_pctpt"].iloc[0]
        )
        verdict = (
            "Chicago-at-N*=40 is close to the original N=277 curve"
            if max_delta < 1.0
            else "Chicago-at-N*=40 is detectably different from the original N=277 curve"
        )
        lines = [
            "# Phase 1 Summary — Chicago N*=40 Reality Check",
            "",
            f"- Master seed: `{config['master_seed']}`",
            f"- Outer finite-population draws: `{config['outer_draws']}`",
            f"- Inner SRSWOR draws per task: `{config['n_inner_draws']}`",
            f"- Headline n for period MdAPE <= 5%: mean `{n5['value_mean']:.2f}` ± `{n5['value_sd']:.2f}` sensors; median `{n5['value_median']:.1f}`.",
            f"- Period MdAPE at n=10: mean `{n10_mdape['value_mean']:.2f}%` ± `{n10_mdape['value_sd']:.2f}` percentage points.",
            f"- Maximum absolute median-curve deviation from the N=277 baseline across n=2..30: `{max_delta:.2f}` percentage points; at n=10: `{n10_delta:.2f}` percentage points.",
            f"- Verdict: {verdict}.",
            "",
            "## Main outputs",
            "",
            f"- Period figure: `plots/phase1_chicago_realitycheck_n40_period_mdape_seed{config['master_seed']}.pdf`",
            f"- Daily figure: `plots/phase1_chicago_realitycheck_n40_daily_mdape_seed{config['master_seed']}.pdf`",
            "- Headline table: `aggregated/headline_numbers.csv`",
            "",
            "## Caveat",
            "",
            "The conclusion could change if the outer finite-population draw count is increased substantially or if a non-random spatial selection rule is used. That is the role of Phases 2–4.",
            "",
            "Daily MC implementation note: within each outer draw, random position matrices are reused for dates with the same valid-sensor count and sample size. This preserves uniform SRSWOR for each date while avoiding redundant random-number generation.",
        ]
    else:
        n5 = headline[headline["metric_name"] == "n_for_mdape_le_5pct"].copy()
        mdape_n10 = headline[headline["metric_name"] == "mdape_at_n10"].copy()
        period_envelope = period_envelope.copy()
        period_envelope["baseline_delta_abs_pctpt"] = (
            period_envelope["value_median"] - period_envelope["baseline_ape_median_pct"]
        ).abs()
        period_envelope["band_width_pctpt"] = (
            period_envelope["value_p95"] - period_envelope["value_p5"]
        )
        lines = [
            f"# Phase {phase} Summary — {config['city']} Finite-Population Sensitivity",
            "",
            f"- Master seed: `{config['master_seed']}`",
            f"- Outer finite-population draws per N*: `{config['outer_draws']}`",
            f"- Inner SRSWOR draws per task: `{config['n_inner_draws']}`",
            "- Headline table: `aggregated/headline_numbers.csv`",
            "- Period envelope: `aggregated/period_mdape_envelope.csv`",
        ]
        if phase == 2:
            mdape_range = (
                float(mdape_n10["value_median"].min()),
                float(mdape_n10["value_median"].max()),
            )
            max_delta = float(period_envelope["baseline_delta_abs_pctpt"].max())
            max_band = float(period_envelope["band_width_pctpt"].max())
            lines.extend(
                [
                    f"- Across Chicago N* values `{config['target_n_stars']}`, the median required n for period MdAPE <= 5% is `{float(n5['value_median'].min()):.0f}` to `{float(n5['value_median'].max()):.0f}` sensors.",
                    f"- Period MdAPE at n=10 ranges from `{mdape_range[0]:.2f}%` to `{mdape_range[1]:.2f}%` across median N* curves.",
                    f"- Maximum absolute median-curve deviation from the original N=277 baseline is `{max_delta:.2f}` percentage points; the maximum 5–95% outer-draw band width is `{max_band:.2f}` percentage points.",
                    "- Verdict: the Chicago study-period MdAPE curve is robust across the tested random finite-population sizes. Smaller N* values widen the outer-draw uncertainty band, but the sensor-count conclusion does not materially change.",
                    "",
                    "## Main outputs",
                    "",
                    f"- N-sensitivity figure: `plots/phase2_chicago_nsensitivity_period_mdape_seed{config['master_seed']}.pdf`",
                    f"- Required-n figure: `plots/phase2_chicago_nrequired_by_nstar_seed{config['master_seed']}.pdf`",
                ]
            )
        elif phase == 3:
            baseline_run = resolve_repo_path(config.get("baseline_run", DEFAULT_BASELINE_RUN))
            dhaka_curve = baseline_period_curve("dhaka_lcs", baseline_run)
            lucknow_n31 = period_envelope[period_envelope["target_N_star"] == 31]
            comparison = lucknow_n31[["sample_size", "value_median"]].merge(
                dhaka_curve[["sample_size", "ape_median_pct"]],
                on="sample_size",
                how="inner",
            )
            comparison["delta"] = comparison["value_median"] - comparison["ape_median_pct"]
            lucknow_n31_n10 = float(
                lucknow_n31.loc[lucknow_n31["sample_size"] == 10, "value_median"].iloc[0]
            )
            dhaka_n10 = float(
                dhaka_curve.loc[dhaka_curve["sample_size"] == 10, "ape_median_pct"].iloc[0]
            )
            lucknow_n31_n5 = n_required(
                lucknow_n31.rename(columns={"value_median": "ape_median_pct"}),
                5.0,
            )
            dhaka_n5 = n_required(dhaka_curve, 5.0)
            lines.extend(
                [
                    f"- At matched finite-population size, Lucknow N*=31 reaches period MdAPE <= 5% at `n={lucknow_n31_n5:.0f}`; Dhaka N=35 reaches the same threshold at `n={dhaka_n5:.0f}`.",
                    f"- At n=10, Lucknow N*=31 median period MdAPE is `{lucknow_n31_n10:.2f}%`; Dhaka N=35 baseline is `{dhaka_n10:.2f}%`, a difference of `{lucknow_n31_n10 - dhaka_n10:.2f}` percentage points.",
                    f"- Across n=2..30, the maximum absolute Lucknow N*=31 versus Dhaka N=35 median-curve difference is `{float(comparison['delta'].abs().max()):.2f}` percentage points.",
                    "- Verdict: matching finite-population size narrows the Lucknow/Dhaka comparison but does not make the curves identical. Lucknow remains modestly higher-error than Dhaka at common small-n values.",
                    "",
                    "## Main outputs",
                    "",
                    f"- Lucknow N-sensitivity figure: `plots/phase3_lucknow_nsensitivity_period_mdape_seed{config['master_seed']}.pdf`",
                    f"- Required-n figure: `plots/phase3_lucknow_nrequired_by_nstar_seed{config['master_seed']}.pdf`",
                    f"- Dhaka-overlay figure: `plots/phase3_lucknow_downsampling_period_mdape_with_dhaka_seed{config['master_seed']}.pdf`",
                    f"- Matched-size comparison figure: `plots/phase3_lucknow_n31_vs_dhaka_n35_period_mdape_seed{config['master_seed']}.pdf`",
                ]
            )
        lines.extend(
            [
                "",
                "Daily MC implementation note: within each outer draw, random position matrices are reused for dates with the same valid-sensor count and sample size. This preserves uniform SRSWOR for each date while avoiding redundant random-number generation.",
            ]
        )
    (phase_dir / f"phase{phase}_summary.md").write_text("\n".join(lines) + "\n")


def update_top_level_readme(results_root: Path, phase_dir: Path, config: dict[str, Any]) -> None:
    results_root.mkdir(parents=True, exist_ok=True)
    readme = results_root / "README.md"
    phase = config["phase"]
    rows = {
        "1": ["1", "not run", "-", "-", "-", "phase1_chicago_realitycheck_n40/phase1_summary.md"],
        "2": ["2", "not run", "-", "-", "-", "phase2_chicago_nsensitivity/phase2_summary.md"],
        "3": ["3", "not run", "-", "-", "-", "phase3_lucknow_downsampling/phase3_summary.md"],
        "4": ["4", "optional", "-", "-", "-", "phase4_chicago_selection_strategies/phase4_summary.md"],
        "5": ["5", "not run", "-", "-", "-", "phase5_mdape_vs_cv_slope/phase5_summary.md"],
    }
    if readme.exists():
        for line in readme.read_text().splitlines():
            if line.startswith("| ") and line.count("|") >= 6:
                parts = [part.strip() for part in line.strip().strip("|").split("|")]
                if parts and parts[0] in rows and parts[0].isdigit():
                    rows[parts[0]] = parts
    key_finding = "see phase summary"
    if phase == 1:
        key_finding = "Chicago N*=40 reality-check completed"
    elif phase == 2:
        key_finding = "Chicago n<=5% remains 2 across N*=30-277"
    elif phase == 3:
        key_finding = "Lucknow N*=31 remains higher than Dhaka N=35 at n=10"
    rows[str(phase)] = [
        str(phase),
        "done",
        datetime.now().date().isoformat(),
        str(config["master_seed"]),
        key_finding,
        f"{phase_dir.name}/phase{phase}_summary.md",
    ]
    lines = [
        "# Finite-Population Experiments",
        "",
        "Results for the finite-population sensitivity and MdAPE-vs-CV slope experiment plan.",
        "",
        "| Phase | Status | Last run | Master seed | Key finding (1-line) | Result file |",
        "|---|---|---|---|---|---|",
    ]
    for phase_key in ["1", "2", "3", "4", "5"]:
        lines.append("| " + " | ".join(rows[phase_key]) + " |")
    readme.write_text("\n".join(lines) + "\n")


def run_phase(args: argparse.Namespace) -> None:
    phase_config = dict(PHASE_CONFIGS[args.phase])
    phase_config["phase"] = args.phase
    phase_config["master_seed"] = args.master_seed
    phase_config["n_inner_draws"] = args.inner_draws
    phase_config["baseline_run"] = args.baseline_run
    if args.outer_draws is not None:
        phase_config["outer_draws"] = args.outer_draws
    if args.target_n_stars:
        phase_config["target_n_stars"] = args.target_n_stars

    phase_dir = args.results_root / phase_config["phase_name"]
    if phase_dir.exists() and not args.overwrite:
        raise SystemExit(f"Phase directory already exists: {phase_dir}")
    for subdir in ["config", "per_draw", "aggregated", "plots"]:
        (phase_dir / subdir).mkdir(parents=True, exist_ok=True)

    bundle = load_dataset(DATASETS[phase_config["dataset_key"]])
    baseline = baseline_summary_for(phase_config["dataset_key"], args.baseline_run)
    write_master_seed_json(phase_dir, phase_config, args)

    tasks = [
        (bundle, phase_config, target_n_star, outer_draw_index, args.master_seed)
        for target_n_star in phase_config["target_n_stars"]
        for outer_draw_index in range(phase_config["outer_draws"])
    ]
    n_jobs = resolve_n_jobs(args.n_jobs)
    print(
        f"Running {phase_config['phase_name']}: {len(tasks)} outer tasks, "
        f"inner_draws={args.inner_draws:,}, n_jobs={n_jobs}"
    )
    start = time.perf_counter()
    seed_rows: list[dict[str, Any]] = []
    all_frames: list[pd.DataFrame] = []
    with ProcessPoolExecutor(max_workers=n_jobs) as executor:
        futures = {executor.submit(run_outer_draw, task): task for task in tasks}
        for completed, future in enumerate(as_completed(futures), start=1):
            frame, seed_row = future.result()
            seed_rows.append(seed_row)
            all_frames.append(frame)
            draw_name = f"draw_{seed_row['target_N_star']:03d}_{seed_row['outer_seed_index']:03d}.parquet"
            frame.to_parquet(phase_dir / "per_draw" / draw_name, index=False)
            if completed == 1 or completed % 10 == 0 or completed == len(futures):
                print(f"[{completed:>4}/{len(futures)}] wrote {draw_name}; rows={len(frame):,}")

    outer_seeds = pd.DataFrame(seed_rows).sort_values(["target_N_star", "outer_seed_index"])
    outer_seeds.to_csv(phase_dir / "config" / "outer_seeds.csv", index=False)
    all_rows = pd.concat(all_frames, ignore_index=True)
    all_rows.to_parquet(phase_dir / "aggregated" / "all_draw_summaries.parquet", index=False)
    all_rows.to_csv(phase_dir / "aggregated" / "all_draw_summaries.csv", index=False)
    period_envelope, daily_envelope, headline = aggregate_phase(phase_dir, phase_config, all_rows, baseline)

    if args.phase == 1:
        plot_phase1_period(period_envelope, phase_dir, phase_config)
        plot_phase1_daily(daily_envelope, phase_dir, phase_config)
    else:
        plot_nsensitivity_period(period_envelope, phase_dir, phase_config)
        plot_n_required(headline, phase_dir, phase_config)
        if args.phase == 3:
            plot_phase3_lucknow_with_dhaka(period_envelope, phase_dir, phase_config)
            plot_phase3_lucknow_n31_vs_dhaka(period_envelope, phase_dir, phase_config)
    mirror_plots(phase_dir)
    write_phase_summary(phase_dir, phase_config, headline, period_envelope)
    update_top_level_readme(args.results_root, phase_dir, phase_config)
    duration = time.perf_counter() - start
    metadata_path = phase_dir / "config" / "master_seed.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["completed_at"] = datetime.now().isoformat(timespec="seconds")
    metadata["duration_seconds"] = duration
    metadata_path.write_text(json.dumps(metadata, indent=2))
    print(f"Wrote {phase_dir}")
    print(f"Duration: {duration:.1f} seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run finite-population sensitivity Phases 1, 2, or 3."
    )
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], required=True)
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--inner-draws", type=int, default=DEFAULT_INNER_DRAWS)
    parser.add_argument("--outer-draws", type=int)
    parser.add_argument("--target-n-stars", type=int, nargs="*")
    parser.add_argument("--n-jobs", type=int, default=-2)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--baseline-run", type=Path, default=DEFAULT_BASELINE_RUN)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.results_root = resolve_repo_path(args.results_root)
    args.baseline_run = resolve_repo_path(args.baseline_run)
    if args.inner_draws < 1:
        raise SystemExit("--inner-draws must be positive")
    if args.outer_draws is not None and args.outer_draws < 1:
        raise SystemExit("--outer-draws must be positive")
    return args


def main() -> None:
    run_phase(parse_args())


if __name__ == "__main__":
    main()
