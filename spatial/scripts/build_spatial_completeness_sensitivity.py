from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
for path in [SCRIPT_DIR, REPO_ROOT / "analysis" / "scripts"]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_spatial_distance_correlation_analysis import (  # noqa: E402
    CITY_COLORS,
    DATA_ROOT,
    GRID_COLOR,
    OUTPUT_DPI,
    RESOLUTION_LABELS,
    NETWORKS,
    PreparedNetwork,
    aggregate_values,
    markdown_table,
    prepare_network,
    save_figure,
    setup_matplotlib,
)
from build_spatial_distance_correlation_summary import (  # noqa: E402
    ALPHA,
    SUMMARY_SEED,
    N_PERMUTATIONS,
    build_weight_schemes,
    distance_matrix_km,
    permutation_morans_summary,
)


OUTPUT_DIR = REPO_ROOT / "spatial/results/completeness_sensitivity"
PLOT_DIR = REPO_ROOT / "spatial/plots/completeness_sensitivity"
COMPLETENESS_SEED = SUMMARY_SEED + 11
RESOLUTION_ORDER = ["highest_hourly", "daily"]
REPORT_SCHEMES = ["band_5km", "knn_5"]


@dataclass(frozen=True)
class CompletenessScenario:
    name: str
    description: str
    daily_min_hours: int
    sensor_filter: str
    include_highest_hourly: bool


SCENARIOS = (
    CompletenessScenario(
        name="baseline_ge_1h",
        description="All sensors; daily value kept when a sensor has at least one valid hourly record that day.",
        daily_min_hours=1,
        sensor_filter="all",
        include_highest_hourly=True,
    ),
    CompletenessScenario(
        name="daily_ge_12h",
        description="All sensors; daily value kept only when a sensor has at least 12 valid hourly records that day.",
        daily_min_hours=12,
        sensor_filter="all",
        include_highest_hourly=False,
    ),
    CompletenessScenario(
        name="daily_ge_18h",
        description="All sensors; daily value kept only when a sensor has at least 18 valid hourly records that day.",
        daily_min_hours=18,
        sensor_filter="all",
        include_highest_hourly=False,
    ),
    CompletenessScenario(
        name="record_uptime_ge_75pct",
        description="Retain sensors with at least 75% valid hourly records; daily value kept with at least one valid hourly record.",
        daily_min_hours=1,
        sensor_filter="record_uptime_ge_75pct",
        include_highest_hourly=True,
    ),
    CompletenessScenario(
        name="daily_ge_18h_record_uptime_ge_75pct",
        description="Retain sensors with at least 75% valid hourly records and require at least 18 valid hourly records per retained sensor-day.",
        daily_min_hours=18,
        sensor_filter="record_uptime_ge_75pct",
        include_highest_hourly=False,
    ),
    CompletenessScenario(
        name="drop_hourly_gap_gt_30d",
        description="Retain sensors whose longest hourly missing run is no more than 30 days; daily value kept with at least one valid hourly record.",
        daily_min_hours=1,
        sensor_filter="hourly_gap_le_30d",
        include_highest_hourly=True,
    ),
    CompletenessScenario(
        name="daily_ge_50pct_gap_le_90d",
        description="Retain sensors with valid daily means on at least 50% of days and longest daily missing run no more than 90 days.",
        daily_min_hours=1,
        sensor_filter="daily_presence_ge_50pct_gap_le_90d",
        include_highest_hourly=True,
    ),
    CompletenessScenario(
        name="daily_ge_50pct_gap_le_25pct_period",
        description="Retain sensors with valid daily means on at least 50% of days and longest daily missing run no more than 25% of the study period.",
        daily_min_hours=1,
        sensor_filter="daily_presence_ge_50pct_gap_le_25pct_period",
        include_highest_hourly=True,
    ),
)


def max_consecutive_true(values: pd.Series | np.ndarray) -> int:
    longest = 0
    current = 0
    for value in np.asarray(values, dtype=bool):
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def daily_values_and_hours(network: PreparedNetwork) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = network.pm[["Timestamp", *network.sensor_ids]].copy()
    frame["Timestamp"] = pd.to_datetime(frame["Timestamp"])
    indexed = frame.set_index("Timestamp")[network.sensor_ids].sort_index()
    daily_values = indexed.resample("D").mean()
    daily_hours = indexed.notna().resample("D").sum()
    daily_values.index.name = "Timestamp"
    daily_hours.index.name = "Timestamp"
    return daily_values, daily_hours


