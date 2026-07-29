# NaCas/MCT vs SDS/SO — Experimental Analysis Report

**Device:** V5-8-1 (junction 30 µm wide × 10 µm deep)
**Analysis date:** 2026-04-28
**Data source:** `analysis/stage_timings.csv`

---

> **CORRECTION — 2026-06-08: FPS error discovered**
>
> All Stage timing and production-rate values in this report are **2× wrong** due to a systematic error:
> the video analysis tool used fps = 25, but the videos were recorded at **50 fps**.
> All Stage*_s values in this report should be **halved**, and all Hz frequency values should be **doubled**.
>
> **What changes:**
> - All absolute timing values (Stage1_s, Stage2_s, Stage3_s, total cycle time) are 2× too long.
> - All reported frequencies (Hz) are 2× too low.
>
> **What does NOT change:**
> - Relative comparisons between NaCas/MCT and SDS/SO survive: the fps error affects both systems equally, so ratios, speed-up %, and "which stage is longest" conclusions remain valid.
> - Stage fractions (Stage 1 as % of cycle) are unchanged (numerator and denominator both halved).
> - Droplet diameter conclusions are unchanged (spatial measurement, not timing-derived).
> - The 200 mbar no-formation finding is unchanged.
>
> To regenerate this report with correct values:
> 1. Run: `python scripts/correct_fps_error.py <path_to_stage_timings.csv>`
> 2. Re-run: `python experimental_workspaces/nacas_mct_comparison/analysis.py`

---

## 1. Overview

This report characterises droplet formation in a new fluid system — 2.5% sodium caseinate
(NaCas) as continuous-phase surfactant with medium-chain triglyceride oil (MCT) as the
dispersed phase — against a well-established SDS/sunflower-oil (SO) control.
Both systems were run at continuous-phase (water) flow rate Qw = 5 ml/hr across a range
of oil inlet pressures (Po). A low-flow NaCas/MCT dataset at Qw = 1 ml/hr is included
as an extreme reference. No model simulations are used; all results are from direct video
measurement.

**Key questions:**
1. Does NaCas/MCT form droplets stably, and what is its minimum operable pressure?
2. Are stage timings comparable to SDS/SO? Which stages scale with pressure and which do not?
3. Does the device produce consistent droplet size along its length (DFU 1–10)?
4. What operational range achieves good uniformity in both systems?

---

## 2. Dataset Summary

| Series | n rows (raw) | Qw (ml/hr) | Po tested (mbar) |
|--------|-------------|------------|-----------------|
| SDS/SO 5 ml/hr (control) | 66 | 5 | 200, 300, 400, 600 |
| NaCas/MCT 5 ml/hr | 36 | 5 | 200 (no formation), 300, 400 |
| NaCas/MCT 1 ml/hr | 25 | 1 | 100, 150 |

Excluded from this analysis: all other SDS concentrations (0.125%–1%), NaCas/SO, and the
legacy V5_30_3_3 device dataset.

---

## 3. 200 mbar NaCas/MCT — No Droplet Formation

At Po = 200 mbar with Qw = 5 ml/hr, the NaCas/MCT system produced no measurable stage
timings or geometry data across all 4 recorded observation rows. This represents the lower
operating boundary for this fluid system under these flow conditions.

**Implication:** The minimum viable oil pressure for NaCas/MCT at 5 ml/hr is between
200 and 300 mbar. This contrasts with SDS/SO, which operates successfully at 200 mbar.
The higher threshold was originally attributed to "the greater viscosity of MCT relative to
the control oil".

> **CORRECTION 2026-07-29 — this explanation no longer holds.** The control's dispersed
> phase was recorded as silicone oil throughout this workspace; it is **sunflower oil**
> (`DispPhase = SO`; ruling confirmed 2026-07-29, see `CLAUDE.md`). Sunflower oil is
> ~50-60 cP while MCT is ~25-30 cP, so MCT is roughly **half** the viscosity of the
> control, not greater. The viscosity argument therefore predicts the *opposite* of what
> was observed and must be discarded.
>
> The observation itself stands: NaCas/MCT produced no droplets at 200 mbar where SDS/SO
> does. A viscosity-independent explanation is needed — candidates are the higher
> interfacial tension of a NaCas-stabilised interface (raising the capillary entry
> pressure), slower NaCas adsorption kinetics at the timescale of neck thinning, or
> different wetting of the channel walls. **Open — do not cite the viscosity reason.**

