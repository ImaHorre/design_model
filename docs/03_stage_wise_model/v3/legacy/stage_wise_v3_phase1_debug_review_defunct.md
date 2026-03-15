> **DEFUNCT — March 2026**
> This debug review diagnosed bugs in the original Washburn-ODE Stage 1
> implementation (spurious w in geometry factor; missing network driving pressure).
> The Washburn ODE has since been replaced entirely. The current Stage 1 model is
> `t = C_visc × V_reset / (P_j / R_rung)`. Bugs documented here no longer apply.
> See `stage_wise_v3_implementation_plan.md` progress log (March 15 2026).

---

# Stage-Wise V3 Phase 1 — Debug Review & Calculation Flow

**Date**: March 14, 2026
**Reviewer**: Claude (Sonnet 4.6)
**Status**: Phase 1 Complete, Phases 2–7 Planned
**Concern**: Test results showing 0 Hz droplet production

---

## Purpose

This document traces the complete calculation flow of the stage-wise v3 model when given a config YAML and asked to simulate. It is written to help identify why the Phase 1 test results show effectively 0 Hz droplet production — whether this is a known limitation of Phase 1 scope, or a genuine physics error in the implemented code.

**Short answer, stated upfront**: There are **two physics bugs** in the current Phase 1 code — one critical and one major — that together produce the 0 Hz result. Neither is expected as a Phase limitation. Both are implementation errors against the authoritative physics plan. Details follow.

---

## Reference Documents

| Document | Role |
|---|---|
| `stage_flow_v3_plan_issues_resolved.md` | Authoritative resolved physics |
| `two_phase_washburn.typ` | Authoritative Washburn derivation |
| `stage_wise_v3_consolidated_physics_plan.md` | Architecture decisions |
| `stage_wise_v3_implementation_plan.md` | Phase scope and pseudocode |
| `configs/test_stage_wise_v3.yaml` | Test configuration |

---

## Test Configuration Summary

From `configs/test_stage_wise_v3.yaml`:

```yaml
fluids:
  mu_continuous: 0.00089      # water, Pa·s
  mu_dispersed:  0.06         # oil, Pa·s  (67x more viscous than water)
  gamma: 0.015                # 15 mN/m

geometry:
  rung:
    mcd: 5e-6                 # rung depth, 5 µm
    mcw: 8e-6                 # rung width, 8 µm
    mcl: 4000e-6              # rung length, 4000 µm

  junction:
    exit_width: 15e-6         # 15 µm
    exit_depth: 5e-6          # 5 µm

operating:
  Po_in_mbar: 300.0
  Qw_in_mlhr: 1.5

stage_wise_v3:
  gamma_effective: 15.0e-3    # N/m
  theta_effective: 30.0       # degrees
  R_critical_ratio: 0.7
  stage1_mechanism: "auto"
```

---

## Complete Calculation Flow

### STEP 0 — Entry Point

**File**: `stepgen/models/stage_wise_v3/hydraulic_interface.py`, line 87

```python
v3_result = stage_wise_v3_solve(config, Po_mbar, Qw_mlhr, P_out_mbar)
```

This calls the main solver in `core.py`. The `StageWiseV3Model.solve()` adapter (line 46) converts units before calling:
- Pa → mbar for Po
- m³/s → mL/hr for Qw
- Pa → mbar for P_out

---

### STEP 1 — Main Iteration Loop

**File**: `core.py`, lines 158–186

```python
while not converged and iteration < v3_config.max_hydraulic_iterations:
    # 1. Solve dynamic hydraulic network
    hydraulic_result = solve_dynamic_hydraulic_network(
        config, droplet_state, Po_in_mbar, Qw_in_mlhr, P_out_mbar
    )

    # 2. Create rung groups
    rung_groups = create_adaptive_rung_groups_v3(hydraulic_result, v3_config)

    # 3. Solve droplet physics for each group
    group_results = [
        solve_droplet_physics_for_group_v3(group, config, v3_config)
        for group in rung_groups
    ]

    # 4. Update droplet state, check convergence
    new_droplet_state = aggregate_droplet_production(group_results, config)
    converged = check_hydraulic_convergence(droplet_state, new_droplet_state, ...)
    droplet_state = new_droplet_state
    iteration += 1
```