def sensor_filter_mask(
    network: PreparedNetwork,
    daily_values: pd.DataFrame,
    scenario: CompletenessScenario,
) -> pd.Series:
    hourly_values = network.pm[network.sensor_ids]
    mask = pd.Series(True, index=network.sensor_ids)
    if scenario.sensor_filter == "all":
        return mask
    if scenario.sensor_filter == "record_uptime_ge_75pct":
        return hourly_values.notna().mean(axis=0).reindex(network.sensor_ids).fillna(False) >= 0.75
    if scenario.sensor_filter == "hourly_gap_le_30d":
        longest_gap_hours = hourly_values.isna().apply(max_consecutive_true)
        return longest_gap_hours.reindex(network.sensor_ids).fillna(np.inf) <= 30 * 24
    daily_presence = daily_values.notna().mean(axis=0)
    longest_daily_gap = daily_values.isna().apply(max_consecutive_true)
    if scenario.sensor_filter == "daily_presence_ge_50pct_gap_le_90d":
        return (daily_presence.reindex(network.sensor_ids).fillna(0) >= 0.50) & (
            longest_daily_gap.reindex(network.sensor_ids).fillna(np.inf) <= 90
        )
    if scenario.sensor_filter == "daily_presence_ge_50pct_gap_le_25pct_period":
        proportional_gap_days = int(math.ceil(len(daily_values) * 0.25))
        return (daily_presence.reindex(network.sensor_ids).fillna(0) >= 0.50) & (
            longest_daily_gap.reindex(network.sensor_ids).fillna(np.inf) <= proportional_gap_days
        )
    raise ValueError(f"Unknown sensor filter: {scenario.sensor_filter}")


def scenario_values(
    network: PreparedNetwork,
    resolution: str,
    scenario: CompletenessScenario,
    keep_ids: list[str],
    daily_values: pd.DataFrame,
    daily_hours: pd.DataFrame,
) -> pd.DataFrame:
    if resolution == "highest_hourly":
        values = aggregate_values(network, "highest_hourly")[keep_ids]
    elif resolution == "daily":
        values = daily_values[keep_ids].where(daily_hours[keep_ids] >= scenario.daily_min_hours)
    else:
        raise ValueError(f"Unsupported resolution: {resolution}")
    values.columns = values.columns.astype(str)
    return values


def reference_shift(baseline: pd.DataFrame, filtered: pd.DataFrame) -> dict[str, float | int]:
    baseline_mean = baseline.mean(axis=1, skipna=True)
    filtered_mean = filtered.mean(axis=1, skipna=True)
    paired = pd.DataFrame({"baseline": baseline_mean, "filtered": filtered_mean}).dropna()
    if paired.empty:
        return {
            "reference_windows_compared": 0,
            "reference_bias_filtered_minus_baseline_ugm3": np.nan,
            "reference_mae_filtered_vs_baseline_ugm3": np.nan,
            "reference_max_abs_diff_ugm3": np.nan,
            "reference_pearson_r": np.nan,
        }
    difference = paired["filtered"] - paired["baseline"]
    return {
        "reference_windows_compared": int(len(paired)),
        "reference_bias_filtered_minus_baseline_ugm3": float(difference.mean()),
        "reference_mae_filtered_vs_baseline_ugm3": float(difference.abs().mean()),
        "reference_max_abs_diff_ugm3": float(difference.abs().max()),
        "reference_pearson_r": float(paired["baseline"].corr(paired["filtered"])) if len(paired) >= 3 else np.nan,
    }


def scenario_window_stats(values: pd.DataFrame) -> dict[str, float | int]:
    valid_counts = values.notna().sum(axis=1)
    return {
        "time_windows_total": int(len(values)),
        "time_windows_with_3plus_sensors": int((valid_counts >= 3).sum()),
        "valid_sensor_count_min": int(valid_counts.min()) if len(valid_counts) else 0,
        "valid_sensor_count_p05": float(valid_counts.quantile(0.05)) if len(valid_counts) else np.nan,
        "valid_sensor_count_median": float(valid_counts.median()) if len(valid_counts) else np.nan,
        "valid_sensor_count_max": int(valid_counts.max()) if len(valid_counts) else 0,
    }


