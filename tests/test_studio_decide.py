"""
Phase 1 — the decide layer.

Covers the roadmap's acceptance criteria for `docs/06_design_studio/roadmap_studio_v1.md`
Phase 1: margin arithmetic at both boundaries, the model-confidence discount, the
validity gate on a known out-of-envelope deep-DFU point, Pareto correctness on a
hand-checked set, and a study whose axes genuinely conflict so that four different
designs win.
"""

from __future__ import annotations

import numpy as np
import pytest

from stepgen.families.base import (
    CALIBRATED,
    EXTRAPOLATION,
    VALIDATED,
    CommonMetrics,
    get_family,
)
from stepgen.studio.ranking import (
    AXES,
    composite_scores,
    decide,
    pareto_indices,
    pareto_mask,
    resolve_axes,
    resolve_weights,
    row_specific_breaches,
    shared_caveats,
)
from stepgen.studio.scoring import score_metrics

# thresholds used throughout: green/orange bounds chosen so the span arithmetic
# is easy to check by hand
_SCORING = {
    "throughput_mlhr":   {"green": 5, "orange": 1, "higher_better": True},
    "uniformity_pct":    {"green": 20, "orange": 100},
    "operating_Po_mbar": {"green": 100, "orange": 500},
    "regime_Ca":         {"green": 0.0125, "orange": 0.03},
    "build":             {"fits_square": "required"},
}
_APPLICABLE = {"throughput_mlhr", "uniformity_pct", "operating_Po_mbar",
               "regime_Ca", "build"}
_WITH_VALIDITY = _APPLICABLE | {"validity"}


def _cm(**kw) -> CommonMetrics:
    base = dict(family="serpentine", label="x")
    base.update(kw)
    return CommonMetrics(**base)


def _healthy(**kw) -> CommonMetrics:
    """A point that is green everywhere and inside the envelope."""
    base = dict(throughput_mlhr=10, uniformity_pct=5, operating_Po_mbar=50,
                regime_Ca=0.005, fits_square=True, manufacturable=True,
                exit_width_um=30.0, exit_depth_um=10.0, lambda_visc=1.0)
    base.update(kw)
    return _cm(**base)


# ---------------------------------------------------------------------------
# Margin arithmetic
# ---------------------------------------------------------------------------

def test_margin_is_one_at_the_green_bound():
    # lower-is-better: uniformity green<=20, orange<=100. At 20 the value is
    # exactly one full green->red span away from red.
    sr = score_metrics(_healthy(uniformity_pct=20), _SCORING, _APPLICABLE)
    assert sr.cells["uniformity_pct"].margin == pytest.approx(1.0)


def test_margin_is_zero_at_the_red_bound():
    sr = score_metrics(_healthy(uniformity_pct=100), _SCORING, _APPLICABLE)
    assert sr.cells["uniformity_pct"].margin == pytest.approx(0.0)


def test_margin_midway_is_half():
    # halfway between green (20) and red (100) bounds
    sr = score_metrics(_healthy(uniformity_pct=60), _SCORING, _APPLICABLE)
    assert sr.cells["uniformity_pct"].margin == pytest.approx(0.5)


def test_margin_floors_at_zero_once_red():
    blown = score_metrics(_healthy(uniformity_pct=1000), _SCORING, _APPLICABLE)
    assert blown.cells["uniformity_pct"].margin == pytest.approx(0.0)


def test_margin_is_uncapped_above_the_green_bound():
    # capping here would make every green row read 1.0 and erase the very
    # distinction the margin column exists to draw
    comfortable = score_metrics(_healthy(uniformity_pct=4), _SCORING, _APPLICABLE)
    assert comfortable.cells["uniformity_pct"].margin == pytest.approx(1.2)


def test_margin_handles_higher_better_direction():
    # throughput green>=5, orange>=1 -> span 4. At 3 the margin is (3-1)/4.
    sr = score_metrics(_healthy(throughput_mlhr=3), _SCORING, _APPLICABLE)
    assert sr.cells["throughput_mlhr"].margin == pytest.approx(0.5)


def test_min_margin_is_the_weakest_link():
    # uniformity at 60 -> 0.5; everything else comfortably 1.0
    sr = score_metrics(_healthy(uniformity_pct=60), _SCORING, _APPLICABLE)
    assert sr.min_margin == pytest.approx(0.5)
    assert sr.weakest_metric == "uniformity_pct"


