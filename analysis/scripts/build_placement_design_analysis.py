from __future__ import annotations

import hashlib
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

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "monte_carlo" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "maps" / "scripts"))

from build_network_maps import geojson_bounds, load_geojson, polygon_patch  # noqa: E402
from plot_style import (  # noqa: E402
    BOUNDARY_FILL_COLOR,
    DISTRICT_EDGE_COLOR,
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    TEXT_COLOR,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)
from run_main_monte_carlo import DATASETS, DatasetBundle, derive_seed, load_dataset  # noqa: E402


OUTPUT_DIR = REPO_ROOT / "analysis/results/placement_design"
PLOT_DIR = REPO_ROOT / "analysis/plots/placement_design"
DAILY_MC_PATH = REPO_ROOT / "monte_carlo/plots/figure_data/daily_error_timeseries_selected_n.csv"
PERIOD_MC_PATH = REPO_ROOT / "monte_carlo/plots/figure_data/period_error_curves.csv"
MASTER_SEED = 20260525
DEFAULT_LENGTH_SCALE_KM = 10.0
FIXED_RANDOM_DRAWS = 10_000
SAMPLE_SIZES = (5, 10, 20)
MAP_SAMPLE_SIZE = 10

PRIMARY_DATASETS = (
    "dhaka_lcs",
    "lucknow_lcs",
    "chicago_lcs_corrected_no_collocation",
)

STRATEGY_LABELS = {
    "random_fixed": "Random",
    "random_fixed_mc": "Fixed random MC median",
    "random_srswor_mc": "Daywise random MC median",
    "max_ess": "Max ESS",
    "min_pred_var": "Min Pred. Var.",
    "min_ess": "Min ESS",
    "random_srswor_mc": "Random MC median",
}

STRATEGY_COLORS = {
    "random_srswor_mc": "#111827",
    "random_fixed_mc": "#374151",
    "random_fixed": "#6b7280",
    "max_ess": "#2563eb",
    "min_pred_var": "#16a34a",
    "min_ess": "#dc2626",
}

MAP_CONFIGS = {
    "dhaka_lcs": {
        "city_file": "Dhaka_City_admin6.geojson",
        "district_file": "Dhaka_District_admin5.geojson",
    },
    "lucknow_lcs": {
        "city_file": "Lucknow_City_admin6.geojson",
        "district_file": "Lucknow_District_admin5.geojson",
    },
    "chicago_lcs_corrected_no_collocation": {
        "city_file": "Chicago_City_admin6.geojson",
        "district_file": "Chicago_District_admin5.geojson",
    },
}


@dataclass(frozen=True)
class StrategySelection:
    dataset_key: str
    city: str
    sample_size: int
    strategy: str
    sensor_indices: tuple[int, ...]
    sensor_ids: tuple[str, ...]
    station_names: tuple[str, ...]


def stable_digest(values: list[str] | tuple[str, ...]) -> str:
    payload = json.dumps(list(values), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def haversine_matrix_km(latitudes: np.ndarray, longitudes: np.ndarray) -> np.ndarray:
    lat = np.radians(latitudes.astype(float))
    lon = np.radians(longitudes.astype(float))
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    value = np.sin(dlat / 2.0) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2.0) ** 2
    return 6371.0088 * 2.0 * np.arcsin(np.sqrt(np.clip(value, 0, 1)))


def project_lon_lat_km(latitudes: np.ndarray, longitudes: np.ndarray) -> np.ndarray:
    mean_lat = float(np.nanmean(latitudes))
    x = longitudes * 111.320 * math.cos(math.radians(mean_lat))
    y = latitudes * 110.574
    return np.column_stack([x, y])


