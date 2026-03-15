# Stage-Wise V3 Phase 1 Amendment — Debug Review & Calculation Flow

**Date**: March 15, 2026
**Reviewer**: Claude (Sonnet 4.6)
**Status**: Phase 1 Amendment COMPLETE
**Scope**: Stage 1 physics amendment — network-driven driving pressure + geometry fixes
**Test config**: `configs/test_stage_wise_v3.yaml`

---

## Purpose

This document traces the amended Stage 1 calculation flow and verifies that the three
physics issues identified in `stage_wise_v3_phase1_debug_review.md` (Bug 1, Issue A, Issue B)
have all been resolved. It also documents the current state of Stage 2 and remaining issues.

---

## Reference Documents

| Document | Role |
|---|---|
| `stage_wise_v3_consolidated_physics_plan.md` | Authoritative physics spec (A3 updated March 15) |
| `stage_wise_v3_phase1_debug_review.md` | Original bug identification |
| `stage_wise_v3_implementation_plan.md` | Phase progress log |
| `configs/test_stage_wise_v3.yaml` | Test configuration |

---

## Summary of Fixes Applied

| Issue | Original bug | Fix applied | Status |
|---|---|---|---|
| **Bug 1** | `geometry_factor = w * h**2 / f_alpha` (extra w factor) | `geometry_factor = h**2 / f_alpha` | ✅ FIXED |
| **Issue A** | Washburn ODE used junction exit dims (15×5 µm) | Changed to rung dims (8×5 µm); L_r stays = exit_width | ✅ FIXED |
| **Issue B** | P_j not in driving pressure (capillary-only Washburn) | `ΔP_drive = P_j − P_cap`; P_j from hydraulic network | ✅ FIXED |
| **Bug 2** | Stage 2 `R_hydraulic` uses `A_channel**3` not `w·h³` | **Not yet fixed — separate phase** | ⚠️ OUTSTANDING |
| **Issue C** | `NeckStateTracker.times` has N+1 entries vs N for other arrays | Not yet fixed — minor | ⚠️ OUTSTANDING |
| **Issue D** | `R_critical` boundary `>` vs `>=` at aspect_ratio = 3.0 | Not yet fixed — minor | ⚠️ OUTSTANDING |

---

## Amended Stage 1 Calculation Flow

### What changed in `stage1_physics.py`

**Function**: `solve_two_fluid_washburn_base`

Old signature:
```python
def solve_two_fluid_washburn_base(config, v3_config) -> WashburnResult
```

New signature:
```python
def solve_two_fluid_washburn_base(P_j, config, v3_config) -> WashburnResult
```

**Old governing equation (incorrect)**:
```
ẋ = [γ cos(θ)(1/h + 1/w)] · [w·h²/f(α)] · [1/(μ_oil·x + μ_water·(L_r − x))]
```
where h, w = junction exit dimensions (15×5 µm), geometry factor = w·h²/f(α)

**New governing equation (correct)**:
```
ΔP_drive = P_j − P_cap
ẋ = ΔP_drive · h²/f(α) / (μ_oil·x + μ_water·(L_r − x))
```
where h, w = rung dimensions (8×5 µm), L_r = exit_width = 15 µm (reset distance)

---

## Test Configuration Values

From `configs/test_stage_wise_v3.yaml`:

```
fluids:
  mu_continuous:  0.00089 Pa·s   (SDS/water)
  mu_dispersed:   0.06 Pa·s      (vegetable oil)
  gamma:          0.015 N/m

geometry:
  rung:   mcd = 5e-6 m,  mcw = 8e-6 m
  junction: exit_width = 15e-6 m, exit_depth = 5e-6 m

operating:
  Po_in_mbar: 300.0

stage_wise_v3:
  gamma_effective:   15.0e-3 N/m
  theta_effective:   30.0 degrees
  R_critical_ratio:  0.7
```

---

## Calculation Trace — Stage 1 (Amended)

### Step 1 — Hydraulic network pressures

The hydraulic network solver runs at Po = 300 mbar (30,000 Pa).

From the end-to-end test output, Group 0 (highest-pressure group):

```
P_oil ≈ 29,452 Pa (upstream oil side)
P_water ≈ 0 Pa (near outlet, P_out = 0)
P_j = P_oil − P_water ≈ 29,452 Pa
```

This P_j is the net hydraulic driving pressure available at the junction.

---

### Step 2 — Capillary barrier (rung dimensions)

Using rung dimensions: h = 5 µm, w = 8 µm

