from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_spatial_distance_correlation_analysis import (  # noqa: E402
    CITY_COLORS,
    DATA_ROOT,
    GRID_COLOR,
    OUTPUT_DPI,
    OUTPUT_DIR,
    PLOT_DIR,
    REPO_ROOT,
    RESOLUTION_LABELS,
    RESOLUTION_ORDER,
    NETWORKS,
    aggregate_values,
    haversine_km,
    markdown_table,
    prepare_network,
    save_figure,
    setup_matplotlib,
)


SUMMARY_SEED = 20260525
N_PERMUTATIONS = 199
ALPHA = 0.05
DISTANCE_BANDS_KM = (2, 5, 10)
KNN_VALUES = (4, 5, 8)
CORRELATION_THRESHOLDS = (0.95, 0.90, 0.75, 0.50)
MAX_WINDOWS_BY_RESOLUTION = {
    "highest_hourly": 120,
    "daily": 240,
    "weekly": 9999,
    "monthly": 9999,
    "total_period": 1,
}
CHICAGO_RAW_HIGH_RES_PATHS = (
    DATA_ROOT / "local_chicago_lcs_wide/highest_resolution_individual_lcs_corrected_pm25.parquet",
    DATA_ROOT / "local_chicago_lcs_wide/highest_resolution_individual_lcs_raw_pm25.parquet",
)


@dataclass(frozen=True)
class WeightScheme:
    name: str
    scheme_type: str
    parameter: int
    weights: np.ndarray
    distances_km: np.ndarray


def distance_matrix_km(locations: pd.DataFrame) -> np.ndarray:
    coords = locations[["Latitude", "Longitude"]].to_numpy(dtype=float)
    distances = np.zeros((len(coords), len(coords)), dtype=float)
    for index in range(len(coords)):
        distances[index] = haversine_km(
            coords[index, 0],
            coords[index, 1],
            coords[:, 0],
            coords[:, 1],
        )
    return distances


def band_weight_matrix(distances_km: np.ndarray, band_km: int) -> np.ndarray:
    return ((distances_km > 0) & (distances_km <= band_km)).astype(float)


def knn_weight_matrix(distances_km: np.ndarray, k_neighbors: int) -> np.ndarray:
    n_locations = distances_km.shape[0]
    weights = np.zeros_like(distances_km, dtype=float)
    if n_locations < 2:
        return weights
    effective_k = min(k_neighbors, n_locations - 1)
    for index in range(n_locations):
        row = distances_km[index].copy()
        row[index] = np.inf
        nearest = np.argsort(row)[:effective_k]
        weights[index, nearest] = 1.0
    return weights


def build_weight_schemes(distances_km: np.ndarray) -> list[WeightScheme]:
    schemes: list[WeightScheme] = []
    for band_km in DISTANCE_BANDS_KM:
        schemes.append(
            WeightScheme(
                name=f"band_{band_km}km",
                scheme_type="distance_band",
                parameter=band_km,
                weights=band_weight_matrix(distances_km, band_km),
                distances_km=distances_km,
            )
        )
    for k_neighbors in KNN_VALUES:
        schemes.append(
            WeightScheme(
                name=f"knn_{k_neighbors}",
                scheme_type="k_nearest_neighbor",
                parameter=k_neighbors,
                weights=knn_weight_matrix(distances_km, k_neighbors),
                distances_km=distances_km,
            )
        )
    return schemes


def weight_scheme_stats(city: str, dataset_key: str, sensor_count: int, scheme: WeightScheme) -> dict[str, Any]:
    weights = scheme.weights
    neighbor_counts = weights.sum(axis=1)
    link_distances = scheme.distances_km[weights > 0]
    undirected_pair_count = (
        int(np.triu(weights > 0, 1).sum())
        if scheme.scheme_type == "distance_band"
        else int(np.count_nonzero(np.maximum(weights, weights.T)) / 2)
    )
    return {
        "city": city,
        "dataset_key": dataset_key,
        "sensor_count": sensor_count,
        "weight_scheme": scheme.name,
        "scheme_type": scheme.scheme_type,
        "parameter": scheme.parameter,
        "directed_link_count": int(weights.sum()),
        "undirected_pair_count": undirected_pair_count,
        "zero_neighbor_sensor_count": int((neighbor_counts == 0).sum()),
        "min_neighbor_count": float(neighbor_counts.min()) if len(neighbor_counts) else np.nan,
        "median_neighbor_count": float(np.median(neighbor_counts)) if len(neighbor_counts) else np.nan,
        "max_neighbor_count": float(neighbor_counts.max()) if len(neighbor_counts) else np.nan,
        "median_link_distance_km": float(np.median(link_distances)) if len(link_distances) else np.nan,
        "p90_link_distance_km": float(np.quantile(link_distances, 0.90)) if len(link_distances) else np.nan,
    }


