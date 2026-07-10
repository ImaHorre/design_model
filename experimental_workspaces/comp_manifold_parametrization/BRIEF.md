# Workspace Brief: Manifold (Comb) Parametrization

**Created**: 2026-07-10
**Status**: active
**Study type**: computational

## Research question

The Design Studio's **third topology family is `manifold`**: a primary oil main that feeds
**secondary arms**, each arm feeding a **parallel array of DFU rungs** into the continuous
phase. Before we commit a general nodal-graph solver (`stepgen/models/nodal_network.py`) and
the `manifold` family to the package, Phase 3 of the Studio plan requires us to **pin the
parametrization** and answer one design question:

> Across `n_arms × rungs_per_arm × arm/primary geometry`, at fixed total DFU count **N**,
> **is there an always-best arrangement** for flatness (ΔP spread across all rungs) and area,
> subject to the hard **no-crossing** constraint (continuous phase must never cross dispersed)?

This is the "gate" step: *do not build the solver before the parametrization is pinned.*

## Background

The serpentine family (current V5) puts all N rungs on **one** oil main. Its weakness is the
axial pressure droop along that single main — the far rungs starve, so ΔP spread grows with N
(the `comp_deep_dfu_v5_main_mods` lesson: the real flatness driver is per-DFU oil draw versus
what the main can feed uniformly). A **manifold** splits the load: a short primary feeds M
arms, each a short sub-ladder of n = N/M rungs. Intuitively this can be flatter than one long
main — but a straight primary *also* droops across its M taps, so there are **two** droop
mechanisms trading off, and the best split is not obvious. Hence the sweep.

The **droplet physics is identical across all three families** — every family ends in the same
step-emulsification exit junction, so droplet size/regime (step-emulsification, Ca-independent
size — `wiki/devices/step-emulsifier`, `@chakraborty2017`, `@montessori2020`) carries over
unchanged. What the manifold changes is purely the **oil-distribution hydraulics** upstream of
the exits, which the DMF wiki does not cover (it is a flow-network question, not a droplet-
physics one). So this workspace is grounded in hydraulic-network theory, not the wiki.

## Parametrization (proposed — to be pinned by this workspace)

Comb / tapped-ladder manifold. The study geometry block:

```yaml
manifold:
  main:  { depth_um, width_um }                 # PRIMARY main (the spine)
  arms:  { count: M, spacing_um, depth_um, width_um }   # M parallel arms off the spine
  rungs_per_arm: n                              # so total N_dfu = M * n
  junction: { exit_width_um, exit_depth_um, pitch_um }  # same exit as serpentine/radial
```

Derived: `arm_length = n * pitch`; `N_dfu = M * n`. The nodal graph (the recipe the package
solver must assemble):

- **Primary spine**: source pressure `P_in` at the head; a chain of `M` branch nodes joined by
  primary segments of resistance `r_prim` (per `spacing_um`).
- **Arm**: each branch node feeds an arm = a chain of `n` rung-tap nodes joined by arm segments
  of resistance `r_arm` (per `pitch_um`).
- **Rung**: each tap node connects to the continuous-phase reference (`P_out`) through the rung
  resistance `R_rung`. (Oil-distribution model: exits share a low-resistance collection — the
  simplified-Poiseuille view used by the live model — so the graph is a **tree to ground**.)

## Approach

- **Model components**: a small **self-contained prototype nodal solver** in `analysis.py`
  (sparse Laplacian assembly + Dirichlet BCs). This is *throwaway exploration code that
  prototypes the eventual `nodal_network.py` assembly* — building it here, against a validated
  anchor, is exactly what the gate is for. Resistances use the same rectangular-channel formula
  as `stepgen/models/resistance.py` (`12 µL / (w h³ · corr)`).
- **Analysis method**:
  1. **Anchor** the solver on a hand-computable network (series/parallel divider) — exact.
  2. **Degenerate check**: comb at M=1 reproduces the single-main serpentine droop (monotone
     starvation of the far end).
  3. **Sweep arms M** (n = N/M) at fixed N, for several **draw regimes** (fat/lean rung draw),
     → ΔP spread vs M. Locate the optimum and test whether it is universal.
  4. **Structure comparison**: single main (serpentine) vs optimal comb vs symmetric **H-tree**
     (the theoretical flatness bound by symmetry).
  5. **No-crossing + area geometry**: which structures are planar-drainable (comb) vs not
     (enclosing H-tree), and the inter-arm gap / area feasibility gate.

## Data sources

None — computational only (model-only exploration).

| ID | Device | Date | Conditions | File | Notes |
|----|--------|------|------------|------|-------|
| — | — | — | model-only sweep | — | no experimental data |

## Success criteria

1. The prototype nodal solver passes the exact divider anchor and reproduces single-main droop.
2. The arms-sweep produces a clear spread-vs-M curve; we can state whether the optimum is
   universal or draw-dependent (and give the rule).
3. The no-crossing question is settled: which manifold structure is planar-manufacturable.
4. A **pinned parametrization** + a **nodal-graph assembly recipe** ready to hand to the
   package solver / family build (the next Phase 3 step).

## Current status

**Analysis complete — parametrization pinned.** See `report.md`. Prototype nodal solver anchored
(exact divider, abs err 0). Ready to hand off to the package solver/family build (next Phase-3 step).

## Key findings

- **No single always-best (M, n)** — flatness is a **V-curve** with an interior optimum that
  moves with N and channel sizing. The portable **rule** is: **beefy (deep+wide) primary + choose
  M so each arm ≈ `λ_arm = √(R_rung/r_arm)` rungs long** (here λ_arm = 128; `M ≈ N/λ_arm`).
- The comb beats a single serpentine main by **1–2 orders of magnitude** in ΔP spread at equal N
  (e.g. N=4000: 3111 % → 38 %). Primary sizing sets the depth of the basin (beefy ≫ thin).
- **H-tree** is the flatness bound (spread ≈ 0 by symmetry) but **fails no-crossing** (partitions
  the plane → continuous can't drain interior leaves single-layer). **Comb is the buildable optimum.**
- **Pinned topology = comb / tapped-ladder**; nodal-graph assembly recipe validated and documented
  in `report.md` for `stepgen/models/nodal_network.py` + `stepgen/families/manifold.py`.

## Cross-workspace links

- [[comp_deep_dfu_v5_main_mods]] — the single-main flatness/per-DFU-draw lesson this generalizes;
  also the source of the "depth is a free lever" rationale for the beefy primary.
- Feeds: Studio Phase 3 `stepgen/models/nodal_network.py` + `stepgen/families/manifold.py`.

## Open questions

- Absolute spread %s use an oil-distribution-only model (no water main / reverse flow). Re-confirm
  the optimum and the `n ≈ λ_arm` rule once the family runs the full ladder physics per rung.
- Tapered primary (widening toward the head) could flatten the spine droop further — untested;
  worth a follow-up once the comb family exists.
