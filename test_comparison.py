#!/usr/bin/env python3
"""Compare steady-state vs time-state vs duty-factor models."""

import numpy as np
from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.hydraulic_models import HydraulicModelRegistry

def compare_models():
    """Compare all hydraulic models."""

    print("Hydraulic Model Comparison")
    print("=" * 50)

    # Load config
    config = load_config("test_config_small.yaml")
    print(f"Configuration: {config.geometry.Nmc} rungs")

    # Test conditions
    Po_Pa = mbar_to_pa(400.0)
    Qw_m3s = mlhr_to_m3s(1.5)
    P_out_Pa = mbar_to_pa(0.0)

    models_to_test = ["steady", "duty_factor", "time_state"]

    results = {}

    for model_name in models_to_test:
        print(f"\nTesting {model_name} model...")

        try:
            # Adjust simulation time for time_state model
            if model_name == "time_state":
                original_sim_time = config.droplet_model.simulation_time_ms
                config.droplet_model.__dict__['simulation_time_ms'] = 1000.0  # 1 second for better statistics

            model = HydraulicModelRegistry.get_model(model_name)
            result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

            # Restore original simulation time
            if model_name == "time_state":
                config.droplet_model.__dict__['simulation_time_ms'] = original_sim_time

            mean_freq = np.mean(result.frequency_hz)
            mean_duty = np.mean(result.duty_factor) if result.duty_factor is not None else 1.0

            results[model_name] = {
                'frequency': mean_freq,
                'duty_factor': mean_duty
            }

            print(f"  Frequency: {mean_freq:.2f} Hz")
            print(f"  Duty factor: {mean_duty:.3f}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results[model_name] = None

    # Summary comparison
    print(f"\n{'='*50}")
    print("SUMMARY COMPARISON:")
    print(f"{'Model':<15} {'Frequency [Hz]':<15} {'Duty Factor':<12} {'Reduction':<10}")
    print("-" * 60)

    steady_freq = results['steady']['frequency'] if results['steady'] else None

    for model_name in models_to_test:
        if results[model_name]:
            freq = results[model_name]['frequency']
            duty = results[model_name]['duty_factor']
            reduction = f"{steady_freq/freq:.1f}x" if steady_freq and freq > 0 else "N/A"

            print(f"{model_name:<15} {freq:<15.2f} {duty:<12.3f} {reduction:<10}")

    # Validation checks
    print(f"\n{'='*50}")
    print("VALIDATION CHECKS:")

    if results['steady'] and results['duty_factor']:
        steady_freq = results['steady']['frequency']
        duty_freq = results['duty_factor']['frequency']
        expected_reduction = 1.0 / config.droplet_model.duty_factor_phi  # phi = 0.18 default
        actual_reduction = steady_freq / duty_freq

        print(f"Duty factor model:")
        print(f"  Expected reduction: {expected_reduction:.1f}x (1/φ where φ={config.droplet_model.duty_factor_phi})")
        print(f"  Actual reduction:   {actual_reduction:.1f}x")
        print(f"  Match: {'PASS' if abs(actual_reduction - expected_reduction) < 0.5 else 'FAIL'}")

    if results['time_state']:
        print(f"Time-state model:")
        print(f"  Duty factor computed: {results['time_state']['duty_factor']:.3f}")
        print(f"  Expected similar to duty_factor model: {'PASS' if results['duty_factor'] and abs(results['time_state']['duty_factor'] - results['duty_factor']['duty_factor']) < 0.1 else 'TBD'}")

if __name__ == "__main__":
    compare_models()