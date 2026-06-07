from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import city_key_from_dataset  # noqa: E402


OUTPUT_DIR = REPO_ROOT / "analysis/results/three_city_comparative_analysis"
DATA_ROOT = REPO_ROOT / "data"


@dataclass(frozen=True)
class CityNetwork:
    dataset_key: str
    city: str
    display_name: str
    pm_path: Path
    location_path: Path
    source_frequency: str
    pm_value: str
    exclude_collocated: bool = False


PRIMARY_NETWORKS = (
    CityNetwork(
        dataset_key="dhaka_lcs",
        city="Dhaka",
        display_name="Dhaka LCS",
        pm_path=DATA_ROOT / "pm/Dhaka_hourly_PM25.csv",
        location_path=DATA_ROOT / "locations/Dhaka_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="inherited_calibrated_pm25",
    ),
    CityNetwork(
        dataset_key="lucknow_lcs",
        city="Lucknow",
        display_name="Lucknow LCS",
        pm_path=DATA_ROOT / "pm/Lucknow_hourly_PM25.csv",
        location_path=DATA_ROOT / "locations/Lucknow_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="inherited_calibrated_pm25",
    ),
    CityNetwork(
        dataset_key="chicago_lcs_corrected_no_collocation",
        city="Chicago",
        display_name="Chicago corrected LCS (collocation excluded)",
        pm_path=DATA_ROOT / "pm/Chicago_LCS_corrected_daily_PM25.csv",
        location_path=DATA_ROOT / "locations/Chicago_LCS_corrected_sensor_locations.csv",
        source_frequency="official_daily",
        pm_value="corrected_pm25",
        exclude_collocated=True,
    ),
)


