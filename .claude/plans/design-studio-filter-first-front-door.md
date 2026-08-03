# Design Studio — the filter-first front door (revised Phase 6)

**Date**: 2026-08-03
**Supersedes**: Phase 6 ("Form-driven UI") in `docs/06_design_studio/roadmap_studio_v1.md`
**Status**: planned, not started
**Derived from**: a `/grill-me` session with Conor, 2026-08-03

---

## The pivot

Phase 6 as written assumed the user composes a bespoke study per question, and that the
job was to replace the raw-YAML sidebar with a form that writes `intent:`.

That is not how the user works. The actual loop is:

> Run one sweep. Filter the results with constraints. Sort by what I care about. Get
> "the best design we ran that meets those requirements". Then optionally refine around
> the designs I liked.

This is a **better architecture**, and it was the user's proposal, not a compromise:

1. **It dissolves the grid-bias trap.** The roadmap's own bolded lesson —
   *"a generated grid inherits the bias of whatever it was sized against"* (the Ca-blind
   grid, Phase 2) — only exists because grids are generated *from a target*. A broad sweep
   is sized against nothing, so there is nothing to inherit.
2. **Every stated constraint is already post-hoc.** ΔP spread, area used, pressure,
   throughput, Ca are all fields on a solved row. None of them need to change what is
   solved.
3. **Thresholds become views, not gates.** Changing 15% → 10% costs zero re-runs.
4. **It shrinks the LLM to nothing.** No model is needed to pick sweep ranges, which was
   the single highest-risk thing about an LLM writing configs.

### Consequences for decisions already taken

- Extending the `intent:` vocabulary (pinned exit, ΔP bar) is **no longer needed** —
  those become filters, not grid generators. No physics-layer change.
- The **LLM helper is OUT for v1.** With exits locked, one family, and levels from
  defaults, the form is ~8 fields. Revisit only if the form proves painful.
- **Exit geometry is locked per study, never swept.** User's call; it is also the one
  axis that could not have been a post-hoc filter, since it changes the physics per point.

---

## Decisions locked (grill-me, 2026-08-03)

| # | Decision | Choice |
|---|---|---|
| 1 | What runs the solve | Local server, `stepgen studio-serve` (FastAPI) |
| 2 | Server scope at v1 | Front door + live schematic preview; Streamlit untouched |
| 3 | How the form sets sweep levels | Locked values + coarse/fine dial; levels from checked-in house defaults; live point count + time |
| 4 | Fate of traffic-light verdicts | Keep as the default view; every gate live and demotable to "show, don't gate" |
| 5 | What is the durable record | Sweep = the chapter (immutable). Filter views = lightweight saved pointers. Refine = new chapter with parent lineage |
| 6 | Empty filter results | Show swept range on every control; warn when a threshold is outside it; offer to extend that axis and run only the new points |
| 7 | DFU count | **Derived** from `packing_capacity()` × a fill-fraction axis, not swept |
| 8 | Area model | One calibrated `usable_area_fraction`; no explicit port/border geometry in the solver |
| 9 | Bend radius / wall-at-turn | **Reported, not gated** — same treatment as Ca, until a real fab minimum exists |

### Why 7 and 8 matter most

The user's critique: area was being *derived from N*, when physically the die is fixed and
geometry determines how many DFUs fit. Doubling the main width should **cost you DFUs**;
in the current sweep it merely grows the device until `fits_square` flips false.

`Family.packing_capacity(compiled)` already exists (Phase 3) and answers exactly this —
it reports serpentine 1,000 used / 5,445 capacity at V5 defaults. It simply was not the
axis being swept.

Deriving N also makes sweeps **~5× smaller**, since N stops being a 5-level axis.

---

## Evidence gathered during the session

Measured, not assumed:

- **Solve cost: ~19 ms/point.** 1,368 points in ~26 s. A realistic serpentine-only sweep
  with exits locked is 2,880 points ≈ **55 s** — not the 35 min figure that came from
  (wrongly) sweeping exits × 3 families.
