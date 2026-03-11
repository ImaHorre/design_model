# Stepgen Model Comprehensive Summary

This document provides a detailed overview of all models implemented in the stepgen system, their physical characteristics, mathematical formulations, and key differences.

## Overview

The stepgen system implements a multi-layered modeling approach for droplet formation in microfluidic devices, ranging from fundamental physical models to advanced time-dependent simulations.

---

## 1. Physical Droplet Models

### 1.1 Droplet Diameter Model (Power-Law)

**Location:** `stepgen/models/droplets.py`

**Mathematical Model:**
```
D = k · w^a · h^b  [m]
```

**Physical Characteristics:**
- **Input Parameters:**
  - `w` = junction exit_width [m]
  - `h` = junction exit_depth [m]
  - `k` = empirical coefficient (≈3.3935)
  - `a` = power on exit_width (≈0.3390)
  - `b` = power on exit_depth (≈0.7198)

**Key Features:**
- Exit depth dominates droplet size (b > a)
- Empirically calibrated coefficients
- Used across all hydraulic models for consistency

### 1.2 Droplet Volume Model

**Mathematical Model:**
```
V_d = (π / 6) · D³  [m³]
```

**Physical Characteristics:**
- Assumes perfectly spherical droplets
- Direct geometric calculation from diameter

### 1.3 Refill Volume Model

**Mathematical Model:**
```
V_refill = exit_width × exit_height × L
where L = refill_length_factor × exit_height
```

**Physical Characteristics:**
- **Purpose:** Captures additional volume during droplet formation
- **Toggle:** `enable_refill_volume` (default: false)
- **Factor:** `refill_length_factor` (default: 2.0)
- **Effect:** Reduces effective droplet frequency when enabled

### 1.4 Droplet Frequency Model

**Mathematical Model:**
```
f = Q_rung / (V_d + V_refill)  [Hz]
```

**Physical Characteristics:**
- **Q_rung:** Rung volumetric flow [m³/s]
- **V_d:** Droplet volume [m³]
- **V_refill:** Optional refill volume [m³]
- Positive flows = oil-into-water (ACTIVE) droplet production

---

## 2. Hydraulic Models

### 2.1 Steady-State Model

**Location:** `stepgen/models/generator.py` (via `hydraulic_models.py`)

**Type:** Threshold/hysteresis iterative solver

**Physical Characteristics:**
- **Rung Classification:**
  - `ACTIVE`: ΔP > dP_cap_ow → oil→water droplet production
  - `REVERSE`: ΔP < -dP_cap_wo → water→oil reverse flow
  - `OFF`: Otherwise → pinned, negligible flow

**Mathematical Framework:**
- Iterative conductance matrix solver
- Affine RHS offsets for capillary thresholds
- Convergence based on regime classification stability

**Key Parameters:**
- `dP_cap_ow_Pa`: Oil→water threshold (≈35-50 mbar)
- `dP_cap_wo_Pa`: Water→oil threshold (≈30 mbar)
- `max_iter`: Maximum iterations (default: 50)

**Assumptions:**
- Steady-state operation (no time dynamics)
- Duty factor = 1.0 (continuous operation)
- Uniform junction properties

### 2.2 Duty Factor Model

**Location:** `stepgen/models/time_state/duty_factor.py`

**Type:** Empirical scaling of steady-state model

**Physical Characteristics:**
- **Purpose:** Captures stop-go cycling effects in real DFUs
- **Duty Factor (φ):** Typically 0.17-0.20
- **Effect:** Reduces effective flow rates and frequencies by ~5-6x

**Mathematical Model:**
```
Q_effective = φ × Q_steady
f_effective = φ × f_steady
```

**Key Features:**
- Two modes: global (uniform φ) and per-rung (position-dependent φ)
- Addresses experimental frequency overprediction
- Maintains steady-state pressure solution

### 2.3 Time-State DFU Model

**Location:** `stepgen/models/time_state/time_state_dfu.py`

**Type:** Time-dependent state machine simulation

**Physical Characteristics:**
- **DFU States:**
  - `OPEN`: Active droplet formation
  - `PINCH`: Flow constriction during droplet detachment
  - `RESET`: Recovery/preparation for next cycle

**Mathematical Framework:**
- Discrete-time simulation with configurable time steps
- State-dependent conductance modifications
- Probabilistic or deterministic state transitions

