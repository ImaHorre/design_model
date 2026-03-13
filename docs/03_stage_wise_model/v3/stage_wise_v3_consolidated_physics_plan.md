
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

Pj = upstream pressure located **immediately before the neck region**.

Bulb pressure exists **downstream of the neck**.

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

Stage 1 consists of two processes:

1. **Fast reset / back‑intrusion**
2. **Slower refill of dispersed phase**

The fast reset is effectively instantaneous relative to refill time.

Therefore:

t_stage1 ≈ t_refill

### Baseline refill physics

Refill is modeled using a **two‑fluid Washburn moving‑interface model**.

Single‑phase Poiseuille refill is **not used** as the baseline model because it
systematically overpredicts refill speed.

Optional alternate mechanisms (not required initially):

• dynamic contact‑line effects  
• adsorption‑limited refill  
• backflow‑dominated refill

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

1. apply instantaneous reset displacement
2. integrate Washburn refill model
3. compute refill time

Stage 1 duration = refill time.

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

