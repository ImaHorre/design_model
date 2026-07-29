# Plan: Large-DFU Stage-1 Hydraulic Screen (`comp_large_dfu_stage1_screen`)

## Context

The Stage-Wise V3 model's implemented physics (Stage 1 Poiseuille refill, Stage 2
Rcrit snap-off) are calibrated against existing device geometries (e.g. V5-30,
10-30 µm scale DFUs). Before extending the model or investing in Stage-2/cyclic
modeling for much larger, deeper DFUs (a design direction for higher per-DFU
throughput), we want a cheap first-pass screen: **can a ladder of large/deep O/W
DFUs even hydraulically refill (Stage 1) fast enough at a practical drive
pressure?** Droplet formation itself is treated as instantaneous for this screen
— it intentionally does not model Stage 2/cyclic snap-off, which is deferred to
a follow-up workspace for whichever candidates survive this screen.

This is a new **computational** workspace (model-only, no experimental data),
built from a simplified relation rather than the full `stage_wise_v3` model:

```
t_S1 = V_reset * R_DFU / DP_eff
V_reset = sqrt(exit_width * exit_depth) * exit_width * exit_depth
DP_eff  = DP_DFU - 12 mbar   (12 mbar = fitted Stage-1 capillary back-pressure)
pass:   t_S1 <= 1 s for EVERY DFU in the ladder (all must have DP_eff > 0)
```

No changes to core `stepgen` — all screen-specific logic lives in the workspace's
`analysis.py`, reusing existing solver/resistance primitives directly.

## Confirmed reuse points (read and verified against source)

- `stepgen/config.py` — `DeviceConfig`, `GeometryConfig`, `MainChannelConfig`,
  `RungConfig`, `JunctionConfig`, `MicrochannelSection`, `FluidConfig`,
  `OperatingConfig` are built **directly in Python per candidate** (no
  per-candidate YAML, no `load_config`). `RungConfig.profile` (a tuple of
  `MicrochannelSection(length, width, depth)`) implements the piecewise 90:10
  DFU profile. `mcd`/`mcw`/`mcl`/`constriction_ratio` on `RungConfig` are
  required fields but are **ignored by the resistance calc whenever `profile`
  is non-empty** (`stepgen/models/resistance.py::rung_resistance`) — set them
  to sensible placeholders (mcd=depth, mcw=upstream width, mcl=DFU length,
  constriction_ratio=1.0).
- `stepgen/models/resistance.py::resistance_piecewise(sections, mu)` (line 58)
  — call directly with the same 2-section profile + `mu_dispersed` to get the
  scalar `R_DFU` for the `t_S1` formula. This is the same function
  `rung_resistance()` uses internally, so the network solve and the screen's
  `R_DFU` are guaranteed consistent.
- `stepgen/models/hydraulics.py::simulate(config, Po_in_mbar, Qw_in_mlhr,
  P_out_mbar)` (line 354) — the plain steady-state mixed-BC ladder solver.
  **Not** `generator.iterative_solve()` — that applies Stage-2-style capillary
  threshold classification via `config.droplet_model.dP_cap_ow/wo`, which is
  irrelevant since Stage 2 is deferred here. Returns `SimResult(P_oil, P_water,
  Q_rungs, x_positions, ...)`, each shape `(Nmc,)` where `Nmc = N_DFU` (via
  `Nmc_override`). `DP_DFU = P_oil - P_water` per rung, in Pa.
- **Not used**: `stepgen/models/metrics.py::droplet_frequency` and
  `model_comparison.py` — both compute whole-cycle droplet frequency from
  `Q_rungs`, not a Stage-1-only refill-time criterion.
- Workspace conventions from `experimental_workspaces/_template/BRIEF.md`,
  `experimental_workspaces/comp_wo_hydraulics/` (comparable existing
  computational workspace), and `scripts/new_workspace.py`.

## Geometry construction (per candidate)

