# StepGen Designer v1  
**Microfluidic Step-Emulsification Device Design & Validation Tool**  
*(Design helper + operating-map + experiment comparison. Not mask/CAD generation.)*

---

# Modeling Philosophy

This tool is a reduced-order design aid, not a CFD solver.

It assumes:
- Laminar, steady-state hydraulic resistance behavior.
- Piecewise-linear threshold model for droplet generators.
- Empirical droplet size mapping from exit geometry.
- Heuristic mechanical risk indices.
- Mixed boundary condition operating analysis (pressure-controlled oil, flow-controlled water).

It is intended for:
- Comparative design optimization.
- Throughput vs robustness tradeoff exploration.
- Operating window mapping.
- Experimental validation and calibration support.

It is NOT:
- A multiphase CFD solver.
- A mask-generation tool.
- A lithography-ready CAD pipeline.

---

# 0. Summary

We design microfluidic “ladder” devices: two long parallel main channels (oil and water) connected by many microchannels (“rungs” / droplet generators).

The current script solves a steady laminar hydraulic resistor network to predict pressure profiles and rung flow distribution.

**v1 goals:**
1. Sweep geometry and constraints to find feasible candidates.
2. Predict flow/pressure uniformity and droplet production performance.
3. Compute operating maps under mixed boundary conditions (oil inlet pressure + water inlet flow).
4. Compute operating window width (robustness).
5. Produce schematic layout previews to verify footprint fit.
6. Support experiment ingestion and predicted-vs-measured comparison.

**Non-goal:** CAD/GDS mask generation.

---

# 1. Users & Jobs-to-be-Done

## Primary User
Microfluidic device designer.

## JTBD 1 — Design Search
> Given target droplet diameter and fabrication constraints, find parameters that maximize throughput without instability.

## JTBD 2 — Robust Operation
> Understand safe oil pressure ranges at given water flow.

## JTBD 3 — Soft Testing
> Predict behavior at gentle operating points before pushing max throughput.

## JTBD 4 — Compare to Experiments
> Log measured droplet size/frequency and compare to predictions.

---

# 2. Core Definitions

- **Main channels**: Oil and water channels with distributed resistance.
- **Rungs**: Microchannels connecting mains; droplet generators.
- **Uniformity**: Variation in ΔP and Q across rungs.
- **Operating window**: Range of oil pressures (for given water flow) where device operates correctly.
- **Hard constraints**: Must never be violated (manufacturing, footprint).
- **Soft constraints**: Tradeoff metrics (uniformity, delam index, etc).

---

# 3. Inputs (Config-Driven YAML)

## 3.1 Fluid Properties

- `mu_continuous` [Pa·s]
- `mu_dispersed` [Pa·s]
- `gamma` [N/m] (optional)
- `emulsion_ratio`
- `temperature_C` (optional)

---

## 3.2 Device Geometry

### Main Channels
- `Mcd` [m]
- `Mcw` [m]
- `Mcl` [m] (routed length)

### Rungs
- `mcd` [m]
- `mcw` [m]
- `mcl` [m]
- `pitch` [m]
- `constriction_ratio`

### Junction (Droplet Size Model Inputs)
- `exit_width` [m]
- `exit_depth` [m]
- `junction_type` (string)

---

## 3.3 Microchannel Profile (Piecewise)

```yaml
microchannel_profile:
  sections:
    - {length: 180e-6, width: 0.5e-6, depth: 0.3e-6}
    - {length: 20e-6,  width: 1.0e-6, depth: 0.3e-6}
```

Allows high-resistance pre-section + fixed exit section.

---

## 3.4 Footprint & Routing

- `footprint_area_cm2` (default 10)
- `footprint_aspect_ratio`
- `lane_spacing`
- `turn_radius`
- `reserve_border`

---

## 3.5 Manufacturing & Mechanical Constraints

- `max_main_depth`
- `min_feature_width`
- `max_main_width`
- `collapse_heuristic` parameters
- `delamination` thresholds

---

## 3.6 Operating Modes

### Mode A (Primary)
- Oil inlet pressure `P_oil_in` [mbar]
- Water inlet flow `Q_water_in` [mL/hr]
- Outlet pressure reference

### Mode B (Optional)
Design from droplet target.

---

# 4. Outputs

## 4.1 Per Candidate

- `Nmc`
- `Q_oil_total`
- `Q_water_total`
- `Q_per_rung_avg`
- `Q_uniformity_pct`
- `dP_uniformity_pct`
- `P_peak`
- `active_fraction`
- `reverse_fraction`
- `off_fraction`
- `D_pred`
- `f_pred_mean`
- `delam_line_load`
- `collapse_index`
- `footprint_area_used`
- `fits_footprint`

---

## 4.2 Sweep Results Table

Pandas DataFrame stored as parquet/csv with all metrics.

---

## 4.3 Plots

- P_o(x) and P_w(x)
- ΔP_rung(x)
- Q_rung(i)
- f_rung(i)
- Regime classification
- Operating maps
- Pareto fronts
- Schematic layout preview

---

## 4.4 Parameter Export

- Candidate JSON (geometry + computed metrics)

---

# 5. Physics Model

## 5.1 Resistance Model

Rectangular channel approximation:

R ≈ (12 μ L) / (w h³) · 1 / (1 − 0.63(h/w))

