## Issue 1 — Upstream Pressure Delivery / Hydraulic Network

**Decision**

V2 will retain a hydraulic network model as the upstream boundary-condition layer, but it will be implemented as a **dynamic reduced-order system** rather than a fully static backbone.

**Reasoning**

Droplet formation physics depends strongly on the pressure delivered to each junction.  
A dynamic reduced-order network allows testing whether junction conditions vary during a droplet cycle or across channels while avoiding unnecessary complexity.

**Impact if wrong**

Critical — incorrect boundary conditions would misattribute local droplet physics and reduce model transferability.


---

## Issue 2 — Definition and Role of Junction Pressure (Pj)

**Decision**

Define **Pj as a quasi-static upstream pressure located pre-neck at the junction**.  
The droplet bulb pressure is **post-neck**, and the **oil neck between them provides a hydrodynamic resistance**.

Stage 2 growth is driven primarily by decreasing bulb Laplace pressure while the neck simultaneously thins and increases resistance.

**Key physical relationship**

Pj − P_bulb = ΔP_neck

Where

P_bulb ≈ P_w + 2γ/R

**Implications**

- Bulb growth lowers Laplace pressure, increasing the driving pressure for inflow.
- Neck thinning increases flow resistance.
- The result may be modest change in volumetric flow but a rise in **local neck velocity** and therefore **local capillary number**.

**Interpretation of slightly oversized droplets**

Likely related to **neck dynamics or transitional regimes**, not changes in Pj.

**Impact if wrong**

High — incorrect pressure definitions would blur the distinction between supply pressure, neck transport physics, and droplet growth dynamics.

## Issue 3 — Stage 1 Reset and Refill Physics

**Decision**

Model Stage 1 as a **two-part process**:

1. **Fast reset / back-intrusion**  
   After Stage 2 ends, the continuous phase pushes the oil meniscus backward into the channel by an approximately fixed distance **L**.

2. **Refill / forward advance**  
   The oil meniscus then advances from this reset position back to the junction edge, and this refill step sets most of the measurable Stage 1 duration.

**Working interpretation**

- The reset distance can be approximated from geometry as a displaced volume:
  
  `V_reset ≈ exit_depth * exit_width * L`

- Based on current observations, **L** is roughly on the order of **exit_width** for the present device and operating regime.
- The reset event itself appears effectively instantaneous at the available time resolution.
- The refill step is slower and is the main contributor to Stage 1 time.

**What controls Stage 1 duration**

Stage 1 duration is primarily controlled by the **refill step**, which depends on the local oil supply conditions.  
Higher `Po` increases refill speed and therefore reduces Stage 1 time.

**Important correction to the simple model**

Although Stage 1 refill is pressure-driven, the refill flow through the rung should **not** be modeled as simple single-phase Poiseuille flow:

`Q = ΔP / R_single_phase`

This approach overpredicts the observed flow rate.

This implies additional physics are slowing refill, likely including:

- meniscus / capillary pressure effects
- moving-interface resistance
- wetting / contact-line effects
- local two-phase occupation of the rung

**V2 modeling approach**

## Issue 3A — Stage 1 timing model using two-fluid Washburn refill through the rung / microchannel

**Decision**

For V2, Stage 1 refill timing will be modeled using a **two-fluid Washburn-type moving-interface equation** for the oil–water meniscus traveling through the rung / microchannel after the reset event.

Rather than treating refill as simple single-phase Poiseuille flow or only as an empirical duty-factor correction, the refill step will be computed from the evolving meniscus position `x(t)`.

The governing form is:

\[
\dot{x}(t)
=
\underbrace{\gamma_{12}\cos\theta_{12}\left(\frac{1}{h}+\frac{1}{w}\right)}_{\text{capillary driving pressure}}
\cdot
\underbrace{\frac{w h^2}{f(\alpha)}}_{\text{channel geometry}}
\cdot
\underbrace{\frac{1}{\mu_1 x(t)+\mu_2\left(L_{\mathrm{tot}}-x(t)\right)}}_{\text{cumulative viscous resistance}}
\]

