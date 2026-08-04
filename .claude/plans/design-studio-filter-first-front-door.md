# Design Studio — the filter-first front door

**Anchor**: `6db6405` (branch `fix/stage1-reset-length-and-cycle-metrics`, pushed)
**Baseline at anchor**: `pytest -q` → **531 passed, 5 failed, 5 skipped**. The 5 are
pre-existing (3 `test_cli` png, 2 `test_design_search`), verified unchanged from `306a4bc`.
Do not chase them.
**Supersedes**: Phase 6 ("Form-driven UI") in `docs/06_design_studio/roadmap_studio_v1.md`
**Status**: **Batch 1 complete** (B0 `e53ddc6`, B1 `e21798e`, A4a+A4b `39e7342`); W1-4
landed early (`77ac36a`). Wave 1 otherwise not started; Wave 2 not started. **Part of D
shipped early** — see "What landed ahead of the plan".
**Derived from**: `/grill-me` sessions with Conor, 2026-08-03 and 2026-08-04

> Rewritten 2026-08-04 and re-anchored `306a4bc` → `a0e82a1` → `6db6405`. Earlier vintages
> are in git history. Everything below is one vintage, verified against the tree at
> `912c74c`; `6db6405` landed during the review and changed no physics (see below).

---

## The pivot

The user does not compose a bespoke study per question. The actual loop is:

> Run one sweep. Filter the results with constraints. Sort by what I care about. Get
> "the best design we ran that meets those requirements". Then optionally refine around
> the designs I liked.

Why this is the better architecture:

1. **It dissolves the grid-bias trap.** The roadmap's bolded lesson — *"a generated grid
   inherits the bias of whatever it was sized against"* — only bites because grids are
   generated *from a target*. A broad sweep is sized against nothing.
2. **Every stated constraint is already post-hoc.** ΔP spread, area, pressure, throughput,
   Ca are all fields on a solved row. None need to change what is solved.
3. **Thresholds become views, not gates.** 15% → 10% costs zero re-runs.
4. **It shrinks the LLM to nothing.** No model picks sweep ranges — the single
   highest-risk thing about an LLM writing configs.

---

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| 1 | What runs the solve | Local server, `stepgen studio-serve` (FastAPI) — **scope reduced, see decision 12** |
| 2 | Server scope at v1 | Front door + live schematic preview; Streamlit untouched |
| 3 | How the form sets sweep levels | Locked values + coarse/fine dial; levels from checked-in house defaults; live point count + time |
| 4 | Exit geometry | Never a *generated axis*, but first-class members of the **design set**. See decision 11 |
| 5 | The durable record | Sweep = the chapter (immutable). Filter views = lightweight saved pointers. Refine/extend = child chapter with parent lineage |
| 6 | Empty filter results | Show swept range on every control; warn when a threshold is outside it; offer to extend that axis |
| 7 | DFU count | One of `rung.N` / `main.length_mm` / `rung.fill_fraction`, **mutually exclusive**. See W2-3 |
| 8 | Area model | Per-family `active_fraction`, measured from real devices. See W1-2 |
| 9 | Bend radius / wall-at-turn | Reported, not gated — until a real fab minimum exists |
| 10 | Pinned vs generated | A constraint on a value the **user pinned** is a *report*; on a value the **tool chose** it is a *gate* |
| 11 | Sets vs grids | A study is `design set × fluid set × swept axes`. Sets **concatenate**; axes **cross**. **Already implemented in the YAML layer** — see below |
| 12 | *(new)* Where filtering lives | The **chapter** filters client-side. `studio-serve` is the *front door only*: form, `POST /run`, `POST /preview`. D1/D2/D4 do not need it |

### Decision 10, in full

> A gate exists to stop the **tool** proposing something the user would not want.
> It does not exist to overrule a choice the user has already made.

- **Generated / swept value** outside a constraint → **red**. The gate doing its job.
- **User-pinned value** outside a constraint → **report it, do not fail the row.**

The failure mode this prevents is specific: **one veto masks every other constraint.** A
run where everything is red for one known reason cannot tell you what else is wrong.

**Correction to the previous vintage.** `dd80c45` did *not* fix this "for `manufacturable`
only". It made **all three** `build` sub-gates opt-in unconditionally — `scoring.py:326`
is `evaluate = (required == "required")` for `fits_square`, `manufacturable` and
`no_crossing` alike. That is a blunter rule than decision 10: not *report when pinned,
gate when generated*, but *off unless asked*. It carries a live regression:

> Only `manufacturable` emits the "⚪ outside fab caps — reported, not gated" chip
> (`scoring.py:328-331`). A **`fits_square` or `no_crossing` failure now passes with no
> chip at all** when the study omits `required`. `study_my_designs.yaml`,
> `study_template.yaml` and `study_serpentine_vs_radial.yaml` all omit `no_crossing` — so
> in the template a phase-crossing design is silently green.

