# Lucknow Temporal and Spatial Missingness Filter Search

## Scope

This searches multiple filtering strategies to see which rules reduce observed temporal missingness structure and missingness dependence on daily spatial variability. The search includes practical rules based on uptime/gap thresholds and diagnostic-targeted rules based on which sensors most contribute to temporal or spatial-CV missingness.

Targeted rules are useful for diagnosis, but they should not be the primary manuscript rule unless we explicitly describe them as post hoc sensitivity checks.

## Baseline MAR-Factor Screen

- Baseline temporal Spearman rho: 0.423.
- Baseline spatial-CV Spearman rho: 0.298.
- Baseline median daily missingness: 27.41%.

## Practical Best Rule

- Best non-targeted low-distortion joint rule: `remove_worst_daily_missing_k15`.
- It retains 56 sensors and has reference-mean MAE 0.54 µg/m³.
- Temporal rho changes from 0.423 to -0.007.
- Spatial-CV rho changes from 0.298 to 0.042.

## Strict Low-Distortion Practical Rule

- Best non-targeted rule with reference-mean MAE <= 0.5 µg/m³: `daily_ge_50pct_gap_le_90d`.
- It retains 57 sensors and has reference-mean MAE 0.43 µg/m³.
- Temporal rho changes from 0.423 to 0.021.
- Spatial-CV rho changes from 0.298 to 0.088.

## Diagnostic Targeted Best Rule

- Best targeted low-distortion joint rule: `remove_high_spatial_cv_missing_k15`.
- It retains 56 sensors and has reference-mean MAE 0.68 µg/m³.
- Temporal rho changes from 0.423 to -0.071.
- Spatial-CV rho changes from 0.298 to 0.013.

## Best Temporal Reductions: All Rules

| filter_name | filter_family | sensors_retained | daily_missing_median_pct | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | joint_temporal_spatial_cv_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| remove_sensor_temporal_rho_k7 | remove_sensor_temporal_rho | 64 | 28.385 | 0.002 | 0.420 | 0.114 | 0.184 | 0.605 | 0.247 |
| remove_temporal_and_spatial_rho_k5 | targeted_temporal_spatial_rho_union | 63 | 28.108 | 0.002 | 0.420 | 0.109 | 0.189 | 0.609 | 0.336 |
| max_gap_le_60d | max_gap_threshold | 53 | 21.698 | 0.003 | 0.420 | 0.113 | 0.185 | 0.605 | 0.795 |
| daily_ge_50pct_gap_le_60d | daily_presence_plus_gap | 52 | 20.673 | 0.005 | 0.418 | 0.100 | 0.198 | 0.616 | 0.927 |
| daily_ge_60pct_gap_le_60d | daily_presence_plus_gap | 52 | 20.673 | 0.005 | 0.418 | 0.100 | 0.198 | 0.616 | 0.927 |
| remove_worst_daily_missing_k15 | remove_worst_daily_missing | 56 | 21.652 | -0.007 | 0.416 | 0.042 | 0.256 | 0.671 | 0.537 |
| record_ge_60pct_gap_le_120d | record_presence_plus_gap | 53 | 18.868 | -0.011 | 0.411 | 0.025 | 0.273 | 0.685 | 1.046 |
| daily_ge_50pct_gap_le_90d | daily_presence_plus_gap | 57 | 22.515 | 0.021 | 0.402 | 0.088 | 0.211 | 0.612 | 0.431 |
| max_gap_le_90d | max_gap_threshold | 58 | 23.491 | 0.024 | 0.399 | 0.109 | 0.189 | 0.588 | 0.354 |
| record_ge_50pct_gap_le_60d | record_presence_plus_gap | 50 | 18.250 | 0.031 | 0.391 | 0.017 | 0.281 | 0.672 | 1.196 |

## Best Spatial-CV Reductions: All Rules

