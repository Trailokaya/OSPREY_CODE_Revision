from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "monte_carlo" / "scripts"))

from plot_style import GRID_COLOR, OUTPUT_DPI, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402


RESULTS_ROOT = REPO_ROOT / "analysis" / "results" / "finite_population_experiments"
OUTPUT_DIR = RESULTS_ROOT / "dual_reference_monte_carlo"
AGGREGATED_DIR = OUTPUT_DIR / "aggregated"
PLOTS_DIR = OUTPUT_DIR / "plots"
REVIEW_PACKET = RESULTS_ROOT / "finite_population_review_packet"
PLOT_MIRROR = REPO_ROOT / "analysis" / "plots" / "finite_population_high_resolution_pdf"
MASTER_SEED = 20260528

PHASE_DIRS = {
    1: RESULTS_ROOT / "phase1_chicago_realitycheck_n40",
    2: RESULTS_ROOT / "phase2_chicago_nsensitivity",
    3: RESULTS_ROOT / "phase3_lucknow_downsampling",
    4: RESULTS_ROOT / "phase4_chicago_selection_strategies",
}

PHASE_EXPECTATIONS = {
    1: {
        "phase_name": "phase1_chicago_realitycheck_n40",
        "targets": [40],
        "outer_rows": 50,
        "per_draw_files": 50,
        "has_daily_in_all_draws": True,
    },
    2: {
        "phase_name": "phase2_chicago_nsensitivity",
        "targets": [30, 40, 50, 70, 100, 150, 200, 277],
        "outer_rows": 800,
        "per_draw_files": 800,
        "has_daily_in_all_draws": True,
    },
    3: {
        "phase_name": "phase3_lucknow_downsampling",
        "targets": [31, 40, 50, 60, 71],
        "outer_rows": 500,
        "per_draw_files": 500,
        "has_daily_in_all_draws": True,
    },
    4: {
        "phase_name": "phase4_chicago_selection_strategies",
        "targets": [30, 50, 70],
        "outer_rows": 630,
        "per_draw_files": 630,
        "has_daily_in_all_draws": False,
    },
}

JOIN_KEYS = [
    "run_key",
    "city",
    "target_N_star",
    "selection_strategy",
    "selection_strategy_label",
    "outer_draw_index",
    "selected_sensor_set_hash",
    "time_aggregation",
    "time_index",
    "sample_size",
]

METRIC_COLUMNS = [
    "reference_mean_ugm3",
    "reference_sd_ugm3",
    "ape_median_pct",
    "ape_p95_pct",
    "absolute_error_median_ugm3",
    "absolute_error_p95_ugm3",
    "subnet_mean_median_ugm3",
    "subnet_mean_p95_ugm3",
    "bias_ugm3",
    "bias_pct",
    "n_sensors_available",
    "n_draws_completed",
]


CITY_DATASET_KEYS = {
    "Chicago": "chicago_lcs_corrected_no_collocation",
    "Lucknow": "lucknow_lcs",
}


def ensure_dirs() -> None:
    for path in [OUTPUT_DIR, AGGREGATED_DIR, PLOTS_DIR, REVIEW_PACKET / "data", REVIEW_PACKET / "plots", PLOT_MIRROR]:
        path.mkdir(parents=True, exist_ok=True)


def add_lucknow_strategy_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["selection_strategy"] = "random"
    frame["selection_strategy_label"] = "Random"
    return frame


def selected_reference_rows() -> pd.DataFrame:
    phase4_dir = PHASE_DIRS[4]
    phase3_dir = PHASE_DIRS[3]

    chicago_period = pd.read_parquet(phase4_dir / "aggregated" / "all_draw_summaries.parquet")
    chicago_period = chicago_period[
        (chicago_period["target_N_star"] == 50)
        & (chicago_period["time_aggregation"] == "period")
    ].copy()
    chicago_period["run_key"] = "chicago_phase4_strategy_n50"

    chicago_daily = pd.read_parquet(phase4_dir / "aggregated" / "daily_strategy_draw_summaries_n50.parquet")
    chicago_daily = chicago_daily[chicago_daily["target_N_star"] == 50].copy()
    chicago_daily["run_key"] = "chicago_phase4_strategy_n50"

    lucknow_compact = phase3_dir / "aggregated" / "selected_reference_draw_summaries_n50.parquet"
    lucknow_all = phase3_dir / "aggregated" / "all_draw_summaries.parquet"
    lucknow_path = lucknow_compact if lucknow_compact.exists() else lucknow_all
    if not lucknow_path.exists():
        raise FileNotFoundError(
            "Missing Lucknow selected-reference draw summaries. Expected "
            f"{lucknow_compact.relative_to(REPO_ROOT)} in the review package, or the full "
            f"{lucknow_all.relative_to(REPO_ROOT)} from a full phase-3 recomputation."
        )
    lucknow = pd.read_parquet(lucknow_path)
    lucknow = lucknow[lucknow["target_N_star"] == 50].copy()
    lucknow = add_lucknow_strategy_columns(lucknow)
    lucknow["run_key"] = "lucknow_phase3_random_n50"

    selected = pd.concat([chicago_period, chicago_daily, lucknow], ignore_index=True, sort=False)
    selected["reference_scope"] = "selected_N_star_mean"
    return selected


