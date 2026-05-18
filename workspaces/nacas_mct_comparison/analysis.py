"""
nacas_mct_analysis.py
=====================
Comparative analysis: 2.5% NaCas/MCT (new system) vs SDS/SO (control).
Device V5-8-1, junction 30 µm wide × 10 µm deep.

Run from project root:
  .venv/Scripts/python.exe analysis/nacas_mct_analysis.py
"""

import os
import re
import sys
import math
import textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(SCRIPT_DIR, "stage_timings.csv")
FIG_DIR    = os.path.join(SCRIPT_DIR, "figures")
REPORT_OUT = os.path.join(SCRIPT_DIR, "nacas_mct_report.md")
os.makedirs(FIG_DIR, exist_ok=True)

# ── Device geometry ───────────────────────────────────────────────────────────
W_UM = 30.0
H_UM = 10.0

# ── Style ─────────────────────────────────────────────────────────────────────
DPI = 150

# System colours: SDS=blue family, NaCas5=orange-red family, NaCas1=green family
SDS_COLORS  = {200: "#1f4e79", 300: "#2e75b6", 400: "#5ba3d9", 600: "#9fc5e8"}
NC5_COLORS  = {200: "#7f2c2c", 300: "#c0392b", 400: "#e67e22"}
NC1_COLORS  = {100: "#1a5c1a", 150: "#27ae60"}

SERIES_COLOR = {
    "SDS/SO 5ml/hr":      "#2e75b6",
    "NaCas/MCT 5ml/hr":   "#c0392b",
    "NaCas/MCT 1ml/hr":   "#27ae60",
}

ALL_SYSTEMS = ["SDS/SO 5ml/hr", "NaCas/MCT 5ml/hr", "NaCas/MCT 1ml/hr"]

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "legend.fontsize": 8.5, "xtick.labelsize": 9, "ytick.labelsize": 9,
})

# Stage breakdown colours (shared by Fig 2 and Fig 3)
S1_COLOR = "#4e79a7"
S2_COLOR = "#f28e2b"
S3_COLOR = "#e15759"

# ── Stats accumulator for report ──────────────────────────────────────────────
R = {}   # populated as we go

# =============================================================================
# 1. LOAD & FILTER
# =============================================================================
print(f"Loading: {CSV_PATH}")
raw = pd.read_csv(CSV_PATH)
print(f"  {len(raw)} total rows")

mask_sds = (raw["ContPhase"] == "SDS") & (raw["DispPhase"] == "SO") & (raw["ContPhaseFlow"] == 5)
mask_nc5 = (raw["ContPhase"] == "2-5NaCas") & (raw["DispPhase"] == "MCT") & (raw["ContPhaseFlow"] == 5)
mask_nc1 = (raw["ContPhase"] == "2-5NaCas") & (raw["DispPhase"] == "MCT") & (raw["ContPhaseFlow"] == 1)
df = raw[mask_sds | mask_nc5 | mask_nc1].copy()
print(f"  {len(df)} rows after scope filter")

R["n_sds"]  = int(mask_sds.sum())
R["n_nc5"]  = int(mask_nc5.sum())
R["n_nc1"]  = int(mask_nc1.sum())

def make_series(row):
    if row["ContPhase"] == "SDS":
        return "SDS/SO 5ml/hr"
    return "NaCas/MCT 5ml/hr" if row["ContPhaseFlow"] == 5 else "NaCas/MCT 1ml/hr"

df["Series"] = df.apply(make_series, axis=1)

# =============================================================================
# 2. PARSE DFU & FLAG SPECIAL ENTRIES
# =============================================================================
def parse_dfu(loc):
    if pd.isna(loc):
        return np.nan
    m = re.match(r"^(\d+)", str(loc).strip())
    return int(m.group(1)) if m else np.nan

def is_flagged(loc):
    return bool(pd.notna(loc) and
                any(k in str(loc) for k in ("justbefor", "lastdfu", "wetting")))

df["DFU_num"]     = df["Location"].apply(parse_dfu)
df["dfu_flagged"] = df["Location"].apply(is_flagged)

# =============================================================================
# 3. DERIVED QUANTITIES
# =============================================================================
df["total_t"] = df[["Stage1_s", "Stage2_s", "Stage3_s"]].sum(axis=1, skipna=False)
df["freq_Hz"] = np.where(df["total_t"] > 0, 1.0 / df["total_t"], np.nan)

def calc_vreset(row):
    lp, lm = row["L_menpoint_um"], row["L_men_um"]
    if pd.isna(lp) or pd.isna(lm):
        return np.nan
    delta = max(lm - lp, 0.0)
    return W_UM * H_UM * lp + (math.pi / 6.0) * W_UM * H_UM * delta

df["V_reset_um3"] = df.apply(calc_vreset, axis=1)
df["V_reset_fL"]  = df["V_reset_um3"] * 1e-3
df["dome_um"]     = df["L_men_um"] - df["L_menpoint_um"]
df["shape_ratio"] = df["dome_um"] / df["L_menpoint_um"]   # dome / tip-to-junction; ~0.5 = hemispherical

# =============================================================================
# 4. TWO-STEP AVERAGING
# =============================================================================
METRICS = ["Stage1_s", "Stage2_s", "Stage3_s", "total_t", "freq_Hz",
           "L_menpoint_um", "L_men_um", "V_reset_fL", "dome_um",
           "shape_ratio", "Droplet_diameter_um"]

GRP_ROI  = ["Series", "ContPhaseFlow", "DispPhasePressure",
            "DFU_num", "ROI_ID", "dfu_flagged"]
GRP_DFU  = ["Series", "ContPhaseFlow", "DispPhasePressure",
            "DFU_num", "dfu_flagged"]
GRP_COND = ["Series", "ContPhaseFlow", "DispPhasePressure"]

# Step 1: per-ROI mean (drop rows with no Stage1)
valid    = df.dropna(subset=["Stage1_s", "DFU_num"]).copy()
roi_avg  = valid.groupby(GRP_ROI, dropna=False)[METRICS].mean().reset_index()

# Step 2: per-DFU mean across ROIs
dfu_agg = roi_avg.groupby(GRP_DFU, dropna=False)[METRICS].agg(["mean", "std"]).reset_index()
dfu_agg.columns = ["_".join(c).rstrip("_") if isinstance(c, tuple) else c
                   for c in dfu_agg.columns]

# Convenience: unflagged DFU data
dfu_ok = dfu_agg[~dfu_agg["dfu_flagged"]].copy()

# Per-condition summary (mean ± std across DFUs, unflagged only)
def cond_stats(m):
    grp = dfu_ok.groupby(GRP_COND)[f"{m}_mean"]
    return grp.mean().rename(m), grp.std().rename(f"{m}_std")

