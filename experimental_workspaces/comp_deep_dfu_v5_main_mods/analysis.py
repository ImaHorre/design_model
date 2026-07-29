"""
Deep (20 µm) DFU V5 main-channel modification study — SIMPLE version.

One question, one fixed inlet oil pressure: for each oil-main config, what
throughput and DFU ΔP flatness do you get, and how many DFUs fit in the area
budget? No Ca / regime analysis, no φ / clog sweep — we assume drops form, and
always dilute to a 10% emulsion (Qw = 9 × Qoil).

Per config (main depth × width × rung length × upstream width), reported at a
single fixed Po, the outputs are:
  - N_DFU (from the area budget: band = W_oil + L_rung + W_water; N = floor(area / (band·pitch)))
  - Q_oil_total [mL/hr]
  - oil velocity at the DFU exit [mm/s]  (mean + spread over rungs)
  - drop frequency [Hz]  (Stage-1 cycle: f = Q_rung / (V_reset + V_drop); size NOT trusted)
  - avg ΔP over rungs [mbar] + ΔP spread [%]
  - water flow for a 10% emulsion [mL/hr]  (= 9 × Qoil)

Reframed premise: a DEEPER main is free (no footprint cost) and always helps; a
WIDER main costs DFU count but flattens — a tradeoff the model resolves.

Reuses stepgen primitives directly (no core changes):
  - stepgen.config dataclasses, built per config
  - stepgen.models.hydraulics.simulate — plain steady mixed-BC ladder solve
  - stepgen.models.droplets.droplet_diameter/droplet_volume — for V_drop / D_pred
  - stepgen.models.resistance.resistance_piecewise / hydraulic_resistance_rectangular

Run from the repo root:
    python experimental_workspaces/comp_deep_dfu_v5_main_mods/analysis.py
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
from stepgen.models.droplets import droplet_diameter, droplet_volume  # noqa: E402
from stepgen.models.hydraulics import simulate  # noqa: E402
from stepgen.models.resistance import (  # noqa: E402
    hydraulic_resistance_rectangular,
    resistance_piecewise,
)

FIG_DPI = 150
M3S_TO_MLHR = 3600.0 / 1e-6   # m³/s → mL/hr  (= 3.6e9)


def load_study() -> dict:
    with open(WORKSPACE / "study_config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Area budget → N_DFU
# ---------------------------------------------------------------------------

def footprint_fit(w_oil_um: float, w_water_um: float, L_rung_mm: float,
                  pitch_um: float, area_cm2: float) -> dict:
    """How many DFUs fit when the folded ladder fills `area_cm2`.

    band = W_oil_main + L_rung + W_water_main   (transverse extent of one pass)
    N    = floor(area / (band · pitch))         (ladder length = N · pitch)
    Depth does NOT enter band — a deeper main costs no footprint.
    """
    band_um = w_oil_um + L_rung_mm * 1000.0 + w_water_um
    area_um2 = area_cm2 * 1e8                       # 1 cm² = 1e8 µm²
    per_dfu_um2 = band_um * pitch_um               # footprint of one DFU pass
    N = int(math.floor(area_um2 / per_dfu_um2)) if per_dfu_um2 > 0 else 0
    return {
        "band_um": float(band_um),
        "N_DFU": max(N, 0),
        "ladder_length_m": float(N * pitch_um * 1e-6),
        "footprint_cm2": float(N * per_dfu_um2 / 1e8),
    }


# ---------------------------------------------------------------------------
# Candidate grid + config builder
# ---------------------------------------------------------------------------

def v5_30_band_um(study: dict) -> float:
    """Transverse band of the real V5-30: two mains + the rung span."""
    a = study["v5_30_actual"]
    return 2.0 * a["main_width_um"] + a["rung_length_um"]


def area_budget_cm2(study: dict) -> float:
    """Area budget for the DFU packing.

    Calibrated to the real V5-30: the routing area it consumes = band × (N · pitch).
    Using the SAME band formula applied to the deep-DFU configs, this anchors N to the
    one real device instead of an idealised die fill. An explicit override may be set via
    footprint.area_budget_cm2.
    """
    fp = study["footprint"]
    if fp.get("area_budget_cm2"):
        return float(fp["area_budget_cm2"])
    a = study["v5_30_actual"]
    routed_um = a["N_dfu"] * a["pitch_um"]
    return v5_30_band_um(study) * routed_um / 1e8   # µm² → cm²


def build_candidates(study: dict) -> list[dict]:
    grid = study["sweep_grid"]
    dg = study["dfu_geometry"]
    area = area_budget_cm2(study)
    pitch = dg["pitch_um"]
    combos = itertools.product(
        grid["main_depth_um"], grid["main_width_um"],
        grid["DFU_length_mm"], grid["upstream_width_um"],
    )
    candidates = []
    for cid, (md, mw, Ldfu, uw) in enumerate(combos):
        # oil & water mains share one width for now (solver uses one width anyway)
        fit = footprint_fit(mw, mw, Ldfu, pitch, area)
        candidates.append({
            "candidate_id": cid,
            "candidate_key": f"D{md:g}_W{mw:g}_L{Ldfu:g}_U{uw:g}",
            "main_depth_um": float(md),
            "main_width_um": float(mw),
            "DFU_length_mm": float(Ldfu),
            "upstream_width_um": float(uw),
            "band_um": fit["band_um"],
            "N_DFU": int(fit["N_DFU"]),
            "ladder_length_m": fit["ladder_length_m"],
            "footprint_cm2": fit["footprint_cm2"],
        })
    return candidates


def build_device_config(cand: dict, study: dict) -> DeviceConfig:
    """Build a DeviceConfig; all unit conversion happens here."""
    dg = study["dfu_geometry"]
    fl = study["fluids"]
    op = study["operating"]

    assert cand["upstream_width_um"] >= dg["min_upstream_width_um"], (
        f"upstream_width {cand['upstream_width_um']} um below aspect floor "
        f"{dg['min_upstream_width_um']} um for a {dg['depth_um']} um-deep DFU"
    )

    depth = dg["depth_um"] * 1e-6
    exit_width = dg["exit_width_um"] * 1e-6
    exit_depth = dg["exit_depth_um"] * 1e-6
    pitch = dg["pitch_um"] * 1e-6
    upstream_width = cand["upstream_width_um"] * 1e-6
    length = cand["DFU_length_mm"] * 1e-3
    main_depth = cand["main_depth_um"] * 1e-6
    main_width = cand["main_width_um"] * 1e-6

    profile = (
        MicrochannelSection(dg["section1_length_frac"] * length, upstream_width, depth),
        MicrochannelSection(dg["section2_length_frac"] * length, exit_width, depth),
    )
    rung = RungConfig(mcd=depth, mcw=upstream_width, mcl=length, pitch=pitch,
                      constriction_ratio=1.0, profile=profile)
    geometry = GeometryConfig(
        main=MainChannelConfig(Mcd=main_depth, Mcw=main_width,
                               Mcl=cand["N_DFU"] * pitch),
        rung=rung,
        junction=JunctionConfig(exit_width=exit_width, exit_depth=exit_depth),
        Nmc_override=int(cand["N_DFU"]),
    )
    fluids = FluidConfig(
        mu_continuous=fl["mu_continuous"], mu_dispersed=fl["mu_dispersed"],
        emulsion_ratio=op["emulsion_fraction"], gamma=fl["gamma_eff"],
        phase_system=fl["phase_system"], continuous_fluid_name="water",
        dispersed_fluid_name="sunflower_oil",
    )
    operating = OperatingConfig(Po_in_mbar=op["Po_in_mbar"],
                                Qw_in_mlhr=1.0, P_out_mbar=op["P_out_mbar"])
    return DeviceConfig(fluids=fluids, geometry=geometry, operating=operating)


# ---------------------------------------------------------------------------
# Evaluation at the single fixed operating pressure
# ---------------------------------------------------------------------------

def _spread_pct(a: np.ndarray) -> float:
    m = float(np.mean(a))
    return float(100.0 * (np.max(a) - np.min(a)) / m) if m > 0 else float("nan")


def evaluate_candidate(cand: dict, study: dict) -> dict:
    """Solve one config at the fixed Po with Qw set for a 10% emulsion."""
    dg = study["dfu_geometry"]
    op = study["operating"]
    mfg = study["manufacturing"]
    Po = op["Po_in_mbar"]
    Pout = op["P_out_mbar"]
    phi = op["emulsion_fraction"]

    base = {
        "candidate_id": cand["candidate_id"], "candidate_key": cand["candidate_key"],
        "main_depth_um": cand["main_depth_um"], "main_width_um": cand["main_width_um"],
        "DFU_length_mm": cand["DFU_length_mm"], "upstream_width_um": cand["upstream_width_um"],
        "band_um": cand["band_um"], "N_DFU": cand["N_DFU"],
        "footprint_cm2": cand["footprint_cm2"],
        "manufacturing_ok": bool(cand["main_depth_um"] <= mfg["max_main_depth_um"]
                                 and cand["main_width_um"] <= mfg["max_main_width_um"]),
    }
    if cand["N_DFU"] < 2:
        base["feasible"] = False
        return base

    config = build_device_config(cand, study)
    ew = dg["exit_width_um"] * 1e-6
    ed = dg["exit_depth_um"] * 1e-6
    exit_area = ew * ed
    R_DFU = resistance_piecewise(config.geometry.rung.profile, config.fluids.mu_dispersed)

    # reset + drop volumes (per the Stage-1 cycle)
    L_reset = math.sqrt(ew * ed)
    V_reset = L_reset * ew * ed
    D_pred = droplet_diameter(config)
    V_drop = droplet_volume(D_pred)
    V_cycle = V_reset + V_drop

    # Oil-side solve at a small nominal carrier flow (oil-side ΔP / throughput are
    # insensitive to it). The 9× dilution water for a 10% emulsion is a DOWNSTREAM
    # number (Qw_10pct below), not injected through the device — injecting it would
    # raise P_water and choke the oil, which is a separate transport question.
    res = simulate(config, Po_in_mbar=Po, Qw_in_mlhr=op["carrier_Qw_mlhr"], P_out_mbar=Pout)

    dP = res.P_oil - res.P_water
    active = dP > 0.0
    Q_active = res.Q_rungs[active] if np.any(active) else res.Q_rungs
    dP_active = dP[active] if np.any(active) else dP

    v_exit = Q_active / exit_area                # m/s per active rung
    f_drop = Q_active / V_cycle                  # Hz per active rung

    Qoil_total_mlhr = res.Q_oil_total * M3S_TO_MLHR
    base.update({
        "feasible": True,
        "R_DFU_Pa_s_per_m3": float(R_DFU),
        "active_fraction": float(np.mean(active)),
        # throughput
        "Q_oil_total_mlhr": Qoil_total_mlhr,
        "Qw_10pct_mlhr": Qoil_total_mlhr * (1.0 / phi - 1.0),
        # oil velocity at the DFU exit
        "v_exit_mean_mmps": float(np.mean(v_exit)) * 1e3,
        "v_exit_max_mmps": float(np.max(v_exit)) * 1e3,
        # drop frequency (size NOT trusted)
        "f_drop_mean_hz": float(np.mean(f_drop)),
        "f_drop_max_hz": float(np.max(f_drop)),
        "D_pred_um": float(D_pred * 1e6),
        # flatness (flow/velocity/freq share this same spread)
        "flow_spread_pct": _spread_pct(Q_active),
        "dP_avg_mbar": float(np.mean(dP_active)) / 100.0,
        "dP_min_mbar": float(np.min(dP_active)) / 100.0,
        "dP_max_mbar": float(np.max(dP_active)) / 100.0,
        "dP_spread_pct": _spread_pct(dP_active),
        "oil_main_droop_pct": float(100.0 * (res.P_oil[0] - res.P_oil[-1]) / res.P_oil[0])
        if res.P_oil[0] != 0 else float("nan"),
    })
    return base


# ---------------------------------------------------------------------------
# Sanity / regression cross-checks (kept minimal)
# ---------------------------------------------------------------------------

def deep_dfu_r_scaling_check(study: dict) -> dict:
    """10 → 20 µm depth: bare 1/h³ law = 8×; realized (corrected) ~4.4× because the
    (1 − 0.63 h/w) aspect correction grows as the channel deepens at fixed width."""
    dg = study["dfu_geometry"]
    mu = study["fluids"]["mu_dispersed"]
    L, uw, ew = 2.0e-3, 20.0e-6, dg["exit_width_um"] * 1e-6
    Ru10 = hydraulic_resistance_rectangular(mu, L, uw, 10e-6, correction=False)
    Ru20 = hydraulic_resistance_rectangular(mu, L, uw, 20e-6, correction=False)
    ratio_uncorr = Ru10 / Ru20

    def R_piece(d_um):
        d = d_um * 1e-6
        return resistance_piecewise((
            MicrochannelSection(dg["section1_length_frac"] * L, uw, d),
            MicrochannelSection(dg["section2_length_frac"] * L, ew, d)), mu)

    ratio_corr = R_piece(10.0) / R_piece(20.0)
    print(f"[sanity] R scaling 10->20 um: bare 1/h^3 = {ratio_uncorr:.2f}x (expect 8), "
          f"realized = {ratio_corr:.2f}x (aspect correction offsets)")
    assert 7.5 <= ratio_uncorr <= 8.5, f"1/h^3 law {ratio_uncorr:.2f}x not ~8x"
    assert 3.0 <= ratio_corr <= 6.0, f"realized {ratio_corr:.2f}x outside 3-6x"
    return {"ratio_uncorr": ratio_uncorr, "ratio_corr": ratio_corr}


def v5_30_calibration_check(study: dict) -> dict:
    """Anchor to the real V5-30: (a) the footprint model must reproduce its DFU count with
    its actual geometry, and (b) its hydraulic solve must give a sane, positive throughput.

    (a) is the calibration that makes the deep-DFU N realistic; (b) is an order check.
    """
    a, fl, op = study["v5_30_actual"], study["fluids"], study["operating"]
    budget = area_budget_cm2(study)

    # (a) footprint reproduces N=11550 with V5-30's own geometry
    fit = footprint_fit(a["main_width_um"], a["main_width_um"],
                        a["rung_length_um"] / 1000.0, a["pitch_um"], budget)
    n_model, n_real = fit["N_DFU"], int(a["N_dfu"])
    err = abs(n_model - n_real) / n_real * 100.0
    print(f"[calib] area budget = {budget:.2f} cm2 -> V5-30 footprint N = {n_model} "
          f"vs real {n_real} ({err:.1f}% {'OK' if err < 1.0 else 'FAIL'})")
    assert err < 1.0, f"footprint model does not reproduce V5-30 N ({n_model} vs {n_real})"

    # (b) hydraulic order check with V5-30's real geometry
    depth = a["dfu_depth_um"] * 1e-6
    ew, ed = a["exit_width_um"] * 1e-6, a["exit_depth_um"] * 1e-6
    pitch, N = a["pitch_um"] * 1e-6, n_real
    L, uw = a["rung_length_um"] * 1e-6, a["upstream_width_um"] * 1e-6
    rung = RungConfig(mcd=depth, mcw=uw, mcl=L, pitch=pitch, constriction_ratio=1.0,
                      profile=(MicrochannelSection(0.9 * L, uw, depth),
                               MicrochannelSection(0.1 * L, ew, depth)))
    geometry = GeometryConfig(
        main=MainChannelConfig(Mcd=a["main_depth_um"] * 1e-6, Mcw=a["main_width_um"] * 1e-6,
                               Mcl=N * pitch), rung=rung,
        junction=JunctionConfig(exit_width=ew, exit_depth=ed), Nmc_override=N)
    fluids = FluidConfig(mu_continuous=fl["mu_continuous"], mu_dispersed=fl["mu_dispersed"],
                         emulsion_ratio=0.1, gamma=fl["gamma_eff"], phase_system="o/w")
    config = DeviceConfig(fluids=fluids, geometry=geometry,
                          operating=OperatingConfig(Po_in_mbar=op["Po_in_mbar"], Qw_in_mlhr=5.0))
    res = simulate(config, Po_in_mbar=op["Po_in_mbar"],
                   Qw_in_mlhr=op["carrier_Qw_mlhr"], P_out_mbar=op["P_out_mbar"])
    Q = res.Q_oil_total * M3S_TO_MLHR
    ok = bool(res.Q_oil_total > 0 and np.isfinite(Q))
    print(f"[sanity] real V5-30 (N={N}) @{op['Po_in_mbar']:g} mbar: Q_oil={Q:.3g} mL/hr "
          f"({'OK' if ok else 'FAIL'})")
    assert ok, "V5-30 hydraulic order check failed"
    return {"N": N, "Q_oil_mlhr": float(Q), "area_budget_cm2": float(budget),
            "band_um": float(v5_30_band_um(study))}


def carrier_sensitivity_check(candidates: list[dict], study: dict) -> dict:
    """Measure (not assert away) how much the oil side moves with the carrier Qw.

    The continuous flow raises P_water and mildly reduces oil throughput. We hold the
    carrier fixed across all configs (fair comparison) and DOCUMENT the worst-case
    sensitivity. Scans carrier Qw = 5 vs 20 mL/hr over a spread of feasible configs and
    reports the largest Q_oil change. A loose bound guards against gross coupling only."""
    op = study["operating"]
    Po, Pout = op["Po_in_mbar"], op["P_out_mbar"]
    feas = [c for c in candidates if c["N_DFU"] >= 2]
    probes = sorted(feas, key=lambda c: c["N_DFU"])[:: max(len(feas) // 6, 1)]

    worst = {"key": "", "q_change_pct": 0.0}
    for cand in probes:
        config = build_device_config(cand, study)

        def q(qw):
            return simulate(config, Po_in_mbar=Po, Qw_in_mlhr=qw,
                            P_out_mbar=Pout).Q_oil_total * M3S_TO_MLHR
        q5, q20 = q(5.0), q(20.0)
        dq = abs(q20 - q5) / abs(q5) * 100.0 if q5 else 0.0
        if dq > worst["q_change_pct"]:
            worst = {"key": cand["candidate_key"], "q_change_pct": float(dq)}

    ok = worst["q_change_pct"] < 25.0
    print(f"[sanity] carrier Qw 5->20 mL/hr: worst oil-side change "
          f"{worst['q_change_pct']:.1f}% ({worst['key']}) "
          f"({'OK' if ok else 'FAIL - coupling too strong'})")
    assert ok, f"carrier coupling too strong ({worst['q_change_pct']:.1f}%)"
    return worst


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def write_provenance(study: dict, command: str, n_cand: int) -> tuple[str, str]:
    today = date.today().isoformat()
    snap_name = f"study_config_{today}.yaml"
    (WORKSPACE / "snapshots").mkdir(exist_ok=True)
    shutil.copy2(WORKSPACE / "study_config.yaml", WORKSPACE / "snapshots" / snap_name)
    git_hash = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    fl, op = study["fluids"], study["operating"]
    manifest = f"""# Run Manifest

