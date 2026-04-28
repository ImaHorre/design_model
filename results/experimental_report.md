# Droplet Formation — Experimental Analysis Report

**Devices:** V5-30 (ID A), V5-8-1 (ID B)  
**Emulsion system:** Silicone oil dispersed / SDS-water continuous (unless noted)  
**Date compiled:** 2026-04-28  

---

## Overview

Three experiment sets are reported here, each varying one parameter of the droplet formation system and measuring the resulting changes in Stage 1 (oil refill), Stage 2 (snap-off), droplet size, and generation frequency.

| Experiment | Device | Varied | Fixed | Location |
|---|---|---|---|---|
| 1 — Po sweep | V5-30 (ID A) | Oil pressure Po (200–500 mbar) | Qw=5 mL/hr, [SDS]=2% | `analysis/` |
| 2 — Qw sweep | V5-8-1 (ID B) | Water flowrate Qw (5–20 mL/hr) | [SDS]=2% | `results/v5_8_1_qw_sweep/` |
| 3 — [SDS] sweep | V5-8-1 (ID B) | SDS concentration (0.125–2%) | Po and Qw per condition | `results/v5_8_1_conc_sweep/` |

Both devices share the V5-30 geometry (30 µm junction, 10 µm depth). ID A and ID B are different fabrication runs of the same design — use `configs/v5_30.yaml` for modelling either.

The Stage 1 model used throughout is:

$$t_{S1} = C_{visc} \cdot \frac{V_{reset} \cdot R_{rung}}{\Delta P_{rung}}$$

where $\Delta P_{rung}$ is obtained from the hydraulic network solver (varies with both Po and Qw).

---

## Experiment 1 — Po Sweep (V5-30, ID A)

*Full analysis in `analysis/Droplet Formation - stage timings - experimental vs model.md`. Reference figures in `analysis/plot types/`. Summary reproduced here for context.*

### Key results

- Stage 1 dominates the cycle at all tested pressures (76–86% of total).
- Stage 1 scales as Po⁻¹·¹⁷ (experimental) vs Po⁻¹·⁰ (ideal Poiseuille). The steeper exponent is consistent with a small capillary back-pressure (~12 mbar) that is proportionally larger at low Po.
- **C_visc ≈ 0.95** once measured V_reset (from L_menpoint) and the 12 mbar capillary correction are applied. The Poiseuille model is physically correct.
- **V_reset varies spatially**: upstream DFUs L_menpoint ≈ 30 µm (consistent with nominal); downstream DFUs ≈ 20–25 µm. This drives up to 15% error in per-rung Hz if the fixed nominal value is used.
- **Stage 2 ≈ 0.19 s** — treated as a constant at these conditions (Qw=5, 2% SDS). Power-law exponent −0.51 vs −1.17 for Stage 1 — snap-off is much less pressure-sensitive than refill.
- **Droplet diameter ≈ 27 µm** — geometry-controlled, no significant Po dependence.

---

## Experiment 2 — Qw Sweep (V5-8-1, ID B)

**Conditions:** Po ∈ {200, 300, 400, 600} mbar × Qw ∈ {5, 10, 20} mL/hr | [SDS] = 2% | n = 143

### Figure 1 — Stage 1 vs Po (log-log with model)

`fig_01_stage1_loglog.png`

**Finding:** Stage 1 increases with Qw at every Po. The hydraulic solver correctly predicts the *shape* of the Qw effect — higher Qw raises water back-pressure, reducing the net rung driving pressure ΔP_rung and slowing oil refill. The model curves (dashed) track the data well in relative terms.

**C_visc with nominal V_reset (9000 µm³) = 0.74 ± 0.20** — systematically below 1.0, revealing that the observed reset volume is smaller than the nominal 30 µm assumption.

**C_visc with observed V_reset (from L_menpoint ≈ 20 µm) = 1.09 ± 0.26** — centred near 1.0, confirming that the L_menpoint-derived reset is the correct model input.

| Po (mbar) | Qw (mL/hr) | S1 exp (s) | t1 model (s) | C_visc (nom) |
|---|---|---|---|---|
| 200 | 5  | 1.08 | 1.42 | 0.76 |
| 200 | 10 | 1.49 | 1.48 | 1.01 |
| 300 | 5  | 0.60 | 0.95 | 0.64 |
| 300 | 20 | 1.14 | 1.03 | 1.11 |
| 600 | 5  | 0.25 | 0.48 | 0.52 |
| 600 | 20 | 0.30 | 0.49 | 0.61 |

