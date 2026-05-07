"""
calibrate_cvisc.py
==================
C_visc calibration for Stage 1 Poiseuille refill model.

Formula:
    t_stage1 = C_visc × V_reset × R_rung / DP_rung

Procedure:
1. Load V5_30_3_3 device config
2. Run hydraulic solver at Po = 200, 300, 400, 500 mbar
3. Extract DP_rung = mean(P_oil - P_water) from the network
4. Compute R_rung (Shah-London), V_reset (from geometry)
5. Compute t_base = V_reset * R_rung / DP_rung
6. Compare to experimental t_S1 mean at each Po
7. Fit C_visc_fitted = t_S1_obs / t_base
8. Report and write markdown summary

Experimental data source: data/analysis/stage_timing_clean.csv
Device config:            configs/v5_30.yaml
"""

import sys
import os
import math
import numpy as np
import pandas as pd

# Ensure project root is on path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
sys.path.insert(0, PROJECT_ROOT)

from stepgen.config import load_config
from stepgen.models.hydraulics import simulate
from stepgen.models.stage_wise_v3.stage1_physics import compute_rung_resistance

# ── Paths ─────────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "v5_30.yaml")
CSV_PATH    = os.path.join(SCRIPT_DIR, "stage_timing_clean.csv")
OUT_MD      = os.path.join(SCRIPT_DIR, "cvisc_calibration_results.md")

# ── Experimental conditions ───────────────────────────────────────────────────
PO_VALUES    = [200, 300, 400, 500]   # mbar
QW_MLHR      = 5.0                    # assumed from v5_30.yaml (not in clean CSV)

# ── Load config ───────────────────────────────────────────────────────────────
print(f"Loading config: {CONFIG_PATH}")
config = load_config(CONFIG_PATH)
print(f"  Nmc = {config.geometry.Nmc} rungs")
print(f"  mu_oil = {config.fluids.mu_dispersed*1e3:.1f} mPa.s")
print(f"  Rung: {config.geometry.rung.mcd*1e6:.0f}um x {config.geometry.rung.mcw*1e6:.0f}um x {config.geometry.rung.mcl*1e6:.0f}um")
print(f"  Junction: {config.geometry.junction.exit_width*1e6:.0f}um x {config.geometry.junction.exit_depth*1e6:.0f}um")

# ── Geometry-derived parameters ───────────────────────────────────────────────
R_rung = compute_rung_resistance(config)

exit_w = config.geometry.junction.exit_width
exit_h = config.geometry.junction.exit_depth
L_r    = exit_w                         # reset distance = one exit width
V_reset = L_r * exit_w * exit_h         # [m³]

print(f"\nGeometry-derived:")
print(f"  R_rung = {R_rung:.4e} Pa.s/m3")
print(f"  V_reset = {V_reset:.4e} m3  = {V_reset*1e18:.1f} um3  = {V_reset*1e15:.4f} fL")

# ── Load experimental data ────────────────────────────────────────────────────
print(f"\nLoading experimental data: {CSV_PATH}")
exp = pd.read_csv(CSV_PATH)
exp_by_po = exp.groupby("Po_mbar").agg(
    n          = ("model_S1_t", "count"),
    t_S1_mean  = ("model_S1_t", "mean"),
    t_S1_std   = ("model_S1_t", "std"),
    t_S1_min   = ("model_S1_t", "min"),
    t_S1_max   = ("model_S1_t", "max"),
    t_S2_mean  = ("model_S2_t", "mean"),
    t_S2_std   = ("model_S2_t", "std"),
    total_mean = ("total_t",    "mean"),
).reset_index()

print("\nExperimental Stage 1 summary:")
print(exp_by_po[["Po_mbar","n","t_S1_mean","t_S1_std"]].to_string(index=False, float_format="%.4f"))

# ── Run hydraulic model at each Po ────────────────────────────────────────────
print(f"\nRunning hydraulic solver at {len(PO_VALUES)} operating points (Qw={QW_MLHR} mL/hr)...")
rows = []