**Architecture**: Iterative hydraulic-droplet coupling per Issue 10 (physics plan). On first iteration, `droplet_state.is_empty() == True` so no dispersed-phase loading corrections are applied.

---

### STEP 2 — Dynamic Hydraulic Network

**File**: `hydraulics.py`, lines 83–138

```python
def solve_dynamic_hydraulic_network(config, droplet_production_state, ...):
    # Base hydraulic state using existing backbone
    base_result = simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar)

    # Loading corrections (zero on iteration 1)
    dispersed_loading = estimate_dispersed_phase_loading(droplet_production_state, config)
    loading_corrections = calculate_loading_corrections(dispersed_loading, base_result, config)

    # Apply corrections
    P_oil_dynamic = apply_oil_corrections(base_result.P_oil, loading_corrections)
    P_water_dynamic = apply_water_corrections(base_result.P_water, loading_corrections)

    # Junction pressure analysis
    junction_pressures = calculate_junction_pressures(P_oil_dynamic, P_water_dynamic, config)
```

The `simulate()` call is the existing v2 hydraulic backbone. On iteration 1, loading corrections are zero (loading fraction = 0.0 since `droplet_state.is_empty()`).

**Junction pressure** (Issue 2, `hydraulics.py` line 248):
```python
P_j_pre_neck = P_oil_dynamic - P_water_dynamic
```

For 300 mbar inlet and typical rung resistances, this gives P_j in the order of tens to hundreds of Pa depending on device position. This definition is correct per the physics plan.

**Result**: A `DynamicHydraulicResult` with per-rung P_oil, P_water, and P_j arrays.

---

### STEP 3 — Rung Grouping

**File**: `core.py`, lines 210–261

```python
P_j = hydraulic_result.P_oil_dynamic - hydraulic_result.P_water_dynamic
P_j_range = np.max(P_j) - np.min(P_j)
P_j_mean = np.mean(P_j)
relative_variation = P_j_range / P_j_mean
requires_grouping = relative_variation > v3_config.pressure_uniformity_threshold  # 5%
```

If the device is hydraulically uniform (variation < 5%), a single group covering all rungs is created. Otherwise groups are created by splitting the rung array into spatial segments. This is consistent with Issue 10.

For the test config (short 0.75m main channel, single operating point), a single group is likely.

**Group dictionary** passed to physics solver:
```python
{
    "group_id": 0,
    "rung_indices": [0, 1, ..., N-1],
    "P_oil_avg": float,
    "P_water_avg": float,
    "P_j_avg": float,   # ← This P_j drives Stage 1 and Stage 2
    "Q_avg": float,     # ← Per-rung average flow rate
}
```

---

### STEP 4 — Droplet Physics for Each Group

**File**: `core.py`, lines 264–302

```python
def solve_droplet_physics_for_group_v3(group, config, v3_config):
    P_j = group["P_j_avg"]
    Q_nominal = group["Q_avg"]

    stage1_result = solve_stage1_washburn_physics(P_j, Q_nominal, config, v3_config)
    stage2_result = solve_stage2_critical_size_with_tracking(P_j, config, v3_config)
    regime_result = classify_regime_multi_factor(P_j, Q_nominal, config, v3_config)
    ...
```

Stage 1 and Stage 2 results together determine the cycle time and therefore the frequency.

---

### STEP 5 — Stage 1: Two-Fluid Washburn

**File**: `stage1_physics.py`, lines 73–162

This is the most important step for understanding the 0 Hz result.

#### Step 5a — Mechanism Selection

```python
mechanism = select_stage1_mechanism(P_j, Q_nominal, config, v3_config)
```

With `stage1_mechanism: "auto"` and no surfactant, the selection computes Ca = μ_w·U/γ. For the test flow rates, Ca is very small (capillary-dominated), so the function returns `HYDRAULIC_DOMINATED`. Correct.

