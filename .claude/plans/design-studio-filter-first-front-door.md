# Design Studio — the filter-first front door

**Anchor**: `6ad1f33` on `master` (was `5674636` before Wave 1)
**Baseline now**: `pytest -q` → **560 passed, 3 failed, 5 skipped**. The 3 are the
pre-existing `test_cli` png failures. **Do not chase them.** The count of known failures
dropped 5 → 3 during Wave 1: the two `test_design_search` failures were **not** unrelated
noise, they were the duplicated lane-pitch formula, and W1-1 fixed them. See W1-1.
**Supersedes**: Phase 6 ("Form-driven UI") in `docs/06_design_studio/roadmap_studio_v1.md`
**Derived from**: `/grill-me` sessions with Conor, 2026-08-03 and 2026-08-04

> Rewritten 2026-08-04 and re-anchored `306a4bc` → `a0e82a1` → `6db6405` → `5674636`
> → `6ad1f33`.
> Earlier vintages are in git history. Everything below is one vintage; items marked ✅
> were executed and verified (Batch 1 on 2026-08-04, Wave 1 on 2026-08-05) and carry what
> implementation found that the plan did not.

---

## Where this stands — read this first

| | State |
|---|---|
| **Batch 1** | ✅ **complete.** B0 `e53ddc6` · B1 `e21798e` · A4a+A4b `39e7342` · plan `5674636` |
| **Wave 1** | ✅ **complete.** W1-4 `77ac36a` · W1-1 `d347643` · W1-2 `747a3ce` · W1-3 `9556202` · W1-6 `fd99045` · W1-5 `6ad1f33` |
| **Wave 2** | **not started — this is the next work.** The risk item: it changes what every number means |
| **C (server)** | not started, and must not start until W2-8 passes |
| **D (explorer)** | D1 ✅, D4 ✅, D2 partly, all in the chapter (`912c74c`, `6db6405`). D5 unblocked |
| **E** | not started |

**Start here**: Wave 2, in the order **W2-2 → W2-1 (+ the viscosity, together) → W2-1a →
W2-7 → W2-3 → W2-4 → W2-5 → W2-6 → W2-8**. Do not start C until W2-8 passes.

**Read "What the ×0.68 costs" in Measured evidence before touching W2-1.** The headline:
the model matches experiment today because two errors cancel, W2-1 removes only one of
them, and `C_visc ≈ 0.7` is sitting there ready to hide the difference. **Conor ruled
2026-08-05 that it must not be used.** The replacement is a measured oil viscosity, which
predicts frequency to ±8% over 200–800 mbar with no correction term anywhere.

**Three things Batch 1 and Wave 1 learned that generalise:**

1. **The site count in this plan is a lower bound — every time it has been checked.** A4a
   was documented as two places and was three. W1-1 was documented as three copies of the
   lane-pitch formula and was **four**: the fourth is
   `viz/plots.py::plot_layout_schematic`, which no vintage of this plan had ever named.
   Treat W2-1's four rung-resistance sites the same way — **grep before editing, and
   assume the count is still wrong.**
2. **Duplicated formulas are not a tidiness problem, they are where the bugs already
   are.** `design_search`'s copy of the lane pitch omitted the rung array, so the search
   sized `Mcl_max` with a lane pair that `compute_layout` then checked with a wider one:
   every candidate it produced was declared not-to-fit by its own footprint check. That is
   what the two "pre-existing, do not chase" `test_design_search` failures were. Nobody had
   looked, because they were on the known-failures list. **The three remaining known
   failures deserve the same suspicion.**
3. **Wave 1 was inert for a pinned N, as required.** N = 1000, 60×20 exit, 500 mbar:
   throughput, ΔP_rung, uniformity, `regime_Ca` and droplet size are bit-identical across
   the whole wave; only `area_used_cm2`, `fits_square` and `packing_capacity` moved.
   Wave 2 will **not** be inert, by design — that is what makes it the risk item.

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

### What the ×0.68 costs — and the one constant that pays for it

Measured 2026-08-05 against `experimental_workspaces/po_sweep/data/stage_timings.csv`
(V5-8-1, Qw = 5 mL/hr, corrected timings).

**The model matches experiment today only because two errors cancel.** With `C_visc = 1.0`
— its default, and no config overrides it — the current model predicts frequency to
−2.3 / +5.9 / −9.3 / −9.3 / +5.1% at 200/300/400/600/800 mbar. That agreement is built on a
rung resistance 1.53× too high. Fix the resistance alone and frequency goes **+25 to +46%
wrong**, at which point `C_visc ≈ 0.7` is sitting there ready to hide it.

