# Workspace Brief: Comp Oil Viscosity

**Created**: 2026-08-05
**Status**: complete
**Study type**: computational (re-analysis of existing experimental data)

## Research question

With the rung resistance exact (W2-1), what oil viscosity does the V5-8-1 sweep
imply — and is it **one number**, or does it move with the operating condition?

The distinction is the whole point. A viscosity is a material property: one value
per fluid per temperature. If the number the data implies changes with the water
flow rate, it is not a viscosity, it is a fitted correction with a physical name
on it.

## Background

W2-1 replaced four disagreeing rectangular-duct resistances with one, correctly
normalised. On V5-30 the rung resistance falls to 0.65×, so the model delivers
~1.5× more oil at the same pressure. The previous agreement with experiment rested
on two errors cancelling; one is now gone.

`C_visc` (a global multiplier on ΔP/R) would hide the difference. **Conor ruled
2026-08-05 that it must not be used** — a constant that multiplies ΔP/R at fixed
geometry *is* a viscosity and must be recorded as one. The design-studio plan
proposed µ = 83 cP as the replacement, fitted at one condition and explicitly
flagged as "a fit, not a measurement". This workspace tests it against the rest of
the dataset.

## Approach

- Model components: `stepgen.models.resistance` (W2-1), `stage_wise_v3.stage1_physics`,
  the serpentine ladder solve via `design.sweep.evaluate_candidate`
- Analysis method: fit `fluids.mu_dispersed` — one parameter, nothing else touched —
  to minimise RMS log-error in droplet frequency, **independently at each Qw**, then
  pooled. Split the measured cycle at the stage boundary to locate the residual.

## Data sources

| ID | Device | Date | Conditions | File | Notes |
|----|--------|------|------------|------|-------|
| `@exp-2026-04-24-v5-8-1` | V5-8-1 (V5-30 geometry) | 2026-04-24 | Po 200–600 mbar × Qw 5/10/20 mL/hr, 2% SDS / sunflower oil | `po_sweep/data/stage_timings.csv` | **primary workspace is `po_sweep/`** — no copy held here; 158 of 278 rows used. See `data/data_sources.md` |

## Success criteria

Either a single µ reproduces the data across every condition to within the
measurement's own noise floor — in which case it is a viscosity and can be
adopted — or it does not, in which case the residual must be named and located
rather than absorbed.

## Current status

Complete. The second branch is what happened.

## Key findings

1. **The implied µ is not one number**: 69 cP at Qw = 5, 81 at Qw = 10, 96 at
   Qw = 20. Each per-Qw fit is good (<15%); pooling all three degrades to 39%.
   A viscosity that rises 39% as the water flow quadruples is not a viscosity.
2. **The plan's 83 cP is the Qw = 10 slice** of that surface. It is `C_visc`
   under a physical name and has **not** been adopted.
3. **µ stays at 60 cP** — the literature value for sunflower oil, unchanged and
   unfitted. Nothing in the model was tuned by this study.
4. **Stage 1 agrees at 60 cP without any correction term**: −14.5% → +0.9% across
   200–600 mbar at Qw = 5, improving with pressure. Stage 1 is the only stage the
   resistance and viscosity control, so this is W2-1's actual result.
5. **The residual is in Stage 2+3** and grows with both Po and Qw. The model
   under-responds to Qw by ~3× (real device loses 28% of production from
   Qw 5→10 at 200 mbar; model loses 5.5%). At 600 mbar the measurement is also
   resolution-limited — Stage 2+3 is 6 frames at 50 fps.
6. **Noise floor ~15%**: the sweep's two independent measures of Q (conservation
   vs meniscus sweep) disagree with each other by 16–26%. That gap is not noise —
   meniscus Q is flow *during Stage 1*, conservation Q is the *cycle average*, and
   flow is not constant through the cycle.
7. **At Qw = 5 the model's flow is inside that band at every pressure** (4 of 4;
   +10 to +17% on conservation, −5 to −8% on meniscus). The model carries one Q,
   and between the two estimates is exactly where it should sit. It steps outside
   only at higher Qw, worst at low Po — Qw = 10 @ 200 mbar and Qw = 20 @ 300 mbar.

**Conor's call, 2026-08-05**: this is close enough. Stage 1 is the rate-limiting
step and it is the stage the resistance and viscosity govern; Stage 2+3 modelled as
a continuation of the same flow is not expected to match, because the growth phase
is mechanistically something else. Accepted as-is — no further fitting.
*One correction to the reasoning, recorded because it points the next investigation:
measured Stage 2+3 is LONGER than `V_drop/Q`, so growth is slower than
flow-continuation predicts, not faster. Whatever the mechanism is, it adds time.*

## Consistency checks

<!-- Each time a repeat run is added, append an entry here. Do not overwrite previous findings. -->

| Date | What was repeated | Result vs original | Notes |
|----|---|---|---|
| 2026-08-05 | the plan's single-condition µ fit, extended to Qw = 5 and 20 | **does not reproduce**: 69 / 81 / 96 cP | this is the finding, not a discrepancy to reconcile |

## Cross-workspace links

- `po_sweep/` — primary workspace for `@exp-2026-04-24-v5-8-1`; holds the file
- `qw_sweep/` — same dataset, asks the Qw question directly; independently found
  "Stage 2 is NOT Qw-independent", which is this workspace's residual seen from
  the other side
- `conc_sweep/`, `Po_Qw_conc_combined/` — same dataset, [SDS] and synthesis

## Open questions

1. **The oil has never been measured.** One viscometer reading at test temperature
   settles the whole argument. Top priority.
2. **Temperature is not recorded** in `stage_timings.csv`. ±5 °C is a ±30%
   viscosity swing — larger than anything argued about here.
3. **Why does the model under-respond to Qw by 3×?** Water-side resistance,
   dispersed-phase loading of the water main (an explicitly deferred v3 feature),
   or the Stage-2 growth model. This is the next physics change, not a constant.
4. **Is Stage 2+3 flattening at high Po physical or a 50 fps artefact?** Studio
   plan open question 2; needs a re-shoot, not more modelling.
5. Does the Qw-dependence of the implied µ reproduce on a second device? Only
   V5-8-1 was available.