#### Step 5b — Two-Fluid Washburn Base Calculation

**File**: `stage1_physics.py`, lines 165–285

```python
def solve_two_fluid_washburn_base(config, v3_config):
    # Geometry from JUNCTION EXIT (lines 183–185)
    w = config.geometry.junction.exit_width    # 15e-6 m
    h = config.geometry.junction.exit_depth    # 5e-6 m
    aspect_ratio = h / w                       # 0.333

    # Reset distance (lines 188–190)
    x0 = 0.0
    xf = w          # exit_width = 15e-6 m
    L_tot = xf - x0 # 15e-6 m

    # Fluid viscosities (lines 193–194)
    mu1 = config.fluids.mu_dispersed    # oil, 0.06 Pa·s (advancing)
    mu2 = config.fluids.mu_continuous   # water, 0.00089 Pa·s (displaced)

    # Effective interfacial properties (lines 197–198)
    gamma12 = v3_config.gamma_effective    # 15e-3 N/m
    theta12 = v3_config.theta_effective    # 30.0 degrees

    # Shah & London f(α) (lines 200–201)
    f_alpha = calculate_resistance_factor(aspect_ratio)  # ≈ 68.4

    # Capillary driving pressure (line 204)
    capillary_pressure = gamma12 * np.cos(np.radians(theta12)) * (1/h + 1/w)

    # Geometry factor (line 207) ← BUG 1 IS HERE
    geometry_factor = w * h**2 / f_alpha

    # Washburn constant
    K = capillary_pressure * geometry_factor
```

Then the ODE is solved:
```python
def washburn_ode(t, x):
    resistance_term = mu1 * x[0] + mu2 * (L_tot - x[0])
    return np.array([K / resistance_term])
```

---

## BUG 1 — Critical: Wrong Geometry Factor in Washburn (0 Hz Root Cause)

**Location**: `stage1_physics.py`, line 207

**The bug**:
```python
geometry_factor = w * h**2 / f_alpha   # ← WRONG: extra factor of w
```

**Should be**:
```python
geometry_factor = h**2 / f_alpha       # ← CORRECT: no w
```

### Where the error comes from

The `two_phase_washburn.typ` document derives the governing equation in Section 4. The intermediate derivation is correct:

```
ẋ = ΔP_cap / (wh · [R₁x + R₂(L_tot-x)])
```

Substituting R_i = f(α)·μ_i / (wh³):

```
ẋ = ΔP_cap / (wh · f(α)·(μ₁x + μ₂(L_tot-x))/(wh³))
  = ΔP_cap · h² / (f(α) · (μ₁x + μ₂(L_tot-x)))
```

However, the boxed final form in the document (Section 6) incorrectly writes:

```
ẋ = [γcos(θ)(1/h + 1/w)] · [wh²/f(α)] · [1/(μ₁x + μ₂(L_tot-x))]
```

There is an **extra factor of `w`** in the `wh²` term that should not be there. The correct form has `h²/f(α)`, not `wh²/f(α)`.

This is confirmed by the units table in the `.typ` document itself: it states K has units `[Pa·m²]`. But using `wh²/f(α)`:

```
K = Pa · m · m² = Pa·m³   ← WRONG (gives ẋ in m²/s, not m/s)
```

Using `h²/f(α)`:

```
K = Pa · m²               ← CORRECT (gives ẋ in m/s)
```

The code faithfully implements the document's boxed formula including this error.

### Numerical impact

With test config values:
- `capillary_pressure` = γcos(θ)(1/h + 1/w) = 15e-3 × 0.866 × (200000 + 66667) = **3463 Pa**
- `f_alpha` ≈ **68.4** (Shah & London for α = 0.333)

**With the bug** (`w * h²/f_alpha`):
```
K_wrong = 3463 × (15e-6 × 25e-12 / 68.4) = 3463 × 5.48e-18 = 1.898e-14 Pa·m³
```

