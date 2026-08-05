# Wiki Ingest Handoff — comp_oil_viscosity

**Date**: 2026-08-05
**Workspace**: experimental_workspaces/comp_oil_viscosity/
**Device**: V5-8-1 (V5-30 geometry: 30 × 10 µm exit, 8 × 10 µm × 4.02 mm DFU, 200 × 1000 µm main)
**Citekey**: @ws-2026-08-05-comp-oil-viscosity
**Model commit**: `71be939`

> **Note for the ingest pass**: this is a *re-analysis* workspace. It measures nothing
> new — it re-asks an old dataset (`@ws-2026-07-13-po-sweep-v5-8-1`) a question that
> only became answerable once the rung resistance was correct. Its evidence layer is
> `[model-v3, 2026-08]` resting on `[experimental]` data already ingested.

## What was measured [experimental]

Nothing new. The source is the existing V5-8-1 sweep,
`experimental_workspaces/po_sweep/data/stage_timings.csv` — 158 of 278 rows, filtered
to `ContPhase == SDS` (2%) and `DispPhase == SO` (sunflower oil), across
Po = 200/300/400/600 mbar × Qw = 5/10/20 mL/hr.

Two facts about that dataset that were not previously stated and matter downstream:

1. **The file's only 800 mbar data is 2.5% sodium caseinate at Qw = 10** — a different
   continuous phase. Any claim spanning 200–800 mbar for the SDS system is mixing
   fluid systems. The SDS data stops at 600 mbar.
2. **Temperature is not recorded anywhere in the file.** Sunflower oil roughly doubles
   in viscosity between 30 °C and 15 °C, so any viscosity argument about this dataset
   is unfalsifiable without it. This should be recorded in future test sessions.

## What the model predicted [model-v3, 2026-08]

With the rung resistance replaced by the exact rectangular-duct solution (W2-1:
`R = fRe(α)·µL/(2·A·D_h²)`, dimensions ordered, integrated piecewise over the measured
two-width DFU), the rung resistance on V5-30 falls to **0.65×** its previous value —
9.981e17 Pa·s/m³ at µ = 60 cP.

At the config's declared condition (Qw = 5 mL/hr), µ = 60 cP, **no correction term
anywhere in the model**:

| Po (mbar) | t_S1 meas | t_S1 model | err | t_S2+3 meas | t_S2+3 model | err |
|---|---|---|---|---|---|---|
| 200 | 0.540 s | 0.462 s | −14.5% | 0.260 s | 0.267 s | +2.9% |
| 300 | 0.300 s | 0.271 s | −9.7% | 0.180 s | 0.157 s | −12.8% |
| 400 | 0.200 s | 0.192 s | −4.1% | 0.140 s | 0.111 s | −20.6% |
| 600 | 0.120 s | 0.121 s | +0.9% | 0.120 s | 0.070 s | −41.5% |

Per-DFU flow lands **inside** the two independent experimental estimates of Q at all
four Qw = 5 pressures (+10 to +17% on conservation, −5 to −8% on meniscus sweep).

## Divergences noticed during analysis

1. **A single fitted oil viscosity does not exist.** Fitting µ independently at each
   water flow rate gives **69 / 81 / 96 cP at Qw = 5 / 10 / 20** — each fit good to
   <15%, pooled 39%. A viscosity cannot depend on the water flow rate. **µ was left at
   the literature 60 cP and not fitted.**
2. **`C_visc` is deleted, not recalibrated.** Ruled by Conor 2026-08-05: a global
   multiplier on ΔP/R at fixed geometry *is* a viscosity and must be recorded as one.
   A config that sets `stage1_viscosity_correction` now raises.
   → **This closes `wiki/model/open-questions.md` item 1 ("C_visc calibration —
   status: uncalibrated"), which is wrong twice over: the parameter no longer exists,
   and calibrating it was never the right question.**
3. **The residual is in Stage 2+3, not Stage 1**, and grows with both Po and Qw. The
   model under-responds to Qw by ~3×: from Qw 5 → 10 at 200 mbar the real device loses
   28% of its production, the model 5.5%. `qw_sweep` reached the same conclusion from
   the other direction ("Stage 2 is NOT Qw-independent").
4. **A geometric error would be Qw-independent**; this is not. So the gap is neither
   viscosity nor geometry — it is the Stage-2 growth model and water-side loading.
5. **The two experimental Q estimates disagree by 16–26%, and that is physics, not
   noise.** Meniscus-sweep Q measures flow *during Stage 1*; conservation Q measures
   the *cycle average*; conservation is the lower of the two at every condition, by
   construction, because flow is not constant through the cycle. A model carrying one
   Q belongs between them.
6. **Measured Stage 2+3 is *longer* than V_drop/Q**, so droplet growth is **slower**
   than flow-continuation predicts, not faster. Whatever the growth mechanism is, it
   adds time. Part of the 600 mbar gap is the 50 fps floor (0.120 s = 6 frames).

**Conor's call, 2026-08-05**: this is close enough for the model's purpose. Stage 1 is
the rate-limiting step and the stage the resistance and viscosity govern; Stage 2+3
modelled as a continuation of the same flow is not expected to match, because growth is
mechanistically something else. Accepted as-is; no further fitting.

## Open questions surfaced

1. **The sunflower oil has never been on a viscometer.** One measurement at test
   temperature collapses the whole argument. Top priority, and cheap.
2. **Record temperature during testing.** ±5 °C is a ±30% viscosity swing — larger than
   any effect argued about in this workspace.
3. **Why does the model under-respond to Qw by ~3×?** Candidates: water-side channel
   resistance, dispersed-phase loading of the water main (an explicitly deferred v3
   feature), or the Stage-2 growth model. This is the next physics change — *not* a
   constant. **Suggested as a new open-questions item.**
4. **Is the Stage 2+3 flattening at high Po physical or a 50 fps artefact?** At 600 mbar
   the measured value is 6 frames and every entry in the column is a multiple of 0.02 s.
   Needs a high-speed re-shoot at 400–1000 mbar, not more modelling.
5. **Does the Qw-dependence of the implied µ reproduce on a second device?** Only
   V5-8-1 was available. `mfg050526_consistency` covers devices 1B/3D/4C but its data
   is not in this repository.

## Suggested wiki actions

- `wiki/model/open-questions.md` item 1 → **close**, superseded by this workspace.
  Replace with the Qw under-response (open question 3 above).
- `wiki/model/stage-wise-v3.md` → record that Stage 1 now agrees to −14.5%→+0.9% at
  Qw = 5 with **zero correction terms**, and that the rung resistance is the exact
  duct solution rather than a correlation.
- `wiki/experiments/@ws-2026-07-13-po-sweep-v5-8-1` → add the two dataset facts above
  (the 800 mbar rows are NaCas; no temperature recorded). Both affect how that page's
  derived exit-Ca figures should be read.
- Consider a `materials/` page for sunflower oil — viscosity vs temperature is now a
  load-bearing unknown in two workspaces.