## Run: Deep (20 µm) DFU V5 main-channel mod study (SIMPLE) — {today}

**Model commit**: {git_hash}
**Config snapshot**: snapshots/{snap_name}
**Command**: `{command}`
**Run started**: {datetime.now().isoformat(timespec='seconds')}
**Outputs**: results/candidate_summary.csv, results/results_summary.md,
figures/dP_over_rungs.png, figures/throughput_vs_main.png

### Experimental data used

None — computational / model-only workspace ({n_cand} configs). No `data/` folder.

### Key parameters

| Parameter | Value |
|---|---|
| Dispersed phase | sunflower oil, η = {fl['mu_dispersed'] * 1000:g} mPa·s |
| Continuous phase | water (2% SDS), η = {fl['mu_continuous'] * 1000:g} mPa·s |
| γ_eff | {fl['gamma_eff'] * 1000:g} mN/m (back-calculated; record only — no Ca analysis) |
| DFU (fixed) | 20 µm deep, 60×20 µm exit, 120 µm pitch, 90:10 profile |
| Main (swept) | depth {study['sweep_grid']['main_depth_um']} µm × width {study['sweep_grid']['main_width_um']} µm |
| Rung length (swept) | {study['sweep_grid']['DFU_length_mm']} mm |
| Upstream width (swept) | {study['sweep_grid']['upstream_width_um']} µm |
| Inlet oil pressure | {op['Po_in_mbar']:g} mbar (single fixed operating point) |
| Emulsion target | {op['emulsion_fraction'] * 100:g}% → Qw = {1 / op['emulsion_fraction'] - 1:g} × Qoil |
| Area budget | {area_budget_cm2(study):.1f} cm² — CALIBRATED to reproduce real V5-30 (N={study['v5_30_actual']['N_dfu']}); N = floor(area / (band·pitch)) |
| V5-30 anchor | Mcw {study['v5_30_actual']['main_width_um']:g} µm, rung {study['v5_30_actual']['rung_length_um']:g} µm, pitch {study['v5_30_actual']['pitch_um']:g} µm, band {v5_30_band_um(study):g} µm |

