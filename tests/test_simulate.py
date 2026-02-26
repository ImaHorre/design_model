"""
Tests for the mixed-BC simulate() function in stepgen.models.hydraulics.
"""

import numpy as np
import pytest

from stepgen.config import (
    DeviceConfig, FluidConfig, GeometryConfig, MainChannelConfig,
    RungConfig, JunctionConfig, OperatingConfig,
)
from stepgen.models.hydraulics import simulate
from stepgen.models.resistance import main_channel_resistance_per_segment, rung_resistance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PITCH = 3.0e-6


def _make_config(Nmc: int, Po_in_mbar: float = 200.0, Qw_in_mlhr: float = 5.0) -> DeviceConfig:
    """Config with given Nmc; geometry matches example_single.yaml."""
    return DeviceConfig(
        fluids=FluidConfig(mu_continuous=0.00089, mu_dispersed=0.03452, emulsion_ratio=0.3),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=100e-6, Mcw=500e-6, Mcl=_PITCH * Nmc),
            rung=RungConfig(mcd=0.3e-6, mcw=1e-6, mcl=200e-6, pitch=_PITCH,
                            constriction_ratio=1.0),
            junction=JunctionConfig(exit_width=1e-6, exit_depth=0.3e-6),
        ),
        operating=OperatingConfig(Po_in_mbar=Po_in_mbar, Qw_in_mlhr=Qw_in_mlhr,
                                  P_out_mbar=0.0),
    )


# ---------------------------------------------------------------------------
# Boundary-condition enforcement
# ---------------------------------------------------------------------------

class TestBoundaryConditions:
    def test_oil_inlet_pressure_is_pinned(self):
        cfg = _make_config(10)
        sol = simulate(cfg)
        assert sol.P_oil[0] == pytest.approx(cfg.operating.Po_in_Pa, rel=1e-10)

    def test_oil_outlet_not_pinned_to_zero(self):
        """Oil outlet is a dead-end manifold: pressure is free (NOT pinned to P_out)."""
        cfg = _make_config(10)
        sol = simulate(cfg)
        # P_oil[-1] must be strictly above P_out (oil must retain pressure to push
        # through the last rung into the water channel)
        assert sol.P_oil[-1] > sol.P_out_Pa

    def test_water_outlet_pressure_is_pinned(self):
        cfg = _make_config(10)
        sol = simulate(cfg)
        assert sol.P_water[-1] == pytest.approx(cfg.operating.P_out_Pa, rel=1e-10, abs=1e-6)

    def test_last_rung_carries_flow(self):
        """With dead-end oil manifold all rungs, including the last, carry oil→water flow."""
        cfg = _make_config(10, Po_in_mbar=500.0, Qw_in_mlhr=0.1)
        sol = simulate(cfg)
        assert sol.Q_rungs[-1] > 0.0

    def test_override_po_qw(self):
        cfg = _make_config(10, Po_in_mbar=100.0, Qw_in_mlhr=2.0)
        sol = simulate(cfg, Po_in_mbar=300.0, Qw_in_mlhr=10.0)
        assert sol.Po_in_Pa == pytest.approx(300.0 * 100.0, rel=1e-10)
        assert sol.Qw_in_m3s == pytest.approx(10.0 * (1e-6 / 3600.0), rel=1e-10)

    def test_default_from_config_operating(self):
        cfg = _make_config(10, Po_in_mbar=150.0, Qw_in_mlhr=3.0)
        sol = simulate(cfg)
        assert sol.Po_in_Pa == pytest.approx(150.0 * 100.0)


# ---------------------------------------------------------------------------
# Analytical verification for N=2
# ---------------------------------------------------------------------------

