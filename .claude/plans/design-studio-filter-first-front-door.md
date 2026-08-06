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
| **Wave 2** | ✅ **complete.** W2-2 `3a55423` · W2-1 `71be939` + viscosity `2d51aa6` · W2-1a `76772af` · W2-7 `19ceb65` · W2-3 `1ced3ac` · W2-4 `2f06095` · W2-5 `a1e2e75` · W2-6 `ec606eb` · W2-8 `<this commit>` |
| **C (server)** | **unblocked** — W2-8 passed. Not started |
| **Regime policy** | ⚠️ **changed `7bf5044`.** Ca no longer fails a row; designs are compared against `v_vs_demonstrated` (× the fastest DFU Peak has run). **D5 is re-specified** — read its entry before executing it |
| **D (explorer)** | ✅ **complete.** D1 · D4 · D5 `c20df77` · D2 `6e34dc8` · D6 `7f346f4` · D7 `f54ee49` · D3 `<this commit>` |
| **E** | not started. **E2 is part-done**: D3 defined the stable chapter id it was blocked on |

**Start here**: **C — the server**, the only section left before E. Section D is
complete.

**Baseline is now `pytest -q` → 636 passed, 0 failed, 5 skipped** (from 605/3/5 at
`bf8afd4`). **The known-failures list is empty for the first time.** Both `test_cli`
defects W2-8 diagnosed are fixed in `<this commit>`: `stepgen report` now writes the six
figures it documents (it wrote two; the five profile builders existed and were never
called), and `stepgen map`'s stale count is gone. Both assertions now check the command's
own list — `cli.REPORT_FIGURES` / `cli.MAP_METRICS` — so neither can go stale again.

**Wave 1's lesson closes out three for three.** Every item that sat on the
known-failures list turned out to be a real defect or a stale assertion, never noise:
the two `test_design_search` failures were the duplicated lane-pitch formula (W1-1), and
these three were a half-implemented command plus a count nobody updated.

**Baseline is now `pytest -q` → 599 passed, 3 failed, 5 skipped.** The 3 are still
the `test_cli` ones, but they are **not one thing** — two are a real defect in
`stepgen report` and one is a stale assertion. See W2-8, which diagnoses both.

**Read "What the ×0.68 costs" in Measured evidence before touching W2-1** — and read
the correction stapled to it. The headline still holds: the model matched experiment
because two errors cancelled, W2-1 removes one, and `C_visc ≈ 0.7` was sitting there
ready to hide the difference. **Conor ruled 2026-08-05 that it must not be used, and it
is now deleted** (`71be939`).

**The replacement is NOT the 83 cP this plan proposed.** That figure was fitted at one
water flow rate. Checked against the other two in the same dataset it becomes 69 / 81 /
96 cP at Qw = 5 / 10 / 20 — a "viscosity" that tracks the water flow, i.e. `C_visc`
wearing a physical name. **µ was left at 60 cP, unfitted**, and the residual is located
instead: Stage 1 agrees to −14.5%→+0.9% with no correction term, and what is left lives
in Stage 2+3 and grows with Qw. See W2-8 and
`experimental_workspaces/comp_oil_viscosity/report.md`.

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

> **CORRECTED 2026-08-05, after W2-1 landed.** The diagnosis in this section is right:
> two errors cancelled, and removing one leaves a constant multiplier on `ΔP/R` that is
> dimensionally a viscosity. **The prescription is wrong.** The 83 cP below was fitted at
> a single water flow rate; the same procedure at Qw = 5 and Qw = 20 gives 69 and 96 cP,
> so no single µ exists and the residual is not a material property at all. It is the
> model's ~3× under-response to Qw, which lives in Stage 2+3, not Stage 1.
>
> Two more errors in the numbers below, found while reproducing them:
> - **The frequency table cannot be Qw = 5.** The 2% SDS data at Qw = 5 gives 1.22 /
>   2.13 / 2.94 / 4.17 Hz at 200/300/400/600 and **has no 800 mbar point**. The table's
>   200–800 mbar span is only reachable at Qw = 10 *and* by including the 2.5% NaCas
>   run — a different continuous phase.
> - **`Q_model/Q_meas` is therefore a mixed-condition ratio**, which is why it looked
>   like scatter with no trend. Split by Qw it has a clear trend.
>
> Kept in full because the reasoning — "a constant multiplier on `ΔP/R` at fixed geometry
> *is* a viscosity" — is correct and is what made the disproof possible. See W2-8.

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

### W2-1 — one rung-resistance implementation ✅ `71be939` + `2d51aa6`

> **Landed 2026-08-05, with the viscosity work as one step.** The resistance
> change is exactly as specified below. **The viscosity half did not go as
> planned, and the plan was wrong about the conclusion, not the method** — see
> "What implementation found" at the end of this item and the rewritten W2-8.

**What was found that the plan did not:**

1. **The site count was right for once.** Four, exactly as listed. The one thing
   the table understates: `radial` splits its copy between `_corr` (the shape
   factor) and the formula body inline at the call site, so grepping `_corr`
   finds something that looks harmless.
2. **The verification paid for itself immediately.** The adopted function
   reproduces the Fourier series to **≤0.06% across α ∈ [0.01, 1.0]**, and the
   check is now `tests/test_resistance.py::TestExactSolution` — including a test
   that pins the *wrong* normalisation at 2.47× so nobody restores it.
3. **`compute_rung_resistance` had a second bug the plan did not name.** Beyond
   the normalisation, it used the full `mcl` while the network used
   `mcl × constriction_ratio` through a different formula — so Stage 1 and the
   solve feeding it were two models of the same rung, 25% apart. It now delegates
   to `resistance.rung_resistance`, so there is one answer.
4. **`mcl` had to stay at 4.0 mm.** The measured DFU is 4020 µm end to end, but
   `mcl` is what *layout* reads (`lane_pitch = 2×main + mcl + wall = 7.00 mm`,
   asserted against the GDS in W1-3). Moving it to 4020 µm would have broken a
   Wave 1 acceptance test to fix a hydraulic length the profile now carries
   anyway. Config says why, so nobody "corrects" it.
5. **Impact measured**: R_rung 1.53e18 → **9.981e17** Pa·s/m³ = **0.652×**, against
   the plan's predicted 0.654×. Frequency at 200 mbar / Qw 5 moved 0.967 →
   1.372 Hz.
