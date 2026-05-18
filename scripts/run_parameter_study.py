"""
run_parameter_study.py — sweep a single operating parameter and plot results.

Replaces the one-off wo_pressure_sweep.py, wo_length_sweep_abs.py,
v5_8_1_qw_sweep_analysis.py, etc.

Usage
-----
    # Sweep oil pressure at fixed Qw values
    python scripts/run_parameter_study.py configs/v5_30.yaml \\
        --axis Po --Po 100 200 300 400 500 --Qw 5 10 20

    # Sweep water flowrate at fixed Po values
    python scripts/run_parameter_study.py configs/v5_30.yaml \\
        --axis Qw --Qw 1 2 5 10 20 --Po 200 300 400

    # Save to a named results folder
    python scripts/run_parameter_study.py configs/v5_30.yaml \\
        --axis Po --out results/v530_po_sweep/

    # Run for a w/o config
    python scripts/run_parameter_study.py configs/wo_w11.yaml --axis Po

Output
------
    results/<out>/
        fig_01_stage1.png      Stage 1 time vs sweep axis
        fig_02_stage2.png      Stage 2 time vs sweep axis
        fig_03_frequency.png   Device frequency vs sweep axis
        fig_04_pressure.png    Pressure profiles along device
        sweep_results.csv      Raw model outputs for all conditions
        metadata.yaml          Config + parameters used
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from stepgen.config import load_config
from stepgen.models.stage_wise_v3 import stage_wise_v3_solve
from stepgen.models.generator import iterative_solve

DEFAULT_PO = [100, 200, 300, 400, 500]
DEFAULT_QW = [5.0, 10.0, 20.0]


# ── Model runner ──────────────────────────────────────────────────────────────

def run_conditions(config_path: str, po_vals: list[float], qw_vals: list[float]) -> pd.DataFrame:
    cfg = load_config(config_path)
    rows = []
    for Po in po_vals:
        for Qw in qw_vals:
            row = {"Po_mbar": Po, "Qw_mlhr": Qw}
            try:
                result = stage_wise_v3_solve(cfg, Po_in_mbar=Po, Qw_in_mlhr=Qw)
                if result.group_results:
                    g = result.group_results[0]
                    row["t1_s"] = getattr(g.stage1_result, 't_displacement', float('nan'))
                    row["t2_s"] = getattr(g.stage2_result, 't_growth', float('nan'))
                    row["R_critical_um"] = getattr(g.stage2_result, 'R_critical', float('nan')) * 1e6
                    row["diameter_um"] = row["R_critical_um"] * 2
                    row["freq_hz"] = result.global_metrics.get("average_frequency_hz", float('nan'))
                    row["cycle_s"] = row["t1_s"] + row["t2_s"]
                    row["stage1_frac"] = row["t1_s"] / row["cycle_s"] if row["cycle_s"] > 0 else float('nan')
                else:
                    for k in ["t1_s", "t2_s", "R_critical_um", "diameter_um", "freq_hz", "cycle_s", "stage1_frac"]:
                        row[k] = float('nan')
                row["error"] = None
            except Exception as exc:
                for k in ["t1_s", "t2_s", "R_critical_um", "diameter_um", "freq_hz", "cycle_s", "stage1_frac"]:
                    row[k] = float('nan')
                row["error"] = str(exc)
                print(f"  [warn] failed at Po={Po}, Qw={Qw}: {exc}")
            rows.append(row)
    return pd.DataFrame(rows)


# ── Plotting ──────────────────────────────────────────────────────────────────

def _color_map(values):
    cmap = plt.cm.viridis
    vals = sorted(set(values))
    if len(vals) == 1:
        return {vals[0]: cmap(0.5)}
    vmin, vmax = vals[0], vals[-1]
    return {v: cmap((v - vmin) / (vmax - vmin)) for v in vals}


def plot_timings(df: pd.DataFrame, axis: str, out_dir: Path) -> None:
    x_col = "Po_mbar" if axis == "Po" else "Qw_mlhr"
    group_col = "Qw_mlhr" if axis == "Po" else "Po_mbar"
    x_label = "Oil pressure [mbar]" if axis == "Po" else "Water flowrate [mL/hr]"
    group_label = "Qw [mL/hr]" if axis == "Po" else "Po [mbar]"
    colors = _color_map(df[group_col].unique())

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for val, grp in df.groupby(group_col):
        c = colors[val]
        grp = grp.sort_values(x_col)
        axes[0].plot(grp[x_col], grp["t1_s"], "o-", color=c, label=f"{group_label.split()[0]}={val}")
        axes[1].plot(grp[x_col], grp["t2_s"], "o-", color=c, label=f"{group_label.split()[0]}={val}")

    for ax, title, ylabel in zip(axes, ["Stage 1 time", "Stage 2 time"], ["t_stage1 [s]", "t_stage2 [s]"]):
        ax.set_xlabel(x_label)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_dir / "fig_01_stage_timings.png", dpi=150)
    plt.close(fig)


def plot_frequency(df: pd.DataFrame, axis: str, out_dir: Path) -> None:
    x_col = "Po_mbar" if axis == "Po" else "Qw_mlhr"
    group_col = "Qw_mlhr" if axis == "Po" else "Po_mbar"
    x_label = "Oil pressure [mbar]" if axis == "Po" else "Water flowrate [mL/hr]"
    group_label = "Qw [mL/hr]" if axis == "Po" else "Po [mbar]"
    colors = _color_map(df[group_col].unique())

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for val, grp in df.groupby(group_col):
        c = colors[val]
        grp = grp.sort_values(x_col)
        axes[0].plot(grp[x_col], grp["freq_hz"], "o-", color=c, label=f"{group_label.split()[0]}={val}")
        axes[1].plot(grp[x_col], grp["diameter_um"], "o-", color=c, label=f"{group_label.split()[0]}={val}")

    axes[0].set_xlabel(x_label); axes[0].set_ylabel("Frequency [Hz]"); axes[0].set_title("Device frequency"); axes[0].legend(fontsize=8); axes[0].grid(True, alpha=0.25)
    axes[1].set_xlabel(x_label); axes[1].set_ylabel("Droplet diameter [µm]"); axes[1].set_title("Droplet size"); axes[1].legend(fontsize=8); axes[1].grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_dir / "fig_02_frequency_size.png", dpi=150)
    plt.close(fig)


def plot_stage_fractions(df: pd.DataFrame, axis: str, out_dir: Path) -> None:
    x_col = "Po_mbar" if axis == "Po" else "Qw_mlhr"
    group_col = "Qw_mlhr" if axis == "Po" else "Po_mbar"
    x_label = "Oil pressure [mbar]" if axis == "Po" else "Water flowrate [mL/hr]"
    colors = _color_map(df[group_col].unique())

    fig, ax = plt.subplots(figsize=(7, 5))
    for val, grp in df.groupby(group_col):
        grp = grp.sort_values(x_col)
        ax.plot(grp[x_col], grp["stage1_frac"] * 100, "o-", color=colors[val], label=f"={val}")

    ax.set_xlabel(x_label)
    ax.set_ylabel("Stage 1 fraction of cycle [%]")
    ax.set_title("Stage 1 fraction vs sweep axis")
    ax.axhline(50, color="gray", lw=0.8, ls="--", label="50%")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "fig_03_stage_fractions.png", dpi=150)
    plt.close(fig)


# ── Metadata ──────────────────────────────────────────────────────────────────

def write_metadata(config_path: str, po_vals: list, qw_vals: list, out_dir: Path) -> None:
    meta = {
        "date": date.today().isoformat(),
        "model_version": "stage_wise_v3",
        "config": config_path,
        "sweep_Po_mbar": sorted(po_vals),
        "sweep_Qw_mlhr": sorted(qw_vals),
        "script": "scripts/run_parameter_study.py",
    }
    with open(out_dir / "metadata.yaml", "w") as f:
        yaml.dump(meta, f, default_flow_style=False, sort_keys=False)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="Device config YAML (e.g. configs/v5_30.yaml)")
    parser.add_argument("--axis", choices=["Po", "Qw"], default="Po", help="Primary sweep axis")
    parser.add_argument("--Po", nargs="+", type=float, default=DEFAULT_PO, metavar="MBAR", help="Oil pressure values [mbar]")
    parser.add_argument("--Qw", nargs="+", type=float, default=DEFAULT_QW, metavar="MLHR", help="Water flowrate values [mL/hr]")
    parser.add_argument("--out", default=None, help="Output directory (default: results/{config_stem}_{axis}_sweep)")
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    config_stem = Path(args.config).stem
    out_dir = Path(args.out) if args.out else Path(f"results/{config_stem}_{args.axis.lower()}_sweep")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Config:  {args.config}")
    print(f"Axis:    {args.axis}")
    print(f"Po:      {args.Po}")
    print(f"Qw:      {args.Qw}")
    print(f"Output:  {out_dir}/")
    print()

    df = run_conditions(args.config, args.Po, args.Qw)
    df.to_csv(out_dir / "sweep_results.csv", index=False)

    plot_timings(df, args.axis, out_dir)
    plot_frequency(df, args.axis, out_dir)
    plot_stage_fractions(df, args.axis, out_dir)
    write_metadata(args.config, args.Po, args.Qw, out_dir)

    print(f"Done. Outputs in: {out_dir}/")


if __name__ == "__main__":
    main()
