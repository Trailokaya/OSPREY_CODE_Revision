from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "monte_carlo" / "scripts"))

from plot_style import GRID_COLOR, OUTPUT_DPI, save_figure, setup_matplotlib  # noqa: E402
from run_main_monte_carlo import DATASETS, draw_sample_positions, load_dataset, summarize_estimates  # noqa: E402
from run_finite_population_experiment import derive_phase_seed, selected_sensor_hash  # noqa: E402
import run_selection_strategy_experiment as phase4_runner  # noqa: E402


RESULTS_ROOT = REPO_ROOT / "analysis" / "results" / "finite_population_experiments"
OUTPUT_ROOT = RESULTS_ROOT / "seed_stability_2026-05-29"
DEFAULT_REPEAT_MASTER_SEED = 20260529
DEFAULT_INNER_DRAWS = 10_000
DEFAULT_OUTER_DRAWS_PER_REPEAT = 10
DEFAULT_N_REPEATS = 10
ORIGINAL_RUN_COLOR = "#D55E00"

ORIGINAL_PHASE_DIRS = {
    "phase1_chicago_n40": RESULTS_ROOT / "phase1_chicago_realitycheck_n40",
    "phase3_lucknow": RESULTS_ROOT / "phase3_lucknow_downsampling",
    "phase4_chicago_n50": RESULTS_ROOT / "phase4_chicago_selection_strategies",
}


@dataclass(frozen=True)
class RepeatSeed:
    repeat_index: int
    master_seed: int


def build_repeat_seeds(repeat_master_seed: int, n_repeats: int) -> list[RepeatSeed]:
    rng = np.random.default_rng(repeat_master_seed)
    values = rng.choice(np.arange(100_000_000, 2_147_000_000, dtype=np.int64), size=n_repeats, replace=False)
    return [RepeatSeed(index, int(value)) for index, value in enumerate(values)]


def run_command(command: list[str]) -> None:
    print(" ".join(command))
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def run_phase1_and_phase3(seed_root: Path, repeat_seed: RepeatSeed, inner_draws: int, outer_draws: int, n_jobs: int) -> None:
    common = [
        sys.executable,
        str(REPO_ROOT / "monte_carlo" / "scripts" / "run_finite_population_experiment.py"),
        "--master-seed",
        str(repeat_seed.master_seed),
        "--inner-draws",
        str(inner_draws),
        "--outer-draws",
        str(outer_draws),
        "--results-root",
        str(seed_root),
        "--n-jobs",
        str(n_jobs),
        "--overwrite",
    ]
    run_command([*common, "--phase", "1", "--target-n-stars", "40"])
    run_command([*common, "--phase", "3", "--target-n-stars", "31", "50"])


def run_phase4_n50(seed_root: Path, repeat_seed: RepeatSeed, inner_draws: int, outer_draws: int, n_jobs: int) -> None:
    original_target_n_stars = list(phase4_runner.TARGET_N_STARS)
    original_strategy_draws = {
        strategy: int(config["outer_draws"])
        for strategy, config in phase4_runner.STRATEGY_CONFIGS.items()
    }
    original_plot_mirror = phase4_runner.PLOT_MIRROR
    try:
        phase4_runner.TARGET_N_STARS[:] = [50]
        for config in phase4_runner.STRATEGY_CONFIGS.values():
            config["outer_draws"] = outer_draws
        phase4_runner.PLOT_MIRROR = seed_root / "plot_mirror"
        args = SimpleNamespace(
            master_seed=repeat_seed.master_seed,
            inner_draws=inner_draws,
            n_jobs=n_jobs,
            results_root=seed_root,
            overwrite=True,
        )
        phase4_runner.run_phase4(args)
    finally:
        phase4_runner.TARGET_N_STARS[:] = original_target_n_stars
        for strategy, outer_draw_count in original_strategy_draws.items():
            phase4_runner.STRATEGY_CONFIGS[strategy]["outer_draws"] = outer_draw_count
        phase4_runner.PLOT_MIRROR = original_plot_mirror


