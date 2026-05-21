# Radial DFU Array — Design Notes

**Date:** 2026-05-21  
**Status:** Brainstorming / concept stage  
**Reference device:** V5-30 (exit 30 µm × 10 µm, pitch 60 µm)

---

## 1. Geometry — the wheel concept

Oil enters at a **hub** (centre). N radial DFU channels radiate outward to the **rim** (circumference), where each DFU exits into an open **continuous-phase bath at atmospheric pressure**.

- DFU pitch at the circumference = 2 × exit_width = **60 µm** (fixed, matches v5-30)
- N_DFU = floor(2πR / pitch) — scales linearly with radius
- Maximum radius: 2.5 inch = **63.5 mm** → N_max ≈ **6,649 DFUs**
- Each DFU channel length = R (the radius); all channels identical by design → uniform resistance automatically

Exit geometry preserved from v5-30:
```
exit_depth  = 10 µm
exit_width  = 30 µm
pitch       = 60 µm
constriction_ratio = 0.9  (90 % → 100 % step at rim)
```

---

## 2. Hydraulic model — key result

Because all N_DFU channels are in parallel and share the same hub pressure (P_oil) and the same exit condition (P_bath = P_atm = 0):

- **P_water = P_atm = constant everywhere** — no continuous-phase pressure gradient
- All DFUs see identical boundary conditions → **uniformity is automatic** (no R_rung/R_main ratio trick needed)
- Upstream resistance is still useful for **flow stability** (Ca control), not for uniformity

**Total flow formula (analytic, independent of radius R):**

```
Q_total = (2π / pitch) × ΔP × w_up × h³ × (1 − 0.63·h/w_up) / (12·µ_oil)
```

where h = exit_depth = 10 µm, w_up = upstream channel width (the free design variable).

**N_DFU ∝ R and R_DFU ∝ R cancel exactly → Q_total is INDEPENDENT of radius R.**

Radius controls *how many* DFUs you have (droplet production rate), not total flow rate.

### Flow table at 200 mbar, R = 63.5 mm, µ_oil = 0.06 Pa·s

| w_up (µm) | R_DFU (Pa·s/m³) | Q_total (µL/hr) | Q/DFU (nL/hr) |
|-----------|-----------------|-----------------|----------------|
| 8         | 2.69 × 10¹⁹    | 17.8            | 2.7            |
| 10        | 1.24 × 10¹⁹    | 38.8            | 5.8            |
| 15        | 5.26 × 10¹⁸    | 91              | 13.7           |
| 20        | 3.34 × 10¹⁸    | 143             | 21.6           |
| 27        | 2.21 × 10¹⁸    | 217             | 32.6           |
| 30        | 1.93 × 10¹⁸    | 248             | 37.3           |
| 50        | 1.05 × 10¹⁸    | 458             | 68.8           |
| 100       | 4.88 × 10¹⁷    | 981             | 147.6          |

---

## 3. Upstream resistance — is it still needed?

**Yes, but for different reasons than the linear ladder design.**

| Design        | Why you need R_upstream high |
|---------------|------------------------------|
| Linear ladder | Uniformity across array (flatten pressure gradient) + stability |
| Radial wheel  | Stability only (Ca control) — uniformity is automatic |

High R_upstream keeps each DFU in the **dripping / step-emulsification regime** by limiting exit velocity.

---

## 4. Minimum resistance — "just a wall at the rim"

The minimum-resistance design uses w_up = exit_width = **30 µm** (uniform channel from hub to rim, same cross-section as exit). The step to the bath is still present at the rim and drives snap-off.

Going wider than 30 µm would require a constriction before the step, changing the emulsification geometry.

**Capillary number at the exit:**

```
Ca = µ_oil × v_exit / γ

v_exit = Q_per_DFU / (exit_w × exit_h)

After substitution (µ_oil cancels):

Ca = ΔP × w_up × h³ × (1 − 0.63·h/w_up) / (12 × L × exit_w × exit_h × γ)
```

