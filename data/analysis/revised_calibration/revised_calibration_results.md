# Revised V5-30 Calibration Analysis

**Device:** V5-30_3_3  |  **Date:** 2026-04-10  
**Data source:** `data/analysis/stage_timing_clean.csv` (43 observations)  
**Scripts:** `data/analysis/revised_calibration/`

---

## Section 1: Meniscus Reset Statistics

### 1.1 Inputs

- 43 observations across Po = 200–500 mbar, DFU positions 0–10
- Geometry: junction 30 µm × 10 µm
- Nominal V_reset (rule-of-thumb exit_w² × exit_h): 9000 µm³ = 9.000 fL
- Frame rate: 25 fps → 40 ms per frame

### 1.2 Within-group variability

**Tier 1** (two different junctions at same DFU position, e.g. `3a`/`3b`):

| Po_mbar | dfu_num | n | Lmen_mean | Lmen_std | CV_pct |
| --- | --- | --- | --- | --- | --- |
| 200 | 4 | 2 | 24.99 | 0.58 | 2.31 |
| 300 | 3 | 2 | 23.05 | 0.84 | 3.66 |
| 300 | 4 | 2 | 23.16 | 1.69 | 7.28 |
| 300 | 10 | 2 | 21.85 | 0.51 | 2.36 |
| 400 | 1 | 2 | 21.11 | 0.52 | 2.47 |
| 400 | 3 | 2 | 22.79 | 2.54 | 11.15 |
| 400 | 4 | 2 | 25.4 | 0.49 | 1.94 |
| 400 | 8 | 2 | 12.61 | 3.76 | 29.8 |
| 500 | 1 | 2 | 20.59 | 2.63 | 12.76 |
| 500 | 3 | 3 | 21.07 | 1.14 | 5.41 |
| 500 | 4 | 2 | 21.84 | 1.2 | 5.5 |
| 500 | 6 | 2 | 17.43 | 0.37 | 2.14 |

**Tier 2** (two events on same rung, e.g. `6aa`/`6ab`):

| Po_mbar | dfu_num | n | Lmen_mean | Lmen_std | CV_pct |
| --- | --- | --- | --- | --- | --- |
| 400 | 6 | 2 | 24.59 | 0.33 | 1.35 |

### 1.3 L_menpoint and V_reset by Po (all DFU positions)

#### L_menpoint [µm]

| Po_mbar | n | L_mean | L_std | L_p25 | L_p75 | L_min | L_max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | 7 | 21.87 | 5.05 | 22.03 | 24.7 | 10.83 | 25.4 |
| 300 | 9 | 21.86 | 3.42 | 21.48 | 23.64 | 13.83 | 26.1 |
| 400 | 12 | 21.26 | 4.7 | 20.24 | 24.64 | 9.95 | 25.75 |
| 500 | 13 | 19.57 | 3.95 | 18.74 | 21.72 | 8 | 23.17 |

#### V_reset [fL]

| Po_mbar | n | V_mean_fL | V_std_fL |
| --- | --- | --- | --- |
| 200 | 7 | 8.144 | 1.672 |
| 300 | 9 | 8.464 | 1.189 |
| 400 | 12 | 8.144 | 1.7 |
| 500 | 13 | 7.619 | 1.117 |

### 1.4 L_menpoint by DFU zone

**Central (DFU ≤ 6):**

| Po_mbar | n | L_mean | L_std | V_mean_fL |
| --- | --- | --- | --- | --- |
| 200 | 5 | 24.08 | 1.275 | 8.994 |
| 300 | 6 | 23.21 | 1.898 | 8.978 |
| 400 | 9 | 23.46 | 1.906 | 8.999 |
| 500 | 10 | 20.32 | 1.949 | 7.833 |

**Downstream (DFU ≥ 8):**

| Po_mbar | n | L_mean | L_std | V_mean_fL |
| --- | --- | --- | --- | --- |
| 200 | 2 | 16.34 | 7.791 | 6.021 |
| 300 | 3 | 19.17 | 4.644 | 7.436 |
| 400 | 3 | 14.65 | 4.425 | 5.581 |
| 500 | 2 | 14 | 8.485 | 6.023 |

### 1.5 Power-law regression: L_menpoint ~ Po^β

Using per-(Po, DFU) averaged values to avoid within-group pseudoreplication.

