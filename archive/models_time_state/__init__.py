"""
stepgen.models.time_state
=========================
Time-state hydraulic models for enhanced droplet frequency prediction.

This module implements enhanced hydraulic models that account for the temporal
behavior of droplet forming units (DFUs) rather than assuming steady flow.

Models:
- DutyFactorModel: Empirical duty factor scaling
- TimeStateDfuModel: Physics-based cycle timing
- FillingMechanicsModel: Time-state + meniscus mechanics
"""

from .duty_factor import DutyFactorModel

__all__ = ["DutyFactorModel"]