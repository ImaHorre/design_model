"""
v5_8_1_conc_sweep_analysis.py
==============================
SDS concentration sweep analysis for V5-8-1 device.

Compares Stage 1 and Stage 2 timings across five SDS concentrations:
  2%, 1%, 0.5%, 0.25%, 0.125%

at matching (Po, Qw) conditions wherever available.

Research questions
------------------
1. Does SDS concentration affect Stage 1?
   (Poiseuille model predicts no direct effect — any change absorbed into C_visc
    or V_reset via contact-angle / meniscus geometry shifts.)
2. Does SDS concentration affect Stage 2?
   (Expected yes, especially below the CMC ~0.24%: higher γ → slower capillary snap-off.)
3. Can a simple γ(c) scaling predict Stage 2 across concentrations?

Concentration → γ mapping (approximate, SDS / silicone-oil system)
-------------------------------------------------------------------
CMC of SDS ≈ 0.24 % mass.  Values below are literature estimates; they should be
replaced with measured values when available.

  2.0%  → γ ≈  6 mN/m  (well above CMC, equilibrium)
  1.0%  → γ ≈  6 mN/m  (above CMC)
  0.5%  → γ ≈  7 mN/m  (above CMC)
  0.25% → γ ≈ 10 mN/m  (near / at CMC)
  0.125%→ γ ≈ 20 mN/m  (below CMC, markedly higher)

Model Stage 2 scaling (capillary hypothesis):
  τ_S2(c) / τ_S2(2%) = γ(c) / γ(2%)
  → predicts Stage 2 is ~constant above CMC, ~3× longer at 0.125%.

Data
----
analysis/stage_timings.csv — all SDS-variant rows
  ContPhase codes: SDS | 1pcSDS | 05pcSDS | 025pcSDS | 0125pcSDS

Overlap conditions (same Po, Qw across concentrations)
  Po=200, Qw=5  : 2%, 1%, 0.5%, 0.25%, 0.125%
  Po=400, Qw=5  : 2%, 1%, 0.5%
  Po=400, Qw=2  : 1%, 0.5%, 0.25%   (no 2% baseline — noted)

Outputs (--out-dir, default results/v5_8_1_conc_sweep/)
-------------------------------------------------------
  fig_01_stage1_vs_conc.png    Stage 1 vs concentration at each (Po, Qw)
  fig_02_stage2_vs_conc.png    Stage 2 vs concentration + γ-scaling model
  fig_03_cvisc_vs_conc.png     C_visc = t1_exp / t1_model vs concentration
  fig_04_geometry_vs_conc.png  L_menpoint, L_men, droplet diameter vs concentration
  fig_05_stage2_model.png      Stage 2: experiment + γ-scaled prediction overlay

Usage
-----
    python scripts/v5_8_1_conc_sweep_analysis.py
    python scripts/v5_8_1_conc_sweep_analysis.py --out-dir results/v5_8_1_conc_sweep/
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

# ── Paths ─────────────────────────────────────────────────────────────────────
CONFIG_PATH = "configs/v5_30.yaml"
DATA_PATH   = "analysis/stage_timings.csv"

# ── Concentration mapping ─────────────────────────────────────────────────────
# ContPhase label → numeric concentration [% mass]
CONC_MAP = {
    "SDS":      2.0,
    "1pcSDS":   1.0,
    "05pcSDS":  0.5,
    "025pcSDS": 0.25,
    "0125pcSDS":0.125,
}
CONC_ORDER = [2.0, 1.0, 0.5, 0.25, 0.125]   # descending for plot x-axis
CONC_LABELS = {
    2.0:   "2%",
    1.0:   "1%",
    0.5:   "0.5%",
    0.25:  "0.25%",
    0.125: "0.125%",
}

# Approximate interfacial tension [N/m] — SDS/water vs silicone oil
# CMC ≈ 0.24% mass.  Replace with measured values if available.
GAMMA_APPROX = {
    2.0:   6e-3,
    1.0:   6e-3,
    0.5:   7e-3,
    0.25:  10e-3,
    0.125: 20e-3,
}
GAMMA_REF = GAMMA_APPROX[2.0]    # reference (2% SDS)

# ── Colours / markers per concentration ──────────────────────────────────────
CONC_COLORS = {
    2.0:   "#1f77b4",
    1.0:   "#ff7f0e",
    0.5:   "#2ca02c",
    0.25:  "#9467bd",
    0.125: "#d62728",
}
CONC_MARKERS = {
    2.0:   "o",
    1.0:   "s",
    0.5:   "^",
    0.25:  "D",
    0.125: "X",
}

# Overlap conditions to plot (Po_mbar, Qw_mlhr)
OVERLAP_CONDITIONS = [(200, 5), (400, 5), (400, 2)]


# =============================================================================
# Data loading
# =============================================================================

def load_and_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    # Keep only SDS-family rows (all non-NaCas surfactant rows)
    sds_mask = df["ContPhase"].isin(CONC_MAP.keys())
    df = df[sds_mask].copy()

    # Drop rows missing stage data
    df = df.dropna(subset=["Stage1_s", "Stage2_s"]).copy()
    df["Stage3_s"] = df["Stage3_s"].fillna(0.0)

    # Derived
    df["total_s"]  = df["Stage1_s"] + df["Stage2_s"] + df["Stage3_s"]
    df["freq_hz"]  = 1.0 / df["total_s"]
    df["Po_mbar"]  = df["DispPhasePressure"].astype(float).astype(int)
    df["Qw_mlhr"]  = df["ContPhaseFlow"].astype(float).astype(int)
    df["conc_pct"] = df["ContPhase"].map(CONC_MAP)
    df["gamma_Nm"] = df["conc_pct"].map(GAMMA_APPROX)

    return df


def compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["conc_pct", "Po_mbar", "Qw_mlhr"])
    stats = g.agg(
        S1_mean  = ("Stage1_s",           "mean"),
        S1_std   = ("Stage1_s",           "std"),
        S2_mean  = ("Stage2_s",           "mean"),
        S2_std   = ("Stage2_s",           "std"),
        S3_mean  = ("Stage3_s",           "mean"),
        S3_std   = ("Stage3_s",           "std"),
        tot_mean = ("total_s",            "mean"),
        Lmp_mean = ("L_menpoint_um",      "mean"),
        Lmp_std  = ("L_menpoint_um",      "std"),
        Lm_mean  = ("L_men_um",           "mean"),
        Lm_std   = ("L_men_um",           "std"),
        Dd_mean  = ("Droplet_diameter_um","mean"),
        Dd_std   = ("Droplet_diameter_um","std"),
        n        = ("Stage1_s",           "count"),
    ).reset_index()
    return stats


# =============================================================================
# Model predictions — Stage 1 only (hydraulics unchanged by concentration)
# =============================================================================

def run_model_predictions(stats: pd.DataFrame, config_path: str) -> pd.DataFrame:
    cfg = load_config(config_path)

    exit_w  = cfg.geometry.junction.exit_width
    exit_d  = cfg.geometry.junction.exit_depth
    V_reset = exit_w ** 2 * exit_d
    R_rung  = compute_rung_resistance(cfg)
    dP_cap_Pa = getattr(cfg.droplet_model, "dP_cap_ow_mbar", 50.0) * 100.0

    # Unique (Po, Qw) conditions — run hydraulics once per condition
    unique_conditions = stats[["Po_mbar", "Qw_mlhr"]].drop_duplicates()

    hydro_cache = {}
    for _, row in unique_conditions.iterrows():
        Po = float(row["Po_mbar"])
        Qw = float(row["Qw_mlhr"])
        result  = iterative_solve(cfg, Po_in_mbar=Po, Qw_in_mlhr=Qw)
        dP_all  = result.P_oil - result.P_water
        active  = dP_all > dP_cap_Pa
        dP_mean = float(np.mean(dP_all[active])) if active.sum() > 0 else float(np.mean(dP_all))
        t1_pred = (V_reset * R_rung / dP_mean) if dP_mean > 0 else np.nan
        hydro_cache[(int(Po), int(Qw))] = {
            "dP_mean_mbar": dP_mean / 100.0,
            "t1_pred_s":    t1_pred,
        }

    # Attach predictions to stats (same for all concentrations at the same Po/Qw)
    rows_pred = []
    for _, row in stats.iterrows():
        key = (int(row["Po_mbar"]), int(row["Qw_mlhr"]))
        h = hydro_cache[key]
        rows_pred.append({
            "conc_pct":      row["conc_pct"],
            "Po_mbar":       int(row["Po_mbar"]),
            "Qw_mlhr":       int(row["Qw_mlhr"]),
            "dP_mean_mbar":  h["dP_mean_mbar"],
            "t1_pred_s":     h["t1_pred_s"],
        })

    pred = pd.DataFrame(rows_pred)
    merged = stats.merge(pred, on=["conc_pct", "Po_mbar", "Qw_mlhr"])
    merged["C_visc"] = merged["S1_mean"] / merged["t1_pred_s"]

    # Gamma-scaled Stage 2 prediction:
    # τ_S2(c) = τ_S2_ref × [γ(c) / γ_ref]
    # where τ_S2_ref is the 2% SDS Stage 2 mean at the same (Po, Qw)
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
# Figures
# =============================================================================

def _finish(fig, path: str) -> None:
    plt.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


def _conc_xaxis(ax, conc_vals):
    """Set log x-axis for concentration with clean labels."""
    ax.set_xscale("log")
    ax.set_xticks([c for c in CONC_ORDER if c in conc_vals])
    ax.set_xticklabels([CONC_LABELS[c] for c in CONC_ORDER if c in conc_vals])
    ax.xaxis.set_minor_locator(ticker.NullLocator())
    ax.axvline(0.24, color="gray", ls=":", lw=1.0, alpha=0.6, label="CMC ≈ 0.24%")


# ── Figure 1: Stage 1 vs concentration ────────────────────────────────────────
def fig_stage1_vs_conc(merged: pd.DataFrame, out_dir: str) -> None:
    """Stage 1 mean (± SD) vs SDS concentration for each overlap condition."""
    conditions = sorted(
        merged[["Po_mbar", "Qw_mlhr"]].drop_duplicates().itertuples(index=False),
        key=lambda r: (r.Po_mbar, r.Qw_mlhr)
    )
    n_cond = len(conditions)
    fig, axes = plt.subplots(1, n_cond, figsize=(4.5 * n_cond, 5), sharey=False)
    if n_cond == 1:
        axes = [axes]

    for ax, cond in zip(axes, conditions):
        sub = merged[(merged["Po_mbar"] == cond.Po_mbar) &
                     (merged["Qw_mlhr"]  == cond.Qw_mlhr)].sort_values("conc_pct")
        conc_vals = list(sub["conc_pct"])

        ax.errorbar(sub["conc_pct"], sub["S1_mean"], yerr=sub["S1_std"],
                    color="steelblue", marker="o", lw=1.8, capsize=4,
                    label="Exp Stage 1")
        # Model prediction (constant for all concentrations)
        t1_pred = sub["t1_pred_s"].iloc[0]
        ax.axhline(t1_pred, color="steelblue", ls="--", lw=1.4,
                   label=f"Model (C_visc=1.0) = {t1_pred:.3f} s")

        _conc_xaxis(ax, conc_vals)
        ax.invert_xaxis()
        ax.set_xlabel("[SDS] %")
        ax.set_ylabel("Stage 1 time [s]")
        ax.set_title(f"Po={cond.Po_mbar} mbar, Qw={cond.Qw_mlhr} mL/hr")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1 — Stage 1 vs SDS concentration  (dashed = Poiseuille model, C_visc=1.0)",
                 fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_01_stage1_vs_conc.png"))


# ── Figure 2: Stage 2 vs concentration ────────────────────────────────────────
def fig_stage2_vs_conc(merged: pd.DataFrame, out_dir: str) -> None:
    """Stage 2 mean (± SD) vs concentration. Red dashed = γ-scaling prediction."""
    conditions = sorted(
        merged[["Po_mbar", "Qw_mlhr"]].drop_duplicates().itertuples(index=False),
        key=lambda r: (r.Po_mbar, r.Qw_mlhr)
    )
    n_cond = len(conditions)
    fig, axes = plt.subplots(1, n_cond, figsize=(4.5 * n_cond, 5), sharey=False)
    if n_cond == 1:
        axes = [axes]

    for ax, cond in zip(axes, conditions):
        sub = merged[(merged["Po_mbar"] == cond.Po_mbar) &
                     (merged["Qw_mlhr"]  == cond.Qw_mlhr)].sort_values("conc_pct")
        conc_vals = list(sub["conc_pct"])

        ax.errorbar(sub["conc_pct"], sub["S2_mean"], yerr=sub["S2_std"],
                    color="tomato", marker="o", lw=1.8, capsize=4,
                    label="Exp Stage 2")
        # γ-scaling model
        model_sub = sub.dropna(subset=["S2_model"])
        if len(model_sub) > 0:
            ax.plot(model_sub["conc_pct"], model_sub["S2_model"],
                    color="tomato", ls="--", lw=1.4, marker="x", ms=7,
                    label="γ-scaling model")

        _conc_xaxis(ax, conc_vals)
        ax.invert_xaxis()
        ax.set_xlabel("[SDS] %")
        ax.set_ylabel("Stage 2 time [s]")
        ax.set_title(f"Po={cond.Po_mbar} mbar, Qw={cond.Qw_mlhr} mL/hr")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)

    fig.suptitle(
        "V5-8-1 — Stage 2 vs SDS concentration\n"
        "Dashed = γ-scaling: τ(c)/τ(2%) = γ(c)/γ(2%)  (γ values: literature estimates)",
        fontsize=10)
    _finish(fig, os.path.join(out_dir, "fig_02_stage2_vs_conc.png"))


# ── Figure 3: C_visc vs concentration ─────────────────────────────────────────
def fig_cvisc_vs_conc(merged: pd.DataFrame, out_dir: str) -> None:
    """
    C_visc = t1_exp / t1_model vs concentration.
    If concentration doesn't affect Stage 1 physics, C_visc should be flat.
    Any trend indicates a concentration-driven change in effective V_reset or
    driving pressure (e.g. contact-angle shift changing meniscus reset distance).
    """
    conditions = sorted(
        merged[["Po_mbar", "Qw_mlhr"]].drop_duplicates().itertuples(index=False),
        key=lambda r: (r.Po_mbar, r.Qw_mlhr)
    )
    n_cond = len(conditions)
    fig, axes = plt.subplots(1, n_cond, figsize=(4.5 * n_cond, 5), sharey=True)
    if n_cond == 1:
        axes = [axes]

    for ax, cond in zip(axes, conditions):
        sub = merged[(merged["Po_mbar"] == cond.Po_mbar) &
                     (merged["Qw_mlhr"]  == cond.Qw_mlhr)].sort_values("conc_pct")
        conc_vals = list(sub["conc_pct"])

        ax.plot(sub["conc_pct"], sub["C_visc"],
                color="darkorange", marker="s", lw=1.8,
                label="C_visc")
        ax.axhline(1.0, color="k", ls=":", lw=1.0, alpha=0.5)
        ax.axhline(0.74, color="k", ls="--", lw=1.0, alpha=0.5,
                   label="2% SDS global mean = 0.74")

        _conc_xaxis(ax, conc_vals)
        ax.invert_xaxis()
        ax.set_xlabel("[SDS] %")
        ax.set_ylabel(r"$C_{visc}$ = $t_{S1,exp}$ / $t_{S1,model}$")
        ax.set_title(f"Po={cond.Po_mbar} mbar, Qw={cond.Qw_mlhr} mL/hr")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)

    fig.suptitle(
        "V5-8-1 — Stage 1 viscosity correction factor vs concentration\n"
        "Flat C_visc → concentration does not affect Stage 1 physics",
        fontsize=10)
    _finish(fig, os.path.join(out_dir, "fig_03_cvisc_vs_conc.png"))


# ── Figure 4: Geometry vs concentration ───────────────────────────────────────
def fig_geometry_vs_conc(merged: pd.DataFrame, out_dir: str) -> None:
    """L_menpoint, L_men, droplet diameter vs concentration — at each (Po, Qw)."""
    cols_info = [
        ("Lmp_mean", "Lmp_std", "L_menpoint [µm]",      "L_menpoint (reset distance)"),
        ("Lm_mean",  "Lm_std",  "L_men [µm]",           "L_men (full meniscus span)"),
        ("Dd_mean",  "Dd_std",  "Droplet diameter [µm]", "Droplet diameter"),
    ]
    # Use Po=200/Qw=5 and Po=400/Qw=5 as the two representative conditions
    plot_conditions = [(200, 5), (400, 5)]

    fig, axes = plt.subplots(len(plot_conditions), 3,
                              figsize=(14, 4.5 * len(plot_conditions)),
                              sharey="col")

    for r, cond in enumerate(plot_conditions):
        sub = merged[(merged["Po_mbar"] == cond[0]) &
                     (merged["Qw_mlhr"]  == cond[1])].sort_values("conc_pct")
        conc_vals = list(sub["conc_pct"])
        for c, (mcol, scol, ylabel, title) in enumerate(cols_info):
            ax = axes[r][c]
            ax.errorbar(sub["conc_pct"], sub[mcol], yerr=sub[scol],
                        color=CONC_COLORS.get(2.0, "steelblue"),
                        marker="o", lw=1.8, capsize=4)
            _conc_xaxis(ax, conc_vals)
            ax.invert_xaxis()
            ax.set_xlabel("[SDS] %")
            ax.set_ylabel(ylabel)
            ax.set_title(f"{title}\nPo={cond[0]}, Qw={cond[1]}")
            ax.grid(True, alpha=0.25)

    fig.suptitle("V5-8-1 — Meniscus geometry and droplet size vs SDS concentration",
                 fontsize=11)
    _finish(fig, os.path.join(out_dir, "fig_04_geometry_vs_conc.png"))


# ── Figure 5: Side-by-side Stage 1 and Stage 2 summary ───────────────────────
def fig_summary(merged: pd.DataFrame, out_dir: str) -> None:
    """
    Two-panel summary at (Po=200, Qw=5) — all five concentrations.
    Left: Stage 1 experiment vs flat model prediction.
    Right: Stage 2 experiment vs γ-scaling model.
    Includes Stage 3 as stacked bar for the 0.125% case to show the
    qualitative regime change below CMC.
    """
    sub = (merged[(merged["Po_mbar"] == 200) & (merged["Qw_mlhr"] == 5)]
           .sort_values("conc_pct", ascending=False))

    conc_labels = [CONC_LABELS[c] for c in sub["conc_pct"]]
    x = np.arange(len(sub))

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # ── Left: Stage 1 ─────────────────────────────────────────────────────────
    ax = axes[0]
    bars = ax.bar(x, sub["S1_mean"], color="steelblue", alpha=0.75,
                  yerr=sub["S1_std"], capsize=5, label="Stage 1 exp")
    t1_pred = sub["t1_pred_s"].iloc[0]
    ax.axhline(t1_pred, color="steelblue", ls="--", lw=1.5,
               label=f"Model (C_visc=1.0) = {t1_pred:.3f} s")
    ax.set_xticks(x)
    ax.set_xticklabels(conc_labels)
    ax.set_xlabel("[SDS] %  (decreasing →)")
    ax.set_ylabel("Stage 1 time [s]")
    ax.set_title("Stage 1 — Po=200 mbar, Qw=5 mL/hr")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25, axis="y")
    ax.axvline(x[sub["conc_pct"].values == 0.25][0] - 0.5 if any(sub["conc_pct"] == 0.25) else -1,
               color="gray", ls=":", alpha=0.5)

    # ── Right: Stage 2 + Stage 3 (stacked) ────────────────────────────────────
    ax = axes[1]
    bars_s2 = ax.bar(x, sub["S2_mean"], color="tomato", alpha=0.75,
                     yerr=sub["S2_std"], capsize=5, label="Stage 2 exp")
    # Stage 3 stacked on top
    s3_vals = sub["S3_mean"].fillna(0)
    if s3_vals.max() > 0.05:
        ax.bar(x, s3_vals, bottom=sub["S2_mean"], color="salmon", alpha=0.5,
               label="Stage 3 exp (stacked)")
    # γ-scaling model
    model_vals = sub["S2_model"]
    valid = ~model_vals.isna()
    ax.plot(x[valid.values], model_vals[valid].values,
            color="tomato", ls="--", lw=1.5, marker="x", ms=8,
            label="γ-scaling model")
    ax.set_xticks(x)
    ax.set_xticklabels(conc_labels)
    ax.set_xlabel("[SDS] %  (decreasing →)")
    ax.set_ylabel("Stage 2 [+Stage 3] time [s]")
    ax.set_title("Stage 2 — Po=200 mbar, Qw=5 mL/hr")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25, axis="y")

    # Annotate CMC
    for ax in axes:
        if any(sub["conc_pct"] == 0.25):
            xi = list(sub["conc_pct"].values).index(0.25)
            ax.axvline(xi - 0.5, color="gray", ls=":", lw=1.2, alpha=0.5)
        ax.text(0.02, 0.97, "← above CMC | below CMC →", transform=ax.transAxes,
                fontsize=7, va="top", color="gray")

    fig.suptitle(
        "V5-8-1 — Stage timings vs [SDS]  (Po=200 mbar, Qw=5 mL/hr)\n"
        "CMC ≈ 0.24%; behaviour changes markedly at 0.125% (below CMC)",
        fontsize=10)
    _finish(fig, os.path.join(out_dir, "fig_05_summary_200_5.png"))


# =============================================================================
# Summary reporting
# =============================================================================

def print_summary(merged: pd.DataFrame) -> None:
    print("\n" + "=" * 82)
    print("CONCENTRATION SWEEP SUMMARY")
    print("=" * 82)
    header = (f"{'Conc%':>7} {'Po':>5} {'Qw':>4} {'n':>3}  "
              f"{'S1_exp':>7} {'S1_std':>6}  "
              f"{'S2_exp':>7} {'S2_std':>6}  "
              f"{'S3_mean':>7}  "
              f"{'t1_pred':>7}  {'C_visc':>6}  "
              f"{'S2_model':>8}  {'Dd_mean':>7}")
    print(header)
    print("-" * 82)
    for _, r in merged.sort_values(["Po_mbar", "Qw_mlhr", "conc_pct"],
                                    ascending=[True, True, False]).iterrows():
        s3 = r.S3_mean if not np.isnan(r.S3_mean) else 0.0
        s2m = f"{r.S2_model:.3f}" if not np.isnan(r.S2_model) else "  —  "
        print(f"{r.conc_pct:>7.3f} {int(r.Po_mbar):>5} {int(r.Qw_mlhr):>4} "
              f"{int(r.n):>3}  "
              f"{r.S1_mean:>7.3f} {r.S1_std:>6.3f}  "
              f"{r.S2_mean:>7.3f} {r.S2_std:>6.3f}  "
              f"{s3:>7.3f}  "
              f"{r.t1_pred_s:>7.3f}  {r.C_visc:>6.3f}  "
              f"{s2m:>8}  {r.Dd_mean:>7.1f}")
    print()

    # Concentration effect on Stage 1 (at Po=200, Qw=5)
    ref_cond = merged[(merged["Po_mbar"] == 200) & (merged["Qw_mlhr"] == 5)].sort_values(
        "conc_pct", ascending=False)
    if len(ref_cond) > 1:
        print("Stage 1 ratio vs 2% SDS  (Po=200, Qw=5):")
        s1_ref = ref_cond[ref_cond["conc_pct"] == 2.0]["S1_mean"].values
        if len(s1_ref) > 0:
            s1_ref = s1_ref[0]
            for _, r in ref_cond.iterrows():
                ratio = r.S1_mean / s1_ref
                print(f"  {CONC_LABELS[r.conc_pct]:>6} : S1 = {r.S1_mean:.3f} s  "
                      f"ratio = {ratio:.2f}")
        print()

    print("Stage 2 ratio vs 2% SDS  (Po=200, Qw=5):")
    if len(ref_cond) > 1:
        s2_ref = ref_cond[ref_cond["conc_pct"] == 2.0]["S2_mean"].values
        if len(s2_ref) > 0:
            s2_ref = s2_ref[0]
            for _, r in ref_cond.iterrows():
                ratio = r.S2_mean / s2_ref
                gamma_ratio = GAMMA_APPROX[r.conc_pct] / GAMMA_REF
                print(f"  {CONC_LABELS[r.conc_pct]:>6} : S2 = {r.S2_mean:.3f} s  "
                      f"exp ratio = {ratio:.2f}  gamma ratio = {gamma_ratio:.2f}")
    print("=" * 82)


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="V5-8-1 SDS concentration sweep analysis")
    parser.add_argument("--out-dir", default="results/v5_8_1_conc_sweep")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Loading data from: {DATA_PATH}")
    df    = load_and_clean(DATA_PATH)
    stats = compute_stats(df)

    concs = sorted(stats["conc_pct"].unique(), reverse=True)
    print(f"  {len(df)} observations across concentrations: "
          f"{[CONC_LABELS[c] for c in concs]}")
    print(f"  Conditions available per concentration:")
    for c in concs:
        sub = stats[stats["conc_pct"] == c]
        conds = [(int(r.Po_mbar), int(r.Qw_mlhr)) for _, r in sub.iterrows()]
        print(f"    {CONC_LABELS[c]:>6}: {conds}")

    print("\nRunning hydraulic model predictions ...")
    merged = run_model_predictions(stats, CONFIG_PATH)

    print_summary(merged)

    print("Generating figures ...")
    fig_stage1_vs_conc(merged, args.out_dir)
    fig_stage2_vs_conc(merged, args.out_dir)
    fig_cvisc_vs_conc(merged, args.out_dir)
    fig_geometry_vs_conc(merged, args.out_dir)
    fig_summary(merged, args.out_dir)

    print(f"\nAll figures saved to: {args.out_dir}")


if __name__ == "__main__":
    main()
