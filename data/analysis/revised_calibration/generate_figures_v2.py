"""
generate_figures_v2.py
======================
Revised figures saved to figures_v2/.

Changes vs v1:
  Fig 1 left : scatter-only per stage (no bars, no arrows), total-time mean connected by curve
  Fig 1 right: wider bars
  Fig 2      : linear axes (no log-log), extended y-range, no inset text box, coolwarm gradient
  Fig 3      : remove β annotation, y-axis label corrected
  Fig 4      : skipped (pending review)
  Fig 5 right: remove "perfect model" dashed line and grey ±5% band
  Fig 6      : updated legend text, remove annotation, coolwarm, no diamonds/errorbars,
               right plot cleaned (no shaded area, no baseline dashed line)
  Fig 7      : no diamonds/errorbars, coolwarm, mean as y-axis tick, table removed

Run from project root:
    .venv/Scripts/python.exe data/analysis/revised_calibration/generate_figures_v2.py
"""

import os
import re
import sys
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats
from scipy.interpolate import CubicSpline

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

CSV_PATH    = os.path.join(PROJECT_ROOT, "data", "analysis", "stage_timing_clean.csv")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "v5_30.yaml")
FIG_DIR     = os.path.join(SCRIPT_DIR, "figures_v2")
os.makedirs(FIG_DIR, exist_ok=True)

from stepgen.config import load_config
from stepgen.models.hydraulics import simulate
from stepgen.models.stage_wise_v3.stage1_physics import compute_rung_resistance

# ── Style ─────────────────────────────────────────────────────────────────────
PO_COLORS = {200: "#4e79a7", 300: "#f28e2b", 400: "#59a14f", 500: "#e15759"}
PO_LIST   = [200, 300, 400, 500]
FIGSIZE   = (11, 5)
DPI       = 150
QW_MLHR   = 5.0
T_S2_LOCKED = 0.20
P_CAP     = 1202.0    # Pa

# Colormap used for DFU position across all figures:
# blue (DFU=0, upstream) → red (DFU=10, downstream)
DFU_CMAP = "coolwarm"
DFU_VMIN, DFU_VMAX = 0, 10

plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
})

# ── Load config + network ─────────────────────────────────────────────────────
print(f"Loading config: {CONFIG_PATH}")
config    = load_config(CONFIG_PATH)
R_rung    = compute_rung_resistance(config)
Nmc       = config.geometry.Nmc
exit_w    = config.geometry.junction.exit_width
exit_h    = config.geometry.junction.exit_depth
V_NOMINAL = exit_w ** 2 * exit_h

print("Running hydraulic network...")
net = {}
for po in PO_LIST:
    sol = simulate(config, Po_in_mbar=po, Qw_in_mlhr=QW_MLHR, P_out_mbar=0.0)
    net[po] = sol

def get_dp_local(sol, dfu_num):
    try:
        v = float(dfu_num)
        if np.isnan(v):
            return float(np.mean(sol.P_oil - sol.P_water))
    except (TypeError, ValueError):
        return float(np.mean(sol.P_oil - sol.P_water))
    idx = max(0, min(int(round(v / 10.0 * (Nmc - 1))), Nmc - 1))
    return float(sol.P_oil[idx] - sol.P_water[idx])

# ── Load and prepare data ─────────────────────────────────────────────────────
print(f"\nLoading: {CSV_PATH}")
df_raw = pd.read_csv(CSV_PATH)

def parse_dfu_num(label):
    if pd.isna(label):
        return np.nan
    m = re.match(r"^(\d+)", str(label).strip())
    return int(m.group(1)) if m else np.nan

df_raw["dfu_num"] = df_raw["DFU_label"].apply(parse_dfu_num)
df = df_raw[df_raw["Po_mbar"].isin(PO_LIST)].copy()

