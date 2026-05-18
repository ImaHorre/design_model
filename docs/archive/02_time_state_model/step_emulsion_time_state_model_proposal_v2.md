# Step/EDGE Emulsification Hydraulic Discrepancy  
## Why the current ladder model overpredicts droplet frequency (×5–6) while droplet size matches

**Context:** You provided two files:

- `hydraulic_model_analysis.md` — a detailed description of the current ladder-network model (“stepgen”).
- `hydraulic_discrepancy_investigation.md` — an observed mismatch: **predicted droplet diameter matches experiment**, but **predicted droplet frequency (and rung oil flow)** is **~5–6× higher** than measured at the same \((Q_\mathrm{water}, P_\mathrm{oil})\).

This document consolidates:

1) The key points from the model + discrepancy notes  
2) Our subsequent discussion (your observations + my feedback, incl. tubing, capillary threshold, etc.)  
3) A deep “time-state” theory for droplet cycling (growth → pinch → reset)  
4) A programmer-facing implementation guide to add this as a feature in the codebase  
5) A layered roadmap to compare **four** model versions: current, duty-factor, time-state, time-state+filling mechanics

---

## 1. What the current model actually does (and what it *does not* do)

### 1.1 Ladder-network hydraulics: steady flows through fixed resistors

The model represents the device as two 1D “rails” (oil and water) coupled by “rungs” (the DFUs / microchannels). It builds and solves a linear system enforcing flow balance at each node.

A key implementation detail (steady solve): rung flows are computed by:

```python
# _simulate_pa()
Q_rungs = g_rungs * (P_oil - P_water) + rhs_oil
```

This is a linear relation in the purely resistive case, with an offset term used to represent capillary thresholds.

### 1.2 Capillary threshold is implemented as a *static* offset + regime classification

The model introduces a three-state rung regime:

```python
class RungRegime(enum.Enum):
    ACTIVE  = "active"   # ΔP > dP_cap_ow → oil → water
    REVERSE = "reverse"  # ΔP < -dP_cap_wo → water → oil
    OFF     = "off"      # |ΔP| below threshold → pinned
```

A capillary activation threshold is treated as a static pressure barrier (config input; you used ~50 mbar in the model), commonly estimated using:

\[
\Delta P_\mathrm{cap} \sim 2\gamma \left(\frac{1}{w_\mathrm{exit}}+\frac{1}{d_\mathrm{exit}}\right)
\]

and the solver implements it (for ACTIVE rungs) by injecting a fixed RHS offset proportional to \(-g_0\,\Delta P_\mathrm{cap}\), i.e., an effective subtraction from \(\Delta P\).

### 1.3 Droplet frequency is not simulated — it is inferred from steady flow

Droplet volume is computed (sphere approximation), then **frequency is computed algebraically**:

```python
def droplet_frequency(Q_rung, D):
    return Q_rung / droplet_volume(D)  # f = Q / V_d
```

**Key point:** the current model has no time, no cycle, no pinch-off dynamics.  
It assumes that a steady volumetric flow through the rung is continuously converted into identical droplets.

That assumption can fail if the real DFU is “stop–go” over its cycle.

---

## 2. What you measured

From `hydraulic_discrepancy_investigation.md` (baseline example):

- **Baseline:** \(P_o = 400\) mbar, \(Q_w = 1.5\) mL/hr  
- **Measured:** \(f_\mathrm{exp} \approx 2.6\) Hz, \(D_\mathrm{exp} \approx 12\) µm  
- **Predicted:** \(f_\mathrm{pred} \approx 14.6\) Hz, \(D_\mathrm{pred} \approx 12\) µm  
- **Mismatch:** ratio ≈ **5.6×**

The discrepancy doc states explicitly:

> “The 5.6× discrepancy in droplet frequency is entirely hydraulic — Q_rung is overestimated 5.6×.”

---

## 3. Candidate causes of a 5–6× hydraulic overprediction (diameter right, frequency wrong)

### 3.1 Rung resistance underestimated (device more resistive than modeled)

Potential contributors:

