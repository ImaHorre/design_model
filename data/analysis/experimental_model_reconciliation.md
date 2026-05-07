# Experimental–Model Reconciliation
## Stage-Wise V3 Physics vs. V5_30_3_3 Video Data

**Date:** 2026-03-20
**Device:** V5_30_3_3 (v5_30.yaml)
**Experimental data source:** `data/flow-stage-copy.xlsx` rows 37–81
**Analysis script:** `data/analysis/experimental_stage_analysis.py`
**Clean dataset:** `data/analysis/stage_timing_clean.csv`
**Conditions:** Po = 200–500 mbar, DFU positions 0–10, N = 43 observations

---

## Section 1 — Stage Naming Reconciliation

### Summary

The video analysis tracked three experimental stages. The v3 physics model uses two stages. The mapping is:

| Experimental stage | Description | → Model stage |
|---|---|---|
| Exp Stage 1 | Oil meniscus travels from reset position to junction edge | → Model Stage 1 |
| Exp Stage 2 | Oil pushes over the edge (transitional inflation) | → Model Stage 1 |
| Exp Stage 3 | Continuous phase enters, neck pinches, snap-off | → Model Stage 2 |

**Model Stage 1 = Exp Stage 1 + Exp Stage 2** (all filling and edge-push)
**Model Stage 2 = Exp Stage 3** (snap-off only)

### Physical justification

Exp Stage 1 and Exp Stage 2 are both driven by oil delivery through the rung against the hydraulic and capillary resistance at the junction. Both scale with Po (higher pressure = faster). Grouping them is correct.

Exp Stage 3 is driven by capillary instability at the neck — not by the applied pressure. It is approximately Po-independent. This maps cleanly onto the Model Stage 2 physics (capillary-controlled snap-off at R_critical).

### Fraction of cycle time

| Po (mbar) | Stage 1 % | Stage 2 % |
|---|---|---|
| 200 | ~83% | ~17% |
| 300 | ~82% | ~18% |
| 400 | ~80% | ~20% |
| 500 | ~77% | ~23% |

Stage 2 grows slightly as a fraction of the cycle as Po increases, because Stage 1 speeds up with pressure while Stage 2 does not.

---

## Section 2 — Stage 1: Data vs Model, C_visc Calibration Path

### Observed timing

| Po (mbar) | t_S1 mean (s) | Relative to 200 mbar | Ideal Poiseuille ratio |
|---|---|---|---|
| 200 | ~1.51 | 1.00 | 1.00 |
| 300 | ~0.97 | 0.64 | 0.67 |
| 400 | ~0.69 | 0.46 | 0.50 |
| 500 | ~0.51 | 0.34 | 0.40 |

Power-law fit: **t_S1 ∝ Po^(−1.2)** (ideal Poiseuille = −1.0).

The slightly steeper-than-ideal exponent indicates a modest additional Po-dependence beyond simple Poiseuille — likely from the external water flow creating a back-pressure that grows with Po, or from an interfacial effect that weakens slightly at higher Po.

### Model prediction (V5_30_3_3 geometry)

The Stage 1 model computes:

```
t_stage1 = C_visc × V_reset × R_rung / DP_rung
```

For the V5_30_3_3 device (μ_oil = 60 mPa·s, rung 10×8×4000 µm, exit 30×10 µm):

- **R_rung** (Shah–London rectangular channel, α = 8/10 = 0.8):
  f(0.8) = 57.5, R_rung = 57.5 × 0.06 × 4e−3 / (10e−6 × (8e−6)³) ≈ **2.70 × 10¹⁸ Pa·s/m³**

- **V_reset** (model formula: L_r = exit_width = 30 µm):
  V_reset = 30² × 10 µm³ = 9000 µm³ = **9.0 × 10⁻¹⁵ m³**
  (Experiment confirms: mean measured V_reset ≈ 8.5–9.0 fL — close match)

- **Baseline t (C_visc = 1.0) with DP_rung = Po (full pressure applied):**

| Po (mbar) | DP_rung (Pa) | t_base (s) | t_obs (s) | C_visc implied |
|---|---|---|---|---|
| 200 | 20,000 | 1.21 | 1.51 | **1.25** |
| 300 | 30,000 | 0.81 | 0.97 | **1.20** |
| 400 | 40,000 | 0.61 | 0.69 | **1.13** |
| 500 | 50,000 | 0.48 | 0.51 | **1.06** |

