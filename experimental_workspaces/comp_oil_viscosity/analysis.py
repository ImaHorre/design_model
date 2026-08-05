"""
comp_oil_viscosity — what oil viscosity does the model need, once the rung
resistance is exact?

Context
-------
W2-1 replaced four disagreeing rectangular-duct resistances with one, normalised
the way Shah & London's polynomial is defined.  On V5-30 that drops the rung
resistance to 0.65x its previous value, so the model now delivers ~1.53x more oil
at the same pressure.  The old agreement with experiment rested on two errors
cancelling; one of them is now gone.

`C_visc` (a global multiplier on ΔP/R) is deleted, not refitted — Conor's ruling,
2026-08-05.  A constant that restores agreement by multiplying ΔP/R at fixed
geometry *is* a viscosity, so this script asks the question that way: **what µ_oil
does the data imply**, and does one value hold across conditions?

What is fitted, and what is not
-------------------------------
One number: `fluids.mu_dispersed`.  Nothing else is touched — geometry is as
drawn (with the real two-width DFU profile), the reset length is the measured
`sqrt(w·h)`, and there is no correction term anywhere.

Two independent measures of the same thing
------------------------------------------
The sweep gives Q per DFU two ways, and their disagreement is the noise floor
this fit cannot beat:

  conservation  Q = V_drop / t_cycle          (measured droplet diameter)
  meniscus      Q = L_menpoint · w · h / t_S1 (measured meniscus sweep)

Usage
-----
    python experimental_workspaces/comp_oil_viscosity/analysis.py
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from stepgen.config import load_config
from stepgen.design.sweep import evaluate_candidate
from stepgen.models.droplets import droplet_volume
from stepgen.models.resistance import rung_resistance

HERE = Path(__file__).parent
REPO = HERE.parents[1]
# The physical copy of this data lives in po_sweep/ (multi-workspace data rule,
# CLAUDE.md): one identity, one location, referenced from here.
DATA = REPO / "experimental_workspaces" / "po_sweep" / "data" / "stage_timings.csv"
CONFIG = HERE / "snapshots" / "v5_30_2026-08-05.yaml"
RESULTS = HERE / "results"

#: the continuous phase configs/v5_30.yaml describes: 2% SDS in water.
#: The file also carries 0.125/0.25/0.5/1% SDS rows (below CMC for the lowest —
#: explicitly outside the model's scope per the v3 physics plan, Section F) and a
#: 2.5% NaCas row.  Those are a different fluid system and are excluded here.
CONT_PHASE = "SDS"


def measured() -> pd.DataFrame:
    """Per-(Qw, Po) measured cycle timings and the two independent Q measures."""
    d = pd.read_csv(DATA)
    d = d[(d.DeviceID == "V5-8-1") & (d.ContPhase == CONT_PHASE) & (d.DispPhase == "SO")]
    d = d.dropna(subset=["Stage1_s", "Stage2_s", "Stage3_s"])
    d = d.assign(t_cycle=d.Stage1_s + d.Stage2_s + d.Stage3_s)

    cfg = load_config(CONFIG)
    w = cfg.geometry.junction.exit_width
    h = cfg.geometry.junction.exit_depth

    # Q two ways, per observation, then aggregated.
    d = d.assign(
        Q_conservation=droplet_volume(d.Droplet_diameter_um * 1e-6) / d.t_cycle,
        Q_meniscus=(d.L_menpoint_um * 1e-6) * w * h / d.Stage1_s,
    )

    g = d.groupby(["ContPhaseFlow", "DispPhasePressure"])
    out = pd.DataFrame({
        "n": g.size(),
        "t_S1_s": g.Stage1_s.median(),
        "t_S23_s": (d.Stage2_s + d.Stage3_s).groupby(
            [d.ContPhaseFlow, d.DispPhasePressure]).median(),
        "t_cycle_s": g.t_cycle.median(),
        "f_meas_hz": 1.0 / g.t_cycle.median(),
        "D_meas_um": g.Droplet_diameter_um.median(),
        "L_menpoint_um": g.L_menpoint_um.median(),
        "Q_conservation": g.Q_conservation.median(),
        "Q_meniscus": g.Q_meniscus.median(),
    }).reset_index().rename(
        columns={"ContPhaseFlow": "Qw_mlhr", "DispPhasePressure": "Po_mbar"})
    out["Q_disagreement_pct"] = 100.0 * (
        out.Q_meniscus - out.Q_conservation) / out.Q_conservation
    return out


def model_at(cfg, Po_mbar: float, Qw_mlhr: float, mu_oil: float) -> dict:
    """Solve the device at one condition with the oil viscosity set to *mu_oil*."""
    c = replace(cfg, fluids=replace(cfg.fluids, mu_dispersed=mu_oil))
    r = evaluate_candidate(c, Po_in_mbar=float(Po_mbar), Qw_in_mlhr=float(Qw_mlhr))
    q = float(r["Q_per_rung_avg"])
    V_drop = droplet_volume(float(r["D_pred"]))
    V_reset = math.sqrt(
        c.geometry.junction.exit_width * c.geometry.junction.exit_depth
    ) * c.geometry.junction.exit_width * c.geometry.junction.exit_depth
    return {
        "f_model_hz": float(r["f_pred_mean"]),
        "q_rung": q,
        "dP_rung_mbar": float(r["dP_avg"]) / 100.0,
        "t_cycle_model_s": V_drop / q if q > 0 else math.inf,
        "t_S1_model_s": V_reset / q if q > 0 else math.inf,
        "D_pred_um": float(r["D_pred"]) * 1e6,
    }


def _rms_log_err(cfg, rows: pd.DataFrame, mu: float) -> float:
    errs = [math.log(model_at(cfg, r.Po_mbar, r.Qw_mlhr, mu)["f_model_hz"] / r.f_meas_hz)
            for _, r in rows.iterrows()]
    return float(np.sqrt(np.mean(np.square(errs))))


def fit_mu(cfg, rows: pd.DataFrame, grid: np.ndarray) -> tuple[float, pd.DataFrame]:
    """
    The µ that minimises RMS log-error in frequency over *rows*.

    Log-error, not relative error, so a 2x over and a 2x under cost the same —
    a fit on raw residuals would sit systematically high.

    Coarse scan then golden-section refine.  A full 1 cP sweep is ~400 solves per
    group at 0.4 s each; this is ~30, and the reported µ is rounded to the
    nearest cP anyway, which is far finer than the data can distinguish.
    """
    scan = pd.DataFrame([
        {"mu_cP": mu * 1e3, "rms_log_err": _rms_log_err(cfg, rows, mu)}
        for mu in grid
    ])
    i = int(scan.rms_log_err.idxmin())
    lo = float(scan.mu_cP.iloc[max(i - 1, 0)]) * 1e-3
    hi = float(scan.mu_cP.iloc[min(i + 1, len(scan) - 1)]) * 1e-3

    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c_, d_ = b - phi * (b - a), a + phi * (b - a)
    fc, fd = _rms_log_err(cfg, rows, c_), _rms_log_err(cfg, rows, d_)
    while (b - a) > 0.5e-3:            # 0.5 cP — below the data's resolution
        if fc < fd:
            b, d_, fd = d_, c_, fc
            c_ = b - phi * (b - a)
            fc = _rms_log_err(cfg, rows, c_)
        else:
            a, c_, fc = c_, d_, fd
            d_ = a + phi * (b - a)
            fd = _rms_log_err(cfg, rows, d_)
    return round((a + b) / 2.0, 6), scan


def table_at(cfg, rows: pd.DataFrame, mu: float) -> pd.DataFrame:
    out = []
    for _, row in rows.iterrows():
        m = model_at(cfg, row.Po_mbar, row.Qw_mlhr, mu)
        out.append({
            "Qw_mlhr": row.Qw_mlhr, "Po_mbar": row.Po_mbar, "n": row.n,
            "f_meas_hz": row.f_meas_hz, "f_model_hz": m["f_model_hz"],
            "f_err_pct": 100.0 * (m["f_model_hz"] - row.f_meas_hz) / row.f_meas_hz,
            "t_S1_meas_s": row.t_S1_s, "t_S1_model_s": m["t_S1_model_s"],
            "t_S1_err_pct": 100.0 * (m["t_S1_model_s"] - row.t_S1_s) / row.t_S1_s,
            "t_cycle_meas_s": row.t_cycle_s, "t_cycle_model_s": m["t_cycle_model_s"],
            # Stage 2+3 by difference: the model has no separate growth clock, so
            # this is "what the cycle needs that Stage 1 does not explain".
            "t_S23_meas_s": row.t_S23_s,
            "t_S23_model_s": m["t_cycle_model_s"] - m["t_S1_model_s"],
            "t_S23_err_pct": 100.0 * (
                (m["t_cycle_model_s"] - m["t_S1_model_s"]) - row.t_S23_s) / row.t_S23_s,
            "dP_rung_mbar": m["dP_rung_mbar"],
            "D_meas_um": row.D_meas_um, "D_pred_um": m["D_pred_um"],
        })
    return pd.DataFrame(out)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    cfg = load_config(CONFIG)
    mu_config = cfg.fluids.mu_dispersed

    meas = measured()
    meas.to_csv(RESULTS / "measured_by_condition.csv", index=False)

    print(f"config: {CONFIG.name}   mu_dispersed = {mu_config*1e3:.1f} cP")
    print(f"R_rung  = {rung_resistance(cfg):.4e} Pa.s/m3 "
          f"(piecewise over the real two-width DFU profile)\n")
    print("=== measured, 2% SDS / sunflower oil, V5-8-1 ===")
    print(meas.to_string(index=False, float_format=lambda v: f"{v:.4g}"))

    print("\n=== the noise floor: two independent measures of Q ===")
    print(f"  meniscus vs conservation disagree by "
          f"{meas.Q_disagreement_pct.abs().min():.0f}-"
          f"{meas.Q_disagreement_pct.abs().max():.0f}% "
          f"(median {meas.Q_disagreement_pct.abs().median():.0f}%)")

    grid = np.arange(30, 161, 10) * 1e-3
    results: dict[str, object] = {
        "config": CONFIG.name,
        "mu_config_cP": mu_config * 1e3,
        "R_rung_Pa_s_per_m3": rung_resistance(cfg),
        "Q_disagreement_pct": {
            "min": float(meas.Q_disagreement_pct.abs().min()),
            "max": float(meas.Q_disagreement_pct.abs().max()),
            "median": float(meas.Q_disagreement_pct.abs().median()),
        },
        "fits": {},
    }

    # ── per-Qw fits: the cross-check the 83 cP figure never had ─────────────
    for qw, rows in meas.groupby("Qw_mlhr"):
        if len(rows) < 2:
            continue
        mu_best, scan = fit_mu(cfg, rows, grid)
        scan.to_csv(RESULTS / f"mu_scan_qw{int(qw)}.csv", index=False)
        tab = table_at(cfg, rows, mu_best)
        tab.to_csv(RESULTS / f"agreement_qw{int(qw)}_fitted.csv", index=False)
        print(f"\n=== Qw = {qw:g} mL/hr  ({len(rows)} pressures) ===")
        print(f"  best-fit mu = {mu_best*1e3:.0f} cP")
        print(tab[["Po_mbar", "n", "f_meas_hz", "f_model_hz", "f_err_pct",
                   "t_S1_meas_s", "t_S1_model_s", "t_S1_err_pct"]]
              .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        results["fits"][f"qw_{int(qw)}"] = {
            "mu_cP": mu_best * 1e3,
            "n_pressures": int(len(rows)),
            "max_abs_f_err_pct": float(tab.f_err_pct.abs().max()),
        }

    # ── global fit across every condition ───────────────────────────────────
    mu_all, scan_all = fit_mu(cfg, meas, grid)
    scan_all.to_csv(RESULTS / "mu_scan_all.csv", index=False)
    tab_all = table_at(cfg, meas, mu_all)
    tab_all.to_csv(RESULTS / "agreement_all_fitted.csv", index=False)
    print(f"\n=== all conditions pooled ({len(meas)} points) ===")
    print(f"  best-fit mu = {mu_all*1e3:.0f} cP")
    print(tab_all[["Qw_mlhr", "Po_mbar", "n", "f_meas_hz", "f_model_hz", "f_err_pct",
                   "t_S1_meas_s", "t_S1_model_s", "t_S1_err_pct"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    # ── what the config's own viscosity gives, for the record ───────────────
    tab_cfg = table_at(cfg, meas, mu_config)
    tab_cfg.to_csv(RESULTS / "agreement_all_config_mu.csv", index=False)
    print(f"\n=== at the config's mu = {mu_config*1e3:.0f} cP (NOT fitted) ===")
    print("  where the residual lives: Stage 1 vs everything after it")
    print(tab_cfg[["Qw_mlhr", "Po_mbar", "f_err_pct",
                   "t_S1_meas_s", "t_S1_model_s", "t_S1_err_pct",
                   "t_S23_meas_s", "t_S23_model_s", "t_S23_err_pct"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    qw5 = tab_cfg[tab_cfg.Qw_mlhr == 5]
    print(f"\n  Stage 1 at Qw = 5 mL/hr (the config's condition), mu = "
          f"{mu_config*1e3:.0f} cP: "
          f"{qw5.t_S1_err_pct.min():+.1f}% to {qw5.t_S1_err_pct.max():+.1f}%")
    print(f"  Stage 2+3 same rows: "
          f"{qw5.t_S23_err_pct.min():+.1f}% to {qw5.t_S23_err_pct.max():+.1f}%")

    results["stage_split_at_config_mu"] = {
        "qw5_t_S1_err_pct": [float(qw5.t_S1_err_pct.min()), float(qw5.t_S1_err_pct.max())],
        "qw5_t_S23_err_pct": [float(qw5.t_S23_err_pct.min()), float(qw5.t_S23_err_pct.max())],
    }

    results["fits"]["all"] = {
        "mu_cP": mu_all * 1e3,
        "n_points": int(len(meas)),
        "max_abs_f_err_pct": float(tab_all.f_err_pct.abs().max()),
    }
    results["at_config_mu"] = {
        "mu_cP": mu_config * 1e3,
        "max_abs_f_err_pct": float(tab_cfg.f_err_pct.abs().max()),
        "mean_f_err_pct": float(tab_cfg.f_err_pct.mean()),
    }
    (RESULTS / "fit_summary.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {RESULTS}")


if __name__ == "__main__":
    main()