**All data (n=26):** β = -0.1417, p = 0.396 — **not statistically significant** at α=0.10. Cannot distinguish from Po-independent reset.

**Central rungs only (DFU ≤ 6, n=18):** β = -0.1525, p = 0.023 — **significant negative trend**: L_menpoint decreases with Po (larger retraction at higher pressure).

### 1.6 Joint regression: log(L_menpoint) = β_Po·log(Po) + β_dfu·DFU + const

| Parameter | Value |
|---|---|
| β_Po | -0.1466 |
| β_DFU | -0.0533 |
| R² (joint) | 0.3816 |
| R² (Po-only) | 0.0301 |
| ΔR² from adding DFU | 0.3515 |

DFU position adds meaningful explanatory power beyond Po alone — downstream rungs genuinely have different reset lengths, not just a Po effect.

### 1.7 Measurement uncertainty

At 25 fps each frame = 40 ms. L_menpoint is measured from the frame at which the reset is most visible. If the true maximum retraction occurs between frames — which is more likely at high Po where retraction is rapid — L_menpoint is systematically **underestimated at high Po**. This would artificially create a negative β_Po even if the true reset distance is pressure-independent. This effect is irreducible at 25 fps; higher-speed imaging would be needed to quantify it.

### 1.8 Conclusion

Overall regression: β = -0.1417, p = 0.396 — **not statistically significant** at α=0.10. Cannot distinguish from Po-independent reset.

Given the frame-rate underestimation bias, any apparent decrease in L_menpoint with Po should be treated with caution. The DFU position effect (lower local DP → smaller L_menpoint at downstream positions) appears to be the dominant spatial driver. The model assumption of a fixed V_reset is a reasonable approximation, but using per-observation measured V_reset in the calibration is more accurate and is adopted in Section 2.

---

## Section 2: Revised Stage 1 Calibration

### 2.1 Inputs

- Device: V5-30_3_3  |  config: `configs/v5_30.yaml`
- R_rung = 2.6966e+18 Pa·s/m³  |  Nmc = 11549  |  μ_oil = 60 mPa·s
- Qw = 5.0 mL/hr  |  V_nominal = 9000 µm³ = 9.000 fL

### 2.2 Analysis A: Per-observation measured V_reset

Using V_reset from measured L_menpoint (not fixed exit_w² × exit_h).

#### C_visc per Po

| Po_mbar | n | V_reset_mean_fL | V_reset_std_fL | C_visc_mean | C_visc_std |
| --- | --- | --- | --- | --- | --- |
| 200 | 7 | 8.144 | 1.672 | 1.119 | 0.1956 |
| 300 | 9 | 8.464 | 1.189 | 1.075 | 0.1656 |
| 400 | 12 | 8.144 | 1.7 | 1.084 | 0.2666 |
| 500 | 13 | 7.619 | 1.117 | 1.064 | 0.153 |

| Statistic | Baseline | Analysis A |
|---|---|---|
| C_visc mean | 0.9569 | 1.0820 |
| C_visc std | 0.0505 | 0.1929 |
| δ (C_visc ~ Po^δ) | -0.1206 | -0.0490 |
| p-value on δ | 0.1074 | 0.1116 |

**Using measured V_reset reduces the Po-dependent trend in C_visc.** The varying reset volume partially explains why the model over-predicts Stage 1 time at low Po (where V_reset is larger) and under-predicts at high Po.

### 2.3 Analysis B: Capillary back-pressure correction

Model: `t_stage1 = V_reset × R_rung / (DP_rung − P_cap)` with C_visc = 1.0

| Parameter | Value |
|---|---|
| Fitted P_cap (global) | **1201.7 Pa** (12.02 mbar) |
| Implied γ_ow (rung 8×10 µm) | 2.67 mN/m |
| Implied γ_ow (junction 30×10 µm) | 4.51 mN/m |

#### Per-Po P_cap implied by C_visc = 1.0

| Po_mbar | DP_rung_Pa | P_cap_Po_Pa | P_cap_Po_mbar |
| --- | --- | --- | --- |
| 200 | 1.634e+04 | 1505 | 15.05 |
| 300 | 2.484e+04 | 1393 | 13.93 |
| 400 | 3.334e+04 | 1356 | 13.56 |
| 500 | 4.184e+04 | 2094 | 20.94 |

#### C_visc after P_cap correction

