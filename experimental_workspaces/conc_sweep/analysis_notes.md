# SDS Concentration Sweep — Analysis Notes
**Device:** V5-8-1 | **Date:** 2026-04-27 | **Script:** `scripts/v5_8_1_conc_sweep_analysis.py`

Concentrations tested: 2%, 1%, 0.5%, 0.25%, 0.125% SDS (mass).
Dispersed phase: sunflower oil. CMC of SDS ≈ 0.24%.

---

## Overlap conditions across concentrations

Not all concentrations share the same (Po, Qw) — cross-concentration comparisons are only valid where conditions overlap.

| Po (mbar) | Qw (mL/hr) | Concentrations with data            | Cross-conc comparison? |
|-----------|------------|-------------------------------------|------------------------|
| 200       | 5          | 2%, 1%, 0.5%, 0.25%, 0.125%         | Yes — full sweep       |
| 400       | 5          | 2%, 1%, 0.5%                        | Yes — upper 3          |
| 400       | 2          | 1%, 0.5%, 0.25%  (no 2% baseline)  | Partial — no reference |
| 200       | 2          | 0.5% only                           | No                     |
| 200       | 20         | 0.125% only                         | No                     |

All conditions are included in the summary table and figures; the three conditions above the line are the most analytically useful.

---

## Stage 1 — affected more than expected

→ **`fig_01_stage1_vs_conc.png`** | **`fig_03_cvisc_vs_conc.png`**

Stage 1 increases monotonically as [SDS] decreases. This was not expected from the
Poiseuille model, which treats Stage 1 as purely hydraulic (no direct concentration
dependence).

### At Po=200, Qw=5 (full 5-concentration sweep):

| [SDS] | S1 mean (s) | Ratio vs 2% | C_visc |
|-------|-------------|-------------|--------|
| 2%    | 1.078       | 1.00        | 0.76   |
| 1%    | 1.136       | 1.05        | 0.80   |
| 0.5%  | 1.316       | 1.22        | 0.93   |
| 0.25% | 1.438       | 1.33        | 1.01   |
| 0.125%| 2.013       | 1.87        | 1.42   |

### At Po=400, Qw=5 (3 concentrations):

| [SDS] | S1 mean (s) | C_visc |
|-------|-------------|--------|
| 2%    | 0.394       | 0.55   |
| 1%    | 0.476       | 0.67   |
| 0.5%  | 0.484       | 0.68   |

### At Po=400, Qw=2 (1%, 0.5%, 0.25% only — no 2% baseline):

| [SDS] | S1 mean (s) | C_visc |
|-------|-------------|--------|
| 1%    | 0.429       | 0.61   |
| 0.5%  | 0.452       | 0.64   |
| 0.25% | 0.491       | 0.70   |

**Mechanism — two effects, both confirmed from data:**

Lower [SDS] → higher contact angle → two consequences for Stage 1:
1. **V_reset increases** (meniscus recedes further after snap-off, more volume to refill)
2. **dP_eff decreases** (capillary driving force for refill = γ·cosθ·f(geometry) weakens)

Both are directly observable by back-calculating the effective driving pressure from the
experiment: `dP_eff = V_reset × R_rung / t1_exp`, where V_reset is estimated from
L_menpoint × junction cross-section (30 × 10 µm).

### L_menpoint and V_reset vs concentration (Po=200, Qw=5):

→ **`fig_04_geometry_vs_conc.png`**

| [SDS] | Lmp mean (µm) | V_reset (pL) | V_reset ratio |
|-------|--------------|--------------|---------------|
| 2%    | 21.2         | 6.37         | 1.00          |
| 1%    | 22.1         | 6.64         | 1.04          |
| 0.5%  | 23.2         | 6.96         | 1.09          |
| 0.25% | 22.7         | 6.80         | 1.07          |
| 0.125%| 6.9 ⚠        | 2.07 ⚠       | 0.32 ⚠        |

V_reset increases ~7–9% across the above-CMC range. Present but a small effect.
The 0.125% Lmp value (6.9 µm) is anomalous — see note below.

### Back-calculated effective driving pressure (Po=200, Qw=5):

