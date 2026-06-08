# QA/QC Low-Tail Screen

Generated: 2026-06-08T16:11:47

## Purpose

This diagnostic directly addresses whether implausibly low but nonzero PM2.5 values remain after inherited QA/QC. It is a screen, not a new filter.

A value is flagged in two ways:

- Absolute low tail: valid PM2.5 greater than zero but below 1.0, 2.0, 5.0 µg/m³.
- Relative low tail: valid PM2.5 below 20% of the same-time network median when at least 5 sensors are valid and the network median is at least 10 µg/m³.

## City-Level Summary

| dataset_key | city | network | source_frequency | sensor_count | timestamp_count | valid_observation_count | missing_observation_count | missing_observation_pct | relative_low_evaluable_timestamp_count | relative_low_observation_count | relative_low_observation_pct_of_valid | daily_relative_low_evaluable_day_count | daily_relative_low_cell_count | daily_relative_low_cell_pct_of_observed_daily_cells | sensors_with_low_tail_review_flag | pm_min_ugm3 | pm_p01_ugm3 | pm_p05_ugm3 | pm_median_ugm3 | pm_p95_ugm3 | pm_max_ugm3 | pm_gt0_lt1_count | pm_gt0_lt1_pct_of_valid | pm_gt0_lt2_count | pm_gt0_lt2_pct_of_valid | pm_gt0_lt5_count | pm_gt0_lt5_pct_of_valid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dhaka_lcs | Dhaka | LCS | hourly | 35 | 8760 | 263052 | 43548 | 14.204 | 7853 | 1884 | 0.716 | 345 | 83 | 0.717 | 2 | 1.000 | 4.000 | 6.750 | 33.000 | 170.000 | 1816.667 | 0 | 0.000 | 234 | 0.089 | 5074 | 1.929 |
| lucknow_lcs | Lucknow | LCS | hourly | 71 | 8760 | 445689 | 176271 | 28.341 | 8090 | 763 | 0.171 | 350 | 28 | 0.139 | 1 | 1.000 | 4.000 | 7.750 | 37.500 | 186.750 | 1883.000 | 0 | 0.000 | 702 | 0.158 | 6640 | 1.490 |
| chicago_lcs_corrected_no_collocation | Chicago | LCS corrected | official_daily | 277 | 273 | 73517 | 2104 | 2.782 | 115 | 9 | 0.012 | 115 | 9 | 0.012 | 2 | 1.690 | 3.562 | 4.370 | 8.840 | 21.020 | 55.210 | 0 | 0.000 | 3 | 0.004 | 7739 | 10.527 |

## Top Sensor-Level Review Flags

| city | sensor_id | station_name | relative_low_observation_pct_of_valid | daily_relative_low_day_pct_of_observed_days | pm_gt0_lt2_pct_of_valid | pm_min_ugm3 | source_record_uptime_pct | low_tail_review_flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | 81432151072 | 63. Khilkhet | 18.881 | 19.420 | 1.019 | 1.000 | 91.838 | True |
| Lucknow | 81432144017 | Aziz Nagar | 9.329 | 8.408 | 2.389 | 1.000 | 90.308 | True |
| Chicago | DAEXF8484 | Mount Greenwood 1 | 1.838 | 1.838 | 1.103 | 1.690 | 99.634 | True |
| Dhaka | 81432150006 | 31. Rupnogor high school, Pallabi | 3.798 | 0.330 | 0.329 | 1.000 | 76.336 | True |
| Chicago | DMMAG3845 | Riverdale 3 | 1.471 | 1.471 | 0.000 | 3.000 | 99.634 | True |
| Lucknow | 81432144008 | Chak Ganjaria | 0.000 | 0.000 | 0.721 | 1.000 | 14.247 | False |
| Dhaka | 81432130035 | 12. Bashundhara RA | 0.056 | 0.578 | 0.019 | 1.500 | 61.701 | False |
| Dhaka | 81432124031 | 1. Siddeshwari  | 0.100 | 0.288 | 0.112 | 1.000 | 91.655 | False |
| Dhaka | 81432130015 | 18. North Badda | 0.094 | 0.296 | 0.094 | 1.000 | 85.422 | False |
| Dhaka | 81432130043 | 17. Mirpur, Botanical | 0.136 | 0.338 | 0.000 | 2.000 | 75.822 | False |
| Dhaka | 81432130017 | 8. Vasantek | 0.107 | 0.301 | 0.061 | 1.000 | 74.760 | False |
| Dhaka | 81432130036 | 10. Dholaipar | 0.090 | 0.296 | 0.077 | 1.000 | 88.836 | False |

## Interpretation

- The screen should not be interpreted as evidence that all low values are bad data; low values may be real during cleaner periods.
- The relative screen is more relevant for reviewer QA/QC concerns because it asks whether a sensor is unusually low when peers are not low.
- These diagnostics support manuscript language that retained values passed inherited QA/QC and were additionally checked for low-tail anomalies, but they do not justify retroactive filtering unless a flagged sensor is independently confirmed faulty.
- If a flagged sensor is excluded in a future sensitivity, the exclusion changes the finite population and should be reported as an estimand-change sensitivity.
