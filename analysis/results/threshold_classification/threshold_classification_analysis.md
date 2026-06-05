# Threshold Classification Sensitivity

Generated: `2026-06-05T18:52:20`

## Purpose

This analysis addresses reviewer-facing questions about whether subnetwork means preserve threshold/exceedance classifications. It is **not** a formal regulatory-compliance analysis. It is a decision-support sensitivity layered on top of the reference-network mean reproducibility estimand.

## Important Caveat

The EPA and WHO thresholds used here have formal averaging and design-value forms. This script asks a narrower finite-population question: if the deployed reference-network mean is treated as the classification reference, how often does an n-sensor random subnetwork produce the same side-of-threshold classification?

## Inputs

| dataset_key                          | city    | n_sensors | n_days | period_reference_mean_ugm3 | first_date | last_date  |
| ------------------------------------ | ------- | --------- | ------ | -------------------------- | ---------- | ---------- |
| chicago_lcs_corrected_no_collocation | Chicago | 277       | 273    | 10.253                     | 2025-09-01 | 2026-05-31 |
| dhaka_lcs                            | Dhaka   | 35        | 365    | 55.182                     | 2022-04-01 | 2023-03-31 |
| lucknow_lcs                          | Lucknow | 71        | 365    | 60.818                     | 2022-04-01 | 2023-03-31 |

## Daily Classification Snapshot

Rows below show selected daily thresholds and selected n values. Full data are in `daily_threshold_classification_summary.csv` and `daily_threshold_classification_by_day.csv`.

| city    | threshold_label     | threshold_ugm3 | n  | truth_prevalence | misclassification_rate | false_positive_rate | false_negative_rate |
| ------- | ------------------- | -------------- | -- | ---------------- | ---------------------- | ------------------- | ------------------- |
| Chicago | WHO 24h AQG         | 15.000         | 5  | 0.188            | 0.017                  | 0.005               | 0.070               |
| Chicago | WHO 24h AQG         | 15.000         | 10 | 0.188            | 0.012                  | 0.003               | 0.049               |
| Chicago | WHO 24h AQG         | 15.000         | 20 | 0.188            | 0.008                  | 0.003               | 0.034               |
| Chicago | EPA 24h NAAQS level | 35.000         | 5  | 0.000            | 0.000                  | 0.000               |                     |
| Chicago | EPA 24h NAAQS level | 35.000         | 10 | 0.000            | 0.000                  | 0.000               |                     |
| Chicago | EPA 24h NAAQS level | 35.000         | 20 | 0.000            | 0.000                  | 0.000               |                     |
| Dhaka   | WHO 24h AQG         | 15.000         | 5  | 0.866            | 0.042                  | 0.144               | 0.026               |
| Dhaka   | WHO 24h AQG         | 15.000         | 10 | 0.866            | 0.029                  | 0.107               | 0.016               |
| Dhaka   | WHO 24h AQG         | 15.000         | 20 | 0.858            | 0.016                  | 0.058               | 0.009               |
| Dhaka   | EPA 24h NAAQS level | 35.000         | 5  | 0.507            | 0.038                  | 0.033               | 0.043               |
| Dhaka   | EPA 24h NAAQS level | 35.000         | 10 | 0.507            | 0.025                  | 0.021               | 0.029               |
| Dhaka   | EPA 24h NAAQS level | 35.000         | 20 | 0.525            | 0.015                  | 0.011               | 0.019               |
| Lucknow | WHO 24h AQG         | 15.000         | 5  | 0.885            | 0.024                  | 0.074               | 0.018               |
| Lucknow | WHO 24h AQG         | 15.000         | 10 | 0.885            | 0.017                  | 0.055               | 0.012               |
| Lucknow | WHO 24h AQG         | 15.000         | 20 | 0.885            | 0.012                  | 0.040               | 0.009               |
| Lucknow | EPA 24h NAAQS level | 35.000         | 5  | 0.578            | 0.036                  | 0.031               | 0.040               |
| Lucknow | EPA 24h NAAQS level | 35.000         | 10 | 0.578            | 0.024                  | 0.019               | 0.028               |
| Lucknow | EPA 24h NAAQS level | 35.000         | 20 | 0.578            | 0.015                  | 0.010               | 0.019               |

