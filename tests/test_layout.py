"""
Tests for stepgen.design.layout.compute_layout.

Covers:
  - LayoutResult field types and positivity
  - Lane geometry formulas (lane_length, lane_pair_width, lane_pitch)
  - num_lanes ceiling logic
  - total_height formula for 1 and N lanes
  - fits_footprint true/false cases
  - footprint_area_used formula and comparison to chip area
"""

from __future__ import annotations

import math

import pytest

from stepgen.config import (
    DeviceConfig, FluidConfig, FootprintConfig, GeometryConfig,
    JunctionConfig, MainChannelConfig, ManufacturingConfig,
    OperatingConfig, RungConfig,
)
from stepgen.design.layout import LayoutResult, compute_layout


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

def _make_config(
    Mcl: float = 30e-3,          # main channel routed length [m]
    Mcw: float = 500e-6,
    Mcd: float = 100e-6,
    footprint_area_cm2: float = 10.0,
    footprint_aspect_ratio: float = 1.5,
    lane_spacing: float = 500e-6,
    turn_radius: float = 500e-6,
    reserve_border: float = 2e-3,
) -> DeviceConfig:
    pitch = 100e-6  # 0.1 mm pitch; Nmc = floor(Mcl / pitch)
    return DeviceConfig(
        fluids=FluidConfig(
            mu_continuous=0.00089, mu_dispersed=0.03452, emulsion_ratio=0.3,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=Mcd, Mcw=Mcw, Mcl=Mcl),
            rung=RungConfig(
                mcd=0.3e-6, mcw=1e-6, mcl=200e-6,
                pitch=pitch, constriction_ratio=1.0,
            ),
            junction=JunctionConfig(exit_width=1e-6, exit_depth=0.3e-6),
        ),
        operating=OperatingConfig(Po_in_mbar=200.0, Qw_in_mlhr=5.0),
        footprint=FootprintConfig(
            footprint_area_cm2=footprint_area_cm2,
            footprint_aspect_ratio=footprint_aspect_ratio,
            lane_spacing=lane_spacing,
            turn_radius=turn_radius,
            reserve_border=reserve_border,
        ),
    )


# Reusable helper: expected L_useful for default chip
def _L_useful(cfg: DeviceConfig) -> float:
    fp = cfg.footprint
    area_m2 = fp.footprint_area_cm2 * 1e-4
    W = math.sqrt(area_m2 * fp.footprint_aspect_ratio)
    return W - 2.0 * fp.reserve_border


def _H_useful(cfg: DeviceConfig) -> float:
    fp = cfg.footprint
    area_m2 = fp.footprint_area_cm2 * 1e-4
    H = math.sqrt(area_m2 / fp.footprint_aspect_ratio)
    return H - 2.0 * fp.reserve_border


# ---------------------------------------------------------------------------
# Basic / type checks
# ---------------------------------------------------------------------------

class TestLayoutTypes:

    def test_returns_layout_result(self):
        cfg = _make_config()
        result = compute_layout(cfg)
        assert isinstance(result, LayoutResult)

    def test_fits_footprint_is_bool(self):
        cfg = _make_config()
        assert isinstance(compute_layout(cfg).fits_footprint, bool)

    def test_num_lanes_is_int(self):
        cfg = _make_config()
        assert isinstance(compute_layout(cfg).num_lanes, int)

    def test_all_float_fields_positive(self):
        cfg = _make_config()
        r = compute_layout(cfg)
        for val in (r.lane_length, r.lane_pair_width, r.lane_pitch,
                    r.total_height, r.footprint_area_used):
            assert val > 0.0

    def test_num_lanes_at_least_one(self):
        cfg = _make_config(Mcl=1e-3)  # 1 mm — fits in one lane
        assert compute_layout(cfg).num_lanes >= 1


# ---------------------------------------------------------------------------
# Lane geometry formulas
# ---------------------------------------------------------------------------

class TestLaneGeometry:

    def test_lane_length_formula(self):
        """lane_length = sqrt(A*AR) − 2*border."""
        cfg = _make_config()
        expected = _L_useful(cfg)
        assert compute_layout(cfg).lane_length == pytest.approx(expected, rel=1e-10)

    def test_lane_pair_width_formula(self):
        """lane_pair_width = 2*Mcw + lane_spacing."""
        cfg = _make_config(Mcw=400e-6, lane_spacing=300e-6)
        expected = 2.0 * 400e-6 + 300e-6
        assert compute_layout(cfg).lane_pair_width == pytest.approx(expected, rel=1e-10)

    def test_lane_pitch_formula(self):
        """lane_pitch = lane_pair_width + 2*turn_radius."""
        cfg = _make_config(Mcw=400e-6, lane_spacing=300e-6, turn_radius=600e-6)
        lane_pair_width = 2.0 * 400e-6 + 300e-6
        expected = lane_pair_width + 2.0 * 600e-6
        assert compute_layout(cfg).lane_pitch == pytest.approx(expected, rel=1e-10)

    def test_lane_pitch_gt_lane_pair_width(self):
        """Pitch must be larger than pair width (room for U-turns)."""
        cfg = _make_config()
        r = compute_layout(cfg)
        assert r.lane_pitch > r.lane_pair_width


# ---------------------------------------------------------------------------
# num_lanes ceiling logic
# ---------------------------------------------------------------------------