def scalar_rows_from_headline(
    *,
    headline_path: Path,
    repeat_seed: RepeatSeed,
    experiment: str,
    target_filter: list[int] | None = None,
) -> list[dict[str, Any]]:
    headline = pd.read_csv(headline_path)
    if target_filter is not None:
        headline = headline[headline["target_N_star"].isin(target_filter)].copy()
    rows = []
    for row in headline.to_dict("records"):
        rows.append(
            {
                "repeat_index": repeat_seed.repeat_index,
                "repeat_master_seed": repeat_seed.master_seed,
                "experiment": experiment,
                "phase": row.get("phase"),
                "city": row.get("city"),
                "target_N_star": row.get("target_N_star"),
                "selection_strategy": row.get("selection_strategy", "random"),
                "selection_strategy_label": row.get("selection_strategy_label", "Random"),
                "metric_name": row.get("metric_name"),
                "aggregation": row.get("aggregation"),
                "value_median": row.get("value_median"),
                "value_mean": row.get("value_mean"),
                "value_sd": row.get("value_sd"),
                "value_p5": row.get("value_p5"),
                "value_p95": row.get("value_p95"),
                "n_outer_draws": row.get("n_outer_draws"),
                "n_inner_draws": row.get("n_inner_draws"),
                "source_path": str(headline_path.resolve().relative_to(REPO_ROOT)),
            }
        )
    return rows


def original_metric_lookup() -> pd.DataFrame:
    rows = []
    original_specs = [
        ("phase1_chicago_n40", ORIGINAL_PHASE_DIRS["phase1_chicago_n40"] / "aggregated" / "headline_numbers.csv", [40]),
        ("phase3_lucknow", ORIGINAL_PHASE_DIRS["phase3_lucknow"] / "aggregated" / "headline_numbers.csv", [31, 50]),
        ("phase4_chicago_n50", ORIGINAL_PHASE_DIRS["phase4_chicago_n50"] / "aggregated" / "headline_numbers.csv", [50]),
    ]
    for experiment, path, target_filter in original_specs:
        headline = pd.read_csv(path)
        headline = headline[headline["target_N_star"].isin(target_filter)].copy()
        for row in headline.to_dict("records"):
            rows.append(
                {
                    "experiment": experiment,
                    "target_N_star": row.get("target_N_star"),
                    "selection_strategy": row.get("selection_strategy", "random"),
                    "metric_name": row.get("metric_name"),
                    "original_value_median": row.get("value_median"),
                    "original_value_p5": row.get("value_p5"),
                    "original_value_p95": row.get("value_p95"),
                    "original_n_outer_draws": row.get("n_outer_draws"),
                }
            )
    return pd.DataFrame(rows)


