---
study-type: experimental
device: V5-30 (ID A)
emulsion: Silicone oil / 2% SDS-water
date: 2026-04
parameter-varied: Po (200–500 mbar)
fixed: Qw=5 mL/hr, [SDS]=2%
---

## Research question

Does a simple Poiseuille rung-flow model correctly predict Stage 1 timing across a range of oil inlet pressures?

## Key findings

> **CORRECTION 2026-06-08**: `data/stage_timings.csv` has been corrected ×0.5 on all Stage*_s columns (fps=25 used instead of 50 in original analysis). All absolute timing values below are pre-correction and should be halved. Derived quantities (Po scaling exponent, C_visc calibration) may need revisiting.

Pre-correction findings (timing values are 2× too large):
- Stage 1 scales as Po^-1.17 (vs Po^-1.0 ideal) — consistent with ~12 mbar capillary back-pressure.
- C_visc ≈ 0.95 when using measured V_reset from L_menpoint ≈ 30 µm. **Needs re-checking after fps correction — if Stage 1 times halve, C_visc calibration result may shift.**
- Stage 2 ≈ 0.19 s pre-correction → corrected ~0.095 s — much less pressure-sensitive than Stage 1.
- Droplet diameter ≈ 27 µm — geometry-controlled, no significant Po dependence. **Unaffected** (spatial measurement).

## Files

- `analysis_notes.md` — full analysis with figures reference
- `data/stage_timings.csv` — raw stage timing data
- `figures/` — primary analysis figures (fig_01–07)
- `plot_types/` — exploratory plot variants

## Model config

`configs/v5_30.yaml`

## Cross-references

Results from this experiment feed into `sds_sweep_synthesis/report.md` (Experiment 1 of 3).
