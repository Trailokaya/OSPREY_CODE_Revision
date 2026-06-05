"""
Generate reviewer-requested figures for the ACS ES&T Air revision.

Creates:
  Figure SI 12 - Estimand-framing schematic (Reviewer 3 #19)
  Figure SI 13 - Daily cross-sensor distribution histograms (Reviewer 2 p.50)
  Figure SI 14 - Period MdAPE with visible 95th-percentile and worst-case bands (Reviewer 3 #12)

Outputs go to:
  manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_{12,13,14}/
"""

import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.lines import Line2D
from scipy import stats


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "data" / "pm").is_dir() and (candidate / "paper").is_dir():
            return candidate
    raise RuntimeError("Could not locate repository root from script path.")


ROOT = str(find_repo_root(Path(__file__).resolve()))
OUT_ROOT = os.path.join(
    ROOT,
    "manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information",
)

# Matplotlib defaults
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "axes.linewidth": 0.8,
    "savefig.bbox": "tight",
    "savefig.dpi": 600,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

# Common city color scheme
CITY_COLORS = {
    "Dhaka": "#D55E00",
    "Lucknow": "#0072B2",
    "Chicago": "#009E73",
}


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)


def save(fig, folder, basename):
    ensure_dir(folder)
    fig.savefig(os.path.join(folder, basename + ".pdf"))
    fig.savefig(os.path.join(folder, basename + ".png"))
    print(f"  wrote {folder}/{basename}.pdf and .png")


# ---------------------------------------------------------------------------
# Figure SI 12: estimand-framing schematic (Reviewer 3 #19)
# ---------------------------------------------------------------------------

def build_schematic():
    print("Building Figure SI 12 (estimand schematic)...")
    out_dir = os.path.join(OUT_ROOT, "Figure_SI_12")
    rng = np.random.default_rng(20260528)

    # Use Dhaka sensor coordinates as the deployed-network locations
    locs = pd.read_csv(os.path.join(ROOT, "data/locations/Dhaka_sensor_locations.csv"))
    x = locs["Longitude"].to_numpy()
    y = locs["Latitude"].to_numpy()

    # Normalize to a [0,1] box for cleaner schematic
    x_n = (x - x.min()) / (x.max() - x.min())
    y_n = (y - y.min()) / (y.max() - y.min())
    network_size = len(x_n)

    # Synthetic "true" pollution field on a grid: smooth sum of 2D Gaussians
    grid = np.linspace(0, 1, 200)
    X, Y = np.meshgrid(grid, grid)
    centers = rng.uniform(0.1, 0.9, size=(6, 2))
    weights = rng.uniform(0.5, 1.5, size=6)
    field = np.zeros_like(X)
    for (cx, cy), w in zip(centers, weights):
        field += w * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / 0.05)
    # Add some lower-amplitude background
    field += 0.4 * np.exp(-((X - 0.5) ** 2 + (Y - 0.5) ** 2) / 0.6)

    # Highlight a random subnetwork of 10 sensors
    subset_size = min(10, network_size)
    subnet_idx = rng.choice(network_size, size=subset_size, replace=False)

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.9))

    # Shared field colormap range
    vmin, vmax = field.min(), field.max()

    titles = [
        r"(a) Continuous field",
        rf"(b) Deployed LCS network ($N={network_size}$)",
        rf"(c) Random subnetwork ($n={subset_size}$)",
    ]

    for ax, title in zip(axes, titles):
        im = ax.imshow(
            field, origin="lower", extent=[0, 1, 0, 1],
            cmap="YlOrRd", vmin=vmin, vmax=vmax, alpha=0.85,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)
        ax.set_title(title, pad=8)

    # Panel B: all deployed sensors
    axes[1].scatter(
        x_n, y_n, s=40, c="0.15", edgecolor="white", linewidth=0.6, zorder=3,
        label=rf"Deployed sensors ($N={network_size}$)",
    )
    # Panel C: subset highlighted; non-selected sensors greyed
    mask = np.zeros(len(x_n), dtype=bool)
    mask[subnet_idx] = True
    axes[2].scatter(
        x_n[~mask], y_n[~mask], s=30, c="white", edgecolor="0.6", linewidth=0.7, zorder=2,
        label="Not in subnetwork",
    )
    axes[2].scatter(
        x_n[mask], y_n[mask], s=55, c="0.05", edgecolor="white", linewidth=0.7, zorder=3,
        label=rf"Sampled ($n={subset_size}$)",
    )
    legend_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="0.15", markeredgecolor="white", markersize=6, label="Deployed sensor"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor="0.6", markersize=6, label="Not sampled"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="0.05", markeredgecolor="white", markersize=6, label="Sampled sensor"),
    ]
    fig.legend(
        legend_handles,
        [handle.get_label() for handle in legend_handles],
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 0.145),
    )

    # Add a single horizontal colorbar below
    cbar_ax = fig.add_axes([0.18, 0.065, 0.64, 0.018])
    cbar = fig.colorbar(axes[0].images[0], cax=cbar_ax, orientation="horizontal")
    cbar.set_label("Relative PM$_{2.5}$ (arbitrary units)", fontsize=8)
    cbar.ax.tick_params(labelsize=7)
    cbar.set_ticks([])

    # (The explanatory sentence formerly placed above the panels is omitted here;
    #  it duplicated the LaTeX \caption and rendered as an awkward full-width strip.)
    plt.subplots_adjust(top=0.88, bottom=0.29, wspace=0.08, left=0.02, right=0.98)
    save(fig, out_dir, "estimand_schematic")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure SI 13: actual daily cross-sensor distributions (Reviewer 2 p.50)
