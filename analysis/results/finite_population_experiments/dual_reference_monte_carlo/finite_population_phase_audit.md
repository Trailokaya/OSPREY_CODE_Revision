# Finite-Population Phase Audit

This audit checks Phases 1–4 for seed/config presence, expected outer seed rows, selected-subset counts, per-draw files, aggregated outputs, and plot outputs.

## phase1_chicago_realitycheck_n40

- `pass` — master_seed: observed `20260528`, expected `20260528`
- `pass` — inner_draws: observed `10000`, expected `10000`
- `pass` — outer_seed_rows: observed `50`, expected `50`
- `pass` — target_N_star_values: observed `[40]`, expected `[40]`
- `pass` — selected_sensor_count_matches_target: observed `True`, expected `True`
- `pass` — per_draw_parquet_files: observed `0`, expected `50`; Per-draw files are omitted from the GitHub package; retained seeds and compact summaries are sufficient for manuscript outputs.
- `pass` — all_draw_time_aggregations: observed `['daily', 'period']`, expected `daily+period`
- `pass` — all_draw_rows: observed `42250`, expected `nonzero`
- `pass` — file_exists:aggregated/headline_numbers.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_mdape_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_absolute_error_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:config/selected_sensor_subsets_long.csv: observed `True`, expected `True`
- `pass` — file_exists:phase1_summary.md: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_mdape_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_absolute_error_envelope.csv: observed `True`, expected `True`
- `pass` — pdf_plot_count: observed `3`, expected `>=1`

## phase2_chicago_nsensitivity

- `pass` — master_seed: observed `20260528`, expected `20260528`
- `pass` — inner_draws: observed `10000`, expected `10000`
- `pass` — outer_seed_rows: observed `800`, expected `800`
- `pass` — target_N_star_values: observed `[30, 40, 50, 70, 100, 150, 200, 277]`, expected `[30, 40, 50, 70, 100, 150, 200, 277]`
- `pass` — selected_sensor_count_matches_target: observed `True`, expected `True`
- `pass` — per_draw_parquet_files: observed `0`, expected `800`; Per-draw files are omitted from the GitHub package; retained seeds and compact summaries are sufficient for manuscript outputs.
- `pass` — all_draw_summaries_parquet: observed `omitted from GitHub package`, expected `compact summaries retained`; Large draw-level aggregate omitted; manuscript-facing summaries, plots, and seeds are retained.
- `pass` — file_exists:aggregated/headline_numbers.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_mdape_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_absolute_error_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:config/selected_sensor_subsets_long.csv: observed `True`, expected `True`
- `pass` — file_exists:phase2_summary.md: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_mdape_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_absolute_error_envelope.csv: observed `True`, expected `True`
- `pass` — pdf_plot_count: observed `3`, expected `>=1`

## phase3_lucknow_downsampling

- `pass` — master_seed: observed `20260528`, expected `20260528`
- `pass` — inner_draws: observed `10000`, expected `10000`
- `pass` — outer_seed_rows: observed `500`, expected `500`
- `pass` — target_N_star_values: observed `[31, 40, 50, 60, 71]`, expected `[31, 40, 50, 60, 71]`
- `pass` — selected_sensor_count_matches_target: observed `True`, expected `True`
- `pass` — per_draw_parquet_files: observed `0`, expected `500`; Per-draw files are omitted from the GitHub package; retained seeds and compact summaries are sufficient for manuscript outputs.
- `pass` — all_draw_summaries_parquet: observed `omitted from GitHub package`, expected `compact summaries retained`; Large draw-level aggregate omitted; manuscript-facing summaries, plots, seeds, and compact N*=50 Lucknow draw table are retained.
- `pass` — file_exists:aggregated/headline_numbers.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_mdape_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_absolute_error_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:config/selected_sensor_subsets_long.csv: observed `True`, expected `True`
- `pass` — file_exists:phase3_summary.md: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_mdape_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_absolute_error_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/selected_reference_draw_summaries_n50.parquet: observed `True`, expected `True`
- `pass` — pdf_plot_count: observed `5`, expected `>=1`

## phase4_chicago_selection_strategies

- `pass` — master_seed: observed `20260528`, expected `20260528`
- `pass` — inner_draws: observed `10000`, expected `10000`
- `pass` — outer_seed_rows: observed `630`, expected `630`
- `pass` — target_N_star_values: observed `[30, 50, 70]`, expected `[30, 50, 70]`
- `pass` — selected_sensor_count_matches_target: observed `True`, expected `True`
- `pass` — per_draw_parquet_files: observed `0`, expected `630`; Per-draw files are omitted from the GitHub package; retained seeds and compact summaries are sufficient for manuscript outputs.
- `pass` — all_draw_time_aggregations: observed `['period']`, expected `period only`; Phase 4 daily strategy outputs are stored separately by design.
- `pass` — all_draw_rows: observed `18270`, expected `nonzero`
- `pass` — file_exists:aggregated/headline_numbers.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_strategy_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/period_strategy_absolute_error_envelope.csv: observed `True`, expected `True`
- `pass` — file_exists:config/selected_sensor_subsets_long.csv: observed `True`, expected `True`
- `pass` — file_exists:phase4_summary.md: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_strategy_summary_n50.csv: observed `True`, expected `True`
- `pass` — file_exists:aggregated/daily_strategy_full_reference_summary_n50.csv: observed `True`, expected `True`
- `pass` — pdf_plot_count: observed `10`, expected `>=1`

## dual_reference_monte_carlo

- `pass` — dual_reference_join_rows: observed `270320`, expected `270320`; Each retained row has selected-reference and full-network-reference metrics for the same selected subset and sample draw seed.
- `pass` — selected_reference_rows_without_full_target: observed `19530`, expected `allowed`; Selected-reference daily rows can exceed the full-reference table when no full-network daily target is available for a date.
- `pass` — dual_reference_run_keys: observed `['chicago_phase4_strategy_n50', 'lucknow_phase3_random_n50']`, expected `['chicago_phase4_strategy_n50', 'lucknow_phase3_random_n50']`
