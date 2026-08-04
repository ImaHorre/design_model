# Design Studio — Roadmap v1

*Companion to `PRD_studio_v1.md`. The PRD is the stable "what and why"; this is the
sequenced "how", and it changes as phases land.*

**Organising target:** run the deep-DFU design sweep — live, together, on the updated
Studio — and come out with a short-list we trust. Phases 0–3 exist to make that session
worth having. Everything after it makes the result durable.

**Where this stands after Phase 2 (2026-07-29).** The deep-DFU question is no longer open in
the way it was when this roadmap was written. Exit Ca — not the etch-depth cap — is what binds
large-droplet designs; in-regime designs *do* exist, in the opposite direction to the standing
hypothesis (many slow DFUs, not few fast ones); and the Ca threshold that decides all of it has
never been approached within 9× on a Peak device. So M1 is now a *selection* session over a
space whose shape we know, and its most valuable output is the shortlist that feeds the Phase 5
wafer. Phase 5 is promoted to run alongside it. Details in Phase 2's "What actually landed".

---

## Status

| Phase | Scope | Size | Status |
|---|---|---|---|
| 0 | Housekeeping + threshold correction | S | **done** (`e390764`) |
| 1 | Decide layer — value axes, margin, confidence, validity | M | **done** (`f47df07`) |
| 2 | Intent layer + constraint diagnosis | M | **done** (`7b7649f` + Ca-audit follow-up) |
| 3 | Design visualiser (to-scale SVG) | M | **done** (MVP — see below) |
| **M1** | **Deep-DFU sweep session** | — | **ungated — next** |
| 5 | Boundary-probe studies + calibration loop | M | **promoted — run with M1** |
| 4 | Workbook as memory | M | not started |
| ~~6~~ | ~~Form-driven UI~~ | — | **superseded 2026-08-04** — see the filter-first plan |
| 7 | GDS handoff | S | not started |
| 8 | Consolidation & archive | S | not started |

> **Active plan, 2026-08-04.** Phase 6 has been replaced by
> **`.claude/plans/design-studio-filter-first-front-door.md`**, which is the executable
> plan for the next block of work (Batch 1 → Wave 1 → Wave 2 → server → explorer). It
> supersedes Phase 6 entirely and re-scopes parts of Phases 3 and 4. Read it before
> starting any Studio work; this roadmap remains the record of Phases 0–3 and M1.
>
> Physical ground truth for layout and packing now lives in **`reference_devices/`** —
> the three built devices as GDS, with the measurement table in its README.

Sizes are relative: **S** = a sitting, **M** = a focused block of work, **L** = multi-session.

Everything lives in `design_model/`. No new repos.

### Items carried out of Phase 2 — both now settled (2026-07-29)

