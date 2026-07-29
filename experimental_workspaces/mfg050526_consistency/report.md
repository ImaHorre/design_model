# V5-30 Device Consistency Report — Batch 050526

**Generated:** 2026-05-07 · Three devices from the same production batch, tested under identical conditions.

---

> **CORRECTION — 2026-06-08: FPS error discovered**
>
> All Stage timing and production-rate values in this report are **incorrect** due to a systematic error:
> the video analysis tool used fps = 25, but the videos for devices **3D and 4C** were recorded at **50 fps**.
> This makes all Stage*_s values for 3D and 4C **2× too long** and their frequencies **2× too low**.
>
> Device **1B** was genuinely recorded at 25 fps and is **unaffected**.
>
> **What this changes:**
> - The reported "40% spread in production rate" is an artefact of the fps mismatch, not manufacturing variation.
> - After correction (×0.5 on 3D and 4C timing values), 3D and 4C frequencies are expected to match 1B — indicating **all three devices are consistent**.
> - The "1B was an outlier with 2× frequency" observation is now explained: 1B was the only correctly analysed device.
> - Droplet diameter conclusions are **unaffected** (spatial measurement, not timing-derived).
>
> To regenerate this report with correct values:
> 1. Run: `python scripts/correct_fps_error.py <path_to_stage_timings_Mfg050526_combined.csv> --skip-device V5-30-260413-1B`
> 2. Re-run: `python experimental_workspaces/mfg050526_consistency/analysis.py`

---

## Quick verdict (PRE-CORRECTION — values below are wrong for 3D and 4C)

| What we measured | Are the devices similar? | Short reason |
|-----------------|--------------------------|--------------|
| **Droplet size** | **Yes — very consistent** | 2.4% spread between devices |
| **Production rate (speed)** | **No — they differ noticeably** | 40% spread between devices |
| **Stage 1 fill timing** | **No — they differ noticeably** | 37% spread between devices |

> **CV% (coefficient of variation)** is the main "at a glance" number used throughout this report.
> It's just the spread (standard deviation) expressed as a percentage of the average.
> Under ~5% = tight. 10–20% = moderate. Over 30% = devices are behaving quite differently from each other.

---

## Test conditions

| Parameter | Value |
|-----------|-------|
| Design | V5-30 |
| Production batch | 050526 |
| Testing date | 060526 |
| Continuous phase | SDS |
| Dispersed phase | Sunflower Oil |
| Flow rate (Qw) | 5 ml/hr |
| Oil pressure (Po) | 300 mbar |
| Positions tested | DFU1–DFU10 |

Devices tested: **1B**, **3D**, **4C** — all from the same batch, run under identical conditions.
Any differences between them are therefore manufacturing variation, not test variation.

---

## 1. Droplet size — consistent across devices

*Drop diameter is controlled mainly by device geometry, so we expect it to be stable.*

| Device | Average diameter | Spread within device | Spread as % of average |
|--------|-----------------|---------------------|------------------------|
| 1B | 26.6 µm | ±0.44 µm | 1.7% |
| 3D | 26.7 µm | ±0.97 µm | 3.6% |
| 4C | 26.8 µm | ±0.77 µm | 2.9% |

The three devices produce drops within **0.16 µm of each other** (device-to-device spread = 2.4% CV).
That's about half a pixel — excellent consistency. Drop size is essentially geometry-controlled and
the batch geometry is uniform.

---

## 2. Production rate — devices differ significantly

*Production rate (drops per second) is sensitive to flow resistance, which varies more with manufacturing.*

| Device | Average rate | Spread within device | Spread as % of average |
|--------|-------------|---------------------|------------------------|
| 1B | 1.52 Hz | ±0.49 Hz | 32% |
| 3D | 0.96 Hz | ±0.20 Hz | 21% |
| 4C | 0.70 Hz | ±0.08 Hz | 11% |

Device 1B produces drops **twice as fast** as device 4C. The between-device spread is **40% CV**.
This is real physical variation — not measurement noise. Device 1B has noticeably lower flow resistance
than 4C, meaning either its channel dimensions differ or there is a geometric asymmetry somewhere.

