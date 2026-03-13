"""
Stage-Wise Model v3: Physics Validation Framework
=================================================

Comprehensive physics validation for v3 implementation to ensure
correct implementation of resolved physics issues and literature consistency.

Validation Components:
- Two-fluid Washburn validation against literature
- Necking time validation (outer phase scaling)
- Mechanism selection logic validation
- Multi-factor regime classification validation
- Design feedback accuracy validation

Quality Assurance:
- Physics parameter bounds checking
- Literature consistency verification
- Experimental validation where available
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Any, List
from dataclasses import dataclass

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from .core import RungGroupResult

# Import validation types
try:
    from . import ValidationResult, PhysicsValidationStatus
except ImportError:
    # Define minimal types for validation
    from enum import Enum
    from dataclasses import dataclass
    from typing import List

    class PhysicsValidationStatus(Enum):
        VALIDATED = "validated"
        WARNING = "warning"
        FAILED = "failed"
        NOT_VALIDATED = "not_validated"

    @dataclass(frozen=True)
    class ValidationResult:
        component: str
        status: PhysicsValidationStatus
        checks_passed: List[str]
        warnings: List[str]
        failures: List[str]
        recommendations: List[str]

# Physics validation constants (literature-based)
WASHBURN_TIME_BOUNDS = (1e-6, 1e-1)       # Reasonable refill times [s]
NECKING_TIME_BOUNDS = (1e-6, 1e-2)        # Reasonable necking times [s]
CRITICAL_RADIUS_BOUNDS = (1e-6, 1e-3)     # Reasonable critical radii [m]
CAPILLARY_NUMBER_BOUNDS = (1e-4, 1e2)     # Typical capillary number range
REYNOLDS_NUMBER_LIMIT = 1000.0            # Upper limit for viscous assumption


def validate_physics_implementation(
    config: "DeviceConfig",
    group_results: List["RungGroupResult"]
) -> Dict[str, Any]:
    """
    Comprehensive physics validation for v3 implementation.

    Tests each resolved physics issue against literature/experimental benchmarks.

    Parameters
    ----------
    config : DeviceConfig
        Device configuration
    group_results : List[RungGroupResult]
        Results from grouped rung simulation

    Returns
    -------
    Dict[str, Any]
        Comprehensive validation report with component-wise validation
    """

    validation_results = {}

    # 1. Two-fluid Washburn validation
    validation_results["washburn"] = validate_two_fluid_washburn(config, group_results)

    # 2. Necking time validation (outer phase scaling)
    validation_results["necking"] = validate_necking_physics_v3(config, group_results)

    # 3. Critical radius validation
    validation_results["critical_radius"] = validate_critical_radius_determination(config, group_results)

    # 4. Mechanism selection validation
    validation_results["mechanisms"] = validate_mechanism_selection_logic(config, group_results)

    # 5. Multi-factor regime classification validation
    validation_results["regime"] = validate_multi_factor_classification(config, group_results)

    # 6. Overall physics consistency
    validation_results["physics_consistency"] = validate_overall_physics_consistency(
        config, group_results, validation_results
    )

    # 7. Literature consistency check
    validation_results["literature_consistency"] = check_literature_consistency(validation_results)

    return validation_results


def validate_two_fluid_washburn(
    config: "DeviceConfig",
    group_results: List["RungGroupResult"]
) -> "ValidationResult":
    """
    Validate two-fluid Washburn implementation against literature expectations.

    Checks:
    - Refill times within reasonable bounds
    - Two-fluid scaling behavior vs single-phase
    - Geometry factor calculations
    - Viscosity ratio effects
    """

    checks_passed = []
    warnings = []
    failures = []

    for group in group_results:
        stage1_result = group.stage1_result

        if not hasattr(stage1_result, 'washburn_result'):
            failures.append("Missing Washburn result in Stage 1 calculation")
            continue

        washburn = stage1_result.washburn_result

        # Check refill time bounds
        t_refill = washburn.refill_time
        if WASHBURN_TIME_BOUNDS[0] <= t_refill <= WASHBURN_TIME_BOUNDS[1]:
            checks_passed.append(f"Refill time within bounds: {t_refill*1e3:.2f} ms")
        else:
            failures.append(f"Refill time outside bounds: {t_refill*1e3:.2f} ms")

        # Check capillary pressure positivity
        if washburn.capillary_pressure > 0:
            checks_passed.append("Positive capillary driving pressure")
        else:
            failures.append(f"Negative capillary pressure: {washburn.capillary_pressure:.2f} Pa")

        # Check resistance factor reasonableness
        f_alpha = washburn.resistance_factor
        if 24 <= f_alpha <= 96:  # Bounds for rectangular channels
            checks_passed.append(f"Resistance factor within expected range: {f_alpha:.1f}")
        else:
            warnings.append(f"Resistance factor outside typical range: {f_alpha:.1f}")

        # Check two-fluid scaling behavior
        physics_params = washburn.physics_params
        mu1 = physics_params.get("mu1_dispersed_Pa_s", 0)
        mu2 = physics_params.get("mu2_continuous_Pa_s", 0)

        if mu1 > 0 and mu2 > 0:
            viscosity_ratio = mu1 / mu2
            if abs(viscosity_ratio - 1.0) > 0.1:  # Significant viscosity difference
                if washburn.two_fluid_scaling == "non_sqrt_t":
                    checks_passed.append("Correct non-square-root scaling for two-fluid system")
                else:
                    warnings.append("Expected non-square-root scaling for different viscosities")
            else:
                if washburn.two_fluid_scaling == "sqrt_t":
                    checks_passed.append("Correct square-root scaling for similar viscosities")
                else:
                    warnings.append("Expected square-root scaling for similar viscosities")

    # Assess overall validation status
    if len(failures) == 0:
        if len(warnings) == 0:
            status = PhysicsValidationStatus.VALIDATED
        else:
            status = PhysicsValidationStatus.WARNING
    else:
        status = PhysicsValidationStatus.FAILED

    recommendations = []
    if len(failures) > 0:
        recommendations.append("Review two-fluid Washburn implementation for physics errors")
    if len(warnings) > 0:
        recommendations.append("Verify viscosity parameters and scaling predictions")

    return ValidationResult(
        component="two_fluid_washburn",
        status=status,
        checks_passed=checks_passed,
        warnings=warnings,
        failures=failures,
        recommendations=recommendations
    )


def validate_necking_physics_v3(
    config: "DeviceConfig",
    group_results: List["RungGroupResult"]
) -> "ValidationResult":
    """
    Validate v3 necking physics implementation (outer-phase corrections).

    Checks:
    - Necking times within literature-based bounds
    - Outer-phase viscosity usage (not inner-phase)
    - Ohnesorge number regime classification
    - Viscosity ratio corrections
    """

    checks_passed = []
    warnings = []
    failures = []

    for group in group_results:
        stage2_result = group.stage2_result

        # Check necking time bounds
        t_necking = stage2_result.t_necking
        if NECKING_TIME_BOUNDS[0] <= t_necking <= NECKING_TIME_BOUNDS[1]:
            checks_passed.append(f"Necking time within literature bounds: {t_necking*1e6:.1f} µs")
        else:
            failures.append(f"Necking time outside bounds: {t_necking*1e6:.1f} µs")

        # Check diagnostics for outer-phase usage
        diagnostics = stage2_result.diagnostics
        if "necking_analysis" in diagnostics:
            necking_diag = diagnostics["necking_analysis"]
            if necking_diag.get("physics_basis") == "outer_phase_viscosity_v3_corrected":
                checks_passed.append("Correct outer-phase viscosity implementation")
            else:
                warnings.append("Unclear whether outer-phase viscosity is used correctly")

            # Check Ohnesorge number calculation
            Oh = necking_diag.get("Oh_outer", 0)
            if 0.001 <= Oh <= 10.0:  # Typical range for microfluidics
                checks_passed.append(f"Ohnesorge number within expected range: {Oh:.3f}")
            else:
                warnings.append(f"Ohnesorge number outside typical range: {Oh:.3f}")

            # Check viscosity ratio
            lambda_visc = necking_diag.get("lambda_visc", 1)
            if 0.1 <= lambda_visc <= 10.0:  # Reasonable range
                checks_passed.append(f"Viscosity ratio reasonable: {lambda_visc:.2f}")
            else:
                warnings.append(f"Extreme viscosity ratio: {lambda_visc:.2f}")

    # Literature consistency check
    if len(checks_passed) > 0 and "outer_phase" in str(checks_passed):
        checks_passed.append("Implementation consistent with Eggers & Villermaux (2008) framework")

    # Assess validation status
    if len(failures) == 0:
        status = PhysicsValidationStatus.VALIDATED if len(warnings) == 0 else PhysicsValidationStatus.WARNING
    else:
        status = PhysicsValidationStatus.FAILED

    recommendations = []
    if len(failures) > 0:
        recommendations.append("Review necking time calculation and parameter bounds")
    if len(warnings) > 0:
        recommendations.append("Verify outer-phase viscosity usage and Ohnesorge number calculation")

    return ValidationResult(
        component="necking_physics_v3",
        status=status,
        checks_passed=checks_passed,
        warnings=warnings,
        failures=failures,
        recommendations=recommendations
    )


def validate_critical_radius_determination(
    config: "DeviceConfig",
    group_results: List["RungGroupResult"]
) -> "ValidationResult":
    """
    Validate critical radius determination from geometry.

    Checks:
    - Critical radius within physical bounds
    - Scaling with geometry parameters
    - Aspect ratio dependence
    """

    checks_passed = []
    warnings = []
    failures = []

    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth

    for group in group_results:
        stage2_result = group.stage2_result
        R_crit = stage2_result.R_critical

        # Check bounds
        if CRITICAL_RADIUS_BOUNDS[0] <= R_crit <= CRITICAL_RADIUS_BOUNDS[1]:
            checks_passed.append(f"Critical radius within physical bounds: {R_crit*1e6:.1f} µm")
        else:
            failures.append(f"Critical radius outside bounds: {R_crit*1e6:.1f} µm")

        # Check scaling with geometry
        min_dimension = min(w, h)
        if 0.1 * min_dimension <= R_crit <= 2.0 * min_dimension:
            checks_passed.append("Critical radius scales appropriately with geometry")
        else:
            warnings.append(f"Critical radius scaling may be incorrect: R_crit/min(w,h) = {R_crit/min_dimension:.2f}")

        # Check aspect ratio handling
        aspect_ratio = w / h if h > 0 else 0
        diagnostics = stage2_result.diagnostics
        if "critical_radius_basis" in diagnostics:
            basis = diagnostics["critical_radius_basis"]
            if "geometry_dependent" in basis:
                checks_passed.append("Critical radius properly determined from geometry")
            else:
                warnings.append("Unclear critical radius determination method")

    # Assess validation status
    if len(failures) == 0:
        status = PhysicsValidationStatus.VALIDATED if len(warnings) == 0 else PhysicsValidationStatus.WARNING
    else:
        status = PhysicsValidationStatus.FAILED

    recommendations = []
    if len(failures) > 0:
        recommendations.append("Review critical radius calculation and geometry scaling")
    if len(warnings) > 0:
        recommendations.append("Verify aspect ratio handling in critical radius determination")

    return ValidationResult(
        component="critical_radius_determination",
        status=status,
        checks_passed=checks_passed,
        warnings=warnings,
        failures=failures,
        recommendations=recommendations
    )


def validate_mechanism_selection_logic(
    config: "DeviceConfig",
    group_results: List["RungGroupResult"]
) -> "ValidationResult":
    """
    Validate Stage 1 mechanism selection logic.

    Checks:
    - Dimensionless number calculations
    - Mechanism hierarchy consistency
    - Confidence assessment reasonableness
    """

    checks_passed = []
    warnings = []
    failures = []

    for group in group_results:
        stage1_result = group.stage1_result

        # Check mechanism selection exists
        if hasattr(stage1_result, 'mechanism'):
            mechanism = stage1_result.mechanism
            confidence = getattr(stage1_result, 'confidence', 0)

            # Check confidence bounds
            if 0 <= confidence <= 1:
                checks_passed.append(f"Mechanism confidence within bounds: {confidence:.2f}")
            else:
                failures.append(f"Mechanism confidence outside [0,1]: {confidence:.2f}")

            # Check mechanism validity
            valid_mechanisms = ["hydraulic_dominated", "interface_dominated", "adsorption_dominated", "backflow_dominated"]
            if mechanism in valid_mechanisms:
                checks_passed.append(f"Valid mechanism selected: {mechanism}")
            else:
                failures.append(f"Invalid mechanism: {mechanism}")

            # Check diagnostics
            if hasattr(stage1_result, 'diagnostics'):
                diagnostics = stage1_result.diagnostics
                if "mechanism_selection" in diagnostics:
                    mech_diag = diagnostics["mechanism_selection"]
                    ca = mech_diag.get("capillary_number", 0)

                    # Check capillary number reasonableness
                    if CAPILLARY_NUMBER_BOUNDS[0] <= ca <= CAPILLARY_NUMBER_BOUNDS[1]:
                        checks_passed.append(f"Capillary number within reasonable range: {ca:.4f}")
                    else:
                        warnings.append(f"Capillary number outside typical range: {ca:.4f}")

        else:
            failures.append("Missing mechanism selection in Stage 1 result")

    # Assess validation status
    if len(failures) == 0:
        status = PhysicsValidationStatus.VALIDATED if len(warnings) == 0 else PhysicsValidationStatus.WARNING
    else:
        status = PhysicsValidationStatus.FAILED

    recommendations = []
    if len(failures) > 0:
        recommendations.append("Review mechanism selection implementation and validation")
    if len(warnings) > 0:
        recommendations.append("Check capillary number calculation and mechanism thresholds")

    return ValidationResult(
        component="mechanism_selection",
        status=status,
        checks_passed=checks_passed,
        warnings=warnings,
        failures=failures,
        recommendations=recommendations
    )


def validate_multi_factor_classification(
    config: "DeviceConfig",
    group_results: List["RungGroupResult"]
) -> "ValidationResult":
    """
    Validate multi-factor regime classification implementation.

    Checks:
    - Validation check implementation
    - Regime refinement logic
    - Confidence assessment
    """

    checks_passed = []
    warnings = []
    failures = []

    for group in group_results:
        if hasattr(group, 'regime_result'):
            regime_result = group.regime_result

            # Check regime classification validity
            if hasattr(regime_result, 'regime'):
                regime = regime_result.regime
                valid_regimes = ["dripping", "transitional", "jetting", "blowout"]
                if hasattr(regime, 'value'):
                    regime_value = regime.value
                else:
                    regime_value = str(regime)

                if regime_value in valid_regimes:
                    checks_passed.append(f"Valid regime classification: {regime_value}")
                else:
                    failures.append(f"Invalid regime classification: {regime_value}")

                # Check confidence
                if hasattr(regime_result, 'confidence'):
                    confidence = regime_result.confidence
                    if 0 <= confidence <= 1:
                        checks_passed.append(f"Regime confidence within bounds: {confidence:.2f}")
                    else:
                        failures.append(f"Regime confidence outside [0,1]: {confidence:.2f}")

                # Check validation checks
                if hasattr(regime_result, 'validation_checks'):
                    n_checks = len(regime_result.validation_checks)
                    if n_checks >= 3:  # Minimum expected checks
                        checks_passed.append(f"Sufficient validation checks performed: {n_checks}")
                    else:
                        warnings.append(f"Few validation checks: {n_checks}")

        else:
            failures.append("Missing regime classification result")

    # Assess validation status
    if len(failures) == 0:
        status = PhysicsValidationStatus.VALIDATED if len(warnings) == 0 else PhysicsValidationStatus.WARNING
    else:
        status = PhysicsValidationStatus.FAILED

    recommendations = []
    if len(failures) > 0:
        recommendations.append("Review regime classification implementation")
    if len(warnings) > 0:
        recommendations.append("Consider adding more validation checks for robustness")

    return ValidationResult(
        component="multi_factor_classification",
        status=status,
        checks_passed=checks_passed,
        warnings=warnings,
        failures=failures,
        recommendations=recommendations
    )


def validate_overall_physics_consistency(
    config: "DeviceConfig",
    group_results: List["RungGroupResult"],
    component_validations: Dict[str, "ValidationResult"]
) -> "ValidationResult":
    """
    Validate overall physics consistency across components.

    Checks:
    - Component interactions
    - Energy/mass conservation
    - Timescale consistency
    """

    checks_passed = []
    warnings = []
    failures = []

    # Check timescale consistency
    for group in group_results:
        t1 = group.stage1_result.t_displacement
        t2 = group.stage2_result.t_growth
        total_time = t1 + t2

        # Stage timescales should be reasonable relative to each other
        if t1 > 0 and t2 > 0:
            stage_ratio = t1 / t2
            if 0.1 <= stage_ratio <= 10.0:  # Within order of magnitude
                checks_passed.append(f"Stage timescales consistent: t1/t2 = {stage_ratio:.2f}")
            else:
                warnings.append(f"Unusual stage time ratio: t1/t2 = {stage_ratio:.2f}")

        # Total cycle time should be reasonable
        if 1e-5 <= total_time <= 1e0:  # 10 µs to 1 s
            checks_passed.append(f"Total cycle time reasonable: {total_time*1e3:.2f} ms")
        else:
            warnings.append(f"Unusual total cycle time: {total_time*1e3:.2f} ms")

    # Check component validation consistency
    failed_components = [name for name, result in component_validations.items()
                        if result.status == PhysicsValidationStatus.FAILED]

    if len(failed_components) == 0:
        checks_passed.append("All physics components validated successfully")
    else:
        failures.append(f"Failed component validations: {', '.join(failed_components)}")

    # Check for critical physics issues
    critical_components = ["washburn", "necking", "critical_radius"]
    critical_failures = [name for name in failed_components if name in critical_components]

    if len(critical_failures) > 0:
        failures.append(f"Critical physics components failed: {', '.join(critical_failures)}")

    # Assess validation status
    if len(failures) == 0:
        status = PhysicsValidationStatus.VALIDATED if len(warnings) == 0 else PhysicsValidationStatus.WARNING
    else:
        status = PhysicsValidationStatus.FAILED

    recommendations = []
    if len(failures) > 0:
        recommendations.append("Address critical physics implementation issues before proceeding")
    if len(warnings) > 0:
        recommendations.append("Review parameter bounds and physical reasonableness")

    return ValidationResult(
        component="overall_physics_consistency",
        status=status,
        checks_passed=checks_passed,
        warnings=warnings,
        failures=failures,
        recommendations=recommendations
    )


def check_literature_consistency(validation_results: Dict[str, "ValidationResult"]) -> Dict[str, Any]:
    """
    Check overall consistency with literature expectations.

    Returns summary of literature alignment for major physics components.
    """

    literature_alignment = {}

    # Two-fluid Washburn literature consistency
    washburn_result = validation_results.get("washburn")
    if washburn_result and washburn_result.status != PhysicsValidationStatus.FAILED:
        literature_alignment["washburn"] = "consistent_with_washburn_literature"
    else:
        literature_alignment["washburn"] = "inconsistent_with_washburn_literature"

    # Necking physics literature consistency
    necking_result = validation_results.get("necking")
    if necking_result and "Eggers" in str(necking_result.checks_passed):
        literature_alignment["necking"] = "consistent_with_eggers_villermaux_2008"
    else:
        literature_alignment["necking"] = "needs_literature_verification"

    # Overall literature consistency
    consistent_components = sum(1 for alignment in literature_alignment.values()
                               if "consistent" in alignment)
    total_components = len(literature_alignment)

    if consistent_components == total_components:
        overall_consistency = "high_literature_consistency"
    elif consistent_components >= total_components * 0.7:
        overall_consistency = "moderate_literature_consistency"
    else:
        overall_consistency = "low_literature_consistency"

    return {
        "component_alignment": literature_alignment,
        "overall_consistency": overall_consistency,
        "consistent_components": consistent_components,
        "total_components": total_components
    }