# StepGen Design Studio — PRD v1

**The interactive design-decision layer over the StepGen physics model.**
*A user arrives with an idea. They leave with a short-list they understand, and a record the next person can find.*

---

## 0. Why this document exists

`docs/implemementation plans - complete/PRD_v1.md` specifies the **model and design-search
engine** — the physics, the sweep, the operating map, the comparison to experiment.
It says nothing about how a person uses it.

The Design Studio is the layer above: study configs, topology families, scoring,
the workbook, and the UI. It was built across four phases (commits `d733f92`,
`4fa7e8c`, `99479bb`, `05eed3b`) with no design document. This PRD is that document,
written after the fact and extended to cover where it is going.

The existing `docs/design_studio_ui.md` remains valid as a *usage guide*. This is the
*design* doc.

---

## 1. The problem

The model can answer almost any question about a device. Getting it to answer the
question you actually have is the hard part.

Today, a designer with a question — *"can we make much larger droplets?"* — has to:
translate the question into geometry, hand-write a Cartesian sweep in YAML, know which
of three topology families is even relevant, run it, read a table of numbers, and
decide for themselves what "good" means. Then the result lives in a workspace folder
that nobody will find again.

Every one of those steps is a place where the physics stops being useful.

### The two entry paths that matter

**Path A — "I have a design question."**
> *"I want deep DFUs for large droplets. What's actually possible? Which design is
> best if I care about flat pressure? About throughput? About not running at
> 1000 mbar? What's the best all-round? What's safest to build first?"*

The user knows the *intent*, not the geometry. They should be able to state the intent
and constraints, and be handed a scored short-list with the reasoning visible.

**Path B — "I have a new design idea."**
> *"What if we tried this topology? Does it beat what we have — on everything, or just
> on some things?"*

The user has a new template. They should be able to drop it in, run the **house-standard
study** (fixed fluids, footprint, fab caps, scoring), and get a diff against the
incumbents on every value axis. No bespoke analysis script.

Both paths must end in the same place: **a chapter in the book**, so the answer is
still there in six months.

---

## 2. Users & jobs-to-be-done

**Primary user:** the device designer (currently: us).

| JTBD | What they say | What the Studio must do |
|---|---|---|
| Explore a design intent | "Can we do deep DFUs?" | Turn intent + constraints into a solved, scored design space |
| Rank by what they care about | "Best flatness? Best throughput? Lowest pressure?" | Per-axis winners, a Pareto set, and a defensible all-round pick |
| Understand the blocker | "Why is nothing green?" | Name the binding constraint and price relaxing it |
| Judge risk before building | "Which is safest to try first?" | Margin from failure, weighted by how much we trust each number |
| Test a new topology | "Is this comb idea better?" | House-standard run + diff vs incumbents |
| Probe where the model breaks | "Where does step-emulsification stop working?" | Boundary-probe studies that generate calibration data |
| Not repeat themselves | "Have we looked at this before?" | Prior-art check against the book *before* running |
| See what they designed | "What does 10 arms actually look like?" | To-scale schematic, whole device and zoomed DFU group |
| Get it built | "Make this one." | Export a device spec to the layout pipeline |

---

## 3. Core concepts

These are the nouns. Everything else is implementation.

**Study** — one YAML file describing a question. Any leaf may be a scalar (fixed) or a
list (swept); lists Cartesian-expand. `family:` is itself sweepable, so a single device
is "a sweep of one". This primitive is correct and stays.

**Family** — a topology style (serpentine, radial, manifold, …) implementing the
`Family` contract: `compile()`, `solve()`, `applicable_metrics()`. Adding a topology
means adding a family, not forking the pipeline.

**Common contract (`CommonMetrics`)** — the comparable result every family fills.
Fields a family genuinely cannot compute are `None`, which renders **grey / N-A** and is
excluded from the verdict. This is what lets a radial wheel and a comb manifold sit in
one table honestly — a radial array has no ΔP-uniformity axis because flatness is
automatic, and the table says so rather than inventing a number.

**Scoring** — declarative green / orange / red thresholds per metric, plus hard build
gates. **Worst-category-wins**, with a reason chip for every non-green. No hidden
weighting, no magic score.

