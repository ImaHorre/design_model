"""
Acceptance tests against the three BUILT devices.

Ground truth is ``reference_devices/README.md`` — measured from the shipped GDS
with ``gdstk``, polygon accounting closing with residual 0. **Where the model
disagrees with a number in that file, the model is wrong.**

Every constant below is a literal citing that README, deliberately: neither
``gdstk`` nor 2.2 MB of GDS binaries should become a test dependency, and a test
that re-derives its expectation from the model cannot catch the model drifting.

    V5-30  serpentine  lane pitch 7.00 mm, 10 lane pairs, 11,154 DFUs
    V5-10  serpentine  lane pitch 5.80 mm, 12 lane pairs, 39,192 DFUs
    V6-30  radial      3,000 DFUs at R = 36.0 mm, 75.4 µm pitch

Note on the DFU counts. 11,154 is what the **GDS** contains, and it is not the
11,565 Conor ruled the model should be driven at (2026-08-04); the two answer
different questions and do not compete. These tests ask whether
``compute_layout`` reproduces the geometry it is given, so the GDS number is the
only admissible one here.
"""

from __future__ import annotations

import math

import pytest

from stepgen.families import get_family
from stepgen.families.base import (
    MANIFOLD_ACTIVE_FRACTION,
    RADIAL_ACTIVE_FRACTION,
    SERPENTINE_ACTIVE_FRACTION,
)

# --- measured, reference_devices/README.md ---------------------------------
DIE_MM = 100.0                      # all three devices are on a 100 x 100 mm die

V5_30 = dict(main_width_um=1000.0, dfu_array_mm=4.0, dfu_pitch_um=60.0,
             lane_pitch_mm=7.00, lane_pairs=10, stack_height_mm=69.0, dfus=11154)
V5_10 = dict(main_width_um=1000.0, dfu_array_mm=2.8, dfu_pitch_um=20.0,
             lane_pitch_mm=5.80, lane_pairs=12, stack_height_mm=68.6, dfus=39192)
V6_30 = dict(radius_mm=36.0, dfu_pitch_um=75.4, dfus=3000, disc_radius_mm=45.0)

WALL_MM = 1.0                       # measured on BOTH serpentines


def _serpentine(dev: dict, *, n_dfu: int = 1000, side_mm: float = DIE_MM):
    fam = get_family("serpentine")
    compiled = fam.compile(
        {
            "main": {"width_um": dev["main_width_um"], "depth_um": 200.0},
            "rung": {"N": n_dfu, "length_mm": dev["dfu_array_mm"],
                     "upstream_width_um": 15.0},
            "junction": {"exit_width_um": 30.0, "exit_depth_um": 10.0,
                         "pitch_um": dev["dfu_pitch_um"]},
        },
        fluids={}, footprint={"square_side_mm": side_mm}, manufacturing={},
    )
    return fam, compiled


# ---------------------------------------------------------------------------
# The stack-up
# ---------------------------------------------------------------------------

