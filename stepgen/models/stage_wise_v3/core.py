"""
Stage-Wise Model v3: Core Solver and Orchestration
==================================================

Main solver implementing the iterative hydraulic-droplet coupling with
grouped rung simulation as specified in the consolidated physics plan.

Physics Implementation:
- Issue 10: Event-based droplet cycle simulation with hydraulic iteration
- Issue 1: Dynamic reduced-order hydraulic network
- Grouped rung simulation for computational efficiency

Architecture:
- Clean separation of hydraulics, droplet physics, and diagnostics
- Iterative coupling until convergence
- Comprehensive result aggregation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Dict, Any

import numpy as np

from .hydraulics import solve_dynamic_hydraulic_network, DynamicHydraulicResult
from .stage1_physics import solve_stage1_physics
from .stage2_physics import solve_stage2_critical_size_with_tracking
from .regime_classification import classify_regime_multi_factor
from .stage2_physics import generate_transition_warnings
from .validation import validate_physics_implementation

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from . import StageWiseV3Config


@dataclass(frozen=True)
class DropletProductionState:
    """
    State of droplet production for hydraulic feedback calculation.

    This represents the current state of droplet formation across all rungs
    and is used to calculate dispersed phase loading on the hydraulic network.
    """
    # Per-rung droplet production rates
    production_rates_m3s: np.ndarray | None = None      # Droplet volume production [m³/s]
    average_cycle_times_s: np.ndarray | None = None     # Average cycle times [s]
    current_stages: np.ndarray | None = None             # Current stage for each rung (1, 2)

    # Aggregate production metrics
    total_throughput_m3s: float = 0.0                    # Total dispersed phase throughput
    average_frequency_hz: float = 0.0                    # Device-average frequency

    def is_empty(self) -> bool:
        """Check if this is an empty/initial state."""
        return self.production_rates_m3s is None


@dataclass(frozen=True)
class RungGroupResult:
    """Results for a group of rungs with similar hydraulic conditions."""
    group_id: int
    rung_indices: List[int]                             # Which rungs are in this group

    # Average hydraulic conditions
    P_oil_avg: float                                    # Average oil pressure [Pa]
    P_water_avg: float                                  # Average water pressure [Pa]
    P_j_avg: float                                      # Average junction pressure difference [Pa]
    Q_avg: float                                        # Average rung flow rate [m³/s]

    # Physics results
    stage1_result: Any                                  # Stage1Result
    stage2_result: Any                                  # Stage2Result
    regime_result: Any                                  # RegimeResult

    # Quality metrics
    confidence_level: str                               # "high", "medium", "low"
    warnings: List[str]                                # Physics warnings for this group


@dataclass(frozen=True)
class StageWiseV3Result:
    """Complete v3 stage-wise model result with comprehensive diagnostics."""

    # Core hydraulic solution
    hydraulic_result: DynamicHydraulicResult           # Hydraulic network solution

    # Grouped physics results
    group_results: List[RungGroupResult]               # Per-group droplet physics

    # Device-level aggregated metrics
    global_metrics: Dict[str, float]                   # Device-average quantities

    # Validation and diagnostics
    physics_validation: Dict[str, Any]                 # Physics validation results
    diagnostics: Dict[str, Any]                        # Comprehensive diagnostics

    # Compatibility properties for existing interface
    @property
    def P_oil(self) -> np.ndarray:
        """Oil pressure profile for backward compatibility."""
        return self.hydraulic_result.P_oil_dynamic

    @property
    def P_water(self) -> np.ndarray:
        """Water pressure profile for backward compatibility."""
        return self.hydraulic_result.P_water_dynamic

    @property
    def Q_rungs(self) -> np.ndarray:
        """Rung flow rates for backward compatibility."""
        # Reconstruct from group results
        Q_rungs = np.zeros(len(self.P_oil))
        for group in self.group_results:
            for rung_idx in group.rung_indices:
                Q_rungs[rung_idx] = group.Q_avg
        return Q_rungs


def stage_wise_v3_solve(
    config: "DeviceConfig",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    P_out_mbar: float | None = None,
) -> StageWiseV3Result:
    """
    Main v3 solver with iterative hydraulic-droplet coupling.

    Implements resolved Issue 10: Event-based droplet cycle simulation
    coupled iteratively with device-scale hydraulic network.

    Parameters
    ----------
    config : DeviceConfig
        Device configuration including stage_wise_v3 section
    Po_in_mbar : float, optional
        Oil inlet pressure [mbar]
    Qw_in_mlhr : float, optional
        Water inlet flow [mL/hr]
    P_out_mbar : float, optional
        Outlet pressure [mbar]

    Returns
    -------
    StageWiseV3Result
        Complete v3 physics results with validation and diagnostics
    """

    # Get v3 configuration
    v3_config = getattr(config, 'stage_wise_v3', None)
    if v3_config is None:
        raise ValueError("Configuration missing 'stage_wise_v3' section required for v3 physics")

    # Initial hydraulic state
    droplet_state = DropletProductionState()

    # Iterative hydraulic-droplet coupling
    converged = False
    iteration = 0

    while not converged and iteration < v3_config.max_hydraulic_iterations:
        # 1. Solve dynamic hydraulic network with droplet loading feedback
        hydraulic_result = solve_dynamic_hydraulic_network(
            config, droplet_state, Po_in_mbar, Qw_in_mlhr, P_out_mbar
        )

        # 2. Create rung groups based on pressure uniformity
        rung_groups = create_adaptive_rung_groups_v3(hydraulic_result, v3_config)

        # 3. Solve droplet physics for each group
        group_results = []
        for group in rung_groups:
            group_result = solve_droplet_physics_for_group_v3(group, config, v3_config)
            group_results.append(group_result)

        # 4. Update droplet production state
        new_droplet_state = aggregate_droplet_production(group_results, config)

        # 5. Check convergence
        converged = check_hydraulic_convergence(
            droplet_state, new_droplet_state, v3_config.hydraulic_convergence_tolerance
        )

        droplet_state = new_droplet_state
        iteration += 1

    # Generate global metrics
    global_metrics = compute_global_metrics(group_results, hydraulic_result)

    # Physics validation (if enabled)
    physics_validation = {}
    if v3_config.enable_physics_validation:
        physics_validation = validate_physics_implementation(config, group_results)

    # Comprehensive diagnostics
    diagnostics = build_comprehensive_diagnostics(
        hydraulic_result, group_results, iteration, converged, config
    )

    return StageWiseV3Result(
        hydraulic_result=hydraulic_result,
        group_results=group_results,
        global_metrics=global_metrics,
        physics_validation=physics_validation,
        diagnostics=diagnostics
    )


def create_adaptive_rung_groups_v3(
    hydraulic_result: DynamicHydraulicResult,
    v3_config: "StageWiseV3Config"
) -> List[Dict[str, Any]]:
    """
    Create rung groups based on pressure uniformity analysis.

    Implements grouped rung simulation for computational efficiency
    while preserving spatial pressure variations.
    """

    # Calculate junction pressures (Issue 2: Pre-neck pressure definition)
    P_j = hydraulic_result.P_oil_dynamic - hydraulic_result.P_water_dynamic
    P_j_range = np.max(P_j) - np.min(P_j)
    P_j_mean = np.mean(P_j)

    # Determine if grouping is needed
    relative_variation = P_j_range / P_j_mean if P_j_mean > 0 else 0.0
    requires_grouping = relative_variation > v3_config.pressure_uniformity_threshold

    if not requires_grouping:
        # Single group for uniform conditions
        N_rungs = len(P_j)
        return [{
            "group_id": 0,
            "rung_indices": list(range(N_rungs)),
            "P_oil_avg": float(np.mean(hydraulic_result.P_oil_dynamic)),
            "P_water_avg": float(np.mean(hydraulic_result.P_water_dynamic)),
            "P_j_avg": float(np.mean(P_j)),
            "Q_avg": float(np.mean(hydraulic_result.base_result.Q_rungs))
        }]
    else:
        # Multiple groups for varying conditions
        N_rungs = len(P_j)
        n_groups = min(v3_config.max_groups, N_rungs // 2)  # At least 2 rungs per group

        groups = []
        for i in range(n_groups):
            start_idx = i * N_rungs // n_groups
            end_idx = (i + 1) * N_rungs // n_groups
            rung_indices = list(range(start_idx, end_idx))

            groups.append({
                "group_id": i,
                "rung_indices": rung_indices,
                "P_oil_avg": float(np.mean(hydraulic_result.P_oil_dynamic[start_idx:end_idx])),
                "P_water_avg": float(np.mean(hydraulic_result.P_water_dynamic[start_idx:end_idx])),
                "P_j_avg": float(np.mean(P_j[start_idx:end_idx])),
                "Q_avg": float(np.mean(hydraulic_result.base_result.Q_rungs[start_idx:end_idx]))
            })

        return groups


def solve_droplet_physics_for_group_v3(
    group: Dict[str, Any],
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> RungGroupResult:
    """Solve droplet physics for a single rung group."""

    P_j = group["P_j_avg"]
    Q_nominal = group["Q_avg"]

    # Stage 1: Simplified Poiseuille refill (V_reset / Q_rung × C_visc)
    stage1_result = solve_stage1_physics(P_j, Q_nominal, config, v3_config)

    # Stage 2: Critical size with neck tracking (Issue 4)
    stage2_result = solve_stage2_critical_size_with_tracking(P_j, config, v3_config)

    # Multi-factor regime classification (Issue 9 + Strategic improvement)
    regime_result = classify_regime_multi_factor(P_j, Q_nominal, config, v3_config)

    # Generate transition warnings if enabled
    warnings = []
    if v3_config.enable_transition_warnings and hasattr(stage2_result, 'neck_evolution'):
        warnings = generate_transition_warnings(
            stage2_result.neck_evolution, stage2_result, config, v3_config
        )

    return RungGroupResult(
        group_id=group["group_id"],
        rung_indices=group["rung_indices"],
        P_oil_avg=group["P_oil_avg"],
        P_water_avg=group["P_water_avg"],
        P_j_avg=P_j,
        Q_avg=Q_nominal,
        stage1_result=stage1_result,
        stage2_result=stage2_result,
        regime_result=regime_result,
        confidence_level=_assess_group_confidence(regime_result, warnings),
        warnings=[str(w) for w in warnings]
    )


def aggregate_droplet_production(
    group_results: List[RungGroupResult],
    config: "DeviceConfig"
) -> DropletProductionState:
    """Aggregate group results to overall droplet production state."""

    # Calculate production rates from group results
    N_rungs = sum(len(group.rung_indices) for group in group_results)
    production_rates = np.zeros(N_rungs)
    cycle_times = np.zeros(N_rungs)

    total_throughput = 0.0
    total_frequency = 0.0

    for group in group_results:
        # Estimate droplet volume from Stage 2 results
        if hasattr(group.stage2_result, 'V_droplet'):
            V_droplet = group.stage2_result.V_droplet
        else:
            # Fallback to geometric estimate
            V_droplet = (4/3) * np.pi * (group.stage2_result.R_critical ** 3)

        # Production rate = Q / V_droplet
        group_production_rate = group.Q_avg / V_droplet if V_droplet > 0 else 0.0

        # Total cycle time
        cycle_time = group.stage1_result.t_displacement + group.stage2_result.t_growth

        # Fill production arrays for rungs in this group
        for rung_idx in group.rung_indices:
            production_rates[rung_idx] = group_production_rate
            cycle_times[rung_idx] = cycle_time

        # Accumulate totals
        total_throughput += group.Q_avg * len(group.rung_indices)
        total_frequency += group_production_rate * len(group.rung_indices)

    average_frequency = total_frequency / N_rungs if N_rungs > 0 else 0.0

    return DropletProductionState(
        production_rates_m3s=production_rates,
        average_cycle_times_s=cycle_times,
        current_stages=np.ones(N_rungs, dtype=int),  # Assume all in Stage 1 for steady state
        total_throughput_m3s=total_throughput,
        average_frequency_hz=average_frequency
    )


def check_hydraulic_convergence(
    old_state: DropletProductionState,
    new_state: DropletProductionState,
    tolerance: float
) -> bool:
    """Check convergence of hydraulic-droplet iteration."""

    if old_state.is_empty():
        return False  # First iteration, not converged

    # Check relative change in total throughput
    old_throughput = old_state.total_throughput_m3s
    new_throughput = new_state.total_throughput_m3s

    if old_throughput == 0 and new_throughput == 0:
        return True  # Both zero, converged

    if old_throughput == 0:
        return False  # Was zero, now non-zero, not converged

    relative_change = abs(new_throughput - old_throughput) / old_throughput
    return relative_change < tolerance


def compute_global_metrics(
    group_results: List[RungGroupResult],
    hydraulic_result: DynamicHydraulicResult
) -> Dict[str, float]:
    """Compute device-level aggregated metrics."""

    total_rungs = sum(len(group.rung_indices) for group in group_results)

    if total_rungs == 0:
        return {}

    # Weighted averages
    total_flow = 0.0
    total_frequency = 0.0
    total_diameter = 0.0

    for group in group_results:
        n_rungs = len(group.rung_indices)
        weight = n_rungs / total_rungs

        total_flow += group.Q_avg * n_rungs

        # Estimate frequency from cycle time
        cycle_time = group.stage1_result.t_displacement + group.stage2_result.t_growth
        frequency = 1.0 / cycle_time if cycle_time > 0 else 0.0
        total_frequency += frequency * n_rungs

        # Diameter from critical radius
        diameter = 2.0 * group.stage2_result.R_critical
        total_diameter += diameter * n_rungs

    return {
        "average_flow_rate_m3s": total_flow / total_rungs,
        "average_frequency_hz": total_frequency / total_rungs,
        "average_diameter_m": total_diameter / total_rungs,
        "total_throughput_m3s": total_flow,
        "total_rungs": float(total_rungs)
    }


def build_comprehensive_diagnostics(
    hydraulic_result: DynamicHydraulicResult,
    group_results: List[RungGroupResult],
    iteration: int,
    converged: bool,
    config: "DeviceConfig"
) -> Dict[str, Any]:
    """Build comprehensive diagnostic information."""

    return {
        "hydraulic_iteration": {
            "iterations_required": iteration,
            "converged": converged,
            "dynamic_corrections_applied": hasattr(hydraulic_result, 'loading_corrections')
        },
        "grouping_analysis": {
            "num_groups": len(group_results),
            "group_sizes": [len(group.rung_indices) for group in group_results],
            "pressure_uniformity": _analyze_pressure_uniformity(hydraulic_result)
        },
        "physics_summary": {
            "stage1_mechanisms": [group.stage1_result.mechanism if hasattr(group.stage1_result, 'mechanism') else 'washburn' for group in group_results],
            "regime_classifications": [group.regime_result.regime.value if hasattr(group.regime_result, 'regime') else 'unknown' for group in group_results]
        }
    }


def _assess_group_confidence(regime_result: Any, warnings: List[Any]) -> str:
    """Assess confidence level for a group based on regime and warnings."""

    if len(warnings) == 0:
        return "high"
    elif len(warnings) <= 2:
        return "medium"
    else:
        return "low"


def _analyze_pressure_uniformity(hydraulic_result: DynamicHydraulicResult) -> Dict[str, float]:
    """Analyze pressure uniformity across the device."""

    P_j = hydraulic_result.P_oil_dynamic - hydraulic_result.P_water_dynamic

    return {
        "P_j_range_Pa": float(np.max(P_j) - np.min(P_j)),
        "P_j_mean_Pa": float(np.mean(P_j)),
        "P_j_std_Pa": float(np.std(P_j)),
        "relative_variation": float((np.max(P_j) - np.min(P_j)) / np.mean(P_j)) if np.mean(P_j) > 0 else 0.0
    }