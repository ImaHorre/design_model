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
    metric_confidence(cm) how far each metric of a row can be trusted
    grid_from_intent(...) a droplet/throughput target -> this family's geometry
                          block (leaves may be lists = swept axes)
    render_schematic(...) compiled config -> a to-scale drawing (Phase 3)
    packing_capacity(...) compiled config -> how many DFUs the die actually holds

`evaluate()` is a convenience that chains compile + solve.

Registry
--------
    register_family(fam)      register an instance
    get_family("serpentine")  look one up
    list_families()           names of all registered families
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any

from stepgen.families.intent import Constraints, Intent, IntentNotSupported


# ---------------------------------------------------------------------------
# The shared, comparable contract
# ---------------------------------------------------------------------------

# The scoring keys that a family may declare applicable.  ``build`` and
# ``validity`` are composite gates: ``build`` over fits_square / manufacturable /
# no_crossing, ``validity`` over the model-envelope checks (see below).
SCORING_KEYS: frozenset[str] = frozenset({
    "throughput_mlhr",
    "uniformity_pct",
    "operating_Po_mbar",
    "regime_Ca",
    "hub_budget_pct",
    "build",
    "validity",
})


# ---------------------------------------------------------------------------
# Model-confidence tiers
# ---------------------------------------------------------------------------
# How much a given number deserves to be trusted.  Margin is discounted by the
# tier, so a generous margin on an extrapolated quantity is not mistaken for
# reassurance (PRD_studio_v1.md §6).
VALIDATED = "validated"          # compared against experiment, agreement established
CALIBRATED = "calibrated"        # empirical fit, evaluated in range
EXTRAPOLATION = "extrapolation"  # model runs, but outside where it has been checked

#: multiplier applied to a metric's margin when ranking by safety
CONFIDENCE_WEIGHT: dict[str, float] = {
    VALIDATED: 1.0,
    CALIBRATED: 0.7,
    EXTRAPOLATION: 0.4,
}

#: exit depth [µm] above which the droplet power-law is being extrapolated.
#: The fit is calibrated at h = 1/5/10 µm (see DropletModelConfig); beyond ~2x
#: the deepest calibration point the size and frequency are not trusted.
DROPLET_FIT_DEPTH_UM = 12.0

#: exit Ca above which the device is out of step-emulsification and the
#: geometry-set droplet size no longer holds.  0.03 is the axisymmetric
#: SE->balloon ceiling (@chakraborty2017-step-emulsification); the rectangular
#: threshold is lower still, ~0.0125 (@montessori2020-step-emulsification).
SE_CEILING_CA = 0.03