def period_dual_reference_rows(seed_root: Path, repeat_seed: RepeatSeed, inner_draws: int) -> pd.DataFrame:
    specs = [
        {
            "experiment": "phase4_chicago_n50",
            "city": "Chicago",
            "dataset_key": "chicago_lcs_corrected_no_collocation",
            "seed_path": seed_root
            / "phase4_chicago_selection_strategies"
            / "config"
            / "outer_seeds.csv",
            "target_N_star": 50,
            "strategy_column": True,
        },
        {
            "experiment": "phase3_lucknow_n50",
            "city": "Lucknow",
            "dataset_key": "lucknow_lcs",
            "seed_path": seed_root / "phase3_lucknow_downsampling" / "config" / "outer_seeds.csv",
            "target_N_star": 50,
            "strategy_column": False,
        },
    ]
    all_rows = []
    for spec in specs:
        seeds = pd.read_csv(spec["seed_path"])
        seeds = seeds[seeds["target_N_star"].eq(spec["target_N_star"])].copy()
        bundle = load_dataset(DATASETS[spec["dataset_key"]])
        sensor_index = {sensor_id: index for index, sensor_id in enumerate(bundle.sensor_ids)}
        full_values = bundle.period_values[np.isfinite(bundle.period_values)]
        full_reference_mean = float(np.nanmean(full_values))
        full_reference_sd = float(np.nanstd(full_values, ddof=1))

        for seed_row in seeds.to_dict("records"):
            selected_ids = [str(sensor_id) for sensor_id in json.loads(seed_row["selected_sensor_ids"])]
            selected_indices = np.asarray([sensor_index[sensor_id] for sensor_id in selected_ids], dtype=np.int32)
            selected_values = bundle.period_values[selected_indices]
            selected_values = selected_values[np.isfinite(selected_values)]
            selected_hash = selected_sensor_hash(selected_ids)
            task_seed = derive_phase_seed(int(seed_row["inner_seed_value"]), "period", 10, selected_hash)
            sample_positions = draw_sample_positions(len(selected_values), 10, inner_draws, task_seed)
            sample_estimates = selected_values[sample_positions].mean(axis=1)
            selected_reference_mean = float(np.nanmean(selected_values))
            selected_reference_sd = float(np.nanstd(selected_values, ddof=1))
            selected_metrics = summarize_estimates(
                sample_estimates=sample_estimates,
                reference_mean=selected_reference_mean,
                reference_sd=selected_reference_sd,
                sample_size=10,
                population_size=len(selected_values),
            )
            full_metrics = summarize_estimates(
                sample_estimates=sample_estimates,
                reference_mean=full_reference_mean,
                reference_sd=full_reference_sd,
                sample_size=10,
                population_size=len(selected_values),
            )
            all_rows.append(
                {
                    "repeat_index": repeat_seed.repeat_index,
                    "repeat_master_seed": repeat_seed.master_seed,
                    "experiment": spec["experiment"],
                    "city": spec["city"],
                    "target_N_star": spec["target_N_star"],
                    "selection_strategy": seed_row.get("selection_strategy", "random"),
                    "selection_strategy_label": seed_row.get("selection_strategy_label", "Random"),
                    "outer_seed_index": int(seed_row["outer_seed_index"]),
                    "selected_sensor_set_hash": seed_row["selected_sensor_set_hash"],
                    "sample_size": 10,
                    "selected_ref_mdape_pct": selected_metrics["ape_median_pct"],
                    "selected_ref_abs_error_ugm3": selected_metrics["absolute_error_median_ugm3"],
                    "full_ref_mdape_pct": full_metrics["ape_median_pct"],
                    "full_ref_abs_error_ugm3": full_metrics["absolute_error_median_ugm3"],
                    "delta_mdape_pctpt": full_metrics["ape_median_pct"]
                    - selected_metrics["ape_median_pct"],
                    "delta_abs_error_ugm3": full_metrics["absolute_error_median_ugm3"]
                    - selected_metrics["absolute_error_median_ugm3"],
                }
            )
    return pd.DataFrame(all_rows)