1. **Dispersed phase — RULED: `SO` is always sunflower oil, never silicone.** Corrected across
   22 files (workspaces, analysis scripts, archived scripts) and the wiki. µ = 50–60 cP, which
   is what the derived Ca figures already assumed, so those stand. Two downstream conclusions
   did *not* survive and were flagged in place rather than silently amended:
   - `nacas_mct_comparison` explained MCT's higher minimum pressure by MCT being *more* viscous
     than the control. Sunflower ~50–60 cP vs MCT ~25–30 cP inverts that — argument withdrawn,
     observation stands, needs a new explanation.
   - `comp_interfacial_inversion`'s `GAMMA_LIT_2PC_MNM = 9.0` was a literature figure for
     SDS/*silicone*. Retained as an order-of-magnitude placeholder, no longer sourced; the
     pendant-drop measurement must be run against sunflower oil.

2. **Interfacial tension — CONFIRMED UNKNOWN, and acted on.** γ has never been measured for the
   Peak system; every config value is a guess (5, 15, 0 mN/m across this repo). Rather than
   leave Ca as a hard gate resting on a guessed constant, the Studio now reports **γ-robustness
   of every Ca verdict**. See below.

---

## Phase 0 — Housekeeping and one correctness fix

**Do this before anything else builds on top of it.**

1. **Commit the outstanding work.** Eight modified files are unstaged, including the
   ~315-line `families/manifold.py` two-rail rewrite and the `design/layout.py` lane-pitch
   correction, plus two untracked workspaces (`comp_deep_dfu_v5_main_mods`,
   `comp_interfacial_inversion`). Stage deliberately — never `git add .` per repo policy.
   Confirm the studio tests pass first.

2. **Fix the `regime_Ca` thresholds.** `configs/study_all_families.yaml` uses
   `{ green: 0.01, orange: 0.3 }`. The wiki-grounded SE→jetting ceiling used in
   `comp_large_dfu_stage1_screen` is **0.0125–0.03**. The current orange bound is an order
   of magnitude too permissive and will pass deep-DFU designs that are outside
   step-emulsification. Correct it in every study config, and record the citekey for the
   value in a comment so the next person can check it.

**Acceptance:** clean `git status`; a deep-DFU config that previously scored green on Ca
now scores orange or red for the right stated reason.

---

## Phase 1 — The decide layer

**Goal:** the scored table stops being a table and starts being a decision. Answers
"best by flatness / by throughput / by drive pressure / all-round / safest".

### Deliverables

**`stepgen/studio/ranking.py`** *(new)*
- Value-axis registry: each axis names a `CommonMetrics` field and a direction.
- Per-axis winner selection.
- Pareto-non-dominated set across the declared axes — **lift `_pareto_front()` from
  `viz/plots.py`**, don't rewrite it.
- Weighted composite with explicit, recorded weights.
- `safest` ranking = maximise the minimum confidence-discounted margin.

**`stepgen/studio/scoring.py`** *(extend)*
- `CellScore.margin`: distance from the red boundary as a fraction of the green→red span.
- `ScoredRow.min_margin`: the weakest link across applicable metrics.
- `validity` added to `SCORING_KEYS` — Ca vs SE ceiling, λ vs validated envelope, aspect
  ratio vs fitted range. Outside envelope → hard orange, never green.

**`stepgen/families/base.py`** *(extend)*
- `metric_confidence()` per family: `validated` | `calibrated` | `extrapolation` per metric.
  Deep-exit frequency and out-of-envelope Ca are `extrapolation`; Stage-1 ΔP distribution is
  `validated`.

**Study schema** — `goal:` (single word) gives way to:
```yaml
decide:
  axes: [flatness, throughput, drive_pressure, margin]
  weights: { flatness: 0.4, throughput: 0.3, drive_pressure: 0.2, margin: 0.1 }
```
Keep `goal:` working as a one-axis shorthand so existing configs don't break.

**Workbook + UI** — a "Decision" panel above the table: per-axis winners, Pareto set,
all-round pick, safest pick, weights shown and (in the UI) live-adjustable.

### Acceptance
- One study returns four differently-named winners where the axes genuinely conflict.
- A green-but-marginal row is visibly distinguishable from a green-and-comfortable one.
- A verdict resting on an `extrapolation` metric is flagged in plain language.
- Tests: Pareto correctness on a known set; margin arithmetic at both boundaries; validity
  gate fires on a known out-of-envelope deep-DFU point.

### Risk
Weight-tuning is seductive and mostly noise. Per-axis winners and the Pareto set are the
real output; the composite is a convenience. Resist letting it become the headline.

### What actually landed

`stepgen/studio/ranking.py` (new) — axis registry, per-axis winners, N-axis Pareto,
weighted composite, `safest`. `viz/plots.py::_pareto_front` now delegates to
`ranking.pareto_mask`, so there is one implementation of the rule.
`scoring.py` — `CellScore.margin` / `.confidence` / `.detail`, `ScoredRow.min_margin`,
`.min_margin_discounted`, `.weakest_metric`, `.extrapolated_keys`, and the `validity`
gate. `families/base.py` — `metric_confidence(cm)` on the contract (row-aware, not just
family-static), plus `exit_width_um` / `exit_depth_um` / `lambda_visc` on `CommonMetrics`
to feed the envelope checks. Decision panel in the chapter and a Decision tab with live
weight sliders in the UI; `decision` block added to the JSON sidecar.
Tests: `tests/test_studio_decide.py` (43) + UI additions.

Three decisions worth recording, because they departed from the plan as written:

1. **Margin is not capped above 1.0.** Capping at the green bound was the first
   implementation and it made *every* green cell read 100%, which destroys the
   distinction the column exists to draw. It is now floored at 0 and uncapped above:
   1.0 is exactly the green bound, and 1.6 means "a full green→red span of headroom
   and a bit over half of another". This resolves open question 2 in the direction of
   *not* forcing commensurability; the caveat about cross-metric comparison is recorded
   in the `_margin` docstring rather than papered over by a clamp.

2. **Validity breaches are split into study-wide caveats and row-specific ones.**
   Our λ ≈ 0.015 is outside the validated envelope for *every* design we will ever run
   on this fluid system, so scoring it per row makes every row orange for the same
   reason and desensitises the signal. `ranking.shared_caveats()` lifts breaches common
   to all rows into a single standing caveat; `row_specific_breaches()` leaves the ones
   that actually discriminate on the row. The gate itself stays honest per row.

3. **Confidence is row-aware, not family-static.** `metric_confidence()` takes the
   `CommonMetrics`, because the same family yields a validated throughput at a 10 µm
   exit and an extrapolated one at 50 µm. This answers open question 3: the tier lives
   in family code but is computed from the row, with the shared v3 position in the base
   class and families free to sharpen it.

Still open: the real `study_all_families` grid has one design that wins every axis, so
the four-different-winners case is exercised by a constructed set in the tests rather
than by a shipped config. M1's deep-DFU grid is where genuine conflict should show up.

---

## Phase 2 — Intent layer and constraint diagnosis

**Goal:** the user states a question, not a grid. And when the answer is "you can't", the
Studio says *why* and *what it would take*.

### Deliverables

**`stepgen/studio/intent.py`** *(new)* — a new study block:
```yaml
intent:
  droplet_um: 140              # "deep DFUs, large droplets"
  throughput_mlhr: 5
constraints:
  max_Po_mbar: 300             # "don't start production at 1000 mbar"
  fab: current                 # or: relaxed_300um
explore: [serpentine, radial, manifold]
```
Generates the sweep grid rather than requiring it: derive junction geometry from the
droplet target per family, bound the sweep by the constraints, hand the result to the
existing expansion path. **The inverse solve already exists** in
`design/design_search.py` (`target_droplet_um` → exit geometry via `D = k·w^a·h^b` with
aspect-ratio limits) — generalise it behind the `Family` contract rather than reimplementing.
`families/serpentine.py` already has a `target_droplet_um` path; radial and manifold need one.

**`stepgen/studio/diagnosis.py`** *(new)*
- Binding-constraint analysis: which gate fails most across the study, and which gate is
  the sole cause of each red row.
- Relaxation pricing: re-run with each active constraint stepped one notch and report the
  delta — *"relax `max_main_depth` 200 → 300 µm: 12 red → green."*

This turns a filter into an answer, and prices process decisions: it puts a number on what
deeper etch capability is actually worth. The large-DFU screen already concluded in prose
that the 200 µm cap — not the physics — is the blocker for long deep-DFU ladders. That
sentence should be computed, not written by hand.

**Grid staging** *(if needed)* — Cartesian expansion over 3 families × depth × main
geometry × N × arm count gets large, and every point runs a full nodal solve. If the
deep-DFU study is slow: prefilter on the cheap analytic build gates before solving, and
screen coarse before refining near the frontier. Only build this if the run is actually
slow — measure first.

### Acceptance
- A user writes only `intent:` + `constraints:` + `explore:` and gets a scored space across
  three families.
- An infeasible intent returns the binding constraint and its relaxation price, not an
  empty table.
- Tests: intent → grid for each family; diagnosis identifies a deliberately-planted single
  binding constraint.

### What actually landed

`stepgen/families/intent.py` (new) — the intent vocabulary in the *family* layer:
`Intent`, `Constraints`, `FAB_PRESETS` (`current` / `relaxed_300um` / `relaxed_500um`),
the junction inverse solve, the analytic DFU-count sizing, and `plan_junction()` which
every family starts from. `families/base.py` — `grid_from_intent()` on the contract,
raising `IntentNotSupported` by default. All three families implement it.
`design_search._derive_mcd_from_ar` now delegates to `intent.depth_for_droplet`, so the
design search and the Studio cannot drift apart on what a droplet target means.

`stepgen/studio/intent.py` (new) — YAML parsing and study generation; `expand_intent()`
returns an ordinary study dict plus an `IntentPlan` recording what was generated, what
the user wrote, and which families were skipped. `study.py` — `build_study(raw)` split
out of `load_study_text` so relaxation pricing can rebuild from a mutated dict without
round-tripping through YAML; `Study.from_intent` / `.intent_plan` / `.intent_raw`.

`stepgen/studio/diagnosis.py` (new) — `binding_gates()` (free, always runs),
`KNOBS` + `active_knobs()`, `price_relaxations()`, and `diagnose()`.
`scoring.py` — the `build` cell now records *which* sub-gate failed in `.detail`.
CLI: `stepgen study --diagnose auto|always|never`, with the diagnosis printed.
Workbook: Intent and Diagnosis panels + both in the JSON sidecar. UI: a Diagnosis tab,
with pricing behind a button and the generated YAML shown in an expander.
Tests: `tests/test_studio_intent.py` (40).

Four decisions worth recording:

1. **Intent generates, it does not refuse.** A 140 µm droplet needs a ~51 µm exit —
   5× beyond the range the droplet power-law was fitted over. Intent draws it anyway
   and lets the `validity` gate flag every row. Refusing to generate would have hidden
   the question; the honest division is *intent decides what to try, scoring decides
   what to trust*.

2. **Knobs write to `constraints:`, not just `manufacturing:`.** For an intent study the
   constraints block generates *both* the manufacturing caps and the geometry grid.
   Stepping only the fab block would have loosened the gate while leaving the generated
   main depth pinned at the old cap — the price would have come back as zero for the
   wrong reason. Relaxation therefore regenerates the whole grid, and
   `Constraints.as_block()` writes the resolved preset back into the recorded question
   so a cap hiding inside a preset is still visible to pricing.

3. **"Sole cause" is the ranking signal, not raw failure count.** A gate that reds half
   the study but never alone is a symptom. Only a gate that is the *only* red on a row
   would change that row's verdict if relaxed, so that is what orders the table and
   selects which knobs are worth a re-run.

4. **Some gates have no knob, and saying so is the finding.** `regime_Ca` is deliberately
   absent from `KNOBS`: no etch depth, die size or pressure ceiling moves the
   step-emulsification ceiling. `Diagnosis.binding_is_physics` reports that explicitly
   rather than offering a process change that would not help.

**The headline result.** Running `study_intent_deep_dfu.yaml` (140 µm at 5 mL/hr under
300 mbar, all three families, 216 points): **0 green, 33 orange, 183 red** — but **87 of
those reds are red on exit Ca alone**, and the low-Ca corner does contain in-regime designs.
The blocker for large droplets is **not** the 200 µm main-depth cap: relaxing it to 300 µm
clears 2 rows out of 183, and the pricing says so in as many words. What binds is that a
deep DFU carries so much oil (`R_rung ∝ 1/h³`) that the exit velocity leaves
step-emulsification — unless you deliberately run many DFUs slowly.

This sharpens M1's standing hypothesis rather than confirming it. *Fewer DFUs* was the wrong
half: the Ca-compliant answer is the opposite direction — **more** DFUs, each throttled, at
low drive pressure:

| Design | Exit Ca | Throughput | ΔP spread |
|---|---|---|---|
| `radial_R29.75_U76_Po45` | **0.0018** | 2.6 mL/hr | automatic |
| `serpentine_…_N344_Po45` | **0.0021** | 1.67 mL/hr | 34% |
| `serpentine_…_N11_Po300` | 0.71 | 18.2 mL/hr | 2.6% |

Those top rows sit *at* the measured envelope (0.0017), so their regime risk is nearly nil.
They are orange rather than green only because a 51 µm exit is outside the range the droplet
*size* power-law was fitted over — a different, narrower uncertainty. The real trade the
decide layer now has to rank is **Ca against flatness**: low Ca wants a long slow ladder, and
a long ladder droops.

#### Correction — the first version of this grid was Ca-blind

As first shipped, `rungs_for_throughput` sized N to hit the throughput target *at the pressure
ceiling*, which maximises per-DFU velocity — precisely the wrong direction when Ca is what
binds. The grid swept N ≤ 44 at Po ≥ 120 mbar and reported **0 green / 131 red**, which was
honest about the space it searched but was searching the wrong corner. Fixed by
`rungs_for_ca_ceiling()` + `dfu_count_ladder()`, which span both sizing answers (they differ
by ~15× here: 23 rungs for throughput, 172 for Ca), and by extending the pressure sweep down
to 0.15× the ceiling. Recorded rather than quietly amended, because the failure mode is
general: **a generated grid inherits the bias of whatever it was sized against.**

#### The Ca audit — why "we don't understand Ca" is an understatement

Computed 2026-07-29 from `experimental_workspaces/po_sweep/data/stage_timings.csv`
(V5-8-1, 30×10 µm exit, `@ws-2026-07-13-po-sweep-v5-8-1`) `[experimental]` — per-DFU flow
from droplet volume over measured cycle time:

| Po (mbar) | Droplet (µm) | CV | Exit Ca |
|---|---|---|---|
| 200 | 25.0 | 12% | 0.00035 |
| 400 | 25.0 | 3.0% | 0.00077 |
| 600 | 25.6 | 2.8% | **0.00137** |

**Every Ca Peak has ever measured is ≤ 0.0017** — 7× below our own 0.0125 green bound and
18× below the 0.03 red bound. At γ = 15 mN/m instead of 5 it drops to 0.0005 (27× below); if
the dispersed phase were a low-viscosity silicone oil it would be 164× below. **On every
assumption we have never operated within an order of magnitude of the threshold we design
against.** Droplet size was flat across the whole sweep, so this is a *lower bound* on the
ceiling and nothing more. Recorded as `families.base.CA_MEASURED_MAX`.

Consequences taken:
* `metric_confidence()` now grades `regime_Ca` on the **measured envelope**, not the SE
  ceiling. Below the ceiling but above 0.0017 is an extrapolation, because it is.
* `diagnosis.EVIDENCE_THIN_GATES` + `theory_limited_rows()` name the designs that are **green
  on everything except Ca**. The verdict stays red — quietly downgrading an unmeasured risk
  would be worse than no verdict — but the chapter, the UI and the CLI now call them
  *build-and-see candidates* and say why. Whether they work is a question the model cannot
  settle, and the user is better placed than the scorer to decide whether to try.

#### γ-robustness — how much of a Ca verdict survives not knowing γ

*Added 2026-07-29 in response to: "if it's major into the red throughout a range of gamma then
that seems more wrong than only just into the red with only select values of gamma."*

γ has never been measured for this fluid system, so a hard red on Ca is a hard verdict resting
on a guessed constant. But **γ enters the studio families in exactly one place** — the
`Ca = µ·v/γ` diagnostic — and never the hydraulic solve. So `Ca ∝ 1/γ` exactly, and the whole
plausible band can be swept **analytically from the single solved value, at zero cost and with
no re-runs**. `ca_gamma_robustness()` does this over `DEFAULT_GAMMA_RANGE_NM = 3–20 mN/m`, a
band written down as a statement of ignorance rather than a measurement, to be narrowed the day
a pendant-drop number exists.

The Ca-only reds then split in two, and the split is the finding:

| | Count (deep-DFU study) | Reading |
|---|---|---|
| Red at **every** plausible γ | 45 | The verdict survives our ignorance. Genuinely out of regime — believe it. |
| Red at **part** of the band | 42 | The verdict turns on a constant nobody has measured. **This is the real shortlist.** |

The shortlist is ordered by **how little γ it takes to clear** — a design that clears above
6.6 mN/m is a far better bet than one needing 18.6, and the second is barely distinguishable
from robustly red. Reported in the chapter, the UI ("Clears above γ" column) and the CLI, and
recorded in the sidecar as `ca_red_at_every_gamma` / `ca_red_only_at_some_gamma`.

This is the mechanism that stops Ca being a hard no while keeping it honest: the gate is not
weakened, but a red caused by our ignorance is separated from a red caused by the design.

*Checked against the wiki.* Two qualifications, neither of which rescues the picture:

* Our `regime_Ca` is the **nominal** exit Ca; the threshold is stated for the **local pinch**
  Ca, `Ca_in ≈ (w/h)·Ca_nominal`
  ([[equations/step-emulsification-generalized-capillary]], `@montessori2020-step-emulsification`)
  `[theory]`. At w/h = 3 the true comparison is ~3× *worse*. The 0.0125 bound is also quoted
  at h/w = 1/5, not the 1/3 intent generates.
* The generalised criterion adds a Weber term, `K = Ca_in + We_in`. Here `We_in ≈ 1e-3`
  (ρu²/2 ≈ 0.1 Pa against σ/λ ≈ 100 Pa) — negligible, so the transition is Ca-driven exactly
  as the dripping branch of that criterion predicts.

#### Two provenance discrepancies found — both resolved 2026-07-29

1. **Dispersed phase — ruled.** `SO` is always **sunflower oil**, never silicone. The wiki page
   and the workspace BRIEF both carried the wrong label; the raw `DispPhase = SO` column and
   `CLAUDE.md` were right. Corrected across 22 files and the wiki. Since the derived Ca table
   already used µ = 60 cP, those figures stand. Two downstream conclusions did not survive —
   see "Items carried out of Phase 2" above.
2. **Interfacial tension — confirmed unknown.** Configs disagree: `study_all_families.yaml`
   uses γ = 5 mN/m, `study_template.yaml` and the `wo_*` configs use 15, and `v5_30.yaml` uses
   0 (Ca disabled). A 3× spread in γ is a 3× spread in every Ca number in this repo. Handled by
   the γ-robustness layer above rather than by picking a number.

Both still belong in Phase 5's scope: the probe measures `Ca_crit` with γ and µ folded in,
which is the right unit for *design*, but exporting the result to another fluid system needs γ
pinned independently.

---

## Phase 3 — Design visualiser

**Goal:** you can see what you are about to choose.

### Deliverables

**`render_schematic()` on the `Family` contract**, rendered from the *compiled* config the
solver used, emitting **inline SVG** (self-contained chapter; readable when zoomed).

- **Whole-device view** — topology at scale in the die square: manifold spine + arms +
  DFU zones; radial hub + spokes; serpentine lanes + turns. Footprint usage obvious.
- **Zoomed DFU group** — a few adjacent DFUs at true scale with dimensions called out:
  rung length, upstream width, exit width/depth, pitch, wall and continuous-phase gaps.

`viz/plots.py::plot_layout_schematic` already does this for serpentine — generalise it.

**Workbook + UI** — schematic in the drill-down for any selected row; whole-device and
zoom side by side.

### Why before M1
The manifold packing model was recently corrected by **~10–20× on DFU count** (arm pitch
was ignoring the DFUs entirely). A to-scale drawing catches that class of error on sight.
Going into a deep-DFU session without it means trusting packing numbers we cannot see.

### Acceptance
- The `study_all_families.yaml` manifold row renders arms, DFU zones and the continuous-phase
  loop at correct relative scale.
- The zoom's called-out dimensions match the compiled config exactly.
- Test: rendered geometry totals reconcile against `CommonMetrics.area_used_cm2` and `N_dfu`.

### Landed — MVP, 2026-07-30

**The split that made it universal.** `stepgen/viz/schematic.py` is a topology-agnostic
drawing engine (primitives in device metres, SVG emission, LOD, dimensioning, legend,
scale bar, pan/zoom). Each family declares its *shape* in ~40 lines behind
`Family.render_schematic(compiled, view)`, emitted from the compiled object the solver
consumes. A config file alone cannot drive this: YAML holds parameters to a shape, not a
shape, so a renderer reading only YAML would be a second packing model free to disagree
with the first — precisely the failure this phase exists to catch. Families that declare
nothing get an honest fallback (die + junction, labelled "topology not declared") rather
than an invented topology.

**Live, because drawing needs no solve.** `compile()` + layout is ~1–4 ms against ~522 ms
for `solve()`. The UI's new Layout tab reads the *live* sidebar YAML and only compiles, so
the drawing tracks edits with no re-run and works before a study has ever been run. A
regression test asserts the preview path never calls `solve()` — the premise the whole tab
rests on.

**Packing capacity — the layout model inverted.** `Family.packing_capacity(compiled)`
answers "what does this die hold", not just "does this fit". Growing the footprint now
visibly buys DFUs instead of merely turning a gate green. Serpentine 1,000/5,445 (18%);
radial 3,115/3,324 (94%); manifold 800/12,662 (6%) — that last against the real V5-30's
11,550, which is the order-of-magnitude tripwire for the family whose arm pitch was wrong
by 10–20×.

**A correction the drawing forces.** `num_lanes = ceil(Mcl / lane_length)` does not contain
`turn_radius`. Tightening the turn compacts the stack so an overflowing design *fits*; it
never adds a lane. Both halves are pinned by test. At the V5 default the ratio is 0.11
(500 µm turn carrying a 4,500 µm bundle), and the drawing says so.

**Honesty.** Every schematic carries an `inventions` list — the fold arc (2·r_turn is
reserved but no turn path or pressure drop is modelled), the nominal exit length (the model
treats the exit as a cross-section with no length), depths annotated not drawn. Rendered in
an amber box under each figure; tests assert every view declares inventions and that they
reach the HTML.

Tests: `tests/test_studio_schematic.py`, 47 new, all passing. Full suite 494 passed; the
same 5 pre-existing failures (3 `test_cli` png, 2 `test_design_search`) remain — verified
identical in a clean worktree at `a1a23d3`, not assumed.

**MVP limits, deliberately left:**
- Workbook embeds drawings for starred rows + the first `MAX_SCHEMATIC_ROWS` (60) at
  ~28 KB/row; uncapped, a 216-point study would add ~6 MB to a ~750 KB chapter. Capped rows
  say so and point at the UI.
- LOD is fixed at render time, so browser zoom on the device view reveals no new detail —
  that is what the zoom view is for. Zoom-responsive LOD needs a client-side redraw.
- No minimum bend radius as a *fab constraint*: `turn_radius` is drawn and live but has no
  floor, so nothing stops the packing model using an unbuildable turn.
- The acceptance item "rendered geometry totals reconcile against `area_used_cm2`" is
  covered indirectly (lane count and fit reconcile against `compute_layout`), not as a
  direct area cross-check.

---

## M1 — The deep-DFU sweep session

**The milestone the first four phases exist for. Run live, together, on the updated Studio.**

Not a script to run unattended — a working session where the tool is driven interactively
and the reasoning happens out loud.

**Going in:**
- Intent: large droplets via deep DFUs. Constraints: fab caps as they stand, plus a
  relaxed-depth scenario. Pressure ceiling stated up front.
- Explore: serpentine, radial, manifold.
- Axes: flatness, throughput, drive pressure, margin.

**Expected to come out with:**
- The best deep-DFU design on each axis, the Pareto set, and the all-round and safest picks.
- The binding constraint named and its relaxation priced.
- An explicit read on the SE-regime risk — flagged by the validity gate rather than
  discovered afterwards in prose.
- A short-list for v1, with the reasoning visible.
- A chapter in the book recording all of it.

**Two of these are now answered in advance** by the Phase 2 run (see "What actually landed"
above), which changes what the session is *for*:

- The depth-cap hypothesis is **settled and priced at roughly zero** — relaxing 200 → 300 µm
  clears 2 rows of 183. Do not spend the session arguing about etch depth.
- The binding constraint is **exit Ca**, and it is a design lever rather than a purchasable
  one. The live trade is **Ca against ΔP flatness**: in-regime designs need many DFUs run
  slowly, and long ladders droop.

So M1 becomes a *selection* session over a space we already know the shape of, and its most
valuable output is the shortlist that feeds Phase 5's wafer — not a feasibility verdict.

**This session also tests the tool.** Whatever we reach for and cannot find becomes the
backlog for Phases 4–6.

---

## Phase 4 — Workbook as memory

**Goal:** "have we done this before?" becomes answerable in the UI, before the run.

### Deliverables
- **Chapter metadata**: `question`, `author`, `date`, `tags`, `finding`, `status`,
  `supersedes` / `builds_on`.
- **`book/registry.json`** keyed on (config hash, model git hash) — exact prior-run
  detection, and a stale-physics warning when a chapter predates a model change.
- **Prior-art check**: on assembling a study, surface nearby prior chapters with the three
  actions — **(a) continue**, **(b) reuse this result**, **(c) compare against it**.
- **Compare picker**: tick prior chapters from a dropdown to overlay them. The mechanism
  exists (`reference: { kind: chapter }` already resolves and draws another chapter's rows);
  it needs an index to search and a UI control instead of a hand-written path.
- **Book index**: searchable by tag, family, droplet band, author, date, status.

### Acceptance
- Re-assembling a previously-run study is detected before it runs.
- A user ticks two prior chapters and sees them overlaid without editing YAML.
- A chapter computed on superseded physics is visibly marked.

---

## Phase 5 — Boundary-probe studies and the calibration loop

**Promoted to the critical path (2026-07-29).** Phase 2 established that exit Ca is the
binding constraint on every large-droplet design, and that the threshold we score it against
has never been approached within 7× on a Peak device. Every deep-DFU decision now rests on a
number we have not measured. This is no longer a follow-up phase; it is the load-bearing
piece of work, and it should run *alongside* M1 rather than after it — M1's shortlist is the
natural input to the wafer.

**Goal:** deliberately design experiments that tell us where the model breaks — starting
with the step-emulsification ceiling.

### Deliverables
- **Probe mode**: given a model-predicted boundary, select the design points that most
  sharply discriminate across it. Output is a **build set / wafer manifest**, not a ranking.
- **The SE-ceiling probe** — designed below.
- **Calibration handoff**: structure results so the measured boundary constrains effective
  interfacial tension and contact angle, and feed that back into the model constants and the
  wiki.

### The SE-ceiling probe — design

**What makes it discriminating** (rather than "build a few and see"):

1. **The readout is `dD/dQ`, not pass/fail.** SE's signature is Ca-*independent* droplet size
   ([[claims/step-emulsification-ca-independent-size]], `@chakraborty2017` + `@montessori2020`
   `[theory]`). Below the ceiling `D` is flat and frequency carries the flow; above it `D`
   starts tracking flow and CV rises. **We have already run this readout once** — the V5-8-1
   Po sweep gave flat 24.8–25.6 µm at CV ~3% (`@ws-2026-07-13-po-sweep-v5-8-1`
   `[experimental]`). The method is proven on a Peak device; the probe extends its reach.

2. **Pressure sweeps Ca for free — spend the mask on geometry.** You cannot reach the ceiling
   on a 30×10 exit by pressure alone: 800 mbar only reached Ca = 0.0017 and you would need
   roughly 6000 mbar. But per-DFU flow is set by how many DFUs share the supply, so a **deep
   exit in a short array** crosses the ceiling comfortably inside the normal Po range (the
   model puts a 51 µm exit at Ca 0.0125 → 0.31 across Po 50–300 at N = 44).

3. **Cross two geometry lines, to learn *which* Ca matters.** The threshold is stated for the
   local pinch Ca, `Ca_in ≈ (w/h)·Ca_nom` (`@montessori2020` `[theory]`), and one geometry
   cannot distinguish the two. Fix `w/h = 3` and vary `h ∈ {10, 25, 50} µm`; fix `h = 25` and
   vary `w/h ∈ {2, 3, 5}`. The lines share a point — that is the internal consistency check.
   If `Ca_crit` is constant across the set, nominal Ca is the right variable; if it scales as
   `h/w`, the local-pinch conversion holds.

4. **Anchor on the known-good.** Include a 30×10 exit as control. If the probe says V5-30 is
   above the ceiling, the probe is wrong.

5. **Short arrays, not production ladders.** At N = 600, Po = 300 the model puts ΔP spread at
   433% — every DFU would see a different Ca and the knee would smear out. **20–50 DFUs at
   matched ΔP** keeps the per-DFU Ca well defined, which is the whole measurement.

**Stated hypothesis per design, and what each outcome means:**

| Observation | Reading |
|---|---|
| `D` flat across the full Po sweep | that geometry never left SE; `Ca_crit` is above the highest Ca reached — record as a new lower bound |
| `D` flat, then rising past some Po | **the measurement**: `Ca_crit` is at the knee |
| `D` rising from the lowest Po | that geometry is above the ceiling everywhere tested; `Ca_crit` is below the lowest Ca reached |
| `Ca_crit` constant across all geometries | nominal Ca is the controlling variable; keep `regime_Ca` as scored |
| `Ca_crit ∝ h/w` | the local-pinch conversion holds; `regime_Ca` should be multiplied by `w/h` before comparison |
| CV rises before `D` moves | pinch is destabilising ahead of the regime change — a separate and useful failure mode |

**Known confounds to design around** (both surfaced in Phase 2):
- **γ is not pinned.** Configs in this repo disagree by 3× (5 vs 15 mN/m), and Ca scales
  inversely. The probe measures `Ca_crit` with γ folded in — the right unit for *design*,
  since Po and geometry are what you control — but γ must be measured independently before
  the result can be exported to another surfactant system.
- **The dispersed phase is settled** (sunflower oil, ruled 2026-07-29), so the control device
  is interpretable. γ remains the open input.

### Why it matters
Our SE ceiling is currently borrowed from literature at λ ≈ 1 while we operate at
λ ≈ 0.015 — far outside the validated envelope, in the direction that *narrows* the SE
window. Every deep-DFU prediction inherits that uncertainty, and Phase 2 showed it is the
only thing standing between us and 87 otherwise-green large-droplet designs. One
well-designed wafer converts the largest open risk into a measured number.

### Acceptance
- A probe study emits a build set with a stated hypothesis per design and what each outcome
  would mean.
- The build set spans the predicted ceiling on both geometry lines, with the 30×10 control.
- Measured results ingest back into a comparison chapter and update `CA_MEASURED_MAX` and the
  scoring thresholds with provenance intact.

---

## Phase 6 — Form-driven UI — **SUPERSEDED 2026-08-04**

> **Do not execute this phase.** It is replaced by
> `.claude/plans/design-studio-filter-first-front-door.md`.
>
> **Why it was wrong.** Phase 6 assumed the user composes a bespoke study per question, so
> the job was a form that writes an `intent:` block. That is not the loop. The real loop is
> *run one broad sweep → filter the results → sort by what matters → refine around the
> designs you liked*. Every constraint the user actually states (ΔP spread, area, pressure,
> throughput, Ca) is a field on a solved row, so it belongs in a **filter, not a grid
> generator**. That dissolves this roadmap's own bolded lesson — a generated grid inherits
> the bias of whatever it was sized against — because a broad sweep is sized against
> nothing.
>
> Two deliverables below survive, relocated: the template gallery becomes the *design set*
> region of the new form, and "YAML stays the source of truth" is unchanged. The
> "I want to…" intent screen and the LLM config helper are **out for v1**.
>
> Retained verbatim below as the record of what was planned.

**Goal:** "easy to understand, easy to interact with" — the current sidebar is a raw YAML
`st.text_area`.

### Deliverables
- Schema-generated forms: every field with units, valid range, fab limit, a one-line
  plain-English "what this does", and live validation.
- An **"I want to…" entry screen** that writes the `intent:` block for you — the front door
  for Path A.
- A **template gallery** for Path B: start from a family template, house-standard study
  attached.
- **YAML stays the source of truth** and the export format — it is what makes provenance
  work. The raw editor remains as an advanced escape hatch, showing the YAML the form
  produces.

### Acceptance
- A first-time user runs a meaningful study without seeing YAML.
- The form and the raw editor round-trip without loss.

---

## Phase 7 — GDS handoff

### Deliverables
- **Device spec export** (JSON): every dimension resolved, SI units, carrying the chapter ID,
  config hash and model git hash that produced it.
- `gds-create` consumes the spec and owns all layout, layer and mask-rule concerns.
- "Export to layout" button on any chapter row.

### Acceptance
- A chosen design exports and is picked up by `gds-create` without manual dimension re-entry.
- Any fabricated device traces back to the study that chose it.

---

## Phase 8 — Consolidation and archive

Per **DR-1** in the PRD:
- Port the genuinely valuable `stepgen_ui` pages — **experiment overlay** and **operating
  map**, which the Studio lacks entirely — into Studio tabs.
- Archive `stepgen_ui` and the `stepgen` integration repo with README pointers here.
- Update `CLAUDE.md` and `docs/README.md` to name the Studio as the design-decision layer
  and add `06_design_studio/`.

---

## Sequencing rationale

**0 → 1 → 2 → 3 → M1** is the critical path, and each phase is independently useful:
Phase 1 improves every existing study; Phase 2 removes the hand-written grid; Phase 3 makes
results checkable by eye.

**Phase 5 was promoted ahead of Phase 4 on 2026-07-29.** The original ordering assumed the
model's weakest assumption was a background risk. Phase 2 showed it is *the* constraint: 87
large-droplet designs are green on everything except a Ca threshold no Peak device has come
within 7× of. Until that number is measured, every deep-DFU verdict is an opinion with a
decimal point. Phase 5 now runs alongside M1, taking M1's shortlist as its build set.

**Phase 4** still converts the tool from per-session to compounding, and is still deliberately
after M1 — the book is nearly empty now, and M1 plus the probe are what start filling it.

**6 → 7 → 8** are adoption and closing the loop: they matter most once the underlying
decisions are trustworthy.

**Deferred, deliberately:** black-box or gradient optimisation over free geometry; a
surrogate model; multi-user infrastructure. All are v2+ per the PRD non-goals.

---

## Open questions

1. **Value axes** — is the right set {flatness, throughput, drive pressure, margin, area},
   or does deep-DFU work need droplet-size fidelity as an axis in its own right?
2. **Margin normalisation** — fraction of the green→red span is the obvious choice, but it
   makes margins comparable across metrics only if the thresholds are themselves
   commensurate. Worth checking against a real study before committing.
3. **Confidence tiers** — who assigns them, and where do they live? Family code is the
   natural home, but the judgement is physics, so it may belong beside the physics plan.
4. **Probe-set selection** — a principled information-gain criterion, or a pragmatic
   "straddle the boundary at 3 points" heuristic? Start pragmatic. *Resolved in the Phase 5
   design above: pragmatic, with two crossed geometry lines so the set discriminates between
   nominal and local-pinch Ca rather than merely bracketing a number.*

5. **Should an evidence-thin gate be allowed to red a row at all?** Phase 2 answered "yes,
   but name it" — the verdict stays red and `theory_limited_rows()` surfaces the build-and-see
   set separately. The alternative, a fourth verdict colour for "buildable but unproven",
   was rejected as premature: it is a real distinction, but one worth making only if the
   build-and-see set turns out to be something people act on repeatedly. Revisit after M1.

6. **What else is evidence-thin?** `EVIDENCE_THIN_GATES` currently holds only `regime_Ca`,
   because that is the one where the gap between what we score and what we have measured was
   actually computed. `uniformity_pct` is asserted to be `validated` on the strength of the
   po_sweep work — worth auditing the same way before trusting it as much as the tier claims.