dp_local = [get_dp_local(net[int(r["Po_mbar"])], r["dfu_num"]) for _, r in df.iterrows()]
df["DP_rung_local"] = dp_local
df["V_reset_m3"]    = df["V_reset_um3"] * 1e-18
dp_mean_by_po       = {po: float(np.mean(net[po].P_oil - net[po].P_water)) for po in PO_LIST}
df["DP_rung_mean"]  = df["Po_mbar"].map(dp_mean_by_po)

# C_visc variants
df["t_pred_base"] = V_NOMINAL * R_rung / df["DP_rung_mean"]
df["C_visc_base"] = df["model_S1_t"] / df["t_pred_base"]
mask_v = df["V_reset_m3"].notna() & (df["V_reset_m3"] > 0)
df.loc[mask_v, "t_pred_A"] = df.loc[mask_v, "V_reset_m3"] * R_rung / df.loc[mask_v, "DP_rung_mean"]
df.loc[mask_v, "C_visc_A"] = df.loc[mask_v, "model_S1_t"] / df.loc[mask_v, "t_pred_A"]
df.loc[mask_v, "DP_eff_B"] = df.loc[mask_v, "DP_rung_mean"] - P_CAP
df.loc[mask_v, "t_pred_B"] = df.loc[mask_v, "V_reset_m3"] * R_rung / df.loc[mask_v, "DP_eff_B"]
df.loc[mask_v, "C_visc_B"] = df.loc[mask_v, "model_S1_t"] / df.loc[mask_v, "t_pred_B"]

# Device Hz
df["rate_obs"]   = 1.0 / df["total_t"]
df["t_S1_fixed"] = V_NOMINAL * R_rung / df["DP_rung_local"]
df["rate_fixed"] = 1.0 / (df["t_S1_fixed"] + T_S2_LOCKED)
df.loc[mask_v, "t_S1_meas"] = df.loc[mask_v, "V_reset_m3"] * R_rung / df.loc[mask_v, "DP_rung_local"]
df.loc[mask_v, "rate_meas"] = 1.0 / (df.loc[mask_v, "t_S1_meas"] + T_S2_LOCKED)

# Per-Po summary
by_po = df.groupby("Po_mbar").agg(
    S1_mean=("model_S1_t",  "mean"),
    S1_std =("model_S1_t",  "std"),
    S2_mean=("exp_s3_t",    "mean"),
    S2_std =("exp_s3_t",    "std"),
    total_mean=("total_t",  "mean"),
    n=("model_S1_t",        "count"),
).reset_index()
by_po["S1_frac_pct"] = by_po["S1_mean"] / by_po["total_mean"] * 100
by_po["S2_frac_pct"] = by_po["S2_mean"] / by_po["total_mean"] * 100
s1_200 = float(by_po.loc[by_po["Po_mbar"]==200, "S1_mean"].values[0])
s2_200 = float(by_po.loc[by_po["Po_mbar"]==200, "S2_mean"].values[0])
by_po["S1_speedup"] = s1_200 / by_po["S1_mean"]
by_po["S2_speedup"] = s2_200 / by_po["S2_mean"]
S1_SPEEDUP  = float(by_po.loc[by_po["Po_mbar"]==500, "S1_speedup"].values[0])
S2_SPEEDUP  = float(by_po.loc[by_po["Po_mbar"]==500, "S2_speedup"].values[0])
S2_GLOBAL_MEAN = float(df["exp_s3_t"].mean())
D_DROP_MEAN    = float(df["D_drop"].mean())

log_po_arr = np.log(np.array(PO_LIST, dtype=float))
log_s1_arr = np.log(by_po["S1_mean"].values)
log_s2_arr = np.log(by_po["S2_mean"].values)
s1_slope, s1_int, *_ = stats.linregress(log_po_arr, log_s1_arr)
s2_slope, s2_int, *_ = stats.linregress(log_po_arr, log_s2_arr)

