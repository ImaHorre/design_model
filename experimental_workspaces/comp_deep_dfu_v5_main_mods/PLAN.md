# Plan: Deep-DFU (20 µm) V5 main-channel modification study

## Context

We currently run V5-30 with **10 µm-deep DFUs** (8 µm wide upstream, 30 µm exit, 60 µm
pitch). We want to move to **20 µm-deep DFUs** with a **15–20 µm upstream width, 60 µm
exit, 120 µm pitch**, targeting ~60 µm droplets. Deepening the DFU drops its resistance
by ~8× (R ∝ 1/depth³), so each DFU draws far more oil — which means the **oil main and
the water dilution flow, not the DFU refill, become the binding constraints**. The prior
`comp_large_dfu_stage1_screen` workspace already showed this for deep ladders (oil-main
loading, not Stage-1, limits large N).

The goal is a clear indication of **what major-channel (oil-main) modifications** — deeper,
wider, or lower-R — are needed to run 20 µm DFUs without (a) an unflat DFU ΔP profile and
(b) clogging from over-concentration of 60 µm droplets. Outputs are, per configuration:
**N DFUs that fit on the die, total oil-main length, DFU ΔP flatness, total oil throughput,
emulsion concentration φ vs required water flow, and a step-emulsification (Ca) regime flag.**

## New workspace

Create `experimental_workspaces/comp_deep_dfu_v5_main_mods/` (computational). Do **not**
extend `comp_large_dfu_stage1_screen` — different research question (design-target-driven,
serpentine-grounded N, throughput + flatness + φ, not Stage-1 pass/fail).

**Implementation step 1 (scaffold + relocate this plan).** Run
`python scripts/new_workspace.py comp_deep_dfu_v5_main_mods "Deep (20 µm) DFU V5 main-channel
mod study — N-fit, ΔP flatness, φ vs water flow, Ca regime"`, then **copy this plan file into the
workspace** as `experimental_workspaces/comp_deep_dfu_v5_main_mods/PLAN.md` so the plan lives with
the study (the project keeps its own record; the `~/.claude` copy is just the plan-mode scratch).
Fill in `BRIEF.md` (study-type: computational; device: V5-30-derived; the research question and
scope limits below). Then model `analysis.py` on `comp_large_dfu_stage1_screen/analysis.py`.

## Reused components (do not reimplement)

- `stepgen.models.hydraulics.simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)` — steady
  mixed-BC ladder solve → `SimResult(P_oil, P_water, Q_rungs, x_positions, Q_oil_total,
  Q_water_total)`. Use plain `simulate`, **not** `iterative_solve`.
- `stepgen.models.metrics.compute_metrics(config, result)` → `dP_spread_pct` (ΔP flatness),
  `Q_oil_total`, `Q_oil_droplets`, `D_pred`, `f_pred_*`, active/reverse/off fractions.
- `stepgen.models.resistance.resistance_piecewise` — via `RungConfig.profile` (90:10 two-section
  microchannel: upstream 90% at 15/20 µm width, exit 10% at 60 µm width, both 20 µm deep).
- `stepgen.config` dataclasses (`DeviceConfig`, `GeometryConfig`, `MainChannelConfig`,
  `RungConfig`, `MicrochannelSection`, `JunctionConfig`, `FluidConfig`, `OperatingConfig`,
  `DropletModelConfig`). Build one `DeviceConfig` per candidate in Python; set
  `Nmc_override = N_DFU` so ladder length is fixed by fitted DFU count.
- `stepgen.viz.plots.plot_rung_dP` (ΔP(x) flatness plot) as a reference for fig style.
- Provenance helpers pattern from `comp_large_dfu_stage1_screen/analysis.py` (`write_provenance`,
  dated `study_config.yaml` snapshot, `git rev-parse HEAD`, `run_manifest.md`).

## New code to write (all inside the workspace `analysis.py` + `study_config.yaml`)

