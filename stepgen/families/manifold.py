"""
stepgen.families.manifold
=========================
The manifold ("comb" / tapped-ladder) family — a primary oil spine feeding
**M parallel arms**, each arm a short sub-ladder of **n rungs** that drain to the
continuous phase.  Total DFU count ``N = M · n``.

Why a comb (and not an H-tree)
------------------------------
The parametrization was pinned by the ``comp_manifold_parametrization`` workspace:

  * Flatness is a **V-curve** vs the number of arms M — a single long serpentine
    main has one long pressure droop (far rungs starve); a comb replaces it with
    two short droops (spine + arm).  The best split is where each arm is about
    one droop length long, ``n ≈ λ_arm = √(R_rung / r_arm)``, with a **deep+wide
    (beefy) primary** (depth costs no in-plane area — the deep-DFU "free" lever).
  * A symmetric **H-tree** is flatter still (uniform by symmetry) but *partitions
    the plane*, so the continuous phase cannot drain the interior exits without
    crossing the oil — it fails the hard **no-crossing** gate.  The comb keeps its
    arms as **open fingers** with the continuous phase draining in the inter-arm
    gaps, so it is planar by construction.  Hence: comb, not tree.

Oil-distribution model
----------------------
Like the live simplified-Poiseuille view, rungs drain to a shared continuous
reference ``P_out`` through the rung resistance, so the oil network is a resistive
tree solved by :class:`stepgen.models.nodal_network.NodalNetwork`.  Droplet
size / frequency reuse the same power-law as the other families (regime-blind;
flagged for deep exits).

Study geometry block (``manifold:``)
------------------------------------
    main:  { depth_um, width_um }                      # PRIMARY spine (keep deep+wide)
    arms:  { count, spacing_um, depth_um, width_um }   # M open fingers
    rung:  { length_mm, upstream_width_um }            # DFU channel (depth = exit_depth)
    rungs_per_arm: <n>                                 # N_dfu = count * n
    junction: { exit_width_um, exit_depth_um, pitch_um }
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from stepgen.families.base import CommonMetrics, Family, register_family
from stepgen.models.nodal_network import NodalNetwork

_M3S_TO_MLHR = 1e6 * 3600.0
_MBAR_TO_PA = 100.0
MU_DEFAULT = 0.06


def _leaf(block: dict, *path, default=None):
    node: Any = block
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _R_rect(L: float, w: float, h: float, mu: float) -> float:
    """Rectangular-channel resistance (matches stepgen.models.resistance)."""
    if not (0 < h < w):
        raise ValueError(
            f"rectangular resistance needs 0 < depth < width; got w={w*1e6:.1f}µm, "
            f"h={h*1e6:.1f}µm — widen the channel or reduce its depth."
        )
    corr = 1.0 - 0.63 * (h / w)
    return 12.0 * mu * L / (w * h ** 3 * corr)


@dataclass
class ManifoldCompiled:
    """Family-native config for one comb-manifold design point (SI units)."""
    M: int                    # number of arms
    n: int                    # rungs per arm
    # resistances
    R_rung: float
    r_arm: float
    r_prim: float
    # geometry (for gates / metrics)
    pitch_m: float
    spacing_m: float
    arm_width_m: float
    main_depth_m: float
    main_width_m: float
    exit_width_m: float
    exit_depth_m: float
    upstream_width_m: float
    # environment
    square_side_m: float
    min_feature_m: float
    max_main_depth_m: float
    max_main_width_m: float
    mu_oil: float
    gamma: float


@register_family
class ManifoldFamily(Family):
    name = "manifold"

    def applicable_metrics(self) -> set[str]:
        # Same comparable gates as serpentine, plus a real no_crossing build gate.
        return {"throughput_mlhr", "uniformity_pct", "operating_Po_mbar",
                "regime_Ca", "build"}

    # -- compile -----------------------------------------------------------
    def compile(
        self,
        params: dict[str, Any],
        *,
        fluids: dict[str, Any],
        footprint: dict[str, Any],
        manufacturing: dict[str, Any],
    ) -> ManifoldCompiled:
        mu = float(fluids.get("mu_dispersed", MU_DEFAULT))

        M = int(_leaf(params, "arms", "count", default=20))
        n = int(params.get("rungs_per_arm", 100))
        if M < 1 or n < 1:
            raise ValueError(f"need arms.count >= 1 and rungs_per_arm >= 1; got M={M}, n={n}")

        pitch = float(_leaf(params, "junction", "pitch_um", default=120.0)) * 1e-6
        exit_w = float(_leaf(params, "junction", "exit_width_um", default=30.0)) * 1e-6
        exit_d = float(_leaf(params, "junction", "exit_depth_um", default=20.0)) * 1e-6

        arm_w = float(_leaf(params, "arms", "width_um", default=200.0)) * 1e-6
        arm_d = float(_leaf(params, "arms", "depth_um", default=100.0)) * 1e-6
        spacing = float(_leaf(params, "arms", "spacing_um", default=arm_w * 1e6 + 20.0)) * 1e-6

        main_d = float(_leaf(params, "main", "depth_um", default=200.0)) * 1e-6
        main_w = float(_leaf(params, "main", "width_um", default=1000.0)) * 1e-6

        rung_len = float(_leaf(params, "rung", "length_mm", default=2.0)) * 1e-3
        upstream_w = float(_leaf(params, "rung", "upstream_width_um", default=30.0)) * 1e-6

        # resistances (rung depth == exit depth: single-etch step)
        R_rung = _R_rect(rung_len, upstream_w, exit_d, mu)
        r_arm = _R_rect(pitch, arm_w, arm_d, mu)
        r_prim = _R_rect(spacing, main_w, main_d, mu)

        side = float(footprint.get("square_side_mm", 63.5)) * 1e-3
        min_feature = float(manufacturing.get("min_wall_um", 0.5)) * 1e-6
        max_main_depth = float(manufacturing.get("max_main_depth_um", 200.0)) * 1e-6
        max_main_width = float(manufacturing.get("max_main_width_um", 1000.0)) * 1e-6

        return ManifoldCompiled(
            M=M, n=n, R_rung=R_rung, r_arm=r_arm, r_prim=r_prim,
            pitch_m=pitch, spacing_m=spacing, arm_width_m=arm_w,
            main_depth_m=main_d, main_width_m=main_w,
            exit_width_m=exit_w, exit_depth_m=exit_d, upstream_width_m=upstream_w,
            square_side_m=side, min_feature_m=min_feature,
            max_main_depth_m=max_main_depth, max_main_width_m=max_main_width,
            mu_oil=mu, gamma=float(fluids.get("gamma", 0.0)),
        )

    # -- solve -------------------------------------------------------------
    def solve(
        self,
        compiled: ManifoldCompiled,
        operating: dict[str, Any],
        *,
        params: dict[str, Any],
        label: str,
    ) -> CommonMetrics:
        return solve_manifold(
            compiled,
            Po_mbar=float(operating.get("Po_mbar", 200.0)),
            params=params,
            label=label,
        )


def build_comb_network(c: ManifoldCompiled, *, Po_Pa: float, P_out_Pa: float = 0.0):
    """Assemble the comb nodal graph and return (network, rung_edge_indices).

    Recipe (pinned by comp_manifold_parametrization):
      ground fixed at P_out; spine head fixed at P_in; spine = chain of M nodes
      joined by primary segments; each spine node → an arm = chain of n nodes
      joined by arm segments; each arm node → ground through the rung.
    """
    net = NodalNetwork()
    gnd = net.add_node(); net.fix(gnd, P_out_Pa)
    head = net.add_node(); net.fix(head, Po_Pa)

    rung_edges: list[int] = []
    prev_spine = head
    for _arm in range(c.M):
        s = net.add_node()
        net.add_edge(prev_spine, s, c.r_prim)      # primary segment
        prev_spine = s
        prev_arm = s
        for _k in range(c.n):
            a = net.add_node()
            net.add_edge(prev_arm, a, c.r_arm)     # arm segment
            rung_edges.append(net.add_edge(a, gnd, c.R_rung))  # the rung
            prev_arm = a
    return net, rung_edges


def solve_manifold(
    c: ManifoldCompiled,
    *,
    Po_mbar: float,
    params: dict[str, Any] | None = None,
    label: str = "",
) -> CommonMetrics:
    """Solve one comb manifold at a supply pressure ``Po_mbar`` → CommonMetrics.

    Exposed as a module function so tests can drive it directly (mirrors
    ``serpentine.solve_config`` / ``radial.solve_radial``).
    """
    Po_Pa = Po_mbar * _MBAR_TO_PA
    net, rung_edges = build_comb_network(c, Po_Pa=Po_Pa)
    P = net.solve()

    # per-rung flow = flow through each rung edge (tap → ground)
    q = np.array([net.edge_flow(e, P) for e in rung_edges], dtype=float)
    q_total = float(np.sum(q))
    q_mean = float(np.mean(q)) if q.size else 0.0
    N_dfu = c.M * c.n

    uniformity_pct = (
        float((np.max(q) - np.min(q)) / q_mean * 100.0) if q_mean > 0 else None
    )
    throughput_mlhr = q_total * _M3S_TO_MLHR

    # ── droplet size / frequency (same regime-blind power-law as other families) ─
    from stepgen.config import DropletModelConfig
    dm = DropletModelConfig()
    D_m = dm.k * (c.exit_width_m ** dm.a) * (c.exit_depth_m ** dm.b)
    v_drop = (math.pi / 6.0) * D_m ** 3
    freq = q_mean / v_drop if v_drop > 0 else 0.0

    # ── exit capillary number (diagnostic) ──────────────────────────────────
    regime_Ca: float | None = None
    if c.gamma > 0 and c.exit_width_m > 0 and c.exit_depth_m > 0 and q_mean > 0:
        v_exit = q_mean / (c.exit_width_m * c.exit_depth_m)
        regime_Ca = c.mu_oil * v_exit / c.gamma

    # ── layout + fabrication + no-crossing gates ────────────────────────────
    arm_len = c.n * c.pitch_m
    comb_span = c.M * c.spacing_m
    area_used_cm2 = arm_len * comb_span * 1e4
    fits_square = bool(arm_len <= c.square_side_m and comb_span <= c.square_side_m)

    manufacturable = bool(
        c.main_depth_m <= c.max_main_depth_m
        and c.main_width_m <= c.max_main_width_m
        and c.upstream_width_m >= c.min_feature_m
        and c.exit_depth_m >= c.min_feature_m
        and c.arm_width_m >= c.min_feature_m
    )

    # no-crossing (planar drainage): the continuous phase drains in the gap
    # between adjacent arms. That gap must be at least a minimum feature wide.
    inter_arm_gap = c.spacing_m - c.arm_width_m
    no_crossing = bool(inter_arm_gap >= c.min_feature_m)

    # ── advisory notes ──────────────────────────────────────────────────────
    lam_arm = math.sqrt(c.R_rung / c.r_arm)
    notes: list[str] = []
    if c.exit_depth_m * 1e6 > 12.0:
        notes.append(
            "deep exit: power-law droplet size extrapolated (~2x) — size/frequency not trusted"
        )
    if c.n > 1.5 * lam_arm:
        notes.append(
            f"arms long vs droop length (n={c.n} > 1.5·λ_arm={1.5*lam_arm:.0f}): "
            f"far rungs starve — add arms (raise count, lower rungs_per_arm)"
        )
    if not no_crossing:
        notes.append(
            f"no drain gap: arm spacing {c.spacing_m*1e6:.0f}µm ≤ arm width "
            f"{c.arm_width_m*1e6:.0f}µm + min feature — continuous cannot drain (widen spacing)"
        )
    notes.append(f"comb: {c.M} arms × {c.n} rungs (λ_arm≈{lam_arm:.0f} rungs)")

    return CommonMetrics(
        family="manifold",
        label=label,
        params=dict(params or {}),
        throughput_mlhr=throughput_mlhr,
        N_dfu=N_dfu,
        droplet_um=D_m * 1e6,
        frequency_hz=freq,
        uniformity_pct=uniformity_pct,
        operating_Po_mbar=Po_mbar,
        regime_Ca=regime_Ca,
        hub_budget_pct=None,        # N-A for manifold (radial-specific)
        area_used_cm2=area_used_cm2,
        fits_square=fits_square,
        manufacturable=manufacturable,
        no_crossing=no_crossing,
        notes=notes,
        raw={
            "M_arms": c.M,
            "n_rungs_per_arm": c.n,
            "N_dfu": N_dfu,
            "lambda_arm_rungs": lam_arm,
            "n_over_lambda": c.n / lam_arm,
            "R_rung_Pa_s_m3": c.R_rung,
            "r_arm_Pa_s_m3": c.r_arm,
            "r_prim_Pa_s_m3": c.r_prim,
            "arm_length_mm": arm_len * 1e3,
            "comb_span_mm": comb_span * 1e3,
            "inter_arm_gap_um": inter_arm_gap * 1e6,
            "Q_per_dfu_nL_hr": q_mean * 1e12 * 3600.0,
            "Q_total_uL_hr": q_total * 1e9 * 3600.0,
        },
    )