**With the fix** (`h²/f_alpha`):
```
K_correct = 3463 × (25e-12 / 68.4) = 3463 × 3.65e-13 = 1.265e-9 Pa·m²
```

The ratio K_correct / K_wrong = w = 15e-6. K is **66,667 times too small** in the current code.

The analytical approximation for refill time (from integrating the ODE):

```
t_refill ≈ L_tot² · (μ₁ + μ₂) / (2 · K)
```

Since K appears in the denominator:

| | K value | t_refill |
|---|---|---|
| Bug (code as written) | 1.9e-14 | **≈ 361 s** |
| Fix (correct formula) | 1.3e-9 | **≈ 5.4 ms** |

The Stage 1 refill time is **67,000 times too long**. The model predicts Stage 1 takes ~6 minutes when it should take ~5 milliseconds.

**This directly explains the 0 Hz production result.** Frequency = 1/(t1 + t2) ≈ 1/361 ≈ 0.003 Hz.

### Is this a Phase limitation?

**No.** Phase 1 explicitly states "Two-fluid Washburn base implementation" as a core deliverable and includes the Washburn ODE as written. The bug is a transcription error against the authoritative `.typ` derivation document — it is an unintended code error, not an intentional deferral.

---

## BUG 2 — Major: Wrong Hydraulic Resistance in Stage 2 Growth

**Location**: `stage2_physics.py`, lines 292–293

**The bug**:
```python
A_channel = config.geometry.junction.exit_width * config.geometry.junction.exit_depth
# A_channel = 15e-6 * 5e-6 = 75e-12 m²

R_hydraulic = 12 * mu_oil * L_eff / A_channel**3   # ← WRONG: A_channel**3
```

**Should use**:
```python
R_hydraulic = 12 * mu_oil * L_eff / (exit_width * exit_depth**3)
# = 12 * 0.06 * 15e-6 / (15e-6 * 125e-18)
```

The correct Poiseuille resistance for a rectangular channel (slit approximation) is:
```
R = f_alpha · μ · L / (w · h³)
```

The code uses `A_channel³ = (w·h)³ = w³·h³` in the denominator instead of `w·h³`. This is wrong by a factor of `w²`.

### Numerical impact

```
R_code    = 12 × 0.06 × 15e-6 / (75e-12)³ = 2.56e25  Pa·s/m³
R_correct = 12 × 0.06 × 15e-6 / (15e-6 × 125e-18) = 5.76e15  Pa·s/m³
```

R_code is **4.4 billion times** too large. This makes Q_eff ≈ 0, so:

```python
growth_time = dV / Q_eff → ∞
```

Which then gets clamped (line 306):
```python
growth_time = max(min(growth_time, 1e-1), 1e-6)  # clamped to [1µs, 100ms]
```

**Stage 2 growth time is always clamped to its maximum value of 100 ms.**

### Is this a Phase limitation?

**No.** The `simulate_droplet_growth_to_critical_radius` function is implemented as part of Phase 1 and should compute a meaningful growth time. The formula typo is an implementation error. However, since Stage 1 is ~361 s and Stage 2 is ~0.1 s, Bug 1 completely dominates the cycle time — Bug 2 is secondary.

---

## STEP 6 — Stage 2: Critical Radius and Necking

**File**: `stage2_physics.py`, lines 137–212

```python
def solve_stage2_critical_size_with_tracking(P_j, config, v3_config):
    R_critical = calculate_critical_radius_from_geometry(config, v3_config)
    neck_tracker = NeckStateTracker()
    growth_result = simulate_droplet_growth_to_critical_radius(R_critical, P_j, config, neck_tracker)
    t_necking, necking_diagnostics = calculate_necking_time_outer_phase(config, v3_config)
    ...
```

#### Critical radius calculation (lines 215–252)

```python
w = config.geometry.junction.exit_width    # 15e-6 m
h = config.geometry.junction.exit_depth    # 5e-6 m
aspect_ratio = w / h                       # 3.0

if aspect_ratio > 3.0:
    R_critical = R_critical_ratio * h      # depth-limited
else:
    R_critical = R_critical_ratio * min(w, h)  # geometric mean

# For w/h = 3.0 (exactly at boundary, takes else branch):
# R_critical = 0.7 * 5e-6 = 3.5 µm
```

