# Plan: Q_rung Spatial Comparison — Model vs Experimental

## Context

`stepgen compare` currently shows aggregate error metrics and scatter plots that aren't useful
for diagnosing *why* the model is wrong. The compare run on W11_4_7 showed:
- Diam MAE = 0.66 µm, bias = +0.05 µm → diameter model is essentially correct
- Freq MAE = 10.84 Hz, bias = +10.84 Hz → model predicts ~5–6× too many drops/sec

Since f = Q_rung / V_droplet and D is correct (so V_droplet is correct), the hydraulic model
is massively overestimating flow through each junction. To diagnose this we need to see the
Q_rung spatial profile — model vs experiment — for each of the 4 operating conditions.

**Experimental Q_rung is derivable from data we already have:**
```
Q_exp = frequency_hz × (π/6 × (droplet_diameter_um × 1e-6)³)   [m³/s]
```

---

## What to build

### 1. New plot: Q_rung vs position (model + experiment), 4 subplots

One subplot per unique (Po, Qw) in the experimental CSV. Each subplot shows:
- **Model line**: `SimResult.Q_rungs * 3.6e12` [nL/hr] vs fractional position, shaded/colored by
  regime (ACTIVE=green, REVERSE=red, OFF=grey)
- **Experimental scatter**: `Q_exp * 3.6e12` [nL/hr] at each DFU fractional position, black dots

### 2. Per-condition numerical breakdown (CLI print)

For each (Po, Qw), print a compact table:
```
--- Po=300.0 mbar  Qw=1.5 mL/hr ---
                         Model     Experiment
  D [µm]                11.95      11.56 ± 0.42
  f_mean [Hz]           12.34       1.92 ± 0.14
  Q_rung_mean [nL/hr]    1.21       0.19 ± 0.03
  active rungs [%]       78.5%      —
```
Model values come from SimResult + droplet_frequency; experimental values from comp_df rows
for that (Po, Qw).

---

## Files to modify

| File | Change |
|------|--------|
| `stepgen/io/experiments.py` | Add `Q_exp_m3s` column to comp_df; extract `_build_sim_cache`; return `(comp_df, sim_cache)` from `compare_to_predictions` |
| `stepgen/viz/plots.py` | Add `plot_qrung_comparison(comp_df, config, sim_cache)` |
| `stepgen/cli.py` | Unpack new return value; print per-condition breakdown; save new plot |

---

## Detailed implementation

### `stepgen/io/experiments.py`

**Step A — Extract helper `_build_sim_cache`:**
```python
def _build_sim_cache(config, exp_df):
    from stepgen.models.generator import iterative_solve
    cache = {}
    for _, row in exp_df.iterrows():
        key = (float(row["Po_in_mbar"]), float(row["Qw_in_mlhr"]))
        if key not in cache:
            cache[key] = iterative_solve(config, Po_in_mbar=key[0], Qw_in_mlhr=key[1])
    return cache
```

**Step B — Modify `compare_to_predictions`:**
- Call `_build_sim_cache` at the top (replaces the inline cache dict)
- After building result_df, add column:
  ```python
  import math
  result_df["Q_exp_m3s"] = result_df.apply(
      lambda r: r["frequency_hz"] * (math.pi / 6) * (r["droplet_diameter_um"] * 1e-6) ** 3,
      axis=1,
  )
  ```
- Change return to: `return result_df, cache`

### `stepgen/viz/plots.py`

**New function `plot_qrung_comparison(comp_df, config, sim_cache)`:**
- Determine unique (Po, Qw) pairs sorted by (Po, Qw)
- Create figure with `len(pairs)` subplots arranged in a 2-column grid
- For each subplot:
  1. Get `sim = sim_cache[(Po, Qw)]`
  2. Compute fractional positions: `frac = sim.x_positions / sim.x_positions[-1]`
  3. Get regimes via `classify_rungs(sim.P_oil - sim.P_water, dP_cap_ow, dP_cap_wo)`
  4. Plot model Q_rungs:
     - ACTIVE segments in green, REVERSE in red, OFF in grey (use regime mask)
     - `Q_nLhr = sim.Q_rungs * 3.6e12`
  5. Overlay experimental points:
     - `sub = comp_df[(comp_df.Po_in_mbar==Po) & (comp_df.Qw_in_mlhr==Qw)]`
     - `plt.scatter(sub.position, sub.Q_exp_m3s * 3.6e12, color='black', zorder=5)`
  6. Labels: title="Po={Po:.0f} mbar, Qw={Qw:.1f} mL/hr", x="Channel position", y="Q_junction (nL/hr)"
- Return figure

Reuse existing imports: `classify_rungs`, `RungRegime` from `stepgen.models.generator`.

### `stepgen/cli.py` — `_cmd_compare`

```python
# Change:
comp_df = compare_to_predictions(config, exp_df)
# To:
comp_df, sim_cache = compare_to_predictions(config, exp_df)
```

After existing metrics print, add per-condition breakdown:
```python
from stepgen.models.droplets import droplet_diameter, droplet_frequency
from stepgen.models.generator import classify_rungs

D_pred_um = droplet_diameter(config) * 1e6
for (Po, Qw), sim in sorted(sim_cache.items()):
    sub = comp_df[(comp_df.Po_in_mbar == Po) & (comp_df.Qw_in_mlhr == Qw)]
    # Model stats
    dP = sim.P_oil - sim.P_water
    regimes = classify_rungs(dP, config.droplet_model.dP_cap_ow_Pa, config.droplet_model.dP_cap_wo_Pa)
    active_mask = [r.name == "ACTIVE" for r in regimes]
    Q_active = sim.Q_rungs[active_mask]
    f_model_mean = float(np.mean(droplet_frequency(Q_active, droplet_diameter(config)))) if Q_active.size else 0.0
    Q_model_mean_nLhr = float(np.mean(Q_active) * 3.6e12) if Q_active.size else 0.0
    active_pct = 100 * sum(active_mask) / len(regimes)
    # Experimental stats
    f_exp = sub.frequency_hz
    Q_exp_nLhr = sub.Q_exp_m3s * 3.6e12
    D_exp = sub.droplet_diameter_um
    print(f"\n  --- Po={Po:.0f} mbar  Qw={Qw:.1f} mL/hr ---")
    print(f"  {'':25s}  {'Model':>10}  {'Experiment':>20}")
    print(f"  {'D [µm]':25s}  {D_pred_um:>10.2f}  {D_exp.mean():>8.2f} ± {D_exp.std():.2f}")
    print(f"  {'f_mean [Hz]':25s}  {f_model_mean:>10.2f}  {f_exp.mean():>8.2f} ± {f_exp.std():.2f}")
    print(f"  {'Q_rung_mean [nL/hr]':25s}  {Q_model_mean_nLhr:>10.3f}  {Q_exp_nLhr.mean():>8.3f} ± {Q_exp_nLhr.std():.3f}")
    print(f"  {'active rungs [%]':25s}  {active_pct:>9.1f}%  {'—':>20}")
```

Save new plot:
```python
fig = plot_qrung_comparison(comp_df, config, sim_cache)
path = out_dir / "compare_qrung.png"
fig.savefig(path, dpi=150)
print(f"  → {path}")
```

---

## Verification

```bash
stepgen compare configs/w11.yaml w11_4_7.csv
```

Expected:
- Per-condition table printed for all 4 (Po, Qw) pairs
- `compare_qrung.png` created showing 4 subplots
- Model Q_rung line clearly much higher than experimental scatter (explaining the freq bias)
- Existing `compare_diameter.png`, `compare_frequency.png`, `spatial_comparison.png` unchanged
