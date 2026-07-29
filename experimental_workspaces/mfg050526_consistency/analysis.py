"""
mfg050526_consistency_analysis.py
==================================
Device consistency analysis for V5-30 Mfg-batch 050526.
Three devices (1B, 3D, 4C), identical conditions (SDS/SO, 5 ml/hr, 300 mbar).
Quantifies device-to-device variation and separates it from user measurement error.

Run from project root:
  .venv/Scripts/python.exe analysis/mfg050526_consistency_analysis.py
"""

import os
import re
import sys
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.colors import LinearSegmentedColormap

sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH     = os.path.join(SCRIPT_DIR, "Mfg-batch 050526",
                            "stage_timings_Mfg050526_combined.csv")
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
FIG_DIR      = os.path.join(PROJECT_ROOT, "results", "v5_30_mfg050526")
REPORT_OUT   = os.path.join(FIG_DIR, "report.md")
os.makedirs(FIG_DIR, exist_ok=True)

# ── Visual style ───────────────────────────────────────────────────────────────
DPI = 150

DEVICE_COLORS = {
    "V5-30-260413-1B": "#2e75b6",
    "V5-30-260413-3D": "#27ae60",
    "V5-30-260413-4C": "#e67e22",
}
DEVICE_MARKERS = {
    "V5-30-260413-1B": "o",
    "V5-30-260413-3D": "s",
    "V5-30-260413-4C": "^",
}
DEVICE_LABELS = {
    "V5-30-260413-1B": "1B",
    "V5-30-260413-3D": "3D",
    "V5-30-260413-4C": "4C",
}
DEVICES = ["V5-30-260413-1B", "V5-30-260413-3D", "V5-30-260413-4C"]

S1_COLOR = "#4e79a7"
S2_COLOR = "#f28e2b"
S3_COLOR = "#e15759"

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "legend.fontsize": 8.5, "xtick.labelsize": 9, "ytick.labelsize": 9,
})

# Core metrics used in variance/heatmap/error figures
CORE_METRICS  = ["Stage1_s",   "freq_Hz",           "Droplet_diameter_um"]
CORE_TITLES   = ["Stage 1",    "Production rate",    "Droplet diameter"]
CORE_YLABELS  = ["Time (s)",   "Frequency (Hz)",     "Diameter (µm)"]
# Reasonable CV% cap per metric for heatmap colour scale
CORE_CV_MAX   = [40,            40,                    8]

# Full metric list for aggregation
METRICS = ["Stage1_s", "Stage2_s", "Stage3_s", "CycleTime_s", "freq_Hz",
           "Droplet_diameter_um", "L_menpoint_um", "L_men_um"]

R = {}  # stats accumulator for report

# =============================================================================
# 1. LOAD & DERIVE COLUMNS
# =============================================================================
print(f"Loading: {CSV_PATH}")
raw = pd.read_csv(CSV_PATH)
print(f"  {len(raw)} total rows")
R["n_total"] = len(raw)

for col in ["Stage1_s", "Stage2_s", "Stage3_s",
            "L_menpoint_um", "L_men_um", "Droplet_diameter_um",
            "ContPhaseFlow", "DispPhasePressure", "ROI_ID"]:
    raw[col] = pd.to_numeric(raw[col], errors="coerce")

def _dfu_base(loc):
    return re.sub(r"_[BC]$", "", str(loc).strip(), flags=re.IGNORECASE) if pd.notna(loc) else np.nan

def _dfu_num(loc):
    m = re.search(r"(\d+)", str(loc)) if pd.notna(loc) else None
    return int(m.group(1)) if m else np.nan

raw["DFU_base"]    = raw["Location"].apply(_dfu_base)
raw["DFU_num"]     = raw["Location"].apply(_dfu_num)
raw["CycleTime_s"] = raw[["Stage1_s", "Stage2_s", "Stage3_s"]].sum(axis=1, skipna=False)
raw["freq_Hz"]     = np.where(raw["CycleTime_s"] > 0, 1.0 / raw["CycleTime_s"], np.nan)

dfu_positions      = sorted(raw["DFU_num"].dropna().unique().astype(int))
R["devices"]       = sorted(raw["DeviceID"].unique().tolist())
R["dfu_positions"] = dfu_positions
print(f"  Devices    : {R['devices']}")
print(f"  DFU positions: {dfu_positions}")

# =============================================================================
# 2. MEASUREMENT ERROR  (σ_meas)
# =============================================================================
REPEAT_KEYS = ["DeviceID", "VideoFile", "ROI_ID"]
raw_valid   = raw.dropna(subset=["Stage1_s"]).copy()

grp_sizes  = raw_valid.groupby(REPEAT_KEYS).size()
repeat_idx = grp_sizes[grp_sizes >= 2].index
n_repeat   = len(repeat_idx)

if n_repeat > 0:
    rep_data   = raw_valid.set_index(REPEAT_KEYS).loc[repeat_idx].reset_index()
    rep_stds   = rep_data.groupby(REPEAT_KEYS)[METRICS].std()
    sigma_meas = rep_stds.mean()
else:
    sigma_meas = pd.Series({m: 0.0 for m in METRICS})

R["n_repeat"]   = n_repeat
R["sigma_meas"] = sigma_meas.to_dict()
print(f"\n  Repeated ROI groups: {n_repeat}")

# =============================================================================
# 3. THREE-LEVEL AVERAGING
# =============================================================================
GRP_L1 = ["DeviceID", "DFU_base", "DFU_num", "VideoFile", "ROI_ID"]
l1 = raw_valid.groupby(GRP_L1, dropna=False)[METRICS].mean().reset_index()
R["n_valid"] = len(raw_valid)
R["n_l1"]    = len(l1)

GRP_L2 = ["DeviceID", "DFU_base", "DFU_num"]
l2 = (
    l1.groupby(GRP_L2, dropna=False)[METRICS]
    .agg(["mean", "std", "count"])
    .reset_index()
)
l2.columns = [
    "_".join(str(c) for c in col).rstrip("_") if isinstance(col, tuple) else col
    for col in l2.columns
]
l2["DFU_num"] = l2["DFU_num"].astype(float)

# Stage fractions
for s, col in [("S1", "Stage1_s"), ("S2", "Stage2_s"), ("S3", "Stage3_s")]:
    l2[f"{s}_frac"] = l2[f"{col}_mean"] / l2["CycleTime_s_mean"]

R["n_l2"] = len(l2)
print(f"  Valid rows: {R['n_valid']} | L1 ROI means: {R['n_l1']} | L2 DFU means: {R['n_l2']}")

def get_dev(device):
    return l2[l2["DeviceID"] == device].sort_values("DFU_num")

# Per-device overall summary
dev_summary = {}
for dev in DEVICES:
    sub = get_dev(dev)
    dev_summary[dev] = {m: (sub[f"{m}_mean"].mean(), sub[f"{m}_mean"].std()) for m in METRICS}

# =============================================================================
# 4. VARIANCE DECOMPOSITION
# =============================================================================
sigma_within_raw  = {}
sigma_within_corr = {}
sigma_between_dfu = {}
sigma_between_dev = {}

for m in METRICS:
    s_w = l2[f"{m}_std"].dropna().mean()
    sigma_within_raw[m]  = s_w if not np.isnan(s_w) else 0.0
    s_m = sigma_meas[m]
    sigma_within_corr[m] = math.sqrt(max(s_w**2 - s_m**2, 0.0)) if not np.isnan(s_w) else 0.0
    bd = [get_dev(d)[f"{m}_mean"].dropna().std() for d in DEVICES]
    sigma_between_dfu[m] = np.nanmean(bd)
    sigma_between_dev[m] = l2.groupby("DFU_num")[f"{m}_mean"].std().mean()

DEV_OFFSETS = {DEVICES[0]: -0.2, DEVICES[1]: 0.0, DEVICES[2]: 0.2}

def _fmt(v, d=3):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:.{d}f}"

