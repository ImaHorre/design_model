"""
wo_pressure_sweep.py
====================
Hydraulic pressure sweep for w/o (or any) config.

Generates one figure with one panel per dispersed-phase pressure value.
Each panel shows both P_dispersed(x) and P_continuous(x) for all
continuous-phase flow rates on the same axes.

Usage
-----
    python scripts/wo_pressure_sweep.py configs/wo_w11.yaml
    python scripts/wo_pressure_sweep.py configs/wo_w11.yaml --out-dir results/wo_w11/
    python scripts/wo_pressure_sweep.py configs/wo_w11.yaml \\
        --P-disp 100 200 400 800 \\
        --Q-cont 1 2.5 5 \\
        --out-dir results/wo_w11/
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Allow running from repo root without installing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stepgen.config import load_config
from stepgen.models.generator import iterative_solve


def run(config_path, P_disp_vals, Q_cont_vals, out_dir):
    cfg = load_config(config_path)
    disp_lbl, cont_lbl = cfg.fluids.channel_labels

    os.makedirs(out_dir, exist_ok=True)

    n_panels = len(P_disp_vals)
    fig, axes = plt.subplots(
        n_panels, 1,
        figsize=(11, 3.5 * n_panels),
        sharex=True,
    )
    if n_panels == 1:
        axes = [axes]

    ls_map = ["-", "--", ":", "-."]

    for ax, Pd in zip(axes, P_disp_vals):
        for i, Qc in enumerate(Q_cont_vals):
            result = iterative_solve(cfg, Po_in_mbar=Pd, Qw_in_mlhr=Qc)
            x_mm = result.x_positions * 1e3
            ls = ls_map[i % len(ls_map)]
            ax.plot(x_mm, result.P_oil   * 1e-2,
                    color="tab:orange", ls=ls, lw=1.4,
                    label=f"P_{disp_lbl}  Q_cont={Qc} mL/hr")
            ax.plot(x_mm, result.P_water * 1e-2,
                    color="tab:blue", ls=ls, lw=1.4,
                    label=f"P_{cont_lbl}  Q_cont={Qc} mL/hr")

        ax.set_ylabel("Pressure [mbar]")
        ax.set_title(
            f"P_{disp_lbl} inlet = {Pd} mbar  "
            f"({cfg.fluids.phase_system}, {disp_lbl} dispersed)"
        )
        ax.grid(True, alpha=0.25)

        # Legend: first panel only, deduplicated by linestyle
        if ax is axes[0]:
            from matplotlib.lines import Line2D
            handles = []
            handles.append(Line2D([0], [0], color="tab:orange", lw=1.4,
                                  label=f"P_{disp_lbl} (dispersed ch.)"))
            handles.append(Line2D([0], [0], color="tab:blue",   lw=1.4,
                                  label=f"P_{cont_lbl} (continuous ch.)"))
            for i, Qc in enumerate(Q_cont_vals):
                handles.append(Line2D([0], [0], color="gray",
                                      ls=ls_map[i % len(ls_map)], lw=1.4,
                                      label=f"Q_cont = {Qc} mL/hr"))
            ax.legend(handles=handles, fontsize=8, loc="upper right")

    axes[-1].set_xlabel("Position along channel [mm]")

    fig.suptitle(
        f"Hydraulic pressure profiles — {os.path.basename(config_path)}\n"
        f"(dP_cap = 0, pure hydraulic)",
        fontsize=11,
    )
    plt.tight_layout()

    out_path = os.path.join(out_dir, "wo_pressure_sweep.png")
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="W/O hydraulic pressure sweep plot"
    )
    parser.add_argument("config", help="Path to YAML config file")
    parser.add_argument(
        "--P-disp", nargs="+", type=float,
        default=[100, 200, 400, 800],
        metavar="MBAR",
        help="Dispersed-phase inlet pressures [mbar] (default: 100 200 400 800)",
    )
    parser.add_argument(
        "--Q-cont", nargs="+", type=float,
        default=[1.0, 2.5, 5.0],
        metavar="MLHR",
        help="Continuous-phase flow rates [mL/hr] (default: 1 2.5 5)",
    )
    parser.add_argument(
        "--out-dir", default="results/wo_sweep",
        help="Output directory (default: results/wo_sweep)",
    )
    args = parser.parse_args()
    run(args.config, args.P_disp, args.Q_cont, args.out_dir)


if __name__ == "__main__":
    main()