This is correct per Issue 6. For this test config, R_critical = 3.5 µm.

#### Necking time (lines 330–380, outer-phase physics)

```python
mu_outer = config.fluids.mu_continuous  # water, 0.00089 Pa·s
R_neck = config.geometry.junction.exit_width / 4  # 3.75 µm

Oh_outer = mu_outer / sqrt(rho_outer * gamma * R_neck)
# = 0.00089 / sqrt(1000 × 0.015 × 3.75e-6)
# = 0.00089 / sqrt(5.625e-5)
# = 0.00089 / 0.0075
# Oh_outer ≈ 0.119

# Oh_outer > 0.1 → viscous regime
tau_viscous = mu_outer * R_neck / gamma
# = 0.00089 × 3.75e-6 / 0.015 = 2.23e-7 s ≈ 0.22 µs
```

After viscosity ratio correction (`λ = 0.06/0.00089 ≈ 67.4`):
```python
viscosity_ratio_correction_viscous(λ) = (1 + λ) / (1 + 0.5·λ) = 68.4 / 34.7 ≈ 1.97
tau_necking ≈ 0.44 µs
```

This is very short (sub-microsecond) and appears physically reasonable for a high-viscosity-ratio system. The necking time contribution to total cycle time is negligible.

> **Note**: Necking time is correctly labelled as diagnostic-only and does NOT control snap-off (per Issue 4 physics plan). This is correctly implemented.

---

### STEP 7 — Cycle Time and Frequency Calculation

**File**: `core.py`, lines 400–402 and `hydraulic_interface.py`, lines 125–136

```python
# Global metrics computation (core.py line 401)
cycle_time = group.stage1_result.t_displacement + group.stage2_result.t_growth
frequency = 1.0 / cycle_time if cycle_time > 0 else 0.0
```

With the bugs:
- `t_displacement` (Stage 1) ≈ **361 s** (should be ~5 ms)
- `t_growth` (Stage 2) ≈ **0.1 s** (clamped, should be physically computed)

```
cycle_time ≈ 361.1 s
frequency  ≈ 0.00277 Hz  ← effectively 0 Hz
```

With bugs fixed:
- `t_displacement` ≈ **5 ms**
- `t_growth` ≈ physically computed value (need Bug 2 fix to assess)

---

## STEP 8 — Regime Classification

**File**: `regime_classification.py`

This step correctly runs multi-factor validation checks: capillary number, pressure balance, flow capacity, inertial effects, and geometry scaling. These are diagnostic-only and do NOT override snap-off. This is correctly implemented per Issue 9.

With Q_avg ≈ very small (per-rung flow), Ca will be very small → `DRIPPING` regime classification. Correct.

---

## STEP 9 — Aggregation and Result

**File**: `core.py`, lines 305–350

```python
def aggregate_droplet_production(group_results, config):
    ...
    # From Stage 2 result:
    V_droplet = group.stage2_result.V_droplet
    # = (4/3)π·R_critical³ = (4/3)π·(3.5e-6)³ ≈ 1.8e-16 m³ ≈ 0.18 fL

    # "Production rate" = Q_avg / V_droplet
    group_production_rate = group.Q_avg / V_droplet
```

> **Design note**: This production rate estimate (`Q_avg / V_droplet`) conflates hydraulic flow with droplet volume. This is an approximation — the real frequency should come from `1/cycle_time`. The `compute_global_metrics` function (line 401) correctly computes frequency from `1/cycle_time`. The `aggregate_droplet_production` result is only used for hydraulic convergence checking, not the final reported frequency.

---

## Additional Physics Issues to Note

### Issue A — Wrong Channel Dimensions in Washburn (moderate)

**File**: `stage1_physics.py`, lines 183–185

The Washburn equation is solved using **junction exit dimensions** (`exit_width=15µm`, `exit_depth=5µm`) but the physics plan says refill occurs through the "**rung / refill channel**":

