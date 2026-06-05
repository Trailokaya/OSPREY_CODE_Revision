# Assumption Stress Tests

Generated: 2026-05-28T13:29:04

## Purpose

This batch tests alternative assumptions that reviewers may ask about after the main analyses: reference-mean construction, approximate spatial weighting, leave-one-sensor influence, simple missing-data imputation, Monte Carlo seed stability, and exact enumeration where feasible.

## Reference Construction Alternatives

| city | estimand_variant | period_mean_pm25_ugm3 | delta_vs_primary_ugm3 | delta_vs_primary_pct | note |
| --- | --- | --- | --- | --- | --- |
| Dhaka | source_observation_weighted | 55.278 | 0.130 | 0.236 | Each valid sensor-time cell has equal weight |
| Dhaka | source_time_equal_network_mean | 54.030 | -1.117 | -2.025 | Each source timestamp has equal weight |
| Dhaka | sensor_equal_daily_period | 55.182 | 0.034 | 0.062 | Sensor-equal mean after daily aggregation |
| Dhaka | day_equal_daily_network_mean | 54.338 | -0.809 | -1.467 | Each daily network mean has equal weight |
| Dhaka | daily_observation_weighted | 55.191 | 0.044 | 0.079 | Each valid daily sensor-day has equal weight |
| Lucknow | source_observation_weighted | 61.877 | 0.074 | 0.120 | Each valid sensor-time cell has equal weight |
| Lucknow | source_time_equal_network_mean | 61.510 | -0.292 | -0.473 | Each source timestamp has equal weight |
| Lucknow | sensor_equal_daily_period | 60.818 | -0.984 | -1.592 | Sensor-equal mean after daily aggregation |
| Lucknow | day_equal_daily_network_mean | 62.047 | 0.245 | 0.396 | Each daily network mean has equal weight |
| Lucknow | daily_observation_weighted | 61.556 | -0.247 | -0.399 | Each valid daily sensor-day has equal weight |
| Chicago | source_observation_weighted | 10.564 | -0.001 | -0.007 | Each valid sensor-time cell has equal weight |
| Chicago | source_time_equal_network_mean | 10.561 | -0.003 | -0.032 | Each source timestamp has equal weight |
| Chicago | sensor_equal_daily_period | 10.565 | 0.000 | 0.000 | Sensor-equal mean after daily aggregation |
| Chicago | day_equal_daily_network_mean | 10.561 | -0.003 | -0.032 | Each daily network mean has equal weight |
| Chicago | daily_observation_weighted | 10.564 | -0.001 | -0.007 | Each valid daily sensor-day has equal weight |

## Daily Pooled-Observation Versus Two-Step Mean

| dataset_key | city | daily_comparison | daily_days_compared | daily_mean_diff_ugm3 | daily_median_diff_ugm3 | daily_mae_ugm3 | daily_p95_abs_diff_ugm3 | daily_max_abs_diff_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dhaka_lcs | Dhaka | pooled_valid_observations_minus_two_step_sensor_mean | 365 | -0.238 | -0.061 | 0.489 | 1.554 | 14.572 |
| lucknow_lcs | Lucknow | pooled_valid_observations_minus_two_step_sensor_mean | 365 | -0.436 | -0.110 | 0.698 | 2.185 | 19.829 |
| chicago_lcs_corrected_no_collocation | Chicago | pooled_valid_observations_minus_two_step_sensor_mean | 241 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Approximate Spatial Weighting Within Deployed Convex Hull

| city | sensor_count | grid_points_inside_hull | primary_equal_sensor_period_mean_ugm3 | approx_voronoi_weighted_period_mean_ugm3 | period_delta_weighted_minus_equal_ugm3 | period_delta_weighted_minus_equal_pct | effective_sensor_count_from_weights | daily_mae_ugm3 | daily_p95_abs_diff_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 35 | 15148 | 55.147 | 56.934 | 1.787 | 3.240 | 22.648 | 2.304 | 6.900 |
| Lucknow | 71 | 17041 | 61.802 | 63.174 | 1.372 | 2.219 | 31.014 | 3.981 | 9.814 |
| Chicago | 277 | 20665 | 10.565 | 10.550 | -0.015 | -0.142 | 180.642 | 0.056 | 0.149 |

## Leave-One-Sensor Influence

