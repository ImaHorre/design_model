# StepGen — Status Assessment & Roadmap
*For review and annotation — generated from planning session 2026-02-26*

---

## Iterative Model: Verdict

**Yes — use iterative as default. Already is the default.**

`evaluate_candidate()` in `stepgen/design/sweep.py:77` already calls `iterative_solve`,
not `simulate`. So all CLI commands (`simulate`, `sweep`, `report`, `map`) already run
the iterative (threshold) solver. The linear solver is used only by `compare_models.py`
as a reference column.

Why iterative is correct:
- Applies capillary thresholds per rung — models actual step-emulsification physics
- Regime classification (active/reverse/off) is only meaningful on iterative results
- 11.8% lower Q_oil than linear at same Po_in (thresholds change effective conductance)
- Fixed-point converged solution is self-consistent

Keep linear as reference in `compare_models.py` only.

---

## What Currently Works

| Goal | CLI command | Status |
|------|------------|--------|
| Simulate one design | `stepgen simulate config.yaml --out result.json` | ✅ |
| Pressure/regime plots | `stepgen report config.yaml --out-dir plots/` | ✅ 5 plots |
| Operating map heatmaps | `stepgen map config.yaml ...grid args... --out-dir maps/` | ✅ |
| Sweep multiple designs | `stepgen sweep cfg1.yaml cfg2.yaml --out sweep.csv` | ✅ (manual YAMLs only) |
| Compare to measurements | `stepgen compare config.yaml experiments.csv --out comp.csv` | ✅ |
| Calibrate droplet model | add `--calibrate` | ✅ |

All 248 tests pass. Physics correct (dead-end oil BC, fluid conventions, iterative thresholds).

---

## Gaps — Ordered by Priority

### A. Design Maker (Design from target)

**A1 — Mode B BC: flow-flow inputs (HIGH) — separate git branch**

- Currently: solver only accepts `Po_in + Qw_in` (Mode A — oil pressure + water flow).
- Need: accept `Qo_in + Qw_in` (both flows) → solver returns required `Po_in` as output.
- Why: say "I want 10% emulsion at 5 mL/hr total" and get back the required oil pressure
  plus full regime/droplet metrics. User may still choose Mode A in production.

- **Implementation approach (simple, no matrix changes):**
  1. Run the existing linear solver with `Q_oil + Q_water` → get `P_oil_inlet`
  2. Feed `Po_in = P_oil_inlet` into `iterative_solve` → get full physically-correct result
  3. Return result plus the derived `Po_in` as an output field
  This is exactly what `compare_models.py` already demonstrates works correctly.
  No matrix builder changes needed — zero risk to existing solver paths.

- **Honest caveat to surface to user:** iterative Q_oil will be ~10-15% below requested
  value (thresholds lower effective conductance). This is physical reality, not a bug.
  For an exact Q_oil match an outer loop would be needed — deferred as unnecessary for
  design use.

- **Branch:** `feature/mode-b-flow-bc` — kept separate so Mode A is never broken.

comment: lets setup git. i was initaly thinking working on a dev brnach but by using what we already do in comapre models anyway it seems less breakable...and might get confusing without reason if swapping dev brances all the time. 

- Files: `stepgen/cli.py` (add `--mode B --Qo` flags to `simulate` and `sweep`),
  `stepgen/models/hydraulics.py` (expose `solve_linear` with Q_oil/Q_water input),
  `stepgen/config.py` (add optional `Qo_in_mlhr` field for YAML-driven Mode B)

---

**A2 — Parameter grid sweep in CLI (HIGH)**

- Currently: `stepgen sweep` takes a list of YAML files — must manually create one per
  candidate. E.g. to sweep 4 mcd values × 3 mcw values you'd need 12 YAML files.
- Need: base YAML + parameter ranges → CLI auto-generates all combinations.
  Proposed syntax:
  ```
  stepgen sweep config.yaml --vary mcd 5,10,15,20 --vary mcw 5,8,12 --out sweep.csv
  ```
- This is the core "design maker" workflow. Without it, sweep is impractical at scale.
- No new physics — just CLI + config variant generation.
- Reuses existing `sweep(configs)` function — just builds the configs list programmatically.
- Files: `stepgen/cli.py` `_cmd_sweep` — add `--vary` argument and combinatoric expansion


