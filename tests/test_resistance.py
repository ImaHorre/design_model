"""
Unit tests for stepgen.models.resistance.
"""

import math
import pytest

from stepgen.models.resistance import (
    hydraulic_resistance_rectangular,
    rect_duct_fRe,
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
        # R = fRe(alpha) * mu * L / (2 * A * D_h^2) -- the normalisation the
        # Shah & London polynomial is DEFINED against. See TestExactSolution for
        # why this one and not f(alpha)*mu*L/(w*h^3).
        mu, L, w, h = 1e-3, 100e-6, 10e-6, 5e-6
        A = w * h
        D_h = 4.0 * A / (2.0 * (w + h))
        expected = rect_duct_fRe(h / w) * mu * L / (2.0 * A * D_h ** 2)
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

    def test_deep_narrow_channel_is_modelled_not_rejected(self):
        """
        The real V5-30 DFU is 8 µm wide x 10 µm DEEP (reference_devices/README.md).

        Every implementation before W2-1 either raised on it (h/w >= 1.587), or
        rejected h >= w outright, or silently divided by a correction outside its
        domain. Ordering the dimensions makes alpha <= 1 unconditionally, so this
        geometry is now just a duct.
        """
        R = hydraulic_resistance_rectangular(0.06, 4020e-6, 8e-6, 10e-6)
        assert R > 0
        # A duct does not care which way round you name its sides.
        R_swapped = hydraulic_resistance_rectangular(0.06, 4020e-6, 10e-6, 8e-6)
        assert math.isclose(R, R_swapped, rel_tol=1e-12)


class TestExactSolution:
    """
    The closed form against the exact Fourier-series solution for a rectangular
    duct. This is the check that stands between the model and a third wrong
    normalisation: two shipped implementations were 1.55x and 2.47x off, and both
    looked plausible until compared to something that is not a correlation.

        Q = (dP/L) * a*b^3/(12 mu) * [1 - 192*b/(pi^5*a) * SUM tanh(n*pi*a/2b)/n^5]
    """

    @staticmethod
    def _exact(mu, L, w, h, terms=200):
        a, b = max(w, h), min(w, h)
        s = sum(math.tanh(n * math.pi * a / (2 * b)) / n ** 5
                for n in range(1, 2 * terms, 2))
        return 12.0 * mu * L / (a * b ** 3 * (1.0 - 192.0 * b / (math.pi ** 5 * a) * s))

    @pytest.mark.parametrize(
        "alpha", [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    def test_matches_series_to_four_significant_figures(self, alpha):
        mu, L, w = 1e-3, 1e-3, 100e-6
        h = w * alpha
        exact = self._exact(mu, L, w, h)
        assert math.isclose(
            hydraulic_resistance_rectangular(mu, L, w, h), exact, rel_tol=1e-3)

    def test_parallel_plate_limit(self):
        """As alpha -> 0 the duct becomes parallel plates: R -> 12 mu L /(w h^3)."""
        mu, L, w, h = 1e-3, 1e-3, 100e-6, 1e-7
        assert math.isclose(
            hydraulic_resistance_rectangular(mu, L, w, h),
            12.0 * mu * L / (w * h ** 3), rel_tol=2e-3)

    def test_the_normalisation_that_shipped_was_wrong(self):
        """
        `f(alpha)*mu*L/(w*h^3)` -- Shah & London's polynomial dropped into the
        parallel-plate form -- is 8x high as alpha -> 0 and 2.47x high on V5-30.
        Pinned so nobody "restores" it.
        """
        mu, L, w, h = 0.06, 4020e-6, 8e-6, 10e-6
        wrong = rect_duct_fRe(min(w, h) / max(w, h)) * mu * L / (max(w, h) * min(w, h) ** 3)
        assert math.isclose(wrong / self._exact(mu, L, w, h), 2.47, rel_tol=5e-3)

    def test_v5_30_rung_piecewise(self):
        """
        The measured two-width DFU, integrated piecewise (reference_devices/README).
        The narrow section carries 98.8% of the resistance.
        """
        mu = 0.06
        narrow = hydraulic_resistance_rectangular(mu, 3610e-6, 8e-6, 10e-6)
        wide = hydraulic_resistance_rectangular(mu, 410e-6, 30e-6, 10e-6)
        assert math.isclose(narrow / (narrow + wide), 0.988, abs_tol=0.002)
        assert math.isclose(narrow + wide, 9.98e17, rel_tol=0.01)


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
