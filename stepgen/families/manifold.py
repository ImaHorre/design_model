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

Hydraulic model — two rails (same setup as the serpentine ladder)
-----------------------------------------------------------------
Both phases are solved together in one :class:`stepgen.models.nodal_network.NodalNetwork`,
exactly like the serpentine ladder but with a comb oil side:

  * OIL rail — pressure-driven at ``Po``: a primary spine feeds M parallel arms,
    each arm a chain of n tap nodes.  N = M·n taps.
  * WATER rail — flow-driven at ``Qw``: a **single serpentine collection channel**
    threads past every rung (no dead zones), so ``P_water`` droops along it just
    like the oil side.  Continuous phase enters flow-controlled at one end and
    leaves at ``P_out``.
  * RUNGS couple each oil tap to its water node; the per-rung flow is set by the
    LOCAL ``P_oil − P_water`` (not a fixed sink).

(The radial family is the deliberate exception: all channels feed one bulk where
oil- and water-side pressures are essentially constant — flatness automatic.)
Droplet size / frequency reuse the same power-law as the other families
(regime-blind; flagged for deep exits).

Packing / footprint model (the honest arm-to-arm pitch)
-------------------------------------------------------
The old model spaced arms by ``arm_width + 20 µm`` and ignored the DFUs entirely,
which overestimated the DFU count by ~10-20x.  The real cross-section, walking
across the stack (perpendicular to the arms), is a repeating cell::

    ┌ arm ┐  DFUs   cont-phase   wall   cont-phase   DFUs  ┌ arm ┐
    │W_arm│──L_dfu──│  W_cp  │──W_wall──│  W_cp  │──L_dfu──│W_arm│
             (out)                (return leg of the loop)

  * DFUs protrude from **both faces** of every arm (``L_dfu`` = rung length), so
    each arm's ``n`` rungs are split ``n/2`` per side and the arm is only half as
    long as a one-sided arm of the same count.
  * The continuous phase is a **loop, not a dead end**: it runs out along one arm's
    DFUs, turns at the inner (spine) edge, and returns along the neighbouring arm's
    DFUs — hence **two** ``W_cp`` widths between adjacent arms.
  * A **separating wall** keeps the out/return legs from merging into a dead pool.
    The collection channels are the deep step-emulsification reservoir, so the wall
    is etched to the main depth; holding its aspect ratio <= 2 requires
    ``W_wall >= main_depth / 2`` (floored at ``wall.min_um``).  A wall at AR 2 is
    the manufacturable edge -> orange.

    arm-to-arm pitch  =  W_arm + 2·L_dfu + 2·W_cp + W_wall

``W_cp`` may be **flow-scaled** (default): the collection channel must pass the oil
it drains, ``W_cp = max(base, n_side·q_rung / (v_cap · depth))``.  This uses only
the oil flow the nodal solve already has; the continuous carrier is not yet added,
so the flow-scaled width is a lower bound (see report note).

