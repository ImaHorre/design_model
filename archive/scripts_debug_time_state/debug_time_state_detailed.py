#!/usr/bin/env python3
"""Detailed debug of time-state model phase transitions."""

from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.time_state.time_state_dfu import TimeStateDFUModel
from stepgen.models.time_state.state_machines import PhaseStateMachine, DFUPhase
from stepgen.models.hydraulics import _simulate_pa, rung_resistance
import numpy as np

def debug_time_state_detailed():
    """Debug time-state model with step-by-step output."""

    config = load_config("test_config_small.yaml")
    print(f"Config: {config.geometry.Nmc} rungs")

    # Test conditions
    Po_Pa = mbar_to_pa(400.0)
    Qw_m3s = mlhr_to_m3s(1.5)
    P_out_Pa = mbar_to_pa(0.0)

    # Get target volumes and flow rates
    model = TimeStateDFUModel()
    target_volumes = model._compute_target_volumes(config)
    print(f"Target droplet volume: {target_volumes[0]:.2e} m³")

    # Test initial hydraulic solution
    result = _simulate_pa(config, Po_Pa, Qw_m3s, P_out_Pa)
    print(f"Initial flow rates: {result.Q_rungs}")
    print(f"Max flow rate: {np.max(result.Q_rungs):.2e} m³/s")

    # Calculate expected accumulation rate
    dt_s = 2e-3  # 2 ms
    max_flow = np.max(result.Q_rungs)
    volume_per_step = max_flow * dt_s
    steps_to_droplet = target_volumes[0] / volume_per_step
    print(f"Volume accumulated per step: {volume_per_step:.2e} m³")
    print(f"Steps to reach droplet volume: {steps_to_droplet:.1f}")

    # Test phase state machine
    state_machine = PhaseStateMachine(config.geometry.Nmc, config)
    print(f"Phase durations: pinch={config.droplet_model.tau_pinch_ms}ms, reset={config.droplet_model.tau_reset_ms}ms")

    # Simulate first few steps manually
    print(f"\nManual simulation of first few steps:")
    droplet_volume = 0.0
    for step in range(20):
        # Get current conductance
        conductance_factors = state_machine.get_conductance_factors(config.droplet_model.g_pinch_frac)
        R_base = rung_resistance(config)
        g_rungs = (1.0 / R_base) * conductance_factors

        # Solve hydraulics
        result = _simulate_pa(config, Po_Pa, Qw_m3s, P_out_Pa, g_rungs=g_rungs)

        # Update droplet volume for rung 0
        if state_machine.phases[0] == DFUPhase.OPEN:
            flow_rate = max(result.Q_rungs[0], 0.0)
            droplet_volume += flow_rate * dt_s

        # Check for droplet formation
        droplet_formed = droplet_volume >= target_volumes[0]

        print(f"Step {step:2d}: Phase={state_machine.phases[0]}, Timer={state_machine.timers[0]:5.1f}ms, "
              f"Volume={droplet_volume:.2e}m³, Flow={result.Q_rungs[0]:.2e}m³/s, Droplet={droplet_formed}")

        if droplet_formed:
            print(f"  -> DROPLET FORMED! Triggering phase transition")
            droplet_volume = 0.0
            state_machine.trigger_droplet_formation(0)

        # Update timers
        state_machine.update_phase_timers(config.droplet_model.dt_ms)

        if step > 15 and not droplet_formed:
            print("  No droplet formed yet after 15 steps - stopping debug")
            break

if __name__ == "__main__":
    debug_time_state_detailed()