from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely import contains_xy

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis/src"))
sys.path.insert(0, str(REPO_ROOT / "maps/scripts"))

from build_network_maps import geojson_bounds, load_geojson, polygon_patch  # noqa: E402
from plot_style import CITY_COLORS, GRID_COLOR, OUTPUT_DPI, TEXT_COLOR, save_figure, setup_matplotlib  # noqa: E402

OUT_DIR = REPO_ROOT / "analysis/results/si1_continuous_field_sampling"
PLOT_DIR = REPO_ROOT / "manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_1"

LCS_PM = REPO_ROOT / "data/pm/Chicago_LCS_corrected_daily_PM25.csv"
AQS_PM = REPO_ROOT / "data/pm/Chicago_AQS_daily_PM25.csv"
LCS_LOC = REPO_ROOT / "data/locations/Chicago_LCS_corrected_sensor_locations.csv"
AQS_LOC = REPO_ROOT / "data/locations/Chicago_AQS_sensor_locations.csv"
CITY_GEOJSON = REPO_ROOT / "data/geo/Chicago_City_admin6.geojson"
DISTRICT_GEOJSON = REPO_ROOT / "data/geo/Chicago_District_admin5.geojson"

TARGET_DATE = "2026-01-01"
ILLUSTRATIVE_SEED = 20260531
SUBNETWORK_N = 10


def read_daily_pm(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    local_ts = pd.to_datetime(frame["Timestamp"], utc=True).dt.tz_convert("America/Chicago")
    frame = frame.copy()
    frame["local_date"] = local_ts.dt.strftime("%Y-%m-%d")
    return frame


def primary_lcs_locations() -> pd.DataFrame:
    loc = pd.read_csv(LCS_LOC)
    return loc[~loc["Station_Name"].astype(str).str.contains("collocation", case=False, na=False)].copy()


def data_columns(pm: pd.DataFrame) -> list[str]:
    return [col for col in pm.columns if col not in {"Timestamp", "local_date"}]


def daily_values(pm: pd.DataFrame, date: str) -> pd.Series:
    cols = data_columns(pm)
    row = pm.loc[pm["local_date"] == date]
    if row.empty:
        raise ValueError(f"No daily row for {date} in {pm}")
    return pd.to_numeric(row[cols].iloc[0], errors="coerce")


def period_values(pm: pd.DataFrame) -> tuple[pd.Series, dict[str, str | int]]:
    cols = data_columns(pm)
    numeric = pm[cols].apply(pd.to_numeric, errors="coerce")
    metadata = {
        "start_date": str(pm["local_date"].min()),
        "end_date": str(pm["local_date"].max()),
        "n_dates": int(pm["local_date"].nunique()),
    }
    return numeric.mean(axis=0, skipna=True), metadata


def valid_dates(pm: pd.DataFrame) -> set[str]:
    cols = data_columns(pm)
    numeric = pm[cols].apply(pd.to_numeric, errors="coerce")
    return set(pm.loc[numeric.notna().any(axis=1), "local_date"].astype(str))


def common_period_frames(lcs_pm: pd.DataFrame, aqs_pm: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str | int]]:
    common_dates = sorted(valid_dates(lcs_pm) & valid_dates(aqs_pm))
    if not common_dates:
        raise ValueError("No shared valid dates found between Chicago LCS and EPA AQS daily files")
    metadata = {
        "start_date": common_dates[0],
        "end_date": common_dates[-1],
        "n_dates": len(common_dates),
    }
    return (
        lcs_pm[lcs_pm["local_date"].isin(common_dates)].copy(),
        aqs_pm[aqs_pm["local_date"].isin(common_dates)].copy(),
        metadata,
    )


def geojson_union(data: dict):
    geometries = [shape(feature["geometry"]) for feature in data.get("features", []) if feature.get("geometry")]
    return unary_union(geometries)


def expanded_bounds(bounds: tuple[float, float, float, float], pad_fraction: float = 0.035) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    dx = maxx - minx
    dy = maxy - miny
    return minx - dx * pad_fraction, miny - dy * pad_fraction, maxx + dx * pad_fraction, maxy + dy * pad_fraction


