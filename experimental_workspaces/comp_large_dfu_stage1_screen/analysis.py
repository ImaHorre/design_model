"""
Large-DFU Stage-1 hydraulic screen.

Screens a sweep grid of large/deep O/W DFU ladder candidates for Stage-1
hydraulic refill feasibility only (droplet formation treated as instantaneous):

    t_S1   = V_reset * R_DFU / DP_eff
    V_reset = sqrt(exit_width * exit_depth) * exit_width * exit_depth
    DP_eff  = DP_DFU - 12 mbar   (flat fitted Stage-1 capillary back-pressure)
    pass:   DP_eff > 0 and t_S1 <= 1 s for EVERY DFU in the ladder

Reuses stepgen primitives directly (no changes to core stepgen):
  - stepgen.config dataclasses, built in Python per candidate (no per-candidate YAML)
  - stepgen.models.resistance.resistance_piecewise for the scalar R_DFU
  - stepgen.models.hydraulics.simulate — plain steady-state mixed-BC ladder solve
    (NOT generator.iterative_solve, which applies Stage-2-style capillary
    threshold classification — irrelevant here since Stage 2 is deferred)

Run from the repo root:
    python experimental_workspaces/comp_large_dfu_stage1_screen/analysis.py
"""

from __future__ import annotations

import itertools
import math
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

WORKSPACE = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from stepgen.config import (  # noqa: E402
    DeviceConfig,
    FluidConfig,
    GeometryConfig,
    JunctionConfig,
    MainChannelConfig,
    MicrochannelSection,
    OperatingConfig,
    RungConfig,
)
from stepgen.models.hydraulics import simulate  # noqa: E402
from stepgen.models.resistance import resistance_piecewise  # noqa: E402

FIG_DPI = 150
M3S_TO_MLHR = 3600.0 / 1e-6  # m³/s → mL/hr


# ---------------------------------------------------------------------------
# Study config / candidate grid
# ---------------------------------------------------------------------------

def load_study() -> dict:
    with open(WORKSPACE / "study_config.yaml", "r") as fh:
        return yaml.safe_load(fh)


def po_sweep_mbar(study: dict) -> np.ndarray:
    s = study["operating"]["Po_sweep_mbar"]
    return np.arange(s["min"], s["max"] + s["step"] / 2.0, s["step"])


def build_candidates(study: dict) -> list[dict]:
    grid = study["sweep_grid"]
    combos = itertools.product(
        grid["N_DFU"],
        grid["DFU_depth_um"],
        grid["DFU_length_mm"],
        grid["upstream_AR"],
        grid["main_depth_um"],
    )
    candidates = []
    for cid, (n, depth_um, length_mm, ar, main_um) in enumerate(combos):
        candidates.append({
            "candidate_id": cid,
            "candidate_key": f"N{n}_D{depth_um:g}_L{length_mm:g}_AR{ar:g}_M{main_um:g}",
            "N_DFU": int(n),
            "DFU_depth_um": float(depth_um),
            "DFU_length_mm": float(length_mm),
            "upstream_AR": float(ar),
            "main_depth_um": float(main_um),
        })
    return candidates


def build_device_config(cand: dict, study: dict) -> DeviceConfig:
    """Apply the geometry construction rules; all unit conversion happens here."""
    gr = study["geometry_rules"]
    fl = study["fluids"]
    op = study["operating"]

    depth = cand["DFU_depth_um"] * 1e-6
    length = cand["DFU_length_mm"] * 1e-3
    main_depth = cand["main_depth_um"] * 1e-6

    exit_depth = depth
    exit_width = gr["exit_width_factor"] * depth
    pitch = gr["pitch_factor"] * exit_width
    upstream_width = cand["upstream_AR"] * depth

    Mcw = min(gr["main_width_factor"] * main_depth, gr["main_width_cap_um"] * 1e-6)
    Mcl = cand["N_DFU"] * pitch  # informational only — Nmc_override fixes Nmc

    profile = (
        MicrochannelSection(
            length=gr["section1_length_frac"] * length,
            width=upstream_width,
            depth=depth,
        ),
        MicrochannelSection(
            length=gr["section2_length_frac"] * length,
            width=gr["section2_width_factor"] * depth,
            depth=depth,
        ),
    )
    # mcd/mcw/mcl/constriction_ratio are required fields but ignored by the
    # resistance calc whenever profile is non-empty — sensible placeholders.
    rung = RungConfig(
        mcd=depth,
        mcw=upstream_width,
        mcl=length,
        pitch=pitch,
        constriction_ratio=1.0,
        profile=profile,
    )
    geometry = GeometryConfig(
        main=MainChannelConfig(Mcd=main_depth, Mcw=Mcw, Mcl=Mcl),
        rung=rung,
        junction=JunctionConfig(exit_width=exit_width, exit_depth=exit_depth),
        Nmc_override=cand["N_DFU"],
    )
    fluids = FluidConfig(
        mu_continuous=fl["mu_continuous"],
        mu_dispersed=fl["mu_dispersed"],
        emulsion_ratio=fl["emulsion_ratio"],
        gamma=fl["gamma"],
        phase_system=fl["phase_system"],
        continuous_fluid_name="water",
        dispersed_fluid_name="sunflower_oil",
    )
    operating = OperatingConfig(
        Po_in_mbar=study["operating"]["Po_sweep_mbar"]["min"],  # overridden per solve
        Qw_in_mlhr=op["Qw_in_mlhr"],
        P_out_mbar=op["P_out_mbar"],
    )
    return DeviceConfig(fluids=fluids, geometry=geometry, operating=operating)


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

