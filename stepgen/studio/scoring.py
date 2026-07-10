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

The overall verdict is the worst category across all applicable metrics, with
a list of *reason chips* explaining every non-green.

Scoring block semantics
------------------------
    <metric>: { green: X, orange: Y, higher_better: <bool> }

``higher_better: true``  -> value >= green is green, >= orange is orange, else red.
otherwise (lower is better) -> value <= green is green, <= orange is orange, else red.

    build: { from: manufacturing, fits_square: required, no_crossing: required }
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from stepgen.families.base import CommonMetrics

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


@dataclass
class CellScore:
    """The verdict for one metric of one row."""
    key: str
    value: float | None
    category: str          # green | orange | red | grey
    reason: str = ""       # chip text when not green


@dataclass
class ScoredRow:
    """A CommonMetrics plus its per-metric verdicts and overall category."""
    metrics: CommonMetrics
    cells: dict[str, CellScore]
    overall: str
    chips: list[str] = field(default_factory=list)


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


def score_metrics(
    cm: CommonMetrics,
    scoring: dict[str, Any],
    applicable: set[str],
) -> ScoredRow:
    """Score one :class:`CommonMetrics` against the study's scoring block."""
    cells: dict[str, CellScore] = {}
    chips: list[str] = []

    if cm.error:
        # a failed solve is red with the error as its only chip
        return ScoredRow(metrics=cm, cells={}, overall=RED, chips=[f"error: {cm.error}"])

    # ── per-metric threshold scoring ────────────────────────────────────────
    for key, (attr, label, unit) in _METRIC_FIELDS.items():
        spec = scoring.get(key)
        value = _num(getattr(cm, attr, None))
        if spec is None or key not in applicable or value is None:
            cells[key] = CellScore(key, value, GREY,
                                   "N-A" if value is None else "")
            continue
        cat = _score_threshold(value, spec)
        reason = ""
        if cat != GREEN:
            higher = spec.get("higher_better", False)
            bound = spec["orange"] if cat == RED else spec["green"]
            arrow = "≥" if higher else "≤"
            reason = f"{label} {value:.3g}{unit} (want {arrow}{bound}{unit})"
            chips.append(("⚠ " if cat == ORANGE else "🔴 ") + reason)
        cells[key] = CellScore(key, value, cat, reason)

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
            applicable = get_family(cm.family).applicable_metrics()
        except KeyError:
            applicable = set()
        scored.append(score_metrics(cm, scoring, applicable))
    return scored
