# Figure / Table → Script → Data Traceability

Every figure and table in the final manuscript and SI is mapped to the script that
produces it and the data that script reads. The "paper-facing filename" is what the LaTeX `\includegraphics`
points to. Many scripts emit a different internal stem during a rerun; the retained paper-facing assets are
the renamed files under `paper/Manuscript_and_SI/Plots/`.

## Main text

| Fig | Paper-facing file | Canonical script | Internal stem | Key direct inputs | Verified |
|---|---|---|---|---|---|
| 1 | `three_city_sensor_network_reference_monitor_map.pdf` | `maps/scripts/build_manuscript_map_package.py` | `F1_sensor_network_reference_monitor_map` | `data/locations/*`, `data/geo/*` | re-run ✓ |
| 2a | `period_mdape_vs_sample_size.pdf` | `monte_carlo/scripts/plot_main_monte_carlo.py` | `F2A_period_mdape_common_n2_30` | `monte_carlo/results/runs/p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602/mc_summary/p0_baseline_summary.parquet` | re-run ✓ |
| 2b | `period_absolute_error_vs_sample_size.pdf` | `monte_carlo/scripts/plot_main_monte_carlo.py` | `F2B_period_absolute_error_common_n2_30` | same baseline run parquet | re-run ✓ |
| 3 | `daily_mdape_timeseries_with_valid_sensor_count.pdf` | `monte_carlo/scripts/plot_main_monte_carlo.py` | `F3_daily_mdape_timeseries_with_nstar` | same baseline run parquet | re-run ✓ |
| 4 | `three_city_placement_strategy_maps_n10.pdf` | `analysis/scripts/build_placement_design_analysis.py` | `placement_strategy_maps_n10` | `monte_carlo/plots/figure_data/{daily_error_timeseries_selected_n,period_error_curves}.csv`, `data/geo/*`, raw PM/locations via `run_main_monte_carlo.load_dataset` | re-run ✓ |

## Supporting Information

| SI | Paper-facing file | Canonical script | Key direct inputs | Verified |
|---|---|---|---|---|
| 1 | `chicago_pm25_lcs_aqs_daily_period_map.pdf` | `analysis/scripts/build_chicago_si1_pm25_reference_map.py` | `data/pm/Chicago_{LCS_corrected_daily,AQS_daily}_PM25.csv`, `data/locations/Chicago_*`, `data/geo/Chicago_*` | re-run ✓ |
| 2 | `three_city_empirical_variogram_binned_by_city.pdf` | `spatial/scripts/build_spatial_distance_correlation_analysis.py` | `data/pm/*_hourly_PM25.csv` (3 cities), `data/locations/*` | provenance ✓ |
| 3 | `three_city_cumulative_pairwise_distance.pdf` | `.../scripts/build_si_plot_consistency_package.py` | `data/locations/*`, `data/pm/*` | re-run ✓ |
| 4 | `three_city_daily_morans_i_qq_knn5.pdf` | `.../scripts/build_si_plot_consistency_package.py` | `data/locations/*`, `data/pm/*` | re-run ✓ |
| 5 | `three_city_hourly_morans_i_qq_knn5.pdf` | `.../scripts/build_si_plot_consistency_package.py` | `data/locations/*`, `data/pm/*` | re-run ✓ |
| 6 | `three_city_RSE_normal_daily_sensor_requirement.pdf` | `analysis/scripts/build_estimator_diagnostics.py` | `data/pm/*`, `data/locations/*` | re-run ✓ |
| 7 | `three_city_RSE_lognormal_daily_sensor_requirement.pdf` | `analysis/scripts/build_estimator_diagnostics.py` | `data/pm/*`, `data/locations/*` | re-run ✓ |
| 8 | `three_city_RSE_exceedance_curves.pdf` | `analysis/scripts/build_estimator_diagnostics.py` | `data/pm/*`, `data/locations/*` | re-run ✓ |
| 9 | `three_city_daily_estimator_mean_sd_comparison.pdf` | `analysis/scripts/build_estimator_comparison.py` | `data/pm/*`, `data/locations/*` (via `build_estimator_diagnostics.load_dataset`) | provenance ✓ |
| 10 | `three_city_lognormal_relative_bias_by_n.pdf` | `analysis/scripts/build_estimator_comparison.py` | `data/pm/*`, `data/locations/*` | provenance ✓ |
| 11 | `three_city_period_sensor_means_bonferroni_ci.pdf` | `analysis/scripts/build_estimator_diagnostics.py` | `analysis/results/estimator_diagnostics/si_f11_sensor_period_ci.csv` (also recomputed from raw) | re-run ✓ |
| 12 | `estimand_schematic.pdf` | `.../scripts/build_reviewer_requested_figures.py` | `data/locations/Dhaka_sensor_locations.csv` (point layout only; field is synthetic) | re-run ✓ |
| 13 | `daily_distributions_representative_days.pdf` | `.../scripts/build_reviewer_requested_figures.py` | `data/pm/{Dhaka_hourly,Lucknow_hourly,Chicago_LCS_corrected_daily}_PM25.csv` | re-run ✓ |
| 14 | `period_error_percentile_bands.pdf` | `.../scripts/build_reviewer_requested_figures.py` | `monte_carlo/plots/figure_data/period_best_worst_error_by_city_n.csv` | re-run ✓ |
| 15 | `chicago_network_with_reference_monitors.pdf` | `maps/scripts/build_exploratory_maps.py` (`chicago_aqs_lcs_combined`) | `data/geo/Chicago_*`, `data/locations/Chicago_{AQS,LCS_corrected,LCS_raw}` | re-run ✓ |
| 16 | `regional_locator.pdf` | `maps/scripts/build_manuscript_map_package.py` (`build_locator_map`) | none (hardcoded city coords; Natural Earth via cartopy) | re-run ✓ |
| 17 | `finite_population_size_sensitivity_chicago.pdf` + `finite_population_size_sensitivity_lucknow_vs_dhaka.pdf` | `monte_carlo/scripts/run_finite_population_experiment.py` (`--phase 2` / `--phase 3`) | phase envelope CSVs + `data/pm/*` (full Monte Carlo) | provenance ✓ (compute-heavy) |
| 18 | `reference_target_sensitivity_selected_vs_full.pdf` + `reference_target_sensitivity_delta.pdf` | `analysis/scripts/build_dual_reference_monte_carlo_summary.py` | phase4 draw tables + phase3 `selected_reference_draw_summaries_n50.parquet` + reference_target_sensitivity `*.parquet` | re-run ✓ |
| 19 | `seed_stability_phase4_strategy_mdape_n10.pdf` | `analysis/scripts/run_finite_population_seed_stability.py --plot-only` | `analysis/results/finite_population_experiments/seed_stability_2026-05-29/aggregated/seed_level_metrics.csv` | re-run ✓ |
| 20 | `three_city_mdape_vs_cv_slope.pdf` | `analysis/scripts/build_mdape_vs_cv_slope.py` | canonical June 2 Monte Carlo summary + `preprocessed/*_daily_sensor_means.parquet` | re-run ✓ |

