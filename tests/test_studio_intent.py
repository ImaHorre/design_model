"""
Phase 2 — the intent layer and constraint diagnosis.

Covers the roadmap's acceptance criteria for `docs/06_design_studio/roadmap_studio_v1.md`
Phase 2:

  * a user writes only `intent:` + `constraints:` + `explore:` and gets a scored
    space across three families;
  * intent -> grid for each family, with the same junction exit for all of them;
  * an infeasible study returns the binding constraint and its relaxation price,
    not an empty table;
  * diagnosis identifies a deliberately-planted single binding constraint.
"""

from __future__ import annotations

import json

import pytest
import yaml

from stepgen.families import get_family, list_families
from stepgen.families.base import CommonMetrics, Family
from stepgen.families.intent import (
    FAB_PRESETS,
    Constraints,
    Intent,
    IntentNotSupported,
    depth_for_droplet,
    dfu_count_ladder,
    droplet_for_junction,
    junction_for_droplet,
    ladder,
    pressure_sweep,
    rungs_for_ca_ceiling,
    rungs_for_throughput,
)
from stepgen.studio.diagnosis import (
    DEFAULT_GAMMA_RANGE_NM,
    EVIDENCE_THIN_GATES,
    KNOBS,
    ca_gamma_robustness,
    active_knobs,
    binding_gates,
    diagnose,
    knobs_for_gate,
    price_relaxations,
    row_failures,
    theory_limited_rows,
)
from stepgen.studio.intent import (
    expand_intent,
    generated_yaml,
    has_intent,
    parse_constraints,
    parse_intent,
)
from stepgen.studio.run import run_study
from stepgen.studio.scoring import ScoredRow, score_metrics, score_result
from stepgen.studio.study import build_study, load_study_text

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

#: The M1 question: large droplets via deep DFUs, under a stated pressure cap.
INTENT_RAW = {
    "intent": {"droplet_um": 140, "throughput_mlhr": 5},
    "constraints": {"max_Po_mbar": 300, "fab": "current", "square_side_mm": 63.5},
    "explore": ["serpentine", "radial", "manifold"],
}

_FLUIDS = {"mu_dispersed": 0.06, "mu_continuous": 0.00089, "gamma": 0.005}


def _intent() -> Intent:
    return Intent(droplet_um=140.0, throughput_mlhr=5.0)


def _constraints() -> Constraints:
    return parse_constraints({"max_Po_mbar": 300, "fab": "current"})


# A serpentine study sized so the ONLY thing wrong with it is that it does not
# fit the die — the planted binding constraint. At 20 mm it is red on
# fits_square alone; one notch of the die-side knob (x1.5 -> 30 mm) clears it.
_PLANTED = """
title: planted binding constraint
family: serpentine
fluids: {mu_dispersed: 0.06, mu_continuous: 0.00089, gamma: 0.005}
footprint: {square_side_mm: 20.0, reserve_border_mm: 2.0}
manufacturing: {max_main_depth_um: 200, max_main_width_um: 1000, min_wall_um: 5}
operating: {Po_mbar: 200, Qw_mlhr: 5}
serpentine:
  main: {depth_um: 200, width_um: 1000}
  rung: {length_mm: 2, upstream_width_um: 15, N: [1000, 1200, 1400]}
  junction: {exit_width_um: 30, exit_depth_um: 10, pitch_um: 60}
scoring:
  throughput_mlhr: {green: 0.5, orange: 0.05, higher_better: true}
  uniformity_pct: {green: 200, orange: 400}
  operating_Po_mbar: {green: 300, orange: 600}
  regime_Ca: {green: 0.0125, orange: 0.03}
  build: {from: manufacturing, fits_square: required}
"""


def _run(text_or_raw):
    """Load, run and score a study; returns ``(study, scored)``."""
    study = (load_study_text(text_or_raw) if isinstance(text_or_raw, str)
             else build_study(text_or_raw))
    result = run_study(study)
    return study, score_result(result, study.scoring)


# ---------------------------------------------------------------------------
# The inverse solve — one implementation of the rule
# ---------------------------------------------------------------------------

