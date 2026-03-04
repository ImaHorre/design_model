#!/usr/bin/env python3
"""Test Phase 3 - Time-state with filling mechanics model."""

import numpy as np
from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.hydraulic_models import HydraulicModelRegistry

def test_phase3_model():
    """Test time_state_filling model vs other approaches."""

    print("Phase 3 - Filling Mechanics Enhancement Test")
    print("=" * 60)
    print("Testing time_state_filling model with enhanced physics")
    print()

    # Load w11_old.yaml config for realistic testing
    try:
        config = load_config("examples/w11_old.yaml")
        print(f"Config: examples/w11_old.yaml ({config.geometry.Nmc} rungs)")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Test conditions: Po=300mbar, Qw=1.5mlhr (target experimental ~3 Hz)
    Po_mbar = 300.0
    Qw_mlhr = 1.5
    P_out_mbar = 0.0

    # Convert units
    Po_Pa = mbar_to_pa(Po_mbar)
    Qw_m3s = mlhr_to_m3s(Qw_mlhr)
    P_out_Pa = mbar_to_pa(P_out_mbar)

    print(f"Test conditions:")
    print(f"  Po = {Po_mbar} mbar")
    print(f"  Qw = {Qw_mlhr} mL/hr")
    print(f"  Target experimental: ~3 Hz")
    print()

    # Test all models for comparison
    models = {
        "steady": "Steady-state (baseline)",
        "duty_factor": "Duty factor (empirical phi=0.18)",
        "time_state": "Time-state (pure physics)",
        "time_state_filling": "Time-state + Filling mechanics (Phase 3)"
    }

    results = {}

    for model_name, description in models.items():
        print(f"Testing {model_name}: {description}")

        try:
            # Adjust simulation time for time-state models
            if "time_state" in model_name:
                original_sim_time = getattr(config.droplet_model, 'simulation_time_ms', 5000.0)
                config.droplet_model.__dict__['simulation_time_ms'] = 1500.0  # 1.5 seconds

            model = HydraulicModelRegistry.get_model(model_name)
            result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

            # Restore simulation time
            if "time_state" in model_name:
                config.droplet_model.__dict__['simulation_time_ms'] = original_sim_time

            mean_freq = np.mean(result.frequency_hz)
            mean_duty = np.mean(result.duty_factor) if result.duty_factor is not None else None

            results[model_name] = {
                'frequency': mean_freq,
                'duty_factor': mean_duty,
                'result': result
            }

            print(f"  Frequency: {mean_freq:.2f} Hz")
            if mean_duty is not None:
                print(f"  Duty factor: {mean_duty:.3f}")

            # Show filling mechanics details for enhanced model
            if model_name == "time_state_filling" and result.time_series:
                filling_info = result.time_series.get("filling_mechanics", {})
                if "volume_breakdown" in filling_info:
                    vb = filling_info["volume_breakdown"]
                    print(f"  Filling mechanics:")
                    print(f"    V_sphere: {vb['V_sphere']:.2e} m³")
                    print(f"    V_refill: {vb['V_refill']:.2e} m³")
                    print(f"    V_total:  {vb['V_total']:.2e} m³")
                    refill_fraction = vb['V_refill'] / vb['V_total'] if vb['V_total'] > 0 else 0
                    print(f"    Refill fraction: {refill_fraction:.2%}")
            print()

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            print()

    # Analysis
    print("=" * 60)
    print("PHASE 3 ANALYSIS:")
    print()

    if all(model in results for model in ["steady", "time_state", "time_state_filling"]):
        steady_freq = results['steady']['frequency']
        time_state_freq = results['time_state']['frequency']
        filling_freq = results['time_state_filling']['frequency']

        print(f"Progressive model improvements:")
        print(f"  Steady-state:        {steady_freq:.2f} Hz (baseline)")
        print(f"  Time-state:          {time_state_freq:.2f} Hz ({steady_freq/time_state_freq:.1f}x reduction)")
        print(f"  Time-state+filling:  {filling_freq:.2f} Hz ({steady_freq/filling_freq:.1f}x total reduction)")
        print()

        print(f"Comparison to experimental target (~3 Hz):")
        for name, freq in [("Time-state", time_state_freq), ("Filling mechanics", filling_freq)]:
            error_factor = freq / 3.0
            if 0.8 <= error_factor <= 1.2:
                status = "EXCELLENT"
            elif 0.5 <= error_factor <= 2.0:
                status = "GOOD"
            elif error_factor < 5.0:
                status = "IMPROVED"
            else:
                status = "NEEDS WORK"
            print(f"  {name:18}: {freq:.2f} Hz ({error_factor:.1f}x error) - {status}")
        print()

        # Check if filling mechanics helped
        improvement = time_state_freq / filling_freq if filling_freq > 0 else 1.0
        if improvement > 1.1:
            print(f"✓ Filling mechanics provides additional {improvement:.1f}x improvement!")
        elif improvement > 0.9:
            print(f"~ Filling mechanics shows minimal change ({improvement:.2f}x)")
        else:
            print(f"× Filling mechanics increased frequency ({improvement:.2f}x) - may need parameter tuning")

    return results

if __name__ == "__main__":
    results = test_phase3_model()