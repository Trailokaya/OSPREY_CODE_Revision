from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = REPO_ROOT / "analysis/results/three_city_comparative_analysis"
OUTPUT_DIR = INPUT_DIR
RANDOM_SEED = 20260524
N_PERMUTATIONS = 10_000
N_BOOTSTRAPS = 2_000


@dataclass(frozen=True)
class DailyVariable:
    column: str
    label: str
    domain: str


@dataclass(frozen=True)
class SensorVariable:
    column: str
    label: str
    domain: str


DAILY_VARIABLES = (
    DailyVariable("daily_reference_mean_ugm3", "daily_mean_pm25", "concentration"),
    DailyVariable("daily_reference_median_ugm3", "daily_median_pm25", "concentration"),
    DailyVariable("daily_spatial_sd_ugm3", "daily_spatial_sd", "spatial_variability"),
    DailyVariable("daily_spatial_cv", "daily_spatial_cv", "spatial_variability"),
    DailyVariable("time_index_days", "calendar_time", "temporal_structure"),
)

SENSOR_VARIABLES = (
    SensorVariable("period_mean_pm25_ugm3", "sensor_period_mean_pm25", "sensor_level_pm25"),
    SensorVariable("period_sd_daily_pm25_ugm3", "sensor_daily_pm25_sd", "sensor_level_variability"),
    SensorVariable("latitude", "sensor_latitude", "sensor_location"),
    SensorVariable("longitude", "sensor_longitude", "sensor_location"),
)


