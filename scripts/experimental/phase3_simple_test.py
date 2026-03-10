#!/usr/bin/env python3
"""
Phase 3 Simple Test
===================
Basic time-state vs duty factor comparison using the same approach as Phase 2.
"""

import time
from stepgen.config import load_config
from stepgen.io.experiments import load_experiments
from stepgen.models.model_comparison import ModelComparator

def main():
    print("Phase 3 Simple Test: Time-State vs Duty Factor Baseline")
    print("=" * 60)

    # Load data
    config = load_config("configs/w11.yaml")
    experiments_df = load_experiments("data/w11_4_7.csv")

    # Test on first condition from Phase 2
    condition_data = experiments_df[
        (experiments_df['Po_in_mbar'] == 300.0) &
        (experiments_df['Qw_in_mlhr'] == 1.5)
    ]

    if len(condition_data) == 0:
        print("No matching condition data found")
        return

    Po = 300.0  # mbar
    Qw = 1.5    # mL/hr
    exp_freq_mean = condition_data['frequency_hz'].mean()

    print(f"Test condition: Po={Po}mbar, Qw={Qw}mL/hr")
    print(f"Experimental frequency: {exp_freq_mean:.3f} Hz")
    print()

    # Convert to SI
    from stepgen.config import mlhr_to_m3s, mbar_to_pa
    Po_Pa = mbar_to_pa(Po)
    Qw_m3s = mlhr_to_m3s(Qw)
    P_out_Pa = 0.0

    # Initialize model comparator
    comparator = ModelComparator()

    # Test 1: Duty factor model (baseline from Phase 2)
    print("Testing duty factor model...")
    try:
        start_time = time.time()
        duty_result = comparator.compare_all_models(
            config, Po_Pa, Qw_m3s, P_out_Pa,
            models=['duty_factor']
        )
        duty_time = time.time() - start_time

        duty_freq = duty_result.model_results[0].frequency_hz
        if hasattr(duty_freq, '__len__'):
            duty_freq = duty_freq.mean()

        duty_rmse = abs(duty_freq - exp_freq_mean)

        print(f"  Duty factor: {duty_freq:.3f} Hz")
        print(f"  RMSE: {duty_rmse:.3f} Hz")
        print(f"  Time: {duty_time:.2f}s")

    except Exception as e:
        print(f"  Duty factor FAILED: {e}")
        duty_freq, duty_rmse, duty_time = None, None, None

    print()

    # Test 2: Time-state model
    print("Testing time-state model...")
    try:
        start_time = time.time()
        ts_result = comparator.compare_all_models(
            config, Po_Pa, Qw_m3s, P_out_Pa,
            models=['time_state']
        )
        ts_time = time.time() - start_time

        ts_freq = ts_result.model_results[0].frequency_hz
        if hasattr(ts_freq, '__len__'):
            ts_freq = ts_freq.mean()

        ts_rmse = abs(ts_freq - exp_freq_mean)

        print(f"  Time-state: {ts_freq:.3f} Hz")
        print(f"  RMSE: {ts_rmse:.3f} Hz")
        print(f"  Time: {ts_time:.2f}s")

        if duty_rmse is not None:
            improvement = (duty_rmse - ts_rmse) / duty_rmse * 100 if duty_rmse > 0 else 0
            speed_ratio = ts_time / duty_time if duty_time is not None else float('inf')
            print(f"  Improvement vs duty factor: {improvement:+.1f}%")
            print(f"  Speed penalty: {speed_ratio:.1f}x")

    except Exception as e:
        print(f"  Time-state FAILED: {e}")
        ts_freq, ts_rmse, ts_time = None, None, None

    print()

    # Test 3: Linear model for reference
    print("Testing linear model...")
    try:
        start_time = time.time()
        linear_result = comparator.compare_all_models(
            config, Po_Pa, Qw_m3s, P_out_Pa,
            models=['steady']
        )
        linear_time = time.time() - start_time

        linear_freq = linear_result.model_results[0].frequency_hz
        if hasattr(linear_freq, '__len__'):
            linear_freq = linear_freq.mean()

        linear_rmse = abs(linear_freq - exp_freq_mean)

        print(f"  Linear: {linear_freq:.3f} Hz")
        print(f"  RMSE: {linear_rmse:.3f} Hz")
        print(f"  Time: {linear_time:.2f}s")

    except Exception as e:
        print(f"  Linear FAILED: {e}")
        linear_freq, linear_rmse, linear_time = None, None, None

    print()
    print("=" * 60)
    print("PHASE 3 SIMPLE TEST SUMMARY")
    print("=" * 60)

    results = []
    if duty_freq is not None:
        results.append(f"Duty Factor: {duty_rmse:.3f} Hz RMSE")
    if ts_freq is not None:
        results.append(f"Time-State: {ts_rmse:.3f} Hz RMSE")
    if linear_freq is not None:
        results.append(f"Linear: {linear_rmse:.3f} Hz RMSE")

    if results:
        print("Results on Po=300mbar, Qw=1.5mL/hr:")
        for result in results:
            print(f"  {result}")
    else:
        print("All models failed - configuration or implementation issues")

    print()
    print("This test validates basic time-state model functionality for Phase 3.")

if __name__ == "__main__":
    main()