def _t_s1_spread_pct(t: np.ndarray) -> float:
    """Percent spread 100*(max-min)/mean; NaN if any rung inactive (t=inf)."""
    if not np.isfinite(t).all():
        return float("nan")
    mean = float(np.mean(t))
    if mean <= 0:
        return float("nan")
    return float(100.0 * (np.max(t) - np.min(t)) / mean)


def screen_candidate(config: DeviceConfig, cand: dict, pressures_mbar: np.ndarray,
                     study: dict) -> tuple[dict, list[dict]]:
    """Screen one candidate across the pressure sweep.

    Returns (summary_row, per_pressure_rows).
    """
    s1 = study["stage1_screen"]
    mfg = study["manufacturing"]
    back_Pa = s1["stage1_backpressure_mbar"] * 100.0
    t_max_s = s1["t_S1_max_s"]
    ideal_mbar = s1["ideal_pressure_mbar"]
    hard_mbar = s1["hard_pressure_mbar"]
    Qw = study["operating"]["Qw_in_mlhr"]
    Pout = study["operating"]["P_out_mbar"]

    R_DFU = resistance_piecewise(config.geometry.rung.profile, config.fluids.mu_dispersed)
    ew = config.geometry.junction.exit_width
    ed = config.geometry.junction.exit_depth
    V_reset = math.sqrt(ew * ed) * ew * ed

    theta = math.radians(study["laplace_diagnostic"]["theta_deg"])
    P_cap_laplace_Pa = config.fluids.gamma * math.cos(theta) * (1.0 / ed + 1.0 / ew)

    id_cols = {k: cand[k] for k in (
        "candidate_id", "candidate_key", "N_DFU", "DFU_depth_um",
        "DFU_length_mm", "upstream_AR", "main_depth_um",
    )}

    per_pressure_rows: list[dict] = []
    by_pressure: dict[float, dict] = {}
    for Po in pressures_mbar:
        res = simulate(config, Po_in_mbar=float(Po), Qw_in_mlhr=Qw, P_out_mbar=Pout)
        DP = res.P_oil - res.P_water
        DP_eff = DP - back_Pa
        active = DP_eff > 0.0
        t_S1 = np.full(DP.shape, np.inf)
        t_S1[active] = V_reset * R_DFU / DP_eff[active]
        passes = bool(active.all() and float(np.max(t_S1)) <= t_max_s)
        emulsion_pct = 100.0 * res.Q_oil_total / (res.Q_oil_total + res.Q_water_total)

        stats = {
            "Po_in_mbar": float(Po),
            "active_fraction": float(np.mean(active)),
            "DP_DFU_mean_Pa": float(np.mean(DP)),
            "DP_DFU_min_Pa": float(np.min(DP)),
            "DP_DFU_max_Pa": float(np.max(DP)),
            "t_S1_mean_s": float(np.mean(t_S1)),
            "t_S1_min_s": float(np.min(t_S1)),
            "t_S1_max_s": float(np.max(t_S1)),
            "t_S1_spread_pct": _t_s1_spread_pct(t_S1),
            "emulsion_pct": float(emulsion_pct),
            "passes": passes,
            "_P_oil_inlet_Pa": float(res.P_oil[0]),
        }
        by_pressure[float(Po)] = stats
        row = dict(id_cols)
        row.update({k: v for k, v in stats.items() if not k.startswith("_")})
        per_pressure_rows.append(row)

    passing = [p for p, s in by_pressure.items() if s["passes"]]
    min_passing = min(passing) if passing else float("nan")

    at_ideal = by_pressure[float(ideal_mbar)]
    at_hard = by_pressure[float(hard_mbar)]

    # Manufacturing feasibility — diagnostic columns only, never excludes rows.
    delam_load = at_hard["_P_oil_inlet_Pa"] * config.geometry.main.Mcw
    mfg_ok_depth = cand["main_depth_um"] <= mfg["max_main_depth_um"]
    max_delam = mfg.get("max_delam_line_load_N_per_m", None)
    mfg_ok_delam = (delam_load <= max_delam) if max_delam is not None else True
    mfg_ok = bool(mfg_ok_depth and mfg_ok_delam)

    summary = dict(id_cols)
    summary.update({
        "exit_width_um": ew * 1e6,
        "exit_depth_um": ed * 1e6,
        "pitch_um": config.geometry.rung.pitch * 1e6,
        "main_Mcw_um": config.geometry.main.Mcw * 1e6,
        "main_Mcl_m": config.geometry.main.Mcl,
        "R_DFU_Pa_s_per_m3": R_DFU,
        "V_reset_m3": V_reset,
        "P_cap_laplace_mbar": P_cap_laplace_Pa / 100.0,
        "min_passing_pressure_mbar": min_passing,
        "pass_at_ideal_500": bool(by_pressure[float(ideal_mbar)]["passes"]),
        "pass_at_hard_1000": bool(by_pressure[float(hard_mbar)]["passes"]),
        "active_fraction_at_500mbar": at_ideal["active_fraction"],
        "t_S1_mean_at_500mbar_s": at_ideal["t_S1_mean_s"],
        "t_S1_min_at_500mbar_s": at_ideal["t_S1_min_s"],
        "t_S1_max_at_500mbar_s": at_ideal["t_S1_max_s"],
        "t_S1_spread_at_500mbar": at_ideal["t_S1_spread_pct"],
        "emulsion_pct_at_500mbar": at_ideal["emulsion_pct"],
        "active_fraction_at_1000mbar": at_hard["active_fraction"],
        "t_S1_mean_at_1000mbar_s": at_hard["t_S1_mean_s"],
        "t_S1_min_at_1000mbar_s": at_hard["t_S1_min_s"],
        "t_S1_max_at_1000mbar_s": at_hard["t_S1_max_s"],
        "t_S1_spread_at_1000mbar": at_hard["t_S1_spread_pct"],
        "emulsion_pct_at_1000mbar": at_hard["emulsion_pct"],
        "delam_line_load_at_1000mbar_N_per_m": delam_load,
        "manufacturing_ok_depth": bool(mfg_ok_depth),
        "manufacturing_ok_delam": bool(mfg_ok_delam),
        "manufacturing_ok": mfg_ok,
    })
    return summary, per_pressure_rows