- **Rule to surface in the UI**: adding an axis with k levels multiplies runtime by k.
- **Area does respond to main width** — at N=500, 1 mm rungs: 6.5 → 7.5 → 8.5 → 9.5 cm²
  across main widths 500 → 2000 µm. So the layout model is not naive; it is *inverted*
  for the user's purpose.
- **Nothing in a 1,152-row serpentine sweep exceeded 50.5 cm² of a 100 cm² die**, and the
  flattest design meeting ΔP ≤ 15% used only 31.5 cm². Filtering for "≥ 90 cm²" returns
  zero rows — **not because it is impossible, but because N was capped at 4,000.** This is
  the motivating case for decision 6.

---

## Batch 1 — the small fixes (ready to run cold)

Five self-contained changes. No dependencies between them; none touch the Studio
architecture. Do these first — B3 is a correctness bug, the rest unblock comfortable use.

Run before starting, to have a baseline:
```
pytest -q
```
Known pre-existing failures at `306a4bc`: **5** (3 `test_cli` png, 2 `test_design_search`) —
verified identical in a clean worktree at `a1a23d3`, so do not chase them.

---

### B3 — two resistance implementations disagree on the same guard *(correctness — do first)*

**The bug.** There are two rectangular-resistance functions applying the same
`1 − 0.63·(h/w)` correction, with **different validity guards**:

| Location | Guard | Rejects |
|---|---|---|
| `stepgen/models/resistance.py:49-54` (serpentine path) | `denom <= 0` | only `h/w ≥ 1.587` |
| `stepgen/families/manifold.py:116-124` (`_R_rect`) | `0 < h < w` | any `h ≥ w` |

So for `1.0 ≤ h/w < 1.587` the **same geometry is a hard error in manifold and a silently
wrong number in serpentine.** The correction factor is being applied outside the range it
is valid for, and it inflates resistance sharply as it approaches zero — at `h/w = 1.33`
(a 15 µm-wide rung at 20 µm exit depth, which is a config a user would plausibly write),
`denom = 0.16`, so resistance comes out **~6× too high** with no warning.

**Fix.** Make `resistance.py` reject `h >= w` for the corrected form, matching manifold's
guard, and have `manifold._R_rect` delegate to `resistance.hydraulic_resistance_rectangular`
so there is one implementation of the rule. (Precedent: Phase 1 did exactly this for the
Pareto rule — `viz/plots.py::_pareto_front` now delegates to `ranking.pareto_mask`.)

**Verify.**
```
pytest tests/ -q -k "resist or manifold"
pytest -q          # expect the same 5 pre-existing failures, no new ones
```
Also confirm the failure is loud, not silent:
```
python -c "from stepgen.models.resistance import hydraulic_resistance_rectangular as R; R(1e-3,15e-6,20e-6,0.06)"
```
should raise, not return a number.

**Note on already-reported results.** The `study_dp15_1000mbar_60x20` run used upstream
widths 25 and 40 µm against a 20 µm exit (`h/w` = 0.8 and 0.5) — both inside the valid
range, so **those numbers are unaffected.**

---

### B2 — manifold fails deep in the solve instead of at compile

**Symptom.** `upstream_width_um: 15` with `exit_depth_um: 20` produces
`rectangular resistance needs 0 < depth < width; got w=15.0µm, h=20.0µm` — raised per
point during `solve()`, so a 108-point family reports 108 identical errors and the study
still "succeeds". Cost this session: a full 684-point run wasted.

**Fix.** Validate in `ManifoldFamily.compile()` (`stepgen/families/manifold.py`, after
`upstream_w` is read at **line 290**) that `upstream_w > exit_d`, raising a message that
names the *config fields* rather than the internal variables — the rung depth equals the
exit depth by construction (single etch), so the actionable advice is "raise
`rung.upstream_width_um` above `junction.exit_depth_um`".

**Verify.** A study with `upstream_width_um: 15`, `exit_depth_um: 20` should fail once,
at load/compile, naming both YAML fields.

---

### B1 — `stepgen study` crashes on Windows printing its own diagnosis

**Symptom.** `UnicodeEncodeError: 'charmap' codec can't encode character 'Δ'` at
`stepgen/cli.py:514` (`print(f"  {line}")` in `_cmd_study`, printing the diagnosis
headline, which contains `ΔP`). The study **completes and writes its chapter**, then dies
on the summary — worst possible ordering. `µ` survives because it exists in cp1252; `Δ`
does not.

