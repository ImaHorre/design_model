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