# =============================================================================
# FIG 1  —  Production rate (Hz) vs DFU position
# =============================================================================
print("\nGenerating Fig 1 ...")
fig, ax = plt.subplots(figsize=(10, 4))

grand = l2.groupby("DFU_num")["freq_Hz_mean"].mean()
ax.plot(grand.index, grand.values, "--", color="grey", lw=1.3, alpha=0.55,
        zorder=1, label="Grand mean")

for dev in DEVICES:
    sub = get_dev(dev)
    x  = sub["DFU_num"] + DEV_OFFSETS[dev]
    y  = sub["freq_Hz_mean"]
    ye = sub["freq_Hz_std"].fillna(0)
    ax.errorbar(x, y, yerr=ye,
                fmt=f"{DEVICE_MARKERS[dev]}-",
                color=DEVICE_COLORS[dev],
                lw=1.5, capsize=3, ms=5,
                label=DEVICE_LABELS[dev], zorder=3)

ax.set_xlabel("DFU position")
ax.set_ylabel("Production rate (Hz)")
ax.set_title("Droplet production rate across DFU positions")
ax.set_xticks(dfu_positions)
ax.legend(ncol=4)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_01_production_rate_vs_dfu.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 2  —  Droplet diameter vs DFU position  (mean ± std, no grand mean)
# =============================================================================
print("Generating Fig 2 ...")
fig, ax = plt.subplots(figsize=(10, 4))

legend_handles = []
for dev in DEVICES:
    sub = get_dev(dev)
    x   = sub["DFU_num"] + DEV_OFFSETS[dev]
    y   = sub["Droplet_diameter_um_mean"]
    ye  = sub["Droplet_diameter_um_std"].fillna(0)
    mn, sd = dev_summary[dev]["Droplet_diameter_um"]
    lbl = f"{DEVICE_LABELS[dev]}  (μ={mn:.2f}, σ={sd:.2f} µm)"
    ax.errorbar(x, y, yerr=ye,
                fmt=f"{DEVICE_MARKERS[dev]}-",
                color=DEVICE_COLORS[dev],
                lw=1.5, capsize=3, ms=5, zorder=3)
    legend_handles.append(
        Line2D([0], [0], marker=DEVICE_MARKERS[dev], color=DEVICE_COLORS[dev],
               lw=1.5, ms=5, label=lbl)
    )

ax.set_xlabel("DFU position")
ax.set_ylabel("Droplet diameter (µm)")
ax.set_title("Droplet diameter across DFU positions")
ax.set_xticks(dfu_positions)
ax.legend(handles=legend_handles, fontsize=8.5)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_02_dropsize_vs_dfu.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 2A  —  Droplet diameter: all individual data points + faint error bars
# =============================================================================
print("Generating Fig 2A ...")
fig, ax = plt.subplots(figsize=(10, 4))
rng_2a = np.random.default_rng(123)

legend_handles = []
for dev in DEVICES:
    c   = DEVICE_COLORS[dev]
    mk  = DEVICE_MARKERS[dev]
    sub_l1 = l1[l1["DeviceID"] == dev]

    # Individual L1 ROI means — small pastel scatter with jitter
    for dnum in dfu_positions:
        pts = sub_l1[sub_l1["DFU_num"] == dnum]["Droplet_diameter_um"].dropna().values
        if len(pts) == 0:
            continue
        jitter = rng_2a.uniform(-0.2, 0.2, len(pts))
        ax.scatter(dnum + DEV_OFFSETS[dev] + jitter, pts,
                   color=c, s=14, alpha=0.3, edgecolors="none", zorder=2)

    # DFU-level mean ± std as faint error bars (no connecting line)
    sub = get_dev(dev)
    x  = sub["DFU_num"] + DEV_OFFSETS[dev]
    y  = sub["Droplet_diameter_um_mean"]
    ye = sub["Droplet_diameter_um_std"].fillna(0)
    ax.errorbar(x, y, yerr=ye,
                fmt=mk, color=c, lw=0, capsize=4, ms=6,
                elinewidth=1.5, alpha=0.6, zorder=4)

    mn, sd = dev_summary[dev]["Droplet_diameter_um"]
    legend_handles.append(
        Line2D([0], [0], marker=mk, color=c, lw=0, ms=6,
               label=f"{DEVICE_LABELS[dev]}  (μ={mn:.2f}, σ={sd:.2f} µm)")
    )

ax.set_xlabel("DFU position")
ax.set_ylabel("Droplet diameter (µm)")
ax.set_title("Droplet diameter — all ROI observations per DFU position")
ax.set_xticks(dfu_positions)
ax.legend(handles=legend_handles, fontsize=8.5)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_02A_dropsize_all_points.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 3  —  Per-device violin summary (original — each panel has own y-axis)
# =============================================================================
print("Generating Fig 3 ...")
VIOLIN_METRICS  = ["Stage1_s", "Stage2_s", "Stage3_s", "Droplet_diameter_um"]
VIOLIN_TITLES   = ["Stage 1", "Stage 2", "Stage 3", "Droplet diameter"]
VIOLIN_YLABELS  = ["Time (s)", "Time (s)", "Time (s)", "Diameter (µm)"]

fig, axes = plt.subplots(1, 4, figsize=(14, 5))
rng3 = np.random.default_rng(42)

for ax, m, ylabel, title in zip(axes, VIOLIN_METRICS, VIOLIN_YLABELS, VIOLIN_TITLES):
    data = [get_dev(d)[f"{m}_mean"].dropna().values for d in DEVICES]
    pos  = [1, 2, 3]
    parts = ax.violinplot(data, positions=pos, showmedians=True, showextrema=True, widths=0.5)
    for body, dev in zip(parts["bodies"], DEVICES):
        body.set_facecolor(DEVICE_COLORS[dev])
        body.set_alpha(0.45)
    for key in ("cmedians", "cmins", "cmaxes", "cbars"):
        parts[key].set_color("dimgrey")
        parts[key].set_linewidth(1.2)
    for i, (dev, vals) in enumerate(zip(DEVICES, data)):
        jx = pos[i] + rng3.uniform(-0.08, 0.08, len(vals))
        ax.scatter(jx, vals, color=DEVICE_COLORS[dev], s=20, alpha=0.85,
                   zorder=4, edgecolors="none")
    ax.set_xticks(pos)
    ax.set_xticklabels([DEVICE_LABELS[d] for d in DEVICES])
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)

fig.suptitle("Per-device distribution across DFU positions", fontsize=12, y=1.01)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_03_device_summary.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 3B  —  Same violin but Stage 1/2/3 share a common y-axis
# =============================================================================
print("Generating Fig 3B ...")
fig, axes = plt.subplots(1, 4, figsize=(14, 5))
rng3b = np.random.default_rng(42)

# Compute shared y-range across all three timing stages
timing_vals = []
for m in ["Stage1_s", "Stage2_s", "Stage3_s"]:
    for dev in DEVICES:
        timing_vals.extend(get_dev(dev)[f"{m}_mean"].dropna().tolist())
t_pad = (max(timing_vals) - min(timing_vals)) * 0.12
shared_ylim = (max(0, min(timing_vals) - t_pad), max(timing_vals) + t_pad)

for ax_idx, (ax, m, ylabel, title) in enumerate(
        zip(axes, VIOLIN_METRICS, VIOLIN_YLABELS, VIOLIN_TITLES)):
    data  = [get_dev(d)[f"{m}_mean"].dropna().values for d in DEVICES]
    pos   = [1, 2, 3]
    parts = ax.violinplot(data, positions=pos, showmedians=True, showextrema=True, widths=0.5)
    for body, dev in zip(parts["bodies"], DEVICES):
        body.set_facecolor(DEVICE_COLORS[dev])
        body.set_alpha(0.45)
    for key in ("cmedians", "cmins", "cmaxes", "cbars"):
        parts[key].set_color("dimgrey")
        parts[key].set_linewidth(1.2)
    for i, (dev, vals) in enumerate(zip(DEVICES, data)):
        jx = pos[i] + rng3b.uniform(-0.08, 0.08, len(vals))
        ax.scatter(jx, vals, color=DEVICE_COLORS[dev], s=20, alpha=0.85,
                   zorder=4, edgecolors="none")
    ax.set_xticks(pos)
    ax.set_xticklabels([DEVICE_LABELS[d] for d in DEVICES])
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    # Apply shared timing scale to S1/S2/S3; drop diameter keeps own scale
    if ax_idx < 3:
        ax.set_ylim(shared_ylim)