> "x(t) is the meniscus position measured along the rung / refill channel"

The rung dimensions from the test config are:
- `mcw` = 8 µm (rung width)
- `mcd` = 5 µm (rung depth)

Using junction exit dimensions instead of rung dimensions changes:
- Capillary pressure: 3463 Pa (junction) vs 4222 Pa (rung, ~22% higher for rung)
- Geometry factor: different f(α) for different aspect ratios
- Net timing error: ~40%

This is a moderate physics accuracy issue but not the root cause of 0 Hz. The code comments say the reset distance ≈ exit_width, which may be why junction dimensions were chosen. However, the channel the meniscus travels through during refill should be the rung geometry, while the reset distance (L_tot = exit_width) is a separate choice. These two things are conflated in the current implementation.

> **Phase note**: This should be addressed when Phase 2 fully implements the Stage 1 Washburn with proper boundary conditions. Not a Phase 2 blocker but a known physics approximation.

### Issue B — P_j Not Included in Washburn Driving Pressure (Phase 2 scope)

The two-fluid Washburn baseline uses only capillary pressure `γcos(θ)(1/h + 1/w)` as the driving force. The plan (Issue 3A) notes:

> "Local pressure conditions during refill can be treated as quasi-static"

Phase 2 should consider whether P_j should be added to the capillary pressure, or whether the capillary pressure alone is the correct driver. In the current junction geometry (step-emulsification), the oil pressure at the junction (P_j) may also contribute to driving refill. This is left for Phase 2 per the implementation plan.

### Issue C — NeckStateTracker Initialization Inconsistency (minor)

**File**: `stage2_physics.py`, lines 95–96

```python
def __init__(self, initial_time: float = 0.0):
    self.times = [initial_time]  # ← 1 entry
    self.neck_widths = []        # ← 0 entries
    self.neck_velocities = []
    self.neck_capillary_numbers = []
    self.thinning_rates = []
```

After the first `update()` call, `times` will have 2 entries while all other arrays have 1 entry. The `get_evolution()` method returns these as numpy arrays of mismatched lengths:

```python
return NeckEvolution(
    times=np.array(self.times),              # length N+1
    widths=np.array(self.neck_widths),       # length N
    velocities=np.array(self.neck_velocities),
    ...
)
```

This causes `neck_evolution.times` to be one element longer than `neck_evolution.widths`. For Phase 1 testing this does not crash (the warning code uses max/len operations), but it is a logical error that should be fixed. The initial_time entry in `times` has no corresponding width entry.

**Fix**: Either remove `self.times = [initial_time]` from `__init__` and start from `[]`, or add initial placeholder entries for all arrays.

### Issue D — aspect_ratio Boundary Condition in R_critical

**File**: `stage2_physics.py`, line 238

```python
if aspect_ratio > 3.0:
    R_critical = R_critical_ratio * h   # depth-limited
else:
    R_critical = R_critical_ratio * min(w, h)  # geometric mean
```

With `w=15µm`, `h=5µm`: `aspect_ratio = w/h = 3.0` (exactly at boundary). The condition `> 3.0` is False, so it takes the `else` branch: `R_critical = 0.7 × min(15, 5) = 3.5 µm`.

If the intent is that w/h ≥ 3 should be depth-limited, the condition should be `>= 3.0`. For this specific test config, the device sits exactly on the boundary and the result depends on whether the test is strict or inclusive. The droplet size computed is 7 µm diameter, which is reasonable for a 5 µm deep junction. This is a minor boundary condition question, not a bug per se.

---

## Summary Table