def build_scenario_summary(
    network: PreparedNetwork,
    scenario: CompletenessScenario,
    resolution: str,
    keep_ids: list[str],
    values: pd.DataFrame,
    baseline_values: pd.DataFrame,
) -> dict[str, Any]:
    stats = scenario_window_stats(values)
    return {
        "city": network.config.city,
        "dataset_key": network.config.dataset_key,
        "resolution": resolution,
        "scenario": scenario.name,
        "scenario_description": scenario.description,
        "daily_min_hours": scenario.daily_min_hours if resolution == "daily" else np.nan,
        "sensor_filter": scenario.sensor_filter,
        "sensors_baseline": len(network.sensor_ids),
        "sensors_retained": len(keep_ids),
        "sensors_removed": len(network.sensor_ids) - len(keep_ids),
        **stats,
        **reference_shift(baseline_values, values),
    }


def filtered_locations(network: PreparedNetwork, keep_ids: list[str]) -> pd.DataFrame:
    return (
        network.locations[network.locations["Sensor_ID"].isin(keep_ids)]
        .set_index("Sensor_ID")
        .loc[keep_ids]
        .reset_index()
    )


def add_baseline_deltas(morans: pd.DataFrame) -> pd.DataFrame:
    baseline = morans[morans["scenario"] == "baseline_ge_1h"][
        [
            "city",
            "dataset_key",
            "resolution",
            "weight_scheme",
            "median_observed_morans_i",
            "positive_sig_pct",
            "two_sided_sig_pct",
        ]
    ].rename(
        columns={
            "median_observed_morans_i": "baseline_median_observed_morans_i",
            "positive_sig_pct": "baseline_positive_sig_pct",
            "two_sided_sig_pct": "baseline_two_sided_sig_pct",
        }
    )
    merged = morans.merge(
        baseline,
        on=["city", "dataset_key", "resolution", "weight_scheme"],
        how="left",
    )
    merged["delta_median_observed_morans_i"] = (
        merged["median_observed_morans_i"] - merged["baseline_median_observed_morans_i"]
    )
    merged["delta_positive_sig_pct"] = merged["positive_sig_pct"] - merged["baseline_positive_sig_pct"]
    merged["delta_two_sided_sig_pct"] = merged["two_sided_sig_pct"] - merged["baseline_two_sided_sig_pct"]
    return merged


def compact_daily_report_table(morans: pd.DataFrame) -> pd.DataFrame:
    keep = morans[
        (morans["resolution"] == "daily")
        & (morans["weight_scheme"].isin(REPORT_SCHEMES))
        & (
            morans["scenario"].isin(
                [
                    "baseline_ge_1h",
                    "daily_ge_18h",
                    "record_uptime_ge_75pct",
                    "daily_ge_18h_record_uptime_ge_75pct",
                    "drop_hourly_gap_gt_30d",
                    "daily_ge_50pct_gap_le_90d",
                ]
            )
        )
    ].copy()
    keep["city"] = pd.Categorical(keep["city"], categories=["Dhaka", "Lucknow", "Chicago"], ordered=True)
    keep["scenario"] = pd.Categorical(
        keep["scenario"],
        categories=[
            "baseline_ge_1h",
            "daily_ge_18h",
            "record_uptime_ge_75pct",
            "daily_ge_18h_record_uptime_ge_75pct",
            "drop_hourly_gap_gt_30d",
            "daily_ge_50pct_gap_le_90d",
        ],
        ordered=True,
    )
    keep["weight_scheme"] = pd.Categorical(keep["weight_scheme"], categories=REPORT_SCHEMES, ordered=True)
    return keep.sort_values(["city", "scenario", "weight_scheme"])


def compact_highest_report_table(morans: pd.DataFrame) -> pd.DataFrame:
    keep = morans[
        (morans["resolution"] == "highest_hourly")
        & (morans["weight_scheme"] == "knn_5")
        & (
            morans["scenario"].isin(
                [
                    "baseline_ge_1h",
                    "record_uptime_ge_75pct",
                    "drop_hourly_gap_gt_30d",
                    "daily_ge_50pct_gap_le_90d",
                ]
            )
        )
    ].copy()
    keep["city"] = pd.Categorical(keep["city"], categories=["Dhaka", "Lucknow", "Chicago"], ordered=True)
    return keep.sort_values(["city", "scenario"])