Fixing that is W2-4, not a separate item. The provenance machinery already exists and is
still unused: `intent.py:153-155` records `plan.generated` / `plan.user_supplied` per
block; nothing consumes it at scoring time.

### Decision 11 is already built — this de-risks C2

`configs/study_my_designs.yaml` proves the engine is done: *"`serpentine:` is a LIST —
lists are concatenated, only dicts are Cartesian-producted."* A list of four design
blocks costs four points; a list of two `fluids:` blocks keeps A/B paired; `Po_mbar` as a
list crosses. `decide.group_by` names which axes make a row a different **device**.

So C2 is a **form over an existing data model**, not a new data model. Provenance for
W2-4 is free by the same route: anything in a set entry is pinned, anything from an axis
is generated.

---

## What landed ahead of the plan (2026-08-04)

Five commits after `a0e82a1`, all in `stepgen/studio/`:

| Commit | What |
|---|---|
| `8c4854d` | Read a multi-design study by design, not by row (`decide.group_by`) |
| `d8397ab` | Name the ladder — main length and derived N — in the decision panels |
| `2908af0` | Improvement advice as a table, not an essay (`levers.py`) |
| `912c74c` | **`stepgen/studio/interactive.py`** (810 lines) — the chapter is filter-first |
| `6db6405` | Tabs, pinned-run spec table, "mark best" over visible rows; **one lever corrected** |

`6db6405` also retired a lever claim the study's own numbers disprove — that adding DFUs
lowers exit Ca by spreading flow. At fixed drive pressure it does not: D1 o/w at 300 mbar,
main 20 → 160 mm gives N ×8, throughput ×7.7, and Ca 0.02054 → 0.01985, a 3% change. **Ca
is set by the ΔP each rung sees, not by how many rungs share the main.** Worth carrying
into W2-5 and D5: it means the Ca ceiling cannot be escaped by scaling N, which is most of
why D5 inverts rankings at all.

`912c74c` is **section D, shipped into the static HTML chapter** rather than into
`studio-serve`: every scored row travels into the page as JSON (`chapter_payload`,
`interactive.py:150`), and the filter bar, winner cards, table and SVG plots recompute in
the browser over whatever subset is visible. That covers D1, most of D2 and D4.

**What it does right**: the JS filters on Python's `verdict` field and never re-derives a
verdict from thresholds. No physics is duplicated into JavaScript. `thresholds` in the
payload is only used to draw bands on plots.

**What it costs — four items, all folded into the plan below**:

1. ~~**A4a is now a live reader-facing gap, not a latent one.**~~ **Closed by `39e7342`.**
   Recorded for the reasoning: `chapter_payload` is a
   *second* row serialiser beside `_chapter_json`. It exposes `regime_Ca` as a filterable
   limit (`interactive.py:64`) and ships `caCeiling` / `caMeasured` — but **carries no γ at
   all**. γ-robustness exists only in the server-rendered diagnosis panel, computed over
   *all* rows, so it does not follow the filter. Narrow to a subset and the Ca verdict
   detaches silently from the constant that decides it. This is exactly what D5 called
   non-negotiable, now breached by a shipped control.
2. **A4b's target moved.** The payload carries only `min_margin_discounted` as
   `metrics.margin`; per-metric margins are what a Ca-distance column needs.
3. **D7 is no longer preventable, only consolidatable.** Three filter surfaces now exist:
   `ui.py`, the chapter JS, and the unbuilt `studio-serve`.
4. **D6 has split.** `t_stage1_s` is in `workbook.py:78`'s column list but absent from
   `interactive.py`'s `PLOT_METRICS`. `Po_min_production_mbar` is absent everywhere.
   `dP_rung_mbar` and `t_cycle_s` are in both.

Sequencing consequence: **D ran before Batch 1.** Nothing is broken by that — D touched no
physics — but Wave 2 will move every number the chapter now plots, so the schema bump
(W2-6) matters more than it did, and any chapter written before Wave 2 must be
distinguishable from one written after.

---

## Measured evidence

Everything in this section was measured, not assumed.

### Solve cost

- **~19 ms/point.** 1,368 points in ~26 s. A realistic serpentine sweep with exits locked
  is 2,880 points ≈ **55 s**.
- **Rule to surface in the UI**: adding an axis with k levels multiplies runtime by k.

### The three real devices (`reference_devices/` — not yet created, see W1-4)

Measured from GDS with `gdstk`; polygon accounting closes with **residual 0**.

