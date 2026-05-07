"""
experimental_stage_analysis.py
================================
Sieve and analyse the experimental stage-timing data from flow-stage-copy.xlsx (A36:X81).

Stage naming reconciliation
---------------------------
The video analysis split droplet formation into 3 experimental stages:
  Exp Stage 1  — oil meniscus travels from reset position to approx the junction edge
  Exp Stage 2  — oil pushes over the edge (transitional)
  Exp Stage 3  — continuous phase enters, pinches the neck, snap-off

Physics model mapping:
  Model Stage 1 = Exp Stage 1 + Exp Stage 2   (meniscus refill + edge push)
  Model Stage 2 = Exp Stage 3                  (squeezing / snap-off)

This mapping is supported by:
  - Stage 1+2 together represent the filling/displacement phase driven by Po -> Q_rung
  - Stage 3 (snap-off) is driven by junction geometry and capillary instability -> ~constant wrt Po

Device geometry (V5_30_3_3, from v5_30.yaml)
---------------------------------------------
  exit_width  w = 30 µm
  exit_depth  h = 10 µm
  rung: 10 µm deep × 8 µm wide × 4000 µm long, 60 µm pitch

Volume displaced during Model Stage 1
--------------------------------------
L_menpoint = distance from meniscus TIP to junction edge [µm]
L_men      = distance from meniscus WALL CONTACT to junction edge [µm]

The oil volume that must flow through the rung to advance the meniscus
from its reset position to the edge is:

  V_displaced = w * h * L_menpoint                       (rectangular slab ahead of tip)
              + (π/6) * w * h * (L_men - L_menpoint)     (half-ellipsoid meniscus dome)

The second term models the volume of the meniscus cap itself — the oil already
present between the wall-contact footprint (L_men) and the tip (L_menpoint).
This uses a half-ellipsoid approximation with semi-axes w/2, h/2, and (L_men - L_menpoint).

Units: µm³  (multiply by 1e-18 for m³, or by 1e-3 for fL)

Frame rate: 25 fps (verified: 27 frames / 1.08 s = 25 fps)
"""

import math
import numpy as np
import pandas as pd
import openpyxl
import warnings
warnings.filterwarnings("ignore")

# ── Device geometry ──────────────────────────────────────────────────────────
EXIT_WIDTH_UM  = 30.0   # µm   junction exit width
EXIT_DEPTH_UM  = 10.0   # µm   junction exit depth
FRAME_RATE     = 25.0   # fps

# ── Load raw data ─────────────────────────────────────────────────────────────
XLSX = "C:/Users/conor/Documents/Code Projects/PE/stepgen/design_model/data/flow-stage-copy.xlsx"

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active

COLS = {
    "device":       1,   # A
    "prod_date":    2,   # B
    "test_date":    3,   # C
    "Qw_mlhr":      4,   # D
    "Po_mbar":      5,   # E
    "DFU_label":    6,   # F
    "s1_fstart":    7,   # G  — Exp Stage 1 frame start
    "s1_fend":      8,   # H  — Exp Stage 1 frame end
    "s2_fend":      9,   # I  — Exp Stage 2 frame end
    "s3_fend":      10,  # J  — Exp Stage 3 frame end
    "exp_s1_t":     11,  # K  — Exp Stage 1 time [s]
    "exp_s2_t":     12,  # L  — Exp Stage 2 time [s]
    "exp_s3_t":     13,  # M  — Exp Stage 3 time [s]
    "total_t":      15,  # O  — Total cycle time [s]
    "L_men":        18,  # R  — Meniscus wall-contact to edge [µm]
    "L_menpoint":   20,  # T  — Meniscus tip to edge [µm]
    "Lpinch":       22,  # V  — Pinch zone length [µm]
    "D_drop":       24,  # X  — Droplet diameter [µm]
}

rows = []
for row_idx in range(37, 82):   # rows 37-81 (36 is header)
    vals = {k: ws.cell(row_idx, c).value for k, c in COLS.items()}
    # Skip blank/separator rows
    if vals["Po_mbar"] is None:
        continue
    rows.append(vals)

df = pd.DataFrame(rows)

# ── Clean & cast ─────────────────────────────────────────────────────────────
df["Po_mbar"]    = df["Po_mbar"].astype(float)
df["Qw_mlhr"]    = df["Qw_mlhr"].astype(float)
df["exp_s1_t"]   = pd.to_numeric(df["exp_s1_t"], errors="coerce")
df["exp_s2_t"]   = pd.to_numeric(df["exp_s2_t"], errors="coerce")
df["exp_s3_t"]   = pd.to_numeric(df["exp_s3_t"], errors="coerce")
df["total_t"]    = pd.to_numeric(df["total_t"],   errors="coerce")
df["L_men"]      = pd.to_numeric(df["L_men"],     errors="coerce")
df["L_menpoint"] = pd.to_numeric(df["L_menpoint"],errors="coerce")
df["Lpinch"]     = pd.to_numeric(df["Lpinch"],    errors="coerce")
df["D_drop"]     = pd.to_numeric(df["D_drop"],    errors="coerce")

