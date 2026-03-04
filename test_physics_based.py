#!/usr/bin/env python3
"""Test pure physics-based time-state model without correction factors."""

import numpy as np
from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.hydraulic_models import HydraulicModelRegistry

def test_physics_based_model(config_file="examples/example_single.yaml"):
    """
    Test time-state model as pure physics simulation without correction factors.

    Target conditions: 1.5 mL/hr water flow, 300 mbar Po
    Expected experimental frequency: ~2-3 Hz
    """

    print("Physics-Based Time-State Model Test")
    print("=" * 50)
    print("Testing pure physics simulation (NO correction factors)")
    print()

    # Load config
    try:
        config = load_config(config_file)
        print(f"Config: {config_file}")
        print(f"Rungs: {config.geometry.Nmc}")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Test conditions as specified
    Po_mbar = 300.0  # As requested
    Qw_mlhr = 1.5    # As requested
    P_out_mbar = 0.0

    # Convert units
    Po_Pa = mbar_to_pa(Po_mbar)
    Qw_m3s = mlhr_to_m3s(Qw_mlhr)
    P_out_Pa = mbar_to_pa(P_out_mbar)

    print(f"Operating conditions:")
    print(f"  Po = {Po_mbar} mbar")
    print(f"  Qw = {Qw_mlhr} mL/hr")
    print(f"  Expected experimental frequency: 2-3 Hz")
    print()

    # Test each model type
    models = {
        "steady": "Steady-state (baseline)",
        "duty_factor": "Duty factor (empirical correction phi=0.18)",
        "time_state": "Time-state (pure physics, NO corrections)"
    }

    results = {}

    for model_name, description in models.items():
        print(f"Testing {model_name}: {description}")

        try:
            # Modify simulation time for time_state (if too many rungs)
            if model_name == "time_state" and config.geometry.Nmc > 100:
                print(f"  Large device ({config.geometry.Nmc} rungs), using shorter simulation")
                original_sim_time = getattr(config.droplet_model, 'simulation_time_ms', 5000.0)
                config.droplet_model.__dict__['simulation_time_ms'] = 1000.0  # 1 second

            model = HydraulicModelRegistry.get_model(model_name)
            result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

            # Restore simulation time
            if model_name == "time_state" and config.geometry.Nmc > 100:
                config.droplet_model.__dict__['simulation_time_ms'] = original_sim_time

            mean_freq = np.mean(result.frequency_hz)
            duty_factor = np.mean(result.duty_factor) if result.duty_factor is not None else None

            results[model_name] = {
                'frequency': mean_freq,
                'duty_factor': duty_factor
            }

            print(f"  Frequency: {mean_freq:.2f} Hz")
            if duty_factor is not None:
                if model_name == "time_state":
                    print(f"  Time in OPEN phase: {duty_factor:.3f} (diagnostic only)")
                else:
                    print(f"  Duty factor: {duty_factor:.3f}")
            print()

        except Exception as e:
            print(f"  ERROR: {e}")
            print()

    # Analysis
    print("=" * 50)
    print("ANALYSIS:")
    print()

    if 'steady' in results and 'time_state' in results:
        steady_freq = results['steady']['frequency']
        time_state_freq = results['time_state']['frequency']
        reduction = steady_freq / time_state_freq

        print(f"Frequency reduction from physics-based model:")
        print(f"  Steady-state:  {steady_freq:.2f} Hz")
        print(f"  Time-state:    {time_state_freq:.2f} Hz")
        print(f"  Reduction:     {reduction:.1f}x")
        print()

        print(f"Comparison to experimental target (2-3 Hz):")
        if 2.0 <= time_state_freq <= 3.0:
            print(f"  ✓ Time-state frequency ({time_state_freq:.2f} Hz) is within experimental range!")
        else:
            error_factor = time_state_freq / 2.5  # Compare to midpoint
            print(f"  × Time-state frequency ({time_state_freq:.2f} Hz) differs from experimental")
            print(f"    Error factor: {error_factor:.1f}x")
        print()

    if 'duty_factor' in results and 'time_state' in results:
        duty_freq = results['duty_factor']['frequency']
        time_state_freq = results['time_state']['frequency']

        print(f"Physics vs empirical correction:")
        print(f"  Duty factor model: {duty_freq:.2f} Hz (with empirical phi=0.18)")
        print(f"  Time-state model:  {time_state_freq:.2f} Hz (pure physics)")
        print(f"  Difference: {abs(duty_freq - time_state_freq):.2f} Hz")

    return results

if __name__ == "__main__":
    # Test with available config - can be changed to w11.yaml when available
    results = test_physics_based_model("examples/example_single.yaml")