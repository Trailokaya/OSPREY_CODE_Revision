# Lucknow Madhwal Monte Carlo Comparison

Source run: `monte_carlo/results/runs/p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602`.

## Scope

- This compares the canonical manuscript Lucknow matrix with the Madhwal validation matrix after both were registered in the same Monte Carlo runner.
- The two files are not identical study windows; compare this as a dataset-sensitivity check, not as a same-period replacement claim.
- Both datasets use the same 71 canonical Lucknow sensor IDs and locations.

## Headline

- Canonical Lucknow period reference mean: `61.802` µg/m³.
- Madhwal period reference mean: `51.468` µg/m³.
- At `n=10`, canonical period MdAPE is `5.641%` and Madhwal period MdAPE is `2.468%`.
- At `n=10`, canonical period median absolute error is `3.486` µg/m³ and Madhwal is `1.270` µg/m³.
- The Madhwal-minus-canonical period MdAPE difference at `n=10` is `-3.173` percentage points.

## Daily Coverage

- Canonical daily MC evaluated `365` days from `2022-04-01` to `2023-03-31`.
- Madhwal daily MC evaluated `349` days from `2021-12-17` to `2022-11-30`.

## Outputs

- `lucknow_madhwal_mc_headline_summary.csv`
- `lucknow_madhwal_vs_canonical_period_mc_comparison.csv`
- `lucknow_madhwal_vs_canonical_daily_n10_mc.csv`
- `lucknow_madhwal_vs_canonical_period_mc.pdf/png`
- `lucknow_madhwal_vs_canonical_daily_n10_mc.pdf/png`
