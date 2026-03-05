#!/usr/bin/env python3
"""Debug steady state model issue."""

from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.hydraulic_models import HydraulicModelRegistry

def debug_steady():
    """Debug steady state model."""

    config = load_config("test_config_small.yaml")
    print(f"Config loaded: {config.geometry.Nmc} rungs")

    # Test conditions
    Po_Pa = mbar_to_pa(400.0)
    Qw_m3s = mlhr_to_m3s(1.5)
    P_out_Pa = mbar_to_pa(0.0)

    try:
        model = HydraulicModelRegistry.get_model("steady")
        print(f"Model created: {type(model).__name__}")

        result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)
        print(f"Result type: {type(result)}")
        print(f"Frequency array: {result.frequency_hz}")
        print(f"Frequency array type: {type(result.frequency_hz)}")

        if result.frequency_hz is not None:
            print(f"Frequency shape: {result.frequency_hz.shape}")
            print(f"Frequency values: {result.frequency_hz}")
        else:
            print("Frequency is None - this is the issue!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_steady()