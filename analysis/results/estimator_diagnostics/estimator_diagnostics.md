# Estimator Diagnostics

## Scope

This report adds the missing three-city estimator diagnostics needed before final manuscript figure promotion: QCE/coverage, RSE robust-scale plots, and SI-F11 per-sensor Bonferroni CI diagnostics.

## Methods Caveat

- Student-t critical values use a Cornish-Fisher approximation because SciPy is not a repository dependency.
- Lognormal confidence intervals use a delta-method interval for `log(mean) = log_mu + log_sigma²/2` with finite-population correction.
- SI-F11 CIs use daily sensor means with a gap-aware AR(1) GLS mean and variance.

## Selected 95% Daily QCE

| city | sample_size | estimator | days_evaluated | median_empirical_coverage | median_qce_pct_points |
| --- | --- | --- | --- | --- | --- |
| Chicago | 5 | arithmetic_mean_ci | 272 | 0.951 | 0.510 |
| Chicago | 5 | lognormal_delta_ci | 272 | 0.952 | 0.515 |
| Chicago | 10 | arithmetic_mean_ci | 272 | 0.950 | 0.540 |
| Chicago | 10 | lognormal_delta_ci | 272 | 0.952 | 0.560 |
| Chicago | 20 | arithmetic_mean_ci | 272 | 0.949 | 0.480 |
| Chicago | 20 | lognormal_delta_ci | 272 | 0.951 | 0.670 |
| Dhaka | 5 | arithmetic_mean_ci | 365 | 0.939 | 2.080 |
| Dhaka | 5 | lognormal_delta_ci | 365 | 0.950 | 1.920 |
| Dhaka | 10 | arithmetic_mean_ci | 365 | 0.936 | 1.460 |
| Dhaka | 10 | lognormal_delta_ci | 365 | 0.949 | 1.630 |
| Dhaka | 20 | arithmetic_mean_ci | 345 | 0.942 | 0.860 |
| Dhaka | 20 | lognormal_delta_ci | 345 | 0.947 | 1.620 |
| Lucknow | 5 | arithmetic_mean_ci | 365 | 0.942 | 1.070 |
| Lucknow | 5 | lognormal_delta_ci | 365 | 0.951 | 0.860 |
| Lucknow | 10 | arithmetic_mean_ci | 365 | 0.941 | 1.000 |
| Lucknow | 10 | lognormal_delta_ci | 365 | 0.947 | 0.930 |
| Lucknow | 20 | arithmetic_mean_ci | 365 | 0.945 | 0.550 |
| Lucknow | 20 | lognormal_delta_ci | 365 | 0.946 | 1.100 |


## Period QCE