| | **V5-30** serpentine | **V5-10** serpentine | **V6-30** radial |
|---|---|---|---|
| Die | 100 × 100 mm | 100 × 100 mm | 100 × 100 mm |
| Active footprint | 69.0 × 74.0 = 51.1 cm² | 68.6 × 74.0 = 50.8 cm² | disc R=45 mm = 63.6 cm² |
| **% of die** | **51%** | **51%** | **64%** |
| Lane pairs | 10 | 12 | — |
| Main width | 1000 µm | 1000 µm | — |
| DFU array gap | 4.0 mm | 2.8 mm | — |
| **Wall** | **1.0 mm** | **1.0 mm** | — |
| **Lane pitch** | **7.00 mm** | **5.80 mm** | — |
| DFU pitch | 60 µm | 20 µm | 75.4 µm |
| DFUs | 10,000 straight + 1,154 curve = **11,154** | 36,000 + 3,192 = **39,192** | **3,000** at R = 36.0 mm |

What this establishes:

1. **`lane_pitch = 2×main + DFU_array + wall`, exactly.** V5-30: 1+4+1+1 = 7.0.
   V5-10: 1+2.8+1+1 = 5.8. The model's `lane_spacing = 500 µm` is spurious, and
   `2 × turn_radius` matching the 1.0 mm wall on V5-30 is a **coincidence** that breaks
   the moment turn_radius changes.
2. **The wall is 1.0 mm on both devices** — a design rule with no input in serpentine today.
3. **Radial `N = 2πR/pitch` is exact**: 2π×36 mm / 75.4 µm = 3,000, matching to the unit.
4. **Serpentine and radial have genuinely different overhead** (51% vs 64%) for a physical
   reason: radial feeds from the centre and needs ~5 mm margin, while the serpentine spends
   a dedicated 65.8 × 8 mm IO strip plus ~13–15 mm margins.
5. The packing model's *geometry* was never wrong. Given the real active area it lands
   exactly: `(69 − 6.0)/7.0 + 1 = 10` lane pairs. The old 1.66× over-prediction was
   entirely the assumption that 96×96 mm of a 100×100 mm die is usable — an assumption
   **still live in every checked-in study config** (`square_side_mm: 100.0` with
   `reserve_border_mm: 2.0`). See W1-6.

### The real DFU profile

```
V5-30   3610 um @  8 um wide  (90% of length)   depth 10 um throughout
         410 um @ 30 um wide  (10%)             = 4020 um total
V5-10   2525 um @  7 um wide  (90%)
         285 um @ 10 um wide  (10%)             = 2810 um total
```

`constriction_ratio: 0.9` encodes that 90%, but `resistance.rung_resistance` uses it to
*shorten the channel* rather than model two widths in series.

### The rung-resistance disagreement — four implementations, three rejection rules

Two functions, same config, same instant, on V5-30:

```
stage1_physics.compute_rung_resistance   2.697e18 Pa.s/m3
resistance.rung_resistance               1.525e18 Pa.s/m3    +76.9% apart
```

Decomposed against the real profile:

```
today (unordered dims, L x 0.9)          1.525e18
ordered dimensions, single section       1.021e18   0.67x
PIECEWISE over the real profile          1.036e18   0.68x
   3610 um @  8 um wide -> 98.8% of total
    410 um @ 30 um wide ->  1.2%
```

**Today over-states the real rung by 1.47×.** Almost all of it is dimension ordering.

The full inventory — **four** sites, not three, and they disagree on three separate axes
(shape factor, dimension ordering, length):

| Site | Shape factor | Ordering | Length | Rejects when |
|---|---|---|---|---|
| `stage1_physics.compute_rung_resistance` | Shah & London | **ordered** (`h=min`, `w=max`) | full `mcl` | never |
| `resistance.hydraulic_resistance_rectangular` | `1−0.63h/w` | unordered | `mcl × constriction_ratio` | `h/w ≥ 1.587` |
| `radial._corr` (`radial.py:78`) | `1−0.63h/w` | unordered | — | `h/w ≥ 1.587` |
| `manifold._R_rect` (`manifold.py:118`) | `1−0.63h/w` | unordered | — | **`h ≥ w`** |

**Critical**: V5-30's narrow section is 8 µm wide × 10 µm deep, so depth > width. The
original B3 fix ("reject `h >= w`") would have made the real device unmodellable — and
`manifold._R_rect` **already enforces exactly that rule**, so the manifold family cannot
model a V5-30-like DFU today. The correct fix is to *order* the dimensions as
`stage1_physics` already does; then α ≤ 1 always and no rejection is needed anywhere.

Also found: `resistance.rung_resistance`'s docstring says *"Viscosity used is
`config.fluids.mu_continuous`"* while the code (`resistance.py:99`) uses `mu_dispersed`.
The code is right for oil-driven Stage 1; the docstring is a trap. Fix it in W2-1.

---

## Batch 1 — genuinely safe to run cold

