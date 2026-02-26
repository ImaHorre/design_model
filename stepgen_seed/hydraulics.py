"""
stepgen_seed.hydraulics

Sparse ladder-network builder and solver extracted from the original script.
Goal: preserve the original indexing and sign conventions in linear mode.

Network:
- Two distributed main channels (oil and water), segmented by pitch.
- N rungs connecting the two mains with resistance R_Omc.

Unknown vector "x" solved from A x = B represents nodal pressures (up to a sign convention).
The original code post-processes:
    Oc_pressures = -result[2::2][::-1]
    Wc_pressures = -result[3::2][::-1]

We keep that to preserve behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.sparse import lil_matrix, csr_matrix
from scipy.sparse.linalg import spsolve

from .resistance import ModelParams


@dataclass(frozen=True)
class LinearSolution:
    raw: np.ndarray
    P_oil: np.ndarray
    P_water: np.ndarray
    Q_rungs: np.ndarray
    x_positions: np.ndarray


def generate_conduction_matrix(params: ModelParams) -> tuple[csr_matrix, np.ndarray]:
    """
    Build the sparse matrix A and RHS B for the original ladder network formulation.
    """
    Nmc = params.Nmc
    r1 = params.R_WMc
    r2 = params.R_Omc
    r3 = params.R_OMc
    QOut = params.Q_O + params.Q_W

    number_of_nodes = 2 * Nmc + 2
    A = lil_matrix((number_of_nodes, number_of_nodes), dtype=float)

    A[0, :3] = [-1 / r3, 0, 1 / r3]
    A[1, :4] = [0, -1 / r1, 0, 1 / r1]
    A[2, :5] = [0, 0, -1 / r3 - 1 / r2, 1 / r2, 1 / r3]
    A[3, :6] = [0, 0, 1 / r2, -1 / r1 - 1 / r2, 0, 1 / r1]
    A[4, -4:] = [-1 / r3, 0, 1 / r3 + 1 / r2, -1 / r2]
    A[5, -1:] = [1 / r1]

    oil_conductance_vector = [-1 / r3, 0, 2 / r3 + 1 / r2, -1 / r2, -1 / r3]
    water_conductance_vector = [1 / r1, 1 / r2, -2 / r1 - 1 / r2, 0, 1 / r1]

    for i in range(Nmc - 2):
        A[2 * i + 6, 2 + 2 * i : 2 + 2 * i + 5] = oil_conductance_vector
        A[2 * i + 7, 3 + 2 * i : 3 + 2 * i + 5] = water_conductance_vector

    B = np.zeros(number_of_nodes, dtype=float)
    B[:6] = [params.Q_O, params.Q_W, params.Q_O, params.Q_W, 0, -QOut]

    return A.tocsr(), B


def solve_linear(params: ModelParams, *, pitch: float) -> LinearSolution:
    """Solve linear ladder and compute rung flows."""
    A, B = generate_conduction_matrix(params)
    raw = spsolve(A, B)

    P_oil = -raw[2::2][::-1]
    P_water = -raw[3::2][::-1]
    Q_rungs = -(P_water - P_oil) / params.R_Omc

    x_positions = np.arange(params.Nmc, dtype=float) * pitch

    return LinearSolution(
        raw=np.asarray(raw, dtype=float),
        P_oil=np.asarray(P_oil, dtype=float),
        P_water=np.asarray(P_water, dtype=float),
        Q_rungs=np.asarray(Q_rungs, dtype=float),
        x_positions=x_positions,
    )


def summarize_solution(sol: LinearSolution, *, Mcw: float) -> dict:
    """Convenience summary mirroring original printouts."""
    Q_rungs_nL_per_min = sol.Q_rungs * 60.0 * 1e12
    avg_flow = float(np.mean(Q_rungs_nL_per_min))
    flow_diff_pct = float((np.max(Q_rungs_nL_per_min) - avg_flow) / avg_flow * 100.0)

    delam_force = float(sol.P_oil[0] * Mcw)

    return {
        "P_oil_start_Pa": float(sol.P_oil[0]),
        "P_oil_end_Pa": float(sol.P_oil[-1]),
        "P_water_start_Pa": float(sol.P_water[0]),
        "P_water_end_Pa": float(sol.P_water[-1]),
        "delaminating_force_N_per_m": delam_force,
        "avg_rung_flow_nL_per_min": avg_flow,
        "flow_difference_pct": flow_diff_pct,
        "Q_rungs_nL_per_min": Q_rungs_nL_per_min,
    }