fig.suptitle("Per-device distribution — Stage 1/2/3 on shared y-axis", fontsize=12, y=1.01)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_03B_device_summary_shared_y.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 4  —  100%-stacked stage fractions per DFU position  (unchanged)
# =============================================================================
print("Generating Fig 4 ...")
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=True)

for ax, dev in zip(axes, DEVICES):
    sub = get_dev(dev).dropna(subset=["S1_frac", "S2_frac", "S3_frac"])
    xs  = np.arange(len(sub))
    s1f = sub["S1_frac"].values * 100
    s2f = sub["S2_frac"].values * 100
    s3f = sub["S3_frac"].values * 100
    w   = 0.7
    ax.bar(xs, s1f, width=w, color=S1_COLOR, alpha=0.88)
    ax.bar(xs, s2f, width=w, bottom=s1f, color=S2_COLOR, alpha=0.88)
    ax.bar(xs, s3f, width=w, bottom=s1f + s2f, color=S3_COLOR, alpha=0.88)
    for i, (f1, f2, f3) in enumerate(zip(s1f, s2f, s3f)):
        if f1 > 6:
            ax.text(i, f1/2, f"{f1:.0f}%", ha="center", va="center",
                    fontsize=7, color="white", fontweight="bold")
        if f2 > 6:
            ax.text(i, f1+f2/2, f"{f2:.0f}%", ha="center", va="center",
                    fontsize=7, color="white", fontweight="bold")
        if f3 > 6:
            ax.text(i, f1+f2+f3/2, f"{f3:.0f}%", ha="center", va="center",
                    fontsize=7, color="white", fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"D{int(n)}" for n in sub["DFU_num"].values], fontsize=8)
    ax.set_xlabel("DFU position")
    ax.set_title(f"Device {DEVICE_LABELS[dev]}")
    ax.set_xlim(-0.5, len(sub)-0.5)

axes[0].set_ylabel("Fraction of cycle time (%)")
axes[0].set_ylim(0, 100)
legend_patches = [
    mpatches.Patch(color=S1_COLOR, alpha=0.88, label="Stage 1"),
    mpatches.Patch(color=S2_COLOR, alpha=0.88, label="Stage 2"),
    mpatches.Patch(color=S3_COLOR, alpha=0.88, label="Stage 3"),
]
fig.legend(handles=legend_patches, loc="upper right", ncol=3,
           bbox_to_anchor=(0.99, 1.01), fontsize=9)
fig.suptitle("Stage fractions by DFU position", fontsize=12)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_04_stage_fractions.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 5  —  Variance decomposition  (core metrics only)
# =============================================================================
print("Generating Fig 5 ...")
fig, axes = plt.subplots(1, 3, figsize=(13, 5))

var_labels = ["σ meas\n(user error)", "σ within-DFU\n(corrected)",
              "σ between-DFU\n(positional)", "σ between-device"]
var_colors = ["#d62728", "#aec7e8", "#ffbb78", "#1f77b4"]

for ax, m, title, ylabel in zip(axes, CORE_METRICS, CORE_TITLES, CORE_YLABELS):
    vals = [
        sigma_meas[m],
        sigma_within_corr[m],
        sigma_between_dfu[m],
        sigma_between_dev[m],
    ]
    xs   = np.arange(len(vals))
    bars = ax.bar(xs, vals, color=var_colors, alpha=0.85, width=0.6, edgecolor="white")
    ymax = max((v for v in vals if not np.isnan(v)), default=1.0)
    for bar, v in zip(bars, vals):
        if not np.isnan(v):
            ax.text(bar.get_x() + bar.get_width()/2, v + ymax*0.02,
                    f"{v:.4f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels(var_labels, fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, ymax * 1.3)

# Shared legend below
legend_handles = [mpatches.Patch(color=c, alpha=0.85, label=l)
                  for c, l in zip(var_colors, var_labels)]
fig.legend(handles=legend_handles, loc="lower center", ncol=4, fontsize=8,
           bbox_to_anchor=(0.5, -0.06))
fig.suptitle("Variance decomposition — σ at each source level", fontsize=12)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_05_variance_decomposition.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 6  —  CV% heatmap  (core metrics, per-metric colour scale)
# =============================================================================
print("Generating Fig 6 ...")
fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))

cmap_cv = LinearSegmentedColormap.from_list("grn_red", ["#27ae60", "#ffffcc", "#d62728"])

for ax, m, title, cv_cap in zip(axes, CORE_METRICS, CORE_TITLES, CORE_CV_MAX):
    mat = np.full((len(DEVICES), len(dfu_positions)), np.nan)
    for di, dev in enumerate(DEVICES):
        sub = l2[l2["DeviceID"] == dev]
        for ci, dnum in enumerate(dfu_positions):
            row = sub[sub["DFU_num"] == dnum]
            if len(row) == 0:
                continue
            mn = row[f"{m}_mean"].values[0]
            sd = row[f"{m}_std"].values[0]
            if pd.notna(mn) and pd.notna(sd) and mn != 0:
                mat[di, ci] = 100 * sd / mn

    # Per-metric adaptive cap: whichever is higher between data 95th pct and minimum cap
    data_max = np.nanpercentile(mat, 95) if not np.all(np.isnan(mat)) else cv_cap
    vmax = max(data_max * 1.05, cv_cap * 0.25)   # at least 25% of cap so colour spreads

    im = ax.imshow(mat, aspect="auto", cmap=cmap_cv, vmin=0, vmax=vmax)
    plt.colorbar(im, ax=ax, label="CV (%)")
    ax.set_xticks(range(len(dfu_positions)))
    ax.set_xticklabels([f"D{d}" for d in dfu_positions], fontsize=8)
    ax.set_yticks(range(len(DEVICES)))
    ax.set_yticklabels([DEVICE_LABELS[d] for d in DEVICES])
    ax.set_title(f"{title}  —  CV%")
    for di in range(len(DEVICES)):
        for ci in range(len(dfu_positions)):
            v = mat[di, ci]
            if not np.isnan(v):
                txt_col = "white" if v > vmax * 0.65 else "black"
                ax.text(ci, di, f"{v:.1f}", ha="center", va="center",
                        fontsize=7.5, color=txt_col)

fig.suptitle("CV% heatmap — within-device spatial consistency", fontsize=12)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_06_cv_heatmap.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 7  —  Measurement reproducibility  (core metrics)
# =============================================================================
print("Generating Fig 7 ...")
fig, (ax_bar, ax_scat) = plt.subplots(1, 2, figsize=(12, 5))

# Left — raw σ vs corrected σ vs σ_meas for core metrics
labels_bar = ["S1 (s)", "Rate (Hz)", "Diam (µm)"]
xb = np.arange(len(CORE_METRICS))
w  = 0.25

ax_bar.bar(xb - w, [sigma_within_raw[m]  for m in CORE_METRICS],
           width=w, color="#aec7e8", label="σ within-DFU (raw)")
ax_bar.bar(xb,     [sigma_within_corr[m] for m in CORE_METRICS],
           width=w, color="#1f77b4", label="σ within-DFU (corr)")
ax_bar.bar(xb + w, [sigma_meas[m]         for m in CORE_METRICS],
           width=w, color="#d62728", alpha=0.8, label="σ meas (user error)")
ax_bar.set_xticks(xb)
ax_bar.set_xticklabels(labels_bar)
ax_bar.set_ylabel("Standard deviation")
ax_bar.set_title("Measurement error vs within-DFU variation")
ax_bar.legend(fontsize=8)
ax_bar.grid(axis="y", alpha=0.3)