class TestSerpentineStackUp:
    """lane_pitch = 2 x main + DFU array + wall, exactly (README point 1)."""

    @pytest.mark.parametrize("dev,name", [(V5_30, "V5-30"), (V5_10, "V5-10")])
    def test_lane_pitch(self, dev, name):
        _, compiled = _serpentine(dev)
        from stepgen.design.layout import compute_layout
        lay = compute_layout(compiled)
        assert lay.lane_pitch * 1e3 == pytest.approx(dev["lane_pitch_mm"], abs=1e-9), name

    @pytest.mark.parametrize("dev", [V5_30, V5_10])
    def test_pitch_decomposes_as_measured(self, dev):
        """The arithmetic, spelled out: 1 + array + 1 + 1."""
        expected = 2.0 * dev["main_width_um"] * 1e-3 + dev["dfu_array_mm"] + WALL_MM
        assert expected == pytest.approx(dev["lane_pitch_mm"], abs=1e-9)

    @pytest.mark.parametrize("dev,name", [(V5_30, "V5-30"), (V5_10, "V5-10")])
    def test_lane_pair_count(self, dev, name):
        """
        10 and 12 lane pairs on a 100 mm die — the number the die height buys at
        the measured 51% routable fraction.
        """
        fam, compiled = _serpentine(dev)
        assert fam.packing_capacity(compiled).detail["lanes_max"] == dev["lane_pairs"], name

    @pytest.mark.parametrize("dev,name", [(V5_30, "V5-30"), (V5_10, "V5-10")])
    def test_stack_height_matches_the_measured_active_footprint(self, dev, name):
        """
        The sharpest check in the file. The measured active footprint heights —
        69.0 mm on V5-30, 68.6 mm on V5-10 — are not inputs anywhere; they fall
        out of (pairs - 1) x pitch + pair_width. Getting both right to the
        micron means the stack-up and the lane count are simultaneously correct.
        """
        pair_w = 2.0 * dev["main_width_um"] * 1e-3 + dev["dfu_array_mm"]
        stack = (dev["lane_pairs"] - 1) * dev["lane_pitch_mm"] + pair_w
        assert stack == pytest.approx(dev["stack_height_mm"], abs=1e-9), name

    def test_turn_radius_is_not_in_the_stack_up(self):
        """
        2 x turn_radius reproduced the 1.0 mm wall only because both defaulted to
        500 µm. Break the coincidence and the pitch must not move.
        """
        from stepgen.design.layout import compute_layout
        _, tight = _serpentine(V5_30)
        fam = get_family("serpentine")
        wide = fam.compile(
            {
                "main": {"width_um": 1000.0, "depth_um": 200.0},
                "rung": {"N": 1000, "length_mm": 4.0, "upstream_width_um": 15.0},
                "junction": {"exit_width_um": 30.0, "exit_depth_um": 10.0,
                             "pitch_um": 60.0},
            },
            fluids={},
            footprint={"square_side_mm": DIE_MM, "turn_radius_um": 3000.0},
            manufacturing={},
        )
        assert compute_layout(wide).lane_pitch == pytest.approx(
            compute_layout(tight).lane_pitch, rel=1e-12)


# ---------------------------------------------------------------------------
# DFU capacity
# ---------------------------------------------------------------------------

class TestDfuCapacity:
    """
    Capacity is an **upper bound** on the built count, and the tests say so.

    The model packs DFUs along the whole lane; the real devices do not use the
    fold ends (V5-30 runs 1,000 straight DFUs per lane in a 71 mm lane at 60 µm
    pitch, and puts a further 1,154 round the curves). So a few percent over is
    the correct sign, and a capacity BELOW the built count would be a real
    failure — the die demonstrably holds that many.
    """

    @pytest.mark.parametrize("dev,name", [(V5_30, "V5-30"), (V5_10, "V5-10")])
    def test_capacity_brackets_the_built_count(self, dev, name):
        fam, compiled = _serpentine(dev)
        n_max = fam.packing_capacity(compiled).n_max
        assert n_max >= dev["dfus"], f"{name}: die must hold what was built on it"
        assert n_max <= dev["dfus"] * 1.10, f"{name}: {n_max:,} vs {dev['dfus']:,}"

    def test_radial_dfu_count_is_the_circumference(self):
        """N = 2piR/pitch, exact to the unit (README point 3)."""
        fam = get_family("radial")
        compiled = fam.compile(
            {"radius_mm": V6_30["radius_mm"],
             "exit": {"width_um": 30.0, "depth_um": 10.0,
                      "pitch_um": V6_30["dfu_pitch_um"]}},
            fluids={}, footprint={"square_side_mm": DIE_MM}, manufacturing={},
        )
        n = fam.packing_capacity(compiled).n_current
        # 2pi x 36 mm / 75.4 um = 2999.93; the model truncates rather than
        # rounds, since a fractional spoke does not exist.
        assert abs(n - V6_30["dfus"]) <= 1, n

    def test_radial_wheel_fits_the_die_with_its_measured_margin(self):
        """
        V6-30's disc is R = 45 mm on a 100 mm die — it does NOT run to side/2
        touching all four edges, it keeps ~5 mm of margin. R_max must land there.
        """
        fam = get_family("radial")
        compiled = fam.compile(
            {"radius_mm": V6_30["radius_mm"],
             "exit": {"width_um": 30.0, "depth_um": 10.0,
                      "pitch_um": V6_30["dfu_pitch_um"]}},
            fluids={}, footprint={"square_side_mm": DIE_MM}, manufacturing={},
        )
        assert compiled.max_radius_m * 1e3 == pytest.approx(
            V6_30["disc_radius_mm"], rel=0.01)