dp_range   = np.array([float(np.mean(net[po].P_oil - net[po].P_water)) for po in PO_LIST])
t_base_arr = V_NOMINAL * R_rung / dp_range
base_slope, base_int, *_ = stats.linregress(log_po_arr, np.log(t_base_arr))

rate_table = []
for po in PO_LIST:
    sub = df[df["Po_mbar"] == po]
    obs   = sub["rate_obs"].mean()
    fixed = sub["rate_fixed"].mean()
    meas  = sub["rate_meas"].mean()
    rate_table.append({
        "po": po, "obs": obs, "fixed": fixed, "meas": meas,
        "err_fixed": (fixed - obs) / obs * 100,
        "err_meas":  (meas  - obs) / obs * 100 if not np.isnan(meas) else np.nan,
    })

print("Data prepared.\n")

# =============================================================================
# FIGURE 1 — Cycle overview (REVISED)
# =============================================================================
print("Figure 1...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
rng = np.random.default_rng(42)

po_arr = np.array(PO_LIST, dtype=float)

# ── Left: scatter only, two groups per Po ────────────────────────────────────
S1_COLOR = "#4e79a7"
S2_COLOR = "#FF9800"
GROUP_OFFSET = 10   # mbar — half-separation between S1 and S2 groups

for po in PO_LIST:
    sub = df[df["Po_mbar"] == po]
    n   = len(sub)
    # Stage 1 group (left of Po)
    j1 = rng.uniform(-6, 6, n)
    ax1.scatter(po - GROUP_OFFSET + j1, sub["model_S1_t"],
                color=S1_COLOR, s=22, alpha=0.75, edgecolors="none", zorder=4)
    # Stage 2 group (right of Po)
    j2 = rng.uniform(-6, 6, n)
    ax1.scatter(po + GROUP_OFFSET + j2, sub["exp_s3_t"],
                color=S2_COLOR, s=22, alpha=0.75, edgecolors="none", zorder=4)

# Mean total time: one point per Po, connected by smooth cubic spline
total_means = by_po["total_mean"].values   # 4 values
cs = CubicSpline(po_arr, total_means)
po_smooth = np.linspace(200, 500, 300)
ax1.plot(po_smooth, cs(po_smooth), color="black", lw=1.65, zorder=5)
ax1.plot(po_arr, total_means, "x", color="black", markersize=8,
         markeredgewidth=1.8, zorder=6, label="Mean total cycle time")

# Manual legend entries for the scatter groups
from matplotlib.lines import Line2D
legend_handles = [
    Line2D([0], [0], marker="o", color="none", markerfacecolor=S1_COLOR,
           markersize=7, label="Stage 1 (fill)"),
    Line2D([0], [0], marker="o", color="none", markerfacecolor=S2_COLOR,
           markersize=7, label="Stage 2 (snap-off)"),
    Line2D([0], [0], color="black", lw=1.65, marker="x", markersize=8,
           markeredgewidth=1.8, label="Mean total time"),
]
ax1.legend(handles=legend_handles, fontsize=8, loc="upper right")
ax1.set_xlabel("Oil inlet pressure Po [mbar]")
ax1.set_ylabel("Time [s]")
ax1.set_title("Stage timing by pressure")
ax1.set_xticks(PO_LIST)

# ── Right: 100% stacked fraction bars (wider) ─────────────────────────────────
bar_width = 28
s1_fracs  = by_po["S1_frac_pct"].values
s2_fracs  = by_po["S2_frac_pct"].values
ax2.bar(po_arr, s1_fracs, width=bar_width, color=S1_COLOR, alpha=0.85)
ax2.bar(po_arr, s2_fracs, width=bar_width, bottom=s1_fracs, color=S2_COLOR, alpha=0.85)
for po_val, f1, f2 in zip(po_arr, s1_fracs, s2_fracs):
    ax2.text(po_val, f1 / 2,      f"{f1:.0f}%", ha="center", va="center",
             fontsize=8, color="white", fontweight="bold")
    ax2.text(po_val, f1 + f2 / 2, f"{f2:.0f}%", ha="center", va="center",
             fontsize=8, color="white", fontweight="bold")

from matplotlib.patches import Patch
ax2.legend(handles=[Patch(facecolor=S1_COLOR, label="Stage 1"),
                    Patch(facecolor=S2_COLOR, label="Stage 2")],
           fontsize=8, loc="upper right")
ax2.set_xlabel("Oil inlet pressure Po [mbar]")
ax2.set_ylabel("% of total cycle")
ax2.set_title("Stage fractions")
ax2.set_xticks(PO_LIST)
ax2.set_ylim(0, 105)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_01_cycle_overview.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_01 saved")

# =============================================================================
# FIGURE 2 — Stage 1 scaling (REVISED: linear axes, no text box, coolwarm)
# =============================================================================
print("Figure 2...")

fig, ax = plt.subplots(figsize=FIGSIZE)

valid = df.dropna(subset=["model_S1_t", "dfu_num"]).copy()
sc = ax.scatter(valid["Po_mbar"], valid["model_S1_t"],
                c=valid["dfu_num"], cmap=DFU_CMAP, vmin=DFU_VMIN, vmax=DFU_VMAX,
                s=30, alpha=0.80, edgecolors="none", zorder=4)
cb = fig.colorbar(sc, ax=ax, pad=0.02)
cb.set_label("DFU position  (0 = upstream,  10 = downstream)", fontsize=9)

# Reference curves on linear axes (smooth over Po range)
po_fit = np.linspace(180, 520, 300)

# Observed power-law fit
ax.plot(po_fit, np.exp(s1_int) * po_fit**s1_slope,
        color="#4e79a7", lw=2,
        label=f"Obs power-law fit:  t ~ Po$^{{{s1_slope:.2f}}}$")

# Ideal Poiseuille  t ~ Po^-1, anchored to same midpoint
anchor_po = 350.0
anchor_val = np.exp(s1_int) * anchor_po**s1_slope
ideal_int = anchor_val * anchor_po          # constant for t = C / Po
ax.plot(po_fit, ideal_int / po_fit,
        color="grey", lw=1.5, linestyle="--",
        label="Ideal Poiseuille:  t ~ Po$^{-1.00}$")

# Model baseline
baseline_const = np.exp(base_int) * anchor_po**(-base_slope) * anchor_po**base_slope
# simpler: just use the pre-computed t_base_arr with a fit curve
ax.plot(po_fit, np.exp(base_int) * po_fit**base_slope,
        color="#e15759", lw=1.5, linestyle="-.",
        label=f"Model baseline:  t ~ Po$^{{{base_slope:.2f}}}$")

ax.set_xscale("log")
ax.set_xlabel("Oil inlet pressure Po [mbar]")
ax.set_ylabel("Stage 1 time [s]")
ax.set_title("Stage 1 scaling with oil pressure")
ax.set_xticks(PO_LIST)
ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
ax.xaxis.set_minor_formatter(mticker.NullFormatter())
# Extend y-axis to comfortably include all data
y_max = valid["model_S1_t"].max()
ax.set_ylim(0, y_max * 1.10)
ax.legend(loc="upper right", fontsize=8)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_02_stage1_scaling.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_02 saved")

# ── Fig 2b: log-log version (straight reference lines) ───────────────────────
print("Figure 2b (log-log)...")

fig, ax = plt.subplots(figsize=FIGSIZE)

sc = ax.scatter(valid["Po_mbar"], valid["model_S1_t"],
                c=valid["dfu_num"], cmap=DFU_CMAP, vmin=DFU_VMIN, vmax=DFU_VMAX,
                s=30, alpha=0.80, edgecolors="none", zorder=4)
cb = fig.colorbar(sc, ax=ax, pad=0.02)
cb.set_label("DFU position  (0 = upstream,  10 = downstream)", fontsize=9)

ax.plot(po_fit, np.exp(s1_int) * po_fit**s1_slope,
        color="#4e79a7", lw=2,
        label=f"Obs power-law fit:  t ~ Po$^{{{s1_slope:.2f}}}$")
ax.plot(po_fit, ideal_int / po_fit,
        color="grey", lw=1.5, linestyle="--",
        label="Ideal Poiseuille:  t ~ Po$^{-1.00}$")
ax.plot(po_fit, np.exp(base_int) * po_fit**base_slope,
        color="#e15759", lw=1.5, linestyle="-.",
        label=f"Model baseline:  t ~ Po$^{{{base_slope:.2f}}}$")

ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Oil inlet pressure Po [mbar]")
ax.set_ylabel("Stage 1 time [s]")
ax.set_title("Stage 1 scaling with oil pressure  (log-log)")
ax.set_xticks(PO_LIST)
ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
ax.xaxis.set_minor_formatter(mticker.NullFormatter())
# Explicit y ticks across the data range — plain decimal labels
y_ticks = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 1.8]
ax.set_yticks(y_ticks)
ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
ax.yaxis.set_minor_formatter(mticker.NullFormatter())
ax.set_ylim(0.35, 2.0)
ax.yaxis.grid(True, which="major", linestyle=":", linewidth=0.5, alpha=0.5)
ax.legend(loc="upper right", fontsize=8)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_02b_stage1_scaling_loglog.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_02b saved")