**Fix.** At the top of `main()` (`stepgen/cli.py:966`), before dispatch:
`sys.stdout`/`sys.stderr` `.reconfigure(encoding="utf-8", errors="replace")`, guarded for
streams that do not support it (redirected/piped output). `errors="replace"` matters — the
goal is that console output can never kill a completed run.

**Verify.**
```
python -m stepgen.cli study configs/study_dp15_1000mbar_60x20.yaml --diagnose always
```
must complete without `PYTHONIOENCODING=utf-8` set.

---

### A4a — γ is missing from the sidecar *(blocks cross-study filtering)*

**Why it matters.** γ is set per study in `fluids:`, varies **3× across this repo's
configs** (5 / 15 / 0 mN/m), and `Ca ∝ 1/γ`. Pooling rows from two chapters would silently
mix Ca computed on different constants — a wrong answer with no visible symptom.

**Fix.** In `_chapter_json()` (`stepgen/studio/workbook.py:991`) add a top-level `fluids`
key from `result.study.raw.get("fluids", {})`. Note `StudyPoint` carries `fluids`
per point, so if any point disagrees with the study-level block, record that rather than
assuming uniformity.

**Verify.** `book/<chapter>.json` contains `fluids.gamma`.

---

### A4b — per-cell margins are missing from the sidecar

**Why it matters.** `ScoredRow` stores `min_margin` but not per-metric margins.
`CellScore.margin` (`scoring.py:96`) is exactly "distance past the ceiling", deliberately
uncapped — it is what the planned **Ca-distance column** displays.

**Fix.** In the same row dict in `_chapter_json`, add
`"margins": {k: c.margin for k, c in sr.cells.items() if c.category != "grey"}`,
mirroring the existing `confidence` block immediately above it.

**Verify.** `rows[0].margins.regime_Ca` is a number in the sidecar.

---

## Work plan (the main build)

### A. Model foundations — must land before the UI is trustworthy

- **A1. `usable_area_fraction`** on `FootprintConfig`. One number, applied to the die
  before packing. **Calibrated, not guessed**: solve it so the packing model reproduces
  the real V5-30 — 11,550 DFUs on a 63.5 mm die. Precedent:
  `comp_deep_dfu_v5_main_mods` calibrated its 41.6 cm² area budget the same way.
  Ports, borders and inlet/outlet real estate stay a *drawing* concern for the Phase 3
  schematic — deliberately not modelled numerically.
- **A2. N from packing.** Grid generation calls `packing_capacity()` per geometry;
  a `fill_fraction` axis (100/75/50/25 %) sets how much of that capacity is used.
  **This changes results** — every number produced before this lands is superseded.
- **A3. Bend radius + wall-at-turn** as `CommonMetrics` fields, reported with no
  threshold. Note the existing tangle: today `lane_pitch = lane_pair_width + 2×turn_radius`
  treats turn radius as a free input that *adds* to pitch, whereas for a real 180° fold the
  centreline radius is ≈ half the lane pitch. Phase 3 already lists the missing bend-radius
  floor as a known MVP limit.
- **A4. Sidecar completeness** — done in Batch 1 (A4a γ, A4b per-cell margins).

### C. The server

- **C1.** `stepgen studio-serve` — FastAPI + uvicorn (both already installed; only
  `streamlit` is declared in `pyproject.toml`). Routes: form page, `POST /run` (solve →
  `write_workbook()` → chapter), `POST /preview` (compile only, ~1–4 ms, no solve).
- **C2.** The form: locked values (exit geometry, family, die size, pressure ceiling) +
  coarse/fine dial + live point count and time estimate. `len(study.points)` is known
  before any solving, so the estimate is exact on count and calibrated per family on time.
- **C3.** House sweep-level defaults as a checked-in, reviewable file — shown read-only in
  the form so nothing is hidden, with an "adjust axes" expander for full control.

### D. The results explorer

