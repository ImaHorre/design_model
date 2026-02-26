"""
stepgen.models.resistance
=========================
Hydraulic resistance formulas for rectangular channels.

Ported from stepgen_seed.resistance; extended with piecewise-section
support and DeviceConfig-aware helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig, MicrochannelSection


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

        R = 12 μ L / (w h³)  ×  1 / (1 − 0.63 h/w)

    Parameters
    ----------
    mu : float        Dynamic viscosity [Pa·s]
    length : float    Channel length [m]
    width : float     Channel width [m]
    depth : float     Channel depth [m]
    correction : bool Apply the (1 − 0.63 h/w) correction (default True).

    Returns
    -------
    float   Hydraulic resistance [Pa·s/m³]
    """
    if mu <= 0 or length <= 0 or width <= 0 or depth <= 0:
        raise ValueError("mu, length, width, depth must all be positive.")
    base = 12.0 * mu * length / (width * depth ** 3)
    if not correction:
        return base
    ratio = depth / width
    denom = 1.0 - 0.63 * ratio
    if denom <= 0:
        raise ValueError(
            f"Correction factor invalid: 1 − 0.63·(depth/width) ≤ 0 "
            f"(depth/width = {ratio:.4f})."
        )
    return base / denom


def resistance_piecewise(
    sections: "tuple[MicrochannelSection, ...]",
    mu: float,
) -> float:
    """
    Total series resistance for a piecewise microchannel profile.

    Each section is treated as an independent rectangular channel; resistances
    are summed (series).

    Parameters
    ----------
    sections : tuple[MicrochannelSection, ...]
        Non-empty sequence of channel sections.
    mu : float
        Dynamic viscosity [Pa·s].

    Returns
    -------
    float   Total hydraulic resistance [Pa·s/m³]
    """
    if not sections:
        raise ValueError("sections must be non-empty.")
    return sum(
        hydraulic_resistance_rectangular(mu, s.length, s.width, s.depth)
        for s in sections
    )


def rung_resistance(config: "DeviceConfig") -> float:
    """
    Hydraulic resistance of one rung (microchannel).

    Uses piecewise profile if ``config.geometry.rung.profile`` is non-empty;
    otherwise falls back to the simple rectangular formula scaled by
    ``constriction_ratio``.

    Viscosity used is ``config.fluids.mu_continuous`` (continuous phase,
    matching the seed convention).
    """
    rung = config.geometry.rung
    mu = config.fluids.mu_dispersed
    if rung.profile:
        return resistance_piecewise(rung.profile, mu)
    constriction_l = rung.mcl * rung.constriction_ratio
    return hydraulic_resistance_rectangular(mu, constriction_l, rung.mcw, rung.mcd)


def main_channel_resistance_per_segment(
    config: "DeviceConfig",
) -> tuple[float, float]:
    """
    Resistance of one pitch-length segment of each main channel.

    Returns
    -------
    (R_oil_main, R_water_main) : tuple[float, float]
        Both in [Pa·s/m³].
    """
    main = config.geometry.main
    rung = config.geometry.rung
    R_oil = hydraulic_resistance_rectangular(
        config.fluids.mu_dispersed, rung.pitch, main.Mcw, main.Mcd
    )
    R_water = hydraulic_resistance_rectangular(
        config.fluids.mu_continuous, rung.pitch, main.Mcw, main.Mcd
    )
    return R_oil, R_water
