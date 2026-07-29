# Run Manifest

## Run: Deep (20 µm) DFU V5 main-channel mod study (SIMPLE) — 2026-07-09

**Model commit**: 79b7401f20cda60207cd01016e87652bf69456d0
**Config snapshot**: snapshots/study_config_2026-07-09.yaml
**Command**: `python experimental_workspaces/comp_deep_dfu_v5_main_mods/analysis.py`
**Run started**: 2026-07-09T15:30:58
**Outputs**: results/candidate_summary.csv, results/results_summary.md,
figures/dP_over_rungs.png, figures/throughput_vs_main.png

### Experimental data used

None — computational / model-only workspace (54 configs). No `data/` folder.

### Key parameters

| Parameter | Value |
|---|---|
| Dispersed phase | sunflower oil, η = 60 mPa·s |
| Continuous phase | water (2% SDS), η = 0.89 mPa·s |
| γ_eff | 15 mN/m (back-calculated; record only — no Ca analysis) |
| DFU (fixed) | 20 µm deep, 60×20 µm exit, 120 µm pitch, 90:10 profile |
| Main (swept) | depth [200.0, 300.0, 400.0] µm × width [1000.0, 1500.0, 2000.0] µm |
| Rung length (swept) | [1.0, 2.0, 4.0] mm |
| Upstream width (swept) | [15.0, 20.0] µm |
| Inlet oil pressure | 500 mbar (single fixed operating point) |
| Emulsion target | 10% → Qw = 9 × Qoil |
| Area budget | 41.6 cm² — CALIBRATED to reproduce real V5-30 (N=11550); N = floor(area / (band·pitch)) |
| V5-30 anchor | Mcw 1000 µm, rung 4000 µm, pitch 60 µm, band 6000 µm |

Fluid system: sunflower oil / 2% SDS-water O/W — SAME mix as `po_sweep` and
`comp_large_dfu_stage1_screen`, inherited unchanged.

## Run: Part 2 — manual N sweep — 2026-07-09

**Model commit**: 79b7401f20cda60207cd01016e87652bf69456d0
**Command**: `python experimental_workspaces/comp_deep_dfu_v5_main_mods/analysis_n_sweep.py`
**Run**: 2026-07-09T15:51:25
**Outputs**: results/n_sweep_summary.csv, results/n_sweep_summary.md,
figures/n_sweep_size_vs_N.png, figures/n_sweep_rung_effect.png
**N values**: [100, 300, 1000, 3000, 10000] (manual, not area-budgeted)
**P_cap**: 8.7 mbar (Laplace, θ=30°)
**Configs**: 90