| filter_name | filter_family | sensors_retained | daily_missing_median_pct | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | joint_temporal_spatial_cv_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| remove_sensor_temporal_rho_k15 | remove_sensor_temporal_rho | 56 | 24.107 | -0.363 | 0.060 | -0.001 | 0.298 | 0.357 | 0.593 |
| remove_worst_daily_missing_k30 | remove_worst_daily_missing | 41 | 14.126 | -0.376 | 0.047 | -0.002 | 0.297 | 0.343 | 1.509 |
| remove_longest_gap_k35 | remove_longest_gap | 36 | 13.773 | -0.157 | 0.266 | 0.002 | 0.297 | 0.562 | 1.553 |
| record_ge_50pct_gap_le_90d | record_presence_plus_gap | 55 | 20.379 | 0.050 | 0.373 | 0.002 | 0.296 | 0.669 | 0.573 |
| daily_ge_75pct_gap_le_90d | daily_presence_plus_gap | 42 | 15.079 | -0.336 | 0.087 | 0.003 | 0.295 | 0.382 | 1.471 |
| daily_ge_75pct_gap_le_120d | daily_presence_plus_gap | 42 | 15.079 | -0.336 | 0.087 | 0.003 | 0.295 | 0.382 | 1.471 |
| daily_presence_ge_75pct | daily_presence_threshold | 42 | 15.079 | -0.336 | 0.087 | 0.003 | 0.295 | 0.382 | 1.471 |
| remove_late_period_missing_k15 | remove_late_period_missing | 56 | 24.182 | -0.293 | 0.130 | -0.006 | 0.292 | 0.422 | 0.364 |
| record_presence_ge_75pct | record_presence_threshold | 34 | 11.642 | -0.332 | 0.090 | 0.009 | 0.289 | 0.380 | 2.810 |
| record_ge_75pct_gap_le_120d | record_presence_plus_gap | 34 | 11.642 | -0.332 | 0.090 | 0.009 | 0.289 | 0.380 | 2.810 |

## Best Joint Reductions: Practical Non-Targeted Rules

| filter_name | filter_family | sensors_retained | daily_missing_median_pct | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | joint_temporal_spatial_cv_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| remove_worst_daily_missing_k15 | remove_worst_daily_missing | 56 | 21.652 | -0.007 | 0.416 | 0.042 | 0.256 | 0.671 | 0.537 |
| record_ge_50pct_gap_le_90d | record_presence_plus_gap | 55 | 20.379 | 0.050 | 0.373 | 0.002 | 0.296 | 0.669 | 0.573 |
| daily_ge_50pct_gap_le_60d | daily_presence_plus_gap | 52 | 20.673 | 0.005 | 0.418 | 0.100 | 0.198 | 0.616 | 0.927 |
| daily_ge_60pct_gap_le_60d | daily_presence_plus_gap | 52 | 20.673 | 0.005 | 0.418 | 0.100 | 0.198 | 0.616 | 0.927 |
| daily_ge_50pct_gap_le_90d | daily_presence_plus_gap | 57 | 22.515 | 0.021 | 0.402 | 0.088 | 0.211 | 0.612 | 0.431 |
| daily_ge_60pct_gap_le_90d | daily_presence_plus_gap | 56 | 22.247 | -0.064 | 0.358 | 0.051 | 0.247 | 0.606 | 0.450 |
| max_gap_le_60d | max_gap_threshold | 53 | 21.698 | 0.003 | 0.420 | 0.113 | 0.185 | 0.605 | 0.795 |
| max_gap_le_90d | max_gap_threshold | 58 | 23.491 | 0.024 | 0.399 | 0.109 | 0.189 | 0.588 | 0.354 |
| remove_longest_gap_k20 | remove_longest_gap | 51 | 20.997 | -0.083 | 0.340 | 0.080 | 0.218 | 0.558 | 0.793 |
| daily_presence_ge_70pct | daily_presence_threshold | 50 | 18.750 | -0.125 | 0.298 | -0.042 | 0.257 | 0.555 | 0.920 |

## Best Joint Reductions: Practical Rules With Reference MAE <= 0.5 µg/m³

