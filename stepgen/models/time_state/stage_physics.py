"""
stepgen.models.time_state.stage_physics
=======================================
Physics calculations for stage-wise droplet formation model.

Implements the three-stage physics with distinct governing equations:
1. Stage 1: Enhanced displacement resistance (NOT using hydraulic_resistance_rectangular)
2. Stage 2: Laplace-accelerated resistance with dynamic neck effects
3. Stage 3: Minimal snap-off resistance

Each stage uses fundamentally different transport laws to capture the
observed experimental behavior where small displacement volume dominates
cycle time despite being much smaller than the final droplet volume.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class StagePhysicsCalculator:
    """
    Calculates stage-dependent resistances implementing three-stage physics.

    Critical: Does NOT reuse hydraulic_resistance_rectangular for Stage 1.
    Each stage implements its own transport law based on the physical mechanisms.
    """

    def __init__(self, config: "DeviceConfig"):
        self.config = config

        # Cache geometric properties
        self.w = config.geometry.junction.exit_width
        self.h = config.geometry.junction.exit_depth
        self.mcw = config.geometry.rung.mcw
        self.mcd = config.geometry.rung.mcd
        self.mcl = config.geometry.rung.mcl

        # Cache fluid properties
        self.mu_oil = config.fluids.mu_dispersed
        self.mu_water = config.fluids.mu_continuous

        # Cache surface tension - prefer fluid config, fallback to droplet model config
        if hasattr(config.fluids, 'gamma') and config.fluids.gamma > 0:
            self.gamma = config.fluids.gamma  # Already in N/m
        else:
            self.gamma = config.droplet_model.surface_tension_mN_m * 1e-3  # Convert mN/m → N/m

        # Compute base resistance for reference
        self.R_base = self._compute_base_resistance()

    def _compute_base_resistance(self) -> float:
        """
        Compute base hydraulic resistance for reference.

        Uses rectangular channel formula as baseline, but Stage 1 will
        apply significant enhancements to this value.
        """
        # Basic rectangular channel resistance: R = 12μL/(wh³) for w >> h
        # More accurate form with aspect ratio correction
        aspect_ratio = self.mcw / self.mcd

        if aspect_ratio >= 3.0:
            # Wide channel approximation
            resistance = (12.0 * self.mu_oil * self.mcl) / (self.mcw * self.mcd**3)
        else:
            # Moderate aspect ratio correction
            f_aspect = 1.0 - 0.63 * (self.mcd / self.mcw) * (1.0 - (self.mcd / self.mcw)**4 / 12.0)
            resistance = (12.0 * self.mu_oil * self.mcl) / (self.mcw * self.mcd**3 * f_aspect)

        return resistance

    def compute_stage_resistances(
        self,
        stage_states: np.ndarray,
        droplet_volumes: np.ndarray,
        config: "DeviceConfig",
        Q_rungs: np.ndarray = None
    ) -> np.ndarray:
        """
        Compute stage-dependent resistances for all rungs.

        Parameters
        ----------
        stage_states : np.ndarray
            Current stage (1, 2, or 3) for each rung
        droplet_volumes : np.ndarray
            Current accumulated volume for each rung [m³]
        config : DeviceConfig
            Device configuration
        Q_rungs : np.ndarray, optional
            Current flow rates for capillary number calculation [m³/s]

        Returns
        -------
        np.ndarray
            Resistance values for each rung [Pa·s/m³]
        """
        n_rungs = len(stage_states)
        resistances = np.zeros(n_rungs)

        for i in range(n_rungs):
            stage = stage_states[i]

            if stage == 1:
                # Include flow rate effects for Stage 1
                Q_rung = Q_rungs[i] if Q_rungs is not None else None
                resistances[i] = self._compute_stage1_resistance(config, Q_rung)
            elif stage == 2:
                resistances[i] = self._compute_stage2_resistance(droplet_volumes[i], config)
            elif stage == 3:
                resistances[i] = self._compute_stage3_resistance(config)
            else:
                # Fallback to base resistance
                resistances[i] = self.R_base

        return resistances

    def _compute_stage1_resistance(self, config: "DeviceConfig", Q_rung: float = None) -> float:
        """
        Stage 1: Enhanced displacement resistance with capillary number effects.

        CRITICAL: This is NOT hydraulic_resistance_rectangular.
        Implements custom displacement physics with moving contact line
        and prewetting film effects that dominate cycle time.

        Physics: Confined displacement with enhanced resistance due to:
        - Moving contact line dynamics
        - Prewetting film drainage
        - Confined geometry effects
        - Flow rate dependence via capillary number
        """
        # Get stage-wise parameters
        contact_line_factor = config.droplet_model.contact_line_resistance_factor
        prewetting_factor = config.droplet_model.prewetting_film_multiplier

        # Base enhanced displacement resistance
        R_displacement = self.R_base * contact_line_factor * prewetting_factor

        # Flow rate dependence via capillary number
        if Q_rung is not None and Q_rung > 0:
            Ca = self._compute_capillary_number(Q_rung)
            # Higher flow rates (higher Ca) → easier displacement → lower resistance
            flow_factor = 1.0 / (1.0 + 1.5 * Ca)  # Very moderate sensitivity
        else:
            flow_factor = 1.0  # No flow rate effect if Q_rung not provided

        # Additional confinement effects for very small volumes
        confinement_enhancement = 1.5  # Additional factor for confined displacement

        return R_displacement * flow_factor * confinement_enhancement

    def _compute_stage2_resistance(self, current_volume: float, config: "DeviceConfig") -> float:
        """
        Stage 2: Laplace-accelerated resistance with dynamic neck effects.

        Physics: As droplet grows, neck radius decreases, Laplace pressure increases,
        accelerating flow. Resistance decreases as neck constriction provides
        additional driving pressure.
        """
        # Get stage-wise parameters
        acceleration_factor = config.droplet_model.laplace_acceleration_factor

        # Estimate neck radius from current volume
        r_neck = self._estimate_neck_radius(current_volume)

        # Laplace pressure contribution: P_laplace = 2γ/r_neck
        P_laplace = 2.0 * self.gamma / max(r_neck, 1e-6)  # Avoid division by zero

        # Effective resistance reduction due to Laplace acceleration
        # Lower resistance = higher flow due to additional driving pressure
        R_stage2 = self.R_base * acceleration_factor

        # Additional neck geometry effects
        neck_enhancement = max(0.5, 1.0 - P_laplace / 1000.0)  # Reduce resistance for high Laplace pressure

        return R_stage2 * neck_enhancement

    def _compute_stage3_resistance(self, config: "DeviceConfig") -> float:
        """
        Stage 3: Minimal snap-off resistance.

        Physics: Rapid pinch-off with minimal resistance for fast transition.
        This stage is nearly instantaneous (~4% of cycle time).
        """
        # Very low resistance for rapid snap-off
        snap_off_fraction = 0.1  # 10% of base resistance
        return self.R_base * snap_off_fraction

    def _estimate_neck_radius(self, current_volume: float) -> float:
        """
        Estimate neck radius from accumulated droplet volume.

        Simple geometric model: neck radius decreases as volume approaches
        final droplet size, following approximately r_neck ∝ (1 - V/V_final).
        """
        # Assume spherical droplet geometry for neck estimation
        if current_volume <= 0:
            return self.h  # Initial neck radius ≈ channel depth

        # Simple linear decay model (can be refined with better geometry)
        V_final = (4.0/3.0) * np.pi * (self._estimate_final_radius())**3
        volume_fraction = min(current_volume / V_final, 0.99)  # Cap at 99%

        # Neck radius decreases linearly with volume fraction
        r_initial = self.h  # Initial neck radius
        r_minimum = self.h * 0.1  # Minimum neck radius (10% of initial)

        r_neck = r_initial * (1.0 - 0.9 * volume_fraction)
        return max(r_neck, r_minimum)

    def _estimate_final_radius(self) -> float:
        """Estimate final droplet radius from power-law model."""
        k = self.config.droplet_model.k
        a = self.config.droplet_model.a
        b = self.config.droplet_model.b

        D = k * (self.w ** a) * (self.h ** b)  # Droplet diameter [m]
        return D / 2.0

    def _compute_capillary_number(self, Q_rung: float) -> float:
        """
        Compute capillary number for flow rate effects.

        Ca = μ * v / γ

        Parameters
        ----------
        Q_rung : float
            Flow rate through the rung [m³/s]

        Returns
        -------
        float
            Capillary number (dimensionless)
        """
        # Estimate velocity from flow rate and cross-sectional area
        cross_section_area = self.w * self.h  # Junction cross-section
        velocity = Q_rung / cross_section_area if cross_section_area > 0 else 0.0

        # Capillary number: Ca = μ * v / γ
        Ca = self.mu_oil * velocity / self.gamma if self.gamma > 0 else 0.0

        return Ca