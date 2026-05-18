# Time-State Model — Archive Summary

This folder contains the archived `time_state/` module from `stepgen/models/time_state/`.
The work was superseded by the Stage-Wise V3 model (see `stepgen/models/stage_wise_v3/`),
which addresses the same core problems with better-grounded physics.

---

## What problem it was solving

The baseline steady-state hydraulic model overpredicted droplet generation frequency by
**5–6×** compared to experiment (e.g. predicted ~12 Hz, observed ~3 Hz for W11 at Po=300 mbar,
Qw=1.5 mL/hr). The time-state work was an attempt to explain and correct that gap.

The hypothesis: real DFUs do not run in continuous steady flow. They cycle through
OPEN → PINCH → RESET phases, with the DFU substantially blocked for a large fraction of each
cycle. This "gating" reduces effective throughput and therefore frequency.

---

## Four model variants built

### 1. Steady-state (baseline, unchanged)
- Algebraic: `f = Q / V_droplet`
- Fast, deterministic, 5–6× overprediction

### 2. Duty-factor model (`duty_factor.py`)
The best practical outcome of this body of work.

Applies an empirical scalar φ to effective flow rates:
```
Q_eff = φ × Q_steady
```
With φ ≈ 0.18 (calibrated range 0.15–0.20), this corrected frequency into good agreement
with experiment. Fast — algebraic, no time integration needed.

**Key insight**: The DFU is only "open" (passing dispersed phase) for roughly 18% of
the cycle time. The rest is pinch + reset overhead.

### 3. Time-state model (`time_state_dfu.py`, `state_machines.py`)
Physics-based: numerically integrates through OPEN → PINCH → RESET cycles.

```
OPEN ──droplet_formation──> PINCH ──tau_pinch──> RESET ──tau_reset──> OPEN
```

During PINCH: conductance drops to `g_pinch_frac × g_open` (≈ 1% — nearly blocked).
Frequency emerges from counting events over simulated time.

Calibrated parameters:
- `tau_pinch_ms` ≈ 50–120 ms (blocked phase duration — high sensitivity)
- `tau_reset_ms` ≈ 20–50 ms (refill/reset overhead)
- `g_pinch_frac` ≈ 0.001–0.01

Result: ~7 Hz for W11 baseline — still 2.3× above experiment. Better than steady-state
but never as accurate as the empirical duty-factor approach.

### 4. Time-state + filling mechanics (`time_state_filling.py`, `filling_mechanics.py`)
Enhanced physics: adds volume consumed by meniscus refill each cycle.

```
V_cycle = V_droplet + V_in_channel + V_refill
V_in_channel = A_DFU × L_breakup   (in-channel volume at breakup)
V_refill = A_DFU × L_retreat        (meniscus re-advance per cycle)
```

With default parameters (L_retreat = 10 µm, L_breakup = 5 µm), this created a 35×
effective volume increase — far too aggressive, giving <1 Hz. With L_retreat = 1–3 µm,
L_breakup = 1–2 µm, the effect is more moderate but parameter-sensitive.

**Key insight**: the meniscus refill cost is physically real but the model couldn't
constrain it well without direct measurement of retreat/advance distances.

---

## What it got right

- The 5–6× overprediction is real and the gating hypothesis is correct in spirit.
  The DFU does not run at full steady-state throughput continuously.
- The duty-factor value φ ≈ 0.18 is a reliable empirical correction and agrees with
  what you'd expect if Stage 1 (refill) occupies ~80% of the cycle.
- The OPEN/PINCH/RESET framework correctly identifies the three phases of a generation cycle.
- The meniscus refill volume concept was the right direction — it maps directly onto
  what Stage 1 of the v3 model computes via two-fluid Washburn.

## What it didn't get right

- The time integration never converged to experimental frequency as reliably as the
  simple duty-factor empirical correction. Too many free parameters.
- The filling mechanics parameters (L_retreat, L_breakup) couldn't be independently
  measured, so the model was underconstrained.
- It modelled a single representative DFU, not the coupled ladder network — so pressure
  redistribution effects across rungs were not captured.

---

## Why V3 stage-wise superseded it

The v3 model replaces the time-state framework with a physically-grounded two-stage decomposition:

| Stage | v3 approach | Replaces |
|-------|------------|---------|
| Stage 1 (refill) | Two-fluid Washburn equation — derives refill time from geometry, viscosities, surface tension | tau_reset + L_retreat empirical parameters |
| Stage 2 (snap-off) | Critical radius Rcrit criterion — derives droplet volume from geometry | V_droplet algebraic |
| Network | Dynamic reduced-order hydraulic network across all rungs | Single-DFU approximation |
| Cycle fraction | Emerges from Stage 1 + Stage 2 times — no empirical φ | duty_factor_phi |

The key difference: Stage 1 Washburn refill time is **derivable from measurable quantities**
(channel geometry, fluid viscosities, contact angle, interfacial tension). No free timing parameters.

---

## Parameters to remember if this work is revisited

| Parameter | Calibrated value | Notes |
|-----------|-----------------|-------|
| `duty_factor_phi` | 0.18 (range 0.15–0.20) | Best empirical correction |
| `tau_pinch_ms` | 50–120 ms | High sensitivity, geometry-dependent |
| `tau_reset_ms` | 20–50 ms | Medium sensitivity |
| `g_pinch_frac` | 0.001–0.01 | 1% conductance during pinch |
| `L_retreat_um` | 1–3 µm realistic (10 µm default too high) | Meniscus refill distance |
| `L_breakup_um` | 1–2 µm realistic (5 µm default too high) | In-channel breakup contribution |

---

## Source files in this archive

| File | Purpose |
|------|---------|
| `duty_factor.py` | Empirical φ model — best practical outcome |
| `time_state_dfu.py` | Base time-integration model |
| `time_state_filling.py` | Enhanced model with filling mechanics |
| `state_machines.py` | OPEN/PINCH/RESET phase transition logic |
| `filling_mechanics.py` | V_in_channel and V_refill volume calculations |
| `stage_physics.py` | Older multi-stage physics (predates the DFU framing) |
| `stage_wise_model.py` | Wrapper that connected stage_physics into the model registry |

Related docs (in `docs/archive/02_time_state_model/`):
- `time_state_model_summary.md` — detailed parameter tuning guide
- `time_state_model_analysis.md` — experimental validation results
- `implementation_plan_time_state.md` — original development roadmap