```
P_cap = γ cos(θ_eff) · (1/h + 1/w)
      = 0.015 × cos(30°) × (1/5e-6 + 1/8e-6)
      = 0.015 × 0.866 × (200,000 + 125,000)
      = 0.015 × 0.866 × 325,000
      = 4,222 Pa
```

Comparison: with junction dims (old code), P_cap would be:
```
P_cap_old = 0.015 × 0.866 × (200,000 + 66,667) = 3,464 Pa
```
The rung channel is narrower (8 µm vs 15 µm), so capillary barrier is slightly higher (~22%).

---

### Step 3 — Net driving pressure

```
ΔP_drive = P_j − P_cap = 29,452 − 4,222 = 25,230 Pa
```

**Key observation**: P_j (≈ 29.5 kPa) dominates over P_cap (≈ 4.2 kPa) by a factor of ~7.
The capillary barrier is only ~14% of the total driving pressure. This means:

- In the old capillary-only model: driving = 3,464 Pa
- In the new network-driven model: driving = 25,230 Pa
- Ratio: 7.3× more driving pressure with the network model

---

### Step 4 — Geometry factor (Bug 1 fix)

Using rung h = 5 µm, α = h/w = 5/8 = 0.625:

```
f(α) = 96 × (1 − 1.3553×0.625 + 1.9467×0.625² − 1.7012×0.625³
             + 0.9564×0.625⁴ − 0.2537×0.625⁵)
     ≈ 96 × 0.613 ≈ 58.8

geometry_factor = h²/f(α) = (5e-6)²/58.8 = 4.25e-13 m²
```

Old (wrong) form would have been:
```
geometry_factor_old = w × h²/f(α) = 8e-6 × 4.25e-13 = 3.40e-18 m³   ← WRONG
```

The old value was 8e-6 times smaller (w = 8 µm) — this alone gives ~125,000× slowdown in refill time.

---

### Step 5 — ODE constant and refill time

```
K = ΔP_drive × geometry_factor = 25,230 × 4.25e-13 = 1.07e-8 Pa·m²

Analytical approximation for refill time:
t_refill ≈ L_r² × (μ_oil + μ_water) / (2K)
         = (15e-6)² × (0.06 + 0.00089) / (2 × 1.07e-8)
         = 2.25e-10 × 0.06089 / 2.14e-8
         = 1.37e-11 / 2.14e-8
         ≈ 6.4e-4 s ≈ 0.64 ms
```

This matches the ODE solver output of **0.646 ms** for Group 0.

---

## Comparison Table: Before vs After Amendment

| Quantity | Before (Bug 1 + capillary-only + junction dims) | After (all fixes) |
|---|---|---|
| Driving pressure | 3,464 Pa (P_cap only, junction dims) | 25,230 Pa (P_j − P_cap, rung dims) |
| Geometry factor | 3.40e-18 m³ (wrong: w·h²/f·junction) | 4.25e-13 m² (correct: h²/f·rung) |
| ODE constant K | 1.18e-14 Pa·m³ | 1.07e-8 Pa·m² |
| t_stage1 | ~361 s (effectively ∞) | ~0.65 ms ✅ |
| Frequency (Stage 1 limited) | 0.003 Hz | Stage 1 no longer the bottleneck |

---

## Current End-to-End Output (Post-Amendment)

Full solver run with `test_stage_wise_v3.yaml` at Po = 300 mbar, Qw = 1.5 mL/hr:

```
Groups: 10 (non-uniform pressure across device)

Group 0 (highest P_j):
  P_j        = 29,452 Pa  (294.5 mbar)
  P_cap      =  4,222 Pa  (42.2 mbar)  ← capillary barrier
  ΔP_drive   = 25,230 Pa  (252.3 mbar)
  t_stage1   = 0.646 ms                ← Stage 1 FIXED ✅
  t_stage2   = 100.000 ms              ← CLAMPED (Bug 2 not yet fixed ⚠️)
  frequency  = 9.9 Hz
  R_critical = 3.50 µm → D_droplet = 7.00 µm

Group 9 (lowest P_j):
  P_j        = 27,083 Pa  (270.8 mbar)
  ΔP_drive   = 22,861 Pa  (228.6 mbar)
  t_stage1   = 0.713 ms
  t_stage2   = 100.000 ms (clamped)
  frequency  = 9.9 Hz

Device average frequency: 9.93 Hz
Device average diameter:  7.00 µm
```

---

## Stage 2 Status (Bug 2 — Outstanding)

Stage 2 growth time is still clamped to its maximum value of 100 ms due to Bug 2 in
`stage2_physics.py` line 292:

