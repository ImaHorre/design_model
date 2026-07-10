# Context: Comp Manifold Parametrization

This document is for Claude. Read this at the start of a fresh session to understand
the relevant parts of the `design_model` repository for this workspace.

---

## What this repo is

`design_model` is a physics-based simulation tool for droplet generation in microfluidic
step-emulsification devices. It models the dispersed-phase droplet generation process
using a stage-wise decomposition:

- **Stage 1**: Hydraulic refill — the rung (microchannel) refills with dispersed phase
  after the previous droplet detaches. Modelled via two-fluid Washburn refill.
- **Stage 2**: Droplet growth and snap-off — droplet grows at the junction until it
  reaches a critical radius (Rcrit), then detaches. Controlled by capillary pressure.

The device is a ladder network of parallel rungs fed by a common dispersed-phase manifold,
with a continuous-phase flow channel.

---

## Current model: Stage-Wise V3

**Source**: `stepgen/models/stage_wise_v3/`

| File | Role |
|------|------|
| `core.py` | Main solver entry point: `stage_wise_v3_solve(config, Po_in_mbar, Qw_in_mlhr)` |
| `stage1_physics.py` | Stage 1 Washburn refill → `Stage1Result.t_displacement` [s] |
| `stage2_physics.py` | Stage 2 critical size snap-off → `Stage2Result.t_growth`, `Stage2Result.R_critical` |
| `hydraulics.py` | Dynamic hydraulic network solver |
| `regime_classification.py` | Multi-factor regime warnings (diagnostic, not override) |
| `validation.py` | Physics validation framework |

**Entry point**:
```python
from stepgen.config import load_config
from stepgen.models.stage_wise_v3 import stage_wise_v3_solve

config = load_config("configs/v5_30.yaml")
result = stage_wise_v3_solve(config, Po_in_mbar=300.0, Qw_in_mlhr=10.0)

# Key outputs:
result.group_results[0].stage1_result.t_displacement   # Stage 1 time [s]
result.group_results[0].stage2_result.t_growth         # Stage 2 time [s]
result.group_results[0].stage2_result.R_critical       # Droplet radius [m]
result.average_frequency_hz                            # Device frequency [Hz]
```

---

## Device configurations

Active configs in `configs/`:
- `v5_30.yaml` — V5-30 device (30 µm features, o/w: SDS continuous, silicone oil dispersed)
- `w11.yaml` — W11 device
- `test_stage_wise_v3.yaml` — test config with full v3 physics section

---

## Experimental data

`analysis/stage_timings.csv` — 278 rows of droplet cycle timing measurements

Columns: `DeviceID`, `ContPhase`, `DispPhase`, `ContPhaseFlow` [mL/hr],
`DispPhasePressure` [mbar], `Location` (DFU/rung), `Stage1_s`, `Stage2_s`, `Stage3_s`,
`L_menpoint_um`, `L_men_um`, `Droplet_diameter_um`

**Model ↔ experiment mapping**:
- `stage1_result.t_displacement` ↔ `Stage1_s`
- `stage2_result.t_growth` ↔ `Stage2_s`
- `1/(Stage1_s + Stage2_s + Stage3_s)` ↔ device frequency

---

## Key scripts

- `scripts/compare_experiments.py` — compare model predictions against stage_timings.csv
- `scripts/run_parameter_study.py` — sweep a parameter (Po, Qw, etc.) and plot results

---

## Physics constants (calibrated)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `stage1_viscosity_correction` | 1.0 (default) | Calibrated at 0.96 ± 0.06 for V5-30 |
| `gamma_effective` | ~15 mN/m | Back-calculated interfacial tension |
| `theta_effective` | 30° | Contact angle |
| `R_critical_ratio` | 0.7 | Critical radius as fraction of junction width |

---

## What to look at for this workspace

Focus files for **Define manifold (comb) parametrization and test for an always-best arms x rungs-per-arm arrangement before building the nodal solver**:

- `stepgen/models/stage_wise_v3/core.py — main solver`
- `stepgen/models/stage_wise_v3/stage1_physics.py — Stage 1`
- `stepgen/models/stage_wise_v3/stage2_physics.py — Stage 2`
- `analysis/stage_timings.csv — experimental timing data`

---

## Authoritative documents (in priority order)

1. `docs/03_stage_wise_model/v3/stage_wise_v3_consolidated_physics_plan_REVISED.md`
2. `docs/03_stage_wise_model/v3/stage_wise_v3_implementation_plan_REVISED.md`
3. `docs/03_stage_wise_model/v3/v3_execution_summary_REVISED.md`
