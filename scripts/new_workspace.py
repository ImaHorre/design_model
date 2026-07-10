"""
new_workspace.py — create a focused research workspace from the template.

Usage
-----
    python scripts/new_workspace.py <name> "<brief description>"

    python scripts/new_workspace.py capillary_numbers \
        "Capillary number scaling of Stage 2 snap-off timing"

Creates
-------
    experimental_workspaces/<name>/
        BRIEF.md    -- pre-filled with your description, ready to expand
        CONTEXT.md  -- repo context for fresh Claude sessions, topic-filtered
        results/    -- empty, for this workspace's outputs
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WORKSPACES_DIR = REPO_ROOT / "experimental_workspaces"
TEMPLATE_DIR = WORKSPACES_DIR / "_template"

TOPIC_HINTS = {
    "capillary": [
        "stepgen/models/stage_wise_v3/stage2_physics.py — capillary pressure, R_critical",
        "stepgen/models/stage_wise_v3/regime_classification.py — Ca-based regime warnings",
        "stepgen/models/stage_wise_v3/stage1_physics.py — Stage 1 Washburn refill",
    ],
    "stage1": [
        "stepgen/models/stage_wise_v3/stage1_physics.py — Stage 1 Washburn refill model",
        "stepgen/models/stage_wise_v3/hydraulics.py — dynamic hydraulic network",
        "analysis/stage_timings.csv — experimental Stage1_s measurements",
    ],
    "stage2": [
        "stepgen/models/stage_wise_v3/stage2_physics.py — snap-off, R_critical, neck tracking",
        "stepgen/models/stage_wise_v3/regime_classification.py — regime warnings",
        "analysis/stage_timings.csv — experimental Stage2_s measurements",
    ],
    "hydraulic": [
        "stepgen/models/stage_wise_v3/hydraulics.py — dynamic hydraulic network",
        "stepgen/models/hydraulics.py — steady-state ladder network solver",
        "stepgen/models/stage_wise_v3/hydraulic_interface.py — interface adapter",
    ],
    "surfactant": [
        "analysis/stage_timings.csv — ContPhase column (SDS, NaCas) comparisons",
        "stepgen/models/stage_wise_v3/stage2_physics.py — gamma_effective parameter",
        "configs/v5_30.yaml — fluid properties section",
    ],
    "viscosity": [
        "stepgen/models/stage_wise_v3/stage1_physics.py — viscosity correction factor",
        "stepgen/config.py — FluidConfig.viscosity field",
        "configs/ — fluid viscosity parameters in yaml configs",
    ],
    "frequency": [
        "stepgen/models/stage_wise_v3/core.py — cycle time = t_stage1 + t_stage2",
        "analysis/stage_timings.csv — Stage1_s, Stage2_s, Stage3_s for Hz calculation",
        "scripts/compare_experiments.py — model vs experimental frequency comparison",
    ],
    "droplet": [
        "stepgen/models/stage_wise_v3/stage2_physics.py — R_critical, V_droplet",
        "stepgen/models/metrics.py — droplet diameter and frequency metrics",
        "analysis/stage_timings.csv — Droplet_diameter_um column",
    ],
}


def slugify(text: str) -> str:
    return re.sub(r"[^\w]+", "_", text.strip().lower()).strip("_")


def detect_topic_hints(name: str, description: str) -> list[str]:
    text = (name + " " + description).lower()
    hits = []
    for keyword, hints in TOPIC_HINTS.items():
        if keyword in text:
            hits.extend(hints)
    if not hits:
        hits = [
            "stepgen/models/stage_wise_v3/core.py — main solver",
            "stepgen/models/stage_wise_v3/stage1_physics.py — Stage 1",
            "stepgen/models/stage_wise_v3/stage2_physics.py — Stage 2",
            "analysis/stage_timings.csv — experimental timing data",
        ]
    return list(dict.fromkeys(hits))  # deduplicate, preserve order


def create_workspace(name: str, description: str) -> Path:
    slug = slugify(name)
    target = WORKSPACES_DIR / slug

    if target.exists():
        print(f"Workspace already exists: {target}")
        sys.exit(1)

    target.mkdir(parents=True)
    (target / "results").mkdir()

    today = date.today().isoformat()
    hints = detect_topic_hints(slug, description)

    brief = (TEMPLATE_DIR / "BRIEF.md").read_text(encoding="utf-8")
    brief = brief.replace("<Title>", name.replace("_", " ").title())
    brief = brief.replace("YYYY-MM-DD", today)
    (target / "BRIEF.md").write_text(brief, encoding="utf-8")

    context_template = (TEMPLATE_DIR / "CONTEXT.md").read_text(encoding="utf-8")
    hints_section = "\n".join(f"- `{h}`" for h in hints)
    context = context_template.replace(
        "<Workspace Name>", name.replace("_", " ").title()
    ).replace(
        "<!-- Filled in by new_workspace.py based on topic keywords -->",
        f"Focus files for **{description}**:\n\n{hints_section}"
    )
    (target / "CONTEXT.md").write_text(context, encoding="utf-8")

    print(f"Created workspace: {target.relative_to(REPO_ROOT)}")
    print()
    print("Next steps:")
    print(f"  1. Edit {slug}/BRIEF.md — fill in your research question and plan")
    print(f"  2. Edit {slug}/CONTEXT.md — add any additional relevant files")
    print(f"  3. Start a fresh Claude session with:")
    print(f'     "Read experimental_workspaces/{slug}/CONTEXT.md and '
          f'experimental_workspaces/{slug}/BRIEF.md."')
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a focused research workspace from the template."
    )
    parser.add_argument("name", help="Workspace name (e.g. capillary_numbers)")
    parser.add_argument("description", help="One-line description of the study")
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    create_workspace(args.name, args.description)


if __name__ == "__main__":
    main()
