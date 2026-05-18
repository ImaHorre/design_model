# Hydraulic Model Discrepancy Investigation

## Status
`compare_models.py` confirmed: **D_pred ≈ D_exp** (~12 µm both predicted and measured from CSV annotations). The 5.6× discrepancy in droplet frequency is **entirely hydraulic** — Q_rung is overestimated 5.6×.

**Experimental baseline** (W11 chip, DFU1, ROI4):
- Po = 400 mbar, Qw = 1.5 mL/hr
- f_exp ≈ 2.6 Hz, D_exp ≈ 12 µm
- f_pred ≈ 14.6 Hz → ratio = 5.6×

**Current rung resistance formula:**
```
R_Omc = 12 * mu_oil * (mcl * constriction_ratio) / (mcw * mcd^3) / (1 - 0.63*mcd/mcw)
      = 2.46e18 Pa·s/m³
```
Parameters: mcd=5µm, mcw=8µm, mcl=4000µm, constriction_ratio=0.9, mu_oil=34.52 mPa·s

---

## Physical Hypotheses

### 1. Rung depth (mcd) shallower than designed — PRIMARY SUSPECT
R ∝ mcd⁻³ (cube law). Depth is the most sensitive and hardest-to-control fabrication variable.

| Actual mcd | R multiplier | Notes |
|---|---|---|
| 5.0 µm (designed) | 1.0× | baseline |
| 4.0 µm | 1.95× | partial |
| 3.0 µm | 4.63× | most of it |
| **2.8 µm** | **5.7×** | ~exact match |

A 2.2 µm underetch would fully explain the discrepancy. Profilometer or SEM cross-section of the W11 rung would confirm or refute this.

### 2. External pressure loss in fluidic circuit
If tubing + connectors + on-chip manifold drop pressure before the oil main channel:

```
Q_rung ∝ (Po_chip - dP_cap) / R_Omc

For 5.6× reduction: Po_chip ≈ 112 mbar  →  288 mbar lost externally
```

**Key distinguishing test**: if the device still runs at Po=200 mbar, external loss is ruled out as the sole cause (200 - 288 < 0 would shut off oil).

### 3. Junction / entrance resistance not modelled
The model only accounts for the Poiseuille resistance along `mcl * constriction_ratio`. The abrupt transition from the 2000µm-wide main channel into the 8µm-wide rung, and the step junction at exit, add entrance/exit losses not captured by the current formula.

### 4. Capillary pressure underestimated
Note: `gamma = 0.0` in `configs/w11.yaml` — the capillary threshold (50 mbar) is a hardcoded guess, not derived from physics. Young-Laplace for exit geometry (w=15µm, h=5µm):

```
dP_cap = 2γ × (1/15µm + 1/5µm) = 2γ × 2.67e5 m⁻¹

At γ = 5 mN/m:  dP_cap = 27 mbar
At γ = 15 mN/m: dP_cap = 80 mbar
At γ = 30 mN/m: dP_cap = 160 mbar
```

For 5.6× reduction from capillary alone, dP_cap would need to be ~337 mbar — unrealistically high. Not the primary cause, but could contribute if γ is large.

---

## Diagnostic Tool: `sensitivity_analysis.py`

Given one experimental point, computes the value of each model parameter that would reconcile Q_rung_pred = Q_rung_exp. Outputs a ranked table.

**Usage:**
```bash
python sensitivity_analysis.py --config configs/w11.yaml \
    --Po_mbar 400 --Qw_mlhr 1.5 --f_exp_hz 2.6 --D_exp_um 12.0
```

**Expected output:**
```
=== PARAMETER SENSITIVITY ===

  Q_rung_pred = 1.32e-14 m^3/s
  Q_rung_exp  = 2.36e-15 m^3/s  (= f_exp * V_d_exp)
  R_scale needed = 5.60x  (R_eff = 1.38e19 Pa.s/m^3)

  Parameter           Model value    Required value    Notes
  ────────────────────────────────────────────────────────────
  mcd [um]            5.00           2.82              R ∝ mcd^-3
  mcw [um]            8.00           1.43              R ∝ mcw^-1
  mcl [um]            4000           22400             R ∝ mcl
  constriction_ratio  0.90           >1.0              n/a
  mu_oil [mPa.s]      34.52          193.3             R ∝ mu
  Po_eff [mbar]       400            112               Q ∝ (Po - dP_cap)
  dP_cap [mbar]       50.0           337.5             Q ∝ (Po - dP_cap)
```

---

## Empirical Validation Strategy

**1. Vary Po at fixed Qw** (e.g., Po = 200, 300, 400, 500 mbar)
- If f ∝ (Po − Po_offset) linearly → external pressure loss (fit Po_offset)
- If f scales differently → geometry/resistance issue