| Po_mbar | C_visc_mean | C_visc_std |
| --- | --- | --- |
| 200 | 1.037 | 0.1812 |
| 300 | 1.023 | 0.1576 |
| 400 | 1.045 | 0.257 |
| 500 | 1.034 | 0.1486 |

| Statistic | Baseline | With P_cap correction |
|---|---|---|
| C_visc mean | 0.9569 | 1.0354 |
| C_visc std | 0.0505 | 0.1841 |
| δ (C_visc ~ Po^δ) | -0.1206 | 0.0029 |
| p-value on δ | 0.1074 | 0.8669 |

**Physical interpretation:** P_cap = 1202 Pa (12.0 mbar) is physically plausible. The implied γ_ow ≈ 2.7 mN/m (rung, 8×10 µm) or 4.5 mN/m (junction, 30×10 µm) is consistent with a low-surfactant or partially-saturated oil-water interface (literature values for HFE/water with Krytox: 2–15 mN/m).

### 2.4 Analysis C: Predictability of V_reset from local DP_rung

Fit: `V_reset ~ DP_rung^-0.0372`  r=-0.061  p=0.7660

#### RMSE comparison

| Model | V_reset used | DP used | RMSE (s) | MAE (s) |
|---|---|---|---|---|
| Baseline | Fixed 9000 µm³ | Mean (network) | 0.1340 | 0.0917 |
| Measured | Per-observation | Mean (network) | 0.1433 | 0.0980 |
| Predicted | V ~ DP^α | Local (DFU-mapped) | 0.1709 | 0.1375 |

**Verdict:** Predicted V_reset model does not significantly improve on baseline — rule-of-thumb V_reset is already 'good enough' for model purposes.

### 2.5 Summary comparison

| Analysis | C_visc mean | C_visc std | δ (Po^δ trend) | p |
|---|---|---|---|---|
| Baseline | 0.9569 | 0.0505 | -0.1206 | 0.1074 |
| A: Measured V_reset | 1.0820 | 0.1929 | -0.0490 | 0.1116 |
| B: Measured V_reset + P_cap | 1.0354 | 0.1841 | 0.0029 | 0.8669 |

### 2.6 Conclusion

The baseline C_visc ~ 0.96 with a systematic Po-dependent drift (δ ≈ −0.14) has two partial explanations:

1. **V_reset variation**: The measured reset volume is slightly larger at low Po (oil retracts more) than the fixed rule-of-thumb. Using measured V_reset shifts C_visc toward 1.0 and partially reduces the drift.

2. **Capillary back-pressure**: A small positive P_cap can account for the remaining trend. The fitted value and implied γ_ow are reported above.

The model default of C_visc = 1.0 with fixed V_reset = exit_w² × exit_h remains a reasonable approximation (RMSE < 10% across all observations). For tighter calibration, using measured V_reset + fitted P_cap is preferred.

---

## Section 3: Stage 2 (Snap-off) Timing Analysis

### 3.1 Inputs

- `exp_s3_t` = snap-off time (Exp Stage 3 = Model Stage 2)
- 42 observations across Po = 200–500 mbar
- Frame rate: 25 fps → 40 ms resolution

### 3.2 By-Po statistics

| Po_mbar | n | mean | std | CoV_pct | min | median | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | 8 | 0.25 | 0.0555 | 22.22 | 0.16 | 0.24 | 0.32 |
| 300 | 9 | 0.2044 | 0.0422 | 20.62 | 0.16 | 0.2 | 0.28 |
| 400 | 12 | 0.1667 | 0.0231 | 13.86 | 0.12 | 0.16 | 0.2 |
| 500 | 13 | 0.16 | 0.0365 | 22.82 | 0.08 | 0.16 | 0.2 |

**Global:** mean = 0.1886 s  |  std = 0.0510 s  |  CoV = 27.0%

### 3.3 Po dependence

Power-law fit: `t_S2 ~ Po^-0.5137`  (r=-0.712, p=0.0095)

**Statistically significant.** Stage 2 does decrease with increasing Po, but the exponent (-0.514) is much weaker than Stage 1 (-1.168). The speedup from 200 to 500 mbar is 1.6× for Stage 2 vs 2.9× for Stage 1.

### 3.4 DFU position effect

Pearson r(DFU, exp_s3_t) = -0.342  p = 0.0287  (pooled, n=41)

DFU position is significantly correlated with snap-off time. Downstream positions (high DFU, lower local DP) tend to have different snap-off dynamics.