**Value axis** — a dimension the user might optimise for: flatness, throughput, drive
pressure, margin, area. A study has *several*, not one. (§5.)

**Margin** — how far a design sits from failing, as a fraction of the green→red span.
The honesty column. (§6.)

**Chapter** — one study's self-contained result: scored table, plots, schematic,
provenance, verbatim config, git hash. An HTML file plus a JSON sidecar.

**Book** — every chapter, indexed and searchable. The institutional memory. (§8.)

---

## 4. Architecture

```
                    ┌─────────────────────────────────┐
   intent  ───────► │  INTENT LAYER                   │  "I want 140 µm droplets
   constraints      │  intent → generated study grid  │   under 300 mbar"
                    └──────────────┬──────────────────┘
                                   ▼
                    ┌─────────────────────────────────┐
   study.yaml ─────►│  STUDY  (Cartesian expansion)   │
                    └──────────────┬──────────────────┘
                                   ▼
                    ┌─────────────────────────────────┐
                    │  FAMILIES  (topology contract)  │  serpentine │ radial │ manifold
                    │  compile → solve → CommonMetrics│
                    └──────────────┬──────────────────┘
                                   ▼
                    ┌─────────────────────────────────┐
                    │  PHYSICS  (untouched)           │  stage_wise_v3, nodal_network
                    └──────────────┬──────────────────┘
                                   ▼
                    ┌─────────────────────────────────┐
                    │  SCORING  → verdict + margin    │
                    │  RANKING  → per-axis, Pareto,   │
                    │             all-round, safest   │
                    │  DIAGNOSIS → binding constraint │
                    └──────────────┬──────────────────┘
                                   ▼
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
  ┌───────────┐            ┌──────────────┐          ┌────────────────┐
  │ WORKBOOK  │◄──────────►│  STUDIO UI   │          │  GDS HANDOFF   │
  │  chapter  │  compare   │  (live)      │          │  device spec   │
  │  + book   │            │              │          │  → gds-create  │
  └───────────┘            └──────────────┘          └────────────────┘
```

**Non-negotiable invariant:** the UI is a *skin*. Batch (`stepgen study`) and interactive
(`stepgen studio-ui`) run the identical pipeline and produce identical numbers. There is
never a second model. This holds today and must keep holding.

**Physics is untouched.** The Studio composes existing solvers behind the family
contract. A Studio change is never a physics change.

---

## 5. The decision model — value axes, not one goal

**Current state:** `goal:` is a single word (`flatness` | `throughput`) and ranking is a
two-tuple `(traffic-light category, one metric)`. Everything else the user cares about is
invisible to the ranking.

**Target state:** a study declares several value axes. The output is not one winner but a
**decision panel**:

| Output | Question it answers |
|---|---|
| Per-axis winner | "Flattest? Highest throughput? Lowest drive pressure? Smallest area?" |
| Pareto set | "Which designs aren't beaten on everything by something else?" |
| All-round pick | "Best combination" — explicit, user-settable weights |
| **Safest pick** | "Best margin from failure, weighted by model confidence" |

Rules:

- **Weights are visible and editable.** A composite score whose weights are hidden is a
  worse tool than no composite score. The UI shows the sliders; the chapter records the
  weights used.
- **Per-axis winners always shown, even when a composite is requested.** Knowing that the
  flattest design is a different device from the highest-throughput one *is* the finding.
- **The Pareto set is the honest answer** when axes genuinely trade off. Say so rather
  than collapsing it.
- `_pareto_front()` already exists in `viz/plots.py` from the legacy sweep path. Lift it,
  don't rewrite it.

---

## 6. Margin and model confidence — the honesty layer

*This supersedes an earlier proposal to score robustness against fabrication drift.*
Device dimensions do not meaningfully drift; **the model may be off**. That is the risk
worth scoring.

A design that scores green but sits 5% above the red threshold is not the same design as
one sitting 200% above it — but today's table shows both as a green cell. If the model is
slightly optimistic, the first is built exactly to spec and does not work.

### Margin

For every graded metric, compute the distance from the red boundary as a fraction of the
green→red span, and report it alongside the traffic light:

```
ΔP flatness   12%   🟢  (margin 78% — comfortable)
Exit Ca      0.028  🟢  (margin  4% — marginal ⚠)
```

A row's margin is the **minimum** across its applicable metrics — the weakest link. Sorting
by it gives the "safest to try" ranking directly.

### Model confidence

Not all metrics deserve equal trust, and pretending otherwise is the failure mode this
layer exists to prevent. Each metric carries a confidence tier:

| Tier | Meaning | Example |
|---|---|---|
| `validated` | Compared against experiment, agreement established | Stage-1 refill hydraulics, ΔP distribution |
| `calibrated` | Empirical fit, in-range | Droplet size `D = k·w^a·h^b` within fitted geometry |
| `extrapolation` | Model runs, but outside where it has been checked | Stage-2 frequency for deep exits; **any Ca above the measured envelope** |

**The tier follows what we have measured, not what we have read.** *Added 2026-07-29.* The
obvious implementation grades `regime_Ca` as `calibrated` below the SE ceiling and
`extrapolation` above it. That is wrong, because the ceiling is itself borrowed: computing the
exit Ca actually reached in the only Peak dataset that measures it gives **≤ 0.0017**, nine
times below the 0.0125 green bound. Everything between those two numbers is a region we score
confidently and have never visited. `families.base.CA_MEASURED_MAX` records the boundary and
the tier follows it. The general rule: **a confidence tier must be pinned to a measurement,
and if nobody can name the measurement the tier is decoration.**

Margin is discounted by tier. A generous margin on an `extrapolation` metric is not
reassurance. Where a design's verdict depends on an extrapolated quantity, the chapter
says so in plain language rather than burying it.

**Concrete case this fixes:** the deep-DFU throughput advantage (~166× oil volume per
droplet at 50 µm depth) is explicitly an *upper bound* — Stage-2 formation frequency for
deep exits is not modelled. Today, throughput ranking silently compares a solid number for
shallow DFUs against an optimistic one for deep DFUs. Under this layer, that comparison
carries its own warning.

### Validity gate

Add `validity` as a scored gate: capillary number against the step-emulsification ceiling,
viscosity ratio λ against the validated envelope, aspect ratios against fitted range.
Outside the envelope → hard orange, never green, with an "extrapolation — model not
validated here" chip.

**This is also a correctness fix.** `configs/study_all_families.yaml` currently scores
`regime_Ca: { green: 0.01, orange: 0.3 }`. The wiki-grounded SE→jetting ceiling used in
`comp_large_dfu_stage1_screen` is **0.0125–0.03**. The current orange bound is an order of
magnitude too permissive — the scorer will return green deep-DFU designs that are outside
step-emulsification entirely, which is precisely the regime where the droplet-size
prediction stops holding.

### Evidence-thin gates — "green apart from Ca"

*Added 2026-07-29, after Phase 2 found this was the common case, not an edge case.*

A row can fail for two very different reasons, and collapsing them loses the thing the user
most needs to know:

- **It does not fit the die.** Computable, certain, and no amount of trying will change it.
- **Our weakest theory says the exit Ca is too high.** A threshold borrowed from literature at
  λ ≈ 1 while we run at λ ≈ 0.015, and one no Peak device has come within 9× of.

The second is not a failure. It is a design sitting somewhere we have never looked.

**The rule the Studio follows:**

1. **The verdict does not soften.** Worst-category-wins still reds the row. Quietly
   downgrading an unmeasured risk to green would be worse than having no verdict, because it
   would launder ignorance as confidence — exactly the failure §6 exists to prevent.
2. **The distinction is named.** `diagnosis.EVIDENCE_THIN_GATES` lists the gates that rest on
   thin evidence (today: `regime_Ca` alone). A row red *only* on those is reported in the
   chapter, the UI and the CLI as a **build-and-see candidate**, with the reason stated.
3. **The call is the user's.** Whether an unmeasured threshold is worth respecting is a
   judgement about appetite for risk and cost of a wafer. The scorer is not the right place to
   make it, and the honest output is "this passes everything we can check, and here is the one
   thing we cannot" — not a verdict that pretends to more than it knows.