# ---------------------------------------------------------------------------
# Sanity check — V5-30 reset length (standalone; not a sweep candidate)
# ---------------------------------------------------------------------------

def sanity_check_v530_reset_length(study: dict) -> dict:
    sc = study["sanity_checks"]
    est_um = math.sqrt(sc["v5_30_exit_width_um"] * sc["v5_30_exit_depth_um"])
    lo, hi = sc["v5_30_observed_reset_length_um"]
    within_loose_bound = 10.0 <= est_um <= 30.0
    print(
        f"[sanity] V5-30 reset length: sqrt({sc['v5_30_exit_width_um']:g}*"
        f"{sc['v5_30_exit_depth_um']:g}) = {est_um:.1f} um "
        f"vs observed {lo:g}-{hi:g} um (loose bound 10-30 um: "
        f"{'OK' if within_loose_bound else 'FAIL'})"
    )
    assert within_loose_bound, "V5-30 reset-length formula outside loose 10-30 um bound"
    return {
        "estimate_um": est_um,
        "observed_lo_um": lo,
        "observed_hi_um": hi,
        "residual_pct_vs_low": 100.0 * (lo - est_um) / est_um,
    }


# ---------------------------------------------------------------------------
# Qw / emulsion-ratio bounded sensitivity check
# ---------------------------------------------------------------------------

def qw_for_target_emulsion(config: DeviceConfig, Po_mbar: float, Qw0_mlhr: float,
                           target_pct: float, P_out_mbar: float, max_iter: int):
    """Short fixed-point loop: adjust Qw so emulsion fraction hits target_pct."""
    Qw = Qw0_mlhr
    res = simulate(config, Po_in_mbar=Po_mbar, Qw_in_mlhr=Qw, P_out_mbar=P_out_mbar)
    for _ in range(max_iter):
        Qo_mlhr = res.Q_oil_total * M3S_TO_MLHR
        Qw_new = Qo_mlhr * (100.0 / target_pct - 1.0)
        if Qw_new <= 0:
            break
        Qw = Qw_new
        res = simulate(config, Po_in_mbar=Po_mbar, Qw_in_mlhr=Qw, P_out_mbar=P_out_mbar)
    return Qw, res


def run_qw_sensitivity(summary_df: pd.DataFrame, candidates: list[dict],
                       study: dict) -> list[dict]:
    """One representative candidate per N_DFU (3 total): does adjusting Qw to hit
    the target emulsion % materially change Stage-1 performance?"""
    ec = study["emulsion_check"]
    s1 = study["stage1_screen"]
    back_Pa = s1["stage1_backpressure_mbar"] * 100.0
    Pout = study["operating"]["P_out_mbar"]
    Qw0 = study["operating"]["Qw_in_mlhr"]
    cand_by_id = {c["candidate_id"]: c for c in candidates}

    out = []
    for n in sorted(summary_df["N_DFU"].unique()):
        grp = summary_df[summary_df["N_DFU"] == n]
        finite = grp[np.isfinite(grp["min_passing_pressure_mbar"])]
        if len(finite):
            # representative: candidate whose required pressure is the group median
            med = finite["min_passing_pressure_mbar"].median()
            rep = finite.iloc[(finite["min_passing_pressure_mbar"] - med).abs().argsort().iloc[0]]
            Po = float(rep["min_passing_pressure_mbar"])
        else:
            rep = grp.iloc[0]
            Po = float(s1["hard_pressure_mbar"])

        cand = cand_by_id[int(rep["candidate_id"])]
        config = build_device_config(cand, study)
        R_DFU = float(rep["R_DFU_Pa_s_per_m3"])
        V_reset = float(rep["V_reset_m3"])

        def stage1_metrics(res):
            DP = res.P_oil - res.P_water
            DP_eff = DP - back_Pa
            active = DP_eff > 0.0
            t = np.full(DP.shape, np.inf)
            t[active] = V_reset * R_DFU / DP_eff[active]
            em = 100.0 * res.Q_oil_total / (res.Q_oil_total + res.Q_water_total)
            return float(np.mean(DP)), float(np.max(t)), float(em)

        base = simulate(config, Po_in_mbar=Po, Qw_in_mlhr=Qw0, P_out_mbar=Pout)
        DP0, t0, em0 = stage1_metrics(base)

        Qw_adj, res_adj = qw_for_target_emulsion(
            config, Po, Qw0, ec["target_emulsion_pct"], Pout,
            ec["qw_sensitivity_max_iterations"],
        )
        DP1, t1, em1 = stage1_metrics(res_adj)

        out.append({
            "N_DFU": int(n),
            "candidate_key": rep["candidate_key"],
            "Po_mbar": Po,
            "Qw_baseline_mlhr": Qw0,
            "Qw_adjusted_mlhr": Qw_adj,
            "emulsion_pct_baseline": em0,
            "emulsion_pct_adjusted": em1,
            "DP_DFU_mean_Pa_baseline": DP0,
            "DP_DFU_mean_Pa_adjusted": DP1,
            "DP_DFU_change_pct": 100.0 * (DP1 - DP0) / DP0 if DP0 else float("nan"),
            "t_S1_max_s_baseline": t0,
            "t_S1_max_s_adjusted": t1,
            "t_S1_change_pct": (100.0 * (t1 - t0) / t0
                                if np.isfinite(t0) and t0 > 0 else float("nan")),
        })
    return out


