from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

from build_estimator_diagnostics import DATASETS, DatasetBundle, derive_seed, draw_sample_positions, load_dataset  # noqa: E402
from plot_style import GRID_COLOR, OUTPUT_DPI, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402


OUTPUT_DIR = REPO_ROOT / "analysis/results/estimator_comparison"
PLOT_DIR = REPO_ROOT / "analysis/plots/estimator_comparison"
MASTER_SEED = 20260525
DRAWS = 10_000
SAMPLE_SIZES = (5, 10, 15, 20)

ESTIMATOR_LABELS = {
    "arithmetic_mean": "Arithmetic mean",
    "robust_arithmetic_median": "Robust median",
    "lognormal_mean": "Lognormal mean",
    "robust_lognormal_median_mad": "Robust lognormal",
}

ESTIMATOR_COLORS = {
    "arithmetic_mean": "#111827",
    "robust_arithmetic_median": "#2563eb",
    "lognormal_mean": "#dc2626",
    "robust_lognormal_median_mad": "#16a34a",
}


def safe_mean(values: np.ndarray, axis: int) -> np.ndarray:
    counts = np.isfinite(values).sum(axis=axis)
    sums = np.nansum(values, axis=axis)
    return np.divide(sums, counts, out=np.full_like(sums, np.nan, dtype=float), where=counts > 0)


def mad(values: np.ndarray, axis: int) -> np.ndarray:
    median = np.nanmedian(values, axis=axis)
    if axis == 1:
        deviations = np.abs(values - median[:, None])
    elif axis == 0:
        deviations = np.abs(values - median[None, :])
    else:
        raise ValueError("mad only supports axis 0 or 1")
    return np.nanmedian(deviations, axis=axis)


def estimator_mean_values(samples: np.ndarray) -> dict[str, np.ndarray]:
    samples = np.asarray(samples, dtype=float)
    arithmetic = safe_mean(samples, axis=1)
    robust = np.nanmedian(samples, axis=1)
    positive = np.where(samples > 0, samples, np.nan)
    log_values = np.log(positive)
    log_mu = safe_mean(log_values, axis=1)
    log_var = np.nanvar(log_values, axis=1, ddof=1)
    lognormal = np.exp(log_mu + log_var / 2.0)
    log_median = np.nanmedian(log_values, axis=1)
    log_mad = mad(log_values, axis=1)
    robust_sigma = 1.4826 * log_mad
    robust_lognormal = np.exp(log_median + robust_sigma**2 / 2.0)
    return {
        "arithmetic_mean": arithmetic,
        "robust_arithmetic_median": robust,
        "lognormal_mean": lognormal,
        "robust_lognormal_median_mad": robust_lognormal,
    }


def full_network_estimators(values: np.ndarray) -> dict[str, float]:
    valid = np.asarray(values, dtype=float)
    valid = valid[np.isfinite(valid)]
    if len(valid) == 0:
        return {f"{name}_{metric}": np.nan for name in ESTIMATOR_LABELS for metric in ["mean", "sd"]}
    positive = valid[valid > 0]
    arithmetic_mean = float(np.mean(valid))
    arithmetic_sd = float(np.std(valid, ddof=1)) if len(valid) > 1 else np.nan
    robust_mean = float(np.median(valid))
    robust_sd = float(1.4826 * np.median(np.abs(valid - np.median(valid)))) if len(valid) > 1 else np.nan
    if len(positive) > 1:
        log_values = np.log(positive)
        log_mu = float(np.mean(log_values))
        log_var = float(np.var(log_values, ddof=1))
        lognormal_mean = float(np.exp(log_mu + log_var / 2.0))
        lognormal_sd = float(math.sqrt(max(math.exp(log_var) - 1.0, 0.0)) * math.exp(log_mu + log_var / 2.0))
        log_median = float(np.median(log_values))
        log_sigma = float(1.4826 * np.median(np.abs(log_values - log_median)))
        robust_lognormal_mean = float(np.exp(log_median + log_sigma**2 / 2.0))
        robust_lognormal_sd = float(math.sqrt(max(math.exp(log_sigma**2) - 1.0, 0.0)) * math.exp(log_median + log_sigma**2 / 2.0))
    else:
        lognormal_mean = np.nan
        lognormal_sd = np.nan
        robust_lognormal_mean = np.nan
        robust_lognormal_sd = np.nan
    return {
        "arithmetic_mean_mean": arithmetic_mean,
        "arithmetic_mean_sd": arithmetic_sd,
        "robust_arithmetic_median_mean": robust_mean,
        "robust_arithmetic_median_sd": robust_sd,
        "lognormal_mean_mean": lognormal_mean,
        "lognormal_mean_sd": lognormal_sd,
        "robust_lognormal_median_mad_mean": robust_lognormal_mean,
        "robust_lognormal_median_mad_sd": robust_lognormal_sd,
    }


