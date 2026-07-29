"""
stepgen.studio.scoring
=====================
Declarative traffic-light scoring — **worst-category-wins**.

Each metric named in the study's ``scoring:`` block gets a green / orange / red
verdict from its thresholds.  A metric that a family cannot compute (value
``None``) or that the family does not declare applicable renders **grey (N-A)**
and is excluded from the overall verdict.

``build`` is a composite gate: ``fits_square`` / ``manufacturable`` /
``no_crossing`` are hard requirements — any required gate that fails forces the
row **red**.

``validity`` is the model-envelope gate: exit Ca against the step-emulsification
ceiling, viscosity ratio λ against the validated envelope, and exit geometry
against the range the droplet power-law was fitted over.  A point outside the
envelope is capped at **orange — never green**, because the model has not been
checked there.  It is never red on envelope grounds alone: being unvalidated is
not the same as being wrong.

The overall verdict is the worst category across all applicable metrics, with
a list of *reason chips* explaining every non-green.

Margin
------
Every graded cell also carries a **margin**: how far the value sits from the red
boundary, as a fraction of the green->red span (PRD_studio_v1.md §6).  1.0 is
exactly the green bound and 0.0 the red bound; values above 1.0 mean more than a
full span of headroom, which is how a comfortably-green row is told apart from a
barely-green one.  A row's
``min_margin`` is the weakest link across its applicable metrics, and
``min_margin_discounted`` weights each margin by the model-confidence tier of
that metric, so a generous margin on an extrapolated number does not read as
reassurance.  Sorting by the discounted margin gives "safest to try" directly.

Scoring block semantics
------------------------
    <metric>: { green: X, orange: Y, higher_better: <bool> }

``higher_better: true``  -> value >= green is green, >= orange is orange, else red.
otherwise (lower is better) -> value <= green is green, <= orange is orange, else red.

    build:    { from: manufacturing, fits_square: required, no_crossing: required }
    validity: { se_ceiling_Ca: 0.03, lambda_range: [0.1, 10.0],
                exit_depth_um_max: 12.0, aspect_ratio_range: [2.5, 3.0] }
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from stepgen.families.base import (
    CONFIDENCE_WEIGHT,
    DROPLET_FIT_DEPTH_UM,
    SE_CEILING_CA,
    VALIDATED,
    CommonMetrics,
)

GREEN, ORANGE, RED, GREY = "green", "orange", "red", "grey"
_RANK = {GREEN: 0, ORANGE: 1, RED: 2}   # for worst-of comparison (grey excluded)

# scoring key -> CommonMetrics attribute + human label + unit
_METRIC_FIELDS: dict[str, tuple[str, str, str]] = {
    "throughput_mlhr":   ("throughput_mlhr",   "Throughput", "mL/hr"),
    "uniformity_pct":    ("uniformity_pct",    "ΔP flatness", "%"),
    "operating_Po_mbar": ("operating_Po_mbar", "Drive pressure", "mbar"),
    "regime_Ca":         ("regime_Ca",         "Exit Ca", ""),
    "hub_budget_pct":    ("hub_budget_pct",    "Hub ΔP budget", "%"),
}


#: default envelope for the ``validity`` gate when the study does not state one.
#: λ range is the literature-validated band (SE sources sit at λ ≈ 1); we run at
#: λ ≈ 0.015, which *narrows* the SE window — see the wiki open question
#: `deep-dfu-se-regime`.  Aspect ratio is the junction range the droplet fit and
#: the design-search hard constraints were built around.
DEFAULT_VALIDITY: dict[str, Any] = {
    "se_ceiling_Ca": SE_CEILING_CA,
    "lambda_range": [0.1, 10.0],
    "exit_depth_um_max": DROPLET_FIT_DEPTH_UM,
    "aspect_ratio_range": [2.5, 3.0],
}


@dataclass
class CellScore:
    """The verdict for one metric of one row."""
    key: str
    value: float | None
    category: str            # green | orange | red | grey
    reason: str = ""         # chip text when not green
    margin: float | None = None    # distance from red as a fraction of the
                                   # green->red span; 1 = at the green bound,
                                   # 0 = at red, >1 = extra headroom
    confidence: str = VALIDATED    # validated | calibrated | extrapolation
    detail: list[str] = field(default_factory=list)   # one entry per envelope
                                   # breach, kept separate from the joined chip
                                   # so callers can tell study-wide caveats from
                                   # row-specific ones


@dataclass
class ScoredRow:
    """A CommonMetrics plus its per-metric verdicts and overall category."""
    metrics: CommonMetrics
    cells: dict[str, CellScore]
    overall: str
    chips: list[str] = field(default_factory=list)

    @property
    def graded_cells(self) -> list[CellScore]:
        """Cells that carry a real margin (grey / gate cells excluded)."""
        return [c for c in self.cells.values() if c.margin is not None]

    @property
    def min_margin(self) -> float | None:
        """The weakest link: smallest margin across applicable metrics."""
        margins = [c.margin for c in self.graded_cells]
        return min(margins) if margins else None

    @property
    def min_margin_discounted(self) -> float | None:
        """
        ``min_margin`` with each margin scaled by its model-confidence tier.

        This is the "safest to try" ordering: it refuses to be reassured by a
        wide margin on a number the model has not been checked against.
        """
        vals = [c.margin * CONFIDENCE_WEIGHT.get(c.confidence, 1.0)
                for c in self.graded_cells]
        return min(vals) if vals else None

    @property
    def weakest_metric(self) -> str | None:
        """Key of the metric holding the row's discounted margin down."""
        graded = self.graded_cells
        if not graded:
            return None
        return min(graded,
                   key=lambda c: c.margin * CONFIDENCE_WEIGHT.get(c.confidence, 1.0)).key

    @property
    def extrapolated_keys(self) -> list[str]:
        """Applicable metrics whose value rests on an extrapolation."""
        return sorted(c.key for c in self.cells.values()
                      if c.category != GREY and c.confidence == "extrapolation")


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _score_threshold(value: float, spec: dict[str, Any]) -> str:
    green = float(spec["green"])
    orange = float(spec["orange"])
    if spec.get("higher_better", False):
        if value >= green:
            return GREEN
        if value >= orange:
            return ORANGE
        return RED
    # lower is better
    if value <= green:
        return GREEN
    if value <= orange:
        return ORANGE
    return RED


