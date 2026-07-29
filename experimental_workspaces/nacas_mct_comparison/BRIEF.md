# Workspace Brief: NaCas vs MCT Surfactant System Comparison

**Created**: 2026-05-18  
**Status**: complete

## Research question

How does sodium caseinate (NaCas) continuous phase with MCT oil compare to the
standard SDS continuous phase with sunflower oil (SO) system in terms of stage timings,
droplet size, and model accuracy?

## Background

Different surfactant and oil systems have different interfacial tensions, viscosities, and
wetting properties. NaCas/MCT is a food-grade alternative to SDS/SO. Understanding how
the stage-wise model translates across fluid systems is important for generalising its use.

## Approach

- Data source: `analysis/stage_timings.csv` (ContPhase == NaCas and SDS rows)
- Analysis: side-by-side timing comparison, model prediction for each system
- Key parameters that differ: gamma_effective, mu_oil, mu_water (NaCas is more viscous)

## Key findings

See `nacas_mct_report.md` for the full analysis.

> **CORRECTION 2026-06-08**: All absolute timing and frequency values in `nacas_mct_report.md` are 2× wrong (fps=25 used instead of 50). Relative comparisons between NaCas and SDS survive. See the correction notice at the top of `nacas_mct_report.md`.

Qualitative findings (survive fps correction — ratios preserved):
- NaCas/MCT produced shorter Stage 1 times than SDS/SO at same pressure (shorter reset geometry)
- Stage 3 (snap-off) faster for NaCas/MCT — points to lower interfacial tension with NaCas adsorbed
- NaCas/MCT minimum operating pressure is higher (≥ 300 mbar vs ≥ 200 mbar for SDS/SO)
- Droplet diameter is consistent along the device for both systems (spatial measurement, unaffected)

Quantitative values needing correction (all absolute timing/frequency numbers should be halved/doubled):
- All Stage*_s values in the report should be halved
- All Hz values should be doubled
- Rerun `analysis.py` after applying `scripts/correct_fps_error.py` to the source CSV
