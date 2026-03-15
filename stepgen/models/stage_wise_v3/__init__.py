"""
Stage-Wise Model v3: Main Entry Points and Result Types
=======================================================

v3 Implementation of the stage-wise droplet formation model following the
consolidated physics plan. This module provides the main entry points and
common data structures for the v3 physics implementation.

Authoritative Physics Basis:
- Two-fluid Washburn refill for Stage 1
- Critical size (Rcrit) controlled snap-off for Stage 2
- Neck-state tracking for diagnostics and warning logic
- Dynamic reduced-order hydraulic network
- Pre-neck junction pressure definition (Pj)

Architecture:
- Modular design with physics separation aligned with resolved issues
- Each module <300 lines (vs v2 50KB monolithic file)
- Clean interfaces for testing and validation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Literal

import numpy as np

# Re-export core result types for external use
from .core import stage_wise_v3_solve, StageWiseV3Result
from .hydraulics import DynamicHydraulicResult, JunctionPressures
from .stage1_physics import Stage1Result
from .stage2_physics import Stage2Result, NeckEvolution, TransitionWarning
from .regime_classification import RegimeClassification, RegimeResult

__all__ = [
    # Main solver
    'stage_wise_v3_solve',

    # Result types
    'StageWiseV3Result',
    'DynamicHydraulicResult',
    'JunctionPressures',
    'Stage1Result',
    'Stage2Result',
    'NeckEvolution',
    'TransitionWarning',
    'RegimeClassification',
    'RegimeResult',

    # Configuration
    'StageWiseV3Config',
]


@dataclass(frozen=True)
class StageWiseV3Config:
    """
    v3 High-level physics controls following consolidated physics plan.

    This configuration addresses v2 code review issues by exposing behavior
    controls rather than low-level physics parameters. Back-calculated
    parameters are prominently featured.
    """

    # Model selection
    enabled: bool = True

    # Stage 1 calibration — viscosity correction multiplier
    # t_stage1 = stage1_viscosity_correction × V_reset / (P_j / R_rung)
    # Default 1.0; expected ~3–5× from experiment once calibrated.
    # Calibrate by fitting t_stage1 vs Po at fixed SDS concentration.
    stage1_viscosity_correction: float = 1.0

    # Physics switches
    enable_outer_phase_necking: bool = True         # Strategic: Literature-corrected necking
    enable_multi_factor_regime: bool = True         # Strategic: Multi-factor classification
    enable_design_feedback: bool = False            # Strategic: Design optimization (deferred)

    # Key physics parameters (back-calculated from experiment)
    gamma_effective: float = 15e-3                  # N/m - effective interfacial tension
    theta_effective: float = 30.0                   # degrees - effective contact angle
    R_critical_ratio: float = 0.7                   # R_crit / min(w,h) - geometry-dependent

    # Hydraulic network parameters (Issue 1: Dynamic reduced-order system)
    enable_dynamic_hydraulics: bool = True          # Enable droplet loading feedback
    hydraulic_convergence_tolerance: float = 0.01   # Convergence tolerance for iteration
    max_hydraulic_iterations: int = 10              # Maximum hydraulic-droplet iterations

    # Grouped rung simulation (Issue 10: Grouped rung architecture)
    pressure_uniformity_threshold: float = 0.05     # 5% P_j variation triggers grouping
    max_groups: int = 10                            # Maximum number of rung groups

    # Advanced physics (hidden from typical users)
    _mechanism_thresholds: dict = field(default_factory=lambda: {
        "ca_interface_threshold": 0.1,               # Interface-dominated threshold
        "pe_adsorption_threshold": 1.0,              # Adsorption-dominated threshold
        "pressure_backflow_threshold": 2.0,          # Backflow-dominated threshold
        "ca_neck_critical": 0.3,                     # Neck capillary number warning
    })

    # Validation parameters
    enable_physics_validation: bool = True          # Enable physics validation checks
    enable_transition_warnings: bool = True         # Enable regime transition warnings


# Diagnostic and warning levels
class DiagnosticLevel(Enum):
    """Diagnostic output verbosity levels."""
    MINIMAL = "minimal"      # Essential results only
    STANDARD = "standard"    # Standard diagnostics
    COMPREHENSIVE = "comprehensive"  # Full diagnostic output


class WarningLevel(Enum):
    """Warning severity levels for regime classification."""
    LOW = "low"             # Informational warnings
    MEDIUM = "medium"       # Caution recommended
    HIGH = "high"           # Action required


# Physics validation status
class PhysicsValidationStatus(Enum):
    """Physics validation outcomes."""
    VALIDATED = "validated"         # Physics checks passed
    WARNING = "warning"            # Physics checks show warnings
    FAILED = "failed"              # Physics checks failed
    NOT_VALIDATED = "not_validated" # Validation not performed


@dataclass(frozen=True)
class ValidationResult:
    """Physics validation result for a specific component."""
    component: str                              # Component being validated
    status: PhysicsValidationStatus             # Validation outcome
    checks_passed: List[str]                   # List of checks that passed
    warnings: List[str]                        # List of warnings
    failures: List[str]                        # List of failures
    recommendations: List[str]                 # Recommended actions