**2. Compare DFU 1–7 on the same chip**
- All DFUs same f at same (Po, Qw) → systematic model error
- DFUs vary → rung-to-rung fabrication variation

**3. Test on a different chip design**
- Same R_scale across chips → systematic formula failure (not fabrication)
- Chip-specific → fabrication variation or geometry mismatch in YAML

---

## LLM Prompts for Physics Consultation

### Prompt A — Hydraulic resistance mechanisms
```
I'm modelling a step-emulsification microfluidic device. Geometry: parallel
microchannels (rungs) h=5µm deep, w=8µm wide, L=4mm long connect an oil main
channel (200µm deep, 2000µm wide) to a water main channel (same dimensions).
Oil viscosity 34.5 mPa·s, water 0.89 mPa·s. Applied oil inlet pressure 400 mbar,
water inlet flow 1.5 mL/hr, 25000 rungs.

I calculate rung resistance using Hagen-Poiseuille for a rectangular channel:
  R = 12μL / (wh³) × 1/(1 − 0.63h/w) = 2.46e18 Pa·s/m³

My model predicts f ≈ 14.6 Hz per rung. Experiment gives f ≈ 2.6 Hz. Droplet
diameter is correctly predicted (D ≈ 12 µm both ways), so the discrepancy is
entirely in the oil flow rate per rung — the model predicts 5.6× too high.

What physical mechanisms in a step-emulsification rung could cause the effective
hydraulic resistance to be 5.6× higher than the Hagen-Poiseuille formula?
Consider specifically:
1. Sensitivity of R to depth h (cube law — actual depth 2.8 µm vs designed 5 µm
   would fully explain it; is this realistic for soft-lithography at this scale?)
2. Entrance/exit pressure losses at the rung-to-main-channel junction
3. Two-phase flow corrections when oil slugs displace water at the junction
4. Dynamic capillary effects during droplet pinch-off that impede steady flow
5. Any other mechanism specific to step-emulsification physics

Please be quantitative where possible and cite literature if relevant.
```

### Prompt B — Distinguishing external pressure loss from resistance error
```
In a microfluidic experiment, pressure is applied via a pressure controller to an
oil inlet. Tubing → on-chip manifold → oil main channel → 25000 parallel rungs
(h=5µm, w=8µm, L=4mm, mu=34.5 mPa·s) → water main channel → outlet.

I apply 400 mbar and observe droplet frequency 5.6× below model prediction. Both
hypotheses — (A) external pressure drop in tubing/connectors, and (B) rung
resistance 5.6× higher than the Poiseuille model — produce the same frequency
error at a single operating point.

1. What experiment would definitively distinguish A from B?
2. For hypothesis A: how much external pressure would be lost in typical
   microfluidic tubing (1/32" ID PTFE, 10-50 cm) at ~0.1-1 mL/hr oil flow?
   Is 288 mbar of external loss physically plausible?
3. For hypothesis B: what is the most likely cause of 5.6× resistance error —
   geometry mismatch, entrance effects, two-phase flow, or something else?
```

### Prompt C — Literature on step-emulsification arrays
```
In passive step-emulsification microfluidic arrays with a ladder-network topology
(N parallel rungs connecting two distributed-pressure main channels), I find that
a Hagen-Poiseuille hydraulic model overpredicts droplet frequency by 5-6×. Droplet
size is correctly predicted by a power-law model D = k·w^a·h^b.

Questions:
1. Are there published validation studies comparing H-P model predictions to
   measured droplet frequencies in step-emulsification arrays? What accuracy do
   they achieve?
2. What corrections to the H-P model have been proposed for these geometries?
3. Is the assumption — that oil flows as a pure Newtonian fluid through the rung —
   justified during active droplet production, or does the droplet pinch-off cycle
   create a pulsatile resistance that changes time-averaged Q?
4. Do you know of any studies on W1/O step emulsification with high-aspect-ratio
   (very long, narrow) rungs similar to h=5µm, w=8µm, L=4mm?

Relevant prior work I'm aware of: Vladisavljević et al. (step emulsification
arrays), Kobayashi et al. (SPG membrane). What else is relevant?
```

---

## Recommended Next Steps (in order)

1. **Build `sensitivity_analysis.py`** — get the quantitative table immediately
2. **Check rung depth physically** — profilometer measurement on W11 chip is the fastest path to ground truth; depth error is the most likely and most testable hypothesis
3. **Run Po sweep experiment** (200–500 mbar, fixed Qw) — distinguishes external loss from resistance error by checking linearity vs. threshold
4. **Use LLM Prompt A** to get physics-based input on what else could cause 5.6× before committing to a model change
5. **Update `rung_resistance()` with confirmed correction** — whether that's a different `mcd`, an added entrance resistance term, or a calibrated `R_scale` factor