where:

- `x(t)` is the meniscus position measured along the rung / refill channel
- `L_tot` is the total refill length being considered
- `μ1` is the viscosity of the advancing fluid
- `μ2` is the viscosity of the displaced fluid
- `γ12` is the oil–water interfacial tension
- `θ12` is the effective contact angle relevant to the interface motion
- `h` and `w` are the channel height and width
- `f(α)` is the rectangular-channel resistance factor
- `α` is the channel aspect ratio

Stage 1 time is then obtained from the refill integral:

\[
t_{\mathrm{Stage1}}
=
\int_{x_0}^{x_f}
\frac{dx}{\dot{x}(x)}
\]

with `x0` the reset position after snap-off and `xf` the junction-edge / end-of-refill position.

---

**Why this choice was made**

The previous resolved Stage 1 discussion already concluded that refill should **not** be modeled as simple single-phase Poiseuille flow because that overpredicts the observed refill rate. This Washburn-style formulation provides a more physical intermediate model because it explicitly includes:

- a moving oil–water interface
- rectangular-channel geometry
- capillary driving pressure
- viscosity of both fluids
- changing hydraulic resistance as the interface moves

This gives V2 a Stage 1 model that is more physical than a pure empirical correction, while still remaining much simpler than a full CFD or phase-field treatment.

---

**Physical interpretation**

This model captures several important Stage 1 physics points:

### 1. Capillary pressure depends on both channel dimensions

The driving pressure scales with:

\[
\left(\frac{1}{h}+\frac{1}{w}\right)
\]

not a single `1/r` term.

This means both confinement dimensions matter directly in determining refill speed.

### 2. Rectangular channels have extra viscous resistance

The factor `f(α)` corrects for the rectangular velocity profile.

This means a real rectangular rung has higher resistance than an ideal slit-like approximation of the same height.

### 3. Resistance changes as the meniscus moves

The total viscous resistance is:

\[
\mu_1 x + \mu_2(L_{\mathrm{tot}}-x)
\]

So the refill dynamics depend on how much of the channel is currently occupied by each phase.

This means Stage 1 is inherently a **two-fluid moving-boundary problem**, not a constant-resistance refill.

### 4. Refill does not generally follow the single-fluid Washburn law

If `μ1 ≠ μ2`, then the denominator changes linearly with interface position, so the velocity is not generally proportional to `1/sqrt(t)`.

In particular:

- if the advancing fluid is **more viscous** than the displaced fluid, refill slows progressively
- if the advancing fluid is **less viscous** than the displaced fluid, refill may accelerate as the meniscus advances

This is an important qualitative difference from the standard single-fluid Washburn picture.

---

**How V2 should use this**

For the current device model, Stage 1 timing should be computed as follows:

1. determine the reset position `x0` after the fast back-intrusion event  
2. define the refill end position `xf` at the junction edge  
3. solve the Washburn refill equation for `x(t)`  
4. compute the refill time from `x0` to `xf`  
5. use that refill time as the dominant contribution to Stage 1 duration  

Operationally:

\[
t_{\mathrm{Stage1}} \approx t_{\mathrm{refill}}
\]

because the reset event itself is still assumed to be fast relative to the measured refill time.

---

**Modeling implications**

This changes the Stage 1 interpretation in an important way.

Stage 1 timing is no longer just:

- higher `Po` gives higher `Q`
- therefore shorter refill time

Instead, refill timing depends on the combined effect of:

- capillary pressure
- channel geometry
- both fluid viscosities
- meniscus position
- effective contact angle / wetting state

Conceptually:

\[
t_{\mathrm{Stage1}}
=
f(\gamma_{12}, \theta_{12}, \mu_1, \mu_2, h, w, L_{\mathrm{tot}}, x_0, x_f)
\]