def test_junction_for_droplet_round_trips():
    w, h = junction_for_droplet(140.0, aspect_ratio=3.0)
    assert w == pytest.approx(3.0 * h)
    assert droplet_for_junction(w, h) == pytest.approx(140.0, rel=1e-9)


def test_a_large_droplet_needs_a_deep_exit():
    """Sanity anchor: 140 µm asks for a ~51 µm exit, 5x the fitted range."""
    h_um = depth_for_droplet(140.0, 3.0) * 1e6
    assert 45.0 < h_um < 60.0


def test_design_search_delegates_to_the_same_inverse_solve():
    """`_derive_mcd_from_ar` and the intent layer must never drift apart."""
    from types import SimpleNamespace

    from stepgen.config import DropletModelConfig
    from stepgen.design.design_search import _derive_mcd_from_ar

    # only the two attributes the helper actually reads
    spec = SimpleNamespace(
        design_targets=SimpleNamespace(target_droplet_um=25.0),
        droplet_model=DropletModelConfig(),
    )
    for ar in (2.5, 2.75, 3.0):
        assert _derive_mcd_from_ar(spec, ar) == pytest.approx(
            depth_for_droplet(25.0, ar, spec.droplet_model)
        )


def test_ca_ceiling_sizing_disagrees_with_throughput_sizing_for_deep_dfus():
    """
    The defect the Ca-aware ladder exists to close.

    Throughput sizing asks "how few DFUs deliver this at the pressure ceiling?"
    and answers by making each run fast — which is what drives Ca up. For a deep
    exit the two answers differ by more than an order of magnitude, and a grid
    generated from the throughput answer alone never visits the corner where the
    design works.
    """
    w, h = junction_for_droplet(140.0, 3.0)
    n_flow = rungs_for_throughput(
        throughput_mlhr=5.0, Po_mbar=300.0, rung_length_m=2e-3,
        upstream_width_m=1.5 * h, exit_depth_m=h, mu_dispersed=0.06)
    n_ca = rungs_for_ca_ceiling(
        throughput_mlhr=5.0, exit_width_m=w, exit_depth_m=h,
        mu_dispersed=0.06, gamma=0.005, max_exit_Ca=0.0125)

    assert n_flow < 30 and n_ca > 100
    assert n_ca > 5 * n_flow
    # the ladder must span both, not anchor on either
    rungs = dfu_count_ladder(n_flow, n_ca)
    assert min(rungs) <= n_flow and max(rungs) >= n_ca


def test_ca_ceiling_sizing_is_geometry_independent_in_velocity():
    """v_max = Ca·γ/µ is the same for every exit; only the area differs."""
    kw = dict(throughput_mlhr=5.0, mu_dispersed=0.06, gamma=0.005,
              max_exit_Ca=0.0125)
    shallow = rungs_for_ca_ceiling(exit_width_m=30e-6, exit_depth_m=10e-6, **kw)
    deep = rungs_for_ca_ceiling(exit_width_m=150e-6, exit_depth_m=50e-6, **kw)
    # area ratio is 25x, so the count ratio must be too (to rounding)
    assert shallow / deep == pytest.approx(25.0, rel=0.02)


def test_ca_sizing_declines_to_constrain_without_an_interfacial_tension():
    assert rungs_for_ca_ceiling(
        throughput_mlhr=5.0, exit_width_m=30e-6, exit_depth_m=10e-6,
        mu_dispersed=0.06, gamma=0.0, max_exit_Ca=0.0125) == 1


def test_the_pressure_sweep_reaches_low_enough_to_find_the_low_Ca_corner():
    """Deep-DFU designs that stay in SE live at the bottom of the range."""
    assert min(pressure_sweep(300.0)) <= 50.0


def test_rungs_for_throughput_falls_with_exit_depth():
    """R_rung ∝ 1/h³ — a deeper DFU carries more oil, so the ladder gets shorter."""
    kw = dict(throughput_mlhr=5.0, Po_mbar=300.0, rung_length_m=2e-3,
              mu_dispersed=0.06)
    shallow = rungs_for_throughput(upstream_width_m=30e-6, exit_depth_m=10e-6, **kw)
    deep = rungs_for_throughput(upstream_width_m=120e-6, exit_depth_m=50e-6, **kw)
    assert deep < shallow
    # the deep-DFU claim in its strong form: orders of magnitude, not percent
    assert shallow > 100 * deep


