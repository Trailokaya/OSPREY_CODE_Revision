from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_three_city_comparative_analysis import (  # noqa: E402
    PRIMARY_NETWORKS,
    REPO_ROOT,
    daily_sensor_availability,
    daily_sensor_means,
    read_locations,
    read_pm_matrix,
    retained_sensor_ids,
)


OUTPUT_DIR = REPO_ROOT / "analysis/results/three_city_comparative_analysis"
LUCKNOW_STRONG_REMOVE_COUNT = 15
LUCKNOW_SENSOR_COUNT = 71
PROPORTIONAL_REMOVE_FRACTION = LUCKNOW_STRONG_REMOVE_COUNT / LUCKNOW_SENSOR_COUNT
PROPORTIONAL_GAP_FRACTION = 90 / 365


@dataclass(frozen=True)
class NetworkData:
    dataset_key: str
    city: str
    sensor_ids: list[str]
    daily: pd.DataFrame
    availability: pd.DataFrame


@dataclass(frozen=True)
class CandidateRule:
    rule_name: str
    rule_family: str
    description: str
    kept_sensors: list[str]
    removed_sensors: list[str]


def pearson_r(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    x = frame["x"].to_numpy(dtype=float)
    y = frame["y"].to_numpy(dtype=float)
    x_centered = x - x.mean()
    y_centered = y - y.mean()
    denominator = float(np.sqrt(np.sum(x_centered**2) * np.sum(y_centered**2)))
    if denominator == 0:
        return float("nan")
    return float(np.sum(x_centered * y_centered) / denominator)


def spearman_rho(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    return pearson_r(frame["x"].rank(method="average"), frame["y"].rank(method="average"))


def max_consecutive_true(values: pd.Series) -> int:
    longest = 0
    current = 0
    for value in values.astype(bool):
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def prepare_networks() -> list[NetworkData]:
    networks = []
    for config in PRIMARY_NETWORKS:
        pm = read_pm_matrix(config.pm_path)
        _, locations = read_locations(config)
        sensor_ids = retained_sensor_ids(locations, pm)
        daily = daily_sensor_means(config, pm, sensor_ids)
        availability = daily_sensor_availability(config, pm, sensor_ids).reindex(daily.index)
        networks.append(
            NetworkData(
                dataset_key=config.dataset_key,
                city=config.city,
                sensor_ids=sensor_ids,
                daily=daily,
                availability=availability,
            )
        )
    return networks


def build_rules(network: NetworkData) -> list[CandidateRule]:
    sensor_ids = network.sensor_ids
    daily_presence = network.daily[sensor_ids].notna().mean(axis=0)
    daily_missing = 1 - daily_presence
    longest_gap = network.daily[sensor_ids].isna().apply(max_consecutive_true)
    proportional_remove_count = max(1, int(round(len(sensor_ids) * PROPORTIONAL_REMOVE_FRACTION)))
    proportional_gap_days = int(math.ceil(len(network.daily) * PROPORTIONAL_GAP_FRACTION))

    def rule_from_removed(
        rule_name: str,
        rule_family: str,
        description: str,
        removed: list[str],
    ) -> CandidateRule:
        removed_set = set(removed)
        return CandidateRule(
            rule_name=rule_name,
            rule_family=rule_family,
            description=description,
            kept_sensors=[sensor_id for sensor_id in sensor_ids if sensor_id not in removed_set],
            removed_sensors=[sensor_id for sensor_id in sensor_ids if sensor_id in removed_set],
        )

    rules = [
        CandidateRule(
            rule_name="baseline_all_sensors",
            rule_family="baseline",
            description="All retained sensors.",
            kept_sensors=list(sensor_ids),
            removed_sensors=[],
        )
    ]
    keep = set(daily_presence[daily_presence >= 0.50].index.astype(str)) & set(
        longest_gap[longest_gap <= proportional_gap_days].index.astype(str)
    )
    rules.append(
        rule_from_removed(
            "daily_ge_50pct_gap_le_25pct_period",
            "proportional_daily_gap",
            f"Keep daily presence >=50% and longest gap <= {proportional_gap_days} days.",
            [sensor_id for sensor_id in sensor_ids if sensor_id not in keep],
        )
    )
    keep = set(daily_presence[daily_presence >= 0.50].index.astype(str)) & set(
        longest_gap[longest_gap <= 90].index.astype(str)
    )
    rules.append(
        rule_from_removed(
            "daily_ge_50pct_gap_le_90d_absolute",
            "absolute_daily_gap",
            "Keep daily presence >=50% and longest gap <= 90 days.",
            [sensor_id for sensor_id in sensor_ids if sensor_id not in keep],
        )
    )
    ranked_daily_missing = daily_missing.sort_values(ascending=False).index.astype(str).tolist()
    rules.append(
        rule_from_removed(
            "remove_worst_daily_missing_21pct",
            "proportional_worst_daily_missing",
            f"Remove worst {proportional_remove_count} sensors by daily missingness.",
            ranked_daily_missing[:proportional_remove_count],
        )
    )
    absolute_remove_count = min(LUCKNOW_STRONG_REMOVE_COUNT, max(len(sensor_ids) - 1, 0))
    rules.append(
        rule_from_removed(
            "remove_worst_daily_missing_15_sensors",
            "absolute_worst_daily_missing",
            f"Remove worst {absolute_remove_count} sensors by daily missingness.",
            ranked_daily_missing[:absolute_remove_count],
        )
    )
    return rules


def summarize_rule(network: NetworkData, rule: CandidateRule, baseline: dict[str, pd.Series | float]) -> dict[str, Any]:
    kept = rule.kept_sensors
    filtered_daily = network.daily[kept]
    filtered_availability = network.availability[kept]
    reference_mean = filtered_daily.mean(axis=1, skipna=True)
    spatial_sd = filtered_daily.std(axis=1, skipna=True)
    spatial_cv = spatial_sd / reference_mean
    missing_fraction = 1 - filtered_availability.mean(axis=1, skipna=True)
    valid_sensor_count = filtered_daily.notna().sum(axis=1)
    time_index = baseline["time_index_days"]
    mean_difference = reference_mean - baseline["reference_mean"]
    absolute_difference = mean_difference.abs()
    missing_improvement = baseline["missing_fraction"] - missing_fraction
    return {
        "dataset_key": network.dataset_key,
        "city": network.city,
        "rule_name": rule.rule_name,
        "rule_family": rule.rule_family,
        "description": rule.description,
        "sensors_total": int(len(network.sensor_ids)),
        "sensors_retained": int(len(kept)),
        "sensors_removed": int(len(rule.removed_sensors)),
        "removed_sensor_ids": ";".join(rule.removed_sensors),
        "daily_missing_mean_pct": float(missing_fraction.mean() * 100),
        "daily_missing_median_pct": float(missing_fraction.median() * 100),
        "daily_missing_p90_pct": float(missing_fraction.quantile(0.90) * 100),
        "days_missing_ge_25pct": int((missing_fraction >= 0.25).sum()),
        "daily_valid_sensor_min": int(valid_sensor_count.min()),
        "daily_valid_sensor_median": float(valid_sensor_count.median()),
        "missing_mean_improvement_pct_points": float(missing_improvement.mean() * 100),
        "reference_mean_bias_ugm3": float(mean_difference.mean()),
        "reference_mean_mae_ugm3": float(absolute_difference.mean()),
        "reference_mean_p95_abs_diff_ugm3": float(absolute_difference.quantile(0.95)),
        "reference_mean_max_abs_diff_ugm3": float(absolute_difference.max()),
        "reference_mean_pearson_r": pearson_r(baseline["reference_mean"], reference_mean),
        "daily_mean_pm25_spearman_rho": spearman_rho(reference_mean, missing_fraction),
        "temporal_spearman_rho": spearman_rho(time_index, missing_fraction),
        "spatial_cv_spearman_rho": spearman_rho(spatial_cv, missing_fraction),
        "baseline_temporal_spearman_rho": baseline["temporal_rho"],
        "baseline_spatial_cv_spearman_rho": baseline["spatial_cv_rho"],
        "temporal_abs_reduction": abs(baseline["temporal_rho"]) - abs(spearman_rho(time_index, missing_fraction)),
        "spatial_cv_abs_reduction": abs(baseline["spatial_cv_rho"]) - abs(spearman_rho(spatial_cv, missing_fraction)),
        "joint_temporal_spatial_cv_reduction": (
            abs(baseline["temporal_rho"]) - abs(spearman_rho(time_index, missing_fraction))
        )
        + (abs(baseline["spatial_cv_rho"]) - abs(spearman_rho(spatial_cv, missing_fraction))),
    }


def build_baseline(network: NetworkData) -> dict[str, pd.Series | float]:
    reference_mean = network.daily[network.sensor_ids].mean(axis=1, skipna=True)
    spatial_cv = network.daily[network.sensor_ids].std(axis=1, skipna=True) / reference_mean
    missing_fraction = 1 - network.availability[network.sensor_ids].mean(axis=1, skipna=True)
    time_index = pd.Series(
        (pd.to_datetime(network.daily.index) - pd.to_datetime(network.daily.index).min()).days,
        index=network.daily.index,
    )
    return {
        "reference_mean": reference_mean,
        "missing_fraction": missing_fraction,
        "time_index_days": time_index,
        "temporal_rho": spearman_rho(time_index, missing_fraction),
        "spatial_cv_rho": spearman_rho(spatial_cv, missing_fraction),
    }


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    display = frame[columns].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def write_report(summary: pd.DataFrame) -> None:
    key_columns = [
        "city",
        "rule_name",
        "sensors_retained",
        "daily_missing_median_pct",
        "missing_mean_improvement_pct_points",
        "temporal_spearman_rho",
        "temporal_abs_reduction",
        "spatial_cv_spearman_rho",
        "spatial_cv_abs_reduction",
        "reference_mean_mae_ugm3",
    ]
    proportional_daily_gap = summary[
        summary["rule_name"].isin(["baseline_all_sensors", "daily_ge_50pct_gap_le_25pct_period"])
    ]
    proportional_remove = summary[
        summary["rule_name"].isin(["baseline_all_sensors", "remove_worst_daily_missing_21pct"])
    ]
    lines = [
        "# Three-City Proportional Missingness Rule Check",
        "",
        "## Scope",
        "",
        "This tests whether the Lucknow rules generalize proportionally to Dhaka and Chicago. Two proportional rules are emphasized: daily presence >=50% plus longest gap <=25% of the study period, and removing the worst 21.1% of sensors by daily missingness. Absolute Lucknow-style rules are included for context.",
        "",
        "## Proportional Daily-Presence Plus Gap Rule",
        "",
        markdown_table(proportional_daily_gap, key_columns),
        "",
        "## Proportional Worst-Daily-Missing Removal Rule",
        "",
        markdown_table(proportional_remove, key_columns),
        "",
        "## All Rules",
        "",
        markdown_table(summary, key_columns),
        "",
        "## Interpretation",
        "",
        "- A rule generalizes well if it reduces temporal/spatial-CV missingness dependence without large reference-mean distortion.",
        "- Dhaka and Chicago should not be expected to show the same gain as Lucknow if their baseline temporal/spatial-CV dependence is already weak.",
        "",
        "## Output Files",
        "",
        "- `three_city_proportional_missingness_rule_check.csv`",
        "- `three_city_proportional_missingness_rule_check.md`",
    ]
    (OUTPUT_DIR / "three_city_proportional_missingness_rule_check.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    rows = []
    for network in prepare_networks():
        baseline = build_baseline(network)
        for rule in build_rules(network):
            rows.append(summarize_rule(network, rule, baseline))
    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT_DIR / "three_city_proportional_missingness_rule_check.csv", index=False)
    metadata = {
        "purpose": "Check whether Lucknow-style missingness filters apply proportionally to Dhaka and Chicago.",
        "lucknow_strong_remove_count": LUCKNOW_STRONG_REMOVE_COUNT,
        "lucknow_sensor_count": LUCKNOW_SENSOR_COUNT,
        "proportional_remove_fraction": PROPORTIONAL_REMOVE_FRACTION,
        "proportional_gap_fraction": PROPORTIONAL_GAP_FRACTION,
        "outputs": [
            "three_city_proportional_missingness_rule_check.csv",
            "three_city_proportional_missingness_rule_check.md",
        ],
    }
    (OUTPUT_DIR / "three_city_proportional_missingness_rule_check_metadata.json").write_text(json.dumps(metadata, indent=2))
    write_report(summary)
    print(f"Wrote proportional missingness rule check to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        summary[
            summary["rule_name"].isin(
                [
                    "baseline_all_sensors",
                    "daily_ge_50pct_gap_le_25pct_period",
                    "remove_worst_daily_missing_21pct",
                ]
            )
        ][
            [
                "city",
                "rule_name",
                "sensors_retained",
                "daily_missing_median_pct",
                "temporal_spearman_rho",
                "spatial_cv_spearman_rho",
                "reference_mean_mae_ugm3",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