- **D1.** Trimmed columnar table embedded in the page (~15 numeric fields) → client-side
  filtering and sorting, instant, no round-trip. Full detail fetched per row on click.
- **D2.** Gates panel — live thresholds; any gate demotable to "show, don't gate".
  The Ca case is already ~80% built: `CellScore.margin` is deliberately uncapped so it
  already *is* distance-past-ceiling; `theory_limited_rows()` already finds
  green-except-Ca designs; `ca_gamma_robustness()` already reports the γ at which each row
  would clear.
- **D3.** Swept-range display per control + out-of-range warning + "extend this axis"
  action that runs only the new points.
- **D4.** Row click → detail panel + Phase 3 schematic.

### E. Provenance

- **E1.** Sweep → chapter, reusing `write_workbook()` unchanged.
- **E2.** Filter views as small saved JSON (thresholds, sort, demoted gates, starred rows),
  shareable as a URL.
- **E3.** Refine sweep → new chapter recording parent chapter + the starred designs it was
  built around.

### Sequencing

`Batch 1 → A1/A2/A3 → C → D → E`.

Batch 1 is self-contained and safe to run cold — start there. **A2 (N from packing) is the
highest-risk item**, because it changes what the numbers mean: every result produced before
it lands, including `study_dp15_1000mbar_60x20`, is superseded by it. C/D/E are additive
and touch no physics.

---

## Explicitly deferred

- **LLM config helper.** Out for v1 (decision above). If it returns, the safe job is
  translating a request into a *filter/sort expression* — a view over computed data, wrong
  answers instantly visible and free to fix — never into sweep ranges.
- **Cross-study pooling.** Blocked on A4 (γ in the sidecar).
- **Full layout rebuild** — turn radius constraining lane count, fold arc as real channel
  with its own pressure drop. Documented Phase 3 inventions; a physics-layer job, not a
  UI one.
- **Streamlit retirement.** `ui.py` (936 lines) left untouched at v1. Revisit once
  `studio-serve` reaches parity on the live behaviours (weight sliders, layout preview).

---

## Open questions

1. **Sort semantics** — user said "primary goal for now, maybe secondary later". A single
   sort column is v1; the existing `decide:` layer (per-axis winners, Pareto, composite)
   remains available in the chapter and may be the better home for multi-objective work.
2. **What the calibrated `usable_area_fraction` actually comes out as.** If reproducing
   V5-30 requires a physically implausible fraction, that is a finding about the layout
   model, not a constant to accept.
3. **Whether "fill the die while holding ΔP ≤ 15%" is achievable at all.** Current
   evidence is discouraging (best filling design at ΔP ≤ 15% used 31.5 cm²; by N = 4,000
   the flattest was already 16.5%) but the sweep stops at N = 4,000, so this is a
   hypothesis, not a result. A2 is what will answer it properly.

---

# Addendum — carried in from the design-comparison session (2026-08-03)

**Added**: 2026-08-03, second session. **Status of the plan above**: unchanged and still
correct; nothing here contradicts a locked decision except **B5**, which is flagged.

Context: a session on comparing *already-committed* designs (four DFU exit geometries, a
pinned ladder, swept pressure and fluid system) produced four commits of model work plus a
CLI runner. That work is **prerequisite to the form** — the front door would otherwise
expose a Stage-1 number that is 2–4× wrong and a Ca gate that does not exist yet.

## Landed on `fix/stage1-reset-length-and-cycle-metrics` — merge before building C

Branched from `306a4bc`. Full suite: **494 passed, same 5 pre-existing failures**, verified
by stashing. Not pushed.

| Commit | What |
|---|---|
| `9c06ef2` | Stage-1 reset length `sqrt(w·h)` + use the network rung flow; new cycle metrics |
| `50cb149` | Ca-gated operating ceiling (`ca_limited_operating_point`, `ca_gated_summary`) |
| `5a02f5e` | `scripts/compare_designs.py` + `configs/study_my_designs.yaml` |
| `b8dc329` | Labels must show exit geometry and fluid system |

`CommonMetrics` gained: `dP_rung_mbar`, `t_stage1_s`, `t_cycle_s`, `stage1_fraction`,
`Po_min_production_mbar`. All derive from the **one** network rung flow, so they cannot
disagree with `throughput_mlhr` or with each other. `t_cycle_s == 1/frequency_hz` to 1e-16
by construction.

