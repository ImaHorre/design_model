"""
Tests for the StepGen Design Studio (families + studio pipeline).

Covers:
  * grid expansion (scalar -> 1 point; lists -> Cartesian product; family axis)
  * the family registry + contract
  * the serpentine anchor: family solve == evaluate_candidate on v5_30
  * design-from-target junction derivation
  * worst-category-wins scoring + N-A (grey) handling
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stepgen.families import CommonMetrics, get_family, list_families
from stepgen.families.serpentine import solve_config
from stepgen.studio.study import build_points, expand_grid, load_study
from stepgen.studio.scoring import score_metrics

REPO = Path(__file__).resolve().parent.parent
V5_30 = REPO / "configs" / "v5_30.yaml"
TEMPLATE = REPO / "configs" / "study_template.yaml"


# ---------------------------------------------------------------------------
# Grid expansion
# ---------------------------------------------------------------------------

def test_expand_grid_scalar_is_single():
    assert expand_grid({"a": 1, "b": 2}) == [{"a": 1, "b": 2}]


def test_expand_grid_list_is_product():
    out = expand_grid({"a": [1, 2], "b": [3, 4]})
    assert len(out) == 4
    assert {"a": 1, "b": 3} in out
    assert {"a": 2, "b": 4} in out


def test_expand_grid_nested():
    out = expand_grid({"main": {"depth_um": [200, 400]}, "n": 5})
    assert len(out) == 2
    assert {"main": {"depth_um": 200}, "n": 5} in out


def test_build_points_family_axis_and_product():
    raw = {
        "family": ["serpentine"],
        "operating": {"Po_mbar": [200, 500], "Qw_mlhr": 5},
        "serpentine": {"main": {"depth_um": [200, 400]}},
    }
    points = build_points(raw)
    # 2 Po × 2 depth = 4 points, all serpentine
    assert len(points) == 4
    assert {p.family for p in points} == {"serpentine"}
    assert {p.operating["Po_mbar"] for p in points} == {200, 500}


def test_single_device_is_sweep_of_one():
    raw = {"family": "serpentine", "operating": {"Po_mbar": 500, "Qw_mlhr": 5},
           "serpentine": {"main": {"depth_um": 200}}}
    assert len(build_points(raw)) == 1


# ---------------------------------------------------------------------------
# Registry / contract
# ---------------------------------------------------------------------------

def test_registry_has_serpentine():
    assert "serpentine" in list_families()
    fam = get_family("serpentine")
    assert "throughput_mlhr" in fam.applicable_metrics()
    assert "build" in fam.applicable_metrics()


def test_unknown_family_raises():
    with pytest.raises(KeyError):
        get_family("does-not-exist")


# ---------------------------------------------------------------------------
# Serpentine anchor: family output must equal evaluate_candidate exactly
# ---------------------------------------------------------------------------

def test_serpentine_anchor_matches_evaluate_candidate():
    from stepgen.config import load_config
    from stepgen.design.sweep import evaluate_candidate

    cfg = load_config(V5_30)
    row = evaluate_candidate(cfg, Po_in_mbar=200.0, Qw_in_mlhr=5.0)
    cm = solve_config(cfg, Po_mbar=200.0, Qw_mlhr=5.0, label="v5_30")

    assert cm.N_dfu == row["Nmc"]
    assert cm.droplet_um == pytest.approx(row["D_pred"] * 1e6, rel=1e-12)
    assert cm.uniformity_pct == pytest.approx(row["dP_spread_pct"], rel=1e-12)
    assert cm.operating_Po_mbar == pytest.approx(200.0)
    assert cm.fits_square == bool(row["fits_footprint"])
    # throughput: Q_oil_total [m^3/s] -> mL/hr
    assert cm.throughput_mlhr == pytest.approx(row["Q_oil_total"] * 1e6 * 3600.0, rel=1e-12)


# ---------------------------------------------------------------------------
# Compile from an explicit study point, and from a droplet target
# ---------------------------------------------------------------------------

_FLUIDS = {"mu_dispersed": 0.06, "mu_continuous": 0.00089, "gamma": 0.015,
           "emulsion_ratio": 0.1, "phase_system": "o/w"}
_FOOT = {"square_side_mm": 63.5}
_MFG = {"max_main_depth_um": 200.0, "max_main_width_um": 1000.0, "min_wall_um": 5.0}
_OP = {"Po_mbar": 500.0, "Qw_mlhr": 5.0}


def test_serpentine_compile_and_solve_runs():
    fam = get_family("serpentine")
    params = {
        "main": {"depth_um": 200, "width_um": 1000},
        "rung": {"length_mm": 4, "upstream_width_um": 15, "N": 1000},
        "junction": {"exit_width_um": 60, "exit_depth_um": 20, "pitch_um": 120},
    }
    cm = fam.evaluate(params, fluids=_FLUIDS, footprint=_FOOT,
                      manufacturing=_MFG, operating=_OP, label="t")
    assert cm.error is None
    assert cm.N_dfu == 1000
    assert cm.throughput_mlhr > 0
    assert cm.regime_Ca is not None      # gamma > 0 -> exit-Ca computed
    assert cm.manufacturable is True     # 200×1000 within caps


def test_design_from_target_droplet():
    fam = get_family("serpentine")
    params = {
        "main": {"depth_um": 200, "width_um": 1000},
        "rung": {"length_mm": 4, "upstream_width_um": 15, "N": 500},
        "target_droplet_um": 10.0,
    }
    cm = fam.evaluate(params, fluids=_FLUIDS, footprint=_FOOT,
                      manufacturing=_MFG, operating=_OP, label="d10")
    assert cm.error is None
    # derived junction should reproduce ~the target droplet size
    assert cm.droplet_um == pytest.approx(10.0, rel=0.05)


# ---------------------------------------------------------------------------
# Scoring: worst-category-wins + N-A grey
# ---------------------------------------------------------------------------

_SCORING = {
    "throughput_mlhr":   {"green": 5, "orange": 1, "higher_better": True},
    "uniformity_pct":    {"green": 20, "orange": 100},
    "operating_Po_mbar": {"green": 100, "orange": 500},
    "regime_Ca":         {"green": 0.01, "orange": 0.3},
    "build":             {"fits_square": "required"},
}
_APPLICABLE = {"throughput_mlhr", "uniformity_pct", "operating_Po_mbar", "regime_Ca", "build"}


def _cm(**kw):
    base = dict(family="serpentine", label="x")
    base.update(kw)
    return CommonMetrics(**base)


def test_scoring_all_green():
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, operating_Po_mbar=50,
             regime_Ca=0.005, fits_square=True, manufacturable=True)
    sr = score_metrics(cm, _SCORING, _APPLICABLE)
    assert sr.overall == "green"
    assert sr.chips == []


def test_scoring_worst_of_wins():
    # throughput green, but flatness red -> overall red
    cm = _cm(throughput_mlhr=10, uniformity_pct=500, operating_Po_mbar=50,
             regime_Ca=0.005, fits_square=True, manufacturable=True)
    sr = score_metrics(cm, _SCORING, _APPLICABLE)
    assert sr.overall == "red"
    assert any("flatness" in c.lower() for c in sr.chips)


def test_scoring_orange_when_worst_is_orange():
    cm = _cm(throughput_mlhr=3, uniformity_pct=5, operating_Po_mbar=50,
             regime_Ca=0.005, fits_square=True, manufacturable=True)
    sr = score_metrics(cm, _SCORING, _APPLICABLE)
    assert sr.overall == "orange"


def test_scoring_na_is_grey_not_counted():
    # regime_Ca None -> grey; everything else green -> overall green
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, operating_Po_mbar=50,
             regime_Ca=None, fits_square=True, manufacturable=True)
    sr = score_metrics(cm, _SCORING, _APPLICABLE)
    assert sr.cells["regime_Ca"].category == "grey"
    assert sr.overall == "green"


def test_scoring_fits_square_gate_forces_red():
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, operating_Po_mbar=50,
             regime_Ca=0.005, fits_square=False, manufacturable=True)
    sr = score_metrics(cm, _SCORING, _APPLICABLE)
    assert sr.overall == "red"


# ---------------------------------------------------------------------------
# End-to-end: the shipped template loads and runs
# ---------------------------------------------------------------------------

def test_template_study_runs_end_to_end(tmp_path):
    from stepgen.studio import run_study, write_workbook

    study = load_study(TEMPLATE)
    assert len(study.points) == 27          # 3 depth × 3 width × 3 length
    result = run_study(study)
    assert all(m.error is None for m in result.metrics)

    chapter = write_workbook(result, tmp_path / "chapter.html")
    assert chapter.exists()
    assert chapter.with_suffix(".json").exists()
    assert chapter.stat().st_size > 10_000


def _payload_of(chapter):
    """The interactive payload back out of a written chapter."""
    import json as _json
    html = chapter.read_text(encoding="utf-8")
    i = html.index("const CHAPTER=") + len("const CHAPTER=")
    j = html.index(";</script>", i)
    return _json.loads(html[i:j].replace("<\\/", "</"))


def test_chapter_carries_gamma_and_per_metric_margins(tmp_path):
    """
    Both sidecars must record γ and the per-metric margins.

    Ca ∝ 1/γ exactly and γ varies 3x across this repo's configs, so a Ca number
    travelling without its γ cannot be re-checked and must never be pooled with
    another chapter's.  The chapter is filter-first, so γ has to ride on the
    *row* — a study-level constant stops applying the moment a reader narrows
    to a subset that mixes fluid systems.
    """
    import json as _json
    from stepgen.studio import run_study, write_workbook

    study = load_study(TEMPLATE)
    gamma = float(study.raw["fluids"]["gamma"])          # 0.015 N/m in the template
    result = run_study(study)
    chapter = write_workbook(result, tmp_path / "chapter.html")

    side = _json.loads(chapter.with_suffix(".json").read_text(encoding="utf-8"))
    assert side["fluids"]["gamma_Nm"] == pytest.approx(gamma)
    assert side["fluids"]["uniform"] is True
    assert side["rows"][0]["metrics"]["gamma_Nm"] == pytest.approx(gamma)
    # per-metric margin, not just the weakest link
    assert isinstance(side["rows"][0]["margins"]["regime_Ca"], float)

    payload = _payload_of(chapter)
    assert all(r["gamma"] == pytest.approx(gamma) for r in payload["rows"])
    assert isinstance(payload["rows"][0]["margins"]["regime_Ca"], float)
    # the filter bar has to be able to say which γ the visible rows used
    html = chapter.read_text(encoding="utf-8")
    assert "gammanote" in html and "paintGamma" in html


# ---------------------------------------------------------------------------
# Phase 2 — radial family (§11 L_eff + hub-ΔP corrections)
# ---------------------------------------------------------------------------

import math

CROSS = REPO / "configs" / "study_serpentine_vs_radial.yaml"

_RADIAL_PARAMS = {
    "radius_mm": 63.5,
    "upstream_width_um": 8,
    "exit": {"width_um": 30, "depth_um": 10, "pitch_um": 60},
    "inlet_radius_mm": 1.0,
}
_RAD_FLUIDS = {"mu_dispersed": 0.06, "gamma": 0.005}


def _uncorrected_q_ulhr(w_um, R_mm=63.5, pitch_um=60.0, h_um=10.0, mu=0.06, dP_mbar=200.0):
    """
    Design-notes §2 closed form with L = R (no L_eff, no hub) — the anchor.

    Uses the library's rectangular-duct resistance rather than restating it, per
    W2-2: a test that carries its own copy of the formula stops testing the model
    the moment the model changes, which is exactly what happened here.
    """
    from stepgen.models.resistance import hydraulic_resistance_rectangular

    w, R, pitch, h = w_um * 1e-6, R_mm * 1e-3, pitch_um * 1e-6, h_um * 1e-6
    r_dfu = hydraulic_resistance_rectangular(mu, R, w, h)
    n = int(2.0 * math.pi * R / pitch)
    q = n * (dP_mbar * 100.0) / r_dfu
    return q * 1e9 * 3600.0


def test_radial_registered_and_contract():
    fam = get_family("radial")
    metrics = fam.applicable_metrics()
    assert "hub_budget_pct" in metrics          # radial-specific gate
    assert "uniformity_pct" not in metrics      # flatness is automatic -> grey


def test_radial_s2_anchor_uncorrected_matches_notes():
    # design_notes §2 (L = R form): w=30 µm -> 248 µL/hr, unchanged by W2-1.
    assert _uncorrected_q_ulhr(30) == pytest.approx(248, abs=3)
    # w=8 µm was 17.8 µL/hr in the notes and is 27.6 after W2-1. The notes used
    # the retired `1 - 0.63·h/w` factor, and 8 µm wide x 10 µm deep is precisely
    # the case it cannot represent: h/w = 1.25 puts it 79% of the way to the
    # singularity at 1.587, so it over-stated the resistance by 55%. The exact
    # duct solution is what the +55% is measured against — see
    # tests/test_resistance.py::TestExactSolution.
    assert _uncorrected_q_ulhr(8) == pytest.approx(27.6, abs=0.3)


def test_radial_leff_factor_matches_formula():
    from stepgen.families.radial import RadialFamily

    fam = RadialFamily()
    for w in (8, 20, 30):
        params = dict(_RADIAL_PARAMS, upstream_width_um=w, inlet_radius_mm=1000.0)  # hub off
        cm = fam.evaluate(params, fluids=_RAD_FLUIDS, footprint=_FOOT,
                          manufacturing=_MFG, operating={"Po_mbar": 200.0},
                          label=f"r{w}")
        assert cm.error is None
        t_min, pitch = 5.0, 60.0
        expected_factor = pitch / (pitch - w - t_min)
        assert cm.raw["L_eff_factor"] == pytest.approx(expected_factor, rel=1e-9)
        # Q must equal the §2 uncorrected value × the L_eff factor (hub off)
        q_expected = _uncorrected_q_ulhr(w) * expected_factor
        assert cm.raw["Q_total_uL_hr"] == pytest.approx(q_expected, rel=1e-6)


def test_radial_uniformity_is_na_grey():
    from stepgen.families.radial import RadialFamily

    cm = RadialFamily().evaluate(_RADIAL_PARAMS, fluids=_RAD_FLUIDS, footprint=_FOOT,
                                 manufacturing=_MFG, operating={"Po_mbar": 200.0}, label="r")
    assert cm.uniformity_pct is None            # -> grey in the scorer
    assert cm.hub_budget_pct is not None


def test_radial_hub_budget_grows_with_width():
    """§11.3: narrow channels ~manageable hub ΔP; wide channels blow the budget."""
    from stepgen.families.radial import RadialFamily

    fam = RadialFamily()
    def hub_pct(w):
        cm = fam.evaluate(dict(_RADIAL_PARAMS, upstream_width_um=w), fluids=_RAD_FLUIDS,
                          footprint=_FOOT, manufacturing=_MFG,
                          operating={"Po_mbar": 200.0}, label=f"r{w}")
        return cm.hub_budget_pct
    p10, p20, p30 = hub_pct(10), hub_pct(20), hub_pct(30)
    assert p10 < p20 < p30
    # Bounds widened from `< 20` after W2-1: at w = 10 µm, h = 10 µm the exact
    # duct resistance is lower than the retired correction gave, so the channels
    # draw more and the hub takes a larger share (20.6%, was just under 20).
    # The ordering above is the physics; these are guard rails.
    assert p10 < 25            # narrow channel: modest hub budget
    assert p30 > 50            # wide channel: hub eats most of the supply


def test_radial_ca_is_viscosity_independent():
    from stepgen.families.radial import RadialFamily

    fam = RadialFamily()
    ca1 = fam.evaluate(_RADIAL_PARAMS, fluids={"mu_dispersed": 0.06, "gamma": 0.005},
                       footprint=_FOOT, manufacturing=_MFG,
                       operating={"Po_mbar": 200.0}, label="a").regime_Ca
    ca2 = fam.evaluate(_RADIAL_PARAMS, fluids={"mu_dispersed": 0.12, "gamma": 0.005},
                       footprint=_FOOT, manufacturing=_MFG,
                       operating={"Po_mbar": 200.0}, label="b").regime_Ca
    assert ca1 == pytest.approx(ca2, rel=1e-9)   # µ cancels in Poiseuille + Ca


def test_radial_fits_square_gate():
    from stepgen.families.radial import RadialFamily

    fam = RadialFamily()
    foot = {"square_side_mm": 100.0}
    small = fam.evaluate(dict(_RADIAL_PARAMS, radius_mm=20), fluids=_RAD_FLUIDS,
                         footprint=foot, manufacturing=_MFG,
                         operating={"Po_mbar": 200.0}, label="s")
    big = fam.evaluate(dict(_RADIAL_PARAMS, radius_mm=63.5), fluids=_RAD_FLUIDS,
                       footprint=foot, manufacturing=_MFG,
                       operating={"Po_mbar": 200.0}, label="b")
    assert small.fits_square is True             # 40 mm wheel in a 100 mm die
    assert big.fits_square is False              # 127 mm wheel does not fit


def test_radial_overlapping_channels_error():
    from stepgen.families.radial import RadialFamily

    # w_up + t_min >= pitch -> channels overlap everywhere -> captured error
    cm = RadialFamily().evaluate(
        dict(_RADIAL_PARAMS, upstream_width_um=60),   # 60 + 5 >= 60 pitch
        fluids=_RAD_FLUIDS, footprint=_FOOT, manufacturing=_MFG,
        operating={"Po_mbar": 200.0}, label="bad")
    assert cm.error is not None
    assert "overlap" in cm.error.lower()


def test_radial_hub_budget_scores_grey_for_serpentine():
    # hub_budget_pct is not applicable to serpentine -> grey, even if scored
    serp = get_family("serpentine")
    cm = serp.evaluate(
        {"main": {"depth_um": 200, "width_um": 1000},
         "rung": {"length_mm": 4, "upstream_width_um": 15, "N": 500},
         "junction": {"exit_width_um": 30, "exit_depth_um": 10, "pitch_um": 60}},
        fluids=_FLUIDS, footprint=_FOOT, manufacturing=_MFG, operating=_OP, label="s")
    scoring = dict(_SCORING, hub_budget_pct={"green": 15, "orange": 50})
    sr = score_metrics(cm, scoring, serp.applicable_metrics())
    assert sr.cells["hub_budget_pct"].category == "grey"


# ---------------------------------------------------------------------------
# Phase 2 — references (click-in overlays) + cross-topology study
# ---------------------------------------------------------------------------

def test_reference_modelled_resolves():
    from stepgen.studio.study import load_study
    from stepgen.studio.references import resolve_references

    study = load_study(CROSS)
    refs = resolve_references(study)
    modelled = [r for r in refs if r.kind == "modelled"]
    assert modelled and modelled[0].error is None
    assert modelled[0].points[0].throughput_mlhr is not None


def test_reference_experimental_column_adapter():
    from stepgen.studio.study import load_study
    from stepgen.studio.references import resolve_references

    study = load_study(CROSS)
    refs = resolve_references(study)
    exp = [r for r in refs if r.kind == "experimental"]
    assert exp, "cross-topology study declares an experimental reference"
    rs = exp[0]
    assert rs.error is None, rs.error
    # adapter mapped DispPhasePressure->Po and Droplet_diameter_um->droplet_um
    assert all(p.operating_Po_mbar is not None for p in rs.points)
    assert any(p.droplet_um is not None for p in rs.points)


def test_reference_unknown_kind_is_captured():
    from stepgen.studio.references import resolve_references

    class _S:
        source_path = str(CROSS)
        references = [{"kind": "bogus", "label": "x"}]
    refs = resolve_references(_S())
    assert refs[0].error is not None and "unknown" in refs[0].error.lower()


def test_cross_topology_study_runs(tmp_path):
    from stepgen.studio import run_study, write_workbook

    study = load_study(CROSS)
    assert set(study.families) == {"serpentine", "radial"}
    result = run_study(study)
    # every point solves (radial overlap guarded by the config's pitch/width)
    assert all(m.error is None for m in result.metrics), \
        [m.error for m in result.metrics if m.error]

    fams = {m.family for m in result.metrics}
    assert fams == {"serpentine", "radial"}
    # radial rows: uniformity N-A, hub-budget populated; serpentine the reverse
    for m in result.metrics:
        if m.family == "radial":
            assert m.uniformity_pct is None
            assert m.hub_budget_pct is not None
        else:
            assert m.hub_budget_pct is None

    chapter = write_workbook(result, tmp_path / "cross.html")
    assert chapter.exists()
    doc = chapter.read_text(encoding="utf-8")
    assert "references" in doc          # overlay toggle rendered
    assert "V5-8-1 (experiment)" in doc  # experimental overlay listed in provenance


# ---------------------------------------------------------------------------
# Phase 3 — nodal-graph solver + manifold (comb) family
# ---------------------------------------------------------------------------
ALL_FAMILIES = REPO / "configs" / "study_all_families.yaml"


def _manifold_params(M, n, *, arm_w=200, cont_phase=None, wall=None):
    p = {
        "main": {"depth_um": 200, "width_um": 1000},
        "arms": {"count": M, "depth_um": 100, "width_um": arm_w},
        "rung": {"length_mm": 2, "upstream_width_um": 30},
        "rungs_per_arm": n,
        "junction": {"exit_width_um": 30, "exit_depth_um": 20, "pitch_um": 120},
    }
    if cont_phase is not None:
        p["cont_phase"] = cont_phase
    if wall is not None:
        p["wall"] = wall
    return p


_MF_FLUIDS = {"mu_dispersed": 0.06, "gamma": 0.015}
_MF_FOOT = {"square_side_mm": 100.0}
_MF_MFG = {"min_wall_um": 5, "max_main_depth_um": 200, "max_main_width_um": 1000}
_MF_OP = {"Po_mbar": 500}


def _solve_manifold(M, n, **kw):
    return get_family("manifold").evaluate(
        _manifold_params(M, n, **kw), fluids=_MF_FLUIDS, footprint=_MF_FOOT,
        manufacturing=_MF_MFG, operating=_MF_OP, label=f"M{M}n{n}")


def test_nodal_solver_divider_anchor_is_exact():
    """Series/parallel divider: P_A = P_in·(R2‖R3)/(R1 + R2‖R3), exactly."""
    from stepgen.models.nodal_network import NodalNetwork
    net = NodalNetwork()
    src, a, gnd = net.add_node(), net.add_node(), net.add_node()
    net.fix(src, 1000.0); net.fix(gnd, 0.0)
    R1, R2, R3 = 2.0, 5.0, 3.0
    net.add_edge(src, a, R1); net.add_edge(a, gnd, R2); net.add_edge(a, gnd, R3)
    P = net.solve()
    Rpar = 1.0 / (1.0 / R2 + 1.0 / R3)
    expected = 1000.0 * Rpar / (R1 + Rpar)
    assert P[a] == pytest.approx(expected, rel=1e-12)


def test_nodal_solver_series_conserves_flow():
    """Two resistors in series carry identical flow (KCL)."""
    from stepgen.models.nodal_network import NodalNetwork
    net = NodalNetwork()
    src, a, gnd = net.add_node(), net.add_node(), net.add_node()
    net.fix(src, 500.0); net.fix(gnd, 0.0)
    e1 = net.add_edge(src, a, 2.0)
    e2 = net.add_edge(a, gnd, 7.0)
    P = net.solve()
    assert net.edge_flow(e1, P) == pytest.approx(net.edge_flow(e2, P), rel=1e-12)


def test_nodal_solver_current_injection_anchor():
    """A flow Q injected at a node draining through R to ground gives P = Q·R."""
    from stepgen.models.nodal_network import NodalNetwork
    net = NodalNetwork()
    a, gnd = net.add_node(), net.add_node()
    net.fix(gnd, 0.0)
    Q, R = 3.0e-9, 2.0e12
    net.inject(a, Q)
    e = net.add_edge(a, gnd, R)
    P = net.solve()
    assert P[a] == pytest.approx(Q * R, rel=1e-12)
    assert net.edge_flow(e, P) == pytest.approx(Q, rel=1e-12)   # all injected flow drains


def test_manifold_two_rail_has_local_water_pressure():
    """The comb now solves a real water rail: P_water varies rung-to-rung and the
    per-rung driving ΔP = P_oil − P_water is what sets the flow (not a fixed sink)."""
    cm = _solve_manifold(20, 100)
    assert cm.error is None
    r = cm.raw
    # water side is not a flat ground: it droops along the collection channel
    assert r["P_water_max_mbar"] > r["P_water_min_mbar"]
    # and the oil rail sits above the water rail everywhere (positive rung ΔP)
    assert r["dP_rung_min_mbar"] > 0.0
    assert r["r_water_Pa_s_m3"] > 0.0


def test_manifold_registered_and_contract():
    fam = get_family("manifold")
    metrics = fam.applicable_metrics()
    assert "uniformity_pct" in metrics    # comb has a real ΔP-flatness axis
    assert "build" in metrics             # carries the no_crossing gate
    assert "manifold" in list_families()


def test_manifold_dfu_count_is_arms_times_rungs():
    cm = _solve_manifold(50, 80)
    assert cm.error is None
    assert cm.N_dfu == 50 * 80


def test_manifold_comb_flattens_vs_single_main():
    """The pinned V-curve: at equal N an intermediate arm split is flatter than
    either extreme, and far flatter than a single long main.  Absolute flatness
    now reflects the realistic arm-pitch spine length (not the old 220 µm segment,
    which understated spine droop ~20x)."""
    single = _solve_manifold(1, 4000).uniformity_pct    # one long serpentine main
    few = _solve_manifold(5, 800).uniformity_pct        # too few arms → long arm droop
    mid = _solve_manifold(20, 200).uniformity_pct       # V-curve interior optimum
    many = _solve_manifold(80, 50).uniformity_pct       # too many arms → long spine droop
    assert single > 1000                                # single main starves the far end
    assert mid < few and mid < many                     # interior optimum (V-curve)
    assert mid < single / 10                            # comb cuts ΔP spread >1 order


def test_manifold_no_crossing_gate_flips_with_wall():
    # The loop stays open when the collection channel + separating wall are both
    # manufacturable; it breaks when the cont-phase channel drops below min feature.
    ok = _solve_manifold(20, 80)                                           # default 200 µm cont-phase
    bad = _solve_manifold(20, 80, cont_phase={"width_um": 2, "flow_scaled": False})
    assert ok.no_crossing is True
    assert bad.no_crossing is False


def test_manifold_no_crossing_scores_red_when_required():
    """A study that requires no_crossing must force a loop-less comb to red."""
    bad = _solve_manifold(20, 80, cont_phase={"width_um": 2, "flow_scaled": False})
    scoring = {
        "uniformity_pct": {"green": 20, "orange": 100},
        "build": {"no_crossing": "required"},
    }
    scored = score_metrics(bad, scoring, get_family("manifold").applicable_metrics())
    assert scored.overall == "red"
    assert any("no phase crossing" in c for c in scored.chips)


def test_build_points_expands_manifold_arms_axis():
    raw = {
        "family": ["manifold"],
        "operating": {"Po_mbar": 500},
        "manifold": {
            "arms": {"count": [1, 10, 50], "spacing_um": 220},
            "rungs_per_arm": [80],
        },
    }
    points = build_points(raw)
    assert len(points) == 3
    assert {p.params["arms"]["count"] for p in points} == {1, 10, 50}
    # label carries the arms axis
    assert any("M50" in p.label for p in points)


def test_all_families_study_runs():
    from stepgen.studio import run_study

    study = load_study(ALL_FAMILIES)
    assert set(study.families) == {"serpentine", "radial", "manifold"}
    result = run_study(study)
    assert all(m.error is None for m in result.metrics), \
        [m.error for m in result.metrics if m.error]
    fams = {m.family for m in result.metrics}
    assert fams == {"serpentine", "radial", "manifold"}
    for m in result.metrics:
        if m.family == "manifold":
            assert m.uniformity_pct is not None   # graded on flatness
            assert m.no_crossing is not None      # carries the gate
            assert m.hub_budget_pct is None       # radial-only, grey here


# ── W2-1a: what remains impossible after W2-1 removed the aspect rule ────────

def test_manifold_deep_narrow_dfu_compiles_and_solves():
    """
    The predicate W2-1a was originally going to enforce -- upstream_width >
    exit_depth -- is exactly the geometry of the real V5-30 DFU (8 µm wide x
    10 µm deep). W2-1 deleted the rule; this pins that it stays deleted.
    """
    from stepgen.families.manifold import ManifoldFamily

    params = {
        "arms": {"count": 8, "width_um": 200.0, "depth_um": 100.0},
        "rungs_per_arm": 20,
        "main": {"depth_um": 200.0, "width_um": 1000.0},
        "rung": {"length_mm": 2.0, "upstream_width_um": 15.0},   # 15 < 20 depth
        "junction": {"exit_width_um": 60.0, "exit_depth_um": 20.0, "pitch_um": 120.0},
    }
    cm = ManifoldFamily().evaluate(
        params, fluids={"mu_dispersed": 0.06, "gamma": 0.005},
        footprint={"square_side_mm": 100.0}, manufacturing={"min_wall_um": 5.0},
        operating={"Po_mbar": 500.0}, label="deep")
    assert cm.error is None
    assert cm.throughput_mlhr and cm.throughput_mlhr > 0


def test_manifold_impossible_geometry_fails_once_at_compile():
    """Non-positive and sub-fab dimensions raise, naming the config field."""
    import pytest as _pytest

    from stepgen.families.manifold import ManifoldFamily

    base = {
        "arms": {"count": 8, "width_um": 200.0, "depth_um": 100.0},
        "rungs_per_arm": 20,
        "main": {"depth_um": 200.0, "width_um": 1000.0},
        "rung": {"length_mm": 2.0, "upstream_width_um": 15.0},
        "junction": {"exit_width_um": 60.0, "exit_depth_um": 20.0, "pitch_um": 120.0},
    }
    fam = ManifoldFamily()
    kw = dict(fluids={"mu_dispersed": 0.06}, footprint={"square_side_mm": 100.0},
              manufacturing={"min_wall_um": 5.0})

    bad = {**base, "junction": {**base["junction"], "exit_depth_um": 0.0}}
    with _pytest.raises(ValueError, match="junction.exit_depth_um"):
        fam.compile(bad, **kw)

    tiny = {**base, "rung": {**base["rung"], "upstream_width_um": 1.0}}
    with _pytest.raises(ValueError, match="min_wall_um"):
        fam.compile(tiny, **kw)


# ── W2-3: N from packing (rung.fill_fraction) ────────────────────────────────

_FF_BASE = {
    "main": {"depth_um": 200, "width_um": 1000},
    "rung": {"length_mm": 4, "upstream_width_um": 15},
    "junction": {"exit_width_um": 60, "exit_depth_um": 20, "pitch_um": 120},
}
_FF_FOOT = {"square_side_mm": 100.0}
_FF_KW = dict(fluids=_FLUIDS, footprint=_FF_FOOT, manufacturing=_MFG, operating=_OP)


def _ff_eval(**rung):
    params = {**_FF_BASE, "rung": {**_FF_BASE["rung"], **rung}}
    return get_family("serpentine").evaluate(params, label="ff", **_FF_KW)


def test_fill_fraction_scales_N_linearly():
    full = _ff_eval(fill_fraction=1.0)
    half = _ff_eval(fill_fraction=0.5)
    assert full.error is None and half.error is None
    assert full.N_dfu > 0
    assert half.N_dfu == pytest.approx(full.N_dfu / 2, rel=0.01)


def test_fill_fraction_one_fits_by_construction():
    """
    ff = 1.0 inverts exactly what the fits-square check applies, so a full-die
    design must fit. If this ever fails, dfu_capacity and compute_layout have
    drifted apart -- which is the whole reason they are one function.
    """
    cm = _ff_eval(fill_fraction=1.0)
    assert cm.fits_square is True


def test_fill_fraction_matches_the_packing_readout():
    """The input and the readout are the same number, not two estimates."""
    fam = get_family("serpentine")
    params = {**_FF_BASE, "rung": {**_FF_BASE["rung"], "fill_fraction": 1.0}}
    compiled = fam.compile(params, fluids=_FLUIDS, footprint=_FF_FOOT,
                           manufacturing=_MFG)
    cap = fam.packing_capacity(compiled)
    assert cap is not None
    assert cap.n_current == cap.n_max


def test_only_one_dfu_count_source_allowed():
    fam = get_family("serpentine")
    kw = dict(fluids=_FLUIDS, footprint=_FF_FOOT, manufacturing=_MFG)

    with pytest.raises(ValueError, match="exactly one"):
        fam.compile({**_FF_BASE, "rung": {**_FF_BASE["rung"], "fill_fraction": 1.0,
                                          "N": 500}}, **kw)
    # the message must name the N each source implies, not just refuse
    try:
        fam.compile({**_FF_BASE, "rung": {**_FF_BASE["rung"], "fill_fraction": 1.0,
                                          "N": 500}}, **kw)
    except ValueError as exc:
        assert "rung.N=500 implies N=500" in str(exc)
        assert "rung.fill_fraction=1.0 implies N=" in str(exc)


def test_fill_fraction_out_of_range_raises():
    fam = get_family("serpentine")
    kw = dict(fluids=_FLUIDS, footprint=_FF_FOOT, manufacturing=_MFG)
    for bad in (1.5, 0.0, -0.2):
        with pytest.raises(ValueError, match=r"must be in \(0, 1\]"):
            fam.compile({**_FF_BASE,
                         "rung": {**_FF_BASE["rung"], "fill_fraction": bad}}, **kw)


def test_fill_fraction_failure_is_reported_not_swallowed():
    """`evaluate` turns a compile error into a row with `.error` set, not a crash."""
    cm = _ff_eval(fill_fraction=1.5)
    assert cm.error is not None
    assert "fill_fraction" in cm.error


def test_fill_fraction_reaches_the_label():
    from stepgen.studio.study import build_points

    raw = {
        "family": "serpentine",
        "operating": {"Po_mbar": 500, "Qw_mlhr": 5},
        "serpentine": {**_FF_BASE,
                       "rung": {**_FF_BASE["rung"], "fill_fraction": [1.0, 0.75]}},
    }
    labels = [p.label for p in build_points(raw)]
    assert any("Ff1" in lab for lab in labels)
    assert any("Ff0.75" in lab for lab in labels)
    assert len(set(labels)) == 2      # must not collide


# ── W2-4: provenance to scoring (decision 10) ────────────────────────────────

_W24_SCORING = {
    "throughput_mlhr": {"green": 5, "orange": 1, "higher_better": True},
    "uniformity_pct": {"green": 20, "orange": 100},
    # note: no `build:` block at all -- this is what study_template.yaml does,
    # and it is the case that used to score a phase-crossing design green in
    # total silence.
}
_W24_APPLICABLE = {"throughput_mlhr", "uniformity_pct", "build"}


def _w24(pinned, **gates):
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, **gates)
    return score_metrics(cm, _W24_SCORING, _W24_APPLICABLE, pinned=pinned)


def test_pinned_geometry_breaching_every_fab_cap_is_not_red():
    """
    A hand-written study is the user's own numbers. Decision 10: report them,
    do not fail the row -- the physics gates still decide the verdict.
    """
    sr = _w24(True, fits_square=False, manufacturable=False, no_crossing=False)
    assert sr.overall != "red"
    assert sr.cells["build"].category == "green"


def test_every_demoted_gate_emits_a_chip():
    """
    The regression this item exists to fix: only `manufacturable` used to say
    anything when demoted, so a design that does not fit the die or crosses
    phases passed with NO chip at all.
    """
    sr = _w24(True, fits_square=False, manufacturable=False, no_crossing=False)
    text = " ".join(sr.chips)
    for phrase in ("fits die square", "within fab caps", "no phase crossing"):
        assert phrase in text, f"demoted gate {phrase!r} vanished silently"
    assert set(sr.cells["build"].reported) == {
        "fits_square", "manufacturable", "no_crossing"}


def test_required_forces_gating_even_when_pinned():
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, manufacturable=False)
    spec = {**_W24_SCORING, "build": {"manufacturable": "required"}}
    sr = score_metrics(cm, spec, _W24_APPLICABLE, pinned=True)
    assert sr.overall == "red"
    assert sr.cells["build"].detail == ["manufacturable"]


def test_generated_geometry_is_gated_without_asking():
    """
    The other half of decision 10: a value the TOOL chose that breaches a
    constraint is the gate doing its job.
    """
    sr = _w24(False, fits_square=False)
    assert sr.overall == "red"
    assert sr.cells["build"].detail == ["fits_square"]
    assert sr.cells["build"].reported == []


def test_off_silences_a_gate_entirely():
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, no_crossing=False)
    spec = {**_W24_SCORING, "build": {"no_crossing": "off"}}
    sr = score_metrics(cm, spec, _W24_APPLICABLE, pinned=False)
    assert sr.overall != "red"
    assert not any("phase crossing" in c for c in sr.chips)


def test_hand_written_study_is_pinned_intent_study_is_not():
    from stepgen.studio.scoring import geometry_is_pinned

    class _Plan:
        generated = ["serpentine"]
        user_supplied = ["manifold"]

    class _Study:
        from_intent = True
        intent_plan = _Plan()

    assert geometry_is_pinned(None, "serpentine") is True        # no study at all
    assert geometry_is_pinned(_Study(), "serpentine") is False   # tool chose it
    assert geometry_is_pinned(_Study(), "manifold") is True      # user chose it


def test_diagnosis_names_a_reported_breach_instead_of_burying_it():
    """
    "Relax the depth cap: nothing changes" is true and useless if the reader is
    never told their pinned depth is over the cap.
    """
    from stepgen.studio.diagnosis import diagnose
    from stepgen.studio.study import Study

    rows = [_w24(True, manufacturable=False) for _ in range(3)]
    study = Study(title="t", goal="", families=["serpentine"], scoring=_W24_SCORING,
                  references=[], points=[])
    diag = diagnose(study, rows, price="never")
    assert diag.reported_not_gated == {"manufacturable": 3}
    assert "reported, not gated" in diag.headline().lower()
    assert "within fab caps" in diag.headline()


# ── D2: the three-state gate control, in the chapter ─────────────────────────
#
# The UI half of W2-4. These tests guard the one thing that makes a client-side
# gate control safe: with no override set it must reproduce Python's verdict
# exactly, and every category it can produce must be one Python computed.

def test_build_gate_states_resolve_the_three_words():
    from stepgen.studio.scoring import build_gate_state

    assert build_gate_state({}, "fits_square", pinned=True) == "report"
    assert build_gate_state({}, "fits_square", pinned=False) == "gate"
    assert build_gate_state({"fits_square": "required"}, "fits_square",
                            pinned=True) == "gate"
    assert build_gate_state({"fits_square": "off"}, "fits_square",
                            pinned=False) == "off"


def test_verdict_without_build_leaves_the_rest_alone():
    """
    The half of the verdict a gate override cannot touch. A row whose ONLY
    problem is a build gate must be green without it; one that also breaches a
    physics gate must keep that verdict whatever the reader does to the gates.
    """
    only_build = _w24(False, fits_square=False)
    assert only_build.overall == "red"
    assert only_build.verdict_without_build == "green"

    also_physics = score_metrics(
        _cm(throughput_mlhr=0.5, uniformity_pct=5, fits_square=False),
        _W24_SCORING, _W24_APPLICABLE, pinned=False)
    assert also_physics.verdict_without_build == "red"


def test_the_payload_carries_each_rows_gate_states_and_provenance():
    from stepgen.studio.interactive import build_gate_json

    sr = _w24(True, fits_square=False, manufacturable=True, no_crossing=False)
    blob = build_gate_json(sr, _W24_SCORING)
    assert blob["g"] == {"fits_square": False, "manufacturable": True,
                         "no_crossing": False}
    assert blob["s"] == {"fits_square": "report", "manufacturable": "report",
                         "no_crossing": "report"}
    assert "fits die square" in blob["why"]
    assert "within fab caps" not in blob["why"]      # it passed
    assert sr.pinned is True


def test_the_control_reproduces_pythons_verdict_with_no_override():
    """
    **The invariant the whole control rests on.** Re-implement the browser's
    recombination in Python and it must agree with `overall` on every row --
    otherwise the page shows one verdict and the sidecar another, which is worse
    than having no control at all.
    """
    from stepgen.studio.interactive import build_gate_json

    rank = {"green": 0, "orange": 1, "red": 2, "grey": 0}

    def as_the_browser_would(sr, scoring, override=None):
        blob = build_gate_json(sr, scoring)
        override = override or {}
        build = "green"
        for key, ok in blob["g"].items():
            if ok is False and (override.get(key) or blob["s"][key]) == "gate":
                build = "red"
                break
        base = sr.verdict_without_build
        return build if rank[build] > rank[base] else base

    cases = [
        (_w24(True,  fits_square=False, manufacturable=False, no_crossing=False), _W24_SCORING),
        (_w24(False, fits_square=False), _W24_SCORING),
        (_w24(True,  fits_square=True,  manufacturable=True,  no_crossing=True), _W24_SCORING),
        (score_metrics(_cm(throughput_mlhr=10, uniformity_pct=5, manufacturable=False),
                       {**_W24_SCORING, "build": {"manufacturable": "required"}},
                       _W24_APPLICABLE, pinned=True),
         {**_W24_SCORING, "build": {"manufacturable": "required"}}),
        (score_metrics(_cm(throughput_mlhr=10, uniformity_pct=5, no_crossing=False),
                       {**_W24_SCORING, "build": {"no_crossing": "off"}},
                       _W24_APPLICABLE, pinned=False),
         {**_W24_SCORING, "build": {"no_crossing": "off"}}),
    ]
    for sr, scoring in cases:
        assert as_the_browser_would(sr, scoring) == sr.overall

    # ...and an override moves it, in both directions
    demoted = cases[0][0]
    assert demoted.overall != "red"
    assert as_the_browser_would(demoted, _W24_SCORING,
                                {"fits_square": "gate"}) == "red"
    gated = cases[1][0]
    assert gated.overall == "red"
    assert as_the_browser_would(gated, _W24_SCORING,
                                {"fits_square": "off"}) == "green"


def test_the_drilldown_explains_a_demoted_gate_instead_of_showing_green():
    """
    The drill-down exists to explain the colour. A build cell that is green
    *because* the failure was demoted used to say nothing at all -- the same
    silence W2-4 fixed in the chips, still live one panel down.
    """
    from stepgen.studio.workbook import _gate_table

    sr = _w24(True, fits_square=False, manufacturable=True, no_crossing=True)
    html_out = _gate_table(sr, _W24_SCORING)
    assert "fits die square" in html_out
    assert "You set this geometry" in html_out


def test_the_chapter_page_carries_the_gate_control_and_no_thresholds_in_js():
    """
    D7's invariant, written as a test rather than a comment: the browser filters
    on Python's verdict and never re-derives one from a bound.

    Reading a threshold is fine and is what the payload ships it for -- the plot
    draws the ceiling as a band. What must never happen is COMPARING a row value
    against one, because that is scoring, and scoring lives in scoring.py.
    """
    import re

    from stepgen.studio.interactive import INTERACTIVE_JS

    assert "data-gate" in INTERACTIVE_JS          # the control exists
    assert "verdictOf" in INTERACTIVE_JS

    thresholdish = r"(?:th\.(?:green|orange)|CHAPTER\.thresholds[\[.]\w*\]?)"
    compared = re.compile(thresholdish + r"\s*[<>]|[<>]=?\s*" + thresholdish)
    hit = compared.search(INTERACTIVE_JS)
    assert hit is None, f"scoring leaked into JS: {hit.group(0)!r}"


def test_the_gate_control_only_offers_sub_gates_some_row_can_answer():
    from stepgen.studio.grouping import build_grouping
    from stepgen.studio.interactive import chapter_payload
    from stepgen.studio.run import run_study
    from stepgen.studio.scoring import score_result
    from stepgen.studio.study import load_study

    study = load_study(TEMPLATE)
    study.points = study.points[:3]
    result = run_study(study)
    scored = score_result(result, study.scoring)
    grouping = build_grouping(study, study.points)
    payload = chapter_payload(scored, grouping, {}, [], {}, study.scoring)

    keys = {bg["key"] for bg in payload["buildGates"]}
    assert keys, "no build sub-gate offered at all"
    for row in payload["rows"]:
        assert set(row["b"]["g"]) <= keys
        assert set(row["b"]["s"]) == set(row["b"]["g"])
        assert row["vnb"] in {"green", "orange", "red"}
        assert isinstance(row["pin"], bool)


# ── W2-5: fold geometry, reported not gated ──────────────────────────────────

def test_bend_radius_is_half_the_lane_pitch():
    """
    A 180 degree turn between two lanes at pitch p has a centreline radius of
    p/2 and cannot have any other. On the real V5-30 the measured pitch is
    7.00 mm (reference_devices/README.md), so the fold radius is 3500 um.
    """
    from stepgen.config import load_config

    cm = solve_config(load_config(V5_30), Po_mbar=200.0, Qw_mlhr=5.0, label="v5_30")
    assert cm.bend_radius_um == pytest.approx(3500.0, rel=1e-9)
    assert cm.wall_at_turn_um == pytest.approx(6000.0, rel=1e-9)


def test_fold_radius_note_fires_when_turn_radius_disagrees():
    """v5_30.yaml carries turn_radius 500 um; the real fold is 7x that."""
    from stepgen.config import load_config

    cm = solve_config(load_config(V5_30), Po_mbar=200.0, Qw_mlhr=5.0, label="v5_30")
    assert any("fold radius" in n for n in cm.notes)


def test_fold_geometry_is_reported_never_gated():
    """No threshold, no gate: a bad fold cannot turn a row red (decision 9)."""
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, operating_Po_mbar=50,
             regime_Ca=0.005, fits_square=True, manufacturable=True,
             bend_radius_um=1.0, wall_at_turn_um=0.0)
    sr = score_metrics(cm, _SCORING, _APPLICABLE)
    assert sr.overall == "green"
    assert "bend_radius_um" not in sr.cells
    assert "wall_at_turn_um" not in sr.cells


def test_bend_radius_tracks_the_stackup_not_turn_radius():
    """Move turn_radius 60x: the fold radius must not budge (W1-1's lesson)."""
    import dataclasses

    from stepgen.config import load_config

    cfg = load_config(V5_30)
    wide = dataclasses.replace(
        cfg, footprint=dataclasses.replace(cfg.footprint, turn_radius=30e-3))
    a = solve_config(cfg, Po_mbar=200.0, Qw_mlhr=5.0, label="a")
    b = solve_config(wide, Po_mbar=200.0, Qw_mlhr=5.0, label="b")
    assert a.bend_radius_um == pytest.approx(b.bend_radius_um)


# ── W2-6: schema bump ────────────────────────────────────────────────────────

def test_both_sidecars_carry_the_same_schema_version():
    """
    Two row serialisers exist -- the JSON sidecar and the in-browser payload --
    and a version on only one of them is worse than none, because the surface a
    reader actually filters would be the unlabelled one.
    """
    from stepgen.studio.interactive import _schema_version
    from stepgen.studio.workbook import SCHEMA_VERSION

    assert _schema_version() == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 2      # Wave 2 moved every serpentine number


def test_chapter_json_and_payload_are_stamped():
    from stepgen.studio.run import run_study
    from stepgen.studio.scoring import score_result
    from stepgen.studio.study import load_study
    from stepgen.studio.workbook import SCHEMA_VERSION, _chapter_json

    study = load_study(TEMPLATE)
    study.points = study.points[:2]
    result = run_study(study)
    scored = score_result(result, study.scoring)

    assert _chapter_json(result, scored)["schema_version"] == SCHEMA_VERSION

    from stepgen.studio.grouping import build_grouping
    from stepgen.studio.interactive import chapter_payload

    grouping = build_grouping(study, study.points)
    payload = chapter_payload(scored, grouping, {}, [], {}, study.scoring)
    assert payload["schemaVersion"] == SCHEMA_VERSION


# ── velocity vs demonstrated experience (2026-08-05) ─────────────────────────

def test_v_exit_and_ratio_are_computed_from_the_solved_flow():
    from stepgen.config import load_config
    from stepgen.families.base import V_EXIT_DEMONSTRATED_MAX

    cfg = load_config(V5_30)
    cm = solve_config(cfg, Po_mbar=600.0, Qw_mlhr=5.0, label="v5_30")
    jc = cfg.geometry.junction
    q = cm.raw["Q_per_rung_avg"]

    assert cm.v_exit_mps == pytest.approx(q / (jc.exit_width * jc.exit_depth))
    assert cm.v_vs_demonstrated == pytest.approx(
        cm.v_exit_mps / V_EXIT_DEMONSTRATED_MAX)


def test_the_anchor_is_the_condition_it_was_measured_at():
    """
    V5-30 at 600 mbar / Qw 5 is the condition V_EXIT_DEMONSTRATED_MAX came from,
    so the model must land near 1x there. It sits slightly above because the
    anchor is the cycle-average (conservation) estimate while the model's Q sits
    between the two experimental estimates -- see comp_oil_viscosity.
    """
    from stepgen.config import load_config

    cm = solve_config(load_config(V5_30), Po_mbar=600.0, Qw_mlhr=5.0, label="x")
    assert 1.0 <= cm.v_vs_demonstrated <= 1.3


def test_the_ratio_carries_no_unmeasured_constant():
    """
    gamma cancels exactly: the ratio is identical whatever interfacial tension
    the study assumes, which is the whole reason it exists.
    """
    import dataclasses

    from stepgen.config import load_config

    cfg = load_config(V5_30)
    a = solve_config(cfg, Po_mbar=400.0, Qw_mlhr=5.0, label="a")
    hi = dataclasses.replace(cfg, fluids=dataclasses.replace(cfg.fluids, gamma=0.020))
    b = solve_config(hi, Po_mbar=400.0, Qw_mlhr=5.0, label="b")
    assert a.v_vs_demonstrated == pytest.approx(b.v_vs_demonstrated)


def test_ca_and_velocity_can_never_turn_a_row_red():
    """
    Both are capped at orange. Ca because gamma is unmeasured; velocity because
    "nobody has been past 1x" is a statement about our experience, not physics.
    """
    from stepgen.studio.scoring import CAPPED_AT_ORANGE

    assert CAPPED_AT_ORANGE == frozenset({"regime_Ca", "v_vs_demonstrated"})
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, operating_Po_mbar=50,
             regime_Ca=5.0, v_vs_demonstrated=300.0,
             fits_square=True, manufacturable=True)
    sr = score_metrics(cm, {**_SCORING, "v_vs_demonstrated": {"green": 1, "orange": 10}},
                       _APPLICABLE | {"v_vs_demonstrated"})
    assert sr.overall == "orange"
    assert sr.cells["regime_Ca"].category == "orange"
    assert sr.cells["v_vs_demonstrated"].category == "orange"


