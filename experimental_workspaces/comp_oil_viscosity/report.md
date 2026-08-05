# The oil viscosity the data implies — and why it must not be adopted

**Date**: 2026-08-05
**Study type**: computational (re-analysis of existing experimental data)
**Model commit**: `71be939`
**Verdict**: **µ stays at 60 cP. Do not fit it.**

---

## The question

W2-1 replaced four disagreeing rectangular-duct resistances with one, normalised
the way Shah & London's polynomial is defined. On V5-30 that drops the rung
resistance to **0.65×** its previous value (1.53e18 → 9.981e17 Pa·s/m³), so the
model now delivers ~1.5× more oil at the same drive pressure. The old agreement
with the V5-8-1 sweep rested on two errors cancelling; W2-1 removed one of them.

`C_visc` — a global multiplier on `ΔP/R` — would restore the agreement instantly.
Conor ruled on 2026-08-05 that it must not be used: a constant that multiplies
`ΔP/R` at fixed geometry **is a viscosity**, and must be recorded as one. So this
workspace asks the question the honest way: *what µ_oil does the data imply, and
is it one number?*

The design-studio plan proposed **83 cP**, fitted at one condition, and flagged it
as "a fit, not a measurement". This workspace tests it against every other
condition in the same dataset.

## Answer

**It is not one number.** Fitting µ independently at each water flow rate gives:

| Qw (mL/hr) | pressures | best-fit µ | worst frequency error at that µ |
|---|---|---|---|
| 5 | 200/300/400/600 | **69 cP** | 9.2% |
| 10 | 200/300/400/600 | **81 cP** | 9.5% |
| 20 | 300/600 | **96 cP** | 13.7% |
| all pooled | 10 points | 79 cP | **38.7%** |

Each per-Qw fit is individually excellent — better than 15% everywhere, which is
the noise floor (below). That is exactly what makes the result damning: **a
viscosity that rises 39% as the water flow rate quadruples is not a viscosity.**
Sunflower oil does not thicken because someone turned up the water.

The plan's 83 cP is the **Qw = 10 slice** of this surface — the same procedure at
Qw = 5 gives 69 and at Qw = 20 gives 96. Pooling all three costs the fit an
order of magnitude in quality (9% → 39%), because there is no single value that
works.

**So 83 cP is `C_visc` wearing a physical name.** It is the same object the ruling
rejected: a scalar fitted at one device at one condition, which would then be
stamped onto every design the studio scores.

## Where the residual actually lives

Splitting the measured cycle at the stage boundary answers this cleanly. At the
config's unfitted **µ = 60 cP**, at **Qw = 5 mL/hr** (the condition
`configs/v5_30.yaml` declares):

| Po (mbar) | Stage 1 meas | Stage 1 model | err | Stage 2+3 meas | Stage 2+3 model | err |
|---|---|---|---|---|---|---|
| 200 | 0.540 s | 0.462 s | **−14.5%** | 0.260 s | 0.267 s | +2.9% |
| 300 | 0.300 s | 0.271 s | **−9.7%** | 0.180 s | 0.157 s | −12.8% |
| 400 | 0.200 s | 0.192 s | **−4.1%** | 0.140 s | 0.111 s | −20.6% |
| 600 | 0.120 s | 0.121 s | **+0.9%** | 0.120 s | 0.070 s | −41.5% |

**Stage 1 — the only stage the rung resistance and the oil viscosity control —
agrees to −14.5% → +0.9% at 60 cP, with the error shrinking monotonically as
pressure rises.** No viscosity change is warranted by Stage 1. That is W2-1's
result, and it is a good one: the exact resistance, the measured DFU profile, the
measured reset length, literature viscosity, **zero correction terms**.

The deficit is in Stage 2+3, and it grows with *both* Po and Qw. Two known things
account for its shape, and neither is a material property:

1. **The model under-responds to Qw by ~3×.** Doubling Qw from 5 to 10 at
   200 mbar costs the real device 28% of its production; the model gives up 5.5%.
   The water back-pressure it computes moves `ΔP_rung` by only 6 mbar in 162.
   This is a *documented* limitation — the v3 physics plan's own "Stage 2 Qw
   dependence" note, and `qw_sweep/BRIEF.md` reached the same conclusion
   independently ("Stage 2 is NOT Qw-independent — contradicts the single-constant
   assumption from the Po sweep").
2. **At high Po the measurement is resolution-limited.** At 600 mbar the measured
   Stage 2+3 is 0.120 s — **6 frames at 50 fps** — and every value in the column
   is an exact multiple of 0.02 s. The quantisation floor biases it high, which is
   the direction of the residual. This is open question 2 in the studio plan and
   is not resolvable by modelling.

A geometric error would be **Qw-independent**. This one is not, so the plan's
counterfactual ("if the oil comes back near 60 cP, the residual is geometric and
*that* is the finding") resolves one step further: it is not geometric either. It
is the Stage-2 growth model and the water-side loading.

## The noise floor — and the strongest thing that can be said for the model

The sweep measures per-DFU flow two independent ways:

```
conservation  Q = V_drop / t_cycle            (measured droplet diameter)
meniscus      Q = L_menpoint · w · h / t_S1   (measured meniscus sweep)
```

They disagree with **each other** by **16–26%** (median 23%) across all ten
conditions. No fit against this data means anything below ~15%, and the plan's
±8% target is inside the measurement's own contradiction.

**That disagreement is not noise — it is the physics of the cycle.** Meniscus-sweep
Q measures flow *during Stage 1*; conservation Q measures the *cycle average*.
They differ because flow is not constant through the cycle, and the conservation
estimate is the lower of the two at every single condition, by construction. The
model carries one Q, so the correct place for it to sit is **between them**.

At **Qw = 5 mL/hr — the condition `configs/v5_30.yaml` declares — it does, at every
pressure**:

| Po (mbar) | Q conservation | Q meniscus | **Q model** | vs cons. | vs men. |
|---|---|---|---|---|---|
| 200 | 1.024e-14 | 1.184e-14 | **1.126e-14** | +9.9% | −5.0% |
| 300 | 1.702e-14 | 2.013e-14 | **1.917e-14** | +12.6% | −4.7% |
| 400 | 2.314e-14 | 2.896e-14 | **2.709e-14** | +17.1% | −6.5% |
| 600 | 3.742e-14 | 4.663e-14 | **4.292e-14** | +14.7% | −8.0% |

4 of 4 inside the band. This is as validated as this dataset can make anything: the
model's flow is not distinguishable from the measurement, because the measurement
does not agree with itself to that precision.

It steps outside the band at Qw = 10 and 20 (6 of 6), which is the same Qw
under-response reported above — though at 300–600 mbar it clears the meniscus
estimate by only 2–4%. The two conditions genuinely far out are Qw = 10 at
200 mbar (+27% on meniscus) and Qw = 20 at 300 mbar (+59%): **low pressure and high
water flow**, where the water side loads the ladder hardest and the model responds
least.

Note the Q-measure disagreement is roughly flat across conditions, so it does
**not** generate the Qw trend above — the trend is real, not an artefact of which Q
you believe.

## What was changed in the model

**Nothing.** `fluids.mu_dispersed` stays at **0.06 Pa·s = 60 cP**, the literature
value for sunflower oil (`po_sweep/BRIEF.md` cites a ~50–60 cP range), unchanged
and **not fitted**. `C_visc` is deleted in `71be939` and a config that sets it now
raises.

This is a deliberate departure from the plan's W2-8 item, which reads "Set the oil
viscosity, and DELETE `C_visc`". Half of it is done. The other half cannot be done
honestly yet, because **the oil has never been on a viscometer**, and the
alternative — adopting a fitted number — is the thing the ruling forbids. The item
anticipated exactly one branch of this ("measure the oil and use the
measurement"); this workspace establishes that the *other* branch, fitting it, is
closed.

## Open actions, in priority order

1. **Put the sunflower oil on a viscometer, at the test temperature.** One
   measurement collapses the whole argument. Until then µ = 60 cP is a literature
   value carrying an unquantified error, and any viscosity claim about this
   dataset is unfalsifiable.
2. **Record temperature during testing.** It is absent from
   `stage_timings.csv`. Sunflower oil roughly doubles in viscosity between 30 °C
   and 15 °C, so ±5 °C is a ±30% viscosity swing — larger than every effect argued
   about here.
3. **The Qw response is the real modelling gap.** Not the viscosity. The model
   loses 5.5% of production when the device loses 28%; that is where the next
   physics change belongs.
4. **Re-shoot at higher frame rate at 400–1000 mbar** to settle whether Stage 2+3
   flattening is physical (studio plan open question 2).

## Caveats

- One device (V5-8-1), one geometry (V5-30), one oil, one surfactant system. The
  Qw-dependence of the fitted µ is established **within** this dataset; whether the
  same slope appears on another device is untested.
- 2 of the 10 conditions (Qw = 20) have only two pressures, so that fit is the
  weakest of the three. The trend does not depend on it: Qw = 5 and Qw = 10 alone
  give 69 vs 81 cP, a 17% spread from four pressures each.
- Measured aggregates are **medians** over 10–23 observations per condition.
- The file's only 800 mbar data is 2.5% sodium caseinate at Qw = 10 — a different
  continuous phase — and is excluded. The plan's frequency table spans
  200–800 mbar, so **it necessarily included that point**; the SDS data reaches
  600 mbar and no further.

## Data provenance

- **Config snapshot**: `snapshots/v5_30_2026-08-05.yaml`
- **Run manifest**: `snapshots/run_manifest.md` (git hash, exact command, row
  filters, and the conditions deliberately excluded)
- **Data source**: `data/data_sources.md` — the physical file lives in
  `po_sweep/data/stage_timings.csv`; this workspace holds no copy
- **Table "Answer"** — `results/fit_summary.json`, `results/mu_scan_qw{5,10,20}.csv`,
  `results/agreement_qw{5,10,20}_fitted.csv`
- **Table "Where the residual actually lives"** — `results/agreement_all_config_mu.csv`
- **Noise floor** — `results/measured_by_condition.csv`, column `Q_disagreement_pct`
- **Full console run** — `results/analysis_stdout.txt`
- No figures: every claim here is a table of ten rows or fewer, and a plot of ten
  points would carry less than the numbers do.
