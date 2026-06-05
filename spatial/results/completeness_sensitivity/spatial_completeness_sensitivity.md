# Spatial Completeness Sensitivity

## Scope

This sensitivity analysis asks whether stricter completeness handling changes the spatial-autocorrelation conclusions for Dhaka, Lucknow, and Chicago corrected LCS with Chicago collocation sensors excluded.

The daily analysis compares minimum valid-hour thresholds, sensor-level uptime filters, long-gap filters, and the data-driven daily-presence/gap rule identified in the missingness audit. The highest-resolution analysis uses the canonical aligned hourly matrices and only applies sensor-retention filters; daily valid-hour thresholds do not apply to hourly rows.

Permutation Moran's I uses 199 deterministic permutations per sampled time window with seed 20260536. Daily and hourly windows are deterministically thinned when needed for bounded runtime.

## Daily Scenario Summary

| city | scenario | sensors_retained | sensors_removed | time_windows_with_3plus_sensors | valid_sensor_count_median | reference_mae_filtered_vs_baseline_ugm3 | reference_bias_filtered_minus_baseline_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | baseline_ge_1h | 35 | 0 | 365 | 33.000 | 0.000 | 0.000 |
| Dhaka | daily_ge_18h | 35 | 0 | 365 | 30.000 | 1.097 | -0.283 |
| Dhaka | record_uptime_ge_75pct | 31 | 4 | 365 | 30.000 | 1.010 | -0.434 |
| Dhaka | daily_ge_18h_record_uptime_ge_75pct | 31 | 4 | 365 | 28.000 | 1.339 | -0.785 |
| Dhaka | drop_hourly_gap_gt_30d | 30 | 5 | 365 | 29.000 | 0.725 | 0.319 |
| Dhaka | daily_ge_50pct_gap_le_90d | 35 | 0 | 365 | 33.000 | 0.000 | 0.000 |
| Lucknow | baseline_ge_1h | 71 | 0 | 365 | 56.000 | 0.000 | 0.000 |
| Lucknow | daily_ge_18h | 71 | 0 | 365 | 50.000 | 1.080 | -0.624 |
| Lucknow | record_uptime_ge_75pct | 34 | 37 | 365 | 31.000 | 2.810 | -2.584 |
| Lucknow | daily_ge_18h_record_uptime_ge_75pct | 34 | 37 | 365 | 30.000 | 2.889 | -2.648 |
| Lucknow | drop_hourly_gap_gt_30d | 34 | 37 | 365 | 31.000 | 2.199 | -1.809 |
| Lucknow | daily_ge_50pct_gap_le_90d | 57 | 14 | 365 | 49.000 | 0.431 | -0.088 |
| Chicago | baseline_ge_1h | 277 | 0 | 243 | 272.000 | 0.000 | 0.000 |
| Chicago | daily_ge_18h | 277 | 0 | 242 | 270.000 | 0.013 | -0.010 |
| Chicago | record_uptime_ge_75pct | 269 | 8 | 243 | 268.000 | 0.011 | 0.006 |
| Chicago | daily_ge_18h_record_uptime_ge_75pct | 269 | 8 | 242 | 266.000 | 0.018 | -0.005 |
| Chicago | drop_hourly_gap_gt_30d | 267 | 10 | 243 | 266.000 | 0.010 | 0.003 |
| Chicago | daily_ge_50pct_gap_le_90d | 273 | 4 | 243 | 270.000 | 0.003 | -0.000 |

## Daily Moran Sensitivity

