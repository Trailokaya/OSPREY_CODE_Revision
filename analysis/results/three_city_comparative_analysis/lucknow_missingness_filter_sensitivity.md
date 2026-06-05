# Lucknow Missingness Filter Sensitivity

## Scope

This compares Lucknow baseline data against three practical filtering rules: remove the five worst-uptime sensors, retain sensors with at least 50% hourly-record presence, and retain sensors with at least 50% daily presence. The 50% hourly-record rule is stricter for sensors that appear on many days but have partial-day coverage.

## Main Summary

| filter_name | sensors_retained | sensors_removed | record_missing_fraction_pct | daily_missing_fraction_median_pct | daily_missing_fraction_p90_pct | days_missing_ge_25pct | longest_daily_missing_ge_25pct_episode_days | baseline_minus_filtered_missing_mean_pct_points | baseline_minus_filtered_missing_mean_ci_low | baseline_minus_filtered_missing_mean_ci_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_all_sensors | 71 | 0 | 28.341 | 27.406 | 38.545 | 255 | 66 | 0.000 | 0.000 | 0.000 |
| remove_5_most_missing | 66 | 5 | 24.195 | 23.169 | 34.003 | 134 | 60 | 4.146 | 4.046 | 4.245 |
| record_presence_ge_50pct | 64 | 7 | 22.806 | 21.875 | 32.487 | 106 | 60 | 5.535 | 5.426 | 5.640 |
| daily_presence_ge_50pct | 66 | 5 | 24.242 | 23.422 | 33.889 | 140 | 60 | 4.099 | 4.007 | 4.190 |

## Practical Conclusion

- Baseline Lucknow median daily missingness is 27.41%, with 255 days at or above 25% missingness.
- The largest missingness gain comes from `record_presence_ge_50pct`: mean daily missingness improves by 5.53 percentage points, with bootstrap 95% CI [5.43, 5.64].
- The smallest reference-mean disruption comes from `daily_presence_ge_50pct`: MAE versus baseline is 0.22 µg/m³.
- A pragmatic default is `daily_presence_ge_50pct` if we want a low-distortion sensitivity case: it removes 5 sensors, improves mean missingness by 4.10 percentage points, and changes the daily reference mean by MAE 0.22 µg/m³.
- All non-baseline filters have bootstrap confidence intervals above zero for mean daily missingness improvement, so the improvement is statistically stable at the day level. The main limitation is that all filters still leave a long late-period high-missingness episode.

## Reference Mean Impact

| filter_name | reference_mean_bias_filtered_minus_baseline_ugm3 | reference_mean_mae_vs_baseline_ugm3 | reference_mean_p95_abs_diff_ugm3 | reference_mean_max_abs_diff_ugm3 | reference_mean_pearson_r |
| --- | --- | --- | --- | --- | --- |
| baseline_all_sensors | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| remove_5_most_missing | -0.488 | 0.549 | 2.394 | 6.947 | 1.000 |
| record_presence_ge_50pct | -0.346 | 0.508 | 1.940 | 5.614 | 1.000 |
| daily_presence_ge_50pct | -0.141 | 0.221 | 1.045 | 4.335 | 1.000 |

## Removed Sensors

| filter_name | sensor_id | station_name | record_uptime_pct | daily_presence_pct | longest_missing_gap_days | period_mean_pm25_ugm3 |
| --- | --- | --- | --- | --- | --- | --- |
| remove_5_most_missing | 81432147056 | Rajajipuram-II | 4.521 | 6.301 | 326 | 46.913 |
| remove_5_most_missing | 81432144016 | Lohiya college | 8.938 | 11.507 | 150 | 44.452 |
| remove_5_most_missing | 81432144008 | Chak Ganjaria | 14.247 | 16.986 | 173 | 33.346 |
| remove_5_most_missing | 81432147034 | Talkatora_BPS | 27.340 | 68.767 | 42 | 81.577 |
| remove_5_most_missing | 81432147039 | Nagram | 29.600 | 47.123 | 47 | 87.793 |
| record_presence_ge_50pct | 81432147034 | Talkatora_BPS | 27.340 | 68.767 | 42 | 81.577 |
| record_presence_ge_50pct | 81432147039 | Nagram | 29.600 | 47.123 | 47 | 87.793 |
| record_presence_ge_50pct | 81432147053 | Ambalika | 32.272 | 66.849 | 37 | 51.377 |
| record_presence_ge_50pct | 81432147056 | Rajajipuram-II | 4.521 | 6.301 | 326 | 46.913 |
| record_presence_ge_50pct | 81432144008 | Chak Ganjaria | 14.247 | 16.986 | 173 | 33.346 |
| record_presence_ge_50pct | 81432144016 | Lohiya college | 8.938 | 11.507 | 150 | 44.452 |
| record_presence_ge_50pct | 81432144024 | Umarbhari | 30.468 | 35.616 | 94 | 43.780 |
| daily_presence_ge_50pct | 81432147039 | Nagram | 29.600 | 47.123 | 47 | 87.793 |
| daily_presence_ge_50pct | 81432147056 | Rajajipuram-II | 4.521 | 6.301 | 326 | 46.913 |
| daily_presence_ge_50pct | 81432144008 | Chak Ganjaria | 14.247 | 16.986 | 173 | 33.346 |
| daily_presence_ge_50pct | 81432144016 | Lohiya college | 8.938 | 11.507 | 150 | 44.452 |
| daily_presence_ge_50pct | 81432144024 | Umarbhari | 30.468 | 35.616 | 94 | 43.780 |

