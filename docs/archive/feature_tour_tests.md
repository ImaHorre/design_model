# StepGen Designer — Feature Tour & Test Checklist

Run these commands from the project root with the venv active:

```bash
# Windows
.venv/Scripts/activate
# or prefix every command with: .venv/Scripts/python -m stepgen ...
```

The commands below use `stepgen` assuming the package is installed in editable
mode (`pip install -e .`). If not installed, replace `stepgen` with
`.venv/Scripts/python -m stepgen`.

---

## Block 1 — Core hydraulic solver (PRD v1 AC1–AC3, AC8, AC9)

### 1a. Basic Mode A simulation

**What it tests:** linear + iterative solver, dead-end oil BC, regime
classification, flow uniformity output.

```bash
stepgen simulate examples/example_single.yaml --Po 200 --Qw 5
```

**Expected output (approx):**
```
  Mode    : A (pressure-flow)
  Po      : 200.0 mbar
  Qw      : 5.00 mL/hr
  active  : 100.0 %
  reverse : 0.0 %
  Q_unif  : <1 %
  D_pred  : ~0.3 µm
  fits    : True
  hard OK : True
```

**Check:** active_fraction 100%, reverse_fraction 0%, hard OK True.

---

### 1b. Trigger reverse bands

Increase Qw so water pressure locally exceeds oil pressure, inducing reverse
flow on some rungs.

```bash
stepgen simulate examples/example_single.yaml --Po 50 --Qw 50
```

**What to look for:** `reverse : > 0 %`, illustrating that the solver
correctly identifies water-into-oil rungs (AC3).

---

### 1c. Full plot report

**What it tests:** all six plot types including the layout schematic (v2 Step 1).

```bash
mkdir -p plots
stepgen report examples/example_single.yaml --Po 200 --Qw 5 --out-dir plots
```

**Check:** Six PNG files appear in `plots/`:
- `layout_schematic.png` — top-view serpentine with arc turns and annotations
- `pressure_profiles.png` — P_oil and P_water vs position
- `rung_dP.png`, `rung_flows.png`, `rung_frequencies.png`, `regime_map.png`

Open `layout_schematic.png`: confirm blue (oil) and red (water) channel
rectangles, footprint bounding box, and turn arcs are visible.

---

## Block 2 — Operating map & windows (PRD v1 AC5)

### 2a. Small operating map

```bash
mkdir -p map_output
stepgen map examples/example_operating_map.yaml \
    --Po-min 50 --Po-max 400 --Po-n 15 \
    --Qw-min 2  --Qw-max 15  --Qw-n 6  \
    --out-dir map_output
```

**Expected output:**
```
  Strict windows computed : 6
  Relaxed windows computed: 6
  → map_active_fraction.png
  → map_reverse_fraction.png
  → ...
```

**What to look for:** `active_fraction` heatmap shows a clear "good" region
(high fraction at moderate Po). Check that window count matches the number of
Qw grid points (6).

---

### 2b. Operating map at higher resolution

```bash
stepgen map examples/example_operating_map.yaml \
    --Po-min 30 --Po-max 600 --Po-n 25 \
    --Qw-min 1  --Qw-max 25  --Qw-n 8  \
    --out-dir map_hires
```

Compare `map_active_fraction.png` to the low-res version to confirm the
physics is smooth and consistent.

---

## Block 3 — Mode B flow-flow BCs (v2 Step 2)

### 3a. Mode B simulate

**What it tests:** linear oracle derives Po from Q_oil + Q_water target.

```bash
stepgen simulate examples/example_single.yaml --Qo 1.7 --Qw 15.3
```

**Expected output:**
```
  Mode    : B (flow-flow)
  Qo      : 1.700 mL/hr (requested)
  Po      : ~446 mbar (derived)
```

**Check:** `derived_Po_in_mbar` is printed (not Po directly); Mode B label shown.

Note: actual Q_oil from the iterative solve will be ~10-15% below requested —
this is physical (capillary threshold bleeds some pressure) not a bug.

