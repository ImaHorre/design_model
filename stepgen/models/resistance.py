"""
stepgen.models.resistance
=========================
Hydraulic resistance formulas for rectangular channels.

**This module holds the one rectangular-duct resistance in the codebase** (W2-1).
Before it, four implementations disagreed on three separate axes — shape factor,
dimension ordering, and length — and none of them was right.  Everything that
needs a rectangular channel calls :func:`hydraulic_resistance_rectangular`:
``stage_wise_v3.stage1_physics``, ``families.radial``, ``families.manifold``,
``families.intent`` and the ladder network here.

Ported from stepgen_seed.resistance; extended with piecewise-section
support and DeviceConfig-aware helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig, MicrochannelSection


def rect_duct_fRe(alpha: float) -> float:
    """
    Shah & London's friction-factor group ``fRe`` for a rectangular duct.

        fRe(α) = 96·(1 − 1.3553α + 1.9467α² − 1.7012α³ + 0.9564α⁴ − 0.2537α⁵)

    where ``α = h/w ∈ (0, 1]`` is the aspect ratio of the *ordered* duct
    (h = short side).  This is the **Darcy** normalisation, and — critically —
    it is normalised on the **hydraulic diameter**, which is what
    :func:`hydraulic_resistance_rectangular` then divides by.
    """
    if alpha <= 0:
        return 96.0
    a = min(alpha, 1.0)
    return 96.0 * (1 - 1.3553*a + 1.9467*a**2 - 1.7012*a**3 + 0.9564*a**4 - 0.2537*a**5)


def hydraulic_resistance_rectangular(
    mu: float,
    length: float,
    width: float,
    depth: float,
    *,
    correction: bool = True,
) -> float:
    """
    Hydraulic resistance for fully developed laminar flow in a rectangular duct.

        R = fRe(α)·μ·L / (2·A·D_h²)       A = w·h,  D_h = 4A/perimeter

    with the dimensions **ordered** (h = min, w = max) so ``α = h/w ≤ 1`` by
    construction.

    Why this normalisation and not ``f(α)·μL/(w·h³)``
    -------------------------------------------------
    ``fRe`` is defined against the hydraulic diameter: ``dP/dx = fRe·μ·u/(2·D_h²)``.
    Dropping the same polynomial into the parallel-plate form is a **different
    normalisation**, and that is what shipped in ``stage1_physics`` until W2-1.
    Check it at α → 0: as-coded gives ``96μL/(wh³)``, eight times the correct
    ``12μL/(wh³)``.  At V5-30's α = 0.8 the polynomial has decayed to 57.5, so the
    error lands at **2.47×**.

    Used correctly the closed form reproduces the exact Fourier-series solution
    for the duct to **four significant figures** across the whole aspect range —
    see ``tests/test_resistance.py::TestExactSolution``, which carries the series
    so this claim is checked and not merely asserted.

    Ordering, not rejecting
    ----------------------
    V5-30's DFU is 8 µm wide × 10 µm **deep** — depth exceeds width on the real
    device (``reference_devices/README.md``).  The three former implementations
    each rejected or mis-handled that: two raised above ``h/w = 1.587``, one
    rejected ``h ≥ w`` outright, and all three fed an unordered ratio into a
    correction that is only valid for ``h ≤ w``.  Ordering makes α ≤ 1
    unconditionally, so **no rejection rule is needed anywhere** and the real
    device is representable.

    Parameters
    ----------
    mu : float        Dynamic viscosity [Pa·s]
    length : float    Channel length [m]
    width : float     Channel width [m]
    depth : float     Channel depth [m]
    correction : bool Apply the aspect-ratio shape factor (default True).
                      ``False`` gives the parallel-plate limit ``12μL/(wh³)``,
                      i.e. the α → 0 form; nothing in the model uses it.

    Returns
    -------
    float   Hydraulic resistance [Pa·s/m³]
    """
    if mu <= 0 or length <= 0 or width <= 0 or depth <= 0:
        raise ValueError("mu, length, width, depth must all be positive.")
    h, w = min(width, depth), max(width, depth)
    if not correction:
        return 12.0 * mu * length / (w * h ** 3)
    area = w * h
    d_h = 4.0 * area / (2.0 * (w + h))
    return rect_duct_fRe(h / w) * mu * length / (2.0 * area * d_h ** 2)


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

    Uses the piecewise profile if ``config.geometry.rung.profile`` is non-empty
    — the right path for a real DFU, which is two widths in series — otherwise
    falls back to the single rectangular section scaled by ``constriction_ratio``.

    Viscosity used is ``config.fluids.mu_dispersed`` (the oil).  Stage 1 is
    oil delivery through the rung, so the dispersed phase is correct; the
    docstring said ``mu_continuous`` until W2-1 while the code always used
    ``mu_dispersed``, which made it a trap rather than a description.
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
