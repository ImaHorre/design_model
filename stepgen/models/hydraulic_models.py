"""
stepgen.models.hydraulic_models
===============================
Hydraulic model registry and interface for time-state enhanced models.

This module provides a registry pattern to route between different hydraulic
models while preserving the existing steady-state implementation as the default.

Model Types:
- "steady": Current implementation (iterative_solve) - UNCHANGED
- "duty_factor": Empirical duty factor scaling model
- "time_state": Time-dependent DFU state machine model
- "time_state_filling": Time-state + filling mechanics model
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Type

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from stepgen.models.hydraulics import SimResult


@dataclass(frozen=True)
class HydraulicResult:
    """Common result format for all hydraulic models."""
    # Core hydraulic solution
    P_oil: np.ndarray           # Oil pressure profile [Pa]
    P_water: np.ndarray         # Water pressure profile [Pa]
    Q_rungs: np.ndarray         # Rung flow rates [m³/s]
    x_positions: np.ndarray     # Axial positions [m]

    # Model-specific outputs
    frequency_hz: np.ndarray | None = None    # Per-rung frequencies [Hz]
    duty_factor: np.ndarray | None = None     # Per-rung duty factors
    phase_states: np.ndarray | None = None    # Time-state phase information
    time_series: dict | None = None           # Time-series data (time_state models)

    # Compatibility with existing SimResult
    @classmethod
    def from_sim_result(cls, solution: "SimResult") -> "HydraulicResult":
        """Convert existing SimResult to HydraulicResult format."""
        return cls(
            P_oil=solution.P_oil,
            P_water=solution.P_water,
            Q_rungs=solution.Q_rungs,
            x_positions=solution.x_positions,
        )


class HydraulicModelInterface(ABC):
    """Abstract interface for hydraulic models."""

    @abstractmethod
    def solve(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float
    ) -> HydraulicResult:
        """
        Solve hydraulic network for given boundary conditions.

        Parameters
        ----------
        config : DeviceConfig
            Device configuration
        Po_Pa : float
            Oil inlet pressure [Pa]
        Qw_m3s : float
            Water inlet flow rate [m³/s]
        P_out_Pa : float
            Outlet pressure [Pa]

        Returns
        -------
        HydraulicResult
            Hydraulic solution with model-specific enhancements
        """


class SteadyStateModel(HydraulicModelInterface):
    """Wrapper for existing steady-state hydraulic model (iterative_solve)."""

    def solve(
        self,
        config: "DeviceConfig",
        Po_Pa: float,
        Qw_m3s: float,
        P_out_Pa: float
    ) -> HydraulicResult:
        """Solve using existing iterative_solve - NO CHANGES to core implementation."""
        from stepgen.models.generator import iterative_solve
        from stepgen.config import mlhr_to_m3s

        # Convert units back to existing interface
        Po_mbar = Po_Pa * 1e-2  # Pa → mbar
        Qw_mlhr = Qw_m3s / mlhr_to_m3s(1.0)  # m³/s → mL/hr
        P_out_mbar = P_out_Pa * 1e-2  # Pa → mbar

        # Call existing implementation unchanged
        solution = iterative_solve(
            config,
            Po_in_mbar=Po_mbar,
            Qw_in_mlhr=Qw_mlhr,
            P_out_mbar=P_out_mbar
        )

        # Compute frequencies using the same formula as other models
        frequencies = self._compute_frequencies(config, solution.Q_rungs)

        return HydraulicResult(
            P_oil=solution.P_oil,
            P_water=solution.P_water,
            Q_rungs=solution.Q_rungs,
            x_positions=solution.x_positions,
            frequency_hz=frequencies,
            duty_factor=np.ones_like(frequencies)  # Steady-state has duty factor = 1
        )

    def _compute_frequencies(
        self,
        config: "DeviceConfig",
        Q_rungs: np.ndarray
    ) -> np.ndarray:
        """
        Compute per-rung droplet frequencies from flow rates.

        Same calculation as used in duty_factor model.
        """
        # Compute droplet diameter using existing power-law model
        w = config.geometry.junction.exit_width
        h = config.geometry.junction.exit_depth
        k = config.droplet_model.k
        a = config.droplet_model.a
        b = config.droplet_model.b

        D = k * (w ** a) * (h ** b)  # Droplet diameter [m]
        V_droplet = (4.0/3.0) * np.pi * (D/2.0)**3  # Droplet volume [m³]

        # Frequency = flow rate / droplet volume
        frequencies = Q_rungs / V_droplet

        # Handle negative or zero flows (inactive rungs)
        frequencies = np.maximum(frequencies, 0.0)

        return frequencies


class HydraulicModelRegistry:
    """Registry for hydraulic model implementations."""

    _models: Dict[str, Type[HydraulicModelInterface]] = {}

    @classmethod
    def register(cls, model_type: str, model_class: Type[HydraulicModelInterface]) -> None:
        """Register a hydraulic model implementation."""
        cls._models[model_type] = model_class

    @classmethod
    def get_model(cls, model_type: str) -> HydraulicModelInterface:
        """Get a hydraulic model instance by type."""
        # Lazy import enhanced models to avoid circular imports
        if model_type not in cls._models:
            if model_type == "duty_factor":
                from stepgen.models.time_state.duty_factor import DutyFactorModel
                cls.register(model_type, DutyFactorModel)
            elif model_type == "time_state":
                from stepgen.models.time_state.time_state_dfu import TimeStateDFUModel
                cls.register(model_type, TimeStateDFUModel)
            elif model_type == "time_state_filling":
                from stepgen.models.time_state.time_state_filling import TimeStateFillingModel
                cls.register(model_type, TimeStateFillingModel)
            elif model_type == "stage_wise":
                from stepgen.models.time_state.stage_wise_model import StageWiseModel
                cls.register(model_type, StageWiseModel)
            elif model_type == "stage_wise_v3":
                from stepgen.models.stage_wise_v3.hydraulic_interface import StageWiseV3Model
                cls.register(model_type, StageWiseV3Model)
            else:
                available = list(cls._models.keys()) + ["duty_factor", "time_state", "time_state_filling", "stage_wise", "stage_wise_v3"]
                raise ValueError(f"Unknown hydraulic model '{model_type}'. Available: {available}")

        return cls._models[model_type]()

    @classmethod
    def list_models(cls) -> list[str]:
        """List all registered model types."""
        # Include lazily-loaded models in the list
        available = list(cls._models.keys())
        for model_type in ["duty_factor", "time_state", "time_state_filling", "stage_wise", "stage_wise_v3"]:
            if model_type not in available:
                available.append(model_type)
        return available


# Register the steady-state model (existing implementation)
HydraulicModelRegistry.register("steady", SteadyStateModel)

# Enhanced models registered lazily to avoid circular imports