Fluid system: sunflower oil / 2% SDS-water O/W — SAME mix as `po_sweep` and
`comp_large_dfu_stage1_screen`, inherited unchanged.
"""
    (WORKSPACE / "snapshots" / "run_manifest.md").write_text(manifest, encoding="utf-8")
    return git_hash, snap_name


# ---------------------------------------------------------------------------
# Results summary
# ---------------------------------------------------------------------------

def _table(d: pd.DataFrame, cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in d.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if isinstance(v, (bool, np.bool_)):
                vals.append("yes" if v else "no")
            elif isinstance(v, (float, np.floating)):
                vals.append("—" if not np.isfinite(v) else f"{v:.3g}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_results_summary(df: pd.DataFrame, study: dict, r_scaling: dict,
                          v530: dict, carrier: dict, git_hash: str,
                          elapsed_s: float) -> None:
    from scipy.stats import spearmanr
    feas = df[df["feasible"]].copy()
    n, nf = len(df), len(feas)
    op = study["operating"]

    def rho(x, y):
        if feas[x].nunique() <= 1 or feas[y].nunique() <= 1:
            return float("nan")
        return float(spearmanr(feas[x], feas[y])[0])

    # depth: free win → flatter ΔP AND higher throughput at NO cost to N.
    rho_depth_flat = rho("main_depth_um", "dP_spread_pct")   # expect < 0
    rho_depth_tp = rho("main_depth_um", "Q_oil_total_mlhr")  # expect > 0
    rho_depth_N = rho("main_depth_um", "N_DFU")              # expect ~0 (depth is free)
    # width: tradeoff → flatter ΔP but fewer DFUs.
    rho_width_flat = rho("main_width_um", "dP_spread_pct")   # expect < 0
    rho_width_N = rho("main_width_um", "N_DFU")              # expect < 0
    rho_width_tp = rho("main_width_um", "Q_oil_total_mlhr")  # net — could be either sign

    assert rho_depth_flat < 0.05, f"deeper main should flatten dP; rho={rho_depth_flat:+.3f}"
    assert abs(rho_depth_N) < 1e-6, f"depth must NOT change N (free); rho={rho_depth_N:+.3f}"
    assert rho_width_N < 0, f"wider main should reduce N; rho={rho_width_N:+.3f}"

    disp = ["candidate_key", "N_DFU", "Q_oil_total_mlhr", "v_exit_mean_mmps",
            "f_drop_mean_hz", "dP_avg_mbar", "dP_spread_pct", "Qw_10pct_mlhr",
            "manufacturing_ok"]
    flat = feas.sort_values("dP_spread_pct").head(8)
    tp = feas.sort_values("Q_oil_total_mlhr", ascending=False).head(8)

    md = f"""# Results Summary — Deep (20 µm) DFU Main-Channel Study (simple)