---

## 4. Stage Timing Analysis

Measured timings are split into three experimental stages:
- **Stage 1** — oil meniscus travels from reset position to the junction edge (hydraulic filling)
- **Stage 2** — oil pushes over the junction edge (transitional)
- **Stage 3** — continuous phase enters and pinches the neck; droplet detaches (snap-off)

Stages 1 and 2 together are driven by the hydraulic pressure difference Po − P_cap and are
expected to scale inversely with Po. Stage 3 is controlled by capillary geometry and is
expected to be approximately constant with Po.

| Series | Po (mbar) | S1 (s) | S2 (s) | S3 (s) | Total (s) | Freq (Hz) | L_men_pt (µm) | Dome (µm) | V_reset (fL) | D_drop (µm) | D CV% |
|--------|-----------|--------|--------|--------|-----------|-----------|---------------|-----------|-------------|-------------|-------|
| SDS/SO 5ml/hr | 200 | 1.08 | 0.35 | 0.19 | 1.62 | 0.620 | 21.3 | 10.7 | 8.1 | 25.2 | 1.0 |
| SDS/SO 5ml/hr | 300 | 0.61 | 0.20 | 0.15 | 0.96 | 1.053 | 20.0 | 10.8 | 7.7 | 25.0 | 2.2 |
| SDS/SO 5ml/hr | 400 | 0.40 | 0.15 | 0.13 | 0.67 | 1.499 | 19.7 | 9.4 | 7.4 | 24.7 | 1.3 |
| SDS/SO 5ml/hr | 600 | 0.25 | 0.12 | 0.11 | 0.48 | 2.107 | 19.7 | 8.5 | 7.3 | 25.7 | 2.9 |
| NaCas/MCT 5ml/hr | 200 | — | — | — | — | — | — | — | — | — | — |
| NaCas/MCT 5ml/hr | 300 | 0.42 | 0.18 | 0.08 | 0.68 | 1.552 | 17.0 | 10.3 | 6.7 | 23.3 | 3.5 |
| NaCas/MCT 5ml/hr | 400 | 0.21 | 0.10 | 0.10 | 0.42 | 2.412 | 13.6 | 11.2 | 5.8 | 23.8 | 3.9 |
| NaCas/MCT 1ml/hr | 100 | 2.23 | 1.11 | 1.27 | 4.61 | 0.220 | 10.9 | 17.3 | 6.0 | 26.2 | 10.6 |
| NaCas/MCT 1ml/hr | 150 | 0.67 | 0.32 | 0.57 | 1.57 | 0.653 | 11.2 | 16.0 | 5.9 | 25.9 | 8.9 |

**Stage 1 + 2 (hydraulic):** Both SDS/SO and NaCas/MCT show Stage 1 decreasing markedly
with increasing Po — consistent with pressure-driven refill. For NaCas/MCT at 5 ml/hr,
Stage 1 is substantially shorter than SDS/SO at the same pressure. The most likely
explanation is the shorter meniscus reset geometry: NaCas produces a smaller L_menpoint
(less oil in the channel at the start of Stage 1), which reduces the initial hydraulic
resistance. Under Washburn-type constant-pressure filling, Stage 1 time scales as
L_menpoint² / ΔP — so the quadratic dependence on reset distance makes this a stronger
effect than any viscosity difference between the two oil phases.

**Stage 2:** Short in both systems (0.04–0.25 s). Represents the brief period when the oil
bulge grows over the junction edge before the neck begins to form.

**Stage 3 (snap-off):**
- SDS/SO 5 ml/hr: mean Stage 3 = 0.15 s, CoV across pressures = 21.5%
- NaCas/MCT 5 ml/hr: mean Stage 3 = 0.09 s, CoV = 15.6%

