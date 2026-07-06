# Report — Large-DFU Stage-1 Hydraulic Screen

**Date**: 2026-07-06
**Workspace**: `experimental_workspaces/comp_large_dfu_stage1_screen/`
**Study type**: computational (model-only — no experimental data)
**Model commit**: `4f415877968db6c34eda03905cbb516778238067`

## Question

Can a ladder of large/deep O/W DFUs (20–50 µm deep, 0.5–4 mm long, 10–1000
rungs) hydraulically refill (Stage 1) fast enough — `t_S1 ≤ 1 s` for **every**
DFU — at a practical drive pressure (ideal ≤ 500 mbar, hard ceiling
1000 mbar)? Droplet formation is treated as instantaneous; Stage-2/cyclic
snap-off is deferred to a follow-up workspace for surviving candidates.

## Headline answer

**Stage-1 refill is not the bottleneck for ladders up to ~100 DFUs — every
one of the 384 candidates with N_DFU ≤ 100 passes at the lowest swept
pressure band (≈50 mbar). At N_DFU = 1000 the screen starts to bite, and it
bites through the main channel, not the DFU itself.**

Pass rates (576 candidates; pass = `DP_eff > 0` and `t_S1 ≤ 1 s` on every rung):

| Criterion | Passing |
|---|---|
| Stage-1 pass at 500 mbar | 519 / 576 (90.1%) |
| Stage-1 pass at 1000 mbar | 530 / 576 (92.0%) |
| Pass at 500 mbar AND manufacturing OK (main depth ≤ 200 µm) | 157 / 576 (27.3%) |

All 46 candidates that never pass ≤ 1000 mbar have N_DFU = 1000, concentrated
at the deep end (4 at 30 µm, 15 at 40 µm, 27 at 50 µm depth).

## Key findings

### 1. The failure mode is main-channel loading, not DFU resistance

The single-DFU closed form (`t_S1 ∝ L/(depth · DP_eff)`) predicts deeper DFUs
refill *faster* and should need *less* pressure. The sweep shows the
opposite at large N: Spearman rho between depth and required pressure is
**+0.71 at N_DFU = 1000** (n/a at N = 10, where everything passes at the
minimum). The mechanism: `R_DFU` falls ~40× from 20 µm to 50 µm depth
(9.9×10¹⁵ → 2.5×10¹⁴ Pa·s/m³), so a 1000-rung ladder of deep DFUs draws far
more oil, the oil main channel drops hundreds of mbar along its length, and
`DP_eff` collapses at the far rungs — the worst rung governs the pass. For the
same reason, *longer* DFUs (higher `R_DFU`) mildly *help* at N = 1000
(rho = −0.27), reversing the naive length penalty. Pass counts at 500 mbar for
N = 1000, by DFU depth: 48/48 (20 µm) → 42/48 (30 µm) → 29/48 (40 µm) →
16/48 (50 µm).

### 2. Main-channel size is the design lever for large ladders

At N_DFU = 1000, passes at 500 mbar rise 29 → 48 → 58 (of 64) as main-channel
depth goes 200 → 300 → 400 µm, and the refill-time spread across the ladder
roughly halves over the same range (fig 4). This collides directly with the
current manufacturing setting `max_main_depth_um = 200`: 362 of the 519
Stage-1 passes at 500 mbar fail the manufacturing check. **The large-N design
question is therefore not "can the DFU refill" but "how deep a main channel
can we build (or how do we split the ladder into shorter manifolded
segments)".** The manufacturing limits are tunable diagnostics in
`study_config.yaml`, kept separate from the physics pass/fail.

### 3. Even the marginal N = 1000 passes are close to the criterion

Among passing N = 1000 candidates the worst-rung `t_S1` at 500 mbar reaches
0.97 s — essentially at the 1 s threshold — versus ≤ 0.04 s for N ≤ 100. Any
Stage-2 follow-up short-list should carry `t_S1_max`, not just the boolean.

### 4. The flat 12 mbar back-pressure is conservative across this grid

