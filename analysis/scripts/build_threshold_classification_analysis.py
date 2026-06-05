from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

for thread_var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(thread_var, "1")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_SRC_DIR = REPO_ROOT / "analysis" / "src"
if str(ANALYSIS_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_SRC_DIR))

from plot_style import GRID_COLOR, OUTPUT_DPI, save_figure, setup_matplotlib  # noqa: E402

BASELINE_RUN = (
    REPO_ROOT
    / "monte_carlo/results/runs/p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602"
)
PREPROCESSED_DIR = BASELINE_RUN / "preprocessed"
RESULTS_DIR = REPO_ROOT / "analysis/results/threshold_classification"
PLOTS_DIR = REPO_ROOT / "analysis/plots/threshold_classification"
DEFAULT_MASTER_SEED = 20260526
DEFAULT_DRAWS = 10_000


DATASETS = {
    "dhaka_lcs": {
        "city": "Dhaka",
        "label": "Dhaka LCS",
        "daily_path": PREPROCESSED_DIR / "dhaka_lcs_daily_sensor_means.parquet",
    },
    "lucknow_lcs": {
        "city": "Lucknow",
        "label": "Lucknow LCS",
        "daily_path": PREPROCESSED_DIR / "lucknow_lcs_daily_sensor_means.parquet",
    },
    "chicago_lcs_corrected_no_collocation": {
        "city": "Chicago",
        "label": "Chicago LCS",
        "daily_path": PREPROCESSED_DIR
        / "chicago_lcs_corrected_no_collocation_daily_sensor_means.parquet",
    },
}


DAILY_THRESHOLDS = [
    {
        "threshold_set": "daily_24h",
        "threshold_label": "WHO 24h AQG",
        "threshold_ugm3": 15.0,
        "source": "WHO 2021 PM2.5 24-hour AQG",
        "formal_compliance_caveat": "WHO short-term guideline is defined using a 99th percentile form; this analysis uses daily binary exceedance only as a decision-support sensitivity.",
    },
    {
        "threshold_set": "daily_24h",
        "threshold_label": "WHO 24h IT-4",
        "threshold_ugm3": 25.0,
        "source": "WHO 2021 PM2.5 24-hour interim target 4",
        "formal_compliance_caveat": "WHO short-term interim targets use a percentile form; this analysis uses daily binary exceedance only as a decision-support sensitivity.",
    },
    {
        "threshold_set": "daily_24h",
        "threshold_label": "EPA 24h NAAQS level",
        "threshold_ugm3": 35.0,
        "source": "US EPA PM2.5 24-hour NAAQS level",
        "formal_compliance_caveat": "US EPA 24-hour PM2.5 NAAQS is based on a 3-year 98th-percentile design value, not single-day binary classification.",
    },
    {
        "threshold_set": "daily_24h",
        "threshold_label": "WHO 24h IT-3",
        "threshold_ugm3": 37.5,
        "source": "WHO 2021 PM2.5 24-hour interim target 3",
        "formal_compliance_caveat": "WHO short-term interim targets use a percentile form; this analysis uses daily binary exceedance only as a decision-support sensitivity.",
    },
    {
        "threshold_set": "daily_24h",
        "threshold_label": "WHO 24h IT-2",
        "threshold_ugm3": 50.0,
        "source": "WHO 2021 PM2.5 24-hour interim target 2",
        "formal_compliance_caveat": "WHO short-term interim targets use a percentile form; this analysis uses daily binary exceedance only as a decision-support sensitivity.",
    },
    {
        "threshold_set": "daily_24h",
        "threshold_label": "WHO 24h IT-1",
        "threshold_ugm3": 75.0,
        "source": "WHO 2021 PM2.5 24-hour interim target 1",
        "formal_compliance_caveat": "WHO short-term interim targets use a percentile form; this analysis uses daily binary exceedance only as a decision-support sensitivity.",
    },
]