- **Depth smaller than assumed** (cube law: \(R \propto d^{-3}\))  
- Effective hydraulic height reduced by rounding, residue, partial collapse, swelling, etc.  
- Entrance/exit losses not captured by pure rectangular Poiseuille  
- **Two-phase / partial-occlusion effects** near the DFU exit that increase *effective* resistance

### 3.2 Capillary activation threshold \(P_\mathrm{cap}\) higher than the model assumes

From our discussion:

- You observe “near no droplet production” at ~100 mbar, with oil filling to the junction and holding.
- That suggests an activation barrier closer to **100–150 mbar** than ~50 mbar.

The current ACTIVE rung relation is effectively:

\[
Q \approx \frac{\Delta P - P_\mathrm{cap}}{R}
\]

so increasing \(P_\mathrm{cap}\) reduces predicted rung flow linearly (for rungs that remain ACTIVE). This can shrink the mismatch but often won’t create a full 5–6× correction alone unless \(P_\mathrm{cap}\) is very large relative to \(\Delta P\).

### 3.3 Plumbing restriction (possible, but your specific tubing is unlikely to be the main culprit)

Your setup:

- Inlet/outlet tubing: **1/32 inch diameter**, **~30 cm** long
- **All rungs active** experimentally

Feedback:

- If 1/32" is truly ~0.8 mm ID, bulk tubing resistance is usually small compared to hundreds of mbar device drops at microfluidic flows.
- However, a *single choke point* (needle, ferrule constriction, microbore segment, filter, partially blocked connector) can dominate.

Net: tubing alone is unlikely to explain 5–6×, but rule out a hidden restriction.

### 3.4 The best symptom match: the model assumes continuous flow, but the real DFU is a stop–go cycle

Your summary (core insight):

> “Right now the model doesn’t know it’s making drops; it just has a high resistance node that fluid travels through and therefore the flowrate is inherently constant. Whereas we know it is in fact making droplets on a cycle so during that phase there is a no-flow time (that the model doesn’t account for).”

If the DFU is effectively “open” only ~15–20% of the time and “blocked / high impedance” for the rest, the **time-averaged throughput** can be 5–6× lower while droplet volume (hence diameter) stays the same.

---

## 4. Notes from our conversation (your observations + my feedback)

### 4.1 Your experimental clarifications

- **All rungs are active** in the experimental version.
- Tubing: **1/32 inch diameter**, **~30 cm** inlet/outlet.
- Activation: **near no droplet production at ~100 mbar**, with oil filled close to the junction and holding.

### 4.2 Implications

- Tubing likely small resistance unless hidden restriction exists.
- Higher \(P_\mathrm{cap}\) reduces predicted flow because the model uses \((\Delta P - P_\mathrm{cap})/R\) once ACTIVE.
- A static capillary threshold + static resistance cannot represent cycle-dependent stall time.

---

## 5. What is actually happening physically (low-order theory, not CFD)

You described the cycle as:

1) After pinch-off, the meniscus **retreats** into the DFU channel  
2) The meniscus **advances** to the junction (pushing continuous phase ahead)  
3) The droplet **balloons** while connected to the feed thread  
4) A **neck forms** and thins to breakup  
5) Meniscus snaps back and repeats

That picture is consistent with how we should model frequency: **frequency is set by cycle time**, not by steady flow alone.

### 5.1 Replace static “rung resistor” with a nonlinear element with internal state

A useful conceptual replacement:

\[
Q(t) = \frac{\Delta P(t) - P_\mathrm{cap}(x(t))}{R(x(t))}
\]

where \(x(t)\) is a low-dimensional internal state representing progress through the cycle.

### 5.2 Duty-cycle gating (the simplest reduced model)

Represent the DFU as phase-switching conductance:

- OPEN / GROW: \(g=g_0\)  
- PINCH / BLOCKED: \(g=g_\mathrm{pinch}\ll g_0\)  
- RESET: optionally intermediate \(g\)

Then:

\[
Q(t)=g(\text{phase})\,[\Delta P(t)-P_\mathrm{cap}(\text{phase})]
\]

and droplet events are determined by time integration rather than \(f=Q/V_d\).

### 5.3 Why “diameter right, frequency wrong” naturally appears

