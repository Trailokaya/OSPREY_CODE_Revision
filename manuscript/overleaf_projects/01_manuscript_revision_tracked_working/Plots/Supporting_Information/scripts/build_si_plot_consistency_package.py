from __future__ import annotations

import csv
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import to_rgba
import numpy as np
import pandas as pd
from scipy import stats


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "data" / "pm").is_dir() and (candidate / "paper").is_dir():
            return candidate
    raise RuntimeError("Could not locate repository root from script path.")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
SI_ROOT = REPO_ROOT / "manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information"
MAP_CSV = SI_ROOT / "SI_PLOT_LOCATION_MAP.csv"
MAP_MD = SI_ROOT / "SI_PLOT_LOCATION_MAP.md"
METADATA_JSON = SI_ROOT / "si_plot_consistency_metadata.json"

sys.path.insert(0, str(REPO_ROOT / "analysis/src"))
from plot_style import (  # noqa: E402
    BOUNDARY_FILL_COLOR,
    CITY_COLORS,
    DISTRICT_EDGE_COLOR,
    GRID_COLOR,
    OUTPUT_DPI,
    REFERENCE_LINE_COLOR,
    TEXT_COLOR,
    save_figure,
    setup_matplotlib,
)

sys.path.insert(0, str(REPO_ROOT / "maps/scripts"))
from build_network_maps import geojson_bounds, load_geojson, polygon_patch  # noqa: E402


@dataclass(frozen=True)
class NetworkSpec:
    key: str
    city: str
    pm_hourly: Path
    pm_daily: Path | None
    locations: Path
    exclude_collocation: bool = False


NETWORKS = (
    NetworkSpec(
        key="dhaka_lcs",
        city="Dhaka",
        pm_hourly=REPO_ROOT / "data/pm/Dhaka_hourly_PM25.csv",
        pm_daily=None,
        locations=REPO_ROOT / "data/locations/Dhaka_sensor_locations.csv",
    ),
    NetworkSpec(
        key="lucknow_lcs",
        city="Lucknow",
        pm_hourly=REPO_ROOT / "data/pm/Lucknow_hourly_PM25.csv",
        pm_daily=None,
        locations=REPO_ROOT / "data/locations/Lucknow_sensor_locations.csv",
    ),
    NetworkSpec(
        key="chicago_lcs_corrected_no_collocation",
        city="Chicago",
        pm_hourly=REPO_ROOT / "data/pm/Chicago_LCS_corrected_hourly_PM25.csv",
        pm_daily=REPO_ROOT / "data/pm/Chicago_LCS_corrected_daily_PM25.csv",
        locations=REPO_ROOT / "data/locations/Chicago_LCS_corrected_sensor_locations.csv",
        exclude_collocation=True,
    ),
)

MAP_GEOJSONS = {
    "Dhaka": {
        "city": REPO_ROOT / "data/geo/Dhaka_City_admin6.geojson",
        "district": REPO_ROOT / "data/geo/Dhaka_District_admin5.geojson",
    },
    "Lucknow": {
        "city": REPO_ROOT / "data/geo/Lucknow_City_admin6.geojson",
        "district": REPO_ROOT / "data/geo/Lucknow_District_admin5.geojson",
    },
    "Chicago": {
        "city": REPO_ROOT / "data/geo/Chicago_City_admin6.geojson",
        "district": REPO_ROOT / "data/geo/Chicago_District_admin5.geojson",
    },
}