def test_green_but_marginal_is_distinguishable_from_green_and_comfortable():
    """
    The roadmap's headline acceptance for the margin column.

    Both rows are green on every gate, so the traffic light cannot tell them
    apart. If the model is slightly optimistic, only the comfortable one still
    works — so the margin has to separate them.
    """
    marginal = score_metrics(_healthy(uniformity_pct=19.5), _SCORING, _APPLICABLE)
    comfortable = score_metrics(_healthy(uniformity_pct=2), _SCORING, _APPLICABLE)
    assert marginal.overall == comfortable.overall == "green"
    assert marginal.min_margin < comfortable.min_margin

    # the flatness cells themselves: (100-19.5)/80 vs (100-2)/80
    assert marginal.cells["uniformity_pct"].margin == pytest.approx(1.00625)
    assert comfortable.cells["uniformity_pct"].margin == pytest.approx(1.225)
    # for the comfortable row flatness is no longer the binding metric —
    # drive pressure is, at (500-50)/400
    assert comfortable.weakest_metric == "operating_Po_mbar"
    assert comfortable.min_margin == pytest.approx(1.125)


def test_grey_cells_carry_no_margin():
    sr = score_metrics(_healthy(regime_Ca=None), _SCORING, _APPLICABLE)
    assert sr.cells["regime_Ca"].margin is None
    assert "regime_Ca" not in {c.key for c in sr.graded_cells}


# ---------------------------------------------------------------------------
# Model confidence and the discount
# ---------------------------------------------------------------------------

def test_confidence_discount_lowers_margin_for_extrapolated_metrics():
    cm = _healthy(uniformity_pct=60)
    trusted = score_metrics(cm, _SCORING, _APPLICABLE,
                            {"uniformity_pct": VALIDATED})
    guessed = score_metrics(cm, _SCORING, _APPLICABLE,
                            {"uniformity_pct": EXTRAPOLATION})
    assert trusted.min_margin == guessed.min_margin == pytest.approx(0.5)
    # same raw margin, but the extrapolated one must not read as reassurance
    assert guessed.min_margin_discounted < trusted.min_margin_discounted
    assert guessed.min_margin_discounted == pytest.approx(0.5 * 0.4)


def test_discount_can_change_which_metric_is_the_weakest_link():
    # uniformity margin 0.5 (validated) vs throughput margin 0.75 (extrapolated
    # -> 0.30). The extrapolated metric becomes the binding one.
    cm = _healthy(uniformity_pct=60, throughput_mlhr=4)
    sr = score_metrics(cm, _SCORING, _APPLICABLE,
                       {"uniformity_pct": VALIDATED,
                        "throughput_mlhr": EXTRAPOLATION})
    assert sr.min_margin == pytest.approx(0.5)
    assert sr.weakest_metric == "throughput_mlhr"


def test_family_marks_deep_exit_throughput_as_extrapolation():
    fam = get_family("serpentine")
    shallow = fam.metric_confidence(_healthy(exit_depth_um=10.0))
    deep = fam.metric_confidence(_healthy(exit_depth_um=50.0))
    assert shallow["throughput_mlhr"] == VALIDATED
    assert deep["throughput_mlhr"] == EXTRAPOLATION
    # Stage-1 hydraulics stay validated either way
    assert deep["operating_Po_mbar"] == VALIDATED


def test_family_marks_out_of_se_ca_as_extrapolation():
    fam = get_family("serpentine")
    inside = fam.metric_confidence(_healthy(regime_Ca=0.005))
    outside = fam.metric_confidence(_healthy(regime_Ca=0.085))
    assert inside["regime_Ca"] == CALIBRATED
    assert outside["regime_Ca"] == EXTRAPOLATION


def test_extrapolated_keys_reported_in_plain_language():
    cm = _healthy(regime_Ca=0.02, exit_depth_um=50.0)
    fam = get_family("serpentine")
    sr = score_metrics(cm, _SCORING, _WITH_VALIDITY, fam.metric_confidence(cm))
    assert "throughput_mlhr" in sr.extrapolated_keys
    assert any("not validated here" in c for c in sr.chips)


