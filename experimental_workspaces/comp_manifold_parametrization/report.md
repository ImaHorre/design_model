# Manifold (comb) parametrization — is there an always-best arrangement?

**Computational · oil-distribution model · commit `d733f92` · sunflower oil (µ = 0.06 Pa·s)**
**Phase-3 GATE deliverable: pins the parametrization before the solver is built.**

## Question

The `manifold` family = a primary oil main (spine) feeding **M arms**, each arm a sub-ladder of
**n rungs**, total **N = M·n** DFUs. Before building the package nodal solver, pin the
parametrization by answering: at fixed N, across arms × rungs-per-arm × channel sizing, subject
to the hard **no-crossing** constraint — **is there an always-best arrangement?**

## Answer in one line

**No single (M, n) is universally best — flatness is a V-curve with an interior optimum — but
there is an always-best RULE: use a beefy (deep+wide) primary and choose the number of arms M so
each arm is about one "droop length" long, `n ≈ λ_arm = √(R_rung / r_arm)`.** That comb beats a
single serpentine main by **1–2 orders of magnitude** in ΔP flatness at the same N. The perfectly
flat H-tree is flatter still but is **not planar-manufacturable** (fails no-crossing), so the
**comb is the buildable optimum**.

## Why there's an optimum (two droops, not one)

A single serpentine main has **one long droop**: pressure falls along the main and the far rungs
starve (our degenerate M=1 check: **spread 3111 %** at N=4000, monotone head→tail — the
`comp_deep_dfu_v5_main_mods` starvation, reproduced). A comb replaces that with **two short
droops**:

- **arm droop** — within each arm, over n rungs; grows with n.
- **spine droop** — along the primary, over M taps; grows with M.

For fixed N = M·n these trade off, giving the V-curves in `figures/spread_vs_arms.png`. The
governing length is the **arm droop length** `λ_arm = √(R_rung / r_arm)` (here **128 rungs**):
an arm stays flat while `n ≲ λ_arm`. The best arrangement sits where the arms are just short
enough, balanced against not having so many arms that the spine itself droops.

| N | primary | best M | best n | n / λ_arm | best spread | single-main spread |
|---|---|---|---|---|---|---|
| 1 000 | beefy | 40 | 25 | 0.20 | **6 %** | 777 % |
| 4 000 | beefy | 50 | 80 | 0.62 | **38 %** | 3 111 % |
| 10 000 | beefy | 80 | 125 | 0.98 | **113 %** | 7 777 % |
| 1 000 | thin | 10 | 100 | 0.78 | 71 % | 777 % |
| 4 000 | thin | 16 | 250 | 1.95 | 343 % | 3 111 % |
| 10 000 | thin | 25 | 400 | 3.12 | 873 % | 7 777 % |

Two rules fall straight out of the table:

1. **The optimum arm length is order λ_arm.** Best-n is always ≤ λ_arm (25, 80, 125 ≤ 128) with a
   beefy primary, approaching it as N grows. So: **pick M ≈ N / λ_arm** and refine on the curve.
2. **Primary sizing dominates the depth of the basin.** A **beefy primary** (deep+wide — the
   "free" lever from `[[comp_deep_dfu_v5_main_mods]]`: depth costs no in-plane area) reaches
   ~5–10× flatter optima than a **thin** primary (same channel as the arms). The naive
   "one channel size everywhere" manifold is far worse and forced to fewer, longer arms.

So "always-best arrangement" is the wrong shape of question — there is no universal point. The
**robust, portable rule** is: *beefy primary + `n ≈ λ_arm` per arm.*

## The no-crossing constraint decides the structure (not just the numbers)

The **H-tree** (symmetric binary bifurcation) is the flatness bound: every leaf is geometrically
identical, so all rung pressures are equal → **spread ≈ 0** (we measure ~1e-12 %, machine zero,
at every depth 64–4096 leaves — `results/htree.csv`). It looks like the obvious winner.

**But it fails the hard no-crossing gate.** A space-filling tree *partitions the plane*; the
continuous phase cannot reach the interior leaf exits to carry droplets away without **crossing
the oil tree**. In a single planar etch that is not manufacturable (it needs a second layer /
bridge). The **comb** does not partition the plane — its arms are **open fingers**, and the
continuous phase drains in the **inter-arm gaps** (interdigitated). It is planar by construction.

| structure | flatness | area (N=10k) | no-crossing planar? | verdict |
|---|---|---|---|---|
| serpentine (M=1) | worst (7 777 %) | ~48 cm² | ✅ | the thing we're improving on |
| **comb (best M)** | **113 %** | **~2.6 cm²** | ✅ | **buildable optimum** |
| H-tree | ~0 % | ~2.6 cm² | ❌ (encloses regions) | flatness bound only; needs 2nd layer |

