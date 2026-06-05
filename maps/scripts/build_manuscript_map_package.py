from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "maps" / "scripts"))

from build_network_maps import (  # noqa: E402
    geojson_bounds,
    load_geojson,
    polygon_patch,
    read_locations,
)
from plot_style import (  # noqa: E402
    BOUNDARY_FILL_COLOR,
    GRID_COLOR,
    OUTPUT_DPI,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


OUTPUT_DIR = REPO_ROOT / "maps/manuscript_plots"
REFERENCE_DIR = REPO_ROOT / "data/reference"


CITY_CONFIGS = [
    {
        "city": "Dhaka",
        "dataset_key": "dhaka_lcs",
        "sensor_file": "data/locations/Dhaka_sensor_locations.csv",
        "city_geojson": "data/geo/Dhaka_City_admin6.geojson",
        "district_geojson": "data/geo/Dhaka_District_admin5.geojson",
        "sensor_label": "LCS sensors",
        "reference_status": "not_used_for_map",
        "reference_label": "No reference markers",
        "reference_note": "Per current project decision, Dhaka reference-monitor markers are not used in Figure 1.",
        "scale_bar_anchor": (0.08, 0.045),
    },
    {
        "city": "Lucknow",
        "dataset_key": "lucknow_lcs",
        "sensor_file": "data/locations/Lucknow_sensor_locations.csv",
        "city_geojson": "data/geo/Lucknow_City_admin6.geojson",
        "district_geojson": "data/geo/Lucknow_District_admin5.geojson",
        "sensor_label": "LCS sensors",
        "reference_status": "not_used_for_map",
        "reference_label": "No reference markers",
        "reference_note": "Per current project decision, Lucknow reference-monitor markers are not used in Figure 1.",
        "scale_bar_anchor": (0.08, 0.10),
    },
    {
        "city": "Chicago",
        "dataset_key": "chicago_lcs_corrected_no_collocation",
        "sensor_file": "data/locations/Chicago_LCS_corrected_sensor_locations.csv",
        "city_geojson": "data/geo/Chicago_City_admin6.geojson",
        "district_geojson": "data/geo/Chicago_District_admin5.geojson",
        "sensor_label": "LCS sensors",
        "reference_status": "si_context_only",
        "reference_file": "data/locations/Chicago_AQS_sensor_locations.csv",
        "reference_label": "EPA AQS sites",
        "reference_note": "Chicago AQS sites are retained for SI/reference-context figures, not plotted in main Figure 1.",
        "exclude_collocation": True,
        "scale_bar_anchor": (0.08, 0.10),
    },
]


def git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def relative(path: Path | str) -> str:
    path = Path(path)
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def filter_primary_sensors(config: dict[str, Any], sensors: pd.DataFrame) -> pd.DataFrame:
    if config.get("exclude_collocation") and "Station_Name" in sensors.columns:
        sensors = sensors[
            ~sensors["Station_Name"].astype(str).str.contains("collocation", case=False, na=False)
        ].copy()
    return sensors


def expanded_bounds(
    district_bounds: tuple[float, float, float, float],
    *frames: pd.DataFrame,
) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = district_bounds
    for frame in frames:
        if frame.empty:
            continue
        minx = min(minx, float(frame["Longitude"].min()))
        maxx = max(maxx, float(frame["Longitude"].max()))
        miny = min(miny, float(frame["Latitude"].min()))
        maxy = max(maxy, float(frame["Latitude"].max()))
    x_pad = (maxx - minx) * 0.08 or 0.01
    y_pad = (maxy - miny) * 0.08 or 0.01
    return minx - x_pad, miny - y_pad, maxx + x_pad, maxy + y_pad


def add_panel_scale_bar(
    axis: plt.Axes,
    bounds: tuple[float, float, float, float],
    anchor: tuple[float, float],
    length_km: float = 10.0,
) -> None:
    minx, miny, maxx, maxy = bounds
    xspan = maxx - minx
    yspan = maxy - miny
    start_lon = minx + anchor[0] * xspan
    start_lat = miny + anchor[1] * yspan
    km_per_degree_lon = 111.32 * abs(math.cos(math.radians(start_lat)))
    if km_per_degree_lon <= 0:
        return
    length_degrees = length_km / km_per_degree_lon
    tick_height = 0.014 * yspan
    label_offset = 0.024 * yspan

    axis.plot(
        [start_lon, start_lon + length_degrees],
        [start_lat, start_lat],
        color="#111827",
        linewidth=1.4,
        solid_capstyle="butt",
        zorder=6,
    )
    axis.plot(
        [start_lon, start_lon],
        [start_lat - tick_height, start_lat + tick_height],
        color="#111827",
        linewidth=1.1,
        zorder=6,
    )
    axis.plot(
        [start_lon + length_degrees, start_lon + length_degrees],
        [start_lat - tick_height, start_lat + tick_height],
        color="#111827",
        linewidth=1.1,
        zorder=6,
    )
    axis.text(
        start_lon + length_degrees / 2,
        start_lat + label_offset,
        f"{int(length_km)} km",
        ha="center",
        va="bottom",
        fontsize=7,
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.78, pad=1.3),
        zorder=7,
    )


