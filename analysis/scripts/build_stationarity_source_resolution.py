from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

from plot_style import GRID_COLOR, REFERENCE_LINE_COLOR, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402
from build_estimator_diagnostics import DATASETS, DatasetBundle, load_dataset  # noqa: E402


RESULTS_DIR = REPO_ROOT / "analysis/results/stationarity_source_resolution"
PLOTS_DIR = REPO_ROOT / "analysis/plots/stationarity_source_resolution"
BONFERRONI_ALPHA = 0.05


def markdown_table(frame: pd.DataFrame, float_digits: int = 3) -> str:
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


def lag1_correlation(values: np.ndarray) -> float:
    left = values[:-1]
    right = values[1:]
    mask = np.isfinite(left) & np.isfinite(right)
    if mask.sum() < 3:
        return np.nan
    left_valid = left[mask]
    right_valid = right[mask]
    if np.nanstd(left_valid) == 0 or np.nanstd(right_valid) == 0:
        return np.nan
    return float(np.corrcoef(left_valid, right_valid)[0, 1])


def ar1_effective_n(observed_n: int, rho: float) -> float:
    if observed_n <= 1:
        return float(observed_n)
    if not np.isfinite(rho):
        return float(observed_n)
    rho = min(max(rho, -0.95), 0.95)
    effective = observed_n * (1.0 - rho) / (1.0 + rho)
    return float(min(observed_n, max(2.0, effective)))


def max_consecutive_missing(values: np.ndarray) -> int:
    longest = 0
    current = 0
    for missing in ~np.isfinite(values):
        if missing:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def source_row_to_days(bundle: DatasetBundle, rows: int) -> float:
    if bundle.spec.source_frequency == "hourly":
        return rows / 24.0
    return float(rows)


def stationarity_rows(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame]:
    values = bundle.source_values.astype(float)
    period_means = np.nanmean(values, axis=0)
    reference_mean = float(np.nanmean(period_means))
    sensor_count = values.shape[1]
    z = NormalDist().inv_cdf(1.0 - BONFERRONI_ALPHA / (2.0 * sensor_count))

    rows: list[dict[str, Any]] = []
    for sensor_index, sensor_id in enumerate(bundle.sensor_ids):
        series = values[:, sensor_index]
        observed = series[np.isfinite(series)]
        observed_n = int(observed.size)
        sensor_mean = float(np.nanmean(series)) if observed_n else np.nan
        sensor_sd = float(np.nanstd(series, ddof=1)) if observed_n > 1 else np.nan
        rho = lag1_correlation(series)
        effective_n = ar1_effective_n(observed_n, rho)
        standard_error = sensor_sd / math.sqrt(effective_n) if np.isfinite(sensor_sd) and effective_n > 0 else np.nan
        ci_low = sensor_mean - z * standard_error if np.isfinite(standard_error) else np.nan
        ci_high = sensor_mean + z * standard_error if np.isfinite(standard_error) else np.nan
        excludes = bool(np.isfinite(ci_low) and np.isfinite(ci_high) and not (ci_low <= reference_mean <= ci_high))
        gap_rows = max_consecutive_missing(series)
        rows.append(
            {
                "dataset_key": bundle.spec.key,
                "city": bundle.spec.city,
                "network": bundle.spec.network,
                "sensor_id": sensor_id,
                "station_name": bundle.station_names[sensor_index],
                "source_frequency": bundle.spec.source_frequency,
                "observed_source_records": observed_n,
                "source_record_uptime_pct": 100.0 * observed_n / len(series) if len(series) else np.nan,
                "period_mean_pm25_ugm3": sensor_mean,
                "reference_mean_pm25_ugm3": reference_mean,
                "mean_minus_reference_ugm3": sensor_mean - reference_mean,
                "source_sd_pm25_ugm3": sensor_sd,
                "lag1_autocorrelation_source_resolution": rho,
                "ar1_effective_n_source_resolution": effective_n,
                "bonferroni_z": z,
                "ci_low_ugm3": ci_low,
                "ci_high_ugm3": ci_high,
                "ci_excludes_reference": excludes,
                "longest_missing_gap_source_rows": gap_rows,
                "longest_missing_gap_days": source_row_to_days(bundle, gap_rows),
                "long_gap_gt_30d": source_row_to_days(bundle, gap_rows) > 30,
            }
        )
    sensor_table = pd.DataFrame(rows).sort_values(["city", "period_mean_pm25_ugm3"])
    city_summary = (
        sensor_table.groupby(["dataset_key", "city", "network", "source_frequency"], as_index=False)
        .agg(
            sensors=("sensor_id", "count"),
            reference_mean_pm25_ugm3=("reference_mean_pm25_ugm3", "first"),
            sensors_ci_excludes_reference=("ci_excludes_reference", "sum"),
            sensors_long_gap_gt_30d=("long_gap_gt_30d", "sum"),
            median_source_record_uptime_pct=("source_record_uptime_pct", "median"),
            median_source_ar1_effective_n=("ar1_effective_n_source_resolution", "median"),
            median_source_lag1_autocorrelation=("lag1_autocorrelation_source_resolution", "median"),
            max_longest_gap_days=("longest_missing_gap_days", "max"),
        )
    )
    return sensor_table, city_summary