Stage 3 shows low variation with Po in both systems, confirming it is capillary/geometry
controlled rather than pressure driven. NaCas/MCT snap-off is markedly faster than SDS/SO
— mean Stage 3 0.09 s vs 0.15 s for SDS/SO — consistent
with a lower oil–water interfacial tension when NaCas is adsorbed, enabling faster capillary
neck collapse. This Stage 3 speed-up is a significant contributor to NaCas/MCT's higher
overall droplet frequency (see Section 5).

**NaCas/MCT at 1 ml/hr (100–150 mbar):** Stage 3 is substantially longer (0.5–2 s) compared
to the 5 ml/hr data (~0.08 s). This very long Stage 3 at low pressure/low flow likely
indicates a different snap-off regime — the neck forms but collapses slowly, possibly because
the driving pressure is insufficient for rapid squeezing by the continuous phase.

---

## 5. Cycle Frequency

Frequency (Hz) = 1 / total cycle time. Higher pressure and flow drive shorter cycles.

For SDS/SO 5 ml/hr:
- 200 mbar → 0.620 Hz
- 300 mbar → 1.053 Hz
- 400 mbar → 1.499 Hz
- 600 mbar → 2.107 Hz

For NaCas/MCT 5 ml/hr:
- 300 mbar → 1.552 Hz
- 400 mbar → 2.412 Hz

NaCas/MCT runs **significantly faster** than SDS/SO at matched pressure:
+47% at 300 mbar and +61% at 400 mbar.
All three stages are faster for NaCas/MCT. Stage 1 (and likely Stage 2) are faster
primarily because NaCas produces a shorter meniscus reset geometry — smaller L_menpoint
means less oil to displace and lower initial hydraulic resistance. Under constant-pressure
Washburn filling, Stage 1 time scales as L_menpoint², so the geometry effect dominates.
Stage 3 is approximately 1.6× faster, which
points to a lower oil–water interfacial tension when NaCas is adsorbed, enabling faster
capillary snap-off independently of the hydraulic geometry.

---

## 6. Meniscus Reset and Shape

The oil meniscus resets to a position inside the rung after each droplet detaches.
Two measurements characterise this:
- **L_menpoint** (µm): distance from the meniscus tip to the junction edge
- **dome_um** = L_men − L_menpoint (µm): axial span of the meniscus dome — larger means more convex (more curved meniscus)

The displaced volume per cycle:
  V_reset = w·h·L_menpoint + (π/6)·w·h·dome_um

where w = 30 µm, h = 10 µm.

| System | Mean dome (µm) | Mean V_reset (fL) |
|--------|----------------|-------------------|
| SDS/SO 5 ml/hr | 9.8 | 7.6 |
| NaCas/MCT 5 ml/hr | 10.7 | 6.3 |
| NaCas/MCT 1 ml/hr | 16.6 | 5.9 |

NaCas/MCT shows a **smaller L_menpoint** and a **more pointed (elongated) meniscus** than
SDS/SO. The meniscus shape ratio (dome_um / L_menpoint) quantifies this:
- SDS/SO mean shape ratio ≈ 0.50 (near-hemispherical)
- NaCas/MCT mean shape ratio ≈ 0.75 (elongated cone;
  0.63 at 300 mbar,
  0.86 at 400 mbar)

Despite similar absolute dome extents, the much shorter L_menpoint for NaCas gives a
proportionally taller, more pointed profile. This reflects altered contact-angle behaviour
when NaCas adsorbs to the channel walls: the oil triple line stays further back while the
meniscus tip advances toward the junction, creating a higher-energy, more elongated interface.
This interpretation is consistent with two observations: (1) the 200 mbar formation failure
(the more pointed geometry requires a higher Laplace-pressure threshold to initiate snap-off),
and (2) the faster Stage 3 (once at the critical geometry, the more energetic interface
collapses faster).

The smaller V_reset for NaCas/MCT reflects the shorter reset distance (smaller L_menpoint),
despite the similar absolute dome extent.

---

## 7. Droplet Diameter Uniformity Across the Device

The central performance question: does the device produce consistent droplet size along
its length (DFU 1–10)?