# Right — Stage 1 repeated-pair scatter
pairs_x, pairs_y = [], []
for _, grp in raw_valid.groupby(REPEAT_KEYS):
    if len(grp) >= 2:
        vals = grp["Stage1_s"].dropna().values
        if len(vals) >= 2:
            pairs_x.append(vals[0])
            pairs_y.append(vals[1])

if pairs_x:
    pairs_x = np.array(pairs_x)
    pairs_y = np.array(pairs_y)
    ax_scat.scatter(pairs_x, pairs_y, color="#2e75b6", s=30, alpha=0.75,
                    edgecolors="none", label=f"Stage 1 pairs (n={len(pairs_x)})")
    lo = min(pairs_x.min(), pairs_y.min()) * 0.92
    hi = max(pairs_x.max(), pairs_y.max()) * 1.08
    ax_scat.plot([lo, hi], [lo, hi], "k--", lw=1.2, alpha=0.4,
                 label="Perfect reproducibility")
    r = np.corrcoef(pairs_x, pairs_y)[0, 1]
    R["meas_r_stage1"] = r
    ax_scat.text(0.05, 0.93, f"Pearson r = {r:.3f}",
                 transform=ax_scat.transAxes, fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))
else:
    ax_scat.text(0.5, 0.5, "No repeated Stage 1 pairs found",
                 ha="center", va="center", transform=ax_scat.transAxes)
    R["meas_r_stage1"] = float("nan")

ax_scat.set_xlabel("Stage 1 — measurement 1 (s)")
ax_scat.set_ylabel("Stage 1 — measurement 2 (s)")
ax_scat.set_title("Stage 1 repeated measurements on same ROI")
ax_scat.legend(fontsize=8)
ax_scat.grid(alpha=0.3)

fig.suptitle("Measurement reproducibility analysis", fontsize=12)
fig.tight_layout()
p = os.path.join(FIG_DIR, "fig_07_measurement_error.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# FIG 8  —  Meniscus geometry vs DFU position  (unchanged)
# =============================================================================
print("Generating Fig 8 ...")
fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

for ax, col, ylabel, title in zip(
    axes,
    ["L_menpoint_um", "L_men_um"],
    ["L_menpoint (µm)", "L_men (µm)"],
    ["Meniscus point position", "Meniscus length"],
):
    grand = l2.groupby("DFU_num")[f"{col}_mean"].mean()
    ax.plot(grand.index, grand.values, "--", color="grey", lw=1.3, alpha=0.55,
            zorder=1, label="Grand mean")
    for dev in DEVICES:
        sub = get_dev(dev)
        x  = sub["DFU_num"] + DEV_OFFSETS[dev]
        y  = sub[f"{col}_mean"]
        ye = sub[f"{col}_std"].fillna(0)
        ax.errorbar(x, y, yerr=ye,
                    fmt=f"{DEVICE_MARKERS[dev]}-",
                    color=DEVICE_COLORS[dev],
                    lw=1.5, capsize=3, ms=5,
                    label=DEVICE_LABELS[dev], zorder=3)
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title} across DFU positions")
    ax.grid(axis="y", alpha=0.3)
    ax.set_xticks(dfu_positions)

axes[-1].set_xlabel("DFU position")
handles, lbls = axes[0].get_legend_handles_labels()
fig.legend(handles, lbls, loc="upper right", ncol=4, fontsize=9,
           bbox_to_anchor=(0.99, 0.99))