PROMOTIONS = (
    {
        "figure": "SI 2",
        "role": "Chicago-inclusive empirical spatial-dependence companion",
        "source_base": REPO_ROOT / "spatial/plots/distance_correlation/empirical_variogram_binned_by_city",
        "target_base": SI_ROOT / "Figure_SI_2/three_city_empirical_variogram_binned_by_city",
        "source_data": "spatial/results/distance_correlation/spatial_distance_binned_summary.csv",
        "status": "preferred companion; does not replace original GP covariogram unless manuscript text is edited",
    },
    {
        "figure": "SI 2",
        "role": "Chicago-inclusive distance-correlation companion",
        "source_base": REPO_ROOT / "spatial/plots/distance_correlation/distance_correlation_binned_by_city",
        "target_base": SI_ROOT / "Figure_SI_2/three_city_distance_correlation_binned_by_city",
        "source_data": "spatial/results/distance_correlation/spatial_distance_binned_summary.csv",
        "status": "preferred companion",
    },
    {
        "figure": "SI 6",
        "role": "Three-city Gaussian RSE daily sensor requirement",
        "source_base": REPO_ROOT / "analysis/plots/estimator_diagnostics/SI_F6_RSE_normal_daily_sensor_requirement",
        "target_base": SI_ROOT / "Figure_SI_6/three_city_RSE_normal_daily_sensor_requirement",
        "source_data": "analysis/results/estimator_diagnostics/rse_daily_sensor_requirements.csv",
        "status": "preferred replacement",
    },
    {
        "figure": "SI 7",
        "role": "Three-city lognormal RSE daily sensor requirement",
        "source_base": REPO_ROOT / "analysis/plots/estimator_diagnostics/SI_F7_RSE_lognormal_daily_sensor_requirement",
        "target_base": SI_ROOT / "Figure_SI_7/three_city_RSE_lognormal_daily_sensor_requirement",
        "source_data": "analysis/results/estimator_diagnostics/rse_daily_sensor_requirements.csv",
        "status": "preferred replacement",
    },
    {
        "figure": "SI 8",
        "role": "Three-city RSE exceedance curves",
        "source_base": REPO_ROOT / "analysis/plots/estimator_diagnostics/SI_F8_RSE_exceedance_curves",
        "target_base": SI_ROOT / "Figure_SI_8/three_city_RSE_exceedance_curves",
        "source_data": "analysis/results/estimator_diagnostics/rse_exceedance_summary.csv",
        "status": "preferred replacement",
    },
    {
        "figure": "SI 9",
        "role": "Three-city estimator mean/SD comparison",
        "source_base": REPO_ROOT / "analysis/plots/estimator_comparison/SI_F9_daily_estimator_mean_sd_comparison",
        "target_base": SI_ROOT / "Figure_SI_9/three_city_daily_estimator_mean_sd_comparison",
        "source_data": "analysis/results/estimator_comparison/daily_full_network_estimator_summary.csv",
        "status": "preferred replacement",
    },
    {
        "figure": "SI 10",
        "role": "Three-city lognormal relative bias by n",
        "source_base": REPO_ROOT / "analysis/plots/estimator_comparison/SI_F10_lognormal_relative_bias_by_n",
        "target_base": SI_ROOT / "Figure_SI_10/three_city_lognormal_relative_bias_by_n",
        "source_data": "analysis/results/estimator_comparison/period_monte_carlo_estimator_summary.csv",
        "status": "preferred replacement",
    },
    {
        "figure": "SI 11",
        "role": "Three-city period sensor means with Bonferroni CIs",
        "source_base": REPO_ROOT / "analysis/plots/estimator_diagnostics/SI_F11_period_sensor_means_bonferroni_ci",
        "target_base": SI_ROOT / "Figure_SI_11/three_city_period_sensor_means_bonferroni_ci",
        "source_data": "analysis/results/estimator_diagnostics/si_f11_sensor_period_ci.csv",
        "status": "preferred replacement",
    },
)


def city_color(city: str) -> str:
    return CITY_COLORS[city.lower()]


def read_locations(spec: NetworkSpec) -> pd.DataFrame:
    locations = pd.read_csv(spec.locations, dtype={"Sensor_ID": str})
    if spec.exclude_collocation:
        locations = locations[
            ~locations["Station_Name"].astype(str).str.contains("collocation", case=False, na=False)
        ].copy()
    locations["Sensor_ID"] = locations["Sensor_ID"].astype(str)
    return locations.drop_duplicates("Sensor_ID").sort_values("Sensor_ID").reset_index(drop=True)


def read_matrix(path: Path, sensor_ids: list[str]) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0)
    timestamp_col = header.columns[0]
    keep = [sensor_id for sensor_id in sensor_ids if sensor_id in header.columns]
    frame = pd.read_csv(path, usecols=[timestamp_col, *keep])
    frame = frame.rename(columns={timestamp_col: "Timestamp"})
    frame["Timestamp"] = pd.to_datetime(frame["Timestamp"].astype(str).str.slice(0, 19), errors="coerce")
    for sensor_id in keep:
        frame[sensor_id] = pd.to_numeric(frame[sensor_id], errors="coerce")
    return frame


