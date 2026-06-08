---
name: project-fps-error-correction
description: Systematic fps=25 error in stage timing analysis; all recent experimental CSVs affected; correction applied 2026-06-08
metadata:
  type: project
---

Systematic fps error discovered 2026-06-08: all stage-timing CSVs from recent experiments were analyzed assuming 25 fps, but videos were recorded at 50 fps. This makes all Stage1_s, Stage2_s, Stage3_s values 2× too long and all derived frequencies (freq_Hz) 2× too low.

**Why:** Video analysis tool hardcoded fps=25 in the annotation interface.

**How to apply:** When reviewing any timing or frequency value from a workspace, check whether it has been corrected. Pre-correction values in reports are labelled; corrected data has been saved to CSVs.

## Correction status by workspace

| Workspace | CSV status | Report status |
|---|---|---|
| `po_sweep/data/stage_timings.csv` | **CORRECTED** (×0.5 applied 2026-06-08) | BRIEF updated |
| `mfg050526_consistency` | NOT corrected (CSV not in repo) | Report has correction notice |
| `nacas_mct_comparison` | NOT corrected (CSV not in repo) | Report has correction notice |

## Exception — mfg050526 device 1B

Device **V5-30-260413-1B** in the mfg050526_consistency workspace was genuinely recorded at 25 fps. Its timing data is correct and should NOT be corrected. Use `--skip-device V5-30-260413-1B` with the correction script.

## Key implication — mfg050526 consistency conclusions

The reported "40% spread in production rate" between devices is an artefact. After correction, 3D and 4C frequencies should match 1B — the three devices are actually consistent. The "1B was an outlier with 2× frequency" was 1B being the only correctly-analysed device.

## Key implication — nacas_mct_comparison

Relative conclusions (NaCas faster than SDS, stage fractions, speed-up %) survive fps correction because both fluid systems had the same error. Only absolute values change. Qualitative findings are valid.

## Key implication — model calibration (C_visc)

C_visc ≈ 0.95 from the po_sweep was calibrated against timing values that were 2× too long. After correction, Stage 1 times halve, so the model calibration result needs to be redone against corrected data.

## Correction script

`scripts/correct_fps_error.py` — accepts CSV path and optional `--skip-device` flag.

## What is NOT affected

- Droplet diameter (spatial measurement from image pixels, not timing-derived)
- Pressure (Po) measurements
- Flow rates (set by pump)
- L_menpoint, L_men (spatial measurements)
- w11_4_7 dataset (`data/flow-stage-copy.xlsx`) — older dataset, fps verification needs separate check

## Old data (w11_4_7, data/flow-stage-copy.xlsx)

The w11_4_7 dataset from Feb 2024 used "Effective FPS: 25" in its frequency analysis txt files. Not confirmed as affected by the 2026 fps error. Do not correct without explicit verification.
