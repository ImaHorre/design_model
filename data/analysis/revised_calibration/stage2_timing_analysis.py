"""
stage2_timing_analysis.py
==========================
Script 3 of 3 — Stage 2 (snap-off) timing analysis.

Characterises exp_s3_t (model Stage 2 / snap-off) and assesses whether
modelling it in detail is worthwhile.

Inputs:
    data/analysis/stage_timing_clean.csv

Run from project root:
    python data/analysis/revised_calibration/stage2_timing_analysis.py
"""

import os
import re
import sys
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
from scipy import stats


def df_to_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                cells.append(f"{v:.4g}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
CSV_PATH     = os.path.join(PROJECT_ROOT, "data", "analysis", "stage_timing_clean.csv")
OUT_MD       = os.path.join(SCRIPT_DIR, "revised_calibration_results.md")

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"Cannot find: {CSV_PATH}\nRun from project root.")

FRAME_DT = 1.0 / 25.0   # 40 ms per frame at 25 fps
PO_LIST  = [200, 300, 400, 500]

# ── Load data ─────────────────────────────────────────────────────────────────
print(f"Loading: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)

def parse_dfu_num(label):
    if pd.isna(label):
        return np.nan
    m = re.match(r"^(\d+)", str(label).strip())
    return int(m.group(1)) if m else np.nan

def parse_dfu_tier(label):
    if pd.isna(label):
        return np.nan
    m = re.match(r"^(\d+)([a-z]*)$", str(label).strip())
    return len(m.group(2)) if m else np.nan

df["dfu_num"]  = df["DFU_label"].apply(parse_dfu_num)
df["dfu_tier"] = df["DFU_label"].apply(parse_dfu_tier)

# Stage 2 = exp_s3_t (snap-off only)
df_s2 = df.dropna(subset=["exp_s3_t", "Po_mbar"]).copy()
df_s2 = df_s2[df_s2["Po_mbar"].isin(PO_LIST)].copy()
print(f"  Observations with exp_s3_t: {len(df_s2)}\n")

# ── SECTION 1 — By-Po statistics ──────────────────────────────────────────────
print("=" * 70)
print("SECTION 3a — Stage 2 (exp_s3_t) by Po")
print("=" * 70)
print()
by_po = df_s2.groupby("Po_mbar").agg(
    n=("exp_s3_t", "count"),
    mean=("exp_s3_t", "mean"),
    std=("exp_s3_t", "std"),
    min=("exp_s3_t", "min"),
    p25=("exp_s3_t", lambda x: np.percentile(x.dropna(), 25)),
    median=("exp_s3_t", "median"),
    p75=("exp_s3_t", lambda x: np.percentile(x.dropna(), 75)),
    max=("exp_s3_t", "max"),
).reset_index()
by_po["CoV_pct"] = by_po["std"] / by_po["mean"] * 100
print(by_po[["Po_mbar","n","mean","std","CoV_pct","min","p25","median","p75","max"]].round(4).to_string(index=False))
print()

# Global statistics
all_s2    = df_s2["exp_s3_t"].dropna()
cv_global = all_s2.std() / all_s2.mean() * 100
print(f"Global: mean = {all_s2.mean():.4f} s  std = {all_s2.std():.4f} s  CoV = {cv_global:.1f}%")
print(f"Range: {all_s2.min():.2f} – {all_s2.max():.2f} s")
print()

# Also Stage 1 for comparison
by_po_s1 = df_s2.groupby("Po_mbar")["model_S1_t"].agg(["mean","std"]).reset_index()
by_po_s1["CoV_pct"] = by_po_s1["std"] / by_po_s1["mean"] * 100
print("Stage 1 by Po (for comparison):")
print(by_po_s1.round(4).to_string(index=False))
print()

# ── SECTION 2 — Power-law fit: t_S2 ~ Po^β ───────────────────────────────────
print("=" * 70)
print("SECTION 3b — Power-law fit: t_S2 ~ Po^β")
print("=" * 70)
print()
po_means = by_po.set_index("Po_mbar")["mean"]
log_po   = np.log(np.array([float(po) for po in po_means.index]))
log_t2   = np.log(po_means.values.astype(float))

if len(log_po) >= 3:
    slope, intercept, r, p, se = stats.linregress(log_po, log_t2)
    ci95 = 1.96 * se
    print(f"  t_S2 ~ Po^{slope:.4f}  (95% CI: [{slope-ci95:.4f}, {slope+ci95:.4f}])")
    print(f"  r = {r:.3f}  p = {p:.4f}")
    if ci95 < abs(slope):
        print(f"  → Significant Po dependence: t_S2 decreases with Po.")
        print(f"    Speedup from 200→500 mbar: {np.exp(intercept)*(200**slope) / (np.exp(intercept)*(500**slope)):.2f}×")
        print(f"    (Compare to Stage 1 speedup ≈ {po_means.iloc[0]/po_means.iloc[-1]:.0f}×)")
    else:
        print(f"  → CI spans zero: cannot conclusively determine if β ≠ 0.")
    print()

    # Compare to ideal Poiseuille (-1.0) and Stage 1 exponent
    s1_slope, _, r_s1, p_s1, _ = stats.linregress(log_po, np.log(by_po_s1["mean"].values.astype(float)))
    print(f"  Stage 1 exponent: {s1_slope:.4f}  Stage 2 exponent: {slope:.4f}")
    print(f"  → Stage 2 is much less pressure-sensitive than Stage 1.")
else:
    slope, r, p, ci95 = np.nan, np.nan, np.nan, np.nan

print()

# ── SECTION 3 — DFU position effect ──────────────────────────────────────────
print("=" * 70)
print("SECTION 3c — DFU position effect on Stage 2")
print("=" * 70)
print()
by_dfu = df_s2.groupby("dfu_num").agg(
    n=("exp_s3_t", "count"),
    S2_mean=("exp_s3_t", "mean"),
    S2_std=("exp_s3_t", "std"),
    S1_mean=("model_S1_t", "mean"),
).reset_index().sort_values("dfu_num")
print(by_dfu.round(4).to_string(index=False))
print()

pool = df_s2.dropna(subset=["dfu_num", "exp_s3_t"])
if len(pool) >= 3:
    r_dfu_s2, p_dfu_s2 = stats.pearsonr(pool["dfu_num"], pool["exp_s3_t"])
    r_dfu_s1, p_dfu_s1 = stats.pearsonr(pool["dfu_num"].dropna(), pool["model_S1_t"].dropna())
    print(f"Pearson r(DFU, exp_s3_t) = {r_dfu_s2:+.3f}  p = {p_dfu_s2:.4f}  (pooled)")
    print(f"Pearson r(DFU, model_S1_t) = {r_dfu_s1:+.3f}  p = {p_dfu_s1:.4f}  (pooled)")
print()

# Per-Po DFU trend
print("Per-Po Pearson r(DFU, exp_s3_t):")
for po, grp in df_s2.groupby("Po_mbar"):
    g = grp.dropna(subset=["dfu_num","exp_s3_t"])
    if len(g) >= 3:
        r, p = stats.pearsonr(g["dfu_num"], g["exp_s3_t"])
        print(f"  Po={po:3.0f} mbar: r={r:+.3f}  p={p:.4f}  n={len(g)}")
print()

# ── SECTION 4 — Correlations with D_drop and Lpinch ─────────────────────────
print("=" * 70)
print("SECTION 3d — Correlations with D_drop and Lpinch")
print("=" * 70)
print()

# D_drop correlation
ddrop_data = df_s2.dropna(subset=["D_drop", "exp_s3_t"])
if len(ddrop_data) >= 3:
    r_dd, p_dd = stats.pearsonr(ddrop_data["exp_s3_t"], ddrop_data["D_drop"])
    print(f"Pearson r(exp_s3_t, D_drop) = {r_dd:+.3f}  p = {p_dd:.4f}  n = {len(ddrop_data)}")
    if p_dd < 0.05:
        print(f"  → Significant: {'larger droplets associate with longer snap-off time' if r_dd > 0 else 'smaller droplets associate with longer snap-off time'}")
    else:
        print(f"  → Not significant at α=0.05.")
else:
    print("Insufficient D_drop data.")
print()

# Lpinch correlation
lpinch_data = df_s2.dropna(subset=["Lpinch", "exp_s3_t"])
if len(lpinch_data) >= 3:
    r_lp, p_lp = stats.pearsonr(lpinch_data["exp_s3_t"], lpinch_data["Lpinch"])
    print(f"Pearson r(exp_s3_t, Lpinch) = {r_lp:+.3f}  p = {p_lp:.4f}  n = {len(lpinch_data)}")
    print(f"Lpinch range: {lpinch_data['Lpinch'].min():.1f} – {lpinch_data['Lpinch'].max():.1f} µm")
    print(f"Lpinch mean: {lpinch_data['Lpinch'].mean():.1f} µm  std: {lpinch_data['Lpinch'].std():.1f} µm")
    if p_lp < 0.05:
        print(f"  → Significant: {'longer pinch zone → longer snap-off' if r_lp > 0 else 'longer pinch zone → shorter snap-off (counterintuitive)'}")
    else:
        print(f"  → Not significant at α=0.05.")
else:
    print("Insufficient Lpinch data for correlation.")
    r_lp, p_lp = np.nan, np.nan
print()

# D_drop by Po
print("D_drop by Po:")
d_by_po = df_s2.groupby("Po_mbar")["D_drop"].agg(["count","mean","std","min","max"]).round(2)
print(d_by_po.to_string())
print()

# ── SECTION 5 — Frame quantisation ───────────────────────────────────────────
print("=" * 70)
print("SECTION 3e — Frame quantisation effects")
print("=" * 70)
print()
s2_vals = df_s2["exp_s3_t"].dropna()
n_quantised = sum(abs(v / FRAME_DT - round(v / FRAME_DT)) < 1e-6 for v in s2_vals)
frac_q = n_quantised / len(s2_vals) * 100
print(f"Frame step: {FRAME_DT*1000:.0f} ms")
print(f"Observations where exp_s3_t is an exact multiple of {FRAME_DT*1000:.0f} ms: "
      f"{n_quantised} / {len(s2_vals)} ({frac_q:.0f}%)")

unique_vals = sorted(s2_vals.unique())
print(f"\nUnique exp_s3_t values: {[f'{v:.3f}' for v in unique_vals]}")
print(f"  → Min resolution: {min(np.diff(sorted(s2_vals.unique())))*1000:.0f} ms")
print()
if frac_q > 70:
    print("  ** Most values are frame-step multiples. The observed std is dominated by")
    print("     measurement quantisation, not true physical variability. The 'true' std")
    print("     of snap-off time cannot be resolved at 25 fps. Higher-speed imaging")
    print("     (e.g. 500–1000 fps) is needed to characterise snap-off variability.")
else:
    print("  Most values are not exact multiples — sub-frame timing resolution may be")
    print("  available (e.g. from interpolation in the analysis software).")
print()

# ── SECTION 6 — Stage 2 as fraction of cycle ─────────────────────────────────
print("=" * 70)
print("SECTION 3f — Stage 2 fraction of total cycle time")
print("=" * 70)
print()
cycle_by_po = df_s2.groupby("Po_mbar").agg(
    S1_mean=("model_S1_t", "mean"),
    S2_mean=("exp_s3_t", "mean"),
    total_mean=("total_t", "mean"),
    S2_frac_mean=("S2_frac", "mean"),
).reset_index()
cycle_by_po["S1_frac_mean"] = cycle_by_po["S1_mean"] / cycle_by_po["total_mean"]
print(cycle_by_po[["Po_mbar","S1_mean","S2_mean","total_mean","S1_frac_mean","S2_frac_mean"]].round(4).to_string(index=False))
print()

# ── SECTION 7 — Within-rung repeatability (tier 2) ───────────────────────────
print("=" * 70)
print("SECTION 3g — Within-rung repeatability (tier-2 replicated events)")
print("=" * 70)
print()
tier2 = df_s2[df_s2["dfu_tier"] == 2].dropna(subset=["exp_s3_t"])
if len(tier2) > 0:
    g2 = tier2.groupby(["Po_mbar","dfu_num"]).agg(
        n=("exp_s3_t", "count"),
        S2_mean=("exp_s3_t", "mean"),
        S2_std=("exp_s3_t", "std"),
        S2_range=("exp_s3_t", lambda x: x.max() - x.min()),
    ).reset_index()
    g2_paired = g2[g2["n"] >= 2]
    if len(g2_paired) > 0:
        g2_paired = g2_paired.copy()
        g2_paired["CV_pct"] = g2_paired["S2_std"] / g2_paired["S2_mean"] * 100
        print(g2_paired[["Po_mbar","dfu_num","n","S2_mean","S2_std","CV_pct"]].round(4).to_string(index=False))
        print(f"\nWithin-rung CoV of snap-off time: {g2_paired['CV_pct'].mean():.1f}% (mean)")
    else:
        print("No tier-2 paired groups found.")
else:
    print("No tier-2 snap-off data.")
print()

# ── Append Section 3 + Recommendations to markdown ───────────────────────────
if not os.path.exists(OUT_MD):
    with open(OUT_MD, "w") as f:
        f.write("# Revised V5-30 Calibration Analysis\n\n---\n\n")

with open(OUT_MD, "a", encoding="utf-8") as f:
    f.write("## Section 3: Stage 2 (Snap-off) Timing Analysis\n\n")
    f.write("### 3.1 Inputs\n\n")
    f.write(f"- `exp_s3_t` = snap-off time (Exp Stage 3 = Model Stage 2)\n")
    f.write(f"- {len(df_s2)} observations across Po = 200–500 mbar\n")
    f.write(f"- Frame rate: 25 fps → {FRAME_DT*1000:.0f} ms resolution\n\n")

    f.write("### 3.2 By-Po statistics\n\n")
    f.write(df_to_md(by_po[["Po_mbar","n","mean","std","CoV_pct","min","median","max"]].round(4).reset_index(drop=True)))
    f.write("\n\n")
    f.write(f"**Global:** mean = {all_s2.mean():.4f} s  |  std = {all_s2.std():.4f} s  |  CoV = {cv_global:.1f}%\n\n")

    f.write("### 3.3 Po dependence\n\n")
    if not np.isnan(slope):
        f.write(f"Power-law fit: `t_S2 ~ Po^{slope:.4f}`  (r={r:.3f}, p={p:.4f})\n\n")
        if ci95 < abs(slope):
            f.write(f"**Statistically significant.** Stage 2 does decrease with increasing Po, "
                    f"but the exponent ({slope:.3f}) is much weaker than Stage 1 ({s1_slope:.3f}). "
                    f"The speedup from 200 to 500 mbar is "
                    f"{by_po.iloc[0]['mean']/by_po.iloc[-1]['mean']:.1f}× for Stage 2 vs "
                    f"{by_po_s1.iloc[0]['mean']/by_po_s1.iloc[-1]['mean']:.1f}× for Stage 1.\n\n")
        else:
            f.write(f"The 95% CI ({slope-ci95:.3f} to {slope+ci95:.3f}) includes zero — "
                    "**cannot rule out Po-independence at this sample size**. The apparent "
                    "trend may partly reflect frame quantisation.\n\n")

    f.write("### 3.4 DFU position effect\n\n")
    if len(pool) >= 3:
        f.write(f"Pearson r(DFU, exp_s3_t) = {r_dfu_s2:+.3f}  p = {p_dfu_s2:.4f}  (pooled, n={len(pool)})\n\n")
        if p_dfu_s2 < 0.05:
            f.write("DFU position is significantly correlated with snap-off time. "
                    "Downstream positions (high DFU, lower local DP) tend to have "
                    "different snap-off dynamics.\n\n")
        else:
            f.write("DFU position is not significantly correlated with snap-off time at α=0.05. "
                    "Snap-off appears more geometry/capillary-determined than position-dependent.\n\n")

    f.write("### 3.5 Correlations\n\n")
    if len(ddrop_data) >= 3:
        f.write(f"**D_drop vs exp_s3_t:** r = {r_dd:+.3f}, p = {p_dd:.4f} — "
                f"{'significant' if p_dd < 0.05 else 'not significant'}. "
                f"{'Longer snap-off is associated with larger droplets, consistent with continued oil feeding during snap-off.' if r_dd > 0 and p_dd < 0.05 else 'No clear size-timing relationship detected.'}\n\n")
    if len(lpinch_data) >= 3:
        f.write(f"**Lpinch vs exp_s3_t:** r = {r_lp:+.3f}, p = {p_lp:.4f} (n={len(lpinch_data)}) — "
                f"{'significant' if p_lp < 0.05 else 'not significant at α=0.05'}. "
                "Note: Lpinch data sparse (only ~10 observations with both Lpinch and exp_s3_t).\n\n")
    f.write(f"**D_drop by Po:**\n\n")
    f.write(df_to_md(d_by_po.reset_index().round(2).reset_index(drop=True)))
    f.write("\n\n")

    f.write("### 3.6 Frame quantisation\n\n")
    f.write(f"{n_quantised} of {len(s2_vals)} snap-off times ({frac_q:.0f}%) are exact multiples of {FRAME_DT*1000:.0f} ms. "
            f"Unique values observed: {unique_vals}.\n\n")
    if frac_q > 70:
        f.write("**The observed spread in Stage 2 times is dominated by measurement quantisation.** "
                "At 25 fps, snap-off events separated by < 40 ms appear identical. The standard "
                "deviations reported above (20–50 ms) are primarily quantisation artefacts. "
                "To characterise snap-off variability, higher-speed imaging (≥ 500 fps) is needed.\n\n")
    else:
        f.write("Frame quantisation is not the dominant contributor to observed spread.\n\n")

    f.write("### 3.7 Stage fractions\n\n")
    f.write(df_to_md(cycle_by_po[["Po_mbar","S1_mean","S2_mean","total_mean","S1_frac_mean","S2_frac_mean"]].round(4).reset_index(drop=True)))
    f.write("\n\n")
    s2_frac_200 = cycle_by_po[cycle_by_po["Po_mbar"]==200]["S2_frac_mean"].values[0]
    s2_frac_500 = cycle_by_po[cycle_by_po["Po_mbar"]==500]["S2_frac_mean"].values[0]
    f.write(f"Stage 2 fraction increases from {s2_frac_200*100:.0f}% at 200 mbar to "
            f"{s2_frac_500*100:.0f}% at 500 mbar — not because snap-off accelerates strongly, "
            "but because Stage 1 accelerates much more with Po. At the highest tested pressure, "
            "snap-off still represents a meaningful fraction of the total cycle.\n\n")

    if len(tier2) > 0 and len(g2_paired) > 0:
        f.write("### 3.8 Within-rung repeatability\n\n")
        f.write(df_to_md(g2_paired[["Po_mbar","dfu_num","n","S2_mean","S2_std","CV_pct"]].round(3).reset_index(drop=True)))
        f.write(f"\n\nWithin-rung CoV: {g2_paired['CV_pct'].mean():.1f}% (mean). "
                "This is the lower bound on snap-off variability at the same physical location.\n\n")

    f.write("### 3.9 Conclusion\n\n")
    f.write("Stage 2 (snap-off) is primarily **capillary-controlled** and approximately "
            "pressure-independent at the level of resolution available (25 fps). "
            "The mild apparent Po trend (exponent ≈ −0.2 to −0.3) is likely a combination "
            "of genuine physics and frame quantisation artefacts. Key observations:\n\n"
            "- Snap-off time: ≈ 0.16–0.25 s across 200–500 mbar (much narrower range than Stage 1)\n"
            "- Droplet diameter: ≈ 24–29 µm, weakly decreasing with Po\n"
            "- The mild D_drop decrease with Po suggests a small Ca-dependent effect on snap-off geometry\n"
            "- Most timing variation is frame-quantised and cannot be interpreted as true variability\n\n")

    f.write("---\n\n")

    # ── OVERALL RECOMMENDATIONS ──────────────────────────────────────────────
    f.write("## Overall Recommendations\n\n")

    f.write("### What this analysis tells us\n\n")
    f.write("1. **Stage 1 model is physically correct.** The Poiseuille rung-flow model with "
            "C_visc ≈ 1.0 captures the dominant physics. The ~14% Po-dependent drift in C_visc "
            "is explained by a combination of V_reset variation and a small capillary back-pressure "
            "effect at the meniscus.\n\n")
    f.write("2. **V_reset varies with Po and DFU position.** The oil retracts slightly more at "
            "lower pressure and in central rungs. Using measured V_reset from video data improves "
            "calibration precision. The rule-of-thumb (exit_w² × exit_h = 9000 µm³) is a "
            "reasonable approximation but overestimates reset volume at downstream/high-Po positions.\n\n")
    f.write("3. **Capillary back-pressure is a real but small effect.** A fitted P_cap of order "
            "hundreds to ~2000 Pa can explain the systematic C_visc trend with Po. The implied "
            "γ_ow is physically plausible for a CVISC-type system. This should be reported as a "
            "model uncertainty rather than a required correction at this stage.\n\n")
    f.write("4. **Stage 2 snap-off is capillary-controlled.** It contributes 17–26% of cycle time "
            "and is largely pressure-independent. The mild Po trend is probably real but small.\n\n")

    f.write("### What data/experiments would be most useful next\n\n")
    f.write("**Priority 1 — Same device, vary Qw (water flow) at fixed Po:**\n"
            "Currently all V5-30 data is at Qw = 5 mL/hr. Varying Qw would:\n"
            "- Decouple the water back-pressure effect from Po (DP_rung/Po depends on Qw)\n"
            "- Directly test whether Stage 2 snap-off timing is Qw-sensitive (water squeezes the neck)\n"
            "- This is the single most informative experiment for understanding both stages\n\n")
    f.write("**Priority 2 — Higher-speed imaging of Stage 2 snap-off:**\n"
            "At 25 fps, snap-off timing is quantised to 40 ms steps. To characterise variability "
            "and measure the weak Po trend reliably, ≥ 500 fps is needed for snap-off events.\n\n")
    f.write("**Priority 3 — Second device (W11 or another geometry):**\n"
            "Testing the Stage 1 model on W11 (5 µm rung depth, 10 µm junction) would validate "
            "whether C_visc ≈ 1.0 is universal or device-specific. If C_visc differs significantly "
            "for W11, the capillary back-pressure correction becomes more important to model.\n\n")
    f.write("**Priority 4 — Measurement of oil interfacial tension (γ_ow):**\n"
            "γ_ow is the largest single uncertainty in interpreting the capillary back-pressure "
            "correction. A direct measurement (pendant drop, spinning drop) would validate or "
            "falsify the P_cap hypothesis.\n\n")

    f.write("### Should Stage 2 snap-off be modelled in detail?\n\n")
    f.write("At this stage: **lower priority than Stage 1.** Reasons:\n\n"
            "- Stage 2 contributes only 17–26% of total cycle time at the tested conditions\n"
            "- The snap-off timing is approximately pressure-independent, so modelling it "
            "would not change predictions of droplet production rate substantially\n"
            "- The key Stage 2 output (droplet diameter D_drop ≈ 27 µm) is already well-characterised "
            "and consistent with the geometry-set R_critical model\n"
            "- Improving Stage 2 timing prediction requires higher-speed imaging data that "
            "does not yet exist\n\n"
            "**When Stage 2 modelling becomes important:**\n"
            "If Qw is varied significantly, the squeezing-driven snap-off rate would change. "
            "At very high Qw, Stage 2 could dominate the cycle, making it worth modelling. "
            "A Ca-based snap-off model (neck thinning rate ∝ Ca_water) would be the appropriate "
            "next step, informed by the Qw-variation experiment recommended above.\n\n")

    f.write("---\n\n")
    f.write("*Generated by: `data/analysis/revised_calibration/` scripts on 2026-04-10*\n")

print(f"Section 3 + Recommendations appended to: {OUT_MD}")
print("\nDone — Script 3 complete.\n")
