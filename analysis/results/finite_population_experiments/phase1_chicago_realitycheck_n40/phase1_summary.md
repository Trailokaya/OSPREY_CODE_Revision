# Phase 1 Summary — Chicago N*=40 Reality Check

- Master seed: `20260528`
- Outer finite-population draws: `50`
- Inner SRSWOR draws per task: `10000`
- Headline n for period MdAPE <= 5%: mean `2.04` ± `0.20` sensors; median `2.0`.
- Period MdAPE at n=10: mean `1.93%` ± `0.64` percentage points.
- Maximum absolute median-curve deviation from the N=277 baseline across n=2..30: `0.61` percentage points; at n=10: `0.24` percentage points.
- Verdict: Chicago-at-N*=40 is close to the original N=277 curve.

## Main outputs

- Period figure: `plots/phase1_chicago_realitycheck_n40_period_mdape_seed20260528.pdf`
- Daily figure: `plots/phase1_chicago_realitycheck_n40_daily_mdape_seed20260528.pdf`
- Headline table: `aggregated/headline_numbers.csv`

## Caveat

The conclusion could change if the outer finite-population draw count is increased substantially or if a non-random spatial selection rule is used. That is the role of Phases 2–4.

Daily MC implementation note: within each outer draw, random position matrices are reused for dates with the same valid-sensor count and sample size. This preserves uniform SRSWOR for each date while avoiding redundant random-number generation.
