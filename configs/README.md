# configs/ — device & study configurations

This directory holds the YAML configs consumed by the `stepgen` CLI. Two kinds
live here:

- **Device configs** — a single device geometry + fluid system, loaded by
  `load_config()` (used by `simulate`, `sweep`, `report`, `map`, `compare`).
- **Design-search / study configs** — parameter-space specs, loaded by
  `load_design_search()` (`stepgen design`) or the studio (`stepgen study`).

Fluid convention (see `CLAUDE.md`): dispersed phase in Peak Emulsions work is
**sunflower oil** (`µ ≈ 0.06 Pa·s`); continuous is **2% SDS-water**
(`µ ≈ 0.00089 Pa·s`). `o/w` = oil-in-water; `w/o` = the reverse.

## Index

| File | Kind | Device / target | Phase | Status |
|---|---|---|---|---|
| `v5_30.yaml` | device | V5-30 (Mcw 1000 µm, pitch 60 µm, N≈11 550) | o/w | **canonical** — the calibration/regression anchor |
| `v5_60.yaml` | device | V5-60 variant | o/w | canonical |
| `w11.yaml` | device | W11 | o/w | canonical |
| `w11_1.yaml` | device | W11 (variant / 1 mL·hr⁻¹ tuning) | o/w | canonical |
| `w11_stage_wise.yaml` | device | W11, stage-wise v3 explicitly enabled | o/w | canonical (v3 model demo) |
| `ow_w11.yaml` | device | W11, explicit o/w fluid block (`µ_disp 0.05`) | o/w | reference |
| `wo_v5_30.yaml` | device | V5-30, water-in-oil variant | w/o | reference |
| `wo_w11.yaml` | device | W11, water-in-oil variant | w/o | reference |
| `example_stage_wise.yaml` | device | example for the stage-wise model | o/w | example/docs |
| `study_template.yaml` | **study** | unified design study (deep-DFU serpentine) | o/w | **canonical** — `stepgen study` template |
| `design_search_10um.yaml` | design-search | target droplet 10 µm | o/w | canonical (`stepgen design`) |
| `design_search_5um.yaml` | design-search | target droplet 5 µm | o/w | canonical (`stepgen design`) |
| `test_device.yaml` | device | small generic device | o/w | **test fixture** |
| `test_30um.yaml` | device | 30 µm test device | o/w | test fixture |
| `test_stage_wise_v3.yaml` | device | stage-wise v3 test device | o/w | test fixture |
| `wo_test30um.yaml` | device | 30 µm, water-in-oil | w/o | test fixture |
| `templates/` | — | seed templates for new configs | — | scaffolding |

Notes
- Several device configs still carry a stale `# example_single.yaml` header
  comment from when they were copied; the **values** are authoritative, not the
  header (see `v5_30.yaml`).
- `phase_system` defaults to `o/w` when the fluids block omits it.
- "Status" is advisory: **canonical** = a real device/target used in analysis;
  **test fixture** = used by `tests/`; **reference/example** = illustrative.
