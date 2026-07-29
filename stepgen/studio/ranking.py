"""
stepgen.studio.ranking
======================
The decide layer — turn a scored table into a decision.

A study rarely has one goal.  Ranking by a single metric hides the finding that
matters most: *the flattest design is usually not the highest-throughput one*.
So a study declares several **value axes**, and the output is a decision panel
rather than a winner (PRD_studio_v1.md §5):

    per-axis winners   "flattest? highest throughput? lowest drive pressure?"
    Pareto set         "which designs aren't beaten on everything by something else?"
    all-round pick     weighted composite — weights explicit and recorded
    safest pick        best confidence-discounted margin from failure

Weights are never hidden.  A composite whose weights are invisible is a worse
tool than no composite at all, so the weights travel with the result into the
chapter and are live-adjustable in the UI.  Per-axis winners are always
reported, even when a composite was requested.

Study schema
------------
    decide:
      axes: [flatness, throughput, drive_pressure, margin]
      weights: { flatness: 0.4, throughput: 0.3, drive_pressure: 0.2, margin: 0.1 }

``goal: flatness`` keeps working as a one-axis shorthand.

Eligibility
-----------
Red rows are excluded from selection whenever any non-red row exists — "best
throughput" should not name a device that cannot be built.  If every row is red
the whole set is ranked and :attr:`Decision.all_red` says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

from stepgen.studio.scoring import RED, ScoredRow


# ---------------------------------------------------------------------------
# Value axes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValueAxis:
    """One dimension a user might optimise for."""

    key: str
    source: str          # attribute name on CommonMetrics, or on ScoredRow
    higher_better: bool
    label: str
    unit: str = ""
    on_row: bool = False   # read from the ScoredRow itself, not its metrics


#: The registry.  Adding an axis here makes it available to every study.
AXES: dict[str, ValueAxis] = {
    "flatness": ValueAxis(
        "flatness", "uniformity_pct", False, "Flatness (ΔP spread)", "%"),
    "throughput": ValueAxis(
        "throughput", "throughput_mlhr", True, "Throughput", " mL/hr"),
    "drive_pressure": ValueAxis(
        "drive_pressure", "operating_Po_mbar", False, "Drive pressure", " mbar"),
    "area": ValueAxis(
        "area", "area_used_cm2", False, "Area used", " cm²"),
    "droplet_um": ValueAxis(
        "droplet_um", "droplet_um", True, "Droplet diameter", " µm"),
    "margin": ValueAxis(
        "margin", "min_margin_discounted", True,
        "Margin from failure (confidence-discounted)", "", on_row=True),
}

#: ``goal:`` shorthand -> axis key, for configs written before ``decide:``.
_GOAL_ALIASES = {
    "flatness": "flatness",
    "throughput": "throughput",
    "pressure": "drive_pressure",
    "drive_pressure": "drive_pressure",
    "area": "area",
    "margin": "margin",
    "safest": "margin",
}

DEFAULT_AXES = ["flatness", "throughput", "drive_pressure", "margin"]


def resolve_axes(spec: dict[str, Any] | None, goal: str = "") -> list[ValueAxis]:
    """
    Work out which axes a study is deciding on.

    Precedence: an explicit ``decide.axes`` block, else the ``goal:`` shorthand
    as a single axis, else :data:`DEFAULT_AXES`.
    """
    names: Sequence[str]
    if spec and spec.get("axes"):
        names = list(spec["axes"])
    elif goal:
        alias = _GOAL_ALIASES.get(goal.strip().lower())
        names = [alias] if alias else DEFAULT_AXES
    else:
        names = DEFAULT_AXES

    axes: list[ValueAxis] = []
    for name in names:
        axis = AXES.get(str(name).strip().lower())
        if axis is None:
            known = ", ".join(sorted(AXES))
            raise KeyError(f"unknown value axis '{name}'; known axes: {known}")
        if axis not in axes:
            axes.append(axis)
    return axes


def resolve_weights(
    spec: dict[str, Any] | None, axes: Sequence[ValueAxis]
) -> dict[str, float]:
    """
    Normalised composite weights, one per axis, summing to 1.

    Unstated axes get an equal share of whatever the stated ones leave; if
    nothing is stated the composite is a flat average.
    """
    raw = dict((spec or {}).get("weights", {}) or {})
    given = {a.key: float(raw[a.key]) for a in axes if a.key in raw}
    total = sum(given.values())

    if not given:
        return {a.key: 1.0 / len(axes) for a in axes} if axes else {}

    missing = [a.key for a in axes if a.key not in given]
    if missing:
        # share out the remainder; if the stated weights already sum to >= 1,
        # fall back to an equal share so an unstated axis is never zero-weighted
        # by accident.
        remainder = max(0.0, 1.0 - total)
        share = remainder / len(missing) if remainder > 0 else 1.0 / len(axes)
        for key in missing:
            given[key] = share
        total = sum(given.values())

    return {k: v / total for k, v in given.items()} if total > 0 else \
        {a.key: 1.0 / len(axes) for a in axes}


def axis_value(row: ScoredRow, axis: ValueAxis) -> float | None:
    """This row's value on *axis*, or ``None`` if the family cannot compute it."""
    source = row if axis.on_row else row.metrics
    value = getattr(source, axis.source, None)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(value) else value