| city | scenario | weight_scheme | time_windows_tested | median_observed_morans_i | positive_sig_pct | two_sided_sig_pct | delta_positive_sig_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | baseline_ge_1h | band_5km | 240 | -0.004 | 18.333 | 10.833 | 0.000 |
| Dhaka | baseline_ge_1h | knn_5 | 240 | -0.040 | 3.750 | 3.750 | 0.000 |
| Dhaka | daily_ge_18h | band_5km | 240 | 0.003 | 22.083 | 14.583 | 3.750 |
| Dhaka | daily_ge_18h | knn_5 | 240 | -0.035 | 4.167 | 2.500 | 0.417 |
| Dhaka | record_uptime_ge_75pct | band_5km | 240 | 0.009 | 23.333 | 15.833 | 5.000 |
| Dhaka | record_uptime_ge_75pct | knn_5 | 240 | -0.014 | 6.250 | 2.917 | 2.500 |
| Dhaka | daily_ge_18h_record_uptime_ge_75pct | band_5km | 240 | 0.001 | 24.167 | 15.000 | 5.833 |
| Dhaka | daily_ge_18h_record_uptime_ge_75pct | knn_5 | 240 | -0.017 | 5.833 | 3.333 | 2.083 |
| Dhaka | drop_hourly_gap_gt_30d | band_5km | 240 | -0.004 | 18.333 | 10.833 | 0.000 |
| Dhaka | drop_hourly_gap_gt_30d | knn_5 | 240 | -0.019 | 6.250 | 3.333 | 2.500 |
| Dhaka | daily_ge_50pct_gap_le_90d | band_5km | 240 | -0.004 | 18.333 | 10.417 | 0.000 |
| Dhaka | daily_ge_50pct_gap_le_90d | knn_5 | 240 | -0.040 | 4.167 | 2.500 | 0.417 |
| Lucknow | baseline_ge_1h | band_5km | 240 | 0.004 | 11.667 | 6.667 | 0.000 |
| Lucknow | baseline_ge_1h | knn_5 | 240 | -0.019 | 5.833 | 4.167 | 0.000 |
| Lucknow | daily_ge_18h | band_5km | 240 | -0.020 | 6.667 | 5.000 | -5.000 |
| Lucknow | daily_ge_18h | knn_5 | 240 | -0.015 | 8.333 | 7.500 | 2.500 |
| Lucknow | record_uptime_ge_75pct | band_5km | 240 | -0.020 | 4.583 | 2.083 | -7.083 |
| Lucknow | record_uptime_ge_75pct | knn_5 | 240 | -0.010 | 8.333 | 6.667 | 2.500 |
| Lucknow | daily_ge_18h_record_uptime_ge_75pct | band_5km | 240 | -0.023 | 5.000 | 3.333 | -6.667 |
| Lucknow | daily_ge_18h_record_uptime_ge_75pct | knn_5 | 240 | -0.007 | 10.000 | 6.250 | 4.167 |
| Lucknow | drop_hourly_gap_gt_30d | band_5km | 240 | -0.007 | 10.417 | 4.583 | -1.250 |
| Lucknow | drop_hourly_gap_gt_30d | knn_5 | 240 | -0.024 | 9.583 | 5.000 | 3.750 |
| Lucknow | daily_ge_50pct_gap_le_90d | band_5km | 240 | -0.007 | 7.917 | 5.833 | -3.750 |
| Lucknow | daily_ge_50pct_gap_le_90d | knn_5 | 240 | -0.039 | 3.333 | 3.333 | -2.500 |
| Chicago | baseline_ge_1h | band_5km | 240 | 0.080 | 81.667 | 77.500 | 0.000 |
| Chicago | baseline_ge_1h | knn_5 | 240 | 0.116 | 74.583 | 69.583 | 0.000 |
| Chicago | daily_ge_18h | band_5km | 240 | 0.087 | 85.417 | 79.167 | 3.750 |
| Chicago | daily_ge_18h | knn_5 | 240 | 0.117 | 73.750 | 70.000 | -0.833 |
| Chicago | record_uptime_ge_75pct | band_5km | 240 | 0.077 | 80.417 | 76.250 | -1.250 |
| Chicago | record_uptime_ge_75pct | knn_5 | 240 | 0.115 | 75.000 | 68.333 | 0.417 |
| Chicago | daily_ge_18h_record_uptime_ge_75pct | band_5km | 240 | 0.088 | 83.333 | 79.167 | 1.667 |
| Chicago | daily_ge_18h_record_uptime_ge_75pct | knn_5 | 240 | 0.120 | 74.583 | 69.583 | 0.000 |
| Chicago | drop_hourly_gap_gt_30d | band_5km | 240 | 0.078 | 81.667 | 77.083 | 0.000 |
| Chicago | drop_hourly_gap_gt_30d | knn_5 | 240 | 0.117 | 73.333 | 68.333 | -1.250 |
| Chicago | daily_ge_50pct_gap_le_90d | band_5km | 240 | 0.079 | 80.833 | 78.333 | -0.833 |
| Chicago | daily_ge_50pct_gap_le_90d | knn_5 | 240 | 0.121 | 75.000 | 69.583 | 0.417 |

