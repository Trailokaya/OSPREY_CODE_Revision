# Missingness Results

This folder contains retained tabular outputs from `../scripts/run_missingness_analysis.py`.

The retained result set uses `10,000` bootstrap iterations, `10,000` M5 Monte Carlo iterations, master seed
`20260522`, and the shared `600` DPI plot style. These files back the missingness, completeness, and
completeness-sensitivity diagnostics cited in the manuscript/SI package.

## Files

| file | contents |
|---|---|
| `missingness_results_bundle.json` | JSON bundle with run metadata and compact records for all analysis blocks. |
| `M1_M2_missingness_correlations.csv` | Pearson/Spearman correlations and bootstrap confidence intervals for concentration/variability vs missingness. |
| `M3_seasonal_missingness.csv` | Season-level missingness percentages and median sensor uptime. |
| `M3_seasonal_tests.csv` | Winter-vs-nonwinter KS tests and seasonal chi-square tests. |
| `M4_gap_lengths.csv` | One row per continuous missing-data gap by network and sensor. |
| `M4_gap_summary.csv` | Per-network gap count, quantiles, maximum gap, and gap-duration category percentages. |
| `M4_long_gaps_gt_30d.csv` | Long gaps exceeding 30 days, with network mean during each gap. |
| `M5_completeness_sensitivity_summary.csv` | Per-network and per-scenario retained sensors and required sample sizes. |
| `M5_completeness_sensitivity_curves.csv` | Monte Carlo MdAPE curves used to build M5 plots. |
| `M6_morans_i_completeness_sensitivity.csv` | Moran's I sensitivity results by network, filter, and distance band. |

## Current Run Parameters

| parameter | value |
|---|---:|
| bootstrap iterations | 10000 |
| period Monte Carlo iterations | 10000 |
| daily Monte Carlo iterations | 10000 |
| M5 parallel workers | 5 in retained output metadata |
| master seed | 20260522 |
| Moran p-value method | analytical normal approximation |

## Reproduction

Run from the repository root:

```bash
python missingness/scripts/run_missingness_analysis.py
```
