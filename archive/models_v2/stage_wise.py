"""
stepgen.models.stage_wise
==========================
Stage-wise droplet formation model with modular corrections.

Implements three-layer architecture:
1. Hydraulic Network (existing backbone)
2. Local Droplet Event Law (Stage 1 displacement + Stage 2 growth)
3. Optional Correction Mechanisms

Physics based on /docs/03_stage_wise_model/v2/compare_ideas.typ analysis.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Any, Optional

import numpy as np

from stepgen.config import mbar_to_pa, mlhr_to_m3s
from stepgen.models.hydraulics import SimResult, simulate
from stepgen.models.resistance import rung_resistance

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class RegimeClassification(enum.Enum):
    """Droplet generation regime based on capillary number and validation checks"""
    DRIPPING = "dripping"                    # Normal droplet formation
    TRANSITIONAL = "transitional"            # Near regime boundary
    TRANSITIONAL_OVERSIZED = "transitional_oversized"  # Monodisperse but large
    JETTING = "jetting"                      # Continuous jet formation
    BLOWOUT = "blowout"                      # Chaotic/failed generation


@dataclass(frozen=True)
class CorrectionFactors:
    """Stage 1 resistance correction factors"""
    interface_resistance: float = 1.0       # Contact line resistance multiplier
    adsorption_delay: float = 0.0            # Surfactant adsorption delay [s]
    backflow_effect: float = 1.0             # Backflow resistance multiplier


@dataclass(frozen=True)
class Stage1Result:
    """Stage 1 displacement physics result"""
    t_displacement: float                    # Stage 1 duration [s]
    reset_distance: float                    # Meniscus reset distance [m]
    base_flow_rate: float                   # Uncorrected flow rate [m³/s]
    correction_factors: CorrectionFactors
    active_corrections: Dict[str, bool]     # Which corrections were applied
    diagnostics: Dict[str, Any]


@dataclass(frozen=True)
class Stage2Result:
    """Stage 2 bulb growth and necking physics result"""
    t_growth: float                         # Growth phase duration [s]
    t_necking: float                        # Necking phase duration [s]
    t_total: float                          # Total Stage 2 duration [s]
    D_droplet: float                        # Final droplet diameter [m]
    V_droplet: float                        # Final droplet volume [m³]
    R_critical: float                       # Critical radius for breakup [m]
    regime_indicators: Dict[str, Any]       # Physics-based regime flags
    diagnostics: Dict[str, Any]


@dataclass(frozen=True)
class RungGroupResult:
    """Results for a group of rungs with similar hydraulic conditions"""
    group_id: int
    rung_indices: List[int]                 # Which rungs are in this group
    P_oil_avg: float                        # Average oil pressure [Pa]
    P_water_avg: float                      # Average water pressure [Pa]
    P_j_avg: float                          # Average junction pressure difference [Pa]
    Q_avg: float                            # Average rung flow rate [m³/s]
    stage1_result: Stage1Result
    stage2_result: Stage2Result
    regime: RegimeClassification
    confidence_level: str                   # "high", "medium", "low"
    warnings: List[str]                     # Regime detection warnings


@dataclass(frozen=True)
class StageWiseDiagnostics:
    """Comprehensive diagnostic output for model debugging"""

    # Adaptive grouping analysis
    pressure_uniformity: Dict[str, float]  # Uniformity metrics
    grouping_triggered: bool               # Whether grouping was used
    num_groups: int                        # Number of groups created

    # Stage timing breakdown
    stage_timings: Dict[str, List[float]]  # Per-group timing analysis

    # Correction mechanism analysis
    correction_analysis: Dict[str, Any]    # Impact of each correction

    # Regime classification details
    regime_diagnostics: Dict[str, Any]     # Ca values, thresholds, confidence

    # Experimental comparison (when available)
    experimental_comparison: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class StageWiseResult:
    """Complete stage-wise model result"""
    hydraulic_state: SimResult             # From existing hydraulics backbone
    group_results: List[RungGroupResult]   # Per-group physics results
    global_metrics: Dict[str, float]       # Device-level averages
    diagnostics: StageWiseDiagnostics      # Debug/analysis data

    # Convenience properties matching existing interface
    @property
    def P_oil(self) -> np.ndarray:
        """Oil pressure profile for compatibility"""
        return self.hydraulic_state.P_oil

    @property
    def P_water(self) -> np.ndarray:
        """Water pressure profile for compatibility"""
        return self.hydraulic_state.P_water

    @property
    def Q_rungs(self) -> np.ndarray:
        """Rung flow rates for compatibility"""
        return self.hydraulic_state.Q_rungs


# =============================================================================
# Main Entry Point
# =============================================================================

def stage_wise_solve(
    config: "DeviceConfig",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    P_out_mbar: float | None = None,
) -> StageWiseResult:
    """
    Stage-wise droplet formation solver with adaptive rung grouping.

    Parameters
    ----------
    config : DeviceConfig
        Device configuration including stage_wise section
    Po_in_mbar : float, optional
        Oil inlet pressure [mbar]. Defaults to config.operating.Po_in_mbar
    Qw_in_mlhr : float, optional
        Water inlet flow [mL/hr]. Defaults to config.operating.Qw_in_mlhr
    P_out_mbar : float, optional
        Outlet pressure [mbar]. Defaults to config.operating.P_out_mbar

    Returns
    -------
    StageWiseResult
        Complete stage-wise physics results with diagnostics
    """

    # Layer 1: Hydraulic Network (existing backbone)
    hydraulic_result = simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)

    # Adaptive Grouping Decision
    pressure_analysis = analyze_pressure_uniformity(hydraulic_result, config)
    if pressure_analysis["requires_grouping"]:
        rung_groups = create_pressure_groups(hydraulic_result, config)
    else:
        rung_groups = create_uniform_group(hydraulic_result, config)

    # Layer 2: Local Droplet Physics (per-group)
    group_results = []
    for group in rung_groups:
        group_result = solve_group_physics(group, config)
        group_results.append(group_result)

    # Global metrics and diagnostics
    global_metrics = compute_global_metrics(group_results)
    diagnostics = build_diagnostics(hydraulic_result, group_results, pressure_analysis, config)

    return StageWiseResult(
        hydraulic_state=hydraulic_result,
        group_results=group_results,
        global_metrics=global_metrics,
        diagnostics=diagnostics
    )


# =============================================================================
# Adaptive Grouping Functions
# =============================================================================

def analyze_pressure_uniformity(hydraulic_result: SimResult, config: "DeviceConfig") -> Dict[str, Any]:
    """Determine if pressure variations require rung grouping"""

    # Calculate pressure differences along device
    P_oil_range = np.max(hydraulic_result.P_oil) - np.min(hydraulic_result.P_oil)
    P_water_range = np.max(hydraulic_result.P_water) - np.min(hydraulic_result.P_water)

    # Junction pressure differences (what drives droplet formation)
    P_j = hydraulic_result.P_oil - hydraulic_result.P_water
    P_j_range = np.max(P_j) - np.min(P_j)
    P_j_mean = np.mean(P_j)

    # Relative variation threshold
    threshold = getattr(config.stage_wise, 'pressure_uniformity_threshold', 0.05)  # 5% default
    relative_variation = P_j_range / P_j_mean if P_j_mean > 0 else 0.0

    requires_grouping = relative_variation > threshold

    return {
        "requires_grouping": requires_grouping,
        "P_j_range_Pa": float(P_j_range),
        "P_j_mean_Pa": float(P_j_mean),
        "relative_variation": float(relative_variation),
        "threshold_used": threshold,
        "P_oil_range_Pa": float(P_oil_range),
        "P_water_range_Pa": float(P_water_range)
    }


def create_uniform_group(hydraulic_result: SimResult, config: "DeviceConfig") -> List[Dict[str, Any]]:
    """Create single group containing all rungs"""

    N_rungs = len(hydraulic_result.P_oil)
    group = {
        "group_id": 0,
        "rung_indices": list(range(N_rungs)),
        "P_oil_avg": float(np.mean(hydraulic_result.P_oil)),
        "P_water_avg": float(np.mean(hydraulic_result.P_water)),
        "Q_avg": float(np.mean(hydraulic_result.Q_rungs))
    }

    return [group]


def create_pressure_groups(hydraulic_result: SimResult, config: "DeviceConfig") -> List[Dict[str, Any]]:
    """Create multiple groups based on pressure variations"""

    max_groups = getattr(config.stage_wise, 'max_groups', 10)

    # Simple grouping: divide rungs into spatial groups along device length
    N_rungs = len(hydraulic_result.P_oil)
    groups_per_device = min(max_groups, N_rungs // 2)  # At least 2 rungs per group

    groups = []
    for i in range(groups_per_device):
        start_idx = i * N_rungs // groups_per_device
        end_idx = (i + 1) * N_rungs // groups_per_device

        rung_indices = list(range(start_idx, end_idx))

        group = {
            "group_id": i,
            "rung_indices": rung_indices,
            "P_oil_avg": float(np.mean(hydraulic_result.P_oil[start_idx:end_idx])),
            "P_water_avg": float(np.mean(hydraulic_result.P_water[start_idx:end_idx])),
            "Q_avg": float(np.mean(hydraulic_result.Q_rungs[start_idx:end_idx]))
        }
        groups.append(group)

    return groups


# =============================================================================
# Stage 1: Displacement Physics Implementation
# =============================================================================

def solve_stage1_displacement_physics(
    P_j: float,
    Q_nominal: float,
    config: "DeviceConfig"
) -> Stage1Result:
    """
    Stage 1: Meniscus displacement with modular resistance corrections.

    Based on experimental observation: reset_distance ≈ exit_width
    Implements corrections for interface resistance, adsorption, backflow.
    """

    # Base displacement calculation
    reset_distance = config.geometry.junction.exit_width  # Experimental observation
    base_flow_rate = abs(Q_nominal)  # Ensure positive

    if base_flow_rate <= 0:
        base_flow_rate = 1e-15  # Avoid division by zero

    t_displacement_base = reset_distance / base_flow_rate

    # Initialize correction factors
    correction_factors = CorrectionFactors()
    active_corrections = {
        "moving_interface": False,
        "adsorption_kinetics": False,
        "backflow": False
    }
    diagnostics = {}

    # Modular corrections based on config
    if config.stage_wise.moving_interface:
        interface_correction, interface_diag = calculate_interface_resistance_correction(
            Q_nominal, config
        )
        correction_factors = CorrectionFactors(
            interface_resistance=interface_correction,
            adsorption_delay=correction_factors.adsorption_delay,
            backflow_effect=correction_factors.backflow_effect
        )
        active_corrections["moving_interface"] = True
        diagnostics["interface_resistance"] = interface_diag

    if config.stage_wise.adsorption_kinetics:
        adsorption_delay, adsorption_diag = calculate_adsorption_delay(config)
        correction_factors = CorrectionFactors(
            interface_resistance=correction_factors.interface_resistance,
            adsorption_delay=adsorption_delay,
            backflow_effect=correction_factors.backflow_effect
        )
        active_corrections["adsorption_kinetics"] = True
        diagnostics["adsorption"] = adsorption_diag

    if config.stage_wise.backflow:
        backflow_correction, backflow_diag = calculate_backflow_correction(
            P_j, config
        )
        correction_factors = CorrectionFactors(
            interface_resistance=correction_factors.interface_resistance,
            adsorption_delay=correction_factors.adsorption_delay,
            backflow_effect=backflow_correction
        )
        active_corrections["backflow"] = True
        diagnostics["backflow"] = backflow_diag

    # Apply all corrections
    t_displacement = (
        t_displacement_base *
        correction_factors.interface_resistance *
        correction_factors.backflow_effect +
        correction_factors.adsorption_delay
    )

    return Stage1Result(
        t_displacement=t_displacement,
        reset_distance=reset_distance,
        base_flow_rate=base_flow_rate,
        correction_factors=correction_factors,
        active_corrections=active_corrections,
        diagnostics=diagnostics
    )


def calculate_interface_resistance_correction(Q_nominal: float, config: "DeviceConfig") -> tuple[float, dict]:
    """
    Calculate interface resistance correction based on capillary number.

    Moving contact lines have additional resistance beyond bulk flow.
    Higher Ca (faster interfaces) → more resistance.
    """

    # Calculate local capillary number
    ca = calculate_capillary_number_local(Q_nominal, config)

    # Interface resistance model: R_interface = f(Ca)
    # Based on Cox-Voinov law and contact line dynamics
    # R_factor = 1 + α * Ca^β (empirical fit)

    # Default parameters (to be calibrated with experimental data)
    alpha = 2.0  # Interface resistance strength
    beta = 0.5   # Ca exponent (square root dependence typical for contact lines)

    resistance_factor = 1.0 + alpha * (ca ** beta)

    diagnostics = {
        "capillary_number": float(ca),
        "resistance_factor": float(resistance_factor),
        "alpha": alpha,
        "beta": beta
    }

    return resistance_factor, diagnostics


def calculate_adsorption_delay(config: "DeviceConfig") -> tuple[float, dict]:
    """
    Calculate surfactant adsorption delay.

    If surfactants are present, interface may pause until γ(t) equilibrates.
    Delay time depends on adsorption kinetics and bulk concentration.
    """

    # Simplified adsorption model
    # τ_ads ≈ L_char / D_surf (diffusion timescale)
    # where L_char is characteristic length, D_surf is surfactant diffusivity

    # Default values (literature typical for common surfactants)
    L_char = config.geometry.junction.exit_width  # Characteristic length
    D_surf = 1e-9  # m²/s (typical surfactant diffusivity)

    # Adsorption delay (simplified)
    tau_adsorption = (L_char ** 2) / D_surf

    # Limit to reasonable range
    tau_adsorption = min(tau_adsorption, 0.001)  # Max 1 ms
    tau_adsorption = max(tau_adsorption, 0.0)    # Non-negative

    diagnostics = {
        "characteristic_length_m": float(L_char),
        "diffusivity_m2_per_s": D_surf,
        "adsorption_delay_s": float(tau_adsorption)
    }

    return tau_adsorption, diagnostics


def calculate_backflow_correction(P_j: float, config: "DeviceConfig") -> tuple[float, dict]:
    """
    Calculate backflow resistance correction.

    During displacement, continuous phase can flow backward,
    effectively reducing the driving pressure for displacement.
    """

    # Backflow model: effective pressure reduction
    # Higher P_j → more potential for backflow
    P_threshold = mbar_to_pa(config.stage_wise.Pj_normal_min_mbar)
    P_max = mbar_to_pa(config.stage_wise.Pj_normal_max_mbar)

    # Normalize pressure
    if P_max > P_threshold:
        P_normalized = (P_j - P_threshold) / (P_max - P_threshold)
        P_normalized = max(0.0, min(1.0, P_normalized))  # Clamp [0,1]
    else:
        P_normalized = 0.0

    # Backflow resistance factor: higher P_j → more resistance
    # R_factor = 1 + γ * P_norm^δ
    gamma = 1.5  # Backflow strength (to be calibrated)
    delta = 1.0  # Linear dependence on pressure

    backflow_factor = 1.0 + gamma * (P_normalized ** delta)

    diagnostics = {
        "P_j_Pa": float(P_j),
        "P_normalized": float(P_normalized),
        "backflow_factor": float(backflow_factor),
        "gamma": gamma,
        "delta": delta
    }

    return backflow_factor, diagnostics


def calculate_capillary_number_local(Q_nominal: float, config: "DeviceConfig") -> float:
    """Calculate local capillary number for interface resistance."""

    # Ca = μ * v / γ
    # v = Q / A_channel (characteristic velocity)

    mu_oil = config.fluids.mu_dispersed
    gamma = config.fluids.gamma if config.fluids.gamma > 0 else 0.015  # Default 15 mN/m

    # Characteristic velocity in microchannel
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    if A_channel <= 0:
        A_channel = 1e-12  # Avoid division by zero

    v_char = abs(Q_nominal) / A_channel

    ca = mu_oil * v_char / gamma

    return ca


# =============================================================================
# Stage 2: Bulb Growth and Necking Physics Implementation
# =============================================================================

def solve_stage2_bulb_physics(P_j: float, Q_nominal: float, config: "DeviceConfig") -> Stage2Result:
    """
    Stage 2: Droplet bulb growth and necking physics.

    Implements geometry-controlled breakup with necking time scaling.
    Based on Dangla criterion and viscocapillary necking laws.
    """

    # Geometry-controlled breakup condition (Dangla criterion)
    R_critical = calculate_critical_radius(config)
    V_critical = (4/3) * np.pi * (R_critical ** 3)

    # Necking time model
    tau_necking, necking_diagnostics = calculate_necking_time(config)

    # Bulb growth time calculation
    if config.stage_wise.use_detailed_growth:
        t_growth, growth_diagnostics = solve_detailed_bulb_growth(P_j, Q_nominal, R_critical, config)
    else:
        t_growth, growth_diagnostics = solve_simplified_bulb_growth(config)

    # Final droplet volume with necking inflation
    V_inflation = abs(Q_nominal) * tau_necking if Q_nominal > 0 else 0.0
    V_final = V_critical + V_inflation

    # Final droplet diameter
    D_droplet = (6 * V_final / np.pi) ** (1/3)

    # Total Stage 2 time
    t_total = t_growth + tau_necking

    # Regime indicators
    regime_indicators = analyze_stage2_regime(P_j, Q_nominal, config, {
        "R_critical": R_critical,
        "necking_time": tau_necking,
        "inflation_fraction": V_inflation / V_critical if V_critical > 0 else 0.0
    })

    # Combine diagnostics
    diagnostics = {
        "necking": necking_diagnostics,
        "growth": growth_diagnostics,
        "regime_analysis": regime_indicators
    }

    return Stage2Result(
        t_growth=t_growth,
        t_necking=tau_necking,
        t_total=t_total,
        D_droplet=D_droplet,
        V_droplet=V_final,
        R_critical=R_critical,
        regime_indicators=regime_indicators,
        diagnostics=diagnostics
    )


def calculate_critical_radius(config: "DeviceConfig") -> float:
    """
    Calculate critical radius for droplet breakup (Dangla criterion).

    The critical radius depends on step geometry and confinement.
    For step emulsification: R* ≈ step_height + geometry_factor * channel_width
    """

    # Step geometry parameters
    step_height = config.geometry.junction.exit_depth
    channel_width = config.geometry.junction.exit_width

    # Dangla criterion parameters (empirical from literature)
    # R* = α * h + β * w, where h=step_height, w=channel_width
    alpha = 1.2  # Step height scaling factor
    beta = 0.5   # Channel width contribution

    R_critical = alpha * step_height + beta * channel_width

    # Ensure physically reasonable bounds
    R_critical = max(R_critical, 0.5 * step_height)  # At least half step height
    R_critical = min(R_critical, 10 * step_height)   # Not more than 10x step height

    return R_critical


def calculate_necking_time(config: "DeviceConfig") -> tuple[float, dict]:
    """
    Calculate necking time based on viscocapillary scaling.

    τ_necking = f(μ_ratio, γ, geometry)
    Based on Eggers & Villermaux scaling laws for pinch-off.
    """

    # Fluid properties
    mu_dispersed = config.fluids.mu_dispersed      # Oil viscosity
    mu_continuous = config.fluids.mu_continuous    # Water viscosity
    gamma = config.fluids.gamma if config.fluids.gamma > 0 else 0.015

    # Characteristic length scale
    l_char = config.geometry.junction.exit_depth  # Step height as characteristic length

    # Viscosity ratio
    lambda_visc = mu_dispersed / mu_continuous

    # Viscocapillary necking time (Eggers scaling)
    if config.stage_wise.necking_time_model == "viscocapillary":
        # τ = (μ_d * l_char) / γ * f(λ)
        # where f(λ) is a function of viscosity ratio

        if lambda_visc < 0.1:
            # Low viscosity ratio (inviscid limit)
            f_lambda = 1.0
        elif lambda_visc > 10:
            # High viscosity ratio (viscous limit)
            f_lambda = lambda_visc ** 0.5
        else:
            # Intermediate regime
            f_lambda = 1.0 + 0.3 * np.log(lambda_visc)

        tau_necking = (mu_dispersed * l_char / gamma) * f_lambda

    elif config.stage_wise.necking_time_model == "empirical":
        # Simplified empirical model
        tau_necking = l_char ** 2 / (gamma / mu_dispersed)  # Capillary time

    else:
        # Default: simple capillary time
        tau_necking = mu_dispersed * l_char / gamma

    # Ensure reasonable bounds
    tau_necking = max(tau_necking, 1e-6)    # Minimum 1 μs
    tau_necking = min(tau_necking, 1e-3)    # Maximum 1 ms

    diagnostics = {
        "viscosity_ratio": float(lambda_visc),
        "characteristic_length_m": float(l_char),
        "surface_tension_N_per_m": float(gamma),
        "necking_model": config.stage_wise.necking_time_model,
        "necking_time_s": float(tau_necking)
    }

    return tau_necking, diagnostics


def solve_simplified_bulb_growth(config: "DeviceConfig") -> tuple[float, dict]:
    """
    Simplified bulb growth time model.

    For constant P_j assumption: growth time is primarily geometry and fluid dependent,
    weakly dependent on pressure (the "frequency ceiling" concept).
    """

    # Simplified growth time based on geometry and fluid properties
    # t_growth ≈ (V_critical / Q_characteristic)

    # Characteristic flow rate for bulb growth
    # Based on pressure difference and effective resistance during growth
    gamma = config.fluids.gamma if config.fluids.gamma > 0 else 0.015
    l_char = config.geometry.junction.exit_depth

    # Characteristic pressure (Laplace pressure at critical radius)
    R_critical = calculate_critical_radius(config)
    P_laplace = 2 * gamma / R_critical

    # Effective resistance for bulb growth (approximate)
    A_eff = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    L_eff = config.geometry.junction.exit_width  # Effective flow length
    mu_oil = config.fluids.mu_dispersed

    R_growth = (12 * mu_oil * L_eff) / (A_eff**3 / (A_eff + l_char**2))  # Modified resistance

    # Characteristic flow rate during growth
    Q_char = P_laplace / R_growth if R_growth > 0 else 1e-15

    # Critical volume
    V_critical = (4/3) * np.pi * (R_critical ** 3)

    # Growth time
    t_growth = V_critical / Q_char if Q_char > 0 else 1e-6

    # Bounds checking
    t_growth = max(t_growth, 1e-6)    # Minimum 1 μs
    t_growth = min(t_growth, 1e-2)    # Maximum 10 ms

    diagnostics = {
        "R_critical_m": float(R_critical),
        "V_critical_m3": float(V_critical),
        "P_laplace_Pa": float(P_laplace),
        "Q_characteristic_m3_per_s": float(Q_char),
        "R_growth_Pa_s_per_m3": float(R_growth),
        "t_growth_s": float(t_growth)
    }

    return t_growth, diagnostics


def solve_detailed_bulb_growth(P_j: float, Q_nominal: float, R_critical: float, config: "DeviceConfig") -> tuple[float, dict]:
    """
    Detailed bulb growth with evolving Laplace pressure.

    Integrates dV/dt = f(P_j, P_laplace(t)) until R = R_critical.
    More accurate but computationally expensive.
    """

    # This is a simplified version of detailed integration
    # Full implementation would use numerical integration (odeint, etc.)

    gamma = config.fluids.gamma if config.fluids.gamma > 0 else 0.015
    mu_oil = config.fluids.mu_dispersed

    # Estimate average Laplace pressure during growth
    R_initial = 0.5 * config.geometry.junction.exit_depth  # Initial bulb size
    P_laplace_initial = 2 * gamma / R_initial
    P_laplace_final = 2 * gamma / R_critical
    P_laplace_avg = (P_laplace_initial + P_laplace_final) / 2

    # Effective driving pressure
    P_driving_avg = max(P_j - P_laplace_avg, 0.1 * P_j)  # Ensure positive

    # Effective resistance (simplified)
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    L_channel = config.geometry.junction.exit_width
    R_eff = (12 * mu_oil * L_channel) / (A_channel ** 3)

    # Average flow rate during growth
    Q_avg = P_driving_avg / R_eff if R_eff > 0 else abs(Q_nominal)

    # Volume to grow
    V_initial = (4/3) * np.pi * (R_initial ** 3)
    V_final = (4/3) * np.pi * (R_critical ** 3)
    Delta_V = V_final - V_initial

    # Growth time
    t_growth = Delta_V / Q_avg if Q_avg > 0 else 1e-6

    # Bounds checking
    t_growth = max(t_growth, 1e-6)
    t_growth = min(t_growth, 1e-2)

    diagnostics = {
        "detailed_integration": True,
        "R_initial_m": float(R_initial),
        "R_final_m": float(R_critical),
        "P_laplace_avg_Pa": float(P_laplace_avg),
        "P_driving_avg_Pa": float(P_driving_avg),
        "Q_avg_m3_per_s": float(Q_avg),
        "Delta_V_m3": float(Delta_V),
        "t_growth_s": float(t_growth)
    }

    return t_growth, diagnostics


def analyze_stage2_regime(P_j: float, Q_nominal: float, config: "DeviceConfig", stage2_params: dict) -> dict:
    """Analyze Stage 2 regime indicators for regime detection."""

    # Pressure-driven vs geometry-dominated
    gamma = config.fluids.gamma if config.fluids.gamma > 0 else 0.015
    R_critical = stage2_params["R_critical"]
    P_laplace_critical = 2 * gamma / R_critical

    pressure_ratio = P_j / P_laplace_critical if P_laplace_critical > 0 else 1.0
    pressure_driven = pressure_ratio > 2.0  # Arbitrary threshold

    # Geometry-dominated regime
    geometry_dominated = not pressure_driven

    # Inflation significance
    inflation_fraction = stage2_params["inflation_fraction"]
    inflation_significant = inflation_fraction > 0.1  # 10% inflation threshold

    # Necking time vs growth time comparison
    necking_time = stage2_params["necking_time"]
    # Note: growth time would be calculated elsewhere, using 0.001 as placeholder
    growth_time = 0.001  # Placeholder
    necking_limited = necking_time > 0.5 * growth_time

    return {
        "pressure_driven": pressure_driven,
        "geometry_dominated": geometry_dominated,
        "inflation_significant": inflation_significant,
        "necking_limited": necking_limited,
        "pressure_ratio": float(pressure_ratio),
        "inflation_fraction": float(inflation_fraction)
    }


# =============================================================================
# Enhanced Regime Detection System
# =============================================================================

def classify_rung_regime(
    P_j: float,
    Q_avg: float,
    stage1_result: Stage1Result,
    stage2_result: Stage2Result,
    config: "DeviceConfig"
) -> tuple[RegimeClassification, str, list[str]]:
    """
    Enhanced regime classification with sequential validation.

    Primary gate: Capillary number
    Secondary validation: Flow capacity, pressure balance, growth rate mismatch
    """

    # Primary Gate: Capillary Number Classification
    ca = calculate_capillary_number_local(Q_avg, config)
    ca_regime, ca_confidence = classify_by_capillary_number(ca, config)

    # Initialize regime classification
    regime = ca_regime
    confidence = ca_confidence
    warnings = []

    # Sequential Validation (only if Ca near threshold or transitional)
    if ca_regime in [RegimeClassification.TRANSITIONAL] or ca_confidence in ["medium", "low"]:

        # A) Flow rate vs Stage 2 capacity check
        flow_check_result = validate_flow_capacity(Q_avg, stage2_result, config)
        if not flow_check_result["valid"]:
            warnings.extend(flow_check_result["warnings"])
            confidence = _downgrade_confidence(confidence)

        # B) Pressure balance check
        pressure_check_result = validate_pressure_balance(P_j, config)
        if not pressure_check_result["valid"]:
            warnings.extend(pressure_check_result["warnings"])
            confidence = _downgrade_confidence(confidence)
            if pressure_check_result["severe"]:
                regime = RegimeClassification.BLOWOUT

        # C) Growth rate mismatch check
        growth_check_result = validate_growth_rate_consistency(Q_avg, stage2_result, config)
        if not growth_check_result["valid"]:
            warnings.extend(growth_check_result["warnings"])
            if growth_check_result["transitional_oversized"]:
                regime = RegimeClassification.TRANSITIONAL_OVERSIZED

    # Final regime validation
    regime, confidence, additional_warnings = _final_regime_validation(
        regime, confidence, warnings, ca, P_j, Q_avg, config
    )
    warnings.extend(additional_warnings)

    return regime, confidence, warnings


def classify_by_capillary_number(ca: float, config: "DeviceConfig") -> tuple[RegimeClassification, str]:
    """Primary regime classification based on capillary number."""

    ca_limit = config.stage_wise.ca_dripping_limit

    if ca < 0.5 * ca_limit:
        # Well within dripping regime
        return RegimeClassification.DRIPPING, "high"
    elif ca < ca_limit:
        # Near dripping limit
        return RegimeClassification.DRIPPING, "medium"
    elif ca < 1.5 * ca_limit:
        # Transitional zone
        return RegimeClassification.TRANSITIONAL, "medium"
    elif ca < 3.0 * ca_limit:
        # Approaching jetting
        return RegimeClassification.TRANSITIONAL, "low"
    else:
        # Clear jetting regime
        return RegimeClassification.JETTING, "low"


def validate_flow_capacity(Q_avg: float, stage2_result: Stage2Result, config: "DeviceConfig") -> dict:
    """Validate oil flow rate against Stage 2 capacity."""

    # Estimate Stage 2 capacity based on necking time limitation
    # Max flow ≈ V_droplet / t_necking
    stage2_capacity = stage2_result.V_droplet / stage2_result.t_necking if stage2_result.t_necking > 0 else 1e-9

    flow_ratio = abs(Q_avg) / stage2_capacity
    flow_limit = config.stage_wise.flow_ratio_limit

    if flow_ratio < flow_limit:
        return {"valid": True, "warnings": [], "flow_ratio": flow_ratio}
    elif flow_ratio < 2 * flow_limit:
        return {
            "valid": False,
            "warnings": ["flow_approaching_stage2_limit"],
            "flow_ratio": flow_ratio
        }
    else:
        return {
            "valid": False,
            "warnings": ["flow_exceeds_stage2_capacity"],
            "flow_ratio": flow_ratio
        }


def validate_pressure_balance(P_j: float, config: "DeviceConfig") -> dict:
    """Validate junction pressure against normal operating range."""

    P_j_mbar = P_j / 100.0  # Convert Pa to mbar
    P_min = config.stage_wise.Pj_normal_min_mbar
    P_max = config.stage_wise.Pj_normal_max_mbar

    if P_min <= P_j_mbar <= P_max:
        return {"valid": True, "warnings": [], "severe": False}
    elif P_j_mbar < 0.5 * P_min:
        return {
            "valid": False,
            "warnings": ["pressure_too_low", "insufficient_driving_force"],
            "severe": True
        }
    elif P_j_mbar > 2 * P_max:
        return {
            "valid": False,
            "warnings": ["pressure_too_high", "blowout_risk"],
            "severe": True
        }
    elif P_j_mbar < P_min:
        return {
            "valid": False,
            "warnings": ["pressure_below_normal_range"],
            "severe": False
        }
    else:  # P_j_mbar > P_max
        return {
            "valid": False,
            "warnings": ["pressure_above_normal_range"],
            "severe": False
        }


def validate_growth_rate_consistency(Q_avg: float, stage2_result: Stage2Result, config: "DeviceConfig") -> dict:
    """Validate oil supply rate against natural bulb growth rate."""

    # Estimate natural bulb growth rate (simplified)
    # Based on Laplace pressure-driven growth
    gamma = config.fluids.gamma if config.fluids.gamma > 0 else 0.015
    mu_oil = config.fluids.mu_dispersed
    R_critical = stage2_result.R_critical

    # Natural growth timescale
    t_natural = mu_oil * R_critical / gamma

    # Natural volume growth rate
    V_critical = (4/3) * np.pi * (R_critical ** 3)
    natural_growth_rate = V_critical / t_natural if t_natural > 0 else 1e-15

    # Supply growth rate
    supply_growth_rate = abs(Q_avg)

    growth_ratio = supply_growth_rate / natural_growth_rate

    if growth_ratio < 2.0:
        # Normal range
        return {"valid": True, "warnings": [], "transitional_oversized": False}
    elif growth_ratio < 5.0:
        # Moderate mismatch - could lead to oversized droplets
        return {
            "valid": False,
            "warnings": ["moderate_growth_rate_mismatch"],
            "transitional_oversized": True
        }
    else:
        # Severe mismatch
        return {
            "valid": False,
            "warnings": ["severe_growth_rate_mismatch", "unstable_formation"],
            "transitional_oversized": False
        }


def _downgrade_confidence(current_confidence: str) -> str:
    """Downgrade confidence level due to validation failures."""
    if current_confidence == "high":
        return "medium"
    elif current_confidence == "medium":
        return "low"
    else:
        return "low"  # Already low


def _final_regime_validation(
    regime: RegimeClassification,
    confidence: str,
    warnings: list[str],
    ca: float,
    P_j: float,
    Q_avg: float,
    config: "DeviceConfig"
) -> tuple[RegimeClassification, str, list[str]]:
    """Final validation and regime adjustment based on multiple indicators."""

    additional_warnings = []

    # Check for conflicting indicators
    severe_warnings = [w for w in warnings if w in [
        "blowout_risk", "severe_growth_rate_mismatch", "flow_exceeds_stage2_capacity"
    ]]

    if len(severe_warnings) >= 2:
        # Multiple severe issues → likely blowout
        regime = RegimeClassification.BLOWOUT
        confidence = "low"
        additional_warnings.append("multiple_severe_issues_detected")

    # Special case: transitional oversized regime
    oversized_indicators = [w for w in warnings if "oversized" in w or "moderate_growth_rate_mismatch" in w]
    if oversized_indicators and regime == RegimeClassification.TRANSITIONAL:
        regime = RegimeClassification.TRANSITIONAL_OVERSIZED

    # Check for extremely high Ca
    ca_limit = config.stage_wise.ca_dripping_limit
    if ca > 5 * ca_limit and regime != RegimeClassification.BLOWOUT:
        regime = RegimeClassification.JETTING
        additional_warnings.append("extremely_high_capillary_number")

    # Flag uncertain predictions
    if confidence == "low":
        additional_warnings.append("predictions_may_be_unreliable")

    return regime, confidence, additional_warnings


def _analyze_regime_distribution(group_results: List[RungGroupResult]) -> dict:
    """Analyze distribution of regimes across rung groups."""

    from collections import Counter

    regimes = [gr.regime.value for gr in group_results]
    regime_counts = Counter(regimes)
    total_groups = len(group_results)

    regime_fractions = {
        regime: count / total_groups
        for regime, count in regime_counts.items()
    }

    # Identify dominant regime
    dominant_regime = max(regime_counts, key=regime_counts.get) if regime_counts else "none"
    dominant_fraction = regime_fractions.get(dominant_regime, 0.0)

    return {
        "regime_counts": dict(regime_counts),
        "regime_fractions": regime_fractions,
        "dominant_regime": dominant_regime,
        "dominant_fraction": float(dominant_fraction),
        "regime_uniformity": float(dominant_fraction)  # Fraction in dominant regime
    }


def _analyze_confidence_distribution(group_results: List[RungGroupResult]) -> dict:
    """Analyze distribution of confidence levels across rung groups."""

    from collections import Counter

    confidences = [gr.confidence_level for gr in group_results]
    confidence_counts = Counter(confidences)
    total_groups = len(group_results)

    confidence_fractions = {
        conf: count / total_groups
        for conf, count in confidence_counts.items()
    }

    # Overall confidence assessment
    high_fraction = confidence_fractions.get("high", 0.0)
    medium_fraction = confidence_fractions.get("medium", 0.0)
    low_fraction = confidence_fractions.get("low", 0.0)

    if high_fraction > 0.8:
        overall_confidence = "high"
    elif high_fraction + medium_fraction > 0.7:
        overall_confidence = "medium"
    else:
        overall_confidence = "low"

    return {
        "confidence_counts": dict(confidence_counts),
        "confidence_fractions": confidence_fractions,
        "overall_confidence": overall_confidence,
        "high_confidence_fraction": float(high_fraction)
    }


def solve_group_physics(group: Dict[str, Any], config: "DeviceConfig") -> RungGroupResult:
    """Solve Stage 1 + Stage 2 physics for a rung group"""

    P_j = group["P_oil_avg"] - group["P_water_avg"]

    # Stage 1: Displacement physics
    stage1_result = solve_stage1_displacement_physics(P_j, group["Q_avg"], config)

    # Stage 2: Bulb growth and necking physics
    stage2_result = solve_stage2_bulb_physics(P_j, group["Q_avg"], config)

    # Enhanced regime classification with sequential validation
    regime, confidence, warnings = classify_rung_regime(
        P_j, group["Q_avg"], stage1_result, stage2_result, config
    )

    return RungGroupResult(
        group_id=group["group_id"],
        rung_indices=group["rung_indices"],
        P_oil_avg=group["P_oil_avg"],
        P_water_avg=group["P_water_avg"],
        P_j_avg=P_j,
        Q_avg=group["Q_avg"],
        stage1_result=stage1_result,
        stage2_result=stage2_result,
        regime=regime,
        confidence_level=confidence,
        warnings=warnings
    )


def compute_global_metrics(group_results: List[RungGroupResult]) -> Dict[str, float]:
    """Compute device-level average metrics"""

    if not group_results:
        return {}

    # Weighted averages by number of rungs in each group
    total_rungs = sum(len(gr.rung_indices) for gr in group_results)

    avg_frequency = 0.0
    avg_diameter = 0.0

    for gr in group_results:
        weight = len(gr.rung_indices) / total_rungs
        cycle_time = gr.stage1_result.t_displacement + gr.stage2_result.t_total
        frequency = 1.0 / cycle_time if cycle_time > 0 else 0.0

        avg_frequency += weight * frequency
        avg_diameter += weight * gr.stage2_result.D_droplet

    return {
        "average_frequency_hz": avg_frequency,
        "average_diameter_m": avg_diameter,
        "total_rungs": total_rungs,
        "num_groups": len(group_results)
    }


def build_diagnostics(
    hydraulic_result: SimResult,
    group_results: List[RungGroupResult],
    pressure_analysis: Dict[str, Any],
    config: "DeviceConfig"
) -> StageWiseDiagnostics:
    """Build comprehensive diagnostic output"""

    # Stage timing analysis
    stage_timings = {
        "stage1_displacement": [gr.stage1_result.t_displacement for gr in group_results],
        "stage2_growth": [gr.stage2_result.t_growth for gr in group_results],
        "stage2_necking": [gr.stage2_result.t_necking for gr in group_results],
        "total_cycle": [gr.stage1_result.t_displacement + gr.stage2_result.t_total
                       for gr in group_results]
    }

    # Enhanced regime analysis
    regime_diagnostics = {
        "regimes": [gr.regime.value for gr in group_results],
        "confidence_levels": [gr.confidence_level for gr in group_results],
        "warnings": [gr.warnings for gr in group_results],
        "capillary_numbers": [calculate_capillary_number_local(gr.Q_avg, config) for gr in group_results],
        "regime_distribution": _analyze_regime_distribution(group_results),
        "confidence_distribution": _analyze_confidence_distribution(group_results)
    }

    return StageWiseDiagnostics(
        pressure_uniformity=pressure_analysis,
        grouping_triggered=pressure_analysis["requires_grouping"],
        num_groups=len(group_results),
        stage_timings=stage_timings,
        correction_analysis={},  # TODO: Implement
        regime_diagnostics=regime_diagnostics
    )


# =============================================================================
# Integration Interface
# =============================================================================

def solve_device(
    config: "DeviceConfig",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    P_out_mbar: float | None = None,
    method: str = "auto"
) -> StageWiseResult | SimResult:
    """
    Unified solver interface supporting both stage-wise and existing methods.

    Parameters
    ----------
    config : DeviceConfig
    Po_in_mbar, Qw_in_mlhr, P_out_mbar : float, optional
        Operating conditions
    method : str
        "auto", "stage_wise", "iterative", or "linear"

    Returns
    -------
    StageWiseResult or SimResult
        Depending on method selected
    """

    if method == "auto":
        # Auto-select based on config
        method = "stage_wise" if hasattr(config, 'stage_wise') and config.stage_wise.enabled else "iterative"

    if method == "stage_wise":
        return stage_wise_solve(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)
    elif method == "iterative":
        from stepgen.models.generator import iterative_solve
        return iterative_solve(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)
    elif method == "linear":
        from stepgen.models.hydraulics import simulate
        return simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)
    else:
        raise ValueError(f"Unknown method: {method}. Use 'auto', 'stage_wise', 'iterative', or 'linear'.")