def test_ladder_and_pressure_sweep_are_bounded_and_unique():
    assert ladder(11, minimum=4, maximum=44) == [6.0, 11.0, 22.0, 44.0]
    assert ladder(1, minimum=4) == [4.0]          # clamped and de-duplicated
    assert pressure_sweep(300.0) == [45.0, 120.0, 210.0, 300.0]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_intent_requires_a_droplet_target():
    with pytest.raises(ValueError, match="droplet_um"):
        parse_intent({"throughput_mlhr": 5})


def test_fab_preset_resolves_and_explicit_caps_override_it():
    c = parse_constraints({"fab": "relaxed_300um"})
    assert c.max_main_depth_um == FAB_PRESETS["relaxed_300um"]["max_main_depth_um"]

    c2 = parse_constraints({"fab": "current", "max_main_depth_um": 450})
    assert c2.max_main_depth_um == 450.0        # explicit beats the preset
    assert c2.fab == "current"                  # ...and the provenance survives


def test_unknown_fab_preset_is_refused_by_name():
    with pytest.raises(KeyError, match="relaxed_9000"):
        parse_constraints({"fab": "relaxed_9000"})


def test_constraints_block_spells_the_preset_out():
    """A cap that only exists inside a preset is one diagnosis cannot price."""
    block = _constraints().as_block()
    assert block["max_main_depth_um"] == 200.0
    assert block["fab"] == "current"


# ---------------------------------------------------------------------------
# intent -> grid, per family
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["serpentine", "radial", "manifold"])
def test_every_family_generates_a_grid_from_an_intent(name):
    block = get_family(name).grid_from_intent(
        _intent(), _constraints(), fluids=_FLUIDS)
    assert isinstance(block, dict) and block
    # at least one axis must actually sweep, or intent has generated a single
    # point and there is nothing to decide between
    assert any(isinstance(v, list) for v in block.values()) or any(
        isinstance(x, list) for v in block.values()
        if isinstance(v, dict) for x in v.values())


def test_all_families_get_the_same_exit_for_the_same_droplet():
    """What makes the resulting cross-family table a fair comparison."""
    intent, constraints = _intent(), _constraints()
    serp = get_family("serpentine").grid_from_intent(intent, constraints, fluids=_FLUIDS)
    rad = get_family("radial").grid_from_intent(intent, constraints, fluids=_FLUIDS)
    man = get_family("manifold").grid_from_intent(intent, constraints, fluids=_FLUIDS)

    assert serp["junction"]["exit_depth_um"] == rad["exit"]["depth_um"]
    assert serp["junction"]["exit_depth_um"] == man["junction"]["exit_depth_um"]
    assert serp["junction"]["exit_width_um"] == rad["exit"]["width_um"]


def test_generated_geometry_respects_the_fab_caps():
    block = get_family("serpentine").grid_from_intent(
        _intent(), parse_constraints({"fab": "current"}), fluids=_FLUIDS)
    assert block["main"]["depth_um"] <= FAB_PRESETS["current"]["max_main_depth_um"]
    assert block["main"]["width_um"] <= FAB_PRESETS["current"]["max_main_width_um"]


def test_a_deeper_fab_preset_generates_a_deeper_main():
    shallow = get_family("serpentine").grid_from_intent(
        _intent(), parse_constraints({"fab": "current"}), fluids=_FLUIDS)
    deep = get_family("serpentine").grid_from_intent(
        _intent(), parse_constraints({"fab": "relaxed_300um"}), fluids=_FLUIDS)
    assert deep["main"]["depth_um"] > shallow["main"]["depth_um"]


def test_a_family_without_an_intent_path_says_so_rather_than_guessing():
    class Bare(Family):
        name = "bare"

        def applicable_metrics(self):
            return set()

        def compile(self, params, *, fluids, footprint, manufacturing):
            return None

        def solve(self, compiled, operating, *, params, label):
            return CommonMetrics(family="bare", label=label)

    with pytest.raises(IntentNotSupported, match="bare"):
        Bare().grid_from_intent(_intent(), _constraints(), fluids=_FLUIDS)


