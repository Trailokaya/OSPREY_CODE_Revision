from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import OUTPUT_DPI, color_for_dataset, save_figure, setup_matplotlib  # noqa: E402


DEFAULT_DATA_ROOT = REPO_ROOT / "data"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "missingness" / "plots"
MEAN_COLOR = "#111827"
MEDIAN_COLOR = "#facc15"


DATASETS = [
    {
        "key": "dhaka_lcs",
        "label": "Dhaka LCS",
        "pm_file": "Dhaka_hourly_PM25.csv",
        "source_frequency": "hourly",
    },
    {
        "key": "lucknow_lcs",
        "label": "Lucknow LCS",
        "pm_file": "Lucknow_hourly_PM25.csv",
        "source_frequency": "hourly",
    },
    {
        "key": "chicago_lcs_corrected",
        "label": "Chicago LCS corrected",
        "pm_file": "Chicago_LCS_corrected_daily_PM25.csv",
        "source_frequency": "official_daily",
    },
]


def daily_sensor_matrix(data_root: Path, pm_file: str, source_frequency: str) -> pd.DataFrame:
    path = data_root / "pm" / pm_file
    frame = pd.read_csv(path, dtype={0: str})
    timestamp_column = frame.columns[0]
    values = frame.drop(columns=[timestamp_column]).apply(pd.to_numeric, errors="coerce")
    dates = pd.to_datetime(frame[timestamp_column].astype(str).str.slice(0, 10), errors="coerce")
    values = values.loc[dates.notna()].copy()
    dates = dates.loc[dates.notna()]
    if source_frequency == "hourly":
        daily = values.groupby(dates.dt.date).mean()
        daily.index = pd.to_datetime(daily.index)
        return daily.sort_index()
    daily = values.copy()
    daily.index = dates
    return daily.groupby(daily.index).mean().sort_index()


def plot_time_series(
    matrices: dict[str, pd.DataFrame],
    output_dir: Path,
    ylim: tuple[float, float],
    stem: str,
    title_suffix: str,
) -> None:
    setup_matplotlib()
    fig, axes = plt.subplots(len(DATASETS), 1, figsize=(9.2, 8.0), sharey=True)
    for ax, config in zip(axes, DATASETS, strict=True):
        key = config["key"]
        matrix = matrices[key]
        sensor_color = color_for_dataset(key)
        for sensor_id in matrix.columns:
            ax.plot(
                matrix.index,
                matrix[sensor_id],
                color=sensor_color,
                alpha=0.055,
                linewidth=0.35,
                zorder=1,
            )
        network_mean = matrix.mean(axis=1, skipna=True)
        network_median = matrix.median(axis=1, skipna=True)
        ax.plot(matrix.index, network_mean, color=MEAN_COLOR, linewidth=1.5, label="network mean", zorder=4)
        ax.plot(matrix.index, network_median, color=MEDIAN_COLOR, linewidth=1.4, label="network median", zorder=5)
        ax.set_title(config["label"], loc="left")
        ax.set_ylabel("Daily PM2.5 (µg/m³)")
        ax.set_ylim(*ylim)
        ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        ax.text(
            0.99,
            0.93,
            f"n={matrix.shape[1]} sensors/sites",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#d1d5db"},
        )
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.958), ncol=2)
    axes[-1].set_xlabel("Date")
    fig.suptitle(f"Daily sensor-level PM2.5 time series, shared y-scale{title_suffix}", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save_figure(fig, output_dir / stem, dpi=OUTPUT_DPI)


def write_summary(matrices: dict[str, pd.DataFrame], output_dir: Path, full_ylim: tuple[float, float], zoom_ylim: tuple[float, float]) -> None:
    records = []
    for config in DATASETS:
        key = config["key"]
        matrix = matrices[key]
        stacked = matrix.stack().dropna()
        records.append(
            {
                "dataset_key": key,
                "label": config["label"],
                "source_file": config["pm_file"],
                "source_frequency": config["source_frequency"],
                "days": int(matrix.shape[0]),
                "sensors": int(matrix.shape[1]),
                "sensor_day_count": int(stacked.shape[0]),
                "sensor_day_min_ugm3": float(stacked.min()),
                "sensor_day_p995_ugm3": float(stacked.quantile(0.995)),
                "sensor_day_max_ugm3": float(stacked.max()),
                "daily_mean_p99_ugm3": float(matrix.mean(axis=1, skipna=True).quantile(0.99)),
            }
        )
    summary = pd.DataFrame(records)
    summary["full_plot_ylim_min"] = full_ylim[0]
    summary["full_plot_ylim_max"] = full_ylim[1]
    summary["zoom_plot_ylim_min"] = zoom_ylim[0]
    summary["zoom_plot_ylim_max"] = zoom_ylim[1]
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_dir / "three_city_daily_pm25_timeseries_summary.csv", index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot all sensor-level daily PM2.5 time series for the three main cities.")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    matrices = {
        config["key"]: daily_sensor_matrix(args.data_root, config["pm_file"], config["source_frequency"])
        for config in DATASETS
    }
    all_values = pd.concat([matrix.stack().dropna() for matrix in matrices.values()], ignore_index=True)
    full_ylim = (0.0, float(all_values.max() * 1.02))
    zoom_ylim = (0.0, float(all_values.quantile(0.995) * 1.05))

    plot_time_series(
        matrices,
        args.output_dir,
        ylim=full_ylim,
        stem="PM25_three_city_daily_sensor_timeseries_common_full_scale",
        title_suffix="",
    )
    plot_time_series(
        matrices,
        args.output_dir,
        ylim=zoom_ylim,
        stem="PM25_three_city_daily_sensor_timeseries_common_p995_zoom",
        title_suffix=" (99.5th percentile zoom)",
    )
    write_summary(matrices, args.output_dir, full_ylim=full_ylim, zoom_ylim=zoom_ylim)
    print(f"Wrote three-city PM2.5 time-series plots to {args.output_dir}")


if __name__ == "__main__":
    main()
