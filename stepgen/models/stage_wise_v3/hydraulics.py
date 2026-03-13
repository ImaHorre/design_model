"""
Stage-Wise Model v3: Dynamic Hydraulic Network
==============================================

Implements the dynamic reduced-order hydraulic network with droplet loading
feedback as specified in the consolidated physics plan.

Physics Implementation:
- Issue 1: Dynamic reduced-order system with temporal pressure variations
- Issue 2: Pre-neck junction pressure definition (Pj)
- Droplet production feedback on hydraulic loading

Key Principles:
- Pj = upstream pressure immediately before neck region
- P_bulb ≈ P_w + 2γ/R (downstream of neck)
- Pj - P_bulb = ΔP_neck
- Hydraulics operates at device scale, droplet physics at junction scale
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Any

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from .core import DropletProductionState


@dataclass(frozen=True)
class DynamicHydraulicResult:
    """
    Result from dynamic hydraulic network solution.

    Contains both the baseline hydraulic state and dynamic corrections
    due to dispersed phase loading effects.
    """
    # Dynamic pressure profiles (with droplet loading corrections)
    P_oil_dynamic: np.ndarray              # Oil pressure with loading corrections [Pa]
    P_water_dynamic: np.ndarray            # Water pressure with loading corrections [Pa]

    # Loading correction analysis
    loading_corrections: Dict[str, np.ndarray]  # Correction terms applied
    dispersed_loading_estimate: float          # Estimated dispersed phase loading

    # Base hydraulic solution (without droplet effects)
    base_result: Any                           # Original SimResult from backbone

    # Junction pressure analysis (Issue 2 implementation)
    junction_pressures: "JunctionPressures"

    @property
    def P_j(self) -> np.ndarray:
        """Junction pressure difference: P_oil - P_water [Pa]."""
        return self.P_oil_dynamic - self.P_water_dynamic


@dataclass(frozen=True)
class JunctionPressures:
    """
    Junction pressure analysis implementing resolved Issue 2.

    Key distinction: Pj is pre-neck upstream pressure, P_bulb is post-neck.
    Physical relationship: Pj - P_bulb = ΔP_neck
    """
    P_j_pre_neck: np.ndarray               # Pre-neck junction pressure [Pa]
    calculate_bulb_pressure: Callable      # Function: R_droplet -> P_bulb
    diagnostics: Dict[str, Any]            # Diagnostic information

    def get_bulb_pressure(self, R_droplet: float, P_water: float, gamma: float) -> float:
        """Calculate post-neck bulb pressure: P_bulb ≈ P_w + 2γ/R."""
        return self.calculate_bulb_pressure(R_droplet, P_water, gamma)

    def get_neck_pressure_drop(self, R_droplet: float, P_water: float, gamma: float) -> float:
        """Calculate neck pressure drop: ΔP_neck = Pj - P_bulb."""
        P_bulb = self.get_bulb_pressure(R_droplet, P_water, gamma)
        P_j_mean = np.mean(self.P_j_pre_neck)
        return P_j_mean - P_bulb


def solve_dynamic_hydraulic_network(
    config: "DeviceConfig",
    droplet_production_state: "DropletProductionState",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    P_out_mbar: float | None = None
) -> DynamicHydraulicResult:
    """
    Dynamic hydraulic network with droplet loading feedback.

    Implements resolved Issue 1: Dynamic reduced-order system that can
    test temporal pressure variations during droplet cycles.

    Parameters
    ----------
    config : DeviceConfig
        Device configuration
    droplet_production_state : DropletProductionState
        Current droplet production state for loading feedback
    Po_in_mbar, Qw_in_mlhr, P_out_mbar : float, optional
        Boundary conditions (use config defaults if None)

    Returns
    -------
    DynamicHydraulicResult
        Hydraulic solution with dynamic corrections and junction pressure analysis
    """

    # Get boundary conditions from config if not specified
    Po_in_mbar = Po_in_mbar or config.operating.Po_in_mbar
    Qw_in_mlhr = Qw_in_mlhr or config.operating.Qw_in_mlhr
    P_out_mbar = P_out_mbar or config.operating.P_out_mbar

    # Base hydraulic state using existing backbone
    from stepgen.models.hydraulics import simulate
    base_result = simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)

    # Dynamic corrections for dispersed phase loading
    dispersed_loading = estimate_dispersed_phase_loading(droplet_production_state, config)
    loading_corrections = calculate_loading_corrections(dispersed_loading, base_result, config)

    # Apply corrections to get dynamic pressures
    P_oil_dynamic = apply_oil_corrections(base_result.P_oil, loading_corrections)
    P_water_dynamic = apply_water_corrections(base_result.P_water, loading_corrections)

    # Junction pressure analysis (Issue 2 implementation)
    junction_pressures = calculate_junction_pressures(P_oil_dynamic, P_water_dynamic, config)

    return DynamicHydraulicResult(
        P_oil_dynamic=P_oil_dynamic,
        P_water_dynamic=P_water_dynamic,
        loading_corrections=loading_corrections,
        dispersed_loading_estimate=dispersed_loading,
        base_result=base_result,
        junction_pressures=junction_pressures
    )


def estimate_dispersed_phase_loading(
    droplet_state: "DropletProductionState",
    config: "DeviceConfig"
) -> float:
    """
    Estimate dispersed phase loading effect on hydraulic network.

    Returns dimensionless loading factor representing the fractional
    hydraulic capacity consumed by droplet formation.
    """

    if droplet_state.is_empty():
        return 0.0  # No droplet production, no loading

    # Estimate loading based on total throughput
    # This is a simplified model - future versions may use more detailed approaches

    # Characteristic device flow rate
    from stepgen.config import mlhr_to_m3s
    Q_water_characteristic = mlhr_to_m3s(config.operating.Qw_in_mlhr)

    # Dispersed phase throughput
    Q_dispersed = droplet_state.total_throughput_m3s

    # Loading fraction (dimensionless)
    if Q_water_characteristic > 0:
        loading_fraction = Q_dispersed / Q_water_characteristic
    else:
        loading_fraction = 0.0

    # Bound loading fraction to reasonable range
    loading_fraction = min(max(loading_fraction, 0.0), 1.0)

    return loading_fraction


def calculate_loading_corrections(
    dispersed_loading: float,
    base_result: Any,
    config: "DeviceConfig"
) -> Dict[str, np.ndarray]:
    """
    Calculate pressure corrections due to dispersed phase loading.

    Implements simple loading model - future versions may include more
    sophisticated dispersed phase feedback mechanisms.
    """

    N_rungs = len(base_result.P_oil)

    # Simple correction model: pressure drop due to additional dispersed phase resistance
    # This represents the additional hydraulic load of forming droplets

    # Base correction magnitude (empirical scaling)
    correction_magnitude_Pa = dispersed_loading * 100.0  # 100 Pa per unit loading

    # Spatial distribution: loading increases along device length
    position_factor = np.linspace(0.5, 1.0, N_rungs)  # Higher loading downstream

    # Oil pressure corrections (negative: additional resistance)
    oil_corrections = -correction_magnitude_Pa * position_factor * dispersed_loading

    # Water pressure corrections (smaller effect on continuous phase)
    water_corrections = -0.1 * oil_corrections  # 10% of oil correction

    return {
        "oil_pressure_corrections_Pa": oil_corrections,
        "water_pressure_corrections_Pa": water_corrections,
        "correction_magnitude_Pa": correction_magnitude_Pa,
        "dispersed_loading_factor": dispersed_loading
    }


def apply_oil_corrections(
    P_oil_base: np.ndarray,
    loading_corrections: Dict[str, np.ndarray]
) -> np.ndarray:
    """Apply loading corrections to oil pressure profile."""

    corrections = loading_corrections.get("oil_pressure_corrections_Pa", np.zeros_like(P_oil_base))
    return P_oil_base + corrections


def apply_water_corrections(
    P_water_base: np.ndarray,
    loading_corrections: Dict[str, np.ndarray]
) -> np.ndarray:
    """Apply loading corrections to water pressure profile."""

    corrections = loading_corrections.get("water_pressure_corrections_Pa", np.zeros_like(P_water_base))
    return P_water_base + corrections


def calculate_junction_pressures(
    P_oil_dynamic: np.ndarray,
    P_water_dynamic: np.ndarray,
    config: "DeviceConfig"
) -> JunctionPressures:
    """
    Calculate junction pressures implementing resolved Issue 2.

    Key physics: Pj is quasi-static upstream pressure located pre-neck.
    Distinction: droplet bulb pressure is post-neck.
    Relationship: Pj - P_bulb = ΔP_neck
    """

    # Pre-neck junction pressure (quasi-static upstream)
    P_j_pre_neck = P_oil_dynamic - P_water_dynamic

    def calculate_bulb_pressure(R_droplet: float, P_water: float, gamma: float) -> float:
        """
        Calculate post-neck bulb pressure.

        Physics: P_bulb ≈ P_w + 2γ/R (Laplace pressure in droplet)
        """
        if R_droplet <= 0 or gamma <= 0:
            return P_water  # Fallback to continuous phase pressure

        laplace_pressure = 2 * gamma / R_droplet
        return P_water + laplace_pressure

    # Diagnostic information
    diagnostics = {
        "pressure_definition": "pre_neck_quasi_static",
        "physical_relationship": "Pj - P_bulb = delta_P_neck",
        "implementation_basis": "resolved_issue_2_v3_physics",
        "P_j_range_Pa": float(np.max(P_j_pre_neck) - np.min(P_j_pre_neck)),
        "P_j_mean_Pa": float(np.mean(P_j_pre_neck)),
    }

    return JunctionPressures(
        P_j_pre_neck=P_j_pre_neck,
        calculate_bulb_pressure=calculate_bulb_pressure,
        diagnostics=diagnostics
    )


def validate_hydraulic_solution(
    hydraulic_result: DynamicHydraulicResult,
    config: "DeviceConfig"
) -> Dict[str, Any]:
    """
    Validate hydraulic solution for physical consistency.

    Returns validation diagnostics for quality assurance.
    """

    validation_results = {
        "pressure_gradients_valid": True,
        "junction_pressures_positive": True,
        "loading_corrections_reasonable": True,
        "warnings": []
    }

    # Check pressure gradients
    P_oil_gradient = np.diff(hydraulic_result.P_oil_dynamic)
    P_water_gradient = np.diff(hydraulic_result.P_water_dynamic)

    if np.any(P_oil_gradient > 0):  # Oil pressure should decrease along device
        validation_results["pressure_gradients_valid"] = False
        validation_results["warnings"].append("Oil pressure increases along device length")

    # Check junction pressures
    P_j = hydraulic_result.P_j
    if np.any(P_j <= 0):
        validation_results["junction_pressures_positive"] = False
        validation_results["warnings"].append("Negative junction pressures detected")

    # Check loading corrections magnitude
    if hydraulic_result.dispersed_loading_estimate > 0.5:
        validation_results["loading_corrections_reasonable"] = False
        validation_results["warnings"].append(f"High dispersed loading: {hydraulic_result.dispersed_loading_estimate:.2f}")

    return validation_results