# =============================================================================
# FIGURE 3 — Meniscus reset (REVISED: remove β text, corrected y-label)
# =============================================================================
print("Figure 3...")

df_geo = df.dropna(subset=["L_menpoint", "dfu_num"]).copy()
df_geo["dfu_zone"] = df_geo["dfu_num"].apply(
    lambda x: "downstream" if x >= 8 else "central"
)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)

# Left — scatter coloured by Po: dark blue → lighter blue → lighter red → dark red
PO_COLORS_F3 = {200: "#1a5fa8", 300: "#7eb8d4", 400: "#f4957a", 500: "#b81c1c"}
for po in PO_LIST:
    sub = df_geo[df_geo["Po_mbar"] == po]
    ax1.scatter(sub["dfu_num"], sub["L_menpoint"],
                color=PO_COLORS_F3[po], s=28, alpha=0.90,
                label=f"{po} mbar", edgecolors="none", zorder=4)
ax1.axhline(30, color="black", lw=1.2, linestyle="--", label="Nominal (30 µm)")
ax1.axvspan(7.5, 10.5, color="grey", alpha=0.12)
ax1.text(9, 2, "Downstream\nzone", ha="center", fontsize=7.5, color="grey")
ax1.set_xlabel("DFU position")
ax1.set_ylabel("Meniscus reset length [µm]")
ax1.set_title("Meniscus reset length vs DFU")
ax1.set_ylim(0, 38)
ax1.legend(title="Po", fontsize=8, title_fontsize=8)