This is a much more physically informative basis for predicting how Stage 1 changes when:

- oil viscosity changes
- water viscosity changes
- interfacial tension changes
- channel dimensions change
- wettability changes

---

**What this affects**

Within the intended monodisperse regime, this Stage 1 Washburn formulation is expected to affect:

- **droplet frequency strongly**
- **droplet volume weakly**, except indirectly if operation approaches a transition regime

The working interpretation remains:

- faster Stage 1 refill increases cycle frequency
- normal monodisperse droplet size is still primarily determined by Stage 2 / snap-off physics
- Stage 1 mainly controls how quickly the next cycle can begin

---

**Important assumptions**

This formulation is a useful V2 model only under the following assumptions:

- Stage 1 is dominated by meniscus refill through the rung / microchannel
- the reset event is fast compared with refill
- the interface remains well-defined during refill
- capillary-driven motion is the dominant refill mechanism
- dynamic contact-angle effects can be absorbed into an effective `θ12`
- no strong instability, breakup, or blowout occurs during Stage 1
- local pressure conditions during refill can be treated as quasi-static

---

**Use boundary**

This Stage 1 Washburn refill model is intended for the **normal monodisperse refill regime**.

It should be used cautiously or revised if:

- the interface becomes poorly defined
- contact-line pinning dominates
- surfactant adsorption kinetics strongly delay motion
- strong backflow alters the local pressure field
- local geometry causes major departures from the assumed refill path
- the system approaches transitional / blowout behavior

So this should be viewed as a **physics-based Stage 1 core model**, not yet a full universal description of all refill behaviors.

---

**Relationship to earlier Stage 1 discussion**

This decision updates the earlier Stage 1 conclusion in an important way:

- we still reject simple single-phase Poiseuille refill
- but instead of relying only on an empirical refill correction,
  V2 now has a physically structured refill law based on moving-interface Washburn dynamics

This gives a cleaner path for later refinement.

An empirical correction factor may still be retained if needed, but it should now be interpreted as a correction to the Washburn-based refill model, not a replacement for it.

---

**Impact if wrong**

High — if Stage 1 timing is governed by other mechanisms not captured here, such as strong contact-line pinning, adsorption-limited motion, or pressure-driven backflow effects, then frequency predictions and pressure-dependence trends will be misattributed.

However, this formulation is still a major improvement over simple Poiseuille refill because it explicitly accounts for the two-fluid moving-interface physics that Stage 1 must contain.

---

**Future refinement**

The following effects should be added later if experiments show they are important:

- dynamic contact angle rather than fixed effective `θ12`
- surfactant-dependent dynamic interfacial tension
- explicit pressure coupling to the hydraulic network through local `Pj`
- backflow-assisted or backflow-opposed refill
- geometry-specific corrections for non-uniform rung shapes
- direct fitting / validation against measured interface trajectories

Long-term goal:

replace a purely effective Stage 1 refill law with a validated moving-interface model that predicts refill timing directly from:

- fluid viscosities
- interfacial tension
- contact angle / wetting
- channel geometry
- local hydraulic boundary conditions



## Issue 4 — Stage 2 Growth and Snap-Off Model

**Decision**

Within the target monodisperse operating regime, Stage 2 will be modeled by assuming a **known critical droplet size** for the current fluid system and device geometry.

This means:
- the droplet grows during Stage 2 until it reaches the known monodisperse size
- the corresponding **critical radius** is treated as known
- once this critical radius is reached, snap-off is assumed to occur
- the cycle then resets

**Pressure picture**

Stage 2 growth is driven by the pressure difference between upstream oil and the bulb:

`ΔP_drive = Pj - P_bulb`

with

`P_bulb ≈ Pw + Laplace term`

and the changing part during growth is primarily the decrease in Laplace pressure as the bulb radius increases.

So as droplet radius increases:
- bulb pressure decreases
- driving pressure for oil inflow increases
- inflow tendency therefore increases

