# StepGen Designer v1 — Capability Summary & Feature Tour

---

## What Is This Tool?

StepGen Designer is a **reduced-order hydraulic design tool** for microfluidic
step-emulsification ladder devices. It lets you:

- Predict pressure profiles and flow distributions along oil/water ladder networks
- Map operating windows (safe ranges of oil pressure and water flow)
- Search geometry space to find designs that hit a target droplet size and throughput
- Compare model predictions against measured experiment data
- Visualise device layout to scale in a serpentine footprint

It is **not** a CFD solver or a mask/CAD tool. It is a fast, constraint-aware
design aid — typically solving in milliseconds per candidate — enabling broad
sweeps that a CFD tool could never cover in reasonable time.

---

## Physical Model (brief)

| Layer | What the code does |
|-------|--------------------|
| **Resistance** | Rectangular Stokes flow: `R = 12µL / (wh³(1 - 0.63h/w))` |
| **Ladder solver** | Sparse nodal matrix with mixed BCs: oil inlet = pressure-controlled, water inlet = flow-controlled, oil downstream = dead-end (Neumann), water downstream = fixed pressure |
| **Regime model** | Iterative threshold classifier: each rung is *active* (oil→water), *reverse* (water→oil), or *off* (pinned) |
| **Droplet size** | Power-law: `D = k · exit_width^a · exit_depth^b` (calibrated: k=3.3935, a=0.339, b=0.720) |
| **Frequency** | `f = Q_rung / V_droplet`; volume from sphere-cap of diameter D |

---

## User Workflows

### Workflow 1 — Simulate a known design (Mode A: pressure + flow)

```
stepgen simulate examples/example_single.yaml --Po 200 --Qw 5
```

Prints: Nmc, active/reverse fraction, flow uniformity, ΔP uniformity, predicted
droplet diameter, mean frequency, footprint fit, hard-constraint pass/fail.

Add `--out result.json` to save a full JSON record.

---

### Workflow 2 — Simulate with flow-flow BCs (Mode B: specify Q_oil + Q_water)

```
stepgen simulate examples/example_single.yaml --Qo 1.7 --Qw 15.3
```

The tool derives the required oil inlet pressure (Po) from a linear oracle,
then runs the full iterative solve. Reports `derived_Po_in_mbar`.

Mode B is useful when you know the emulsion ratio target rather than the
pressure set-point.

---

### Workflow 3 — Multi-plot report for a single config

```
stepgen report examples/example_single.yaml --Po 200 --Qw 5 --out-dir plots/
```

Saves six PNGs in `plots/`:
- `layout_schematic.png` — serpentine top-view to scale with arc turns
- `pressure_profiles.png` — P_oil(x) and P_water(x) along device
- `rung_dP.png` — ΔP across each rung
- `rung_flows.png` — volumetric flow through each rung
- `rung_frequencies.png` — predicted droplet frequency per rung
- `regime_map.png` — active / reverse / off classification per rung

---

### Workflow 4 — Operating map (2D heatmap over Po × Qw grid)

```
stepgen map examples/example_operating_map.yaml \
    --Po-min 50 --Po-max 500 --Po-n 20 \
    --Qw-min 1  --Qw-max 20  --Qw-n 8  \
    --out-dir map_output/
```

Saves heatmaps for `active_fraction`, `reverse_fraction`,
`Q_uniformity_pct`, `dP_uniformity_pct`, `P_peak_Pa`.
Also computes strict and relaxed operating windows for each Qw slice.

---

### Workflow 5 — Design-from-targets sweep

```
stepgen design examples/design_search_template.yaml --out design_results.csv
```

Given a target droplet size and footprint:
1. Enumerates all (Mcd, Mcw, pitch, rung mcd/mcw/mcl) combinations
2. **Automatically derives** Mcl (max that fits footprint) and Nmc for each
3. Auto-derives junction geometry from target droplet diameter (square junction assumption)
4. Evaluates each candidate in Mode B (emulsion ratio)
5. Applies hard constraints (footprint, depth, min feature), flags soft constraints
6. Returns a ranked CSV: best throughput first

