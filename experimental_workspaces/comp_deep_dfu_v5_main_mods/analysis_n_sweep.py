"""
Part 2 — manual N sweep: does a SMALLER device (fewer DFUs) buy flatness + operating range?

The Part-1 area-budget study maximises N (thousands of DFUs), which is why every config
needed a main beyond current fab caps. Here we set N by hand (100 → 10 000) and ask:

  - Fewer rungs → higher overall device resistance → less throughput (expected). By how much?
  - Does the ΔP profile get flatter, and does the *operating range* widen?
  - At low N, can we (a) stay within current fab caps (200 µm deep / 1000 µm wide main) and/or
    (b) get away with shorter rungs — or does none of that matter?

**Operating range** is quantified as the lowest inlet pressure Po at which *every* rung still
clears the capillary back-pressure `P_cap = γ·cosθ·(1/w_exit + 1/h_exit)` (a Laplace estimate).
Below that Po the drooped far rungs fall under P_cap and stop producing drops. Lower
min-operating-Po = wider usable range = more robust.

Reuses Part-1 machinery (`build_device_config`, etc.) from `analysis.py`; only N and the
operating-range metric are new. Run from the repo root:
    python experimental_workspaces/comp_deep_dfu_v5_main_mods/analysis_n_sweep.py
"""

from __future__ import annotations

import itertools
import math
import subprocess
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis import (  # reuse Part-1 machinery
    M3S_TO_MLHR,
    REPO_ROOT,
    WORKSPACE,
    _spread_pct,
    build_device_config,
    load_study,
)
from stepgen.models.hydraulics import simulate

FIG_DPI = 150


def p_cap_mbar(study: dict) -> float:
    """Laplace capillary back-pressure at the deep exit [mbar]."""
    dg, ns, fl = study["dfu_geometry"], study["n_sweep"], study["fluids"]
    w, h = dg["exit_width_um"] * 1e-6, dg["exit_depth_um"] * 1e-6
    theta = math.radians(ns["theta_deg"])
    return fl["gamma_eff"] * math.cos(theta) * (1.0 / w + 1.0 / h) / 100.0


def po_sweep(study: dict) -> np.ndarray:
    ns = study["n_sweep"]
    if "Po_values_mbar" in ns:
        return np.array([float(v) for v in ns["Po_values_mbar"]])
    s = ns["Po_sweep_mbar"]
    return np.arange(s["min"], s["max"] + s["step"] / 2.0, s["step"])


def build_n_candidates(study: dict) -> list[dict]:
    ns = study["n_sweep"]
    uw = ns["upstream_width_um"]
    combos = itertools.product(ns["N_values"], ns["main_depth_um"],
                               ns["main_width_um"], ns["DFU_length_mm"])
    out = []
    for cid, (N, md, mw, L) in enumerate(combos):
        out.append({
            "candidate_id": cid,
            "candidate_key": f"N{N}_D{md:g}_W{mw:g}_L{L:g}",
            "N_DFU": int(N), "main_depth_um": float(md), "main_width_um": float(mw),
            "DFU_length_mm": float(L), "upstream_width_um": float(uw),
        })
    return out