def pearson_r(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if len(x) < 3:
        return float("nan")
    x_centered = x - x.mean()
    y_centered = y - y.mean()
    denominator = np.sqrt(np.sum(x_centered**2) * np.sum(y_centered**2))
    if denominator == 0:
        return float("nan")
    return float(np.sum(x_centered * y_centered) / denominator)


def spearman_rho(x_values: pd.Series | np.ndarray, y_values: pd.Series | np.ndarray) -> float:
    x = pd.Series(x_values, dtype="float64")
    y = pd.Series(y_values, dtype="float64")
    frame = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    return pearson_r(frame["x"].rank(method="average"), frame["y"].rank(method="average"))


def permutation_p_value(
    x_values: pd.Series,
    y_values: pd.Series,
    rng: np.random.Generator,
    n_permutations: int = N_PERMUTATIONS,
) -> float:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 6:
        return float("nan")
    x_rank = frame["x"].rank(method="average").to_numpy(dtype=float)
    y_rank = frame["y"].rank(method="average").to_numpy(dtype=float)
    observed = abs(pearson_r(x_rank, y_rank))
    count = 0
    for _ in range(n_permutations):
        permuted_y = rng.permutation(y_rank)
        if abs(pearson_r(x_rank, permuted_y)) >= observed:
            count += 1
    return float((count + 1) / (n_permutations + 1))


def bootstrap_spearman_ci(
    x_values: pd.Series,
    y_values: pd.Series,
    rng: np.random.Generator,
    n_bootstraps: int = N_BOOTSTRAPS,
) -> tuple[float, float]:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 6:
        return float("nan"), float("nan")
    x = frame["x"].to_numpy(dtype=float)
    y = frame["y"].to_numpy(dtype=float)
    estimates = np.empty(n_bootstraps, dtype=float)
    for index in range(n_bootstraps):
        sample_indices = rng.integers(0, len(frame), len(frame))
        estimates[index] = spearman_rho(x[sample_indices], y[sample_indices])
    return float(np.nanquantile(estimates, 0.025)), float(np.nanquantile(estimates, 0.975))


def classify_effect(abs_rho: float) -> str:
    if pd.isna(abs_rho):
        return "not evaluated"
    if abs_rho < 0.10:
        return "little evidence"
    if abs_rho < 0.30:
        return "weak evidence"
    if abs_rho < 0.50:
        return "moderate evidence"
    return "strong evidence"


def classify_p_value(p_value: float) -> str:
    if pd.isna(p_value):
        return "not evaluated"
    if p_value < 0.001:
        return "p<0.001"
    if p_value < 0.01:
        return "p<0.01"
    if p_value < 0.05:
        return "p<0.05"
    return "not statistically distinguishable at 0.05"


def high_low_contrast(
    values: pd.Series,
    missing_fraction: pd.Series,
    rng: np.random.Generator,
    n_permutations: int = N_PERMUTATIONS,
) -> dict[str, Any]:
    frame = (
        pd.DataFrame({"x": values, "missing_fraction": missing_fraction})
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(frame) < 12:
        return {
            "n_low_days": 0,
            "n_high_days": 0,
            "low_group_missing_pct": np.nan,
            "high_group_missing_pct": np.nan,
            "high_minus_low_missing_pct_points": np.nan,
            "permutation_p_value": np.nan,
        }
    low_cut = frame["x"].quantile(0.25)
    high_cut = frame["x"].quantile(0.75)
    low = frame[frame["x"] <= low_cut]["missing_fraction"].to_numpy(dtype=float) * 100
    high = frame[frame["x"] >= high_cut]["missing_fraction"].to_numpy(dtype=float) * 100
    combined = np.concatenate([low, high])
    labels = np.array([0] * len(low) + [1] * len(high), dtype=int)
    observed = float(high.mean() - low.mean())
    count = 0
    for _ in range(n_permutations):
        permuted_labels = rng.permutation(labels)
        permuted_low = combined[permuted_labels == 0]
        permuted_high = combined[permuted_labels == 1]
        if abs(permuted_high.mean() - permuted_low.mean()) >= abs(observed):
            count += 1
    return {
        "n_low_days": int(len(low)),
        "n_high_days": int(len(high)),
        "low_group_missing_pct": float(low.mean()),
        "high_group_missing_pct": float(high.mean()),
        "high_minus_low_missing_pct_points": observed,
        "permutation_p_value": float((count + 1) / (n_permutations + 1)),
    }


def linear_slope(x_values: pd.Series, y_values: pd.Series) -> tuple[float, float]:
    frame = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan"), float("nan")
    x = frame["x"].to_numpy(dtype=float)
    y = frame["y"].to_numpy(dtype=float) * 100
    x_std = x.std(ddof=0)
    if x_std == 0:
        return float("nan"), float("nan")
    x_standardized = (x - x.mean()) / x_std
    slope = pearson_r(x_standardized, y) * y.std(ddof=0)
    return float(slope), float(x_std)


def build_daily_tests(daily: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["time_index_days"] = daily.groupby("city")["date"].transform(lambda dates: (dates - dates.min()).dt.days)
    records: list[dict[str, Any]] = []
    for city, city_frame in daily.groupby("city", sort=True):
        for variable in DAILY_VARIABLES:
            frame = city_frame[[variable.column, "daily_missing_fraction"]].replace([np.inf, -np.inf], np.nan).dropna()
            ci_low, ci_high = bootstrap_spearman_ci(frame[variable.column], frame["daily_missing_fraction"], rng)
            slope_per_1sd, x_sd = linear_slope(frame[variable.column], frame["daily_missing_fraction"])
            rho = spearman_rho(frame[variable.column], frame["daily_missing_fraction"])
            p_value = permutation_p_value(frame[variable.column], frame["daily_missing_fraction"], rng)
            records.append(
                {
                    "city": city,
                    "domain": variable.domain,
                    "x_variable": variable.label,
                    "y_variable": "daily_missing_fraction",
                    "n_days": int(len(frame)),
                    "pearson_r": pearson_r(frame[variable.column], frame["daily_missing_fraction"]),
                    "spearman_rho": rho,
                    "spearman_ci_low": ci_low,
                    "spearman_ci_high": ci_high,
                    "permutation_p_value": p_value,
                    "effect_strength": classify_effect(abs(rho)),
                    "p_value_flag": classify_p_value(p_value),
                    "slope_missing_pct_points_per_1sd_x": slope_per_1sd,
                    "x_sd": x_sd,
                }
            )
    return pd.DataFrame(records)


def build_high_low_tests(daily: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["time_index_days"] = daily.groupby("city")["date"].transform(lambda dates: (dates - dates.min()).dt.days)
    records: list[dict[str, Any]] = []
    for city, city_frame in daily.groupby("city", sort=True):
        for variable in DAILY_VARIABLES:
            result = high_low_contrast(city_frame[variable.column], city_frame["daily_missing_fraction"], rng)
            records.append(
                {
                    "city": city,
                    "domain": variable.domain,
                    "x_variable": variable.label,
                    **result,
                    "p_value_flag": classify_p_value(result["permutation_p_value"]),
                }
            )
    return pd.DataFrame(records)


def build_monthly_tests(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["month"] = daily["date"].dt.to_period("M").astype(str)
    monthly = (
        daily.groupby(["city", "month"], as_index=False)
        .agg(
            n_days=("date", "size"),
            mean_missing_pct=("daily_missing_fraction", lambda series: float(series.mean() * 100)),
            median_missing_pct=("daily_missing_fraction", lambda series: float(series.median() * 100)),
            mean_pm25_ugm3=("daily_reference_mean_ugm3", "mean"),
            median_pm25_ugm3=("daily_reference_median_ugm3", "median"),
            mean_spatial_cv=("daily_spatial_cv", "mean"),
            zero_valid_sensor_days=("daily_valid_sensor_count", lambda series: int((series == 0).sum())),
        )
    )
    range_records = []
    for city, city_monthly in monthly.groupby("city", sort=True):
        min_row = city_monthly.loc[city_monthly["mean_missing_pct"].idxmin()]
        max_row = city_monthly.loc[city_monthly["mean_missing_pct"].idxmax()]
        range_records.append(
            {
                "city": city,
                "n_months": int(len(city_monthly)),
                "lowest_missing_month": min_row["month"],
                "lowest_month_mean_missing_pct": float(min_row["mean_missing_pct"]),
                "highest_missing_month": max_row["month"],
                "highest_month_mean_missing_pct": float(max_row["mean_missing_pct"]),
                "monthly_missing_range_pct_points": float(
                    max_row["mean_missing_pct"] - min_row["mean_missing_pct"]
                ),
            }
        )
    return monthly, pd.DataFrame(range_records)


def build_sensor_tests(sensor: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    sensor = sensor.copy()
    sensor["record_missing_pct"] = 100 - sensor["record_uptime_pct"]
    sensor["daily_missing_pct"] = 100 - sensor["daily_availability_pct"]
    records: list[dict[str, Any]] = []
    for city, city_frame in sensor.groupby("city", sort=True):
        for y_column, y_label in [
            ("record_missing_pct", "sensor_record_missing_pct"),
            ("daily_missing_pct", "sensor_daily_missing_pct"),
            ("longest_missing_gap_days", "sensor_longest_missing_gap_days"),
        ]:
            for variable in SENSOR_VARIABLES:
                frame = city_frame[[variable.column, y_column]].replace([np.inf, -np.inf], np.nan).dropna()
                rho = spearman_rho(frame[variable.column], frame[y_column])
                p_value = permutation_p_value(frame[variable.column], frame[y_column], rng)
                records.append(
                    {
                        "city": city,
                        "domain": variable.domain,
                        "x_variable": variable.label,
                        "y_variable": y_label,
                        "n_sensors": int(len(frame)),
                        "pearson_r": pearson_r(frame[variable.column], frame[y_column]),
                        "spearman_rho": rho,
                        "permutation_p_value": p_value,
                        "effect_strength": classify_effect(abs(rho)),
                        "p_value_flag": classify_p_value(p_value),
                    }
                )
    return pd.DataFrame(records)


def build_city_summary(
    daily_tests: pd.DataFrame,
    high_low_tests: pd.DataFrame,
    monthly_range: pd.DataFrame,
    sensor_tests: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for city in sorted(daily_tests["city"].unique()):
        city_daily = daily_tests[daily_tests["city"] == city].copy()
        city_daily["abs_spearman_rho"] = city_daily["spearman_rho"].abs()
        strongest_daily = city_daily.sort_values("abs_spearman_rho", ascending=False).iloc[0]

        city_high_low = high_low_tests[high_low_tests["city"] == city].copy()
        city_high_low["abs_contrast"] = city_high_low["high_minus_low_missing_pct_points"].abs()
        strongest_contrast = city_high_low.sort_values("abs_contrast", ascending=False).iloc[0]

        city_sensor = sensor_tests[sensor_tests["city"] == city].copy()
        city_sensor["abs_spearman_rho"] = city_sensor["spearman_rho"].abs()
        strongest_sensor = city_sensor.sort_values("abs_spearman_rho", ascending=False).iloc[0]

        month = monthly_range[monthly_range["city"] == city].iloc[0]
        rows.append(
            {
                "city": city,
                "strongest_daily_domain": strongest_daily["domain"],
                "strongest_daily_variable": strongest_daily["x_variable"],
                "strongest_daily_spearman_rho": strongest_daily["spearman_rho"],
                "strongest_daily_p_value": strongest_daily["permutation_p_value"],
                "strongest_daily_effect_strength": strongest_daily["effect_strength"],
                "largest_high_low_variable": strongest_contrast["x_variable"],
                "largest_high_low_missing_pct_point_difference": strongest_contrast[
                    "high_minus_low_missing_pct_points"
                ],
                "largest_high_low_p_value": strongest_contrast["permutation_p_value"],
                "monthly_missing_range_pct_points": month["monthly_missing_range_pct_points"],
                "highest_missing_month": month["highest_missing_month"],
                "strongest_sensor_variable": strongest_sensor["x_variable"],
                "strongest_sensor_y": strongest_sensor["y_variable"],
                "strongest_sensor_spearman_rho": strongest_sensor["spearman_rho"],
                "strongest_sensor_p_value": strongest_sensor["permutation_p_value"],
            }
        )
    return pd.DataFrame(rows)


def markdown_table(frame: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> str:
    display = frame[columns].copy()
    if max_rows is not None:
        display = display.head(max_rows)
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def write_report(
    city_summary: pd.DataFrame,
    daily_tests: pd.DataFrame,
    high_low_tests: pd.DataFrame,
    monthly_range: pd.DataFrame,
    sensor_tests: pd.DataFrame,
) -> None:
    strongest_daily = (
        daily_tests.assign(abs_spearman_rho=daily_tests["spearman_rho"].abs())
        .sort_values(["city", "abs_spearman_rho"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(2)
    )
    strongest_sensor = (
        sensor_tests.assign(abs_spearman_rho=sensor_tests["spearman_rho"].abs())
        .sort_values(["city", "abs_spearman_rho"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(2)
    )
    strongest_contrast = (
        high_low_tests.assign(abs_contrast=high_low_tests["high_minus_low_missing_pct_points"].abs())
        .sort_values(["city", "abs_contrast"], ascending=[True, False])
        .groupby("city", as_index=False)
        .head(2)
    )

    lines = [
        "# Missingness Follow-Up Tests",
        "",
        "## Interpretation",
        "",
        "Weak evidence of non-random missingness means the missing-data fraction has a small observed association with measured daily conditions, such as PM2.5 concentration, spatial variability, or calendar time. It does not prove a missing-not-at-random mechanism, and it does not prove that the final Monte Carlo conclusions are biased. It means we should avoid claiming missing completely at random and should keep sensitivity analyses in the manuscript workflow.",
        "",
        "The tests below use observed data only. They cannot test dependence on unobserved PM2.5 values on days when a sensor is missing.",
        "",
        "## City-Level Summary",
        "",
        markdown_table(
            city_summary,
            [
                "city",
                "strongest_daily_domain",
                "strongest_daily_variable",
                "strongest_daily_spearman_rho",
                "strongest_daily_p_value",
                "strongest_daily_effect_strength",
                "largest_high_low_variable",
                "largest_high_low_missing_pct_point_difference",
                "monthly_missing_range_pct_points",
                "highest_missing_month",
            ],
        ),
        "",
        "## Strongest Daily Association Screens",
        "",
        markdown_table(
            strongest_daily,
            [
                "city",
                "domain",
                "x_variable",
                "n_days",
                "spearman_rho",
                "spearman_ci_low",
                "spearman_ci_high",
                "permutation_p_value",
                "effect_strength",
                "slope_missing_pct_points_per_1sd_x",
            ],
        ),
        "",
        "## High-Versus-Low Day Contrasts",
        "",
        "This compares mean missingness on top-quartile versus bottom-quartile days for each domain variable.",
        "",
        markdown_table(
            strongest_contrast,
            [
                "city",
                "domain",
                "x_variable",
                "low_group_missing_pct",
                "high_group_missing_pct",
                "high_minus_low_missing_pct_points",
                "permutation_p_value",
            ],
        ),
        "",
        "## Monthly Missingness Range",
        "",
        markdown_table(
            monthly_range,
            [
                "city",
                "n_months",
                "lowest_missing_month",
                "lowest_month_mean_missing_pct",
                "highest_missing_month",
                "highest_month_mean_missing_pct",
                "monthly_missing_range_pct_points",
            ],
        ),
        "",
        "## Strongest Sensor-Level Screens",
        "",
        markdown_table(
            strongest_sensor,
            [
                "city",
                "domain",
                "x_variable",
                "y_variable",
                "n_sensors",
                "spearman_rho",
                "permutation_p_value",
                "effect_strength",
            ],
        ),
        "",
        "## Output Files",
        "",
        "- `missingness_followup_city_summary.csv`",
        "- `missingness_followup_daily_permutation_tests.csv`",
        "- `missingness_followup_high_low_contrasts.csv`",
        "- `missingness_followup_monthly_summary.csv`",
        "- `missingness_followup_monthly_range.csv`",
        "- `missingness_followup_sensor_level_tests.csv`",
        "- `missingness_followup_tests.md`",
    ]
    (OUTPUT_DIR / "missingness_followup_tests.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    daily = pd.read_csv(INPUT_DIR / "comparative_daily_city_metrics.csv")
    sensor = pd.read_csv(INPUT_DIR / "comparative_sensor_level_summary.csv")

    daily_tests = build_daily_tests(daily, rng)
    high_low_tests = build_high_low_tests(daily, rng)
    monthly_summary, monthly_range = build_monthly_tests(daily)
    sensor_tests = build_sensor_tests(sensor, rng)
    city_summary = build_city_summary(daily_tests, high_low_tests, monthly_range, sensor_tests)

    outputs = {
        "missingness_followup_city_summary.csv": city_summary,
        "missingness_followup_daily_permutation_tests.csv": daily_tests,
        "missingness_followup_high_low_contrasts.csv": high_low_tests,
        "missingness_followup_monthly_summary.csv": monthly_summary,
        "missingness_followup_monthly_range.csv": monthly_range,
        "missingness_followup_sensor_level_tests.csv": sensor_tests,
    }
    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)

    metadata = {
        "purpose": "Follow-up observed-data missingness diagnostics for Dhaka, Lucknow, and Chicago.",
        "random_seed": RANDOM_SEED,
        "n_permutations": N_PERMUTATIONS,
        "n_bootstraps": N_BOOTSTRAPS,
        "input_dir": str(INPUT_DIR.relative_to(REPO_ROOT)),
        "outputs": sorted([*outputs.keys(), "missingness_followup_tests.md"]),
        "important_limitation": "These are observed-data association tests; they do not prove or disprove formal missing-at-random assumptions.",
    }
    (OUTPUT_DIR / "missingness_followup_metadata.json").write_text(json.dumps(metadata, indent=2))
    write_report(city_summary, daily_tests, high_low_tests, monthly_range, sensor_tests)
    print(f"Wrote missingness follow-up tests to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(city_summary.to_string(index=False))


if __name__ == "__main__":
    main()