def plot_stationarity(sensor_table: pd.DataFrame) -> None:
    setup_matplotlib()
    cities = sensor_table["city"].drop_duplicates().tolist()
    fig, axes = plt.subplots(len(cities), 1, figsize=(10, 3.4 * len(cities)), sharex=False)
    if len(cities) == 1:
        axes = [axes]
    for ax, city in zip(axes, cities, strict=True):
        subset = sensor_table.loc[sensor_table["city"] == city].sort_values("period_mean_pm25_ugm3").reset_index(drop=True)
        x = np.arange(len(subset))
        color = color_for_dataset(str(subset["dataset_key"].iloc[0]))
        ax.vlines(x, subset["ci_low_ugm3"], subset["ci_high_ugm3"], color=color, alpha=0.35, linewidth=1.0)
        ax.scatter(
            x,
            subset["period_mean_pm25_ugm3"],
            color=np.where(subset["ci_excludes_reference"], "#dc2626", color),
            s=np.where(subset["long_gap_gt_30d"], 30, 16),
            alpha=0.9,
        )
        ax.axhline(float(subset["reference_mean_pm25_ugm3"].iloc[0]), color=REFERENCE_LINE_COLOR, linewidth=1.2)
        ax.set_title(f"{city}: source-resolution AR(1) stationarity screen")
        ax.set_ylabel("PM2.5 (µg/m³)")
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.text(
            0.01,
            0.94,
            f"CI excludes reference: {int(subset['ci_excludes_reference'].sum())}/{len(subset)}",
            transform=ax.transAxes,
            va="top",
            fontsize=8,
        )
    axes[-1].set_xlabel("Sensors sorted by period mean")
    save_figure(fig, PLOTS_DIR / "S24_source_resolution_stationarity_screen")


def write_markdown(sensor_table: pd.DataFrame, city_summary: pd.DataFrame) -> None:
    flagged = sensor_table.loc[
        sensor_table["ci_excludes_reference"] | sensor_table["long_gap_gt_30d"],
        [
            "city",
            "sensor_id",
            "station_name",
            "period_mean_pm25_ugm3",
            "reference_mean_pm25_ugm3",
            "mean_minus_reference_ugm3",
            "source_record_uptime_pct",
            "lag1_autocorrelation_source_resolution",
            "ar1_effective_n_source_resolution",
            "ci_excludes_reference",
            "longest_missing_gap_days",
            "long_gap_gt_30d",
        ],
    ].sort_values(["city", "ci_excludes_reference", "longest_missing_gap_days"], ascending=[True, False, False])
    lines = [
        "# Source-Resolution Stationarity Screen",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Purpose",
        "",
        "This diagnostic complements the existing SI-F11 daily AR(1) screen by estimating Bonferroni-adjusted per-sensor period-mean intervals at the source resolution of each canonical primary matrix: hourly for Dhaka/Lucknow and official daily for Chicago.",
        "",
        "## City Summary",
        "",
        markdown_table(city_summary),
        "",
        "## Flagged Or Long-Gap Sensors",
        "",
        markdown_table(flagged),
        "",
        "## Interpretation",
        "",
        "- This remains an approximation to full GLS-AR(1), but it uses the highest canonical resolution available for each primary dataset.",
        "- A CI excluding the deployed-network reference mean is a stationarity sensitivity flag, not automatic evidence of a faulty sensor.",
        "- Long gaps remain important because they can shift a sensor's period mean by removing seasonal or episodic high-pollution periods.",
        "- The manuscript should present this as a robustness/stationarity screen, not as proof that all sensors sample an identical underlying mean.",
        "",
    ]
    (RESULTS_DIR / "stationarity_source_resolution.md").write_text("\n".join(lines))


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    sensor_tables: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    metadata: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "bonferroni_alpha": BONFERRONI_ALPHA,
        "method": "source-resolution AR(1) effective-n Bonferroni normal CI",
        "datasets": {},
    }
    for spec in DATASETS.values():
        bundle = load_dataset(spec)
        sensor_table, city_summary = stationarity_rows(bundle)
        sensor_tables.append(sensor_table)
        summaries.append(city_summary)
        metadata["datasets"][spec.key] = {
            "city": spec.city,
            "source_frequency": spec.source_frequency,
            "pm_path": spec.pm_path,
            "location_path": spec.location_path,
            "input_hashes": bundle.input_hashes,
        }
    combined_sensor = pd.concat(sensor_tables, ignore_index=True)
    combined_summary = pd.concat(summaries, ignore_index=True)
    combined_sensor.to_csv(RESULTS_DIR / "stationarity_source_resolution_sensor_ci.csv", index=False)
    combined_summary.to_csv(RESULTS_DIR / "stationarity_source_resolution_city_summary.csv", index=False)
    (RESULTS_DIR / "stationarity_source_resolution_metadata.json").write_text(json.dumps(metadata, indent=2))
    plot_stationarity(combined_sensor)
    write_markdown(combined_sensor, combined_summary)
    print(f"Wrote source-resolution stationarity outputs to {RESULTS_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
