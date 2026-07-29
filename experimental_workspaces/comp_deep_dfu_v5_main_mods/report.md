# Deep (20 µm) DFU — what oil-main works, and why

**Computational · V5-30-derived · commit `79b7401` · Po = 500 mbar · 10% emulsion**
**DFU count calibrated to the real V5-30 (see below).**

## Question

We want 20 µm-deep DFUs (60×20 µm exit, 120 µm pitch). Deepening the DFU makes each one
draw more oil, so the **oil main** — not the DFU — becomes the limit. For each main-channel
config, at one fixed inlet pressure: how many DFUs fit, what oil flow do we get, and how
flat is the ΔP across the rungs?

## Answer in one line

**Make the oil main as deep as you can (it's free), then choose width for flatness-vs-count.**

## Calibration to the real V5-30 (so N is realistic)

The number of DFUs is set by an **area budget calibrated to your actual V5-30**, not a
guessed die fill. V5-30 routes **N = 11,550** DFUs (Mcl 693 mm / 60 µm pitch) with a
transverse band of `2·Mcw + L_rung = 6000 µm`, so it consumes `6000 µm × 693 mm ≈ 41.6 cm²`
of routing. We use that same 41.6 cm² as the budget for the deep-DFU configs (same
die/process/packing), which bakes in real packing losses (manifolds, serpentine turns,
frame, dicing). The model reproduces N = 11,550 for V5-30's own geometry **exactly**. At the
coarser 120 µm deep-DFU pitch this gives **4,300 – 11,550 DFUs** — fewer than V5-30, as
expected. (For reference the real V5-30 delivers **1.13 mL/hr** oil at 500 mbar.)

## The two levers

| Lever | ΔP flatness | DFU count (area) | Throughput | Verdict |
|---|---|---|---|---|
| **Deeper main** | flatter (ρ −0.51) | **no change** (ρ 0) | more (ρ +0.50) | **free win — always do it** |
| **Wider main** | flatter (ρ −0.40) | fewer (ρ −0.53) | net +0.12 | **tradeoff** |

**Why depth is free:** a deeper main is etched *down*, not *out* — it doesn't touch the
footprint (`band = W_oil + rung + W_water` has no depth term). Lower main resistance → less
droop → far rungs stay fed → flatter ΔP *and* more total oil, at the same DFU count
(`throughput_vs_main.png`: three depth lines separate on the left, overlap on the right).

**Why width is a tradeoff:** wider also flattens, but it eats in-plane area so you fit fewer
DFUs. Each DFU flows a bit more, so net throughput still edges up (ρ +0.12) — a real trade,
not a free lunch like depth.

## The real flatness driver is per-DFU oil draw

Flatness is set by whether the DFUs draw more oil than the main can feed uniformly, not by
the main alone. `dP_over_rungs.png`:

- **`D400_W2000_L4_U15`** (deep+wide main, long/narrow DFUs): ΔP holds ~480 mbar across the
  whole ladder — **spread 5%**. Every DFU works.
- **`D200_W1000_L1_U20`** (shallow+narrow main, short/fat DFUs): ΔP collapses to ~0 within
  the first 20% of the ladder — **spread ~1200%+**. The far 80% of DFUs are starved.

Long/narrow DFUs (high R_DFU) draw little each and keep the ladder flat; short/fat DFUs draw
hard, load the main, and starve the far end. Hence the flatness-vs-throughput tension:

- **Flattest** (spread <10%): deep+wide main, **L = 4 mm, upstream 15 µm** → ~5.5 mL/hr oil.
- **Highest-throughput** (~57 mL/hr): deep+wide main, **L = 1 mm, upstream 20 µm** → spread >100%.

Even the flat option gives **~5× the V5-30 baseline** (1.13 mL/hr) with 2.7× *fewer* DFUs —
each deep DFU simply flows much more. The high-throughput end is ~50× V5-30 but unflat.

## Numbers (54 configs, 500 mbar)

| quantity | range |
|---|---|
| N_DFU (area-limited, V5-30-calibrated) | 4 300 – 11 550 |
| oil throughput | 4 – 57 mL/hr |
| oil velocity at exit | 0.16 – 1.9 mm/s |
| drop frequency* | 1.6 – 20 Hz |
| avg ΔP across DFU | 34 – 482 mbar |
| ΔP spread | 5 – 1200 % |
| water for 10% emulsion | 36 – 518 mL/hr (downstream) |

\* Drop frequency uses the Stage-1 cycle `f = Q_rung / (V_reset + V_drop)`, with
`V_reset = √(w·h)·w·h` (meniscus reset) and `V_drop` from the **regime-blind power-law size
(~52 µm) — the size is not trusted**, so read frequency as indicative. Oil velocity and
throughput are the solid numbers.

## Recommendation

1. **Deepest main your process allows** (here 400 µm). Free flatness + throughput.
2. **Pick width for your goal**: wide (2000 µm) for flatness; the DFU-count cost is real but
   throughput still rises slightly.
3. **Set flatness with the DFUs, not just the main**: longer / narrower DFUs (higher R_DFU)
   flatten the ladder. A flat device is ~5.5 mL/hr, not the ~57 mL/hr you'd get by starving
   most of the ladder.
4. **Dilution water (9× oil, ~36–518 mL/hr) is a downstream number** — don't push it through
   the device water main or it chokes the oil.

## Caveats

- Every config here needs a main **beyond current fab caps** (200 µm deep / 1000 µm wide) —
  `manufacturing_ok = no` throughout. Deeper/wider mains are the fabrication ask.
- **Droplet size is not trusted** (power-law ~52 µm, ~2× extrapolation) → drop *frequency*
  inherits that; oil *velocity/throughput* do not (`droplet-model-regime-blind`).
- Oil-side numbers are at a fixed 5 mL/hr carrier; they shift ≤ ~10% (worst: a rejected
  shallow/narrow main). The 10% dilution water is reported downstream.
- N is calibrated to V5-30's packing via `band = 2·Mcw + L_rung`; if V5-30's 4 mm rung is
  folded (not a straight transverse span) the absolute band differs, but the calibration is
  self-consistent because the same band formula is applied to every config.
- Single fixed pressure (500 mbar).

## Provenance

- Config snapshot: `snapshots/study_config_2026-07-09.yaml` · manifest: `snapshots/run_manifest.md`.
- V5-30 anchor (user-provided): Mcw 1000 µm, rung 4000 µm, pitch 60 µm, N 11,550.
- Fluid: sunflower oil (µ = 0.06 Pa·s) / 2% SDS-water (µ = 0.00089 Pa·s) — same mix as
  `[[comp_large_dfu_stage1_screen]]`, inherited unchanged.
- Numbers: `results/candidate_summary.csv` → `results/results_summary.md`. Figures:
  `dP_over_rungs.png`, `throughput_vs_main.png`.

---

# Part 2 — Device size (manual N): fewer DFUs, wider margin

Part 1 *maximised* N (area budget → 4,300–11,550 DFUs), which is exactly why every config
needed a main beyond current fab caps. Part 2 asks the opposite: set N **by hand** (100 →
10,000) and see whether a *smaller* device is flatter, more robust, and buildable now.
Analysis: `analysis_n_sweep.py` → `results/n_sweep_summary.{csv,md}`, figures
`n_sweep_size_vs_N.png`, `n_sweep_rung_effect.png`. Operating range = the **lowest drive
pressure Po at which every rung still clears the capillary back-pressure** `P_cap ≈ 8.7 mbar`
(Laplace, `γ·cosθ·(1/w+1/h)`); below it the drooped far rungs stop making drops.

## The headline (answers your questions)

**Yes — a smaller device is decisively better on everything except throughput, and it lets
you build within the current fabrication process.** N is the dominant lever, above main size.

| Your question | Answer |
|---|---|
| Fewer rungs → less throughput? | **Yes**, ~proportional to N at low N (fewer parallel paths = higher device resistance). N=1000 gives ~1.3 mL/hr vs ~11 at N=10,000 on the big main. |
| Wider operating range? | **Yes.** Low-N devices work down to ~10 mbar (P_cap floor); high N on a small main needs 70 mbar. Fewer DFUs = lower min drive pressure = more margin. |
| Safer with a smaller device (~1000)? | **Yes** — flat *and* wide-range. |
| Can we stay at **smaller major-channel dimensions**? | **Yes — the big one.** The **current fab-cap main (200 µm deep × 1000 µm wide) runs flat (ΔP spread ≤ 20%) up to ~N=1000–2000** and across the full pressure range. No relaxed-fab main needed if you keep N modest. |
| Can we get away with **shorter rungs**? | **Yes at low N.** On the current-cap main, even 1 mm rungs stay flat (spread ~17%) at N=1000; 4 mm holds to ~N=2700 (`n_sweep_rung_effect.png`). Shorter rungs cost flatness margin but are viable when N is small. |
| Does none of it matter? | It matters a lot — N sets flatness and operating range more strongly than the main does. |

## What you give up, and the ceiling

Throughput scales ~with N. A ~1000-DFU current-fab-cap device makes **~1.3–4.7 mL/hr**
(rung 4→1 mm) — still **~1–4× the V5-30 baseline** (1.13 mL/hr), on a *buildable* process,
vs the 5–57 mL/hr of the beyond-fab-cap Part-1 designs.

There's also a **useful-N ceiling**: on a small main, pushing N too high makes the far rungs
*reverse* (water→oil), so throughput plateaus (~4 mL/hr at N=10,000 on 200×1000) while the
far ~80% of the ladder sits dead — you pay area for DFUs that do nothing. Big mains don't hit
this in the tested range.

## Recommendation (Part 1 + Part 2 together)

- **If you can relax fabrication** (deeper/wider mains): Part 1 — deepest main is free, wide
  for flatness, expect ~5–57 mL/hr depending on the flatness you demand.
- **If you must build on the current process now**: **run ~1000 DFUs of deep 20 µm DFUs on
  the existing 200 × 1000 µm main** — flat, robust down to ~10 mbar, ~1.3–4.7 mL/hr (still
  beats V5-30). This is the cheapest path to a working deep-DFU device, and Part 1's
  "everything needs beyond-cap mains" conclusion only applied because it packed the die full.