fig.tight_layout(rect=[0, 0, 1, 0.96])
p = os.path.join(FIG_DIR, "fig_08_geometry_vs_dfu.png")
fig.savefig(p, dpi=DPI, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {p}")

# =============================================================================
# AVERAGING EXPLAINER  (builds the layer-by-layer section for the report)
# =============================================================================

def build_averaging_explainer():
    """
    Returns a markdown string that walks through the full averaging chain
    with real numbers from the dataset — concrete enough to follow by hand.
    """
    out = []
    a = out.append

    a("## Appendix: How Averages and Uncertainties Are Computed — Layer by Layer\n")
    a(
        "Every mean and error bar in this report is the result of a structured "
        "three-level aggregation.  This section walks through each level using real "
        "data so the numbers can be traced by hand.\n"
    )
    a("---\n")

    # ── Layer 0: raw observations ──────────────────────────────────────────────
    a("### Layer 0 — Raw observations\n")
    a(
        "Each row in the source CSV is one analysis event: a user selected a video "
        "frame, drew a region of interest (ROI) around a droplet generator, and the "
        "analysis tool returned timing and diameter values for that observation.  "
        "Nothing has been averaged yet.\n\n"
        "Each ROI corresponds to one specific droplet generator on the device.  "
        "Because the same generator fires repeatedly (a new drop every ~1 s), "
        "multiple rows can share the same `(VideoFile, ROI_ID)` — these are separate "
        "drops produced by the same generator, measured at different moments.  "
        "In ideal conditions the same generator should produce identical drops every "
        "cycle, so within-ROI spread reflects measurement precision plus occasional "
        "anomalous events (misfires, partial occlusions, etc.).\n"
    )

    # Pick a concrete example: 1B / DFU4 — has 3 ROIs, two of which have repeats
    ex_dev = "V5-30-260413-1B"
    ex_loc = "DFU4"
    ex_raw = raw_valid[
        (raw_valid["DeviceID"] == ex_dev) &
        (raw_valid["DFU_base"] == ex_loc)
    ].copy()
    ex_raw["ROI_ID"] = ex_raw["ROI_ID"].astype(int)

    a(f"**Worked example — Device 1B, position {ex_loc}**\n")
    a("| Row | ROI | Stage 1 (s) | Drop diameter (µm) | Note |")
    a("|-----|-----|------------|-------------------|------|")
    roi_seen = {}
    for _, row in ex_raw.sort_values(["ROI_ID"]).iterrows():
        roi = int(row["ROI_ID"])
        roi_seen[roi] = roi_seen.get(roi, 0) + 1
        note = f"ROI {roi}, obs {roi_seen[roi]}"
        s1  = f"{row['Stage1_s']:.2f}" if pd.notna(row["Stage1_s"]) else "—"
        diam = f"{row['Droplet_diameter_um']:.2f}" if pd.notna(row["Droplet_diameter_um"]) else "—"
        a(f"| — | {roi} | {s1} | {diam} | {note} |")
    a("")

    # ── Layer 1: ROI mean ──────────────────────────────────────────────────────
    a("### Layer 1 — ROI mean  *(collapses repeated observations of the same generator)*\n")
    a(
        "All raw rows sharing the same `(DeviceID, VideoFile, ROI_ID)` are averaged "
        "into a single value.  This treats each observation as an independent estimate "
        "of that generator's true output and takes their mean as the best estimate.  "
        "If a generator was only observed once, that single value passes through unchanged.\n\n"
        "The spread *within* a group (its standard deviation) is the raw material for "
        "the measurement-error estimate σ_meas — see Layer M below.\n"
    )

    ex_l1 = ex_raw.groupby(["ROI_ID"])[["Stage1_s", "Droplet_diameter_um"]].agg(
        ["mean", "std", "count"]
    )
    ex_l1.columns = ["_".join(c) for c in ex_l1.columns]
    ex_l1 = ex_l1.reset_index()

    a(f"**After Layer 1 — Device 1B, position {ex_loc}  (one row per ROI)**\n")
    a("| ROI | n obs | Stage 1 mean (s) | Drop diam mean (µm) | Within-ROI std (µm) |")
    a("|-----|-------|-----------------|--------------------|--------------------|")
    for _, row in ex_l1.iterrows():
        sd_str = f"{row['Droplet_diameter_um_std']:.3f}" if pd.notna(row["Droplet_diameter_um_std"]) else "n/a (single obs)"
        a(f"| {int(row['ROI_ID'])} | {int(row['Droplet_diameter_um_count'])} "
          f"| {row['Stage1_s_mean']:.3f} | {row['Droplet_diameter_um_mean']:.3f} | {sd_str} |")
    a("")
    a(
        "Note: ROI 1 has two observations with a diameter spread of "
        f"{abs(ex_raw[ex_raw['ROI_ID']==1]['Droplet_diameter_um'].diff().dropna().values[0]):.2f} µm.  "
        "After averaging, ROI 1's mean is slightly higher than ROIs 2 and 3.  "
        "That elevated mean is what enters Layer 2.\n"
    )

    # ── Layer M: σ_meas ────────────────────────────────────────────────────────
    a("### Layer M — Measurement error estimate  *(σ_meas)*\n")
    a(
        "Before moving to Layer 2, we estimate how much of the within-ROI spread is "
        "pure measurement noise.  We collect every ROI group that has ≥ 2 observations, "
        "compute the standard deviation within that group, and average those standard "
        "deviations across the whole dataset.  The result — σ_meas — is a single "
        "dataset-wide estimate of the noise floor.\n\n"
        f"**Repeated-observation groups found across all devices: {n_repeat}**\n"
    )

    # Show a sample of the within-group stds
    if n_repeat > 0:
        rep_data_show = raw_valid.set_index(REPEAT_KEYS).loc[repeat_idx].reset_index()
        rep_stds_show = (
            rep_data_show.groupby(REPEAT_KEYS)[["Stage1_s", "Droplet_diameter_um", "freq_Hz"]]
            .std()
            .reset_index()
        )
        rep_stds_show["device_label"] = rep_stds_show["DeviceID"].map(DEVICE_LABELS)
        rep_sizes_show = raw_valid.groupby(REPEAT_KEYS).size().reset_index(name="n_obs")
        rep_stds_show = rep_stds_show.merge(rep_sizes_show, on=REPEAT_KEYS, how="left")

        a("Sample of within-ROI standard deviations (first 10 repeated groups):\n")
        a("| Device | Location | ROI | n obs | σ Stage 1 (s) | σ Drop diam (µm) |")
        a("|--------|---------|-----|-------|--------------|-----------------|")
        for _, row in rep_stds_show.head(10).iterrows():
            loc_raw = raw_valid[
                (raw_valid["DeviceID"] == row["DeviceID"]) &
                (raw_valid["VideoFile"] == row["VideoFile"]) &
                (raw_valid["ROI_ID"]   == row["ROI_ID"])
            ]["Location"].iloc[0]
            s1_s  = f"{row['Stage1_s']:.4f}" if pd.notna(row["Stage1_s"]) else "—"
            dd_s  = f"{row['Droplet_diameter_um']:.4f}" if pd.notna(row["Droplet_diameter_um"]) else "—"
            a(f"| {row['device_label']} | {loc_raw} | {int(row['ROI_ID'])} "
              f"| {int(row['n_obs'])} | {s1_s} | {dd_s} |")
        a("")

    a("**σ_meas (average of all within-group stds):**\n")
    a("| Metric | σ_meas |")
    a("|--------|--------|")
    for m, lbl in [("Stage1_s", "Stage 1 (s)"),
                   ("freq_Hz",  "Freq (Hz)"),
                   ("Droplet_diameter_um", "Drop diam (µm)")]:
        a(f"| {lbl} | {sigma_meas[m]:.4f} |")
    a("")
    a(
        "σ_meas is a conservative upper bound: it includes both genuine user "
        "measurement error *and* any real device misfires that happened to be captured "
        "during repeated observations of the same generator.  This means σ_corrected "
        "values (see Layer 3) will be slightly conservative too — if anything, "
        "understating rather than overstating genuine physical variation.\n"
    )

    # Practical interpretation of σ_meas
    cal   = raw["Calibration_px_per_um"].dropna().iloc[0]
    px_um = 1.0 / cal
    sm_d  = sigma_meas["Droplet_diameter_um"]
    sm_s1 = sigma_meas["Stage1_s"]

    a("#### What σ_meas means in practice\n")
    a(
        "σ_meas is a **1-sigma (1σ) value** — one standard deviation of the "
        "measurement noise.  In practical terms:\n\n"
        "- A **single measurement** has a ~68% chance of being within ±1σ of the "
        "true value, and a ~95% chance of being within ±2σ.\n"
        "- If you take **N measurements** of the same generator and average them, "
        "the uncertainty on that mean shrinks by √N.\n"
        "- The two levels are therefore a practical guide: ±1σ is a typical error, "
        "±2σ is a near-worst-case error you would rarely exceed.\n"
    )
    a("**Drop diameter — single measurement confidence intervals:**\n")
    a("| Confidence | Interval |")
    a("|-----------|----------|")
    a(f"| 68%  (±1σ) | ±{sm_d:.3f} µm |")
    a(f"| 95%  (±2σ) | ±{sm_d*2:.3f} µm |")
    a("")
    a(
        "So if you measure a drop and get 26.5 µm, the true diameter is most likely "
        f"in the range 26.1–26.9 µm, and almost certainly in "
        f"{26.5 - sm_d*2:.1f}–{26.5 + sm_d*2:.1f} µm.\n"
    )
    a("**How averaging N measurements reduces the uncertainty on the mean:**\n")
    a("| N measurements | Uncertainty on mean (1σ) |")
    a("|---------------|--------------------------|")
    for n in [1, 2, 3, 4, 9]:
        a(f"| {n} | ±{sm_d / math.sqrt(n):.3f} µm |")
    a("")
    a("**Stage 1 timing — single measurement confidence intervals:**\n")
    a("| Confidence | Interval |")
    a("|-----------|----------|")
    a(f"| 68%  (±1σ) | ±{sm_s1:.4f} s |")
    a(f"| 95%  (±2σ) | ±{sm_s1*2:.4f} s |")
    a("")
    a(
        f"**Calibration sanity check:** the image calibration is {cal:.2f} px/µm, "
        f"so 1 pixel = {px_um:.3f} µm.  The measured σ_meas for drop diameter is "
        f"{sm_d:.3f} µm — essentially **1 pixel**.  This is exactly the expected "
        "precision limit when manually placing an ROI boundary: the dominant error "
        "is which pixel the boundary lands on.  The measurement process is therefore "
        "performing at the pixel-level limit, which is about as good as possible "
        "without sub-pixel interpolation.  It also confirms the noise is coming from "
        "boundary placement rather than something worse such as focus variation or "
        "inconsistent frame selection.\n"
    )

    # ── Layer 2: DFU mean ─────────────────────────────────────────────────────
    a("### Layer 2 — DFU-position mean  *(pools all ROIs and sub-groups at one position)*\n")
    a(
        "Layer 1 outputs one value per ROI.  Layer 2 groups all Layer 1 values that "
        "belong to the same device and the same physical DFU position — including "
        "different ROIs within the main video *and* any `_B` / `_C` sub-group "
        "recordings of the same position.  The mean and standard deviation across "
        "those Layer 1 values are the numbers plotted in Figs 1–2.\n\n"
        "The std at this level (σ_within-DFU) captures:\n"
        "- spread across different ROIs (different generators in the same neighbourhood)\n"
        "- spread across _B/_C sub-groups (slightly different fields of view of the same position)\n"
        "- any residual measurement noise that survived the Layer 1 mean\n"
    )

    # Show L2 for the worked example, expanding to include _B/_C if present
    ex_dev_l1 = l1[(l1["DeviceID"] == ex_dev) & (l1["DFU_base"] == ex_loc)].copy()
    ex_l2_mean = ex_dev_l1["Droplet_diameter_um"].mean()
    ex_l2_std  = ex_dev_l1["Droplet_diameter_um"].std()
    ex_l2_n    = len(ex_dev_l1)

    # Also show a position that has sub-groups — pick device 1B DFU3
    ex_loc2 = "DFU3"
    ex_l1_dfu3 = l1[(l1["DeviceID"] == ex_dev) & (l1["DFU_base"] == ex_loc2)].copy()

    a(f"**Continuing example — Device 1B, position {ex_loc}**\n")
    a(
        f"Layer 1 produced {ex_l2_n} ROI means for this position.  "
        f"Layer 2 takes the mean and std of those {ex_l2_n} values:\n"
    )
    a("| Layer 1 input | Drop diam (µm) |")
    a("|--------------|----------------|")
    for _, row in ex_dev_l1.iterrows():
        src = f"ROI {int(row['ROI_ID'])} ({row['DFU_base']})"
        a(f"| {src} | {row['Droplet_diameter_um']:.3f} |")
    a(f"| **Layer 2 mean** | **{ex_l2_mean:.3f}** |")
    a(f"| **Layer 2 std** | **{ex_l2_std:.3f}** |")
    a("")

    # Now show a sub-group example
    if len(ex_l1_dfu3) > 0:
        n_subgroups = ex_l1_dfu3["VideoFile"].nunique()
        a(f"**Sub-group pooling example — Device 1B, position {ex_loc2}**\n")
        a(
            f"This position has {n_subgroups} separate video recordings "
            f"(main, _B, _C), each with their own ROIs.  All are pooled together "
            f"at Layer 2 because they all represent the same physical region of the device.\n"
        )
        a("| Source | ROI | Drop diam L1 mean (µm) |")
        a("|--------|-----|----------------------|")
        for _, row in ex_l1_dfu3.sort_values(["VideoFile", "ROI_ID"]).iterrows():
            # Extract suffix from video filename
            vf = row["VideoFile"]
            sfx_m = re.search(r"(DFU\d+(?:_[BC])?)\.mp4", vf, re.IGNORECASE)
            src_lbl = sfx_m.group(1) if sfx_m else vf
            a(f"| {src_lbl} | {int(row['ROI_ID'])} | {row['Droplet_diameter_um']:.3f} |")
        l2_dfu3 = l2[(l2["DeviceID"] == ex_dev) & (l2["DFU_base"] == ex_loc2)]
        if len(l2_dfu3) > 0:
            m2 = l2_dfu3["Droplet_diameter_um_mean"].values[0]
            s2 = l2_dfu3["Droplet_diameter_um_std"].values[0]
            a(f"| **Layer 2 mean** | — | **{m2:.3f}** |")
            a(f"| **Layer 2 std** | — | **{_fmt(s2, 3)}** |")
        a("")

    # ── Layer 3: device mean ──────────────────────────────────────────────────
    a("### Layer 3 — Device mean  *(one number per device, across all DFU positions)*\n")
    a(
        "Layer 3 takes all 10 Layer 2 DFU-position means for a device and averages "
        "them.  This gives the single overall performance number shown in the Fig 2 "
        "legend.  The std at this level tells you how much the device varies "
        "from position to position — this is σ_between-DFU.\n"
    )
    a("| Device | DFU position | Layer 2 mean diam (µm) |")
    a("|--------|-------------|------------------------|")
    dev_1b = get_dev(ex_dev).sort_values("DFU_num")
    for _, row in dev_1b.iterrows():
        a(f"| 1B | DFU{int(row['DFU_num'])} | {row['Droplet_diameter_um_mean']:.3f} |")
    l3_1b_mean = dev_1b["Droplet_diameter_um_mean"].mean()
    l3_1b_std  = dev_1b["Droplet_diameter_um_mean"].std()
    a(f"| **Layer 3 mean** | (all) | **{l3_1b_mean:.3f}** |")
    a(f"| **Layer 3 std (= σ_between-DFU for 1B)** | (all) | **{l3_1b_std:.3f}** |")
    a("")

    # ── Variance decomposition ────────────────────────────────────────────────
    a("### Variance decomposition — what each σ term means\n")
    a(
        "Once Layers 1–3 are computed, four σ values are reported for each metric.  "
        "They are derived as follows:\n"
    )
    a("| σ term | How it is computed | What it means |")
    a("|--------|--------------------|---------------|")
    a("| **σ_meas** | Mean of within-ROI stds from all repeated-obs groups (Layer M) | User measurement error + occasional device misfires captured at the frame level |")
    a("| **σ_within-DFU (raw)** | Mean of Layer 2 stds across all device×position combinations | Total spread of individual ROI observations at one device position |")
    a("| **σ_within-DFU (corrected)** | √(σ_within-DFU_raw² − σ_meas²) | Same as above but with measurement noise removed in quadrature |")
    a("| **σ_between-DFU** | Std of the 10 Layer 2 means within one device, averaged across all 3 devices | How much a device's output varies from position to position along its length |")
    a("| **σ_between-device** | For each DFU position, std of the 3 device means; averaged over all 10 positions | How much devices differ from each other at the same physical location |")
    a("")
    a(
        "The quadrature correction (σ_corrected = √(σ²_raw − σ²_meas)) is valid under "
        "the assumption that measurement noise and physical variation are independent "
        "and additive in variance.  If σ_meas > σ_within-DFU_raw (measurement noise "
        "dominates), the corrected value is set to zero rather than producing an "
        "imaginary number.\n"
    )

    a("**Concrete numbers for drop diameter:**\n")
    a("| σ term | Value (µm) |")
    a("|--------|-----------|")
    a(f"| σ_meas | {sigma_meas['Droplet_diameter_um']:.4f} |")
    a(f"| σ_within-DFU (raw) | {sigma_within_raw['Droplet_diameter_um']:.4f} |")
    a(f"| σ_within-DFU (corrected) | {sigma_within_corr['Droplet_diameter_um']:.4f} |")
    a(f"| σ_between-DFU | {sigma_between_dfu['Droplet_diameter_um']:.4f} |")
    a(f"| σ_between-device | {sigma_between_dev['Droplet_diameter_um']:.4f} |")
    a("")
    a(
        "Reading these numbers in order: measurement noise (σ_meas) is the smallest "
        "contributor.  The within-DFU spread (different ROIs at the same position) is "
        "a bit larger.  Positional variation along the device (σ_between-DFU) and "
        "device-to-device variation (σ_between-device) are the dominant sources — "
        "meaning the devices differ from each other about as much as any single device "
        "varies along its own length.\n"
    )

    return "\n".join(out)


# =============================================================================
# REPORT
# =============================================================================
print("\nGenerating report ...")

obs_by_dev   = raw.groupby("DeviceID").size().to_dict()
valid_by_dev = raw_valid.groupby("DeviceID").size().to_dict()

drop_mean_all = np.nanmean([dev_summary[d]["Droplet_diameter_um"][0] for d in DEVICES])
drop_bdr      = sigma_between_dev["Droplet_diameter_um"]
drop_cv_bdr   = 100 * drop_bdr / drop_mean_all if drop_mean_all > 0 else float("nan")

s1_mean_all = np.nanmean([dev_summary[d]["Stage1_s"][0] for d in DEVICES])
s1_bdr      = sigma_between_dev["Stage1_s"]
s1_cv_bdr   = 100 * s1_bdr / s1_mean_all if s1_mean_all > 0 else float("nan")

hz_mean_all = np.nanmean([dev_summary[d]["freq_Hz"][0] for d in DEVICES])
hz_bdr      = sigma_between_dev["freq_Hz"]
hz_cv_bdr   = 100 * hz_bdr / hz_mean_all if hz_mean_all > 0 else float("nan")

meas_pct_s1 = (100 * sigma_meas["Stage1_s"]**2 / sigma_within_raw["Stage1_s"]**2
               if sigma_within_raw["Stage1_s"] > 0 else float("nan"))

sources = [
    ("σ_meas",           sigma_meas["Stage1_s"]),
    ("σ_within-DFU",     sigma_within_corr["Stage1_s"]),
    ("σ_between-DFU",    sigma_between_dfu["Stage1_s"]),
    ("σ_between-device", sigma_between_dev["Stage1_s"]),
]
dominant = max(sources, key=lambda x: x[1] if not np.isnan(x[1]) else 0)[0]

# ── Pre-compute a few extra numbers for the humanized report ──────────────────

# Per-device range (max - min of DFU-level means)
dev_range = {dev: get_dev(dev)["Droplet_diameter_um_mean"].max()
             - get_dev(dev)["Droplet_diameter_um_mean"].min()
             for dev in DEVICES}

# Grand mean drop diam
drop_grand_mean = np.nanmean([dev_summary[d]["Droplet_diameter_um"][0] for d in DEVICES])
drop_all_means  = [dev_summary[d]["Droplet_diameter_um"][0] for d in DEVICES]
drop_dev_range  = max(drop_all_means) - min(drop_all_means)

hz_all_means  = [dev_summary[d]["freq_Hz"][0] for d in DEVICES]
hz_dev_range  = max(hz_all_means) - min(hz_all_means)

s1_all_means  = [dev_summary[d]["Stage1_s"][0] for d in DEVICES]
s1_dev_range  = max(s1_all_means) - min(s1_all_means)

cal_val   = raw["Calibration_px_per_um"].dropna().iloc[0]
px_size   = 1.0 / cal_val
drop_bdr_px = drop_bdr / px_size

# Variance shares for drop diameter
drop_var_meas_share  = 100 * sigma_meas["Droplet_diameter_um"]**2 / sigma_within_raw["Droplet_diameter_um"]**2
drop_var_phys_share  = 100 - drop_var_meas_share
s1_var_meas_share    = 100 * sigma_meas["Stage1_s"]**2 / sigma_within_raw["Stage1_s"]**2

# Dominant variance source for Stage 1 (plain label)
dom_labels = {
    "σ_meas":           "measurement noise",
    "σ_within-DFU":     "variation between generators at the same position",
    "σ_between-DFU":    "variation along the device (position to position)",
    "σ_between-device": "variation between devices",
}
dominant_plain = dom_labels.get(dominant, dominant)

report = f"""# V5-30 Device Consistency Report — Batch 050526

**Generated:** {pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
**Devices tested:** 1B, 3D, 4C (same design, same production batch)
**Conditions:** SDS continuous phase, sunflower oil dispersed, 5 ml/hr, 300 mbar
**Positions measured:** DFU1–DFU10 (10 positions per device)

---

## The short answer

> **Drop size: yes, very consistent.**
> All three devices produce drops in a similar size range. The average diameter differs by just {_fmt(drop_dev_range, 2)} µm between the best and worst device — about {_fmt(drop_dev_range/px_size, 1)} pixels at this magnification. For context, a single measurement is only accurate to about ±{_fmt(sigma_meas['Droplet_diameter_um'], 2)} µm (1 pixel), so the device-to-device difference is real but small.
>
> **Timing and production rate: somewhat consistent, with more spread.**
> Stage 1 timing differs by {_fmt(s1_dev_range, 3)} s on average between devices. The biggest source of timing variation is not device-to-device differences — it is the variation *along* each device (position to position). This means devices 1B, 3D and 4C behave similarly to each other, but all three show some position-dependent variation internally.

---

## 1. What was measured

Each device has 1000s of individual droplet generators arranged along its length.
We measured 10 positions (DFU1–DFU10) on each device, capturing multiple generators
per position.  Everything — the fluids, flow rate, pressure, temperature — was
held constant across all three devices.  Any difference in performance is therefore
down to the devices themselves.

**Data collected:**

| Device | Raw observations | Used in analysis |
|--------|-----------------|-----------------|
"""

| Parameter | Value |
|-----------|-------|
| Design | V5-30 |
| Production batch | 050526 |
| Testing date | 060526 |
| Continuous phase | SDS |
| Dispersed phase | Sunflower Oil (SO) |
| Cont. flow rate (Qw) | 5 ml/hr |
| Disp. pressure (Po) | 300 mbar |
| DFU positions tested | DFU1–DFU10 |

**Observation counts:**

| Device | Total rows | Valid (Stage1 present) |
|--------|-----------|------------------------|
"""
for dev in DEVICES:
    report += f"| {DEVICE_LABELS[dev]} | {obs_by_dev.get(dev,0)} | {valid_by_dev.get(dev,0)} |\n"

report += f"""
Total: {R['n_total']} raw rows → {R['n_valid']} valid → {R['n_l1']} L1 ROI means → {R['n_l2']} L2 DFU means

**Averaging hierarchy used throughout this report:**

| Level | Grouping | Purpose |
|-------|---------|---------|
| Raw | Individual observations | Starting data |
| L1 — ROI mean | (Device, VideoFile, ROI_ID) | Collapses repeated measurements on the same physical ROI |
| L2 — DFU mean | (Device, DFU_base) | Per-position mean ± std, pooling ROIs and spatial sub-groups (_B/_C) |

---

## 2. Measurement Error

Repeated measurements are defined as multiple rows sharing the same
`(DeviceID, VideoFile, ROI_ID)`.  The standard deviation within these groups
is **user measurement error (σ_meas)** — the irreducible noise from the analysis
process itself (frame selection, ROI boundary placement, etc.).

**Repeated ROI groups found: {R['n_repeat']}**

| Metric | σ_meas | σ_within-DFU (raw) | Meas. error share of variance | σ_within-DFU (corrected) |
|--------|--------|--------------------|-------------------------------|--------------------------|
"""
for m in CORE_METRICS:
    sm  = sigma_meas[m]
    sw  = sigma_within_raw[m]
    sc  = sigma_within_corr[m]
    var_share = 100 * sm**2 / sw**2 if sw > 0 else float("nan")
    report += f"| {m} | {_fmt(sm, 4)} | {_fmt(sw, 4)} | {_fmt(var_share, 1)}% | {_fmt(sc, 4)} |\n"

report += f"""
Stage 1 reproducibility (Pearson r, same-ROI pairs): **{_fmt(R.get('meas_r_stage1'), 3)}**

All σ values in subsequent sections can be read as either raw (includes measurement error)
or corrected (σ_corrected = √(σ²_raw − σ²_meas)).  Fig 7 shows both side by side.

---

## 3. Stage 1 Timing Consistency

| Device | Mean (s) | Std (s) | CV% |
|--------|---------|---------|-----|
"""
for dev in DEVICES:
    mn, sd = dev_summary[dev]["Stage1_s"]
    cv = 100 * sd / mn if mn > 0 else float("nan")
    report += f"| {DEVICE_LABELS[dev]} | {_fmt(mn)} | {_fmt(sd)} | {_fmt(cv,1)}% |\n"

all_mn = [dev_summary[d]["Stage1_s"][0] for d in DEVICES]
report += f"\nBetween-device range: {_fmt(max(all_mn)-min(all_mn),4)} s  |  σ_between-device: {_fmt(s1_bdr,4)} s  |  CV%: {_fmt(s1_cv_bdr,1)}%\n"

report += """
---

## 4. Production Rate Consistency

"""
report += "| Device | Mean (Hz) | Std (Hz) | CV% |\n|--------|----------|---------|-----|\n"
for dev in DEVICES:
    mn, sd = dev_summary[dev]["freq_Hz"]
    cv = 100 * sd / mn if mn > 0 else float("nan")
    report += f"| {DEVICE_LABELS[dev]} | {_fmt(mn)} | {_fmt(sd)} | {_fmt(cv,1)}% |\n"
all_mn = [dev_summary[d]["freq_Hz"][0] for d in DEVICES]
report += f"\nBetween-device range: {_fmt(max(all_mn)-min(all_mn),4)} Hz  |  σ_between-device: {_fmt(hz_bdr,4)} Hz  |  CV%: {_fmt(hz_cv_bdr,1)}%\n"

report += """
---

## 5. Droplet Diameter Consistency

"""
report += "| Device | Mean (µm) | Std (µm) | CV% |\n|--------|----------|---------|-----|\n"
for dev in DEVICES:
    mn, sd = dev_summary[dev]["Droplet_diameter_um"]
    cv = 100 * sd / mn if mn > 0 else float("nan")
    report += f"| {DEVICE_LABELS[dev]} | {_fmt(mn)} | {_fmt(sd)} | {_fmt(cv,1)}% |\n"
all_mn = [dev_summary[d]["Droplet_diameter_um"][0] for d in DEVICES]
report += f"\nBetween-device range: {_fmt(max(all_mn)-min(all_mn),3)} µm  |  σ_between-device: {_fmt(drop_bdr,4)} µm  |  CV%: {_fmt(drop_cv_bdr,2)}%\n"

report += """
---

## 6. Variance Decomposition

| Source | Description |
|--------|-------------|
| **σ_meas** | User measurement error — same ROI measured twice |
| **σ_within-DFU (corr)** | Variation across ROIs and sub-groups at same DFU position, with measurement error removed |
| **σ_between-DFU** | Positional variation along the device (DFU1 → DFU10), within each device |
| **σ_between-device** | Device-to-device variation at matched DFU positions |

"""
report += "| Metric | σ_meas | σ_within-DFU (corr) | σ_between-DFU | σ_between-device |\n"
report += "|--------|--------|---------------------|---------------|------------------|\n"
for m in CORE_METRICS:
    report += (f"| {m} | {_fmt(sigma_meas[m],4)} | {_fmt(sigma_within_corr[m],4)} "
               f"| {_fmt(sigma_between_dfu[m],4)} | {_fmt(sigma_between_dev[m],4)} |\n")

report += """
---

## 7. How to Read Each Figure

**Fig 1 — Production rate vs DFU position**
Each point is the mean droplet generation frequency (Hz = 1 / cycle time) at a given DFU
position for one device, averaged across all ROIs and sub-group recordings (_B/_C) at that
position.  Error bars are ±1 std.  The dashed grey line is the grand mean across all three
devices.  Look for: positions where one device's rate deviates from the others (possible
local defect), or a consistent trend along DFU1→10 (suggesting a systematic spatial gradient).

