# Workspace Brief: Large-DFU Stage-1 Hydraulic Screen

**Created**: 2026-07-06
**Status**: active
**Study type**: computational

## Research question

Can a ladder of large/deep O/W DFUs (20–50 µm deep, 0.5–4 mm long, 10–1000 rungs)
hydraulically refill (Stage 1) fast enough — t_S1 ≤ 1 s for **every** DFU — at a
practical drive pressure (ideal ≤ 500 mbar, hard ceiling 1000 mbar)?

## Background

Larger, deeper DFUs are a design direction for higher per-DFU throughput, but the
Stage-Wise V3 model is calibrated on 10–30 µm scale devices (e.g. V5-30). Before
investing in Stage-2/cyclic modeling for large DFUs, we want a cheap first-pass
hydraulic screen: if a candidate can't even refill fast enough, no snap-off model
will save it. This is a **two-layer screening strategy**: Stage-1 hydraulics now
(this workspace); Stage-2/cyclic snap-off deferred to a follow-up workspace for
whichever candidates survive.

## Approach

Simplified Stage-1 relation, not the full `stage_wise_v3` model:

```
t_S1    = V_reset * R_DFU / DP_eff
V_reset = sqrt(exit_width * exit_depth) * exit_width * exit_depth
DP_eff  = DP_DFU - 12 mbar     (fitted Stage-1 capillary back-pressure)
pass:   DP_eff > 0 and t_S1 <= 1 s for EVERY DFU in the ladder
```

- Model components: `stepgen.models.hydraulics.simulate` (plain steady-state
  mixed-BC ladder solve) for per-rung `DP_DFU = P_oil − P_water`;
  `stepgen.models.resistance.resistance_piecewise` for the scalar `R_DFU` from
  the 90:10 two-section DFU profile. DeviceConfigs are built directly in Python
  per candidate. No changes to core stepgen.
- Analysis method: 576-candidate grid (`N_DFU` × `DFU_depth` × `DFU_length` ×
  `upstream_AR` × `main_depth`) × 20 pressures (50–1000 mbar in 50 mbar steps),
  fixed Qw = 5 mL/hr water. See `study_config.yaml` for the full grid and rules.

### Assumptions (mirrored from the study spec)

1. **Instantaneous droplet formation** — Stage 2 / cyclic snap-off is not
   modeled; this screen is Stage-1 refill only.
2. **Flat 12 mbar capillary back-pressure** — a fitted constant; a Laplace
   estimate `gamma·cos(θ)·(1/depth + 1/exit_width)` (θ = 30°) is computed as a
   diagnostic only and never substituted for the constant.
3. **Piecewise-profile-only resistance** — `R_DFU` comes from the 2-section
   90:10 profile via `resistance_piecewise`; `mcd/mcw/mcl/constriction_ratio`
   are placeholders ignored when the profile is non-empty.
4. **`V_reset = sqrt(w·h)·w·h` taken as given** — the reset length scale
   `sqrt(w·h)` is checked once against the V5-30 observation (see below), not
   re-derived.
5. **No transient feedback** — one static steady-state solve per (candidate,
   pressure); no coupling between refill and the network state over a cycle.
6. **Fixed Qw = 5 mL/hr** (continuous/water phase) for the main sweep; a
   bounded Qw-sensitivity check tests the impact of adjusting Qw to a target
   emulsion fraction for 3 representative candidates.
7. **`main.Mcl` is inert** — `Nmc_override = N_DFU` fixes the rung count
   directly, so the routed main-channel length never affects the solve.
8. **Other DeviceConfig fields at dataclass defaults** — `footprint`,
   `manufacturing`, `droplet_model`, `operating_map`, `stage_wise`,
   `stage_wise_v3` are not read by the static Stage-1-only solve.
9. **"All rungs must pass" criterion** — the worst rung governs: every DFU
   needs `DP_eff > 0` and `t_S1 ≤ 1 s`.
10. **±50 mbar grid resolution** — `min_passing_pressure_mbar` is resolved
    only to the 50 mbar sweep step.

Manufacturing feasibility (max main depth; optional delamination line-load
limit) is computed as **diagnostic columns with tunable settings** in
`study_config.yaml` — never as row exclusion — because the exact limits are
not settled.

## Data sources

None — computational (model-only) workspace. No experimental data; no `data/`
folder by design.

## Success criteria

- The sweep runs end-to-end and produces `candidate_summary.csv`,
  `per_pressure_long.csv`, `results_summary.md`, and 5 figures.
- We can state, per (N_DFU, depth, length, AR, main_depth) region of the grid,
  the minimum drive pressure for a full-ladder Stage-1 pass — or that none
  exists ≤ 1000 mbar.
- Physics sanity holds: required pressure non-increasing in depth,
  non-decreasing in length and N_DFU (verification checks in
  `results/results_summary.md`).
- A short-list of candidates worth Stage-2/cyclic follow-up exists (or the
  design direction is ruled out on hydraulics alone).

## Current status

First full sweep run and report written 2026-07-06 (see
`snapshots/run_manifest.md`, `results/results_summary.md`, `report.md`).
Awaiting decision on the Stage-2/cyclic follow-up short-list and on the
main-channel manufacturability question.

## Key findings

- Stage-1 refill is **not** the bottleneck for N_DFU ≤ 100: all 384 such
  candidates pass at the lowest swept pressure band (≈50 mbar).
- At N_DFU = 1000, 135/192 pass at 500 mbar; all 46 never-passing candidates
  (≤1000 mbar) are N = 1000, concentrated at 40–50 µm depth.
- The single-DFU intuition (deeper → less pressure) is **reversed** at large N
  (Spearman rho = +0.71 at N = 1000): deep DFUs have ~40× lower R_DFU, draw
  more oil, and collapse DP_eff at far rungs via main-channel loading. The
  worst rung governs. Longer DFUs mildly help at large N for the same reason.
- Main-channel depth is the design lever at N = 1000 (passes at 500 mbar:
  29/48/58 of 64 for 200/300/400 µm mains) — colliding with the current
  200 µm manufacturing limit. 362 of 519 Stage-1 passes fail that check.
- Flat 12 mbar back-pressure is conservative vs the Laplace diagnostic
  (8.7 → 3.5 mbar over 20 → 50 µm depth) across the whole grid.
- Qw-sensitivity hypothesis confirmed: retuning Qw to a 10% emulsion target
  changes worst-rung t_S1 by ≤3% (N = 1000) and <0.2% (N ≤ 100).

## Consistency checks

<!-- Each time a repeat run is added, append an entry here. Do not overwrite previous findings. -->

## Cross-workspace links

- Follow-up (planned, not yet created): Stage-2/cyclic snap-off workspace for
  candidates surviving this screen.

## Open questions

- Should a Stage-2/cyclic snap-off study follow for the passing candidates,
  and which short-list should it use?
- Does the flat 12 mbar Stage-1 back-pressure constant hold across the full
  20–50 µm depth range? The diagnostic Laplace estimate
  `gamma·cos(θ)·(1/depth + 1/exit_width)` scales as ~1/depth and is compared
  per candidate in `candidate_summary.csv` (`P_cap_laplace_mbar`).
- V5-30 reset-length residual: `sqrt(30×10) = 17.3 µm` vs the observed
  19–21 µm lab range — a ~15% gap. Acceptable for a screen, but worth
  revisiting if `V_reset` becomes load-bearing in a Stage-2 follow-up.
