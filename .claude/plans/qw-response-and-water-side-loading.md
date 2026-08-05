# The Qw response — the model under-responds to water flow by ~5×

**Anchor**: `9b7012f` on `master`
**Baseline**: `pytest -q` → **636 passed, 0 failed, 5 skipped**. The known-failures list is
empty; if anything is failing when you start, you broke it or you are not at the anchor.
**Separate from** `.claude/plans/design-studio-filter-first-front-door.md` deliberately —
that plan is Studio *tooling* (only C and E remain). This is a **model physics** change.
They share only a consequence: every verdict the Studio prints inherits this error.
**Written 2026-08-05**, after section D closed, from a fresh measurement of the model
against `po_sweep/data/stage_timings.csv`.

---

## Where this stands — read this first

| | State |
|---|---|
| **Diagnosis** | ✅ measured, below. Not started on any fix |
| **Q1 — locate the deficit** | not started |
| **Q2 — the water main is pure water** | not started |
| **Q3 — decide the mechanism** | not started, **blocked on Q1+Q2** |
| **Q4 — re-validate + exit criteria** | not started |

**Start at Q1.** Do not start Q3 before Q1 and Q2 have both reported — Q3 is where the
tempting wrong answer lives, and it is only safe once the shape of the deficit is pinned.

---

## The finding

Measured 2026-08-05 against `experimental_workspaces/po_sweep/data/stage_timings.csv`
(V5-8-1, 2% SDS / sunflower oil, medians per condition, n = 11–23), model at `9b7012f`
with `configs/v5_30.yaml` unchanged.

**Response to doubling Qw from 5 to 10 mL/hr:**

```
            ── measured ──          ── model ──        deficit
 Po      Δt_S1   Δt_S2    Δf      Δt_S1     Δf         on Δf
200     +22.2%  +44.4%  -28.1%    +5.8%   -5.5%         5.1x
300     +16.7%  +30.0%  -16.1%    +3.4%   -3.2%         5.0x
400     +20.0%  +25.0%  -17.1%    +2.3%   -2.3%         7.4x
600     +16.7%    0.0%   -7.7%    +1.4%   -1.4%         5.5x
```

Two things in that table matter more than the headline, and **neither is in any existing
workspace report**:

### 1. The deficit is a roughly constant ~5×, not a growing one

`comp_oil_viscosity` reported it as "~3×" from a single condition (200 mbar). Across all
four pressures it is **5.0 / 5.1 / 5.5 / 7.4** — flat within the scatter. That is a
better-behaved error than a drifting one and it narrows the search: whatever is missing
scales with the same things the model already scales with, it is simply **too small**.

### 2. But the *shape in Po* is wrong, and that is the discriminating signature

Look at the Stage-1 columns alone:

```
measured Δt_S1 vs Po:   +22.2  +16.7  +20.0  +16.7 %   → FLAT in Po (~19%, mildly declining)
model    Δt_S1 vs Po:    +5.8   +3.4   +2.3   +1.4 %   → DECAYS 4x across the same span
```

**The real device's Stage-1 sensitivity to water flow barely cares about drive pressure.
The model's falls off a cliff.** So this is not one missing constant — a constant would be
wrong at three of the four pressures whichever value you picked.

### Why the model's shape decays — the mechanism, and it is structural

The model's water back-pressure moves by **exactly −6.17 mbar** when Qw goes 5 → 10 —
**at 200, 300, 400 and 600 mbar alike, to the last decimal.** It is a pure additive offset
with no coupling to the oil side at all, which is what a linear water-side resistance
gives: `ΔP_water = Qw × R_water`.

Against a `ΔP_rung` that grows 162 → 478 mbar with Po, a fixed 6.17 mbar offset *must*
decay as a fraction — 3.8% → 1.3%. **The decay is an artefact of the structure, not
physics.** For the model to reproduce a flat ~19%, the water-side loading has to **grow
with Po**.