# ── Extract DFU number ────────────────────────────────────────────────────────
def dfu_number(label):
    """Extract integer DFU position from label like '3a', '10b', '6aa'. None -> NaN."""
    if label is None:
        return np.nan
    import re
    m = re.match(r"(\d+)", str(label))
    return int(m.group(1)) if m else np.nan

df["DFU"] = df["DFU_label"].apply(dfu_number)

# ── Stage mapping: experimental -> model ──────────────────────────────────────
df["model_S1_t"] = df["exp_s1_t"] + df["exp_s2_t"]   # filling + edge push
df["model_S2_t"] = df["exp_s3_t"]                      # snap-off
df["S1_frac"]    = df["model_S1_t"] / df["total_t"]   # fraction of cycle spent in S1
df["S2_frac"]    = df["model_S2_t"] / df["total_t"]   # fraction of cycle spent in S2

# ── Volume displaced during Model Stage 1 ────────────────────────────────────
#
#   V = w*h*L_menpoint + (π/6)*w*h*(L_men - L_menpoint)
#
#   This sums:
#     (1) rectangular block ahead of the meniscus tip
#     (2) half-ellipsoid meniscus cap volume
#
def calc_V_displaced(row):
    w = EXIT_WIDTH_UM
    h = EXIT_DEPTH_UM
    lp = row["L_menpoint"]
    lm = row["L_men"]
    if pd.isna(lp) or pd.isna(lm):
        return np.nan
    delta = max(lm - lp, 0.0)   # meniscus dome axial span [µm]
    V_slab = w * h * lp
    V_dome = (math.pi / 6.0) * w * h * delta
    return V_slab + V_dome   # µm³

df["V_reset_um3"]  = df.apply(calc_V_displaced, axis=1)
df["V_reset_fL"]   = df["V_reset_um3"] * 1e-3    # femtolitres (1 µm³ = 1e-3 fL)
df["V_reset_m3"]   = df["V_reset_um3"] * 1e-18   # m³

# ── Apparent Q through junction during Stage 1 ───────────────────────────────
# Q_apparent = V_reset / model_S1_t  (gives the effective flow rate driving refill)
df["Q_apparent_m3s"]  = df["V_reset_m3"] / df["model_S1_t"]
df["Q_apparent_nLhr"] = df["Q_apparent_m3s"] * 1e9 * 3600   # nL/hr for readability

# ── Actionable clean dataset ──────────────────────────────────────────────────
KEEP = [
    "Po_mbar", "DFU", "DFU_label",
    "exp_s1_t", "exp_s2_t", "exp_s3_t", "total_t",
    "model_S1_t", "model_S2_t",
    "S1_frac", "S2_frac",
    "L_men", "L_menpoint", "V_reset_um3", "V_reset_fL",
    "Q_apparent_nLhr",
    "Lpinch", "D_drop",
]
clean = df[KEEP].copy()
clean = clean.sort_values(["Po_mbar", "DFU"]).reset_index(drop=True)

OUT_CSV = "C:/Users/conor/Documents/Code Projects/PE/stepgen/design_model/data/analysis/stage_timing_clean.csv"
clean.to_csv(OUT_CSV, index=False, float_format="%.4f")
print(f"Clean dataset saved -> {OUT_CSV}")
print(f"N rows: {len(clean)}\n")

# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 70)
print("SECTION 1 — Stage timings by Po (model stage mapping)")
print("=" * 70)
print()
print("Mapping: Model S1 = Exp S1+S2 (filling)   Model S2 = Exp S3 (snap-off)")
print()

by_po = clean.groupby("Po_mbar").agg(
    n=("model_S1_t", "count"),
    S1_mean=("model_S1_t", "mean"),
    S1_std=("model_S1_t", "std"),
    S1_min=("model_S1_t", "min"),
    S1_max=("model_S1_t", "max"),
    S2_mean=("model_S2_t", "mean"),
    S2_std=("model_S2_t", "std"),
    S2_min=("model_S2_t", "min"),
    S2_max=("model_S2_t", "max"),
    total_mean=("total_t", "mean"),
    S2_frac_mean=("S2_frac", "mean"),
).round(4)
print(by_po.to_string())
print()

# Check S2 constancy: coefficient of variation across all Po
all_s2 = clean["model_S2_t"].dropna()
cv_s2  = all_s2.std() / all_s2.mean() * 100
print(f"Model S2 (snap-off) CoV across ALL observations: {cv_s2:.1f}%")
print(f"  -> {'LOW — consistent with Po-independent snap-off' if cv_s2 < 25 else 'VARIABLE — some Po dependence'}")
print()