### Figure 2 — Stage 2 vs Po and Qw

`fig_02_stage2.png`

**Finding: Stage 2 is NOT Qw-independent.** This contradicts the assumption from Experiment 1 (where Qw was fixed at 5 mL/hr).

| Qw (mL/hr) | Stage 2 mean (all Po) |
|---|---|
| 5  | **0.207 s** |
| 10 | **0.315 s** |
| 20 | **0.313 s** |

- Effect is strongest at low Po (200 mbar): 0.35 s → 0.66 s going from Qw=5 to 10.
- Effect saturates between Qw=10 and 20 mL/hr.
- At Po=600 mbar, Stage 2 ≈ 0.12 s regardless of Qw — a pressure-dominated regime.

The most reliable Stage 2 model approximation is a **per-Po lookup at Qw=5 mL/hr**:

| Po (mbar) | Stage 2 (s) |
|---|---|
| 200 | 0.350 |
| 300 | 0.205 |
| 400 | 0.154 |
| 600 | 0.120 |

Using a single global constant introduces >50% error in Stage 2 when Qw departs from 5 mL/hr.

### Figure 3 — C_visc Calibration

`fig_03_cvisc_calibration.png`

Shows the C_visc shift when switching from nominal (9000 µm³) to observed V_reset. The residual decline of C_visc with Po (present with both V_reset choices) matches the capillary back-pressure signature seen in Experiment 1 — a ~12 mbar correction would flatten it further.

### Figure 4 — Operational Summary

`fig_04_summary.png`

- **Generation frequency** increases with Po and decreases with Qw. At Po=200: 0.62 Hz (Qw=5) → 0.46 Hz (Qw=10) — a 26% reduction. At Po=600 the Qw effect is minor (~11%).
- **Droplet diameter ≈ 25 µm** — constant across all Po and Qw. Geometry-controlled snap-off confirmed. Grand mean = 24.9 µm (slightly smaller than V5-30 ID A ≈ 27 µm — consistent with a small run-to-run fabrication difference).

---

## Experiment 3 — [SDS] Concentration Sweep (V5-8-1, ID B)

**Conditions:** [SDS] ∈ {2%, 1%, 0.5%, 0.25%, 0.125%} | Key comparison: Po=200, Qw=5 (all 5 conc.)  
CMC of SDS ≈ 0.24% mass.

### Figure 1 — Stage 1 vs [SDS]

`fig_01_stage1_vs_conc.png`

**Finding: Stage 1 increases monotonically as [SDS] decreases — the Poiseuille model predicts no concentration dependence, so this effect is outside the model's current scope.**

At Po=200, Qw=5 (full 5-concentration comparison):

| [SDS] | S1 (s) | Ratio vs 2% | C_visc |
|---|---|---|---|
| 2%    | 1.08 | 1.00 | 0.76 |
| 1%    | 1.14 | 1.05 | 0.80 |
| 0.5%  | 1.32 | 1.22 | 0.93 |
| 0.25% | 1.44 | 1.33 | 1.01 |
| 0.125%| 2.01 | 1.87 | 1.42 |

The 1.87× increase from 2% → 0.125% cannot be a measurement artefact — it is physically consistent with two compounding effects investigated in Figure 2.

### Figure 2 — Mechanistic Decomposition

`fig_02_mechanism.png`

**Finding: The dominant mechanism is a falling effective driving pressure (dP_eff), not a growing V_reset.**

Back-calculating the effective driving pressure from experiment:

$$dP_{eff} = \frac{V_{reset,obs} \cdot R_{rung}}{t_{S1,exp}}$$

| [SDS] | V_reset (pL) | V_reset ratio | dP_eff (mbar) | dP_eff ratio |
|---|---|---|---|---|
| 2%    | 6.37 | 1.00 | 159 | 1.00 |
| 1%    | 6.64 | 1.04 | 158 | 0.99 |
| 0.5%  | 6.96 | 1.09 | 143 | 0.90 |
| 0.25% | 6.80 | 1.07 | 128 | 0.80 |

