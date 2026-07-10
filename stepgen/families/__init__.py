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

(radial and manifold are planned; see the studio plan.)
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

__all__ = [
    "CommonMetrics",
    "Family",
    "get_family",
    "list_families",
    "register_family",
]
