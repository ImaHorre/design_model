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

> **CORRECTION 2026-06-08**: The findings below were based on a fps=25 analysis of 50fps videos for devices 3D and 4C. After correcting the timing data (÷2 for 3D and 4C), all three devices are expected to show consistent production rates. The "1B was an outlier" observation was an artefact. See `report.md` for full correction details.

See `report.md` in this workspace for the full analysis. **All timing and frequency values in the generated report are incorrect and need to be regenerated after fps correction.**

Pre-correction observations (DO NOT USE as findings):
- Device 1B appeared as an outlier with ~2× production frequency of 3D and 4C (artefact of fps error)
- Droplet diameter: consistent across all three devices (correct — spatial measurement)
- Stage 1 timing: appeared to differ between devices (artefact — 3D/4C had wrong fps)

**Corrected interpretation**: All three devices likely show consistent production rate and stage timing. The batch-to-batch manufacturing consistency finding (for diameter at least) remains valid.
