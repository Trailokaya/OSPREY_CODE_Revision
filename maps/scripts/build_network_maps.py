from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import (  # noqa: E402
    BOUNDARY_FILL_COLOR,
    DISTRICT_EDGE_COLOR,
    OUTPUT_DPI,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


DEFAULT_DATA_ROOT = REPO_ROOT / "data"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "maps" / "plots"
GEO_DIRNAME = "geo"
LOCATION_DIRNAME = "locations"
CHICAGO_CITY_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_17_place_500k.zip"
)
US_COUNTY_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
)


MAP_CONFIGS = [
    {
        "key": "dhaka_lcs",
        "location_file": "Dhaka_sensor_locations.csv",
        "city_file": "Dhaka_City_admin6.geojson",
        "district_file": "Dhaka_District_admin5.geojson",
        "title": "Dhaka LCS Sensor Network",
        "count_label": "sensors",
        "output_stem": "dhaka_lcs_sensor_network_map",
    },
    {
        "key": "lucknow_lcs",
        "location_file": "Lucknow_sensor_locations.csv",
        "city_file": "Lucknow_City_admin6.geojson",
        "district_file": "Lucknow_District_admin5.geojson",
        "title": "Lucknow LCS Sensor Network",
        "count_label": "sensors",
        "output_stem": "lucknow_lcs_sensor_network_map",
    },
    {
        "key": "chicago_aqs",
        "location_file": "Chicago_AQS_sensor_locations.csv",
        "city_file": "Chicago_City_admin6.geojson",
        "district_file": "Chicago_District_admin5.geojson",
        "title": "Chicago AQS Sensor Network",
        "count_label": "sites",
        "output_stem": "chicago_aqs_sensor_network_map",
    },
    {
        "key": "chicago_lcs_corrected",
        "location_file": "Chicago_LCS_corrected_sensor_locations.csv",
        "city_file": "Chicago_City_admin6.geojson",
        "district_file": "Chicago_District_admin5.geojson",
        "title": "Chicago LCS Corrected Sensor Network",
        "count_label": "sensors",
        "output_stem": "chicago_lcs_corrected_sensor_network_map",
    },
    {
        "key": "chicago_lcs_raw",
        "location_file": "Chicago_LCS_raw_sensor_locations.csv",
        "city_file": "Chicago_City_admin6.geojson",
        "district_file": "Chicago_District_admin5.geojson",
        "title": "Chicago LCS Raw Sensor Network",
        "count_label": "sensors",
        "output_stem": "chicago_lcs_raw_sensor_network_map",
    },
]


def download(url: str, output_path: Path) -> None:
    with urllib.request.urlopen(url) as response:
        output_path.write_bytes(response.read())


def run_ogr2ogr(
    source_shp: Path,
    where_clause: str,
    output_path: Path,
) -> None:
    ogr2ogr = shutil.which("ogr2ogr")
    if ogr2ogr is None:
        raise SystemExit(
            "Missing `ogr2ogr`. Install GDAL or provide Chicago boundary GeoJSON files manually."
        )
    subprocess.run(
        [
            ogr2ogr,
            "-f",
            "GeoJSON",
            str(output_path),
            str(source_shp),
            "-where",
            where_clause,
            "-t_srs",
            "EPSG:4326",
            "-ct_opt",
            "WARN_ABOUT_DIFFERENT_COORD_OP=NO",
        ],
        check=True,
    )


