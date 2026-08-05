#!/usr/bin/env python
"""
Compare a set of fixed designs across pressure, gated against recorded experience.

    python scripts/compare_designs.py configs/study_my_designs.yaml
    python scripts/compare_designs.py configs/study_my_designs.yaml --max-v 2
    python scripts/compare_designs.py configs/study_my_designs.yaml --out-dir results/

Why this exists separately from ``stepgen study``: ``study`` scores and ranks a
design space into an HTML workbook.  This answers the narrower operating
question — *for designs I have already committed to, what pressure can I run at,
and what is that worth?* — and applies the experience gate, which the workbook
reports but does not enforce.

Two tables come out:

**Per operating point** — the raw sweep.  ΔP and its spread, the Stage-1 refill
time, the full cycle time, frequency, throughput, exit velocity and exit Ca.

**Per design, gated** — each design at its own highest pressure that still drives
each DFU no harder than the fastest one Peak has run (``v_vs_demonstrated <= 1``).
This is the honest headline: throughput at max pressure is not claimable if max
pressure is somewhere nobody has been.

**The gate changed on 2026-08-05** and this is the point of the script.  It used
to be ``exit Ca <= 0.0125``, a literature ceiling divided by a γ nobody has
measured.  It is now a ratio of velocities against a *measurement*, in which γ
cancels exactly and — against the same fluid — so does µ.  Exit Ca is still
printed, with the γ behind it, because what the literature threshold would say is
worth seeing.  It just no longer decides anything.

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

from stepgen.families.base import (  # noqa: E402
    CA_MEASURED_MAX,
    V_EXIT_DEMONSTRATED_MAX,
)
from stepgen.families.serpentine import (  # noqa: E402
    gated_summary,
    production_threshold_mbar,
)
from stepgen.studio.run import run_study  # noqa: E402
from stepgen.studio.study import load_study  # noqa: E402

#: γ band over which the *reported* Ca column is stress-tested.  γ has never been
#: measured for the Peak fluid system and Ca ∝ 1/γ exactly, so a ceiling quoted
#: without this band is a hard verdict resting on a guessed constant.  Since the
#: 2026-08-05 ruling nothing is gated on Ca, so this band no longer qualifies a
#: verdict — it qualifies a footnote.
GAMMA_BAND = (0.003, 0.020)

#: Rectangular SE→jetting bound (@montessori2020-step-emulsification), at λ ≈ 1
#: while Peak runs λ ≈ 0.015.  Kept only to annotate the reported Ca column.
CA_LITERATURE_CEILING = 0.0125


def _fluid_key(fluids: dict) -> tuple:
    """Identity of a fluid system, for counting distinct ones in a study."""
    return (fluids.get("phase_system"), fluids.get("mu_dispersed"),
            fluids.get("mu_continuous"), fluids.get("gamma"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study", help="Study YAML listing the designs (see configs/study_my_designs.yaml)")
    ap.add_argument("--max-v", type=float, default=1.0, metavar="K",
                    help="Gate: highest exit velocity allowed, as a multiple of the "
                         "fastest DFU Peak has run (%.4f mm/s, V5-8-1 at 600 mbar / "
                         "Qw 5). Default 1 = stay inside what we have run. No "
                         "unmeasured constant enters this number."
                         % (V_EXIT_DEMONSTRATED_MAX * 1e3))
    ap.add_argument("--min-production", action="store_true",
                    help="Also solve each design's minimum pressure for 100%% DFU "
                         "production (~40 extra solves per design).")
    ap.add_argument("--phase", type=str, default=None, metavar="o/w|w/o",
                    help="Show only this phase system. A VIEW over the same solve — "
                         "all fluid systems are still run, so one command still "
                         "produces one auditable result set.")
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

    # Filter AFTER solving, never before: the phase view is a view, so the run
    # stays one auditable solve of everything the config declares.
    if args.phase:
        if "phase_system" not in frame.columns:
            print(f"  ! --phase given but rows carry no phase_system; ignoring")
        else:
            keep = frame["phase_system"].astype(str) == args.phase
            if not keep.any():
                have = sorted(set(frame["phase_system"].dropna().astype(str)))
                print(f"  ! no rows with phase_system == {args.phase!r}; have {have}")
                return 2
            frame = frame[keep]
            print(f"  showing phase_system == {args.phase!r} "
                  f"({len(frame)} of {len(result.frame)} rows)")

    # ── per operating point ─────────────────────────────────────────────────
    cols = ["label", "operating_Po_mbar", "Qw_mlhr", "emulsion_pct",
            "dP_rung_mbar", "uniformity_pct",
            "t_stage1_s", "t_cycle_s", "stage1_fraction", "frequency_hz",
            "throughput_mlhr", "droplet_um", "v_vs_demonstrated", "regime_Ca"]
    per_point = frame[[c for c in cols if c in frame.columns]].copy()
    pd.set_option("display.width", 240)
    print("\n" + "=" * 110)
    print("PER OPERATING POINT")
    print("=" * 110)
    print(per_point.to_string(index=False, float_format=lambda v: f"{v:.4g}"))

    # ── per design, gated against recorded experience ───────────────────────
    gated = gated_summary(frame, max_v_vs_demonstrated=args.max_v)
    print("\n" + "=" * 110)
    print(f"PER DESIGN — gated at exit velocity <= {args.max_v:g}x demonstrated "
          f"({V_EXIT_DEMONSTRATED_MAX * 1e3 * args.max_v:.4f} mm/s)")
    print("=" * 110)
    gcols = [c for c in ["label", "Po_gated_mbar", "throughput_gated",
                         "frequency_gated_hz", "v_vs_demonstrated_gated",
                         "regime_Ca_gated", "gamma_Nm",
                         "Po_next_failed"] if c in gated.columns]
    print(gated[gcols].to_string(index=False, float_format=lambda v: f"{v:.4g}"))

    # ── the honest footnotes ────────────────────────────────────────────────
    print("\nRead this before quoting the gated numbers:")
    print(f"  * Po_next_failed is the lowest SIMULATED pressure that failed. The true")
    print(f"    ceiling lies between it and Po_gated_mbar — that gap is headroom you")
    print(f"    did not simulate, not headroom you do not have. Add Po points to close it.")
    print(f"  * The gate is a RATIO to a measurement ({V_EXIT_DEMONSTRATED_MAX*1e3:.4f} mm/s,")
    print(f"    V5-8-1 at 600 mbar / Qw 5, n=14). gamma cancels out of it exactly and, against")
    print(f"    the same fluid, so does viscosity. It says nobody has been past 1x — not that")
    print(f"    past 1x fails. A design over the gate is unproven, not disproven.")
    # regime_Ca_gated is REPORTED, never gated (2026-08-05 ruling). All this
    # footnote does is say what the borrowed literature ceiling would have said.
    sub = gated[["regime_Ca_gated", "gamma_Nm"]].dropna(subset=["regime_Ca_gated"])
    if len(sub):
        over = int((sub["regime_Ca_gated"] > CA_LITERATURE_CEILING).sum())
        # Ca ∝ 1/γ, so the pessimistic end of the band scales Ca up by γ_row/γ_lo.
        with_g = sub.dropna(subset=["gamma_Nm"])
        over_lo = int((with_g["regime_Ca_gated"] * with_g["gamma_Nm"] / GAMMA_BAND[0]
                       > CA_LITERATURE_CEILING).sum()) if len(with_g) == len(sub) else None
        print(f"  * regime_Ca_gated is REPORTED, not gated. Against the borrowed "
              f"{CA_LITERATURE_CEILING:g} literature")
        print(f"    ceiling, {over} of {len(sub)} gated point(s) would fail as solved"
              + (f", and {over_lo} at the pessimistic"
                 f" gamma = {GAMMA_BAND[0]*1e3:.0f} mN/m." if over_lo is not None else "."))
        print(f"    That ceiling is at lambda ~ 1; Peak runs lambda ~ 0.015, and the highest exit")
        print(f"    Ca Peak has MEASURED is {CA_MEASURED_MAX}. gamma has never been measured for")
        print(f"    this fluid system, which is why it no longer decides anything here.")
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
        gated.to_csv(args.out_dir / "per_design_gated.csv", index=False)
        print(f"\nWrote {args.out_dir/'per_operating_point.csv'}")
        print(f"Wrote {args.out_dir/'per_design_gated.csv'}")
        print(f"Model commit: {result.provenance.git_hash}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