6. **Five tests encoded the retired formula**, in two files, one of them a studio
   test carrying its own copy of `1−0.63h/w` as an "anchor" — W2-2's bug class,
   inside a test. All now call the library function or the exact series.

**What implementation found about the viscosity — the plan's 83 cP does not
survive.** Fitting µ independently at each water flow rate gives **69 / 81 / 96 cP
at Qw = 5 / 10 / 20**. Each fit is individually good (<15%); pooled it degrades to
39%. A viscosity that climbs 39% as the water flow quadruples is not a viscosity,
and 83 cP is simply the Qw = 10 slice of that surface — `C_visc` under a physical
name. **µ was left at 60 cP, unfitted.** Full argument and provenance in
`experimental_workspaces/comp_oil_viscosity/report.md`; consequences for the exit
criteria are in the rewritten W2-8.

### The item as specified *(kept for the record)* *(was B3 + A5; rewritten 2026-08-05)*

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

### W2-1a — manifold aspect validation ✅ `<this commit>` *(was B2 — moved out of Batch 1)*

**What implementation found**: the verify step below **already passed before any code
was written** — W2-1's deletion of the `h < w` guard is what unblocked it, exactly as
this item predicted. `study_dp15_1000mbar_60x20.yaml` now solves **1368/1368, 0 errors**,
216 of them manifold. So W2-1a's real content was only the second half: decide what is
still worth failing on.

`_validate_geometry` checks two things and deliberately no more:

* non-positive / absurd dimensions — no channel at all;
* anything below the study's own declared `manufacturing.min_wall_um`.

Fab *caps* a design may legitimately exceed (max main depth/width) stay in the `build`
gate per decision 10 and are **not** raised here. A compile-time raise deletes the row
from the table, and a row you cannot see is a row you cannot reason about — which is the
same argument decision 10 makes about vetoes, applied one layer earlier.

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

### W2-2 — audit for other duplicated formulas ✅ `<pending>`

Grep the remaining physical formulas (area, fits, capacity, droplet size) for second
copies before building on them. The rung-resistance audit found **four** copies where the
last vintage of this plan said two; the lane-pitch audit found **three** where it said two.
Assume the count is wrong until grepped.

**Done. What the grep found:**

| Formula | Live copies | Verdict |
|---|---|---|
| rectangular-duct resistance | **4** | the plan's count is right — for the first time. W2-1 |
| exit capillary number `µ(q/wh)/γ` | **3**, one per family | ✅ consolidated → `base.exit_capillary_number` |
| droplet power law `k·w^a·h^b` | **4** | ✅ radial/manifold now call `intent.droplet_for_junction` |
| droplet volume `(π/6)D³` | **4** | ✅ all now call `droplets.droplet_volume` |
| lane stack-up / active extent / area | 1 each | **Wave 1 held** — all four sites still delegate |

1. **The rung-resistance count is finally exact**: `models/resistance.py`,
   `stage_wise_v3/stage1_physics.py`, `families/radial.py` (`_corr` + the formula body
   inline at `radial.py:325`), `families/manifold.py::_R_rect`. No fifth. The one thing
   the inventory table understates is that `radial` splits the formula across two places —
   the shape factor in `_corr`, the `12µL/wh³` body at the call site — so a grep for
   `_corr` alone finds a function that looks harmless.
2. **`regime_Ca` was written three times.** Identical arithmetic, but this is the gate the
   whole studio scores against and the one A4a just attached per-row γ provenance to.
   Consolidated, with the guard: it returns `None`, never `0.0`, when Ca is undefined — a
   missing Ca scores grey, a zero Ca scores **green**, which would be a clean bill of
   health for a device nobody evaluated.
3. **Three things found and deliberately not fixed** (recorded so they are not re-found):
   - `design/design_search.py:300` sets `D_pred_um = exit_depth_um`, commented "rough
     proxy". That is not a copy of the power law, it is a **different droplet-size model**
     living in the search path. Whether the search should use the real one is a design
     question, not a de-duplication.
   - `radial` and `manifold` construct `DropletModelConfig()` with its defaults, so **a
     study cannot change `k`/`a`/`b` for those two families** — serpentine reads the
     config's. Consolidating made this visible; fixing it is a separate change.
   - Outside `stepgen/`: `designs/radial/radial_hydraulics.py` carries six more copies of
     the `1−0.63h/w` form and `experimental_workspaces/comp_manifold_parametrization/`
     one. Neither is imported by the library. Workspace analysis scripts are **frozen
     records** under `CLAUDE.md`'s provenance rules and must not be retro-edited; after
     W2-1 they disagree with the library, and that is the correct state for a record of
     what was run.

### W2-3 — N from packing ✅ `<this commit>` *(was A2)*

**What implementation found:**

1. **The capacity arithmetic had to be extracted first, or this item would have
   created W2-2's bug class while closing it.** `packing_capacity()` computed
   `lanes_max` / `per_lane` inline from a *compiled* config, and `fill_fraction`
   needs the same numbers *before* a DFU count exists. Writing it a second time was
   the obvious move and the wrong one. It is now
   `design/layout.py::dfu_capacity`, which both the input and the readout call.
2. **Capacity does not depend on N at all** — lane pitch comes from main width,
   DFU array and wall; lane length is the routable extent. That is what makes
   `fill_fraction` possible as an input, and it is worth stating because it is not
   obvious from `compute_layout`, which takes N as its first move.
3. **The footprint block had to move above the DFU-count block** in
   `serpentine.compile`, since capacity needs the die. No behaviour change; it is
   the same construction, earlier.
4. **`fits_square` is true by construction at `ff = 1.0`, and there is now a test
   that says so** — `test_fill_fraction_one_fits_by_construction`. It is an
   invariant assertion, exactly as this item predicted: if it ever fails,
   `dfu_capacity` and `compute_layout` have drifted apart, which is precisely what
   making them one function prevents.
5. Measured: a 100 mm die at 200×1000 µm main, 4 mm rung, 120 µm pitch holds
   **5,950 DFUs**; `ff = 1.0` consumes 96.6 cm² of the 100 cm² die.

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

### W2-4 — carry provenance to scoring ✅ `<this commit>` *(decision 10, generalised)*

**What implementation found:**

