"""
Radial DFU Array — Hydraulic Model
====================================
Wheel geometry: oil enters at hub, flows through N radial DFU channels to rim,
exits as droplets into an open bath at atmospheric pressure.

Key physics differences vs. linear ladder network
--------------------------------------------------
Linear ladder:
  - Two flowing main channels (oil + water), pressure gradients on both sides
  - High R_rung/R_main ratio required for cross-array uniformity

Radial wheel:
  - P_bath = P_atm = const everywhere (no continuous-phase channel)
  - All N_DFU channels share the same hub pressure → automatically uniform
  - High upstream resistance still useful for flow stability (Ca control)

Critical insight: Q_total is INDEPENDENT of radius R
-----------------------------------------------------
  N_DFU ∝ R  (circumference grows with R)
  R_DFU  ∝ R  (channel length = R)
  Q/DFU  ∝ 1/R  (less flow per channel)
  Q_total = N × Q/DFU ∝ R × (1/R) = const

Analytic formula:
  Q_total = (2π / pitch) × ΔP × w_up × h³ × (1 − 0.63·h/w_up) / (12·µ)

where h = exit_depth, w_up = upstream channel width (the free design variable).
Resistance formula matches stepgen.models.resistance.hydraulic_resistance_rectangular.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# ── Unit helpers ──────────────────────────────────────────────────────────────
INCH_TO_M = 0.0254
MBAR_TO_PA = 100.0
M3S_TO_UL_HR = 1e9 * 3600.0    # m³/s  ->  uL/hr  (1 m3 = 1e9 uL)
M3S_TO_NL_HR = 1e12 * 3600.0  # m³/s  ->  nL/hr  (1 m3 = 1e12 nL)


# ── Core physics ──────────────────────────────────────────────────────────────

def channel_resistance(width_m: float, depth_m: float,
                        length_m: float, mu: float) -> float:
    """
    Hydraulic resistance of one rectangular DFU channel [Pa·s/m³].

    R = 12·µ·L / (w·h³) / (1 − 0.63·h/w)

    Uses the same approximation as stepgen.models.resistance so results
    are directly comparable.  Valid for h/w < 1.587.
    """
    if width_m <= 0 or depth_m <= 0 or length_m <= 0 or mu <= 0:
        raise ValueError("All parameters must be positive.")
    ratio = depth_m / width_m
    denom = 1.0 - 0.63 * ratio
    if denom <= 0.0:
        raise ValueError(
            f"h/w = {ratio:.3f} exceeds correction limit "
            f"(must be < {1/0.63:.3f}). Widen the channel."
        )
    base = 12.0 * mu * length_m / (width_m * depth_m**3)
    return base / denom


def ca_exit(
    delta_P_Pa: float,
    upstream_width_m: float,
    radius_m: float,
    exit_width_m: float = 30e-6,
    exit_depth_m: float = 10e-6,
    gamma: float = 5e-3,
    mu_oil: float = 0.06,
) -> float:
    """
    Capillary number at the DFU exit step.

      Ca = mu_oil * v_exit / gamma

    where v_exit = Q_per_DFU / (exit_w * exit_h).

    Key result: mu_oil cancels — Ca is viscosity-independent for Poiseuille flow
    where the same fluid provides both resistance and Ca numerator:

      Ca = dP * w_up * h^3 * corr / (12 * L * exit_w * exit_h * gamma)

    The relevant regime thresholds from Flow Regimes theory:
      Ca < 0.01          dripping / step emulsification  (target)
      0.01 < Ca < 0.3    transitional (avoid)
      Ca > 0.3           jetting / blow-out
    """
    h, w = exit_depth_m, upstream_width_m
    correction = 1.0 - 0.63 * (h / w)
    if correction <= 0:
        raise ValueError(f"h/w = {h/w:.3f} out of valid range.")
    return (delta_P_Pa * w * h**3 * correction
            / (12.0 * radius_m * exit_width_m * exit_depth_m * gamma))


def p_max_stable(
    ca_crit: float,
    upstream_width_m: float,
    radius_m: float,
    exit_width_m: float = 30e-6,
    exit_depth_m: float = 10e-6,
    gamma: float = 5e-3,
) -> float:
    """
    Maximum hub pressure [Pa] that keeps Ca <= ca_crit at the exit.
    Rearrangement of ca_exit(): independent of mu_oil.
    """
    h, w = exit_depth_m, upstream_width_m
    correction = 1.0 - 0.63 * (h / w)
    return (ca_crit * 12.0 * radius_m * exit_width_m * exit_depth_m * gamma
            / (w * h**3 * correction))


def min_radius_for_stability(
    delta_P_Pa: float,
    upstream_width_m: float,
    ca_crit: float = 0.01,
    exit_width_m: float = 30e-6,
    exit_depth_m: float = 10e-6,
    gamma: float = 5e-3,
) -> float:
    """
    Minimum radius [m] to maintain Ca <= ca_crit at given operating pressure.
    Below this radius you must either narrow the upstream channel or drop pressure.
    """
    h, w = exit_depth_m, upstream_width_m
    correction = 1.0 - 0.63 * (h / w)
    return (delta_P_Pa * w * h**3 * correction
            / (12.0 * ca_crit * exit_width_m * exit_depth_m * gamma))


def q_total_analytic(
    delta_P_Pa: float,
    upstream_width_m: float,
    exit_depth_m: float = 10e-6,
    pitch_m: float = 60e-6,
    mu_oil: float = 0.06,
) -> float:
    """
    Total device flow rate [m³/s] — analytic form independent of radius R.

      Q = (2π/pitch) × ΔP × w_up × h³ × (1 − 0.63·h/w_up) / (12·µ)
    """
    h, w = exit_depth_m, upstream_width_m
    correction = 1.0 - 0.63 * (h / w)
    if correction <= 0:
        raise ValueError(f"h/w = {h/w:.3f} out of range.")
    return (2.0 * np.pi / pitch_m) * delta_P_Pa * w * h**3 * correction / (12.0 * mu_oil)


# ── Device class ──────────────────────────────────────────────────────────────

@dataclass
class RadialArray:
    """
    Radial DFU wheel device at a fixed radius.

    Parameters
    ----------
    radius_m          Hub-to-rim radius [m]
    upstream_width_m  Width of each radial DFU channel [m]
    exit_width_m      Exit junction width [m]       (default 30 µm, v5-30)
    exit_depth_m      Exit junction depth [m]       (default 10 µm, v5-30)
    pitch_m           DFU pitch at circumference [m](default 60 µm, v5-30)
    mu_oil            Oil dynamic viscosity [Pa·s]  (default 0.06)
    """
    radius_m: float
    upstream_width_m: float
    exit_width_m: float = 30e-6
    exit_depth_m: float = 10e-6
    pitch_m: float = 60e-6
    mu_oil: float = 0.06

    @property
    def n_dfu(self) -> int:
        """Number of DFUs around the circumference."""
        return int(2.0 * np.pi * self.radius_m / self.pitch_m)

    @property
    def r_dfu(self) -> float:
        """Resistance of one DFU channel [Pa·s/m³]."""
        return channel_resistance(
            self.upstream_width_m, self.exit_depth_m,
            self.radius_m, self.mu_oil,
        )

    def q_total(self, delta_P_Pa: float) -> float:
        """Total flow [m³/s] at hub-to-bath pressure difference [Pa]."""
        return self.n_dfu * delta_P_Pa / self.r_dfu

    def q_per_dfu(self, delta_P_Pa: float) -> float:
        """Flow through one DFU [m³/s]."""
        return delta_P_Pa / self.r_dfu

    def summary(self, P_mbar: float = 200.0) -> dict:
        """Quick diagnostic dict at a given pressure."""
        dP = P_mbar * MBAR_TO_PA
        return {
            "radius_mm": self.radius_m * 1e3,
            "upstream_width_um": self.upstream_width_m * 1e6,
            "n_dfu": self.n_dfu,
            "r_dfu_Pa_s_m3": self.r_dfu,
            "Q_total_uL_hr": self.q_total(dP) * M3S_TO_UL_HR,
            "Q_per_dfu_nL_hr": self.q_per_dfu(dP) * M3S_TO_NL_HR,
        }


# ── Plotting ──────────────────────────────────────────────────────────────────

_DEFAULT_WIDTHS_UM = [8, 10, 15, 20, 27, 30, 50, 100]
_REF_PRESSURES_MBAR = [100, 200, 300]


def plot_pq(
    upstream_widths_um: Sequence[float] = _DEFAULT_WIDTHS_UM,
    P_max_mbar: float = 500.0,
    exit_depth_m: float = 10e-6,
    pitch_m: float = 60e-6,
    mu_oil: float = 0.06,
    radius_max_m: float = 2.5 * INCH_TO_M,
    save_path: str | None = None,
) -> plt.Figure:
    """
    Two-panel figure:
      Left  — P vs Q_total for each upstream width choice
      Right — Q_total vs upstream width at reference pressures
    """
    P_arr_mbar = np.linspace(0, P_max_mbar, 400)
    P_arr_Pa = P_arr_mbar * MBAR_TO_PA

    cmap = plt.cm.plasma
    colors_pq = cmap(np.linspace(0.1, 0.88, len(upstream_widths_um)))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        f"Radial DFU Array — Hydraulic Design Space\n"
        f"Exit: {exit_depth_m*1e6:.0f} µm depth × 30 µm width, "
        f"pitch = {pitch_m*1e6:.0f} µm, µ_oil = {mu_oil:.3f} Pa·s",
        fontsize=11,
    )

    # ── Panel 1: P vs Q_total ─────────────────────────────────────────────
    for w_um, col in zip(upstream_widths_um, colors_pq):
        w_m = w_um * 1e-6
        Q_ulhr = np.array([
            q_total_analytic(P, w_m, exit_depth_m, pitch_m, mu_oil) * M3S_TO_UL_HR
            for P in P_arr_Pa
        ])
        ax1.plot(P_arr_mbar, Q_ulhr, color=col, linewidth=2.0, label=f"{w_um} µm")

    ax1.axvline(200, color="gray", linestyle="--", linewidth=1, alpha=0.55, label="200 mbar ref")
    ax1.set_xlabel("Oil pressure at hub  (mbar)", fontsize=12)
    ax1.set_ylabel("Total device flow rate  (µL/hr)", fontsize=12)
    ax1.set_title("P vs Q   [Q independent of radius R]", fontsize=11, pad=6)
    ax1.legend(title="Upstream\nwidth (µm)", fontsize=8.5, title_fontsize=8.5,
               loc="upper left", framealpha=0.85)
    ax1.grid(True, alpha=0.25)
    ax1.set_xlim(0, P_max_mbar)
    ax1.set_ylim(bottom=0)

    # Mark exact values at 200 mbar with scatter points
    P_ref_Pa = 200.0 * MBAR_TO_PA
    for w_um, col in zip(upstream_widths_um, colors_pq):
        w_m = w_um * 1e-6
        Q_ref = q_total_analytic(P_ref_Pa, w_m, exit_depth_m, pitch_m, mu_oil) * M3S_TO_UL_HR
        ax1.scatter(200, Q_ref, color=col, s=35, zorder=5, edgecolors="white", linewidths=0.6)

    ax1.annotate(
        "Q_total = (2π/pitch)·ΔP·w·h³·(1−0.63h/w) / (12µ)\n"
        "→  N_DFU and R_DFU both ∝ R  →  ratio cancels",
        xy=(0.98, 0.03), xycoords="axes fraction",
        ha="right", va="bottom", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#fffde7", edgecolor="#ccc", alpha=0.9),
    )

    # ── Panel 2: Q_total vs upstream width at fixed pressures ─────────────
    w_scan_um = np.linspace(6, 120, 300)
    w_scan_m = w_scan_um * 1e-6
    p_colors = ["#1a73e8", "#e67c00", "#2ecc71"]

    for P_mbar, pcol in zip(_REF_PRESSURES_MBAR, p_colors):
        dP_Pa = P_mbar * MBAR_TO_PA
        Q_vals = []
        for wm in w_scan_m:
            try:
                Q_vals.append(
                    q_total_analytic(dP_Pa, wm, exit_depth_m, pitch_m, mu_oil) * M3S_TO_UL_HR
                )
            except ValueError:
                Q_vals.append(np.nan)
        ax2.plot(w_scan_um, Q_vals, color=pcol, linewidth=2.2, label=f"{P_mbar} mbar")

    # Vertical markers for the nominal widths
    for w_um, col in zip(upstream_widths_um, colors_pq):
        ax2.axvline(w_um, color=col, linestyle=":", linewidth=0.9, alpha=0.55)

    ax2.set_xlabel("Upstream channel width  (µm)", fontsize=12)
    ax2.set_ylabel("Total device flow rate  (µL/hr)", fontsize=12)
    ax2.set_title(
        f"Q vs Upstream Width  [R_max = {radius_max_m*1e3:.0f} mm, "
        f"N_max = {int(2*np.pi*radius_max_m/pitch_m):,} DFUs]",
        fontsize=11, pad=6,
    )
    ax2.legend(title="Hub pressure", fontsize=9, title_fontsize=9, framealpha=0.85)
    ax2.grid(True, alpha=0.25)
    ax2.set_xlim(w_scan_um[0], w_scan_um[-1])
    ax2.set_ylim(bottom=0)

    # Shade the region where h/w > 1 (depth > width — aspect ratio caution)
    ax2.axvspan(w_scan_um[0], exit_depth_m * 1e6, alpha=0.10, color="red",
                label="depth > width (high aspect ratio)")
    ax2.axvline(exit_depth_m * 1e6, color="red", linestyle="--", linewidth=1.0,
                alpha=0.6, label="w_up = depth (h/w = 1)")
    ax2.legend(title="Hub pressure", fontsize=8.5, title_fontsize=8.5,
               framealpha=0.85, loc="upper left")

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=160, bbox_inches="tight")
        print(f"Saved -> {save_path}")

    return fig


# ── CLI ───────────────────────────────────────────────────────────────────────

def print_summary_table(
    P_mbar: float = 200.0,
    radius_m: float = 2.5 * INCH_TO_M,
    widths_um: Sequence[float] = _DEFAULT_WIDTHS_UM,
    exit_depth_m: float = 10e-6,
    pitch_m: float = 60e-6,
    mu_oil: float = 0.06,
) -> None:
    N_max = int(2 * np.pi * radius_m / pitch_m)
    dP = P_mbar * MBAR_TO_PA

    print(f"\nRadial DFU Array — Summary at {P_mbar} mbar")
    print(f"R_max = {radius_m*1e3:.1f} mm  |  N_DFU = {N_max:,}  |  pitch = {pitch_m*1e6:.0f} µm")
    print(f"Exit: {exit_depth_m*1e6:.0f} µm depth × 30 µm width  |  µ_oil = {mu_oil} Pa·s")
    print("-" * 72)
    print(f"{'w_up (µm)':<12}{'R_DFU (Pa·s/m³)':<22}{'Q_total (µL/hr)':<20}{'Q/DFU (nL/hr)'}")
    print("-" * 72)
    for w_um in widths_um:
        w_m = w_um * 1e-6
        try:
            R = channel_resistance(w_m, exit_depth_m, radius_m, mu_oil)
            Q_tot = q_total_analytic(dP, w_m, exit_depth_m, pitch_m, mu_oil) * M3S_TO_UL_HR
            Q_dfu = (dP / R) * M3S_TO_NL_HR
            print(f"{w_um:<12}{R:<22.3e}{Q_tot:<20.2f}{Q_dfu:.3f}")
        except ValueError as e:
            print(f"{w_um:<12}  *** {e}")
    print()


def print_stability_table(
    P_mbar: float = 200.0,
    radius_m: float = 2.5 * INCH_TO_M,
    widths_um: Sequence[float] = _DEFAULT_WIDTHS_UM,
    exit_depth_m: float = 10e-6,
    exit_width_m: float = 30e-6,
    gamma: float = 5e-3,
) -> None:
    """
    Print Ca at the exit and maximum stable pressure for each upstream width.
    Ca is viscosity-independent (mu cancels in Poiseuille + Ca combination).
    """
    dP = P_mbar * MBAR_TO_PA
    R_mm = radius_m * 1e3
    R_min_vals = []
    print(f"\nStability analysis — Ca at exit  (gamma = {gamma*1e3:.0f} mN/m, R = {R_mm:.0f} mm)")
    print(f"Ca < 0.01 = dripping/step-emulsification target  |  Ca > 0.01 = transitional/jet")
    print(f"Note: Ca is VISCOSITY-INDEPENDENT (mu cancels for Poiseuille + Ca = mu*v/gamma)")
    print("-" * 90)
    print(f"{'w_up (um)':<12}{'Ca @ 200mbar':<18}{'Ca/Ca_crit':<14}{'P_max stable (mbar)':<22}{'R_min (mm)'}")
    print("-" * 90)
    for w_um in widths_um:
        w_m = w_um * 1e-6
        try:
            ca = ca_exit(dP, w_m, radius_m, exit_width_m, exit_depth_m, gamma)
            pmax = p_max_stable(0.01, w_m, radius_m, exit_width_m, exit_depth_m, gamma)
            rmin = min_radius_for_stability(dP, w_m, 0.01, exit_width_m, exit_depth_m, gamma)
            R_min_vals.append(rmin * 1e3)
            flag = "  <-- transitional!" if ca > 0.01 else ""
            print(f"{w_um:<12}{ca:<18.4e}{ca/0.01:<14.2f}{pmax/MBAR_TO_PA:<22.0f}{rmin*1e3:.2f}{flag}")
        except ValueError as e:
            print(f"{w_um:<12}  *** {e}")
    print()


def plot_ca_stability(
    upstream_widths_um: Sequence[float] = [10, 20, 30, 50, 100],
    radius_values_mm: Sequence[float] = [5, 10, 20, 40, 63.5],
    P_max_mbar: float = 600.0,
    exit_depth_m: float = 10e-6,
    exit_width_m: float = 30e-6,
    gamma: float = 5e-3,
    save_path: str | None = None,
) -> plt.Figure:
    """
    Two-panel stability figure:
      Left  — Ca vs hub pressure for different (width, radius) combinations
      Right — Max stable pressure vs radius for each upstream width
    """
    P_arr_mbar = np.linspace(1, P_max_mbar, 400)
    P_arr_Pa = P_arr_mbar * MBAR_TO_PA

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        "Radial DFU — Stability: Capillary Number at Exit Step\n"
        f"Exit: {exit_depth_m*1e6:.0f} µm x {exit_width_m*1e6:.0f} µm, "
        f"gamma = {gamma*1e3:.0f} mN/m   [Ca = mu*v/gamma; mu CANCELS — regime independent of viscosity]",
        fontsize=10,
    )

    # ── Panel 1: Ca vs P, curves per (width, radius) ─────────────────────
    cmap = plt.cm.tab10
    line_idx = 0
    for i, w_um in enumerate(upstream_widths_um):
        for j, R_mm in enumerate(radius_values_mm):
            w_m, R_m = w_um * 1e-6, R_mm * 1e-3
            ca_vals = [
                ca_exit(P, w_m, R_m, exit_width_m, exit_depth_m, gamma)
                for P in P_arr_Pa
            ]
            ls = ["-", "--", ":", "-."][j % 4]
            col = cmap(i / len(upstream_widths_um))
            label = f"w={w_um}µm, R={R_mm:.0f}mm" if j == 0 else None
            ax1.semilogy(P_arr_mbar, ca_vals, ls=ls, color=col, linewidth=1.6,
                         label=label, alpha=0.85)

    # Regime boundary lines
    ax1.axhline(0.01, color="red", linestyle="--", linewidth=1.8, label="Ca_crit = 0.01 (drip/jet boundary)")
    ax1.axhline(0.3,  color="darkred", linestyle=":", linewidth=1.5, label="Ca = 0.3 (jetting)")
    ax1.fill_between([0, P_max_mbar], 0.01, 0.3, alpha=0.07, color="orange", label="Transitional zone")
    ax1.fill_between([0, P_max_mbar], 0.3, 10,  alpha=0.07, color="red", label="Jetting zone")

    ax1.set_xlabel("Hub pressure  (mbar)", fontsize=12)
    ax1.set_ylabel("Ca at exit  (log scale)", fontsize=12)
    ax1.set_title("Ca vs pressure for (width, radius) combinations\n(dashed = different radii, same color = same width)",
                  fontsize=9)
    ax1.legend(fontsize=7.5, loc="upper left", framealpha=0.85, ncol=2)
    ax1.set_xlim(0, P_max_mbar)
    ax1.set_ylim(1e-5, 10)
    ax1.grid(True, alpha=0.2, which="both")

    # ── Panel 2: P_max_stable vs radius for each width ───────────────────
    R_scan_mm = np.linspace(1, 70, 300)
    R_scan_m = R_scan_mm * 1e-3
    cmap2 = plt.cm.plasma

    for i, w_um in enumerate(upstream_widths_um):
        w_m = w_um * 1e-6
        pmax_vals = [
            p_max_stable(0.01, w_m, R, exit_width_m, exit_depth_m, gamma) / MBAR_TO_PA
            for R in R_scan_m
        ]
        col = cmap2(0.1 + i * 0.75 / len(upstream_widths_um))
        ax2.semilogy(R_scan_mm, pmax_vals, color=col, linewidth=2.0, label=f"{w_um} µm")

    ax2.axhline(200, color="gray", linestyle="--", linewidth=1.2, alpha=0.7, label="200 mbar ref")
    ax2.axhline(500, color="gray", linestyle=":",  linewidth=1.2, alpha=0.7, label="500 mbar ref")
    ax2.axvline(63.5, color="black", linestyle="--", linewidth=1.0, alpha=0.5, label="R_max = 63.5 mm")

    ax2.set_xlabel("Radius R  (mm)", fontsize=12)
    ax2.set_ylabel("Max stable hub pressure  (mbar, log)", fontsize=12)
    ax2.set_title("Max pressure for Ca < 0.01 vs radius\n(above line = stable step emulsification)", fontsize=9)
    ax2.legend(title="w_up", fontsize=8.5, title_fontsize=8.5, framealpha=0.85)
    ax2.grid(True, alpha=0.2, which="both")
    ax2.set_xlim(0, 70)
    ax2.set_ylim(10, 1e5)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=160, bbox_inches="tight")
        print(f"Saved -> {save_path}")
    return fig


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    print_summary_table()
    print_stability_table()
    plot_pq(save_path=str(out_dir / "pq_radial.png"))
    plot_ca_stability(save_path=str(out_dir / "ca_stability_radial.png"))
    plt.show()