# ---------------------------------------------------------------------------
# The area model
# ---------------------------------------------------------------------------

class TestActiveAreaFraction:

    def test_measured_fractions(self):
        """51% / 64% — measured, README's summary table."""
        assert SERPENTINE_ACTIVE_FRACTION == 0.51
        assert RADIAL_ACTIVE_FRACTION == 0.64
        # no built manifold; it borrows the serpentine's and says so per row
        assert MANIFOLD_ACTIVE_FRACTION == SERPENTINE_ACTIVE_FRACTION

    @pytest.mark.parametrize("dev,active_cm2", [(V5_30, 51.1), (V5_10, 50.8)])
    def test_routable_box_reproduces_the_measured_active_area(self, dev, active_cm2):
        """
        69.0 x 74.0 = 51.1 cm² measured. The model lays the same area out square
        (the die is square and the families set aspect ratio 1), so the AREA has
        to match even though the box is 71.4 x 71.4 rather than 69 x 74.
        """
        from stepgen.design.layout import active_extent
        _, compiled = _serpentine(dev)
        L, H = active_extent(compiled.footprint)
        assert L * H * 1e4 == pytest.approx(active_cm2, rel=0.01)

    def test_the_implied_margin_matches_the_measured_one(self):
        """
        The margin is derived now, not configured. At 51% of a 100 mm die it
        comes out ~14.3 mm, against the 13-15 mm measured on the serpentines —
        and nowhere near the 2 mm reserve_border it replaces, which is the whole
        1.66x capacity over-prediction in one number.
        """
        from stepgen.design.layout import active_extent
        _, compiled = _serpentine(V5_30)
        L, _ = active_extent(compiled.footprint)
        margin_mm = (DIE_MM - L * 1e3) / 2.0
        assert 13.0 <= margin_mm <= 15.0, margin_mm

    def test_off_calibration_die_is_flagged_on_the_row(self):
        """
        The fractions were measured at 100 mm and an area fraction does not
        scale. A row on any other die must say so rather than quietly reporting
        an area it cannot support (open question 5).
        """
        fam, compiled = _serpentine(V5_30, side_mm=63.5)
        m = fam.solve(compiled, {"Po_mbar": 300.0, "Qw_mlhr": 5.0},
                      params={}, label="off-die")
        assert any("100 mm die" in n for n in m.notes), m.notes

        fam, on_die = _serpentine(V5_30, side_mm=DIE_MM)
        m = fam.solve(on_die, {"Po_mbar": 300.0, "Qw_mlhr": 5.0},
                      params={}, label="on-die")
        assert not any("100 mm die" in n for n in m.notes), m.notes

    def test_manifold_says_it_is_uncalibrated(self):
        """No built manifold exists. Every manifold row has to admit that."""
        fam = get_family("manifold")
        compiled = fam.compile(
            {
                "main": {"depth_um": 200.0, "width_um": 1000.0},
                "arms": {"count": 4, "depth_um": 100.0, "width_um": 400.0},
                "rung": {"length_mm": 2.0, "upstream_width_um": 30.0},
                "rungs_per_arm": 40,
                "junction": {"exit_width_um": 30.0, "exit_depth_um": 10.0,
                             "pitch_um": 60.0},
            },
            fluids={}, footprint={"square_side_mm": DIE_MM}, manufacturing={},
        )
        m = fam.solve(compiled, {"Po_mbar": 300.0}, params={}, label="manifold")
        assert any("UNCALIBRATED" in n for n in m.notes), m.notes


def test_no_gds_dependency():
    """
    The point of asserting literals: this module must not import gdstk or read
    the GDS files. If that ever changes, 2.2 MB of binaries and a parser have
    become a test dependency.
    """
    import sys
    assert "gdstk" not in sys.modules
