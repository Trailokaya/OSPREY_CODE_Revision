# QA/QC And Calibration Summary

Generated: 2026-06-06T23:16:41

## Analysis Position

The analysis uses the cleaned/calibrated PM2.5 values supplied by the deployment data products. Our contribution is not to rederive calibration models; it is to evaluate how random subnetworks reproduce the deployed reference-network mean after the inherited QA/QC/calibration pipeline.

## Retained Data Products

- Dhaka and Lucknow use inherited calibrated low-cost-sensor PM2.5 matrices from the original manuscript data package.
- Chicago uses corrected low-cost-sensor daily PM2.5 as the primary third-city analysis; raw Chicago LCS and AQS are retained as context/sensitivity, not as the primary finite population.
- Negative, zero, and nonpositive values are absent in the canonical matrices used here.
- The low-tail screen in `analysis/results/qaqc_low_tail/` checks for unusually low but positive values without applying additional filtering.
- Calibration uncertainty can shift the pollution scale; the design-based subnetwork reproducibility result is conditional on the calibrated deployed network.

## Current Canonical QA/QC Counts

| city | source_frequency | valid_observation_count | missing_observation_pct | pm_min_ugm3 | pm_p01_ugm3 | pm_gt0_lt2_pct_of_valid | relative_low_observation_pct_of_valid | sensors_with_low_tail_review_flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dhaka | hourly | 263052 | 14.204 | 1.000 | 4.000 | 0.089 | 0.716 | 2 |
| Lucknow | hourly | 445689 | 28.341 | 1.000 | 4.000 | 0.158 | 0.171 | 1 |
| Chicago | official_daily | 73517 | 2.782 | 1.690 | 3.562 | 0.004 | 0.012 | 2 |

## Remaining Limitation

Full calibration-method details still depend on the deployment-team documentation and source publications. The manuscript should cite those sources and avoid implying that this revision independently validates instrument calibration.