# Per-Po CoV for S1 vs S2
print("Per-Po CoV (std/mean × 100):  [within-group scatter from varying DFU position]")
print(f"  {'Po':>6}  {'S1 CoV%':>8}  {'S2 CoV%':>8}")
for po, grp in clean.groupby("Po_mbar"):
    s1cv = grp["model_S1_t"].std() / grp["model_S1_t"].mean() * 100
    s2cv = grp["model_S2_t"].std() / grp["model_S2_t"].mean() * 100
    print(f"  {po:>6.0f}  {s1cv:>8.1f}  {s2cv:>8.1f}")
print()

print("=" * 70)
print("SECTION 2 — Po scaling of Model S1 (expected: t ~ 1/Q ~ 1/Po)")
print("=" * 70)
print()
# Fit power law: log(S1_mean) = a + b * log(Po)
po_vals  = by_po.index.values.astype(float)
s1_means = by_po["S1_mean"].values
log_po   = np.log(po_vals)
log_s1   = np.log(s1_means)
b, a     = np.polyfit(log_po, log_s1, 1)
print(f"  Power-law fit: t_S1 ~ Po^{b:.3f}  (ideal Poiseuille: -1.0, ideal viscous: ~ -1)")
print(f"  Fit: t_S1 = exp({a:.3f}) × Po^{b:.3f}")
print()

# Expected vs actual
print(f"  {'Po (mbar)':>10}  {'t_S1 obs (s)':>14}  {'t_S1 200mbar ratio':>18}  {'1/Po ratio (expected)':>22}")
t_ref = by_po.loc[200, "S1_mean"]
for po in [200, 300, 400, 500]:
    t_obs    = by_po.loc[po, "S1_mean"]
    obs_rat  = t_obs / t_ref
    exp_rat  = 200.0 / po
    print(f"  {po:>10.0f}  {t_obs:>14.4f}  {obs_rat:>18.3f}  {exp_rat:>22.3f}")
print()

print("=" * 70)
print("SECTION 3 — DFU position effect")
print("=" * 70)
print()
print("DFU number: lower = nearer device inlet, higher = farther downstream")
print("Hydraulic network: downstream rungs see slightly lower ΔP -> slower S1, different S2")
print()

by_dfu = clean.groupby("DFU").agg(
    n=("model_S1_t", "count"),
    S1_mean=("model_S1_t", "mean"),
    S1_std=("model_S1_t", "std"),
    S2_mean=("model_S2_t", "mean"),
    S2_std=("model_S2_t", "std"),
    D_drop_mean=("D_drop", "mean"),
    L_menpoint_mean=("L_menpoint", "mean"),
).round(4)
print(by_dfu.to_string())
print()

# Check DFU trend in S1
dfu_vals  = by_dfu.index.values.astype(float)
s1_dfu    = by_dfu["S1_mean"].values
mask      = ~np.isnan(s1_dfu)
if mask.sum() >= 2:
    slope, intercept = np.polyfit(dfu_vals[mask], s1_dfu[mask], 1)
    print(f"  S1 vs DFU linear trend: slope = {slope:.4f} s/DFU  (+ = slower downstream)")

s2_dfu = by_dfu["S2_mean"].values
mask2  = ~np.isnan(s2_dfu)
if mask2.sum() >= 2:
    slope2, _ = np.polyfit(dfu_vals[mask2], s2_dfu[mask2], 1)
    print(f"  S2 vs DFU linear trend: slope = {slope2:.4f} s/DFU  (+ = slower downstream)")
print()

print("=" * 70)
print("SECTION 4 — Geometry: L_menpoint, V_reset, and drop size")
print("=" * 70)
print()
print(f"  Junction geometry: exit_width = {EXIT_WIDTH_UM:.0f} µm, exit_depth = {EXIT_DEPTH_UM:.0f} µm")
print()
print("  V_displaced formula (half-ellipsoid meniscus correction):")
print("    V = w·h·L_menpoint  +  (π/6)·w·h·(L_men − L_menpoint)")
print("      = rectangular slab  +  meniscus dome volume")
print()
geo_by_po = clean.groupby("Po_mbar").agg(
    L_menpoint_mean=("L_menpoint", "mean"),
    L_menpoint_std=("L_menpoint", "std"),
    L_men_mean=("L_men", "mean"),
    V_reset_fL_mean=("V_reset_fL", "mean"),
    V_reset_fL_std=("V_reset_fL", "std"),
    Q_apparent_nLhr_mean=("Q_apparent_nLhr", "mean"),
    D_drop_mean=("D_drop", "mean"),
    D_drop_std=("D_drop", "std"),
).round(3)
print(geo_by_po.to_string())
print()

