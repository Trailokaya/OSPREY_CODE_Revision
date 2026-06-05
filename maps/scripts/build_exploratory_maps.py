from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from build_network_maps import MAP_CONFIGS, geojson_bounds, iter_rings, load_geojson, polygon_patch, read_locations
from plot_style import (  # noqa: E402
    AQS_COLOR,
    BOUNDARY_FILL_COLOR,
    DISTRICT_EDGE_COLOR,
    MAP_HIGHLIGHT_COLOR,
    MAP_OUTSIDE_COLOR,
    OUTPUT_DPI,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


DEFAULT_DATA_ROOT = REPO_ROOT / "data"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "maps" / "exploratory_maps"
GEO_DIRNAME = "geo"
LOCATION_DIRNAME = "locations"


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def ring_paths(geojson: dict) -> list[MplPath]:
    paths = []
    for feature in geojson.get("features", []):
        for ring in iter_rings(feature.get("geometry", {})):
            if len(ring) >= 3:
                paths.append(MplPath([(float(lon), float(lat)) for lon, lat, *_ in ring]))
    return paths


def boundary_vertices(geojson: dict) -> list[tuple[float, float]]:
    vertices: list[tuple[float, float]] = []
    for feature in geojson.get("features", []):
        for ring in iter_rings(feature.get("geometry", {})):
            vertices.extend((float(lon), float(lat)) for lon, lat, *_ in ring)
    return vertices


def contains_points(geojson: dict, locations: pd.DataFrame) -> list[bool]:
    paths = ring_paths(geojson)
    points = locations[["Longitude", "Latitude"]].to_numpy()
    return [any(path.contains_point(point) for path in paths) for point in points]


def map_extent(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    x_pad = (maxx - minx) * 0.08
    y_pad = (maxy - miny) * 0.08
    return minx - x_pad, miny - y_pad, maxx + x_pad, maxy + y_pad


def outside_extent(row: pd.Series, extent: tuple[float, float, float, float]) -> bool:
    minx, miny, maxx, maxy = extent
    return bool(
        row["Longitude"] < minx
        or row["Longitude"] > maxx
        or row["Latitude"] < miny
        or row["Latitude"] > maxy
    )


def nearest_boundary_vertex_km(row: pd.Series, vertices: list[tuple[float, float]]) -> float:
    return min(
        haversine_km(row["Longitude"], row["Latitude"], lon, lat)
        for lon, lat in vertices
    )


def annotate_location(ax: plt.Axes, row: pd.Series, label: str, color: str) -> None:
    ax.scatter(
        [row["Longitude"]],
        [row["Latitude"]],
        marker="*",
        s=120,
        c=color,
        edgecolors="black",
        linewidths=0.5,
        zorder=6,
    )
    ax.text(
        row["Longitude"],
        row["Latitude"],
        f"  {label}",
        fontsize=7,
        color="black",
        zorder=7,
    )


def expanded_bounds(
    district_bounds: tuple[float, float, float, float], locations: pd.DataFrame
) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = district_bounds
    minx = min(minx, float(locations["Longitude"].min()))
    maxx = max(maxx, float(locations["Longitude"].max()))
    miny = min(miny, float(locations["Latitude"].min()))
    maxy = max(maxy, float(locations["Latitude"].max()))
    x_pad = (maxx - minx) * 0.10 or 0.01
    y_pad = (maxy - miny) * 0.10 or 0.01
    return minx - x_pad, miny - y_pad, maxx + x_pad, maxy + y_pad


def plot_exploratory_network(
    city_geojson: dict,
    district_geojson: dict,
    locations: pd.DataFrame,
    config: dict,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_matplotlib()
    fig, ax = plt.subplots(1, 1, figsize=(5.0, 5.0))
    ax.add_patch(
        polygon_patch(city_geojson, facecolor=BOUNDARY_FILL_COLOR, edgecolor="none", alpha=0.35, zorder=1)
    )
    ax.add_patch(
        polygon_patch(district_geojson, facecolor="none", edgecolor=DISTRICT_EDGE_COLOR, linewidth=1.4, zorder=2)
    )

    inside = locations[locations["inside_district"]]
    outside = locations[~locations["inside_district"]]
    outside_view = locations[locations["outside_current_extent"]]
    ax.scatter(
        inside["Longitude"],
        inside["Latitude"],
        c=color_for_dataset(config["key"]),
        s=18,
        alpha=0.8,
        label="inside district",
        zorder=3,
    )
    if not outside.empty:
        ax.scatter(
            outside["Longitude"],
            outside["Latitude"],
            c=MAP_OUTSIDE_COLOR,
            s=28,
            alpha=0.9,
            label="outside district",
            zorder=4,
        )
    if not outside_view.empty:
        ax.scatter(
            outside_view["Longitude"],
            outside_view["Latitude"],
            facecolors="none",
            edgecolors=MAP_HIGHLIGHT_COLOR,
            s=70,
            linewidths=1.2,
            label="outside current map extent",
            zorder=5,
        )

    farthest = locations.sort_values("distance_to_map_center_km", ascending=False).iloc[0]
    annotate_location(ax, farthest, "farthest from map center", "yellow")
    if not outside.empty:
        farthest_outside = outside.sort_values("nearest_boundary_vertex_km", ascending=False).iloc[0]
        annotate_location(ax, farthest_outside, "farthest outside boundary", "magenta")

    minx, miny, maxx, maxy = expanded_bounds(geojson_bounds(district_geojson), locations)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (°)", fontsize=9)
    ax.set_ylabel("Latitude (°N)", fontsize=9)
    ax.set_title(f"{config['title']} Coverage Check", fontsize=10, fontweight="bold")
    ax.legend(loc="lower left", fontsize=7, frameon=True)
    fig.tight_layout()

    output_base = output_dir / f"{config['output_stem']}_exploratory"
    return save_figure(fig, output_base, dpi=OUTPUT_DPI)


def plot_chicago_combined(data_root: Path, output_dir: Path) -> dict[str, str]:
    geo_dir = data_root / GEO_DIRNAME
    city_geojson = load_geojson(geo_dir / "Chicago_City_admin6.geojson")
    district_geojson = load_geojson(geo_dir / "Chicago_District_admin5.geojson")
    aqs = read_locations(data_root / LOCATION_DIRNAME / "Chicago_AQS_sensor_locations.csv")
    lcs = read_locations(data_root / LOCATION_DIRNAME / "Chicago_LCS_corrected_sensor_locations.csv")

    output_dir.mkdir(parents=True, exist_ok=True)
    setup_matplotlib()
    fig, ax = plt.subplots(1, 1, figsize=(5.0, 5.0))
    ax.add_patch(
        polygon_patch(city_geojson, facecolor=BOUNDARY_FILL_COLOR, edgecolor="none", alpha=0.35, zorder=1)
    )
    ax.add_patch(
        polygon_patch(district_geojson, facecolor="none", edgecolor=DISTRICT_EDGE_COLOR, linewidth=1.4, zorder=2)
    )
    ax.scatter(
        lcs["Longitude"],
        lcs["Latitude"],
        c=color_for_dataset("chicago_lcs_corrected"),
        s=16,
        alpha=0.7,
        label="LCS sensors",
        zorder=3,
    )
    ax.scatter(
        aqs["Longitude"],
        aqs["Latitude"],
        c=AQS_COLOR,
        s=42,
        marker="^",
        alpha=0.95,
        label="AQS sites",
        edgecolors="white",
        linewidths=0.4,
        zorder=4,
    )

    all_locations = pd.concat([aqs, lcs], ignore_index=True)
    minx, miny, maxx, maxy = expanded_bounds(geojson_bounds(district_geojson), all_locations)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (°)", fontsize=9)
    ax.set_ylabel("Latitude (°N)", fontsize=9)
    ax.set_title("Chicago AQS and LCS Sensor Locations", fontsize=10, fontweight="bold")
    ax.legend(loc="lower left", fontsize=8, frameon=True)
    fig.tight_layout()

    output_base = output_dir / "chicago_aqs_lcs_combined_exploratory_map"
    return save_figure(fig, output_base, dpi=OUTPUT_DPI)


def analyze_network(data_root: Path, output_dir: Path, config: dict) -> tuple[pd.DataFrame, dict[str, object]]:
    geo_dir = data_root / GEO_DIRNAME
    location_dir = data_root / LOCATION_DIRNAME
    city_geojson = load_geojson(geo_dir / config["city_file"])
    district_geojson = load_geojson(geo_dir / config["district_file"])
    locations = read_locations(location_dir / config["location_file"]).copy()
    district_bounds = geojson_bounds(district_geojson)
    current_extent = map_extent(district_bounds)
    center_lon = (district_bounds[0] + district_bounds[2]) / 2
    center_lat = (district_bounds[1] + district_bounds[3]) / 2
    vertices = boundary_vertices(district_geojson)

    locations["network"] = config["key"]
    locations["inside_district"] = contains_points(district_geojson, locations)
    locations["outside_district"] = ~locations["inside_district"]
    locations["outside_current_extent"] = locations.apply(outside_extent, axis=1, extent=current_extent)
    locations["distance_to_map_center_km"] = locations.apply(
        lambda row: haversine_km(row["Longitude"], row["Latitude"], center_lon, center_lat),
        axis=1,
    )
    locations["nearest_boundary_vertex_km"] = locations.apply(
        nearest_boundary_vertex_km,
        axis=1,
        vertices=vertices,
    )
    plot_paths = plot_exploratory_network(city_geojson, district_geojson, locations, config, output_dir)
    farthest = locations.sort_values("distance_to_map_center_km", ascending=False).iloc[0]
    outside = locations[locations["outside_district"]]
    summary = {
        "network": config["key"],
        "n_points": int(len(locations)),
        "outside_district_count": int(locations["outside_district"].sum()),
        "outside_current_extent_count": int(locations["outside_current_extent"].sum()),
        "farthest_from_map_center_sensor_id": str(farthest["Sensor_ID"]),
        "farthest_from_map_center_station_name": str(farthest.get("Station_Name", "")),
        "farthest_from_map_center_km": float(farthest["distance_to_map_center_km"]),
        "exploratory_png": plot_paths["png"],
        "exploratory_pdf": plot_paths["pdf"],
    }
    if not outside.empty:
        farthest_outside = outside.sort_values("nearest_boundary_vertex_km", ascending=False).iloc[0]
        summary.update(
            {
                "farthest_outside_sensor_id": str(farthest_outside["Sensor_ID"]),
                "farthest_outside_station_name": str(farthest_outside.get("Station_Name", "")),
                "farthest_outside_nearest_boundary_vertex_km": float(farthest_outside["nearest_boundary_vertex_km"]),
            }
        )
    else:
        summary.update(
            {
                "farthest_outside_sensor_id": "",
                "farthest_outside_station_name": "",
                "farthest_outside_nearest_boundary_vertex_km": "",
            }
        )
    return locations, summary


def build_exploratory_maps(data_root: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_locations = []
    summaries = []
    figures = {}
    for config in MAP_CONFIGS:
        locations, summary = analyze_network(data_root, output_dir, config)
        all_locations.append(locations)
        summaries.append(summary)
        figures[config["key"]] = {
            "png": summary["exploratory_png"],
            "pdf": summary["exploratory_pdf"],
        }

    all_locations_frame = pd.concat(all_locations, ignore_index=True)
    summary_frame = pd.DataFrame(summaries)
    all_locations_frame.to_csv(output_dir / "network_location_coverage_diagnostics.csv", index=False)
    summary_frame.to_csv(output_dir / "network_location_coverage_summary.csv", index=False)
    figures["chicago_aqs_lcs_combined"] = plot_chicago_combined(data_root, output_dir)

    metadata = {
        "purpose": "Exploratory checks for sensors outside map boundaries/extents and combined Chicago AQS/LCS locations.",
        "data_root": str(data_root),
        "output_dir": str(output_dir),
        "summary_csv": str(output_dir / "network_location_coverage_summary.csv"),
        "diagnostics_csv": str(output_dir / "network_location_coverage_diagnostics.csv"),
        "style_source": "analysis/src/plot_style.py",
        "output_dpi": OUTPUT_DPI,
        "figures": figures,
    }
    with (output_dir / "exploratory_map_metadata.json").open("w") as file:
        json.dump(metadata, file, indent=2)
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build exploratory network maps and location coverage diagnostics."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    metadata = build_exploratory_maps(args.data_root, args.output_dir)
    summary = pd.read_csv(metadata["summary_csv"], dtype=str).fillna("")
    print(f"Wrote exploratory maps under {args.output_dir}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
