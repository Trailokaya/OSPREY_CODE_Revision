# Missingness Follow-Up Tests

## Interpretation

Weak evidence of non-random missingness means the missing-data fraction has a small observed association with measured daily conditions, such as PM2.5 concentration, spatial variability, or calendar time. It does not prove a missing-not-at-random mechanism, and it does not prove that the final Monte Carlo conclusions are biased. It means we should avoid claiming missing completely at random and should keep sensitivity analyses in the manuscript workflow.

The tests below use observed data only. They cannot test dependence on unobserved PM2.5 values on days when a sensor is missing.

## City-Level Summary

| city | strongest_daily_domain | strongest_daily_variable | strongest_daily_spearman_rho | strongest_daily_p_value | strongest_daily_effect_strength | largest_high_low_variable | largest_high_low_missing_pct_point_difference | monthly_missing_range_pct_points | highest_missing_month |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chicago | temporal_structure | calendar_time | 0.108 | 0.099 | weak evidence | calendar_time | 1.586 | 3.791 | 2026-04 |
| Dhaka | spatial_variability | daily_spatial_sd | -0.133 | 0.010 | weak evidence | calendar_time | -5.791 | 37.782 | 2022-04 |
| Lucknow | temporal_structure | calendar_time | 0.423 | 0.000 | moderate evidence | calendar_time | 9.779 | 25.085 | 2023-03 |

## Strongest Daily Association Screens

| city | domain | x_variable | n_days | spearman_rho | spearman_ci_low | spearman_ci_high | permutation_p_value | effect_strength | slope_missing_pct_points_per_1sd_x |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chicago | temporal_structure | calendar_time | 242 | 0.108 | -0.018 | 0.233 | 0.099 | weak evidence | 0.647 |
| Chicago | concentration | daily_median_pm25 | 241 | -0.064 | -0.190 | 0.066 | 0.330 | little evidence | -0.049 |
| Dhaka | spatial_variability | daily_spatial_sd | 365 | -0.133 | -0.226 | -0.038 | 0.010 | weak evidence | -2.213 |
| Dhaka | concentration | daily_mean_pm25 | 365 | -0.127 | -0.210 | -0.041 | 0.017 | weak evidence | -2.241 |
| Lucknow | temporal_structure | calendar_time | 365 | 0.423 | 0.320 | 0.521 | 0.000 | moderate evidence | 3.511 |
| Lucknow | spatial_variability | daily_spatial_cv | 365 | 0.298 | 0.203 | 0.389 | 0.000 | weak evidence | 1.351 |

## High-Versus-Low Day Contrasts

This compares mean missingness on top-quartile versus bottom-quartile days for each domain variable.

| city | domain | x_variable | low_group_missing_pct | high_group_missing_pct | high_minus_low_missing_pct_points | permutation_p_value |
| --- | --- | --- | --- | --- | --- | --- |
| Chicago | temporal_structure | calendar_time | 2.574 | 4.161 | 1.586 | 0.558 |
| Chicago | concentration | daily_mean_pm25 | 2.450 | 2.355 | -0.095 | 0.384 |
| Dhaka | temporal_structure | calendar_time | 20.110 | 14.319 | -5.791 | 0.010 |
| Dhaka | spatial_variability | daily_spatial_sd | 15.089 | 9.838 | -5.251 | 0.000 |
| Lucknow | temporal_structure | calendar_time | 25.057 | 34.836 | 9.779 | 0.000 |
| Lucknow | spatial_variability | daily_spatial_cv | 26.024 | 31.852 | 5.828 | 0.000 |

## Monthly Missingness Range

| city | n_months | lowest_missing_month | lowest_month_mean_missing_pct | highest_missing_month | highest_month_mean_missing_pct | monthly_missing_range_pct_points |
| --- | --- | --- | --- | --- | --- | --- |
| Chicago | 8 | 2025-11 | 1.889 | 2026-04 | 5.680 | 3.791 |
| Dhaka | 12 | 2022-06 | 6.643 | 2022-04 | 44.425 | 37.782 |
| Lucknow | 12 | 2022-12 | 18.626 | 2023-03 | 43.711 | 25.085 |

## Strongest Sensor-Level Screens

| city | domain | x_variable | y_variable | n_sensors | spearman_rho | permutation_p_value | effect_strength |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Chicago | sensor_level_variability | sensor_daily_pm25_sd | sensor_longest_missing_gap_days | 277 | -0.109 | 0.069 | weak evidence |
| Chicago | sensor_level_pm25 | sensor_period_mean_pm25 | sensor_record_missing_pct | 277 | 0.075 | 0.212 | little evidence |
| Dhaka | sensor_location | sensor_latitude | sensor_record_missing_pct | 35 | 0.491 | 0.003 | moderate evidence |
| Dhaka | sensor_location | sensor_latitude | sensor_daily_missing_pct | 35 | 0.364 | 0.030 | moderate evidence |
| Lucknow | sensor_location | sensor_latitude | sensor_record_missing_pct | 71 | -0.164 | 0.171 | weak evidence |
| Lucknow | sensor_location | sensor_latitude | sensor_daily_missing_pct | 71 | -0.120 | 0.318 | weak evidence |

## Output Files

- `missingness_followup_city_summary.csv`
- `missingness_followup_daily_permutation_tests.csv`
- `missingness_followup_high_low_contrasts.csv`
- `missingness_followup_monthly_summary.csv`
- `missingness_followup_monthly_range.csv`
- `missingness_followup_sensor_level_tests.csv`
- `missingness_followup_tests.md`