| dataset_key | city | sensors | max_period_abs_shift_ugm3 | median_period_abs_shift_ugm3 | max_daily_mae_ugm3 | median_daily_mae_ugm3 | max_daily_p95_abs_diff_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dhaka_lcs | Dhaka | 35 | 0.921 | 0.165 | 1.010 | 0.300 | 3.466 |
| lucknow_lcs | Lucknow | 71 | 0.757 | 0.157 | 0.647 | 0.135 | 1.832 |
| chicago_lcs_corrected_no_collocation | Chicago | 277 | 0.031 | 0.002 | 0.028 | 0.003 | 0.074 |

### Top Influential Sensors

| city | sensor_id | station_name | period_mean_pm25_ugm3 | period_abs_shift_when_removed_ugm3 | daily_mae_ugm3 | daily_p95_abs_diff_ugm3 |
| --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 81432151014 | 64. Satarkul | 86.452 | 0.921 | 0.849 | 2.787 |
| Dhaka | 81432151072 | 63. Khilkhet | 25.026 | 0.886 | 1.010 | 3.466 |
| Lucknow | 81432147065 | Balaganj | 114.788 | 0.757 | 0.402 | 1.332 |
| Dhaka | 81432130014 | 16. Narayangonj, Gognogor | 79.629 | 0.720 | 0.911 | 3.369 |
| Lucknow | 81432147045 | Qaiserbagh | 103.127 | 0.590 | 0.462 | 1.741 |
| Lucknow | 81432147039 | Nagram | 100.987 | 0.560 | 0.172 | 0.809 |
| Dhaka | 81432150006 | 31. Rupnogor high school, Pallabi | 36.829 | 0.539 | 0.398 | 1.416 |
| Lucknow | 81432147034 | Talkatora_BPS | 98.835 | 0.529 | 0.378 | 1.832 |
| Lucknow | 81432147060 | Shanti Nagar | 24.818 | 0.528 | 0.042 | 0.168 |
| Dhaka | 81432130017 | 8. Vasantek | 73.008 | 0.525 | 0.827 | 2.088 |
| Chicago | DWGYM0810 | Avalon Park 1 | 19.208 | 0.031 | 0.028 | 0.074 |
| Chicago | DMMAG3845 | Riverdale 3 | 5.021 | 0.020 | 0.021 | 0.051 |
| Chicago | DZLAV7766 | Austin 4 | 13.889 | 0.012 | 0.012 | 0.024 |
| Chicago | DGHRH9009 | Gage Park 1 | 7.448 | 0.011 | 0.012 | 0.034 |
| Chicago | DYWWS0378 | Uptown 4 | 7.679 | 0.010 | 0.010 | 0.037 |

## Imputation Alternatives

| city | imputation_variant | period_delta_variant_minus_baseline_ugm3 | period_delta_variant_minus_baseline_pct | daily_mae_ugm3 | daily_p95_abs_diff_ugm3 | note |
| --- | --- | --- | --- | --- | --- | --- |
| Dhaka | linear_time_interpolation | -0.550 | -0.997 | 1.490 | 6.464 | Per-sensor daily interpolation, both directions |
| Dhaka | sensor_period_mean_fill | 0.000 | 0.000 | 3.119 | 10.801 | Fill each missing sensor-day with that sensor period mean |
| Dhaka | sensor_month_mean_then_period_fill | -0.377 | -0.683 | 1.453 | 6.220 | Fill missing sensor-day with same-sensor month mean, fallback period mean |
| Lucknow | linear_time_interpolation | 2.003 | 3.293 | 5.478 | 19.999 | Per-sensor daily interpolation, both directions |
| Lucknow | sensor_period_mean_fill | 0.000 | 0.000 | 9.879 | 28.437 | Fill each missing sensor-day with that sensor period mean |
| Lucknow | sensor_month_mean_then_period_fill | -0.029 | -0.047 | 5.959 | 21.152 | Fill missing sensor-day with same-sensor month mean, fallback period mean |
| Chicago | linear_time_interpolation | 0.010 | 0.096 | 0.106 | 0.249 | Per-sensor daily interpolation, both directions |
| Chicago | sensor_period_mean_fill | 0.000 | 0.000 | 0.102 | 0.246 | Fill each missing sensor-day with that sensor period mean |
| Chicago | sensor_month_mean_then_period_fill | 0.009 | 0.087 | 0.099 | 0.239 | Fill missing sensor-day with same-sensor month mean, fallback period mean |

## Monte Carlo Seed Stability At 10,000 Draws