### Calibration conclusion

With the actual device parameters (μ_oil = 60 mPa·s), the default model (C_visc = 1.0) already falls within ~25% of the observed Stage 1 timing. The implied C_visc is in the range **1.05–1.25**, not the "3–5×" range stated in the module docstring.

**Important caveat:** This analysis assumes DP_rung = Po (i.e., the hydraulic network delivers full Po to each rung with negligible network pressure loss). If the hydraulic model computes a lower DP_rung at the rung inlet — due to main-channel resistance, water back-pressure, or the running emulsion load — then C_visc will be correspondingly higher. The calibration should be performed *after* confirming what value the hydraulic network returns for DP_rung at each Po.

**Recommended calibration procedure:**
1. Run the v3 model at Po = 200, 300, 400, 500 mbar and log the `DP_rung_Pa` from `stage1_result.diagnostics`.
2. Compare to experimental t_S1 mean at each Po using:
   `C_visc_fitted = t_S1_obs × DP_rung / (R_rung × V_reset)`
3. Fit a single global C_visc (or allow weak Po dependence if the exponent is significantly off −1.0).

**The power-law exponent mismatch (−1.2 vs −1.0)** should be addressed after the main C_visc calibration. Likely explanations: capillary backpressure (P_cap ∝ 1/R, which reduces effective DP at low Po), or the water channel resistance growing with Qw which increases with Po.

---

## Section 3 — Stage 2: Po Dependence, D_drop, and Recommendation to Keep Simple

### Observed timing

| Po (mbar) | t_S2 mean (s) | t_S2 std (s) |
|---|---|---|
| 200 | ~0.24 | ~0.06 |
| 300 | ~0.21 | ~0.04 |
| 400 | ~0.17 | ~0.03 |
| 500 | ~0.16 | ~0.04 |

Global coefficient of variation across all observations: approximately **25–35%**.

Stage 2 decreases weakly from ~240 ms at 200 mbar to ~160 ms at 500 mbar (a 1.5× change over 2.5× pressure range). This contrasts with Stage 1 which changes ~3× over the same range. Stage 2 is **predominantly capillary-controlled**, with a minor Po sensitivity.

The minor Po dependence is plausible: at higher Po, the oil pressure inside the forming neck is greater, which slightly accelerates the neck thinning. This is not captured by a purely capillary model, but it is a secondary effect and the current physics plan is correct to treat Stage 2 as capillary-controlled.

**Recommendation: keep Stage 2 physics simple.** The baseline snap-off-at-R_critical approach is appropriate. Do not add a Po-dependent correction to Stage 2 timing unless quantitative fit quality requires it.

### Droplet size

| Po (mbar) | D_drop mean (µm) | D_drop std (µm) |
|---|---|---|
| 200 | ~26.5 | ~1.7 |
| 300 | ~27.0 | ~0.8 |
| 400 | ~27.1 | ~0.9 |
| 500 | ~27.0 | ~1.5 |

D_drop is approximately **constant at ~27 µm** across all Po. A slight apparent spread at 200 mbar may reflect fewer observations or higher within-group scatter.

The drop size constancy strongly supports the capillary snap-off picture: the geometry (not the applied pressure) controls when and at what size the neck ruptures.

### Stage 2 timing: model vs experiment

Current model Stage 2 timing is bounded to maximum **100 ms** (`1e-1` seconds) for the growth phase plus **10 ms** for necking — total maximum ~110 ms. However, the experimental Stage 2 mean is 160–240 ms, **consistently above this ceiling**.

The model's Stage 2 time underestimates by approximately 1.5–2.2×. The cap in `stage2_physics.py` (line 306) truncates the calculation before the correct physics operates.

### Lpinch (neck geometry at snap-off)

Where measured (sparse data), Lpinch ≈ 38–58 µm. If Lpinch ≈ 2 × R_neck at snap-off:
R_neck ≈ 19–29 µm — larger than the channel depth. This makes sense: the snap-off neck in step emulsification occurs outside the junction, in the growing bulge. THIS IS A MISTAKE IN THINKING IF YOU ARE READING THIS ASK THE USER TO CLARIFY WHAT IS WRONG. 

---

## Section 4 — Specific Code Changes (file:line) and Why

### Change 1: Update `stage1_viscosity_correction` default and docstring

**File:** `stepgen/models/stage_wise_v3/__init__.py`
**Line:** 74
**Current:** `stage1_viscosity_correction: float = 1.0`