If the droplet volume per event is set by geometry/capillarity (so size matches), but there is a significant fraction of time where the DFU is blocked/high-impedance, then time-averaged throughput drops → frequency drops.

A simple approximation:

\[
\overline{Q}\approx \phi\,Q_\mathrm{open}
\]

where \(\phi\) is the “open fraction” (duty factor). Your baseline mismatch suggests \(\phi\approx 0.17\)–0.20.

### 5.4 Additional cycle-volume mechanics (refill distance and in-channel droplet volume)

Your updated mechanistic understanding adds two *cycle-volume* effects that can materially reduce droplet frequency without changing the observed droplet diameter:

#### A) Refill (meniscus retreat + re-advance) requires “non-droplet” pumped volume each cycle

After pinch-off, the oil meniscus retreats upstream inside the DFU channel by a distance \(L_r\). Before the next droplet can balloon, the meniscus must advance back to the junction. That implies a per-cycle refill volume:

\[
V_\mathrm{refill} = A_\mathrm{DFU}\,L_r
\]

Even if the open-phase hydraulics set an “instantaneous” open flow \(Q_\mathrm{open}\), refill adds time:

\[
T_\mathrm{refill} \approx \frac{V_\mathrm{refill}}{Q_\mathrm{open}}
\]

So the cycle time is not only \(V_d/Q_\mathrm{open}\); it includes this extra pumped volume.

#### B) Effective droplet volume is not necessarily only the “external sphere”

Breakup can occur at a neck location *inside* the DFU channel, a distance \(L_\mathrm{break}\) from the junction exit plane. Oil on the droplet side of the pinch plane—including oil still residing in the channel on the downstream side—becomes part of the droplet volume at detachment.

A simple first-order correction is:

\[
V_{d,\mathrm{eff}} \approx V_{\mathrm{sphere}} + A_\mathrm{DFU}\,L_\mathrm{break}
\]

This matters because the current model’s frequency proxy is \(f = Q/V_d\); using \(V_{d,\mathrm{eff}}\) reduces predicted frequency without changing the hydraulic solve.

#### C) A compact “cycle” frequency model that combines hydraulics + refill + blocked time

Define:
- \(Q_\mathrm{open}\): rung flow when the DFU is hydraulically open (from the ladder solve)
- \(T_\mathrm{block}\): pinch/reset time during which the DFU is effectively blocked (or high-resistance)

Then a practical predictor is:

\[
f \approx \frac{Q_\mathrm{open}}{V_{d,\mathrm{eff}} + V_\mathrm{refill} + Q_\mathrm{open}\,T_\mathrm{block}}
\]

This connects directly to the duty factor concept: refill volume and blocked time increase the “effective denominator per cycle”.

---

## 6. How to implement a time-state solve in the existing codebase (programmer guide)

### 6.1 Design goals

- Preserve your existing ladder network solver (fast, distributes pressure/flow).
- Replace the **static DFU constitutive law** with a **time-state DFU law**.
- Produce droplet frequency as an **emergent result** of cycle timing, not \(f=Q/V_d\).
- Allow running and comparing multiple model variants (Section 7.1).

### 6.2 High-level approach

Add an outer time loop. Each timestep:

1) Determine each rung’s current **phase/state**  
2) Build network matrices using state-dependent rung conductances and capillary offsets  
3) Solve network → pressures, flows  
4) Update each rung’s droplet-cycle state (volume accumulation, phase transitions)  
5) Record droplet events → compute \(f\)

### 6.3 New data structures (per rung `i`)

- `phase[i]` : enum {OPEN, PINCH, RESET}  
- `V[i]` : accumulated droplet volume since last pinch [m³]  
- `t_phase[i]` : time spent in current phase [s]  
- `drop_count[i]` : integer  
- `t_last_drop[i]` : last pinch time (optional)

### 6.4 Config parameters (first-pass)

- `Vd[i]` or `D_target[i]` (drop size model)  
- `tau_pinch` [s] (time DFU stays effectively blocked)  
- `tau_reset` [s] (optional)  
- `g0[i]` (existing rung conductance)  
- `g_pinch_frac` (e.g., 0.01 → 100× higher resistance during pinch)  
- `Pcap_open`, `Pcap_pinch` (optional higher during pinch)

