---
study-type: experimental
device: V5-8-1 (ID B, V5-30 geometry)
emulsion: Silicone oil / SDS-water
date: 2026-04
parameter-varied: [SDS] (0.125–2% mass), CMC ≈ 0.24%
fixed: key cross-concentration comparison at Po=200 mbar, Qw=5 mL/hr
---

## Research question

How does SDS concentration affect Stage 1 and Stage 2, and what is the physical mechanism?

## Key findings

- Stage 1 rises 1.87× from 2% → 0.125% SDS. Dominant mechanism: falling effective driving pressure
  dP_eff (−20% from 2%→0.25%), not rising V_reset (+7%). Both caused by increasing contact angle.
- Stage 2 flat above CMC; rises below CMC but experimental increase (1.45×) is ~2× smaller than
  γ-scaling prediction (3.33×) — literature γ values may be too high for this system.
- 0.125% SDS is a qualitatively different regime: Stage 3 dominant, droplets ~34 µm vs ~25 µm.
- C_visc is not a universal constant — it encodes contact-angle effects and varies with [SDS].

## Files

- `analysis_notes.md` — full analysis
- `figures/fig_01–05.png`

## Model config

`configs/v5_30.yaml`

## Cross-references

Results from this experiment feed into `sds_sweep_synthesis/report.md` (Experiment 3 of 3).