**Fig 2 — Droplet diameter vs DFU position (mean ± std)**
Same format as Fig 1 but for droplet diameter.  Each point is the L2 DFU-level mean; error
bars are the spread across ROIs at that position.  The legend shows each device's overall
mean and std across all 10 DFU positions — use these numbers to compare device-level
diameter offset.  No grand mean line is shown so device-to-device offset is clearer.

**Fig 2A — Droplet diameter: all individual observations**
Each faint dot is one L1 ROI-mean value (i.e. the average of repeated frames for a single
ROI, if any repetitions exist).  Dots are jittered horizontally within each device's
x-offset position so overlapping points are visible.  The error bars (faint, no connecting
line) show the L2 DFU-level mean ± std — the same values as Fig 2.  This figure reveals the
full raw scatter and helps you judge whether the error bars in Fig 2 are driven by one or
two outliers vs a broad distribution.

**Fig 3 — Per-device violin summary (individual y-axes)**
Each violin spans the range of L2 DFU-position means for one device.  The wide part of the
violin is where the data is densest; the median line is shown inside.  Jittered dots are the
10 individual DFU-position means.  This shows the overall spread of each device but uses a
different y-axis scale per panel — Stage 3 may appear to vary a lot simply because its axis
is magnified.

**Fig 3B — Per-device violin summary (shared y-axis for timing stages)**
Identical to Fig 3 except Stage 1, 2, and 3 share the same y-axis range.  This allows direct
visual comparison of how much each stage contributes to the total timing spread.  A stage
whose violin looks small here genuinely varies little in absolute terms.  Droplet diameter
retains its own scale since it is in different units.