PERIOD_THRESHOLDS = [
    {
        "threshold_set": "period_mean",
        "threshold_label": "WHO annual AQG",
        "threshold_ugm3": 5.0,
        "source": "WHO 2021 PM2.5 annual AQG",
        "formal_compliance_caveat": "This uses the observed study-period network mean, not a formal population exposure or regulatory design value.",
    },
    {
        "threshold_set": "period_mean",
        "threshold_label": "EPA annual NAAQS level",
        "threshold_ugm3": 9.0,
        "source": "US EPA 2024 annual PM2.5 NAAQS level",
        "formal_compliance_caveat": "US EPA annual PM2.5 NAAQS is based on a 3-year annual-mean design value, not this study-period network mean.",
    },
    {
        "threshold_set": "period_mean",
        "threshold_label": "WHO annual IT-4",
        "threshold_ugm3": 10.0,
        "source": "WHO 2021 PM2.5 annual interim target 4",
        "formal_compliance_caveat": "This uses the observed study-period network mean, not a formal population exposure or regulatory design value.",
    },
    {
        "threshold_set": "period_mean",
        "threshold_label": "WHO annual IT-3",
        "threshold_ugm3": 15.0,
        "source": "WHO 2021 PM2.5 annual interim target 3",
        "formal_compliance_caveat": "This uses the observed study-period network mean, not a formal population exposure or regulatory design value.",
    },
    {
        "threshold_set": "period_mean",
        "threshold_label": "WHO annual IT-2",
        "threshold_ugm3": 25.0,
        "source": "WHO 2021 PM2.5 annual interim target 2",
        "formal_compliance_caveat": "This uses the observed study-period network mean, not a formal population exposure or regulatory design value.",
    },
    {
        "threshold_set": "period_mean",
        "threshold_label": "WHO annual IT-1",
        "threshold_ugm3": 35.0,
        "source": "WHO 2021 PM2.5 annual interim target 1",
        "formal_compliance_caveat": "This uses the observed study-period network mean, not a formal population exposure or regulatory design value.",
    },
]


@dataclass(frozen=True)
class Confusion:
    tp: np.ndarray
    fp: np.ndarray
    tn: np.ndarray
    fn: np.ndarray


