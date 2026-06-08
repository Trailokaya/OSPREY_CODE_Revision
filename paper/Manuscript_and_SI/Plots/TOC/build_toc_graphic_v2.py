"""Build the ACS graphical table-of-contents image.

The right panel uses retained period MdAPE curves from the manuscript Monte
Carlo outputs. The left panel shows the Lucknow network footprint with a
deterministic, spatially balanced example subnetwork.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Polygon as MplPolygon


REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = Path(__file__).resolve().parent

CURVES_CSV = REPO_ROOT / "monte_carlo/plots/figure_data/period_error_curves.csv"
COORDS_CSV = (
    REPO_ROOT
    / "analysis/results/three_city_comparative_analysis/comparative_sensor_level_summary.csv"
)

SERIES = [
    ("Dhaka", "dhaka_lcs", "#d97706"),
    ("Lucknow", "lucknow_lcs", "#2563eb"),
    ("Chicago", "chicago_lcs_corrected_no_collocation", "#9f1239"),
]

PICK = "#0f766e"
INK = "#0f172a"
GREY = "#aab4c4"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "axes.linewidth": 0.6,
    }
)


def load_period_curves() -> dict[str, dict[str, object]]:
    curves: dict[str, dict[str, object]] = {}
    wanted = {dataset_key for _, dataset_key, _ in SERIES}
    with CURVES_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["dataset_key"] not in wanted:
                continue
            if row["scenario"] != "S0_baseline":
                continue
            if row["estimator"] != "arithmetic_mean":
                continue
            if row["placement"] != "random_srswor":
                continue
            if row["time_aggregation"] != "period" or row["time_index"] != "study_period":
                continue

            sample_size = int(row["sample_size"])
            if not 2 <= sample_size <= 30:
                continue

            entry = curves.setdefault(
                row["dataset_key"],
                {
                    "city": row["city"],
                    "n_sensors": int(row["n_sensors_available"]),
                    "points": {},
                },
            )
            entry["points"][sample_size] = float(row["ape_median"])

    missing = wanted - set(curves)
    if missing:
        raise RuntimeError(f"Missing TOC curve data for: {sorted(missing)}")
    return curves


def load_lucknow_points() -> np.ndarray:
    lon: list[float] = []
    lat: list[float] = []
    with COORDS_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["city"] != "Lucknow":
                continue
            if not row["latitude"] or not row["longitude"]:
                continue
            lat.append(float(row["latitude"]))
            lon.append(float(row["longitude"]))
    if not lon:
        raise RuntimeError("No Lucknow coordinates found for TOC map panel")
    return np.column_stack([lon, lat])


def convex_hull(points: np.ndarray) -> np.ndarray:
    pts = sorted(map(tuple, points))

    def half(seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
        hull: list[tuple[float, float]] = []
        for point in seq:
            while len(hull) >= 2:
                cross = (hull[-1][0] - hull[-2][0]) * (point[1] - hull[-2][1]) - (
                    hull[-1][1] - hull[-2][1]
                ) * (point[0] - hull[-2][0])
                if cross > 0:
                    break
                hull.pop()
            hull.append(point)
        return hull[:-1]

    return np.array(half(pts) + half(pts[::-1]))


def point_in_hull(x: float, y: float, hull: np.ndarray) -> bool:
    inside = False
    j = len(hull) - 1
    for i in range(len(hull)):
        xi, yi = hull[i]
        xj, yj = hull[j]
        if (yi > y) != (yj > y):
            x_at_y = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < x_at_y:
                inside = not inside
        j = i
    return inside


def balanced_subnetwork(points: np.ndarray, k: int, hull: np.ndarray, seed: int = 11) -> list[int]:
    bounds_min = points.min(axis=0)
    bounds_max = points.max(axis=0)
    grid_x = np.linspace(bounds_min[0], bounds_max[0], 55)
    grid_y = np.linspace(bounds_min[1], bounds_max[1], 55)
    grid = np.array([(x, y) for x in grid_x for y in grid_y if point_in_hull(x, y, hull)])

    rng = np.random.default_rng(seed)
    centroids = grid[rng.choice(len(grid), k, replace=False)].astype(float)
    for _ in range(120):
        labels = np.argmin(((grid[:, None, :] - centroids[None]) ** 2).sum(axis=2), axis=1)
        new_centroids = np.array(
            [
                grid[labels == idx].mean(axis=0) if (labels == idx).any() else centroids[idx]
                for idx in range(k)
            ]
        )
        if np.allclose(new_centroids, centroids):
            break
        centroids = new_centroids

    selected: list[int] = []
    used: set[int] = set()
    for centroid in centroids:
        for idx in np.argsort(((points - centroid) ** 2).sum(axis=1)):
            idx = int(idx)
            if idx not in used:
                used.add(idx)
                selected.append(idx)
                break
    return selected


def main() -> None:
    curves = load_period_curves()
    points = load_lucknow_points()
    hull = convex_hull(points)
    selected = balanced_subnetwork(points, 7, hull)

    fig = plt.figure(figsize=(3.25, 1.75), dpi=600)
    fig.patch.set_facecolor("white")

    fig.text(
        0.5,
        0.965,
        "A well-spread subnetwork can closely estimate a denser network's mean PM$_{2.5}$",
        ha="center",
        va="top",
        fontsize=5.2,
        fontweight="bold",
        color=INK,
    )
    fig.text(
        0.5,
        0.035,
        "Adding more sensors gives diminishing returns beyond n = 10-15",
        ha="center",
        va="bottom",
        fontsize=6.0,
        color="#64748b",
        style="italic",
    )

    ax_map = fig.add_axes([0.03, 0.345, 0.25, 0.40])
    ax_map.axis("off")
    ax_map.set_aspect("equal")
    ax_map.add_patch(
        MplPolygon(hull, closed=True, facecolor="#eaf0fb", edgecolor="#c2d2f3", lw=0.7, zorder=0)
    )
    ax_map.scatter(points[:, 0], points[:, 1], s=4.5, color=GREY, alpha=0.75, linewidths=0, zorder=2)
    ax_map.scatter(
        points[selected, 0],
        points[selected, 1],
        s=17,
        color=PICK,
        edgecolors="white",
        linewidths=0.5,
        zorder=4,
    )
    margin = 0.04
    ax_map.set_xlim(points[:, 0].min() - margin, points[:, 0].max() + margin)
    ax_map.set_ylim(points[:, 1].min() - margin, points[:, 1].max() + margin)
    ax_map.text(
        0.5,
        -0.08,
        "a subset of the\nreference network",
        transform=ax_map.transAxes,
        ha="center",
        va="top",
        fontsize=6.4,
        color=INK,
        linespacing=1.05,
    )

    fig.add_artist(
        FancyArrowPatch(
            (0.29, 0.50),
            (0.395, 0.50),
            transform=fig.transFigure,
            arrowstyle="-|>",
            mutation_scale=9,
            lw=1.1,
            color=INK,
        )
    )
    fig.text(
        0.342,
        0.55,
        "many random\nsubsets",
        ha="center",
        va="bottom",
        fontsize=6.0,
        color="#64748b",
        linespacing=1.0,
    )

    ax_curve = fig.add_axes([0.585, 0.30, 0.385, 0.45])
    ax_curve.axhspan(0, 10, color="#ecfdf5", zorder=0)

    for city, dataset_key, color in SERIES:
        entry = curves[dataset_key]
        curve_points = entry["points"]
        sample_sizes = sorted(curve_points)
        ax_curve.plot(
            sample_sizes,
            [curve_points[n] for n in sample_sizes],
            color=color,
            lw=1.4,
            zorder=3,
            label=city,
        )

    ax_curve.axvspan(10, 15, color="#0f172a", alpha=0.06, zorder=1)
    ax_curve.axhline(10, color="#475569", lw=0.8, ls=(0, (4, 2)), zorder=2)
    ax_curve.text(
        12.5,
        13.4,
        "10-15\nsensors",
        ha="center",
        va="top",
        fontsize=6.2,
        color=INK,
        linespacing=1.0,
        fontweight="bold",
    )
    ax_curve.set_xlim(2, 30)
    ax_curve.set_ylim(0, 14)
    ax_curve.set_xticks([2, 10, 20, 30])
    ax_curve.set_yticks([0, 5, 10])
    ax_curve.tick_params(labelsize=6.3, length=2, pad=1.5, color="#94a3b8")
    for spine in ("top", "right"):
        ax_curve.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax_curve.spines[spine].set_color("#94a3b8")
    ax_curve.set_xlabel("Sensors in subnetwork (n)", fontsize=6.4, color=INK, labelpad=1.5)
    ax_curve.set_ylabel("Error %\n(reference - subnetwork mean)", fontsize=6.0, color=INK, labelpad=2)
    ax_curve.legend(
        loc="upper right",
        bbox_to_anchor=(1.0, 1.08),
        fontsize=5.7,
        frameon=True,
        framealpha=0.9,
        facecolor="white",
        edgecolor="white",
        borderpad=0.12,
        handlelength=0.85,
        borderaxespad=0.0,
        labelspacing=0.18,
        handletextpad=0.35,
    )

    fig.savefig(OUT_DIR / "TOC_v2.pdf", facecolor="white")
    fig.savefig(OUT_DIR / "TOC_v2.png", facecolor="white", dpi=600)
    plt.close(fig)


if __name__ == "__main__":
    main()