# ---------------------------------------------------------------------------
# expand_intent
# ---------------------------------------------------------------------------

def test_a_study_without_intent_is_passed_through_untouched():
    raw = {"title": "plain", "family": "serpentine"}
    out, plan = expand_intent(raw)
    assert plan is None and out is raw
    assert not has_intent(raw)


def test_intent_generates_every_block_a_study_needs():
    out, plan = expand_intent(INTENT_RAW)
    for block in ("fluids", "footprint", "manufacturing", "operating",
                  "scoring", "decide", "serpentine", "radial", "manifold"):
        assert out.get(block), f"{block} was not generated"
        assert block in plan.generated
    assert out["family"] == ["serpentine", "radial", "manifold"]
    assert not plan.skipped


def test_explicit_blocks_win_and_are_reported_as_such():
    raw = dict(INTENT_RAW)
    raw["serpentine"] = {"main": {"depth_um": 77}, "rung": {"N": 5}}
    raw["operating"] = {"Po_mbar": 999}

    out, plan = expand_intent(raw)
    assert out["serpentine"]["main"]["depth_um"] == 77     # untouched
    assert out["operating"]["Po_mbar"] == 999              # ceiling not imposed
    assert "serpentine" in plan.user_supplied
    assert "operating" in plan.user_supplied
    assert "serpentine" not in plan.generated
    # the other two families are still generated around the pinned one
    assert "radial" in plan.generated and "manifold" in plan.generated


def test_the_pressure_sweep_is_bounded_by_the_ceiling():
    out, _ = expand_intent(INTENT_RAW)
    assert max(out["operating"]["Po_mbar"]) <= 300.0


def test_generated_study_round_trips_through_yaml():
    """Intent is a front door, not a lock-in: the YAML it emits runs as a study."""
    text = generated_yaml(INTENT_RAW)
    regenerated = load_study_text(text)
    direct = build_study(INTENT_RAW)
    assert [p.label for p in regenerated.points] == [p.label for p in direct.points]


def test_intent_with_no_answerable_family_refuses_rather_than_emptying():
    raw = dict(INTENT_RAW)
    raw["explore"] = ["nosuchfamily"]
    with pytest.raises(ValueError, match="no explored family"):
        expand_intent(raw)


# ---------------------------------------------------------------------------
# Acceptance: intent + constraints + explore -> a scored space
# ---------------------------------------------------------------------------

def test_intent_only_study_yields_a_scored_space_across_three_families():
    study, scored = _run(INTENT_RAW)

    assert study.from_intent
    assert study.families == ["serpentine", "radial", "manifold"]
    assert len(scored) > 20, "intent should generate a space, not a point"
    assert {s.metrics.family for s in scored} == {"serpentine", "radial", "manifold"}
    assert not [s for s in scored if s.metrics.error], "every point must solve"
    # every row is graded on something — a table of grey is not an answer
    assert all(s.overall in {"green", "orange", "red"} for s in scored)


def test_a_hand_written_study_is_unaffected_by_the_intent_layer():
    study, scored = _run(_PLANTED)
    assert not study.from_intent
    assert study.intent_plan is None
    assert len(scored) == 3


def test_the_deep_dfu_intent_is_flagged_as_outside_the_validated_envelope():
    """A 51 µm exit is far past the droplet fit — no row may read green on it."""
    _, scored = _run(INTENT_RAW)
    assert all(s.cells["validity"].category != "green" for s in scored)
    assert all(s.cells["validity"].detail for s in scored)


# ---------------------------------------------------------------------------
# Binding-constraint analysis
# ---------------------------------------------------------------------------

_SCORING = {
    "throughput_mlhr": {"green": 5, "orange": 1, "higher_better": True},
    "uniformity_pct": {"green": 20, "orange": 100},
    "build": {"fits_square": "required", "no_crossing": "required"},
}
_APPLICABLE = {"throughput_mlhr", "uniformity_pct", "build"}