# ---------------------------------------------------------------------------
# Validity gate
# ---------------------------------------------------------------------------

def test_validity_green_inside_the_envelope():
    sr = score_metrics(_healthy(), _SCORING, _WITH_VALIDITY)
    assert sr.cells["validity"].category == "green"
    assert sr.overall == "green"


def test_validity_gate_fires_on_a_deep_dfu_point():
    """
    The concrete case Phase 0 and Phase 1 exist for: a 50 µm-deep DFU driven
    hard. Green on every threshold it is graded against, yet outside the
    envelope on Ca, exit depth and aspect ratio at once.
    """
    # 100 x 50 µm exit -> aspect ratio 2.0, below the 2.5-3.0 fitted range
    deep = _healthy(regime_Ca=0.085, exit_width_um=100.0, exit_depth_um=50.0,
                    lambda_visc=1.0)

    # the Ca *threshold* alone already reds this row, so drop regime_Ca from the
    # graded set to show the envelope gate acting on its own
    scoring_no_ca = {k: v for k, v in _SCORING.items() if k != "regime_Ca"}
    gated = score_metrics(deep, scoring_no_ca, _WITH_VALIDITY)
    ungated = score_metrics(deep, scoring_no_ca, _APPLICABLE)

    assert ungated.overall == "green"          # nothing else complains
    assert gated.overall == "orange"           # the envelope does
    assert gated.cells["validity"].category == "orange"

    detail = gated.cells["validity"].detail
    assert len(detail) == 3
    joined = " | ".join(detail)
    assert "step-emulsification ceiling" in joined
    assert "droplet-fit range" in joined
    assert "aspect ratio" in joined

    # and the gate is grey, not green, for a family that never declares it
    assert score_metrics(deep, _SCORING, _APPLICABLE).cells["validity"].category == "grey"


def test_validity_is_never_green_but_never_red_on_envelope_grounds():
    breached = _healthy(exit_depth_um=50.0)
    sr = score_metrics(breached, _SCORING, _WITH_VALIDITY)
    assert sr.cells["validity"].category == "orange"
    assert sr.overall == "orange"      # capped, not failed


def test_validity_flags_viscosity_ratio_outside_envelope():
    sr = score_metrics(_healthy(lambda_visc=0.0148), _SCORING, _WITH_VALIDITY)
    detail = " ".join(sr.cells["validity"].detail)
    assert "λ" in detail and "0.0148" in detail


def test_validity_respects_a_study_supplied_envelope():
    cm = _healthy(exit_depth_um=50.0)
    strict = score_metrics(cm, _SCORING, _WITH_VALIDITY)
    relaxed = score_metrics(
        cm, dict(_SCORING, validity={"exit_depth_um_max": 80.0,
                                     "aspect_ratio_range": [0.1, 10.0]}),
        _WITH_VALIDITY)
    assert strict.cells["validity"].category == "orange"
    assert relaxed.cells["validity"].category == "green"


def test_validity_is_grey_when_family_does_not_declare_it():
    sr = score_metrics(_healthy(exit_depth_um=50.0), _SCORING, _APPLICABLE)
    assert sr.cells["validity"].category == "grey"


# ---------------------------------------------------------------------------
# Pareto
# ---------------------------------------------------------------------------

def test_pareto_mask_on_a_hand_checked_set():
    # maximise both columns. (2,2) dominates (1,1); (3,0) and (0,3) are corners.
    pts = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 0.0], [0.0, 3.0]])
    assert list(pareto_mask(pts)) == [False, True, True, True]


def test_pareto_mask_keeps_duplicates_of_a_non_dominated_point():
    pts = np.array([[2.0, 2.0], [2.0, 2.0], [1.0, 1.0]])
    assert list(pareto_mask(pts)) == [True, True, False]


def test_pareto_mask_single_point_is_non_dominated():
    assert list(pareto_mask(np.array([[1.0, 5.0]]))) == [True]


def test_pareto_mask_generalises_beyond_two_axes():
    pts = np.array([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0], [2.0, 0.0, 3.0]])
    assert list(pareto_mask(pts)) == [False, True, True]


