# C_visc Calibration Results
## Stage 1 Poiseuille Refill Model — V5_30_3_3

**Date:** 2026-03-20  
**Device config:** configs/v5_30.yaml  
**Experimental data:** data/analysis/stage_timing_clean.csv  
**Water flow (Qw):** 5.0 mL/hr (default from v5_30.yaml)  

---

## Model formula

```
t_stage1 = C_visc × V_reset × R_rung / DP_rung
```

## Device parameters

| Parameter | Value |
|---|---|
| mu_oil | 60.0 mPa.s |
| Rung geometry | 10x8x4000 um (d x w x L) |
| Junction | 30x10 um (w x h) |
| Nmc (rungs) | 11549 |
| R_rung (Shah-London) | 2.6966e+18 Pa.s/m3 |
| V_reset = exit_w^2 x exit_h | 9000 um3 = 9.000 fL |

## Hydraulic network pressures

*P_oil and P_water from the full ladder-network solver at each Po, Qw = 5 mL/hr.*

| Po (mbar) | DP_mean (Pa) | DP as % of Po | P_oil inlet (Pa) | P_water outlet (Pa) |
|---|---|---|---|---|
| 200 | 16344.4 | 81.7% | 20000.0 | 0.0 |
| 300 | 24842.1 | 82.8% | 30000.0 | 0.0 |
| 400 | 33339.7 | 83.3% | 40000.0 | 0.0 |
| 500 | 41837.3 | 83.7% | 50000.0 | 0.0 |

## C_visc calibration

### Per-Po fit

| Po (mbar) | DP_mean (Pa) | t_base (s) | t_S1 obs (s) | C_visc (network DP) | C_visc (bare Po) |
|---|---|---|---|---|---|
| 200 | 16344.4 | 1.4849 | 1.5100 | **1.017** | 1.244 |
| 300 | 24842.1 | 0.9769 | 0.9733 | **0.996** | 1.203 |
| 400 | 33339.7 | 0.7279 | 0.6867 | **0.943** | 1.132 |
| 500 | 41837.3 | 0.5801 | 0.5169 | **0.891** | 1.065 |

### Global fit

| Statistic | Value |
|---|---|
| C_visc mean (all Po) | **0.962** |
| C_visc std | 0.056 |
| C_visc range | 0.891 – 1.017 |
| t_base Po exponent | -1.026 (ideal −1.0) |
| t_obs Po exponent | -1.168 |
| C_visc residual exponent (δ) | -0.142 (0 = no Po dependence) |

### Predicted vs observed with best-fit C_visc

*Using C_visc = 0.962*

| Po (mbar) | t_pred (s) | t_obs (s) | residual (%) |
|---|---|---|---|
| 200 | 1.4283 | 1.5100 | -5.4% |
| 300 | 0.9397 | 0.9733 | -3.5% |
| 400 | 0.7002 | 0.6867 | +2.0% |
| 500 | 0.5580 | 0.5169 | +7.9% |

## Po scaling analysis

Power-law exponents from log-log fit:

- **t_base ~ Po^(-1.026)** (model baseline, ideal −1.0)
- **t_obs ~ Po^(-1.168)** (experimental observation)
- **Δexponent = -0.142** (C_visc would need Po^(-0.142) dependence to fully close gap)

→ C_visc has **weak Po dependence**. A single global constant is a good approximation.

## Stage 2 summary (experimental, no model fit)

| Po (mbar) | t_S2 mean (ms) | t_S2 std (ms) |
|---|---|---|
| 200 | 250.0 | 55.5 |
| 300 | 204.4 | 42.2 |
| 400 | 166.7 | 23.1 |
| 500 | 160.0 | 36.5 |

Stage 2 is approximately Po-independent. No C_visc equivalent is fitted for Stage 2 at this stage.

## Interpretation and recommended code change

### Finding 1 — C_visc is approximately 1.0 (model correct as-is)

With the actual device parameters (mu_oil = 60 mPa.s, rung 10x8x4000 um), the fitted C_visc = **0.96 ± 0.06**.

This is within measurement uncertainty of 1.0. The Poiseuille refill model with bulk oil viscosity correctly predicts Stage 1 timing for this device **without requiring any empirical correction factor**.

This directly contradicts the comment in `stage1_physics.py` (lines 26–31) which states "~0.25–0.30 s at 200–300 mbar without correction, which is 3–4× short of experiment". That calculation was based on a lower assumed mu_oil (~10 mPa.s). With the actual mu_oil = 60 mPa.s, the model prediction at 200 mbar is 1.485 s — within 1.7% of the observed 1.510 s.

### Finding 2 — Water back-pressure reduces DP_rung to ~82% of Po

The hydraulic network does **not** deliver the full Po as DP_rung. At Qw = 5 mL/hr, the water channel builds a back-pressure that reduces DP_rung to 81.7–83.7% of Po across the Po range:

| Po (mbar) | DP_mean as % of Po |
|---|---|
| 200 | 81.7% |
| 300 | 82.8% |
| 400 | 83.3% |
| 500 | 83.7% |

This back-pressure grows slightly with Po (because Qw is fixed and the water channel pressure drop does not grow proportionally with Po). This is the **dominant factor** explaining why the bare-Po column `C_visc_fullPo` shows values of 1.06–1.24 while the network-corrected values are 0.89–1.02.

The hydraulic network is doing real physics here. If someone ran the model with `DP_rung = Po` (bypassing the network), they would need C_visc ≈ 1.1–1.24 to compensate.

### Finding 3 — Residual systematic trend (not fully explained by C_visc = const)

C_visc decreases from 1.017 at 200 mbar to 0.891 at 500 mbar. The residual exponent is **-0.142** (would need C_visc ~ Po^(-0.142) to fully close the gap). With a single C_visc = 0.962, the residuals range from -5.4% (200 mbar) to +7.9% (500 mbar).

The most physically plausible explanation: **capillary back-pressure from the advancing meniscus** is a fixed pressure (~2γ/R ≈ 2 × 0.015 / 15e-6 ≈ 2000 Pa ≈ 20 mbar) that reduces the effective driving pressure more at low Po (20/200 = 10% reduction) than at high Po (20/500 = 4% reduction). This would naturally cause the apparent driving pressure to fall more steeply with increasing Po than the network DP_rung alone, producing a steeper observed exponent (-1.168 vs -1.026).

To test this: compute `DP_eff = DP_rung - P_cap` and refit — if P_cap ≈ 2000 Pa, the residual trend should largely disappear.

### Summary of what to do with the code

| Issue | Action |
|---|---|
| `C_visc` default = 1.0 | **Keep as-is** — the default is correct for this device |
| Docstring claim "3–4× short" | **Correct** — was wrong viscosity assumption; with mu_oil = 60 mPa.s model is accurate |
| Docstring claim "expected 3–5×" | **Correct** — remove; actual C_visc ≈ 1.0 |
| Residual ±8% trend | **Document** as capillary back-pressure effect; add P_cap correction in a later phase if needed |
| DP_rung from network | **Confirmed correct** — network provides 82% of Po due to water back-pressure; this is physical |

**Short recommendation:** Leave `stage1_viscosity_correction = 1.0`. The model is already calibrated. Fix the misleading docstring in `stage1_physics.py` and the "3–5×" comment in `__init__.py`.

---
*Generated by data/analysis/calibrate_cvisc.py*