**Neck / flow picture**

At the same time:
- the neck width decreases
- the local flow path for oil narrows
- local oil velocity through the neck increases

So the Stage 2 picture should explicitly acknowledge:

- droplet radius increases
- driving pressure increases
- neck width decreases
- neck resistance effectively increases
- local neck velocity increases

Even if total volumetric flow does not increase dramatically, the shrinking neck area means local neck velocity can still rise significantly.

**V2 implementation view**

For the current model scope:
- assume monodisperse operation
- assume the normal droplet size is known for the tested fluid system and geometry
- use the known droplet size to define the snap-off point

At the same time, still calculate and track quantities such as:
- droplet radius increase during growth
- inflow increase tendency
- neck-width decrease
- local neck velocity increase

These tracked quantities can be used to build warning indicators for when the monodisperse assumption may begin to fail.

**Blowout / transition warning concept**

The current Stage 2 model is not intended to fully predict blowout.

Instead, V2 should evaluate warning-style indicators such as:
- unusually high local neck velocity
- unusually high effective neck capillary number
- failure of the neck to reach the expected snap-off condition within the normal growth window

These indicators can be used to flag when operating conditions may be approaching a transition away from normal monodisperse droplet formation.

**Why this choice was made**

This keeps the model practical and aligned with the current experimental goal:

- reproduce normal monodisperse droplet cycling for the tested system
- avoid overcomplicating V2 with a full instability model
- still retain enough evolving physics to support later refinement toward transition / blowout prediction

**Use boundary**

This Stage 2 formulation is intended only for the current experimentally tested fluid system and the normal monodisperse operating window.

If the fluid system, viscosity ratio, interfacial tension, or operating regime changes significantly, the critical droplet size assumption and warning logic should be revisited.

**Impact if wrong**

High — incorrect Stage 2 growth or snap-off assumptions would directly affect predicted droplet size, frequency, and confidence in regime-stability warnings.

**Future refinement**

Long-term, the fixed critical-radius assumption should be replaced or supported by a more physical instability criterion based on one or more of:
- critical neck width
- critical neck capillary number
- coupled neck-thinning instability
- regime-dependent snap-off / transition criteria....further exapliend: 

### Future refinement — Physical snap-off and regime transition criteria

Although V2 currently assumes a **known critical droplet radius (`R_crit`)** to trigger snap-off in the monodisperse regime, the underlying physical mechanism is believed to be related to **neck instability**, not droplet size alone.

Therefore, during Stage 2 the model should still track the evolving quantities that likely govern the true instability condition:

- **neck width (or neck radius)**
- **local oil velocity through the neck (`U_neck`)**
- **local neck capillary number**

  `Ca_neck = μ_o * U_neck / γ`

These quantities will not yet determine snap-off in V2 but will be **evaluated continuously during growth**.

The long-term objective is to replace the fixed `R_crit` assumption with a physically derived snap-off condition based on one or more of:

- **critical neck width**
- **critical neck velocity**
- **critical neck capillary number**

These quantities are expected to depend on:

- fluid viscosities
- interfacial tension
- wettability
- device geometry

Once sufficient experimental data are available, these relationships may allow the model to **predict droplet size directly from fluid properties and device geometry**, rather than requiring a pre-defined `R_crit`.

**Connection to blowout / regime transition**

Monitoring neck variables also provides a pathway to identify when the system leaves the ideal monodisperse regime.

For example, if the model predicts:

- droplet radius exceeding the normal `R_crit`
- while the neck has **not yet reached a critical instability condition**

then this suggests the system may be entering a **delayed snap-off / blowout-like regime**, where the bulb continues to grow while remaining attached.

Tracking these neck-state variables therefore provides a future mechanism for:

- detecting transition away from monodisperse operation
- predicting the onset of blowout conditions
- refining the snap-off model beyond the fixed-radius assumption.

