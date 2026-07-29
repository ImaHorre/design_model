# Workspace Brief: Interfacial-Tension Inversion & Capillary-Number Regime Map

**Created**: 2026-07-13
**Status**: active
**Study type**: synthesis

## Research question

Can we back-calculate the interfacial properties we don't measure directly —
the capillary group **γ·cosθ** and the **Stage-2 snap-off prefactor β** — from
the pooled pressure + surfactant-concentration timing data, with uncertainty,
and use them to estimate the **capillary number Ca** and the droplet-formation
**regime** (stall / dripping / blowout) for any device + condition?

## Background

γ (interfacial tension) is unknown for this SDS / silicone-oil system and is a
hard-coded 15 mN/m default in the model (`stage_wise_v3/__init__.py`). It only
ever appears in the data as lumped groups (γ·cosθ in Stage-1 refill; γ×prefactor
in Stage-2 snap-off). This workspace formalises the by-hand inversions already
done in `conc_sweep/analysis_notes.md` and `data/analysis/cvisc_calibration_results.md`
into one reproducible pipeline that emits calibrated constants, updatable the
moment a pendant-drop γ arrives.

**Key physics (established from code + prior analysis):**
- Droplet **size is geometry-set**, not Ca-set (po_sweep: D≈25 µm flat while
  frequency changes 3.4×). Ca gates the *regime*, not the size.
- Stage-1 refill residual ⇒ a fixed capillary back-pressure P_cap ≈ 2 kPa ≈ 20 mbar.
- Onset (~30 mbar, observed) ⇒ ΔP_rung ≈ P_cap ≈ 1.9 kPa — an independent second
  anchor on the *same* γ·cosθ group (cross-check, not a γ splitter).
- **Junction Ca ≈ 10⁻⁵ across the whole feasible range** (even at 1200 mbar) —
  so "jetting at ~1000 mbar, device start/end" is a **pressure/spatial-manifold
  blowout**, NOT a Ca=0.3 capillary transition. The absolute γ/θ split therefore
  still needs the pendant drop.

## Approach

- **Model components:** `stepgen` hydraulic solver (`simulate`, `rung_resistance`,
  `iterative_solve`, `compute_metrics`); junction Ca formula from
  `regime_classification.calculate_capillary_number`.
- **Analysis method:** pool the master event CSV; fit P_cap from the Stage-1
  Po-scaling shape; back-calc γ·cosθ([SDS]) from Stage-1 driving pressure; fit
  Stage-2 β from the S2-vs-[SDS] ratio; bootstrap all uncertainties; hold out
  0.25 %/0.125 % (near/below CMC) as validation. Emit `calibrated_constants.yaml`.

## Data sources

| ID | Device | Date | Conditions | File | Notes |
|----|--------|------|------------|------|-------|
| @exp-2026-04-24-V5-8-1 | V5-8-1 | 2026-04-24 | Po 200–600 mbar, Qw 2–20 mL/hr, [SDS] 0.125–2 %, SDS/silicone-oil | `../po_sweep/data/stage_timings.csv` | **Master CSV** — the po/qw/conc "sweeps" are filtered views of this one file. [SDS] is in the `ContPhase` column. Absolute stage times are 0.5× the conc_sweep notes (FPS convention); ratios/scaling identical. NaCas rows excluded. |

## Success criteria

1. Loader reproduces the conc_sweep S1/S2 **ratios** vs [SDS] (done: 1.00/1.05/1.22/1.33/1.87). ✓
2. Fitted P_cap ≈ 1.5–2.5 kPa and γ·cosθ ≈ 12–18 mN/m, consistent with the two
   independent routes (Stage-1 residual + onset anchor).
3. Held-out points: good Stage-1/2 prediction above CMC; documented miss at 0.125 %
   (regime change, not a bug).
4. `regime_estimator` places stall near the observed onset and reports Ca≪1 (dripping)
   everywhere feasible, flagging the high-Po failure as pressure/blowout.

## Key findings

*(Full detail in `report.md`; constants in `calibrated_constants.yaml`.)*

- **Capillary entry pressure P_entry = 1898 Pa [1474, 2748]** (from the ~30 mbar
  onset) → **γ·cosθ ≈ 14 mN/m** at 2% SDS, matching the model's 15 mN/m default.
  This is the "make droplets at all" threshold and the recommended `dP_cap_ow_Pa`
  (currently 5000 Pa ⇒ ~2.5× too high; predicts onset ~63 mbar vs observed ~30).
- **Junction Ca ≈ 1e-5 across the whole feasible range** (even 1200 mbar), ~1e4–1e5×
  below the ~0.3 jetting threshold. Size is geometry-set; Ca gates neither size nor jetting.
- **γ·cosθ vs [SDS]** rises 14→36 mN/m as [SDS] falls 2%→0.25%; dP_eff ratios
  (1.00/0.99/0.90/0.80) reproduce conc_sweep exactly.
- **Stage-1 refill back-pressure ≈ 6.4 kPa** (from Po-scaling) EXCEEDS the capillary
  entry pressure ⇒ extra non-capillary velocity-dependent dissipation (not γ).
- **Stage-2 β ≈ 0** above CMC — snap-off is γ-insensitive in the dripping window.
- **Jetting (~1000 mbar, device start/end) is a pressure/manifold blowout, not a Ca
  transition** — needs the manifold geometry to reproduce spatially.

## Cross-workspace links

- [[conc_sweep]] — source of the S1/S2-vs-[SDS] hand analysis this formalises.
- [[po_sweep]] — owns the master CSV; Po-scaling and size-stability evidence.
- [[qw_sweep]] — Qw dependence (same master CSV).
- [[comp_manifold_parametrization]] — needed to model the *spatial* start/end jetting.

## Open questions

- Pendant-drop γ for SDS/silicone-oil (keystone: splits γ from cosθ and fixes β).
- Sessile θ([SDS]) on the device substrate.
- Low-pressure frequency data (30–200 mbar) to pin the onset anchor.
- High-pressure / manifold data to characterise the blowout boundary.
