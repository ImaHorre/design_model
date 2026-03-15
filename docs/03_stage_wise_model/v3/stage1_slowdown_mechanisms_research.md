# Stage 1 Refill: Candidate Slowdown Mechanisms — Research Notes

Date: March 2026
Status: Research / pre-implementation background
Purpose: Guide experimental investigation and future model extension

---

## Context

The simple Poiseuille estimate for Stage 1 refill:

```
t ≈ V_junction / Q_rung
  = (L_r × exit_width × exit_depth) / (P_j / R_rung)
```

With corrected geometry (rung: mcd=10µm, mcw=8µm, L=4mm; junction exit: 15µm × 10µm;
L_r ≈ 15µm) and Po ≈ 200–300 mbar, this predicts **t ≈ 0.25–0.30 s**.

Experimental observation: **t ≈ 1 s** at those pressures.

The discrepancy is approximately **3–4×**. This document catalogues the physical mechanisms
that could account for this gap, what each predicts, how to distinguish them experimentally,
and what the implementation would require.

---

## Baseline reminder: what the model currently assumes

- Oil is a Newtonian fluid (bulk viscosity μ_oil ≈ 0.06 Pa·s vegetable oil)
- Water is a Newtonian fluid (μ_water ≈ 0.001 Pa·s)
- The oil–water interface is sharp, with no internal structure
- Contact angle is fixed (no dynamics)
- The rung delivers flow Q = P_j / R_rung unimpeded
- No resistance at the interface itself

All five assumptions are questionable in a surfactant-laden microfluidic system.

---

## Mechanism 1: Surface viscosity / Marangoni stress at the fresh oil–water interface

### Physical description

When the neck snaps and a new oil–water interface is created, the SDS surfactant
layer at that interface is initially absent or depleted. A clean (or depleted) oil–water
interface under SDS has a **surface viscosity** — resistance to deformation within the
interfacial plane — that can be 10–100× larger than a fully equilibrated interface.

As the fresh meniscus advances through the junction, the interface must deform and
stretch. If surface viscosity is significant, this acts as an additional viscous resistance
localised at the interface, not captured by bulk μ_oil or μ_water.

### Scaling

The Boussinesq–Scriven model for surface viscosity contribution to channel flow
introduces an additional resistance proportional to:

```
R_surface ≈ η_s / (h × w²)   [Pa·s/m³]
```

where η_s is the surface shear viscosity [Pa·s·m = N·s/m].

For SDS systems, η_s at a fresh interface can be O(10⁻⁶) to O(10⁻⁵) N·s/m.

With h=10µm, w=15µm:
```
R_surface ≈ 1e-5 / (10e-6 × (15e-6)²) ≈ 4.4×10¹² Pa·s/m³
```

This is much smaller than R_rung (≈ 2.7×10¹⁸), so surface viscosity at the
junction exit alone is **unlikely to contribute meaningfully** unless the interface
traverses a much longer path.

However, if the fresh interface extends back through the rung length (~mm), the
cumulative surface viscosity resistance scales with distance and could become
non-negligible.

### How to test experimentally

- Vary SDS concentration: if this mechanism is active, higher SDS → faster
  equilibration → lower surface viscosity → faster Stage 1
- Measure Stage 1 time vs SDS concentration at fixed Po — a non-monotonic or
  concentration-dependent response implicates surface viscosity

### Implementation complexity: Medium
Requires η_s(t, [SDS]) model or a lumped correction factor.

---

## Mechanism 2: Dynamic contact angle and contact line resistance

### Physical description

The oil meniscus advancing through the junction exit moves on a wetted wall. Even in
a nominally hydrophilic channel, the dynamic contact angle θ_d differs from the
equilibrium angle θ_eq when the contact line moves.

The Cox–Voinov law gives:

```
θ_d³ ≈ θ_eq³ + 9 Ca ln(L/λ)
```

where:
- Ca = μ U / γ  (capillary number, U = meniscus velocity)
- L  = macroscopic length scale (channel width, ~15µm)
- λ  = molecular cutoff length (~1 nm)

As U increases, θ_d increases, which in a hydrophilic system reduces the capillary
driving force (or increases the barrier if θ_d approaches 90°).