| filter_name | filter_family | sensors_retained | daily_missing_median_pct | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | joint_temporal_spatial_cv_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| daily_ge_50pct_gap_le_90d | daily_presence_plus_gap | 57 | 22.515 | 0.021 | 0.402 | 0.088 | 0.211 | 0.612 | 0.431 |
| daily_ge_60pct_gap_le_90d | daily_presence_plus_gap | 56 | 22.247 | -0.064 | 0.358 | 0.051 | 0.247 | 0.606 | 0.450 |
| max_gap_le_90d | max_gap_threshold | 58 | 23.491 | 0.024 | 0.399 | 0.109 | 0.189 | 0.588 | 0.354 |
| remove_longest_gap_k15 | remove_longest_gap | 56 | 22.619 | 0.056 | 0.367 | 0.134 | 0.164 | 0.532 | 0.454 |
| remove_longest_gap_k10 | remove_longest_gap | 61 | 24.522 | 0.062 | 0.361 | 0.138 | 0.160 | 0.522 | 0.258 |
| remove_longest_gap_k12 | remove_longest_gap | 59 | 23.164 | 0.084 | 0.338 | 0.129 | 0.169 | 0.508 | 0.331 |
| remove_worst_daily_missing_k12 | remove_worst_daily_missing | 59 | 22.599 | 0.110 | 0.312 | 0.176 | 0.122 | 0.435 | 0.462 |
| remove_worst_daily_missing_k10 | remove_worst_daily_missing | 61 | 22.678 | 0.177 | 0.245 | 0.190 | 0.108 | 0.354 | 0.344 |
| record_ge_50pct_gap_le_120d | record_presence_plus_gap | 62 | 21.707 | 0.288 | 0.135 | 0.165 | 0.133 | 0.268 | 0.491 |
| daily_ge_60pct_gap_le_120d | daily_presence_plus_gap | 62 | 22.581 | 0.256 | 0.166 | 0.214 | 0.084 | 0.251 | 0.321 |

## Best Joint Reductions: Targeted Diagnostic Rules

| filter_name | filter_family | sensors_retained | daily_missing_median_pct | temporal_spearman_rho | temporal_abs_reduction | spatial_cv_spearman_rho | spatial_cv_abs_reduction | joint_temporal_spatial_cv_reduction | reference_mean_mae_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| remove_high_spatial_cv_missing_k15 | remove_high_spatial_cv_missing | 56 | 20.833 | -0.071 | 0.352 | 0.013 | 0.285 | 0.637 | 0.684 |
| remove_temporal_and_spatial_rho_k5 | targeted_temporal_spatial_rho_union | 63 | 28.108 | 0.002 | 0.420 | 0.109 | 0.189 | 0.609 | 0.336 |
| remove_high_spatial_cv_missing_k12 | remove_high_spatial_cv_missing | 59 | 21.540 | 0.065 | 0.357 | 0.049 | 0.249 | 0.606 | 0.544 |
| remove_sensor_temporal_rho_k7 | remove_sensor_temporal_rho | 64 | 28.385 | 0.002 | 0.420 | 0.114 | 0.184 | 0.605 | 0.247 |
| remove_temporal_and_spatial_rho_k7 | targeted_temporal_spatial_rho_union | 62 | 28.159 | -0.067 | 0.356 | 0.072 | 0.226 | 0.582 | 0.380 |
| remove_sensor_spatial_cv_rho_k10 | remove_sensor_spatial_cv_rho | 61 | 28.005 | -0.097 | 0.325 | 0.048 | 0.251 | 0.576 | 0.373 |
| remove_sensor_spatial_cv_rho_ge_20 | targeted_spatial_cv_rho_threshold | 60 | 28.056 | -0.114 | 0.309 | 0.052 | 0.246 | 0.555 | 0.447 |
| remove_late_and_high_cv_missing_k7 | targeted_late_high_cv_union | 59 | 21.963 | 0.080 | 0.343 | 0.109 | 0.189 | 0.532 | 0.481 |
| remove_sensor_spatial_cv_rho_k12 | remove_sensor_spatial_cv_rho | 59 | 28.390 | -0.154 | 0.268 | 0.046 | 0.252 | 0.521 | 0.807 |
| remove_sensor_spatial_cv_rho_k7 | remove_sensor_spatial_cv_rho | 64 | 28.190 | 0.072 | 0.351 | 0.135 | 0.164 | 0.514 | 0.336 |

## Output Files

- `lucknow_missingness_filter_search_all_results.csv`
- `lucknow_missingness_filter_search_top_temporal_all.csv`
- `lucknow_missingness_filter_search_top_spatial_cv_all.csv`
- `lucknow_missingness_filter_search_top_joint_all.csv`
- `lucknow_missingness_filter_search_top_joint_practical.csv`
- `lucknow_missingness_filter_search_top_joint_practical_ref_mae_le_0p5.csv`
- `lucknow_missingness_filter_search_top_targeted_joint_low_distortion.csv`
- `lucknow_missingness_filter_search.md`
