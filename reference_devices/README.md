# Reference devices

The three built Peak Emulsions devices the model is checked against, as shipped GDS.

These are the **ground truth for layout and packing**. Where the model's geometry
disagrees with a number in this file, the model is wrong. Every constant in
`design/layout.py`'s stack-up and every per-family `active_fraction` traces back here.

| File | Device | Family | Revision |
|---|---|---|---|
| `v5_30umV1.1.gds` | V5-30 | serpentine | V1.1 |
| `v5_10umV1.gds` | V5-10 | serpentine | V1 |
| `V6-30um_v1.2.gds` | V6-30 | radial | V1.2 |

## Measurements

Extracted with `gdstk`. Polygon accounting closes with **residual 0** — every polygon on
the DFU layer is assigned to either a straight run or a curve run, with nothing left over.

| | **V5-30** serpentine | **V5-10** serpentine | **V6-30** radial |
|---|---|---|---|
| Die | 100 × 100 mm | 100 × 100 mm | 100 × 100 mm |
| Active footprint | 69.0 × 74.0 = 51.1 cm² | 68.6 × 74.0 = 50.8 cm² | disc R = 45 mm = 63.6 cm² |
| **% of die** | **51%** | **51%** | **64%** |
| Lane pairs | 10 | 12 | — |
| Main width | 1000 µm | 1000 µm | — |
| DFU array gap | 4.0 mm | 2.8 mm | — |
| **Wall** | **1.0 mm** | **1.0 mm** | — |
| **Lane pitch** | **7.00 mm** | **5.80 mm** | — |
| DFU pitch | 60 µm | 20 µm | 75.4 µm |
| DFUs | 10,000 straight + 1,154 curve = **11,154** | 36,000 + 3,192 = **39,192** | **3,000** at R = 36.0 mm |

### The DFU profile — two widths in series, not one

```
V5-30   3610 µm @  8 µm wide  (90% of length)   depth 10 µm throughout
         410 µm @ 30 µm wide  (10%)             = 4020 µm total
V5-10   2525 µm @  7 µm wide  (90%)
         285 µm @ 10 µm wide  (10%)             = 2810 µm total
```

**Note the aspect ratio.** V5-30's narrow section is 8 µm wide × 10 µm deep — *depth
exceeds width*. Any resistance model that rejects `h >= w` cannot represent this device.
The correct handling is to order the dimensions (`h = min`, `w = max`) so α ≤ 1 by
construction. `families/manifold.py::_R_rect` currently rejects it; that is a known bug.

## What these establish

1. **`lane_pitch = 2×main + DFU_array + wall`, exactly.**
   V5-30: 1 + 4 + 1 + 1 = 7.0 mm. V5-10: 1 + 2.8 + 1 + 1 = 5.8 mm.
   The model's `lane_spacing = 500 µm` is spurious, and `2 × turn_radius` matching the
   1.0 mm wall on V5-30 is a **coincidence** that breaks as soon as `turn_radius` changes.
2. **The wall is 1.0 mm on both serpentines** — a design rule with no input in the model.
3. **Radial `N = 2πR/pitch` is exact**: 2π × 36 mm / 75.4 µm = 3,000, to the unit.
4. **Serpentine and radial have genuinely different overhead** (51% vs 64%), for a physical
   reason: radial feeds from the centre and needs ~5 mm margin, while the serpentine spends
   a dedicated 65.8 × 8 mm IO strip plus ~13–15 mm margins.
5. **The packing model's geometry was never wrong.** Given the real active area it lands
   exactly: `(69 − 6.0)/7.0 + 1 = 10` lane pairs. The old 1.66× over-prediction came
   entirely from assuming 96 × 96 mm of a 100 × 100 mm die is usable.

### Caveat on `active_fraction`

51% and 64% are measured **at a 100 mm die**. They are not scale-free — the IO strip and
the margins are absolute lengths, not fractions. The family defaults are `square_side_mm:
63.5`, where these numbers do not apply. Until a per-family IO/port model exists, treat
`active_fraction` as valid at 100 mm only, and say so on any row that is not.

## 11,154 vs 11,565 DFUs on V5-30 — closed 2026-08-04

The GDS gives **11,154** (10,000 straight + 1,154 curve), with all 31,674 DFU-layer
polygons accounted for and nothing left over. Conor's working figure is **11,565** —
3.7% apart. **Conor ruled 11,565: 3.7% is close enough, and no reconciliation is being
sought.** The likely cause (a revision difference — this file is V1.1 — or a different
convention on the curve DFUs) is recorded only so nobody re-opens it.

The two numbers do not compete, because they answer different questions:

| Number | What it is | Where it belongs |
|---|---|---|
| **11,565** | the device figure, the N the model is driven at | `configs/v5_30.yaml` (`Mcl = 693 mm`, reported as 11,549) |
| **11,154** | polygons counted in this GDS, residual 0 | the layout acceptance tests, `tests/test_reference_devices.py` |

The acceptance tests ask whether `compute_layout` reproduces *the geometry the GDS
contains*, so 11,154 is the only admissible number there. Asserting 11,565 would be
asserting the model against a number this file does not contain.

## Provenance of these numbers

Measured 2026-08-03/04 with `gdstk` in an analysis session. **The extraction script is not
yet in the repo** — the measurements were taken in a scratchpad and only the results were
carried across. Re-deriving it is outstanding work: it belongs here as
`measure_reference_devices.py` so any of the above can be re-checked against the GDS
without redoing the analysis by hand.

Until then, the acceptance tests in `tests/` assert these values as **literals citing this
file**, deliberately — so that neither `gdstk` nor 2.2 MB of binaries becomes a test
dependency.
