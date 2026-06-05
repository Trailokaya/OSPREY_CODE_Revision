from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis/src"))

from plot_style import (  # noqa: E402
    GRID_COLOR,
    REFERENCE_LINE_COLOR,
    color_for_dataset,
    save_figure,
    setup_matplotlib,
)


CANONICAL_KEY = "lucknow_lcs"
MADHWAL_KEY = "lucknow_madhwal_lcs"
LABELS = {
    CANONICAL_KEY: "Lucknow canonical",
    MADHWAL_KEY: "Lucknow Madhwal",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare canonical Lucknow and Madhwal-validation Monte Carlo outputs."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Monte Carlo run directory containing mc_summary/p0_baseline_summary.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "analysis/results/lucknow_madhwal_monte_carlo_comparison",
    )
    return parser.parse_args()


def load_summary(run_dir: Path) -> pd.DataFrame:
    summary_path = run_dir / "mc_summary/p0_baseline_summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    summary = pd.read_csv(summary_path)
    required = {CANONICAL_KEY, MADHWAL_KEY}
    available = set(summary["dataset_key"].unique())
    missing = required.difference(available)
    if missing:
        raise ValueError(f"Missing dataset(s) in summary: {sorted(missing)}")
    return summary


def build_period_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    period = summary[
        (summary["time_aggregation"] == "period")
        & summary["dataset_key"].isin([CANONICAL_KEY, MADHWAL_KEY])
    ].copy()
    keep = [
        "dataset_key",
        "sample_size",
        "n_sensors_available",
        "reference_mean_ugm3",
        "ape_median_pct",
        "ape_p95_pct",
        "absolute_error_median_ugm3",
        "absolute_error_p95_ugm3",
    ]
    period = period[keep].sort_values(["dataset_key", "sample_size"])
    wide = period.pivot(index="sample_size", columns="dataset_key")
    comparison = pd.DataFrame(index=wide.index)
    comparison["sample_size"] = wide.index
    for metric in [
        "reference_mean_ugm3",
        "ape_median_pct",
        "ape_p95_pct",
        "absolute_error_median_ugm3",
        "absolute_error_p95_ugm3",
    ]:
        comparison[f"canonical_{metric}"] = wide[(metric, CANONICAL_KEY)].to_numpy()
        comparison[f"madhwal_{metric}"] = wide[(metric, MADHWAL_KEY)].to_numpy()
        comparison[f"madhwal_minus_canonical_{metric}"] = (
            comparison[f"madhwal_{metric}"] - comparison[f"canonical_{metric}"]
        )
    comparison["canonical_n_sensors_available"] = wide[
        ("n_sensors_available", CANONICAL_KEY)
    ].to_numpy()
    comparison["madhwal_n_sensors_available"] = wide[
        ("n_sensors_available", MADHWAL_KEY)
    ].to_numpy()
    return comparison.reset_index(drop=True)


def build_daily_n10_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    daily = summary[
        (summary["time_aggregation"] == "daily")
        & (summary["sample_size"] == 10)
        & summary["dataset_key"].isin([CANONICAL_KEY, MADHWAL_KEY])
    ].copy()
    daily["date"] = pd.to_datetime(daily["time_index"])
    keep = [
        "dataset_key",
        "date",
        "n_sensors_available",
        "reference_mean_ugm3",
        "ape_median_pct",
        "ape_p95_pct",
        "absolute_error_median_ugm3",
        "absolute_error_p95_ugm3",
    ]
    return daily[keep].sort_values(["dataset_key", "date"])


def write_headline_summary(
    period_comparison: pd.DataFrame, daily_n10: pd.DataFrame, output_dir: Path
) -> pd.DataFrame:
    rows = []
    for dataset_key, group in daily_n10.groupby("dataset_key"):
        rows.append(
            {
                "dataset_key": dataset_key,
                "label": LABELS[dataset_key],
                "daily_evaluated_days": int(group["date"].nunique()),
                "daily_start": group["date"].min().date().isoformat(),
                "daily_end": group["date"].max().date().isoformat(),
                "daily_n10_median_mdape_pct": group["ape_median_pct"].median(),
                "daily_n10_p95_mdape_pct": group["ape_median_pct"].quantile(0.95),
                "daily_n10_median_absolute_error_ugm3": group[
                    "absolute_error_median_ugm3"
                ].median(),
                "period_reference_mean_ugm3": period_comparison[
                    f"{'canonical' if dataset_key == CANONICAL_KEY else 'madhwal'}_reference_mean_ugm3"
                ].iloc[0],
                "period_n10_mdape_pct": period_comparison.loc[
                    period_comparison["sample_size"] == 10,
                    f"{'canonical' if dataset_key == CANONICAL_KEY else 'madhwal'}_ape_median_pct",
                ].iloc[0],
                "period_n10_absolute_error_ugm3": period_comparison.loc[
                    period_comparison["sample_size"] == 10,
                    f"{'canonical' if dataset_key == CANONICAL_KEY else 'madhwal'}_absolute_error_median_ugm3",
                ].iloc[0],
            }
        )
    headline = pd.DataFrame(rows)
    headline.to_csv(output_dir / "lucknow_madhwal_mc_headline_summary.csv", index=False)
    return headline


