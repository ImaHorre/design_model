"""
ow_water_viscosity_sweep.py
===========================
Pressure-distribution profiles sweeping over water (continuous phase) viscosity
for an o/w (oil-in-water) system.

  Dispersed phase (oil):   fixed at 50 mPa·s (50 cP), inlet P = 200 mbar
  Continuous phase (water): 50, 25, 20, 5, 2, 1  mPa·s  at Q = 5 mL/hr

All viscosities plotted on the same axes.
Colour encodes water viscosity (plasma: dark = high viscosity).
Solid lines = dispersed channel pressure, dashed = continuous channel pressure.

Usage
-----
    python scripts/ow_water_viscosity_sweep.py
    python scripts/ow_water_viscosity_sweep.py --config configs/ow_w11.yaml
    python scripts/ow_water_viscosity_sweep.py --P-disp 300 --Q-cont 5 --out-dir results/viscosity_sweep/
"""

import argparse
import os
import sys
from dataclasses import replace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stepgen.config import load_config
from stepgen.models.generator import iterative_solve


# Water (continuous phase) viscosities to sweep [cP = mPa·s], highest → lowest
WATER_VISCOSITIES_CP = [50, 25, 20, 5, 2, 1]

MU_OIL_PA_S = 0.050   # 50 cP, fixed (dispersed)

DEFAULT_CONFIG      = "configs/ow_w11.yaml"
DEFAULT_P_DISP_MBAR = 200.0   # oil (dispersed) inlet pressure
DEFAULT_Q_CONT_MLHR = 5.0     # water (continuous) flow rate


def run_sweep(config_path: str, P_disp: float, Q_cont: float, out_dir: str) -> str:
    base_cfg = load_config(config_path)
    disp_lbl, cont_lbl = base_cfg.fluids.channel_labels
    device_name = os.path.splitext(os.path.basename(config_path))[0]

    # Sanity-check: config must be o/w (oil dispersed, water continuous)
    if base_cfg.fluids.phase_system != "o/w":
        raise ValueError(
            f"Expected phase_system='o/w' in {config_path}, "
            f"got '{base_cfg.fluids.phase_system}'. "
            "Use an o/w config for this script."
        )

    n = len(WATER_VISCOSITIES_CP)
    # plasma colormap: dark purple = high viscosity → yellow = low
    colors = plt.cm.plasma(np.linspace(0.85, 0.15, n))

    fig, ax = plt.subplots(figsize=(12, 5))

    for idx, mu_w_cp in enumerate(WATER_VISCOSITIES_CP):
        mu_water = mu_w_cp * 1e-3   # Pa·s
        color = colors[idx]

        new_fluids = replace(base_cfg.fluids,
                             mu_dispersed=MU_OIL_PA_S,
                             mu_continuous=mu_water)
        cfg = replace(base_cfg, fluids=new_fluids)

        result = iterative_solve(cfg, Po_in_mbar=P_disp, Qw_in_mlhr=Q_cont)
        x_mm = result.x_positions * 1e3

        # P_oil  = dispersed channel pressure (oil inlet side)
        # P_water = continuous channel pressure (water inlet side)
        ax.plot(x_mm, result.P_oil   * 1e-2,
                color=color, ls="-",  lw=1.8,
                label=f"{mu_w_cp} cP")
        ax.plot(x_mm, result.P_water * 1e-2,
                color=color, ls="--", lw=1.8)

    # --- Legend: colour patches for viscosity + style entries for channel ---
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    visc_handles = [
        Patch(facecolor=colors[i], label=f"{WATER_VISCOSITIES_CP[i]} cP")
        for i in range(n)
    ]
    style_handles = [
        Line2D([0], [0], color="k", ls="-",  lw=1.8,
               label=f"P_{disp_lbl} (dispersed ch., oil)"),
        Line2D([0], [0], color="k", ls="--", lw=1.8,
               label=f"P_{cont_lbl} (continuous ch., water)"),
    ]

    leg1 = ax.legend(handles=visc_handles, title="Water viscosity",
                     fontsize=8, loc="upper right", framealpha=0.88)
    ax.add_artist(leg1)
    ax.legend(handles=style_handles, fontsize=8, loc="center right", framealpha=0.88)

    ax.set_xlabel("Position along channel [mm]", fontsize=11)
    ax.set_ylabel("Pressure [mbar]", fontsize=11)
    ax.set_title(
        f"{device_name}  |  Water (continuous) viscosity sweep\n"
        f"P_disp inlet = {P_disp:.0f} mbar,  Q_cont = {Q_cont:.1f} mL/hr,  "
        f"oil (dispersed) = {MU_OIL_PA_S*1e3:.0f} mPa·s fixed  "
        f"({base_cfg.fluids.phase_system}, {disp_lbl} dispersed)",
        fontsize=10,
    )
    ax.grid(True, alpha=0.25)

    plt.tight_layout()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{device_name}_water_viscosity_sweep.png")
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Sweep water (continuous phase) viscosity in o/w — all lines on one graph"
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help=f"Path to YAML config (must be o/w) (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--P-disp", type=float, default=DEFAULT_P_DISP_MBAR, metavar="MBAR",
        help=f"Dispersed-phase (oil) inlet pressure [mbar] (default: {DEFAULT_P_DISP_MBAR})",
    )
    parser.add_argument(
        "--Q-cont", type=float, default=DEFAULT_Q_CONT_MLHR, metavar="MLHR",
        help=f"Continuous-phase (water) flow rate [mL/hr] (default: {DEFAULT_Q_CONT_MLHR})",
    )
    parser.add_argument(
        "--out-dir", default="results/viscosity_sweep",
        help="Output directory (default: results/viscosity_sweep)",
    )
    args = parser.parse_args()
    run_sweep(args.config, args.P_disp, args.Q_cont, args.out_dir)
    print("Done.")


if __name__ == "__main__":
    main()
