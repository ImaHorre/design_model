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
    dP_mbar = (result.P_oil - result.P_water) * 1e-2
    ax.plot(np.arange(len(dP_mbar)), dP_mbar, marker=".", color="tab:purple")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Rung index")
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
    Q_nL = result.Q_rungs * 60.0 * 1e12
    idx  = np.arange(len(Q_nL))
    colors = np.where(Q_nL >= 0, "tab:blue", "tab:red")
    ax.bar(idx, Q_nL, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Rung index")
    ax.set_ylabel("Q_rung [nL/min]")
    ax.set_title("Rung flow rates")
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
    ax.bar(np.arange(len(f_arr)), f_arr, color="tab:green")
    ax.set_xlabel("Rung index")
    ax.set_ylabel("Frequency [Hz]")
    ax.set_title("Per-rung droplet frequency")
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
    idx = np.arange(len(regimes))
    bar_colors = [color_map[r] for r in regimes]
    ax.bar(idx, np.ones(len(idx)), color=bar_colors, width=1.0)

    # Legend patches
    from matplotlib.patches import Patch
    handles = [
        Patch(color=color_map[r], label=label_map[r])
        for r in [RungRegime.ACTIVE, RungRegime.REVERSE, RungRegime.OFF]
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=8)
    ax.set_xlabel("Rung index")
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
                 'Q_uniformity_pct', 'dP_uniformity_pct', 'P_peak_Pa'
    """
    valid = {
        "active_fraction":   map_result.active_fraction,
        "reverse_fraction":  map_result.reverse_fraction,
        "Q_uniformity_pct":  map_result.Q_uniformity_pct,
        "dP_uniformity_pct": map_result.dP_uniformity_pct,
        "P_peak_Pa":         map_result.P_peak_Pa,
    }
    if metric not in valid:
        raise ValueError(
            f"Unknown metric {metric!r}. Choose from: {list(valid)}"
        )
    data = valid[metric]

    fig, ax = _new_fig(figsize=(7, 5))
    Po = map_result.Po_grid
    Qw = map_result.Qw_grid
    mesh = ax.pcolormesh(Po, Qw, data, shading="auto", cmap="viridis")
    fig.colorbar(mesh, ax=ax, label=metric)
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
    Draw the serpentine chip layout to scale.

    Both main channels (oil and water) are shown side-by-side in each
    straight serpentine lane, with semicircular turns at alternating ends.
    A hatched region between the channels represents the rung/junction area.

    Parameters
    ----------
    config : DeviceConfig
    layout : LayoutResult (optional — computed from config if not supplied)

    Returns
    -------
    matplotlib.figure.Figure
    """
    from stepgen.design.layout import compute_layout

    if layout is None:
        layout = compute_layout(config)

    fp   = config.footprint
    geom = config.geometry

    # ── Derived quantities in mm ────────────────────────────────────────────
    Mcw       = geom.main.Mcw    * 1e3   # channel width [mm]
    ls        = fp.lane_spacing  * 1e3   # gap between channels [mm]
    tr        = fp.turn_radius   * 1e3   # turn radius buffer [mm]
    border    = fp.reserve_border * 1e3  # chip border [mm]
    lane_L    = layout.lane_length     * 1e3
    lane_pw   = layout.lane_pair_width * 1e3
    lane_pit  = layout.lane_pitch      * 1e3
    tot_h     = layout.total_height    * 1e3
    num_lanes = layout.num_lanes

    # Chip bounding box (mm)
    chip_w = lane_L + 2.0 * border
    chip_h = tot_h  + 2.0 * border

    # Colours
    oil_col   = "tab:orange"
    water_col = "tab:blue"
    rung_col  = "tab:green"

    # Figure size: keep aspect ratio; cap at 14 wide
    aspect  = chip_w / max(chip_h, 1e-9)
    fig_w   = min(max(7.0, aspect * 4.0), 14.0)
    fig_h   = fig_w / max(aspect, 0.3)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    for lane_i in range(num_lanes):
        y_base = border + lane_i * lane_pit
        x0     = border

        # Within the lane pair:
        #   y_base                 → y_base + Mcw          : oil channel
        #   y_base + Mcw           → y_base + Mcw + ls      : rung gap
        #   y_base + Mcw + ls      → y_base + 2*Mcw + ls    : water channel
        y_oil   = y_base
        y_gap   = y_base + Mcw
        y_water = y_base + Mcw + ls

        from matplotlib.patches import Rectangle
        ax.add_patch(Rectangle((x0, y_oil),   lane_L, Mcw, color=oil_col,   alpha=0.55, zorder=2))
        ax.add_patch(Rectangle((x0, y_gap),   lane_L, ls,  color=rung_col,  alpha=0.25, zorder=2,
                                hatch="//", linewidth=0))
        ax.add_patch(Rectangle((x0, y_water), lane_L, Mcw, color=water_col, alpha=0.55, zorder=2))

        # ── Serpentine turns to next lane ────────────────────────────────
        if lane_i < num_lanes - 1:
            # Even lane → right turn; odd lane → left turn
            # Arc sweeps from π → 0 (right turn, CW in standard coords)
            #             or 0 → π (left turn, CCW)
            # Center of the turn (in y): midpoint between bottom of pair in
            # lane_i and bottom of pair in lane_i+1, offset by one turn radius.
            y_turn_cen = y_base + lane_pit / 2.0
            r_oil_cen   = abs(y_turn_cen - (y_oil + Mcw / 2.0))
            r_water_cen = abs(y_turn_cen - (y_water + Mcw / 2.0))

            if lane_i % 2 == 0:
                # Right turn: centre at x = border + lane_L
                x_tc   = border + lane_L
                t1, t2 = np.pi / 2.0, -np.pi / 2.0   # sweep south-to-north (CW)
            else:
                # Left turn: centre at x = border
                x_tc   = border
                t1, t2 = np.pi / 2.0, 3.0 * np.pi / 2.0  # sweep south-to-north (CCW)

            for r_cen, col in (
                (r_oil_cen,   oil_col),
                (r_water_cen, water_col),
            ):
                ri = max(r_cen - Mcw / 2.0, 0.0)
                ro = r_cen + Mcw / 2.0
                xp, yp = _arc_polygon(x_tc, y_turn_cen, ri, ro, t1, t2)
                ax.fill(xp, yp, color=col, alpha=0.55, zorder=2)

    # ── Chip footprint border ───────────────────────────────────────────────
    from matplotlib.patches import Rectangle as Rect
    ax.add_patch(Rect(
        (0, 0), chip_w, chip_h,
        fill=False, edgecolor="black", linewidth=2, linestyle="--", zorder=3,
    ))

    # ── Dimension annotations ───────────────────────────────────────────────
    ann_kw = dict(ha="center", va="center", fontsize=7, color="dimgray")
    ax.annotate(f"{lane_L:.1f} mm", xy=(chip_w / 2, -0.4 * border), **ann_kw)
    ax.annotate(f"{chip_h:.1f} mm", xy=(-0.4 * border, chip_h / 2),
                rotation=90, **ann_kw)
    ax.annotate(
        f"{num_lanes} lane{'s' if num_lanes != 1 else ''}  |  "
        f"Nmc={config.geometry.Nmc:,}  |  "
        f"fits={layout.fits_footprint}",
        xy=(chip_w / 2, chip_h + 0.3 * border),
        **ann_kw,
    )

    # ── Legend ──────────────────────────────────────────────────────────────
    from matplotlib.patches import Patch
    handles = [
        Patch(color=oil_col,   alpha=0.55, label="Oil main channel"),
        Patch(color=water_col, alpha=0.55, label="Water main channel"),
        Patch(color=rung_col,  alpha=0.4,  label="Rung / junction region"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=8)

    ax.set_xlim(-border, chip_w + border)
    ax.set_ylim(-border, chip_h + border)
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title("Chip layout schematic (top view, to scale)")
    ax.set_aspect("equal")
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
    from stepgen.models.droplets import droplet_diameter, droplet_frequency
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
    f_arr = np.zeros(N)
    active = regimes == RungRegime.ACTIVE
    if np.any(active):
        f_arr[active] = droplet_frequency(result.Q_rungs[active], D_m)

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

    # Panel 3: Frequency
    ax3 = axes[2]
    ax3.plot(x_fr, f_arr, color="tab:green", label="f_pred")
    if "frequency_hz" in exp_df.columns:
        ax3.scatter(exp_x, exp_df["frequency_hz"],
                    color="black", s=40, zorder=5, label="Measured")
    ax3.set_ylabel("Frequency [Hz]")
    ax3.set_title("Droplet frequency")
    ax3.set_xlabel("Fractional position along device")
    ax3.legend(fontsize=8)

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