**Ca is viscosity-independent.** The regime (dripping / jetting) is set by pressure, geometry, and interfacial tension only.

### Stability table at 200 mbar, R = 63.5 mm, γ = 5 mN/m

| w_up (µm) | Ca at exit    | Ca / Ca_crit | P_max stable (mbar) | R_min (mm) |
|-----------|---------------|-------------|---------------------|------------|
| 8         | 3.0 × 10⁻⁵   | 0.003       | 67,000              | 0.19       |
| 20        | 2.4 × 10⁻⁴   | 0.024       | 8,300               | 1.52       |
| 27        | 3.6 × 10⁻⁴   | 0.036       | 5,500               | 2.30       |
| 30        | 4.1 × 10⁻⁴   | 0.041       | 4,800               | 2.63       |
| 50        | 7.6 × 10⁻⁴   | 0.076       | 2,600               | 4.86       |
| 100       | 1.6 × 10⁻³   | 0.16        | 1,220               | 10.4       |

**Regime thresholds** (from Flow Regimes theory docs):
- Ca < 0.01 → dripping / step emulsification (target)
- Ca 0.01–0.3 → transitional (avoid)
- Ca > 0.3 → jetting / blow-out

At R = 63.5 mm and 200 mbar, even the widest channel (100 µm) has Ca = 1.6 × 10⁻³ — **6× below the transitional threshold**. Maximum stable pressure for the minimum-resistance design (30 µm) is ~4800 mbar — far beyond any practical operating pressure.

For R > R_min (2.6 mm for 30 µm channels at 200 mbar), the device is safely in the dripping regime at all reasonable pressures.

---

## 5. Stage 1 in the bath design

**Stage 1 still occurs.** After snap-off:

1. Oil interface retracts ~√(w×h) ≈ √(30×10) ≈ 17 µm into the exit channel
2. Bath continuous phase fills this short plug
3. Hub pressure drives oil meniscus back out → next droplet

This is confirmed by the v5-30 calibration: measured L_menpoint ≈ 21–25 µm (central rungs), giving V_reset ≈ 6.6–9 fL.

The difference from the linear design: Stage 1 driving pressure = P_hub - P_atm = P_hub (simpler). No hydraulic network needed to determine P_water — it is always zero gauge.

Stage 1 duration for the bath design:
```
t_S1 = V_reset × R_DFU_short / (P_hub − P_cap)
```
where R_DFU_short is the resistance of the short water-filled plug (not the full channel length, only ~17–25 µm). This is much shorter than Stage 1 in the linear device and will likely not be the rate-limiting step.

---

## 6. Interfacial tension γ — what the data tells us

### Inferred from v5-30 calibration (Section 2.3, revised_calibration_results.md)

Fitted capillary back-pressure: **P_cap = 1202 Pa (12.02 mbar)**

Back-calculating γ (P_cap = 2γ·cos(θ) × (1/h + 1/w)):

| Geometry used | θ_eff | Implied γ |
|---------------|-------|-----------|
| Rung 8×10 µm  | 0°    | 2.67 mN/m |
| Junction 30×10 µm | 0° | 4.51 mN/m |
| Junction 30×10 µm | 30° | **5.2 mN/m** |

**Important caveat:** P_cap is a fitted regression parameter, not a direct measurement. It could include flow entry/exit losses and fresh-interface surfactant effects, not purely capillary pressure.

### Independent check via droplet size

D_drop ≈ 24–29 µm measured → R_crit = 12–14 µm.  
Model prediction: R_crit = 0.7 × √(w×h) = 0.7 × 17.3 = **12.1 µm** ✓  
Snap-off is geometry-controlled. γ sets the timescale but not the critical radius.

### Literature values: 2% SDS + sunflower oil