def add_panel(
    axis: plt.Axes,
    config: dict[str, Any],
) -> dict[str, Any]:
    city_geojson = load_geojson(REPO_ROOT / config["city_geojson"])
    district_geojson = load_geojson(REPO_ROOT / config["district_geojson"])
    sensors = filter_primary_sensors(config, read_locations(REPO_ROOT / config["sensor_file"]))
    district_bounds = geojson_bounds(district_geojson)
    bounds = expanded_bounds(district_bounds, sensors)
    sensor_color = color_for_dataset(config["dataset_key"])

    axis.add_patch(
        polygon_patch(
            city_geojson,
            facecolor=sensor_color,
            edgecolor=sensor_color,
            alpha=0.16,
            linewidth=1.2,
            zorder=1,
        )
    )
    axis.add_patch(
        polygon_patch(
            district_geojson,
            facecolor="none",
            edgecolor=sensor_color,
            linewidth=1.4,
            alpha=0.92,
            zorder=2,
        )
    )
    axis.scatter(
        sensors["Longitude"],
        sensors["Latitude"],
        c=sensor_color,
        s=16 if config["city"] != "Chicago" else 9,
        alpha=0.82 if config["city"] != "Chicago" else 0.64,
        edgecolors="white",
        linewidths=0.25,
        zorder=3,
    )
    axis.set_xlim(bounds[0], bounds[2])
    axis.set_ylim(bounds[1], bounds[3])
    axis.set_aspect("equal", adjustable="box")
    axis.set_title(config["city"], fontweight="bold", fontsize=11)
    axis.set_xlabel("Longitude (°)")
    axis.set_ylabel("Latitude (°N)")
    axis.xaxis.set_major_locator(MaxNLocator(nbins=3 if config["city"] == "Dhaka" else 4))
    axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
    axis.grid(True, color=GRID_COLOR, linestyle="--", linewidth=0.45)
    add_panel_scale_bar(axis, bounds, config.get("scale_bar_anchor", (0.08, 0.10)))

    return {
        "city": config["city"],
        "dataset_key": config["dataset_key"],
        "sensor_count_plotted": int(len(sensors)),
        "reference_count_plotted": 0,
        "reference_status": config["reference_status"],
        "reference_label": config["reference_label"],
        "reference_note": config["reference_note"],
        "sensor_file": config["sensor_file"],
        "reference_file": config.get("reference_file"),
        "city_geojson": config["city_geojson"],
        "district_geojson": config["district_geojson"],
    }