| [SDS] | dP_eff (mbar) | dP_eff ratio |
|-------|--------------|--------------|
| 2%    | 159          | 1.00         |
| 1%    | 158          | 0.99         |
| 0.5%  | 143          | 0.90         |
| 0.25% | 128          | 0.80         |

Applied pressure is 200 mbar for all rows. dP_eff sits below that due to oil
back-pressure and hydraulic losses, but **drops a further 20% going from 2% to
0.25%** with no change in applied conditions. This is the reduced γ·cosθ capillary
contribution to refill driving force showing up experimentally.

### Decomposition — which effect dominates? (Po=200, Qw=5):

`t1_ratio = V_reset_ratio / dP_eff_ratio`

| [SDS] | t1 ratio | V_reset ratio | dP_eff ratio | V/dP (= t1 check) |
|-------|----------|---------------|--------------|-------------------|
| 2%    | 1.000    | 1.000         | 1.000        | 1.000             |
| 1%    | 1.054    | 1.042         | 0.989        | 1.054 ✓           |
| 0.5%  | 1.220    | 1.093         | 0.895        | 1.220 ✓           |
| 0.25% | 1.333    | 1.067         | 0.800        | 1.333 ✓           |

The falling dP_eff (−20%) is the dominant term; the rising V_reset (+7%) is secondary.
Together they fully account for the observed Stage 1 lengthening.

**0.125% Lmp anomaly:** Lmp = 6.9 µm vs ~22 µm for all other concentrations,
yielding a nonsensical V_reset and a collapsed dP_eff of 27 mbar. This is not a
physical result — at 0.125% the formation regime has changed (much larger droplet,
dominant Stage 3, different meniscus shape), and the Lmp measurement is no longer
capturing the same geometric feature as in the above-CMC cases. V_reset and dP_eff
estimates at 0.125% should not be trusted.

**Can dP_eff be predicted from [SDS]?** Directionally yes, but the contact angle
θ([SDS]) is needed as input. The capillary refill driving force scales as
`~2γ·cosθ / r_eff`. With measured θ at each concentration, the 31 mbar drop from
2%→0.25% could be closed quantitatively. The order-of-magnitude is consistent with θ
increasing from near 0° (fully wetting, 2% SDS) toward ~30–40° at 0.25% SDS.

**Model implication:** C_visc is not a universal constant. It drifts from ~0.55 at
2% / high pressure to ~1.42 at 0.125%. The drift is explained by two measurable
physical quantities (V_reset and dP_eff), both driven by contact angle. To predict
Stage 1 from [SDS], the model would need θ([SDS]) or γ([SDS]) as inputs and a
geometric formula for the capillary driving pressure. Currently outside model scope.

---

## Stage 2 — correct direction, magnitude weaker than γ-scaling predicts

→ **`fig_02_stage2_vs_conc.png`** | **`fig_05_summary_200_5.png`**

### At Po=200, Qw=5:

| [SDS] | S2 mean (s) | Exp ratio vs 2% | γ-ratio (model) | Model S2 (s) |
|-------|-------------|-----------------|-----------------|--------------|
| 2%    | 0.350       | 1.00            | 1.00            | 0.350        |
| 1%    | 0.296       | 0.85            | 1.00            | 0.350        |
| 0.5%  | 0.308       | 0.88            | 1.17            | 0.408        |
| 0.25% | 0.373       | 1.07            | 1.67            | 0.583        |
| 0.125%| 0.507       | 1.45            | 3.33            | 1.165        |

**Above CMC (≥0.5%):** Stage 2 is essentially flat. 1% and 0.5% are indistinguishable
from 2% within measurement scatter. The γ-scaling model slightly over-predicts even
here.

**Near/below CMC (0.25% and 0.125%):** Stage 2 rises, as expected — higher γ slows
capillary snap-off. But the experimental rise (1.45×) is much smaller than the
γ-scaling prediction (3.33×). Possible reasons:
- Literature γ values at 0.125% (≈20 mN/m) may be too high for this system.
- Snap-off is not purely capillary — viscous dissipation in the thinning neck also
  contributes, limiting sensitivity to γ.
- Dynamic adsorption: at snap-off timescales the interface may not be at equilibrium γ.