---

## 3. Stage 1 timing — devices differ significantly

*Stage 1 is the refill phase. Longer Stage 1 = slower production. This mirrors the rate data above.*

| Device | Average Stage 1 | Spread within device | Spread as % of average |
|--------|----------------|---------------------|------------------------|
| 1B | 0.44 s | ±0.12 s | 27% |
| 3D | 0.68 s | ±0.19 s | 28% |
| 4C | 0.94 s | ±0.15 s | 16% |

Between-device spread: **37% CV**. The fastest device (1B) takes half the time of the slowest (4C).
The dominant source of variation across this dataset is **device-to-device differences** — i.e. the
devices genuinely run differently, not just measurement noise making them look different.

---

## 4. Measurement quality — our measurements are accurate

*Before trusting the numbers above, it's worth checking how much of the spread is just measurement error.*

We measured the same physical generator twice in 21 cases across the dataset. The spread between those
repeated measurements tells us our measurement noise floor:

| What we're measuring | Noise in a single measurement | Is noise a problem? |
|---------------------|------------------------------|---------------------|
| Drop diameter | ±0.36 µm (1 sigma) | No — accounts for only 67% of within-position spread but <1% of between-device spread |
| Stage 1 timing | ±0.024 s (1 sigma) | No — only 4.5% of within-position variance |
| Production rate | ±0.040 Hz (1 sigma) | No |

The ±0.36 µm diameter noise is **exactly 1 pixel** at our imaging calibration (2.85 px/µm).
This means we're already at the precision limit of manual ROI placement — about as good as it gets
without sub-pixel software. The measurement process is not a bottleneck.

**Stage 1 reproducibility:** Pearson r = **0.988** on repeated measurements — near-perfect.

---

## 5. Where does variation come from?

For each metric, variation can come from four places. Here they are ranked from smallest to largest
(for the typical case — exact values below):

```
Measurement noise   →   Within one position   →   Position to position   →   Device to device
     (least)                                                                       (most)
```

| Metric | Meas. noise (σ) | Within position (σ) | Pos. to pos. (σ) | Device to device (σ) |
|--------|----------------|---------------------|------------------|---------------------|
| Stage 1 (s) | 0.024 | 0.108 | 0.152 | **0.256** ← biggest |
| Freq (Hz) | 0.040 | 0.124 | 0.254 | **0.429** ← biggest |
| Drop diam (µm) | 0.362 | 0.254 | **0.727** ← biggest | 0.635 |

> Reading this table: for **timing and rate**, the biggest source of variation is that the three devices
> behave differently from each other. For **drop size**, the biggest source is position-to-position
> variation within a single device (one end produces slightly larger drops than the other end) —
> but even that is small in absolute terms (~0.7 µm across 10 positions).

---

## 6. Figure guide

| Figure | What it shows |
|--------|--------------|
| Fig 1 | Production rate (Hz) at each of the 10 DFU positions, one line per device. Dashed grey = grand mean. |
| Fig 2 | Drop diameter at each DFU position. Legend shows each device's overall average ± spread. |
| Fig 2A | Same as Fig 2 but every individual data point shown — reveals whether outliers drive the error bars. |
| Fig 3 | Violin summary per device (individual y-axes). Wide = where most data falls; dot = median. |
| Fig 3B | Same violins but Stage 1/2/3 on a shared y-axis so you can compare magnitudes directly. |
| Fig 4 | Stacked bars showing what fraction of each cycle is Stage 1, 2, 3 at each DFU position. |
| Fig 5 | Four bars per metric showing how much each source (noise → within-pos → pos-to-pos → device) contributes. |
| Fig 6 | Heatmap: each cell is one device at one position, coloured by CV%. Red = high variation. |
| Fig 7 | Left: raw vs corrected spread. Right: scatter of repeated measurements — points on the diagonal = perfect reproducibility. |
| Fig 8 | Meniscus geometry (L_menpoint, L_men) at each position. Longer meniscus = slower Stage 1 — check if geometry differences explain the timing spread. |

---

## 7. Defective DFUs — impact on whole-device output quality