def sparse_links(weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    row_index, column_index = np.nonzero(weights > 0)
    return row_index.astype(int), column_index.astype(int)


def morans_i_sparse(values: np.ndarray, row_index: np.ndarray, column_index: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values)
    n_valid = int(valid.sum())
    if n_valid < 3:
        return float("nan")
    link_valid = valid[row_index] & valid[column_index]
    weight_sum = int(link_valid.sum())
    if weight_sum == 0:
        return float("nan")
    centered = values - np.nanmean(values)
    denominator = float(np.nansum(centered[valid] ** 2))
    if denominator == 0:
        return float("nan")
    numerator = float(np.sum(centered[row_index[link_valid]] * centered[column_index[link_valid]]))
    return float(n_valid / weight_sum * numerator / denominator)


def select_time_windows(values: pd.DataFrame, resolution: str) -> pd.DataFrame:
    valid = values.replace([np.inf, -np.inf], np.nan)
    valid = valid[valid.notna().sum(axis=1) >= 3]
    max_windows = MAX_WINDOWS_BY_RESOLUTION[resolution]
    if len(valid) <= max_windows:
        return valid
    selected_positions = np.unique(np.linspace(0, len(valid) - 1, max_windows, dtype=int))
    return valid.iloc[selected_positions]


def permutation_morans_summary(
    city: str,
    dataset_key: str,
    resolution: str,
    values: pd.DataFrame,
    scheme: WeightScheme,
    rng: np.random.Generator,
) -> dict[str, Any]:
    sampled = select_time_windows(values, resolution)
    row_index, column_index = sparse_links(scheme.weights)
    observed_values: list[float] = []
    p_positive_values: list[float] = []
    p_negative_values: list[float] = []
    p_two_sided_values: list[float] = []
    valid_sensor_counts: list[int] = []

    for _, row in sampled.iterrows():
        vector = row.to_numpy(dtype=float)
        valid = np.isfinite(vector)
        observed = morans_i_sparse(vector, row_index, column_index)
        if not np.isfinite(observed):
            continue
        valid_values = vector[valid].copy()
        permuted_i = np.empty(N_PERMUTATIONS, dtype=float)
        for permutation_index in range(N_PERMUTATIONS):
            permuted = vector.copy()
            permuted[valid] = rng.permutation(valid_values)
            permuted_i[permutation_index] = morans_i_sparse(permuted, row_index, column_index)
        permuted_i = permuted_i[np.isfinite(permuted_i)]
        if len(permuted_i) == 0:
            continue
        p_positive = (1 + np.sum(permuted_i >= observed)) / (len(permuted_i) + 1)
        p_negative = (1 + np.sum(permuted_i <= observed)) / (len(permuted_i) + 1)
        p_two_sided = min(1.0, 2 * min(p_positive, p_negative))
        observed_values.append(float(observed))
        p_positive_values.append(float(p_positive))
        p_negative_values.append(float(p_negative))
        p_two_sided_values.append(float(p_two_sided))
        valid_sensor_counts.append(int(valid.sum()))

    observed_array = np.asarray(observed_values, dtype=float)
    positive_array = np.asarray(p_positive_values, dtype=float)
    negative_array = np.asarray(p_negative_values, dtype=float)
    two_sided_array = np.asarray(p_two_sided_values, dtype=float)
    sensor_count_array = np.asarray(valid_sensor_counts, dtype=float)

    return {
        "city": city,
        "dataset_key": dataset_key,
        "resolution": resolution,
        "weight_scheme": scheme.name,
        "scheme_type": scheme.scheme_type,
        "parameter": scheme.parameter,
        "time_windows_available": int(len(values)),
        "time_windows_sampled": int(len(sampled)),
        "time_windows_tested": int(len(observed_array)),
        "n_permutations": N_PERMUTATIONS,
        "alpha": ALPHA,
        "median_observed_morans_i": float(np.median(observed_array)) if len(observed_array) else np.nan,
        "p10_observed_morans_i": float(np.quantile(observed_array, 0.10)) if len(observed_array) else np.nan,
        "p90_observed_morans_i": float(np.quantile(observed_array, 0.90)) if len(observed_array) else np.nan,
        "positive_sig_pct": float(100 * np.mean(positive_array <= ALPHA)) if len(positive_array) else np.nan,
        "negative_sig_pct": float(100 * np.mean(negative_array <= ALPHA)) if len(negative_array) else np.nan,
        "two_sided_sig_pct": float(100 * np.mean(two_sided_array <= ALPHA)) if len(two_sided_array) else np.nan,
        "median_p_positive": float(np.median(positive_array)) if len(positive_array) else np.nan,
        "median_p_two_sided": float(np.median(two_sided_array)) if len(two_sided_array) else np.nan,
        "median_valid_sensor_count": float(np.median(sensor_count_array)) if len(sensor_count_array) else np.nan,
        "min_valid_sensor_count": float(np.min(sensor_count_array)) if len(sensor_count_array) else np.nan,
    }


def distance_decay_thresholds(binned: pd.DataFrame) -> pd.DataFrame:
    records = []
    usable = binned[binned["resolution"] != "total_period"].dropna(subset=["median_pearson_correlation"]).copy()
    for (city, dataset_key, resolution), group in usable.groupby(["city", "dataset_key", "resolution"], sort=True):
        group = group.sort_values("distance_bin_left_km")
        for threshold in CORRELATION_THRESHOLDS:
            below = group[group["median_pearson_correlation"] <= threshold]
            if below.empty:
                row = {
                    "city": city,
                    "dataset_key": dataset_key,
                    "resolution": resolution,
                    "correlation_threshold": threshold,
                    "first_distance_bin_label": "",
                    "first_bin_pair_count": np.nan,
                    "first_median_distance_km": np.nan,
                    "first_bin_median_correlation": np.nan,
                }
            else:
                first = below.iloc[0]
                row = {
                    "city": city,
                    "dataset_key": dataset_key,
                    "resolution": resolution,
                    "correlation_threshold": threshold,
                    "first_distance_bin_label": first["distance_bin_label"],
                    "first_bin_pair_count": int(first["pair_count"]),
                    "first_median_distance_km": float(first["median_distance_km"]),
                    "first_bin_median_correlation": float(first["median_pearson_correlation"]),
                }
            records.append(row)
    return pd.DataFrame(records)


def chicago_raw_high_resolution_inventory() -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for path in CHICAGO_RAW_HIGH_RES_PATHS:
        if not path.exists():
            records.append(
                {
                    "dataset": path.stem,
                    "path": str(path.relative_to(REPO_ROOT)),
                    "exists": False,
                    "row_count": 0,
                    "sensor_column_count": 0,
                    "timestamp_min": "",
                    "timestamp_max": "",
                    "median_timestamp_gap_seconds": np.nan,
                    "p90_timestamp_gap_seconds": np.nan,
                    "total_non_null_sensor_readings": 0,
                    "median_non_null_readings_per_sensor": np.nan,
                    "p10_non_null_readings_per_sensor": np.nan,
                    "p90_non_null_readings_per_sensor": np.nan,
                }
            )
            continue
        parquet_file = pq.ParquetFile(path)
        metadata = parquet_file.metadata
        column_names = parquet_file.schema.names
        timestamp_column = column_names[0]
        sensor_columns = column_names[1:]
        non_null_counts = {column: 0 for column in sensor_columns}
        for row_group_index in range(metadata.num_row_groups):
            row_group = metadata.row_group(row_group_index)
            for column_index, column in enumerate(column_names[1:], start=1):
                column_chunk = row_group.column(column_index)
                stats = column_chunk.statistics
                null_count = stats.null_count if stats is not None and stats.has_null_count else 0
                non_null_counts[column] += row_group.num_rows - null_count
        timestamps = pd.read_parquet(path, columns=[timestamp_column])[timestamp_column]
        timestamp_naive = pd.to_datetime(timestamps, errors="coerce")
        if getattr(timestamp_naive.dt, "tz", None) is not None:
            timestamp_naive = timestamp_naive.dt.tz_localize(None)
        timestamp_sorted = timestamp_naive.dropna().sort_values()
        gaps_seconds = timestamp_sorted.diff().dt.total_seconds().dropna()
        sensor_non_null = np.asarray(list(non_null_counts.values()), dtype=float)
        records.append(
            {
                "dataset": path.stem,
                "path": str(path.relative_to(REPO_ROOT)),
                "exists": True,
                "row_count": int(metadata.num_rows),
                "sensor_column_count": int(len(sensor_columns)),
                "timestamp_min": str(timestamp_sorted.min()) if len(timestamp_sorted) else "",
                "timestamp_max": str(timestamp_sorted.max()) if len(timestamp_sorted) else "",
                "median_timestamp_gap_seconds": float(gaps_seconds.median()) if len(gaps_seconds) else np.nan,
                "p90_timestamp_gap_seconds": float(gaps_seconds.quantile(0.90)) if len(gaps_seconds) else np.nan,
                "total_non_null_sensor_readings": int(sensor_non_null.sum()),
                "median_non_null_readings_per_sensor": float(np.median(sensor_non_null)) if len(sensor_non_null) else np.nan,
                "p10_non_null_readings_per_sensor": float(np.quantile(sensor_non_null, 0.10)) if len(sensor_non_null) else np.nan,
                "p90_non_null_readings_per_sensor": float(np.quantile(sensor_non_null, 0.90)) if len(sensor_non_null) else np.nan,
            }
        )
    return pd.DataFrame(records)


def plot_permutation_heatmap(permutation: pd.DataFrame) -> None:
    setup_matplotlib()
    schemes = [f"band_{band}km" for band in DISTANCE_BANDS_KM] + [f"knn_{k}" for k in KNN_VALUES]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.3), sharex=True, sharey=True, constrained_layout=True)
    image = None
    for axis, city in zip(axes, ["Dhaka", "Lucknow", "Chicago"], strict=True):
        city_data = permutation[permutation["city"] == city]
        matrix = (
            city_data.pivot_table(
                index="weight_scheme",
                columns="resolution",
                values="positive_sig_pct",
                aggfunc="first",
            )
            .reindex(index=schemes, columns=RESOLUTION_ORDER)
            .to_numpy(dtype=float)
        )
        image = axis.imshow(matrix, vmin=0, vmax=100, cmap="magma")
        axis.set_title(city)
        axis.set_xticks(np.arange(len(RESOLUTION_ORDER)))
        axis.set_xticklabels([RESOLUTION_LABELS[item] for item in RESOLUTION_ORDER], rotation=35, ha="right")
        axis.set_yticks(np.arange(len(schemes)))
        axis.set_yticklabels(schemes)
        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                value = matrix[row_index, column_index]
                if np.isfinite(value):
                    axis.text(
                        column_index,
                        row_index,
                        f"{value:.0f}",
                        ha="center",
                        va="center",
                        color="white" if value > 45 else "black",
                        fontsize=7,
                    )
    if image is not None:
        colorbar = fig.colorbar(image, ax=axes.ravel().tolist(), shrink=0.82)
        colorbar.set_label("% windows with positive Moran's I, permutation p ≤ 0.05")
    fig.suptitle("Permutation Moran's I sensitivity by weighting scheme")
    save_figure(fig, PLOT_DIR / "morans_i_permutation_sensitivity_heatmap", dpi=OUTPUT_DPI)