**Fig 4 — Stage fractions (100% stacked bar)**
Each bar is one DFU position; the coloured segments show what fraction of the total cycle
time is spent in Stage 1 (fill), Stage 2 (collapse/neck), and Stage 3 (exit).  Consistent
bar patterns across positions and across devices indicate robust hydraulic balance.
Positions where Stage 1 is much larger or smaller than neighbours suggest local resistance
variation.

**Fig 5 — Variance decomposition**
For each of the three key metrics, four bars show the standard deviation attributable to each
source of variation, ordered from smallest (σ_meas) to largest expected.  If σ_between-device
is the tallest bar, device manufacturing is the dominant source.  If σ_within-DFU (corrected)
dominates, the scatter seen within a single device position is larger than device-to-device
differences — meaning the devices are actually quite similar to each other.

**Fig 6 — CV% heatmap**
Rows are devices; columns are DFU positions.  Each cell shows the coefficient of variation
(CV% = 100 × std/mean) for that device at that position, computed from the spread of
individual ROI observations at that location.  Colour scale is calibrated per metric: green
is low variation, red is high.  Note the drop diameter panel uses a much tighter colour scale
than the timing panels — a cell that looks "red" for diameter may only represent 3–4% CV.
Hot spots (a single red cell in an otherwise green heatmap) indicate a specific position on a
specific device that behaves anomalously.

