# Three-City Comparative Analysis

## Scope

This report compares the current primary manuscript networks: Dhaka LCS, Lucknow LCS, and Chicago corrected LCS with collocation sensors excluded.

It is a screening and audit summary, not a proof that missingness is missing-at-random. The missingness section tests whether daily missing fraction is associated with observed daily PM2.5 level or cross-sensor variability.

## Key Findings

- **Dhaka:** 35 retained sensors; period mean 55.15 µg/m³; median daily missing fraction 11.31%; all-missing daily row count 0; median nearest-neighbor distance 1.57 km; MAR screen: weak evidence of non-random missingness with observed daily conditions.
- **Lucknow:** 71 retained sensors; period mean 61.80 µg/m³; median daily missing fraction 27.41%; all-missing daily row count 0; median nearest-neighbor distance 1.93 km; MAR screen: weak evidence of non-random missingness with observed daily conditions.
- **Chicago:** 277 retained sensors; period mean 10.25 µg/m³; median daily missing fraction 2.53%; all-missing daily row count 1; median nearest-neighbor distance 1.37 km; MAR screen: no strong evidence against concentration/variability-independent missingness.
- **Chicago AQS context:** corrected LCS daily network mean is strongly correlated with AQS mean (r=0.90, paired days=212), with MAE=2.12 µg/m³ and LCS-minus-AQS bias=1.56 µg/m³.

## Overall Comparative Summary

| city | source_frequency | retained_sensor_count | daily_mean_pm25_median_ugm3 | period_sensor_mean_mean_ugm3 | missing_pm_fraction_pct | daily_valid_sensor_median | daily_days_with_zero_valid_sensors | convex_hull_area_km2 | sensor_density_per_100_km2_hull | median_nearest_neighbor_km | strongest_missingness_association_variable | strongest_missingness_spearman_rho |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | hourly | 35 | 35.34 | 55.15 | 14.20 | 33.00 | 0 | 342.35 | 10.22 | 1.57 | daily_spatial_sd | -0.13 |
| Lucknow | hourly | 71 | 40.25 | 61.80 | 28.34 | 56.00 | 0 | 1504.54 | 4.72 | 1.93 | daily_spatial_cv | 0.30 |
| Chicago | official_daily | 277 | 8.94 | 10.25 | 2.78 | 270.00 | 1 | 695.83 | 39.81 | 1.37 | daily_median_pm25 | -0.07 |

## QA/QC Screen

The canonical matrices show no negative or nonpositive PM2.5 values in the retained primary networks. Chicago uses official daily corrected LCS values for the main comparison; Dhaka and Lucknow use hourly matrices.

| city | timestamp_rows | expected_timestamp_rows | retained_sensor_count | collocation_rows_excluded | missing_pm_fraction_pct | nonpositive_value_count | pm_gt_250_count | pm_min_ugm3 | pm_max_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 8760 | 8760 | 35 | 0 | 14.20 | 0 | 3502 | 1.00 | 1816.67 |
| Lucknow | 8760 | 8760 | 71 | 0 | 28.34 | 0 | 7911 | 1.00 | 1883.00 |
| Chicago | 273 | 273 | 277 | 9 | 2.78 | 0 | 0 | 1.69 | 55.21 |

## PM2.5 Mean/Median Summary

| city | daily_count | daily_mean_pm25_mean_ugm3 | daily_mean_pm25_median_ugm3 | daily_median_pm25_median_ugm3 | daily_spatial_sd_median_ugm3 | daily_spatial_cv_median | period_sensor_mean_mean_ugm3 | period_sensor_mean_median_ugm3 | period_sensor_mean_cv |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 365 | 54.34 | 35.34 | 33.12 | 10.70 | 0.31 | 55.15 | 54.32 | 0.21 |
| Lucknow | 365 | 62.05 | 40.25 | 39.53 | 9.16 | 0.23 | 61.80 | 59.49 | 0.28 |
| Chicago | 272 | 10.25 | 8.94 | 8.87 | 1.28 | 0.14 | 10.25 | 10.24 | 0.10 |

## Missingness and MAR Screen

This is an observed-data diagnostic. A weak correlation does not prove missing-at-random, and a correlation does not by itself identify mechanism. It indicates whether missingness tracks observed daily concentration or spatial variability.

| city | daily_days_total | daily_days_with_zero_valid_sensors | record_missing_fraction_pct | median_sensor_record_uptime_pct | p10_sensor_record_uptime_pct | daily_missing_fraction_median_pct | daily_valid_sensor_min | daily_valid_sensor_median | daily_missing_fraction_p90_pct | max_longest_missing_gap_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 365 | 0 | 14.20 | 87.64 | 75.18 | 11.31 | 15 | 33.00 | 22.38 | 46 |
| Lucknow | 365 | 0 | 28.34 | 73.22 | 51.28 | 27.41 | 39 | 56.00 | 38.54 | 326 |
| Chicago | 273 | 1 | 2.78 | 99.63 | 98.17 | 2.53 | 0 | 270.00 | 3.25 | 181 |