Study geometry block (``manifold:``)
------------------------------------
    main:  { depth_um, width_um }                      # PRIMARY spine (keep deep+wide)
    arms:  { count, depth_um, width_um }               # M open fingers (no spacing_um)
    rung:  { length_mm, upstream_width_um }            # DFU protrusion (depth = exit_depth)
    rungs_per_arm: <n>                                 # N_dfu = count * n (n/2 per face)
    junction: { exit_width_um, exit_depth_um, pitch_um }
    cont_phase: { width_um, flow_scaled, max_velocity_mps, outlet_width_um }
    wall: { min_um, width_um }                         # width_um optional override
    # footprint block adds: feed_length_mm (spine length), reserve_border_mm
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from stepgen.families.base import CommonMetrics, Family, register_family
from stepgen.families.intent import (
    Constraints,
    Intent,
    plan_junction,
    rungs_for_throughput,
)
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
    n: int                    # rungs per arm (split n/2 per face)
    # resistances
    R_rung: float
    r_arm: float
    r_prim: float
    # geometry (for gates / metrics)
    pitch_m: float            # along-arm DFU pitch (junction pitch)
    arm_width_m: float
    rung_len_m: float         # L_dfu — DFU protrusion off each arm face
    main_depth_m: float
    main_width_m: float
    exit_width_m: float
    exit_depth_m: float
    upstream_width_m: float
    # continuous-phase collection + separating wall (packing)
    cp_base_m: float          # continuous-phase channel width (floor)
    cp_flow_scaled: bool      # scale cp width with collected oil flow?
    cp_v_cap: float           # max oil velocity in the collection channel [m/s]
    cp_depth_m: float         # continuous-phase (water) channel depth
    wall_width_m: float       # separating wall between out/return legs
    wall_min_m: float
    outlet_m: float           # continuous-phase outlet manifold allowance
    # water rail (single serpentine collection channel past all rungs)
    r_water: float            # water-channel resistance per rung segment [Pa·s/m³]
    mu_water: float           # continuous-phase viscosity [Pa·s]
    # environment
    square_side_m: float
    feed_length_m: float      # spine length available for stacking arms
    border_m: float
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
                "regime_Ca", "build", "validity"}

    # -- intent ------------------------------------------------------------
    #: arm counts intent sweeps.  The comb's flatness is a V-curve in M, so the
    #: sweep has to straddle the minimum rather than pick a point on it.
    INTENT_ARM_COUNTS: tuple[int, ...] = (2, 4, 8, 16)

    def grid_from_intent(
        self,
        intent: Intent,
        constraints: Constraints,
        *,
        fluids: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Comb-manifold geometry for a droplet + throughput target.

        The DFU count ``N = M · n`` is split two ways, and the split is the whole
        point of the family: flatness is a **V-curve in M** (one long droop vs
        two short ones), so intent sweeps arm counts across the minimum rather
        than guessing where it sits.  ``rungs_per_arm`` is generated as
        ``ceil(N_est / M)`` for each swept ``M``, so the paired combinations hold
        the total count roughly constant and isolate the split — the other
        combinations in the Cartesian product then show the count dependence too.

        The primary spine is pinned deep and wide at the fab caps: depth costs no
        in-plane area, which is the free lever the manifold parametrisation work
        identified.
        """
        plan = plan_junction(intent, constraints, rung_length_mm=(1.0, 2.0))
        n_est = rungs_for_throughput(
            throughput_mlhr=intent.throughput_mlhr,
            Po_mbar=constraints.max_Po_mbar,
            rung_length_m=plan.mid_rung_length_m,
            upstream_width_m=plan.mid_upstream_m,
            exit_depth_m=plan.exit_depth_um * 1e-6,
            mu_dispersed=float(fluids.get("mu_dispersed", 0.06)),
        )
        per_arm = sorted({max(2, math.ceil(n_est / M)) for M in self.INTENT_ARM_COUNTS})

        # arms are shallower than the spine and must stay wider than they are
        # deep for the rectangular resistance to hold
        arm_depth = min(100.0, constraints.max_main_depth_um)
        arm_width = max(200.0, 2.0 * arm_depth)

        return {
            "main": {
                "depth_um": constraints.max_main_depth_um,
                "width_um": constraints.max_main_width_um,
            },
            "arms": {
                "count": list(self.INTENT_ARM_COUNTS),
                "depth_um": arm_depth,
                "width_um": arm_width,
            },
            "rung": {
                "length_mm": plan.mid_rung_length_m * 1e3,
                "upstream_width_um": plan.upstream_width_um,
            },
            "rungs_per_arm": per_arm,
            "junction": {
                "exit_width_um": plan.exit_width_um,
                "exit_depth_um": plan.exit_depth_um,
                "pitch_um": plan.pitch_um,
            },
            "cont_phase": {
                "width_um": 200.0,
                "flow_scaled": True,
                "max_velocity_mps": 0.1,
            },
            # the wall between the out/return continuous legs; the family widens
            # it to main_depth/2 to hold its aspect ratio at 2
            "wall": {"min_um": 100.0},
        }

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
        mu_water = float(fluids.get("mu_continuous", 0.00089))

        M = int(_leaf(params, "arms", "count", default=20))
        n = int(params.get("rungs_per_arm", 100))
        if M < 1 or n < 1:
            raise ValueError(f"need arms.count >= 1 and rungs_per_arm >= 1; got M={M}, n={n}")

        pitch = float(_leaf(params, "junction", "pitch_um", default=120.0)) * 1e-6
        exit_w = float(_leaf(params, "junction", "exit_width_um", default=30.0)) * 1e-6
        exit_d = float(_leaf(params, "junction", "exit_depth_um", default=20.0)) * 1e-6

        arm_w = float(_leaf(params, "arms", "width_um", default=200.0)) * 1e-6
        arm_d = float(_leaf(params, "arms", "depth_um", default=100.0)) * 1e-6

        main_d = float(_leaf(params, "main", "depth_um", default=200.0)) * 1e-6
        main_w = float(_leaf(params, "main", "width_um", default=1000.0)) * 1e-6

        rung_len = float(_leaf(params, "rung", "length_mm", default=2.0)) * 1e-3
        upstream_w = float(_leaf(params, "rung", "upstream_width_um", default=30.0)) * 1e-6

        # ── continuous-phase collection + separating wall (packing geometry) ──
        cp_base = float(_leaf(params, "cont_phase", "width_um", default=200.0)) * 1e-6
        cp_flow_scaled = bool(_leaf(params, "cont_phase", "flow_scaled", default=True))
        cp_v_cap = float(_leaf(params, "cont_phase", "max_velocity_mps", default=0.1))
        cp_depth = float(_leaf(params, "cont_phase", "depth_um",
                               default=main_d * 1e6)) * 1e-6   # deep collection reservoir
        # Hydraulic width of the water collection channel — the "water main" analog
        # (mirrors the serpentine water main = Mcw). Distinct from the narrow packing
        # cp gap: the channel the continuous phase actually flows along can be wide.
        cp_channel_w = float(_leaf(params, "cont_phase", "channel_width_um",
                                   default=main_w * 1e6)) * 1e-6
        outlet = float(_leaf(params, "cont_phase", "outlet_width_um",
                             default=main_w * 1e6)) * 1e-6

        min_feature = float(manufacturing.get("min_wall_um", 0.5)) * 1e-6
        wall_min = float(_leaf(params, "wall", "min_um", default=100.0)) * 1e-6
        # The wall between the out/return continuous legs is etched to the DEEP
        # level (the collection channels are the step-emulsification reservoir),
        # so its aspect ratio is set by the main depth: hold AR <= 2 -> width >=
        # depth/2, floored at wall.min_um.  An explicit wall.width_um overrides.
        wall_override = _leaf(params, "wall", "width_um")
        wall_width = (float(wall_override) * 1e-6 if wall_override is not None
                      else max(wall_min, main_d / 2.0))

        # arm-to-arm pitch: the honest spine segment length between adjacent arms
        pitch_arm = arm_w + 2.0 * rung_len + 2.0 * cp_base + wall_width

        # resistances (rung depth == exit depth: single-etch step).  The primary
        # spine segment spans one arm pitch (was previously the fictitious
        # arm_width+20µm — this is the realistic length).
        R_rung = _R_rect(rung_len, upstream_w, exit_d, mu)
        r_arm = _R_rect(pitch, arm_w, arm_d, mu)
        r_prim = _R_rect(pitch_arm, main_w, main_d, mu)
        # water rail: one serpentine collection channel threads past every rung.
        # A segment spans one along-arm pitch, in the continuous phase, using the
        # (wide) water-channel width — not the narrow packing gap.
        r_water = _R_rect(pitch, cp_channel_w, cp_depth, mu_water)

        side = float(footprint.get("square_side_mm", 63.5)) * 1e-3
        feed_len = float(footprint.get("feed_length_mm", side * 1e3)) * 1e-3
        border = float(footprint.get("reserve_border_mm", 2.0)) * 1e-3
        max_main_depth = float(manufacturing.get("max_main_depth_um", 200.0)) * 1e-6
        max_main_width = float(manufacturing.get("max_main_width_um", 1000.0)) * 1e-6

        return ManifoldCompiled(
            M=M, n=n, R_rung=R_rung, r_arm=r_arm, r_prim=r_prim,
            pitch_m=pitch, arm_width_m=arm_w, rung_len_m=rung_len,
            main_depth_m=main_d, main_width_m=main_w,
            exit_width_m=exit_w, exit_depth_m=exit_d, upstream_width_m=upstream_w,
            cp_base_m=cp_base, cp_flow_scaled=cp_flow_scaled, cp_v_cap=cp_v_cap,
            cp_depth_m=cp_depth,
            wall_width_m=wall_width, wall_min_m=wall_min, outlet_m=outlet,
            r_water=r_water, mu_water=mu_water,
            square_side_m=side, feed_length_m=feed_len, border_m=border,
            min_feature_m=min_feature,
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
            Qw_mlhr=float(operating.get("Qw_mlhr", 5.0)),
            params=params,
            label=label,
        )


def build_comb_network(
    c: ManifoldCompiled, *, Po_Pa: float, Qw_m3s: float = 0.0, P_out_Pa: float = 0.0
):
    """Assemble the two-rail comb network → (net, rung_edges, oil_nodes, water_nodes).

    Same two-rail setup as the serpentine ladder, generalised to a comb oil side:

      OIL rail (pressure-driven):  head fixed at ``Po_Pa``; spine = chain of M nodes
        joined by primary segments (``r_prim``); each spine node → an arm = chain of
        n nodes joined by arm segments (``r_arm``).  There are N = M·n oil tap nodes.

      WATER rail (flow-driven, single serpentine collection channel — NO dead zones):
        one water node per rung, chained in tap order by the water-channel segment
        resistance (``r_water``).  The continuous phase enters flow-controlled
        (``Qw_m3s`` injected at the first water node) and leaves at ``P_out_Pa``
        (last node), so P_water drops along the channel just like the oil side.

      RUNGS couple each oil tap node → its water node through ``R_rung``; the rung
      flow is oil→water, so the per-rung driving ΔP is ``P_oil − P_water`` locally.

    ``rung_edges[k]``, ``oil_nodes[k]``, ``water_nodes[k]`` are aligned by rung index.
    """
    net = NodalNetwork()
    head = net.add_node(); net.fix(head, Po_Pa)   # oil supply (pressure BC)

    # ── oil comb: N tap nodes in (arm, rung) creation order ──────────────────
    oil_nodes: list[int] = []
    prev_spine = head
    for _arm in range(c.M):
        s = net.add_node()
        net.add_edge(prev_spine, s, c.r_prim)      # primary spine segment
        prev_spine = s
        prev_arm = s
        for _k in range(c.n):
            a = net.add_node()
            net.add_edge(prev_arm, a, c.r_arm)     # arm segment
            oil_nodes.append(a)
            prev_arm = a

    # ── water rail: one serpentine channel past every rung, in the same order ─
    water_nodes: list[int] = []
    prev_w: int | None = None
    for _ in oil_nodes:
        w = net.add_node()
        if prev_w is not None:
            net.add_edge(prev_w, w, c.r_water)     # water-channel segment
        water_nodes.append(w)
        prev_w = w
    net.inject(water_nodes[0], Qw_m3s)             # flow-controlled water inlet
    net.fix(water_nodes[-1], P_out_Pa)             # water outlet reference

    # ── rungs: oil tap → water node (flow is oil→water) ──────────────────────
    rung_edges: list[int] = [
        net.add_edge(a, w, c.R_rung) for a, w in zip(oil_nodes, water_nodes)
    ]
    return net, rung_edges, oil_nodes, water_nodes


def solve_manifold(
    c: ManifoldCompiled,
    *,
    Po_mbar: float,
    Qw_mlhr: float = 5.0,
    params: dict[str, Any] | None = None,
    label: str = "",
) -> CommonMetrics:
    """Solve one comb manifold at (``Po_mbar``, ``Qw_mlhr``) → CommonMetrics.

    Two-rail solve, same setup as the serpentine ladder: oil is pressure-driven
    (``Po``), the continuous phase is flow-driven (``Qw``) through a single
    serpentine collection channel, and each rung's flow is set by the LOCAL
    ``P_oil − P_water``.  Exposed as a module function so tests can drive it
    directly (mirrors ``serpentine.solve_config`` / ``radial.solve_radial``).
    """
    from stepgen.config import mlhr_to_m3s

    Po_Pa = Po_mbar * _MBAR_TO_PA
    Qw_m3s = mlhr_to_m3s(Qw_mlhr)
    net, rung_edges, oil_nodes, water_nodes = build_comb_network(
        c, Po_Pa=Po_Pa, Qw_m3s=Qw_m3s
    )
    P = net.solve()

    # per-rung pressures + flow (rung edge is oil tap → water node; +ve = oil→water)
    P_oil = P[np.asarray(oil_nodes, dtype=int)]
    P_water = P[np.asarray(water_nodes, dtype=int)]
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

    # ── packing / footprint (realistic arm-to-arm pitch) ────────────────────
    # DFUs protrude from BOTH faces, so the n rungs split n/2 per side and the
    # arm is only half as long as a one-sided arm of the same count.
    n_side = math.ceil(c.n / 2)
    arm_len = n_side * c.pitch_m

    # continuous-phase collection width: a floor, optionally widened to pass the
    # oil it drains (n_side rungs at q_mean, deep collection at the main depth).
    # NOTE: the continuous carrier flow is not in this oil-only network, so the
    # flow-scaled width is a LOWER bound (see report note).
    cp_w = c.cp_base_m
    if c.cp_flow_scaled and c.cp_v_cap > 0 and c.main_depth_m > 0:
        cp_flow = (n_side * q_mean) / (c.cp_v_cap * c.main_depth_m)
        cp_w = max(cp_w, cp_flow)

    pitch_arm = c.arm_width_m + 2.0 * c.rung_len_m + 2.0 * cp_w + c.wall_width_m
    # stack extent across the arms: M arm cells (arm + its two DFU rows), (M-1)
    # inter-arm loop pairs (2·cp + wall), plus one collection channel per outer edge.
    stack = (
        c.M * (c.arm_width_m + 2.0 * c.rung_len_m)
        + max(c.M - 1, 0) * (2.0 * cp_w + c.wall_width_m)
        + 2.0 * cp_w
    )
    # perpendicular extent: spine + arm reach + continuous outlet manifold + borders
    perp = 2.0 * c.border_m + c.main_width_m + arm_len + c.outlet_m

    stack_budget = min(c.feed_length_m, c.square_side_m) - 2.0 * c.border_m
    fits_square = bool(
        stack <= stack_budget
        and perp <= c.square_side_m
        and c.feed_length_m <= c.square_side_m
    )
    area_used_cm2 = stack * perp * 1e4

    # ── fabrication + no-crossing gates ─────────────────────────────────────
    wall_ar = c.main_depth_m / c.wall_width_m if c.wall_width_m > 0 else float("inf")
    manufacturable = bool(
        c.main_depth_m <= c.max_main_depth_m
        and c.main_width_m <= c.max_main_width_m
        and c.upstream_width_m >= c.min_feature_m
        and c.exit_depth_m >= c.min_feature_m
        and c.arm_width_m >= c.min_feature_m
        and c.wall_width_m >= c.min_feature_m
        and wall_ar <= 2.0 + 1e-6            # a taller-than-2× wall slumps
    )

    # no-crossing (planar drainage): the continuous phase circulates through the
    # loop, kept open by the separating wall.  Both the collection channel and
    # the wall must be at least a minimum feature wide for the loop to exist.
    no_crossing = bool(cp_w >= c.min_feature_m and c.wall_width_m >= c.min_feature_m)

    # ── advisory notes ──────────────────────────────────────────────────────
    lam_arm = math.sqrt(c.R_rung / c.r_arm)
    notes: list[str] = []
    if c.exit_depth_m * 1e6 > 12.0:
        notes.append(
            "deep exit: power-law droplet size extrapolated (~2x) — size/frequency not trusted"
        )
    if n_side > 1.5 * lam_arm:
        notes.append(
            f"arms long vs droop length (n/2={n_side} > 1.5·λ_arm={1.5*lam_arm:.0f}): "
            f"far rungs starve — add arms (raise count, lower rungs_per_arm)"
        )
    if wall_ar > 2.0 + 1e-6:
        notes.append(
            f"wall AR {wall_ar:.1f} > 2 (depth {c.main_depth_m*1e6:.0f}µm / wall "
            f"{c.wall_width_m*1e6:.0f}µm): too thin/tall — widen wall or reduce depth"
        )
    elif wall_ar >= 2.0 - 1e-6:
        notes.append(
            f"wall at AR 2 ({c.wall_width_m*1e6:.0f}µm at {c.main_depth_m*1e6:.0f}µm deep) "
            f"— manufacturable edge (orange)"
        )
    if not no_crossing:
        notes.append(
            f"loop broken: cont-phase {cp_w*1e6:.0f}µm / wall {c.wall_width_m*1e6:.0f}µm "
            f"below min feature {c.min_feature_m*1e6:.0f}µm — continuous cannot circulate"
        )
    if c.cp_flow_scaled and cp_w > c.cp_base_m + 1e-12:
        notes.append(
            f"cont-phase widened to {cp_w*1e6:.0f}µm by oil flow (base {c.cp_base_m*1e6:.0f}µm; "
            f"carrier not yet included — lower bound)"
        )
    notes.append(f"comb: {c.M} arms × {c.n} rungs (n/2 per face; λ_arm≈{lam_arm:.0f})")

    # water-rail droop: how much of the per-rung ΔP variation is continuous-side
    dP_rung = P_oil - P_water
    if q_mean > 0 and P_water.size:
        pw_range = float(np.max(P_water) - np.min(P_water))
        po_range = float(np.max(P_oil) - np.min(P_oil))
        notes.append(
            f"two-rail: P_oil droop {po_range/_MBAR_TO_PA:.1f} mbar, "
            f"P_water droop {pw_range/_MBAR_TO_PA:.2f} mbar over the collection channel"
        )

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
        exit_width_um=c.exit_width_m * 1e6,
        exit_depth_um=c.exit_depth_m * 1e6,
        lambda_visc=(c.mu_water / c.mu_oil) if c.mu_oil else None,
        hub_budget_pct=None,        # N-A for manifold (radial-specific)
        area_used_cm2=area_used_cm2,
        fits_square=fits_square,
        manufacturable=manufacturable,
        no_crossing=no_crossing,
        notes=notes,
        raw={
            "M_arms": c.M,
            "n_rungs_per_arm": c.n,
            "n_per_face": n_side,
            "N_dfu": N_dfu,
            "lambda_arm_rungs": lam_arm,
            "n_over_lambda": n_side / lam_arm,
            "R_rung_Pa_s_m3": c.R_rung,
            "r_arm_Pa_s_m3": c.r_arm,
            "r_prim_Pa_s_m3": c.r_prim,
            "r_water_Pa_s_m3": c.r_water,
            "arm_length_mm": arm_len * 1e3,
            "arm_pitch_mm": pitch_arm * 1e3,
            "stack_extent_mm": stack * 1e3,
            "perp_extent_mm": perp * 1e3,
            "cont_phase_width_um": cp_w * 1e6,
            "wall_width_um": c.wall_width_m * 1e6,
            "wall_aspect_ratio": wall_ar,
            # two-rail hydraulic state (same names as serpentine SimResult)
            "P_oil_min_mbar": float(np.min(P_oil)) / _MBAR_TO_PA,
            "P_oil_max_mbar": float(np.max(P_oil)) / _MBAR_TO_PA,
            "P_water_min_mbar": float(np.min(P_water)) / _MBAR_TO_PA,
            "P_water_max_mbar": float(np.max(P_water)) / _MBAR_TO_PA,
            "dP_rung_min_mbar": float(np.min(dP_rung)) / _MBAR_TO_PA,
            "dP_rung_max_mbar": float(np.max(dP_rung)) / _MBAR_TO_PA,
            "Q_water_total_uL_hr": Qw_mlhr * 1e3,
            "Q_per_dfu_nL_hr": q_mean * 1e12 * 3600.0,
            "Q_total_uL_hr": q_total * 1e9 * 3600.0,
        },
    )