comment:hmm maybe we misundersnaf what we would sweep against and how the setup should be for a new design (perhaps we can dicuss furhter). one option is simialr to how legacy/main (ant stepgen seed) handled it is to get the user to prep the features tehy want e.g emulsion ration, droplet sizze(junction geometry), set constraints (area of device, major channel depth etc, minor channel aspect ratio and major channel Aspect atio - which might not be the same ), tehn sweep over things like mcd, mcw (the part pre junction), MCL and Nmc(dependds on MCL and pitch, these vars & the total area all tie in together) to acheive optimised design. weher optimised might mean hgihest throughout possible, or higheste throughout posisble while mainintating a opil P of less than x mbar, or a design that has the largest operating window (where for a change in oil pressure we can still see droplets made (need to determine how droplet blow oout (DP too high) can be determined before we go down this route, might rely on some model feedback first from real tests).....so i was thinking single dconfg ymal and then in that the user can suggest or elect the span of teh sweep? can the model reccommend how to sweep idk how best to ahdnle this?.....option B is to use a predeisgned system as a base/default and then go in and makde edits - i think i prefer option A. 
---

**A3 — Robustness fields in evaluate_candidate (MEDIUM)**

- Currently: `compute_operating_map` exists and works correctly, but is NOT called from
  `evaluate_candidate`. Sweep table lacks `window_width_mbar`.
- Problem: can't build Pareto plots (PRD §6.3) without window_width in sweep results.
- Need: add `compute_robustness=False` flag to `evaluate_candidate`. When True, run a
  local map sweep around the design point (e.g. Po ∈ [0.2×, 3×] design point,
  Qw ∈ [0.5×, 5×]) and append these fields to the row dict:
    - `window_width_mbar`
    - `margin_lower_mbar` (Po_design - P_min_ok)
    - `margin_upper_mbar` (P_max_ok - Po_design)
    - `window_center_mbar`
    - `robustness_class` (ROBUST / MODERATE / TIGHT / CLOSED)
    - `throughput_headroom_pct`
- Files: `stepgen/design/sweep.py`, `stepgen/cli.py` (add `--robustness` flag)

---

**A4 — Pareto front plots (LOW — depends on A3)**

- PRD §6.3: throughput vs window_width, throughput vs uniformity.
- Files: `stepgen/viz/plots.py` — add `plot_pareto_front(df, x_col, y_col)` function

---

### B. Experiment Ingestion (Already works — needs real data, not code)

Full pipeline exists (`stepgen compare`). CSV schema:
```
device_id, Po_in_mbar, Qw_in_mlhr, position, droplet_diameter_um, frequency_hz
```

No code changes needed. Create a CSV from physical device measurements and run:
```
stepgen compare config.yaml real_data.csv --calibrate --out comp.csv
```

comment: yep would love to have this setup. i want to inport experiemtn data on droplet size measured and droplet prodcution freq measured (at 15%, 25%, 50%, 75% 90% etc along the device length and convert that back into a way of comparing the expected result and real result side bys side. like the orinal degin should have a pressure dist graph and the real result will also be able to show soemthign simialr (i think?) we shoudl be able to see from avg drop size variance and avg freq variance along teh legnth of device imperfections in the model. 

W
---

### C. Visual Layout Schematic (MEDIUM — self-contained)

- `compute_layout(config)` gives numbers (num_lanes, fits_footprint) but no drawing.
- PRD §7: schematic blocks showing serpentine routing, oil + water channels, rung region.
- Currently `stepgen report` saves 5 plots — layout schematic would be a 6th.
- Files: `stepgen/viz/plots.py` — add `plot_layout_schematic(config, layout)`;
  `stepgen/cli.py` — call it from `_cmd_report`

---

## MultiBC Mode PRD Amendment

`docs/Multi-BC mode + Operating Window robustness_PRDAmendment.txt` formalises A1 and A3
into acceptance criteria AC10–AC13. Mode C (pressure-pressure, both channels) is lower
priority and deferred.

---

## Recommended Implementation Order

```
1. A2 — Parameter grid sweep CLI     ← unlocks design-maker immediately; no physics risk
2. C  — Layout schematic plot        ← self-contained, high visual value, independent
3. A1 — Mode B (flow-flow BC)        ← separate branch; simple (linear-oracle approach)
4. A3 — Robustness in evaluate_candidate ← uses existing compute_operating_map
5. A4 — Pareto front plots           ← depends on A3
```

---

## Verification After Each Item

**A2:** `stepgen sweep config.yaml --vary mcd 5,10,15,20 --vary mcw 6,8,12 --out sweep.csv`
→ 12 rows in sweep.csv, all PRD §4.1 columns present, passes_hard_constraints column populated

**C:** `stepgen report config.yaml --out-dir plots/`
→ layout_schematic.png appears alongside existing 5 plots

**A1 (branch):** `stepgen simulate config.yaml --mode B --Qo 1.7 --Qw 15.3`
→ returned Po_in ≈ 446 mbar (matches seed oracle for this geometry/flow combination)
→ 248 existing tests still pass on main branch (not broken)

**A3:** `stepgen sweep config.yaml --vary mcd 5,10 --robustness --out sweep.csv`
→ window_width_mbar column present, values positive and finite for passing candidates

**A4:** `stepgen sweep ... --plot-pareto --out-dir pareto/`
→ pareto PNG renders with throughput vs window_width, labelled axes, non-dominated front marked

---


