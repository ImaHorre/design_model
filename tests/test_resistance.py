"""
Unit tests for stepgen.models.resistance.
"""

import math
import pytest

from stepgen.models.resistance import (
    hydraulic_resistance_rectangular,
    resistance_piecewise,
)
from stepgen.config import MicrochannelSection


class TestHydraulicResistanceRectangular:
    def test_base_formula_no_correction(self):
        mu, L, w, h = 1e-3, 100e-6, 10e-6, 5e-6
        expected = 12.0 * mu * L / (w * h ** 3)
        result = hydraulic_resistance_rectangular(mu, L, w, h, correction=False)
        assert math.isclose(result, expected, rel_tol=1e-12)

    def test_correction_increases_resistance(self):
        # denom = 1 - 0.63*(h/w) < 1 for h < w  →  R_corrected > R_base
        mu, L, w, h = 1e-3, 100e-6, 10e-6, 5e-6
        R_base = hydraulic_resistance_rectangular(mu, L, w, h, correction=False)
        R_corr = hydraulic_resistance_rectangular(mu, L, w, h, correction=True)
        assert R_corr > R_base

    def test_correction_formula(self):
        mu, L, w, h = 1e-3, 100e-6, 10e-6, 5e-6
        base = 12.0 * mu * L / (w * h ** 3)
        denom = 1.0 - 0.63 * (h / w)
        expected = base / denom
        result = hydraulic_resistance_rectangular(mu, L, w, h, correction=True)
        assert math.isclose(result, expected, rel_tol=1e-12)

    def test_seed_defaults_mu_oil(self):
        # Reproduces the rung resistance used in the seed for its default geometry.
        # constriction_ratio=1.0  →  constriction_l = mcl = 200e-6
        mu_oil = 0.03452
        result = hydraulic_resistance_rectangular(
            mu_oil, 200e-6, 1e-6, 0.3e-6, correction=True
        )
        assert result > 0

    def test_bad_inputs_raise(self):
        with pytest.raises(ValueError):
            hydraulic_resistance_rectangular(-1e-3, 100e-6, 10e-6, 5e-6)
        with pytest.raises(ValueError):
            hydraulic_resistance_rectangular(1e-3, 0.0, 10e-6, 5e-6)
        with pytest.raises(ValueError):
            hydraulic_resistance_rectangular(1e-3, 100e-6, 0.0, 5e-6)
        with pytest.raises(ValueError):
            hydraulic_resistance_rectangular(1e-3, 100e-6, 10e-6, 0.0)

    def test_correction_invalid_geometry_raises(self):
        # depth/width > 1/0.63 ≈ 1.587 makes denom <= 0
        with pytest.raises(ValueError):
            hydraulic_resistance_rectangular(1e-3, 100e-6, 1e-6, 2e-6, correction=True)


class TestResistancePiecewise:
    def test_two_sections_match_single_call_sum(self):
        mu = 1e-3
        s1 = MicrochannelSection(length=180e-6, width=0.5e-6, depth=0.3e-6)
        s2 = MicrochannelSection(length=20e-6,  width=1.0e-6, depth=0.3e-6)
        R1 = hydraulic_resistance_rectangular(mu, s1.length, s1.width, s1.depth)
        R2 = hydraulic_resistance_rectangular(mu, s2.length, s2.width, s2.depth)
        result = resistance_piecewise((s1, s2), mu)
        assert math.isclose(result, R1 + R2, rel_tol=1e-12)

    def test_single_section_matches_direct(self):
        mu = 0.03452
        s = MicrochannelSection(length=200e-6, width=1e-6, depth=0.3e-6)
        expected = hydraulic_resistance_rectangular(mu, s.length, s.width, s.depth)
        result = resistance_piecewise((s,), mu)
        assert math.isclose(result, expected, rel_tol=1e-12)

    def test_empty_sections_raises(self):
        with pytest.raises(ValueError):
            resistance_piecewise((), 1e-3)
