from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = REPO_ROOT / "analysis/results/three_city_comparative_analysis"
OUTPUT_DIR = INPUT_DIR


def row_as_dict(frame: pd.DataFrame, **query: str) -> dict[str, Any]:
    subset = frame.copy()
    for column, value in query.items():
        subset = subset[subset[column] == value]
    if subset.empty:
        raise ValueError(f"No row found for {query}")
    return subset.iloc[0].to_dict()


def common_from_proportional(row: dict[str, Any], role: str, rationale: str) -> dict[str, Any]:
    return {
        "city": row["city"],
        "recommended_role": role,
        "rule_name": row["rule_name"],
        "rule_family": row["rule_family"],
        "rationale": rationale,
        "sensors_total": int(row["sensors_total"]),
        "sensors_retained": int(row["sensors_retained"]),
        "sensors_removed": int(row["sensors_removed"]),
        "daily_missing_median_pct": row["daily_missing_median_pct"],
        "daily_missing_p90_pct": row["daily_missing_p90_pct"],
        "days_missing_ge_25pct": int(row["days_missing_ge_25pct"]),
        "missing_mean_improvement_pct_points": row["missing_mean_improvement_pct_points"],
        "temporal_spearman_rho": row["temporal_spearman_rho"],
        "spatial_cv_spearman_rho": row["spatial_cv_spearman_rho"],
        "reference_mean_mae_ugm3": row["reference_mean_mae_ugm3"],
        "reference_mean_p95_abs_diff_ugm3": row["reference_mean_p95_abs_diff_ugm3"],
        "reference_mean_pearson_r": row["reference_mean_pearson_r"],
        "removed_sensor_ids": "" if pd.isna(row.get("removed_sensor_ids")) else row.get("removed_sensor_ids", ""),
    }


def common_from_lucknow(row: dict[str, Any], role: str, rationale: str) -> dict[str, Any]:
    return {
        "city": "Lucknow",
        "recommended_role": role,
        "rule_name": row["filter_name"],
        "rule_family": row["filter_family"],
        "rationale": rationale,
        "sensors_total": 71,
        "sensors_retained": int(row["sensors_retained"]),
        "sensors_removed": int(row["sensors_removed"]),
        "daily_missing_median_pct": row["daily_missing_median_pct"],
        "daily_missing_p90_pct": row["daily_missing_p90_pct"],
        "days_missing_ge_25pct": int(row["days_missing_ge_25pct"]),
        "missing_mean_improvement_pct_points": row["missing_mean_improvement_pct_points"],
        "temporal_spearman_rho": row["temporal_spearman_rho"],
        "spatial_cv_spearman_rho": row["spatial_cv_spearman_rho"],
        "reference_mean_mae_ugm3": row["reference_mean_mae_ugm3"],
        "reference_mean_p95_abs_diff_ugm3": row["reference_mean_p95_abs_diff_ugm3"],
        "reference_mean_pearson_r": row["reference_mean_pearson_r"],
        "removed_sensor_ids": "" if pd.isna(row.get("removed_sensor_ids")) else row.get("removed_sensor_ids", ""),
    }


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    display = frame[columns].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.to_numpy()]
    return "\n".join([header, separator, *rows])


