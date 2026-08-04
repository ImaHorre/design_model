"""
stepgen.studio.levers
=====================
"Which way do I move this design, and what does it cost me?"

A scored table says which design won.  It does not say what to *do* next, and a
decision panel that names a winner without naming a direction leaves the reader
to reverse-engineer the physics from a scatter plot.  This module answers the
follow-up in two ways, and keeps them clearly apart:

**Measured levers** — read straight out of the study.  For every axis the study
actually swept inside a design (drive pressure, main length, fluid system), the
matched pairs of rows that differ *only* on that axis give the observed effect of
one notch on every metric being watched.  Nothing is modelled here beyond what
was already solved: if the study swept it, the number is the study's own.

**Structural levers** — for knobs the study did *not* sweep.  These come from the
model's own scaling structure and the ingested literature, are labelled as such,
and every one carries its cost.  A lever without a cost is marketing: widening a
rung raises throughput *and* flattens the ladder's advantage over the main,
deepening the exit raises throughput *and* grows the droplet, and both push exit
Ca toward a step-emulsification ceiling nobody has measured near
(`[[open-questions/deep-dfu-se-regime]]`).

Evidence labels follow the wiki convention: ``[model-v3]`` for a scaling that
falls out of the implemented physics, ``[theory]`` with a citekey for an ingested
literature result, ``[experimental]`` for a measurement.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Sequence

from stepgen.studio.grouping import Axis
from stepgen.studio.scoring import GREEN, ScoredRow


# ---------------------------------------------------------------------------
# What we watch when a lever moves
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Watch:
    """A metric whose response to a lever is worth reporting."""

    key: str                 # CommonMetrics attribute
    label: str
    better: int              # +1 higher is better, -1 lower is better, 0 neutral
    points: bool = False     # report as percentage points, not relative %
    scale: float = 1.0       # multiply the absolute delta before display
    unit: str = ""           # for the absolute-change fallback

    def direction(self, delta: float) -> str:
        """``better`` / ``worse`` / ``""`` for a change of *delta*."""
        if self.better == 0 or delta == 0:
            return ""
        improved = (delta > 0) if self.better > 0 else (delta < 0)
        return "better" if improved else "worse"


WATCHED: tuple[Watch, ...] = (
    Watch("throughput_mlhr", "Throughput", +1, unit="mL/hr"),
    Watch("min_margin_discounted", "Margin", +1, points=True, scale=100.0),
    Watch("uniformity_pct", "ΔP flatness", -1, points=True),
    Watch("operating_Po_mbar", "Drive pressure", -1, unit="mbar"),
    Watch("regime_Ca", "Exit Ca", -1),
    Watch("N_dfu", "N DFU", 0),
    Watch("droplet_um", "Droplet", 0, unit="µm"),
    Watch("area_used_cm2", "Area", -1, unit="cm²"),
)

_WATCH_BY_KEY = {w.key: w for w in WATCHED}

#: decide-axis key -> the metric it is measured on, so a lever can be pointed at
#: the axis a user says they care about.
OBJECTIVE_METRIC = {
    "throughput": "throughput_mlhr",
    "flatness": "uniformity_pct",
    "drive_pressure": "operating_Po_mbar",
    "area": "area_used_cm2",
    "droplet_um": "droplet_um",
    "margin": "min_margin_discounted",
}


def _value(row: ScoredRow, key: str) -> float | None:
    # margin lives on the scored row, every other watched number on its metrics
    v = getattr(row.metrics, key, None)
    if v is None:
        v = getattr(row, key, None)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


# ---------------------------------------------------------------------------
# Measured levers
# ---------------------------------------------------------------------------

@dataclass
class Effect:
    """How one metric responded to one lever step."""

    watch: Watch
    rel: float | None            # median relative change (fraction), None = no base
    delta: float                 # median absolute change, metric units
    n: int

    @property
    def direction(self) -> str:
        # rel and delta are medians of the same pairs, but rel drops pairs with
        # no usable baseline — so the sign that decides better/worse comes from
        # whichever of them the number on screen was rendered from.
        return self.watch.direction(self.rel if self.rel is not None else self.delta)

    def amount(self) -> str:
        """The bare change: ``+24%`` / ``×43`` / ``+18.0 pts``."""
        if self.watch.points:
            return f"{self.delta * self.watch.scale:+,.1f} pts"
        if self.rel is None:
            # no meaningful baseline (the metric started at ~0), so a percentage
            # would be an artefact of dividing by nothing — state the change
            return f"{self.delta:+,.3g} {self.watch.unit}".strip()
        if self.rel >= 5.0:
            return f"×{1.0 + self.rel:,.0f}"
        return f"{self.rel * 100:+,.0f}%"

    def text(self) -> str:
        """``Throughput +24%`` / ``ΔP flatness +18 pts``."""
        return f"{self.watch.label} {self.amount()}"


@dataclass
class LeverStep:
    """One notch of one swept axis, and everything it moved."""

    axis: Axis
    frm: Any
    to: Any
    n_pairs: int
    effects: dict[str, Effect] = field(default_factory=dict)
    green_before: int = 0
    green_after: int = 0
    pairs: list[tuple[int, int]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.axis.label} {self.axis.show(self.frm)} → {self.axis.show(self.to)}"

    def effect_on(self, metric_key: str) -> Effect | None:
        return self.effects.get(metric_key)


def reverse_step(rows: Sequence[ScoredRow], step: LeverStep) -> LeverStep:
    """
    The same lever pulled the other way, recomputed rather than negated.

    Relative changes are not symmetric — going from 4 to 8 is +100%, coming back
    is −50% — so a "shorten the main" recommendation built by flipping the sign
    of a "lengthen the main" number would be wrong by construction.  Every
    matched pair is simply re-read backwards.
    """
    rev = LeverStep(axis=step.axis, frm=step.to, to=step.frm, n_pairs=step.n_pairs,
                    pairs=[(b, a) for a, b in step.pairs])
    rev.effects = _effects(rows, rev.pairs)
    rev.green_before, rev.green_after = step.green_after, step.green_before
    return rev


def _match_key(leaves: dict[str, Any], axes: Sequence[Axis], skip: str) -> tuple:
    return tuple(leaves.get(a.path) for a in axes if a.path != skip)


def _effects(
    rows: Sequence[ScoredRow], pairs: Sequence[tuple[int, int]]
) -> dict[str, Effect]:
    """Median response of every watched metric over *pairs* of (before, after)."""
    out: dict[str, Effect] = {}
    for watch in WATCHED:
        rels, deltas = [], []
        for a, b in pairs:
            va, vb = _value(rows[a], watch.key), _value(rows[b], watch.key)
            if va is None or vb is None:
                continue
            deltas.append(vb - va)
            # A baseline of ~0 — a design below its production threshold — turns
            # a relative change into a division artefact (throughput "up 3e14
            # %"). Those pairs contribute their absolute change and nothing
            # else; with no usable baseline at all the step is reported in
            # metric units instead.
            if abs(va) > 1e-12 and abs(va) >= 1e-6 * abs(vb):
                rels.append((vb - va) / abs(va))
        if not deltas:
            continue
        out[watch.key] = Effect(
            watch=watch,
            rel=statistics.median(rels) if rels else None,
            delta=statistics.median(deltas),
            n=len(deltas),
        )
    return out


def measured_steps(
    rows: Sequence[ScoredRow],
    indices: Sequence[int],
    leaves_by_index: dict[int, dict[str, Any]],
    axis: Axis,
    all_axes: Sequence[Axis],
    *,
    mode: str = "adjacent",
) -> list[LeverStep]:
    """
    The observed effect of stepping *axis*, over matched pairs.

    Two rows form a pair when they agree on **every other** varying axis and
    differ only on this one.  Pairing rather than fitting keeps the statement
    causal in the one sense the study can support: nothing else moved.

    ``mode="adjacent"`` walks the notches; ``mode="span"`` reports the whole
    range as a single step, which is the headline a reader wants first.
    """
    if len(axis.values) < 2:
        return []

    buckets: dict[Any, dict[tuple, int]] = {v: {} for v in axis.values}
    for i in indices:
        leaves = leaves_by_index.get(i, {})
        value = leaves.get(axis.path)
        if value not in buckets:
            continue
        buckets[value][_match_key(leaves, all_axes, axis.path)] = i

    if mode == "span":
        wanted = [(axis.values[0], axis.values[-1])]
    else:
        wanted = list(zip(axis.values, axis.values[1:]))

    steps: list[LeverStep] = []
    for frm, to in wanted:
        shared = set(buckets[frm]) & set(buckets[to])
        if not shared:
            continue
        pairs = [(buckets[frm][k], buckets[to][k]) for k in shared]
        step = LeverStep(axis=axis, frm=frm, to=to, n_pairs=len(pairs), pairs=pairs)
        step.effects = _effects(rows, pairs)
        step.green_before = sum(1 for a, _ in pairs if rows[a].overall == GREEN)
        step.green_after = sum(1 for _, b in pairs if rows[b].overall == GREEN)
        steps.append(step)
    return steps


def measured_levers(
    rows: Sequence[ScoredRow],
    indices: Sequence[int],
    leaves_by_index: dict[int, dict[str, Any]],
    axes: Sequence[Axis],
    *,
    mode: str = "adjacent",
) -> list[LeverStep]:
    """Every step of every swept axis, for one design group."""
    out: list[LeverStep] = []
    for axis in axes:
        out.extend(measured_steps(rows, indices, leaves_by_index, axis, axes, mode=mode))
    return out


def best_step_for(
    steps: Sequence[LeverStep],
    metric_key: str,
    rows: Sequence[ScoredRow] | None = None,
) -> LeverStep | None:
    """
    The swept step that moves *metric_key* furthest in the good direction.

    Both directions of every lever are considered when *rows* is given: an axis
    whose forward step hurts the objective is a recommendation to move the other
    way, and reporting only the forward direction would leave "how do I get this
    flatter?" unanswered in a study that swept exactly the axis that answers it.

    A metric with no preferred direction (droplet size) falls back to the
    largest movement, which is still the useful answer.
    """
    watch = _WATCH_BY_KEY.get(metric_key)
    if watch is None:
        return None

    candidates = list(steps)
    if rows is not None:
        candidates += [reverse_step(rows, s) for s in steps if s.pairs]

    best, best_score = None, 0.0
    for step in candidates:
        eff = step.effect_on(metric_key)
        if eff is None or eff.delta == 0:
            continue
        helps = abs(eff.delta) if watch.better == 0 else eff.delta * watch.better
        if helps <= 0:
            continue
        size = abs(eff.rel) if eff.rel is not None else abs(eff.delta)
        if best is None or size > best_score:
            best, best_score = step, size
    return best


# ---------------------------------------------------------------------------
# Structural levers — knobs the study did not sweep
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StructuralLever:
    """A knob, which way to turn it for one objective, and what it costs."""

    objective: str            # decide-axis key
    knob: str                 # human name
    path: str                 # dotted study path, so "already swept" can be told
    move: str                 # "increase" / "decrease"
    mechanism: str            # why it works
    costs: tuple[str, ...]    # what it takes away — never empty
    evidence: str             # "[model-v3]" / "[theory] @citekey"

    @property
    def headline(self) -> str:
        arrow = "↑" if self.move == "increase" else "↓"
        return f"{arrow} {self.knob}"


#: The registry.  Every entry names a cost: a lever with no downside would
#: already be the default, and presenting one as free is how a design tool
#: starts lying.  Scalings marked [model-v3] fall out of the implemented
#: rectangular-duct resistance and the ladder solve; literature claims carry
#: their citekey and the wiki page that holds the evidence table.
STRUCTURAL: tuple[StructuralLever, ...] = (
    # ── throughput ──────────────────────────────────────────────────────────
    StructuralLever(
        "throughput", "Exit / rung depth", "junction.exit_depth_um", "increase",
        "Rung resistance scales as 1/h³, so depth is the steepest throughput knob "
        "there is — doubling it moves roughly 8× the oil at the same pressure.",
        ("Droplet diameter tracks depth (d ≈ 4h), so the product size changes with it "
         "[theory] @montessori2020-step-emulsification.",
         "Exit velocity rises with the extra flow, and exit Ca with it — this is the "
         "fastest route out of the step-emulsification regime.",
         "Beyond 12 µm the droplet power-law is extrapolated, so size and frequency "
         "become soft numbers while throughput stays sound."),
        "[model-v3] + [theory] @montessori2020-step-emulsification",
    ),
    StructuralLever(
        "throughput", "Rung width", "rung.upstream_width_um", "increase",
        "Rung resistance falls as 1/w, so a wider rung draws more oil at the same ΔP.",
        ("The ladder gets less flat: droop is set by main resistance *relative to* rung "
         "resistance, and lowering the rung's share hands the main more authority.",
         "The rectangular-duct correction is only trustworthy to h/w ≈ 0.8, so widening "
         "is what buys a deeper exit its validity, not a free gain on its own."),
        "[model-v3]",
    ),
    StructuralLever(
        "throughput", "Pitch", "junction.pitch_um", "decrease",
        "N is main length ÷ pitch, so a tighter pitch packs more DFUs into the same "
        "channel run and each one adds its rung flow.",
        ("Wall thickness between DFUs shrinks toward the fab minimum.",
         "More rungs on one main means more droop — the far end starves first."),
        "[model-v3]",
    ),
    StructuralLever(
        "throughput", "Rung length", "rung.length_mm", "decrease",
        "Rung resistance is linear in length; a shorter rung is a cheaper path for oil.",
        ("Same flatness cost as widening — the rung stops dominating the network.",
         "Layout: the DFU span is what the serpentine fold is built around."),
        "[model-v3]",
    ),
    # ── flatness ────────────────────────────────────────────────────────────
    StructuralLever(
        "flatness", "Main depth", "main.depth_um", "increase",
        "Main resistance scales as 1/(W·D³). Deepening the main flattens the ladder "
        "without touching a single DFU — the rungs keep their geometry and their "
        "droplet size, they just see a stiffer supply.",
        ("Etch depth is the fab cap most likely to bind; this is a process purchase, "
         "not a design change.",
         "Deeper mains hold more dead volume, which costs priming and flush time."),
        "[model-v3]",
    ),
    StructuralLever(
        "flatness", "Main width", "main.width_um", "increase",
        "Also lowers main resistance, by the same ladder argument as depth.",
        ("Width is charged to the footprint: a wider main is fewer parallel lanes on "
         "the same die, so it trades against DFU count directly.",),
        "[model-v3]",
    ),
    StructuralLever(
        "flatness", "Rung width", "rung.upstream_width_um", "decrease",
        "Raising rung resistance restores its authority over the network, so every "
        "DFU sees nearly the same ΔP regardless of where it sits on the main.",
        ("Throughput falls roughly in proportion — this is the throughput lever run "
         "backwards.",
         "Watch h/w: narrowing at fixed exit depth walks toward the h/w ≥ 1 region "
         "where the resistance correction is silently wrong."),
        "[model-v3]",
    ),
    StructuralLever(
        "flatness", "Main length / DFU count", "main.length_mm", "decrease",
        "Droop accumulates along the main, so a shorter ladder is a flatter one.",
        ("Throughput falls with the DFUs you remove.",
         "Per-DFU flow rises to hold total flow, which raises exit Ca — the flatness "
         "and regime levers pull against each other here."),
        "[model-v3] + [[open-questions/deep-dfu-se-regime]]",
    ),
    # ── drive pressure ──────────────────────────────────────────────────────
    StructuralLever(
        "drive_pressure", "Exit / rung depth", "junction.exit_depth_um", "increase",
        "The same 1/h³ that buys throughput buys pressure: a deeper rung reaches the "
        "target flow at a fraction of the drive.",
        ("Droplet size grows with depth — this only helps if the bigger droplet is "
         "acceptable [theory] @montessori2020-step-emulsification.",
         "Ca is set by exit velocity, not by pressure, so a lower Po at the same flow "
         "does not by itself buy regime margin."),
        "[model-v3]",
    ),
    StructuralLever(
        "drive_pressure", "DFU count", "main.length_mm", "increase",
        "More rungs in parallel means the target throughput is reached at lower ΔP per "
        "rung, so the whole device runs gentler.",
        ("Droop grows with N; past a point the far rungs stop producing and the extra "
         "DFUs are not paying their way.",
         "Area grows with the channel run."),
        "[model-v3]",
    ),
    # ── margin / staying in regime ──────────────────────────────────────────
    StructuralLever(
        "margin", "Drive pressure", "operating.Po_mbar", "decrease",
        "Exit Ca is proportional to exit velocity and therefore to drive pressure. "
        "Backing off pressure is the only lever that lowers Ca without changing the "
        "device, and in the SE regime it costs no droplet size at all — size is "
        "Ca-independent, frequency carries the flow.",
        ("Throughput falls in proportion — regime margin is bought with output.",
         "Below the production threshold the far rungs stop producing entirely, which "
         "is a cliff, not a gradient."),
        "[theory] @chakraborty2017-step-emulsification, @montessori2020-step-emulsification "
        "· [[claims/step-emulsification-ca-independent-size]]",
    ),
    StructuralLever(
        "margin", "DFU count", "main.length_mm", "increase",
        "Spreading the same total flow over more DFUs lowers per-DFU velocity, which "
        "is what exit Ca actually measures. The in-regime shape of this device is many "
        "DFUs run slowly, not few run fast.",
        ("A longer ladder droops: flatness is the price of regime margin, and it is "
         "the trade this whole family is stuck in.",
         "Area and priming volume grow with the run."),
        "[model-v3, 2026-07] · [[open-questions/deep-dfu-se-regime]]",
    ),
    StructuralLever(
        "margin", "Exit depth", "junction.exit_depth_um", "decrease",
        "A shallower exit makes smaller droplets at lower velocity, moving the design "
        "back toward the band Peak has actually measured (exit Ca ≤ 0.0017).",
        ("Throughput per DFU falls as 1/h³ — this is the most expensive lever in the "
         "set, and only worth pulling if the size target allows it.",
         "The device needs proportionally more DFUs to hold throughput, which costs "
         "flatness and area."),
        "[experimental] @ws-2026-07-13-po-sweep-v5-8-1 · [[claims/step-emulsification-ca-independent-size]]",
    ),
)


def structural_levers(objective: str, swept_paths: Sequence[str] = ()) -> list[StructuralLever]:
    """
    Structural levers for *objective*, skipping knobs the study already swept.

    A curated statement about a knob the study measured would be a worse version
    of a number already on the page, so measured always wins.
    """
    swept = set(swept_paths)
    return [lever for lever in STRUCTURAL
            if lever.objective == objective and lever.path not in swept]