Output columns include: `rank`, `Mcd_um`, `Mcw_um`, `Mcl_derived_mm`,
`Nmc_derived`, `Q_total_mlhr`, `Po_required_mbar`, `passes_hard`, `soft_flags`.

---

### Workflow 6 — Compare predictions to measurements

```
stepgen compare examples/example_single.yaml experiments.csv \
    --out compare.csv
```

CSV schema: `device_id, Po_in_mbar, Qw_in_mlhr, position, droplet_diameter_um, frequency_hz`

Produces:
- `compare_diameter.png` — predicted vs measured scatter with 1:1 line
- `compare_frequency.png` — same for frequency
- `spatial_comparison.png` — 3-panel plot: pressure profile + D vs position + f vs position
- Printed report: MAE, RMSE, bias for diameter and frequency

Add `--calibrate` to auto-scale the droplet model `k` coefficient to match
the mean measured diameter before computing residuals.

---

### Workflow 7 — Multi-config sweep (programmatic or CLI)

```
stepgen sweep config_A.yaml config_B.yaml config_C.yaml \
    --Po 300 --Qw 10 --out sweep.csv
```

One row per config in the output CSV. Errors (e.g. invalid geometry) produce
NaN rows with an `error` column. Compatible with the same `save_results` /
`load_results` I/O used elsewhere.

---

## Robustness Fields (evaluate_candidate)

Any simulation (simulate, sweep, design) can request robustness analysis:

```python
from stepgen.design.sweep import evaluate_candidate
row = evaluate_candidate(config, Po_in_mbar=200, Qw_in_mlhr=10,
                         compute_robustness=True)
# row["window_width_mbar"]  — strict operating window width
# row["margin_lower_mbar"]  — headroom below current Po
# row["margin_upper_mbar"]  — headroom above current Po
# row["robustness_class"]   — "none" | "narrow" | "moderate" | "wide"
```

---

## Key Physical Constraints

| Constraint | Type | Meaning |
|-----------|------|---------|
| `Mcd ≤ max_main_depth` | Hard | Etch limit |
| `Mcw ≤ max_main_width` | Hard | Lithography limit |
| `rung mcd, mcw ≥ min_feature_width` | Hard | Resolution limit |
| `fits_footprint` | Hard | Device fits on chip |
| `collapse_index = Mcw/Mcd` | Soft | Bonding collapse risk |
| `Q_uniformity_pct` | Soft | Rung-to-rung flow variation |
| `dP_uniformity_pct` | Soft | Rung-to-rung pressure variation |
| `active_fraction` | Soft | Fraction of rungs producing droplets |

---

## Module Map

```
stepgen/
  config.py             — DeviceConfig, DesignSearchSpec, load_config, load_design_search
  models/
    resistance.py       — R_rect(), main_channel_resistance_per_segment(), rung_resistance()
    hydraulics.py       — _build_mixed_bc_matrix(), iterative_solve(), linear_solve_from_flows()
    generator.py        — threshold/hysteresis rung regime classification
    droplets.py         — droplet_diameter(), droplet_frequency()
    metrics.py          — compute_metrics() → uniformity, delam, collapse, active fraction
  design/
    layout.py           — compute_layout() → serpentine packing, num_lanes, lane_length
    sweep.py            — evaluate_candidate(), sweep(), _compute_robustness_fields()
    operating_map.py    — compute_operating_map() → windows_strict, windows_relaxed
    design_search.py    — run_design_search() → ranked DataFrame
  io/
    results.py          — save_results(), load_results(), export_candidate_json()
    experiments.py      — load_experiments(), compare_to_predictions(),
                          compute_compare_report(), calibrate_droplet_model()
  viz/
    plots.py            — 9 plot functions returning matplotlib Figure
  cli.py                — 6 subcommands (simulate, sweep, report, map, design, compare)
```

---

## Running Tests

All 287 tests pass. Use the project's virtual environment:

```bash
.venv/Scripts/python -m pytest -q
```
