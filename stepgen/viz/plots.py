"""
stepgen.viz.plots
=================
Plotting functions for StepGen simulation and sweep results.

All functions return a ``matplotlib.figure.Figure`` object.
The caller is responsible for saving (``fig.savefig()``) or displaying
(``plt.show()``).  This module never calls ``plt.show()`` itself.

Functions
---------
plot_pressure_profiles(result)              — P_oil(x) and P_water(x)
plot_rung_dP(result)                        — ΔP_rung(x) = P_oil(x) − P_water(x)
plot_rung_flows(result)                     — Q_rung(i) bar chart
plot_rung_frequencies(result, config)       — f_rung(i) bar chart
plot_regime_map(result, config)             — rung classification colour map
plot_operating_map(map_result, metric)      — 2-D heatmap over (Po, Qw) grid
plot_pareto(df, x_col, y_col)              — Pareto front scatter
plot_experiment_comparison(compare_df, metric) — predicted vs measured scatter
plot_layout_schematic(config, layout)       — serpentine chip layout to scale
plot_spatial_comparison(config, result, exp_df) — spatial pressure/diam/freq profiles
plot_design_results(df)                     — ranked bar + scatter from design search
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import matplotlib.figure
    import pandas
    from stepgen.config import DeviceConfig
    from stepgen.design.operating_map import OperatingMapResult
    from stepgen.models.hydraulics import SimResult

import matplotlib
matplotlib.use("Agg")          # non-interactive backend; safe for servers
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _new_fig(figsize=(7, 4)) -> tuple:
    """Create a fresh Figure + Axes pair."""
    fig, ax = plt.subplots(figsize=figsize)
    return fig, ax


# ---------------------------------------------------------------------------
# Simulation plots
# ---------------------------------------------------------------------------

def plot_pressure_profiles(
    result: "SimResult",
    config: "DeviceConfig | None" = None,
) -> "matplotlib.figure.Figure":
    """
    Plot P_oil(x) and P_water(x) along the channel.

    Parameters
    ----------
    result : SimResult
    config : DeviceConfig (optional — used only for axis labels)
    """
    fig, ax = _new_fig()
    x_mm = result.x_positions * 1e3
    ax.plot(x_mm, result.P_oil   * 1e-2, label="P_oil",   color="tab:orange")
    ax.plot(x_mm, result.P_water * 1e-2, label="P_water", color="tab:blue")
    ax.set_xlabel("Position along channel [mm]")
    ax.set_ylabel("Pressure [mbar]")
    ax.set_title("Pressure profiles")
    ax.legend()
    fig.tight_layout()
    return fig


def plot_rung_dP(
    result: "SimResult",
    config: "DeviceConfig | None" = None,
) -> "matplotlib.figure.Figure":
    """
    Plot ΔP_rung(i) = P_oil(i) − P_water(i) across rungs.
    """
    fig, ax = _new_fig()
    x_mm    = result.x_positions * 1e3
    dP_mbar = (result.P_oil - result.P_water) * 1e-2
    ax.plot(x_mm, dP_mbar, marker=".", color="tab:purple")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Position along channel [mm]")
    ax.set_ylabel("ΔP_rung [mbar]")
    ax.set_title("Rung pressure difference")
    fig.tight_layout()
    return fig


def plot_rung_flows(
    result: "SimResult",
    config: "DeviceConfig | None" = None,
) -> "matplotlib.figure.Figure":
    """
    Plot Q_rung(i) [nL/min] as a bar chart.
    """
    fig, ax = _new_fig()
    x_mm   = result.x_positions * 1e3
    Q_nL   = result.Q_rungs * 60.0 * 1e12
    colors = np.where(Q_nL >= 0, "tab:blue", "tab:red")
    ax.bar(x_mm, Q_nL, width=(x_mm[1] - x_mm[0]) * 0.9 if len(x_mm) > 1 else 1.0, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Position along channel [mm]")
    ax.set_ylabel("Q_rung [nL/min]")
    ax.set_title("Rung oil flow rates")
    fig.tight_layout()
    return fig


def plot_rung_frequencies(
    result: "SimResult",
    config: "DeviceConfig",
) -> "matplotlib.figure.Figure":
    """
    Plot predicted droplet frequency f_rung(i) [Hz] for ACTIVE rungs.
    Inactive rungs (Q_rung ≤ 0) are shown as zero.
    """
    from stepgen.models.droplets import droplet_diameter, droplet_frequency
    from stepgen.models.generator import RungRegime, classify_rungs

    dP      = result.P_oil - result.P_water
    regimes = classify_rungs(
        dP,
        config.droplet_model.dP_cap_ow_Pa,
        config.droplet_model.dP_cap_wo_Pa,
    )
    D     = droplet_diameter(config)
    f_arr = np.zeros(len(result.Q_rungs))
    active = regimes == RungRegime.ACTIVE
    if np.any(active):
        f_arr[active] = droplet_frequency(result.Q_rungs[active], D)

    fig, ax = _new_fig()
    x_mm = result.x_positions * 1e3
    ax.bar(x_mm, f_arr, width=(x_mm[1] - x_mm[0]) * 0.9 if len(x_mm) > 1 else 1.0, color="tab:green")
    ax.set_xlabel("Position along channel [mm]")
    ax.set_ylabel("Frequency [Hz]")
    ax.set_title("Per-rung droplet frequency")
    fig.tight_layout()
    return fig


def plot_combined_profiles(
    result: "SimResult",
    config: "DeviceConfig",
) -> "matplotlib.figure.Figure":
    """
    Four-panel spatial profile plot with a shared position x-axis.

    Panels (top to bottom):
      1. P_oil and P_water [mbar] vs position
      2. ΔP_rung [mbar] with active/reverse threshold lines
      3. Per-rung oil flow [nL/hr]
      4. Per-rung droplet frequency [Hz]

    Regime regions (ACTIVE/REVERSE/OFF) are shown as background shading on
    every panel.
    """
    from stepgen.models.droplets import droplet_diameter, droplet_frequency
    from stepgen.models.generator import RungRegime, classify_rungs

    N    = len(result.Q_rungs)
    x_mm = result.x_positions * 1e3
    dP   = result.P_oil - result.P_water

    regimes = classify_rungs(
        dP,
        config.droplet_model.dP_cap_ow_Pa,
        config.droplet_model.dP_cap_wo_Pa,
    )

    D     = droplet_diameter(config)
    f_arr = np.zeros(N)
    act   = regimes == RungRegime.ACTIVE
    if np.any(act):
        f_arr[act] = droplet_frequency(result.Q_rungs[act], D)

    fig, axes = plt.subplots(
        4, 1, figsize=(10, 12), sharex=True,
        gridspec_kw={"hspace": 0.06},
    )

    # ── Regime background shading ──────────────────────────────────────────
    regime_styles = {
        RungRegime.ACTIVE:  ("tab:green", 0.08),
        RungRegime.REVERSE: ("tab:red",   0.18),
        RungRegime.OFF:     ("tab:gray",  0.18),
    }

    def _shade(ax):
        for regime, (color, alpha) in regime_styles.items():
            mask   = regimes == regime
            if not np.any(mask):
                continue
            padded = np.concatenate([[False], mask, [False]])
            edges  = np.diff(padded.astype(int))
            starts = np.where(edges ==  1)[0]
            ends   = np.where(edges == -1)[0]
            for s, e in zip(starts, ends):
                ax.axvspan(x_mm[s], x_mm[min(e, N - 1)],
                           alpha=alpha, color=color, linewidth=0)

    # ── Panel 1: Pressure profiles ─────────────────────────────────────────
    ax1 = axes[0]
    ax1.plot(x_mm, result.P_oil   * 1e-2, color="tab:orange", linewidth=1.2, label="P_oil")
    ax1.plot(x_mm, result.P_water * 1e-2, color="tab:blue",   linewidth=1.2, label="P_water")
    ax1.set_ylabel("Pressure [mbar]")
    ax1.legend(fontsize=8, loc="upper right")
    _shade(ax1)

    # ── Panel 2: Rung ΔP ──────────────────────────────────────────────────
    ax2 = axes[1]
    ax2.plot(x_mm, dP * 1e-2, color="tab:purple", linewidth=1.0)
    ax2.axhline(
        config.droplet_model.dP_cap_ow_Pa * 1e-2,
        color="tab:green", linestyle="--", linewidth=1.0,
        label=f"dP_cap_ow = {config.droplet_model.dP_cap_ow_Pa*1e-2:.0f} mbar (active threshold)",
    )
    ax2.axhline(
        -config.droplet_model.dP_cap_wo_Pa * 1e-2,
        color="tab:red", linestyle="--", linewidth=1.0,
        label=f"−dP_cap_wo = {-config.droplet_model.dP_cap_wo_Pa*1e-2:.0f} mbar (reverse threshold)",
    )
    ax2.axhline(0, color="black", linewidth=0.5, linestyle=":")
    ax2.set_ylabel("ΔP rung [mbar]")
    ax2.legend(fontsize=8, loc="upper right")
    _shade(ax2)

    # ── Panel 3: Per-rung oil flow ─────────────────────────────────────────
    ax3 = axes[2]
    Q_nL_hr = result.Q_rungs * 3.6e15   # m³/s → nL/hr
    ax3.plot(x_mm, Q_nL_hr, color="tab:blue", linewidth=1.0)
    ax3.axhline(0, color="black", linewidth=0.5, linestyle=":")
    ax3.set_ylabel("Q rung [nL/hr]")
    _shade(ax3)

    # ── Panel 4: Droplet frequency ─────────────────────────────────────────
    ax4 = axes[3]
    ax4.plot(x_mm, f_arr, color="tab:green", linewidth=1.0)
    ax4.set_ylabel("Frequency [Hz]")
    ax4.set_xlabel("Position along channel [mm]")
    _shade(ax4)

    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)

    fig.suptitle(
        f"Spatial profiles  |  Po = {result.Po_in_Pa*1e-2:.1f} mbar  "
        f"Qw = {result.Qw_in_m3s*3.6e9:.2f} mL/hr",
        fontsize=11,
    )
    fig.tight_layout()
    return fig


def plot_regime_map(
    result: "SimResult",
    config: "DeviceConfig",
) -> "matplotlib.figure.Figure":
    """
    Plot rung regime classification (ACTIVE / REVERSE / OFF) as a colour-coded bar.
    """
    from stepgen.models.generator import RungRegime, classify_rungs

    dP      = result.P_oil - result.P_water
    regimes = classify_rungs(
        dP,
        config.droplet_model.dP_cap_ow_Pa,
        config.droplet_model.dP_cap_wo_Pa,
    )

    color_map = {
        RungRegime.ACTIVE:  "tab:green",
        RungRegime.REVERSE: "tab:red",
        RungRegime.OFF:     "tab:gray",
    }
    label_map = {
        RungRegime.ACTIVE:  "ACTIVE",
        RungRegime.REVERSE: "REVERSE",
        RungRegime.OFF:     "OFF",
    }

    fig, ax = _new_fig(figsize=(8, 2))
    x_mm       = result.x_positions * 1e3
    bar_width  = (x_mm[1] - x_mm[0]) if len(x_mm) > 1 else 1.0
    bar_colors = [color_map[r] for r in regimes]
    ax.bar(x_mm, np.ones(len(x_mm)), color=bar_colors, width=bar_width)

    # Legend patches
    from matplotlib.patches import Patch
    handles = [
        Patch(color=color_map[r], label=label_map[r])
        for r in [RungRegime.ACTIVE, RungRegime.REVERSE, RungRegime.OFF]
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=8)
    ax.set_xlabel("Position along channel [mm]")
    ax.set_yticks([])
    ax.set_title("Rung regime classification")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Operating map plots
# ---------------------------------------------------------------------------

def plot_operating_map(
    map_result: "OperatingMapResult",
    metric: str = "active_fraction",
) -> "matplotlib.figure.Figure":
    """
    Plot a 2-D heatmap of a scalar metric over the (Po, Qw) grid.

    Parameters
    ----------
    map_result : OperatingMapResult
    metric     : one of 'active_fraction', 'reverse_fraction',
                 'Q_spread_pct', 'dP_spread_pct', 'P_peak_Pa',
                 'f_mean', 'dP_avg_mbar', 'Q_rung_nL_hr'
    """
    valid = {
        "active_fraction":  (map_result.active_fraction,              "Active fraction [0–1]"),
        "reverse_fraction": (map_result.reverse_fraction,             "Reverse fraction [0–1]"),
        "Q_spread_pct":     (map_result.Q_spread_pct,                 "Q spread (max−min)/mean [%]"),
        "dP_spread_pct":    (map_result.dP_spread_pct,                "ΔP spread (max−min)/mean [%]"),
        "P_peak_Pa":        (map_result.P_peak_Pa,                    "Peak oil pressure [Pa]"),
        "f_mean":           (map_result.f_mean,                       "Mean drop frequency [Hz]"),
        "dP_avg_mbar":      (map_result.dP_avg * 1e-2,                "Mean rung ΔP [mbar]"),
        "Q_rung_nL_hr":     (map_result.Q_per_rung_avg * 3.6e15,      "Mean Q/rung [nL/hr]"),
    }
    if metric not in valid:
        raise ValueError(
            f"Unknown metric {metric!r}. Choose from: {list(valid)}"
        )
    data, cb_label = valid[metric]

    fig, ax = _new_fig(figsize=(7, 5))
    Po = map_result.Po_grid
    Qw = map_result.Qw_grid
    mesh = ax.pcolormesh(Po, Qw, data, shading="auto", cmap="viridis")
    fig.colorbar(mesh, ax=ax, label=cb_label)
    ax.set_xlabel("P_oil_in [mbar]")
    ax.set_ylabel("Q_water_in [mL/hr]")
    ax.set_title(f"Operating map — {metric}")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Sweep / Pareto plots
# ---------------------------------------------------------------------------

def _pareto_front(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """
    Return a boolean mask of Pareto-optimal points (maximise both axes).

    A point is Pareto-optimal if no other point dominates it (i.e., no other
    point is strictly better in at least one axis and at least as good in the
    other).
    """
    n = len(xs)
    dominated = np.zeros(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if xs[j] >= xs[i] and ys[j] >= ys[i] and (xs[j] > xs[i] or ys[j] > ys[i]):
                dominated[i] = True
                break
    return ~dominated


def plot_pareto(
    df: "import pandas; pandas.DataFrame",
    x_col: str,
    y_col: str,
) -> "matplotlib.figure.Figure":
    """
    Scatter plot with Pareto-optimal points highlighted.

    Parameters
    ----------
    df    : sweep DataFrame (from ``sweep()``)
    x_col : column name for x axis (maximised)
    y_col : column name for y axis (maximised)
    """
    import pandas as pd

    xs = np.asarray(df[x_col], dtype=float)
    ys = np.asarray(df[y_col], dtype=float)
    valid = np.isfinite(xs) & np.isfinite(ys)
    xs_v, ys_v = xs[valid], ys[valid]

    pareto_mask = _pareto_front(xs_v, ys_v)

    fig, ax = _new_fig()
    ax.scatter(xs_v[~pareto_mask], ys_v[~pareto_mask],
               color="tab:gray", alpha=0.5, label="Dominated", s=30)
    ax.scatter(xs_v[pareto_mask], ys_v[pareto_mask],
               color="tab:red", zorder=5, label="Pareto front", s=60)

    # Draw Pareto step line (sorted by x)
    if pareto_mask.any():
        order = np.argsort(xs_v[pareto_mask])
        ax.step(xs_v[pareto_mask][order], ys_v[pareto_mask][order],
                where="post", color="tab:red", linewidth=1.5)

    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title("Pareto front")
    ax.legend()
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Experiment comparison plot
# ---------------------------------------------------------------------------

def plot_experiment_comparison(
    compare_df: "pandas.DataFrame",
    metric: str = "diameter",
) -> "matplotlib.figure.Figure":
    """
    Scatter plot of predicted vs measured values with a 1:1 identity line.

    Parameters
    ----------
    compare_df : DataFrame from ``compare_to_predictions``
    metric     : ``'diameter'`` or ``'frequency'``

    Raises
    ------
    ValueError : if ``metric`` is not one of the valid options
    """
    if metric == "diameter":
        pred_col = "D_pred_um"
        meas_col = "droplet_diameter_um"
        label    = "Diameter [µm]"
    elif metric == "frequency":
        pred_col = "f_pred_hz"
        meas_col = "frequency_hz"
        label    = "Frequency [Hz]"
    else:
        raise ValueError(
            f"Unknown metric {metric!r}. Choose 'diameter' or 'frequency'."
        )

    pred = np.asarray(compare_df[pred_col], dtype=float)
    meas = np.asarray(compare_df[meas_col], dtype=float)

    fig, ax = _new_fig()
    ax.scatter(meas, pred, color="tab:blue", alpha=0.7, zorder=3)

    lo = float(min(np.nanmin(meas), np.nanmin(pred)))
    hi = float(max(np.nanmax(meas), np.nanmax(pred)))
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=1, label="1:1")

    ax.set_xlabel(f"Measured {label}")
    ax.set_ylabel(f"Predicted {label}")
    ax.set_title(f"Predicted vs measured — {metric}")
    ax.legend()
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Layout schematic plot
# ---------------------------------------------------------------------------

def _arc_polygon(
    x_c: float, y_c: float, r_inner: float, r_outer: float,
    theta_start: float, theta_end: float, n: int = 80,
) -> tuple:
    """
    Return (x, y) arrays for a filled arc annulus polygon.

    theta_start / theta_end in radians, measured from +x axis CCW.
    """
    theta = np.linspace(theta_start, theta_end, n)
    x_out = x_c + r_outer * np.cos(theta)
    y_out = y_c + r_outer * np.sin(theta)
    x_in  = x_c + r_inner * np.cos(theta[::-1])
    y_in  = y_c + r_inner * np.sin(theta[::-1])
    return np.concatenate([x_out, x_in]), np.concatenate([y_out, y_in])


def plot_layout_schematic(
    config: "DeviceConfig",
    layout: "object | None" = None,
) -> "matplotlib.figure.Figure":
    """
    Draw the serpentine chip layout schematic.

    Channel block heights are physically proportional:
      - Oil / water main channels: height = Mcw
      - Rung array between them:   height = mcl  (actual rung length)

    Lanes that overflow the chip footprint are drawn faded with a dashed
    outline, and an overflow warning is annotated above the chip boundary.

    Parameters
    ----------
    config : DeviceConfig
    layout : LayoutResult (optional — computed from config if not supplied)
    """
    import math
    from stepgen.design.layout import compute_layout
    from matplotlib.patches import Rectangle, Patch

    if layout is None:
        layout = compute_layout(config)

    fp   = config.footprint
    geom = config.geometry

    # ── Dimensions [mm] ────────────────────────────────────────────────────
    Mcw    = geom.main.Mcw   * 1e3   # main channel width
    mcl    = geom.rung.mcl   * 1e3   # rung length → gap between channels
    tr     = fp.turn_radius  * 1e3   # turn-end buffer
    bd     = fp.reserve_border * 1e3 # chip border

    area_mm2 = fp.footprint_area_cm2 * 100.0
    AR       = fp.footprint_aspect_ratio
    chip_W   = math.sqrt(area_mm2 * AR)
    chip_H   = math.sqrt(area_mm2 / AR)
    L_useful = max(chip_W - 2.0 * bd, 1.0)

    # Serpentine geometry using mcl as the physical rung gap
    pair_w  = 2.0 * Mcw + mcl           # cross-sectional height per lane
    pitch   = pair_w + 2.0 * tr         # centre-to-centre lane spacing
    n_lanes = math.ceil(geom.main.Mcl * 1e3 / L_useful)
    tot_h   = (n_lanes - 1) * pitch + pair_w
    fits    = tot_h <= (chip_H - 2.0 * bd)

    oil_col   = "tab:orange"
    water_col = "tab:blue"
    rung_col  = "tab:green"

    # ── Figure size: fixed width, height from content ───────────────────────
    show_h  = max(tot_h + 2.0 * bd, chip_H) + bd
    show_w  = chip_W + 2.0 * bd
    aspect  = show_w / max(show_h, 1e-9)
    fig_w   = min(max(8.0, aspect * 7.0), 14.0)
    fig_h   = fig_w / max(aspect, 0.3)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # ── Draw lanes ──────────────────────────────────────────────────────────
    for i in range(n_lanes):
        y0     = bd + i * pitch
        x0     = bd
        inside = (y0 + pair_w) <= (chip_H - bd + 1e-9)
        al     = 0.6 if inside else 0.2
        ls_rect = "-" if inside else "--"

        ax.add_patch(Rectangle(
            (x0, y0), L_useful, Mcw,
            color=oil_col, alpha=al, zorder=2, linewidth=0 if inside else 0.5,
            linestyle=ls_rect,
        ))
        ax.add_patch(Rectangle(
            (x0, y0 + Mcw), L_useful, mcl,
            color=rung_col, alpha=al * 0.5, zorder=2,
            hatch="//" if inside else "", linewidth=0,
        ))
        ax.add_patch(Rectangle(
            (x0, y0 + Mcw + mcl), L_useful, Mcw,
            color=water_col, alpha=al, zorder=2, linewidth=0 if inside else 0.5,
            linestyle=ls_rect,
        ))

        # Turn indicator at alternating ends
        if i < n_lanes - 1:
            tx = (x0 + L_useful) if (i % 2 == 0) else (x0 - 2.0 * tr)
            ax.add_patch(Rectangle(
                (tx, y0), 2.0 * tr, pitch,
                color="dimgray", alpha=0.12, zorder=2, linewidth=0,
            ))

    # ── Chip boundary ───────────────────────────────────────────────────────
    ax.add_patch(Rectangle(
        (0, 0), chip_W, chip_H,
        fill=False, edgecolor="black", linewidth=2, linestyle="--", zorder=5,
    ))
    # Usable-area guides
    for y_guide in (bd, chip_H - bd):
        ax.axhline(y_guide, color="gray", linewidth=0.5, linestyle=":", zorder=4)

    # ── Dimension annotations (left side, first lane) ───────────────────────
    ann_x = -bd * 0.3
    y_cur = bd
    for height, label in [(Mcw, f"Mcw\n{Mcw:.3f} mm"), (mcl, f"mcl\n{mcl:.3f} mm")]:
        ax.annotate(
            "", xy=(ann_x, y_cur), xytext=(ann_x, y_cur + height),
            arrowprops=dict(arrowstyle="<->", color="dimgray", lw=0.8),
        )
        ax.text(ann_x - bd * 0.15, y_cur + height / 2, label,
                ha="right", va="center", fontsize=7, color="dimgray")
        y_cur += height

    # ── Overflow warning ────────────────────────────────────────────────────
    if not fits:
        overflow_mm = tot_h - (chip_H - 2.0 * bd)
        ax.text(
            chip_W * 0.5, chip_H + bd * 0.4,
            f"⚠  overflows chip by {overflow_mm:.1f} mm  ({n_lanes} lanes needed)",
            ha="center", va="bottom", fontsize=8, color="tab:red", zorder=6,
        )

    # ── Legend ──────────────────────────────────────────────────────────────
    handles = [
        Patch(color=oil_col,   alpha=0.6,  label=f"Oil main channel  (Mcw = {Mcw:.3f} mm)"),
        Patch(color=water_col, alpha=0.6,  label=f"Water main channel  (Mcw = {Mcw:.3f} mm)"),
        Patch(color=rung_col,  alpha=0.35, label=f"Rung array  (mcl = {mcl:.3f} mm,  pitch = {geom.rung.pitch*1e6:.0f} µm)"),
    ]
    ax.legend(handles=handles, fontsize=7, loc="upper right")

    ax.set_xlim(-bd * 2.0, chip_W + bd * 2.0)
    ax.set_ylim(-bd, show_h)
    ax.set_aspect("equal")
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title(
        f"Layout schematic  |  {n_lanes} lanes  |  "
        f"Nmc = {geom.Nmc:,}  |  fits = {fits}"
    )
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Spatial comparison plot
# ---------------------------------------------------------------------------

def plot_spatial_comparison(
    config: "DeviceConfig",
    result: "SimResult",
    exp_df: "pandas.DataFrame",
) -> "matplotlib.figure.Figure":
    """
    Three-panel spatial comparison of predicted profiles vs measured data.

    Panel 1 — Pressure profiles: P_oil(x) and P_water(x) [mbar] vs
               fractional position along device (0 = inlet, 1 = outlet).
    Panel 2 — Diameter: flat predicted D_pred line + measured dots.
    Panel 3 — Frequency: predicted per-rung frequency curve + measured dots.

    ``position`` in exp_df can be an integer rung index or a float in [0, 1]
    (fractional position); both are accepted and mapped to the nearest rung.

    Parameters
    ----------
    config  : DeviceConfig
    result  : SimResult  (from iterative_solve at the operating point)
    exp_df  : DataFrame from load_experiments (or compare_to_predictions)
    """
    from stepgen.models.droplets import droplet_diameter, droplet_frequency, refill_volume
    from stepgen.models.generator import RungRegime, classify_rungs

    N    = len(result.Q_rungs)
    x_fr = np.arange(N) / max(N - 1, 1)   # fractional positions 0 → 1

    dP      = result.P_oil - result.P_water
    regimes = classify_rungs(
        dP,
        config.droplet_model.dP_cap_ow_Pa,
        config.droplet_model.dP_cap_wo_Pa,
    )
    D_m   = droplet_diameter(config)
    V_refill = refill_volume(config)  # Get refill volume
    f_arr = np.zeros(N)
    active = regimes == RungRegime.ACTIVE
    if np.any(active):
        f_arr[active] = droplet_frequency(result.Q_rungs[active], D_m, V_refill)

    # ── Map experiment positions to fractional ──────────────────────────────
    def _to_frac(pos_series):
        """Convert position column to fractional 0–1 positions."""
        pos = np.asarray(pos_series, dtype=float)
        # Detect if already fractional (all values in [0, 1]) or integer indices
        if np.all((pos >= 0) & (pos <= 1)):
            return pos        # already fractional
        # Integer rung indices → normalise
        return np.clip(pos, 0, N - 1) / max(N - 1, 1)

    exp_x = _to_frac(exp_df["position"])

    fig, axes = plt.subplots(3, 1, figsize=(8, 9), sharex=True)

    # Panel 1: Pressure profiles
    ax1 = axes[0]
    ax1.plot(x_fr, result.P_oil   * 1e-2, color="tab:orange", label="P_oil")
    ax1.plot(x_fr, result.P_water * 1e-2, color="tab:blue",   label="P_water")
    ax1.set_ylabel("Pressure [mbar]")
    ax1.set_title("Pressure profiles")
    ax1.legend(fontsize=8)

    # Panel 2: Diameter
    ax2 = axes[1]
    ax2.axhline(D_m * 1e6, color="tab:purple", linewidth=2, label=f"D_pred = {D_m*1e6:.2f} µm")
    if "droplet_diameter_um" in exp_df.columns:
        ax2.scatter(exp_x, exp_df["droplet_diameter_um"],
                    color="black", s=40, zorder=5, label="Measured")
    ax2.set_ylabel("Diameter [µm]")
    ax2.set_title("Droplet diameter")
    ax2.legend(fontsize=8)

    # Panel 3: Frequency (multiple operating conditions)
    ax3 = axes[2]

    # Get unique operating conditions from experimental data
    if "frequency_hz" in exp_df.columns and "Po_in_mbar" in exp_df.columns and "Qw_in_mlhr" in exp_df.columns:
        from stepgen.models.generator import iterative_solve
        import matplotlib.colors as mcolors

        # Find unique operating conditions
        conditions = exp_df[["Po_in_mbar", "Qw_in_mlhr"]].drop_duplicates().sort_values(["Po_in_mbar", "Qw_in_mlhr"])

        # Use a colormap for different conditions
        colors = plt.cm.tab10(np.linspace(0, 1, len(conditions)))

        for i, (_, row) in enumerate(conditions.iterrows()):
            Po = float(row["Po_in_mbar"])
            Qw = float(row["Qw_in_mlhr"])
            color = colors[i]

            # Run simulation for this operating condition
            try:
                sim_result = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)

                # Calculate frequency array for this condition
                N_sim = len(sim_result.Q_rungs)
                x_fr_sim = np.arange(N_sim) / max(N_sim - 1, 1)
                dP_sim = sim_result.P_oil - sim_result.P_water
                regimes_sim = classify_rungs(dP_sim, config.droplet_model.dP_cap_ow_Pa, config.droplet_model.dP_cap_wo_Pa)
                f_arr_sim = np.zeros(N_sim)
                active_sim = regimes_sim == RungRegime.ACTIVE
                if np.any(active_sim):
                    f_arr_sim[active_sim] = droplet_frequency(sim_result.Q_rungs[active_sim], D_m, V_refill)

                # Plot model prediction line
                ax3.plot(x_fr_sim, f_arr_sim, color=color, linewidth=2,
                        label=f"Model Po={Po:.0f}mbar, Qw={Qw:.1f}mL/hr")

                # Plot experimental data for this condition
                cond_data = exp_df[(exp_df["Po_in_mbar"] == Po) & (exp_df["Qw_in_mlhr"] == Qw)]
                if len(cond_data) > 0:
                    exp_x_cond = _to_frac(cond_data["position"])
                    ax3.scatter(exp_x_cond, cond_data["frequency_hz"], color=color, s=60,
                              edgecolors='black', linewidth=1, zorder=5,
                              label=f"Measured Po={Po:.0f}mbar, Qw={Qw:.1f}mL/hr")

            except Exception as e:
                print(f"Warning: Could not simulate Po={Po}, Qw={Qw}: {e}")
                continue

    else:
        # Fallback to original single-condition plot
        ax3.plot(x_fr, f_arr, color="tab:green", label="f_pred")
        if "frequency_hz" in exp_df.columns:
            ax3.scatter(exp_x, exp_df["frequency_hz"],
                        color="black", s=40, zorder=5, label="Measured")

    ax3.set_ylabel("Frequency [Hz]")
    ax3.set_title("Droplet frequency - All operating conditions")
    ax3.set_xlabel("Fractional position along device")
    ax3.legend(fontsize=7, bbox_to_anchor=(1.05, 1), loc='upper left')

    fig.suptitle(
        f"Spatial comparison  |  Po={result.Po_in_Pa*1e-2:.1f} mbar  "
        f"Qw={result.Qw_in_m3s*3.6e6:.2f} mL/hr",
        fontsize=10,
    )
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Design results plots
# ---------------------------------------------------------------------------

def plot_design_results(
    df: "pandas.DataFrame",
    top_n: int = 20,
) -> "matplotlib.figure.Figure":
    """
    Ranked bar chart + scatter for design search results.

    Left panel  — Q_total_mlhr for the top *top_n* candidates (bar chart).
    Right panel — Po_required_mbar vs Q_total_mlhr scatter, coloured by
                  passes_hard (True=blue, False=grey).

    Parameters
    ----------
    df    : DataFrame from run_design_search
    top_n : number of top candidates to show in bar chart
    """
    import pandas as pd

    required = {"rank", "Q_total_mlhr", "Po_required_mbar", "passes_hard"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(f"plot_design_results: missing columns {sorted(missing)}")

    df_sorted = df.sort_values("rank").head(top_n).reset_index(drop=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Left: ranked bar chart of throughput
    colors = ["tab:blue" if p else "tab:gray" for p in df_sorted["passes_hard"]]
    ax1.barh(
        np.arange(len(df_sorted)),
        df_sorted["Q_total_mlhr"],
        color=colors,
    )
    ax1.set_yticks(np.arange(len(df_sorted)))
    ax1.set_yticklabels([f"#{int(r)}" for r in df_sorted["rank"]], fontsize=7)
    ax1.invert_yaxis()
    ax1.set_xlabel("Q_total [mL/hr]")
    ax1.set_title(f"Top {top_n} candidates by rank")
    from matplotlib.patches import Patch
    ax1.legend(
        handles=[Patch(color="tab:blue", label="Passes hard"),
                 Patch(color="tab:gray", label="Fails hard")],
        fontsize=8,
    )

    # Right: scatter Po vs Q_total
    pass_mask = np.asarray(df["passes_hard"], dtype=bool)
    ax2.scatter(
        df.loc[~pass_mask, "Q_total_mlhr"],
        df.loc[~pass_mask, "Po_required_mbar"],
        color="tab:gray", alpha=0.5, s=25, label="Fails hard",
    )
    ax2.scatter(
        df.loc[pass_mask, "Q_total_mlhr"],
        df.loc[pass_mask, "Po_required_mbar"],
        color="tab:blue", s=40, zorder=4, label="Passes hard",
    )
    ax2.set_xlabel("Q_total [mL/hr]")
    ax2.set_ylabel("Po_required [mbar]")
    ax2.set_title("Throughput vs required oil pressure")
    ax2.legend(fontsize=8)

    fig.tight_layout()
    return fig