| dataset_key | city | time_aggregation | time_index | sample_size | n_sensors_available | estimator | nominal_coverage | empirical_coverage | qce_pct_points | absolute_error_median_ugm3 | absolute_error_p95_ugm3 | draws | seed_used | valid_sensor_set_hash |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 5 | 277 | arithmetic_mean_ci | 0.680 | 0.676 | 0.350 | 0.268 | 0.906 | 10000 | 2478654535 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 5 | 277 | arithmetic_mean_ci | 0.900 | 0.908 | 0.760 | 0.268 | 0.906 | 10000 | 2478654535 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 5 | 277 | arithmetic_mean_ci | 0.950 | 0.952 | 0.230 | 0.268 | 0.906 | 10000 | 2478654535 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 5 | 277 | lognormal_delta_ci | 0.680 | 0.682 | 0.180 | 0.266 | 0.888 | 10000 | 2478654535 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 5 | 277 | lognormal_delta_ci | 0.900 | 0.908 | 0.850 | 0.266 | 0.888 | 10000 | 2478654535 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 5 | 277 | lognormal_delta_ci | 0.950 | 0.953 | 0.310 | 0.266 | 0.888 | 10000 | 2478654535 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 10 | 277 | arithmetic_mean_ci | 0.680 | 0.672 | 0.780 | 0.197 | 0.674 | 10000 | 3322833977 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 10 | 277 | arithmetic_mean_ci | 0.900 | 0.908 | 0.830 | 0.197 | 0.674 | 10000 | 3322833977 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 10 | 277 | arithmetic_mean_ci | 0.950 | 0.956 | 0.620 | 0.197 | 0.674 | 10000 | 3322833977 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 10 | 277 | lognormal_delta_ci | 0.680 | 0.680 | 0.020 | 0.196 | 0.665 | 10000 | 3322833977 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 10 | 277 | lognormal_delta_ci | 0.900 | 0.911 | 1.090 | 0.196 | 0.665 | 10000 | 3322833977 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 10 | 277 | lognormal_delta_ci | 0.950 | 0.956 | 0.620 | 0.196 | 0.665 | 10000 | 3322833977 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 15 | 277 | arithmetic_mean_ci | 0.680 | 0.664 | 1.560 | 0.165 | 0.543 | 10000 | 2407662816 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 15 | 277 | arithmetic_mean_ci | 0.900 | 0.907 | 0.660 | 0.165 | 0.543 | 10000 | 2407662816 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 15 | 277 | arithmetic_mean_ci | 0.950 | 0.955 | 0.530 | 0.165 | 0.543 | 10000 | 2407662816 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 15 | 277 | lognormal_delta_ci | 0.680 | 0.679 | 0.140 | 0.164 | 0.530 | 10000 | 2407662816 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 15 | 277 | lognormal_delta_ci | 0.900 | 0.908 | 0.840 | 0.164 | 0.530 | 10000 | 2407662816 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 15 | 277 | lognormal_delta_ci | 0.950 | 0.957 | 0.680 | 0.164 | 0.530 | 10000 | 2407662816 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 20 | 277 | arithmetic_mean_ci | 0.680 | 0.672 | 0.780 | 0.143 | 0.472 | 10000 | 2911454192 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 20 | 277 | arithmetic_mean_ci | 0.900 | 0.904 | 0.400 | 0.143 | 0.472 | 10000 | 2911454192 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 20 | 277 | arithmetic_mean_ci | 0.950 | 0.954 | 0.400 | 0.143 | 0.472 | 10000 | 2911454192 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 20 | 277 | lognormal_delta_ci | 0.680 | 0.687 | 0.710 | 0.141 | 0.461 | 10000 | 2911454192 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 20 | 277 | lognormal_delta_ci | 0.900 | 0.912 | 1.210 | 0.141 | 0.461 | 10000 | 2911454192 | 3f39e8d9593910d0 |
| chicago_lcs_corrected_no_collocation | Chicago | period | study_period | 20 | 277 | lognormal_delta_ci | 0.950 | 0.956 | 0.550 | 0.141 | 0.461 | 10000 | 2911454192 | 3f39e8d9593910d0 |
| dhaka_lcs | Dhaka | period | study_period | 5 | 35 | arithmetic_mean_ci | 0.680 | 0.669 | 1.050 | 3.300 | 9.315 | 10000 | 3194401873 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 5 | 35 | arithmetic_mean_ci | 0.900 | 0.924 | 2.450 | 3.300 | 9.315 | 10000 | 3194401873 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 5 | 35 | arithmetic_mean_ci | 0.950 | 0.968 | 1.770 | 3.300 | 9.315 | 10000 | 3194401873 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 5 | 35 | lognormal_delta_ci | 0.680 | 0.693 | 1.270 | 3.268 | 9.237 | 10000 | 3194401873 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 5 | 35 | lognormal_delta_ci | 0.900 | 0.930 | 3.010 | 3.268 | 9.237 | 10000 | 3194401873 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 5 | 35 | lognormal_delta_ci | 0.950 | 0.970 | 2.020 | 3.268 | 9.237 | 10000 | 3194401873 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 10 | 35 | arithmetic_mean_ci | 0.680 | 0.668 | 1.170 | 2.145 | 6.103 | 10000 | 2909120527 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 10 | 35 | arithmetic_mean_ci | 0.900 | 0.903 | 0.350 | 2.145 | 6.103 | 10000 | 2909120527 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 10 | 35 | arithmetic_mean_ci | 0.950 | 0.960 | 0.950 | 2.145 | 6.103 | 10000 | 2909120527 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 10 | 35 | lognormal_delta_ci | 0.680 | 0.704 | 2.390 | 2.107 | 6.032 | 10000 | 2909120527 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 10 | 35 | lognormal_delta_ci | 0.900 | 0.919 | 1.860 | 2.107 | 6.032 | 10000 | 2909120527 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 10 | 35 | lognormal_delta_ci | 0.950 | 0.965 | 1.460 | 2.107 | 6.032 | 10000 | 2909120527 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 15 | 35 | arithmetic_mean_ci | 0.680 | 0.672 | 0.820 | 1.598 | 4.480 | 10000 | 457764198 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 15 | 35 | arithmetic_mean_ci | 0.900 | 0.895 | 0.460 | 1.598 | 4.480 | 10000 | 457764198 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 15 | 35 | arithmetic_mean_ci | 0.950 | 0.950 | 0.040 | 1.598 | 4.480 | 10000 | 457764198 | cbc1dbbb6cf43f80 |
| dhaka_lcs | Dhaka | period | study_period | 15 | 35 | lognormal_delta_ci | 0.680 | 0.706 | 2.570 | 1.570 | 4.429 | 10000 | 457764198 | cbc1dbbb6cf43f80 |


