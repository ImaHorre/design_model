#!/usr/bin/env python3
"""
Comprehensive validation test suite for time-state hydraulic models.

This suite validates:
1. Backward compatibility - steady model unchanged
2. Model progression - logical frequency reduction sequence
3. Parameter sensitivity - effect of key parameters
4. Performance regression - execution time bounds
5. Physics consistency - volume conservation, etc.
"""

import time
from typing import Dict, List, Tuple, Any
import numpy as np

from stepgen.config import load_config, mlhr_to_m3s, mbar_to_pa
from stepgen.models.hydraulic_models import HydraulicModelRegistry
from stepgen.models.model_comparison import ModelComparator


class ValidationSuite:
    """Comprehensive validation test suite for hydraulic models."""

    def __init__(self):
        """Initialize validation suite."""
        self.comparator = ModelComparator()
        self.test_results = {}

    def run_all_tests(self, config_file: str = "test_config_small.yaml") -> Dict[str, Any]:
        """
        Run complete validation suite.

        Parameters
        ----------
        config_file : str
            Configuration file for testing

        Returns
        -------
        Dict[str, Any]
            Complete test results
        """
        print("Time-State Model Validation Suite")
        print("=" * 50)
        print(f"Configuration: {config_file}")
        print()

        # Load test configuration
        try:
            config = load_config(config_file)
            print(f"✓ Configuration loaded: {config.geometry.Nmc} rungs")
        except Exception as e:
            print(f"✗ Failed to load configuration: {e}")
            return {"error": str(e)}

        # Standard test conditions
        Po_Pa = mbar_to_pa(300.0)
        Qw_m3s = mlhr_to_m3s(1.5)
        P_out_Pa = mbar_to_pa(0.0)

        # Run test categories
        results = {
            "configuration": config_file,
            "test_conditions": {
                "Po_mbar": 300.0,
                "Qw_mlhr": 1.5,
                "P_out_mbar": 0.0
            },
            "tests": {}
        }

        print("Running validation tests...")
        print()

        # Test 1: Backward compatibility
        results["tests"]["backward_compatibility"] = self.test_backward_compatibility(config, Po_Pa, Qw_m3s, P_out_Pa)

        # Test 2: Model progression
        results["tests"]["model_progression"] = self.test_model_progression(config, Po_Pa, Qw_m3s, P_out_Pa)

        # Test 3: Parameter sensitivity
        results["tests"]["parameter_sensitivity"] = self.test_parameter_sensitivity(config, Po_Pa, Qw_m3s, P_out_Pa)

        # Test 4: Performance regression
        results["tests"]["performance_regression"] = self.test_performance_regression(config, Po_Pa, Qw_m3s, P_out_Pa)

        # Test 5: Physics consistency
        results["tests"]["physics_consistency"] = self.test_physics_consistency(config, Po_Pa, Qw_m3s, P_out_Pa)

        # Generate summary
        results["summary"] = self.generate_test_summary(results["tests"])

        return results

    def test_backward_compatibility(self, config, Po_Pa, Qw_m3s, P_out_Pa) -> Dict[str, Any]:
        """Test that steady-state model produces consistent results."""
        print("1. Backward Compatibility Test")
        print("-" * 30)

        try:
            # Run steady model multiple times
            frequencies = []
            for i in range(3):
                model = HydraulicModelRegistry.get_model("steady")
                result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)
                freq = np.mean(result.frequency_hz)
                frequencies.append(freq)

            # Check consistency
            freq_std = np.std(frequencies)
            freq_mean = np.mean(frequencies)
            consistency = freq_std < 0.01 * freq_mean  # < 1% variation

            test_result = {
                "passed": consistency,
                "frequencies": frequencies,
                "mean_frequency": freq_mean,
                "std_frequency": freq_std,
                "consistency_pct": (freq_std / freq_mean * 100) if freq_mean > 0 else 0
            }

            status = "PASS" if consistency else "FAIL"
            print(f"  Multiple runs: {frequencies}")
            print(f"  Consistency: {freq_std/freq_mean*100:.3f}% variation")
            print(f"  Result: {status}")
            print()

            return test_result

        except Exception as e:
            print(f"  ERROR: {e}")
            print()
            return {"passed": False, "error": str(e)}

    def test_model_progression(self, config, Po_Pa, Qw_m3s, P_out_Pa) -> Dict[str, Any]:
        """Test logical progression of frequency reduction across models."""
        print("2. Model Progression Test")
        print("-" * 30)

        models = ["steady", "duty_factor", "time_state"]
        frequencies = {}
        errors = {}

        # Test each model
        for model_name in models:
            try:
                # Adjust simulation time for time-state models
                if "time_state" in model_name:
                    original_time = getattr(config.droplet_model, 'simulation_time_ms', 5000.0)
                    config.droplet_model.__dict__['simulation_time_ms'] = 500.0  # Short for testing

                model = HydraulicModelRegistry.get_model(model_name)
                result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)
                frequencies[model_name] = np.mean(result.frequency_hz)

                # Restore simulation time
                if "time_state" in model_name:
                    config.droplet_model.__dict__['simulation_time_ms'] = original_time

                print(f"  {model_name}: {frequencies[model_name]:.2f} Hz")

            except Exception as e:
                errors[model_name] = str(e)
                print(f"  {model_name}: ERROR - {e}")

        # Check progression
        progression_valid = True
        reduction_factors = {}

        if "steady" in frequencies and "duty_factor" in frequencies:
            reduction_factors["duty_factor"] = frequencies["steady"] / frequencies["duty_factor"]
            expected_reduction = 1.0 / config.droplet_model.duty_factor_phi
            duty_factor_valid = 3.0 < reduction_factors["duty_factor"] < 8.0  # Reasonable range
            if not duty_factor_valid:
                progression_valid = False
            print(f"  Duty factor reduction: {reduction_factors['duty_factor']:.1f}x (expected ~{expected_reduction:.1f}x)")

        if "steady" in frequencies and "time_state" in frequencies:
            reduction_factors["time_state"] = frequencies["steady"] / frequencies["time_state"]
            time_state_valid = reduction_factors["time_state"] >= 1.0  # Should reduce frequency
            if not time_state_valid:
                progression_valid = False
            print(f"  Time-state reduction: {reduction_factors['time_state']:.1f}x")

        status = "PASS" if progression_valid else "FAIL"
        print(f"  Result: {status}")
        print()

        return {
            "passed": progression_valid,
            "frequencies": frequencies,
            "reduction_factors": reduction_factors,
            "errors": errors
        }

    def test_parameter_sensitivity(self, config, Po_Pa, Qw_m3s, P_out_Pa) -> Dict[str, Any]:
        """Test sensitivity to key time-state parameters."""
        print("3. Parameter Sensitivity Test")
        print("-" * 30)

        # Test time-state model with different parameters
        base_params = {
            "tau_pinch_ms": config.droplet_model.tau_pinch_ms,
            "tau_reset_ms": config.droplet_model.tau_reset_ms,
            "g_pinch_frac": config.droplet_model.g_pinch_frac
        }

        # Parameter variations to test
        param_tests = {
            "tau_pinch_ms": [25.0, 50.0, 100.0],  # Pinch duration
            "g_pinch_frac": [0.001, 0.01, 0.1],   # Pinch conductance
        }

        results = {}

        for param_name, values in param_tests.items():
            results[param_name] = {}
            print(f"  Testing {param_name}:")

            for value in values:
                try:
                    # Set parameter
                    config.droplet_model.__dict__[param_name] = value
                    config.droplet_model.__dict__['simulation_time_ms'] = 300.0  # Short test

                    # Run model
                    model = HydraulicModelRegistry.get_model("time_state")
                    result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)
                    freq = np.mean(result.frequency_hz)
                    duty = np.mean(result.duty_factor) if result.duty_factor is not None else 1.0

                    results[param_name][value] = {"frequency": freq, "duty_factor": duty}
                    print(f"    {param_name}={value}: {freq:.2f} Hz, duty={duty:.3f}")

                except Exception as e:
                    results[param_name][value] = {"error": str(e)}
                    print(f"    {param_name}={value}: ERROR - {e}")

            # Restore base parameter
            config.droplet_model.__dict__[param_name] = base_params[param_name]

        # Check sensitivity
        sensitivity_detected = False
        for param_name, param_results in results.items():
            frequencies = [r["frequency"] for r in param_results.values() if "frequency" in r]
            if len(frequencies) > 1:
                freq_range = max(frequencies) - min(frequencies)
                if freq_range > 0.1 * np.mean(frequencies):  # > 10% variation
                    sensitivity_detected = True

        status = "PASS" if sensitivity_detected else "WARN"
        print(f"  Sensitivity detected: {sensitivity_detected}")
        print(f"  Result: {status}")
        print()

        # Restore all base parameters
        for param_name, value in base_params.items():
            config.droplet_model.__dict__[param_name] = value

        return {
            "passed": True,  # This test is informational
            "sensitivity_detected": sensitivity_detected,
            "parameter_results": results
        }

    def test_performance_regression(self, config, Po_Pa, Qw_m3s, P_out_Pa) -> Dict[str, Any]:
        """Test execution time performance."""
        print("4. Performance Regression Test")
        print("-" * 30)

        performance_targets = {
            "steady": 1.0,          # Should be very fast
            "duty_factor": 1.0,     # Should be similar to steady
            "time_state": 30.0,     # Time integration - can be slower
        }

        execution_times = {}
        performance_ok = True

        for model_name, max_time in performance_targets.items():
            try:
                # Adjust simulation for fair comparison
                if "time_state" in model_name:
                    config.droplet_model.__dict__['simulation_time_ms'] = 200.0

                start_time = time.time()
                model = HydraulicModelRegistry.get_model(model_name)
                result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)
                execution_time = time.time() - start_time

                execution_times[model_name] = execution_time
                within_target = execution_time <= max_time

                status_symbol = "✓" if within_target else "✗"
                print(f"  {model_name}: {execution_time:.2f}s (target: <{max_time}s) {status_symbol}")

                if not within_target:
                    performance_ok = False

            except Exception as e:
                execution_times[model_name] = float('inf')
                performance_ok = False
                print(f"  {model_name}: ERROR - {e}")

        status = "PASS" if performance_ok else "WARN"
        print(f"  Result: {status}")
        print()

        return {
            "passed": performance_ok,
            "execution_times": execution_times,
            "performance_targets": performance_targets
        }

    def test_physics_consistency(self, config, Po_Pa, Qw_m3s, P_out_Pa) -> Dict[str, Any]:
        """Test physical consistency of models."""
        print("5. Physics Consistency Test")
        print("-" * 30)

        consistency_checks = []

        try:
            # Test 1: Duty factors should be <= 1.0
            for model_name in ["duty_factor", "time_state"]:
                try:
                    if "time_state" in model_name:
                        config.droplet_model.__dict__['simulation_time_ms'] = 200.0

                    model = HydraulicModelRegistry.get_model(model_name)
                    result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

                    if result.duty_factor is not None:
                        max_duty = np.max(result.duty_factor)
                        duty_valid = max_duty <= 1.01  # Allow small numerical error
                        consistency_checks.append({
                            "test": f"{model_name}_duty_factor_bounds",
                            "passed": duty_valid,
                            "value": max_duty,
                            "description": f"Duty factor <= 1.0"
                        })
                        print(f"  {model_name} duty factor: {max_duty:.3f} ≤ 1.0 {'✓' if duty_valid else '✗'}")

                except Exception as e:
                    consistency_checks.append({
                        "test": f"{model_name}_duty_factor_bounds",
                        "passed": False,
                        "error": str(e)
                    })

            # Test 2: Frequencies should be non-negative
            for model_name in ["steady", "duty_factor", "time_state"]:
                try:
                    if "time_state" in model_name:
                        config.droplet_model.__dict__['simulation_time_ms'] = 200.0

                    model = HydraulicModelRegistry.get_model(model_name)
                    result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

                    min_freq = np.min(result.frequency_hz)
                    freq_valid = min_freq >= 0.0
                    consistency_checks.append({
                        "test": f"{model_name}_frequency_positive",
                        "passed": freq_valid,
                        "value": min_freq,
                        "description": f"Frequency >= 0.0"
                    })
                    print(f"  {model_name} frequency: {min_freq:.3f} ≥ 0.0 {'✓' if freq_valid else '✗'}")

                except Exception as e:
                    consistency_checks.append({
                        "test": f"{model_name}_frequency_positive",
                        "passed": False,
                        "error": str(e)
                    })

            all_passed = all(check["passed"] for check in consistency_checks)
            status = "PASS" if all_passed else "FAIL"
            print(f"  Result: {status}")
            print()

        except Exception as e:
            print(f"  ERROR: {e}")
            print()
            return {"passed": False, "error": str(e)}

        return {
            "passed": all_passed,
            "consistency_checks": consistency_checks
        }

    def generate_test_summary(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate overall test summary."""
        total_tests = len(test_results)
        passed_tests = sum(1 for result in test_results.values() if result.get("passed", False))

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "success_rate": passed_tests / total_tests if total_tests > 0 else 0,
            "overall_status": "PASS" if passed_tests == total_tests else "PARTIAL" if passed_tests > 0 else "FAIL"
        }

    def print_summary(self, results: Dict[str, Any]) -> None:
        """Print validation summary."""
        print("=" * 50)
        print("VALIDATION SUMMARY")
        print("=" * 50)

        summary = results["summary"]
        print(f"Tests run: {summary['total_tests']}")
        print(f"Tests passed: {summary['passed_tests']}")
        print(f"Success rate: {summary['success_rate']*100:.1f}%")
        print(f"Overall status: {summary['overall_status']}")
        print()

        # Test breakdown
        for test_name, test_result in results["tests"].items():
            status = "PASS" if test_result.get("passed", False) else "FAIL"
            print(f"  {test_name}: {status}")

        print()


if __name__ == "__main__":
    # Run validation suite
    suite = ValidationSuite()
    results = suite.run_all_tests("test_config_small.yaml")
    suite.print_summary(results)