#!/usr/bin/env python3
"""
Phase 3 Parameter Sensitivity Test
==================================
Test key time-state parameters to understand model behavior.
"""

import time
import dataclasses
from stepgen.config import load_config
from stepgen.io.experiments import load_experiments
from stepgen.models.model_comparison import ModelComparator

def test_time_state_with_params(config, Po_Pa, Qw_m3s, dt_ms=5.0, tau_pinch_ms=35, tau_reset_ms=20):
    """Test time-state model with specific parameters."""

    # Modify config with time-state parameters
    new_droplet_model = dataclasses.replace(
        config.droplet_model,
        hydraulic_model='time_state',
        dt_ms=dt_ms,
        tau_pinch_ms=tau_pinch_ms,
        tau_reset_ms=tau_reset_ms
    )

    config_copy = dataclasses.replace(config, droplet_model=new_droplet_model)
    comparator = ModelComparator()

    try:
        start_time = time.time()
        result = comparator.compare_all_models(
            config_copy, Po_Pa, Qw_m3s, 0.0,
            models=['time_state']
        )
        execution_time = time.time() - start_time

        frequency = result.model_results[0].frequency_hz
        if hasattr(frequency, '__len__'):
            frequency = frequency.mean()

        return {
            'frequency_hz': frequency,
            'execution_time_s': execution_time,
            'success': True,
            'error': None
        }

    except Exception as e:
        return {
            'frequency_hz': 0.0,
            'execution_time_s': float('inf'),
            'success': False,
            'error': str(e)
        }

def main():
    print("Phase 3 Parameter Sensitivity Test")
    print("=" * 50)

    # Load data
    config = load_config("configs/w11.yaml")
    experiments_df = load_experiments("data/w11_4_7.csv")

    # Test condition
    Po, Qw = 300.0, 1.5
    exp_freq = 1.903

    from stepgen.config import mlhr_to_m3s, mbar_to_pa
    Po_Pa = mbar_to_pa(Po)
    Qw_m3s = mlhr_to_m3s(Qw)

    print(f"Test condition: Po={Po}mbar, Qw={Qw}mL/hr")
    print(f"Target frequency: {exp_freq:.3f} Hz")
    print()

    # Test dt_ms sensitivity
    print("dt_ms Parameter Sensitivity:")
    print("dt_ms | Frequency | RMSE  | Time  | Status")
    print("------|-----------|-------|-------|-------")

    dt_values = [1.0, 2.0, 5.0]
    for dt in dt_values:
        result = test_time_state_with_params(config, Po_Pa, Qw_m3s, dt_ms=dt, tau_pinch_ms=35)
        if result['success']:
            rmse = abs(result['frequency_hz'] - exp_freq)
            print(f"{dt:5.1f} | {result['frequency_hz']:9.3f} | {rmse:5.3f} | {result['execution_time_s']:5.1f} | OK")
        else:
            print(f"{dt:5.1f} | {'FAILED':>9} | {'---':>5} | {'---':>5} | ERROR")

    print()

    # Test tau_pinch_ms sensitivity
    print("tau_pinch_ms Parameter Sensitivity:")
    print("tau_ms | Frequency | RMSE  | Time  | Status")
    print("-------|-----------|-------|-------|-------")

    tau_values = [10, 20, 35, 50]
    for tau in tau_values:
        result = test_time_state_with_params(config, Po_Pa, Qw_m3s, dt_ms=2.0, tau_pinch_ms=tau)
        if result['success']:
            rmse = abs(result['frequency_hz'] - exp_freq)
            print(f"{tau:6.0f} | {result['frequency_hz']:9.3f} | {rmse:5.3f} | {result['execution_time_s']:5.1f} | OK")
        else:
            print(f"{tau:6.0f} | {'FAILED':>9} | {'---':>5} | {'---':>5} | ERROR")

    print()

    # Test a higher pressure condition to see if time-state works better
    print("Testing higher pressure condition (Po=400mbar, Qw=1.5mL/hr):")
    higher_condition = experiments_df[
        (experiments_df['Po_in_mbar'] == 400.0) &
        (experiments_df['Qw_in_mlhr'] == 1.5)
    ]

    if len(higher_condition) > 0:
        exp_freq_high = higher_condition['frequency_hz'].mean()
        Po_high_Pa = mbar_to_pa(400.0)

        print(f"Experimental frequency: {exp_freq_high:.3f} Hz")

        result = test_time_state_with_params(config, Po_high_Pa, Qw_m3s, dt_ms=2.0, tau_pinch_ms=35)
        if result['success']:
            rmse = abs(result['frequency_hz'] - exp_freq_high)
            print(f"Time-state prediction: {result['frequency_hz']:.3f} Hz (RMSE: {rmse:.3f} Hz)")
        else:
            print("Time-state FAILED")

    print()
    print("=" * 50)
    print("Phase 3 parameter testing complete!")

if __name__ == "__main__":
    main()