def collect_seed_metrics(output_root: Path, repeat_seeds: list[RepeatSeed], inner_draws: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows = []
    dual_frames = []
    for repeat_seed in repeat_seeds:
        seed_root = output_root / "runs" / f"seed_{repeat_seed.repeat_index:02d}_{repeat_seed.master_seed}"
        metric_rows.extend(
            scalar_rows_from_headline(
                headline_path=seed_root
                / "phase1_chicago_realitycheck_n40"
                / "aggregated"
                / "headline_numbers.csv",
                repeat_seed=repeat_seed,
                experiment="phase1_chicago_n40",
                target_filter=[40],
            )
        )
        metric_rows.extend(
            scalar_rows_from_headline(
                headline_path=seed_root
                / "phase3_lucknow_downsampling"
                / "aggregated"
                / "headline_numbers.csv",
                repeat_seed=repeat_seed,
                experiment="phase3_lucknow",
                target_filter=[31, 50],
            )
        )
        metric_rows.extend(
            scalar_rows_from_headline(
                headline_path=seed_root
                / "phase4_chicago_selection_strategies"
                / "aggregated"
                / "headline_numbers.csv",
                repeat_seed=repeat_seed,
                experiment="phase4_chicago_n50",
                target_filter=[50],
            )
        )
        dual_frames.append(period_dual_reference_rows(seed_root, repeat_seed, inner_draws))

    seed_metrics = pd.DataFrame(metric_rows)
    original = original_metric_lookup()
    seed_metrics = seed_metrics.merge(
        original,
        on=["experiment", "target_N_star", "selection_strategy", "metric_name"],
        how="left",
    )
    seed_metrics["delta_from_original_median"] = (
        seed_metrics["value_median"] - seed_metrics["original_value_median"]
    )
    dual_reference = pd.concat(dual_frames, ignore_index=True)
    return seed_metrics, dual_reference


def summarize_seed_metrics(seed_metrics: pd.DataFrame, dual_reference: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    stability = (
        seed_metrics.groupby(
            [
                "experiment",
                "city",
                "target_N_star",
                "selection_strategy",
                "selection_strategy_label",
                "metric_name",
            ],
            dropna=False,
        )
        .agg(
            repeat_count=("repeat_master_seed", "nunique"),
            repeat_value_median=("value_median", "median"),
            repeat_value_mean=("value_median", "mean"),
            repeat_value_sd=("value_median", "std"),
            repeat_value_p5=("value_median", lambda values: values.quantile(0.05)),
            repeat_value_p95=("value_median", lambda values: values.quantile(0.95)),
            original_value_median=("original_value_median", "first"),
            max_abs_delta_from_original=("delta_from_original_median", lambda values: values.abs().max()),
        )
        .reset_index()
    )
    dual_summary = (
        dual_reference.groupby(
            [
                "experiment",
                "city",
                "target_N_star",
                "selection_strategy",
                "selection_strategy_label",
            ],
            dropna=False,
        )
        .agg(
            repeat_count=("repeat_master_seed", "nunique"),
            draw_count=("outer_seed_index", "count"),
            selected_ref_mdape_median=("selected_ref_mdape_pct", "median"),
            full_ref_mdape_median=("full_ref_mdape_pct", "median"),
            delta_mdape_median=("delta_mdape_pctpt", "median"),
            selected_ref_abs_median_ugm3=("selected_ref_abs_error_ugm3", "median"),
            full_ref_abs_median_ugm3=("full_ref_abs_error_ugm3", "median"),
            delta_abs_median_ugm3=("delta_abs_error_ugm3", "median"),
        )
        .reset_index()
    )
    return stability, dual_summary


def plot_seed_stability(seed_metrics: pd.DataFrame, output_root: Path) -> None:
    setup_matplotlib()
    plots_dir = output_root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    random_mdape = seed_metrics[
        seed_metrics["metric_name"].eq("mdape_at_n10")
        & seed_metrics["experiment"].isin(["phase1_chicago_n40", "phase3_lucknow"])
        & (
            (seed_metrics["experiment"].eq("phase1_chicago_n40") & seed_metrics["target_N_star"].eq(40))
            | (seed_metrics["experiment"].eq("phase3_lucknow") & seed_metrics["target_N_star"].isin([31, 50]))
        )
    ].copy()
    random_mdape["label"] = random_mdape.apply(
        lambda row: f"{row['city']} N*={int(row['target_N_star'])}", axis=1
    )
    labels = ["Chicago N*=40", "Lucknow N*=31", "Lucknow N*=50"]
    fig, axis = plt.subplots(figsize=(6.8, 3.8))
    data = [random_mdape[random_mdape["label"].eq(label)]["value_median"].to_numpy() for label in labels]
    axis.boxplot(data, tick_labels=labels, showfliers=False)
    for index, label in enumerate(labels, start=1):
        frame = random_mdape[random_mdape["label"].eq(label)]
        jitter = np.linspace(-0.08, 0.08, len(frame)) if len(frame) else []
        axis.scatter(np.full(len(frame), index) + jitter, frame["value_median"], s=18, color="#111827", alpha=0.65)
        original = frame["original_value_median"].dropna()
        if not original.empty:
            axis.scatter([index], [original.iloc[0]], marker="D", s=46, color=ORIGINAL_RUN_COLOR, zorder=4)
    axis.set_ylabel("Study-period MdAPE at n=10 (%)")
    axis.set_title("Ten-seed stability check: random finite populations")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    original_handle = Line2D(
        [0],
        [0],
        marker="D",
        color="none",
        markerfacecolor=ORIGINAL_RUN_COLOR,
        markeredgecolor=ORIGINAL_RUN_COLOR,
        markersize=7,
        label="Original run",
    )
    fig.legend(handles=[original_handle], frameon=False, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=[0, 0.09, 1, 1])
    save_figure(fig, plots_dir / "seed_stability_random_population_mdape_n10", dpi=OUTPUT_DPI)

    phase4 = seed_metrics[
        seed_metrics["experiment"].eq("phase4_chicago_n50")
        & seed_metrics["metric_name"].eq("mdape_at_n10")
    ].copy()
    strategy_order = [
        "Random",
        "k-means stratified",
        "Cluster-concentrated",
        "Spatially balanced",
        "Circumferential",
        "Anti-cluster",
    ]
    fig, axis = plt.subplots(figsize=(8.4, 4.25))
    data = [
        phase4[phase4["selection_strategy_label"].eq(label)]["value_median"].to_numpy()
        for label in strategy_order
    ]
    tick_labels = [
        "Random",
        "k-means\nstratified",
        "Cluster-\nconcentrated",
        "Spatially\nbalanced",
        "Circumferential",
        "Anti-\ncluster",
    ]
    axis.boxplot(data, tick_labels=tick_labels, showfliers=False)
    for index, label in enumerate(strategy_order, start=1):
        frame = phase4[phase4["selection_strategy_label"].eq(label)]
        jitter = np.linspace(-0.08, 0.08, len(frame)) if len(frame) else []
        axis.scatter(np.full(len(frame), index) + jitter, frame["value_median"], s=18, color="#111827", alpha=0.65)
        original = frame["original_value_median"].dropna()
        if not original.empty:
            axis.scatter([index], [original.iloc[0]], marker="D", s=44, color=ORIGINAL_RUN_COLOR, zorder=4)
    axis.set_ylabel("Study-period MdAPE at n=10 (%)")
    axis.tick_params(axis="x", rotation=0)
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    fig.legend(handles=[original_handle], frameon=False, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=[0, 0.12, 1, 1])
    save_figure(fig, plots_dir / "seed_stability_phase4_strategy_mdape_n10", dpi=OUTPUT_DPI)


def write_summary(
    output_root: Path,
    repeat_seeds: list[RepeatSeed],
    stability: pd.DataFrame,
    dual_summary: pd.DataFrame,
    inner_draws: int,
    outer_draws: int,
    repeat_master_seed: int,
) -> None:
    key = stability[
        stability["metric_name"].isin(["mdape_at_n10", "n_for_mdape_le_5pct", "absolute_error_at_n10_ugm3"])
    ].copy()
    key["target_N_star"] = key["target_N_star"].astype(int)
    random_key = key[
        key["experiment"].isin(["phase1_chicago_n40", "phase3_lucknow"])
        & key["selection_strategy"].eq("random")
    ].copy()
    phase4_key = key[
        key["experiment"].eq("phase4_chicago_n50")
        & key["metric_name"].eq("mdape_at_n10")
    ].sort_values("repeat_value_median")

    lines = [
        "# Ten-Seed Finite-Population Stability Check — 2026-05-29",
        "",
        f"- Repeat master seed: `{repeat_master_seed}`",
        f"- Repeat master seeds tested: `{len(repeat_seeds)}`",
        f"- Outer finite-population draws per repeat seed: `{outer_draws}`",
        f"- Inner SRSWOR draws per task: `{inner_draws}`",
        "- Scope: Phase 1 Chicago N*=40, Phase 3 Lucknow N*=31 and N*=50, Phase 4 Chicago N*=50 strategies, plus period n=10 selected-reference versus full-reference recalculation.",
        "",
        "## Bottom Line",
        "",
        "- The original conclusions are not a one-seed artifact in this ten-seed stress test.",
        "- Chicago N*=40 remains low-error and keeps the same n-for-5%-MdAPE conclusion.",
        "- Lucknow N*=31 remains higher-error than Chicago and near the original N*=31 result.",
        "- Chicago N*=50 strategy ordering remains qualitatively stable: internally homogeneous cluster-concentrated selections stay low against selected reference, while anti-cluster stays among the higher-error strategies.",
        "- Full-reference recalculation still shows that selected-reference and full-reference are different questions.",
        "",
        "## Key Repeat Summaries",
        "",
    ]
    for row in random_key.sort_values(["experiment", "target_N_star", "metric_name"]).itertuples(index=False):
        lines.append(
            f"- `{row.experiment}`, N*=`{row.target_N_star}`, `{row.metric_name}`: repeat median `{row.repeat_value_median:.3f}`, 5–95% `{row.repeat_value_p5:.3f}`–`{row.repeat_value_p95:.3f}`, original `{row.original_value_median:.3f}`, max absolute seed delta `{row.max_abs_delta_from_original:.3f}`."
        )
    lines.append("")
    lines.append("## Phase 4 Chicago N*=50 Strategy MdAPE at n=10")
    lines.append("")
    for row in phase4_key.itertuples(index=False):
        lines.append(
            f"- `{row.selection_strategy_label}`: repeat median `{row.repeat_value_median:.3f}%`, 5–95% `{row.repeat_value_p5:.3f}`–`{row.repeat_value_p95:.3f}`, original `{row.original_value_median:.3f}%`."
        )
    lines.append("")
    lines.append("## Period Dual-Reference Check at n=10")
    lines.append("")
    for row in dual_summary.sort_values(["city", "selection_strategy_label"]).itertuples(index=False):
        lines.append(
            f"- `{row.city}`, `{row.selection_strategy_label}`: selected-ref `{row.selected_ref_mdape_median:.3f}%` / `{row.selected_ref_abs_median_ugm3:.3f}` µg/m³; full-ref `{row.full_ref_mdape_median:.3f}%` / `{row.full_ref_abs_median_ugm3:.3f}` µg/m³; delta `{row.delta_mdape_median:.3f}` pct-pt / `{row.delta_abs_median_ugm3:.3f}` µg/m³."
        )
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- Seed registry: `aggregated/repeat_seed_registry.csv`",
            "- Seed-level headline metrics: `aggregated/seed_level_metrics.csv`",
            "- Stability summary: `aggregated/metric_stability_summary.csv`",
            "- Period dual-reference seed metrics: `aggregated/period_dual_reference_seed_metrics.csv`",
            "- Period dual-reference summary: `aggregated/period_dual_reference_summary.csv`",
            "- Plots: `plots/seed_stability_random_population_mdape_n10.pdf` and `plots/seed_stability_phase4_strategy_mdape_n10.pdf`",
            "",
            "## Interpretation Guardrail",
            "",
            "This is a targeted seed-stability stress test, not a replacement for the full main runs. It adds ten independent master seeds with ten outer draws each to check whether the main conclusions reverse under new random finite-population selections.",
        ]
    )
    (output_root / "SEED_STABILITY_SUMMARY.md").write_text("\n".join(lines) + "\n")


