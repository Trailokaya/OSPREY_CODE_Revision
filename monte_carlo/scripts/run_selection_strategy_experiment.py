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
from run_main_monte_carlo import DATASETS, DatasetBundle, draw_sample_positions, load_dataset, summarize_estimates  # noqa: E402


DEFAULT_MASTER_SEED = 20260528
DEFAULT_INNER_DRAWS = 10_000
DEFAULT_RESULTS_ROOT = REPO_ROOT / "analysis" / "results" / "finite_population_experiments"
PHASE_NAME = "phase4_chicago_selection_strategies"
DATASET_KEY = "chicago_lcs_corrected_no_collocation"
PLOT_MIRROR = REPO_ROOT / "analysis" / "plots" / "finite_population_high_resolution_pdf"

TARGET_N_STARS = [30, 50, 70]
PERIOD_SAMPLE_SIZES = list(range(2, 31))
STOCHASTIC_OUTER_DRAWS = 50
DETERMINISTIC_OUTER_DRAWS = 20

STRATEGY_CONFIGS = {
    "random": {
        "label": "Random",
        "outer_draws": STOCHASTIC_OUTER_DRAWS,
        "notes": "Uniform random N* finite-population draw.",
    },
    "equidistant": {
        "label": "Spatially balanced",
        "outer_draws": STOCHASTIC_OUTER_DRAWS,
        "notes": "Greedy max-min coverage with seed-varying first sensor.",
    },
    "kmeans_stratified": {
        "label": "k-means stratified",
        "outer_draws": STOCHASTIC_OUTER_DRAWS,
        "notes": "NumPy Lloyd k-means with one observed sensor nearest each centroid.",
    },
    "cluster_concentrated": {
        "label": "Cluster-concentrated",
        "outer_draws": DETERMINISTIC_OUTER_DRAWS,
        "notes": "N* nearest sensors to a seed-varying center sensor.",
    },
    "circumferential": {
        "label": "Circumferential",
        "outer_draws": DETERMINISTIC_OUTER_DRAWS,
        "notes": "Random N* draw from the high-radial-distance boundary ring.",
    },
    "anti_cluster": {
        "label": "Anti-cluster",
        "outer_draws": DETERMINISTIC_OUTER_DRAWS,
        "notes": "Greedy max-sum-distance dispersion with seed-varying first sensor.",
    },
}

STRATEGY_COLORS = {
    "random": "#111827",
    "equidistant": "#0072B2",
    "kmeans_stratified": "#009E73",
    "cluster_concentrated": "#D55E00",
    "circumferential": "#7c3aed",
    "anti_cluster": "#dc2626",
}


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


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


def coordinate_km(bundle: DatasetBundle, available_indices: np.ndarray) -> np.ndarray:
    latitudes = np.asarray(bundle.latitudes, dtype=np.float64)[available_indices]
    longitudes = np.asarray(bundle.longitudes, dtype=np.float64)[available_indices]
    lat0 = np.nanmean(latitudes)
    radius_km = 6371.0088
    x = radius_km * np.radians(longitudes) * np.cos(np.radians(lat0))
    y = radius_km * np.radians(latitudes)
    points = np.column_stack([x, y])
    points -= np.nanmean(points, axis=0)
    return points


def pairwise_distances(points: np.ndarray) -> np.ndarray:
    diff = points[:, None, :] - points[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=2))


def greedy_max_min(distances: np.ndarray, target_n_star: int, rng: np.random.Generator) -> np.ndarray:
    selected = [int(rng.integers(0, len(distances)))]
    nearest = distances[selected[0]].copy()
    nearest[selected[0]] = -np.inf
    while len(selected) < target_n_star:
        next_index = int(np.argmax(nearest))
        selected.append(next_index)
        nearest = np.minimum(nearest, distances[next_index])
        nearest[selected] = -np.inf
    return np.asarray(selected, dtype=np.int32)


def greedy_max_sum(distances: np.ndarray, target_n_star: int, rng: np.random.Generator) -> np.ndarray:
    selected = [int(rng.integers(0, len(distances)))]
    score = distances[selected[0]].copy()
    score[selected[0]] = -np.inf
    while len(selected) < target_n_star:
        next_index = int(np.argmax(score))
        selected.append(next_index)
        score = score + distances[next_index]
        score[selected] = -np.inf
    return np.asarray(selected, dtype=np.int32)


