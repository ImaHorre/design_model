---
study-type: experimental
device: V5-30 (ID A)
emulsion: "DISPUTED — see 'Fluid identity' below / 2% SDS-water"
date: 2026-04
parameter-varied: Po (200–500 mbar)
fixed: Qw=5 mL/hr, [SDS]=2%
---

## Fluid identity — unresolved discrepancy (flagged 2026-07-29)

This frontmatter previously read **"Silicone oil / 2% SDS-water"**, and the wiki page
`@ws-2026-07-13-po-sweep-v5-8-1` inherited that reading. The raw data disagrees:

| Source | Says |
|---|---|
| this BRIEF (as originally written) | Silicone oil |
| `data/stage_timings.csv`, column `DispPhase` | `SO` |
| `CLAUDE.md` (project convention) | **SO = sunflower oil; never interpret SO as silicone oil** |

Not cosmetic: sunflower oil is ~60 cP while silicone oils span ~5–100 cP. Exit Ca scales
linearly with µ, and this dataset is the **only** measurement of exit Ca Peak has
(0.00035–0.00137 at µ = 60 cP, γ = 5 mN/m — see the wiki page's derived-Ca section). Every
regime verdict in the design model that anchors on this device moves with the answer.

**Needs a human answer.** Per CLAUDE.md, a fluid mismatch is flagged rather than resolved by
inference. Once settled, correct this frontmatter, the wiki setup table, and the derived Ca
table together.

## Research question

Does a simple Poiseuille rung-flow model correctly predict Stage 1 timing across a range of oil inlet pressures?

## Key findings

> **CORRECTION 2026-06-08**: `data/stage_timings.csv` has been corrected ×0.5 on all Stage*_s columns (fps=25 used instead of 50 in original analysis). All absolute timing values below are pre-correction and should be halved. Derived quantities (Po scaling exponent, C_visc calibration) may need revisiting.

Pre-correction findings (timing values are 2× too large):
- Stage 1 scales as Po^-1.17 (vs Po^-1.0 ideal) — consistent with ~12 mbar capillary back-pressure.
- C_visc ≈ 0.95 when using measured V_reset from L_menpoint ≈ 30 µm. **Needs re-checking after fps correction — if Stage 1 times halve, C_visc calibration result may shift.**
- Stage 2 ≈ 0.19 s pre-correction → corrected ~0.095 s — much less pressure-sensitive than Stage 1.
- Droplet diameter ≈ 27 µm — geometry-controlled, no significant Po dependence. **Unaffected** (spatial measurement).

## Files

- `analysis_notes.md` — full analysis with figures reference
- `data/stage_timings.csv` — raw stage timing data
- `figures/` — primary analysis figures (fig_01–07)
- `plot_types/` — exploratory plot variants

## Model config

`configs/v5_30.yaml`

## Cross-references

Results from this experiment feed into `sds_sweep_synthesis/report.md` (Experiment 1 of 3).
