"""
stepgen_seed.resistance

Refactors the resistance + parameter definitions from the original monolithic script.
Goal: preserve the current physics kernel behavior while making it importable.

Notes:
- The original script uses a simplified rectangular-channel correction factor:
    R = 12*mu*L / (w*h^3) * 1/(1 - 0.63*(h/w))
  (and similarly for the oil constriction, with h=mcd, w=mcw)
- Units: SI (m, Pa*s, m^3/s, Pa)
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


def hydraulic_resistance_rectangular(
    mu: float,
    length: float,
    width: float,
    depth: float,
    *,
    correction: bool = True,
) -> float:
    """
    Approximate hydraulic resistance for laminar flow in a rectangular channel.

    Parameters
    ----------
    mu : float
        Dynamic viscosity [Pa*s]
    length : float
        Channel length [m]
    width : float
        Channel width [m]
    depth : float
        Channel depth/height [m]
    correction : bool
        Apply the simple correction factor used in the original code.

    Returns
    -------
    float
        Hydraulic resistance [Pa*s/m^3]
    """
    if width <= 0 or depth <= 0 or length <= 0 or mu <= 0:
        raise ValueError("mu, length, width, depth must be positive.")
    base = 12.0 * mu * length / (width * (depth ** 3))
    if not correction:
        return base
    # Preserve original simplified correction: 1 / (1 - 0.63*(h/w))
    ratio = depth / width
    denom = (1.0 - 0.63 * ratio)
    if denom <= 0:
        raise ValueError(
            f"Invalid geometry for correction: 1 - 0.63*(depth/width) <= 0 (depth/width={ratio})."
        )
    return base / denom


@dataclass(frozen=True)
class Geometry:
    # Main channel
    Mcl: float  # main-channel routed length [m]
    Mcd: float  # main-channel depth [m]
    Mcw: float  # main-channel width [m]

    # Microchannel ("rung")
    mcd: float  # microchannel depth [m]
    mcw: float  # microchannel width [m]
    mcl: float  # microchannel length [m]

    pitch: float  # microchannel pitch along main channels [m]
    constriction_ratio: float  # fraction of mcl that is constriction/junction region


@dataclass(frozen=True)
class Fluids:
    mu_water: float = 0.00089
    mu_oil: float = 0.03452


@dataclass(frozen=True)
class DropletSpec:
    emulsion_ratio: float = 0.3
    droplet_radius: float = 0.5e-6
    production_frequency: float = 50.0  # Hz


@dataclass(frozen=True)
class ModelParams:
    """
    Parameters consumed by the ladder solver (linear mode).

    Nmc : int
        Number of microchannels
    R_OMc : float
        Resistance of one pitch-length segment of oil main channel
    R_WMc : float
        Resistance of one pitch-length segment of water main channel
    R_Omc : float
        Resistance of microchannel (rung / constriction)
    Q_O : float
        Oil inlet flow [m^3/s] used in original 'design mode' assumption
    Q_W : float
        Water inlet flow [m^3/s] used in original 'design mode' assumption
    """
    Nmc: int
    R_OMc: float
    R_WMc: float
    R_Omc: float
    Q_O: float
    Q_W: float


def compute_design_flows(
    *,
    Nmc: int,
    droplet_radius: float,
    production_frequency: float,
    emulsion_ratio: float,
) -> tuple[float, float]:
    """
    Replicates the original script's "design-mode" flow computation:
    - droplet_volume = 4/3*pi*r^3
    - total oil flow = f * Vdroplet * Nmc
    - total water flow = oil / emulsion_ratio
    """
    droplet_volume = (4.0 / 3.0) * np.pi * (droplet_radius ** 3)
    Q_oil = production_frequency * droplet_volume * Nmc
    Q_water = Q_oil / emulsion_ratio
    return float(Q_oil), float(Q_water)


def define_parameters(
    geom: Geometry,
    fluids: Fluids = Fluids(),
    droplet: DropletSpec = DropletSpec(),
) -> ModelParams:
    """
    Preserves the original define_parameters() behavior.

    Returns
    -------
    ModelParams
        Parameters for ladder solver.
    """
    if geom.pitch <= 0:
        raise ValueError("pitch must be > 0")
    if not (0 < geom.constriction_ratio <= 1.0):
        raise ValueError("constriction_ratio must be in (0, 1].")

    constriction_l = geom.mcl * geom.constriction_ratio
    Nmc = int(np.floor(geom.Mcl / geom.pitch))
    if Nmc < 2:
        raise ValueError(f"Nmc too small ({Nmc}); increase Mcl or decrease pitch.")

    # Resistances (match current uncommented section of original script)
    R_Omc = hydraulic_resistance_rectangular(
        fluids.mu_oil, constriction_l, geom.mcw, geom.mcd, correction=True
    )
    R_OMc = hydraulic_resistance_rectangular(
        fluids.mu_oil, geom.pitch, geom.Mcw, geom.Mcd, correction=True
    )
    R_WMc = hydraulic_resistance_rectangular(
        fluids.mu_water, geom.pitch, geom.Mcw, geom.Mcd, correction=True
    )

    Q_O, Q_W = compute_design_flows(
        Nmc=Nmc,
        droplet_radius=droplet.droplet_radius,
        production_frequency=droplet.production_frequency,
        emulsion_ratio=droplet.emulsion_ratio,
    )

    return ModelParams(Nmc=Nmc, R_OMc=R_OMc, R_WMc=R_WMc, R_Omc=R_Omc, Q_O=Q_O, Q_W=Q_W)
