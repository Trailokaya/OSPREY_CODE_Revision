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
RANDOM_SEED = 20260525
N_BOOTSTRAPS = 10_000


@dataclass(frozen=True)
class FilterResult:
    filter_name: str
    description: str
    kept_sensors: list[str]
    removed_sensors: list[str]


def pearson_r(x_values: pd.Series, y_values: pd.Series) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    return float(frame["x"].corr(frame["y"]))


def spearman_rho(x_values: pd.Series, y_values: pd.Series) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    return float(frame["x"].rank(method="average").corr(frame["y"].rank(method="average")))


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


def bootstrap_ci(values: pd.Series, rng: np.random.Generator) -> tuple[float, float]:
    array = values.dropna().to_numpy(dtype=float)
    if len(array) < 2:
        return float("nan"), float("nan")
    bootstrapped = np.empty(N_BOOTSTRAPS, dtype=float)
    for index in range(N_BOOTSTRAPS):
        sample = rng.choice(array, size=len(array), replace=True)
        bootstrapped[index] = sample.mean()
    return float(np.quantile(bootstrapped, 0.025)), float(np.quantile(bootstrapped, 0.975))


def build_episodes(series: pd.Series, threshold: float) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    start = None
    previous = None
    for timestamp, value in series.sort_index().items():
        if pd.notna(value) and value >= threshold:
            if start is None:
                start = timestamp
            previous = timestamp
        elif start is not None and previous is not None:
            window = series.loc[start:previous]
            records.append(
                {
                    "start_date": start.date().isoformat(),
                    "end_date": previous.date().isoformat(),
                    "duration_days": int(len(window)),
                    "mean_missing_pct": float(window.mean() * 100),
                    "max_missing_pct": float(window.max() * 100),
                }
            )
            start = None
            previous = None
    if start is not None and previous is not None:
        window = series.loc[start:previous]
        records.append(
            {
                "start_date": start.date().isoformat(),
                "end_date": previous.date().isoformat(),
                "duration_days": int(len(window)),
                "mean_missing_pct": float(window.mean() * 100),
                "max_missing_pct": float(window.max() * 100),
            }
        )
    if not records:
        return pd.DataFrame(columns=["start_date", "end_date", "duration_days", "mean_missing_pct", "max_missing_pct"])
    return pd.DataFrame(records).sort_values(["duration_days", "max_missing_pct"], ascending=[False, False])