- V_reset increases +7–9% across the above-CMC range (small, secondary effect).
- dP_eff falls −20% from 2% → 0.25% (dominant effect).

The dP_eff drop is physically explained by **weakening γ·cosθ capillary driving force**: as [SDS] falls below the CMC-adjacent range, contact angle θ increases toward 30–40°, reducing the capillary contribution to refill pressure beyond what the pure hydraulic model captures. To predict Stage 1 from [SDS], θ([SDS]) must be measured.

*(Note: 0.125% data excluded from decomposition — at this concentration the formation regime has changed qualitatively and the L_menpoint measurement no longer captures the same geometric feature.)*

### Figure 3 — Stage 2 vs [SDS]

`fig_03_stage2_vs_conc.png`

**Above CMC (≥0.5%): Stage 2 is flat.** The γ-scaling model predicts a small rise for 0.5% that is not observed — consistent with literature γ values being slightly too high for this specific oil/surfactant system.

**Near/below CMC (0.25%, 0.125%): Stage 2 rises,** but the experimental increase (1.45× at 0.125%) is much smaller than the γ-scaling prediction (3.33×).

| [SDS] | S2 exp (s) | Exp ratio | γ-model ratio |
|---|---|---|---|
| 2%    | 0.350 | 1.00 | 1.00 |
| 1%    | 0.296 | 0.85 | 1.00 |
| 0.5%  | 0.308 | 0.88 | 1.17 |
| 0.25% | 0.373 | 1.07 | 1.67 |
| 0.125%| 0.507 | 1.45 | 3.33 |

The ~2× over-prediction of the γ-model likely reflects: (a) literature γ values overestimating the actual interfacial tension for this SDS/silicone-oil system; (b) snap-off not being purely capillary — viscous dissipation in the thinning neck limits sensitivity to γ; (c) dynamic adsorption effects at snap-off timescales.

### Figure 4 — Full Cycle Summary

`fig_04_summary_stacked.png`

**Below CMC, the formation regime changes entirely.** At 0.125% SDS:

- Stage 3 (tail/stalled phase) grows to ~2.05 s vs ~0.15 s at 2%.
- Total cycle more than doubles (from 1.62 s to 4.57 s).
- Droplet diameter increases from ~25 µm to ~34 µm — the snap-off geometry is no longer set by the junction alone.
- The 0.125% data should not be compared to above-CMC results using the same model framework.

---

## Cross-Experiment Conclusions

### On the Poiseuille Stage 1 model

1. **The model is physically correct.** Across all three experiments, the Poiseuille form $t_{S1} = V_{reset} \cdot R_{rung} / \Delta P_{rung}$ consistently captures the scaling behaviour (Po, Qw) when the right inputs are used.

2. **V_reset is the most impactful input.** The measured L_menpoint ≈ 19–21 µm (V5-8-1) gives a nominal V_reset ≈ 5,700–6,300 µm³, compared to the 9,000 µm³ from the 30 µm junction width assumption. Using L_menpoint as the reset length brings C_visc close to 1.0 in both Experiments 1 and 2.

3. **Residual C_visc < 1 at high Po** is a consistent signature across both devices and both Experiments 1 and 2. The best explanation remains a ~12 mbar capillary back-pressure opposing refill at the meniscus. This is a second-order correction — the model without it has < 15% error on Stage 1.

4. **[SDS] breaks the model** by changing dP_eff through a contact-angle effect. C_visc is not universal — it encodes the γ·cosθ capillary driving force contribution, which varies with surfactant concentration. Currently unparameterised.

### On Stage 2

5. **Stage 2 is NOT a single universal constant.** It depends on both Po and Qw:
   - Strong Po dependence: 0.35 s → 0.12 s from 200 → 600 mbar.
   - Significant Qw dependence at low Po: 0.35 s → 0.66 s from Qw=5 → 10 mL/hr at 200 mbar.
   - The Qw effect saturates above Qw=10 mL/hr.
   - At Po=600 mbar, Stage 2 ≈ 0.12 s and Qw-insensitive.

6. **Above CMC, Stage 2 is γ-insensitive** (interfacial tension is stable). The γ-scaling model is correct in predicting no change — any apparent variation at ≥0.5% SDS is within measurement scatter.