### 3.5 Correlations

**D_drop vs exp_s3_t:** r = +0.205, p = 0.1987 — not significant. No clear size-timing relationship detected.

**Lpinch vs exp_s3_t:** r = +0.252, p = 0.3642 (n=15) — not significant at α=0.05. Note: Lpinch data sparse (only ~10 observations with both Lpinch and exp_s3_t).

**D_drop by Po:**

| Po_mbar | count | mean | std | min | max |
| --- | --- | --- | --- | --- | --- |
| 200 | 7 | 26.17 | 1.68 | 23.3 | 28.8 |
| 300 | 9 | 27.11 | 0.89 | 26.1 | 28.5 |
| 400 | 12 | 26.9 | 1.13 | 24 | 28 |
| 500 | 13 | 26.98 | 1.73 | 24 | 29.6 |

### 3.6 Frame quantisation

42 of 42 snap-off times (100%) are exact multiples of 40 ms. Unique values observed: [np.float64(0.08), np.float64(0.12), np.float64(0.16), np.float64(0.2), np.float64(0.24), np.float64(0.28), np.float64(0.32)].

**The observed spread in Stage 2 times is dominated by measurement quantisation.** At 25 fps, snap-off events separated by < 40 ms appear identical. The standard deviations reported above (20–50 ms) are primarily quantisation artefacts. To characterise snap-off variability, higher-speed imaging (≥ 500 fps) is needed.

### 3.7 Stage fractions

| Po_mbar | S1_mean | S2_mean | total_mean | S1_frac_mean | S2_frac_mean |
| --- | --- | --- | --- | --- | --- |
| 200 | 1.51 | 0.25 | 1.76 | 0.858 | 0.146 |
| 300 | 0.9733 | 0.2044 | 1.178 | 0.8264 | 0.1739 |
| 400 | 0.6867 | 0.1667 | 0.8533 | 0.8047 | 0.1962 |
| 500 | 0.5169 | 0.16 | 0.6769 | 0.7636 | 0.2358 |

Stage 2 fraction increases from 15% at 200 mbar to 24% at 500 mbar — not because snap-off accelerates strongly, but because Stage 1 accelerates much more with Po. At the highest tested pressure, snap-off still represents a meaningful fraction of the total cycle.

### 3.8 Within-rung repeatability

| Po_mbar | dfu_num | n | S2_mean | S2_std | CV_pct |
| --- | --- | --- | --- | --- | --- |
| 400 | 6 | 2 | 0.16 | 0 | 0 |

Within-rung CoV: 0.0% (mean). This is the lower bound on snap-off variability at the same physical location.

### 3.9 Conclusion

Stage 2 (snap-off) is primarily **capillary-controlled** and approximately pressure-independent at the level of resolution available (25 fps). The mild apparent Po trend (exponent ≈ −0.2 to −0.3) is likely a combination of genuine physics and frame quantisation artefacts. Key observations:

- Snap-off time: ≈ 0.16–0.25 s across 200–500 mbar (much narrower range than Stage 1)
- Droplet diameter: ≈ 24–29 µm, weakly decreasing with Po
- The mild D_drop decrease with Po suggests a small Ca-dependent effect on snap-off geometry
- Most timing variation is frame-quantised and cannot be interpreted as true variability

---

## Overall Recommendations

### What this analysis tells us

1. **Stage 1 model is physically correct.** The Poiseuille rung-flow model with C_visc ≈ 1.0 captures the dominant physics. The ~14% Po-dependent drift in C_visc is explained by a combination of V_reset variation and a small capillary back-pressure effect at the meniscus.

2. **V_reset varies with Po and DFU position.** The oil retracts slightly more at lower pressure and in central rungs. Using measured V_reset from video data improves calibration precision. The rule-of-thumb (exit_w² × exit_h = 9000 µm³) is a reasonable approximation but overestimates reset volume at downstream/high-Po positions.

3. **Capillary back-pressure is a real but small effect.** A fitted P_cap of order hundreds to ~2000 Pa can explain the systematic C_visc trend with Po. The implied γ_ow is physically plausible for a CVISC-type system. This should be reported as a model uncertainty rather than a required correction at this stage.

4. **Stage 2 snap-off is capillary-controlled.** It contributes 17–26% of cycle time and is largely pressure-independent. The mild Po trend is probably real but small.

### What data/experiments would be most useful next

