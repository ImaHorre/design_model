#!/usr/bin/env python3
"""
Quick Time-State Model Calibration
==================================
Focused testing based on the breakthrough finding that k_factor scaling works.
"""

import time
import dataclasses
import numpy as np
from stepgen.config import load_config
from stepgen.io.experiments import load_experiments
from stepgen.models.model_comparison import ModelComparator

def test_time_state_config(config, Po_Pa, Qw_m3s, **model_params):
    """Test time-state model with specific configuration parameters."""

    # Create modified config with time-state parameters
    new_droplet_model = dataclasses.replace(
        config.droplet_model,
        hydraulic_model='time_state',
        **model_params
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

def main():
    print("Quick Time-State Model Calibration")
    print("=" * 50)

    # Load fixed geometry and operating conditions
    config = load_config("configs/w11.yaml")
    experiments_df = load_experiments("data/w11_4_7.csv")

    # Test condition
    Po_mbar, Qw_mlhr = 300.0, 1.5
    exp_freq = 1.903  # Hz

    from stepgen.config import mlhr_to_m3s, mbar_to_pa
    Po_Pa = mbar_to_pa(Po_mbar)
    Qw_m3s = mlhr_to_m3s(Qw_mlhr)

    print(f"Test condition: Po={Po_mbar}mbar, Qw={Qw_mlhr}mL/hr")
    print(f"Target frequency: {exp_freq:.3f} Hz")
    print()

    # Get baseline values
    k_base = config.droplet_model.k

    print("TARGET VOLUME SCALING RESULTS:")
    print("k_factor | Frequency | Time | Error_vs_Target | Status")
    print("---------|-----------|------|-----------------|-------")

    # Test k_factors around the promising range
    k_factors = [0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2]

    promising_results = []

    for k_factor in k_factors:
        k_test = k_base * k_factor

        result = test_time_state_config(
            config, Po_Pa, Qw_m3s,
            k=k_test,
            dt_ms=2.0,
            simulation_time_ms=8000.0  # Longer simulation
        )

        if result['success']:
            freq = result['frequency_hz']
            error = abs(freq - exp_freq) / exp_freq * 100
            status = "EXCELLENT" if error < 20 else "GOOD" if error < 50 else "OK" if freq > 0 else "ZERO"

            print(f"{k_factor:8.3f} | {freq:9.3f} | {result['execution_time_s']:4.1f} | {error:13.1f}% | {status}")

            if freq > 0.1:  # Promising result
                promising_results.append({
                    'k_factor': k_factor,
                    'frequency': freq,
                    'error_pct': error
                })
        else:
            print(f"{k_factor:8.3f} | FAILED    | ---- | ----------------- | ERROR")

    print()

    if promising_results:
        print("PROMISING CONFIGURATIONS FOUND:")
        best = min(promising_results, key=lambda x: x['error_pct'])
        print(f"Best match: k_factor={best['k_factor']:.3f}, freq={best['frequency']:.3f} Hz, error={best['error_pct']:.1f}%")
        print()

        # Test the best configuration with different phase timings
        print("OPTIMIZING PHASE TIMINGS FOR BEST k_factor:")
        print("tau_pinch | tau_reset | Frequency | Time | Error_vs_Target")
        print("----------|-----------|-----------|------|----------------")

        k_best = k_base * best['k_factor']
        phase_combinations = [
            (1, 1), (2, 2), (5, 5), (10, 10), (20, 10), (50, 20), (100, 50)
        ]

        for tau_pinch, tau_reset in phase_combinations:
            result = test_time_state_config(
                config, Po_Pa, Qw_m3s,
                k=k_best,
                tau_pinch_ms=tau_pinch,
                tau_reset_ms=tau_reset,
                dt_ms=1.0,
                simulation_time_ms=10000.0
            )

            if result['success']:
                freq = result['frequency_hz']
                error = abs(freq - exp_freq) / exp_freq * 100
                print(f"{tau_pinch:9.0f} | {tau_reset:9.0f} | {freq:9.3f} | {result['execution_time_s']:4.1f} | {error:13.1f}%")

        print()

        # Test capillary pressure scaling with best k_factor
        print("TESTING CAPILLARY PRESSURE WITH BEST k_factor:")
        print("Pcap_factor | Frequency | Time | Error_vs_Target")
        print("------------|-----------|------|----------------")

        pcap_factors = [0.1, 0.2, 0.5, 1.0, 2.0]

        for pcap_factor in pcap_factors:
            dP_cap_ow = config.droplet_model.dP_cap_ow_mbar * pcap_factor
            dP_cap_wo = config.droplet_model.dP_cap_wo_mbar * pcap_factor

            result = test_time_state_config(
                config, Po_Pa, Qw_m3s,
                k=k_best,
                dP_cap_ow_mbar=dP_cap_ow,
                dP_cap_wo_mbar=dP_cap_wo,
                dt_ms=1.0,
                simulation_time_ms=10000.0
            )

            if result['success']:
                freq = result['frequency_hz']
                error = abs(freq - exp_freq) / exp_freq * 100
                print(f"{pcap_factor:11.1f} | {freq:9.3f} | {result['execution_time_s']:4.1f} | {error:13.1f}%")

        print()

        # Test time_state_filling model with best parameters
        print("TESTING time_state_filling MODEL:")

        # Test time_state_filling with best k_factor
        new_droplet_model = dataclasses.replace(
            config.droplet_model,
            hydraulic_model='time_state_filling',
            k=k_best,
            dt_ms=1.0,
            simulation_time_ms=10000.0
        )

        config_copy = dataclasses.replace(config, droplet_model=new_droplet_model)
        comparator = ModelComparator()

        try:
            start_time = time.time()
            result = comparator.compare_all_models(
                config_copy, Po_Pa, Qw_m3s, 0.0,
                models=['time_state_filling']
            )
            execution_time = time.time() - start_time

            model_result = result.model_results[0]
            frequency = np.mean(model_result.frequency_hz) if isinstance(model_result.frequency_hz, np.ndarray) else model_result.frequency_hz
            error = abs(frequency - exp_freq) / exp_freq * 100

            print(f"time_state_filling: {frequency:.3f} Hz, error: {error:.1f}%")

        except Exception as e:
            print(f"time_state_filling FAILED: {e}")

    else:
        print("No promising configurations found. May need more aggressive parameter scaling.")

    print()
    print("=" * 50)
    print("CALIBRATION SUMMARY:")
    print("- Target volume scaling (k_factor) is KEY to enabling droplet formation")
    print("- Reduced droplet sizes allow volume thresholds to be reached")
    print("- Further optimization of phase timings and pressure thresholds needed")
    print("=" * 50)

if __name__ == "__main__":
    main()