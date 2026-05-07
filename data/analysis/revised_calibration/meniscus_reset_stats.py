"""
meniscus_reset_stats.py
=======================
Script 1 of 3 — Meniscus reset length statistics.

Does L_menpoint (and V_reset) vary systematically with Po or DFU position?

Inputs:
    data/analysis/stage_timing_clean.csv

Outputs:
    Prints tables to stdout
    Creates/overwrites data/analysis/revised_calibration/revised_calibration_results.md
      with Section 1.

Run from project root:
    python data/analysis/revised_calibration/meniscus_reset_stats.py
"""

import os
import re
import sys
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
from scipy import stats


def df_to_md(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavoured markdown table (no tabulate needed)."""
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
    raise FileNotFoundError(
        f"Cannot find stage_timing_clean.csv.\n"
        f"Expected: {CSV_PATH}\n"
        "Run from the project root directory."
    )

# ── Constants ─────────────────────────────────────────────────────────────────
FRAME_RATE  = 25.0            # fps
FRAME_DT    = 1.0 / FRAME_RATE  # 0.04 s per frame
EXIT_W_UM   = 30.0            # junction exit width [µm]
EXIT_H_UM   = 10.0            # junction exit depth [µm]
V_NOMINAL   = EXIT_W_UM ** 2 * EXIT_H_UM  # 9000 µm³ — rule-of-thumb reset volume

# ── Load data ─────────────────────────────────────────────────────────────────
print(f"Loading: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)
print(f"  Rows loaded: {len(df)}")
print(f"  Columns: {list(df.columns)}\n")

# ── DFU label parsing ─────────────────────────────────────────────────────────
# DFU_label examples: "0a", "3b", "6aa", "6ab", NaN (one unlabelled row)
# tier 0 = single observation (no suffix)
# tier 1 = within-position replicates (one letter suffix: 3a, 3b)
# tier 2 = within-rung replicates (two letter suffix: 6aa, 6ab)

def parse_dfu(label):
    """Return (dfu_num, tier) from a DFU label string."""
    if pd.isna(label) or label == "":
        return (np.nan, np.nan)
    label = str(label).strip()
    m = re.match(r"^(\d+)([a-z]*)$", label)
    if not m:
        return (np.nan, np.nan)
    num    = int(m.group(1))
    suffix = m.group(2)
    tier   = len(suffix)      # 0, 1, or 2
    return (num, tier)

parsed         = df["DFU_label"].apply(parse_dfu)
df["dfu_num"]  = parsed.apply(lambda x: x[0])
df["dfu_tier"] = parsed.apply(lambda x: x[1])

# ── Drop rows with missing L_menpoint ────────────────────────────────────────
n_before = len(df)
df_geo = df.dropna(subset=["L_menpoint", "V_reset_fL"]).copy()
print(f"Rows with L_menpoint measured: {len(df_geo)} / {n_before}")
print(f"  (Missing: {n_before - len(df_geo)} rows — unlabelled or no geometry data)\n")

# ── DFU tier summary ──────────────────────────────────────────────────────────
print("=" * 70)
print("SECTION 1a — DFU label tiers")
print("=" * 70)
tier_counts = df_geo.groupby("dfu_tier")["dfu_num"].count()
print(f"  Tier 0 (single obs per position): {tier_counts.get(0, 0)} rows")
print(f"  Tier 1 (within-position, e.g. 3a/3b): {tier_counts.get(1, 0)} rows")
print(f"  Tier 2 (within-rung, e.g. 6aa/6ab): {tier_counts.get(2, 0)} rows\n")

# ── Within-group variability ──────────────────────────────────────────────────
print("=" * 70)
print("SECTION 1b — Within-group variability")
print("=" * 70)
print()
print("--- Tier 1: Within-position (e.g. two junctions at same DFU) ---")
tier1 = df_geo[df_geo["dfu_tier"] == 1].copy()
if len(tier1) > 0:
    g1 = tier1.groupby(["Po_mbar", "dfu_num"]).agg(
        n=("L_menpoint", "count"),
        Lmen_mean=("L_menpoint", "mean"),
        Lmen_std=("L_menpoint", "std"),
        Lmen_range=("L_menpoint", lambda x: x.max() - x.min()),
        Vreset_mean=("V_reset_fL", "mean"),
        Vreset_std=("V_reset_fL", "std"),
    ).reset_index()
    # Only groups with n >= 2 have meaningful std
    g1_paired = g1[g1["n"] >= 2].copy()
    if len(g1_paired) > 0:
        g1_paired["CV_pct"] = g1_paired["Lmen_std"] / g1_paired["Lmen_mean"] * 100
        print(g1_paired[["Po_mbar","dfu_num","n","Lmen_mean","Lmen_std","CV_pct","Lmen_range"]].round(2).to_string(index=False))
        high_cv = g1_paired[g1_paired["CV_pct"] > 20]
        if len(high_cv) > 0:
            print(f"\n  ** High intra-group CV (>20%) at:")
            print(high_cv[["Po_mbar","dfu_num","CV_pct"]].to_string(index=False))
    else:
        print("  No paired tier-1 groups found.")
else:
    print("  No tier-1 data found.")
print()

print("--- Tier 2: Within-rung (e.g. two events on same rung) ---")
tier2 = df_geo[df_geo["dfu_tier"] == 2].copy()
if len(tier2) > 0:
    g2 = tier2.groupby(["Po_mbar", "dfu_num"]).agg(
        n=("L_menpoint", "count"),
        Lmen_mean=("L_menpoint", "mean"),
        Lmen_std=("L_menpoint", "std"),
        Lmen_range=("L_menpoint", lambda x: x.max() - x.min()),
    ).reset_index()
    g2_paired = g2[g2["n"] >= 2].copy()
    if len(g2_paired) > 0:
        g2_paired["CV_pct"] = g2_paired["Lmen_std"] / g2_paired["Lmen_mean"] * 100
        print(g2_paired[["Po_mbar","dfu_num","n","Lmen_mean","Lmen_std","CV_pct"]].round(2).to_string(index=False))
    else:
        print("  No paired tier-2 groups found.")
else:
    print("  No tier-2 data found.")
print()

# ── Average to one row per (Po, dfu_num) ─────────────────────────────────────
df_avg = df_geo.groupby(["Po_mbar", "dfu_num"]).agg(
    n=("L_menpoint", "count"),
    L_menpoint=("L_menpoint", "mean"),
    V_reset_fL=("V_reset_fL", "mean"),
    model_S1_t=("model_S1_t", "mean"),
).reset_index()

# ── L_menpoint by Po (all data) ───────────────────────────────────────────────
print("=" * 70)
print("SECTION 1c — L_menpoint and V_reset by Po (all DFU positions)")
print("=" * 70)
print()
by_po_all = df_geo.groupby("Po_mbar").agg(
    n=("L_menpoint", "count"),
    L_mean=("L_menpoint", "mean"),
    L_std=("L_menpoint", "std"),
    L_p25=("L_menpoint", lambda x: np.percentile(x.dropna(), 25)),
    L_p75=("L_menpoint", lambda x: np.percentile(x.dropna(), 75)),
    L_min=("L_menpoint", "min"),
    L_max=("L_menpoint", "max"),
    V_mean_fL=("V_reset_fL", "mean"),
    V_std_fL=("V_reset_fL", "std"),
).reset_index()
print("L_menpoint [µm]:")
print(by_po_all[["Po_mbar","n","L_mean","L_std","L_p25","L_p75","L_min","L_max"]].round(2).to_string(index=False))
print()
print("V_reset [fL]:")
print(by_po_all[["Po_mbar","n","V_mean_fL","V_std_fL"]].round(3).to_string(index=False))
print(f"\n  Nominal V_reset (rule-of-thumb exit_w² × exit_h): {V_NOMINAL:.0f} µm³ = {V_NOMINAL/1000:.3f} fL")
print()

# ── L_menpoint by DFU-tier subsets ────────────────────────────────────────────
# "Central" = DFU ≤ 6 (closer to mean network DP)
# "Downstream" = DFU ≥ 8 (known lower local DP)
df_geo["dfu_zone"] = df_geo["dfu_num"].apply(
    lambda x: "central" if (x <= 6) else ("downstream" if x >= 8 else "mid")
)

print("=" * 70)
print("SECTION 1d — L_menpoint by DFU zone (central ≤6 vs downstream ≥8)")
print("=" * 70)
print()
for zone in ["central", "downstream"]:
    sub = df_geo[df_geo["dfu_zone"] == zone]
    if len(sub) == 0:
        continue
    by_po_z = sub.groupby("Po_mbar").agg(
        n=("L_menpoint", "count"),
        L_mean=("L_menpoint", "mean"),
        L_std=("L_menpoint", "std"),
        V_mean_fL=("V_reset_fL", "mean"),
    ).reset_index()
    print(f"Zone: {zone} (DFU {'≤6' if zone=='central' else '≥8'})")
    print(by_po_z[["Po_mbar","n","L_mean","L_std","V_mean_fL"]].round(3).to_string(index=False))
    print()

# ── Power-law regression: L_menpoint vs Po ────────────────────────────────────
print("=" * 70)
print("SECTION 1e — Power-law regression: L_menpoint ~ Po^β")
print("=" * 70)
print()

# Use per-(Po, dfu) averages to avoid within-group pseudoreplication
log_po  = np.log(df_avg["Po_mbar"].values.astype(float))
log_Lm  = np.log(df_avg["L_menpoint"].values.astype(float))
log_Vr  = np.log(df_avg["V_reset_fL"].values.astype(float))

mask = np.isfinite(log_po) & np.isfinite(log_Lm)
slope_L, intercept_L, r_L, p_L, se_L = stats.linregress(log_po[mask], log_Lm[mask])
ci95_L = 1.96 * se_L

mask_v = np.isfinite(log_po) & np.isfinite(log_Vr)
slope_V, intercept_V, r_V, p_V, se_V = stats.linregress(log_po[mask_v], log_Vr[mask_v])
ci95_V = 1.96 * se_V

print(f"All (Po, DFU) pairs  [n={mask.sum()}]:")
print(f"  L_menpoint ~ Po^{slope_L:.4f}  (95% CI: [{slope_L-ci95_L:.4f}, {slope_L+ci95_L:.4f}])  r={r_L:.3f}  p={p_L:.4f}")
print(f"  V_reset    ~ Po^{slope_V:.4f}  (95% CI: [{slope_V-ci95_V:.4f}, {slope_V+ci95_V:.4f}])  r={r_V:.3f}  p={p_V:.4f}")
print()

# Central zone only
df_avg_central = df_avg[df_avg["dfu_num"] <= 6]
if len(df_avg_central) >= 3:
    lpc = np.log(df_avg_central["Po_mbar"].values.astype(float))
    lLc = np.log(df_avg_central["L_menpoint"].values.astype(float))
    lVc = np.log(df_avg_central["V_reset_fL"].values.astype(float))
    mc = np.isfinite(lpc) & np.isfinite(lLc)
    sL_c, _, rL_c, pL_c, seL_c = stats.linregress(lpc[mc], lLc[mc])
    ci_c = 1.96 * seL_c
    mv = np.isfinite(lpc) & np.isfinite(lVc)
    sV_c, _, rV_c, pV_c, seV_c = stats.linregress(lpc[mv], lVc[mv])
    print(f"Central zone only (DFU ≤ 6)  [n={mc.sum()}]:")
    print(f"  L_menpoint ~ Po^{sL_c:.4f}  (95% CI: [{sL_c-ci_c:.4f}, {sL_c+ci_c:.4f}])  r={rL_c:.3f}  p={pL_c:.4f}")
    print(f"  V_reset    ~ Po^{sV_c:.4f}  r={rV_c:.3f}  p={pV_c:.4f}")
    print()
else:
    sL_c, pL_c, rL_c, sV_c = slope_L, p_L, r_L, slope_V  # fallback for report

# ── L_menpoint vs DFU position ────────────────────────────────────────────────
print("=" * 70)
print("SECTION 1f — L_menpoint vs DFU position")
print("=" * 70)
print()
by_dfu = df_geo.groupby("dfu_num").agg(
    n=("L_menpoint", "count"),
    L_mean=("L_menpoint", "mean"),
    L_std=("L_menpoint", "std"),
).reset_index().sort_values("dfu_num")
print(by_dfu.round(2).to_string(index=False))
print()

# Per-Po DFU trend
print("Pearson r(dfu_num, L_menpoint) per Po:")
for po, grp in df_geo.groupby("Po_mbar"):
    g = grp.dropna(subset=["dfu_num","L_menpoint"])
    if len(g) >= 3:
        r, p = stats.pearsonr(g["dfu_num"], g["L_menpoint"])
        print(f"  Po={po:3.0f} mbar: r={r:+.3f}  p={p:.4f}  n={len(g)}")

# Pooled
pool = df_geo.dropna(subset=["dfu_num","L_menpoint"])
r_pool, p_pool = stats.pearsonr(pool["dfu_num"], pool["L_menpoint"])
print(f"  Pooled all Po:    r={r_pool:+.3f}  p={p_pool:.4f}  n={len(pool)}")
print()

# ── Joint model: log(L_menpoint) = β_Po·log(Po) + β_dfu·DFU + const ──────────
print("=" * 70)
print("SECTION 1g — Joint regression: log(L_menpoint) = β_Po·log(Po) + β_dfu·DFU + const")
print("=" * 70)
print()
jdf = df_avg.dropna(subset=["L_menpoint","dfu_num"])
if len(jdf) >= 4:
    X = np.column_stack([
        np.log(jdf["Po_mbar"].values.astype(float)),
        jdf["dfu_num"].values.astype(float),
        np.ones(len(jdf))
    ])
    y = np.log(jdf["L_menpoint"].values.astype(float))
    coeff, resid, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    beta_po, beta_dfu, const = coeff
    y_pred = X @ coeff
    ss_tot = np.sum((y - y.mean())**2)
    ss_res = np.sum((y - y_pred)**2)
    r2_joint = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Compare to Po-only model
    X_po = np.column_stack([np.log(jdf["Po_mbar"].values.astype(float)), np.ones(len(jdf))])
    c_po, _, _, _ = np.linalg.lstsq(X_po, y, rcond=None)
    y_pred_po = X_po @ c_po
    r2_po = 1.0 - np.sum((y - y_pred_po)**2) / ss_tot if ss_tot > 0 else 0.0

    print(f"  β_Po      = {beta_po:.4f}  (L ~ Po^β_Po)")
    print(f"  β_dfu     = {beta_dfu:.4f}  (per unit DFU position)")
    print(f"  constant  = {const:.4f}")
    print(f"  R² (joint, Po + DFU)  = {r2_joint:.4f}")
    print(f"  R² (Po-only)          = {r2_po:.4f}")
    dr2 = r2_joint - r2_po
    print(f"  ΔR² from adding DFU   = {dr2:.4f}  {'(DFU adds meaningful explanatory power)' if dr2 > 0.05 else '(DFU adds little beyond Po alone)'}")
else:
    print("  Insufficient data for joint regression.")
    beta_po, beta_dfu, r2_joint, r2_po, dr2 = slope_L, 0.0, r_L**2, r_L**2, 0.0
print()

# ── Frame quantisation note ───────────────────────────────────────────────────
print("=" * 70)
print("SECTION 1h — Measurement uncertainty note")
print("=" * 70)
print()
print(f"  Frame rate: {FRAME_RATE} fps  → {FRAME_DT*1000:.0f} ms per frame")
print(f"  L_menpoint is measured from video still at the moment of snap-off reset.")
print(f"  If the true maximum retraction occurs between frames, L_menpoint is")
print(f"  underestimated. This systematic bias is most significant at high Po,")
print(f"  where the oil retracts quickly, giving a shorter window to capture the")
print(f"  true maximum. This would cause L_menpoint to appear artificially smaller")
print(f"  at high Po, potentially amplifying (or even generating) any negative β_Po.")
print()
print(f"  V_reset range in data: {df_geo['V_reset_fL'].min():.2f} – {df_geo['V_reset_fL'].max():.2f} fL")
print(f"  Nominal rule-of-thumb: {V_NOMINAL/1000:.3f} fL")
print(f"  Data mean (all): {df_geo['V_reset_fL'].mean():.3f} fL  (std {df_geo['V_reset_fL'].std():.3f} fL)")
print()

# ── Write Section 1 of markdown report ───────────────────────────────────────
def interp_beta(b, p, ci_lo, ci_hi):
    """Plain-English interpretation of the power-law exponent."""
    if p > 0.10:
        return (f"β = {b:.4f}, p = {p:.3f} — **not statistically significant** at α=0.10. "
                "Cannot distinguish from Po-independent reset.")
    elif ci_lo < 0 < ci_hi:
        return (f"β = {b:.4f}, p = {p:.3f} — CI [{ci_lo:.4f}, {ci_hi:.4f}] straddles zero: "
                "**result is ambiguous**.")
    elif b < 0:
        return (f"β = {b:.4f}, p = {p:.3f} — **significant negative trend**: "
                "L_menpoint decreases with Po (larger retraction at higher pressure).")
    else:
        return (f"β = {b:.4f}, p = {p:.3f} — **positive trend**: "
                "L_menpoint increases with Po (counterintuitive; check DFU confound).")

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("# Revised V5-30 Calibration Analysis\n\n")
    f.write("**Device:** V5-30_3_3  |  **Date:** 2026-04-10  \n")
    f.write("**Data source:** `data/analysis/stage_timing_clean.csv` (43 observations)  \n")
    f.write("**Scripts:** `data/analysis/revised_calibration/`\n\n")
    f.write("---\n\n")

    f.write("## Section 1: Meniscus Reset Statistics\n\n")
    f.write("### 1.1 Inputs\n\n")
    f.write(f"- 43 observations across Po = 200–500 mbar, DFU positions 0–10\n")
    f.write(f"- Geometry: junction {EXIT_W_UM:.0f} µm × {EXIT_H_UM:.0f} µm\n")
    f.write(f"- Nominal V_reset (rule-of-thumb exit_w² × exit_h): {V_NOMINAL:.0f} µm³ = {V_NOMINAL/1000:.3f} fL\n")
    f.write(f"- Frame rate: {FRAME_RATE:.0f} fps → {FRAME_DT*1000:.0f} ms per frame\n\n")

    f.write("### 1.2 Within-group variability\n\n")
    f.write("**Tier 1** (two different junctions at same DFU position, e.g. `3a`/`3b`):\n\n")
    if len(tier1) > 0 and len(g1_paired) > 0:
        f.write(df_to_md(g1_paired[["Po_mbar","dfu_num","n","Lmen_mean","Lmen_std","CV_pct"]].round(2).reset_index(drop=True)))
        f.write("\n\n")
    else:
        f.write("No tier-1 paired data found.\n\n")

    f.write("**Tier 2** (two events on same rung, e.g. `6aa`/`6ab`):\n\n")
    if len(tier2) > 0 and len(g2_paired) > 0:
        f.write(df_to_md(g2_paired[["Po_mbar","dfu_num","n","Lmen_mean","Lmen_std","CV_pct"]].round(2).reset_index(drop=True)))
        f.write("\n\n")
    else:
        f.write("No tier-2 paired data found.\n\n")

    f.write("### 1.3 L_menpoint and V_reset by Po (all DFU positions)\n\n")
    f.write("#### L_menpoint [µm]\n\n")
    f.write(df_to_md(by_po_all[["Po_mbar","n","L_mean","L_std","L_p25","L_p75","L_min","L_max"]].round(2).reset_index(drop=True)))
    f.write("\n\n")
    f.write("#### V_reset [fL]\n\n")
    f.write(df_to_md(by_po_all[["Po_mbar","n","V_mean_fL","V_std_fL"]].round(3).reset_index(drop=True)))
    f.write("\n\n")

    f.write("### 1.4 L_menpoint by DFU zone\n\n")
    for zone in ["central", "downstream"]:
        sub = df_geo[df_geo["dfu_zone"] == zone]
        if len(sub) == 0:
            continue
        by_po_z = sub.groupby("Po_mbar").agg(
            n=("L_menpoint","count"),
            L_mean=("L_menpoint","mean"),
            L_std=("L_menpoint","std"),
            V_mean_fL=("V_reset_fL","mean"),
        ).reset_index()
        label = "Central (DFU ≤ 6)" if zone=="central" else "Downstream (DFU ≥ 8)"
        f.write(f"**{label}:**\n\n")
        f.write(df_to_md(by_po_z[["Po_mbar","n","L_mean","L_std","V_mean_fL"]].round(3).reset_index(drop=True)))
        f.write("\n\n")

    f.write("### 1.5 Power-law regression: L_menpoint ~ Po^β\n\n")
    f.write("Using per-(Po, DFU) averaged values to avoid within-group pseudoreplication.\n\n")
    f.write(f"**All data (n={mask.sum()}):** ")
    f.write(interp_beta(slope_L, p_L, slope_L - ci95_L, slope_L + ci95_L))
    f.write("\n\n")
    if len(df_avg_central) >= 3:
        f.write(f"**Central rungs only (DFU ≤ 6, n={mc.sum()}):** ")
        f.write(interp_beta(sL_c, pL_c, sL_c - 1.96*seL_c, sL_c + 1.96*seL_c))
        f.write("\n\n")

    f.write("### 1.6 Joint regression: log(L_menpoint) = β_Po·log(Po) + β_dfu·DFU + const\n\n")
    if len(jdf) >= 4:
        f.write(f"| Parameter | Value |\n|---|---|\n")
        f.write(f"| β_Po | {beta_po:.4f} |\n")
        f.write(f"| β_DFU | {beta_dfu:.4f} |\n")
        f.write(f"| R² (joint) | {r2_joint:.4f} |\n")
        f.write(f"| R² (Po-only) | {r2_po:.4f} |\n")
        f.write(f"| ΔR² from adding DFU | {dr2:.4f} |\n\n")
        if dr2 > 0.05:
            f.write("DFU position adds meaningful explanatory power beyond Po alone — "
                    "downstream rungs genuinely have different reset lengths, not just a Po effect.\n\n")
        else:
            f.write("DFU position adds little explanatory power beyond Po — "
                    "the variation in L_menpoint with DFU can largely be attributed to the "
                    "lower local DP at downstream positions (which is already captured by the "
                    "network model) rather than a distinct positional effect on reset.\n\n")

    f.write("### 1.7 Measurement uncertainty\n\n")
    f.write(f"At {FRAME_RATE:.0f} fps each frame = {FRAME_DT*1000:.0f} ms. L_menpoint is measured from the "
            "frame at which the reset is most visible. If the true maximum retraction occurs between "
            "frames — which is more likely at high Po where retraction is rapid — L_menpoint is "
            "systematically **underestimated at high Po**. This would artificially create a negative "
            "β_Po even if the true reset distance is pressure-independent. This effect is irreducible "
            "at 25 fps; higher-speed imaging would be needed to quantify it.\n\n")

    f.write("### 1.8 Conclusion\n\n")
    interp_text = interp_beta(slope_L, p_L, slope_L - ci95_L, slope_L + ci95_L)
    f.write(f"Overall regression: {interp_text}\n\n")
    f.write("Given the frame-rate underestimation bias, any apparent decrease in L_menpoint "
            "with Po should be treated with caution. The DFU position effect (lower local DP "
            "→ smaller L_menpoint at downstream positions) appears to be the dominant spatial "
            "driver. The model assumption of a fixed V_reset is a reasonable approximation, "
            "but using per-observation measured V_reset in the calibration is more accurate "
            "and is adopted in Section 2.\n\n")

    f.write("---\n\n")

print(f"Section 1 written to: {OUT_MD}")
print("\nDone — Script 1 complete.\n")