## Highest-Hourly Sensor-Retention Sensitivity

| city | scenario | time_windows_tested | median_observed_morans_i | positive_sig_pct | two_sided_sig_pct | delta_positive_sig_pct |
| --- | --- | --- | --- | --- | --- | --- |
| Dhaka | baseline_ge_1h | 120 | -0.019 | 13.333 | 8.333 | 0.000 |
| Dhaka | daily_ge_50pct_gap_le_90d | 120 | -0.019 | 15.000 | 9.167 | 1.667 |
| Dhaka | drop_hourly_gap_gt_30d | 120 | 0.003 | 15.000 | 12.500 | 1.667 |
| Dhaka | record_uptime_ge_75pct | 120 | -0.013 | 10.833 | 6.667 | -2.500 |
| Lucknow | baseline_ge_1h | 120 | 0.043 | 27.500 | 20.000 | 0.000 |
| Lucknow | daily_ge_50pct_gap_le_90d | 120 | 0.034 | 19.167 | 15.000 | -8.333 |
| Lucknow | drop_hourly_gap_gt_30d | 120 | 0.018 | 17.500 | 13.333 | -10.000 |
| Lucknow | record_uptime_ge_75pct | 120 | 0.029 | 20.000 | 11.667 | -7.500 |
| Chicago | baseline_ge_1h | 120 | 0.178 | 74.167 | 72.500 | 0.000 |
| Chicago | daily_ge_50pct_gap_le_90d | 120 | 0.183 | 76.667 | 72.500 | 2.500 |
| Chicago | drop_hourly_gap_gt_30d | 120 | 0.179 | 75.000 | 71.667 | 0.833 |
| Chicago | record_uptime_ge_75pct | 120 | 0.177 | 78.333 | 71.667 | 4.167 |

## Interpretation

- Daily valid-hour thresholds and sensor-retention filters do not create a strong daily positive Moran signal in Dhaka or Lucknow under kNN-5.
- Chicago remains spatially autocorrelated under all practical completeness filters, so the Chicago spatial signal is not an artifact of low-completeness sensor-days.
- Lucknow's data-driven 50% daily presence plus <=90 day gap filter mainly addresses missingness structure and reference-mean stability; it does not materially change the conclusion that daily spatial autocorrelation is weak/inconsistent.
- Any manuscript claim should say spatial autocorrelation was not consistently detectable in Dhaka/Lucknow at observed spacing and daily aggregation, while Chicago showed clearer positive spatial structure.

## Output Files

- `spatial_completeness_scenario_summary.csv`
- `spatial_completeness_morans_i_sensitivity.csv`
- `spatial_completeness_sensor_retention.csv`
- `spatial_completeness_sensitivity_metadata.json`
- `spatial/plots/completeness_sensitivity/daily_knn5_positive_morans_completeness_sensitivity.png` and `.pdf`
- `spatial/plots/completeness_sensitivity/daily_reference_mean_shift_completeness_sensitivity.png` and `.pdf`
- `spatial/plots/completeness_sensitivity/daily_valid_sensor_counts_completeness_sensitivity.png` and `.pdf`