1. **`Study.intent_plan` was the right handle and it already carried what was
   needed** — `generated` / `user_supplied` block names. `geometry_is_pinned(study,
   family)` is nine lines. No per-leaf provenance was necessary, because all three
   build sub-gates are functions of the *family geometry block*, so the answer is
   per family, not per field.
2. **The default direction matters and is deliberate**: when provenance is
   unavailable, assume **pinned**. Guessing "generated" would let the tool veto a
   number the user typed — the exact failure decision 10 exists to prevent.
   Guessing "pinned" costs a chip instead of a red.
3. **Nothing in `_METRIC_FIELDS` is a geometric *input*.** Throughput, flatness
   and Ca are solved outcomes; drive pressure is an operating axis. So "threshold
   gates scoring a geometric quantity" turned out to be the empty set, and the
   `build` composite is the whole of this item's surface.
4. **A third state was needed: `off`.** With gating now provenance-driven rather
   than opt-in, a study that genuinely wants a gate silenced had no way to say so
   — `required` was the only word the schema knew. `build: { no_crossing: off }`
   silences it, and unlike a demotion it emits no chip, because that is the point.
5. **It is inert on every checked-in study.** `study_dp15` (hand-written): 1176
   red of 1368, before and after. `study_intent_deep_dfu` (generated): 187 red of
   216, identical scored both ways. No build sub-gate fails anywhere in the
   current configs — which is *why* the silent-`no_crossing` hole was never
   observed. The mechanism was live; nothing had tripped it yet.

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

### W2-5 — bend radius + wall-at-turn as reported metrics ✅ `<this commit>` *(was A3)*

**What implementation found:**

1. **On the real V5-30 the fold radius is 3,500 µm and `turn_radius` says 500 µm** —
   7× out. The row now carries a note saying so. This is W1-1's coincidence seen
   from the other end: `2 × 500 µm` reproduced the measured 1.0 mm wall exactly,
   which is what made the old stack-up look right for the wrong reason.
2. **`wall_at_turn` shows the turn is not where a fold stack collides.** Folds
   alternate ends, so successive folds at one end connect lanes (1,2), (3,4), …
   — centres `2p` apart, closest approach `p − Mcw` = **6,000 µm** on V5-30,
   against a straight-section wall of 1,000 µm. The straight section is six times
   tighter. Worth having precisely because it says "stop worrying about this".
3. **Scope held deliberately**: the routing *inside* a lane pair, where the two
   mains flanking the DFU array each turn at their own radius, is not modelled.
   That is the deferred full layout rebuild (fold as a real channel with its own
   ΔP), and approximating it here would have been a guess dressed as a metric.
4. Guarded by a test that moves `turn_radius` 60× and asserts the fold radius does
   not budge — the same shape of test W1-1 used, for the same reason.

`CommonMetrics` fields, no threshold. Note the tangle W1-1 partly resolves: for a real 180°
fold the centreline radius is ≈ half the lane pitch, so turn radius is *determined by*
pitch, not a free input that adds to it.

### W2-6 — schema bump ✅ `<this commit>`

`SCHEMA_VERSION = 2` in `workbook.py`, on the sidecar (`schema_version`), on the
payload (`schemaVersion`) and printed in the chapter's provenance line beside the
commit hash. A test asserts the two serialisers agree — a version on only one of
them would be worse than none, because the surface a reader actually filters would
be the unlabelled one.