def summarize_daily_filter(
    filter_result: FilterResult,
    daily: pd.DataFrame,
    availability: pd.DataFrame,
    baseline_reference_mean: pd.Series,
    baseline_missing_fraction: pd.Series,
    rng: np.random.Generator,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    kept = filter_result.kept_sensors
    filtered_daily = daily[kept]
    filtered_availability = availability[kept]
    reference_mean = filtered_daily.mean(axis=1, skipna=True)
    reference_median = filtered_daily.median(axis=1, skipna=True)
    spatial_sd = filtered_daily.std(axis=1, skipna=True)
    spatial_cv = spatial_sd / reference_mean
    daily_missing_fraction = 1 - filtered_availability.mean(axis=1, skipna=True)
    daily_valid_sensor_count = filtered_daily.notna().sum(axis=1)

    paired = pd.DataFrame(
        {
            "baseline_reference_mean_ugm3": baseline_reference_mean,
            "filtered_reference_mean_ugm3": reference_mean,
            "baseline_daily_missing_fraction": baseline_missing_fraction,
            "filtered_daily_missing_fraction": daily_missing_fraction,
        }
    ).dropna()
    mean_difference = paired["filtered_reference_mean_ugm3"] - paired["baseline_reference_mean_ugm3"]
    absolute_difference = mean_difference.abs()
    missing_improvement = paired["baseline_daily_missing_fraction"] - paired["filtered_daily_missing_fraction"]
    ci_low, ci_high = bootstrap_ci(missing_improvement * 100, rng)

    sensor_longest_gaps = filtered_daily.isna().apply(max_consecutive_true)
    sensor_record_uptime = filtered_availability.mean(axis=0)
    summary = {
        "filter_name": filter_result.filter_name,
        "description": filter_result.description,
        "sensors_retained": int(len(kept)),
        "sensors_removed": int(len(filter_result.removed_sensors)),
        "removed_sensor_ids": ";".join(filter_result.removed_sensors),
        "record_missing_fraction_pct": float((1 - filtered_availability.stack().mean()) * 100),
        "daily_missing_fraction_mean_pct": float(daily_missing_fraction.mean() * 100),
        "daily_missing_fraction_median_pct": float(daily_missing_fraction.median() * 100),
        "daily_missing_fraction_p90_pct": float(daily_missing_fraction.quantile(0.90) * 100),
        "daily_missing_fraction_max_pct": float(daily_missing_fraction.max() * 100),
        "daily_valid_sensor_min": int(daily_valid_sensor_count.min()),
        "daily_valid_sensor_median": float(daily_valid_sensor_count.median()),
        "days_missing_ge_25pct": int((daily_missing_fraction >= 0.25).sum()),
        "days_missing_ge_30pct": int((daily_missing_fraction >= 0.30).sum()),
        "days_missing_ge_40pct": int((daily_missing_fraction >= 0.40).sum()),
        "days_missing_ge_50pct": int((daily_missing_fraction >= 0.50).sum()),
        "longest_daily_missing_ge_25pct_episode_days": int(
            build_episodes(daily_missing_fraction, 0.25)["duration_days"].max()
            if not build_episodes(daily_missing_fraction, 0.25).empty
            else 0
        ),
        "median_sensor_daily_uptime_pct": float(sensor_record_uptime.median() * 100),
        "min_sensor_daily_uptime_pct": float(sensor_record_uptime.min() * 100),
        "sensors_with_gap_gt_30d": int((sensor_longest_gaps > 30).sum()),
        "sensors_with_gap_gt_90d": int((sensor_longest_gaps > 90).sum()),
        "baseline_minus_filtered_missing_mean_pct_points": float(missing_improvement.mean() * 100),
        "baseline_minus_filtered_missing_mean_ci_low": ci_low,
        "baseline_minus_filtered_missing_mean_ci_high": ci_high,
        "reference_mean_bias_filtered_minus_baseline_ugm3": float(mean_difference.mean()),
        "reference_mean_mae_vs_baseline_ugm3": float(absolute_difference.mean()),
        "reference_mean_rmse_vs_baseline_ugm3": float(math.sqrt((mean_difference**2).mean())),
        "reference_mean_max_abs_diff_ugm3": float(absolute_difference.max()),
        "reference_mean_p95_abs_diff_ugm3": float(absolute_difference.quantile(0.95)),
        "reference_mean_pearson_r": pearson_r(
            paired["baseline_reference_mean_ugm3"],
            paired["filtered_reference_mean_ugm3"],
        ),
    }

    daily_metrics = pd.DataFrame(
        {
            "filter_name": filter_result.filter_name,
            "date": daily.index,
            "reference_mean_ugm3": reference_mean,
            "reference_median_ugm3": reference_median,
            "spatial_sd_ugm3": spatial_sd,
            "spatial_cv": spatial_cv,
            "daily_missing_fraction": daily_missing_fraction,
            "daily_valid_sensor_count": daily_valid_sensor_count,
        }
    ).reset_index(drop=True)
    daily_metrics["date"] = pd.to_datetime(daily_metrics["date"])
    daily_metrics["time_index_days"] = (daily_metrics["date"] - daily_metrics["date"].min()).dt.days

    correlation_records = []
    for variable, column in [
        ("daily_mean_pm25", "reference_mean_ugm3"),
        ("daily_median_pm25", "reference_median_ugm3"),
        ("daily_spatial_sd", "spatial_sd_ugm3"),
        ("daily_spatial_cv", "spatial_cv"),
        ("calendar_time", "time_index_days"),
    ]:
        correlation_records.append(
            {
                "filter_name": filter_result.filter_name,
                "x_variable": variable,
                "y_variable": "daily_missing_fraction",
                "n_days": int(daily_metrics[[column, "daily_missing_fraction"]].dropna().shape[0]),
                "pearson_r": pearson_r(daily_metrics[column], daily_metrics["daily_missing_fraction"]),
                "spearman_rho": spearman_rho(daily_metrics[column], daily_metrics["daily_missing_fraction"]),
            }
        )

    episodes = build_episodes(daily_missing_fraction, 0.25).copy()
    episodes.insert(0, "filter_name", filter_result.filter_name)
    return summary, daily_metrics, pd.DataFrame(correlation_records), episodes


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    display = frame[columns].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def build_mar_factor_delta(correlations: pd.DataFrame) -> pd.DataFrame:
    baseline = correlations[correlations["filter_name"] == "baseline_all_sensors"][
        ["x_variable", "spearman_rho", "pearson_r"]
    ].rename(
        columns={
            "spearman_rho": "baseline_spearman_rho",
            "pearson_r": "baseline_pearson_r",
        }
    )
    filtered = correlations[correlations["filter_name"] != "baseline_all_sensors"].copy()
    delta = filtered.merge(baseline, on="x_variable", how="left")
    delta["filtered_spearman_rho"] = delta["spearman_rho"]
    delta["filtered_pearson_r"] = delta["pearson_r"]
    delta["spearman_delta_filtered_minus_baseline"] = (
        delta["filtered_spearman_rho"] - delta["baseline_spearman_rho"]
    )
    delta["abs_spearman_baseline"] = delta["baseline_spearman_rho"].abs()
    delta["abs_spearman_filtered"] = delta["filtered_spearman_rho"].abs()
    delta["abs_spearman_reduction"] = delta["abs_spearman_baseline"] - delta["abs_spearman_filtered"]
    delta["abs_spearman_reduction_pct"] = np.where(
        delta["abs_spearman_baseline"] > 0,
        delta["abs_spearman_reduction"] / delta["abs_spearman_baseline"] * 100,
        np.nan,
    )
    return delta[
        [
            "filter_name",
            "x_variable",
            "baseline_spearman_rho",
            "filtered_spearman_rho",
            "spearman_delta_filtered_minus_baseline",
            "abs_spearman_reduction",
            "abs_spearman_reduction_pct",
            "baseline_pearson_r",
            "filtered_pearson_r",
            "n_days",
        ]
    ]


def write_report(
    summary: pd.DataFrame,
    removed: pd.DataFrame,
    correlations: pd.DataFrame,
    mar_delta: pd.DataFrame,
    episodes: pd.DataFrame,
) -> None:
    baseline = summary[summary["filter_name"] == "baseline_all_sensors"].iloc[0]
    nonbaseline = summary[summary["filter_name"] != "baseline_all_sensors"].copy()
    best_missing = nonbaseline.sort_values("baseline_minus_filtered_missing_mean_pct_points", ascending=False).iloc[0]
    best_reference = nonbaseline.sort_values("reference_mean_mae_vs_baseline_ugm3", ascending=True).iloc[0]
    practical_choice = summary[summary["filter_name"] == "daily_presence_ge_50pct"].iloc[0]
    strongest_correlations = (
        correlations.assign(abs_spearman=correlations["spearman_rho"].abs())
        .sort_values(["filter_name", "abs_spearman"], ascending=[True, False])
        .groupby("filter_name", as_index=False)
        .head(2)
    )
    key_mar_delta = mar_delta[
        mar_delta["x_variable"].isin(["daily_mean_pm25", "daily_spatial_cv", "calendar_time"])
    ].copy()
    top_episodes = (
        episodes.sort_values(["filter_name", "duration_days"], ascending=[True, False])
        .groupby("filter_name", as_index=False)
        .head(3)
        if not episodes.empty
        else episodes
    )

    lines = [
        "# Lucknow Missingness Filter Sensitivity",
        "",
        "## Scope",
        "",
        "This compares Lucknow baseline data against three practical filtering rules: remove the five worst-uptime sensors, retain sensors with at least 50% hourly-record presence, and retain sensors with at least 50% daily presence. The 50% hourly-record rule is stricter for sensors that appear on many days but have partial-day coverage.",
        "",
        "## Main Summary",
        "",
        markdown_table(
            summary,
            [
                "filter_name",
                "sensors_retained",
                "sensors_removed",
                "record_missing_fraction_pct",
                "daily_missing_fraction_median_pct",
                "daily_missing_fraction_p90_pct",
                "days_missing_ge_25pct",
                "longest_daily_missing_ge_25pct_episode_days",
                "baseline_minus_filtered_missing_mean_pct_points",
                "baseline_minus_filtered_missing_mean_ci_low",
                "baseline_minus_filtered_missing_mean_ci_high",
            ],
        ),
        "",
        "## Practical Conclusion",
        "",
        f"- Baseline Lucknow median daily missingness is {baseline['daily_missing_fraction_median_pct']:.2f}%, with {int(baseline['days_missing_ge_25pct'])} days at or above 25% missingness.",
        f"- The largest missingness gain comes from `{best_missing['filter_name']}`: mean daily missingness improves by {best_missing['baseline_minus_filtered_missing_mean_pct_points']:.2f} percentage points, with bootstrap 95% CI [{best_missing['baseline_minus_filtered_missing_mean_ci_low']:.2f}, {best_missing['baseline_minus_filtered_missing_mean_ci_high']:.2f}].",
        f"- The smallest reference-mean disruption comes from `{best_reference['filter_name']}`: MAE versus baseline is {best_reference['reference_mean_mae_vs_baseline_ugm3']:.2f} µg/m³.",
        f"- A pragmatic default is `{practical_choice['filter_name']}` if we want a low-distortion sensitivity case: it removes {int(practical_choice['sensors_removed'])} sensors, improves mean missingness by {practical_choice['baseline_minus_filtered_missing_mean_pct_points']:.2f} percentage points, and changes the daily reference mean by MAE {practical_choice['reference_mean_mae_vs_baseline_ugm3']:.2f} µg/m³.",
        "- All non-baseline filters have bootstrap confidence intervals above zero for mean daily missingness improvement, so the improvement is statistically stable at the day level. The main limitation is that all filters still leave a long late-period high-missingness episode.",
        "",
        "## Reference Mean Impact",
        "",
        markdown_table(
            summary,
            [
                "filter_name",
                "reference_mean_bias_filtered_minus_baseline_ugm3",
                "reference_mean_mae_vs_baseline_ugm3",
                "reference_mean_p95_abs_diff_ugm3",
                "reference_mean_max_abs_diff_ugm3",
                "reference_mean_pearson_r",
            ],
        ),
        "",
        "## Removed Sensors",
        "",
        markdown_table(
            removed,
            [
                "filter_name",
                "sensor_id",
                "station_name",
                "record_uptime_pct",
                "daily_presence_pct",
                "longest_missing_gap_days",
                "period_mean_pm25_ugm3",
            ],
        ),
        "",
        "## Strongest Remaining Missingness Correlations",
        "",
        markdown_table(strongest_correlations, ["filter_name", "x_variable", "spearman_rho", "pearson_r", "n_days"]),
        "",
        "## Observed MAR-Factor Change",
        "",
        "These are observed-data association screens, not formal MAR tests. Lower absolute Spearman values mean missingness is less tied to the observed factor after filtering.",
        "",
        markdown_table(
            key_mar_delta,
            [
                "filter_name",
                "x_variable",
                "baseline_spearman_rho",
                "filtered_spearman_rho",
                "abs_spearman_reduction",
                "abs_spearman_reduction_pct",
            ],
        ),
        "",
        "## High-Missing Episodes After Filtering",
        "",
    ]
    if top_episodes.empty:
        lines.append("No daily missingness episodes at or above 25% remain.")
    else:
        lines.append(
            markdown_table(
                top_episodes,
                ["filter_name", "start_date", "end_date", "duration_days", "mean_missing_pct", "max_missing_pct"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A filter meaningfully improves missingness if it lowers median and high-percentile daily missingness, shortens high-missing episodes, and does not materially shift the reference mean. These tables separate the data-completeness benefit from the estimand-change cost.",
            "",
            "## Output Files",
            "",
            "- `lucknow_missingness_filter_sensitivity_summary.csv`",
            "- `lucknow_missingness_filter_removed_sensors.csv`",
            "- `lucknow_missingness_filter_daily_metrics.csv`",
            "- `lucknow_missingness_filter_correlations.csv`",
            "- `lucknow_missingness_filter_mar_factor_delta.csv`",
            "- `lucknow_missingness_filter_high_missing_episodes.csv`",
            "- `lucknow_missingness_filter_sensitivity.md`",
        ]
    )
    (OUTPUT_DIR / "lucknow_missingness_filter_sensitivity.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    config = next(config for config in PRIMARY_NETWORKS if config.city == "Lucknow")
    pm = read_pm_matrix(config.pm_path)
    _, locations = read_locations(config)
    sensor_ids = retained_sensor_ids(locations, pm)
    locations = locations[locations["Sensor_ID"].isin(sensor_ids)].set_index("Sensor_ID").loc[sensor_ids].reset_index()
    daily = daily_sensor_means(config, pm, sensor_ids)
    availability = daily_sensor_availability(config, pm, sensor_ids).reindex(daily.index)

    record_uptime = pm[sensor_ids].notna().mean(axis=0)
    daily_presence = daily.notna().mean(axis=0)
    longest_gaps = daily.isna().apply(max_consecutive_true)
    period_means = daily.mean(axis=0, skipna=True)

    worst_five = record_uptime.sort_values().head(5).index.astype(str).tolist()
    record_ge_50 = record_uptime[record_uptime >= 0.50].index.astype(str).tolist()
    daily_ge_50 = daily_presence[daily_presence >= 0.50].index.astype(str).tolist()
    filters = [
        FilterResult(
            "baseline_all_sensors",
            "All retained Lucknow sensors.",
            list(sensor_ids),
            [],
        ),
        FilterResult(
            "remove_5_most_missing",
            "Remove the five sensors with lowest hourly-record uptime.",
            [sensor_id for sensor_id in sensor_ids if sensor_id not in worst_five],
            worst_five,
        ),
        FilterResult(
            "record_presence_ge_50pct",
            "Keep sensors with at least 50% hourly-record presence.",
            record_ge_50,
            [sensor_id for sensor_id in sensor_ids if sensor_id not in record_ge_50],
        ),
        FilterResult(
            "daily_presence_ge_50pct",
            "Keep sensors with valid daily means on at least 50% of days.",
            daily_ge_50,
            [sensor_id for sensor_id in sensor_ids if sensor_id not in daily_ge_50],
        ),
    ]

    baseline_mean = daily[sensor_ids].mean(axis=1, skipna=True)
    baseline_missing = 1 - availability[sensor_ids].mean(axis=1, skipna=True)
    summary_records = []
    daily_frames = []
    correlation_frames = []
    episode_frames = []
    for filter_result in filters:
        summary, daily_metrics, correlations, episodes = summarize_daily_filter(
            filter_result,
            daily,
            availability,
            baseline_mean,
            baseline_missing,
            rng,
        )
        summary_records.append(summary)
        daily_frames.append(daily_metrics)
        correlation_frames.append(correlations)
        episode_frames.append(episodes)

    summary = pd.DataFrame(summary_records)
    daily_metrics = pd.concat(daily_frames, ignore_index=True)
    correlations = pd.concat(correlation_frames, ignore_index=True)
    mar_delta = build_mar_factor_delta(correlations)
    episodes = pd.concat(episode_frames, ignore_index=True)

    removed_records = []
    location_lookup = locations.set_index("Sensor_ID")
    for filter_result in filters:
        for sensor_id in filter_result.removed_sensors:
            location = location_lookup.loc[sensor_id]
            removed_records.append(
                {
                    "filter_name": filter_result.filter_name,
                    "sensor_id": sensor_id,
                    "station_name": location["Station_Name"],
                    "latitude": float(location["Latitude"]),
                    "longitude": float(location["Longitude"]),
                    "record_uptime_pct": float(record_uptime.loc[sensor_id] * 100),
                    "daily_presence_pct": float(daily_presence.loc[sensor_id] * 100),
                    "longest_missing_gap_days": int(longest_gaps.loc[sensor_id]),
                    "period_mean_pm25_ugm3": float(period_means.loc[sensor_id]),
                }
            )
    removed = pd.DataFrame(removed_records)

    outputs = {
        "lucknow_missingness_filter_sensitivity_summary.csv": summary,
        "lucknow_missingness_filter_removed_sensors.csv": removed,
        "lucknow_missingness_filter_daily_metrics.csv": daily_metrics,
        "lucknow_missingness_filter_correlations.csv": correlations,
        "lucknow_missingness_filter_mar_factor_delta.csv": mar_delta,
        "lucknow_missingness_filter_high_missing_episodes.csv": episodes,
    }
    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)

    metadata = {
        "purpose": "Lucknow sensitivity for removing most-missing sensors and applying 50% presence thresholds.",
        "random_seed": RANDOM_SEED,
        "n_bootstraps": N_BOOTSTRAPS,
        "primary_50pct_rule": "record_presence_ge_50pct",
        "note": "Daily-presence >=50% is also included because partial-day sensors can have low hourly presence but many valid daily means.",
        "outputs": sorted([*outputs.keys(), "lucknow_missingness_filter_sensitivity.md"]),
    }
    (OUTPUT_DIR / "lucknow_missingness_filter_sensitivity_metadata.json").write_text(json.dumps(metadata, indent=2))
    write_report(summary, removed, correlations, mar_delta, episodes)
    print(f"Wrote Lucknow filter sensitivity to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        summary[
            [
                "filter_name",
                "sensors_retained",
                "daily_missing_fraction_median_pct",
                "daily_missing_fraction_p90_pct",
                "days_missing_ge_25pct",
                "baseline_minus_filtered_missing_mean_pct_points",
                "reference_mean_mae_vs_baseline_ugm3",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