#: The highest exit Ca **Peak has ever measured** on its own devices.
#:
#: Computed 2026-07-29 from the V5-8-1 Po sweep (@ws-2026-07-13-po-sweep-v5-8-1,
#: `experimental_workspaces/po_sweep/data/stage_timings.csv`): per-DFU flow from
#: droplet volume over measured cycle time, through the 30x10 µm exit, at
#: µ = 0.06 Pa·s and γ = 5 mN/m.  Droplet size was flat (24.8-25.6 µm, CV ~3%)
#: across the whole sweep, so this is a *lower bound* on the SE ceiling: we know
#: SE holds up to here and have no measurement above it.
#:
#: The number matters because of how far it is from the thresholds we score
#: against: 0.0017 is **7x below** the 0.0125 green bound and 18x below the 0.03
#: red bound.  Taking γ = 15 mN/m instead drops it to 0.0005 (27x below).  On
#: every assumption, Peak has never operated within an order of magnitude of its
#: own SE ceiling — the ceiling is entirely borrowed from literature at λ ≈ 1
#: while we run at λ ≈ 0.015.  See wiki open-questions/deep-dfu-se-regime.
#:
#: Consequence for scoring: a Ca *below* the SE ceiling but *above* this is not
#: "calibrated", it is unmeasured. metric_confidence() grades it accordingly.
CA_MEASURED_MAX = 0.0017


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

    # ── cycle / pressure diagnostics (2026-08-03) ───────────────────────────
    # All three derive from the one network rung flow Q, so they cannot disagree
    # with each other or with throughput.  See stage1_physics for the validation.
    dP_rung_mbar: float | None = None       # mean ΔP across an active rung [mbar]
    t_stage1_s: float | None = None         # meniscus reset → junction edge [s]
    t_cycle_s: float | None = None          # full droplet cycle, V_drop/Q [s]
    stage1_fraction: float | None = None    # t_S1/t_cycle = V_reset/V_drop (geometric)
    #: lowest Po at which every DFU produces [mbar]; None unless explicitly computed
    #: (needs a Po scan — see serpentine.production_threshold_mbar)
    Po_min_production_mbar: float | None = None
    regime_Ca: float | None = None          # exit capillary number (diagnostic)
    hub_budget_pct: float | None = None     # radial: hub ΔP as % of supply (lower=better; N-A elsewhere)
    area_used_cm2: float | None = None      # occupied chip area [cm²]
    fits_square: bool | None = None         # fits the die/wafer square?
    manufacturable: bool | None = None      # within fab caps (depth/width/wall)?
    no_crossing: bool | None = None         # continuous never crosses dispersed?

    # ── model-envelope inputs (feed the `validity` gate; see scoring.py) ─────
    exit_width_um: float | None = None      # junction exit width [µm]
    exit_depth_um: float | None = None      # junction exit depth [µm]
    lambda_visc: float | None = None        # µ_continuous / µ_dispersed
    #: the γ this row's ``regime_Ca`` was computed at [N/m].  Carried per row,
    #: not read from the study, because a study may hold several fluid systems
    #: with different interfacial tensions — and since Ca ∝ 1/γ exactly, the
    #: γ-robustness of a Ca verdict is meaningless against the wrong γ.
    gamma_Nm: float | None = None
    phase_system: str | None = None         # "o/w" / "w/o" — which phase is dispersed

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

    def metric_confidence(self, cm: "CommonMetrics") -> dict[str, str]:
        """
        How far each metric of *this row* can be trusted.

        Returns ``{scoring_key: tier}`` over :data:`VALIDATED` /
        :data:`CALIBRATED` / :data:`EXTRAPOLATION`.  The judgement is
        row-dependent, not merely family-dependent: the same family produces a
        validated throughput at a 10 µm exit and an extrapolated one at 50 µm,
        because Stage-2 formation frequency for deep exits is not modelled and
        the hydraulic number therefore becomes an upper bound.

        This default encodes the shared v3 position (PRD_studio_v1.md §6);
        families override to sharpen it for their own topology.
        """
        deep = (cm.exit_depth_um or 0.0) > DROPLET_FIT_DEPTH_UM
        ca = cm.regime_Ca or 0.0
        # Two different questions. "Is this still step-emulsification?" is the
        # SE ceiling. "Have we ever *been* here?" is the measured envelope, and
        # it is the one that governs how much a number deserves to be trusted.
        measured = ca <= CA_MEASURED_MAX

        return {
            # Stage-1 refill hydraulics and the ΔP distribution across the
            # ladder are what the po_sweep work actually checked.
            "operating_Po_mbar": VALIDATED,
            "uniformity_pct": VALIDATED,
            # Oil delivery is Stage-1 (solid), but it only converts to
            # throughput if the DFU keeps up — unmodelled for deep exits.
            "throughput_mlhr": EXTRAPOLATION if deep else VALIDATED,
            # Ca is an analytic diagnostic. It is only CALIBRATED inside the
            # band Peak has actually operated in (Ca <= CA_MEASURED_MAX, where
            # the Po sweep showed flat droplet size). Above that it is an
            # extrapolation *whether or not* it is under the SE ceiling — the
            # ceiling itself is borrowed from λ ≈ 1 literature and has never
            # been approached on a Peak device.
            "regime_Ca": CALIBRATED if measured else EXTRAPOLATION,
            # Analytic Hele-Shaw hub drop — never checked against experiment.
            "hub_budget_pct": CALIBRATED,
        }

    def grid_from_intent(
        self,
        intent: Intent,
        constraints: Constraints,
        *,
        fluids: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate this family's geometry block from a target, not a grid.

        Returns the same dict shape the family's YAML sub-block has, except that
        any leaf may be a **list** — which the study expander then treats as a
        swept axis.  The family is the only thing that knows how to lay itself
        out for a given droplet size and pressure ceiling, so the inverse solve
        lives behind this contract rather than in the studio layer.

        Raise :class:`IntentNotSupported` if the family has no sensible answer;
        the intent layer reports which families it had to skip rather than
        inventing geometry on their behalf.
        """
        raise IntentNotSupported(
            f"family '{self.name}' cannot generate a grid from an intent; "
            f"write its geometry block explicitly"
        )

    # -- geometry rendering (Phase 3) --------------------------------------

    def render_schematic(self, compiled: Any, view: str = "device"):
        """
        Draw *this compiled design* to scale.

        Returns a :class:`stepgen.viz.schematic.Schematic`.  ``view`` is
        ``"device"`` (the whole die) or ``"zoom"`` (a few adjacent DFUs at true
        scale, with the junction dimensions called out).

        The argument is the **compiled** config — the very object ``solve()``
        consumes — and never the raw study params.  That is deliberate and is
        the one rule this method must keep: a drawing derived from the YAML
        instead would be a second packing model, free to disagree with the one
        that produced the numbers.  The manifold arm pitch was wrong by 10-20x
        and every derived metric still looked plausible; the drawing is only
        able to catch that class of error while it shares the solver's geometry.

        Anything drawn for legibility that the model does not actually compute
        must be declared in ``Schematic.inventions``, which is rendered under
        the picture.

        The default implementation is a deliberately crude, honest fallback
        built from the shared contract alone — see :meth:`_fallback_schematic`.
        A family that has not declared its topology gets a drawing that says so
        rather than one that invents a shape.
        """
        return self._fallback_schematic(compiled, view)

    def _fallback_schematic(self, compiled: Any, view: str = "device"):
        """
        The topology-agnostic fallback: die square, occupied-area block and the
        junction at true scale, explicitly labelled as topology-unknown.

        Everything here comes from fields every family fills, so any new family
        gets a partial drawing for free — and one that cannot mislead, because
        it draws no topology at all.
        """
        from stepgen.viz.schematic import Label, Rect, Schematic

        side = float(getattr(compiled, "square_side_m", 0.0) or 0.0)
        if not side:
            fp = getattr(compiled, "footprint", None)
            area = float(getattr(fp, "footprint_area_cm2", 0.0) or 0.0) * 1e-4
            side = math.sqrt(area) if area > 0 else 10e-3

        prims: list[Any] = []
        notes = [
            f"{self.name} has not declared a topology for the visualiser; "
            f"only the die square and the junction are drawn."
        ]

        if view == "zoom":
            w = float(getattr(compiled, "exit_width_m", 0.0) or 30e-6)
            h = float(getattr(compiled, "exit_depth_m", 0.0) or 10e-6)
            prims.append(Rect(0.0, 0.0, w, h, "exit", label="exit"))
            prims.append(Label(w / 2, -h, f"exit {w*1e6:.0f} x {h*1e6:.0f} µm"))
            return Schematic(
                family=self.name, view="zoom", prims=prims,
                extent=(-w * 0.5, -h * 2.0, w * 1.5, h * 2.0),
                title=f"{self.name} — junction (topology not declared)",
                notes=notes,
                inventions=["No topology declared: neighbouring DFUs are not drawn."],
            )

        prims.append(Rect(0.0, 0.0, side, side, "die", dashed=True))
        prims.append(Label(side / 2, side / 2, "topology not declared", size=1.2))
        return Schematic(
            family=self.name, view="device", prims=prims,
            extent=(0.0, 0.0, side, side),
            die_side_m=side,
            title=f"{self.name} — die outline only",
            notes=notes,
            inventions=["No topology declared: no channels are drawn."],
        )

    def packing_capacity(self, compiled: Any):
        """
        How many DFUs this footprint holds, versus how many are configured.

        Returns a :class:`stepgen.viz.schematic.PackingCapacity`, or ``None``
        where the family cannot answer.  This inverts the historical layout
        model, which only ever *checked* a written ``N`` against the die: it
        tells you what the area could hold, so enlarging the die visibly buys
        DFUs rather than merely turning a gate green.

        Layout is microseconds, so this is free to recompute on every redraw.
        """
        return None

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
