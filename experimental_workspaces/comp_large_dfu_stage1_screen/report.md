# Report — Large-DFU Stage-1 Hydraulic Screen

**Date**: 2026-07-06 · **Type**: computational (model-only) · **Model commit**: `4f41587`

## Bottom line

For deep DFUs (large droplets), Stage-1 refill is a problem *only if you build a
long single ladder of many of them*. And you probably shouldn't: a 50 µm-deep
DFU makes a ~140 µm droplet carrying **~166× the oil volume** of a V5-30
droplet, so you need far fewer DFUs to hit the same output — which lands you
back in the easy hydraulic regime and sidesteps the whole issue.

---

## The one mechanism that drives everything

Depth is the master variable, and it cuts both ways:

- A DFU's hydraulic resistance falls **~40× from 20 µm to 50 µm depth**
  (`R_DFU ∝ 1/depth⁴`). Individually, a deep DFU refills *faster*.
- But low resistance means each deep DFU **draws more oil**. Line up a thousand
  of them and the cumulative draw drops the pressure along the **oil** main
  channel faster than the channel can supply it. The far rungs starve.

Confirmed in the model: for a passing 1000×50 µm ladder at 500 mbar, the oil
main channel drops **343 mbar** end-to-end while the water main drops only
**8 mbar**. The usable driving pressure at the last DFU falls from 492 mbar
(inlet) to 157 mbar (far end). This is an **oil-side** problem — the water main
is nearly flat because water flow is small.

---

## Design considerations for deep DFUs

**1. The oil main channel is the master lever — make it big.**
At 1000×50 µm, passes at ≤500 mbar go **29 → 48 → 58 (of 64)** as the main
channel deepens 200 → 300 → 400 µm, and refill-time non-uniformity roughly
halves. A large (deep) oil main keeps the pressure drop *in the DFUs, where it
does work,* instead of *in the channel, where it's wasted.* This is your
primary knob. **Constraint:** every good long-ladder config needs a main
deeper than the current **200 µm manufacturing limit** — that limit, not the
physics, is the real blocker for long deep-DFU ladders.

**2. You cannot claw it back with DFU geometry.**
Narrowing/lengthening the DFU upstream raises its resistance and helps a
little, but not enough. At the manufacturable 200 µm main, even the most
resistive DFU in the whole sweep (4 mm long, narrowest AR=1 upstream) only just
scrapes a pass at the 1000 mbar ceiling; every other 1000×50 µm config fails
outright. The ~40× resistance loss from going deep is simply too large to
recover through upstream shape within buildable limits.

**3. If you truly need many deep DFUs, parallelise.**
Run the count as several shorter ladders fed by a manifold rather than one long
strip. Ten parallel 100-DFU ladders = same total DFUs, but each sub-ladder
sits in the easy regime (shallow 200 µm mains, ~50 mbar, manufacturable). Cost
is the distribution network. This is the clean escape from the oil-main limit.

**4. Best option: use fewer DFUs, because deep ones are volumetrically huge.**
Droplet diameter and per-droplet oil volume (calibrated `D = k·w^a·h^b`):

| DFU depth | Exit (w×h) | Droplet D | Oil volume vs V5-30 |
|---|---|---|---|
| V5-30 ref | 30×10 µm | 25 µm | 1× |
| 20 µm | 60×20 µm | 52 µm | 9× |
| 30 µm | 90×30 µm | 80 µm | 33× |
| 40 µm | 120×40 µm | 109 µm | 82× |
| **50 µm** | 150×50 µm | **138 µm** | **166×** |

At equal formation frequency, one 50 µm DFU replaces ~166 V5-30 DFUs on oil
throughput. Even if big droplets form an order of magnitude slower (a Stage-2
quantity **not** modelled here — treat 166× as an upper bound), a deep design
matching V5-30-class output likely wants only **tens to low-hundreds** of DFUs,
not thousands. At 50 µm the pitch is 300 µm, so 100 DFUs is a **3 cm** ladder —
comfortably in the regime where Stage-1 imposes no constraint at all.