`resistance.main_channel_resistance_per_segment` (`resistance.py:156`) builds the water
main with `config.fluids.mu_continuous` — **0.89 cP, pure water** — and the same
`Mcw`/`Mcd` as the oil main. The ladder KCL does route crossed-over oil into the water
channel, so the *volume* accumulates; the **viscosity never does**. By the outlet that
channel is carrying a dense oil-in-water droplet train and is being modelled as clean
water. More oil crosses at higher Po, so the missing term is one that **grows with Po** —
the right shape.

**Do not read that as the answer.** It is the leading hypothesis and it is almost
certainly insufficient on its own: an Einstein/Krieger-Dougherty correction at φ ≈ 0.1
gives µ_eff ≈ 1.25–1.4× µ_water, so ~6 → ~8 mbar. The deficit needs ~5×. Q2 exists to
measure this rather than assume it, and Q3 lists the other candidates.

---

## THE TRAP — read this before touching anything

The obvious fix is written down in two workspace reports already, and **it is the exact
failure mode Wave 2 spent an afternoon disproving.**

`Po_Qw_conc_combined/report.md:225` and `qw_sweep/qw_report.md:55` both recommend:

> per-Po Stage 2 lookup at Qw = 5: `{200: 0.35, 300: 0.205, 400: 0.154, 600: 0.12 s}`

and a "Qw correction factor pending further data". **Do not implement either.** That is a
constant fitted at one device, one geometry, one fluid system, one surfactant
concentration, stamped onto every design the Studio scores. It is `C_visc` with more
subscripts. The rule from W2-8, which now applies to this work verbatim:

> **A constant that fits one condition perfectly is not evidence; it is an untested
> hypothesis with a good disguise.** Cross-check against every other condition in the
> dataset before adopting anything.

The 83 cP viscosity died exactly this way: excellent at Qw = 10, and 69 / 96 at the two
conditions nobody had checked. **Any Qw correction you propose must be evaluated at all
three Qw values AND all four pressures before it goes in**, and if it needs different
numbers at different conditions, it is not physics.

Corollary: `stage1_viscosity_correction` raises on purpose
(`tests/test_stage_wise_v3_phase1.py::TestCViscStaysDeleted`). Do not add a sibling.

---

## Data hazards — both will bite

### 1. The April-2026 reports' absolute times are exactly 2× too large

`qw_sweep/qw_report.md` and `Po_Qw_conc_combined/report.md` predate the 25 → 50 fps
timing correction. Verified against `stage_timings.csv`:

```
Po 200 Qw  5:  report 1.08 s   file 0.540 s   2.00x
Po 300 Qw  5:  report 0.60 s   file 0.300 s   2.00x
Po 600 Qw  5:  report 0.25 s   file 0.120 s   2.08x
Po 300 Qw 20:  report 1.14 s   file 0.560 s   2.04x
```

**Ratios and trends in those reports are still good** (the factor cancels); **every
absolute number is not.** They are frozen records under `CLAUDE.md` and must not be
retro-edited — but nothing new may quote their absolute times. Use
`po_sweep/data/stage_timings.csv`.

They also carry `C_visc` recommendations (0.74 / 0.95 / 1.09) and a `V_reset = 6000 µm³`
recommendation. **Both are superseded**: `C_visc` is deleted (`71be939`), and the reset
length moved to `sqrt(w·h)` on a mechanism argument on 2026-08-03. Do not resurrect either.

### 2. Stage 2 at 600 mbar is at the frame-rate floor

Measured Stage 2 is 0.06 s at 600 mbar — **three frames at 50 fps** — and every value in
that column is an exact multiple of 0.02 s. The `+0.0%` Qw response at 600 mbar in the
table above is **not evidence of Qw-insensitivity**; it is evidence that the instrument
cannot resolve the difference. This is open question 2 in the studio plan and it is not
resolvable by modelling. **Weight 200 and 300 mbar accordingly.**

---

## The items

### Q1 — locate the deficit: which stage, and does it have one shape?

The measurement above splits t_S1 from t_S2 and finds the deficit in **both**. That
contradicts `comp_oil_viscosity/report.md`, which concluded "Stage 1 … agrees to −14.5% →
+0.9%, the deficit is in Stage 2+3" — **because that analysis was run at Qw = 5 only**.
At a fixed Qw the Stage-1 agreement is genuine; it says nothing about the Qw axis.

