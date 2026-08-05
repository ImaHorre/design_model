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
