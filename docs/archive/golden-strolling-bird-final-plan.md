# Edge Emulsion Linear Model Updates - Final Implementation Plan

## Context
We need to add a toggle feature to the linear droplet model that includes "refill volume" - additional fluid volume that gets pushed out at the same flowrate but doesn't contribute to droplet formation. This reduces the effective flow for droplet production and thus reduces droplet frequency.

**Problem**: Current linear model overpredicts droplet frequency by ~5-6× because it assumes continuous flow through DFUs, but in reality there are refill phases where no droplets are produced.

**Solution**: Add `V_refill = exit_width × exit_height × L` where `L = 2 × exit_height` to the total cycle volume, making frequency `f = Q_open / (V_drop + V_refill)` when enabled.

## Implementation Approach

### 1. Configuration Changes

**File: `stepgen/config.py`**

Add new fields to `DropletModelConfig` class (lines 179-181):
```python
# NEW: Refill volume toggle for linear model
enable_refill_volume: bool = False          # Toggle on/off for refill volume
refill_length_factor: float = 2.0          # L = factor × exit_height (default: 2.0)
```

Update `_parse_droplet_model()` function (around line 360) to handle new fields:
```python
def _parse_droplet_model(d: dict[str, Any]) -> DropletModelConfig:
    return DropletModelConfig(
        k=float(d.get("k", 3.3935)),
        a=float(d.get("a", 0.3390)),
        b=float(d.get("b", 0.7198)),
        dP_cap_ow_mbar=float(d.get("dP_cap_ow_mbar", 30.0)),
        dP_cap_wo_mbar=float(d.get("dP_cap_wo_mbar", 30.0)),
        hydraulic_model=str(d.get("hydraulic_model", "steady")),
        duty_factor_phi=float(d.get("duty_factor_phi", 0.18)),
        duty_factor_mode=str(d.get("duty_factor_mode", "global")),
        tau_pinch_ms=float(d.get("tau_pinch_ms", 50.0)),
        tau_reset_ms=float(d.get("tau_reset_ms", 20.0)),
        g_pinch_frac=float(d.get("g_pinch_frac", 0.01)),
        dt_ms=float(d.get("dt_ms", 5.0)),
        simulation_time_ms=float(d.get("simulation_time_ms", 3000.0)),
        L_retreat_um=float(d.get("L_retreat_um", 10.0)),
        L_breakup_um=float(d.get("L_breakup_um", 5.0)),
        # NEW fields
        enable_refill_volume=bool(d.get("enable_refill_volume", False)),
        refill_length_factor=float(d.get("refill_length_factor", 2.0)),
    )
```

### 2. Core Droplet Model Enhancement

**File: `stepgen/models/droplets.py`**

Add new function for refill volume calculation:
```python
def refill_volume(config: "DeviceConfig") -> float:
    """
    Calculate refill volume for linear model when enabled.

    V_refill = exit_width × exit_height × L
    where L = refill_length_factor × exit_height

    Returns 0.0 if refill volume is disabled.
    """
    if not config.droplet_model.enable_refill_volume:
        return 0.0

    jc = config.geometry.junction
    L = config.droplet_model.refill_length_factor * jc.exit_depth
    return jc.exit_width * jc.exit_depth * L
```

Modify `droplet_frequency()` function to accept optional refill volume:
```python
def droplet_frequency(
    Q_rung: "Union[float, np.ndarray]",
    D: float,
    V_refill: float = 0.0,
) -> "Union[float, np.ndarray]":
    """
    Droplet production frequency with optional refill volume.

    f = Q_rung / (V_d + V_refill)  [Hz]

    Parameters
    ----------
    Q_rung : scalar or ndarray
        Rung volumetric flow [m³/s].
    D : float
        Droplet diameter [m].
    V_refill : float, optional
        Additional refill volume per droplet [m³]. Default: 0.0

    Returns
    -------
    Frequency in Hz; same type and shape as Q_rung.
    """
    V_drop = droplet_volume(D)
    V_total = V_drop + V_refill
    return Q_rung / V_total
```

### 3. Integration with Metrics Calculation

**File: `stepgen/models/metrics.py`**

Update `compute_metrics()` function (around line 132) to use refill volume:
```python
# ── Droplet model ──────────────────────────────────────────────────────
D_pred = droplet_diameter(config)
V_refill = refill_volume(config)  # NEW: Get refill volume

if np.any(active_mask):
    f_arr = droplet_frequency(result.Q_rungs[active_mask], D_pred, V_refill)  # Modified
    f_pred_mean = float(np.mean(f_arr))
    f_pred_min  = float(np.min(f_arr))
    f_pred_max  = float(np.max(f_arr))
    dP_avg      = float(np.mean(dP[active_mask]))
else:
    f_pred_mean = 0.0
    f_pred_min  = 0.0
    f_pred_max  = 0.0
    dP_avg      = 0.0
```

### 4. CLI Support

**File: `stepgen/cli.py`**

Add CLI arguments to simulate parser (around line 550):
```python
p_sim.add_argument("--enable-refill", action="store_true",
                   help="Enable refill volume calculation (overrides config).")
p_sim.add_argument("--disable-refill", action="store_true",
                   help="Disable refill volume calculation (overrides config).")
p_sim.add_argument("--refill-factor", type=float, default=None,
                   metavar="FACTOR", help="Refill length factor: L = factor × exit_height (overrides config).")
```

Add override logic in `_cmd_simulate()` function:
```python
# Apply CLI parameter overrides for refill volume
if hasattr(args, 'enable_refill') and args.enable_refill:
    config.droplet_model.__dict__['enable_refill_volume'] = True
    print("  Override: enable_refill_volume = True")

if hasattr(args, 'disable_refill') and args.disable_refill:
    config.droplet_model.__dict__['enable_refill_volume'] = False
    print("  Override: enable_refill_volume = False")

if hasattr(args, 'refill_factor') and args.refill_factor is not None:
    config.droplet_model.__dict__['refill_length_factor'] = args.refill_factor
    print(f"  Override: refill_length_factor = {args.refill_factor}")
```

## Files to Modify

1. **`stepgen/config.py`** - Add refill volume fields to DropletModelConfig and parsing
2. **`stepgen/models/droplets.py`** - Add refill_volume() function and modify droplet_frequency()
3. **`stepgen/models/metrics.py`** - Update metrics calculation to use refill volume
4. **`stepgen/cli.py`** - Add CLI arguments and override logic

## Backward Compatibility

- Default `enable_refill_volume: false` ensures no behavior change for existing configs
- When disabled, `refill_volume()` returns `0.0`, making `droplet_frequency()` work exactly as before
- Optional `V_refill` parameter in `droplet_frequency()` defaults to `0.0`
- Config parsing handles missing fields gracefully with defaults

## Verification

After implementation, test with:
1. `stepgen simulate config.yaml` (should behave exactly as before)
2. `stepgen simulate config.yaml --enable-refill` (should reduce frequency by including refill volume)
3. `stepgen simulate config.yaml --refill-factor 3.0` (should use L = 3 × exit_height)

This provides a simple, toggleable linear model enhancement that captures the refill volume physics while maintaining full backward compatibility.