cond_rows = {}
for ser in ALL_SYSTEMS:
    sub = dfu_ok[dfu_ok["Series"] == ser]
    for _, row in sub.groupby(GRP_COND):
        pass

cond_mean = dfu_ok.groupby(GRP_COND)[[f"{m}_mean" for m in METRICS]].mean().reset_index()
cond_std  = dfu_ok.groupby(GRP_COND)[[f"{m}_mean" for m in METRICS]].std().reset_index()
cond_mean.columns = [c.replace("_mean", "") if c.endswith("_mean") else c
                     for c in cond_mean.columns]
cond_std.columns  = [c.replace("_mean", "_std") if c.endswith("_mean") else c
                     for c in cond_std.columns]
cond = cond_mean.merge(cond_std, on=GRP_COND, how="left")

print("\nPer-condition summary (mean across DFUs):")
print(cond[["Series","DispPhasePressure","Stage1_s","Stage2_s","Stage3_s",
            "total_t","freq_Hz","Droplet_diameter_um"]].to_string(index=False))

# Helper: get cond row safely
def get_cond(series, po):
    row = cond[(cond["Series"] == series) & (cond["DispPhasePressure"] == po)]
    return row.iloc[0] if len(row) else None

# Helper: DFU data for a given series + Po
def get_dfu(series, po, flagged=False):
    mask = ((dfu_agg["Series"] == series) &
            (dfu_agg["DispPhasePressure"] == po) &
            (dfu_agg["dfu_flagged"] == flagged))
    return dfu_agg[mask].sort_values("DFU_num")

# =============================================================================
# 5. FIGURE 1 — Stage timing by stage (3 panels)
# =============================================================================
print("\nFigure 1 — stage timing...")

fig, axes = plt.subplots(1, 3, figsize=(14, 5))
stage_cols = ["Stage1_s", "Stage2_s", "Stage3_s"]
stage_labels = ["Stage 1 (hydraulic fill)", "Stage 2 (edge transition)", "Stage 3 (snap-off)"]

rng = np.random.default_rng(42)

for ax, scol, stitle in zip(axes, stage_cols, stage_labels):
    # SDS/SO 5mlhr
    for po, col in SDS_COLORS.items():
        pts = get_dfu("SDS/SO 5ml/hr", po)
        if len(pts) == 0:
            continue
        vals = pts[f"{scol}_mean"].dropna().values
        jx   = po + rng.uniform(-8, 8, len(vals))
        ax.scatter(jx, vals, color=col, s=22, alpha=0.7, zorder=4, edgecolors="none")
    # means connected
    po_sds = sorted(SDS_COLORS.keys())
    mn_sds = [get_cond("SDS/SO 5ml/hr", p) for p in po_sds]
    mn_sds = [(p, r[scol]) for p, r in zip(po_sds, mn_sds) if r is not None and not pd.isna(r[scol])]
    if mn_sds:
        ax.plot([p for p, _ in mn_sds], [v for _, v in mn_sds],
                "-o", color=SDS_COLORS[300], lw=1.8, ms=6, zorder=5)

    # NaCas/MCT 5mlhr
    for po, col in NC5_COLORS.items():
        pts = get_dfu("NaCas/MCT 5ml/hr", po)
        if len(pts) == 0:
            continue
        vals = pts[f"{scol}_mean"].dropna().values
        jx   = po + rng.uniform(-8, 8, len(vals))
        ax.scatter(jx, vals, color=col, s=22, alpha=0.7, zorder=4,
                   edgecolors="none", marker="s")
    po_nc5 = [300, 400]
    mn_nc5 = [get_cond("NaCas/MCT 5ml/hr", p) for p in po_nc5]
    mn_nc5 = [(p, r[scol]) for p, r in zip(po_nc5, mn_nc5) if r is not None and not pd.isna(r[scol])]
    if mn_nc5:
        ax.plot([p for p, _ in mn_nc5], [v for _, v in mn_nc5],
                "-s", color=NC5_COLORS[300], lw=1.8, ms=6, zorder=5)

    ax.set_xlabel("Oil inlet pressure Po [mbar]")
    ax.set_ylabel("Time [s]")
    ax.set_title(stitle)
    ax.set_xticks([200, 300, 400, 600])
    ax.set_ylim(bottom=0)

# Legend
handles = [
    Line2D([0],[0], color=SDS_COLORS[300], lw=2, marker="o", ms=6,
           label="SDS/SO 5 ml/hr"),
    Line2D([0],[0], color=NC5_COLORS[300], lw=2, marker="s", ms=6,
           label="NaCas/MCT 5 ml/hr"),
]
axes[0].legend(handles=handles, fontsize=8.5)
axes[0].annotate("No formation\n(200 mbar)", xy=(200, 0), xytext=(200, axes[0].get_ylim()[1]*0.05),
                  fontsize=7.5, ha="center", color=NC5_COLORS[200], style="italic")

