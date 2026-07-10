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
