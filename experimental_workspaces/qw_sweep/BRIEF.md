---
study-type: experimental
device: V5-8-1 (ID B, V5-30 geometry)
emulsion: Sunflower oil / 2% SDS-water
date: 2026-04
parameter-varied: Qw (5–20 mL/hr) × Po (200–600 mbar)
fixed: [SDS]=2%
n: 143
---

## Research question

How does water flowrate Qw affect Stage 1 and Stage 2 timings, and does the hydraulic solver correctly predict the Qw effect on Stage 1?

## Key findings

- Stage 2 is NOT Qw-independent (contradicts the single-constant assumption from the Po sweep).
- Qw effect on Stage 2 saturates above Qw=10 mL/hr; at Po≥600 mbar Stage 2 is Qw-insensitive.
- C_visc ≈ 1.09 ± 0.26 when using L_menpoint-derived V_reset ≈ 20 µm (vs 0.74 with nominal 30 µm).
- Per-Po Stage 2 lookup (at Qw=5): {200: 0.35 s, 300: 0.205 s, 400: 0.154 s, 600: 0.12 s}.

## Files

- `qw_report.md` — full analysis
- `figures/fig_01–06.png`

## Model config

`configs/v5_30.yaml`

## Cross-references

Results from this experiment feed into `sds_sweep_synthesis/report.md` (Experiment 2 of 3).
