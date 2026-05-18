#!/usr/bin/env python3
"""
compare_models.py – Diagnostic script for stepgen hydraulic model frequency discrepancy.

Decomposes the f_pred / f_exp ratio into its two independent sources:
  1. Droplet-size error  (D_pred vs D_exp)  → V_d underestimated
  2. Flow error          (Q_rung_pred vs Q_rung_exp)

Usage
-----
    python compare_models.py --config configs/w11.yaml \\
        --Po_mbar 400 --Qw_mlhr 1.5 \\
        [--f_exp_hz 2.6] [--D_exp_um <measured_value>]

Experimental flags are optional; omit to show model-only output.
"""
from __future__ import annotations

import argparse

import numpy as np
import matplotlib.pyplot as plt

from stepgen.config import load_config, mlhr_to_m3s
from stepgen.models.resistance import rung_resistance, main_channel_resistance_per_segment
from stepgen.models.droplets import droplet_diameter, droplet_volume, droplet_frequency
from stepgen.models.hydraulics import solve_linear
from stepgen.models.generator import iterative_solve, classify_rungs, RungRegime


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnose stepgen frequency vs experiment for a single operating point.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--config",    required=True,       help="Path to device YAML config")
    p.add_argument("--Po_mbar",   type=float, required=True, help="Oil inlet pressure [mbar]")
    p.add_argument("--Qw_mlhr",   type=float, required=True, help="Water flow rate [mL/hr]")
    p.add_argument("--f_exp_hz",  type=float, default=None,  help="Experimental frequency [Hz]")
    p.add_argument("--D_exp_um",  type=float, default=None,  help="Experimental droplet diameter [µm]")
    p.add_argument("--no_plot",   action="store_true",        help="Skip plot generation")
    p.add_argument("--plot_out",  default="compare_models.png", help="Output filename for plot")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    # ── 1. Load config ──────────────────────────────────────────────────────
    config = load_config(args.config)
    N = config.geometry.Nmc

    # ── 2. Stepgen mixed-BC solve (pressure oil, flow water) ────────────────
    result = iterative_solve(config, Po_in_mbar=args.Po_mbar, Qw_in_mlhr=args.Qw_mlhr)

    dP = result.P_oil - result.P_water
    dP_ow = config.droplet_model.dP_cap_ow_Pa
    dP_wo = config.droplet_model.dP_cap_wo_Pa
    regimes   = classify_rungs(dP, dP_ow, dP_wo)
    active_mask = regimes == RungRegime.ACTIVE
    n_active  = int(np.sum(active_mask))

    D_pred  = droplet_diameter(config)        # [m]
    V_d_pred = droplet_volume(D_pred)          # [m³]

    Q_rungs_active  = result.Q_rungs[active_mask]
    Q_rung_mean_pred = float(np.mean(Q_rungs_active)) if n_active > 0 else 0.0
    f_arr_active     = droplet_frequency(Q_rungs_active, D_pred)
    f_pred_mean      = float(np.mean(f_arr_active))   if n_active > 0 else 0.0

    R_Omc          = rung_resistance(config)
    R_OMc, R_WMc   = main_channel_resistance_per_segment(config)
    Q_oil_m3s      = result.Q_oil_total
    Q_water_m3s    = mlhr_to_m3s(args.Qw_mlhr)

    # ── 3. Stepgen linear (flow-controlled) cross-check ─────────────────────
    # Feed the Q_oil extracted from the mixed-BC solve; should give ≈ same Q_rungs.
    seed_result     = solve_linear(config, Q_oil=Q_oil_m3s, Q_water=Q_water_m3s)
    f_arr_seed      = droplet_frequency(seed_result.Q_rungs, D_pred)
    Q_rung_mean_seed = float(np.mean(seed_result.Q_rungs))
    f_seed_mean      = float(np.mean(f_arr_seed))

    # ── 4. Print diagnostic tables ──────────────────────────────────────────
    W = 65
    print()
    print("=" * W)
    print("  STEPGEN MODEL  (mixed-BC: pressure oil, flow water)")
    print("=" * W)
    print(f"  Operating point:     Po = {args.Po_mbar:.0f} mbar,  Qw = {args.Qw_mlhr:.2f} mL/hr")
    print(f"  Nmc:                 {N}")
    print(f"  R_Omc:               {R_Omc:.3e} Pa.s/m^3  (rung)")
    print(f"  R_OMc (oil main):    {R_OMc:.3e} Pa.s/m^3  (per pitch segment)")
    print(f"  R_WMc (water main):  {R_WMc:.3e} Pa.s/m^3  (per pitch segment)")
    print(f"  D_pred:              {D_pred*1e6:.2f} um")
    print(f"  V_d_pred:            {V_d_pred:.3e} m^3  ({V_d_pred*1e15:.3f} fL)")
    print(f"  Q_oil_total:         {Q_oil_m3s:.3e} m^3/s  ({Q_oil_m3s*1e6*3600:.4f} mL/hr)")
    print(f"  Q_rung (mean):       {Q_rung_mean_pred:.3e} m^3/s   "
          f"[ACTIVE: {n_active} / {N}]")
    print(f"  f_pred (mean):       {f_pred_mean:.3f} Hz")

    print()
    print("=" * W)
    print("  STEPGEN LINEAR  (flow-controlled, same Q_oil as above)")
    print("=" * W)
    print(f"  Q_oil in:            {Q_oil_m3s:.3e} m^3/s")
    print(f"  Q_water in:          {Q_water_m3s:.3e} m^3/s")
    print(f"  Q_rung (mean):       {Q_rung_mean_seed:.3e} m^3/s")
    print(f"  f_seed (mean):       {f_seed_mean:.3f} Hz   (using D_pred)")

    # ── 5. Experimental section ─────────────────────────────────────────────
    if args.f_exp_hz is not None or args.D_exp_um is not None:
        print()
        print("=" * W)
        print("  EXPERIMENTAL")
        print("=" * W)
        if args.f_exp_hz is not None:
            print(f"  f_exp:               {args.f_exp_hz:.3f} Hz")
        if args.D_exp_um is not None:
            print(f"  D_exp:               {args.D_exp_um:.2f} um")

    # ── 6. Decomposition (both experimental values provided) ────────────────
    if args.f_exp_hz is not None and args.D_exp_um is not None:
        D_exp  = args.D_exp_um * 1e-6
        f_exp  = args.f_exp_hz
        V_d_exp = droplet_volume(D_exp)
        Q_rung_exp = f_exp * V_d_exp          # implied Q_rung from experiment

        f_ratio  = f_pred_mean / f_exp
        D_ratio  = D_pred / D_exp
        V_ratio  = V_d_pred / V_d_exp         # = D_ratio^3
        Q_ratio  = Q_rung_mean_pred / Q_rung_exp

        # Algebraic check:  f_ratio = Q_ratio * (D_exp/D_pred)^3  ?
        check = Q_ratio * (D_exp / D_pred) ** 3
        rel_err = abs(check - f_ratio) / (abs(f_ratio) + 1e-30)
        ok = "OK" if rel_err < 0.05 else f"MISMATCH (rel err {rel_err:.1%})"

        # Reconciliation estimates
        D_needed = D_pred * (f_ratio ** (1.0 / 3.0))
        R_needed = R_Omc * Q_ratio

        print()
        print("=" * W)
        print("  DISCREPANCY DECOMPOSITION")
        print("=" * W)
        print(f"  f_pred / f_exp       = {f_ratio:.3f}   (total error factor)")
        print(f"  D_pred / D_exp       = {D_ratio:.4f}")
        print(f"  (D_pred/D_exp)^3     = {D_ratio**3:.4f}   (volume error contribution)")
        print(f"  Q_rung_pred / Q_exp  = {Q_ratio:.3f}   (flow error contribution)")
        print(f"  Check: Q_ratio * (D_exp/D_pred)^3 = {check:.3f}   {ok}")
        print()
        print(f"  Implied Q_rung_exp:  {Q_rung_exp:.3e} m^3/s  (= f_exp * V_d_exp)")
        print(f"  V_d_exp:             {V_d_exp:.3e} m^3  ({V_d_exp*1e15:.3f} fL)")
        print()
        print("  --- What would reconcile the model ---")
        print(f"  If only D wrong:  D_actual = {D_needed*1e6:.2f} um"
              f"  (vs D_pred = {D_pred*1e6:.2f} um,  factor = {D_needed/D_pred:.2f}x)")
        print(f"  If only R wrong:  R_effective = {R_needed:.3e} Pa.s/m^3"
              f"  (vs R_Omc = {R_Omc:.3e},  factor = {R_needed/R_Omc:.2f}x)")

    elif args.f_exp_hz is not None:
        # Frequency only – can't decompose, but can estimate D_actual
        f_exp    = args.f_exp_hz
        f_ratio  = f_pred_mean / f_exp
        D_needed = D_pred * (f_ratio ** (1.0 / 3.0))
        print()
        print("=" * W)
        print("  DISCREPANCY  (frequency only — D_exp not provided)")
        print("=" * W)
        print(f"  f_pred / f_exp       = {f_ratio:.3f}   (total error factor)")
        print(f"  If only D wrong:  D_actual = {D_needed*1e6:.2f} um"
              f"  (vs D_pred = {D_pred*1e6:.2f} um,  factor = {D_needed/D_pred:.2f}x)")

    print()

    # ── 7. Plot ─────────────────────────────────────────────────────────────
    if args.no_plot:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    x_mm_sg   = result.x_positions * 1e3
    x_mm_seed = seed_result.x_positions * 1e3

    # --- Left panel: Q_rung distribution ---
    Q_fLs = 1e15   # m³/s → fL/s
    ax1.plot(x_mm_sg,   result.Q_rungs        * Q_fLs, color="tab:blue",   lw=1.5,
             label="stepgen (mixed-BC)")
    ax1.plot(x_mm_seed, seed_result.Q_rungs   * Q_fLs, color="tab:orange", lw=1.5,
             ls="--", label="stepgen linear (flow-ctrl)")
    ax1.set_xlabel("Position along device [mm]")
    ax1.set_ylabel("Q_rung [fL/s]")
    ax1.set_title("Rung oil-flow distribution")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # --- Right panel: frequency distribution ---
    f_per_rung_sg   = droplet_frequency(result.Q_rungs,      D_pred)
    f_per_rung_seed = droplet_frequency(seed_result.Q_rungs, D_pred)

    ax2.plot(x_mm_sg,   f_per_rung_sg,   color="tab:blue",   lw=1.5,
             label="stepgen (mixed-BC)")
    ax2.plot(x_mm_seed, f_per_rung_seed, color="tab:orange", lw=1.5,
             ls="--", label="stepgen linear (flow-ctrl)")
    if args.f_exp_hz is not None:
        ax2.axhline(args.f_exp_hz, color="red", ls=":", lw=2,
                    label=f"f_exp = {args.f_exp_hz:.2f} Hz")
    ax2.set_xlabel("Position along device [mm]")
    ax2.set_ylabel("Frequency [Hz]")
    ax2.set_title("Droplet frequency distribution")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    title = f"Po = {args.Po_mbar:.0f} mbar,  Qw = {args.Qw_mlhr:.2f} mL/hr  |  D_pred = {D_pred*1e6:.1f} um"
    if args.f_exp_hz is not None:
        title += f"  |  f_exp = {args.f_exp_hz:.2f} Hz"
    plt.suptitle(title, fontsize=11)
    plt.tight_layout()
    plt.savefig(args.plot_out, dpi=150, bbox_inches="tight")
    print(f"Plot saved → {args.plot_out}")
    plt.show()


if __name__ == "__main__":
    main()
