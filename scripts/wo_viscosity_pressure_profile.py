"""
wo_viscosity_pressure_profile.py
=================================
Pressure-distribution profiles for a 2x2 viscosity comparison:

  Dispersed phase (water):  1.00 mPa·s  vs  1.76 mPa·s (20% glycerol blend)
  Continuous phase (oil):   5.00 mPa·s  (fixed, ~5 cSt)

Fixed operating point: P_dispersed = 200 mbar, Q_continuous = 5 mL/hr

Produces two figures — one per device config — saved to --out-dir.

Usage
-----
    python scripts/wo_viscosity_pressure_profile.py
    python scripts/wo_viscosity_pressure_profile.py --out-dir results/viscosity_sweep/
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


CONFIGS = {
    "wo_v5_30": "configs/wo_v5_30.yaml",
    "wo_w11":   "configs/wo_w11.yaml",
}

# Fixed operating point
P_DISP_MBAR = 200.0
Q_CONT_MLHR = 5.0

# Oil (continuous) viscosity: 5 cSt ≈ 5 mPa·s for density ~1 g/cm³
MU_OIL = 0.005  # Pa·s

# Viscosity pairs: (label, mu_water_Pa_s)
VISC_PAIRS = [
    ("DI water  (1.00 mPa·s)",       0.001000),
    ("20% glycerol (1.76 mPa·s)",    0.001760),
]

COLORS = {
    "dispersed":  ["tab:blue",   "tab:cyan"],
    "continuous": ["tab:orange", "tab:red"],
}
LINE_STYLES = ["-", "--"]


def run_one_device(config_path: str, device_name: str, out_dir: str):
    base_cfg = load_config(config_path)
    disp_lbl, cont_lbl = base_cfg.fluids.channel_labels

    fig, ax = plt.subplots(figsize=(11, 5))

    for idx, (label, mu_w) in enumerate(VISC_PAIRS):
        new_fluids = replace(base_cfg.fluids, mu_continuous=MU_OIL, mu_dispersed=mu_w)
        cfg = replace(base_cfg, fluids=new_fluids)

        result = iterative_solve(cfg, Po_in_mbar=P_DISP_MBAR, Qw_in_mlhr=Q_CONT_MLHR)
        x_mm = result.x_positions * 1e3
        ls = LINE_STYLES[idx]

        ax.plot(x_mm, result.P_oil   * 1e-2,
                color=COLORS["dispersed"][idx],  ls=ls, lw=1.6,
                label=f"P_{disp_lbl} — {label}")
        ax.plot(x_mm, result.P_water * 1e-2,
                color=COLORS["continuous"][idx], ls=ls, lw=1.6,
                label=f"P_{cont_lbl} — {label}")

    ax.set_xlabel("Position along channel [mm]", fontsize=11)
    ax.set_ylabel("Pressure [mbar]", fontsize=11)
    ax.set_title(
        f"{device_name}  |  P_disp inlet = {P_DISP_MBAR:.0f} mbar,  "
        f"Q_cont = {Q_CONT_MLHR:.0f} mL/hr,  mu_oil = {MU_OIL*1e3:.1f} mPa·s\n"
        f"({base_cfg.fluids.phase_system}, {disp_lbl} dispersed)",
        fontsize=10,
    )
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.25)

    plt.tight_layout()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{device_name}_viscosity_pressure_profile.png")
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="W/O viscosity comparison pressure profiles")
    parser.add_argument("--out-dir", default="results/viscosity_sweep",
                        help="Output directory (default: results/viscosity_sweep)")
    args = parser.parse_args()

    for device_name, config_path in CONFIGS.items():
        print(f"\nRunning {device_name} ({config_path}) ...")
        run_one_device(config_path, device_name, args.out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
