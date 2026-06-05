# Phase 5 Summary — MdAPE-vs-CV Slope

- Master seed label: `20260528`
- Analysis uses existing baseline Monte Carlo daily MdAPE outputs; no new outer finite-population draw is used.
- X-axis: daily cross-sensor coefficient of variation, computed as 100 × SD / mean across valid sensors.
- Y-axis: daily MdAPE at n=10 from the baseline 10,000-draw SRSWOR Monte Carlo.

## n=10 slope estimates

| City | slope beta | SE | 95% CI | R² | days |
|---|---:|---:|---:|---:|---:|
| Dhaka | 0.2025 | 0.0020 | 0.1986 to 0.2065 | 0.965 | 365 |
| Lucknow | 0.1557 | 0.0016 | 0.1526 to 0.1588 | 0.964 | 365 |
| Chicago | 0.1085 | 0.0051 | 0.0985 to 0.1185 | 0.630 | 272 |

Verdict: Chicago's slope is smaller than the average South Asian slope, so the same increase in cross-sensor CV translates into less subnetwork error in Chicago.

Use the simple interpretation only: the slope is the rate at which daily cross-sensor heterogeneity translates into subnetwork error. Do not present this as a formal variance-decomposition mechanism.

## Main outputs

- Figure: `plots/three_city_mdape_vs_cv_slope.pdf`
- Slope table: `aggregated/slope_summary.csv`
- Headline table: `aggregated/headline_numbers.csv`
