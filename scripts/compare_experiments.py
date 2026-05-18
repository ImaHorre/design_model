"""
compare_experiments.py — compare Stage-Wise V3 model predictions against
experimental stage timing measurements from analysis/stage_timings.csv.

Usage
-----
    python scripts/compare_experiments.py --config configs/v5_30.yaml

    # Filter to a specific device or continuous phase
    python scripts/compare_experiments.py \\
        --config configs/v5_30.yaml \\
        --device V5-8-1 \\
        --cont-phase SDS

    # Output to a specific folder (default: results/comparison/)
    python scripts/compare_experiments.py \\
        --config configs/v5_30.yaml \\
        --out results/v530_comparison/

    # Use a different data file (e.g. from a workspace)
    python scripts/compare_experiments.py \\
        --config configs/v5_30.yaml \\
        --data workspaces/my_study/data.csv

Outputs (in --out directory)
------------------------------
    fig_01_stage1_comparison.png   Model vs experimental Stage 1 time
    fig_02_stage2_comparison.png   Model vs experimental Stage 2 time
    fig_03_frequency.png           Model vs experimental device frequency
    fig_04_parity.png              Parity plots (predicted vs measured)
    summary.md                     Text summary of model accuracy metrics
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from stepgen.config import load_config, mbar_to_pa, mlhr_to_m3s
from stepgen.models.stage_wise_v3 import stage_wise_v3_solve

DEFAULT_DATA = REPO_ROOT / "analysis" / "stage_timings.csv"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data(path: str, device: str | None, cont_phase: str | None) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"Stage1_s", "Stage2_s", "DispPhasePressure", "ContPhaseFlow"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Data file missing columns: {missing}")
    df = df.dropna(subset=["Stage1_s", "Stage2_s"]).copy()
    df["Stage3_s"] = df.get("Stage3_s", pd.Series(0.0, index=df.index)).fillna(0.0)
    df["total_s"] = df["Stage1_s"] + df["Stage2_s"] + df["Stage3_s"]
    df["freq_hz"] = 1.0 / df["total_s"]
    df["Po_mbar"] = df["DispPhasePressure"].astype(float).round().astype(int)
    df["Qw_mlhr"] = df["ContPhaseFlow"].astype(float)
    if device and "DeviceID" in df.columns:
        df = df[df["DeviceID"] == device].copy()
        if df.empty:
            raise ValueError(f"No rows found for DeviceID='{device}'")
    if cont_phase and "ContPhase" in df.columns:
        df = df[df["ContPhase"] == cont_phase].copy()
        if df.empty:
            raise ValueError(f"No rows found for ContPhase='{cont_phase}'")
    return df


# ── Model evaluation ──────────────────────────────────────────────────────────

def run_model_for_conditions(
    config_path: str,
    conditions: list[tuple[float, float]],
) -> dict[tuple[float, float], dict]:
    cfg = load_config(config_path)
    results = {}
    for Po, Qw in conditions:
        try:
            result = stage_wise_v3_solve(cfg, Po_in_mbar=Po, Qw_in_mlhr=Qw)
            if result.group_results:
                g = result.group_results[0]
                t1 = g.stage1_result.t_displacement if hasattr(g.stage1_result, 't_displacement') else float('nan')
                t2 = g.stage2_result.t_growth if hasattr(g.stage2_result, 't_growth') else float('nan')
                R_crit = g.stage2_result.R_critical if hasattr(g.stage2_result, 'R_critical') else float('nan')
                freq = result.global_metrics.get("average_frequency_hz", float('nan'))
            else:
                t1 = t2 = R_crit = freq = float('nan')
            results[(Po, Qw)] = {
                "t1_model": t1,
                "t2_model": t2,
                "freq_model": freq,
                "R_critical_um": R_crit * 1e6 if not np.isnan(R_crit) else float('nan'),
                "error": None,
            }
        except Exception as exc:
            results[(Po, Qw)] = {"t1_model": float('nan'), "t2_model": float('nan'),
                                  "freq_model": float('nan'), "R_critical_um": float('nan'),
                                  "error": str(exc)}
            print(f"  [warn] model failed at Po={Po} mbar, Qw={Qw} mL/hr: {exc}")
    return results


def attach_predictions(df: pd.DataFrame, model_results: dict) -> pd.DataFrame:
    df = df.copy()
    df["t1_model"] = df.apply(lambda r: model_results.get((r["Po_mbar"], r["Qw_mlhr"]), {}).get("t1_model", float('nan')), axis=1)
    df["t2_model"] = df.apply(lambda r: model_results.get((r["Po_mbar"], r["Qw_mlhr"]), {}).get("t2_model", float('nan')), axis=1)
    df["freq_model"] = df.apply(lambda r: model_results.get((r["Po_mbar"], r["Qw_mlhr"]), {}).get("freq_model", float('nan')), axis=1)
    df["R_critical_um"] = df.apply(lambda r: model_results.get((r["Po_mbar"], r["Qw_mlhr"]), {}).get("R_critical_um", float('nan')), axis=1)
    return df


# ── Plotting ──────────────────────────────────────────────────────────────────

def _po_color_map(po_vals):
    cmap = plt.cm.viridis
    vmin, vmax = min(po_vals), max(po_vals)
    return {p: cmap((p - vmin) / max(vmax - vmin, 1)) for p in sorted(set(po_vals))}


def plot_stage1(df: pd.DataFrame, out_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    po_colors = _po_color_map(df["Po_mbar"].unique())
    qw_vals = sorted(df["Qw_mlhr"].unique())

    ax = axes[0]
    for Po, grp in df.groupby("Po_mbar"):
        qw_means = grp.groupby("Qw_mlhr")["Stage1_s"].mean()
        qw_means_m = grp.groupby("Qw_mlhr")["t1_model"].mean()
        ax.plot(qw_means.index, qw_means.values, "o-", color=po_colors[Po], label=f"Exp Po={Po}")
        ax.plot(qw_means_m.index, qw_means_m.values, "s--", color=po_colors[Po], alpha=0.7, label=f"Model Po={Po}")
    ax.set_xlabel("Qw [mL/hr]")
    ax.set_ylabel("Stage 1 time [s]")
    ax.set_title("Stage 1: experiment vs model")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, alpha=0.25)

    ax = axes[1]
    valid = df.dropna(subset=["Stage1_s", "t1_model"])
    ax.scatter(valid["Stage1_s"], valid["t1_model"], c=[po_colors[p] for p in valid["Po_mbar"]], alpha=0.6, s=20)
    lims = [min(valid["Stage1_s"].min(), valid["t1_model"].min()) * 0.9,
            max(valid["Stage1_s"].max(), valid["t1_model"].max()) * 1.1]
    ax.plot(lims, lims, "k--", lw=0.8, label="1:1")
    ax.set_xlabel("Experimental Stage 1 [s]")
    ax.set_ylabel("Model Stage 1 [s]")
    ax.set_title("Stage 1 parity")
    ax.legend()
    ax.grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_dir / "fig_01_stage1_comparison.png", dpi=150)
    plt.close(fig)


def plot_stage2(df: pd.DataFrame, out_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    po_colors = _po_color_map(df["Po_mbar"].unique())

    ax = axes[0]
    for Po, grp in df.groupby("Po_mbar"):
        qw_means = grp.groupby("Qw_mlhr")["Stage2_s"].mean()
        qw_means_m = grp.groupby("Qw_mlhr")["t2_model"].mean()
        ax.plot(qw_means.index, qw_means.values, "o-", color=po_colors[Po], label=f"Exp Po={Po}")
        ax.plot(qw_means_m.index, qw_means_m.values, "s--", color=po_colors[Po], alpha=0.7, label=f"Model Po={Po}")
    ax.set_xlabel("Qw [mL/hr]")
    ax.set_ylabel("Stage 2 time [s]")
    ax.set_title("Stage 2: experiment vs model")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, alpha=0.25)

    ax = axes[1]
    valid = df.dropna(subset=["Stage2_s", "t2_model"])
    ax.scatter(valid["Stage2_s"], valid["t2_model"], c=[po_colors[p] for p in valid["Po_mbar"]], alpha=0.6, s=20)
    lims = [min(valid["Stage2_s"].min(), valid["t2_model"].min()) * 0.9,
            max(valid["Stage2_s"].max(), valid["t2_model"].max()) * 1.1]
    ax.plot(lims, lims, "k--", lw=0.8, label="1:1")
    ax.set_xlabel("Experimental Stage 2 [s]")
    ax.set_ylabel("Model Stage 2 [s]")
    ax.set_title("Stage 2 parity")
    ax.legend()
    ax.grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_dir / "fig_02_stage2_comparison.png", dpi=150)
    plt.close(fig)


def plot_frequency(df: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    po_colors = _po_color_map(df["Po_mbar"].unique())
    for Po, grp in df.groupby("Po_mbar"):
        qw_means = grp.groupby("Qw_mlhr")["freq_hz"].mean()
        qw_means_m = grp.groupby("Qw_mlhr")["freq_model"].mean()
        ax.plot(qw_means.index, qw_means.values, "o-", color=po_colors[Po], label=f"Exp Po={Po}")
        ax.plot(qw_means_m.index, qw_means_m.values, "s--", color=po_colors[Po], alpha=0.7, label=f"Model Po={Po}")
    ax.set_xlabel("Qw [mL/hr]")
    ax.set_ylabel("Frequency [Hz]")
    ax.set_title("Device frequency: experiment vs model")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "fig_03_frequency.png", dpi=150)
    plt.close(fig)


# ── Summary ───────────────────────────────────────────────────────────────────

def _rmse(a, b):
    v = pd.Series(a).values
    p = pd.Series(b).values
    mask = ~(np.isnan(v) | np.isnan(p))
    if mask.sum() == 0:
        return float('nan')
    return float(np.sqrt(np.mean((v[mask] - p[mask])**2)))


def _ratio(a, b):
    v = pd.Series(a).values
    p = pd.Series(b).values
    mask = (~(np.isnan(v) | np.isnan(p))) & (v > 0)
    if mask.sum() == 0:
        return float('nan')
    return float(np.mean(p[mask] / v[mask]))


def write_summary(df: pd.DataFrame, config_path: str, data_path: str, out_dir: Path) -> None:
    n = len(df)
    n_cond = df.groupby(["Po_mbar", "Qw_mlhr"]).ngroups
    rmse_t1 = _rmse(df["Stage1_s"], df["t1_model"])
    rmse_t2 = _rmse(df["Stage2_s"], df["t2_model"])
    ratio_t1 = _ratio(df["Stage1_s"], df["t1_model"])
    ratio_t2 = _ratio(df["Stage2_s"], df["t2_model"])
    ratio_freq = _ratio(df["freq_hz"], df["freq_model"])

    lines = [
        "# Model vs Experiment Comparison Summary",
        "",
        f"**Config**: `{config_path}`",
        f"**Data**: `{data_path}`",
        f"**Measurements**: {n} rows, {n_cond} unique conditions",
        "",
        "## Accuracy metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Stage 1 RMSE | {rmse_t1:.3f} s |",
        f"| Stage 1 mean model/exp ratio | {ratio_t1:.2f} |",
        f"| Stage 2 RMSE | {rmse_t2:.3f} s |",
        f"| Stage 2 mean model/exp ratio | {ratio_t2:.2f} |",
        f"| Frequency mean model/exp ratio | {ratio_freq:.2f} |",
        "",
        "## Interpretation",
        "",
        "- Ratio > 1: model overpredicts; ratio < 1: model underpredicts",
        "- Stage 1 ratio > 1 → viscosity correction factor may need tuning",
        "- Stage 2 ratio >> 1 → R_critical_ratio may be too large",
        "",
        "## Conditions tested",
        "",
    ]
    for (Po, Qw), grp in df.groupby(["Po_mbar", "Qw_mlhr"]):
        t1e = grp["Stage1_s"].mean()
        t1m = grp["t1_model"].mean()
        t2e = grp["Stage2_s"].mean()
        t2m = grp["t2_model"].mean()
        lines.append(
            f"- Po={Po} mbar, Qw={Qw} mL/hr: "
            f"t1 exp={t1e:.3f}s / model={t1m:.3f}s, "
            f"t2 exp={t2e:.3f}s / model={t2m:.3f}s"
        )

    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-20:]))  # print last section to terminal


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="Device config YAML (e.g. configs/v5_30.yaml)")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Experimental data CSV (default: analysis/stage_timings.csv)")
    parser.add_argument("--device", default=None, help="Filter by DeviceID (e.g. V5-8-1)")
    parser.add_argument("--cont-phase", default=None, help="Filter by ContPhase (e.g. SDS)")
    parser.add_argument("--out", default="results/comparison", help="Output directory")
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading data: {args.data}")
    df = load_data(args.data, args.device, args.cont_phase)
    print(f"  {len(df)} rows, {df.groupby(['Po_mbar','Qw_mlhr']).ngroups} unique conditions")

    conditions = sorted(set(zip(df["Po_mbar"], df["Qw_mlhr"])))
    print(f"\nRunning model for {len(conditions)} conditions...")
    model_results = run_model_for_conditions(args.config, conditions)

    df = attach_predictions(df, model_results)

    print("\nPlotting...")
    plot_stage1(df, out_dir)
    plot_stage2(df, out_dir)
    plot_frequency(df, out_dir)
    write_summary(df, args.config, args.data, out_dir)

    print(f"\nOutputs written to: {out_dir}/")


if __name__ == "__main__":
    main()