The diagnostic Laplace estimate `γ·cos(30°)·(1/depth + 1/exit_width)` is
8.7 mbar at 20 µm depth falling to 3.5 mbar at 50 µm — below the flat
12 mbar constant everywhere in the sweep. If the constant is roughly right at
V5-30 scale, using it unchanged for large DFUs overstates capillary
back-pressure and the screen errs conservative. (Per-candidate values in
`P_cap_laplace_mbar`, `candidate_summary.csv`.)

### 5. Qw sensitivity — hypothesis confirmed

Adjusting Qw (continuous/water flow) from the fixed 5 mL/hr to hit a 10%
target emulsion fraction changes Stage-1 performance negligibly: worst case
(N = 1000 representative, Qw 5 → 15.9 mL/hr) moves mean `DP_DFU` by −6.6% and
worst-rung `t_S1` by −3.0%; for N ≤ 100 the change is < 0.2%. The fixed-Qw
sweep is therefore a valid screen — emulsion fraction can be tuned via Qw
downstream without re-screening. Note the raw emulsion fractions at fixed
Qw = 5 mL/hr vary enormously (median 33% at N = 10 to 93% at N = 1000 among
passing candidates at 500 mbar), which is why they are reported as a
diagnostic column, not a pass criterion.

### 6. Verification status

- Depth/length monotonicity checks confirm the expected single-DFU-limit signs
  are **reversed at large N by the network effect** (finding 1) — the
  per-N_DFU breakdown in `results/results_summary.md` isolates this cleanly.
- N_DFU degradation check: mean required pressure 50 → 51.6 → 373 mbar and
  mean t_S1 spread 0.2% → 15% → 121% for N = 10 → 100 → 1000, as expected.
- Hard check "no candidate with an inactive rung marked passing": **PASS**
  (asserted in code).
- V5-30 reset-length sanity: `sqrt(30×10) = 17.3 µm` vs observed 19–21 µm
  (~10–15% low; within the loose bound; flagged in BRIEF Open Questions).

## Recommendation

Proceed to the Stage-2/cyclic follow-up with a short-list drawn from
N_DFU = 1000 passes at 500 mbar, stratified by DFU depth — but resolve the
main-channel manufacturability question first (deeper-than-200-µm mains vs
segmented/manifolded ladders), since it dominates large-N feasibility. For
N ≤ 100 devices, Stage-1 hydraulics impose no meaningful constraint anywhere
in this grid and Stage-2 physics will decide everything.

## Data provenance

- **Config snapshot**: `snapshots/study_config_2026-07-06.yaml` (verbatim copy
  of `study_config.yaml` at run time; DeviceConfigs are built in Python from
  it — no per-candidate YAML exists)
- **Run manifest**: `snapshots/run_manifest.md` (model commit, exact command,
  key fluid/geometry parameters)
- **Experimental data**: none — computational workspace; no `data/` folder by
  design
- **Figures** (all generated by `analysis.py` from
  `results/candidate_summary.csv`, except fig 5):
  - Fig 1 — `figures/fig_01_pressure_requirement_vs_depth.png` ← `results/candidate_summary.csv`
  - Fig 2 — `figures/fig_02_pressure_requirement_vs_length.png` ← `results/candidate_summary.csv`
  - Fig 3 — `figures/fig_03_pressure_requirement_vs_N.png` ← `results/candidate_summary.csv`
  - Fig 4 — `figures/fig_04_uniformity_vs_main_channel_size.png` ← `results/candidate_summary.csv`
  - Fig 5 — `figures/fig_05_top_candidate_pressure_profiles.png` ← direct
    re-simulation of the top-5 candidates (per-rung arrays are not persisted
    to CSV; candidate selection from `results/candidate_summary.csv`)
- **Tables**: pass-rate, best/worst, verification and Qw-sensitivity tables in
  `results/results_summary.md` ← `results/candidate_summary.csv` and direct
  solves recorded therein; per-pressure detail in
  `results/per_pressure_long.csv`
- **Wiki check**: `wiki/index.md` reviewed 2026-07-06 — current wiki content
  covers Stage-2/snap-off literature (Ca-independence, backflow mechanism);
  nothing constrains the Stage-1 quantities used here (12 mbar back-pressure,
  `V_reset`), which remain open questions.