def test_a_hopeless_design_still_says_how_hopeless():
    """Capping the colour must not hide the magnitude."""
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, operating_Po_mbar=50,
             regime_Ca=0.5, v_vs_demonstrated=308.0,
             fits_square=True, manufacturable=True)
    sr = score_metrics(cm, {**_SCORING, "v_vs_demonstrated": {"green": 1, "orange": 10}},
                       _APPLICABLE | {"v_vs_demonstrated"})
    text = " ".join(sr.chips)
    assert "308" in text
    assert "nobody has been past 1x" in text


def test_the_velocity_ratio_is_scored_without_the_study_asking():
    """
    Its bounds are facts about what Peak has run, not a modelling choice, so a
    study should not have to opt in to being told it is 47x outside experience.
    """
    cm = _cm(throughput_mlhr=10, uniformity_pct=5, v_vs_demonstrated=47.0,
             fits_square=True, manufacturable=True)
    sr = score_metrics(cm, {"throughput_mlhr": {"green": 5, "orange": 1,
                                                "higher_better": True}},
                       {"throughput_mlhr", "v_vs_demonstrated"})
    assert sr.cells["v_vs_demonstrated"].category == "orange"


# ── gated_summary: the operating gate, re-pointed off Ca (D5, 2026-08-05) ────
#
# The predicate is v_vs_demonstrated <= k, not Ca <= ca_max.  These tests exist
# mostly to stop Ca creeping back into it: the whole value of the change is that
# no unmeasured constant decides which pressure a design may claim.

