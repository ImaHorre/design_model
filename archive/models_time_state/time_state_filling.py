"""
stepgen.models.time_state.time_state_filling
============================================
Time-state hydraulic model with enhanced filling mechanics.

This model extends the base time-state DFU model with detailed filling mechanics:
- Meniscus retreat/advance mechanics with refill volume requirements
- Effective droplet volume including in-channel breakup contributions
- Enhanced cycle timing accounting for both effective volume and refill volume

The enhanced physics should provide more accurate frequency predictions by
capturing microfluidic details that affect droplet formation timing.

Key enhancements over base time-state model:
1. V_target = V_d_eff (not just V_sphere)
2. Additional refill volume requirement after each droplet
3. More realistic cycle timing including meniscus mechanics
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from stepgen.models.hydraulic_models import HydraulicModelInterface, HydraulicResult
from stepgen.models.time_state.state_machines import PhaseStateMachine, DFUPhase
from stepgen.models.time_state.filling_mechanics import FillingMechanics

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class TimeStateFillingModel(HydraulicModelInterface):
    """
    Time-state hydraulic model with enhanced filling mechanics.

    Extends the base time-state model by incorporating:
    - Effective droplet volumes (sphere + in-channel)
    - Meniscus refill requirements
    - Enhanced cycle timing physics
    """

    def solve(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float
    ) -> HydraulicResult:
        """
        Solve time-dependent hydraulic system with filling mechanics enhancement.

        Algorithm extends base time-state model:
        1. Initialize filling mechanics calculator
        2. Use effective droplet volumes for formation thresholds
        3. Account for refill volume requirements in cycle timing
        4. Enhanced frequency calculation from actual cycle mechanics

        Parameters
        ----------
        config : DeviceConfig
            Device configuration
        Po_Pa : float
            Oil inlet pressure [Pa]
        Qw_m3s : float
            Water inlet flow rate [m³/s]
        P_out_Pa : float
            Outlet pressure [Pa]

        Returns
        -------
        HydraulicResult
            Hydraulic solution with filling mechanics enhancements
        """
        # Extract time-state parameters
        dt_ms = config.droplet_model.dt_ms
        t_end_ms = config.droplet_model.simulation_time_ms
        g_pinch_frac = config.droplet_model.g_pinch_frac

        # Initialize simulation
        N_rungs = config.geometry.Nmc
        dt_s = dt_ms * 1e-3  # Convert ms → s

        # Initialize filling mechanics
        filling_mechanics = FillingMechanics(config)

        # Initialize phase state machine
        state_machine = PhaseStateMachine(N_rungs, config)

        # Initialize droplet tracking with enhanced volumes
        droplet_volumes = np.zeros(N_rungs)  # Current volume accumulation [m³]
        refill_volumes = np.zeros(N_rungs)   # Current refill accumulation [m³]
        droplet_events = [[] for _ in range(N_rungs)]  # Event times per rung

        # Use effective target volumes (not just spherical)
        target_volumes = self._compute_effective_target_volumes(filling_mechanics, N_rungs)
        refill_requirements = self._compute_refill_requirements(filling_mechanics, N_rungs)

        # Time series storage for diagnostics
        time_points = []
        pressure_oil_series = []
        pressure_water_series = []
        flow_rates_series = []
        phase_states_series = []

        # Get baseline rung resistances for conductance computation
        from stepgen.models.hydraulics import rung_resistance
        R_base = rung_resistance(config)
        g_base = 1.0 / R_base  # Base conductance per rung

        # Time integration loop
        t_ms = 0.0
        n_steps = int(t_end_ms / dt_ms)

        # Initialize caching variables for performance optimization
        previous_conductance_factors = None
        cached_solve_result = None
        cached_regimes = None
        cached_rhs_oil = np.zeros(N_rungs)

        print(f"Time-state filling simulation: {n_steps} steps, dt={dt_ms:.1f}ms, t_end={t_end_ms:.0f}ms")

        # Import progress bar
        try:
            from tqdm import tqdm
            progress_bar = tqdm(
                range(n_steps),
                desc="Time-state filling simulation",
                unit="step",
                disable=n_steps < 100  # Only show for longer simulations
            )
        except ImportError:
            progress_bar = range(n_steps)

        for step in progress_bar:
            # 1) Set conductances based on current phases
            conductance_factors = state_machine.get_conductance_factors(g_pinch_frac)
            g_rungs = g_base * conductance_factors

            # Track state changes for caching optimization
            current_conductance_factors = tuple(conductance_factors)
            conductances_changed = (step == 0 or
                                  current_conductance_factors != previous_conductance_factors)

            # 2) Solve hydraulic network with dynamic conductances
            from stepgen.models.hydraulics import _simulate_pa
            from stepgen.models.generator import RungRegime, classify_rungs

            if conductances_changed or cached_solve_result is None:
                # Calculate capillary pressure compensation (like steady-state model)
                # First do a quick solve to get pressure differences for classification
                temp_result = _simulate_pa(config, Po_Pa, Qw_m3s, P_out_Pa, g_rungs=g_rungs)
                cached_solve_result = temp_result
                previous_conductance_factors = current_conductance_factors

                dP = temp_result.P_oil - temp_result.P_water

                # Classify rungs based on pressure difference
                regimes = classify_rungs(
                    dP,
                    config.droplet_model.dP_cap_ow_Pa,
                    config.droplet_model.dP_cap_wo_Pa,
                )
                cached_regimes = regimes
            else:
                # Reuse cached results
                temp_result = cached_solve_result
                regimes = cached_regimes

            # Calculate RHS offsets for capillary pressure subtraction
            from stepgen.models.hydraulics import rung_resistance
            g0 = 1.0 / rung_resistance(config)
            rhs_oil = np.zeros(N_rungs, dtype=float)
            rhs_oil[regimes == RungRegime.ACTIVE] = -g0 * config.droplet_model.dP_cap_ow_Pa
            rhs_oil[regimes == RungRegime.REVERSE] = +g0 * config.droplet_model.dP_cap_wo_Pa
            rhs_water = -rhs_oil  # equal and opposite at paired water nodes

            # Check if we need the second solve
            if conductances_changed or not np.array_equal(rhs_oil, cached_rhs_oil):
                # Final solve with capillary pressure compensation
                result = _simulate_pa(
                    config,
                    Po_Pa,
                    Qw_m3s,
                    P_out_Pa,
                    g_rungs=g_rungs,
                    rhs_oil=rhs_oil,
                    rhs_water=rhs_water
                )
                cached_rhs_oil = rhs_oil.copy()
            else:
                # Use first solve result if capillary corrections didn't change
                result = temp_result

            # 3) Update volume accumulation with filling mechanics
            for i in range(N_rungs):
                if state_machine.phases[i] == DFUPhase.OPEN:
                    # Accumulate volume only for positive flows
                    flow_rate = max(result.Q_rungs[i], 0.0)
                    volume_increment = flow_rate * dt_s

                    # First satisfy any refill requirement
                    if refill_volumes[i] < refill_requirements[i]:
                        refill_needed = refill_requirements[i] - refill_volumes[i]
                        refill_contribution = min(volume_increment, refill_needed)
                        refill_volumes[i] += refill_contribution
                        volume_increment -= refill_contribution

                    # Then accumulate toward droplet formation
                    if volume_increment > 0:
                        droplet_volumes[i] += volume_increment

                    # 4) Check for droplet formation event
                    if (refill_volumes[i] >= refill_requirements[i] and
                        droplet_volumes[i] >= target_volumes[i]):

                        # Record droplet formation event
                        droplet_events[i].append(t_ms)

                        # Reset volumes and trigger phase transition
                        droplet_volumes[i] = 0.0
                        refill_volumes[i] = 0.0  # Reset refill requirement for next cycle
                        state_machine.trigger_droplet_formation(i)

            # 5) Update phase timers and transitions
            state_machine.update_phase_timers(dt_ms)

            # Store time series data (downsample for memory efficiency)
            if step % 10 == 0:  # Store every 10th step
                time_points.append(t_ms)
                pressure_oil_series.append(result.P_oil.copy())
                pressure_water_series.append(result.P_water.copy())
                flow_rates_series.append(result.Q_rungs.copy())
                phase_states_series.append(state_machine.phases.copy())

            t_ms += dt_ms

        # Compute frequencies from droplet event timing
        frequencies = self._compute_frequencies_from_events(
            droplet_events, t_end_ms
        )

        # Compute time-averaged hydraulic solution
        if len(pressure_oil_series) > 0:
            P_oil_avg = np.mean(pressure_oil_series, axis=0)
            P_water_avg = np.mean(pressure_water_series, axis=0)
            Q_rungs_avg = np.mean(flow_rates_series, axis=0)
        else:
            # Fallback to last result if no time series data
            P_oil_avg = result.P_oil
            P_water_avg = result.P_water
            Q_rungs_avg = result.Q_rungs

        # Compute time-averaged duty factor from stored phase states
        if len(phase_states_series) > 0:
            phase_states_array = np.array(phase_states_series)  # Shape: (time_steps, N_rungs)
            time_averaged_duty = np.mean(phase_states_array == DFUPhase.OPEN, axis=0)
            duty_factors = time_averaged_duty
        else:
            # Fallback to final phase summary if no time series data
            phase_summary = state_machine.get_phase_summary()
            duty_factors = np.full(N_rungs, phase_summary["frac_open"])

        # Get final phase summary for diagnostic info
        phase_summary = state_machine.get_phase_summary()

        # Get filling mechanics diagnostics
        volume_breakdown = filling_mechanics.get_volume_breakdown()

        # Package time series data with filling mechanics info
        time_series = {
            "time_ms": np.array(time_points),
            "P_oil": np.array(pressure_oil_series),
            "P_water": np.array(pressure_water_series),
            "Q_rungs": np.array(flow_rates_series),
            "phases": np.array(phase_states_series),
            "droplet_events": droplet_events,
            "final_phase_summary": phase_summary,
            "filling_mechanics": {
                "volume_breakdown": volume_breakdown,
                "target_volumes": target_volumes[0],  # First rung as representative
                "refill_requirement": refill_requirements[0]
            }
        }

        return HydraulicResult(
            P_oil=P_oil_avg,
            P_water=P_water_avg,
            Q_rungs=Q_rungs_avg,
            x_positions=result.x_positions,
            frequency_hz=frequencies,
            duty_factor=duty_factors,
            phase_states=state_machine.phases.copy(),
            time_series=time_series
        )

    def _compute_effective_target_volumes(
        self,
        filling_mechanics: FillingMechanics,
        N_rungs: int
    ) -> np.ndarray:
        """
        Compute effective target droplet volumes using filling mechanics.

        Returns
        -------
        np.ndarray
            Effective target droplet volume per rung [m³]
        """
        V_d_eff = filling_mechanics.compute_effective_droplet_volume()
        # For now, uniform across all rungs
        return np.full(N_rungs, V_d_eff)

    def _compute_refill_requirements(
        self,
        filling_mechanics: FillingMechanics,
        N_rungs: int
    ) -> np.ndarray:
        """
        Compute refill volume requirements per rung.

        Returns
        -------
        np.ndarray
            Refill volume requirement per rung [m³]
        """
        V_refill = filling_mechanics.compute_refill_volume()
        # For now, uniform across all rungs
        return np.full(N_rungs, V_refill)

    def _compute_frequencies_from_events(
        self,
        droplet_events: list[list[float]],
        t_end_ms: float
    ) -> np.ndarray:
        """
        Compute per-rung frequencies from droplet formation event timing.

        Same as base time-state model - frequencies from actual event timing.

        Parameters
        ----------
        droplet_events : list of list of float
            Droplet formation times [ms] for each rung
        t_end_ms : float
            Total simulation time [ms]

        Returns
        -------
        np.ndarray
            Per-rung frequencies [Hz]
        """
        N_rungs = len(droplet_events)
        frequencies = np.zeros(N_rungs)

        t_end_s = t_end_ms * 1e-3  # Convert to seconds

        for i in range(N_rungs):
            n_events = len(droplet_events[i])
            if n_events > 0:
                # Frequency = events / time
                frequencies[i] = n_events / t_end_s
            else:
                frequencies[i] = 0.0

        return frequencies