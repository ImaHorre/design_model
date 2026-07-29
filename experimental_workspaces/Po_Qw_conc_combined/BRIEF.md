---
study-type: synthesis
covers: po_sweep_v530, qw_sweep_v581, conc_sweep_v581
devices: V5-30 (ID A), V5-8-1 (ID B)
date: 2026-04-28
---

## Purpose

Cross-experiment synthesis across three parameter sweeps (Po, Qw, [SDS]) on V5-30 geometry devices.
This is the authoritative analysis document for the SDS/sunflower-oil system characterisation.

## Key conclusions

1. The Poiseuille Stage 1 model is physically correct — V_reset (from L_menpoint) is the critical input.
2. Stage 2 is NOT a single constant; it depends on both Po and Qw.
3. [SDS] below CMC breaks the model through contact-angle effects on dP_eff.
4. Droplet diameter is geometry-controlled across all tested conditions (above CMC).

## Model tuning recommendations

See `report.md` — includes per-Po Stage 2 lookup table and V_reset recommendation.

## Files

- `report.md` — full cross-experiment analysis and model tuning recommendations
