# StepGen Designer — Practical User Guide

This guide walks through two real use cases:

1. **Designing from a target** — you want ~15µm drops and need to find a geometry and understand what frequencies you'll get across a range of operating pressures.
2. **Modelling an existing device** — you have a physical device with known specs, and you want to predict its behaviour, generate pressure maps, and compare to measurements.

---

## Background: what the model actually does

The device is a "ladder" — two long parallel channels (oil rail and water rail) connected by many short microchannels (rungs). Oil is fed at a controlled inlet pressure; water is fed at a controlled flow rate. At each rung junction (the "step"), a droplet forms when the oil–water pressure difference exceeds a capillary threshold.

The model solves for:
- Pressure along both rails
- Flow through each rung
- Which rungs are active (making drops), reversed, or off
- Droplet size and frequency at each rung

**Droplet size model** (empirical power law, calibrated to your data):

```
D = k · exit_width^a · exit_depth^b
```

Calibrated values:  `k = 3.3935`,  `a = 0.339`,  `b = 0.720`  (SI throughout)

Depth dominates strongly — doubling the exit depth increases D by ~65%; doubling width increases D by only ~27%.

| exit_width | exit_depth | Predicted D |
|-----------|-----------|------------|
| 0.3 µm    | 1.0 µm    | 1.0 µm     |
| 15 µm     | 5 µm      | 12 µm      |
| 30 µm     | 10 µm     | 25 µm      |

---

## Scenario 1 — Designing for 15 µm drops

### Step 1: Find the exit geometry