def convex_hull(points: np.ndarray) -> np.ndarray:
    unique = sorted(set(map(tuple, points.tolist())))
    if len(unique) <= 1:
        return np.asarray(unique, dtype=float)

    def cross(origin: tuple[float, float], point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
        return (point_a[0] - origin[0]) * (point_b[1] - origin[1]) - (point_a[1] - origin[1]) * (point_b[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], dtype=float)


def polygon_area(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    x = points[:, 0]
    y = points[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def point_in_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    if len(polygon) < 3:
        return np.ones(len(points), dtype=bool)
    x = points[:, 0]
    y = points[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    xj, yj = polygon[-1]
    for xi, yi in polygon:
        crosses = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi)
        inside ^= crosses
        xj, yj = xi, yi
    return inside


def quadrature_points(points_km: np.ndarray, max_points: int = 225) -> np.ndarray:
    hull = convex_hull(points_km)
    if len(hull) < 3:
        return points_km
    minx, miny = np.min(hull, axis=0)
    maxx, maxy = np.max(hull, axis=0)
    side = int(math.ceil(math.sqrt(max_points)))
    xs = np.linspace(minx, maxx, side)
    ys = np.linspace(miny, maxy, side)
    grid = np.asarray([(x, y) for y in ys for x in xs], dtype=float)
    inside = grid[point_in_polygon(grid, hull)]
    if len(inside) < 20:
        return points_km
    return inside


def covariance_from_distances(distances_km: np.ndarray, length_scale_km: float) -> np.ndarray:
    corr = np.exp(-distances_km / length_scale_km)
    if corr.ndim == 2 and corr.shape[0] == corr.shape[1]:
        np.fill_diagonal(corr, 1.0)
    return corr


def ess_score(correlation: np.ndarray, selected: list[int]) -> float:
    if not selected:
        return 0.0
    sub = correlation[np.ix_(selected, selected)].copy()
    sub.flat[:: len(selected) + 1] += 1e-6
    inv = np.linalg.pinv(sub)
    ones = np.ones(len(selected))
    return float(ones @ inv @ ones)


def predictive_information(
    correlation: np.ndarray,
    sensor_to_quad_corr: np.ndarray,
    selected: list[int],
) -> float:
    if not selected:
        return 0.0
    sub = correlation[np.ix_(selected, selected)].copy()
    sub.flat[:: len(selected) + 1] += 1e-6
    inv = np.linalg.pinv(sub)
    summed_cov = sensor_to_quad_corr[selected, :].sum(axis=1)
    return float(summed_cov @ inv @ summed_cov / (sensor_to_quad_corr.shape[1] ** 2))


def deterministic_random_indices(population_size: int, sample_size: int, seed: int) -> list[int]:
    rng = np.random.default_rng(seed)
    return sorted(rng.choice(population_size, size=sample_size, replace=False).astype(int).tolist())


def select_max_ess(correlation: np.ndarray, distances: np.ndarray, sample_size: int) -> list[int]:
    if sample_size == 1:
        return [int(np.argmax(np.mean(distances, axis=1)))]
    farthest = np.unravel_index(np.argmax(distances), distances.shape)
    selected = [int(farthest[0]), int(farthest[1])]
    while len(selected) < sample_size:
        candidates = [idx for idx in range(correlation.shape[0]) if idx not in selected]
        best = max(candidates, key=lambda idx: ess_score(correlation, [*selected, idx]))
        selected.append(int(best))
    return sorted(selected)


def select_min_ess(correlation: np.ndarray, distances: np.ndarray, sample_size: int) -> list[int]:
    if sample_size == 1:
        return [int(np.argmin(np.mean(distances, axis=1)))]
    masked = distances.copy()
    np.fill_diagonal(masked, np.inf)
    closest = np.unravel_index(np.argmin(masked), masked.shape)
    selected = [int(closest[0]), int(closest[1])]
    while len(selected) < sample_size:
        candidates = [idx for idx in range(correlation.shape[0]) if idx not in selected]
        best = min(candidates, key=lambda idx: ess_score(correlation, [*selected, idx]))
        selected.append(int(best))
    return sorted(selected)


def select_min_predictive_variance(
    correlation: np.ndarray,
    sensor_to_quad_corr: np.ndarray,
    sample_size: int,
) -> list[int]:
    first = int(np.argmax(sensor_to_quad_corr.sum(axis=1)))
    selected = [first]
    while len(selected) < sample_size:
        candidates = [idx for idx in range(correlation.shape[0]) if idx not in selected]
        best = max(candidates, key=lambda idx: predictive_information(correlation, sensor_to_quad_corr, [*selected, idx]))
        selected.append(int(best))
    return sorted(selected)


def strategy_indices(
    bundle: DatasetBundle,
    sample_size: int,
    length_scale_km: float,
) -> dict[str, list[int]]:
    latitudes = np.asarray(bundle.latitudes, dtype=float)
    longitudes = np.asarray(bundle.longitudes, dtype=float)
    distances = haversine_matrix_km(latitudes, longitudes)
    correlation = covariance_from_distances(distances, length_scale_km)
    points_km = project_lon_lat_km(latitudes, longitudes)
    q_points = quadrature_points(points_km)
    sensor_quad_distances = np.sqrt(np.sum((points_km[:, None, :] - q_points[None, :, :]) ** 2, axis=2))
    sensor_to_quad_corr = covariance_from_distances(sensor_quad_distances, length_scale_km)
    return {
        "random_fixed": deterministic_random_indices(
            len(bundle.sensor_ids),
            sample_size,
            derive_seed(MASTER_SEED, bundle.spec.key, "placement", "random_fixed", sample_size),
        ),
        "max_ess": select_max_ess(correlation, distances, sample_size),
        "min_pred_var": select_min_predictive_variance(correlation, sensor_to_quad_corr, sample_size),
        "min_ess": select_min_ess(correlation, distances, sample_size),
    }


def selection_from_indices(bundle: DatasetBundle, sample_size: int, strategy: str, indices: list[int]) -> StrategySelection:
    sensor_ids = tuple(str(bundle.sensor_ids[index]) for index in indices)
    station_names = tuple(str(bundle.station_names[index]) for index in indices)
    return StrategySelection(
        dataset_key=bundle.spec.key,
        city=bundle.spec.city,
        sample_size=sample_size,
        strategy=strategy,
        sensor_indices=tuple(indices),
        sensor_ids=sensor_ids,
        station_names=station_names,
    )


def subset_spatial_metrics(
    bundle: DatasetBundle,
    selected_indices: tuple[int, ...],
    length_scale_km: float,
) -> dict[str, float]:
    latitudes = np.asarray(bundle.latitudes, dtype=float)
    longitudes = np.asarray(bundle.longitudes, dtype=float)
    distances = haversine_matrix_km(latitudes, longitudes)
    correlation = covariance_from_distances(distances, length_scale_km)
    selected = list(selected_indices)
    selected_distances = distances[np.ix_(selected, selected)]
    pair_values = selected_distances[np.triu_indices(len(selected), k=1)]
    points_km = project_lon_lat_km(latitudes, longitudes)
    hull = convex_hull(points_km[selected, :])
    return {
        "ess_score": ess_score(correlation, selected),
        "min_pairwise_distance_km": float(np.nanmin(pair_values)) if len(pair_values) else 0.0,
        "median_pairwise_distance_km": float(np.nanmedian(pair_values)) if len(pair_values) else 0.0,
        "mean_pairwise_distance_km": float(np.nanmean(pair_values)) if len(pair_values) else 0.0,
        "convex_hull_area_km2": polygon_area(hull),
        "centroid_lat": float(np.nanmean(latitudes[selected])),
        "centroid_lon": float(np.nanmean(longitudes[selected])),
    }


def evaluate_period(bundle: DatasetBundle, selection: StrategySelection) -> dict[str, Any]:
    values = np.asarray(bundle.period_values, dtype=float)
    reference_values = values[np.isfinite(values)]
    selected_values = values[list(selection.sensor_indices)]
    selected_values = selected_values[np.isfinite(selected_values)]
    reference_mean = float(np.nanmean(reference_values))
    subset_mean = float(np.nanmean(selected_values))
    absolute_error = abs(subset_mean - reference_mean)
    ape = absolute_error / abs(reference_mean) * 100.0 if reference_mean != 0 else np.nan
    return {
        "dataset_key": selection.dataset_key,
        "city": selection.city,
        "strategy": selection.strategy,
        "sample_size": selection.sample_size,
        "time_aggregation": "period",
        "time_index": "study_period",
        "reference_mean_ugm3": reference_mean,
        "subset_mean_ugm3": subset_mean,
        "n_reference_valid": int(len(reference_values)),
        "n_subset_valid": int(len(selected_values)),
        "ape_pct": float(ape),
        "absolute_error_ugm3": float(absolute_error),
    }


def evaluate_daily(bundle: DatasetBundle, selection: StrategySelection) -> tuple[pd.DataFrame, dict[str, Any]]:
    values = np.asarray(bundle.daily_values, dtype=float)
    selected_values = values[:, list(selection.sensor_indices)]
    n_reference_valid = np.isfinite(values).sum(axis=1)
    n_subset_valid = np.isfinite(selected_values).sum(axis=1)
    reference_sum = np.nansum(values, axis=1)
    subset_sum = np.nansum(selected_values, axis=1)
    reference_mean = np.divide(
        reference_sum,
        n_reference_valid,
        out=np.full(values.shape[0], np.nan, dtype=float),
        where=n_reference_valid > 0,
    )
    subset_mean = np.divide(
        subset_sum,
        n_subset_valid,
        out=np.full(values.shape[0], np.nan, dtype=float),
        where=n_subset_valid > 0,
    )
    absolute_error = np.abs(subset_mean - reference_mean)
    ape = np.where(reference_mean != 0, absolute_error / np.abs(reference_mean) * 100.0, np.nan)
    daily = pd.DataFrame(
        {
            "dataset_key": selection.dataset_key,
            "city": selection.city,
            "strategy": selection.strategy,
            "sample_size": selection.sample_size,
            "date": bundle.daily_dates,
            "reference_mean_ugm3": reference_mean,
            "subset_mean_ugm3": subset_mean,
            "n_reference_valid": n_reference_valid,
            "n_subset_valid": n_subset_valid,
            "ape_pct": ape,
            "absolute_error_ugm3": absolute_error,
        }
    )
    finite = daily.replace([np.inf, -np.inf], np.nan).dropna(subset=["ape_pct", "absolute_error_ugm3"])
    summary = {
        "dataset_key": selection.dataset_key,
        "city": selection.city,
        "strategy": selection.strategy,
        "sample_size": selection.sample_size,
        "time_aggregation": "daily",
        "time_index": "all_days",
        "n_days_total": int(len(daily)),
        "n_days_evaluated": int(len(finite)),
        "ape_mean_pct": float(finite["ape_pct"].mean()),
        "ape_median_pct": float(finite["ape_pct"].median()),
        "ape_p75_pct": float(finite["ape_pct"].quantile(0.75)),
        "ape_p95_pct": float(finite["ape_pct"].quantile(0.95)),
        "absolute_error_mean_ugm3": float(finite["absolute_error_ugm3"].mean()),
        "absolute_error_median_ugm3": float(finite["absolute_error_ugm3"].median()),
        "absolute_error_p75_ugm3": float(finite["absolute_error_ugm3"].quantile(0.75)),
        "absolute_error_p95_ugm3": float(finite["absolute_error_ugm3"].quantile(0.95)),
        "median_subset_valid_sensors": float(finite["n_subset_valid"].median()),
        "min_subset_valid_sensors": int(finite["n_subset_valid"].min()) if not finite.empty else 0,
    }
    return daily, summary


def random_mc_baseline_rows() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    daily = pd.read_csv(DAILY_MC_PATH)
    period = pd.read_csv(PERIOD_MC_PATH)
    daily = daily[
        (daily["dataset_key"].isin(PRIMARY_DATASETS))
        & (daily["sample_size"].isin(SAMPLE_SIZES))
        & (daily["scenario"] == "S0_baseline")
        & (daily["estimator"] == "arithmetic_mean")
        & (daily["placement"] == "random_srswor")
    ].copy()
    for (dataset_key, city, sample_size), group in daily.groupby(["dataset_key", "city", "sample_size"], sort=True):
        rows.append(
            {
                "dataset_key": dataset_key,
                "city": city,
                "strategy": "random_srswor_mc",
                "sample_size": int(sample_size),
                "time_aggregation": "daily",
                "time_index": "all_days",
                "n_days_total": int(len(group)),
                "n_days_evaluated": int(len(group.dropna(subset=["ape_median_pct"]))),
                "ape_mean_pct": float(group["ape_median_pct"].mean()),
                "ape_median_pct": float(group["ape_median_pct"].median()),
                "ape_p75_pct": float(group["ape_median_pct"].quantile(0.75)),
                "ape_p95_pct": float(group["ape_median_pct"].quantile(0.95)),
                "absolute_error_mean_ugm3": float(group["absolute_error_median_ugm3"].mean()),
                "absolute_error_median_ugm3": float(group["absolute_error_median_ugm3"].median()),
                "absolute_error_p75_ugm3": float(group["absolute_error_median_ugm3"].quantile(0.75)),
                "absolute_error_p95_ugm3": float(group["absolute_error_median_ugm3"].quantile(0.95)),
                "median_subset_valid_sensors": np.nan,
                "min_subset_valid_sensors": np.nan,
            }
        )
    period = period[
        (period["dataset_key"].isin(PRIMARY_DATASETS))
        & (period["sample_size"].isin(SAMPLE_SIZES))
        & (period["scenario"] == "S0_baseline")
        & (period["estimator"] == "arithmetic_mean")
        & (period["placement"] == "random_srswor")
    ].copy()
    for _, row in period.iterrows():
        rows.append(
            {
                "dataset_key": row["dataset_key"],
                "city": row["city"],
                "strategy": "random_srswor_mc",
                "sample_size": int(row["sample_size"]),
                "time_aggregation": "period",
                "time_index": "study_period",
                "reference_mean_ugm3": float(row["reference_mean_ugm3"]),
                "subset_mean_ugm3": np.nan,
                "n_reference_valid": int(row["n_sensors_available"]),
                "n_subset_valid": int(row["sample_size"]),
                "ape_pct": float(row["ape_median"]),
                "absolute_error_ugm3": float(row["absolute_median"]),
            }
        )
    return pd.DataFrame(rows)


def build_selections() -> tuple[list[StrategySelection], pd.DataFrame, dict[str, DatasetBundle]]:
    bundles = {key: load_dataset(DATASETS[key]) for key in PRIMARY_DATASETS}
    selections: list[StrategySelection] = []
    spatial_rows: list[dict[str, Any]] = []
    for dataset_key, bundle in bundles.items():
        for sample_size in SAMPLE_SIZES:
            if sample_size >= len(bundle.sensor_ids):
                continue
            for strategy, indices in strategy_indices(bundle, sample_size, DEFAULT_LENGTH_SCALE_KM).items():
                selection = selection_from_indices(bundle, sample_size, strategy, indices)
                selections.append(selection)
                metrics = subset_spatial_metrics(bundle, selection.sensor_indices, DEFAULT_LENGTH_SCALE_KM)
                spatial_rows.append(
                    {
                        "dataset_key": selection.dataset_key,
                        "city": selection.city,
                        "strategy": strategy,
                        "strategy_label": STRATEGY_LABELS[strategy],
                        "sample_size": sample_size,
                        "length_scale_km": DEFAULT_LENGTH_SCALE_KM,
                        "sensor_ids_json": json.dumps(list(selection.sensor_ids)),
                        "station_names_json": json.dumps(list(selection.station_names)),
                        "sensor_set_hash": stable_digest(selection.sensor_ids),
                        **metrics,
                    }
                )
    return selections, pd.DataFrame(spatial_rows), bundles


def fixed_random_mc_baseline_rows(bundles: dict[str, DatasetBundle]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dataset_key, bundle in bundles.items():
        daily_values = np.asarray(bundle.daily_values, dtype=float)
        period_values = np.asarray(bundle.period_values, dtype=float)
        n_reference_valid = np.isfinite(daily_values).sum(axis=1)
        reference_mean = np.divide(
            np.nansum(daily_values, axis=1),
            n_reference_valid,
            out=np.full(daily_values.shape[0], np.nan, dtype=float),
            where=n_reference_valid > 0,
        )
        period_reference = float(np.nanmean(period_values))
        for sample_size in SAMPLE_SIZES:
            if sample_size >= len(bundle.sensor_ids):
                continue
            rng = np.random.default_rng(
                derive_seed(MASTER_SEED, dataset_key, "placement", "random_fixed_mc", sample_size)
            )
            random_keys = rng.random((FIXED_RANDOM_DRAWS, len(bundle.sensor_ids)))
            positions = np.argpartition(random_keys, sample_size - 1, axis=1)[:, :sample_size]

            daily_median_apes: list[np.ndarray] = []
            daily_p95_apes: list[np.ndarray] = []
            daily_median_abs: list[np.ndarray] = []
            daily_p95_abs: list[np.ndarray] = []
            period_apes: list[np.ndarray] = []
            period_abs: list[np.ndarray] = []
            chunk_size = 500
            for start in range(0, FIXED_RANDOM_DRAWS, chunk_size):
                chunk_positions = positions[start : start + chunk_size]
                chunk_daily = daily_values[:, chunk_positions]
                chunk_counts = np.isfinite(chunk_daily).sum(axis=2)
                chunk_means = np.divide(
                    np.nansum(chunk_daily, axis=2),
                    chunk_counts,
                    out=np.full(chunk_counts.shape, np.nan, dtype=float),
                    where=chunk_counts > 0,
                )
                chunk_abs = np.abs(chunk_means - reference_mean[:, None])
                chunk_ape = np.where(reference_mean[:, None] != 0, chunk_abs / np.abs(reference_mean[:, None]) * 100.0, np.nan)
                daily_median_apes.append(np.nanmedian(chunk_ape, axis=0))
                daily_p95_apes.append(np.nanquantile(chunk_ape, 0.95, axis=0))
                daily_median_abs.append(np.nanmedian(chunk_abs, axis=0))
                daily_p95_abs.append(np.nanquantile(chunk_abs, 0.95, axis=0))

                chunk_period = period_values[chunk_positions]
                chunk_period_counts = np.isfinite(chunk_period).sum(axis=1)
                chunk_period_means = np.divide(
                    np.nansum(chunk_period, axis=1),
                    chunk_period_counts,
                    out=np.full(chunk_period_counts.shape, np.nan, dtype=float),
                    where=chunk_period_counts > 0,
                )
                chunk_period_abs = np.abs(chunk_period_means - period_reference)
                chunk_period_ape = np.where(period_reference != 0, chunk_period_abs / abs(period_reference) * 100.0, np.nan)
                period_apes.append(chunk_period_ape)
                period_abs.append(chunk_period_abs)

            daily_median_ape_values = np.concatenate(daily_median_apes)
            daily_p95_ape_values = np.concatenate(daily_p95_apes)
            daily_median_abs_values = np.concatenate(daily_median_abs)
            daily_p95_abs_values = np.concatenate(daily_p95_abs)
            period_ape_values = np.concatenate(period_apes)
            period_abs_values = np.concatenate(period_abs)
            rows.append(
                {
                    "dataset_key": dataset_key,
                    "city": bundle.spec.city,
                    "strategy": "random_fixed_mc",
                    "sample_size": sample_size,
                    "time_aggregation": "daily",
                    "time_index": "all_days",
                    "n_days_total": int(len(bundle.daily_dates)),
                    "n_days_evaluated": int(np.isfinite(reference_mean).sum()),
                    "n_draws": FIXED_RANDOM_DRAWS,
                    "ape_mean_pct": float(np.nanmean(daily_median_ape_values)),
                    "ape_median_pct": float(np.nanmedian(daily_median_ape_values)),
                    "ape_p75_pct": float(np.nanquantile(daily_median_ape_values, 0.75)),
                    "ape_p95_pct": float(np.nanquantile(daily_median_ape_values, 0.95)),
                    "daily_p95_ape_median_across_fixed_subsets_pct": float(np.nanmedian(daily_p95_ape_values)),
                    "absolute_error_mean_ugm3": float(np.nanmean(daily_median_abs_values)),
                    "absolute_error_median_ugm3": float(np.nanmedian(daily_median_abs_values)),
                    "absolute_error_p75_ugm3": float(np.nanquantile(daily_median_abs_values, 0.75)),
                    "absolute_error_p95_ugm3": float(np.nanquantile(daily_median_abs_values, 0.95)),
                    "daily_p95_absolute_error_median_across_fixed_subsets_ugm3": float(np.nanmedian(daily_p95_abs_values)),
                }
            )
            rows.append(
                {
                    "dataset_key": dataset_key,
                    "city": bundle.spec.city,
                    "strategy": "random_fixed_mc",
                    "sample_size": sample_size,
                    "time_aggregation": "period",
                    "time_index": "study_period",
                    "n_draws": FIXED_RANDOM_DRAWS,
                    "reference_mean_ugm3": period_reference,
                    "subset_mean_ugm3": np.nan,
                    "n_reference_valid": int(np.isfinite(period_values).sum()),
                    "n_subset_valid": sample_size,
                    "ape_pct": float(np.nanmedian(period_ape_values)),
                    "ape_p75_pct": float(np.nanquantile(period_ape_values, 0.75)),
                    "ape_p95_pct": float(np.nanquantile(period_ape_values, 0.95)),
                    "absolute_error_ugm3": float(np.nanmedian(period_abs_values)),
                    "absolute_error_p75_ugm3": float(np.nanquantile(period_abs_values, 0.75)),
                    "absolute_error_p95_ugm3": float(np.nanquantile(period_abs_values, 0.95)),
                }
            )
    return pd.DataFrame(rows)


def summarize_performance(
    selections: list[StrategySelection],
    bundles: dict[str, DatasetBundle],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily_frames: list[pd.DataFrame] = []
    performance_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []
    for selection in selections:
        bundle = bundles[selection.dataset_key]
        daily, daily_summary = evaluate_daily(bundle, selection)
        period_summary = evaluate_period(bundle, selection)
        daily_frames.append(daily)
        performance_rows.append(daily_summary)
        period_rows.append(period_summary)

    daily_errors = pd.concat(daily_frames, ignore_index=True)
    daily_summary = pd.DataFrame(performance_rows)
    period_summary = pd.DataFrame(period_rows)
    baseline = pd.concat([fixed_random_mc_baseline_rows(bundles), random_mc_baseline_rows()], ignore_index=True, sort=False)
    performance = pd.concat([daily_summary, period_summary, baseline], ignore_index=True, sort=False)
    performance["strategy_label"] = performance["strategy"].map(STRATEGY_LABELS)
    return daily_errors, period_summary, performance


def performance_delta(performance: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in performance.groupby(["dataset_key", "city", "sample_size", "time_aggregation"], sort=True):
        baseline = group[group["strategy"] == "random_fixed_mc"]
        baseline_type = "random_fixed_mc"
        if baseline.empty:
            baseline = group[group["strategy"] == "random_srswor_mc"]
            baseline_type = "random_srswor_mc"
        if baseline.empty:
            continue
        baseline_row = baseline.iloc[0]
        base_ape = (
            float(baseline_row["ape_median_pct"])
            if keys[3] == "daily"
            else float(baseline_row["ape_pct"])
        )
        base_abs = (
            float(baseline_row["absolute_error_median_ugm3"])
            if keys[3] == "daily"
            else float(baseline_row["absolute_error_ugm3"])
        )
        deterministic_group = group[~group["strategy"].isin({"random_srswor_mc", "random_fixed_mc"})]
        for _, row in deterministic_group.iterrows():
            ape_value = float(row["ape_median_pct"]) if keys[3] == "daily" else float(row["ape_pct"])
            abs_value = (
                float(row["absolute_error_median_ugm3"])
                if keys[3] == "daily"
                else float(row["absolute_error_ugm3"])
            )
            rows.append(
                {
                    "dataset_key": keys[0],
                    "city": keys[1],
                    "sample_size": int(keys[2]),
                    "time_aggregation": keys[3],
                    "strategy": row["strategy"],
                    "strategy_label": row["strategy_label"],
                    "ape_value_pct": ape_value,
                    "random_mc_ape_value_pct": base_ape,
                    "random_baseline_strategy": baseline_type,
                    "ape_delta_vs_random_pct_points": ape_value - base_ape,
                    "absolute_error_value_ugm3": abs_value,
                    "random_mc_absolute_error_value_ugm3": base_abs,
                    "absolute_error_delta_vs_random_ugm3": abs_value - base_abs,
                    "beats_random_by_ape": bool(ape_value < base_ape),
                }
            )
    return pd.DataFrame(rows)


def plot_performance_by_n(performance: pd.DataFrame) -> None:
    deterministic = performance[performance["strategy"] != "random_srswor_mc"].copy()
    if deterministic.empty:
        return
    fig, axes = plt.subplots(2, 3, figsize=(12, 7.5), sharex=True, constrained_layout=True)
    city_order = ["Dhaka", "Lucknow", "Chicago"]
    strategy_order = ["random_fixed_mc", "random_fixed", "max_ess", "min_pred_var", "min_ess"]
    for column, city in enumerate(city_order):
        for row_index, time_aggregation in enumerate(["daily", "period"]):
            axis = axes[row_index, column]
            subset = performance[
                (performance["city"] == city)
                & (performance["time_aggregation"] == time_aggregation)
            ].copy()
            for strategy in strategy_order:
                group = subset[subset["strategy"] == strategy].sort_values("sample_size")
                if group.empty:
                    continue
                y_values = (
                    group["ape_median_pct"].to_numpy(dtype=float)
                    if time_aggregation == "daily"
                    else group["ape_pct"].to_numpy(dtype=float)
                )
                axis.plot(
                    group["sample_size"],
                    y_values,
                    marker="o",
                    lw=1.5,
                    color=STRATEGY_COLORS[strategy],
                    label=STRATEGY_LABELS[strategy],
                )
            axis.set_title(f"{city} — {'daily median' if time_aggregation == 'daily' else 'study-period'}")
            axis.set_xlabel("Number of sensors")
            axis.set_ylabel("APE (%)")
            axis.grid(True, color=GRID_COLOR, lw=0.5)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False)
    fig.suptitle("Placement strategy performance versus random-subnetwork Monte Carlo")
    save_figure(fig, PLOT_DIR / "placement_strategy_performance_by_n")


def plot_n10_bar(performance: pd.DataFrame) -> None:
    frame = performance[performance["sample_size"] == MAP_SAMPLE_SIZE].copy()
    strategies = ["random_fixed_mc", "random_fixed", "max_ess", "min_pred_var", "min_ess"]
    cities = ["Dhaka", "Lucknow", "Chicago"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), constrained_layout=True)
    for axis, time_aggregation in zip(axes, ["daily", "period"]):
        width = 0.15
        x = np.arange(len(cities))
        for offset_index, strategy in enumerate(strategies):
            values: list[float] = []
            for city in cities:
                row = frame[
                    (frame["city"] == city)
                    & (frame["time_aggregation"] == time_aggregation)
                    & (frame["strategy"] == strategy)
                ]
                if row.empty:
                    values.append(np.nan)
                elif time_aggregation == "daily":
                    values.append(float(row.iloc[0]["ape_median_pct"]))
                else:
                    values.append(float(row.iloc[0]["ape_pct"]))
            axis.bar(
                x + (offset_index - 2) * width,
                values,
                width=width,
                color=STRATEGY_COLORS[strategy],
                label=STRATEGY_LABELS[strategy],
                alpha=0.88,
            )
        axis.set_xticks(x)
        axis.set_xticklabels(cities)
        axis.set_ylabel("APE (%)")
        axis.set_title("Daily median MdAPE" if time_aggregation == "daily" else "Study-period APE")
        axis.grid(True, axis="y", color=GRID_COLOR, lw=0.5)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False)
    fig.suptitle("n=10 placement strategy performance")
    save_figure(fig, PLOT_DIR / "placement_strategy_performance_n10_bar")


def expanded_extent(bounds: tuple[float, float, float, float], latitudes: np.ndarray, longitudes: np.ndarray) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    minx = min(minx, float(np.nanmin(longitudes)))
    maxx = max(maxx, float(np.nanmax(longitudes)))
    miny = min(miny, float(np.nanmin(latitudes)))
    maxy = max(maxy, float(np.nanmax(latitudes)))
    xpad = (maxx - minx) * 0.08 or 0.01
    ypad = (maxy - miny) * 0.08 or 0.01
    return minx - xpad, miny - ypad, maxx + xpad, maxy + ypad


def plot_strategy_maps(selections: list[StrategySelection], bundles: dict[str, DatasetBundle]) -> None:
    setup_matplotlib()
    strategies = ["random_fixed", "max_ess", "min_pred_var", "min_ess"]
    city_order = list(PRIMARY_DATASETS)
    selection_lookup = {
        (selection.dataset_key, selection.sample_size, selection.strategy): set(selection.sensor_ids)
        for selection in selections
    }
    fig, axes = plt.subplots(len(city_order), len(strategies), figsize=(14.8, 10.6), constrained_layout=False)
    for row_index, dataset_key in enumerate(city_order):
        bundle = bundles[dataset_key]
        config = MAP_CONFIGS[dataset_key]
        selected_color = color_for_dataset(dataset_key)
        city_geojson = load_geojson(REPO_ROOT / "data/geo" / config["city_file"])
        district_geojson = load_geojson(REPO_ROOT / "data/geo" / config["district_file"])
        bounds = geojson_bounds(district_geojson)
        latitudes = np.asarray(bundle.latitudes, dtype=float)
        longitudes = np.asarray(bundle.longitudes, dtype=float)
        extent = expanded_extent(bounds, latitudes, longitudes)
        locations = pd.DataFrame(
            {
                "Sensor_ID": bundle.sensor_ids,
                "Latitude": latitudes,
                "Longitude": longitudes,
            }
        )
        for column_index, strategy in enumerate(strategies):
            axis = axes[row_index, column_index]
            axis.add_patch(
                polygon_patch(
                    city_geojson,
                    facecolor=selected_color,
                    edgecolor=selected_color,
                    alpha=0.13,
                    linewidth=0.85,
                    zorder=1,
                )
            )
            axis.add_patch(
                polygon_patch(
                    district_geojson,
                    facecolor="none",
                    edgecolor=selected_color,
                    linewidth=0.9,
                    alpha=0.88,
                    zorder=2,
                )
            )
            axis.scatter(
                locations["Longitude"],
                locations["Latitude"],
                s=11 if dataset_key.startswith("chicago") else 18,
                color="#9ca3af",
                alpha=0.45,
                linewidths=0,
                zorder=3,
            )
            selected = locations[
                locations["Sensor_ID"].astype(str).isin(
                    selection_lookup[(dataset_key, MAP_SAMPLE_SIZE, strategy)]
                )
            ]
            axis.scatter(
                selected["Longitude"],
                selected["Latitude"],
                s=78 if dataset_key.startswith("chicago") else 92,
                color=selected_color,
                edgecolors="white",
                linewidths=0.75,
                zorder=4,
            )
            axis.set_xlim(extent[0], extent[2])
            axis.set_ylim(extent[1], extent[3])
            axis.set_aspect("equal", adjustable="box")
            axis.grid(True, color=GRID_COLOR, lw=0.28)
            axis.set_xticks([])
            axis.set_yticks([])
            if row_index == 0:
                axis.set_title(STRATEGY_LABELS[strategy], fontsize=11, pad=8)
            if column_index == 0:
                axis.text(
                    -0.04,
                    0.5,
                    bundle.spec.city,
                    transform=axis.transAxes,
                    rotation=90,
                    va="center",
                    ha="right",
                    fontsize=11,
                    fontweight="bold",
                )
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#9ca3af", markersize=6, label="All sensors"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=color_for_dataset("dhaka_lcs"),
            markeredgecolor="white",
            markersize=8,
            label="Dhaka selected",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=color_for_dataset("lucknow_lcs"),
            markeredgecolor="white",
            markersize=8,
            label="Lucknow selected",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=color_for_dataset("chicago_lcs_corrected_no_collocation"),
            markeredgecolor="white",
            markersize=8,
            label="Chicago selected",
        ),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.018))
    fig.suptitle(f"Placement strategy subsets at n={MAP_SAMPLE_SIZE}", y=0.985, fontsize=12)
    fig.subplots_adjust(left=0.055, right=0.995, top=0.91, bottom=0.095, wspace=0.025, hspace=0.075)
    save_figure(fig, PLOT_DIR / "placement_strategy_maps_n10")