- `exit_depth = DFU_depth`; `exit_width = 3 * DFU_depth`
- `pitch = 2 * exit_width`
- `main.Mcl = N_DFU * pitch` (informational only — `Nmc_override` fixes
  `Nmc = N_DFU` directly, so `Mcl` never affects the solve)
- `main.Mcw = min(5 * main_depth, 5000e-6)` (capped at 5 mm); `main.Mcd = main_depth`
- Rung profile: section 1 = `0.9 * DFU_length` @ width = `upstream_AR * DFU_depth`,
  section 2 = `0.1 * DFU_length` @ width = `3 * DFU_depth`, both at
  `depth = DFU_depth` (matches the exit, no discontinuity into the junction)
- Fluids: `mu_dispersed=0.06 Pa·s` (oil), `mu_continuous=0.00089 Pa·s` (water),
  `gamma=0.015 N/m`, `phase_system="o/w"`, `emulsion_ratio=0.3` (nominal,
  unused by the plain hydraulic solve)
- `Qw_in_mlhr = 5.0` fixed; `Po_in_mbar` swept 50–1000 mbar in 50 mbar steps
  (20 points); `P_out_mbar = 0`
- All other `DeviceConfig` fields (`footprint`, `manufacturing`,
  `droplet_model`, `operating_map`, `stage_wise`, `stage_wise_v3`) left at
  dataclass defaults — none are read by this static Stage-1-only solve.

Sweep grid: `N_DFU=[10,100,1000]` × `DFU_depth_um=[20,30,40,50]` ×
`DFU_length_mm=[0.5,1,2,4]` × `upstream_AR=[1,1.5,2,3]` ×
`main_depth_um=[200,300,400]` = 576 candidates × 20 pressures = 11,520 sparse
solves (small banded systems, `Nmc` up to 1000 — expected to run quickly).

## Files to create

```
experimental_workspaces/comp_large_dfu_stage1_screen/
  BRIEF.md
  study_config.yaml
  analysis.py
  report.md                          (stub; authored narratively after first run)
  snapshots/
    study_config_2026-07-06.yaml     (verbatim copy, written by analysis.py at run start)
    run_manifest.md
  results/
    candidate_summary.csv            (576 rows — one per candidate)
    per_pressure_long.csv             (11,520 rows — one per candidate x pressure)
    results_summary.md
  figures/
    fig_01_pressure_requirement_vs_depth.png
    fig_02_pressure_requirement_vs_length.png
    fig_03_pressure_requirement_vs_N.png
    fig_04_uniformity_vs_main_channel_size.png
    fig_05_top_candidate_pressure_profiles.png
```

No `data/` folder — no experimental data in this workspace; state this
explicitly in `BRIEF.md` and `run_manifest.md` rather than leaving it implicit.

### `study_config.yaml`

Top-level keys: `fluids` (mu_dispersed, mu_continuous, gamma, phase_system,
emulsion_ratio), `operating` (Qw_in_mlhr, P_out_mbar, `Po_sweep_mbar: {min,
max, step}`), `sweep_grid` (the five lists above), `geometry_rules`
(exit_width_factor=3, pitch_factor=2, main_width_factor=5,
main_width_cap_um=5000, section1/2_length_frac=0.9/0.1, section2_width_factor=3),
`stage1_screen` (stage1_backpressure_mbar=12.0, t_S1_max_s=1.0,
ideal_pressure_mbar=500, hard_pressure_mbar=1000), `laplace_diagnostic`
(theta_deg=30 — used only for a secondary diagnostic capillary estimate
`P_cap_laplace = gamma*cos(theta)*(1/depth + 1/exit_width)`, compared against
but never substituted for the flat 12 mbar constant), and `sanity_checks`
(v5_30_exit_width_um=30, v5_30_exit_depth_um=10,
v5_30_observed_reset_length_um=[19,21]). All sweep arrays use `_um`/`_mm`
suffixes (matching `configs/design_search_10um.yaml` convention); SI
conversion happens only in `analysis.py`, never stored in the YAML.