# Right — grouped bar chart
central_means, central_stds, ds_means, ds_stds = [], [], [], []
for po in PO_LIST:
    sc_  = df_geo[(df_geo["Po_mbar"]==po) & (df_geo["dfu_zone"]=="central")]["L_menpoint"]
    sd_  = df_geo[(df_geo["Po_mbar"]==po) & (df_geo["dfu_zone"]=="downstream")]["L_menpoint"]
    central_means.append(sc_.mean() if len(sc_) else np.nan)
    central_stds.append(sc_.std()  if len(sc_) > 1 else 0)
    ds_means.append(sd_.mean()     if len(sd_) else np.nan)
    ds_stds.append(sd_.std()       if len(sd_) > 1 else 0)

x_pos = np.array(PO_LIST, dtype=float)
w = 14
# Pastel blue for central, pastel red for downstream — no hatch
ax2.bar(x_pos - w/2, central_means, width=w, color="#a8c8e8", alpha=0.95,
        yerr=central_stds, capsize=3,
        label="Central (DFU ≤ 6)", error_kw={"elinewidth": 1, "ecolor": "#5a8fb5"})
ax2.bar(x_pos + w/2, ds_means,      width=w, color="#f4a9a8", alpha=0.95,
        yerr=ds_stds, capsize=3,
        label="Downstream (DFU ≥ 8)", error_kw={"elinewidth": 1, "ecolor": "#c0504d"})
