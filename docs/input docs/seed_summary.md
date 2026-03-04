# stepgen_seed — Baseline Behaviour Summary

## Purpose
Solves the steady-state laminar hydraulic ladder network for a microfluidic
oil/water device: two long main channels (oil, water) connected by N rungs.
Outputs pressure profiles and rung flow rates in **linear mode only** (no
threshold model, no mixed BCs).

---

## Inputs

| Parameter | Symbol | Units | Source |
|-----------|--------|-------|--------|
| Main channel length | `Mcl` | m | `Geometry` |
| Main channel depth | `Mcd` | m | `Geometry` |
| Main channel width | `Mcw` | m | `Geometry` |
| Rung depth | `mcd` | m | `Geometry` |
| Rung width | `mcw` | m | `Geometry` |
| Rung length | `mcl` | m | `Geometry` |
| Rung pitch | `pitch` | m | `Geometry` |
| Constriction ratio | `constriction_ratio` | — | `Geometry` |
| Water viscosity | `mu_water` | Pa·s | `Fluids` (default 8.9×10⁻⁴) |
| Oil viscosity | `mu_oil` | Pa·s | `Fluids` (default 3.45×10⁻²) |
| Emulsion ratio | `emulsion_ratio` | — | `DropletSpec` (default 0.3) |
| Droplet radius | `droplet_radius` | m | `DropletSpec` (default 0.5 µm) |
| Production frequency | `production_frequency` | Hz | `DropletSpec` (default 50) |

`Nmc = floor(Mcl / pitch)` is derived, not a direct input.

---

## Outputs

| Quantity | Symbol | Units | Where |
|----------|--------|-------|-------|
| Nodal pressures (oil main) | `P_oil` | Pa | `LinearSolution` |
| Nodal pressures (water main) | `P_water` | Pa | `LinearSolution` |
| Rung volumetric flow rates | `Q_rungs` | m³/s | `LinearSolution` |
| Rung positions | `x_positions` | m | `LinearSolution` |
| Avg rung flow | `Q_avg` | m³/s | `summarize_solution` |
| Flow uniformity | `flow_diff_pct` | % | `summarize_solution` |
| Delaminating line load | `delam_line_load` | N/m | `summarize_solution` |

---

## Resistance Formula

Rectangular channel approximation (Washburn / Poiseuille):

```
R = (12 μ L) / (w h³)  ×  1 / (1 − 0.63 · h/w)
```

Applied with `correction=True` (default) for non-square channels.
Implemented in `resistance.py::hydraulic_resistance_rectangular()`.

Derived resistances:
- `R_OMc` — one main-channel segment (oil side), µ = `mu_oil`, L = `pitch`
- `R_WMc` — one main-channel segment (water side), µ = `mu_water`, L = `pitch`
- `R_Omc` — one rung, µ = `mu_water`, L = `mcl × constriction_ratio`

---

## Linear Solver

`generate_conduction_matrix(params)` builds a **sparse `(2N+2) × (2N+2)`**
matrix in LIL format (converted to CSR before solve) encoding:

- Node ordering: pairs `[oil_i, water_i]` for i = 0…N−1, plus inlet/outlet nodes.
- Interior row stencil: 5-point coupling (left main seg, right main seg, rung).
- Boundary rows: pin inlet oil pressure and water-side outlet; source terms carry
  inlet flow `Q_O` and `Q_W`.

`solve_linear(params)` calls `spsolve(A, B)` and recovers physical pressures via:

```python
P_oil   = -raw[2::2][::-1]   # reverse index; negate sign convention
P_water = -raw[3::2][::-1]
Q_rungs = -(P_water - P_oil) / R_Omc
```

**Sign convention is embedded** — must be preserved exactly when porting.

---

## Units

All internal quantities are SI throughout:
- Lengths: **m**; pressures: **Pa**; flows: **m³/s**; viscosities: **Pa·s**

---

## Limitations of Seed (addressed in v1)

1. No YAML config — geometry hard-coded in `example_run.py`.
2. Linear only — no capillary threshold, no reverse-flow regime.
3. Single fixed operating point — no mixed BCs (Po_in + Qw_in).
4. No sweep, no operating map, no droplet size model, no experiment compare.
5. No CLI or package entry-point.