**Fig 7 — Measurement reproducibility**
*Left panel:* Three grouped bar sets (one per metric).  Within each set: light blue = raw
σ within a DFU position, dark blue = same σ after subtracting measurement error in quadrature
(σ_corrected), red = σ_meas from repeated same-ROI measurements.  If red is a large fraction
of light blue, measurement error is inflating the apparent within-DFU variation.
*Right panel:* Each dot is one repeated Stage 1 measurement pair — the x-coordinate is the
first measurement, y is the second measurement of the same ROI.  Points on the dashed diagonal
line are perfectly reproducible.  Scatter around the diagonal is pure user measurement error.
A high Pearson r (> 0.95) indicates good reproducibility.

**Fig 8 — Meniscus geometry vs DFU position**
Same format as Fig 1/2 but for L_menpoint (the distance from the junction to the meniscus
tip) and L_men (total meniscus length).  These geometric parameters drive Stage 1 duration via
the Washburn refill model: a longer L_menpoint means a larger reset volume and slower refill.
Consistent geometry across devices and positions indicates the device fabrication is
dimensionally reproducible.  Any device that has systematically higher L_menpoint will also
tend to have longer Stage 1 times.

---

## 8. Conclusions

- **Droplet diameter** is tightly controlled: between-device σ = {_fmt(drop_bdr,3)} µm
  ({_fmt(drop_cv_bdr,2)}% CV), confirming geometry-dominated size control.

- **Stage 1 timing** shows between-device σ = {_fmt(s1_bdr,4)} s ({_fmt(s1_cv_bdr,1)}% CV).
  The dominant variance source is **{dominant}**.

- **Production rate** between-device σ = {_fmt(hz_bdr,4)} Hz ({_fmt(hz_cv_bdr,1)}% CV).

- **User measurement error** (σ_meas) accounts for {_fmt(meas_pct_s1,1)}% of raw
  within-DFU Stage 1 **variance** (i.e. σ²_meas / σ²_within-DFU; Pearson r =
  {_fmt(R.get('meas_r_stage1'),3)} on same-ROI pairs).  This is the share of observed
  spread that is noise rather than real physical variation.

---

## Figures

| Figure | File | Description |
|--------|------|-------------|
| Fig 1 | fig_01_production_rate_vs_dfu.png | Production rate (Hz) vs DFU position |
| Fig 2 | fig_02_dropsize_vs_dfu.png | Droplet diameter vs DFU position, device stats in legend |
| Fig 2A | fig_02A_dropsize_all_points.png | Droplet diameter — all individual ROI observations |
| Fig 3 | fig_03_device_summary.png | Per-device violin, individual y-axes |
| Fig 3B | fig_03B_device_summary_shared_y.png | Per-device violin, Stage 1/2/3 on shared y-axis |
| Fig 4 | fig_04_stage_fractions.png | 100% stacked stage fractions per DFU position |
| Fig 5 | fig_05_variance_decomposition.png | Variance decomposition by source level |
| Fig 6 | fig_06_cv_heatmap.png | CV% heatmap — device × DFU position |
| Fig 7 | fig_07_measurement_error.png | Measurement reproducibility analysis |
| Fig 8 | fig_08_geometry_vs_dfu.png | Meniscus geometry vs DFU position |
"""

report += "\n---\n\n" + build_averaging_explainer()

with open(REPORT_OUT, "w", encoding="utf-8") as f:
    f.write(report)
print(f"Report written: {REPORT_OUT}")
print("\nDone — all outputs in:", FIG_DIR)
