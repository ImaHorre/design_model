"""
stepgen.models.metrics
======================
Aggregate device performance metrics derived from a SimResult.

Usage
-----
    from stepgen.models.metrics import compute_metrics

    metrics = compute_metrics(config, result)

All quantities are in SI unless otherwise noted in the field docstring.

Metrics computed here (excluding layout, which is Stage F):

    Nmc               — number of rungs
    Q_oil_total       — oil inlet flow [m³/s]
    Q_water_total     — water inlet flow [m³/s]
    Q_per_rung_avg    — mean Q over ACTIVE rungs (0 if none active) [m³/s]
    Q_uniformity_pct  — (max−min)/mean × 100 over ACTIVE rungs [%]
    dP_uniformity_pct — (max−min)/mean × 100 over ACTIVE rung ΔP [%]
    P_peak            — max(P_oil) [Pa]
    active_fraction   — fraction of rungs ACTIVE [0–1]
    reverse_fraction  — fraction of rungs REVERSE [0–1]
    off_fraction      — fraction of rungs OFF [0–1]
    D_pred            — predicted droplet diameter [m]
    f_pred_mean       — mean droplet frequency over ACTIVE rungs [Hz]
    delam_line_load   — P_peak × Mcw  (delamination risk) [N/m]
    collapse_index    — Mcw / Mcd  (higher aspect ratio → more collapse risk)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from stepgen.models.droplets import droplet_diameter, droplet_frequency
from stepgen.models.generator import RungRegime, classify_rungs

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from stepgen.models.hydraulics import SimResult


@dataclass(frozen=True)
class DeviceMetrics:
    """Per-operating-point device performance metrics (SI units)."""

    Nmc: int
    Q_oil_total: float       # m³/s
    Q_water_total: float     # m³/s
    Q_per_rung_avg: float    # m³/s — mean over ACTIVE rungs; 0 if none
    Q_uniformity_pct: float  # %    — (max−min)/mean × 100 for ACTIVE rungs
    dP_uniformity_pct: float # %    — (max−min)/mean × 100 for ACTIVE rung ΔP
    P_peak: float            # Pa   — max oil pressure
    active_fraction: float   # 0–1
    reverse_fraction: float  # 0–1
    off_fraction: float      # 0–1
    D_pred: float            # m    — predicted droplet diameter
    f_pred_mean: float       # Hz   — mean droplet frequency over ACTIVE rungs; 0 if none
    delam_line_load: float   # N/m  — P_peak × Mcw
    collapse_index: float    # —    — Mcw / Mcd (dimensionless aspect ratio)


def compute_metrics(
    config: "DeviceConfig",
    result: "SimResult",
) -> DeviceMetrics:
    """
    Compute DeviceMetrics from a config and SimResult.

    Parameters
    ----------
    config : DeviceConfig
    result : SimResult  (from ``simulate()`` or ``iterative_solve()``)

    Returns
    -------
    DeviceMetrics
    """
    N = result.P_oil.shape[0]
    dP = result.P_oil - result.P_water

    # ── Regime classification ──────────────────────────────────────────────
    regimes = classify_rungs(
        dP,
        config.droplet_model.dP_cap_ow_Pa,
        config.droplet_model.dP_cap_wo_Pa,
    )
    active_mask  = regimes == RungRegime.ACTIVE
    reverse_mask = regimes == RungRegime.REVERSE
    off_mask     = regimes == RungRegime.OFF

    active_fraction  = float(np.sum(active_mask)  / N)
    reverse_fraction = float(np.sum(reverse_mask) / N)
    off_fraction     = float(np.sum(off_mask)     / N)

    # ── Flow and ΔP uniformity (ACTIVE rungs only) ─────────────────────────
    if np.any(active_mask):
        Q_active = result.Q_rungs[active_mask]
        Q_per_rung_avg = float(np.mean(Q_active))
        Q_mean = float(np.mean(Q_active))
        if Q_mean > 0:
            Q_uniformity_pct = float(
                (np.max(Q_active) - np.min(Q_active)) / Q_mean * 100.0
            )
        else:
            Q_uniformity_pct = 0.0

        dP_active = dP[active_mask]
        dP_mean = float(np.mean(dP_active))
        if dP_mean > 0:
            dP_uniformity_pct = float(
                (np.max(dP_active) - np.min(dP_active)) / dP_mean * 100.0
            )
        else:
            dP_uniformity_pct = 0.0
    else:
        Q_per_rung_avg    = 0.0
        Q_uniformity_pct  = 0.0
        dP_uniformity_pct = 0.0

    # ── Peak pressure ──────────────────────────────────────────────────────
    P_peak = float(np.max(result.P_oil))

    # ── Droplet model ──────────────────────────────────────────────────────
    D_pred = droplet_diameter(config)
    if np.any(active_mask):
        f_arr = droplet_frequency(result.Q_rungs[active_mask], D_pred)
        f_pred_mean = float(np.mean(f_arr))
    else:
        f_pred_mean = 0.0

    # ── Mechanical risk ────────────────────────────────────────────────────
    Mcw = config.geometry.main.Mcw
    Mcd = config.geometry.main.Mcd
    delam_line_load = P_peak * Mcw
    collapse_index  = Mcw / Mcd

    return DeviceMetrics(
        Nmc=N,
        Q_oil_total=result.Q_oil_total,
        Q_water_total=result.Q_water_total,
        Q_per_rung_avg=Q_per_rung_avg,
        Q_uniformity_pct=Q_uniformity_pct,
        dP_uniformity_pct=dP_uniformity_pct,
        P_peak=P_peak,
        active_fraction=active_fraction,
        reverse_fraction=reverse_fraction,
        off_fraction=off_fraction,
        D_pred=D_pred,
        f_pred_mean=f_pred_mean,
        delam_line_load=delam_line_load,
        collapse_index=collapse_index,
    )
