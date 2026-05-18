"""
stepgen.models.time_state.time_state_dfu
========================================
Time-dependent DFU hydraulic model with phase state machines.

This model implements physics-based cycle timing where droplet frequency emerges
from time-dependent phase transitions rather than algebraic flow calculations.

Key Features:
- Time integration loop with configurable timestep
- Phase state machines for each DFU (OPEN/PINCH/RESET)
- Droplet volume accumulation and event detection
- Frequency calculation from actual timing of droplet formation events
- Reuses existing _simulate_pa for hydraulic network solving

This addresses the 5-6x frequency overprediction by capturing the stop-go
cycle behavior observed in real DFU operation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from stepgen.models.hydraulic_models import HydraulicModelInterface, HydraulicResult
from stepgen.models.time_state.state_machines import PhaseStateMachine

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class TimeStateDFUModel(HydraulicModelInterface):
    """
    Time-state DFU hydraulic model with phase-dependent conductance.

    This model simulates the time evolution of DFU behavior where each rung
    cycles through OPEN/PINCH/RESET phases. Droplet formation frequency
    emerges naturally from the timing of volume accumulation and phase
    transitions, rather than being computed algebraically.
    """

    def solve(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float
    ) -> HydraulicResult:
        """
        Solve time-dependent hydraulic system with phase state machines.

        Algorithm:
        1. Initialize phase state machines and droplet tracking
        2. Time integration loop:
           a. Set conductances based on current phases
           b. Solve hydraulic network using _simulate_pa
           c. Update droplet volume accumulation
           d. Detect droplet formation events
           e. Update phase timers and transitions
        3. Compute frequencies from droplet event timing
        4. Return final state with time-averaged hydraulics

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
            Hydraulic solution with time-state enhancements
        """
        # Extract time-state parameters
        dt_ms = config.droplet_model.dt_ms
        t_end_ms = config.droplet_model.simulation_time_ms
        g_pinch_frac = config.droplet_model.g_pinch_frac

        # Initialize simulation
        N_rungs = config.geometry.Nmc
        dt_s = dt_ms * 1e-3  # Convert ms → s

        # Initialize phase state machine
        state_machine = PhaseStateMachine(N_rungs, config)

        # Initialize droplet tracking
        droplet_volumes = np.zeros(N_rungs)  # Current volume accumulation [m³]
        droplet_events = [[] for _ in range(N_rungs)]  # Event times per rung
        target_volumes = self._compute_target_volumes(config)

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

        # Time integration loop with adaptive timestep
        t_ms = 0.0
        n_steps = int(t_end_ms / dt_ms)

        # Initialize caching variables for performance optimization
        previous_conductance_factors = None
        cached_solve_result = None
        cached_regimes = None
        cached_rhs_oil = np.zeros(N_rungs)

        # Initialize adaptive timestep variables
        base_dt_ms = dt_ms
        current_dt_ms = dt_ms
        phase_changes_history = []
        steady_state_threshold = 10  # Steps without phase changes to consider steady

        print(f"Time-state simulation: ~{n_steps} steps, dt={dt_ms:.1f}ms, t_end={t_end_ms:.0f}ms")

        # Import progress bar - use time-based progress
        try:
            from tqdm import tqdm
            progress_bar = tqdm(
                total=t_end_ms,
                desc="Time-state simulation",
                unit="ms",
                disable=False  # Always show progress
            )
        except ImportError:
            progress_bar = None

        step = 0
        while t_ms < t_end_ms:
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

            # 3) Update droplet volume accumulation
            for i in range(N_rungs):
                if state_machine.phases[i] == 0:  # OPEN phase
                    # Accumulate volume only for positive flows
                    flow_rate = max(result.Q_rungs[i], 0.0)
                    droplet_volumes[i] += flow_rate * dt_s

                    # 4) Check for droplet formation event
                    if droplet_volumes[i] >= target_volumes[i]:
                        # Record droplet formation event
                        droplet_events[i].append(t_ms)

                        # Reset droplet volume and trigger phase transition
                        droplet_volumes[i] = 0.0
                        state_machine.trigger_droplet_formation(i)

            # 5) Update phase timers and transitions
            previous_phases = state_machine.phases.copy()
            state_machine.update_phase_timers(current_dt_ms)

            # Track phase changes for adaptive timestep and early termination
            phase_changes_this_step = not np.array_equal(previous_phases, state_machine.phases)
            phase_changes_history.append(phase_changes_this_step)

            # Keep only recent history for steady-state detection
            if len(phase_changes_history) > steady_state_threshold:
                phase_changes_history.pop(0)

            # Adaptive timestep based on phase transitions
            if phase_changes_this_step:
                current_dt_ms = base_dt_ms  # Fine timestep during transitions
            else:
                current_dt_ms = base_dt_ms * 2  # Coarser timestep during steady state

            # Early termination check - steady state detection
            if (len(phase_changes_history) >= steady_state_threshold and
                not any(phase_changes_history)):
                print(f"Steady state reached at {t_ms:.1f}ms, terminating early")
                break

            # Store time series data (downsample for memory efficiency)
            if step % 10 == 0:  # Store every 10th step
                time_points.append(t_ms)
                pressure_oil_series.append(result.P_oil.copy())
                pressure_water_series.append(result.P_water.copy())
                flow_rates_series.append(result.Q_rungs.copy())
                phase_states_series.append(state_machine.phases.copy())

            # Update time and progress
            t_ms += current_dt_ms
            step += 1

            if progress_bar is not None:
                progress_bar.update(current_dt_ms)
                progress_bar.set_postfix({
                    'Phase transitions': sum(phase_changes_history),
                    'Current dt': f"{current_dt_ms:.1f}ms"
                })

        # Close progress bar
        if progress_bar is not None:
            progress_bar.close()

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
            # Duty factor = fraction of time spent in OPEN phase (phase == 0)
            time_averaged_duty = np.mean(phase_states_array == 0, axis=0)  # Average over time axis
            duty_factors = time_averaged_duty
        else:
            # Fallback to final phase summary if no time series data
            phase_summary = state_machine.get_phase_summary()
            duty_factors = np.full(N_rungs, phase_summary["frac_open"])

        # Get final phase summary for diagnostic info
        phase_summary = state_machine.get_phase_summary()

        # Package time series data
        time_series = {
            "time_ms": np.array(time_points),
            "P_oil": np.array(pressure_oil_series),
            "P_water": np.array(pressure_water_series),
            "Q_rungs": np.array(flow_rates_series),
            "phases": np.array(phase_states_series),
            "droplet_events": droplet_events,
            "final_phase_summary": phase_summary
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

    def _compute_target_volumes(self, config: "DeviceConfig") -> np.ndarray:
        """
        Compute target droplet volumes for each rung using power-law model.

        Returns
        -------
        np.ndarray
            Target droplet volume per rung [m³]
        """
        # Use same droplet volume calculation as existing model
        w = config.geometry.junction.exit_width
        h = config.geometry.junction.exit_depth
        k = config.droplet_model.k
        a = config.droplet_model.a
        b = config.droplet_model.b

        D = k * (w ** a) * (h ** b)  # Droplet diameter [m]
        V_droplet = (4.0/3.0) * np.pi * (D/2.0)**3  # Droplet volume [m³]

        # For now, uniform volume across all rungs
        # Future enhancement could include position-dependent sizing
        N_rungs = config.geometry.Nmc
        return np.full(N_rungs, V_droplet)

    def _compute_frequencies_from_events(
        self,
        droplet_events: list[list[float]],
        t_end_ms: float
    ) -> np.ndarray:
        """
        Compute per-rung frequencies from droplet formation event timing.

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