def plot_distance_band_support(weight_stats: pd.DataFrame) -> None:
    setup_matplotlib()
    band_stats = weight_stats[weight_stats["scheme_type"] == "distance_band"].copy()
    fig, axis = plt.subplots(figsize=(8.5, 5))
    x_positions = np.arange(len(DISTANCE_BANDS_KM))
    width = 0.24
    for offset, city in zip([-width, 0, width], ["Dhaka", "Lucknow", "Chicago"], strict=True):
        subset = (
            band_stats[band_stats["city"] == city]
            .set_index("parameter")
            .reindex(DISTANCE_BANDS_KM)
        )
        axis.bar(
            x_positions + offset,
            subset["undirected_pair_count"],
            width=width,
            label=city,
            color=CITY_COLORS[city],
        )
    axis.set_xticks(x_positions)
    axis.set_xticklabels([f"{band} km" for band in DISTANCE_BANDS_KM])
    axis.set_ylabel("Undirected sensor pairs in distance band")
    axis.set_xlabel("Distance-band weighting threshold")
    axis.set_title("Moran's I distance-band support")
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    axis.legend()
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "distance_band_pair_counts_by_city", dpi=OUTPUT_DPI)


def plot_thresholds(thresholds: pd.DataFrame) -> None:
    setup_matplotlib()
    subset = thresholds[thresholds["correlation_threshold"].isin([0.95, 0.90])].copy()
    subset = subset[subset["resolution"].isin(["highest_hourly", "daily", "weekly", "monthly"])]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), sharey=True)
    for axis, threshold in zip(axes, [0.95, 0.90], strict=True):
        data = subset[subset["correlation_threshold"] == threshold]
        x_positions = np.arange(4)
        width = 0.24
        for offset, city in zip([-width, 0, width], ["Dhaka", "Lucknow", "Chicago"], strict=True):
            city_data = (
                data[data["city"] == city]
                .set_index("resolution")
                .reindex(["highest_hourly", "daily", "weekly", "monthly"])
            )
            axis.bar(
                x_positions + offset,
                city_data["first_median_distance_km"],
                width=width,
                label=city,
                color=CITY_COLORS[city],
            )
        axis.set_title(f"Median pairwise r ≤ {threshold:.2f}")
        axis.set_xticks(x_positions)
        axis.set_xticklabels(["Hourly", "Daily", "Weekly", "Monthly"], rotation=20, ha="right")
        axis.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    axes[0].set_ylabel("First affected distance-bin median (km)")
    axes[-1].legend()
    fig.suptitle("Distance scale where pairwise correlations drop below thresholds")
    fig.tight_layout()
    save_figure(fig, PLOT_DIR / "distance_decay_thresholds_by_city", dpi=OUTPUT_DPI)