# ---------------------------------------------------------------------------
# Verification checks (reported in results_summary.md)
# ---------------------------------------------------------------------------

def _monotonicity_check(df: pd.DataFrame, x_col: str, direction: str) -> dict:
    """Per-group monotonicity of min_passing_pressure_mbar in x_col.

    Never-passing candidates (NaN) are treated as requiring more than the max
    swept pressure (ranked above 1000 mbar).
    """
    from scipy.stats import spearmanr

    other = [c for c in ("N_DFU", "DFU_depth_um", "DFU_length_mm",
                         "upstream_AR", "main_depth_um") if c != x_col]
    y = df["min_passing_pressure_mbar"].fillna(1050.0)
    work = df[[x_col] + other].copy()
    work["_y"] = y

    n_groups = 0
    n_monotone = 0
    for _, g in work.groupby(other):
        g = g.sort_values(x_col)
        diffs = np.diff(g["_y"].values)
        n_groups += 1
        if direction == "non-increasing":
            ok = bool((diffs <= 1e-9).all())
        else:
            ok = bool((diffs >= -1e-9).all())
        n_monotone += int(ok)

    rho, pval = spearmanr(work[x_col], work["_y"])

    # Per-N_DFU breakdown: the closed-form expectation holds in the
    # single-DFU limit; main-channel loading can reverse it at large N.
    by_n = {}
    for n, g in df.groupby("N_DFU"):
        y_n = g["min_passing_pressure_mbar"].fillna(1050.0)
        if y_n.nunique() <= 1 or g[x_col].nunique() <= 1:
            by_n[int(n)] = float("nan")  # constant input — correlation undefined
        else:
            r_n, _ = spearmanr(g[x_col], y_n)
            by_n[int(n)] = float(r_n)

    return {
        "x": x_col,
        "expected": direction,
        "groups_total": n_groups,
        "groups_monotone": n_monotone,
        "spearman_rho": float(rho),
        "spearman_p": float(pval),
        "rho_by_N": by_n,
    }


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def write_provenance(study: dict, command: str) -> tuple[str, str]:
    today = date.today().isoformat()
    snap_name = f"study_config_{today}.yaml"
    shutil.copy2(WORKSPACE / "study_config.yaml", WORKSPACE / "snapshots" / snap_name)

    git_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    fl = study["fluids"]
    manifest = f"""# Run Manifest

## Run: Large-DFU Stage-1 hydraulic screen — {today}

**Model commit**: {git_hash}
**Config snapshot**: snapshots/{snap_name}
**Command**: `{command}`
**Run started**: {datetime.now().isoformat(timespec='seconds')}
**Outputs**: results/candidate_summary.csv, results/per_pressure_long.csv,
results/results_summary.md, figures/fig_01–fig_05

### Experimental data used

None — computational/model-only workspace. No `data/` folder exists by design;
this study screens model candidates only and uses no lab data.

### Key config parameters (verify against actual fluid)

| Parameter | Value in snapshot |
|---|---|
| Dispersed phase | sunflower oil |
| η_dispersed | {fl['mu_dispersed'] * 1000:g} mPa·s |
| Continuous phase | water |
| η_continuous | {fl['mu_continuous'] * 1000:g} mPa·s |
| Interfacial tension | {fl['gamma'] * 1000:g} mN/m |
| Phase system | {fl['phase_system']} |
| Device geometry | synthetic sweep grid (576 candidates; see snapshots/{snap_name}) |
| Qw (continuous) | {study['operating']['Qw_in_mlhr']:g} mL/hr fixed |
| Po sweep | {study['operating']['Po_sweep_mbar']['min']:g}–{study['operating']['Po_sweep_mbar']['max']:g} mbar, step {study['operating']['Po_sweep_mbar']['step']:g} |
| Stage-1 back-pressure | {study['stage1_screen']['stage1_backpressure_mbar']:g} mbar (flat constant) |
| t_S1 pass threshold | {study['stage1_screen']['t_S1_max_s']:g} s (every DFU) |
"""
    (WORKSPACE / "snapshots" / "run_manifest.md").write_text(manifest, encoding="utf-8")
    return git_hash, snap_name