def compact_scenario_table(summary: pd.DataFrame) -> pd.DataFrame:
    keep = summary[
        (summary["resolution"] == "daily")
        & (
            summary["scenario"].isin(
                [
                    "baseline_ge_1h",
                    "daily_ge_18h",
                    "record_uptime_ge_75pct",
                    "daily_ge_18h_record_uptime_ge_75pct",
                    "drop_hourly_gap_gt_30d",
                    "daily_ge_50pct_gap_le_90d",
                ]
            )
        )
    ].copy()
    keep["city"] = pd.Categorical(keep["city"], categories=["Dhaka", "Lucknow", "Chicago"], ordered=True)
    keep["scenario"] = pd.Categorical(
        keep["scenario"],
        categories=[
            "baseline_ge_1h",
            "daily_ge_18h",
            "record_uptime_ge_75pct",
            "daily_ge_18h_record_uptime_ge_75pct",
            "drop_hourly_gap_gt_30d",
            "daily_ge_50pct_gap_le_90d",
        ],
        ordered=True,
    )
    return keep.sort_values(["city", "scenario"])


def plot_daily_knn5(morans: pd.DataFrame) -> None:
    setup_matplotlib()
    scenarios = [
        "baseline_ge_1h",
        "daily_ge_18h",
        "record_uptime_ge_75pct",
        "daily_ge_18h_record_uptime_ge_75pct",
        "drop_hourly_gap_gt_30d",
        "daily_ge_50pct_gap_le_90d",
    ]
    plot_data = morans[
        (morans["resolution"] == "daily")
        & (morans["weight_scheme"] == "knn_5")
        & (morans["scenario"].isin(scenarios))
    ].copy()
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), sharey=True)
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        subset = plot_data[plot_data["city"] == city].set_index("scenario").reindex(scenarios)
        x_positions = np.arange(len(scenarios))
        axis.bar(
            x_positions,
            subset["positive_sig_pct"],
            color=CITY_COLORS[city],
            alpha=0.82,
        )
        axis.axhline(5, color="black", linewidth=0.8, linestyle="--", alpha=0.65)
        axis.set_title(city)
        axis.set_xticks(x_positions)
        axis.set_xticklabels(
            [
                "baseline",
                "18h/day",
                "75% uptime",
                "18h + 75%",
                "gap ≤30d",
                "50% daily + gap≤90d",
            ],
            rotation=35,
            ha="right",
        )
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("% daily windows with positive Moran's I, permutation p ≤ 0.05")
    fig.suptitle("Daily spatial autocorrelation sensitivity to completeness filters (kNN-5)")
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "daily_knn5_positive_morans_completeness_sensitivity", dpi=OUTPUT_DPI)


def plot_reference_shift(summary: pd.DataFrame) -> None:
    setup_matplotlib()
    scenarios = [
        "daily_ge_18h",
        "record_uptime_ge_75pct",
        "daily_ge_18h_record_uptime_ge_75pct",
        "drop_hourly_gap_gt_30d",
        "daily_ge_50pct_gap_le_90d",
    ]
    plot_data = summary[(summary["resolution"] == "daily") & (summary["scenario"].isin(scenarios))].copy()
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.0), sharey=True)
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        subset = plot_data[plot_data["city"] == city].set_index("scenario").reindex(scenarios)
        x_positions = np.arange(len(scenarios))
        axis.bar(
            x_positions,
            subset["reference_mae_filtered_vs_baseline_ugm3"],
            color=CITY_COLORS[city],
            alpha=0.82,
        )
        axis.set_title(city)
        axis.set_xticks(x_positions)
        axis.set_xticklabels(
            ["18h/day", "75% uptime", "18h + 75%", "gap ≤30d", "50% daily + gap≤90d"],
            rotation=35,
            ha="right",
        )
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("Mean absolute shift in daily network mean (µg/m³)")
    fig.suptitle("Estimand shift caused by completeness filters")
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "daily_reference_mean_shift_completeness_sensitivity", dpi=OUTPUT_DPI)


