# Phase 2 Summary — Chicago Finite-Population Sensitivity

- Master seed: `20260528`
- Outer finite-population draws per N*: `100`
- Inner SRSWOR draws per task: `10000`
- Headline table: `aggregated/headline_numbers.csv`
- Period envelope: `aggregated/period_mdape_envelope.csv`
- Across Chicago N* values `[30, 40, 50, 70, 100, 150, 200, 277]`, the median required n for period MdAPE <= 5% is `2` to `2` sensors.
- Period MdAPE at n=10 ranges from `1.59%` to `1.93%` across median N* curves.
- Maximum absolute median-curve deviation from the original N=277 baseline is `1.17` percentage points; the maximum 5–95% outer-draw band width is `2.65` percentage points.
- Verdict: the Chicago study-period MdAPE curve is robust across the tested random finite-population sizes. Smaller N* values widen the outer-draw uncertainty band, but the sensor-count conclusion does not materially change.

## Main outputs

- N-sensitivity figure: `plots/phase2_chicago_nsensitivity_period_mdape_seed20260528.pdf`
- Required-n figure: `plots/phase2_chicago_nrequired_by_nstar_seed20260528.pdf`

Daily MC implementation note: within each outer draw, random position matrices are reused for dates with the same valid-sensor count and sample size. This preserves uniform SRSWOR for each date while avoiding redundant random-number generation.
