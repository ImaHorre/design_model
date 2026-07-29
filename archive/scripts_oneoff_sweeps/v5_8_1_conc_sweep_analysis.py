"""
v5_8_1_conc_sweep_analysis.py
==============================
SDS concentration sweep — V5-8-1 device.

Compares Stage 1 and Stage 2 timings across five SDS concentrations:
  2%, 1%, 0.5%, 0.25%, 0.125%
at matching (Po, Qw) conditions wherever available.

CMC of SDS ≈ 0.24%.  Behaviour below CMC changes qualitatively.

Interfacial tension estimates (SDS/water vs sunflower oil, literature):
  2.0%  → γ ≈  6 mN/m   (above CMC)
  1.0%  → γ ≈  6 mN/m   (above CMC)
  0.5%  → γ ≈  7 mN/m   (above CMC)
  0.25% → γ ≈ 10 mN/m   (near CMC)
  0.125%→ γ ≈ 20 mN/m   (below CMC)
Replace with measured values when available.

Figures produced (results/v5_8_1_conc_sweep/)
----------------------------------------------
  fig_01_stage1_vs_conc.png    Stage 1 vs [SDS]; model flat line; CMC marked
  fig_02_mechanism.png         V_reset and dP_eff vs [SDS]; mechanistic decomposition
  fig_03_stage2_vs_conc.png    Stage 2 vs [SDS]; γ-scaling model; Stage 3 stacked
  fig_04_summary_stacked.png   Stacked bar S1+S2+S3 across concentrations
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stepgen.config import load_config
from stepgen.models.generator import iterative_solve
from stepgen.models.stage_wise_v3.stage1_physics import compute_rung_resistance

CONFIG_PATH = "configs/v5_30.yaml"
DATA_PATH   = "analysis/stage_timings.csv"

CONC_MAP = {
    "SDS":       2.0,
    "1pcSDS":    1.0,
    "05pcSDS":   0.5,
    "025pcSDS":  0.25,
    "0125pcSDS": 0.125,
}
CONC_ORDER  = [2.0, 1.0, 0.5, 0.25, 0.125]
CONC_LABELS = {2.0: "2%", 1.0: "1%", 0.5: "0.5%", 0.25: "0.25%", 0.125: "0.125%"}
CMC_PCT = 0.24

GAMMA_APPROX = {
    2.0:   6e-3,
    1.0:   6e-3,
    0.5:   7e-3,
    0.25:  10e-3,
    0.125: 20e-3,
}
GAMMA_REF = GAMMA_APPROX[2.0]

CONC_COLORS = {
    2.0:   "#1f77b4",
    1.0:   "#ff7f0e",
    0.5:   "#2ca02c",
    0.25:  "#9467bd",
    0.125: "#d62728",
}
CONC_MARKERS = {
    2.0: "o", 1.0: "s", 0.5: "^", 0.25: "D", 0.125: "X",
}


# =============================================================================
# Data loading
# =============================================================================

def load_and_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["ContPhase"].isin(CONC_MAP.keys())].copy()
    df = df.dropna(subset=["Stage1_s", "Stage2_s"]).copy()
    df["Stage3_s"] = df["Stage3_s"].fillna(0.0)
    df["total_s"]  = df["Stage1_s"] + df["Stage2_s"] + df["Stage3_s"]
    df["Po_mbar"]  = df["DispPhasePressure"].astype(float).astype(int)
    df["Qw_mlhr"]  = df["ContPhaseFlow"].astype(float).astype(int)
    df["conc_pct"] = df["ContPhase"].map(CONC_MAP)
    df["gamma_Nm"] = df["conc_pct"].map(GAMMA_APPROX)
    return df


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["conc_pct", "Po_mbar", "Qw_mlhr"])
    stats = g.agg(
        S1_mean  = ("Stage1_s",            "mean"),
        S1_std   = ("Stage1_s",            "std"),
        S2_mean  = ("Stage2_s",            "mean"),
        S2_std   = ("Stage2_s",            "std"),
        S3_mean  = ("Stage3_s",            "mean"),
        tot_mean = ("total_s",             "mean"),
        Lmp_mean = ("L_menpoint_um",       "mean"),
        Lmp_std  = ("L_menpoint_um",       "std"),
        Dd_mean  = ("Droplet_diameter_um", "mean"),
        Dd_std   = ("Droplet_diameter_um", "std"),
        n        = ("Stage1_s",            "count"),
    ).reset_index()
    return stats


# =============================================================================
# Model predictions and mechanism decomposition
# =============================================================================

def run_model_predictions(stats: pd.DataFrame, config_path: str) -> pd.DataFrame:
    cfg = load_config(config_path)
    exit_w    = cfg.geometry.junction.exit_width
    exit_d    = cfg.geometry.junction.exit_depth
    V_reset_nom = exit_w ** 2 * exit_d       # 9000 µm³
    R_rung    = compute_rung_resistance(cfg)
    dP_cap_Pa = getattr(cfg.droplet_model, "dP_cap_ow_mbar", 50.0) * 100.0

    # Hydraulics depends only on (Po, Qw) — cache it
    hydro_cache = {}
    for _, row in stats[["Po_mbar", "Qw_mlhr"]].drop_duplicates().iterrows():
        Po, Qw = float(row["Po_mbar"]), float(row["Qw_mlhr"])
        result  = iterative_solve(cfg, Po_in_mbar=Po, Qw_in_mlhr=Qw)
        dP_all  = result.P_oil - result.P_water
        active  = dP_all > dP_cap_Pa
        dP_mean = float(np.mean(dP_all[active])) if active.sum() > 0 else float(np.mean(dP_all))
        hydro_cache[(int(Po), int(Qw))] = {
            "dP_mean_Pa":  dP_mean,
            "t1_pred_s":   (V_reset_nom * R_rung / dP_mean) if dP_mean > 0 else np.nan,
        }

    rows = []
    for _, row in stats.iterrows():
        key = (int(row["Po_mbar"]), int(row["Qw_mlhr"]))
        h   = hydro_cache[key]
        dP_mean = h["dP_mean_Pa"]
        t1_pred = h["t1_pred_s"]

        # Back-calculate effective driving pressure from experiment:
        # t1_exp = V_reset_obs × R_rung / dP_eff → dP_eff = V_reset_obs × R_rung / t1_exp
        Lmp_m       = float(row["Lmp_mean"]) * 1e-6
        V_reset_obs = Lmp_m * exit_w * exit_d
        dP_eff_Pa   = (V_reset_obs * R_rung / row["S1_mean"]) if row["S1_mean"] > 0 else np.nan

        # γ-scaled Stage 2 model (reference = 2% SDS at same Po/Qw)
        rows.append({
            "conc_pct":       row["conc_pct"],
            "Po_mbar":        int(row["Po_mbar"]),
            "Qw_mlhr":        int(row["Qw_mlhr"]),
            "dP_mean_mbar":   dP_mean / 100.0,
            "t1_pred_s":      t1_pred,
            "V_reset_nom_pL": V_reset_nom * 1e15,
            "V_reset_obs_pL": V_reset_obs * 1e15,
            "dP_eff_mbar":    dP_eff_Pa / 100.0,
        })

    pred   = pd.DataFrame(rows)
    merged = stats.merge(pred, on=["conc_pct", "Po_mbar", "Qw_mlhr"])
    merged["C_visc"] = merged["S1_mean"] / merged["t1_pred_s"]

    # γ-scaled Stage 2 prediction anchored to 2% SDS reference
    ref_s2 = (merged[merged["conc_pct"] == 2.0]
               .set_index(["Po_mbar", "Qw_mlhr"])["S2_mean"])

    def _s2_model(row):
        key = (int(row["Po_mbar"]), int(row["Qw_mlhr"]))
        if key not in ref_s2.index:
            return np.nan
        return ref_s2[key] * (GAMMA_APPROX[row["conc_pct"]] / GAMMA_REF)

    merged["S2_model"] = merged.apply(_s2_model, axis=1)
    return merged


# =============================================================================
# Axis helpers
# =============================================================================

def _conc_xaxis(ax, conc_vals, invert: bool = True) -> None:
    ax.set_xscale("log")
    ticks = [c for c in CONC_ORDER if c in conc_vals]
    ax.set_xticks(ticks)
    ax.set_xticklabels([CONC_LABELS[c] for c in ticks], fontsize=9)
    ax.xaxis.set_minor_locator(ticker.NullLocator())
    ax.axvline(CMC_PCT, color="gray", ls=":", lw=1.2, alpha=0.7, label="CMC ≈ 0.24%")
    if invert:
        ax.invert_xaxis()


def _finish(fig, path: str) -> None:
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# =============================================================================
# Figures
# =============================================================================

def fig_stage1_vs_conc(merged: pd.DataFrame, out_dir: str) -> None:
    """
    Stage 1 vs [SDS] at Po=200/Qw=5 (full 5-concentration sweep) and Po=400/Qw=5.
    Model (Poiseuille, no concentration dependence) shown as flat dashed line.
    Key finding: Stage 1 increases monotonically as [SDS] falls — the model is flat,
    so this concentration effect must come from changing V_reset or dP_eff (see fig_02).
    """
    plot_conditions = [(200, 5), (400, 5)]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=False)

    for ax, (Po, Qw) in zip(axes, plot_conditions):
        sub = (merged[(merged["Po_mbar"] == Po) & (merged["Qw_mlhr"] == Qw)]
               .sort_values("conc_pct"))
        conc_vals = list(sub["conc_pct"])

        ax.errorbar(sub["conc_pct"], sub["S1_mean"], yerr=sub["S1_std"],
                    color="steelblue", marker="o", lw=1.8, ms=7, capsize=5,
                    label="Exp Stage 1", zorder=3)

        t1_pred = sub["t1_pred_s"].iloc[0]
        ax.axhline(t1_pred, color="steelblue", ls="--", lw=1.5, alpha=0.7,
                   label=f"Model (C_visc=1.0) = {t1_pred:.3f} s")

        _conc_xaxis(ax, conc_vals)
        ax.set_xlabel("[SDS] %  (decreasing →)", fontsize=11)
        ax.set_ylabel("Stage 1 time [s]", fontsize=11)
        ax.set_title(f"Po = {Po} mbar, Qw = {Qw} mL/hr\n"
                     f"Model predicts flat; experiment rises 1.9× from 2%→0.25%", fontsize=10)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.25)

        # Annotate values
        for _, r in sub.iterrows():
            ax.annotate(f"{r.S1_mean:.2f}", xy=(r.conc_pct, r.S1_mean),
                        xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=7.5, color="steelblue")

    fig.suptitle("V5-8-1  |  Stage 1 vs [SDS] — unexpected concentration dependence\n"
                 "Poiseuille model predicts no [SDS] effect; experiment shows clear rise below CMC",
                 fontsize=11, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_01_stage1_vs_conc.png"))


def fig_mechanism(merged: pd.DataFrame, out_dir: str) -> None:
    """
    Mechanistic decomposition at Po=200, Qw=5 (above CMC only).
    Left:  V_reset vs [SDS] — small +7% increase as [SDS] falls.
    Right: dP_eff vs [SDS] — larger -20% drop.
    Together these fully account for the observed Stage 1 lengthening.
    The falling dP_eff is the dominant mechanism (reduced capillary driving force as γ·cosθ drops).
    """
    sub = (merged[(merged["Po_mbar"] == 200) & (merged["Qw_mlhr"] == 5)]
           .sort_values("conc_pct"))
    # Exclude 0.125% from mechanism decomposition (different regime)
    sub_fit = sub[sub["conc_pct"] >= 0.25].copy()
    conc_vals = list(sub_fit["conc_pct"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))

    # Left: V_reset
    ax = axes[0]
    ax.errorbar(sub_fit["conc_pct"], sub_fit["V_reset_obs_pL"],
                color="#2ca02c", marker="s", lw=1.8, ms=7, capsize=4,
                label="V_reset from L_menpoint")
    ref_vreset = sub_fit[sub_fit["conc_pct"] == 2.0]["V_reset_obs_pL"].values[0]
    ax.axhline(ref_vreset, color="#2ca02c", ls="--", lw=1.2, alpha=0.6,
               label=f"2% reference = {ref_vreset:.1f} pL")
    ax.axhline(sub_fit["V_reset_nom_pL"].iloc[0], color="gray", ls=":", lw=1.2,
               label="Nominal (30×30×10 µm) = 9.0 pL")

    _conc_xaxis(ax, conc_vals)
    ax.set_xlabel("[SDS] %  (decreasing →)", fontsize=11)
    ax.set_ylabel("V_reset [pL]", fontsize=11)
    ax.set_title("V_reset vs [SDS]\nSmall increase (+7–9%) across above-CMC range", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    # Annotate ratios
    for _, r in sub_fit.iterrows():
        ratio = r.V_reset_obs_pL / ref_vreset
        ax.annotate(f"{ratio:.2f}×", xy=(r.conc_pct, r.V_reset_obs_pL),
                    xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=7.5, color="#2ca02c")

    # Right: dP_eff
    ax = axes[1]
    ax.errorbar(sub_fit["conc_pct"], sub_fit["dP_eff_mbar"],
                color="#d62728", marker="D", lw=1.8, ms=7, capsize=4,
                label="dP_eff (back-calc.)")
    ref_dpeff = sub_fit[sub_fit["conc_pct"] == 2.0]["dP_eff_mbar"].values[0]
    ax.axhline(ref_dpeff, color="#d62728", ls="--", lw=1.2, alpha=0.6,
               label=f"2% reference = {ref_dpeff:.0f} mbar")
    ax.axhline(sub_fit["dP_mean_mbar"].iloc[0], color="gray", ls=":", lw=1.2,
               label=f"Hydraulic DP (no cap.) = {sub_fit['dP_mean_mbar'].iloc[0]:.0f} mbar")

    _conc_xaxis(ax, conc_vals)
    ax.set_xlabel("[SDS] %  (decreasing →)", fontsize=11)
    ax.set_ylabel("Effective driving pressure dP_eff [mbar]", fontsize=11)
    ax.set_title("dP_eff vs [SDS]\nDominant effect: −20% drop from 2%→0.25%\n"
                 "Mechanism: γ·cosθ capillary driving force weakens as [SDS] falls", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    for _, r in sub_fit.iterrows():
        ratio = r.dP_eff_mbar / ref_dpeff
        ax.annotate(f"{ratio:.2f}×", xy=(r.conc_pct, r.dP_eff_mbar),
                    xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=7.5, color="#d62728")

    fig.suptitle("V5-8-1  |  Stage 1 mechanism: why does [SDS] affect S1?\n"
                 "V_reset rises slightly (+7%); dP_eff falls sharply (−20%) — dP_eff is the dominant term",
                 fontsize=11, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_02_mechanism.png"))


def fig_stage2_vs_conc(merged: pd.DataFrame, out_dir: str) -> None:
    """
    Stage 2 vs [SDS] at Po=200/Qw=5.
    Shows experimental data and γ-scaling model prediction.
    Above CMC: Stage 2 flat and γ-model over-predicts.
    Below CMC (0.125%): Stage 2 rises as expected but less than γ-scaling predicts.
    Stage 3 annotated separately to show regime change at 0.125%.
    """
    sub = (merged[(merged["Po_mbar"] == 200) & (merged["Qw_mlhr"] == 5)]
           .sort_values("conc_pct"))
    conc_vals = list(sub["conc_pct"])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    # Left: Stage 2 vs conc
    ax = axes[0]
    ax.errorbar(sub["conc_pct"], sub["S2_mean"], yerr=sub["S2_std"],
                color="tomato", marker="o", lw=1.8, ms=7, capsize=5,
                label="Exp Stage 2", zorder=3)

    model_sub = sub.dropna(subset=["S2_model"])
    ax.plot(model_sub["conc_pct"], model_sub["S2_model"],
            color="tomato", ls="--", lw=1.5, marker="x", ms=8,
            label="γ-scaling: τ ∝ γ(c)/γ(2%)")

    _conc_xaxis(ax, conc_vals)
    ax.set_xlabel("[SDS] %  (decreasing →)", fontsize=11)
    ax.set_ylabel("Stage 2 time [s]", fontsize=11)
    ax.set_title("Stage 2 vs [SDS]  (Po=200, Qw=5)\n"
                 "Above CMC: flat (capillary force stable); below CMC: rises (γ increases)", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    # Annotate experimental vs model ratios vs 2%
    ref_s2 = sub[sub["conc_pct"] == 2.0]["S2_mean"].values[0]
    for _, r in sub.iterrows():
        exp_ratio = r.S2_mean / ref_s2
        ax.annotate(f"{exp_ratio:.2f}×", xy=(r.conc_pct, r.S2_mean),
                    xytext=(0, 9), textcoords="offset points",
                    ha="center", fontsize=7, color="tomato")

    # Right: Stage 2 + Stage 3 stacked — shows regime change
    ax = axes[1]
    x    = np.arange(len(sub))
    lbls = [CONC_LABELS[c] for c in sub["conc_pct"]]

    s2_bars = ax.bar(x, sub["S2_mean"], color="tomato", alpha=0.8,
                     yerr=sub["S2_std"], capsize=5, label="Stage 2")
    s3_vals = sub["S3_mean"].fillna(0)
    if s3_vals.max() > 0.02:
        ax.bar(x, s3_vals, bottom=sub["S2_mean"].values, color="salmon", alpha=0.6,
               label="Stage 3 (tail / stalled)")

    model_vals = sub["S2_model"].values
    valid = ~np.isnan(model_vals)
    ax.plot(x[valid], model_vals[valid], color="tomato", ls="--", lw=1.5,
            marker="x", ms=8, label="γ-scaling model")

    # CMC marker
    if any(sub["conc_pct"] == 0.25):
        xi = list(sub["conc_pct"].values).index(0.25)
        ax.axvline(xi - 0.5, color="gray", ls=":", lw=1.3, alpha=0.6)
        ax.text(xi - 0.5, ax.get_ylim()[1] * 0.95, "← above CMC | below →",
                fontsize=7.5, ha="center", color="gray")

    ax.set_xticks(x)
    ax.set_xticklabels(lbls)
    ax.set_xlabel("[SDS] %  (decreasing →)", fontsize=11)
    ax.set_ylabel("Stage 2 [+ Stage 3] time [s]", fontsize=11)
    ax.set_title("Stage 2 + Stage 3 stacked  (Po=200, Qw=5)\n"
                 "At 0.125% Stage 3 dominates — different formation regime (below CMC)", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25, axis="y")

    fig.suptitle("V5-8-1  |  Stage 2 vs [SDS] — flat above CMC, rises below; γ-model over-predicts",
                 fontsize=11, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_03_stage2_vs_conc.png"))


def fig_summary_stacked(merged: pd.DataFrame, out_dir: str) -> None:
    """
    Stacked bar of S1 + S2 + S3 for all five concentrations at Po=200/Qw=5.
    Clear visual of how the cycle composition changes across the CMC boundary.
    Droplet diameter on second panel — confirms size increase below CMC.
    """
    sub = (merged[(merged["Po_mbar"] == 200) & (merged["Qw_mlhr"] == 5)]
           .sort_values("conc_pct", ascending=False))

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    x    = np.arange(len(sub))
    lbls = [CONC_LABELS[c] for c in sub["conc_pct"]]

    # Left: stacked timing
    ax = axes[0]
    b1 = ax.bar(x, sub["S1_mean"], color="steelblue", alpha=0.85, label="Stage 1 (oil refill)")
    b2 = ax.bar(x, sub["S2_mean"], bottom=sub["S1_mean"], color="tomato", alpha=0.85,
                label="Stage 2 (snap-off)")
    s3 = sub["S3_mean"].fillna(0)
    if s3.max() > 0.02:
        b3 = ax.bar(x, s3, bottom=sub["S1_mean"].values + sub["S2_mean"].values,
                    color="salmon", alpha=0.7, label="Stage 3 (tail)")

    # Annotate total cycle time
    for i, (_, r) in enumerate(sub.iterrows()):
        tot = r.S1_mean + r.S2_mean + r.S3_mean
        ax.text(i, tot + 0.05, f"{tot:.2f} s", ha="center", fontsize=8, fontweight="bold")

    # CMC boundary
    if any(sub["conc_pct"] == 0.25):
        xi = list(sub["conc_pct"].values).index(0.25)
        # between 0.25% and 0.5% (indices xi and xi-1)
        ax.axvline(xi + 0.5, color="gray", ls=":", lw=1.5, alpha=0.7)
        ax.text(xi + 0.55, ax.get_ylim()[0], "← above CMC", fontsize=7.5,
                color="gray", va="bottom")

    ax.set_xticks(x)
    ax.set_xticklabels(lbls)
    ax.set_xlabel("[SDS] %  (2% → 0.125%)", fontsize=11)
    ax.set_ylabel("Cycle time [s]", fontsize=11)
    ax.set_title("Droplet cycle breakdown vs [SDS]  (Po=200, Qw=5)\n"
                 "Stage 3 appears below CMC; total cycle more than doubles at 0.125%", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2, axis="y")

    # Right: droplet diameter
    ax = axes[1]
    ax.errorbar(sub["conc_pct"], sub["Dd_mean"], yerr=sub["Dd_std"],
                color="#9467bd", marker="o", lw=1.8, ms=7, capsize=5,
                label="Droplet diameter")
    ax.axvline(CMC_PCT, color="gray", ls=":", lw=1.2, alpha=0.7, label="CMC ≈ 0.24%")
    ax.set_xscale("log")
    ticks = list(sub["conc_pct"])
    ax.set_xticks(ticks)
    ax.set_xticklabels([CONC_LABELS[c] for c in ticks])
    ax.xaxis.set_minor_locator(ticker.NullLocator())
    ax.invert_xaxis()
    ax.set_xlabel("[SDS] %  (decreasing →)", fontsize=11)
    ax.set_ylabel("Droplet diameter [µm]", fontsize=11)
    ax.set_title("Droplet size vs [SDS]\n"
                 "Above CMC: ~25 µm (geometry-controlled)\n"
                 "Below CMC: grows to ~35 µm (regime change)", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    for _, r in sub.iterrows():
        ax.annotate(f"{r.Dd_mean:.1f}", xy=(r.conc_pct, r.Dd_mean),
                    xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=7.5, color="#9467bd")

    fig.suptitle("V5-8-1  |  Summary: full cycle and droplet size vs [SDS]  (Po=200, Qw=5)",
                 fontsize=12, fontweight="bold")
    _finish(fig, os.path.join(out_dir, "fig_04_summary_stacked.png"))


# =============================================================================
# Summary reporting
# =============================================================================

def print_summary(merged: pd.DataFrame) -> None:
    print("\n" + "=" * 85)
    print("CONCENTRATION SWEEP SUMMARY")
    print("=" * 85)
    header = (f"{'Conc%':>7} {'Po':>5} {'Qw':>4} {'n':>3}  "
              f"{'S1':>6} {'S1sd':>5}  "
              f"{'S2':>6} {'S2sd':>5}  "
              f"{'S3':>5}  "
              f"{'C_visc':>6}  "
              f"{'dP_eff':>7}  "
              f"{'Vrst_obs':>8}  "
              f"{'Dd':>6}")
    print(header)
    print("-" * 85)
    for _, r in merged.sort_values(["Po_mbar", "Qw_mlhr", "conc_pct"],
                                    ascending=[True, True, False]).iterrows():
        print(f"{r.conc_pct:>7.3f} {int(r.Po_mbar):>5} {int(r.Qw_mlhr):>4} "
              f"{int(r.n):>3}  "
              f"{r.S1_mean:>6.3f} {r.S1_std:>5.3f}  "
              f"{r.S2_mean:>6.3f} {r.S2_std:>5.3f}  "
              f"{r.S3_mean:>5.3f}  "
              f"{r.C_visc:>6.3f}  "
              f"{r.dP_eff_mbar:>7.1f}  "
              f"{r.V_reset_obs_pL:>8.2f}  "
              f"{r.Dd_mean:>6.1f}")

    # Stage 1 ratios at Po=200, Qw=5
    ref_cond = merged[(merged["Po_mbar"] == 200) & (merged["Qw_mlhr"] == 5)].sort_values(
        "conc_pct", ascending=False)
    if len(ref_cond) > 1:
        ref_s1 = ref_cond[ref_cond["conc_pct"] == 2.0]["S1_mean"].values
        if len(ref_s1) > 0:
            print(f"\nStage 1 ratios vs 2% SDS  (Po=200, Qw=5):")
            for _, r in ref_cond.iterrows():
                print(f"  {CONC_LABELS[r.conc_pct]:>6} : {r.S1_mean:.3f} s  "
                      f"({r.S1_mean/ref_s1[0]:.2f}×)  C_visc={r.C_visc:.2f}  "
                      f"dP_eff={r.dP_eff_mbar:.0f} mbar")

        ref_s2 = ref_cond[ref_cond["conc_pct"] == 2.0]["S2_mean"].values
        if len(ref_s2) > 0:
            print(f"\nStage 2 ratios vs 2% SDS  (Po=200, Qw=5):")
            for _, r in ref_cond.iterrows():
                gamma_ratio = GAMMA_APPROX[r.conc_pct] / GAMMA_REF
                print(f"  {CONC_LABELS[r.conc_pct]:>6} : {r.S2_mean:.3f} s  "
                      f"exp={r.S2_mean/ref_s2[0]:.2f}x  gamma-model={gamma_ratio:.2f}x")
    print("=" * 85)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="results/v5_8_1_conc_sweep")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Loading data: {DATA_PATH}")
    df    = load_and_clean(DATA_PATH)
    stats = compute_stats(df)
    concs = sorted(stats["conc_pct"].unique(), reverse=True)
    print(f"  {len(df)} SDS observations across: {[CONC_LABELS[c] for c in concs]}")

    print("Running hydraulic model predictions ...")
    merged = run_model_predictions(stats, CONFIG_PATH)

    print_summary(merged)

    print("Generating figures ...")
    fig_stage1_vs_conc(merged, args.out_dir)
    fig_mechanism(merged, args.out_dir)
    fig_stage2_vs_conc(merged, args.out_dir)
    fig_summary_stacked(merged, args.out_dir)

    print(f"\nDone — figures saved to: {args.out_dir}")


if __name__ == "__main__":
    main()