---

### 3b. Mode B vs Mode A consistency

Run Mode B to get a derived Po, then feed that Po back into Mode A and confirm
the results are close:

```bash
# Step 1 — get derived Po
stepgen simulate examples/example_single.yaml --Qo 1.7 --Qw 15.3

# Step 2 — re-run Mode A at that Po (substitute the value from step 1)
stepgen simulate examples/example_single.yaml --Po 446 --Qw 15.3
```

**Check:** Q_oil in Mode A output should be close to (but slightly above)
1.7 mL/hr, and all other metrics should be consistent.

---

## Block 4 — Design-from-targets sweep (v2 Step 3)

### 4a. Standard design search

**What it tests:** full geometry sweep, automatic Mcl + Nmc derivation from
footprint, junction auto-derivation from target droplet size.

```bash
stepgen design examples/design_search_template.yaml --out design_results.csv
```

**Expected output (~12 s):**
```
  Target droplet  : 15.0 µm
  Emulsion ratio  : 0.1
  Objective       : max_throughput
  Candidates      : 96
  Hard-pass       : N  (some fraction)
  Top candidate   : Mcd=...µm  Mcw=...µm  Nmc=...  Q_total=... mL/hr  Po=... mbar
  → design_results.csv
  → design_results_plot.png
```

**What to check:**
- CSV has `Mcl_derived_mm` and `Nmc_derived` columns (computed, not input)
- `passes_hard` column is True/False; candidates are sorted by `Q_total_mlhr`
- `soft_flags` column shows which soft constraints fail

---

### 4b. Inspect design search CSV

```python
import pandas as pd
df = pd.read_csv("design_results.csv")
print(df[df["passes_hard"]].head(5)[
    ["rank","Mcd_um","Mcw_um","Mcl_derived_mm","Nmc_derived",
     "Q_total_mlhr","Po_required_mbar","soft_flags"]
])
```

**Check:** Top rows have the highest Q_total_mlhr; Mcl is never a raw input.

---

## Block 5 — Robustness fields (v2 Step 5)

### 5a. Robustness via Python API

```python
from stepgen.config import load_config
from stepgen.design.sweep import evaluate_candidate

config = load_config("examples/example_single.yaml")
row = evaluate_candidate(config, Po_in_mbar=200, Qw_in_mlhr=5,
                         compute_robustness=True)

print(f"Window width  : {row['window_width_mbar']:.1f} mbar")
print(f"Margin lower  : {row['margin_lower_mbar']:.1f} mbar")
print(f"Margin upper  : {row['margin_upper_mbar']:.1f} mbar")
print(f"Robustness    : {row['robustness_class']}")
```

**Check:** All four robustness fields present; `robustness_class` is one of
`"none"` / `"narrow"` / `"moderate"` / `"wide"`.

---

### 5b. Robustness at a tight operating point

```python
row_tight = evaluate_candidate(config, Po_in_mbar=55, Qw_in_mlhr=5,
                               compute_robustness=True)
print(row_tight["robustness_class"])  # expect "none" or "narrow"
```

---

## Block 6 — Experiment ingestion & comparison (PRD v1 AC7, v2 Step 4)

### 6a. Create a synthetic experiment CSV

```python
import pandas as pd, numpy as np

rows = []
for pos in [0.15, 0.25, 0.50, 0.75, 0.90]:
    rows.append({
        "device_id": "dev_A",
        "Po_in_mbar": 200.0,
        "Qw_in_mlhr": 5.0,
        "position": pos,
        "droplet_diameter_um": 0.32 + np.random.normal(0, 0.01),
        "frequency_hz": 1500 + np.random.normal(0, 50),
    })
pd.DataFrame(rows).to_csv("test_experiments.csv", index=False)
```

---

### 6b. Compare predictions to synthetic data

```bash
stepgen compare examples/example_single.yaml test_experiments.csv \
    --out compare_output.csv
```

