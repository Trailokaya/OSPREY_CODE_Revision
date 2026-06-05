# SI Figure 1: continuous-field concept and Chicago point-sample context

## Purpose

This figure is designed to make the finite-population estimand explicit. The upper row shows a hypothetical continuous PM2.5 field, then the finite point samples observed by a deployed network, then one subnetwork drawn from that finite population. The lower row shows the analogous Chicago data example: actual Jan 1, 2026 samples, actual shared-period mean samples, and the network-mean summaries available from those samples.

## Date-window audit

- Chicago LCS daily corrected data span 2025-09-01 to 2026-05-31 (273 daily rows) in the current canonical file.
- Chicago AQS daily data span 2025-09-01 to 2026-04-30 (242 daily rows) in the current canonical file.
- The lower-row period panel restricts both networks to the shared valid-date overlap: 2025-09-01 to 2026-03-31 (212 days). This avoids comparing an LCS nine-month mean with an AQS shorter-window mean.
- January 1, 2026 is available in both LCS and AQS daily files.

## Summary

| panel | network | n | mean | median | min | max | start_date | end_date | n_dates_available_for_network |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Conceptual field | Full deployed LCS sample | 277 | 9.86 | 9.18 | 6.91 | 15.4 | not applicable | not applicable | 0 |
| Conceptual field | One n=10 subnetwork | 10 | 10.8 | 10.3 | 7.77 | 15.4 | not applicable | not applicable | 0 |
| Jan 1, 2026 | Chicago LCS | 272 | 5.93 | 5.79 | 3.74 | 11.2 | 2026-01-01 | 2026-01-01 | 1 |
| Jan 1, 2026 | EPA AQS | 10 | 5.21 | 5.39 | 4.05 | 6.67 | 2026-01-01 | 2026-01-01 | 1 |
| Shared period | Chicago LCS | 277 | 10.8 | 10.8 | 4.97 | 19.2 | 2025-09-01 | 2026-03-31 | 212 |
| Shared period | EPA AQS | 10 | 9.3 | 9.25 | 7.77 | 10.3 | 2025-09-01 | 2026-03-31 | 212 |

## Files

- Figure PDF: `manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_1/si1_continuous_field_sampling_chicago.pdf`
- Figure PNG: `manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/Figure_SI_1/si1_continuous_field_sampling_chicago.png`
- Actual data: `analysis/results/si1_continuous_field_sampling/si1_chicago_actual_daily_period_values.csv`
- Concept data: `analysis/results/si1_continuous_field_sampling/si1_conceptual_sampling_sensor_values.csv`
- Summary: `analysis/results/si1_continuous_field_sampling/si1_continuous_field_sampling_summary.csv`