def _oriented(row: ScoredRow, axis: ValueAxis) -> float | None:
    """Axis value flipped so that larger is always better."""
    value = axis_value(row, axis)
    return None if value is None else (value if axis.higher_better else -value)


# ---------------------------------------------------------------------------
# Pareto
# ---------------------------------------------------------------------------

def pareto_mask(points: np.ndarray) -> np.ndarray:
    """
    Boolean mask of the Pareto-non-dominated rows of *points*.

    ``points`` is ``(n_rows, n_axes)`` and **every column is maximised** — the
    caller orients its axes first.  A row is dominated when another is at least
    as good on every axis and strictly better on one.

    This generalises the two-axis ``_pareto_front`` that the legacy sweep path
    used; ``viz.plots._pareto_front`` now delegates here so there is one
    implementation of the rule.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    n = len(pts)
    dominated = np.zeros(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j or dominated[i]:
                continue
            if np.all(pts[j] >= pts[i]) and np.any(pts[j] > pts[i]):
                dominated[i] = True
    return ~dominated


def pareto_indices(
    rows: Sequence[ScoredRow],
    axes: Sequence[ValueAxis],
    candidates: Iterable[int] | None = None,
) -> list[int]:
    """
    Indices (into *rows*) of the non-dominated designs across *axes*.

    Rows missing a value on any axis are excluded: a design that cannot be
    compared on one of the declared dimensions cannot honestly be called
    non-dominated on all of them (DR-4 — grey means grey).
    """
    idx = list(range(len(rows))) if candidates is None else list(candidates)
    if not idx or not axes:
        return []

    usable, vectors = [], []
    for i in idx:
        vec = [_oriented(rows[i], a) for a in axes]
        if any(v is None for v in vec):
            continue
        usable.append(i)
        vectors.append(vec)

    if not usable:
        return []
    mask = pareto_mask(np.array(vectors, dtype=float))
    return [i for i, keep in zip(usable, mask) if keep]


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

def composite_scores(
    rows: Sequence[ScoredRow],
    axes: Sequence[ValueAxis],
    weights: dict[str, float],
    candidates: Iterable[int] | None = None,
) -> dict[int, float]:
    """
    Weighted composite in [0, 1], min-max normalised per axis over *candidates*.

    Normalisation is relative to the candidate set, so a composite score is only
    ever meaningful *within* one study — it is a convenience for ordering, not a
    number to quote or compare across chapters.

    A row missing an axis is not given a substitute value; its weights are
    renormalised over the axes it does have.
    """
    idx = list(range(len(rows))) if candidates is None else list(candidates)
    if not idx or not axes:
        return {}

    # per-axis min/max over the candidate set (oriented so larger = better)
    spans: dict[str, tuple[float, float]] = {}
    for axis in axes:
        vals = [v for v in (_oriented(rows[i], axis) for i in idx) if v is not None]
        if vals:
            spans[axis.key] = (min(vals), max(vals))

    scores: dict[int, float] = {}
    for i in idx:
        total = 0.0
        used = 0.0
        for axis in axes:
            span = spans.get(axis.key)
            value = _oriented(rows[i], axis)
            if span is None or value is None:
                continue
            lo, hi = span
            unit = 1.0 if hi == lo else (value - lo) / (hi - lo)
            w = weights.get(axis.key, 0.0)
            total += w * unit
            used += w
        scores[i] = total / used if used > 0 else 0.0
    return scores


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    """Everything the decide layer concluded about one scored table."""

    axes: list[ValueAxis]
    weights: dict[str, float]
    candidates: list[int]                      # rows eligible for selection
    all_red: bool                              # nothing was buildable
    per_axis: dict[str, int | None]            # axis key -> winning row index
    pareto: list[int]
    composite: dict[int, float]
    all_round: int | None
    safest: int | None
    caveats: list[str] = field(default_factory=list)   # breaches shared by every row

    def winner_labels(self, rows: Sequence[ScoredRow]) -> dict[str, str]:
        """Axis key -> winning row label, for display."""
        return {k: rows[i].metrics.label
                for k, i in self.per_axis.items() if i is not None}

    def is_conflicted(self) -> bool:
        """True when the axes genuinely disagree about the best design."""
        picks = {i for i in self.per_axis.values() if i is not None}
        return len(picks) > 1


def decide(
    rows: Sequence[ScoredRow],
    spec: dict[str, Any] | None = None,
    goal: str = "",
    weights_override: dict[str, float] | None = None,
) -> Decision:
    """
    Rank a scored table: per-axis winners, Pareto set, all-round and safest picks.

    *spec* is the study's ``decide:`` block; *goal* the legacy one-word shorthand.
    *weights_override* lets the UI re-rank live without re-solving.
    """
    axes = resolve_axes(spec, goal)
    weights = dict(weights_override) if weights_override else resolve_weights(spec, axes)
    # a live override may be unnormalised (sliders); make it sum to 1
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    # ── eligibility: prefer buildable designs ───────────────────────────────
    viable = [i for i, r in enumerate(rows) if r.overall != RED]
    all_red = not viable and bool(rows)
    candidates = viable if viable else list(range(len(rows)))

    # ── per-axis winners ────────────────────────────────────────────────────
    per_axis: dict[str, int | None] = {}
    for axis in axes:
        scored = [(i, _oriented(rows[i], axis)) for i in candidates]
        scored = [(i, v) for i, v in scored if v is not None]
        per_axis[axis.key] = max(scored, key=lambda t: t[1])[0] if scored else None

    # ── Pareto, composite, safest ───────────────────────────────────────────
    pareto = pareto_indices(rows, axes, candidates)
    composite = composite_scores(rows, axes, weights, candidates)
    all_round = max(composite, key=lambda i: composite[i]) if composite else None

    safe = [(i, rows[i].min_margin_discounted) for i in candidates]
    safe = [(i, m) for i, m in safe if m is not None]
    safest = max(safe, key=lambda t: t[1])[0] if safe else None

    return Decision(
        axes=list(axes),
        weights=weights,
        candidates=candidates,
        all_red=all_red,
        per_axis=per_axis,
        pareto=pareto,
        composite=composite,
        all_round=all_round,
        safest=safest,
        caveats=shared_caveats(rows),
    )


def shared_caveats(rows: Sequence[ScoredRow]) -> list[str]:
    """
    Validity breaches that every row shares.

    These are properties of the *study* — the fluid system's viscosity ratio,
    say — not of any one design, so they belong in a standing caveat rather than
    as a per-row discriminator.  Reporting them per row would make every row
    orange for the same reason and drown the breaches that actually distinguish
    one design from another.
    """
    if not rows:
        return []
    sets = []
    for row in rows:
        cell = row.cells.get("validity")
        if cell is None or cell.category == "grey":
            return []          # not every row was checked; nothing is universal
        sets.append(set(cell.detail))
    common = set.intersection(*sets) if sets else set()
    return sorted(common)


def row_specific_breaches(row: ScoredRow, caveats: Sequence[str]) -> list[str]:
    """The validity breaches of *row* that are not study-wide — what sets it apart."""
    cell = row.cells.get("validity")
    if cell is None:
        return []
    shared = set(caveats)
    return [b for b in cell.detail if b not in shared]


def best_indices(
    rows: Sequence[ScoredRow],
    spec: dict[str, Any] | None = None,
    goal: str = "",
    n: int = 3,
) -> list[int]:
    """
    The top *n* rows by composite score — the highlight set for plots.

    Replaces the old ``(verdict, one metric)`` two-tuple sort while keeping the
    same contract, so existing callers get multi-axis ranking for free.
    """
    decision = decide(rows, spec, goal)
    if not decision.composite:
        return []
    order = sorted(decision.composite, key=lambda i: -decision.composite[i])
    return order[:n]