for po in PO_VALUES:
    print(f"  Po = {po} mbar ... ", end="", flush=True)
    sim = simulate(config, po, QW_MLHR, 0.0)

    P_oil   = sim.P_oil      # [Pa] array over Nmc rungs
    P_water = sim.P_water    # [Pa] array over Nmc rungs
    DP_j    = P_oil - P_water  # [Pa] DP_rung profile

    # Summary statistics of DP_rung across all rungs
    DP_mean = float(np.mean(DP_j))
    DP_std  = float(np.std(DP_j))
    DP_min  = float(np.min(DP_j))
    DP_max  = float(np.max(DP_j))

    # Baseline model time (C_visc = 1)
    if DP_mean > 0:
        t_base = V_reset * R_rung / DP_mean
    else:
        t_base = float('inf')

    # Po as Pa (what "ideal" DP_rung would be if P_water = 0)
    Po_Pa    = po * 100.0
    t_base_full_po = V_reset * R_rung / Po_Pa

    # Experimental t_S1 mean at this Po
    row_exp = exp_by_po[exp_by_po["Po_mbar"] == float(po)]
    if len(row_exp) == 0:
        t_obs = None
        C_visc = None
    else:
        t_obs  = float(row_exp["t_S1_mean"].iloc[0])
        C_visc = t_obs / t_base if t_base < float('inf') else None

    C_visc_full_po = t_obs / t_base_full_po if (t_obs is not None and t_base_full_po > 0) else None

    print(f"DP_mean = {DP_mean:.1f} Pa  (Po = {Po_Pa:.0f} Pa)  t_base = {t_base:.3f} s  t_obs = {t_obs:.3f} s  C_visc = {C_visc:.3f}")

    rows.append({
        "Po_mbar":       po,
        "Po_Pa":         Po_Pa,
        "P_oil_inlet":   float(P_oil[0]),
        "P_oil_outlet":  float(P_oil[-1]),
        "P_water_inlet": float(P_water[0]),
        "P_water_outlet":float(P_water[-1]),
        "DP_mean_Pa":    DP_mean,
        "DP_std_Pa":     DP_std,
        "DP_min_Pa":     DP_min,
        "DP_max_Pa":     DP_max,
        "DP_frac_of_Po": DP_mean / Po_Pa,
        "t_base_s":      t_base,
        "t_base_fullPo": t_base_full_po,
        "t_S1_obs":      t_obs,
        "C_visc_network":C_visc,          # using hydraulic-network DP_rung
        "C_visc_fullPo": C_visc_full_po,  # using bare Po (sanity check)
    })

results = pd.DataFrame(rows)

# ── C_visc fit ────────────────────────────────────────────────────────────────
# Fit 1: single global mean
c_vals = results["C_visc_network"].dropna()
C_visc_mean  = float(c_vals.mean())
C_visc_std   = float(c_vals.std())
C_visc_range = (float(c_vals.min()), float(c_vals.max()))

# Fit 2: power law — does C_visc vary with Po?
log_po   = np.log(results["Po_Pa"].astype(float))
log_tv   = np.log(results["t_S1_obs"].astype(float))
b_obs, a_obs = np.polyfit(log_po, log_tv, 1)   # t_obs ~ Po^b_obs

log_tb   = np.log(results["t_base_s"].astype(float))
b_base, a_base = np.polyfit(log_po, log_tb, 1) # t_base ~ Po^b_base  (should be ~-1.0)

# Residual exponent (from C_visc variation with Po)
# t_obs = C_visc × t_base  →  if C_visc ~ Po^δ, then b_obs = b_base + δ
delta_exponent = b_obs - b_base

print(f"\n--- Calibration Summary ---")
print(f"R_rung         = {R_rung:.4e} Pa·s/m³")
print(f"V_reset        = {V_reset:.4e} m³  ({V_reset*1e18:.0f} µm³)")
print(f"t_base exponent (vs Po):  {b_base:.3f}  (ideal Poiseuille: -1.0)")
print(f"t_obs  exponent (vs Po):  {b_obs:.3f}")
print(f"C_visc exponent residual: {delta_exponent:.3f}  (0 = no Po dependence)")
print(f"\nC_visc (network DP_rung): mean = {C_visc_mean:.3f} ± {C_visc_std:.3f}")
print(f"C_visc range: {C_visc_range[0]:.3f} – {C_visc_range[1]:.3f}")
print(f"\nPer-Po:")
print(results[["Po_mbar","DP_mean_Pa","DP_frac_of_Po","t_base_s","t_S1_obs","C_visc_network","C_visc_fullPo"]].to_string(index=False, float_format="%.4f"))

# ── Predicted vs observed table ──────────────────────────────────────────────
results["t_pred_best"] = results["t_base_s"] * C_visc_mean
results["residual_pct"] = (results["t_pred_best"] - results["t_S1_obs"]) / results["t_S1_obs"] * 100

