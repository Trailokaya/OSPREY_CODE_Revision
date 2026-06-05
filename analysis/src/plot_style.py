from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt


FIGURE_DPI = 180
OUTPUT_DPI = 600

TEXT_COLOR = "#111827"
MUTED_TEXT_COLOR = "#6b7280"
GRID_COLOR = "#e5e7eb"
REFERENCE_LINE_COLOR = "#d1d5db"
BOUNDARY_FILL_COLOR = "#bfdbfe"
DISTRICT_EDGE_COLOR = "#1d4ed8"
MAP_OUTSIDE_COLOR = "#f97316"
MAP_HIGHLIGHT_COLOR = "#dc2626"
REGRESSION_LINE_COLOR = "#dc2626"
NSTAR_FILL_COLOR = "#9ca3af"
AQS_COLOR = "#111827"

CITY_COLORS = {
    "dhaka": "#D55E00",
    "lucknow": "#0072B2",
    "chicago": "#009E73",
}

NETWORK_COLORS = {
    "dhaka_lcs": CITY_COLORS["dhaka"],
    "lucknow_lcs": CITY_COLORS["lucknow"],
    "lucknow_madhwal_lcs": "#56B4E9",
    "chicago_lcs": CITY_COLORS["chicago"],
    "chicago_lcs_corrected": CITY_COLORS["chicago"],
    "chicago_lcs_corrected_all": CITY_COLORS["chicago"],
    "chicago_lcs_corrected_no_collocation": CITY_COLORS["chicago"],
    "chicago_lcs_raw": "#66C2A5",
    "chicago_lcs_raw_all": "#66C2A5",
    "chicago_lcs_raw_no_collocation": "#66C2A5",
    "chicago_aqs": AQS_COLOR,
}

SAMPLE_SIZE_COLORS = {
    5: "#2563eb",
    10: "#f97316",
    20: "#16a34a",
    30: "#7c3aed",
    50: "#0f766e",
}

SCENARIO_COLORS = {
    "S0_baseline": "#111827",
    "S1_daily_18h": "#2563eb",
    "S2_daily_12h": "#0f766e",
    "S3_annual_75pct": "#7c3aed",
    "S4_daily_18h_annual_75pct": "#dc2626",
    "S5_drop_gap_gt_30d": "#d97706",
}


def city_key_from_dataset(dataset_key: str) -> str:
    lowered = dataset_key.lower()
    if lowered.startswith("dhaka"):
        return "dhaka"
    if lowered.startswith("lucknow"):
        return "lucknow"
    if lowered.startswith("chicago"):
        return "chicago"
    return lowered


def color_for_dataset(dataset_key: str) -> str:
    return NETWORK_COLORS.get(dataset_key, CITY_COLORS.get(city_key_from_dataset(dataset_key), TEXT_COLOR))


def setup_matplotlib() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": FIGURE_DPI,
            "savefig.dpi": OUTPUT_DPI,
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#9ca3af",
            "axes.labelcolor": TEXT_COLOR,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
            "text.color": TEXT_COLOR,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save_figure(fig: plt.Figure, output_base: Path, dpi: int = OUTPUT_DPI) -> dict[str, str]:
    output_base = Path(output_base)
    output_base.parent.mkdir(parents=True, exist_ok=True)
    png_path = output_base.with_suffix(".png")
    pdf_path = output_base.with_suffix(".pdf")
    fig.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {"png": str(png_path), "pdf": str(pdf_path)}