The neck constriction is assumed not to significantly limit volumetric inflow during Stage 2; the dominant effect on inflow is the reduction of droplet Laplace pressure as radius increases. Neck narrowing mainly affects local velocity and instability indicators rather than the core inflow law.

## Issue 6 — What determines the monodisperse droplet size?

**Decision**

For V2, the monodisperse droplet size will continue to be treated as an **empirically determined quantity tied to the junction geometry and fluid system**, while the model tracks evolving neck-state variables that will later allow prediction of that size from first principles.

This means the model assumes a known `R_crit` (or droplet volume) for the current device and fluid pair, but also evaluates quantities that are likely related to the true instability condition.

**Physical interpretation**

The monodisperse droplet size corresponds to the moment when the droplet growth process reaches a **critical instability condition in the neck region**.

During Stage 2:

- droplet radius increases  
- Laplace pressure decreases  
- driving pressure increases  
- neck width decreases  
- local oil velocity in the neck increases  
- local neck capillary number increases  

Snap-off occurs when the system reaches a critical instability state.

In V2 this instability is represented operationally by the known droplet size (`R_crit`), but the underlying physics is believed to involve the **neck state**, not droplet size alone.

**Role of geometry**

Junction geometry plays a critical role in determining the monodisperse droplet size.

For example, two rungs with identical upstream conditions (`Pj`) but different junction exit geometries may produce different droplet sizes because the geometry sets different confinement conditions and therefore different neck instability points.

Therefore droplet size cannot be predicted from flow conditions alone.

Conceptually:

`R_crit = f(geometry, wetting, fluid properties)`

**Future predictive goal**

The long-term goal is to determine the snap-off condition using a **dimensionless instability criterion** based on neck dynamics.

The model will therefore track variables such as:

- neck width  
- local neck velocity `U_neck`  
- neck capillary number  

`Ca_neck = μ_o * U_neck / γ`

These quantities may eventually allow the snap-off condition to be expressed as a geometry-dependent critical relation such as:

`Ca_neck,crit = f(geometry, wetting, viscosity ratio)`

or another combined instability condition.

**Connection to blowout / regime transition**

Monitoring these neck-state variables also helps detect when the system leaves the monodisperse regime.

If droplet radius grows beyond the normal monodisperse size without reaching the expected neck instability condition, this indicates that the system may be entering a **delayed snap-off / blowout-like regime**.

**Impact if wrong**

Medium–High — misunderstanding what determines droplet size would limit the ability of the model to predict droplet size changes when geometry or fluid systems change.

**Future refinement**

With sufficient experimental data, the empirical droplet size assumption should be replaced with a predictive relation linking droplet size to:

- neck capillary number  
- junction geometry  
- fluid properties  

allowing the model to predict monodisperse droplet size without requiring prior calibration.

## Issue 7 — Treatment of continuous-phase pressure (`Pw`) across the device

**Decision**

`Pw` will **not be treated as globally constant**, but it will be treated as **locally quasi-static during a single droplet event** within a grouped rung simulation.

The hydraulic network model will determine how `Po` and `Pw` vary **along the device length**, and droplet simulations will be performed for **groups of rungs that share similar local hydraulic conditions**.

This avoids unnecessary computation while still capturing spatial variations in pressure across the device.

**Modeling interpretation**

Two scales are considered:

1. **Local droplet-event scale**

During Stage 2 growth for a given rung (or rung group):

- `Po` and `Pw` are treated as quasi-static
- the evolving term driving droplet growth remains the Laplace pressure change as the droplet radius increases

This preserves the simplified Stage 2 pressure balance used in earlier issues.

2. **Device-scale variation**

Across the length of the device:

- `Po` and `Pw` may vary due to hydraulic losses
- groups of rungs may therefore operate under slightly different local conditions
- grouped simulations will be used to capture this effect without simulating each rung individually

**Influence of dispersed-phase loading**

Droplet generation introduces oil droplets into the continuous-phase stream, which can potentially:

