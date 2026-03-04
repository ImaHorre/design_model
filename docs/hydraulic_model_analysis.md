# Hydraulic Model: In-Depth Analysis

*stepgen — ladder-network simulation of a step-emulsification array*

---

## Table of Contents

1. [What This Model Is](#1-what-this-model-is)
2. [Device Anatomy](#2-device-anatomy)
3. [The Ladder Network Abstraction](#3-the-ladder-network-abstraction)
4. [Hydraulic Resistance: Hagen-Poiseuille for Rectangular Channels](#4-hydraulic-resistance-hagen-poiseuille-for-rectangular-channels)
5. [Boundary Conditions: How the Device Is Driven](#5-boundary-conditions-how-the-device-is-driven)
6. [Linear Solver (Mode B — flow/flow)](#6-linear-solver-mode-b--flowflow)
7. [Mixed-BC Solver (Mode A — pressure/flow)](#7-mixed-bc-solver-mode-a--pressureflow)
8. [Threshold and Hysteresis: The Iterative Solver](#8-threshold-and-hysteresis-the-iterative-solver)
9. [Droplet Size and Frequency Model](#9-droplet-size-and-frequency-model)
10. [Configuration Structure](#10-configuration-structure)
11. [Key Assumptions and Known Limitations](#11-key-assumptions-and-known-limitations)

---

## 1. What This Model Is

`stepgen` simulates a **step-emulsification microfluidic array** — a class of passive droplet generator in which oil is pushed through thousands of shallow microchannels (rungs) into a deeper water-filled channel. At each rung exit, the sudden depth increase (the "step") triggers a Rayleigh-Plateau instability that pinches off a monodisperse droplet.

The model answers two questions:

1. **Hydraulic**: Given an applied oil pressure and water flow rate, what pressure and flow distribution develops across all N rungs?
2. **Droplet**: Given those rung flows, what is the predicted droplet diameter and production frequency?

The model is deliberately not a CFD simulation. It treats the device as a **resistor network** (a ladder circuit), which makes it fast enough to sweep thousands of candidate geometries in a design search while still capturing the dominant physics.

---

## 2. Device Anatomy

Understanding the physical layout is essential for understanding every modelling choice.

```
                         OIL IN (pressure Po)
                              │
                         ─────┴─────────────────── Oil main channel (width Mcw, depth Mcd)
                         │         │         │
                     rung 0    rung 1  ... rung N-1    (each: width mcw, depth mcd, length mcl)
                         │         │         │
                         ─────┬─────────────────── Water main channel (width Mcw, depth Mcd)
                              │
                       WATER IN (flow Qw)          OUT (P = 0)
```

### Key geometric zones

| Zone | Parameter names | Physical role |
|---|---|---|
| Oil main channel | `Mcd`, `Mcw`, `Mcl` | Distributes oil along the array; has resistance per pitch segment |
| Water main channel | same dimensions | Collects water + droplets; driven by imposed flow Qw |
| Rung (microchannel) | `mcd`, `mcw`, `mcl`, `pitch` | Restricts oil flow; sets per-rung hydraulic resistance |
| Step junction | `exit_width`, `exit_depth` | Geometry at which the droplet pinches off; controls droplet size |

### Why geometry matters so much

The main channels are wide and deep (~2000 µm × 200 µm), so their per-segment resistance is orders of magnitude lower than the rungs (~8 µm × 5 µm × 4 mm). This asymmetry means:

- **Pressure drop across the main channels is small** relative to drop across the rungs.
- **All rungs see nearly the same driving pressure**, making the array naturally uniform.
- **The rung is the flow-controlling element** — it dominates the hydraulic resistance budget.

This is why the model's predictions are exquisitely sensitive to rung geometry, particularly the **depth** (mcd), which enters resistance as mcd³.

---

## 3. The Ladder Network Abstraction

A ladder network is the standard circuit analogy for a flow network with distributed parallel branches:

```
 Po ──[R_OMc]──┬──[R_OMc]──┬── ... ──┬──[R_OMc]── WALL (dead-end)
               │            │          │
            [R_Omc]      [R_Omc]    [R_Omc]         ← N rungs
               │            │          │
 Qw ──────────┴──[R_WMc]──┴── ... ──┴──[R_WMc]── P_out = 0
```

Each node in the oil rail is connected to:
- Its left and right neighbours via `R_OMc` (main channel segment resistance).
- Its paired water node via `R_Omc` (rung resistance).

Each node in the water rail is connected to:
- Its left and right neighbours via `R_WMc`.
- Its paired oil node via `R_Omc`.

This gives **2N nodes** and a sparse, banded linear system. Kirchhoff's Current Law (KCL) at each node produces one equation per node: net flow in = net flow out.

### Why a ladder, not a tree or single-port model?

A step-emulsification device has a **distributed** oil pressure inlet: the oil pressure at rung 0 (near the inlet) is slightly higher than at rung N-1 (far from the inlet), because each rung draws oil from the main channel which carries the remainder. This axial gradient causes **non-uniform rung flows** if the main channel resistance is not negligible. The ladder network captures this gradient exactly, while a simpler lumped-resistance model would not.

---

## 4. Hydraulic Resistance: Hagen-Poiseuille for Rectangular Channels

### 4.1 The Hagen-Poiseuille formula for a rectangular channel

For a circular pipe, Poiseuille's law gives R = 128μL/(πd⁴). For a rectangular channel of width w and depth h (with h ≤ w), an approximate analytic form is:

```
R = 12μL / (w h³) × 1/(1 − 0.63 h/w)
```

The correction factor `1/(1 − 0.63 h/w)` accounts for the finite width of the channel (for an infinite-width slot, the correction term vanishes and you recover the 2D Poiseuille result). It comes from a one-term truncation of the exact series solution for rectangular duct flow.

```python
# resistance.py: hydraulic_resistance_rectangular()
def hydraulic_resistance_rectangular(mu, length, width, depth, *, correction=True):
    base = 12.0 * mu * length / (width * depth ** 3)
    if not correction:
        return base
    ratio = depth / width
    denom = 1.0 - 0.63 * ratio
    return base / denom
```

**Why depth³ matters so much**: the cube law means a 10% reduction in etch depth (e.g., 5 µm → 4.5 µm) increases resistance by 37%. A 44% depth reduction (5 µm → 2.8 µm) increases resistance by 5.7×. This makes actual fabricated depth the single most sensitive uncertainty in the model.

### 4.2 Rung resistance

The rung resistance is the hydraulic resistance of one microchannel between the oil and water main channels. By default:

```python
# resistance.py: rung_resistance()
def rung_resistance(config):
    rung = config.geometry.rung
    mu = config.fluids.mu_dispersed      # oil viscosity (oil fills the rung)
    constriction_l = rung.mcl * rung.constriction_ratio
    return hydraulic_resistance_rectangular(mu, constriction_l, rung.mcw, rung.mcd)
```

The `constriction_ratio` (typically 0.9) shortens the effective hydraulic length. Physically it accounts for the fact that near the step junction the channel flares slightly — the "active" constricted length is shorter than the nominal `mcl`.

**Note**: `mu_dispersed` is used here because during droplet production the rung is filled with oil (the dispersed phase). This is a critical assumption — the model assumes single-phase (pure oil) Poiseuille flow in the rung at all times. If there is a water plug or a partially formed droplet partially blocking the rung, the effective resistance will be higher.

### 4.3 Piecewise microchannel profiles

If a rung has a more complex cross-section (e.g., a tapered neck feeding into a wider vestibule), the config supports a `microchannel_profile` list of sections. These are summed in series:

```python
# resistance.py: resistance_piecewise()
def resistance_piecewise(sections, mu):
    return sum(
        hydraulic_resistance_rectangular(mu, s.length, s.width, s.depth)
        for s in sections
    )
```

This is exact for sections in series, each individually satisfying the rectangular Poiseuille assumption. It breaks down if sections interact (e.g., if a short constriction has entrance-length effects that extend into the adjacent section).

### 4.4 Main channel resistance per pitch segment

The main channel is divided into N pitch-length segments. Each segment has resistance:

```python
# resistance.py: main_channel_resistance_per_segment()
def main_channel_resistance_per_segment(config):
    R_oil = hydraulic_resistance_rectangular(
        config.fluids.mu_dispersed, rung.pitch, main.Mcw, main.Mcd
    )
    R_water = hydraulic_resistance_rectangular(
        config.fluids.mu_continuous, rung.pitch, main.Mcw, main.Mcd
    )
    return R_oil, R_water
```

The oil and water main channels share the same geometry (Mcw, Mcd) but use different viscosities. Because the main channels are deep and wide (200 µm × 2000 µm) compared to the rungs (5 µm × 8 µm), `R_OMc` and `R_WMc` are typically 3-4 orders of magnitude smaller than `R_Omc`. This is what keeps the array nearly uniform.

---

## 5. Boundary Conditions: How the Device Is Driven

The model supports two operating modes, reflecting how real experiments are run:

### Mode A — Pressure-in + Flow-in (the primary simulation mode)

- **Oil inlet**: Dirichlet boundary condition — the pressure `Po_in` is fixed (pressure controller).
- **Water inlet**: Neumann boundary condition — the volumetric flow `Qw_in` is fixed (syringe pump).
- **Both outlets**: share a common reference pressure `P_out = 0` (gauge pressure).
- **Oil dead-end**: the far end of the oil main channel is a wall — zero axial oil flow out.

This is the physically realistic operating mode. The oil dead-end condition enforces that all oil entering from the oil inlet must exit through rungs.

### Mode B — Flow-in + Flow-in (design search)

Both oil and water inlet flows are prescribed. This is used in design search to evaluate a candidate geometry at a specific emulsion ratio (Q_oil / Q_water) without needing to know the corresponding pressure. The boundary conditions give a unique pressure solution up to an arbitrary global offset.

---

## 6. Linear Solver (Mode B — flow/flow)

`solve_linear()` handles the flow/flow case. It assembles a `(2N+2) × (2N+2)` sparse system using the `generate_conduction_matrix()` function ported directly from the original seed code.

### Matrix structure

The system uses a node ordering that interleaves oil and water nodes. The interior stencil is:

```python
# hydraulics.py: generate_conduction_matrix()

# Interior oil node i (connects to oil neighbours left/right and water node i):
oil_stencil   = [-1/r3, 0, 2/r3 + 1/r2, -1/r2, -1/r3]
# Interior water node i (connects to water neighbours and oil node i):
water_stencil = [ 1/r1, 1/r2, -2/r1 - 1/r2, 0, 1/r1]

# where:
#   r1 = R_WMc  (water main channel segment resistance)
#   r2 = R_Omc  (rung resistance)
#   r3 = R_OMc  (oil main channel segment resistance)
```

Each coefficient in the stencil is a conductance (1/R): the diagonal entry is the sum of all conductances attached to that node (with negative sign), and off-diagonal entries are the individual conductances. This is the nodal conductance matrix standard to circuit analysis.

### Post-solve extraction

```python
# hydraulics.py: solve_linear()
raw = spsolve(A, B)

# Sign convention: negative raw values flip to positive physical pressures
P_oil   = -raw[2::2][::-1]    # every other element, reversed
P_water = -raw[3::2][::-1]

# Rung flow from Ohm's law: Q = ΔP / R
Q_rungs = -(P_water - P_oil) / params.R_Omc
```

The sign conventions here (`-raw[...]`) are inherited verbatim from the seed code and encode a choice about which direction is "positive" flow. The result is that positive `Q_rungs` means oil flowing into water (the intended droplet-production direction).

---

## 7. Mixed-BC Solver (Mode A — pressure/flow)

`simulate()` is the primary function used for operating-point analysis. It delegates to `_simulate_pa()` which builds a `2N × 2N` system with mixed boundary conditions.

### Node ordering

Unlike the linear solver, the mixed-BC system separates oil and water nodes cleanly:

```
x = [P_oil[0], P_oil[1], ..., P_oil[N-1],
     P_water[0], P_water[1], ..., P_water[N-1]]
```

Rows 0 to N-1 are KCL equations for oil nodes; rows N to 2N-1 are for water nodes.

### Key boundary condition rows

```python
# hydraulics.py: _build_mixed_bc_matrix()

# Dirichlet: oil inlet pressure fixed
A[0, 0] = 1.0
B[0] = Po_in_Pa

# KCL: oil interior node i (1 <= i <= N-2)
A[i, i-1] =  1.0 / R_OMc           # inflow from left oil neighbour
A[i, i]   = -(2.0 / R_OMc + g_i)   # outflow to left+right neighbours + rung
A[i, i+1] =  1.0 / R_OMc           # inflow from right oil neighbour
A[i, N+i] =  g_i                    # conductance to paired water node
B[i] = rhs_oil[i]                   # threshold offset (zero in linear case)

# Neumann: oil dead-end node N-1 (no rightward main-channel segment)
A[N-1, N-2]   =  1.0 / R_OMc       # only leftward main-channel inflow
A[N-1, N-1]   = -(1.0 / R_OMc + g_last)
A[N-1, 2*N-1] =  g_last

# Neumann: water inlet — prescribed flow Qw injected at node 0
A[N,  0] =  g_0w                    # conductance to paired oil node
A[N,  N] = -(g_0w + 1.0/R_WMc)
A[N, N+1] = 1.0 / R_WMc
B[N] = -Qw_in_m3s + rhs_water[0]   # negative because Qw flows INTO this node

# Dirichlet: water outlet pressure fixed
A[2*N-1, 2*N-1] = 1.0
B[2*N-1] = P_out_Pa
```

### Rung flow computation

After solving for pressures, rung flows are:

```python
# _simulate_pa()
Q_rungs = g_rungs * (P_oil - P_water) + rhs_oil
```

In the linear (no-threshold) case, `rhs_oil = 0` and this reduces to `Q = g × ΔP = ΔP / R_Omc`, i.e., Ohm's law for flow. The `rhs_oil` offset is non-zero only in the iterative threshold solver.

---

## 8. Threshold and Hysteresis: The Iterative Solver

The linear solve ignores a physically important phenomenon: **capillary pressure at the step junction**. A rung will not produce droplets unless the pressure difference across it exceeds the capillary threshold. If ΔP is too low, the oil-water interface pins at the step (the rung is "OFF"). If ΔP is strongly reversed, water can be driven back into the oil channel.

The iterative solver models this as a three-state regime for each rung:

```python
# generator.py: RungRegime
class RungRegime(enum.Enum):
    ACTIVE  = "active"   # ΔP > dP_cap_ow → oil → water (droplet production)
    REVERSE = "reverse"  # ΔP < -dP_cap_wo → water → oil (reverse flow)
    OFF     = "off"      # |ΔP| below threshold → pinned, negligible flow
```

### Capillary threshold physics

The threshold `dP_cap_ow` is the capillary pressure required to push the oil-water interface through the step junction. It is set by the Young-Laplace equation:

```
dP_cap = 2γ × (1/exit_width + 1/exit_depth)
```

where γ is the oil-water interfacial tension and the exit dimensions are the junction geometry. This is currently a config input (`dP_cap_ow_mbar`, default 50 mbar) rather than computed from γ, because the `gamma` field is not yet propagated through to this formula.

### Iterative algorithm

```python
# generator.py: iterative_solve()

g0 = 1.0 / rung_resistance(config)

# Start: all rungs open, no threshold offsets (= linear solve)
g_rungs   = np.full(N, g0)
rhs_oil   = np.zeros(N)
rhs_water = np.zeros(N)

for _ in range(max_iter):
    result = _simulate_pa(config, Po_Pa, Qw_m3s, Pout_Pa,
                          g_rungs=g_rungs, rhs_oil=rhs_oil, rhs_water=rhs_water)

    dP = result.P_oil - result.P_water
    regimes = classify_rungs(dP, dP_cap_ow, dP_cap_wo)

    if np.array_equal(regimes, prev_regimes):
        break  # converged — regime pattern unchanged

    # Rebuild per-rung parameters based on new classification
    g_rungs = np.where(regimes == RungRegime.OFF, g0 * 1e-10, g0)

    rhs_oil[regimes == RungRegime.ACTIVE]  = -g0 * dP_cap_ow   # threshold offset
    rhs_oil[regimes == RungRegime.REVERSE] = +g0 * dP_cap_wo
    rhs_water = -rhs_oil
```

### Why the RHS offset encoding works

For an ACTIVE rung, the physical flow law is:

```
Q_rung = (ΔP - dP_cap_ow) / R_Omc
       = g0 × (ΔP - dP_cap_ow)
       = g0 × ΔP - g0 × dP_cap_ow
```

Rearranging for the nodal matrix (where `g0 × ΔP` appears as the matrix term `g0 × (P_oil - P_water)`):

```
g0 × P_oil - g0 × P_water = Q_rung + g0 × dP_cap_ow
```

The `+g0 × dP_cap_ow` on the right-hand side is exactly what `rhs_oil[i] = -g0 * dP_cap_ow` encodes (with the sign absorbed into the formulation). After solving, `Q_rungs = g_rungs × ΔP + rhs_oil` recovers the physically meaningful threshold-adjusted flow.

### OFF rungs: numerical treatment

An OFF rung is not completely disconnected (that would make the matrix singular). Instead, its conductance is reduced by a factor of `_EPSILON_OFF = 1e-10`:

```python
_EPSILON_OFF: float = 1e-10
g_rungs = np.where(regimes == RungRegime.OFF, g0 * _EPSILON_OFF, g0)
```

This keeps the system non-singular while making the OFF rung's contribution negligible. The physical interpretation is a near-zero but non-zero leak — acceptable because the fraction of OFF rungs is typically small.

### Convergence

The algorithm converges when the regime classification (ACTIVE/REVERSE/OFF pattern across all N rungs) is identical between two successive iterations. In practice this converges in 2-4 iterations because the pressure distribution does not change dramatically when a small fraction of marginal rungs flip state.

---

## 9. Droplet Size and Frequency Model

### 9.1 Power-law diameter

Step-emulsification droplet diameter is set by the junction exit geometry, not by the flow rate. Experiments show a robust power-law scaling:

```
D = k · exit_width^a · exit_depth^b
```

```python
# droplets.py: droplet_diameter()
def droplet_diameter(config):
    dm = config.droplet_model
    jc = config.geometry.junction
    return dm.k * (jc.exit_width ** dm.a) * (jc.exit_depth ** dm.b)
```

The default calibration coefficients:
- `k = 3.3935` (SI)
- `a = 0.3390` (width exponent — weak dependence)
- `b = 0.7198` (depth exponent — strong dependence)

These are calibrated from empirical data spanning multiple device geometries. The higher exponent on depth than width is physically consistent: the Rayleigh-Plateau instability that governs step emulsification is more sensitive to the smaller confinement dimension.

**Critical note**: the `junction.exit_depth` can differ from the rung `mcd`. If the step is formed by a shallower rung opening into a deeper chamber, `exit_depth = mcd` is appropriate. If the step is into an unbounded reservoir, a different effective depth applies. The config separates these two parameters explicitly.

### 9.2 Droplet volume and frequency

```python
# droplets.py
def droplet_volume(D):
    return (math.pi / 6.0) * D ** 3   # sphere approximation

def droplet_frequency(Q_rung, D):
    return Q_rung / droplet_volume(D)  # f = Q / V_d  [Hz]
```

The sphere approximation (`V = π/6 × D³`) is accurate for droplets in the size range ~5-30 µm where shape is dominated by surface tension rather than gravity (Bond number << 1). For large droplets or low-γ systems this could be a source of error.

The frequency formula `f = Q / V_d` assumes that every oil volume unit that flows through the rung produces exactly one droplet of volume V_d. This is the steady-state passive step-emulsification assumption: the droplet formation cycle is fast compared to the time between droplets, and no oil accumulates at the junction between events.

---

## 10. Configuration Structure

The full model state for a device is encapsulated in a `DeviceConfig` — a tree of frozen dataclasses loaded from a YAML file.

```
DeviceConfig
├── fluids: FluidConfig
│   ├── mu_continuous  [Pa·s]   — water viscosity (fills water main channel)
│   ├── mu_dispersed   [Pa·s]   — oil viscosity (fills rungs during production)
│   ├── emulsion_ratio           — Q_oil / Q_water (design target)
│   └── gamma          [N/m]    — interfacial tension (currently informational)
│
├── geometry: GeometryConfig
│   ├── main: MainChannelConfig
│   │   ├── Mcd  [m]  — depth of both main channels
│   │   ├── Mcw  [m]  — width of both main channels
│   │   └── Mcl  [m]  — routed length (sets N = floor(Mcl / pitch))
│   ├── rung: RungConfig
│   │   ├── mcd  [m]  — CRITICAL: rung depth (enters R as mcd^-3)
│   │   ├── mcw  [m]  — rung width
│   │   ├── mcl  [m]  — rung length
│   │   ├── pitch [m] — centre-to-centre spacing along main channel
│   │   └── constriction_ratio  — effective length = mcl × ratio
│   └── junction: JunctionConfig
│       ├── exit_width [m]  — sets droplet diameter (width component)
│       └── exit_depth [m]  — sets droplet diameter (depth component, dominates)
│
├── operating: OperatingConfig
│   ├── Po_in_mbar  — applied oil inlet pressure
│   ├── Qw_in_mlhr  — water inlet volumetric flow
│   └── P_out_mbar  — outlet gauge reference (usually 0)
│
└── droplet_model: DropletModelConfig
    ├── k, a, b         — power-law size calibration
    ├── dP_cap_ow_mbar  — oil→water capillary threshold
    └── dP_cap_wo_mbar  — water→oil reverse threshold
```

**Example values for chip W11:**

```yaml
# configs/w11.yaml
geometry:
  main:
    Mcd: 200.0e-6    # 200 µm deep
    Mcw: 2000.0e-6   # 2 mm wide
    Mcl: 0.75        # 750 mm routed → N ≈ 25,000 rungs at 30 µm pitch

  rung:
    mcd: 5.0e-6      # designed rung depth — most uncertain parameter
    mcw: 8.0e-6
    mcl: 4000.0e-6
    pitch: 30.0e-6
    constriction_ratio: 0.9

fluids:
  mu_dispersed: 0.03452    # 34.52 mPa·s — relatively viscous oil
  mu_continuous: 0.00089   # 0.89 mPa·s  — water

operating:
  Po_in_mbar: 400.0
  Qw_in_mlhr: 1.5
```

---

## 11. Key Assumptions and Known Limitations

### 11.1 Single-phase Poiseuille in the rung

The model assumes the rung always contains a continuous oil column whose viscosity is `mu_dispersed`. In reality, during active droplet production the rung contains an oil-water interface at the exit, and the droplet pinch-off cycle may briefly obstruct flow. This pulsatile interruption could raise the time-averaged effective resistance above the steady-state Poiseuille value.

### 11.2 Uniform channel cross-section along the rung

The `hydraulic_resistance_rectangular()` formula assumes the channel cross-section is constant over its length. Real soft-lithography rungs have tapered or rounded edges (especially at corners) and may have a non-rectangular profile due to the exposure and development process. The `constriction_ratio` partially accounts for the effective length being shorter, but does not capture cross-sectional variation.

### 11.3 The depth cube law — the dominant uncertainty

```
R_Omc = 12 μ (mcl × constriction_ratio) / (mcw × mcd³) / (1 − 0.63 × mcd/mcw)
```

For chip W11 at nominal design dimensions:
- mcd = 5 µm, mcw = 8 µm, mcl = 4000 µm, constriction_ratio = 0.9, µ = 34.52 mPa·s
- **R_Omc ≈ 2.46 × 10¹⁸ Pa·s/m³**

The experiment (W11, DFU1, 400 mbar, 1.5 mL/hr) gives f_exp ≈ 2.6 Hz while the model predicts f ≈ 14.6 Hz — a **5.6× overestimate of Q_rung**. The droplet diameter is correctly predicted (D_pred ≈ D_exp ≈ 12 µm), confirming the discrepancy is hydraulic, not geometric.

Since R ∝ mcd⁻³, the actual rung depth required to explain the discrepancy:

```
R_needed = 5.6 × R_Omc
mcd_needed = mcd_designed × 5.6^(-1/3) ≈ 5.0 × 0.565 ≈ 2.82 µm
```

A 2.2 µm underetch (5 µm → 2.8 µm designed-to-actual) would fully account for the discrepancy. This is plausible for soft-lithography at 5 µm nominal depth, where photoresist exposure and PDMS curing conditions can significantly affect the actual etched depth.

### 11.4 Capillary threshold as a fixed input

The capillary threshold `dP_cap_ow` is currently a config input rather than being computed from the interfacial tension γ and junction geometry. The YAML field `gamma` exists in `FluidConfig` but is not propagated to `DropletModelConfig.dP_cap_ow_Pa`. The physical Young-Laplace formula is:

```
dP_cap = 2γ × (1/exit_width + 1/exit_depth)
```

For the W11 junction (exit_width = 15 µm, exit_depth = 5 µm):

| γ [mN/m] | dP_cap [mbar] |
|---|---|
| 5  | 27 |
| 15 | 80 |
| 30 | 160 |

The hardcoded default of 50 mbar corresponds to γ ≈ 9 mN/m. The actual interfacial tension for the specific oil/surfactant system should be measured (pendant drop or spinning drop tensiometry) and used to compute dP_cap physically rather than fitting it.

### 11.5 Symmetric main channels

The model assumes the oil and water main channels have the same width `Mcw` and depth `Mcd`. On some chips the oil main channel may be a different depth (fabricated on a separate layer). The config supports different values in principle (they read from the same `main` block), but the resistance calculation applies the same geometry to both.

### 11.6 No entrance/exit losses at the rung junction

The Hagen-Poiseuille formula accounts only for fully-developed viscous losses along the channel length. At the transition from a 2000 µm-wide main channel into an 8 µm-wide rung (aspect ratio change of ~250×), there will be entrance contraction losses and exit expansion losses. These are usually expressed as:

```
ΔP_entrance = K_c × (ρ v²/2)     (contraction coefficient K_c ~ 0.5)
ΔP_exit     = (v_rung − v_main)² × ρ/2  (Borda-Carnot sudden expansion)
```

For the low Reynolds numbers in microfluidics (Re << 1 in the rung, Re << 0.01 in the main channel), these inertial terms are negligible. However, at the rung-to-junction exit, **capillary and viscous entrance effects during interface pinch-off** may not be negligible and are not captured.

### 11.7 Independent rung assumption

The model solves for pressures globally (all rungs coupled through the main channels) but assumes each rung's droplet formation is independent. In reality, droplet production at one rung creates a momentary pressure wave in the water main channel that could trigger or suppress droplet formation in neighbouring rungs. This collective dynamics is not modelled. For very large N (25,000 rungs) at steady state this is likely a small effect, but it contributes to polydispersity in experiments.

---

## Summary

The stepgen hydraulic model is a sparse linear solver for a ladder resistor network. The physics is:

1. **Hagen-Poiseuille** for each channel section → hydraulic resistance R [Pa·s/m³]
2. **Nodal KCL** at every pressure node → sparse linear system A·x = B
3. **Mixed boundary conditions** (pressure Dirichlet at oil inlet, flow Neumann at water inlet) → determined system for Mode A
4. **Iterative threshold classification** (ACTIVE/OFF/REVERSE per rung) → capillary hysteresis without per-timestep transient simulation
5. **Power-law droplet diameter** from junction geometry → D = k·w^a·h^b
6. **f = Q/V_d** → droplet frequency from rung flow and diameter

The largest known uncertainty is the **actual fabricated rung depth** (mcd), which enters resistance as mcd⁻³ and is the primary suspect in the 5.6× hydraulic discrepancy observed on chip W11.