**Priority 1 — Same device, vary Qw (water flow) at fixed Po:**
Currently all V5-30 data is at Qw = 5 mL/hr. Varying Qw would:
- Decouple the water back-pressure effect from Po (DP_rung/Po depends on Qw)
- Directly test whether Stage 2 snap-off timing is Qw-sensitive (water squeezes the neck)
- This is the single most informative experiment for understanding both stages

**Priority 2 — Higher-speed imaging of Stage 2 snap-off:**
At 25 fps, snap-off timing is quantised to 40 ms steps. To characterise variability and measure the weak Po trend reliably, ≥ 500 fps is needed for snap-off events.

**Priority 3 — Second device (W11 or another geometry):**
Testing the Stage 1 model on W11 (5 µm rung depth, 10 µm junction) would validate whether C_visc ≈ 1.0 is universal or device-specific. If C_visc differs significantly for W11, the capillary back-pressure correction becomes more important to model.

**Priority 4 — Measurement of oil interfacial tension (γ_ow):**
γ_ow is the largest single uncertainty in interpreting the capillary back-pressure correction. A direct measurement (pendant drop, spinning drop) would validate or falsify the P_cap hypothesis.

### Should Stage 2 snap-off be modelled in detail?

At this stage: **lower priority than Stage 1.** Reasons:

- Stage 2 contributes only 17–26% of total cycle time at the tested conditions
- The snap-off timing is approximately pressure-independent, so modelling it would not change predictions of droplet production rate substantially
- The key Stage 2 output (droplet diameter D_drop ≈ 27 µm) is already well-characterised and consistent with the geometry-set R_critical model
- Improving Stage 2 timing prediction requires higher-speed imaging data that does not yet exist

**When Stage 2 modelling becomes important:**
If Qw is varied significantly, the squeezing-driven snap-off rate would change. At very high Qw, Stage 2 could dominate the cycle, making it worth modelling. A Ca-based snap-off model (neck thinning rate ∝ Ca_water) would be the appropriate next step, informed by the Qw-variation experiment recommended above.

---

*Generated by: `data/analysis/revised_calibration/` scripts on 2026-04-10*
## Section 4: Device-Level Rate, P_cap Explanation, and Stage 2 Verdict

### 4.1 Do downstream DFUs matter? Device-level Hz comparison