The main lever is `exit_depth`. Fix that based on your fabrication process (it's usually the channel etch depth), then back-calculate `exit_width`.

```
exit_width = (D_target / (k · exit_depth^b))^(1/a)
```

| exit_depth | exit_width needed for 15 µm |
|-----------|--------------------------|
| 3 µm      | ~85 µm                   |
| 5 µm      | ~29 µm                   |
| 7 µm      | ~14 µm   ← practical     |
| 10 µm     | ~7 µm                    |
| 15 µm     | ~3 µm                    |

A 7 µm deep channel with 14 µm wide exit is a practical target — achievable with standard soft lithography.

### Step 2: Write the config

Save this as `my_15um_device.yaml`:

```yaml
fluids:
  mu_continuous: 0.00089    # Pa·s — water (carrier phase)
  mu_dispersed:  0.03452    # Pa·s — oil  (droplet phase)
  emulsion_ratio: 0.3

geometry:
  main:
    Mcd: 100.0e-6   # 100 µm — main channel depth (deeper than rungs)
    Mcw: 500.0e-6   # 500 µm — main channel width
    Mcl: 50.0e-3    # 50 mm routed length → Nmc = floor(50e-3 / 100e-6) = 500 rungs

  rung:
    mcd: 7.0e-6     # 7 µm — rung depth  (matches exit_depth)
    mcw: 14.0e-6    # 14 µm — rung width (matches exit_width)
    mcl: 200.0e-6   # 200 µm — rung length
    pitch: 100.0e-6 # 100 µm pitch → 500 rungs in 50 mm
    constriction_ratio: 1.0

  junction:
    exit_width: 14.0e-6   # 14 µm — controls droplet size
    exit_depth:  7.0e-6   #  7 µm — controls droplet size (dominant)

operating:
  Po_in_mbar: 200.0   # starting estimate — we'll sweep this
  Qw_in_mlhr: 5.0

droplet_model:
  k: 3.3935
  a: 0.3390
  b: 0.7198
  dP_cap_ow_mbar: 50.0   # threshold to form drops (oil→water)
  dP_cap_wo_mbar: 30.0   # threshold for reverse flow (water→oil)
```

### Step 3: Run a single simulation to verify

```bash
stepgen simulate my_15um_device.yaml
```

Expected output:
```
=== simulate ===
  Config  : my_15um_device.yaml
  Po      : 200.0 mbar
  Qw      : 5.00 mL/hr
  Nmc     : 500
  active  : ...%
  D_pred  : ~15.0 µm      ← this is what you're checking
  f_mean  : ... Hz
  fits    : True/False
```

If `D_pred` isn't 15 µm, your exit_width or exit_depth in the YAML doesn't match what you intended — double-check the values.

If `active` is 0%: your oil pressure is below the capillary threshold. Raise `Po_in_mbar` (e.g. to 300–400 mbar).

### Step 4: Map pressure vs frequency

This is the key step — you want to know: **at what oil pressures do drops form, and how fast?**

```bash
stepgen map my_15um_device.yaml \
    --Po-min 50 --Po-max 600 --Po-n 30 \
    --Qw-min 1  --Qw-max 20  --Qw-n 8 \
    --out-dir ./map_15um
```

This sweeps 30 oil pressures × 8 water flows and saves heatmaps to `./map_15um/`:

- `map_active_fraction.png` — where the device is actually making drops
- `map_reverse_fraction.png` — where back-flow is occurring (bad)
- `map_Q_uniformity_pct.png` — how uniform the rung flow is
- `map_dP_uniformity_pct.png` — how uniform the driving force is
- `map_P_peak_Pa.png` — peak pressure (delamination risk)

**Reading the active_fraction map:** look for the region where active_fraction ≈ 1.0 (all rungs making drops) and reverse_fraction ≈ 0. That's your operating window.

From the map you'll be able to read off approximate operating pressure ranges for each water flow. The window summary is also printed:

```
Strict windows computed : 8
Relaxed windows computed: 8
```

### Step 5: Get per-rung frequencies at a specific pressure

Once you've identified a good operating pressure from the map, do a detailed single simulation and generate all plots:

```bash
stepgen simulate my_15um_device.yaml --Po 350 --Qw 10
stepgen report   my_15um_device.yaml --Po 350 --Qw 10 --out-dir ./report_15um
```

This saves:
- `pressure_profiles.png` — P_oil(x) and P_water(x) along the device
- `rung_frequencies.png` — f(i) at each rung → this shows how uniform production is
- `regime_map.png` — which rungs are active/reversed/off
- `rung_flows.png` — Q_rung(i)
- `rung_dP.png` — ΔP across each rung

**The `rung_frequencies.png` plot directly answers "what frequency at what pressure"** — run `report` at multiple Po values to see how it changes.

### Step 6: Python API for a frequency-vs-pressure curve

If you want to plot frequency vs oil pressure programmatically:

```python
import numpy as np
import matplotlib.pyplot as plt
from stepgen.config import load_config
from stepgen.models.generator import iterative_solve
from stepgen.models.metrics import compute_metrics

config = load_config("my_15um_device.yaml")

Po_values = np.linspace(100, 600, 50)   # mbar
f_means   = []
actives   = []

for Po in Po_values:
    result  = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=10.0)
    metrics = compute_metrics(config, result)
    f_means.append(metrics.f_pred_mean)
    actives.append(metrics.active_fraction)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
ax1.plot(Po_values, f_means)
ax1.set_ylabel("Mean droplet frequency [Hz]")
ax1.set_title("Frequency vs oil pressure  (Qw = 10 mL/hr)")

ax2.plot(Po_values, [a * 100 for a in actives], color="tab:green")
ax2.set_ylabel("Active fraction [%]")
ax2.set_xlabel("P_oil_in [mbar]")
ax2.axhline(90, color="gray", linestyle="--", label="90% threshold")
ax2.legend()

fig.tight_layout()
fig.savefig("freq_vs_pressure.png", dpi=150)
```

This gives you the full picture: where the device switches on, how frequency scales with pressure, and where it saturates.

---

## Scenario 2 — Modelling an existing physical device

You have a device already made. You know the geometry from your mask/SEM and want to understand the pressure-flow behaviour and compare predictions to measurements.

### Step 1: Translate your specs into a config

You'll need:

| What you know | Config field |
|--------------|-------------|
| Main channel depth (etch depth) | `geometry.main.Mcd` |
| Main channel width | `geometry.main.Mcw` |
| Total channel length (routed) | `geometry.main.Mcl` |
| Microchannel depth | `geometry.rung.mcd` |
| Microchannel width | `geometry.rung.mcw` |
| Microchannel length | `geometry.rung.mcl` |
| Rung-to-rung spacing | `geometry.rung.pitch` |
| Exit junction width | `geometry.junction.exit_width` |
| Exit junction depth | `geometry.junction.exit_depth` |
| Oil inlet pressure you'll run at | `operating.Po_in_mbar` |
| Water flow rate | `operating.Qw_in_mlhr` |

For a device with 5 µm deep, 15 µm wide microchannels (making ~12 µm drops), a 100 µm main channel, and 50 µm pitch:

```yaml
fluids:
  mu_continuous: 0.00089
  mu_dispersed:  0.03452
  emulsion_ratio: 0.3

geometry:
  main:
    Mcd: 100.0e-6    # your main channel etch depth [m]
    Mcw: 500.0e-6    # your main channel width [m]
    Mcl: 20.0e-3     # routed length; Nmc = floor(20e-3 / 50e-6) = 400 rungs

  rung:
    mcd: 5.0e-6      # microchannel depth [m]
    mcw: 15.0e-6     # microchannel width [m]
    mcl: 150.0e-6    # microchannel length [m]
    pitch: 50.0e-6   # rung-to-rung pitch [m]
    constriction_ratio: 1.0

  junction:
    exit_width: 15.0e-6   # exit width at the step [m]
    exit_depth:  5.0e-6   # exit depth at the step [m]
    # → predicted D = 12.0 µm

operating:
  Po_in_mbar: 200.0
  Qw_in_mlhr: 5.0

droplet_model:
  k: 3.3935
  a: 0.3390
  b: 0.7198
  dP_cap_ow_mbar: 50.0
  dP_cap_wo_mbar: 30.0
```

### Step 2: Simulate and check D_pred

```bash
stepgen simulate my_existing_device.yaml
```

Check that `D_pred` in the output matches what you observe experimentally. If it doesn't, the exit geometry in the YAML is wrong (check exit_width / exit_depth), or you need to recalibrate the model (see Step 5 below).

### Step 3: Generate all plots for your operating point

```bash
stepgen report my_existing_device.yaml --Po 200 --Qw 5 --out-dir ./device_report
```

Open the plots:

- **`pressure_profiles.png`** — shows whether the oil pressure drops significantly along the rail. A flat P_oil profile means all rungs see similar driving force → good uniformity. A steep drop means the first rungs hog all the flow.
- **`regime_map.png`** — tells you immediately if some rungs are reversed or off at this operating point.
- **`rung_dP.png`** — ΔP at each rung. Should be relatively flat for a well-designed device.
- **`rung_frequencies.png`** — predicted drops/second per rung. A flat profile means uniform production.

### Step 4: Map out the operating window

This tells you how sensitive the device is to pressure fluctuations:

```bash
stepgen map my_existing_device.yaml \
    --Po-min 50 --Po-max 500 --Po-n 25 \
    --Qw-min 1  --Qw-max 15  --Qw-n 6 \
    --out-dir ./device_map
```

Look at `map_active_fraction.png`. The "good" zone (high active fraction, low reverse fraction) is your operating window. If it's narrow, the device is pressure-sensitive and will be hard to run stably.

### Step 5: Compare predictions to measurements

If you have experimental droplet size and/or frequency data, create a CSV:

```csv
device_id,Po_in_mbar,Qw_in_mlhr,position,droplet_diameter_um,frequency_hz,notes
dev1,200,5,10,11.8,42.3,rung 10 measured by microscopy
dev1,200,5,50,12.1,40.1,
dev1,300,5,10,12.0,65.7,
dev1,300,5,50,11.9,63.2,
```

`position` is the rung index (0-based) where you made the measurement.

Run the comparison:

```bash
stepgen compare my_existing_device.yaml measurements.csv --out comparison.csv
```

Output:
```
=== compare ===
  Points         : 4
  Diam MAE       : 0.15 µm       ← mean absolute diameter error
  Diam RMSE      : 0.18 µm
  Diam bias      : +0.05 µm      ← positive = model overpredicts
  Freq MAE       : 2.3 Hz
  Freq RMSE      : 2.7 Hz
  Freq bias      : -1.8 Hz       ← negative = model underpredicts frequency
```

Also saves `compare_diameter.png` and `compare_frequency.png` — predicted vs measured scatter plots with a 1:1 line. Points on the line = perfect prediction.

### Step 6: Calibrate the droplet model to your device

If diameter prediction is consistently off (large bias), scale the model to your data:

```bash
stepgen compare my_existing_device.yaml measurements.csv --calibrate --out comparison_cal.csv
```

`--calibrate` adjusts `k` so that the mean predicted diameter matches the mean measured diameter. It doesn't touch `a` or `b`. This is a simple one-parameter fit — useful if your exit geometry definition differs slightly from what the model expects.

Or in Python, with more control:

```python
from stepgen.config import load_config
from stepgen.io.experiments import load_experiments, calibrate_droplet_model, compare_to_predictions, compute_compare_report

config = load_config("my_existing_device.yaml")
exp_df = load_experiments("measurements.csv")

# Before calibration
comp_before = compare_to_predictions(config, exp_df)
report_before = compute_compare_report(comp_before)
print(f"Before: bias = {report_before.diam_bias_um:+.2f} µm")

# Calibrate
config_cal = calibrate_droplet_model(config, exp_df)
comp_after  = compare_to_predictions(config_cal, exp_df)
report_after = compute_compare_report(comp_after)
print(f"After:  bias = {report_after.diam_bias_um:+.2f} µm")
print(f"New k = {config_cal.droplet_model.k:.4f}")
```

---

## Common issues

**Active fraction is 0% at any pressure**

Your oil pressure threshold (`dP_cap_ow_mbar`) may be too high for the rung resistance. Either lower the threshold or raise Po. Also check that `mcd` and `mcw` are physically correct — a very high-resistance rung means very little flow, very little driving force.

**All rungs show as REVERSED**

Water pressure is dominating oil pressure everywhere. This happens when water flow rate is too high for the given geometry. Lower `Qw_in_mlhr` or raise `Po_in_mbar`.

**D_pred is wildly off from what you observe**

The exit_width and exit_depth in your YAML may not match your actual junction geometry. In many devices, the "step" is defined by the channel cross-section (so exit_depth = mcd, exit_width = mcw). Set them accordingly and re-check.

**Fits footprint = False**

Increase `footprint_area_cm2` or reduce `Mcl`. The layout model routes the channels in a serpentine — if the total routed length doesn't fit in the chip area it flags this.

**Frequency predictions look right but uniformity is poor**

A steep pressure drop along the oil rail means early rungs get more flow. The fix is to increase main channel cross-section (Mcd, Mcw) relative to rung resistance, or reduce the number of rungs. The `dP_uniformity_pct` metric quantifies this — aim for < 10%.

---

## Quick reference: key config levers

| You want to change | Config field | Effect |
|-------------------|-------------|--------|
| Droplet size | `exit_depth` (primary), `exit_width` | D ∝ h^0.72 · w^0.34 |
| Droplet frequency | `Po_in_mbar`, `Qw_in_mlhr` | More pressure/flow → more drops |
| Number of rungs | `Mcl` (or `pitch`) | Nmc = floor(Mcl/pitch) |
| Rung resistance | `mcd`, `mcw`, `mcl` | Higher R → lower Q per rung at same ΔP |
| Uniformity | `Mcd`, `Mcw` (main channel size) | Bigger main → flatter pressure profile |
| Operating window width | Balance rung R vs main R | High rung/main ratio → wider window |
| Mechanical risk | `delam_line_load`, `collapse_index` | Reduce P_peak or Mcw |