4. **Membership of the list is a claim, and must be earned.** A gate goes in only when the gap
   between what we score and what we have measured has actually been computed. `regime_Ca` is
   there because that computation was done and written down; nothing else is there yet.

This is the mechanism by which an unmeasured boundary stops being a wall and becomes an
experiment — which is what §7 is for.

---

## 7. Boundary-probe studies — designing to learn

Ranking finds the best device. It does not tell you which devices to *build first*, and
those are different questions.

Where the model is uncertain, the most valuable wafer is not four copies of the predicted
winner — it is a set of designs that **straddle a predicted boundary**, so the result tells
you which way the physics actually goes.

**The immediate case: the step-emulsification ceiling.** Take one DFU geometry and walk it
across the predicted SE→jetting boundary. Where does droplet size stay geometry-set and
Ca-independent, and where does it start tracking flow rate? That experiment:

1. locates the real boundary for *our* fluid system, rather than one borrowed from
   literature at λ ≈ 1 when we run at λ ≈ 0.015;
2. constrains the constants we currently assume — effective interfacial tension and
   contact angle — which propagate into every future prediction;
3. converts the largest open risk on deep DFUs from a caveat into a number.

So the Studio needs a **probe study** mode: given a boundary the model predicts, select the
design points that most sharply discriminate across it, and mark them as a build set. The
output is a wafer manifest, not a ranking.

This closes the design → experiment → model loop that `vision.md` describes and the current
tooling does not implement.

**Priority raised, 2026-07-29.** This section was written as "the immediate case" among
several. Phase 2 established it is the *only* case that currently matters: exit Ca is the
binding constraint on every large-droplet design, 87 of 216 generated deep-DFU designs are red
on it alone, and the highest Ca ever measured on a Peak device is nine times below the
threshold those verdicts turn on. Until that boundary is measured, every deep-DFU decision is
an opinion with a decimal point on it. The concrete probe — two crossed geometry lines, `dD/dQ`
readout, short arrays, a 30×10 control — is designed in the roadmap's Phase 5.

Two inputs must be pinned alongside it, both surfaced by the same audit: **interfacial
tension** (configs in this repo disagree 3×, and Ca scales inversely with γ) and the
**dispersed-phase identity** of the anchor experiment (disputed between sunflower and silicone
oil; µ differs up to 10×, and Ca scales with µ). The probe measures `Ca_crit` with both folded
in, which is the right unit for *design* — Po and geometry are what you control — but not for
exporting the result to another fluid system.

---

## 8. The workbook as institutional memory

The book is not an export format. It is the point.

Every study run — including the ones that went nowhere — becomes a chapter carrying its
verbatim config, model git hash, resolved constants, timestamp, and author. That already
works. What is missing is everything that makes it *findable and reusable*.

### Prior-art check — before you run

When a user assembles a study, the Studio searches the book for prior work in the same
region of design space and surfaces it **before** the run, with three actions:

- **(a) Continue anyway** — the prior work doesn't cover this, proceed.
- **(b) Reuse** — this has been answered; open that chapter instead of burning the run.
- **(c) Compare against** — run it, and overlay the prior chapter's rows on the results.

Option (c) is largely built: `reference: { kind: chapter }` already resolves another
chapter's rows and overlays them on the plots. It needs an index to search and a
tick-from-dropdown picker in the UI instead of a hand-written YAML path.

### What a chapter must record

Provenance answers *what* and *when*. The book also needs *who*, *why*, and *how to reuse*:

| Field | Purpose |
|---|---|
| `question` | The one-line question this study was run to answer |
| `author`, `date` | Who to ask |
| `tags` | Topology, regime, droplet size band, intent |
| `finding` | One-line conclusion, written after the run |
| `supersedes` / `builds_on` | Chapter lineage |
| `status` | exploratory / decision-grade / superseded |

### Registry

A `book/registry.json` keyed on (config hash, model git hash) makes "have we run this
before" exact rather than fuzzy, and makes it visible when a chapter's result predates a
model change that would alter it. A chapter computed on old physics should say so.

---

## 9. Design visualiser

A scored table tells you a manifold with 10 arms wins. It does not tell you what that
*is*, and a designer cannot sanity-check a device they cannot see.

