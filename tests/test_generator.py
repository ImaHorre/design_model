"""
Tests for stepgen.models.generator:
  - classify_rungs unit tests
  - iterative_solve basics
  - reverse-band synthetic scenario
"""

import numpy as np
import pytest

from stepgen.config import (
    DeviceConfig, FluidConfig, GeometryConfig, MainChannelConfig,
    RungConfig, JunctionConfig, OperatingConfig, DropletModelConfig,
)
from stepgen.models.generator import RungRegime, classify_rungs, iterative_solve
from stepgen.models.hydraulics import SimResult, simulate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PITCH = 3.0e-6


def _make_config(
    Nmc: int = 10,
    Po_in_mbar: float = 200.0,
    Qw_in_mlhr: float = 5.0,
    dP_cap_ow_mbar: float = 50.0,
    dP_cap_wo_mbar: float = 30.0,
    Mcd: float = 100e-6,
) -> DeviceConfig:
    return DeviceConfig(
        fluids=FluidConfig(mu_continuous=0.00089, mu_dispersed=0.03452, emulsion_ratio=0.3),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=Mcd, Mcw=500e-6, Mcl=_PITCH * Nmc),
            rung=RungConfig(mcd=0.3e-6, mcw=1e-6, mcl=200e-6, pitch=_PITCH,
                            constriction_ratio=1.0),
            junction=JunctionConfig(exit_width=1e-6, exit_depth=0.3e-6),
        ),
        operating=OperatingConfig(Po_in_mbar=Po_in_mbar, Qw_in_mlhr=Qw_in_mlhr,
                                  P_out_mbar=0.0),
        droplet_model=DropletModelConfig(
            dP_cap_ow_mbar=dP_cap_ow_mbar,
            dP_cap_wo_mbar=dP_cap_wo_mbar,
        ),
    )


# ---------------------------------------------------------------------------
# classify_rungs unit tests
# ---------------------------------------------------------------------------

class TestClassifyRungs:
    def test_all_active(self):
        dP = np.array([200.0, 300.0, 500.0])
        r = classify_rungs(dP, dP_cap_ow_Pa=100.0, dP_cap_wo_Pa=50.0)
        assert all(v == RungRegime.ACTIVE for v in r)

    def test_all_reverse(self):
        dP = np.array([-200.0, -300.0, -100.0])
        r = classify_rungs(dP, dP_cap_ow_Pa=50.0, dP_cap_wo_Pa=60.0)
        assert all(v == RungRegime.REVERSE for v in r)

    def test_all_off(self):
        dP = np.array([10.0, -10.0, 0.0, 20.0])
        r = classify_rungs(dP, dP_cap_ow_Pa=50.0, dP_cap_wo_Pa=50.0)
        assert all(v == RungRegime.OFF for v in r)

    def test_mixed(self):
        dP = np.array([-200.0, 5.0, 200.0])   # REVERSE, OFF, ACTIVE
        r = classify_rungs(dP, dP_cap_ow_Pa=100.0, dP_cap_wo_Pa=100.0)
        assert r[0] == RungRegime.REVERSE
        assert r[1] == RungRegime.OFF
        assert r[2] == RungRegime.ACTIVE

    def test_exact_threshold_not_active(self):
        # Strict inequality: dP == dP_cap_ow is NOT ACTIVE
        dP = np.array([100.0])
        r = classify_rungs(dP, dP_cap_ow_Pa=100.0, dP_cap_wo_Pa=50.0)
        assert r[0] == RungRegime.OFF

    def test_exact_negative_threshold_not_reverse(self):
        # Strict inequality: dP == -dP_cap_wo is NOT REVERSE
        dP = np.array([-50.0])
        r = classify_rungs(dP, dP_cap_ow_Pa=100.0, dP_cap_wo_Pa=50.0)
        assert r[0] == RungRegime.OFF

    def test_single_element(self):
        r = classify_rungs(np.array([999.0]), 500.0, 500.0)
        assert r[0] == RungRegime.ACTIVE

    def test_output_shape(self):
        dP = np.zeros(20)
        r = classify_rungs(dP, 50.0, 50.0)
        assert r.shape == (20,)