def load_network_panel(spec: NetworkSpec) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    locations = read_locations(spec)
    sensor_ids = locations["Sensor_ID"].tolist()
    hourly = read_matrix(spec.pm_hourly, sensor_ids)
    retained = [sensor_id for sensor_id in sensor_ids if sensor_id in hourly.columns]
    locations = locations.set_index("Sensor_ID").loc[retained].reset_index()
    hourly = hourly[["Timestamp", *retained]]
    if spec.pm_daily:
        daily = read_matrix(spec.pm_daily, retained)
        daily = daily[["Timestamp", *[sensor_id for sensor_id in retained if sensor_id in daily.columns]]]
    else:
        values = hourly.drop(columns="Timestamp")
        daily_values = values.groupby(hourly["Timestamp"].dt.date, sort=True).mean()
        daily = daily_values.reset_index().rename(columns={"Timestamp": "date"})
        daily = daily.rename(columns={"date": "Timestamp"})
        daily["Timestamp"] = pd.to_datetime(daily["Timestamp"])
    return locations, hourly, daily


def haversine_matrix(locations: pd.DataFrame) -> np.ndarray:
    lat = np.radians(locations["Latitude"].to_numpy(dtype=float))
    lon = np.radians(locations["Longitude"].to_numpy(dtype=float))
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(a))


def pairwise_distances(locations: pd.DataFrame) -> np.ndarray:
    distances = haversine_matrix(locations)
    return distances[np.triu_indices_from(distances, k=1)]


def knn_weights(distances: np.ndarray, k: int = 5) -> tuple[np.ndarray, np.ndarray]:
    weights = np.zeros_like(distances, dtype=bool)
    for index in range(distances.shape[0]):
        row = distances[index].copy()
        row[index] = np.inf
        nearest = np.argsort(row)[: min(k, distances.shape[0] - 1)]
        weights[index, nearest] = True
    return np.nonzero(weights)