## Strongest Remaining Missingness Correlations

| filter_name | x_variable | spearman_rho | pearson_r | n_days |
| --- | --- | --- | --- | --- |
| baseline_all_sensors | calendar_time | 0.423 | 0.491 | 365 |
| baseline_all_sensors | daily_spatial_cv | 0.298 | 0.189 | 365 |
| daily_presence_ge_50pct | calendar_time | 0.384 | 0.448 | 365 |
| daily_presence_ge_50pct | daily_spatial_cv | 0.260 | 0.180 | 365 |
| record_presence_ge_50pct | calendar_time | 0.419 | 0.493 | 365 |
| record_presence_ge_50pct | daily_spatial_cv | 0.220 | 0.178 | 365 |
| remove_5_most_missing | calendar_time | 0.399 | 0.479 | 365 |
| remove_5_most_missing | daily_spatial_cv | 0.246 | 0.193 | 365 |

## Observed MAR-Factor Change

These are observed-data association screens, not formal MAR tests. Lower absolute Spearman values mean missingness is less tied to the observed factor after filtering.

| filter_name | x_variable | baseline_spearman_rho | filtered_spearman_rho | abs_spearman_reduction | abs_spearman_reduction_pct |
| --- | --- | --- | --- | --- | --- |
| remove_5_most_missing | daily_mean_pm25 | 0.062 | 0.089 | -0.027 | -43.581 |
| remove_5_most_missing | daily_spatial_cv | 0.298 | 0.246 | 0.052 | 17.538 |
| remove_5_most_missing | calendar_time | 0.423 | 0.399 | 0.023 | 5.533 |
| record_presence_ge_50pct | daily_mean_pm25 | 0.062 | 0.067 | -0.006 | -9.000 |
| record_presence_ge_50pct | daily_spatial_cv | 0.298 | 0.220 | 0.078 | 26.096 |
| record_presence_ge_50pct | calendar_time | 0.423 | 0.419 | 0.004 | 0.966 |
| daily_presence_ge_50pct | daily_mean_pm25 | 0.062 | 0.053 | 0.008 | 13.668 |
| daily_presence_ge_50pct | daily_spatial_cv | 0.298 | 0.260 | 0.038 | 12.678 |
| daily_presence_ge_50pct | calendar_time | 0.423 | 0.384 | 0.039 | 9.120 |

## High-Missing Episodes After Filtering

| filter_name | start_date | end_date | duration_days | mean_missing_pct | max_missing_pct |
| --- | --- | --- | --- | --- | --- |
| baseline_all_sensors | 2023-01-25 | 2023-03-31 | 66 | 38.269 | 49.824 |
| baseline_all_sensors | 2022-10-14 | 2022-12-01 | 49 | 33.360 | 41.373 |
| baseline_all_sensors | 2022-04-01 | 2022-04-26 | 26 | 27.982 | 32.746 |
| daily_presence_ge_50pct | 2023-01-31 | 2023-03-31 | 60 | 35.113 | 46.023 |
| daily_presence_ge_50pct | 2022-10-19 | 2022-11-29 | 42 | 29.860 | 38.447 |
| daily_presence_ge_50pct | 2022-04-03 | 2022-04-08 | 6 | 26.368 | 27.399 |
| record_presence_ge_50pct | 2023-01-31 | 2023-03-31 | 60 | 34.167 | 45.247 |
| record_presence_ge_50pct | 2022-11-05 | 2022-11-28 | 24 | 29.820 | 33.073 |
| record_presence_ge_50pct | 2022-10-25 | 2022-11-01 | 8 | 29.077 | 36.523 |
| remove_5_most_missing | 2023-01-31 | 2023-03-31 | 60 | 35.760 | 46.907 |
| remove_5_most_missing | 2022-11-05 | 2022-11-29 | 25 | 31.169 | 35.101 |
| remove_5_most_missing | 2022-10-19 | 2022-11-01 | 14 | 28.702 | 36.932 |

## Interpretation

A filter meaningfully improves missingness if it lowers median and high-percentile daily missingness, shortens high-missing episodes, and does not materially shift the reference mean. These tables separate the data-completeness benefit from the estimand-change cost.

## Output Files

- `lucknow_missingness_filter_sensitivity_summary.csv`
- `lucknow_missingness_filter_removed_sensors.csv`
- `lucknow_missingness_filter_daily_metrics.csv`
- `lucknow_missingness_filter_correlations.csv`
- `lucknow_missingness_filter_mar_factor_delta.csv`
- `lucknow_missingness_filter_high_missing_episodes.csv`
- `lucknow_missingness_filter_sensitivity.md`