### 6.5 State-dependent rung constitutive law

Your solver uses arrays:

- `g_rungs[i]`  
- `rhs_oil[i]` (capillary offset)

Set these per phase:

**OPEN:**
- `g_rungs[i] = g0[i]`
- `rhs_oil[i] = -g_rungs[i] * Pcap_open`

**PINCH:**
- `g_rungs[i] = g0[i] * g_pinch_frac`
- `rhs_oil[i] = -g_rungs[i] * Pcap_pinch` (optional)

**RESET:**
- intermediate or same as PINCH

Then existing computation:

```python
Q_rungs = g_rungs * (P_oil - P_water) + rhs_oil
```

automatically yields \(Q_i(t)\).

### 6.6 Time integrator loop (pseudo-code)

```python
t = 0
while t < t_end:

    # 1) set g_rungs and rhs_oil based on phase
    for i in range(N):
        if phase[i] == OPEN:
            g_rungs[i] = g0[i]
            rhs_oil[i] = -g_rungs[i] * Pcap_open
        elif phase[i] == PINCH:
            g_rungs[i] = g0[i] * g_pinch_frac
            rhs_oil[i] = -g_rungs[i] * Pcap_pinch
        elif phase[i] == RESET:
            g_rungs[i] = g0[i] * g_reset_frac
            rhs_oil[i] = -g_rungs[i] * Pcap_reset

    # 2) solve network (instantaneous hydraulics)
    P_oil, P_water = solve_network(g_rungs, rhs_oil, Po, Qw, ...)

    # 3) compute rung flows
    Q = g_rungs * (P_oil - P_water) + rhs_oil

    # 4) update droplet state machines
    for i in range(N):
        t_phase[i] += dt

        if phase[i] == OPEN:
            V[i] += max(Q[i], 0) * dt

            if V[i] >= Vd[i]:
                drop_count[i] += 1
                t_last_drop[i] = t
                V[i] = 0.0
                phase[i] = PINCH
                t_phase[i] = 0.0

        elif phase[i] == PINCH:
            if t_phase[i] >= tau_pinch:
                phase[i] = RESET
                t_phase[i] = 0.0

        elif phase[i] == RESET:
            if t_phase[i] >= tau_reset:
                phase[i] = OPEN
                t_phase[i] = 0.0

    t += dt
```

### 6.7 Frequency output from events

Compute per rung:

\[
f_i = \frac{N_{\mathrm{drops},i}}{t_1 - t_0}
\]

or compute mean inter-event time \(\bar T\) from event timestamps and set \(f=1/\bar T\).

### 6.8 dt choice and event accuracy

- Start: `dt <= min(tau_pinch, tau_reset)/20`.
- If sensitive, refine pinch timing by interpolating when `V` crosses `Vd`.

### 6.9 OFF/ACTIVE threshold compatibility

Keep the existing threshold logic as a guard:

- If rung is OFF (below activation), it remains OFF (no time-state cycling).
- If rung is ACTIVE, it participates in OPEN/PINCH/RESET cycling.

### 6.10 Empirical duty-factor mode (fast check + regression tool)

Before (or alongside) the full time-state DFU implementation, add an explicit **duty factor** \(\phi\in(0,1]\) that scales the predicted oil throughput through each active rung to reflect “fraction-of-cycle productive flow”.

#### What it is
- Current model assumes \(\phi=1\) (always open).
- Your baseline mismatch suggests \(\phi \approx 0.17\)–0.20 (e.g., 0.18).

#### Where to apply it (recommended)
Apply \(\phi\) **after** the steady ladder solve produces rung flows:

\[
\overline{Q}_i = \phi\,Q_{i,\mathrm{steady}}
\quad\Rightarrow\quad
f_i = \overline{Q}_i / V_{d,\mathrm{eff}}
\]

(You may also scale frequency directly, but scaling flow keeps mass balance more interpretable.)

#### Config and outputs
Add config fields such as:
- `duty_factor_mode: "off" | "global" | "per_rung"`
- `duty_factor_global: float` (e.g., 0.18)
- `duty_factor_rungs: List[float]` (optional)
- optional future: `duty_factor_model(...)` for \(\phi(\Delta P, Q_w,\text{geometry})\)

