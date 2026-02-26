# StepGen Implementation Plan v2
*Generated 2026-02-26. Updated live as work progresses.*

---

## Steps

| # | Name | Status | Notes |
|---|------|--------|-------|
| 0 | Git init | ⏳ pending | |
| 1 | Layout schematic plot | ⏳ pending | |
| 2 | Mode B flow-flow BC | ⏳ pending | |
| 3 | Design-from-targets sweep | ⏳ pending | |
| 4 | Spatial comparison plot | ⏳ pending | |
| 5 | Robustness in evaluate_candidate | ⏳ pending | |
| 6 | Pareto front plots | ⏳ pending | |

---

## Step 0 — Git init

`git init` in project root. Commit all current files as initial state.

**Done when:** `git log` shows initial commit with all existing source files.

---

## Step 1 — Layout Schematic Plot

**Goal:** Add a matplotlib figure showing the serpentine channel layout to scale.

**New function:** `plot_layout_schematic(config, layout) -> Figure` in `stepgen/viz/plots.py`

**Drawing elements:**
- Footprint bounding box (dashed)
- Each serpentine lane: oil channel (blue rectangle) + water channel (red rectangle), side by side
- Rung region shading between oil and water channels
- Turn arcs at each end
- Dimension annotations: Mcw, Mcd, lane count, total length

**Wired into:** `stepgen/cli.py` `_cmd_report` → saves `layout_schematic.png`

**Files changed:**
- `stepgen/viz/plots.py`
- `stepgen/cli.py`

**Test:** `stepgen report examples/example_single.yaml --out-dir plots/`
→ `plots/layout_schematic.png` present and non-empty

---

## Step 2 — Mode A1: Mode B Flow-Flow BC

**Goal:** Accept `Q_oil + Q_water` as inputs; return required `Po_in` + full iterative result.

**Approach (no matrix changes — linear oracle):**
1. Run `build_ladder_params` + `solve_linear` with Q_oil, Q_water → `P_oil_inlet`
2. Run `iterative_solve(config, Po_in=P_oil_inlet, Qw=Q_water)` → full result
3. Append `derived_Po_in_mbar` to output dict

**CLI:** `stepgen simulate config.yaml --mode B --Qo 1.7 --Qw 15.3`

**Files changed:**
- `stepgen/models/hydraulics.py` — add `linear_solve_from_flows(config, Q_oil_m3s, Q_water_m3s) -> float` returning P_oil_inlet_Pa
- `stepgen/design/sweep.py` — `evaluate_candidate` accepts `Qo_in_mlhr` kwarg; when set, calls linear oracle first
- `stepgen/cli.py` — add `--mode` (A/B) and `--Qo` args to `simulate`
- `stepgen/config.py` — add `Qo_in_mlhr: float | None = None` to `OperatingConfig`

**Verification:**
`stepgen simulate examples/example_single.yaml --mode B --Qo 1.7 --Qw 15.3`
→ `derived_Po_in ≈ 446 mbar`
→ 248 existing tests pass

---

## Step 3 — Design-from-Targets Sweep Engine

**Goal:** User declares targets + constraints → engine finds best geometry.

**Key rule:** `Mcl` is NEVER a sweep input. For each candidate, engine computes:
```
Mcl_max = max Mcl that fits footprint (via compute_layout)
Nmc     = Mcl_max / pitch
```

**New design YAML schema:** `design_targets`, `footprint`, `hard_constraints`,
`soft_constraints`, `optimization_target`, `sweep_ranges` sections.
Junction geometry auto-derived from `target_droplet_um`.

**New CLI command:** `stepgen design design_search.yaml --out design_results.csv`

**New files:**
- `stepgen/design/design_search.py` — `run_design_search(spec) -> pd.DataFrame`
- `stepgen/config.py` — `DesignSearchSpec` dataclass
- `examples/design_search_template.yaml`

**Modified:**
- `stepgen/cli.py` — add `design` subcommand
- `stepgen/viz/plots.py` — add `plot_design_results(df)`

**Verification:**
`stepgen design examples/design_search_template.yaml --out results.csv`
→ CSV with `Mcl_derived`, `Nmc_derived` columns (computed, not input)
→ Results sorted by `Q_total_mlhr` (max_throughput mode)
→ 248 existing tests pass

---

## Step 4 — Spatial Comparison Plot

**Goal:** Show predicted spatial profiles overlaid with measured data at positions
along device (fractional: 0.15, 0.25, 0.5, 0.75, 0.9).

**New function:** `plot_spatial_comparison(config, result, exp_df) -> Figure`
Three panels: pressure profiles | D vs position | frequency vs position.

**Position handling update:** `position` column accepts int (rung index) OR float (0-1 fraction).

**Files changed:**
- `stepgen/viz/plots.py`
- `stepgen/io/experiments.py`
- `stepgen/cli.py` — `_cmd_compare` saves `spatial_comparison.png`

**Verification:** Stubbed test with synthetic positional data.
Real validation requires physical device measurements.

---

## Step 5 — Robustness in evaluate_candidate

**Goal:** Add operating window fields to every evaluated candidate.

**Change:** `evaluate_candidate(..., compute_robustness=False)` — when True, calls
`compute_operating_map` over local Po/Qw grid, appends:
`window_width_mbar, margin_lower_mbar, margin_upper_mbar, robustness_class`

**Enables:** `max_window_width` as optimization target in Step 3.

**Files changed:** `stepgen/design/sweep.py`, `stepgen/cli.py`

---

## Step 6 — Pareto Front Plots

**Goal:** Scatter of all design search candidates with Pareto front highlighted.
User picks their throughput/window tradeoff visually.

**Prerequisite:** Step 5 (window_width_mbar in results).

**New function:** `plot_pareto_front(df, x_col, y_col) -> Figure`

**Files changed:** `stepgen/viz/plots.py`

---

## Execution Log

| Date | Step | Action | Result |
|------|------|--------|--------|
| — | — | Plan created | — |

---

## Notes / Decisions

- Mode B caveat: iterative Q_oil will be ~10-15% below requested (physical, not a bug)
- `max_window_width` as design target deferred until Step 5 complete
- Blowout threshold calibration deferred (needs real experimental data)
- `stepgen_seed/` never modified — reference baseline only
- All 248 existing tests must pass after every step
