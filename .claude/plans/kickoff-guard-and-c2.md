# Kickoff — the reverse-flow guard, then C2 (the form)

Two parts, in this order. Part 1 is a correctness fix and is the prerequisite for
Part 2's fluid region. Do not start Part 2 until Part 1's tests are green.

**Anchor**: HEAD `2463848`. Baseline **667 passed, 5 skipped, 0 failed** — confirm that
before changing anything. The known-failures list is empty; a new failure is a new bug,
not an acceptable cost.

**Read first**: `.claude/plans/design-studio-filter-first-front-door.md` — section C
(C1 ✅, C3 ✅, C2 is yours), and the *Explicitly deferred* entry "Reverse-flow hard
constraint", which carries the measurements below and the corrections to an earlier
kickoff prompt whose claims did not survive measurement.

---

## Part 1 — promote reverse flow to a hard constraint

### The defect, measured 2026-08-06

`configs/wo_v5_30.yaml` (693 mm main, 1000 × 200 µm, 50 cP continuous) at Po = 200:

```
Qw= 5:  rev=0.315 off=0.327 act=0.358  dP_spread=188%  Q_spread=293%  passes=True
Qw=20:  rev=0.465 off=0.225 act=0.310                                 passes=True
```

`configs/v5_30.yaml` (o/w, same geometry, 0.89 cP) at Po = 200, Qw = 5/10/20:

```
rev=0.000 off=0.000 act=1.000  passes=True
```

A row where a third of the rungs run backwards reports `passes_hard_constraints=True`
and presents device-level numbers computed over the 36% that are active, with nothing
saying so.

### Scope — three things

1. **Promote `reverse_fraction` to a hard constraint.**
   `_check_hard_constraints(config, fits_footprint)` is `design/sweep.py:40` with
   **exactly one call site**, `design/sweep.py:257`. Changing its signature is the task;
   the change is contained.

2. **Carry `reverse_fraction`, `off_fraction`, `active_fraction` into the Studio chapter.**
   They appear **nowhere** under `stepgen/studio/` today — verify with grep before you
   start; if that has changed, stop and report. The chain is
   `evaluate_candidate` row → `CommonMetrics` (`families/base.py`) → `to_row()` → frame →
   workbook, and `CommonMetrics` does not carry them, which is why they are absent
   downstream.

   Registry is `studio/scoring.py:67 _METRIC_FIELDS` (iterated at `scoring.py:431`).

3. **Decide whether `workbook.SCHEMA_VERSION` needs a bump.** It is **3**
   (`workbook.py:78`). Adding columns is not the same as moving numbers — argue it either
   way in the commit, do not bump reflexively. An absent field still means version 1 and
   `load_lineage` reads it (`workbook.py:1713`, `:1768`).

### The threshold — a judgement call, deliberately left open

Conor's framing: *experimentally any reverse flow is device-killing, but the model could
red-flag a run that worked in the lab, so a buffer is right — not zero.* It is a
tolerance, not a physical line. State your choice and justify it in the commit.

- **0.10** matches `operating_map.py:154 reverse_fraction_max`, already this codebase's
  line for an acceptable operating point, used by both strict and relaxed window
  criteria. `evaluate_candidate` already reaches it via `_compute_robustness_fields`, so
  a different number lets a row pass hard constraints while its own robustness window
  says the point is out.
- **0.01** is clear of single-rung noise (1/11549 = 8.7e-5) and far below the 0.31 signal.
- **Not zero** — one rung flipping near the capillary threshold would fail a whole design.

### Traps

- **`tests/test_studio.py:1069` will fire.** It guards `workbook._COLUMNS` (`:94`)
  against `interactive.PLOT_METRICS` (`interactive.py:55`) precisely to stop these lists
  drifting. That is the test doing its job — update both lists, do not weaken it.
  `ui.py:62 _VALUE_KEYS` derives from `_COLUMNS` and follows automatically.
