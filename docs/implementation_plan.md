# StepGen v1 — Implementation Plan

## Context
Refactor `stepgen_seed/` (linear ladder solver) into a full config-driven
package `stepgen/` with mixed-BC simulation, threshold/hysteresis rung model,
sweep engine, operating maps, layout preview, experiment comparison, and CLI.
`stepgen_seed/` is never modified — it is the reference baseline.

Dependencies: numpy, scipy, pandas, matplotlib, pyyaml. No extras.

---

## Stages

### ✅ Stage A — Summarise seed behaviour
**Files:** `docs/seed_summary.md`
- Inputs/outputs table, resistance formula, matrix sign convention
  (`P_oil = -raw[2::2][::-1]`), 5-point stencil, SI units, seed limitations.

---

### ✅ Stage B1 — Package scaffold + config
**Files added:**
- `stepgen/__init__.py`, `stepgen/models/__init__.py`, `stepgen/design/__init__.py`,
  `stepgen/io/__init__.py`, `stepgen/viz/__init__.py`
- `stepgen/config.py` — `load_config(path) → DeviceConfig`
- `examples/example_single.yaml`
- `pytest.ini`

**Key APIs:** `DeviceConfig`, `FluidConfig`, `GeometryConfig`, `MainChannelConfig`,
`RungConfig`, `JunctionConfig`, `MicrochannelSection`, `OperatingConfig`,
`FootprintConfig`, `ManufacturingConfig`, `DropletModelConfig`.
Unit properties: `.Po_in_Pa`, `.Qw_in_m3s`, `.dP_cap_ow_Pa`. Derived: `GeometryConfig.Nmc`.

---

### ✅ Stage B2 — Linear physics modules + regression tests
**Files added:**
- `stepgen/models/resistance.py` — `hydraulic_resistance_rectangular`,
  `resistance_piecewise`, `rung_resistance`, `main_channel_resistance_per_segment`
- `stepgen/models/hydraulics.py` — `LadderParams`, `LinearSolution`,
  `build_ladder_params`, `generate_conduction_matrix`, `solve_linear`,
  `summarize_solution`
- `tests/__init__.py`
- `tests/test_resistance.py` (7 tests)
- `tests/test_hydraulics_regression.py` (6 tests, golden match vs seed rtol=1e-10)

**Key result:** regression test with Nmc=10 confirms new solver reproduces seed
P_oil, P_water, Q_rungs to floating-point precision.

---

### ✅ Stage C — Mixed boundary-condition simulation
**Files changed:** `stepgen/models/hydraulics.py`, `stepgen/models/resistance.py`,
`stepgen/config.py`, `examples/example_single.yaml`
**Files added:** `tests/test_simulate.py` (21 tests), `tests/test_generator.py` (18 tests)

**New APIs:** `SimResult` dataclass, `_build_mixed_bc_matrix`, `_simulate_pa`,
`simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar=0.0) → SimResult`.

**Physics correction (dead-end oil manifold, AC8/AC9):**
Oil rail has no downstream outlet — it is a dead-end manifold. The oil outlet
BC is a zero-flux Neumann condition, implemented as KCL at node N-1 without a
rightward main-channel segment:
```
A[N-1, N-2] =  1/R_OMc
A[N-1, N-1] = -(1/R_OMc + g_last)
A[N-1, 2N-1] = g_last
```
Water outlet remains Dirichlet (P_water[N-1] = P_out).
Global conservation: Q_oil_total = Σ Q_rungs (all N rungs carry flow including last).
See `docs/physical_model_clarification.md` for derivation.

**Fluid convention correction:**
- `mu_continuous` = **water** = 0.00089 Pa·s (continuous carrier phase)
- `mu_dispersed`  = **oil**   = 0.03452 Pa·s (dispersed droplet phase)
- `main_channel_resistance_per_segment`: R_oil uses `mu_dispersed`; R_water uses `mu_continuous`
- `rung_resistance`: uses `mu_dispersed` (oil flows through rungs)
- All test FluidConfig calls and `examples/example_single.yaml` updated accordingly.

