from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import GRID_COLOR, OUTPUT_DPI, save_figure, setup_matplotlib  # noqa: E402


DEFAULT_MASTER_SEED = 20260528
DEFAULT_RESULTS_ROOT = REPO_ROOT / "analysis" / "results" / "finite_population_experiments"
DEFAULT_BASELINE_RUN = (
    REPO_ROOT
    / "monte_carlo"
    / "results"
    / "runs"
    / "p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602"
)
PLOT_MIRROR = REPO_ROOT / "analysis" / "plots" / "finite_population_high_resolution_pdf"
MANUSCRIPT_FIGURE_DIR = (
    REPO_ROOT
    / "paper"
    / "Manuscript_and_SI"
    / "Plots"
    / "Supporting_Information"
    / "Figure_SI_20"
)
DATASETS = {
    "Dhaka": {
        "dataset_key": "dhaka_lcs",
        "daily_sensor_means": "preprocessed/dhaka_lcs_daily_sensor_means.parquet",
    },
    "Lucknow": {
        "dataset_key": "lucknow_lcs",
        "daily_sensor_means": "preprocessed/lucknow_lcs_daily_sensor_means.parquet",
    },
    "Chicago": {
        "dataset_key": "chicago_lcs_corrected_no_collocation",
        "daily_sensor_means": "preprocessed/chicago_lcs_corrected_no_collocation_daily_sensor_means.parquet",
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


def release_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return "<outside-repository>"


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def read_daily_cv(baseline_run: Path, city: str, rel_path: str) -> pd.DataFrame:
    frame = pd.read_parquet(baseline_run / rel_path)
    date_col = frame.columns[0]
    sensor_values = frame.drop(columns=[date_col]).apply(pd.to_numeric, errors="coerce")
    mean = sensor_values.mean(axis=1, skipna=True)
    sd = sensor_values.std(axis=1, skipna=True, ddof=1)
    valid_count = sensor_values.notna().sum(axis=1)
    cv_pct = sd / mean.abs() * 100.0
    return pd.DataFrame(
        {
            "city": city,
            "time_index": frame[date_col].astype(str),
            "daily_mean_ugm3": mean,
            "daily_sd_ugm3": sd,
            "daily_cv_pct": cv_pct,
            "valid_sensor_count": valid_count,
        }
    )


def read_daily_mdape(baseline_run: Path, sample_sizes: list[int]) -> pd.DataFrame:
    summary = pd.read_csv(baseline_run / "mc_summary" / "p0_baseline_summary.csv")
    keep_keys = {info["dataset_key"]: city for city, info in DATASETS.items()}
    daily = summary[
        (summary["time_aggregation"] == "daily")
        & (summary["sample_size"].isin(sample_sizes))
        & (summary["dataset_key"].isin(keep_keys))
    ].copy()
    daily["city"] = daily["dataset_key"].map(keep_keys)
    return daily[
        [
            "city",
            "dataset_key",
            "time_index",
            "sample_size",
            "ape_median_pct",
            "absolute_error_median_ugm3",
            "n_sensors_available",
            "reference_mean_ugm3",
        ]
    ]


def fit_ols(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    n = len(x)
    if n < 3:
        return {
            "n_days": n,
            "intercept": math.nan,
            "slope_beta": math.nan,
            "slope_se": math.nan,
            "slope_ci_low": math.nan,
            "slope_ci_high": math.nan,
            "r_squared": math.nan,
            "p_value": math.nan,
        }
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    sxx = float(np.sum((x - x_mean) ** 2))
    sxy = float(np.sum((x - x_mean) * (y - y_mean)))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    fitted = intercept + slope * x
    residuals = y - fitted
    sse = float(np.sum(residuals**2))
    sst = float(np.sum((y - y_mean) ** 2))
    sigma2 = sse / (n - 2)
    slope_se = math.sqrt(sigma2 / sxx)
    tcrit = float(stats.t.ppf(0.975, df=n - 2))
    _, p_value = stats.pearsonr(x, y)
    return {
        "n_days": n,
        "intercept": intercept,
        "slope_beta": slope,
        "slope_se": slope_se,
        "slope_ci_low": slope - tcrit * slope_se,
        "slope_ci_high": slope + tcrit * slope_se,
        "r_squared": 1.0 - sse / sst if sst > 0 else math.nan,
        "p_value": float(p_value),
    }


def prediction_band(x_grid: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    fit = fit_ols(x, y)
    y_hat = fit["intercept"] + fit["slope_beta"] * x_grid
    n = len(x)
    x_mean = float(np.mean(x))
    sxx = float(np.sum((x - x_mean) ** 2))
    residuals = y - (fit["intercept"] + fit["slope_beta"] * x)
    mse = float(np.sum(residuals**2) / (n - 2))
    tcrit = float(stats.t.ppf(0.975, df=n - 2))
    se_mean = np.sqrt(mse * (1.0 / n + (x_grid - x_mean) ** 2 / sxx))
    return y_hat, y_hat - tcrit * se_mean, y_hat + tcrit * se_mean


def build_analysis_frame(baseline_run: Path, sample_sizes: list[int]) -> pd.DataFrame:
    mdape = read_daily_mdape(baseline_run, sample_sizes)
    cv_frames = [
        read_daily_cv(baseline_run, city, info["daily_sensor_means"])
        for city, info in DATASETS.items()
    ]
    cv = pd.concat(cv_frames, ignore_index=True)
    merged = mdape.merge(cv, on=["city", "time_index"], how="left")
    merged = merged[np.isfinite(merged["daily_cv_pct"]) & np.isfinite(merged["ape_median_pct"])].copy()
    return merged.sort_values(["city", "sample_size", "time_index"])


def write_headline_numbers(slope_summary: pd.DataFrame, output_path: Path, master_seed: int) -> None:
    rows: list[dict[str, Any]] = []
    n10 = slope_summary[slope_summary["sample_size"] == 10]
    for _, row in n10.iterrows():
        rows.append(
            {
                "phase": 5,
                "city": row["city"],
                "metric_name": "cv_slope_beta",
                "target_N_star": np.nan,
                "aggregation": "across_days",
                "value_median": row["slope_beta"],
                "value_p5": row["slope_ci_low"],
                "value_p95": row["slope_ci_high"],
                "value_mean": row["slope_beta"],
                "value_sd": row["slope_se"],
                "n_outer_draws": 0,
                "n_inner_draws": 10000,
                "notes": (
                    "OLS slope for daily MdAPE at n=10 vs daily cross-sensor CV percent; "
                    f"deterministic baseline analysis, master seed {master_seed} retained for file naming."
                ),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False)


def plot_n10(frame: pd.DataFrame, slope_summary: pd.DataFrame, phase_dir: Path, master_seed: int) -> None:
    setup_matplotlib()
    plot_data = frame[frame["sample_size"] == 10].copy()
    fig, axis = plt.subplots(figsize=(6.9, 4.3))
    for city in ["Dhaka", "Lucknow", "Chicago"]:
        city_data = plot_data[plot_data["city"] == city]
        color = PLAN_CITY_COLORS[city]
        axis.scatter(
            city_data["daily_cv_pct"],
            city_data["ape_median_pct"],
            s=12,
            color=color,
            alpha=0.38,
            linewidths=0,
            label=f"{city} days",
        )
        x_values = city_data["daily_cv_pct"].to_numpy(dtype=float)
        y_values = city_data["ape_median_pct"].to_numpy(dtype=float)
        x_grid = np.linspace(np.nanmin(x_values), np.nanmax(x_values), 120)
        y_hat, ci_low, ci_high = prediction_band(x_grid, x_values, y_values)
        axis.plot(x_grid, y_hat, color=color, linewidth=2.0, label=f"{city} OLS")
        axis.fill_between(x_grid, ci_low, ci_high, color=color, alpha=0.14, linewidth=0)
    axis.set_xlabel("Daily cross-sensor CV (%)")
    axis.set_ylabel("Daily MdAPE at n=10 (%)")
    axis.set_title("Daily subnetwork error increases with cross-sensor heterogeneity")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
    handles, labels = axis.get_legend_handles_labels()
    keep_handles: list[Any] = []
    keep_labels: list[str] = []
    for handle, label in zip(handles, labels, strict=True):
        if label.endswith("OLS"):
            keep_handles.append(handle)
            keep_labels.append(label.replace(" OLS", ""))
    axis.legend(keep_handles, keep_labels, title="City OLS fit", frameon=False, loc="upper left")
    save_figure(
        fig,
        phase_dir / "plots" / "three_city_mdape_vs_cv_slope",
        dpi=OUTPUT_DPI,
    )


def write_summary(phase_dir: Path, slope_summary: pd.DataFrame, master_seed: int) -> None:
    n10 = slope_summary[slope_summary["sample_size"] == 10].set_index("city")
    lines = [
        "# Phase 5 Summary — MdAPE-vs-CV Slope",
        "",
        f"- Master seed label: `{master_seed}`",
        "- Analysis uses existing baseline Monte Carlo daily MdAPE outputs; no new outer finite-population draw is used.",
        "- X-axis: daily cross-sensor coefficient of variation, computed as 100 × SD / mean across valid sensors.",
        "- Y-axis: daily MdAPE at n=10 from the baseline 10,000-draw SRSWOR Monte Carlo.",
        "",
        "## n=10 slope estimates",
        "",
        "| City | slope beta | SE | 95% CI | R² | days |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for city in ["Dhaka", "Lucknow", "Chicago"]:
        row = n10.loc[city]
        lines.append(
            f"| {city} | {row['slope_beta']:.4f} | {row['slope_se']:.4f} | "
            f"{row['slope_ci_low']:.4f} to {row['slope_ci_high']:.4f} | "
            f"{row['r_squared']:.3f} | {int(row['n_days'])} |"
        )
    chicago_slope = float(n10.loc["Chicago", "slope_beta"])
    south_asia_mean = float(n10.loc[["Dhaka", "Lucknow"], "slope_beta"].mean())
    if chicago_slope < south_asia_mean:
        verdict = (
            "Chicago's slope is smaller than the average South Asian slope, so the same increase "
            "in cross-sensor CV translates into less subnetwork error in Chicago."
        )
    else:
        verdict = (
            "Chicago's slope is not smaller than the South Asian slopes in this run; the local-source "
            "interpretation should be treated cautiously."
        )
    lines.extend(
        [
            "",
            f"Verdict: {verdict}",
            "",
            "Use the simple interpretation only: the slope is the rate at which daily cross-sensor heterogeneity translates into subnetwork error. Do not present this as a formal variance-decomposition mechanism.",
            "",
            "## Main outputs",
            "",
            "- Figure: `plots/three_city_mdape_vs_cv_slope.pdf`",
            "- Slope table: `aggregated/slope_summary.csv`",
            "- Headline table: `aggregated/headline_numbers.csv`",
        ]
    )
    (phase_dir / "phase5_summary.md").write_text("\n".join(lines) + "\n")


def update_top_level_readme(results_root: Path, master_seed: int) -> None:
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
    rows["5"] = [
        "5",
        "done",
        datetime.now().date().isoformat(),
        str(master_seed),
        "MdAPE-vs-CV slope completed",
        "phase5_mdape_vs_cv_slope/phase5_summary.md",
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
    source_pdf = phase_dir / "plots" / "three_city_mdape_vs_cv_slope.pdf"
    if source_pdf.exists():
        MANUSCRIPT_FIGURE_DIR.mkdir(parents=True, exist_ok=True)
        (MANUSCRIPT_FIGURE_DIR / source_pdf.name).write_bytes(source_pdf.read_bytes())


def run(args: argparse.Namespace) -> None:
    args.baseline_run = resolve_repo_path(args.baseline_run)
    args.results_root = resolve_repo_path(args.results_root)
    phase_dir = args.results_root / "phase5_mdape_vs_cv_slope"
    if phase_dir.exists() and not args.overwrite:
        raise SystemExit(f"Phase directory already exists: {phase_dir}")
    for subdir in ["config", "aggregated", "plots"]:
        (phase_dir / subdir).mkdir(parents=True, exist_ok=True)

    config = {
        "phase": 5,
        "phase_name": "phase5_mdape_vs_cv_slope",
        "master_seed": args.master_seed,
        "sample_sizes": args.sample_sizes,
        "baseline_run": release_path(args.baseline_run),
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (phase_dir / "config" / "master_seed.json").write_text(json.dumps(config, indent=2))

    frame = build_analysis_frame(args.baseline_run, args.sample_sizes)
    frame.to_csv(phase_dir / "aggregated" / "daily_mdape_cv_analysis_table.csv", index=False)
    frame.to_parquet(phase_dir / "aggregated" / "daily_mdape_cv_analysis_table.parquet", index=False)

    slope_rows: list[dict[str, Any]] = []
    for sample_size in args.sample_sizes:
        for city in ["Dhaka", "Lucknow", "Chicago"]:
            subset = frame[(frame["city"] == city) & (frame["sample_size"] == sample_size)]
            fit = fit_ols(
                subset["daily_cv_pct"].to_numpy(dtype=float),
                subset["ape_median_pct"].to_numpy(dtype=float),
            )
            slope_rows.append({"city": city, "sample_size": sample_size, **fit})
    slope_summary = pd.DataFrame(slope_rows)
    slope_summary.to_csv(phase_dir / "aggregated" / "slope_summary.csv", index=False)
    write_headline_numbers(
        slope_summary,
        phase_dir / "aggregated" / "headline_numbers.csv",
        args.master_seed,
    )
    plot_n10(frame, slope_summary, phase_dir, args.master_seed)
    mirror_plots(phase_dir)
    write_summary(phase_dir, slope_summary, args.master_seed)
    update_top_level_readme(args.results_root, args.master_seed)
    print(f"Wrote {phase_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Phase 5 MdAPE-vs-CV slope analysis.")
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--baseline-run", type=Path, default=DEFAULT_BASELINE_RUN)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--sample-sizes", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