def compact_permutation_table(permutation: pd.DataFrame) -> pd.DataFrame:
    keep = permutation[
        permutation["resolution"].isin(["highest_hourly", "daily", "monthly", "total_period"])
        & permutation["weight_scheme"].isin(["band_5km", "knn_5"])
    ].copy()
    keep["resolution"] = pd.Categorical(keep["resolution"], categories=RESOLUTION_ORDER, ordered=True)
    keep["weight_scheme"] = pd.Categorical(keep["weight_scheme"], categories=["band_5km", "knn_5"], ordered=True)
    keep["city"] = pd.Categorical(keep["city"], categories=["Dhaka", "Lucknow", "Chicago"], ordered=True)
    return keep.sort_values(["city", "resolution", "weight_scheme"])


def compact_weight_table(weight_stats: pd.DataFrame) -> pd.DataFrame:
    keep = weight_stats[
        weight_stats["weight_scheme"].isin(["band_2km", "band_5km", "band_10km", "knn_5"])
    ].copy()
    keep["weight_scheme"] = pd.Categorical(
        keep["weight_scheme"],
        categories=["band_2km", "band_5km", "band_10km", "knn_5"],
        ordered=True,
    )
    keep["city"] = pd.Categorical(keep["city"], categories=["Dhaka", "Lucknow", "Chicago"], ordered=True)
    return keep.sort_values(["city", "weight_scheme"])