### Strongest Missingness Association By City

| city | x_variable | n_days | pearson_r | spearman_rho | evidence_strength | direction |
| --- | --- | --- | --- | --- | --- | --- |
| Chicago | daily_median_pm25 | 272 | -0.09 | -0.07 | little evidence | negative |
| Dhaka | daily_spatial_sd | 365 | -0.18 | -0.13 | weak evidence | negative |
| Lucknow | daily_spatial_cv | 365 | 0.19 | 0.30 | weak evidence | positive |

### Longest Sensor Gaps

These are the top five longest daily gaps per city retained for follow-up QA/QC and sensitivity checks.

| city | sensor_id | record_uptime_pct | daily_availability_pct | longest_missing_gap_days | period_mean_pm25_ugm3 | latitude | longitude |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Chicago | DJJWX4142 | 21.25 | 21.25 | 181 | 8.62 | 41.83 | -87.72 |
| Chicago | DMAEX1156 | 37.00 | 37.00 | 172 | 9.96 | 41.70 | -87.59 |
| Chicago | DEYGE9157 | 53.48 | 53.48 | 109 | 8.78 | 41.70 | -87.57 |
| Chicago | DSSQU9498 | 61.17 | 61.17 | 104 | 10.50 | 41.89 | -87.64 |
| Chicago | DDVZB7943 | 70.33 | 70.33 | 80 | 8.41 | 41.80 | -87.58 |
| Dhaka | 81432151044 | 72.25 | 73.70 | 46 | 46.87 | 23.87 | 90.39 |
| Dhaka | 81432151062 | 86.68 | 87.95 | 38 | 51.68 | 23.73 | 90.40 |
| Dhaka | 81432152006 | 87.56 | 88.77 | 38 | 60.38 | 23.74 | 90.39 |
| Dhaka | 81432151066 | 80.07 | 81.64 | 35 | 60.75 | 23.79 | 90.40 |
| Dhaka | 81432151048 | 78.17 | 80.55 | 34 | 48.22 | 23.73 | 90.39 |
| Lucknow | 81432147056 | 4.52 | 6.30 | 326 | 45.11 | 26.84 | 80.89 |
| Lucknow | 81432144008 | 14.25 | 16.99 | 173 | 34.47 | 26.80 | 81.02 |
| Lucknow | 81432147060 | 52.85 | 55.62 | 162 | 24.82 | 26.76 | 80.87 |
| Lucknow | 81432144016 | 8.94 | 11.51 | 150 | 42.55 | 26.85 | 81.03 |
| Lucknow | 81432131007 | 61.20 | 61.92 | 139 | 30.91 | 26.84 | 80.93 |

## Sensor Spatial Support

Density here means sensor density per convex-hull area, not population density.

| city | retained_sensor_count | convex_hull_area_km2 | sensor_density_per_100_km2_hull | mean_pairwise_distance_km | median_pairwise_distance_km | median_nearest_neighbor_km | p90_nearest_neighbor_km |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 35 | 342.35 | 10.22 | 9.14 | 7.93 | 1.57 | 4.61 |
| Lucknow | 71 | 1504.54 | 4.72 | 15.72 | 13.07 | 1.93 | 5.68 |
| Chicago | 277 | 695.83 | 39.81 | 15.62 | 13.95 | 1.37 | 1.48 |

## Chicago Regulatory Context

| paired_days | pearson_r | mae_ugm3 | rmse_ugm3 | bias_lcs_minus_aqs_ugm3 | lcs_mean_ugm3 | aqs_mean_ugm3 |
| --- | --- | --- | --- | --- | --- | --- |
| 212 | 0.90 | 2.12 | 2.80 | 1.56 | 10.85 | 9.29 |

## Output Files

- `comparative_overall_summary.csv`
- `comparative_qaqc_summary.csv`
- `comparative_pm25_summary.csv`
- `comparative_missingness_summary.csv`
- `comparative_missingness_correlation_screen.csv`
- `comparative_spatial_support_summary.csv`
- `comparative_sensor_level_summary.csv`
- `comparative_sensor_long_gap_extremes.csv`
- `comparative_daily_city_metrics.csv`
- `comparative_chicago_lcs_aqs_context.csv`
- `three_city_comparative_analysis.md`

## Recommended Next Uses

- Use `comparative_overall_summary.csv` for one-row-per-city manuscript tables.
- Use `comparative_missingness_correlation_screen.csv` to decide how cautiously to write about missingness.
- Use `comparative_sensor_level_summary.csv` to identify sensors driving long gaps, low uptime, or high/low period means.
- Use `comparative_spatial_support_summary.csv` for map captions and spatial-support language.