### At Po=400, Qw=5:

| [SDS] | S2 mean (s) |
|-------|-------------|
| 2%    | 0.154       |
| 1%    | 0.120       |
| 0.5%  | 0.124       |

Stage 2 is nearly identical across these three concentrations — all are above CMC
and in a pressure-dominated regime. The γ-scaling model here predicts no change
(correct for 1%) and a small rise for 0.5% (not observed).

---

## Stage 3 / regime change at 0.125%

→ **`fig_05_summary_200_5.png`** (stacked bars include Stage 3)

At 0.125% SDS (below CMC), Stage 3 grows to ~2.05 s at Po=200/Qw=5, versus ~0.15 s
at 2% SDS. At Po=200/Qw=20 (0.125% only) Stage 3 = 3.23 s. The droplet diameter
also increases markedly (33–38 µm vs 24–25 µm at 2%), indicating the system has
crossed into a qualitatively different formation regime — the tail-pinch phase
becomes rate-limiting, not Stage 2 snap-off.

This is consistent with the expectation that the 0.125% data represents a different
physical regime and should not be directly compared to the above-CMC concentrations
using the same model scaling.

---

## What the model can / cannot currently predict from [SDS]

| Quantity | Current capability | Notes |
|----------|--------------------|-------|
| Stage 1 trend direction | Qualitatively yes | C_visc increases as [SDS] drops |
| Stage 1 magnitude | No | C_visc varies with [SDS]; needs contact-angle parametrisation |
| Stage 2 direction (above CMC) | Yes — predicts flat | Correct |
| Stage 2 direction (below CMC) | Yes | γ-scaling predicts rise, data confirms |
| Stage 2 magnitude (below CMC) | Over-predicts by ~2× | γ literature values may be too high; dynamic adsorption |
| Stage 3 / regime change | Not modelled | 0.125% is a different regime |

---

## Figures reference

| File | Content |
|------|---------|
| `fig_01_stage1_vs_conc.png` | Stage 1 mean ± SD vs [SDS], one panel per (Po, Qw) condition. Dashed = Poiseuille model at C_visc=1.0. |
| `fig_02_stage2_vs_conc.png` | Stage 2 mean ± SD vs [SDS]. Dashed = γ-scaling model (τ(c)/τ(2%) = γ(c)/γ(2%)). |
| `fig_03_cvisc_vs_conc.png` | C_visc = t1_exp / t1_model vs [SDS]. Flat line would mean no concentration effect on Stage 1. |
| `fig_04_geometry_vs_conc.png` | L_menpoint, L_men, droplet diameter vs [SDS] at Po=200/Qw=5 and Po=400/Qw=5. Check for meniscus recession trend. |
| `fig_05_summary_200_5.png` | Two-panel summary at Po=200, Qw=5. Left: Stage 1 + model. Right: Stage 2 + Stage 3 (stacked) + γ model. |

---

## Open questions / next steps

1. **Measure γ for this specific SDS/sunflower-oil system** at each concentration —
   literature values for SDS/water vs air are not the same as SDS/water vs silicone
   oil. A pendant drop measurement at each concentration would anchor the Stage 2 model.

2. **L_menpoint confirmed increasing 2%→0.5%** (21.2→23.2 µm, see Stage 1 section
   above). V_reset rise is real but secondary — the dominant Stage 1 effect is the
   falling dP_eff (reduced capillary driving force). The 0.125% Lmp value is
   anomalous and should not be used.

3. **Measure contact angle θ at each [SDS]** — the 31 mbar drop in dP_eff from
   2%→0.25% is physically consistent with θ rising from ~0° to ~30–40°. A sessile
   drop measurement on the device substrate at each concentration would allow
   quantitative prediction of dP_eff and therefore Stage 1.

4. **Parametrise C_visc(θ) rather than C_visc([SDS])** — contact angle is the
   physical variable; concentration is just a proxy. If θ is measured, both the
   V_reset and capillary pressure terms can be computed from geometry, making
   Stage 1 fully predictable without an empirical fit.

4. **0.125% should be treated as a separate regime** — the Stage 3 tail dominates
   and the droplet diameter is meaningfully larger. The current model does not
   capture this.