**Key test results:** N=2 analytical closed-form verified; oil conservation AC9
confirmed for N=2,5,10,20,50; dead-end BC physics verified; 56/56 tests pass.

---

### ✅ Stage D — Threshold/hysteresis rung model
**Files created:** `stepgen/models/generator.py`
**Files modified:** `stepgen/models/hydraulics.py` (`_build_mixed_bc_matrix` extended
with `g_rungs`, `rhs_oil`, `rhs_water` per-rung override arrays; `_simulate_pa` exposed)
**Files added:** `tests/test_generator.py` (18 tests)

**New APIs:**
- `RungRegime` enum: `ACTIVE`, `REVERSE`, `OFF`
- `classify_rungs(dP: ndarray, dP_cap_ow_Pa, dP_cap_wo_Pa) → ndarray[RungRegime]`
  Strict inequalities: `dP > dP_cap_ow` → ACTIVE; `dP < -dP_cap_wo` → REVERSE; else OFF.
- `iterative_solve(config, Po_in_mbar=None, Qw_in_mlhr=None, *, max_iter=50) → SimResult`
  Accepts optional overrides (defaults to config.operating values). Raises `ValueError`
  if `max_iter < 1`. Uses `_simulate_pa` as inner solver.
- `_EPSILON_OFF`: small conductance multiplier for OFF rungs (near-zero flow).

**Iteration logic:** Each iteration: classify rungs from ΔP; build per-rung arrays:
- OFF rungs: `g_rungs[i] = g0 * _EPSILON_OFF` (near-zero conductance)
- ACTIVE rungs: `rhs_oil[i] = -g0 * dP_cap_ow_Pa`; `rhs_water[i] = +g0 * dP_cap_ow_Pa`
- REVERSE rungs: `rhs_oil[i] = +g0 * dP_cap_wo_Pa`; `rhs_water[i] = -g0 * dP_cap_wo_Pa`
Converges when classifications unchanged between iterations.

**Key test notes:**
- `test_all_open_matches_simulate`: with thresholds → ∞, iterative_solve ≈ simulate exactly.
- `test_convergence_self_consistency`: converged solution is a fixed point (re-running
  with the same regimes reproduces identical pressures to rtol=1e-8).
- `TestReverseBand` uses `Mcd=20 µm` (not default 100 µm): needed to get sufficient
  R_WMc ≈ 8.2×10⁹ Pa·s/m³ so P_water[0] > P_oil[0] at Qw=2000 mL/hr, Po=200 mbar.

---

### ✅ Stage E — Droplet model + metrics
**Files created:** `stepgen/models/droplets.py`, `stepgen/models/metrics.py`,
`tests/test_metrics.py`

**New APIs:**
- `droplet_diameter(config) → float`  — D = k·w^a·h^b [m]
- `droplet_volume(D) → float`         — V = (π/6)·D³ [m³]
- `droplet_frequency(Q_rung, D) → float | ndarray`  — f = Q/V [Hz]
- `DeviceMetrics` dataclass (13 fields, all SI)
- `compute_metrics(config, result) → DeviceMetrics`

**Metrics computed:** Nmc, Q_oil_total, Q_water_total, Q_per_rung_avg,
Q_uniformity_pct, dP_uniformity_pct, P_peak, active_fraction,
reverse_fraction, off_fraction, D_pred, f_pred_mean, delam_line_load,
collapse_index.

**Uniformity definition:** (max−min)/mean × 100 over ACTIVE rungs; 0 if
no ACTIVE rungs.  collapse_index = Mcw/Mcd.

**Key test results:** 97/97 tests pass; all-active, all-off, and mixed
scenarios verified; mathematical identities (fractions sum to 1,
delam_line_load = P_peak×Mcw, etc.) confirmed.

---

### ✅ Stage F — Schematic layout preview
**Files created:** `stepgen/design/layout.py`, `tests/test_layout.py`

