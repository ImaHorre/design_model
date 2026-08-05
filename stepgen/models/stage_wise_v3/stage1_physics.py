"""
Stage-Wise Model v3: Stage 1 Simplified Poiseuille Refill Physics
=================================================================

Physics basis (updated August 2026 — W2-1):

    t_stage1 = V_reset / Q_rung
             = V_reset × R_rung / DP_rung

where:
  - V_reset = L_r × exit_width × exit_depth  (junction exit volume to displace)
  - L_r     = sqrt(exit_width × exit_depth)  (measured against L_menpoint)
  - R_rung  = the ONE rectangular-duct resistance, integrated over the real DFU
              profile — see stepgen.models.resistance
  - DP_rung = P_oil(x) − P_water(x)  (pressure difference driving flow through rung)
    (DISTINCT from P_j which is preneck junction pressure for Stage 2)

**There is no correction term.**  `C_visc` (`stage1_viscosity_correction`) was
deleted on 2026-08-05: a global multiplier on ΔP/R at fixed geometry is a
viscosity, and must be recorded as one.  See the note in `__init__.py` and
`experimental_workspaces/comp_oil_viscosity/`.

Rationale:
  The rate-limiting step for Stage 1 refill is oil delivery through the rung,
  not meniscus motion through the short junction exit. R_rung >> R_exit by ~500×,
  so the correct model is V_reset / Q_rung where Q_rung = DP_rung / R_rung.

  The two-fluid Washburn ODE through the junction exit (previous approach)
  predicted ~0.2 ms at 200–300 mbar — orders of magnitude too fast, and was
  superseded by this rung-flow model.  It is archived at
  stepgen/models/stage_wise_v3/legacy/stage1_physics_washburn_defunct.py

  The 2026-03 C_visc calibration (0.96 ± 0.06) is historical only: it was fitted
  against timings later corrected ×0.5 for a frame-rate error, through a rung
  resistance since found to be 1.53× too high, with a reset length since
  replaced on measured evidence. Three of its inputs have changed; the number
  does not survive any of them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from . import StageWiseV3Config


@dataclass(frozen=True)
class Stage1Result:
    """Stage 1 physics result."""
    t_displacement: float           # Stage 1 duration [s]
    mechanism: str                  # Physics model label
    physics_basis: str              # Description of physics used
    diagnostics: Dict[str, Any]     # Diagnostic information


def solve_stage1_physics(
    DP_rung: float,
    Q_rung: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> Stage1Result:
    """
    Solve Stage 1 using simplified Poiseuille refill model.

    Parameters
    ----------
    DP_rung : float
        Pressure difference driving flow through rung: DP_rung = P_oil(x) - P_water(x) [Pa]
        This is the driving pressure for rung Poiseuille flow during Stage 1 refill
        DISTINCT from P_j which is preneck junction pressure for Stage 2 droplet formation
    Q_rung : float
        Rung flow rate from hydraulic network [m³/s] (used for diagnostics only;
        t is computed from Po_local / R_rung directly for self-consistency)
    config : DeviceConfig
    v3_config : StageWiseV3Config

    Returns
    -------
    Stage1Result
    """

    # Junction exit geometry — the volume that must be displaced during reset
    exit_width = config.geometry.junction.exit_width
    exit_depth = config.geometry.junction.exit_depth

    # Reset length L_r — the distance the meniscus retreats after snap-off and must
    # re-advance before the next droplet grows.  Two modes:
    #
    #   "geometric"  (default)  L_r = sqrt(exit_width × exit_depth)
    #   "exit_width" (legacy)   L_r = exit_width
    #
    # both then scaled by ``stage1_reset_length_factor`` (default 1.0).
    #
    # The geometric form is the hydraulic-radius scale of the exit and is what the
    # data supports.  Validated 2026-08-03 against the V5-8-1 Po sweep
    # (experimental_workspaces/po_sweep/data/stage_timings.csv): the volume actually
    # delivered during Stage 1, V_S1 = Q_rung × t_S1_measured, is
    #     5.31e-15 m³ @ 200 mbar and 5.30e-15 m³ @ 300 mbar
    # against sqrt(w·h)·w·h = 5.20e-15 m³ for the 30 × 10 µm exit — 2% agreement at
    # both pressures, drifting to −25% by 800 mbar where Stage 1 is only ~5 frames.
    # It also matches the directly measured L_menpoint (14.4–20 µm): sqrt(w·h) =
    # 17.3 µm, where the legacy exit_width form gives 30 µm — 1.7× too long.
    #
    # DEPARTURE FROM PREVIOUS BEHAVIOUR: the default was L_r = exit_width, which
    # over-predicted t_stage1 by ~2× at 200 mbar (1.42 s modelled vs 0.669 s
    # measured).  Set mode="exit_width" to restore it exactly.
    #
    # NOTE: C_visc (stage1_viscosity_correction) was calibrated 2026-03-20 against
    # timings that were later corrected ×0.5 (fps 25→50, po_sweep/BRIEF.md
    # 2026-06-08).  That recalibration is still outstanding and is tracked
    # separately — this change fixes the reset length, not C_visc.
    mode = v3_config.stage1_reset_length_mode
    if mode == "exit_width":
        L_r_base = exit_width
    elif mode == "geometric":
        L_r_base = math.sqrt(exit_width * exit_depth)
    else:
        # Fail loudly: silently defaulting a typo to "geometric" would swap the
        # reset length by ~1.7x on a 3:1 exit without anything in the output saying so.
        raise ValueError(
            f"stage1_reset_length_mode must be 'geometric' or 'exit_width', got {mode!r}"
        )
    L_r = L_r_base * v3_config.stage1_reset_length_factor
    V_reset = L_r * exit_width * exit_depth        # [m³]

    # Rung Poiseuille resistance from geometry
    R_rung = compute_rung_resistance(config)

    # Optional capillary back-pressure correction (physics plan A3, Step 4-5).
    # P_cap = γ·cos(θ_eff)·(1/h + 1/w) opposes oil advance through the reset zone.
    # Disabled by default — enabling requires re-calibration of C_visc.
    P_cap = 0.0
    if v3_config.enable_stage1_capillary_correction:
        theta_rad = math.radians(v3_config.theta_effective)
        gamma = v3_config.gamma_effective
        h = exit_depth
        w = exit_width
        P_cap = gamma * math.cos(theta_rad) * (1.0 / h + 1.0 / w)

    # Effective driving pressure after capillary correction
    DP_effective = max(DP_rung - P_cap, 0.0)

    # Base refill time: V_reset / Q_rung.
    #
    # Q_rung is taken from the hydraulic network when the caller supplies it, and
    # only recomputed as DP_effective / R_rung when it is not available.
    #
    # DEPARTURE FROM PREVIOUS BEHAVIOUR (2026-08-03): this function previously
    # always recomputed Q internally and used the passed-in Q_rung for diagnostics
    # only, "for self-consistency".  That is the wrong self: `compute_rung_resistance`
    # below (full mcl, Shah & London) and `stepgen.models.hydraulics.rung_resistance`
    # (mcl × constriction_ratio, a different rectangular formula) are two different
    # models of the same rung and disagree by 25% on V5-30 — 2.697e18 vs 2.155e18
    # Pa·s/m³.  Recomputing meant Stage 1 silently used a rung the rest of the solve
    # did not have.
    #
    # The network flow is the one validated against experiment: with it, V_reset/Q
    # reproduces the measured Stage-1 time to 2% at 200 and 300 mbar (0.655 vs 0.669 s;
    # 0.385 vs 0.392 s).  Recomputing internally gives 0.820 s at 200 mbar, 23% high.
    #
    # Capillary back-pressure, when enabled, still scales the network flow by
    # DP_effective/DP_rung so the correction keeps acting.
    if Q_rung and Q_rung > 0:
        Q_effective = Q_rung
        if DP_rung > 0 and DP_effective != DP_rung:
            Q_effective = Q_rung * (DP_effective / DP_rung)
    elif DP_effective > 0 and R_rung > 0:
        Q_effective = DP_effective / R_rung
    else:
        Q_effective = 0.0

    t_displacement = V_reset / Q_effective if Q_effective > 0 else float('inf')

    diagnostics = {
        "V_reset_m3": V_reset,
        "R_rung_Pa_s_per_m3": R_rung,
        "DP_rung_Pa": DP_rung,
        "P_cap_Pa": P_cap,
        "DP_effective_Pa": DP_effective,
        "capillary_correction_enabled": v3_config.enable_stage1_capillary_correction,
        "reset_length_factor": v3_config.stage1_reset_length_factor,
        "reset_length_mode": v3_config.stage1_reset_length_mode,
        "pressure_type": "rung_pressure_difference_driving_flow",
        "Q_rung_network_m3s": Q_rung,
        "Q_rung_computed_m3s": DP_effective / R_rung if R_rung > 0 else 0.0,
        "Q_rung_used_m3s": Q_effective,
        "Q_source": "network" if (Q_rung and Q_rung > 0) else "recomputed",
        "t_base_s": t_displacement,
        "exit_width_m": exit_width,
        "exit_depth_m": exit_depth,
        "L_r_m": L_r,
        "physics_valid": DP_rung > 0 and R_rung > 0,
    }

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism="poiseuille_rung_flow",
        physics_basis="V_reset / Q_rung, no correction term",
        diagnostics=diagnostics
    )


def compute_rung_resistance(config: "DeviceConfig") -> float:
    """
    Poiseuille resistance of the rung channel [Pa·s/m³].

    Delegates to :func:`stepgen.models.resistance.rung_resistance` — **the**
    rung resistance, the same one the hydraulic network solves with.

    DEPARTURE FROM PREVIOUS BEHAVIOUR (W2-1).  This function used to compute its
    own, two ways wrong at once:

      1. It applied Shah & London's ``fRe`` in the parallel-plate normalisation
         ``f(α)·µL/(w·h³)`` instead of ``fRe·µL/(2·A·D_h²)``, which the polynomial
         is *defined* against — 2.47x high on V5-30, 8x as α → 0.
      2. It used the full ``mcl`` while the network used ``mcl × constriction_ratio``
         through a different formula, so Stage 1 and the solve that fed it were
         two different models of the same rung, 25% apart.

    Both are gone: one function, one answer, and where the config declares the
    real two-width DFU profile it is integrated piecewise over that.
    """
    from stepgen.models.resistance import rung_resistance

    return rung_resistance(config)
