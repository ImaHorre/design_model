# Wiki Ingest Handoff — comp_large_dfu_stage1_screen

**Date**: 2026-07-06
**Workspace**: experimental_workspaces/comp_large_dfu_stage1_screen/
**Device**: synthetic sweep grid (large/deep O/W DFU ladders; no physical device)
**Citekey**: @ws-2026-07-06-large-dfu-stage1-screen
**Study type**: computational (model-only, no experimental data)
**Model commit**: 4f41587

> Handoff for a wiki session to file per the ingest workflow. The full report,
> figures, and CSVs stay in the workspace — the wiki gets the synthesis below
> plus a citekey pointer back here. Workspace BRIEF is still `Status: active`;
> file the open questions now, treat the experiment page as provisional.

## What was measured [experimental]

None — this is a model-only screen. No lab data.

## What the model predicted [model-v3, 2026-07]

- Stage-1 hydraulic refill (t_S1 ≤ 1 s on every rung) is **not limiting** for DFU
  ladders up to N ≈ 100; every 20–50 µm-deep candidate passes at ~50 mbar.
- At N ≈ 1000 the constraint appears and is a **main-channel (oil-side) loading**
  effect, not a DFU-resistance effect: deep DFUs have ~40× lower resistance
  (R ∝ 1/depth⁴), draw more oil, and drop the oil main channel by ~343 mbar
  end-to-end (vs ~8 mbar on the water main), starving the far rungs. Worst rung
  governs the pass.
- Design levers, ranked: (1) deeper oil main channel is the master knob (passes
  at 500 mbar rise 29→48→58 of 64 as the main deepens 200→400 µm) but collides
  with the 200 µm manufacturing limit; (2) DFU upstream geometry cannot recover
  the resistance loss within buildable limits; (3) parallelise into manifolded
  sub-ladders; (4) use fewer DFUs.
- Droplet-volume scaling (calibrated `D = k·w^a·h^b`, geometric only): a 50 µm
  DFU (150×50 µm exit) → ~138 µm droplet = ~166× the oil volume of a V5-30
  25 µm droplet. So a deep design matching V5-30-class output needs far fewer
  DFUs (tens–low-hundreds), staying in the easy hydraulic regime.

## Divergences noticed during analysis

- **Model vs theory — droplet size.** design_model power law gives 138 µm for a
  50 µm-deep (h/w = 1/3) exit; literature `d ≈ 4h` (`@montessori2020-step-emulsification`,
  h/w = 1/5) gives ~200 µm — a ~45% divergence. The design_model law is
  calibrated only up to 30×10 µm (a 5× extrapolation here) and is regime-blind.
  → candidate `wiki/contradictions/` page (model-v3 vs theory), and links to
  `open-questions/step-emulsification-prefactor` (prefactor at h/w = 1/3 untested).
- **Regime risk.** At Stage-1 operating pressures the estimated nozzle Ca is
  ~0.016–0.08 (200–1000 mbar), at/above the SE→jetting/balloon ceiling of
  ~0.0125–0.03 (`@montessori2020`, `@chakraborty2017`). If the device exits SE,
  the Ca-independent geometric size prediction fails. Compounded by viscosity
  ratio λ = µ_c/µ_d ≈ 0.015, far outside the validated λ ≈ 0.1–10 envelope
  (`claims/step-emulsification-viscosity-insensitive` notes the SE window
  narrows at low λ). Ca estimate uses steady mean throughput, not cyclic pinch
  velocity — order-of-magnitude flag, not a committed number.

## Open questions surfaced

1. Does a deep DFU (~50 µm) driven at the pressures needed for Stage-1 refill
   stay in the step-emulsification regime, or fall into jetting/balloon where
   size becomes flow-dependent? Needs a proper Ca/We check at the cyclic
   operating point. → `open-questions/`
2. What is the droplet-size prefactor at aspect ratio h/w = 1/3 (vs the
   literature 1/5)? → extends existing `open-questions/step-emulsification-prefactor`.
3. Does step-emulsification hold at all for a very viscous dispersed phase
   (λ ≈ 0.015, sunflower oil in water) — the opposite extreme from the
   validated near-unity λ? → `open-questions/`
4. Model-side: the design_model droplet power law is regime-blind and
   extrapolated 5× beyond its ≤30×10 µm calibration. → `wiki/model/open-questions.md`.
5. Should the flat 12 mbar Stage-1 capillary back-pressure constant vary with
   depth? Diagnostic Laplace estimate falls 8.7→3.5 mbar over 20→50 µm.
   → `wiki/model/open-questions.md`.

## Source artifacts (stay in workspace; reference by path, do not copy into wiki)

- report.md (narrative + design considerations)
- results/results_summary.md, results/candidate_summary.csv, results/per_pressure_long.csv
- figures/fig_01…fig_05
- snapshots/run_manifest.md (commit 4f41587)