### 1. Serpentine N-fit estimator (`serpentine_fit(die, w_main, L_dfu, ...)`)
Single dual-main ladder snaked across the die (oil main + water main bridged by DFUs, per the
`gds-create` dual-serpentine analogy). Formulas:
```
c2c          = w_main + L_dfu               # centre-to-centre of the oil/water pair
r_outer      = r_inner + c2c                # r_inner ≈ 1000 µm min turn radius
band_pitch   = r_inner + r_outer            # vertical pitch between passes
turn_extent  = r_outer + w_main/2           # horizontal area lost to each U-turn
N_rows       = floor((H - 2*margin) / band_pitch)
L_row        = W - 2*turn_extent - 2*margin
DFUs_per_row = floor(L_row / pitch_dfu)     # pitch_dfu = 120 µm
N_DFU        = N_rows * DFUs_per_row         # straights only
L_main       = N_rows * L_row + (N_rows-1) * pi * r_inner
```
Report the **effective usable W×H** (`N_rows*band_pitch` × `L_row`) so the die-vs-usable loss
is explicit (a 100 mm die yields ~85 mm usable straights — the turns/margins eat one dimension).
Run for die = **100 mm and 80 mm**. Straights only (no turn-populated DFUs).

### 2. Per-candidate config builder (`build_device_config`)
Fixed: DFU depth 20 µm; exit 60 µm × 20 µm; pitch 120 µm; two-section 90:10 profile.
Swept axes (`itertools.product`, candidate key like `M300x1500_L2_W20_D100`):
- `main_depth_um`: [200, 300, 400]
- `main_width_um`: [1000, 1500, 2000]
- `DFU_length_mm`: [1.0, 2.0, 4.0]
- `upstream_width_um`: [15, 20]
- `die_mm`: [100, 80]
`N_DFU` per candidate comes from the serpentine estimator (not swept independently). Flag any
candidate that busts the current manufacturing cap (200 µm depth / 1000 µm width) — relaxed
here by design. Guard the 20 µm-deep aspect constraint: solver needs width ≥ ~13 µm, so 15 µm
upstream is the floor (assert, don't silently fail).

### 3. Per-candidate evaluation (`evaluate_candidate`)
For each candidate at each oil pressure in the `Po_sweep`:
- `result = simulate(config, Po, Qw, 0.0)`; `m = compute_metrics(config, result)`.
- **Throughput**: `Q_oil_total` (µL/hr) and `Q_oil_droplets`.
- **Flatness**: `dP_spread_pct` + raw `min/mean/max` DFU ΔP; also oil-main end-to-end droop
  `P_oil[0]-P_oil[-1]`.
- **Ca regime flag** (see below).
- **Emulsion φ + required water flow** (see below).
Write `results/candidate_summary.csv` (one row/candidate at nominal Po) and
`results/per_pressure_long.csv` (candidate × Po).

### 4. Ca / SE-regime flag

**Interfacial tension source.** There is **no directly measured γ** in the repo. 15 mN/m is the
*back-calculated effective IFT* for this exact sunflower-oil / SDS-water O/W system, used
consistently across `po_sweep`, `comp_large_dfu_stage1_screen`, and `wo_v5_30.yaml`
(`_template/CONTEXT.md:90` labels it "back-calculated"). Because this study uses the **same
oil/water mix**, all fluid properties are inherited unchanged from that system —
`mu_oil = 0.06 Pa·s`, `mu_water = 0.00089 Pa·s`, `gamma_eff = 0.015 N/m` — rather than picked
fresh. Two workspaces flag literature γ (~20 mN/m at low SDS) as too high
(`Po_Qw_conc_combined/report.md:172,255`; `conc_sweep/analysis_notes.md:154`), so γ is uncertain.
Handle that by reporting Ca over a **γ sensitivity band 10–20 mN/m**, not a single value, so the
regime flag is not hostage to one unmeasured number. (Config `gamma` is literally 0.0 → the
0.015 override is explicit and documented in the manifest.)

**Two flowrates → bracketed Ca** (per the "geometric vs drop-growth" distinction). Compute
`v_nozzle = Q / (exit_width * exit_depth)` from **both** oil flowrates the model provides, per DFU:
- `Ca_hydraulic` from `Q_rung` — the steady **geometric/hydraulic** oil delivery.
- `Ca_droplet` from the **droplet-production rate** (`Q_oil_droplets / n_active` = f × V_drop per DFU,
  `compute_metrics`) — the **actual rate including the drop-growth/snap-off mechanic**.
Report per-candidate `Ca_max`/`Ca_mean` for each, forming a band. Flag `Ca > 0.03` (SE ceiling,
Chakraborty) and note `Ca > 0.0125` (Montessori) as a stricter bound. Still an
**order-of-magnitude regime flag** — even `Ca_droplet` is a cycle-averaged rate, not the
instantaneous pinch velocity (local pinch Ca ≈ (w/h)× higher). λ = µ_c/µ_d ≈ 0.015 caveat noted.
If a workspace later yields a measured oil flowrate at DFU exits (drop volume × frequency), it
can back out γ_eff directly and replace the band — flag as a follow-up.

### 5. Emulsion concentration φ vs required water flow
`phi_out = Q_oil_total / (Q_oil_total + Q_water_total)` at the outlet (and the φ(x) rise along
the main from cumulative `Q_rungs`). For each candidate compute the **water flow Qw needed to
hold `phi_out ≤ phi_max`** (default 0.6 random-close-packing; also report at emulsion_ratio 0.3),
i.e. `Qw_req = Q_oil_total * (1-phi_max)/phi_max`, and whether that Qw is deliverable (pressure
to drive it through the water main at that main geometry). This is the direct "does it clog /
do we need a lower-R (bigger) main or fewer DFUs" answer.

## Figures (faceted, matplotlib Agg, DPI 150, saved to `figures/`)
1. `throughput_vs_main_size.png` — Q_oil_total vs main depth, faceted by DFU length, lines = main width.
2. `flatness_vs_main_size.png` — `dP_spread_pct` vs main depth × width (the depth-vs-width asymmetry).
3. `N_and_throughput_tradeoff.png` — N_DFU (from serpentine) vs main width, with total throughput overlaid.
4. `phi_and_required_Qw.png` — φ_out and Qw_req vs main size / N; clog threshold line.
5. `Ca_regime_map.png` — Ca band (hydraulic vs droplet-rate) vs Po/main size, shaded γ = 10–20 mN/m
   band, SE ceiling lines (0.0125 / 0.03); which configs exit SE.
6. `dP_profile_top_configs.png` — ΔP(x) along the ladder for a few representative configs (reuse
   `plot_rung_dP` style) showing flat vs drooping.

## Data provenance (per CLAUDE.md)
- `study_config.yaml` (all values in µm/mm; SI conversion only in Python) + dated snapshot in
  `snapshots/`.
- `snapshots/run_manifest.md`: `git rev-parse HEAD`, exact command, fluid/geometry params
  (sunflower oil µ = 0.06 Pa·s dispersed, water µ = 0.00089, γ_eff = 0.015 N/m **back-calculated**
  for this O/W SDS system — same mix as `po_sweep`/`comp_large_dfu_stage1_screen`, not literature;
  Ca reported over γ = 10–20 mN/m band). Note γ is unmeasured (follow-up: pendant/spinning-drop).
- Model-only study → no experimental `data/` files; note computational study type in `BRIEF.md`.
- `results/results_summary.md` auto-generated (pass tables, monotonicity/Spearman checks, asserts).

## Honest scope limits (state in BRIEF.md + report.md)
- Droplet size (60 µm) from the regime-blind power law is a ~2× extrapolation beyond its
  ~30×10 µm calibration — reported, not trusted. (`droplet-model-regime-blind`)
- "Clog" is flagged (φ loading + Ca), not decided — true clogging is a Stage-2/regime
  phenomenon outside the steady model. (`deep-dfu-se-regime`)
- Two DFU-resistance formulas exist (network `12/(1−0.63h/w)` constriction-scaled vs Stage-1
  Shah-London full-length). This study uses the **network path** (throughput + ΔP + φ). Note the
  discrepancy; a Stage-1 refill cross-check can reuse the prior workspace's relation if wanted.

## Verification
1. `pytest tests/test_stage_wise_v3_phase1.py tests/test_simulate.py` — confirm no regression from any
   config construction (we only build configs, don't touch model code).
2. Sanity solve: build the baseline V5-30-like config (10 µm DFU) via the new builder and confirm
   `simulate` + `compute_metrics` reproduce known V5-30 numbers (N=11550, throughput order).
3. Run `analysis.py` end-to-end; confirm all CSVs + 6 figures generate and `results_summary.md`
   asserts pass.
4. Spot-check one deep candidate by hand: R ∝ 1/(w·h³) scaling from 10→20 µm depth ≈ 8× lower R,
   Q_rung ≈ 8× higher — confirm the model output matches order-of-magnitude.
5. Serpentine estimator: cross-check N against the `gds-create` `floor(L/pitch)` idiom for one case.
