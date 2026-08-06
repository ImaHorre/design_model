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
    from stepgen.models.metrics import DeviceMetrics

# Minimum set of keys every candidate row must contain (PRD §4.1).
REQUIRED_KEYS: frozenset[str] = frozenset({
    "Nmc", "Q_oil_total", "Q_water_total", "Q_per_rung_avg",
    "Q_spread_pct", "dP_spread_pct", "P_peak",
    "active_fraction", "reverse_fraction", "off_fraction",
    "D_pred", "f_pred_mean", "delam_line_load", "collapse_index",
    "footprint_area_used", "fits_footprint",
})


def _check_hard_constraints(
    config: "DeviceConfig",
    fits_footprint: bool,
    metrics: "DeviceMetrics | None" = None,
) -> list[str]:
    """
    Return a list of violated hard constraint descriptions. Empty list means all pass.

    *metrics* is optional only so a caller with no solve in hand (a geometry-only
    screen) can still check the fabrication and footprint limits.  When it is
    given, ``reverse_fraction`` is checked against
    :data:`~stepgen.design.operating_map.REVERSE_FRACTION_MAX`.

    **Why reverse flow is a hard constraint and not a soft flag.**  A reversed
    rung is continuous phase flowing *into* the dispersed main.  That is not a
    design running below its best operating point — it is the device doing the
    opposite of its function, and no drive pressure recovers it.  It also
    silently invalidates the row's own headline numbers: ``dP_avg``,
    ``dP_spread_pct``, ``Q_spread_pct``, ``Q_per_rung_avg`` and ``f_pred_*`` are
    all computed over ``active_mask`` (``models/metrics.py``), so a device with a
    third of its rungs backwards reports flatness and frequency for the 36 % that
    still work, presented as device-level.  Measured on ``configs/wo_v5_30.yaml``
    at Po = 200 mbar: ``reverse_fraction`` 0.315 (Qw = 5) and 0.465 (Qw = 20),
    and at Qw = 20 the net ``Q_oil_total`` is *negative* — the device consumes
    oil.  Every one of those rows reported ``passes_hard_constraints=True``.

    ``off_fraction`` is deliberately **not** promoted alongside it; see
    :func:`evaluate_candidate` for that judgement.
    """
    from stepgen.design.operating_map import REVERSE_FRACTION_MAX

    mfg  = config.manufacturing
    geom = config.geometry
    failures: list[str] = []
    if geom.main.Mcd > mfg.max_main_depth:
        failures.append(
            f"Mcd ({geom.main.Mcd*1e6:.0f}µm) > max_main_depth ({mfg.max_main_depth*1e6:.0f}µm)"
        )
    if geom.main.Mcw > mfg.max_main_width:
        failures.append(
            f"Mcw ({geom.main.Mcw*1e6:.0f}µm) > max_main_width ({mfg.max_main_width*1e6:.0f}µm)"
        )
    if geom.rung.mcd < mfg.min_feature_width:
        failures.append(
            f"mcd ({geom.rung.mcd*1e6:.2f}µm) < min_feature_width ({mfg.min_feature_width*1e6:.2f}µm)"
        )
    if geom.rung.mcw < mfg.min_feature_width:
        failures.append(
            f"mcw ({geom.rung.mcw*1e6:.2f}µm) < min_feature_width ({mfg.min_feature_width*1e6:.2f}µm)"
        )
    if not fits_footprint:
        failures.append("footprint too large for chip")
    if metrics is not None and metrics.reverse_fraction > REVERSE_FRACTION_MAX:
        failures.append(
            f"reverse_fraction ({metrics.reverse_fraction*100:.1f}%) > "
            f"max ({REVERSE_FRACTION_MAX*100:.0f}%) — continuous phase is entering "
            f"the dispersed main; device-level metrics are computed over the "
            f"{metrics.active_fraction*100:.1f}% of rungs still active"
        )
    return failures


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
    model_type: str | None = None,  # NEW parameter for model selection
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
    model_type         : hydraulic model type; defaults to config.droplet_model.hydraulic_model
                         or "steady" for backward compatibility
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

    # Determine hydraulic model type
    if model_type is None:
        model_type = getattr(config.droplet_model, 'hydraulic_model', 'steady')

    # Route to appropriate hydraulic model
    if model_type == 'steady':
        # EXISTING path unchanged - preserves backward compatibility
        result = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)
        metrics = compute_metrics(config, result)
    else:
        # NEW path - use enhanced hydraulic models
        from stepgen.models.hydraulic_models import HydraulicModelRegistry
        from stepgen.config import mbar_to_pa, mlhr_to_m3s

        # Get enhanced model
        model = HydraulicModelRegistry.get_model(model_type)

        # Convert units for enhanced model interface
        Po_Pa = mbar_to_pa(Po)
        Qw_m3s = mlhr_to_m3s(Qw)
        P_out_Pa = mbar_to_pa(0.0)  # Default outlet pressure

        # Solve with enhanced model
        hydraulic_result = model.solve(config, Po_Pa, Qw_m3s, P_out_Pa)

        # Create compatibility layer for existing result structure
        from stepgen.models.hydraulics import SimResult
        result = SimResult(
            P_oil=hydraulic_result.P_oil,
            P_water=hydraulic_result.P_water,
            Q_rungs=hydraulic_result.Q_rungs,
            x_positions=hydraulic_result.x_positions,
            Q_oil_total=float(np.sum(np.maximum(hydraulic_result.Q_rungs, 0))),  # Sum positive flows
            Q_water_total=Qw_m3s,
            Po_in_Pa=Po_Pa,
            Qw_in_m3s=Qw_m3s,
            P_out_Pa=P_out_Pa
        )

        # Use existing metrics computation for compatibility in Phase 1
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
    failures = _check_hard_constraints(config, layout.fits_footprint, metrics)
    row["passes_hard_constraints"]   = len(failures) == 0
    row["hard_constraint_failures"]  = "; ".join(failures)

    # ── Subpopulation disclosure (never a failure) ─────────────────────────
    # `dP_avg`, `dP_spread_pct`, `Q_spread_pct`, `Q_per_rung_avg` and `f_pred_*`
    # are means over `active_mask` only.  That arithmetic is correct — they are
    # honest statistics over the rungs that produce — but the row presents them
    # as device-level, and with a third of the rungs dead the two are not the
    # same claim.  Worse, the direction of the error flatters: the rungs that
    # switch off first are the starved far-end ones, so killing a device's worst
    # rungs *improves* its reported ΔP flatness.
    #
    # This warns rather than fails, and deliberately.  An OFF rung is one below
    # its capillary threshold at this drive pressure — a legitimate low-Po point
    # on a working device, not a broken design, and failing it would delete the
    # bottom of every pressure sweep, which is the part an operating map exists
    # to show.  The codebase already rules this way: `min_active_fraction` is a
    # *soft* flag (`design_search.py`).  Reverse flow is categorically different
    # and is gated above.
    row["metrics_over_subpopulation"] = metrics.active_fraction < 1.0
    row["subpopulation_note"] = (
        ""
        if metrics.active_fraction >= 1.0
        else (
            f"device-level metrics (ΔP spread, Q spread, frequency) are computed "
            f"over the {metrics.active_fraction*100:.1f}% of rungs that are active; "
            f"{metrics.off_fraction*100:.1f}% are off and "
            f"{metrics.reverse_fraction*100:.1f}% run backwards"
        )
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
    model_type: str | None = None,
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
    model_type : hydraulic model variant for all candidates

    Returns
    -------
    pd.DataFrame — one row per candidate
    """
    rows: list[dict] = []
    for cfg in configs:
        try:
            row = evaluate_candidate(cfg, Po_in_mbar, Qw_in_mlhr, Qo_in_mlhr, model_type)
            row["error"] = None
        except Exception as exc:
            row = {"error": str(exc)}
        rows.append(row)
    return pd.DataFrame(rows)