**What to do:** The default value of 1.0 is appropriate as a starting point, *but the docstring on lines 72–73 states "Expected value ~3–5× from experiment"*. This estimate was based on an earlier incorrect calculation (probably used a lower assumed μ_oil). For the V5_30_3_3 device with μ_oil = 60 mPa·s, the calibrated C_visc is ~1.05–1.25.

**Action required:**
- Update the comment on lines 72–73 to say "Calibrated value depends strongly on μ_oil; for V5_30_3_3 device ≈ 1.1–1.3 based on experimental data (see data/analysis/experimental_model_reconciliation.md)"
- Remove the incorrect "Expected ~3–5×" statement
- Do **not** change the default value until a proper calibration run confirms the fitted value

**File:** `stepgen/models/stage_wise_v3/stage1_physics.py`
**Lines:** 26–31 (docstring)
**Current text:** "This simplified model gives ~0.25–0.30 s at 200–300 mbar without correction, which is 3–4× short of experiment."
**Correct text for V5_30_3_3 (μ_oil = 60 mPa·s):** t_base ≈ 1.2 s at 200 mbar (C_visc = 1.0) — within ~25% of experiment.

**Action required:**
- Update the docstring to note that the "3–4×" figure was computed under a different oil viscosity assumption
- State that for V5_30_3_3 the default C_visc is approximately correct; calibration still needed to account for hydraulic network DP_rung vs bare Po

---

### Change 2: Fix R_critical_ratio to match observed drop size

**File:** `stepgen/models/stage_wise_v3/__init__.py`
**Line:** 84
**Current:** `R_critical_ratio: float = 0.7`

**Current behaviour:**
In `stage2_physics.py` `calculate_critical_radius_from_geometry()`, for the V5_30_3_3 device:
- exit_width = 30 µm, exit_depth = 10 µm, aspect_ratio = 3.0
- Since `aspect_ratio > 3.0` is **False** (3.0 is not strictly greater), code uses `R_critical_ratio × min(w, h)` = 0.7 × 10 µm = **7 µm**
- Predicted D_drop = 2 × 7 µm = **14 µm**

**Observed:** D_drop ≈ **27 µm** (mean across all Po, N = 43)

The current R_critical_ratio understimates D_drop by a factor of ~1.9.

**Required correction:**
R_critical = D_drop_obs / 2 ≈ 13.5 µm
R_critical_ratio = 13.5 / 10 = **1.35**

**Action required:**
- Update default: `R_critical_ratio: float = 1.35`
- Update the comment to clarify: "R_crit / exit_depth for high-aspect (w/h = 3) step emulsification; calibrated from V5_30_3_3 D_drop = 27 µm"
- Note that this ratio is device-geometry-dependent and should be re-calibrated for each junction design

**Alternative formulation (future):** The step emulsification literature relates D_drop to both exit_width and exit_depth (D ∝ w^a × h^b). If cross-device predictions are needed, a geometry scaling law should replace the single ratio. This is a deferred improvement.

---

### Change 3: Remove growth_time ceiling that clips Stage 2

**File:** `stepgen/models/stage_wise_v3/stage2_physics.py`
**Line:** 306
**Current code:**
```python
growth_time = max(min(growth_time, 1e-1), 1e-6)  # 1 µs to 100 ms
```

**Problem:**
Experimental Stage 2 is 160–240 ms. This 100 ms upper bound silently clips all predictions for this device. Any diagnostic output showing t_growth = 100 ms is hitting the ceiling.

**Action required:**
- Raise upper bound to 1.0 s: `growth_time = max(min(growth_time, 1.0), 1e-6)  # 1 µs to 1 s`
- Or better: remove the clipping entirely and let the physics compute freely, then add a validation warning if the result is outside a physically plausible range

**Note on absolute Stage 2 timing:**
Even with the ceiling removed, the `simulate_droplet_growth_to_critical_radius()` function uses a simplified constant-pressure model (line ~285–310) that may not give quantitatively correct Stage 2 durations. Bringing Stage 2 timing into quantitative agreement with experiment is a deferred calibration step. The priority is: (1) correct D_drop via R_critical_ratio, (2) remove the clipping, (3) calibrate t_S2 if needed.

---

### Change 4: Fix boundary condition edge case in R_critical calculation

