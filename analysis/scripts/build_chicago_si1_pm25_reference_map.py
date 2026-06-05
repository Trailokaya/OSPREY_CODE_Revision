from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis/src"))
sys.path.insert(0, str(REPO_ROOT / "maps/scripts"))

from build_network_maps import geojson_bounds, load_geojson, polygon_patch  # noqa: E402
from plot_style import CITY_COLORS, GRID_COLOR, OUTPUT_DPI, TEXT_COLOR, save_figure, setup_matplotlib  # noqa: E402

OUT_DIR = REPO_ROOT / "analysis/results/chicago_si1_pm25_reference_map"
PLOT_DIR = REPO_ROOT / "manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_1"

LCS_PM = REPO_ROOT / "data/pm/Chicago_LCS_corrected_daily_PM25.csv"
AQS_PM = REPO_ROOT / "data/pm/Chicago_AQS_daily_PM25.csv"
LCS_LOC = REPO_ROOT / "data/locations/Chicago_LCS_corrected_sensor_locations.csv"
AQS_LOC = REPO_ROOT / "data/locations/Chicago_AQS_sensor_locations.csv"
CITY_GEOJSON = REPO_ROOT / "data/geo/Chicago_City_admin6.geojson"
DISTRICT_GEOJSON = REPO_ROOT / "data/geo/Chicago_District_admin5.geojson"

TARGET_DATE = "2026-01-01"
PERIOD_START_DATE = "2025-09-01"
PERIOD_END_DATE = "2026-03-31"
LCS_KEY = "Chicago LCS"
AQS_KEY = "EPA AQS"