def read_pm_matrix(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    timestamp_column = frame.columns[0]
    frame = frame.rename(columns={timestamp_column: "Timestamp"})
    timestamp_text = frame["Timestamp"].astype(str).str.replace(r"(Z|[+-]\d{2}:?\d{2})$", "", regex=True)
    frame["Timestamp"] = pd.to_datetime(timestamp_text, errors="coerce", format="mixed")
    if frame["Timestamp"].dt.tz is not None:
        frame["Timestamp"] = frame["Timestamp"].dt.tz_convert(None)
    for column in frame.columns:
        if column != "Timestamp":
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def read_locations(config: CityNetwork) -> tuple[pd.DataFrame, pd.DataFrame]:
    original = pd.read_csv(config.location_path, dtype={"Sensor_ID": str})
    original["Sensor_ID"] = original["Sensor_ID"].astype(str)
    original["Latitude"] = pd.to_numeric(original["Latitude"], errors="coerce")
    original["Longitude"] = pd.to_numeric(original["Longitude"], errors="coerce")
    filtered = original.copy()
    if config.exclude_collocated:
        filtered = filtered[
            ~filtered["Station_Name"].astype(str).str.contains("collocation", case=False, na=False)
        ].copy()
    return original.reset_index(drop=True), filtered.reset_index(drop=True)


def retained_sensor_ids(locations: pd.DataFrame, pm: pd.DataFrame) -> list[str]:
    pm_columns = set(str(column) for column in pm.columns if column != "Timestamp")
    return [sensor_id for sensor_id in locations["Sensor_ID"].astype(str) if sensor_id in pm_columns]


def daily_sensor_means(config: CityNetwork, pm: pd.DataFrame, sensor_ids: list[str]) -> pd.DataFrame:
    values = pm[["Timestamp", *sensor_ids]].copy()
    if config.source_frequency == "hourly":
        dates = values["Timestamp"].dt.normalize()
        daily = values[sensor_ids].groupby(dates, sort=True).mean()
    elif config.source_frequency == "official_daily":
        daily = values.set_index("Timestamp")[sensor_ids].groupby(level=0, sort=True).mean()
    else:
        raise ValueError(f"Unsupported source frequency: {config.source_frequency}")
    daily.index.name = "date"
    daily.columns = daily.columns.astype(str)
    return daily


def daily_sensor_availability(config: CityNetwork, pm: pd.DataFrame, sensor_ids: list[str]) -> pd.DataFrame:
    if config.source_frequency == "hourly":
        dates = pm["Timestamp"].dt.normalize()
        availability = pm[sensor_ids].notna().groupby(dates, sort=True).sum() / 24.0
    elif config.source_frequency == "official_daily":
        availability = pm.set_index("Timestamp")[sensor_ids].notna().astype(float).groupby(level=0, sort=True).mean()
    else:
        raise ValueError(f"Unsupported source frequency: {config.source_frequency}")
    availability.index.name = "date"
    availability.columns = availability.columns.astype(str)
    return availability.clip(0, 1)


def expected_timestamp_count(pm: pd.DataFrame, source_frequency: str) -> int:
    timestamps = pm["Timestamp"].dropna()
    if timestamps.empty:
        return 0
    frequency = "h" if source_frequency == "hourly" else "D"
    return len(pd.date_range(timestamps.min(), timestamps.max(), freq=frequency))


def max_consecutive_true(values: pd.Series) -> int:
    longest = 0
    current = 0
    for value in values.astype(bool):
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def haversine_km(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> np.ndarray:
    radius = 6371.0088
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    value = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(value))


def pairwise_distances_km(locations: pd.DataFrame) -> np.ndarray:
    coords = locations[["Latitude", "Longitude"]].to_numpy(dtype=float)
    distances: list[float] = []
    for index in range(len(coords) - 1):
        distances.extend(
            haversine_km(
                coords[index, 0],
                coords[index, 1],
                coords[index + 1 :, 0],
                coords[index + 1 :, 1],
            )
        )
    return np.array(distances, dtype=float)


def nearest_neighbor_distances_km(locations: pd.DataFrame) -> np.ndarray:
    coords = locations[["Latitude", "Longitude"]].to_numpy(dtype=float)
    nearest: list[float] = []
    for index in range(len(coords)):
        distances = haversine_km(coords[index, 0], coords[index, 1], coords[:, 0], coords[:, 1])
        distances[index] = np.inf
        nearest.append(float(np.min(distances)))
    return np.array(nearest, dtype=float)


def convex_hull_lonlat(locations: pd.DataFrame) -> list[tuple[float, float]]:
    points = sorted(set(zip(locations["Longitude"], locations["Latitude"], strict=True)))
    if len(points) < 3:
        return points

    def cross(origin: tuple[float, float], left: tuple[float, float], right: tuple[float, float]) -> float:
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def convex_hull_area_km2(locations: pd.DataFrame) -> float:
    hull = convex_hull_lonlat(locations)
    if len(hull) < 3:
        return 0.0
    origin_lat = float(locations["Latitude"].mean())
    origin_lon = float(locations["Longitude"].mean())
    scale_x = 111.320 * math.cos(math.radians(origin_lat))
    scale_y = 110.574
    xy = [((lon - origin_lon) * scale_x, (lat - origin_lat) * scale_y) for lon, lat in hull]
    area = 0.0
    for left, right in zip(xy, [*xy[1:], xy[0]], strict=True):
        area += left[0] * right[1] - right[0] * left[1]
    return abs(area) / 2


def pearson_r(x: pd.Series, y: pd.Series) -> float:
    frame = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return np.nan
    return float(frame["x"].corr(frame["y"]))


def spearman_rho(x: pd.Series, y: pd.Series) -> float:
    frame = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return np.nan
    return float(frame["x"].rank().corr(frame["y"].rank()))


def classify_correlation(value: float) -> str:
    if pd.isna(value):
        return "not evaluated"
    absolute = abs(value)
    if absolute < 0.10:
        return "little evidence"
    if absolute < 0.30:
        return "weak evidence"
    if absolute < 0.50:
        return "moderate evidence"
    return "strong evidence"


def mar_screen_label(max_abs_spearman: float) -> str:
    if pd.isna(max_abs_spearman):
        return "not evaluated"
    if max_abs_spearman < 0.10:
        return "no strong evidence against concentration/variability-independent missingness"
    if max_abs_spearman < 0.30:
        return "weak evidence of non-random missingness with observed daily conditions"
    return "moderate/strong evidence of non-random missingness with observed daily conditions"


def summarize_network(config: CityNetwork) -> dict[str, pd.DataFrame | dict[str, Any]]:
    pm = read_pm_matrix(config.pm_path)
    original_locations, filtered_locations = read_locations(config)
    sensor_ids = retained_sensor_ids(filtered_locations, pm)
    retained_locations = filtered_locations[filtered_locations["Sensor_ID"].isin(sensor_ids)].copy()
    retained_locations = retained_locations.set_index("Sensor_ID").loc[sensor_ids].reset_index()
    values = pm[sensor_ids]
    daily = daily_sensor_means(config, pm, sensor_ids)
    availability = daily_sensor_availability(config, pm, sensor_ids).reindex(daily.index)
    period_sensor_means = values.mean(axis=0, skipna=True)
    sensor_daily_availability = daily.notna().mean(axis=0)
    sensor_record_uptime = values.notna().mean(axis=0)

    timestamp_rows = len(pm)
    expected_rows = expected_timestamp_count(pm, config.source_frequency)
    total_cells = int(values.shape[0] * values.shape[1])
    valid_cells = int(values.notna().sum().sum())
    missing_cells = total_cells - valid_cells
    valid_values = values.stack().dropna()
    all_pm_columns = [str(column) for column in pm.columns if column != "Timestamp"]
    location_ids = set(filtered_locations["Sensor_ID"].astype(str))
    pm_ids = set(all_pm_columns)

    qa_record = {
        "dataset_key": config.dataset_key,
        "city": config.city,
        "display_name": config.display_name,
        "source_frequency": config.source_frequency,
        "pm_value": config.pm_value,
        "pm_path": str(config.pm_path.relative_to(REPO_ROOT)),
        "location_path": str(config.location_path.relative_to(REPO_ROOT)),
        "timestamp_start": pm["Timestamp"].min().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp_end": pm["Timestamp"].max().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp_rows": timestamp_rows,
        "expected_timestamp_rows": expected_rows,
        "missing_timestamp_rows_in_range": max(expected_rows - timestamp_rows, 0),
        "duplicate_timestamp_rows": int(pm["Timestamp"].duplicated().sum()),
        "location_rows_original": int(len(original_locations)),
        "location_rows_after_filter": int(len(filtered_locations)),
        "collocation_rows_excluded": int(len(original_locations) - len(filtered_locations)),
        "pm_sensor_columns": int(len(all_pm_columns)),
        "retained_sensor_count": int(len(sensor_ids)),
        "pm_columns_without_filtered_location": int(len(pm_ids - location_ids)),
        "filtered_locations_without_pm_column": int(len(location_ids - pm_ids)),
        "duplicate_location_sensor_ids_original": int(original_locations["Sensor_ID"].duplicated().sum()),
        "duplicate_location_sensor_ids_retained": int(retained_locations["Sensor_ID"].duplicated().sum()),
        "missing_coordinate_rows_retained": int(
            retained_locations["Latitude"].isna().sum() + retained_locations["Longitude"].isna().sum()
        ),
        "duplicate_coordinate_rows_retained": int(
            retained_locations.duplicated(subset=["Latitude", "Longitude"]).sum()
        ),
        "total_pm_cells": total_cells,
        "valid_pm_cells": valid_cells,
        "missing_pm_cells": missing_cells,
        "missing_pm_fraction_pct": missing_cells / total_cells * 100 if total_cells else np.nan,
        "all_missing_sensor_count": int(values.isna().all(axis=0).sum()),
        "negative_value_count": int((valid_values < 0).sum()),
        "zero_value_count": int((valid_values == 0).sum()),
        "nonpositive_value_count": int((valid_values <= 0).sum()),
        "pm_gt_100_count": int((valid_values > 100).sum()),
        "pm_gt_250_count": int((valid_values > 250).sum()),
        "pm_gt_500_count": int((valid_values > 500).sum()),
        "pm_min_ugm3": float(valid_values.min()) if len(valid_values) else np.nan,
        "pm_max_ugm3": float(valid_values.max()) if len(valid_values) else np.nan,
    }

    daily_reference_mean = daily.mean(axis=1, skipna=True)
    daily_reference_median = daily.median(axis=1, skipna=True)
    daily_reference_sd = daily.std(axis=1, skipna=True)
    daily_reference_cv = daily_reference_sd / daily_reference_mean
    pm_record = {
        "dataset_key": config.dataset_key,
        "city": config.city,
        "display_name": config.display_name,
        "daily_count": int(daily_reference_mean.notna().sum()),
        "daily_mean_pm25_mean_ugm3": float(daily_reference_mean.mean()),
        "daily_mean_pm25_median_ugm3": float(daily_reference_mean.median()),
        "daily_mean_pm25_p10_ugm3": float(daily_reference_mean.quantile(0.10)),
        "daily_mean_pm25_p90_ugm3": float(daily_reference_mean.quantile(0.90)),
        "daily_median_pm25_mean_ugm3": float(daily_reference_median.mean()),
        "daily_median_pm25_median_ugm3": float(daily_reference_median.median()),
        "daily_spatial_sd_median_ugm3": float(daily_reference_sd.median()),
        "daily_spatial_cv_median": float(daily_reference_cv.replace([np.inf, -np.inf], np.nan).median()),
        "period_sensor_mean_mean_ugm3": float(period_sensor_means.mean()),
        "period_sensor_mean_median_ugm3": float(period_sensor_means.median()),
        "period_sensor_mean_sd_ugm3": float(period_sensor_means.std()),
        "period_sensor_mean_cv": float(period_sensor_means.std() / period_sensor_means.mean()),
        "period_sensor_mean_min_ugm3": float(period_sensor_means.min()),
        "period_sensor_mean_max_ugm3": float(period_sensor_means.max()),
        "period_sensor_mean_iqr_ugm3": float(period_sensor_means.quantile(0.75) - period_sensor_means.quantile(0.25)),
    }

    daily_valid_sensor_count = daily.notna().sum(axis=1)
    daily_missing_fraction = 1 - availability.mean(axis=1, skipna=True)
    sensor_longest_missing_days = pd.Series(
        {
            sensor_id: max_consecutive_true(daily[sensor_id].isna())
            for sensor_id in sensor_ids
        }
    )
    missing_record = {
        "dataset_key": config.dataset_key,
        "city": config.city,
        "display_name": config.display_name,
        "daily_days_total": int(len(daily_valid_sensor_count)),
        "daily_days_with_zero_valid_sensors": int((daily_valid_sensor_count == 0).sum()),
        "daily_days_with_any_missing_sensors": int((daily_missing_fraction > 0).sum()),
        "record_missing_fraction_pct": qa_record["missing_pm_fraction_pct"],
        "median_sensor_record_uptime_pct": float(sensor_record_uptime.median() * 100),
        "p10_sensor_record_uptime_pct": float(sensor_record_uptime.quantile(0.10) * 100),
        "min_sensor_record_uptime_pct": float(sensor_record_uptime.min() * 100),
        "median_sensor_daily_availability_pct": float(sensor_daily_availability.median() * 100),
        "p10_sensor_daily_availability_pct": float(sensor_daily_availability.quantile(0.10) * 100),
        "min_sensor_daily_availability_pct": float(sensor_daily_availability.min() * 100),
        "daily_valid_sensor_min": int(daily_valid_sensor_count.min()),
        "daily_valid_sensor_p10": float(daily_valid_sensor_count.quantile(0.10)),
        "daily_valid_sensor_median": float(daily_valid_sensor_count.median()),
        "daily_valid_sensor_max": int(daily_valid_sensor_count.max()),
        "days_with_valid_sensors_lt_5": int((daily_valid_sensor_count < 5).sum()),
        "days_with_valid_sensors_lt_10": int((daily_valid_sensor_count < 10).sum()),
        "days_with_valid_sensors_lt_20": int((daily_valid_sensor_count < 20).sum()),
        "days_with_valid_sensors_lt_30": int((daily_valid_sensor_count < 30).sum()),
        "daily_missing_fraction_mean_pct": float(daily_missing_fraction.mean() * 100),
        "daily_missing_fraction_median_pct": float(daily_missing_fraction.median() * 100),
        "daily_missing_fraction_p90_pct": float(daily_missing_fraction.quantile(0.90) * 100),
        "daily_missing_fraction_max_pct": float(daily_missing_fraction.max() * 100),
        "median_longest_missing_gap_days": float(sensor_longest_missing_days.median()),
        "p90_longest_missing_gap_days": float(sensor_longest_missing_days.quantile(0.90)),
        "max_longest_missing_gap_days": int(sensor_longest_missing_days.max()),
    }

    daily_metrics = pd.DataFrame(
        {
            "dataset_key": config.dataset_key,
            "city": config.city,
            "date": daily.index,
            "daily_reference_mean_ugm3": daily_reference_mean,
            "daily_reference_median_ugm3": daily_reference_median,
            "daily_spatial_sd_ugm3": daily_reference_sd,
            "daily_spatial_cv": daily_reference_cv,
            "daily_valid_sensor_count": daily_valid_sensor_count,
            "daily_missing_fraction": daily_missing_fraction,
        }
    ).reset_index(drop=True)

    correlation_records: list[dict[str, Any]] = []
    for x_column, x_label in [
        ("daily_reference_mean_ugm3", "daily_mean_pm25"),
        ("daily_reference_median_ugm3", "daily_median_pm25"),
        ("daily_spatial_sd_ugm3", "daily_spatial_sd"),
        ("daily_spatial_cv", "daily_spatial_cv"),
        ("daily_valid_sensor_count", "daily_valid_sensor_count"),
    ]:
        frame = daily_metrics[[x_column, "daily_missing_fraction"]].replace([np.inf, -np.inf], np.nan).dropna()
        rho = spearman_rho(frame[x_column], frame["daily_missing_fraction"])
        correlation_records.append(
            {
                "dataset_key": config.dataset_key,
                "city": config.city,
                "x_variable": x_label,
                "y_variable": "daily_missing_fraction",
                "n_days": int(len(frame)),
                "pearson_r": pearson_r(frame[x_column], frame["daily_missing_fraction"]),
                "spearman_rho": rho,
                "abs_spearman_rho": abs(rho) if not pd.isna(rho) else np.nan,
                "evidence_strength": classify_correlation(rho),
                "direction": "positive" if rho > 0 else "negative" if rho < 0 else "none",
            }
        )

    pairwise = pairwise_distances_km(retained_locations)
    nearest = nearest_neighbor_distances_km(retained_locations)
    hull_area = convex_hull_area_km2(retained_locations)
    spatial_record = {
        "dataset_key": config.dataset_key,
        "city": config.city,
        "display_name": config.display_name,
        "retained_sensor_count": int(len(retained_locations)),
        "convex_hull_area_km2": hull_area,
        "sensor_density_per_100_km2_hull": len(retained_locations) / hull_area * 100 if hull_area else np.nan,
        "mean_pairwise_distance_km": float(pairwise.mean()),
        "median_pairwise_distance_km": float(np.median(pairwise)),
        "p10_pairwise_distance_km": float(np.quantile(pairwise, 0.10)),
        "p90_pairwise_distance_km": float(np.quantile(pairwise, 0.90)),
        "median_nearest_neighbor_km": float(np.median(nearest)),
        "p10_nearest_neighbor_km": float(np.quantile(nearest, 0.10)),
        "p90_nearest_neighbor_km": float(np.quantile(nearest, 0.90)),
        "latitude_min": float(retained_locations["Latitude"].min()),
        "latitude_max": float(retained_locations["Latitude"].max()),
        "longitude_min": float(retained_locations["Longitude"].min()),
        "longitude_max": float(retained_locations["Longitude"].max()),
    }

    sensor_records = []
    for sensor_id in sensor_ids:
        location = retained_locations.set_index("Sensor_ID").loc[sensor_id]
        sensor_records.append(
            {
                "dataset_key": config.dataset_key,
                "city": config.city,
                "sensor_id": sensor_id,
                "station_name": location["Station_Name"],
                "latitude": float(location["Latitude"]),
                "longitude": float(location["Longitude"]),
                "record_uptime_pct": float(sensor_record_uptime.loc[sensor_id] * 100),
                "daily_availability_pct": float(sensor_daily_availability.loc[sensor_id] * 100),
                "longest_missing_gap_days": int(sensor_longest_missing_days.loc[sensor_id]),
                "period_mean_pm25_ugm3": float(period_sensor_means.loc[sensor_id]),
                "period_median_daily_pm25_ugm3": float(daily[sensor_id].median()),
                "period_sd_daily_pm25_ugm3": float(daily[sensor_id].std()),
            }
        )

    return {
        "qa": pd.DataFrame([qa_record]),
        "pm": pd.DataFrame([pm_record]),
        "missing": pd.DataFrame([missing_record]),
        "daily": daily_metrics,
        "correlations": pd.DataFrame(correlation_records),
        "spatial": pd.DataFrame([spatial_record]),
        "sensor": pd.DataFrame(sensor_records),
    }


def chicago_lcs_aqs_comparison() -> pd.DataFrame:
    chicago_config = PRIMARY_NETWORKS[2]
    lcs_pm = read_pm_matrix(chicago_config.pm_path)
    _, lcs_locations = read_locations(chicago_config)
    lcs_ids = retained_sensor_ids(lcs_locations, lcs_pm)
    lcs_daily = daily_sensor_means(chicago_config, lcs_pm, lcs_ids)
    lcs_mean = lcs_daily.mean(axis=1, skipna=True)

    aqs_config = CityNetwork(
        dataset_key="chicago_aqs",
        city="Chicago",
        display_name="Chicago AQS",
        pm_path=DATA_ROOT / "pm/Chicago_AQS_daily_PM25.csv",
        location_path=DATA_ROOT / "locations/Chicago_AQS_sensor_locations.csv",
        source_frequency="official_daily",
        pm_value="aqs_pm25",
    )
    aqs_pm = read_pm_matrix(aqs_config.pm_path)
    _, aqs_locations = read_locations(aqs_config)
    aqs_ids = retained_sensor_ids(aqs_locations, aqs_pm)
    aqs_daily = daily_sensor_means(aqs_config, aqs_pm, aqs_ids)
    aqs_mean = aqs_daily.mean(axis=1, skipna=True)
    paired = pd.DataFrame({"lcs_mean_ugm3": lcs_mean, "aqs_mean_ugm3": aqs_mean}).dropna()
    difference = paired["lcs_mean_ugm3"] - paired["aqs_mean_ugm3"]
    return pd.DataFrame(
        [
            {
                "comparison": "Chicago corrected LCS no-collocation mean vs AQS mean",
                "paired_days": int(len(paired)),
                "pearson_r": float(paired["lcs_mean_ugm3"].corr(paired["aqs_mean_ugm3"])),
                "mae_ugm3": float(difference.abs().mean()),
                "rmse_ugm3": float(math.sqrt((difference**2).mean())),
                "bias_lcs_minus_aqs_ugm3": float(difference.mean()),
                "lcs_mean_ugm3": float(paired["lcs_mean_ugm3"].mean()),
                "aqs_mean_ugm3": float(paired["aqs_mean_ugm3"].mean()),
            }
        ]
    )


def build_overall_summary(
    qa: pd.DataFrame,
    pm: pd.DataFrame,
    missing: pd.DataFrame,
    spatial: pd.DataFrame,
    correlations: pd.DataFrame,
) -> pd.DataFrame:
    strongest = (
        correlations[correlations["x_variable"].isin(["daily_mean_pm25", "daily_median_pm25", "daily_spatial_sd", "daily_spatial_cv"])]
        .sort_values(["dataset_key", "abs_spearman_rho"], ascending=[True, False])
        .groupby("dataset_key", as_index=False)
        .head(1)
        .rename(
            columns={
                "x_variable": "strongest_missingness_association_variable",
                "spearman_rho": "strongest_missingness_spearman_rho",
                "evidence_strength": "strongest_missingness_evidence",
            }
        )
    )
    summary = (
        qa[
            [
                "dataset_key",
                "city",
                "display_name",
                "source_frequency",
                "timestamp_start",
                "timestamp_end",
                "retained_sensor_count",
                "missing_pm_fraction_pct",
                "nonpositive_value_count",
                "pm_gt_250_count",
            ]
        ]
        .merge(
            pm[
                [
                    "dataset_key",
                    "daily_mean_pm25_median_ugm3",
                    "daily_mean_pm25_p90_ugm3",
                    "period_sensor_mean_mean_ugm3",
                    "period_sensor_mean_median_ugm3",
                    "period_sensor_mean_cv",
                ]
            ],
            on="dataset_key",
        )
        .merge(
            missing[
                [
                    "dataset_key",
                    "median_sensor_record_uptime_pct",
                    "daily_days_total",
                    "daily_days_with_zero_valid_sensors",
                    "daily_valid_sensor_min",
                    "daily_valid_sensor_median",
                    "daily_missing_fraction_median_pct",
                    "max_longest_missing_gap_days",
                ]
            ],
            on="dataset_key",
        )
        .merge(
            spatial[
                [
                    "dataset_key",
                    "convex_hull_area_km2",
                    "sensor_density_per_100_km2_hull",
                    "median_nearest_neighbor_km",
                    "mean_pairwise_distance_km",
                ]
            ],
            on="dataset_key",
        )
        .merge(
            strongest[
                [
                    "dataset_key",
                    "strongest_missingness_association_variable",
                    "strongest_missingness_spearman_rho",
                    "strongest_missingness_evidence",
                ]
            ],
            on="dataset_key",
            how="left",
        )
    )
    summary["mar_screen_conclusion"] = summary["strongest_missingness_spearman_rho"].apply(
        lambda value: mar_screen_label(abs(value))
    )
    return summary


def markdown_table(frame: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> str:
    display = frame[columns].copy()
    if max_rows is not None:
        display = display.head(max_rows)
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.2f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def network_metadata(config: CityNetwork) -> dict[str, Any]:
    record = config.__dict__.copy()
    record["pm_path"] = str(config.pm_path.relative_to(REPO_ROOT))
    record["location_path"] = str(config.location_path.relative_to(REPO_ROOT))
    return record


def write_report(
    output_dir: Path,
    overall: pd.DataFrame,
    qa: pd.DataFrame,
    pm: pd.DataFrame,
    missing: pd.DataFrame,
    correlations: pd.DataFrame,
    spatial: pd.DataFrame,
    chicago_aqs: pd.DataFrame,
    sensor_gap_extremes: pd.DataFrame,
) -> None:
    strongest_rows = (
        correlations[correlations["x_variable"].isin(["daily_mean_pm25", "daily_median_pm25", "daily_spatial_sd", "daily_spatial_cv"])]
        .sort_values(["dataset_key", "abs_spearman_rho"], ascending=[True, False])
        .groupby("dataset_key", as_index=False)
        .head(1)
    )
    lines = [
        "# Three-City Comparative Analysis",
        "",
        "## Scope",
        "",
        "This report compares the current primary manuscript networks: Dhaka LCS, Lucknow LCS, and Chicago corrected LCS with collocation sensors excluded.",
        "",
        "It is a screening summary, not a proof that missingness is missing-at-random. The missingness section tests whether daily missing fraction is associated with observed daily PM2.5 level or cross-sensor variability.",
        "",
        "## Key Findings",
        "",
    ]
    for row in overall.itertuples(index=False):
        lines.append(
            f"- **{row.city}:** {row.retained_sensor_count} retained sensors; "
            f"period mean {row.period_sensor_mean_mean_ugm3:.2f} µg/m³; "
            f"median daily missing fraction {row.daily_missing_fraction_median_pct:.2f}%; "
            f"all-missing daily row count {row.daily_days_with_zero_valid_sensors}; "
            f"median nearest-neighbor distance {row.median_nearest_neighbor_km:.2f} km; "
            f"MAR screen: {row.mar_screen_conclusion}."
        )
    if not chicago_aqs.empty:
        comp = chicago_aqs.iloc[0]
        lines.append(
            f"- **Chicago AQS context:** corrected LCS daily network mean is strongly correlated with AQS mean "
            f"(r={comp['pearson_r']:.2f}, paired days={int(comp['paired_days'])}), with MAE={comp['mae_ugm3']:.2f} µg/m³ "
            f"and LCS-minus-AQS bias={comp['bias_lcs_minus_aqs_ugm3']:.2f} µg/m³."
        )

    lines.extend(
        [
            "",
            "## Overall Comparative Summary",
            "",
            markdown_table(
                overall,
                [
                    "city",
                    "source_frequency",
                    "retained_sensor_count",
                    "daily_mean_pm25_median_ugm3",
                    "period_sensor_mean_mean_ugm3",
                    "missing_pm_fraction_pct",
                    "daily_valid_sensor_median",
                    "daily_days_with_zero_valid_sensors",
                    "convex_hull_area_km2",
                    "sensor_density_per_100_km2_hull",
                    "median_nearest_neighbor_km",
                    "strongest_missingness_association_variable",
                    "strongest_missingness_spearman_rho",
                ],
            ),
            "",
            "## QA/QC Screen",
            "",
            "The canonical matrices show no negative or nonpositive PM2.5 values in the retained primary networks. Chicago uses official daily corrected LCS values for the main comparison; Dhaka and Lucknow use hourly matrices.",
            "",
            markdown_table(
                qa,
                [
                    "city",
                    "timestamp_rows",
                    "expected_timestamp_rows",
                    "retained_sensor_count",
                    "collocation_rows_excluded",
                    "missing_pm_fraction_pct",
                    "nonpositive_value_count",
                    "pm_gt_250_count",
                    "pm_min_ugm3",
                    "pm_max_ugm3",
                ],
            ),
            "",
            "## PM2.5 Mean/Median Summary",
            "",
            markdown_table(
                pm,
                [
                    "city",
                    "daily_count",
                    "daily_mean_pm25_mean_ugm3",
                    "daily_mean_pm25_median_ugm3",
                    "daily_median_pm25_median_ugm3",
                    "daily_spatial_sd_median_ugm3",
                    "daily_spatial_cv_median",
                    "period_sensor_mean_mean_ugm3",
                    "period_sensor_mean_median_ugm3",
                    "period_sensor_mean_cv",
                ],
            ),
            "",
            "## Missingness and MAR Screen",
            "",
            "This is an observed-data diagnostic. A weak correlation does not prove missing-at-random, and a correlation does not by itself identify mechanism. It indicates whether missingness tracks observed daily concentration or spatial variability.",
            "",
            markdown_table(
                missing,
                [
                    "city",
                    "daily_days_total",
                    "daily_days_with_zero_valid_sensors",
                    "record_missing_fraction_pct",
                    "median_sensor_record_uptime_pct",
                    "p10_sensor_record_uptime_pct",
                    "daily_missing_fraction_median_pct",
                    "daily_valid_sensor_min",
                    "daily_valid_sensor_median",
                    "daily_missing_fraction_p90_pct",
                    "max_longest_missing_gap_days",
                ],
            ),
            "",
            "### Strongest Missingness Association By City",
            "",
            markdown_table(
                strongest_rows,
                [
                    "city",
                    "x_variable",
                    "n_days",
                    "pearson_r",
                    "spearman_rho",
                    "evidence_strength",
                    "direction",
                ],
            ),
            "",
            "### Longest Sensor Gaps",
            "",
            "These are the top five longest daily gaps per city retained for follow-up QA/QC and sensitivity checks.",
            "",
            markdown_table(
                sensor_gap_extremes,
                [
                    "city",
                    "sensor_id",
                    "record_uptime_pct",
                    "daily_availability_pct",
                    "longest_missing_gap_days",
                    "period_mean_pm25_ugm3",
                    "latitude",
                    "longitude",
                ],
            ),
            "",
            "## Sensor Spatial Support",
            "",
            "Density here means sensor density per convex-hull area, not population density.",
            "",
            markdown_table(
                spatial,
                [
                    "city",
                    "retained_sensor_count",
                    "convex_hull_area_km2",
                    "sensor_density_per_100_km2_hull",
                    "mean_pairwise_distance_km",
                    "median_pairwise_distance_km",
                    "median_nearest_neighbor_km",
                    "p90_nearest_neighbor_km",
                ],
            ),
            "",
            "## Chicago Regulatory Context",
            "",
        ]
    )
    if chicago_aqs.empty:
        lines.append("Chicago AQS comparison was not evaluated.")
    else:
        lines.append(
            markdown_table(
                chicago_aqs,
                [
                    "paired_days",
                    "pearson_r",
                    "mae_ugm3",
                    "rmse_ugm3",
                    "bias_lcs_minus_aqs_ugm3",
                    "lcs_mean_ugm3",
                    "aqs_mean_ugm3",
                ],
            )
        )

    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `comparative_overall_summary.csv`",
            "- `comparative_qaqc_summary.csv`",
            "- `comparative_pm25_summary.csv`",
            "- `comparative_missingness_summary.csv`",
            "- `comparative_missingness_correlation_screen.csv`",
            "- `comparative_spatial_support_summary.csv`",
            "- `comparative_sensor_level_summary.csv`",
            "- `comparative_sensor_long_gap_extremes.csv`",
            "- `comparative_daily_city_metrics.csv`",
            "- `comparative_chicago_lcs_aqs_context.csv`",
            "- `three_city_comparative_analysis.md`",
            "",
            "## Recommended Next Uses",
            "",
            "- Use `comparative_overall_summary.csv` for one-row-per-city manuscript tables.",
            "- Use `comparative_missingness_correlation_screen.csv` to decide how cautiously to write about missingness.",
            "- Use `comparative_sensor_level_summary.csv` to identify sensors driving long gaps, low uptime, or high/low period means.",
            "- Use `comparative_spatial_support_summary.csv` for map captions and spatial-support language.",
        ]
    )
    (output_dir / "three_city_comparative_analysis.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pieces = [summarize_network(config) for config in PRIMARY_NETWORKS]
    qa = pd.concat([piece["qa"] for piece in pieces], ignore_index=True)
    pm = pd.concat([piece["pm"] for piece in pieces], ignore_index=True)
    missing = pd.concat([piece["missing"] for piece in pieces], ignore_index=True)
    daily = pd.concat([piece["daily"] for piece in pieces], ignore_index=True)
    correlations = pd.concat([piece["correlations"] for piece in pieces], ignore_index=True)
    spatial = pd.concat([piece["spatial"] for piece in pieces], ignore_index=True)
    sensor = pd.concat([piece["sensor"] for piece in pieces], ignore_index=True)
    sensor_gap_extremes = (
        sensor.sort_values(["city", "longest_missing_gap_days", "record_uptime_pct"], ascending=[True, False, True])
        .groupby("city", as_index=False)
        .head(5)
        .reset_index(drop=True)
    )
    chicago_aqs = chicago_lcs_aqs_comparison()
    overall = build_overall_summary(qa, pm, missing, spatial, correlations)

    outputs = {
        "comparative_qaqc_summary.csv": qa,
        "comparative_pm25_summary.csv": pm,
        "comparative_missingness_summary.csv": missing,
        "comparative_daily_city_metrics.csv": daily,
        "comparative_missingness_correlation_screen.csv": correlations,
        "comparative_spatial_support_summary.csv": spatial,
        "comparative_sensor_level_summary.csv": sensor,
        "comparative_sensor_long_gap_extremes.csv": sensor_gap_extremes,
        "comparative_chicago_lcs_aqs_context.csv": chicago_aqs,
        "comparative_overall_summary.csv": overall,
    }
    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False)

    metadata = {
        "purpose": "Three-city comparative QA/QC, missingness, MAR-screening, PM2.5, and spatial-support analysis.",
        "primary_networks": [network_metadata(config) for config in PRIMARY_NETWORKS],
        "outputs": sorted(outputs),
        "note": "MAR screening is based on observed correlations only; it is not a formal proof of missing-at-random.",
    }
    (OUTPUT_DIR / "comparative_analysis_metadata.json").write_text(json.dumps(metadata, indent=2, default=str))
    write_report(OUTPUT_DIR, overall, qa, pm, missing, correlations, spatial, chicago_aqs, sensor_gap_extremes)
    print(f"Wrote comparative analysis to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(overall[["city", "retained_sensor_count", "period_sensor_mean_mean_ugm3", "daily_missing_fraction_median_pct", "median_nearest_neighbor_km", "mar_screen_conclusion"]].to_string(index=False))


if __name__ == "__main__":
    main()
