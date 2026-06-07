# Dual-Reference Monte Carlo Summary

This output joins two reference targets side by side for the same N*=50 selected subsets and the same Monte Carlo sampling tasks.

- `selected_ref_*`: error against the selected N*=50 finite-population mean.
- `full_ref_*`: error against the full deployed-network mean, Chicago N=277 or Lucknow N=71.
- `*_delta_*`: full-reference metric minus selected-reference metric.

## n=10 Results

- Chicago, daily, Anti-cluster: selected-ref `2.85%` / `0.273` µg/m³; full-ref `4.08%` / `0.386` µg/m³; delta `0.88` pct-pt / `0.101` µg/m³.
- Chicago, daily, Circumferential: selected-ref `2.55%` / `0.240` µg/m³; full-ref `3.38%` / `0.316` µg/m³; delta `0.46` pct-pt / `0.048` µg/m³.
- Chicago, daily, Cluster-concentrated: selected-ref `2.11%` / `0.201` µg/m³; full-ref `3.52%` / `0.342` µg/m³; delta `1.06` pct-pt / `0.099` µg/m³.
- Chicago, daily, Random: selected-ref `2.39%` / `0.226` µg/m³; full-ref `2.62%` / `0.243` µg/m³; delta `0.09` pct-pt / `0.010` µg/m³.
- Chicago, daily, Spatially balanced: selected-ref `2.75%` / `0.264` µg/m³; full-ref `3.23%` / `0.301` µg/m³; delta `0.28` pct-pt / `0.031` µg/m³.
- Chicago, daily, k-means stratified: selected-ref `2.43%` / `0.235` µg/m³; full-ref `2.62%` / `0.243` µg/m³; delta `0.07` pct-pt / `0.007` µg/m³.
- Chicago, period, Anti-cluster: selected-ref `2.26%` / `0.224` µg/m³; full-ref `3.00%` / `0.317` µg/m³; delta `0.76` pct-pt / `0.095` µg/m³.
- Chicago, period, Circumferential: selected-ref `2.10%` / `0.209` µg/m³; full-ref `2.36%` / `0.250` µg/m³; delta `0.36` pct-pt / `0.048` µg/m³.
- Chicago, period, Cluster-concentrated: selected-ref `1.64%` / `0.173` µg/m³; full-ref `2.14%` / `0.226` µg/m³; delta `0.33` pct-pt / `0.043` µg/m³.
- Chicago, period, Random: selected-ref `1.74%` / `0.178` µg/m³; full-ref `1.91%` / `0.202` µg/m³; delta `0.07` pct-pt / `0.014` µg/m³.
- Chicago, period, Spatially balanced: selected-ref `2.22%` / `0.221` µg/m³; full-ref `2.69%` / `0.284` µg/m³; delta `0.41` pct-pt / `0.052` µg/m³.
- Chicago, period, k-means stratified: selected-ref `1.75%` / `0.178` µg/m³; full-ref `1.84%` / `0.195` µg/m³; delta `0.05` pct-pt / `0.011` µg/m³.
- Lucknow, daily, Random: selected-ref `4.29%` / `1.719` µg/m³; full-ref `4.51%` / `1.784` µg/m³; delta `0.07` pct-pt / `0.025` µg/m³.
- Lucknow, period, Random: selected-ref `5.44%` / `3.371` µg/m³; full-ref `5.60%` / `3.462` µg/m³; delta `0.09` pct-pt / `0.058` µg/m³.

## Retained Output Check

- Checks run: `66`
- Failed checks: `0`
- Warning checks: `0`
- Warning checks indicate optional compute-heavy draw-level files that are not needed for the retained manuscript-facing outputs.
