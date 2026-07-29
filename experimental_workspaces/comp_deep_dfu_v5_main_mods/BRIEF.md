# Workspace Brief: Deep (20 µm) DFU V5 Main-Channel Study

**Created**: 2026-07-09
**Status**: active
**Study type**: computational
**Device**: V5-30-derived (deep-DFU variant)

## Research question

We run V5-30 today with 10 µm-deep DFUs. We want **20 µm-deep DFUs** (60×20 µm exit,
120 µm pitch). Deepening the DFU makes each one draw more oil, so the **oil main**, not the
DFU, becomes the limit. For each oil-main config, at one fixed inlet oil pressure:

> **How many DFUs fit in the area budget, what oil flow do we get, and how flat is the ΔP
> across the rungs — and which main-channel changes make it work?**

## Approach (simple, model-only)

For each config (main depth × width × rung length × upstream width = 54 configs), at a
single fixed Po = 500 mbar:

- **N_DFU** from an area budget: `band = W_oil + L_rung + W_water`,
  `N = floor(area / (band · pitch))`. Depth does NOT enter band → depth is free. The area
  budget (41.6 cm²) is **calibrated to reproduce the real V5-30 (N = 11,550)**, not guessed.
- **Oil flow**: `Q_oil_total`, oil velocity at the DFU exit, and drop frequency via the
  Stage-1 cycle `f = Q_rung / (V_reset + V_drop)`, `V_reset = √(w·h)·w·h`.
- **Flatness**: avg ΔP over the rungs + ΔP spread %.
- **Water flow for a 10% emulsion** = 9 × Q_oil (a downstream number, not injected through
  the device — that would choke the oil).

Model components: `stepgen.models.hydraulics.simulate` (plain steady mixed-BC),
`stepgen.models.droplets` (V_drop / D_pred), `stepgen.config` built per config.

**Deliberately dropped** (vs the earlier over-built version): Ca / step-emulsification
regime analysis, φ / clog sweeps, the serpentine geometry, the 8-vs-10 die sweep, and the
6 figures. Assume drops form; keep it to throughput + flatness + N.

## Data sources

None — computational / model-only. Fluid inherited unchanged from the sunflower-oil /
SDS-water O/W system: µ_oil = 0.06 Pa·s, µ_water = 0.00089 Pa·s.

## Success criteria

A clear, per-config picture of which oil-main changes keep the DFU ΔP flat and how that
trades against throughput and DFU count — i.e. *what works and why*.

## Current status

Implemented and run (2026-07-09, commit 79b7401); 54 configs at 500 mbar. All sanity
asserts pass. See `report.md` and `results/results_summary.md`.

## Key findings

- **N calibrated to V5-30**: area budget 41.6 cm² reproduces the real V5-30 (11,550 DFUs)
  exactly; deep-DFU configs land at **4,300–11,550 DFUs** (fewer than V5-30, as expected at
  120 µm pitch).
- **Depth is a free win.** Deeper oil main → flatter ΔP (ρ −0.51) + more throughput
  (ρ +0.50) at **no DFU-count cost** (ρ 0) — a deeper channel is etched down, not out.
- **Width is a tradeoff.** Wider → flatter (ρ −0.40) but fewer DFUs (ρ −0.53); net
  throughput edges up (ρ +0.12).
- **Flatness is really set by per-DFU oil draw.** Long/narrow DFUs (high R_DFU) keep the
  ladder flat (spread ~5%); short/fat DFUs starve the far 80% of rungs (spread >1000%).
- **Flatness fights throughput**: flat ≈ 5.5 mL/hr oil; max ≈ 57 mL/hr but badly unflat.
  Deep DFU gives ~5–50× the V5-30 baseline (1.13 mL/hr @ 500 mbar).
- Every Part-1 config needs a main **beyond current fab caps** — but only because the area
  budget packs the die full (see Part 2).

### Part 2 — manual N sweep (`analysis_n_sweep.py`)

- **Fewer DFUs → flatter ΔP + wider operating range**, throughput ~proportional to N.
- **A ~1000-DFU deep-DFU device runs flat (spread ≤ 20%) on the CURRENT fab-cap main
  (200 µm deep × 1000 µm wide)** and works down to ~10 mbar — no relaxed fab needed. It makes
  ~1.3–4.7 mL/hr (rung 4→1 mm), still ~1–4× V5-30. **Dropping N is the cheapest route to a
  buildable deep-DFU device.**
- Shorter rungs are viable at low N (even 1 mm stays flat at N=1000 on the current-cap main).
- **Useful-N ceiling**: on a small main, past some N the far rungs reverse (water→oil) and
  throughput plateaus while most of the ladder sits dead.

## Honest scope limits

- **Droplet size not trusted** (power-law ~52 µm, ~2× extrapolation) → drop *frequency*
  inherits that; oil *velocity / throughput* do not (`droplet-model-regime-blind`).
- Oil-side numbers at a fixed 5 mL/hr carrier; ≤ ~5% sensitive for the recommended
  deep/wide configs, up to ~23% for the rejected shallow/narrow ones. 10% dilution is
  downstream.
- Single fixed pressure (500 mbar), one area budget (80 cm²), no serpentine turn losses.

## Cross-workspace links

- [[comp_large_dfu_stage1_screen]] — established oil-main loading (not Stage-1) limits
  large-N deep ladders; this workspace quantifies the main-channel design levers.

## Open questions

- True droplet size for these deep 60×20 µm DFUs (would make the frequency trustworthy).
- Where on the flatness↔throughput curve to sit — a device-integration decision.