def write_markdown(
    performance: pd.DataFrame,
    delta: pd.DataFrame,
    spatial_scores: pd.DataFrame,
    output_path: Path,
) -> None:
    n10_delta = delta[delta["sample_size"] == MAP_SAMPLE_SIZE].copy()
    n10_delta = n10_delta.sort_values(["time_aggregation", "city", "ape_delta_vs_random_pct_points"])
    daily_winners = (
        n10_delta[n10_delta["time_aggregation"] == "daily"]
        .sort_values("ape_delta_vs_random_pct_points")
        .groupby("city", as_index=False)
        .first()
    )
    period_winners = (
        n10_delta[n10_delta["time_aggregation"] == "period"]
        .sort_values("ape_delta_vs_random_pct_points")
        .groupby("city", as_index=False)
        .first()
    )

    def table(frame: pd.DataFrame, columns: list[str]) -> str:
        if frame.empty:
            return "_No rows._"
        out = frame[columns].copy()
        for column in out.columns:
            out[column] = out[column].map(lambda value: f"{value:.3f}" if isinstance(value, (float, np.floating)) else str(value))
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        rows = ["| " + " | ".join(row) + " |" for row in out.astype(str).to_numpy()]
        return "\n".join([header, sep, *rows])

    markdown = f"""# Placement Design Analysis

Generated by `analysis/scripts/build_placement_design_analysis.py`.

## Method

- Strategies tested: deterministic random subset, maximum effective sample size, minimum predictive variance, and minimum effective sample size.
- The model-based placement scores use an exponential spatial correlation model, `corr(d) = exp(-d / 10 km)`.
- `max_ess` maximizes `1' R^-1 1` greedily.
- `min_ess` intentionally selects a highly redundant/clustered subset as a worst-case spatial design.
- `min_pred_var` greedily maximizes block-prediction information over quadrature points inside the sensor convex hull.
- Empirical performance is measured against the deployed-network reference mean, using the actual PM2.5 data. This is separate from the model-based placement objective.

## n=10 Best Deterministic Strategy Versus Fixed-Random MC Baseline

### Daily Median MdAPE

{table(daily_winners, ["city", "strategy_label", "ape_value_pct", "random_mc_ape_value_pct", "ape_delta_vs_random_pct_points", "beats_random_by_ape"])}

### Study-Period APE

{table(period_winners, ["city", "strategy_label", "ape_value_pct", "random_mc_ape_value_pct", "ape_delta_vs_random_pct_points", "beats_random_by_ape"])}

## Interpretation

- These results test Reviewer 3's concern directly: a spatial design objective does not automatically guarantee lower empirical PM2.5 mean error.
- If a deterministic strategy has positive `ape_delta_vs_random_pct_points`, it performed worse than the random Monte Carlo median for that city, `n`, and time scale.
- The primary baseline is `random_fixed_mc`: 10,000 fixed random subnetworks evaluated across the full daily or study-period series. The daywise SRSWOR Monte Carlo baseline is retained in the CSV as context but is not the primary placement-design comparator.
- `min_ess` is included as a deliberately clustered stress-test, not as a recommended design.
- The analysis is exploratory because the placement strategies are selected from observed deployment locations; they do not optimize over all possible city locations.

## Output Inventory

- `placement_strategy_selected_sensors.csv`: one row per selected sensor and strategy.
- `placement_strategy_spatial_scores.csv`: ESS, pairwise-distance, centroid, and convex-hull metrics for each selected subset.
- `placement_strategy_daily_errors.csv`: daily error time series for deterministic strategy subsets.
- `placement_strategy_period_errors.csv`: period/study-period error for deterministic strategy subsets.
- `placement_strategy_performance_summary.csv`: deterministic, fixed-random MC, and daywise-random MC baseline performance summaries.
- `placement_strategy_vs_random_summary.csv`: deterministic strategy deltas versus fixed-random MC median baseline.
- `placement_strategy_maps_n10.*`: map panels for all cities and strategies at `n=10`.
- `placement_strategy_performance_n10_bar.*`: n=10 performance comparison.
- `placement_strategy_performance_by_n.*`: n=5/10/20 sensitivity curves.
"""
    output_path.write_text(markdown)