```python
# Current (wrong):
R_hydraulic = 12 * mu_oil * L_eff / A_channel**3   # A_channel = w×h, denominator = (wh)³

# Should be:
R_hydraulic = 12 * mu_oil * L_eff / (exit_width * exit_depth**3)  # denominator = w·h³
```

This makes R_hydraulic ~4.4 billion times too large → Q_eff ≈ 0 → growth_time clamped.

**Impact on current output**: The reported 9.9 Hz is dominated entirely by the 100 ms Stage 2
clamp, not by Stage 1. The true frequency after fixing Bug 2 will be dictated by both stages.

**Not fixed in this amendment**: Bug 2 is a separate Stage 2 fix and should be addressed in
the next implementation phase.

---

## Test Results

### New tests added

All 4 new tests pass:

| Test | Result | What it checks |
|---|---|---|
| `test_two_fluid_washburn_basic` (updated) | ✅ PASS | Refill time in ms range, driving_pressure > 0 |
| `test_washburn_geometry_factor_correct` | ✅ PASS | geometry_factor = h²/f(α), not w·h²/f(α) |
| `test_washburn_network_driving_pressure` | ✅ PASS | Higher P_j → shorter refill time |
| `test_washburn_uses_rung_dimensions` | ✅ PASS | geometry_factor matches rung dims, not junction |

### Full test suite results

```
10 passed, 1 failed
```

The 1 failure is `test_v3_solver_integration` — a pre-existing issue: the test attempts
`config.stage_wise_v3 = StageWiseV3Config()` on a frozen dataclass. This failure predates
this amendment and is not caused by any change here.

---

## Physics Validation Checks

### P_j >> P_cap: hydraulic driving dominates

```
P_j   ≈ 29,452 Pa  (295 mbar)
P_cap ≈  4,222 Pa  ( 42 mbar)
ratio = P_j / P_cap ≈ 7.0
```

Oil inlet pressure (300 mbar) substantially exceeds the capillary barrier (42 mbar). The
network-driven model is the correct choice; pure capillary Washburn would underpredict
driving pressure by ~7× and overpredict refill time by ~7×.

### Capillary barrier is correctly signed (hydrophilic channel)

Channel is hydrophilic (SDS/water wets the walls). Oil (non-wetting phase) must overcome
P_cap to advance. P_cap enters as a subtracted barrier in `ΔP_drive = P_j − P_cap`. ✅

### P_j from network includes all upstream losses

P_j is computed as `P_oil − P_water` by the hydraulic network solver and already includes
all upstream channel resistances. Stage 1 ODE correctly uses only `R_reset(x)` for the
local reset zone resistance — no double-counting. ✅

### θ_eff = 30° is a calibration parameter

The effective contact angle is not a directly measured physical quantity. It encodes the
combined `γ·cos(θ)` capillary driving as a fitting parameter. Back-calculation from
experimental Stage 1 timing data remains the route to constraining this parameter. ✅

### Stage 1 P_j variation across device

P_j varies from 29,452 Pa (Group 0) to 27,083 Pa (Group 9) — a 8.0% variation across the
device. This is above the 5% grouping threshold, hence 10 groups are created. Stage 1 time
varies from 0.646 ms to 0.713 ms — a 10% variation. This spatial variation is correctly
captured by the grouped rung architecture.

---

## Remaining Issues and Recommended Next Steps

### Immediate (before meaningful frequency output)

1. **Fix Bug 2** in `stage2_physics.py` line 292:
   ```python
   # Change:
   R_hydraulic = 12 * mu_oil * L_eff / A_channel**3
   # To:
   R_hydraulic = 12 * mu_oil * L_eff / (config.geometry.junction.exit_width * config.geometry.junction.exit_depth**3)
   ```
   This will unclamp Stage 2 and give a physically computed growth time.

### Minor (fix when convenient)

2. **Fix Issue C** (`NeckStateTracker` `times` length off-by-one): initialise `self.times = []`
   instead of `self.times = [initial_time]`.

3. **Fix Issue D** (`R_critical` boundary): change `if aspect_ratio > 3.0` to `>= 3.0` for
   correct depth-limited behaviour at exactly w/h = 3.

### Future (Phase 2 scope)

4. **Validate θ_eff**: compare model-predicted Stage 1 timing against experimental
   measurements and back-calculate `γ·cos(θ_eff)`.

5. **Test Po sweep**: verify that t_stage1 decreases monotonically with Po (now should work
   since P_j scales with Po).

6. **Fix integration test**: update `test_v3_solver_integration` to load
   `configs/test_stage_wise_v3.yaml` directly (which has the v3 section) rather than
   attempting to mutate a frozen dataclass.

---

*End of Phase 1 Amendment debug review.*
