
# Stage‑Wise Model v3: Consolidated Physics Modeling Strategy (Authoritative Implementation Spec)

Date: March 13, 2026  
Status: Consolidated and clarified specification for implementation  
Supersedes: earlier v2 implementation plan and issues‑resolved notes

---

# DOCUMENT PRECEDENCE RULE

If this document conflicts with any previous planning documents, **this document is authoritative**.

Earlier materials (deep research notes, issues‑resolved notes, and planning drafts) are considered
**supporting background only**.

This document separates:

1. **Authoritative resolved physics decisions**
2. **Implementation scope for this version**
3. **Deferred or research‑stage improvements**

This separation prevents implementation drift when using autonomous coding agents.

---

# SECTION A — AUTHORITATIVE RESOLVED PHYSICS DECISIONS

The following decisions are considered **locked for implementation**.

These should not be re‑interpreted or redesigned during coding.

---

## A1. Hydraulic Boundary Conditions

**Decision:**  
The device uses a **dynamic reduced‑order hydraulic network** to determine local pressure
conditions at each junction.

Purpose:

• Provide realistic junction pressures across the array  
• Allow testing whether pressure varies during droplet formation  
• Avoid full CFD complexity

Key property:

Hydraulics operates at **device scale**, while droplet formation physics operates at **junction scale**.

---

## A2. Junction Pressure Definition

**Definition:**

Pj = upstream pressure located **immediately before the neck region** (used in Stage 2).

Po_local = local oil pressure at rung inlet **P_oil(x) - P_water(x)** (used in Stage 1).

Bulb pressure exists **downstream of the neck**.

**Pressure Variable Separation (March 2026 Physics Correction):**

Stage 1 and Stage 2 use different pressure variables to reflect different physics:
- **Stage 1**: Uses Po_local for rung flow physics during refill
- **Stage 2**: Uses Pj for preneck junction pressure during droplet formation

Relationship:

Pj − P_bulb = ΔP_neck

Where:

P_bulb ≈ Pw + 2γ/R

Implication:

As the droplet grows:

• Laplace pressure decreases  
• Flow resistance increases due to neck thinning

The result is a modest change in volumetric flow but an increase in **local neck velocity**.

---

## A3. Stage 1 Physical Model

> **NOTE — March 2026**: The Washburn ODE section below (baseline refill physics
> through junction exit) has been superseded. The current implementation uses:
>
>     t_stage1 = C_visc × V_reset / (P_j / R_rung)
>
> where V_reset = L_r × exit_width × exit_depth, R_rung is the rung Poiseuille
> resistance, and C_visc = stage1_viscosity_correction (default 1.0, calibrate from
> experiment). The Washburn ODE predicted ~0.2 ms at 200–300 mbar — too fast by
> ~3 orders of magnitude. The qualitative reasoning below (Po-dependence, t_stage1
> ≈ t_refill) remains valid. See implementation_plan.md progress log March 15 2026.

Stage 1 consists of two processes:

1. **Fast reset / back‑intrusion**
2. **Slower refill of dispersed phase**

The fast reset is effectively instantaneous relative to refill time.

Therefore:

t_stage1 ≈ t_refill

### Baseline refill physics

Refill is modeled as **network-driven Poiseuille flow through a short two-fluid reset
zone with a capillary pressure barrier**.

This formulation generalises the two-fluid Washburn moving-interface model by explicitly
including the hydraulic network pressure as the primary driving force. Pure capillary-only
Washburn is the limiting case when P_j ≈ P_water, but is not used as the baseline because
it has no dependence on inlet oil pressure (Po) and therefore cannot reproduce the observed
strong Po-dependence of Stage 1 timing.

Single-phase Poiseuille refill is **not used** as the baseline model because it
systematically overpredicts refill speed.

### Wettability and capillary pressure direction

The device uses a **hydrophilic channel** (SDS/water continuous phase, vegetable oil
dispersed phase). Water is the wetting phase; oil is non-wetting.