def _gated_frame():
    """
    Two designs x four pressures, hand-built so the expected answer is readable.

    A's velocity crosses 1.0 between 400 and 600 mbar; B is over everywhere.
    Ca is set to DISAGREE with the velocity ordering on purpose -- B has the
    lower Ca at every point, so anything gating on Ca would pick B.
    """
    import pandas as pd

    rows = []
    for po, va, vb in [(200, 0.4, 3.0), (400, 0.9, 6.0),
                       (600, 1.4, 9.0), (800, 2.0, 12.0)]:
        rows.append(dict(label=f"A_Po{po}", operating_Po_mbar=float(po),
                         v_vs_demonstrated=va, regime_Ca=0.02,
                         throughput_mlhr=va * 10, frequency_hz=va * 2,
                         gamma_Nm=0.005))
        rows.append(dict(label=f"B_Po{po}", operating_Po_mbar=float(po),
                         v_vs_demonstrated=vb, regime_Ca=0.001,
                         throughput_mlhr=vb * 10, frequency_hz=vb * 2,
                         gamma_Nm=0.005))
    return pd.DataFrame(rows)


def test_gate_picks_the_highest_pressure_inside_experience():
    from stepgen.families.serpentine import gated_summary

    out = gated_summary(_gated_frame())
    a = out[out["label"].str.startswith("A")].iloc[0]

    assert a["Po_gated_mbar"] == 400.0          # 600 mbar is 1.4x
    assert a["v_vs_demonstrated_gated"] == pytest.approx(0.9)
    assert a["throughput_gated"] == pytest.approx(9.0)
    assert a["Po_next_failed"] == 600.0         # unsimulated headroom, 400->600


