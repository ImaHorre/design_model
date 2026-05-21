"""
Radial DFU Array — Geometry Sketch
====================================
Visualises the channel convergence problem at the hub:
  - At radius r, arc spacing = pitch × r/R
  - Channels of width w_up merge where arc_spacing = w_up
    → r_merge = R × w_up / pitch

Three figures:
  1. Full device polar schematic (representative subset of channels)
  2. Close-up of hub region showing convergence
  3. r_hub vs upstream width — how much of the device is "hub" dead zone
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from pathlib import Path

# ── Device parameters ─────────────────────────────────────────────────────────
R_MAX_M       = 2.5 * 0.0254          # 63.5 mm
PITCH_M       = 60e-6
EXIT_WIDTH_M  = 30e-6
N_DFU         = int(2 * np.pi * R_MAX_M / PITCH_M)   # 6649
OUT_DIR       = Path(__file__).parent


def r_merge(w_up_m, R=R_MAX_M, pitch=PITCH_M):
    """Radius at which uniform-width channels just touch (no wall)."""
    return R * w_up_m / pitch


def r_hub_tapered(w_min_m, w_rim_m=EXIT_WIDTH_M):
    """Hub radius for tapered design: channel width ∝ r/R, stopping at w_min."""
    return R_MAX_M * w_min_m / w_rim_m


# ── Figure 1: full device polar schematic ─────────────────────────────────────

def plot_device_schematic(save_path=None):
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    fig.suptitle(
        f"Radial DFU Array — Geometry   "
        f"[R = {R_MAX_M*1e3:.0f} mm, N_DFU = {N_DFU:,}, pitch = {PITCH_M*1e6:.0f} µm]",
        fontsize=12,
    )

    R_mm = R_MAX_M * 1e3

    # ── Panel A: Full device, uniform 8 µm channels ───────────────────────────
    ax = axes[0]
    ax.set_aspect("equal")
    N_show = 300   # representative spokes for visual clarity
    angles = np.linspace(0, 2 * np.pi, N_show, endpoint=False)

    w_up = 8e-6
    r_hub_mm = r_merge(w_up) * 1e3

    # draw channels (lines from r_hub to R)
    for a in angles:
        x0 = r_hub_mm * np.cos(a)
        y0 = r_hub_mm * np.sin(a)
        x1 = R_mm * np.cos(a)
        y1 = R_mm * np.sin(a)
        ax.plot([x0, x1], [y0, y1], color="#e07b00", linewidth=0.5, alpha=0.7)

    # hub circle
    hub_circle = plt.Circle((0, 0), r_hub_mm, color="#3a86ff", alpha=0.25, zorder=3)
    ax.add_patch(hub_circle)
    hub_edge = plt.Circle((0, 0), r_hub_mm, fill=False, edgecolor="#3a86ff",
                           linewidth=2, linestyle="--", zorder=4)
    ax.add_patch(hub_edge)
    # rim
    rim = plt.Circle((0, 0), R_mm, fill=False, edgecolor="black", linewidth=2)
    ax.add_patch(rim)

    ax.set_xlim(-R_mm * 1.1, R_mm * 1.1)
    ax.set_ylim(-R_mm * 1.1, R_mm * 1.1)
    ax.set_title(
        f"Uniform channels, w_up = {w_up*1e6:.0f} µm\n"
        f"r_hub = {r_hub_mm:.1f} mm  ({r_hub_mm/R_mm*100:.0f}% of R)",
        fontsize=9,
    )
    ax.set_xlabel("mm")
    ax.set_ylabel("mm")
    ax.annotate(
        f"Hub\n(oil plenum)\nr = {r_hub_mm:.1f} mm",
        xy=(0, 0), xytext=(R_mm * 0.35, R_mm * 0.35),
        arrowprops=dict(arrowstyle="->", color="#3a86ff"),
        fontsize=8, color="#3a86ff",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#3a86ff", alpha=0.8),
    )
    ax.annotate(
        f"DFU channels\n({N_DFU:,} total)",
        xy=(R_mm * 0.7 * np.cos(0.4), R_mm * 0.7 * np.sin(0.4)),
        xytext=(R_mm * 0.3, -R_mm * 0.55),
        arrowprops=dict(arrowstyle="->", color="#e07b00"),
        fontsize=8, color="#e07b00",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#e07b00", alpha=0.8),
    )

    # ── Panel B: Full device, uniform 30 µm channels ──────────────────────────
    ax = axes[1]
    ax.set_aspect("equal")

    w_up2 = 30e-6
    r_hub2_mm = r_merge(w_up2) * 1e3

    for a in angles:
        x0 = r_hub2_mm * np.cos(a)
        y0 = r_hub2_mm * np.sin(a)
        x1 = R_mm * np.cos(a)
        y1 = R_mm * np.sin(a)
        ax.plot([x0, x1], [y0, y1], color="#e07b00", linewidth=0.5, alpha=0.7)

    hub2 = plt.Circle((0, 0), r_hub2_mm, color="#3a86ff", alpha=0.3, zorder=3)
    ax.add_patch(hub2)
    hub2_edge = plt.Circle((0, 0), r_hub2_mm, fill=False, edgecolor="#3a86ff",
                            linewidth=2, linestyle="--", zorder=4)
    ax.add_patch(hub2_edge)
    rim2 = plt.Circle((0, 0), R_mm, fill=False, edgecolor="black", linewidth=2)
    ax.add_patch(rim2)

    ax.set_xlim(-R_mm * 1.1, R_mm * 1.1)
    ax.set_ylim(-R_mm * 1.1, R_mm * 1.1)
    ax.set_title(
        f"Uniform channels, w_up = {w_up2*1e6:.0f} µm (= exit width)\n"
        f"r_hub = {r_hub2_mm:.1f} mm  ({r_hub2_mm/R_mm*100:.0f}% of R!)  -- half the device!",
        fontsize=9,
    )
    ax.set_xlabel("mm")
    ax.annotate(
        f"Hub = {r_hub2_mm/R_mm*100:.0f}% of radius!\n(r = {r_hub2_mm:.0f} mm)",
        xy=(0, 0), xytext=(R_mm * 0.25, R_mm * 0.55),
        arrowprops=dict(arrowstyle="->", color="#d00000"),
        fontsize=9, color="#d00000", fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#d00000", alpha=0.9),
    )

    # ── Panel C: Tapered channels (wedge design) ──────────────────────────────
    ax = axes[2]
    ax.set_aspect("equal")

    w_min = 5e-6    # minimum manufacturable width at hub
    r_hub3_mm = r_hub_tapered(w_min) * 1e3

    # draw tapered channels: narrower near hub (represented by fading lines)
    for a in angles:
        # channels taper from w_min at hub to EXIT_WIDTH at R
        # represent visually by grading linewidth
        r_inner = r_hub3_mm
        r_outer = R_mm
        n_seg = 8
        r_segs = np.linspace(r_inner, r_outer, n_seg + 1)
        for k in range(n_seg):
            frac = (r_segs[k] - r_inner) / (r_outer - r_inner)
            lw = 0.3 + 1.2 * frac   # thinner near hub, thicker near rim
            r0, r1 = r_segs[k], r_segs[k + 1]
            ax.plot(
                [r0 * np.cos(a), r1 * np.cos(a)],
                [r0 * np.sin(a), r1 * np.sin(a)],
                color="#e07b00", linewidth=lw, alpha=0.7,
            )

    hub3 = plt.Circle((0, 0), r_hub3_mm, color="#3a86ff", alpha=0.3, zorder=3)
    ax.add_patch(hub3)
    hub3_edge = plt.Circle((0, 0), r_hub3_mm, fill=False, edgecolor="#3a86ff",
                            linewidth=2, linestyle="--", zorder=4)
    ax.add_patch(hub3_edge)
    rim3 = plt.Circle((0, 0), R_mm, fill=False, edgecolor="black", linewidth=2)
    ax.add_patch(rim3)

    ax.set_xlim(-R_mm * 1.1, R_mm * 1.1)
    ax.set_ylim(-R_mm * 1.1, R_mm * 1.1)
    ax.set_title(
        f"Tapered (wedge) channels: w ∝ r/R\n"
        f"w_min = {w_min*1e6:.0f} µm at hub, {EXIT_WIDTH_M*1e6:.0f} µm at rim\n"
        f"r_hub = {r_hub3_mm:.1f} mm  ({r_hub3_mm/R_mm*100:.0f}% of R)",
        fontsize=9,
    )
    ax.set_xlabel("mm")
    ax.annotate(
        f"Tapered hub\nr = {r_hub3_mm:.1f} mm\n({r_hub3_mm/R_mm*100:.0f}% of R)",
        xy=(0, 0), xytext=(R_mm * 0.3, R_mm * 0.45),
        arrowprops=dict(arrowstyle="->", color="#3a86ff"),
        fontsize=8, color="#3a86ff",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#3a86ff", alpha=0.8),
    )
    ax.annotate(
        "Channels widen\ntoward rim",
        xy=(R_mm * 0.65 * np.cos(1.1), R_mm * 0.65 * np.sin(1.1)),
        xytext=(-R_mm * 0.7, R_mm * 0.5),
        arrowprops=dict(arrowstyle="->", color="#777"),
        fontsize=8, color="#555",
    )

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path}")
    return fig


# ── Figure 2: r_hub vs w_up parametric plot ───────────────────────────────────

def plot_hub_size(save_path=None):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    fig.suptitle(
        f"Hub size vs channel width  —  N_DFU = {N_DFU:,}, R = {R_MAX_M*1e3:.0f} mm",
        fontsize=12,
    )

    w_scan_um  = np.linspace(4, 60, 400)
    w_scan_m   = w_scan_um * 1e-6

    # uniform channels: r_hub = N × w_up / (2π)  =  R × w_up/pitch
    r_hub_uniform_mm = np.array([r_merge(w) * 1e3 for w in w_scan_m])
    hub_frac_uniform = r_hub_uniform_mm / (R_MAX_M * 1e3)   # fraction of R
    dead_area_frac   = hub_frac_uniform**2                   # dead area ∝ r²

    # tapered channels: r_hub = R × w_min / w_rim  (using w_min = w_scan as w_min)
    r_hub_tapered_mm = np.array([r_hub_tapered(w) * 1e3 for w in w_scan_m])
    hub_frac_tapered = r_hub_tapered_mm / (R_MAX_M * 1e3)
    dead_area_taper  = hub_frac_tapered**2

    ax1, ax2 = axes

    # ── Left: r_hub ──────────────────────────────────────────────────────────
    ax1.plot(w_scan_um, r_hub_uniform_mm, "b-", linewidth=2,
             label="Uniform channels: r_hub = R × w_up / pitch")
    ax1.plot(w_scan_um, r_hub_tapered_mm, "g--", linewidth=2,
             label="Tapered channels: r_hub = R × w_min / w_exit")

    ax1.axhline(R_MAX_M * 1e3 * 0.5, color="red", linestyle=":", linewidth=1.2,
                alpha=0.7, label="50% of R (half the device!)")
    ax1.axhline(R_MAX_M * 1e3 * 0.25, color="orange", linestyle=":", linewidth=1.2,
                alpha=0.7, label="25% of R")

    # vertical markers for key widths
    for wm, col, lbl in [(8, "#aaa", "8 µm"), (20, "#bbb", "20 µm"),
                          (30, "#888", "30 µm (= exit)")]:
        ax1.axvline(wm, color=col, linestyle=":", linewidth=0.9)
        ax1.text(wm + 0.5, R_MAX_M * 1e3 * 0.95, lbl, fontsize=7, color="#555")

    ax1.set_xlabel("Channel width  (µm)", fontsize=11)
    ax1.set_ylabel("Minimum hub radius  (mm)", fontsize=11)
    ax1.set_title("How big the hub must be", fontsize=10)
    ax1.legend(fontsize=8, framealpha=0.9)
    ax1.grid(True, alpha=0.25)
    ax1.set_xlim(4, 60)
    ax1.set_ylim(0, R_MAX_M * 1e3 * 1.05)

    # ── Right: dead area fraction ─────────────────────────────────────────────
    ax2.plot(w_scan_um, dead_area_frac * 100, "b-", linewidth=2,
             label="Uniform: dead area = (r_hub/R)²")
    ax2.plot(w_scan_um, dead_area_taper * 100, "g--", linewidth=2,
             label="Tapered: dead area = (r_hub/R)²")

    ax2.fill_between(w_scan_um, dead_area_frac * 100, alpha=0.12, color="blue")
    ax2.axhline(50, color="red", linestyle=":", linewidth=1.2, alpha=0.7,
                label="50% dead (half device unused)")
    ax2.axhline(25, color="orange", linestyle=":", linewidth=1.2, alpha=0.7,
                label="25% dead")

    for wm, col in [(8, "#aaa"), (20, "#bbb"), (30, "#888")]:
        ax2.axvline(wm, color=col, linestyle=":", linewidth=0.9)

    ax2.set_xlabel("Channel width  (µm)", fontsize=11)
    ax2.set_ylabel("Hub dead-zone as % of device area", fontsize=11)
    ax2.set_title("Wasted area in hub region", fontsize=10)
    ax2.legend(fontsize=8, framealpha=0.9)
    ax2.grid(True, alpha=0.25)
    ax2.set_xlim(4, 60)
    ax2.set_ylim(0, 105)

    # annotate key widths on right panel
    for wm in [8, 20, 30]:
        wm_m = wm * 1e-6
        ya = (r_merge(wm_m) / R_MAX_M)**2 * 100
        ax2.annotate(
            f"{wm}µm\n→ {ya:.0f}% dead",
            xy=(wm, ya), xytext=(wm + 3, ya + 5),
            fontsize=7.5, color="#333",
            arrowprops=dict(arrowstyle="->", color="#333", lw=0.8),
        )

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path}")
    return fig


# ── Figure 3: close-up of hub convergence (small angular slice) ───────────────

def plot_hub_closeup(save_path=None):
    """
    Zoomed view of a small angular wedge near the hub, showing
    how channels converge for the three design options.
    """
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle(
        "Hub convergence — close-up view (angular wedge, radii in µm scale)\n"
        "Showing 7 adjacent channels at the hub boundary",
        fontsize=11,
    )

    configs = [
        ("Uniform  w=8µm",  8e-6,  "uniform",  "#3a86ff"),
        ("Uniform  w=30µm", 30e-6, "uniform",  "#e63946"),
        ("Tapered  w_min=5µm → 30µm", 5e-6, "tapered", "#2ec4b6"),
    ]

    for ax, (title, w_param, mode, color) in zip(axes, configs):
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=9)

        N_show = 9    # channels to show in closeup
        if mode == "uniform":
            w_up = w_param
            r_hub = r_merge(w_up, R_MAX_M, PITCH_M)
        else:
            w_min = w_param
            r_hub = r_hub_tapered(w_min, EXIT_WIDTH_M)

        # angle subtended by a few channels at the hub
        angle_per_dfu = 2 * np.pi / N_DFU
        half_span = (N_show // 2 + 1) * angle_per_dfu
        center_a = np.pi / 2   # point upward for clarity

        # plot range: from hub out to hub + some length
        r_show_inner = r_hub * 0.5
        r_show_outer = r_hub * 2.2

        # draw channels
        for i in range(-N_show // 2, N_show // 2 + 1):
            a = center_a + i * angle_per_dfu
            if mode == "uniform":
                # constant width channel walls (offset perpendicularly)
                w_half = w_up / 2
                # approximate: draw centerline + offset lines
                cx0 = r_show_inner * np.cos(a)
                cy0 = r_show_inner * np.sin(a)
                cx1 = r_show_outer * np.cos(a)
                cy1 = r_show_outer * np.sin(a)
                ax.plot([cx0, cx1], [cy0, cy1], color=color, linewidth=1.5, alpha=0.8)
                # channel walls (perpendicular offset)
                perp_a = a + np.pi / 2
                for sign in [+1, -1]:
                    wx0 = cx0 + sign * w_half * np.cos(perp_a)
                    wy0 = cy0 + sign * w_half * np.sin(perp_a)
                    wx1 = cx1 + sign * w_half * np.cos(perp_a)
                    wy1 = cy1 + sign * w_half * np.sin(perp_a)
                    ax.plot([wx0, wx1], [wy0, wy1], color=color,
                            linewidth=0.7, alpha=0.4, linestyle="--")
            else:
                # tapered: width ∝ r
                r_arr = np.linspace(r_show_inner, r_show_outer, 50)
                cx = r_arr * np.cos(a)
                cy = r_arr * np.sin(a)
                for k in range(len(r_arr) - 1):
                    frac = (r_arr[k] - r_show_inner) / (r_show_outer - r_show_inner)
                    lw = 0.4 + 2.5 * frac
                    ax.plot([cx[k], cx[k+1]], [cy[k], cy[k+1]],
                            color=color, linewidth=lw, alpha=0.8)

        # hub circle
        hub_ring = plt.Circle((0, 0), r_hub, fill=True,
                               facecolor="#3a86ff", alpha=0.15,
                               edgecolor="#3a86ff", linewidth=2, linestyle="--")
        ax.add_patch(hub_ring)

        # inner/outer view boundary
        view_ring = plt.Circle((0, 0), r_show_outer, fill=False,
                                edgecolor="#ccc", linewidth=0.8, linestyle=":")
        ax.add_patch(view_ring)

        # annotate hub radius
        ax.annotate(
            f"r_hub = {r_hub*1e3:.1f} mm",
            xy=(0, r_hub), xytext=(r_hub * 0.4, r_hub * 1.6),
            fontsize=8,
            arrowprops=dict(arrowstyle="->", color="#3a86ff", lw=0.8),
            color="#3a86ff",
        )

        # spacing annotation at hub boundary
        spacing_at_hub = 2 * np.pi * r_hub / N_DFU * 1e6   # µm
        ax.text(
            0, -r_show_outer * 0.8,
            f"Spacing at hub = {spacing_at_hub:.1f} µm",
            ha="center", va="center", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#888", alpha=0.8),
        )

        ax.set_xlim(-r_show_outer * 1.05, r_show_outer * 1.05)
        ax.set_ylim(-r_show_outer * 1.05, r_show_outer * 1.05)

        # unit label (meters, convert to mm for display)
        scale = r_show_outer
        unit = "mm" if scale > 1e-3 else "µm"
        factor = 1e3 if scale > 1e-3 else 1e6
        ticks = np.linspace(-r_show_outer, r_show_outer, 5)
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{t*factor:.0f}" for t in ticks], fontsize=7)
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"{t*factor:.0f}" for t in ticks], fontsize=7)
        ax.set_xlabel(unit, fontsize=8)
        ax.grid(True, alpha=0.15)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved -> {save_path}")
    return fig


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nN_DFU = {N_DFU:,}  (R = {R_MAX_M*1e3:.0f} mm, pitch = {PITCH_M*1e6:.0f} um)")
    print("\nHub radius for uniform channels (just touching, no wall):")
    for w_um in [4, 5, 8, 10, 15, 20, 27, 30]:
        rh = r_merge(w_um * 1e-6)
        print(f"  w_up = {w_um:3d} um  ->  r_hub = {rh*1e3:6.2f} mm  "
              f"({rh/R_MAX_M*100:.0f}% of R,  dead area = {(rh/R_MAX_M)**2*100:.0f}%)")

    print("\nHub radius for tapered channels (w proportional to r/R):")
    for w_min_um in [3, 5, 8, 10]:
        rh = r_hub_tapered(w_min_um * 1e-6)
        print(f"  w_min = {w_min_um:2d} um  ->  r_hub = {rh*1e3:6.2f} mm  "
              f"({rh/R_MAX_M*100:.0f}% of R,  dead area = {(rh/R_MAX_M)**2*100:.0f}%)")

    plot_device_schematic(save_path=str(OUT_DIR / "geometry_device.png"))
    plot_hub_size(save_path=str(OUT_DIR / "geometry_hub_size.png"))
    plot_hub_closeup(save_path=str(OUT_DIR / "geometry_hub_closeup.png"))
    print("\nDone.")