def test_legacy_two_axis_pareto_delegates_to_the_same_rule():
    from stepgen.viz.plots import _pareto_front

    xs = np.array([1.0, 2.0, 3.0, 0.0])
    ys = np.array([1.0, 2.0, 0.0, 3.0])
    assert list(_pareto_front(xs, ys)) == [False, True, True, True]


def test_pareto_indices_excludes_rows_missing_an_axis():
    rows = [
        score_metrics(_healthy(label_hint := 0 or None or 0.0) if False else
                      _healthy(uniformity_pct=5, throughput_mlhr=10),
                      _SCORING, _APPLICABLE),
        # uniformity N-A -> cannot be called non-dominated across both axes
        score_metrics(_healthy(uniformity_pct=None, throughput_mlhr=100),
                      _SCORING, _APPLICABLE),
    ]
    axes = [AXES["flatness"], AXES["throughput"]]
    assert pareto_indices(rows, axes) == [0]


# ---------------------------------------------------------------------------
# Axes, weights and the composite
# ---------------------------------------------------------------------------

def test_goal_still_works_as_a_one_axis_shorthand():
    axes = resolve_axes(None, "flatness")
    assert [a.key for a in axes] == ["flatness"]


def test_decide_block_supersedes_goal():
    axes = resolve_axes({"axes": ["throughput", "area"]}, "flatness")
    assert [a.key for a in axes] == ["throughput", "area"]


def test_unknown_axis_raises_with_the_known_set_listed():
    with pytest.raises(KeyError, match="unknown value axis"):
        resolve_axes({"axes": ["wishful_thinking"]}, "")


def test_weights_normalise_to_one():
    axes = resolve_axes({"axes": ["flatness", "throughput"]}, "")
    w = resolve_weights({"weights": {"flatness": 3, "throughput": 1}}, axes)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["flatness"] == pytest.approx(0.75)


def test_unweighted_axes_default_to_an_equal_split():
    axes = resolve_axes({"axes": ["flatness", "throughput"]}, "")
    w = resolve_weights({}, axes)
    assert w["flatness"] == pytest.approx(0.5)
    assert w["throughput"] == pytest.approx(0.5)


def test_composite_is_normalised_within_the_candidate_set():
    rows = [
        score_metrics(_healthy(throughput_mlhr=10), _SCORING, _APPLICABLE),
        score_metrics(_healthy(throughput_mlhr=6), _SCORING, _APPLICABLE),
    ]
    scores = composite_scores(rows, [AXES["throughput"]], {"throughput": 1.0})
    assert scores[0] == pytest.approx(1.0)
    assert scores[1] == pytest.approx(0.0)