def build_daily_full_network_estimator_table(bundle: DatasetBundle) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row_index, date in enumerate(bundle.daily_dates):
        values = bundle.daily_values[row_index, :]
        estimates = full_network_estimators(values)
        reference_mean = estimates["arithmetic_mean_mean"]
        reference_sd = estimates["arithmetic_mean_sd"]
        n_valid = int(np.isfinite(values).sum())
        for estimator in ESTIMATOR_LABELS:
            mean_value = estimates[f"{estimator}_mean"]
            sd_value = estimates[f"{estimator}_sd"]
            rows.append(
                {
                    "dataset_key": bundle.spec.key,
                    "city": bundle.spec.city,
                    "date": date,
                    "n_valid_sensors": n_valid,
                    "estimator": estimator,
                    "estimator_label": ESTIMATOR_LABELS[estimator],
                    "estimated_mean_ugm3": mean_value,
                    "estimated_sd_ugm3": sd_value,
                    "arithmetic_reference_mean_ugm3": reference_mean,
                    "arithmetic_reference_sd_ugm3": reference_sd,
                    "mean_relative_difference_pct": (
                        (mean_value - reference_mean) / reference_mean * 100.0
                        if reference_mean and np.isfinite(reference_mean) and np.isfinite(mean_value)
                        else np.nan
                    ),
                    "sd_relative_difference_pct": (
                        (sd_value - reference_sd) / reference_sd * 100.0
                        if reference_sd and np.isfinite(reference_sd) and np.isfinite(sd_value)
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def summarize_estimator_draws(
    estimates: np.ndarray,
    reference_mean: float,
    dataset_key: str,
    city: str,
    time_aggregation: str,
    time_index: str,
    sample_size: int,
    n_sensors_available: int,
    estimator: str,
    seed_used: int,
) -> dict[str, Any]:
    absolute_error = np.abs(estimates - reference_mean)
    ape = absolute_error / abs(reference_mean) * 100.0 if reference_mean else np.full_like(estimates, np.nan)
    bias = float(np.nanmean(estimates) - reference_mean)
    return {
        "dataset_key": dataset_key,
        "city": city,
        "time_aggregation": time_aggregation,
        "time_index": time_index,
        "sample_size": sample_size,
        "n_sensors_available": n_sensors_available,
        "estimator": estimator,
        "estimator_label": ESTIMATOR_LABELS[estimator],
        "draws": int(np.isfinite(estimates).sum()),
        "seed_used": seed_used,
        "reference_mean_ugm3": reference_mean,
        "estimator_mean_ugm3": float(np.nanmean(estimates)),
        "estimator_median_ugm3": float(np.nanmedian(estimates)),
        "bias_ugm3": bias,
        "relative_bias_pct": bias / reference_mean * 100.0 if reference_mean else np.nan,
        "median_absolute_error_ugm3": float(np.nanmedian(absolute_error)),
        "p75_absolute_error_ugm3": float(np.nanquantile(absolute_error, 0.75)),
        "p95_absolute_error_ugm3": float(np.nanquantile(absolute_error, 0.95)),
        "median_ape_pct": float(np.nanmedian(ape)),
        "p75_ape_pct": float(np.nanquantile(ape, 0.75)),
        "p95_ape_pct": float(np.nanquantile(ape, 0.95)),
    }


def mask_digest(indices: np.ndarray) -> str:
    payload = ",".join(str(int(index)) for index in indices)
    return __import__("hashlib").sha256(payload.encode("utf-8")).hexdigest()[:16]


def grouped_daily_indices(bundle: DatasetBundle, sample_size: int) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    valid_masks = np.isfinite(bundle.daily_values)
    for row_index, mask in enumerate(valid_masks):
        available = np.flatnonzero(mask)
        if len(available) < sample_size:
            continue
        digest = mask_digest(available)
        if digest not in groups:
            groups[digest] = {"available": available, "row_indices": []}
        groups[digest]["row_indices"].append(row_index)
    return groups


def run_monte_carlo_estimator_comparison(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []
    for sample_size in SAMPLE_SIZES:
        groups = grouped_daily_indices(bundle, sample_size)
        for digest, group in groups.items():
            available = group["available"]
            seed = derive_seed(MASTER_SEED, "estimator_comparison", bundle.spec.key, "daily", sample_size, digest)
            positions = draw_sample_positions(len(available), sample_size, DRAWS, seed)
            for row_index in group["row_indices"]:
                values = bundle.daily_values[row_index, available]
                reference_mean = float(np.nanmean(values))
                sample_values = values[positions]
                estimates_by_name = estimator_mean_values(sample_values)
                for estimator, estimates in estimates_by_name.items():
                    daily_rows.append(
                        summarize_estimator_draws(
                            estimates=estimates,
                            reference_mean=reference_mean,
                            dataset_key=bundle.spec.key,
                            city=bundle.spec.city,
                            time_aggregation="daily",
                            time_index=bundle.daily_dates[row_index],
                            sample_size=sample_size,
                            n_sensors_available=len(available),
                            estimator=estimator,
                            seed_used=seed,
                        )
                    )

        values = bundle.period_values[np.isfinite(bundle.period_values)]
        if len(values) >= sample_size:
            digest = mask_digest(np.arange(len(values)))
            seed = derive_seed(MASTER_SEED, "estimator_comparison", bundle.spec.key, "period", sample_size, digest)
            positions = draw_sample_positions(len(values), sample_size, DRAWS, seed)
            sample_values = values[positions]
            reference_mean = float(np.nanmean(values))
            estimates_by_name = estimator_mean_values(sample_values)
            for estimator, estimates in estimates_by_name.items():
                period_rows.append(
                    summarize_estimator_draws(
                        estimates=estimates,
                        reference_mean=reference_mean,
                        dataset_key=bundle.spec.key,
                        city=bundle.spec.city,
                        time_aggregation="period",
                        time_index="study_period",
                        sample_size=sample_size,
                        n_sensors_available=len(values),
                        estimator=estimator,
                        seed_used=seed,
                    )
                )
    return pd.DataFrame(daily_rows), pd.DataFrame(period_rows)


def summarize_daily_mc(daily_mc: pd.DataFrame) -> pd.DataFrame:
    return (
        daily_mc.groupby(["dataset_key", "city", "sample_size", "estimator", "estimator_label"], dropna=False)
        .agg(
            days_evaluated=("time_index", "nunique"),
            median_relative_bias_pct=("relative_bias_pct", "median"),
            mean_relative_bias_pct=("relative_bias_pct", "mean"),
            median_mdape_pct=("median_ape_pct", "median"),
            p75_mdape_pct=("median_ape_pct", lambda values: float(np.nanquantile(values, 0.75))),
            median_absolute_error_ugm3=("median_absolute_error_ugm3", "median"),
            p95_absolute_error_ugm3=("p95_absolute_error_ugm3", "median"),
        )
        .reset_index()
    )


def summarize_full_daily_estimators(daily_full: pd.DataFrame) -> pd.DataFrame:
    return (
        daily_full.groupby(["dataset_key", "city", "estimator", "estimator_label"], dropna=False)
        .agg(
            days_evaluated=("date", "nunique"),
            median_mean_relative_difference_pct=("mean_relative_difference_pct", "median"),
            mean_mean_relative_difference_pct=("mean_relative_difference_pct", "mean"),
            median_sd_relative_difference_pct=("sd_relative_difference_pct", "median"),
            mean_sd_relative_difference_pct=("sd_relative_difference_pct", "mean"),
            median_estimated_mean_ugm3=("estimated_mean_ugm3", "median"),
            median_estimated_sd_ugm3=("estimated_sd_ugm3", "median"),
        )
        .reset_index()
    )


def plot_daily_full_estimator_comparison(daily_full: pd.DataFrame) -> None:
    setup_matplotlib()
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(2, len(cities), figsize=(13.2, 6.9), constrained_layout=True, sharex="col")
    displayed_estimators = [
        "robust_arithmetic_median",
        "lognormal_mean",
        "robust_lognormal_median_mad",
    ]
    for column_index, city in enumerate(cities):
        city_frame = daily_full[daily_full["city"] == city].copy()
        city_frame["date"] = pd.to_datetime(city_frame["date"], errors="coerce")
        for estimator in displayed_estimators:
            group = city_frame[city_frame["estimator"] == estimator].sort_values("date")
            if group.empty:
                continue
            color = ESTIMATOR_COLORS[estimator]
            axes[0, column_index].plot(
                group["date"],
                group["mean_relative_difference_pct"],
                lw=1.05,
                alpha=0.88,
                color=color,
                label=ESTIMATOR_LABELS[estimator],
            )
            axes[1, column_index].plot(
                group["date"],
                group["sd_relative_difference_pct"],
                lw=1.05,
                alpha=0.88,
                color=color,
                label=ESTIMATOR_LABELS[estimator],
            )
        for axis in axes[:, column_index]:
            axis.axhline(0, color="#6b7280", lw=0.8, ls="--")
            axis.grid(True, color=GRID_COLOR, lw=0.5)
            axis.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        axes[0, column_index].set_title(city)
        axes[1, column_index].set_xlabel("Date")
    axes[0, 0].set_ylabel("Mean difference\nfrom arithmetic (%)")
    axes[1, 0].set_ylabel("SD difference\nfrom arithmetic (%)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.02))
    save_figure(fig, PLOT_DIR / "SI_F9_daily_estimator_mean_sd_comparison", dpi=OUTPUT_DPI)


def plot_lognormal_bias(daily_summary: pd.DataFrame, period_summary: pd.DataFrame) -> None:
    setup_matplotlib()
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(2, len(cities), figsize=(12.8, 6.3), sharex=True)
    targets = [
        (daily_summary, "median_relative_bias_pct", "Daily median bias"),
        (period_summary, "relative_bias_pct", "Study-period bias"),
    ]
    for row_index, (frame, y_column, row_title) in enumerate(targets):
        subset = frame[frame["estimator"].isin(["lognormal_mean", "robust_lognormal_median_mad"])].copy()
        finite_values = pd.to_numeric(subset[y_column], errors="coerce").dropna().to_numpy(dtype=float)
        if len(finite_values):
            row_min = min(float(finite_values.min()), 0.0)
            row_max = max(float(finite_values.max()), 0.0)
            pad = max((row_max - row_min) * 0.08, 0.5)
            row_ylim = (row_min - pad, row_max + pad)
        else:
            row_ylim = (-5.0, 5.0)
        for column_index, city in enumerate(cities):
            axis = axes[row_index, column_index]
            city_subset = subset[subset["city"] == city]
            for estimator in ["lognormal_mean", "robust_lognormal_median_mad"]:
                group = city_subset[city_subset["estimator"] == estimator].sort_values("sample_size")
                if group.empty:
                    continue
                dataset_key = str(group["dataset_key"].iloc[0])
                axis.plot(
                    group["sample_size"],
                    group[y_column],
                    marker="o",
                    markersize=4,
                    lw=1.7,
                    color=color_for_dataset(dataset_key),
                    linestyle="-" if estimator == "lognormal_mean" else "--",
                    label=ESTIMATOR_LABELS[estimator],
                )
            axis.axhline(0, color="#6b7280", lw=0.8)
            axis.grid(True, color=GRID_COLOR, lw=0.5)
            axis.set_ylim(*row_ylim)
            axis.set_xticks(SAMPLE_SIZES)
            axis.set_title(city if row_index == 0 else "")
            if column_index == 0:
                axis.set_ylabel(f"{row_title}\nrelative bias (%)")
            if row_index == 1:
                axis.set_xlabel("Number of sensors")
    legend_handles = [
        Line2D([0], [0], color="#111827", marker="o", markersize=4, lw=1.7, linestyle="-", label=ESTIMATOR_LABELS["lognormal_mean"]),
        Line2D(
            [0],
            [0],
            color="#111827",
            marker="o",
            markersize=4,
            lw=1.7,
            linestyle="--",
            label=ESTIMATOR_LABELS["robust_lognormal_median_mad"],
        ),
    ]
    fig.legend(
        legend_handles,
        [handle.get_label() for handle in legend_handles],
        loc="lower center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 0.02),
        handlelength=3.0,
    )
    fig.suptitle("Lognormal estimator relative bias by sample size", y=0.98)
    fig.tight_layout(rect=[0, 0.10, 1, 0.94])
    save_figure(fig, PLOT_DIR / "SI_F10_lognormal_relative_bias_by_n", dpi=OUTPUT_DPI)


def plot_estimator_mdape(daily_summary: pd.DataFrame) -> None:
    setup_matplotlib()
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(1, len(cities), figsize=(13, 4), constrained_layout=True, sharey=True)
    for axis, city in zip(axes, cities):
        subset = daily_summary[daily_summary["city"] == city].copy()
        for estimator in ESTIMATOR_LABELS:
            group = subset[subset["estimator"] == estimator].sort_values("sample_size")
            axis.plot(
                group["sample_size"],
                group["median_mdape_pct"],
                marker="o",
                lw=1.4,
                color=ESTIMATOR_COLORS[estimator],
                label=ESTIMATOR_LABELS[estimator],
            )
        axis.set_title(city)
        axis.set_xlabel("Number of sensors")
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("Median daily MdAPE (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False)
    fig.suptitle("Daily Monte Carlo estimator comparison")
    save_figure(fig, PLOT_DIR / "daily_monte_carlo_estimator_mdape_comparison", dpi=OUTPUT_DPI)


def write_markdown(
    full_summary: pd.DataFrame,
    daily_summary: pd.DataFrame,
    period_summary: pd.DataFrame,
    output_path: Path,
) -> None:
    def table(frame: pd.DataFrame, columns: list[str], max_rows: int = 24) -> str:
        subset = frame[columns].head(max_rows).copy()
        if subset.empty:
            return "_No rows._"
        for column in subset.columns:
            subset[column] = subset[column].map(lambda value: f"{value:.3f}" if isinstance(value, (float, np.floating)) else str(value))
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        rows = ["| " + " | ".join(row) + " |" for row in subset.astype(str).to_numpy()]
        return "\n".join([header, sep, *rows])

    key_daily = daily_summary[
        (daily_summary["sample_size"].isin([5, 10, 20]))
        & (daily_summary["estimator"].isin(["arithmetic_mean", "lognormal_mean", "robust_lognormal_median_mad"]))
    ].sort_values(["city", "sample_size", "estimator"])
    key_period = period_summary[
        (period_summary["sample_size"].isin([5, 10, 20]))
        & (period_summary["estimator"].isin(["arithmetic_mean", "lognormal_mean", "robust_lognormal_median_mad"]))
    ].sort_values(["city", "sample_size", "estimator"])
    lognormal_bias_range = (
        period_summary[period_summary["estimator"] == "lognormal_mean"]
        .groupby("city")["relative_bias_pct"]
        .agg(["min", "max"])
        .reset_index()
    )
    markdown = f"""# Estimator Comparison and Lognormal Bias

Generated by `analysis/scripts/build_estimator_comparison.py`.

## What Was Tested

- Full-network daily estimator comparison for mean and SD: arithmetic mean/SD, robust median/MAD, lognormal mean/SD, and robust lognormal median/MAD.
- Monte Carlo subnetwork estimator comparison at n = {", ".join(map(str, SAMPLE_SIZES))} with {DRAWS:,} draws.
- Lognormal and robust-lognormal relative bias versus the arithmetic reference-network mean.

## Period Lognormal Bias Range

{table(lognormal_bias_range, ["city", "min", "max"], max_rows=10)}

## Daily Monte Carlo Estimator Summary

{table(key_daily, ["city", "sample_size", "estimator_label", "median_relative_bias_pct", "median_mdape_pct", "median_absolute_error_ugm3"], max_rows=40)}

## Study-Period Monte Carlo Estimator Summary

{table(key_period, ["city", "sample_size", "estimator_label", "relative_bias_pct", "median_ape_pct", "median_absolute_error_ugm3"], max_rows=40)}

## Interpretation

- Arithmetic mean remains the estimand-aligned default because the reference mean is arithmetic.
- Lognormal estimators can change bias and interval behavior, but their usefulness depends on the cross-sectional distribution; this should be presented as sensitivity, not as a replacement estimand.
- Robust median-based estimators answer a different location question and can reduce sensitivity to outliers, but they no longer estimate the arithmetic reference-network mean directly.

## Output Inventory

- `daily_full_network_estimator_comparison.csv`
- `daily_full_network_estimator_summary.csv`
- `daily_monte_carlo_estimator_by_day.csv`
- `daily_monte_carlo_estimator_summary.csv`
- `period_monte_carlo_estimator_summary.csv`
- `SI_F9_daily_estimator_mean_sd_comparison.*`
- `SI_F10_lognormal_relative_bias_by_n.*`
- `daily_monte_carlo_estimator_mdape_comparison.*`
"""
    output_path.write_text(markdown)


def main() -> None:
    setup_matplotlib()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    bundles = {key: load_dataset(spec) for key, spec in DATASETS.items()}

    full_daily = pd.concat([build_daily_full_network_estimator_table(bundle) for bundle in bundles.values()], ignore_index=True)
    full_summary = summarize_full_daily_estimators(full_daily)
    daily_mc_frames: list[pd.DataFrame] = []
    period_mc_frames: list[pd.DataFrame] = []
    for bundle in bundles.values():
        daily_mc, period_mc = run_monte_carlo_estimator_comparison(bundle)
        daily_mc_frames.append(daily_mc)
        period_mc_frames.append(period_mc)
    daily_mc = pd.concat(daily_mc_frames, ignore_index=True)
    period_mc = pd.concat(period_mc_frames, ignore_index=True)
    daily_summary = summarize_daily_mc(daily_mc)

    full_daily.to_csv(OUTPUT_DIR / "daily_full_network_estimator_comparison.csv", index=False)
    full_summary.to_csv(OUTPUT_DIR / "daily_full_network_estimator_summary.csv", index=False)
    daily_mc.to_csv(OUTPUT_DIR / "daily_monte_carlo_estimator_by_day.csv", index=False)
    daily_summary.to_csv(OUTPUT_DIR / "daily_monte_carlo_estimator_summary.csv", index=False)
    period_mc.to_csv(OUTPUT_DIR / "period_monte_carlo_estimator_summary.csv", index=False)

    plot_daily_full_estimator_comparison(full_daily)
    plot_lognormal_bias(daily_summary, period_mc)
    plot_estimator_mdape(daily_summary)
    write_markdown(full_summary, daily_summary, period_mc, OUTPUT_DIR / "estimator_comparison.md")
    metadata = {
        "script": "analysis/scripts/build_estimator_comparison.py",
        "master_seed": MASTER_SEED,
        "draws": DRAWS,
        "sample_sizes": list(SAMPLE_SIZES),
        "estimators": ESTIMATOR_LABELS,
        "outputs": {
            "results_dir": str(OUTPUT_DIR.relative_to(REPO_ROOT)),
            "plots_dir": str(PLOT_DIR.relative_to(REPO_ROOT)),
        },
        "caveats": [
            "Robust median-based estimators are sensitivity estimators and do not target the arithmetic reference-network mean exactly.",
            "Lognormal estimators require positive sampled values; nonpositive values are treated as missing for the log-scale calculations.",
        ],
    }
    (OUTPUT_DIR / "estimator_comparison_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Wrote estimator comparison results to {OUTPUT_DIR}")
    print(f"Wrote estimator comparison plots to {PLOT_DIR}")


if __name__ == "__main__":
    main()
