# Context: Deep DFU V5 Main-Channel Study (simple)

For Claude. Read at the start of a fresh session working on this workspace.

## What this workspace does

Computational (model-only) study of **oil-main-channel design** for 20 µm-deep DFUs on a
V5-30-derived device. One question, one fixed inlet pressure: per config, how many DFUs
fit, what oil flow, how flat is the ΔP. See `BRIEF.md`; `report.md` is the 1-page answer.

> This is the **simplified** version. An earlier over-built version (Ca/step-emulsification
> regime analysis, φ/clog sweeps, serpentine geometry, 8-vs-10 die sweep, 6 figures) was
> deliberately cut. `PLAN.md` is the original plan and is partly superseded.

## Model used

Steady mixed-BC ladder solver, built per config in Python (no per-config YAML):

| Component | Role |
|-----------|------|
| `stepgen.models.hydraulics.simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)` | steady solve → `SimResult(P_oil, P_water, Q_rungs, ...)`. Plain `simulate`, not `iterative_solve`. |
| `stepgen.models.droplets.droplet_diameter/droplet_volume` | D_pred / V_drop for the Stage-1 cycle frequency. |
| `stepgen.models.resistance.resistance_piecewise` | R_DFU for the 90:10 two-section DFU. |
| `stepgen.config` dataclasses | built per config; `Nmc_override = N_DFU`. |

## Key models in `analysis.py`

- **Area budget → N**: `band = W_oil + L_rung + W_water`, `N = floor(area / (band·pitch))`.
  The area budget (41.6 cm²) is **calibrated to reproduce the real V5-30 (N = 11,550)** — see
  `v5_30_actual` in the config and `v5_30_calibration_check` (hard assert). Depth is absent
  from band → deeper main is free.
- **Stage-1 cycle → frequency**: `L_reset = √(w_exit·h_exit)`, `V_reset = L_reset·w·h`,
  `f = Q_rung / (V_reset + V_drop)`. Drop size is the untrusted power law → frequency indicative.
- **Water for 10% emulsion**: `Qw = 9·Q_oil`, a downstream number (not injected — would choke oil).
- Oil-side solved at a fixed 5 mL/hr carrier (mild sensitivity, documented).

## Two analyses

- **Part 1 — `analysis.py`**: main-channel design levers at area-budgeted N (depth free,
  width tradeoff). Outputs `results/candidate_summary.csv`, `results/results_summary.md`,
  figures `dP_over_rungs.png`, `throughput_vs_main.png`.
- **Part 2 — `analysis_n_sweep.py`**: manual N sweep (100→10,000). Does a smaller device buy
  flatness + operating range and fit current fab caps? Reuses Part-1 `build_device_config`.
  Adds an operating-range metric (min Po that clears the Laplace P_cap ≈ 8.7 mbar). Outputs
  `results/n_sweep_summary.{csv,md}`, figures `n_sweep_size_vs_N.png`, `n_sweep_rung_effect.png`.
  Key result: **~1000 DFUs run flat on the current 200×1000 µm main.**

## Run it

```
python experimental_workspaces/comp_deep_dfu_v5_main_mods/analysis.py          # Part 1
python experimental_workspaces/comp_deep_dfu_v5_main_mods/analysis_n_sweep.py  # Part 2
```

## Fluid (inherited, do not re-pick)

Sunflower oil (dispersed, µ = 0.06 Pa·s) / 2% SDS-water (continuous, µ = 0.00089 Pa·s).
Droplet size from the regime-blind power law is not trusted.