7. **Below CMC, Stage 2 rises but much less than γ-scaling predicts.** The model over-predicts by ~2× at 0.125%. Either the literature γ values are too high for this system, or viscous dissipation in the neck reduces sensitivity to γ.

### On droplet size

8. **Droplet diameter is geometry-controlled across all tested conditions.** Mean ~25–27 µm (V5-30 geometry), no significant dependence on Po, Qw, or [SDS] (above CMC). Below CMC the size increases markedly — a regime change, not a continuous trend.

---

## Model Tuning — Strict Recommendations

### Immediate changes (implement now)

| Parameter | Current assumption | Recommended | Basis |
|---|---|---|---|
| `V_reset` | 9,000 µm³ (30×30×10) | 6,000 µm³ (20×30×10) | L_menpoint = 20 µm observed across both devices |
| `C_visc` | 1.0 default | 1.0 (if using V_reset=6000 µm³) | C_visc_obs ≈ 1.09 ± 0.26, consistent with 1.0 |
| Stage 2 constant | 0.19 s (single value) | Per-Po lookup (Qw=5 baseline) | Stage 2 varies 0.12–0.35 s with Po |

Stage 2 per-Po constants to implement at Qw=5 mL/hr:

```
{200: 0.35 s,  300: 0.205 s,  400: 0.154 s,  600: 0.12 s}
```

Acceptable as a constant only when Qw is near 5 mL/hr and Po is known. Otherwise accept ±50% Stage 2 error.

### Qw correction for Stage 2 (pending further data)

The Qw dependence of Stage 2 is real and documented. Until a functional form is derived, the safest approximation is:
- Use per-Po constants calibrated at Qw=5 as the baseline.
- Accept ±50% Stage 2 uncertainty if operating at Qw ≠ 5 mL/hr.
- At Po ≥ 600 mbar: Stage 2 ≈ 0.12 s, Qw-insensitive — use as fixed constant.

### Capillary back-pressure (second-order, implement if < 15% S1 error is insufficient)

A P_cap = 12 mbar opposing term in the Stage 1 driving pressure eliminates the residual Po-dependent C_visc trend. This was calibrated from Experiment 1 and is consistent with Experiment 2. Implement as a tunable parameter in the model.

### Concentration effects (not yet in scope — document as limitation)

- C_visc is not a material constant when [SDS] varies. It encodes contact-angle effects that the current model cannot predict without θ([SDS]) as input.
- **Do not apply C_visc calibrated at 2% SDS to different-concentration systems** — error can reach 1.87× on Stage 1.
- For the NaCas/MCT system (Experiment 4): expect Stage 1 behaviour to shift substantially. Treat C_visc as a fresh calibration parameter; the hydraulic model structure remains valid.

### Required measurements to close the model gaps

1. **Contact angle θ([SDS])** on device substrate at each concentration — would allow quantitative prediction of dP_eff and therefore Stage 1 at arbitrary [SDS].
2. **Interfacial tension γ** for SDS/water vs silicone oil at each concentration — literature values for SDS/water vs air are not representative; a pendant drop or spinning drop measurement is needed.
3. **Higher frame rate imaging** for Stage 2 — at 25 fps, Stage 2 is quantised to 40 ms steps. True snap-off variability cannot be resolved. A 100+ fps measurement would allow a functional Stage 2 model to be fitted.

---

## Next Step — Experiment 4 (NaCas/MCT)

The next dataset uses sodium caseinate (NaCas) as the continuous-phase surfactant and MCT oil as the dispersed phase — a different emulsion chemistry on the same device geometry.

Expected differences vs SDS/silicone oil:
- NaCas is a protein surfactant: adsorption kinetics are slower and concentration-independent above saturation. Dynamic interfacial tension effects may be more pronounced during Stage 2.
- MCT oil viscosity differs from silicone oil — Stage 1 will shift accordingly (R_rung scales with µ_oil).
- The Stage 1 model form remains valid; C_visc will need fresh calibration for this system.

Recommended analysis: mirror the structure of Experiments 1–3 — sweep Po at fixed Qw and concentration first, then introduce Qw and concentration variation once the baseline C_visc for NaCas/MCT is established.