### Overall diameter statistics

| System | Mean D (µm) | Std D (µm) | CV% across device |
|--------|-------------|------------|-------------------|
| SDS/SO 5 ml/hr | 25.2 | 0.54 | 2.1 |
| NaCas/MCT 5 ml/hr | 23.5 | 0.83 | 3.5 |
| NaCas/MCT 1 ml/hr | 26.0 | 2.29 | 8.8 |

### SDS/SO 5 ml/hr (control)

At all tested pressures (200–600 mbar), droplet diameter is remarkably uniform across
DFU 1–10. The per-pressure CV is low (≤ 2–3%), confirming that the device architecture
produces consistent droplets regardless of position along the device at these conditions.
Diameter is slightly smaller at higher pressures, consistent with the observed trend in
the literature for pressure-controlled squeezing: faster snap-off at higher Po leaves a
slightly smaller droplet.

### NaCas/MCT 5 ml/hr

At **300 mbar**, diameter is consistent across DFU 1–9 but falls slightly at downstream
positions. At **400 mbar**, the central DFUs (1–7) show good uniformity; however, **DFU 10
exhibits markedly higher variability and larger droplets**, flagged on Fig 5. Two DFU 10
observations are annotated: one labelled *"just before oil wetting begins"* (Stage 3 = 0.52 s,
D = 32.9 µm) and one *"last DFUs"* (Stage 3 = 0.28 s, D = 28.5 µm). These are characteristic
of oil wetting the channel walls at the device outlet — a known failure mode at high pressure.

**Operational range for NaCas/MCT (5 ml/hr):** DFU 1–7 at 300–400 mbar produces
consistent droplets with CV < ~5%. Operation should avoid the terminal DFUs at 400 mbar
where oil wetting risk is elevated.

### NaCas/MCT 1 ml/hr

At 100 mbar, droplet diameter is notably higher and more variable at downstream DFUs
(DFU 7–9 show larger droplets). This is consistent with the very long Stage 3 observed
at this condition: slow snap-off allows more oil to accumulate, forming larger droplets.
At 150 mbar, there is improvement in consistency but the trend persists. The 1 ml/hr
dataset demonstrates that very low flow rates can produce larger, less uniform droplets —
this represents an operational extreme rather than a recommended working condition.

---

## 8. Operational Range Summary

| System | Recommended Po (mbar) | Qw (ml/hr) | Reliable DFU range | Notes |
|--------|----------------------|------------|-------------------|-------|
| SDS/SO | 200–600 | 5 | 1–10 | All conditions show good uniformity |
| NaCas/MCT | 300–400 | 5 | 1–7 | Avoid DFU 8–10 at 400 mbar (oil wetting risk) |
| NaCas/MCT | 100–150 | 1 | 1–5 | Low flow extreme; larger and less uniform droplets |

Both systems produce droplets in a similar diameter range (~22–26 µm for the primary
5 ml/hr conditions), demonstrating that NaCas/MCT is a viable alternative fluid system
for this device architecture. The key operational difference is the higher minimum
pressure requirement for NaCas/MCT (≥ 300 mbar vs ≥ 200 mbar for SDS/SO) and increased
sensitivity to oil wetting at the downstream end of the device at 400 mbar.

---

## 9. Low-Flow Extreme — NaCas/MCT 1 ml/hr (100–150 mbar)

At Qw = 1 ml/hr, the NaCas/MCT system operates in a different regime:
- Stage 1 is very long (~1–3 s), reflecting slow hydraulic filling at low pressure
- Stage 3 is dramatically extended (0.5–2 s) — slow snap-off, possibly limited by continuous-phase shear
- Droplets are 24–30 µm, with larger droplets forming at downstream DFUs
- The device still produces droplets, but with low frequency (< 0.2 Hz) and lower uniformity

This confirms the device can operate across a broad flow-rate range with NaCas/MCT, but the
optimal window (uniformity, predictable timing, stable snap-off) is clearly at 5 ml/hr,
300–400 mbar, DFU 1–7.

---

*Generated by `analysis/nacas_mct_analysis.py` — 2026-04-28 15:45*