# ---------------------------------------------------------------------------

def build_daily_distributions():
    print("Building Figure SI 13 (daily distributions)...")
    out_dir = os.path.join(OUT_ROOT, "Figure_SI_13")

    # Load hourly PM data and compute daily sensor means
    dhaka_h = pd.read_csv(os.path.join(ROOT, "data/pm/Dhaka_hourly_PM25.csv"),
                          parse_dates=["Timestamp"])
    lucknow_h = pd.read_csv(os.path.join(ROOT, "data/pm/Lucknow_hourly_PM25.csv"),
                            parse_dates=["Timestamp"])

    # Chicago is already daily
    chicago_d = pd.read_csv(os.path.join(ROOT, "data/pm/Chicago_LCS_corrected_daily_PM25.csv"),
                             parse_dates=["Timestamp"])

    def daily_sensor_means(df):
        df = df.set_index("Timestamp")
        return df.resample("D").mean(numeric_only=True)

    dhaka_d = daily_sensor_means(dhaka_h)
    lucknow_d = daily_sensor_means(lucknow_h)
    chicago_d = chicago_d.set_index("Timestamp")

    def representative_days(df, n_keep=3):
        # Compute daily network mean across sensors
        net_mean = df.mean(axis=1)
        valid = net_mean.dropna()
        # Pick low (5th), mid (50th), high (95th) percentile days
        q_low = valid.quantile(0.05)
        q_mid = valid.quantile(0.50)
        q_high = valid.quantile(0.95)
        targets = [q_low, q_mid, q_high]
        labels = ["Low (5th pct day)", "Median day", "High (95th pct day)"]
        picks = []
        for t, lab in zip(targets, labels):
            idx = (valid - t).abs().idxmin()
            picks.append((idx, lab))
        return picks

    cities = [
        ("Lucknow", lucknow_d),
        ("Dhaka", dhaka_d),
        ("Chicago", chicago_d),
    ]

    fig, axes = plt.subplots(3, 3, figsize=(12.2, 9.2), constrained_layout=False)

    for row, (city, df) in enumerate(cities):
        picks = representative_days(df)
        for col, (day, label) in enumerate(picks):
            ax = axes[row, col]
            vals = df.loc[day].dropna().to_numpy()
            if len(vals) < 3:
                ax.text(0.5, 0.5, "Insufficient sensors", ha="center", va="center",
                        transform=ax.transAxes)
                continue

            # Histogram on raw values
            n_bins = min(20, max(5, int(np.sqrt(len(vals)))))
            ax.hist(vals, bins=n_bins, color=CITY_COLORS[city], alpha=0.62,
                    edgecolor="white", linewidth=0.5, density=True)

            # Overlay normal fit
            mu, sigma = np.mean(vals), np.std(vals, ddof=1)
            x_axis = np.linspace(max(0.001, vals.min() * 0.5), vals.max() * 1.3, 200)
            if sigma > 0:
                pdf_n = stats.norm.pdf(x_axis, loc=mu, scale=sigma)
                ax.plot(x_axis, pdf_n, color="0.12", lw=1.25, label="Normal")

            # Overlay lognormal fit if all positive
            if (vals > 0).all() and len(vals) > 2:
                try:
                    shape, loc_p, scale_p = stats.lognorm.fit(vals, floc=0)
                    pdf_ln = stats.lognorm.pdf(x_axis, shape, loc=loc_p, scale=scale_p)
                    ax.plot(x_axis, pdf_ln, color="0.12", lw=1.25, ls="--",
                            label="Lognormal")
                except Exception:
                    pass

            # Network mean as a vertical line
            ax.axvline(mu, color="0.25", lw=0.8, ls=":")

            # Shapiro-Wilk p-values
            try:
                _, p_norm = stats.shapiro(vals)
            except Exception:
                p_norm = np.nan
            try:
                if (vals > 0).all():
                    _, p_logn = stats.shapiro(np.log(vals))
                else:
                    p_logn = np.nan
            except Exception:
                p_logn = np.nan

            stats_str = (
                f"N*={len(vals)}; mean={mu:.1f}\n"
                f"SW pN={p_norm:.3f}; pLogN={p_logn:.3f}"
            )
            ax.text(0.03, 0.97, stats_str, transform=ax.transAxes,
                    fontsize=7.2, va="top", ha="left",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.75", lw=0.5, alpha=0.92))

            if col == 0:
                ax.set_ylabel(f"{city}\nDensity")
            if row == len(cities) - 1:
                ax.set_xlabel(r"Sensor daily mean PM$_{2.5}$ ($\mu$g/m$^3$)")
            natural_upper = ax.get_ylim()[1]
            ax.set_ylim(0, max(natural_upper * 1.12, 0.5))
            day_label = pd.to_datetime(day).strftime("%Y-%m-%d")
            ax.set_title(f"{label}\n{day_label}", fontsize=9.5, pad=5)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 0.015), fontsize=9)
    fig.subplots_adjust(left=0.07, right=0.985, bottom=0.12, top=0.94, wspace=0.20, hspace=0.50)
    save(fig, out_dir, "daily_distributions_representative_days")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure SI 14: period MdAPE with visible 95th-percentile and worst-case bands