- increase effective water-side resistance
- alter local `Pw`
- change effective mixture viscosity
- introduce additional pressure drop due to droplet transport

These effects are expected to depend on:

- dispersed-phase fraction (oil fraction)
- droplet size
- droplet frequency
- channel geometry

**V2 modeling assumption**

For the initial model scope, the water-side hydraulic properties will be assumed **unchanged below a dispersed-phase loading threshold**.

However, this threshold will **not be hard-coded**.

Instead, a future module will estimate dispersed-phase loading dynamically.

**Future module: dispersed-phase loading feedback**

The model should eventually:

1. Use predicted droplet frequency and droplet size to estimate **oil fraction in the water stream**.
2. Estimate how this fraction alters:
   - effective viscosity of the mixture
   - hydraulic resistance of the water channels
3. Feed the updated resistance back into the **hydraulic network model**.

This may change the predicted local values of:

- `Po`
- `Pw`
- `Pj`

which would then influence droplet formation dynamics (Issues 4–6).

**Design-stage warning capability**

If dispersed-phase loading becomes large enough to significantly modify water-side resistance, the model should generate a **design warning** indicating that device operation may move outside the ideal monodisperse regime.

Possible suggested design responses may include:

- reducing target oil fraction
- increasing water channel dimensions
- reducing hydraulic resistance in continuous-phase channels
- adjusting operating conditions to reduce droplet loading

This allows the model to function not only as a prediction tool but also as a **design feedback tool**.

**Impact if wrong**

Medium — incorrect assumptions about continuous-phase pressure distribution could lead to inaccurate predictions of local droplet timing and device-scale uniformity, particularly at high dispersed-phase loading.

**Future refinement**

Introduce a dispersed-phase loading model linking:

- droplet size
- droplet frequency
- oil fraction
- mixture viscosity
- water-side hydraulic resistance

to dynamically update `Pw` within the hydraulic network model.

## Issue 8 — Interaction between neighboring droplet generators (rung coupling)

**Decision**

Rungs will be treated as **independent droplet generators**.  
No direct neighbor-to-neighbor dynamic coupling between droplet formation events will be modeled.

Differences in droplet behavior between rungs arise only from **device-scale hydraulic variations** in local pressures (`Po`, `Pw`) determined by the global hydraulic network.

**Physical interpretation**

Each rung forms droplets according to the same local physics:

- Stage 1 reset and refill
- Stage 2 bulb growth
- snap-off at the monodisperse critical condition

Because upstream hydraulic resistance dominates and droplet events are very fast, pressure perturbations from individual droplet events do not propagate strongly enough through the network to synchronize or influence neighboring rungs.

Therefore neighboring droplet generators operate **statistically independently**.

**Source of variation between rungs**

Any differences in droplet timing or operating conditions arise from **position-dependent pressures** along the device:

- local `Po`
- local `Pw`

These pressures vary gradually due to hydraulic losses along the oil and water channels and are computed using the hydraulic network model.

**Model implementation**

To avoid unnecessary computational cost:

- the device will be divided into **groups of rungs** with similar local hydraulic conditions
- a droplet formation simulation will be performed **once per group**
- results will be applied to all rungs within that group

This approach captures spatial variation across the device while avoiding the need to simulate every rung individually.

**When this assumption could fail**

Direct rung coupling could occur if:

- upstream hydraulic resistance becomes very low
- droplet loading becomes high enough to strongly modify water-side resistance
- pressure fluctuations propagate through the network
- droplet generators become synchronized

These conditions would likely appear experimentally as:

- synchronized droplet formation
- oscillating droplet frequencies
- irregular droplet spacing

No such behavior has been observed in the current system.

**Impact if wrong**

Low–Medium — if strong coupling existed, the grouped-rung assumption could underestimate spatial variability in droplet timing or size.

**Future refinement**

If experiments reveal synchronization or strong droplet interaction effects, the model could be extended to include dynamic coupling through the hydraulic network. For the current device and operating regime, this is considered unnecessary.

