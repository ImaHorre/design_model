"""
stepgen.models.hydraulics
=========================
Sparse ladder-network builder and linear solver.

Two solvers are provided:

solve_linear(config, *, Q_oil, Q_water)
    Flow-controlled on both sides (design mode; ported from seed).
    Sign convention: P_oil = -raw[2::2][::-1], P_water = -raw[3::2][::-1]

simulate(config, Po_in_mbar, Qw_in_mlhr, P_out_mbar=0.0)
    Mixed boundary conditions: oil inlet pressure + water inlet flow.
    Builds a fresh 2N×2N nodal system; unknowns ordered
        x = [P_oil[0..N-1], P_water[0..N-1]]
    Dirichlet BCs: P_oil[0]=Po_in, P_water[N-1]=P_out
    Neumann BC (oil dead-end): KCL at node N-1 has no rightward main-channel
        segment — the oil rail terminates in a wall.  This enforces zero axial
        oil flow past node N-1 and allows all N rungs to carry oil→water flow.
        Global conservation: Q_oil_in = Σ Q_rungs (AC9).
    Neumann BC (water inlet): Q_water injected at water inlet node 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from .resistance import main_channel_resistance_per_segment, rung_resistance
from stepgen.config import mbar_to_pa, mlhr_to_m3s

if TYPE_CHECKING:
    from scipy.sparse import csr_matrix
    from stepgen.config import DeviceConfig


@dataclass(frozen=True)
class LinearSolution:
    raw: np.ndarray
    P_oil: np.ndarray
    P_water: np.ndarray
    Q_rungs: np.ndarray
    x_positions: np.ndarray


@dataclass(frozen=True)
class LadderParams:
    """Internal parameter bundle for the sparse matrix builder."""
    Nmc: int
    R_OMc: float   # oil main channel resistance per pitch segment
    R_WMc: float   # water main channel resistance per pitch segment
    R_Omc: float   # rung (microchannel) resistance
    Q_O: float     # oil inlet flow [m³/s]
    Q_W: float     # water inlet flow [m³/s]


def build_ladder_params(
    config: "DeviceConfig",
    *,
    Q_oil: float,
    Q_water: float,
) -> LadderParams:
    """Derive LadderParams from a DeviceConfig and prescribed inlet flows."""
    R_oil_main, R_water_main = main_channel_resistance_per_segment(config)
    return LadderParams(
        Nmc=config.geometry.Nmc,
        R_OMc=R_oil_main,
        R_WMc=R_water_main,
        R_Omc=rung_resistance(config),
        Q_O=Q_oil,
        Q_W=Q_water,
    )


def generate_conduction_matrix(
    params: LadderParams,
) -> "tuple[csr_matrix, np.ndarray]":
    """
    Build sparse matrix A and RHS vector B for the ladder network.

    Ported directly from stepgen_seed.hydraulics.generate_conduction_matrix;
    indexing and stencil are unchanged.
    """
    Nmc = params.Nmc
    r1 = params.R_WMc
    r2 = params.R_Omc
    r3 = params.R_OMc
    QOut = params.Q_O + params.Q_W

    number_of_nodes = 2 * Nmc + 2
    A = lil_matrix((number_of_nodes, number_of_nodes), dtype=float)

    # Boundary / inlet rows (rows 0–5)
    A[0, :3] = [-1 / r3, 0, 1 / r3]
    A[1, :4] = [0, -1 / r1, 0, 1 / r1]
    A[2, :5] = [0, 0, -1 / r3 - 1 / r2, 1 / r2, 1 / r3]
    A[3, :6] = [0, 0, 1 / r2, -1 / r1 - 1 / r2, 0, 1 / r1]
    A[4, -4:] = [-1 / r3, 0, 1 / r3 + 1 / r2, -1 / r2]
    A[5, -1:] = [1 / r1]

    # Interior rung stencils
    oil_stencil   = [-1 / r3, 0,        2 / r3 + 1 / r2, -1 / r2, -1 / r3]
    water_stencil = [ 1 / r1, 1 / r2, -2 / r1 - 1 / r2,        0,  1 / r1]

    for i in range(Nmc - 2):
        A[2 * i + 6, 2 + 2 * i : 2 + 2 * i + 5] = oil_stencil
        A[2 * i + 7, 3 + 2 * i : 3 + 2 * i + 5] = water_stencil

    B = np.zeros(number_of_nodes, dtype=float)
    B[:6] = [params.Q_O, params.Q_W, params.Q_O, params.Q_W, 0, -QOut]

    return A.tocsr(), B


def solve_linear(
    config: "DeviceConfig",
    *,
    Q_oil: float,
    Q_water: float,
) -> LinearSolution:
    """
    Solve the linear ladder network for given inlet flows.

    Parameters
    ----------
    config : DeviceConfig
    Q_oil : float   Oil inlet flow [m³/s]
    Q_water : float Water inlet flow [m³/s]

    Returns
    -------
    LinearSolution
    """
    params = build_ladder_params(config, Q_oil=Q_oil, Q_water=Q_water)
    A, B = generate_conduction_matrix(params)
    raw = spsolve(A, B)

    # Sign convention: preserved verbatim from stepgen_seed
    P_oil   = -raw[2::2][::-1]
    P_water = -raw[3::2][::-1]
    Q_rungs = -(P_water - P_oil) / params.R_Omc

    x_positions = np.arange(params.Nmc, dtype=float) * config.geometry.rung.pitch

    return LinearSolution(
        raw=np.asarray(raw, dtype=float),
        P_oil=np.asarray(P_oil, dtype=float),
        P_water=np.asarray(P_water, dtype=float),
        Q_rungs=np.asarray(Q_rungs, dtype=float),
        x_positions=x_positions,
    )


def summarize_solution(sol: LinearSolution, *, Mcw: float) -> dict:
    """Convenience summary mirroring stepgen_seed.hydraulics.summarize_solution."""
    Q_nL_min = sol.Q_rungs * 60.0 * 1e12
    avg = float(np.mean(Q_nL_min))
    flow_diff_pct = float((np.max(Q_nL_min) - avg) / avg * 100.0)
    return {
        "P_oil_start_Pa": float(sol.P_oil[0]),
        "P_oil_end_Pa": float(sol.P_oil[-1]),
        "P_water_start_Pa": float(sol.P_water[0]),
        "P_water_end_Pa": float(sol.P_water[-1]),
        "delaminating_force_N_per_m": float(sol.P_oil[0] * Mcw),
        "avg_rung_flow_nL_per_min": avg,
        "flow_difference_pct": flow_diff_pct,
        "Q_rungs_nL_per_min": Q_nL_min,
    }


# ---------------------------------------------------------------------------
# Mixed boundary-condition simulation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimResult:
    """
    Result of a mixed-BC simulation.

    Pressure profiles and rung flows follow the same spatial convention as
    LinearSolution: index 0 is the oil/water inlet end.

    Attributes
    ----------
    P_oil, P_water : ndarray shape (N,)   pressures [Pa]
    Q_rungs        : ndarray shape (N,)   rung flows [m³/s], +ve = oil→water
    x_positions    : ndarray shape (N,)   along-channel positions [m]
    Q_oil_total    : float                oil flow at inlet [m³/s]
    Q_water_total  : float                water flow at inlet [m³/s]  (= Qw_in_m3s)
    Po_in_Pa       : float                oil inlet pressure used [Pa]
    Qw_in_m3s      : float                water inlet flow used [m³/s]
    P_out_Pa       : float                outlet reference pressure [Pa]
    """
    P_oil: np.ndarray
    P_water: np.ndarray
    Q_rungs: np.ndarray
    x_positions: np.ndarray
    Q_oil_total: float
    Q_water_total: float
    Po_in_Pa: float
    Qw_in_m3s: float
    P_out_Pa: float


def _build_mixed_bc_matrix(
    N: int,
    R_OMc: float,
    R_WMc: float,
    R_Omc: float,
    Po_in_Pa: float,
    Qw_in_m3s: float,
    P_out_Pa: float,
    *,
    g_rungs: "np.ndarray | None" = None,
    rhs_oil: "np.ndarray | None" = None,
    rhs_water: "np.ndarray | None" = None,
) -> "tuple[csr_matrix, np.ndarray]":
    """
    Build the 2N × 2N sparse system for mixed-BC simulation.

    Unknowns: x = [P_oil[0..N-1], P_water[0..N-1]]

    Optional per-rung overrides (used by the threshold/hysteresis solver):
      g_rungs   : per-rung conductances [m³/(Pa·s)], shape (N,).
                  Defaults to uniform 1/R_Omc.
      rhs_oil   : RHS offset for oil interior nodes, shape (N,).
                  For ACTIVE rung i: -g_i * dP_cap_ow;  for REVERSE: +g_i * dP_cap_wo.
      rhs_water : equal and opposite to rhs_oil at paired water nodes.
    """
    if N < 2:
        raise ValueError(f"Need Nmc >= 2 for mixed-BC simulation; got {N}.")

    g0 = 1.0 / R_Omc
    if g_rungs is None:
        g_rungs = np.full(N, g0)
    if rhs_oil is None:
        rhs_oil = np.zeros(N)
    if rhs_water is None:
        rhs_water = np.zeros(N)

    size = 2 * N
    A = lil_matrix((size, size), dtype=float)
    B = np.zeros(size, dtype=float)

    # ── Dirichlet: oil inlet ────────────────────────────────────────────────
    A[0, 0] = 1.0
    B[0] = Po_in_Pa

    # ── KCL: oil interior nodes 1 .. N-2 ───────────────────────────────────
    for i in range(1, N - 1):
        gi = float(g_rungs[i])
        A[i, i - 1] =  1.0 / R_OMc
        A[i, i]     = -(2.0 / R_OMc + gi)
        A[i, i + 1] =  1.0 / R_OMc
        A[i, N + i] =  gi
        B[i] = float(rhs_oil[i])

    # ── KCL: oil dead-end node N-1 (zero-flux Neumann) ─────────────────────
    # No rightward main-channel segment — the oil rail terminates here.
    # Inflow from node N-2 equals outflow through rung N-1.
    g_last = float(g_rungs[N - 1])
    A[N - 1, N - 2] =  1.0 / R_OMc
    A[N - 1, N - 1] = -(1.0 / R_OMc + g_last)
    A[N - 1, 2 * N - 1] = g_last
    B[N - 1] = float(rhs_oil[N - 1])

    # ── KCL: water inlet (node 0 in water space, row N overall) ────────────
    g0w = float(g_rungs[0])
    A[N, 0]     =  g0w
    A[N, N]     = -(g0w + 1.0 / R_WMc)
    A[N, N + 1] =  1.0 / R_WMc
    B[N] = -Qw_in_m3s + float(rhs_water[0])

    # ── KCL: water interior nodes 1 .. N-2 ─────────────────────────────────
    for j in range(1, N - 1):
        gj = float(g_rungs[j])
        row = N + j
        A[row, row - 1] =  1.0 / R_WMc
        A[row, row]     = -(2.0 / R_WMc + gj)
        A[row, row + 1] =  1.0 / R_WMc
        A[row, j]       =  gj
        B[row] = float(rhs_water[j])

    # ── Dirichlet: water outlet ─────────────────────────────────────────────
    A[2 * N - 1, 2 * N - 1] = 1.0
    B[2 * N - 1] = P_out_Pa

    return A.tocsr(), B


def _simulate_pa(
    config: "DeviceConfig",
    Po_Pa: float,
    Qw_m3s: float,
    P_out_Pa: float,
    *,
    g_rungs: "np.ndarray | None" = None,
    rhs_oil: "np.ndarray | None" = None,
    rhs_water: "np.ndarray | None" = None,
) -> SimResult:
    """
    Core solver (SI units).  Public interface is ``simulate()``;
    ``generator.iterative_solve()`` calls this directly with modified arrays.

    Q_rungs computation accounts for threshold offsets:
        Q_rungs[i] = g_rungs[i] * (P_oil[i] - P_water[i]) + rhs_oil[i]
    This equals the physically meaningful flow (threshold-adjusted) for
    ACTIVE and REVERSE rungs, and ≈ 0 for OFF rungs.
    """
    N = config.geometry.Nmc
    R_OMc, R_WMc = main_channel_resistance_per_segment(config)
    R_Omc = rung_resistance(config)

    # Defaults (uniform, linear case)
    if g_rungs is None:
        g_rungs = np.full(N, 1.0 / R_Omc)
    if rhs_oil is None:
        rhs_oil = np.zeros(N)
    if rhs_water is None:
        rhs_water = np.zeros(N)

    A, B = _build_mixed_bc_matrix(
        N, R_OMc, R_WMc, R_Omc, Po_Pa, Qw_m3s, P_out_Pa,
        g_rungs=g_rungs, rhs_oil=rhs_oil, rhs_water=rhs_water,
    )
    x = spsolve(A, B)

    P_oil   = np.asarray(x[:N], dtype=float)
    P_water = np.asarray(x[N:], dtype=float)

    # Threshold-adjusted rung flows (identical to linear for default arrays)
    Q_rungs = g_rungs * (P_oil - P_water) + rhs_oil

    x_pos = np.arange(N, dtype=float) * config.geometry.rung.pitch
    Q_oil_total = float((P_oil[0] - P_oil[1]) / R_OMc + Q_rungs[0])

    return SimResult(
        P_oil=P_oil,
        P_water=P_water,
        Q_rungs=np.asarray(Q_rungs, dtype=float),
        x_positions=x_pos,
        Q_oil_total=Q_oil_total,
        Q_water_total=float(Qw_m3s),
        Po_in_Pa=float(Po_Pa),
        Qw_in_m3s=float(Qw_m3s),
        P_out_Pa=float(P_out_Pa),
    )


def simulate(
    config: "DeviceConfig",
    Po_in_mbar: float | None = None,
    Qw_in_mlhr: float | None = None,
    P_out_mbar: float | None = None,
) -> SimResult:
    """
    Mixed boundary-condition simulation.

    Oil inlet is pressure-controlled; water inlet is flow-controlled; both
    channel outlets share a common pressure reference P_out (default 0).

    Parameters default to ``config.operating`` values when not supplied.
    """
    Po   = config.operating.Po_in_mbar  if Po_in_mbar is None else Po_in_mbar
    Qw   = config.operating.Qw_in_mlhr  if Qw_in_mlhr is None else Qw_in_mlhr
    Pout = config.operating.P_out_mbar  if P_out_mbar is None else P_out_mbar
    return _simulate_pa(config, mbar_to_pa(Po), mlhr_to_m3s(Qw), mbar_to_pa(Pout))
