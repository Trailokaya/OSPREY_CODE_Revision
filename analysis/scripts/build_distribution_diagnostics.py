from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from statistics import NormalDist
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import scipy
    from scipy import stats as scipy_stats

    SCIPY_AVAILABLE = True
    SCIPY_VERSION = getattr(scipy, "__version__", None)
except Exception:
    scipy_stats = None
    SCIPY_AVAILABLE = False
    SCIPY_VERSION = None

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

from build_estimator_diagnostics import DATASETS, DatasetBundle, load_dataset  # noqa: E402
from plot_style import GRID_COLOR, OUTPUT_DPI, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402


OUTPUT_DIR = REPO_ROOT / "analysis/results/distribution_diagnostics"
PLOT_DIR = REPO_ROOT / "analysis/plots/distribution_diagnostics"
P_BINS = (0.0, 0.001, 0.01, 0.05, 0.1, 1.0)
P_BIN_LABELS = ("<0.001", "0.001-0.01", "0.01-0.05", "0.05-0.1", ">=0.1")


def standardized(values: np.ndarray) -> np.ndarray:
    values = values[np.isfinite(values)].astype(float)
    if len(values) < 2:
        return np.array([], dtype=float)
    sd = float(np.std(values, ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return np.array([], dtype=float)
    return (values - float(np.mean(values))) / sd


def skewness(values: np.ndarray) -> float:
    z = standardized(values)
    if len(z) < 3:
        return np.nan
    return float(np.mean(z**3))


def excess_kurtosis(values: np.ndarray) -> float:
    z = standardized(values)
    if len(z) < 4:
        return np.nan
    return float(np.mean(z**4) - 3.0)


def jarque_bera(values: np.ndarray) -> tuple[float, float]:
    valid = values[np.isfinite(values)].astype(float)
    n = len(valid)
    if n < 5:
        return np.nan, np.nan
    s = skewness(valid)
    k = excess_kurtosis(valid)
    if not np.isfinite(s) or not np.isfinite(k):
        return np.nan, np.nan
    statistic = n / 6.0 * (s**2 + (k**2) / 4.0)
    p_value = math.exp(-statistic / 2.0)  # chi-square survival for df=2
    return float(statistic), float(p_value)


def qq_correlation(values: np.ndarray) -> float:
    valid = np.sort(standardized(values))
    n = len(valid)
    if n < 5:
        return np.nan
    probabilities = (np.arange(1, n + 1) - 0.5) / n
    normal = NormalDist()
    theoretical = np.array([normal.inv_cdf(float(probability)) for probability in probabilities])
    if np.std(valid) == 0 or np.std(theoretical) == 0:
        return np.nan
    return float(np.corrcoef(valid, theoretical)[0, 1])


def shapiro_wilk(values: np.ndarray) -> tuple[float, float]:
    valid = values[np.isfinite(values)].astype(float)
    if not SCIPY_AVAILABLE or len(valid) < 3:
        return np.nan, np.nan
    statistic, p_value = scipy_stats.shapiro(valid)
    return float(statistic), float(p_value)


def diagnostics_for_values(values: np.ndarray) -> dict[str, float]:
    valid = values[np.isfinite(values)].astype(float)
    positive = valid[valid > 0]
    jb_stat, jb_p = jarque_bera(valid)
    log_jb_stat, log_jb_p = jarque_bera(np.log(positive)) if len(positive) == len(valid) else (np.nan, np.nan)
    shapiro_stat, shapiro_p = shapiro_wilk(valid)
    log_shapiro_stat, log_shapiro_p = (
        shapiro_wilk(np.log(positive)) if len(positive) == len(valid) else (np.nan, np.nan)
    )
    return {
        "n_valid_sensors": int(len(valid)),
        "mean_ugm3": float(np.mean(valid)) if len(valid) else np.nan,
        "median_ugm3": float(np.median(valid)) if len(valid) else np.nan,
        "sd_ugm3": float(np.std(valid, ddof=1)) if len(valid) > 1 else np.nan,
        "skewness_original": skewness(valid),
        "excess_kurtosis_original": excess_kurtosis(valid),
        "jarque_bera_original": jb_stat,
        "jarque_bera_original_p": jb_p,
        "shapiro_wilk_original": shapiro_stat,
        "shapiro_wilk_original_p": shapiro_p,
        "qq_correlation_original": qq_correlation(valid),
        "skewness_log": skewness(np.log(positive)) if len(positive) == len(valid) else np.nan,
        "excess_kurtosis_log": excess_kurtosis(np.log(positive)) if len(positive) == len(valid) else np.nan,
        "jarque_bera_log": log_jb_stat,
        "jarque_bera_log_p": log_jb_p,
        "shapiro_wilk_log": log_shapiro_stat,
        "shapiro_wilk_log_p": log_shapiro_p,
        "qq_correlation_log": qq_correlation(np.log(positive)) if len(positive) == len(valid) else np.nan,
    }


def build_daily_distribution_diagnostics(bundle: DatasetBundle) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row_index, date in enumerate(bundle.daily_dates):
        values = bundle.daily_values[row_index, :]
        row = {
            "dataset_key": bundle.spec.key,
            "city": bundle.spec.city,
            "date": date,
            **diagnostics_for_values(values),
        }
        original_p = row["jarque_bera_original_p"]
        log_p = row["jarque_bera_log_p"]
        if np.isfinite(original_p) and np.isfinite(log_p):
            row["preferred_scale_by_jb_p"] = "log" if log_p > original_p else "original"
        else:
            row["preferred_scale_by_jb_p"] = "undetermined"
        original_shapiro_p = row["shapiro_wilk_original_p"]
        log_shapiro_p = row["shapiro_wilk_log_p"]
        if np.isfinite(original_shapiro_p) and np.isfinite(log_shapiro_p):
            row["preferred_scale_by_shapiro_p"] = "log" if log_shapiro_p > original_shapiro_p else "original"
        else:
            row["preferred_scale_by_shapiro_p"] = "undetermined"
        rows.append(row)
    return pd.DataFrame(rows)


def p_bin(value: float) -> str:
    if not np.isfinite(value):
        return "missing"
    for left, right, label in zip(P_BINS[:-1], P_BINS[1:], P_BIN_LABELS):
        if left <= value < right or (label == ">=0.1" and value <= right):
            return label
    return "missing"


def build_summary(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = (
        daily.groupby(["dataset_key", "city"], dropna=False)
        .agg(
            days_evaluated=("date", "nunique"),
            median_n_valid_sensors=("n_valid_sensors", "median"),
            median_skewness_original=("skewness_original", "median"),
            median_skewness_log=("skewness_log", "median"),
            median_excess_kurtosis_original=("excess_kurtosis_original", "median"),
            median_excess_kurtosis_log=("excess_kurtosis_log", "median"),
            median_jb_original_p=("jarque_bera_original_p", "median"),
            median_jb_log_p=("jarque_bera_log_p", "median"),
            median_shapiro_original_p=("shapiro_wilk_original_p", "median"),
            median_shapiro_log_p=("shapiro_wilk_log_p", "median"),
            days_jb_original_p_ge_0p1=("jarque_bera_original_p", lambda values: int(np.sum(np.asarray(values) >= 0.1))),
            days_jb_log_p_ge_0p1=("jarque_bera_log_p", lambda values: int(np.sum(np.asarray(values) >= 0.1))),
            days_shapiro_original_p_ge_0p1=("shapiro_wilk_original_p", lambda values: int(np.sum(np.asarray(values) >= 0.1))),
            days_shapiro_log_p_ge_0p1=("shapiro_wilk_log_p", lambda values: int(np.sum(np.asarray(values) >= 0.1))),
            fraction_days_log_preferred=("preferred_scale_by_jb_p", lambda values: float(np.mean(np.asarray(values) == "log"))),
            fraction_days_log_preferred_by_shapiro=("preferred_scale_by_shapiro_p", lambda values: float(np.mean(np.asarray(values) == "log"))),
            median_qq_correlation_original=("qq_correlation_original", "median"),
            median_qq_correlation_log=("qq_correlation_log", "median"),
        )
        .reset_index()
    )

    bin_rows: list[dict[str, Any]] = []
    for (dataset_key, city), group in daily.groupby(["dataset_key", "city"], sort=True):
        for scale, column in [("original", "jarque_bera_original_p"), ("log", "jarque_bera_log_p")]:
            counts = group[column].map(p_bin).value_counts()
            for label in [*P_BIN_LABELS, "missing"]:
                bin_rows.append(
                    {
                        "dataset_key": dataset_key,
                        "city": city,
                        "scale": scale,
                        "p_bin": label,
                        "day_count": int(counts.get(label, 0)),
                    }
                )
    return summary, pd.DataFrame(bin_rows)


def plot_pvalue_histograms(
    daily: pd.DataFrame,
    test_name: str,
    original_column: str,
    log_column: str,
    output_name: str,
) -> None:
    setup_matplotlib()
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(len(cities), 2, figsize=(10, 8), constrained_layout=True, sharex=True, sharey=True)
    for row_index, city in enumerate(cities):
        city_frame = daily[daily["city"] == city]
        for col_index, (scale, column) in enumerate([("Original", original_column), ("Log", log_column)]):
            axis = axes[row_index, col_index]
            values = city_frame[column].replace([np.inf, -np.inf], np.nan).dropna()
            axis.hist(values, bins=np.linspace(0, 1, 31), color=color_for_dataset(str(city_frame["dataset_key"].iloc[0])), alpha=0.75)
            axis.axvline(0.1, color="#dc2626", lw=1.0, ls="--")
            axis.grid(True, color=GRID_COLOR, lw=0.5)
            if row_index == 0:
                axis.set_title(f"{scale} scale")
            if col_index == 0:
                axis.set_ylabel(city)
            if row_index == len(cities) - 1:
                axis.set_xlabel(f"{test_name} p-value")
    fig.suptitle(f"{test_name} normality screen by day")
    save_figure(fig, PLOT_DIR / output_name, dpi=OUTPUT_DPI)


def plot_skewness_comparison(daily: pd.DataFrame) -> None:
    setup_matplotlib()
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True, sharey=True)
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"]):
        city_frame = daily[daily["city"] == city]
        axis.scatter(
            city_frame["skewness_original"],
            city_frame["skewness_log"],
            s=14,
            alpha=0.55,
            color=color_for_dataset(str(city_frame["dataset_key"].iloc[0])),
            edgecolor="none",
        )
        lim = np.nanmax(np.abs(city_frame[["skewness_original", "skewness_log"]].to_numpy(dtype=float)))
        lim = max(1.0, min(float(lim), 6.0))
        axis.plot([-lim, lim], [-lim, lim], color="#6b7280", lw=0.8, ls="--")
        axis.axhline(0, color=GRID_COLOR, lw=0.6)
        axis.axvline(0, color=GRID_COLOR, lw=0.6)
        axis.set_xlim(-lim, lim)
        axis.set_ylim(-lim, lim)
        axis.set_title(city)
        axis.set_xlabel("Original-scale skewness")
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    axes[0].set_ylabel("Log-scale skewness")
    fig.suptitle("Does log transform reduce daily cross-sectional skewness?")
    save_figure(fig, PLOT_DIR / "distribution_skewness_original_vs_log", dpi=OUTPUT_DPI)


def representative_day(bundle: DatasetBundle) -> int:
    n_valid = np.isfinite(bundle.daily_values).sum(axis=1)
    means = np.divide(
        np.nansum(bundle.daily_values, axis=1),
        n_valid,
        out=np.full(len(n_valid), np.nan, dtype=float),
        where=n_valid > 0,
    )
    valid = np.flatnonzero((n_valid >= max(10, np.nanmedian(n_valid))) & np.isfinite(means))
    if len(valid) == 0:
        return int(np.nanargmax(n_valid))
    median_mean = float(np.nanmedian(means[valid]))
    return int(valid[np.argmin(np.abs(means[valid] - median_mean))])


def plot_representative_distributions(bundles: dict[str, DatasetBundle]) -> None:
    setup_matplotlib()
    fig, axes = plt.subplots(3, 2, figsize=(10, 8), constrained_layout=True)
    for row_index, key in enumerate(["dhaka_lcs", "lucknow_lcs", "chicago_lcs_corrected_no_collocation"]):
        bundle = bundles[key]
        row = representative_day(bundle)
        values = bundle.daily_values[row, :]
        values = values[np.isfinite(values)]
        positive = values[values > 0]
        color = color_for_dataset(key)
        axes[row_index, 0].hist(values, bins=18, color=color, alpha=0.75)
        axes[row_index, 1].hist(np.log(positive), bins=18, color=color, alpha=0.75)
        axes[row_index, 0].set_ylabel(f"{bundle.spec.city}\n{bundle.daily_dates[row]}")
        for axis in axes[row_index, :]:
            axis.grid(True, color=GRID_COLOR, lw=0.5)
        axes[row_index, 0].set_xlabel("PM2.5 (µg/m³)")
        axes[row_index, 1].set_xlabel("log(PM2.5)")
    axes[0, 0].set_title("Original scale")
    axes[0, 1].set_title("Log scale")
    fig.suptitle("Representative daily cross-sectional distributions")
    save_figure(fig, PLOT_DIR / "distribution_representative_daily_histograms", dpi=OUTPUT_DPI)


def write_markdown(summary: pd.DataFrame, bin_counts: pd.DataFrame, output_path: Path) -> None:
    def table(frame: pd.DataFrame, columns: list[str], max_rows: int = 30) -> str:
        subset = frame[columns].head(max_rows).copy()
        if subset.empty:
            return "_No rows._"
        for column in subset.columns:
            subset[column] = subset[column].map(lambda value: f"{value:.3f}" if isinstance(value, (float, np.floating)) else str(value))
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        rows = ["| " + " | ".join(row) + " |" for row in subset.astype(str).to_numpy()]
        return "\n".join([header, sep, *rows])

    ge_0p1 = bin_counts[bin_counts["p_bin"] == ">=0.1"].pivot_table(
        index=["city"], columns="scale", values="day_count", aggfunc="sum"
    ).reset_index()
    shapiro_section = ""
    if SCIPY_AVAILABLE:
        shapiro_section = f"""
## Days With Exact Shapiro-Wilk p ≥ 0.1

{table(summary, ["city", "days_shapiro_original_p_ge_0p1", "days_shapiro_log_p_ge_0p1", "median_shapiro_original_p", "median_shapiro_log_p", "fraction_days_log_preferred_by_shapiro"], max_rows=10)}
"""
    else:
        shapiro_section = """
## Exact Shapiro-Wilk

Exact Shapiro-Wilk p-values were not computed because SciPy was unavailable in this environment.
"""

    markdown = f"""# Distribution Diagnostics

Generated by `analysis/scripts/build_distribution_diagnostics.py`.

## Important Caveat

This run uses exact SciPy Shapiro-Wilk p-values when SciPy is available, alongside a dependency-free distribution screen using:

- daily cross-sectional skewness;
- daily cross-sectional excess kurtosis;
- Jarque–Bera p-values, with chi-square df=2 survival calculated analytically;
- Q-Q correlation against normal quantiles;
- original-scale and log-scale distribution plots.

## Summary

{table(summary, ["city", "days_evaluated", "median_n_valid_sensors", "median_skewness_original", "median_skewness_log", "median_jb_original_p", "median_jb_log_p", "days_jb_original_p_ge_0p1", "days_jb_log_p_ge_0p1", "days_shapiro_original_p_ge_0p1", "days_shapiro_log_p_ge_0p1", "fraction_days_log_preferred"])}

## Days With Jarque–Bera p ≥ 0.1

{table(ge_0p1, ["city", "log", "original"], max_rows=10)}

{shapiro_section}

## Interpretation

- The log transform is useful when it reduces skewness or increases the normality-screen p-value, but it does not universally make daily cross-sections normal.
- Chicago should be treated separately in interpretation because it has many more sensors and lower PM2.5 levels than Dhaka/Lucknow.
- These results support presenting lognormal methods as sensitivity checks, not as a universally valid parametric assumption.

## Output Inventory

- `distribution_daily_diagnostics.csv`
- `distribution_normality_screen_summary.csv`
- `distribution_pvalue_bin_counts.csv`
- `distribution_jb_pvalue_histograms.*`
- `distribution_shapiro_pvalue_histograms.*` when SciPy is available
- `distribution_skewness_original_vs_log.*`
- `distribution_representative_daily_histograms.*`
"""
    output_path.write_text(markdown)


def main() -> None:
    setup_matplotlib()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    bundles = {key: load_dataset(spec) for key, spec in DATASETS.items()}
    daily = pd.concat([build_daily_distribution_diagnostics(bundle) for bundle in bundles.values()], ignore_index=True)
    summary, bin_counts = build_summary(daily)
    daily.to_csv(OUTPUT_DIR / "distribution_daily_diagnostics.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "distribution_normality_screen_summary.csv", index=False)
    bin_counts.to_csv(OUTPUT_DIR / "distribution_pvalue_bin_counts.csv", index=False)
    plot_pvalue_histograms(
        daily,
        "Jarque-Bera",
        "jarque_bera_original_p",
        "jarque_bera_log_p",
        "distribution_jb_pvalue_histograms",
    )
    if SCIPY_AVAILABLE:
        plot_pvalue_histograms(
            daily,
            "Shapiro-Wilk",
            "shapiro_wilk_original_p",
            "shapiro_wilk_log_p",
            "distribution_shapiro_pvalue_histograms",
        )
    plot_skewness_comparison(daily)
    plot_representative_distributions(bundles)
    write_markdown(summary, bin_counts, OUTPUT_DIR / "distribution_diagnostics.md")
    metadata = {
        "script": "analysis/scripts/build_distribution_diagnostics.py",
        "uses_scipy": SCIPY_AVAILABLE,
        "scipy_version": SCIPY_VERSION,
        "normality_screen": "Exact Shapiro-Wilk when SciPy is available; Jarque-Bera with analytical chi-square df=2 survival p-value always included",
        "outputs": {
            "results_dir": str(OUTPUT_DIR.relative_to(REPO_ROOT)),
            "plots_dir": str(PLOT_DIR.relative_to(REPO_ROOT)),
        },
    }
    (OUTPUT_DIR / "distribution_diagnostics_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Wrote distribution diagnostics to {OUTPUT_DIR}")
    print(f"Wrote distribution plots to {PLOT_DIR}")


if __name__ == "__main__":
    main()