- 2% SDS ≈ 87 mM >> CMC (~8 mM) → rapid adsorption, micelles as reservoir
- Equilibrium γ: **3–8 mN/m** (literature range for SDS/vegetable oil systems)
- At 2% SDS, γ_dynamic ≈ γ_equilibrium for production rates up to ~50 Hz per DFU
- v5-30 operates at ~0.6 Hz per DFU at 200 mbar → far from dynamic effects
- Radial at 200 mbar, 30 µm upstream: ~7 Hz per DFU → within safe range for 2% SDS

**Working reference: γ = 5 mN/m** — consistent with both the calibrated P_cap and literature.

Dynamic effects become important if:
- SDS concentration is reduced below 0.5% (approaching CMC)
- Production rate exceeds ~50 Hz per DFU (requires much higher pressure or wider channels)
- Device is run with a different surfactant system (requires re-calibration of P_cap and C_visc)

---

## 7. Contact angle and surfactant–surface interaction

### The calibrated θ_eff = 30°

Consistent with SDS-treated PDMS (or glass):
- Clean PDMS: θ_water ≈ 105° (hydrophobic)
- After SDS treatment: θ_water ≈ 30–60° (hydrophilic)
- θ_eff = 30° is the *effective* angle during meniscus advance, including dynamic contact line effects

### Effects on device performance

| Effect | Mechanism | Consequence |
|--------|-----------|-------------|
| SDS adsorbs onto walls | Renders PDMS hydrophilic | θ_eff ≈ 30° (calibrated) |
| Hydrophilic walls | Water wets walls preferentially | Thin water film lubricates droplet → clean snap-off |
| P_cap ∝ γ·cos(θ) | Capillary barrier for oil advance | Sets minimum working pressure |
| Dynamic contact line | Moving meniscus sees higher θ than static | θ_eff is not pure static contact angle |

### Minimum entry pressure

```
P_min = 2γ·cos(θ) × (1/h + 1/w)
      = 2 × 5e-3 × cos(30°) × (1/10e-6 + 1/30e-6)
      ≈ 12 mbar
```

This matches the calibrated P_cap exactly — strong consistency check.

P_min scales with γ and cos(θ):
- At γ = 2 mN/m (high SDS): P_min ≈ 5 mbar
- At γ = 5 mN/m (2% SDS): P_min ≈ 12 mbar
- At γ = 30 mN/m (no surfactant): P_min ≈ 70 mbar

All are comfortably below the 200 mbar operating point.

### For the radial design specifically

At higher per-DFU frequency (7 Hz vs 0.6 Hz for v5-30), the water film establishing itself on the channel walls after initial filling may take a few cycles to equilibrate. At 2% SDS this is unlikely to matter in practice — but the first few droplets from each DFU may show slightly different Stage 2 timing on device start-up.

---

## 8. Recommended next experiment (from calibration report)

> Vary SDS concentration at fixed Po and Qw on V5-30. If Stage 2 timing is sensitive to surfactant concentration, it confirms capillary instability as the primary mechanism. If not sensitive, snap-off is geometry-dominated.

This experiment requires no new equipment and would:
1. Directly quantify γ's effect on Stage 2 timing and droplet size
2. Validate (or refine) the γ ≈ 5 mN/m working value
3. Establish the minimum SDS concentration for stable monodisperse production
4. Inform the radial design's operating window for alternative fluid systems

---

## 9. Open design questions

1. **Upstream channel width**: Choose w_up based on target Q_total (see flow table §2). Wider → more flow, lower resistance, still highly stable for R > R_min.
2. **Working radius**: Determines N_DFU and per-DFU frequency. Larger R → more droplets per second, lower Q per DFU (more stable), same total flow.
3. **Hub geometry**: How is the oil distributed from the single inlet to N radial channels? Needs to ensure equal pressure at all channel entries — a wide plenum at the hub achieves this.
4. **Channel depth uniformity**: All DFUs must have identical depth (10 µm) for equal resistance and droplet size. Fabrication tolerance is critical.
5. **Bath flow**: A gentle cross-flow through the bath would carry droplets away and prevent coalescence at the rim. This does not change the hydraulic model (P_bath ≈ P_atm still holds if bath flow velocity is low).
6. **γ measurement**: A direct measurement of γ for the specific fluid system (pendant drop or spinning drop tensiometry) would reduce the main parameter uncertainty.