Every family renders its own to-scale schematic from the same compiled config the solver
used — so the picture and the numbers cannot disagree:

**Whole-device view** — the topology at scale within the die square: manifold spine with
its arms and the zones where DFUs sit; radial hub with spokes; serpentine lanes and turns.
Footprint usage visible at a glance.

**Zoomed DFU group** — a handful of adjacent DFUs at true scale with real dimensions and
spacings called out: rung length, upstream width, exit width and depth, pitch, wall and
continuous-phase gaps. This is the view that makes a packing model believable — and the
manifold packing model was recently corrected by ~10–20× on DFU count, which a to-scale
drawing would have caught immediately.

Requirements:

- `render_schematic()` on the `Family` contract, so a new topology draws itself.
- **Inline SVG**, not raster — the chapter must stay self-contained with no external
  requests, and SVG stays readable when zoomed.
- Rendered from the *compiled* config, never from a separate parallel description.
- `viz/plots.py::plot_layout_schematic` already does this for serpentine — that is the
  precedent to generalise.

---

## 10. GDS handoff

**This supersedes PRD_v1's "Non-goal: CAD/GDS mask generation."** Not because the Studio
should generate masks — it should not — but because the decision tree currently dead-ends
at an HTML file, and the gap between "we picked this design" and "we drew this design" is
manual re-entry of every dimension.

The boundary: the Studio exports a **normalised device spec** (JSON — every dimension
resolved, in SI, with the chapter and config hash that produced it). `gds-create` consumes
that spec and owns everything about layout, layers and mask rules.

One rule: the spec must carry the provenance of the chapter it came from, so any fabricated
device can be traced back to the study that chose it.

---

## 11. Non-goals

- **Not a CFD solver.** Reduced-order, as PRD_v1 states.
- **Not a mask generator.** Exports a spec; `gds-create` owns layout.
- **Not a second physics model.** The Studio composes existing solvers; if a number is
  wrong, it is wrong in the model, not here.
- **Not a general optimiser.** Sweeps, screens and ranks a declared space. It does not do
  gradient-based or black-box optimisation over free geometry.
- **Not multi-user infrastructure.** File-based book, local runs, no server, no database.

---

## 12. Decision records

**DR-1 — The Studio is the platform; `stepgen_ui` and the `stepgen` integration repo are
superseded.**
Three overlapping UI efforts exist: `design_model/stepgen/studio/` (current, multi-family,
tested), `stepgen_ui` (Streamlit dashboard, one commit, mock data, serpentine-only), and
`stepgen` (integration layer converting UI dicts to the old single-family `DeviceConfig`).
The last is a dead end against a multi-topology contract. Port the genuinely valuable parts
of `stepgen_ui` — the experiment-overlay and operating-map pages, which the Studio lacks
entirely — into Studio tabs, then archive both repos with a pointer here.

**DR-2 — Margin replaces fabrication-drift robustness.**
Design dimensions are held accurately in fabrication; model error is the live risk. Score
distance-from-red discounted by model confidence. (§6.)

**DR-3 — GDS export is in scope, mask generation is not.** (§10.)

**DR-4 — Grey means grey.** A family that cannot compute a metric reports `None` and the
cell renders N-A. Never substitute a default, an estimate, or a zero to make a table look
complete.

---

## 13. Success criteria for v1

The Studio is v1-complete when a designer can, without writing Python:

1. State an intent ("deep DFUs, large droplets, under 300 mbar") and get a solved,
   scored design space across all three topology families.
2. See the best design by each value axis, the Pareto set, the all-round pick, and the
   safest pick — with the weights visible.
3. Be told what the binding constraint is, and what relaxing it would buy.
4. See any candidate drawn to scale, whole-device and zoomed.
5. Be warned when a verdict rests on an extrapolated quantity.
6. Be shown relevant prior chapters before running, and tick any of them for comparison.
7. Export the chosen design to `gds-create`.
8. Have the whole thing land in the book, findable by the next person.

---

*Roadmap and phasing: `roadmap_studio_v1.md`.*
*Usage guide for the current app: `../design_studio_ui.md`.*