**File:** `stepgen/models/stage_wise_v3/stage2_physics.py`
**Line:** 238
**Current code:**
```python
if aspect_ratio > 3.0:
    R_critical = R_critical_ratio * h  # Depth-limited for high aspect ratios
else:
    R_critical = R_critical_ratio * min(w, h)  # Geometric mean for normal aspects
```

**Issue:**
For the V5_30_3_3 device, aspect_ratio = w/h = 30/10 = exactly 3.0, so `aspect_ratio > 3.0` is False. The device falls into the "normal aspect" branch using `min(w, h) = h`. The branch labelling is misleading — the "high aspect" branch was intended for w/h = 3 devices like this one, but the boundary condition excludes it.

**Action required:**
Change `> 3.0` to `>= 3.0`:
```python
if aspect_ratio >= 3.0:
    R_critical = R_critical_ratio * h  # Depth-limited for high-aspect junctions (w/h ≥ 3)
```

This is a one-character fix but is semantically correct for step emulsification devices where h sets the dominant size constraint.

---

## Section 5 — Physics Understanding Update

### What the experimental data confirms

1. **Stage 1 is Poiseuille rung-flow limited.** The model's identification of R_rung and V_reset as the key parameters is correct. The Po scaling (exponent −1.2, close to −1.0) is consistent with viscous Poiseuille flow through the rung.

2. **C_visc is close to 1 for the V5_30_3_3 device.** This implies that bulk Poiseuille flow through the rung (without surface viscosity enhancement) is the dominant resistance. The "3–5× correction" suggested in the code was based on a different viscosity assumption. At μ_oil = 60 mPa·s the base model is already approximately correct.

3. **Stage 2 snap-off is capillary-controlled.** The ~5× weaker Po sensitivity of Stage 2 compared to Stage 1 confirms this. The current model's use of R_critical as the governing snap-off criterion is physically correct.

4. **V_reset is approximately Po-independent.** The meniscus reset position (L_menpoint ≈ 20–22 µm) does not vary strongly with Po. This means it is a geometric feature of the device, not a function of pressure, validating the model's use of a fixed V_reset.

5. **D_drop is approximately constant.** D_drop ≈ 27 µm across all Po (±2 µm), consistent with geometry-set snap-off at a fixed R_critical. The slight decrease at high Po (if present) is a second-order effect.

### What the model gets wrong or is not yet calibrated

1. **R_critical_ratio = 0.7 underpredicts D_drop by 2×.** For this device and geometry, R_critical_ratio ≈ 1.35 is correct. The default must be updated.

2. **The "3–4× slow" docstring comment is device-dependent.** It reflects a calculation done with a lower μ_oil assumption, not the actual V5_30 parameters. With the actual μ_oil = 60 mPa·s, the base model prediction is already within ~25% of experiment.

3. **Stage 2 timing is underestimated by 1.5–2×.** The 100 ms cap clips the model. Even with the cap removed, the simplified growth model needs calibration for quantitative Stage 2 timing. However, Stage 2 timing is not critical for the primary model outputs (D_drop, cycle frequency) because it is the smaller fraction of the cycle (17–23%).

4. **The −1.2 exponent (vs ideal −1.0) is unexplained.** The most likely cause is that at lower Po the capillary back-pressure from the meniscus represents a larger fraction of the driving pressure, effectively slowing Stage 1 more than the pure Poiseuille model predicts. This would be captured by including a capillary pressure term: `DP_eff = DP_rung − P_cap`. At 200 mbar with γ=15 mN/m and a ~30 µm meniscus:
   P_cap ≈ 2γ/R ≈ 2×0.015/(15e−6) ≈ 2000 Pa ≈ 20 mbar
   This is ~10% of 200 mbar but ~4% of 500 mbar, which would slightly steepen the exponent.

### Updated understanding of DFU position effect

The within-Po scatter in Stage 1 timing is partly attributed to DFU position (downstream rungs see lower DP_rung due to main-channel pressure drop). However, the data do not show a clear monotonic trend with DFU position — scatter appears driven by other factors (local geometry, surfactant concentration, flow history). The hydraulic network model should capture DFU position effects through the reduced-order pressure calculation.

---

## Section 6 — Further Experimental Data Wishlist

### Priority 1 — C_visc calibration data (most valuable)

**Goal:** Isolate the effect of Po on Stage 1 timing with maximal control.

