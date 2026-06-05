from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "scripts"))

from build_estimator_diagnostics import derive_seed, sha256_file  # noqa: E402
from plot_style import AQS_COLOR, GRID_COLOR, OUTPUT_DPI, save_figure, setup_matplotlib  # noqa: E402


OUTPUT_DIR = REPO_ROOT / "analysis/results/chicago_sensitivity"
PLOT_DIR = REPO_ROOT / "analysis/plots/chicago_sensitivity"
CANONICAL_RUN_DIR = (
    REPO_ROOT
    / "monte_carlo"
    / "results"
    / "runs"
    / "p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602"
)
DEFAULT_DRAWS = 10_000
MASTER_SEED = 20260522
SUBSET_CANDIDATES = (1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200)
SELECTED_DAILY_N = (5, 10, 20)
LCS_COLOR = "#9f1239"
RAW_COLOR = "#be123c"
COLLAPSED_COLOR = "#7c3aed"
ALL_COLOR = "#f97316"

CANONICAL_PERIOD_VARIANTS = {
    "chicago_aqs": "aqs",
    "chicago_lcs_corrected_all": "corrected_all",
    "chicago_lcs_corrected_no_collocation": "corrected_no_collocation",
    "chicago_lcs_raw_all": "raw_all",
    "chicago_lcs_raw_no_collocation": "raw_no_collocation",
}


def local_timestamps(series: pd.Series) -> pd.Series:
    timestamp_text = series.astype(str).str.replace(r"(?:Z|[+-]\d{2}:?\d{2})$", "", regex=True)
    return pd.to_datetime(timestamp_text, errors="coerce")


