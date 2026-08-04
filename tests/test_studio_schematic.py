"""
Phase 3 — the design visualiser.

The tests that matter here are not "does it draw something".  They are:

1. **Anti-drift** — the drawing is derived from the compiled config the solver
   consumes, so a change to a family's packing maths moves the picture too.
   This is the whole justification for the phase: the manifold arm pitch was
   wrong by 10-20x and every derived metric still looked plausible.
2. **Honesty** — nothing is drawn that the model does not compute without being
   declared in ``inventions``; a family with no declared topology gets a drawing
   that says so rather than an invented shape.
3. **Level of detail** — at 11,550 DFUs the renderer must not emit 11,550
   rectangles, and the band it draws instead must still be true-scale.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from stepgen.families import get_family
from stepgen.viz.schematic import (
    MAX_DRAWN_UNITS,
    AnnularZone,
    PackingCapacity,
    Rect,
    Schematic,
    Zone,
    panzoom_js,
    schematic_block,
    to_svg,
)

SVG_NS = "{http://www.w3.org/2000/svg}"

CONTEXT = dict(
    fluids={"mu_dispersed": 0.06, "mu_continuous": 0.00089, "gamma": 0.015},
    footprint={"square_side_mm": 63.5},
    manufacturing={"max_main_depth_um": 200.0, "max_main_width_um": 1000.0,
                   "min_wall_um": 5.0},
)

PARAMS = {
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

ALL = sorted(PARAMS)


def compiled(name, **overrides):
    """Compile one family, optionally overriding the shared context blocks."""
    ctx = {k: dict(v) for k, v in CONTEXT.items()}
    for block, patch in overrides.items():
        ctx[block].update(patch)
    return get_family(name), get_family(name).compile(PARAMS[name], **ctx)


# ---------------------------------------------------------------------------
# Every family draws, and every drawing is valid, self-contained SVG
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("view", ["device", "zoom"])
def test_renders_valid_svg(name, view):
    fam, cfg = compiled(name)
    sch = fam.render_schematic(cfg, view)
    assert isinstance(sch, Schematic)
    assert sch.family == name and sch.view == view
    assert sch.prims, "a schematic with no primitives is a bug, not a drawing"

    svg = to_svg(sch)
    ET.fromstring(svg)                      # parses -> well-formed
    assert svg.startswith("<svg")


@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("view", ["device", "zoom"])
def test_svg_is_self_contained(name, view):
    """No external fetch: the same markup has to work in the workbook offline."""
    fam, cfg = compiled(name)
    svg = to_svg(fam.render_schematic(cfg, view))
    # the SVG namespace URI is a declaration, not a fetch — drop it before testing
    body = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    for forbidden in ("http://", "https://", "<image", "@import", "xlink:href", "url("):
        if forbidden == "url(":
            # url(#hatch) / url(#dense) are internal refs; url(http…) would not be
            assert "url(http" not in body
            continue
        assert forbidden not in body, f"{forbidden} would need a network fetch"


@pytest.mark.parametrize("name", ALL)
def test_drawing_is_proportioned(name):
    """
    A rung is 15-30x longer than the pitch is wide, so a fixed DFU count gives a
    7:1 sliver on real V5 geometry. The zoom has to adapt its span.
    """
    fam, cfg = compiled(name)
    for view in ("device", "zoom"):
        sch = fam.render_schematic(cfg, view)
        aspect = sch.height_m / sch.width_m
        assert 0.3 < aspect < 3.0, f"{name}/{view} aspect {aspect:.2f} is unreadable"


# ---------------------------------------------------------------------------
# Anti-drift — the picture follows the compiled geometry
# ---------------------------------------------------------------------------

def test_serpentine_geometry_matches_compiled_config():
    """Drawn block sizes are the compiled values, not a redrawn approximation."""
    fam, cfg = compiled("serpentine")
    sch = fam.render_schematic(cfg, "device")

    oil = [p for p in sch.prims if isinstance(p, Rect) and p.role == "oil_main"]
    assert oil, "no oil main drawn"
    assert oil[0].h == pytest.approx(cfg.geometry.main.Mcw)

    dfu = [p for p in sch.prims if isinstance(p, Zone) and p.role == "dfu"]
    assert dfu, "no DFU zone drawn"
    assert dfu[0].h == pytest.approx(cfg.geometry.rung.mcl)
    assert dfu[0].pitch == pytest.approx(cfg.geometry.rung.pitch)
    assert dfu[0].unit_w == pytest.approx(cfg.geometry.rung.mcw)


def test_serpentine_lane_count_matches_compute_layout():
    """
    The drawing and ``compute_layout`` must agree on the fold. If they ever
    disagree, one of them is a second packing model — the failure this whole
    phase exists to prevent.
    """
    from stepgen.design.layout import compute_layout

    fam, cfg = compiled("serpentine")
    lay = compute_layout(cfg)
    sch = fam.render_schematic(cfg, "device")

    drawn_lanes = len([p for p in sch.prims
                       if isinstance(p, Rect) and p.role == "oil_main"])
    assert drawn_lanes == lay.num_lanes
    assert sch.fits == lay.fits_footprint


def test_manifold_arm_pitch_matches_the_resistance_model():
    """
    The drawn arm pitch must equal the pitch ``compile()`` used to build
    ``r_prim``.  This is the number the 2026-07-13 rewrite corrected by 10-20x.
    """
    from stepgen.families.manifold import _arm_pitch

    fam, cfg = compiled("manifold")
    expected = (cfg.arm_width_m + 2 * cfg.rung_len_m
                + 2 * cfg.cp_base_m + cfg.wall_width_m)
    assert _arm_pitch(cfg) == pytest.approx(expected)

    sch = fam.render_schematic(cfg, "device")
    arms = sorted(p.y for p in sch.prims if isinstance(p, Rect) and p.role == "arm")
    assert len(arms) == cfg.M
    gaps = [b - a for a, b in zip(arms, arms[1:])]
    assert all(g == pytest.approx(expected) for g in gaps), \
        "drawn arm spacing must be the modelled arm pitch"


def test_radial_hub_radius_matches_the_solver():
    """r_hub = R(w+t)/pitch — the same expression solve_radial uses (§11.2)."""
    from stepgen.families.radial import _hub_radius

    fam, cfg = compiled("radial")
    expected = cfg.radius_m * (cfg.upstream_width_m + cfg.t_min_m) / cfg.pitch_m
    assert _hub_radius(cfg) == pytest.approx(expected)

    sch = fam.render_schematic(cfg, "device")
    band = [p for p in sch.prims if isinstance(p, AnnularZone)][0]
    assert band.r_in == pytest.approx(expected)
    assert band.r_out == pytest.approx(cfg.radius_m)


def test_geometry_change_moves_the_drawing():
    """A different die must produce a different drawing — no stale caching."""
    fam, small = compiled("serpentine", footprint={"square_side_mm": 20.0})
    _, big = compiled("serpentine", footprint={"square_side_mm": 63.5})
    assert to_svg(fam.render_schematic(small, "device")) != \
           to_svg(fam.render_schematic(big, "device"))


# ---------------------------------------------------------------------------
# Level of detail
# ---------------------------------------------------------------------------

def test_large_dfu_counts_collapse_to_a_density_band():
    """11,550 DFUs must not become 11,550 <rect> elements."""
    fam, cfg = compiled("radial")           # ~3,115 spokes at R=29.75, pitch 60 µm
    cap = fam.packing_capacity(cfg)
    assert cap.n_current > MAX_DRAWN_UNITS

    svg = to_svg(fam.render_schematic(cfg, "device"))
    n_paths = svg.count("<path")
    assert n_paths < 50, f"{n_paths} paths — the LOD band did not engage"
    assert 'url(#dense)' in svg, "expected the density fill for an unresolvable count"


def test_small_counts_are_drawn_individually():
    """Below the cap the real features are drawn, not a smear."""
    fam, cfg = compiled("serpentine")
    zoom = fam.render_schematic(cfg, "zoom")
    rungs = [p for p in zoom.prims if isinstance(p, Rect) and p.role == "dfu"]
    assert 4 <= len(rungs) <= 40


def test_zone_band_is_true_scale_even_when_collapsed():
    """The band collapses its contents, never its own size."""
    z = Zone(0.0, 0.0, 10e-3, 2e-3, "dfu", count=99999,
             unit_w=15e-6, unit_h=2e-3, pitch=120e-6)
    sch = Schematic(family="t", view="device", prims=[z],
                    extent=(0.0, 0.0, 10e-3, 2e-3))
    root = ET.fromstring(to_svg(sch))
    # count only the drawing itself — defs patterns and legend swatches are chrome
    scene = next(g for g in root.iter(SVG_NS + "g") if g.get("id") == "scene")
    rects = list(scene.iter(SVG_NS + "rect"))
    assert len(rects) == 2                        # band + density overlay, not 99999
    band = rects[0]
    assert float(band.get("width")) == pytest.approx(10.0)   # 10 mm, true scale
    assert float(band.get("height")) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Honesty
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("view", ["device", "zoom"])
def test_every_drawing_declares_its_inventions(name, view):
    """
    Each family draws *something* beyond what the model computes (a turn path, a
    nominal exit length). Every one of those must be declared, because a
    schematic that quietly infills plausible geometry looks right and lies.
    """
    fam, cfg = compiled(name)
    sch = fam.render_schematic(cfg, view)
    assert sch.inventions, f"{name}/{view} declares no inventions"
    assert all(isinstance(s, str) and s.strip() for s in sch.inventions)


@pytest.mark.parametrize("name", ALL)
@pytest.mark.parametrize("view", ["device", "zoom"])
def test_inventions_are_surfaced_in_the_rendered_block(name, view):
    """Declaring an invention is pointless if the reader never sees it."""
    fam, cfg = compiled(name)
    sch = fam.render_schematic(cfg, view)
    html = schematic_block(sch)
    assert "Drawn but not modelled" in html
    for note in sch.inventions:
        assert note.split(".")[0][:40] in html


def test_undeclared_family_gets_an_honest_fallback_not_an_invented_shape():
    """A family with no topology declared must say so, not draw a guess."""
    from stepgen.families.base import CommonMetrics, Family

    class Bare(Family):
        name = "bare"

        def applicable_metrics(self):
            return {"build"}

        def compile(self, params, *, fluids, footprint, manufacturing):
            class C:
                square_side_m = 63.5e-3
                exit_width_m = 30e-6
                exit_depth_m = 10e-6
            return C()

        def solve(self, compiled, operating, *, params, label):
            return CommonMetrics(family="bare", label=label)

    fam = Bare()
    cfg = fam.compile({}, fluids={}, footprint={}, manufacturing={})

    device = fam.render_schematic(cfg, "device")
    assert "not declared" in " ".join(device.notes + device.inventions).lower()
    # nothing but the die outline — no channels invented
    assert not [p for p in device.prims
                if isinstance(p, Rect) and p.role not in ("die",)]
    ET.fromstring(to_svg(device))

    zoom = fam.render_schematic(cfg, "zoom")
    assert "not declared" in " ".join(zoom.notes + zoom.inventions).lower()


# ---------------------------------------------------------------------------
# Packing capacity — the generative readout
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL)
def test_capacity_is_reported(name):
    fam, cfg = compiled(name)
    cap = fam.packing_capacity(cfg)
    assert isinstance(cap, PackingCapacity)
    assert cap.n_current > 0 and cap.n_max > 0
    assert cap.limited_by


def test_serpentine_capacity_agrees_with_compute_layout():
    """n_max lanes must be consistent with the checker it inverts."""
    from stepgen.design.layout import compute_layout

    fam, cfg = compiled("serpentine")
    cap = fam.packing_capacity(cfg)
    lay = compute_layout(cfg)

    assert cap.detail["lanes_current"] == lay.num_lanes
    assert cap.detail["lanes_max"] >= lay.num_lanes      # this design fits
    assert cap.n_max >= cap.n_current
    per_lane = int(lay.lane_length / cfg.geometry.rung.pitch)
    assert cap.n_max == pytest.approx(cap.detail["lanes_max"] * per_lane)


def test_bigger_die_buys_more_dfus():
    """
    The point of the inverse. The old layout model only ever flipped a
    fits/does-not-fit flag when the die grew; capacity has to actually rise.
    """
    fam, small = compiled("serpentine", footprint={"square_side_mm": 30.0})
    _, big = compiled("serpentine", footprint={"square_side_mm": 63.5})
    assert fam.packing_capacity(big).n_max > fam.packing_capacity(small).n_max


def test_turn_radius_does_not_change_the_lane_count():
    """
    The turn radius plays no part in the stack-up at all (W1-1). It used to set
    the inter-lane gap as 2×turn_radius, which reproduced the measured 1.0 mm
    wall only because both defaulted to 500 µm — a coincidence. The gap is the
    wall; turn_radius is reported.
    """
    fam, tight = compiled("serpentine", footprint={"turn_radius_um": 50.0})
    _, wide = compiled("serpentine", footprint={"turn_radius_um": 2000.0})
    c_tight, c_wide = fam.packing_capacity(tight), fam.packing_capacity(wide)

    assert c_tight.detail["lanes_current"] == c_wide.detail["lanes_current"]
    assert c_tight.detail["lanes_max"] == c_wide.detail["lanes_max"]
    assert c_tight.detail["lane_pitch_mm"] == pytest.approx(
        c_wide.detail["lane_pitch_mm"], rel=1e-12)


def test_the_wall_sets_the_lane_count():
    """
    The counterpart: what turn_radius no longer does, the wall does. A thinner
    wall stacks more lane pairs into the same die height.
    """
    fam, thin = compiled("serpentine", footprint={"wall_width_um": 200.0})
    _, thick = compiled("serpentine", footprint={"wall_width_um": 2000.0})
    c_thin, c_thick = fam.packing_capacity(thin), fam.packing_capacity(thick)

    assert c_thin.detail["lanes_max"] > c_thick.detail["lanes_max"]


def test_manifold_capacity_is_in_the_right_order_of_magnitude():
    """
    A sanity anchor against the real V5-30 (11,550 DFUs). This is the family
    whose packing was wrong by 10-20x; an order-of-magnitude check is exactly
    the tripwire that would have caught it.
    """
    fam, cfg = compiled("manifold")
    cap = fam.packing_capacity(cfg)
    assert 3_000 < cap.n_max < 40_000, f"n_max={cap.n_max:,} is off by an order"


def test_overflowing_design_is_reported_as_not_fitting():
    fam, cfg = compiled("serpentine", footprint={"square_side_mm": 8.0})
    cap = fam.packing_capacity(cfg)
    sch = fam.render_schematic(cfg, "device")
    assert not cap.fits
    assert sch.fits is False
    assert any("overflow" in p.role for p in sch.prims if isinstance(p, Rect))


# ---------------------------------------------------------------------------
# Wiring into the surfaces
# ---------------------------------------------------------------------------

def test_ui_layout_path_needs_no_solve(monkeypatch):
    """
    The live tab must never call solve() — that is what makes it live at all
    (compile ~1 ms against solve ~500 ms per point).
    """
    from stepgen.studio.study import load_study
    from stepgen.studio.ui import schematic_for_point

    study = load_study("configs/study_template.yaml")
    point = study.points[0]

    family = get_family(point.family)
    called = {"solve": False}
    monkeypatch.setattr(
        type(family), "solve",
        lambda *a, **k: called.__setitem__("solve", True),
    )
    sch, cap = schematic_for_point(point, "device")
    assert sch.prims and cap is not None
    assert not called["solve"], "the layout preview solved the design"


def test_workbook_caps_embedded_schematics():
    from stepgen.studio.workbook import MAX_SCHEMATIC_ROWS, _schematic_rows

    scored = [object()] * 300
    best = {250, 260, 299}
    rows = _schematic_rows(scored, best)
    assert len(rows) == MAX_SCHEMATIC_ROWS
    assert best <= rows, "starred rows must always be drawn"


def test_panzoom_script_is_emitted_once_per_document():
    """
    A chapter can carry hundreds of drawings; one script copy each would bloat
    it for no benefit. The block carries no script, the page carries one.
    """
    fam, cfg = compiled("serpentine")
    block = schematic_block(fam.render_schematic(cfg, "device"))
    assert "<script" not in block
    assert "data-panzoom" in block
    assert "__stepgenPanzoom" in panzoom_js()