def test_a_design_outside_experience_everywhere_gates_to_nan():
    import pandas as pd

    from stepgen.families.serpentine import gated_summary

    out = gated_summary(_gated_frame())
    b = out[out["label"].str.startswith("B")].iloc[0]
    assert pd.isna(b["Po_gated_mbar"])
    assert pd.isna(b["throughput_gated"])
    assert b["Po_next_failed"] == 200.0


def test_ca_is_reported_but_does_not_decide():
    """
    B has the lower Ca at every pressure and the higher velocity at every
    pressure. A Ca gate would hand B the win; the experience gate refuses it.
    This is the 2026-08-05 ruling, expressed as a test.
    """
    import pandas as pd

    from stepgen.families.serpentine import gated_summary

    out = gated_summary(_gated_frame())
    a = out[out["label"].str.startswith("A")].iloc[0]
    b = out[out["label"].str.startswith("B")].iloc[0]

    assert a["regime_Ca_gated"] == pytest.approx(0.02)   # reported...
    assert a["Po_gated_mbar"] == 400.0                   # ...but not consulted
    assert pd.isna(b["regime_Ca_gated"])                 # B has no passing point
    assert "passes_at_gamma_lo" not in out.columns


def test_moving_the_multiple_re_gates_without_re_solving():
    from stepgen.families.serpentine import gated_summary

    frame = _gated_frame()
    loose = gated_summary(frame, max_v_vs_demonstrated=10.0)
    b = loose[loose["label"].str.startswith("B")].iloc[0]
    assert b["Po_gated_mbar"] == 600.0     # 9.0x passes, 12.0x does not
    assert b["Po_next_failed"] == 800.0