Consequence: capillary pressure **opposes** oil advance into the water-filled reset zone.
It acts as a barrier that must be overcome by the hydraulic driving pressure.

### Driving pressure

The net driving pressure for meniscus advance is:

  ΔP_drive = P_j − P_water − P_cap

where:

• P_j     = oil pressure at the junction, pre-neck (from the hydraulic network solver —
            same variable as used in Stage 2; already includes all upstream oil-column
            resistance and must NOT be added again here)
• P_water = local continuous-phase pressure downstream of the reset zone
• P_cap   = γ cos(θ_eff) · (1/h + 1/w)   [capillary barrier, positive value]
• γ       = oil-water interfacial tension
• θ_eff   = effective contact angle (treated as a calibration parameter; back-calculated
            from experimental Stage 1 timing data once available)

The meniscus advances when ΔP_drive > 0. Refill speed increases with higher P_j
(i.e. higher Po), which is consistent with experimental observations.

### Channel geometry for the reset zone

The reset meniscus moves through the **junction exit region**, not the rung.

The rung (mcd, mcw) is a long high-resistance upstream channel. Its resistance is already
captured in P_j from the hydraulic network and must NOT be re-introduced in this ODE.

Dimensions for the ODE:

• h = exit_depth   (junction exit channel depth)
• w = exit_width   (junction exit channel width; also equals L_r)
• L_r = exit_width (reset distance — the oil was pushed back approximately one exit width)

### Two-fluid resistance of the reset zone

At meniscus position x along the reset zone of total length L_r:

  R_reset(x) = f(α) / (w · h³) · [μ_oil · x + μ_water · (L_r − x)]

where:

• f(α) = rectangular-channel resistance correction factor (Shah & London)
• α    = h/w = exit_depth / exit_width (junction exit aspect ratio)
• μ_oil, μ_water = viscosities of the two phases

As oil replaces water, resistance evolves with x, giving naturally Washburn-like dynamics
even under pressure-driven flow.

### Governing equation

  dx/dt = ΔP_drive / [w · h · R_reset(x)]
        = (P_j − P_cap) · h² / [f(α) · (μ_oil · x + μ_water · (L_r − x))]

Stage 1 refill time is obtained by integrating x from 0 to L_r.

Note: the geometry factor is h²/f(α), not w·h²/f(α). The extra factor of w is a known
transcription error in earlier derivation documents and must not be reintroduced.

### Optional alternate mechanisms (extensions, not baseline)

• dynamic contact-line effects
• adsorption-limited refill
• backflow-dominated refill

These are **extensions**, not baseline physics.

---

## A4. Stage 2 Snap‑Off Condition

Within the **monodisperse regime**, droplet snap‑off occurs when droplet radius reaches:

R = Rcrit

This value is treated as:

• experimentally known  
• geometry dependent  
• configurable per device

Neck variables are tracked during growth but **do not control snap‑off in the first implementation**.

Tracked diagnostics may include:

• neck velocity  
• neck capillary number  
• thinning rate

These are used for **warnings and regime detection only**.

---

## A5. Grouped Rung Simulation

Rungs are simulated in **groups** sharing similar local hydraulic conditions.

Reason:

Pressure and flow vary along the array.

Grouped simulation reduces computational cost while preserving spatial variation.

Simulation therefore proceeds:

Hydraulics → group conditions → droplet cycle → aggregated device output.

---

# SECTION B — IMPLEMENTATION SCOPE FOR THIS VERSION

This section defines **what must actually be implemented now**.

Anything not listed here is **out of scope for this version**.

---

## Core Model Components

### 1. Hydraulic Network Layer

Responsibilities:

• Represent device channel network  
• Compute local Po and Pw values  
• Determine Pj for each rung group

Initial implementation may be **quasi‑static**, with optional dynamic extension later.

---

### 2. Droplet Cycle Simulator

Runs for each rung group.

Inputs:

• local pressures (Po, Pw, Pj)  
• geometry parameters  
• fluid properties  
• critical radius Rcrit

---

### Stage 1 Algorithm

1. Apply instantaneous reset displacement (x = 0 at start of reset zone)
2. Obtain Po_local from hydraulic network (local oil pressure at rung inlet for Stage 1 flow)
   NOTE: Stage 1 now uses Po_local = P_oil(x) - P_water(x) for rung flow physics
   This is distinct from P_j (preneck junction pressure) used in Stage 2
3. Obtain P_water from hydraulic network (local continuous-phase pressure)
4. Compute capillary barrier: P_cap = γ cos(θ_eff) · (1/h + 1/w)
   where h = exit_depth, w = exit_width (junction exit dims — the reset zone)
5. Compute driving pressure: ΔP_drive = Po_local − P_cap
   NOTE: Po_local already accounts for local pressure difference (P_oil - P_water)
6. Integrate dx/dt = ΔP_drive · h² / [f(α) · (μ_oil · x + μ_water · (L_r − x))]
   from x = 0 to x = L_r
7. Refill time = integration time

Stage 1 duration = refill time.

Important: do NOT add upstream oil-column resistance inside the Stage 1 ODE. Po_local
already incorporates all upstream losses.

---

### Stage 2 Algorithm

1. droplet grows under local flow
2. monitor radius
3. stop when R = Rcrit

Record neck diagnostic values during growth.

---

### 3. Warning and Regime Detection Layer

This layer evaluates conditions that suggest leaving the monodisperse regime.

Possible checks include:

• neck capillary number threshold  
• pressure imbalance conditions  
• flow‑capacity limits

Important rule:

The warning layer **never overrides the Rcrit snap‑off condition**.

---

### 4. Device‑Level Simulation Loop

Simulation proceeds iteratively:

1. Solve hydraulic network
2. Partition rungs into groups
3. Run droplet‑cycle simulator for each group
4. Aggregate outputs
5. Update hydraulic loading if required
6. Repeat until convergence

---

# SECTION C — DEFERRED EXTENSIONS (NOT REQUIRED FOR INITIAL IMPLEMENTATION)

The following ideas remain valuable but **should not delay the baseline model**.

---

## Mechanism Selection Framework

Future versions may allow Stage 1 to switch between mechanisms:

• Washburn refill  
• adsorption‑limited refill  
• backflow refill  
• contact‑line dynamics

For now:

Washburn refill is the default model.

---

## Predictive Neck Instability

Future work may replace fixed Rcrit with predictive instability criteria based on:

• neck thinning dynamics  
• viscous scaling laws  
• capillary‑driven instability models

This is currently **diagnostic only**.

---

## Advanced Dispersed‑Phase Loading Feedback

Hydraulics may eventually incorporate feedback from droplet throughput.

Initial implementation may approximate this or ignore it.

---

## Design Optimization Layer

Future additions may include:

• automated parameter sweeps  
• device geometry optimization  
• throughput maximization routines

These are **analysis tools**, not part of the core simulator.

---

# SECTION D — RECOMMENDED IMPLEMENTATION ORDER

To minimize integration risk:

1. Implement Washburn Stage‑1 refill module
2. Implement Stage‑2 growth to Rcrit
3. Implement droplet‑cycle simulator
4. Implement grouped rung abstraction
5. Implement hydraulic network solver
6. Connect hydraulic iteration loop
7. Implement regime warning layer
8. Add validation tests

---

# SECTION E — OUT‑OF‑SCOPE FOR INITIAL IMPLEMENTATION

The following should **not block the first working version**:

• full mechanism auto‑selection
• predictive neck‑instability snap‑off
• full adsorption kinetics modeling
• full dynamic hydraulic network
• design optimization tools

---

# RESULT

This document defines the **baseline physics architecture** for the stage‑wise droplet model.

The goal of this version is **a stable, physics‑consistent baseline model**
that can later support additional mechanisms and refinements.