def morans_i(values: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> float:
    valid = np.isfinite(values)
    if valid.sum() < 3:
        return float("nan")
    link_valid = valid[rows] & valid[cols]
    weight_sum = link_valid.sum()
    if weight_sum == 0:
        return float("nan")
    centered = values - np.nanmean(values)
    denominator = np.nansum(centered[valid] ** 2)
    if denominator == 0:
        return float("nan")
    numerator = np.sum(centered[rows[link_valid]] * centered[cols[link_valid]])
    return float(valid.sum() / weight_sum * numerator / denominator)


def sampled_windows(frame: pd.DataFrame, max_windows: int) -> pd.DataFrame:
    value_frame = frame.drop(columns="Timestamp").replace([np.inf, -np.inf], np.nan)
    value_frame = value_frame[value_frame.notna().sum(axis=1) >= 3]
    if len(value_frame) <= max_windows:
        return value_frame
    positions = np.unique(np.linspace(0, len(value_frame) - 1, max_windows, dtype=int))
    return value_frame.iloc[positions]


def permutation_standardized_moran(values: pd.DataFrame, locations: pd.DataFrame, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rows, cols = knn_weights(haversine_matrix(locations), k=5)
    z_values: list[float] = []
    for _, row in values.iterrows():
        vector = row.to_numpy(dtype=float)
        valid = np.isfinite(vector)
        observed = morans_i(vector, rows, cols)
        if not np.isfinite(observed):
            continue
        valid_values = vector[valid].copy()
        permuted = np.empty(199, dtype=float)
        for index in range(len(permuted)):
            shuffled = vector.copy()
            shuffled[valid] = rng.permutation(valid_values)
            permuted[index] = morans_i(shuffled, rows, cols)
        permuted = permuted[np.isfinite(permuted)]
        if len(permuted) < 10:
            continue
        sd = np.std(permuted, ddof=1)
        if sd == 0 or not np.isfinite(sd):
            continue
        z_values.append(float((observed - np.mean(permuted)) / sd))
    return np.asarray(z_values, dtype=float)


def plot_missingness_map(panels: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]) -> dict[str, str]:
    records = []
    for spec in NETWORKS:
        locations, hourly, _ = panels[spec.city]
        missing = hourly.drop(columns="Timestamp").isna().mean() * 100
        merged = locations.copy()
        merged["missing_pct"] = merged["Sensor_ID"].map(missing)
        records.append(merged.assign(city=spec.city))
    all_missing = pd.concat(records, ignore_index=True)
    vmax = float(np.nanpercentile(all_missing["missing_pct"], 98))
    vmax = max(vmax, 1.0)

    fig, axes = plt.subplots(1, 3, figsize=(11.0, 3.8), constrained_layout=True)
    scatter = None
    for axis, spec in zip(axes, NETWORKS, strict=True):
        data = all_missing[all_missing["city"] == spec.city]
        geojsons = MAP_GEOJSONS[spec.city]
        city_geojson = load_geojson(geojsons["city"])
        district_geojson = load_geojson(geojsons["district"])
        axis.add_patch(
            polygon_patch(
                district_geojson,
                facecolor="#f8fafc",
                edgecolor=city_color(spec.city),
                linewidth=0.7,
                alpha=0.35,
                zorder=0,
            )
        )
        axis.add_patch(
            polygon_patch(
                city_geojson,
                facecolor=to_rgba(BOUNDARY_FILL_COLOR, 0.35),
                edgecolor=city_color(spec.city),
                linewidth=1.1,
                zorder=1,
            )
        )
        scatter = axis.scatter(
            data["Longitude"],
            data["Latitude"],
            c=data["missing_pct"],
            cmap="magma_r",
            vmin=0,
            vmax=vmax,
            s=22 if spec.city != "Chicago" else 12,
            edgecolors=city_color(spec.city),
            linewidth=0.45 if spec.city != "Chicago" else 0.25,
            alpha=0.95,
            zorder=3,
        )
        minx, miny, maxx, maxy = geojson_bounds(district_geojson)
        minx = min(minx, float(data["Longitude"].min()))
        miny = min(miny, float(data["Latitude"].min()))
        maxx = max(maxx, float(data["Longitude"].max()))
        maxy = max(maxy, float(data["Latitude"].max()))
        xpad = max((maxx - minx) * 0.055, 0.008)
        ypad = max((maxy - miny) * 0.055, 0.008)
        axis.set_xlim(minx - xpad, maxx + xpad)
        axis.set_ylim(miny - ypad, maxy + ypad)
        axis.set_title(spec.city)
        axis.set_xlabel("")
        axis.set_ylabel("")
        axis.grid(True, color=GRID_COLOR, linewidth=0.5)
        axis.xaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
        axis.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
        axis.tick_params(labelbottom=False, labelleft=False, length=0)
        axis.set_aspect("equal", adjustable="box")
    colorbar = fig.colorbar(scatter, ax=axes, shrink=0.86, pad=0.02)
    colorbar.set_label("Missing hourly records (%)")
    output = SI_ROOT / "Figure_SI_1/three_city_missingness_spatial_map"
    return save_figure(fig, output, dpi=OUTPUT_DPI)


def plot_pairwise_distance_cdf(panels: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]) -> dict[str, str]:
    fig, axis = plt.subplots(figsize=(6.2, 3.9))
    for spec in NETWORKS:
        locations = panels[spec.city][0]
        distances = np.sort(pairwise_distances(locations))
        y = np.arange(1, len(distances) + 1) / len(distances) * 100
        axis.plot(distances, y, color=city_color(spec.city), linewidth=2.0, label=spec.city)
    for threshold in (2, 5, 10):
        axis.axvline(threshold, color=REFERENCE_LINE_COLOR, linestyle="--", linewidth=1.0)
        axis.text(threshold + 0.15, 96, f"{threshold} km", rotation=90, color="#6b7280", fontsize=8, va="top")
    axis.set_xlabel("Pairwise sensor distance (km)")
    axis.set_ylabel("Cumulative sensor pairs (%)")
    axis.set_xlim(left=0)
    axis.set_ylim(0, 100)
    axis.grid(True, color=GRID_COLOR, linewidth=0.6)
    axis.legend(frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5), borderaxespad=0)
    axis.set_title("Pairwise sensor-distance distribution")
    fig.subplots_adjust(left=0.12, right=0.78, bottom=0.18, top=0.90)
    output = SI_ROOT / "Figure_SI_3/three_city_cumulative_pairwise_distance"
    return save_figure(fig, output, dpi=OUTPUT_DPI)


