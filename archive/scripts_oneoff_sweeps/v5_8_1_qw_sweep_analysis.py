"""
v5_8_1_qw_sweep_analysis.py
============================
Experimental analysis of V5-8-1 device: oil pressure × water-flowrate sweep.
2% SDS continuous, sunflower oil dispersed.

Research questions
------------------
1. Does Qw affect Stage 1 timing?  (expected yes — hydraulic back-pressure)
2. Does Qw affect Stage 2 timing?  (not assumed — test this directly)
3. What V_reset correctly calibrates the Stage 1 model?
4. Can Stage 2 be locked to a constant at fixed Qw?

Data
----
analysis/stage_timings.csv — SDS rows only (NaCas excluded)
  ContPhase = "SDS"  (2% SDS continuous phase)
  DispPhasePressure : oil pressure   [mbar]  200, 300, 400, 600
  ContPhaseFlow     : water flowrate [mL/hr] 5, 10, 20
  Stage1_s, Stage2_s, Stage3_s — timing measurements
  L_menpoint_um, L_men_um    — meniscus reset geometry
  Droplet_diameter_um

Model
-----
configs/v5_30.yaml (o/w: water continuous, sunflower-oil dispersed)
Stage 1 formula: t = C_visc × V_reset × R_rung / DP_rung
  V_reset_nom = exit_width^2 × exit_depth  (= 9000 µm³, 30 µm junction)
  V_reset_obs = L_menpoint × exit_width × exit_depth  (from experiment)
  R_rung  = Shah–London Poiseuille resistance of rung
  DP_rung = mean(P_oil - P_water) from hydraulic solve

Figures produced (results/v5_8_1_qw_sweep/)
--------------------------------------------
  fig_01_stage1_loglog.png     Stage 1 vs Po log-log; model overlay per Qw
  fig_02_stage2.png            Stage 2 vs Po and vs Qw; key Qw-sensitivity finding
  fig_03_cvisc_calibration.png C_visc vs Po per Qw; V_reset sensitivity shown
  fig_04_summary.png           Hz vs Po per Qw + droplet diameter (geometry-controlled)
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
from scipy import stats as scipy_stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stepgen.config import load_config
from stepgen.models.generator import iterative_solve
from stepgen.models.stage_wise_v3.stage1_physics import compute_rung_resistance

CONFIG_PATH = "configs/v5_30.yaml"
DATA_PATH   = "analysis/stage_timings.csv"

QW_COLORS  = {5: "#1f77b4", 10: "#ff7f0e", 20: "#2ca02c"}
QW_MARKERS = {5: "o",       10: "s",       20: "^"}
PO_COLORS  = {200: "#1f77b4", 300: "#ff7f0e", 400: "#2ca02c", 600: "#d62728"}
PO_MARKERS = {200: "o",       300: "s",       400: "^",       600: "D"}


# =============================================================================
# Data loading
# =============================================================================

def load_and_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["ContPhase"] == "SDS"].copy()
    df = df.dropna(subset=["Stage1_s", "Stage2_s"]).copy()
    df["Stage3_s"] = df["Stage3_s"].fillna(0.0)
    df["total_s"]  = df["Stage1_s"] + df["Stage2_s"] + df["Stage3_s"]
    df["freq_hz"]  = 1.0 / df["total_s"]
    df["Po_mbar"]  = df["DispPhasePressure"].astype(float).astype(int)
    df["Qw_mlhr"]  = df["ContPhaseFlow"].astype(float).astype(int)
    return df


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["Po_mbar", "Qw_mlhr"])
    stats = g.agg(
        S1_mean  = ("Stage1_s",           "mean"),
        S1_std   = ("Stage1_s",           "std"),
        S2_mean  = ("Stage2_s",           "mean"),
        S2_std   = ("Stage2_s",           "std"),
        tot_mean = ("total_s",            "mean"),
        freq_mean= ("freq_hz",            "mean"),
        Lmp_mean = ("L_menpoint_um",      "mean"),
        Lmp_std  = ("L_menpoint_um",      "std"),
        Dd_mean  = ("Droplet_diameter_um","mean"),
        Dd_std   = ("Droplet_diameter_um","std"),
        n        = ("Stage1_s",           "count"),
    ).reset_index()
    return stats


# =============================================================================
# Model predictions
# =============================================================================

def run_model_predictions(stats: pd.DataFrame, config_path: str) -> pd.DataFrame:
    cfg = load_config(config_path)

    exit_w       = cfg.geometry.junction.exit_width
    exit_d       = cfg.geometry.junction.exit_depth
    V_reset_nom  = exit_w ** 2 * exit_d            # 9000 µm³ (30×30×10)
    R_rung       = compute_rung_resistance(cfg)
    dP_cap_Pa    = getattr(cfg.droplet_model, "dP_cap_ow_mbar", 50.0) * 100.0

    rows = []
    for _, row in stats.iterrows():
        Po = float(row["Po_mbar"])
        Qw = float(row["Qw_mlhr"])

        result   = iterative_solve(cfg, Po_in_mbar=Po, Qw_in_mlhr=Qw)
        dP_all   = result.P_oil - result.P_water
        active   = dP_all > dP_cap_Pa
        dP_mean  = float(np.mean(dP_all[active])) if active.sum() > 0 else float(np.mean(dP_all))

        t1_nom   = (V_reset_nom * R_rung / dP_mean) if dP_mean > 0 else np.nan

        # V_reset from observed L_menpoint: L_mp × exit_width × exit_depth
        Lmp_m    = float(row["Lmp_mean"]) * 1e-6
        V_reset_obs = Lmp_m * exit_w * exit_d
        t1_obs   = (V_reset_obs * R_rung / dP_mean) if dP_mean > 0 else np.nan

        rows.append({
            "Po_mbar":        int(Po),
            "Qw_mlhr":        int(Qw),
            "dP_mean_mbar":   dP_mean / 100.0,
            "V_reset_nom_m3": V_reset_nom,
            "V_reset_obs_m3": V_reset_obs,
            "t1_nom_s":       t1_nom,
            "t1_obs_s":       t1_obs,
        })

    pred   = pd.DataFrame(rows)
    merged = stats.merge(pred, on=["Po_mbar", "Qw_mlhr"])
    merged["C_visc_nom"] = merged["S1_mean"] / merged["t1_nom_s"]
    merged["C_visc_obs"] = merged["S1_mean"] / merged["t1_obs_s"]
    return merged


# =============================================================================
# Figures
# =============================================================================

def _finish(fig, path: str) -> None:
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def fig_stage1_loglog(merged: pd.DataFrame, out_dir: str) -> None:
    """
    Stage 1 vs Po on log-log axes, one line per Qw.
    Model (Poiseuille, V_reset=9000 µm³, C_visc=1) shown as dashed.
    Power-law exponents annotated per Qw.
    Key question: does Qw affect Stage 1, and does the hydraulic model capture it?
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    po_vals = np.array(sorted(merged["Po_mbar"].unique()))
    po_fit  = np.logspace(np.log10(po_vals.min()), np.log10(po_vals.max()), 80)

    # Left: experimental data + model
    ax = axes[0]
    for Qw in sorted(merged["Qw_mlhr"].unique()):
        sub = merged[merged["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")

        # Experimental
        ax.errorbar(sub["Po_mbar"], sub["S1_mean"], yerr=sub["S1_std"],
                    color=col, marker=mk, ms=7, lw=0, capsize=4, elinewidth=1.5,
                    zorder=3, label=f"Exp  Qw = {Qw} mL/hr")

        # Model prediction (V_reset nominal, C_visc=1)
        ax.plot(sub["Po_mbar"], sub["t1_nom_s"],
                color=col, ls="--", lw=1.6, alpha=0.7, zorder=2,
                label=f"Model Qw = {Qw} mL/hr")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Oil pressure Po [mbar]", fontsize=11)
    ax.set_ylabel("Stage 1 time [s]", fontsize=11)
    ax.set_title("Stage 1 vs Po — experiment and Poiseuille model\n"
                 r"Dashed = model, $C_{visc}$=1, $V_{reset}$=9000 µm³", fontsize=10)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, which="both", alpha=0.2)

    # Right: power-law exponents per Qw
    ax = axes[1]
    for Qw in sorted(merged["Qw_mlhr"].unique()):
        sub = merged[merged["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")

        log_po = np.log10(sub["Po_mbar"].values.astype(float))
        log_s1 = np.log10(sub["S1_mean"].values.astype(float))

        ax.scatter(sub["Po_mbar"], sub["S1_mean"],
                   color=col, marker=mk, s=55, zorder=3)

        if len(sub) >= 3:
            slope, intercept, r, p, _ = scipy_stats.linregress(log_po, log_s1)
            fit_y = 10 ** (intercept + slope * np.log10(po_fit))
            ax.plot(po_fit, fit_y, color=col, lw=1.8, ls="-",
                    label=f"Qw={Qw}  exp={slope:.2f}")
        else:
            ax.plot(sub["Po_mbar"], sub["S1_mean"], color=col, lw=1.6, ls="-",
                    label=f"Qw={Qw}")

    # Ideal Poiseuille reference
    ref = merged[merged["Qw_mlhr"] == 5].sort_values("Po_mbar").iloc[0]
    anchor = ref["t1_nom_s"] * (200.0 / 200.0)
    ideal_y = anchor * (200.0 / po_fit)
    ax.plot(po_fit, ideal_y, color="k", ls=":", lw=1.2, alpha=0.6, label="Ideal Po⁻¹")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Oil pressure Po [mbar]", fontsize=11)
    ax.set_ylabel("Stage 1 time [s]", fontsize=11)
    ax.set_title("Power-law fits: observed exponent vs ideal –1\n"
                 "Steeper than –1 → capillary back-pressure effect at low Po", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, which="both", alpha=0.2)

    fig.suptitle("V5-8-1  |  Stage 1 (oil refill) — hydraulic Qw effect and model validation",
                 fontsize=12, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_01_stage1_loglog.png"))


def fig_stage2(stats: pd.DataFrame, out_dir: str) -> None:
    """
    Stage 2 vs Po (per Qw) and Stage 2 vs Qw (per Po).
    Key finding: Stage 2 is NOT Qw-independent — it increases with Qw.
    Annotate per-Po mean values at Qw=5 as recommended model constants.
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    # Per-Po constants at Qw=5 (recommended model values)
    qw5 = stats[stats["Qw_mlhr"] == 5].sort_values("Po_mbar")
    po_constants = dict(zip(qw5["Po_mbar"], qw5["S2_mean"]))

    # Left: Stage 2 vs Po, coloured by Qw
    ax = axes[0]
    for Qw in sorted(stats["Qw_mlhr"].unique()):
        sub = stats[stats["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        ax.errorbar(sub["Po_mbar"], sub["S2_mean"], yerr=sub["S2_std"],
                    color=col, marker=mk, lw=1.8, capsize=4, ms=7,
                    label=f"Qw = {Qw} mL/hr")

    # Annotate Qw=5 constants
    for Po, s2 in po_constants.items():
        ax.annotate(f"{s2:.2f} s", xy=(Po, s2), xytext=(Po + 15, s2 + 0.04),
                    fontsize=7.5, color=QW_COLORS[5], ha="left")

    ax.set_xlabel("Oil pressure Po [mbar]", fontsize=11)
    ax.set_ylabel("Stage 2 time [s]", fontsize=11)
    ax.set_title("Stage 2 vs Po — Qw shifts snap-off time\n"
                 "Annotations = recommended per-Po constants at Qw=5 mL/hr", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    # Right: Stage 2 vs Qw, per Po
    ax = axes[1]
    for Po in sorted(stats["Po_mbar"].unique()):
        sub = stats[stats["Po_mbar"] == Po].sort_values("Qw_mlhr")
        if len(sub) < 2:
            continue
        col = PO_COLORS.get(Po, "gray")
        mk  = PO_MARKERS.get(Po, "o")
        ax.errorbar(sub["Qw_mlhr"], sub["S2_mean"], yerr=sub["S2_std"],
                    color=col, marker=mk, lw=1.8, capsize=4, ms=7,
                    label=f"Po = {Po} mbar")

    ax.set_xlabel("Water flowrate Qw [mL/hr]", fontsize=11)
    ax.set_ylabel("Stage 2 time [s]", fontsize=11)
    ax.set_title("Stage 2 vs Qw — effect saturates at high Qw\n"
                 "At 600 mbar: Stage 2 ≈ 0.12 s regardless of Qw", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1  |  Stage 2 (snap-off) — Qw dependence is real and pressure-dependent",
                 fontsize=12, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_02_stage2.png"))


def fig_cvisc_calibration(merged: pd.DataFrame, out_dir: str) -> None:
    """
    C_visc calibration panel.
    Left: C_visc (V_reset nominal = 9000 µm³) vs Po per Qw.
    Right: C_visc (V_reset observed from L_menpoint) vs Po per Qw.
    Shows that measured L_menpoint ≈ 19-21 µm (not 30 µm) accounts for most of the offset.
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    configs_text = [
        ("C_visc_nom", "t1_nom_s",
         r"$V_{reset}$ = 9000 µm³  (nominal 30×30×10 µm)",
         "C_visc with nominal V_reset = 9000 µm³\n"
         "Systematic offset → observed reset is shorter than 30 µm"),
        ("C_visc_obs", "t1_obs_s",
         r"$V_{reset}$ from $L_{menpoint}$ × junction",
         "C_visc with observed V_reset (from L_menpoint)\n"
         "Closer to 1.0 → L_menpoint ≈ 19–21 µm is the correct input"),
    ]

    for ax, (cvisc_col, t1_col, vreset_label, title) in zip(axes, configs_text):
        for Qw in sorted(merged["Qw_mlhr"].unique()):
            sub = merged[merged["Qw_mlhr"] == Qw].sort_values("Po_mbar")
            col = QW_COLORS.get(Qw, "gray")
            mk  = QW_MARKERS.get(Qw, "o")
            ax.plot(sub["Po_mbar"], sub[cvisc_col],
                    color=col, marker=mk, lw=1.8, ms=7,
                    label=f"Qw = {Qw} mL/hr")

        ax.axhline(1.0, color="k", ls=":", lw=1.2, alpha=0.7, label="Ideal C_visc = 1.0")

        global_mean = merged[cvisc_col].mean()
        ax.axhline(global_mean, color="k", ls="--", lw=1.2,
                   label=f"Global mean = {global_mean:.2f}")

        ax.set_xlabel("Oil pressure Po [mbar]", fontsize=11)
        ax.set_ylabel(r"$C_{visc}$ = $t_{S1,exp}$ / $t_{S1,model}$", fontsize=11)
        ax.set_title(title, fontsize=10)
        ax.annotate(vreset_label, xy=(0.03, 0.97), xycoords="axes fraction",
                    fontsize=8, va="top", color="gray",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1  |  Stage 1 calibration: V_reset choice drives C_visc offset",
                 fontsize=12, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_03_cvisc_calibration.png"))


def fig_summary(stats: pd.DataFrame, out_dir: str) -> None:
    """
    Left: generation frequency vs Po per Qw — operational summary.
    Right: droplet diameter vs Po per Qw — confirms geometry-controlled size.
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    ax = axes[0]
    for Qw in sorted(stats["Qw_mlhr"].unique()):
        sub = stats[stats["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        ax.plot(sub["Po_mbar"], sub["freq_mean"],
                color=col, marker=mk, lw=1.8, ms=7, label=f"Qw = {Qw} mL/hr")
    ax.set_xlabel("Oil pressure Po [mbar]", fontsize=11)
    ax.set_ylabel("Generation frequency [Hz]", fontsize=11)
    ax.set_title("Droplet production rate vs Po\n"
                 "Higher Qw reduces Hz by raising water back-pressure", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    ax = axes[1]
    for Qw in sorted(stats["Qw_mlhr"].unique()):
        sub = stats[stats["Qw_mlhr"] == Qw].sort_values("Po_mbar")
        col = QW_COLORS.get(Qw, "gray")
        mk  = QW_MARKERS.get(Qw, "o")
        ax.errorbar(sub["Po_mbar"], sub["Dd_mean"], yerr=sub["Dd_std"],
                    color=col, marker=mk, lw=1.8, ms=7, capsize=4,
                    label=f"Qw = {Qw} mL/hr")

    overall_dd = float(stats["Dd_mean"].mean())
    ax.axhline(overall_dd, color="k", ls="--", lw=1.2, alpha=0.6,
               label=f"Grand mean = {overall_dd:.1f} µm")
    ax.set_xlabel("Oil pressure Po [mbar]", fontsize=11)
    ax.set_ylabel("Droplet diameter [µm]", fontsize=11)
    ax.set_title("Droplet diameter vs Po — geometry-controlled\n"
                 "No significant Qw or Po dependence confirms snap-off by geometry", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1  |  Operational summary: frequency and droplet size",
                 fontsize=12, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_04_summary.png"))


# =============================================================================
# Summary reporting
# =============================================================================

def print_summary(merged: pd.DataFrame) -> None:
    print("\n" + "=" * 80)
    print("QW SWEEP — EXPERIMENTAL + MODEL SUMMARY")
    print("=" * 80)
    header = (f"{'Po':>6} {'Qw':>5} {'n':>4}  "
              f"{'S1_exp':>7} {'S1_std':>6}  "
              f"{'S2_exp':>7} {'S2_std':>6}  "
              f"{'t1_nom':>7}  {'C_nom':>6}  "
              f"{'t1_obs':>7}  {'C_obs':>6}  "
              f"{'dP_mean':>8}")
    print(header)
    print("-" * 80)
    for _, r in merged.sort_values(["Po_mbar", "Qw_mlhr"]).iterrows():
        print(f"{int(r.Po_mbar):>6} {int(r.Qw_mlhr):>5} {int(r.n):>4}  "
              f"{r.S1_mean:>7.3f} {r.S1_std:>6.3f}  "
              f"{r.S2_mean:>7.3f} {r.S2_std:>6.3f}  "
              f"{r.t1_nom_s:>7.3f}  {r.C_visc_nom:>6.3f}  "
              f"{r.t1_obs_s:>7.3f}  {r.C_visc_obs:>6.3f}  "
              f"{r.dP_mean_mbar:>8.1f}")

    print()
    print(f"C_visc (nominal V_reset=9000µm³)  : mean = {merged['C_visc_nom'].mean():.3f} ± {merged['C_visc_nom'].std():.3f}")
    print(f"C_visc (observed V_reset from Lmp): mean = {merged['C_visc_obs'].mean():.3f} ± {merged['C_visc_obs'].std():.3f}")
    print()
    print("Stage 2 mean per Qw (mL/hr):")
    for Qw in sorted(merged["Qw_mlhr"].unique()):
        s = merged[merged["Qw_mlhr"] == Qw]["S2_mean"]
        print(f"  Qw = {Qw:2d} : S2 = {s.mean():.3f} s")
    print()
    print("Stage 2 mean per Po at Qw=5 (recommended per-Po constants):")
    qw5 = merged[merged["Qw_mlhr"] == 5].sort_values("Po_mbar")
    for _, r in qw5.iterrows():
        print(f"  Po = {int(r.Po_mbar):3d} mbar : S2 = {r.S2_mean:.3f} s")
    print("=" * 80)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="results/v5_8_1_qw_sweep")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Loading data: {DATA_PATH}")
    df    = load_and_clean(DATA_PATH)
    stats = compute_stats(df)
    print(f"  {len(df)} SDS observations  |  "
          f"Po = {sorted(stats['Po_mbar'].unique())} mbar  |  "
          f"Qw = {sorted(stats['Qw_mlhr'].unique())} mL/hr")

    print("Running hydraulic model predictions ...")
    merged = run_model_predictions(stats, CONFIG_PATH)

    print_summary(merged)

    print("Generating figures ...")
    fig_stage1_loglog(merged, args.out_dir)
    fig_stage2(stats, args.out_dir)
    fig_cvisc_calibration(merged, args.out_dir)
    fig_summary(stats, args.out_dir)

    print(f"\nDone — figures saved to: {args.out_dir}")


if __name__ == "__main__":
    main()