def _row(**kw) -> ScoredRow:
    base = dict(family="serpentine", label="x", throughput_mlhr=10,
                uniformity_pct=5, fits_square=True, manufacturable=True,
                no_crossing=True)
    base.update(kw)
    return score_metrics(CommonMetrics(**base), _SCORING, _APPLICABLE)


def test_row_failures_names_the_build_sub_gate_not_the_composite():
    row = _row(fits_square=False)
    assert row_failures(row) == ["build:fits_square"]


def test_sole_cause_separates_the_constraint_from_the_symptoms():
    rows = [
        _row(fits_square=False),                        # fits_square alone
        _row(fits_square=False),                        # fits_square alone
        _row(fits_square=False, throughput_mlhr=0.1),   # two causes, neither sole
        _row(),                                         # fine
    ]
    by_key = {f.key: f for f in binding_gates(rows)}
    assert by_key["build:fits_square"].n_red == 3
    assert by_key["build:fits_square"].n_sole_cause == 2
    assert by_key["throughput_mlhr"].n_red == 1
    assert by_key["throughput_mlhr"].n_sole_cause == 0
    # ordering puts the sole cause first — that is the thing in the way
    assert binding_gates(rows)[0].key == "build:fits_square"


def test_a_gate_no_process_change_touches_is_named_as_physics():
    assert knobs_for_gate("regime_Ca") == []
    assert knobs_for_gate("build:fits_square")


# ---------------------------------------------------------------------------
# Acceptance: the planted binding constraint, and its price
# ---------------------------------------------------------------------------

def test_diagnosis_finds_the_planted_binding_constraint():
    study, scored = _run(_PLANTED)
    diag = diagnose(study, scored, price="never")

    assert diag.n_red == 3 and diag.n_green == 0
    assert diag.infeasible
    assert diag.binding.key == "build:fits_square"
    assert diag.binding.n_sole_cause == 3
    assert not diag.binding_is_physics       # a die size is a decision, not physics


def test_relaxing_the_planted_constraint_is_priced_in_designs():
    study, scored = _run(_PLANTED)
    knobs = active_knobs(study.raw, binding_gates(scored))
    assert "square_side_mm" in [k.key for k in knobs]

    prices = price_relaxations(
        study, scored, [k for k in knobs if k.key == "square_side_mm"])
    assert len(prices) == 1
    price = prices[0]
    assert price.before == 20.0 and price.after == 30.0
    assert price.red_before == 3 and price.red_after == 0
    assert price.reds_cleared == 3
    assert price.is_worth_it
    assert "20 → 30 mm" in price.describe()


def test_an_infeasible_study_answers_with_the_constraint_and_its_price():
    """The acceptance criterion: not an empty table."""
    study, scored = _run(_PLANTED)
    diag = diagnose(study, scored, price="auto")     # auto prices when 0 green

    assert diag.priced
    assert diag.best_price is not None
    head = diag.headline()
    assert "fits the die square" in head.lower()   # the binding constraint
    assert "die square side" in head               # ...and what it costs to move


def test_pricing_an_inert_constraint_reports_that_it_changes_nothing():
    study, scored = _run(_PLANTED)
    depth = [k for k in KNOBS if k.key == "max_main_depth_um"]
    prices = price_relaxations(study, scored, depth)
    assert prices and not prices[0].is_worth_it
    assert "not what is binding" in prices[0].describe()


# ---------------------------------------------------------------------------
# Green apart from Ca — the build-and-see shortlist
# ---------------------------------------------------------------------------

_CA_SCORING = dict(_SCORING, regime_Ca={"green": 0.0125, "orange": 0.03})
_CA_APPLICABLE = _APPLICABLE | {"regime_Ca"}


def _ca_row(**kw) -> ScoredRow:
    base = dict(family="serpentine", label="x", throughput_mlhr=10,
                uniformity_pct=5, regime_Ca=0.005, fits_square=True,
                manufacturable=True, no_crossing=True)
    base.update(kw)
    return score_metrics(CommonMetrics(**base), _CA_SCORING, _CA_APPLICABLE)


def test_a_row_red_only_on_Ca_is_a_build_and_see_candidate():
    rows = [
        _ca_row(regime_Ca=0.20),                      # red on Ca alone
        _ca_row(regime_Ca=0.20, fits_square=False),   # also unbuildable
        _ca_row(fits_square=False),                   # unbuildable, Ca fine
        _ca_row(),                                    # green
    ]
    assert theory_limited_rows(rows) == [0]


