#!/usr/bin/env python3
"""Quick test script for time-state model functionality."""

import sys
import numpy as np

from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.hydraulic_models import HydraulicModelRegistry

def test_time_state_model():
    """Test time-state model with example configuration."""

    print("Testing Time-State DFU Model...")
    print("=" * 50)

    # Load small test configuration
    try:
        config = load_config("test_config_small.yaml")
        print(f"[OK] Loaded config: {config.geometry.Nmc} rungs")
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return False

    # Test model instantiation
    try:
        model = HydraulicModelRegistry.get_model("time_state")
        print(f"[OK] Created time-state model: {type(model).__name__}")
    except Exception as e:
        print(f"[ERROR] Failed to create model: {e}")
        return False

    # Set up test conditions (from example_single.yaml defaults)
    Po_mbar = 400.0
    Qw_mlhr = 1.5
    P_out_mbar = 0.0

    # Convert units
    Po_Pa = mbar_to_pa(Po_mbar)
    Qw_m3s = mlhr_to_m3s(Qw_mlhr)
    P_out_Pa = mbar_to_pa(P_out_mbar)

    print(f"Test conditions: Po={Po_mbar} mbar, Qw={Qw_mlhr} mL/hr")

    # Reduce simulation time for quick test
    original_sim_time = config.droplet_model.simulation_time_ms
    config.droplet_model.__dict__['simulation_time_ms'] = 500.0  # 0.5 seconds for quick test

    try:
        print("Running time-state simulation...")
        result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

        print(f"[OK] Simulation completed successfully")
        print(f"  Frequencies: {result.frequency_hz}")
        print(f"  Mean frequency: {np.mean(result.frequency_hz):.2f} Hz")
        print(f"  Duty factors: {result.duty_factor[0]:.3f}")

        if result.time_series:
            n_events = sum(len(events) for events in result.time_series['droplet_events'])
            print(f"  Total droplet events: {n_events}")
            print(f"  Phase summary: {result.time_series['final_phase_summary']}")

        # Restore original simulation time
        config.droplet_model.__dict__['simulation_time_ms'] = original_sim_time

        return True

    except Exception as e:
        print(f"[ERROR] Simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_time_state_model()
    sys.exit(0 if success else 1)