def bounds_with_points(
    base_bounds: tuple[float, float, float, float],
    frames: list[pd.DataFrame],
    pad_fraction: float = 0.04,
) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = base_bounds
    for frame in frames:
        minx = min(minx, float(frame["Longitude"].min()))
        miny = min(miny, float(frame["Latitude"].min()))
        maxx = max(maxx, float(frame["Longitude"].max()))
        maxy = max(maxy, float(frame["Latitude"].max()))
    return expanded_bounds((minx, miny, maxx, maxy), pad_fraction=pad_fraction)


def synthetic_field(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    x = (lon + 87.72) / 0.22
    y = (lat - 41.84) / 0.24
    regional_gradient = 8.5 + 2.1 * x - 1.4 * y
    south_plume = 5.4 * np.exp(-(((lon + 87.66) / 0.085) ** 2 + ((lat - 41.69) / 0.075) ** 2))
    west_plume = 3.0 * np.exp(-(((lon + 87.82) / 0.070) ** 2 + ((lat - 41.93) / 0.060) ** 2))
    lake_gradient = -1.6 * np.exp(-((lon + 87.56) / 0.055) ** 2)
    ripple = 0.45 * np.sin((lon + 87.75) * 35) * np.cos((lat - 41.82) * 24)
    return np.clip(regional_gradient + south_plume + west_plume + lake_gradient + ripple, 2.0, 20.0)


def merge_values(loc: pd.DataFrame, values: pd.Series, network: str, panel: str, metadata: dict[str, str | int]) -> pd.DataFrame:
    out = loc.copy()
    out["value_pm25_ug_m3"] = out["Sensor_ID"].map(values)
    out["network"] = network
    out["panel"] = panel
    out["start_date"] = metadata["start_date"]
    out["end_date"] = metadata["end_date"]
    out["n_dates_available_for_network"] = metadata["n_dates"]
    return out.dropna(subset=["value_pm25_ug_m3"])


def frame_stats(frame: pd.DataFrame) -> dict[str, float | int]:
    values = pd.to_numeric(frame["value_pm25_ug_m3"], errors="coerce")
    return {
        "n": int(values.notna().sum()),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "min": float(values.min()),
        "max": float(values.max()),
    }


def add_boundaries(axis: plt.Axes, bounds: tuple[float, float, float, float], city_geojson: dict, district_geojson: dict) -> None:
    city_color = CITY_COLORS["chicago"]
    axis.add_patch(
        polygon_patch(
            district_geojson,
            facecolor="none",
            edgecolor=city_color,
            alpha=0.45,
            linewidth=0.8,
            zorder=5,
        )
    )
    axis.add_patch(
        polygon_patch(
            city_geojson,
            facecolor="none",
            edgecolor=city_color,
            alpha=0.95,
            linewidth=1.1,
            zorder=6,
        )
    )
    axis.set_xlim(bounds[0], bounds[2])
    axis.set_ylim(bounds[1], bounds[3])
    axis.set_aspect("equal", adjustable="box")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)


def add_panel_label(axis: plt.Axes, label: str, title: str) -> None:
    axis.text(
        0.02,
        0.98,
        label,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="#d1d5db", alpha=0.95),
        zorder=20,
    )
    axis.set_title(title, fontsize=9.7, fontweight="bold", pad=4)