def compact_threshold_table(thresholds: pd.DataFrame) -> pd.DataFrame:
    keep = thresholds[
        thresholds["correlation_threshold"].isin([0.95, 0.90])
        & thresholds["resolution"].isin(["highest_hourly", "daily", "weekly", "monthly"])
    ].copy()
    keep["resolution"] = pd.Categorical(keep["resolution"], categories=RESOLUTION_ORDER, ordered=True)
    keep["city"] = pd.Categorical(keep["city"], categories=["Dhaka", "Lucknow", "Chicago"], ordered=True)
    return keep.sort_values(["city", "resolution", "correlation_threshold"])


def write_report(
    weight_stats: pd.DataFrame,
    thresholds: pd.DataFrame,
    permutation: pd.DataFrame,
    raw_inventory: pd.DataFrame,
) -> None:
    daily_knn5 = permutation[(permutation["resolution"] == "daily") & (permutation["weight_scheme"] == "knn_5")]
    monthly_knn5 = permutation[(permutation["resolution"] == "monthly") & (permutation["weight_scheme"] == "knn_5")]
    lines = [
        "# Spatial Autocorrelation Sensitivity Summary",
        "",
        "## Scope And Guardrails",
        "",
        "This summary reports spatial distance relations and spatial autocorrelation sensitivity for the three primary networks: Dhaka LCS, Lucknow LCS, and Chicago corrected LCS with collocation sensors excluded.",
        "",
        "The manuscript-comparable highest-resolution layer is the aligned hourly matrix for all three cities. Chicago also has raw sub-hourly individual-reading parquet files, but those rows are event-level sparse readings rather than a synchronized cross-sensor matrix; exact-timestamp pairwise spatial correlations would therefore be dominated by alignment artifacts. The raw high-resolution files are inventoried below and the spatial-correlation analysis uses the aligned hourly layer.",
        "",
        f"Permutation Moran's I uses {N_PERMUTATIONS} deterministic permutations per sampled time window with seed {SUMMARY_SEED}. Hourly and daily windows are deterministically thinned when needed to keep the summary reproducible and computationally bounded; weekly, monthly, and total-period windows are kept in full.",
        "",
        "## Chicago Raw High-Resolution Inventory",
        "",
        markdown_table(
            raw_inventory,
            [
                "dataset",
                "row_count",
                "sensor_column_count",
                "timestamp_min",
                "timestamp_max",
                "median_timestamp_gap_seconds",
                "median_non_null_readings_per_sensor",
            ],
        ),
        "",
        "## Distance-Band And KNN Support",
        "",
        markdown_table(
            compact_weight_table(weight_stats),
            [
                "city",
                "weight_scheme",
                "sensor_count",
                "undirected_pair_count",
                "zero_neighbor_sensor_count",
                "median_neighbor_count",
                "median_link_distance_km",
            ],
        ),
        "",
        "## Distance-Decay Thresholds",
        "",
        "Rows show the first distance bin where median pairwise Pearson correlation drops at or below the threshold. Blank rows mean the threshold was not reached in the observed distance bins.",
        "",
        markdown_table(
            compact_threshold_table(thresholds),
            [
                "city",
                "resolution",
                "correlation_threshold",
                "first_distance_bin_label",
                "first_bin_pair_count",
                "first_median_distance_km",
                "first_bin_median_correlation",
            ],
        ),
        "",
        "## Permutation Moran's I Sensitivity",
        "",
        "Total-period rows contain one cross-sectional vector, so 0% or 100% significance values are single-vector diagnostics rather than temporal prevalence estimates.",
        "",
        markdown_table(
            compact_permutation_table(permutation),
            [
                "city",
                "resolution",
                "weight_scheme",
                "time_windows_tested",
                "median_observed_morans_i",
                "positive_sig_pct",
                "negative_sig_pct",
                "two_sided_sig_pct",
                "median_p_positive",
            ],
        ),
        "",
        "## Manuscript Interpretation",
        "",
        "- Chicago has the clearest distance-decay and positive spatial autocorrelation signal, especially at hourly and daily aggregation.",
        "- Dhaka and Lucknow have strong shared temporal signals but weaker daily/monthly spatial structure under the observed sensor spacing; nonsignificant Moran tests should be written as weak or inconsistent detectable spatial autocorrelation, not proof that spatial structure is absent.",
        "- Distance-band Moran tests are sensitive to support: the 2 km band leaves many Dhaka and Lucknow sensors isolated, so 5 km, 10 km, and k-nearest-neighbor schemes are needed as sensitivity checks.",
        "- The design-based Monte Carlo estimand remains defensible because it reproduces the deployed-network mean; spatial placement or kriging arguments should be framed as secondary design guidance, with Chicago being the strongest candidate for spatial methods.",
        "",
        "## Quick City Signals",
        "",
        markdown_table(
            daily_knn5[["city", "median_observed_morans_i", "positive_sig_pct", "two_sided_sig_pct"]].sort_values("city"),
            ["city", "median_observed_morans_i", "positive_sig_pct", "two_sided_sig_pct"],
        ),
        "",
        markdown_table(
            monthly_knn5[["city", "median_observed_morans_i", "positive_sig_pct", "two_sided_sig_pct"]].sort_values("city"),
            ["city", "median_observed_morans_i", "positive_sig_pct", "two_sided_sig_pct"],
        ),
        "",
        "## Output Files",
        "",
        "- `spatial/results/distance_correlation/spatial_weight_scheme_pair_counts.csv`",
        "- `spatial/results/distance_correlation/spatial_distance_decay_thresholds.csv`",
        "- `spatial/results/distance_correlation/spatial_morans_i_permutation_sensitivity.csv`",
        "- `spatial/results/distance_correlation/spatial_chicago_raw_high_resolution_inventory.csv`",
        "- `spatial/results/distance_correlation/spatial_distance_correlation_summary_metadata.json`",
        "- `spatial/plots/distance_correlation/morans_i_permutation_sensitivity_heatmap.png` and `.pdf`",
        "- `spatial/plots/distance_correlation/distance_band_pair_counts_by_city.png` and `.pdf`",
        "- `spatial/plots/distance_correlation/distance_decay_thresholds_by_city.png` and `.pdf`",
    ]
    (OUTPUT_DIR / "spatial_distance_correlation_summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    binned_path = OUTPUT_DIR / "spatial_distance_binned_summary.csv"
    if not binned_path.exists():
        raise FileNotFoundError(
            f"Missing {binned_path.relative_to(REPO_ROOT)}. Run build_spatial_distance_correlation_analysis.py first."
        )

    rng = np.random.default_rng(SUMMARY_SEED)
    weight_records: list[dict[str, Any]] = []
    permutation_records: list[dict[str, Any]] = []

    for config in NETWORKS:
        network = prepare_network(config)
        distances = distance_matrix_km(network.locations)
        schemes = build_weight_schemes(distances)
        for scheme in schemes:
            weight_records.append(
                weight_scheme_stats(
                    config.city,
                    config.dataset_key,
                    len(network.sensor_ids),
                    scheme,
                )
            )
        for resolution in RESOLUTION_ORDER:
            values = aggregate_values(network, resolution)
            for scheme in schemes:
                permutation_records.append(
                    permutation_morans_summary(
                        config.city,
                        config.dataset_key,
                        resolution,
                        values,
                        scheme,
                        rng,
                    )
                )
            print(
                f"{config.city} {resolution}: "
                f"windows={len(values)} schemes={len(schemes)}"
            )

    weight_stats = pd.DataFrame(weight_records)
    permutation = pd.DataFrame(permutation_records)
    binned = pd.read_csv(binned_path)
    thresholds = distance_decay_thresholds(binned)
    raw_inventory = chicago_raw_high_resolution_inventory()

    weight_stats.to_csv(OUTPUT_DIR / "spatial_weight_scheme_pair_counts.csv", index=False)
    thresholds.to_csv(OUTPUT_DIR / "spatial_distance_decay_thresholds.csv", index=False)
    permutation.to_csv(OUTPUT_DIR / "spatial_morans_i_permutation_sensitivity.csv", index=False)
    raw_inventory.to_csv(OUTPUT_DIR / "spatial_chicago_raw_high_resolution_inventory.csv", index=False)
    metadata = {
        "purpose": "Manuscript-oriented spatial summary: distance-band support, distance-decay thresholds, permutation Moran sensitivity, and Chicago raw high-resolution inventory.",
        "seed": SUMMARY_SEED,
        "n_permutations": N_PERMUTATIONS,
        "alpha": ALPHA,
        "distance_bands_km": DISTANCE_BANDS_KM,
        "knn_values": KNN_VALUES,
        "max_windows_by_resolution": MAX_WINDOWS_BY_RESOLUTION,
        "correlation_thresholds": CORRELATION_THRESHOLDS,
        "raw_high_resolution_note": "Chicago raw sub-hourly parquet rows are event-level sparse and are inventoried, not used as synchronized pairwise-correlation matrices.",
    }
    (OUTPUT_DIR / "spatial_distance_correlation_summary_metadata.json").write_text(json.dumps(metadata, indent=2, default=str))

    plot_permutation_heatmap(permutation)
    plot_distance_band_support(weight_stats)
    plot_thresholds(thresholds)
    write_report(weight_stats, thresholds, permutation, raw_inventory)
    print(f"Wrote spatial distance-correlation summary outputs to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        compact_permutation_table(permutation)[
            [
                "city",
                "resolution",
                "weight_scheme",
                "time_windows_tested",
                "median_observed_morans_i",
                "positive_sig_pct",
                "two_sided_sig_pct",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
