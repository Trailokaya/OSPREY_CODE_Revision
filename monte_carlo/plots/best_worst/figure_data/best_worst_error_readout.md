# Best and Worst Monte Carlo Error Readout

This readout is generated from the P0 baseline run. For the period table, `best` and `worst` are the minimum and maximum errors observed across the 10,000 SRSWOR draws for that city and sample size. For the daily table, values summarize the distribution of each day's best/worst draw across all evaluated days.

## Selected Period n Values

| dataset_key | sample_size | reference_mean_ugm3 | best_ape_pct | ape_median_pct | ape_p95_pct | worst_ape_pct | best_absolute_error_ugm3 | absolute_error_median_ugm3 | absolute_error_p95_ugm3 | worst_absolute_error_ugm3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chicago_lcs_corrected_no_collocation | 5 | 10.3 | 0.000985 | 2.59 | 9.07 | 25.7 | 0.000101 | 0.265 | 0.93 | 2.63 |
| chicago_lcs_corrected_no_collocation | 10 | 10.3 | 0.000183 | 1.9 | 6.63 | 16.8 | 1.88e-05 | 0.195 | 0.68 | 1.72 |
| chicago_lcs_corrected_no_collocation | 20 | 10.3 | 0.000835 | 1.42 | 4.61 | 9.11 | 8.56e-05 | 0.145 | 0.472 | 0.934 |
| chicago_lcs_corrected_no_collocation | 30 | 10.3 | 0.000237 | 1.17 | 3.61 | 7.73 | 2.43e-05 | 0.12 | 0.371 | 0.793 |
| chicago_lcs_corrected_no_collocation | 50 | 10.3 | 9.78e-05 | 0.881 | 2.6 | 5.4 | 1e-05 | 0.0903 | 0.266 | 0.554 |
| chicago_lcs_corrected_no_collocation | 100 | 10.3 | 1.07e-05 | 0.577 | 1.62 | 3.09 | 1.09e-06 | 0.0592 | 0.167 | 0.317 |
| chicago_lcs_corrected_no_collocation | 200 | 10.3 | 4.26e-05 | 0.263 | 0.764 | 1.37 | 4.37e-06 | 0.027 | 0.0783 | 0.141 |
| dhaka_lcs | 5 | 55.1 | 2.18e-05 | 5.89 | 17.3 | 30.3 | 1.2e-05 | 3.25 | 9.55 | 16.7 |
| dhaka_lcs | 10 | 55.1 | 0.000174 | 3.89 | 10.9 | 19.1 | 9.59e-05 | 2.15 | 6.02 | 10.5 |
| dhaka_lcs | 20 | 55.1 | 1.06e-05 | 2.12 | 5.92 | 9.72 | 5.84e-06 | 1.17 | 3.26 | 5.36 |
| dhaka_lcs | 30 | 55.1 | 0.000266 | 0.971 | 2.83 | 5.3 | 0.000147 | 0.536 | 1.56 | 2.92 |
| lucknow_lcs | 5 | 61.8 | 0.000537 | 7.98 | 23.2 | 54.7 | 0.000332 | 4.93 | 14.3 | 33.8 |
| lucknow_lcs | 10 | 61.8 | 0.00128 | 5.64 | 15.8 | 30.1 | 0.000789 | 3.49 | 9.77 | 18.6 |
| lucknow_lcs | 20 | 61.8 | 0.000725 | 3.61 | 10.4 | 20.9 | 0.000448 | 2.23 | 6.41 | 12.9 |
| lucknow_lcs | 30 | 61.8 | 0.000218 | 2.6 | 7.5 | 15 | 0.000135 | 1.61 | 4.63 | 9.24 |

## Selected Daily n Values

