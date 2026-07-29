"""
inversion.py — back-calculate the interfacial groups from pooled timing data.
=============================================================================
All fits are deliberately **scale-invariant** in the stage times, because this
device's absolute stage times carry a 2x FPS-convention ambiguity (see
data_loader). Only Po-scaling SHAPE and cross-[SDS] RATIOS are used; the single
absolute pressure scale comes from the ONSET boundary via the hydraulic solver
(not from any time).

Outputs (each with a bootstrap uncertainty):
  1. P_cap_2pc      capillary entry / back-pressure at 2 % SDS  [Pa]
                    -> gamma*cos(theta) under a stated meniscus-radius convention.
                    Anchored by the observed production onset (~30 mbar).
                    ALSO the recommended value for the model's dP_cap_ow.
  2. P_cap(sds), gamma*cos(theta)(sds)   the [SDS] trend, from Stage-1 refill
                    RATIOS anchored to (1).
  3. beta           Stage-2 snap-off prefactor: how much weaker the observed S2
                    sensitivity to [SDS] is than ideal gamma-scaling (dimensionless).
  X. Stage-1 refill back-pressure from the 2 % Stage-1 Po-exponent steepening
                    (delta ~ -0.26 here). Comes out ~6 kPa -- LARGER than the
                    capillary entry pressure (1) and too high to be pure
                    gamma*cos(theta). Reported as an effective back-pressure that
                    lumps velocity-dependent contact-line / entrance dissipation,
                    NOT as a second gamma estimate.

Physics note on sign: an OPPOSING pressure that GROWS as [SDS] falls is
consistent with the onset AND the longer Stage-1 at low [SDS]. The onset gives
the clean capillary entry pressure (~14 mN/m, matching literature gamma with
cos(theta)~1); the Stage-1 Po-scaling gives a larger *effective* refill
back-pressure, the excess being non-capillary dissipation.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stepgen.config import load_config                              # noqa: E402
from stepgen.models.hydraulics import simulate                     # noqa: E402
from stepgen.models.stage_wise_v3.stage1_physics import compute_rung_resistance  # noqa: E402

from data_loader import load_events, JUNCTION_W_UM, JUNCTION_H_UM  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "v5_30.yaml"

# Characteristic meniscus radius for converting P_cap -> gamma*cos(theta).
# Convention (matches the model's existing 15 mN/m hand-calc in
# cvisc_calibration_results.md): single principal curvature at r = exit_width/2.
R_MEN_M = (JUNCTION_W_UM / 2.0) * 1e-6            # 15 um

N_BOOT = 2000
RNG = np.random.default_rng(20260713)


@dataclass(frozen=True)
class Estimate:
    """A scalar estimate with a bootstrap confidence interval."""
    value: float
    lo: float          # 16th percentile
    hi: float          # 84th percentile (i.e. +/- 1 sigma band)
    unit: str = ""

    def __str__(self) -> str:
        return f"{self.value:.4g} [{self.lo:.4g}, {self.hi:.4g}] {self.unit}".strip()


# ── Hydraulics helpers ──────────────────────────────────────────────────────
def dP_rung_mean(config, Po_mbar: float, Qw_mlhr: float) -> float:
    """Network mean rung driving pressure DP_rung = mean(P_oil - P_water) [Pa]."""
    sim = simulate(config, float(Po_mbar), float(Qw_mlhr), 0.0)
    return float(np.mean(sim.P_oil - sim.P_water))


def gamma_cos_theta_from_Pcap(P_cap_Pa: float, r_men_m: float = R_MEN_M) -> float:
    """gamma*cos(theta) = P_cap * r_men / 2   [N/m]  (P_cap = 2 gamma cos(theta) / r)."""
    return P_cap_Pa * r_men_m / 2.0


# ── 1. Onset anchor: P_cap at 2 % SDS ───────────────────────────────────────
def entry_pressure_from_onset(
    config,
    onset_po_mbar: float = 30.0,
    onset_po_band: tuple[float, float] = (25.0, 40.0),
    qw_mlhr: float = 5.0,
) -> Estimate:
    """
    Capillary entry pressure P_cap(2%) = DP_rung at the observed production onset.

    Below this DP_rung the oil cannot overcome the interfacial entry pressure and
    no droplets form. Uncertainty comes from the uncertainty in the onset pressure
    (user estimate ~30 mbar; band 25-40 mbar).
    """
    val = dP_rung_mean(config, onset_po_mbar, qw_mlhr)
    lo = dP_rung_mean(config, onset_po_band[0], qw_mlhr)
    hi = dP_rung_mean(config, onset_po_band[1], qw_mlhr)
    return Estimate(val, min(lo, hi), max(lo, hi), "Pa")


# ── 2. Stage-1 [SDS] trend (scale-invariant ratios, anchored to onset) ──────
def _cond_events(df: pd.DataFrame, Po: float, Qw: float) -> pd.DataFrame:
    return df[(df.Po_mbar == Po) & (df.Qw_mlhr == Qw)]


def fit_sds_curve(
    df: pd.DataFrame,
    config,
    P_cap_2pc: float,
    Po_ref: float = 200.0,
    Qw_ref: float = 5.0,
    n_boot: int = N_BOOT,
) -> pd.DataFrame:
    """
    Back-calculate P_cap and gamma*cos(theta) for every [SDS] at (Po_ref, Qw_ref).

    Method (all scale-invariant except the single anchor P_cap_2pc):
        dP_eff(2%)   = DP_rung(Po_ref) - P_cap(2%)          [effective S1 driving]
        dP_eff(sds)  = dP_eff(2%) * [Vreset_ratio / t1_ratio]
        P_cap(sds)   = DP_rung(Po_ref) - dP_eff(sds)
        gamma cos(theta)(sds) = P_cap(sds) * r_men / 2
    where the ratios are (sds / 2%) of mean V_reset and mean Stage-1 time.
    Bootstrap resamples events within each [SDS] to get CIs.
    """
    dP_rung = dP_rung_mean(config, Po_ref, Qw_ref)
    dP_eff_2pc = dP_rung - P_cap_2pc

    base = _cond_events(df, Po_ref, Qw_ref)
    base2 = base[base.sds_pc == 2.0]
    if len(base2) == 0:
        raise ValueError("No 2% baseline events at reference condition.")

    rows = []
    for sds in sorted(base.sds_pc.unique(), reverse=True):
        sub = base[base.sds_pc == sds]
        # point estimate from means
        vr_ratio = sub.V_reset_m3.mean() / base2.V_reset_m3.mean()
        t1_ratio = sub.S1_s.mean() / base2.S1_s.mean()
        dP_eff = dP_eff_2pc * vr_ratio / t1_ratio
        P_cap = dP_rung - dP_eff
        gct = gamma_cos_theta_from_Pcap(P_cap)

        # bootstrap over events (both sds group and 2% baseline resampled)
        boot_gct, boot_pcap = [], []
        s1b = base2.S1_s.to_numpy(); vrb = base2.V_reset_m3.to_numpy()
        s1s = sub.S1_s.to_numpy();  vrs = sub.V_reset_m3.to_numpy()
        for _ in range(n_boot):
            bb = RNG.integers(0, len(s1b), len(s1b))
            bs = RNG.integers(0, len(s1s), len(s1s))
            vr_r = vrs[bs].mean() / vrb[bb].mean()
            t1_r = s1s[bs].mean() / s1b[bb].mean()
            dpe = dP_eff_2pc * vr_r / t1_r
            pc = dP_rung - dpe
            if np.isfinite(pc):
                boot_pcap.append(pc)
                boot_gct.append(gamma_cos_theta_from_Pcap(max(pc, 0.0)))
        rows.append({
            "sds_pc": sds, "n": len(sub),
            "t1_ratio": t1_ratio, "vr_ratio": vr_ratio,
            "dP_eff_ratio": vr_ratio / t1_ratio,
            "P_cap_Pa": P_cap,
            "P_cap_lo": np.percentile(boot_pcap, 16),
            "P_cap_hi": np.percentile(boot_pcap, 84),
            "gamma_cos_theta_mNm": gct * 1e3,
            "gct_lo_mNm": np.percentile(boot_gct, 16) * 1e3,
            "gct_hi_mNm": np.percentile(boot_gct, 84) * 1e3,
            "regime_class": sub.regime_class.iloc[0],
        })
    return pd.DataFrame(rows)


# ── 3. Stage-2 prefactor beta (scale-invariant) ─────────────────────────────
def fit_stage2_beta(
    df: pd.DataFrame,
    sds_curve: pd.DataFrame,
    Po_ref: float = 200.0,
    Qw_ref: float = 5.0,
    n_boot: int = N_BOOT,
) -> Estimate:
    """
    Stage-2 snap-off prefactor beta.

    Ideal capillary snap-off scales as tau ~ mu_out * R / gamma, so for fixed
    geometry the ideal S2 ratio vs the 2% baseline is
        S2_ideal_ratio(sds) = gamma(sds) / gamma(2%)  ~  P_cap(sds) / P_cap(2%)
    (using gamma*cos(theta) as the gamma proxy). The observed S2 ratio is smaller;
    beta is the slope of observed-vs-ideal excess:
        (S2_obs_ratio - 1) = beta * (S2_ideal_ratio - 1)
    beta = 1 -> pure gamma-scaling; beta < 1 -> snap-off less gamma-sensitive
    (viscous neck dissipation + dynamic adsorption). Fitted over ABOVE + near-CMC
    points where an S2 trend exists; 0.125% (deep sub-CMC, different regime) is
    excluded from the fit and reported as validation.
    """
    base = _cond_events(df, Po_ref, Qw_ref)
    base2 = base[base.sds_pc == 2.0]
    s2_base = base2.S2_s.to_numpy()

    # ideal ratio from the gamma*cos(theta) curve (proxy for gamma)
    gct = sds_curve.set_index("sds_pc")["gamma_cos_theta_mNm"]
    gct2 = gct.loc[2.0]

    xs, ys, groups = [], [], []
    for sds in sorted(base.sds_pc.unique(), reverse=True):
        if sds < 0.5:      # near/sub-CMC (0.25, 0.125): excluded from fit (validation only)
            continue
        sub = base[base.sds_pc == sds]
        ideal_ratio = gct.loc[sds] / gct2
        obs_ratio = sub.S2_s.mean() / base2.S2_s.mean()
        xs.append(ideal_ratio - 1.0)
        ys.append(obs_ratio - 1.0)
        groups.append(sub.S2_s.to_numpy())

    xs = np.array(xs)
    # point estimate: least-squares slope through origin
    beta = float(np.dot(xs, ys) / np.dot(xs, xs)) if np.dot(xs, xs) > 0 else float("nan")

    # bootstrap over events
    boot = []
    for _ in range(n_boot):
        yb = []
        b2 = s2_base[RNG.integers(0, len(s2_base), len(s2_base))].mean()
        for g in groups:
            gb = g[RNG.integers(0, len(g), len(g))].mean()
            yb.append(gb / b2 - 1.0)
        yb = np.array(yb)
        if np.dot(xs, xs) > 0:
            boot.append(float(np.dot(xs, yb) / np.dot(xs, xs)))
    return Estimate(beta, float(np.percentile(boot, 16)), float(np.percentile(boot, 84)), "")


# ── X. Po-scaling cross-check (independent P_cap at 2%) ─────────────────────
def po_scaling_crosscheck(df: pd.DataFrame, config, Qw_ref: float = 5.0) -> dict:
    """
    Independent P_cap(2%) from the 2 % Stage-1 Po-scaling steepening.

    Fits t1(Po) = k / (DP_rung(Po) - P_cap) over the 2% baseline Po points by
    grid-searching P_cap to best match the log-log slope, and reports the fitted
    P_cap. Diagnostic / consistency check on the onset anchor.
    """
    b2 = df[(df.sds_pc == 2.0) & (df.Qw_mlhr == Qw_ref)]
    po_vals = np.array(sorted(b2.Po_mbar.unique()))
    t1_obs = np.array([b2[b2.Po_mbar == p].S1_s.mean() for p in po_vals])
    dP = np.array([dP_rung_mean(config, p, Qw_ref) for p in po_vals])

    def resid(P_cap):
        denom = dP - P_cap
        if np.any(denom <= 0):
            return np.inf
        # best k in log space -> compare shapes only (scale-invariant)
        pred = 1.0 / denom
        # fit multiplicative constant via log-mean offset
        c = np.exp(np.mean(np.log(t1_obs) - np.log(pred)))
        return float(np.sum((np.log(t1_obs) - np.log(c * pred)) ** 2))

    grid = np.linspace(0.0, min(dP) * 0.95, 400)
    r = np.array([resid(p) for p in grid])
    P_cap = float(grid[np.argmin(r)])
    # Weak-constraint band: all P_cap whose residual is within 2x the minimum
    # (this fit is known to be poorly constrained -- cvisc delta = -0.142, +/-8%).
    rmin = float(np.min(r))
    ok = grid[r <= 2.0 * rmin] if rmin > 0 else grid[r <= (rmin + 1e-6)]
    band = (float(ok.min()), float(ok.max())) if len(ok) else (P_cap, P_cap)
    return {
        "P_cap_Pa": P_cap, "P_cap_band": band,
        "gamma_cos_theta_mNm": gamma_cos_theta_from_Pcap(P_cap) * 1e3,
        "Po_mbar": po_vals, "t1_obs": t1_obs, "dP_rung_Pa": dP,
    }


if __name__ == "__main__":
    cfg = load_config(str(CONFIG_PATH))
    df = load_events()
    R_rung = compute_rung_resistance(cfg)
    print(f"R_rung = {R_rung:.4e} Pa.s/m3 | r_men = {R_MEN_M*1e6:.1f} um\n")

    onset = entry_pressure_from_onset(cfg)
    print(f"[1] Onset anchor  P_cap(2%) = {onset}  "
          f"-> gamma*cos(theta) = {gamma_cos_theta_from_Pcap(onset.value)*1e3:.1f} mN/m")
    print(f"    (recommended model dP_cap_ow; current config value = "
          f"{cfg.droplet_model.dP_cap_ow_Pa:.0f} Pa)\n")

    xc = po_scaling_crosscheck(df, cfg)
    print(f"[X] Stage-1 refill back-pressure (from Po-scaling steepening) = "
          f"{xc['P_cap_Pa']:.0f} Pa  [{xc['P_cap_band'][0]:.0f}-{xc['P_cap_band'][1]:.0f}]")
    print(f"    NOTE: exceeds the capillary entry pressure ({onset.value:.0f} Pa) and implies "
          f"gamma*cos(theta)={xc['gamma_cos_theta_mNm']:.0f} mN/m,")
    print(f"    too high for pure capillarity -> extra velocity-dependent refill "
          f"dissipation (contact-line / entrance), NOT gamma.\n")

    curve = fit_sds_curve(df, cfg, P_cap_2pc=onset.value)
    print("[2] gamma*cos(theta) vs [SDS] (Po=200, Qw=5):")
    print(curve[["sds_pc", "n", "dP_eff_ratio", "P_cap_Pa",
                 "gamma_cos_theta_mNm", "gct_lo_mNm", "gct_hi_mNm", "regime_class"]]
          .to_string(index=False, float_format="%.2f"))

    beta = fit_stage2_beta(df, curve)
    print(f"\n[3] Stage-2 prefactor  beta = {beta}   (1.0 = pure gamma-scaling)")