---

## 10. Files

| File | Description |
|------|-------------|
| `radial_hydraulics.py` | Core hydraulic model, Ca stability analysis, P vs Q plots |
| `config_radial_v1.yaml` | Example device config (20 µm upstream, 200 mbar, R = 63.5 mm) |
| `pq_radial.png` | P vs Q design space plot |
| `ca_stability_radial.png` | Ca vs pressure and max stable pressure vs radius |
| `design_notes.md` | This file |

---

## 11. Hub geometry and hydraulics

### 11.1 Why the hub is a geometric necessity

At radius r, the arc spacing between adjacent DFU channels is:

```
arc(r) = pitch × (r / R)
```

Wall thickness between adjacent channels:

```
t_wall(r) = arc(r) − w_up = pitch × r/R − w_up
```

Walls vanish (t_wall = 0) at:

```
r_merge = R × w_up / pitch
```

Below r_merge, separate channel walls are geometrically impossible — channels would
physically overlap. The hub is therefore a forced open plenum for r < r_merge regardless
of design intent. With a minimum wall thickness t_min ≈ 5 µm for fabrication, the
practical hub edge radius is:

```
r_hub = R × (w_up + t_min) / pitch
```

**Hub dimensions for R = 63.5 mm:**

| w_up | r_merge (geometric min) | r_hub (+5 µm wall min) | Hub as % of area |
|------|------------------------|------------------------|-----------------|
| 8 µm | 8.5 mm | 10.8 mm | 2.9% |
| 20 µm | 21.2 mm | 26.5 mm | 17.4% |
| 27 µm | 28.6 mm | 34.1 mm | 28.8% |
| 30 µm | 31.75 mm | 37.1 mm | 34.1% |

Hub area fraction = (r_hub / R)² — much smaller than the radius fraction suggests because
area scales as r².

**Layout sketch (top-down):**

```
┌──────────────────── R = 63.5 mm ────────────────────┐
│                open bath / P_atm                    │  ← rim, each channel exits
│    ╔══════════════════════════════════════╗          │
│    ║   radial channels (depth 10 µm)     ║          │  ← N_DFU wedge-shaped channels
│    ║      ┌──────────────────────┐       ║          │     walls: thin near hub,
│    ║      │    HUB plenum        │       ║          │     thicker near rim
│    ║      │   (open, 10 µm)      │       ║          │
│    ║      │   oil inlet → ●      │       ║          │
│    ║      └──────────────────────┘       ║          │
│    ╚══════════════════════════════════════╝          │
└─────────────────────────────────────────────────────┘
```

Channel walls are wedge-shaped: zero thickness at r_merge, (pitch − w_up) wide at
the rim. For w_up = 20 µm: walls grow from 0 µm at 21.2 mm to 40 µm at 63.5 mm.

---

### 11.2 Correction to channel length: L_eff ≠ R

The current model uses L = R (full radius) as channel length. But channels only exist
for r > r_hub, so the effective length is:

```
L_eff = R − r_hub = R × (pitch − w_up − t_min) / pitch
```

This does **not** break the Q_total independence from R (both N_DFU ∝ R and L_eff ∝ R,
so they cancel as before). But it changes the magnitude of Q_total. The corrected value is
higher by:

```
Q_total_corrected = Q_total_model × pitch / (pitch − w_up − t_min)
```

**Correction factors at R = 63.5 mm, t_min = 5 µm:**

