# Data-Driven Missingness Strategy

## Decision

Use city-specific missingness handling rather than a universal proportional rule. The diagnostics show that Lucknow has a real time-structured missingness problem, while Dhaka and Chicago do not benefit from the same proportional filters in a defensible way.

## Main Analysis Strategy

| city | recommended_role | rule_name | sensors_retained | sensors_removed | daily_missing_median_pct | missing_mean_improvement_pct_points | temporal_spearman_rho | spatial_cv_spearman_rho | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | main_no_filter | baseline_all_sensors | 35 | 0 | 11.310 | 0.000 | 0.014 | 0.039 | 0.000 |
| Lucknow | main_sensitivity_filter | daily_ge_50pct_gap_le_90d | 57 | 14 | 22.515 | 6.595 | 0.021 | 0.088 | 0.431 |
| Chicago | main_no_filter | baseline_all_sensors | 277 | 0 | 2.527 | 0.000 | 0.108 | 0.002 | 0.000 |

## Rationale

- **Dhaka:** Keep all sensors. The daily+gap rule removes no sensors, and proportional worst-sensor removal reduces missingness but worsens observed temporal/spatial association screens and shifts the reference mean.
- **Lucknow:** Use daily presence >=50% and longest gap <=90 days as the defensible low-distortion sensitivity. It sharply reduces temporal and spatial-CV missingness dependence while keeping reference-mean MAE below 0.5 µg/m³.
- **Chicago:** Keep all non-collocation corrected LCS sensors. Missingness is already low; proportional filtering makes missingness nearly constant and correlation screens unstable, with little substantive benefit.

## Optional Sensitivity Checks

| city | recommended_role | rule_name | sensors_retained | sensors_removed | daily_missing_median_pct | missing_mean_improvement_pct_points | temporal_spearman_rho | spatial_cv_spearman_rho | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Lucknow | stronger_cleanup_sensitivity | remove_worst_daily_missing_k15 | 56 | 15 | 21.652 | 7.897 | -0.007 | 0.042 | 0.537 |
| Chicago | long_gap_qaqc_sensitivity | daily_ge_50pct_gap_le_25pct_period | 269 | 8 | 0.743 | 1.491 | -0.217 | -0.089 | 0.009 |
| Dhaka | not_recommended_diagnostic_only | remove_worst_daily_missing_21pct | 28 | 7 | 8.482 | 2.943 | -0.164 | -0.063 | 0.806 |

## Interpretation

- Lucknow gets a real sensitivity filter because missingness structure is substantial and filterable.
- Dhaka stays unfiltered because baseline observed temporal/spatial missingness dependence is already weak, and proportional worst-sensor removal worsens the association screen while shifting the estimand.
- Chicago stays unfiltered for main analysis because missingness is already very low; removing sensors mostly makes correlation diagnostics unstable because missingness becomes nearly constant.

## Output Files

- `three_city_data_driven_missingness_strategy.csv`
- `three_city_data_driven_missingness_optional_sensitivities.csv`
- `three_city_data_driven_missingness_strategy.md`
