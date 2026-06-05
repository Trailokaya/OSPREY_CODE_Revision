# Phase 4 Summary — Chicago Selection-Strategy Comparison

- Master seed: `20260528`
- Inner SRSWOR draws per task: `10000`
- Stochastic strategies use `B'=50` outer selections: random, spatially balanced, k-means stratified.
- Partially deterministic strategies use `B'=20` outer selections: cluster-concentrated, circumferential, anti-cluster.
- Headline table: `aggregated/headline_numbers.csv`
- Strategy envelope: `aggregated/period_strategy_envelope.csv`
- Median required n for period MdAPE <= 5% is largely insensitive to strategy in Chicago: all strategies are `n=2` at N*=50 and N*=70, while anti-cluster increases to `n=3` at N*=30.
- At N*=50, MdAPE at n=10 ranges from `1.64%` for `Cluster-concentrated` to `2.26%` for `Anti-cluster`.
- At N*=50, random selection requires median n=`2`; cluster-concentrated selection requires median n=`2`.
- Verdict: strategy choice produces visible but small differences in Chicago period MdAPE curves. Cluster-concentrated finite populations are not worst for this deployed-network-mean estimand because they are internally homogeneous; spatially dispersed strategies expose slightly more cross-sensor heterogeneity.

## Median n for MdAPE <= 5%

- N*=30: Circumferential: 2, Cluster-concentrated: 2, Spatially balanced: 2, k-means stratified: 2, Random: 2, Anti-cluster: 3
- N*=50: Anti-cluster: 2, Circumferential: 2, Cluster-concentrated: 2, Spatially balanced: 2, k-means stratified: 2, Random: 2
- N*=70: Anti-cluster: 2, Circumferential: 2, Cluster-concentrated: 2, Spatially balanced: 2, k-means stratified: 2, Random: 2

## Median period MdAPE at n=10

- N*=30: Cluster-concentrated: 1.59%, Random: 1.60%, Circumferential: 1.62%, k-means stratified: 1.74%, Spatially balanced: 1.96%, Anti-cluster: 2.50%
- N*=50: Cluster-concentrated: 1.64%, Random: 1.74%, k-means stratified: 1.75%, Circumferential: 2.10%, Spatially balanced: 2.22%, Anti-cluster: 2.26%
- N*=70: Cluster-concentrated: 1.78%, k-means stratified: 1.92%, Random: 1.98%, Anti-cluster: 2.04%, Circumferential: 2.11%, Spatially balanced: 2.15%

## Main outputs

- N*=30 figure: `plots/phase4_chicago_selection_strategy_n30_period_mdape_seed20260528.pdf`
- N*=50 figure: `plots/phase4_chicago_selection_strategy_n50_period_mdape_seed20260528.pdf`
- N*=70 figure: `plots/phase4_chicago_selection_strategy_n70_period_mdape_seed20260528.pdf`
- Three-panel figure: `plots/phase4_chicago_selection_strategy_alln_period_mdape_seed20260528.pdf`
- Required-n figure: `plots/phase4_chicago_selection_strategy_required_n_seed20260528.pdf`

## Daily N*=50 strategy check

- Daily strategy outputs: `aggregated/daily_strategy_summary_n50.csv`, `aggregated/daily_strategy_envelope_n50.csv`, and `aggregated/daily_strategy_absolute_error_envelope_n50.csv`.
- At n=10, median daily subnetwork absolute error ranges from `0.190` µg/m³ for `Cluster-concentrated` to `0.260` µg/m³ for `Anti-cluster`.
- The selected N*=50 daily network mean differs from the full N=277 daily mean by `0.100` µg/m³ for `k-means stratified` to `0.306` µg/m³ for `Anti-cluster`.

## Daily N*=50 strategy check against full network

- Full-network-reference outputs: `aggregated/daily_strategy_full_reference_summary_n50.csv`, `aggregated/daily_strategy_full_reference_envelope_n50.csv`, and `aggregated/daily_strategy_full_reference_absolute_error_envelope_n50.csv`.
- Here the sampled n-sensor means are still drawn from each selected N*=50 strategy population, but daily error is computed against the full Chicago N=277 network mean.
- At n=10, median daily absolute error versus the full N=277 mean ranges from `0.233` µg/m³ for `k-means stratified` to `0.371` µg/m³ for `Anti-cluster`.
