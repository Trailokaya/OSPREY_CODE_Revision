# Three-City Proportional Missingness Rule Check

## Scope

This tests whether the Lucknow rules generalize proportionally to Dhaka and Chicago. Two proportional rules are emphasized: daily presence >=50% plus longest gap <=25% of the study period, and removing the worst 21.1% of sensors by daily missingness. Absolute Lucknow-style rules are included for context.

## Proportional Daily-Presence Plus Gap Rule

| city | rule_name | sensors_retained | daily_missing_median_pct | missing_mean_improvement_pct_points | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | baseline_all_sensors | 35 | 11.310 | 0.000 | 0.014 | 0.000 | 0.039 | 0.000 | 0.000 |
| Dhaka | daily_ge_50pct_gap_le_25pct_period | 35 | 11.310 | 0.000 | 0.014 | 0.000 | 0.039 | 0.000 | 0.000 |
| Lucknow | baseline_all_sensors | 71 | 27.406 | 0.000 | 0.423 | 0.000 | 0.298 | 0.000 | 0.000 |
| Lucknow | daily_ge_50pct_gap_le_25pct_period | 57 | 22.515 | 6.595 | 0.021 | 0.402 | 0.088 | 0.211 | 0.431 |
| Chicago | baseline_all_sensors | 277 | 2.527 | 0.000 | 0.108 | 0.000 | 0.002 | 0.000 | 0.000 |
| Chicago | daily_ge_50pct_gap_le_25pct_period | 269 | 0.743 | 1.491 | -0.217 | -0.109 | -0.089 | -0.087 | 0.009 |

## Proportional Worst-Daily-Missing Removal Rule

| city | rule_name | sensors_retained | daily_missing_median_pct | missing_mean_improvement_pct_points | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | baseline_all_sensors | 35 | 11.310 | 0.000 | 0.014 | 0.000 | 0.039 | 0.000 | 0.000 |
| Dhaka | remove_worst_daily_missing_21pct | 28 | 8.482 | 2.943 | -0.164 | -0.150 | -0.063 | -0.024 | 0.806 |
| Lucknow | baseline_all_sensors | 71 | 27.406 | 0.000 | 0.423 | 0.000 | 0.298 | 0.000 | 0.000 |
| Lucknow | remove_worst_daily_missing_21pct | 56 | 21.652 | 7.897 | -0.007 | 0.416 | 0.042 | 0.256 | 0.537 |
| Chicago | baseline_all_sensors | 277 | 2.527 | 0.000 | 0.108 | 0.000 | 0.002 | 0.000 | 0.000 |
| Chicago | remove_worst_daily_missing_21pct | 218 | 0.000 | 2.402 | 0.096 | 0.012 |  |  | 0.048 |

## All Rules

| city | rule_name | sensors_retained | daily_missing_median_pct | missing_mean_improvement_pct_points | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | baseline_all_sensors | 35 | 11.310 | 0.000 | 0.014 | 0.000 | 0.039 | 0.000 | 0.000 |
| Dhaka | daily_ge_50pct_gap_le_25pct_period | 35 | 11.310 | 0.000 | 0.014 | 0.000 | 0.039 | 0.000 | 0.000 |
| Dhaka | daily_ge_50pct_gap_le_90d_absolute | 35 | 11.310 | 0.000 | 0.014 | 0.000 | 0.039 | 0.000 | 0.000 |
| Dhaka | remove_worst_daily_missing_21pct | 28 | 8.482 | 2.943 | -0.164 | -0.150 | -0.063 | -0.024 | 0.806 |
| Dhaka | remove_worst_daily_missing_15_sensors | 20 | 6.667 | 4.708 | -0.079 | -0.065 | -0.051 | -0.012 | 1.687 |
| Lucknow | baseline_all_sensors | 71 | 27.406 | 0.000 | 0.423 | 0.000 | 0.298 | 0.000 | 0.000 |
| Lucknow | daily_ge_50pct_gap_le_25pct_period | 57 | 22.515 | 6.595 | 0.021 | 0.402 | 0.088 | 0.211 | 0.431 |
| Lucknow | daily_ge_50pct_gap_le_90d_absolute | 57 | 22.515 | 6.595 | 0.021 | 0.402 | 0.088 | 0.211 | 0.431 |
| Lucknow | remove_worst_daily_missing_21pct | 56 | 21.652 | 7.897 | -0.007 | 0.416 | 0.042 | 0.256 | 0.537 |
| Lucknow | remove_worst_daily_missing_15_sensors | 56 | 21.652 | 7.897 | -0.007 | 0.416 | 0.042 | 0.256 | 0.537 |
| Chicago | baseline_all_sensors | 277 | 2.527 | 0.000 | 0.108 | 0.000 | 0.002 | 0.000 | 0.000 |
| Chicago | daily_ge_50pct_gap_le_25pct_period | 269 | 0.743 | 1.491 | -0.217 | -0.109 | -0.089 | -0.087 | 0.009 |
| Chicago | daily_ge_50pct_gap_le_90d_absolute | 272 | 1.287 | 1.079 | -0.157 | -0.048 | -0.062 | -0.060 | 0.005 |
| Chicago | remove_worst_daily_missing_21pct | 218 | 0.000 | 2.402 | 0.096 | 0.012 |  |  | 0.048 |
| Chicago | remove_worst_daily_missing_15_sensors | 262 | 0.382 | 2.052 | -0.147 | -0.039 | -0.068 | -0.065 | 0.012 |

## Interpretation

- A rule generalizes well if it reduces temporal/spatial-CV missingness dependence without large reference-mean distortion.
- Dhaka and Chicago should not be expected to show the same gain as Lucknow if their baseline temporal/spatial-CV dependence is already weak.

## Output Files

- `three_city_proportional_missingness_rule_check.csv`
- `three_city_proportional_missingness_rule_check.md`