> **B2 has been removed from Batch 1** — it is not inert. See W2-1a.
> B3 was removed earlier (it changes results 1.47×; it is now W2-1).
> B4's physics half landed in `21c974f`, `7810092`, `45437cc`; the form half is C2.

### B1 — `stepgen study` crashes on Windows printing its own diagnosis ✅ `e21798e`

**Symptom.** `UnicodeEncodeError` at `cli.py:513-514`, printing `diag.headline()`. The
study **completes and writes its chapter**, then dies on the summary — worst possible
ordering.

**Correction to the previous vintage**: `Δ` does not appear in `cli.py` at all. It arrives
from `diagnosis.py:64` (`"uniformity_pct": "ΔP flatness"`) through the headline. The
cp1252-fatal characters *in `cli.py` itself* are `─` (**858 occurrences**), `→`, `γ`
(`cli.py:523`) and `✗`. `µ`, `…`, `×`, `—`, `·` survive. The crash surface is far wider
than one glyph, and `d8397ab` / `2908af0` added more Δ-bearing prose on that path.

**Fix.** At the top of `main()` (`cli.py:966`), reconfigure `sys.stdout`/`stderr` to
`encoding="utf-8", errors="replace"`, guarded for streams that do not support it.
`errors="replace"` matters — console output must never kill a completed run.

**Verify.** ✅ Exits 0 under `PYTHONIOENCODING=cp1252`, full diagnosis printed. Regression
tests in `tests/test_cli.py::TestConsoleEncoding` cover both the cp1252 stream and a stream
with no `.reconfigure`.

### B0 — commit the repro config ✅ `e53ddc6`

`configs/study_dp15_1000mbar_60x20.yaml` was untracked. B1's and W2-1a's verify steps both
name it. Now committed.

### A4a — γ is missing from **both** sidecars ✅ `39e7342`

**Why.** γ varies 3× across this repo's configs (5 / 15 / 0 mN/m) and `Ca ∝ 1/γ`. Pooling
rows from two chapters would silently mix Ca computed on different constants — and since
`912c74c`, a reader can filter on `regime_Ca` in-browser with no γ anywhere on the page.

**Fix — three places, not two.** A third was found while implementing: `radial` and
`manifold` never filled `CommonMetrics.gamma_Nm` at all (`base.py:163` existed; only
`serpentine.py:839` set it), so two of three families computed a Ca and discarded the
constant behind it. Per-row γ was unreachable until that was fixed.

1. ✅ `radial.py` / `manifold.py` fill `gamma_Nm` from the compiled `c.gamma`.
2. ✅ `_chapter_json()` — top-level `fluids` block (`_fluids_json`). γ resolved from the
   **points actually solved**, not the study block: `fluids:` may be a list, and where the
   points disagree `gamma_Nm` is null with `gamma_values_Nm` listing every value found.
3. ✅ `chapter_payload()` — `gamma` per row (kept out of `m` so it never becomes a plot
   axis; it is provenance, not a result), plus `paintGamma()` in the rail, recomputed over
   the **visible** rows: one system, several (flagged *not comparable on Ca*), or none.

**Verify.** ✅ On the 1368-row study: `fluids.gamma_Nm = 0.005`, every payload row carries
`gamma`, and the rail states it. Radial confirmed on `study_serpentine_vs_radial.yaml`.
Guarded by `tests/test_studio.py::test_chapter_carries_gamma_and_per_metric_margins`.

### A4b — per-cell margins are missing from both sidecars ✅ `39e7342`

**Why.** `ScoredRow` stores `min_margin` but not per-metric margins. `CellScore.margin` is
"distance past the ceiling", deliberately uncapped — it is what the planned Ca-distance
column displays.

**Fix.** ✅ In `_chapter_json`, mirroring the `confidence` block:
`"margins": {k: c.margin for k, c in sr.cells.items() if c.category != "grey"}`.
In `chapter_payload`, the same dict per row (`None` margins dropped), so the Ca-distance
column can exist in the interactive table.

**Verify.** ✅ `rows[0].margins.regime_Ca` is a float in both.

---

## Wave 1 — bounded: area and capacity only

Fully determined by the GDS measurements; no design decisions remain. `compute_layout`
never feeds the hydraulic solve, so for a **pinned N** these change `area_used_cm2`,
`fits_square` and `packing_capacity` but leave throughput and ΔP untouched.

### W1-1 — correct the serpentine stack-up

```python
lane_pair_width = 2 * main_width + dfu_array_length     # drop lane_spacing
lane_pitch      = lane_pair_width + wall_width          # wall is an INPUT, not 2*turn_radius
```

`wall_width` becomes a `FootprintConfig` field, default **1.0 mm** (measured on both
serpentines). `turn_radius` stops setting the inter-lane gap; per decision 9 it is reported.

**Correction: the formula is written three times, not twice.**