def test_the_gate_is_not_softened_only_named():
    """
    The verdict must stay red. An unmeasured risk quietly downgraded to green
    would be worse than no verdict at all — the point is to name the distinction
    so the call is the user's, not to make it for them.
    """
    row = _ca_row(regime_Ca=0.20)
    assert row.overall == "red"
    assert row.cells["regime_Ca"].category == "red"
    assert theory_limited_rows([row]) == [0]


def test_only_regime_Ca_counts_as_evidence_thin():
    """Widening this set is a claim about evidence — it should be deliberate."""
    assert EVIDENCE_THIN_GATES == frozenset({"regime_Ca"})


def test_ca_confidence_tracks_the_measured_envelope_not_the_se_ceiling():
    """
    Below the SE ceiling but above anything measured is still an extrapolation.

    The ceiling is borrowed from λ ≈ 1 literature; the measured envelope is what
    Peak has actually operated in. They differ by 7x and the tier follows the
    second, not the first.
    """
    from stepgen.families.base import CA_MEASURED_MAX, SE_CEILING_CA

    fam = get_family("serpentine")
    inside = fam.metric_confidence(CommonMetrics(
        family="serpentine", label="a", regime_Ca=CA_MEASURED_MAX * 0.5))
    between = fam.metric_confidence(CommonMetrics(
        family="serpentine", label="b", regime_Ca=SE_CEILING_CA * 0.3))

    assert CA_MEASURED_MAX < SE_CEILING_CA * 0.3 < SE_CEILING_CA
    assert inside["regime_Ca"] == "calibrated"
    assert between["regime_Ca"] == "extrapolation"


def test_the_intent_grid_now_reaches_the_low_Ca_corner():
    """
    Regression on the Ca-blind sizing defect.

    The first Phase 2 grid sized N for throughput at the pressure ceiling and
    found nothing under the Ca bound. With both sizings on the ladder, in-regime
    deep-DFU designs must appear.
    """
    _, scored = _run(INTENT_RAW)
    in_regime = [s for s in scored if s.cells["regime_Ca"].category == "green"]
    assert in_regime, "no design sits under the Ca green bound"
    # and they must be real designs, not degenerate no-flow points
    assert max(s.metrics.throughput_mlhr or 0 for s in in_regime) > 1.0


def test_the_deep_dfu_study_reports_a_build_and_see_shortlist():
    study, scored = _run(INTENT_RAW)
    diag = diagnose(study, scored, price="never")
    assert diag.theory_limited
    assert len(diag.theory_limited_labels) == len(diag.theory_limited)
    assert "build-and-see" in diag.headline()
    assert diag.to_json()["theory_limited"] == diag.theory_limited_labels


# ---------------------------------------------------------------------------
# γ-robustness — Ca is a verdict resting on a constant nobody has measured
# ---------------------------------------------------------------------------

def test_gamma_enters_only_the_ca_diagnostic_never_the_flow_solve():
    """
    The premise the whole γ-robustness layer rests on.

    If γ affected the hydraulics, sweeping it would need a re-solve per value.
    It does not — so Ca ∝ 1/γ exactly and the band is free.
    """
    base = _PLANTED.replace("gamma: 0.005", "gamma: 0.005")
    other = _PLANTED.replace("gamma: 0.005", "gamma: 0.020")
    _, a = _run(base)
    _, b = _run(other)

    for ra, rb in zip(a, b):
        assert ra.metrics.throughput_mlhr == pytest.approx(rb.metrics.throughput_mlhr)
        assert ra.metrics.uniformity_pct == pytest.approx(rb.metrics.uniformity_pct)
        # ...and Ca moved by exactly the inverse ratio
        assert ra.metrics.regime_Ca == pytest.approx(rb.metrics.regime_Ca * 4.0)


