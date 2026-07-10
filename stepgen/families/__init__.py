"""
stepgen.families
================
Topology (design-style) families behind a common contract.

A "design style" (serpentine, radial, manifold) is a *different hydraulic
model*, not just a config value.  Each family implements the :class:`Family`
interface and fills the shared :class:`CommonMetrics` contract so that
different topologies can be scored and compared side by side.

The working serpentine solver is untouched; families layer on top of it.

Public API
----------
    from stepgen.families import get_family, list_families, CommonMetrics

Currently registered families:
    serpentine   — wraps the existing ladder solve + serpentine layout.
    radial       — analytic radial ("wheel") array with §11 L_eff/hub corrections.
    manifold     — comb (tapped-ladder) array on a general sparse nodal solver.
"""

from __future__ import annotations

from stepgen.families.base import (
    CommonMetrics,
    Family,
    get_family,
    list_families,
    register_family,
)

# Import concrete families for their registration side effects.
from stepgen.families import serpentine as _serpentine  # noqa: F401
from stepgen.families import radial as _radial  # noqa: F401
from stepgen.families import manifold as _manifold  # noqa: F401

__all__ = [
    "CommonMetrics",
    "Family",
    "get_family",
    "list_families",
    "register_family",
]