def _margin(value: float, spec: dict[str, Any]) -> float:
    """
    Distance from the red boundary as a fraction of the green->red span.

    The red boundary is the ``orange`` bound (past it the cell is red); the span
    is ``|orange - green|``.  So the margin is exactly **1.0 at the green bound**
    and **0.0 at the red bound**.

    Floored at zero — once a design has failed, by how much stops mattering —
    but deliberately **not capped above**.  Capping at the green bound would
    give every green cell a margin of 1.0 and destroy the distinction this
    column exists to draw: a design sitting a hair inside green is not the same
    design as one sitting three spans clear of red, and if the model is slightly
    optimistic only the second one still works.  A margin of 1.6 reads as "a
    full green-to-red span of headroom, and a bit over half of another".

    Caveat, tracked as open question 2 in the Phase 1 roadmap: margins are only
    strictly comparable *across* metrics if the underlying thresholds are
    themselves commensurate.  Treat cross-metric comparison as indicative until
    that has been checked against a real study.
    """
    green = float(spec["green"])
    orange = float(spec["orange"])
    span = abs(orange - green)
    if span == 0:
        # degenerate thresholds: no gradient to report, so grade it binary
        return 1.0 if _score_threshold(value, spec) == GREEN else 0.0
    if spec.get("higher_better", False):
        frac = (value - orange) / span
    else:
        frac = (orange - value) / span
    return max(0.0, frac)


def _validity_breaches(cm: CommonMetrics, spec: dict[str, Any]) -> list[str]:
    """
    Envelope checks for the ``validity`` gate.

    Returns one plain-language string per breach — each says what is out of
    range and what the validated range is — or an empty list if the point sits
    inside everywhere the model has been checked.
    """
    breaches: list[str] = []

    ca_ceiling = _num(spec.get("se_ceiling_Ca", DEFAULT_VALIDITY["se_ceiling_Ca"]))
    ca = _num(cm.regime_Ca)
    if ca is not None and ca_ceiling is not None and ca > ca_ceiling:
        breaches.append(
            f"exit Ca {ca:.3g} is above the step-emulsification ceiling "
            f"{ca_ceiling:.4g} — droplet size is no longer geometry-set"
        )

    lam_range = spec.get("lambda_range", DEFAULT_VALIDITY["lambda_range"])
    lam = _num(cm.lambda_visc)
    if lam is not None and lam_range:
        lo, hi = float(lam_range[0]), float(lam_range[1])
        if not (lo <= lam <= hi):
            breaches.append(
                f"viscosity ratio λ {lam:.3g} is outside the validated envelope "
                f"{lo:g}–{hi:g} (SE literature sits at λ ≈ 1)"
            )

    depth_max = _num(spec.get("exit_depth_um_max", DEFAULT_VALIDITY["exit_depth_um_max"]))
    depth = _num(cm.exit_depth_um)
    if depth is not None and depth_max is not None and depth > depth_max:
        breaches.append(
            f"exit depth {depth:.3g} µm is beyond the droplet-fit range "
            f"(≤{depth_max:g} µm) — size and frequency extrapolated"
        )

    ar_range = spec.get("aspect_ratio_range", DEFAULT_VALIDITY["aspect_ratio_range"])
    w, h = _num(cm.exit_width_um), _num(cm.exit_depth_um)
    if ar_range and w is not None and h and h > 0:
        ar = w / h
        lo, hi = float(ar_range[0]), float(ar_range[1])
        if not (lo <= ar <= hi):
            breaches.append(
                f"exit aspect ratio {ar:.3g} is outside the fitted range {lo:g}–{hi:g}"
            )

    return breaches