def main() -> None:
    setup_matplotlib()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    selections, spatial_scores, bundles = build_selections()
    daily_errors, period_errors, performance = summarize_performance(selections, bundles)
    delta = performance_delta(performance)

    selected_rows: list[dict[str, Any]] = []
    for selection in selections:
        bundle = bundles[selection.dataset_key]
        for index, sensor_index in enumerate(selection.sensor_indices, start=1):
            selected_rows.append(
                {
                    "dataset_key": selection.dataset_key,
                    "city": selection.city,
                    "sample_size": selection.sample_size,
                    "strategy": selection.strategy,
                    "strategy_label": STRATEGY_LABELS[selection.strategy],
                    "selection_order": index,
                    "sensor_index": int(sensor_index),
                    "sensor_id": bundle.sensor_ids[sensor_index],
                    "station_name": bundle.station_names[sensor_index],
                    "latitude": float(bundle.latitudes[sensor_index]),
                    "longitude": float(bundle.longitudes[sensor_index]),
                }
            )
    selected = pd.DataFrame(selected_rows)
    selected.to_csv(OUTPUT_DIR / "placement_strategy_selected_sensors.csv", index=False)
    spatial_scores.to_csv(OUTPUT_DIR / "placement_strategy_spatial_scores.csv", index=False)
    daily_errors.to_csv(OUTPUT_DIR / "placement_strategy_daily_errors.csv", index=False)
    period_errors.to_csv(OUTPUT_DIR / "placement_strategy_period_errors.csv", index=False)
    performance.to_csv(OUTPUT_DIR / "placement_strategy_performance_summary.csv", index=False)
    delta.to_csv(OUTPUT_DIR / "placement_strategy_vs_random_summary.csv", index=False)

    plot_strategy_maps(selections, bundles)
    plot_n10_bar(performance)
    plot_performance_by_n(performance)
    write_markdown(performance, delta, spatial_scores, OUTPUT_DIR / "placement_design_analysis.md")

    metadata = {
        "script": "analysis/scripts/build_placement_design_analysis.py",
        "master_seed": MASTER_SEED,
        "length_scale_km": DEFAULT_LENGTH_SCALE_KM,
        "sample_sizes": list(SAMPLE_SIZES),
        "map_sample_size": MAP_SAMPLE_SIZE,
        "datasets": list(PRIMARY_DATASETS),
        "strategies": STRATEGY_LABELS,
        "outputs": {
            "results_dir": str(OUTPUT_DIR.relative_to(REPO_ROOT)),
            "plots_dir": str(PLOT_DIR.relative_to(REPO_ROOT)),
        },
        "method_caveats": [
            "Placement objectives are optimized over existing deployment locations only.",
            "The exponential covariance model uses a fixed 10 km correlation length for the primary comparison.",
            "Primary placement baseline is 10,000 fixed random subnetworks evaluated across the full daily/study-period series.",
            "The existing daywise SRSWOR Monte Carlo baseline is retained as context but is not the primary fixed-design comparator.",
        ],
    }
    (OUTPUT_DIR / "placement_design_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Wrote placement design results to {OUTPUT_DIR}")
    print(f"Wrote placement design plots to {PLOT_DIR}")


if __name__ == "__main__":
    main()