Deliverables, as a workspace (`comp_qw_response`, computational):

1. Model vs measured for `t_S1`, `t_S2+3`, `t_cycle`, `f` at **all 10 conditions**
   (Po × Qw), at the config's unfitted µ = 60 cP, with the deficit ratio per cell.
2. State whether one multiplier on the water-side loading can reconcile all ten. **Predict
   in advance that it cannot** — the flat-vs-decaying shape above says so — and record
   what the best single multiplier leaves behind. That residual is the real target.
3. Do the same split for `Qw = 20`, which the table above omits (only 300 and 600 mbar
   have it). Two points, so it is corroboration, not evidence.

**Exit**: a table saying which stage carries how much of the deficit at each condition,
and an explicit statement of whether the deficit's shape in Po is flat or decaying.

### Q2 — measure what the water main is actually carrying

Not a model change. Instrument the existing solve and report, per condition:

- oil volume fraction φ in the water main **as a function of position** (it is ~0 at the
  inlet and maximal at the outlet — a single number is the wrong answer);
- the water main's pressure drop, and what fraction of `ΔP_rung` it represents;
- what µ_eff a Krieger-Dougherty / Einstein correction at that φ implies, and what that
  does to the 6.17 mbar — **as an estimate, not as a change**.

**Exit**: the number that says whether emulsion viscosity is 20% of the answer or 90% of
it. Q3's choice turns on this.

### Q3 — decide the mechanism *(blocked on Q1 + Q2)*

Candidates, in the order the evidence currently ranks them. Each must be argued against
the **flat-in-Po** signature, which is the discriminator:

1. **Emulsion viscosity in the water main.** Grows with Po (more oil crossed over) — right
   shape. Probably too small alone (Q2 settles it). Has a principled functional form and
   no free constant, which is why it is first.
2. **Droplet-train resistance, not homogeneous viscosity.** 11,550 DFUs feed one water
   main; downstream it is a dense train of confined droplets, where the pressure drop is
   dominated by interfacial (Bretherton) terms and scales with droplet *count*, not with a
   mixture viscosity. Right shape, larger magnitude, and a real literature basis —
   **check the DMF wiki before writing any of it**; this is exactly the sort of claim that
   should be cited, not derived from scratch.
3. **Water main geometry.** Verify `Mcw`/`Mcd` for the water channel against
   `reference_devices/README.md` rather than assuming it matches the oil main. Cheap, and
   the kind of thing W1-1 found four copies of.
4. **A Stage-2 growth term that depends on the outer phase directly.** `stage2_physics`
   takes its entire Qw dependence through `Q_rung`
   (`simulate_droplet_growth_to_critical_radius`, `stage2_physics.py:260`) and its docstring
   says so explicitly. If Q1 shows Stage 2's deficit exceeds Stage 1's *after* the
   water-side loading is fixed, something acts on snap-off that is not the rung flow.

**Whatever is chosen must have no fitted constant, or must justify one against all ten
conditions.** See THE TRAP.

### Q4 — re-validate, and the exit criteria

Wave 2's shape: land the change and the re-validation as one step, because the interval
between them is where a fudge factor gets invented.

Not done until:

- [ ] `pytest -q` → **at least 636 passed, 0 failed, 5 skipped**. The empty
      known-failures list is a property worth keeping; a new failure is a new bug.
- [ ] Model vs measured reported at **all ten conditions**, both stages, before and after.
- [ ] The Qw deficit stated as a number at each condition, not as "improved".
- [ ] **No new global scalar.** If one was added, this item fails regardless of the fit.
- [ ] `configs/v5_30.yaml`'s Qw = 5 agreement **has not regressed** — Stage 1 is currently
      −14.5% → +0.9% with zero correction terms and that is W2-1's result, not something to
      spend.
