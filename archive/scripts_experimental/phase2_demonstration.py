#!/usr/bin/env python3
"""
Phase 2 Demonstration Script
============================
Demonstrates the duty factor cross-condition analysis functionality implemented in Phase 2.

This script showcases:
1. Duty factor calibration on reference condition
2. Cross-condition validation
3. Per-position accuracy analysis
4. Error pattern analysis vs operating conditions
5. Comparison with different duty factor values
"""

import numpy as np
import pandas as pd
from stepgen.config import load_config
from stepgen.io.experiments import load_experiments
from stepgen.testing.duty_factor_analyzer import DutyFactorAnalyzer

def main():
    print("=" * 80)
    print("PHASE 2 DUTY FACTOR ANALYSIS DEMONSTRATION")
    print("=" * 80)

    # Load configuration and experimental data
    print("\n1. Loading configuration and experimental data...")
    config = load_config("configs/w11.yaml")
    experiments_df = load_experiments("data/w11_4_7.csv")

    print(f"   Device: {experiments_df.iloc[0]['device_id']}")
    print(f"   Total experimental points: {len(experiments_df)}")
    print(f"   Operating conditions: {len(experiments_df.groupby(['Po_in_mbar', 'Qw_in_mlhr']))}")

    # Show experimental conditions summary
    print("\n   Experimental conditions summary:")
    condition_summary = experiments_df.groupby(['Po_in_mbar', 'Qw_in_mlhr']).agg({
        'position': 'count',
        'frequency_hz': ['mean', 'std']
    }).round(3)
    condition_summary.columns = ['n_points', 'freq_mean_hz', 'freq_std_hz']
    print(condition_summary)

    # Initialize analyzer
    print("\n2. Initializing Duty Factor Analyzer...")
    analyzer = DutyFactorAnalyzer(config, experiments_df)

    # Run main analysis
    print("\n3. Running Cross-Condition Analysis...")
    results = analyzer.run_cross_condition_analysis()

    # Detailed per-condition analysis
    print("\n4. Detailed Per-Condition Results...")
    print("-" * 60)

    for i, condition_result in enumerate(results.cross_condition_results):
        print(f"\nCondition {i+1}: Po={condition_result.Po_mbar}mbar, Qw={condition_result.Qw_mlhr}mL/hr")
        print(f"  Data points: {condition_result.n_points}")
        print(f"  Duty factor: {condition_result.duty_factor:.3f}")
        print(f"  Frequency RMSE: {condition_result.frequency_rmse_hz:.3f} Hz")
        print(f"  Frequency MAE:  {condition_result.frequency_mae_hz:.3f} Hz")
        print(f"  Frequency bias: {condition_result.frequency_bias_hz:+.3f} Hz")

        # Show per-position comparison
        print("  Per-position comparison:")
        print("    Position  | Experimental | Predicted | Error")
        print("    --------- | ------------ | --------- | -----")

        # Get position data for this condition
        condition_data = analyzer.conditions[i]
        for j, (exp_freq, pred_freq, error) in enumerate(zip(
            condition_result.experimental_frequencies,
            condition_result.predicted_frequencies,
            condition_result.position_errors
        )):
            pos = condition_data.iloc[j]['position']
            print(f"    {pos:8.3f}  | {exp_freq:11.3f}  | {pred_freq:8.3f}  | {error:+6.3f}")

    # Demonstrate sensitivity to duty factor value
    print("\n5. Duty Factor Sensitivity Demonstration...")
    print("-" * 50)

    # Test a few different duty factors on the calibration condition
    test_duty_factors = [0.20, 0.25, 0.30, 0.35, 0.40]
    calibration_condition = analyzer.conditions[0]

    print("Testing different duty factors on calibration condition:")
    print(f"(Po={calibration_condition.iloc[0]['Po_in_mbar']}mbar, Qw={calibration_condition.iloc[0]['Qw_in_mlhr']}mL/hr)")
    print("\nDuty Factor | RMSE (Hz) | Bias (Hz)")
    print("----------- | --------- | ---------")

    for phi in test_duty_factors:
        test_result = analyzer._test_duty_factor_condition(calibration_condition, phi)
        marker = " <- OPTIMAL" if abs(phi - results.optimal_duty_factor) < 0.01 else ""
        print(f"    {phi:.2f}    |   {test_result.frequency_rmse_hz:.3f}   | {test_result.frequency_bias_hz:+.3f}{marker}")

    # Error correlation analysis
    print("\n6. Error Pattern Analysis...")
    print("-" * 30)

    if results.error_analysis:
        error_stats = results.error_analysis['error_statistics']
        trends = results.error_analysis['trends']

        print(f"Mean RMSE across conditions: {error_stats['mean_rmse']:.3f} Hz")
        print(f"RMSE standard deviation: {error_stats['std_rmse']:.3f} Hz")
        print(f"Mean bias: {error_stats['mean_bias']:.3f} Hz")

        print(f"\nCorrelation analysis:")
        print(f"  RMSE vs Pressure (Po): {trends['rmse_vs_Po_correlation']:+.3f}")
        print(f"  RMSE vs Flow (Qw):     {trends['rmse_vs_Qw_correlation']:+.3f}")
        print(f"  Bias vs Pressure (Po): {trends['bias_vs_Po_correlation']:+.3f}")
        print(f"  Bias vs Flow (Qw):     {trends['bias_vs_Qw_correlation']:+.3f}")

    # Final assessment
    print("\n7. Phase 2 Assessment Summary...")
    print("-" * 35)

    # Calculate success metrics
    rmse_values = [r.frequency_rmse_hz for r in results.cross_condition_results]
    success_threshold = 1.0  # Hz
    n_good = sum(1 for rmse in rmse_values if rmse < success_threshold)
    success_rate = n_good / len(rmse_values) * 100

    print(f"Optimal duty factor: {results.optimal_duty_factor:.3f}")
    print(f"Execution time: {results.execution_time_s:.1f} seconds")
    print(f"Conditions tested: {len(results.cross_condition_results)}")
    print(f"Success rate (RMSE < {success_threshold} Hz): {success_rate:.0f}% ({n_good}/{len(rmse_values)})")
    print(f"RMSE range: {min(rmse_values):.2f} - {max(rmse_values):.2f} Hz")

    # Assessment conclusion
    if success_rate >= 75:
        assessment = "EXCELLENT: Single duty factor works very well across conditions"
    elif success_rate >= 50:
        assessment = "GOOD: Single duty factor viable with some conditions needing refinement"
    else:
        assessment = "POOR: Single duty factor approach needs significant improvement"

    print(f"\nFINAL ASSESSMENT: {assessment}")

    print("\n" + "=" * 80)
    print("PHASE 2 DEMONSTRATION COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()