def plot_moran_qq(
    panels: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]],
    resolution: str,
    max_windows: int,
    seed_offset: int,
) -> dict[str, str]:
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.5), sharex=True, sharey=True, constrained_layout=True)
    all_z: list[np.ndarray] = []
    by_city: dict[str, np.ndarray] = {}
    for spec in NETWORKS:
        locations, hourly, daily = panels[spec.city]
        frame = daily if resolution == "daily" else hourly
        z = permutation_standardized_moran(sampled_windows(frame, max_windows), locations, seed=20260525 + seed_offset)
        by_city[spec.city] = z
        all_z.append(z)
    combined = np.concatenate([z for z in all_z if len(z)])
    limit = max(3.0, float(np.nanpercentile(np.abs(combined), 98)) if len(combined) else 3.0)

    for axis, spec in zip(axes, NETWORKS, strict=True):
        z = np.sort(by_city[spec.city])
        quantiles = stats.norm.ppf((np.arange(1, len(z) + 1) - 0.5) / len(z)) if len(z) else np.array([])
        axis.scatter(quantiles, z, color=city_color(spec.city), s=12, alpha=0.75, edgecolor="none")
        axis.plot([-limit, limit], [-limit, limit], color="#4b5563", linestyle="--", linewidth=1.0)
        axis.set_title(f"{spec.city} (n={len(z)} windows)")
        axis.set_xlabel("Theoretical normal quantile")
        axis.grid(True, color=GRID_COLOR, linewidth=0.6)
        axis.set_xlim(-limit, limit)
        axis.set_ylim(-limit, limit)
    axes[0].set_ylabel("Empirical permutation-standardized Moran's I")
    title = "Daily" if resolution == "daily" else "Hourly"
    fig.suptitle(f"{title} Moran's I Q-Q diagnostic, kNN-5 weights")
    output = SI_ROOT / f"Figure_SI_{4 if resolution == 'daily' else 5}/three_city_{resolution}_morans_i_qq_knn5"
    return save_figure(fig, output, dpi=OUTPUT_DPI)