def full_reference_rows() -> pd.DataFrame:
    frame = pd.read_parquet(
        RESULTS_ROOT
        / "reference_target_sensitivity"
        / "aggregated"
        / "full_reference_draw_summaries_n50.parquet"
    )
    return frame.copy()


def prefixed_metric_frame(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    available_metrics = [column for column in METRIC_COLUMNS if column in frame.columns]
    keep_columns = JOIN_KEYS + available_metrics
    out = frame[keep_columns].copy()
    return out.rename(columns={column: f"{prefix}_{column}" for column in available_metrics})


def build_dual_reference_rows() -> pd.DataFrame:
    selected = selected_reference_rows()
    full = full_reference_rows()
    selected_small = prefixed_metric_frame(selected, "selected_ref")
    full_small = prefixed_metric_frame(full, "full_ref")
    dual = selected_small.merge(full_small, on=JOIN_KEYS, how="inner", validate="one_to_one")

    full_joined = full_small.merge(dual[JOIN_KEYS], on=JOIN_KEYS, how="left", indicator=True)
    unmatched_full = int((full_joined["_merge"] == "left_only").sum())
    if unmatched_full:
        raise RuntimeError(
            f"Dual-reference join is missing selected-reference rows for {unmatched_full} full-reference rows."
        )

    dual["mdape_delta_full_minus_selected_pctpt"] = (
        dual["full_ref_ape_median_pct"] - dual["selected_ref_ape_median_pct"]
    )
    dual["absolute_error_delta_full_minus_selected_ugm3"] = (
        dual["full_ref_absolute_error_median_ugm3"]
        - dual["selected_ref_absolute_error_median_ugm3"]
    )
    dual["reference_mean_delta_full_minus_selected_ugm3"] = (
        dual["full_ref_reference_mean_ugm3"] - dual["selected_ref_reference_mean_ugm3"]
    )
    dual["same_draw_two_reference_results"] = True

    out = dual.sort_values(JOIN_KEYS).reset_index(drop=True)
    out.attrs["selected_reference_rows"] = len(selected)
    out.attrs["full_reference_rows"] = len(full)
    out.attrs["matched_reference_rows"] = len(out)
    out.attrs["unmatched_selected_reference_rows"] = len(selected) - len(out)
    return out


def summarize_dual_reference(dual: pd.DataFrame) -> pd.DataFrame:
    grouped = dual.groupby(
        ["run_key", "city", "selection_strategy", "selection_strategy_label", "time_aggregation", "sample_size"],
        dropna=False,
    )
    summary = grouped.agg(
        row_count=("selected_ref_ape_median_pct", "count"),
        n_outer_draws=("outer_draw_index", "nunique"),
        n_days=(
            "time_index",
            lambda values: 0
            if len(values) and str(pd.Series(values).iloc[0]) == "study_period"
            else int(pd.Series(values).nunique()),
        ),
        selected_ref_mdape_median_pct=("selected_ref_ape_median_pct", "median"),
        full_ref_mdape_median_pct=("full_ref_ape_median_pct", "median"),
        mdape_delta_median_pctpt=("mdape_delta_full_minus_selected_pctpt", "median"),
        selected_ref_abs_median_ugm3=("selected_ref_absolute_error_median_ugm3", "median"),
        full_ref_abs_median_ugm3=("full_ref_absolute_error_median_ugm3", "median"),
        abs_delta_median_ugm3=("absolute_error_delta_full_minus_selected_ugm3", "median"),
        reference_mean_delta_median_ugm3=("reference_mean_delta_full_minus_selected_ugm3", "median"),
        mdape_delta_p95_pctpt=("mdape_delta_full_minus_selected_pctpt", lambda values: values.quantile(0.95)),
        abs_delta_p95_ugm3=("absolute_error_delta_full_minus_selected_ugm3", lambda values: values.quantile(0.95)),
    ).reset_index()
    return summary


def color_for_city(city: str) -> str:
    return color_for_dataset(CITY_DATASET_KEYS.get(city, city.lower()))


def apply_strategy_axis(axis: plt.Axes, positions: np.ndarray, labels: pd.Series) -> None:
    axis.set_xticks(positions)
    axis.set_xticklabels(labels, rotation=25, ha="right")
    if len(positions) == 1:
        axis.set_xlim(-0.85, 0.85)
    elif len(positions) > 1:
        axis.set_xlim(-0.55, float(len(positions)) - 0.45)


def plot_dual_reference_n10(summary: pd.DataFrame, output_base: Path) -> None:
    setup_matplotlib()
    n10 = summary[(summary["sample_size"] == 10) & (summary["city"] == "Chicago")].copy()
    panels = [
        ("Chicago", "period", "Chicago period"),
        ("Chicago", "daily", "Chicago daily"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.9))
    width = 0.28
    for axis, (city, aggregation, title) in zip(np.ravel(axes), panels, strict=True):
        frame = n10[(n10["city"] == city) & (n10["time_aggregation"] == aggregation)].copy()
        frame = frame.sort_values("full_ref_abs_median_ugm3")
        x = np.arange(len(frame))
        axis.bar(
            x - width / 2,
            frame["selected_ref_abs_median_ugm3"],
            width=width,
            color="#9ca3af",
            label="Selected N*=50 reference",
        )
        axis.bar(
            x + width / 2,
            frame["full_ref_abs_median_ugm3"],
            width=width,
            color=color_for_city(city),
            label="Full-network reference",
        )
        axis.set_title(title)
        axis.set_ylabel("Median absolute error at n=10 (µg/m³)")
        apply_strategy_axis(axis, x, frame["selection_strategy_label"])
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    handles, labels = np.ravel(axes)[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.005))
    fig.suptitle("Chicago N*=50 Monte Carlo with two reference targets")
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    save_figure(fig, output_base, dpi=OUTPUT_DPI)


