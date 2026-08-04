"""
Design grouping, per-design decisions, improvement levers and number formatting.

The behaviour under test is what makes a multi-design study readable: that a
study of four exits swept over pressure and length arrives as **four designs**
rather than 352 anonymous rows, that each one is ranked against its own
operating points, and that the levers reported for it come from row pairs where
nothing else moved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stepgen.studio.grouping import (
    Axis, build_grouping, fluid_tag, point_leaves, row_axis_values, varying_axes,
)
from stepgen.studio.study import build_study, load_study

REPO = Path(__file__).resolve().parents[1]
MY_DESIGNS = REPO / "configs" / "study_my_designs.yaml"


# ---------------------------------------------------------------------------
# A small study: 2 exits x 2 lengths x 3 pressures x 2 fluids
# ---------------------------------------------------------------------------

def _raw(**decide):
    return {
        "title": "grouping test",
        "family": "serpentine",
        "decide": decide or {},
        "serpentine": [
            {"main": {"depth_um": 200, "width_um": 1000, "length_mm": [20, 40]},
             "rung": {"length_mm": 2, "upstream_width_um": 40},
             "junction": {"exit_width_um": 60, "exit_depth_um": 20, "pitch_um": 120}},
            {"main": {"depth_um": 200, "width_um": 1000, "length_mm": [20, 40]},
             "rung": {"length_mm": 2, "upstream_width_um": 80},
             "junction": {"exit_width_um": 120, "exit_depth_um": 40, "pitch_um": 240}},
        ],
        "fluids": [
            {"mu_dispersed": 0.06, "mu_continuous": 0.00089, "gamma": 0.005,
             "phase_system": "o/w"},
            {"mu_dispersed": 0.00089, "mu_continuous": 0.06, "gamma": 0.005,
             "phase_system": "w/o"},
        ],
        "footprint": {"square_side_mm": 100.0},
        "manufacturing": {"max_main_depth_um": 200.0},
        "operating": {"Po_mbar": [50, 100, 200], "Qw_mlhr": 5.0},
        "scoring": {"uniformity_pct": {"green": 15, "orange": 30},
                    "throughput_mlhr": {"green": 5, "orange": 1, "higher_better": True}},
    }


@pytest.fixture(scope="module")
def study():
    return build_study(_raw())


def test_axes_that_vary_are_found_and_named(study):
    axes = {a.path: a for a in varying_axes(study.points)}
    assert "junction.exit_width_um" in axes
    assert "main.length_mm" in axes
    assert "operating.Po_mbar" in axes
    # constants are not axes
    assert "main.depth_um" not in axes
    assert axes["operating.Po_mbar"].values == (50, 100, 200)
    assert axes["junction.exit_width_um"].label == "Exit width"
    assert axes["junction.exit_width_um"].unit == "µm"


def test_fluid_fields_collapse_to_one_axis(study):
    """Four fields that move together are one choice, not four columns."""
    axes = {a.path for a in varying_axes(study.points)}
    assert "fluids" in axes
    assert not any(p.startswith("fluids.") for p in axes)
    assert fluid_tag({"phase_system": "o/w", "mu_dispersed": 0.06,
                      "mu_continuous": 0.00089, "gamma": 0.005}) \
        == "o/w · µ 60/0.89 · γ 5"


def test_default_grouping_treats_geometry_as_the_design(study):
    g = build_grouping(study)
    # exit + rung width + main length all vary geometrically -> 2 exits x 2 lengths
    assert len(g.groups) == 4
    assert {a.path for a in g.condition_axes} == {"operating.Po_mbar", "fluids"}
    assert sum(len(grp.indices) for grp in g.groups) == len(study.points)


def test_group_by_declares_what_a_design_is():
    """The four-exit study must come back as four designs, not sixteen."""
    study = build_study(_raw(group_by=["junction.exit_width_um",
                                       "junction.exit_depth_um"]))
    g = build_grouping(study)
    assert len(g.groups) == 2
    assert [grp.gid for grp in g.groups] == ["D1", "D2"]
    # main length is now something to optimise over, not a separate device
    assert "main.length_mm" in {a.path for a in g.condition_axes}
    assert "Exit width 60 µm" in g.groups[0].label(g.design_axes)


def test_within_moves_an_axis_out_of_the_design_identity():
    study = build_study(_raw(within=["main.length_mm"]))
    g = build_grouping(study)
    assert len(g.groups) == 2
    assert "main.length_mm" in {a.path for a in g.condition_axes}


def test_unknown_group_by_path_is_reported_not_silently_dropped():
    study = build_study(_raw(group_by=["junction.exit_width_um", "nonsense.path"]))
    g = build_grouping(study)
    assert len(g.groups) == 2
    assert "nonsense.path" in g.source


def test_every_row_belongs_to_exactly_one_group(study):
    g = build_grouping(study)
    seen = [i for grp in g.groups for i in grp.indices]
    assert sorted(seen) == list(range(len(study.points)))
    assert len(g.group_of) == len(study.points)


def test_point_leaves_and_row_axis_values_agree(study):
    g = build_grouping(study)
    axes = list(g.design_axes) + list(g.condition_axes)
    point = study.points[0]
    values = row_axis_values(point, axes)
    leaves = point_leaves(point)
    assert values == {a.path: leaves.get(a.path) for a in axes}


# ---------------------------------------------------------------------------
# Per-design decisions
# ---------------------------------------------------------------------------

def test_decide_subset_reindexes_to_the_whole_table():
    from stepgen.studio.ranking import decide, decide_subset
    from stepgen.studio.run import run_study
    from stepgen.studio.scoring import score_result

    study = build_study(_raw(group_by=["junction.exit_width_um"]))
    result = run_study(study)
    scored = score_result(result, study.scoring)
    g = build_grouping(study)

    group = g.groups[1]
    sub = decide_subset(scored, group.indices, study.decide)
    # every index the subset decision names is a member of that group
    for i in sub.per_axis.values():
        assert i is None or i in group.indices
    assert set(sub.composite) <= set(group.indices)
    assert sub.all_round is None or sub.all_round in group.indices

    # and it is a real restriction: the whole-table winner need not be in it
    whole = decide(scored, study.decide)
    assert whole.candidates != sub.candidates


# ---------------------------------------------------------------------------
# Levers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def solved():
    from stepgen.studio.run import run_study
    from stepgen.studio.scoring import score_result

    study = build_study(_raw(group_by=["junction.exit_width_um"]))
    result = run_study(study)
    scored = score_result(result, study.scoring)
    g = build_grouping(study)
    axes = list(g.design_axes) + list(g.condition_axes)
    leaves = {i: row_axis_values(p, axes) for i, p in enumerate(study.points)}
    return study, scored, g, leaves


def test_measured_lever_pairs_differ_on_one_axis_only(solved):
    from stepgen.studio.levers import measured_levers

    study, scored, g, leaves = solved
    group = g.groups[0]
    steps = measured_levers(scored, group.indices, leaves, g.condition_axes)
    assert steps

    for step in steps:
        for a, b in step.pairs:
            la, lb = leaves[a], leaves[b]
            differing = [k for k in la if la[k] != lb[k]]
            assert differing == [step.axis.path], differing


def test_raising_pressure_raises_throughput_and_costs_flatness(solved):
    """The trade this family lives in, read straight out of the study."""
    from stepgen.studio.levers import measured_levers

    study, scored, g, leaves = solved
    group = g.groups[0]
    po = next(a for a in g.condition_axes if a.path == "operating.Po_mbar")
    span = measured_levers(scored, group.indices, leaves, [po], mode="span")[0]

    assert span.frm == 50 and span.to == 200
    assert span.effect_on("throughput_mlhr").direction == "better"
    assert span.effect_on("uniformity_pct").direction == "worse"


def test_reversing_a_lever_recomputes_rather_than_negates(solved):
    from stepgen.studio.levers import measured_levers, reverse_step

    study, scored, g, leaves = solved
    group = g.groups[0]
    po = next(a for a in g.condition_axes if a.path == "operating.Po_mbar")
    fwd = measured_levers(scored, group.indices, leaves, [po], mode="span")[0]
    rev = reverse_step(scored, fwd)

    assert (rev.frm, rev.to) == (fwd.to, fwd.frm)
    assert rev.effect_on("throughput_mlhr").direction == "worse"
    # +100% out is -50% back: a sign flip would have been wrong
    up = fwd.effect_on("throughput_mlhr").rel
    down = rev.effect_on("throughput_mlhr").rel
    assert up is not None and down is not None
    assert down != pytest.approx(-up)
    assert -1.0 <= down < 0.0


def test_best_step_can_recommend_moving_an_axis_downwards(solved):
    """Flatness is improved by *lowering* pressure — the study swept it, so say so."""
    from stepgen.studio.levers import best_step_for, measured_levers

    study, scored, g, leaves = solved
    group = g.groups[0]
    spans = measured_levers(scored, group.indices, leaves, g.condition_axes, mode="span")

    step = best_step_for(spans, "uniformity_pct", scored)
    assert step is not None
    assert step.effect_on("uniformity_pct").direction == "better"


def test_near_zero_baseline_reports_an_absolute_change(solved):
    """A design below its production threshold must not produce a 1e14 % lever."""
    from stepgen.studio.levers import Effect, Watch

    watch = Watch("throughput_mlhr", "Throughput", +1, unit="mL/hr")
    eff = Effect(watch=watch, rel=None, delta=12.4, n=3)
    assert eff.amount() == "+12.4 mL/hr"
    assert "%" not in eff.amount()

    big = Effect(watch=watch, rel=51.0, delta=12.4, n=3)
    assert big.amount() == "×52"


def test_every_structural_lever_states_a_cost():
    from stepgen.studio.levers import STRUCTURAL

    assert STRUCTURAL
    for lever in STRUCTURAL:
        assert lever.costs, f"{lever.knob} claims a free lunch"
        assert lever.evidence
        assert lever.move in ("increase", "decrease")


def test_structural_levers_defer_to_what_the_study_measured():
    from stepgen.studio.levers import structural_levers

    all_of_them = structural_levers("throughput")
    swept = structural_levers("throughput", ["junction.exit_depth_um"])
    assert len(swept) == len(all_of_them) - 1
    assert all(l.path != "junction.exit_depth_um" for l in swept)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,spec,expected", [
    (12.6666, "f1", "12.7"),        # mL/hr and % to one decimal
    (0.04999, "f1", "0.0"),
    (11550, "int", "11,550"),
    (1333.7, "int", "1,334"),
    (52.14159, "f1", "52.1"),
    (0.00051234, "ca", "0.0005"),
    (2456.7, "freq", "2,457"),
    (12.34, "freq", "12.3"),
    (None, "f1", "—"),
    (float("nan"), "f1", "—"),
])
def test_metric_formatting(value, spec, expected):
    from stepgen.studio.workbook import fmt_metric
    assert fmt_metric(value, spec) == expected


def test_axis_values_render_with_their_own_units():
    from stepgen.studio.grouping import format_axis_value
    assert format_axis_value(0.06, "visc") == "60"        # Pa·s -> mPa·s
    assert format_axis_value(0.005, "tension") == "5"     # N/m -> mN/m
    assert format_axis_value(160.0, "num1") == "160"
    assert format_axis_value(20, "int") == "20"


# ---------------------------------------------------------------------------
# End to end on the real study config
# ---------------------------------------------------------------------------

def test_my_designs_config_is_four_designs_swept_over_length_and_pressure():
    study = load_study(MY_DESIGNS)
    g = build_grouping(study)
    assert len(g.groups) == 4, "the four exits must arrive as four designs"
    paths = {a.path for a in g.condition_axes}
    assert "main.length_mm" in paths and "operating.Po_mbar" in paths
    lengths = next(a for a in g.condition_axes if a.path == "main.length_mm")
    assert lengths.values == (20, 40, 80, 160)


def test_workbook_renders_per_design_panels_and_filters(tmp_path):
    from stepgen.studio import run_study, write_workbook

    study = build_study(_raw(group_by=["junction.exit_width_um"]))
    result = run_study(study)
    chapter = write_workbook(result, tmp_path / "grouped.html", price="never")
    doc = chapter.read_text(encoding="utf-8")

    assert "Per-design decisions — 2 designs" in doc
    assert 'id="grp-D1"' in doc and 'id="grp-D2"' in doc
    assert 'id="filters"' in doc and 'filterToDesign' in doc
    assert "Design vs design" in doc
    assert "How to push this design further" in doc
    # the mashed label is gone from the table, but still auditable in the drill-down
    assert 'data-gid="D1"' in doc
    assert "Config</h4>" in doc


def test_swept_lengths_and_derived_N_are_stated_in_the_decision_layer(tmp_path):
    """
    N and main length must be readable without scrolling into the wide table.

    Both were only ever columns; the panel a reader looks at first named neither,
    which made "best throughput at 144 mL/hr" a number with no ladder attached.
    """
    from stepgen.studio import run_study, write_workbook

    study = build_study(_raw(group_by=["junction.exit_width_um"]))
    result = run_study(study)
    doc = write_workbook(result, tmp_path / "n.html", price="never") \
        .read_text(encoding="utf-8")

    # the swept values themselves, not just the axis name
    assert "Main length: 20, 40 mm" in doc
    # N is derived, so it is reported as the range each design spans...
    assert "N 166 → 333 DFUs" in doc
    # ...and named on each winner, next to the length that produced it
    assert "Main length 40 mm" in doc
    assert "N 333 DFUs" in doc
    assert "<th>Main length (mm)</th>" in doc or "Main length (mm)" in doc
    assert ">N DFU<" in doc