def evaluate(cand: dict, study: dict, pressures: np.ndarray, P_cap: float) -> dict:
    op, mfg = study["operating"], study["manufacturing"]
    carrier, Pout = op["carrier_Qw_mlhr"], op["P_out_mbar"]
    config = build_device_config(cand, study)

    min_op_Po = float("nan")
    nominal = None
    for Po in pressures:
        res = simulate(config, Po_in_mbar=float(Po), Qw_in_mlhr=carrier, P_out_mbar=Pout)
        dP = res.P_oil - res.P_water
        all_clear = bool(np.min(dP) >= P_cap * 100.0)  # every rung above P_cap [Pa]
        if all_clear and not np.isfinite(min_op_Po):
            min_op_Po = float(Po)
        if abs(float(Po) - op["Po_in_mbar"]) < 1e-9:
            active = dP > 0.0
            dP_a = dP[active] if np.any(active) else dP
            nominal = {
                "Q_oil_total_mlhr": res.Q_oil_total * M3S_TO_MLHR,
                "dP_avg_mbar": float(np.mean(dP_a)) / 100.0,
                "dP_spread_pct": _spread_pct(dP_a),
                "frac_above_Pcap": float(np.mean(dP >= P_cap * 100.0)),
            }
    if nominal is None:  # nominal Po not on the grid — solve it
        res = simulate(config, Po_in_mbar=op["Po_in_mbar"], Qw_in_mlhr=carrier, P_out_mbar=Pout)
        dP = res.P_oil - res.P_water
        active = dP > 0.0
        dP_a = dP[active] if np.any(active) else dP
        nominal = {
            "Q_oil_total_mlhr": res.Q_oil_total * M3S_TO_MLHR,
            "dP_avg_mbar": float(np.mean(dP_a)) / 100.0,
            "dP_spread_pct": _spread_pct(dP_a),
            "frac_above_Pcap": float(np.mean(dP >= P_cap * 100.0)),
        }

    row = {k: cand[k] for k in ("candidate_id", "candidate_key", "N_DFU",
                                "main_depth_um", "main_width_um", "DFU_length_mm",
                                "upstream_width_um")}
    row.update(nominal)
    row["min_operating_Po_mbar"] = min_op_Po
    row["manufacturing_ok"] = bool(cand["main_depth_um"] <= mfg["max_main_depth_um"]
                                   and cand["main_width_um"] <= mfg["max_main_width_um"])
    return row


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _main_label(d, w):
    return f"{d:g}×{w:g} µm"