def test_the_gate_is_unmoved_by_gamma():
    """
    The point of the change: re-solve at 4x the interfacial tension and the
    gated pressure and throughput are identical, because gamma is not in the
    predicate. Every Ca in the frame moves; nothing the gate reads does.
    """
    import dataclasses

    import pandas as pd

    from stepgen.config import load_config
    from stepgen.families.serpentine import gated_summary

    cfg = load_config(V5_30)
    hi = dataclasses.replace(cfg, fluids=dataclasses.replace(cfg.fluids, gamma=0.020))

    def frame_for(config):
        rows = []
        for po in (200.0, 400.0, 600.0, 800.0):
            cm = solve_config(config, Po_mbar=po, Qw_mlhr=5.0, label=f"v5_30_Po{po:.0f}")
            rows.append(cm.to_row())
        return pd.DataFrame(rows).drop(columns=["_raw"])

    ref, wide = frame_for(cfg), frame_for(hi)
    assert not ref["regime_Ca"].equals(wide["regime_Ca"])      # Ca did move

    g_ref = gated_summary(ref).iloc[0]
    g_wide = gated_summary(wide).iloc[0]
    assert g_ref["Po_gated_mbar"] == g_wide["Po_gated_mbar"]
    assert g_ref["throughput_gated"] == pytest.approx(g_wide["throughput_gated"])