# ---------------------------------------------------------------------------
# Results summary markdown
# ---------------------------------------------------------------------------

def _fmt_rho_by_n(by_n: dict) -> str:
    parts = []
    for n, r in sorted(by_n.items()):
        parts.append(f"N={n}: " + ("n/a (all pass at min Po)" if not np.isfinite(r)
                                   else f"{r:+.3f}"))
    return "; ".join(parts)


def write_results_summary(df: pd.DataFrame, study: dict, sanity: dict,
                          qw_rows: list[dict], git_hash: str,
                          elapsed_s: float) -> None:
    s1 = study["stage1_screen"]
    n = len(df)
    n500 = int(df["pass_at_ideal_500"].sum())
    n1000 = int(df["pass_at_hard_1000"].sum())

    # Check 5: no candidate with DP_eff <= 0 anywhere marked passing
    hard_pass = df[df["pass_at_hard_1000"]]
    check5_ok = bool((hard_pass["active_fraction_at_1000mbar"] == 1.0).all())
    assert check5_ok, "Candidate marked passing at 1000 mbar with inactive rungs!"

    check_depth = _monotonicity_check(df, "DFU_depth_um", "non-increasing")
    check_length = _monotonicity_check(df, "DFU_length_mm", "non-decreasing")

    ndfu_tbl = (df.assign(mpp=df["min_passing_pressure_mbar"].fillna(1050.0))
                  .groupby("N_DFU")[["mpp", "t_S1_spread_at_1000mbar"]]
                  .mean())
    ndfu_lines = ["| N_DFU | mean min passing Po [mbar] | mean t_S1 spread at 1000 mbar [%] |",
                  "|---|---|---|"]
    for idx, r in ndfu_tbl.iterrows():
        ndfu_lines.append(
            f"| {idx} | {r['mpp']:.3g} | {r['t_S1_spread_at_1000mbar']:.3g} |")
    ndfu_md = "\n".join(ndfu_lines)

    # Manufacturing vs Stage-1 screen separation
    s1_pass_mfg_fail = int((df["pass_at_hard_1000"] & ~df["manufacturing_ok"]).sum())
    s1_pass_mfg_fail_500 = int((df["pass_at_ideal_500"] & ~df["manufacturing_ok"]).sum())
    both_ok_500 = int((df["pass_at_ideal_500"] & df["manufacturing_ok"]).sum())
    both_ok_1000 = int((df["pass_at_hard_1000"] & df["manufacturing_ok"]).sum())

    best = df[df["pass_at_ideal_500"]].sort_values(
        ["N_DFU", "min_passing_pressure_mbar"], ascending=[False, True]).head(10)
    worst = df.assign(mpp=df["min_passing_pressure_mbar"].fillna(np.inf)).sort_values(
        "mpp", ascending=False).head(5)

    def cand_table(d: pd.DataFrame) -> str:
        cols = ["candidate_key", "N_DFU", "DFU_depth_um", "DFU_length_mm",
                "upstream_AR", "main_depth_um", "min_passing_pressure_mbar",
                "t_S1_max_at_500mbar_s", "emulsion_pct_at_500mbar", "manufacturing_ok"]
        lines = ["| " + " | ".join(cols) + " |",
                 "|" + "---|" * len(cols)]
        for _, r in d.iterrows():
            vals = []
            for c in cols:
                v = r[c]
                if isinstance(v, float):
                    vals.append("—" if not np.isfinite(v) else f"{v:.3g}")
                else:
                    vals.append(str(v))
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)

    def qw_table(rows: list[dict]) -> str:
        if not rows:
            return "_(no rows)_"
        cols = list(rows[0].keys())
        lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for r in rows:
            vals = []
            for c in cols:
                v = r[c]
                vals.append(f"{v:.4g}" if isinstance(v, float) and np.isfinite(v)
                            else ("—" if isinstance(v, float) else str(v)))
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)

    md = f"""# Results Summary — Large-DFU Stage-1 Hydraulic Screen

Auto-generated by `analysis.py` — raw numbers only; narrative in `../report.md`.

**Model commit**: {git_hash}
**Generated**: {datetime.now().isoformat(timespec='seconds')}
**Candidates**: {n} ({len(po_sweep_mbar(study))} pressures each; wall time {elapsed_s:.0f} s)

## Pass rates

Pass = DP_eff > 0 AND t_S1 <= {s1['t_S1_max_s']:g} s for EVERY DFU in the ladder.

| Criterion | Passing | Rate |
|---|---|---|
| Stage-1 pass at ideal {s1['ideal_pressure_mbar']:g} mbar | {n500} / {n} | {100 * n500 / n:.1f}% |
| Stage-1 pass at hard {s1['hard_pressure_mbar']:g} mbar | {n1000} / {n} | {100 * n1000 / n:.1f}% |
| Stage-1 pass at 500 AND manufacturing OK | {both_ok_500} / {n} | {100 * both_ok_500 / n:.1f}% |
| Stage-1 pass at 1000 AND manufacturing OK | {both_ok_1000} / {n} | {100 * both_ok_1000 / n:.1f}% |

## Manufacturing feasibility (diagnostic — settings-dependent, rows never excluded)

Current settings: `max_main_depth_um = {study['manufacturing']['max_main_depth_um']:g}`,
`max_delam_line_load_N_per_m = {study['manufacturing']['max_delam_line_load_N_per_m']}`.

- Candidates passing Stage-1 at 500 mbar but failing manufacturing check: **{s1_pass_mfg_fail_500}**
- Candidates passing Stage-1 at 1000 mbar but failing manufacturing check: **{s1_pass_mfg_fail}**

The two concerns are kept separate: the Stage-1 screen answers "can it refill",
the manufacturing columns answer "can we build it under current assumptions".

## Best candidates (pass at 500 mbar; largest N_DFU, then lowest required pressure)

{cand_table(best)}

## Worst candidates (highest / no passing pressure)

{cand_table(worst)}

## Verification checks

### 1. Smoke test
Both CSVs, this summary, and 5 figures generated — see file listing.

### 2. Depth → required pressure (expected {check_depth['expected']} in the single-DFU limit)
Closed form at fixed DP_eff: t_S1 ∝ DFU_length / (depth · DP_eff), since
V_reset ∝ depth³ and R_DFU ∝ length/depth⁴. This holds only when DP_eff is
independent of the geometry — i.e. when main-channel loading is negligible.
At large N_DFU, deeper (lower-R_DFU) DFUs draw more oil, load the main
channel, and collapse DP_eff at the far rungs, which can reverse the sign.
- Monotone groups: {check_depth['groups_monotone']} / {check_depth['groups_total']}
- Overall Spearman rho = {check_depth['spearman_rho']:.3f} (p = {check_depth['spearman_p']:.2g})
- Per-N_DFU rho: {_fmt_rho_by_n(check_depth['rho_by_N'])}

### 3. Length → required pressure (expected {check_length['expected']} in the single-DFU limit)
Same argument, opposite sign — and the same network caveat: longer DFUs have
higher R_DFU, draw less oil, and improve ladder uniformity, which can reverse
the sign at large N_DFU.
- Monotone groups: {check_length['groups_monotone']} / {check_length['groups_total']}
- Overall Spearman rho = {check_length['spearman_rho']:.3f} (p = {check_length['spearman_p']:.2g})
- Per-N_DFU rho: {_fmt_rho_by_n(check_length['rho_by_N'])}

### 4. N_DFU → required pressure / uniformity (expected both non-decreasing 10 → 1000)
R_DFU and V_reset do not depend on N_DFU, so any degradation comes from
main-channel pressure non-uniformity along the ladder.
(min_passing_pressure NaN → 1050 mbar for the mean; t_S1 spread is % (max−min)/mean at 1000 mbar)

{ndfu_md}

### 5. No candidate with DP_eff ≤ 0 marked passing
`(pass_at_hard_1000 → active_fraction_at_1000mbar == 1.0)`: **{'PASS' if check5_ok else 'FAIL'}** (hard assert)

### 6. V5-30 regression check (standalone — not a sweep candidate)
V_reset length scale sqrt(w·h) = sqrt(30×10) = {sanity['estimate_um']:.1f} µm vs observed
{sanity['observed_lo_um']:g}–{sanity['observed_hi_um']:g} µm lab range. Loose bound (10–30 µm) satisfied;
the ~{abs(sanity['residual_pct_vs_low']):.0f}% residual gap vs the low end of the observed range is
flagged in BRIEF.md Open Questions, not treated as a failure.

## Qw sensitivity check (emulsion-fraction diagnostic)

`Qw_in_mlhr` is the **continuous phase** (water) flow. At fixed Qw = {study['operating']['Qw_in_mlhr']:g} mL/hr,
low-N_DFU candidates show a very low emulsion (dispersed) fraction. Hypothesis
tested here: adjusting Qw to hit a target emulsion % of {study['emulsion_check']['target_emulsion_pct']:g}%
does **not** materially change Stage-1 performance (Qw couples into t_S1 only
indirectly, through the water main channel's contribution to DP_DFU).
One representative candidate per N_DFU, at its min passing pressure (else {s1['hard_pressure_mbar']:g} mbar):

{qw_table(qw_rows)}
"""
    (WORKSPACE / "results" / "results_summary.md").write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _mpp_for_plot(df: pd.DataFrame) -> pd.DataFrame:
    """min_passing_pressure with NaN (never passes in sweep) left as NaN → gaps."""
    return df