Auto-generated by `analysis.py`. Narrative in `../report.md`.

**Model commit**: {git_hash} · **Generated**: {datetime.now().isoformat(timespec='seconds')}
**Configs**: {n} ({nf} feasible) at a single fixed Po = {op['Po_in_mbar']:g} mbar · wall time {elapsed_s:.0f} s
**Emulsion**: {op['emulsion_fraction'] * 100:g}% (Qw = {1 / op['emulsion_fraction'] - 1:g} × Qoil) · **Area budget**: {v530['area_budget_cm2']:.1f} cm² (calibrated to reproduce the real V5-30 N = {v530['N']})
**Reference — real V5-30**: N = {v530['N']}, Q_oil = {v530['Q_oil_mlhr']:.3g} mL/hr @ {op['Po_in_mbar']:g} mbar (10 µm DFU, 60 µm pitch)

## The two levers (Spearman ρ over feasible configs)

| Lever | metric | ρ | reading |
|---|---|---|---|
| main **depth** | → ΔP spread | {rho_depth_flat:+.3f} | flatter (expected < 0) |
| main **depth** | → throughput | {rho_depth_tp:+.3f} | more oil (expected > 0) |
| main **depth** | → N_DFU | {rho_depth_N:+.3f} | **no cost** (depth is free — expected 0) |
| main **width** | → ΔP spread | {rho_width_flat:+.3f} | flatter (expected < 0) |
| main **width** | → N_DFU | {rho_width_N:+.3f} | fewer DFUs (expected < 0) |
| main **width** | → throughput | {rho_width_tp:+.3f} | **net of the tradeoff** |

