"""
wo_length_sweep_frac.py  —  fractional x-axis (0 -> 1)
=======================================================
Same as wo_length_sweep_abs.py but x-axis is normalised fractional position
so all three device lengths share the same axis range.
Easier to compare pressure gradient shape and channel cross-over point.

Usage
-----
    python scripts/wo_length_sweep_frac.py
    python scripts/wo_length_sweep_frac.py --out-dir results/wo_w11/
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stepgen.config import load_config, DeviceConfig
from stepgen.models.generator import iterative_solve

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_CONFIG   = "configs/wo_w11.yaml"
P_DISP_VALS   = [100, 200, 400, 800]
Q_CONT_VALS   = [1.0, 2.5, 5.0]
LENGTH_FRACS  = {"full": 1.0, "half": 0.5, "quarter": 0.25}
LENGTH_COLORS = {"full": "#2ca02c", "half": "#ff7f0e", "quarter": "#d62728"}


def _make_config(base: DeviceConfig, mcl: float) -> DeviceConfig:
    from dataclasses import replace
    new_main = replace(base.geometry.main, Mcl=mcl)
    new_geom = replace(base.geometry, main=new_main)
    return replace(base, geometry=new_geom)


def run(out_dir: str) -> None:
    base = load_config(BASE_CONFIG)
    disp_lbl, cont_lbl = base.fluids.channel_labels
    base_mcl = base.geometry.main.Mcl

    configs = {
        label: _make_config(base, base_mcl * frac)
        for label, frac in LENGTH_FRACS.items()
    }

    n_rows = len(P_DISP_VALS)
    n_cols = len(Q_CONT_VALS)
    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(4.5 * n_cols, 3.5 * n_rows),
        sharex=True, sharey=False,
    )

    for r, Pd in enumerate(P_DISP_VALS):
        for c, Qc in enumerate(Q_CONT_VALS):
            ax = axes[r][c]
            for label, cfg in configs.items():
                result = iterative_solve(cfg, Po_in_mbar=Pd, Qw_in_mlhr=Qc)
                N = len(result.Q_rungs)
                x_frac = np.linspace(0, 1, N)
                col = LENGTH_COLORS[label]
                ax.plot(x_frac, result.P_oil   * 1e-2,
                        color=col, ls="-",  lw=1.4)
                ax.plot(x_frac, result.P_water * 1e-2,
                        color=col, ls="--", lw=1.4)
            ax.grid(True, alpha=0.22)
            if r == 0:
                ax.set_title(f"Q_cont = {Qc} mL/hr", fontsize=9)
            if c == 0:
                ax.set_ylabel(f"P_disp={Pd} mbar\nPressure [mbar]", fontsize=8)
            if r == n_rows - 1:
                ax.set_xlabel("Fractional position (0=inlet, 1=outlet)", fontsize=8)

    from matplotlib.lines import Line2D
    handles = []
    for label, col in LENGTH_COLORS.items():
        mcl = base_mcl * LENGTH_FRACS[label]
        nmc = int(mcl / base.geometry.rung.pitch)
        handles.append(Line2D([0], [0], color=col, lw=1.4,
                               label=f"{label}  Mcl={mcl:.3f}m  Nmc={nmc:,}"))
    handles += [
        Line2D([0], [0], color="gray", ls="-",  lw=1.4, label=f"solid = P_{disp_lbl}"),
        Line2D([0], [0], color="gray", ls="--", lw=1.4, label=f"dashed = P_{cont_lbl}"),
    ]
    axes[0][0].legend(handles=handles, fontsize=7, loc="upper right")

    fig.suptitle(
        f"wo_w11 — pressure vs fractional position  |  full / half / quarter Mcl\n"
        f"({disp_lbl} dispersed / {cont_lbl} continuous)",
        fontsize=11,
    )
    plt.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "wo_length_sweep_frac.png")
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="results/wo_w11")
    args = parser.parse_args()
    run(args.out_dir)


if __name__ == "__main__":
    main()
