from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

from plot_style import GRID_COLOR, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402
from build_estimator_diagnostics import DATASETS, DatasetBundle, load_dataset  # noqa: E402


RESULTS_DIR = REPO_ROOT / "analysis/results/qaqc_low_tail"
PLOTS_DIR = REPO_ROOT / "analysis/plots/qaqc_low_tail"
RECOMMENDATIONS_DIR = REPO_ROOT / "analysis/results/recommendations"

LOW_THRESHOLDS = (1.0, 2.0, 5.0)
RELATIVE_RATIO_THRESHOLD = 0.20
REFERENCE_MEDIAN_MIN = 10.0
MIN_VALID_PEERS = 5


def finite_summary(values: np.ndarray) -> dict[str, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {
            "pm_min_ugm3": np.nan,
            "pm_p01_ugm3": np.nan,
            "pm_p05_ugm3": np.nan,
            "pm_median_ugm3": np.nan,
            "pm_p95_ugm3": np.nan,
            "pm_max_ugm3": np.nan,
        }
    return {
        "pm_min_ugm3": float(np.min(finite)),
        "pm_p01_ugm3": float(np.quantile(finite, 0.01)),
        "pm_p05_ugm3": float(np.quantile(finite, 0.05)),
        "pm_median_ugm3": float(np.median(finite)),
        "pm_p95_ugm3": float(np.quantile(finite, 0.95)),
        "pm_max_ugm3": float(np.max(finite)),
    }


def percent(numerator: float, denominator: float) -> float:
    if denominator <= 0 or not np.isfinite(denominator):
        return np.nan
    return float(100.0 * numerator / denominator)


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


def relative_low_mask(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid = np.isfinite(values)
    valid_count = valid.sum(axis=1)
    row_median = np.full(values.shape[0], np.nan, dtype=float)
    usable_rows = valid_count >= MIN_VALID_PEERS
    if usable_rows.any():
        row_median[usable_rows] = np.nanmedian(values[usable_rows], axis=1)
    evaluable_row = usable_rows & np.isfinite(row_median) & (row_median >= REFERENCE_MEDIAN_MIN)
    low = valid & evaluable_row[:, None] & (values < RELATIVE_RATIO_THRESHOLD * row_median[:, None])
    return low, row_median, evaluable_row


def sensor_low_tail_rows(bundle: DatasetBundle) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    values = bundle.source_values.astype(float)
    valid = np.isfinite(values)
    valid_counts = valid.sum(axis=0)
    relative_low, row_median, evaluable_rows = relative_low_mask(values)

    daily_values = bundle.daily_values.astype(float)
    daily_relative_low, daily_median, daily_evaluable = relative_low_mask(daily_values)

    rows: list[dict[str, Any]] = []
    for sensor_index, sensor_id in enumerate(bundle.sensor_ids):
        sensor_values = values[:, sensor_index]
        sensor_valid = valid[:, sensor_index]
        valid_n = int(valid_counts[sensor_index])
        row: dict[str, Any] = {
            "dataset_key": bundle.spec.key,
            "city": bundle.spec.city,
            "network": bundle.spec.network,
            "sensor_id": sensor_id,
            "station_name": bundle.station_names[sensor_index],
            "source_frequency": bundle.spec.source_frequency,
            "valid_observation_count": valid_n,
            "source_record_uptime_pct": percent(valid_n, len(sensor_values)),
            "relative_low_observation_count": int(relative_low[:, sensor_index].sum()),
            "relative_low_observation_pct_of_valid": percent(
                int(relative_low[:, sensor_index].sum()), valid_n
            ),
            "daily_relative_low_day_count": int(daily_relative_low[:, sensor_index].sum()),
            "daily_relative_low_day_pct_of_observed_days": percent(
                int(daily_relative_low[:, sensor_index].sum()),
                int(np.isfinite(daily_values[:, sensor_index]).sum()),
            ),
            "period_mean_pm25_ugm3": float(bundle.period_values[sensor_index]),
        }
        row.update(finite_summary(sensor_values))
        for threshold in LOW_THRESHOLDS:
            threshold_count = int(((sensor_values > 0.0) & (sensor_values < threshold)).sum())
            row[f"pm_gt0_lt{threshold:g}_count"] = threshold_count
            row[f"pm_gt0_lt{threshold:g}_pct_of_valid"] = percent(threshold_count, valid_n)
        rows.append(row)

    sensor_summary = pd.DataFrame(rows)
    sensor_summary["low_tail_review_flag"] = (
        (sensor_summary["relative_low_observation_pct_of_valid"] >= 1.0)
        | (sensor_summary["daily_relative_low_day_pct_of_observed_days"] >= 5.0)
        | (sensor_summary["pm_gt0_lt2_pct_of_valid"] >= 1.0)
    )
    sensor_summary["low_tail_rank_score"] = (
        sensor_summary["relative_low_observation_pct_of_valid"].fillna(0)
        + sensor_summary["daily_relative_low_day_pct_of_observed_days"].fillna(0)
        + sensor_summary["pm_gt0_lt2_pct_of_valid"].fillna(0)
    )

    city_row: dict[str, Any] = {
        "dataset_key": bundle.spec.key,
        "city": bundle.spec.city,
        "network": bundle.spec.network,
        "source_frequency": bundle.spec.source_frequency,
        "sensor_count": len(bundle.sensor_ids),
        "timestamp_count": len(bundle.source_timestamps),
        "valid_observation_count": int(valid.sum()),
        "missing_observation_count": int((~valid).sum()),
        "missing_observation_pct": percent(int((~valid).sum()), valid.size),
        "relative_low_evaluable_timestamp_count": int(evaluable_rows.sum()),
        "relative_low_observation_count": int(relative_low.sum()),
        "relative_low_observation_pct_of_valid": percent(int(relative_low.sum()), int(valid.sum())),
        "daily_relative_low_evaluable_day_count": int(daily_evaluable.sum()),
        "daily_relative_low_cell_count": int(daily_relative_low.sum()),
        "daily_relative_low_cell_pct_of_observed_daily_cells": percent(
            int(daily_relative_low.sum()), int(np.isfinite(daily_values).sum())
        ),
        "sensors_with_low_tail_review_flag": int(sensor_summary["low_tail_review_flag"].sum()),
    }
    city_row.update(finite_summary(values))
    for threshold in LOW_THRESHOLDS:
        threshold_count = int(((values > 0.0) & (values < threshold)).sum())
        city_row[f"pm_gt0_lt{threshold:g}_count"] = threshold_count
        city_row[f"pm_gt0_lt{threshold:g}_pct_of_valid"] = percent(threshold_count, int(valid.sum()))

    row_diagnostics = pd.DataFrame(
        {
            "dataset_key": bundle.spec.key,
            "city": bundle.spec.city,
            "timestamp": bundle.source_timestamps,
            "network_median_pm25_ugm3": row_median,
            "valid_sensor_count": valid.sum(axis=1),
            "relative_low_sensor_count": relative_low.sum(axis=1),
            "relative_low_sensor_fraction_pct": np.divide(
                100.0 * relative_low.sum(axis=1),
                valid.sum(axis=1),
                out=np.full(values.shape[0], np.nan, dtype=float),
                where=valid.sum(axis=1) > 0,
            ),
            "relative_low_screen_evaluable": evaluable_rows,
        }
    )

    return pd.DataFrame([city_row]), sensor_summary, row_diagnostics


def plot_city_low_tail(summary: pd.DataFrame) -> None:
    setup_matplotlib()
    metrics = [
        ("pm_gt0_lt2_pct_of_valid", "0 < PM2.5 < 2"),
        ("pm_gt0_lt5_pct_of_valid", "0 < PM2.5 < 5"),
        ("relative_low_observation_pct_of_valid", "<20% of same-time median"),
    ]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    x = np.arange(len(summary))
    width = 0.24
    for offset, (column, label) in zip([-width, 0, width], metrics, strict=True):
        ax.bar(
            x + offset,
            summary[column],
            width=width,
            label=label,
            color=[color_for_dataset(key) for key in summary["dataset_key"]],
            alpha=0.45 + 0.2 * (offset / width + 1),
            edgecolor="#111827",
            linewidth=0.5,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(summary["city"])
    ax.set_ylabel("Percent of valid observations")
    ax.set_title("Low-tail PM2.5 screen by city")
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    save_figure(fig, PLOTS_DIR / "S26_low_tail_screen_by_city")


def plot_top_flagged_sensors(sensor_summary: pd.DataFrame) -> None:
    setup_matplotlib()
    top = (
        sensor_summary.sort_values("low_tail_rank_score", ascending=False)
        .head(20)
        .sort_values("low_tail_rank_score")
    )
    if top.empty:
        return
    labels = top["city"] + " " + top["sensor_id"].astype(str)
    fig, ax = plt.subplots(figsize=(8.5, max(4.2, 0.24 * len(top))))
    ax.barh(
        np.arange(len(top)),
        top["low_tail_rank_score"],
        color=[color_for_dataset(key) for key in top["dataset_key"]],
        alpha=0.85,
    )
    ax.set_yticks(np.arange(len(top)))
    ax.set_yticklabels(labels)
    ax.set_xlabel("Composite low-tail flag score")
    ax.set_title("Sensors with strongest low-tail review signals")
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.7)
    save_figure(fig, PLOTS_DIR / "S26_top_low_tail_sensors")


def write_qaqc_markdown(summary: pd.DataFrame, sensor_summary: pd.DataFrame) -> None:
    top_flags = (
        sensor_summary.sort_values("low_tail_rank_score", ascending=False)
        .head(12)
        [
            [
                "city",
                "sensor_id",
                "station_name",
                "relative_low_observation_pct_of_valid",
                "daily_relative_low_day_pct_of_observed_days",
                "pm_gt0_lt2_pct_of_valid",
                "pm_min_ugm3",
                "source_record_uptime_pct",
                "low_tail_review_flag",
            ]
        ]
    )
    lines = [
        "# QA/QC Low-Tail Screen",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Purpose",
        "",
        "This diagnostic directly addresses whether implausibly low but nonzero PM2.5 values remain after inherited QA/QC. It is a screen, not a new filter.",
        "",
        "A value is flagged in two ways:",
        "",
        f"- Absolute low tail: valid PM2.5 greater than zero but below {', '.join(str(v) for v in LOW_THRESHOLDS)} µg/m³.",
        f"- Relative low tail: valid PM2.5 below {RELATIVE_RATIO_THRESHOLD:.0%} of the same-time network median when at least {MIN_VALID_PEERS} sensors are valid and the network median is at least {REFERENCE_MEDIAN_MIN:g} µg/m³.",
        "",
        "## City-Level Summary",
        "",
        markdown_table(summary),
        "",
        "## Top Sensor-Level Review Flags",
        "",
        markdown_table(top_flags),
        "",
        "## Interpretation",
        "",
        "- The screen should not be interpreted as evidence that all low values are bad data; low values may be real during cleaner periods.",
        "- The relative screen is more relevant for reviewer QA/QC concerns because it asks whether a sensor is unusually low when peers are not low.",
        "- These diagnostics support manuscript language that retained values passed inherited QA/QC and were additionally checked for low-tail anomalies, but they do not justify retroactive filtering unless a flagged sensor is independently confirmed faulty.",
        "- If a flagged sensor is excluded in a future sensitivity, the exclusion changes the finite population and should be reported as an estimand-change sensitivity.",
        "",
    ]
    (RESULTS_DIR / "qaqc_low_tail_review.md").write_text("\n".join(lines))


def write_qaqc_calibration_summary(summary: pd.DataFrame) -> None:
    lines = [
        "# QA/QC And Calibration Summary",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Analysis Position",
        "",
        "The analysis uses the cleaned/calibrated PM2.5 values supplied by the deployment data products. Our contribution is not to rederive calibration models; it is to evaluate how random subnetworks reproduce the deployed reference-network mean after the inherited QA/QC/calibration pipeline.",
        "",
        "## Retained Data Products",
        "",
        "- Dhaka and Lucknow use inherited calibrated low-cost-sensor PM2.5 matrices from the original manuscript data package.",
        "- Chicago uses corrected low-cost-sensor daily PM2.5 as the primary third-city analysis; raw Chicago LCS and AQS are retained as context/sensitivity, not as the primary finite population.",
        "- Negative, zero, and nonpositive values are absent in the canonical matrices used here.",
        "- The low-tail screen in `analysis/results/qaqc_low_tail/` checks for unusually low but positive values without applying additional filtering.",
        "- Calibration uncertainty can shift the pollution scale; the design-based subnetwork reproducibility result is conditional on the calibrated deployed network.",
        "",
        "## Current Canonical QA/QC Counts",
        "",
        markdown_table(summary[
            [
                "city",
                "source_frequency",
                "valid_observation_count",
                "missing_observation_pct",
                "pm_min_ugm3",
                "pm_p01_ugm3",
                "pm_gt0_lt2_pct_of_valid",
                "relative_low_observation_pct_of_valid",
                "sensors_with_low_tail_review_flag",
            ]
        ]),
        "",
        "## Remaining Limitation",
        "",
        "Full calibration-method details still depend on the deployment-team documentation and source publications. The manuscript should cite those sources and avoid implying that this revision independently validates instrument calibration.",
        "",
    ]
    (RESULTS_DIR / "qaqc_calibration_summary.md").write_text("\n".join(lines))


def write_recommendations() -> None:
    RECOMMENDATIONS_DIR.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "decision_context": "Primary claim",
            "recommendation": "Frame results as deployed reference-network mean reproducibility.",
            "rationale": "All Monte Carlo targets are arithmetic means of observed network sensors, not population- or area-weighted city means.",
            "manuscript_location": "Title/abstract/methods/discussion",
            "caveat": "Do not call this true city-wide exposure or regulatory compliance.",
        },
        {
            "decision_context": "Primary Chicago analysis",
            "recommendation": "Use Chicago corrected LCS with collocation sensors excluded.",
            "rationale": "Corrected LCS is the intended calibrated LCS product; collocation exclusion avoids overweighting one deployment site.",
            "manuscript_location": "Main Chicago methods and SI sensitivity",
            "caveat": "Raw LCS and AQS should remain context/sensitivity outputs.",
        },
        {
            "decision_context": "Missingness language",
            "recommendation": "Use weak/inconsistent evidence language rather than claiming MCAR or MAR.",
            "rationale": "Observed associations with PM2.5 and spatial variability are present but not strong enough for formal missing-at-random claims.",
            "manuscript_location": "SI missingness discussion",
            "caveat": "Filtering missing sensors can change the finite-population estimand.",
        },
        {
            "decision_context": "Completeness sensitivity",
            "recommendation": "Show threshold and data-driven filters as sensitivity analyses, not as new defaults.",
            "rationale": "Lucknow filters alter retained sensors and reference means most; Chicago filters barely alter conclusions.",
            "manuscript_location": "SI robustness",
            "caveat": "Report both improved completeness and reference-mean distortion.",
        },
        {
            "decision_context": "Estimator choice",
            "recommendation": "Keep arithmetic mean as primary and lognormal/robust estimators as sensitivity checks.",
            "rationale": "The arithmetic mean is aligned with the finite-population estimand; lognormal and robust median variants target related but not identical quantities.",
            "manuscript_location": "Methods and SI estimator section",
            "caveat": "Do not present lognormal improvement as assumption-free.",
        },
        {
            "decision_context": "Spatial placement",
            "recommendation": "Frame placement-design results as empirical design sensitivity.",
            "rationale": "Minimum predictive variance performs most consistently among deterministic designs, while max ESS is not reliably better.",
            "manuscript_location": "Discussion/SI placement",
            "caveat": "Spatial structure is not uniformly strong across cities/scales.",
        },
        {
            "decision_context": "Operations and maintenance",
            "recommendation": "Prioritize uptime monitoring, gap detection, and calibration checks before adding advanced estimators.",
            "rationale": "Long gaps and missingness filters change Lucknow more than estimator choice in several diagnostics.",
            "manuscript_location": "Practical recommendations",
            "caveat": "Maintenance guidance is conditional on the deployed-network support and instrument QA/QC.",
        },
    ]
    table = pd.DataFrame(rows)
    table.to_csv(RECOMMENDATIONS_DIR / "practical_recommendations.csv", index=False)
    lines = [
        "# Practical Recommendations",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        markdown_table(table),
        "",
        "## Discussion Guidance",
        "",
        "These results should be read as guidance on how many sensors are needed to reproduce a deployed reference-network mean under observed missingness and spatial support, not as a direct estimate of a population- or area-weighted city exposure. The operational interpretation is staged: maintain calibration and uptime first, report completeness and reference-mean sensitivity, then use the MdAPE and absolute-error curves to choose a subnetwork size matched to the temporal target. Chicago supports transferability to a lower-concentration setting as a nine-month corrected-LCS study-period analysis with regulatory monitors used as context.",
        "",
    ]
    (RECOMMENDATIONS_DIR / "practical_recommendations.md").write_text("\n".join(lines))


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    city_rows: list[pd.DataFrame] = []
    sensor_rows: list[pd.DataFrame] = []
    row_diagnostics: list[pd.DataFrame] = []
    metadata: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "thresholds_ugm3": LOW_THRESHOLDS,
        "relative_ratio_threshold": RELATIVE_RATIO_THRESHOLD,
        "relative_reference_median_min_ugm3": REFERENCE_MEDIAN_MIN,
        "min_valid_peers": MIN_VALID_PEERS,
        "datasets": {},
    }

    for spec in DATASETS.values():
        bundle = load_dataset(spec)
        city_summary, sensor_summary, diagnostics = sensor_low_tail_rows(bundle)
        city_rows.append(city_summary)
        sensor_rows.append(sensor_summary)
        row_diagnostics.append(diagnostics)
        metadata["datasets"][spec.key] = {
            "city": spec.city,
            "network": spec.network,
            "source_frequency": spec.source_frequency,
            "pm_path": spec.pm_path,
            "location_path": spec.location_path,
            "input_hashes": bundle.input_hashes,
            "preprocessing": bundle.preprocessing,
        }

    summary = pd.concat(city_rows, ignore_index=True)
    sensor_summary = pd.concat(sensor_rows, ignore_index=True).sort_values(
        ["low_tail_rank_score", "relative_low_observation_pct_of_valid"],
        ascending=False,
    )
    diagnostics = pd.concat(row_diagnostics, ignore_index=True)

    summary.to_csv(RESULTS_DIR / "low_tail_city_summary.csv", index=False)
    sensor_summary.to_csv(RESULTS_DIR / "low_tail_sensor_flags.csv", index=False)
    diagnostics.to_csv(RESULTS_DIR / "low_tail_timestamp_diagnostics.csv", index=False)
    (RESULTS_DIR / "qaqc_low_tail_metadata.json").write_text(json.dumps(metadata, indent=2))

    plot_city_low_tail(summary)
    plot_top_flagged_sensors(sensor_summary)
    write_qaqc_markdown(summary, sensor_summary)
    write_qaqc_calibration_summary(summary)
    write_recommendations()

    print(f"Wrote QA/QC low-tail outputs to {RESULTS_DIR.relative_to(REPO_ROOT)}")
    print(f"Wrote recommendations to {RECOMMENDATIONS_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
