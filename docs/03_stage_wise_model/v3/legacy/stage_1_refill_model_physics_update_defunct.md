> **DEFUNCT — March 2026**
> This document resolved the Washburn vs Poiseuille question in favour of a
> network-driven two-fluid Washburn ODE through the junction exit. That approach
> has since been superseded: the Washburn ODE through the 15 µm exit predicts
> ~0.2 ms at 200–300 mbar (orders of magnitude too fast). The current model uses
> simplified Poiseuille `t = C_visc × V_reset / (P_j / R_rung)`. See
> `stage_wise_v3_implementation_plan.md` progress log (March 15 2026) and
> `stage1_slowdown_mechanisms_research.md` for the current basis.

---

# Stage 1 Meniscus Refill – Pressure and Resistance Model

## Purpose

This note clarifies how **Stage 1 refill** should be modeled in the droplet cycle and resolves confusion between:

- Poiseuille flow
- Washburn-type interface motion
- Hydraulic network pressures already computed upstream

The goal of Stage 1 is to determine:

**How long it takes the oil–water meniscus to move through the reset zone after snap-off and clear the small volume of water that intrudes into the channel.**

---

# 1. Physical Picture of Stage 1

After a droplet snaps off:

1. The outlet side contains water.
2. A short **reset zone** of length `L_r` inside the channel contains water.
3. Upstream of that region the channel is already filled with oil.
4. Oil must push the interface forward until it reaches the step again.

So at any moment:

[ upstream oil column ] --- meniscus --- [ water in reset zone ] → outlet

Definitions:

- `x` = distance the oil has advanced inside the reset zone  
- `L_r` = total reset zone length

---

# 2. Pressures in the System

Three pressures matter for Stage 1.

## Oil pressure from the hydraulic network

The hydraulic network solver already computes the oil pressure field.

Define

P_oil(x)

= oil pressure at the meniscus location.

This pressure already includes **all upstream oil-column resistance**.

Therefore:

**Upstream resistances must NOT be added again in Stage 1.**

---

## Water pressure downstream

Define

P_water

= pressure in the downstream water phase.

Often this is near outlet pressure.

---

## Capillary pressure at the interface

A curved oil–water interface creates a pressure jump described by the **Young–Laplace equation**:

P_cap = γ (1/R₁ + 1/R₂)

For a rectangular channel this is often approximated as:

P_cap ≈ γ cosθ (1/h + 1/w)

where

- γ = interfacial tension  
- θ = contact angle  
- h = channel height  
- w = channel width

This pressure must be overcome for the interface to move.

---

# 3. Driving Pressure for the Meniscus

The pressure available to push the interface forward is

ΔP_drive(x) = P_oil(x) − P_water − P_cap

If

ΔP_drive > 0

the meniscus advances.

If

ΔP_drive < 0

the interface retreats.

Increasing inlet oil pressure increases P_oil(x), which increases ΔP_drive and therefore speeds refill.

---

# 4. Hydraulic Resistance of the Reset Segment

The refill region contains two fluids.

The hydraulic resistance of that short segment is

R_reset(x) = f(α)/(w h³) [ μ_o x + μ_w (L_r − x) ]

where

- μ_o = oil viscosity  
- μ_w = water viscosity  
- f(α) = rectangular channel correction factor

As oil replaces water, this resistance changes with x.

---

# 5. Flow Rate Through the Reset Segment

Using Poiseuille flow:

Q(x) = ΔP_drive(x) / R_reset(x)

---

# 6. Meniscus Velocity

The interface speed follows from the flow rate:

dx/dt = Q(x) / (w h)

Substituting:

dx/dt =
( P_oil(x) − P_water − P_cap )
--------------------------------
w h · R_reset(x)

This is effectively a **pressure-driven Washburn-type equation**, but expressed using the network pressure instead of assuming purely capillary driving.

---

# 7. Relationship to Classic Washburn

Classic Washburn assumes the only pressure driving the interface is capillary pressure:

ΔP_drive = P_cap

In the droplet generator this is not true because the hydraulic network supplies additional oil pressure.

Therefore Stage 1 is better described as:

**Network-driven Poiseuille flow through a short two-fluid segment with a capillary pressure barrier.**

Washburn behavior appears naturally because the resistance of the segment varies with meniscus position.

---

# 8. Important Implementation Rule

Because P_oil(x) already includes upstream pressure losses:

**DO NOT add upstream oil-column resistance again in Stage 1.**

Stage 1 should only model the **local reset zone physics**.

---

# 9. Recommended Stage-1 Implementation

1. Obtain oil pressure from the hydraulic network

   P_oil(x)

2. Use downstream water pressure

   P_water

3. Compute capillary pressure

   P_cap

4. Compute reset-zone resistance

   R_reset(x)

5. Compute flow and meniscus speed

   Q(x) = (P_oil(x) − P_water − P_cap) / R_reset(x)

   dx/dt = Q(x) / (w h)

6. Integrate

   x = 0 → L_r

to obtain the Stage-1 refill time.

---

# 10. Suggested Location in the Project

Add this document near the droplet physics code.

Recommended path:

docs/physics/stage1_refill_model.md

This should be referenced from:

- the Stage-1 solver
- droplet physics documentation
- derivation notes explaining the refill timing model

This ensures future contributors understand why Stage 1 uses **network pressure + interface physics** instead of a simple Poiseuille or pure Washburn model.