**Key Parameters:**
- `simulation_time_ms`: Total simulation duration (default: 5000ms)
- Phase duration distributions
- State transition probabilities

**Advantages:**
- Captures temporal dynamics of droplet formation
- More physically realistic than duty factor scaling
- Provides time-series output for analysis

### 2.4 Time-State Filling Model

**Location:** `stepgen/models/time_state/time_state_filling.py`

**Type:** Enhanced time-state model with filling mechanics

**Physical Characteristics:**
- **Additional Physics:**
  - Junction filling dynamics
  - Volume-dependent state transitions
  - Enhanced refill volume calculations

**Key Features:**
- Most comprehensive physical model
- Incorporates detailed junction mechanics
- Higher computational cost
- Provides volume breakdown analysis

---

## 3. Configuration Differences

### Current Device Configurations

#### W11 Configuration (`configs/w11.yaml`)
- **Junction:** 15µm × 5µm exit
- **Main Channel:** 200µm depth × 2000µm width
- **Rungs:** 5µm depth × 8µm width
- **Operating:** 300 mbar, 5 mL/hr
- **Refill Volume:** Disabled

#### V5_30 Configuration (`configs/v5_30.yaml`)
- **Junction:** 30µm × 10µm exit (2x larger)
- **Main Channel:** 200µm depth × 1000µm width
- **Rungs:** 10µm depth × 8µm width (2x deeper)
- **Operating:** 200 mbar, 5 mL/hr (lower pressure)
- **Channel Length:** 693mm (much longer)

**Key Differences:**
- V5_30 has larger junction dimensions → larger droplets
- V5_30 has deeper rungs → higher conductance
- V5_30 has longer main channel → more rungs (~11,550 vs ~25,000)
- Different pressure operating points

---

## 4. Performance Metrics Model

**Location:** `stepgen/models/metrics.py`

**Computed Metrics:**
- **Flow Metrics:** Q_spread, Q_per_rung_avg, active_fraction
- **Droplet Metrics:** D_pred, f_pred_mean, f_pred_min/max
- **Mechanical Risk:** delam_line_load, collapse_index
- **Pressure Metrics:** P_peak, dP_spread, dP_avg

**Physical Significance:**
- **Q_spread_pct:** Flow uniformity across active rungs
- **Active_fraction:** Percentage of rungs in droplet production
- **Delam_line_load:** Delamination risk (P_peak × channel_width)
- **Collapse_index:** Aspect ratio for channel collapse risk

---

## 5. Model Comparison Framework

**Location:** `stepgen/models/model_comparison.py`

**Capabilities:**
- Side-by-side comparison of all hydraulic models
- Performance timing and validation
- JSON export for analysis
- Experimental data comparison

**Typical Frequency Progression:**
1. **Steady:** Baseline frequency (highest)
2. **Duty Factor:** ~5-6x reduction
3. **Time-State:** Variable reduction based on phase dynamics
4. **Time-State Filling:** Additional reduction due to filling mechanics

---

## 6. Key Physical Differences Summary

| Model Type | Time Dynamics | Duty Factor | Physical Realism | Computational Cost |
|------------|---------------|-------------|------------------|-------------------|
| Steady-State | None | 1.0 | Low | Low |
| Duty Factor | None | 0.17-0.20 | Medium | Low |
| Time-State DFU | Full | Variable | High | Medium |
| Time-State Filling | Full | Variable | Highest | High |

## 7. Use Case Recommendations

- **Steady-State:** Initial design, parameter sweeps, comparative studies
- **Duty Factor:** Quick empirical correction for experimental comparison
- **Time-State DFU:** Detailed droplet dynamics analysis
- **Time-State Filling:** Most accurate predictions, research applications

---

## 8. Future Model Extensions

The modular architecture supports additional models:
- Surface tension dependent models
- Temperature-dependent viscosity models
- Particle-loaded fluid models
- Multi-phase droplet formation

## 9. Validation Status

All models use the same:
- Power-law droplet diameter correlation (k=3.3935, a=0.3390, b=0.7198)
- Capillary pressure thresholds (35-50 mbar ow, 30 mbar wo)
- Junction geometry definitions
- Resistance calculation methods

This ensures consistency across model comparisons while allowing each model to capture different physical phenomena.