def plot_valid_sensor_counts(summary: pd.DataFrame) -> None:
    setup_matplotlib()
    scenarios = [
        "baseline_ge_1h",
        "daily_ge_18h",
        "record_uptime_ge_75pct",
        "daily_ge_18h_record_uptime_ge_75pct",
        "drop_hourly_gap_gt_30d",
        "daily_ge_50pct_gap_le_90d",
    ]
    plot_data = summary[(summary["resolution"] == "daily") & (summary["scenario"].isin(scenarios))].copy()
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.0), sharey=False)
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        subset = plot_data[plot_data["city"] == city].set_index("scenario").reindex(scenarios)
        x_positions = np.arange(len(scenarios))
        axis.plot(
            x_positions,
            subset["sensors_retained"],
            marker="o",
            linewidth=1.8,
            label="Retained sensors",
            color=CITY_COLORS[city],
        )
        axis.plot(
            x_positions,
            subset["valid_sensor_count_median"],
            marker="s",
            linewidth=1.8,
            label="Median valid sensors/day",
            color="black",
        )
        axis.set_title(city)
        axis.set_xticks(x_positions)
        axis.set_xticklabels(
            ["baseline", "18h/day", "75% uptime", "18h + 75%", "gap ≤30d", "50% daily + gap≤90d"],
            rotation=35,
            ha="right",
        )
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("Sensor count")
    axes[-1].legend()
    fig.suptitle("Sensor retention and daily valid counts under completeness filters")
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "daily_valid_sensor_counts_completeness_sensitivity", dpi=OUTPUT_DPI)