## Table of Contents Graphic

| Asset | Paper-facing file | Source | Key direct inputs | Verified |
|---|---|---|---|---|
| TOC | `TOC_v2.pdf` + `TOC_v2.png` | `paper/Manuscript_and_SI/Plots/TOC/build_toc_graphic_v2.py` | `monte_carlo/plots/figure_data/period_error_curves.csv`; `analysis/results/three_city_comparative_analysis/comparative_sensor_level_summary.csv` | re-run ✓ |

## Shared helpers (imported, not standalone outputs)

| File | Used by |
|---|---|
| `analysis/src/plot_style.py` | every figure script except `build_reviewer_requested_figures.py` |
| `maps/scripts/build_network_maps.py` | Fig 1, Fig 4, SI 1, SI 15, consistency package |
| `monte_carlo/scripts/run_main_monte_carlo.py` | Fig 4, SI 17, SI 19 (provides `DATASETS`, `load_dataset`) |
| `monte_carlo/scripts/run_finite_population_experiment.py` | SI 17, and imported by seed-stability + reference-target |
| `monte_carlo/scripts/run_selection_strategy_experiment.py` | imported by seed-stability + reference-target (phase-4 strategies) |
| `analysis/scripts/build_estimator_diagnostics.py` | imported by `build_estimator_comparison.py` and `build_distribution_diagnostics.py` |
| `analysis/scripts/build_three_city_comparative_analysis.py` | imported by `build_spatial_distance_correlation_analysis.py` |
| `analysis/scripts/build_reference_target_sensitivity.py` | upstream prerequisite that produces SI 18's `full_reference_draw_summaries_n50.parquet` |

## Tables

| Table | Backing CSV | Producing script |
|---|---|---|
| `ci.tex` | `analysis/results/estimator_diagnostics/qce_daily_summary.csv` | `build_estimator_diagnostics.py` |
| `shapiro.tex` | `analysis/results/distribution_diagnostics/distribution_daily_diagnostics.csv` | `build_distribution_diagnostics.py` |
| `spatial_support.tex` | `analysis/results/three_city_comparative_analysis/comparative_spatial_support_summary.csv` | `build_three_city_comparative_analysis.py` |

The `.tex` files themselves are hand-authored (no generator); numbers are transcribed from these CSVs.
