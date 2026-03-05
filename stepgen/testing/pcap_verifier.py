"""
stepgen.testing.pcap_verifier
=============================
Verification of Pcap tax implementation across model types.

This module provides the PcapVerifier class for ensuring that time-state models
implement capillary pressure thresholds consistently with the linear model.
Verifies that deltaP over rungs is properly depleted by Pcap.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from stepgen.models.model_comparison import ModelComparator
from stepgen.models.generator import iterative_solve, classify_rungs, RungRegime

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


@dataclass
class PcapTestCondition:
    """Test condition for Pcap verification."""
    Po_mbar: float
    Qw_mlhr: float
    description: str
    expected_regime: str  # "STATIONARY", "ACTIVE", "REVERSE"


@dataclass
class PcapModelResult:
    """Pcap verification results for a single model."""
    model_name: str
    regime_classifications: List[str]
    mean_frequency_hz: float
    pressure_drops_pa: List[float]
    pcap_corrected_drops_pa: List[float]  # deltaP - Pcap
    implementation_consistent: bool
    notes: str


@dataclass
class PcapVerificationResults:
    """Complete Pcap verification results."""
    test_conditions: List[PcapTestCondition]
    model_results: Dict[str, List[PcapModelResult]]
    cross_model_consistency: bool
    experimental_validation: Dict[str, Any]
    implementation_issues: List[str]
    execution_time_s: float = 0.0


class PcapVerifier:
    """
    Verification utility for Pcap tax implementation across model types.

    Ensures that time-state models implement capillary pressure thresholds
    the same way as the linear model, with proper pressure depletion.
    """

    def __init__(self, config: "DeviceConfig", experiments_df: pd.DataFrame):
        """
        Initialize the Pcap verifier.

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

        # Extract Pcap thresholds from config
        self.dP_cap_ow_pa = getattr(config.droplet_model, 'dP_cap_ow_Pa', 3500.0)  # Default 35 mbar
        self.dP_cap_wo_pa = getattr(config.droplet_model, 'dP_cap_wo_Pa', 3000.0)  # Default 30 mbar

        print(f"PcapVerifier initialized:")
        print(f"  dP_cap_ow: {self.dP_cap_ow_pa/100:.0f} mbar ({self.dP_cap_ow_pa:.0f} Pa)")
        print(f"  dP_cap_wo: {self.dP_cap_wo_pa/100:.0f} mbar ({self.dP_cap_wo_pa:.0f} Pa)")

    def verify_implementation(self) -> PcapVerificationResults:
        """
        Execute comprehensive Pcap implementation verification.

        Returns
        -------
        PcapVerificationResults
            Complete verification results
        """
        start_time = time.time()

        print("Running Pcap tax verification...")

        # Step 1: Define test conditions based on user's experimental findings
        test_conditions = self._define_test_conditions()

        # Step 2: Test each model's implementation
        print("Step 1: Testing model implementations...")
        model_results = {}

        models_to_test = ['steady', 'duty_factor', 'time_state', 'time_state_filling']
        for model_name in models_to_test:
            print(f"  Testing {model_name}...")
            model_results[model_name] = self._test_model_pcap_implementation(model_name, test_conditions)

        # Step 3: Check cross-model consistency
        print("Step 2: Checking cross-model consistency...")
        cross_model_consistency = self._check_cross_model_consistency(model_results)

        # Step 4: Validate against experimental thresholds
        print("Step 3: Validating against experimental data...")
        experimental_validation = self._validate_experimental_thresholds()

        # Step 5: Identify implementation issues
        implementation_issues = self._identify_implementation_issues(model_results, cross_model_consistency)

        results = PcapVerificationResults(
            test_conditions=test_conditions,
            model_results=model_results,
            cross_model_consistency=cross_model_consistency,
            experimental_validation=experimental_validation,
            implementation_issues=implementation_issues,
            execution_time_s=time.time() - start_time
        )

        print(f"Pcap verification complete in {results.execution_time_s:.1f}s")
        self._print_summary(results)

        return results

    def _define_test_conditions(self) -> List[PcapTestCondition]:
        """Define test conditions based on user's experimental findings."""
        # User reported:
        # - At Qw=1mL/hr, Po=35mbar needed for stationary meniscus (0Hz)
        # - At Qw=5mL/hr, Po=50mbar needed for stationary meniscus (0Hz)

        return [
            PcapTestCondition(
                Po_mbar=35.0,
                Qw_mlhr=1.0,
                description="Critical threshold - Qw=1mL/hr",
                expected_regime="STATIONARY"
            ),
            PcapTestCondition(
                Po_mbar=50.0,
                Qw_mlhr=5.0,
                description="Critical threshold - Qw=5mL/hr",
                expected_regime="STATIONARY"
            ),
            PcapTestCondition(
                Po_mbar=30.0,
                Qw_mlhr=1.0,
                description="Below threshold - should be OFF/REVERSE",
                expected_regime="OFF"
            ),
            PcapTestCondition(
                Po_mbar=40.0,
                Qw_mlhr=1.0,
                description="Above threshold - should be ACTIVE",
                expected_regime="ACTIVE"
            ),
            PcapTestCondition(
                Po_mbar=60.0,
                Qw_mlhr=5.0,
                description="Above threshold - should be ACTIVE",
                expected_regime="ACTIVE"
            )
        ]

    def _test_model_pcap_implementation(self, model_name: str, test_conditions: List[PcapTestCondition]) -> List[PcapModelResult]:
        """Test Pcap implementation for a specific model."""
        results = []

        for condition in test_conditions:
            try:
                # Convert to SI units using standard utility functions
                from stepgen.config import mlhr_to_m3s, mbar_to_pa
                Po_Pa = mbar_to_pa(condition.Po_mbar)
                Qw_m3s = mlhr_to_m3s(condition.Qw_mlhr)
                P_out_Pa = 0.0

                # For linear model, use direct hydraulic solve to get detailed pressure info
                if model_name == 'steady':
                    result = self._test_linear_model_pcap(condition, Po_Pa, Qw_m3s)
                else:
                    result = self._test_other_model_pcap(model_name, condition, Po_Pa, Qw_m3s, P_out_Pa)

                results.append(result)

            except Exception as e:
                print(f"    Error testing {model_name} at {condition.description}: {e}")

                # Create error result
                error_result = PcapModelResult(
                    model_name=model_name,
                    regime_classifications=["ERROR"],
                    mean_frequency_hz=0.0,
                    pressure_drops_pa=[],
                    pcap_corrected_drops_pa=[],
                    implementation_consistent=False,
                    notes=f"Error: {e}"
                )
                results.append(error_result)

        return results

    def _test_linear_model_pcap(self, condition: PcapTestCondition, Po_Pa: float, Qw_m3s: float) -> PcapModelResult:
        """Test Pcap implementation in linear (steady) model using direct hydraulic solve."""

        # Use iterative solver to get detailed results
        sim_result = iterative_solve(self.config, Po_in_mbar=condition.Po_mbar, Qw_in_mlhr=condition.Qw_mlhr)

        # Calculate pressure drops
        pressure_drops = sim_result.P_oil - sim_result.P_water

        # Apply Pcap correction as done in linear model
        pcap_corrected_drops = pressure_drops - self.dP_cap_ow_pa

        # Classify regimes
        regimes = classify_rungs(pressure_drops, self.dP_cap_ow_pa, self.dP_cap_wo_pa)
        regime_names = [regime.name for regime in regimes]

        # Calculate frequency (simplified - use first active rung)
        from stepgen.models.droplets import droplet_frequency, droplet_diameter

        mean_frequency = 0.0
        active_rungs = [i for i, regime in enumerate(regimes) if regime == RungRegime.ACTIVE]
        if active_rungs and np.any(sim_result.Q_rungs > 0):
            droplet_diameter_m = droplet_diameter(self.config)
            active_flows = [sim_result.Q_rungs[i] for i in active_rungs if sim_result.Q_rungs[i] > 0]
            if active_flows:
                frequencies = [droplet_frequency(Q, droplet_diameter_m) for Q in active_flows]
                mean_frequency = np.mean(frequencies)

        # Check implementation consistency
        consistent = self._check_linear_implementation_consistency(pressure_drops, regimes)

        return PcapModelResult(
            model_name="steady",
            regime_classifications=regime_names,
            mean_frequency_hz=mean_frequency,
            pressure_drops_pa=pressure_drops.tolist(),
            pcap_corrected_drops_pa=pcap_corrected_drops.tolist(),
            implementation_consistent=consistent,
            notes=f"Linear model: {len(active_rungs)}/{len(regimes)} rungs ACTIVE"
        )

    def _test_other_model_pcap(self, model_name: str, condition: PcapTestCondition,
                              Po_Pa: float, Qw_m3s: float, P_out_Pa: float) -> PcapModelResult:
        """Test Pcap implementation for non-linear models."""

        # Run model comparison
        comparison = self.model_comparator.compare_all_models(
            self.config, Po_Pa, Qw_m3s, P_out_Pa, models=[model_name]
        )

        model_result = comparison.model_results[0]
        mean_frequency = model_result.frequency_hz

        # For time-state models, we can't easily extract per-rung pressures
        # Instead, we check if the model produces sensible results
        regime_estimate = self._estimate_regime_from_frequency(mean_frequency, condition.expected_regime)

        implementation_consistent = self._check_time_state_implementation_consistency(
            model_name, mean_frequency, condition
        )

        return PcapModelResult(
            model_name=model_name,
            regime_classifications=[regime_estimate],
            mean_frequency_hz=mean_frequency,
            pressure_drops_pa=[],  # Not available for time-state models
            pcap_corrected_drops_pa=[],  # Not available for time-state models
            implementation_consistent=implementation_consistent,
            notes=f"{model_name}: freq={mean_frequency:.2f}Hz, estimated regime={regime_estimate}"
        )

    def _estimate_regime_from_frequency(self, frequency: float, expected_regime: str) -> str:
        """Estimate regime from frequency output."""
        if frequency < 0.1:  # Very low frequency
            return "OFF" if expected_regime in ["STATIONARY", "OFF"] else "UNKNOWN"
        elif frequency < 1.0:  # Low frequency
            return "MARGINAL"
        else:  # High frequency
            return "ACTIVE"

    def _check_linear_implementation_consistency(self, pressure_drops: np.ndarray, regimes: List) -> bool:
        """Check if linear model implements Pcap correctly."""
        # Verify that regimes are classified correctly based on pressure drops
        consistent = True

        for i, (dP, regime) in enumerate(zip(pressure_drops, regimes)):
            if regime == RungRegime.ACTIVE:
                # Should have dP > dP_cap_ow
                if dP <= self.dP_cap_ow_pa:
                    consistent = False
            elif regime == RungRegime.REVERSE:
                # Should have dP < -dP_cap_wo
                if dP >= -self.dP_cap_wo_pa:
                    consistent = False
            elif regime == RungRegime.OFF:
                # Should be between thresholds
                if not (-self.dP_cap_wo_pa <= dP <= self.dP_cap_ow_pa):
                    consistent = False

        return consistent

    def _check_time_state_implementation_consistency(self, model_name: str, frequency: float,
                                                   condition: PcapTestCondition) -> bool:
        """Check if time-state model implementation is consistent with expected behavior."""
        # Simple consistency check based on expected vs actual behavior
        if condition.expected_regime == "STATIONARY" or condition.expected_regime == "OFF":
            return frequency < 0.5  # Expect low/zero frequency
        elif condition.expected_regime == "ACTIVE":
            return frequency > 0.5  # Expect reasonable frequency
        else:
            return True  # Unknown expectation

    def _check_cross_model_consistency(self, model_results: Dict[str, List[PcapModelResult]]) -> bool:
        """Check if all models give consistent regime classifications."""
        if len(model_results) < 2:
            return True

        # Compare regime classifications across models for each test condition
        n_conditions = len(next(iter(model_results.values())))

        for i in range(n_conditions):
            # Get regime from linear model as reference
            if 'steady' in model_results:
                reference_regimes = model_results['steady'][i].regime_classifications
                if not reference_regimes:
                    continue

                reference_freq = model_results['steady'][i].mean_frequency_hz

                # Check other models
                for model_name, results in model_results.items():
                    if model_name == 'steady' or i >= len(results):
                        continue

                    model_freq = results[i].mean_frequency_hz
                    freq_consistent = self._frequencies_consistent(reference_freq, model_freq)

                    if not freq_consistent:
                        print(f"    Inconsistency: {model_name} freq={model_freq:.2f}Hz vs steady freq={reference_freq:.2f}Hz")
                        return False

        return True

    def _frequencies_consistent(self, freq1: float, freq2: float, tolerance: float = 0.5) -> bool:
        """Check if two frequencies indicate consistent regimes."""
        # Both very low (stationary/off)
        if freq1 < 0.1 and freq2 < 0.1:
            return True

        # Both active, check relative difference
        if freq1 > 0.1 and freq2 > 0.1:
            relative_error = abs(freq1 - freq2) / max(freq1, freq2)
            return relative_error < tolerance

        # One active, one not - inconsistent
        return False

    def _validate_experimental_thresholds(self) -> Dict[str, Any]:
        """Validate model predictions against user's experimental threshold data."""

        experimental_tests = [
            {
                "condition": "Qw=1mL/hr, Po=35mbar",
                "Po_mbar": 35.0,
                "Qw_mlhr": 1.0,
                "expected_behavior": "stationary meniscus (0Hz)",
                "threshold_type": "critical"
            },
            {
                "condition": "Qw=5mL/hr, Po=50mbar",
                "Po_mbar": 50.0,
                "Qw_mlhr": 5.0,
                "expected_behavior": "stationary meniscus (0Hz)",
                "threshold_type": "critical"
            }
        ]

        validation_results = []

        for test in experimental_tests:
            Po_Pa = mbar_to_pa(test["Po_mbar"])
            Qw_m3s = mlhr_to_m3s(test["Qw_mlhr"])

            try:
                # Test with linear model
                comparison = self.model_comparator.compare_all_models(
                    self.config, Po_Pa, Qw_m3s, 0.0, models=['steady']
                )

                predicted_freq = comparison.model_results[0].frequency_hz
                matches_expectation = predicted_freq < 0.1  # Low frequency as expected

                validation_results.append({
                    "condition": test["condition"],
                    "predicted_frequency_hz": predicted_freq,
                    "matches_expectation": matches_expectation,
                    "notes": "Frequency < 0.1 Hz" if matches_expectation else f"Unexpectedly high: {predicted_freq:.2f} Hz"
                })

            except Exception as e:
                validation_results.append({
                    "condition": test["condition"],
                    "predicted_frequency_hz": None,
                    "matches_expectation": False,
                    "notes": f"Error: {e}"
                })

        return {
            "experimental_tests": experimental_tests,
            "validation_results": validation_results,
            "overall_agreement": all(r["matches_expectation"] for r in validation_results if r["matches_expectation"] is not None)
        }

    def _identify_implementation_issues(self, model_results: Dict[str, List[PcapModelResult]],
                                      cross_model_consistency: bool) -> List[str]:
        """Identify potential implementation issues."""
        issues = []

        # Check individual model consistency
        for model_name, results in model_results.items():
            inconsistent_results = [r for r in results if not r.implementation_consistent]
            if inconsistent_results:
                issues.append(f"{model_name} model: {len(inconsistent_results)} inconsistent results")

        # Check cross-model consistency
        if not cross_model_consistency:
            issues.append("Cross-model inconsistency detected - models disagree on regime classification")

        # Check if any model failed completely
        for model_name, results in model_results.items():
            error_results = [r for r in results if "ERROR" in r.regime_classifications]
            if error_results:
                issues.append(f"{model_name} model: {len(error_results)} failed evaluations")

        if not issues:
            issues.append("No implementation issues detected")

        return issues

    def _print_summary(self, results: PcapVerificationResults) -> None:
        """Print summary of Pcap verification results."""
        print("\n" + "=" * 60)
        print("PCAP TAX VERIFICATION SUMMARY")
        print("=" * 60)

        print("Test conditions:")
        for i, condition in enumerate(results.test_conditions):
            print(f"  {i+1}. {condition.description}: Po={condition.Po_mbar}mbar, Qw={condition.Qw_mlhr}mL/hr")

        print(f"\nCross-model consistency: {'PASS' if results.cross_model_consistency else 'FAIL'}")

        # Experimental validation
        exp_val = results.experimental_validation
        if exp_val:
            overall_agreement = exp_val.get("overall_agreement", False)
            print(f"Experimental validation: {'PASS' if overall_agreement else 'FAIL'}")

            for val_result in exp_val.get("validation_results", []):
                condition = val_result["condition"]
                freq = val_result.get("predicted_frequency_hz", "N/A")
                match = val_result["matches_expectation"]
                print(f"  {condition}: {freq:.2f}Hz {'PASS' if match else 'FAIL'}")

        # Implementation issues
        print(f"\nImplementation issues:")
        for issue in results.implementation_issues:
            if "No implementation issues" in issue:
                print(f"  GOOD: {issue}")
            else:
                print(f"  ISSUE: {issue}")

        # Overall assessment
        no_issues = len([i for i in results.implementation_issues if "No implementation issues" in i]) > 0
        consistent = results.cross_model_consistency
        experimental_ok = results.experimental_validation.get("overall_agreement", False)

        if no_issues and consistent and experimental_ok:
            print(f"\nOVERALL PASS: Pcap implementation appears correct across all models")
        else:
            print(f"\nOVERALL WARNING: Pcap implementation issues detected - review recommended")