# ---------------------------------------------------------------------------
# iterative_solve basics
# ---------------------------------------------------------------------------

class TestIterativeSolveBasics:
    def test_returns_simresult(self):
        cfg = _make_config()
        result = iterative_solve(cfg)
        assert isinstance(result, SimResult)

    def test_oil_inlet_pressure_pinned(self):
        cfg = _make_config(Po_in_mbar=300.0)
        result = iterative_solve(cfg)
        assert result.P_oil[0] == pytest.approx(300.0 * 100.0, rel=1e-8)

    def test_outlet_pressures(self):
        cfg = _make_config()
        result = iterative_solve(cfg)
        # Water outlet is Dirichlet at P_out = 0.
        assert result.P_water[-1] == pytest.approx(0.0, abs=1e-6)
        # Oil outlet is a dead-end manifold (Neumann): NOT pinned to P_out.
        # It should be above P_out (oil retains pressure to drive the last rung).
        assert result.P_oil[-1] > result.P_out_Pa

    def test_shapes(self):
        Nmc = 12
        cfg = _make_config(Nmc=Nmc)
        result = iterative_solve(cfg)
        assert result.P_oil.shape   == (Nmc,)
        assert result.P_water.shape == (Nmc,)
        assert result.Q_rungs.shape == (Nmc,)

    def test_max_iter_one_returns_without_crash(self):
        cfg = _make_config()
        result = iterative_solve(cfg, max_iter=1)
        assert isinstance(result, SimResult)

    def test_invalid_max_iter_raises(self):
        cfg = _make_config()
        with pytest.raises(ValueError):
            iterative_solve(cfg, max_iter=0)

    def test_defaults_from_config(self):
        cfg = _make_config(Po_in_mbar=150.0)
        result = iterative_solve(cfg)
        assert result.Po_in_Pa == pytest.approx(15000.0)

    def test_override_po_qw(self):
        cfg = _make_config(Po_in_mbar=100.0)
        result = iterative_solve(cfg, Po_in_mbar=400.0, Qw_in_mlhr=8.0)
        assert result.Po_in_Pa == pytest.approx(40000.0)

    def test_all_open_matches_simulate(self):
        """With thresholds very high (no OFF/REVERSE), iterative_solve ≈ simulate."""
        cfg = _make_config(dP_cap_ow_mbar=1e9, dP_cap_wo_mbar=1e9)
        r_iter = iterative_solve(cfg)
        r_sim  = simulate(cfg)
        np.testing.assert_allclose(r_iter.P_oil,   r_sim.P_oil,   rtol=1e-6)
        np.testing.assert_allclose(r_iter.P_water, r_sim.P_water, rtol=1e-6)

    def test_convergence_self_consistency(self):
        """
        After iterative_solve converges, running one more classify step
        on the returned pressures should give the same regimes that produced
        the returned solution.
        """
        cfg = _make_config(dP_cap_ow_mbar=50.0, dP_cap_wo_mbar=30.0)
        result = iterative_solve(cfg, max_iter=50)
        dP = result.P_oil - result.P_water
        final_regimes = classify_rungs(
            dP,
            cfg.droplet_model.dP_cap_ow_Pa,
            cfg.droplet_model.dP_cap_wo_Pa,
        )
        # Re-run with those exact regimes to get pressures; they should be
        # identical to the converged result (self-consistent fixed point).
        from stepgen.models.generator import _EPSILON_OFF
        from stepgen.models.hydraulics import _simulate_pa
        from stepgen.models.resistance import rung_resistance
        N  = cfg.geometry.Nmc
        g0 = 1.0 / rung_resistance(cfg)
        g_rungs = np.where(final_regimes == RungRegime.OFF, g0 * _EPSILON_OFF, g0).astype(float)
        rhs_oil = np.zeros(N, dtype=float)
        rhs_oil[final_regimes == RungRegime.ACTIVE]  = -g0 * cfg.droplet_model.dP_cap_ow_Pa
        rhs_oil[final_regimes == RungRegime.REVERSE] = +g0 * cfg.droplet_model.dP_cap_wo_Pa
        rhs_water = -rhs_oil
        from stepgen.config import mbar_to_pa, mlhr_to_m3s
        rerun = _simulate_pa(
            cfg,
            mbar_to_pa(cfg.operating.Po_in_mbar),
            mlhr_to_m3s(cfg.operating.Qw_in_mlhr),
            mbar_to_pa(cfg.operating.P_out_mbar),
            g_rungs=g_rungs, rhs_oil=rhs_oil, rhs_water=rhs_water,
        )
        np.testing.assert_allclose(rerun.P_oil,   result.P_oil,   rtol=1e-8)
        np.testing.assert_allclose(rerun.P_water, result.P_water, rtol=1e-8)