**5. Regime caveat — the deep-DFU operating point may fall outside step-emulsification.**
The predicted droplet sizes above assume the device stays in the
step-emulsification (SE) regime, where droplet size is set by geometry and is
Ca-independent. A preliminary capillary-number check says this is at risk. Using
the steady mean oil throughput velocity from the screen (µ_oil = 60 cP,
σ = 15 mN/m), a 50 µm DFU has nozzle Ca ≈ 0.016 at 200 mbar rising to ≈ 0.04–0.08
at 500–1000 mbar — at or above the SE→jetting/balloon ceiling of ~0.0125–0.03
reported in the wiki (`@montessori2020-step-emulsification`, `@chakraborty2017-step-emulsification`,
`[theory]`). Two compounding concerns: (a) the pressures needed for Stage-1
refill are the same pressures that push Ca out of SE; (b) the O/W fluid system
has viscosity ratio λ = µ_c/µ_d ≈ 0.015, far outside the literature-validated
λ ≈ 0.1–10 (near 1), in the direction that *narrows* the SE window. Above SE, the
138–200 µm geometric prediction does not hold — droplets become larger and
flow-rate-dependent. **This is a model-vs-theory divergence to resolve before
committing to deep DFUs, and it reinforces "fewer DFUs, driven gently."**
Caveat on the caveat: Ca here uses steady mean throughput, not the true cyclic
pinch velocity (a Stage-2 quantity), so treat it as an order-of-magnitude flag.

---

## Small vs long device — the direct answer

Your two scenarios map onto the sweep because pitch = 300 µm at 50 µm depth:

| Your device | ≈ grid point | Verdict |
|---|---|---|
| ~4 cm, 100 DFUs | N=100 | **Works everywhere.** All 50 µm configs pass at ≤200 mbar, most at 50 mbar. Main-channel depth barely matters. Full design freedom. |
| ~30 cm, 1000 DFUs | N=1000 | **Conditional.** Needs a deep oil main: 200 µm main essentially fails, 300 µm is a coin-flip at high pressure, 400 µm works (best configs at 50–100 mbar). All passing configs bust the 200 µm manufacturing limit. |

Both *can* hit good pressures — but the long device only does so with a main
channel you currently can't manufacture, whereas the small device is
unconstrained. Given consideration 4, the long 1000-DFU device is likely
solving a throughput problem you don't have.

---

## Recommendation

If the goal is deep DFUs for large droplets: **size the DFU count from the
droplet-volume math first** (you'll likely need far fewer than intuition
suggests), which keeps you in the easy N ≤ 100 regime. Only if a genuine
high-count requirement survives that should you either (a) commit to a
deeper-than-200 µm oil main channel, or (b) parallelise into manifolded
sub-ladders. Then hand the short-list to the Stage-2/cyclic follow-up, which
will decide formation frequency and actual output — the quantity this Stage-1
screen deliberately does not model.

---

## Data provenance

- **Config snapshot**: `snapshots/study_config_2026-07-06.yaml` (verbatim; per-candidate DeviceConfigs built in Python from it)
- **Run manifest**: `snapshots/run_manifest.md` (commit, command, fluid/geometry parameters)
- **Experimental data**: none — computational workspace, no `data/` folder by design
- **Figures** (from `results/candidate_summary.csv`; fig 5 from direct re-simulation):
  fig 1 depth, fig 2 length, fig 3 ladder-size N, fig 4 uniformity vs main-channel size, fig 5 top-candidate pressure profiles
- **Tables/detail**: `results/results_summary.md` (aggregates, verification, Qw-sensitivity); `results/per_pressure_long.csv` (per-pressure detail). Droplet-volume table uses the calibrated `droplet_model` (k=3.3935, a=0.339, b=0.7198) applied to the sweep exit geometry and the V5-30 30×10 µm reference — geometric estimate, no frequency model.
- **Wiki**: `wiki/index.md` reviewed 2026-07-06 — covers Stage-2/snap-off literature; nothing constrains the Stage-1 quantities used here (12 mbar back-pressure, `V_reset`), which remain open questions.