def ensure_chicago_boundary_geojsons(geo_dir: Path) -> dict[str, str]:
    geo_dir.mkdir(parents=True, exist_ok=True)
    city_output = geo_dir / "Chicago_City_admin6.geojson"
    district_output = geo_dir / "Chicago_District_admin5.geojson"

    if city_output.exists() and district_output.exists():
        return {
            "city": str(city_output),
            "district": str(district_output),
            "city_source": CHICAGO_CITY_URL,
            "district_source": US_COUNTY_URL,
            "rebuilt": False,
        }

    with tempfile.TemporaryDirectory() as tmpdir_name:
        tmpdir = Path(tmpdir_name)
        place_zip = tmpdir / "cb_2023_17_place_500k.zip"
        county_zip = tmpdir / "cb_2023_us_county_500k.zip"
        download(CHICAGO_CITY_URL, place_zip)
        download(US_COUNTY_URL, county_zip)

        place_dir = tmpdir / "place"
        county_dir = tmpdir / "county"
        with zipfile.ZipFile(place_zip) as archive:
            archive.extractall(place_dir)
        with zipfile.ZipFile(county_zip) as archive:
            archive.extractall(county_dir)

        run_ogr2ogr(
            source_shp=place_dir / "cb_2023_17_place_500k.shp",
            where_clause="PLACEFP='14000'",
            output_path=city_output,
        )
        run_ogr2ogr(
            source_shp=county_dir / "cb_2023_us_county_500k.shp",
            where_clause="STATEFP='17' AND COUNTYFP='031'",
            output_path=district_output,
        )

    return {
        "city": str(city_output),
        "district": str(district_output),
        "city_source": CHICAGO_CITY_URL,
        "district_source": US_COUNTY_URL,
        "rebuilt": True,
    }


def load_geojson(path: Path) -> dict:
    with path.open() as file:
        return json.load(file)


def iter_rings(geometry: dict) -> list[list[list[float]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        return coordinates
    if geometry_type == "MultiPolygon":
        return [ring for polygon in coordinates for ring in polygon]
    return []


def geojson_bounds(data: dict) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for feature in data.get("features", []):
        for ring in iter_rings(feature.get("geometry", {})):
            for lon, lat, *_ in ring:
                xs.append(float(lon))
                ys.append(float(lat))
    if not xs or not ys:
        raise ValueError("GeoJSON contains no polygon coordinates")
    return min(xs), min(ys), max(xs), max(ys)


def polygon_patch(data: dict, **kwargs) -> PathPatch:
    vertices = []
    codes = []
    for feature in data.get("features", []):
        for ring in iter_rings(feature.get("geometry", {})):
            if not ring:
                continue
            ring_vertices = [(float(lon), float(lat)) for lon, lat, *_ in ring]
            vertices.extend(ring_vertices)
            codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(ring_vertices) - 1))
            vertices.append(ring_vertices[0])
            codes.append(MplPath.CLOSEPOLY)
    return PathPatch(MplPath(vertices, codes), **kwargs)


def add_scale_bar(ax: plt.Axes, bounds: tuple[float, float, float, float]) -> None:
    minx, miny, maxx, maxy = bounds
    latitude = miny + 0.08 * (maxy - miny)
    km_per_degree_lon = 111.32 * abs(__import__("math").cos(__import__("math").radians(latitude)))
    degrees_for_10km = 10.0 / km_per_degree_lon
    x0 = minx + 0.08 * (maxx - minx)
    y0 = miny + 0.08 * (maxy - miny)
    ax.plot([x0, x0 + degrees_for_10km], [y0, y0], color="black", lw=2.0, zorder=5)
    ax.plot([x0, x0], [y0 - 0.003, y0 + 0.003], color="black", lw=1.2, zorder=5)
    ax.plot(
        [x0 + degrees_for_10km, x0 + degrees_for_10km],
        [y0 - 0.003, y0 + 0.003],
        color="black",
        lw=1.2,
        zorder=5,
    )
    ax.text(
        x0 + degrees_for_10km / 2,
        y0 + 0.01 * (maxy - miny),
        "10 km",
        fontsize=8,
        ha="center",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8, edgecolor="none"),
        zorder=6,
    )


def read_locations(path: Path) -> pd.DataFrame:
    locations = pd.read_csv(path, dtype={"Sensor_ID": str})
    locations["Latitude"] = pd.to_numeric(locations["Latitude"], errors="coerce")
    locations["Longitude"] = pd.to_numeric(locations["Longitude"], errors="coerce")
    return locations.dropna(subset=["Latitude", "Longitude"])