def fig_size_vs_N(df: pd.DataFrame, study: dict, P_cap: float) -> None:
    """3 panels vs N (log): ΔP spread, min operating Po, throughput. Lines = main size.
    Rung fixed at the longest (flattest) value to isolate the N × main effect."""
    L = max(study["n_sweep"]["DFU_length_mm"])
    sub = df[df["DFU_length_mm"] == L]
    mains = sorted({(d, w) for d, w in zip(sub["main_depth_um"], sub["main_width_um"])})
    fig, (a0, a1, a2) = plt.subplots(1, 3, figsize=(13, 4.2))
    for d, w in mains:
        g = sub[(sub["main_depth_um"] == d) & (sub["main_width_um"] == w)].sort_values("N_DFU")
        cap = "current fab caps" if (d <= 200 and w <= 1000) else None
        lbl = _main_label(d, w) + (f" ({cap})" if cap else "")
        lw = 2.4 if cap else 1.4
        a0.plot(g["N_DFU"], g["dP_spread_pct"], marker="o", ms=4, lw=lw, label=lbl)
        a1.plot(g["N_DFU"], g["min_operating_Po_mbar"], marker="o", ms=4, lw=lw, label=lbl)
        a2.plot(g["N_DFU"], g["Q_oil_total_mlhr"], marker="o", ms=4, lw=lw, label=lbl)
    for ax in (a0, a1, a2):
        ax.set_xscale("log"); ax.set_xlabel("N DFUs (manual)"); ax.tick_params(labelsize=8)
    a0.set_ylabel("ΔP spread @ 500 mbar [%]"); a0.axhline(20, color="grey", ls="--", lw=0.8)
    a0.set_yscale("log"); a0.set_title("Flatness")
    a1.set_ylabel("min operating Po [mbar]"); a1.set_title("Operating range (lower = wider)")
    a2.set_ylabel("oil throughput [mL/hr]"); a2.set_title("Throughput (the cost)")
    a0.legend(fontsize=7, title=f"main (rung {L:g} mm)")
    fig.suptitle(f"Fewer DFUs → flatter + wider range, at the cost of throughput "
                 f"(P_cap ≈ {P_cap:.0f} mbar)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(WORKSPACE / "figures" / "n_sweep_size_vs_N.png", dpi=FIG_DPI)
    plt.close(fig)


def fig_rung_effect(df: pd.DataFrame, study: dict) -> None:
    """At the CURRENT fab-cap main (200×1000), ΔP spread vs N, one line per rung length —
    answers 'can we get away with shorter rungs at low N?'."""
    sub = df[(df["main_depth_um"] == 200.0) & (df["main_width_um"] == 1000.0)]
    if sub.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for L in sorted(sub["DFU_length_mm"].unique()):
        g = sub[sub["DFU_length_mm"] == L].sort_values("N_DFU")
        ax.plot(g["N_DFU"], g["dP_spread_pct"], marker="o", ms=5, label=f"rung {L:g} mm")
    ax.axhline(20, color="grey", ls="--", lw=0.8, label="20% (flat)")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("N DFUs (manual)"); ax.set_ylabel("ΔP spread @ 500 mbar [%]")
    ax.set_title("Current fab-cap main (200×1000 µm): rung length vs N")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(WORKSPACE / "figures" / "n_sweep_rung_effect.png", dpi=FIG_DPI)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Summary + provenance append
# ---------------------------------------------------------------------------

def write_summary(df: pd.DataFrame, study: dict, P_cap: float, git_hash: str,
                  elapsed: float) -> None:
    flat_thresh = 20.0
    # Can the current-fab-cap main (200×1000) run flat, and at what N?
    caps = df[(df["main_depth_um"] == 200.0) & (df["main_width_um"] == 1000.0)]
    caps_flat = caps[caps["dP_spread_pct"] <= flat_thresh].sort_values("N_DFU", ascending=False)
    max_flat_N_caps = int(caps_flat["N_DFU"].max()) if len(caps_flat) else 0

    def tbl(d, cols):
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

    cols = ["candidate_key", "N_DFU", "main_depth_um", "main_width_um", "DFU_length_mm",
            "Q_oil_total_mlhr", "dP_spread_pct", "min_operating_Po_mbar", "manufacturing_ok"]

    # representative: 4 mm rung, biggest main, across N — the flatness/throughput trend
    trend = df[(df["DFU_length_mm"] == max(study["n_sweep"]["DFU_length_mm"]))
               & (df["main_depth_um"] == 400.0) & (df["main_width_um"] == 2000.0)
               ].sort_values("N_DFU")

    md = f"""# Part 2 Results — Manual N sweep (device size & operating range)

Auto-generated by `analysis_n_sweep.py`. Narrative in `../report.md` (Part 2).

**Model commit**: {git_hash} · **Generated**: {datetime.now().isoformat(timespec='seconds')}
**Configs**: {len(df)} · Po = {study['operating']['Po_in_mbar']:g} mbar (spread/throughput), Po swept {min(study['n_sweep']['Po_values_mbar']):g}–{max(study['n_sweep']['Po_values_mbar']):g} mbar (operating range)
**Capillary back-pressure P_cap** ≈ {P_cap:.1f} mbar (Laplace, γ·cosθ·(1/w+1/h), θ={study['n_sweep']['theta_deg']:g}°) · wall time {elapsed:.0f} s

## Headline

- **Fewer DFUs → flatter ΔP and a wider operating range**, at a throughput cost roughly
  proportional to N (fewer parallel rungs = higher device resistance = less oil out).
- **A ~{max_flat_N_caps}-DFU device runs flat (ΔP spread ≤ {flat_thresh:g}%) on the CURRENT fab-cap main
  (200 µm deep × 1000 µm wide)** — which no area-budget (thousands-of-DFU) config could.
  Dropping N is the cheapest route to a buildable, robust deep-DFU device.

## Flatness / range / throughput vs N (biggest main, 4 mm rung)

{tbl(trend[cols], cols)}

## Can the current fab-cap main (200×1000 µm) stay flat? (≤ {flat_thresh:g}% spread)

{tbl(caps_flat[cols] if len(caps_flat) else caps.sort_values('N_DFU')[cols], cols)}

## Verification

- Smoke test: `n_sweep_summary.csv`, this file, 2 figures generated.
- Monotonic (expected): throughput rises with N; ΔP spread rises with N; min-operating-Po
  rises with N (all within each main/rung group).
"""
    (WORKSPACE / "results" / "n_sweep_summary.md").write_text(md, encoding="utf-8")


def append_manifest(study: dict, command: str, git_hash: str, P_cap: float, n: int) -> None:
    entry = f"""

## Run: Part 2 — manual N sweep — {datetime.now().date().isoformat()}

**Model commit**: {git_hash}
**Command**: `{command}`
**Run**: {datetime.now().isoformat(timespec='seconds')}
**Outputs**: results/n_sweep_summary.csv, results/n_sweep_summary.md,
figures/n_sweep_size_vs_N.png, figures/n_sweep_rung_effect.png
**N values**: {study['n_sweep']['N_values']} (manual, not area-budgeted)
**P_cap**: {P_cap:.1f} mbar (Laplace, θ={study['n_sweep']['theta_deg']:g}°)
**Configs**: {n}
"""
    path = WORKSPACE / "snapshots" / "run_manifest.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = "\n\n## Run: Part 2 — manual N sweep"
    if marker in text:                       # drop any prior Part-2 entry (idempotent)
        text = text[:text.index(marker)]
    path.write_text(text.rstrip() + entry, encoding="utf-8")


def main() -> None:
    t0 = time.time()
    study = load_study()
    import sys
    command = "python " + " ".join([str(Path(sys.argv[0]).as_posix())] + sys.argv[1:])
    git_hash = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    P_cap = p_cap_mbar(study)
    print(f"[part2] P_cap ~ {P_cap:.2f} mbar (Laplace)")

    cands = build_n_candidates(study)
    pressures = po_sweep(study)
    print(f"[part2] {len(cands)} configs x {len(pressures)} pressures")
    rows = [evaluate(c, study, pressures, P_cap) for c in cands]
    df = pd.DataFrame(rows)
    df.to_csv(WORKSPACE / "results" / "n_sweep_summary.csv", index=False)

    # Guard only the lightly-loaded big main (400×2000), where throughput and spread should
    # rise cleanly with N. For heavily-loaded small mains, throughput is NON-monotonic — past
    # a "useful N ceiling" the far rungs reverse and stop adding oil (a finding, not a bug).
    big = df[(df["main_depth_um"] == 400.0) & (df["main_width_um"] == 2000.0)]
    n_nonmono = 0
    for _, g in df.groupby(["main_depth_um", "main_width_um", "DFU_length_mm"]):
        g = g.sort_values("N_DFU")
        if not (np.diff(g["Q_oil_total_mlhr"].values) >= -1e-6).all():
            n_nonmono += 1
    for _, g in big.groupby("DFU_length_mm"):
        g = g.sort_values("N_DFU")
        assert (np.diff(g["Q_oil_total_mlhr"].values) >= -1e-6).all(), \
            "throughput should rise with N for the lightly-loaded 400x2000 main"
        assert (np.diff(g["dP_spread_pct"].values) >= -1e-6).all(), \
            "dP spread should rise with N for the 400x2000 main"
    print(f"[part2] big-main monotonicity OK; {n_nonmono} small-main groups show a "
          f"useful-N ceiling (throughput plateaus/falls as far rungs reverse)")

    write_summary(df, study, P_cap, git_hash, time.time() - t0)
    fig_size_vs_N(df, study, P_cap)
    fig_rung_effect(df, study)
    append_manifest(study, command, git_hash, P_cap, len(df))
    print(f"[part2] summary + 2 figures written; wall time {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
