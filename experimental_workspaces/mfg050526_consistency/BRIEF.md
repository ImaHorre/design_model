# Workspace Brief: Manufacturing Batch 050526 Consistency Analysis

**Created**: 2026-05-18  
**Status**: complete

## Research question

How consistent is droplet generation across devices from manufacturing batch 050526
(three V5-30 devices: 1B, 3D, 4C)?

## Background

Multiple devices from the same batch should produce similar droplets under the same
operating conditions. Measuring device-to-device variance vs within-device measurement
variance tells us about manufacturing quality and the limits of what the model needs to predict.

## Approach

- Data source: `analysis/stage_timings.csv` (batch 050526 rows)
- Analysis: variance decomposition, CV heatmaps, measurement error estimates
- Model comparison: stage timings predicted vs measured

## Key findings

See `nacas_mct_report.md` (in the nacas_mct_comparison workspace) and `results/v5_30_mfg050526/`
for figures and the analysis report.

Batch 050526 showed:
- Device 1B and 3D closely matched
- Device 4C showed elevated Stage 1 times at high pressure
- Within-device CV < between-device CV for Stage 1 (manufacturing variation dominates)