## RSE Exceedance At n=20

| city | model | scale_estimator | days_rse_gt_10pct_pct |
| --- | --- | --- | --- |
| Chicago | lognormal | robust_mad | 0.000 |
| Chicago | lognormal | standard | 0.000 |
| Chicago | normal | robust_mad | 0.000 |
| Chicago | normal | standard | 0.735 |
| Dhaka | lognormal | robust_mad | 2.192 |
| Dhaka | lognormal | standard | 16.164 |
| Dhaka | normal | robust_mad | 1.644 |
| Dhaka | normal | standard | 9.041 |
| Lucknow | lognormal | robust_mad | 0.000 |
| Lucknow | lognormal | standard | 4.932 |
| Lucknow | normal | robust_mad | 0.000 |
| Lucknow | normal | standard | 5.205 |


## SI-F11 City Summary

| dataset_key | city | sensors | reference_mean_pm25_ugm3 | sensors_ci_excludes_reference | sensors_long_gap_gt_30d | median_daily_presence_pct | median_ar1_effective_n | median_gls_effective_n | max_longest_gap_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dhaka_lcs | Dhaka | 35 | 55.147 | 2 | 5 | 92.603 | 19.812 | 22.056 | 46.000 |
| lucknow_lcs | Lucknow | 71 | 61.802 | 4 | 37 | 81.370 | 12.827 | 15.645 | 326.000 |
| chicago_lcs_corrected_no_collocation | Chicago | 277 | 10.253 | 12 | 11 | 99.634 | 77.793 | 78.759 | 181.000 |


## Plot Files

- `/Users/guru/Documents/Macbook Pro/Manuscript Final Codes/OSPREY_CODE_Revision/analysis/plots/estimator_diagnostics/Table1_QCE_daily_median_by_city_estimator.png` and `.pdf`
- `/Users/guru/Documents/Macbook Pro/Manuscript Final Codes/OSPREY_CODE_Revision/analysis/plots/estimator_diagnostics/SI_F6_RSE_normal_daily_sensor_requirement.png` and `.pdf`
- `/Users/guru/Documents/Macbook Pro/Manuscript Final Codes/OSPREY_CODE_Revision/analysis/plots/estimator_diagnostics/SI_F7_RSE_lognormal_daily_sensor_requirement.png` and `.pdf`
- `/Users/guru/Documents/Macbook Pro/Manuscript Final Codes/OSPREY_CODE_Revision/analysis/plots/estimator_diagnostics/SI_F8_RSE_exceedance_curves.png` and `.pdf`
- `/Users/guru/Documents/Macbook Pro/Manuscript Final Codes/OSPREY_CODE_Revision/analysis/plots/estimator_diagnostics/SI_F11_period_sensor_means_bonferroni_ci.png` and `.pdf`

## Metadata

