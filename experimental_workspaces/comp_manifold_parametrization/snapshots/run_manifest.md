# Run Manifest

## Run: Manifold (comb) parametrization exploration — 2026-07-10

**Model commit**: `d733f92b2c15fc260f480f6da8df999c16d29b8b`
**Config snapshot**: none — this study defines geometry inline in `analysis.py`
  (no external device YAML consumed; representative geometry is documented below).
**Command**: `PYTHONIOENCODING=utf-8 python analysis.py`  (run from the workspace dir)
**Outputs**:
  - `results/arms_sweep.csv` — spread vs M for N∈{1000,4000,10000}, beefy/thin primary
  - `results/best_arrangement.csv` — min-spread (M,n) per case
  - `results/htree.csv` — H-tree spread vs depth (structural flatness bound)
  - `results/geometry.csv` — area + no-crossing verdict per structure
  - `figures/spread_vs_arms.png`, `figures/pressure_profile.png`,
    `figures/structure_comparison.png`

### Experimental data used

None — computational (model-only) parametrization study.

| File | Device ID | Test date | Rows | Notes |
|---|---|---|---|---|
| — | — | — | — | no experimental data |

### Solver anchor (reproducibility)

`analysis.py::anchor_divider()` checks the prototype `NodalNetwork` against an exact
series/parallel voltage divider: `P_A = P_in · (R2‖R3)/(R1 + R2‖R3)`. Result: abs err **0.0**
(machine exact). This validates the sparse-Laplacian assembly the package `nodal_network.py`
will reuse.

### Representative geometry (verify against any real target before quoting absolute %s)

| Parameter | Value in run |
|---|---|
| Dispersed phase | sunflower oil |
| η_dispersed | 0.06 Pa·s |
| Continuous phase | shared open drain (P_out = 0) — oil-distribution model only |
| Rung | L = 2 mm, w = 30 µm, h = 20 µm → R_rung ≈ 1.03e16 Pa·s/m³ |
| Arm segment | pitch 120 µm, W = 200 µm, H = 100 µm → r_arm ≈ 6.31e11 |
| Primary (beefy) | spacing 220 µm, W = 1000 µm, H = 200 µm → r_prim ≈ 2.27e10 |
| Primary (thin) | spacing 220 µm, W = 200 µm, H = 100 µm → r_prim ≈ 1.16e12 |
| λ_arm = √(R_rung/r_arm) | 128 rungs |
| N tested | 1000, 4000, 10000 |
| Resistance formula | R = 12 µL / (w h³ (1 − 0.63 h/w)), matches `stepgen/models/resistance.py` |

### Notes / limitations

- Oil-distribution-only (no water main, no reverse flow): absolute spread %s are not full-ladder
  numbers; the robust results are the V-curve optimum, the `n ≈ λ_arm` rule, comb ≫ single main,
  and H-tree planar-infeasibility. See `report.md` caveats.
- Areas are order-of-magnitude (different packing models for single-main vs comb).
