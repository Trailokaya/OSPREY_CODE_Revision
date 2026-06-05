# Phase 3 Summary — Lucknow Finite-Population Sensitivity

- Master seed: `20260528`
- Outer finite-population draws per N*: `100`
- Inner SRSWOR draws per task: `10000`
- Headline table: `aggregated/headline_numbers.csv`
- Period envelope: `aggregated/period_mdape_envelope.csv`
- At matched finite-population size, Lucknow N*=31 reaches period MdAPE <= 5% at `n=10`; Dhaka N=35 reaches the same threshold at `n=7`.
- At n=10, Lucknow N*=31 median period MdAPE is `4.91%`; Dhaka N=35 baseline is `3.89%`, a difference of `1.01` percentage points.
- Across n=2..30, the maximum absolute Lucknow N*=31 versus Dhaka N=35 median-curve difference is `3.55` percentage points.
- Verdict: matching finite-population size narrows the Lucknow/Dhaka comparison but does not make the curves identical. Lucknow remains modestly higher-error than Dhaka at common small-n values.

## Main outputs

- Lucknow N-sensitivity figure: `plots/phase3_lucknow_nsensitivity_period_mdape_seed20260528.pdf`
- Required-n figure: `plots/phase3_lucknow_nrequired_by_nstar_seed20260528.pdf`
- Dhaka-overlay figure: `plots/phase3_lucknow_downsampling_period_mdape_with_dhaka_seed20260528.pdf`
- Matched-size comparison figure: `plots/phase3_lucknow_n31_vs_dhaka_n35_period_mdape_seed20260528.pdf`

Daily MC implementation note: within each outer draw, random position matrices are reused for dates with the same valid-sensor count and sample size. This preserves uniform SRSWOR for each date while avoiding redundant random-number generation.