def plot_sensor_map(
    city_geojson: dict,
    district_geojson: dict,
    locations: pd.DataFrame,
    config: dict,
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bounds = geojson_bounds(district_geojson)
    minx, miny, maxx, maxy = bounds
    x_pad = (maxx - minx) * 0.08
    y_pad = (maxy - miny) * 0.08

    setup_matplotlib()
    fig, ax = plt.subplots(1, 1, figsize=(4.0, 4.5))
    ax.add_patch(
        polygon_patch(
            city_geojson,
            facecolor=BOUNDARY_FILL_COLOR,
            edgecolor="none",
            alpha=0.4,
            zorder=1,
        )
    )
    ax.add_patch(
        polygon_patch(
            district_geojson,
            facecolor="none",
            edgecolor=DISTRICT_EDGE_COLOR,
            linewidth=1.5,
            alpha=1.0,
            zorder=2,
        )
    )
    ax.scatter(
        locations["Longitude"],
        locations["Latitude"],
        c=color_for_dataset(config["key"]),
        s=15,
        alpha=0.8,
        zorder=3,
        edgecolors="white",
        linewidths=0.3,
    )
    ax.set_xlim(minx - x_pad, maxx + x_pad)
    ax.set_ylim(miny - y_pad, maxy + y_pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude (°)", fontsize=9)
    ax.set_ylabel("Latitude (°N)", fontsize=9)
    ax.set_title(
        config["title"],
        fontsize=10,
        fontweight="bold",
        pad=10,
    )
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.2, linestyle="--", linewidth=0.5)
    ax.text(
        0.98,
        0.98,
        f"n = {len(locations)} {config['count_label']}",
        fontsize=8,
        transform=ax.transAxes,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8, edgecolor="none"),
    )
    add_scale_bar(ax, bounds)
    fig.tight_layout()

    output_base = output_dir / config["output_stem"]
    plot_paths = save_figure(fig, output_base, dpi=OUTPUT_DPI)
    return {
        "png": plot_paths["png"],
        "pdf": plot_paths["pdf"],
        "sensor_or_site_count": int(len(locations)),
        "city_boundary": str(Path(GEO_DIRNAME) / config["city_file"]),
        "district_boundary": str(Path(GEO_DIRNAME) / config["district_file"]),
        "locations": str(Path(LOCATION_DIRNAME) / config["location_file"]),
    }


def build_maps(data_root: Path, output_dir: Path) -> dict[str, object]:
    geo_dir = data_root / GEO_DIRNAME
    location_dir = data_root / LOCATION_DIRNAME
    chicago_boundary_info = ensure_chicago_boundary_geojsons(geo_dir)

    figures = {}
    for config in MAP_CONFIGS:
        city_geojson = load_geojson(geo_dir / config["city_file"])
        district_geojson = load_geojson(geo_dir / config["district_file"])
        locations = read_locations(location_dir / config["location_file"])
        figures[config["key"]] = plot_sensor_map(
            city_geojson=city_geojson,
            district_geojson=district_geojson,
            locations=locations,
            config=config,
            output_dir=output_dir,
        )

    metadata = {
        "purpose": "All available sensor network maps in the legacy OSPREY style.",
        "data_root": str(data_root),
        "output_dir": str(output_dir),
        "chicago_boundary_files": chicago_boundary_info,
        "style_source": "analysis/src/plot_style.py; legacy reference _local_archive/branches/main/notebooks_median/04_sensor_network_maps.ipynb",
        "output_dpi": OUTPUT_DPI,
        "figures": figures,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "network_map_metadata.json").open("w") as file:
        json.dump(metadata, file, indent=2)
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build all available legacy-style network maps."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    metadata = build_maps(args.data_root, args.output_dir)
    print(f"Wrote network maps under {args.output_dir}")
    for key, info in metadata["figures"].items():
        print(f"{key}: {info['png']} ({info['sensor_or_site_count']} points)")


if __name__ == "__main__":
    main()
