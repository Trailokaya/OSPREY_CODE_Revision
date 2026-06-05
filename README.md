# OSPREY Code Revision

Code and retained analysis outputs for:

*How many sensors are needed to estimate daily and annual reference-network mean concentrations?*

This repository is the cleaned review-facing code package. It contains the runnable analysis scripts, direct
input data, generated plots, retained result tables, and final manuscript/SI figure assets needed to reproduce
the manuscript-facing outputs. The original working tree was about 46 GB; this GitHub-ready package is about
552 MB.

For figure and table provenance, see `FIGURE_TO_SCRIPT_MAP.md`.

## Contents

```
analysis/
  src/plot_style.py                 # shared plotting style/helper
  scripts/                          # analysis and figure-generation scripts
  plots/                            # retained generated plots
  results/                          # retained summary tables and compact provenance
monte_carlo/
  scripts/                          # Monte Carlo engine and plotting scripts
  results/runs/p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602/
                                    # canonical Monte Carlo run used by main figures and SI checks
  plots/figure_data/                # figure-data CSVs used by downstream plots
spatial/
  scripts/                          # spatial diagnostics
  results/                          # spatial diagnostic outputs
missingness/
  scripts/                          # missingness and completeness diagnostics
  results/                          # retained missingness/completeness outputs
  plots/                            # retained missingness plots
maps/
  scripts/                          # network and locator map builders
data/
  pm/                               # PM2.5 time series for Dhaka, Lucknow, and Chicago
  locations/                        # sensor and reference-monitor coordinates
  geo/                              # city/district GeoJSON boundaries
manuscript/overleaf_projects/01_manuscript_revision_tracked_working/
  Plots/Supporting_Information/scripts/
                                    # consolidated SI figure builders used by the manuscript tree
paper/
  Manuscript_and_SI/                # final manuscript/SI LaTeX tree and figure assets
```

## Environment

Python 3.10+ is recommended.

```bash
pip install -r requirements.txt
```

Key packages are `numpy`, `pandas`, `pyarrow`, `scipy`, `matplotlib`, `cartopy`, and `openpyxl`.
`cartopy` is needed for the locator map and may download Natural Earth basemap layers on first use. The
other figure builders run offline once dependencies are installed.

## Reproduce Main Figures

Run from the repository root:

```bash
python monte_carlo/scripts/plot_main_monte_carlo.py
python analysis/scripts/build_placement_design_analysis.py
python maps/scripts/build_manuscript_map_package.py
```

Ordering note: `build_placement_design_analysis.py` reads `monte_carlo/plots/figure_data/*.csv`, so run
`plot_main_monte_carlo.py` first when regenerating from a fresh checkout.

## Reproduce SI Figures And Diagnostics

```bash
python maps/scripts/build_exploratory_maps.py
python analysis/scripts/build_chicago_si1_pm25_reference_map.py
python spatial/scripts/build_spatial_distance_correlation_analysis.py

python analysis/scripts/build_estimator_diagnostics.py
python analysis/scripts/build_estimator_comparison.py
python analysis/scripts/build_distribution_diagnostics.py
python analysis/scripts/build_three_city_comparative_analysis.py
python analysis/scripts/build_mdape_vs_cv_slope.py

python analysis/scripts/build_completeness_standardized.py
python analysis/scripts/build_missingness_followup_tests.py
python analysis/scripts/build_qaqc_low_tail_recommendations.py
python analysis/scripts/build_chicago_sensitivity.py
python analysis/scripts/build_temporal_diagnostics.py
python analysis/scripts/build_regression_clustering_diagnostics.py
python spatial/scripts/build_spatial_completeness_sensitivity.py
python missingness/scripts/run_missingness_analysis.py
```

The consolidated SI builders should be run after the estimator and spatial steps above:

```bash
python manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/scripts/build_si_plot_consistency_package.py
python manuscript/overleaf_projects/01_manuscript_revision_tracked_working/Plots/Supporting_Information/scripts/build_reviewer_requested_figures.py
```

## Finite-Population Outputs

The finite-population phase runs are compute-heavy because they use 10,000 inner Monte Carlo draws. This repo
keeps the phase configs, seed files, compact summaries, final plots, and compact selected/full-reference
tables needed by the manuscript-facing outputs. The largest draw-level aggregate files are not included in the
GitHub repository because they exceed GitHub's normal-file size limit and Git LFS was not used here.

The retained plot-only and compact-reference steps can be run with:

```bash
python analysis/scripts/build_dual_reference_monte_carlo_and_audit.py
python analysis/scripts/run_finite_population_seed_stability.py --plot-only
```

Full phase recomputation, including SI 17, should be run from the phase scripts if the omitted draw-level
files are needed.

## Tables

The SI tables in `paper/Manuscript_and_SI/tables/` are hand-authored LaTeX files. Their backing CSVs are:

| Table | Backing CSV | Script |
|---|---|---|
| `ci.tex` | `analysis/results/estimator_diagnostics/qce_daily_summary.csv` | `analysis/scripts/build_estimator_diagnostics.py` |
| `shapiro.tex` | `analysis/results/distribution_diagnostics/distribution_pvalue_bin_counts.csv` | `analysis/scripts/build_distribution_diagnostics.py` |
| `spatial_support.tex` | `analysis/results/three_city_comparative_analysis/comparative_spatial_support_summary.csv` | `analysis/scripts/build_three_city_comparative_analysis.py` |

## Notes

- The canonical Monte Carlo run is `p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602`.
- Script paths are package-relative; they do not depend on the original local working-tree path.
- Audit-only validation scripts and cleanup reports are not included in this GitHub package.
