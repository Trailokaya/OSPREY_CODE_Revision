from __future__ import annotations

import json
import math
import os
import hashlib
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import (  # noqa: E402
    CITY_COLORS,
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    SAMPLE_SIZE_COLORS,
    TEXT_COLOR,
    city_key_from_dataset,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


RESULT_DIR = REPO_ROOT / "analysis/results/regression_clustering_diagnostics"
PLOT_DIR = REPO_ROOT / "analysis/plots/regression_clustering_diagnostics"

DAILY_METRICS_PATH = (
    REPO_ROOT / "analysis/results/three_city_comparative_analysis/comparative_daily_city_metrics.csv"
)
SENSOR_SUMMARY_PATH = (
    REPO_ROOT / "analysis/results/three_city_comparative_analysis/comparative_sensor_level_summary.csv"
)
SPATIAL_SUPPORT_PATH = (
    REPO_ROOT / "analysis/results/three_city_comparative_analysis/comparative_spatial_support_summary.csv"
)
DAILY_ERROR_PATH = REPO_ROOT / "monte_carlo/plots/figure_data/daily_error_timeseries_selected_n.csv"
PERIOD_ERROR_PATH = REPO_ROOT / "monte_carlo/plots/figure_data/period_error_curves.csv"
SPATIAL_DISTANCE_PATH = (
    REPO_ROOT / "spatial/results/distance_correlation/spatial_distance_relation_summary.csv"
)
SPATIAL_MORAN_PATH = REPO_ROOT / "spatial/results/distance_correlation/spatial_morans_i_summary.csv"

MASTER_SEED = 20260525
CLUSTER_SEED = 2026052501
PERMUTATION_SEED = 2026052502


@dataclass(frozen=True)
class KMeansResult:
    labels: np.ndarray
    centers: np.ndarray
    inertia: float
    iterations: int
    seed: int


def stable_int_hash(text: str, modulo: int | None = None) -> int:
    value = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
    return value % modulo if modulo is not None else value


def read_required_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    return pd.read_csv(path)


def finite_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan).dropna(subset=columns)


