"""
Stage-Wise Model v3: Multi-Factor Regime Classification
=======================================================

Implements multi-factor regime classification system as warning/diagnostic
logic that does NOT override baseline snap-off physics.

Physics Implementation:
- Issue 9: Multi-factor transition warning system
- Strategic improvement: Beyond single capillary number threshold
- Sequential validation framework with design feedback

Key Principles:
- Warning system only - does NOT control snap-off
- Multi-factor validation beyond single Ca threshold
- Separate from critical radius snap-off condition
- Provides design-oriented diagnostics
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, Any, List, Optional

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from . import StageWiseV3Config


class RegimeClassification(Enum):
    """Multi-factor regime classification."""
    DRIPPING = "dripping"                  # Stable droplet formation
    TRANSITIONAL = "transitional"          # Near regime boundaries
    JETTING = "jetting"                    # Continuous jet formation
    BLOWOUT = "blowout"                    # Chaotic/failed generation


@dataclass(frozen=True)
class ValidationCheck:
    """Individual physics validation check result."""
    check_name: str                        # Name of the validation check
    passed: bool                           # Whether check passed
    value: float                           # Measured value
    threshold: float                       # Threshold used
    description: str                       # Human-readable description
    severity: str                          # "low", "medium", "high"


@dataclass(frozen=True)
class RegimeResult:
    """Complete regime classification result."""
    regime: RegimeClassification           # Primary regime classification
    confidence: float                      # Confidence in classification [0-1]

    # Multi-factor validation
    primary_regime: RegimeClassification   # From capillary number alone
    validation_checks: List[ValidationCheck]  # Secondary validation results

    # Design feedback
    design_feedback: Dict[str, Any]        # Actionable design guidance

    # Diagnostics
    diagnostics: Dict[str, Any]           # Detailed diagnostic information


def classify_regime_multi_factor(
    P_j: float,
    Q_avg: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> RegimeResult:
    """
    v3: Multi-factor regime classification with design feedback.

    Implements resolved Issue 9: Separate multi-factor warning system
    + v3 strategic improvement: Sequential validation framework

    Parameters
    ----------
    P_j : float
        Junction pressure difference [Pa]
    Q_avg : float
        Average flow rate [m³/s]
    config : DeviceConfig
        Device configuration
    v3_config : StageWiseV3Config
        v3 physics configuration

    Returns
    -------
    RegimeResult
        Complete regime classification with validation and design feedback
    """

    # Primary screening: Capillary number (existing gate)
    ca = calculate_capillary_number(Q_avg, config, v3_config)
    primary_regime = get_primary_regime_from_ca(ca, config)

    # Secondary validation checks (v3 improvements)
    validation_checks = []

    pressure_check = validate_pressure_balance_v3(P_j, config, v3_config)
    validation_checks.append(pressure_check)

    flow_check = validate_flow_capacity_balance_v3(Q_avg, config, v3_config)
    validation_checks.append(flow_check)

    inertial_check = validate_inertial_effects_v3(Q_avg, config, v3_config)
    validation_checks.append(inertial_check)

    # Additional v3 checks
    if v3_config.enable_multi_factor_regime:
        surface_tension_check = validate_surface_tension_balance_v3(P_j, ca, config, v3_config)
        validation_checks.append(surface_tension_check)

        geometry_check = validate_geometry_scaling_v3(config, v3_config)
        validation_checks.append(geometry_check)

    # Regime refinement based on secondary checks
    final_regime, confidence = refine_regime_classification_v3(
        primary_regime, validation_checks
    )

    # Design feedback generation (v3 strategic improvement)
    design_feedback = {}
    if v3_config.enable_design_feedback:
        design_feedback = generate_design_feedback_v3(
            final_regime, validation_checks, ca, P_j, config, v3_config
        )

    # Build diagnostics
    diagnostics = build_regime_diagnostics(
        ca, P_j, Q_avg, primary_regime, final_regime, validation_checks, config
    )

    return RegimeResult(
        regime=final_regime,
        confidence=confidence,
        primary_regime=primary_regime,
        validation_checks=validation_checks,
        design_feedback=design_feedback,
        diagnostics=diagnostics
    )


def calculate_capillary_number(
    Q_avg: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> float:
    """Calculate capillary number with v3 effective properties."""

    # Characteristic velocity
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    U_char = abs(Q_avg) / A_channel if A_channel > 0 else 0.0

    # v3 effective fluid properties
    mu = config.fluids.mu_continuous
    gamma = v3_config.gamma_effective

    return mu * U_char / gamma if gamma > 0 else 0.0


def get_primary_regime_from_ca(ca: float, config: "DeviceConfig") -> RegimeClassification:
    """Primary regime classification from capillary number alone."""

    # Standard capillary number thresholds (empirical)
    ca_dripping_max = getattr(config, 'stage_wise', None)
    if ca_dripping_max is not None:
        ca_threshold = getattr(ca_dripping_max, 'ca_dripping_limit', 0.3)
    else:
        ca_threshold = 0.3  # Default threshold

    if ca < 0.01:
        return RegimeClassification.DRIPPING  # Well within dripping
    elif ca < ca_threshold:
        return RegimeClassification.DRIPPING  # Normal dripping
    elif ca < 2.0 * ca_threshold:
        return RegimeClassification.TRANSITIONAL  # Near boundary
    else:
        return RegimeClassification.JETTING  # Jetting regime


def validate_pressure_balance_v3(
    P_j: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> ValidationCheck:
    """
    Validate pressure balance for stable droplet formation.

    Checks if junction pressure is within reasonable operating range.
    """

    # Convert P_j from Pa to mbar for comparison
    P_j_mbar = P_j * 1e-2

    # Get operating range (default values if not specified)
    P_min = 50.0  # mbar
    P_max = 300.0  # mbar

    # Check if pressure is within reasonable range
    within_range = P_min <= P_j_mbar <= P_max

    if P_j_mbar < P_min:
        description = f"Pressure too low: {P_j_mbar:.1f} mbar < {P_min:.1f} mbar"
        severity = "high"
    elif P_j_mbar > P_max:
        description = f"Pressure too high: {P_j_mbar:.1f} mbar > {P_max:.1f} mbar"
        severity = "medium"
    else:
        description = f"Pressure within normal range: {P_j_mbar:.1f} mbar"
        severity = "low"

    return ValidationCheck(
        check_name="pressure_balance",
        passed=within_range,
        value=P_j_mbar,
        threshold=P_max if P_j_mbar > P_max else P_min,
        description=description,
        severity=severity
    )


def validate_flow_capacity_balance_v3(
    Q_avg: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> ValidationCheck:
    """
    Validate flow rate vs device capacity balance.

    Checks if flow rate is compatible with device geometry and staging.
    """

    # Estimate device flow capacity
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    L_char = config.geometry.junction.exit_width

    # Characteristic flow rate based on geometry
    gamma = v3_config.gamma_effective
    mu = config.fluids.mu_continuous

    # Capillary-driven characteristic flow
    Q_capillary = gamma * A_channel**2 / (mu * L_char) if mu > 0 and L_char > 0 else 1e-15

    # Flow ratio
    flow_ratio = abs(Q_avg) / Q_capillary if Q_capillary > 0 else 0.0

    # Check flow capacity balance
    capacity_ok = 0.1 <= flow_ratio <= 10.0  # Reasonable range

    if flow_ratio < 0.1:
        description = f"Flow too low vs capacity: ratio {flow_ratio:.2f} < 0.1"
        severity = "medium"
    elif flow_ratio > 10.0:
        description = f"Flow too high vs capacity: ratio {flow_ratio:.2f} > 10.0"
        severity = "high"
    else:
        description = f"Flow vs capacity balanced: ratio {flow_ratio:.2f}"
        severity = "low"

    return ValidationCheck(
        check_name="flow_capacity_balance",
        passed=capacity_ok,
        value=flow_ratio,
        threshold=10.0 if flow_ratio > 10.0 else 0.1,
        description=description,
        severity=severity
    )


def validate_inertial_effects_v3(
    Q_avg: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> ValidationCheck:
    """
    Validate inertial effects vs viscous forces.

    Checks Reynolds number to assess flow regime.
    """

    # Characteristic velocity
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    U_char = abs(Q_avg) / A_channel if A_channel > 0 else 0.0

    # Hydraulic diameter
    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth
    D_h = 2 * w * h / (w + h) if (w + h) > 0 else 0.0

    # Reynolds number
    rho = getattr(config.fluids, 'rho_continuous', 1000.0)  # Default water density
    mu = config.fluids.mu_continuous

    Re = rho * U_char * D_h / mu if mu > 0 else 0.0

    # Check inertial effects
    inertial_ok = Re < 100.0  # Viscous-dominated flow expected

    if Re > 100.0:
        description = f"High Reynolds number: Re = {Re:.1f} > 100, inertial effects significant"
        severity = "medium"
    elif Re > 1000.0:
        description = f"Very high Reynolds number: Re = {Re:.1f} > 1000, turbulence possible"
        severity = "high"
    else:
        description = f"Viscous-dominated flow: Re = {Re:.1f} < 100"
        severity = "low"

    return ValidationCheck(
        check_name="inertial_effects",
        passed=inertial_ok,
        value=Re,
        threshold=100.0,
        description=description,
        severity=severity
    )


def validate_surface_tension_balance_v3(
    P_j: float,
    ca: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> ValidationCheck:
    """
    Validate surface tension force balance.

    Checks if interfacial forces are balanced vs hydrodynamic forces.
    """

    # Characteristic surface tension force
    gamma = v3_config.gamma_effective
    L_char = min(config.geometry.junction.exit_width, config.geometry.junction.exit_depth)
    F_surface = gamma * L_char

    # Characteristic viscous force
    mu = config.fluids.mu_continuous
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    U_char = ca * gamma / mu if mu > 0 else 0.0
    F_viscous = mu * U_char * A_channel / L_char if L_char > 0 else 0.0

    # Force balance ratio
    force_ratio = F_viscous / F_surface if F_surface > 0 else 0.0

    # Check surface tension balance (should be order unity for droplet formation)
    balance_ok = 0.1 <= force_ratio <= 10.0

    if force_ratio < 0.1:
        description = f"Surface tension dominated: force ratio {force_ratio:.2f} < 0.1"
        severity = "low"
    elif force_ratio > 10.0:
        description = f"Viscous force dominated: force ratio {force_ratio:.2f} > 10.0"
        severity = "medium"
    else:
        description = f"Balanced interfacial forces: force ratio {force_ratio:.2f}"
        severity = "low"

    return ValidationCheck(
        check_name="surface_tension_balance",
        passed=balance_ok,
        value=force_ratio,
        threshold=10.0 if force_ratio > 10.0 else 0.1,
        description=description,
        severity=severity
    )


def validate_geometry_scaling_v3(
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> ValidationCheck:
    """
    Validate geometry scaling for droplet formation.

    Checks if device geometry is within validated scaling ranges.
    """

    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth
    aspect_ratio = w / h if h > 0 else 0.0

    # Check aspect ratio (empirical range for stable droplet formation)
    aspect_ok = 0.1 <= aspect_ratio <= 10.0

    # Check absolute dimensions
    min_dimension = min(w, h)
    max_dimension = max(w, h)

    dimension_ok = (1e-6 <= min_dimension <= 1e-3 and  # 1 µm to 1 mm
                    max_dimension <= 5e-3)               # Max 5 mm

    geometry_ok = aspect_ok and dimension_ok

    if not aspect_ok:
        description = f"Extreme aspect ratio: {aspect_ratio:.2f} outside [0.1, 10.0]"
        severity = "high"
    elif not dimension_ok:
        description = f"Extreme dimensions: {min_dimension*1e6:.1f}-{max_dimension*1e6:.1f} µm outside validated range"
        severity = "medium"
    else:
        description = f"Geometry within validated range: AR={aspect_ratio:.2f}, size={min_dimension*1e6:.1f} µm"
        severity = "low"

    return ValidationCheck(
        check_name="geometry_scaling",
        passed=geometry_ok,
        value=aspect_ratio,
        threshold=10.0 if aspect_ratio > 10.0 else 0.1,
        description=description,
        severity=severity
    )


def refine_regime_classification_v3(
    primary_regime: RegimeClassification,
    validation_checks: List[ValidationCheck]
) -> tuple[RegimeClassification, float]:
    """
    Refine regime classification based on secondary validation checks.

    Returns refined regime and confidence level.
    """

    # Count failed checks by severity
    failed_high = sum(1 for check in validation_checks
                     if not check.passed and check.severity == "high")
    failed_medium = sum(1 for check in validation_checks
                       if not check.passed and check.severity == "medium")

    # Start with primary regime
    final_regime = primary_regime
    base_confidence = 0.8  # Base confidence in primary classification

    # Adjust based on validation failures
    if failed_high > 0:
        # High severity failures suggest transitional or problematic regime
        if primary_regime == RegimeClassification.DRIPPING:
            final_regime = RegimeClassification.TRANSITIONAL
        elif primary_regime == RegimeClassification.TRANSITIONAL:
            final_regime = RegimeClassification.BLOWOUT  # More severe
        confidence = base_confidence * 0.3  # Low confidence

    elif failed_medium > 1:
        # Multiple medium failures suggest transitional regime
        if primary_regime == RegimeClassification.DRIPPING:
            final_regime = RegimeClassification.TRANSITIONAL
        confidence = base_confidence * 0.6  # Medium confidence

    elif failed_medium == 1:
        # Single medium failure reduces confidence but keeps regime
        confidence = base_confidence * 0.8

    else:
        # All checks passed or only low severity issues
        confidence = base_confidence

    return final_regime, confidence


def generate_design_feedback_v3(
    regime: RegimeClassification,
    validation_checks: List[ValidationCheck],
    ca: float,
    P_j: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> Dict[str, Any]:
    """
    Generate actionable device design guidance (deferred extension).

    Provides specific recommendations based on regime and validation results.
    """

    feedback = {
        "regime_stability": "stable" if regime == RegimeClassification.DRIPPING else "unstable",
        "recommendations": [],
        "priority_actions": [],
        "parameter_adjustments": {}
    }

    # Analyze failed checks and generate specific recommendations
    for check in validation_checks:
        if not check.passed:
            if check.check_name == "pressure_balance":
                if check.value < check.threshold:
                    feedback["recommendations"].append("Increase oil inlet pressure")
                    feedback["parameter_adjustments"]["Po_in_mbar"] = check.threshold * 1.2
                else:
                    feedback["recommendations"].append("Reduce oil inlet pressure")
                    feedback["parameter_adjustments"]["Po_in_mbar"] = check.threshold * 0.8

            elif check.check_name == "flow_capacity_balance":
                if check.value > check.threshold:
                    feedback["recommendations"].append("Reduce flow rate or increase channel size")
                    feedback["priority_actions"].append("flow_rate_reduction")
                else:
                    feedback["recommendations"].append("Increase flow rate or optimize geometry")

            elif check.check_name == "geometry_scaling":
                feedback["recommendations"].append("Adjust channel aspect ratio toward 1:1")
                feedback["priority_actions"].append("geometry_optimization")

    # Regime-specific recommendations
    if regime == RegimeClassification.JETTING:
        feedback["recommendations"].append("Reduce flow rate to return to dripping regime")
        feedback["priority_actions"].append("flow_reduction")
    elif regime == RegimeClassification.BLOWOUT:
        feedback["recommendations"].append("Check for blockages and pressure instabilities")
        feedback["priority_actions"].append("system_diagnosis")

    return feedback


def build_regime_diagnostics(
    ca: float,
    P_j: float,
    Q_avg: float,
    primary_regime: RegimeClassification,
    final_regime: RegimeClassification,
    validation_checks: List[ValidationCheck],
    config: "DeviceConfig"
) -> Dict[str, Any]:
    """Build comprehensive regime classification diagnostics."""

    return {
        "capillary_number": ca,
        "junction_pressure_Pa": P_j,
        "flow_rate_m3s": Q_avg,
        "primary_regime": primary_regime.value,
        "final_regime": final_regime.value,
        "regime_changed": primary_regime != final_regime,
        "validation_summary": {
            "total_checks": len(validation_checks),
            "passed_checks": sum(1 for check in validation_checks if check.passed),
            "failed_checks": sum(1 for check in validation_checks if not check.passed),
            "high_severity_failures": sum(1 for check in validation_checks
                                        if not check.passed and check.severity == "high")
        },
        "check_details": [
            {
                "name": check.check_name,
                "passed": check.passed,
                "value": check.value,
                "threshold": check.threshold,
                "severity": check.severity
            }
            for check in validation_checks
        ]
    }