| w_up | L_eff | Factor | Q_model @ 200 mbar | Q_corrected |
|------|-------|--------|--------------------|-------------|
| 8 µm | 52.7 mm | ×1.17 | 17.8 µL/hr | 20.8 µL/hr |
| 20 µm | 37.0 mm | ×1.71 | 143 µL/hr | 245 µL/hr |
| 30 µm | 26.4 mm | ×2.40 | 248 µL/hr | 595 µL/hr |

The flow table in §2 underestimates Q by 17–140% depending on w_up. The hydraulic model
(`radial_hydraulics.py`) needs updating to use L_eff, not R, as the channel length.

The Ca and P_max_stable formulas are also affected: effective L is shorter, so Ca at exit
is higher than currently computed. The existing stability margins are comfortable enough
that this doesn't threaten the dripping-regime conclusion, but the numbers should be
corrected.

---

### 11.3 Hub hydraulics — Hele-Shaw radial flow

If oil is delivered from a single central point (radius r_inlet), it must flow radially
outward through the hub disc (depth h = 10 µm) to reach all N_DFU channel entries at r_hub.
This is Hele-Shaw radial flow and has a well-defined pressure drop:

```
ΔP_hub = (6µ × Q_total / π × h³) × ln(r_hub / r_inlet)
```

This hub resistance sits **in series** with the parallel channel array. It does not break
uniformity — all channel entries at r_hub are at the same pressure by radial symmetry. It
does reduce the effective drive pressure across the channels:

```
ΔP_channels = P_supply − ΔP_hub
```

**Hub ΔP values (h = 10 µm, r_inlet = 1 mm, using Q_corrected):**

| w_up | Q_corrected | r_hub | ΔP_hub | ΔP_hub vs 200 mbar supply |
|------|-------------|-------|--------|--------------------------|
| 8 µm | 20.8 µL/hr | 10.8 mm | ~16 mbar | ~8% |
| 20 µm | 245 µL/hr | 26.5 mm | ~255 mbar | ~127% |
| 30 µm | 595 µL/hr | 37.1 mm | ~684 mbar | ~342% |

**Interpretation:**

- Narrow channels (w_up ≤ 10 µm): hub ΔP ≈ 8–15% of supply pressure. Manageable as a
  series correction — increase supply pressure by that fraction and the channels operate as
  designed.
- Wide channels (w_up ≥ 20 µm): hub ΔP equals or greatly exceeds the intended channel ΔP.
  A 200 mbar supply cannot drive meaningful flow through 20 µm channels if the hub alone
  consumes >255 mbar. Would require supply pressures of 450–880 mbar to achieve the same
  channel operating conditions. Whether this is acceptable depends on the pressure source.

**This is not a uniformity problem — it is a pressure budget problem.**

The uniformity argument holds regardless of hub depth, because the hub pressure drop is
the same at all angular positions (radial symmetry). All channels see the same
P_at_r_hub. The issue is only whether P_supply is high enough to overcome ΔP_hub and
still drive the channels at the intended ΔP.

**Key open question:** How is oil delivered to the hub? If the inlet is not a small
central point but a larger port or manifold feeding the hub at or near r_hub, then
ln(r_hub / r_inlet) → 0 and ΔP_hub becomes negligible regardless of h. A ring-manifold
inlet at r_hub (oil delivered in a ring around the hub circumference) eliminates hub flow
entirely — the hub becomes a static pressure equaliser, not a flow path.

**Mitigation options:**

1. **Large or ring inlet port** — maximise r_inlet; ideally feed oil uniformly around the
   hub perimeter at r_hub so there is no radial hub flow at all. ΔP_hub → 0.
2. **Higher supply pressure** — for narrow channels this is a minor correction; for wide
   channels it requires significantly higher pressure but is still compatible with standard
   pressure controllers (< 1 bar).
3. **Narrow upstream channels (w_up ≤ 10 µm)** — keeps Q_total low and r_hub small,
   limiting ΔP_hub to negligible levels without any change to inlet design.

---

*Hub geometry and hydraulics section added 2026-05-21*

---

*Notes compiled from brainstorming session, 2026-05-21*