**New APIs:**
- `LayoutResult` dataclass: `fits_footprint`, `num_lanes`, `lane_length`,
  `lane_pair_width`, `lane_pitch`, `total_height`, `footprint_area_used`
- `compute_layout(config) → LayoutResult`

**Geometry model:** two main channels routed side by side in a serpentine.
  lane_length = sqrt(A×AR) − 2×border; lane_pair_width = 2×Mcw + lane_spacing;
  lane_pitch = lane_pair_width + 2×turn_radius; num_lanes = ceil(Mcl/lane_length);
  total_height = (N−1)×pitch + pair_width; fits ↔ total_height ≤ H_useful.

**Key test results:** 121/121 tests pass; ceiling logic, formula identities,
fits/no-fits scenarios, and footprint area formula all verified.

---

### ✅ Stage G — Sweep engine + operating map + plots
**Files created:** `stepgen/design/sweep.py`, `stepgen/design/operating_map.py`,
`stepgen/viz/plots.py`, `stepgen/io/results.py`,
`examples/example_sweep.yaml`, `examples/example_operating_map.yaml`

**New APIs:**
- `evaluate_candidate(config, Po=None, Qw=None) → dict` — full flat record per candidate
- `sweep(configs, Po=None, Qw=None) → pd.DataFrame` — evaluate sequence; errors → NaN row
- `REQUIRED_KEYS` — frozenset of PRD §4.1 mandatory column names
- `_passes_hard_constraints(config, fits_footprint) → bool`
- `OperatingWindow` dataclass: Qw, P_min_ok, P_max_ok, window_width, window_center, is_open
- `OperatingMapResult` dataclass: Po_grid, Qw_grid, 5 metric arrays, windows_strict/relaxed
- `compute_operating_map(config, Po_grid, Qw_grid, *, criteria...) → OperatingMapResult`
- `_widest_contiguous_window(Po_grid, ok_mask, Qw) → OperatingWindow`
- 7 plot functions in `plots.py` (all return `matplotlib.figure.Figure`)
- `save_results(df, path)`, `load_results(path)`, `export_candidate_json(...)`

**Window extraction:** widest contiguous run of Po values satisfying criteria.
Strict: active_fraction, reverse_fraction, Q_unif, dP_unif (+ optional blowout).
Relaxed: active_fraction and reverse_fraction only.

**Key test results:** 177/177 tests pass.

---

### ✅ Stage H — Experiment ingestion + comparison
**Files:** `stepgen/io/experiments.py`, additions to `stepgen/viz/plots.py`

---

### ✅ Stage I — CLI
**Files:** `stepgen/cli.py`, `pyproject.toml` (console_scripts entry-point)

---

### ✅ Stage J — README
**Files:** `README.md`

---

## Execution log

| Stage | Status | Notes |
|-------|--------|-------|
| A | ✅ | `docs/seed_summary.md` written |
| B1 | ✅ | Config + scaffold; `load_config` import check passed |
| B2 | ✅ | Linear solver; 15/15 tests; one physics assumption corrected (P_oil nearly flat, not monotone, due to dominant rung resistance) |
| C  | ✅ | Mixed BC + physics fixes; dead-end oil BC (AC8/AC9); fluid convention corrected; 56/56 tests pass |
| D  | ✅ | Threshold/hysteresis rung model; `generator.py`; 18 tests; fixed-point verified |
| E  | ✅ | Droplet model + metrics; `droplets.py`, `metrics.py`; 41 new tests; 97/97 pass |
| F  | ✅ | Schematic layout preview; `layout.py`; 24 new tests; 121/121 pass |
| G  | ✅ | Sweep + operating map + plots + I/O; 56 new tests; 177/177 pass |
| H  | ✅ | Experiment ingestion + comparison; `experiments.py`, `plot_experiment_comparison`; 41 new tests; 218/218 pass |
| I  | ✅ | CLI (`cli.py`, `pyproject.toml`); 5 subcommands; 30 new tests; 248/248 pass |
| J  | ✅ | README.md — installation, CLI reference, API reference, module layout, physics summary |
