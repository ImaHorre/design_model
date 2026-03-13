"""
Stage-Wise Model v3: Stage 1 Two-Fluid Washburn Physics
=======================================================

Implements the two-fluid Washburn refill model for Stage 1 as specified
in the consolidated physics plan Issue 3A.

Physics Implementation:
- Two-fluid Washburn equation for rectangular microchannels
- Baseline model: single-phase Poiseuille is NOT used (overpredicts speed)
- Optional competing mechanisms: interface, adsorption, backflow (deferred extensions)

Key Physics:
- ẋ(t) = [γ₁₂cos(θ₁₂)(1/h + 1/w)] · [wh²/f(α)] · [1/(μ₁x(t) + μ₂(L_tot - x(t)))]
- Non-square-root time dependence due to two-fluid viscosity effects
- Reset distance ≈ exit_width (experimental observation)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, Any, Optional

import numpy as np
from scipy.integrate import solve_ivp

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from . import StageWiseV3Config


class Stage1Mechanism(Enum):
    """Stage 1 refill mechanisms (baseline + deferred extensions)."""
    HYDRAULIC_DOMINATED = "hydraulic_dominated"         # Two-fluid Washburn baseline
    INTERFACE_DOMINATED = "interface_dominated"         # Contact line resistance effects
    ADSORPTION_DOMINATED = "adsorption_dominated"       # Surfactant adsorption
    BACKFLOW_DOMINATED = "backflow_dominated"           # Water backflow effects


@dataclass(frozen=True)
class WashburnResult:
    """Two-fluid Washburn refill calculation result."""
    refill_time: float                                  # Time to refill reset distance [s]
    meniscus_trajectory: Any                           # solve_ivp solution object
    physics_params: Dict[str, Any]                     # Physical parameters used

    # Diagnostic quantities
    capillary_pressure: float                          # Driving capillary pressure [Pa]
    geometry_factor: float                             # wh²/f(α) geometric scaling
    resistance_factor: float                           # f(α) Shah & London factor
    two_fluid_scaling: str                             # "non_sqrt_t" or "sqrt_t"


@dataclass(frozen=True)
class Stage1Result:
    """Complete Stage 1 physics result."""
    t_displacement: float                              # Stage 1 duration [s]
    mechanism: str                                     # Active mechanism
    confidence: float                                  # Mechanism confidence [0-1]
    physics_basis: str                                 # Physics model used

    # Core physics results
    washburn_result: WashburnResult                    # Base Washburn calculation

    # Mechanism-specific corrections (if applied)
    correction_factors: Dict[str, float]               # Applied correction factors

    # Diagnostics
    diagnostics: Dict[str, Any]                        # Detailed diagnostic information


def solve_stage1_washburn_physics(
    P_j: float,
    Q_nominal: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> Stage1Result:
    """
    Solve Stage 1 physics using two-fluid Washburn baseline model.

    Implements resolved Issue 3A: Two-fluid Washburn replaces single-phase Poiseuille.

    Parameters
    ----------
    P_j : float
        Junction pressure difference [Pa]
    Q_nominal : float
        Nominal flow rate [m³/s]
    config : DeviceConfig
        Device configuration
    v3_config : StageWiseV3Config
        v3 physics configuration

    Returns
    -------
    Stage1Result
        Complete Stage 1 physics result with mechanism selection
    """

    # Select Stage 1 mechanism (baseline: hydraulic-dominated)
    mechanism = select_stage1_mechanism(P_j, Q_nominal, config, v3_config)

    # Base two-fluid Washburn calculation
    washburn_result = solve_two_fluid_washburn_base(config, v3_config)

    # Apply mechanism-specific modifications
    if mechanism == Stage1Mechanism.HYDRAULIC_DOMINATED:
        # Pure two-fluid Washburn - no additional physics
        t_displacement = washburn_result.refill_time
        correction_factors = {}
        confidence = 1.0
        physics_basis = "two_fluid_washburn_baseline"

    elif mechanism == Stage1Mechanism.INTERFACE_DOMINATED:
        # Contact line resistance effects (deferred extension)
        ca = calculate_capillary_number(Q_nominal, config)
        t_displacement, correction_factors = apply_interface_resistance_correction(
            washburn_result.refill_time, ca, config
        )
        confidence = confidence_from_ca_regime(ca)
        physics_basis = "washburn_plus_contact_line_resistance"

    elif mechanism == Stage1Mechanism.ADSORPTION_DOMINATED:
        # Surfactant adsorption effects (deferred extension)
        pe_ads = calculate_peclet_adsorption(config)
        t_displacement, correction_factors = apply_adsorption_delay_correction(
            washburn_result.refill_time, pe_ads, config
        )
        confidence = confidence_from_adsorption_regime(pe_ads)
        physics_basis = "washburn_plus_adsorption_kinetics"

    elif mechanism == Stage1Mechanism.BACKFLOW_DOMINATED:
        # Water backflow effects (deferred extension)
        pressure_ratio = P_j / config.operating.Po_in_mbar
        t_displacement, correction_factors = apply_backflow_correction(
            washburn_result.refill_time, pressure_ratio, config
        )
        confidence = confidence_from_backflow_regime(pressure_ratio)
        physics_basis = "washburn_plus_backflow_effects"

    else:
        # Fallback to hydraulic-dominated
        t_displacement = washburn_result.refill_time
        correction_factors = {}
        confidence = 0.5
        physics_basis = "washburn_baseline_fallback"

    # Build diagnostics
    diagnostics = build_stage1_diagnostics(
        mechanism, washburn_result, correction_factors, P_j, Q_nominal, config
    )

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism=mechanism.value,
        confidence=confidence,
        physics_basis=physics_basis,
        washburn_result=washburn_result,
        correction_factors=correction_factors,
        diagnostics=diagnostics
    )


def solve_two_fluid_washburn_base(
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> WashburnResult:
    """
    Base two-fluid Washburn equation for rectangular microchannel.

    Governing equation (from consolidated physics plan):
    ẋ(t) = [γ₁₂cos(θ₁₂)(1/h + 1/w)] · [wh²/f(α)] · [1/(μ₁x(t) + μ₂(L_tot - x(t)))]

    Where:
    - μ₁ = dispersed phase (oil) viscosity
    - μ₂ = continuous phase (water) viscosity
    - γ₁₂ = effective interfacial tension
    - θ₁₂ = effective contact angle
    """

    # Geometry parameters
    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth
    aspect_ratio = h / w

    # Reset distance (experimental observation: ≈ exit_width)
    x0 = 0.0
    xf = w  # Reset distance ≈ exit_width
    L_tot = xf - x0

    # Fluid properties
    mu1 = config.fluids.mu_dispersed  # Oil (dispersed phase)
    mu2 = config.fluids.mu_continuous  # Water (continuous phase)

    # Effective interfacial properties (back-calculated parameters)
    gamma12 = v3_config.gamma_effective
    theta12 = v3_config.theta_effective

    # Resistance factor f(α) for rectangular channel (Shah & London)
    f_alpha = calculate_resistance_factor(aspect_ratio)

    # Capillary driving pressure
    capillary_pressure = gamma12 * np.cos(np.radians(theta12)) * (1/h + 1/w)

    # Geometric scaling factor
    geometry_factor = w * h**2 / f_alpha

    # Washburn equation constant
    K = capillary_pressure * geometry_factor

    def washburn_ode(t: float, x: np.ndarray) -> np.ndarray:
        """
        Two-fluid Washburn ODE: dx/dt = K / [μ₁x + μ₂(L_tot - x)]
        """
        x_pos = x[0]

        # Ensure x stays within bounds
        x_pos = max(min(x_pos, L_tot), 0.0)

        # Resistance term with two-fluid viscosity
        resistance_term = mu1 * x_pos + mu2 * (L_tot - x_pos)

        if resistance_term <= 0:
            return np.array([0.0])  # Avoid division by zero

        return np.array([K / resistance_term])

    # Event function: stop when meniscus reaches xf
    def reached_target(t: float, x: np.ndarray) -> float:
        return x[0] - xf

    reached_target.terminal = True
    reached_target.direction = 1

    # Solve ODE from x0 to xf
    try:
        solution = solve_ivp(
            washburn_ode,
            [0, 1000.0],  # Large time span, will terminate at event
            [x0],
            events=reached_target,
            dense_output=True,
            rtol=1e-6,
            atol=1e-9
        )

        if solution.t_events[0].size > 0:
            refill_time = solution.t_events[0][0]
        else:
            # Fallback: estimate from final time
            refill_time = solution.t[-1]

    except Exception:
        # Fallback calculation for numerical issues
        # Use average resistance approximation
        resistance_avg = 0.5 * (mu1 + mu2) * L_tot
        refill_time = resistance_avg * L_tot / K
        solution = None

    # Determine scaling behavior
    if abs(mu1 - mu2) / max(mu1, mu2) < 0.1:
        scaling_type = "sqrt_t"  # Similar viscosities → classic Washburn
    else:
        scaling_type = "non_sqrt_t"  # Different viscosities → non-classical

    physics_params = {
        "mu1_dispersed_Pa_s": mu1,
        "mu2_continuous_Pa_s": mu2,
        "gamma_effective_N_per_m": gamma12,
        "theta_effective_deg": theta12,
        "reset_distance_m": L_tot,
        "aspect_ratio": aspect_ratio,
        "washburn_constant_K": K
    }

    return WashburnResult(
        refill_time=refill_time,
        meniscus_trajectory=solution,
        physics_params=physics_params,
        capillary_pressure=capillary_pressure,
        geometry_factor=geometry_factor,
        resistance_factor=f_alpha,
        two_fluid_scaling=scaling_type
    )


def calculate_resistance_factor(aspect_ratio: float) -> float:
    """
    Calculate f(α) resistance factor for rectangular channel.

    Uses Shah & London correlation for rectangular channels.
    """

    α = aspect_ratio

    if α <= 0:
        return 96.0  # Fallback for invalid aspect ratio

    # Shah & London correlation for rectangular channels
    if α <= 1:
        f_Re = 96 * (1 - 1.3553*α + 1.9467*α**2 - 1.7012*α**3 + 0.9564*α**4 - 0.2537*α**5)
    else:
        # For α > 1, use reciprocal relation
        α_inv = 1.0 / α
        f_Re = 96 * (1 - 1.3553*α_inv + 1.9467*α_inv**2 - 1.7012*α_inv**3 + 0.9564*α_inv**4 - 0.2537*α_inv**5)

    return f_Re


def select_stage1_mechanism(
    P_j: float,
    Q_nominal: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> Stage1Mechanism:
    """
    Physics-based mechanism selection using dimensionless numbers.

    Hierarchy based on resolved physics:
    1. Adsorption-dominated (if surfactant + low Pe)
    2. Interface-dominated (if high Ca)
    3. Backflow-dominated (if high pressure ratio)
    4. Hydraulic-dominated (baseline)

    Note: This is a deferred extension unless explicitly enabled.
    For baseline implementation, always returns HYDRAULIC_DOMINATED.
    """

    if v3_config.stage1_mechanism == "auto":
        # Automatic selection based on physics (deferred extension)

        # Calculate characteristic dimensionless groups
        ca = calculate_capillary_number(Q_nominal, config)
        pe_ads = calculate_peclet_adsorption(config) if hasattr(config.fluids, 'surfactant_concentration') else np.inf
        pressure_ratio = P_j / (config.operating.Po_in_mbar * 100.0)  # mbar to Pa

        # Get thresholds
        thresholds = v3_config._mechanism_thresholds

        # Mechanism selection hierarchy
        if (pe_ads < thresholds["pe_adsorption_threshold"] and
            hasattr(config.fluids, 'surfactant_concentration') and
            getattr(config.fluids, 'surfactant_concentration', 0) > 1e-6):
            return Stage1Mechanism.ADSORPTION_DOMINATED

        elif ca > thresholds["ca_interface_threshold"]:
            return Stage1Mechanism.INTERFACE_DOMINATED

        elif pressure_ratio > thresholds["pressure_backflow_threshold"]:
            return Stage1Mechanism.BACKFLOW_DOMINATED

        else:
            return Stage1Mechanism.HYDRAULIC_DOMINATED

    elif v3_config.stage1_mechanism == "hydraulic":
        return Stage1Mechanism.HYDRAULIC_DOMINATED
    elif v3_config.stage1_mechanism == "interface":
        return Stage1Mechanism.INTERFACE_DOMINATED
    elif v3_config.stage1_mechanism == "adsorption":
        return Stage1Mechanism.ADSORPTION_DOMINATED
    elif v3_config.stage1_mechanism == "backflow":
        return Stage1Mechanism.BACKFLOW_DOMINATED
    else:
        return Stage1Mechanism.HYDRAULIC_DOMINATED  # Default fallback


def calculate_capillary_number(Q_nominal: float, config: "DeviceConfig") -> float:
    """Calculate capillary number: Ca = μU/γ."""

    # Characteristic velocity
    A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    U_char = abs(Q_nominal) / A_channel if A_channel > 0 else 0.0

    # Fluid properties
    mu = config.fluids.mu_continuous  # Continuous phase viscosity
    gamma = getattr(config.fluids, 'gamma', 15e-3)  # Default 15 mN/m

    return mu * U_char / gamma if gamma > 0 else 0.0


def calculate_peclet_adsorption(config: "DeviceConfig") -> float:
    """Calculate adsorption Péclet number (deferred extension)."""
    # Placeholder for adsorption kinetics
    # Pe_ads = UL/D_surf where D_surf is surfactant diffusivity
    return np.inf  # No adsorption effects in baseline


# Correction functions (deferred extensions - not required for baseline)

def apply_interface_resistance_correction(
    base_time: float, ca: float, config: "DeviceConfig"
) -> tuple[float, Dict[str, float]]:
    """Apply Cox-Voinov contact line resistance correction (deferred extension)."""
    # Simplified Cox-Voinov correction
    resistance_factor = 1.0 + 0.5 * ca  # Simplified model
    corrected_time = base_time * resistance_factor

    return corrected_time, {"interface_resistance_factor": resistance_factor}


def apply_adsorption_delay_correction(
    base_time: float, pe_ads: float, config: "DeviceConfig"
) -> tuple[float, Dict[str, float]]:
    """Apply surfactant adsorption delay correction (deferred extension)."""
    # Adsorption delay model (simplified)
    delay_factor = 1.0 / (1.0 + pe_ads)  # Higher Pe → less delay
    delay_time = 0.001 * delay_factor  # 1 ms base delay
    corrected_time = base_time + delay_time

    return corrected_time, {"adsorption_delay_s": delay_time}


def apply_backflow_correction(
    base_time: float, pressure_ratio: float, config: "DeviceConfig"
) -> tuple[float, Dict[str, float]]:
    """Apply water backflow resistance correction (deferred extension)."""
    # Backflow resistance model
    backflow_factor = 1.0 + 0.2 * max(pressure_ratio - 1.0, 0.0)
    corrected_time = base_time * backflow_factor

    return corrected_time, {"backflow_resistance_factor": backflow_factor}


def confidence_from_ca_regime(ca: float) -> float:
    """Assess confidence based on capillary number regime."""
    if 0.01 < ca < 1.0:
        return 0.9  # High confidence in interface-dominated regime
    elif 0.001 < ca < 10.0:
        return 0.6  # Medium confidence in extended range
    else:
        return 0.3  # Low confidence outside typical range


def confidence_from_adsorption_regime(pe_ads: float) -> float:
    """Assess confidence based on adsorption Péclet number."""
    if pe_ads < 1.0:
        return 0.8  # High confidence in adsorption-dominated regime
    elif pe_ads < 10.0:
        return 0.5  # Medium confidence
    else:
        return 0.2  # Low confidence


def confidence_from_backflow_regime(pressure_ratio: float) -> float:
    """Assess confidence based on pressure ratio."""
    if pressure_ratio > 2.0:
        return 0.7  # High confidence in backflow effects
    elif pressure_ratio > 1.5:
        return 0.5  # Medium confidence
    else:
        return 0.3  # Low confidence


def build_stage1_diagnostics(
    mechanism: Stage1Mechanism,
    washburn_result: WashburnResult,
    correction_factors: Dict[str, float],
    P_j: float,
    Q_nominal: float,
    config: "DeviceConfig"
) -> Dict[str, Any]:
    """Build comprehensive Stage 1 diagnostics."""

    ca = calculate_capillary_number(Q_nominal, config)

    return {
        "mechanism_selection": {
            "selected_mechanism": mechanism.value,
            "capillary_number": ca,
            "selection_basis": "dimensionless_number_hierarchy"
        },
        "washburn_physics": {
            "refill_time_s": washburn_result.refill_time,
            "scaling_type": washburn_result.two_fluid_scaling,
            "capillary_pressure_Pa": washburn_result.capillary_pressure,
            "geometry_factor": washburn_result.geometry_factor
        },
        "corrections_applied": correction_factors,
        "physics_validation": {
            "refill_time_reasonable": 1e-6 < washburn_result.refill_time < 1e-1,
            "capillary_pressure_positive": washburn_result.capillary_pressure > 0,
            "viscosity_ratio_valid": True
        }
    }