def derive_seed(master_seed: int, *parts: object) -> int:
    payload = json.dumps(
        {"master_seed": master_seed, "parts": [str(part) for part in parts]},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") % (2**32)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def empty_confusion(max_n: int) -> Confusion:
    return Confusion(
        tp=np.zeros(max_n, dtype=np.int64),
        fp=np.zeros(max_n, dtype=np.int64),
        tn=np.zeros(max_n, dtype=np.int64),
        fn=np.zeros(max_n, dtype=np.int64),
    )


def add_confusion(confusion: Confusion, truth: bool, predicted_true_counts: np.ndarray, draws: int) -> None:
    n_count = predicted_true_counts.size
    if truth:
        confusion.tp[:n_count] += predicted_true_counts
        confusion.fn[:n_count] += draws - predicted_true_counts
    else:
        confusion.fp[:n_count] += predicted_true_counts
        confusion.tn[:n_count] += draws - predicted_true_counts


def confusion_to_records(
    confusion: Confusion,
    *,
    dataset_key: str,
    city: str,
    threshold: dict[str, Any],
    aggregation: str,
    days_evaluated: np.ndarray | None = None,
    near_margin_ugm3: float | None = None,
    reference_mean_ugm3: float | None = None,
    truth_exceeds: bool | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    total = confusion.tp + confusion.fp + confusion.tn + confusion.fn
    valid = total > 0
    for index in np.flatnonzero(valid):
        tp = int(confusion.tp[index])
        fp = int(confusion.fp[index])
        tn = int(confusion.tn[index])
        fn = int(confusion.fn[index])
        total_count = tp + fp + tn + fn
        sensitivity_den = tp + fn
        specificity_den = tn + fp
        precision_den = tp + fp
        npv_den = tn + fn
        sensitivity = tp / sensitivity_den if sensitivity_den else np.nan
        specificity = tn / specificity_den if specificity_den else np.nan
        precision = tp / precision_den if precision_den else np.nan
        npv = tn / npv_den if npv_den else np.nan
        f1_den = precision + sensitivity if np.isfinite(precision) and np.isfinite(sensitivity) else np.nan
        records.append(
            {
                "dataset_key": dataset_key,
                "city": city,
                "aggregation": aggregation,
                "threshold_set": threshold["threshold_set"],
                "threshold_label": threshold["threshold_label"],
                "threshold_ugm3": threshold["threshold_ugm3"],
                "n": index + 1,
                "near_margin_ugm3": near_margin_ugm3,
                "days_evaluated": int(days_evaluated[index]) if days_evaluated is not None else np.nan,
                "reference_mean_ugm3": reference_mean_ugm3,
                "truth_exceeds": truth_exceeds,
                "truth_prevalence": (tp + fn) / total_count if total_count else np.nan,
                "predicted_exceedance_fraction": (tp + fp) / total_count if total_count else np.nan,
                "accuracy": (tp + tn) / total_count if total_count else np.nan,
                "misclassification_rate": (fp + fn) / total_count if total_count else np.nan,
                "sensitivity": sensitivity,
                "specificity": specificity,
                "false_positive_rate": fp / specificity_den if specificity_den else np.nan,
                "false_negative_rate": fn / sensitivity_den if sensitivity_den else np.nan,
                "precision_ppv": precision,
                "negative_predictive_value": npv,
                "f1": (2 * precision * sensitivity / f1_den) if np.isfinite(f1_den) and f1_den else np.nan,
                "balanced_accuracy": np.nanmean([sensitivity, specificity]),
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
                "total_classifications": total_count,
            }
        )
    return records


def load_daily_matrix(path: Path) -> pd.DataFrame:
    daily = pd.read_parquet(path)
    if "date" not in daily.columns:
        raise ValueError(f"{path} must contain a date column")
    daily["date"] = daily["date"].astype(str)
    return daily


def analyze_dataset(
    dataset_key: str,
    spec: dict[str, Any],
    *,
    draws: int,
    master_seed: int,
    near_margins: tuple[float, ...],
) -> dict[str, Any]:
    daily = load_daily_matrix(spec["daily_path"])
    sensor_columns = [column for column in daily.columns if column != "date"]
    values = daily[sensor_columns].to_numpy(dtype=float)
    dates = daily["date"].tolist()
    max_n = len(sensor_columns)
    city = spec["city"]

    daily_confusions = {
        threshold["threshold_label"]: empty_confusion(max_n) for threshold in DAILY_THRESHOLDS
    }
    daily_near_confusions = {
        (threshold["threshold_label"], margin): empty_confusion(max_n)
        for threshold in DAILY_THRESHOLDS
        for margin in near_margins
    }
    daily_day_counts = {
        threshold["threshold_label"]: np.zeros(max_n, dtype=np.int64)
        for threshold in DAILY_THRESHOLDS
    }
    daily_near_day_counts = {
        (threshold["threshold_label"], margin): np.zeros(max_n, dtype=np.int64)
        for threshold in DAILY_THRESHOLDS
        for margin in near_margins
    }
    by_day_records: list[dict[str, Any]] = []

    for day_index, (date_value, row) in enumerate(zip(dates, values, strict=True)):
        valid_values = row[np.isfinite(row)]
        available = valid_values.size
        if available == 0:
            continue
        reference_mean = float(np.mean(valid_values))
        rng = np.random.default_rng(derive_seed(master_seed, dataset_key, "daily", date_value))
        order = np.argsort(rng.random((draws, available), dtype=np.float64), axis=1)
        selected_values = valid_values[order]
        subset_means = np.cumsum(selected_values, axis=1) / np.arange(1, available + 1)

        for threshold in DAILY_THRESHOLDS:
            threshold_value = float(threshold["threshold_ugm3"])
            truth = reference_mean > threshold_value
            predicted = subset_means > threshold_value
            predicted_true_counts = predicted.sum(axis=0).astype(np.int64)
            add_confusion(
                daily_confusions[threshold["threshold_label"]],
                truth,
                predicted_true_counts,
                draws,
            )
            daily_day_counts[threshold["threshold_label"]][:available] += 1

            misclassification = (~predicted if truth else predicted).mean(axis=0)
            for n_index in range(available):
                by_day_records.append(
                    {
                        "dataset_key": dataset_key,
                        "city": city,
                        "date": date_value,
                        "n_available": available,
                        "n": n_index + 1,
                        "threshold_label": threshold["threshold_label"],
                        "threshold_ugm3": threshold_value,
                        "reference_mean_ugm3": reference_mean,
                        "truth_exceeds": truth,
                        "predicted_exceedance_fraction": predicted_true_counts[n_index] / draws,
                        "misclassification_rate": misclassification[n_index],
                        "abs_distance_to_threshold_ugm3": abs(reference_mean - threshold_value),
                    }
                )

            for margin in near_margins:
                if abs(reference_mean - threshold_value) <= margin:
                    add_confusion(
                        daily_near_confusions[(threshold["threshold_label"], margin)],
                        truth,
                        predicted_true_counts,
                        draws,
                    )
                    daily_near_day_counts[(threshold["threshold_label"], margin)][:available] += 1

    daily_summary_records: list[dict[str, Any]] = []
    for threshold in DAILY_THRESHOLDS:
        daily_summary_records.extend(
            confusion_to_records(
                daily_confusions[threshold["threshold_label"]],
                dataset_key=dataset_key,
                city=city,
                threshold=threshold,
                aggregation="daily",
                days_evaluated=daily_day_counts[threshold["threshold_label"]],
            )
        )

    daily_near_records: list[dict[str, Any]] = []
    for threshold in DAILY_THRESHOLDS:
        for margin in near_margins:
            daily_near_records.extend(
                confusion_to_records(
                    daily_near_confusions[(threshold["threshold_label"], margin)],
                    dataset_key=dataset_key,
                    city=city,
                    threshold=threshold,
                    aggregation="daily_near_threshold",
                    days_evaluated=daily_near_day_counts[(threshold["threshold_label"], margin)],
                    near_margin_ugm3=margin,
                )
            )

    period_values = np.nanmean(values, axis=0)
    period_values = period_values[np.isfinite(period_values)]
    period_reference_mean = float(np.mean(period_values))
    rng = np.random.default_rng(derive_seed(master_seed, dataset_key, "period"))
    order = np.argsort(rng.random((draws, period_values.size), dtype=np.float64), axis=1)
    period_subset_means = np.cumsum(period_values[order], axis=1) / np.arange(1, period_values.size + 1)
    period_records: list[dict[str, Any]] = []
    for threshold in PERIOD_THRESHOLDS:
        truth = period_reference_mean > float(threshold["threshold_ugm3"])
        predicted = period_subset_means > float(threshold["threshold_ugm3"])
        predicted_true_counts = predicted.sum(axis=0).astype(np.int64)
        confusion = empty_confusion(period_values.size)
        add_confusion(confusion, truth, predicted_true_counts, draws)
        period_records.extend(
            confusion_to_records(
                confusion,
                dataset_key=dataset_key,
                city=city,
                threshold=threshold,
                aggregation="period",
                reference_mean_ugm3=period_reference_mean,
                truth_exceeds=truth,
            )
        )

    inventory = {
        "dataset_key": dataset_key,
        "city": city,
        "label": spec["label"],
        "source_path": str(spec["daily_path"].relative_to(REPO_ROOT)),
        "source_sha256": sha256_file(spec["daily_path"]),
        "n_sensors": len(sensor_columns),
        "n_days": len(dates),
        "period_reference_mean_ugm3": period_reference_mean,
        "first_date": min(dates),
        "last_date": max(dates),
        "draws": draws,
    }
    return {
        "inventory": inventory,
        "daily_summary": daily_summary_records,
        "daily_near_summary": daily_near_records,
        "daily_by_day": by_day_records,
        "period_summary": period_records,
    }


def plot_daily_summary(daily_summary: pd.DataFrame) -> None:
    setup_matplotlib()
    selected = daily_summary[
        daily_summary["threshold_label"].isin(
            ["WHO 24h AQG", "EPA 24h NAAQS level", "WHO 24h IT-1"]
        )
        & (daily_summary["n"] <= 30)
    ].copy()
    city_order = ["Dhaka", "Lucknow", "Chicago"]
    colors = {
        "WHO 24h AQG": "#1b9e77",
        "EPA 24h NAAQS level": "#d95f02",
        "WHO 24h IT-1": "#7570b3",
    }
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharex=True, sharey=True)
    for axis, city in zip(axes, city_order, strict=True):
        city_data = selected[selected["city"] == city]
        for label, group in city_data.groupby("threshold_label", sort=False):
            group = group.sort_values("n")
            axis.plot(
                group["n"],
                group["misclassification_rate"] * 100,
                label=label,
                color=colors.get(label),
                linewidth=2,
            )
        axis.set_title(city)
        axis.set_xlabel("Number of sensors, n")
        axis.grid(color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("Daily misclassification rate (%)")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle("Daily PM2.5 threshold-classification sensitivity", y=0.98)
    fig.tight_layout(rect=(0, 0.12, 1, 0.93))
    save_figure(fig, PLOTS_DIR / "daily_threshold_classification_misclassification", dpi=OUTPUT_DPI)


def plot_period_summary(period_summary: pd.DataFrame) -> None:
    setup_matplotlib()
    selected = period_summary[period_summary["n"] <= 30].copy()
    city_order = ["Dhaka", "Lucknow", "Chicago"]
    colors = {
        "WHO annual AQG": "#1b9e77",
        "EPA annual NAAQS level": "#d95f02",
        "WHO annual IT-4": "#7570b3",
        "WHO annual IT-3": "#e7298a",
        "WHO annual IT-2": "#66a61e",
        "WHO annual IT-1": "#e6ab02",
    }
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharex=True, sharey=True)
    for axis, city in zip(axes, city_order, strict=True):
        city_data = selected[selected["city"] == city]
        for label, group in city_data.groupby("threshold_label", sort=False):
            group = group.sort_values("n")
            axis.plot(
                group["n"],
                group["misclassification_rate"] * 100,
                label=label,
                color=colors.get(label),
                linewidth=1.8,
            )
        axis.set_title(city)
        axis.set_xlabel("Number of sensors, n")
        axis.grid(color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("Study-period misclassification rate (%)")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle("Study-period PM2.5 threshold-classification sensitivity", y=0.98)
    fig.tight_layout(rect=(0, 0.16, 1, 0.93))
    save_figure(fig, PLOTS_DIR / "period_threshold_classification_misclassification", dpi=OUTPUT_DPI)


def plot_near_threshold(daily_near: pd.DataFrame) -> None:
    setup_matplotlib()
    selected = daily_near[
        (daily_near["near_margin_ugm3"] == 2.0)
        & (daily_near["threshold_label"].isin(["WHO 24h AQG", "EPA 24h NAAQS level"]))
        & (daily_near["n"] <= 30)
    ].copy()
    if selected.empty:
        return
    city_order = ["Dhaka", "Lucknow", "Chicago"]
    colors = {
        "WHO 24h AQG": "#1b9e77",
        "EPA 24h NAAQS level": "#d95f02",
    }
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharex=True, sharey=True)
    for axis, city in zip(axes, city_order, strict=True):
        city_data = selected[selected["city"] == city]
        for label, group in city_data.groupby("threshold_label", sort=False):
            group = group.sort_values("n")
            axis.plot(
                group["n"],
                group["misclassification_rate"] * 100,
                label=label,
                color=colors.get(label),
                linewidth=2,
            )
        axis.set_title(city)
        axis.set_xlabel("Number of sensors, n")
        axis.grid(color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("Near-threshold misclassification rate (%)")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False)
    fig.suptitle("Daily classification only on days within ±2 µg/m³ of threshold", y=0.98)
    fig.tight_layout(rect=(0, 0.12, 1, 0.93))
    save_figure(fig, PLOTS_DIR / "daily_near_threshold_classification_misclassification_margin2", dpi=OUTPUT_DPI)


def write_markdown(
    inventory: pd.DataFrame,
    daily_summary: pd.DataFrame,
    daily_near: pd.DataFrame,
    period_summary: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    key_daily = daily_summary[
        daily_summary["threshold_label"].isin(["WHO 24h AQG", "EPA 24h NAAQS level"])
        & daily_summary["n"].isin([5, 10, 20])
    ].copy()
    key_period = period_summary[
        period_summary["threshold_label"].isin(["WHO annual AQG", "EPA annual NAAQS level"])
        & period_summary["n"].isin([5, 10, 20])
    ].copy()

    def table(df: pd.DataFrame, cols: list[str]) -> str:
        if df.empty:
            return "_No rows available._"
        view = df[cols].copy()
        for col in view.select_dtypes(include=[float]).columns:
            view[col] = view[col].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
        headers = list(view.columns)
        rows = [[str(value) for value in row] for row in view.to_numpy()]
        widths = [
            max(len(str(header)), *(len(row[index]) for row in rows))
            for index, header in enumerate(headers)
        ]
        header_line = "| " + " | ".join(
            str(header).ljust(widths[index]) for index, header in enumerate(headers)
        ) + " |"
        separator = "| " + " | ".join("-" * width for width in widths) + " |"
        body = [
            "| " + " | ".join(row[index].ljust(widths[index]) for index in range(len(headers))) + " |"
            for row in rows
        ]
        return "\n".join([header_line, separator, *body])

    daily_cols = [
        "city",
        "threshold_label",
        "threshold_ugm3",
        "n",
        "truth_prevalence",
        "misclassification_rate",
        "false_positive_rate",
        "false_negative_rate",
    ]
    period_cols = [
        "city",
        "threshold_label",
        "threshold_ugm3",
        "n",
        "reference_mean_ugm3",
        "truth_exceeds",
        "misclassification_rate",
        "false_positive_rate",
        "false_negative_rate",
    ]

    text = f"""# Threshold Classification Sensitivity

Generated: `{metadata['generated_at']}`

## Purpose

This analysis addresses reviewer-facing questions about whether subnetwork means preserve threshold/exceedance classifications. It is **not** a formal regulatory-compliance analysis. It is a decision-support sensitivity layered on top of the reference-network mean reproducibility estimand.

## Important Caveat

The EPA and WHO thresholds used here have formal averaging and design-value forms. This script asks a narrower finite-population question: if the deployed reference-network mean is treated as the classification reference, how often does an n-sensor random subnetwork produce the same side-of-threshold classification?

## Inputs

{table(inventory, ['dataset_key', 'city', 'n_sensors', 'n_days', 'period_reference_mean_ugm3', 'first_date', 'last_date'])}

## Daily Classification Snapshot

Rows below show selected daily thresholds and selected n values. Full data are in `daily_threshold_classification_summary.csv` and `daily_threshold_classification_by_day.csv`.

{table(key_daily, daily_cols)}

## Study-Period Classification Snapshot

Rows below show selected study-period thresholds and selected n values. Full data are in `period_threshold_classification_summary.csv`.

{table(key_period, period_cols)}

## Near-Threshold Sensitivity

`daily_near_threshold_classification_summary.csv` restricts the calculation to days where the reference-network mean is within ±1, ±2, or ±5 µg/m³ of a threshold. These rows are important because most classification disagreement happens near threshold boundaries.

## Outputs

- `classification_thresholds.csv`
- `dataset_inventory.csv`
- `daily_threshold_classification_summary.csv`
- `daily_threshold_classification_by_day.csv`
- `daily_near_threshold_classification_summary.csv`
- `period_threshold_classification_summary.csv`
- `threshold_classification_metadata.json`
- `analysis/plots/threshold_classification/daily_threshold_classification_misclassification.*`
- `analysis/plots/threshold_classification/period_threshold_classification_misclassification.*`
- `analysis/plots/threshold_classification/daily_near_threshold_classification_misclassification_margin2.*`

## Interpretation Rule

Use this analysis only if the manuscript keeps any health-guideline or threshold-classification claims. If the revised paper avoids those claims, this output is better kept as internal/SI evidence rather than a main-text result.
"""
    (RESULTS_DIR / "threshold_classification_analysis.md").write_text(text)


def build_metadata(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": "analysis/scripts/build_threshold_classification_analysis.py",
        "baseline_run": str(BASELINE_RUN.relative_to(REPO_ROOT)),
        "master_seed": args.master_seed,
        "draws": args.draws,
        "near_margins_ugm3": list(args.near_margins),
        "datasets": list(DATASETS),
        "threshold_source_urls": {
            "us_epa_pm_naaqs": "https://www.epa.gov/pm-pollution/national-ambient-air-quality-standards-naaqs-pm",
            "who_2021_aqg": "https://www.who.int/publications/i/item/9789240034228/",
            "who_threshold_table_reference": "https://www.ncbi.nlm.nih.gov/books/NBK574582/table/fm-ch1.tab1/",
        },
        "resource_policy": {
            "n_jobs": args.n_jobs,
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
            "blas_thread_env": {
                name: os.environ.get(name)
                for name in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                )
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PM2.5 threshold-classification Monte Carlo sensitivity for primary city networks."
    )
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--n-jobs", type=int, default=min(3, os.cpu_count() or 1))
    parser.add_argument("--near-margins", type=float, nargs="+", default=[1.0, 2.0, 5.0])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    worker_count = max(1, min(args.n_jobs, len(DATASETS), os.cpu_count() or 1))
    futures = []
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        for dataset_key, spec in DATASETS.items():
            futures.append(
                executor.submit(
                    analyze_dataset,
                    dataset_key,
                    spec,
                    draws=args.draws,
                    master_seed=args.master_seed,
                    near_margins=tuple(args.near_margins),
                )
            )
        outputs = [future.result() for future in as_completed(futures)]

    inventory = pd.DataFrame([output["inventory"] for output in outputs]).sort_values("city")
    daily_summary = pd.DataFrame(
        [record for output in outputs for record in output["daily_summary"]]
    ).sort_values(["city", "threshold_ugm3", "n"])
    daily_near = pd.DataFrame(
        [record for output in outputs for record in output["daily_near_summary"]]
    ).sort_values(["city", "threshold_ugm3", "near_margin_ugm3", "n"])
    daily_by_day = pd.DataFrame(
        [record for output in outputs for record in output["daily_by_day"]]
    ).sort_values(["city", "date", "threshold_ugm3", "n"])
    period_summary = pd.DataFrame(
        [record for output in outputs for record in output["period_summary"]]
    ).sort_values(["city", "threshold_ugm3", "n"])
    thresholds = pd.DataFrame(DAILY_THRESHOLDS + PERIOD_THRESHOLDS)

    inventory.to_csv(RESULTS_DIR / "dataset_inventory.csv", index=False)
    thresholds.to_csv(RESULTS_DIR / "classification_thresholds.csv", index=False)
    daily_summary.to_csv(RESULTS_DIR / "daily_threshold_classification_summary.csv", index=False)
    daily_near.to_csv(RESULTS_DIR / "daily_near_threshold_classification_summary.csv", index=False)
    daily_by_day.to_csv(RESULTS_DIR / "daily_threshold_classification_by_day.csv", index=False)
    period_summary.to_csv(RESULTS_DIR / "period_threshold_classification_summary.csv", index=False)

    metadata = build_metadata(args)
    metadata["inventory_rows"] = int(len(inventory))
    metadata["daily_summary_rows"] = int(len(daily_summary))
    metadata["daily_near_summary_rows"] = int(len(daily_near))
    metadata["daily_by_day_rows"] = int(len(daily_by_day))
    metadata["period_summary_rows"] = int(len(period_summary))
    (RESULTS_DIR / "threshold_classification_metadata.json").write_text(
        json.dumps(metadata, indent=2)
    )

    plot_daily_summary(daily_summary)
    plot_period_summary(period_summary)
    plot_near_threshold(daily_near)
    write_markdown(inventory, daily_summary, daily_near, period_summary, metadata)

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