def markdown_table(frame: pd.DataFrame) -> str:
    rows = ["| " + " | ".join(frame.columns) + " |", "| " + " | ".join(["---"] * len(frame.columns)) + " |"]
    for _, row in frame.iterrows():
        values = []
        for value in row:
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

    city_geojson = load_geojson(CITY_GEOJSON)
    district_geojson = load_geojson(DISTRICT_GEOJSON)
    city_shape = geojson_union(city_geojson)
    lcs_loc = primary_lcs_locations()
    aqs_loc = pd.read_csv(AQS_LOC)
    map_bounds = bounds_with_points(geojson_bounds(city_geojson), [lcs_loc, aqs_loc], pad_fraction=0.04)
    lcs_pm = read_daily_pm(LCS_PM)
    aqs_pm = read_daily_pm(AQS_PM)

    lcs_daily_values = daily_values(lcs_pm, TARGET_DATE)
    aqs_daily_values = daily_values(aqs_pm, TARGET_DATE)
    _, lcs_full_period_meta = period_values(lcs_pm)
    _, aqs_full_period_meta = period_values(aqs_pm)
    lcs_common_pm, aqs_common_pm, shared_period_meta = common_period_frames(lcs_pm, aqs_pm)
    lcs_period_values, lcs_period_meta = period_values(lcs_common_pm)
    aqs_period_values, aqs_period_meta = period_values(aqs_common_pm)
    daily_meta = {"start_date": TARGET_DATE, "end_date": TARGET_DATE, "n_dates": 1}

    actual_data = pd.concat(
        [
            merge_values(lcs_loc, lcs_daily_values, "Chicago LCS", "Jan 1, 2026", daily_meta),
            merge_values(aqs_loc, aqs_daily_values, "EPA AQS", "Jan 1, 2026", daily_meta),
            merge_values(lcs_loc, lcs_period_values, "Chicago LCS", "Shared period", lcs_period_meta),
            merge_values(aqs_loc, aqs_period_values, "EPA AQS", "Shared period", aqs_period_meta),
        ],
        ignore_index=True,
    )

    lons = np.linspace(map_bounds[0], map_bounds[2], 260)
    lats = np.linspace(map_bounds[1], map_bounds[3], 260)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    mask = contains_xy(city_shape, lon_grid, lat_grid)
    field = np.ma.array(synthetic_field(lon_grid, lat_grid), mask=~mask)
    lcs_loc = lcs_loc.copy()
    lcs_loc["synthetic_pm25_ug_m3"] = synthetic_field(lcs_loc["Longitude"].to_numpy(), lcs_loc["Latitude"].to_numpy())

    rng = np.random.default_rng(ILLUSTRATIVE_SEED)
    valid_indices = np.flatnonzero(lcs_loc["synthetic_pm25_ug_m3"].notna().to_numpy())
    selected_indices = rng.choice(valid_indices, size=SUBNETWORK_N, replace=False)
    lcs_loc["selected_for_concept"] = False
    lcs_loc.loc[lcs_loc.index[selected_indices], "selected_for_concept"] = True
    full_synthetic_mean = float(lcs_loc["synthetic_pm25_ug_m3"].mean())
    selected_synthetic_mean = float(lcs_loc.loc[lcs_loc["selected_for_concept"], "synthetic_pm25_ug_m3"].mean())

    concept_data = lcs_loc[
        ["Sensor_ID", "Latitude", "Longitude", "synthetic_pm25_ug_m3", "selected_for_concept"]
    ].copy()
    concept_data.to_csv(OUT_DIR / "si1_conceptual_sampling_sensor_values.csv", index=False)
    actual_data.to_csv(OUT_DIR / "si1_chicago_actual_daily_period_values.csv", index=False)

    summary_rows = []
    for (panel, network), group in actual_data.groupby(["panel", "network"]):
        row = {"panel": panel, "network": network, **frame_stats(group)}
        row["start_date"] = str(group["start_date"].iloc[0])
        row["end_date"] = str(group["end_date"].iloc[0])
        row["n_dates_available_for_network"] = int(group["n_dates_available_for_network"].iloc[0])
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows).sort_values(["panel", "network"])
    concept_summary = pd.DataFrame(
        [
            {
                "panel": "Conceptual field",
                "network": "Full deployed LCS sample",
                "n": len(lcs_loc),
                "mean": full_synthetic_mean,
                "median": float(lcs_loc["synthetic_pm25_ug_m3"].median()),
                "min": float(lcs_loc["synthetic_pm25_ug_m3"].min()),
                "max": float(lcs_loc["synthetic_pm25_ug_m3"].max()),
                "start_date": "not applicable",
                "end_date": "not applicable",
                "n_dates_available_for_network": 0,
            },
            {
                "panel": "Conceptual field",
                "network": f"One n={SUBNETWORK_N} subnetwork",
                "n": SUBNETWORK_N,
                "mean": selected_synthetic_mean,
                "median": float(lcs_loc.loc[lcs_loc["selected_for_concept"], "synthetic_pm25_ug_m3"].median()),
                "min": float(lcs_loc.loc[lcs_loc["selected_for_concept"], "synthetic_pm25_ug_m3"].min()),
                "max": float(lcs_loc.loc[lcs_loc["selected_for_concept"], "synthetic_pm25_ug_m3"].max()),
                "start_date": "not applicable",
                "end_date": "not applicable",
                "n_dates_available_for_network": 0,
            },
        ]
    )
    all_summary = pd.concat([concept_summary, summary], ignore_index=True)
    all_summary.to_csv(OUT_DIR / "si1_continuous_field_sampling_summary.csv", index=False)

    norm = Normalize(vmin=0, vmax=20)
    cmap = "viridis"
    chicago_color = CITY_COLORS["chicago"]
    aqs_color = "#111827"

    fig, axes = plt.subplots(2, 3, figsize=(11.0, 7.2), constrained_layout=False)
    for axis in axes.flat:
        axis.set_facecolor("white")

    field_artist = axes[0, 0].contourf(lon_grid, lat_grid, field, levels=np.linspace(0, 20, 17), cmap=cmap, norm=norm, zorder=1)
    add_boundaries(axes[0, 0], map_bounds, city_geojson, district_geojson)
    add_panel_label(axes[0, 0], "A", "Unobserved continuous field")
    axes[0, 0].text(
        0.04,
        0.05,
        "Illustrative smooth field,\nnot observed directly",
        transform=axes[0, 0].transAxes,
        ha="left",
        va="bottom",
        fontsize=7.8,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#d1d5db", alpha=0.93),
        zorder=20,
    )

    axes[0, 1].contourf(lon_grid, lat_grid, field, levels=np.linspace(0, 20, 17), cmap=cmap, norm=norm, alpha=0.24, zorder=1)
    add_boundaries(axes[0, 1], map_bounds, city_geojson, district_geojson)
    axes[0, 1].scatter(
        lcs_loc["Longitude"],
        lcs_loc["Latitude"],
        c=lcs_loc["synthetic_pm25_ug_m3"],
        cmap=cmap,
        norm=norm,
        s=12,
        alpha=0.82,
        edgecolors="white",
        linewidths=0.18,
        zorder=10,
    )
    add_panel_label(axes[0, 1], "B", "Deployed network sample points")
    axes[0, 1].text(
        0.04,
        0.05,
        "The estimand is the\nmean of sampled sites",
        transform=axes[0, 1].transAxes,
        ha="left",
        va="bottom",
        fontsize=7.8,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#d1d5db", alpha=0.93),
        zorder=20,
    )

    axes[0, 2].scatter(
        lcs_loc["Longitude"],
        lcs_loc["Latitude"],
        s=9,
        color="#cbd5e1",
        alpha=0.75,
        edgecolors="none",
        zorder=8,
    )
    selected = lcs_loc[lcs_loc["selected_for_concept"]]
    axes[0, 2].scatter(
        selected["Longitude"],
        selected["Latitude"],
        c=selected["synthetic_pm25_ug_m3"],
        cmap=cmap,
        norm=norm,
        s=46,
        marker="o",
        edgecolors=TEXT_COLOR,
        linewidths=0.55,
        zorder=12,
    )
    add_boundaries(axes[0, 2], map_bounds, city_geojson, district_geojson)
    add_panel_label(axes[0, 2], "C", "A subnetwork estimates that mean")
    axes[0, 2].text(
        0.04,
        0.05,
        f"Full network mean: {full_synthetic_mean:.1f}\nSubnetwork mean: {selected_synthetic_mean:.1f}",
        transform=axes[0, 2].transAxes,
        ha="left",
        va="bottom",
        fontsize=7.8,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#d1d5db", alpha=0.93),
        zorder=20,
    )

    panel_specs = [
        (axes[1, 0], "Jan 1, 2026", "D", "Actual daily samples"),
        (axes[1, 1], "Shared period", "E", "Actual shared-period samples"),
    ]
    for axis, panel, label, title in panel_specs:
        add_boundaries(axis, map_bounds, city_geojson, district_geojson)
        panel_data = actual_data[actual_data["panel"] == panel]
        lcs = panel_data[panel_data["network"] == "Chicago LCS"]
        aqs = panel_data[panel_data["network"] == "EPA AQS"]
        axis.scatter(
            lcs["Longitude"],
            lcs["Latitude"],
            c=lcs["value_pm25_ug_m3"],
            cmap=cmap,
            norm=norm,
            s=13,
            alpha=0.80,
            edgecolors="white",
            linewidths=0.16,
            zorder=10,
        )
        axis.scatter(
            aqs["Longitude"],
            aqs["Latitude"],
            c=aqs["value_pm25_ug_m3"],
            cmap=cmap,
            norm=norm,
            s=58,
            marker="^",
            alpha=0.98,
            edgecolors=aqs_color,
            linewidths=0.70,
            zorder=12,
        )
        add_panel_label(axis, label, title)
        lcs_stats = frame_stats(lcs)
        aqs_stats = frame_stats(aqs)
        axis.text(
            0.04,
            0.05,
            f"LCS n={lcs_stats['n']}, mean={lcs_stats['mean']:.1f}\nAQS n={aqs_stats['n']}, mean={aqs_stats['mean']:.1f}",
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=7.8,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#d1d5db", alpha=0.93),
            zorder=20,
        )

    means = []
    for panel in ["Jan 1, 2026", "Shared period"]:
        for network in ["Chicago LCS", "EPA AQS"]:
            group = actual_data[(actual_data["panel"] == panel) & (actual_data["network"] == network)]
            means.append(
                {
                    "panel": "Jan 1" if panel == "Jan 1, 2026" else "Shared period",
                    "network": network,
                    "mean": frame_stats(group)["mean"],
                    "n": frame_stats(group)["n"],
                }
            )
    means_frame = pd.DataFrame(means)
    means_frame.to_csv(OUT_DIR / "si1_chicago_actual_mean_comparison.csv", index=False)

    axis = axes[1, 2]
    x_positions = {"Jan 1": 0, "Shared period": 1}
    offsets = {"Chicago LCS": -0.08, "EPA AQS": 0.08}
    markers = {"Chicago LCS": "o", "EPA AQS": "^"}
    colors = {"Chicago LCS": chicago_color, "EPA AQS": aqs_color}
    for _, row in means_frame.iterrows():
        axis.scatter(
            x_positions[row["panel"]] + offsets[row["network"]],
            row["mean"],
            s=95 if row["network"] == "EPA AQS" else 75,
            marker=markers[row["network"]],
            color=colors[row["network"]],
            edgecolors="white" if row["network"] == "Chicago LCS" else TEXT_COLOR,
            linewidths=0.7,
            zorder=10,
        )
        axis.text(
            x_positions[row["panel"]] + offsets[row["network"]],
            row["mean"] + 0.45,
            f"{row['mean']:.1f}",
            ha="center",
            va="bottom",
            fontsize=7.7,
        )
    axis.set_xlim(-0.45, 1.45)
    axis.set_ylim(0, 13.5)
    axis.set_xticks([0, 1], ["Jan 1, 2026", "Shared period"])
    axis.set_ylabel(r"Mean PM$_{2.5}$ ($\mu$g m$^{-3}$)")
    axis.grid(True, axis="y", color=GRID_COLOR, linestyle="--", linewidth=0.5)
    add_panel_label(axis, "F", "What the samples summarize")
    axis.text(
        0.02,
        0.04,
        f"Shared period:\n{shared_period_meta['start_date']}--{shared_period_meta['end_date']}\n"
        f"({shared_period_meta['n_dates']} days)",
        transform=axis.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.5,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#d1d5db", alpha=0.93),
    )

    handles = [
        mlines.Line2D([], [], marker="o", markersize=6, linestyle="None", markerfacecolor=chicago_color, markeredgecolor="white", label="Chicago LCS"),
        mlines.Line2D([], [], marker="^", markersize=7, linestyle="None", markerfacecolor=aqs_color, markeredgecolor=TEXT_COLOR, label="EPA AQS reference site"),
        mlines.Line2D([], [], marker="o", markersize=5, linestyle="None", markerfacecolor="#cbd5e1", markeredgecolor="none", label="Non-selected LCS in concept panel"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.48, 0.02), fontsize=8)
    cbar_ax = fig.add_axes([0.925, 0.18, 0.016, 0.66])
    cbar = fig.colorbar(field_artist, cax=cbar_ax)
    cbar.set_label(r"PM$_{2.5}$ scale ($\mu$g m$^{-3}$; top row illustrative)")
    fig.suptitle("Continuous-field concept and Chicago point-sample context", y=0.972, fontsize=12, fontweight="bold")
    fig.subplots_adjust(left=0.04, right=0.90, top=0.91, bottom=0.10, wspace=0.08, hspace=0.20)
    save_figure(fig, PLOT_DIR / "si1_continuous_field_sampling_chicago")

    note = f"""# SI Figure 1: continuous-field concept and Chicago point-sample context

## Purpose

This figure is designed to make the finite-population estimand explicit. The upper row shows a hypothetical continuous PM2.5 field, then the finite point samples observed by a deployed network, then one subnetwork drawn from that finite population. The lower row shows the analogous Chicago data example: actual Jan 1, 2026 samples, actual shared-period mean samples, and the network-mean summaries available from those samples.

## Date-window audit

- Chicago LCS daily corrected data span {lcs_full_period_meta['start_date']} to {lcs_full_period_meta['end_date']} ({lcs_full_period_meta['n_dates']} daily rows) in the current canonical file.
- Chicago AQS daily data span {aqs_full_period_meta['start_date']} to {aqs_full_period_meta['end_date']} ({aqs_full_period_meta['n_dates']} daily rows) in the current canonical file.
- The lower-row period panel restricts both networks to the shared valid-date overlap: {shared_period_meta['start_date']} to {shared_period_meta['end_date']} ({shared_period_meta['n_dates']} days). This avoids comparing an LCS nine-month mean with an AQS shorter-window mean.
- January 1, 2026 is available in both LCS and AQS daily files.

## Summary

{markdown_table(all_summary)}

## Files

- Figure PDF: `manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_1/si1_continuous_field_sampling_chicago.pdf`
- Figure PNG: `manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_1/si1_continuous_field_sampling_chicago.png`
- Actual data: `analysis/results/si1_continuous_field_sampling/si1_chicago_actual_daily_period_values.csv`
- Concept data: `analysis/results/si1_continuous_field_sampling/si1_conceptual_sampling_sensor_values.csv`
- Summary: `analysis/results/si1_continuous_field_sampling/si1_continuous_field_sampling_summary.csv`
"""
    (OUT_DIR / "si1_continuous_field_sampling_note.md").write_text(note)
    metadata = {
        "target_date": TARGET_DATE,
        "illustrative_seed": ILLUSTRATIVE_SEED,
        "subnetwork_n": SUBNETWORK_N,
        "lcs_full_period": lcs_full_period_meta,
        "aqs_full_period": aqs_full_period_meta,
        "shared_lcs_aqs_period": shared_period_meta,
        "period_panel_uses": "shared_lcs_aqs_period",
        "outputs": {
            "figure_pdf": str((PLOT_DIR / "si1_continuous_field_sampling_chicago.pdf").relative_to(REPO_ROOT)),
            "figure_png": str((PLOT_DIR / "si1_continuous_field_sampling_chicago.png").relative_to(REPO_ROOT)),
            "actual_data_csv": str((OUT_DIR / "si1_chicago_actual_daily_period_values.csv").relative_to(REPO_ROOT)),
            "concept_data_csv": str((OUT_DIR / "si1_conceptual_sampling_sensor_values.csv").relative_to(REPO_ROOT)),
            "summary_csv": str((OUT_DIR / "si1_continuous_field_sampling_summary.csv").relative_to(REPO_ROOT)),
            "note": str((OUT_DIR / "si1_continuous_field_sampling_note.md").relative_to(REPO_ROOT)),
        },
    }
    (OUT_DIR / "si1_continuous_field_sampling_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    build()
