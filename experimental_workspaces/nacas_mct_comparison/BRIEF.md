# Workspace Brief: NaCas vs MCT Surfactant System Comparison

**Created**: 2026-05-18  
**Status**: complete

## Research question

How does sodium caseinate (NaCas) continuous phase with MCT oil compare to the
standard SDS continuous phase with silicone oil (SO) system in terms of stage timings,
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

- NaCas/MCT produced longer Stage 1 times (higher aqueous viscosity)
- Stage 2 was similar across systems — snap-off geometry-controlled
- Model needs different `gamma_effective` for NaCas/MCT vs SDS/SO