# Also compute the "best fit" predicted Stage 1 times
print(f"\nPredicted Stage 1 times (C_visc = {C_visc_mean:.3f}):")
for _, row in results.iterrows():
    print(f"  Po = {row['Po_mbar']:3.0f} mbar:  t_pred = {row['t_pred_best']:.3f} s  t_obs = {row['t_S1_obs']:.3f} s  residual = {row['residual_pct']:+.1f}%")

# ── Stage 2 summary ──────────────────────────────────────────────────────────
print(f"\n--- Stage 2 Summary (from experiment) ---")
print(exp_by_po[["Po_mbar","t_S2_mean","t_S2_std"]].to_string(index=False, float_format="%.4f"))

# ── Write markdown report ─────────────────────────────────────────────────────
with open(OUT_MD, "w", encoding="utf-8") as f:

    f.write("# C_visc Calibration Results\n")
    f.write("## Stage 1 Poiseuille Refill Model — V5_30_3_3\n\n")
    f.write(f"**Date:** 2026-03-20  \n")
    f.write(f"**Device config:** configs/v5_30.yaml  \n")
    f.write(f"**Experimental data:** data/analysis/stage_timing_clean.csv  \n")
    f.write(f"**Water flow (Qw):** {QW_MLHR} mL/hr (default from v5_30.yaml)  \n\n")

    f.write("---\n\n")
    f.write("## Model formula\n\n")
    f.write("```\n")
    f.write("t_stage1 = C_visc × V_reset × R_rung / DP_rung\n")
    f.write("```\n\n")

    f.write("## Device parameters\n\n")
    f.write(f"| Parameter | Value |\n|---|---|\n")
    f.write(f"| mu_oil | {config.fluids.mu_dispersed*1e3:.1f} mPa.s |\n")
    f.write(f"| Rung geometry | {config.geometry.rung.mcd*1e6:.0f}x{config.geometry.rung.mcw*1e6:.0f}x{config.geometry.rung.mcl*1e6:.0f} um (d x w x L) |\n")
    f.write(f"| Junction | {exit_w*1e6:.0f}x{exit_h*1e6:.0f} um (w x h) |\n")
    f.write(f"| Nmc (rungs) | {config.geometry.Nmc} |\n")
    f.write(f"| R_rung (Shah-London) | {R_rung:.4e} Pa.s/m3 |\n")
    f.write(f"| V_reset = exit_w^2 x exit_h | {V_reset*1e18:.0f} um3 = {V_reset*1e15:.3f} fL |\n\n")

    f.write("## Hydraulic network pressures\n\n")
    f.write("*P_oil and P_water from the full ladder-network solver at each Po, Qw = 5 mL/hr.*\n\n")
    f.write("| Po (mbar) | DP_mean (Pa) | DP as % of Po | P_oil inlet (Pa) | P_water outlet (Pa) |\n")
    f.write("|---|---|---|---|---|\n")
    for _, row in results.iterrows():
        f.write(f"| {row['Po_mbar']:.0f} | {row['DP_mean_Pa']:.1f} | {row['DP_frac_of_Po']*100:.1f}% | {row['P_oil_inlet']:.1f} | {row['P_water_outlet']:.1f} |\n")
    f.write("\n")

    f.write("## C_visc calibration\n\n")
    f.write("### Per-Po fit\n\n")
    f.write("| Po (mbar) | DP_mean (Pa) | t_base (s) | t_S1 obs (s) | C_visc (network DP) | C_visc (bare Po) |\n")
    f.write("|---|---|---|---|---|---|\n")
    for _, row in results.iterrows():
        f.write(f"| {row['Po_mbar']:.0f} | {row['DP_mean_Pa']:.1f} | {row['t_base_s']:.4f} | {row['t_S1_obs']:.4f} | **{row['C_visc_network']:.3f}** | {row['C_visc_fullPo']:.3f} |\n")
    f.write("\n")

    f.write(f"### Global fit\n\n")
    f.write(f"| Statistic | Value |\n|---|---|\n")
    f.write(f"| C_visc mean (all Po) | **{C_visc_mean:.3f}** |\n")
    f.write(f"| C_visc std | {C_visc_std:.3f} |\n")
    f.write(f"| C_visc range | {C_visc_range[0]:.3f} – {C_visc_range[1]:.3f} |\n")
    f.write(f"| t_base Po exponent | {b_base:.3f} (ideal −1.0) |\n")
    f.write(f"| t_obs Po exponent | {b_obs:.3f} |\n")
    f.write(f"| C_visc residual exponent (δ) | {delta_exponent:.3f} (0 = no Po dependence) |\n\n")

    f.write("### Predicted vs observed with best-fit C_visc\n\n")
    f.write(f"*Using C_visc = {C_visc_mean:.3f}*\n\n")
    f.write("| Po (mbar) | t_pred (s) | t_obs (s) | residual (%) |\n")
    f.write("|---|---|---|---|\n")
    for _, row in results.iterrows():
        f.write(f"| {row['Po_mbar']:.0f} | {row['t_pred_best']:.4f} | {row['t_S1_obs']:.4f} | {row['residual_pct']:+.1f}% |\n")
    f.write("\n")

    f.write("## Po scaling analysis\n\n")
    f.write("Power-law exponents from log-log fit:\n\n")
    f.write(f"- **t_base ~ Po^({b_base:.3f})** (model baseline, ideal −1.0)\n")
    f.write(f"- **t_obs ~ Po^({b_obs:.3f})** (experimental observation)\n")
    f.write(f"- **Δexponent = {delta_exponent:.3f}** (C_visc would need Po^({delta_exponent:.3f}) dependence to fully close gap)\n\n")
    if abs(delta_exponent) < 0.05:
        f.write("→ C_visc is essentially **Po-independent**. A single global constant is appropriate.\n\n")
    elif abs(delta_exponent) < 0.15:
        f.write("→ C_visc has **weak Po dependence**. A single global constant is a good approximation.\n\n")
    else:
        f.write(f"→ C_visc has **significant Po dependence** (exponent {delta_exponent:.3f}). A Po-varying C_visc may be needed, "
                f"or a physical correction term (capillary back-pressure) should be added.\n\n")

    f.write("## Stage 2 summary (experimental, no model fit)\n\n")
    f.write("| Po (mbar) | t_S2 mean (ms) | t_S2 std (ms) |\n")
    f.write("|---|---|---|\n")
    for _, row in exp_by_po.iterrows():
        if row["Po_mbar"] in [200, 300, 400, 500]:
            f.write(f"| {row['Po_mbar']:.0f} | {row['t_S2_mean']*1000:.1f} | {row['t_S2_std']*1000:.1f} |\n")
    f.write("\n")
    f.write("Stage 2 is approximately Po-independent. No C_visc equivalent is fitted for Stage 2 at this stage.\n\n")

    f.write("## Interpretation and recommended code change\n\n")
    f.write(f"With the actual device parameters (μ_oil = {config.fluids.mu_dispersed*1e3:.0f} mPa·s, "
            f"rung {config.geometry.rung.mcd*1e6:.0f}×{config.geometry.rung.mcw*1e6:.0f}×{config.geometry.rung.mcl*1e6:.0f} µm), "
            f"the fitted C_visc = **{C_visc_mean:.2f} ± {C_visc_std:.2f}**.\n\n")
    if C_visc_mean > 2.0:
        f.write("This is substantially above 1.0, indicating significant additional resistance beyond bulk Poiseuille flow. "
                "Likely mechanisms: surface viscosity at fresh oil–water interface, partial SDS depletion at the contact line, "
                "or geometric entry/exit losses not captured by the straight-rung Poiseuille formula.\n\n")
    elif C_visc_mean > 1.1:
        f.write("This is modestly above 1.0. The model captures most of the Stage 1 physics correctly. "
                "The residual C_visc factor reflects minor additional resistance from the fresh interface "
                "(surface viscosity, contact line effects) or geometric corrections at the rung entry/exit.\n\n")
    else:
        f.write("This is close to 1.0, indicating that the Poiseuille model with the bulk oil viscosity "
                "captures Stage 1 correctly without significant additional correction.\n\n")

    f.write(f"**Recommended action:** Set `stage1_viscosity_correction = {C_visc_mean:.2f}` in "
            f"`StageWiseV3Config` (file: `stepgen/models/stage_wise_v3/__init__.py`, line 74) "
            f"after validating that the hydraulic network DP_rung values are physically correct.\n\n")

    f.write("---\n")
    f.write("*Generated by data/analysis/calibrate_cvisc.py*\n")

print(f"\nMarkdown report written to: {OUT_MD}")
print("\nDone.")
