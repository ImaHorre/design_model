"""
stepgen.testing.time_state_evaluator
====================================
Comprehensive evaluation of time-state models against experimental data.

This module provides the TimeStateEvaluator class for systematic parameter
sensitivity analysis, performance comparison, and model improvement feedback
for time-state droplet generation models.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from stepgen.models.model_comparison import ModelComparator

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


@dataclass
class ParameterSensitivityPoint:
    """Results for a single parameter value in sensitivity analysis."""
    parameter_name: str
    parameter_value: float
    frequency_rmse_hz: float
    frequency_bias_hz: float
    execution_time_s: float
    convergence_success: bool


@dataclass
class ParameterSensitivityResults:
    """Complete parameter sensitivity analysis results."""
    parameter_name: str
    parameter_values: List[float]
    sensitivity_points: List[ParameterSensitivityPoint]
    optimal_value: float
    optimal_rmse: float
    baseline_rmse: float
    improvement_factor: float


@dataclass
class TimeStateModelComparison:
    """Comparison results for time-state vs baseline models."""
    condition_description: str
    linear_rmse_hz: float
    time_state_rmse_hz: float
    time_state_filling_rmse_hz: float
    improvement_vs_linear: float  # (linear_rmse - time_state_rmse) / linear_rmse
    execution_time_linear_s: float
    execution_time_time_state_s: float
    time_penalty_factor: float  # execution_time_time_state / execution_time_linear


@dataclass
class TimeStateResults:
    """Complete time-state model evaluation results."""
    baseline_comparisons: List[TimeStateModelComparison]
    parameter_sensitivity: Dict[str, ParameterSensitivityResults]
    performance_optimization: Optional[Dict[str, Any]] = None
    tuning_recommendations: Optional[Dict[str, Any]] = None
    execution_time_s: float = 0.0


class TimeStateEvaluator:
    """
    Comprehensive evaluation of time-state models against experimental data.

    Focuses on parameter tuning, performance analysis, and model improvement
    feedback for the first realistic comparison against experimental data.
    """

    def __init__(self, config: "DeviceConfig", experiments_df: pd.DataFrame):
        """
        Initialize the time-state evaluator.

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
        print(f"TimeStateEvaluator initialized with {len(self.conditions)} conditions")

    def _group_by_conditions(self) -> List[pd.DataFrame]:
        """Group experimental data by operating conditions."""
        conditions = []
        grouped = self.experiments_df.groupby(['Po_in_mbar', 'Qw_in_mlhr'])

        for (Po, Qw), group_data in grouped:
            conditions.append(group_data.copy())

        # Sort by Po, then Qw for consistent ordering
        conditions.sort(key=lambda df: (df.iloc[0]['Po_in_mbar'], df.iloc[0]['Qw_in_mlhr']))

        return conditions

    def run_evaluation(self) -> TimeStateResults:
        """
        Execute comprehensive time-state model evaluation.

        Returns
        -------
        TimeStateResults
            Complete evaluation results
        """
        start_time = time.time()

        print("Running time-state model evaluation...")

        # Step 1: Baseline model comparison
        print("Step 1: Baseline comparison vs linear models...")
        baseline_comparisons = self._compare_baseline_models()

        # Step 2: Parameter sensitivity analysis
        print("Step 2: Parameter sensitivity analysis...")
        parameter_sensitivity = self._analyze_parameter_sensitivity()

        # Step 3: Performance optimization
        print("Step 3: Performance optimization analysis...")
        performance_optimization = self._optimize_performance()

        # Step 4: Generate tuning recommendations
        print("Step 4: Generating tuning recommendations...")
        tuning_recommendations = self._generate_tuning_recommendations(
            baseline_comparisons, parameter_sensitivity
        )

        results = TimeStateResults(
            baseline_comparisons=baseline_comparisons,
            parameter_sensitivity=parameter_sensitivity,
            performance_optimization=performance_optimization,
            tuning_recommendations=tuning_recommendations,
            execution_time_s=time.time() - start_time
        )

        print(f"Time-state evaluation complete in {results.execution_time_s:.1f}s")
        self._print_summary(results)

        return results

    def _compare_baseline_models(self) -> List[TimeStateModelComparison]:
        """Compare time-state models vs linear baseline across conditions."""
        comparisons = []

        for i, condition_data in enumerate(self.conditions):
            Po = condition_data.iloc[0]['Po_in_mbar']
            Qw = condition_data.iloc[0]['Qw_in_mlhr']

            print(f"  Condition {i+1}/{len(self.conditions)}: Po={Po}mbar, Qw={Qw}mL/hr...")

            # Convert to SI units using standard utility functions
            from stepgen.config import mlhr_to_m3s, mbar_to_pa
            Po_Pa = mbar_to_pa(Po)
            Qw_m3s = mlhr_to_m3s(Qw)
            P_out_Pa = 0.0

            # Run all models with timing
            models = ['steady', 'time_state', 'time_state_filling']
            model_results = {}
            execution_times = {}

            for model_name in models:
                try:
                    start_model_time = time.time()
                    comparison = self.model_comparator.compare_all_models(
                        self.config, Po_Pa, Qw_m3s, P_out_Pa,
                        models=[model_name]
                    )
                    execution_times[model_name] = time.time() - start_model_time
                    model_results[model_name] = comparison.model_results[0]

                except Exception as e:
                    print(f"    Error with {model_name}: {e}")
                    execution_times[model_name] = float('inf')
                    model_results[model_name] = None

            # Calculate experimental RMSE (simplified - using mean frequency)
            exp_freqs = condition_data['frequency_hz'].values
            exp_mean_freq = np.mean(exp_freqs)

            rmse_values = {}
            for model_name in models:
                if model_results[model_name] is not None:
                    pred_freq = model_results[model_name].frequency_hz
                    rmse_values[model_name] = abs(pred_freq - exp_mean_freq)
                else:
                    rmse_values[model_name] = float('inf')

            # Create comparison
            linear_rmse = rmse_values.get('steady', float('inf'))
            time_state_rmse = rmse_values.get('time_state', float('inf'))
            time_state_filling_rmse = rmse_values.get('time_state_filling', float('inf'))

            improvement = (linear_rmse - time_state_rmse) / linear_rmse if linear_rmse > 0 else 0
            time_penalty = (execution_times.get('time_state', 0) /
                          execution_times.get('steady', 1) if execution_times.get('steady', 0) > 0 else float('inf'))

            comparison = TimeStateModelComparison(
                condition_description=f"Po={Po}mbar, Qw={Qw}mL/hr",
                linear_rmse_hz=linear_rmse,
                time_state_rmse_hz=time_state_rmse,
                time_state_filling_rmse_hz=time_state_filling_rmse,
                improvement_vs_linear=improvement,
                execution_time_linear_s=execution_times.get('steady', 0),
                execution_time_time_state_s=execution_times.get('time_state', 0),
                time_penalty_factor=time_penalty
            )

            comparisons.append(comparison)

            print(f"    Linear RMSE: {linear_rmse:.2f} Hz")
            print(f"    Time-state RMSE: {time_state_rmse:.2f} Hz")
            print(f"    Improvement: {improvement*100:+.1f}%")
            print(f"    Time penalty: {time_penalty:.1f}x")

        return comparisons

    def _analyze_parameter_sensitivity(self) -> Dict[str, ParameterSensitivityResults]:
        """Systematic analysis of time-state model parameter sensitivity."""

        # Define parameter ranges for sensitivity analysis
        parameter_ranges = {
            'tau_pinch_ms': [20.0, 35.0, 50.0, 75.0, 100.0],
            'tau_reset_ms': [10.0, 20.0, 30.0, 40.0, 50.0],
            'g_pinch_frac': [0.001, 0.005, 0.01, 0.05, 0.1],
            'dt_ms': [0.5, 1.0, 2.0, 5.0],
            'simulation_time_ms': [1000.0, 2000.0, 5000.0, 10000.0]
        }

        sensitivity_results = {}

        for param_name, param_values in parameter_ranges.items():
            print(f"  Analyzing {param_name} sensitivity...")

            # Get baseline performance with default parameters
            baseline_rmse = self._evaluate_parameter_set({})

            sensitivity_points = []
            best_rmse = float('inf')
            best_value = param_values[0]

            for value in param_values:
                print(f"    Testing {param_name}={value}...")

                try:
                    start_time_param = time.time()
                    test_params = {param_name: value}
                    rmse, bias = self._evaluate_parameter_set(test_params)
                    exec_time = time.time() - start_time_param
                    success = True

                    if rmse < best_rmse:
                        best_rmse = rmse
                        best_value = value

                except Exception as e:
                    print(f"      Error: {e}")
                    rmse = float('inf')
                    bias = 0.0
                    exec_time = float('inf')
                    success = False

                point = ParameterSensitivityPoint(
                    parameter_name=param_name,
                    parameter_value=value,
                    frequency_rmse_hz=rmse,
                    frequency_bias_hz=bias,
                    execution_time_s=exec_time,
                    convergence_success=success
                )
                sensitivity_points.append(point)

                print(f"      RMSE: {rmse:.2f} Hz, Time: {exec_time:.1f}s")

            improvement = (baseline_rmse - best_rmse) / baseline_rmse if baseline_rmse > 0 else 0

            sensitivity_results[param_name] = ParameterSensitivityResults(
                parameter_name=param_name,
                parameter_values=param_values,
                sensitivity_points=sensitivity_points,
                optimal_value=best_value,
                optimal_rmse=best_rmse,
                baseline_rmse=baseline_rmse,
                improvement_factor=improvement
            )

            print(f"    Best {param_name}: {best_value} (RMSE: {best_rmse:.2f} Hz, "
                  f"improvement: {improvement*100:+.1f}%)")

        return sensitivity_results

    def _evaluate_parameter_set(self, test_params: Dict[str, float]) -> Tuple[float, float]:
        """
        Evaluate time-state model with specific parameter set.

        Parameters
        ----------
        test_params : Dict[str, float]
            Parameters to override

        Returns
        -------
        Tuple[float, float]
            Mean RMSE and bias across all conditions
        """
        import dataclasses

        # Create new droplet model with test parameters
        droplet_model_dict = dataclasses.asdict(self.config.droplet_model)

        # Apply parameter overrides
        for param_name, value in test_params.items():
            droplet_model_dict[param_name] = value

        # Ensure time-state model is selected
        droplet_model_dict['hydraulic_model'] = 'time_state'

        # Create new droplet model and config
        new_droplet_model = type(self.config.droplet_model)(**droplet_model_dict)
        config_copy = dataclasses.replace(self.config, droplet_model=new_droplet_model)

        # Test on subset of conditions (first 2 for speed)
        test_conditions = self.conditions[:2]
        rmse_values = []
        bias_values = []

        for condition_data in test_conditions:
            Po = condition_data.iloc[0]['Po_in_mbar']
            Qw = condition_data.iloc[0]['Qw_in_mlhr']

            Po_Pa = mbar_to_pa(Po)
            Qw_m3s = mlhr_to_m3s(Qw)

            # Run time-state model
            comparison = self.model_comparator.compare_all_models(
                config_copy, Po_Pa, Qw_m3s, 0.0, models=['time_state']
            )

            # Calculate error vs experimental data
            exp_freqs = condition_data['frequency_hz'].values
            exp_mean_freq = np.mean(exp_freqs)
            pred_freq = comparison.model_results[0].frequency_hz

            error = pred_freq - exp_mean_freq
            rmse_values.append(abs(error))
            bias_values.append(error)

        return np.mean(rmse_values), np.mean(bias_values)

    def _optimize_performance(self) -> Dict[str, Any]:
        """Analyze performance optimization opportunities."""
        print("  Analyzing performance bottlenecks...")

        # Test different time step sizes vs accuracy
        dt_values = [0.5, 1.0, 2.0, 5.0]
        dt_analysis = {}

        for dt in dt_values:
            try:
                start_time_dt = time.time()
                rmse, _ = self._evaluate_parameter_set({'dt_ms': dt})
                exec_time = time.time() - start_time_dt

                dt_analysis[dt] = {
                    'rmse_hz': rmse,
                    'execution_time_s': exec_time,
                    'speed_factor': exec_time / dt_analysis.get(2.0, {}).get('execution_time_s', exec_time)
                }

            except Exception as e:
                print(f"    Error with dt={dt}: {e}")
                dt_analysis[dt] = {'rmse_hz': float('inf'), 'execution_time_s': float('inf')}

        return {
            "timestep_analysis": dt_analysis,
            "recommendations": self._generate_performance_recommendations(dt_analysis)
        }

    def _generate_performance_recommendations(self, dt_analysis: Dict) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []

        # Find optimal time step
        valid_results = {dt: data for dt, data in dt_analysis.items()
                        if np.isfinite(data['rmse_hz']) and np.isfinite(data['execution_time_s'])}

        if valid_results:
            # Find fastest acceptable accuracy
            min_rmse = min(data['rmse_hz'] for data in valid_results.values())
            acceptable_rmse_threshold = min_rmse * 1.2  # Allow 20% accuracy loss

            fast_options = [(dt, data) for dt, data in valid_results.items()
                           if data['rmse_hz'] <= acceptable_rmse_threshold]

            if fast_options:
                fastest_dt, fastest_data = min(fast_options, key=lambda x: x[1]['execution_time_s'])
                recommendations.append(f"Use dt={fastest_dt}ms for optimal speed/accuracy balance")

        recommendations.extend([
            "Consider adaptive time stepping to reduce solve frequency",
            "Investigate caching hydraulic solutions between similar time steps",
            "Implement early termination when steady-state is reached"
        ])

        return recommendations

    def _generate_tuning_recommendations(self,
                                       baseline_comparisons: List[TimeStateModelComparison],
                                       sensitivity: Dict[str, ParameterSensitivityResults]) -> Dict[str, Any]:
        """Generate comprehensive tuning recommendations."""

        # Analyze overall time-state performance
        improvements = [comp.improvement_vs_linear for comp in baseline_comparisons
                       if np.isfinite(comp.improvement_vs_linear)]

        avg_improvement = np.mean(improvements) if improvements else 0

        # Identify most sensitive parameters
        param_importance = {name: result.improvement_factor
                           for name, result in sensitivity.items()
                           if np.isfinite(result.improvement_factor)}

        sorted_params = sorted(param_importance.items(), key=lambda x: x[1], reverse=True)

        recommendations = {
            "overall_performance": {
                "average_improvement_vs_linear": avg_improvement,
                "performance_assessment": self._assess_performance(avg_improvement),
                "time_penalty_acceptable": np.mean([comp.time_penalty_factor for comp in baseline_comparisons]) < 5.0
            },
            "priority_parameters": sorted_params[:3],  # Top 3 most important
            "tuning_suggestions": self._generate_tuning_suggestions(sorted_params),
            "model_refinement_ideas": [
                "Consider flow-dependent phase timing (tau_pinch vs Qw)",
                "Investigate pressure-dependent conductance reduction",
                "Implement adaptive simulation time based on convergence",
                "Add position-dependent phase parameters if spatial patterns exist"
            ]
        }

        return recommendations

    def _assess_performance(self, avg_improvement: float) -> str:
        """Assess overall model performance."""
        if avg_improvement > 0.2:
            return "EXCELLENT - significant improvement over linear model"
        elif avg_improvement > 0.1:
            return "GOOD - moderate improvement over linear model"
        elif avg_improvement > 0.0:
            return "FAIR - slight improvement over linear model"
        else:
            return "POOR - no improvement over linear model"

    def _generate_tuning_suggestions(self, sorted_params: List[Tuple[str, float]]) -> List[str]:
        """Generate specific tuning suggestions based on sensitivity analysis."""
        suggestions = []

        for param_name, improvement in sorted_params[:3]:
            if improvement > 0.1:
                suggestions.append(f"Focus on optimizing {param_name} - high sensitivity detected")
            elif improvement > 0.05:
                suggestions.append(f"Consider fine-tuning {param_name} - moderate sensitivity")

        if not suggestions:
            suggestions.append("No parameters show strong sensitivity - model may be robust or need structural changes")

        return suggestions

    def _print_summary(self, results: TimeStateResults) -> None:
        """Print summary of time-state evaluation results."""
        print("\n" + "=" * 70)
        print("TIME-STATE MODEL EVALUATION SUMMARY")
        print("=" * 70)

        # Baseline comparison summary
        improvements = [comp.improvement_vs_linear for comp in results.baseline_comparisons]
        time_penalties = [comp.time_penalty_factor for comp in results.baseline_comparisons]

        print(f"Baseline Comparison:")
        print(f"  Average improvement vs linear: {np.mean(improvements)*100:+.1f}%")
        print(f"  Average time penalty: {np.mean(time_penalties):.1f}x")

        # Parameter sensitivity summary
        print(f"\nParameter Sensitivity:")
        if results.parameter_sensitivity:
            for param_name, sensitivity in results.parameter_sensitivity.items():
                if np.isfinite(sensitivity.improvement_factor):
                    print(f"  {param_name}: {sensitivity.improvement_factor*100:+.1f}% max improvement "
                          f"(optimal: {sensitivity.optimal_value})")

        # Recommendations
        if results.tuning_recommendations:
            overall = results.tuning_recommendations.get("overall_performance", {})
            assessment = overall.get("performance_assessment", "UNKNOWN")
            print(f"\nOverall Assessment: {assessment}")

            priority_params = results.tuning_recommendations.get("priority_parameters", [])
            if priority_params:
                print(f"Priority parameters for tuning:")
                for param_name, importance in priority_params:
                    print(f"  1. {param_name} (importance: {importance*100:.1f}%)")