#!/usr/bin/env python
"""
Compare a set of fixed designs across pressure, with the Ca ceiling as a gate.

    python scripts/compare_designs.py configs/study_my_designs.yaml
    python scripts/compare_designs.py configs/study_my_designs.yaml --ca-max 0.0017
    python scripts/compare_designs.py configs/study_my_designs.yaml --out-dir results/

Why this exists separately from ``stepgen study``: ``study`` scores and ranks a
design space into an HTML workbook.  This answers the narrower operating
question — *for designs I have already committed to, what pressure can I run at,
and what is that worth?* — and applies the Ca gate, which the workbook does not.

Two tables come out:

**Per operating point** — the raw sweep.  ΔP and its spread, the Stage-1 refill
time, the full cycle time, frequency, throughput, exit Ca.

**Per design, gated** — each design at its own highest in-regime pressure.
This is the honest headline: throughput at max pressure is not claimable if max
pressure is out of step-emulsification.

Every number derives from one hydraulic solve per point.  t_S1, t_cycle,
frequency and throughput all come from the same rung flow Q, so they cannot
disagree with each other.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from stepgen.families.serpentine import (  # noqa: E402
    ca_gated_summary,
    production_threshold_mbar,
)
from stepgen.studio.run import run_study  # noqa: E402
from stepgen.studio.study import load_study  # noqa: E402

#: γ band over which the Ca verdict is stress-tested.  γ has never been measured
#: for the Peak fluid system and Ca ∝ 1/γ exactly, so a ceiling quoted without
#: this band is a hard verdict resting on a guessed constant.
GAMMA_BAND = (0.003, 0.020)

#: Highest exit Ca Peak has ever measured (V5-8-1 Po sweep, µ=60 cP, γ=5 mN/m).
#: Passing the 0.0125 literature bound means "not obviously out of regime";
#: passing this means "inside the envelope we can actually vouch for".
CA_MEASURED_MAX = 0.0017


def _fluid_key(fluids: dict) -> tuple:
    """Identity of a fluid system, for counting distinct ones in a study."""
    return (fluids.get("phase_system"), fluids.get("mu_dispersed"),
            fluids.get("mu_continuous"), fluids.get("gamma"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study", help="Study YAML listing the designs (see configs/study_my_designs.yaml)")
    ap.add_argument("--ca-max", type=float, default=0.0125,
                    help="Exit-Ca ceiling for the gate. Default 0.0125 = rectangular "
                         "SE->jetting bound (@montessori2020). Use 0.0017 for the "
                         "measured envelope, 0.03 for the axisymmetric bound.")
    ap.add_argument("--min-production", action="store_true",
                    help="Also solve each design's minimum pressure for 100%% DFU "
                         "production (~40 extra solves per design).")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="Write both tables as CSV here.")
    args = ap.parse_args()

    study = load_study(args.study)
    print(f"{study.title}\n")
    n_designs = len({p.label.rsplit("_Po", 1)[0] for p in study.points})
    n_press = len({p.operating.get("Po_mbar") for p in study.points})
    n_fluid = len({_fluid_key(p.fluids) for p in study.points})
    print(f"  {n_designs} designs x {n_press} pressures x {n_fluid} fluid system(s) "
          f"= {len(study.points)} points")

    result = run_study(study, progress=True)
    frame = result.frame
    if "error" in frame.columns and frame["error"].notna().any():
        for _, bad in frame[frame["error"].notna()].iterrows():
            print(f"  ! {bad.get('label', '?')}: {bad['error']}")

    # gamma may vary across points when `fluids:` is a list of whole blocks. The
    # gamma-robustness column only means something against a single reference, so
    # compute it when the study uses one gamma and say so plainly when it does not.
    gammas = {float(p.fluids.get("gamma", 0.0) or 0.0) for p in study.points}
    gamma_ref = gammas.pop() if len(gammas) == 1 else 0.0
    if not gamma_ref:
        print("  ! gamma varies across points (or is 0) — the gamma-robustness "
              "column is skipped; split the study by fluid system to get it")

    # ── per operating point ─────────────────────────────────────────────────
    cols = ["label", "operating_Po_mbar", "dP_rung_mbar", "uniformity_pct",
            "t_stage1_s", "t_cycle_s", "stage1_fraction", "frequency_hz",
            "throughput_mlhr", "droplet_um", "regime_Ca"]
    per_point = frame[[c for c in cols if c in frame.columns]].copy()
    pd.set_option("display.width", 240)
    print("\n" + "=" * 110)
    print("PER OPERATING POINT")
    print("=" * 110)
    print(per_point.to_string(index=False, float_format=lambda v: f"{v:.4g}"))

    # ── per design, Ca-gated ────────────────────────────────────────────────
    gated = ca_gated_summary(frame, ca_max=args.ca_max,
                             gamma_ref=gamma_ref or None, gamma_range=GAMMA_BAND)
    print("\n" + "=" * 110)
    print(f"PER DESIGN — gated at exit Ca <= {args.ca_max:g}"
          + (f"  (gamma = {gamma_ref * 1e3:.1f} mN/m)" if gamma_ref else ""))
    print("=" * 110)
    gcols = [c for c in ["label", "Po_gated_mbar", "throughput_gated",
                         "frequency_gated_hz", "regime_Ca_gated",
                         "Po_next_failed", "passes_at_gamma_lo"] if c in gated.columns]
    print(gated[gcols].to_string(index=False, float_format=lambda v: f"{v:.4g}"))

    # ── the honest footnotes ────────────────────────────────────────────────
    print("\nRead this before quoting the gated numbers:")
    print(f"  * Po_next_failed is the lowest SIMULATED pressure that failed. The true")
    print(f"    ceiling lies between it and Po_gated_mbar — that gap is headroom you")
    print(f"    did not simulate, not headroom you do not have. Add Po points to close it.")
    if gamma_ref:
        flips = gated[gated["passes_at_gamma_lo"] == False]  # noqa: E712
        if len(flips):
            print(f"  * {len(flips)} design(s) pass at gamma = {gamma_ref*1e3:.0f} mN/m but FAIL at")
            print(f"    {GAMMA_BAND[0]*1e3:.0f} mN/m. For those the gate is reporting our ignorance")
            print(f"    about interfacial tension, not a property of the design. gamma has never")
            print(f"    been measured for this fluid system.")
    if args.ca_max > CA_MEASURED_MAX:
        print(f"  * The {args.ca_max:g} ceiling is borrowed from literature at viscosity ratio")
        print(f"    lambda ~ 1; Peak runs lambda ~ 0.015. The highest exit Ca Peak has MEASURED")
        print(f"    is {CA_MEASURED_MAX} — rerun with --ca-max {CA_MEASURED_MAX} for the envelope")
        print(f"    we can actually vouch for.")
    deep = frame.get("exit_depth_um")
    if deep is not None and (deep > 12.0).any():
        print(f"  * Exits deeper than 12 um extrapolate the droplet power law (~2x), so")
        print(f"    droplet_um and frequency_hz are soft. throughput_mlhr is NOT affected —")
        print(f"    it is the sum of rung flows and carries no droplet model.")

    # ── optional: minimum pressure for full production ──────────────────────
    if args.min_production:
        print("\n" + "=" * 110)
        print("MINIMUM PRESSURE FOR 100% DFU PRODUCTION")
        print("=" * 110)
        from stepgen.families import get_family
        fam = get_family("serpentine")
        seen: set[str] = set()
        for point in study.points:
            key = point.label.rsplit("_Po", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            cfg = fam.compile(point.params, fluids=point.fluids,
                              footprint=point.footprint,
                              manufacturing=point.manufacturing)
            po = production_threshold_mbar(
                cfg, Qw_mlhr=float(point.operating.get("Qw_mlhr", 5.0)))
            print(f"  {key:<52} {po if po is not None else 'never (>2000 mbar)'} mbar")

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        per_point.to_csv(args.out_dir / "per_operating_point.csv", index=False)
        gated.to_csv(args.out_dir / "per_design_ca_gated.csv", index=False)
        print(f"\nWrote {args.out_dir/'per_operating_point.csv'}")
        print(f"Wrote {args.out_dir/'per_design_ca_gated.csv'}")
        print(f"Model commit: {result.provenance.git_hash}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