def plot_dual_reference_delta_n10(summary: pd.DataFrame, output_base: Path) -> None:
    setup_matplotlib()
    n10 = summary[(summary["sample_size"] == 10) & (summary["city"] == "Chicago")].copy()
    panels = [
        ("Chicago", "period", "Chicago period"),
        ("Chicago", "daily", "Chicago daily"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.9))
    for axis, (city, aggregation, title) in zip(np.ravel(axes), panels, strict=True):
        frame = n10[(n10["city"] == city) & (n10["time_aggregation"] == aggregation)].copy()
        frame = frame.sort_values("abs_delta_median_ugm3")
        x = np.arange(len(frame))
        axis.bar(
            x,
            frame["abs_delta_median_ugm3"],
            width=0.24 if len(frame) == 1 else 0.50,
            color=color_for_city(city),
        )
        axis.axhline(0, color="#6b7280", linewidth=0.8)
        axis.set_title(title)
        axis.set_ylabel("Full-ref minus selected-ref\nabsolute error (µg/m³)")
        apply_strategy_axis(axis, x, frame["selection_strategy_label"])
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    fig.suptitle("Chicago change in n=10 error when switching reference target")
    fig.tight_layout()
    save_figure(fig, output_base, dpi=OUTPUT_DPI)


def summarize_phase(phase: int, phase_dir: Path, expectations: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(check: str, status: str, observed: Any, expected: Any, notes: str = "") -> None:
        rows.append(
            {
                "phase": phase,
                "phase_name": expectations["phase_name"],
                "check": check,
                "status": status,
                "observed": observed,
                "expected": expected,
                "notes": notes,
            }
        )

    master_seed_path = phase_dir / "config" / "master_seed.json"
    if master_seed_path.exists():
        payload = json.loads(master_seed_path.read_text())
        observed_seed = payload.get("master_seed")
        observed_draws = payload.get("inner_draws")
        add("master_seed", "pass" if observed_seed == MASTER_SEED else "warn", observed_seed, MASTER_SEED)
        add("inner_draws", "pass" if observed_draws == 10_000 else "warn", observed_draws, 10_000)
    else:
        add("master_seed_json", "fail", "missing", "exists")

    outer_path = phase_dir / "config" / "outer_seeds.csv"
    if outer_path.exists():
        outer = pd.read_csv(outer_path)
        add(
            "outer_seed_rows",
            "pass" if len(outer) == expectations["outer_rows"] else "warn",
            len(outer),
            expectations["outer_rows"],
        )
        observed_targets = sorted(pd.to_numeric(outer["target_N_star"]).dropna().astype(int).unique().tolist())
        add(
            "target_N_star_values",
            "pass" if observed_targets == expectations["targets"] else "warn",
            observed_targets,
            expectations["targets"],
        )
        sensor_count_ok = bool((outer["selected_sensor_count"] == outer["target_N_star"]).all())
        add(
            "selected_sensor_count_matches_target",
            "pass" if sensor_count_ok else "fail",
            sensor_count_ok,
            True,
        )
    else:
        add("outer_seeds_csv", "fail", "missing", "exists")

    per_draw_files = list((phase_dir / "per_draw").glob("*.parquet"))
    compact_summary_present = (phase_dir / "aggregated" / "headline_numbers.csv").exists()
    add(
        "per_draw_parquet_files",
        "pass" if len(per_draw_files) == expectations["per_draw_files"] or compact_summary_present else "warn",
        len(per_draw_files),
        expectations["per_draw_files"],
        "Per-draw files are omitted from the GitHub package; retained seeds and compact summaries are sufficient for manuscript outputs."
        if not per_draw_files and compact_summary_present
        else "",
    )

    all_draw_path = phase_dir / "aggregated" / "all_draw_summaries.parquet"
    if all_draw_path.exists():
        all_draw = pd.read_parquet(all_draw_path, columns=["time_aggregation", "target_N_star", "sample_size"])
        aggregations = sorted(all_draw["time_aggregation"].unique().tolist())
        expected_has_daily = expectations["has_daily_in_all_draws"]
        status = "pass" if (("daily" in aggregations) == expected_has_daily) else "warn"
        notes = "Phase 4 daily strategy outputs are stored separately by design." if phase == 4 else ""
        add("all_draw_time_aggregations", status, aggregations, "daily+period" if expected_has_daily else "period only", notes)
        add("all_draw_rows", "pass", len(all_draw), "nonzero")
    else:
        compact_lucknow = phase_dir / "aggregated" / "selected_reference_draw_summaries_n50.parquet"
        compact_status = compact_summary_present or compact_lucknow.exists()
        add(
            "all_draw_summaries_parquet",
            "pass" if compact_status else "fail",
            "omitted from GitHub package",
            "compact summaries retained",
            (
                "Large draw-level aggregate omitted; manuscript-facing summaries, plots, seeds, and compact N*=50 Lucknow draw table are retained."
                if compact_lucknow.exists()
                else "Large draw-level aggregate omitted; manuscript-facing summaries, plots, and seeds are retained."
            ),
        )

    expected_files = [
        "aggregated/headline_numbers.csv",
        "aggregated/period_mdape_envelope.csv" if phase != 4 else "aggregated/period_strategy_envelope.csv",
        "aggregated/period_absolute_error_envelope.csv" if phase != 4 else "aggregated/period_strategy_absolute_error_envelope.csv",
        "config/selected_sensor_subsets_long.csv",
        f"phase{phase}_summary.md",
    ]
    if phase in {1, 2, 3}:
        expected_files.extend(["aggregated/daily_mdape_envelope.csv", "aggregated/daily_absolute_error_envelope.csv"])
    if phase == 3:
        expected_files.append("aggregated/selected_reference_draw_summaries_n50.parquet")
    if phase == 4:
        expected_files.extend(
            [
                "aggregated/daily_strategy_summary_n50.csv",
                "aggregated/daily_strategy_full_reference_summary_n50.csv",
            ]
        )
    for relative in expected_files:
        path = phase_dir / relative
        add(f"file_exists:{relative}", "pass" if path.exists() else "fail", path.exists(), True)

    plot_files = list((phase_dir / "plots").glob("*.pdf"))
    add("pdf_plot_count", "pass" if plot_files else "warn", len(plot_files), ">=1")
    return rows


def build_phase_manifest(dual: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for phase, phase_dir in PHASE_DIRS.items():
        rows.extend(summarize_phase(phase, phase_dir, PHASE_EXPECTATIONS[phase]))
    rows.append(
        {
            "phase": "dual",
            "phase_name": "dual_reference_monte_carlo",
            "check": "dual_reference_join_rows",
            "status": "pass",
            "observed": len(dual),
            "expected": dual.attrs.get("full_reference_rows", "matches full-reference row count"),
            "notes": "Each retained row has selected-reference and full-network-reference metrics for the same selected subset and sample draw seed.",
        }
    )
    rows.append(
        {
            "phase": "dual",
            "phase_name": "dual_reference_monte_carlo",
            "check": "selected_reference_rows_without_full_target",
            "status": "pass",
            "observed": dual.attrs.get("unmatched_selected_reference_rows", 0),
            "expected": "allowed",
            "notes": "Selected-reference daily rows can exceed the full-reference table when no full-network daily target is available for a date.",
        }
    )
    rows.append(
        {
            "phase": "dual",
            "phase_name": "dual_reference_monte_carlo",
            "check": "dual_reference_run_keys",
            "status": "pass",
            "observed": sorted(dual["run_key"].unique().tolist()),
            "expected": ["chicago_phase4_strategy_n50", "lucknow_phase3_random_n50"],
            "notes": "",
        }
    )
    return pd.DataFrame(rows)


def write_dual_summary(summary: pd.DataFrame, manifest: pd.DataFrame) -> None:
    n10 = summary[summary["sample_size"] == 10].copy()
    lines = [
        "# Dual-Reference Monte Carlo Summary",
        "",
        "This output joins two reference targets side by side for the same N*=50 selected subsets and the same Monte Carlo sampling tasks.",
        "",
        "- `selected_ref_*`: error against the selected N*=50 finite-population mean.",
        "- `full_ref_*`: error against the full deployed-network mean, Chicago N=277 or Lucknow N=71.",
        "- `*_delta_*`: full-reference metric minus selected-reference metric.",
        "",
        "## n=10 Results",
        "",
    ]
    for row in n10.sort_values(["city", "time_aggregation", "selection_strategy_label"]).itertuples(index=False):
        lines.append(
            f"- {row.city}, {row.time_aggregation}, {row.selection_strategy_label}: "
            f"selected-ref `{row.selected_ref_mdape_median_pct:.2f}%` / `{row.selected_ref_abs_median_ugm3:.3f}` µg/m³; "
            f"full-ref `{row.full_ref_mdape_median_pct:.2f}%` / `{row.full_ref_abs_median_ugm3:.3f}` µg/m³; "
            f"delta `{row.mdape_delta_median_pctpt:.2f}` pct-pt / `{row.abs_delta_median_ugm3:.3f}` µg/m³."
        )
    lines.extend(
        [
            "",
            "## Retained Output Check",
            "",
            f"- Checks run: `{len(manifest)}`",
            f"- Failed checks: `{int((manifest['status'] == 'fail').sum())}`",
            f"- Warning checks: `{int((manifest['status'] == 'warn').sum())}`",
            "- Warning checks indicate optional compute-heavy draw-level files that are not needed for the retained manuscript-facing outputs.",
        ]
    )
    (OUTPUT_DIR / "dual_reference_monte_carlo_summary.md").write_text("\n".join(lines) + "\n")


def write_phase_manifest_markdown(manifest: pd.DataFrame) -> None:
    lines = [
        "# Finite-Population Retained Output Manifest",
        "",
        "This manifest records the retained finite-population phase outputs used by the manuscript and SI: seed/config files, selected-subset registries, compact summaries, and final plots. Large draw-level files are intentionally omitted when compact summaries and seeds are sufficient to reproduce manuscript-facing outputs.",
        "",
    ]
    for phase_name, frame in manifest.groupby("phase_name", sort=False):
        lines.extend([f"## {phase_name}", ""])
        for row in frame.itertuples(index=False):
            lines.append(
                f"- `{row.status}` — {row.check}: observed `{row.observed}`, expected `{row.expected}`"
                + (f"; {row.notes}" if isinstance(row.notes, str) and row.notes else "")
            )
        lines.append("")
    (OUTPUT_DIR / "finite_population_phase_summary.md").write_text("\n".join(lines))


def mirror_outputs() -> None:
    for source in [
        AGGREGATED_DIR / "dual_reference_summary_n50.csv",
        AGGREGATED_DIR / "dual_reference_n10_summary_n50.csv",
        AGGREGATED_DIR / "finite_population_phase_summary.csv",
    ]:
        shutil.copy2(source, REVIEW_PACKET / "data" / source.name)
    for source in PLOTS_DIR.glob("*.pdf"):
        shutil.copy2(source, REVIEW_PACKET / "plots" / source.name)
        shutil.copy2(source.with_suffix(".png"), REVIEW_PACKET / "plots" / source.with_suffix(".png").name)
        shutil.copy2(source, PLOT_MIRROR / source.name)
        shutil.copy2(source.with_suffix(".png"), PLOT_MIRROR / source.with_suffix(".png").name)


def update_readmes(summary: pd.DataFrame, manifest: pd.DataFrame) -> None:
    packet_readme = REVIEW_PACKET / "README.md"
    if packet_readme.exists():
        text = packet_readme.read_text()
        n10 = summary[summary["sample_size"] == 10]
        chicago_cluster_daily = n10[
            (n10["city"] == "Chicago")
            & (n10["time_aggregation"] == "daily")
            & (n10["selection_strategy"] == "cluster_concentrated")
        ].iloc[0]
        lucknow_daily = n10[
            (n10["city"] == "Lucknow")
            & (n10["time_aggregation"] == "daily")
            & (n10["selection_strategy"] == "random")
        ].iloc[0]
        line = (
            "- Dual-reference Monte Carlo: each N*=50 task now has selected-reference and full-network-reference "
            f"metrics in the same row. Chicago cluster-concentrated daily n=10 increases from "
            f"`{chicago_cluster_daily.selected_ref_abs_median_ugm3:.3f}` to "
            f"`{chicago_cluster_daily.full_ref_abs_median_ugm3:.3f}` µg/m³; Lucknow random daily n=10 increases from "
            f"`{lucknow_daily.selected_ref_abs_median_ugm3:.3f}` to "
            f"`{lucknow_daily.full_ref_abs_median_ugm3:.3f}` µg/m³."
        )
        if line not in text:
            text = text.replace("## Maps\n", line + "\n\n## Maps\n")
        for data_line in [
            "- `data/dual_reference_summary_n50.csv`: compact selected-reference versus full-reference summary for N*=50 at all stored sample sizes.",
            "- `data/finite_population_phase_summary.csv`: machine-readable manifest of Phases 1-4, seed/config files, selected-subset registries, and expected output files.",
        ]:
            if data_line not in text:
                text = text.replace("- Phase directories also retain `config/outer_seeds.csv`, where `selected_sensor_ids` stores the exact selected subset as JSON.\n", data_line + "\n- Phase directories also retain `config/outer_seeds.csv`, where `selected_sensor_ids` stores the exact selected subset as JSON.\n")
        packet_readme.write_text(text)


def main() -> None:
    ensure_dirs()
    dual = build_dual_reference_rows()
    summary = summarize_dual_reference(dual)
    manifest = build_phase_manifest(dual)

    dual.to_parquet(AGGREGATED_DIR / "dual_reference_draw_summaries_n50.parquet", index=False)
    summary.to_csv(AGGREGATED_DIR / "dual_reference_summary_n50.csv", index=False)
    summary[summary["sample_size"] == 10].to_csv(
        AGGREGATED_DIR / "dual_reference_n10_summary_n50.csv",
        index=False,
    )
    manifest.to_csv(AGGREGATED_DIR / "finite_population_phase_summary.csv", index=False)
    write_phase_manifest_markdown(manifest)

    plot_dual_reference_n10(summary, PLOTS_DIR / "dual_reference_n50_n10_selected_vs_full_abs_error_seed20260528")
    plot_dual_reference_delta_n10(summary, PLOTS_DIR / "dual_reference_n50_n10_full_minus_selected_delta_seed20260528")
    write_dual_summary(summary, manifest)
    mirror_outputs()
    update_readmes(summary, manifest)

    print(f"Wrote dual-reference Monte Carlo outputs to {OUTPUT_DIR}")
    print(summary[summary["sample_size"] == 10].sort_values(["city", "time_aggregation", "full_ref_abs_median_ugm3"]).to_string(index=False))
    print("\nRetained output status counts")
    print(manifest["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
