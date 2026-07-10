"""
stepgen.families.base
=====================
The topology-family contract.

Every design style fills the same comparable contract, :class:`CommonMetrics`,
so a scored table can put serpentine, radial and manifold rows next to each
other.  A family leaves *inapplicable* fields as ``None`` (rendered grey / N-A
by the scorer) — e.g. a radial array has no ΔP-uniformity axis because
flatness is automatic.

Interface (`Family`)
--------------------
    required_geometry()   which YAML sub-block the family reads (its name)
    compile(params, ...)  study params  -> family-native config object
    solve(compiled, op)   family-native config -> CommonMetrics
    applicable_metrics()  which scoring gates apply to this family

`evaluate()` is a convenience that chains compile + solve.

Registry
--------
    register_family(fam)      register an instance
    get_family("serpentine")  look one up
    list_families()           names of all registered families
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# The shared, comparable contract
# ---------------------------------------------------------------------------

# The scoring keys that a family may declare applicable.  ``build`` is a
# composite gate (fits_square / manufacturable / no_crossing).
SCORING_KEYS: frozenset[str] = frozenset({
    "throughput_mlhr",
    "uniformity_pct",
    "operating_Po_mbar",
    "regime_Ca",
    "hub_budget_pct",
    "build",
})


@dataclass
class CommonMetrics:
    """
    The shared contract every family fills for one design point.

    Comparable fields are populated where the family can compute them and left
    as ``None`` (N-A / grey) otherwise.  ``raw`` carries the full family-native
    result for the per-device drill-down; ``params`` carries the swept study
    parameters that produced this point.
    """

    family: str
    label: str
    params: dict[str, Any] = field(default_factory=dict)

    # ── comparable contract (None = N-A for this family) ────────────────────
    throughput_mlhr: float | None = None    # total dispersed-phase throughput
    N_dfu: int | None = None                # number of droplet-forming units
    droplet_um: float | None = None         # predicted droplet diameter [µm]
    frequency_hz: float | None = None       # mean droplet frequency [Hz]
    uniformity_pct: float | None = None     # ΔP spread across DFUs [%] (lower=flatter)
    operating_Po_mbar: float | None = None  # drive pressure [mbar]
    regime_Ca: float | None = None          # exit capillary number (diagnostic)
    hub_budget_pct: float | None = None     # radial: hub ΔP as % of supply (lower=better; N-A elsewhere)
    area_used_cm2: float | None = None      # occupied chip area [cm²]
    fits_square: bool | None = None         # fits the die/wafer square?
    manufacturable: bool | None = None      # within fab caps (depth/width/wall)?
    no_crossing: bool | None = None         # continuous never crosses dispersed?

    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_row(self) -> dict[str, Any]:
        """Flat dict for DataFrame / JSON (params flattened as ``p.<key>``)."""
        d = asdict(self)
        params = d.pop("params")
        raw = d.pop("raw")
        d.pop("notes")
        for k, v in params.items():
            d[f"p.{k}"] = v
        d["notes"] = "; ".join(self.notes)
        d["_raw"] = raw
        return d


# ---------------------------------------------------------------------------
# The family interface
# ---------------------------------------------------------------------------

class Family(ABC):
    """A topology (design-style) family behind the common contract."""

    #: unique family name (matches the YAML geometry sub-block it reads)
    name: str = ""

    def required_geometry(self) -> str:
        """Return the name of the YAML sub-block this family reads."""
        return self.name

    @abstractmethod
    def applicable_metrics(self) -> set[str]:
        """Return the subset of :data:`SCORING_KEYS` that apply to this family."""

    @abstractmethod
    def compile(
        self,
        params: dict[str, Any],
        *,
        fluids: dict[str, Any],
        footprint: dict[str, Any],
        manufacturing: dict[str, Any],
    ) -> Any:
        """Turn resolved study params into a family-native config object."""

    @abstractmethod
    def solve(
        self,
        compiled: Any,
        operating: dict[str, Any],
        *,
        params: dict[str, Any],
        label: str,
    ) -> CommonMetrics:
        """Solve the family-native config at an operating point -> CommonMetrics."""

    def evaluate(
        self,
        params: dict[str, Any],
        *,
        fluids: dict[str, Any],
        footprint: dict[str, Any],
        manufacturing: dict[str, Any],
        operating: dict[str, Any],
        label: str,
    ) -> CommonMetrics:
        """Convenience: compile then solve, wrapping failures into CommonMetrics."""
        try:
            compiled = self.compile(
                params,
                fluids=fluids,
                footprint=footprint,
                manufacturing=manufacturing,
            )
            return self.solve(compiled, operating, params=params, label=label)
        except Exception as exc:  # a single bad point must not kill the study
            return CommonMetrics(
                family=self.name,
                label=label,
                params=params,
                notes=[f"error: {exc}"],
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Family] = {}


def register_family(family):
    """
    Register a family under its ``name``.

    Usable as a class decorator (``@register_family``): when given a class it
    registers an instance and returns the class unchanged, so the class name
    stays bound.  When given an instance it registers it directly.
    """
    instance = family() if isinstance(family, type) else family
    if not instance.name:
        raise ValueError("Family must define a non-empty name")
    _REGISTRY[instance.name] = instance
    return family


def get_family(name: str) -> Family:
    """Look up a registered family by name."""
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"unknown family '{name}'; registered: {known}") from None


def list_families() -> list[str]:
    """Return the names of all registered families."""
    return sorted(_REGISTRY)