def test_composite_renormalises_weights_over_the_axes_a_row_actually_has():
    # row 1 has no uniformity; its composite must come from throughput alone
    # rather than being penalised with a substituted zero (DR-4).
    rows = [
        score_metrics(_healthy(uniformity_pct=5, throughput_mlhr=10),
                      _SCORING, _APPLICABLE),
        score_metrics(_healthy(uniformity_pct=None, throughput_mlhr=10),
                      _SCORING, _APPLICABLE),
    ]
    axes = [AXES["flatness"], AXES["throughput"]]
    scores = composite_scores(rows, axes, {"flatness": 0.5, "throughput": 0.5})
    assert scores[1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# The decision as a whole
# ---------------------------------------------------------------------------

def _conflicting_rows() -> list:
    """
    Four designs, each best on exactly one axis — a genuine trade-off.

      A  flattest, but slow and needs high pressure
      B  highest throughput, but least flat
      C  lowest drive pressure
      D  biggest margin from failure (comfortably mid on everything)
    """
    specs = [
        # label,        uniformity, throughput, Po,  Ca
        ("A_flat",      2.0,        1.2,        480, 0.0290),
        ("B_fast",      95.0,       50.0,       480, 0.0290),
        ("C_lowP",      95.0,       1.2,         10, 0.0290),
        ("D_safe",      30.0,       6.0,        150, 0.0100),
    ]
    rows = []
    for label, uni, thr, po, ca in specs:
        cm = _healthy(uniformity_pct=uni, throughput_mlhr=thr,
                      operating_Po_mbar=po, regime_Ca=ca)
        cm.label = label
        rows.append(score_metrics(cm, _SCORING, _APPLICABLE))
    return rows


def test_four_axes_can_name_four_different_winners():
    """Roadmap acceptance: axes that genuinely conflict produce distinct winners."""
    rows = _conflicting_rows()
    dec = decide(rows, {"axes": ["flatness", "throughput",
                                 "drive_pressure", "margin"]})
    winners = dec.winner_labels(rows)
    assert winners["flatness"] == "A_flat"
    assert winners["throughput"] == "B_fast"
    assert winners["drive_pressure"] == "C_lowP"
    assert winners["margin"] == "D_safe"
    assert len(set(winners.values())) == 4
    assert dec.is_conflicted()


def test_weights_change_the_all_round_pick():
    rows = _conflicting_rows()
    spec = {"axes": ["flatness", "throughput"]}
    flat_first = decide(rows, spec, weights_override={"flatness": 0.9,
                                                      "throughput": 0.1})
    fast_first = decide(rows, spec, weights_override={"flatness": 0.1,
                                                      "throughput": 0.9})
    assert rows[flat_first.all_round].metrics.label == "A_flat"
    assert rows[fast_first.all_round].metrics.label == "B_fast"


def test_weights_are_recorded_on_the_decision():
    rows = _conflicting_rows()
    dec = decide(rows, {"axes": ["flatness", "throughput"],
                        "weights": {"flatness": 0.75, "throughput": 0.25}})
    assert dec.weights == pytest.approx({"flatness": 0.75, "throughput": 0.25})


def test_safest_maximises_the_discounted_margin():
    rows = _conflicting_rows()
    dec = decide(rows, {"axes": ["flatness", "throughput"]})
    assert rows[dec.safest].metrics.label == "D_safe"


def test_red_rows_are_excluded_from_selection():
    rows = _conflicting_rows()
    # make the fastest design unbuildable
    broken = _healthy(throughput_mlhr=500, fits_square=False)
    broken.label = "E_broken"
    rows.append(score_metrics(broken, _SCORING, _APPLICABLE))

    dec = decide(rows, {"axes": ["throughput"]})
    assert rows[-1].overall == "red"
    assert len(rows) - 1 not in dec.candidates
    assert dec.per_axis["throughput"] != len(rows) - 1
    assert not dec.all_red


def test_all_red_study_still_ranks_and_says_so():
    broken = _healthy(fits_square=False)
    broken.label = "only_option"
    rows = [score_metrics(broken, _SCORING, _APPLICABLE)]
    dec = decide(rows, {"axes": ["throughput"]})
    assert dec.all_red
    assert dec.per_axis["throughput"] == 0


def test_decide_on_an_empty_table_is_harmless():
    dec = decide([], {"axes": ["throughput"]})
    assert dec.all_round is None and dec.safest is None and dec.pareto == []
    assert not dec.all_red


# ---------------------------------------------------------------------------
# Study-wide caveats vs row-specific breaches
# ---------------------------------------------------------------------------

def _lambda_rows() -> list:
    """Two rows sharing a λ breach; only the second is also a deep exit."""
    shallow = _healthy(lambda_visc=0.0148)
    shallow.label = "shallow"
    deep = _healthy(lambda_visc=0.0148, exit_width_um=150.0, exit_depth_um=50.0)
    deep.label = "deep"
    return [score_metrics(shallow, _SCORING, _WITH_VALIDITY),
            score_metrics(deep, _SCORING, _WITH_VALIDITY)]


def test_shared_breaches_are_reported_once_as_a_study_caveat():
    rows = _lambda_rows()
    caveats = shared_caveats(rows)
    assert len(caveats) == 1
    assert "λ" in caveats[0]


def test_row_specific_breaches_exclude_the_study_wide_ones():
    rows = _lambda_rows()
    caveats = shared_caveats(rows)
    assert row_specific_breaches(rows[0], caveats) == []
    specific = row_specific_breaches(rows[1], caveats)
    assert specific and all("λ" not in s for s in specific)
    assert any("exit depth" in s for s in specific)


def test_no_shared_caveats_when_a_row_was_never_envelope_checked():
    rows = _lambda_rows()
    rows.append(score_metrics(_healthy(), _SCORING, _APPLICABLE))  # validity grey
    assert shared_caveats(rows) == []
