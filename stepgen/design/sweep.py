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

import numpy as np
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


def _mode_b_derive_po(
    config: "DeviceConfig",
    Qo_in_mlhr: float,
    Qw_in_mlhr: float,
) -> float:
    """
    Mode B oracle: use the linear solver to derive oil inlet pressure from
    prescribed oil and water flows.

    Returns Po_in_mbar (derived).  The iterative solve is then run with
    this pressure, so the actual Q_oil will be ~10-15 % below the requested
    value due to capillary thresholds — this is physical, not a bug.
    """
    from stepgen.config import mlhr_to_m3s
    from stepgen.models.hydraulics import solve_linear

    lin = solve_linear(
        config,
        Q_oil=mlhr_to_m3s(Qo_in_mlhr),
        Q_water=mlhr_to_m3s(Qw_in_mlhr),
    )
    return float(lin.P_oil[0]) * 1e-2   # Pa → mbar


def _compute_robustness_fields(
    config: "DeviceConfig",
    Po: float,
    Qw: float,
) -> dict:
    """
    Compute operating-window robustness at (Po, Qw).

    Sweeps a 9-point Po grid spanning [0.4×Po, 2.6×Po] at fixed Qw and
    reports the strict window metrics, plus margins from the design point.

    Returns a dict with:
        window_width_mbar   : strict window width [mbar]; 0 if closed
        margin_lower_mbar   : Po − P_min_ok [mbar]; nan if closed
        margin_upper_mbar   : P_max_ok − Po [mbar]; nan if closed
        robustness_class    : "none" | "narrow" | "moderate" | "wide"
    """
    from stepgen.design.operating_map import compute_operating_map

    Po_lo = max(Po * 0.4, 1.0)
    Po_hi = max(Po * 2.6, Po + 50.0)
    Po_grid = np.linspace(Po_lo, Po_hi, 9)
    Qw_grid = np.array([Qw])

    map_res = compute_operating_map(config, Po_grid, Qw_grid)
    win = map_res.windows_strict[0]   # only one Qw slice

    width = win.window_width
    if win.is_open:
        margin_lo = Po - win.P_min_ok
        margin_hi = win.P_max_ok - Po
    else:
        margin_lo = float("nan")
        margin_hi = float("nan")

    if width == 0.0:
        rob_class = "none"
    elif width < 50.0:
        rob_class = "narrow"
    elif width < 150.0:
        rob_class = "moderate"
    else:
        rob_class = "wide"

    return {
        "window_width_mbar":  width,
        "margin_lower_mbar":  margin_lo,
        "margin_upper_mbar":  margin_hi,
        "robustness_class":   rob_class,
    }


def evaluate_candidate(
    config: "DeviceConfig",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    Qo_in_mlhr: float | None = None,
    *,
    compute_robustness: bool = False,
) -> dict:
    """
    Evaluate a single DeviceConfig at one operating point.

    Returns a flat dict containing all PRD §4.1 fields plus a geometry
    summary, operating-point record, layout fields, and a hard-constraint
    flag.

    Parameters
    ----------
    config             : DeviceConfig
    Po_in_mbar         : oil inlet pressure [mbar]; defaults to config.operating
    Qw_in_mlhr         : water inlet flow [mL/hr]; defaults to config.operating
    Qo_in_mlhr         : oil inlet flow [mL/hr] for Mode B (flow-flow BC).
                         When supplied, the linear solver derives Po_in_mbar and
                         the result includes ``derived_Po_in_mbar``.
    compute_robustness : when True, run a local operating-map sweep and append
                         window_width_mbar, margin_lower_mbar, margin_upper_mbar,
                         robustness_class to the returned dict.
    """
    Po = config.operating.Po_in_mbar if Po_in_mbar is None else float(Po_in_mbar)
    Qw = config.operating.Qw_in_mlhr if Qw_in_mlhr is None else float(Qw_in_mlhr)

    # Resolve Mode B: Qo kwarg > config.operating.Qo_in_mlhr
    Qo = Qo_in_mlhr
    if Qo is None and config.operating.mode == "B":
        Qo = config.operating.Qo_in_mlhr

    derived_Po: float | None = None
    if Qo is not None:
        derived_Po = _mode_b_derive_po(config, float(Qo), Qw)
        Po = derived_Po

    result  = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)
    metrics = compute_metrics(config, result)
    layout  = compute_layout(config)

    row: dict = {}

    # ── Operating point ────────────────────────────────────────────────────
    row["Po_in_mbar"] = Po
    row["Qw_in_mlhr"] = Qw
    if derived_Po is not None:
        row["derived_Po_in_mbar"] = derived_Po
        row["Qo_in_mlhr"] = Qo

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

    # ── Robustness (optional) ───────────────────────────────────────────────
    if compute_robustness:
        row.update(_compute_robustness_fields(config, Po, Qw))

    return row


def sweep(
    configs: "Sequence[DeviceConfig]",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    Qo_in_mlhr: float | None = None,
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
    Qo_in_mlhr : Mode B — override oil flow [mL/hr]; when supplied,
                 Po_in_mbar is derived by the linear solver and the result
                 includes ``derived_Po_in_mbar`` and ``Qo_in_mlhr``.

    Returns
    -------
    pd.DataFrame — one row per candidate
    """
    rows: list[dict] = []
    for cfg in configs:
        try:
            row = evaluate_candidate(cfg, Po_in_mbar, Qw_in_mlhr, Qo_in_mlhr)
            row["error"] = None
        except Exception as exc:
            row = {"error": str(exc)}
        rows.append(row)
    return pd.DataFrame(rows)
