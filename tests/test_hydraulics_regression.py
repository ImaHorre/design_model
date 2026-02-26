"""
Regression tests: stepgen.models.hydraulics vs stepgen_seed reference.

Geometry is identical to examples/example_single.yaml but with Mcl reduced
to pitch*10 (Nmc=10) so the test runs in milliseconds while exercising the
same matrix stencil and sign conventions.
"""

import numpy as np
import pytest

# ── Seed reference ────────────────────────────────────────────────────────────
from stepgen_seed.resistance import (
    Geometry as SeedGeometry,
    Fluids as SeedFluids,
    DropletSpec as SeedDropletSpec,
    define_parameters as seed_define_parameters,
)
from stepgen_seed.hydraulics import solve_linear as seed_solve_linear

# ── New package ───────────────────────────────────────────────────────────────
from stepgen.config import (
    DeviceConfig,
    FluidConfig,
    GeometryConfig,
    MainChannelConfig,
    RungConfig,
    JunctionConfig,
    OperatingConfig,
)
from stepgen.models.hydraulics import solve_linear as new_solve_linear


# ── Shared geometry constants (from example_single.yaml) ─────────────────────
_PITCH = 3.0e-6
_NMC   = 10
_MCL   = _PITCH * _NMC   # 30 µm  →  exact integer Nmc

_SEED_GEOM = SeedGeometry(
    Mcl=_MCL,
    Mcd=100e-6,
    Mcw=500e-6,
    mcd=0.3e-6,
    mcw=1.0e-6,
    mcl=200e-6,
    pitch=_PITCH,
    constriction_ratio=1.0,
)
_SEED_FLUIDS  = SeedFluids(mu_water=0.00089, mu_oil=0.03452)
_SEED_DROPLET = SeedDropletSpec(
    emulsion_ratio=0.3, droplet_radius=0.5e-6, production_frequency=50.0
)


def _build_new_config(Mcl: float = _MCL) -> DeviceConfig:
    return DeviceConfig(
        fluids=FluidConfig(
            mu_continuous=0.00089,
            mu_dispersed=0.03452,
            emulsion_ratio=0.3,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=100e-6, Mcw=500e-6, Mcl=Mcl),
            rung=RungConfig(
                mcd=0.3e-6,
                mcw=1.0e-6,
                mcl=200e-6,
                pitch=_PITCH,
                constriction_ratio=1.0,
            ),
            junction=JunctionConfig(exit_width=1e-6, exit_depth=0.3e-6),
        ),
        operating=OperatingConfig(Po_in_mbar=200.0, Qw_in_mlhr=5.0),
    )


class TestLinearSolverRegression:
    """New solver must reproduce the seed to floating-point precision."""

    def test_pressures_and_flows_match_seed(self):
        seed_params = seed_define_parameters(
            geom=_SEED_GEOM,
            fluids=_SEED_FLUIDS,
            droplet=_SEED_DROPLET,
        )
        seed_sol = seed_solve_linear(seed_params, pitch=_PITCH)

        cfg = _build_new_config()
        new_sol = new_solve_linear(cfg, Q_oil=seed_params.Q_O, Q_water=seed_params.Q_W)

        np.testing.assert_allclose(new_sol.P_oil,   seed_sol.P_oil,   rtol=1e-10)
        np.testing.assert_allclose(new_sol.P_water, seed_sol.P_water, rtol=1e-10)
        np.testing.assert_allclose(new_sol.Q_rungs, seed_sol.Q_rungs, rtol=1e-10)

    def test_x_positions_shape_and_values(self):
        seed_params = seed_define_parameters(
            geom=_SEED_GEOM, fluids=_SEED_FLUIDS, droplet=_SEED_DROPLET
        )
        cfg = _build_new_config()
        sol = new_solve_linear(cfg, Q_oil=seed_params.Q_O, Q_water=seed_params.Q_W)

        assert sol.x_positions.shape == (_NMC,)
        assert sol.x_positions[0] == pytest.approx(0.0)
        assert sol.x_positions[-1] == pytest.approx(_PITCH * (_NMC - 1))

    def test_nmc_is_correct(self):
        cfg = _build_new_config()
        assert cfg.geometry.Nmc == _NMC


class TestLinearSolverPhysics:
    """Basic physical-consistency checks on solver output."""

    def _solve(self):
        seed_params = seed_define_parameters(
            geom=_SEED_GEOM, fluids=_SEED_FLUIDS, droplet=_SEED_DROPLET
        )
        cfg = _build_new_config()
        return new_solve_linear(cfg, Q_oil=seed_params.Q_O, Q_water=seed_params.Q_W)

    def test_rung_flows_all_positive(self):
        # In design mode (oil driven into water), all rungs should carry
        # positive (oil→water) flow.
        sol = self._solve()
        assert np.all(sol.Q_rungs > 0), "Expected all rung flows to be positive."

    def test_oil_pressure_is_positive_and_uniform(self):
        # With dominant rung resistance, the oil main pressure is nearly flat.
        # All values should be positive and the coefficient of variation small.
        sol = self._solve()
        assert np.all(sol.P_oil > 0), "Expected positive oil pressures."
        cv = sol.P_oil.std() / sol.P_oil.mean()
        assert cv < 0.01, f"Oil pressure variation unexpectedly large: CV={cv:.4f}"

    def test_solution_arrays_have_correct_length(self):
        sol = self._solve()
        assert len(sol.P_oil)   == _NMC
        assert len(sol.P_water) == _NMC
        assert len(sol.Q_rungs) == _NMC