ax2.axhline(30, color="black", lw=1.2, linestyle="--")
ax2.set_xlabel("Po [mbar]")
ax2.set_ylabel("Meniscus reset length [µm]")
ax2.set_title("Mean reset length by zone and Po")
ax2.set_xticks(PO_LIST)
ax2.set_ylim(0, 38)
ax2.legend(fontsize=8)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_03_meniscus_reset.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_03 saved")

# =============================================================================
# FIGURE 4 — skipped
# =============================================================================
print("  fig_04 skipped (pending review)")

# =============================================================================
# FIGURE 5 — Device Hz (REVISED: right plot cleaned)
# =============================================================================
print("Figure 5...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)
rng3 = np.random.default_rng(13)

po_arr_f = np.array(PO_LIST, dtype=float)
obs_arr   = np.array([r["obs"]   for r in rate_table])
fixed_arr = np.array([r["fixed"] for r in rate_table])
meas_arr  = np.array([r["meas"]  for r in rate_table])

w_bar = 12
ax1.bar(po_arr_f - w_bar, obs_arr,   width=w_bar, color="grey",    alpha=0.75, label="Observed")
ax1.bar(po_arr_f,          fixed_arr, width=w_bar, color="#4e79a7", alpha=0.85, label="Fixed V model")
ax1.bar(po_arr_f + w_bar,  meas_arr,  width=w_bar, color="#59a14f", alpha=0.85, label="Measured V model")

# Scatter individual obs rates over grey bars
for po in PO_LIST:
    sub = df[df["Po_mbar"] == po]
    j = rng3.uniform(-4, 4, len(sub))
    ax1.scatter(po - w_bar + j, sub["rate_obs"],
                s=14, color="black", alpha=0.6, zorder=5, edgecolors="none")

ax1.set_xlabel("Po [mbar]")
ax1.set_ylabel("Droplet rate [Hz]")
ax1.set_title("Device droplet rate vs model")
ax1.set_xticks(PO_LIST)
ax1.legend(fontsize=8)

# Right — % error (no perfect-model dashed line, no grey band)
err_fixed = np.array([r["err_fixed"] for r in rate_table])
err_meas  = np.array([r["err_meas"]  for r in rate_table])
ax2.plot(po_arr_f, err_fixed, "o-", color="#4e79a7", lw=1.8, markersize=7,
         label="Fixed V model")
ax2.plot(po_arr_f, err_meas,  "s-", color="#59a14f", lw=1.8, markersize=7,
         label="Measured V model")

ax2.set_xlabel("Po [mbar]")
ax2.set_ylabel("Model error vs observed [%]\n(model − obs) / obs × 100")
ax2.set_title("Model Hz error vs Po")
ax2.set_xticks(PO_LIST)
ax2.legend(fontsize=8)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_05_device_hz.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_05 saved")

# =============================================================================
# FIGURE 6 — Stage 2 (REVISED)
# =============================================================================
print("Figure 6...")

df_s2 = df.dropna(subset=["exp_s3_t"]).copy()
rng4  = np.random.default_rng(21)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIGSIZE)

# Left — Stage 2 individual points, coloured by DFU (coolwarm), no diamonds/errorbars
s2_valid = df_s2.dropna(subset=["dfu_num"])
j = rng4.uniform(-8, 8, len(s2_valid))
sc2 = ax1.scatter(s2_valid["Po_mbar"] + j, s2_valid["exp_s3_t"],
                  c=s2_valid["dfu_num"], cmap=DFU_CMAP,
                  vmin=DFU_VMIN, vmax=DFU_VMAX,
                  s=25, alpha=0.75, edgecolors="none", zorder=4)