fig.suptitle("Stage timing by stage — SDS/SO vs NaCas/MCT (5 ml/hr)", fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_01_stage_timing.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_01 saved")

# =============================================================================
# 6. FIGURE 2 — Cycle time (left) + absolute stage breakdown bars (right)
# =============================================================================
print("Figure 2 — cycle time and stage breakdown...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
rng2 = np.random.default_rng(7)

# LEFT: total cycle time vs Po (scatter + mean line)
for system, mcolors, marker in [
    ("SDS/SO 5ml/hr",    SDS_COLORS,  "o"),
    ("NaCas/MCT 5ml/hr", NC5_COLORS,  "s"),
    ("NaCas/MCT 1ml/hr", NC1_COLORS,  "^"),
]:
    po_order = sorted(mcolors.keys())
    mn_t, po_vals = [], []
    for po in po_order:
        c = get_cond(system, po)
        if c is None or pd.isna(c["total_t"]):
            continue
        pts  = get_dfu(system, po)
        vals = pts["total_t_mean"].dropna().values
        jx   = po + rng2.uniform(-8, 8, len(vals))
        ax1.scatter(jx, vals, color=mcolors[po], s=20, alpha=0.65,
                    zorder=4, edgecolors="none", marker=marker)
        mn_t.append(c["total_t"]); po_vals.append(po)
    if po_vals:
        base_col = list(mcolors.values())[min(1, len(mcolors) - 1)]
        ax1.plot(po_vals, mn_t, f"-{marker}", color=base_col, lw=2, ms=7, zorder=5,
                 label=system)

ax1.set_xlabel("Oil inlet pressure Po [mbar]")
ax1.set_ylabel("Total cycle time [s]")
ax1.set_title("Total cycle time vs pressure")
ax1.legend(fontsize=8.5)
ax1.set_ylim(bottom=0)
ax1.annotate("NaCas/MCT\n200 mbar:\nno formation", xy=(200, 0.02),
             xytext=(225, 1.2),
             arrowprops=dict(arrowstyle="->", color="grey"),
             fontsize=7.5, color="grey", ha="left")

# RIGHT: stacked absolute-time bars (S1, S2, S3) per condition
bar_specs2 = (
    [("SDS/SO 5ml/hr",    po) for po in [200, 300, 400, 600]] +
    [("NaCas/MCT 5ml/hr", po) for po in [200, 300, 400]] +
    [("NaCas/MCT 1ml/hr", po) for po in [100, 150]]
)
labels2, s1v, s2v, s3v = [], [], [], []
for sys_name, po in bar_specs2:
    c = get_cond(sys_name, po)
    labels2.append(f"{sys_name.split()[0]}\n{po}mb")
    if c is None or pd.isna(c["total_t"]) or c["total_t"] <= 0:
        s1v.append(0); s2v.append(0); s3v.append(0)
    else:
        s1v.append(c["Stage1_s"]); s2v.append(c["Stage2_s"]); s3v.append(c["Stage3_s"])

x2 = np.arange(len(labels2))
w2 = 0.55
ax2.bar(x2, s1v, width=w2, color=S1_COLOR, alpha=0.88, label="Stage 1 (fill)")
ax2.bar(x2, s2v, width=w2, bottom=s1v, color=S2_COLOR, alpha=0.88, label="Stage 2 (edge)")
ax2.bar(x2, s3v, width=w2, bottom=[a+b for a,b in zip(s1v, s2v)],
        color=S3_COLOR, alpha=0.88, label="Stage 3 (snap-off)")

ymax2 = max((a+b+c for a,b,c in zip(s1v, s2v, s3v)), default=1) * 1.18
ax2.axvline(3.5, color="black", lw=0.8, ls="--", alpha=0.4)
ax2.axvline(6.5, color="black", lw=0.8, ls="--", alpha=0.4)
ax2.text(1.75, ymax2*0.97, "SDS/SO 5 ml/hr",    ha="center", fontsize=8, color=SDS_COLORS[300])
ax2.text(5.0,  ymax2*0.97, "NaCas/MCT 5 ml/hr", ha="center", fontsize=8, color=NC5_COLORS[300])
ax2.text(8.25, ymax2*0.97, "NaCas/MCT 1 ml/hr", ha="center", fontsize=8, color=NC1_COLORS[150])
ax2.set_xticks(x2); ax2.set_xticklabels(labels2, fontsize=8)
ax2.set_ylim(0, ymax2)
ax2.set_ylabel("Absolute time [s]")
ax2.set_title("Stage duration breakdown by condition\n(shows which stages drive the NaCas speed advantage)")
ax2.legend(fontsize=8.5, loc="upper right")

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_02_cycle_freq.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_02 saved")

# =============================================================================
# 7. FIGURE 3 — Stage fractions (100% stacked bar)
# =============================================================================
print("Figure 3 — stage fractions...")

# Build ordered list of bars
bar_specs = []
for po in [200, 300, 400, 600]:
    bar_specs.append(("SDS/SO 5ml/hr", po, SDS_COLORS.get(po, "grey")))
for po in [200, 300, 400]:
    bar_specs.append(("NaCas/MCT 5ml/hr", po, NC5_COLORS.get(po, "grey")))
for po in [100, 150]:
    bar_specs.append(("NaCas/MCT 1ml/hr", po, NC1_COLORS.get(po, "grey")))

labels, s1f, s2f, s3f = [], [], [], []
for sys_name, po, _ in bar_specs:
    c = get_cond(sys_name, po)
    short = f"{sys_name.split()[0]}\n{po}mb"
    labels.append(short)
    if c is None or pd.isna(c["total_t"]) or c["total_t"] <= 0:
        s1f.append(0); s2f.append(0); s3f.append(0)
    else:
        s1f.append(c["Stage1_s"] / c["total_t"] * 100)
        s2f.append(c["Stage2_s"] / c["total_t"] * 100)
        s3f.append(c["Stage3_s"] / c["total_t"] * 100)

x = np.arange(len(labels))
w = 0.6

fig, ax = plt.subplots(figsize=(13, 5))
b1 = ax.bar(x, s1f, width=w, color=S1_COLOR, alpha=0.88, label="Stage 1 (fill)")
b2 = ax.bar(x, s2f, width=w, bottom=s1f, color=S2_COLOR, alpha=0.88, label="Stage 2 (edge)")
b3 = ax.bar(x, s3f, width=w,
            bottom=[a+b for a,b in zip(s1f,s2f)], color=S3_COLOR, alpha=0.88,
            label="Stage 3 (snap-off)")

for i, (f1, f2, f3) in enumerate(zip(s1f, s2f, s3f)):
    total = f1+f2+f3
    if total < 1:
        ax.text(i, 50, "No data", ha="center", va="center", fontsize=7, color="grey",
                style="italic", rotation=90)
        continue
    if f1 > 8:
        ax.text(i, f1/2, f"{f1:.0f}%", ha="center", va="center",
                fontsize=7.5, color="white", fontweight="bold")
    if f2 > 5:
        ax.text(i, f1+f2/2, f"{f2:.0f}%", ha="center", va="center",
                fontsize=7.5, color="white", fontweight="bold")
    if f3 > 5:
        ax.text(i, f1+f2+f3/2, f"{f3:.0f}%", ha="center", va="center",
                fontsize=7.5, color="white", fontweight="bold")

# Vertical dividers between systems
ax.axvline(3.5, color="black", lw=0.8, ls="--", alpha=0.4)
ax.axvline(6.5, color="black", lw=0.8, ls="--", alpha=0.4)
ax.text(1.75, 105, "SDS/SO 5 ml/hr", ha="center", fontsize=8.5, color=SDS_COLORS[300])
ax.text(5.0,  105, "NaCas/MCT 5 ml/hr", ha="center", fontsize=8.5, color=NC5_COLORS[300])
ax.text(8.25, 105, "NaCas/MCT 1 ml/hr", ha="center", fontsize=8.5, color=NC1_COLORS[150])

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=8)
ax.set_ylim(0, 115)
ax.set_ylabel("% of total cycle time")
ax.set_title("Stage fractions by condition")
ax.legend(fontsize=8.5, loc="upper right")
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_03_stage_fractions.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_03 saved")

# =============================================================================
# 8. FIGURE 4 — Meniscus reset (V_reset and dome)
# =============================================================================
print("Figure 4 — meniscus reset...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
rng4 = np.random.default_rng(13)

# Left: L_menpoint vs DFU, all conditions
for system, mcolors, ms in [
    ("SDS/SO 5ml/hr",    SDS_COLORS,  "o"),
    ("NaCas/MCT 5ml/hr", NC5_COLORS,  "s"),
]:
    for po, col in mcolors.items():
        pts = get_dfu(system, po)
        if len(pts) == 0:
            continue
        vals = pts["L_menpoint_um_mean"].dropna()
        dfus = pts.loc[vals.index, "DFU_num"]
        jx   = dfus + rng4.uniform(-0.25, 0.25, len(vals))
        label = f"{system.split()[0]} {po}mb"
        ax1.scatter(jx, vals.values, color=col, s=22, alpha=0.75,
                    marker=ms, edgecolors="none", label=label, zorder=4)

ax1.set_xlabel("DFU position")
ax1.set_ylabel("L_menpoint [µm]  (tip to junction)")
ax1.set_title("Meniscus reset length vs DFU position")
ax1.axhline(30, color="grey", lw=1, ls="--", label="Nominal 30 µm")
ax1.set_xlim(0, 11)
ax1.legend(fontsize=7, ncol=2)

# Right: dome_um vs Po
for system, mcolors, ms, lbl in [
    ("SDS/SO 5ml/hr",    SDS_COLORS,  "o", "SDS/SO 5ml/hr"),
    ("NaCas/MCT 5ml/hr", NC5_COLORS,  "s", "NaCas/MCT 5ml/hr"),
    ("NaCas/MCT 1ml/hr", NC1_COLORS,  "^", "NaCas/MCT 1ml/hr"),
]:
    po_list, dome_mean_list, dome_std_list = [], [], []
    for po in sorted(mcolors.keys()):
        c = get_cond(system, po)
        if c is None or pd.isna(c["dome_um"]):
            continue
        po_list.append(po)
        dome_mean_list.append(c["dome_um"])
        col_s = cond_std[
            (cond_std["Series"] == system) &
            (cond_std["DispPhasePressure"] == po)
        ]
        dome_std_list.append(float(col_s["dome_um_std"].values[0]) if len(col_s) else 0)
    if po_list:
        base_col = list(mcolors.values())[0]
        ax2.errorbar(po_list, dome_mean_list, yerr=dome_std_list,
                     fmt=f"-{ms}", color=base_col, lw=2, ms=7, capsize=3,
                     label=lbl, zorder=4)

ax2.set_xlabel("Oil inlet pressure Po [mbar]")
ax2.set_ylabel("Dome extent  L_men − L_menpoint [µm]")
ax2.set_title("Meniscus curvature vs pressure\n(larger = more convex)")
ax2.set_ylim(bottom=0)
ax2.legend(fontsize=8.5)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_04_meniscus_reset.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_04 saved")

# =============================================================================
# 9. FIGURE 5 — Droplet diameter vs DFU position (key figure)
# =============================================================================
print("Figure 5 — droplet diameter vs DFU...")

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
ax_sds, ax_nc5, ax_nc1 = axes

for ax, system, mcolors, title in [
    (ax_sds, "SDS/SO 5ml/hr",    SDS_COLORS,  "SDS/SO  5 ml/hr"),
    (ax_nc5, "NaCas/MCT 5ml/hr", NC5_COLORS,  "NaCas/MCT  5 ml/hr"),
    (ax_nc1, "NaCas/MCT 1ml/hr", NC1_COLORS,  "NaCas/MCT  1 ml/hr"),
]:
    all_d = []
    for po in sorted(mcolors.keys()):
        pts = get_dfu(system, po)
        if len(pts) == 0:
            continue
        col = mcolors[po]
        d_vals = pts["Droplet_diameter_um_mean"].dropna()
        dfu_vals = pts.loc[d_vals.index, "DFU_num"].values
        ax.plot(dfu_vals, d_vals.values, "-o", color=col, lw=1.5, ms=6,
                label=f"{po} mbar", zorder=4)
        all_d.extend(d_vals.values.tolist())

    # Flagged DFU10 for NaCas/MCT 5mlhr
    if system == "NaCas/MCT 5ml/hr":
        flagged = dfu_agg[dfu_agg["dfu_flagged"] &
                          (dfu_agg["Series"] == system)]
        for _, fr in flagged.iterrows():
            d = fr["Droplet_diameter_um_mean"]
            if not pd.isna(d):
                ax.scatter(fr["DFU_num"], d, color="black", s=60, zorder=6,
                           marker="x", linewidths=2)
                ax.annotate("⚠ oil\nwetting", xy=(fr["DFU_num"], d),
                            xytext=(fr["DFU_num"] - 1.5, d + 1.5),
                            fontsize=7, color="black",
                            arrowprops=dict(arrowstyle="->", lw=0.8))

    if all_d:
        overall_mean = np.mean(all_d)
        ax.axhline(overall_mean, color="grey", lw=1, ls="--", alpha=0.7)
        ax.text(0.98, overall_mean + 0.3, f"Mean {overall_mean:.1f} µm",
                transform=ax.get_yaxis_transform(), fontsize=7.5,
                ha="right", color="grey")

    ax.set_xlabel("DFU position (1=upstream, 10=downstream)")
    ax.set_ylabel("Droplet diameter [µm]")
    ax.set_title(title)
    ax.set_xlim(0, 11)
    ax.set_xticks(range(1, 11))
    ax.legend(title="Po", fontsize=7.5, title_fontsize=7.5)

    # y-axis range: consistent across panels
    ax.set_ylim(18, 36)

# Mark NaCas 200 mbar no-data
ax_nc5.text(5.5, 20, "200 mbar: no droplet formation", ha="center",
            fontsize=8, color=NC5_COLORS[200], style="italic",
            bbox=dict(facecolor="white", edgecolor=NC5_COLORS[200], alpha=0.8, boxstyle="round"))

fig.suptitle("Droplet diameter along device length (DFU 1–10)", fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_05_droplet_dfu.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_05 saved")

# =============================================================================
# 10. FIGURE 6 — Droplet diameter summary
# =============================================================================
print("Figure 6 — droplet diameter summary...")

# Collect per-condition diameter stats
diam_rows = []
for system in ALL_SYSTEMS:
    sub = dfu_ok[dfu_ok["Series"] == system]
    for po in sorted(sub["DispPhasePressure"].unique()):
        d_vals = sub[sub["DispPhasePressure"] == po]["Droplet_diameter_um_mean"].dropna().values
        if len(d_vals) == 0:
            continue
        diam_rows.append({
            "Series": system,
            "Po": po,
            "mean": np.mean(d_vals),
            "std":  np.std(d_vals),
            "cv_pct": np.std(d_vals) / np.mean(d_vals) * 100,
            "vals": d_vals,
        })

# Group by system for x positions
fig, ax = plt.subplots(figsize=(13, 5))
x_pos = 0
xticks, xlabels = [], []
for system in ALL_SYSTEMS:
    rows = [r for r in diam_rows if r["Series"] == system]
    col  = SERIES_COLOR[system]
    for r in rows:
        ax.bar(x_pos, r["mean"], width=0.6, color=col, alpha=0.8,
               yerr=r["std"], capsize=4,
               error_kw={"elinewidth": 1.2, "ecolor": "black"})
        ax.text(x_pos, r["mean"] + r["std"] + 0.3,
                f"CV {r['cv_pct']:.1f}%", ha="center", va="bottom",
                fontsize=7.5, color="black")
        xticks.append(x_pos)
        xlabels.append(f"{r['Po']}mb")
        x_pos += 1
    x_pos += 0.5  # gap between systems

ax.set_xticks(xticks)
ax.set_xticklabels(xlabels, fontsize=8.5)
ax.set_ylabel("Mean droplet diameter [µm]")
ax.set_title("Droplet diameter summary by condition (mean ± std across DFUs)")
ax.set_ylim(18, 32)
ax.axhline(ax.get_ylim()[0], color="black", lw=0.5)

# System labels above bars
x_pos = 0
for system in ALL_SYSTEMS:
    rows = [r for r in diam_rows if r["Series"] == system]
    if not rows:
        continue
    xs = [x_pos + i for i in range(len(rows))]
    mid = np.mean(xs)
    col = SERIES_COLOR[system]
    ax.text(mid, 31.5, system, ha="center", fontsize=9, color=col, fontweight="bold")
    x_pos += len(rows) + 0.5

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_06_droplet_summary.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_06 saved")

# =============================================================================
# 10b. FIGURE 7 — V_reset / droplet diameter correlation chain
# =============================================================================
print("Figure 7 — Stage1_s → V_reset → D_drop correlation...")

cor_data = dfu_ok.dropna(subset=["Stage1_s_mean", "V_reset_fL_mean",
                                  "Droplet_diameter_um_mean"]).copy()

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

for system, mcolors, ms in [
    ("SDS/SO 5ml/hr",    SDS_COLORS,  "o"),
    ("NaCas/MCT 5ml/hr", NC5_COLORS,  "s"),
    ("NaCas/MCT 1ml/hr", NC1_COLORS,  "^"),
]:
    sub = cor_data[cor_data["Series"] == system]
    for po in sorted(mcolors.keys()):
        pts = sub[sub["DispPhasePressure"] == po]
        if len(pts) == 0:
            continue
        col   = mcolors[po]
        label = f"{system.split()[0]} {po}mb"
        ax1.scatter(pts["Stage1_s_mean"], pts["V_reset_fL_mean"],
                    color=col, s=50, alpha=0.85, marker=ms,
                    edgecolors="white", linewidths=0.5, label=label, zorder=4)
        ax2.scatter(pts["V_reset_fL_mean"], pts["Droplet_diameter_um_mean"],
                    color=col, s=50, alpha=0.85, marker=ms,
                    edgecolors="white", linewidths=0.5, label=label, zorder=4)

for ax, xcol, ycol, xlabel, ylabel, title in [
    (ax1, "Stage1_s_mean", "V_reset_fL_mean",
     "Stage 1 time [s]", "V_reset [fL]",
     "Stage 1 fill time → oil volume reset"),
    (ax2, "V_reset_fL_mean", "Droplet_diameter_um_mean",
     "V_reset [fL]", "Droplet diameter [µm]",
     "Oil volume reset → droplet size"),
]:
    x_all = cor_data[xcol].values
    y_all = cor_data[ycol].values
    ok    = np.isfinite(x_all) & np.isfinite(y_all)
    if ok.sum() > 2:
        r = np.corrcoef(x_all[ok], y_all[ok])[0, 1]
        n = int(ok.sum())
        coeffs = np.polyfit(x_all[ok], y_all[ok], 1)
        xfit   = np.linspace(x_all[ok].min(), x_all[ok].max(), 100)
        ax.plot(xfit, np.polyval(coeffs, xfit), "k--", lw=1.2, alpha=0.45, zorder=3)
        ax.text(0.05, 0.95, f"Pearson r = {r:.2f}  (n={n})",
                transform=ax.transAxes, fontsize=9, va="top",
                bbox=dict(facecolor="white", alpha=0.75, edgecolor="grey", boxstyle="round,pad=0.3"))
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.set_title(title)

# Deduplicated legend on right panel
handles7, labels7 = ax2.get_legend_handles_labels()
seen, uh, ul = set(), [], []
for h, l in zip(handles7, labels7):
    if l not in seen:
        seen.add(l); uh.append(h); ul.append(l)
ax2.legend(uh, ul, fontsize=7, ncol=2)

fig.suptitle("Correlation chain: Stage 1 fill time  →  V_reset  →  Droplet diameter",
             fontsize=11)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_07_vreset_correlation.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_07 saved")

# =============================================================================
# 11. COLLECT REPORT STATISTICS
# =============================================================================
def fmt(val, dp=2):
    return f"{val:.{dp}f}" if pd.notna(val) else "N/A"

def get_cv(series, po, metric="Droplet_diameter_um"):
    pts = dfu_ok[(dfu_ok["Series"] == series) &
                 (dfu_ok["DispPhasePressure"] == po)][f"{metric}_mean"].dropna()
    if len(pts) < 2:
        return np.nan
    return pts.std() / pts.mean() * 100

# Condition table rows
cond_table = []
for system in ALL_SYSTEMS:
    sub = cond[cond["Series"] == system].sort_values("DispPhasePressure")
    for _, row in sub.iterrows():
        po = int(row["DispPhasePressure"])
        cv_d = get_cv(system, po)
        cond_table.append({
            "Series":  system,
            "Po":      po,
            "S1_mean": fmt(row["Stage1_s"]),
            "S2_mean": fmt(row["Stage2_s"]),
            "S3_mean": fmt(row["Stage3_s"]),
            "total":   fmt(row["total_t"]),
            "freq":    fmt(row["freq_Hz"], 3),
            "L_men":   fmt(row["L_menpoint_um"], 1),
            "dome":    fmt(row["dome_um"], 1),
            "V_fL":    fmt(row["V_reset_fL"], 1),
            "D_drop":  fmt(row["Droplet_diameter_um"], 1),
            "CV_drop": fmt(cv_d, 1) if not np.isnan(cv_d) else "N/A",
        })

# NaCas 200 mbar no-data rows
cond_table.insert(4, {
    "Series": "NaCas/MCT 5ml/hr", "Po": 200,
    "S1_mean": "—", "S2_mean": "—", "S3_mean": "—",
    "total": "—", "freq": "—", "L_men": "—", "dome": "—",
    "V_fL": "—", "D_drop": "—", "CV_drop": "—",
})

# Stage constancy check: S3 CV across all SDS pressures
sds_s3 = []
for po in [200, 300, 400, 600]:
    c = get_cond("SDS/SO 5ml/hr", po)
    if c is not None and not pd.isna(c["Stage3_s"]):
        sds_s3.append(c["Stage3_s"])
R["sds_s3_cv"] = np.std(sds_s3) / np.mean(sds_s3) * 100 if sds_s3 else np.nan

nc5_s3 = []
for po in [300, 400]:
    c = get_cond("NaCas/MCT 5ml/hr", po)
    if c is not None and not pd.isna(c["Stage3_s"]):
        nc5_s3.append(c["Stage3_s"])
R["nc5_s3_cv"]     = np.std(nc5_s3) / np.mean(nc5_s3) * 100 if nc5_s3 else np.nan
R["sds_s3_mean"]   = np.mean(sds_s3) if sds_s3 else np.nan
R["nc5_s3_mean"]   = np.mean(nc5_s3) if nc5_s3 else np.nan

# Overall D_drop for each system
for system, key in [("SDS/SO 5ml/hr", "sds"), ("NaCas/MCT 5ml/hr", "nc5"), ("NaCas/MCT 1ml/hr", "nc1")]:
    d_vals = dfu_ok[dfu_ok["Series"] == system]["Droplet_diameter_um_mean"].dropna().values
    R[f"{key}_d_mean"] = np.mean(d_vals) if len(d_vals) else np.nan
    R[f"{key}_d_std"]  = np.std(d_vals) if len(d_vals) else np.nan
    R[f"{key}_d_cv"]   = R[f"{key}_d_std"] / R[f"{key}_d_mean"] * 100 if len(d_vals) > 1 else np.nan

# Dome comparison
R["sds_dome_mean"]  = float(cond[cond["Series"]=="SDS/SO 5ml/hr"]["dome_um"].mean())
R["nc5_dome_mean"]  = float(cond[cond["Series"]=="NaCas/MCT 5ml/hr"]["dome_um"].mean())
R["nc1_dome_mean"]  = float(cond[cond["Series"]=="NaCas/MCT 1ml/hr"]["dome_um"].mean())

# V_reset comparison
R["sds_v_mean"]  = float(cond[cond["Series"]=="SDS/SO 5ml/hr"]["V_reset_fL"].mean())
R["nc5_v_mean"]  = float(cond[cond["Series"]=="NaCas/MCT 5ml/hr"]["V_reset_fL"].mean())
R["nc1_v_mean"]  = float(cond[cond["Series"]=="NaCas/MCT 1ml/hr"]["V_reset_fL"].mean())

# Shape ratio comparison (dome_um / L_menpoint_um)
R["sds_shape_ratio_mean"] = float(cond[cond["Series"]=="SDS/SO 5ml/hr"]["shape_ratio"].mean())
R["nc5_shape_ratio_mean"] = float(cond[cond["Series"]=="NaCas/MCT 5ml/hr"]["shape_ratio"].mean())
for po in [300, 400]:
    c_nc5 = get_cond("NaCas/MCT 5ml/hr", po)
    R[f"nc5_shape_ratio_{po}"] = float(c_nc5["shape_ratio"]) if c_nc5 is not None and not pd.isna(c_nc5["shape_ratio"]) else np.nan

# Frequency speed-up at matched pressure
for po in [300, 400]:
    c_sds = get_cond("SDS/SO 5ml/hr", po)
    c_nc5 = get_cond("NaCas/MCT 5ml/hr", po)
    if c_sds is not None and c_nc5 is not None and not pd.isna(c_sds["freq_Hz"]) and not pd.isna(c_nc5["freq_Hz"]):
        R[f"freq_speedup_pct_{po}"] = (c_nc5["freq_Hz"] / c_sds["freq_Hz"] - 1) * 100
    else:
        R[f"freq_speedup_pct_{po}"] = np.nan

# =============================================================================
# 12. WRITE REPORT
# =============================================================================
print(f"\nWriting report → {REPORT_OUT}")

def trow(r):
    return (f"| {r['Series']} | {r['Po']} | {r['S1_mean']} | {r['S2_mean']} | "
            f"{r['S3_mean']} | {r['total']} | {r['freq']} | {r['L_men']} | "
            f"{r['dome']} | {r['V_fL']} | {r['D_drop']} | {r['CV_drop']} |")

table_lines = [
    "| Series | Po (mbar) | S1 (s) | S2 (s) | S3 (s) | Total (s) | Freq (Hz) | "
    "L_men_pt (µm) | Dome (µm) | V_reset (fL) | D_drop (µm) | D CV% |",
    "|--------|-----------|--------|--------|--------|-----------|-----------|"
    "---------------|-----------|-------------|-------------|-------|",
]
for r in cond_table:
    table_lines.append(trow(r))

report = f"""\
# NaCas/MCT vs SDS/SO — Experimental Analysis Report

**Device:** V5-8-1 (junction 30 µm wide × 10 µm deep)
**Analysis date:** 2026-04-28
**Data source:** `analysis/stage_timings.csv`

---

## 1. Overview

This report characterises droplet formation in a new fluid system — 2.5% sodium caseinate
(NaCas) as continuous-phase surfactant with medium-chain triglyceride oil (MCT) as the
dispersed phase — against a well-established SDS/silicone-oil (SO) control.
Both systems were run at continuous-phase (water) flow rate Qw = 5 ml/hr across a range
of oil inlet pressures (Po). A low-flow NaCas/MCT dataset at Qw = 1 ml/hr is included
as an extreme reference. No model simulations are used; all results are from direct video
measurement.

**Key questions:**
1. Does NaCas/MCT form droplets stably, and what is its minimum operable pressure?
2. Are stage timings comparable to SDS/SO? Which stages scale with pressure and which do not?
3. Does the device produce consistent droplet size along its length (DFU 1–10)?
4. What operational range achieves good uniformity in both systems?

---

## 2. Dataset Summary

| Series | n rows (raw) | Qw (ml/hr) | Po tested (mbar) |
|--------|-------------|------------|-----------------|
| SDS/SO 5 ml/hr (control) | {R['n_sds']} | 5 | 200, 300, 400, 600 |
| NaCas/MCT 5 ml/hr | {R['n_nc5']} | 5 | 200 (no formation), 300, 400 |
| NaCas/MCT 1 ml/hr | {R['n_nc1']} | 1 | 100, 150 |

Excluded from this analysis: all other SDS concentrations (0.125%–1%), NaCas/SO, and the
legacy V5_30_3_3 device dataset.

---

## 3. 200 mbar NaCas/MCT — No Droplet Formation

At Po = 200 mbar with Qw = 5 ml/hr, the NaCas/MCT system produced no measurable stage
timings or geometry data across all 4 recorded observation rows. This represents the lower
operating boundary for this fluid system under these flow conditions.

**Implication:** The minimum viable oil pressure for NaCas/MCT at 5 ml/hr is between
200 and 300 mbar. This contrasts with SDS/SO, which operates successfully at 200 mbar.
The higher threshold likely reflects the greater viscosity of MCT relative to silicone oil,
requiring a larger driving pressure to initiate and sustain filling.

---

## 4. Stage Timing Analysis

Measured timings are split into three experimental stages:
- **Stage 1** — oil meniscus travels from reset position to the junction edge (hydraulic filling)
- **Stage 2** — oil pushes over the junction edge (transitional)
- **Stage 3** — continuous phase enters and pinches the neck; droplet detaches (snap-off)

Stages 1 and 2 together are driven by the hydraulic pressure difference Po − P_cap and are
expected to scale inversely with Po. Stage 3 is controlled by capillary geometry and is
expected to be approximately constant with Po.

{chr(10).join(table_lines)}

**Stage 1 + 2 (hydraulic):** Both SDS/SO and NaCas/MCT show Stage 1 decreasing markedly
with increasing Po — consistent with pressure-driven refill. For NaCas/MCT at 5 ml/hr,
Stage 1 is substantially shorter than SDS/SO at the same pressure. The most likely
explanation is the shorter meniscus reset geometry: NaCas produces a smaller L_menpoint
(less oil in the channel at the start of Stage 1), which reduces the initial hydraulic
resistance. Under Washburn-type constant-pressure filling, Stage 1 time scales as
L_menpoint² / ΔP — so the quadratic dependence on reset distance makes this a stronger
effect than any viscosity difference between the two oil phases.

**Stage 2:** Short in both systems (0.04–0.25 s). Represents the brief period when the oil
bulge grows over the junction edge before the neck begins to form.

**Stage 3 (snap-off):**
- SDS/SO 5 ml/hr: mean Stage 3 = {fmt(R['sds_s3_mean'])} s, CoV across pressures = {fmt(R['sds_s3_cv'], 1)}%
- NaCas/MCT 5 ml/hr: mean Stage 3 = {fmt(R['nc5_s3_mean'])} s, CoV = {fmt(R['nc5_s3_cv'], 1)}%

Stage 3 shows low variation with Po in both systems, confirming it is capillary/geometry
controlled rather than pressure driven. NaCas/MCT snap-off is markedly faster than SDS/SO
— mean Stage 3 {fmt(R['nc5_s3_mean'])} s vs {fmt(R['sds_s3_mean'])} s for SDS/SO — consistent
with a lower oil–water interfacial tension when NaCas is adsorbed, enabling faster capillary
neck collapse. This Stage 3 speed-up is a significant contributor to NaCas/MCT's higher
overall droplet frequency (see Section 5).

**NaCas/MCT at 1 ml/hr (100–150 mbar):** Stage 3 is substantially longer (0.5–2 s) compared
to the 5 ml/hr data (~0.08 s). This very long Stage 3 at low pressure/low flow likely
indicates a different snap-off regime — the neck forms but collapses slowly, possibly because
the driving pressure is insufficient for rapid squeezing by the continuous phase.

---

## 5. Cycle Frequency

Frequency (Hz) = 1 / total cycle time. Higher pressure and flow drive shorter cycles.

For SDS/SO 5 ml/hr:
- 200 mbar → {fmt(get_cond('SDS/SO 5ml/hr', 200)['freq_Hz'] if get_cond('SDS/SO 5ml/hr', 200) is not None else float('nan'), 3)} Hz
- 300 mbar → {fmt(get_cond('SDS/SO 5ml/hr', 300)['freq_Hz'] if get_cond('SDS/SO 5ml/hr', 300) is not None else float('nan'), 3)} Hz
- 400 mbar → {fmt(get_cond('SDS/SO 5ml/hr', 400)['freq_Hz'] if get_cond('SDS/SO 5ml/hr', 400) is not None else float('nan'), 3)} Hz
- 600 mbar → {fmt(get_cond('SDS/SO 5ml/hr', 600)['freq_Hz'] if get_cond('SDS/SO 5ml/hr', 600) is not None else float('nan'), 3)} Hz

For NaCas/MCT 5 ml/hr:
- 300 mbar → {fmt(get_cond('NaCas/MCT 5ml/hr', 300)['freq_Hz'] if get_cond('NaCas/MCT 5ml/hr', 300) is not None else float('nan'), 3)} Hz
- 400 mbar → {fmt(get_cond('NaCas/MCT 5ml/hr', 400)['freq_Hz'] if get_cond('NaCas/MCT 5ml/hr', 400) is not None else float('nan'), 3)} Hz

NaCas/MCT runs **significantly faster** than SDS/SO at matched pressure:
+{fmt(R['freq_speedup_pct_300'], 0)}% at 300 mbar and +{fmt(R['freq_speedup_pct_400'], 0)}% at 400 mbar.
All three stages are faster for NaCas/MCT. Stage 1 (and likely Stage 2) are faster
primarily because NaCas produces a shorter meniscus reset geometry — smaller L_menpoint
means less oil to displace and lower initial hydraulic resistance. Under constant-pressure
Washburn filling, Stage 1 time scales as L_menpoint², so the geometry effect dominates.
Stage 3 is approximately {fmt(R['sds_s3_mean']/R['nc5_s3_mean'] if R['nc5_s3_mean'] else float('nan'), 1)}× faster, which
points to a lower oil–water interfacial tension when NaCas is adsorbed, enabling faster
capillary snap-off independently of the hydraulic geometry.

---

## 6. Meniscus Reset and Shape

The oil meniscus resets to a position inside the rung after each droplet detaches.
Two measurements characterise this:
- **L_menpoint** (µm): distance from the meniscus tip to the junction edge
- **dome_um** = L_men − L_menpoint (µm): axial span of the meniscus dome — larger means more convex (more curved meniscus)

The displaced volume per cycle:
  V_reset = w·h·L_menpoint + (π/6)·w·h·dome_um

where w = 30 µm, h = 10 µm.

| System | Mean dome (µm) | Mean V_reset (fL) |
|--------|----------------|-------------------|
| SDS/SO 5 ml/hr | {fmt(R['sds_dome_mean'], 1)} | {fmt(R['sds_v_mean'], 1)} |
| NaCas/MCT 5 ml/hr | {fmt(R['nc5_dome_mean'], 1)} | {fmt(R['nc5_v_mean'], 1)} |
| NaCas/MCT 1 ml/hr | {fmt(R['nc1_dome_mean'], 1)} | {fmt(R['nc1_v_mean'], 1)} |

NaCas/MCT shows a **smaller L_menpoint** and a **more pointed (elongated) meniscus** than
SDS/SO. The meniscus shape ratio (dome_um / L_menpoint) quantifies this:
- SDS/SO mean shape ratio ≈ {fmt(R['sds_shape_ratio_mean'], 2)} (near-hemispherical)
- NaCas/MCT mean shape ratio ≈ {fmt(R['nc5_shape_ratio_mean'], 2)} (elongated cone;
  {fmt(R.get('nc5_shape_ratio_300', float('nan')), 2)} at 300 mbar,
  {fmt(R.get('nc5_shape_ratio_400', float('nan')), 2)} at 400 mbar)

Despite similar absolute dome extents, the much shorter L_menpoint for NaCas gives a
proportionally taller, more pointed profile. This reflects altered contact-angle behaviour
when NaCas adsorbs to the channel walls: the oil triple line stays further back while the
meniscus tip advances toward the junction, creating a higher-energy, more elongated interface.
This interpretation is consistent with two observations: (1) the 200 mbar formation failure
(the more pointed geometry requires a higher Laplace-pressure threshold to initiate snap-off),
and (2) the faster Stage 3 (once at the critical geometry, the more energetic interface
collapses faster).

The smaller V_reset for NaCas/MCT reflects the shorter reset distance (smaller L_menpoint),
despite the similar absolute dome extent.

---

## 7. Droplet Diameter Uniformity Across the Device

The central performance question: does the device produce consistent droplet size along
its length (DFU 1–10)?

### Overall diameter statistics

| System | Mean D (µm) | Std D (µm) | CV% across device |
|--------|-------------|------------|-------------------|
| SDS/SO 5 ml/hr | {fmt(R['sds_d_mean'], 1)} | {fmt(R['sds_d_std'], 2)} | {fmt(R['sds_d_cv'], 1)} |
| NaCas/MCT 5 ml/hr | {fmt(R['nc5_d_mean'], 1)} | {fmt(R['nc5_d_std'], 2)} | {fmt(R['nc5_d_cv'], 1)} |
| NaCas/MCT 1 ml/hr | {fmt(R['nc1_d_mean'], 1)} | {fmt(R['nc1_d_std'], 2)} | {fmt(R['nc1_d_cv'], 1)} |

### SDS/SO 5 ml/hr (control)

At all tested pressures (200–600 mbar), droplet diameter is remarkably uniform across
DFU 1–10. The per-pressure CV is low (≤ 2–3%), confirming that the device architecture
produces consistent droplets regardless of position along the device at these conditions.
Diameter is slightly smaller at higher pressures, consistent with the observed trend in
the literature for pressure-controlled squeezing: faster snap-off at higher Po leaves a
slightly smaller droplet.

### NaCas/MCT 5 ml/hr

At **300 mbar**, diameter is consistent across DFU 1–9 but falls slightly at downstream
positions. At **400 mbar**, the central DFUs (1–7) show good uniformity; however, **DFU 10
exhibits markedly higher variability and larger droplets**, flagged on Fig 5. Two DFU 10
observations are annotated: one labelled *"just before oil wetting begins"* (Stage 3 = 0.52 s,
D = 32.9 µm) and one *"last DFUs"* (Stage 3 = 0.28 s, D = 28.5 µm). These are characteristic
of oil wetting the channel walls at the device outlet — a known failure mode at high pressure.

**Operational range for NaCas/MCT (5 ml/hr):** DFU 1–7 at 300–400 mbar produces
consistent droplets with CV < ~5%. Operation should avoid the terminal DFUs at 400 mbar
where oil wetting risk is elevated.

### NaCas/MCT 1 ml/hr

At 100 mbar, droplet diameter is notably higher and more variable at downstream DFUs
(DFU 7–9 show larger droplets). This is consistent with the very long Stage 3 observed
at this condition: slow snap-off allows more oil to accumulate, forming larger droplets.
At 150 mbar, there is improvement in consistency but the trend persists. The 1 ml/hr
dataset demonstrates that very low flow rates can produce larger, less uniform droplets —
this represents an operational extreme rather than a recommended working condition.

---

## 8. Operational Range Summary

| System | Recommended Po (mbar) | Qw (ml/hr) | Reliable DFU range | Notes |
|--------|----------------------|------------|-------------------|-------|
| SDS/SO | 200–600 | 5 | 1–10 | All conditions show good uniformity |
| NaCas/MCT | 300–400 | 5 | 1–7 | Avoid DFU 8–10 at 400 mbar (oil wetting risk) |
| NaCas/MCT | 100–150 | 1 | 1–5 | Low flow extreme; larger and less uniform droplets |

Both systems produce droplets in a similar diameter range (~22–26 µm for the primary
5 ml/hr conditions), demonstrating that NaCas/MCT is a viable alternative fluid system
for this device architecture. The key operational difference is the higher minimum
pressure requirement for NaCas/MCT (≥ 300 mbar vs ≥ 200 mbar for SDS/SO) and increased
sensitivity to oil wetting at the downstream end of the device at 400 mbar.

---

## 9. Low-Flow Extreme — NaCas/MCT 1 ml/hr (100–150 mbar)

At Qw = 1 ml/hr, the NaCas/MCT system operates in a different regime:
- Stage 1 is very long (~1–3 s), reflecting slow hydraulic filling at low pressure
- Stage 3 is dramatically extended (0.5–2 s) — slow snap-off, possibly limited by continuous-phase shear
- Droplets are 24–30 µm, with larger droplets forming at downstream DFUs
- The device still produces droplets, but with low frequency (< 0.2 Hz) and lower uniformity

This confirms the device can operate across a broad flow-rate range with NaCas/MCT, but the
optimal window (uniformity, predictable timing, stable snap-off) is clearly at 5 ml/hr,
300–400 mbar, DFU 1–7.

---

*Generated by `analysis/nacas_mct_analysis.py` — {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}*
"""

with open(REPORT_OUT, "w", encoding="utf-8") as fh:
    fh.write(report)
print(f"Report written → {REPORT_OUT}")
print("\nDone.")
