from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import (  # noqa: E402
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    NSTAR_FILL_COLOR,
    OUTPUT_DPI,
    REFERENCE_LINE_COLOR,
    SAMPLE_SIZE_COLORS,
    color_for_dataset,
    save_figure as save_figure_pair,
    setup_matplotlib,
)


CANONICAL_RUN_ID = "p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602"
DEFAULT_RUN_DIR = (
    REPO_ROOT
    / "monte_carlo"
    / "results"
    / "runs"
    / CANONICAL_RUN_ID
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "monte_carlo" / "plots"
DEFAULT_SELECTED_SAMPLE_SIZES = (5, 10, 20)
NSTAR_OVERLAY_LOW = 0.78
NSTAR_OVERLAY_HIGH = 0.96

CITY_LABELS = {
    "dhaka_lcs": "Dhaka LCS",
    "lucknow_lcs": "Lucknow LCS",
    "chicago_lcs_corrected_no_collocation": "Chicago LCS",
}
CITY_ORDER = [
    "dhaka_lcs",
    "lucknow_lcs",
    "chicago_lcs_corrected_no_collocation",
]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def release_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return "<outside-repository>"


def load_summary(run_dir: Path) -> tuple[dict, pd.DataFrame]:
    metadata_path = run_dir / "config/run_metadata.json"
    summary_path = run_dir / "mc_summary/p0_baseline_summary.parquet"
    if not metadata_path.exists():
        raise SystemExit(f"Missing metadata: {metadata_path}")
    if not summary_path.exists():
        raise SystemExit(f"Missing Monte Carlo summary: {summary_path}")
    metadata = json.loads(metadata_path.read_text())
    summary = pd.read_parquet(summary_path)
    return metadata, summary


def label_for(dataset_key: str) -> str:
    return CITY_LABELS.get(dataset_key, dataset_key)


def save_figure(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    save_figure_pair(fig, output_dir / stem)


def period_panel(
    ax: plt.Axes,
    period: pd.DataFrame,
    metric_prefix: str,
    y_label: str,
    title: str,
    max_n: int | None,
) -> None:
    for dataset_key in CITY_ORDER:
        group = period[period["dataset_key"] == dataset_key].sort_values("sample_size")
        if max_n is not None:
            group = group[group["sample_size"] <= max_n]
        if group.empty:
            continue
        color = color_for_dataset(dataset_key)
        x = group["sample_size"].to_numpy()
        median = group[f"{metric_prefix}_median"].to_numpy()
        p95 = group[f"{metric_prefix}_p95"].to_numpy()
        ax.plot(x, median, color=color, lw=1.8, label=label_for(dataset_key))
        ax.plot(x, p95, color=color, lw=1.05, ls="--", alpha=0.85)
    ax.set_xlabel("Number of sampled sensors (n)")
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    if max_n is not None:
        ax.set_xlim(2, max_n)
    ax.axhline(5, color=REFERENCE_LINE_COLOR, lw=0.8, ls=":", zorder=0)


def add_period_legends(ax: plt.Axes) -> None:
    city_handles = [
        Line2D([0], [0], color=color_for_dataset(dataset_key), lw=2.0, label=label_for(dataset_key))
        for dataset_key in CITY_ORDER
    ]
    statistic_handles = [
        Line2D([0], [0], color="#111827", lw=2.0, label="Median"),
        Line2D([0], [0], color="#111827", lw=1.2, ls="--", label="95th percentile"),
    ]
    legend_handles = [*city_handles, *statistic_handles]
    ax.legend(handles=legend_handles, frameon=False, loc="upper right", ncol=1, fontsize=8)


def prepare_period(summary: pd.DataFrame) -> pd.DataFrame:
    period = summary[summary["time_aggregation"] == "period"].copy()
    period = period.rename(
        columns={
            "ape_median_pct": "ape_median",
            "ape_p25_pct": "ape_p25",
            "ape_p75_pct": "ape_p75",
            "ape_p95_pct": "ape_p95",
            "absolute_error_median_ugm3": "absolute_median",
            "absolute_error_p25_ugm3": "absolute_p25",
            "absolute_error_p75_ugm3": "absolute_p75",
            "absolute_error_p95_ugm3": "absolute_p95",
        }
    )
    return period


def reference_text(period: pd.DataFrame) -> str:
    pieces: list[str] = []
    for dataset_key in CITY_ORDER:
        group = period[period["dataset_key"] == dataset_key]
        if group.empty:
            continue
        reference = group["reference_mean_ugm3"].iloc[0]
        label = "Chicago 9-month" if dataset_key.startswith("chicago") else label_for(dataset_key)
        pieces.append(f"{label}: {reference:.1f} µg/m³")
    return "Reference means\n" + "\n".join(pieces)


def add_reference_box(ax: plt.Axes, period: pd.DataFrame) -> None:
    ax.text(
        0.98,
        0.98,
        reference_text(period),
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": REFERENCE_LINE_COLOR},
    )


def plot_single_period_figure(
    period: pd.DataFrame,
    output_dir: Path,
    metric_prefix: str,
    y_label: str,
    title: str,
    stem: str,
    max_n: int | None,
) -> None:
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    period_panel(
        ax,
        period,
        metric_prefix=metric_prefix,
        y_label=y_label,
        title="" if max_n is not None else title,
        max_n=max_n,
    )
    if max_n is None:
        add_reference_box(ax, period)
    add_period_legends(ax)
    fig.tight_layout()
    save_figure(fig, output_dir, stem)


def plot_period_figures(period: pd.DataFrame, output_dir: Path) -> None:
    plot_single_period_figure(
        period,
        output_dir,
        metric_prefix="ape",
        y_label="MdAPE (%)",
        title="Period Mean MdAPE vs. Sample Size",
        stem="F2A_period_mdape_common_n2_30",
        max_n=30,
    )
    plot_single_period_figure(
        period,
        output_dir,
        metric_prefix="absolute",
        y_label="Absolute error (µg/m³)",
        title="Period Mean Absolute Error vs. Sample Size",
        stem="F2B_period_absolute_error_common_n2_30",
        max_n=30,
    )

    plot_single_period_figure(
        period,
        output_dir,
        metric_prefix="ape",
        y_label="Absolute percentage error (%)",
        title="SI. Period Mean Error vs. Sample Size, Full n Range",
        stem="SI_period_relative_error_full_range",
        max_n=None,
    )
    plot_single_period_figure(
        period,
        output_dir,
        metric_prefix="absolute",
        y_label="Absolute error (µg/m³)",
        title="SI. Period Mean Absolute Error, Full n Range",
        stem="SI_period_absolute_error_full_range",
        max_n=None,
    )


def prepare_daily(summary: pd.DataFrame, selected_sample_sizes: tuple[int, ...]) -> pd.DataFrame:
    daily = summary[
        (summary["time_aggregation"] == "daily")
        & (summary["sample_size"].isin(selected_sample_sizes))
    ].copy()
    daily["date"] = pd.to_datetime(daily["time_index"], errors="coerce")
    daily = daily.dropna(subset=["date"])
    return daily.sort_values(["dataset_key", "sample_size", "date"])


def daily_nstar(summary: pd.DataFrame) -> pd.DataFrame:
    daily = summary[summary["time_aggregation"] == "daily"].copy()
    nstar = (
        daily.groupby(["dataset_key", "time_index"], as_index=False)
        .agg(n_star=("n_sensors_available", "max"))
        .sort_values(["dataset_key", "time_index"])
    )
    nstar["date"] = pd.to_datetime(nstar["time_index"], errors="coerce")
    return nstar.dropna(subset=["date"])


def rescale_nstar_for_overlay(
    values: pd.Series | np.ndarray,
    band_low: float,
    band_high: float,
) -> tuple[np.ndarray, list[float], list[str]]:
    array = values.to_numpy(dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return array, [], []
    minimum = float(finite.min())
    maximum = float(finite.max())
    if np.isclose(minimum, maximum):
        midpoint = (band_low + band_high) / 2
        return np.full_like(array, midpoint, dtype=float), [midpoint], [f"{maximum:.0f}"]
    scaled = band_low + (array - minimum) / (maximum - minimum) * (band_high - band_low)
    tick_values = np.array([minimum, maximum], dtype=float)
    tick_positions = band_low + (tick_values - minimum) / (maximum - minimum) * (band_high - band_low)
    tick_labels = [f"{value:.0f}" for value in tick_values]
    return scaled, tick_positions.tolist(), tick_labels


def nstar_overlay_band(dataset_key: str, y_upper: float, relative_scale: bool) -> tuple[float, float]:
    if relative_scale:
        return (6.0, 10.0) if "chicago" in dataset_key else (15.0, 25.0)
    return (NSTAR_OVERLAY_LOW * y_upper, NSTAR_OVERLAY_HIGH * y_upper)


def mark_high_error_days(
    ax: plt.Axes,
    city_daily: pd.DataFrame,
    metric_column: str,
    selected_n: int = 10,
) -> None:
    selected = city_daily[city_daily["sample_size"] == selected_n].copy()
    if selected.empty:
        return
    threshold = selected[metric_column].quantile(0.95)
    flagged = selected[selected[metric_column] >= threshold]
    ax.scatter(
        flagged["date"],
        flagged[metric_column],
        s=14,
        facecolors="none",
        edgecolors="#111827",
        linewidths=0.8,
        label=f"≥95th percentile, n={selected_n}",
        zorder=4,
    )


def plot_daily_metric(
    daily: pd.DataFrame,
    nstar: pd.DataFrame,
    output_dir: Path,
    metric_column: str,
    y_label: str,
    title: str,
    stem: str,
    relative_scale: bool,
) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(8.4, 8.2), sharey=False)
    global_y_max = float(daily[metric_column].max() * 1.05)
    global_y_max = max(1.0, np.ceil(global_y_max))

    for ax, dataset_key in zip(axes, CITY_ORDER, strict=True):
        city_daily = daily[daily["dataset_key"] == dataset_key]
        city_nstar = nstar[nstar["dataset_key"] == dataset_key]

        for sample_size, group in city_daily.groupby("sample_size", sort=True):
            ax.plot(
                group["date"],
                group[metric_column],
                color=SAMPLE_SIZE_COLORS.get(int(sample_size), "#111827"),
                lw=1.15,
                label=f"n={int(sample_size)}",
            )
        mark_high_error_days(ax, city_daily, metric_column, selected_n=10)
        if relative_scale:
            for reference_line in [5, 10, 20]:
                ax.axhline(reference_line, color=REFERENCE_LINE_COLOR, lw=0.7, ls=":")
        ax.set_title(label_for(dataset_key), loc="left")
        ax.set_ylabel(y_label)
        if relative_scale:
            # Chicago's daily MdAPE is far smaller, so give it a tighter axis (0-10);
            # Dhaka/Lucknow use a common 0-25 axis.
            ax.set_ylim(0, 10.0 if "chicago" in dataset_key else 25.0)
        else:
            city_y_max = float(city_daily[metric_column].quantile(0.995) * 1.18)
            if not np.isfinite(city_y_max) or city_y_max <= 0:
                city_y_max = float(city_daily[metric_column].max() * 1.05)
            ax.set_ylim(0, max(0.5, np.ceil(city_y_max)))
        n_ax = ax.twinx()
        nstar_values = city_nstar["n_star"].to_numpy(dtype=float)
        n_ax.set_ylim(ax.get_ylim())
        n_ax.patch.set_visible(False)
        ax.set_zorder(1)
        n_ax.set_zorder(2)
        band_low, band_high = nstar_overlay_band(dataset_key, float(ax.get_ylim()[1]), relative_scale)
        scaled_nstar, tick_positions, tick_labels = rescale_nstar_for_overlay(
            city_nstar["n_star"],
            band_low=band_low,
            band_high=band_high,
        )
        n_ax.plot(
            city_nstar["date"].to_numpy(),
            scaled_nstar,
            color="#4b5563",
            alpha=0.98,
            linewidth=1.85,
            linestyle=(0, (4.5, 2.2)),
            zorder=20,
            label="N*(d): valid sensors per day",
        )
        n_ax.set_ylabel("N*(d)", color=MUTED_TEXT_COLOR)
        n_ax.tick_params(axis="y", colors=MUTED_TEXT_COLOR)
        n_ax.spines["top"].set_visible(False)
        n_ax.spines["right"].set_color(REFERENCE_LINE_COLOR)
        if tick_positions:
            n_ax.set_yticks(tick_positions, tick_labels)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    axes[-1].set_xlabel("Date")
    # Combined legend placed in the outer margin below the bottom (Chicago) panel.
    from matplotlib.lines import Line2D
    handles, labels = axes[0].get_legend_handles_labels()
    handles.append(Line2D([0], [0], color="#4b5563", lw=1.85, linestyle=(0, (4.5, 2.2))))
    labels.append("N*(d): valid sensors per day")
    fig.legend(handles, labels, loc="lower center", ncol=len(labels),
               frameon=False, bbox_to_anchor=(0.5, -0.01), fontsize=8)
    fig.suptitle(title, y=0.995)
    fig.tight_layout(rect=[0, 0.05, 1, 1])
    save_figure(fig, output_dir, stem)


def plot_daily_figures(
    daily: pd.DataFrame,
    nstar: pd.DataFrame,
    output_dir: Path,
) -> None:
    plot_daily_metric(
        daily=daily,
        nstar=nstar,
        output_dir=output_dir,
        metric_column="ape_median_pct",
        y_label="Daily MdAPE (%)",
        title="Daily Median Absolute Percentage Error",
        stem="F3_daily_mdape_timeseries_with_nstar",
        relative_scale=True,
    )
    plot_daily_metric(
        daily=daily,
        nstar=nstar,
        output_dir=output_dir,
        metric_column="absolute_error_median_ugm3",
        y_label="Daily median absolute error (µg/m³)",
        title="Daily Median Absolute Error",
        stem="NEW_G2_daily_absolute_error_timeseries_with_nstar",
        relative_scale=False,
    )


def write_figure_data(
    metadata: dict,
    period: pd.DataFrame,
    daily: pd.DataFrame,
    nstar: pd.DataFrame,
    run_dir: Path,
    output_dir: Path,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    period.to_csv(figure_data_dir / "period_error_curves.csv", index=False)
    daily.to_csv(figure_data_dir / "daily_error_timeseries_selected_n.csv", index=False)
    nstar.to_csv(figure_data_dir / "daily_nstar.csv", index=False)
    selected_period = period[period["sample_size"].between(2, 30)].rename(
        columns={
            "ape_min_pct": "best_ape_pct",
            "ape_median": "ape_median_pct",
            "ape_p95": "ape_p95_pct",
            "ape_max_pct": "worst_ape_pct",
            "absolute_error_min_ugm3": "best_absolute_error_ugm3",
            "absolute_median": "absolute_error_median_ugm3",
            "absolute_p95": "absolute_error_p95_ugm3",
            "absolute_error_max_ugm3": "worst_absolute_error_ugm3",
        }
    )
    selected_period[
        [
            "dataset_key",
            "city",
            "network",
            "sample_size",
            "n_sensors_available",
            "n_draws_completed",
            "reference_mean_ugm3",
            "best_ape_pct",
            "ape_median_pct",
            "ape_p95_pct",
            "worst_ape_pct",
            "best_absolute_error_ugm3",
            "absolute_error_median_ugm3",
            "absolute_error_p95_ugm3",
            "worst_absolute_error_ugm3",
        ]
    ].to_csv(figure_data_dir / "period_best_worst_error_by_city_n.csv", index=False)
    plot_metadata = {
        "source_run_id": metadata.get("run_id"),
        "source_run_dir": release_path(run_dir),
        "draws": metadata.get("draws"),
        "master_seed": metadata.get("master_seed"),
        "scenario": metadata.get("scenario"),
        "estimator": metadata.get("estimator"),
        "placement": metadata.get("placement"),
        "plot_style": {
            "module": "analysis/src/plot_style.py",
            "output_dpi": OUTPUT_DPI,
            "city_colors": "shared across maps, Monte Carlo, and missingness plots",
            "period_interval": "period panels show median and 95th percentile only; IQR is intentionally omitted",
            "daily_nstar": "right-axis N*(d) is a dashed dark-gray trace compressed into the upper band of each panel; right-axis tick labels give native valid-sensor counts",
        },
        "figures": [
            "F2A_period_mdape_common_n2_30.png",
            "F2B_period_absolute_error_common_n2_30.png",
            "SI_period_relative_error_full_range.png",
            "SI_period_absolute_error_full_range.png",
            "F3_daily_mdape_timeseries_with_nstar.png",
            "NEW_G2_daily_absolute_error_timeseries_with_nstar.png",
        ],
        "notes": [
            "Chicago period curve is a nine-month aggregate, not a 12-month annual mean.",
            "Daily plots mark n=10 days at or above the city-specific 95th percentile of the plotted error metric; mechanism labels are pending event classification.",
        ],
    }
    (figure_data_dir / "plot_metadata.json").write_text(json.dumps(plot_metadata, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build first manuscript-review Monte Carlo plots from a completed run."
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--selected-sample-sizes",
        default=",".join(str(value) for value in DEFAULT_SELECTED_SAMPLE_SIZES),
        help="Comma-separated daily sample sizes to plot.",
    )
    return parser


def parse_sample_sizes(value: str) -> tuple[int, ...]:
    sizes = tuple(sorted({int(item.strip()) for item in value.split(",") if item.strip()}))
    if not sizes:
        raise argparse.ArgumentTypeError("at least one sample size is required")
    return sizes


def main() -> None:
    args = build_parser().parse_args()
    run_dir = resolve_repo_path(args.run_dir)
    output_dir = resolve_repo_path(args.output_dir)
    selected_sample_sizes = parse_sample_sizes(args.selected_sample_sizes)
    setup_matplotlib()
    metadata, summary = load_summary(run_dir)
    period = prepare_period(summary)
    daily = prepare_daily(summary, selected_sample_sizes)
    nstar = daily_nstar(summary)
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_period_figures(period, output_dir)
    plot_daily_figures(daily, nstar, output_dir)
    write_figure_data(metadata, period, daily, nstar, run_dir, output_dir)
    print(f"Wrote Monte Carlo plots to {output_dir}")
    print(f"Source run: {run_dir}")
    print(f"Selected daily sample sizes: {selected_sample_sizes}")


if __name__ == "__main__":
    main()