- **Name collision — read this before you grep.** `SERPENTINE_ACTIVE_FRACTION = 0.51`,
  `RADIAL_ACTIVE_FRACTION = 0.64`, `MANIFOLD_ACTIVE_FRACTION = 0.51`
  (`families/base.py:158-160`) and `active_fraction_note()` are about **routable die
  area**. They have nothing to do with the rung-regime `active_fraction`. Grepping
  `active_fraction` under `stepgen/families/` will make it look like this is half done.
  It is not.
- The only regime-fraction check that exists today is a **soft** flag on
  `active_fraction` at `design/design_search.py:205` — and that is a path the Studio does
  not use.

### Four claims from the earlier (2026-08-05) kickoff prompt are FALSE

Measured. Do not re-inherit them:

1. *"`dP_avg` is a mean taken across a sign change."* No — `metrics.py:140` is
   `np.mean(dP[active_mask])`, active rungs only, as are `Q_spread_pct`, `dP_spread_pct`,
   `Q_per_rung_avg`, `f_pred_*` (`metrics.py:104-140`). The numbers are correct statistics
   over a subpopulation. The defect is **labelling** — the row presents them as
   device-level without disclosure — not corrupted arithmetic.
2. *"Half of every row `study_my_designs.yaml` produces is already degenerate W/O."* No.
   All 352 expanded points measured: `reverse_fraction > 0` in **0/176 o/w and 0/176 w/o**.
   That study's main is 20–160 mm at 2000 × 400 µm; `wo_v5_30`'s is 693 mm at 1000 × 200 µm.
   At 60 cP the study geometry needs a ~2560 mm main — 16× its longest swept value —
   before reverse appears at all, and then only 0.035.
3. *"`production_threshold_mbar` can report a producing pressure for a device running half
   backwards."* No. Default is `active_fraction_min=1.0` (`serpentine.py:414`), the three
   regime masks partition the rungs (`metrics.py:96-102`), so `active == 1.0` forces
   `reverse == 0.0`. Both callers (`serpentine.py:904`, `studio/run.py:157`) use the
   default. Already safe — it returns `None` for a degenerate device.
4. *"Urgent."* Nothing on a live config produces a wrong number today.

### Adjacent — decide whether it is in scope, do not silently skip it

`off_fraction` is arguably the bigger hole and **is** reachable from the live study. At
60 cP w/o, Po = 200, as `main.length_mm` goes 160 → 320 → 640 → 1280:

```
off = 0.000 → 0.130 → 0.576 → 0.798     (act = 1.000 → 0.870 → 0.424 → 0.202)
```

`main.length_mm` is a swept axis in `configs/study_my_designs.yaml`. A device with 58% of
its DFUs dead still reports throughput and flatness over the surviving 42%. Argue whether
a mostly-off device should fail hard, flag soft, or stay as-is — and say which you chose.

---

## Part 2 — C2, the form

Three regions, per the plan's decision 11. `len(study.points)` is known before solving,
so the count is exact.

```
DESIGNS (set, concatenated)     30x10 | 60x20 | 30x20 | 15x10
FLUIDS  (set, concatenated)     µ_disp / µ_cont  + o/w<->w/o toggle
AXES    (grid, crossed)         Po 200..1200 (6 levels) + coarse/fine dial
                                points = 4 x 2 x 6 = 48
```

**This form writes the YAML shape `configs/study_my_designs.yaml` already uses. Read that
file first — its comments are the spec**, including the set-vs-axis rule (**lists
concatenate, dicts cross**) and the shallow-merge trap on `<<: *rung` (writing
`rung: { upstream_width_um: 40 }` under a `<<: *ladder` design REPLACES the whole rung
block and silently drops the rest). Exits live in the set region, never on the dial.

### The fluid region — ruled 2026-08-06, supersedes the "fluid presets + swap A/B" sketch

- **Two number fields, `µ_dispersed` and `µ_continuous`, are the WHOLE hydraulic control.**
  Verified: `resistance.py:149` builds the rung from `mu_dispersed`, `:170` the oil main
  from `mu_dispersed`, `:173` the continuous main from `mu_continuous`. Nothing else in
  the ladder reads a fluid property.
- **`phase_system` is a label that branches no physics.** All 12 reads are display —
  `channel_labels` (`config.py:50-59`), two CLI prints, a plot title, studio grouping.
  **But `study.py:161 _fluid_tag` makes it the row discriminator**, so a label that
  disagrees with the viscosities changes how rows *group*, and `decide.group_by` is what
  separates a design from a condition.
