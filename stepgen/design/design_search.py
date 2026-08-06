"""
stepgen.design.design_search
=============================
Design-from-targets sweep engine.

Given a DesignSearchSpec (loaded from a design_search.yaml), this module:
  1. For each (Mcd, Mcw, pitch, mcd, mcw, mcl_rung) combination, derives
     junction exit geometry from the target droplet diameter with
     exit_depth = mcd (depth is constant; the rung widens only laterally at
     the junction exit).  exit_width is solved from D = k*w^a*h^b.
  2. Enforces exit_width / exit_depth in [min_junction_aspect_ratio,
     max_junction_aspect_ratio] as a hard constraint.
  3. Computes the maximum Mcl that fits in the footprint (Mcl is NEVER a
     sweep input — it is always derived), then builds a DeviceConfig and
     evaluates it in Mode B.
  4. Checks hard and soft constraints, ranks passing candidates by the
     optimisation objective, and returns a DataFrame.

Key insight: Mcl_max depends on Mcw (via lane_pair_width) and footprint
geometry, so it changes for every Mcw value in the sweep.

API
---
    from stepgen.design.design_search import run_design_search
    from stepgen.config import load_design_search

    spec = load_design_search("design_search.yaml")
    df   = run_design_search(spec)
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from tqdm import tqdm

if TYPE_CHECKING:
    from stepgen.config import DesignSearchSpec


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _derive_mcd_from_ar(spec: "DesignSearchSpec", ar: float) -> float:
    """
    Derive rung depth mcd from target droplet diameter and junction aspect ratio.

    With exit_width = ar * mcd and exit_depth = mcd:
        D = k * (ar * mcd)^a * mcd^b = k * ar^a * mcd^(a+b)
        mcd = (D / (k * ar^a))^(1/(a+b))

    Returns mcd [m].

    The closed form lives in ``stepgen.families.intent.depth_for_droplet``,
    which the Studio's intent layer also calls, so the design search and the
    Studio can never drift apart on what a droplet target means geometrically.
    """
    from stepgen.families.intent import depth_for_droplet

    return depth_for_droplet(
        spec.design_targets.target_droplet_um, ar, spec.droplet_model
    )


def _derive_junction_geometry(
    spec: "DesignSearchSpec", mcd_m: float
) -> tuple[float, float]:
    """
    Derive junction exit geometry given rung depth mcd_m.

    The junction exit depth equals the rung depth: depth is constant throughout
    the rung and its widened exit section (single etch step — only width
    expands at the junction).

    Solves D = k * w^a * h^b with h = mcd_m for exit_width w:
        w = (D / (k * h^b))^(1/a)

    Returns (exit_width_m, exit_depth_m).
    """
    dm = spec.droplet_model
    D  = spec.design_targets.target_droplet_um * 1e-6   # SI
    h  = mcd_m
    w  = (D / (dm.k * (h ** dm.b))) ** (1.0 / dm.a)
    return w, h


def _max_mcl_for_footprint(
    fp,          # FootprintConfig
    Mcw_m: float,
    mcl_rung_m: float,
) -> float:
    """
    Compute the maximum main-channel routed length that fits in the footprint.

    Inverts :func:`stepgen.design.layout.compute_layout`: instead of asking
    whether a given Mcl fits, it asks how many lanes the die height holds.

    The stack-up comes from :func:`~stepgen.design.layout.lane_stackup`, which
    is the only place it is written down.  This site used to keep its own copy
    that omitted the rung array entirely (``2×Mcw + lane_spacing``), so it
    disagreed with both the model and the drawing and over-stated Mcl_max.

    Returns Mcl_max [m]; 0.0 if even one lane doesn't fit.
    """
    from stepgen.design.layout import active_extent, lane_stackup

    L_useful, H_useful = active_extent(fp)

    if L_useful <= 0.0:
        return 0.0

    lane_pair_width, lane_pitch = lane_stackup(
        main_width_m=Mcw_m,
        dfu_array_m=mcl_rung_m,
        wall_width_m=fp.wall_width,
    )

    if lane_pair_width > H_useful:
        return 0.0   # even a single lane doesn't fit vertically

    # How many lanes fit?
    # total_height = (n-1)*lane_pitch + lane_pair_width <= H_useful
    # n <= 1 + floor((H_useful - lane_pair_width) / lane_pitch)
    max_num_lanes = 1 + int((H_useful - lane_pair_width) / lane_pitch)
    return max_num_lanes * L_useful


# ---------------------------------------------------------------------------
# Candidate building
# ---------------------------------------------------------------------------

def _build_device_config(
    spec: "DesignSearchSpec",
    Mcd_m: float,
    Mcw_m: float,
    Mcl_m: float,
    pitch_m: float,
    mcd_m: float,
    mcw_m: float,
    mcl_rung_m: float,
    exit_width_m: float,
    exit_depth_m: float,
    Po_fallback_mbar: float = 100.0,
) -> "object":
    """Build a DeviceConfig for the candidate geometry."""
    from stepgen.config import (
        DeviceConfig, FluidConfig, GeometryConfig, MainChannelConfig,
        RungConfig, JunctionConfig, OperatingConfig, FootprintConfig,
    )

    return DeviceConfig(
        fluids=dataclasses.replace(
            spec.fluids,
            emulsion_ratio=spec.design_targets.target_emulsion_ratio,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=Mcd_m, Mcw=Mcw_m, Mcl=Mcl_m),
            rung=RungConfig(
                mcd=mcd_m,
                mcw=mcw_m,
                mcl=mcl_rung_m,
                pitch=pitch_m,
                constriction_ratio=1.0,
            ),
            junction=JunctionConfig(
                exit_width=exit_width_m,
                exit_depth=exit_depth_m,
            ),
        ),
        operating=OperatingConfig(
            Po_in_mbar=Po_fallback_mbar,
            Qw_in_mlhr=spec.design_targets.Qw_in_mlhr,
            mode="B",
            Qo_in_mlhr=(
                spec.design_targets.target_emulsion_ratio
                * spec.design_targets.Qw_in_mlhr
            ),
        ),
        footprint=spec.footprint,
        manufacturing=spec.manufacturing,
        droplet_model=spec.droplet_model,
    )


# ---------------------------------------------------------------------------
# Constraint checks
# ---------------------------------------------------------------------------

def _geometry_failure_reasons(
    hc,                      # DesignHardConstraints
    Mcd_m: float,
    Mcw_m: float,
    mcd_m: float,
    mcw_m: float,
    collapse_index: float,
    ar: float,
) -> list[str]:
    """
    Return one human-readable reason per violated *geometry* hard constraint.

    This is the pre-solve screen: everything checkable from the candidate's
    dimensions alone, before a config is built.  The caller derives
    ``passes_hard_geom`` from ``not _geometry_failure_reasons(...)`` rather than
    keeping a parallel boolean — this used to be a single collapsed ``and`` of
    six conditions with nothing recorded, so a rejected candidate reached the
    CSV as ``passes_hard=False`` and no reason at all.

    Messages name the *config field*, in the units the YAML is written in, so a
    reader can go straight to the key that has to change.

    Note for whoever generalises this: :class:`~stepgen.config.DesignHardConstraints`
    and :class:`~stepgen.config.ManufacturingConfig` carry the **same three
    limits** (max main depth, max main width, min feature width) on the same
    ``DesignSearchSpec``, checked here and again in
    :func:`stepgen.design.sweep._check_hard_constraints`.  They agree today only
    because nothing sets one without the other.  Deliberately left alone — it is
    a config-schema change, not a reason-column one.
    """
    fails: list[str] = []
    if Mcd_m > hc.max_main_depth_um * 1e-6:
        fails.append(
            f"Mcd ({Mcd_m*1e6:.0f}µm) > max_main_depth_um ({hc.max_main_depth_um:.0f})"
        )
    if Mcw_m > hc.max_main_width_um * 1e-6:
        fails.append(
            f"Mcw ({Mcw_m*1e6:.0f}µm) > max_main_width_um ({hc.max_main_width_um:.0f})"
        )
    if mcd_m < hc.min_feature_width_um * 1e-6:
        fails.append(
            f"mcd ({mcd_m*1e6:.2f}µm, derived from the droplet target) "
            f"< min_feature_width_um ({hc.min_feature_width_um:.2f})"
        )
    if mcw_m < hc.min_feature_width_um * 1e-6:
        fails.append(
            f"mcw ({mcw_m*1e6:.2f}µm) < min_feature_width_um ({hc.min_feature_width_um:.2f})"
        )
    if collapse_index > hc.max_collapse_index:
        # Mcw/Mcd is a ratio of two values converted from µm, so an intended
        # exact tie is not exact: Mcw = 2000 µm, Mcd = 200 µm gives
        # 10.000000000000002, which fails `> 10.0`.  The comparison is
        # unchanged here — tightening or loosening it changes which candidates
        # pass and is a ruling, not a reason-column edit — but the message must
        # not read "10.0 > 10.0" and leave the reader hunting a phantom.
        tie = f"{collapse_index:.1f}" == f"{hc.max_collapse_index:.1f}"
        fails.append(
            f"collapse_index Mcw/Mcd ({collapse_index:.1f}) "
            f"> max_collapse_index ({hc.max_collapse_index:.1f})"
            + (
                # No em-dash and no "; " inside this bracket: the first is
                # where the reason tally cuts an explanatory tail, the second
                # is the field separator.
                f" [floating-point tie: {collapse_index!r} vs "
                f"{float(hc.max_collapse_index)!r}, raise max_collapse_index "
                f"if this ratio is meant to pass]"
                if tie else ""
            )
        )
    if ar < hc.min_junction_aspect_ratio:
        fails.append(
            f"junction_ar ({ar:.2f}) < min_junction_aspect_ratio "
            f"({hc.min_junction_aspect_ratio:.2f})"
        )
    elif ar > hc.max_junction_aspect_ratio:
        fails.append(
            f"junction_ar ({ar:.2f}) > max_junction_aspect_ratio "
            f"({hc.max_junction_aspect_ratio:.2f})"
        )
    return fails


def _operating_failure_reasons(hc, Po_mbar: float, delam: float) -> list[str]:
    """
    Return one reason per violated *operating-point* hard constraint.

    Separate from the geometry screen because these need a solve first: in
    Mode B the drive pressure is derived, not swept, so ``Po_required_mbar``
    breaching its ceiling is a statement about the candidate's oil demand rather
    than about anything the user asked for.
    """
    fails: list[str] = []
    if Po_mbar < hc.min_Po_in_mbar:
        fails.append(
            f"Po_required ({Po_mbar:.0f} mbar) < min_Po_in_mbar ({hc.min_Po_in_mbar:.0f})"
        )
    if Po_mbar > hc.max_Po_in_mbar:
        fails.append(
            f"Po_required ({Po_mbar:.0f} mbar) > max_Po_in_mbar ({hc.max_Po_in_mbar:.0f})"
        )
    if hc.max_delam_line_load_N_per_m is not None:
        if delam > hc.max_delam_line_load_N_per_m:
            fails.append(
                f"delam_line_load ({delam:.2f} N/m) > max_delam_line_load_N_per_m "
                f"({hc.max_delam_line_load_N_per_m:.2f})"
            )
    return fails


def _check_soft_constraints(row: dict, soft) -> list[str]:
    """Return a list of soft-constraint violation labels (empty if all pass)."""
    flags: list[str] = []
    if row.get("Q_spread_pct", 0.0) > soft.max_Q_spread_pct:
        flags.append("Q_spread")
    if row.get("f_pred_mean", 0.0) > 0 and "f_pred_mean" in row:
        # freq_spread: no dedicated metric yet (PM-2)
        pass
    if row.get("Po_in_mbar", 0.0) > soft.max_Po_in_mbar:
        flags.append("Po_too_high")
    if row.get("active_fraction", 0.0) < soft.min_active_fraction:
        flags.append("active_fraction_low")
    return flags


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

def run_design_search(spec: "DesignSearchSpec") -> pd.DataFrame:
    """
    Execute the design-from-targets parameter sweep.

    For each candidate in the Cartesian product of sweep_ranges, the engine:
      1. Pre-checks geometry hard constraints (fast, no solver).
      2. Derives Mcl_max from footprint geometry (Mcl is NEVER a sweep input).
      3. Builds a DeviceConfig and evaluates via Mode B (flow-flow BC).
      4. Checks soft constraints and records any violations.

    Candidates are ranked by the optimisation objective:
      "max_throughput"   → descending Q_total_mlhr
      "max_window_width" → not yet supported (requires robustness sweep)

    Parameters
    ----------
    spec : DesignSearchSpec  (from load_design_search)

    Returns
    -------
    pd.DataFrame — one row per candidate, sorted by rank.
    """
    from stepgen.design.sweep import evaluate_candidate

    hc   = spec.hard_constraints
    soft = spec.soft_constraints
    sr   = spec.sweep_ranges
    fp   = spec.footprint

    rows: list[dict] = []

    combinations = list(itertools.product(
        sr.Mcd_um, sr.Mcw_um, sr.junction_ar, sr.mcw_um, sr.mcl_rung_um,
    ))

    for Mcd_um, Mcw_um, ar, mcw_um, mcl_rung_um in tqdm(
        combinations, desc="design search", unit="candidate"
    ):
        # ── SI conversions ──────────────────────────────────────────────────
        Mcd_m      = Mcd_um      * 1e-6
        Mcw_m      = Mcw_um      * 1e-6
        mcw_m      = mcw_um      * 1e-6
        mcl_rung_m = mcl_rung_um * 1e-6

        # ── Derived: mcd, exit geometry, pitch ──────────────────────────────
        # mcd is fully determined by target droplet + AR (exit_depth = mcd,
        # exit_width = AR × mcd, pitch = 2 × exit_width)
        mcd_m            = _derive_mcd_from_ar(spec, ar)
        exit_w_m, exit_d_m = _derive_junction_geometry(spec, mcd_m)
        pitch_m          = 2.0 * exit_w_m
        mcd_um           = mcd_m   * 1e6
        pitch_derived_um = pitch_m * 1e6
        junction_ar      = ar      # already the AR value being swept

        # ── Pre-filter: geometry hard constraints ───────────────────────────
        # The boolean is DERIVED from the reasons, not kept beside them: a
        # collapsed `and` of six conditions is what made a rejected candidate
        # reach the CSV with no reason recorded anywhere.
        collapse_index = Mcw_m / max(Mcd_m, 1e-12)
        geom_failures = _geometry_failure_reasons(
            hc, Mcd_m, Mcw_m, mcd_m, mcw_m, collapse_index, ar
        )
        passes_hard_geom = not geom_failures

        # ── Compute Mcl_max from footprint ──────────────────────────────────
        Mcl_max_m = _max_mcl_for_footprint(fp, Mcw_m, mcl_rung_m)
        Nmc_derived = int(math.floor(Mcl_max_m / max(pitch_m, 1e-12)))

        if Nmc_derived < 2:
            # Footprint can't fit a usable device.
            #
            # This append used to be guarded by `if not passes_hard_geom`, so a
            # candidate whose geometry was FINE and which merely did not fit was
            # dropped from the output entirely — no row, no reason, no trace.
            # That is the same defect as a missing reason column, in its extreme
            # form, so it is fixed here: every candidate the search considers now
            # appears in the frame with a verdict.
            fails = [
                f"footprint fits only {Nmc_derived} DFUs (need >= 2) — "
                f"Mcl_max {Mcl_max_m*1e3:.1f} mm at pitch {pitch_derived_um:.1f} µm"
            ] + geom_failures
            row = {
                "Mcd_um": Mcd_um, "Mcw_um": Mcw_um,
                "Mcl_derived_mm": 0.0, "Nmc_derived": Nmc_derived,
                "junction_ar": ar,
                "mcd_derived_um": mcd_um, "pitch_derived_um": pitch_derived_um,
                "mcw_um": mcw_um, "mcl_rung_um": mcl_rung_um,
                "exit_width_um": exit_w_m * 1e6,
                "exit_depth_um": exit_d_m * 1e6,
                "Q_total_mlhr": float("nan"),
                "Q_oil_mlhr": float("nan"),
                "Q_water_mlhr": spec.design_targets.Qw_in_mlhr,
                "Q_spread_pct": float("nan"),
                "Po_required_mbar": float("nan"),
                "active_fraction": float("nan"),
                "reverse_fraction": float("nan"),
                "off_fraction": float("nan"),
                "D_pred_um": exit_d_m * 1e6,   # rough proxy
                "f_pred_mean_Hz": float("nan"),
                "collapse_index": collapse_index,
                "passes_hard": False,
                "hard_constraint_failures": "; ".join(fails),
                "soft_flags": "footprint_too_small",
                "error": "footprint_too_small",
            }
            rows.append(row)
            continue

        Mcl_derived_m = Mcl_max_m   # use the maximum available Mcl

        # ── Build config and evaluate ───────────────────────────────────────
        try:
            cfg = _build_device_config(
                spec, Mcd_m, Mcw_m, Mcl_derived_m,
                pitch_m, mcd_m, mcw_m, mcl_rung_m,
                exit_w_m, exit_d_m,
            )
            Qo_mlhr = (
                spec.design_targets.target_emulsion_ratio
                * spec.design_targets.Qw_in_mlhr
            )
            eval_row = evaluate_candidate(
                cfg,
                Qw_in_mlhr=spec.design_targets.Qw_in_mlhr,
                Qo_in_mlhr=Qo_mlhr,
            )
        except Exception as exc:
            nan = float("nan")
            row = {
                "Mcd_um": Mcd_um, "Mcw_um": Mcw_um,
                "Mcl_derived_mm": Mcl_derived_m * 1e3,
                "Nmc_derived": Nmc_derived,
                "junction_ar": ar,
                "mcd_derived_um": mcd_um, "pitch_derived_um": pitch_derived_um,
                "mcw_um": mcw_um, "mcl_rung_um": mcl_rung_um,
                "exit_width_um": exit_w_m * 1e6,
                "exit_depth_um": exit_d_m * 1e6,
                "Q_total_mlhr": nan, "Q_oil_mlhr": nan,
                "Q_water_mlhr": spec.design_targets.Qw_in_mlhr,
                "Q_spread_pct": nan, "Po_required_mbar": nan,
                "active_fraction": nan,
                "reverse_fraction": nan, "off_fraction": nan,
                "D_pred_um": nan,
                "f_pred_mean_Hz": nan, "collapse_index": collapse_index,
                "passes_hard": False,
                "hard_constraint_failures": "; ".join(
                    [f"solver error: {exc}"] + geom_failures
                ),
                "soft_flags": "solver_error",
                "error": str(exc),
            }
            rows.append(row)
            continue

        # ── Soft constraints ────────────────────────────────────────────────
        soft_flags = _check_soft_constraints(eval_row, soft)

        # ── Hard constraints: FOUR sources, one reason list ──────────────────
        # `passes_hard` is a conjunction of four independent screens, and until
        # 2026-08-06 only one of them (`evaluate_candidate`'s) had a reason
        # string in existence anywhere — and the search dropped even that.  So a
        # search over an oil-starved geometry returned `passes_hard: False` on
        # every row and the CSV said nothing about why.  All four now write into
        # one list, and the verdict is derived from it.
        Po_mbar = eval_row.get("Po_in_mbar", 0.0) or 0.0
        delam   = eval_row.get("delam_line_load", 0.0) or 0.0

        hard_failures = list(geom_failures)
        hard_failures += _operating_failure_reasons(hc, Po_mbar, delam)

        # `evaluate_candidate` already joined its own (fab caps, footprint fit
        # and — since `1cdcb0b` — reverse flow) with "; ".  Carried verbatim.
        solved_failures = eval_row.get("hard_constraint_failures", "") or ""
        if solved_failures:
            hard_failures.append(solved_failures)

        passes_hard = not hard_failures

        Q_water = spec.design_targets.Qw_in_mlhr
        Q_oil   = eval_row.get("Q_oil_total", float("nan"))
        if isinstance(Q_oil, float) and not math.isnan(Q_oil):
            Q_oil_mlhr = Q_oil * 3.6e6          # m³/s → mL/hr
        else:
            Q_oil_mlhr = float("nan")
        Q_total_mlhr = Q_water + Q_oil_mlhr

        row = {
            "Mcd_um":           Mcd_um,
            "Mcw_um":           Mcw_um,
            "Mcl_derived_mm":   Mcl_derived_m * 1e3,
            "Nmc_derived":      Nmc_derived,
            "junction_ar":      ar,
            "mcd_derived_um":   mcd_um,
            "pitch_derived_um": pitch_derived_um,
            "mcw_um":           mcw_um,
            "mcl_rung_um":      mcl_rung_um,
            "exit_width_um":    exit_w_m * 1e6,
            "exit_depth_um":    exit_d_m * 1e6,
            "Q_total_mlhr":    Q_total_mlhr,
            "Q_oil_mlhr":      Q_oil_mlhr,
            "Q_water_mlhr":    Q_water,
            "Q_spread_pct":    eval_row.get("Q_spread_pct", float("nan")),
            "Po_required_mbar": eval_row.get("Po_in_mbar", float("nan")),
            "active_fraction":  eval_row.get("active_fraction", float("nan")),
            # Carried because the reverse-flow guard is what now fails these
            # rows, and the fraction that caused the failure was the one number
            # the search dropped while keeping `active_fraction`.
            "reverse_fraction": eval_row.get("reverse_fraction", float("nan")),
            "off_fraction":     eval_row.get("off_fraction", float("nan")),
            "D_pred_um":        eval_row.get("D_pred", float("nan")) * 1e6
                                if "D_pred" in eval_row and not math.isnan(eval_row.get("D_pred", float("nan")))
                                else float("nan"),
            "f_pred_mean_Hz":   eval_row.get("f_pred_mean", float("nan")),
            "collapse_index":   collapse_index,
            "passes_hard":      passes_hard,
            "hard_constraint_failures": "; ".join(hard_failures),
            "soft_flags":       ";".join(soft_flags) if soft_flags else "",
            "error":            None,
        }
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # ── Rank by objective ───────────────────────────────────────────────────
    obj = spec.optimization_target
    if obj == "max_throughput":
        sort_col = "Q_total_mlhr"
        ascending = False
    elif obj == "max_window_width":
        # Window width requires robustness sweep; fall back to throughput
        sort_col = "Q_total_mlhr"
        ascending = False
    else:
        sort_col = "Q_total_mlhr"
        ascending = False

    df_sorted = df.sort_values(sort_col, ascending=ascending, na_position="last")
    df_sorted = df_sorted.reset_index(drop=True)
    df_sorted.insert(0, "rank", range(1, len(df_sorted) + 1))

    return df_sorted
