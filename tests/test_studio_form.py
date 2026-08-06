"""
tests.test_studio_form
======================
The three-region study builder (plan C2).

The substance of C2 is the **set-versus-axis rule**: designs and fluids are
sets that concatenate, axes are a grid that crosses.  Getting that wrong is not
a cosmetic bug — a 4-exit x fluid-swap study written as crossed axes produced 64
points of which 32 were fluid systems that do not exist.  So the tests that
matter are: does the form's point count match what the engine actually expands
to, and does the generated YAML parse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stepgen.studio.form import (
    PHASE_SYSTEMS,
    FormAxes,
    FormDesign,
    FormFluid,
    StudyForm,
    build_yaml,
    form_from_defaults,
    form_from_payload,
    po_levels,
    validate,
)
from stepgen.studio.study import load_study_text

REPO = Path(__file__).resolve().parent.parent


def _flagship() -> StudyForm:
    """The plan's worked example: 4 designs x 2 fluids x 6 pressures = 48."""
    form = form_from_defaults()
    form.title = "flagship"
    form.designs = [
        FormDesign(30, 10, 60, 8, label="30x10"),
        FormDesign(60, 20, 120, 40, label="60x20"),
        FormDesign(30, 20, 60, 20, label="30x20"),
        FormDesign(15, 10, 30, 8, label="15x10"),
    ]
    form.fluids = [
        FormFluid(0.06, 0.00089, "o/w", 0.005),
        FormFluid(0.00089, 0.06, "w/o", 0.005),
    ]
    form.axes = FormAxes(Po_mbar=po_levels(200, 1200, 6),
                         main_length_mm=[40.0], Qw_mlhr=5.0)
    return form


# ---------------------------------------------------------------------------
# Set vs axis — the whole point of the three regions
# ---------------------------------------------------------------------------

def test_the_worked_example_is_48_points_and_the_engine_agrees():
    form = _flagship()
    assert form.n_points == 4 * 2 * 6 == 48
    study = load_study_text(build_yaml(form))
    assert len(study.points) == 48, "form count and engine expansion disagree"


def test_designs_concatenate_they_do_not_cross():
    """Four designs cost four points. If they crossed, this would be 4x."""
    one = _flagship()
    one.designs = one.designs[:1]
    four = _flagship()

    assert len(load_study_text(build_yaml(four)).points) == \
        4 * len(load_study_text(build_yaml(one)).points)


def test_fluids_concatenate_they_do_not_cross():
    one, two = _flagship(), _flagship()
    one.fluids = one.fluids[:1]
    assert len(load_study_text(build_yaml(two)).points) == \
        2 * len(load_study_text(build_yaml(one)).points)


def test_axes_cross_with_everything():
    """Adding a length level multiplies; adding a design only adds."""
    base = _flagship()
    n_base = len(load_study_text(build_yaml(base)).points)

    longer = _flagship()
    longer.axes.main_length_mm = [40.0, 80.0, 160.0]
    assert len(load_study_text(build_yaml(longer)).points) == 3 * n_base
    assert longer.n_points == 3 * n_base

    wider = _flagship()
    wider.designs.append(FormDesign(90, 30, 180, 60, label="90x30"))
    assert len(load_study_text(build_yaml(wider)).points) == n_base + n_base // 4


def test_every_fluid_block_stays_a_paired_whole():
    """
    The failure this region exists to prevent: independent viscosity lists cross,
    and half the resulting points are fluids where both phases are one liquid.
    """
    study = load_study_text(build_yaml(_flagship()))
    systems = {(p.fluids["mu_dispersed"], p.fluids["mu_continuous"])
               for p in study.points}
    assert systems == {(0.06, 0.00089), (0.00089, 0.06)}
    for mu_d, mu_c in systems:
        assert mu_d != mu_c


# ---------------------------------------------------------------------------
# The generated YAML
# ---------------------------------------------------------------------------

def test_generated_yaml_uses_no_anchors():
    """
    `<<:` merge is SHALLOW — `rung: { upstream_width_um: 40 }` under a merged
    design replaces the whole rung block and silently drops the rest.  Generated
    output simply does not go there.
    """
    text = build_yaml(_flagship())
    # comments *explain* the trap, so only the YAML itself is checked
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    assert "<<:" not in code
    assert "&" not in code and "*" not in code
    # and every design still carries a complete rung block
    study = load_study_text(text)
    for point in study.points:
        assert set(point.params["rung"]) >= {"length_mm", "upstream_width_um"}


def test_generated_yaml_carries_the_house_scoring_and_grouping():
    study = load_study_text(build_yaml(_flagship()))
    assert study.scoring, "scoring block did not survive generation"
    assert study.scoring["throughput_mlhr"]["higher_better"] is True
    # group_by is what keeps 4 designs x 4 lengths from reading as 16 designs
    assert "junction.exit_width_um" in study.decide["group_by"]


def test_booleans_are_yaml_not_python():
    """`True` parses under YAML 1.1 and is a trap waiting for a stricter loader."""
    text = build_yaml(_flagship())
    assert "higher_better: true" in text
    assert "higher_better: True" not in text


def test_gamma_is_optional_and_omitted_when_unset():
    form = _flagship()
    for f in form.fluids:
        f.gamma = None
    text = build_yaml(form)
    assert "gamma" not in text.split("operating:")[0].split("fluids:")[1]
    study = load_study_text(text)
    assert all("gamma" not in p.fluids for p in study.points)


def test_po_levels_is_the_coarse_fine_dial():
    assert po_levels(200, 1200, 6) == [200, 400, 600, 800, 1000, 1200]
    assert po_levels(200, 1200, 2) == [200, 1200]
    assert po_levels(200, 1200, 1) == [200]
    # whole mbar: the gate can only quote a pressure that was actually simulated,
    # so a level of 233.333 reads as precision nobody set
    assert all(float(p).is_integer() for p in po_levels(100, 1000, 7))


