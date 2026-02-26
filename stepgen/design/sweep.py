"""
stepgen.design.sweep
====================
Sweep engine: evaluate one or more DeviceConfig candidates at an operating
point and return a pandas DataFrame of results.

API
---
    from stepgen.design.sweep import evaluate_candidate, sweep

    row = evaluate_candidate(config)            # single candidate → dict
    df  = sweep([cfg1, cfg2, ...])              # many candidates → DataFrame
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Sequence

import pandas as pd

from stepgen.design.layout import compute_layout
from stepgen.models.generator import iterative_solve
from stepgen.models.metrics import compute_metrics

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig

# Minimum set of keys every candidate row must contain (PRD §4.1).
REQUIRED_KEYS: frozenset[str] = frozenset({
    "Nmc", "Q_oil_total", "Q_water_total", "Q_per_rung_avg",
    "Q_uniformity_pct", "dP_uniformity_pct", "P_peak",
    "active_fraction", "reverse_fraction", "off_fraction",
    "D_pred", "f_pred_mean", "delam_line_load", "collapse_index",
    "footprint_area_used", "fits_footprint",
})


def _passes_hard_constraints(config: "DeviceConfig", fits_footprint: bool) -> bool:
    """Return True if config satisfies all hard manufacturing and footprint constraints."""
    mfg  = config.manufacturing
    geom = config.geometry
    if geom.main.Mcd > mfg.max_main_depth:
        return False
    if geom.main.Mcw > mfg.max_main_width:
        return False
    if geom.rung.mcd < mfg.min_feature_width:
        return False
    if geom.rung.mcw < mfg.min_feature_width:
        return False
    if not fits_footprint:
        return False
    return True


def evaluate_candidate(
    config: "DeviceConfig",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
) -> dict:
    """
    Evaluate a single DeviceConfig at one operating point.

    Returns a flat dict containing all PRD §4.1 fields plus a geometry
    summary, operating-point record, layout fields, and a hard-constraint
    flag.

    Parameters
    ----------
    config      : DeviceConfig
    Po_in_mbar  : oil inlet pressure [mbar]; defaults to config.operating
    Qw_in_mlhr  : water inlet flow [mL/hr]; defaults to config.operating
    """
    Po = config.operating.Po_in_mbar if Po_in_mbar is None else float(Po_in_mbar)
    Qw = config.operating.Qw_in_mlhr if Qw_in_mlhr is None else float(Qw_in_mlhr)

    result  = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)
    metrics = compute_metrics(config, result)
    layout  = compute_layout(config)

    row: dict = {}

    # ── Operating point ────────────────────────────────────────────────────
    row["Po_in_mbar"] = Po
    row["Qw_in_mlhr"] = Qw

    # ── Geometry summary (human-readable units) ────────────────────────────
    row["Mcd_um"]        = config.geometry.main.Mcd * 1e6
    row["Mcw_um"]        = config.geometry.main.Mcw * 1e6
    row["Mcl_mm"]        = config.geometry.main.Mcl * 1e3
    row["mcd_um"]        = config.geometry.rung.mcd * 1e6
    row["mcw_um"]        = config.geometry.rung.mcw * 1e6
    row["mcl_um"]        = config.geometry.rung.mcl * 1e6
    row["pitch_um"]      = config.geometry.rung.pitch * 1e6
    row["exit_width_um"] = config.geometry.junction.exit_width * 1e6
    row["exit_depth_um"] = config.geometry.junction.exit_depth * 1e6

    # ── DeviceMetrics (PRD §4.1) ───────────────────────────────────────────
    for f in dataclasses.fields(metrics):
        row[f.name] = getattr(metrics, f.name)

    # ── LayoutResult ───────────────────────────────────────────────────────
    for f in dataclasses.fields(layout):
        row[f.name] = getattr(layout, f.name)

    # ── Hard constraints ───────────────────────────────────────────────────
    row["passes_hard_constraints"] = _passes_hard_constraints(
        config, layout.fits_footprint
    )

    return row


def sweep(
    configs: "Sequence[DeviceConfig]",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
) -> pd.DataFrame:
    """
    Evaluate a sequence of DeviceConfig candidates and return a DataFrame.

    Each row corresponds to one candidate.  If a candidate raises an
    exception (e.g. singular matrix), its row contains NaN for all numeric
    columns; an ``error`` column records the exception message.

    Parameters
    ----------
    configs    : sequence of DeviceConfig
    Po_in_mbar : override oil pressure for all candidates [mbar]
    Qw_in_mlhr : override water flow for all candidates [mL/hr]

    Returns
    -------
    pd.DataFrame — one row per candidate
    """
    rows: list[dict] = []
    for cfg in configs:
        try:
            row = evaluate_candidate(cfg, Po_in_mbar, Qw_in_mlhr)
            row["error"] = None
        except Exception as exc:
            row = {"error": str(exc)}
        rows.append(row)
    return pd.DataFrame(rows)