def read_daily_matrix(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    timestamp_column = frame.columns[0]
    timestamps = local_timestamps(frame[timestamp_column])
    values = frame.drop(columns=[timestamp_column]).apply(pd.to_numeric, errors="coerce")
    values = values.loc[timestamps.notna()].copy()
    values.index = timestamps.loc[timestamps.notna()].dt.strftime("%Y-%m-%d")
    values.index = pd.to_datetime(values.index)
    return values.groupby(values.index, sort=True).mean().sort_index()


def collocation_base(station_name: str) -> str:
    if "collocation" not in station_name.lower():
        return station_name
    return re.sub(r"\s+Collocation\s+\d+\s*$", " Collocation", station_name, flags=re.I)


def build_lcs_variants(values: pd.DataFrame, locations: pd.DataFrame, prefix: str) -> dict[str, pd.DataFrame]:
    locations = locations.copy()
    locations["Sensor_ID"] = locations["Sensor_ID"].astype(str)
    locations["Station_Name"] = locations["Station_Name"].astype(str)
    locations = locations[locations["Sensor_ID"].isin(values.columns)]
    collocated = locations["Station_Name"].str.contains("collocation", case=False, na=False)
    no_collocation_ids = locations.loc[~collocated, "Sensor_ID"].tolist()
    group_names = {
        row.Sensor_ID: collocation_base(str(row.Station_Name)) if is_collocated else str(row.Sensor_ID)
        for row, is_collocated in zip(locations.itertuples(index=False), collocated.to_numpy())
    }
    collapsed_columns: dict[str, list[str]] = {}
    for sensor_id, group_name in group_names.items():
        collapsed_columns.setdefault(group_name, []).append(sensor_id)
    collapsed = pd.concat(
        {
            group_name: values[sensor_ids].mean(axis=1, skipna=True)
            for group_name, sensor_ids in collapsed_columns.items()
        },
        axis=1,
    )
    return {
        f"{prefix}_all": values[locations["Sensor_ID"].tolist()].copy(),
        f"{prefix}_no_collocation": values[no_collocation_ids].copy(),
        f"{prefix}_collapsed": collapsed,
    }


def network_daily_summary(variants: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for variant, values in variants.items():
        valid_counts = values.notna().sum(axis=1)
        row = pd.DataFrame(
            {
                "variant": variant,
                "date": values.index.strftime("%Y-%m-%d"),
                "network_mean_ugm3": values.mean(axis=1, skipna=True),
                "network_median_ugm3": values.median(axis=1, skipna=True),
                "valid_sensor_count": valid_counts,
                "missing_fraction": 1.0 - valid_counts / max(values.shape[1], 1),
            }
        )
        rows.append(row)
    return pd.concat(rows, ignore_index=True)


def period_mdape(values: np.ndarray, sample_size: int, draws: int, seed: int) -> tuple[float, float, float]:
    values = values[np.isfinite(values)].astype(float)
    population_size = len(values)
    if population_size < sample_size or sample_size < 1:
        return np.nan, np.nan, np.nan
    reference = float(np.mean(values))
    if not np.isfinite(reference) or reference == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    keys = rng.random((draws, population_size), dtype=np.float64)
    indexes = np.argpartition(keys, sample_size - 1, axis=1)[:, :sample_size]
    estimates = values[indexes].mean(axis=1)
    absolute_error = np.abs(estimates - reference)
    ape = absolute_error / abs(reference) * 100.0
    return (
        float(np.nanmedian(ape)),
        float(np.nanmedian(absolute_error)),
        float(np.nanquantile(ape, 0.95)),
    )


def build_period_curves(variants: dict[str, pd.DataFrame], draws: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variant, values in variants.items():
        period_values = values.mean(axis=0, skipna=True).dropna().to_numpy(dtype=float)
        for sample_size in [n for n in SUBSET_CANDIDATES if n <= len(period_values)]:
            seed = derive_seed(MASTER_SEED, "chicago_sensitivity_period", variant, sample_size)
            mdape, med_abs, p95 = period_mdape(period_values, sample_size, draws, seed)
            rows.append(
                {
                    "variant": variant,
                    "sample_size": sample_size,
                    "n_sensors_available": int(len(period_values)),
                    "n_draws": draws,
                    "seed": seed,
                    "reference_mean_ugm3": float(np.mean(period_values)),
                    "ape_median_pct": mdape,
                    "ape_p95_pct": p95,
                    "absolute_error_median_ugm3": med_abs,
                }
            )
    return pd.DataFrame(rows).sort_values(["variant", "sample_size"])


def canonical_period_curves() -> pd.DataFrame:
    summary = pd.read_csv(CANONICAL_RUN_DIR / "mc_summary" / "p0_baseline_summary.csv")
    canonical = summary[
        (summary["time_aggregation"] == "period")
        & (summary["dataset_key"].isin(CANONICAL_PERIOD_VARIANTS))
        & (summary["sample_size"].isin(SUBSET_CANDIDATES))
    ].copy()
    canonical["variant"] = canonical["dataset_key"].map(CANONICAL_PERIOD_VARIANTS)
    canonical = canonical.rename(
        columns={
            "n_draws_completed": "n_draws",
            "seed_used": "seed",
        }
    )
    return canonical[
        [
            "variant",
            "sample_size",
            "n_sensors_available",
            "n_draws",
            "seed",
            "reference_mean_ugm3",
            "ape_median_pct",
            "ape_p95_pct",
            "absolute_error_median_ugm3",
        ]
    ]


def merge_canonical_period_curves(generated: pd.DataFrame) -> pd.DataFrame:
    canonical = canonical_period_curves()
    keys = ["variant", "sample_size"]
    generated_indexed = generated.set_index(keys)
    canonical_indexed = canonical.set_index(keys)
    merged = pd.concat(
        [generated_indexed.drop(index=canonical_indexed.index, errors="ignore"), canonical_indexed],
        axis=0,
    ).reset_index()
    return merged.sort_values(["variant", "sample_size"]).reset_index(drop=True)


def build_daily_selected_n(variants: dict[str, pd.DataFrame], draws: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variant, values in variants.items():
        daily_values_by_n: dict[int, dict[str, list[float]]] = {
            sample_size: {"ape": [], "abs": []} for sample_size in SELECTED_DAILY_N
        }
        evaluated_by_n = {sample_size: 0 for sample_size in SELECTED_DAILY_N}
        for date, row in values.iterrows():
            day_values = row.to_numpy(dtype=float)
            day_values = day_values[np.isfinite(day_values)]
            population_size = len(day_values)
            possible_n = [n for n in SELECTED_DAILY_N if n <= population_size]
            if not possible_n:
                continue
            reference = float(np.mean(day_values))
            if not np.isfinite(reference) or reference == 0:
                continue
            max_n = max(possible_n)
            seed = derive_seed(
                MASTER_SEED,
                "chicago_sensitivity_daily_selected_n",
                variant,
                str(date.date()),
            )
            rng = np.random.default_rng(seed)
            keys = rng.random((draws, population_size), dtype=np.float64)
            indexes = np.argpartition(keys, max_n - 1, axis=1)[:, :max_n]
            for sample_size in possible_n:
                estimates = day_values[indexes[:, :sample_size]].mean(axis=1)
                absolute_error = np.abs(estimates - reference)
                ape = absolute_error / abs(reference) * 100.0
                daily_values_by_n[sample_size]["ape"].append(float(np.nanmedian(ape)))
                daily_values_by_n[sample_size]["abs"].append(float(np.nanmedian(absolute_error)))
                evaluated_by_n[sample_size] += 1
        for sample_size in SELECTED_DAILY_N:
            day_apes = daily_values_by_n[sample_size]["ape"]
            day_abs = daily_values_by_n[sample_size]["abs"]
            rows.append(
                {
                    "variant": variant,
                    "sample_size": sample_size,
                    "days_evaluated": evaluated_by_n[sample_size],
                    "daily_median_mdape_pct": float(np.nanmedian(day_apes)) if day_apes else np.nan,
                    "daily_p95_mdape_pct": float(np.nanquantile(day_apes, 0.95)) if day_apes else np.nan,
                    "daily_median_absolute_error_ugm3": float(np.nanmedian(day_abs)) if day_abs else np.nan,
                }
            )
    return pd.DataFrame(rows).sort_values(["variant", "sample_size"])


def comparison_metrics(daily_summary: pd.DataFrame, reference_variant: str) -> pd.DataFrame:
    wide = daily_summary.pivot(index="date", columns="variant", values="network_mean_ugm3")
    rows: list[dict[str, Any]] = []
    reference = wide[reference_variant]
    for variant in wide.columns:
        if variant == reference_variant:
            continue
        joined = pd.concat([reference.rename("reference"), wide[variant].rename("variant")], axis=1)
        joined = joined.dropna()
        diff = joined["variant"] - joined["reference"]
        rows.append(
            {
                "reference_variant": reference_variant,
                "comparison_variant": variant,
                "days_compared": int(len(joined)),
                "reference_mean_ugm3": float(joined["reference"].mean()) if len(joined) else np.nan,
                "comparison_mean_ugm3": float(joined["variant"].mean()) if len(joined) else np.nan,
                "bias_comparison_minus_reference_ugm3": float(diff.mean()) if len(diff) else np.nan,
                "mae_ugm3": float(np.abs(diff).mean()) if len(diff) else np.nan,
                "rmse_ugm3": float(math.sqrt(np.mean(diff**2))) if len(diff) else np.nan,
                "pearson_r": float(joined["reference"].corr(joined["variant"]))
                if len(joined) > 1
                and joined["reference"].std(ddof=1) > 0
                and joined["variant"].std(ddof=1) > 0
                else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["reference_variant", "comparison_variant"])


def variant_inventory(variants: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for variant, values in variants.items():
        rows.append(
            {
                "variant": variant,
                "sensor_or_group_count": values.shape[1],
                "days": values.shape[0],
                "valid_day_count": int(values.mean(axis=1, skipna=True).notna().sum()),
                "mean_network_pm25_ugm3": float(values.mean(axis=1, skipna=True).mean()),
                "median_valid_sensor_count": float(values.notna().sum(axis=1).median()),
                "min_valid_sensor_count": int(values.notna().sum(axis=1).min()),
            }
        )
    return pd.DataFrame(rows).sort_values("variant")


def plot_daily_comparison(daily_summary: pd.DataFrame) -> None:
    setup_matplotlib()
    selected = {
        "corrected_no_collocation": LCS_COLOR,
        "raw_no_collocation": RAW_COLOR,
        "aqs": AQS_COLOR,
    }
    fig, axis = plt.subplots(figsize=(11, 4), constrained_layout=True)
    for variant, color in selected.items():
        frame = daily_summary[daily_summary["variant"] == variant].copy()
        axis.plot(
            pd.to_datetime(frame["date"]),
            frame["network_mean_ugm3"],
            color=color,
            lw=1.2,
            label=variant.replace("_", " "),
        )
    axis.set_ylabel("Network mean PM2.5 (µg/m³)")
    axis.set_xlabel("Date")
    axis.set_title("S03. Chicago daily network mean: corrected LCS, raw LCS, and AQS context")
    axis.grid(True, color=GRID_COLOR, lw=0.5)
    axis.legend(frameon=False, ncol=3, loc="upper right")
    save_figure(fig, PLOT_DIR / "S03_chicago_daily_mean_comparison", dpi=OUTPUT_DPI)


def plot_period_curves(period_curves: pd.DataFrame) -> None:
    setup_matplotlib()
    groups = [
        (
            "Raw vs corrected, collocations excluded",
            {
                "corrected_no_collocation": LCS_COLOR,
                "raw_no_collocation": RAW_COLOR,
            },
        ),
        (
            "Corrected LCS collocation handling",
            {
                "corrected_all": ALL_COLOR,
                "corrected_no_collocation": LCS_COLOR,
                "corrected_collapsed": COLLAPSED_COLOR,
            },
        ),
    ]
    y_max = float(
        np.nanmax(
            period_curves[
                period_curves["variant"].isin(
                    [
                        "corrected_no_collocation",
                        "raw_no_collocation",
                        "corrected_all",
                        "corrected_collapsed",
                    ]
                )
            ]["ape_median_pct"]
        )
    ) * 1.15
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True, constrained_layout=True)
    for axis, (title, variants) in zip(axes, groups):
        for variant, color in variants.items():
            frame = period_curves[period_curves["variant"] == variant].sort_values("sample_size")
            axis.plot(
                frame["sample_size"],
                frame["ape_median_pct"],
                color=color,
                lw=1.5,
                label=variant.replace("_", " "),
            )
        axis.set_title(title)
        axis.set_xlabel("Number of sensors")
        axis.set_ylim(0, y_max)
        axis.grid(True, color=GRID_COLOR, lw=0.5)
        axis.legend(frameon=False, fontsize=7)
    axes[0].set_ylabel("Study-period MdAPE (%)")
    fig.suptitle("S03/S04. Chicago sensitivity curves")
    save_figure(fig, PLOT_DIR / "S03_S04_chicago_sensitivity_period_curves", dpi=OUTPUT_DPI)


def table(frame: pd.DataFrame, columns: list[str], max_rows: int = 30) -> str:
    subset = frame[columns].head(max_rows).copy()
    if subset.empty:
        return "_No rows._"
    for column in subset.columns:
        subset[column] = subset[column].map(
            lambda value: f"{value:.3f}" if isinstance(value, (float, np.floating)) else str(value)
        )
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in subset.astype(str).to_numpy()]
    return "\n".join([header, sep, *rows])


def write_markdown(
    inventory: pd.DataFrame,
    metrics_main: pd.DataFrame,
    metrics_aqs: pd.DataFrame,
    period_curves: pd.DataFrame,
    daily_selected: pd.DataFrame,
    output_path: Path,
) -> None:
    period_n10 = period_curves[period_curves["sample_size"] == 10].sort_values("variant")
    daily_n10 = daily_selected[daily_selected["sample_size"] == 10].sort_values("variant")
    markdown = f"""# Chicago Raw/Corrected/AQS And Collocation Sensitivity

Generated by `analysis/scripts/build_chicago_sensitivity.py`.

## Scope

- Main Chicago finite population remains corrected LCS with collocation sensors excluded.
- Raw LCS is treated as a calibration sensitivity.
- AQS is treated as regulatory/reference context only, not as the main finite population.
- Collocation sensitivity compares corrected LCS using all sensors, collocation-excluded sensors, and collocation-site collapsed groups.

## Variant Inventory

{table(inventory, [
    "variant",
    "sensor_or_group_count",
    "days",
    "valid_day_count",
    "mean_network_pm25_ugm3",
    "median_valid_sensor_count",
    "min_valid_sensor_count",
])}

## Daily Network-Mean Comparisons Against Main Corrected No-Collocation LCS

{table(metrics_main, [
    "comparison_variant",
    "days_compared",
    "bias_comparison_minus_reference_ugm3",
    "mae_ugm3",
    "rmse_ugm3",
    "pearson_r",
])}

## Daily Network-Mean Comparisons Against AQS Context

{table(metrics_aqs, [
    "comparison_variant",
    "days_compared",
    "bias_comparison_minus_reference_ugm3",
    "mae_ugm3",
    "rmse_ugm3",
    "pearson_r",
])}

## Study-Period Monte Carlo At n=10

{table(period_n10, [
    "variant",
    "n_sensors_available",
    "reference_mean_ugm3",
    "ape_median_pct",
    "ape_p95_pct",
    "absolute_error_median_ugm3",
])}

## Daily Monte Carlo At n=10

{table(daily_n10, [
    "variant",
    "days_evaluated",
    "daily_median_mdape_pct",
    "daily_p95_mdape_pct",
    "daily_median_absolute_error_ugm3",
])}

## Interpretation

- Excluding or collapsing the nine collocated LCS changes the Chicago finite population only slightly because the network has hundreds of non-collocated sensors.
- Raw and corrected LCS should be compared in SI because correction affects concentration scale and therefore absolute-error interpretation.
- AQS agreement should be presented as context, not as a truth replacement for the LCS finite-population estimand.
- AQS `n=10` Monte Carlo rows are census-like when all ten AQS monitors are valid, so their zero-error values should not be interpreted as evidence that an AQS subnetwork outperforms the LCS network.

## Output Inventory

- `chicago_sensitivity_variant_inventory.csv`
- `chicago_sensitivity_daily_network_summary.csv`
- `chicago_sensitivity_network_comparison_metrics.csv`
- `chicago_sensitivity_aqs_comparison_metrics.csv`
- `chicago_sensitivity_period_curves.csv`
- `chicago_sensitivity_daily_selected_n.csv`
- `S03_chicago_daily_mean_comparison.*`
- `S03_S04_chicago_sensitivity_period_curves.*`
"""
    output_path.write_text(markdown)


def main() -> None:
    started = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    locations = pd.read_csv(REPO_ROOT / "data/locations/Chicago_LCS_corrected_sensor_locations.csv")
    corrected = read_daily_matrix(REPO_ROOT / "data/pm/Chicago_LCS_corrected_daily_PM25.csv")
    raw = read_daily_matrix(REPO_ROOT / "data/pm/Chicago_LCS_raw_daily_PM25.csv")
    aqs = read_daily_matrix(REPO_ROOT / "data/pm/Chicago_AQS_daily_PM25.csv")

    variants = {}
    variants.update(build_lcs_variants(corrected, locations, "corrected"))
    variants.update(build_lcs_variants(raw, locations, "raw"))
    variants["aqs"] = aqs

    inventory = variant_inventory(variants)
    daily_summary = network_daily_summary(variants)
    period_curves = merge_canonical_period_curves(build_period_curves(variants, DEFAULT_DRAWS))
    daily_selected = build_daily_selected_n(variants, DEFAULT_DRAWS)
    metrics_main = comparison_metrics(daily_summary, "corrected_no_collocation")
    metrics_aqs = comparison_metrics(daily_summary, "aqs")

    inventory.to_csv(OUTPUT_DIR / "chicago_sensitivity_variant_inventory.csv", index=False)
    daily_summary.to_csv(OUTPUT_DIR / "chicago_sensitivity_daily_network_summary.csv", index=False)
    metrics_main.to_csv(OUTPUT_DIR / "chicago_sensitivity_network_comparison_metrics.csv", index=False)
    metrics_aqs.to_csv(OUTPUT_DIR / "chicago_sensitivity_aqs_comparison_metrics.csv", index=False)
    period_curves.to_csv(OUTPUT_DIR / "chicago_sensitivity_period_curves.csv", index=False)
    daily_selected.to_csv(OUTPUT_DIR / "chicago_sensitivity_daily_selected_n.csv", index=False)

    plot_daily_comparison(daily_summary)
    plot_period_curves(period_curves)
    write_markdown(
        inventory,
        metrics_main,
        metrics_aqs,
        period_curves,
        daily_selected,
        OUTPUT_DIR / "chicago_sensitivity.md",
    )
    metadata = {
        "script": "analysis/scripts/build_chicago_sensitivity.py",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime_seconds": round(time.time() - started, 3),
        "draws": DEFAULT_DRAWS,
        "master_seed": MASTER_SEED,
        "canonical_period_source": str(CANONICAL_RUN_DIR.relative_to(REPO_ROOT)),
        "canonical_period_variants": CANONICAL_PERIOD_VARIANTS,
        "input_hashes": {
            "corrected_daily": sha256_file(REPO_ROOT / "data/pm/Chicago_LCS_corrected_daily_PM25.csv"),
            "raw_daily": sha256_file(REPO_ROOT / "data/pm/Chicago_LCS_raw_daily_PM25.csv"),
            "aqs_daily": sha256_file(REPO_ROOT / "data/pm/Chicago_AQS_daily_PM25.csv"),
            "lcs_locations": sha256_file(
                REPO_ROOT / "data/locations/Chicago_LCS_corrected_sensor_locations.csv"
            ),
        },
    }
    (OUTPUT_DIR / "chicago_sensitivity_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True)
    )
    print(f"Wrote Chicago sensitivity outputs to {OUTPUT_DIR}")
    print(f"Wrote Chicago sensitivity plots to {PLOT_DIR}")


if __name__ == "__main__":
    main()