## Issue 9 — Detection of transition out of the monodisperse regime

**Decision**

V2 will use a **separate multi-factor warning system** to detect when operation may be moving out of the normal monodisperse regime.

This warning system will remain distinct from the core monodisperse snap-off model.

The monodisperse model will continue to assume normal droplet formation up to the expected `R_crit`, while the warning system evaluates whether that assumption is still safe to trust.

**Why this is needed**

The current model is designed to reproduce droplet formation within the stable monodisperse operating window.

However, the model also needs to indicate when operating conditions may be approaching:

- delayed snap-off
- oversized droplets
- transitional behavior
- blowout / jetting risk

Rather than trying to force one snap-off rule to cover both normal operation and failure modes, V2 will use a dedicated regime-warning layer.

**Warning variables to track**

The warning system should be based on calculated or predicted quantities such as:

- local `Pj` relative to capillary pressure scale
- predicted oil throughput relative to formation capacity
- local neck velocity `U_neck`
- local neck capillary number
- possible inertial indicators such as `We` or `Re` if needed
- whether droplet radius exceeds the expected normal monodisperse size without satisfying the expected breakup behavior

These variables provide a practical basis for warning of regime transition even before a full physical blowout model exists.

**How the warning system is used**

The purpose of the warning system is to classify operation into categories such as:

- stable monodisperse
- near transition
- transitional / oversized droplet behavior
- blowout / jetting risk

For now, these categories will be based on best-available predicted values rather than fully validated critical thresholds.

**Current limitation**

The exact critical values for these indicators are not yet known.

They are expected to depend on:

- device geometry
- neck geometry
- fluid viscosities
- interfacial tension
- wettability
- operating conditions

Therefore the initial warning system should be treated as a **design and trust-assessment tool**, not yet a final predictive regime boundary model.

**Future refinement**

As more experimental data become available, the model should be refined to identify:

- which warning variables are most predictive
- what critical values correspond to mono-to-transition and transition-to-blowout behavior
- how those critical values depend on geometry and fluid properties

This will eventually allow the warning system to evolve into a more predictive regime map for monodisperse operation and blowout onset.

**Impact if wrong**

High — without a good transition warning system, the model may appear trustworthy even when operating conditions have moved outside the regime where the monodisperse assumptions remain valid.
## Issue 10 — Simulation architecture: grouped rung cycles with hydraulic iteration

**Decision**

The model will use an **event-based droplet cycle simulation for representative rungs**, coupled iteratively with the **device-scale hydraulic network model**.

Rather than simulating every rung individually, the device will be divided into **groups of rungs with similar local hydraulic conditions**. A droplet-cycle simulation will be run for **one representative rung per group**, and the result will be scaled by the number of rungs in that group.

**Local droplet simulation (rung level)**

For each representative rung:

1. Stage 1 reset + refill time is computed.
2. Stage 2 droplet growth is simulated until `R = R_crit`.
3. Snap-off occurs.
4. Total cycle time is obtained.

From this cycle time the model computes:

- droplet frequency
- oil throughput per rung
- predicted droplet size
- neck state variables (`U_neck`, `Ca_neck`, etc.)
- regime warning indicators

These results are then multiplied by the number of rungs in that group to obtain group-level production.

**Device-scale hydraulics**

The hydraulic network model computes:

- local `Po`
- local `Pw`
- resulting `Pj` conditions

for each rung group based on channel resistances and flow distribution across the device.

**Iterative coupling**

Because droplet production influences the hydraulic state of the device, the model will iterate between the droplet model and the hydraulic model until convergence.

The iterative loop follows the structure:
Solve hydraulic network → estimate local Po and Pw

Run droplet model for each rung group

Compute droplet frequency, oil throughput, oil fraction

Update hydraulic network with new loading conditions

Recompute Po and Pw

Repeat until convergence

Convergence is reached when key quantities stabilize, such as:

