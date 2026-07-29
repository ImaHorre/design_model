# Plan: FPS Error Impact Assessment and Correction

## Context

The experimental stage-timing analysis was done assuming **25 fps** but the videos were actually recorded at **50 fps**. This means every frame-count-to-time conversion used `t = n_frames / 25.0` when the correct formula is `t = n_frames / 50.0`. All time measurements derived from frame counts are therefore **2× too long**, and all frequencies derived from those times are **2× too low**.

This is a systematic error in the source data (`data/flow-stage-copy.xlsx`), not in the Python analysis scripts themselves — the scripts correctly compute `freq_Hz = 1 / total_cycle_time_s`, trusting whatever times are in the source file.

**Critical exception — Device 1B in `mfg050526_consistency`**: The video for device 1B was genuinely recorded at 25 fps. This device appeared as an outlier with ~2× the production frequency of the other two consistency-check devices. That "outlier" is now explained: 1B was the only correctly-analysed device. After correcting the other two devices, they should show frequency comparable to 1B — validating device-to-device consistency rather than contradicting it.

---

## The Correction Factor

| Quantity | Recorded value | Actual value | Fix |
|---|---|---|---|
| Stage 1 time (Stage1_s) | T | T / 2 | multiply recorded value × 0.5 |
| Stage 2 time (Stage2_s) | T | T / 2 | × 0.5 |
| Stage 3 / snap-off time (Stage3_s) | T | T / 2 | × 0.5 |
| Total cycle time (total_t) | T | T / 2 | × 0.5 |
| Droplet frequency (freq_Hz) | f | 2f | × 2.0 |

**What is NOT affected** (spatial measurements, not time-derived):
- Droplet diameter (measured in µm from images)
- Meniscus geometry: L_menpoint, L_men
- Pressure Po
- Flow rates Qw (set by pump, not derived from video)

---

## Affected Files and Outputs

### Primary source of error
- `data/flow-stage-copy.xlsx` — columns K, L, M (exp_s1_t, exp_s2_t, exp_s3_t) were computed from frame columns G–J using fps=25. These are the values loaded by all workspace analysis scripts.

### Affected workspaces (experimental data + timing analysis)
| Workspace | Affected outputs | Exception |
|---|---|---|
| `experimental_workspaces/nacas_mct_comparison/` | All freq_Hz, all Stage*_s, frequency figures, model comparison | None — all data at 50 fps |
| `experimental_workspaces/mfg050526_consistency/` | All freq_Hz, all Stage*_s for devices **other than 1B** | **Device 1B: leave untouched** — its video was genuinely 25 fps and is already correct |
| `experimental_workspaces/po_sweep/data/stage_timings.csv` | If times are fps-derived, same correction | Verify before correcting |
| `experimental_workspaces/conc_sweep/` | If timing data present — check | — |
| `experimental_workspaces/qw_sweep/` | If timing data present — check | — |
| `experimental_workspaces/Po_Qw_conc_combined/` | If timing data present — check | — |

### Computational workspaces — NOT affected
- `comp_viscosity_sweep`, `comp_wo_hydraulics` — model-only, no experimental timing data

### Downstream impact on model comparison
The model predicts droplet frequency from first principles (geometry + flow). If measured frequency was 2× too low, the model appeared to **overpredict frequency by 2×** relative to experiment. Any model calibration (e.g. adjusting C_visc or Rcrit) against these results would have compensated for an error that doesn't exist in the physics. Those calibration conclusions need revisiting.

---

## Step-by-step Correction Plan

### Step 1 — Verify the source
Before correcting anything, confirm the error is in the Excel file by:
1. Opening `data/flow-stage-copy.xlsx`
2. Picking one row — take its frame count (e.g., Stage3 frame end − Stage1 frame start)
3. Compute: `time_at_25fps = frames / 25.0` and `time_at_50fps = frames / 50.0`
4. Confirm which matches the time in columns K–M

Also note the verification comment in `data/analysis/experimental_stage_analysis.py` line 44:  
`"Frame rate: 25 fps (verified: 27 frames / 1.08 s = 25 fps)"`  
This needs to be re-examined — either the stopwatch timing was wrong, or 27 frames at 50 fps = 0.54 s (not 1.08 s). Understanding how this verification was done is important.

### Step 2 — Correct the source data
Two options (choose one):

**Option A — Fix in Excel**: In `flow-stage-copy.xlsx`, update columns K, L, M to use `= G_col / 50.0` (instead of `/ 25.0`) and re-export. This fixes the root cause.

**Option B — Apply correction in analysis scripts**: Add `fps_correction = 25.0 / 50.0` scaling to the time columns as they are loaded. Less clean but avoids touching the Excel file.

**Recommendation: Option A** — fix the source data and re-export, so the Excel file is correct and the scripts need no hacks.

### Step 3 — Re-run affected workspace analyses
For each affected workspace:
1. Re-run `analysis.py` with corrected source data
2. Overwrite results CSVs in `results/`
3. Regenerate all figures
4. Update `snapshots/run_manifest.md` with new git hash and note about fps correction
5. Add a dated "Correction — 2026-06-08" section to `report.md` documenting what changed and why

### Step 4 — Re-examine model comparison conclusions
With corrected frequencies (2× higher), revisit:
- Whether model predictions now agree better or worse with experiment
- Whether any C_visc or Rcrit calibration was done against the wrong data — if so, it should be recalibrated against corrected frequencies
- Update wiki pages if any model-vs-experiment claims change materially

---

## Verification

After correction:
1. Pick a single known data point — check that its corrected freq_Hz = (old freq_Hz × 2)
2. Re-run `pytest` to confirm no regressions in model code
3. Check that model frequency predictions and corrected experimental frequencies are in closer agreement than before (this is the expected outcome)
4. Review po_sweep/data/stage_timings.csv separately to confirm whether it also needs correction

---

## Re-interpretation of consistency report

The most immediate consequence is the re-reading of `mfg050526_consistency`:
- **Before correction**: Device 1B appeared to produce droplets at ~2× the rate of devices 2 and 3, marked as an anomaly
- **After correction**: Devices 2 and 3 had their frequencies corrected ×2 → all three devices should show similar production rates
- **Interpretation**: The consistency data actually shows good device-to-device reproducibility; the apparent outlier was an artefact of the fps error
- Update the consistency report with this finding

## Open questions
1. Confirm that `po_sweep/data/stage_timings.csv` times are fps-derived (not directly measured) before applying correction
2. Check whether `conc_sweep`, `qw_sweep`, `Po_Qw_conc_combined` workspaces contain any fps-derived timing data (from the inventory, these don't have analysis.py files, so they may be model-only or pressure-only sweeps)
