"""
Stage-Wise Model v3: Stage 2 Critical Size + Neck Physics
=========================================================

Implements Stage 2 physics with critical size controlled snap-off and
neck state tracking as specified in the consolidated physics plan.

Physics Implementation:
- Issue 4: Known critical size + evolving neck tracking
- Issue 6: Critical radius determination from geometry
- Strategic improvement: Outer-phase necking physics (diagnostic only)

Key Principles:
- Snap-off occurs when droplet radius reaches R = Rcrit
- Rcrit is experimentally known, geometry dependent, configurable
- Neck variables tracked for diagnostics and warning logic ONLY
- Neck tracking does NOT control snap-off in baseline implementation
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Dict, Any, Optional

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from . import StageWiseV3Config


class TransitionWarningType(Enum):
    """Types of regime transition warnings."""
    DELAYED_SNAP_OFF = "delayed_snap_off"
    HIGH_NECK_CAPILLARY_NUMBER = "high_neck_capillary_number"
    NECK_THINNING_ANOMALY = "neck_thinning_anomaly"
    PRESSURE_IMBALANCE = "pressure_imbalance"


@dataclass(frozen=True)
class TransitionWarning:
    """Warning about potential regime transition."""
    type: TransitionWarningType
    severity: str                           # "low", "medium", "high"
    description: str                        # Human-readable description
    suggested_action: str                   # Recommended response
    diagnostic_value: float                 # Quantitative diagnostic


@dataclass(frozen=True)
class NeckEvolution:
    """Evolution of neck state variables during Stage 2 growth."""
    times: np.ndarray                       # Time points [s]
    widths: np.ndarray                     # Neck width evolution [m]
    velocities: np.ndarray                 # Neck velocity evolution [m/s]
    capillary_numbers: np.ndarray          # Local neck capillary numbers
    thinning_rates: np.ndarray             # Neck thinning rates [1/s]

    @property
    def max_capillary_number(self) -> float:
        """Maximum neck capillary number during evolution."""
        return float(np.max(self.capillary_numbers)) if len(self.capillary_numbers) > 0 else 0.0

    @property
    def final_neck_width(self) -> float:
        """Final neck width at snap-off."""
        return float(self.widths[-1]) if len(self.widths) > 0 else 0.0


@dataclass(frozen=True)
class Stage2Result:
    """Complete Stage 2 physics result."""
    t_growth: float                        # Growth phase duration [s]
    t_necking: float                       # Necking phase duration [s]
    t_total: float                         # Total Stage 2 duration [s]

    # Droplet properties at snap-off
    R_critical: float                      # Critical radius for breakup [m]
    D_droplet: float                       # Final droplet diameter [m]
    V_droplet: float                       # Final droplet volume [m³]

    # Neck state tracking (diagnostic only)
    neck_evolution: NeckEvolution          # Complete neck evolution
    transition_warnings: List[TransitionWarning]  # Transition warnings

    # Physics diagnostics
    physics_basis: str                     # Physics model used
    diagnostics: Dict[str, Any]            # Detailed diagnostic information


class NeckStateTracker:
    """Tracks evolving neck quantities during Stage 2 growth."""

    def __init__(self, initial_time: float = 0.0):
        self.times = [initial_time]
        self.neck_widths = []
        self.neck_velocities = []
        self.neck_capillary_numbers = []
        self.thinning_rates = []

    def update(self, t: float, neck_width: float, U_neck: float, gamma: float, mu_oil: float):
        """Update neck state at time t."""

        if len(self.times) > 0 and t <= self.times[-1]:
            return  # Avoid duplicate or backwards time steps

        # Calculate derived quantities
        ca_neck = mu_oil * U_neck / gamma if gamma > 0 else 0.0

        # Thinning rate (change in width over time)
        if len(self.neck_widths) > 0 and len(self.times) > 1:
            dt = t - self.times[-1]
            dw_dt = (neck_width - self.neck_widths[-1]) / dt if dt > 0 else 0.0
            thinning_rate = -dw_dt / neck_width if neck_width > 0 else 0.0
        else:
            thinning_rate = 0.0

        # Store state
        self.times.append(t)
        self.neck_widths.append(neck_width)
        self.neck_velocities.append(U_neck)
        self.neck_capillary_numbers.append(ca_neck)
        self.thinning_rates.append(thinning_rate)

    def get_evolution(self) -> NeckEvolution:
        """Return complete neck evolution for analysis."""
        return NeckEvolution(
            times=np.array(self.times),
            widths=np.array(self.neck_widths),
            velocities=np.array(self.neck_velocities),
            capillary_numbers=np.array(self.neck_capillary_numbers),
            thinning_rates=np.array(self.thinning_rates)
        )


def solve_stage2_critical_size_with_tracking(
    P_j: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> Stage2Result:
    """
    Stage 2 with known critical size but full neck state tracking.

    Implements resolved Issue 4: Assume monodisperse operation with known
    droplet size while tracking neck-state variables for future transition prediction.

    Parameters
    ----------
    P_j : float
        Junction pressure difference [Pa]
    config : DeviceConfig
        Device configuration
    v3_config : StageWiseV3Config
        v3 physics configuration

    Returns
    -------
    Stage2Result
        Complete Stage 2 result with neck evolution and transition warnings
    """

    # Calculate critical radius from geometry (Issue 6)
    R_critical = calculate_critical_radius_from_geometry(config, v3_config)

    # Initialize neck tracking
    neck_tracker = NeckStateTracker()

    # Stage 2 growth simulation to critical radius
    growth_result = simulate_droplet_growth_to_critical_radius(
        R_critical, P_j, config, neck_tracker
    )

    # Calculate necking time using outer-phase physics (strategic improvement)
    t_necking, necking_diagnostics = calculate_necking_time_outer_phase(config, v3_config)

    # Extract neck evolution
    neck_evolution = neck_tracker.get_evolution()

    # Generate transition warnings
    transition_warnings = generate_transition_warnings_internal(
        neck_evolution, R_critical, config, v3_config
    )

    # Total Stage 2 time
    t_total = growth_result["growth_time"] + t_necking

    # Droplet properties at snap-off
    D_droplet = 2.0 * R_critical
    V_droplet = (4.0/3.0) * np.pi * (R_critical ** 3)

    # Build diagnostics
    diagnostics = {
        "growth_simulation": growth_result,
        "necking_analysis": necking_diagnostics,
        "critical_radius_basis": "geometry_dependent_back_calculated",
        "neck_tracking_points": len(neck_evolution.times),
        "physics_validation": validate_stage2_physics(R_critical, t_total, config)
    }

    return Stage2Result(
        t_growth=growth_result["growth_time"],
        t_necking=t_necking,
        t_total=t_total,
        R_critical=R_critical,
        D_droplet=D_droplet,
        V_droplet=V_droplet,
        neck_evolution=neck_evolution,
        transition_warnings=transition_warnings,
        physics_basis="critical_size_with_neck_tracking",
        diagnostics=diagnostics
    )


def calculate_critical_radius_from_geometry(
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> float:
    """
    Geometry-controlled breakup radius with v3 validation.

    Implements resolved Issue 6: Critical radius determination from geometry.
    """

    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth

    if w <= 0 or h <= 0:
        raise ValueError(
            f"Invalid geometry: width={w*1e6:.1f}µm, depth={h*1e6:.1f}µm. "
            "Both must be positive for v3 physics calculations."
        )

    # v3 implementation with back-calculated ratio
    R_critical_ratio = v3_config.R_critical_ratio
    aspect_ratio = w / h

    if aspect_ratio > 3.0:
        R_critical = R_critical_ratio * h  # Depth-limited for high aspect ratios
        basis = "depth_limited_high_aspect"
    else:
        R_critical = R_critical_ratio * min(w, h)  # Geometric mean for normal aspects
        basis = "geometric_mean_normal_aspect"

    # Validation checks
    if R_critical < 1e-6:  # 1 µm minimum
        raise ValueError(
            f"Calculated R_critical = {R_critical*1e6:.2f} µm is below physical minimum. "
            "Check geometry or R_critical_ratio parameter."
        )

    return R_critical


def simulate_droplet_growth_to_critical_radius(
    R_critical: float,
    P_j: float,
    config: "DeviceConfig",
    neck_tracker: NeckStateTracker
) -> Dict[str, Any]:
    """
    Simulate droplet growth from initial size to critical radius.

    This is a simplified growth model for baseline implementation.
    Future versions may include detailed Laplace pressure evolution.
    """

    # Simplified growth model: constant effective driving pressure
    gamma = getattr(config, 'stage_wise_v3', None)
    if gamma is not None:
        gamma_eff = gamma.gamma_effective
    else:
        gamma_eff = 15e-3  # Default 15 mN/m

    # Initial droplet radius (small seed)
    R_initial = 0.1 * min(config.geometry.junction.exit_width,
                         config.geometry.junction.exit_depth)

    # Effective flow rate for growth (simplified)
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    mu_oil = config.fluids.mu_dispersed

    # Average Laplace pressure during growth
    P_laplace_initial = 2 * gamma_eff / R_initial
    P_laplace_final = 2 * gamma_eff / R_critical
    P_laplace_avg = 0.5 * (P_laplace_initial + P_laplace_final)

    # Effective driving pressure
    P_driving = max(P_j - P_laplace_avg, 0.1 * P_j)

    # Effective resistance (simplified)
    L_eff = config.geometry.junction.exit_width
    R_hydraulic = 12 * mu_oil * L_eff / A_channel**3 if A_channel > 0 else 1e12

    # Effective flow rate
    Q_eff = P_driving / R_hydraulic if R_hydraulic > 0 else 1e-15

    # Volume change and growth time
    V_initial = (4.0/3.0) * np.pi * (R_initial ** 3)
    V_final = (4.0/3.0) * np.pi * (R_critical ** 3)
    dV = V_final - V_initial

    growth_time = dV / Q_eff if Q_eff > 0 else 1e-3

    # Bound growth time to reasonable values
    growth_time = max(min(growth_time, 1e-1), 1e-6)  # 1 µs to 100 ms

    # Track neck evolution during growth (simplified)
    n_points = 10
    for i in range(n_points + 1):
        t = i * growth_time / n_points
        R_current = R_initial + (R_critical - R_initial) * i / n_points

        # Estimate neck properties (simplified)
        neck_width = 0.5 * config.geometry.junction.exit_depth  # Constant for simplicity
        U_neck = Q_eff / A_channel if A_channel > 0 else 0.0

        neck_tracker.update(t, neck_width, U_neck, gamma_eff, mu_oil)

    return {
        "growth_time": growth_time,
        "R_initial": R_initial,
        "R_final": R_critical,
        "Q_effective": Q_eff,
        "P_driving_avg": P_driving,
        "growth_physics": "simplified_constant_pressure"
    }


def calculate_necking_time_outer_phase(
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> tuple[float, Dict[str, Any]]:
    """
    v3: Outer-phase viscosity + interfacial tension scaling.

    Implements v3 strategic improvement: Corrected necking physics
    Based on Eggers & Villermaux (Rep. Prog. Phys. 2008)

    NOTE: This is diagnostic only and does NOT control snap-off.
    """

    # Use outer phase (water) viscosity - CORRECTED from v2
    mu_outer = config.fluids.mu_continuous
    mu_inner = config.fluids.mu_dispersed
    gamma = v3_config.gamma_effective
    rho_outer = getattr(config.fluids, 'rho_continuous', 1000.0)  # Default water density

    # Characteristic neck radius
    R_neck = config.geometry.junction.exit_width / 4

    # Viscosity ratio effects
    lambda_visc = mu_inner / mu_outer

    # Ohnesorge number based on outer phase - CORRECTED
    Oh_outer = mu_outer / np.sqrt(rho_outer * gamma * R_neck)

    # Necking time scaling with v3 corrections
    if Oh_outer < 0.1:  # Inertial regime
        tau_inertial = np.sqrt(rho_outer * R_neck**3 / gamma)
        tau_necking = tau_inertial * viscosity_ratio_correction_inertial(lambda_visc)
        regime = "inertial"
    else:  # Viscous regime
        tau_viscous = mu_outer * R_neck / gamma  # NOT mu_dispersed (v2 correction)
        tau_necking = tau_viscous * viscosity_ratio_correction_viscous(lambda_visc)
        regime = "viscous"

    # Bounds checking
    tau_necking = max(min(tau_necking, 1e-2), 1e-6)  # 1 µs to 10 ms

    diagnostics = {
        "Oh_outer": Oh_outer,
        "lambda_visc": lambda_visc,
        "regime": regime,
        "R_neck_m": R_neck,
        "physics_basis": "outer_phase_viscosity_v3_corrected",
        "literature_reference": "Eggers_Villermaux_2008"
    }

    return tau_necking, diagnostics


def viscosity_ratio_correction_inertial(lambda_visc: float) -> float:
    """Viscosity ratio correction for inertial necking regime."""
    return 1.0 + 0.1 * np.log(1.0 + lambda_visc)


def viscosity_ratio_correction_viscous(lambda_visc: float) -> float:
    """Viscosity ratio correction for viscous necking regime."""
    return (1.0 + lambda_visc) / (1.0 + 0.5 * lambda_visc)


def generate_transition_warnings_internal(
    neck_evolution: NeckEvolution,
    R_critical: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> List[TransitionWarning]:
    """
    Multi-factor warning system based on neck state tracking.

    Implements resolved Issue 9 warning variables:
    - Local neck velocity U_neck
    - Local neck capillary number
    - Whether droplet exceeds normal size without expected breakup
    """

    warnings = []

    if not v3_config.enable_transition_warnings or len(neck_evolution.times) == 0:
        return warnings

    # Check neck capillary number trends
    ca_neck_max = neck_evolution.max_capillary_number
    ca_threshold = v3_config._mechanism_thresholds.get("ca_neck_critical", 0.3)

    if ca_neck_max > ca_threshold:
        warnings.append(TransitionWarning(
            type=TransitionWarningType.HIGH_NECK_CAPILLARY_NUMBER,
            severity="medium",
            description=f"Max neck Ca = {ca_neck_max:.3f} exceeds threshold {ca_threshold:.3f}",
            suggested_action="Risk of jetting transition",
            diagnostic_value=ca_neck_max
        ))

    # Check for anomalous neck thinning
    if len(neck_evolution.thinning_rates) > 0:
        max_thinning_rate = np.max(np.abs(neck_evolution.thinning_rates))
        if max_thinning_rate > 1e3:  # 1/ms threshold
            warnings.append(TransitionWarning(
                type=TransitionWarningType.NECK_THINNING_ANOMALY,
                severity="high",
                description=f"Rapid neck thinning rate: {max_thinning_rate:.0f} /s",
                suggested_action="Check for numerical instability or extreme conditions",
                diagnostic_value=max_thinning_rate
            ))

    # Check final neck width
    final_neck_width = neck_evolution.final_neck_width
    expected_minimum = 0.1 * config.geometry.junction.exit_depth
    if final_neck_width < expected_minimum:
        warnings.append(TransitionWarning(
            type=TransitionWarningType.NECK_THINNING_ANOMALY,
            severity="medium",
            description=f"Final neck width {final_neck_width*1e6:.1f} µm below expected minimum",
            suggested_action="Verify physics parameters and numerical accuracy",
            diagnostic_value=final_neck_width
        ))

    return warnings


def validate_stage2_physics(R_critical: float, t_total: float, config: "DeviceConfig") -> Dict[str, Any]:
    """Validate Stage 2 physics for reasonableness."""

    validation = {
        "R_critical_reasonable": True,
        "timing_reasonable": True,
        "geometry_consistent": True,
        "warnings": []
    }

    # Check critical radius
    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth
    min_dimension = min(w, h)

    if R_critical < 0.1 * min_dimension:
        validation["R_critical_reasonable"] = False
        validation["warnings"].append(f"R_critical too small: {R_critical*1e6:.1f} µm")

    if R_critical > 5.0 * min_dimension:
        validation["R_critical_reasonable"] = False
        validation["warnings"].append(f"R_critical too large: {R_critical*1e6:.1f} µm")

    # Check timing
    if t_total < 1e-6 or t_total > 1e-1:
        validation["timing_reasonable"] = False
        validation["warnings"].append(f"Stage 2 time outside reasonable range: {t_total*1e3:.2f} ms")

    return validation


# External interface for transition warnings (used by core.py)
def generate_transition_warnings(
    neck_evolution: NeckEvolution,
    stage2_result: Stage2Result,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> List[TransitionWarning]:
    """External interface for generating transition warnings."""
    return generate_transition_warnings_internal(
        neck_evolution, stage2_result.R_critical, config, v3_config
    )