| Site | What it is |
|---|---|
| `design/layout.py:114-115` | the model |
| `design/design_search.py:117` | the search (note: omits `mcl`, so it already differs) |
| `families/serpentine.py:879` | **the schematic drawing** |

The third is the one that bites: `serpentine.py`'s `packing_capacity` docstring explicitly
claims *"The drawing and this readout agree on that, which is the point."* Fix two of the
three and the picture silently stops matching the number.

### W1-2 — per-family `active_fraction`, measured

Each number is measured from a built device; the difference between families reflects real
IO topology, not a fitted constant.

```
serpentine  0.51   V5-30, V5-10   (two independent devices)
radial      0.64   V6-30          (one device)
manifold    0.51   [UNCALIBRATED — no built device; note on every row]
```

`reserve_border` stops carrying overhead it was never sized for.

**Caveat to record on the field**: 0.51 and 0.64 were measured on a **100 × 100 mm** die.
`serpentine.py:230` and `radial.py:186` both default `square_side_mm` to **63.5**. An area
*fraction* does not scale to a different die — the IO strip and margins are absolute. Flag
it on any row whose die is not 100 mm; the real fix is the deferred per-family IO model.

### W1-3 — acceptance tests from the real devices

```
V5-30 -> 10 lane pairs, 7.00 mm pitch, 11,154 DFUs
V5-10 -> 12 lane pairs, 5.80 mm pitch, 39,192 DFUs
V6-30 ->  3,000 DFUs at R = 36.0 mm
```

Constants asserted as literals citing `reference_devices/`, so neither `gdstk` nor 2.2 MB
of binaries becomes a test dependency.

### W1-4 — commit the reference devices ✅ `77ac36a`

`reference_devices/` at top level: the three GDS files (`v5_30umV1.1.gds`,
`v5_10umV1.gds`, `V6-30um_v1.2.gds`) plus a short `README.md` carrying the measurement
table above and the script that produced it. **Read the README — it is ground truth for
layout and packing; do not re-derive its numbers from the model.**

### W1-5 — fix `configs/v5_30.yaml`

`Mcl = 693 mm` implies 11,550 DFUs; the GDS has 11,154, i.e. **669 mm**. The comments
("Mcl=2040 mm, pitch=3 µm, Nmc=680 000", "0.3 µm depth", "1 µm width") are stale template
text describing nothing in the file. Correct against the GDS and delete the comments.
**Blocked on** reconciling 11,154 vs 11,565 — see open question 1.

### W1-6 — migrate the study configs off `reserve_border` *(new)*

Every checked-in study config pairs `square_side_mm: 100.0` with `reserve_border_mm: 2.0`
— the 96×96-of-100×100 assumption that W1-2 identifies as the entire source of the old
1.66× over-prediction. W1-2 changes the model; without this item the configs keep feeding
it the old overhead. Touches `study_all_families`, `study_dp15_1000mbar_60x20`,
`study_my_designs`, `study_serpentine_vs_radial`, `study_template`.

---

## Wave 2 — changes what the numbers mean

Everything here shifts results. Ends with a schema bump so pre- and post-wave-2 chapters
cannot be silently pooled.

### W2-1 — one rung-resistance implementation *(was B3 + A5)*

One rectangular-duct function, **dimensions ordered** (`h = min`, `w = max`), applied
**piecewise** over the real two-width DFU profile. Shah & London dropped in favour of the
single `1 − 0.63·h/w` term — record in a comment *why*, so nobody re-adds it: consistency
between call sites is worth more than the few percent of accuracy.

All four sites delegate to it: `stage1_physics.compute_rung_resistance`,
`resistance.rung_resistance`, `manifold._R_rect`, `radial._corr`. Precedent: Phase 1 did
exactly this for the Pareto rule (`viz/plots.py::_pareto_front` → `ranking.pareto_mask`).

The piecewise machinery already exists — `resistance_piecewise` (`resistance.py:58`) +
`rung.profile`; it is simply not the default path.

Also in scope, because they are the same edit:
- Fix the `resistance.rung_resistance` docstring (says `mu_continuous`, uses `mu_dispersed`).
- **Delete the three rejection rules.** Ordered dimensions make `h/w ≤ 1` unconditionally,
  so `manifold._R_rect`'s `h < w` guard, `radial._ASPECT_LIMIT` and
  `hydraulic_resistance_rectangular`'s `denom <= 0` raise all become dead.

**Impact**: rung resistance ×0.68 on V5-30; throughput and ΔP move on every serpentine row.

### W2-1a — manifold aspect validation *(was B2 — moved out of Batch 1)*

