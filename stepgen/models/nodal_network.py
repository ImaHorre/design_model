"""
stepgen.models.nodal_network
=============================
A general sparse resistive nodal-graph solver.

This generalizes the fixed serpentine ladder in :mod:`stepgen.models.hydraulics`
to an arbitrary resistor network: nodes are pressures, edges are hydraulic
resistances, and any node may be pinned to a fixed pressure (a supply inlet or a
drain/ground).  It is used by the ``manifold`` family to solve the comb
(tapped-ladder) oil-distribution network — a primary spine feeding parallel
arms, each arm feeding rungs to a shared continuous-phase reference.

The assembly recipe and the design rationale (why a comb, why not an H-tree)
were pinned by the ``comp_manifold_parametrization`` workspace, whose throwaway
prototype this module promotes to package quality.

Physics
-------
Steady incompressible flow through hydraulic resistances is exactly analogous to
a resistor network: pressure ↔ voltage, volumetric flow ↔ current,
``R = 12 µ L / (w h³ · corr)`` ↔ resistance.  KCL (flow conservation) at every
free node ``i``::

        Σ_j  (P_i − P_j) / R_ij  =  0

with Dirichlet (fixed-pressure) nodes replaced by identity rows.  The resulting
sparse linear system is solved with :func:`scipy.sparse.linalg.spsolve`.

Example
-------
>>> net = NodalNetwork()
>>> src = net.add_node(); a = net.add_node(); gnd = net.add_node()
>>> net.fix(src, 1000.0); net.fix(gnd, 0.0)
>>> e1 = net.add_edge(src, a, 2.0)
>>> e2 = net.add_edge(a, gnd, 3.0)
>>> P = net.solve()
>>> round(net.edge_flow(e1, P), 6) == round(net.edge_flow(e2, P), 6)  # series
True
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve


@dataclass
class NodalNetwork:
    """Sparse resistive network with Dirichlet (fixed-pressure) nodes.

    Nodes are integer ids from :meth:`add_node`.  Edges carry a hydraulic
    resistance ``R`` (parallel edges between the same pair simply add in
    conductance).  :meth:`fix` pins a node's pressure (supply or ground);
    :meth:`solve` returns the pressure at every node.
    """

    _edges: list[tuple[int, int, float]] = field(default_factory=list)  # (i, j, g)
    _fixed: dict[int, float] = field(default_factory=dict)
    _injections: dict[int, float] = field(default_factory=dict)          # node -> Q in [m³/s]
    _n: int = 0

    # -- construction ------------------------------------------------------
    def add_node(self) -> int:
        """Add a node and return its id."""
        i = self._n
        self._n += 1
        return i

    def add_edge(self, i: int, j: int, R: float) -> int:
        """Add a resistive edge of resistance ``R`` between nodes ``i`` and ``j``.

        Returns the edge index (usable with :meth:`edge_flow`).
        """
        if R <= 0:
            raise ValueError(f"edge resistance must be positive; got {R}")
        if not (0 <= i < self._n and 0 <= j < self._n):
            raise ValueError(f"edge ({i},{j}) references an unknown node")
        self._edges.append((i, j, 1.0 / R))
        return len(self._edges) - 1

    def fix(self, node: int, pressure: float) -> None:
        """Pin ``node`` to a fixed pressure (Dirichlet boundary)."""
        if not (0 <= node < self._n):
            raise ValueError(f"unknown node {node}")
        self._fixed[node] = float(pressure)

    def inject(self, node: int, Q: float) -> None:
        """Inject a fixed volumetric flow ``Q`` at ``node`` (Neumann boundary).

        Positive ``Q`` is flow **into** the node (a source, e.g. a flow-controlled
        inlet); it appears on the RHS of that node's KCL row.  Injection on a
        fixed (Dirichlet) node is ignored — a pinned pressure overrides it.
        Repeated calls accumulate.
        """
        if not (0 <= node < self._n):
            raise ValueError(f"unknown node {node}")
        self._injections[node] = self._injections.get(node, 0.0) + float(Q)

    # -- solve -------------------------------------------------------------
    def solve(self) -> np.ndarray:
        """Solve KCL for the pressure at every node → ndarray shape (n_nodes,)."""
        n = self._n
        if n == 0:
            return np.zeros(0)
        if not self._fixed:
            raise ValueError("network has no fixed node; system is singular")

        A = lil_matrix((n, n), dtype=float)
        b = np.zeros(n, dtype=float)

        # accumulate conductances for free nodes
        for (i, j, g) in self._edges:
            if i not in self._fixed:
                A[i, i] += g
                A[i, j] -= g
            if j not in self._fixed:
                A[j, j] += g
                A[j, i] -= g

        # Neumann injections: fixed inflow on a free node's KCL row (RHS)
        for node, Q in self._injections.items():
            if node not in self._fixed:
                b[node] += Q

        # Dirichlet rows overwrite whatever was accumulated
        for node, value in self._fixed.items():
            A.rows[node] = [node]
            A.data[node] = [1.0]
            b[node] = value

        return np.asarray(spsolve(A.tocsr(), b), dtype=float)

    # -- queries -----------------------------------------------------------
    def edge_flow(self, edge: int, pressures: np.ndarray) -> float:
        """Volumetric flow through ``edge`` given a solved pressure vector.

        Positive = flow from the edge's first node to its second.
        """
        i, j, g = self._edges[edge]
        return float((pressures[i] - pressures[j]) * g)

    @property
    def n_nodes(self) -> int:
        return self._n

    @property
    def n_edges(self) -> int:
        return len(self._edges)