**Expected output:**
```
  Points         : 5
  Diam MAE       : ~0.0x µm
  Diam RMSE      : ~0.0x µm
  Freq MAE       : ~5x Hz
  → compare_diameter.png
  → compare_frequency.png
  → spatial_comparison.png
```

**What to check in `spatial_comparison.png`:**
- Panel 1: smooth P_oil (declining) and P_water (rising) pressure profiles
- Panel 2: D_pred horizontal line + measured dots at fractional positions 0.15–0.90
- Panel 3: f_pred profile + measured dots

---

### 6c. Calibration mode

```bash
stepgen compare examples/example_single.yaml test_experiments.csv \
    --out compare_calibrated.csv --calibrate
```

**Check:** Line `(calibration applied: k adjusted...)` appears; Diam bias ≈ 0
after calibration; Diam MAE is lower than without `--calibrate`.

---

## Block 7 — JSON export & results I/O (PRD v1 §4.4)

### 7a. Export a full candidate JSON

```bash
stepgen simulate examples/example_single.yaml --Po 200 --Qw 5 \
    --out candidate.json
```

```python
import json
with open("candidate.json") as f:
    data = json.load(f)
print(list(data.keys()))   # expect: geometry, operating, metrics, layout
```

---

### 7b. Save and reload sweep results

```python
from stepgen.config import load_config
from stepgen.design.sweep import sweep
from stepgen.io.results import save_results, load_results
import dataclasses

base = load_config("examples/example_sweep.yaml")

candidates = []
for po in [150, 200, 250, 300]:
    op = dataclasses.replace(base.operating, Po_in_mbar=po)
    candidates.append(dataclasses.replace(base, operating=op))

df = sweep(candidates)
save_results(df, "sweep_output.csv")
df2 = load_results("sweep_output.csv")
assert len(df2) == 4
print(df2[["Po_in_mbar","active_fraction","Q_uniformity_pct","D_pred"]])
```

---

## Block 8 — Layout schematic (v2 Step 1)

### 8a. Verify layout schematic standalone

```python
import matplotlib; matplotlib.use("Agg")
from stepgen.config import load_config
from stepgen.design.layout import compute_layout
from stepgen.viz.plots import plot_layout_schematic

config = load_config("examples/example_single.yaml")
layout = compute_layout(config)
fig = plot_layout_schematic(config, layout)
fig.savefig("schematic_test.png", dpi=150)
print(f"Lanes: {layout.num_lanes}, Lane length: {layout.lane_length_m*1000:.1f} mm")
```

**Check:** `schematic_test.png` shows a recognisable serpentine pattern. The
number of lanes × lane_length should be close to the configured Mcl.

---

## Block 9 — Full test suite

Confirm all 287 tests pass before and after any changes:

```bash
.venv/Scripts/python -m pytest -q
```

Expected: `287 passed` in a few seconds.

For verbose output on a specific module:

```bash
.venv/Scripts/python -m pytest tests/test_design_search.py -v
.venv/Scripts/python -m pytest tests/test_plots.py -v
.venv/Scripts/python -m pytest tests/test_sweep.py -v
.venv/Scripts/python -m pytest tests/test_cli.py -v
```

---

## Coverage Matrix

| Test block | PRD v1 AC | v2 Step |
|------------|-----------|---------|
| 1a basic simulate | AC1, AC2 | — |
| 1b reverse bands | AC3 | — |
| 1c report plots | AC6 | Step 1 |
| 2a/2b operating map | AC5 | — |
| 3a/3b Mode B | — | Step 2 |
| 4a/4b design search | — | Step 3 |
| 5a/5b robustness | — | Step 5 |
| 6a–c compare & calibrate | AC7 | Step 4 |
| 7a JSON export | §4.4 | — |
| 7b results I/O | AC4 | — |
| 8a layout schematic | AC6 | Step 1 |
| 9 test suite | all ACs | all steps |
| (dead-end BC implicit in 1a) | AC8, AC9 | — |