**Do not let it.** A global scalar that restores agreement would encode the fab and fluid
state of one device, at one condition, into every design the studio ever scores.

What the discrepancy actually is: with geometry as drawn and the resistance solved exactly,
the model over-predicts Q by a factor that is **constant, not pressure-dependent**:

```
Po (mbar)     200    300    400    600    800
Q_model/Q_meas 1.39   1.50   1.29   1.29   1.49      scatter, no trend
implied µ       83     90     77     77     90  cP
```

A constant multiplier on `ΔP/R` at fixed geometry **is a viscosity**. So there is no
missing physics — no capillary back-pressure term, no droplet-growth model, no
pressure-dependent correction. There is one number, and it is a material property.

Best fit, geometry as drawn, resistance exact, **zero correction terms**:

```
µ = 83 cP   (config assumes 60; po_sweep/BRIEF.md cites a ~50-60 cP literature range)

 Po    f meas   f model    err
 200     0.95      0.94   -0.2%
 300     1.60      1.74   +8.3%
 400     2.71      2.52   -7.3%
 600     3.82      3.54   -7.3%
 800     4.92      5.29   +7.5%
```

**±8% across a 4× pressure range, errors alternating in sign** — no systematic drift left.

Two things to hold onto:

1. **83 cP is a fit, not a measurement.** It is the right *kind* of constant — physical,
   portable, testable, and it correctly enters the main channels and scales with
   temperature and with a change of oil — but until the oil is on a viscometer it carries
   whatever else is unaccounted for. Conor's read (2026-08-05): partly colder oil (83 cP is
   ~17–18 °C for sunflower), partly a slight geometric difference from the drawing, and
   **not worth chasing further** — `R ∝ 1/h³`, so 8.0 → 7.2 µm alone would also do it.
2. **The data cannot support better than ~15% anyway.** The sweep gives two independent
   measures of Q — meniscus sweep (`L_menpoint·w·h / t_S1`) and conservation
   (`V_drop / t_cycle`) — and they disagree with **each other** by 13–26%. ±8% is at the
   noise floor. Stop there.

### The real DFU profile

```
V5-30   3610 um @  8 um wide  (90% of length)   depth 10 um throughout
         410 um @ 30 um wide  (10%)             = 4020 um total
V5-10   2525 um @  7 um wide  (90%)
         285 um @ 10 um wide  (10%)             = 2810 um total
```

`constriction_ratio: 0.9` encodes that 90%, but `resistance.rung_resistance` uses it to
*shorten the channel* rather than model two widths in series.

### The rung-resistance disagreement — measured against the exact solution

> **Rewritten 2026-08-05.** The previous vintage of this section compared the two live
> implementations *to each other* and concluded the fix was ×0.68. Both were then compared
> to the **exact** rectangular-duct solution (Fourier series), which changes the verdict:
> neither implementation is right, they are wrong in opposite directions, and the ×0.68 is
> incomplete. See W2-1.

Two functions, same config, same instant, on V5-30:

```
stage1_physics.compute_rung_resistance   2.697e18 Pa.s/m3
resistance.rung_resistance               1.525e18 Pa.s/m3    +76.9% apart
```

Both against the exact solution, for the single narrow section (8 x 10 µm, 4 mm, µ = 60 cP):

```
EXACT (Fourier series)                        1.092e18   1.000x
1-0.63, ORDERED   (h=8, w=10)                 1.134e18   1.039x
1-0.63, UNORDERED (resistance.py as written)  1.694e18   1.552x
Shah & London AS CODED in stage1_physics      2.697e18   2.470x
Shah & London USED CORRECTLY                  1.092e18   1.000x
```

**Shah & London is the better formula and the code misapplies it.** `fRe = 96(1 − 1.3553α
+ …)` is a friction factor normalised on *hydraulic diameter*, so the resistance is
`R = fRe·µL / (2·A·D_h²)`. `stage1_physics` instead drops `f(α)` into the parallel-plate
form `R = f·µL/(w·h³)`, where the coefficient should be `12/(1−0.63α)`. Two different
normalisations. Check it at α → 0: as coded gives `96µL/(wh³)`, eight times the correct
`12µL/(wh³)`. At α = 0.8 the polynomial has decayed to 57.5, so the error lands at 2.47×.