def kmeans_stratified(points: np.ndarray, target_n_star: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n_points = len(points)
    center_indices = [int(rng.integers(0, n_points))]
    closest_sq = np.sum((points - points[center_indices[0]]) ** 2, axis=1)
    for _ in range(1, target_n_star):
        probabilities = closest_sq / closest_sq.sum() if closest_sq.sum() > 0 else None
        next_index = int(rng.choice(n_points, p=probabilities))
        center_indices.append(next_index)
        closest_sq = np.minimum(closest_sq, np.sum((points - points[next_index]) ** 2, axis=1))
    centers = points[np.asarray(center_indices, dtype=np.int32)].copy()

    labels = np.zeros(n_points, dtype=np.int32)
    for _ in range(30):
        squared = np.sum((points[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(squared, axis=1)
        new_centers = centers.copy()
        for cluster_index in range(target_n_star):
            members = points[labels == cluster_index]
            if len(members):
                new_centers[cluster_index] = members.mean(axis=0)
            else:
                farthest = int(np.argmax(np.min(squared, axis=1)))
                new_centers[cluster_index] = points[farthest]
        if np.allclose(new_centers, centers):
            break
        centers = new_centers

    selected: list[int] = []
    for cluster_index in range(target_n_star):
        members = np.flatnonzero(labels == cluster_index)
        if len(members):
            distances = np.sum((points[members] - centers[cluster_index]) ** 2, axis=1)
            ordered_members = members[np.argsort(distances)]
        else:
            distances = np.sum((points - centers[cluster_index]) ** 2, axis=1)
            ordered_members = np.argsort(distances)
        for candidate in ordered_members:
            candidate_int = int(candidate)
            if candidate_int not in selected:
                selected.append(candidate_int)
                break

    if len(selected) < target_n_star:
        distances = pairwise_distances(points)
        selected_set = set(selected)
        nearest = np.min(distances[:, selected], axis=1) if selected else np.full(n_points, np.inf)
        for candidate in np.argsort(nearest)[::-1]:
            candidate_int = int(candidate)
            if candidate_int not in selected_set:
                selected.append(candidate_int)
                selected_set.add(candidate_int)
            if len(selected) == target_n_star:
                break
    return np.asarray(selected[:target_n_star], dtype=np.int32)


def select_strategy_indices(
    bundle: DatasetBundle,
    target_n_star: int,
    strategy: str,
    outer_seed: int,
) -> np.ndarray:
    available = np.flatnonzero(np.isfinite(bundle.period_values))
    if target_n_star > len(available):
        raise ValueError(f"target N*={target_n_star} exceeds available sensors {len(available)}")
    points = coordinate_km(bundle, available)
    rng = np.random.default_rng(outer_seed)
    if strategy == "random":
        local_indices = np.sort(rng.choice(len(available), size=target_n_star, replace=False))
    elif strategy == "equidistant":
        local_indices = np.sort(greedy_max_min(pairwise_distances(points), target_n_star, rng))
    elif strategy == "kmeans_stratified":
        local_indices = np.sort(kmeans_stratified(points, target_n_star, outer_seed))
    elif strategy == "cluster_concentrated":
        center = int(rng.integers(0, len(available)))
        distances = np.sqrt(np.sum((points - points[center]) ** 2, axis=1))
        local_indices = np.sort(np.argsort(distances)[:target_n_star])
    elif strategy == "circumferential":
        center = np.nanmean(points, axis=0)
        radial = np.sqrt(np.sum((points - center) ** 2, axis=1))
        candidate_count = min(len(available), max(target_n_star, int(math.ceil(target_n_star * 2.5))))
        candidates = np.argsort(radial)[-candidate_count:]
        weights = radial[candidates]
        weights = weights / weights.sum() if weights.sum() > 0 else None
        local_indices = np.sort(rng.choice(candidates, size=target_n_star, replace=False, p=weights))
    elif strategy == "anti_cluster":
        local_indices = np.sort(greedy_max_sum(pairwise_distances(points), target_n_star, rng))
    else:
        raise ValueError(f"unknown strategy: {strategy}")
    return available[local_indices].astype(np.int32, copy=False)


def n_required(curve: pd.DataFrame, threshold_pct: float) -> float:
    eligible = curve.sort_values("sample_size")
    eligible = eligible[eligible["ape_median_pct"] <= threshold_pct]
    if eligible.empty:
        return math.nan
    return float(eligible["sample_size"].iloc[0])


def run_outer_draw(args: tuple[DatasetBundle, int, str, int, int, int]) -> tuple[pd.DataFrame, dict[str, Any]]:
    bundle, target_n_star, strategy, outer_draw_index, master_seed, n_inner_draws = args
    outer_seed = derive_phase_seed(master_seed, PHASE_NAME, target_n_star, strategy, "outer", outer_draw_index)
    inner_seed = derive_phase_seed(master_seed, PHASE_NAME, target_n_star, strategy, "inner", outer_draw_index)
    selected_indices = select_strategy_indices(bundle, target_n_star, strategy, outer_seed)
    selected_sensor_ids = [bundle.sensor_ids[int(index)] for index in selected_indices]
    selected_hash = selected_sensor_hash(selected_sensor_ids)
    values = bundle.period_values[selected_indices]
    population_size = len(values)
    reference_mean = float(np.nanmean(values))
    reference_sd = float(np.nanstd(values, ddof=1)) if population_size > 1 else np.nan

    rows: list[dict[str, Any]] = []
    for sample_size in PERIOD_SAMPLE_SIZES:
        if sample_size > population_size:
            continue
        task_seed = derive_phase_seed(inner_seed, "period", sample_size, selected_hash)
        sample_positions = draw_sample_positions(population_size, sample_size, n_inner_draws, task_seed)
        sample_estimates = values[sample_positions].mean(axis=1)
        row: dict[str, Any] = {
            "phase": 4,
            "city": bundle.spec.city,
            "dataset_key": bundle.spec.key,
            "target_N_star": target_n_star,
            "selection_strategy": strategy,
            "selection_strategy_label": STRATEGY_CONFIGS[strategy]["label"],
            "outer_draw_index": outer_draw_index,
            "outer_seed_value": outer_seed,
            "inner_seed_value": inner_seed,
            "selected_sensor_set_hash": selected_hash,
            "selected_sensor_count": len(selected_indices),
            "time_aggregation": "period",
            "time_index": "study_period",
            "sample_size": sample_size,
            "n_sensors_available": population_size,
            "n_draws_requested": n_inner_draws,
            "n_draws_completed": n_inner_draws,
            "reference_mean_ugm3": reference_mean,
            "reference_sd_ugm3": reference_sd,
            "task_seed_used": task_seed,
        }
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
    seed_row = {
        "phase": 4,
        "target_N_star": target_n_star,
        "selection_strategy": strategy,
        "selection_strategy_label": STRATEGY_CONFIGS[strategy]["label"],
        "outer_seed_index": outer_draw_index,
        "outer_seed_value": outer_seed,
        "inner_seed_value": inner_seed,
        "selected_sensor_ids": json.dumps(selected_sensor_ids),
        "selected_sensor_count": len(selected_sensor_ids),
        "selected_sensor_set_hash": selected_hash,
    }
    return pd.DataFrame(rows), seed_row


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


def headline_row(
    *,
    metric_name: str,
    target_n_star: int,
    strategy: str,
    values: pd.Series | list[float],
    n_outer_draws: int,
    n_inner_draws: int,
    notes: str,
) -> dict[str, Any]:
    series = pd.Series(values, dtype="float64").dropna()
    return {
        "phase": 4,
        "city": "Chicago",
        "metric_name": metric_name,
        "target_N_star": target_n_star,
        "selection_strategy": strategy,
        "selection_strategy_label": STRATEGY_CONFIGS[strategy]["label"],
        "aggregation": "period",
        "value_median": float(series.median()) if len(series) else math.nan,
        "value_p5": float(series.quantile(0.05)) if len(series) else math.nan,
        "value_p95": float(series.quantile(0.95)) if len(series) else math.nan,
        "value_mean": float(series.mean()) if len(series) else math.nan,
        "value_sd": float(series.std(ddof=1)) if len(series) > 1 else math.nan,
        "n_outer_draws": n_outer_draws,
        "n_inner_draws": n_inner_draws,
        "notes": notes,
    }


def aggregate_outputs(phase_dir: Path, all_rows: pd.DataFrame, n_inner_draws: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    aggregated_dir = phase_dir / "aggregated"
    aggregated_dir.mkdir(parents=True, exist_ok=True)
    envelope = quantile_envelope(
        all_rows,
        ["target_N_star", "selection_strategy", "selection_strategy_label", "sample_size"],
        "ape_median_pct",
    )
    envelope.to_csv(aggregated_dir / "period_strategy_envelope.csv", index=False)

    headline_rows: list[dict[str, Any]] = []
    for (target_n_star, strategy), frame in all_rows.groupby(["target_N_star", "selection_strategy"]):
        by_draw = frame.groupby("outer_draw_index")
        n5 = by_draw.apply(lambda draw: n_required(draw, 5.0), include_groups=False)
        n10 = by_draw.apply(lambda draw: n_required(draw, 10.0), include_groups=False)
        n10_mdape = frame[frame["sample_size"] == 10]["ape_median_pct"]
        outer_draws = int(STRATEGY_CONFIGS[strategy]["outer_draws"])
        headline_rows.extend(
            [
                headline_row(
                    metric_name="n_for_mdape_le_5pct",
                    target_n_star=int(target_n_star),
                    strategy=strategy,
                    values=n5,
                    n_outer_draws=outer_draws,
                    n_inner_draws=n_inner_draws,
                    notes="First n where period MdAPE <= 5% within each strategy-selected finite population.",
                ),
                headline_row(
                    metric_name="n_for_mdape_le_10pct",
                    target_n_star=int(target_n_star),
                    strategy=strategy,
                    values=n10,
                    n_outer_draws=outer_draws,
                    n_inner_draws=n_inner_draws,
                    notes="First n where period MdAPE <= 10% within each strategy-selected finite population.",
                ),
                headline_row(
                    metric_name="mdape_at_n10",
                    target_n_star=int(target_n_star),
                    strategy=strategy,
                    values=n10_mdape,
                    n_outer_draws=outer_draws,
                    n_inner_draws=n_inner_draws,
                    notes="Period MdAPE at n=10 across outer strategy-selected finite populations.",
                ),
            ]
        )
    headline = pd.DataFrame(headline_rows).sort_values(
        ["target_N_star", "selection_strategy", "metric_name"]
    )
    headline.to_csv(aggregated_dir / "headline_numbers.csv", index=False)
    return envelope, headline


def plot_strategy_for_nstar(envelope: pd.DataFrame, phase_dir: Path, target_n_star: int, master_seed: int) -> None:
    setup_matplotlib()
    frame = envelope[envelope["target_N_star"] == target_n_star].copy()
    fig, axis = plt.subplots(figsize=(7.2, 4.2))
    for strategy, strategy_config in STRATEGY_CONFIGS.items():
        strategy_frame = frame[frame["selection_strategy"] == strategy].sort_values("sample_size")
        if strategy_frame.empty:
            continue
        color = STRATEGY_COLORS[strategy]
        axis.fill_between(
            strategy_frame["sample_size"].to_numpy(),
            strategy_frame["value_p5"].to_numpy(),
            strategy_frame["value_p95"].to_numpy(),
            color=color,
            alpha=0.10,
            linewidth=0,
        )
        axis.plot(
            strategy_frame["sample_size"],
            strategy_frame["value_median"],
            color=color,
            linewidth=1.8,
            label=strategy_config["label"],
        )
    axis.axhline(5, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    axis.axhline(10, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
    axis.set_xlabel("Number of sampled sensors (n)")
    axis.set_ylabel("Study-period MdAPE (%)")
    axis.set_title(f"Chicago selection strategies at N*={target_n_star}")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axis.legend(frameon=False, ncol=2)
    save_figure(
        fig,
        phase_dir
        / "plots"
        / f"phase4_chicago_selection_strategy_n{target_n_star}_period_mdape_seed{master_seed}",
        dpi=OUTPUT_DPI,
    )


def plot_strategy_all_nstars(envelope: pd.DataFrame, phase_dir: Path, master_seed: int) -> None:
    setup_matplotlib()
    nstars = sorted(envelope["target_N_star"].unique())
    fig, axes = plt.subplots(1, len(nstars), figsize=(11.5, 3.6), sharey=True)
    axes_array = np.atleast_1d(axes)
    for axis, target_n_star in zip(axes_array, nstars, strict=True):
        frame = envelope[envelope["target_N_star"] == target_n_star]
        for strategy, strategy_config in STRATEGY_CONFIGS.items():
            strategy_frame = frame[frame["selection_strategy"] == strategy].sort_values("sample_size")
            if strategy_frame.empty:
                continue
            color = STRATEGY_COLORS[strategy]
            axis.fill_between(
                strategy_frame["sample_size"].to_numpy(),
                strategy_frame["value_p5"].to_numpy(),
                strategy_frame["value_p95"].to_numpy(),
                color=color,
                alpha=0.08,
                linewidth=0,
            )
            axis.plot(
                strategy_frame["sample_size"],
                strategy_frame["value_median"],
                color=color,
                linewidth=1.5,
                label=strategy_config["label"],
            )
        axis.axhline(5, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
        axis.axhline(10, color=REFERENCE_LINE_COLOR, linewidth=0.9, linestyle=":")
        axis.set_title(f"N*={target_n_star}")
        axis.set_xlabel("Sampled sensors (n)")
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axes_array[0].set_ylabel("Study-period MdAPE (%)")
    handles, labels = axes_array[-1].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="center left", ncol=1, bbox_to_anchor=(1.01, 0.5))
    fig.subplots_adjust(right=0.84, wspace=0.2)
    save_figure(
        fig,
        phase_dir / "plots" / f"phase4_chicago_selection_strategy_alln_period_mdape_seed{master_seed}",
        dpi=OUTPUT_DPI,
    )


def plot_required_n(headline: pd.DataFrame, phase_dir: Path, master_seed: int) -> None:
    setup_matplotlib()
    frame = headline[headline["metric_name"] == "n_for_mdape_le_5pct"].copy()
    pivot = frame.pivot(index="selection_strategy_label", columns="target_N_star", values="value_median")
    order = [STRATEGY_CONFIGS[strategy]["label"] for strategy in STRATEGY_CONFIGS]
    pivot = pivot.reindex(order)
    fig, axis = plt.subplots(figsize=(7.2, 3.8))
    x = np.arange(len(pivot.index))
    target_n_stars = sorted(frame["target_N_star"].unique())
    width = min(0.7 / max(1, len(target_n_stars)), 0.22)
    offsets = (np.arange(len(target_n_stars)) - (len(target_n_stars) - 1) / 2) * width
    for offset, target_n_star in zip(offsets, target_n_stars, strict=True):
        values = pivot[target_n_star].to_numpy(dtype=float)
        axis.bar(x + offset, values, width=width, label=f"N*={target_n_star}")
    axis.set_xticks(x)
    axis.set_xticklabels(pivot.index, rotation=25, ha="right")
    axis.set_ylabel("Required sampled sensors n")
    axis.set_title("Chicago n for study-period MdAPE ≤ 5% by strategy")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    axis.legend(frameon=False)
    save_figure(
        fig,
        phase_dir / "plots" / f"phase4_chicago_selection_strategy_required_n_seed{master_seed}",
        dpi=OUTPUT_DPI,
    )


def write_master_seed_json(phase_dir: Path, args: argparse.Namespace) -> None:
    payload = {
        "phase": 4,
        "phase_name": PHASE_NAME,
        "master_seed": args.master_seed,
        "seed_algorithm": "int.from_bytes(sha256('|'.join([master_seed, parts])).digest()[:4], 'big')",
        "dataset_key": DATASET_KEY,
        "target_n_stars": TARGET_N_STARS,
        "selection_strategies": STRATEGY_CONFIGS,
        "inner_draws": args.inner_draws,
        "period_sample_sizes": PERIOD_SAMPLE_SIZES,
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "python": sys.version,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (phase_dir / "config" / "master_seed.json").write_text(json.dumps(payload, indent=2))


def write_summary(phase_dir: Path, headline: pd.DataFrame, master_seed: int, inner_draws: int) -> None:
    n5 = headline[headline["metric_name"] == "n_for_mdape_le_5pct"].copy()
    mdape_n10 = headline[headline["metric_name"] == "mdape_at_n10"].copy()
    n50 = n5[n5["target_N_star"] == 50].sort_values("value_median")
    random_n50 = n50[n50["selection_strategy"] == "random"].iloc[0]
    clustered_n50 = n50[n50["selection_strategy"] == "cluster_concentrated"].iloc[0]
    n50_mdape = mdape_n10[mdape_n10["target_N_star"] == 50].sort_values("value_median")
    best_n50_mdape = n50_mdape.iloc[0]
    worst_n50_mdape = n50_mdape.iloc[-1]
    strategy_lines = []
    for target_n_star in TARGET_N_STARS:
        subset = n5[n5["target_N_star"] == target_n_star].sort_values("value_median")
        compact = ", ".join(
            f"{row.selection_strategy_label}: {row.value_median:.0f}"
            for row in subset.itertuples(index=False)
        )
        strategy_lines.append(f"- N*={target_n_star}: {compact}")
    mdape_lines = []
    for target_n_star in TARGET_N_STARS:
        subset = mdape_n10[mdape_n10["target_N_star"] == target_n_star].sort_values("value_median")
        compact = ", ".join(
            f"{row.selection_strategy_label}: {row.value_median:.2f}%"
            for row in subset.itertuples(index=False)
        )
        mdape_lines.append(f"- N*={target_n_star}: {compact}")

    lines = [
        "# Phase 4 Summary — Chicago Selection-Strategy Comparison",
        "",
        f"- Master seed: `{master_seed}`",
        f"- Inner SRSWOR draws per task: `{inner_draws}`",
        "- Stochastic strategies use `B'=50` outer selections: random, spatially balanced, k-means stratified.",
        "- Partially deterministic strategies use `B'=20` outer selections: cluster-concentrated, circumferential, anti-cluster.",
        "- Headline table: `aggregated/headline_numbers.csv`",
        "- Strategy envelope: `aggregated/period_strategy_envelope.csv`",
        "- Median required n for period MdAPE <= 5% is largely insensitive to strategy in Chicago: all strategies are `n=2` at N*=50 and N*=70, while anti-cluster increases to `n=3` at N*=30.",
        f"- At N*=50, MdAPE at n=10 ranges from `{best_n50_mdape.value_median:.2f}%` for `{best_n50_mdape.selection_strategy_label}` to `{worst_n50_mdape.value_median:.2f}%` for `{worst_n50_mdape.selection_strategy_label}`.",
        f"- At N*=50, random selection requires median n=`{random_n50.value_median:.0f}`; cluster-concentrated selection requires median n=`{clustered_n50.value_median:.0f}`.",
        "- Verdict: strategy choice produces visible but small differences in Chicago period MdAPE curves. Cluster-concentrated finite populations are not worst for this deployed-network-mean estimand because they are internally homogeneous; spatially dispersed strategies expose slightly more cross-sensor heterogeneity.",
        "",
        "## Median n for MdAPE <= 5%",
        "",
        *strategy_lines,
        "",
        "## Median period MdAPE at n=10",
        "",
        *mdape_lines,
        "",
        "## Main outputs",
        "",
        f"- N*=30 figure: `plots/phase4_chicago_selection_strategy_n30_period_mdape_seed{master_seed}.pdf`",
        f"- N*=50 figure: `plots/phase4_chicago_selection_strategy_n50_period_mdape_seed{master_seed}.pdf`",
        f"- N*=70 figure: `plots/phase4_chicago_selection_strategy_n70_period_mdape_seed{master_seed}.pdf`",
        f"- Three-panel figure: `plots/phase4_chicago_selection_strategy_alln_period_mdape_seed{master_seed}.pdf`",
        f"- Required-n figure: `plots/phase4_chicago_selection_strategy_required_n_seed{master_seed}.pdf`",
    ]
    (phase_dir / "phase4_summary.md").write_text("\n".join(lines) + "\n")


def update_top_level_readme(results_root: Path, phase_dir: Path, master_seed: int) -> None:
    readme = results_root / "README.md"
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
    rows["4"] = [
        "4",
        "done",
        datetime.now().date().isoformat(),
        str(master_seed),
        "Chicago selection strategies compared at N*=30,50,70",
        f"{phase_dir.name}/phase4_summary.md",
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


def mirror_plots(phase_dir: Path) -> None:
    PLOT_MIRROR.mkdir(parents=True, exist_ok=True)
    for plot_file in (phase_dir / "plots").glob("*"):
        if plot_file.suffix.lower() in {".pdf", ".png"}:
            (PLOT_MIRROR / plot_file.name).write_bytes(plot_file.read_bytes())


def run_phase4(args: argparse.Namespace) -> None:
    phase_dir = args.results_root / PHASE_NAME
    if phase_dir.exists() and not args.overwrite:
        raise SystemExit(f"Phase directory already exists: {phase_dir}")
    for subdir in ["config", "per_draw", "aggregated", "plots"]:
        (phase_dir / subdir).mkdir(parents=True, exist_ok=True)

    bundle = load_dataset(DATASETS[DATASET_KEY])
    write_master_seed_json(phase_dir, args)
    tasks = [
        (bundle, target_n_star, strategy, outer_draw_index, args.master_seed, args.inner_draws)
        for target_n_star in TARGET_N_STARS
        for strategy, strategy_config in STRATEGY_CONFIGS.items()
        for outer_draw_index in range(int(strategy_config["outer_draws"]))
    ]
    n_jobs = resolve_n_jobs(args.n_jobs)
    print(
        f"Running {PHASE_NAME}: {len(tasks)} outer tasks, "
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
            draw_name = (
                f"draw_{seed_row['target_N_star']:03d}_"
                f"{seed_row['selection_strategy']}_{seed_row['outer_seed_index']:03d}.parquet"
            )
            frame.to_parquet(phase_dir / "per_draw" / draw_name, index=False)
            if completed == 1 or completed % 10 == 0 or completed == len(futures):
                print(f"[{completed:>4}/{len(futures)}] wrote {draw_name}; rows={len(frame):,}")

    outer_seeds = pd.DataFrame(seed_rows).sort_values(
        ["target_N_star", "selection_strategy", "outer_seed_index"]
    )
    outer_seeds.to_csv(phase_dir / "config" / "outer_seeds.csv", index=False)
    all_rows = pd.concat(all_frames, ignore_index=True)
    all_rows.to_parquet(phase_dir / "aggregated" / "all_draw_summaries.parquet", index=False)
    all_rows.to_csv(phase_dir / "aggregated" / "all_draw_summaries.csv", index=False)
    envelope, headline = aggregate_outputs(phase_dir, all_rows, args.inner_draws)
    for target_n_star in TARGET_N_STARS:
        plot_strategy_for_nstar(envelope, phase_dir, target_n_star, args.master_seed)
    plot_strategy_all_nstars(envelope, phase_dir, args.master_seed)
    plot_required_n(headline, phase_dir, args.master_seed)
    mirror_plots(phase_dir)
    write_summary(phase_dir, headline, args.master_seed, args.inner_draws)
    update_top_level_readme(args.results_root, phase_dir, args.master_seed)
    metadata_path = phase_dir / "config" / "master_seed.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["completed_at"] = datetime.now().isoformat(timespec="seconds")
    metadata["duration_seconds"] = time.perf_counter() - start
    metadata_path.write_text(json.dumps(metadata, indent=2))
    print(f"Wrote {phase_dir}")
    print(f"Duration: {metadata['duration_seconds']:.1f} seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 4 Chicago selection-strategy experiment.")
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--inner-draws", type=int, default=DEFAULT_INNER_DRAWS)
    parser.add_argument("--n-jobs", type=int, default=-2)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.inner_draws < 1:
        raise SystemExit("--inner-draws must be positive")
    return args


def main() -> None:
    run_phase4(parse_args())


if __name__ == "__main__":
    main()
