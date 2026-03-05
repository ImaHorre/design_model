#!/usr/bin/env python3
"""Debug droplet volume accumulation in time-state model."""

from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.time_state.time_state_dfu import TimeStateDFUModel
from stepgen.models.hydraulics import _simulate_pa
import numpy as np

def debug_volumes():
    """Debug droplet volume calculations."""

    # Load config
    config = load_config("test_config_small.yaml")
    print(f"N_rungs: {config.geometry.Nmc}")

    # Get target volumes
    model = TimeStateDFUModel()
    target_volumes = model._compute_target_volumes(config)
    print(f"Target droplet volume: {target_volumes[0]:.2e} m³")

    # Test hydraulic solution
    Po_Pa = mbar_to_pa(400.0)
    Qw_m3s = mlhr_to_m3s(1.5)
    P_out_Pa = mbar_to_pa(0.0)

    result = _simulate_pa(config, Po_Pa, Qw_m3s, P_out_Pa)
    print(f"Flow rates (first 5): {result.Q_rungs[:5]}")
    print(f"Min flow rate: {np.min(result.Q_rungs):.2e} m³/s")
    print(f"Max flow rate: {np.max(result.Q_rungs):.2e} m³/s")

    # Calculate how long it takes to accumulate target volume
    dt_s = 2e-3  # 2 ms
    max_flow = np.max(result.Q_rungs)
    time_to_droplet = target_volumes[0] / max_flow
    print(f"Time to accumulate droplet at max flow: {time_to_droplet:.2f} s = {time_to_droplet*1000:.1f} ms")

    # Check if this fits in simulation time
    sim_time_s = 0.5  # 500 ms
    print(f"Simulation time: {sim_time_s} s")
    print(f"Expected droplets per rung: {sim_time_s / time_to_droplet:.1f}")

if __name__ == "__main__":
    debug_volumes()