Used correctly it reproduces the series to **four significant figures** — exactness in a
closed form. That is what W2-1 should adopt; the previous instruction to drop it in favour
of `1 − 0.63·h/w` was wrong and is withdrawn.

The unordered form fails for a different reason. V5-30's DFU is **deeper than it is wide**,
so `depth/width = 1.25` and the correction factor is `1 − 0.63×1.25 = 0.2125`; the formula
divides by that. It is not imprecise, it is outside its domain — 79% of the way to the
singularity at 1.587 where the code raises. Hence 55% high rather than 4%.

Piecewise over the real profile, exact:

```
3610 um @  8 x 10 um   9.854e17    98.8% of total
 410 um @ 30 x 10 um   1.246e16     1.2%
TOTAL                  9.978e17    0.654x the live network value
```

**The network path over-states the real rung by 1.53×** — and it is the network path that
sets Q, so it is the one the po_sweep validation rests on. See "What the ×0.68 costs".

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

### W1-1 — correct the serpentine stack-up ✅ `d347643`

```python
lane_pair_width = 2 * main_width + dfu_array_length     # drop lane_spacing
lane_pitch      = lane_pair_width + wall_width          # wall is an INPUT, not 2*turn_radius
```

`wall_width` becomes a `FootprintConfig` field, default **1.0 mm** (measured on both
serpentines). `turn_radius` stops setting the inter-lane gap; per decision 9 it is reported.

**Correction: the formula was written FOUR times, not three.**

| Site | What it is | |
|---|---|---|
| `design/layout.py` | the model | |
| `design/design_search.py` | the search | **omitted `mcl` outright** |
| `families/serpentine.py` | the Phase 3 schematic | |
| `viz/plots.py::plot_layout_schematic` | the matplotlib layout schematic | **named in no vintage of this plan** |

All four now delegate to `design.layout.lane_stackup`.

**What the omission cost.** `design_search` sized `Mcl_max` from
`2×Mcw + lane_spacing`, with no rung array, while `compute_layout` checked the result with
`2×Mcw + mcl + lane_spacing`. So the search handed out designs that its own footprint
check then rejected — `fits_footprint=False` on every candidate. That is exactly
`tests/test_design_search.py::TestJunctionAspectRatio::test_valid_ar_passes_hard` and
`TestPressureHardConstraints::test_default_Po_limits_allow_normal_design`, the two failures
this plan told the reader not to chase. **Both pass now.**

**Also landed, because the drawing had to stay honest.** The fold arc is drawn centre to
centre between the lanes it connects: a 180° turn between lanes at a given pitch *has* a
centreline radius of half that pitch. Drawing it at `turn_radius` while the gap is the wall
would let the arc overlap the next lane. W2-5 turns that into a metric.

**Verify.** ✅ V5-30 → 7.00 mm pitch, V5-10 → 5.80 mm, on the nose. `turn_radius` moved
60× with no change to the pitch. Guarded by `tests/test_reference_devices.py`.

### W1-2 — per-family `active_fraction`, measured ✅ `747a3ce`

Each number is measured from a built device; the difference between families reflects real
IO topology, not a fitted constant.

```
serpentine  0.51   V5-30, V5-10   (two independent devices)
radial      0.64   V6-30          (one device)
manifold    0.51   [UNCALIBRATED — no built device; note on every row]
```

`reserve_border` stops carrying overhead it was never sized for.

**Caveat to record on the field**: 0.51 and 0.64 were measured on a **100 × 100 mm** die.
`serpentine.py` and `radial.py` both default `square_side_mm` to **63.5**. An area
*fraction* does not scale to a different die — the IO strip and margins are absolute. Flag
it on any row whose die is not 100 mm; the real fix is the deferred per-family IO model.
✅ Done: `families.base.active_fraction_note()`.

**Five things implementation found that the plan did not:**

1. **Name collision.** `active_fraction` was already taken — it is the *physics* metric for
   the fraction of rungs ACTIVE (`models/metrics.py`). The layout quantity is
   **`active_area_fraction`**. Do not merge the two.
2. **`active_extent()` is a second shared implementation**, beside `lane_stackup`. The same
   four sites each computed the usable extent themselves, so the same consolidation applied.