cb2 = fig.colorbar(sc2, ax=ax1, pad=0.02)
cb2.set_label("DFU position  (0 = upstream,  10 = downstream)", fontsize=8)

# Power-law fit line
po_fit = np.linspace(180, 520, 300)
ax1.plot(po_fit, np.exp(s2_int) * po_fit**s2_slope,
         color="#e15759", lw=1.8,
         label=f"Fit:  t ~ Po$^{{{s2_slope:.2f}}}$")

# Global mean — updated label
ax1.axhline(S2_GLOBAL_MEAN, color="grey", lw=1.2, linestyle="--",
            label=f"Mean Stage 2 time over exp. data ({S2_GLOBAL_MEAN:.2f} s)")

ax1.set_xlabel("Po [mbar]")
ax1.set_ylabel("Stage 2 time [s]")
ax1.set_title("Stage 2 (snap-off) timing vs Po")
ax1.set_xticks(PO_LIST)
ax1.set_ylim(0, 0.40)
ax1.legend(fontsize=8)

# Right — speedup comparison (no shaded area, no dashed baseline)
po_sp = by_po["Po_mbar"].values
ax2.plot(po_sp, by_po["S1_speedup"].values, "o-", color="#4e79a7",
         lw=2, markersize=7, label=f"Stage 1:  {S1_SPEEDUP:.1f}×")
ax2.plot(po_sp, by_po["S2_speedup"].values, "s-", color="#FF9800",
         lw=2, markersize=7, label=f"Stage 2:  {S2_SPEEDUP:.1f}×")
ax2.set_xlabel("Po [mbar]")
ax2.set_ylabel("Speedup relative to 200 mbar")
ax2.set_title("Stage 1 vs Stage 2 speedup")
ax2.set_xticks(PO_LIST)
ax2.set_ylim(0.5, max(S1_SPEEDUP * 1.15, 3.5))
ax2.legend(fontsize=8)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_06_stage2_analysis.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_06 saved")

# =============================================================================
# FIGURE 7 — Droplet size (REVISED: no diamonds/errorbars, no table, mean tick)
# =============================================================================
print("Figure 7...")

df_drop = df.dropna(subset=["D_drop", "dfu_num"]).copy()
rng5 = np.random.default_rng(33)

fig, ax = plt.subplots(figsize=(8, 4))

j6 = rng5.uniform(-8, 8, len(df_drop))
sc3 = ax.scatter(df_drop["Po_mbar"] + j6, df_drop["D_drop"],
                 c=df_drop["dfu_num"], cmap=DFU_CMAP,
                 vmin=DFU_VMIN, vmax=DFU_VMAX,
                 s=30, alpha=0.80, edgecolors="none", zorder=4)
fig.colorbar(sc3, ax=ax, pad=0.02,
             label="DFU position  (0 = upstream,  10 = downstream)")

# Global mean dashed line
y_lo, y_hi = 20, 35
ax.axhline(D_DROP_MEAN, color="grey", lw=1.3, linestyle="--")
# Label at top of plot area, left-aligned
ax.text(0.02, 0.97, f"Mean  {D_DROP_MEAN:.1f} µm",
        transform=ax.transAxes, fontsize=8.5,
        va="top", ha="left", color="grey")

ax.set_xlabel("Oil inlet pressure Po [mbar]")
ax.set_ylabel("Droplet diameter D_drop [µm]")
ax.set_title("Droplet size vs oil pressure")
ax.set_xticks(PO_LIST)
ax.set_ylim(y_lo, y_hi)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "fig_07_droplet_size_summary.png"), dpi=DPI, bbox_inches="tight")
plt.close(fig)
print("  fig_07 saved")

print(f"\n=== Done. Figures saved to: {FIG_DIR} ===")