def write_reference_locations() -> None:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    chicago = read_locations(REPO_ROOT / "data/locations/Chicago_AQS_sensor_locations.csv").copy()
    chicago["City"] = "Chicago"
    chicago["Reference_Type"] = "EPA AQS regulatory/context monitor"
    chicago["Coordinate_Status"] = "canonical_from_data_locations"
    chicago[
        [
            "City",
            "Sensor_ID",
            "Station_Name",
            "Latitude",
            "Longitude",
            "Reference_Type",
            "Coordinate_Status",
        ]
    ].to_csv(REFERENCE_DIR / "reference_monitor_locations.csv", index=False)

    scope_report = """# Reference Monitor Location Scope

Generated by `maps/scripts/build_manuscript_map_package.py`.

## Current Mapping Decision

- Main Figure 1 plots only low-cost sensor network locations for Dhaka, Lucknow, and Chicago.
- Chicago EPA AQS reference/regulatory monitor coordinates are retained for SI/reference-context figures and are not plotted in main Figure 1.
- Dhaka and Lucknow reference-monitor markers are not used in Figure 1 under the current project decision.

## Canonical Coordinates Used

- Chicago EPA AQS sites are available in `data/locations/Chicago_AQS_sensor_locations.csv` and mirrored into `data/reference/reference_monitor_locations.csv`.

No Dhaka or Lucknow reference-monitor coordinates are needed for the current Figure 1 map scope.
"""
    (REFERENCE_DIR / "reference_monitor_location_scope.md").write_text(scope_report)
    stale_gap_report = REFERENCE_DIR / "reference_monitor_location_gaps.md"
    if stale_gap_report.exists():
        stale_gap_report.unlink()


def build_composite_map() -> tuple[dict[str, str], pd.DataFrame]:
    setup_matplotlib()
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.35), constrained_layout=True)
    panel_rows = [add_panel(axis, config) for axis, config in zip(axes, CITY_CONFIGS)]

    sensor_handles = [
        mlines.Line2D(
            [],
            [],
            marker="o",
            linestyle="None",
            markersize=6,
            markerfacecolor=color_for_dataset("dhaka_lcs"),
            markeredgecolor="white",
            label="Dhaka LCS",
        ),
        mlines.Line2D(
            [],
            [],
            marker="o",
            linestyle="None",
            markersize=6,
            markerfacecolor=color_for_dataset("lucknow_lcs"),
            markeredgecolor="white",
            label="Lucknow LCS",
        ),
        mlines.Line2D(
            [],
            [],
            marker="o",
            linestyle="None",
            markersize=6,
            markerfacecolor=color_for_dataset("chicago_lcs_corrected_no_collocation"),
            markeredgecolor="white",
            label="Chicago LCS",
        ),
    ]
    fig.legend(
        handles=sensor_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=3,
        frameon=False,
    )
    paths = save_figure(
        fig,
        OUTPUT_DIR / "F1_sensor_network_reference_monitor_map",
        dpi=OUTPUT_DPI,
    )
    return paths, pd.DataFrame(panel_rows)


