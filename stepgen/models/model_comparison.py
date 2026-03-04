"""
stepgen.models.model_comparison
===============================
Multi-model comparison and validation framework.

This module provides comprehensive comparison functionality for all hydraulic
models, including performance metrics, JSON export, and validation testing.

Features:
- Side-by-side model comparison
- JSON export of results
- Performance timing
- Parameter sensitivity analysis
- Validation against experimental data
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

from stepgen.models.hydraulic_models import HydraulicModelRegistry

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


@dataclass
class ModelResult:
    """Results from a single hydraulic model run."""
    model_name: str
    frequency_hz: float
    frequency_std: float
    duty_factor: float
    duty_factor_std: float
    execution_time_s: float
    n_events_total: int
    phase_distribution: Dict[str, float]
    model_specific_data: Dict[str, Any]


@dataclass
class ComparisonResults:
    """Complete comparison results across all models."""
    config_file: str
    operating_conditions: Dict[str, float]
    model_results: List[ModelResult]
    frequency_progression: Dict[str, float]
    reduction_factors: Dict[str, float]
    experimental_comparison: Optional[Dict[str, Any]] = None


class ModelComparator:
    """
    Multi-model comparison framework for hydraulic models.

    Provides comprehensive testing and validation across all model types
    with detailed output and JSON export capabilities.
    """

    def __init__(self):
        """Initialize the model comparator."""
        self.available_models = HydraulicModelRegistry.list_models()

    def compare_all_models(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float,
        models: Optional[List[str]] = None,
        experimental_freq: Optional[float] = None
    ) -> ComparisonResults:
        """
        Compare all specified hydraulic models.

        Parameters
        ----------
        config : DeviceConfig
            Device configuration
        Po_Pa : float
            Oil inlet pressure [Pa]
        Qw_m3s : float
            Water inlet flow rate [m³/s]
        P_out_Pa : float
            Outlet pressure [Pa]
        models : list of str, optional
            Models to compare. If None, compares all available models.
        experimental_freq : float, optional
            Experimental frequency for comparison [Hz]

        Returns
        -------
        ComparisonResults
            Complete comparison results
        """
        if models is None:
            models = self.available_models.copy()

        # Ensure models are tested in logical order
        model_order = ["steady", "duty_factor", "time_state", "time_state_filling"]
        ordered_models = [m for m in model_order if m in models]
        ordered_models.extend([m for m in models if m not in model_order])

        model_results = []
        frequency_progression = {}

        print(f"Multi-Model Comparison ({len(ordered_models)} models)")
        print("=" * 60)

        for model_name in ordered_models:
            try:
                print(f"Testing {model_name}...")

                # Adjust simulation parameters for time-state models
                original_sim_time = getattr(config.droplet_model, 'simulation_time_ms', 5000.0)
                if "time_state" in model_name:
                    # Use shorter simulation for large devices
                    sim_time = 1500.0 if config.geometry.Nmc > 100 else original_sim_time
                    config.droplet_model.__dict__['simulation_time_ms'] = sim_time

                # Time the model execution
                start_time = time.time()

                model = HydraulicModelRegistry.get_model(model_name)
                result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

                execution_time = time.time() - start_time

                # Restore original simulation time
                if "time_state" in model_name:
                    config.droplet_model.__dict__['simulation_time_ms'] = original_sim_time

                # Extract results
                frequencies = result.frequency_hz
                duty_factors = result.duty_factor if result.duty_factor is not None else np.ones_like(frequencies)

                mean_freq = np.mean(frequencies)
                std_freq = np.std(frequencies)
                mean_duty = np.mean(duty_factors)
                std_duty = np.std(duty_factors)

                # Count total droplet events
                n_events = 0
                if result.time_series and "droplet_events" in result.time_series:
                    n_events = sum(len(events) for events in result.time_series["droplet_events"])

                # Get phase distribution if available
                phase_dist = {}
                if result.time_series and "final_phase_summary" in result.time_series:
                    phase_summary = result.time_series["final_phase_summary"]
                    phase_dist = {
                        "frac_open": phase_summary.get("frac_open", 1.0),
                        "frac_pinch": phase_summary.get("frac_pinch", 0.0),
                        "frac_reset": phase_summary.get("frac_reset", 0.0)
                    }

                # Model-specific data
                model_specific = {}
                if result.time_series:
                    if "filling_mechanics" in result.time_series:
                        fm = result.time_series["filling_mechanics"]
                        if "volume_breakdown" in fm:
                            vb = fm["volume_breakdown"]
                            model_specific["volume_ratios"] = {
                                "refill_to_sphere": vb["V_refill"] / vb["V_sphere"] if vb["V_sphere"] > 0 else 0,
                                "total_to_sphere": vb["V_total"] / vb["V_sphere"] if vb["V_sphere"] > 0 else 1
                            }

                model_result = ModelResult(
                    model_name=model_name,
                    frequency_hz=mean_freq,
                    frequency_std=std_freq,
                    duty_factor=mean_duty,
                    duty_factor_std=std_duty,
                    execution_time_s=execution_time,
                    n_events_total=n_events,
                    phase_distribution=phase_dist,
                    model_specific_data=model_specific
                )

                model_results.append(model_result)
                frequency_progression[model_name] = mean_freq

                print(f"  Frequency: {mean_freq:.2f} ± {std_freq:.2f} Hz")
                print(f"  Duty factor: {mean_duty:.3f} ± {std_duty:.3f}")
                print(f"  Execution time: {execution_time:.2f}s")
                if n_events > 0:
                    print(f"  Events: {n_events}")
                print()

            except Exception as e:
                print(f"  ERROR: {e}")
                print()

        # Calculate reduction factors
        reduction_factors = {}
        if "steady" in frequency_progression:
            steady_freq = frequency_progression["steady"]
            for model_name, freq in frequency_progression.items():
                if freq > 0:
                    reduction_factors[model_name] = steady_freq / freq
                else:
                    reduction_factors[model_name] = float('inf')

        # Experimental comparison
        experimental_comparison = None
        if experimental_freq is not None:
            experimental_comparison = {}
            for model_name, freq in frequency_progression.items():
                if freq > 0:
                    error_factor = freq / experimental_freq
                    experimental_comparison[model_name] = {
                        "frequency_ratio": error_factor,
                        "error_description": self._categorize_error(error_factor)
                    }

        # Operating conditions
        operating_conditions = {
            "Po_Pa": Po_Pa,
            "Qw_m3s": Qw_m3s,
            "P_out_Pa": P_out_Pa,
            "Po_mbar": Po_Pa * 1e-2,
            "Qw_mlhr": Qw_m3s / (1e-6 / 3600),  # Convert back to mL/hr
            "P_out_mbar": P_out_Pa * 1e-2
        }

        return ComparisonResults(
            config_file="comparison",
            operating_conditions=operating_conditions,
            model_results=model_results,
            frequency_progression=frequency_progression,
            reduction_factors=reduction_factors,
            experimental_comparison=experimental_comparison
        )

    def _categorize_error(self, error_factor: float) -> str:
        """Categorize error factor for experimental comparison."""
        if 0.8 <= error_factor <= 1.2:
            return "EXCELLENT"
        elif 0.5 <= error_factor <= 2.0:
            return "GOOD"
        elif 0.2 <= error_factor <= 5.0:
            return "ACCEPTABLE"
        else:
            return "NEEDS_IMPROVEMENT"

    def print_summary(self, results: ComparisonResults) -> None:
        """Print a formatted summary of comparison results."""
        print("=" * 60)
        print("MODEL COMPARISON SUMMARY")
        print("=" * 60)

        # Operating conditions
        oc = results.operating_conditions
        print(f"Operating conditions:")
        print(f"  Po = {oc['Po_mbar']:.1f} mbar, Qw = {oc['Qw_mlhr']:.1f} mL/hr")
        print()

        # Results table
        print(f"{'Model':<20} {'Freq [Hz]':<12} {'Reduction':<10} {'Duty Factor':<12} {'Time [s]':<10}")
        print("-" * 70)

        for result in results.model_results:
            reduction = results.reduction_factors.get(result.model_name, 1.0)
            reduction_str = f"{reduction:.1f}x" if reduction != float('inf') else "∞"

            print(f"{result.model_name:<20} {result.frequency_hz:<12.2f} {reduction_str:<10} "
                  f"{result.duty_factor:<12.3f} {result.execution_time_s:<10.1f}")

        # Experimental comparison
        if results.experimental_comparison:
            print()
            print("Experimental comparison:")
            for model_name, comparison in results.experimental_comparison.items():
                ratio = comparison["frequency_ratio"]
                desc = comparison["error_description"]
                print(f"  {model_name:<20}: {ratio:.2f}x error ({desc})")

        print()

    def export_json(self, results: ComparisonResults, filename: str) -> None:
        """Export comparison results to JSON file."""
        # Convert to dictionary for JSON serialization
        results_dict = asdict(results)

        # Convert numpy arrays to lists if present
        for result in results_dict["model_results"]:
            for key, value in result.items():
                if isinstance(value, np.ndarray):
                    result[key] = value.tolist()

        with open(filename, 'w') as f:
            json.dump(results_dict, f, indent=2)

        print(f"Results exported to {filename}")


def compare_models_cli(
    config_file: str,
    Po_mbar: float = 300.0,
    Qw_mlhr: float = 1.5,
    P_out_mbar: float = 0.0,
    experimental_hz: Optional[float] = None,
    export_json: bool = False,
    models: Optional[List[str]] = None
) -> ComparisonResults:
    """
    Command-line interface for model comparison.

    Parameters
    ----------
    config_file : str
        Path to device configuration file
    Po_mbar : float
        Oil inlet pressure [mbar]
    Qw_mlhr : float
        Water inlet flow rate [mL/hr]
    P_out_mbar : float
        Outlet pressure [mbar]
    experimental_hz : float, optional
        Experimental frequency for comparison [Hz]
    export_json : bool
        Whether to export results to JSON
    models : list of str, optional
        Models to compare

    Returns
    -------
    ComparisonResults
        Comparison results
    """
    from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa

    # Load configuration
    config = load_config(config_file)

    # Convert units
    Po_Pa = mbar_to_pa(Po_mbar)
    Qw_m3s = mlhr_to_m3s(Qw_mlhr)
    P_out_Pa = mbar_to_pa(P_out_mbar)

    # Run comparison
    comparator = ModelComparator()
    results = comparator.compare_all_models(
        config, Po_Pa, Qw_m3s, P_out_Pa, models, experimental_hz
    )

    # Print summary
    comparator.print_summary(results)

    # Export JSON if requested
    if export_json:
        json_filename = f"model_comparison_{config_file.replace('/', '_').replace('.yaml', '')}.json"
        comparator.export_json(results, json_filename)

    return results