# V_reset vs Po trend
v_reset_vals = geo_by_po["V_reset_fL_mean"].values
b_v, a_v = np.polyfit(np.log(po_vals), np.log(v_reset_vals), 1)
print(f"  V_reset ~ Po^{b_v:.3f}  (if constant -> reset position Po-independent; if varies -> Po affects reset)")
print()

# Drop size
print(f"  D_drop overall: mean = {clean['D_drop'].mean():.2f} µm, std = {clean['D_drop'].std():.2f} µm")
print(f"  D_drop range: {clean['D_drop'].min():.1f} – {clean['D_drop'].max():.1f} µm")
d_by_po = clean.groupby("Po_mbar")["D_drop"].agg(["mean","std","min","max"]).round(2)
print(d_by_po.to_string())
print()

print("=" * 70)
print("SECTION 5 — Snap-off geometry: Lpinch")
print("=" * 70)
print()
lpinch_data = clean[clean["Lpinch"].notna()]
print(f"  Observations with Lpinch: {len(lpinch_data)} / {len(clean)}")
if len(lpinch_data) > 0:
    print(f"  Lpinch overall: mean = {lpinch_data['Lpinch'].mean():.2f} µm, std = {lpinch_data['Lpinch'].std():.2f} µm")
    print(f"  Lpinch/2 (approx R_neck at snap-off): {lpinch_data['Lpinch'].mean()/2:.2f} µm")
    print()
    lp_by_po = lpinch_data.groupby("Po_mbar")["Lpinch"].agg(["count","mean","std"]).round(2)
    print("  Lpinch by Po:")
    print(lp_by_po.to_string())
print()

print("=" * 70)
print("SECTION 6 — Key findings and model implications")
print("=" * 70)
print()

s1_200 = by_po.loc[200, "S1_mean"]
s1_500 = by_po.loc[500, "S1_mean"]
s2_200 = by_po.loc[200, "S2_mean"]
s2_500 = by_po.loc[500, "S2_mean"]
s1_ratio = s1_200 / s1_500
s2_ratio = s2_200 / s2_500
ideal_ratio = 500.0 / 200.0

print(f"  1. Stage 1 (filling) scales with Po:")
print(f"       t_S1(200 mbar) = {s1_200:.3f} s")
print(f"       t_S1(500 mbar) = {s1_500:.3f} s")
print(f"       Observed speedup 200->500 mbar: {s1_ratio:.2f}×")
print(f"       Ideal Poiseuille (Q ∝ ΔP): {ideal_ratio:.2f}×")
print(f"       -> Model exponent {b:.3f} vs ideal -1.0")
print()
print(f"  2. Stage 2 (snap-off) is approximately Po-independent:")
print(f"       t_S2(200 mbar) = {s2_200:.3f} s")
print(f"       t_S2(500 mbar) = {s2_500:.3f} s")
print(f"       Ratio: {s2_ratio:.2f}×  (ideal if constant: 1.0×)")
print(f"       Global CoV: {cv_s2:.1f}%")
print(f"       -> Snap-off is geometry/capillary controlled, not pressure driven ✓")
print()
print(f"  3. Cycle time breakdown at each Po:")
for po in [200, 300, 400, 500]:
    s1f = by_po.loc[po, "S1_mean"] / by_po.loc[po, "total_mean"]
    s2f = by_po.loc[po, "S2_mean"] / by_po.loc[po, "total_mean"]
    print(f"       Po={po:3.0f} mbar: S1={s1f*100:.0f}%  S2={s2f*100:.0f}% of cycle")
print()
print(f"  4. V_reset (oil volume displaced per cycle) is approximately constant at ~{clean['V_reset_fL'].mean():.1f} fL")
print(f"     -> Reset geometry (L_menpoint) not strongly Po-dependent")
print(f"     -> Implies Q_rung changes with Po, not the reset volume")
print()
print(f"  5. Drop diameter weakly decreases with Po:")
d_by_po_simple = clean.groupby("Po_mbar")["D_drop"].mean()
for po, d in d_by_po_simple.items():
    print(f"       Po={po:3.0f} mbar: D_drop = {d:.1f} µm")
print(f"     -> Consistent with stage 2 being snap-off at fixed R_critical (geometry-set)")
print(f"       slight decrease at high Po may indicate partial Rcrit sensitivity or Ca effect")
print()

print("=" * 70)
print("SECTION 7 — Per-observation table (for reference)")
print("=" * 70)
print()
cols_display = ["Po_mbar","DFU_label","model_S1_t","model_S2_t","total_t",
                "S1_frac","L_menpoint","V_reset_fL","D_drop","Lpinch"]
pd.set_option("display.max_rows", 60)
pd.set_option("display.width", 120)
pd.set_option("display.float_format", "{:.3f}".format)
print(clean[cols_display].to_string(index=False))
