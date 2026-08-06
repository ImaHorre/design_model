"""
bench_solve_cost.py — re-measure the solve costs in configs/studio_defaults.yaml

    python scripts/bench_solve_cost.py

Prints a table per family and the YAML block to paste back into
``configs/studio_defaults.yaml`` under ``solve_cost:``.

These numbers are wall-clock on one machine and feed only the runtime estimate
the Studio form shows before a run.  Nothing scores or gates on them, so a
machine-to-machine difference is not a bug — but the *shape* matters: serpentine
and manifold are linear in the number of elements they solve, radial is closed
form and does no network solve at all.  If a re-measure ever shows otherwise,
that is worth investigating before pasting it in.
"""

from __future__ import annotations

import statistics
import time

import matplotlib

matplotlib.use("Agg")

from stepgen.families import get_family  # noqa: E402

FLUIDS = {"mu_dispersed": 0.06, "mu_continuous": 0.00089,
          "gamma": 0.005, "phase_system": "o/w"}
FOOTPRINT = {"square_side_mm": 100.0}
MANUFACTURING = {"max_main_depth_um": 200.0, "max_main_width_um": 2000.0,
                 "min_wall_um": 5.0}
OPERATING = {"Po_mbar": 200.0, "Qw_mlhr": 5.0}

#: Serpentine ladder lengths to sweep — (main length mm, pitch µm).
SERPENTINE_SIZES = [10, 20, 40, 80, 160, 320]
SERPENTINE_PITCH_UM = 120

#: Manifold (arms, rungs per arm).
MANIFOLD_SIZES = [(4, 20), (8, 40), (16, 80), (32, 100)]

#: The size each family's flat ``ms_per_point`` is quoted at.
REFERENCE = {"serpentine": 333, "manifold": 320, "radial": 0}


def _median_ms(fn, reps: int) -> float:
    fn()                                   # warm-up, not counted
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples)


def _serpentine_params(length_mm: int) -> dict:
    return {
        "main": {"length_mm": length_mm, "depth_um": 400, "width_um": 2000},
        "rung": {"length_mm": 4, "upstream_width_um": 40},
        "junction": {"exit_width_um": 60, "exit_depth_um": 20,
                     "pitch_um": SERPENTINE_PITCH_UM},
    }


def _manifold_params(arms: int, per_arm: int) -> dict:
    return {
        "main": {"depth_um": 200, "width_um": 1000},
        "arms": {"count": arms, "depth_um": 100, "width_um": 200},
        "rung": {"length_mm": 2, "upstream_width_um": 30},
        "rungs_per_arm": per_arm,
        "junction": {"exit_width_um": 30, "exit_depth_um": 20, "pitch_um": 120},
    }


def _radial_params() -> dict:
    return {
        "main": {"depth_um": 200, "width_um": 1000},
        "spokes": {"count": 64},
        "rung": {"length_mm": 2, "upstream_width_um": 30},
        "junction": {"exit_width_um": 30, "exit_depth_um": 20, "pitch_um": 120},
    }


def _run(family: str, params: dict, fluids=None, operating=None) -> None:
    get_family(family).evaluate(
        params, fluids=fluids or FLUIDS, footprint=FOOTPRINT,
        manufacturing=MANUFACTURING, operating=operating or OPERATING,
        label="bench")


def measure() -> dict[str, dict]:
    out: dict[str, dict] = {}

    print("=== serpentine — linear in rung count ===")
    rows = []
    for length_mm in SERPENTINE_SIZES:
        n = int(length_mm * 1000 / SERPENTINE_PITCH_UM)
        params = _serpentine_params(length_mm)
        ms = _median_ms(lambda: _run("serpentine", params), reps=15)
        rows.append((n, ms))
        print(f"  N={n:>5}  {ms:8.1f} ms   ({ms / n * 1000:6.2f} µs/rung)")
    out["serpentine"] = {
        "us_per_element": round(statistics.median(ms / n * 1000 for n, ms in rows), 1),
        "ms_per_point": round(dict(rows).get(REFERENCE["serpentine"], rows[0][1]), 1),
        "reference_elements": REFERENCE["serpentine"],
    }

    print("\n=== manifold — linear in node count ===")
    rows = []
    for arms, per_arm in MANIFOLD_SIZES:
        n = arms * per_arm
        params = _manifold_params(arms, per_arm)
        ms = _median_ms(
            lambda: _run("manifold", params,
                         fluids={"mu_dispersed": 0.06, "gamma": 0.015},
                         operating={"Po_mbar": 500}),
            reps=10)
        rows.append((n, ms))
        print(f"  nodes={n:>5}  {ms:8.1f} ms   ({ms / n * 1000:6.2f} µs/node)")
    out["manifold"] = {
        "us_per_element": round(statistics.median(ms / n * 1000 for n, ms in rows), 1),
        "ms_per_point": round(dict(rows).get(REFERENCE["manifold"], rows[0][1]), 1),
        "reference_elements": REFERENCE["manifold"],
    }

    print("\n=== radial — closed form, no network solve ===")
    params = _radial_params()
    ms = _median_ms(lambda: _run("radial", params), reps=100)
    print(f"  {ms:8.3f} ms/point")
    out["radial"] = {"us_per_element": 0.0,
                     "ms_per_point": round(ms, 3),
                     "reference_elements": 0}
    return out


def main() -> int:
    costs = measure()
    print("\n" + "=" * 60)
    print("Paste under `solve_cost:` in configs/studio_defaults.yaml:\n")
    for family, c in costs.items():
        print(f"  {family}:")
        print(f"    us_per_element: {c['us_per_element']}")
        print(f"    ms_per_point: {c['ms_per_point']}")
        print(f"    reference_elements: {c['reference_elements']}")
    print("\n  default:")
    print(f"    us_per_element: {costs['serpentine']['us_per_element']}")
    print(f"    ms_per_point: {costs['serpentine']['ms_per_point']}")
    print(f"    reference_elements: {costs['serpentine']['reference_elements']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
