# StepGen Designer v1

Microfluidic step-emulsification device design and validation tool.

Solves a steady laminar hydraulic resistor network ("ladder" of oil and water main channels connected by rung microchannels) to predict pressure profiles, rung flow distribution, droplet production, and operating windows.  Supports experiment ingestion and predicted-vs-measured comparison.

**Not** a CFD solver, mask generator, or CAD pipeline.

---

## Contents

- [Installation](#installation)
- [Quick Start — CLI](#quick-start--cli)
- [Quick Start — Python API](#quick-start--python-api)
- [CLI Reference](#cli-reference)
- [Config File Format](#config-file-format)
- [Experiment CSV Format](#experiment-csv-format)
- [Python API Reference](#python-api-reference)
- [Module Layout](#module-layout)
- [Physics Summary](#physics-summary)
- [Running Tests](#running-tests)

---

## Installation

```bash
# from the repo root (requires Python ≥ 3.10)
pip install -e .
```

Dependencies (all pip-installable): `numpy`, `scipy`, `pandas`, `matplotlib`, `pyyaml`.

After installation the `stepgen` command is available on your PATH.

---

## Quick Start — CLI

```bash
# Single-point simulation
stepgen simulate examples/example_single.yaml

# Sweep two configs and save results
stepgen sweep examples/example_single.yaml examples/example_sweep.yaml --out sweep.csv

# Generate simulation plots
stepgen report examples/example_single.yaml --out-dir ./plots

# Compute operating map (5×5 grid)
stepgen map examples/example_operating_map.yaml \
    --Po-min 50 --Po-max 400 --Po-n 20 \
    --Qw-min 1  --Qw-max 20  --Qw-n 10 \
    --out-dir ./map_plots

# Compare to experiments
stepgen compare examples/example_single.yaml data/experiment.csv --out compare.csv
```

---

## Quick Start — Python API

```python
from stepgen.config import load_config
from stepgen.models.generator import iterative_solve
from stepgen.models.metrics import compute_metrics
from stepgen.design.layout import compute_layout
from stepgen.design.sweep import sweep
from stepgen.design.operating_map import compute_operating_map
from stepgen.viz.plots import plot_pressure_profiles, plot_operating_map
import numpy as np

# Load config
config = load_config("examples/example_single.yaml")

# Simulate one operating point
result  = iterative_solve(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)
metrics = compute_metrics(config, result)
layout  = compute_layout(config)

print(f"Active fraction : {metrics.active_fraction*100:.1f}%")
print(f"D_pred          : {metrics.D_pred*1e6:.2f} µm")
print(f"f_mean          : {metrics.f_pred_mean:.1f} Hz")
print(f"Fits footprint  : {layout.fits_footprint}")

# Pressure profile plot
fig = plot_pressure_profiles(result, config)
fig.savefig("pressure_profiles.png", dpi=150)

# Sweep a parameter
import dataclasses
candidates = []
for mcd_um in [0.2, 0.3, 0.4, 0.5]:
    rung = dataclasses.replace(config.geometry.rung, mcd=mcd_um * 1e-6)
    geom = dataclasses.replace(config.geometry, rung=rung)
    candidates.append(dataclasses.replace(config, geometry=geom))

df = sweep(candidates)
print(df[["mcd_um", "active_fraction", "Q_uniformity_pct", "D_pred"]].to_string())

# Operating map
Po_grid = np.linspace(50, 400, 30)
Qw_grid = np.linspace(1, 20, 10)
map_result = compute_operating_map(config, Po_grid, Qw_grid)

fig = plot_operating_map(map_result, metric="active_fraction")
fig.savefig("operating_map.png", dpi=150)

for w in map_result.windows_strict:
    print(f"Qw={w.Qw_in_mlhr:.1f} mL/hr  "
          f"window [{w.P_min_ok:.0f}, {w.P_max_ok:.0f}] mbar  "
          f"width={w.window_width:.0f} mbar")

# Experiment comparison
from stepgen.io.experiments import load_experiments, compare_to_predictions, compute_compare_report

exp_df  = load_experiments("data/experiment.csv")
comp_df = compare_to_predictions(config, exp_df)
report  = compute_compare_report(comp_df)
print(f"Diameter MAE: {report.diam_mae_um:.2f} µm")
print(f"Frequency MAE: {report.freq_mae_hz:.2f} Hz")
```

---

## CLI Reference

### `simulate`

Run the iterative solver for a single config at one operating point and print a metrics summary.

```
stepgen simulate <config.yaml> [--Po MBAR] [--Qw MLHR] [--out FILE]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--Po` | from config | Oil inlet pressure [mbar] |
| `--Qw` | from config | Water inlet flow [mL/hr] |
| `--out` | — | Save metrics JSON to FILE |

---

### `sweep`

Evaluate one or more config files and save a results table.

```
stepgen sweep <cfg1.yaml> [cfg2.yaml …] [--Po MBAR] [--Qw MLHR] [--out FILE]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--Po` | from each config | Override oil pressure for all candidates |
| `--Qw` | from each config | Override water flow for all candidates |
| `--out` | `sweep.csv` | Output path — `.csv` or `.parquet` |

---

### `report`

Generate simulation plots (PNG) for a single config.

```
stepgen report <config.yaml> [--Po MBAR] [--Qw MLHR] [--out-dir DIR]
```

Saves: `pressure_profiles.png`, `rung_dP.png`, `rung_flows.png`, `rung_frequencies.png`, `regime_map.png`.

---

### `map`

Compute an operating map over a rectangular (Po, Qw) grid and save heatmap PNGs.

```
stepgen map <config.yaml>
    [--Po-min MBAR] [--Po-max MBAR] [--Po-n N]
    [--Qw-min MLHR] [--Qw-max MLHR] [--Qw-n N]
    [--out-dir DIR]
```

| Option | Default |
|--------|---------|
| `--Po-min` | 50 mbar |
| `--Po-max` | 500 mbar |
| `--Po-n` | 10 |
| `--Qw-min` | 1 mL/hr |
| `--Qw-max` | 20 mL/hr |
| `--Qw-n` | 5 |
| `--out-dir` | `.` |

Saves one PNG per metric: `active_fraction`, `reverse_fraction`, `Q_uniformity_pct`, `dP_uniformity_pct`, `P_peak_Pa`.

---

### `compare`

Ingest an experiment CSV, run model predictions, and print residual statistics.

```
stepgen compare <config.yaml> <experiments.csv> [--out FILE] [--calibrate]
```

| Option | Description |
|--------|-------------|
| `--out` | Save comparison DataFrame as CSV |
| `--calibrate` | Scale droplet model `k` to minimise diameter error before comparing |

Always saves `compare_diameter.png` and `compare_frequency.png` alongside `--out` (or in `.` if `--out` not given).

---

## Config File Format

All internal quantities are SI (m, Pa, m³/s, Pa·s). User-facing YAML fields use convenient units as documented below.

```yaml
fluids:
  mu_continuous: 0.00089      # Pa·s  — water (continuous carrier phase)
  mu_dispersed:  0.03452      # Pa·s  — oil   (dispersed droplet phase)
  emulsion_ratio: 0.3         # Q_oil / Q_water (dimensionless)
  gamma: 0.0                  # N/m   — interfacial tension (optional)
  temperature_C: 25.0         # °C    — informational

geometry:
  main:
    Mcd: 100.0e-6    # m — main channel depth
    Mcw: 500.0e-6    # m — main channel width
    Mcl: 30.0e-3     # m — routed main channel length
                     #     Nmc = floor(Mcl / pitch)

  rung:
    mcd: 0.3e-6      # m — rung depth
    mcw: 1.0e-6      # m — rung width
    mcl: 200.0e-6    # m — rung length
    pitch: 3.0e-6    # m — rung pitch along main channel
    constriction_ratio: 1.0

    # Optional piecewise microchannel profile (overrides scalar mcd/mcw/mcl):
    # microchannel_profile:
    #   sections:
    #     - {length: 180e-6, width: 0.5e-6, depth: 0.3e-6}
    #     - {length:  20e-6, width: 1.0e-6, depth: 0.3e-6}

  junction:
    exit_width: 1.0e-6   # m — junction exit width (for droplet size model)
    exit_depth: 0.3e-6   # m — junction exit depth
    junction_type: step  # string label (informational)

operating:
  mode: A
  Po_in_mbar: 200.0   # mbar — oil inlet pressure
  Qw_in_mlhr: 5.0     # mL/hr — water inlet flow rate
  P_out_mbar: 0.0     # mbar — outlet reference pressure

footprint:
  footprint_area_cm2: 10.0
  footprint_aspect_ratio: 1.5
  lane_spacing: 500.0e-6    # m
  turn_radius: 500.0e-6     # m
  reserve_border: 2.0e-3    # m

manufacturing:
  max_main_depth: 200.0e-6   # m — hard constraint
  min_feature_width: 0.5e-6  # m — hard constraint
  max_main_width: 1000.0e-6  # m — hard constraint

droplet_model:
  k: 1.2               # power-law coefficient  D = k · w^a · h^b
  a: 0.5
  b: 0.3
  dP_cap_ow_mbar: 50.0  # mbar — oil→water capillary threshold
  dP_cap_wo_mbar: 30.0  # mbar — water→oil reverse threshold
```

---

## Experiment CSV Format

Required columns (order does not matter):

| Column | Type | Description |
|--------|------|-------------|
| `device_id` | str | Identifier for the physical device |
| `Po_in_mbar` | float | Oil inlet pressure [mbar] |
| `Qw_in_mlhr` | float | Water inlet flow [mL/hr] |
| `position` | int | Rung index (0-based) where measurement was taken |
| `droplet_diameter_um` | float | Measured droplet diameter [µm] |
| `frequency_hz` | float | Measured droplet production frequency [Hz] |

Optional: `notes` (str) — any additional columns are preserved.

---

## Python API Reference

### Config

```python
from stepgen.config import load_config, DeviceConfig
config = load_config("device.yaml")   # → DeviceConfig
```

`DeviceConfig` is a frozen dataclass with sub-configs: `fluids`, `geometry`, `operating`, `footprint`, `manufacturing`, `droplet_model`.  Key derived property: `config.geometry.Nmc` (number of rungs).

---

### Simulation

```python
from stepgen.models.generator import iterative_solve
from stepgen.models.hydraulics import simulate

# Iterative threshold/hysteresis solver (recommended)
result = iterative_solve(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

# Linear solver (no threshold, for reference)
result = simulate(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)
```

`SimResult` fields: `P_oil`, `P_water`, `Q_rungs`, `x_positions`, `Q_oil_total`, `Q_water_total`.

---

### Metrics

```python
from stepgen.models.metrics import compute_metrics
metrics = compute_metrics(config, result)   # → DeviceMetrics
```

Key fields: `Nmc`, `Q_oil_total`, `Q_water_total`, `Q_per_rung_avg`, `Q_uniformity_pct`, `dP_uniformity_pct`, `P_peak`, `active_fraction`, `reverse_fraction`, `off_fraction`, `D_pred`, `f_pred_mean`, `delam_line_load`, `collapse_index`.

---

### Layout

```python
from stepgen.design.layout import compute_layout
layout = compute_layout(config)   # → LayoutResult
```

Fields: `fits_footprint`, `num_lanes`, `lane_length`, `footprint_area_used`.

---

### Sweep

```python
from stepgen.design.sweep import evaluate_candidate, sweep

row = evaluate_candidate(config)            # → dict (all PRD §4.1 fields)
df  = sweep([cfg1, cfg2, …])               # → pd.DataFrame (one row per candidate)
```

Failed candidates produce a NaN row with an `error` column.

---

### Operating Map

```python
from stepgen.design.operating_map import compute_operating_map
import numpy as np

Po_grid    = np.linspace(50, 400, 30)
Qw_grid    = np.linspace(1, 20, 10)
map_result = compute_operating_map(config, Po_grid, Qw_grid)
```

`OperatingMapResult` fields: `Po_grid`, `Qw_grid`, `active_fraction`, `reverse_fraction`, `Q_uniformity_pct`, `dP_uniformity_pct`, `P_peak_Pa`, `windows_strict`, `windows_relaxed`.

Each window (`OperatingWindow`): `Qw_in_mlhr`, `P_min_ok`, `P_max_ok`, `window_width`, `window_center`, `is_open`.

---

### Plots

```python
from stepgen.viz.plots import (
    plot_pressure_profiles,      # P_oil(x), P_water(x)
    plot_rung_dP,                # ΔP_rung(i)
    plot_rung_flows,             # Q_rung(i) bar chart
    plot_rung_frequencies,       # f_rung(i) bar chart
    plot_regime_map,             # ACTIVE / REVERSE / OFF colour bar
    plot_operating_map,          # 2-D heatmap over (Po, Qw)
    plot_pareto,                 # Pareto front scatter
    plot_experiment_comparison,  # predicted vs measured scatter
)

fig = plot_pressure_profiles(result, config)
fig.savefig("out.png", dpi=150)
```

All functions return `matplotlib.figure.Figure`.  This module never calls `plt.show()`.

---

### I/O

```python
from stepgen.io.results import save_results, load_results, export_candidate_json
from stepgen.io.experiments import (
    load_experiments, compare_to_predictions,
    compute_compare_report, calibrate_droplet_model,
)

# Sweep results
save_results(df, "sweep.csv")          # or .parquet (needs pyarrow)
df = load_results("sweep.csv")

# Candidate export
export_candidate_json(config, metrics, layout, "candidate.json")

# Experiments
exp_df  = load_experiments("experiment.csv")
comp_df = compare_to_predictions(config, exp_df)
report  = compute_compare_report(comp_df)         # → CompareReport
cal_cfg = calibrate_droplet_model(config, exp_df) # → DeviceConfig with adjusted k
```

---

## Module Layout

```
stepgen/
  config.py                 — YAML loading, frozen dataclasses, unit conversion
  models/
    resistance.py           — rectangular channel hydraulic resistance
    hydraulics.py           — ladder network solver, SimResult, mixed-BC matrix
    generator.py            — iterative threshold/hysteresis solver, RungRegime
    droplets.py             — power-law droplet diameter and frequency model
    metrics.py              — DeviceMetrics, compute_metrics
  design/
    layout.py               — serpentine footprint layout, LayoutResult
    sweep.py                — evaluate_candidate, sweep engine
    operating_map.py        — compute_operating_map, window extraction
  io/
    results.py              — save/load sweep DataFrames, export candidate JSON
    experiments.py          — CSV ingestion, predicted-vs-measured comparison
  viz/
    plots.py                — all plotting functions
  cli.py                    — argparse CLI entry point

examples/
  example_single.yaml       — single-point simulation
  example_sweep.yaml        — geometry sweep base config
  example_operating_map.yaml — operating map example

tests/                      — pytest test suite (248 tests)
docs/
  PRD_v1.md                 — full product requirements document
  implementation_plan.md    — stage-by-stage build log
  seed_summary.md           — reference seed script analysis
  physical_model_clarification.md — oil dead-end manifold physics derivation
```

---

## Physics Summary

**Resistance model** — rectangular channel approximation (Bruus 2008):

```
R = (12 µ L) / (w h³) · 1 / (1 − 0.63 h/w)
```

**Network topology** — ladder with N rungs:
- Oil rail: pressure-controlled inlet (`P_oil[0] = Po_in`); dead-end downstream (zero-flux Neumann BC, `Q_main_oil(end) = 0`)
- Water rail: flow-controlled inlet (`Q_water = Qw_in`); fixed-pressure outlet (`P_water[N-1] = P_out`)
- All oil must exit through rungs: `Q_oil_in = Σ Q_rung[i]`

**Rung regimes** — iterative piecewise-linear solve:
- `ΔP_i > dP_cap_ow` → ACTIVE (oil→water droplet production)
- `ΔP_i < −dP_cap_wo` → REVERSE (water→oil back-flow)
- else → OFF (pinned)

**Droplet size model** — empirical power law:

```
D = k · w^a · h^b     [m]
f = Q_rung / V_d      [Hz],   V_d = (π/6) D³
```

---

## Running Tests

```bash
.venv/Scripts/python -m pytest -q    # Windows
python -m pytest -q                  # Linux / macOS
```

248 tests, all passing.
