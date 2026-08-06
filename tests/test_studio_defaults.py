"""
tests.test_studio_defaults
==========================
House defaults for the Studio front door (plan C3).

The point of the file is that it is reviewable, so these tests mostly guard
that it stays loadable and internally consistent — and that the solve-cost
entries keep the property the measurement showed: cost is linear in element
count, and one flat ms/point across all families is not good enough.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stepgen.studio.defaults import (
    DEFAULTS_PATH,
    SolveCost,
    StudioDefaults,
    load_defaults,
)

REPO = Path(__file__).resolve().parent.parent


def test_shipped_defaults_exist_and_load():
    assert DEFAULTS_PATH == REPO / "configs" / "studio_defaults.yaml"
    d = load_defaults()
    assert isinstance(d, StudioDefaults)
    assert d.source_text                       # comments preserved for the form
    assert "sweep_defaults" in d.source_text


def test_sweep_defaults_carry_the_measured_die_and_fab_caps():
    sd = load_defaults().sweep_defaults
    assert sd["footprint"]["square_side_mm"] == 100.0
    # 100 mm matters: the per-family routable fractions are measured there and
    # do not scale — a different die silently invalidates them.
    assert "reserve_border_mm" not in sd["footprint"]
    assert sd["manufacturing"]["max_main_depth_um"] == 200.0


def test_default_fluid_is_the_ow_sunflower_oil_system():
    f = load_defaults().sweep_defaults["fluids"]
    assert f["mu_dispersed"] == 0.06          # sunflower oil, never silicone
    assert f["mu_continuous"] == 0.00089      # 2% SDS water
    assert f["phase_system"] == "o/w"
    # the label must agree with the viscosities, or grouping lies
    assert f["mu_dispersed"] > f["mu_continuous"]


def test_every_family_in_the_registry_has_a_cost_entry():
    from stepgen.families import list_families

    costs = load_defaults().solve_cost
    for fam in list_families():
        assert fam in costs, f"{fam} has no measured solve cost"
    assert "default" in costs


def test_cost_for_falls_back_rather_than_raising():
    d = load_defaults()
    assert d.cost_for("hexagonal") is d.solve_cost["default"]


def test_radial_is_orders_of_magnitude_cheaper_than_serpentine():
    """
    Radial does no network solve — it is closed form.  Measured 2026-08-06 at
    0.017 ms/point against serpentine's 12.1 ms at 333 rungs.  A single flat
    rate across families would be wrong by ~700x here, which is the whole
    reason this file carries per-family numbers.
    """
    c = load_defaults().solve_cost
    assert c["radial"].us_per_element == 0.0
    assert c["radial"].ms_per_point < c["serpentine"].ms_per_point / 100


#: Measured 2026-08-06, median of 15 reps after warm-up — {rungs: ms/point}.
#: A 30x spread, which is why the flat rate alone is not good enough.
SERPENTINE_MEASURED = {83: 3.5, 333: 12.1, 666: 23.7, 1333: 47.0, 2666: 106.4}


def test_flat_rate_agrees_with_the_element_rate_at_the_reference_size():
    c = load_defaults().cost_for("serpentine")
    assert c.reference_elements == 333
    assert c.seconds(100, c.reference_elements) == pytest.approx(c.seconds(100), rel=0.02)


@pytest.mark.parametrize("rungs,measured_ms", sorted(SERPENTINE_MEASURED.items()))
def test_element_rate_reproduces_the_measured_serpentine_curve(rungs, measured_ms):
    """
    One linear rate has to cover a 30x span, so it cannot be exact anywhere.
    20% is the honest tolerance: it is close enough to size a run and loose
    enough not to break when the machine changes.
    """
    c = load_defaults().cost_for("serpentine")
    predicted_ms = c.seconds(1, rungs) * 1000.0
    assert predicted_ms == pytest.approx(measured_ms, rel=0.20)


def test_flat_rate_alone_would_not_reproduce_that_curve():
    """The justification for carrying us_per_element at all."""
    c = load_defaults().cost_for("serpentine")
    flat_ms = c.ms_per_point
    assert flat_ms == pytest.approx(SERPENTINE_MEASURED[333], rel=0.05)   # right here
    assert flat_ms != pytest.approx(SERPENTINE_MEASURED[83], rel=0.20)    # wrong here
    assert flat_ms != pytest.approx(SERPENTINE_MEASURED[2666], rel=0.20)  # and here


def test_estimate_sums_across_families():
    d = load_defaults()
    only_serp = d.estimate_seconds({"serpentine": 100})
    mixed = d.estimate_seconds({"serpentine": 100, "radial": 100})
    assert mixed > only_serp
    # …but radial adds almost nothing, which is the point
    assert mixed == pytest.approx(only_serp, rel=0.01)


def test_estimate_uses_elements_when_given():
    d = load_defaults()
    flat = d.estimate_seconds({"serpentine": 50})
    big = d.estimate_seconds({"serpentine": 50}, {"serpentine": 2666})
    assert big > flat * 5


def test_zero_us_per_element_falls_back_to_flat():
    """A closed-form family has no element rate; asking for one must not zero it."""
    c = SolveCost(us_per_element=0.0, ms_per_point=0.017, reference_elements=0)
    assert c.seconds(100, elements=999) == pytest.approx(100 * 0.017 / 1000.0)


def test_missing_default_entry_is_synthesised(tmp_path):
    """A defaults file without `default:` must not turn cost_for into KeyError."""
    p = tmp_path / "d.yaml"
    p.write_text("solve_cost:\n  serpentine:\n    ms_per_point: 5.0\n",
                 encoding="utf-8")
    d = load_defaults(p)
    assert d.cost_for("anything").ms_per_point > 0
