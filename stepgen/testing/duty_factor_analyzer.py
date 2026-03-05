"""
stepgen.testing.duty_factor_analyzer
====================================
Duty factor analysis and cross-condition validation.

This module provides the DutyFactorAnalyzer class for calibrating duty factors
on one operating condition and testing their validity across different flow
settings. Answers the key question: does one duty factor work for all conditions?
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from stepgen.models.model_comparison import ModelComparator

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


@dataclass
class DutyFactorConditionResult:
    """Results for duty factor testing on a single operating condition."""
    Po_mbar: float
    Qw_mlhr: float
    n_points: int
    duty_factor: float
    frequency_rmse_hz: float
    frequency_mae_hz: float
    frequency_bias_hz: float
    position_errors: List[float]
    experimental_frequencies: List[float]
    predicted_frequencies: List[float]


@dataclass
class DutyFactorResults:
    """Complete duty factor analysis results."""
    calibration_condition: DutyFactorConditionResult
    optimal_duty_factor: float
    cross_condition_results: List[DutyFactorConditionResult]
    position_analysis: Optional[Dict[str, Any]] = None
    error_analysis: Optional[Dict[str, Any]] = None
    execution_time_s: float = 0.0


class DutyFactorAnalyzer:
    """
    Specialized analyzer for duty factor model calibration and validation.

    Tests whether a single duty factor works across all flow conditions by:
    1. Calibrating duty factor on first condition
    2. Applying to all other conditions
    3. Analyzing error patterns and position dependence
    """

    def __init__(self, config: "DeviceConfig", experiments_df: pd.DataFrame):
        """
        Initialize the duty factor analyzer.

        Parameters
        ----------
        config : DeviceConfig
            Device configuration
        experiments_df : pd.DataFrame
            Experimental data from load_experiments()
        """
        self.config = config
        self.experiments_df = experiments_df
        self.model_comparator = ModelComparator()

        # Group data by operating conditions
        self.conditions = self._group_by_conditions()
        print(f"DutyFactorAnalyzer initialized with {len(self.conditions)} conditions")

    def _group_by_conditions(self) -> List[pd.DataFrame]:
        """Group experimental data by operating conditions."""
        conditions = []
        grouped = self.experiments_df.groupby(['Po_in_mbar', 'Qw_in_mlhr'])

        for (Po, Qw), group_data in grouped:
            conditions.append(group_data.copy())

        # Sort by Po, then Qw for consistent ordering
        conditions.sort(key=lambda df: (df.iloc[0]['Po_in_mbar'], df.iloc[0]['Qw_in_mlhr']))

        return conditions

    def run_cross_condition_analysis(self) -> DutyFactorResults:
        """
        Execute comprehensive duty factor analysis across all conditions.

        Returns
        -------
        DutyFactorResults
            Complete analysis results
        """
        start_time = time.time()

        print("Running duty factor cross-condition analysis...")

        # Step 1: Calibrate on first condition
        calibration_condition = self.conditions[0]
        Po_cal = calibration_condition.iloc[0]['Po_in_mbar']
        Qw_cal = calibration_condition.iloc[0]['Qw_in_mlhr']

        print(f"Step 1: Calibrating on condition Po={Po_cal}mbar, Qw={Qw_cal}mL/hr...")

        optimal_phi, calibration_result = self._calibrate_duty_factor(calibration_condition)

        print(f"  Optimal duty factor: {optimal_phi:.3f}")
        print(f"  Calibration RMSE: {calibration_result.frequency_rmse_hz:.2f} Hz")

        # Step 2: Test across all conditions
        print("Step 2: Testing across all conditions...")
        cross_condition_results = []

        for i, condition_data in enumerate(self.conditions):
            Po = condition_data.iloc[0]['Po_in_mbar']
            Qw = condition_data.iloc[0]['Qw_in_mlhr']

            print(f"  Testing condition {i+1}/{len(self.conditions)}: Po={Po}mbar, Qw={Qw}mL/hr...")

            result = self._test_duty_factor_condition(condition_data, optimal_phi)
            cross_condition_results.append(result)

            print(f"    RMSE: {result.frequency_rmse_hz:.2f} Hz")

        # Step 3: Position-dependent analysis
        print("Step 3: Analyzing position dependence...")
        position_analysis = self._analyze_position_dependence()

        # Step 4: Error pattern analysis
        print("Step 4: Analyzing error patterns...")
        error_analysis = self._analyze_error_patterns(cross_condition_results)

        results = DutyFactorResults(
            calibration_condition=calibration_result,
            optimal_duty_factor=optimal_phi,
            cross_condition_results=cross_condition_results,
            position_analysis=position_analysis,
            error_analysis=error_analysis,
            execution_time_s=time.time() - start_time
        )

        print(f"Duty factor analysis complete in {results.execution_time_s:.1f}s")
        self._print_summary(results)

        return results

    def _calibrate_duty_factor(self, condition_data: pd.DataFrame) -> Tuple[float, DutyFactorConditionResult]:
        """
        Find optimal duty factor for a single operating condition.

        Parameters
        ----------
        condition_data : pd.DataFrame
            Experimental data for one operating condition

        Returns
        -------
        Tuple[float, DutyFactorConditionResult]
            Optimal duty factor and calibration results
        """

        def objective(phi: float) -> float:
            """Objective function: frequency RMSE for given duty factor."""
            try:
                result = self._test_duty_factor_condition(condition_data, phi)
                return result.frequency_rmse_hz
            except Exception as e:
                print(f"    Error evaluating phi={phi}: {e}")
                return 1e6  # Large penalty for failed evaluations

        # Optimize duty factor in reasonable range
        result = minimize_scalar(objective, bounds=(0.05, 0.5), method='bounded')

        if not result.success:
            print(f"    Warning: optimization failed, using phi=0.18")
            optimal_phi = 0.18
        else:
            optimal_phi = result.x

        # Get final calibration result
        calibration_result = self._test_duty_factor_condition(condition_data, optimal_phi)

        return optimal_phi, calibration_result

    def _test_duty_factor_condition(self, condition_data: pd.DataFrame, phi: float) -> DutyFactorConditionResult:
        """
        Test a specific duty factor on one operating condition.

        Parameters
        ----------
        condition_data : pd.DataFrame
            Experimental data for the condition
        phi : float
            Duty factor to test

        Returns
        -------
        DutyFactorConditionResult
            Test results for this condition
        """
        Po = condition_data.iloc[0]['Po_in_mbar']
        Qw = condition_data.iloc[0]['Qw_in_mlhr']

        # Create temporary config with specified duty factor
        config_copy = self._configure_duty_factor(phi)

        # Convert to SI units using standard utility functions
        from stepgen.config import mlhr_to_m3s, mbar_to_pa
        Po_Pa = mbar_to_pa(Po)
        Qw_m3s = mlhr_to_m3s(Qw)
        P_out_Pa = 0.0

        # Run duty factor model
        comparison = self.model_comparator.compare_all_models(
            config_copy, Po_Pa, Qw_m3s, P_out_Pa,
            models=['duty_factor']
        )

        # Extract predicted frequencies at experimental positions
        duty_factor_result = comparison.model_results[0]  # First (and only) model result
        predicted_frequencies = []
        experimental_frequencies = []
        position_errors = []

        for _, row in condition_data.iterrows():
            pos = float(row['position'])
            exp_freq = float(row['frequency_hz'])

            # Map position to rung index (same logic as experiments.py)
            if 0.0 <= pos <= 1.0 and not pos.is_integer():
                N = self.config.geometry.Nmc
                idx = int(round(pos * (N - 1)))
            else:
                idx = int(round(pos))

            # Use per-rung frequencies like existing validation code
            frequencies_array = duty_factor_result.frequency_hz
            if isinstance(frequencies_array, np.ndarray) and len(frequencies_array) > idx:
                pred_freq = frequencies_array[idx]
            else:
                # Fallback to mean if array access fails
                pred_freq = np.mean(frequencies_array) if isinstance(frequencies_array, np.ndarray) else frequencies_array

            error = pred_freq - exp_freq

            predicted_frequencies.append(pred_freq)
            experimental_frequencies.append(exp_freq)
            position_errors.append(error)

        # Calculate statistics
        errors = np.array(position_errors)
        frequency_rmse = np.sqrt(np.mean(errors**2))
        frequency_mae = np.mean(np.abs(errors))
        frequency_bias = np.mean(errors)

        return DutyFactorConditionResult(
            Po_mbar=Po,
            Qw_mlhr=Qw,
            n_points=len(condition_data),
            duty_factor=phi,
            frequency_rmse_hz=frequency_rmse,
            frequency_mae_hz=frequency_mae,
            frequency_bias_hz=frequency_bias,
            position_errors=position_errors,
            experimental_frequencies=experimental_frequencies,
            predicted_frequencies=predicted_frequencies
        )

    def _configure_duty_factor(self, phi: float) -> "DeviceConfig":
        """Create config copy with specified duty factor."""
        import dataclasses

        # Create new droplet model with duty factor
        new_droplet_model = dataclasses.replace(
            self.config.droplet_model,
            duty_factor_phi=phi,
            hydraulic_model='duty_factor'
        )

        # Create new config with updated droplet model
        config_copy = dataclasses.replace(
            self.config,
            droplet_model=new_droplet_model
        )

        return config_copy

    def _analyze_position_dependence(self) -> Dict[str, Any]:
        """Analyze whether duty factor should vary with position."""
        print("  Analyzing position-dependent duty factor patterns...")

        # For now, return placeholder analysis
        # This would require more sophisticated analysis of spatial error patterns
        return {
            "analysis_type": "position_dependence",
            "recommendation": "single_duty_factor",  # or "position_dependent"
            "spatial_patterns": [],
            "notes": "Position-dependent analysis not yet implemented"
        }

    def _analyze_error_patterns(self, results: List[DutyFactorConditionResult]) -> Dict[str, Any]:
        """Analyze error patterns across operating conditions."""
        print("  Analyzing error patterns vs Po/Qw...")

        # Extract error trends
        Po_values = [r.Po_mbar for r in results]
        Qw_values = [r.Qw_mlhr for r in results]
        rmse_values = [r.frequency_rmse_hz for r in results]
        bias_values = [r.frequency_bias_hz for r in results]

        # Basic trend analysis
        Po_range = max(Po_values) - min(Po_values) if len(set(Po_values)) > 1 else 0
        Qw_range = max(Qw_values) - min(Qw_values) if len(set(Qw_values)) > 1 else 0

        return {
            "analysis_type": "error_patterns",
            "operating_conditions": {
                "Po_mbar": Po_values,
                "Qw_mlhr": Qw_values,
                "Po_range": Po_range,
                "Qw_range": Qw_range
            },
            "error_statistics": {
                "rmse_hz": rmse_values,
                "bias_hz": bias_values,
                "mean_rmse": np.mean(rmse_values),
                "std_rmse": np.std(rmse_values),
                "mean_bias": np.mean(bias_values)
            },
            "trends": {
                "rmse_vs_Po_correlation": np.corrcoef(Po_values, rmse_values)[0,1] if len(Po_values) > 1 else 0,
                "rmse_vs_Qw_correlation": np.corrcoef(Qw_values, rmse_values)[0,1] if len(Qw_values) > 1 else 0,
                "bias_vs_Po_correlation": np.corrcoef(Po_values, bias_values)[0,1] if len(Po_values) > 1 else 0,
                "bias_vs_Qw_correlation": np.corrcoef(Qw_values, bias_values)[0,1] if len(Qw_values) > 1 else 0
            }
        }

    def _print_summary(self, results: DutyFactorResults) -> None:
        """Print a summary of duty factor analysis results."""
        print("\n" + "=" * 60)
        print("DUTY FACTOR ANALYSIS SUMMARY")
        print("=" * 60)

        print(f"Optimal duty factor: {results.optimal_duty_factor:.3f}")
        print(f"Calibration condition: Po={results.calibration_condition.Po_mbar}mbar, "
              f"Qw={results.calibration_condition.Qw_mlhr}mL/hr")
        print(f"Calibration RMSE: {results.calibration_condition.frequency_rmse_hz:.2f} Hz")

        print("\nCross-condition performance:")
        print(f"{'Condition':<25} {'RMSE [Hz]':<10} {'MAE [Hz]':<10} {'Bias [Hz]':<10}")
        print("-" * 60)

        for result in results.cross_condition_results:
            condition_str = f"Po={result.Po_mbar}, Qw={result.Qw_mlhr}"
            print(f"{condition_str:<25} {result.frequency_rmse_hz:<10.2f} "
                  f"{result.frequency_mae_hz:<10.2f} {result.frequency_bias_hz:<10.2f}")

        # Overall performance
        all_rmse = [r.frequency_rmse_hz for r in results.cross_condition_results]
        print(f"\nOverall performance:")
        print(f"  Mean RMSE: {np.mean(all_rmse):.2f} Hz")
        print(f"  RMSE range: {np.min(all_rmse):.2f} - {np.max(all_rmse):.2f} Hz")

        # Success assessment
        max_acceptable_rmse = 1.0  # Hz - this could be a parameter
        n_good = sum(1 for rmse in all_rmse if rmse < max_acceptable_rmse)
        success_rate = n_good / len(all_rmse) * 100

        print(f"  Success rate (RMSE < {max_acceptable_rmse:.1f} Hz): {success_rate:.0f}% "
              f"({n_good}/{len(all_rmse)} conditions)")

        if success_rate >= 75:
            print("  GOOD: Single duty factor appears viable across conditions")
        elif success_rate >= 50:
            print("  MIXED: Mixed performance - consider position-dependent duty factor")
        else:
            print("  POOR: Poor performance - duty factor model may need refinement")