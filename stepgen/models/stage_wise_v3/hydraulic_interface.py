"""
Stage-Wise Model v3: Hydraulic Interface Adapter
================================================

Provides HydraulicModelInterface wrapper for v3 stage-wise model to integrate
with existing CLI and model registry system.

This adapter:
- Implements HydraulicModelInterface for CLI compatibility
- Converts between v3 result format and existing interface expectations
- Maintains backward compatibility with existing workflows
- Provides proper unit conversions and result mapping
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from stepgen.models.hydraulic_models import HydraulicModelInterface, HydraulicResult
from stepgen.config import mlhr_to_m3s, mbar_to_pa

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class StageWiseV3Model(HydraulicModelInterface):
    """
    Stage-wise droplet formation model v3 with physics improvements.

    Implements HydraulicModelInterface for CLI integration while providing
    comprehensive v3 physics improvements including:
    - Two-fluid Washburn baseline for Stage 1
    - Critical size controlled snap-off for Stage 2
    - Dynamic reduced-order hydraulic network
    - Multi-factor regime classification (warning system)
    """

    def solve(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float
    ) -> HydraulicResult:
        """
        Solve hydraulic network using stage-wise v3 physics.

        Parameters
        ----------
        config : DeviceConfig
            Device configuration (must include stage_wise_v3 section)
        Po_Pa : float
            Oil inlet pressure [Pa]
        Qw_m3s : float
            Water inlet flow rate [m³/s]
        P_out_Pa : float
            Outlet pressure [Pa]

        Returns
        -------
        HydraulicResult
            Hydraulic solution with v3 physics enhancements
        """

        # Import v3 solver
        try:
            from .core import stage_wise_v3_solve
        except ImportError as e:
            raise ImportError(f"Failed to import v3 stage-wise solver: {e}")

        # Check for v3 configuration
        if not hasattr(config, 'stage_wise_v3'):
            raise ValueError(
                "Configuration missing 'stage_wise_v3' section required for v3 physics. "
                "Add stage_wise_v3 configuration or use 'stage_wise' model instead."
            )

        # Convert units for v3 solver (expects mbar, mL/hr)
        Po_mbar = Po_Pa * 1e-2  # Pa → mbar
        Qw_mlhr = Qw_m3s / mlhr_to_m3s(1.0)  # m³/s → mL/hr
        P_out_mbar = P_out_Pa * 1e-2  # Pa → mbar

        try:
            # Solve using v3 physics
            v3_result = stage_wise_v3_solve(config, Po_mbar, Qw_mlhr, P_out_mbar)

        except Exception as e:
            raise RuntimeError(f"v3 stage-wise solver failed: {e}")

        # Extract hydraulic solution for interface compatibility
        hydraulic_result = v3_result.hydraulic_result

        # Compute frequencies from v3 results
        frequencies = self._compute_frequencies_from_v3_results(v3_result, config)

        # Build comprehensive time series data
        time_series = self._build_time_series_from_v3(v3_result)

        # Convert back to HydraulicResult format for compatibility
        return HydraulicResult(
            P_oil=hydraulic_result.P_oil_dynamic,
            P_water=hydraulic_result.P_water_dynamic,
            Q_rungs=v3_result.Q_rungs,  # Uses compatibility property
            x_positions=hydraulic_result.base_result.x_positions,
            frequency_hz=frequencies,
            phase_states=self._extract_phase_states(v3_result),
            time_series=time_series
        )

    def _compute_frequencies_from_v3_results(
        self,
        v3_result: "StageWiseV3Result",
        config: "DeviceConfig"
    ) -> np.ndarray:
        """Compute per-rung frequencies from v3 grouped results."""

        N_rungs = len(v3_result.P_oil)
        frequencies = np.zeros(N_rungs)

        # Extract frequencies from group results
        for group in v3_result.group_results:
            # Compute frequency from cycle time
            t1 = group.stage1_result.t_displacement
            t2 = group.stage2_result.t_growth + group.stage2_result.t_necking
            total_cycle_time = t1 + t2

            frequency = 1.0 / total_cycle_time if total_cycle_time > 0 else 0.0

            # Apply to all rungs in this group
            for rung_idx in group.rung_indices:
                if rung_idx < N_rungs:  # Bounds check
                    frequencies[rung_idx] = frequency

        return frequencies

    def _extract_phase_states(self, v3_result: "StageWiseV3Result") -> np.ndarray:
        """Extract phase states for compatibility."""

        N_rungs = len(v3_result.P_oil)
        phase_states = np.ones(N_rungs, dtype=int)  # Default to stage 1

        # Extract current stages from group results if available
        for group in v3_result.group_results:
            # For steady-state solution, assume all rungs in Stage 1
            # Future time-dependent versions may track actual stage progression
            for rung_idx in group.rung_indices:
                if rung_idx < N_rungs:
                    phase_states[rung_idx] = 1  # Stage 1 (refill/displacement)

        return phase_states

    def _build_time_series_from_v3(self, v3_result: "StageWiseV3Result") -> dict:
        """Build comprehensive time series data from v3 results."""

        time_series = {
            "model_type": "stage_wise_v3",
            "physics_basis": "two_fluid_washburn_critical_size",
            "validation_status": self._extract_validation_summary(v3_result),
            "group_results_summary": self._summarize_group_results(v3_result)
        }

        # Add hydraulic time series if available
        hydraulic_result = v3_result.hydraulic_result
        if hasattr(hydraulic_result, 'time_series'):
            time_series["hydraulic_evolution"] = hydraulic_result.time_series

        # Add global metrics
        time_series["global_metrics"] = v3_result.global_metrics

        # Add diagnostics summary
        time_series["diagnostics_summary"] = self._summarize_diagnostics(v3_result)

        return time_series

    def _extract_validation_summary(self, v3_result: "StageWiseV3Result") -> dict:
        """Extract validation summary for time series."""

        validation = v3_result.physics_validation
        if not validation:
            return {"status": "not_validated"}

        # Count validation outcomes
        validated_components = 0
        total_components = 0
        failed_components = []

        for component, result in validation.items():
            if hasattr(result, 'status'):
                total_components += 1
                if result.status.value == "validated":
                    validated_components += 1
                elif result.status.value == "failed":
                    failed_components.append(component)

        return {
            "overall_status": "validated" if validated_components == total_components else "partial",
            "validated_components": validated_components,
            "total_components": total_components,
            "failed_components": failed_components
        }

    def _summarize_group_results(self, v3_result: "StageWiseV3Result") -> dict:
        """Summarize group results for time series."""

        summary = {
            "num_groups": len(v3_result.group_results),
            "stage1_mechanisms": [],
            "regime_classifications": [],
            "average_confidence": 0.0,
            "total_warnings": 0
        }

        total_confidence = 0.0
        for group in v3_result.group_results:
            # Stage 1 mechanisms
            if hasattr(group.stage1_result, 'mechanism'):
                summary["stage1_mechanisms"].append(group.stage1_result.mechanism)

            # Regime classifications
            if hasattr(group, 'regime_result') and hasattr(group.regime_result, 'regime'):
                regime_value = group.regime_result.regime.value if hasattr(group.regime_result.regime, 'value') else str(group.regime_result.regime)
                summary["regime_classifications"].append(regime_value)

                # Confidence
                if hasattr(group.regime_result, 'confidence'):
                    total_confidence += group.regime_result.confidence

            # Warnings
            summary["total_warnings"] += len(group.warnings)

        if len(v3_result.group_results) > 0:
            summary["average_confidence"] = total_confidence / len(v3_result.group_results)

        return summary

    def _summarize_diagnostics(self, v3_result: "StageWiseV3Result") -> dict:
        """Summarize diagnostics for time series."""

        diagnostics = v3_result.diagnostics

        return {
            "hydraulic_iterations": diagnostics.get("hydraulic_iteration", {}).get("iterations_required", 0),
            "converged": diagnostics.get("hydraulic_iteration", {}).get("converged", False),
            "grouping_used": diagnostics.get("grouping_analysis", {}).get("num_groups", 1) > 1,
            "physics_summary": diagnostics.get("physics_summary", {})
        }