Alternatively, contact line pinning at geometric features (rung–junction interface,
corners) can arrest the meniscus temporarily, creating apparent slowdown.

### Scaling

For the advancing meniscus at U ~ L_r / t ~ 15µm / 1s = 15 µm/s:
```
Ca = 0.06 × 15e-6 / 15e-3 ≈ 6×10⁻⁵
```

This is very low Ca, so Cox–Voinov correction is small (~few percent). Contact angle
dynamics are **unlikely to be the primary cause** at these velocities.

However, if Stage 1 involves the contact line traversing the rung–junction step
(a geometric discontinuity), pinning could add a threshold delay of O(10–100 ms).

### How to test experimentally

- Image the meniscus directly: if pinning is present, the meniscus stalls visibly
  at geometric features before jumping forward
- Compare channels with rounded vs sharp rung–junction transitions

### Implementation complexity: Low–Medium
Cox–Voinov is analytically tractable; pinning threshold requires empirical calibration.

---

## Mechanism 3: Adsorption kinetics — SDS depletion at the fresh interface

### Physical description

When snap-off creates a new oil–water interface, SDS molecules must diffuse from
the bulk water to the fresh surface to re-establish the equilibrium monolayer.
Until the layer is established:

1. Interfacial tension γ is higher than equilibrium (cleaner interface → higher γ)
2. A higher γ means a larger capillary barrier P_cap = γ cos(θ) (1/h + 1/w)
3. This reduces ΔP_drive and slows the meniscus

This is a **transient** effect: it decays as SDS adsorbs, so Stage 1 would start slowly
and accelerate as the interface equilibrates.

### Scaling

The adsorption timescale for diffusion-limited SDS adsorption is:

```
t_ads ≈ (Γ_eq / c_bulk)² × π / (4 D)
```

where:
- Γ_eq ≈ 3×10⁻⁶ mol/m²  (equilibrium surface excess)
- c_bulk ≈ 1–10 mM  (typical SDS concentrations)
- D ≈ 4×10⁻¹⁰ m²/s  (SDS diffusivity)

For c = 3 mM = 3 mol/m³:
```
t_ads ≈ (3e-6 / 3)² × π / (4 × 4e-10) ≈ 1e-12 × π / 1.6e-9 ≈ 2 ms
```

At typical SDS concentrations above CMC, adsorption is fast (ms). This is likely
**too fast** to explain a 1 s Stage 1 unless the local SDS concentration near the
fresh interface is severely depleted by prior droplet formation.

Below CMC or in micelle-limited conditions, adsorption could be much slower
(100 ms–seconds scale).

### How to test experimentally

- Vary SDS concentration above and below CMC and observe Stage 1 time
- Below CMC → adsorption limited → Stage 1 much slower
- Above CMC → fast adsorption → Stage 1 approaches Poiseuille baseline
- A step-change in Stage 1 time near the CMC is a diagnostic signature

### Implementation complexity: High
Requires coupling an adsorption ODE to the meniscus motion ODE.

---

## Mechanism 4: Water backflow resistance through the exit channel

### Physical description

As oil enters the junction from one side, water must exit from the other side
(downstream). If the exit channel has significant resistance, a pressure builds
up ahead of the advancing oil meniscus that opposes its motion — effectively
adding a backpressure term.

This is the reverse of the forward problem: the same channel geometry that
controls P_j also controls how quickly water can escape.

### Scaling

In a symmetric device where the exit resistance R_exit ≈ R_rung / 585 (from
the earlier calculation), this would contribute only ~0.2% additional backpressure
and is negligible.

However, if the exit is partially blocked (e.g., a droplet has not fully cleared
the junction), backpressure could be significant — O(1×) the driving pressure.

### How to test experimentally

- Observe whether Stage 1 duration correlates with whether the previous droplet
  has fully exited the junction at the time Stage 1 begins
- Compare high-frequency (queue of droplets) vs low-frequency (droplets well separated)
  conditions — backflow effect would increase at high frequency

### Implementation complexity: Low
Can be added as a pressure-correction term to P_j if exit resistance is characterised.

---

## Mechanism 5: Effective viscosity higher than bulk oil

### Physical description

