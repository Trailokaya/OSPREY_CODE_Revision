# Spatial Distance-Correlation Analysis

## Scope

This compares spatial distance relationships across the three primary networks at highest available canonical resolution, daily, weekly, monthly, and total-period aggregation. Highest resolution means the canonical hourly matrix for Dhaka, Lucknow, and Chicago corrected LCS. Chicago collocation sensors are excluded.

Pairwise Pearson correlations are only meaningful where at least three time windows exist, so the total-period rows summarize pairwise absolute differences in full-period sensor means rather than temporal correlations.

## Distance Relation Summary

| city | resolution | sensor_count | time_windows | median_pearson_correlation | spearman_distance_vs_correlation | correlation_slope_per_10km | median_mean_abs_difference_ugm3 | median_semivariance_ugm3_sq | spearman_distance_vs_mean_abs_difference |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chicago | highest_hourly | 277 | 6557 | 0.891 | -0.557 | -0.032 | 1.851 | 5.003 | 0.471 |
| Chicago | daily | 277 | 274 | 0.969 | -0.444 | -0.012 | 1.188 | 1.386 | 0.231 |
| Chicago | weekly | 277 | 40 | 0.973 | -0.243 | -0.008 | 0.950 | 0.743 | 0.096 |
| Chicago | monthly | 277 | 10 | 0.921 | -0.145 | -0.019 | 1.096 | 1.090 | 0.085 |
| Chicago | total_period | 277 | 1 |  |  |  | 0.794 | 0.315 | 0.021 |
| Dhaka | highest_hourly | 35 | 8760 | 0.779 | -0.188 | -0.022 | 20.487 | 890.255 | 0.278 |
| Dhaka | daily | 35 | 365 | 0.920 | -0.170 | 0.003 | 15.211 | 296.648 | 0.200 |
| Dhaka | weekly | 35 | 53 | 0.952 | -0.009 | 0.018 | 13.872 | 201.509 | 0.138 |
| Dhaka | monthly | 35 | 12 | 0.971 | 0.055 | 0.024 | 13.136 | 173.604 | 0.104 |
| Dhaka | total_period | 35 | 1 |  |  |  | 10.137 | 51.384 | 0.099 |
| Lucknow | highest_hourly | 71 | 8760 | 0.898 | -0.289 | -0.022 | 15.437 | 455.329 | 0.229 |
| Lucknow | daily | 71 | 365 | 0.962 | -0.250 | -0.013 | 12.083 | 186.143 | 0.184 |
| Lucknow | weekly | 71 | 53 | 0.968 | -0.110 | -0.007 | 12.254 | 167.248 | 0.141 |
| Lucknow | monthly | 71 | 12 | 0.977 | -0.073 | 0.003 | 12.957 | 164.858 | 0.116 |
| Lucknow | total_period | 71 | 1 |  |  |  | 15.392 | 118.459 | 0.055 |

## Moran's I Summary

| city | resolution | time_windows_with_valid_morans_i | median_morans_i_knn5 | p10_morans_i_knn5 | p90_morans_i_knn5 |
| --- | --- | --- | --- | --- | --- |
| Dhaka | highest_hourly | 8758 | -0.019 | -0.130 | 0.155 |
| Dhaka | daily | 365 | -0.041 | -0.132 | 0.056 |
| Dhaka | weekly | 53 | -0.062 | -0.142 | 0.032 |
| Dhaka | monthly | 12 | -0.068 | -0.108 | -0.028 |
| Dhaka | total_period | 1 | -0.060 | -0.060 | -0.060 |
| Lucknow | highest_hourly | 8760 | 0.026 | -0.104 | 0.254 |
| Lucknow | daily | 365 | -0.019 | -0.128 | 0.100 |
| Lucknow | weekly | 53 | -0.037 | -0.153 | 0.037 |
| Lucknow | monthly | 12 | -0.031 | -0.127 | 0.008 |
| Lucknow | total_period | 1 | -0.040 | -0.040 | -0.040 |
| Chicago | highest_hourly | 6553 | 0.159 | 0.012 | 0.525 |
| Chicago | daily | 274 | 0.129 | 0.026 | 0.363 |
| Chicago | weekly | 40 | 0.099 | 0.041 | 0.210 |
| Chicago | monthly | 10 | 0.079 | 0.030 | 0.186 |
| Chicago | total_period | 1 | 0.068 | 0.068 | 0.068 |

## Plot Files

- `spatial/plots/distance_correlation/distance_correlation_binned_by_city.png` and `.pdf`
- `spatial/plots/distance_correlation/distance_absolute_difference_binned_by_city.png` and `.pdf`
- `spatial/plots/distance_correlation/empirical_variogram_binned_by_city.png` and `.pdf`
- `spatial/plots/distance_correlation/morans_i_by_city_resolution.png` and `.pdf`

## Output CSV Files

- `spatial/results/distance_correlation/spatial_pairwise_distance_metrics.csv`
- `spatial/results/distance_correlation/spatial_distance_binned_summary.csv`
- `spatial/results/distance_correlation/spatial_distance_relation_summary.csv`
- `spatial/results/distance_correlation/spatial_morans_i_summary.csv`
- `spatial/results/distance_correlation/spatial_distance_correlation_metadata.json`
