"""
stepgen.models.time_state.filling_mechanics
===========================================
Filling mechanics enhancements for time-state hydraulic models.

This module implements detailed meniscus mechanics and effective droplet volume
corrections that account for:

1. **Meniscus retreat/advance mechanics**: Each droplet formation cycle involves
   meniscus retreat that must be refilled before the next droplet can form.

2. **Effective droplet volume**: The actual volume consumed per droplet includes
   both the spherical droplet volume and in-channel volume up to the breakup plane.

3. **Enhanced cycle frequency**: Accounts for refill volume and blocked time:
   f = Q_open / (V_d_eff + V_refill + Q_open * T_block)

These refinements should bring the time-state model predictions closer to
experimental observations by capturing more detailed microfluidic physics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


class FillingMechanics:
    """
    Filling mechanics calculator for enhanced droplet volume modeling.

    This class encapsulates the physics of meniscus retreat/advance and
    effective volume calculations for droplet formation cycles.
    """

    def __init__(self, config: "DeviceConfig"):
        """
        Initialize filling mechanics with device configuration.

        Parameters
        ----------
        config : DeviceConfig
            Device configuration containing geometry and droplet model parameters
        """
        self.config = config

        # Extract filling mechanics parameters
        self.L_retreat_um = config.droplet_model.L_retreat_um
        self.L_breakup_um = config.droplet_model.L_breakup_um

        # Convert to SI units
        self.L_retreat_m = self.L_retreat_um * 1e-6  # µm → m
        self.L_breakup_m = self.L_breakup_um * 1e-6  # µm → m

        # Calculate DFU cross-sectional area
        self.A_DFU = self._compute_dfu_area()

    def _compute_dfu_area(self) -> float:
        """
        Compute DFU cross-sectional area for volume calculations.

        Uses junction exit dimensions as the effective area for
        meniscus retreat and in-channel volume calculations.

        Returns
        -------
        float
            DFU cross-sectional area [m²]
        """
        w = self.config.geometry.junction.exit_width
        h = self.config.geometry.junction.exit_depth
        return w * h

    def compute_baseline_droplet_volume(self) -> float:
        """
        Compute baseline spherical droplet volume using power-law model.

        Returns
        -------
        float
            Spherical droplet volume [m³]
        """
        w = self.config.geometry.junction.exit_width
        h = self.config.geometry.junction.exit_depth
        k = self.config.droplet_model.k
        a = self.config.droplet_model.a
        b = self.config.droplet_model.b

        D = k * (w ** a) * (h ** b)  # Droplet diameter [m]
        V_sphere = (4.0/3.0) * np.pi * (D/2.0)**3  # Spherical volume [m³]

        return V_sphere

    def compute_refill_volume(self) -> float:
        """
        Compute refill volume per droplet formation cycle.

        The meniscus retreats by L_retreat during droplet formation,
        creating a volume that must be refilled before the next cycle.

        V_refill = A_DFU * L_retreat

        Returns
        -------
        float
            Refill volume per cycle [m³]
        """
        return self.A_DFU * self.L_retreat_m

    def compute_effective_droplet_volume(self) -> float:
        """
        Compute effective droplet volume including in-channel contributions.

        The effective volume includes:
        1. Spherical droplet volume (V_sphere)
        2. In-channel volume from breakup plane (A_DFU * L_breakup)

        V_d_eff = V_sphere + A_DFU * L_breakup

        Returns
        -------
        float
            Effective droplet volume [m³]
        """
        V_sphere = self.compute_baseline_droplet_volume()
        V_in_channel = self.A_DFU * self.L_breakup_m

        return V_sphere + V_in_channel

    def compute_total_cycle_volume(self) -> float:
        """
        Compute total volume that must flow through DFU per droplet cycle.

        This includes both the effective droplet volume and the refill volume:
        V_total = V_d_eff + V_refill

        Returns
        -------
        float
            Total cycle volume [m³]
        """
        V_d_eff = self.compute_effective_droplet_volume()
        V_refill = self.compute_refill_volume()

        return V_d_eff + V_refill

    def estimate_cycle_frequency(self, Q_flow: float, T_blocked_s: float = 0.0) -> float:
        """
        Estimate droplet formation frequency including filling mechanics.

        Enhanced frequency calculation:
        f = Q_open / (V_d_eff + V_refill + Q_open * T_blocked)

        Parameters
        ----------
        Q_flow : float
            Flow rate during OPEN phase [m³/s]
        T_blocked_s : float, optional
            Additional blocked time per cycle [s]. Default: 0.0

        Returns
        -------
        float
            Estimated droplet frequency [Hz]
        """
        V_total = self.compute_total_cycle_volume()

        # Account for additional blocked time
        V_blocked = Q_flow * T_blocked_s if T_blocked_s > 0 else 0.0

        # Total volume per cycle including blocked flow
        V_cycle_total = V_total + V_blocked

        # Frequency = flow rate / total cycle volume
        if V_cycle_total > 0 and Q_flow > 0:
            frequency = Q_flow / V_cycle_total
        else:
            frequency = 0.0

        return frequency

    def get_volume_breakdown(self) -> dict:
        """
        Get detailed breakdown of volume contributions for diagnostics.

        Returns
        -------
        dict
            Volume breakdown with all components [m³]
        """
        V_sphere = self.compute_baseline_droplet_volume()
        V_refill = self.compute_refill_volume()
        V_in_channel = self.A_DFU * self.L_breakup_m
        V_d_eff = self.compute_effective_droplet_volume()
        V_total = self.compute_total_cycle_volume()

        return {
            "V_sphere": V_sphere,
            "V_refill": V_refill,
            "V_in_channel": V_in_channel,
            "V_d_eff": V_d_eff,
            "V_total": V_total,
            "A_DFU": self.A_DFU,
            "L_retreat_m": self.L_retreat_m,
            "L_breakup_m": self.L_breakup_m
        }