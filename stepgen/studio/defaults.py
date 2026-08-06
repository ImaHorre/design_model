"""
stepgen.studio.defaults
=======================
House defaults for the Studio front door (plan C3).

The values live in ``configs/studio_defaults.yaml`` — a checked-in, reviewable
file — rather than in this module, so "what did we assume?" has something to
point at that shows up in a diff.  This module only loads them and turns the
measured solve costs into a runtime estimate.

Nothing here scores, gates or feeds physics.  The costs are wall-clock numbers
from one machine, used to put a figure on the form before a run is paid for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

#: Shipped defaults, relative to the repo root.
DEFAULTS_PATH = Path(__file__).resolve().parents[2] / "configs" / "studio_defaults.yaml"


@dataclass(frozen=True)
class SolveCost:
    """What one point of a given family costs to solve."""

    us_per_element: float
    ms_per_point: float
    reference_elements: int

    def seconds(self, n_points: int, elements: int | None = None) -> float:
        """
        Estimated seconds for *n_points* of this family.

        *elements* is the per-point element count — rungs for serpentine, nodes
        for manifold.  When it is None the flat ``ms_per_point`` is used, which
        is only right at ``reference_elements``: serpentine spans 3.5 ms at 83
        rungs to 106 ms at 2666, so a flat rate is a placeholder, not an answer.
        """
        if elements is None or self.us_per_element <= 0.0:
            return n_points * self.ms_per_point / 1000.0
        return n_points * elements * self.us_per_element / 1e6


@dataclass(frozen=True)
class StudioDefaults:
    """Parsed ``studio_defaults.yaml``."""

    sweep_defaults: dict[str, Any]
    solve_cost: dict[str, SolveCost]
    extras: dict[str, Any]
    source_path: str | None = None
    source_text: str | None = None

    def cost_for(self, family: str) -> SolveCost:
        """The cost entry for *family*, falling back to ``default``."""
        return self.solve_cost.get(family) or self.solve_cost["default"]

    def estimate_seconds(
        self,
        per_family: Mapping[str, int],
        elements: Mapping[str, int] | None = None,
    ) -> float:
        """
        Estimated wall-clock seconds for a study.

        Parameters
        ----------
        per_family : {family: n_points}
        elements   : optional {family: elements per point}; without it each
                     family uses its flat reference rate.
        """
        elements = elements or {}
        return sum(
            self.cost_for(fam).seconds(n, elements.get(fam))
            for fam, n in per_family.items()
        )


def _parse_costs(raw: Mapping[str, Any]) -> dict[str, SolveCost]:
    costs: dict[str, SolveCost] = {}
    for name, entry in (raw or {}).items():
        costs[name] = SolveCost(
            us_per_element=float(entry.get("us_per_element", 0.0)),
            ms_per_point=float(entry.get("ms_per_point", 0.0)),
            reference_elements=int(entry.get("reference_elements", 0)),
        )
    # A missing `default` would turn cost_for() into a KeyError on any
    # unrecognised family, which is a silly way for a preview to fail.
    costs.setdefault("default", SolveCost(36.0, 12.1, 333))
    return costs


def load_defaults(path: str | Path | None = None) -> StudioDefaults:
    """Load ``studio_defaults.yaml`` (the shipped one unless *path* is given)."""
    target = Path(path) if path is not None else DEFAULTS_PATH
    text = target.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    return StudioDefaults(
        sweep_defaults=raw.get("sweep_defaults", {}) or {},
        solve_cost=_parse_costs(raw.get("solve_cost", {})),
        extras=raw.get("extras", {}) or {},
        source_path=str(target),
        source_text=text,
    )
