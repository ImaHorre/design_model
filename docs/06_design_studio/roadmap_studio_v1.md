# Design Studio — Roadmap v1

*Companion to `PRD_studio_v1.md`. The PRD is the stable "what and why"; this is the
sequenced "how", and it changes as phases land.*

**Organising target:** run the deep-DFU design sweep — live, together, on the updated
Studio — and come out with a short-list we trust. Phases 0–3 exist to make that session
worth having. Everything after it makes the result durable.

---

## Status

| Phase | Scope | Size | Status |
|---|---|---|---|
| 0 | Housekeeping + threshold correction | S | **done** (`e390764`) |
| 1 | Decide layer — value axes, margin, confidence, validity | M | **done** |
| 2 | Intent layer + constraint diagnosis | M | **done** |
| 3 | Design visualiser (to-scale SVG) | M | not started |
| **M1** | **Deep-DFU sweep session** | — | **gated on 0–3** |
| 4 | Workbook as memory | M | not started |
| 5 | Boundary-probe studies + calibration loop | M | not started |
| 6 | Form-driven UI | M | not started |
| 7 | GDS handoff | S | not started |
| 8 | Consolidation & archive | S | not started |

Sizes are relative: **S** = a sitting, **M** = a focused block of work, **L** = multi-session.

Everything lives in `design_model/`. No new repos.

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

**The headline result, already in hand.** Running `study_intent_deep_dfu.yaml` (140 µm at
5 mL/hr under 300 mbar, all three families, 138 points): **0 green, 7 orange, 131 red**, and
exit Ca is the sole cause of 107 of those reds. The blocker for large droplets is **not**
the 200 µm main-depth cap — relaxing it to 300 µm changes nothing, and the pricing says so
in as many words. It is that a deep DFU carries so much oil (`R_rung ∝ 1/h³`; the sizing
estimate drops from ~1000 rungs to ~11) that the exit velocity leaves step-emulsification
entirely. This sharpens M1's standing hypothesis rather than confirming it: fewer DFUs is
right, but the constraint that bites is the SE ceiling, not the etch depth — and that
ceiling is itself borrowed from literature at λ ≈ 1 while we run at λ ≈ 0.015. Phase 5's
boundary probe is now the load-bearing piece of work, not a nice-to-have.

*Checked against the wiki before writing this down.* Two qualifications, neither of which
rescues the result:

* Our `regime_Ca` is the **nominal** exit Ca, but the threshold it is compared against is
  stated for the **local pinch** Ca: `Ca_in ≈ (w/h)·Ca_nominal`
  ([[equations/step-emulsification-generalized-capillary]], `@montessori2020-step-emulsification`)
  `[theory]`. The intent designs run at w/h = 3, so the true comparison is ~3× *worse* than
  the number in the table, not better. The 0.0125 bound in the study configs is also quoted
  at h/w = 1/5, which is not the aspect ratio intent generates.
* The generalised criterion adds a Weber term, `K = Ca_in + We_in`. At these geometries
  `We_in ≈ 1e-3` (ρu²/2 ≈ 0.1 Pa against σ/λ ≈ 100 Pa), so it is negligible here — the
  transition is Ca-driven, as the dripping-regime branch of that criterion says it should be.

So the finding is robust in sign and roughly an order of magnitude in size. What it is *not*
is validated: both sources sit at λ ≈ 1 and we run at λ ≈ 0.015
([[claims/step-emulsification-viscosity-insensitive]] is "supported" but on 2 sources, neither
in our λ range). The `validity` gate already flags every row for exactly this.

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
- The binding constraint named and its relaxation priced — the standing hypothesis, from
  `comp_large_dfu_stage1_screen`, is that the 200 µm main-depth cap binds for long ladders
  and that the escape is fewer DFUs (a 50 µm DFU carries ~166× the oil of a V5-30 droplet)
  or a comb manifold. The session either confirms that with numbers or overturns it.
- An explicit read on the SE-regime risk — flagged by the validity gate rather than
  discovered afterwards in prose.
- A short-list for v1, with the reasoning visible.
- A chapter in the book recording all of it.

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

**Goal:** deliberately design experiments that tell us where the model breaks — starting
with the step-emulsification ceiling.

### Deliverables
- **Probe mode**: given a model-predicted boundary, select the design points that most
  sharply discriminate across it. Output is a **build set / wafer manifest**, not a ranking.
- **The SE-ceiling probe**: one DFU geometry walked across the predicted SE→jetting
  boundary. Where does droplet size stay geometry-set and Ca-independent, and where does it
  start tracking flow rate?
- **Calibration handoff**: structure results so the measured boundary constrains effective
  interfacial tension and contact angle, and feed that back into the model constants and the
  wiki.

### Why it matters
Our SE ceiling is currently borrowed from literature at λ ≈ 1 while we operate at
λ ≈ 0.015 — far outside the validated envelope, in the direction that *narrows* the SE
window. Every deep-DFU prediction inherits that uncertainty. One well-designed wafer
converts the largest open risk into a measured number, and the constants it pins improve
every prediction afterwards.

### Acceptance
- A probe study emits a build set with a stated hypothesis per design and what each outcome
  would mean.
- Measured results ingest back into a comparison chapter and update the constants with
  provenance intact.

---

## Phase 6 — Form-driven UI

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

**4 → 5** convert the tool from per-session to compounding: the book remembers, and probe
studies feed the model. Phase 4 is deliberately after M1 — the book is nearly empty now, and
M1 is what starts filling it.

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
   "straddle the boundary at 3 points" heuristic? Start pragmatic.