Output both:
- `Q_rung_steady` and `Q_rung_effective`
- `f_steady` and `f_effective`

#### Why implement this even if time-state is the goal
- Fast diagnostic: does “cycle gating” explain the mismatch?
- Regression harness: time-state model should reproduce similar \(\phi\) behavior.
- Device-to-device mapping: test if \(\phi\) correlates with geometry/conditions.

### 6.11 Adding “filling mechanics” as the next layer (meniscus travel + breakup plane)

After the base time-state model is working, add **one more layer** that reflects the detailed mechanics you described:

#### A) Meniscus retreat/advance (refill)
Add a meniscus-position-like state or a per-cycle “refill budget”:

- Parameterize retreat distance \(L_r\) (from video or fit)
- Compute refill volume \(V_\mathrm{refill} = A_\mathrm{DFU} L_r\)
- Implement REFILL as an explicit phase (optional), or include it by requiring that a cycle must pump \(V_\mathrm{refill}+V_{d,\mathrm{eff}}\) before triggering pinch.

#### B) Effective droplet volume includes in-channel droplet-side volume at breakup
Replace the sphere-only droplet volume by:

\[
V_{d,\mathrm{eff}} \approx V_{\mathrm{sphere}} + A_\mathrm{DFU}L_\mathrm{break}
\]

where \(L_\mathrm{break}\) is the breakup plane distance from the exit.

This can be used in both:
- the duty-factor model, and
- the time-state event trigger (i.e., use \(V_{d,\mathrm{eff}}\) as the threshold volume).

---

## 7. Validation plan (so you know the feature is working)

### 7.1 Compare model “versions” side-by-side (required for development)

For the same input conditions, the code should run and report:

1. **Current (steady) model**
   - steady ladder hydraulics
   - droplet frequency via \(f = Q/V_{\mathrm{sphere}}\)

2. **Empirical duty-factor model**
   - steady ladder hydraulics
   - apply \(\phi\) → \(Q_\mathrm{effective}\)
   - frequency via \(f = Q_\mathrm{effective}/V_{d,\mathrm{eff}}\) (or \(V_{\mathrm{sphere}}\) for exact parity)

3. **Time-state DFU model**
   - ladder solve inside a time loop
   - phases OPEN/PINCH/RESET
   - frequency from event timing

4. **Time-state + updated filling mechanics**
   - explicit refill mechanics and effective droplet volume that includes in-channel breakup-plane volume
   - report fit/assumed parameters \(L_r\), \(L_\mathrm{break}\), \(T_\mathrm{block}\) (or equivalents)

Programmer output structure (single dict/JSON) should include at minimum:
- rung flows: `Q_steady`, `Q_effective`, `Q_timeavg`
- droplet volumes: `V_sphere`, `V_eff`
- droplet frequency: `f_steady`, `f_duty`, `f_time_state`, `f_time_state_filling`
- optional: \(\phi_\mathrm{equiv} = \overline{Q}/Q_\mathrm{open}\) computed from time-state results

### 7.2 Backward-compatibility check
Set:
- `g_pinch_frac = 1.0`
- `tau_pinch = tau_reset = 0`

The time-state model should collapse to the steady behavior (within numerical tolerance).

### 7.3 Sensitivity checks
- Increase \(P_\mathrm{cap}\) from 50 → 100–150 mbar (per your observation)
- Verify directionality: higher \(P_\mathrm{cap}\) reduces production/flow and shifts activation thresholds

---

## 8. Practical next actions

- Update \(P_\mathrm{cap}\) to reflect observed activation (100–150 mbar plausible).
- Rule out hidden restrictions (single choke point) even if tubing bulk resistance is small.
- Implement the **time-state DFU gating** as the first physics upgrade.
- Add duty-factor mode early as a quick diagnostic/regression tool.
- From high-speed video (even rough), estimate:
  - \(L_r\): meniscus retreat distance after pinch-off
  - \(L_\mathrm{break}\): pinch plane distance downstream of exit at breakup  
  These enable the “filling mechanics” layer and help explain when/why a constant duty factor generalizes.

---

*End of document.*