# ---------------------------------------------------------------------------
# The o/w <-> w/o label
# ---------------------------------------------------------------------------

def test_the_toggle_renames_it_does_not_swap_the_viscosities():
    """
    phase_system branches no physics, so flipping the label must leave every
    solved number identical -- and change only how rows GROUP.
    """
    ow = FormFluid(0.06, 0.00089, "o/w")
    wo = FormFluid(0.06, 0.00089, "w/o")     # same fluid, relabelled
    assert ow.as_block()["mu_dispersed"] == wo.as_block()["mu_dispersed"]
    assert ow.as_block()["mu_continuous"] == wo.as_block()["mu_continuous"]
    assert ow.label_matches_viscosities
    assert not wo.label_matches_viscosities


def test_a_mismatched_label_warns_and_never_blocks():
    """
    JUDGEMENT (2026-08-06): warn, do not block.  The label sets no physics, so a
    mismatch cannot produce a wrong number -- only an odd grouping.  And the
    check is a heuristic that holds only because one phase here is always oil and
    one always water; two oils of similar viscosity would trip it while correctly
    labelled.  Refusing a study on a heuristic the code itself says is not
    general would be the tool overruling a choice the user made.
    """
    form = _flagship()
    form.fluids = [FormFluid(0.06, 0.00089, "w/o")]      # oil dispersed, called w/o
    issues = validate(form)
    mismatch = [i for i in issues if "labelled w/o" in i.message]
    assert len(mismatch) == 1
    assert mismatch[0].level == "warning"
    assert not mismatch[0].blocking
    assert not any(i.blocking for i in issues)
    # and it still generates something runnable
    assert len(load_study_text(build_yaml(form)).points) == 4 * 1 * 6


def test_one_liquid_in_both_phases_warns():
    form = _flagship()
    form.fluids = [FormFluid(0.06, 0.06, "o/w")]
    issues = validate(form)
    assert any("one fluid, not an emulsion" in i.message for i in issues)
    assert not any(i.blocking for i in issues)


def test_a_duplicated_fluid_warns_that_it_buys_nothing():
    form = _flagship()
    form.fluids = [FormFluid(0.06, 0.00089, "o/w"),
                   FormFluid(0.06, 0.00089, "o/w")]
    assert any("identical to fluid 1" in i.message for i in validate(form))


# ---------------------------------------------------------------------------
# What blocks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mutate, where", [
    (lambda f: setattr(f, "designs", []), "designs"),
    (lambda f: setattr(f, "fluids", []), "fluids"),
    (lambda f: setattr(f.axes, "Po_mbar", []), "axes"),
])
def test_an_empty_region_blocks(mutate, where):
    form = _flagship()
    mutate(form)
    blocking = [i for i in validate(form) if i.blocking]
    assert blocking and blocking[0].where == where


def test_giving_both_qw_and_emulsion_target_blocks():
    """Not a judgement call -- the solve itself raises when both are set."""
    form = _flagship()
    form.axes.target_emulsion_pct = 10.0     # Qw is already 5.0
    blocking = [i for i in validate(form) if i.blocking]
    assert any("never both" in i.message for i in blocking)


def test_giving_neither_qw_nor_emulsion_target_blocks():
    form = _flagship()
    form.axes.Qw_mlhr = None
    assert any(i.blocking for i in validate(form))


def test_errors_sort_before_warnings():
    form = _flagship()
    form.designs = []
    form.fluids = [FormFluid(0.06, 0.00089, "w/o")]   # also a warning
    issues = validate(form)
    levels = [i.level for i in issues]
    assert levels == sorted(levels, key=lambda x: 0 if x == "error" else 1)


# ---------------------------------------------------------------------------
# Seeding and the wire format
# ---------------------------------------------------------------------------

def test_the_form_starts_from_the_house_defaults_file():
    """
    C3 made `configs/studio_defaults.yaml` the single reviewable place these
    numbers live.  A second copy in the form would be exactly the drift that
    file exists to prevent.
    """
    from stepgen.studio.defaults import load_defaults

    house = load_defaults().sweep_defaults
    form = form_from_defaults()

    assert form.fluids[0].mu_dispersed == house["fluids"]["mu_dispersed"]
    assert form.fluids[0].mu_continuous == house["fluids"]["mu_continuous"]
    assert form.fluids[0].phase_system == house["fluids"]["phase_system"]
    assert form.axes.Po_mbar == [float(p) for p in house["operating"]["Po_mbar"]]
    assert form.scoring == house["scoring"]
    assert form.footprint == house["footprint"]


def test_payload_round_trip_from_the_browser_shape():
    payload = {
        "title": "posted",
        "designs": [{"label": "a", "exit_width_um": 30, "exit_depth_um": 10,
                     "pitch_um": 60, "upstream_width_um": 8, "rung_length_mm": 4}],
        "fluids": [{"mu_dispersed": 0.06, "mu_continuous": 0.00089,
                    "phase_system": "o/w", "gamma": ""}],
        "axes": {"Po_mbar": [200, 600], "main_length_mm": [40],
                 "Qw_mlhr": 5, "target_emulsion_pct": ""},
    }
    form = form_from_payload(payload)
    assert form.title == "posted"
    assert form.fluids[0].gamma is None          # "" means unset, not 0.0
    assert form.axes.target_emulsion_pct is None
    assert form.n_points == 2
    assert len(load_study_text(build_yaml(form)).points) == 2


def test_phase_systems_is_the_only_list_of_labels():
    assert PHASE_SYSTEMS == ("o/w", "w/o")