def plot_period(period_comparison: pd.DataFrame, output_dir: Path) -> None:
    setup_matplotlib()
    plot_data = period_comparison[period_comparison["sample_size"] <= 30]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.1), sharex=True)
    metrics = [
        ("ape_median_pct", "MdAPE (%)"),
        ("absolute_error_median_ugm3", "Median absolute error (µg/m³)"),
    ]
    for ax, (metric, ylabel) in zip(axes, metrics, strict=True):
        ax.plot(
            plot_data["sample_size"],
            plot_data[f"canonical_{metric}"],
            color=color_for_dataset(CANONICAL_KEY),
            linewidth=1.8,
            label=LABELS[CANONICAL_KEY],
        )
        ax.plot(
            plot_data["sample_size"],
            plot_data[f"madhwal_{metric}"],
            color=color_for_dataset(MADHWAL_KEY),
            linewidth=1.8,
            linestyle="--",
            label=LABELS[MADHWAL_KEY],
        )
        ax.set_xlabel("Number of sampled sensors (n)")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
        ax.axhline(0, color=REFERENCE_LINE_COLOR, linewidth=0.7)
    axes[0].legend(loc="upper right", frameon=False)
    fig.suptitle("Lucknow canonical vs Madhwal validation: study-period Monte Carlo")
    save_figure(fig, output_dir / "lucknow_madhwal_vs_canonical_period_mc")


def plot_daily(daily_n10: pd.DataFrame, output_dir: Path) -> None:
    setup_matplotlib()
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 4.8), sharex=False)
    metrics = [
        ("ape_median_pct", "Daily MdAPE at n=10 (%)"),
        ("absolute_error_median_ugm3", "Daily median absolute error at n=10 (µg/m³)"),
    ]
    for ax, (metric, ylabel) in zip(axes, metrics, strict=True):
        for dataset_key, group in daily_n10.groupby("dataset_key", sort=False):
            ax.plot(
                group["date"],
                group[metric],
                color=color_for_dataset(dataset_key),
                linewidth=1.1,
                linestyle="--" if dataset_key == MADHWAL_KEY else "-",
                label=LABELS[dataset_key],
            )
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    axes[0].legend(loc="upper right", frameon=False)
    axes[-1].set_xlabel("Date")
    fig.suptitle("Lucknow canonical vs Madhwal validation: daily Monte Carlo")
    save_figure(fig, output_dir / "lucknow_madhwal_vs_canonical_daily_n10_mc")


def write_markdown(
    run_dir: Path,
    headline: pd.DataFrame,
    period_comparison: pd.DataFrame,
    output_dir: Path,
) -> None:
    canonical = headline[headline["dataset_key"] == CANONICAL_KEY].iloc[0]
    madhwal = headline[headline["dataset_key"] == MADHWAL_KEY].iloc[0]
    n10 = period_comparison[period_comparison["sample_size"] == 10].iloc[0]
    lines = [
        "# Lucknow Madhwal Monte Carlo Comparison",
        "",
        f"Source run: `{run_dir}`.",
        "",
        "## Scope",
        "",
        "- This compares the canonical manuscript Lucknow matrix with the Madhwal validation matrix after both were registered in the same Monte Carlo runner.",
        "- The two files are not identical study windows; compare this as a dataset-sensitivity check, not as a same-period replacement claim.",
        "- Both datasets use the same 71 canonical Lucknow sensor IDs and locations.",
        "",
        "## Headline",
        "",
        f"- Canonical Lucknow period reference mean: `{canonical.period_reference_mean_ugm3:.3f}` µg/m³.",
        f"- Madhwal period reference mean: `{madhwal.period_reference_mean_ugm3:.3f}` µg/m³.",
        f"- At `n=10`, canonical period MdAPE is `{canonical.period_n10_mdape_pct:.3f}%` and Madhwal period MdAPE is `{madhwal.period_n10_mdape_pct:.3f}%`.",
        f"- At `n=10`, canonical period median absolute error is `{canonical.period_n10_absolute_error_ugm3:.3f}` µg/m³ and Madhwal is `{madhwal.period_n10_absolute_error_ugm3:.3f}` µg/m³.",
        f"- The Madhwal-minus-canonical period MdAPE difference at `n=10` is `{n10.madhwal_minus_canonical_ape_median_pct:+.3f}` percentage points.",
        "",
        "## Daily Coverage",
        "",
        f"- Canonical daily MC evaluated `{canonical.daily_evaluated_days}` days from `{canonical.daily_start}` to `{canonical.daily_end}`.",
        f"- Madhwal daily MC evaluated `{madhwal.daily_evaluated_days}` days from `{madhwal.daily_start}` to `{madhwal.daily_end}`.",
        "",
        "## Outputs",
        "",
        "- `lucknow_madhwal_mc_headline_summary.csv`",
        "- `lucknow_madhwal_vs_canonical_period_mc_comparison.csv`",
        "- `lucknow_madhwal_vs_canonical_daily_n10_mc.csv`",
        "- `lucknow_madhwal_vs_canonical_period_mc.pdf/png`",
        "- `lucknow_madhwal_vs_canonical_daily_n10_mc.pdf/png`",
    ]
    (output_dir / "lucknow_madhwal_monte_carlo_comparison.md").write_text(
        "\n".join(lines) + "\n"
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = load_summary(args.run_dir)
    period_comparison = build_period_comparison(summary)
    daily_n10 = build_daily_n10_comparison(summary)
    period_comparison.to_csv(
        args.output_dir / "lucknow_madhwal_vs_canonical_period_mc_comparison.csv",
        index=False,
    )
    daily_n10.to_csv(
        args.output_dir / "lucknow_madhwal_vs_canonical_daily_n10_mc.csv",
        index=False,
    )
    headline = write_headline_summary(period_comparison, daily_n10, args.output_dir)
    plot_period(period_comparison, args.output_dir)
    plot_daily(daily_n10, args.output_dir)
    write_markdown(args.run_dir, headline, period_comparison, args.output_dir)
    print(f"Wrote Lucknow Madhwal Monte Carlo comparison to {args.output_dir}")


if __name__ == "__main__":
    main()