**The rule, written where it will be read** (the constant's docstring): bump when a
number that survives into a chapter would *mean* something different. Version 1 is
everything through Wave 1; version 2 is Wave 2, because W2-1 moved throughput, ΔP,
frequency and exit Ca on every serpentine row and W1-2 had already changed what
`area_used_cm2` means.

**An absent field means version 1, not "current".** Pre-Wave-2 chapters cannot be
retro-stamped, and treating missing as current is exactly the silent pooling this
exists to prevent. D3's guard reads both this and `git_hash`.

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

### W2-8 — exit criteria: re-validate before C starts ✅ `<this commit>` *(was W2-7)*

**Wave 2 is complete. C is unblocked.**

| Criterion | Result |
|---|---|
| `pytest -q` | **599 passed, 3 failed, 5 skipped** (from 560/3/5). 39 tests added, no new failures |
| po_sweep re-validation | done — see the viscosity item; Stage 1 **−14.5% → +0.9%** at Qw = 5 with zero correction terms |
| `C_visc` deleted | done, `71be939`, and a config that sets it now raises |
| oil viscosity set | **deliberately not set** — the fit is refuted, see below |

**The ±8% target was not met and must not be chased.** It is unreachable without a
per-condition fitted µ, which is `C_visc` under another name. What was achieved
instead: Stage 1 to within 15% at the config's own operating condition, with no
correction term anywhere in the model, and the residual **located** rather than
absorbed. The data cannot support better — its two independent measures of Q
disagree with each other by 16–26%.

#### The three "known failures" — looked at, as instructed, and they are two different things

Wave 1's lesson was that a known-failures list is where bugs hide. Checked:

1. **`TestReport::test_creates_png_files` and `test_pressure_profiles_png_exists`
   are a REAL DEFECT, not noise.** `stepgen report` emits **2 PNGs** where
   `CLAUDE.md` and `configs/v5_30.yaml` both document **6** ("layout schematic +
   5 simulation plots"). `_cmd_report` (`cli.py:234-246`) calls
   `plot_layout_schematic` and `plot_pressure_sweep` and nothing else —
   `plot_pressure_profiles`, `plot_rung_dP`, `plot_rung_flows`,
   `plot_rung_frequencies` and `plot_combined_profiles` all **exist in
   `viz/plots.py` and are never called.** The tests are right and the command is
   incomplete. Wiring five existing functions is a small, contained fix, but it is
   a CLI change nothing in Wave 2 asked for — **left for a decision, not done
   silently.**
2. **`TestMap::test_creates_png_files` is a stale test**, failing the other way:
   `stepgen map` now emits **8** PNGs and the test pins exactly 5. The command
   grew metrics; nobody updated the assertion.

Neither is flaky, and neither was caused by Wave 2.

Wave 2 is not done until:

- [ ] `pytest -q` → at least **560 passed, 3 failed** (the `test_cli` png ones), 5 skipped.
      *The "531 passed, same 5 known failures" this line used to read is stale — Wave 1 added
      tests and removed two failures. The two `test_design_search` failures are gone for a
      reason and must not come back.* After W2-1 the count is **577 passed, 3 failed,
      5 skipped**.
- [x] Re-run against `experimental_workspaces/po_sweep/data/stage_timings.csv`, reporting
      new Stage-1 and cycle-time agreement ✅ — see the viscosity item below.
      **Correction to this line: the sweep does not reach 800 mbar in the fluid system
      the config describes.** At 2% SDS the SDS data stops at 600 mbar; the file's only
      800 mbar rows are 2.5% sodium caseinate at Qw = 10 — a different continuous phase.
      The plan's "200–800 mbar" frequency table therefore *had* to include that point.
      **Do not restore an 800 mbar claim about this device from this dataset.**
- [x] **DELETE `C_visc`** ✅ `71be939`. Gone from `StageWiseV3Config`, gone from
      `stage1_physics`, and a config that still sets `stage1_viscosity_correction`
      now **raises** rather than being silently ignored. Pinned by
      `tests/test_stage_wise_v3_phase1.py::TestCViscStaysDeleted`.
- [x] **Set the oil viscosity** ✅ `2d51aa6` — **and the answer is: do not.**

      > **This is the item the wave turned on, and the plan had it half right.**
      > The method was right (ask what µ the data implies). The conclusion was
      > wrong, because 83 cP had only ever been checked at one Qw.

      `experimental_workspaces/comp_oil_viscosity/` fits µ independently at each
      water flow rate in the same dataset:

      ```
      Qw =  5 mL/hr  ->  69 cP   (4 pressures, worst error  9.2%)
      Qw = 10 mL/hr  ->  81 cP   (4 pressures, worst error  9.5%)
      Qw = 20 mL/hr  ->  96 cP   (2 pressures, worst error 13.7%)
      pooled         ->  79 cP   (worst error 38.7%)
      ```

      Every per-Qw fit is excellent, which is exactly what condemns it: **a
      viscosity that rises 39% as the water flow quadruples is not a viscosity.**
      The plan's 83 cP is the Qw = 10 slice. Adopting it would have re-created
      `C_visc` with a physical name on it — the precise failure the ruling exists
      to prevent, arriving through the door the ruling opened.

      **µ stays at 60 cP**, the literature value for sunflower oil, unfitted.
      Nothing in the model was tuned.

      **Where the residual is**, at 60 cP and Qw = 5 (the config's condition):

      ```
      Stage 1     -14.5% -> +0.9%  across 200-600 mbar, improving with pressure
      Stage 2+3    +2.9% -> -41.5%, worsening with BOTH Po and Qw
      ```

      Stage 1 is the only stage the resistance and the viscosity control, so that
      first line is W2-1's real result: **exact resistance, measured DFU profile,
      measured reset length, literature viscosity, zero correction terms.** The
      rest is the model under-responding to Qw by ~3× (the device loses 28% of
      production from Qw 5→10 at 200 mbar; the model loses 5.5%) — which
      `qw_sweep` found independently from the other side — plus a 50 fps
      quantisation floor at 600 mbar.

      **A geometric error would be Qw-independent.** This one is not, so the
      plan's counterfactual ("if it comes back near 60 cP the residual is
      geometric and THAT is the finding") resolves one step further: it is neither
      viscosity nor geometry. It is the Stage-2 growth model and the water-side
      loading, and that is the next physics change — not a constant.

      **The oil still has to go on a viscometer.** Until it does, 60 cP is a
      literature value carrying an unquantified error, and temperature is not even
      recorded in the data file (±5 °C ≈ ±30% on µ).

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

- **C1.** `stepgen studio-serve` — FastAPI + uvicorn. ✅ `<this commit>`

  `stepgen/studio/server.py`. Routes as specified: `GET /` form, `POST /preview`
  (expand only), `POST /run` (solve → score → diagnose → `write_workbook` →
  `write_book_index`), plus `GET /book`, `GET /book/{name}`, `GET /configs`. `/run` calls
  exactly the pipeline `_cmd_study` calls — nothing re-implemented. 12 tests in
  `tests/test_studio_server.py`, and the app was booted under real uvicorn (TestClient
  does not exercise it).

  Packaging bug fixed: `serve = ["fastapi", "uvicorn"]` added as its own extra, not folded
  into `[ui]` — the server replaces Streamlit rather than extending it.

  **Two things worth knowing for C2:**
  - `from __future__ import annotations` + FastAPI's `eval_str=True` means request models
    and response classes **must be module-level**. As locals inside `create_app` every
    route raises `NameError` at decoration time. This is why `server.py` imports fastapi
    at module scope; `_cmd_studio_serve` checks for the extra first so a lean install
    never reaches the ImportError.
  - **An unknown family parses and expands cleanly.** `load_study_text` does not consult
    the registry; the failure only surfaces per-point inside `run_study`, which records it
    and carries on. Correct for a run, useless for a preview — so `/preview` checks
    `list_families()` itself. C2's form should not assume validation it did not do.
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

  **The fluid region — ruled 2026-08-06, supersedes the "fluid presets + swap A/B"
  sketch above.** Two number fields, `µ_dispersed` and `µ_continuous`, are the *whole*
  hydraulic control. Verified: `resistance.py:149` builds the rung from `mu_dispersed`,
  `:170` the oil main from `mu_dispersed`, `:173` the continuous main from
  `mu_continuous`, and nothing else in the ladder reads a fluid property.

  **`phase_system` is a label with no physics behind it.** All 12 reads are display —
  `channel_labels` (`config.py:50-59`), two CLI prints, a plot title, studio grouping.
  Nothing branches on it in the solve. So `mu_dispersed: 0.00089, mu_continuous: 0.06,
  phase_system: o/w` is a physically W/O device, solved correctly as W/O, and mislabelled
  everywhere. That is not cosmetic: `study.py:161 _fluid_tag` makes it the row
  discriminator, so a wrong label changes how rows **group**, and `decide.group_by` is
  what separates a design from a condition. The two checked-in fluid blocks stay
  consistent today only because they were written together by hand — independent number
  fields remove that.

  **So: a toggle that sets the label, physics from the µ values.** The o/w ↔ w/o click is
  explicitly cosmetic — it renames, it does not swap the viscosities. Validate it against
  the µ values and warn on mismatch rather than deriving it, since "which phase is
  dispersed" is not recoverable from magnitudes in general (it happens to be here only
  because one phase is always oil and one always water).

  **The rest of the eventual fluid A:** γ is **not** inert — live in Ca (`base.py:257`)
  and stage-2 — but gates nothing since the gate moved to `v_vs_demonstrated`, where it
  cancels. Expose it as optional, carrying its unmeasured caveat. Density and contact
  angle are genuinely absent: `rho_continuous` is not a `FluidConfig` field at all, both
  uses are `getattr(config.fluids, 'rho_continuous', 1000.0)` so they silently always get
  water, and both call sites are diagnostic-only paths. A form field for either would be
  inert today.

  **Note on the block:** two free viscosity fields are a slightly *wider* door than the
  swap button was — a swap offers two vetted systems, a number field accepts 60 cP against
  a long main and scores it silently.

  **Blocked on the reverse-flow guard** (see *Explicitly deferred* below). The swap button
  is what makes W/O one click instead of a hand-edited YAML, and a W/O row on a long,
  narrow main scores today with no disclosure that a third of its rungs run backwards.
  C1 and C3 are not blocked.
- **C3.** House sweep-level defaults as a checked-in, reviewable file — shown read-only in
  the form, with an "adjust axes" expander for full control. Carries the measured
  ms/point per family for C2's estimate.

---

## D — the results explorer

D1, most of D2 and D4 landed in `912c74c`, in the chapter rather than the server. What
remains:

- **D1.** ✅ *Landed.* Columnar payload + client-side filter/sort, no round-trip.
- **D2.** ✅ `<this commit>` *(the rest of it — filter bar had verdict + numeric limits)*

  The three-state **gate / report / off** control is in the rail, one select per build
  sub-gate, plus the "you set this geometry" marker. **What implementation found:**

  1. **The control has four states, not three, and that is what makes it safe.** The
     fourth is **"as scored"**, the default, which uses each row's *own* resolved state.
     Without it a global three-state control would flatten the per-family answer
     `geometry_is_pinned` gives — a chapter with a generated serpentine and a pinned
     manifold has two different correct defaults, and one dropdown cannot hold both.
  2. **How this does not breach D7.** Python ships `vnb` (the verdict with `build` left
     out, `ScoredRow.verdict_without_build`) and the sub-gate pass/fail booleans; the
     browser takes the worse of `vnb` and a build category that is a **lookup**, never a
     comparison. Every category on the page is still one Python computed. Written at the
     top of `INTERACTIVE_JS` and guarded by a test that greps that string for a threshold
     comparison — the regex has to allow *reading* `th.green` (the plot draws the ceiling
     as a band) while banning a comparison against it.
  3. **Verified against real chapters, not just unit tests.** The browser's recombination
     was re-run in node over the payload extracted from two built chapters:
     **0 mismatches against Python's verdict on 352 rows (`study_my_designs`) and 1368
     (`study_dp15`)** with no override. And the control does real work: flipping
     `manufacturable` to *gate* on `study_my_designs` moves **170 rows orange → red** —
     that is the 400 µm main depth against the study's own 200 µm cap, previously visible
     only as a chip.
  4. **`no_crossing` correctly never appears on a serpentine chapter.** Serpentine and
     radial both set it `None` (N-A by construction); only manifold computes it. The
     multi-family `study_dp15` chapter offers all three. This is worth recording because
     W2-4's regression was *about* `no_crossing`, and "the control is missing" looks like
     the same bug returning when it is the opposite.
  5. **A second silence of the same shape was still live, one panel down.** `_gate_table`
     in the drill-down showed the build cell green with an **empty note** when a failure
     had been demoted — the drill-down exists to explain the colour and was mute about the
     only thing needing explanation. W2-4 fixed this in the chips and not here. Fixed.
  6. **`BUILD_GATES` is now one definition** (key → attribute + human label) read by
     `score_metrics`, the payload and the drill-down. The labels had already been written
     twice; a third copy in the UI is exactly W2-2's bug class arriving in the studio.
  7. **No schema bump.** W2-6's rule is *bump when a number that survives into a chapter
     would mean something different*. Nothing's meaning moved — the invariant test proves
     default verdicts are bit-identical; the payload only gained fields. Schema stays at 3.
  8. **Per-axis provenance does not exist and was not invented.** `IntentPlan` records
     generated / user_supplied per *block*, so "you set this" is answerable per family,
     not per field — the same conclusion W2-4 reached about the gates. The marker
     therefore sits on the rail ("⚪ you set this geometry") and on the row, not on
     individual axis controls. Building per-field provenance to decorate a dropdown would
     be new machinery for a cosmetic gain.
- **D3.** ✅ `<this commit>`

  Swept range under every numeric limit, an out-of-range warning that names the fix, a
  `chapter_id` + `parent` in the sidecar, `stepgen study --extends PARENT.json`, and
  `load_lineage()` with the git_hash + schema_version guard.

  **What implementation found:**

  1. **`chapter_id` must be a CONTENT hash, and the first version was wrong twice.**
     Hashing the run timestamp gave *two ids for one chapter* — and at one-second
     resolution it **collided anyway**: a parent and its child, built back to back in a
     test, got the same id and `load_lineage` reported a loop. It now hashes title +
     study text + git_hash + **the labels of every point solved**. Consequences, all of
     them the right ones: extending an axis changes the labels so a child gets a new id;
     **re-running the identical study at the same commit gives the same id**, because
     same inputs and same model means one chapter and a second copy of it; and declaring
     a chapter to extend one with identical content is therefore a **detectable loop**
     rather than a chapter silently pooled with itself. Pinned by
     `test_the_id_is_content_not_wall_clock`.
  2. **The guard fires at creation, not at read.** `stepgen study --extends` calls
     `load_lineage` immediately and prints the refusal, because a lineage that cannot be
     pooled is worth knowing about while re-running the parent is still cheap — not
     months later when someone tries to read the two together.
  3. **"An absent `schema_version` means version 1" is now enforced, not just written
     down.** `_assert_poolable` defaults to 1, never to the current version, and a test
     deletes the key from a parent sidecar and asserts the refusal. That default is the
     whole reason W2-6 exists and it is one `.get(k, SCHEMA_VERSION)` away from being
     undone.
  4. **The out-of-range warning is one-sided, deliberately.** Only a `min` above
     everything swept or a `max` below it is flagged: those cannot be answered from this
     chapter, and an empty result there means **untried, not impossible** — which is the
     distinction decision 6 exists to draw. A bound that is merely wider than the sweep
     is loose, not unanswerable, and flagging it would train the reader to ignore the
     warning.
  5. **"Offer to extend that axis" is a command, not a button.** The chapter is a static
     file; it cannot run a solve. It prints the exact
     `stepgen study <source> --extends <this chapter>.json` to run, using the study path
     carried in the payload. When C lands, that is the invocation the button fires.
  6. **Ranges are computed over ALL rows, never the filtered subset.** A swept range that
     shrank as the reader filtered would defeat the one thing it is for. `n` (distinct
     values) ships beside lo/hi, because "200–1000 mbar" is a different claim at eleven
     levels than at two.
  7. Verified end to end: an 11-point parent extended to 33 points reports
     `Lineage: 2 chapters, poolable`; editing the parent's `git_hash` produces the
     refusal naming both commits and saying to re-run the parent.
- **D4.** ✅ *Landed* — click-to-pin, a Pinned-runs table carrying every design and
  condition axis with verdict and reason, "pinned only" on the plot, and "mark best" over
  the *visible* rows (`6db6405`). Phase 3 schematic in the detail panel still to wire.
- **D5.** ✅ `<this commit>` *(re-specified 2026-08-05; executed against the re-spec)*

  **What implementation found:**

  1. **The retired ceiling, read back in units of experience, is `8.35x`.** Under one
     fluid the two predicates are the *same* predicate up to a constant — `Ca = µv/γ`,
     so `Ca ≤ 0.0125` at µ = 60 cP and γ = 5 mN/m **is** `v ≤ 1.0417 mm/s`, which is
     8.35 × `V_EXIT_DEMONSTRATED_MAX`. Gating at `k = 8.35` reproduces the old gate's
     operating points exactly. That is the sharpest statement of what the ruling was
     about: the borrowed ceiling was not cautious, it licensed driving every DFU
     **eight times harder than anything Peak has made work**, and it took that licence
     from a constant nobody has measured. Pinned by
     `test_the_retired_ca_ceiling_expressed_in_units_of_experience`.
  2. **The ranking inversion survives, and at k = 1 it is larger.** Re-measured
     post-Wave-2 (the plan's 18.87 / 4.35 / 3.29 predate W2-1's 0.65× resistance):

     ```
     60x20 exit, N=1000, o/w      wide main 200x1000   narrow main 100x500
     ungated at 1000 mbar            20.43 mL/hr           6.414 mL/hr
     gated v<=1     Po/Q          40 mbar / 0.1822    100 mbar / 0.2703   <- inverts
     gated v<=10    Po/Q         200 mbar / 3.557     700 mbar / 4.366    <- inverts
     retired Ca<=0.0125           200 mbar / 3.557     700 mbar / 4.366    identical
     ```

     The wide main wins ungated by 3.2× and loses under every gate. The effect is a
     **velocity** effect, exactly as the re-spec predicted, and it does not depend on
     which multiple you pick.
  3. **The function was renamed, not just re-pointed**: `ca_gated_summary` →
     `gated_summary`, because a name saying "ca" on something Ca no longer decides is
     the next reader's trap. `ca_max`/`gamma_ref`/`gamma_range` → one
     `max_v_vs_demonstrated` (default 1.0). Only one caller existed
     (`scripts/compare_designs.py`), so no compatibility shim was warranted — grepped,
     including the workspaces.
  4. **`regime_Ca_gated` and `gamma_Nm` were KEPT as reported columns**, and this is a
     deliberate reading of "γ-robustness stays where it is": the gated point still shows
     its Ca and the γ behind it, and `compare_designs.py` prints how many gated points
     the literature ceiling *would* have failed, at the solved γ and at the pessimistic
     3 mN/m. A footnote, not a verdict. `passes_at_gamma_lo` is gone from the summary;
     `ca_limited_operating_point` / `CaLimit` (the real γ-band analysis) is untouched.
  5. **A frame with no `v_vs_demonstrated` column raises rather than gating nothing.**
     A pre-2026-08 frame passed silently would read as *every design is inside
     experience*, which is the worst available answer — the same argument A4a made
     about a Ca detached from its γ.
  6. **On the checked-in `study_my_designs.yaml`, only 4 of 88 rows gate in at k = 1**,
     all of them the 60×20 exit in o/w at 40 mbar. That is not a defect in the designs;
     it is what "nobody has run a DFU past 0.1247 mm/s" costs when stated honestly. The
     config now says so, and points at `--max-v`.
  7. **Downstream text falsified and fixed**: `study_my_designs.yaml`'s fluids block
     claimed γ "alone decides the Ca verdict" and the operating block quoted per-phase
     "Ca ceiling 93–195 / 374–678 mbar" windows. Both are dead. Grepped for `ca_max`,
     `Ca gate`, `Ca ceiling`, `SE window`; the remaining hits are `SE_CEILING_CA`
     scoring prose (still true — Ca is still *scored*, capped at orange) and
     `ca_limited_operating_point` (untouched by design).

  *Re-spec follows, for the record:*

  Conor's call: **judge a design by how far it is from experiments we have already
  run, not by a threshold resting on a γ nobody has measured.** Landed in
  `7bf5044`. Consequences for this item:

  1. **`regime_Ca` can no longer fail a row** — it and `v_vs_demonstrated` are
     capped at orange (`scoring.CAPPED_AT_ORANGE`). So "the Ca gate as a live
     control" is gating something that no longer gates. That framing is dead.
  2. **What replaces it**: `v_vs_demonstrated` — exit velocity as a multiple of
     `V_EXIT_DEMONSTRATED_MAX = 0.1247 mm/s`, the fastest DFU Peak has run with
     monodisperse output. **γ cancels exactly in a ratio**, and against the same
     fluid so does µ, so this number carries no unmeasured constant at all.
  3. **The valuable half of D5 survives intact and should still be built**:
     `ca_gated_summary()` already re-solves nothing and already reports
     `Po_gated_mbar` / `throughput_gated` / `Po_next_failed` per design. Re-point
     it from `Ca ≤ ca_max` to `v_vs_demonstrated ≤ k` (default k = 1, "stay inside
     what we have run"). The ranking inversion that justified D5 is a *velocity*
     effect and survives the change unaltered.
  4. **`passes_at_gamma_lo` becomes unnecessary** in the gated summary — there is
     no γ in the predicate any more. Keep γ-robustness where it is, as an
     analysis of what the *literature* threshold would say; it is no longer load-
     bearing for a verdict.

  Also settled while re-specifying, and worth not re-deriving: **Peak sits
  2,500–27,000,000× below the inertial (Weber) branch** of
  `@montessori2020-step-emulsification`, so the jetting/We half of that literature
  does not apply to these devices at all. Only the viscous branch is in play.

  *Original text follows, superseded on the ceiling-control framing only:*

  **The Ca gate as a live control.** `ca_gated_summary(frame, ca_max, gamma_ref)`
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
- **D6.** ✅ `<this commit>`

  **What implementation found:**

  1. **`Po_min_production_mbar` is a post-pass, not a solve option** — `stepgen study
     --production-threshold`, `studio.run.fill_production_thresholds()`. Computing it
     inside `solve()` would have meant either paying per point or threading a
     "compute this once" flag through the whole family interface. A post-pass gets
     "once per design" for free, because the cache key *is* the design. **Measured on
     `study_my_designs`: 32 designs for 352 rows — an 11× saving**, and the collapse is
     exactly the 11 swept pressures.
  2. **The cache key is built from the compile inputs, not the label.** A label is a
     display string; two designs that render identically must not share an answer. Key
     is `(family, params, fluids, footprint, manufacturing, Qw)`.
  3. **`target_emulsion_pct` defeats the caching by construction, and that is correct.**
     When Qw is *derived* per point it differs at every pressure, so the key is unique
     per row and the cost returns to ~40 solves per point. The threshold genuinely does
     differ there. Said out loud in the docstring, because it is the difference between
     seconds and minutes.
  4. **Serpentine only.** Radial and manifold have no threshold model, so those rows stay
     `None` / grey rather than being given a borrowed number.
  5. **The two lists are now guarded by a test, not merged.** Merging them was the
     obvious move and the wrong one: they hold different tuples for different jobs (a
     table column has a header; a plot axis has a log-by-default flag), and collapsing
     them would have meant one list with two half-used shapes. Instead
     `test_the_two_metric_lists_have_not_drifted` asserts every plot axis is a column,
     every column is a plot axis **unless it is in `_TABLE_ONLY` with a written reason**,
     and every key in either is a real `CommonMetrics` field. `t_stage1_s` had left the
     plot menu for no reason; a key can now only leave by someone stating why.
     Five deliberate exclusions came out of doing this — `Qw_mlhr`, `v_exit_mps`,
     `hub_budget_pct`, `bend_radius_um`, `wall_at_turn_um`.
  6. **`stage1_fraction` is deliberately not a column**, recorded as `_NOT_A_COLUMN` so it
     is not re-added by someone noticing it missing. It is V_reset/V_drop, a ratio of two
     geometric volumes — **constant down every column in this model**, so 350 identical
     numbers. The measurement is *not* constant (0.63/0.63/0.65/0.54/0.46 across
     200→800 mbar) and that drift is physics the model does not have, which is exactly
     why it is a diagnostic of the model and never a guard on a design. The caveat now
     prints where the number actually appears, in `compare_designs.py`.
- **D7.** ✅ `<this commit>` *(the JS half landed with D2 — `6e34dc8`)*

  **What implementation found:**

  1. **There is one real duplication and it had already gone wrong.** The rule for
     colouring the discounted margin was written twice **and the two copies
     disagreed**: `workbook._margin_cell` reddened below 0.2 and said nothing above it,
     while `ui.category_frame` banded at 0.2 *and* 0.5. **The same study, the same
     number, two different colours depending on which tool you opened it in.** Now one
     definition — `scoring.margin_category` / `MARGIN_MARGINAL` / `MARGIN_COMFORTABLE`.
     The chapter gains the orange band as a result; that is an intentional appearance
     change and the price of the two surfaces agreeing.
  2. **The filter surfaces were already clean.** `ui.py` filters on `df["Verdict"]`,
     which *is* `ScoredRow.overall`; the chapter JS filters on `row.verdict`. Neither
     compares a value against a bound. The consolidation D7 was written to do turned out
     to be one function, not a module — and the thing worth building was the guard.
  3. **The invariant is now stated as a rule with a carve-out that survives contact.**
     A module may **read** a scoring block — to print a bound in the gate table, to draw
     a plot band, to sweep a verdict across γ — but may not **apply** one; anything
     reaching into the block must delegate the comparison to `scoring.py`. That
     distinction was forced by `diagnosis.ca_gamma_robustness`, which reads the
     `regime_Ca` spec and then calls `scoring._score_threshold` rather than writing `>`.
     A blunter "nothing may read the scoring block" test would have flagged the one
     module doing it correctly.
  4. Three tests: the bands, the two surfaces agreeing on the same rows, and the
     read-vs-apply rule across every `stepgen/studio/*.py`.
  5. **`studio-serve` does not exist yet**, so the "three surfaces" are two. When C
     lands it inherits the rule and the test covers it automatically — the test walks
     the directory rather than naming files.

---

## E — provenance

- **E1.** Sweep → chapter, reusing `write_workbook()` unchanged.
- **E2.** Filter views as small saved JSON (thresholds, sort, demoted gates, starred rows),
  shareable as a URL. ~~**Needs a stable chapter id** — undefined today~~ — **D3 defined
  it**: `workbook.chapter_id()`, a content hash over title + study text + git_hash + the
  labels of every point solved, recorded as `chapter_id` in every sidecar. A view can now
  name the chapter it points at, and two chapters with the same id genuinely hold the same
  rows. Still needs to serialise the in-chapter filter state, which since D2 also includes
  the three-state gate overrides (`S.gate`).
- **E3.** Refine sweep → child chapter recording parent + the starred designs it was built
  around. Same lineage mechanism as D3.

---

## Sequencing

```
B0 ✅ -> B1 ✅ -> A4a/A4b ✅ -> Wave 1 ✅ -> Wave 2 ✅ -> D ✅ -> C -> E
                          \                    │
                           \                   ├─ W2-2 audit  (FIRST — see W1-1)
                            \                  ├─ W2-1 + measured viscosity
                             \                 │     ONE step, not two: W2-1 alone
                              \                │     breaks the po_sweep validation
                               \               └─ W2-8 re-validation
                                └─ D5 unblocked: it needed A4a only, which has landed
```

**Batch 1, Wave 1 and Wave 2 are all done.** Batch 1 and Wave 1 were inert, as designed.
Wave 2 was not, also as designed: the rung resistance fell to 0.65× on V5-30, so
throughput, ΔP, frequency and exit Ca moved on every serpentine row, and the chapter
schema was bumped to 2 so pre- and post-wave chapters cannot be pooled. Baseline
**599 passed, 3 failed, 5 skipped**.

**What Wave 2 turned out to be about.** On paper it was a resistance fix with a viscosity
attached. In practice the resistance fix was the easy half — one function, verified against
the exact series — and the viscosity was the item that mattered, because checking the
plan's own 83 cP against the two conditions it had never been tested at **refuted it**. The
lesson generalises past this wave: *a constant that fits one condition perfectly is not
evidence; it is an untested hypothesis with a good disguise.* The cross-check cost one
afternoon and was worth more than everything else in the wave.

**Section D is complete** (D5 `c20df77`, D2 `6e34dc8`, D6 `7f346f4`, D7 `f54ee49`,
D3 this commit). What it turned out to be about, in one line each:

* **D5** re-pointed the operating gate off Ca onto `v_vs_demonstrated`, and what it made
  visible was not the Ca ceiling but **how far past recorded experience every
  large-droplet design sits** — 4 of 88 rows in the checked-in study survive `k = 1`, and
  the ceiling it replaced was **8.35× demonstrated**.
* **D2** made decision 10 movable rather than fixed, and the safety of that rests on a
  single testable equivalence: with no override the browser reproduces Python's verdict
  on every row (verified on 352 and 1368 real rows).
* **D6** cost one column and bought a guard — the two metric lists can no longer drift
  without someone writing down why.
* **D7** found that the only rule genuinely duplicated across surfaces was the margin
  banding, **and the two copies already disagreed**.
* **D3** found that a chapter's identity is its content, not when it was run — the
  timestamp version gave two ids for one chapter and collided between a real parent and
  child anyway.

**Next**: C, the server — the last section before E.

~~**Also outstanding, found during W2-8 and not fixed**: `stepgen report` emits 2 of the 6
PNGs it documents.~~ **Fixed 2026-08-05.** The five profile builders needed one solve at a
single operating point — and the `iterative_solve` import was already sitting at the top of
`_cmd_report`, unused, which is what the missing solve looked like from the outside. The
operating point is printed, because a spatial profile with no stated Po/Qw is a picture of
an unnamed device. `stepgen map`'s stale assertion went with it. **`pytest -q` is now
clean: 636 passed, 0 failed, 5 skipped.**

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
- **Reverse-flow hard constraint.** *(deferred 2026-08-06, after measurement — Conor ruled
  "move on")* **Prerequisite for C2, not for C1/C3.**

  The defect is real but narrow. `configs/wo_v5_30.yaml` at Po=200 returns
  `passes_hard_constraints=True` with `rev=0.315 off=0.327 act=0.358` (Qw=5) and
  `rev=0.465` (Qw=20); `configs/v5_30.yaml` o/w is `rev=0.000` at Qw=5,10,20. The three
  fractions appear nowhere under `stepgen/studio/`. `_check_hard_constraints` has exactly
  one call site (`design/sweep.py:257`), so promoting `reverse_fraction` to a hard
  constraint is a contained signature change. `tests/test_studio.py:1069` guards
  `workbook._COLUMNS` against `interactive.PLOT_METRICS` and will fire — update both,
  don't weaken it.

  **Four claims in the 2026-08-05 kickoff prompt are FALSE — measured, do not re-inherit:**
  1. *"`dP_avg` is a mean taken across a sign change."* No. `metrics.py:140` is
     `np.mean(dP[active_mask])` — active rungs only, as are `Q_spread_pct`,
     `dP_spread_pct`, `Q_per_rung_avg`, `f_pred_*`. The numbers are correct statistics
     over a subpopulation; the defect is that the row presents them as device-level
     without disclosure. It is a **labelling** hole, not corrupted arithmetic.
  2. *"Half of every row `study_my_designs.yaml` produces is already degenerate W/O."*
     No. All 352 expanded points measured: `reverse_fraction > 0` in **0/176 o/w and
     0/176 w/o**. That study's main is 20–160 mm at 2000×400 µm; `wo_v5_30`'s is 693 mm
     at 1000×200 µm. At 60 cP the study geometry needs a ~2560 mm main — 16× its longest
     swept value — before reverse appears at all, and then only 0.035.
  3. *"`production_threshold_mbar` can report a producing pressure for a device running
     half backwards."* No. Its default is `active_fraction_min=1.0`, the three regime
     masks partition the rungs, so `active == 1.0` forces `reverse == 0.0`. Both callers
     (`serpentine.py:904`, `studio/run.py:157`) use the default. Already safe — it
     returns `None` for a degenerate device.
  4. *"Urgent."* Nothing on a live config produces a wrong number today.

  **Threshold — still open, and it is a tolerance, not a physical line.** Conor's framing
  (2026-08-06): experimentally *any* reverse flow is device-killing, but the model could
  red-flag a run that worked in the lab, so a buffer is right — not zero. Candidates:
  **0.10**, matching `operating_map.py:154 reverse_fraction_max` — already this codebase's
  line for an acceptable operating point, and `evaluate_candidate` reaches it via
  `_compute_robustness_fields`, so a different number lets a row pass while its own
  robustness window says the point is out. Or **0.01**, clear of single-rung noise
  (1/11549 = 8.7e-5) and far below the 0.31 signal. Not zero — brittle.

  **Adjacent, possibly the bigger hole, and reachable from the live study:** at 60 cP w/o,
  Po=200, `off_fraction` goes 0.000 → 0.130 → 0.576 → 0.798 as `main.length_mm` goes
  160 → 320 → 640 → 1280. `main.length_mm` is a swept axis in `study_my_designs.yaml`.
  A device with 58% of its DFUs dead still reports throughput and flatness over the
  surviving 42%; `min_active_fraction` only *soft*-flags it, and only on the
  `design_search.py:205` path — not the Studio path.

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