# ---------------------------------------------------------------------------

def build_percentile_band_figure():
    print("Building Figure SI 14 (percentile bands)...")
    out_dir = os.path.join(OUT_ROOT, "Figure_SI_14")

    df = pd.read_csv(
        os.path.join(ROOT, "monte_carlo/plots/figure_data/period_best_worst_error_by_city_n.csv")
    )

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.5), sharey=False)

    for city in ["Lucknow", "Dhaka", "Chicago"]:
        sub = df[df["city"] == city].sort_values("sample_size")
        if sub.empty:
            continue
        color = CITY_COLORS[city]

        for ax, value_col_med, value_col_p95, value_col_max, ylabel in [
            (axes[0], "ape_median_pct", "ape_p95_pct", "worst_ape_pct",
             "Period APE (%)"),
            (axes[1], "absolute_error_median_ugm3", "absolute_error_p95_ugm3",
             "worst_absolute_error_ugm3", "Period absolute error ($\\mu$g/m$^3$)"),
        ]:
            n = sub["sample_size"].to_numpy()
            med = sub[value_col_med].to_numpy()
            p95 = sub[value_col_p95].to_numpy()
            worst = sub[value_col_max].to_numpy()

            # Shaded bands: median-P95 (dark) and P95-worst (light)
            ax.fill_between(n, med, p95, color=color, alpha=0.30,
                            label=f"{city}: median–P95")
            ax.fill_between(n, p95, worst, color=color, alpha=0.10,
                            label=f"{city}: P95–worst")
            ax.plot(n, med, color=color, lw=1.6, label=f"{city}: median")
            ax.plot(n, p95, color=color, lw=1.0, ls="--",
                    label=f"{city}: 95th percentile")
            ax.plot(n, worst, color=color, lw=0.6, ls=":",
                    label=f"{city}: worst (max)")

            ax.set_xlabel("Subnetwork size $n$")
            ax.set_ylabel(ylabel)
            ax.set_xlim(2, 30)
            ax.set_xticks([2, 5, 10, 20, 30])
            ax.get_xaxis().set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}"))
            ax.grid(True, axis="y", lw=0.35, alpha=0.5)

    # Custom legend per panel: only show one set per city (median + bands)
    for ax in axes:
        ax.set_ylim(bottom=0)
        # Threshold guides
        if ax is axes[0]:
            ax.axhline(10, color="0.6", lw=0.6, ls="-")
            ax.text(
                1.01,
                10,
                "10%",
                transform=ax.get_yaxis_transform(),
                ha="left",
                va="center",
                fontsize=7.5,
                color="#111827",
                clip_on=False,
            )
            ax.axhline(5, color="0.7", lw=0.5, ls="-")
            ax.text(
                1.01,
                5,
                "5%",
                transform=ax.get_yaxis_transform(),
                ha="left",
                va="center",
                fontsize=7.5,
                color="#111827",
                clip_on=False,
            )
            ax.set_ylim(0, 35)

    # Build a custom legend
    legend_handles = []
    for city, color in CITY_COLORS.items():
        legend_handles.append(Line2D([0], [0], color=color, lw=2.0, label=city))
    legend_handles.extend([
        Line2D([0], [0], color="0.2", lw=1.6, label="median (MdAPE)"),
        Line2D([0], [0], color="0.2", lw=1.0, ls="--", label="95th percentile"),
        Line2D([0], [0], color="0.2", lw=0.6, ls=":", label="worst-case (max)"),
        mpatches.Patch(color="0.4", alpha=0.30, label="median–P95 band"),
        mpatches.Patch(color="0.4", alpha=0.10, label="P95–worst band"),
    ])
    axes[1].legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(1.02, 1.0),
                   fontsize=7.5, frameon=False, borderaxespad=0)

    axes[0].set_title("(a) Relative error", pad=6)
    axes[1].set_title("(b) Absolute concentration error", pad=6)

    fig.suptitle(
        "Period subnetwork error — median, 95th percentile, and worst observed draw\n"
        "across $B=10{,}000$ SRSWOR Monte Carlo subnetworks",
        x=0.43, y=1.01, ha="center", fontsize=10,
    )
    plt.tight_layout(rect=[0, 0, 0.82, 1])
    save(fig, out_dir, "period_error_percentile_bands")
    plt.close(fig)


if __name__ == "__main__":
    ensure_dir(OUT_ROOT)
    build_schematic()
    build_daily_distributions()
    build_percentile_band_figure()
    print("Done.")