| city | sample_size | mdape_mean_pct | mdape_sd_pct | mdape_range_pct | q95_ape_range_pct | median_abs_error_range_ugm3 |
| --- | --- | --- | --- | --- | --- | --- |
| Chicago | 2 | 3.914 | 0.028 | 0.066 | 0.464 | 0.007 |
| Chicago | 5 | 2.643 | 0.027 | 0.071 | 0.155 | 0.007 |
| Chicago | 10 | 1.932 | 0.019 | 0.052 | 0.133 | 0.005 |
| Chicago | 20 | 1.434 | 0.014 | 0.035 | 0.141 | 0.004 |
| Chicago | 30 | 1.172 | 0.024 | 0.062 | 0.072 | 0.007 |
| Dhaka | 2 | 8.758 | 0.054 | 0.132 | 1.153 | 0.073 |
| Dhaka | 5 | 5.905 | 0.058 | 0.124 | 0.337 | 0.068 |
| Dhaka | 10 | 3.912 | 0.025 | 0.072 | 0.258 | 0.039 |
| Dhaka | 20 | 2.139 | 0.033 | 0.071 | 0.097 | 0.039 |
| Dhaka | 30 | 0.976 | 0.014 | 0.039 | 0.040 | 0.022 |
| Lucknow | 2 | 12.559 | 0.272 | 0.677 | 0.282 | 0.419 |
| Lucknow | 5 | 8.035 | 0.079 | 0.215 | 0.646 | 0.133 |
| Lucknow | 10 | 5.516 | 0.044 | 0.106 | 0.517 | 0.066 |
| Lucknow | 20 | 3.588 | 0.075 | 0.205 | 0.316 | 0.127 |
| Lucknow | 30 | 2.633 | 0.026 | 0.069 | 0.221 | 0.043 |

## Exact Enumeration Where Feasible

| city | sample_size | exact_combination_count | exact_mdape_pct | mc_10k_mdape_mean_pct | mc_minus_exact_mdape_pct_points | exact_q95_ape_pct | mc_minus_exact_q95_ape_pct_points |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 1 | 35 | 10.163 |  |  | 47.461 |  |
| Dhaka | 2 | 595 | 8.693 | 8.758 | 0.065 | 30.250 | -0.043 |
| Dhaka | 3 | 6545 | 7.420 |  |  | 23.371 |  |
| Dhaka | 4 | 52360 | 6.565 |  |  | 19.761 |  |
| Dhaka | 5 | 324632 | 5.875 | 5.905 | 0.030 | 17.264 | -0.005 |
| Dhaka | 30 | 324632 | 0.979 | 0.976 | -0.003 | 2.877 | -0.009 |
| Lucknow | 1 | 71 | 17.798 |  |  | 59.882 |  |
| Lucknow | 2 | 2485 | 12.562 | 12.559 | -0.003 | 38.527 | -0.135 |
| Lucknow | 3 | 57155 | 10.401 |  |  | 30.813 |  |
| Lucknow | 4 | 971635 | 9.047 |  |  | 26.333 |  |
| Chicago | 1 | 277 | 5.454 |  |  | 18.701 |  |
| Chicago | 2 | 38226 | 3.953 | 3.914 | -0.039 | 13.484 | -0.041 |

## Interpretation

- If reference-construction alternatives shift the period mean materially, the manuscript should emphasize that the primary target is a chosen finite-population estimand rather than a unique city truth.
- Approximate Voronoi weighting is not a replacement for a population-weighted exposure model; it is a stress test for unequal spatial support within the deployed convex hull.
- Leave-one-sensor influence identifies sensors that strongly affect the equal-sensor reference mean; it does not by itself justify exclusion.
- Simple imputation checks whether the no-imputation choice is driving the reference mean. If imputation shifts are small, the current all-available-data approach is easier to defend.
- Monte Carlo seed ranges at 10,000 draws quantify simulation noise. Exact enumeration rows show whether the Monte Carlo approximation is close where full enumeration is computationally feasible.

## Output Inventory

- `reference_construction_sensitivity.csv`
- `daily_reference_construction_sensitivity.csv`
- `spatial_weighting_sensitivity.csv`
- `spatial_weighting_daily_differences.csv`
- `spatial_weighting_sensor_weights.csv`
- `leave_one_sensor_influence.csv`
- `leave_one_city_summary.csv`
- `missingness_imputation_sensitivity.csv`
- `missingness_imputation_daily_differences.csv`
- `monte_carlo_stability_runs.csv`
- `monte_carlo_stability_summary.csv`
- `monte_carlo_exact_enumeration_comparison.csv`
