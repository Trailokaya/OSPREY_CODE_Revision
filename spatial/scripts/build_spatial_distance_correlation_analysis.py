from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
ANALYSIS_SCRIPT_DIR = REPO_ROOT / "analysis" / "scripts"
ANALYSIS_SRC_DIR = REPO_ROOT / "analysis" / "src"
for path in [SCRIPT_DIR, ANALYSIS_SCRIPT_DIR, ANALYSIS_SRC_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_three_city_comparative_analysis import (  # noqa: E402
    DATA_ROOT,
    CityNetwork,
    haversine_km,
    read_locations,
    read_pm_matrix,
    retained_sensor_ids,
)
from plot_style import (  # noqa: E402
    CITY_COLORS as SHARED_CITY_COLORS,
    GRID_COLOR,
    OUTPUT_DPI,
    save_figure,
    setup_matplotlib,
)


OUTPUT_DIR = REPO_ROOT / "spatial/results/distance_correlation"
PLOT_DIR = REPO_ROOT / "spatial/plots/distance_correlation"
DISTANCE_BINS_KM = [0, 1, 2, 5, 10, 20, 50, np.inf]
RESOLUTION_ORDER = ["highest_hourly", "daily", "weekly", "monthly", "total_period"]
RESOLUTION_LABELS = {
    "highest_hourly": "Highest/hourly",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "total_period": "Total period",
}
CITY_COLORS = {city.title(): SHARED_CITY_COLORS[city] for city in ("dhaka", "lucknow", "chicago")}
RESOLUTION_MARKERS = {
    "highest_hourly": "o",
    "daily": "s",
    "weekly": "^",
    "monthly": "D",
    "total_period": "X",
}


NETWORKS = (
    CityNetwork(
        dataset_key="dhaka_lcs",
        city="Dhaka",
        display_name="Dhaka LCS",
        pm_path=DATA_ROOT / "pm/Dhaka_hourly_PM25.csv",
        location_path=DATA_ROOT / "locations/Dhaka_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="pm25",
    ),
    CityNetwork(
        dataset_key="lucknow_lcs",
        city="Lucknow",
        display_name="Lucknow LCS",
        pm_path=DATA_ROOT / "pm/Lucknow_hourly_PM25.csv",
        location_path=DATA_ROOT / "locations/Lucknow_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="pm25",
    ),
    CityNetwork(
        dataset_key="chicago_lcs_corrected_no_collocation",
        city="Chicago",
        display_name="Chicago corrected LCS (collocation excluded)",
        pm_path=DATA_ROOT / "pm/Chicago_LCS_corrected_hourly_PM25.csv",
        location_path=DATA_ROOT / "locations/Chicago_LCS_corrected_sensor_locations.csv",
        source_frequency="hourly",
        pm_value="corrected_pm25",
        exclude_collocated=True,
    ),
)


@dataclass(frozen=True)
class PreparedNetwork:
    config: CityNetwork
    pm: pd.DataFrame
    locations: pd.DataFrame
    sensor_ids: list[str]


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


def safe_slope_per_10km(distance_km: pd.Series, y_values: pd.Series) -> float:
    frame = pd.DataFrame({"distance": distance_km, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 3:
        return float("nan")
    x = frame["distance"].to_numpy(dtype=float)
    y = frame["y"].to_numpy(dtype=float)
    if np.std(x) == 0:
        return float("nan")
    slope, _ = np.polyfit(x, y, 1)
    return float(slope * 10)


def prepare_network(config: CityNetwork) -> PreparedNetwork:
    pm = read_pm_matrix(config.pm_path)
    _, locations = read_locations(config)
    sensor_ids = retained_sensor_ids(locations, pm)
    locations = (
        locations[locations["Sensor_ID"].isin(sensor_ids)]
        .set_index("Sensor_ID")
        .loc[sensor_ids]
        .reset_index()
    )
    return PreparedNetwork(config=config, pm=pm, locations=locations, sensor_ids=sensor_ids)


def aggregate_values(network: PreparedNetwork, resolution: str) -> pd.DataFrame:
    frame = network.pm[["Timestamp", *network.sensor_ids]].copy()
    frame["Timestamp"] = pd.to_datetime(frame["Timestamp"])
    if resolution == "highest_hourly":
        values = frame.set_index("Timestamp")[network.sensor_ids].sort_index()
    elif resolution == "daily":
        values = frame.set_index("Timestamp")[network.sensor_ids].resample("D").mean()
    elif resolution == "weekly":
        values = frame.set_index("Timestamp")[network.sensor_ids].resample("W-MON").mean()
    elif resolution == "monthly":
        values = frame.set_index("Timestamp")[network.sensor_ids].resample("MS").mean()
    elif resolution == "total_period":
        values = pd.DataFrame(
            [frame[network.sensor_ids].mean(axis=0, skipna=True).to_dict()],
            index=[frame["Timestamp"].min()],
        )
    else:
        raise ValueError(f"Unsupported resolution: {resolution}")
    values.index.name = "Timestamp"
    values.columns = values.columns.astype(str)
    return values


def pairwise_distance_table(network: PreparedNetwork) -> pd.DataFrame:
    location_lookup = network.locations.set_index("Sensor_ID")
    rows = []
    for left_index, left_sensor in enumerate(network.sensor_ids[:-1]):
        left = location_lookup.loc[left_sensor]
        right_sensors = network.sensor_ids[left_index + 1 :]
        right_locations = location_lookup.loc[right_sensors]
        distances = haversine_km(
            float(left["Latitude"]),
            float(left["Longitude"]),
            right_locations["Latitude"].to_numpy(dtype=float),
            right_locations["Longitude"].to_numpy(dtype=float),
        )
        for right_sensor, distance in zip(right_sensors, distances, strict=True):
            rows.append(
                {
                    "dataset_key": network.config.dataset_key,
                    "city": network.config.city,
                    "sensor_i": left_sensor,
                    "sensor_j": right_sensor,
                    "distance_km": float(distance),
                }
            )
    return pd.DataFrame(rows)


def pairwise_metrics(values: pd.DataFrame, distance_table: pd.DataFrame, resolution: str) -> pd.DataFrame:
    matrix = values.copy()
    corr = matrix.corr(method="pearson", min_periods=3) if len(matrix) >= 3 else pd.DataFrame(
        np.nan,
        index=matrix.columns,
        columns=matrix.columns,
    )
    rows = []
    for row in distance_table.itertuples(index=False):
        left = matrix[row.sensor_i]
        right = matrix[row.sensor_j]
        paired = pd.DataFrame({"left": left, "right": right}).dropna()
        if paired.empty:
            mean_abs_diff = np.nan
            median_abs_diff = np.nan
            mean_squared_diff = np.nan
            semivariance = np.nan
            n_paired = 0
        else:
            signed_diff = paired["left"] - paired["right"]
            abs_diff = signed_diff.abs()
            squared_diff = signed_diff**2
            mean_abs_diff = float(abs_diff.mean())
            median_abs_diff = float(abs_diff.median())
            mean_squared_diff = float(squared_diff.mean())
            semivariance = float(0.5 * mean_squared_diff)
            n_paired = int(len(paired))
        corr_value = float(corr.loc[row.sensor_i, row.sensor_j]) if row.sensor_i in corr.index else np.nan
        rows.append(
            {
                "dataset_key": row.dataset_key,
                "city": row.city,
                "resolution": resolution,
                "sensor_i": row.sensor_i,
                "sensor_j": row.sensor_j,
                "distance_km": row.distance_km,
                "pearson_correlation": corr_value,
                "mean_abs_difference_ugm3": mean_abs_diff,
                "median_abs_difference_ugm3": median_abs_diff,
                "mean_squared_difference_ugm3_sq": mean_squared_diff,
                "semivariance_ugm3_sq": semivariance,
                "paired_time_windows": n_paired,
            }
        )
    return pd.DataFrame(rows)


def distance_bin_label(left: float, right: float) -> str:
    if np.isinf(right):
        return f"{left:g}+ km"
    return f"{left:g}-{right:g} km"


def build_binned_summary(pairwise: pd.DataFrame) -> pd.DataFrame:
    bins = pd.IntervalIndex.from_breaks(DISTANCE_BINS_KM, closed="left")
    pairwise = pairwise.copy()
    pairwise["distance_bin"] = pd.cut(pairwise["distance_km"], bins=bins)
    labels = {interval: distance_bin_label(interval.left, interval.right) for interval in bins}
    pairwise["distance_bin_label"] = pairwise["distance_bin"].map(labels).astype(str)
    records = []
    grouped = pairwise.groupby(["city", "dataset_key", "resolution", "distance_bin", "distance_bin_label"], observed=False)
    for keys, group in grouped:
        city, dataset_key, resolution, interval, label = keys
        if group.empty:
            continue
        records.append(
            {
                "city": city,
                "dataset_key": dataset_key,
                "resolution": resolution,
                "distance_bin_label": label,
                "distance_bin_left_km": float(interval.left),
                "distance_bin_right_km": float(interval.right) if not np.isinf(interval.right) else np.inf,
                "pair_count": int(len(group)),
                "median_distance_km": float(group["distance_km"].median()),
                "median_pearson_correlation": float(group["pearson_correlation"].median()),
                "p10_pearson_correlation": float(group["pearson_correlation"].quantile(0.10)),
                "p90_pearson_correlation": float(group["pearson_correlation"].quantile(0.90)),
                "median_mean_abs_difference_ugm3": float(group["mean_abs_difference_ugm3"].median()),
                "p10_mean_abs_difference_ugm3": float(group["mean_abs_difference_ugm3"].quantile(0.10)),
                "p90_mean_abs_difference_ugm3": float(group["mean_abs_difference_ugm3"].quantile(0.90)),
                "median_semivariance_ugm3_sq": float(group["semivariance_ugm3_sq"].median()),
                "p10_semivariance_ugm3_sq": float(group["semivariance_ugm3_sq"].quantile(0.10)),
                "p90_semivariance_ugm3_sq": float(group["semivariance_ugm3_sq"].quantile(0.90)),
            }
        )
    return pd.DataFrame(records)


def knn_weight_matrix(locations: pd.DataFrame, k: int = 5) -> np.ndarray:
    coords = locations[["Latitude", "Longitude"]].to_numpy(dtype=float)
    n_locations = len(coords)
    weights = np.zeros((n_locations, n_locations), dtype=float)
    if n_locations < 3:
        return weights
    effective_k = min(k, n_locations - 1)
    for index in range(n_locations):
        distances = haversine_km(coords[index, 0], coords[index, 1], coords[:, 0], coords[:, 1])
        distances[index] = np.inf
        nearest = np.argsort(distances)[:effective_k]
        weights[index, nearest] = 1.0
    return weights


def morans_i(values: np.ndarray, weights: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    if valid.sum() < 3:
        return float("nan")
    x = values[valid]
    w = weights[np.ix_(valid, valid)]
    weight_sum = float(w.sum())
    if weight_sum == 0:
        return float("nan")
    centered = x - x.mean()
    denominator = float(np.sum(centered**2))
    if denominator == 0:
        return float("nan")
    return float(len(x) / weight_sum * (centered @ w @ centered) / denominator)


def morans_summary(network: PreparedNetwork, values: pd.DataFrame, resolution: str) -> dict[str, Any]:
    weights = knn_weight_matrix(network.locations, k=5)
    moran_values = np.array([morans_i(row.to_numpy(dtype=float), weights) for _, row in values.iterrows()])
    valid = moran_values[np.isfinite(moran_values)]
    return {
        "dataset_key": network.config.dataset_key,
        "city": network.config.city,
        "resolution": resolution,
        "time_windows_total": int(len(values)),
        "time_windows_with_valid_morans_i": int(len(valid)),
        "median_morans_i_knn5": float(np.median(valid)) if len(valid) else np.nan,
        "p10_morans_i_knn5": float(np.quantile(valid, 0.10)) if len(valid) else np.nan,
        "p90_morans_i_knn5": float(np.quantile(valid, 0.90)) if len(valid) else np.nan,
    }


def relation_summary(pairwise: pd.DataFrame, values: pd.DataFrame) -> dict[str, Any]:
    valid_corr = pairwise.dropna(subset=["pearson_correlation"])
    valid_diff = pairwise.dropna(subset=["mean_abs_difference_ugm3"])
    return {
        "dataset_key": pairwise["dataset_key"].iloc[0],
        "city": pairwise["city"].iloc[0],
        "resolution": pairwise["resolution"].iloc[0],
        "sensor_count": int(values.shape[1]),
        "time_windows": int(len(values)),
        "pair_count": int(len(pairwise)),
        "pairs_with_valid_correlation": int(len(valid_corr)),
        "median_pairwise_distance_km": float(pairwise["distance_km"].median()),
        "median_pearson_correlation": float(valid_corr["pearson_correlation"].median()) if len(valid_corr) else np.nan,
        "p10_pearson_correlation": float(valid_corr["pearson_correlation"].quantile(0.10)) if len(valid_corr) else np.nan,
        "p90_pearson_correlation": float(valid_corr["pearson_correlation"].quantile(0.90)) if len(valid_corr) else np.nan,
        "spearman_distance_vs_correlation": spearman_rho(valid_corr["distance_km"], valid_corr["pearson_correlation"]) if len(valid_corr) else np.nan,
        "correlation_slope_per_10km": safe_slope_per_10km(valid_corr["distance_km"], valid_corr["pearson_correlation"]) if len(valid_corr) else np.nan,
        "median_mean_abs_difference_ugm3": float(valid_diff["mean_abs_difference_ugm3"].median()) if len(valid_diff) else np.nan,
        "median_semivariance_ugm3_sq": float(valid_diff["semivariance_ugm3_sq"].median()) if len(valid_diff) else np.nan,
        "spearman_distance_vs_semivariance": spearman_rho(
            valid_diff["distance_km"],
            valid_diff["semivariance_ugm3_sq"],
        )
        if len(valid_diff)
        else np.nan,
        "semivariance_slope_ugm3_sq_per_10km": safe_slope_per_10km(
            valid_diff["distance_km"],
            valid_diff["semivariance_ugm3_sq"],
        )
        if len(valid_diff)
        else np.nan,
        "spearman_distance_vs_mean_abs_difference": spearman_rho(
            valid_diff["distance_km"],
            valid_diff["mean_abs_difference_ugm3"],
        )
        if len(valid_diff)
        else np.nan,
        "mean_abs_difference_slope_ugm3_per_10km": safe_slope_per_10km(
            valid_diff["distance_km"],
            valid_diff["mean_abs_difference_ugm3"],
        )
        if len(valid_diff)
        else np.nan,
    }


def plot_correlation_bins(binned: pd.DataFrame) -> None:
    setup_matplotlib()
    plot_data = binned[binned["resolution"] != "total_period"].dropna(subset=["median_pearson_correlation"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        city_data = plot_data[plot_data["city"] == city]
        for resolution in RESOLUTION_ORDER:
            if resolution == "total_period":
                continue
            subset = city_data[city_data["resolution"] == resolution].sort_values("distance_bin_left_km")
            if subset.empty:
                continue
            axis.plot(
                subset["median_distance_km"],
                subset["median_pearson_correlation"],
                marker=RESOLUTION_MARKERS[resolution],
                linewidth=1.8,
                label=RESOLUTION_LABELS[resolution],
            )
        axis.set_title(city)
        axis.set_xlabel("Pairwise distance (km)")
        axis.grid(color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("Median pairwise Pearson correlation")
    axes[-1].legend(loc="lower left", fontsize=8)
    fig.suptitle("Spatial distance-correlation relation by aggregation scale")
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "distance_correlation_binned_by_city", dpi=OUTPUT_DPI)


def plot_difference_bins(binned: pd.DataFrame) -> None:
    setup_matplotlib()
    plot_data = binned.dropna(subset=["median_mean_abs_difference_ugm3"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=False)
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        city_data = plot_data[plot_data["city"] == city]
        for resolution in RESOLUTION_ORDER:
            subset = city_data[city_data["resolution"] == resolution].sort_values("distance_bin_left_km")
            if subset.empty:
                continue
            axis.plot(
                subset["median_distance_km"],
                subset["median_mean_abs_difference_ugm3"],
                marker=RESOLUTION_MARKERS[resolution],
                linewidth=1.8,
                label=RESOLUTION_LABELS[resolution],
            )
        axis.set_title(city)
        axis.set_xlabel("Pairwise distance (km)")
        axis.set_ylabel("Median mean absolute difference (µg/m³)")
        axis.grid(color=GRID_COLOR, linewidth=0.8)
    axes[-1].legend(loc="upper left", fontsize=8)
    fig.suptitle("Spatial distance-absolute-difference relation by aggregation scale")
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "distance_absolute_difference_binned_by_city", dpi=OUTPUT_DPI)


def plot_variogram_bins(binned: pd.DataFrame) -> None:
    setup_matplotlib()
    plot_data = binned.dropna(subset=["median_semivariance_ugm3_sq"])
    fig, axes = plt.subplots(3, 1, figsize=(8.6, 9.8), sharex=True, sharey=False)
    line_styles = {
        "highest_hourly": "-",
        "daily": "--",
        "weekly": "-.",
        "monthly": ":",
        "total_period": (0, (5, 1, 1, 1)),
    }
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        city_data = plot_data[plot_data["city"] == city]
        city_color = CITY_COLORS[city]
        for resolution in RESOLUTION_ORDER:
            subset = city_data[city_data["resolution"] == resolution].sort_values("distance_bin_left_km")
            if subset.empty:
                continue
            axis.plot(
                subset["median_distance_km"],
                subset["median_semivariance_ugm3_sq"],
                marker=RESOLUTION_MARKERS[resolution],
                markersize=4.5,
                linewidth=1.8,
                linestyle=line_styles[resolution],
                color=city_color,
                alpha=0.92,
                label=RESOLUTION_LABELS[resolution],
            )
        axis.set_title(city, loc="left", fontweight="bold")
        axis.set_ylabel("Median semivariance\n((µg/m³)²)")
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.65)
        axis.set_xlim(left=0)
    axes[-1].set_xlabel("Pairwise sensor distance (km)", labelpad=8)
    handles = [
        Line2D(
            [0],
            [0],
            color="#1f2937",
            marker=RESOLUTION_MARKERS[resolution],
            linestyle=line_styles[resolution],
            markersize=4.5,
            linewidth=1.8,
            label=RESOLUTION_LABELS[resolution],
        )
        for resolution in RESOLUTION_ORDER
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 0.015))
    fig.suptitle("Empirical variogram by temporal aggregation", y=0.98, fontsize=12)
    fig.subplots_adjust(left=0.11, right=0.98, top=0.93, bottom=0.13, hspace=0.12)
    save_figure(fig, PLOT_DIR / "empirical_variogram_binned_by_city", dpi=OUTPUT_DPI)


def plot_morans_i(morans: pd.DataFrame) -> None:
    setup_matplotlib()
    data = morans[morans["resolution"] != "total_period"].copy()
    fig, axis = plt.subplots(figsize=(10.5, 5))
    x_positions = np.arange(len(RESOLUTION_ORDER) - 1)
    width = 0.22
    for offset, city in zip([-width, 0, width], ["Dhaka", "Lucknow", "Chicago"], strict=True):
        subset = data[data["city"] == city].set_index("resolution").reindex(RESOLUTION_ORDER[:-1])
        axis.errorbar(
            x_positions + offset,
            subset["median_morans_i_knn5"],
            yerr=[
                subset["median_morans_i_knn5"] - subset["p10_morans_i_knn5"],
                subset["p90_morans_i_knn5"] - subset["median_morans_i_knn5"],
            ],
            fmt="o",
            capsize=3,
            label=city,
            color=CITY_COLORS[city],
        )
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_xticks(x_positions)
    axis.set_xticklabels([RESOLUTION_LABELS[resolution] for resolution in RESOLUTION_ORDER[:-1]])
    axis.set_ylabel("Median Moran's I (k=5 nearest-neighbor weights)")
    axis.set_title("Spatial autocorrelation summary by temporal aggregation")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    axis.legend()
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "morans_i_by_city_resolution", dpi=OUTPUT_DPI)


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    display = frame[columns].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def write_report(summary: pd.DataFrame, morans: pd.DataFrame) -> None:
    key = summary[summary["resolution"].isin(["highest_hourly", "daily", "weekly", "monthly", "total_period"])].copy()
    key["resolution"] = pd.Categorical(key["resolution"], categories=RESOLUTION_ORDER, ordered=True)
    key = key.sort_values(["city", "resolution"])
    lines = [
        "# Spatial Distance-Correlation Analysis",
        "",
        "## Scope",
        "",
        "This compares spatial distance relationships across the three primary networks at highest available canonical resolution, daily, weekly, monthly, and total-period aggregation. Highest resolution means the canonical hourly matrix for Dhaka, Lucknow, and Chicago corrected LCS. Chicago collocation sensors are excluded.",
        "",
        "Pairwise Pearson correlations are only meaningful where at least three time windows exist, so the total-period rows summarize pairwise absolute differences in full-period sensor means rather than temporal correlations.",
        "",
        "## Distance Relation Summary",
        "",
        markdown_table(
            key,
            [
                "city",
                "resolution",
                "sensor_count",
                "time_windows",
                "median_pearson_correlation",
                "spearman_distance_vs_correlation",
                "correlation_slope_per_10km",
                "median_mean_abs_difference_ugm3",
                "median_semivariance_ugm3_sq",
                "spearman_distance_vs_mean_abs_difference",
            ],
        ),
        "",
        "## Moran's I Summary",
        "",
        markdown_table(
            morans,
            [
                "city",
                "resolution",
                "time_windows_with_valid_morans_i",
                "median_morans_i_knn5",
                "p10_morans_i_knn5",
                "p90_morans_i_knn5",
            ],
        ),
        "",
        "## Plot Files",
        "",
        "- `spatial/plots/distance_correlation/distance_correlation_binned_by_city.png` and `.pdf`",
        "- `spatial/plots/distance_correlation/distance_absolute_difference_binned_by_city.png` and `.pdf`",
        "- `spatial/plots/distance_correlation/empirical_variogram_binned_by_city.png` and `.pdf`",
        "- `spatial/plots/distance_correlation/morans_i_by_city_resolution.png` and `.pdf`",
        "",
        "## Output CSV Files",
        "",
        "- `spatial/results/distance_correlation/spatial_pairwise_distance_metrics.csv`",
        "- `spatial/results/distance_correlation/spatial_distance_binned_summary.csv`",
        "- `spatial/results/distance_correlation/spatial_distance_relation_summary.csv`",
        "- `spatial/results/distance_correlation/spatial_morans_i_summary.csv`",
        "- `spatial/results/distance_correlation/spatial_distance_correlation_metadata.json`",
    ]
    (OUTPUT_DIR / "spatial_distance_correlation_analysis.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    pairwise_frames = []
    summary_records = []
    morans_records = []
    for config in NETWORKS:
        network = prepare_network(config)
        distance_table = pairwise_distance_table(network)
        for resolution in RESOLUTION_ORDER:
            values = aggregate_values(network, resolution)
            metrics = pairwise_metrics(values, distance_table, resolution)
            pairwise_frames.append(metrics)
            summary_records.append(relation_summary(metrics, values))
            morans_records.append(morans_summary(network, values, resolution))
            print(
                f"{config.city} {resolution}: sensors={values.shape[1]} "
                f"time_windows={len(values)} pairs={len(metrics)}"
            )
    pairwise = pd.concat(pairwise_frames, ignore_index=True)
    binned = build_binned_summary(pairwise)
    summary = pd.DataFrame(summary_records)
    morans = pd.DataFrame(morans_records)
    pairwise.to_csv(OUTPUT_DIR / "spatial_pairwise_distance_metrics.csv", index=False)
    binned.to_csv(OUTPUT_DIR / "spatial_distance_binned_summary.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "spatial_distance_relation_summary.csv", index=False)
    morans.to_csv(OUTPUT_DIR / "spatial_morans_i_summary.csv", index=False)
    metadata = {
        "purpose": "Spatial distance-correlation and distance-difference analysis by temporal aggregation.",
        "resolutions": RESOLUTION_ORDER,
        "distance_bins_km": DISTANCE_BINS_KM,
        "networks": [
            {
                "dataset_key": config.dataset_key,
                "city": config.city,
                "pm_path": str(config.pm_path.relative_to(REPO_ROOT)),
                "location_path": str(config.location_path.relative_to(REPO_ROOT)),
                "exclude_collocated": config.exclude_collocated,
            }
            for config in NETWORKS
        ],
        "note": "Total-period rows summarize pairwise differences in total-period means; temporal correlations are undefined with one time window.",
    }
    (OUTPUT_DIR / "spatial_distance_correlation_metadata.json").write_text(json.dumps(metadata, indent=2, default=str))
    plot_correlation_bins(binned)
    plot_difference_bins(binned)
    plot_variogram_bins(binned)
    plot_morans_i(morans)
    write_report(summary, morans)
    print(f"Wrote spatial distance-correlation outputs to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        summary[
            [
                "city",
                "resolution",
                "median_pearson_correlation",
                "spearman_distance_vs_correlation",
                "median_mean_abs_difference_ugm3",
                "spearman_distance_vs_mean_abs_difference",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
