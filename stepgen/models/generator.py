"""
stepgen.models.generator
========================
Threshold/hysteresis rung regime model and iterative solver.

Physics
-------
For each rung i, ΔP_i = P_oil[i] − P_water[i].

    ΔP_i >  dP_cap_ow  →  ACTIVE  (oil → water droplet production)
    ΔP_i < −dP_cap_wo  →  REVERSE (water → oil, reverse band)
    otherwise          →  OFF     (pinned, negligible flow)

Iterative solve
---------------
1. Initial solve with uniform conductances (all rungs open).
2. Classify rungs from ΔP.
3. If classification unchanged → converged.
4. Update per-rung conductances and RHS threshold offsets:
     OFF     : g → g₀ × ε  (near-zero, avoids singular matrix)
     ACTIVE  : g → g₀,  rhs_oil[i] = −g₀ × dP_cap_ow,  rhs_water[i] = +g₀ × dP_cap_ow
     REVERSE : g → g₀,  rhs_oil[i] = +g₀ × dP_cap_wo,  rhs_water[i] = −g₀ × dP_cap_wo
5. Re-solve and repeat.

The affine RHS offsets model the capillary threshold: Q_i = g₀(ΔP_i − dP_cap)
is rewritten as g₀ ΔP_i = Q_i + g₀ dP_cap, shifting the source term to the RHS.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

import numpy as np

from stepgen.config import mbar_to_pa, mlhr_to_m3s
from stepgen.models.hydraulics import SimResult, _simulate_pa
from stepgen.models.resistance import rung_resistance

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig

# Conductance multiplier for OFF rungs; small enough to be negligible,
# large enough to keep the matrix non-singular.
_EPSILON_OFF: float = 1e-10


class RungRegime(enum.Enum):
    ACTIVE  = "active"   # oil → water
    REVERSE = "reverse"  # water → oil
    OFF     = "off"      # pinned / no flow


def classify_rungs(
    dP: np.ndarray,
    dP_cap_ow_Pa: float,
    dP_cap_wo_Pa: float,
) -> np.ndarray:
    """
    Classify each rung by its pressure difference.

    Parameters
    ----------
    dP           : array of ΔP = P_oil − P_water [Pa], shape (N,)
    dP_cap_ow_Pa : oil→water capillary threshold [Pa]  (positive)
    dP_cap_wo_Pa : water→oil reverse threshold  [Pa]  (positive)

    Returns
    -------
    np.ndarray of dtype=object, each element a RungRegime value, shape (N,).
    """
    dP = np.asarray(dP, dtype=float)
    out = np.full(len(dP), RungRegime.OFF, dtype=object)
    out[dP >  dP_cap_ow_Pa] = RungRegime.ACTIVE
    out[dP < -dP_cap_wo_Pa] = RungRegime.REVERSE
    return out


def iterative_solve(
    config: "DeviceConfig",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    P_out_mbar: float | None = None,
    *,
    max_iter: int = 50,
    tol: float = 1e-6,   # reserved for future pressure-change convergence check
) -> SimResult:
    """
    Iterative threshold/hysteresis solver.

    Thresholds are read from ``config.droplet_model.dP_cap_ow_Pa`` and
    ``config.droplet_model.dP_cap_wo_Pa``.

    Operating-point parameters default to ``config.operating`` when not given.

    Returns the SimResult from the final (converged or max_iter) iteration.
    The Q_rungs field contains threshold-adjusted flows.
    """
    if max_iter < 1:
        raise ValueError(f"max_iter must be >= 1; got {max_iter}.")

    Po   = config.operating.Po_in_mbar  if Po_in_mbar is None else Po_in_mbar
    Qw   = config.operating.Qw_in_mlhr  if Qw_in_mlhr is None else Qw_in_mlhr
    Pout = config.operating.P_out_mbar  if P_out_mbar is None else P_out_mbar

    Po_Pa   = mbar_to_pa(Po)
    Qw_m3s  = mlhr_to_m3s(Qw)
    Pout_Pa = mbar_to_pa(Pout)

    dP_cap_ow = config.droplet_model.dP_cap_ow_Pa
    dP_cap_wo = config.droplet_model.dP_cap_wo_Pa

    N  = config.geometry.Nmc
    g0 = 1.0 / rung_resistance(config)

    # Start: uniform conductance, no threshold offsets (linear open system)
    g_rungs   = np.full(N, g0, dtype=float)
    rhs_oil   = np.zeros(N, dtype=float)
    rhs_water = np.zeros(N, dtype=float)

    prev_regimes: np.ndarray | None = None
    result: SimResult | None = None

    for _ in range(max_iter):
        result = _simulate_pa(
            config, Po_Pa, Qw_m3s, Pout_Pa,
            g_rungs=g_rungs, rhs_oil=rhs_oil, rhs_water=rhs_water,
        )

        dP = result.P_oil - result.P_water
        regimes = classify_rungs(dP, dP_cap_ow, dP_cap_wo)

        # Convergence: regime pattern unchanged since last iteration
        if prev_regimes is not None and np.array_equal(regimes, prev_regimes):
            break

        prev_regimes = regimes

        # Rebuild per-rung parameters from new classification
        g_rungs = np.where(
            regimes == RungRegime.OFF,
            g0 * _EPSILON_OFF,
            g0,
        ).astype(float)

        rhs_oil = np.zeros(N, dtype=float)
        rhs_oil[regimes == RungRegime.ACTIVE]  = -g0 * dP_cap_ow
        rhs_oil[regimes == RungRegime.REVERSE] = +g0 * dP_cap_wo

        rhs_water = -rhs_oil   # equal and opposite at the paired water node

    assert result is not None  # guaranteed: loop runs at least once
    return result