def write_report(summary: pd.DataFrame, morans: pd.DataFrame) -> None:
    lines = [
        "# Spatial Completeness Sensitivity",
        "",
        "## Scope",
        "",
        "This sensitivity analysis asks whether stricter completeness handling changes the spatial-autocorrelation conclusions for Dhaka, Lucknow, and Chicago corrected LCS with Chicago collocation sensors excluded.",
        "",
        "The daily analysis compares minimum valid-hour thresholds, sensor-level uptime filters, long-gap filters, and the data-driven daily-presence/gap rule identified in the missingness diagnostics. The highest-resolution analysis uses the canonical aligned hourly matrices and only applies sensor-retention filters; daily valid-hour thresholds do not apply to hourly rows.",
        "",
        f"Permutation Moran's I uses {N_PERMUTATIONS} deterministic permutations per sampled time window with seed {COMPLETENESS_SEED}. Daily and hourly windows are deterministically thinned when needed for bounded runtime.",
        "",
        "## Daily Scenario Summary",
        "",
        markdown_table(
            compact_scenario_table(summary),
            [
                "city",
                "scenario",
                "sensors_retained",
                "sensors_removed",
                "time_windows_with_3plus_sensors",
                "valid_sensor_count_median",
                "reference_mae_filtered_vs_baseline_ugm3",
                "reference_bias_filtered_minus_baseline_ugm3",
            ],
        ),
        "",
        "## Daily Moran Sensitivity",
        "",
        markdown_table(
            compact_daily_report_table(morans),
            [
                "city",
                "scenario",
                "weight_scheme",
                "time_windows_tested",
                "median_observed_morans_i",
                "positive_sig_pct",
                "two_sided_sig_pct",
                "delta_positive_sig_pct",
            ],
        ),
        "",
        "## Highest-Hourly Sensor-Retention Sensitivity",
        "",
        markdown_table(
            compact_highest_report_table(morans),
            [
                "city",
                "scenario",
                "time_windows_tested",
                "median_observed_morans_i",
                "positive_sig_pct",
                "two_sided_sig_pct",
                "delta_positive_sig_pct",
            ],
        ),
        "",
        "## Interpretation",
        "",
        "- Daily valid-hour thresholds and sensor-retention filters do not create a strong daily positive Moran signal in Dhaka or Lucknow under kNN-5.",
        "- Chicago remains spatially autocorrelated under all practical completeness filters, so the Chicago spatial signal is not an artifact of low-completeness sensor-days.",
        "- Lucknow's data-driven 50% daily presence plus <=90 day gap filter mainly addresses missingness structure and reference-mean stability; it does not materially change the conclusion that daily spatial autocorrelation is weak/inconsistent.",
        "- Any manuscript claim should say spatial autocorrelation was not consistently detectable in Dhaka/Lucknow at observed spacing and daily aggregation, while Chicago showed clearer positive spatial structure.",
        "",
        "## Output Files",
        "",
        "- `spatial_completeness_scenario_summary.csv`",
        "- `spatial_completeness_morans_i_sensitivity.csv`",
        "- `spatial_completeness_sensor_retention.csv`",
        "- `spatial_completeness_sensitivity_metadata.json`",
        "- `spatial/plots/completeness_sensitivity/daily_knn5_positive_morans_completeness_sensitivity.png` and `.pdf`",
        "- `spatial/plots/completeness_sensitivity/daily_reference_mean_shift_completeness_sensitivity.png` and `.pdf`",
        "- `spatial/plots/completeness_sensitivity/daily_valid_sensor_counts_completeness_sensitivity.png` and `.pdf`",
    ]
    (OUTPUT_DIR / "spatial_completeness_sensitivity.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(COMPLETENESS_SEED)
    summary_records: list[dict[str, Any]] = []
    moran_records: list[dict[str, Any]] = []
    retention_records: list[dict[str, Any]] = []

    for config in NETWORKS:
        network = prepare_network(config)
        daily_values, daily_hours = daily_values_and_hours(network)
        baseline_by_resolution = {
            "highest_hourly": aggregate_values(network, "highest_hourly"),
            "daily": daily_values.where(daily_hours >= 1),
        }
        for scenario in SCENARIOS:
            keep_mask = sensor_filter_mask(network, daily_values, scenario)
            keep_ids = [sensor_id for sensor_id in network.sensor_ids if bool(keep_mask.loc[sensor_id])]
            retention_records.extend(
                {
                    "city": config.city,
                    "dataset_key": config.dataset_key,
                    "scenario": scenario.name,
                    "sensor_id": sensor_id,
                    "retained": bool(sensor_id in keep_ids),
                }
                for sensor_id in network.sensor_ids
            )
            for resolution in RESOLUTION_ORDER:
                if resolution == "highest_hourly" and not scenario.include_highest_hourly:
                    continue
                if len(keep_ids) < 3:
                    continue
                values = scenario_values(network, resolution, scenario, keep_ids, daily_values, daily_hours)
                baseline_values = baseline_by_resolution[resolution][network.sensor_ids]
                summary_records.append(
                    build_scenario_summary(network, scenario, resolution, keep_ids, values, baseline_values)
                )
                scenario_locations = filtered_locations(network, keep_ids)
                schemes = build_weight_schemes(distance_matrix_km(scenario_locations))
                for scheme in schemes:
                    record = permutation_morans_summary(
                        config.city,
                        config.dataset_key,
                        resolution,
                        values,
                        scheme,
                        rng,
                    )
                    record["scenario"] = scenario.name
                    record["scenario_description"] = scenario.description
                    record["sensors_retained"] = len(keep_ids)
                    moran_records.append(record)
                print(
                    f"{config.city} {resolution} {scenario.name}: "
                    f"retained={len(keep_ids)} windows={len(values)}"
                )

    summary = pd.DataFrame(summary_records)
    morans = add_baseline_deltas(pd.DataFrame(moran_records))
    retention = pd.DataFrame(retention_records)
    summary.to_csv(OUTPUT_DIR / "spatial_completeness_scenario_summary.csv", index=False)
    morans.to_csv(OUTPUT_DIR / "spatial_completeness_morans_i_sensitivity.csv", index=False)
    retention.to_csv(OUTPUT_DIR / "spatial_completeness_sensor_retention.csv", index=False)
    metadata = {
        "purpose": "Completeness-filtered spatial autocorrelation sensitivity for the three primary city networks.",
        "seed": COMPLETENESS_SEED,
        "n_permutations": N_PERMUTATIONS,
        "alpha": ALPHA,
        "resolutions": RESOLUTION_ORDER,
        "scenarios": [scenario.__dict__ for scenario in SCENARIOS],
        "note": "Highest-hourly uses the canonical aligned hourly matrices; daily valid-hour thresholds apply only to daily aggregation.",
    }
    (OUTPUT_DIR / "spatial_completeness_sensitivity_metadata.json").write_text(json.dumps(metadata, indent=2, default=str))
    plot_daily_knn5(morans)
    plot_reference_shift(summary)
    plot_valid_sensor_counts(summary)
    write_report(summary, morans)
    print(f"Wrote spatial completeness sensitivity outputs to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        compact_daily_report_table(morans)[
            [
                "city",
                "scenario",
                "weight_scheme",
                "time_windows_tested",
                "median_observed_morans_i",
                "positive_sig_pct",
                "delta_positive_sig_pct",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
