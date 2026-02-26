"""
stepgen.design.operating_map
============================
Operating-map computation and operating-window extraction (PRD §6).

For a given DeviceConfig, simulate a grid of (Po, Qw) operating points and
extract the range of oil pressures — at each fixed water flow — where the
device operates correctly.

Window extraction (PRD §6.2)
-----------------------------
For each fixed-Qw row the *widest contiguous* range of Po values satisfying
a set of criteria is reported as the operating window.

Strict window criteria (all must pass):
    active_fraction  ≥ active_fraction_min
    reverse_fraction ≤ reverse_fraction_max
    Q_uniformity_pct ≤ Q_uniformity_max_pct
    dP_uniformity_pct ≤ dP_uniformity_max_pct
    (optionally) P_peak ≤ blowout_dP_Pa

Relaxed window criteria (subset — uniformity not required):
    active_fraction  ≥ active_fraction_min
    reverse_fraction ≤ reverse_fraction_max
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from tqdm import tqdm

from stepgen.models.generator import iterative_solve
from stepgen.models.metrics import compute_metrics

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


@dataclass(frozen=True)
class OperatingWindow:
    """
    Operating window extracted from a single fixed-Qw slice.

    Attributes
    ----------
    Qw_in_mlhr   : water flow for this slice [mL/hr]
    P_min_ok     : lower bound of the widest contiguous OK Po range [mbar]
    P_max_ok     : upper bound [mbar]
    window_width : P_max_ok − P_min_ok [mbar]; 0 if closed
    window_center: midpoint [mbar]; math.nan if closed
    is_open      : True when window_width > 0
    """
    Qw_in_mlhr: float
    P_min_ok: float
    P_max_ok: float
    window_width: float
    window_center: float
    is_open: bool


@dataclass
class OperatingMapResult:
    """
    Result of compute_operating_map.

    Attributes
    ----------
    Po_grid           : oil pressures [mbar], shape (nPo,)
    Qw_grid           : water flows [mL/hr], shape (nQw,)
    active_fraction   : shape (nQw, nPo)
    reverse_fraction  : shape (nQw, nPo)
    Q_uniformity_pct  : shape (nQw, nPo)
    dP_uniformity_pct : shape (nQw, nPo)
    P_peak_Pa         : shape (nQw, nPo)
    windows_strict    : list[OperatingWindow] — one per Qw (strict criteria)
    windows_relaxed   : list[OperatingWindow] — one per Qw (relaxed criteria)
    """
    Po_grid: np.ndarray
    Qw_grid: np.ndarray
    active_fraction: np.ndarray
    reverse_fraction: np.ndarray
    Q_uniformity_pct: np.ndarray
    dP_uniformity_pct: np.ndarray
    P_peak_Pa: np.ndarray
    windows_strict: list = field(default_factory=list)
    windows_relaxed: list = field(default_factory=list)


def _widest_contiguous_window(
    Po_grid: np.ndarray,
    ok_mask: np.ndarray,
    Qw_in_mlhr: float,
) -> OperatingWindow:
    """
    Find the widest contiguous run of True in ok_mask and return an
    OperatingWindow.  Returns a closed window if no True values exist.
    """
    best_start = -1
    best_end   = -1
    best_len   = 0
    run_start: int | None = None

    for j, v in enumerate(ok_mask):
        if v:
            if run_start is None:
                run_start = j
            run_len = j - run_start + 1
            if run_len > best_len:
                best_len = run_len
                best_start, best_end = run_start, j
        else:
            run_start = None

    if best_start < 0:
        return OperatingWindow(
            Qw_in_mlhr=Qw_in_mlhr,
            P_min_ok=math.nan,
            P_max_ok=math.nan,
            window_width=0.0,
            window_center=math.nan,
            is_open=False,
        )

    P_min   = float(Po_grid[best_start])
    P_max   = float(Po_grid[best_end])
    width   = P_max - P_min
    center  = (P_min + P_max) / 2.0
    return OperatingWindow(
        Qw_in_mlhr=Qw_in_mlhr,
        P_min_ok=P_min,
        P_max_ok=P_max,
        window_width=width,
        window_center=center,
        is_open=True,
    )


def compute_operating_map(
    config: "DeviceConfig",
    Po_grid_mbar: np.ndarray,
    Qw_grid_mlhr: np.ndarray,
    *,
    active_fraction_min: float = 0.8,
    reverse_fraction_max: float = 0.1,
    Q_uniformity_max_pct: float = 10.0,
    dP_uniformity_max_pct: float = 10.0,
    blowout_dP_Pa: float | None = None,
) -> OperatingMapResult:
    """
    Simulate a (Po, Qw) grid and extract operating windows.

    Parameters
    ----------
    config               : DeviceConfig
    Po_grid_mbar         : 1-D array of oil pressures to sweep [mbar]
    Qw_grid_mlhr         : 1-D array of water flows to sweep [mL/hr]
    active_fraction_min  : minimum active_fraction for strict + relaxed criteria
    reverse_fraction_max : maximum reverse_fraction for strict + relaxed criteria
    Q_uniformity_max_pct : maximum Q_uniformity_pct for strict window
    dP_uniformity_max_pct: maximum dP_uniformity_pct for strict window
    blowout_dP_Pa        : if set, P_peak must not exceed this [Pa] (strict)

    Returns
    -------
    OperatingMapResult
    """
    Po_grid = np.asarray(Po_grid_mbar, dtype=float)
    Qw_grid = np.asarray(Qw_grid_mlhr, dtype=float)
    nPo = len(Po_grid)
    nQw = len(Qw_grid)

    # Allocate result arrays
    active_frac   = np.zeros((nQw, nPo))
    reverse_frac  = np.zeros((nQw, nPo))
    Q_unif        = np.zeros((nQw, nPo))
    dP_unif       = np.zeros((nQw, nPo))
    P_peak        = np.zeros((nQw, nPo))

    for i, Qw in enumerate(tqdm(Qw_grid, desc="operating map", unit="Qw")):
        for j, Po in enumerate(Po_grid):
            result  = iterative_solve(config, Po_in_mbar=float(Po), Qw_in_mlhr=float(Qw))
            metrics = compute_metrics(config, result)
            active_frac[i, j]  = metrics.active_fraction
            reverse_frac[i, j] = metrics.reverse_fraction
            Q_unif[i, j]       = metrics.Q_uniformity_pct
            dP_unif[i, j]      = metrics.dP_uniformity_pct
            P_peak[i, j]       = metrics.P_peak

    # ── Window extraction ──────────────────────────────────────────────────
    windows_strict:  list[OperatingWindow] = []
    windows_relaxed: list[OperatingWindow] = []

    for i, Qw in enumerate(Qw_grid):
        # Strict mask
        ok_strict = (
            (active_frac[i]  >= active_fraction_min)  &
            (reverse_frac[i] <= reverse_fraction_max) &
            (Q_unif[i]       <= Q_uniformity_max_pct) &
            (dP_unif[i]      <= dP_uniformity_max_pct)
        )
        if blowout_dP_Pa is not None:
            ok_strict &= (P_peak[i] <= blowout_dP_Pa)

        # Relaxed mask (no uniformity criteria)
        ok_relaxed = (
            (active_frac[i]  >= active_fraction_min) &
            (reverse_frac[i] <= reverse_fraction_max)
        )

        windows_strict.append(
            _widest_contiguous_window(Po_grid, ok_strict, float(Qw))
        )
        windows_relaxed.append(
            _widest_contiguous_window(Po_grid, ok_relaxed, float(Qw))
        )

    return OperatingMapResult(
        Po_grid=Po_grid,
        Qw_grid=Qw_grid,
        active_fraction=active_frac,
        reverse_fraction=reverse_frac,
        Q_uniformity_pct=Q_unif,
        dP_uniformity_pct=dP_unif,
        P_peak_Pa=P_peak,
        windows_strict=windows_strict,
        windows_relaxed=windows_relaxed,
    )