def test_ca_robustness_reports_the_band_analytically():
    row = _ca_row(regime_Ca=0.05)          # red at γ_ref = 5 mN/m
    rb = ca_gamma_robustness(row, _CA_SCORING, gamma_ref=0.005,
                             gamma_range=(0.003, 0.020))
    assert rb is not None
    # Ca ∝ 1/γ
    assert rb.ca_at_lo == pytest.approx(0.05 * 0.005 / 0.003)
    assert rb.ca_at_hi == pytest.approx(0.05 * 0.005 / 0.020)   # = 0.0125, green
    assert rb.verdict_lo == "red" and rb.verdict_hi == "green"
    assert not rb.robustly_red and not rb.is_robust
    # clears once γ takes Ca to the red bound (0.03)
    assert rb.gamma_to_clear_red == pytest.approx(0.05 * 0.005 / 0.03)


def test_a_design_far_into_the_red_stays_red_at_every_gamma():
    """The user's distinction: 'major into the red throughout a range of γ'."""
    rb = ca_gamma_robustness(_ca_row(regime_Ca=0.5), _CA_SCORING,
                             gamma_ref=0.005, gamma_range=(0.003, 0.020))
    assert rb.robustly_red
    assert rb.gamma_to_clear_red is None
    assert "genuinely out of regime" in rb.describe()


def test_a_design_only_just_red_depends_on_gamma():
    """'...only just into the red with only select values of γ'."""
    rb = ca_gamma_robustness(_ca_row(regime_Ca=0.035), _CA_SCORING,
                             gamma_ref=0.005, gamma_range=(0.003, 0.020))
    assert not rb.robustly_red
    assert rb.gamma_to_clear_red is not None
    assert "red only for γ below" in rb.describe()


def test_a_comfortably_green_design_is_robust_too():
    rb = ca_gamma_robustness(_ca_row(regime_Ca=0.001), _CA_SCORING,
                             gamma_ref=0.005, gamma_range=(0.003, 0.020))
    assert rb.robustly_ok and rb.is_robust
    assert "does not depend on the γ we assume" in rb.describe()


def test_ca_robustness_declines_when_there_is_no_ca():
    row = _ca_row(regime_Ca=None)
    assert ca_gamma_robustness(row, _CA_SCORING, gamma_ref=0.005) is None
    assert ca_gamma_robustness(_ca_row(), {}, gamma_ref=0.005) is None
    assert ca_gamma_robustness(_ca_row(), _CA_SCORING, gamma_ref=0.0) is None


def test_diagnosis_splits_the_shortlist_by_gamma_robustness():
    study, scored = _run(INTENT_RAW)
    diag = diagnose(study, scored, price="never")

    assert diag.gamma_ref == pytest.approx(0.005)
    assert diag.robustly_red_ca and diag.gamma_dependent_ca
    # the split partitions the theory-limited set
    assert (len(diag.robustly_red_ca) + len(diag.gamma_dependent_ca)
            == len(diag.theory_limited))
    assert set(diag.robustly_red_ca).isdisjoint(diag.gamma_dependent_ca)
    assert "build-and-see shortlist" in diag.headline()


def test_the_shortlist_is_ordered_by_how_little_gamma_it_needs():
    """A design needing 6 mN/m is a better bet than one needing 19."""
    study, scored = _run(INTENT_RAW)
    diag = diagnose(study, scored, price="never")

    needed = []
    for i in diag.gamma_dependent_ca:
        rb = ca_gamma_robustness(scored[i], study.scoring,
                                 gamma_ref=diag.gamma_ref,
                                 gamma_range=diag.gamma_range)
        needed.append(rb.gamma_to_clear_red)
    assert needed == sorted(needed)


def test_gamma_split_reaches_the_chapter_sidecar():
    study, scored = _run(INTENT_RAW)
    blob = diagnose(study, scored, price="never").to_json()
    assert blob["gamma_ref_Nm"] == pytest.approx(0.005)
    assert blob["gamma_range_Nm"] == [0.003, 0.020]
    assert blob["ca_red_only_at_some_gamma"]
    assert blob["ca_red_at_every_gamma"]


