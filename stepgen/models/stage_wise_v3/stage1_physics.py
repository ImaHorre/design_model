"""
Stage-Wise Model v3: Stage 1 Simplified Poiseuille Refill Physics
=================================================================

Physics basis (updated March 2026):

    t_stage1 = C_visc × V_reset / Q_rung
             = C_visc × V_reset × R_rung / DP_rung

where:
  - V_reset = L_r × exit_width × exit_depth  (junction exit volume to displace)
  - L_r ≈ exit_width  (confirmed reset distance)
  - R_rung = f(α) × μ_oil × mcl / (w × h³)  (rung Poiseuille resistance)
  - DP_rung = P_oil(x) − P_water(x)  (pressure difference driving flow through rung)
    (DISTINCT from P_j which is preneck junction pressure for Stage 2)
  - C_visc = stage1_viscosity_correction  (calibration multiplier, default 1.0)

Rationale:
  The rate-limiting step for Stage 1 refill is oil delivery through the rung,
  not meniscus motion through the short junction exit. R_rung >> R_exit by ~500×,
  so the correct model is V_reset / Q_rung where Q_rung = DP_rung / R_rung.

  The two-fluid Washburn ODE through the junction exit (previous approach)
  predicted ~0.2 ms at 200–300 mbar — orders of magnitude too fast, and was
  superseded by this rung-flow model.

  Calibration against V5_30_3_3 data (2026-03-20, data/analysis/calibrate_cvisc.py):
    - mu_oil = 60 mPa.s, rung 10x8x4000 um, junction 30x10 um, Qw = 5 mL/hr
    - Hydraulic network gives DP_rung ~ 82% of Po (water back-pressure at Qw = 5 mL/hr)
    - Fitted C_visc = 0.96 +/- 0.06 across Po = 200-500 mbar
    - Default C_visc = 1.0 is correct for this device; no large empirical correction needed.
    - Residual trend: model exponent -1.026 vs observed -1.168; likely capillary
      back-pressure (~20 mbar) reduces effective DP more at low Po. Not corrected here.

  C_visc is a calibration multiplier for device-specific deviations (surface viscosity,
  contact-line effects, geometric entry/exit losses). For bulk Poiseuille flow with
  known mu_oil the expected value is close to 1.0. Re-calibrate if mu_oil changes
  or a new device geometry is used.

  The superseded Washburn model is archived at:
  stepgen/models/stage_wise_v3/legacy/stage1_physics_washburn_defunct.py
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

    t_base = V_reset / Q_effective if Q_effective > 0 else float('inf')

    # Effective viscosity correction — calibrated from t_stage1 vs Po experiment
    C_visc = v3_config.stage1_viscosity_correction
    t_displacement = C_visc * t_base

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
        "t_base_s": t_base,
        "viscosity_correction": C_visc,
        "exit_width_m": exit_width,
        "exit_depth_m": exit_depth,
        "L_r_m": L_r,
        "physics_valid": DP_rung > 0 and R_rung > 0,
    }

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism="poiseuille_viscosity_corrected",
        physics_basis="V_reset / (DP_rung / R_rung) × C_visc",
        diagnostics=diagnostics
    )


def compute_rung_resistance(config: "DeviceConfig") -> float:
    """
    Compute Poiseuille resistance of the rung channel [Pa·s/m³].

        R_rung = f(α) × μ_oil × mcl / (w × h³)

    where h = min(mcd, mcw), w = max(mcd, mcw), α = h/w.
    """
    mcd = config.geometry.rung.mcd
    mcw = config.geometry.rung.mcw
    mcl = config.geometry.rung.mcl
    mu_oil = config.fluids.mu_dispersed

    h = min(mcd, mcw)
    w = max(mcd, mcw)
    alpha = h / w                           # ≤ 1 by construction
    f_alpha = _shah_london_factor(alpha)

    return f_alpha * mu_oil * mcl / (w * h**3)


def _shah_london_factor(alpha: float) -> float:
    """
    Shah & London rectangular channel resistance factor f(α).

    f(α) = 96(1 - 1.3553α + 1.9467α² - 1.7012α³ + 0.9564α⁴ - 0.2537α⁵)
    Valid for α = h/w ∈ (0, 1].
    """
    if alpha <= 0:
        return 96.0
    a = min(alpha, 1.0)
    return 96.0 * (1 - 1.3553*a + 1.9467*a**2 - 1.7012*a**3 + 0.9564*a**4 - 0.2537*a**5)
