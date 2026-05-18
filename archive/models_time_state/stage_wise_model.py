"""
stepgen.models.time_state.stage_wise_model
==========================================
Stage-wise droplet formation model implementing three-stage physics.

This model addresses the 5-6x frequency overprediction of single-flow models by
implementing distinct physical stages with different governing equations:

- Stage 1: Confined displacement (82.5% cycle time) - Enhanced resistance
- Stage 2: Accelerating bulb growth (13.5% cycle time) - Laplace effects
- Stage 3: Instantaneous snap-off (4% cycle time) - Rapid transition

The model preserves the existing network hydraulics infrastructure while
implementing stage-dependent resistance modifications for each rung.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from stepgen.models.hydraulic_models import HydraulicModelInterface, HydraulicResult
from stepgen.models.time_state.stage_physics import StagePhysicsCalculator

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class StageProgressTracker:
    """Tracks volume accumulation and stage transitions for each rung."""

    def __init__(self, n_rungs: int, config: "DeviceConfig"):
        self.n_rungs = n_rungs
        self.config = config

        # Volume accumulation tracking
        self.droplet_volumes = np.zeros(n_rungs)  # Current accumulated volume per rung
        self.stage_states = np.ones(n_rungs, dtype=int)  # Stage number (1, 2, or 3) per rung

        # Stage transition thresholds
        self.V_displacement = self._compute_displacement_volumes()
        self.V_final = self._compute_final_droplet_volumes()

        # Timing diagnostics
        self.stage_durations = np.zeros((n_rungs, 3))  # [rung, stage] timing
        self.stage_start_times = np.zeros((n_rungs, 3))  # When each stage started

    def _compute_displacement_volumes(self) -> np.ndarray:
        """Compute Stage 1 displacement volume for each rung."""
        V_final = self._compute_final_droplet_volumes()
        displacement_fraction = self.config.droplet_model.displacement_volume_fraction
        return displacement_fraction * V_final

    def _compute_final_droplet_volumes(self) -> np.ndarray:
        """Compute final droplet volume using existing power-law model."""
        w = self.config.geometry.junction.exit_width
        h = self.config.geometry.junction.exit_depth
        k = self.config.droplet_model.k
        a = self.config.droplet_model.a
        b = self.config.droplet_model.b

        D = k * (w ** a) * (h ** b)  # Droplet diameter [m]
        V_droplet = (4.0/3.0) * np.pi * (D/2.0)**3  # Droplet volume [m³]

        return np.full(self.n_rungs, V_droplet)

    def get_current_stages(self) -> np.ndarray:
        """Return current stage number for each rung (1, 2, or 3)."""
        return self.stage_states.copy()

    def update_volumes_and_transitions(self, Q_rungs: np.ndarray, dt: float, current_time: float) -> None:
        """Update volume accumulation and check for stage transitions."""
        # Add volume from flow rates
        dV = Q_rungs * dt
        self.droplet_volumes += np.maximum(dV, 0.0)  # Only positive flows add volume

        # Check for stage transitions
        for i in range(self.n_rungs):
            old_stage = self.stage_states[i]

            if self.stage_states[i] == 1 and self.droplet_volumes[i] >= self.V_displacement[i]:
                # Transition from Stage 1 → Stage 2
                self.stage_states[i] = 2
                self.stage_durations[i, 0] = current_time - self.stage_start_times[i, 0]
                self.stage_start_times[i, 1] = current_time

            elif self.stage_states[i] == 2 and self.droplet_volumes[i] >= self.V_final[i]:
                # Transition from Stage 2 → Stage 3 (snap-off)
                self.stage_states[i] = 3
                self.stage_durations[i, 1] = current_time - self.stage_start_times[i, 1]
                self.stage_start_times[i, 2] = current_time

            elif self.stage_states[i] == 3:
                # Complete snap-off and reset to Stage 1
                self.stage_states[i] = 1
                self.stage_durations[i, 2] = current_time - self.stage_start_times[i, 2]

                # Reset for next cycle
                self.droplet_volumes[i] = 0.0
                self.stage_start_times[i, 0] = current_time

    def get_stage_diagnostics(self) -> dict:
        """Return comprehensive stage timing diagnostics."""
        total_cycle_time = np.sum(self.stage_durations, axis=1)

        # Avoid division by zero for incomplete cycles
        safe_totals = np.where(total_cycle_time > 0, total_cycle_time, 1.0)

        stage_fractions = self.stage_durations / safe_totals[:, np.newaxis]

        return {
            "stage_durations_s": self.stage_durations,
            "total_cycle_time_s": total_cycle_time,
            "stage_fractions": stage_fractions,
            "current_stages": self.stage_states,
            "accumulated_volumes_m3": self.droplet_volumes,
            "displacement_volumes_m3": self.V_displacement,
            "final_volumes_m3": self.V_final
        }


class StageWiseModel(HydraulicModelInterface):
    """
    Stage-wise droplet formation model with three distinct physical stages.

    Implements time integration with stage-dependent resistance modifications
    to capture the different transport physics governing each stage of the
    droplet formation cycle.
    """

    def solve(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float
    ) -> HydraulicResult:
        """
        Solve hydraulic network with stage-wise physics.

        Algorithm:
        1. Initialize stage tracking for all rungs
        2. Time integration loop with stage-dependent resistances
        3. Solve network at each timestep using modified conductances
        4. Update stage progression and volume accumulation
        5. Return hydraulic result with stage diagnostics
        """
        from stepgen.models.hydraulics import _simulate_pa

        # Initialize stage tracking
        n_rungs = config.geometry.Nmc
        stage_tracker = StageProgressTracker(n_rungs, config)
        physics_calc = StagePhysicsCalculator(config)

        # Time integration parameters
        dt = config.droplet_model.dt_ms * 1e-3  # Convert ms → s
        t_end = config.droplet_model.simulation_time_ms * 1e-3  # Convert ms → s

        # Storage for time series
        time_points = []
        P_oil_series = []
        P_water_series = []
        Q_rungs_series = []
        stage_series = []

        # Time integration loop
        t = 0.0
        Q_rungs_prev = None  # For capillary number calculation

        while t < t_end:
            # Get current stages for all rungs
            current_stages = stage_tracker.get_current_stages()

            # Compute stage-dependent resistances (include flow rate effects)
            resistances = physics_calc.compute_stage_resistances(
                current_stages,
                stage_tracker.droplet_volumes,
                config,
                Q_rungs_prev
            )

            # Convert to conductances for network solver
            conductances = 1.0 / resistances

            # Solve network with stage-enhanced resistances
            result = _simulate_pa(
                config,
                Po_Pa,
                Qw_m3s,
                P_out_Pa,
                g_rungs=conductances
            )

            # Update flow rates for next iteration
            Q_rungs_prev = result.Q_rungs.copy()

            # Store time series data
            time_points.append(t)
            P_oil_series.append(result.P_oil.copy())
            P_water_series.append(result.P_water.copy())
            Q_rungs_series.append(result.Q_rungs.copy())
            stage_series.append(current_stages.copy())

            # Update stage progression
            stage_tracker.update_volumes_and_transitions(result.Q_rungs, dt, t)

            t += dt

        # Compute time-averaged quantities for main result
        Q_rungs_avg = np.mean(Q_rungs_series, axis=0)
        P_oil_avg = np.mean(P_oil_series, axis=0)
        P_water_avg = np.mean(P_water_series, axis=0)

        # Compute frequencies from average flow rates and final droplet volumes
        V_droplet = stage_tracker.V_final[0]  # All rungs have same geometry
        frequencies = Q_rungs_avg / V_droplet
        frequencies = np.maximum(frequencies, 0.0)  # Handle inactive rungs

        # Get stage diagnostics
        stage_diagnostics = stage_tracker.get_stage_diagnostics()

        # Build comprehensive time series data
        time_series = {
            "time_s": np.array(time_points),
            "P_oil_Pa": np.array(P_oil_series),
            "P_water_Pa": np.array(P_water_series),
            "Q_rungs_m3s": np.array(Q_rungs_series),
            "stage_states": np.array(stage_series),
            "stage_diagnostics": stage_diagnostics
        }

        return HydraulicResult(
            P_oil=P_oil_avg,
            P_water=P_water_avg,
            Q_rungs=Q_rungs_avg,
            x_positions=result.x_positions,
            frequency_hz=frequencies,
            phase_states=stage_diagnostics["current_stages"],
            time_series=time_series
        )