### `analysis.py`

Plain `yaml.safe_load` (no dataclass wrapper) for `study_config.yaml`, plus
`numpy`/`pandas`/`matplotlib` (Agg backend, 150 DPI).

- `build_candidates(study) -> list[dict]`: `itertools.product` over the five
  sweep lists, `enumerate`d into `candidate_id`; one dict per combination.
- `build_device_config(candidate, study) -> DeviceConfig`: applies the
  geometry construction rules above; unit conversions (`um`→m, `mm`→m,
  `mbar`→Pa where relevant) happen here.
- `screen_candidate(config, pressures_mbar, study) -> dict`: computes
  `R_DFU = resistance_piecewise(config.geometry.rung.profile,
  config.fluids.mu_dispersed)` once; `V_reset` once; then for each
  `Po_mbar` calls `simulate(config, Po_in_mbar=Po_mbar,
  Qw_in_mlhr=study["operating"]["Qw_in_mlhr"], P_out_mbar=...)`, computes
  `DP_DFU = P_oil - P_water`, `DP_eff = DP_DFU - 1200 Pa`,
  `active = DP_eff > 0`, `t_S1 = V_reset*R_DFU/DP_eff` where active else
  `inf`, and records active_fraction / DP_DFU mean-min-max / t_S1
  mean-min-max / `passes = active.all() and t_S1.max() <= t_S1_max_s`.
- `main()`:
  1. Load config; copy `study_config.yaml` → `snapshots/study_config_<date>.yaml`;
     write `snapshots/run_manifest.md` with `git rev-parse HEAD` + exact command.
  2. Run `sanity_check_v530_reset_length(study)` standalone (prints
     `sqrt(30*10)=17.3 um` vs observed 19–21 um range; loose assert only,
     not a hard failure — this is a formula sanity check, **not** a sweep
     candidate, since V5-30's 30×10 µm exit isn't in this sweep's 20–50 µm
     depth grid).
  3. Loop candidates → build config → screen → accumulate per-pressure rows
     and per-candidate summary rows.
  4. Write `results/candidate_summary.csv`, `results/per_pressure_long.csv`.
  5. Write `results/results_summary.md` (pass-rate at 500/1000 mbar,
     best/worst candidates, the correlation checks from the Verification
     section below).
  6. Generate the 5 figures.

`candidate_summary.csv` columns: `candidate_id, candidate_key, N_DFU,
DFU_depth_um, DFU_length_mm, upstream_AR, main_depth_um, exit_width_um,
exit_depth_um, pitch_um, main_Mcw_um, main_Mcl_m, R_DFU_Pa_s_per_m3,
V_reset_m3, P_cap_laplace_mbar, min_passing_pressure_mbar, pass_at_ideal_500,
pass_at_hard_1000, active_fraction_at_500mbar, t_S1_mean/min/max_at_500mbar_s,
t_S1_spread_at_500mbar, active_fraction_at_1000mbar,
t_S1_mean/min/max_at_1000mbar_s, t_S1_spread_at_1000mbar`.

`per_pressure_long.csv` columns: `candidate_id, candidate_key, N_DFU,
DFU_depth_um, DFU_length_mm, upstream_AR, main_depth_um, Po_in_mbar,
active_fraction, DP_DFU_mean/min/max_Pa, t_S1_mean/min/max_s, passes`.

Full per-rung arrays are **not** persisted (would balloon for N_DFU=1000);
`fig_05` re-simulates the handful of selected top candidates directly.

Plots:
- `fig_01`: rows=N_DFU, cols=DFU_length_mm, x=DFU_depth_um, lines=upstream_AR,
  y=min_passing_pressure_mbar.