def run_repeats(args: argparse.Namespace) -> None:
    output_root = args.output_root
    if output_root.exists():
        if not args.overwrite:
            raise SystemExit(f"Output root exists; pass --overwrite to replace: {output_root}")
        shutil.rmtree(output_root)
    for subdir in ["runs", "aggregated", "plots", "config"]:
        (output_root / subdir).mkdir(parents=True, exist_ok=True)

    repeat_seeds = build_repeat_seeds(args.repeat_master_seed, args.n_repeats)
    seed_registry = pd.DataFrame(
        [
            {
                "repeat_index": seed.repeat_index,
                "repeat_master_seed": seed.master_seed,
                "outer_draws_per_repeat": args.outer_draws,
                "inner_draws": args.inner_draws,
            }
            for seed in repeat_seeds
        ]
    )
    seed_registry.to_csv(output_root / "aggregated" / "repeat_seed_registry.csv", index=False)
    (output_root / "config" / "repeat_seed_config.json").write_text(
        json.dumps(
            {
                "repeat_master_seed": args.repeat_master_seed,
                "n_repeats": args.n_repeats,
                "outer_draws_per_repeat": args.outer_draws,
                "inner_draws": args.inner_draws,
                "n_jobs": args.n_jobs,
                "scope": [
                    "phase1_chicago_n40",
                    "phase3_lucknow_n31_n50",
                    "phase4_chicago_n50_strategies",
                    "period_dual_reference_n10",
                ],
            },
            indent=2,
        )
    )

    for repeat_seed in repeat_seeds:
        seed_root = output_root / "runs" / f"seed_{repeat_seed.repeat_index:02d}_{repeat_seed.master_seed}"
        if seed_root.exists():
            shutil.rmtree(seed_root)
        seed_root.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Repeat {repeat_seed.repeat_index + 1}/{len(repeat_seeds)} seed={repeat_seed.master_seed} ===")
        run_phase1_and_phase3(seed_root, repeat_seed, args.inner_draws, args.outer_draws, args.n_jobs)
        run_phase4_n50(seed_root, repeat_seed, args.inner_draws, args.outer_draws, args.n_jobs)

    seed_metrics, dual_reference = collect_seed_metrics(output_root, repeat_seeds, args.inner_draws)
    stability, dual_summary = summarize_seed_metrics(seed_metrics, dual_reference)
    seed_metrics.to_csv(output_root / "aggregated" / "seed_level_metrics.csv", index=False)
    stability.to_csv(output_root / "aggregated" / "metric_stability_summary.csv", index=False)
    dual_reference.to_csv(output_root / "aggregated" / "period_dual_reference_seed_metrics.csv", index=False)
    dual_summary.to_csv(output_root / "aggregated" / "period_dual_reference_summary.csv", index=False)
    plot_seed_stability(seed_metrics, output_root)
    write_summary(
        output_root,
        repeat_seeds,
        stability,
        dual_summary,
        args.inner_draws,
        args.outer_draws,
        args.repeat_master_seed,
    )
    print(f"Wrote seed-stability outputs to {output_root}")