- local pressures (`Po`, `Pw`)
- droplet frequency
- predicted oil fraction

**Advantages of this architecture**

- avoids simulating every rung individually (which could number in the thousands or more)
- preserves local droplet physics where it matters
- captures device-scale feedback through the hydraulic network
- allows efficient design exploration and parameter sweeps

**Impact if wrong**

Medium — if grouping assumptions are too coarse or hydraulic coupling is stronger than expected, the model could underpredict spatial variability in droplet production across the device.

**Future refinement**

Future versions of the model may include:

- adaptive grouping of rungs based on hydraulic gradients
- improved convergence strategies (e.g., relaxation methods)
- tighter coupling between droplet production and water-side resistance changes due to dispersed-phase loading.

## Issue 11— Unknown interfacial properties (γ, θ) and critical neck state

### Decision

Several key interfacial quantities in the model are currently **unknown or only partially observable**, including:

- interfacial tension (γ₁₂)
- contact angle between fluids and channel wall (θ₁₂)
- critical neck geometry at snap-off
- critical capillary number for neck collapse

For V2 these quantities will be treated as **effective parameters** rather than known physical constants.

Where possible, approximate values may be **back-calculated from experimental observations**, particularly:

- Stage 1 refill timing
- observable neck width before snap-off
- observable interface geometry

These inferred values should be treated as **best estimates consistent with current data**, not definitive material properties.

Users of the model should be encouraged to **re-evaluate these estimates whenever new experimental measurements become available.**

---

### Contact angle and interfacial tension

The Stage 1 refill model contains a capillary driving term proportional to:

γ₁₂ · cos(θ₁₂)

At present:

- channel geometry is known
- viscosities are known
- refill time can be measured experimentally

This means experimental Stage 1 timing may allow **back-calculation of an effective capillary driving pressure**, which can be interpreted as:

γ_eff · cos(θ_eff)

This provides a practical way to estimate plausible values for:

- effective interfacial tension
- effective contact angle
- or their combined capillary pressure contribution

Any such values should be considered **effective model parameters**, not true equilibrium wetting properties.

---

### Apparent contact angle from imaging

If the oil–water interface is visible inside the microchannel, it may be possible to estimate an **apparent interface angle** from experimental images.

However this angle will likely be:

- a **dynamic angle**
- measured in **confined microchannel geometry**
- affected by limited imaging resolution

Therefore any measured angle should be interpreted as an **apparent effective angle** suitable for model calibration rather than a fundamental wetting property.

---

### Neck collapse and critical capillary number

The exact neck collapse condition during droplet snap-off is currently unknown.

High-speed imaging shows the neck thinning before breakup, but due to frame-rate limits:

- the final collapse occurs between frames
- the observed neck width is therefore an **upper bound**
- the true critical neck radius is likely smaller

Because of this limitation, the model cannot currently determine the **true critical neck state**.

However it may still be possible to estimate an **apparent capillary number near snap-off**, defined conceptually as:

Ca ≈ μ_d · U_neck / γ

where:

- μ_d is dispersed phase viscosity
- U_neck is the neck velocity just before breakup
- γ is interfacial tension

This value should be interpreted as an **observed pre-collapse capillary number**, not necessarily the true instability threshold.

---

### Modeling implication

For V2:

- droplet size in the stable regime remains primarily empirical
- Stage 1 timing may help constrain effective capillary parameters
- neck geometry and neck velocity should be recorded as diagnostic indicators

These quantities may later help identify:

- snap-off conditions
- transition to blow-up regimes
- geometry or fluid-dependent stability limits

---

### Future refinement

Additional experimental data should be used to improve estimates of:

- interfacial tension
- contact angle
- neck thinning dynamics
- capillary number at breakup

Users should therefore be encouraged to periodically **re-evaluate assumed values for:**

- contact angle
- interfacial tension
- capillary number estimates
- neck geometry indicators

as new experimental measurements become available.