def build_locator_map() -> dict[str, str]:
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
    except ImportError as exc:
        raise RuntimeError(
            "Cartopy is required for the manuscript regional locator map. "
            "Install with `.venv/bin/python -m pip install -r requirements.txt`."
        ) from exc

    setup_matplotlib()
    cities = pd.DataFrame(
        [
            {"city": "Dhaka", "longitude": 90.4125, "latitude": 23.8103, "dataset_key": "dhaka_lcs"},
            {"city": "Lucknow", "longitude": 80.9462, "latitude": 26.8467, "dataset_key": "lucknow_lcs"},
            {
                "city": "Chicago",
                "longitude": -87.6298,
                "latitude": 41.8781,
                "dataset_key": "chicago_lcs_corrected_no_collocation",
            },
        ]
    )

    projection = ccrs.Robinson()
    plate_carree = ccrs.PlateCarree()
    fig = plt.figure(figsize=(8.4, 4.65))
    axis = fig.add_subplot(1, 1, 1, projection=projection)
    axis.set_global()
    axis.add_feature(cfeature.OCEAN, facecolor="#f8fafc", zorder=0)
    axis.add_feature(cfeature.LAND, facecolor="#f3f4f6", edgecolor="none", zorder=1)
    axis.coastlines(linewidth=0.55, color="#6b7280", zorder=2)
    axis.add_feature(cfeature.BORDERS, linewidth=0.35, edgecolor="#9ca3af", zorder=2)
    axis.gridlines(color=GRID_COLOR, linewidth=0.45, linestyle="--", alpha=0.85)
    axis.set_title("Study locations", fontweight="bold", fontsize=11, pad=8)

    label_offsets = {
        "Dhaka": (3.5, -4.0),
        "Lucknow": (3.0, 3.0),
        "Chicago": (4.0, 2.0),
    }
    for row in cities.itertuples(index=False):
        axis.scatter(
            row.longitude,
            row.latitude,
            s=62,
            color=color_for_dataset(row.dataset_key),
            edgecolors="white",
            linewidths=0.8,
            transform=plate_carree,
            zorder=4,
        )
        dx, dy = label_offsets[row.city]
        axis.text(
            row.longitude + dx,
            row.latitude + dy,
            row.city,
            fontsize=8.5,
            fontweight="bold",
            transform=plate_carree,
            zorder=5,
        )
    fig.tight_layout()

    return save_figure(fig, OUTPUT_DIR / "F1_regional_locator_map", dpi=OUTPUT_DPI)


def write_readme(panel_status: pd.DataFrame) -> None:
    readme = """# Manuscript Map Package

Generated by `maps/scripts/build_manuscript_map_package.py`.

## Current Files

| file stem | purpose |
|---|---|
| `F1_sensor_network_reference_monitor_map` | Three-panel map for Dhaka, Lucknow, and Chicago primary LCS networks. |
| `F1_regional_locator_map` | Single Cartopy world locator with coastlines, borders, and the three study cities. |
| `F1_reference_monitor_overlay_status.csv` | Per-city status table for plotted LCS sensors and non-plotted reference-context scope. |
| `F1_map_package_metadata.json` | Reproducibility metadata. |

## Current Limitation

Main Figure 1 is LCS-only. Chicago EPA AQS sites are retained for SI/reference-context figures, while Dhaka and Lucknow reference-monitor markers are intentionally not used in Figure 1 under the current project decision. The scope is recorded in `data/reference/reference_monitor_location_scope.md`.

## Promotion Status

These are manuscript-map products staged for revision. Legacy draft-named files may remain in the folder for audit history, but the final stems above are the promoted assets.
"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "README.md").write_text(readme)
    panel_status.to_csv(OUTPUT_DIR / "F1_reference_monitor_overlay_status.csv", index=False)


def build_metadata(
    map_paths: dict[str, str],
    locator_paths: dict[str, str],
    panel_status: pd.DataFrame,
    started: float,
) -> dict[str, Any]:
    return {
        "script": "maps/scripts/build_manuscript_map_package.py",
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime_seconds": round(time.time() - started, 3),
        "git_commit": git_value(["rev-parse", "HEAD"]),
        "output_dpi": OUTPUT_DPI,
        "map_paths": {key: relative(path) for key, path in map_paths.items()},
        "locator_paths": {key: relative(path) for key, path in locator_paths.items()},
        "reference_location_file": "data/reference/reference_monitor_locations.csv",
        "reference_scope_report": "data/reference/reference_monitor_location_scope.md",
        "panel_status": panel_status.to_dict(orient="records"),
    }


def main() -> None:
    started = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_reference_locations()
    map_paths, panel_status = build_composite_map()
    locator_paths = build_locator_map()
    write_readme(panel_status)
    metadata = build_metadata(map_paths, locator_paths, panel_status, started)
    (OUTPUT_DIR / "F1_map_package_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True)
    )
    print(f"Wrote manuscript map package to {OUTPUT_DIR}")
    print(f"Reference monitor status: {OUTPUT_DIR / 'F1_reference_monitor_overlay_status.csv'}")


if __name__ == "__main__":
    main()