Supports piecewise summation.

---

## 5.2 Ladder Network Solver

Sparse matrix nodal solver enforcing continuity.

Q_i = (P_o,i − P_w,i) / R_rung,i

### 5.2.1 Hydraulic Topology & Boundary Conditions (Critical Clarification)

The oil main channel is a **dead-end manifold**.

There is NO downstream oil outlet.

All injected oil must exit the device through the rungs into the water channel.

This implies:

- Axial oil flow decreases monotonically along the oil rail.
- At the downstream end of the oil rail:

      Q_main_oil(end) = 0

Mathematically:

      P_oil[N-1] = P_oil[N-2]

This is a zero-flux (Neumann) boundary condition on the oil rail.

The solver MUST NOT impose a fixed-pressure boundary at the downstream oil node.

---

The water main channel is a through-flow manifold.

At the downstream end:

      P_water[N-1] = P_out

This is a fixed-pressure (Dirichlet) boundary condition.

---

Mass conservation must hold globally:

      Q_oil_in = Σ Q_rung[i]

At the ideal uniform operating point:

- All rungs have identical resistance
- ΔP_i is constant across device
- Q_rung[i] is identical for all i
- Axial oil flow decreases linearly
- Axial oil flow after final rung is zero

---

## 5.3 Step Generator Regime Model

ΔP_i = P_o,i − P_w,i

Parameters:
- dP_cap_ow
- dP_cap_wo
- optional leakage conductance

Regimes:
- Oil→Water if ΔP_i > dP_cap_ow
- Water→Oil if ΔP_i < −dP_cap_wo
- Else pinned/off

Iterative piecewise-linear solve:
1. Solve linear system.
2. Classify rungs.
3. Modify conductances.
4. Re-solve until stable.

---

## 5.4 Droplet Size Model (v1 Empirical)

Power law:

D = k · w^a · h^b

Frequency:

f_i = Q_d,i / V_d  
V_d = (π/6) D³

Optionally interpolation from dataset.

---

## 5.5 Blowout & Stability

Soft constraint:

max ΔP_rung ≤ dP_blowout

---

# 6. Operating Map & Operating Window

## 6.1 Mixed Boundary Conditions

Oil inlet pressure controlled.  
Water inlet flow controlled.

Boundary conditions:

Oil rail:
- Upstream: pressure-controlled (P_oil[0] = Po_in)
- Downstream: zero-flux (dead-end manifold)

Water rail:
- Upstream: flow-controlled (Q_water injected)
- Downstream: fixed pressure reference (P_water[N-1] = P_out)

This topology ensures:

- All oil must pass through rungs.
- No artificial oil outlet pressure is imposed.
- Reverse flow bands can arise naturally when local ΔP_i < 0.

Simulate grid of (Po, Qw).



---

## 6.2 Window Extraction

For fixed Qw:

Find contiguous Po range satisfying:
- active_fraction ≥ threshold
- reverse_fraction ≤ threshold
- ΔP_uniformity ≤ threshold
- Q_uniformity ≤ threshold
- ΔP ≤ blowout threshold

Compute:
- P_min_ok
- P_max_ok
- window_width
- window_center

Compute both strict and relaxed windows.

---

## 6.3 Tradeoff Plots

- Throughput vs window width
- Throughput vs uniformity
- Pareto front

---

# 7. Layout Preview (Schematic Only)

- Oil main block
- Water main block
- Active rung region block
- Serpentine packing to fit footprint

Outputs:
- fits_footprint
- num_lanes
- lane_length
- footprint_area_used

No microchannel-level rendering.

---

# 8. Sweep Engine

## Hard Constraints
- Depth limits
- Min feature width
- Footprint fit

## Soft Constraints
- Uniformity
- Delam index
- Collapse index
- Blowout ΔP
- Window width

Support weighted scoring and Pareto selection.

---

# 9. Experiment Ingestion

## CSV Schema

- device_id
- Po_in_mbar
- Qw_in_mlhr
- position
- droplet_diameter_um
- frequency_hz
- notes

---

## Compare Report

- Predicted vs measured diameter
- Predicted vs measured frequency
- Reverse band comparison
- Residual statistics

Calibration stub allowed.

---

# 10. Code Architecture

Modules:

- stepgen/config.py
- stepgen/models/resistance.py
- stepgen/models/hydraulics.py
- stepgen/models/generator.py
- stepgen/models/droplets.py
- stepgen/models/metrics.py
- stepgen/design/layout.py
- stepgen/design/sweep.py
- stepgen/design/operating_map.py
- stepgen/io/results.py
- stepgen/io/experiments.py
- stepgen/viz/plots.py
- stepgen/cli.py
- examples/
- tests/

---

# 11. CLI Commands

simulate  
sweep  
report  
map  
compare  

---

# 12. Acceptance Criteria

AC1 — Linear solver matches existing script.  
AC2 — Mixed BC simulation stable.  
AC3 — Reverse band classification works.  
AC4 — Sweep produces correct schema.  
AC5 — Operating window computed.  
AC6 — Layout preview renders.  
AC7 — Experiment compare runs.
AC8 — Oil downstream boundary is implemented as zero-flux (dead-end manifold).
AC9 — Global conservation holds: Q_oil_in = Σ Q_rungs within numerical tolerance.

---

# End of PRD