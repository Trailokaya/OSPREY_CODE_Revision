# Spatial Autocorrelation Sensitivity Summary

## Scope And Guardrails

This summary reports spatial distance relations and spatial autocorrelation sensitivity for the three primary networks: Dhaka LCS, Lucknow LCS, and Chicago corrected LCS with collocation sensors excluded.

The manuscript-comparable highest-resolution layer is the aligned hourly matrix for all three cities. Chicago also has raw sub-hourly individual-reading parquet files, but those rows are event-level sparse readings rather than a synchronized cross-sensor matrix; exact-timestamp pairwise spatial correlations would therefore be dominated by alignment artifacts. The raw high-resolution files are inventoried below and the spatial-correlation analysis uses the aligned hourly layer.

Permutation Moran's I uses 199 deterministic permutations per sampled time window with seed 20260525. Hourly and daily windows are deterministically thinned when needed to keep the summary reproducible and computationally bounded; weekly, monthly, and total-period windows are kept in full.

## Chicago Raw High-Resolution Inventory

| dataset | row_count | sensor_column_count | timestamp_min | timestamp_max | median_timestamp_gap_seconds | median_non_null_readings_per_sensor |
| --- | --- | --- | --- | --- | --- | --- |
| highest_resolution_individual_lcs_corrected_pm25 | 0 | 0 |  |  |  |  |
| highest_resolution_individual_lcs_raw_pm25 | 0 | 0 |  |  |  |  |

## Distance-Band And KNN Support

| city | weight_scheme | sensor_count | undirected_pair_count | zero_neighbor_sensor_count | median_neighbor_count | median_link_distance_km |
| --- | --- | --- | --- | --- | --- | --- |
| Dhaka | band_2km | 35 | 39 | 14 | 1.000 | 1.065 |
| Dhaka | band_5km | 35 | 172 | 4 | 10.000 | 3.137 |
| Dhaka | band_10km | 35 | 367 | 1 | 24.000 | 5.180 |
| Dhaka | knn_5 | 35 | 121 | 0 | 5.000 | 2.494 |
| Lucknow | band_2km | 71 | 33 | 33 | 1.000 | 1.557 |
| Lucknow | band_5km | 71 | 285 | 11 | 8.000 | 3.526 |
| Lucknow | band_10km | 71 | 885 | 2 | 29.000 | 6.459 |
| Lucknow | knn_5 | 71 | 232 | 0 | 5.000 | 2.923 |
| Chicago | band_2km | 277 | 710 | 0 | 5.000 | 1.484 |
| Chicago | band_5km | 277 | 3838 | 0 | 29.000 | 3.222 |
| Chicago | band_10km | 277 | 12508 | 0 | 93.000 | 6.372 |
| Chicago | knn_5 | 277 | 786 | 0 | 5.000 | 1.477 |

## Distance-Decay Thresholds

Rows show the first distance bin where median pairwise Pearson correlation drops at or below the threshold. Blank rows mean the threshold was not reached in the observed distance bins.

| city | resolution | correlation_threshold | first_distance_bin_label | first_bin_pair_count | first_median_distance_km | first_bin_median_correlation |
| --- | --- | --- | --- | --- | --- | --- |
| Dhaka | highest_hourly | 0.900 | 0-1 km | 15.000 | 0.500 | 0.813 |
| Dhaka | highest_hourly | 0.950 | 0-1 km | 15.000 | 0.500 | 0.813 |
| Dhaka | daily | 0.900 | 20-50 km | 26.000 | 23.536 | 0.892 |
| Dhaka | daily | 0.950 | 0-1 km | 15.000 | 0.500 | 0.906 |
| Dhaka | weekly | 0.900 |  |  |  |  |
| Dhaka | weekly | 0.950 | 0-1 km | 15.000 | 0.500 | 0.937 |
| Dhaka | monthly | 0.900 |  |  |  |  |
| Dhaka | monthly | 0.950 |  |  |  |  |
| Lucknow | highest_hourly | 0.900 | 10-20 km | 900.000 | 14.008 | 0.897 |
| Lucknow | highest_hourly | 0.950 | 0-1 km | 3.000 | 0.929 | 0.935 |
| Lucknow | daily | 0.900 |  |  |  |  |
| Lucknow | daily | 0.950 |  |  |  |  |
| Lucknow | weekly | 0.900 |  |  |  |  |
| Lucknow | weekly | 0.950 |  |  |  |  |
| Lucknow | monthly | 0.900 |  |  |  |  |
| Lucknow | monthly | 0.950 |  |  |  |  |
| Chicago | highest_hourly | 0.900 | 10-20 km | 14367.000 | 14.285 | 0.894 |
| Chicago | highest_hourly | 0.950 | 1-2 km | 705.000 | 1.485 | 0.948 |
| Chicago | daily | 0.900 |  |  |  |  |
| Chicago | daily | 0.950 |  |  |  |  |
| Chicago | weekly | 0.900 |  |  |  |  |
| Chicago | weekly | 0.950 |  |  |  |  |
| Chicago | monthly | 0.900 |  |  |  |  |
| Chicago | monthly | 0.950 | 5-10 km | 8670.000 | 7.547 | 0.930 |

## Permutation Moran's I Sensitivity

Total-period rows contain one cross-sectional vector, so 0% or 100% significance values are single-vector diagnostics rather than temporal prevalence estimates.