| Issue | File | Line | Severity | Root Cause of 0 Hz? | Phase Fix? |
|---|---|---|---|---|---|
| **BUG 1**: Washburn K has extra `w` factor | `stage1_physics.py` | 207 | **CRITICAL** | **YES — primary cause** | Fix now (Phase 1 error) |
| **BUG 2**: Stage 2 R_hydraulic uses `A³` not `w·h³` | `stage2_physics.py` | 292 | **MAJOR** | Secondary (dominated by Bug 1) | Fix now (Phase 1 error) |
| **Issue A**: Washburn uses junction dims, not rung dims | `stage1_physics.py` | 183–185 | Moderate | No | Phase 2 refinement |
| **Issue B**: P_j not in Washburn driving pressure | `stage1_physics.py` | 204 | Design | No | Phase 2 scope |
| **Issue C**: NeckStateTracker `times` has N+1 entries | `stage2_physics.py` | 95–96 | Minor | No | Fix at convenience |
| **Issue D**: R_critical boundary `>` vs `>=` | `stage2_physics.py` | 238 | Minor | No | Clarify intent |

---

## Expected Behaviour After Bug Fixes

After fixing **Bug 1** (`geometry_factor = h**2 / f_alpha`):

- Stage 1 refill time: ~5 ms (from ~361 s)
- Frequency estimate: dictated by Stage 2 growth time

After also fixing **Bug 2** (correct hydraulic resistance in Stage 2):

- Stage 2 growth time: physically computed (not clamped)
- Full cycle time: t1 (~5 ms) + t2 (to be computed) + t_necking (~0.4 µs)
- Expected frequency: order 10–200 Hz range depending on exact Stage 2 growth physics

**Note**: Even with both bugs fixed, the Stage 2 growth model uses a simplified constant-pressure approximation with constant neck width. Phase 3 is needed to implement the full Laplace-pressure-coupled growth model. Some additional inaccuracy in t2 should be expected even after fixing Bug 2.

---

## Verification Check Against `stage_flow_v3_plan_issues_resolved.md`

The `issues_resolved` document describes the following intended physics flow for Stage 1:

> "Stage 1 time is then obtained from the refill integral:
> t_Stage1 = ∫ dx/ẋ(x) from x0 to xf"

The governing equation written there is:
```
ẋ(t) = [γ₁₂cos(θ₁₂)(1/h + 1/w)] · [wh²/f(α)] · [1/(μ₁x + μ₂(L_tot - x))]
```

**This formula as written also contains the Bug 1 error** — it is transcribed from the `.typ` document's incorrect boxed equation. The correct form (derivable from the intermediate steps in Section 4 of the `.typ` document) is:

```
ẋ(t) = [γ₁₂cos(θ₁₂)(1/h + 1/w)] · [h²/f(α)] · [1/(μ₁x + μ₂(L_tot - x))]
```

The `w` in the geometry factor is a propagated typo from the `.typ` document's final summary equation. The derivation steps within the `.typ` document (Section 2 and Section 4 intermediate lines) are internally consistent and give the correct formula without `w`.

---

## Recommended Actions

### Immediate (to unblock meaningful Phase 1 output)

1. **Fix Bug 1** in `stage1_physics.py` line 207:
   ```python
   # Change:
   geometry_factor = w * h**2 / f_alpha
   # To:
   geometry_factor = h**2 / f_alpha
   ```

2. **Fix Bug 2** in `stage2_physics.py` line 292–293:
   ```python
   # Change:
   R_hydraulic = 12 * mu_oil * L_eff / A_channel**3
   # To:
   R_hydraulic = 12 * mu_oil * L_eff / (config.geometry.junction.exit_width * config.geometry.junction.exit_depth**3)
   ```

3. **Fix Bug C** in `stage2_physics.py` line 95–96:
   ```python
   # Change:
   self.times = [initial_time]
   # To:
   self.times = []
   ```
   (and start updating from the first `update()` call)

### Before Phase 2

4. Decide whether junction dimensions or rung dimensions should be used in the Washburn calculation (Issue A above). The physics plan says "rung / refill channel" — if the refill path is the rung, `mcw` and `mcd` should be used.

5. Update the erroneous formula in `stage_flow_v3_plan_issues_resolved.md` and `two_phase_washburn.typ` (if edit permission exists) to show `h²/f(α)` not `wh²/f(α)` to prevent future confusion.

---

*End of debug review document.*