def write_report(main_strategy: pd.DataFrame, optional_strategy: pd.DataFrame) -> None:
    lines = [
        "# Data-Driven Missingness Strategy",
        "",
        "## Decision",
        "",
        "Use city-specific missingness handling rather than a universal proportional rule. The diagnostics show that Lucknow has a real time-structured missingness problem, while Dhaka and Chicago do not benefit from the same proportional filters in a defensible way.",
        "",
        "## Main Analysis Strategy",
        "",
        markdown_table(
            main_strategy,
            [
                "city",
                "recommended_role",
                "rule_name",
                "sensors_retained",
                "sensors_removed",
                "daily_missing_median_pct",
                "missing_mean_improvement_pct_points",
                "temporal_spearman_rho",
                "spatial_cv_spearman_rho",
                "reference_mean_mae_ugm3",
            ],
        ),
        "",
        "## Rationale",
        "",
    ]
    for row in main_strategy.itertuples(index=False):
        lines.append(f"- **{row.city}:** {row.rationale}")
    lines.extend(
        [
            "",
            "## Optional Sensitivity Checks",
            "",
            markdown_table(
                optional_strategy,
                [
                    "city",
                    "recommended_role",
                    "rule_name",
                    "sensors_retained",
                    "sensors_removed",
                    "daily_missing_median_pct",
                    "missing_mean_improvement_pct_points",
                    "temporal_spearman_rho",
                    "spatial_cv_spearman_rho",
                    "reference_mean_mae_ugm3",
                ],
            ),
            "",
            "## Interpretation",
            "",
            "- Lucknow gets a real sensitivity filter because missingness structure is substantial and filterable.",
            "- Dhaka stays unfiltered because baseline observed temporal/spatial missingness dependence is already weak, and proportional worst-sensor removal worsens the association screen while shifting the estimand.",
            "- Chicago stays unfiltered for main analysis because missingness is already very low; removing sensors mostly makes correlation diagnostics unstable because missingness becomes nearly constant.",
            "",
            "## Output Files",
            "",
            "- `three_city_data_driven_missingness_strategy.csv`",
            "- `three_city_data_driven_missingness_optional_sensitivities.csv`",
            "- `three_city_data_driven_missingness_strategy.md`",
        ]
    )
    (OUTPUT_DIR / "three_city_data_driven_missingness_strategy.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    proportional = pd.read_csv(INPUT_DIR / "three_city_proportional_missingness_rule_check.csv")
    lucknow_search = pd.read_csv(INPUT_DIR / "lucknow_missingness_filter_search_all_results.csv")

    main_rows = [
        common_from_proportional(
            row_as_dict(proportional, city="Dhaka", rule_name="baseline_all_sensors"),
            role="main_no_filter",
            rationale=(
                "Keep all sensors. The daily+gap rule removes no sensors, and proportional worst-sensor removal "
                "reduces missingness but worsens observed temporal/spatial association screens and shifts the reference mean."
            ),
        ),
        common_from_lucknow(
            row_as_dict(lucknow_search, filter_name="daily_ge_50pct_gap_le_90d"),
            role="main_sensitivity_filter",
            rationale=(
                "Use daily presence >=50% and longest gap <=90 days as the defensible low-distortion sensitivity. "
                "It sharply reduces temporal and spatial-CV missingness dependence while keeping reference-mean MAE below 0.5 µg/m³."
            ),
        ),
        common_from_proportional(
            row_as_dict(proportional, city="Chicago", rule_name="baseline_all_sensors"),
            role="main_no_filter",
            rationale=(
                "Keep all non-collocation corrected LCS sensors. Missingness is already low; proportional filtering "
                "makes missingness nearly constant and correlation screens unstable, with little substantive benefit."
            ),
        ),
    ]
    optional_rows = [
        common_from_lucknow(
            row_as_dict(lucknow_search, filter_name="remove_worst_daily_missing_k15"),
            role="stronger_cleanup_sensitivity",
            rationale=(
                "Exploratory stronger Lucknow cleanup. It reduces temporal and spatial-CV dependence slightly more "
                "than the main sensitivity but has a larger reference-mean MAE."
            ),
        ),
        common_from_proportional(
            row_as_dict(proportional, city="Chicago", rule_name="daily_ge_50pct_gap_le_25pct_period"),
            role="long_gap_qaqc_sensitivity",
            rationale=(
                "Optional Chicago QA/QC check only. It removes a small number of long-gap sensors and barely changes "
                "the mean, but it should not be treated as improving MAR diagnostics."
            ),
        ),
        common_from_proportional(
            row_as_dict(proportional, city="Dhaka", rule_name="remove_worst_daily_missing_21pct"),
            role="not_recommended_diagnostic_only",
            rationale=(
                "Diagnostic only. It shows that proportional worst-sensor removal is not a good Dhaka rule because "
                "it introduces stronger temporal association and changes the reference mean."
            ),
        ),
    ]
    main_strategy = pd.DataFrame(main_rows)
    optional_strategy = pd.DataFrame(optional_rows)
    main_strategy.to_csv(OUTPUT_DIR / "three_city_data_driven_missingness_strategy.csv", index=False)
    optional_strategy.to_csv(
        OUTPUT_DIR / "three_city_data_driven_missingness_optional_sensitivities.csv",
        index=False,
    )
    metadata = {
        "purpose": "City-specific missingness-handling recommendation based on observed diagnostics.",
        "source_files": [
            "three_city_proportional_missingness_rule_check.csv",
            "lucknow_missingness_filter_search_all_results.csv",
        ],
        "outputs": [
            "three_city_data_driven_missingness_strategy.csv",
            "three_city_data_driven_missingness_optional_sensitivities.csv",
            "three_city_data_driven_missingness_strategy.md",
        ],
        "note": "This is a data-driven sensitivity strategy, not proof of MCAR/MAR/MNAR.",
    }
    (OUTPUT_DIR / "three_city_data_driven_missingness_strategy_metadata.json").write_text(
        json.dumps(metadata, indent=2)
    )
    write_report(main_strategy, optional_strategy)
    print(f"Wrote data-driven missingness strategy to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(
        main_strategy[
            [
                "city",
                "recommended_role",
                "rule_name",
                "sensors_retained",
                "daily_missing_median_pct",
                "temporal_spearman_rho",
                "spatial_cv_spearman_rho",
                "reference_mean_mae_ugm3",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
