"""
preview_schematics.py
=====================
Render every family's device + zoom schematic into one self-contained HTML page.

A quick eyeball check on the Phase 3 renderer without launching the Studio UI:

    python scripts/preview_schematics.py [--out preview.html]

The page is standalone (inline SVG, inline script) so it opens from disk and
survives being emailed around.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from stepgen.families import get_family
from stepgen.viz.schematic import to_interactive_html

# Representative points, one per family — deliberately the deep-DFU corner the
# M1 session cares about, not a toy.
CASES: dict[str, dict] = {
    "serpentine": {
        "main": {"depth_um": 200, "width_um": 1000},
        "rung": {"length_mm": 2, "upstream_width_um": 15, "N": 1000},
        "junction": {"exit_width_um": 60, "exit_depth_um": 20, "pitch_um": 120},
    },
    "radial": {
        "radius_mm": 29.75,
        "upstream_width_um": 20,
        "exit": {"width_um": 30, "depth_um": 10, "pitch_um": 60},
        "inlet_radius_mm": 1.0,
    },
    "manifold": {
        "main": {"depth_um": 200, "width_um": 1000},
        "arms": {"count": 8, "depth_um": 100, "width_um": 200},
        "rung": {"length_mm": 2, "upstream_width_um": 30},
        "rungs_per_arm": 100,
        "junction": {"exit_width_um": 60, "exit_depth_um": 20, "pitch_um": 120},
        "cont_phase": {"width_um": 200},
        "wall": {"min_um": 100},
    },
}

CONTEXT = dict(
    fluids={"mu_dispersed": 0.06, "mu_continuous": 0.00089, "gamma": 0.015},
    footprint={"square_side_mm": 63.5},
    manufacturing={"max_main_depth_um": 200.0, "max_main_width_um": 1000.0,
                   "min_wall_um": 5.0},
)


def build_page(cases: dict[str, dict] = CASES) -> str:
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Phase 3 schematic preview</title></head>",
        "<body style=\"font-family:ui-sans-serif,system-ui,sans-serif;"
        "max-width:1700px;margin:24px auto;padding:0 20px;background:#fff\">",
        "<h1 style='font-size:20px'>Design Studio Phase 3 — schematic preview</h1>",
        "<p style='color:#555;font-size:13px;max-width:70ch'>Every drawing is "
        "emitted from the compiled config the solver consumes. Scroll to zoom, "
        "drag to pan. Anything drawn that the model does not compute is listed "
        "under each figure.</p>",
    ]
    for name, params in cases.items():
        fam = get_family(name)
        cfg = fam.compile(params, **CONTEXT)
        cap = fam.packing_capacity(cfg)
        parts.append(
            f"<h2 style='font-size:16px;border-top:2px solid #eee;"
            f"padding-top:16px;margin-top:28px'>{name}</h2>"
        )
        if cap:
            parts.append(
                f"<p style='font:13px ui-monospace,Menlo,monospace;color:#444'>"
                f"configured N = {cap.n_current:,} &nbsp;|&nbsp; die holds "
                f"{cap.n_max:,} &nbsp;|&nbsp; {cap.utilisation:.0%} full "
                f"&nbsp;|&nbsp; limited by {cap.limited_by}</p>"
            )
        parts.append(
            "<div style='display:flex;gap:26px;flex-wrap:wrap;"
            "align-items:flex-start'>"
        )
        for view in ("device", "zoom"):
            html = to_interactive_html(
                fam.render_schematic(cfg, view), width_px=640, uid=f"{name}-{view}"
            )
            parts.append(f"<div style='flex:1;min-width:520px'>{html}</div>")
        parts.append("</div>")
    parts.append("</body></html>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="schematic_preview.html", help="output HTML path")
    args = ap.parse_args()

    out = Path(args.out)
    out.write_text(build_page(), encoding="utf-8")
    print(f"wrote {out.resolve()}")


if __name__ == "__main__":
    main()