def read_daily_pm(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    local_ts = pd.to_datetime(frame["Timestamp"], utc=True).dt.tz_convert("America/Chicago")
    frame = frame.copy()
    frame["local_date"] = local_ts.dt.strftime("%Y-%m-%d")
    return frame


def primary_lcs_locations() -> pd.DataFrame:
    loc = pd.read_csv(LCS_LOC)
    loc = loc[~loc["Station_Name"].astype(str).str.contains("collocation", case=False, na=False)].copy()
    return loc


def daily_values(pm: pd.DataFrame, date: str) -> pd.Series:
    cols = [col for col in pm.columns if col not in {"Timestamp", "local_date"}]
    row = pm.loc[pm["local_date"] == date]
    if row.empty:
        raise ValueError(f"No data for {date}")
    return pd.to_numeric(row[cols].iloc[0], errors="coerce")


def period_values(pm: pd.DataFrame, start_date: str, end_date: str) -> tuple[pd.Series, dict[str, str | int]]:
    pm = pm.loc[(pm["local_date"] >= start_date) & (pm["local_date"] <= end_date)].copy()
    cols = [col for col in pm.columns if col not in {"Timestamp", "local_date"}]
    numeric = pm[cols].apply(pd.to_numeric, errors="coerce")
    values = numeric.mean(axis=0, skipna=True)
    metadata = {
        "start_date": start_date,
        "end_date": end_date,
        "n_dates": int(pm["local_date"].nunique()),
        "n_valid_dates": int(numeric.notna().any(axis=1).sum()),
    }
    return values, metadata


def merge_values(loc: pd.DataFrame, values: pd.Series, network: str, panel: str, period_meta: dict[str, str | int]) -> pd.DataFrame:
    out = loc.copy()
    out["value_pm25_ug_m3"] = out["Sensor_ID"].map(values)
    out["network"] = network
    out["panel"] = panel
    out["start_date"] = period_meta["start_date"]
    out["end_date"] = period_meta["end_date"]
    out["n_dates_available_for_network"] = period_meta["n_dates"]
    out["n_valid_dates_for_network"] = period_meta.get("n_valid_dates", period_meta["n_dates"])
    return out.dropna(subset=["value_pm25_ug_m3"])


def expand_bounds(bounds: tuple[float, float, float, float], *frames: pd.DataFrame) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    for frame in frames:
        if frame.empty:
            continue
        minx = min(minx, float(frame["Longitude"].min()))
        maxx = max(maxx, float(frame["Longitude"].max()))
        miny = min(miny, float(frame["Latitude"].min()))
        maxy = max(maxy, float(frame["Latitude"].max()))
    dx = maxx - minx
    dy = maxy - miny
    pad_x = dx * 0.06
    pad_y = dy * 0.06
    return minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y


def add_boundaries(
    axis: plt.Axes,
    bounds: tuple[float, float, float, float],
    city_geojson: dict,
    district_geojson: dict,
) -> None:
    chicago_green = CITY_COLORS["chicago"]
    axis.add_patch(
        polygon_patch(
            city_geojson,
            facecolor=chicago_green,
            edgecolor=chicago_green,
            alpha=0.10,
            linewidth=1.1,
            zorder=1,
        )
    )
    axis.add_patch(
        polygon_patch(
            district_geojson,
            facecolor="none",
            edgecolor=chicago_green,
            alpha=0.85,
            linewidth=1.3,
            zorder=2,
        )
    )
    axis.set_xlim(bounds[0], bounds[2])
    axis.set_ylim(bounds[1], bounds[3])
    axis.set_aspect("equal", adjustable="box")
    axis.grid(True, color=GRID_COLOR, linestyle="--", linewidth=0.45, zorder=0)
    axis.set_xlabel("")
    axis.set_ylabel("")


def network_stats(frame: pd.DataFrame) -> dict[str, float | int]:
    vals = frame["value_pm25_ug_m3"].astype(float)
    return {
        "n": int(vals.notna().sum()),
        "mean": float(vals.mean()),
        "median": float(vals.median()),
        "min": float(vals.min()),
        "max": float(vals.max()),
    }


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(f"{value:.3g}")
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def build() -> None:
    setup_matplotlib()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    lcs_pm = read_daily_pm(LCS_PM)
    aqs_pm = read_daily_pm(AQS_PM)
    lcs_loc = primary_lcs_locations()
    aqs_loc = pd.read_csv(AQS_LOC)

    lcs_daily = daily_values(lcs_pm, TARGET_DATE)
    aqs_daily = daily_values(aqs_pm, TARGET_DATE)
    lcs_period, lcs_meta = period_values(lcs_pm, PERIOD_START_DATE, PERIOD_END_DATE)
    aqs_period, aqs_meta = period_values(aqs_pm, PERIOD_START_DATE, PERIOD_END_DATE)

    daily_meta = {"start_date": TARGET_DATE, "end_date": TARGET_DATE, "n_dates": 1, "n_valid_dates": 1}
    panels = []
    panels.extend([
        merge_values(lcs_loc, lcs_daily, LCS_KEY, "Jan 1, 2026 daily mean", daily_meta),
        merge_values(aqs_loc, aqs_daily, AQS_KEY, "Jan 1, 2026 daily mean", daily_meta),
        merge_values(lcs_loc, lcs_period, LCS_KEY, "Sep 2025-Mar 2026 mean", lcs_meta),
        merge_values(aqs_loc, aqs_period, AQS_KEY, "Sep 2025-Mar 2026 mean", aqs_meta),
    ])
    data = pd.concat(panels, ignore_index=True)
    data.to_csv(OUT_DIR / "chicago_si1_pm25_reference_map_data.csv", index=False)

    stats_rows = []
    for (panel, network), group in data.groupby(["panel", "network"]):
        row = {"panel": panel, "network": network, **network_stats(group)}
        row["start_date"] = str(group["start_date"].iloc[0])
        row["end_date"] = str(group["end_date"].iloc[0])
        row["n_dates_available_for_network"] = int(group["n_dates_available_for_network"].iloc[0])
        row["n_valid_dates_for_network"] = int(group["n_valid_dates_for_network"].iloc[0])
        stats_rows.append(row)
    stats = pd.DataFrame(stats_rows).sort_values(["panel", "network"])
    stats.to_csv(OUT_DIR / "chicago_si1_pm25_reference_map_summary.csv", index=False)

    city_geojson = load_geojson(CITY_GEOJSON)
    district_geojson = load_geojson(DISTRICT_GEOJSON)
    bounds = expand_bounds(geojson_bounds(district_geojson), lcs_loc, aqs_loc)
    vmin = 0.0
    vmax = float(np.ceil(data["value_pm25_ug_m3"].max() / 5) * 5)
    vmax = max(20.0, vmax)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8), constrained_layout=False)
    panel_specs = [
        ("Jan 1, 2026 daily mean", "Daily PM$_{2.5}$ on Jan 1, 2026"),
        ("Sep 2025-Mar 2026 mean", "Matched-period mean PM$_{2.5}$"),
    ]
    scatter_for_colorbar = None
    for axis, (panel, title) in zip(axes, panel_specs):
        add_boundaries(axis, bounds, city_geojson, district_geojson)
        panel_data = data[data["panel"] == panel]
        lcs = panel_data[panel_data["network"] == LCS_KEY]
        aqs = panel_data[panel_data["network"] == AQS_KEY]
        scatter_for_colorbar = axis.scatter(
            lcs["Longitude"],
            lcs["Latitude"],
            c=lcs["value_pm25_ug_m3"],
            cmap="viridis",
            vmin=vmin,
            vmax=vmax,
            s=18,
            alpha=0.78,
            edgecolors="white",
            linewidths=0.20,
            zorder=3,
            label="Chicago LCS",
        )
        axis.scatter(
            aqs["Longitude"],
            aqs["Latitude"],
            c=aqs["value_pm25_ug_m3"],
            cmap="viridis",
            vmin=vmin,
            vmax=vmax,
            s=76,
            marker="^",
            alpha=0.98,
            edgecolors=TEXT_COLOR,
            linewidths=0.80,
            zorder=4,
            label="EPA AQS",
        )
        lcs_stats = network_stats(lcs)
        aqs_stats = network_stats(aqs)
        axis.set_title(title, fontsize=10.5, fontweight="bold")
        axis.text(
            0.02,
            0.035,
            f"LCS n={lcs_stats['n']}, mean={lcs_stats['mean']:.1f}\nAQS n={aqs_stats['n']}, mean={aqs_stats['mean']:.1f}",
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.28", facecolor="white", edgecolor="#d1d5db", alpha=0.92),
            zorder=6,
        )

    handles = [
        mlines.Line2D([], [], marker="o", markersize=6, linestyle="None", markerfacecolor="#6dbe8a", markeredgecolor="white", label="Chicago LCS"),
        mlines.Line2D([], [], marker="^", markersize=8, linestyle="None", markerfacecolor="#6dbe8a", markeredgecolor=TEXT_COLOR, label="EPA AQS reference site"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.43, 0.035), fontsize=8.5)
    cbar_ax = fig.add_axes([0.82, 0.18, 0.018, 0.66])
    cbar = fig.colorbar(scatter_for_colorbar, cax=cbar_ax)
    cbar.set_label(r"PM$_{2.5}$ ($\mu$g m$^{-3}$)")
    fig.suptitle("Chicago low-cost-sensor values with EPA AQS reference context", y=0.965, fontsize=12)
    fig.subplots_adjust(left=0.07, right=0.79, top=0.88, bottom=0.13, wspace=0.12)
    save_figure(fig, PLOT_DIR / "chicago_pm25_lcs_aqs_daily_period_map")
    plt.close(fig)

    concept = f"""# SI Figure 1 candidate: Chicago PM2.5 value/reference map

## Rationale

The previous three-city missingness map was visually crowded and hard to interpret because it mixed three different geographies, two time bases, and a missingness color scale in one figure. For an SI data-quality figure, a cleaner alternative is a Chicago-only value map that shows the low-cost-sensor field and the regulatory/reference context directly.

## Proposed visual

- Panel A: January 1, 2026 daily mean PM2.5 at Chicago LCS sites and EPA AQS sites.
- Panel B: September 1, 2025 through March 31, 2026 mean PM2.5 at the same sites, using the period when both the LCS and AQS daily datasets have valid values.
- Circles show non-collocated Chicago LCS sensors used as the primary finite population.
- Triangles show EPA AQS reference sites.
- Cook County and City of Chicago boundaries remain visible but do not dominate the figure.
- A shared color scale is used across both panels, so daily and period patterns can be compared visually.

## Data caveat

The period panel fixes the plotted window at {PERIOD_START_DATE} to {PERIOD_END_DATE} for both LCS and AQS. This is the matched valid AQS period in the current daily files; April 2026 AQS rows exist in the local file but contain no valid PM2.5 values. Within this window, the LCS daily file has {lcs_meta['n_valid_dates']} valid daily rows and the AQS daily file has {aqs_meta['n_valid_dates']} valid daily rows. January 1, 2026 is available for both LCS and AQS.

## Summary numbers

{markdown_table(stats)}

## Audit files

- Plot: `manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_1/chicago_pm25_lcs_aqs_daily_period_map.pdf`
- Plot data: `analysis/results/chicago_si1_pm25_reference_map/chicago_si1_pm25_reference_map_data.csv`
- Summary: `analysis/results/chicago_si1_pm25_reference_map/chicago_si1_pm25_reference_map_summary.csv`
"""
    (OUT_DIR / "chicago_si1_pm25_reference_map_concept_note.md").write_text(concept)

    metadata = {
        "target_date": TARGET_DATE,
        "lcs_daily_file": str(LCS_PM.relative_to(REPO_ROOT)),
        "aqs_daily_file": str(AQS_PM.relative_to(REPO_ROOT)),
        "lcs_location_file": str(LCS_LOC.relative_to(REPO_ROOT)),
        "aqs_location_file": str(AQS_LOC.relative_to(REPO_ROOT)),
        "period_panel_window": {
            "start_date": PERIOD_START_DATE,
            "end_date": PERIOD_END_DATE,
            "description": "matched valid period used for both LCS and AQS period panel",
        },
        "lcs_period": lcs_meta,
        "aqs_period": aqs_meta,
        "vmin": vmin,
        "vmax": vmax,
        "outputs": {
            "plot_pdf": str((PLOT_DIR / "chicago_pm25_lcs_aqs_daily_period_map.pdf").relative_to(REPO_ROOT)),
            "plot_png": str((PLOT_DIR / "chicago_pm25_lcs_aqs_daily_period_map.png").relative_to(REPO_ROOT)),
            "data_csv": str((OUT_DIR / "chicago_si1_pm25_reference_map_data.csv").relative_to(REPO_ROOT)),
            "summary_csv": str((OUT_DIR / "chicago_si1_pm25_reference_map_summary.csv").relative_to(REPO_ROOT)),
            "concept_note": str((OUT_DIR / "chicago_si1_pm25_reference_map_concept_note.md").relative_to(REPO_ROOT)),
        },
    }
    (OUT_DIR / "chicago_si1_pm25_reference_map_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    build()