| city | resolution | weight_scheme | time_windows_tested | median_observed_morans_i | positive_sig_pct | negative_sig_pct | two_sided_sig_pct | median_p_positive |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | highest_hourly | band_5km | 120 | 0.002 | 25.833 | 3.333 | 23.333 | 0.258 |
| Dhaka | highest_hourly | knn_5 | 120 | -0.019 | 12.500 | 5.000 | 10.000 | 0.388 |
| Dhaka | daily | band_5km | 240 | -0.004 | 17.917 | 0.833 | 11.667 | 0.290 |
| Dhaka | daily | knn_5 | 240 | -0.040 | 3.333 | 3.750 | 2.500 | 0.490 |
| Dhaka | monthly | band_5km | 12 | -0.022 | 0.000 | 0.000 | 0.000 | 0.420 |
| Dhaka | monthly | knn_5 | 12 | -0.068 | 0.000 | 0.000 | 0.000 | 0.647 |
| Dhaka | total_period | band_5km | 1 | 0.007 | 0.000 | 0.000 | 0.000 | 0.240 |
| Dhaka | total_period | knn_5 | 1 | -0.060 | 0.000 | 0.000 | 0.000 | 0.640 |
| Lucknow | highest_hourly | band_5km | 120 | 0.025 | 24.167 | 0.833 | 16.667 | 0.217 |
| Lucknow | highest_hourly | knn_5 | 120 | 0.043 | 29.167 | 2.500 | 23.333 | 0.228 |
| Lucknow | daily | band_5km | 240 | 0.004 | 11.667 | 1.667 | 6.250 | 0.328 |
| Lucknow | daily | knn_5 | 240 | -0.019 | 6.250 | 3.333 | 4.167 | 0.480 |
| Lucknow | monthly | band_5km | 12 | 0.001 | 0.000 | 0.000 | 0.000 | 0.360 |
| Lucknow | monthly | knn_5 | 12 | -0.031 | 0.000 | 0.000 | 0.000 | 0.583 |
| Lucknow | total_period | band_5km | 1 | -0.049 | 0.000 | 0.000 | 0.000 | 0.725 |
| Lucknow | total_period | knn_5 | 1 | -0.040 | 0.000 | 0.000 | 0.000 | 0.600 |
| Chicago | highest_hourly | band_5km | 120 | 0.163 | 82.500 | 0.000 | 75.833 | 0.005 |
| Chicago | highest_hourly | knn_5 | 120 | 0.212 | 80.000 | 0.833 | 75.000 | 0.005 |
| Chicago | daily | band_5km | 240 | 0.083 | 81.667 | 0.000 | 80.000 | 0.005 |
| Chicago | daily | knn_5 | 240 | 0.128 | 77.917 | 0.000 | 74.167 | 0.005 |
| Chicago | monthly | band_5km | 10 | 0.049 | 90.000 | 0.000 | 80.000 | 0.005 |
| Chicago | monthly | knn_5 | 10 | 0.079 | 80.000 | 0.000 | 70.000 | 0.020 |
| Chicago | total_period | band_5km | 1 | 0.034 | 100.000 | 0.000 | 100.000 | 0.025 |
| Chicago | total_period | knn_5 | 1 | 0.068 | 100.000 | 0.000 | 100.000 | 0.020 |

## Manuscript Interpretation

- Chicago has the clearest distance-decay and positive spatial autocorrelation signal, especially at hourly and daily aggregation.
- Dhaka and Lucknow have strong shared temporal signals but weaker daily/monthly spatial structure under the observed sensor spacing; nonsignificant Moran tests should be written as weak or inconsistent detectable spatial autocorrelation, not proof that spatial structure is absent.
- Distance-band Moran tests are sensitive to support: the 2 km band leaves many Dhaka and Lucknow sensors isolated, so 5 km, 10 km, and k-nearest-neighbor schemes are needed as sensitivity checks.
- The design-based Monte Carlo estimand remains defensible because it reproduces the deployed-network mean; spatial placement or kriging arguments should be framed as secondary design guidance, with Chicago being the strongest candidate for spatial methods.

## Quick City Signals

| city | median_observed_morans_i | positive_sig_pct | two_sided_sig_pct |
| --- | --- | --- | --- |
| Chicago | 0.128 | 77.917 | 74.167 |
| Dhaka | -0.040 | 3.333 | 2.500 |
| Lucknow | -0.019 | 6.250 | 4.167 |

| city | median_observed_morans_i | positive_sig_pct | two_sided_sig_pct |
| --- | --- | --- | --- |
| Chicago | 0.079 | 80.000 | 70.000 |
| Dhaka | -0.068 | 0.000 | 0.000 |
| Lucknow | -0.031 | 0.000 | 0.000 |

## Output Files

- `spatial/results/distance_correlation/spatial_weight_scheme_pair_counts.csv`
- `spatial/results/distance_correlation/spatial_distance_decay_thresholds.csv`
- `spatial/results/distance_correlation/spatial_morans_i_permutation_sensitivity.csv`
- `spatial/results/distance_correlation/spatial_chicago_raw_high_resolution_inventory.csv`
- `spatial/results/distance_correlation/spatial_distance_correlation_summary_metadata.json`
- `spatial/plots/distance_correlation/morans_i_permutation_sensitivity_heatmap.png` and `.pdf`
- `spatial/plots/distance_correlation/distance_band_pair_counts_by_city.png` and `.pdf`
- `spatial/plots/distance_correlation/distance_decay_thresholds_by_city.png` and `.pdf`