def test_the_deep_dfu_intent_is_blocked_by_physics_not_by_a_cap():
    """
    The M1 question, answered honestly.

    A 140 µm droplet drives the exit Ca past the step-emulsification ceiling.
    No etch depth, die size or pressure ceiling relaxes that, and the diagnosis
    must say so rather than offering a process change that would not help.
    """
    study, scored = _run(INTENT_RAW)
    diag = diagnose(study, scored, price="never")

    assert diag.binding.key == "regime_Ca"
    assert diag.binding_is_physics
    assert not knobs_for_gate("regime_Ca")
    assert "No process constraint relaxes" in diag.headline()


def test_auto_pricing_stays_out_of_the_way_when_the_study_is_feasible():
    text = _PLANTED.replace("square_side_mm: 20.0", "square_side_mm: 63.5")
    study, scored = _run(text)
    diag = diagnose(study, scored, price="auto")
    if diag.n_green:
        assert not diag.priced and not diag.prices


def test_diagnosis_serialises_for_the_chapter_sidecar():
    study, scored = _run(_PLANTED)
    diag = diagnose(study, scored, price="never")
    blob = json.loads(json.dumps(diag.to_json(), default=str))
    assert blob["binding"]["gate"] == "build:fits_square"
    assert blob["infeasible"] is True
    assert blob["binding_is_physics"] is False


# ---------------------------------------------------------------------------
# Relaxation pricing regenerates an intent grid, not just the gate
# ---------------------------------------------------------------------------

def test_relaxing_an_intent_constraint_regenerates_the_geometry():
    """
    A deeper permitted etch must change the geometry that gets *tried*.

    Relaxing only the gate that judges a design would price the constraint at
    zero for the wrong reason, so the knob writes to `constraints:` and the grid
    is regenerated from it.
    """
    import copy

    knob = next(k for k in KNOBS if k.key == "max_main_depth_um")
    raw = copy.deepcopy(build_study(INTENT_RAW).intent_raw)
    before_depth = build_study(raw).raw["serpentine"]["main"]["depth_um"]

    assert knob.apply(raw) == (200.0, 300.0)
    after_depth = build_study(raw).raw["serpentine"]["main"]["depth_um"]

    assert before_depth == 200.0 and after_depth == 300.0


def test_a_knob_with_nothing_to_step_is_skipped_rather_than_invented():
    knob = next(k for k in KNOBS if k.key == "max_Po_mbar")
    raw = yaml.safe_load(_PLANTED)          # a hand-written study has no ceiling
    assert knob.current(raw) is None
    assert knob.apply(raw) is None


# ---------------------------------------------------------------------------
# The chapter and the UI see the same thing
# ---------------------------------------------------------------------------

def test_chapter_renders_the_intent_and_diagnosis_panels(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from stepgen.studio.workbook import write_workbook

    study = build_study(INTENT_RAW)
    result = run_study(study)
    scored = score_result(result, study.scoring)
    diag = diagnose(study, scored, price="never")

    path = write_workbook(result, tmp_path / "chapter.html", diagnosis=diag)
    doc = path.read_text(encoding="utf-8")
    assert "<h2>Intent</h2>" in doc
    assert "<h2>Diagnosis</h2>" in doc
    assert "Build-and-see candidates" in doc  # exit Ca has no process knob

    sidecar = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["intent"]["droplet_um"] == 140.0
    assert sidecar["diagnosis"]["binding"]["gate"] == "regime_Ca"


def test_a_hand_written_chapter_carries_no_intent_panel(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from stepgen.studio.workbook import write_workbook

    study = load_study_text(_PLANTED)
    result = run_study(study)
    path = write_workbook(result, tmp_path / "plain.html", price="never")
    doc = path.read_text(encoding="utf-8")
    assert "<h2>Intent</h2>" not in doc
    assert json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))["intent"] is None


def test_the_ui_pipeline_runs_an_intent_study_identically():
    """The UI is a skin: batch and interactive must produce the same numbers."""
    import matplotlib
    matplotlib.use("Agg")
    from stepgen.studio import ui

    text = yaml.safe_dump(INTENT_RAW)
    data = ui._compute(text, None)

    _, scored = _run(INTENT_RAW)
    assert data["study"].from_intent
    assert [s.metrics.label for s in data["scored"]] == [s.metrics.label for s in scored]
    assert [s.overall for s in data["scored"]] == [s.overall for s in scored]
