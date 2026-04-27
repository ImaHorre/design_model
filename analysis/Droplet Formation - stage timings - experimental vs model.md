
 **A focus was made to analyse the time taken for different parts of the droplet formation event to take place. This was then compared against a predictive model to evaluate stage timings and droplet production rates at the same tested experimental conditions**

---

[[Droplet generation - stage overview]] highlights some of the immediate thoughts on 'stages' of the droplet formation. 

[[droplet stage timings - dataset]] holds the data of these tests + continued analysis of other devices and/or flow conditions/emulsion setups etc. in this manner. 

--- 
#### Background 

 Oil enters through a network of parallel rungs, each rung connecting to a junction/step where it meets the continuous water phase. Droplet formation proceeds in two identifiable stages after completion of a  droplet formation event:
- Stage 1 (flow), in which the oil meniscus, after just resetting to a position (L) back from the junction edge begins to advance again to the junction exit. 
- Stage 2 (snap-off), in which a neck (or thinning thread) if oil pinches off to release the droplet.

Looking at analysis of different inlet pressures (200, 300, 400, 500 mbar) at a fixed water flow rate of 5 mL/hr. For each observation we measured the time of Stage 1, Stage 2 as well as droplet diameter and the meniscus reset length. From the device geometry and hydraulic network model the local rung pressure drop at each DFU position was evaluated.

1) Does a simple Poiseuille rung-flow model correctly predict Stage 1 timing?
2) How does the assumed reset volume affect model accuracy? 
3) Can Stage 2 snap-off be modelled in detail, or should it be locked to a constant? 
4) Is there spatial variation in reset length across the device?

---
#### What dominates the droplet cycle?

Stage 1 (oil rung filling) is the dominant contributor to total cycle time at all tested pressures. It accelerates strongly with Po because the driving pressure for rung flow scales directly with the inlet pressure. Stage 2 (snap-off) is shorter and shows some minimal Po dependence, it is controlled primarily by other factors, possibly associated with fluid/emulsion system properties (viscosty? interfacial tension? contact angle?).

![[fig_01_cycle_overview.png]]

At 200 mbar, Stage 1 accounts for 86% of the total cycle (1.51 s mean). By 500 mbar it has accelerated 2.9× to 0.52 s (76% of cycle). 

Stage 2 changes from an average 0.25 s at 200 mbar to 0.16 s at 500 mbar, a 1.6× speedup. But its fraction of the cycle grows from 14% to 24% because Stage 1 is shrinking faster. 

---
#### Stage 1: does the Poiseuille model work?

The stage 1 part of the model is evaluating 

$$t_{S1} = \frac{V_{reset}  R_{DFU}}
{\Delta P_{DFU}}$$

![[fig_02b_stage1_scaling_loglog.png]]

The observed experimental power-law exponent is -1.17, compared to the ideal Poiseuille flow of -1.