Vegetable oil is not a pure Newtonian fluid. It is a mixture of triglycerides with
some natural surfactant-like components. At microchannel scales (h ≈ 10 µm), the
continuum assumption begins to break down for complex fluids.

Additionally, during Stage 1 the oil–water interface is fresh and the SDS layer
incomplete. The interface can support stress differently than at equilibrium,
effectively making the two-fluid column more viscous than expected from bulk values.

A lumped effective viscosity μ_eff = C × μ_oil (with C = 3–5) would explain the
observed slowdown without introducing new mechanisms.

### How to test experimentally

- Measure Stage 1 time as a function of Po over a wide range (50–500 mbar)
  and check whether t ∝ 1/Po (Poiseuille scaling) is obeyed
- If t ∝ 1/Po with a consistent prefactor, this is a simple viscosity correction
- If the scaling deviates from 1/Po, a more complex mechanism is required

This is the **first test to run** — it distinguishes a simple constant multiplier
(mechanism 5) from pressure-dependent effects (mechanisms 1–4).

### Implementation complexity: Trivial
A single calibration factor C multiplying μ_oil (or equivalently, a correction factor
on R_rung).

---

## Summary table

| Mechanism | Expected slowdown | Po-dependence | SDS-dependence | Implementation |
|---|---|---|---|---|
| Surface viscosity at interface | 1–5× if long interface path | Weak | Yes — higher [SDS] → less | Medium |
| Dynamic contact angle (Cox–Voinov) | <10% at these Ca | None | Weak | Low |
| Contact line pinning at geometry | 0 or step-change delay | None | Weak | Low (threshold) |
| SDS adsorption kinetics | 1–10× depending on [SDS] vs CMC | None | Strong — step at CMC | High |
| Water backflow | Negligible normally | Weak | None | Low |
| Effective viscosity (bulk correction) | 3–5× (matches gap) | 1/Po scaling preserved | None | Trivial |

---

## Recommended experimental sequence

1. **Measure t_stage1 vs Po** at fixed SDS concentration (above CMC).
   - If t ∝ 1/Po: mechanisms 1–4 are subdominant. Use a viscosity prefactor.
   - If t ∝ 1/Po^n with n ≠ 1: pressure-dependent mechanism is active.

2. **Measure t_stage1 vs [SDS]** at fixed Po.
   - Sweep from below CMC to above CMC.
   - A strong dependence below CMC → adsorption kinetics (mechanism 3).
   - A weak dependence → mechanisms 1 or 5.

3. **High-speed imaging** of the meniscus during Stage 1.
   - Does the meniscus advance smoothly or does it stall/pin?
   - What is the actual advance distance (is L_r really ≈ 15 µm or larger)?
   - This answers the L_r question definitively.

4. **Compare single-droplet vs high-frequency** operation.
   - If Stage 1 is longer when a queue of droplets is present → mechanism 4.

---

## Key open question for the model

The biggest unknown is whether the Poiseuille scaling (t ∝ 1/Po) is actually
obeyed experimentally. If yes, the correct implementation is:

```
t_stage1 = C × V_junction / (P_j / R_rung)
```

where C is a single calibration constant (likely 3–5) that lumps all interface
and viscosity effects. This is simple, defensible, and directly fitted to experiment.

If the scaling is not 1/Po, then the model needs an explicit mechanism from
mechanisms 1–4, which are substantially more complex to implement correctly.

---

## Notes for future implementation session

- Mechanism 5 (viscosity prefactor): add `stage1_viscosity_correction` field to
  `StageWiseV3Config` defaulting to 1.0; multiply μ_oil by this factor in the ODE.

- Mechanism 3 (adsorption): needs a new ODE for Γ(t) coupled to the meniscus ODE;
  γ(t) computed from Γ via Gibbs adsorption isotherm.

- The Washburn ODE framework in `stage1_physics.py` is structurally correct for
  mechanisms 5 and 3. The geometry fix (using rung h/w in the ODE if L_r > exit)
  is a separate, independent change.

- Before any mechanism is added: confirm L_r experimentally. If L_r >> 15 µm
  (meniscus retreats significantly into the rung), the geometry in the ODE must
  change first — the mechanism corrections come after.
