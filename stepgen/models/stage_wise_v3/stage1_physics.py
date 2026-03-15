"""
Stage-Wise Model v3: Stage 1 Simplified Poiseuille Refill Physics
=================================================================

Physics basis (updated March 2026):

    t_stage1 = C_visc × V_reset / Q_rung
             = C_visc × V_reset × R_rung / P_j

where:
  - V_reset = L_r × exit_width × exit_depth  (junction exit volume to displace)
  - L_r ≈ exit_width  (confirmed reset distance)
  - R_rung = f(α) × μ_oil × mcl / (w × h³)  (rung Poiseuille resistance)
  - P_j = P_oil − P_water  (pre-neck junction pressure from hydraulic network)
  - C_visc = stage1_viscosity_correction  (calibration multiplier, default 1.0)

Rationale:
  The rate-limiting step for Stage 1 refill is oil delivery through the rung,
  not meniscus motion through the short junction exit. R_rung >> R_exit by ~500×,
  so the correct model is V_reset / Q_rung where Q_rung = P_j / R_rung.

  The two-fluid Washburn ODE through the 15 µm junction exit (previous approach)
  predicted ~0.2 ms at 200–300 mbar — orders of magnitude too fast. This
  simplified model gives ~0.25–0.30 s at 200–300 mbar without correction, which
  is 3–4× short of experiment.

  C_visc accounts for fresh-interface effects (surface viscosity, partial SDS
  depletion) that slow flow beyond bulk Poiseuille. Expected value ~3–5× from
  experiment; to be calibrated from t_stage1 vs Po data. Preserves 1/Po scaling.

  Candidate mechanisms for C_visc > 1 are documented in:
  docs/03_stage_wise_model/v3/stage1_slowdown_mechanisms_research.md

  The superseded Washburn model is archived at:
  stepgen/models/stage_wise_v3/legacy/stage1_physics_washburn_defunct.py
"""

from __future__ import annotations

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
    P_j: float,
    Q_rung: float,
    config: "DeviceConfig",
    v3_config: "StageWiseV3Config"
) -> Stage1Result:
    """
    Solve Stage 1 using simplified Poiseuille refill model.

    Parameters
    ----------
    P_j : float
        Junction pressure difference P_oil − P_water [Pa]
    Q_rung : float
        Rung flow rate from hydraulic network [m³/s] (used for diagnostics only;
        t is computed from P_j / R_rung directly for self-consistency)
    config : DeviceConfig
    v3_config : StageWiseV3Config

    Returns
    -------
    Stage1Result
    """

    # Junction exit geometry — the volume that must be displaced
    exit_width = config.geometry.junction.exit_width
    exit_depth = config.geometry.junction.exit_depth
    L_r = exit_width                               # reset distance ≈ one junction exit width
    V_reset = L_r * exit_width * exit_depth        # [m³]

    # Rung Poiseuille resistance from geometry
    R_rung = compute_rung_resistance(config)

    # Base refill time: V_reset / Q_rung where Q_rung = P_j / R_rung
    if P_j <= 0 or R_rung <= 0:
        t_base = float('inf')
    else:
        t_base = V_reset * R_rung / P_j            # = V_reset / (P_j / R_rung)

    # Effective viscosity correction — calibrated from t_stage1 vs Po experiment
    C_visc = v3_config.stage1_viscosity_correction
    t_displacement = C_visc * t_base

    diagnostics = {
        "V_reset_m3": V_reset,
        "R_rung_Pa_s_per_m3": R_rung,
        "P_j_Pa": P_j,
        "Q_rung_network_m3s": Q_rung,
        "Q_rung_computed_m3s": P_j / R_rung if R_rung > 0 else 0.0,
        "t_base_s": t_base,
        "viscosity_correction": C_visc,
        "exit_width_m": exit_width,
        "exit_depth_m": exit_depth,
        "L_r_m": L_r,
        "physics_valid": P_j > 0 and R_rung > 0,
    }

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism="poiseuille_viscosity_corrected",
        physics_basis="V_reset / (P_j / R_rung) × C_visc",
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