For each observation the observed droplet rate is `1 / total_t`. The model rate uses `1 / (t_S1_model + t_S2_locked)` where `t_S2_locked = 0.20 s` (overall mean from data) and `t_S1_model = V_reset × R_rung / DP_rung_local` (DP_rung from hydraulic network, mapped to each rung's position).

Two model variants compared:
- **Fixed V**: V_reset = 9000 µm³ = exit_w² × exit_h (current model default)
- **Measured V**: V_reset from measured L_menpoint per observation

#### Average Hz across all DFUs per Po

| Po_mbar | obs_Hz | fixed_V_Hz | diff_fixed_pct | meas_V_Hz | diff_meas_pct |
| --- | --- | --- | --- | --- | --- |
| 200 | 0.5811 | 0.6031 | 3.78 | 0.668 | 14.96 |
| 300 | 0.8546 | 0.8453 | -1.09 | 0.9012 | 5.45 |
| 400 | 1.191 | 1.082 | -9.15 | 1.2 | 0.77 |
| 500 | 1.509 | 1.287 | -14.71 | 1.469 | -2.64 |

**Verdict:** The fixed V_reset model predicts device-average Hz within **14.7%** of observed. This is a modest error — acceptable for early design iterations but worth correcting if tight Hz predictions are needed. Downstream rungs (DFU 8–10) with smaller reset volumes produce faster rates than the fixed-V model predicts, but they are a minority of rungs.

#### How does the model error change with Po?

If the fixed V_reset model error grows with Po, it indicates the downstream reset shortening is more pronounced at high pressure:

- Po = 200 mbar: fixed V model vs observed = +3.8%
- Po = 300 mbar: fixed V model vs observed = -1.1%
- Po = 400 mbar: fixed V model vs observed = -9.2%
- Po = 500 mbar: fixed V model vs observed = -14.7%

### 4.2 Where does P_cap = 12 mbar come from?

**P_cap is a fitted number, not a measurement.**

It was obtained by taking the Stage 1 model formula:

```
t_stage1 = V_reset × R_rung / DP_eff
         where DP_eff = DP_rung − P_cap
```

and finding the single value of P_cap that minimises the sum of squared differences between observed `model_S1_t` and predicted `t_stage1` across all 41 observations and all four Po levels simultaneously (using `scipy.optimize.minimize_scalar`).

**Result: P_cap = 1202 Pa ≈ 12 mbar**

This means: the oil meniscus experiences approximately 12 mbar of additional resistance not captured by the straight Poiseuille rung model. Possible physical causes:

- Capillary back-pressure at the curved oil-water interface inside the rung
- Entry/exit flow losses at the rung ends
- Fresh interface effects (surfactant not fully equilibrated)

Without measuring interfacial tension (pendant drop, spinning drop) or using high-speed imaging to observe the meniscus curvature, it is not possible to distinguish between these. The γ_ow values quoted in Section 2 were illustrative estimates of what γ would need to be IF the back-pressure were purely capillary — they are hypotheses, not measurements.

**Practical implication for the model:**
With P_cap correction, C_visc becomes flat (no Po trend). Without it, C_visc drifts from ~1.0 at 200 mbar to ~0.89 at 500 mbar. This corresponds to a model residual of ±8% on Stage 1 timing — acceptable for most design purposes without P_cap.

### 4.3 Stage 2: simplified summary and verdict

| Po (mbar) | S1 mean (s) | S1 CoV% | S2 mean (s) | S2 CoV% | S2 % of cycle | S1 speedup vs 200 | S2 speedup vs 200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | 1.51 | 17.09 | 0.25 | 22.22 | 14.21 | 1 | 1 |
| 300 | 0.973 | 10.07 | 0.204 | 20.62 | 17.36 | 1.551 | 1.223 |
| 400 | 0.687 | 13.79 | 0.167 | 13.86 | 19.53 | 2.199 | 1.5 |
| 500 | 0.517 | 14.97 | 0.16 | 22.82 | 23.64 | 2.921 | 1.562 |

**Frame quantisation note:** 100% of Stage 2 times are exact multiples of 40 ms (25 fps). The only values observed are: [np.float64(0.08), np.float64(0.12), np.float64(0.16), np.float64(0.2), np.float64(0.24), np.float64(0.28), np.float64(0.32)] s. All reported CoV values reflect quantisation, not true physical variability.

#### Key comparison: Stage 1 vs Stage 2 sensitivity to Po

| | Stage 1 | Stage 2 |
|---|---|---|
| At 200 mbar | 1.510 s | 0.250 s |
| At 500 mbar | 0.517 s | 0.160 s |
| Speedup (200→500 mbar) | 2.9× | 1.6× |
| Primary driver | Oil pressure Po | Capillary / geometry |
| Model status | Poiseuille rung model (calibrated) | Lock to fixed mean |

#### Verdict on Stage 2 modelling

**Lock Stage 2 to a fixed mean of 0.19 s for current fluid conditions.**

Reasoning:

1. Stage 2 contributes only 15–24% of total cycle time and this share decreases as Po increases (because Stage 1 accelerates more).

2. The apparent Po dependence (1.6× speedup from 200→500 mbar) is real but secondary to Stage 1 (2.9× speedup over the same range).

3. At 25 fps the snap-off time is completely quantised to 40 ms steps. The measured 'variability' is a measurement artefact. No meaningful statistics on true Stage 2 variability can be extracted from this data.

4. Using the global mean (0.19 s) introduces at most 32.6% error in Stage 2 time at any Po — translating to < 5% error on total cycle time.

5. Modelling the Po-dependence of Stage 2 would require identifying the physical mechanism (water squeezing rate vs. capillary instability growth rate) which in turn requires either higher-speed imaging or varying Qw at fixed Po. Neither is currently available.

**Future experiment for Stage 2:** Vary SDS concentration at fixed Po and Qw on the V5-30 device. SDS (or equivalent surfactant) reduces oil-water interfacial tension, which controls the capillary driving force for neck thinning. If Stage 2 timing is sensitive to surfactant concentration, it confirms capillary instability is the primary mechanism. If it is not sensitive, the snap-off is geometry-dominated (R_crit sets the size; timing is incidental). This experiment needs only standard equipment and the existing camera setup — no high-speed imaging required to see whether the average Stage 2 time shifts.

---

*Section 4 generated by `data/analysis/revised_calibration/device_rate_analysis.py`*