**Validation anchor** (`experimental_workspaces/po_sweep/data/stage_timings.csv`, V5-8-1,
30×10 µm exit, SO/2% SDS): Stage-1 time now −2% at 200 and 300 mbar (was +112%), degrading
to +33% at 800 mbar where Stage 1 is only ~5 video frames. Cycle time matches to ~6% with
**no pressure drift** — `t_cycle ∝ 1/Q` holds to 0.2% across a 4× pressure range.

---

## B4 — the fluid-system control *(new Batch 1 item; small and exact)*

**The requirement, in full**: set o/w vs w/o, or set the viscosity of fluid A and fluid B.
Nothing more. No fluid library, no phase-property model.

**The trap this must not fall into.** Sweeping the viscosities as independent lists
Cartesian-products them:

```yaml
fluids:
  mu_dispersed:  [0.06, 0.00089]     # WRONG
  mu_continuous: [0.00089, 0.06]     # -> lambda = 0.015, 1.0, 1.0, 67.4
```

Half the resulting points are fluids that do not exist (mu_d = mu_c = 0.06). Verified: a
4-exit x fluid-swap study produced 64 points where 32 were physical.

**The correct emission** — `fluids:` as a list of *whole blocks*, which the expander
already concatenates rather than crosses (same mechanism as a list of designs):

```yaml
fluids:
  - { mu_dispersed: 0.06,    mu_continuous: 0.00089, gamma: 0.005, phase_system: o/w }
  - { mu_dispersed: 0.00089, mu_continuous: 0.06,    gamma: 0.005, phase_system: w/o }
```

**Form shape.** One repeater, "fluid system", each entry four fields (phase, mu_A, mu_B,
gamma). A "swap A/B" button writes the mirrored entry. Emits the list form above. **No
physics-layer change is required** — `serpentine.compile()` already reads `phase_system`,
`mu_dispersed`, `mu_continuous` from the fluids block
(`stepgen/families/serpentine.py:194-198`).

**Verify.** Two fluid entries x four exits x two pressures => 16 points, 16 distinct labels,
`lambda_visc` taking exactly two values (not four).

---

## B5 — exit geometry: decision 4 conflicts with a real job *(needs a call)*

Decision 4 locks exit geometry per study, never swept — sound, since the exit changes the
physics per point and it is the one axis that could not have been a post-hoc filter.

But the motivating job of this session was **"four DFU exit designs, everything else
fixed"**. Under decision 4 that is four studies joined by hand.

**This already works in the pipeline** — `serpentine:` as a list of whole design blocks
gives four intact designs with no Cartesian blowup, and `b8dc329` makes their labels
distinct. So the constraint would be a *form* constraint, not a model one.

**Recommendation**: keep exits out of the coarse/fine dial (they must never multiply with
the geometry axes), but allow an explicit **small named set** — "compare these 4 exits" as
a first-class control that emits the list-of-designs form. The grid-bias argument does not
apply: an enumerated set the user typed is not a generated grid.

---

## D5 — the Ca gate as a filter control *(extends D2; mostly built)*

Exit Ca rises with pressure, so the SE ceiling is an **upper bound on operating pressure**
and therefore a gate on throughput. The claimable number for a design is its throughput at
the highest in-regime pressure, not at max pressure.

`ca_gated_summary(frame, ca_max=..., gamma_ref=...)` **re-solves nothing** — `regime_Ca` is
a solved field and gamma enters as an exact 1/gamma, so moving the ceiling *and* moving
gamma are arithmetic on existing rows. It is a live slider by construction, matching
decision 4 ("thresholds become views, not gates"). Returns per design:

- `Po_gated_mbar` — highest *simulated* pressure that passes
- `throughput_gated` — what it makes there
- `Po_next_failed` — lowest simulated pressure that failed; **the gap is unsimulated
  headroom, not absent headroom.** Surface it, or coarse Po spacing silently costs
  throughput the design actually has.
- `passes_at_gamma_lo` — whether the verdict survives gamma = 3 mN/m