def zscore(values: np.ndarray, mean: np.ndarray | None = None, std: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        n_columns = arr.shape[1] if arr.ndim == 2 else 0
        if mean is None:
            mean = np.zeros(n_columns, dtype=float)
        if std is None:
            std = np.ones(n_columns, dtype=float)
        return arr, mean, std
    if mean is None:
        mean = np.nanmean(arr, axis=0)
    if std is None:
        std = np.nanstd(arr, axis=0, ddof=0)
    std = np.where(np.isfinite(std) & (std > 0), std, 1.0)
    return (arr - mean) / std, mean, std


def is_binary_series(values: pd.Series) -> bool:
    unique = set(pd.to_numeric(values, errors="coerce").dropna().unique().tolist())
    return unique.issubset({0, 1, 0.0, 1.0})


def design_matrix(
    frame: pd.DataFrame,
    features: list[str],
    train_stats: dict[str, tuple[float, float]] | None = None,
) -> tuple[np.ndarray, dict[str, tuple[float, float]]]:
    matrix_parts: list[np.ndarray] = [np.ones((len(frame), 1), dtype=float)]
    stats: dict[str, tuple[float, float]] = {}
    for feature in features:
        values = pd.to_numeric(frame[feature], errors="coerce").to_numpy(dtype=float)
        if train_stats is not None and feature in train_stats:
            mean, std = train_stats[feature]
        elif is_binary_series(frame[feature]):
            mean, std = 0.0, 1.0
        else:
            mean = float(np.nanmean(values))
            std = float(np.nanstd(values, ddof=0))
            if not np.isfinite(std) or std <= 0:
                std = 1.0
        stats[feature] = (mean, std)
        matrix_parts.append(((values - mean) / std).reshape(-1, 1))
    return np.hstack(matrix_parts), stats


def ols_coefficients(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(x, y, rcond=None)[0]


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray, n_features: int) -> dict[str, float]:
    residual = y_true - y_pred
    sse = float(np.sum(residual**2))
    sst = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else np.nan
    rmse = float(np.sqrt(np.mean(residual**2)))
    mae = float(np.mean(np.abs(residual)))
    n = len(y_true)
    adjusted_r2 = np.nan
    if n > n_features + 1 and np.isfinite(r2):
        adjusted_r2 = 1.0 - (1.0 - r2) * (n - 1) / (n - n_features - 1)
    return {"r2": r2, "adjusted_r2": adjusted_r2, "rmse": rmse, "mae": mae}


def deterministic_folds(frame: pd.DataFrame, n_folds: int = 5) -> np.ndarray:
    key = (
        frame["dataset_key"].astype(str)
        + "|"
        + frame.get("date", frame.index.to_series()).astype(str)
        + "|"
        + frame.get("sample_size", pd.Series("", index=frame.index)).astype(str)
    )
    return key.apply(lambda text: stable_int_hash(text, n_folds)).to_numpy(dtype=int)


def fit_ols_with_cv(
    frame: pd.DataFrame,
    features: list[str],
    target: str,
    model_name: str,
    n_folds: int = 5,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    needed = [*features, target]
    model_frame = finite_frame(frame, needed).reset_index(drop=True)
    y = pd.to_numeric(model_frame[target], errors="coerce").to_numpy(dtype=float)
    x, stats = design_matrix(model_frame, features)
    beta = ols_coefficients(x, y)
    pred = x @ beta
    full_metrics = regression_metrics(y, pred, len(features))

    folds = deterministic_folds(model_frame, n_folds=n_folds)
    oof_pred = np.full(len(model_frame), np.nan, dtype=float)
    for fold in range(n_folds):
        test_mask = folds == fold
        train_mask = ~test_mask
        if train_mask.sum() <= len(features) + 1 or test_mask.sum() == 0:
            continue
        x_train, train_stats = design_matrix(model_frame.loc[train_mask], features)
        y_train = y[train_mask]
        beta_train = ols_coefficients(x_train, y_train)
        x_test, _ = design_matrix(model_frame.loc[test_mask], features, train_stats=train_stats)
        oof_pred[test_mask] = x_test @ beta_train

    cv_mask = np.isfinite(oof_pred)
    cv_metrics = regression_metrics(y[cv_mask], oof_pred[cv_mask], len(features)) if cv_mask.any() else {
        "r2": np.nan,
        "adjusted_r2": np.nan,
        "rmse": np.nan,
        "mae": np.nan,
    }

    summary = {
        "model_name": model_name,
        "target": target,
        "features": ", ".join(features),
        "n_rows": int(len(model_frame)),
        "n_features": int(len(features)),
        "full_r2": full_metrics["r2"],
        "full_adjusted_r2": full_metrics["adjusted_r2"],
        "full_rmse": full_metrics["rmse"],
        "full_mae": full_metrics["mae"],
        "cv_r2": cv_metrics["r2"],
        "cv_adjusted_r2": cv_metrics["adjusted_r2"],
        "cv_rmse": cv_metrics["rmse"],
        "cv_mae": cv_metrics["mae"],
    }

    coefficient_rows = [
        {
            "model_name": model_name,
            "target": target,
            "feature": "intercept",
            "coefficient": float(beta[0]),
            "standardization_mean": np.nan,
            "standardization_sd": np.nan,
        }
    ]
    for index, feature in enumerate(features, start=1):
        coefficient_rows.append(
            {
                "model_name": model_name,
                "target": target,
                "feature": feature,
                "coefficient": float(beta[index]),
                "standardization_mean": stats[feature][0],
                "standardization_sd": stats[feature][1],
            }
        )

    prediction_frame = model_frame.copy()
    prediction_frame["model_name"] = model_name
    prediction_frame["target"] = target
    prediction_frame["observed"] = y
    prediction_frame["fitted"] = pred
    prediction_frame["oof_predicted"] = oof_pred
    prediction_frame["oof_residual"] = y - oof_pred
    prediction_frame["cv_fold"] = folds

    return summary, pd.DataFrame(coefficient_rows), prediction_frame


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


def nearest_neighbor_km(locations: pd.DataFrame) -> pd.Series:
    coords = locations[["latitude", "longitude"]].to_numpy(dtype=float)
    nearest: list[float] = []
    for index in range(len(coords)):
        distances = haversine_km(coords[index, 0], coords[index, 1], coords[:, 0], coords[:, 1])
        distances[index] = np.inf
        nearest.append(float(np.nanmin(distances)))
    return pd.Series(nearest, index=locations.index)


def pearson_r(x: np.ndarray, y: np.ndarray) -> float:
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_arr = x_arr[mask]
    y_arr = y_arr[mask]
    if len(x_arr) < 3 or np.nanstd(x_arr) == 0 or np.nanstd(y_arr) == 0:
        return np.nan
    return float(np.corrcoef(x_arr, y_arr)[0, 1])


def spearman_r(x: np.ndarray, y: np.ndarray) -> float:
    x_rank = pd.Series(x).rank(method="average").to_numpy(dtype=float)
    y_rank = pd.Series(y).rank(method="average").to_numpy(dtype=float)
    return pearson_r(x_rank, y_rank)


def permutation_p_value(
    x: np.ndarray,
    y: np.ndarray,
    observed: float,
    rng: np.random.Generator,
    n_permutations: int = 5000,
) -> float:
    if not np.isfinite(observed):
        return np.nan
    count = 0
    y_arr = np.asarray(y, dtype=float)
    for _ in range(n_permutations):
        permuted = rng.permutation(y_arr)
        permuted_r = spearman_r(x, permuted)
        if np.isfinite(permuted_r) and abs(permuted_r) >= abs(observed):
            count += 1
    return float((count + 1) / (n_permutations + 1))


def build_daily_model_frame() -> pd.DataFrame:
    daily_metrics = read_required_csv(DAILY_METRICS_PATH)
    spatial_support = read_required_csv(SPATIAL_SUPPORT_PATH)
    daily_error = read_required_csv(DAILY_ERROR_PATH)

    daily_metrics["date"] = pd.to_datetime(daily_metrics["date"], errors="coerce")
    daily_error["date"] = pd.to_datetime(daily_error["date"], errors="coerce")

    daily_error = daily_error[
        (daily_error["scenario"] == "S0_baseline")
        & (daily_error["estimator"] == "arithmetic_mean")
        & (daily_error["placement"] == "random_srswor")
    ].copy()

    merged = daily_error.merge(
        daily_metrics,
        on=["dataset_key", "city", "date"],
        how="left",
        validate="many_to_one",
    )
    merged = merged.merge(
        spatial_support,
        on=["dataset_key", "city"],
        how="left",
        validate="many_to_one",
        suffixes=("", "_support"),
    )

    merged["city_key"] = merged["dataset_key"].map(city_key_from_dataset)
    merged["city_Dhaka"] = (merged["city"] == "Dhaka").astype(int)
    merged["city_Lucknow"] = (merged["city"] == "Lucknow").astype(int)
    merged["city_Chicago"] = (merged["city"] == "Chicago").astype(int)
    merged["log_pm25"] = np.log1p(pd.to_numeric(merged["daily_reference_mean_ugm3"], errors="coerce"))
    merged["log_spatial_sd"] = np.log1p(pd.to_numeric(merged["daily_spatial_sd_ugm3"], errors="coerce"))
    merged["missing_pct"] = pd.to_numeric(merged["daily_missing_fraction"], errors="coerce") * 100.0
    merged["valid_sensor_fraction"] = (
        pd.to_numeric(merged["daily_valid_sensor_count"], errors="coerce")
        / pd.to_numeric(merged["retained_sensor_count"], errors="coerce")
    )
    merged["log_sensor_density"] = np.log1p(
        pd.to_numeric(merged["sensor_density_per_100_km2_hull"], errors="coerce")
    )
    merged["log_retained_sensor_count"] = np.log1p(
        pd.to_numeric(merged["retained_sensor_count"], errors="coerce")
    )
    merged["log_median_nearest_neighbor_km"] = np.log1p(
        pd.to_numeric(merged["median_nearest_neighbor_km"], errors="coerce")
    )
    merged["month"] = merged["date"].dt.month
    merged["season"] = merged["month"].map(month_to_season)
    return merged


def month_to_season(month: int | float) -> str:
    if not np.isfinite(month):
        return "unknown"
    month_int = int(month)
    if month_int in {12, 1, 2}:
        return "DJF"
    if month_int in {3, 4, 5}:
        return "MAM"
    if month_int in {6, 7, 8}:
        return "JJA"
    return "SON"


def build_period_model_frame() -> pd.DataFrame:
    period = read_required_csv(PERIOD_ERROR_PATH)
    spatial_support = read_required_csv(SPATIAL_SUPPORT_PATH)
    period = period[
        (period["scenario"] == "S0_baseline")
        & (period["estimator"] == "arithmetic_mean")
        & (period["placement"] == "random_srswor")
    ].copy()
    period = period.merge(spatial_support, on=["dataset_key", "city"], how="left", validate="many_to_one")
    period["city_Dhaka"] = (period["city"] == "Dhaka").astype(int)
    period["city_Lucknow"] = (period["city"] == "Lucknow").astype(int)
    period["city_Chicago"] = (period["city"] == "Chicago").astype(int)
    period["log_sample_size"] = np.log(pd.to_numeric(period["sample_size"], errors="coerce"))
    period["sampling_fraction"] = (
        pd.to_numeric(period["sample_size"], errors="coerce")
        / pd.to_numeric(period["n_sensors_available"], errors="coerce")
    )
    period["log_sensor_density"] = np.log1p(
        pd.to_numeric(period["sensor_density_per_100_km2_hull"], errors="coerce")
    )
    period["log_median_nearest_neighbor_km"] = np.log1p(
        pd.to_numeric(period["median_nearest_neighbor_km"], errors="coerce")
    )
    period["log_reference_sd"] = np.log1p(pd.to_numeric(period["reference_sd_ugm3"], errors="coerce"))
    period = period.rename(columns={"ape_median": "ape_median_pct", "absolute_median": "absolute_error_median_ugm3"})
    return period


def kmeans_plus_plus_init(x: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    n = x.shape[0]
    first = int(rng.integers(0, n))
    centers = [x[first]]
    closest_sq = np.sum((x - centers[0]) ** 2, axis=1)
    for _ in range(1, k):
        total = float(np.sum(closest_sq))
        if total <= 0 or not np.isfinite(total):
            next_index = int(rng.integers(0, n))
        else:
            probabilities = closest_sq / total
            next_index = int(rng.choice(n, p=probabilities))
        centers.append(x[next_index])
        closest_sq = np.minimum(closest_sq, np.sum((x - centers[-1]) ** 2, axis=1))
    return np.vstack(centers)


def run_kmeans(
    x: np.ndarray,
    k: int,
    seed: int,
    n_init: int = 40,
    max_iter: int = 300,
    tolerance: float = 1e-8,
) -> KMeansResult:
    rng = np.random.default_rng(seed)
    best: KMeansResult | None = None
    for init_index in range(n_init):
        init_seed = int(rng.integers(0, 2**32 - 1))
        init_rng = np.random.default_rng(init_seed)
        centers = kmeans_plus_plus_init(x, k, init_rng)
        labels = np.zeros(x.shape[0], dtype=int)
        iterations = 0
        for iterations in range(1, max_iter + 1):
            distances = np.sum((x[:, None, :] - centers[None, :, :]) ** 2, axis=2)
            new_labels = np.argmin(distances, axis=1)
            new_centers = centers.copy()
            for cluster_id in range(k):
                cluster_mask = new_labels == cluster_id
                if cluster_mask.any():
                    new_centers[cluster_id] = np.mean(x[cluster_mask], axis=0)
                else:
                    farthest_index = int(np.argmax(np.min(distances, axis=1)))
                    new_centers[cluster_id] = x[farthest_index]
            shift = float(np.max(np.sqrt(np.sum((new_centers - centers) ** 2, axis=1))))
            centers = new_centers
            labels = new_labels
            if shift < tolerance:
                break
        final_distances = np.sum((x[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        inertia = float(np.sum(np.min(final_distances, axis=1)))
        candidate = KMeansResult(labels=labels, centers=centers, inertia=inertia, iterations=iterations, seed=init_seed)
        if best is None or candidate.inertia < best.inertia:
            best = candidate
    if best is None:
        raise RuntimeError("K-means failed to produce a result.")
    return best


def silhouette_score(x: np.ndarray, labels: np.ndarray) -> float:
    unique_labels = np.unique(labels)
    if len(unique_labels) < 2 or len(unique_labels) >= len(labels):
        return np.nan
    distances = np.sqrt(np.sum((x[:, None, :] - x[None, :, :]) ** 2, axis=2))
    values: list[float] = []
    for index in range(len(labels)):
        same_mask = labels == labels[index]
        same_mask[index] = False
        if same_mask.any():
            a_value = float(np.mean(distances[index, same_mask]))
        else:
            a_value = 0.0
        b_values = [
            float(np.mean(distances[index, labels == other_label]))
            for other_label in unique_labels
            if other_label != labels[index] and np.any(labels == other_label)
        ]
        b_value = min(b_values) if b_values else 0.0
        denom = max(a_value, b_value)
        values.append((b_value - a_value) / denom if denom > 0 else 0.0)
    return float(np.mean(values))


def prepare_cluster_matrix(frame: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, np.ndarray]:
    clean = finite_frame(frame, features).reset_index(drop=True)
    matrix = clean[features].to_numpy(dtype=float)
    matrix, _, _ = zscore(matrix)
    return clean, matrix


def cluster_city_purity(labels: np.ndarray, cities: pd.Series) -> tuple[float, float, dict[int, str]]:
    mapping: dict[int, str] = {}
    correct = 0
    total = len(labels)
    for label in np.unique(labels):
        cluster_cities = cities.iloc[np.where(labels == label)[0]].astype(str)
        counts = Counter(cluster_cities)
        majority_city, majority_count = counts.most_common(1)[0]
        mapping[int(label)] = majority_city
        correct += majority_count
    accuracy = correct / total if total else np.nan
    weighted_purity = accuracy
    return float(weighted_purity), float(accuracy), mapping


def cluster_profiles(frame: pd.DataFrame, labels: np.ndarray, features: list[str], id_columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    out["cluster"] = labels
    profile_rows: list[dict[str, Any]] = []
    for cluster_id, group in out.groupby("cluster", sort=True):
        row: dict[str, Any] = {"cluster": int(cluster_id), "n_rows": int(len(group))}
        for column in id_columns:
            if column in group.columns:
                values = group[column].dropna().astype(str)
                row[f"{column}_mode"] = values.mode().iloc[0] if not values.empty else ""
        for feature in features:
            row[f"{feature}_mean"] = float(pd.to_numeric(group[feature], errors="coerce").mean())
            row[f"{feature}_median"] = float(pd.to_numeric(group[feature], errors="coerce").median())
        profile_rows.append(row)
    return pd.DataFrame(profile_rows)


def run_global_daily_clustering(daily_model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n10 = daily_model[daily_model["sample_size"] == 10].copy().reset_index(drop=True)
    feature_sets = {
        "environment_only": [
            "log_pm25",
            "log_spatial_sd",
            "daily_spatial_cv",
            "missing_pct",
            "valid_sensor_fraction",
            "log_sensor_density",
            "log_median_nearest_neighbor_km",
        ],
        "environment_plus_error_n10": [
            "log_pm25",
            "log_spatial_sd",
            "daily_spatial_cv",
            "missing_pct",
            "valid_sensor_fraction",
            "log_sensor_density",
            "log_median_nearest_neighbor_km",
            "ape_median_pct",
            "absolute_error_median_ugm3",
        ],
    }

    score_rows: list[dict[str, Any]] = []
    assignment_frames: list[pd.DataFrame] = []
    profile_frames: list[pd.DataFrame] = []
    for feature_set_name, features in feature_sets.items():
        clean, x = prepare_cluster_matrix(n10, features)
        results_by_k: dict[int, KMeansResult] = {}
        for k in range(2, 9):
            result = run_kmeans(x, k=k, seed=CLUSTER_SEED + k + len(feature_set_name))
            results_by_k[k] = result
            silhouette = silhouette_score(x, result.labels)
            purity, city_accuracy, _ = cluster_city_purity(result.labels, clean["city"])
            score_rows.append(
                {
                    "scope": "global_daily",
                    "feature_set": feature_set_name,
                    "k": k,
                    "n_rows": int(len(clean)),
                    "inertia": result.inertia,
                    "silhouette": silhouette,
                    "city_purity": purity,
                    "majority_city_prediction_accuracy": city_accuracy,
                    "seed_used": result.seed,
                    "iterations": result.iterations,
                }
            )
        score_frame = pd.DataFrame([row for row in score_rows if row["feature_set"] == feature_set_name])
        best_k = int(score_frame.sort_values(["silhouette", "city_purity"], ascending=[False, False]).iloc[0]["k"])
        selected_k_values = sorted(set([3, best_k]))
        for k in selected_k_values:
            result = results_by_k[k]
            _, _, mapping = cluster_city_purity(result.labels, clean["city"])
            assignment = clean[
                [
                    "dataset_key",
                    "city",
                    "date",
                    "sample_size",
                    "daily_reference_mean_ugm3",
                    "daily_spatial_cv",
                    "missing_pct",
                    "daily_valid_sensor_count",
                    "ape_median_pct",
                    "absolute_error_median_ugm3",
                ]
            ].copy()
            assignment["feature_set"] = feature_set_name
            assignment["k"] = k
            assignment["selection"] = "best_silhouette" if k == best_k else "k_equals_city_count"
            assignment["cluster"] = result.labels
            assignment["cluster_majority_city"] = [mapping[int(label)] for label in result.labels]
            assignment_frames.append(assignment)

            profile = cluster_profiles(
                clean,
                result.labels,
                [
                    "daily_reference_mean_ugm3",
                    "daily_spatial_sd_ugm3",
                    "daily_spatial_cv",
                    "missing_pct",
                    "valid_sensor_fraction",
                    "ape_median_pct",
                    "absolute_error_median_ugm3",
                ],
                ["city", "season"],
            )
            profile["scope"] = "global_daily"
            profile["feature_set"] = feature_set_name
            profile["k"] = k
            profile["selection"] = "best_silhouette" if k == best_k else "k_equals_city_count"
            profile_frames.append(profile)
    assignments = pd.concat(assignment_frames, ignore_index=True) if assignment_frames else pd.DataFrame()
    profiles = pd.concat(profile_frames, ignore_index=True) if profile_frames else pd.DataFrame()
    return pd.DataFrame(score_rows), assignments, profiles


def run_per_city_daily_clustering(daily_model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n10 = daily_model[daily_model["sample_size"] == 10].copy().reset_index(drop=True)
    features = [
        "log_pm25",
        "log_spatial_sd",
        "daily_spatial_cv",
        "missing_pct",
        "valid_sensor_fraction",
        "ape_median_pct",
        "absolute_error_median_ugm3",
    ]
    score_rows: list[dict[str, Any]] = []
    assignment_frames: list[pd.DataFrame] = []
    profile_frames: list[pd.DataFrame] = []
    for dataset_key, city_frame in n10.groupby("dataset_key", sort=True):
        clean, x = prepare_cluster_matrix(city_frame, features)
        city_name = str(city_frame["city"].dropna().iloc[0]) if city_frame["city"].notna().any() else str(dataset_key)
        max_k = min(8, len(clean) - 1)
        if max_k < 2:
            score_rows.append(
                {
                    "scope": "per_city_daily",
                    "dataset_key": dataset_key,
                    "city": city_name,
                    "feature_set": "daily_environment_plus_error_n10",
                    "k": np.nan,
                    "n_rows": int(len(clean)),
                    "inertia": np.nan,
                    "silhouette": np.nan,
                    "seed_used": np.nan,
                    "iterations": 0,
                    "skip_reason": "fewer_than_three_complete_rows",
                }
            )
            continue
        results_by_k: dict[int, KMeansResult] = {}
        for k in range(2, max_k + 1):
            result = run_kmeans(x, k=k, seed=CLUSTER_SEED + 1000 + k + stable_int_hash(dataset_key, 10000))
            results_by_k[k] = result
            score_rows.append(
                {
                    "scope": "per_city_daily",
                    "dataset_key": dataset_key,
                    "city": clean["city"].iloc[0],
                    "feature_set": "daily_environment_plus_error_n10",
                    "k": k,
                    "n_rows": int(len(clean)),
                    "inertia": result.inertia,
                    "silhouette": silhouette_score(x, result.labels),
                    "seed_used": result.seed,
                    "iterations": result.iterations,
                    "skip_reason": "",
                }
            )
        city_scores = pd.DataFrame(
            [
                row
                for row in score_rows
                if row["dataset_key"] == dataset_key and row["scope"] == "per_city_daily"
            ]
        ).dropna(subset=["silhouette"])
        if city_scores.empty:
            continue
        best_k = int(city_scores.sort_values("silhouette", ascending=False).iloc[0]["k"])
        result = results_by_k[best_k]
        assignment = clean[
            [
                "dataset_key",
                "city",
                "date",
                "daily_reference_mean_ugm3",
                "daily_spatial_cv",
                "missing_pct",
                "daily_valid_sensor_count",
                "ape_median_pct",
                "absolute_error_median_ugm3",
            ]
        ].copy()
        assignment["feature_set"] = "daily_environment_plus_error_n10"
        assignment["optimal_k"] = best_k
        assignment["cluster"] = result.labels
        assignment_frames.append(assignment)

        profile = cluster_profiles(
            clean,
            result.labels,
            [
                "daily_reference_mean_ugm3",
                "daily_spatial_sd_ugm3",
                "daily_spatial_cv",
                "missing_pct",
                "valid_sensor_fraction",
                "ape_median_pct",
                "absolute_error_median_ugm3",
            ],
            ["season"],
        )
        profile["scope"] = "per_city_daily"
        profile["dataset_key"] = dataset_key
        profile["city"] = clean["city"].iloc[0]
        profile["feature_set"] = "daily_environment_plus_error_n10"
        profile["optimal_k"] = best_k
        profile_frames.append(profile)
    assignments = pd.concat(assignment_frames, ignore_index=True) if assignment_frames else pd.DataFrame()
    profiles = pd.concat(profile_frames, ignore_index=True) if profile_frames else pd.DataFrame()
    return pd.DataFrame(score_rows), assignments, profiles


def build_sensor_frame() -> pd.DataFrame:
    sensors = read_required_csv(SENSOR_SUMMARY_PATH)
    sensors["latitude"] = pd.to_numeric(sensors["latitude"], errors="coerce")
    sensors["longitude"] = pd.to_numeric(sensors["longitude"], errors="coerce")
    parts: list[pd.DataFrame] = []
    for _, group in sensors.groupby("dataset_key", sort=True):
        group = group.copy().reset_index(drop=True)
        group["nearest_neighbor_km"] = nearest_neighbor_km(group)
        group["city_key"] = group["dataset_key"].map(city_key_from_dataset)
        group["log_longest_missing_gap_days"] = np.log1p(
            pd.to_numeric(group["longest_missing_gap_days"], errors="coerce")
        )
        group["log_nearest_neighbor_km"] = np.log1p(
            pd.to_numeric(group["nearest_neighbor_km"], errors="coerce")
        )
        parts.append(group)
    return pd.concat(parts, ignore_index=True)


def run_sensor_clustering(sensor_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features = [
        "latitude",
        "longitude",
        "period_mean_pm25_ugm3",
        "period_sd_daily_pm25_ugm3",
        "record_uptime_pct",
        "log_longest_missing_gap_days",
        "log_nearest_neighbor_km",
    ]
    score_rows: list[dict[str, Any]] = []
    assignment_frames: list[pd.DataFrame] = []
    profile_frames: list[pd.DataFrame] = []
    for dataset_key, city_frame in sensor_frame.groupby("dataset_key", sort=True):
        clean, x = prepare_cluster_matrix(city_frame, features)
        city_name = str(city_frame["city"].dropna().iloc[0]) if city_frame["city"].notna().any() else str(dataset_key)
        max_k = min(8, len(clean) - 1)
        if max_k < 2:
            score_rows.append(
                {
                    "scope": "sensor_level",
                    "dataset_key": dataset_key,
                    "city": city_name,
                    "feature_set": "location_pm_uptime_density",
                    "k": np.nan,
                    "n_rows": int(len(clean)),
                    "inertia": np.nan,
                    "silhouette": np.nan,
                    "seed_used": np.nan,
                    "iterations": 0,
                    "skip_reason": "fewer_than_three_complete_rows",
                }
            )
            continue
        results_by_k: dict[int, KMeansResult] = {}
        for k in range(2, max_k + 1):
            result = run_kmeans(x, k=k, seed=CLUSTER_SEED + 2000 + k + stable_int_hash(dataset_key, 10000))
            results_by_k[k] = result
            score_rows.append(
                {
                    "scope": "sensor_level",
                    "dataset_key": dataset_key,
                    "city": clean["city"].iloc[0],
                    "feature_set": "location_pm_uptime_density",
                    "k": k,
                    "n_rows": int(len(clean)),
                    "inertia": result.inertia,
                    "silhouette": silhouette_score(x, result.labels),
                    "seed_used": result.seed,
                    "iterations": result.iterations,
                    "skip_reason": "",
                }
            )
        city_scores = pd.DataFrame(
            [
                row
                for row in score_rows
                if row["dataset_key"] == dataset_key and row["scope"] == "sensor_level"
            ]
        ).dropna(subset=["silhouette"])
        if city_scores.empty:
            continue
        best_k = int(city_scores.sort_values("silhouette", ascending=False).iloc[0]["k"])
        result = results_by_k[best_k]
        assignment = clean[
            [
                "dataset_key",
                "city",
                "sensor_id",
                "station_name",
                "latitude",
                "longitude",
                "period_mean_pm25_ugm3",
                "record_uptime_pct",
                "daily_availability_pct",
                "longest_missing_gap_days",
                "nearest_neighbor_km",
            ]
        ].copy()
        assignment["feature_set"] = "location_pm_uptime_density"
        assignment["optimal_k"] = best_k
        assignment["cluster"] = result.labels
        assignment_frames.append(assignment)

        profile = cluster_profiles(
            clean,
            result.labels,
            [
                "latitude",
                "longitude",
                "period_mean_pm25_ugm3",
                "period_sd_daily_pm25_ugm3",
                "record_uptime_pct",
                "daily_availability_pct",
                "longest_missing_gap_days",
                "nearest_neighbor_km",
            ],
            [],
        )
        profile["scope"] = "sensor_level"
        profile["dataset_key"] = dataset_key
        profile["city"] = clean["city"].iloc[0]
        profile["feature_set"] = "location_pm_uptime_density"
        profile["optimal_k"] = best_k
        profile_frames.append(profile)
    return pd.DataFrame(score_rows), pd.concat(assignment_frames, ignore_index=True), pd.concat(profile_frames, ignore_index=True)


def build_sensor_density_relationships(sensor_frame: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(PERMUTATION_SEED)
    target_columns = [
        "period_mean_pm25_ugm3",
        "period_sd_daily_pm25_ugm3",
        "record_uptime_pct",
        "daily_availability_pct",
        "longest_missing_gap_days",
    ]
    rows: list[dict[str, Any]] = []
    for (dataset_key, city), group in sensor_frame.groupby(["dataset_key", "city"], sort=True):
        clean = finite_frame(group, ["nearest_neighbor_km", *target_columns])
        x = clean["nearest_neighbor_km"].to_numpy(dtype=float)
        for target in target_columns:
            y = clean[target].to_numpy(dtype=float)
            spearman = spearman_r(x, y)
            rows.append(
                {
                    "dataset_key": dataset_key,
                    "city": city,
                    "x": "nearest_neighbor_km",
                    "y": target,
                    "n_sensors": int(len(clean)),
                    "pearson_r": pearson_r(x, y),
                    "spearman_r": spearman,
                    "spearman_permutation_p_two_sided": permutation_p_value(
                        x, y, spearman, rng=rng, n_permutations=5000
                    ),
                    "x_median": float(np.nanmedian(x)),
                    "y_median": float(np.nanmedian(y)),
                }
            )
    return pd.DataFrame(rows)


def fit_regression_suite(daily_model: pd.DataFrame, period_model: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily_feature_sets = {
        "daily_error_city_only": ["city_Dhaka", "city_Lucknow"],
        "daily_error_environment": [
            "log_pm25",
            "log_spatial_sd",
            "daily_spatial_cv",
            "missing_pct",
            "valid_sensor_fraction",
        ],
        "daily_error_environment_support": [
            "log_pm25",
            "log_spatial_sd",
            "daily_spatial_cv",
            "missing_pct",
            "valid_sensor_fraction",
            "log_sensor_density",
            "log_median_nearest_neighbor_km",
            "log_retained_sensor_count",
        ],
        "daily_error_environment_city": [
            "log_pm25",
            "log_spatial_sd",
            "daily_spatial_cv",
            "missing_pct",
            "valid_sensor_fraction",
            "city_Dhaka",
            "city_Lucknow",
        ],
    }
    period_feature_sets = {
        "period_error_n_only": ["log_sample_size"],
        "period_error_n_fraction": ["log_sample_size", "sampling_fraction"],
        "period_error_n_city": ["log_sample_size", "sampling_fraction", "city_Dhaka", "city_Lucknow"],
        "period_error_n_support": [
            "log_sample_size",
            "sampling_fraction",
            "log_sensor_density",
            "log_median_nearest_neighbor_km",
            "log_reference_sd",
        ],
    }

    summaries: list[dict[str, Any]] = []
    coefficients: list[pd.DataFrame] = []
    predictions: list[pd.DataFrame] = []

    for sample_size in [5, 10, 20]:
        subset = daily_model[daily_model["sample_size"] == sample_size].copy()
        for target in ["ape_median_pct", "absolute_error_median_ugm3"]:
            for base_name, features in daily_feature_sets.items():
                model_name = f"{base_name}_n{sample_size}"
                summary, coef, pred = fit_ols_with_cv(subset, features, target, model_name)
                summary["sample_size"] = sample_size
                summary["time_scale"] = "daily"
                summaries.append(summary)
                coefficients.append(coef.assign(sample_size=sample_size, time_scale="daily"))
                predictions.append(pred.assign(sample_size=sample_size, time_scale="daily"))

    for target in ["ape_median_pct", "absolute_error_median_ugm3"]:
        for model_name, features in period_feature_sets.items():
            summary, coef, pred = fit_ols_with_cv(period_model, features, target, model_name)
            summary["sample_size"] = "all_period_n"
            summary["time_scale"] = "study_period"
            summaries.append(summary)
            coefficients.append(coef.assign(sample_size="all_period_n", time_scale="study_period"))
            predictions.append(pred.assign(sample_size="all_period_n", time_scale="study_period"))

    return pd.DataFrame(summaries), pd.concat(coefficients, ignore_index=True), pd.concat(predictions, ignore_index=True)


def pca_two_dimensions(x: np.ndarray) -> np.ndarray:
    centered = x - np.mean(x, axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ vt[:2].T


def plot_regression_observed_vs_predicted(predictions: pd.DataFrame) -> None:
    model_name = "daily_error_environment_city_n10"
    frame = predictions[
        (predictions["model_name"] == model_name)
        & (predictions["target"].isin(["ape_median_pct", "absolute_error_median_ugm3"]))
    ].copy()
    if frame.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    target_titles = {
        "ape_median_pct": "Median APE (%)",
        "absolute_error_median_ugm3": "Median absolute error (µg/m³)",
    }
    for axis, (target, group) in zip(axes, frame.groupby("target", sort=False)):
        for dataset_key, city_group in group.groupby("dataset_key", sort=True):
            color = color_for_dataset(dataset_key)
            axis.scatter(
                city_group["observed"],
                city_group["oof_predicted"],
                s=12,
                alpha=0.55,
                color=color,
                label=str(city_group["city"].iloc[0]),
                edgecolor="none",
            )
        finite = group[["observed", "oof_predicted"]].replace([np.inf, -np.inf], np.nan).dropna()
        if not finite.empty:
            low = float(min(finite["observed"].min(), finite["oof_predicted"].min()))
            high = float(max(finite["observed"].max(), finite["oof_predicted"].max()))
            axis.plot([low, high], [low, high], color=MUTED_TEXT_COLOR, lw=1, ls="--")
        axis.set_title(target_titles.get(target, target))
        axis.set_xlabel("Observed")
        axis.set_ylabel("Cross-validated prediction")
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle("Daily n=10 error regression: observed vs cross-validated fitted values")
    save_figure(fig, PLOT_DIR / "daily_regression_observed_vs_predicted_n10")


def plot_regression_coefficients(coefficients: pd.DataFrame) -> None:
    model_name = "daily_error_environment_city_n10"
    frame = coefficients[
        (coefficients["model_name"] == model_name)
        & (coefficients["target"] == "ape_median_pct")
        & (coefficients["feature"] != "intercept")
    ].copy()
    if frame.empty:
        return
    frame = frame.sort_values("coefficient")
    colors = ["#dc2626" if value > 0 else "#2563eb" for value in frame["coefficient"]]
    fig, axis = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    axis.barh(frame["feature"], frame["coefficient"], color=colors, alpha=0.85)
    axis.axvline(0, color=TEXT_COLOR, lw=0.8)
    axis.grid(True, axis="x", color=GRID_COLOR, lw=0.5)
    axis.set_xlabel("Coefficient in MdAPE percentage points")
    axis.set_title("Regression coefficients for daily n=10 MdAPE")
    save_figure(fig, PLOT_DIR / "daily_regression_coefficients_n10_mdape")


def plot_clustering_scores(scores: pd.DataFrame) -> None:
    global_scores = scores[scores["scope"] == "global_daily"].copy()
    if global_scores.empty:
        return
    feature_sets = list(global_scores["feature_set"].drop_duplicates())
    fig, axes = plt.subplots(1, len(feature_sets), figsize=(5 * len(feature_sets), 4), constrained_layout=True)
    if len(feature_sets) == 1:
        axes = [axes]
    for axis, feature_set in zip(axes, feature_sets):
        group = global_scores[global_scores["feature_set"] == feature_set].sort_values("k")
        axis.plot(group["k"], group["silhouette"], marker="o", color=TEXT_COLOR, label="silhouette")
        axis2 = axis.twinx()
        axis2.plot(
            group["k"],
            group["majority_city_prediction_accuracy"],
            marker="s",
            color="#dc2626",
            label="city majority accuracy",
        )
        axis.set_title(feature_set.replace("_", " "))
        axis.set_xlabel("k")
        axis.set_ylabel("Silhouette")
        axis2.set_ylabel("City prediction accuracy")
        axis.grid(True, color=GRID_COLOR, lw=0.5)
        axis.set_ylim(bottom=0)
        axis2.set_ylim(0, 1)
    fig.suptitle("Global daily clustering scores")
    save_figure(fig, PLOT_DIR / "global_daily_clustering_scores")


def plot_global_cluster_pca(assignments: pd.DataFrame, daily_model: pd.DataFrame) -> None:
    assignment = assignments[
        (assignments["feature_set"] == "environment_plus_error_n10")
        & (assignments["selection"] == "best_silhouette")
    ].copy()
    if assignment.empty:
        return
    features = [
        "log_pm25",
        "log_spatial_sd",
        "daily_spatial_cv",
        "missing_pct",
        "valid_sensor_fraction",
        "log_sensor_density",
        "log_median_nearest_neighbor_km",
        "ape_median_pct",
        "absolute_error_median_ugm3",
    ]
    source = daily_model[daily_model["sample_size"] == 10].copy()
    source = source.merge(
        assignment[["dataset_key", "date", "cluster"]],
        on=["dataset_key", "date"],
        how="inner",
        validate="one_to_one",
    )
    clean, x = prepare_cluster_matrix(source, features)
    coords = pca_two_dimensions(x)
    clean["pc1"] = coords[:, 0]
    clean["pc2"] = coords[:, 1]
    clean["cluster"] = source.loc[clean.index, "cluster"].to_numpy()

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    for dataset_key, group in clean.groupby("dataset_key", sort=True):
        axes[0].scatter(
            group["pc1"],
            group["pc2"],
            s=14,
            alpha=0.65,
            color=color_for_dataset(dataset_key),
            label=str(group["city"].iloc[0]),
            edgecolor="none",
        )
    for cluster_id, group in clean.groupby("cluster", sort=True):
        axes[1].scatter(
            group["pc1"],
            group["pc2"],
            s=14,
            alpha=0.65,
            label=f"Cluster {cluster_id}",
            edgecolor="none",
        )
    for axis in axes:
        axis.axhline(0, color=GRID_COLOR, lw=0.6)
        axis.axvline(0, color=GRID_COLOR, lw=0.6)
        axis.grid(True, color=GRID_COLOR, lw=0.5)
        axis.set_xlabel("PC1")
        axis.set_ylabel("PC2")
    axes[0].set_title("Colored by city")
    axes[1].set_title("Colored by cluster")
    axes[0].legend(frameon=False, loc="best")
    axes[1].legend(frameon=False, loc="best")
    fig.suptitle("Daily environment + n=10 error clustering projected to two dimensions")
    save_figure(fig, PLOT_DIR / "global_daily_cluster_pca_n10")


def plot_per_city_daily_cluster_profiles(profiles: pd.DataFrame) -> None:
    if profiles.empty:
        return
    cities = list(profiles[["dataset_key", "city"]].drop_duplicates().itertuples(index=False, name=None))
    fig, axes = plt.subplots(len(cities), 1, figsize=(8.5, 3.2 * len(cities)), constrained_layout=True)
    if len(cities) == 1:
        axes = [axes]
    for axis, (dataset_key, city) in zip(axes, cities):
        group = profiles[profiles["dataset_key"] == dataset_key].sort_values("cluster")
        x = np.arange(len(group))
        width = 0.36
        axis.bar(
            x - width / 2,
            group["daily_reference_mean_ugm3_mean"],
            width=width,
            color=color_for_dataset(dataset_key),
            alpha=0.8,
            label="mean PM2.5",
        )
        axis2 = axis.twinx()
        axis2.bar(
            x + width / 2,
            group["ape_median_pct_mean"],
            width=width,
            color="#dc2626",
            alpha=0.65,
            label="mean n=10 MdAPE",
        )
        axis.set_title(f"{city}: optimal daily clusters (k={int(group['optimal_k'].iloc[0])})")
        axis.set_xticks(x)
        axis.set_xticklabels([f"C{int(value)}\nN={int(n)}" for value, n in zip(group["cluster"], group["n_rows"])])
        axis.set_ylabel("PM2.5 (µg/m³)")
        axis2.set_ylabel("MdAPE (%)")
        axis.grid(True, axis="y", color=GRID_COLOR, lw=0.5)
    fig.suptitle("Per-city daily cluster profiles")
    save_figure(fig, PLOT_DIR / "per_city_daily_cluster_profiles_n10")


def plot_sensor_cluster_maps(assignments: pd.DataFrame) -> None:
    cities = list(assignments[["dataset_key", "city"]].drop_duplicates().itertuples(index=False, name=None))
    fig, axes = plt.subplots(1, len(cities), figsize=(5 * len(cities), 4.5), constrained_layout=True)
    if len(cities) == 1:
        axes = [axes]
    for axis, (dataset_key, city) in zip(axes, cities):
        group = assignments[assignments["dataset_key"] == dataset_key]
        for cluster_id, cluster_group in group.groupby("cluster", sort=True):
            axis.scatter(
                cluster_group["longitude"],
                cluster_group["latitude"],
                s=28,
                alpha=0.8,
                label=f"C{cluster_id}",
                edgecolor="white",
                linewidth=0.4,
            )
        axis.set_title(f"{city}: sensor clusters (k={int(group['optimal_k'].iloc[0])})")
        axis.set_xlabel("Longitude")
        axis.set_ylabel("Latitude")
        axis.grid(True, color=GRID_COLOR, lw=0.5)
        axis.legend(frameon=False, loc="best", ncol=2)
    fig.suptitle("Sensor-level clusters using location, PM2.5, uptime, and nearest-neighbor density")
    save_figure(fig, PLOT_DIR / "sensor_cluster_maps_by_city")


def plot_sensor_density_relationships(sensor_frame: pd.DataFrame) -> None:
    cities = list(sensor_frame[["dataset_key", "city"]].drop_duplicates().itertuples(index=False, name=None))
    fig, axes = plt.subplots(1, len(cities), figsize=(5 * len(cities), 4), constrained_layout=True)
    if len(cities) == 1:
        axes = [axes]
    for axis, (dataset_key, city) in zip(axes, cities):
        group = sensor_frame[sensor_frame["dataset_key"] == dataset_key]
        axis.scatter(
            group["nearest_neighbor_km"],
            group["period_mean_pm25_ugm3"],
            s=28,
            alpha=0.75,
            color=color_for_dataset(dataset_key),
            edgecolor="white",
            linewidth=0.4,
        )
        axis.set_title(city)
        axis.set_xlabel("Nearest-neighbor distance (km)")
        axis.set_ylabel("Sensor period mean PM2.5 (µg/m³)")
        axis.grid(True, color=GRID_COLOR, lw=0.5)
    fig.suptitle("Sensor density relation: nearest-neighbor distance versus period mean")
    save_figure(fig, PLOT_DIR / "sensor_density_vs_period_mean_pm25")


def plot_period_error_regression(predictions: pd.DataFrame) -> None:
    frame = predictions[
        (predictions["model_name"] == "period_error_n_city")
        & (predictions["target"] == "ape_median_pct")
    ].copy()
    if frame.empty:
        return
    fig, axis = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    for dataset_key, group in frame.groupby("dataset_key", sort=True):
        group = group.sort_values("sample_size")
        axis.plot(
            group["sample_size"],
            group["observed"],
            color=color_for_dataset(dataset_key),
            lw=1.8,
            label=f"{group['city'].iloc[0]} observed",
        )
        axis.plot(
            group["sample_size"],
            group["fitted"],
            color=color_for_dataset(dataset_key),
            lw=1.2,
            ls="--",
            alpha=0.8,
            label=f"{group['city'].iloc[0]} fitted",
        )
    axis.set_xlabel("Number of sensors")
    axis.set_ylabel("Study-period MdAPE (%)")
    axis.set_title("Regression fit for period error-versus-sensor-count curves")
    axis.grid(True, color=GRID_COLOR, lw=0.5)
    axis.legend(frameon=False, ncol=2)
    save_figure(fig, PLOT_DIR / "period_error_curve_regression_fit")


def simple_markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_No rows._"
    subset = frame[columns].copy()
    formatted = subset.astype(object).copy()
    for column in formatted.columns:
        formatted[column] = formatted[column].map(
            lambda value: f"{value:.3f}" if isinstance(value, (float, np.floating)) else str(value)
        )
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in formatted.astype(str).to_numpy()]
    return "\n".join([header, separator, *rows])


def write_markdown_summary(
    regression_summary: pd.DataFrame,
    global_scores: pd.DataFrame,
    per_city_scores: pd.DataFrame,
    sensor_scores: pd.DataFrame,
    sensor_density: pd.DataFrame,
    spatial_distance: pd.DataFrame,
    spatial_moran: pd.DataFrame,
    output_path: Path,
) -> None:
    def best_global(feature_set: str) -> pd.Series:
        subset = global_scores[global_scores["feature_set"] == feature_set]
        return subset.sort_values(["silhouette", "city_purity"], ascending=[False, False]).iloc[0]

    def best_per_city(scores: pd.DataFrame) -> pd.DataFrame:
        return (
            scores.sort_values("silhouette", ascending=False)
            .groupby(["dataset_key", "city"], as_index=False)
            .first()
            .sort_values("city")
        )

    daily_n10 = regression_summary[
        (regression_summary["time_scale"] == "daily")
        & (regression_summary["sample_size"].astype(str) == "10")
        & (regression_summary["target"] == "ape_median_pct")
    ].sort_values("cv_r2", ascending=False)
    period_mdape = regression_summary[
        (regression_summary["time_scale"] == "study_period")
        & (regression_summary["target"] == "ape_median_pct")
    ].sort_values("cv_r2", ascending=False)
    best_daily = daily_n10.iloc[0]
    best_period = period_mdape.iloc[0]
    env_global = best_global("environment_only")
    err_global = best_global("environment_plus_error_n10")
    city_daily_best = best_per_city(per_city_scores)
    sensor_best = best_per_city(sensor_scores)

    notable_density = sensor_density.reindex(
        sensor_density["spearman_r"].abs().sort_values(ascending=False).index
    ).head(8)

    spatial_lines: list[str] = []
    if not spatial_distance.empty:
        for _, row in spatial_distance[spatial_distance["resolution"].isin(["highest_hourly", "daily", "monthly", "period"])].iterrows():
            spatial_lines.append(
                f"- {row['city']} `{row['resolution']}`: median pairwise correlation "
                f"{row['median_pearson_correlation']:.3f}; Spearman distance-correlation "
                f"{row['spearman_distance_vs_correlation']:.3f}; median distance "
                f"{row['median_pairwise_distance_km']:.2f} km."
            )
    moran_lines: list[str] = []
    if not spatial_moran.empty:
        for _, row in spatial_moran[spatial_moran["resolution"].isin(["highest_hourly", "daily", "monthly", "period"])].iterrows():
            moran_lines.append(
                f"- {row['city']} `{row['resolution']}`: median kNN5 Moran's I "
                f"{row['median_morans_i_knn5']:.3f}."
            )

    markdown = f"""# Regression, Clustering, Density, and Spatial-Relation Diagnostics

Generated by `analysis/scripts/build_regression_clustering_diagnostics.py`.

## What Was Tested

- **Regression fitting:** OLS models tested whether daily and study-period Monte Carlo errors are explained by PM2.5 level, between-sensor spread, missingness, valid-sensor fraction, city, and spatial-support metrics.
- **City predictability from clustering:** K-means clusters were fit to daily network descriptors. City predictability is reported as cluster-majority city accuracy, not as a supervised classifier.
- **Optimal clustering:** K values were searched by silhouette score for global daily clustering, per-city daily clustering, and sensor-level clustering.
- **Density/spatial relations:** Sensor nearest-neighbor distance was related to period mean PM2.5, uptime, and gap metrics by Pearson/Spearman correlation with permutation p-values.

## Key Regression Results

- Best daily n=10 MdAPE model: `{best_daily['model_name']}` with cross-validated R² = {best_daily['cv_r2']:.3f}, RMSE = {best_daily['cv_rmse']:.3f} percentage points, MAE = {best_daily['cv_mae']:.3f}.
- Best study-period MdAPE model: `{best_period['model_name']}` with cross-validated R² = {best_period['cv_r2']:.3f}, RMSE = {best_period['cv_rmse']:.3f} percentage points, MAE = {best_period['cv_mae']:.3f}.
- Interpretation: regression is useful for explaining broad error structure, especially the sensor-count curve, but daily error still has substantial residual scatter because individual random subset composition matters.

## Global Daily Clustering

- Environment-only optimal k = {int(env_global['k'])}; silhouette = {env_global['silhouette']:.3f}; city-majority accuracy = {env_global['majority_city_prediction_accuracy']:.3f}.
- Environment + n=10 error optimal k = {int(err_global['k'])}; silhouette = {err_global['silhouette']:.3f}; city-majority accuracy = {err_global['majority_city_prediction_accuracy']:.3f}.
- Interpretation: if city-majority accuracy is high, clusters are mostly separating city/regime identity. That means clustering can help describe city regimes, but it is not independent proof that one universal clustering rule predicts all cities.

## Per-City Daily Clustering

{simple_markdown_table(city_daily_best, ['city', 'k', 'silhouette', 'n_rows'])}

## Sensor-Level Clustering

{simple_markdown_table(sensor_best, ['city', 'k', 'silhouette', 'n_rows'])}

Sensor clusters use location, period mean PM2.5, daily PM2.5 variability, uptime, longest gap, and nearest-neighbor distance. These clusters are exploratory; they are useful for finding sensor regimes, not for replacing design-based Monte Carlo.

## Strongest Sensor-Density Relationships

{simple_markdown_table(notable_density, ['city', 'x', 'y', 'n_sensors', 'spearman_r', 'spearman_permutation_p_two_sided'])}

## Existing Spatial Distance-Correlation Context

{os.linesep.join(spatial_lines[:18])}

## Existing Moran's I Context

{os.linesep.join(moran_lines[:18])}

## Output Inventory

- `daily_regression_model_summary.csv`: regression R²/RMSE/MAE by target, n, and feature set.
- `regression_coefficients.csv`: fitted coefficients; continuous predictors are standardized before fitting.
- `regression_predictions.csv`: fitted and cross-validated predictions.
- `period_error_curve_regression_summary.csv`: study-period error-versus-n regression summary.
- `global_daily_clustering_scores.csv`: k search for cross-city daily clustering.
- `global_daily_cluster_assignments.csv`: daily cluster labels for selected global cluster models.
- `global_daily_cluster_profiles.csv`: cluster-level means/medians for selected global cluster models.
- `per_city_daily_clustering_scores.csv`: per-city daily k search.
- `per_city_daily_cluster_assignments.csv`: daily cluster labels by city.
- `per_city_daily_cluster_profiles.csv`: per-city daily cluster profiles.
- `sensor_clustering_scores.csv`: sensor-level k search by city.
- `sensor_cluster_assignments.csv`: sensor-level cluster labels.
- `sensor_cluster_profiles.csv`: sensor-level cluster profiles.
- `sensor_density_relationships.csv`: nearest-neighbor density correlations with permutation p-values.
"""
    output_path.write_text(markdown)


def main() -> None:
    setup_matplotlib()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    daily_model = build_daily_model_frame()
    period_model = build_period_model_frame()
    sensor_frame = build_sensor_frame()

    regression_summary, regression_coefficients, regression_predictions = fit_regression_suite(
        daily_model=daily_model,
        period_model=period_model,
    )
    daily_regression_summary = regression_summary[regression_summary["time_scale"] == "daily"].copy()
    period_regression_summary = regression_summary[regression_summary["time_scale"] == "study_period"].copy()

    global_scores, global_assignments, global_profiles = run_global_daily_clustering(daily_model)
    per_city_scores, per_city_assignments, per_city_profiles = run_per_city_daily_clustering(daily_model)
    sensor_scores, sensor_assignments, sensor_profiles = run_sensor_clustering(sensor_frame)
    sensor_density = build_sensor_density_relationships(sensor_frame)

    spatial_distance = read_required_csv(SPATIAL_DISTANCE_PATH) if SPATIAL_DISTANCE_PATH.exists() else pd.DataFrame()
    spatial_moran = read_required_csv(SPATIAL_MORAN_PATH) if SPATIAL_MORAN_PATH.exists() else pd.DataFrame()

    daily_model.to_csv(RESULT_DIR / "daily_regression_model_input.csv", index=False)
    period_model.to_csv(RESULT_DIR / "period_regression_model_input.csv", index=False)
    sensor_frame.to_csv(RESULT_DIR / "sensor_density_model_input.csv", index=False)
    daily_regression_summary.to_csv(RESULT_DIR / "daily_regression_model_summary.csv", index=False)
    period_regression_summary.to_csv(RESULT_DIR / "period_error_curve_regression_summary.csv", index=False)
    regression_coefficients.to_csv(RESULT_DIR / "regression_coefficients.csv", index=False)
    regression_predictions.to_csv(RESULT_DIR / "regression_predictions.csv", index=False)
    global_scores.to_csv(RESULT_DIR / "global_daily_clustering_scores.csv", index=False)
    global_assignments.to_csv(RESULT_DIR / "global_daily_cluster_assignments.csv", index=False)
    global_profiles.to_csv(RESULT_DIR / "global_daily_cluster_profiles.csv", index=False)
    per_city_scores.to_csv(RESULT_DIR / "per_city_daily_clustering_scores.csv", index=False)
    per_city_assignments.to_csv(RESULT_DIR / "per_city_daily_cluster_assignments.csv", index=False)
    per_city_profiles.to_csv(RESULT_DIR / "per_city_daily_cluster_profiles.csv", index=False)
    sensor_scores.to_csv(RESULT_DIR / "sensor_clustering_scores.csv", index=False)
    sensor_assignments.to_csv(RESULT_DIR / "sensor_cluster_assignments.csv", index=False)
    sensor_profiles.to_csv(RESULT_DIR / "sensor_cluster_profiles.csv", index=False)
    sensor_density.to_csv(RESULT_DIR / "sensor_density_relationships.csv", index=False)

    plot_regression_observed_vs_predicted(regression_predictions)
    plot_regression_coefficients(regression_coefficients)
    combined_scores = pd.concat([global_scores, per_city_scores, sensor_scores], ignore_index=True, sort=False)
    plot_clustering_scores(combined_scores)
    plot_global_cluster_pca(global_assignments, daily_model)
    plot_per_city_daily_cluster_profiles(per_city_profiles)
    plot_sensor_cluster_maps(sensor_assignments)
    plot_sensor_density_relationships(sensor_frame)
    plot_period_error_regression(regression_predictions)

    write_markdown_summary(
        regression_summary=regression_summary,
        global_scores=global_scores,
        per_city_scores=per_city_scores,
        sensor_scores=sensor_scores,
        sensor_density=sensor_density,
        spatial_distance=spatial_distance,
        spatial_moran=spatial_moran,
        output_path=RESULT_DIR / "regression_clustering_diagnostics.md",
    )

    metadata = {
        "script": str(Path(__file__).relative_to(REPO_ROOT)),
        "master_seed": MASTER_SEED,
        "cluster_seed": CLUSTER_SEED,
        "permutation_seed": PERMUTATION_SEED,
        "inputs": {
            "daily_metrics": str(DAILY_METRICS_PATH.relative_to(REPO_ROOT)),
            "sensor_summary": str(SENSOR_SUMMARY_PATH.relative_to(REPO_ROOT)),
            "spatial_support": str(SPATIAL_SUPPORT_PATH.relative_to(REPO_ROOT)),
            "daily_error": str(DAILY_ERROR_PATH.relative_to(REPO_ROOT)),
            "period_error": str(PERIOD_ERROR_PATH.relative_to(REPO_ROOT)),
            "spatial_distance": str(SPATIAL_DISTANCE_PATH.relative_to(REPO_ROOT)),
            "spatial_moran": str(SPATIAL_MORAN_PATH.relative_to(REPO_ROOT)),
        },
        "outputs": {
            "results_dir": str(RESULT_DIR.relative_to(REPO_ROOT)),
            "plots_dir": str(PLOT_DIR.relative_to(REPO_ROOT)),
        },
        "method_notes": [
            "OLS uses least squares via numpy; continuous predictors are standardized before fitting.",
            "Cross-validation uses deterministic five-fold splits based on dataset/date/sample-size keys.",
            "K-means uses deterministic k-means++ initializations with multiple starts and silhouette-based k selection.",
            "Cluster-based city prediction is majority-label accuracy from unsupervised clusters, not a supervised classifier.",
            "Sensor-density p-values are permutation-based two-sided Spearman tests.",
        ],
    }
    (RESULT_DIR / "regression_clustering_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Wrote regression/clustering diagnostics to {RESULT_DIR}")
    print(f"Wrote plots to {PLOT_DIR}")


if __name__ == "__main__":
    main()
