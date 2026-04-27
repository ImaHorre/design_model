# V5-8-1 — Qw Sweep Analysis Report
**Device:** V5-8-1 (V5-30 geometry, 30 µm junction)  
**Fluids:** 2% SDS continuous (water), silicone oil dispersed  
**Date analysed:** 2026-04-27  
**Script:** `scripts/v5_8_1_qw_sweep_analysis.py`  
**Output figures:** `results/v5_8_1_qw_sweep/fig_01–06.png`

---

## Conditions tested

| Po (mbar) | Qw = 5 mL/hr | Qw = 10 mL/hr | Qw = 20 mL/hr |
|-----------|:---:|:---:|:---:|
| 200 | ✓ (n=23) | ✓ (n=15) | — |
| 300 | ✓ (n=16) | ✓ (n=12) | ✓ (n=11) |
| 400 | ✓ (n=13) | ✓ (n=14) | — |
| 600 | ✓ (n=14) | ✓ (n=15) | ✓ (n=10) |

143 observations total after NaCas exclusion.

---

## Stage 1 (oil refill)

**Qw strongly affects Stage 1** — both stages increase with Qw at every fixed Po.

- At Po = 300 mbar: S1 = 0.60 s (Qw=5) → 0.70 s (Qw=10) → 1.14 s (Qw=20)
- Mechanism: higher Qw raises water back-pressure, reducing DP_rung, slowing oil refill.
- The Poiseuille model captures the Qw trend shape correctly via hydraulic solve.
- **Global C_visc = 0.74 ± 0.20** using default V_reset = 9000 µm³.
- Measured L_menpoint ≈ 19–21 µm (not 30 µm). Using V_reset = 20×30×10 = 6000 µm³ gives C_visc ≈ 1.11 — close to 1.0. The offset is largely a V_reset calibration issue.
- Residual C_visc decline with Po (0.76→0.52 for Qw=5) matches the capillary back-pressure signature seen in the previous device; a P_cap ≈ 12 mbar correction would flatten it.

## Stage 2 (snap-off)

**Stage 2 is NOT Qw-independent.** It increases with Qw, particularly at lower Po.

| Qw | Stage 2 mean (all Po) |
|----|:---:|
| 5 mL/hr | **0.207 s** |
| 10 mL/hr | **0.315 s** |
| 20 mL/hr | **0.313 s** |

| Po | Stage 2 mean (all Qw) |
|----|:---:|
| 200 mbar | 0.507 s |
| 300 mbar | 0.318 s |
| 400 mbar | 0.190 s |
| 600 mbar | **0.123 s** ← Qw-insensitive here |

- Qw effect saturates: 10 → 20 mL/hr produces little additional increase.
- Large SDs at 200/10 and 300/20 are driven by a small number of anomalously slow snap-off events at specific DFU positions under high Qw.
- At 600 mbar Stage 2 ≈ 0.12 s regardless of Qw; can be locked there.

**Implication for model:** A single global constant (0.272 s) introduces >50% error when Qw varies. Best approximation: per-Po constant {200: 0.51, 300: 0.32, 400: 0.19, 600: 0.12 s} at Qw=5 mL/hr; accept ±50% if Qw departs from 5 mL/hr.

## Meniscus geometry and droplet size

- **L_menpoint ≈ 19–21 µm** — flat across Po and Qw. This is the effective V_reset input.
- **L_men ≈ 28–35 µm**, mild decline with Po. No Qw dependence.
- **Droplet diameter ≈ 24.2–25.6 µm** — geometry-controlled, essentially constant. Consistent with previous analysis (geometry sets droplet size, not operating conditions).

## Generation frequency

- Frequency increases with Po (Stage 1 dominated) and decreases with Qw.
- At 200 mbar: 0.62 Hz (Qw=5) → 0.46 Hz (Qw=10) — 26% reduction.
- At 600 mbar the Qw effect is minor (~11% range).

## Model recommendations

1. **Stage 1:** Poiseuille model is physically correct. Use V_reset = 6000 µm³ (from L_menpoint = 20 µm) with C_visc = 1.0, or V_reset = 9000 µm³ with C_visc = 0.74.
2. **Stage 2 at Qw = 5 mL/hr:** lock to **0.207 s** (consistent with previous device's 0.19 s).
3. **Stage 2 with varying Qw:** do not use a single constant; Qw adds ~50% variability. A per-Po lookup is the safest simple approximation.
4. **Follow-up:** per-DFU analysis to determine whether the elevated Stage 2 at high Qw / low Po is localised to specific positions (upstream vs downstream) or a global device response.
