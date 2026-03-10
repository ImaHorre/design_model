#!/usr/bin/env python3
"""
Phase 3 Focused Time-State Model Evaluation
==========================================
Targeted analysis of time-state model parameters against Phase 2 duty factor baseline.
Optimized for practical runtime while covering key parameter sensitivity.
"""

import time
import dataclasses
import numpy as np
import pandas as pd
from stepgen.config import load_config
from stepgen.io.experiments import load_experiments
from stepgen.models.model_comparison import ModelComparator

def test_time_state_condition(config, Po_Pa, Qw_m3s, dt_ms=2.0, tau_pinch_ms=35):
    """Test time-state model on single condition with specified parameters."""

    # Create modified config with time-state parameters
    new_droplet_model = dataclasses.replace(
        config.droplet_model,
        hydraulic_model='time_state',
        dt_ms=dt_ms,
        tau_pinch_ms=tau_pinch_ms,
        tau_reset_ms=20,  # Fixed reasonable value
        g_pinch_frac=0.01  # Fixed reasonable value
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

        model_result = result.model_results[0]
        frequency = np.mean(model_result.frequency_hz) if isinstance(model_result.frequency_hz, np.ndarray) else model_result.frequency_hz

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

def test_duty_factor_baseline(config, Po_Pa, Qw_m3s, phi=0.30):
    """Test duty factor model for baseline comparison."""

    new_droplet_model = dataclasses.replace(
        config.droplet_model,
        hydraulic_model='duty_factor',
        duty_factor_phi=phi
    )

    config_copy = dataclasses.replace(config, droplet_model=new_droplet_model)
    comparator = ModelComparator()

    start_time = time.time()
    result = comparator.compare_all_models(
        config_copy, Po_Pa, Qw_m3s, 0.0,
        models=['duty_factor']
    )
    execution_time = time.time() - start_time

    model_result = result.model_results[0]
    frequency = np.mean(model_result.frequency_hz) if isinstance(model_result.frequency_hz, np.ndarray) else model_result.frequency_hz

    return {
        'frequency_hz': frequency,
        'execution_time_s': execution_time
    }

def main():
    print("=" * 80)
    print("PHASE 3: TIME-STATE MODEL EVALUATION (FOCUSED ANALYSIS)")
    print("=" * 80)

    # Load data
    config = load_config("configs/w11.yaml")
    experiments_df = load_experiments("data/w11_4_7.csv")

    # Group conditions
    conditions = []
    grouped = experiments_df.groupby(['Po_in_mbar', 'Qw_in_mlhr'])
    for (Po, Qw), group_data in grouped:
        conditions.append({
            'Po_mbar': Po,
            'Qw_mlhr': Qw,
            'data': group_data,
            'exp_freq_mean': np.mean(group_data['frequency_hz']),
            'exp_freq_std': np.std(group_data['frequency_hz'])
        })

    # Sort conditions by Po, then Qw
    conditions.sort(key=lambda c: (c['Po_mbar'], c['Qw_mlhr']))

    print(f"Testing time-state models on {len(conditions)} conditions")
    print("Focus: parameter sensitivity and performance vs duty factor baseline\n")

    # Phase 3.1: Baseline comparison vs duty factor model
    print("=" * 60)
    print("PHASE 3.1: BASELINE COMPARISON")
    print("=" * 60)

    baseline_results = []

    for i, condition in enumerate(conditions[:4]):  # Skip extreme condition for speed
        Po_mbar = condition['Po_mbar']
        Qw_mlhr = condition['Qw_mlhr']

        print(f"\nCondition {i+1}: Po={Po_mbar}mbar, Qw={Qw_mlhr}mL/hr")
        print(f"  Experimental: {condition['exp_freq_mean']:.3f} ± {condition['exp_freq_std']:.3f} Hz")

        # Convert to SI units
        Po_Pa = Po_mbar * 100.0
        Qw_m3s = Qw_mlhr / (1e6 / 3600.0)

        # Test duty factor baseline (from Phase 2)
        duty_result = test_duty_factor_baseline(config, Po_Pa, Qw_m3s, phi=0.30)
        duty_rmse = abs(duty_result['frequency_hz'] - condition['exp_freq_mean'])

        print(f"  Duty Factor (phi=0.30): {duty_result['frequency_hz']:.3f} Hz, "
              f"RMSE: {duty_rmse:.3f} Hz, Time: {duty_result['execution_time_s']:.2f}s")

        # Test time-state model (default parameters)
        ts_result = test_time_state_condition(config, Po_Pa, Qw_m3s, dt_ms=2.0, tau_pinch_ms=35)

        if ts_result['success']:
            ts_rmse = abs(ts_result['frequency_hz'] - condition['exp_freq_mean'])
            improvement = (duty_rmse - ts_rmse) / duty_rmse * 100 if duty_rmse > 0 else 0
            speed_penalty = ts_result['execution_time_s'] / duty_result['execution_time_s']

            print(f"  Time-State (default): {ts_result['frequency_hz']:.3f} Hz, "
                  f"RMSE: {ts_rmse:.3f} Hz, Time: {ts_result['execution_time_s']:.2f}s")
            print(f"    → RMSE improvement: {improvement:+.1f}%, Speed penalty: {speed_penalty:.1f}x")

            baseline_results.append({
                'condition': f"Po={Po_mbar}, Qw={Qw_mlhr}",
                'exp_freq': condition['exp_freq_mean'],
                'duty_freq': duty_result['frequency_hz'],
                'ts_freq': ts_result['frequency_hz'],
                'duty_rmse': duty_rmse,
                'ts_rmse': ts_rmse,
                'improvement_pct': improvement,
                'duty_time': duty_result['execution_time_s'],
                'ts_time': ts_result['execution_time_s'],
                'speed_penalty': speed_penalty
            })
        else:
            print(f"  Time-State (default): FAILED - {ts_result['error']}")
            baseline_results.append({
                'condition': f"Po={Po_mbar}, Qw={Qw_mlhr}",
                'exp_freq': condition['exp_freq_mean'],
                'duty_freq': duty_result['frequency_hz'],
                'ts_freq': np.nan,
                'duty_rmse': duty_rmse,
                'ts_rmse': np.nan,
                'improvement_pct': np.nan,
                'duty_time': duty_result['execution_time_s'],
                'ts_time': np.inf,
                'speed_penalty': np.inf
            })

    # Phase 3.2: Parameter sensitivity analysis
    print("\n" + "=" * 60)
    print("PHASE 3.2: PARAMETER SENSITIVITY ANALYSIS")
    print("=" * 60)

    # Test on one representative condition for speed
    test_condition = conditions[0]  # Po=300mbar, Qw=1.5mL/hr
    Po_Pa = test_condition['Po_mbar'] * 100.0
    Qw_m3s = test_condition['Qw_mlhr'] / (1e6 / 3600.0)

    print(f"\nTesting parameters on: Po={test_condition['Po_mbar']}mbar, Qw={test_condition['Qw_mlhr']}mL/hr")
    print(f"Experimental frequency: {test_condition['exp_freq_mean']:.3f} Hz")

    # Test dt_ms sensitivity
    print(f"\ndt_ms sensitivity:")
    print(f"{'dt_ms':<8} {'Frequency':<10} {'RMSE':<8} {'Time':<8} {'Status'}")
    print("-" * 45)

    dt_values = [1.0, 2.0, 5.0]  # Reduced range for speed
    dt_results = []

    for dt in dt_values:
        result = test_time_state_condition(config, Po_Pa, Qw_m3s, dt_ms=dt, tau_pinch_ms=35)
        if result['success']:
            rmse = abs(result['frequency_hz'] - test_condition['exp_freq_mean'])
            print(f"{dt:<8.1f} {result['frequency_hz']:<10.3f} {rmse:<8.3f} {result['execution_time_s']:<8.2f} {'OK'}")
            dt_results.append({'dt_ms': dt, 'rmse': rmse, 'time': result['execution_time_s']})
        else:
            print(f"{dt:<8.1f} {'FAILED':<10} {'-':<8} {'-':<8} {'ERROR'}")

    # Test tau_pinch_ms sensitivity
    print(f"\ntau_pinch_ms sensitivity:")
    print(f"{'tau_ms':<8} {'Frequency':<10} {'RMSE':<8} {'Time':<8} {'Status'}")
    print("-" * 45)

    tau_values = [20, 35, 50]  # Reduced range for speed
    tau_results = []

    for tau in tau_values:
        result = test_time_state_condition(config, Po_Pa, Qw_m3s, dt_ms=2.0, tau_pinch_ms=tau)
        if result['success']:
            rmse = abs(result['frequency_hz'] - test_condition['exp_freq_mean'])
            print(f"{tau:<8.0f} {result['frequency_hz']:<10.3f} {rmse:<8.3f} {result['execution_time_s']:<8.2f} {'OK'}")
            tau_results.append({'tau_pinch_ms': tau, 'rmse': rmse, 'time': result['execution_time_s']})
        else:
            print(f"{tau:<8.0f} {'FAILED':<10} {'-':<8} {'-':<8} {'ERROR'}")

    # Summary analysis
    print("\n" + "=" * 80)
    print("PHASE 3 SUMMARY")
    print("=" * 80)

    # Overall baseline comparison
    successful_results = [r for r in baseline_results if not np.isnan(r['ts_rmse'])]

    if successful_results:
        mean_duty_rmse = np.mean([r['duty_rmse'] for r in successful_results])
        mean_ts_rmse = np.mean([r['ts_rmse'] for r in successful_results])
        mean_improvement = np.mean([r['improvement_pct'] for r in successful_results])
        mean_speed_penalty = np.mean([r['speed_penalty'] for r in successful_results])

        print(f"\nBaseline Comparison (n={len(successful_results)} conditions):")
        print(f"  Duty Factor RMSE:    {mean_duty_rmse:.3f} Hz (average)")
        print(f"  Time-State RMSE:     {mean_ts_rmse:.3f} Hz (average)")
        print(f"  Average improvement: {mean_improvement:+.1f}%")
        print(f"  Speed penalty:       {mean_speed_penalty:.1f}x slower")

        if mean_improvement > 10:
            assessment = "EXCELLENT: Time-state models significantly outperform duty factor"
        elif mean_improvement > 0:
            assessment = "GOOD: Time-state models show improvement over duty factor"
        elif mean_improvement > -10:
            assessment = "MIXED: Time-state and duty factor models comparable"
        else:
            assessment = "POOR: Time-state models underperform duty factor baseline"

        print(f"\n  ASSESSMENT: {assessment}")

    # Parameter sensitivity summary
    if dt_results:
        best_dt = min(dt_results, key=lambda x: x['rmse'])
        print(f"\ndt_ms Parameter:")
        print(f"  Best value: {best_dt['dt_ms']:.1f} ms (RMSE: {best_dt['rmse']:.3f} Hz)")
        print(f"  Speed vs accuracy trade-off evident")

    if tau_results:
        best_tau = min(tau_results, key=lambda x: x['rmse'])
        print(f"\ntau_pinch_ms Parameter:")
        print(f"  Best value: {best_tau['tau_pinch_ms']:.0f} ms (RMSE: {best_tau['rmse']:.3f} Hz)")

    print(f"\nPhase 3 focused evaluation complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()