# Anomaly Scorecard Outputs

These retained outputs back the diagnostic-only anomaly scorecard described in SI Section S1.

Files:

| File | Role |
|---|---|
| `dhaka_scorecard.csv` | Per-sensor Dhaka residual diagnostics: median residual, MAD, spike rate, changepoint count, peer correlation, and flags. |
| `lucknow_scorecard.csv` | Per-sensor Lucknow residual diagnostics with the same fields. |
| `changepoints_dhaka.pdf/png` | Dhaka changepoint diagnostic plot. |
| `changepoints_lucknow.pdf/png` | Lucknow changepoint diagnostic plot. |

The scorecard is diagnostic only. It was not used as an additional exclusion rule in the main Monte Carlo
analysis. The retained CSVs reproduce the SI counts: no sensors with peer correlation below 0.5, 15 Dhaka
sensors with spike-rate flags, and 38 Lucknow sensors with spike-rate flags.
