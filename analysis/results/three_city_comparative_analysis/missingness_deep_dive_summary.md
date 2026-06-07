# Missingness Deep-Dive Summary

## Scope

This extends the missingness screen with multivariable controls, lag checks, high-missing episodes, sensor-gap episodes, hourly missingness profiles where hourly data exist, sensor-level missingness concentration, spatial clustering of missingness, and reference-mean sensitivity to stricter sensor inclusion.

These are diagnostics. They can identify likely data-quality structure, but they cannot prove a formal missing-data mechanism because unobserved values are unavailable when sensors are missing.

## Multivariable Daily Missingness Model

Coefficients are percentage-point changes in daily missingness per 1 SD increase in the predictor, controlling for the other listed predictors.

| city | predictor | coefficient_missing_pct_points_per_1sd | permutation_p_value | model_r_squared |
| --- | --- | --- | --- | --- |
| Chicago | calendar_time | 0.049 | 0.184 | 0.016 |
| Chicago | daily_mean_pm25 | -0.038 | 0.354 | 0.016 |
| Chicago | daily_spatial_cv | 0.027 | 0.492 | 0.016 |
| Dhaka | calendar_time | -2.590 | 0.003 | 0.072 |
| Dhaka | daily_spatial_cv | -0.937 | 0.156 | 0.072 |
| Dhaka | daily_mean_pm25 | -0.661 | 0.446 | 0.072 |
| Lucknow | calendar_time | 4.502 | 0.000 | 0.339 |
| Lucknow | daily_mean_pm25 | -2.476 | 0.000 | 0.339 |
| Lucknow | daily_spatial_cv | 0.519 | 0.179 | 0.339 |

## Peak Lag Associations

Lag convention: positive lag means the predictor is from earlier dates; negative lag means the predictor is from later dates.

| city | x_variable | lag_days | n_days | spearman_rho |
| --- | --- | --- | --- | --- |
| Chicago | daily_spatial_cv | -14 | 258 | -0.175 |
| Chicago | daily_spatial_sd | 12 | 260 | 0.172 |
| Chicago | daily_mean_pm25 | 12 | 260 | 0.154 |
| Dhaka | daily_spatial_sd | -8 | 357 | -0.200 |
| Dhaka | daily_mean_pm25 | -8 | 357 | -0.173 |
| Dhaka | daily_spatial_cv | -12 | 353 | -0.110 |
| Lucknow | daily_spatial_cv | -5 | 360 | 0.304 |
| Lucknow | daily_spatial_sd | 5 | 360 | 0.184 |
| Lucknow | daily_mean_pm25 | 11 | 354 | 0.113 |

## Network-Level High-Missing Episodes

Top episodes where daily network missingness is at least 25%.

| city | threshold_missing_pct | start_date | end_date | duration_days | mean_missing_pct | max_missing_pct |
| --- | --- | --- | --- | --- | --- | --- |
| Chicago | 25.000 | 2026-04-14 | 2026-04-14 | 1 | 100.000 | 100.000 |
| Dhaka | 25.000 | 2022-04-01 | 2022-04-21 | 21 | 57.681 | 61.786 |
| Dhaka | 25.000 | 2023-03-10 | 2023-03-12 | 3 | 25.873 | 26.190 |
| Dhaka | 25.000 | 2022-10-04 | 2022-10-04 | 1 | 35.000 | 35.000 |
| Lucknow | 25.000 | 2023-01-25 | 2023-03-31 | 66 | 38.269 | 49.824 |
| Lucknow | 25.000 | 2022-10-14 | 2022-12-01 | 49 | 33.360 | 41.373 |
| Lucknow | 25.000 | 2022-04-01 | 2022-04-26 | 26 | 27.982 | 32.746 |

## Longest Sensor Gap Episodes

| city | sensor_id | start_date | end_date | duration_days |
| --- | --- | --- | --- | --- |
| Chicago | DJJWX4142 | 2025-12-02 | 2026-05-31 | 181 |
| Chicago | DMAEX1156 | 2025-12-11 | 2026-05-31 | 172 |
| Chicago | DEYGE9157 | 2026-02-12 | 2026-05-31 | 109 |
| Chicago | DSSQU9498 | 2025-09-01 | 2025-12-13 | 104 |
| Chicago | DDVZB7943 | 2025-12-17 | 2026-03-06 | 80 |
| Chicago | DUVHI0112 | 2026-01-24 | 2026-04-10 | 77 |
| Dhaka | 81432151044 | 2023-02-14 | 2023-03-31 | 46 |
| Dhaka | 81432151044 | 2022-04-01 | 2022-05-08 | 38 |
| Dhaka | 81432151062 | 2022-04-01 | 2022-05-08 | 38 |
| Dhaka | 81432152006 | 2022-04-01 | 2022-05-08 | 38 |
| Dhaka | 81432151066 | 2022-08-10 | 2022-09-13 | 35 |
| Dhaka | 81432151048 | 2023-02-26 | 2023-03-31 | 34 |
| Lucknow | 81432147056 | 2022-05-10 | 2023-03-31 | 326 |
| Lucknow | 81432144008 | 2022-10-10 | 2023-03-31 | 173 |
| Lucknow | 81432147060 | 2022-10-21 | 2023-03-31 | 162 |
| Lucknow | 81432144016 | 2022-06-26 | 2022-11-22 | 150 |
| Lucknow | 81432131007 | 2022-11-13 | 2023-03-31 | 139 |
| Lucknow | 81432144016 | 2022-11-24 | 2023-03-31 | 128 |

