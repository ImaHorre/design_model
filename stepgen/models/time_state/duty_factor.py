"""
stepgen.models.time_state.duty_factor
=====================================
Duty factor hydraulic model for empirical cycle gating effects.

This model applies an empirical duty factor φ ≈ 0.17-0.20 to scale the effective
flow through droplet forming units (DFUs). This captures the observation that
real DFUs operate in stop-go cycles with significant blocked/high-impedance time,
rather than continuous steady flow assumed by the base model.

The model modifies effective flow rates:
- Global mode: Q_eff = φ * Q_steady (uniform scaling)
- Per-rung mode: Q_eff[i] = φ[i] * Q_steady[i] (position-dependent scaling)

This addresses the 5-6x frequency overprediction observed in experimental validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from stepgen.models.hydraulic_models import HydraulicModelInterface, HydraulicResult

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class DutyFactorModel(HydraulicModelInterface):
    """
    Duty factor model applying empirical φ scaling to effective flow rates.

    This model first computes the steady-state solution, then applies duty factor
    scaling to the rung flow rates to capture cycle gating effects.
    """

    def solve(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float
    ) -> HydraulicResult:
        """
        Solve with duty factor scaling applied to rung flows.

        Algorithm:
        1. Compute steady-state solution using existing iterative_solve
        2. Apply duty factor scaling to Q_rungs: Q_eff = φ * Q_steady
        3. Recompute frequency using scaled flows: f = Q_eff / V_droplet

        The pressure profiles remain unchanged since we're applying an effective
        scaling to capture temporal gating effects rather than changing the
        instantaneous flow physics.
        """
        # Get duty factor parameters
        phi = config.droplet_model.duty_factor_phi
        mode = config.droplet_model.duty_factor_mode

        # First solve steady-state (unchanged)
        from stepgen.models.generator import iterative_solve
        from stepgen.config import mlhr_to_m3s

        # Convert units for existing interface
        Po_mbar = Po_Pa * 1e-2  # Pa → mbar
        Qw_mlhr = Qw_m3s / mlhr_to_m3s(1.0)  # m³/s → mL/hr
        P_out_mbar = P_out_Pa * 1e-2  # Pa → mbar

        # Call existing steady-state solver
        solution = iterative_solve(
            config,
            Po_in_mbar=Po_mbar,
            Qw_in_mlhr=Qw_mlhr,
            P_out_mbar=P_out_mbar
        )

        # Apply duty factor scaling to rung flows
        if mode == "global":
            # Uniform duty factor across all rungs
            duty_factors = np.full_like(solution.Q_rungs, phi)
        elif mode == "per_rung":
            # Position-dependent duty factor (future enhancement)
            # For now, use global value - can be enhanced in future phases
            duty_factors = np.full_like(solution.Q_rungs, phi)
        else:
            raise ValueError(f"Unknown duty_factor_mode: {mode}")

        # Scale effective flow rates
        Q_rungs_effective = solution.Q_rungs * duty_factors

        # Compute per-rung frequencies with duty factor scaling
        frequencies = self._compute_frequencies(config, Q_rungs_effective)

        # Create enhanced result
        return HydraulicResult(
            P_oil=solution.P_oil,
            P_water=solution.P_water,
            Q_rungs=Q_rungs_effective,  # Use scaled flows
            x_positions=solution.x_positions,
            frequency_hz=frequencies,
            duty_factor=duty_factors
        )

    def _compute_frequencies(
        self,
        config: "DeviceConfig",
        Q_rungs: np.ndarray
    ) -> np.ndarray:
        """
        Compute per-rung droplet frequencies from (effective) flow rates.

        Uses the same droplet volume calculation as the existing model:
        V_droplet = (4/3) * π * (D/2)³
        where D is computed from the power-law model.

        Then f = Q_rung / V_droplet for each rung.
        """
        # Compute droplet diameter using existing power-law model
        w = config.geometry.junction.exit_width
        h = config.geometry.junction.exit_depth
        k = config.droplet_model.k
        a = config.droplet_model.a
        b = config.droplet_model.b

        D = k * (w ** a) * (h ** b)  # Droplet diameter [m]
        V_droplet = (4.0/3.0) * np.pi * (D/2.0)**3  # Droplet volume [m³]

        # Frequency = flow rate / droplet volume
        frequencies = Q_rungs / V_droplet

        # Handle negative or zero flows (inactive rungs)
        frequencies = np.maximum(frequencies, 0.0)

        return frequencies