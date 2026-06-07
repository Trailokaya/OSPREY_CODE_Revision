# Requirements And Final Environment Check

Date: 2026-06-07

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