class TestNumLanes:

    def test_single_lane_when_mcl_le_lane_length(self):
        """Mcl fits in one pass → num_lanes = 1."""
        cfg = _make_config(Mcl=10e-3)  # 10 mm << L_useful ≈ 34.7 mm
        assert compute_layout(cfg).num_lanes == 1

    def test_num_lanes_ceil(self):
        """num_lanes = ceil(Mcl / lane_length)."""
        cfg_base = _make_config()
        L = _L_useful(cfg_base)
        # Mcl = 2.5 × L_useful → ceil(2.5) = 3
        cfg = _make_config(Mcl=2.5 * L)
        assert compute_layout(cfg).num_lanes == 3

    def test_num_lanes_exact_multiple(self):
        """Mcl = exactly 2 × L_useful → num_lanes = 2 (not 3)."""
        cfg_base = _make_config()
        L = _L_useful(cfg_base)
        cfg = _make_config(Mcl=2.0 * L)
        assert compute_layout(cfg).num_lanes == 2

    def test_larger_mcl_more_lanes(self):
        """Increasing Mcl increases (or maintains) num_lanes."""
        cfg_small = _make_config(Mcl=50e-3)
        cfg_large = _make_config(Mcl=200e-3)
        assert compute_layout(cfg_large).num_lanes >= compute_layout(cfg_small).num_lanes


# ---------------------------------------------------------------------------
# total_height formula
# ---------------------------------------------------------------------------

class TestTotalHeight:

    def test_single_lane_total_height(self):
        """1 lane: total_height = lane_pair_width (no inter-lane gap)."""
        cfg = _make_config(Mcl=5e-3)   # 5 mm → 1 lane
        r = compute_layout(cfg)
        assert r.num_lanes == 1
        assert r.total_height == pytest.approx(r.lane_pair_width, rel=1e-10)

    def test_multi_lane_total_height(self):
        """N lanes: total_height = (N−1)*lane_pitch + lane_pair_width."""
        cfg_base = _make_config()
        L = _L_useful(cfg_base)
        cfg = _make_config(Mcl=2.5 * L)  # → 3 lanes
        r = compute_layout(cfg)
        assert r.num_lanes == 3
        expected = 2.0 * r.lane_pitch + r.lane_pair_width
        assert r.total_height == pytest.approx(expected, rel=1e-10)

    def test_total_height_increases_with_lanes(self):
        cfg_base = _make_config()
        L = _L_useful(cfg_base)
        r1 = compute_layout(_make_config(Mcl=L * 1.0))   # 1 lane
        r2 = compute_layout(_make_config(Mcl=L * 2.5))   # 3 lanes
        assert r2.total_height > r1.total_height


# ---------------------------------------------------------------------------
# fits_footprint
# ---------------------------------------------------------------------------

class TestFitsFootprint:

    def test_fits_true_for_small_device(self):
        """A 10-rung device with 30 µm Mcl fits easily on a 10 cm² chip."""
        cfg = _make_config(Mcl=30e-6)
        assert compute_layout(cfg).fits_footprint is True

    def test_fits_true_implies_total_height_le_H_useful(self):
        cfg = _make_config(Mcl=30e-6)
        r = compute_layout(cfg)
        if r.fits_footprint:
            assert r.total_height <= _H_useful(cfg) + 1e-12  # tolerance

    def test_fits_false_for_large_device(self):
        """Very long Mcl forces many lanes that exceed chip height."""
        # Need total_height > H_useful.
        # H_useful ≈ 21.8 mm for default chip; lane_pitch ≈ 2.5 mm.
        # 10 lanes: total_height = 9*2.5 + 1.5 = 24 mm > 21.8 mm → no fit.
        cfg_base = _make_config()
        L = _L_useful(cfg_base)
        cfg = _make_config(Mcl=10.0 * L)   # → 10 lanes
        r = compute_layout(cfg)
        assert r.num_lanes == 10
        assert r.fits_footprint is False

    def test_fits_consistent_with_total_height(self):
        """fits_footprint must agree with total_height ≤ H_useful."""
        for Mcl in [10e-3, 50e-3, 150e-3, 400e-3]:
            cfg = _make_config(Mcl=Mcl)
            r = compute_layout(cfg)
            H_u = _H_useful(cfg)
            if r.fits_footprint:
                assert r.total_height <= H_u + 1e-12
            else:
                assert r.total_height > H_u - 1e-12


# ---------------------------------------------------------------------------
# footprint_area_used
# ---------------------------------------------------------------------------

class TestFootprintAreaUsed:

    def test_positive(self):
        cfg = _make_config()
        assert compute_layout(cfg).footprint_area_used > 0.0

    def test_formula(self):
        """footprint_area_used = (total_height + 2*border) * (lane_length + 2*border)."""
        cfg = _make_config()
        r = compute_layout(cfg)
        border = cfg.footprint.reserve_border
        expected = (r.total_height + 2.0 * border) * (r.lane_length + 2.0 * border)
        assert r.footprint_area_used == pytest.approx(expected, rel=1e-10)

    def test_lte_chip_area_when_fits(self):
        """If device fits, area_used ≤ chip total area."""
        cfg = _make_config(Mcl=30e-6)
        r = compute_layout(cfg)
        assert r.fits_footprint is True
        chip_area = cfg.footprint.footprint_area_cm2 * 1e-4
        assert r.footprint_area_used <= chip_area + 1e-12

    def test_larger_device_larger_area(self):
        """More lanes → larger footprint area used."""
        cfg_base = _make_config()
        L = _L_useful(cfg_base)
        r1 = compute_layout(_make_config(Mcl=L * 0.5))   # 1 lane
        r2 = compute_layout(_make_config(Mcl=L * 3.5))   # 4 lanes
        assert r2.footprint_area_used > r1.footprint_area_used