- `fig_02`: same grid transposed (x=DFU_length_mm).
- `fig_03`: rows=DFU_depth_um, cols=upstream_AR, x=N_DFU (log), lines=DFU_length_mm.
- `fig_04`: x=main_depth_um, y=t_S1_spread_at_1000mbar, faceted by
  DFU_depth_um, one line per N_DFU (uniformity vs main-channel size).
- `fig_05`: top-5 candidates (largest N_DFU among `pass_at_ideal_500==True`,
  tie-broken by lowest required pressure) — re-simulated P_oil/P_water/DP_DFU
  vs x_positions at 500 and 1000 mbar.

### Provenance (per CLAUDE.md)

- `snapshots/study_config_<date>.yaml`: verbatim copy of the live config —
  this is the "config snapshot" since no per-candidate YAML goes through
  `load_config`.
- `snapshots/run_manifest.md`: git hash (`git rev-parse HEAD` at run time),
  config snapshot path, exact command, output paths, and an explicit
  **"Experimental data used: None — computational/model-only workspace"**
  line (omit the CLAUDE.md experimental-data subtable entirely rather than
  leaving it blank, to make clear this was intentional).
- `report.md` (hand-authored after first run): `## Data provenance` section
  per CLAUDE.md linkage rules, pointing at the snapshot, run manifest, and
  mapping each figure/table to its source CSV. Kept distinct from the
  auto-generated `results/results_summary.md` (raw numbers vs. narrative).

### `BRIEF.md`

