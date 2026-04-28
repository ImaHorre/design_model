"""
v5_8_1_qw_sweep_analysis.py
============================
Experimental analysis of V5-8-1 device: oil pressure × water-flowrate sweep.

Research questions
------------------
1. Does Qw affect Stage 1 timing?  (expected yes — hydraulic back-pressure)
2. Does Qw affect Stage 2 timing?  (unknown — test this here)
3. What C_visc is needed to match Stage 1 model predictions?
4. Can Stage 2 be locked to a constant (or constant per Po)?

Data
----
analysis/stage_timings.csv — SDS rows only (NaCas excluded)
  DispPhasePressure : oil pressure   [mbar]  200, 300, 400, 600
  ContPhaseFlow     : water flowrate [mL/hr] 5, 10, 20
  Stage1_s, Stage2_s, Stage3_s — timing measurements
  L_menpoint_um, L_men_um    — meniscus reset geometry
  Droplet_diameter_um

Model
-----
configs/v5_30.yaml (o/w: water continuous, silicone-oil dispersed)
Stage 1 formula: t = C_visc × V_reset × R_rung / DP_rung
  V_reset = exit_width² × exit_depth  (= 9000 µm³)
  R_rung  = Shah–London Poiseuille resistance of rung
  DP_rung = mean(P_oil - P_water) from hydraulic solve

Outputs (--out-dir, default results/v5_8_1_qw_sweep/)
------------------------------------------------------
  fig_01_timings_vs_Po.png     Stage 1 & 2 vs Po, coloured by Qw
  fig_02_timings_vs_Qw.png     Stage 1 & 2 vs Qw, coloured by Po
  fig_03_model_vs_exp_stage1.png  Model vs experiment, C_visc calibration
  fig_04_stage2_analysis.png   Stage 2 vs (Po, Qw) + global mean line
  fig_05_geometry.png          L_menpoint, L_men, droplet diameter
  fig_06_frequency.png         Total generation frequency

Usage
-----
    python scripts/v5_8_1_qw_sweep_analysis.py
    python scripts/v5_8_1_qw_sweep_analysis.py --out-dir results/v5_8_1_qw_sweep/
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stepgen.config import load_config
from stepgen.models.generator import iterative_solve
from stepgen.models.stage_wise_v3.stage1_physics import compute_rung_resistance

# ── Paths ─────────────────────────────────────────────────────────────────────
CONFIG_PATH = "configs/v5_30.yaml"
DATA_PATH   = "analysis/stage_timings.csv"

# ── Colour / marker schemes ───────────────────────────────────────────────────
QW_COLORS  = {5: "#1f77b4", 10: "#ff7f0e", 20: "#2ca02c"}
QW_MARKERS = {5: "o",       10: "s",       20: "^"}
PO_COLORS  = {200: "#1f77b4", 300: "#ff7f0e", 400: "#2ca02c", 600: "#d62728"}
PO_MARKERS = {200: "o",       300: "s",       400: "^",       600: "D"}


# =============================================================================
# Data loading
# =============================================================================

def load_and_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Exclude NaCas rows
    df = df[~df["ContPhase"].str.contains("NaCas", na=False)].copy()
    # Drop rows missing any stage timing
    df = df.dropna(subset=["Stage1_s", "Stage2_s"]).copy()
    df["Stage3_s"] = df["Stage3_s"].fillna(0.0)
    # Derived quantities
    df["total_s"]  = df["Stage1_s"] + df["Stage2_s"] + df["Stage3_s"]
    df["freq_hz"]  = 1.0 / df["total_s"]
    df["Po_mbar"]  = df["DispPhasePressure"].astype(float).astype(int)
    df["Qw_mlhr"]  = df["ContPhaseFlow"].astype(float).astype(int)
    return df


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["Po_mbar", "Qw_mlhr"])
    stats = g.agg(
        S1_mean  = ("Stage1_s",          "mean"),
        S1_std   = ("Stage1_s",          "std"),
        S2_mean  = ("Stage2_s",          "mean"),
        S2_std   = ("Stage2_s",          "std"),
        S3_mean  = ("Stage3_s",          "mean"),
        tot_mean = ("total_s",           "mean"),
        tot_std  = ("total_s",           "std"),
        freq_mean= ("freq_hz",           "mean"),
        Lmp_mean = ("L_menpoint_um",     "mean"),
        Lmp_std  = ("L_menpoint_um",     "std"),
        Lm_mean  = ("L_men_um",          "mean"),
        Lm_std   = ("L_men_um",          "std"),
        Dd_mean  = ("Droplet_diameter_um","mean"),
        Dd_std   = ("Droplet_diameter_um","std"),
        n        = ("Stage1_s",          "count"),
    ).reset_index()
    return stats


# =============================================================================
# Model predictions (Stage 1 only; Stage 2 treated as empirical constant)
# =============================================================================

def run_model_predictions(stats: pd.DataFrame, config_path: str) -> pd.DataFrame:
    """
    For each (Po, Qw) condition, run the hydraulic solver and compute:
      - mean DP_rung across active rungs
      - predicted Stage 1 time (C_visc = 1.0 baseline)
      - observed C_visc = t1_exp / t1_pred
    """
    cfg = load_config(config_path)

    exit_w  = cfg.geometry.junction.exit_width   # 30 µm
    exit_d  = cfg.geometry.junction.exit_depth   # 10 µm
    V_reset = exit_w ** 2 * exit_d               # 9000 µm³ = 9 × 10⁻¹² m³
    R_rung  = compute_rung_resistance(cfg)        # Pa·s/m³

    dP_cap_Pa = getattr(cfg.droplet_model, "dP_cap_ow_mbar", 50.0) * 100.0

    rows = []
    for _, row in stats.iterrows():
        Po = float(row["Po_mbar"])
        Qw = float(row["Qw_mlhr"])

        result   = iterative_solve(cfg, Po_in_mbar=Po, Qw_in_mlhr=Qw)
        dP_all   = result.P_oil - result.P_water
        active   = dP_all > dP_cap_Pa
        dP_mean  = float(np.mean(dP_all[active])) if active.sum() > 0 else float(np.mean(dP_all))

        t1_pred  = (V_reset * R_rung / dP_mean) if dP_mean > 0 else np.nan

        rows.append({
            "Po_mbar":        int(Po),
            "Qw_mlhr":        int(Qw),
            "dP_mean_mbar":   dP_mean / 100.0,
            "n_active_rungs": int(active.sum()),
            "V_reset_m3":     V_reset,
            "R_rung_Pa_s_m3": R_rung,
            "t1_pred_s":      t1_pred,
        })

    pred = pd.DataFrame(rows)
    merged = stats.merge(pred, on=["Po_mbar", "Qw_mlhr"])
    merged["C_visc"] = merged["S1_mean"] / merged["t1_pred_s"]
    return merged


# =============================================================================
# Figures
# =============================================================================

def _finish(fig, path: str) -> None:
    plt.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_timings_vs_Po(stats: pd.DataFrame, out_dir: str) -> None:
    """Stage 1 and Stage 2 vs oil pressure, one line per Qw."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    for Qw in sorted(stats["Qw_mlhr"].unique()):
        sub = stats[stats["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        lbl = f"Qw = {Qw} mL/hr  (n≈{int(sub['n'].mean())})"

        axes[0].errorbar(sub["Po_mbar"], sub["S1_mean"], yerr=sub["S1_std"],
                         color=col, marker=mk, lw=1.8, capsize=4, label=lbl)
        axes[1].errorbar(sub["Po_mbar"], sub["S2_mean"], yerr=sub["S2_std"],
                         color=col, marker=mk, lw=1.8, capsize=4, label=lbl)

    for ax, title, ylabel in zip(
        axes,
        ["Stage 1 (oil refill)", "Stage 2 (snap-off)"],
        ["Stage 1 time [s]",     "Stage 2 time [s]"],
    ):
        ax.set_xlabel("Oil pressure Po [mbar]")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1 — Stage timings vs oil pressure (error = 1 SD, coloured by Qw)",
                 fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_01_timings_vs_Po.png"))


def fig_timings_vs_Qw(stats: pd.DataFrame, out_dir: str) -> None:
    """Stage 1 and Stage 2 vs water flowrate, one line per Po."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    for Po in sorted(stats["Po_mbar"].unique()):
        sub = stats[stats["Po_mbar"] == Po].sort_values("Qw_mlhr")
        if len(sub) < 2:
            continue
        col = PO_COLORS.get(Po, "gray")
        mk  = PO_MARKERS.get(Po, "o")
        lbl = f"Po = {Po} mbar"

        axes[0].errorbar(sub["Qw_mlhr"], sub["S1_mean"], yerr=sub["S1_std"],
                         color=col, marker=mk, lw=1.8, capsize=4, label=lbl)
        axes[1].errorbar(sub["Qw_mlhr"], sub["S2_mean"], yerr=sub["S2_std"],
                         color=col, marker=mk, lw=1.8, capsize=4, label=lbl)

    for ax, title, ylabel in zip(
        axes,
        ["Stage 1 (oil refill)", "Stage 2 (snap-off)"],
        ["Stage 1 time [s]",     "Stage 2 time [s]"],
    ):
        ax.set_xlabel("Water flowrate Qw [mL/hr]")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1 — Stage timings vs water flowrate (error = 1 SD, coloured by Po)",
                 fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_02_timings_vs_Qw.png"))


def fig_model_vs_exp_stage1(merged: pd.DataFrame, out_dir: str) -> None:
    """Model vs experimental Stage 1, plus C_visc calibration panel."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # ── Left: exp (markers + error) and model (dashed line) vs Po ─────────────
    ax = axes[0]
    for Qw in sorted(merged["Qw_mlhr"].unique()):
        sub = merged[merged["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        ax.errorbar(sub["Po_mbar"], sub["S1_mean"], yerr=sub["S1_std"],
                    color=col, marker=mk, lw=0, capsize=3, elinewidth=1.2,
                    label=f"Exp  Qw={Qw}")
        ax.plot(sub["Po_mbar"], sub["t1_pred_s"],
                color=col, ls="--", lw=1.6,
                label=f"Model Qw={Qw}")
    ax.set_xlabel("Po [mbar]")
    ax.set_ylabel("Stage 1 time [s]")
    ax.set_title("Stage 1: experiment vs Poiseuille model (C_visc = 1.0)")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.25)

    # ── Right: C_visc = t_exp / t_pred vs Po ──────────────────────────────────
    ax = axes[1]
    all_cvisc = merged["C_visc"].dropna()
    c_global = float(all_cvisc.mean())
    c_std    = float(all_cvisc.std())

    for Qw in sorted(merged["Qw_mlhr"].unique()):
        sub = merged[merged["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        ax.plot(sub["Po_mbar"], sub["C_visc"],
                color=col, marker=mk, lw=1.8,
                label=f"Qw = {Qw} mL/hr")

    ax.axhline(1.0, color="k", ls=":", lw=1.0, alpha=0.5, label="C_visc = 1.0 (ideal)")
    ax.axhline(c_global, color="k", ls="-", lw=1.5,
               label=f"Global mean = {c_global:.2f} ± {c_std:.2f}")
    ax.fill_between(sorted(merged["Po_mbar"].unique()),
                    c_global - c_std, c_global + c_std,
                    color="k", alpha=0.08)
    ax.set_xlabel("Po [mbar]")
    ax.set_ylabel(r"$C_{visc}$ = $t_{exp}$ / $t_{model}$")
    ax.set_title("Viscosity correction factor (Stage 1 calibration)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    fig.suptitle(
        f"V5-8-1 — Stage 1 model vs experiment  |  global C_visc = {c_global:.2f} ± {c_std:.2f}",
        fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_03_model_vs_exp_stage1.png"))


def fig_stage2_analysis(stats: pd.DataFrame, out_dir: str) -> float:
    """Stage 2 vs Po and Qw; returns global mean Stage 2 time."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Global mean across all SDS conditions
    s2_global = float(stats["S2_mean"].mean())

    # ── Left: Stage 2 vs Po, per Qw ──────────────────────────────────────────
    ax = axes[0]
    for Qw in sorted(stats["Qw_mlhr"].unique()):
        sub = stats[stats["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        ax.errorbar(sub["Po_mbar"], sub["S2_mean"], yerr=sub["S2_std"],
                    color=col, marker=mk, lw=1.8, capsize=4,
                    label=f"Qw = {Qw} mL/hr")
    ax.axhline(s2_global, color="k", ls="--", lw=1.2,
               label=f"Global mean = {s2_global:.3f} s")
    ax.set_xlabel("Po [mbar]")
    ax.set_ylabel("Stage 2 time [s]")
    ax.set_title("Stage 2 vs Po (coloured by Qw)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    # ── Right: Stage 2 vs Qw, per Po ─────────────────────────────────────────
    ax = axes[1]
    for Po in sorted(stats["Po_mbar"].unique()):
        sub = stats[stats["Po_mbar"] == Po].sort_values("Qw_mlhr")
        if len(sub) < 2:
            continue
        col = PO_COLORS.get(Po, "gray")
        mk  = PO_MARKERS.get(Po, "o")
        ax.errorbar(sub["Qw_mlhr"], sub["S2_mean"], yerr=sub["S2_std"],
                    color=col, marker=mk, lw=1.8, capsize=4,
                    label=f"Po = {Po} mbar")
    ax.axhline(s2_global, color="k", ls="--", lw=1.2,
               label=f"Global mean = {s2_global:.3f} s")
    ax.set_xlabel("Water flowrate Qw [mL/hr]")
    ax.set_ylabel("Stage 2 time [s]")
    ax.set_title("Stage 2 vs Qw (coloured by Po)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    fig.suptitle(
        f"V5-8-1 — Stage 2 snap-off analysis  |  global mean = {s2_global:.3f} s",
        fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_04_stage2_analysis.png"))
    return s2_global


def fig_geometry(stats: pd.DataFrame, out_dir: str) -> None:
    """L_menpoint, L_men, and droplet diameter vs Po, coloured by Qw."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    cols_info = [
        ("Lmp_mean", "Lmp_std", "L_menpoint [µm]",       "L_menpoint (top of meniscus → edge)"),
        ("Lm_mean",  "Lm_std",  "L_men [µm]",            "L_men (bottom of meniscus → edge)"),
        ("Dd_mean",  "Dd_std",  "Droplet diameter [µm]",  "Droplet diameter"),
    ]
    for ax, (mcol, scol, ylabel, title) in zip(axes, cols_info):
        for Qw in sorted(stats["Qw_mlhr"].unique()):
            sub = stats[stats["Qw_mlhr"] == Qw].sort_values("Po_mbar")
            col = QW_COLORS.get(Qw, "gray")
            mk  = QW_MARKERS.get(Qw, "o")
            ax.errorbar(sub["Po_mbar"], sub[mcol], yerr=sub[scol],
                        color=col, marker=mk, lw=1.8, capsize=4,
                        label=f"Qw = {Qw} mL/hr")
        ax.set_xlabel("Po [mbar]")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1 — Meniscus geometry and droplet size vs oil pressure", fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_05_geometry.png"))


def fig_frequency(stats: pd.DataFrame, out_dir: str) -> None:
    """Generation frequency vs Po and vs Qw."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: freq vs Po, per Qw
    ax = axes[0]
    for Qw in sorted(stats["Qw_mlhr"].unique()):
        sub = stats[stats["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        ax.plot(sub["Po_mbar"], sub["freq_mean"],
                color=col, marker=mk, lw=1.8, label=f"Qw = {Qw} mL/hr")
    ax.set_xlabel("Po [mbar]")
    ax.set_ylabel("Generation frequency [Hz]")
    ax.set_title("Frequency vs Po (per Qw)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    # Right: freq vs Qw, per Po
    ax = axes[1]
    for Po in sorted(stats["Po_mbar"].unique()):
        sub = stats[stats["Po_mbar"] == Po].sort_values("Qw_mlhr")
        if len(sub) < 2:
            continue
        col = PO_COLORS.get(Po, "gray")
        mk  = PO_MARKERS.get(Po, "o")
        ax.plot(sub["Qw_mlhr"], sub["freq_mean"],
                color=col, marker=mk, lw=1.8, label=f"Po = {Po} mbar")
    ax.set_xlabel("Water flowrate Qw [mL/hr]")
    ax.set_ylabel("Generation frequency [Hz]")
    ax.set_title("Frequency vs Qw (per Po)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1 — Droplet generation frequency = 1 / (S1 + S2 + S3)", fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_06_frequency.png"))


# =============================================================================
# Summary reporting
# =============================================================================

def print_summary(merged: pd.DataFrame, s2_global: float) -> None:
    print("\n" + "=" * 72)
    print("EXPERIMENTAL + MODEL SUMMARY")
    print("=" * 72)
    header = (f"{'Po':>6} {'Qw':>5} {'n':>4}  "
              f"{'S1_exp':>8} {'S1_std':>7}  "
              f"{'S2_exp':>8} {'S2_std':>7}  "
              f"{'t1_pred':>8}  {'C_visc':>7}")
    print(header)
    print("-" * 72)
    for _, r in merged.sort_values(["Po_mbar", "Qw_mlhr"]).iterrows():
        print(f"{int(r.Po_mbar):>6} {int(r.Qw_mlhr):>5} {int(r.n):>4}  "
              f"{r.S1_mean:>8.3f} {r.S1_std:>7.3f}  "
              f"{r.S2_mean:>8.3f} {r.S2_std:>7.3f}  "
              f"{r.t1_pred_s:>8.3f}  {r.C_visc:>7.3f}")

    print()
    c_mean = float(merged["C_visc"].mean())
    c_std  = float(merged["C_visc"].std())
    print(f"C_visc  global mean ± SD : {c_mean:.3f} ± {c_std:.3f}")
    print(f"Stage 2 global mean      : {s2_global:.3f} s")
    print(f"  (use as constant for current fluid/device conditions)")

    # Check for Qw dependence of Stage 2
    print()
    print("Stage 2 mean per Qw:")
    qw_vals = sorted(merged["Qw_mlhr"].unique())
    for Qw in qw_vals:
        sub = merged[merged["Qw_mlhr"] == Qw]
        print(f"  Qw = {Qw:2d} mL/hr : S2 = {sub['S2_mean'].mean():.3f} s")
    print()
    print("Stage 2 mean per Po:")
    for Po in sorted(merged["Po_mbar"].unique()):
        sub = merged[merged["Po_mbar"] == Po]
        print(f"  Po = {Po:3d} mbar  : S2 = {sub['S2_mean'].mean():.3f} s")
    print("=" * 72)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="V5-8-1 Qw sweep analysis")
    parser.add_argument("--out-dir", default="results/v5_8_1_qw_sweep")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Loading data from: {DATA_PATH}")
    df    = load_and_clean(DATA_PATH)
    stats = compute_stats(df)

    print(f"  {len(df)} observations after filtering NaCas / NaN rows")
    print(f"  Conditions: {sorted(stats['Po_mbar'].unique())} mbar × "
          f"{sorted(stats['Qw_mlhr'].unique())} mL/hr")

    print("\nRunning hydraulic simulations and Stage 1 predictions ...")
    merged = run_model_predictions(stats, CONFIG_PATH)

    s2_global = float(stats["S2_mean"].mean())

    print_summary(merged, s2_global)

    print("\nGenerating figures ...")
    fig_timings_vs_Po(stats, args.out_dir)
    fig_timings_vs_Qw(stats, args.out_dir)
    fig_model_vs_exp_stage1(merged, args.out_dir)
    s2_ret = fig_stage2_analysis(stats, args.out_dir)
    fig_geometry(stats, args.out_dir)
    fig_frequency(stats, args.out_dir)

    print(f"\nAll figures saved to: {args.out_dir}")


if __name__ == "__main__":
    main()
