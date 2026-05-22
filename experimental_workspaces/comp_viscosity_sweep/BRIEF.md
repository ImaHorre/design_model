---
study-type: computational
model: Stage-wise droplet model (hydraulic network + Poiseuille Stage 1)
parameter-varied: Oil viscosity, water viscosity
devices: W11 (O/W and W/O), V5-30
---

## Purpose

Model-only parameter sweeps varying oil and water viscosity to understand sensitivity of Stage 1
timings and pressure profiles to fluid properties. No experimental comparison.

Useful for: checking model behaviour before running experiments with different oil/surfactant systems
(e.g. MCT oil vs silicone oil, or NaCas continuous phase).

## Files

- `figures/` — viscosity sweep plots:
  - `ow_w11_water_viscosity_sweep.png` — O/W W11, varying water viscosity
  - `wo_v5_30_viscosity_pressure_profile.png` — W/O V5-30, pressure profile at different viscosities
  - `wo_w11_oil_viscosity_sweep.png` — W/O W11, varying oil viscosity
  - `wo_w11_viscosity_pressure_profile.png` — W/O W11, pressure profile at different viscosities