3. **`area_used_cm2` had to change meaning to be worth anything.** It is now *die* area
   consumed — the active box grossed up by the fraction — uniformly across the three
   families. Compared as raw active area, the measured 51%-vs-64% split would buy nothing
   on area and would only ever move fits/capacity; grossed up, the family with worse IO
   overhead correctly costs more die. **This is a semantic change to a scored column**, and
   it is the one thing in Wave 1 that a pre-Wave-1 chapter cannot be silently pooled with
   — another argument for W2-6 landing before anyone pools anything.
4. **Radial `fits_square` was `2R ≤ side`** — a wheel touching the die edge on all four
   sides, with nowhere to put an inlet. Now `R ≤ side·√(f/π)` = 45.1 mm on a 100 mm die,
   which is the V6-30 disc to 0.3%.
5. **`reserve_border` is now dead everywhere**, not only in the study configs. Retained as a
   field so older device YAMLs still load, and marked DEPRECATED in `config.py`. Rows with
   no overhead model (`active_area_fraction = 1.0`, which is what a hand-written device
   YAML means by giving an area directly) correctly get no caveat note.

### W1-3 — acceptance tests from the real devices ✅ `9556202`

```
V5-30 -> 10 lane pairs, 7.00 mm pitch, 11,154 DFUs
V5-10 -> 12 lane pairs, 5.80 mm pitch, 39,192 DFUs
V6-30 ->  3,000 DFUs at R = 36.0 mm
```

Constants asserted as literals citing `reference_devices/`, so neither `gdstk` nor 2.2 MB
of binaries becomes a test dependency.

**11,154 here is correct and is not superseded by the 11,565 ruling.** These assert that
`compute_layout` reproduces the geometry in the GDS; the ruling is about what N
`configs/v5_30.yaml` drives the model at. See W1-5.

**As built** (`tests/test_reference_devices.py`, 20 tests, all passing):

* **Exact**: lane pitch (7.00 / 5.80 mm), lane-pair count (10 / 12), radial N at R = 36 mm
  (2,999 — the model truncates rather than rounds, since a fractional spoke does not
  exist), radial R_max ≈ 45 mm, and the implied serpentine margin (14.3 mm, against the
  13–15 mm measured).
* **The sharpest check is one the plan did not list.** The measured *active footprint
  heights*, 69.0 and 68.6 mm, are inputs nowhere — they fall out of
  `(pairs−1)×pitch + pair_width`. Both land to the micron, so the stack-up and the lane
  count are right simultaneously.
* **DFU capacity is asserted as a bracket, not an equality**, and the test says why: the
  model packs DFUs along the whole lane while the real device does not use the fold ends
  (V5-30 runs 1,000 straight per lane in a 71 mm lane at 60 µm pitch, plus 1,154 round the
  curves). Capacity lands **+6.7%** (V5-30) and **+9.3%** (V5-10). *Over* is the correct
  sign — capacity *below* the built count would be a real failure, since the die
  demonstrably holds that many. Closing the gap needs the deferred fold model, not a fudge
  factor.

### W1-4 — commit the reference devices ✅ `77ac36a`

`reference_devices/` at top level: the three GDS files (`v5_30umV1.1.gds`,
`v5_10umV1.gds`, `V6-30um_v1.2.gds`) plus a short `README.md` carrying the measurement
table above and the script that produced it. **Read the README — it is ground truth for
layout and packing; do not re-derive its numbers from the model.**

### W1-5 — fix `configs/v5_30.yaml` ✅ `6ad1f33` (ruled 2026-08-04)

**Conor's ruling: use 11,565; the 3.7% gap to the GDS does not matter.** So `Mcl` stays at
**693 mm** (which implies 11,550, within 0.13% of 11,565) and the DFU count is *not*
re-cut to the GDS's 11,154. This also keeps `comp_deep_dfu_main_mods`, calibrated at
11,550, valid — see the memory note.

What W1-5 still is, therefore, is **comment hygiene only**: the block
("Mcl=2040 mm, pitch=3 µm, Nmc=680 000", "0.3 µm depth", "1 µm width") is stale template
text describing nothing in the file. Delete it and state the real numbers.

**Two things found while doing it:**

1. **The footprint block was wrong, not merely badly commented.** It declared a 1.5:1
   rectangle for a device that is a 100 × 100 mm square die, and carried two keys W1-1 and
   W1-2 had just made dead. Corrected — footprint never feeds the hydraulic solve, so this
   moves `fits_footprint`, `footprint_area_used` and the schematic and nothing else. The
   config now reproduces the built device: 10 lane pairs, 7.00 mm pitch, 69.0 mm stack
   height, fits, 96.6 cm² of the 100 cm² die.