def test_the_retired_ca_ceiling_expressed_in_units_of_experience():
    """
    Under a single fluid the two predicates are the SAME predicate up to a
    constant: Ca = µv/γ, so ``Ca <= 0.0125`` at µ = 60 cP and γ = 5 mN/m is
    exactly ``v <= 1.0417 mm/s``, which is 8.35x V_EXIT_DEMONSTRATED_MAX.

    This is the number the 2026-08-05 ruling turned on, and it is worth pinning
    because it reads the borrowed ceiling back in units we can check. It was not
    a cautious bound: it permitted driving every DFU eight times harder than
    anything Peak has made work, and it took that permission from a gamma nobody
    has measured. Measured on the D5 worked example, gating at k = 8.35 selects
    the same operating points the retired Ca gate did.
    """
    from stepgen.families.base import V_EXIT_DEMONSTRATED_MAX

    mu, gamma, ca_ceiling = 0.06, 0.005, 0.0125
    v_allowed = ca_ceiling * gamma / mu
    assert v_allowed / V_EXIT_DEMONSTRATED_MAX == pytest.approx(8.35, abs=0.01)


def test_a_frame_without_the_velocity_column_refuses_rather_than_passes_all():
    """
    A pre-2026-08 frame silently gating nothing would read as 'every design is
    inside experience', which is the worst available answer.
    """
    from stepgen.families.serpentine import gated_summary

    frame = _gated_frame().drop(columns=["v_vs_demonstrated"])
    with pytest.raises(KeyError, match="v_vs_demonstrated"):
        gated_summary(frame)
