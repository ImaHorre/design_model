"""
stepgen.models.time_state.state_machines
========================================
Phase state machine logic for time-dependent DFU modeling.

This module implements the state machine logic for droplet forming units (DFUs)
operating in stop-go cycles. Each DFU rung transitions between three phases:

- OPEN: Normal flow operation (high conductance)
- PINCH: Blocked/high-impedance operation (very low conductance)
- RESET: Recovery phase before returning to OPEN

The state transitions are driven by:
1. Droplet formation events (OPEN → PINCH when droplet volume threshold reached)
2. Fixed timers (PINCH → RESET after tau_pinch_ms, RESET → OPEN after tau_reset_ms)

This captures the observed cycle-dependent flow gating that causes the 5-6x
frequency overprediction in the steady-state model.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class DFUPhase(IntEnum):
    """
    DFU phase states for time-dependent hydraulic modeling.

    Using IntEnum for efficient array storage and comparison.
    """
    OPEN = 0    # Normal flow operation
    PINCH = 1   # Blocked/high-impedance (droplet formed, flow restricted)
    RESET = 2   # Recovery phase (clearing, preparing for next cycle)


class PhaseStateMachine:
    """
    State machine manager for DFU phase transitions.

    Manages the phase states and timers for all DFU rungs in the device.
    Each rung operates independently with its own state and timer.
    """

    def __init__(self, N_rungs: int, config: "DeviceConfig"):
        """
        Initialize phase state machine for N_rungs DFUs.

        Parameters
        ----------
        N_rungs : int
            Number of DFU rungs in the device
        config : DeviceConfig
            Device configuration with time-state parameters
        """
        self.N = N_rungs

        # Extract timing parameters
        self.tau_pinch_ms = config.droplet_model.tau_pinch_ms
        self.tau_reset_ms = config.droplet_model.tau_reset_ms
        self.dt_ms = config.droplet_model.dt_ms

        # Initialize all rungs in OPEN phase
        self.phases = np.full(N_rungs, DFUPhase.OPEN, dtype=int)
        self.timers = np.zeros(N_rungs, dtype=float)  # Timer for current phase [ms]

    def trigger_droplet_formation(self, rung_idx: int) -> None:
        """
        Trigger droplet formation event for specified rung.

        This transitions the rung from OPEN → PINCH phase and resets its timer.
        Called when droplet volume threshold is reached.

        Parameters
        ----------
        rung_idx : int
            Index of the rung where droplet formed
        """
        if self.phases[rung_idx] == DFUPhase.OPEN:
            self.phases[rung_idx] = DFUPhase.PINCH
            self.timers[rung_idx] = 0.0

    def update_phase_timers(self, dt_ms: float | None = None) -> None:
        """
        Update phase timers and handle automatic transitions.

        Updates all rung timers and processes timer-based phase transitions:
        - PINCH → RESET after tau_pinch_ms
        - RESET → OPEN after tau_reset_ms

        Parameters
        ----------
        dt_ms : float, optional
            Time step [ms]. If None, uses self.dt_ms
        """
        if dt_ms is None:
            dt_ms = self.dt_ms

        # Update all timers
        self.timers += dt_ms

        # Handle PINCH → RESET transitions
        pinch_mask = (self.phases == DFUPhase.PINCH) & (self.timers >= self.tau_pinch_ms)
        self.phases[pinch_mask] = DFUPhase.RESET
        self.timers[pinch_mask] = 0.0

        # Handle RESET → OPEN transitions
        reset_mask = (self.phases == DFUPhase.RESET) & (self.timers >= self.tau_reset_ms)
        self.phases[reset_mask] = DFUPhase.OPEN
        self.timers[reset_mask] = 0.0

    def get_conductance_factors(self, g_pinch_frac: float) -> np.ndarray:
        """
        Get conductance scaling factors based on current phase states.

        Parameters
        ----------
        g_pinch_frac : float
            Fractional conductance during PINCH phase (e.g., 0.01 = 1% of open)

        Returns
        -------
        np.ndarray
            Conductance scaling factors for each rung:
            - OPEN: 1.0 (full conductance)
            - PINCH: g_pinch_frac (reduced conductance)
            - RESET: 1.0 (full conductance, preparing for next cycle)
        """
        factors = np.ones(self.N, dtype=float)

        # Apply reduced conductance during PINCH phase
        pinch_mask = (self.phases == DFUPhase.PINCH)
        factors[pinch_mask] = g_pinch_frac

        return factors

    def get_phase_summary(self) -> dict:
        """
        Get summary statistics of current phase distribution.

        Returns
        -------
        dict
            Phase counts and percentages for diagnostic purposes
        """
        n_open = np.sum(self.phases == DFUPhase.OPEN)
        n_pinch = np.sum(self.phases == DFUPhase.PINCH)
        n_reset = np.sum(self.phases == DFUPhase.RESET)

        return {
            "n_open": int(n_open),
            "n_pinch": int(n_pinch),
            "n_reset": int(n_reset),
            "frac_open": float(n_open) / self.N,
            "frac_pinch": float(n_pinch) / self.N,
            "frac_reset": float(n_reset) / self.N
        }

    def reset_all_phases(self) -> None:
        """Reset all rungs to OPEN phase with zero timers."""
        self.phases[:] = DFUPhase.OPEN
        self.timers[:] = 0.0