def score_metrics(
    cm: CommonMetrics,
    scoring: dict[str, Any],
    applicable: set[str],
    confidence: dict[str, str] | None = None,
) -> ScoredRow:
    """Score one :class:`CommonMetrics` against the study's scoring block."""
    cells: dict[str, CellScore] = {}
    chips: list[str] = []
    confidence = confidence or {}

    if cm.error:
        # a failed solve is red with the error as its only chip
        return ScoredRow(metrics=cm, cells={}, overall=RED, chips=[f"error: {cm.error}"])

    # ── per-metric threshold scoring ────────────────────────────────────────
    for key, (attr, label, unit) in _METRIC_FIELDS.items():
        spec = scoring.get(key)
        value = _num(getattr(cm, attr, None))
        tier = confidence.get(key, VALIDATED)
        if spec is None or key not in applicable or value is None:
            cells[key] = CellScore(key, value, GREY,
                                   "N-A" if value is None else "",
                                   confidence=tier)
            continue
        cat = _score_threshold(value, spec)
        reason = ""
        if cat != GREEN:
            higher = spec.get("higher_better", False)
            bound = spec["orange"] if cat == RED else spec["green"]
            arrow = "≥" if higher else "≤"
            reason = f"{label} {value:.3g}{unit} (want {arrow}{bound}{unit})"
            chips.append(("⚠ " if cat == ORANGE else "🔴 ") + reason)
        cells[key] = CellScore(key, value, cat, reason,
                               margin=_margin(value, spec), confidence=tier)

    # ── build gate (fits_square / manufacturable / no_crossing) ─────────────
    build_spec = scoring.get("build", {}) or {}
    build_cat = GREEN
    if "build" in applicable:
        gate_map = {
            "fits_square": (cm.fits_square, "fits die square"),
            "manufacturable": (cm.manufacturable, "within fab caps"),
            "no_crossing": (cm.no_crossing, "no phase crossing"),
        }
        for gate_key, (val, human) in gate_map.items():
            required = build_spec.get(gate_key, None)
            # manufacturable is always evaluated when known; fits_square /
            # no_crossing only when the study marks them required.
            evaluate = (required == "required") or (gate_key == "manufacturable" and val is not None)
            if not evaluate or val is None:
                continue
            if val is False:
                build_cat = RED
                chips.append(f"🔴 {human} — no")
        cells["build"] = CellScore("build", None, build_cat,
                                   "" if build_cat == GREEN else "gate failed")
    else:
        cells["build"] = CellScore("build", None, GREY, "N-A")

    # ── validity gate: is the model even checked here? ──────────────────────
    # A breach caps the row at ORANGE and never makes it red — an unvalidated
    # prediction is not a failed one, but it must not be allowed to read green.
    if "validity" in applicable:
        vspec = scoring.get("validity")
        vspec = DEFAULT_VALIDITY if vspec is None else {**DEFAULT_VALIDITY, **vspec}
        breaches = _validity_breaches(cm, vspec)
        if breaches:
            cells["validity"] = CellScore(
                "validity", None, ORANGE,
                "extrapolation — model not validated here",
                confidence="extrapolation",
                detail=breaches,
            )
            chips.append("⚠ extrapolation — model not validated here: "
                         + "; ".join(breaches))
        else:
            cells["validity"] = CellScore("validity", None, GREEN, "")
    else:
        cells["validity"] = CellScore("validity", None, GREY, "N-A")

    # ── worst-category-wins ─────────────────────────────────────────────────
    graded = [c.category for c in cells.values() if c.category in _RANK]
    overall = GREEN if not graded else max(graded, key=lambda c: _RANK[c])

    return ScoredRow(metrics=cm, cells=cells, overall=overall, chips=chips)


def score_result(result, scoring: dict[str, Any]) -> list[ScoredRow]:
    """Score every row of a StudyResult (imports lazily to avoid cycles)."""
    from stepgen.families import get_family

    scored: list[ScoredRow] = []
    for cm in result.metrics:
        try:
            family = get_family(cm.family)
            applicable = family.applicable_metrics()
            confidence = family.metric_confidence(cm)
        except KeyError:
            applicable, confidence = set(), {}
        scored.append(score_metrics(cm, scoring, applicable, confidence))
    return scored