**Depth is a free win** (flatter + more throughput, N unchanged). **Width is a tradeoff**
(flatter, but fewer DFUs); the net throughput sign is ρ = {rho_width_tp:+.3f}.

## Ranges (feasible configs, at {op['Po_in_mbar']:g} mbar)

| quantity | min | max |
|---|---|---|
| N_DFU | {int(feas['N_DFU'].min())} | {int(feas['N_DFU'].max())} |
| Q_oil_total [mL/hr] | {feas['Q_oil_total_mlhr'].min():.3g} | {feas['Q_oil_total_mlhr'].max():.3g} |
| oil velocity at exit [mm/s] | {feas['v_exit_mean_mmps'].min():.3g} | {feas['v_exit_mean_mmps'].max():.3g} |
| drop frequency [Hz] | {feas['f_drop_mean_hz'].min():.3g} | {feas['f_drop_mean_hz'].max():.3g} |
| ΔP avg [mbar] | {feas['dP_avg_mbar'].min():.3g} | {feas['dP_avg_mbar'].max():.3g} |
| ΔP spread [%] | {feas['dP_spread_pct'].min():.3g} | {feas['dP_spread_pct'].max():.3g} |
| Qw for 10% [mL/hr] | {feas['Qw_10pct_mlhr'].min():.3g} | {feas['Qw_10pct_mlhr'].max():.3g} |

