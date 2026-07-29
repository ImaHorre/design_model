"""
regime_estimator.py — "will it make droplets, and if not what do I change?"
============================================================================
Given a device config and an operating point (Po, Qw), estimate:
  - the junction capillary number Ca (continuous- and dispersed-phase),
  - the driving-pressure margin over the calibrated capillary entry pressure,
  - a verdict: STALL / DRIPPING / BLOWOUT, with a concrete operating-change hint.

Key finding this encodes (see report.md):
  Junction Ca is O(1e-5) across the entire feasible pressure range -- you are
  deep in the capillary-dominated DRIPPING regime everywhere, which is why
  droplet size is flow-independent. Therefore the two failure modes are NOT a
  Ca=0.3 jetting transition:
    * low-Po STALL  : DP_rung < P_entry  (oil cannot overcome capillary entry) -- clean, capillary.
    * high-Po BLOWOUT: pressure-driven / spatial-manifold instability (reverse
      rungs, P_peak, dP spread). This simple ladder config stays uniform, so the
      spatial "device start/end" jetting needs the manifold geometry to reproduce.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stepgen.config import load_config                       # noqa: E402
from stepgen.models.generator import iterative_solve         # noqa: E402
from stepgen.models.metrics import compute_metrics           # noqa: E402
from stepgen.models.hydraulics import simulate               # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "v5_30.yaml"

# Jetting Ca threshold (literature dripping->jetting is ~O(0.1-1); used only to
# demonstrate how far the junction is from it -- it is never approached here).
CA_JET = 0.3


@dataclass(frozen=True)
class RegimePoint:
    Po_mbar: float
    Qw_mlhr: float
    dP_rung_Pa: float
    P_entry_Pa: float
    entry_margin_Pa: float        # dP_rung - P_entry ; <0 => stall
    active_fraction: float
    reverse_fraction: float
    P_peak_mbar: float
    U_junction_ms: float
    Ca_continuous: float
    Ca_dispersed: float
    verdict: str                  # "stall" | "dripping" | "blowout"
    hint: str


def estimate_point(
    config,
    Po_mbar: float,
    Qw_mlhr: float,
    P_entry_Pa: float,
    gamma_Nm: float = 15e-3,
    P_blowout_mbar: float = 1000.0,
) -> RegimePoint:
    """
    Classify a single operating point. ``P_entry_Pa`` is the calibrated capillary
    entry pressure (from inversion.entry_pressure_from_onset). ``P_blowout_mbar``
    is the observed high-Po instability boundary (user: ~1000 mbar).
    """
    sim = simulate(config, float(Po_mbar), float(Qw_mlhr), 0.0)
    dP_rung = float(np.mean(sim.P_oil - sim.P_water))

    res = iterative_solve(config, float(Po_mbar), float(Qw_mlhr))
    m = compute_metrics(config, res)

    A = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
    Q = m.Q_per_rung_avg if m.Q_per_rung_avg > 0 else float(np.mean(res.Q_rungs))
    U = Q / A if A > 0 else 0.0
    Ca_c = config.fluids.mu_continuous * U / gamma_Nm
    Ca_d = config.fluids.mu_dispersed * U / gamma_Nm

    margin = dP_rung - P_entry_Pa

    # ── Verdict logic ───────────────────────────────────────────────────────
    # The CALIBRATED capillary entry pressure (P_entry) is authoritative for the
    # stall boundary -- not the config's uncalibrated dP_cap_ow. reverse_fraction
    # / P_peak remain the diagnostics for the high-Po pressure-blowout mode.
    if margin <= 0:
        verdict = "stall"
        deficit_mbar = max(-margin, 0.0) / 100.0
        hint = (f"At/below capillary entry pressure: raise Po by >~{deficit_mbar:.0f} mbar "
                f"(or lower Qw / raise surfactant to reduce entry pressure).")
    elif Po_mbar >= P_blowout_mbar or m.reverse_fraction > 0.1:
        verdict = "blowout"
        hint = ("Pressure-driven instability regime (spatial manifold blowout at "
                "device start/end). Lower Po below the instability boundary; a "
                "flatter manifold widens the usable window.")
    else:
        verdict = "dripping"
        hint = (f"Stable dripping. Junction Ca={Ca_c:.1e} (continuous) is ~{CA_JET/Ca_c:.0e}x "
                f"below the jetting threshold; size is geometry-set, rate scales with Po.")

    return RegimePoint(
        Po_mbar=float(Po_mbar), Qw_mlhr=float(Qw_mlhr),
        dP_rung_Pa=dP_rung, P_entry_Pa=P_entry_Pa, entry_margin_Pa=margin,
        active_fraction=m.active_fraction, reverse_fraction=m.reverse_fraction,
        P_peak_mbar=m.P_peak / 100.0, U_junction_ms=U,
        Ca_continuous=Ca_c, Ca_dispersed=Ca_d,
        verdict=verdict, hint=hint,
    )


def estimate_grid(
    config,
    Po_grid_mbar,
    Qw_mlhr: float,
    P_entry_Pa: float,
    gamma_Nm: float = 15e-3,
    P_blowout_mbar: float = 1000.0,
):
    """Convenience: list[RegimePoint] over a Po grid at fixed Qw."""
    return [estimate_point(config, po, Qw_mlhr, P_entry_Pa, gamma_Nm, P_blowout_mbar)
            for po in Po_grid_mbar]


if __name__ == "__main__":
    cfg = load_config(str(CONFIG_PATH))
    # Use the calibrated entry pressure from the onset inversion.
    from inversion import entry_pressure_from_onset
    P_entry = entry_pressure_from_onset(cfg).value
    print(f"Calibrated capillary entry pressure P_entry = {P_entry:.0f} Pa "
          f"({P_entry/100:.0f} mbar-equivalent DP_rung)\n")

    print(f"{'Po':>5} {'DPrung':>7} {'margin':>7} {'act':>4} {'rev':>4} "
          f"{'Ppeak':>6} {'Ca_c':>8} {'verdict':>9}  hint")
    for rp in estimate_grid(cfg, [20, 30, 50, 100, 200, 400, 600, 800, 1000, 1200], 5.0, P_entry):
        print(f"{rp.Po_mbar:5.0f} {rp.dP_rung_Pa:7.0f} {rp.entry_margin_Pa:7.0f} "
              f"{rp.active_fraction:4.2f} {rp.reverse_fraction:4.2f} {rp.P_peak_mbar:6.0f} "
              f"{rp.Ca_continuous:8.1e} {rp.verdict:>9}  {rp.hint[:60]}")