```json
{
  "created_at": "2026-06-08T16:20:19",
  "completed_at": "2026-06-08T16:21:15",
  "duration_seconds": 55.78552537500218,
  "draws": 10000,
  "master_seed": 20260522,
  "qce_sample_sizes": [
    5,
    10,
    15,
    20
  ],
  "coverage_levels": [
    0.68,
    0.9,
    0.95
  ],
  "skip_qce": false,
  "rse_target": 0.1,
  "bonferroni_alpha": 0.05,
  "requested_jobs": 1,
  "effective_jobs": 1,
  "compute_resources": {
    "requested_jobs": 1,
    "effective_jobs": 1,
    "available_cpu_count": 12,
    "total_memory_gb": 24.0,
    "platform": "macOS-26.5.1-arm64-arm-64bit-Mach-O",
    "blas_thread_environment": {
      "OMP_NUM_THREADS": "1",
      "OPENBLAS_NUM_THREADS": "1",
      "MKL_NUM_THREADS": "1",
      "VECLIB_MAXIMUM_THREADS": "1",
      "NUMEXPR_NUM_THREADS": "1"
    },
    "blas_thread_policy": "one BLAS/native thread per worker process to avoid oversubscription"
  },
  "critical_value_method": "Cornish-Fisher Student-t approximation",
  "lognormal_ci_method": "delta method on lognormal mean with finite-population correction",
  "si_f11_ci_method": "Bonferroni normal critical value on daily sensor means with gap-aware AR(1) GLS variance",
  "datasets": {
    "dhaka_lcs": {
      "spec": {
        "key": "dhaka_lcs",
        "city": "Dhaka",
        "network": "LCS",
        "pm_path": "data/pm/Dhaka_hourly_PM25.csv",
        "location_path": "data/locations/Dhaka_sensor_locations.csv",
        "source_frequency": "hourly",
        "pm_value": "inherited_calibrated_pm25",
        "exclude_collocated": false
      },
      "input_hashes": {
        "pm_matrix": "790d47a334e027d73c90f529d0d850218ebee0265f0a98c7db1a29bcd3700a95",
        "locations": "188717bb29805009fdbee4a1c24f5f89ee39b94ba9d5616fecb7710d0868b230"
      },
      "preprocessing": {
        "source_rows": 8760,
        "source_sensor_columns": 35,
        "retained_sensor_count": 35,
        "dropped_all_nan_sensor_count": 0,
        "dropped_all_nan_sensors": [],
        "date_count": 365,
        "date_min": "2022-04-01",
        "date_max": "2023-03-31",
        "source_frequency": "hourly",
        "exclude_collocated": false
      }
    },
    "lucknow_lcs": {
      "spec": {
        "key": "lucknow_lcs",
        "city": "Lucknow",
        "network": "LCS",
        "pm_path": "data/pm/Lucknow_hourly_PM25.csv",
        "location_path": "data/locations/Lucknow_sensor_locations.csv",
        "source_frequency": "hourly",
        "pm_value": "inherited_calibrated_pm25",
        "exclude_collocated": false
      },
      "input_hashes": {
        "pm_matrix": "74e3d7265f97f1f33bdc22cc02016470c0592683d753dedf2e0dc0dbefa9b13e",
        "locations": "a9219a95bcc2d43b5fd5495adbe08a6895616b4502654411c5d624f85325a61e"
      },
      "preprocessing": {
        "source_rows": 8760,
        "source_sensor_columns": 71,
        "retained_sensor_count": 71,
        "dropped_all_nan_sensor_count": 0,
        "dropped_all_nan_sensors": [],
        "date_count": 365,
        "date_min": "2022-04-01",
        "date_max": "2023-03-31",
        "source_frequency": "hourly",
        "exclude_collocated": false
      }
    },
    "chicago_lcs_corrected_no_collocation": {
      "spec": {
        "key": "chicago_lcs_corrected_no_collocation",
        "city": "Chicago",
        "network": "LCS corrected",
        "pm_path": "data/pm/Chicago_LCS_corrected_daily_PM25.csv",
        "location_path": "data/locations/Chicago_LCS_corrected_sensor_locations.csv",
        "source_frequency": "official_daily",
        "pm_value": "corrected_pm25",
        "exclude_collocated": true
      },
      "input_hashes": {
        "pm_matrix": "3ee4e821cb90da5ca9b1a5c5079c34a4a3f486f699ada94f061f727b0a75e2e0",
        "locations": "67d4ecc273939ca8f1af56b39f4098d2ed19c2a177577b58bda2eecb44d3d89b"
      },
      "preprocessing": {
        "source_rows": 273,
        "source_sensor_columns": 277,
        "retained_sensor_count": 277,
        "dropped_all_nan_sensor_count": 0,
        "dropped_all_nan_sensors": [],
        "date_count": 273,
        "date_min": "2025-09-01",
        "date_max": "2026-05-31",
        "source_frequency": "official_daily",
        "exclude_collocated": true
      }
    }
  },
  "git_commit": "accb6e0f4120ace5cc1c4ff37346ac12f24f1aae"
}
```
