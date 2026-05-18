"""
Minimal example to reproduce the original linear-mode workflow.

Run:
    python -m stepgen_seed.example_run
"""

from __future__ import annotations

from stepgen_seed.resistance import Geometry, Fluids, DropletSpec, define_parameters
from stepgen_seed.hydraulics import solve_linear, summarize_solution


def main() -> None:
    geom = Geometry(
        Mcl=2040e-3,
        Mcd=100e-6,
        Mcw=500e-6,
        mcd=0.3e-6,
        mcw=1e-6,
        mcl=200e-6,
        pitch=3e-6,
        constriction_ratio=1.0,
    )

    params = define_parameters(
        geom=geom,
        fluids=Fluids(mu_water=0.00089, mu_oil=0.03452),
        droplet=DropletSpec(emulsion_ratio=0.3, droplet_radius=0.5e-6, production_frequency=50),
    )

    sol = solve_linear(params, pitch=geom.pitch)
    s = summarize_solution(sol, Mcw=geom.Mcw)

    print("Nmc =", params.Nmc)
    print("Oil channel start and end pressure [Pa]:", s["P_oil_start_Pa"], s["P_oil_end_Pa"])
    print("Water channel start and end pressure [Pa]:", s["P_water_start_Pa"], s["P_water_end_Pa"])
    print("Delaminating force [N/m]:", s["delaminating_force_N_per_m"])
    print("Flow difference [%]:", s["flow_difference_pct"])
    print("Avg rung flow [nL/min]:", s["avg_rung_flow_nL_per_min"])


if __name__ == "__main__":
    main()
