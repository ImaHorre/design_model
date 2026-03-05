"""
stepgen.testing.experimental_test_suite
========================================
Main testing orchestrator for systematic experimental validation.

This module provides the ExperimentalTestSuite class that coordinates all testing
phases including duty factor analysis, time-state model evaluation, and performance
optimization against real experimental data.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np
import pandas as pd

from stepgen.config import load_config
from stepgen.io.experiments import load_experiments, compare_to_predictions, compute_compare_report
from stepgen.models.model_comparison import ModelComparator

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from stepgen.io.experiments import CompareReport

@dataclass
class OperatingCondition:
    """Represents a single operating condition from experimental data."""
    Po_mbar: float
    Qw_mlhr: float
    data: pd.DataFrame
    n_points: int = field(init=False)

    def __post_init__(self):
        self.n_points = len(self.data)


@dataclass
class TestSuiteResults:
    """Complete results from experimental test suite."""
    config_file: str
    experiment_file: str
    operating_conditions: List[OperatingCondition]
    duty_factor_analysis: Optional[Any] = None
    time_state_analysis: Optional[Any] = None
    pcap_verification: Optional[Any] = None
    performance_analysis: Optional[Any] = None
    execution_time_s: float = 0.0


class ExperimentalTestSuite:
    """
    Systematic testing framework for model validation against experimental data.

    Orchestrates comprehensive analysis including duty factor calibration,
    time-state model evaluation, Pcap verification, and performance optimization.
    """

    def __init__(self, config_file: str, experiment_file: str):
        """
        Initialize the test suite with configuration and experimental data.

        Parameters
        ----------
        config_file : str
            Path to device configuration YAML file
        experiment_file : str
            Path to experimental data CSV file
        """
        self.config_file = config_file
        self.experiment_file = experiment_file

        # Load data
        self.config = load_config(config_file)
        self.experiments_df = load_experiments(experiment_file)
        self.operating_conditions = self._extract_operating_conditions()

        # Initialize sub-analyzers
        self.model_comparator = ModelComparator()

        print(f"Initialized ExperimentalTestSuite:")
        print(f"  Config: {config_file}")
        print(f"  Data: {experiment_file}")
        print(f"  Operating conditions: {len(self.operating_conditions)}")
        print(f"  Total data points: {len(self.experiments_df)}")

    def _extract_operating_conditions(self) -> List[OperatingCondition]:
        """Extract unique operating conditions from experimental data."""
        conditions = []

        # Group by Po and Qw
        grouped = self.experiments_df.groupby(['Po_in_mbar', 'Qw_in_mlhr'])

        for (Po, Qw), group_data in grouped:
            condition = OperatingCondition(
                Po_mbar=Po,
                Qw_mlhr=Qw,
                data=group_data.copy()
            )
            conditions.append(condition)

        # Sort by Po, then Qw for consistent ordering
        conditions.sort(key=lambda c: (c.Po_mbar, c.Qw_mlhr))

        return conditions

    def run_comprehensive_analysis(self,
                                 include_duty_factor: bool = True,
                                 include_time_state: bool = True,
                                 include_pcap_verification: bool = True,
                                 include_performance: bool = True,
                                 output_dir: Optional[str] = None) -> TestSuiteResults:
        """
        Execute the complete testing pipeline.

        Parameters
        ----------
        include_duty_factor : bool
            Whether to run duty factor analysis
        include_time_state : bool
            Whether to run time-state model evaluation
        include_pcap_verification : bool
            Whether to run Pcap implementation verification
        include_performance : bool
            Whether to run performance analysis
        output_dir : str, optional
            Directory to save results and reports

        Returns
        -------
        TestSuiteResults
            Complete analysis results
        """
        start_time = time.time()

        print("=" * 80)
        print("COMPREHENSIVE EXPERIMENTAL TESTING")
        print("=" * 80)

        results = TestSuiteResults(
            config_file=self.config_file,
            experiment_file=self.experiment_file,
            operating_conditions=self.operating_conditions
        )

        # Phase 1: Baseline model comparison
        print("\nPhase 1: Baseline Model Comparison")
        print("-" * 40)
        baseline_results = self._run_baseline_comparison()

        # Phase 2: Duty Factor Analysis
        if include_duty_factor:
            print("\nPhase 2: Duty Factor Analysis")
            print("-" * 40)
            from .duty_factor_analyzer import DutyFactorAnalyzer
            duty_analyzer = DutyFactorAnalyzer(self.config, self.experiments_df)
            results.duty_factor_analysis = duty_analyzer.run_cross_condition_analysis()

        # Phase 3: Time-State Model Evaluation
        if include_time_state:
            print("\nPhase 3: Time-State Model Evaluation")
            print("-" * 40)
            from .time_state_evaluator import TimeStateEvaluator
            time_state_evaluator = TimeStateEvaluator(self.config, self.experiments_df)
            results.time_state_analysis = time_state_evaluator.run_evaluation()

        # Phase 4: Pcap Verification
        if include_pcap_verification:
            print("\nPhase 4: Pcap Tax Verification")
            print("-" * 40)
            from .pcap_verifier import PcapVerifier
            pcap_verifier = PcapVerifier(self.config, self.experiments_df)
            results.pcap_verification = pcap_verifier.verify_implementation()

        # Phase 5: Performance Analysis
        if include_performance:
            print("\nPhase 5: Performance Analysis")
            print("-" * 40)
            results.performance_analysis = self._run_performance_analysis()

        results.execution_time_s = time.time() - start_time

        # Generate reports if output directory provided
        if output_dir:
            self._generate_reports(results, output_dir)

        print(f"\nTotal execution time: {results.execution_time_s:.1f}s")
        print("Analysis complete!")

        return results

    def _run_baseline_comparison(self) -> Dict[str, Any]:
        """Run baseline comparison across all operating conditions."""
        baseline_results = {}

        for i, condition in enumerate(self.operating_conditions):
            print(f"  Condition {i+1}/{len(self.operating_conditions)}: "
                  f"Po={condition.Po_mbar}mbar, Qw={condition.Qw_mlhr}mL/hr "
                  f"({condition.n_points} points)")

            # Convert to SI units
            Po_Pa = condition.Po_mbar * 100.0  # mbar to Pa
            Qw_m3s = condition.Qw_mlhr / (1e6 / 3600.0)  # mL/hr to m³/s
            P_out_Pa = 0.0

            # Run all models
            comparison = self.model_comparator.compare_all_models(
                self.config, Po_Pa, Qw_m3s, P_out_Pa,
                models=['steady', 'duty_factor', 'time_state', 'time_state_filling']
            )

            # Compute experimental comparison
            comparison_df = compare_to_predictions(self.config, condition.data)
            report = compute_compare_report(comparison_df)

            baseline_results[f"condition_{i}"] = {
                "operating_condition": condition,
                "model_comparison": comparison,
                "experimental_report": report
            }

            print(f"    Frequency RMSE: {report.freq_rmse_hz:.2f} Hz")
            print(f"    Diameter RMSE: {report.diam_rmse_um:.2f} μm")

        return baseline_results

    def _run_performance_analysis(self) -> Dict[str, Any]:
        """Run performance analysis across all models."""
        print("  Profiling model execution times...")

        performance_results = {}

        # Test each model type with different parameters
        for model_name in ['steady', 'duty_factor', 'time_state', 'time_state_filling']:
            print(f"    Profiling {model_name}...")

            model_times = []
            for condition in self.operating_conditions[:2]:  # Test on first 2 conditions
                Po_Pa = condition.Po_mbar * 100.0
                Qw_m3s = condition.Qw_mlhr / (1e6 / 3600.0)

                start_time = time.time()
                try:
                    self.model_comparator.compare_all_models(
                        self.config, Po_Pa, Qw_m3s, 0.0, models=[model_name]
                    )
                    exec_time = time.time() - start_time
                    model_times.append(exec_time)
                except Exception as e:
                    print(f"      Error with {model_name}: {e}")
                    model_times.append(float('inf'))

            performance_results[model_name] = {
                "mean_time_s": np.mean(model_times) if model_times else float('inf'),
                "times": model_times
            }

            if model_times and np.isfinite(np.mean(model_times)):
                print(f"      Average time: {np.mean(model_times):.2f}s")

        return performance_results

    def _generate_reports(self, results: TestSuiteResults, output_dir: str) -> None:
        """Generate comprehensive reports and visualizations."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        print(f"\nGenerating reports in {output_dir}/...")

        # Export main results as JSON
        results_dict = self._results_to_dict(results)
        json_path = output_path / "experimental_test_results.json"
        with open(json_path, 'w') as f:
            json.dump(results_dict, f, indent=2, default=str)
        print(f"  Exported results: {json_path}")

        # Generate summary report
        summary_path = output_path / "test_summary.md"
        self._generate_summary_report(results, summary_path)
        print(f"  Generated summary: {summary_path}")

    def _results_to_dict(self, results: TestSuiteResults) -> Dict[str, Any]:
        """Convert results to JSON-serializable dictionary."""
        return {
            "config_file": results.config_file,
            "experiment_file": results.experiment_file,
            "n_operating_conditions": len(results.operating_conditions),
            "operating_conditions": [
                {
                    "Po_mbar": c.Po_mbar,
                    "Qw_mlhr": c.Qw_mlhr,
                    "n_points": c.n_points
                } for c in results.operating_conditions
            ],
            "execution_time_s": results.execution_time_s,
            "duty_factor_analysis": self._serialize_analysis(results.duty_factor_analysis),
            "time_state_analysis": self._serialize_analysis(results.time_state_analysis),
            "pcap_verification": self._serialize_analysis(results.pcap_verification),
            "performance_analysis": results.performance_analysis
        }

    def _serialize_analysis(self, analysis: Any) -> Any:
        """Serialize analysis results for JSON export."""
        if analysis is None:
            return None
        if hasattr(analysis, '__dict__'):
            return {k: self._serialize_analysis(v) for k, v in analysis.__dict__.items()}
        if isinstance(analysis, (list, tuple)):
            return [self._serialize_analysis(item) for item in analysis]
        if isinstance(analysis, dict):
            return {k: self._serialize_analysis(v) for k, v in analysis.items()}
        if isinstance(analysis, (np.ndarray, pd.Series, pd.DataFrame)):
            return analysis.tolist() if hasattr(analysis, 'tolist') else str(analysis)
        return analysis

    def _generate_summary_report(self, results: TestSuiteResults, output_path: Path) -> None:
        """Generate a markdown summary report."""
        with open(output_path, 'w') as f:
            f.write("# Experimental Testing Summary\n\n")
            f.write(f"**Configuration**: {results.config_file}\n")
            f.write(f"**Experimental Data**: {results.experiment_file}\n")
            f.write(f"**Execution Time**: {results.execution_time_s:.1f} seconds\n\n")

            f.write("## Operating Conditions\n\n")
            for i, condition in enumerate(results.operating_conditions):
                f.write(f"{i+1}. Po={condition.Po_mbar} mbar, Qw={condition.Qw_mlhr} mL/hr "
                       f"({condition.n_points} data points)\n")

            f.write("\n## Analysis Results\n\n")

            if results.duty_factor_analysis:
                f.write("- ✓ Duty Factor Analysis completed\n")
            else:
                f.write("- ✗ Duty Factor Analysis skipped\n")

            if results.time_state_analysis:
                f.write("- ✓ Time-State Model Evaluation completed\n")
            else:
                f.write("- ✗ Time-State Model Evaluation skipped\n")

            if results.pcap_verification:
                f.write("- ✓ Pcap Verification completed\n")
            else:
                f.write("- ✗ Pcap Verification skipped\n")

            if results.performance_analysis:
                f.write("- ✓ Performance Analysis completed\n")
            else:
                f.write("- ✗ Performance Analysis skipped\n")


def run_experimental_testing_cli(
    config_file: str,
    experiment_file: str,
    output_dir: str = "test_results",
    include_duty_factor: bool = True,
    include_time_state: bool = True,
    include_pcap: bool = True,
    include_performance: bool = True
) -> TestSuiteResults:
    """
    Command-line interface for experimental testing.

    Parameters
    ----------
    config_file : str
        Path to device configuration file
    experiment_file : str
        Path to experimental data CSV
    output_dir : str
        Directory for results output
    include_duty_factor : bool
        Include duty factor analysis
    include_time_state : bool
        Include time-state model evaluation
    include_pcap : bool
        Include Pcap verification
    include_performance : bool
        Include performance analysis

    Returns
    -------
    TestSuiteResults
        Complete test results
    """
    suite = ExperimentalTestSuite(config_file, experiment_file)

    return suite.run_comprehensive_analysis(
        include_duty_factor=include_duty_factor,
        include_time_state=include_time_state,
        include_pcap_verification=include_pcap,
        include_performance=include_performance,
        output_dir=output_dir
    )