from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "src"))

from plot_style import (  # noqa: E402
    CITY_COLORS,
    GRID_COLOR,
    REFERENCE_LINE_COLOR,
    save_figure,
    setup_matplotlib,
)


RESULTS_DIR = REPO_ROOT / "analysis/results/estimand_framing"
PLOTS_DIR = REPO_ROOT / "analysis/plots/estimand_framing"


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)
    rows = [
        "| " + " | ".join(str(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        rows.append(
            "| "
            + " | ".join("" if pd.isna(row[column]) else str(row[column]).replace("\n", " ") for column in columns)
            + " |"
        )
    return "\n".join(rows)


def draw_schematic() -> None:
    setup_matplotlib()
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    boxes = [
        {
            "xy": (0.45, 3.75),
            "w": 2.4,
            "h": 1.55,
            "title": "Underlying city field",
            "body": "Continuous PM2.5 surface\nand population exposure",
            "color": "#f3f4f6",
            "edge": "#6b7280",
        },
        {
            "xy": (3.65, 3.75),
            "w": 2.55,
            "h": 1.55,
            "title": "Deployed network",
            "body": "Finite set of valid sensors\nused as reference population",
            "color": "#dbeafe",
            "edge": CITY_COLORS["lucknow"],
        },
        {
            "xy": (6.95, 3.75),
            "w": 2.55,
            "h": 1.55,
            "title": "Random subnetwork",
            "body": "n sensors sampled SRSWOR\nfrom available network",
            "color": "#fee2e2",
            "edge": CITY_COLORS["chicago"],
        },
        {
            "xy": (3.65, 0.75),
            "w": 2.55,
            "h": 1.55,
            "title": "Reference mean",
            "body": "Arithmetic mean of\nsensor-level means",
            "color": "#fef3c7",
            "edge": CITY_COLORS["dhaka"],
        },
        {
            "xy": (6.95, 0.75),
            "w": 2.55,
            "h": 1.55,
            "title": "Subnetwork error",
            "body": "MdAPE and absolute error\nvs reference-network mean",
            "color": "#ecfccb",
            "edge": "#65a30d",
        },
    ]

    for box in boxes:
        rect = patches.FancyBboxPatch(
            box["xy"],
            box["w"],
            box["h"],
            boxstyle="round,pad=0.025,rounding_size=0.08",
            linewidth=1.4,
            edgecolor=box["edge"],
            facecolor=box["color"],
        )
        ax.add_patch(rect)
        x, y = box["xy"]
        ax.text(x + box["w"] / 2, y + box["h"] - 0.35, box["title"], ha="center", va="top", weight="bold")
        ax.text(x + box["w"] / 2, y + 0.55, box["body"], ha="center", va="center", fontsize=8.5)

    arrows = [
        ((2.9, 4.52), (3.55, 4.52), "sampled deployment\nnot full field"),
        ((6.25, 4.52), (6.85, 4.52), "Monte Carlo\nsubsets"),
        ((4.92, 3.68), (4.92, 2.38), "two-step\naggregation"),
        ((6.25, 1.52), (6.85, 1.52), "compare estimates\nwith target"),
        ((8.2, 3.68), (8.2, 2.38), "subnetwork\nmean"),
    ]
    for start, end, label in arrows:
        ax.annotate(
            "",
            xy=end,
            xytext=start,
            arrowprops={"arrowstyle": "->", "color": "#111827", "lw": 1.2},
        )
        ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.25, label, ha="center", va="bottom", fontsize=8)

    ax.plot([0.45, 9.5], [3.25, 3.25], color=GRID_COLOR, linewidth=1)
    ax.text(
        0.55,
        3.08,
        "Not estimated here",
        color="#6b7280",
        fontsize=8,
        va="top",
    )
    ax.text(
        3.65,
        3.08,
        "Estimated here",
        color="#111827",
        fontsize=8,
        va="top",
    )
    ax.text(
        0.45,
        0.25,
        "Core wording: results quantify how well random subnetworks reproduce the deployed reference-network mean.",
        fontsize=9,
        color="#111827",
    )
    ax.text(
        0.45,
        0.02,
        "Avoid wording that implies a population-weighted, area-weighted, or regulatory-compliance city-wide mean.",
        fontsize=8.5,
        color="#6b7280",
    )

    save_figure(fig, PLOTS_DIR / "S01_reference_network_estimand_schematic")


def write_outputs() -> None:
    glossary = pd.DataFrame(
        [
            {
                "term": "deployed reference-network mean",
                "use": "Primary estimand",
                "definition": "Arithmetic mean of sensor-level means across the deployed valid sensor network for a specified time window.",
                "avoid_confusion_with": "True city-wide, area-weighted, population-weighted, or regulatory-compliance mean.",
            },
            {
                "term": "subnetwork estimate",
                "use": "Monte Carlo sampled estimate",
                "definition": "Arithmetic mean calculated from n sensors sampled without replacement from the deployed network.",
                "avoid_confusion_with": "A new independent deployment or sampling with replacement.",
            },
            {
                "term": "reference-network reproducibility error",
                "use": "Primary error framing",
                "definition": "Absolute or percentage difference between the subnetwork estimate and deployed reference-network mean.",
                "avoid_confusion_with": "Instrument calibration error or city-wide exposure error.",
            },
            {
                "term": "Chicago study-period mean",
                "use": "Chicago period target",
                "definition": "Nine-month corrected-LCS deployed-network mean for the available Chicago period.",
                "avoid_confusion_with": "Annual Chicago mean.",
            },
        ]
    )
    glossary.to_csv(RESULTS_DIR / "estimand_glossary.csv", index=False)

    lines = [
        "# Estimand Framing Summary",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Core Decision",
        "",
        "The defensible manuscript framing is deployed reference-network mean reproducibility. The current analyses do not estimate a true city-wide population-weighted, area-weighted, or regulatory-compliance PM2.5 mean.",
        "",
        "## Replacement Language",
        "",
        "| Avoid | Use Instead | Reason |",
        "|---|---|---|",
        "| true city-wide mean | deployed reference-network mean | The target is the finite sensor network. |",
        "| city exposure | network-average PM2.5 across deployed sensors | Exposure requires population weighting. |",
        "| representative of the whole city | representative of the deployed network support | Spatial support is limited to where sensors exist. |",
        "| annual Chicago mean | nine-month Chicago study-period mean | Chicago data do not cover a full year. |",
        "| reference monitors in all cities | Chicago AQS context monitors | Dhaka/Lucknow reference markers are not used in the current Figure 1 map package. |",
        "",
        "## Methods Text",
        "",
        "For each city and time window, we defined the target estimand as the arithmetic mean of sensor-level PM2.5 means across the deployed network after the inherited QA/QC and calibration pipeline. We then drew simple random samples without replacement from that finite network and compared each subnetwork estimate with the deployed reference-network mean. The resulting MdAPE and absolute-error curves therefore quantify reference-network mean reproducibility, not population-weighted exposure or regulatory compliance.",
        "",
        "## Results Text",
        "",
        "Adding Chicago extends the finite-population reproducibility analysis to a lower-concentration, higher-density low-cost-sensor deployment. Chicago results should be labeled as a nine-month study-period analysis using corrected low-cost sensors with collocation sites excluded from the primary finite population.",
        "",
        "## Revision Note",
        "",
        "We revised the framing throughout to clarify that the analysis estimates the reproducibility of a deployed reference-network mean; we do not claim that random subnetworks recover a true city-wide exposure or area-weighted PM2.5 field.",
        "",
        "## Glossary",
        "",
        markdown_table(glossary),
        "",
    ]
    (RESULTS_DIR / "estimand_language_and_schematic.md").write_text("\n".join(lines))

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "schematic_png": str((PLOTS_DIR / "S01_reference_network_estimand_schematic.png").relative_to(REPO_ROOT)),
        "schematic_pdf": str((PLOTS_DIR / "S01_reference_network_estimand_schematic.pdf").relative_to(REPO_ROOT)),
        "primary_estimand": "deployed reference-network mean",
        "excluded_estimands": [
            "true city-wide mean",
            "population-weighted exposure mean",
            "area-weighted field mean",
            "regulatory-compliance mean",
        ],
    }
    (RESULTS_DIR / "estimand_framing_metadata.json").write_text(json.dumps(metadata, indent=2))


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    draw_schematic()
    write_outputs()
    print(f"Wrote estimand framing outputs to {RESULTS_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