**Why the gate earns a place**: it *inverts rankings*. Two designs, 60x20 um exit, 1000
DFUs — ungated at 1000 mbar, main 200x1000 um makes 18.87 mL/hr against 4.35 for
100x500 um. Gated at Ca <= 0.0125, the wide main is capped at 200 mbar and makes **3.29**,
losing to the narrow main's 4.35. The wide main buys flow per DFU that it is not allowed to
use. Consistent with the deep-DFU finding that the in-regime answer is many slow DFUs.

**Non-negotiable for the UI**: `passes_at_gamma_lo` must sit *next to* the ceiling control,
not in a detail panel. In the example above **both** designs pass at gamma = 5 mN/m and
**both** fail at 3. On the exits this studio is being pointed at, the gate's verdict is
currently decided by a constant nobody has measured, and a bare green would read as a
physics result.

---

## D6 — new columns for the results table *(extends D1)*

Add to the ~15 numeric fields: `dP_rung_mbar`, `t_stage1_s`, `t_cycle_s`,
`Po_min_production_mbar`. Two carry caveats that must ship with them:

- **`stage1_fraction` is constant by construction.** It is the geometric ratio
  V_reset/V_drop, so the model reports one value at every pressure (0.63 for a 30x10 exit).
  Measurement gives 0.63 / 0.63 / 0.65 / 0.54 / 0.46 across 200->800 mbar. It is right where
  the data is well resolved and drifts at the top end, so it is a **diagnostic, not a
  guard** — it will not warn when snap-off starts eating the cycle.
- **`Po_min_production_mbar` costs ~40 solves** and is a property of the *design* at a given
  Qw, independent of the swept Po. Compute once per design, never per operating point.
  `solve_config` leaves it `None` unless `with_production_threshold=True`.

---

## A5 — a *third* resistance implementation *(extends B3)*

B3 unifies two rectangular-resistance functions that disagree on a validity guard. There is
a third pair, disagreeing on a value:

| Function | Model | V5-30 |
|---|---|---|
| `stage_wise_v3.stage1_physics.compute_rung_resistance` | full `mcl`, Shah & London | 2.697e18 Pa.s/m3 |
| `stepgen.models.hydraulics.rung_resistance` | `mcl x constriction_ratio`, different rectangular form | 2.155e18 Pa.s/m3 |

**25% apart on the same rung.** Stage 1 was silently modelling a rung the rest of the solve
did not have. `9c06ef2` fixes the *consequence* (Stage 1 now prefers the network flow it is
handed, rather than recomputing from its own resistance) but leaves both functions in place.

Fold into B3's scope: one rung-resistance implementation, one rectangular form, one guard.
Until then, any new consumer of `compute_rung_resistance` reintroduces the 25%.

---

## Open questions added

4. **C_visc recalibration is outstanding.** `stage1_viscosity_correction` was fitted
   2026-03-20 against timings that were corrected **x0.5** on 2026-06-08 (fps 25->50,
   `po_sweep/BRIEF.md`), which explicitly flagged that the calibration "may need
   revisiting". `stage1_physics.py` was last touched 2026-05-18, so it never was. The
   reset-length fix removes most of the resulting error but not the residual **+33% at
   800 mbar**, which is one-directional and unexplained. Candidates: stale C_visc, the
   disabled capillary back-pressure term, or Stage 1 being 5 frames at that pressure.
   Deserves its own workspace, not a constant nudged inside a UI build.
5. **Is Stage 3 a real capillary floor or a frame-rate artefact?** S2+S3 flatten above
   400 mbar, but there they are 2-3 frames at 50 fps and every value is an exact multiple
   of 0.02 s. If physical, per-DFU frequency saturates and conservation over-predicts at
   high pressure; if artefact, conservation holds. Current evidence favours artefact
   (`t_cycle` proportional to `1/Q` to 0.2% across 200-800 mbar), but it is unresolved and
   it is the one thing that would change how the throughput column should be read. Settling
   it needs a high-speed re-shoot at 400-1000 mbar, not more modelling.

---

## Decision 10 — a constraint on a value the USER PINNED is a report; a constraint on a value the TOOL CHOSE is a gate