## Hourly Missingness Profile

| city | lowest_missing_hour | lowest_hour_missing_pct | highest_missing_hour | highest_hour_missing_pct | hourly_range_pct_points |
| --- | --- | --- | --- | --- | --- |
| Chicago | 18 | 2.354 | 21 | 2.785 | 0.431 |
| Dhaka | 22 | 12.157 | 23 | 15.374 | 3.217 |
| Lucknow | 21 | 27.629 | 17 | 29.562 | 1.933 |

## Sensor Missingness Concentration

| city | sensor_count | top_10pct_sensors_missing_cell_share_pct | top_20pct_sensors_missing_cell_share_pct | sensors_below_75pct_uptime | sensors_below_50pct_uptime | sensors_with_gap_gt_30d | sensors_with_gap_gt_90d |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 35 | 26.725 | 40.955 | 4 | 0 | 5 | 0 |
| Lucknow | 71 | 29.884 | 45.405 | 37 | 7 | 37 | 13 |
| Chicago | 277 | 86.027 | 89.496 | 10 | 4 | 11 | 4 |

## Spatial Clustering Of Sensor Missingness

| city | metric | morans_i | permutation_p_two_sided | permutation_p_positive_clustering |
| --- | --- | --- | --- | --- |
| Dhaka | record_missing_pct | 0.201 | 0.015 | 0.009 |
| Dhaka | daily_missing_pct | -0.008 | 0.939 | 0.370 |
| Dhaka | longest_missing_gap_days | -0.079 | 0.407 | 0.705 |
| Lucknow | record_missing_pct | 0.008 | 0.909 | 0.345 |
| Lucknow | daily_missing_pct | 0.003 | 0.958 | 0.371 |
| Lucknow | longest_missing_gap_days | -0.060 | 0.347 | 0.763 |
| Chicago | record_missing_pct | 0.063 | 0.051 | 0.051 |
| Chicago | daily_missing_pct | 0.063 | 0.051 | 0.050 |
| Chicago | longest_missing_gap_days | 0.062 | 0.048 | 0.048 |

## Reference-Mean Sensitivity To Sensor Inclusion

| city | filter_name | sensors_retained | days_compared | bias_filtered_minus_baseline_ugm3 | mae_filtered_vs_baseline_ugm3 | max_abs_difference_ugm3 | pearson_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | record_uptime_ge_75pct | 31 | 365 | -0.434 | 1.010 | 13.336 | 0.999 |
| Dhaka | daily_uptime_ge_75pct_and_gap_le_30d | 29 | 365 | 0.083 | 0.700 | 9.507 | 1.000 |
| Dhaka | exclude_gap_gt_90d | 35 | 365 | 0.000 | 0.000 | 0.000 | 1.000 |
| Lucknow | record_uptime_ge_75pct | 34 | 365 | -2.584 | 2.810 | 31.472 | 0.998 |
| Lucknow | daily_uptime_ge_75pct_and_gap_le_30d | 32 | 365 | -1.605 | 2.142 | 15.858 | 0.999 |
| Lucknow | exclude_gap_gt_90d | 58 | 365 | 0.034 | 0.354 | 3.608 | 1.000 |
| Chicago | record_uptime_ge_75pct | 267 | 272 | 0.001 | 0.008 | 0.066 | 1.000 |
| Chicago | daily_uptime_ge_75pct_and_gap_le_30d | 264 | 272 | 0.000 | 0.011 | 0.063 | 1.000 |
| Chicago | exclude_gap_gt_90d | 273 | 272 | 0.003 | 0.006 | 0.031 | 1.000 |

## Output Files

- `missingness_deep_multivariable_daily_models.csv`
- `missingness_deep_lag_correlations.csv`
- `missingness_deep_peak_lag_summary.csv`
- `missingness_deep_network_episodes.csv`
- `missingness_deep_sensor_gap_episodes_top.csv`
- `missingness_deep_hourly_profile.csv`
- `missingness_deep_hourly_summary.csv`
- `missingness_deep_sensor_concentration.csv`
- `missingness_deep_sensor_spatial_moran.csv`
- `missingness_deep_reference_mean_sensitivity.csv`
- `missingness_deep_dive_summary.md`
