"""
DEFUNCT — March 2026
====================
This module implemented a two-fluid Washburn ODE through the junction exit zone
(L_r ≈ 15 µm) as the Stage 1 refill model. It is superseded by the simplified
Poiseuille model in stage1_physics.py (active file).

Reason for replacement:
  The Washburn ODE through the 15 µm junction exit predicts ~0.2 ms refill at
  200–300 mbar, orders of magnitude too fast relative to experiment (~1 s).
  The correct rate-limiting step is flow delivery through the rung (R_rung >> R_exit
  by ~500×). The simplified Poiseuille model uses V_reset/Q_rung directly, gives
  the right order of magnitude, and is calibrated via a single viscosity correction
  factor (stage1_viscosity_correction in StageWiseV3Config).

  See stage1_slowdown_mechanisms_research.md for discussion of the candidate
  mechanisms contributing to the viscosity correction factor (expected ~3–5×).

Do not import this file in production code.
====================

Stage-Wise Model v3: Stage 1 Two-Fluid Washburn Physics
=======================================================

Implements the network-driven two-fluid Washburn refill model for Stage 1.

Physics (consolidated physics plan A3, updated March 15 2026):

    ΔP_drive = P_j − P_cap

    dx/dt = ΔP_drive · h²/f(α) · 1/(μ_oil·x + μ_water·(L_r − x))

where:
  - P_j = P_oil − P_water from the hydraulic network (pre-neck junction pressure difference)
  - P_cap = γ cos(θ_eff) · (1/h + 1/w)  [capillary BARRIER, opposes oil advance,
            hydrophilic channel — SDS/water continuous, vegetable oil dispersed]
  - h, w = rung channel dimensions (mcw, mcd) — NOT junction exit dimensions
  - L_r  = reset distance ≈ exit_width  (separate from channel dims)
  - f(α) = Shah & London rectangular-channel resistance factor
  - geometry factor is h²/f(α)  [NOT wh²/f(α) — that extra w is a known derivation error]

Key properties:
  - Refill speed increases with P_j (and therefore with Po) — required physical behaviour
  - Pure capillary-only Washburn recovered in the limit P_j → P_cap
  - Single-phase Poiseuille is NOT used (overpredicts speed)
  - Optional competing mechanisms (interface, adsorption, backflow) are deferred extensions
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

    # Driving pressure decomposition
    driving_pressure_Pa: float                         # ΔP_drive = P_j − P_cap [Pa]
    P_j_hydraulic: float                               # P_j from network [Pa]
    capillary_pressure: float                          # P_cap barrier [Pa] (opposes advance)

    # Channel geometry used
    geometry_factor: float                             # h²/f(α) — correct form, no extra w
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

    # Base two-fluid Washburn calculation — P_j drives refill alongside capillary pressure
    washburn_result = solve_two_fluid_washburn_base(P_j, config, v3_config)

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
    P_j: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> WashburnResult:
    """
    Network-driven two-fluid Washburn refill for rectangular microchannel.

    Governing equation (consolidated physics plan A3):

        dx/dt = (P_j − P_cap) · h²/f(α) / (μ_oil·x + μ_water·(L_r − x))

    where:
      P_j   = P_oil − P_water from the hydraulic network [Pa]
      P_cap = γ cos(θ_eff) · (1/h + 1/w)  [capillary barrier, opposes oil advance]
      h, w  = junction exit dimensions (exit_depth, exit_width) — the reset zone geometry
      L_r   = exit_width  (reset distance ≈ one junction exit width)
      f(α)  = Shah & London factor, α = h/w (junction exit aspect ratio)

    The rung (mcd, mcw) is the long upstream channel whose resistance is already
    captured in P_j from the hydraulic network. It does NOT appear in this ODE.

    Note: geometry factor is h²/f(α). The form wh²/f(α) contains a spurious w and is wrong.
    """

    # Junction exit dimensions — the reset zone the meniscus moves through
    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth
    aspect_ratio = h / w  # α < 1 for a wider-than-deep junction exit

    # Reset distance — the oil was pushed back approximately one junction exit width
    L_r = config.geometry.junction.exit_width

    # Fluid properties
    mu_oil = config.fluids.mu_dispersed    # Oil (dispersed phase, advancing)
    mu_water = config.fluids.mu_continuous  # Water (continuous phase, displaced)

    # Effective interfacial properties (calibration parameters)
    gamma12 = v3_config.gamma_effective
    theta12 = v3_config.theta_effective

    # Resistance factor f(α) for rectangular channel (Shah & London)
    f_alpha = calculate_resistance_factor(aspect_ratio)

    # Capillary barrier: opposes oil advance in hydrophilic (SDS/water) channel
    capillary_pressure = gamma12 * np.cos(np.radians(theta12)) * (1/h + 1/w)

    # Net driving pressure: hydraulic network minus capillary barrier
    delta_P_drive = P_j - capillary_pressure

    # Geometry factor — correct form h²/f(α), no extra w
    geometry_factor = h**2 / f_alpha

    # ODE constant K = ΔP_drive · h²/f(α)
    K = delta_P_drive * geometry_factor

    # Handle no-refill condition: driving pressure cannot overcome capillary barrier
    if delta_P_drive <= 0:
        resistance_avg = 0.5 * (mu_oil + mu_water) * L_r
        # Analytical estimate using |K| to give a finite (large) time with correct sign
        fallback_time = resistance_avg * L_r / max(abs(K), 1e-30)
        scaling_type = "non_sqrt_t"
        physics_params = {
            "mu_oil_Pa_s": mu_oil,
            "mu_water_Pa_s": mu_water,
            "gamma_effective_N_per_m": gamma12,
            "theta_effective_deg": theta12,
            "reset_distance_m": L_r,
            "junction_exit_width_m": w,
            "junction_exit_depth_m": h,
            "aspect_ratio": aspect_ratio,
            "P_j_Pa": P_j,
            "capillary_barrier_Pa": capillary_pressure,
            "delta_P_drive_Pa": delta_P_drive,
            "warning": "ΔP_drive ≤ 0: hydraulic pressure cannot overcome capillary barrier"
        }
        return WashburnResult(
            refill_time=fallback_time,
            meniscus_trajectory=None,
            physics_params=physics_params,
            driving_pressure_Pa=delta_P_drive,
            P_j_hydraulic=P_j,
            capillary_pressure=capillary_pressure,
            geometry_factor=geometry_factor,
            resistance_factor=f_alpha,
            two_fluid_scaling=scaling_type
        )

    def washburn_ode(t: float, x: np.ndarray) -> np.ndarray:
        """dx/dt = K / (μ_oil·x + μ_water·(L_r − x))"""
        x_pos = max(min(x[0], L_r), 0.0)
        resistance_term = mu_oil * x_pos + mu_water * (L_r - x_pos)
        if resistance_term <= 0:
            return np.array([0.0])
        return np.array([K / resistance_term])

    def reached_target(t: float, x: np.ndarray) -> float:
        return x[0] - L_r

    reached_target.terminal = True
    reached_target.direction = 1

    try:
        solution = solve_ivp(
            washburn_ode,
            [0, 10.0],  # 10 s upper bound; should terminate at event well before this
            [0.0],
            events=reached_target,
            dense_output=True,
            rtol=1e-6,
            atol=1e-12
        )

        if solution.t_events[0].size > 0:
            refill_time = float(solution.t_events[0][0])
        else:
            refill_time = float(solution.t[-1])

    except Exception:
        resistance_avg = 0.5 * (mu_oil + mu_water) * L_r
        refill_time = resistance_avg * L_r / K
        solution = None

    scaling_type = "sqrt_t" if abs(mu_oil - mu_water) / max(mu_oil, mu_water) < 0.1 else "non_sqrt_t"

    physics_params = {
        "mu_oil_Pa_s": mu_oil,
        "mu_water_Pa_s": mu_water,
        "gamma_effective_N_per_m": gamma12,
        "theta_effective_deg": theta12,
        "reset_distance_m": L_r,
        "junction_exit_width_m": w,
        "junction_exit_depth_m": h,
        "aspect_ratio": aspect_ratio,
        "P_j_Pa": P_j,
        "capillary_barrier_Pa": capillary_pressure,
        "delta_P_drive_Pa": delta_P_drive,
        "washburn_constant_K": K
    }

    return WashburnResult(
        refill_time=refill_time,
        meniscus_trajectory=solution,
        physics_params=physics_params,
        driving_pressure_Pa=delta_P_drive,
        P_j_hydraulic=P_j,
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
            "P_j_hydraulic_Pa": washburn_result.P_j_hydraulic,
            "capillary_barrier_Pa": washburn_result.capillary_pressure,
            "driving_pressure_Pa": washburn_result.driving_pressure_Pa,
            "geometry_factor_h2_over_falpha": washburn_result.geometry_factor
        },
        "corrections_applied": correction_factors,
        "physics_validation": {
            "refill_time_reasonable": 1e-6 < washburn_result.refill_time < 1.0,
            "driving_pressure_positive": washburn_result.driving_pressure_Pa > 0,
            "capillary_barrier_positive": washburn_result.capillary_pressure > 0,
            "hydraulic_driving_dominant": washburn_result.P_j_hydraulic > washburn_result.capillary_pressure
        }
    }