**Added**: 2026-08-03, from a live run. **Status**: agreed, partially implemented.
**Generalises**: decision 9 (bend radius / wall-at-turn "reported, not gated").

### The bug that exposed it

`stepgen/studio/scoring.py` evaluated the `manufacturable` sub-gate unconditionally:

```python
evaluate = (required == "required") or (gate_key == "manufacturable" and val is not None)
```

Every other sub-gate is opt-in via `required`. This one was not, so a main depth the
user had **explicitly typed** (400 µm) sitting above the fab cap (200 µm) turned all
88 rows red. The run's verdict became a restatement of one config line, and the
diagnosis compounded it: it reported "within fab caps is the sole reason", then priced
relaxing the cap to 300 µm as *"nothing changes — this is not what is binding"*, which
is true and useless, because 300 is still below 400.

Fixed in `dd80c45` for this one gate. Verdicts went from 0 green / 0 orange / 88 red to
0 green / 22 orange / 66 red, and the diagnosis started naming ΔP flatness as the
binding constraint on 29 designs and finding 13 that pass everything except exit Ca.

### The rule

> A gate exists to stop the **tool** proposing something the user would not want.
> It does not exist to overrule a choice the user has already made.

- **Generated / swept value** outside a constraint → the search is proposing something
  unbuildable → **red**. This is the gate doing its job.
- **User-pinned value** outside a constraint → the user has decided → **report it, do
  not fail the row.** The tool's job is to say "this is outside the cap", not to bury
  the question that was actually asked.

The failure mode this prevents is specific and severe: **one veto masks every other
constraint.** A run where everything is red for a single known reason cannot tell you
what else is wrong, so the user learns nothing from a sweep they paid for.

### Why this is not just "make the gates optional"

Making every gate opt-in loses the protection on generated grids, which is where gates
earn their place — the intent layer really can propose a 500 µm-deep main and it really
should be stopped. The distinction has to be **per value**, not per gate.

### The machinery already exists and is unused

`stepgen/studio/intent.py` already records provenance per block:

```python
plan.user_supplied.append(block)     # came from the user's YAML
plan.generated.append(block)         # the intent layer invented it
```

Nothing consumes this at scoring time. `ScoredRow` has no idea which of its inputs the
user chose. That is the gap.

Note the two study shapes:
- **hand-written study** (no `intent:`) — *every* geometry value is user-supplied by
  definition, so essentially all geometry constraints should be reports
- **intent-generated study** — only the blocks in `plan.user_supplied` are pinned; the
  rest are the tool's proposals and stay gated

### Work item

1. Carry provenance to scoring. Either thread `Study.intent_plan` into `score_row`, or
   put a `pinned: set[str]` on the row. A hand-written study marks all geometry pinned.
2. Apply the rule uniformly to every sub-gate in the `build` composite
   (`fits_square`, `manufacturable`, `no_crossing`) and to the threshold gates that
   score a *geometric* quantity, not just `manufacturable` — that one was fixed
   individually in `dd80c45` and is currently the only one obeying the rule.
3. Keep the explicit override: `build: { manufacturable: required }` forces gating even
   on a pinned value, for the case where the user wants the cap enforced against their
   own numbers.
4. **UI consequence (feeds D2).** The gates panel needs three states, not two:
   *gate* / *report* / *off*, with pinned values defaulting to **report** and a visible
   marker saying why ("you set this"). Decision 4 already promises every gate is
   demotable to "show, don't gate"; this makes the default correct instead of relying on
   the user to notice and demote.
5. **Diagnosis consequence.** `diagnose()` must not price relaxing a constraint that
   only a *pinned* value breaches — that is what produced the "relax 200 → 300 µm:
   nothing changes" line. If the breach is pinned, the honest output is "you set depth
   to 400 µm, which is above the 200 µm cap", not a relaxation ladder that cannot reach.

### Test to write

A hand-written study whose geometry breaches every fab cap must still produce
non-red verdicts driven by the *physics* gates, and must name the breach in a chip. The
same study with `manufacturable: required` must go red. Neither currently has coverage —
`dd80c45` was verified by running the real config, not by a test.
