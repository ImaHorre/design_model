#!/usr/bin/env python3
"""
Time-State Model Configuration Calibration Experiment
=====================================================
Systematic testing of time-state model parameters to identify why the model
predicts zero droplet formation when experimental data shows 1.9 Hz at
Po=300mbar, Qw=1.5mL/hr.

Focus: Keep geometry and operating conditions fixed, vary model parameters
Goal: Find parameter combinations that produce realistic droplet frequencies
"""

import time
import dataclasses
import numpy as np
import pandas as pd
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

def test_time_state_filling_config(config, Po_Pa, Qw_m3s, **model_params):
    """Test time-state FILLING model with specific configuration parameters."""

    # Create modified config with time-state filling parameters
    new_droplet_model = dataclasses.replace(
        config.droplet_model,
        hydraulic_model='time_state_filling',
        **model_params
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
    print("=" * 80)
    print("TIME-STATE MODEL CONFIGURATION CALIBRATION EXPERIMENT")
    print("=" * 80)

    # Load fixed geometry and operating conditions
    config = load_config("configs/w11.yaml")
    experiments_df = load_experiments("data/w11_4_7.csv")

    # Test condition - fixed as per experimental data
    Po_mbar, Qw_mlhr = 300.0, 1.5
    exp_freq = 1.903  # Hz from experimental data

    from stepgen.config import mlhr_to_m3s, mbar_to_pa
    Po_Pa = mbar_to_pa(Po_mbar)
    Qw_m3s = mlhr_to_m3s(Qw_mlhr)

    print(f"Fixed test condition: Po={Po_mbar}mbar, Qw={Qw_mlhr}mL/hr")
    print(f"Target frequency: {exp_freq:.3f} Hz")
    print(f"Geometry: exit_width={config.geometry.junction.exit_width*1e6:.1f}um, exit_depth={config.geometry.junction.exit_depth*1e6:.1f}um")
    print()

    results = []

    # EXPERIMENT 1: Target Volume Scaling
    print("=" * 60)
    print("EXPERIMENT 1: TARGET VOLUME SCALING")
    print("=" * 60)
    print("Hypothesis: Target volumes too large, preventing droplet formation")
    print()

    # Calculate baseline target volume
    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth
    k_base = config.droplet_model.k
    a = config.droplet_model.a
    b = config.droplet_model.b
    D_base = k_base * (w ** a) * (h ** b)
    V_base = (4.0/3.0) * np.pi * (D_base/2.0)**3
    print(f"Baseline: k={k_base:.4f}, D={D_base*1e6:.1f}um, V={V_base*1e18:.3f} fL")
    print()

    print("Testing k scaling factors:")
    print("k_factor | k_value | Target_D | Target_V | Frequency | Time | Status")
    print("---------|---------|----------|----------|-----------|------|-------")

    k_factors = [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]

    for k_factor in k_factors:
        k_test = k_base * k_factor
        D_test = k_test * (w ** a) * (h ** b)
        V_test = (4.0/3.0) * np.pi * (D_test/2.0)**3

        result = test_time_state_config(
            config, Po_Pa, Qw_m3s,
            k=k_test,
            dt_ms=2.0,  # Finer timestep for better resolution
            simulation_time_ms=5000.0  # Longer simulation
        )

        if result['success']:
            status = "OK" if result['frequency_hz'] > 0 else "ZERO"
            marker = " ← TARGET" if 0.5 < result['frequency_hz'] < 5.0 else ""
            print(f"{k_factor:8.2f} | {k_test:7.4f} | {D_test*1e6:8.1f} | {V_test*1e18:8.3f} | {result['frequency_hz']:9.3f} | {result['execution_time_s']:4.1f} | {status}{marker}")

            results.append({
                'experiment': 'k_scaling',
                'k_factor': k_factor,
                'k_value': k_test,
                'frequency_hz': result['frequency_hz'],
                'execution_time_s': result['execution_time_s'],
                'success': True
            })
        else:
            print(f"{k_factor:8.2f} | {k_test:7.4f} | {D_test*1e6:8.1f} | {V_test*1e18:8.3f} | {'FAILED':>9} | {'---':>4} | ERROR")

    print()

    # EXPERIMENT 2: Capillary Pressure Thresholds
    print("=" * 60)
    print("EXPERIMENT 2: CAPILLARY PRESSURE THRESHOLDS")
    print("=" * 60)
    print("Hypothesis: Capillary pressure thresholds too high, preventing flow")
    print()

    print("Testing capillary pressure scaling:")
    print("Pcap_factor | dP_cap_ow | dP_cap_wo | Frequency | Time | Status")
    print("------------|-----------|-----------|-----------|------|-------")

    pcap_factors = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0]

    for pcap_factor in pcap_factors:
        dP_cap_ow = config.droplet_model.dP_cap_ow_mbar * pcap_factor
        dP_cap_wo = config.droplet_model.dP_cap_wo_mbar * pcap_factor

        result = test_time_state_config(
            config, Po_Pa, Qw_m3s,
            dP_cap_ow_mbar=dP_cap_ow,
            dP_cap_wo_mbar=dP_cap_wo,
            dt_ms=2.0,
            simulation_time_ms=5000.0
        )

        if result['success']:
            status = "OK" if result['frequency_hz'] > 0 else "ZERO"
            marker = " ← TARGET" if 0.5 < result['frequency_hz'] < 5.0 else ""
            print(f"{pcap_factor:11.1f} | {dP_cap_ow:9.1f} | {dP_cap_wo:9.1f} | {result['frequency_hz']:9.3f} | {result['execution_time_s']:4.1f} | {status}{marker}")

            results.append({
                'experiment': 'pcap_scaling',
                'pcap_factor': pcap_factor,
                'frequency_hz': result['frequency_hz'],
                'execution_time_s': result['execution_time_s'],
                'success': True
            })
        else:
            print(f"{pcap_factor:11.1f} | {dP_cap_ow:9.1f} | {dP_cap_wo:9.1f} | {'FAILED':>9} | {'---':>4} | ERROR")

    print()

    # EXPERIMENT 3: Phase Timing Parameters
    print("=" * 60)
    print("EXPERIMENT 3: PHASE TIMING PARAMETERS")
    print("=" * 60)
    print("Hypothesis: Phase timings prevent sustained droplet formation")
    print()

    print("Testing phase timing combinations:")
    print("tau_pinch | tau_reset | Frequency | Time | Status")
    print("----------|-----------|-----------|------|-------")

    phase_combinations = [
        (5, 5),    # Very short phases
        (10, 10),  # Short phases
        (20, 10),  # Medium pinch, short reset
        (50, 20),  # Default
        (100, 50), # Long phases
        (1, 1),    # Minimal phases
        (2, 2),    # Ultra-short phases
    ]

    for tau_pinch, tau_reset in phase_combinations:
        result = test_time_state_config(
            config, Po_Pa, Qw_m3s,
            tau_pinch_ms=tau_pinch,
            tau_reset_ms=tau_reset,
            dt_ms=1.0,  # Fine timestep for short phases
            simulation_time_ms=5000.0
        )

        if result['success']:
            status = "OK" if result['frequency_hz'] > 0 else "ZERO"
            marker = " ← TARGET" if 0.5 < result['frequency_hz'] < 5.0 else ""
            print(f"{tau_pinch:9.0f} | {tau_reset:9.0f} | {result['frequency_hz']:9.3f} | {result['execution_time_s']:4.1f} | {status}{marker}")

            results.append({
                'experiment': 'phase_timing',
                'tau_pinch_ms': tau_pinch,
                'tau_reset_ms': tau_reset,
                'frequency_hz': result['frequency_hz'],
                'execution_time_s': result['execution_time_s'],
                'success': True
            })
        else:
            print(f"{tau_pinch:9.0f} | {tau_reset:9.0f} | {'FAILED':>9} | {'---':>4} | ERROR")

    print()

    # EXPERIMENT 4: Conductance During Pinch
    print("=" * 60)
    print("EXPERIMENT 4: CONDUCTANCE FACTORS")
    print("=" * 60)
    print("Hypothesis: Pinch conductance affects flow dynamics")
    print()

    print("Testing g_pinch_frac values:")
    print("g_pinch | Description | Frequency | Time | Status")
    print("--------|-------------|-----------|------|-------")

    g_pinch_values = [0.001, 0.01, 0.05, 0.1, 0.2, 0.5]

    for g_pinch in g_pinch_values:
        desc = f"{g_pinch*100:.1f}% flow"
        result = test_time_state_config(
            config, Po_Pa, Qw_m3s,
            g_pinch_frac=g_pinch,
            dt_ms=2.0,
            simulation_time_ms=5000.0
        )

        if result['success']:
            status = "OK" if result['frequency_hz'] > 0 else "ZERO"
            marker = " ← TARGET" if 0.5 < result['frequency_hz'] < 5.0 else ""
            print(f"{g_pinch:7.3f} | {desc:11} | {result['frequency_hz']:9.3f} | {result['execution_time_s']:4.1f} | {status}{marker}")
        else:
            print(f"{g_pinch:7.3f} | {desc:11} | {'FAILED':>9} | {'---':>4} | ERROR")

    print()

    # EXPERIMENT 5: Time-State FILLING Model
    print("=" * 60)
    print("EXPERIMENT 5: TIME-STATE FILLING MODEL")
    print("=" * 60)
    print("Testing the alternative filling regime time-state model")
    print()

    print("Testing time_state_filling with various parameters:")
    print("Configuration | Frequency | Time | Status")
    print("--------------|-----------|------|-------")

    filling_tests = [
        {'description': 'Default params', 'params': {}},
        {'description': 'Fine timestep', 'params': {'dt_ms': 1.0}},
        {'description': 'Reduced volumes', 'params': {'k': k_base * 0.1, 'dt_ms': 1.0}},
        {'description': 'Fast phases', 'params': {'tau_pinch_ms': 5, 'tau_reset_ms': 5, 'dt_ms': 1.0}},
        {'description': 'Low Pcap', 'params': {'dP_cap_ow_mbar': 10, 'dP_cap_wo_mbar': 8, 'dt_ms': 1.0}},
    ]

    for test in filling_tests:
        desc = test['description']
        params = test['params']
        params['simulation_time_ms'] = 5000.0  # Longer simulation for all tests

        result = test_time_state_filling_config(config, Po_Pa, Qw_m3s, **params)

        if result['success']:
            status = "OK" if result['frequency_hz'] > 0 else "ZERO"
            marker = " ← TARGET" if 0.5 < result['frequency_hz'] < 5.0 else ""
            print(f"{desc:13} | {result['frequency_hz']:9.3f} | {result['execution_time_s']:4.1f} | {status}{marker}")
        else:
            print(f"{desc:13} | {'FAILED':>9} | {'---':>4} | ERROR")

    # EXPERIMENT 6: Combined Parameter Optimization
    print()
    print("=" * 60)
    print("EXPERIMENT 6: COMBINED PARAMETER OPTIMIZATION")
    print("=" * 60)
    print("Testing promising parameter combinations")
    print()

    print("Combined parameter tests:")
    print("Description | Frequency | Time | Status")
    print("------------|-----------|------|-------")

    combined_tests = [
        {
            'description': 'Small drops + low Pcap',
            'params': {
                'k': k_base * 0.05,
                'dP_cap_ow_mbar': 10,
                'dP_cap_wo_mbar': 8,
                'dt_ms': 1.0,
                'simulation_time_ms': 8000.0
            }
        },
        {
            'description': 'Tiny drops + fast phases',
            'params': {
                'k': k_base * 0.01,
                'tau_pinch_ms': 2,
                'tau_reset_ms': 2,
                'dt_ms': 0.5,
                'simulation_time_ms': 10000.0
            }
        },
        {
            'description': 'Minimal thresholds',
            'params': {
                'k': k_base * 0.02,
                'dP_cap_ow_mbar': 5,
                'dP_cap_wo_mbar': 3,
                'tau_pinch_ms': 1,
                'tau_reset_ms': 1,
                'g_pinch_frac': 0.1,
                'dt_ms': 0.5,
                'simulation_time_ms': 15000.0
            }
        }
    ]

    for test in combined_tests:
        desc = test['description']
        params = test['params']

        result = test_time_state_config(config, Po_Pa, Qw_m3s, **params)

        if result['success']:
            status = "OK" if result['frequency_hz'] > 0 else "ZERO"
            marker = " ← SUCCESS!" if 0.5 < result['frequency_hz'] < 5.0 else ""
            print(f"{desc:11} | {result['frequency_hz']:9.3f} | {result['execution_time_s']:4.1f} | {status}{marker}")
        else:
            print(f"{desc:11} | {'FAILED':>9} | {'---':>4} | ERROR")

    print()
    print("=" * 80)
    print("CALIBRATION EXPERIMENT SUMMARY")
    print("=" * 80)

    # Find any successful configurations
    successful_configs = [r for r in results if r['success'] and r['frequency_hz'] > 0.1]

    if successful_configs:
        print(f"Found {len(successful_configs)} configurations with non-zero frequencies:")
        for config_result in successful_configs:
            print(f"  {config_result['experiment']}: {config_result['frequency_hz']:.3f} Hz")
    else:
        print("No configurations produced significant droplet formation frequencies.")
        print("This suggests fundamental model implementation or physics issues.")

    print()
    print("Next steps based on results:")
    print("1. If successful configs found → Fine-tune parameters around working values")
    print("2. If no success → Investigate hydraulic solve outputs and flow rates")
    print("3. Consider fundamental model assumptions and implementation bugs")
    print()
    print("Calibration experiment complete!")

if __name__ == "__main__":
    main()