2. **The model reports 11,549, not 11,550** — `0.693 / 60e-6` lands a hair under in binary
   floating point and the floor takes the hit. One DFU in 11,550 (0.009%). Written into the
   config so nobody re-derives it and files a bug.

`reference_devices/README.md`'s "Open discrepancy" section still claimed the 11,154/11,565
gap "blocks correcting `configs/v5_30.yaml`". It has not since the ruling; rewritten there
to record the ruling and which number belongs where.

**Do not propagate 11,565 into W1-3.** The two numbers answer different questions:

| Number | What it is | Where it belongs |
|---|---|---|
| **11,565** | Conor's device figure, the N the model is driven at | `configs/v5_30.yaml` (`Mcl = 693 mm`) |
| **11,154** | polygons counted in the GDS, residual 0 | W1-3's `packing_capacity` acceptance test |

W1-3 tests that `compute_layout` reproduces *the geometry it is given*. Asserting 11,565
there would be asserting the model against a number the GDS does not contain, which is the
one thing the acceptance tests exist to prevent.

### W1-6 — migrate the study configs off `reserve_border` ✅ `fd99045`

Every checked-in study config pairs `square_side_mm: 100.0` with `reserve_border_mm: 2.0`
— the 96×96-of-100×100 assumption that W1-2 identifies as the entire source of the old
1.66× over-prediction. W1-2 changes the model; without this item the configs keep feeding
it the old overhead.

**Three files, not five**: `study_serpentine_vs_radial` and `study_template` never set the
key. Each of the three keeps a comment saying what replaced it, so it does not come back.
`study_dp15`'s manifold `feed_length_mm` went 96 → 100 — it was explicitly "side minus
border", and there is no border any more.

---

## Wave 2 — changes what the numbers mean

Everything here shifts results. Ends with a schema bump so pre- and post-wave-2 chapters
cannot be silently pooled.

### W2-1 — one rung-resistance implementation *(was B3 + A5; rewritten 2026-08-05)*

> **This item changed shape.** The previous vintage said "Shah & London dropped in favour
> of the single `1 − 0.63·h/w` term … consistency is worth more than the few percent of
> accuracy", and put the impact at ×0.68. Measured against the exact solution, that was
> wrong on both counts: Shah & London used *correctly* is exact, the accuracy gap is not a
> few percent, and ×0.68 is only part of the move. **W2-1 must not land without W2-8's
> viscosity item** — alone it breaks the model's only experimental validation.

One rectangular-duct function:

```
R = Shah & London, normalised as the polynomial is DEFINED:
        R = fRe(α)·µL / (2·A·D_h²)        fRe(α) = 96(1 − 1.3553α + …)
    dimensions ORDERED   h = min, w = max, so α ≤ 1 by construction
    applied PIECEWISE    over the real two-width DFU profile
```

Record in a comment *why* this normalisation and not `f(α)·µL/(w·h³)`: they differ by 2.47×
on V5-30 and by 8× as α → 0, and the wrong one is what shipped. Verify on adoption that the
function reproduces the Fourier series to 4 significant figures — that check is cheap and it
is the only thing standing between this and a third wrong normalisation.

All four sites delegate to it: `stage1_physics.compute_rung_resistance`,
`resistance.rung_resistance`, `manifold._R_rect`, `radial._corr`. **Grep first — Wave 1
found a fourth copy of a formula documented as having three.** Precedent: Phase 1 did
exactly this for the Pareto rule (`viz/plots.py::_pareto_front` → `ranking.pareto_mask`).

The piecewise machinery already exists — `resistance_piecewise` (`resistance.py:58`) +
`rung.profile`; it is simply not the default path.

Also in scope, because they are the same edit:
- Fix the `resistance.rung_resistance` docstring (says `mu_continuous`, uses `mu_dispersed`).
- **Delete the three rejection rules.** Ordered dimensions make `h/w ≤ 1` unconditionally,
  so `manifold._R_rect`'s `h < w` guard, `radial._ASPECT_LIMIT` and
  `hydraulic_resistance_rectangular`'s `denom <= 0` raise all become dead.