(Areas are order-of-magnitude only — see caveats. The comb is markedly more compact than the
single folded main because arms are parallel fingers, not one 1.2 m serpentine.)

## Pinned parametrization (the Phase-3 deliverable)

**Topology = comb / tapped-ladder** (parallel arms off a straight beefy primary; continuous
drains in the gaps). The study geometry block for the `manifold` family:

```yaml
manifold:
  main:  { depth_um, width_um }                         # PRIMARY spine — keep deep+wide
  arms:  { count: M, spacing_um, depth_um, width_um }   # M open fingers
  rungs_per_arm: n                                      # N_dfu = M * n
  junction: { exit_width_um, exit_depth_um, pitch_um }  # same exit as serpentine/radial
```

Derived: `arm_length = n·pitch`, `N_dfu = M·n`, `λ_arm = √(R_rung/r_arm)`.

**Nodal-graph assembly recipe** (validated here; hand to `stepgen/models/nodal_network.py`):

- ground node fixed at `P_out`; spine-head node fixed at `P_in` (oil, pressure-BC).
- spine = chain of **M** nodes joined by primary segments `r_prim = R_rect(spacing, W_prim, H_prim)`.
- each spine node → an arm = chain of **n** nodes joined by arm segments
  `r_arm = R_rect(pitch, W_arm, H_arm)`.
- each arm node → ground through the rung `R_rung` (drains to the shared continuous reference).
- solve the sparse Laplacian with the two Dirichlet nodes; rung flow `q_i = (P_i − P_out)/R_rung`;
  `uniformity_pct` = spread of `q_i`. This is the exact prototype in `analysis.py::NodalNetwork`
  (anchored to an exact series/parallel divider, abs err 0).

**Gates for the family** (`applicable_metrics`): `throughput_mlhr`, `uniformity_pct`,
`operating_Po_mbar`, `regime_Ca` (exit — same as serpentine), and **`build` with a real
`no_crossing` check**: comb passes when the inter-arm gap `≥ min_feature` and arms are open
(not enclosing); a tree-like routing fails. Droplet size/frequency reuse the same regime-blind
power-law as the other families (unchanged; flagged for deep exits).

## Recommendation for the solver/family build (next Phase-3 step)

1. Implement `nodal_network.py` as the general sparse-Laplacian solver above (the `NodalNetwork`
   prototype here is the reference; it also subsumes the serpentine ladder as M=1 for cross-check).
2. Implement `manifold` family emitting the comb graph; default the primary deep+wide.
3. Auto-suggest `M ≈ N/λ_arm` (or expose M as the swept axis and let the scored table find the
   V-curve minimum — the Studio already sweeps and scores).
4. `no_crossing` gate = comb open-finger check; **reject tree routings**.

## Caveats

- **Oil-distribution model only.** Rungs drain to a *shared* continuous reference (P_out = 0) —
  the simplified-Poiseuille view the live model uses. It has **no water main and no reverse-flow**
  (unlike the full ladder in `stepgen/models/hydraulics.py`), so the **absolute** spread %s here
  are not the full-model numbers — the *shape of the answer* (V-curve, interior optimum, λ_arm
  rule, comb ≫ single main, H-tree infeasible) is the robust result, not the exact percentages.
  The package family will run the real ladder physics per rung.
- **Droplet size is regime-blind** (inherited power-law, ~2× extrapolation for deep exits) — so
  drop *frequency* is indicative; oil *throughput/velocity* are the solid outputs
  (`[[droplet-model-regime-blind]]`).
- **Areas are order-of-magnitude**: single-main uses the deep_dfu `band = 2·Mcw + rung` fold
  model; the comb uses `arms × spacing × arm_length`. Different packing models — read the ratio,
  not the absolute cm².
- Representative geometry (rung 2 mm×30×20 µm; arm 200×100 µm; primary 1000×200 µm; N up to 10k).
  λ_arm and the optimum shift with geometry, but the **rule** `n ≈ λ_arm` is scale-free in
  `R_rung/r_arm`.
- No experimental data — this is a design-definition (parametrization) study.

## Data provenance

- **Model commit**: `d733f92` · **manifest**: `snapshots/run_manifest.md`.
- Fluid: sunflower oil, µ = 0.06 Pa·s (dispersed). Continuous phase enters only as the shared
  drain reference (open-collection assumption).
- Analysis: `analysis.py` (self-contained; prototype `NodalNetwork` solver + sweeps).
- Numbers: `results/arms_sweep.csv`, `results/best_arrangement.csv`, `results/htree.csv`,
  `results/geometry.csv`.
- Figures: `figures/spread_vs_arms.png` (V-curves, both primary regimes) ← `arms_sweep.csv`;
  `figures/pressure_profile.png` (single-main vs comb tap pressures, N=4000);
  `figures/structure_comparison.png` (serpentine vs comb vs H-tree flatness) ← the three CSVs.