class TestN2Analytical:
    """
    For N=2 (one interior oil node replaced by dead-end KCL, no water interior nodes):

    Oil node N-1=1 (dead-end KCL):
        (P_oil[0] - P_oil[1]) / R_OMc = (P_oil[1] - P_water[1]) / R_Omc
        With P_water[1] = P_out:
        P_oil[1] = P_oil[0] * R_Omc / (R_Omc + R_OMc)

    Water node 0 (KCL with Q_water injection):
        g0*(P_oil[0] - P_water[0]) + (P_water[1] - P_water[0])/R_WMc + Qw = 0
        P_water[0] = (Po_in/R_Omc + P_out/R_WMc + Qw) / (1/R_Omc + 1/R_WMc)

    Q_rungs[0] = (P_oil[0] - P_water[0]) / R_Omc
    Q_rungs[1] = (P_oil[1] - P_water[1]) / R_Omc = P_oil[1] / R_Omc (P_out=0)
    """

    def _resistances(self, cfg: DeviceConfig):
        R_OMc, R_WMc = main_channel_resistance_per_segment(cfg)
        R_Omc = rung_resistance(cfg)
        return R_OMc, R_WMc, R_Omc

    def _analytical_P_oil_1(self, cfg: DeviceConfig) -> float:
        R_OMc, _, R_Omc = self._resistances(cfg)
        Po_in = cfg.operating.Po_in_Pa
        P_out = cfg.operating.P_out_Pa
        # Dead-end KCL at node 1:
        # (Po_in - P_oil1)/R_OMc = (P_oil1 - P_out)/R_Omc
        return (Po_in / R_OMc + P_out / R_Omc) / (1.0 / R_OMc + 1.0 / R_Omc)

    def _analytical_P_water_0(self, cfg: DeviceConfig) -> float:
        R_OMc, R_WMc, R_Omc = self._resistances(cfg)
        Po_in = cfg.operating.Po_in_Pa
        P_out = cfg.operating.P_out_Pa
        Qw    = cfg.operating.Qw_in_m3s
        # Water node 0 KCL is identical to old system (unaffected by oil-outlet BC change)
        return (Po_in / R_Omc + P_out / R_WMc + Qw) / (1.0 / R_Omc + 1.0 / R_WMc)

    def test_p_oil_1_matches_analytical(self):
        cfg = _make_config(2)
        sol = simulate(cfg)
        expected = self._analytical_P_oil_1(cfg)
        assert sol.P_oil[1] == pytest.approx(expected, rel=1e-8)

    def test_p_water_0_matches_analytical(self):
        cfg = _make_config(2)
        sol = simulate(cfg)
        expected = self._analytical_P_water_0(cfg)
        assert sol.P_water[0] == pytest.approx(expected, rel=1e-8)

    def test_q_rungs_1_positive(self):
        """Last rung carries oil→water flow (dead-end: P_oil[1] > P_water[1]=P_out)."""
        cfg = _make_config(2)
        sol = simulate(cfg)
        assert sol.Q_rungs[1] > 0.0

    def test_q_rungs_0_from_pressure_diff(self):
        cfg = _make_config(2)
        sol = simulate(cfg)
        R_Omc = rung_resistance(cfg)
        expected = (sol.P_oil[0] - sol.P_water[0]) / R_Omc
        assert sol.Q_rungs[0] == pytest.approx(expected, rel=1e-10)

    def test_conservation_n2(self):
        """Q_oil_total = Q_rungs[0] + Q_rungs[1] for N=2."""
        cfg = _make_config(2)
        sol = simulate(cfg)
        assert sol.Q_oil_total == pytest.approx(float(np.sum(sol.Q_rungs)), rel=1e-6)


# ---------------------------------------------------------------------------
# Physical properties
# ---------------------------------------------------------------------------

class TestPhysicalProperties:
    def test_rung_flows_positive_high_pressure(self):
        """With large Po_in all rungs (including the last) carry positive flow."""
        cfg = _make_config(20, Po_in_mbar=1000.0, Qw_in_mlhr=0.1)
        sol = simulate(cfg)
        assert np.all(sol.Q_rungs > 0)

    def test_oil_pressure_decreasing(self):
        """Interior oil pressure must decrease monotonically from inlet to outlet."""
        cfg = _make_config(20, Po_in_mbar=500.0, Qw_in_mlhr=1.0)
        sol = simulate(cfg)
        assert np.all(np.diff(sol.P_oil) <= 0)

    def test_oil_pressure_above_outlet(self):
        """Every oil node should be at or above P_out."""
        cfg = _make_config(10)
        sol = simulate(cfg)
        assert np.all(sol.P_oil >= sol.P_out_Pa - 1e-6)

    def test_arrays_correct_shape(self):
        Nmc = 15
        cfg = _make_config(Nmc)
        sol = simulate(cfg)
        assert sol.P_oil.shape   == (Nmc,)
        assert sol.P_water.shape == (Nmc,)
        assert sol.Q_rungs.shape == (Nmc,)
        assert sol.x_positions.shape == (Nmc,)

    def test_x_positions_start_at_zero(self):
        cfg = _make_config(10)
        sol = simulate(cfg)
        assert sol.x_positions[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Conservation (AC9)
# ---------------------------------------------------------------------------

class TestConservation:
    def test_oil_conservation_ac9(self):
        """
        AC9: Q_oil_in = Σ Q_rungs within numerical tolerance.

        With the dead-end manifold all oil must exit through the rungs; there
        is no axial oil outlet.  The computed Q_oil_total (from KCL at inlet)
        must equal the sum of all rung flows.
        """
        cfg = _make_config(20)
        sol = simulate(cfg)
        assert sol.Q_oil_total == pytest.approx(float(np.sum(sol.Q_rungs)), rel=1e-6)

    def test_oil_conservation_various_n(self):
        """Conservation holds for several device sizes."""
        for N in (2, 5, 10, 50):
            cfg = _make_config(N)
            sol = simulate(cfg)
            assert sol.Q_oil_total == pytest.approx(
                float(np.sum(sol.Q_rungs)), rel=1e-6
            ), f"Conservation failed for N={N}"

    def test_q_water_total_equals_prescribed(self):
        """Q_water_total must equal the prescribed water inlet flow."""
        cfg = _make_config(10)
        sol = simulate(cfg)
        assert sol.Q_water_total == pytest.approx(cfg.operating.Qw_in_m3s, rel=1e-10)