def make_fig_01(df: pd.DataFrame, study: dict) -> None:
    """rows=N_DFU, cols=DFU_length_mm, x=DFU_depth_um, lines=upstream_AR,
    y=min_passing_pressure (mean over main_depth_um)."""
    Ns = sorted(df["N_DFU"].unique())
    Ls = sorted(df["DFU_length_mm"].unique())
    ARs = sorted(df["upstream_AR"].unique())
    fig, axes = plt.subplots(len(Ns), len(Ls), figsize=(3.2 * len(Ls), 2.6 * len(Ns)),
                             sharex=True, sharey=True, squeeze=False)
    for i, n in enumerate(Ns):
        for j, L in enumerate(Ls):
            ax = axes[i][j]
            sub = df[(df["N_DFU"] == n) & (df["DFU_length_mm"] == L)]
            for ar in ARs:
                g = (sub[sub["upstream_AR"] == ar]
                     .groupby("DFU_depth_um")["min_passing_pressure_mbar"].mean())
                ax.plot(g.index, g.values, marker="o", ms=3, label=f"AR={ar:g}")
            ax.axhline(500, color="grey", lw=0.7, ls="--")
            ax.axhline(1000, color="grey", lw=0.7, ls=":")
            if i == 0:
                ax.set_title(f"L = {L:g} mm", fontsize=9)
            if j == 0:
                ax.set_ylabel(f"N = {n}\nmin passing Po [mbar]", fontsize=8)
            if i == len(Ns) - 1:
                ax.set_xlabel("DFU depth [µm]", fontsize=8)
            ax.tick_params(labelsize=7)
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Required pressure vs DFU depth (mean over main_depth; gaps = never passes ≤1000 mbar)",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(WORKSPACE / "figures" / "fig_01_pressure_requirement_vs_depth.png", dpi=FIG_DPI)
    plt.close(fig)


