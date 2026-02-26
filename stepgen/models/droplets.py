"""
stepgen.models.droplets
=======================
Empirical droplet size and frequency model.

Physics
-------
Power-law diameter:

    D = k · w^a · h^b  [m]

where w = junction exit_width, h = junction exit_depth, and
k, a, b are empirical coefficients from DropletModelConfig.

Droplet volume (sphere approximation):

    V_d = (π / 6) · D³  [m³]

Per-rung droplet production frequency:

    f_i = Q_rung_i / V_d  [Hz]
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Union

import numpy as np

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


def droplet_diameter(config: "DeviceConfig") -> float:
    """
    Predicted droplet diameter from exit geometry.

    D = k · w^a · h^b  [m]

    Uses ``config.geometry.junction.exit_width`` and ``exit_depth``
    together with ``config.droplet_model`` coefficients k, a, b.
    """
    dm = config.droplet_model
    jc = config.geometry.junction
    return dm.k * (jc.exit_width ** dm.a) * (jc.exit_depth ** dm.b)


def droplet_volume(D: float) -> float:
    """
    Droplet volume for a sphere of diameter D [m].

    V = (π / 6) · D³  [m³]
    """
    return (math.pi / 6.0) * D ** 3


def droplet_frequency(
    Q_rung: "Union[float, np.ndarray]",
    D: float,
) -> "Union[float, np.ndarray]":
    """
    Droplet production frequency.

    f = Q_rung / V_d  [Hz]

    Parameters
    ----------
    Q_rung : scalar or ndarray
        Rung volumetric flow [m³/s].  Positive values correspond to
        oil-into-water (ACTIVE) flow.
    D : float
        Droplet diameter [m].

    Returns
    -------
    Frequency in Hz; same type and shape as Q_rung.
    """
    V = droplet_volume(D)
    return Q_rung / V