Status: active; Type: computational. Research question, approach (two-layer
screening strategy — Stage 1 now, Stage 2/cyclic deferred), the 10-point
assumptions list mirrored from the original spec (instantaneous droplet
formation, flat 12 mbar constant vs. diagnostic-only Laplace estimate,
piecewise-profile-only resistance, `V_reset` taken as given, no transient
feedback, fixed Qw, `Mcl` inert, other DeviceConfig fields at defaults, "all
rungs must pass" criterion, ±50 mbar grid resolution), Data sources: None,
Success criteria, Open questions (whether Stage 2 should follow for passing
candidates; whether the flat 12 mbar constant holds across the full depth
range vs. the Laplace diagnostic).

## Addendum — post-approval refinements

Two extensions agreed after initial review (still ladder-only; the topology-
generalization/graph-solver idea discussed separately stays parked for a
future initiative, not part of this workspace):

### Manufacturing feasibility — tunable settings, not hardcoded pass/fail

We're not confident in the exact limits, so these are exposed as config knobs
(easy to tinker with) rather than baked into the pass/fail logic:

```yaml
manufacturing:
  max_main_depth_um: 200.0            # matches stepgen ManufacturingConfig default
  max_delam_line_load_N_per_m: null   # optional; null = disabled (limit not settled yet)
```

Per candidate, compute (diagnostic columns, do NOT exclude rows):
- `manufacturing_ok_depth = main_depth_um <= max_main_depth_um`
- `delam_line_load_N_per_m = P_oil_peak_Pa * main_Mcw_m` (reuse `P_oil[0]` from
  the existing solve at the reference pressure) and, only if
  `max_delam_line_load_N_per_m` is set, `manufacturing_ok_delam`
- `manufacturing_ok = manufacturing_ok_depth and manufacturing_ok_delam`

`results_summary.md` reports how many candidates pass the Stage-1 screen but
fail the manufacturing check under the current settings, so the two concerns
stay visibly separate.

### Qw / emulsion-ratio diagnostic + bounded sensitivity check

Clarification: `Qw_in_mlhr` is the **continuous phase** (water) flow; oil
(dispersed, driven by `Po`) goes through the DFUs and forms droplets. At
fixed `Qw=5 mL/hr`, low-N_DFU candidates would show a very low emulsion
(dispersed) fraction even at reasonable droplet formation rates — worth
surfacing, without rebuilding the whole sweep around it (hypothesis to test,
not assumed: adjusting Qw to hit a target emulsion % is not expected to
materially change Stage-1 performance, since Qw's only coupling into `t_S1`
is indirect, through the water main-channel's contribution to `DP_DFU`).

1. **Free diagnostic (no extra solves)**: `SimResult` already returns
   `Q_oil_total` and `Q_water_total` from every `simulate()` call — add
   `emulsion_pct = 100 * Q_oil_total / (Q_oil_total + Q_water_total)` as a
   per-pressure column in `per_pressure_long.csv`, and
   `emulsion_pct_at_500mbar` / `emulsion_pct_at_1000mbar` in
   `candidate_summary.csv`. This uses the existing fixed-`Qw=5` sweep as-is.

2. **Bounded sensitivity check** (separate, small, not part of the 576×20
   main sweep): add to `study_config.yaml`:
   ```yaml
   emulsion_check:
     target_emulsion_pct: 10.0
     qw_sensitivity_max_iterations: 3
   ```
   Implement `qw_for_target_emulsion(config, Po_mbar, target_pct, max_iter=3)`:
   a short fixed-point loop — solve, read `Q_oil_total`, set
   `Qw_new_mlhr = Q_oil_total_mlhr * (100/target_pct - 1)`, resolve, repeat
   up to `max_iter` times (a handful of solves, not a full re-sweep). Run this
   only for one representative candidate per `N_DFU` value (3 total), at its
   `min_passing_pressure_mbar` if it has one else 1000 mbar, and report the
   resulting `t_S1`/`DP_DFU` percent change vs. the baseline fixed-`Qw`
   result in a "Qw sensitivity check" section of `results_summary.md`. This
   directly tests the stated hypothesis with real numbers at negligible
   extra compute cost, instead of doubling the sweep.

## Verification

1. **Smoke test**: run `analysis.py`, confirm both CSVs, `results_summary.md`,
   and all 5 PNGs are generated without error.
2. **Depth → required pressure** (should be non-increasing): closed-form
   argument — `t_S1 ∝ DFU_length / (depth * DP_eff)` since `V_reset ∝ depth^3`
   and `R_DFU ∝ length/depth^4` (both sections scale as `length/(width·depth^3)`
   with `width ∝ depth`). Verify empirically via a per-group monotonicity
   check (`groupby` over the other 4 sweep dims, check
   `min_passing_pressure_mbar` is non-increasing in `DFU_depth_um`) plus a
   Spearman correlation, printed in `results_summary.md`.
3. **Length → required pressure** (should be non-decreasing): same
   closed-form argument, opposite sign; same groupby/correlation check.
4. **N_DFU → required pressure / uniformity**: since `R_DFU`/`V_reset` don't
   depend on `N_DFU`, degradation with `N_DFU` must come from main-channel
   pressure non-uniformity along the ladder — check via
   `groupby("N_DFU")[["min_passing_pressure_mbar","t_S1_spread_at_1000mbar"]].mean()`,
   expect both non-decreasing from N_DFU=10 to 1000 (most visible at small
   `main_depth_um`).
5. **No candidate with DP_eff ≤ 0 marked passing**: assert
   `(df[df.pass_at_hard_1000]["active_fraction_at_1000mbar"] == 1.0).all()`
   in `results_summary.md` generation — hard requirement per the pass
   definition (worst rung governs).
6. **V5-30 regression check** (standalone, not a sweep candidate): printed
   assertion at the top of `main()` — `sqrt(30*10)=17.3 µm` vs. observed
   19–21 µm lab range; loose bound only (10–30 µm), flag the ~15% residual
   gap in `BRIEF.md` Open Questions rather than treating it as a failure.

### Critical files referenced

- `stepgen/config.py`
- `stepgen/models/resistance.py`
- `stepgen/models/hydraulics.py`
- `CLAUDE.md` (data provenance conventions)
- `experimental_workspaces/comp_wo_hydraulics/` (comparable existing workspace)
