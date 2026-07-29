# Interfacial Inversion — SDS / silicone-oil, device V5-8-1
*Generated 2026-07-13 by `analysis.py`. Constants in `calibrated_constants.yaml`.*

## Headline

- **Capillary entry pressure P_entry = 1898 Pa [1474, 2748]** (from the ~30 mbar onset) → **γ·cosθ ≈ 14 mN/m** at 2% SDS (matches the model's 15 mN/m default).
- This is the **'make droplets at all' threshold** and the recommended `dP_cap_ow_Pa` — the model currently uses 5000 Pa (~2.5× too high; predicts onset ~63 mbar vs observed ~30).
- **Junction Ca ≈ 1e-5 across the whole feasible range** (even at 1200 mbar), ~1e4–1e5× below the ~0.3 jetting threshold. Droplet size is geometry-set; **Ca does not drive size or a jetting transition here**.
- **Stage-2 prefactor β = -0.17 [-0.27, -0.05]** (≈0): snap-off timing is γ-insensitive in the dripping window — far below pure capillary scaling (β=1).

## 1. Capillary entry pressure and γ·cosθ(2%)

The observed production onset (~30 mbar, frequency→0) is where the network driving pressure ΔP_rung can no longer overcome the interfacial entry pressure. Reading ΔP_rung at the onset gives P_entry directly (hydraulic, so immune to the stage-time FPS ambiguity).

| Quantity | Value |
|---|---|
| P_entry (2% SDS) | 1898 Pa [1474, 2748] |
| γ·cosθ (2% SDS), r=w/2 | 14.2 mN/m |
| Recommended dP_cap_ow_Pa | 1898 (current: 5000) |

## 2. γ·cosθ vs [SDS] (anchored to onset; ratios reproduce conc_sweep)

Fitted from Stage-1 refill **ratios** (scale-invariant), anchored to the onset value at 2%. The dP_eff ratios (1.00 / 0.99 / 0.90 / 0.80) reproduce `conc_sweep/analysis_notes.md` exactly.

| [SDS] % | n | dP_eff ratio | γ·cosθ (mN/m) | 68% CI | class |
|---|---|---|---|---|---|
| 2 | 23 | 1.00 | 14.2 | [11.2, 17.5] | clean |
| 1 | 10 | 0.99 | 15.4 | [11.1, 19.5] | clean |
| 0.5 | 10 | 0.90 | 25.6 | [16.7, 33.8] | clean |
| 0.25 | 18 | 0.80 | 35.9 | [29.8, 41.4] | heldout |
| 0.125 | 8 | 0.17 | 103.8 | [101.1, 106.0] | heldout |

γ·cosθ rises as [SDS] falls (higher γ, and θ departing from 0 below CMC). The 0.125% point is out-of-regime (Stage-3-dominated; anomalous L_menpoint) — validation only, not a fit input.

## 3. Stage-1 refill back-pressure (distinct from capillary entry)

The 2% Stage-1 Po-scaling is steeper than 1/Po (exponent ≈ −1.29 vs −1.03 baseline). Interpreted as an opposing pressure it implies **~6382 Pa [5798, 6927]** — *larger* than the capillary entry pressure (1898 Pa). At 48 mN/m it is too high for pure capillarity, so the excess is **non-capillary, velocity-dependent refill dissipation** (contact-line / entrance losses), NOT γ·cosθ. Reported separately; not used to estimate γ.

## 4. Stage-2 snap-off prefactor β

Above CMC, β = -0.17 [-0.27, -0.05] — essentially zero. Stage-2 timing barely responds to γ across the dripping window (consistent with conc_sweep's 'flat above CMC'), indicating viscous neck dissipation and dynamic adsorption dominate over pure capillary snap-off. Below CMC Stage-2 does rise (0.25% / 0.125% held out) but the naive γ-model over-predicts the rise — absolute β there needs a measured γ.

## 5. Regime map: stall / dripping / blowout

| Po (mbar) | ΔP_rung (Pa) | entry margin (Pa) | Ca_c | verdict |
|---|---|---|---|---|
| 20 | 1049 | -850 | 1.6e-17 | stall |
| 30 | 1898 | +0 | 2.9e-17 | stall |
| 50 | 3598 | +1700 | 6.2e-17 | dripping |
| 100 | 7847 | +5948 | 4.7e-07 | dripping |
| 200 | 16344 | +14446 | 1.6e-06 | dripping |
| 300 | 24842 | +22944 | 2.7e-06 | dripping |
| 400 | 33340 | +31441 | 3.8e-06 | dripping |
| 600 | 50335 | +48436 | 6.0e-06 | dripping |
| 800 | 67330 | +65432 | 8.2e-06 | dripping |
| 1000 | 84325 | +82427 | 1.0e-05 | blowout |
| 1200 | 101321 | +99422 | 1.3e-05 | blowout |

- **Stall** below the calibrated entry pressure (onset ~30 mbar). Fix: raise Po, lower Qw, or raise surfactant.
- **Dripping** in between — junction Ca ≪ 1, size geometry-set, rate ∝ Po.
- **Blowout** at high Po (~1000 mbar, observed at device start/end): a pressure-driven / spatial-manifold instability, **not** a Ca transition. This simple ladder config stays spatially uniform, so reproducing the start/end effect quantitatively needs the manifold geometry — see `comp_manifold_parametrization`.

## Provisional γ / θ split (needs pendant drop)

Using a literature γ(2% SDS/silicone-oil) ≈ 9 mN/m: cosθ ≈ 1.00 → θ ≈ 0°. **Provisional** — the two regime boundaries cannot pin γ (Ca is tiny; jetting is pressure-driven), so an absolute γ still requires measurement.

## What else is needed (ranked)

1. **Pendant-drop γ** for SDS/silicone-oil (≥1 conc) — the keystone: turns every γ·cosθ into absolute γ + θ, and fixes absolute β. Highest value.
2. **Sessile θ([SDS])** on the device substrate — confirms the provisional θ trend.
3. **Low-pressure frequency data (30–200 mbar)** — the onset anchor rests on a single observation with no measured points below 200 mbar; a few points would pin it.
4. **Manifold/spatial data + geometry** near the ~1000 mbar boundary — to model the start/end blowout (this ladder config can't).
5. **Resolve the 2× stage-time convention** (this CSV vs conc_sweep notes) so *absolute* Stage-1 dissipation constants — not just ratios — can be trusted.
6. Confirm silicone-oil grade/density and that bare-`SDS` = 2% mass.

## Figures

| File | Content |
|---|---|
| `figures/fig_01_gamma_cos_theta_vs_sds.png` | γ·cosθ vs [SDS] with 68% CI |
| `figures/fig_02_stage2_beta.png` | Stage-2 observed vs ideal γ-scaling (β fit) |
| `figures/fig_03_ca_regime_map.png` | Junction Ca(Po) + stall/dripping/blowout margins |
| `figures/fig_04_stage_ratios_validation.png` | S1/S2 ratios vs [SDS] (reproduces conc_sweep) |
