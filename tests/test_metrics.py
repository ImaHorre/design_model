"""
Tests for stepgen.models.droplets and stepgen.models.metrics.

Covers:
  - droplet_diameter / droplet_volume / droplet_frequency
  - compute_metrics field types, mathematical identities, and edge cases
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from stepgen.config import (
    DeviceConfig, DropletModelConfig, FluidConfig, GeometryConfig,
    JunctionConfig, MainChannelConfig, OperatingConfig, RungConfig,
)
from stepgen.models.droplets import (
    droplet_diameter, droplet_frequency, droplet_volume,
)
from stepgen.models.generator import iterative_solve
from stepgen.models.hydraulics import simulate
from stepgen.models.metrics import DeviceMetrics, compute_metrics

# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

_PITCH = 3.0e-6


def _make_config(
    Nmc: int = 10,
    Po_in_mbar: float = 200.0,
    Qw_in_mlhr: float = 5.0,
    dP_cap_ow_mbar: float = 50.0,
    dP_cap_wo_mbar: float = 30.0,
    k: float = 1.2,
    a: float = 0.5,
    b: float = 0.3,
    exit_width: float = 1e-6,
    exit_depth: float = 0.3e-6,
) -> DeviceConfig:
    return DeviceConfig(
        fluids=FluidConfig(
            mu_continuous=0.00089,
            mu_dispersed=0.03452,
            emulsion_ratio=0.3,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=100e-6, Mcw=500e-6, Mcl=_PITCH * Nmc),
            rung=RungConfig(
                mcd=0.3e-6, mcw=1e-6, mcl=200e-6,
                pitch=_PITCH, constriction_ratio=1.0,
            ),
            junction=JunctionConfig(
                exit_width=exit_width, exit_depth=exit_depth,
            ),
        ),
        operating=OperatingConfig(
            Po_in_mbar=Po_in_mbar,
            Qw_in_mlhr=Qw_in_mlhr,
            P_out_mbar=0.0,
        ),
        droplet_model=DropletModelConfig(
            k=k, a=a, b=b,
            dP_cap_ow_mbar=dP_cap_ow_mbar,
            dP_cap_wo_mbar=dP_cap_wo_mbar,
        ),
    )


# ---------------------------------------------------------------------------
# droplet_diameter
# ---------------------------------------------------------------------------

class TestDropletDiameter:

    def test_power_law_formula(self):
        """D = k * w^a * h^b verified against hand calculation."""
        k, a, b = 1.2, 0.5, 0.3
        w, h = 2e-6, 1e-6
        expected = k * (w ** a) * (h ** b)
        cfg = _make_config(k=k, a=a, b=b, exit_width=w, exit_depth=h)
        assert droplet_diameter(cfg) == pytest.approx(expected, rel=1e-12)

    def test_diameter_positive(self):
        cfg = _make_config()
        assert droplet_diameter(cfg) > 0.0

    def test_diameter_scales_with_width(self):
        """Wider exit → larger droplet."""
        cfg_narrow = _make_config(exit_width=0.5e-6)
        cfg_wide   = _make_config(exit_width=2.0e-6)
        assert droplet_diameter(cfg_wide) > droplet_diameter(cfg_narrow)

    def test_diameter_scales_with_depth(self):
        """Deeper exit → larger droplet."""
        cfg_shallow = _make_config(exit_depth=0.1e-6)
        cfg_deep    = _make_config(exit_depth=1.0e-6)
        assert droplet_diameter(cfg_deep) > droplet_diameter(cfg_shallow)

    def test_diameter_micron_scale(self):
        """For typical exit geometry, D should be in the ~1–100 µm range."""
        cfg = _make_config()
        D = droplet_diameter(cfg)
        assert 1e-7 < D < 1e-4   # 0.1 µm to 100 µm

    def test_k_scales_diameter_linearly(self):
        """Doubling k doubles D."""
        cfg1 = _make_config(k=1.0)
        cfg2 = _make_config(k=2.0)
        assert droplet_diameter(cfg2) == pytest.approx(2.0 * droplet_diameter(cfg1))


# ---------------------------------------------------------------------------
# droplet_volume
# ---------------------------------------------------------------------------

class TestDropletVolume:

    def test_formula(self):
        D = 10e-6
        expected = math.pi / 6.0 * D ** 3
        assert droplet_volume(D) == pytest.approx(expected, rel=1e-12)

    def test_positive(self):
        assert droplet_volume(5e-6) > 0.0

    def test_scales_cubic(self):
        """Doubling D increases volume by factor 8."""
        V1 = droplet_volume(1e-6)
        V2 = droplet_volume(2e-6)
        assert V2 == pytest.approx(8.0 * V1, rel=1e-10)


# ---------------------------------------------------------------------------
# droplet_frequency
# ---------------------------------------------------------------------------

class TestDropletFrequency:

    def test_scalar(self):
        D = 10e-6
        Q = 1e-12  # 1 pL/s
        V = droplet_volume(D)
        expected = Q / V
        assert droplet_frequency(Q, D) == pytest.approx(expected, rel=1e-12)

    def test_array(self):
        D = 5e-6
        Q = np.array([1e-12, 2e-12, 3e-12])
        V = droplet_volume(D)
        result = droplet_frequency(Q, D)
        np.testing.assert_allclose(result, Q / V, rtol=1e-12)
        assert result.shape == (3,)

    def test_zero_Q_gives_zero_f(self):
        assert droplet_frequency(0.0, 10e-6) == pytest.approx(0.0)

    def test_proportional_to_Q(self):
        """Frequency scales linearly with flow."""
        D = 8e-6
        f1 = droplet_frequency(1e-12, D)
        f2 = droplet_frequency(3e-12, D)
        assert f2 == pytest.approx(3.0 * f1, rel=1e-10)

    def test_inversely_proportional_to_D_cubed(self):
        """f ~ 1/D³ for fixed Q."""
        Q = 1e-12
        D1, D2 = 5e-6, 10e-6
        f1 = droplet_frequency(Q, D1)
        f2 = droplet_frequency(Q, D2)
        assert f1 == pytest.approx(f2 * (D2 / D1) ** 3, rel=1e-10)


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------

class TestComputeMetricsTypes:

    def test_returns_device_metrics(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert isinstance(m, DeviceMetrics)

    def test_nmc_matches(self):
        cfg = _make_config(Nmc=15)
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.Nmc == 15

    def test_all_fields_are_floats(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        float_fields = [
            m.Q_oil_total, m.Q_water_total, m.Q_per_rung_avg,
            m.Q_spread_pct, m.dP_spread_pct, m.P_peak,
            m.active_fraction, m.reverse_fraction, m.off_fraction,
            m.D_pred, m.f_pred_mean, m.delam_line_load, m.collapse_index,
        ]
        for v in float_fields:
            assert isinstance(v, float)


class TestComputeMetricsIdentities:

    def test_fractions_sum_to_one(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        total = m.active_fraction + m.reverse_fraction + m.off_fraction
        assert total == pytest.approx(1.0, abs=1e-10)

    def test_fractions_in_unit_interval(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        for frac in (m.active_fraction, m.reverse_fraction, m.off_fraction):
            assert 0.0 <= frac <= 1.0

    def test_P_peak_equals_max_oil(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.P_peak == pytest.approx(float(np.max(result.P_oil)), rel=1e-12)

    def test_P_peak_positive(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.P_peak > 0.0

    def test_D_pred_matches_droplet_diameter(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.D_pred == pytest.approx(droplet_diameter(cfg), rel=1e-12)

    def test_delam_line_load_formula(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        expected = m.P_peak * cfg.geometry.main.Mcw
        assert m.delam_line_load == pytest.approx(expected, rel=1e-12)

    def test_collapse_index_formula(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        expected = cfg.geometry.main.Mcw / cfg.geometry.main.Mcd
        assert m.collapse_index == pytest.approx(expected, rel=1e-12)

    def test_Q_water_total_matches_result(self):
        cfg = _make_config(Qw_in_mlhr=10.0)
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.Q_water_total == pytest.approx(result.Q_water_total, rel=1e-12)

    def test_Q_oil_total_matches_result(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.Q_oil_total == pytest.approx(result.Q_oil_total, rel=1e-12)

    def test_Q_spread_nonnegative(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.Q_spread_pct >= 0.0

    def test_dP_spread_nonnegative(self):
        cfg = _make_config()
        result = simulate(cfg)
        m = compute_metrics(cfg, result)
        assert m.dP_spread_pct >= 0.0


class TestComputeMetricsAllActive:
    """With tiny dP_cap_ow (≈ 0), all rungs with dP > 0 are ACTIVE."""

    # Use very small threshold so all rungs with positive dP are ACTIVE.
    _CFG = _make_config(
        Po_in_mbar=200.0,
        Qw_in_mlhr=5.0,
        dP_cap_ow_mbar=0.001,   # 0.1 Pa — negligibly small
        dP_cap_wo_mbar=0.001,
    )

    def test_all_active(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.active_fraction == pytest.approx(1.0)

    def test_reverse_off_zero(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.reverse_fraction == pytest.approx(0.0)
        assert m.off_fraction == pytest.approx(0.0)

    def test_f_pred_mean_positive(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.f_pred_mean > 0.0

    def test_Q_per_rung_avg_positive(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.Q_per_rung_avg > 0.0

    def test_spread_small_for_dominant_rung_resistance(self):
        """
        With rung R >> main-channel R, all rungs see ~equal dP and Q.
        Spread should be very small (< 1 %).
        """
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.Q_spread_pct < 1.0
        assert m.dP_spread_pct < 1.0


class TestComputeMetricsAllOff:
    """With enormous thresholds no rung can be ACTIVE or REVERSE."""

    _CFG = _make_config(
        dP_cap_ow_mbar=1e9,   # ~10^11 Pa — impossible to exceed
        dP_cap_wo_mbar=1e9,
    )

    def test_all_off(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.off_fraction == pytest.approx(1.0)

    def test_active_reverse_zero(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.active_fraction == pytest.approx(0.0)
        assert m.reverse_fraction == pytest.approx(0.0)

    def test_Q_per_rung_avg_zero(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.Q_per_rung_avg == pytest.approx(0.0)

    def test_spread_zero(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.Q_spread_pct == pytest.approx(0.0)
        assert m.dP_spread_pct == pytest.approx(0.0)

    def test_f_pred_mean_zero(self):
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.f_pred_mean == pytest.approx(0.0)

    def test_D_pred_still_positive(self):
        """Droplet diameter is a geometry property, unaffected by regime."""
        result = simulate(self._CFG)
        m = compute_metrics(self._CFG, result)
        assert m.D_pred > 0.0


class TestComputeMetricsWithIterativeSolve:
    """Metrics can also be computed from an iterative_solve result."""

    def test_fractions_sum_to_one(self):
        cfg = _make_config(dP_cap_ow_mbar=50.0, dP_cap_wo_mbar=30.0)
        result = iterative_solve(cfg)
        m = compute_metrics(cfg, result)
        total = m.active_fraction + m.reverse_fraction + m.off_fraction
        assert total == pytest.approx(1.0, abs=1e-10)

    def test_D_pred_consistent(self):
        cfg = _make_config()
        result = iterative_solve(cfg)
        m = compute_metrics(cfg, result)
        assert m.D_pred == pytest.approx(droplet_diameter(cfg), rel=1e-12)