- [ ] Chapter `SCHEMA_VERSION` bumped to **4** if throughput, frequency or ΔP move on any
      row — which they will. An absent field still means version 1
      (`workbook.SCHEMA_VERSION`, and D3's `load_lineage` guard reads it).
- [ ] The studio plan's W2-8 and the `comp_oil_viscosity` report updated to say the
      Stage-1-is-fine conclusion was a fixed-Qw statement.

---

## What this is worth, and what it is not

**Worth**: the Studio compares designs on throughput and frequency, and
`configs/study_my_designs.yaml` notes that four exit designs need Qw from **16.9 to 198.7
mL/hr** at a matched 10% emulsion fraction — a 12× spread. Any comparison at matched
emulsion runs straight through the axis the model is 5× wrong on. Fixed-Qw operating
predictions on a built device are much less exposed.

**Not worth**: droplet *size* is untouched by this. It is geometry-set and measured flat at
24.3–25.8 µm across the entire Po × Qw grid. Nothing here changes a droplet diameter.

**Conor's call, 2026-08-05**: Po is the leading operational variable and the Qw work is
deprioritised. That is consistent with the measurement — Po moves Stage 2 by 4.1× across
200–600 mbar where Qw moves it 1.5× across 5–20 mL/hr — and this plan exists so the
decision is revisitable rather than forgotten. **The one thing to carry forward
meanwhile**: prefer `Qw_mlhr` over `target_emulsion_pct` in study configs, because the
latter solves a different Qw per design and walks straight into the 5× error. The
checked-in `study_my_designs.yaml` already does the right thing (fixed `Qw_mlhr: 5.0`,
with `target_emulsion_pct` commented out) — leave it that way until this is fixed.

---

## Open questions

1. **Does the ~5× deficit hold on another device?** Everything here is V5-8-1, one
   geometry, one fluid system. `nacas_mct_comparison` and `conc_sweep` are the nearest
   other datasets and neither sweeps Qw.
2. **Is the Qw saturation real?** Both April reports say the Stage-2 Qw effect saturates
   between 10 and 20 mL/hr. In the corrected file only 300 and 600 mbar have Qw = 20, and
   600 mbar is at the frame-rate floor, so this rests on **one usable condition**. Treat as
   unverified.
3. **Temperature is not recorded anywhere in `stage_timings.csv`.** ±5 °C is ±30% on
   sunflower oil viscosity — larger than most effects argued about here, and it would
   appear as scatter across conditions measured on different days.
4. **Is Stage 3 physical or a frame-rate artefact?** Studio plan open question 2, unchanged,
   and it caps how well any Stage-2 model can be validated above 400 mbar.

---

## Kickoff prompt for a fresh session

> Read `.claude/plans/qw-response-and-water-side-loading.md` — start with "Where this
> stands", then "The finding" and "THE TRAP" before anything else.
>
> The model under-responds to water flow by ~5×, and the diagnosis is already measured:
> the water back-pressure moves by exactly −6.17 mbar per Qw doubling **at every drive
> pressure**, because the water main is a linear resistance carrying pure water. The real
> device's Stage-1 sensitivity to Qw is flat in Po (~19%); the model's decays 4× across
> 200–600 mbar. That shape mismatch, not the magnitude, is the thing to explain.
>
> Your job is **Q1 then Q2**. Do not start Q3 before both have reported. Do not implement
> the per-Po Stage-2 lookup that `qw_sweep` and `Po_Qw_conc_combined` recommend — read
> THE TRAP for why; it is `C_visc` with subscripts, and Wave 2 already disproved that
> class of answer once.
>
> Two data hazards that will bite: the April-2026 workspace reports' absolute times are
> **exactly 2× too large** (pre 25→50 fps correction — ratios survive, absolutes do not),
> and Stage 2 at 600 mbar is **three frames**, so its apparent Qw-insensitivity is the
> instrument, not the physics.
>
> Q1 is its own workspace (`comp_qw_response`, computational) under the data-provenance
> protocol in CLAUDE.md — config snapshot, run manifest with the git hash and exact
> commands, outputs in `results/`. `*.csv` is gitignored repo-wide, so commit a JSON or a
> stdout capture carrying the numbers the report quotes.
>
> Baseline is `pytest -q` → 636 passed, 0 failed, 5 skipped. The known-failures list is
> empty for the first time; keep it that way. Report actual test results. Commit per
> meaningful unit, staging only intentionally modified files, and update this plan's
> status markers with what implementation found that the plan did not — the way Batch 1,
> Wave 1 and Wave 2 did in the studio plan.