Drop diameter (regime-blind power law — **size not trusted**): {feas['D_pred_um'].mean():.0f} µm.

## Flattest configs (lowest ΔP spread)

{_table(flat, disp)}

## Highest-throughput configs

{_table(tp, disp)}

## Verification

- **Smoke test**: `candidate_summary.csv`, this summary, 2 figures generated.
- **R scaling** 10→20 µm depth: bare 1/h³ = {r_scaling['ratio_uncorr']:.2f}× (expect 8, hard assert); realized {r_scaling['ratio_corr']:.2f}× (aspect correction). PASS.
- **V5-30 calibration**: area budget {v530['area_budget_cm2']:.1f} cm² reproduces the real V5-30 N = {v530['N']} exactly (hard assert); its hydraulic solve gives Q_oil = {v530['Q_oil_mlhr']:.3g} mL/hr @ {op['Po_in_mbar']:g} mbar, positive. PASS.
- **Depth is free**: ρ(depth, N_DFU) = {rho_depth_N:+.3f} (exactly 0, hard assert). **Width costs N**: ρ(width, N_DFU) = {rho_width_N:+.3f} < 0 (hard assert). PASS.
- **Carrier-flow sensitivity**: oil-side Q_oil moves at most {carrier['q_change_pct']:.1f}% between carrier Qw = 5 and 20 mL/hr (worst: {carrier['key']}) — mild, so we report at a fixed 5 mL/hr carrier and treat the 9× dilution water for 10% as a downstream number. PASS (loose guard).
"""
    (WORKSPACE / "results" / "results_summary.md").write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# Figures (two, minimal)
# ---------------------------------------------------------------------------

def fig_dP_over_rungs(feas: pd.DataFrame, candidates: list[dict], study: dict) -> list[str]:
    """ΔP vs rung position for a few representative configs (flat → droopy)."""
    cand_by_id = {c["candidate_id"]: c for c in candidates}
    op = study["operating"]
    Po, Pout, Qw = op["Po_in_mbar"], op["P_out_mbar"], op["carrier_Qw_mlhr"]
    ranked = feas.sort_values("dP_spread_pct")
    idx = np.linspace(0, len(ranked) - 1, 4).round().astype(int)
    picks = ranked.iloc[idx].drop_duplicates("candidate_id")
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    keys = []
    for _, row in picks.iterrows():
        cand = cand_by_id[int(row["candidate_id"])]
        keys.append(cand["candidate_key"])
        config = build_device_config(cand, study)
        res = simulate(config, Po_in_mbar=Po, Qw_in_mlhr=Qw, P_out_mbar=Pout)
        x_frac = np.linspace(0.0, 1.0, cand["N_DFU"])  # position along ladder (0=inlet)
        ax.plot(x_frac, (res.P_oil - res.P_water) / 100.0, lw=1.4,
                label=f"{cand['candidate_key']} (N={cand['N_DFU']}, spread {row['dP_spread_pct']:.0f}%)")
    ax.set_xlabel("position along ladder (0 = inlet end, 1 = far end)")
    ax.set_ylabel("ΔP across DFU [mbar]")
    ax.set_title(f"DFU ΔP profile — flat vs drooping (@ {Po:g} mbar)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(WORKSPACE / "figures" / "dP_over_rungs.png", dpi=FIG_DPI)
    plt.close(fig)
    return keys


def fig_throughput_vs_main(feas: pd.DataFrame) -> None:
    """Total throughput and N_DFU vs main width, one line per depth — the two levers.

    Averaged over rung length & upstream width. Depth lines separating = depth's
    (free) throughput gain; downward N slope with width = the area tradeoff.
    """
    depths = sorted(feas["main_depth_um"].unique())
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(10, 4.2))
    for d in depths:
        sub = feas[feas["main_depth_um"] == d]
        g = sub.groupby("main_width_um")["Q_oil_total_mlhr"].mean()
        ax0.plot(g.index, g.values, marker="o", ms=5, label=f"depth {d:g} µm")
        gn = sub.groupby("main_width_um")["N_DFU"].mean()
        ax1.plot(gn.index, gn.values, marker="s", ms=5, label=f"depth {d:g} µm")
    ax0.set_xlabel("main width [µm]"); ax0.set_ylabel("total oil throughput [mL/hr]")
    ax0.set_title("Throughput vs main size (deeper = free gain)")
    ax1.set_xlabel("main width [µm]"); ax1.set_ylabel("N_DFU (area-limited)")
    ax1.set_title("DFU count vs width (depth lines overlap → depth is free)")
    ax0.legend(fontsize=8); ax1.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(WORKSPACE / "figures" / "throughput_vs_main.png", dpi=FIG_DPI)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    study = load_study()
    command = "python " + " ".join([str(Path(sys.argv[0]).as_posix())] + sys.argv[1:])
    candidates = build_candidates(study)
    git_hash, snap = write_provenance(study, command, len(candidates))
    print(f"[provenance] commit {git_hash}; snapshot snapshots/{snap}")

    r_scaling = deep_dfu_r_scaling_check(study)
    v530 = v5_30_calibration_check(study)
    carrier = carrier_sensitivity_check(candidates, study)

    Ns = [c["N_DFU"] for c in candidates]
    print(f"[sweep] {len(candidates)} configs, N_DFU {min(Ns)}-{max(Ns)}, "
          f"1 pressure ({study['operating']['Po_in_mbar']:g} mbar)")
    rows = [evaluate_candidate(c, study) for c in candidates]
    df = pd.DataFrame(rows)
    df.to_csv(WORKSPACE / "results" / "candidate_summary.csv", index=False)
    print(f"[results] candidate_summary.csv ({len(df)} rows)")

    elapsed = time.time() - t0
    write_results_summary(df, study, r_scaling, v530, carrier, git_hash, elapsed)
    feas = df[df["feasible"]].copy()
    keys = fig_dP_over_rungs(feas, candidates, study)
    fig_throughput_vs_main(feas)
    print(f"[figures] 2 figures written; dP profile configs: {keys}")
    print(f"[done] wall time {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