| dataset_key | sample_size | dates_evaluated | best_ape_median_over_days_pct | median_ape_median_over_days_pct | p95_ape_median_over_days_pct | worst_ape_median_over_days_pct | worst_ape_max_over_days_pct | date_at_worst_ape |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chicago_aqs | 5 | 212 | 0.0343 | 3.04 | 7.77 | 10 | 21.9 | 2026-01-20 |
| chicago_lcs_corrected_all | 5 | 272 | 0.00567 | 3.53 | 11.5 | 33.4 | 239 | 2026-03-13 |
| chicago_lcs_corrected_all | 10 | 272 | 0.00265 | 2.6 | 8.21 | 20.6 | 120 | 2026-03-13 |
| chicago_lcs_corrected_all | 20 | 272 | 0.00112 | 1.88 | 5.94 | 13.2 | 64.6 | 2026-03-16 |
| chicago_lcs_corrected_all | 30 | 272 | 0.000806 | 1.53 | 4.66 | 9.79 | 44 | 2026-03-16 |
| chicago_lcs_corrected_all | 50 | 272 | 0.000483 | 1.16 | 3.45 | 7.02 | 24 | 2026-03-13 |
| chicago_lcs_corrected_no_collocation | 5 | 272 | 0.00459 | 3.5 | 11.5 | 32 | 240 | 2026-03-13 |
| chicago_lcs_corrected_no_collocation | 10 | 272 | 0.00255 | 2.61 | 8.26 | 20.5 | 119 | 2026-03-13 |
| chicago_lcs_corrected_no_collocation | 20 | 272 | 0.00112 | 1.88 | 5.9 | 12.8 | 62.5 | 2026-03-13 |
| chicago_lcs_corrected_no_collocation | 30 | 272 | 0.000822 | 1.54 | 4.71 | 9.81 | 40.5 | 2026-03-13 |
| chicago_lcs_corrected_no_collocation | 50 | 272 | 0.000539 | 1.18 | 3.43 | 7.02 | 23.7 | 2026-03-16 |
| chicago_lcs_raw_all | 5 | 272 | 0.00303 | 5.58 | 17.7 | 44.1 | 539 | 2026-03-01 |
| chicago_lcs_raw_all | 10 | 272 | 0.00152 | 4.03 | 12.3 | 27.9 | 294 | 2026-03-01 |
| chicago_lcs_raw_all | 20 | 272 | 0.000799 | 2.86 | 8.52 | 18.5 | 162 | 2026-03-01 |
| chicago_lcs_raw_all | 30 | 272 | 0.000607 | 2.33 | 6.84 | 14 | 107 | 2026-03-01 |
| chicago_lcs_raw_all | 50 | 272 | 0.000391 | 1.73 | 5.08 | 10 | 66.8 | 2026-03-01 |
| chicago_lcs_raw_no_collocation | 5 | 272 | 0.00298 | 5.55 | 17.8 | 42.9 | 547 | 2026-03-01 |
| chicago_lcs_raw_no_collocation | 10 | 272 | 0.00198 | 4.03 | 12.5 | 27.9 | 297 | 2026-03-01 |
| chicago_lcs_raw_no_collocation | 20 | 272 | 0.000954 | 2.87 | 8.59 | 18.1 | 153 | 2026-03-01 |
| chicago_lcs_raw_no_collocation | 30 | 272 | 0.000675 | 2.31 | 6.77 | 14.2 | 107 | 2026-03-01 |
| chicago_lcs_raw_no_collocation | 50 | 272 | 0.000374 | 1.76 | 5.06 | 10.4 | 62.8 | 2026-03-01 |
| dhaka_lcs | 5 | 365 | 0.00133 | 8.8 | 24.8 | 49.3 | 127 | 2023-02-10 |
| dhaka_lcs | 10 | 365 | 0.00083 | 5.75 | 15.8 | 28.4 | 88.3 | 2022-05-19 |
| dhaka_lcs | 20 | 345 | 0.000411 | 3.03 | 8.32 | 14.8 | 42.2 | 2022-05-19 |
| dhaka_lcs | 30 | 320 | 0.000357 | 1.15 | 3.44 | 6.59 | 20.2 | 2023-02-10 |
| lucknow_lcs | 5 | 365 | 0.000995 | 6.51 | 19.3 | 41.4 | 194 | 2023-01-17 |
| lucknow_lcs | 10 | 365 | 0.000643 | 4.5 | 12.7 | 25.9 | 92.5 | 2023-01-17 |
| lucknow_lcs | 20 | 365 | 0.000399 | 2.85 | 7.95 | 15.1 | 39.7 | 2023-01-17 |
| lucknow_lcs | 30 | 365 | 0.000271 | 1.95 | 5.48 | 10.4 | 25.1 | 2023-01-17 |
| lucknow_lcs | 50 | 303 | 0.000121 | 0.756 | 2.21 | 4.57 | 18.5 | 2023-01-17 |
| lucknow_madhwal_lcs | 5 | 353 | 0.000938 | 5.65 | 16.9 | 35 | 152 | 2022-07-25 |
| lucknow_madhwal_lcs | 10 | 349 | 0.000675 | 3.91 | 11.3 | 22.6 | 76.8 | 2022-06-21 |
| lucknow_madhwal_lcs | 20 | 297 | 0.000432 | 2.73 | 7.71 | 14.4 | 41.4 | 2022-06-21 |
| lucknow_madhwal_lcs | 30 | 294 | 0.000207 | 1.94 | 5.45 | 10.2 | 27.4 | 2022-06-16 |
| lucknow_madhwal_lcs | 50 | 274 | 0.000116 | 0.834 | 2.42 | 4.9 | 15.8 | 2022-06-21 |