**Why it moved.** B2 proposed validating at `ManifoldFamily.compile()` (after `upstream_w`
is read, `manifold.py:290`) that `upstream_width_um > exit_depth_um`, so a bad config fails
once at compile instead of 108 identical times inside `solve()`. But the constraint it
would codify **is `manifold._R_rect`'s `h < w` guard, which W2-1 deletes.** Landing B2
first hardens a rule Wave 2 removes, and would leave a compile-time error rejecting
geometry the physics can then model fine — including the real V5-30 DFU.

**What to do instead.** After W2-1, the fail-fast-at-compile idea is still right, but the
predicate changes: validate what actually remains impossible (non-positive dimensions,
`min_feature` violations), not `h < w`. Name the *config fields* in the message.

**Verify.** `configs/study_dp15_1000mbar_60x20.yaml` (`upstream_width_um: 15`,
`exit_depth_um: 20`) **solves** after W2-1 rather than raising 108 times.

### W2-2 — audit for other duplicated formulas

Grep the remaining physical formulas (area, fits, capacity, droplet size) for second
copies before building on them. The rung-resistance audit found **four** copies where the
last vintage of this plan said two; the lane-pitch audit found **three** where it said two.
Assume the count is wrong until grepped.

### W2-3 — N from packing *(was A2)*

`packing_capacity()` becomes an input, not just a readout. Extends `fdc8ec9`'s
raise-don't-guess rule to three sources:

```yaml
rung:  { N: 1000 }                      # -> Mcl = N x pitch          [implemented]
main:  { length_mm: 120 }               # -> N   = L / pitch          [implemented]
rung:  { fill_fraction: [1.0, 0.75] }   # -> N   = ff x packing_capacity(geom)   [TODO]
```

Exactly one may be given; two or more raises, naming the N each implies. Label gains an
`Ff` tag alongside `N` / `Lm`.

`fits_square` becomes **true by construction** in fill_fraction mode (`layout.py:137` is
precisely what `packing_capacity` inverts) — so it degrades to an invariant assertion
there, and to a *report* under decision 10 when N is pinned. It is never a live gate again.

Also answers open question 3: `lane_length = L_useful` always (`layout.py:129`), so area
grows only vertically and `ff = 1.0` **is** "fill the die".

### W2-4 — carry provenance to scoring *(decision 10, generalised)*

1. Thread pinned-ness to `score_row` — either `Study.intent_plan` or a `pinned: set[str]`
   on the row. Decision 11 makes this nearly free: set entry → pinned, axis → generated. A
   hand-written study (no `intent:`) marks all geometry pinned.
2. Apply uniformly to every sub-gate in the `build` composite and to threshold gates
   scoring a *geometric* quantity. **This is where the silent-`no_crossing` regression gets
   fixed**: every sub-gate that is demoted to a report must emit a chip, not vanish.
   Today only `manufacturable` does (`scoring.py:328-331`).
3. Keep the explicit override: `build: { manufacturable: required }` forces gating even on
   a pinned value.
4. `diagnose()` must not price relaxing a constraint that only a *pinned* value breaches.
   That is what produced "relax 200 → 300 µm: nothing changes" against a user-set 400 µm.
   The honest output is "you set depth to 400 µm, above the 200 µm cap".

**Tests** (none exist today):
- A hand-written study breaching every fab cap still produces non-red verdicts driven by
  the *physics* gates, and names the breach in a chip.
- The same study with `manufacturable: required` goes red.
- **A design that does not fit the die, or that crosses phases, emits a chip even when the
  study omits `required`.**

### W2-5 — bend radius + wall-at-turn as reported metrics *(was A3)*

`CommonMetrics` fields, no threshold. Note the tangle W1-1 partly resolves: for a real 180°
fold the centreline radius is ≈ half the lane pitch, so turn radius is *determined by*
pitch, not a free input that adds to it.

### W2-6 — schema bump

`schema_version` on the chapter sidecar **and on `chapter_payload`**. `git_hash` is already
recorded but nothing reads it; the version is what makes the pooling guard in D3
enforceable. Raised in priority by `912c74c`: chapters written before Wave 2 now carry an
interactive filter over numbers Wave 2 will change.

### W2-7 — downstream text that W2-1 falsifies *(new)*

`configs/study_my_designs.yaml:83-94` documents the aspect-ratio trap as a *user-facing
design rule* — *"needs h/w < 1 … Above h/w = 1.587 it raises; BETWEEN 1.0 and 1.587 it
returns a silently wrong number"*, with a `upstream_width_um >= 1.25 × exit_depth_um` hard
floor. After W2-1 all of that is false and the floor is unnecessary. Update the comment
block and the same warning wherever it is repeated. Grep for `1.587` and `h/w`.

### W2-8 — exit criteria: re-validate before C starts *(was W2-7)*

Wave 2 is not done until:

- [ ] `pytest -q` → 531 passed, same 5 known failures
- [ ] Re-run against `experimental_workspaces/po_sweep/data/stage_timings.csv`, reporting
      new Stage-1 and cycle-time agreement at 200–800 mbar
- [ ] **`C_visc` refit in its own workspace.** It was fitted 2026-03-20 against timings
      later corrected ×0.5 (fps 25→50, `po_sweep/BRIEF.md`) and never revisited;
      `stage1_physics.py` was last touched 2026-05-18. W2-1 stacks a second shift on top.
      Refit as a study, not as a constant nudged inside a UI build.

---

## C — the server

Scope reduced by decision 12: the chapter already filters, so C is the **front door only**.

- **C1.** `stepgen studio-serve` — FastAPI + uvicorn. **Add both to `pyproject.toml`**;
  only `streamlit` is declared today (`pyproject.toml:22`), so a fresh clone breaks.
  Routes: form page, `POST /run` (solve → `write_workbook()` → chapter), `POST /preview`
  (compile only, ~1–4 ms, no solve).
- **C2.** The form, per decision 11 — three regions:

  ```
  DESIGNS (set, concatenated)     30x10 | 60x20 | 30x20 | 15x10
  FLUIDS  (set, concatenated)     o/w SDS | w/o oil-soluble     [swap A/B button]
  AXES    (grid, crossed)         Po 200..1200 (6 levels)  + coarse/fine dial
                                  points = 4 x 2 x 6 = 48
  ```

  Pure comparison = several designs, no axes. Pure optimisation = one design skeleton, all
  axes. Exits live in the set region, never on the dial — the real content of the grid-bias
  lesson. Fluid entries are whole blocks; never independent viscosity lists (a 4-exit ×
  fluid-swap study produced 64 points of which 32 were fluids that do not exist).
  `len(study.points)` is known before solving, so the count is exact.

  **This form writes the YAML shape `study_my_designs.yaml` already uses.** The engine
  exists; C2 is UI over it. Read that file before writing the form — its comments are the
  spec, including the shallow-merge trap on `<<: *rung`.
- **C3.** House sweep-level defaults as a checked-in, reviewable file — shown read-only in
  the form, with an "adjust axes" expander for full control. Carries the measured
  ms/point per family for C2's estimate.

---

## D — the results explorer

D1, most of D2 and D4 landed in `912c74c`, in the chapter rather than the server. What
remains:

- **D1.** ✅ *Landed.* Columnar payload + client-side filter/sort, no round-trip.
- **D2.** *Partly landed.* The filter bar has verdict and numeric limits. **Missing**: the
  three-state *gate / report / off* control, and the "you set this" marker on pinned
  values. Blocked on W2-4.
- **D3.** Swept-range display per control, out-of-range warning, and "extend this axis"
  → **a child chapter recording its parent**, loaded with the parent as one lineage table.
  Safe where arbitrary pooling is not, because a lineage holds family, exits and fluids
  fixed by construction. **Guard**: pool only when `git_hash` *and* `schema_version` match;
  otherwise refuse and offer to re-run the parent.
- **D4.** ✅ *Landed* — click-to-pin, a Pinned-runs table carrying every design and
  condition axis with verdict and reason, "pinned only" on the plot, and "mark best" over
  the *visible* rows (`6db6405`). Phase 3 schematic in the detail panel still to wire.
- **D5.** **The Ca gate as a live control.** `ca_gated_summary(frame, ca_max, gamma_ref)`
  re-solves nothing — `regime_Ca` is solved and γ enters as an exact 1/γ. Returns per
  design: `Po_gated_mbar`, `throughput_gated`, `Po_next_failed` (**the gap is unsimulated
  headroom, not absent headroom**), and `passes_at_gamma_lo`.

  It earns its place because it *inverts rankings*: two designs, 60×20 µm exit, 1000 DFUs
  — ungated at 1000 mbar, main 200×1000 µm makes 18.87 mL/hr against 4.35 for 100×500 µm.
  Gated at Ca ≤ 0.0125 the wide main caps at 200 mbar and makes **3.29**, losing to 4.35.

  **Non-negotiable. Half-closed.** `39e7342` put γ on the page: the rail states which γ the
  *visible* rows were solved at, and says so when a subset mixes systems. Still missing is
  `passes_at_gamma_lo` sitting *next to* the ceiling control rather than in a detail panel
  — in the example above **both** designs pass at γ = 5 mN/m and **both** fail at 3, and
  only the ceiling control can say that at the moment the reader filters. A4a's
  prerequisite is done, so D5 is unblocked.