> This section uses a QC observation (defective DFU count per row, one row sampled per device) to
> estimate how defective drop generators affect the output from each device. The measurements in
> sections 1–6 were taken on visually normal-looking DFUs only — these estimates extend the picture
> to the full device output stream.

---

### The headline metric: in-spec yield

**Yield** is the fraction of output drops that fall within an acceptable size window around the
target (~26 µm). It is the most useful single number for characterising a device whose output
contains two clearly separated populations: normal drops (~26.7 µm) and defective drops (~14 µm).
Because these two populations do not overlap, any sensible tolerance window cleanly separates them —
what yield really measures is simply *what fraction of the drops coming out are the right size*.

| Device | In-spec yield | CV of in-spec drops | CV of full output (for reference) |
|--------|--------------|---------------------|-----------------------------------|
| 3D | ~92% | 3.6% | ~14% |
| 1B | ~80% | 1.7% | ~22% |
| 4C | ~61% | 2.9% | ~29% |

> The CV of in-spec drops (2–4%) is the true monodispersity of the device — it is consistent and
> good across all three devices. Yield is where they diverge: device 3D loses roughly 1 in 10 drops
> to defects; device 4C loses nearly 4 in 10.

---

### Where the yield numbers come from

**Device-level defect counts** (from QC inspection of one sampled row, extrapolated to all 10 rows):

The V5-30 device has **11,549 DFUs** in total (~1,154 per row position), from the device config
(main channel length 693 mm ÷ rung pitch 60 µm).

| Device | Defects per row (observed) | Estimated total defective DFUs | % of device |
|--------|---------------------------|-------------------------------|-------------|
| 3D | 16 | ~160 | 1.4% |
| 1B | 43 | ~430 | 3.7% |
| 4C | 105 | ~1,050 | 9.1% |

*Extrapolation assumes the sampled row is representative of the full device.*

**Defective drop size:** modelled as a normal distribution centred at **15 µm**, range **10–20 µm**
(±2σ). Defect drop size is constrained by channel geometry, so the spread is bounded. Normal drops
average 26.7 µm — defective drops are roughly half that size.

**Why defective DFUs produce more than their share of drops:** drop volume scales as D³, so a
15 µm drop needs only (15/26.7)³ = 18% of the fill volume of a normal drop — meaning the defective
generator fires roughly **6.5× faster** on average across the 10–20 µm defect size distribution.
The structural defect fraction and the output drop fraction therefore differ substantially:

| Device | Defective DFUs | Defective drops in output |
|--------|---------------|--------------------------|
| 3D | 1.4% | ~8% → yield ~92% |
| 1B | 3.7% | ~20% → yield ~80% |
| 4C | 9.1% | ~39% → yield ~61% |

*Even though only 9% of 4C's generators are defective, they produce nearly 40% of its output drops
because they fire so much faster.*

---

## 8. Conclusions

- **Droplet diameter is consistent across devices** when looking at normal DFUs: 2.4% CV between devices (σ = 0.63 µm). Geometry controls drop size, and that geometry is uniform across the batch.

- **Production rate and timing differ substantially:** 40% CV (σ = 0.43 Hz) and 37% CV (σ = 0.26 s) respectively. Device 1B runs approximately twice as fast as device 4C. The dominant source is genuine device-to-device differences — not measurement noise.

- **Measurement error is not the cause of the spread:** User measurement noise accounts for only 4.5% of within-position Stage 1 variance (Pearson r = 0.988 on repeated measurements).

- **Defective DFUs are the hidden quality risk, best expressed as yield.** Device 4C has ~1,050 defective generators (9% of 11,549 DFUs) versus ~160 (1.4%) for device 3D. Because defective drops (~15 µm) are roughly half the normal size, they fire ~6.5× faster — so 9% defective DFUs account for ~39% of 4C's output drops. Expressed as yield (fraction of output drops within a usable size window): **3D ~92%, 1B ~80%, 4C ~61%**. The monodispersity of the in-spec drops remains good across all three devices (CV 2–4%); yield is the differentiating quality metric in this batch.
