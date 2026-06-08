# Requirements And Final Environment Check

Date: 2026-06-07; updated 2026-06-08

## Scope

This check verifies the Python package requirements, current system environment, and a clean install/import run for the release-facing code package. It is focused on environment reproducibility and script importability; manuscript figure/value reproducibility is tracked separately in `README.md` and `FIGURE_TO_SCRIPT_MAP.md`.

## Current System

| Item | Value |
|---|---|
| macOS | 26.5.1, build 25F80 |
| Kernel | Darwin 25.5.0, arm64 |
| Python | 3.14.2 |
| pip | 25.3, `/opt/homebrew/lib/python3.14/site-packages/pip` |

## Actual Script Imports

The repository contains 42 Python files. Direct third-party imports found in those scripts are:

| Package | Covered by `requirements.txt` | Notes |
|---|---|---|
| `numpy` | yes | numerical arrays and Monte Carlo calculations |
| `pandas` | yes | tabular data and CSV/parquet IO |
| `pyarrow` | yes | parquet read/write support |
| `scipy` | yes | statistical tests and distributions |
| `matplotlib` | yes | plots and figure export |
| `cartopy` | yes | regional locator map |
| `shapely` | yes | geometry operations in SI sampling figure support |

`openpyxl`, the Jupyter packages, and `tzdata` are retained for spreadsheet IO, notebook review/execution, and timezone support. They are not direct imports in the main scripts but are appropriate environment dependencies.

## Requirement Update

Added `shapely>=2.0` to `requirements.txt` because `analysis/scripts/build_si1_continuous_field_sampling_figure.py` imports `shapely` directly. Although `cartopy` often installs it transitively, direct imports should be explicit.

## Current System Package Versions

| Package | Version |
|---|---|
| `numpy` | 2.4.5 |
| `pandas` | 3.0.3 |
| `pyarrow` | 24.0.0 |
| `scipy` | 1.17.1 |
| `openpyxl` | 3.1.5 |
| `matplotlib` | 3.10.9 |
| `cartopy` | 0.25.0 |
| `shapely` | 2.1.2 |
| `jupyterlab` | 4.5.7 |
| `notebook` | 7.5.6 |
| `ipykernel` | 7.1.0 |
| `nbformat` | 5.10.4 |
| `nbconvert` | 7.17.1 |
| `tzdata` | 2026.2 |

Current global `pip check` reports unrelated conflicts from installed packages that are not used by this repository (`tensorflow`, `catboost`, `seaborn-image`, and `torchvision`). The clean environment check below is therefore the relevant package-consistency test for this release package.

## Clean Environment Check

A temporary virtual environment was created at `/private/tmp/osprey_req_check_20260607` using Python 3.14.2.

Commands run:

```bash
python3 -m venv /private/tmp/osprey_req_check_20260607
/private/tmp/osprey_req_check_20260607/bin/python -m pip install --upgrade pip
/private/tmp/osprey_req_check_20260607/bin/python -m pip install -r requirements.txt
/private/tmp/osprey_req_check_20260607/bin/python -m pip check
find analysis maps missingness monte_carlo spatial manuscript paper -name '*.py' -type f -print0 | sort -z | xargs -0 /private/tmp/osprey_req_check_20260607/bin/python -m py_compile
```

Results:

| Check | Result |
|---|---|
| `pip install -r requirements.txt` in clean venv | pass |
| Import all listed packages in clean venv | pass |
| `pip check` in clean venv | pass, no broken requirements |
| Compile all repository Python files in clean venv | pass |

Clean venv package versions:

| Package | Version |
|---|---|
| `numpy` | 2.4.6 |
| `pandas` | 3.0.3 |
| `pyarrow` | 24.0.0 |
| `scipy` | 1.17.1 |
| `openpyxl` | 3.1.5 |
| `matplotlib` | 3.10.9 |
| `cartopy` | 0.25.0 |
| `shapely` | 2.1.2 |
| `jupyter` | 1.1.1 |
| `jupyterlab` | 4.5.8 |
| `notebook` | 7.5.7 |
| `ipykernel` | 7.2.0 |
| `nbformat` | 5.10.4 |
| `nbconvert` | 7.17.1 |
| `tzdata` | 2026.2 |

## Conclusion

`requirements.txt` now covers the repository's direct third-party Python imports. A clean Python 3.14.2 virtual environment can install the requirements, import the required packages, pass dependency consistency checks, and compile all repository Python scripts.

## Final Pre-Push Reruns

After the release-summary filenames were normalized, the affected builders were run again in the clean virtual environment:

```bash
/private/tmp/osprey_req_check_20260607/bin/python analysis/scripts/build_dual_reference_monte_carlo_summary.py
/private/tmp/osprey_req_check_20260607/bin/python analysis/scripts/build_missingness_deep_dive.py
/private/tmp/osprey_req_check_20260607/bin/python spatial/scripts/build_spatial_distance_correlation_summary.py
/private/tmp/osprey_req_check_20260607/bin/python spatial/scripts/build_spatial_completeness_sensitivity.py
```

Results:

| Check | Result |
|---|---|
| Dual-reference Monte Carlo summary builder | pass |
| Missingness deep-dive summary builder | pass |
| Spatial distance-correlation summary builder | pass |
| Spatial completeness-sensitivity builder | pass |
| Paper plot-reference coverage | pass: 28 LaTeX plot references, 28 retained paper PDFs, no missing or extra paper PDFs |
| Paper PNG companion coverage | pass: 28 retained paper PDFs, 28 same-basename PNG companions, all PNG density metadata at 600 DPI |
| Strict wording scan | pass: only the requested acknowledgement text in `README.md` remains |

## June 8 Targeted Rerun And Markdown Check

After the retained estimator and missingness diagnostics were touched up, the affected scripts were rerun with
the project scientific Python environment at `../Manuscript Revision/.venv/bin/python`.

Commands run:

```bash
../Manuscript\ Revision/.venv/bin/python analysis/scripts/build_estimator_diagnostics.py --jobs 1
../Manuscript\ Revision/.venv/bin/python analysis/scripts/build_stationarity_source_resolution.py
../Manuscript\ Revision/.venv/bin/python monte_carlo/scripts/plot_main_monte_carlo.py
../Manuscript\ Revision/.venv/bin/python analysis/scripts/build_mdape_vs_cv_slope.py
../Manuscript\ Revision/.venv/bin/python analysis/scripts/build_chicago_sensitivity.py
../Manuscript\ Revision/.venv/bin/python analysis/scripts/build_lucknow_madhwal_monte_carlo_comparison.py --run-dir monte_carlo/results/runs/p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602 --output-dir analysis/results/lucknow_madhwal_monte_carlo_comparison_20260602
../Manuscript\ Revision/.venv/bin/python missingness/scripts/run_missingness_analysis.py
../Manuscript\ Revision/.venv/bin/python missingness/scripts/plot_three_city_pm25_timeseries.py
```

Additional checks:

| Check | Result |
|---|---|
| Compile affected Python scripts | pass |
| Estimator diagnostics `--skip-qce` smoke test | pass |
| SI-F11 Bonferroni exclusions | pass: Dhaka 2/35, Lucknow 4/71, Chicago 12/277 |
| Period model-based RSE text values | pass: Dhaka n=5, Lucknow n=8, Chicago n=2 |
| Monte Carlo figure data RSE columns | pass: removed the obsolete lognormal-RSE column, retained `rse_normal_pct`, added `empirical_estimator_rse_pct` |
| Manuscript plot mirrors | pass: regenerated paper PDF/PNG copies match retained analysis outputs for updated figures |
| Markdown stale-value scan | pass: no tracked Markdown retains the old sensor-count range, old SI-F11 counts, old GLS caveat, or obsolete Dhaka division-boundary reference |
| Dhaka boundary files | pass: retained plot scripts use `Dhaka_City_admin6.geojson` for shading and `Dhaka_District_admin5.geojson` for outline |

## June 8 Full Rerun For Updated Plot Files

The canonical Monte Carlo run and downstream manuscript-facing builders were rerun before pushing the updated
plot files. The Monte Carlo command used the retained manuscript seed and run ID:

```bash
../Manuscript\ Revision/.venv/bin/python monte_carlo/scripts/run_main_monte_carlo.py \
  --run-id p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602 \
  --datasets dhaka_lcs,lucknow_lcs,lucknow_madhwal_lcs,chicago_lcs_corrected_no_collocation,chicago_lcs_corrected_all,chicago_lcs_raw_no_collocation,chicago_lcs_raw_all,chicago_aqs \
  --draws 10000 \
  --master-seed 20260522 \
  --max-daily-n 50 \
  --max-period-n 300 \
  --n-jobs 0 \
  --overwrite
```

The main README figure, SI, missingness, spatial, stationarity, finite-population plot-only, and consolidated
SI builders were then rerun with the same project environment.

Final verification results:

| Check | Result |
|---|---|
| Canonical Monte Carlo run | pass: run ID `p0_baseline_updated_chicago_may31_plus_madhwal_10000_20260602`, master seed `20260522`, 100,221 summary rows |
| Figure 2 period MdAPE at `n=10` | pass: Dhaka 3.893408%, Lucknow 5.640595%, Chicago 1.904133% |
| Figure 3 across-day median daily MdAPE at `n=10` | pass: Dhaka 5.752410%, Lucknow 4.499974%, Chicago 2.606671% |
| Placement fixed-random period MdAPE at `n=10` | pass: Dhaka 3.924346%, Lucknow 5.583475%, Chicago 1.921026% |
| SI-F11 Bonferroni exclusions | pass: Dhaka 2/35, Lucknow 4/71, Chicago 12/277 |
| Period model-based RSE `<=10%` | pass: Dhaka `n=5`, Lucknow `n=8`, Chicago `n=2` |
| Paper plot PDF/PNG coverage | pass: 28 same-basename PDF/PNG pairs |
| Paper PNG density metadata | pass: all retained paper PNGs report 600 DPI |
| Source-to-paper plot mirrors | pass for regenerated main Monte Carlo, SI-F11, and SI-20 spot checks |

The rerun also generated large draw-extreme outputs under the Monte Carlo run directory. Those files were
deleted after verification because they are reproducible and are not part of the retained GitHub package.
