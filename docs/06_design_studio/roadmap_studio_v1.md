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
| 0 | Housekeeping + threshold correction | S | not started |
| 1 | Decide layer — value axes, margin, confidence, validity | M | not started |
| 2 | Intent layer + constraint diagnosis | M | not started |
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
