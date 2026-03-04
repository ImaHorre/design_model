#!/usr/bin/env python3
"""Debug script for time-state model."""

from stepgen.config import load_config
from stepgen.models.time_state.state_machines import PhaseStateMachine, DFUPhase

def test_state_machine():
    """Test state machine functionality in isolation."""
    print("Testing PhaseStateMachine...")

    # Load config
    config = load_config("examples/example_single.yaml")
    N = config.geometry.Nmc
    print(f"N_rungs: {N}")

    # Create state machine
    sm = PhaseStateMachine(N, config)
    print(f"Initial phases: {sm.phases}")
    print(f"Initial timers: {sm.timers}")

    # Test phase updates
    for i in range(5):
        print(f"\nStep {i}:")
        sm.update_phase_timers()
        print(f"Phases: {sm.phases}")
        print(f"Timers: {sm.timers[:5]}...")  # Show first 5 timers
        print(f"Summary: {sm.get_phase_summary()}")

        # Trigger a droplet event on rung 0
        if i == 2:
            print("Triggering droplet formation on rung 0")
            sm.trigger_droplet_formation(0)

    print("\nState machine test complete!")

def test_droplet_volumes():
    """Test droplet volume calculation."""
    print("\nTesting droplet volume calculation...")

    config = load_config("examples/example_single.yaml")

    # Import the time-state model and test volume calculation
    from stepgen.models.time_state.time_state_dfu import TimeStateDFUModel
    model = TimeStateDFUModel()

    target_volumes = model._compute_target_volumes(config)
    print(f"Target volumes: {target_volumes}")
    print(f"Target volume (first rung): {target_volumes[0]:.2e} m³")

if __name__ == "__main__":
    test_state_machine()
    test_droplet_volumes()