def copy_promoted_plots() -> list[dict[str, Any]]:
    rows = []
    for promotion in PROMOTIONS:
        copied = []
        for suffix in (".pdf", ".png"):
            source = promotion["source_base"].with_suffix(suffix)
            target = promotion["target_base"].with_suffix(suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not source.exists():
                raise FileNotFoundError(source)
            shutil.copy2(source, target)
            copied.append(str(target.relative_to(REPO_ROOT)))
        rows.append({**promotion, "output_pdf": copied[0], "output_png": copied[1]})
    return rows


def write_plot_map(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "figure",
        "role",
        "preferred_file",
        "png_file",
        "source_data",
        "status",
        "style_status",
        "latex_action",
    ]
    MAP_CSV.parent.mkdir(parents=True, exist_ok=True)
    with MAP_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    lines = [
        "# SI Plot Location Map",
        "",
        "This file maps the current Chicago-inclusive or Chicago-acknowledged SI plot assets to their intended manuscript locations.",
        "",
        "| Figure | Intended role | Preferred file | Source data | Status |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['figure']} | {row['role']} | `{row['preferred_file']}` | `{row['source_data']}` | {row['status']} |"
        )
    lines.extend(
        [
            "",
            "## Style Standard",
            "",
            "- New/generated figures use `analysis/src/plot_style.py` colors: Dhaka orange, Lucknow blue, Chicago green.",
            "- New/generated figures are saved as both PDF and PNG with `600` DPI PNG output.",
            "- Promoted figures were generated by the current analysis scripts using the same shared style module.",
            "- Legacy two-city files are retained for audit history, but the `preferred_file` column identifies the plot to use for Chicago-inclusive revision figures.",
            "",
        ]
    )
    MAP_MD.write_text("\n".join(lines))


def main() -> None:
    setup_matplotlib()
    panels = {spec.city: load_network_panel(spec) for spec in NETWORKS}
    map_rows: list[dict[str, Any]] = []

    generated = [
        {
            "figure": "SI 1",
            "role": "Three-city spatial missingness map",
            "outputs": plot_missingness_map(panels),
            "source_data": "data/pm/*_hourly_PM25.csv + data/locations/*_sensor_locations.csv",
            "status": "preferred replacement",
            "latex_action": "Replace Figure_SI_1/missingness_maps.pdf with this file if including Chicago in SI 1.",
        },
        {
            "figure": "SI 3",
            "role": "Three-city pairwise sensor-distance CDF",
            "outputs": plot_pairwise_distance_cdf(panels),
            "source_data": "data/locations/*_sensor_locations.csv",
            "status": "preferred replacement",
            "latex_action": "Replace Figure_SI_3/cumulative_pwod.pdf with this file if including Chicago in SI 3.",
        },
        {
            "figure": "SI 4",
            "role": "Three-city daily Moran's I Q-Q diagnostic",
            "outputs": plot_moran_qq(panels, resolution="daily", max_windows=240, seed_offset=4),
            "source_data": "data/pm/*_hourly_PM25.csv; Chicago uses official daily corrected file",
            "status": "preferred replacement/companion",
            "latex_action": "Use with caption noting kNN-5 permutation-standardized Moran's I and deterministic window cap.",
        },
        {
            "figure": "SI 5",
            "role": "Three-city hourly Moran's I Q-Q diagnostic",
            "outputs": plot_moran_qq(panels, resolution="hourly", max_windows=120, seed_offset=5),
            "source_data": "data/pm/*_hourly_PM25.csv",
            "status": "preferred replacement/companion",
            "latex_action": "Use with caption noting kNN-5 permutation-standardized Moran's I and deterministic hourly subsample.",
        },
    ]
    for item in generated:
        map_rows.append(
            {
                "figure": item["figure"],
                "role": item["role"],
                "preferred_file": str(Path(item["outputs"]["pdf"]).relative_to(REPO_ROOT)),
                "png_file": str(Path(item["outputs"]["png"]).relative_to(REPO_ROOT)),
                "source_data": item["source_data"],
                "status": item["status"],
                "style_status": "shared plot_style colors, 600 DPI, PDF+PNG",
                "latex_action": item["latex_action"],
            }
        )

    for item in copy_promoted_plots():
        map_rows.append(
            {
                "figure": item["figure"],
                "role": item["role"],
                "preferred_file": item["output_pdf"],
                "png_file": item["output_png"],
                "source_data": item["source_data"],
                "status": item["status"],
                "style_status": "promoted from current shared-style analysis output",
                "latex_action": "Use preferred file if updating this SI figure to the Chicago-inclusive version.",
            }
        )

    existing = [
        ("SI 12", "Estimand schematic", "Figure_SI_12/estimand_schematic.pdf", "generated by build_reviewer_requested_figures.py", "already present"),
        ("SI 13", "Three-city representative daily distributions", "Figure_SI_13/daily_distributions_representative_days.pdf", "data/pm primary networks", "already present"),
        ("SI 14", "Three-city period error percentile bands", "Figure_SI_14/period_error_percentile_bands.pdf", "monte_carlo results", "already present"),
        ("SI 15", "Chicago network with reference monitors", "Figure_SI_15/chicago_network_with_reference_monitors.pdf", "maps/manuscript outputs", "already present"),
        ("SI 16", "Regional locator", "Figure_SI_16/regional_locator.pdf", "maps/manuscript outputs", "already present"),
    ]
    for figure, role, preferred, source_data, status in existing:
        pdf = SI_ROOT / preferred
        map_rows.append(
            {
                "figure": figure,
                "role": role,
                "preferred_file": str(pdf.relative_to(REPO_ROOT)),
                "png_file": str(pdf.with_suffix(".png").relative_to(REPO_ROOT)) if pdf.with_suffix(".png").exists() else "",
                "source_data": source_data,
                "status": status,
                "style_status": "current manuscript asset",
                "latex_action": "No plot-generation action needed.",
            }
        )

    map_rows = sorted(map_rows, key=lambda row: (int(row["figure"].split()[1]), row["preferred_file"]))
    write_plot_map(map_rows)
    METADATA_JSON.write_text(
        json.dumps(
            {
                "script": str(Path(__file__).relative_to(REPO_ROOT)),
                "outputs": map_rows,
                "style_standard": {
                    "city_colors": CITY_COLORS,
                    "output_dpi": OUTPUT_DPI,
                    "text_color": TEXT_COLOR,
                },
                "moran_qq": {
                    "weight_scheme": "kNN-5",
                    "n_permutations": 199,
                    "seed_base": 20260525,
                    "daily_max_windows_per_city": 240,
                    "hourly_max_windows_per_city": 120,
                },
            },
            indent=2,
        )
    )
    print(f"Wrote {MAP_CSV.relative_to(REPO_ROOT)}")
    print(f"Wrote {MAP_MD.relative_to(REPO_ROOT)}")
    print(f"Wrote {METADATA_JSON.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