## Study-Period Classification Snapshot

Rows below show selected study-period thresholds and selected n values. Full data are in `period_threshold_classification_summary.csv`.

| city    | threshold_label        | threshold_ugm3 | n  | reference_mean_ugm3 | truth_exceeds | misclassification_rate | false_positive_rate | false_negative_rate |
| ------- | ---------------------- | -------------- | -- | ------------------- | ------------- | ---------------------- | ------------------- | ------------------- |
| Chicago | WHO annual AQG         | 5.000          | 5  | 10.253              | True          | 0.000                  |                     | 0.000               |
| Chicago | WHO annual AQG         | 5.000          | 10 | 10.253              | True          | 0.000                  |                     | 0.000               |
| Chicago | WHO annual AQG         | 5.000          | 20 | 10.253              | True          | 0.000                  |                     | 0.000               |
| Chicago | EPA annual NAAQS level | 9.000          | 5  | 10.253              | True          | 0.005                  |                     | 0.005               |
| Chicago | EPA annual NAAQS level | 9.000          | 10 | 10.253              | True          | 0.000                  |                     | 0.000               |
| Chicago | EPA annual NAAQS level | 9.000          | 20 | 10.253              | True          | 0.000                  |                     | 0.000               |
| Dhaka   | WHO annual AQG         | 5.000          | 5  | 55.182              | True          | 0.000                  |                     | 0.000               |
| Dhaka   | WHO annual AQG         | 5.000          | 10 | 55.182              | True          | 0.000                  |                     | 0.000               |
| Dhaka   | WHO annual AQG         | 5.000          | 20 | 55.182              | True          | 0.000                  |                     | 0.000               |
| Dhaka   | EPA annual NAAQS level | 9.000          | 5  | 55.182              | True          | 0.000                  |                     | 0.000               |
| Dhaka   | EPA annual NAAQS level | 9.000          | 10 | 55.182              | True          | 0.000                  |                     | 0.000               |
| Dhaka   | EPA annual NAAQS level | 9.000          | 20 | 55.182              | True          | 0.000                  |                     | 0.000               |
| Lucknow | WHO annual AQG         | 5.000          | 5  | 60.818              | True          | 0.000                  |                     | 0.000               |
| Lucknow | WHO annual AQG         | 5.000          | 10 | 60.818              | True          | 0.000                  |                     | 0.000               |
| Lucknow | WHO annual AQG         | 5.000          | 20 | 60.818              | True          | 0.000                  |                     | 0.000               |
| Lucknow | EPA annual NAAQS level | 9.000          | 5  | 60.818              | True          | 0.000                  |                     | 0.000               |
| Lucknow | EPA annual NAAQS level | 9.000          | 10 | 60.818              | True          | 0.000                  |                     | 0.000               |
| Lucknow | EPA annual NAAQS level | 9.000          | 20 | 60.818              | True          | 0.000                  |                     | 0.000               |

## Near-Threshold Sensitivity

`daily_near_threshold_classification_summary.csv` restricts the calculation to days where the reference-network mean is within ±1, ±2, or ±5 µg/m³ of a threshold. These rows are important because most classification disagreement happens near threshold boundaries.

## Outputs

- `classification_thresholds.csv`
- `dataset_inventory.csv`
- `daily_threshold_classification_summary.csv`
- `daily_threshold_classification_by_day.csv`
- `daily_near_threshold_classification_summary.csv`
- `period_threshold_classification_summary.csv`
- `threshold_classification_metadata.json`
- `analysis/plots/threshold_classification/daily_threshold_classification_misclassification.*`
- `analysis/plots/threshold_classification/period_threshold_classification_misclassification.*`
- `analysis/plots/threshold_classification/daily_near_threshold_classification_misclassification_margin2.*`

## Interpretation Rule

Use this analysis only if the manuscript keeps any health-guideline or threshold-classification claims. If the revised paper avoids those claims, this output is better kept as internal/SI evidence rather than a main-text result.