- **So the o/w ↔ w/o click is explicitly cosmetic: it renames, it does not swap the
  viscosities.** Validate it against the µ values and warn on mismatch rather than
  deriving it — "which phase is dispersed" is not recoverable from magnitudes in general
  (it happens to be here only because one phase is always oil and one always water).
- **γ is live but gates nothing** — used in Ca (`families/base.py:257`) and stage-2, and
  the operating gate is `v_vs_demonstrated`, in which γ cancels. Expose it as optional,
  carrying its unmeasured caveat.
- **Density and contact angle are absent.** `rho_continuous` is not a `FluidConfig` field
  at all; both uses are `getattr(config.fluids, 'rho_continuous', 1000.0)` so they
  silently always get water, and both call sites are diagnostic-only. A form field for
  either would be inert today. Do not add one.

### What C1 and C3 already give you

- `stepgen/studio/server.py` — `create_app()`, routes `/`, `/preview`, `/run`, `/book`,
  `/book/{name}`, `/configs`, `/defaults`. `POST /run` calls exactly the pipeline
  `_cmd_study` calls. The form page is inline `_FORM_HTML`; C2 replaces its single
  textarea with the three regions and keeps the textarea as the generated-YAML view.
- `configs/studio_defaults.yaml` + `stepgen/studio/defaults.py` — what the form starts
  from, and `SolveCost` for the point-count estimate. **The "adjust axes" expander from
  C3's sketch belongs to C2** — it needs the axis region to adjust.
- `tests/test_studio_server.py` (14) and `tests/test_studio_defaults.py` (17).

### Two traps found building C1

- **`from __future__ import annotations` + FastAPI's `eval_str=True` means request models
  and response classes MUST be module-level.** Declared as locals inside `create_app`,
  every route raises `NameError` at decoration time.
- **An unknown family parses and expands cleanly.** `load_study_text` does not consult the
  registry; the failure only surfaces per-point inside `run_study`, which records it and
  carries on. `/preview` therefore checks `list_families()` itself. The form must not
  assume validation it did not do.

---

## Explicitly out of scope

- Any change to `stepgen/models/resistance.py` or how the continuous main is built. The
  physics is probably right — 50 cP down a 693 mm channel really does cost that.
- Any W/O calibration. There is **no** W/O experimental data — deferred deliberately.
- Any new fitted constant anywhere. `stage1_viscosity_correction` raises on purpose
  (`tests/test_stage_wise_v3_phase1.py::TestCViscStaysDeleted`); do not add a sibling.
- Section E (provenance — saved filter views, refine-to-child-chapter). Separate work.
- `.claude/plans/qw-response-and-water-side-loading.md` is **RETIRED** — the water main is
  worth 1–4% of the pressure budget and cannot carry the 22% effect it was written to
  explain. Read it for context only; do not execute it.

## Done means

- `pytest -q` at **≥ 667 passed, 0 failed, 5 skipped**. Confirm the baseline BEFORE
  changing anything.
- A W/O row at Po=200, Qw=5 and Qw=20 no longer passes hard constraints — shown as actual
  output, **before and after**.
- An O/W row at Po=200, Qw=5/10/20 is **UNCHANGED**. `reverse_fraction` is 0.000 there and
  nothing about O/W scoring may move. Show this; it is the regression that matters.
- `configs/study_my_designs.yaml` — all 352 points — still shows `reverse_fraction > 0` in
  **0/352**, and its scoring is unchanged. This is the live study; it must not move.
- The form produces a YAML that `load_study_text` parses and `run_study` solves, shown by
  actually running one.
- Report actual test results. Commit per meaningful unit, staging only intentionally
  modified files. **Never `git add .`.**

## Judgement calls left to you — state each, do not inherit one

1. The reverse-flow threshold (see above).
2. Whether `SCHEMA_VERSION` bumps.
3. Whether `off_fraction` is in scope, and if so whether it fails hard or flags soft.
4. Whether the o/w↔w/o mismatch warning blocks submission or just warns.
