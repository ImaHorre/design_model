"""
analysis.py — Manifold (comb) parametrization exploration.
===========================================================
Phase-3 GATE step of the Design Studio plan: pin the manifold parametrization
and answer "is there an always-best arms x rungs-per-arm arrangement?" BEFORE
committing the package solver (`stepgen/models/nodal_network.py`) and the
`manifold` family.

This script is deliberately SELF-CONTAINED (throwaway exploration code). Its
`NodalNetwork` class is a *prototype* of the general sparse nodal-graph solver
the package will later host — building it here, against an exact anchor, is
exactly what the gate is for: it validates the assembly recipe cheaply.

Model (oil-distribution only)
-----------------------------
Oil enters the primary spine at pressure P_in. It distributes through the spine
and arms (resistive channel segments) to N rung tap-nodes; each rung drains to a
shared continuous-phase reference P_out=0 through R_rung (the simplified-
Poiseuille "rung-limited" view the live model uses). The graph is therefore a
resistive TREE to ground. Rung flow q_i = g_rung * P(tap_i); flatness = spread
of q_i (== spread of tap pressures, since g_rung is common).

Resistances use the same rectangular-channel formula as
`stepgen/models/resistance.py`:  R = 12 µ L / (w h^3 (1 - 0.63 h/w)),  h < w.

Run:  python analysis.py
Outputs: results/*.csv, figures/*.png
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
RESULTS = HERE / "results"
FIGS = HERE / "figures"
RESULTS.mkdir(exist_ok=True)
FIGS.mkdir(exist_ok=True)

MU_OIL = 0.06  # Pa·s (sunflower oil)


# ---------------------------------------------------------------------------
# Rectangular-channel resistance (matches stepgen/models/resistance.py)
# ---------------------------------------------------------------------------
def R_rect(L: float, w: float, h: float, mu: float = MU_OIL) -> float:
    """Hydraulic resistance of a rectangular channel [Pa·s/m³]. Requires h < w."""
    if not (0 < h < w):
        raise ValueError(f"need 0 < h < w; got w={w}, h={h}")
    corr = 1.0 - 0.63 * (h / w)
    return 12.0 * mu * L / (w * h ** 3 * corr)


# ---------------------------------------------------------------------------
# Prototype general nodal-graph solver (this is what nodal_network.py becomes)
# ---------------------------------------------------------------------------
@dataclass
class NodalNetwork:
    """Sparse resistive-network solver with Dirichlet (fixed-pressure) nodes.

    Nodes are integer ids obtained from `add_node`. Edges carry a conductance
    g = 1/R. `fix(node, P)` pins a node to pressure P (a source or ground).
    `solve()` returns the pressure at every node via KCL:
        for each free node i:  sum_j g_ij (P_i - P_j) = 0.
    """
    _adj: dict = field(default_factory=dict)      # node -> list[(other, g)]
    _fixed: dict = field(default_factory=dict)    # node -> pressure
    _n: int = 0

    def add_node(self) -> int:
        i = self._n
        self._adj[i] = []
        self._n += 1
        return i

    def add_edge(self, i: int, j: int, R: float) -> None:
        g = 1.0 / R
        self._adj[i].append((j, g))
        self._adj[j].append((i, g))

    def fix(self, node: int, pressure: float) -> None:
        self._fixed[node] = pressure

    def solve(self) -> np.ndarray:
        n = self._n
        A = lil_matrix((n, n), dtype=float)
        b = np.zeros(n, dtype=float)
        for i in range(n):
            if i in self._fixed:
                A[i, i] = 1.0
                b[i] = self._fixed[i]
                continue
            gsum = 0.0
            for (j, g) in self._adj[i]:
                A[i, j] -= g
                gsum += g
            A[i, i] = gsum
        return np.asarray(spsolve(A.tocsr(), b), dtype=float)


# ---------------------------------------------------------------------------
# ANCHOR: exact series/parallel divider (validates the solver)
# ---------------------------------------------------------------------------
def anchor_divider() -> dict:
    """P_in -R1- A -R2- gnd, and A -R3- gnd. Exact node-A pressure by hand:
    A drains through R2 || R3, so P_A = P_in * (R2||R3) / (R1 + R2||R3)."""
    P_in, R1, R2, R3 = 1000.0, 2.0e13, 5.0e13, 3.0e13
    net = NodalNetwork()
    src = net.add_node(); a = net.add_node(); gnd = net.add_node()
    net.fix(src, P_in); net.fix(gnd, 0.0)
    net.add_edge(src, a, R1)
    net.add_edge(a, gnd, R2)
    net.add_edge(a, gnd, R3)
    P = net.solve()
    Rpar = 1.0 / (1.0 / R2 + 1.0 / R3)
    expected = P_in * Rpar / (R1 + Rpar)
    return {"P_A_solver": P[a], "P_A_exact": expected,
            "abs_err": abs(P[a] - expected)}


# ---------------------------------------------------------------------------
# COMB manifold builder:  P_in -> spine(M taps) -> arm(n rungs each) -> ground
# ---------------------------------------------------------------------------
def build_comb(M: int, n: int, *, R_rung: float, r_prim: float, r_arm: float):
    """Return (network, tap_nodes). M arms, n rungs/arm, total N=M*n rungs."""
    net = NodalNetwork()
    gnd = net.add_node(); net.fix(gnd, 0.0)
    head = net.add_node(); net.fix(head, 1.0)   # P_in = 1.0 (linear -> scale-free)

    prev_spine = head
    taps: list[int] = []
    for _ in range(M):
        s = net.add_node()
        net.add_edge(prev_spine, s, r_prim)      # primary segment
        prev_spine = s
        prev_arm = s
        for _k in range(n):
            a = net.add_node()
            net.add_edge(prev_arm, a, r_arm)     # arm segment
            net.add_edge(a, gnd, R_rung)         # the rung (drains to continuous)
            prev_arm = a
            taps.append(a)
    return net, np.array(taps, dtype=int)


def spread_pct(q: np.ndarray) -> float:
    """Flatness metric: (max-min)/mean * 100 %."""
    m = float(np.mean(q))
    return float((np.max(q) - np.min(q)) / m * 100.0) if m > 0 else float("inf")


def comb_metrics(M: int, n: int, *, R_rung, r_prim, r_arm) -> dict:
    net, taps = build_comb(M, n, R_rung=R_rung, r_prim=r_prim, r_arm=r_arm)
    P = net.solve()
    q = P[taps] / R_rung                          # rung flows (P_out=0)
    return {"M": M, "n": n, "N": M * n,
            "spread_pct": spread_pct(q),
            "throughput_rel": float(np.sum(q)),   # relative (P_in=1)
            "P_min_tap": float(np.min(P[taps])),
            "P_max_tap": float(np.max(P[taps]))}


# ---------------------------------------------------------------------------
# H-TREE: balanced binary distribution (symmetry -> perfectly flat)
# ---------------------------------------------------------------------------
def build_htree(depth: int, *, R_rung: float, r_edge: float):
    """Balanced binary tree, 2^depth leaf rungs. Every leaf is symmetric ->
    identical pressure -> spread == 0 (to machine precision)."""
    net = NodalNetwork()
    gnd = net.add_node(); net.fix(gnd, 0.0)
    root = net.add_node(); net.fix(root, 1.0)
    leaves: list[int] = []

    def grow(parent: int, level: int):
        if level == depth:
            net.add_edge(parent, gnd, R_rung)
            leaves.append(parent)
            return
        # edge resistance halves each level (space-filling H-tree lengths)
        Redge = r_edge / (2 ** level)
        for _ in range(2):
            child = net.add_node()
            net.add_edge(parent, child, Redge)
            grow(child, level + 1)

    grow(root, 0)
    return net, np.array(leaves, dtype=int)


# ===========================================================================
# MAIN
# ===========================================================================
def main() -> None:
    print("=== Anchor: series/parallel divider ===")
    anc = anchor_divider()
    print(f"  solver P_A = {anc['P_A_solver']:.6f} Pa")
    print(f"  exact  P_A = {anc['P_A_exact']:.6f} Pa")
    print(f"  abs err    = {anc['abs_err']:.2e}  ->  "
          f"{'PASS' if anc['abs_err'] < 1e-6 else 'FAIL'}")
    assert anc["abs_err"] < 1e-6, "solver anchor failed"

    # -- representative geometry (sunflower oil) ----------------------------
    pitch = 120e-6
    spacing = 220e-6                                   # arm-to-arm (arm width + wall)
    R_rung = R_rect(2.0e-3, 30e-6, 20e-6)             # rung: 2 mm x 30 x 20 µm
    r_arm = R_rect(pitch, 200e-6, 100e-6)             # arm segment: thin 200 x 100 µm
    r_prim_beefy = R_rect(spacing, 1000e-6, 200e-6)   # primary: deep+wide spine (free)
    r_prim_thin = R_rect(spacing, 200e-6, 100e-6)     # primary: same thin channel as arm

    lam_arm = math.sqrt(R_rung / r_arm)               # arm droop length [rungs]
    print(f"\nR_rung        = {R_rung:.3e} Pa·s/m³")
    print(f"r_arm/seg     = {r_arm:.3e}  ->  lambda_arm = sqrt(R_rung/r_arm) "
          f"= {lam_arm:.0f} rungs")
    print(f"r_prim beefy  = {r_prim_beefy:.3e}   r_prim thin = {r_prim_thin:.3e}")

    # -- 1. degenerate M=1 = single serpentine main -------------------------
    N_demo = 4000
    single = comb_metrics(1, N_demo, R_rung=R_rung, r_prim=r_prim_beefy, r_arm=r_arm)
    print(f"\n=== Degenerate check: M=1 (single main), N={N_demo} ===")
    print(f"  spread = {single['spread_pct']:.1f} %  "
          f"(P_min/P_max tap = {single['P_min_tap']:.3f}/{single['P_max_tap']:.3f})")
    net, taps = build_comb(1, N_demo, R_rung=R_rung, r_prim=r_prim_beefy, r_arm=r_arm)
    Psingle = net.solve()[taps]
    mono = bool(np.all(np.diff(Psingle) <= 1e-15))
    print(f"  monotonic droop head->tail (far end starved): {mono}")

    # -- 2. arms sweep at fixed N, two primary regimes ----------------------
    Ns = [1000, 4000, 10000]
    sweep_rows: list[dict] = []
    for N in Ns:
        # M over the divisors that keep n integer, log-ish spread
        Ms = sorted({m for m in
                     [1, 2, 4, 5, 8, 10, 16, 20, 25, 40, 50, 80, 100, 125, 160,
                      200, 250, 400, 500, 800, 1000, 2000]
                     if m <= N and N % m == 0})
        for regime, r_prim in [("beefy_primary", r_prim_beefy),
                               ("thin_primary", r_prim_thin)]:
            for M in Ms:
                row = comb_metrics(M, N // M, R_rung=R_rung,
                                   r_prim=r_prim, r_arm=r_arm)
                row["regime"] = regime
                row["lambda_arm"] = lam_arm
                sweep_rows.append(row)

    with open(RESULTS / "arms_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["regime", "N", "M", "n", "spread_pct",
                                          "throughput_rel", "lambda_arm"])
        w.writeheader()
        for r in sweep_rows:
            w.writerow({k: r[k] for k in w.fieldnames})

    # report the best M per (N, regime)
    print("\n=== Arms sweep: best M (min spread) per case ===")
    best_rows = []
    for N in Ns:
        for regime in ("beefy_primary", "thin_primary"):
            sub = [r for r in sweep_rows if r["N"] == N and r["regime"] == regime]
            best = min(sub, key=lambda r: r["spread_pct"])
            m1 = next(r for r in sub if r["M"] == 1)
            best_rows.append({"N": N, "regime": regime, "best_M": best["M"],
                              "best_n": best["n"], "best_spread_pct": best["spread_pct"],
                              "single_main_spread_pct": m1["spread_pct"],
                              "n_over_lambda_at_best": best["n"] / lam_arm})
            print(f"  N={N:5d} {regime:14s}: best M={best['M']:4d} "
                  f"(n={best['n']:4d}, n/lam={best['n']/lam_arm:.2f})  "
                  f"spread {best['spread_pct']:7.2f}%  "
                  f"(single main: {m1['spread_pct']:.1f}%)")

    with open(RESULTS / "best_arrangement.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(best_rows[0].keys()))
        w.writeheader()
        w.writerows(best_rows)

    # -- 3. H-tree structural bound -----------------------------------------
    print("\n=== H-tree (symmetric bifurcation) structural bound ===")
    htree_rows = []
    for depth in (6, 8, 10, 12):          # 64 .. 4096 leaves
        net, leaves = build_htree(depth, R_rung=R_rung, r_edge=r_arm * 8)
        P = net.solve()
        q = P[leaves] / R_rung
        s = spread_pct(q)
        htree_rows.append({"depth": depth, "N_leaves": len(leaves), "spread_pct": s})
        print(f"  depth={depth:2d}  N={len(leaves):5d} leaves  spread = {s:.2e} %")
    with open(RESULTS / "htree.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["depth", "N_leaves", "spread_pct"])
        w.writeheader(); w.writerows(htree_rows)

    # -- 4. area + no-crossing geometry -------------------------------------
    print("\n=== Area / no-crossing geometry (N=10000) ===")
    geo = geometry_check(N=10000, best_rows=best_rows, pitch=pitch, spacing=spacing)
    with open(RESULTS / "geometry.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(geo[0].keys()))
        w.writeheader(); w.writerows(geo)
    for g in geo:
        print(f"  {g['structure']:16s} area {g['area_cm2']:6.2f} cm²  "
              f"no_crossing_planar={g['no_crossing_planar']}  ({g['note']})")

    make_figures(sweep_rows, Ns, lam_arm, Psingle, htree_rows)
    print("\nWrote results/*.csv and figures/*.png")


def geometry_check(*, N, best_rows, pitch, spacing) -> list[dict]:
    """Rough footprint + planar no-crossing verdict for each structure."""
    rows = []
    # single serpentine main: one lane, length N*pitch, folded to square (as deep_dfu)
    L_main = N * pitch
    band = 2 * 1000e-6 + 2.0e-3         # 2*Mcw + rung span (deep_dfu band model)
    area_single = L_main * band * 1e4    # m² -> cm²
    rows.append({"structure": "serpentine (M=1)", "area_cm2": area_single,
                 "no_crossing_planar": True,
                 "note": "single folded pair; continuous drains alongside — planar"})
    # comb: M arms (fingers) each n*pitch long, spaced by `spacing`; continuous
    # drains in the gaps between fingers (interdigitated comb) — planar.
    best = next(r for r in best_rows
                if r["N"] == N and r["regime"] == "beefy_primary")
    M, n = best["best_M"], best["best_n"]
    arm_len = n * pitch
    comb_w = M * spacing
    comb_area = arm_len * comb_w * 1e4
    rows.append({"structure": f"comb (M={M})", "area_cm2": comb_area,
                 "no_crossing_planar": True,
                 "note": "open fingers; continuous drains in inter-arm gaps — planar"})
    # H-tree: space-filling binary tree PARTITIONS the plane; continuous must
    # reach interior leaves, crossing oil edges -> NOT planar-drainable single-layer.
    rows.append({"structure": "H-tree", "area_cm2": comb_area,
                 "no_crossing_planar": False,
                 "note": "tree encloses regions; continuous cannot drain interior "
                         "leaves without crossing oil — needs 2nd layer"})
    return rows


def make_figures(sweep_rows, Ns, lam_arm, Psingle, htree_rows) -> None:
    # Fig 1: spread vs M, both primary regimes, per N
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, regime, title in [
        (axes[0], "beefy_primary", "Beefy primary (deep+wide spine)"),
        (axes[1], "thin_primary", "Thin primary (= arm channel)")]:
        for N in Ns:
            sub = sorted([r for r in sweep_rows
                          if r["N"] == N and r["regime"] == regime],
                         key=lambda r: r["M"])
            ax.loglog([r["M"] for r in sub], [max(r["spread_pct"], 1e-6) for r in sub],
                      marker="o", ms=3, label=f"N={N}")
        # mark the threshold M = N/lambda_arm for each N
        for N in Ns:
            ax.axvline(N / lam_arm, ls=":", lw=0.8, color="grey", alpha=0.5)
        ax.set_title(title)
        ax.set_xlabel("number of arms  M")
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("ΔP spread across all rungs  [%]")
    fig.suptitle("Manifold flatness vs number of arms  (dotted = M = N/λ_arm threshold)")
    fig.tight_layout()
    fig.savefig(FIGS / "spread_vs_arms.png", dpi=130)
    plt.close(fig)

    # Fig 2: pressure profile single main vs a good comb (N=4000, beefy)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(np.linspace(0, 1, len(Psingle)), Psingle, lw=1.6,
            label="single main (M=1): far end starved")
    # rebuild a good comb for the same N to overlay tap pressures
    from math import isclose
    net, taps = build_comb(40, 100, R_rung=R_rect(2e-3, 30e-6, 20e-6),
                           r_prim=R_rect(220e-6, 1000e-6, 200e-6),
                           r_arm=R_rect(120e-6, 200e-6, 100e-6))
    Pcomb = net.solve()[taps]
    ax.plot(np.linspace(0, 1, len(Pcomb)), Pcomb, lw=1.6,
            label="comb M=40, n=100: flat across all rungs")
    ax.set_xlabel("rung index (normalised, head → tail)")
    ax.set_ylabel("tap pressure = rung ΔP  (P_in = 1)")
    ax.set_title("Why a manifold is flat: two short droops instead of one long one  (N=4000)")
    ax.grid(True, alpha=0.3); ax.legend()
    fig.tight_layout(); fig.savefig(FIGS / "pressure_profile.png", dpi=130)
    plt.close(fig)

    # Fig 3: structure comparison bar (flatness, log)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    sub = [r for r in sweep_rows if r["N"] == 4000 and r["regime"] == "beefy_primary"]
    single = next(r for r in sub if r["M"] == 1)["spread_pct"]
    best = min(sub, key=lambda r: r["spread_pct"])["spread_pct"]
    htree = max(htree_rows, key=lambda r: r["N_leaves"])["spread_pct"]
    labels = ["serpentine\n(single main)", "comb manifold\n(best M)", "H-tree\n(symmetric)"]
    vals = [max(single, 1e-9), max(best, 1e-9), max(htree, 1e-9)]
    colors = ["#c44", "#4a4", "#48c"]
    bars = ax.bar(labels, vals, color=colors)
    ax.set_yscale("log"); ax.set_ylabel("ΔP spread  [%]  (log)")
    ax.set_title("Flatness by structure (N≈4000). H-tree is flattest but NOT planar-drainable.")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v, f"{v:.1e}%", ha="center",
                va="bottom", fontsize=9)
    ax.text(2, htree * 5, "planar\nno-crossing: ✗", ha="center", color="#48c", fontsize=9)
    fig.tight_layout(); fig.savefig(FIGS / "structure_comparison.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
