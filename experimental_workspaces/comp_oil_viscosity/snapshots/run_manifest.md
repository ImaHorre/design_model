# Run Manifest

## Run: viscosity implied by the V5-8-1 Po/Qw sweep, with the rung resistance exact — 2026-08-05

**Model commit**: `71be939b4eb3825910df2c1385f34e12d8d5dd48`
("W2-1: one rectangular-duct resistance, normalised as Shah & London define it")

**Config snapshot**: `snapshots/v5_30_2026-08-05.yaml` — a verbatim copy of
`configs/v5_30.yaml` as of that commit, including the measured two-width DFU
profile W2-1 turned on. `analysis.py` loads the **snapshot**, never the live config.

**Command**:
```
python experimental_workspaces/comp_oil_viscosity/analysis.py
```

**Outputs**:
- `results/measured_by_condition.csv` — measured aggregates per (Qw, Po)
- `results/mu_scan_qw{5,10,20}.csv`, `results/mu_scan_all.csv` — RMS log-error vs µ
- `results/agreement_qw{5,10,20}_fitted.csv` — model vs measured at each per-Qw best fit
- `results/agreement_all_fitted.csv` — at the pooled best fit
- `results/agreement_all_config_mu.csv` — **at the config's unfitted µ = 60 cP**
- `results/fit_summary.json` — the numbers quoted in `report.md`
- `results/analysis_stdout.txt` — the full console run

### Experimental data used

| File | Device ID | Test date | Rows | Notes |
|---|---|---|---|---|
| (not copied — see below) | V5-8-1 | 2026-04-24 | 278 total; **158 used** | primary workspace: `po_sweep/` |

The physical file is `experimental_workspaces/po_sweep/data/stage_timings.csv`
(278 rows, 34 KB). It is **not duplicated here** — one dataset, one identity, one
location, per the multi-workspace rule in `CLAUDE.md`. See `data/data_sources.md`.

**Rows used**: `DeviceID == "V5-8-1" AND ContPhase == "SDS" AND DispPhase == "SO"`,
dropping rows with any missing stage timing → 158 observations across 10 (Qw, Po)
conditions.

**Rows deliberately excluded**:

| Excluded | Why |
|---|---|
| `ContPhase ∈ {0125pcSDS, 025pcSDS, 05pcSDS, 1pcSDS}` | sub-2% SDS; the lowest are below CMC, which the v3 physics plan §F puts explicitly outside the model's scope |
| `ContPhase == 2-5NaCas` (Qw = 10, Po = 800, n = 19) | 2.5% sodium caseinate — a different continuous phase from the one `configs/v5_30.yaml` describes. **This is the file's only 800 mbar data.** |

**The timing data carries an applied correction.** `Stage*_s` were multiplied by
0.5 on 2026-06-08 (analysed at 25 fps, filmed at 50 — see `po_sweep/BRIEF.md`).
This analysis uses the corrected values as they stand in the file.

### Key config parameters (verified against the snapshot, not inherited from a label)

| Parameter | Value in snapshot |
|---|---|
| Dispersed phase | **sunflower oil** (`DispPhase == "SO"`; ruled 2026-07-29, never silicone) |
| η_dispersed | 0.06 Pa·s = **60 cP** — literature value, **not fitted**, unchanged by this study |
| Continuous phase | 2% SDS in water |
| η_continuous | 0.00089 Pa·s |
| Interfacial tension | `gamma: 0.0` in the config — Ca is therefore not computed here and no Ca claim is made in this workspace |
| Rung (DFU) | 3610 µm @ 8 × 10 µm + 410 µm @ 30 × 10 µm, piecewise |
| Junction exit | 30 × 10 µm |
| Main | 200 µm deep × 1000 µm wide, 693 mm routed → N = 11,549 |
| R_rung at 60 cP | 9.9810e17 Pa·s/m³ |

### Temperature

**Not recorded in the data file.** This matters more than usual here: sunflower
oil viscosity roughly doubles between 30 °C and 15 °C, so any viscosity argument
about this dataset is unfalsifiable without it. Recorded as an open action in
`report.md`, not as an assumption.