# ---------------------------------------------------------------------------
# Reverse-band scenario
# ---------------------------------------------------------------------------

class TestReverseBand:
    """
    With high water inlet flow relative to oil pressure the water pressure
    exceeds the oil pressure at inlet-side rungs, producing a reverse band.

    Geometry: Mcd = 20 µm (narrow main channel, high R_WMc ≈ 8.2e9 Pa·s/m³
    per segment).  This is necessary to create sufficient water back-pressure:
      P_water[0] ≈ (N-1) × Qw × R_WMc ≈ 9 × 5.56e-7 × 8.2e9 ≈ 41 000 Pa
    which comfortably exceeds Po_in = 200 mbar = 20 000 Pa.

    With dP_cap_ow = 500 mbar >> Po_in = 200 mbar no rung can be ACTIVE.
    Rungs near the water inlet where ΔP = P_oil − P_water < −dP_cap_wo are
    classified REVERSE, producing a detectable reverse band.
    """

    _CFG = _make_config(
        Nmc=10,
        Po_in_mbar=200.0,
        Qw_in_mlhr=2000.0,
        dP_cap_ow_mbar=500.0,   # very high: no ACTIVE expected
        dP_cap_wo_mbar=100.0,   # 10 000 Pa
        Mcd=20e-6,              # 20 µm deep → R_WMc high enough for reverse bands
    )

    def test_simulate_produces_negative_dP_at_inlet(self):
        """The unthresholded solve must show P_water > P_oil at node 0."""
        sol = simulate(self._CFG)
        assert sol.P_water[0] > sol.P_oil[0], (
            f"Expected P_water[0] > P_oil[0]; got {sol.P_water[0]:.1f} vs {sol.P_oil[0]:.1f} Pa"
        )

    def test_reverse_fraction_positive_after_iterative_solve(self):
        result = iterative_solve(self._CFG)
        dP = result.P_oil - result.P_water
        regimes = classify_rungs(
            dP,
            self._CFG.droplet_model.dP_cap_ow_Pa,
            self._CFG.droplet_model.dP_cap_wo_Pa,
        )
        reverse_fraction = np.sum(regimes == RungRegime.REVERSE) / len(regimes)
        assert reverse_fraction > 0, (
            f"Expected reverse_fraction > 0; got {reverse_fraction:.2f}"
        )

    def test_iterative_solve_converges(self):
        """iterative_solve must return within max_iter without raising."""
        result = iterative_solve(self._CFG, max_iter=50)
        assert isinstance(result, SimResult)

    def test_no_active_rungs_with_high_threshold(self):
        """With dP_cap_ow = 500 mbar >> Po_in = 200 mbar, no rung can be ACTIVE."""
        result = iterative_solve(self._CFG)
        dP = result.P_oil - result.P_water
        regimes = classify_rungs(
            dP,
            self._CFG.droplet_model.dP_cap_ow_Pa,
            self._CFG.droplet_model.dP_cap_wo_Pa,
        )
        active_count = np.sum(regimes == RungRegime.ACTIVE)
        assert active_count == 0, f"Expected no ACTIVE rungs; got {active_count}"