**Impact**: the network rung resistance falls to **0.654×** on V5-30 (not 0.68 — that
figure came from comparing the two wrong implementations to each other). Throughput and ΔP
move on every serpentine row, and **frequency goes 25–46% high until the viscosity lands.**
Land W2-1 and the µ change together, or the model spends the interval visibly wrong with an
obvious fudge available.

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

- [ ] `pytest -q` → **560 passed, 3 failed** (the `test_cli` png ones), 5 skipped. *The
      "531 passed, same 5 known failures" this line used to read is stale — Wave 1 added
      tests and removed two failures. The two `test_design_search` failures are gone for a
      reason and must not come back.*
- [ ] Re-run against `experimental_workspaces/po_sweep/data/stage_timings.csv`, reporting
      new Stage-1 and cycle-time agreement at 200–800 mbar
- [ ] **Set the oil viscosity, and DELETE `C_visc`** — in its own workspace, per the
      data-provenance protocol in `CLAUDE.md`. **This replaces the "refit `C_visc`" item
      that used to sit here, which was the wrong instruction.**

      `C_visc` is already 1.0 and does nothing: the 2026-03 fit returned 0.96 ± 0.06, and
      no config overrides the default. The 2× that the fps 25→50 correction implied was
      absorbed on 2026-08-03 by a **mechanism** change — the reset length went from
      `exit_width` (30 µm) to `sqrt(w·h)` (17.3 µm), justified against the measured
      `L_menpoint`. Nothing is left for a refit to do.

      What W2-1 opens up instead is a single physical constant. With the resistance exact
      and geometry as drawn, µ = **83 cP** predicts frequency to ±8% over 200–800 mbar with
      no correction term anywhere (see "What the ×0.68 costs"). Measure the sunflower oil at
      test temperature and use the measurement; if it comes back at 60 cP then the residual
      is geometric and *that* is the finding.

      **The rule this item exists to enforce**: a constant that restores agreement by
      multiplying `ΔP/R` at fixed geometry *is a viscosity*, and must be recorded as one.
      Do not reintroduce `C_visc` under any name. A fitted global scalar encodes the fab and
      fluid state of one device at one condition into every design the studio scores —
      exactly the failure Conor ruled against on 2026-08-05.

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
B0 ✅ -> B1 ✅ -> A4a/A4b ✅ -> Wave 1 ✅ -> Wave 2 -> C -> D-rest -> E
                          \                    │
                           \                   ├─ W2-2 audit  (FIRST — see W1-1)
                            \                  ├─ W2-1 + measured viscosity
                             \                 │     ONE step, not two: W2-1 alone
                              \                │     breaks the po_sweep validation
                               \               └─ W2-8 re-validation
                                └─ D5 unblocked: it needed A4a only, which has landed
```

Batch 1 and Wave 1 are both done, and both were inert as expected: no throughput or ΔP
number moved at a pinned N. 560 pass against 3 known failures (down from 5 — see W1-1).
**Next up is Wave 2**, the risk item: it changes what every number means, and C does not
start until W2-8 passes. Start with W2-2 (the duplicate-formula audit) *before* W2-1 rather
than after — Wave 1 found a fourth copy of a formula documented as having three, and W2-1
edits the site with the most copies of all.

**Note for W2-8's exit criteria**: the `pytest -q` line there still reads "531 passed, same
5 known failures". The current baseline is **560 passed, 3 failed** (the `test_cli` png
ones). The two `test_design_search` failures are gone for a reason and must not come
back.

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

1. ~~**11,154 vs 11,565.**~~ **Closed 2026-08-04 — Conor ruled 11,565, 3.7% is close
   enough.** No reconciliation needed and none is being sought; the likely cause (a
   revision difference — this is V1.1 — or a different convention on the curve DFUs) is
   recorded only so nobody re-opens it. W1-5 is unblocked and reduced to comment hygiene.
   **The GDS's 11,154 still stands as the layout acceptance number in W1-3** — see the
   table there for why the two numbers do not compete.
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
5. *(new)* **Does `active_area_fraction` survive a die-size change?** 0.51/0.64 are
   measured at 100 mm; the family defaults are 63.5 mm. Until the deferred IO model exists,
   W1-2 is only valid at 100 mm. **Still open, but no longer silent**: since `747a3ce` any
   row on another die carries `active_fraction_note()` saying the fraction does not scale.
   Note this bites the *defaults* — a study that does not set `square_side_mm: 100.0` is
   off-calibration by default, so most rows will carry the note until the IO model lands.