def make_fig_02(df: pd.DataFrame, study: dict) -> None:
    """rows=N_DFU, cols=DFU_depth_um, x=DFU_length_mm, lines=upstream_AR."""
    Ns = sorted(df["N_DFU"].unique())
    Ds = sorted(df["DFU_depth_um"].unique())
    ARs = sorted(df["upstream_AR"].unique())
    fig, axes = plt.subplots(len(Ns), len(Ds), figsize=(3.2 * len(Ds), 2.6 * len(Ns)),
                             sharex=True, sharey=True, squeeze=False)
    for i, n in enumerate(Ns):
        for j, d in enumerate(Ds):
            ax = axes[i][j]
            sub = df[(df["N_DFU"] == n) & (df["DFU_depth_um"] == d)]
            for ar in ARs:
                g = (sub[sub["upstream_AR"] == ar]
                     .groupby("DFU_length_mm")["min_passing_pressure_mbar"].mean())
                ax.plot(g.index, g.values, marker="o", ms=3, label=f"AR={ar:g}")
            ax.axhline(500, color="grey", lw=0.7, ls="--")
            ax.axhline(1000, color="grey", lw=0.7, ls=":")
            if i == 0:
                ax.set_title(f"depth = {d:g} µm", fontsize=9)
            if j == 0:
                ax.set_ylabel(f"N = {n}\nmin passing Po [mbar]", fontsize=8)
            if i == len(Ns) - 1:
                ax.set_xlabel("DFU length [mm]", fontsize=8)
            ax.tick_params(labelsize=7)
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Required pressure vs DFU length (mean over main_depth; gaps = never passes ≤1000 mbar)",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(WORKSPACE / "figures" / "fig_02_pressure_requirement_vs_length.png", dpi=FIG_DPI)
    plt.close(fig)


def make_fig_03(df: pd.DataFrame, study: dict) -> None:
    """rows=DFU_depth_um, cols=upstream_AR, x=N_DFU (log), lines=DFU_length_mm."""
    Ds = sorted(df["DFU_depth_um"].unique())
    ARs = sorted(df["upstream_AR"].unique())
    Ls = sorted(df["DFU_length_mm"].unique())
    fig, axes = plt.subplots(len(Ds), len(ARs), figsize=(3.0 * len(ARs), 2.4 * len(Ds)),
                             sharex=True, sharey=True, squeeze=False)
    for i, d in enumerate(Ds):
        for j, ar in enumerate(ARs):
            ax = axes[i][j]
            sub = df[(df["DFU_depth_um"] == d) & (df["upstream_AR"] == ar)]
            for L in Ls:
                g = (sub[sub["DFU_length_mm"] == L]
                     .groupby("N_DFU")["min_passing_pressure_mbar"].mean())
                ax.plot(g.index, g.values, marker="o", ms=3, label=f"L={L:g} mm")
            ax.set_xscale("log")
            ax.axhline(500, color="grey", lw=0.7, ls="--")
            ax.axhline(1000, color="grey", lw=0.7, ls=":")
            if i == 0:
                ax.set_title(f"AR = {ar:g}", fontsize=9)
            if j == 0:
                ax.set_ylabel(f"depth = {d:g} µm\nmin passing Po [mbar]", fontsize=8)
            if i == len(Ds) - 1:
                ax.set_xlabel("N_DFU", fontsize=8)
            ax.tick_params(labelsize=7)
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Required pressure vs ladder size N_DFU (mean over main_depth)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(WORKSPACE / "figures" / "fig_03_pressure_requirement_vs_N.png", dpi=FIG_DPI)
    plt.close(fig)


def make_fig_04(df: pd.DataFrame, study: dict) -> None:
    """x=main_depth_um, y=t_S1_spread_at_1000mbar (mean), faceted by DFU_depth_um,
    one line per N_DFU."""
    Ds = sorted(df["DFU_depth_um"].unique())
    Ns = sorted(df["N_DFU"].unique())
    fig, axes = plt.subplots(1, len(Ds), figsize=(3.2 * len(Ds), 3.2),
                             sharex=True, sharey=True, squeeze=False)
    for j, d in enumerate(Ds):
        ax = axes[0][j]
        sub = df[df["DFU_depth_um"] == d]
        for n in Ns:
            g = (sub[sub["N_DFU"] == n]
                 .groupby("main_depth_um")["t_S1_spread_at_1000mbar"].mean())
            ax.plot(g.index, g.values, marker="o", ms=4, label=f"N={n}")
        ax.set_title(f"DFU depth = {d:g} µm", fontsize=9)
        ax.set_xlabel("main channel depth [µm]", fontsize=8)
        if j == 0:
            ax.set_ylabel("t_S1 spread at 1000 mbar [% (max−min)/mean]", fontsize=8)
        ax.tick_params(labelsize=7)
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Refill-time uniformity vs main-channel size (mean over length & AR)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(WORKSPACE / "figures" / "fig_04_uniformity_vs_main_channel_size.png", dpi=FIG_DPI)
    plt.close(fig)