The slightly steeper than ideal slope (-1.17 vs -1) is consistent perhaps with a small capillary back-pressure at the meniscus (~12 mbar, see [[#4. Calibrating the Stage 1 model C_visc]]) that is proportionally larger at low Po. 

Downstream DFUs are consistently showing shorter Stage 1 times than upstream DFUs at the same Po. Here, experimentally we can see that V_reset is slightly smaller (also droplet size is smaller) and in theory the $\Delta P_{DFU}$ should be the same at all positions as we have designed such that the $R_{DFU} / R_{MC-cont}$  is at a maximum, within fabrication limits. However, it could be that there is some lower $\Delta P_{DFU}$ at these locations. 

The model baseline (using the network mean DP) and C_visc correction factor, has exponent -1.03 and sits within the scatter of observations, indicating that the Poiseuille type flow is physically correct.

---

## 3. Does meniscus reset length vary?

At each snap-off event, oil retracts into the DFU by a distance $L_{men}$.

The default model assumption is that this retraction corresponds to a fixed reset volume, taking: $$L_{men} = DFU_{w}\quad\text{and}\quad V_{reset} = DFU_{w}² × DFU_{h} = 9000 µm³\quad \text{(for a V5-30 device)}$$ 
Does $L_{men}$ vary with Po or DFU position?

![[fig_03_meniscus_reset.png]]

For upstream DFUs (DFU ≤ 6), $L_{men}$ is close to the nominal 30 µm and shows only a mild negative trend with Po (β ≈ −0.15 µm per 10 mbar). 

Downstream positions (DFU ≥ 8) have measurably shorter reset lengths, approximately 20-25 µm. This means the downstream DFUs have smaller reset volumes, resulting in faster production cycles vs the uniform-Vol model prediction. An important caveat: the framerate of the camera might at higher Po obscure the true maximum reset length - but over the number of measurements made no frames were caught in a max position that matches the upstream DFUs. 

##### Meniscus length and ties to droplet size/ Is the droplet volume related to $V_{reset}$

Droplet volume > $V_{reset}$

So cannot be linked to say that $V_{drop}$ is = $V_{reset}$. However, there is a length that the neck reaches to at its maximum, where it might be that the neck forms at its critical width 1/2 of this length. Where, all volume downstream after this critical length go towards the droplet upon snap-off and the other half goes back to forming the meniscus. Giving the ability to describe both final $V_{drop}$ and $L_{men}$. The issue is just like with modelling for determining $L_{men}$ we don't inherently know the max pinch off length. 
![[Droplet Formation - meniscus reset and droplet diameter.png|351]]

---

## 4. Calibrating the Stage 1 model: C_visc

$C_{visc}$ is defined as the ratio of observed Stage 1 time to the model prediction: $$C_{visc} = \frac{t_{obs}}{t_{pred}}$$ 
If the Poiseuille model were perfect and $V_{reset}$ were known exactly, $C_{visc}$ would equal 1.0 everywhere. In practice, $C_{visc}$ absorbs any systematic errors in $V_{reset}$ or in the hydraulic driving pressure.

Three analyses are compared:
- **Baseline**: fixed $V_{reset}$ = 9000 µm. 
- A: measured $V_{reset}$ per observation (from $L_{men}$ analysis)
- B: measured $V_{reset}$ + capillary back-pressure correction of 12 mbar. [[#What is P_cap?]] ]

The baseline shows a systematic drift: 
- $C_{visc}$ is ~1.02 at 200 mbar and ~0.89 at 500 mbar (δ = -0.044 per 100 mbar). 
- Using measured/observed $V_{reset}$ (A) we can roughly half this trend (δ = -0.015), confirming that V_reset variation is a real contributor. 
- Adding a fitted capillary back-pressure of $P_{cap} = 12 mbar$ (B) eliminates the residual trend entirely (δ ≈ +0.001), indicating that $C_{visc}$≈ 1.0 when both effects are accounted for. The Poiseuille model is physically correct; the remaining scatter reflects genuine within-DFU variability in reset volume (CoV ~20%).

##### What is P_cap?
$P_{cap} = 12 mbar$ is a fitted regression correction, not a measurement.
 It represents the average additional pressure opposing oil flow beyond what the straight Poiseuille model predicts. The model works well without it (±8% error); with it, C_visc is flat across all Po.

---

## 5. Device-level droplet rate: does the reset variation matter?

The device produces droplets at all rungs simultaneously. The overall droplet production rate (Hz) is the average across all DFU positions. If downstream rungs have shorter reset volumes than the fixed-V model assumes, they will generate faster individual cycles and the device average Hz will differ from the model prediction.

![[fig_05_device_hz.png]]

The fixed-V model error reaches **14.7%** across the tested Po range. The largest error occurs at 500 mbar (-14.7%), where the downstream reset shortening is most pronounced. Using measured V_reset reduces the maximum error to **15.0%**. For applications where Hz prediction accuracy better than ~5% is needed, using position-dependent reset volumes (or measured L_menpoint data) is recommended. For early design screening at fixed Po, the fixed-V model is adequate.

---

## 6. Stage 2: snap-off timing

Stage 2 begins when the oil neck at the junction exit starts to thin under the squeezing action of the water flow and the capillary instability of the interface. It ends when the neck pinches off and the droplet detaches. At 25 fps, all measured snap-off times are exact multiples of 40 ms — the spread in measured values reflects measurement quantisation, not true physical variability.

![[fig_06_stage2_analysis.png]]

A power-law fit to Stage 2 mean times gives exponent **-0.51**, compared to -1.17 for Stage 1. The 1.6× speedup from 200 to 500 mbar is statistically detectable but physically minor — snap-off is primarily controlled by capillary forces (geometry and interfacial tension) rather than oil pressure. At 25 fps the snap-off time appears at just 7 discrete levels between 0.08 s and 0.32 s. No meaningful statistics on true snap-off variability can be extracted at this frame rate.

**Verdict:** Lock Stage 2 to its global mean of **0.19 s** for current fluid conditions (Po = 200–500 mbar, Qw = 5 mL/hr, same surfactant). This introduces at most 32.6% error in Stage 2 time at any single Po, corresponding to < 5% error on total cycle time.

---

## 7. Droplet size and summary

![[fig_07_droplet_size_summary.png]]

Droplet diameter is 27 µm mean (23–30 µm range) and shows no strong Po dependence — confirming it is set by the device geometry (junction width and critical radius for snap-off) rather than the driving pressure. The weak decreasing trend with Po is consistent with a small capillary-number effect at the snap-off neck.

---

## Conclusions and next steps

### What the model gets right

- The Poiseuille rung-flow model (t = V·R/DP) correctly captures Stage 1 physics. The power-law scaling exponent (−1.17) is close to the ideal −1.0 and holds across all pressures and DFU positions.
- C_visc ≈ 0.95 globally with no systematic trend once V_reset variation and a small capillary correction are accounted for.
- Droplet diameter (~27 µm) is geometry-controlled and consistent with the R_critical snap-off model.
- Stage 2 (~0.19 s) can be treated as a constant for current conditions, introducing < 5% cycle-time error.

### Where the model currently has uncertainty

- **V_reset**: the rule-of-thumb (9000 µm³) overestimates downstream DFU reset volumes by ~20–30%, introducing up to 15% error in per-rung Hz prediction. Within-DFU CoV is ~20% and cannot be reduced further without higher-speed imaging.
- **P_cap**: the 12 mbar capillary back-pressure is a fitted number. Its physical origin (meniscus curvature, entry/exit losses, surfactant) is not resolved and would require direct measurement of interfacial tension or high-speed meniscus imaging.
- **Stage 2 variability**: the true distribution of snap-off times is unresolvable at 25 fps. At low Po (200 mbar) Stage 2 contributes 14% of the cycle, so even moderate true variability (±50%) would contribute only ±7% to Hz spread — acceptable for design.

### Recommended next experiments

1. **Vary Qw at fixed Po (same V5-30 device)** — highest priority. Decouples water back-pressure from oil driving pressure, directly tests whether Stage 2 is Qw-sensitive, and provides the cleanest test of the Poiseuille model.
2. **Vary SDS concentration at fixed Po/Qw** — tests whether Stage 2 timing is interfacial-tension-sensitive (capillary-controlled) or geometry-dominated. No new equipment required.
3. **Test W11 device for C_visc universality** — validates whether C_visc ≈ 1.0 is geometry-independent or device-specific.