**What is needed:**
- Runs at a wider range of Po: ideally 100–600 mbar in 50 mbar steps
- Multiple repeats (≥5) at each Po to reduce per-Po variance
- All runs on the same DFU position (e.g., DFU=3 consistently) to eliminate DFU scatter
- Simultaneous recording of Qw so we can separate oil rung flow from water back-pressure

**Why:** The current Po range (200–500 mbar) shows an exponent of −1.2 but with scatter from DFU variation. A wider range with controlled DFU would determine whether the deviation from −1.0 is real and whether a capillary correction is needed.

---

### Priority 2 — Stage 2 timing decomposition

**Goal:** Separate the "neck inflation" (early Stage 2) from the "rapid snap-off" (late Stage 2).

**What is needed:**
- Higher frame rate video (ideally ≥100 fps vs current 25 fps) at the junction during Stage 2
- The current 25 fps gives only 4–8 frames per Stage 2 event (~200 ms / 40 ms per frame), which is insufficient to resolve internal dynamics

**Why:** The experimental Stage 2 measured here (Exp Stage 3 = model Stage 2) is 160–240 ms. Whether this is dominated by slow neck inflation or by a true capillary necking timescale determines whether the model needs a "droplet inflation phase" added to Stage 2.

---

### Priority 3 — D_drop vs Po at fixed geometry

**Goal:** Confirm that D_drop is truly Po-independent, or quantify any residual dependence.

**What is needed:**
- More observations at Po = 200 mbar (currently only 7 DFU positions sampled, with high scatter)
- Droplet diameter measured with a calibrated scale bar (not just pixel count)

**Why:** The slight apparent increase in D_drop scatter at 200 mbar (vs 300–500 mbar) may be real (pressure is barely above the critical pressure for step formation, so the snap-off condition is less stable) or an artefact of fewer observations.

---

### Priority 4 — Separate μ_oil measurement

**Goal:** Confirm the assumed oil viscosity μ_oil = 60 mPa·s.

**What is needed:**
- Viscometer measurement of the actual oil batch used in the experiments
- Or: extract μ_oil from a Stage 1 rung-flow experiment on a single-rung test device

**Why:** C_visc is directly proportional to μ_oil. If the actual oil viscosity differs from 60 mPa·s by 20%, the calibrated C_visc shifts by the same amount. This is the largest single uncertainty in the Stage 1 calibration.

---

### Priority 5 — Multi-device geometry comparison

**Goal:** Validate the R_critical_ratio = D_drop / (2 × exit_depth) formula across devices.

**What is needed:**
- Same experiment run on at least one device with a different junction geometry (e.g., 30×20 µm or 20×10 µm)
- Record D_drop and t_S1 at matched Po values

**Why:** The current R_critical_ratio = 1.35 is back-calculated from a single device. Step emulsification theory predicts D_drop scales with both exit_width and exit_depth. Testing a second device would distinguish between ratio-based and geometry-scaling-law approaches.

---

## Appendix: Key Numbers at a Glance

### V5_30_3_3 device, μ_oil = 60 mPa·s

| Parameter | Value |
|---|---|
| R_rung (Shah–London, α=0.8) | 2.70 × 10¹⁸ Pa·s/m³ |
| V_reset (model: 30²×10 µm³) | 9000 µm³ = 9.0 fL |
| V_reset (experiment mean) | ~8.5–9.0 fL |
| t_base at 200 mbar (C_visc=1) | 1.21 s |
| t_S1 observed at 200 mbar | ~1.51 s |
| Implied C_visc at 200 mbar | ~1.25 |
| Implied C_visc at 500 mbar | ~1.05 |
| t_S2 observed (all Po) | 160–240 ms |
| D_drop observed (all Po) | ~27 µm (σ ≈ 1.5 µm) |
| R_critical from D_drop | ~13.5 µm |
| R_critical_ratio (correct) | 1.35 (currently 0.7 in code) |
| Stage 1 Po exponent | −1.2 (ideal −1.0) |
| Stage 2 Po exponent | ~−0.2 to −0.3 (approximately 0) |

### Units note

`Q_apparent_nLhr` in `stage_timing_clean.csv` is labelled nL/hr but the multiplier `1e9` in the analysis script gives µL/hr. Actual rung flow rate during Stage 1 refill is approximately **0.025–0.065 µL/hr** per rung. This has no impact on the timing calibration (which uses t directly) but should be corrected in the analysis script if Q is used for absolute comparisons.