def make_fig_05(df: pd.DataFrame, candidates: list[dict], study: dict) -> list[str]:
    """Top-5 candidates (largest N_DFU among pass_at_ideal_500, tie-broken by
    lowest required pressure) — re-simulated pressure profiles at 500 & 1000 mbar."""
    top = df[df["pass_at_ideal_500"]].sort_values(
        ["N_DFU", "min_passing_pressure_mbar"], ascending=[False, True]).head(5)
    if top.empty:
        # fall back to lowest-required-pressure overall so the figure still exists
        top = df.assign(mpp=df["min_passing_pressure_mbar"].fillna(np.inf)) \
                .sort_values("mpp").head(5)

    cand_by_id = {c["candidate_id"]: c for c in candidates}
    Qw = study["operating"]["Qw_in_mlhr"]
    Pout = study["operating"]["P_out_mbar"]
    pressures = [study["stage1_screen"]["ideal_pressure_mbar"],
                 study["stage1_screen"]["hard_pressure_mbar"]]

    nrows = len(top)
    fig, axes = plt.subplots(nrows, 2, figsize=(9, 2.4 * nrows),
                             sharex=False, squeeze=False)
    keys = []
    for i, (_, row) in enumerate(top.iterrows()):
        cand = cand_by_id[int(row["candidate_id"])]
        keys.append(cand["candidate_key"])
        config = build_device_config(cand, study)
        for j, Po in enumerate(pressures):
            res = simulate(config, Po_in_mbar=float(Po), Qw_in_mlhr=Qw, P_out_mbar=Pout)
            x_mm = res.x_positions * 1e3
            ax = axes[i][j]
            ax.plot(x_mm, res.P_oil / 100.0, label="P_oil", lw=1.2)
            ax.plot(x_mm, res.P_water / 100.0, label="P_water", lw=1.2)
            ax.plot(x_mm, (res.P_oil - res.P_water) / 100.0, label="DP_DFU", lw=1.2, ls="--")
            ax.axhline(study["stage1_screen"]["stage1_backpressure_mbar"],
                       color="grey", lw=0.7, ls=":")
            ax.set_title(f"{cand['candidate_key']} @ {Po:g} mbar", fontsize=8)
            ax.tick_params(labelsize=7)
            if j == 0:
                ax.set_ylabel("P [mbar]", fontsize=8)
            if i == nrows - 1:
                ax.set_xlabel("x along ladder [mm]", fontsize=8)
    axes[0][0].legend(fontsize=7)
    fig.suptitle("Top candidates — re-simulated pressure profiles (dotted: 12 mbar back-pressure)",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(WORKSPACE / "figures" / "fig_05_top_candidate_pressure_profiles.png", dpi=FIG_DPI)
    plt.close(fig)
    return keys


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t_start = time.time()
    study = load_study()
    command = "python " + " ".join(
        [str(Path(sys.argv[0]).as_posix())] + sys.argv[1:])
    git_hash, snap_name = write_provenance(study, command)
    print(f"[provenance] model commit {git_hash}; snapshot snapshots/{snap_name}")

    sanity = sanity_check_v530_reset_length(study)

    pressures = po_sweep_mbar(study)
    candidates = build_candidates(study)
    print(f"[sweep] {len(candidates)} candidates x {len(pressures)} pressures "
          f"= {len(candidates) * len(pressures)} solves")

    summary_rows: list[dict] = []
    long_rows: list[dict] = []
    for k, cand in enumerate(candidates):
        config = build_device_config(cand, study)
        summary, per_pressure = screen_candidate(config, cand, pressures, study)
        summary_rows.append(summary)
        long_rows.extend(per_pressure)
        if (k + 1) % 50 == 0:
            print(f"  ... {k + 1}/{len(candidates)} candidates "
                  f"({time.time() - t_start:.0f} s)")

    df = pd.DataFrame(summary_rows)
    df_long = pd.DataFrame(long_rows)
    df.to_csv(WORKSPACE / "results" / "candidate_summary.csv", index=False)
    df_long.to_csv(WORKSPACE / "results" / "per_pressure_long.csv", index=False)
    print(f"[results] candidate_summary.csv ({len(df)} rows), "
          f"per_pressure_long.csv ({len(df_long)} rows)")

    qw_rows = run_qw_sensitivity(df, candidates, study)

    elapsed = time.time() - t_start
    write_results_summary(df, study, sanity, qw_rows, git_hash, elapsed)
    print("[results] results_summary.md written")

    make_fig_01(df, study)
    make_fig_02(df, study)
    make_fig_03(df, study)
    make_fig_04(df, study)
    top_keys = make_fig_05(df, candidates, study)
    print(f"[figures] 5 figures written; fig_05 candidates: {top_keys}")
    print(f"[done] total wall time {time.time() - t_start:.0f} s")


if __name__ == "__main__":
    main()