- **D6.** Columns to add: `dP_rung_mbar` ✅, `t_cycle_s` ✅, `t_stage1_s` (in `workbook.py`,
  **missing from `interactive.py:PLOT_METRICS`**), `Po_min_production_mbar` (missing
  everywhere). Two caveats ship with them:
  - **`stage1_fraction` is constant by construction** — the geometric ratio V_reset/V_drop,
    one value at every pressure (0.63 for a 30×10 exit). Measurement gives
    0.63/0.63/0.65/0.54/0.46 across 200→800 mbar. A **diagnostic, not a guard**.
  - **`Po_min_production_mbar` costs ~40 solves** and is a property of the *design* at a
    given Qw, independent of swept Po. Compute once per design.

  **Keep the two metric lists in sync or merge them** — `workbook.py:78` and
  `interactive.py:PLOT_METRICS` are already diverging. This is W2-2's bug class arriving
  inside the studio.
- **D7.** Gate and filter evaluation in **one shared module**. Reworded: this is no longer
  prevention, it is consolidation. Three surfaces exist — `ui.py`, the chapter JS,
  `studio-serve`. The JS holds the line today by filtering on Python's `verdict` rather
  than re-deriving it; **that invariant is the thing to protect.** Write it down as a
  comment at the top of `interactive.py` and as a test: no threshold comparison in JS.

---

## E — provenance

- **E1.** Sweep → chapter, reusing `write_workbook()` unchanged.
- **E2.** Filter views as small saved JSON (thresholds, sort, demoted gates, starred rows),
  shareable as a URL. **Needs a stable chapter id** — undefined today; a view must be able
  to name the chapter it points at. Now also needs to serialise the in-chapter filter
  state that `912c74c` introduced.
- **E3.** Refine sweep → child chapter recording parent + the starred designs it was built
  around. Same lineage mechanism as D3.

---

## Sequencing

```
B0 ✅ -> B1 ✅ -> A4a/A4b ✅  ->  Wave 1  ->  Wave 2 (+ re-validation, C_visc refit)  ->  C  ->  D-rest  ->  E
                          \
                           └─ D5 unblocked: it needed A4a only, which has landed
```

Batch 1 is done and was inert as expected — no physics moved, 534 passed against the same
5 known failures. **Next up is Wave 1**, which is measurement-determined with tests already
written (W1-4's `reference_devices/README.md` is the ground truth; read it, do not
re-derive). **Wave 2 is the risk** — it changes what every number means, and C does not
start until W2-8 passes.

**The one item worth pulling forward now**: D5's ceiling control with `passes_at_gamma_lo`
beside it. Its prerequisite (γ on the page) landed in `39e7342`; it depends on nothing in
Wave 1 or 2.

---

## Explicitly deferred

- **LLM config helper.** Out for v1. If it returns, the safe job is translating a request
  into a *filter/sort expression* — a view over computed data, wrong answers instantly
  visible — never into sweep ranges.
- **Arbitrary cross-study pooling.** Lineage pooling (D3) is in; pooling unrelated
  chapters is not.
- **Full layout rebuild** — turn radius constraining lane count, fold arc as a real channel
  with its own pressure drop. W1-1 fixes the stack-up arithmetic, not this.
- **Per-family IO modelling.** The 51% vs 64% difference is measured, not explained. An
  explicit port/strip model would say *why* and would scale to a different die size, where
  an area fraction will not — see W1-2's caveat.
- **Streamlit retirement.** `ui.py` (941 lines) untouched at v1.

---

## Open questions

1. **11,154 vs 11,565.** The GDS gives 11,154 (10,000 straight + 1,154 curve) with all
   31,674 layer-2 polygons accounted for and nothing left over. Conor's figure is 11,565 —
   3.7% apart. Possibly a revision difference (this is V1.1) or a different convention on
   the curve DFUs. **Blocks W1-5.**
2. **Is Stage 3 a real capillary floor or a frame-rate artefact?** S2+S3 flatten above
   400 mbar, but there they are 2–3 frames at 50 fps and every value is an exact multiple
   of 0.02 s. If physical, per-DFU frequency saturates and conservation over-predicts at
   high pressure. Current evidence favours artefact (`t_cycle ∝ 1/Q` to 0.2% across
   200–800 mbar). Needs a high-speed re-shoot at 400–1000 mbar, not more modelling.
3. **Sort semantics.** A single sort column is v1; the existing `decide:` layer (per-axis
   winners, Pareto, composite) remains available in the chapter and may be the better home
   for multi-objective work.
4. **The Ca ceiling itself.** `SE_CEILING_CA = 0.03` (`base.py:87`) is borrowed from
   literature; `CA_MEASURED_MAX = 0.0017` (`base.py:107`) is the highest Ca Peak has ever
   measured — 18× below. Every Ca verdict inherits that.
5. *(new)* **Does `active_fraction` survive a die-size change?** 0.51/0.64 are measured at
   100 mm; the family defaults are 63.5 mm. Until the deferred IO model exists, W1-2 is
   only valid at 100 mm and must say so on the row.