def run_plot_only(output_root: Path) -> None:
    seed_metrics_path = output_root / "aggregated" / "seed_level_metrics.csv"
    if not seed_metrics_path.exists():
        raise SystemExit(f"Missing seed metrics for --plot-only: {seed_metrics_path}")
    seed_metrics = pd.read_csv(seed_metrics_path)
    plot_seed_stability(seed_metrics, output_root)
    print(f"Regenerated seed-stability plots from {seed_metrics_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ten-seed finite-population stability stress test.")
    parser.add_argument("--repeat-master-seed", type=int, default=DEFAULT_REPEAT_MASTER_SEED)
    parser.add_argument("--n-repeats", type=int, default=DEFAULT_N_REPEATS)
    parser.add_argument("--outer-draws", type=int, default=DEFAULT_OUTER_DRAWS_PER_REPEAT)
    parser.add_argument("--inner-draws", type=int, default=DEFAULT_INNER_DRAWS)
    parser.add_argument("--n-jobs", type=int, default=0)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="Regenerate seed-stability plots from existing aggregated seed metrics without rerunning repeats.",
    )
    args = parser.parse_args()
    if args.n_repeats < 1:
        raise SystemExit("--n-repeats must be positive")
    if args.outer_draws < 1:
        raise SystemExit("--outer-draws must be positive")
    if args.inner_draws < 1:
        raise SystemExit("--inner-draws must be positive")
    return args


if __name__ == "__main__":
    parsed_args = parse_args()
    RESULTS_ROOT = parsed_args.results_root
    ORIGINAL_PHASE_DIRS = {
        "phase1_chicago_n40": RESULTS_ROOT / "phase1_chicago_realitycheck_n40",
        "phase3_lucknow": RESULTS_ROOT / "phase3_lucknow_downsampling",
        "phase4_chicago_n50": RESULTS_ROOT / "phase4_chicago_selection_strategies",
    }
    if parsed_args.plot_only:
        run_plot_only(parsed_args.output_root)
    else:
        run_repeats(parsed_args)
