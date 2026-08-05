"""
stepgen.studio.diagnosis
========================
When the answer is "you can't", say **why** and **what it would take**.

A scored table that comes back all red is a filter, not an answer.  This module
turns it into one, in two steps:

**Binding-constraint analysis** — which gate fails, how often, and how often it
is the *sole* reason a row is red.  A gate that fails on half the study but
never alone is a symptom; a gate that single-handedly reds twelve rows is the
thing standing in the way.

**Relaxation pricing** — take each constraint that is actually active, step it
one notch, re-run, and report the delta:

    relax max_main_depth 200 → 300 µm:  12 red → 0 red, 4 green → 14 green

This is what converts a process argument into a number.  The
``comp_large_dfu_stage1_screen`` workspace already concluded *in prose* that the
200 µm main-depth cap — not the physics — is what blocks long deep-DFU ladders.
That sentence should be computed, and this is what computes it.

Cost
----
Pricing re-runs the whole study once per knob, so it is deliberately opt-in and
bounded (:data:`MAX_PRICED_KNOBS`).  Binding-constraint analysis is free — it
reads the rows that are already scored — and always runs.

Where a knob is written
-----------------------
For an intent study the canonical home of a cap is the ``constraints:`` block,
because that is what generates *both* the ``manufacturing:`` block and the
geometry grid; relaxing only ``manufacturing:`` would loosen the gate while
leaving the generated geometry pinned at the old cap, and the price would come
back as zero for the wrong reason.  Knobs therefore write to every location they
own, and the intent layer's "explicit wins" rule keeps the two consistent.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from stepgen.studio.scoring import (
    GREEN, ORANGE, RED, ScoredRow, _score_threshold, score_result,
)
from stepgen.studio.study import Study, build_study

#: Most constraints to price in one pass.  Each costs a full re-run.
MAX_PRICED_KNOBS = 4


# ---------------------------------------------------------------------------
# Which gate is in the way
# ---------------------------------------------------------------------------

#: Human labels for the gate keys diagnosis reports on.  ``build`` is expanded
#: into its sub-gates (``build:fits_square`` …) so a diagnosis can name the
#: actual failure rather than the composite.
GATE_LABELS: dict[str, str] = {
    "throughput_mlhr": "throughput",
    "uniformity_pct": "ΔP flatness",
    "operating_Po_mbar": "drive pressure",
    "regime_Ca": "exit Ca (step-emulsification regime)",
    "hub_budget_pct": "hub ΔP budget",
    "validity": "model validity envelope",
    "build:fits_square": "fits the die square",
    "build:manufacturable": "within fab caps",
    "build:no_crossing": "continuous phase can drain without crossing",
}


def gate_label(key: str) -> str:
    return GATE_LABELS.get(key, key)


def row_failures(row: ScoredRow, category: str = RED) -> list[str]:
    """
    The gate keys of *row* sitting at *category*, with ``build`` expanded.

    A red build cell reports ``build:fits_square`` rather than ``build`` so the
    caller knows which constraint to reach for.  A build cell that failed
    without recording which sub-gate did (older rows) degrades to ``build``.
    """
    out: list[str] = []
    for key, cell in row.cells.items():
        if cell.category != category:
            continue
        if key != "build":
            out.append(key)
        elif cell.detail:
            out.extend(f"build:{g}" for g in cell.detail)
        else:
            out.append("build")
    return sorted(out)


@dataclass
class GateFailure:
    """How badly one gate is standing in the way, across the whole study."""

    key: str
    label: str
    n_red: int = 0             # rows this gate reds
    n_non_green: int = 0       # rows this gate is orange or red on
    n_sole_cause: int = 0      # red rows where it is the ONLY red gate

    @property
    def is_binding(self) -> bool:
        """True when relaxing this gate alone would change a row's verdict."""
        return self.n_sole_cause > 0

    def describe(self) -> str:
        if self.n_sole_cause:
            return (f"{self.label} is the sole reason {self.n_sole_cause} "
                    f"design{'s' if self.n_sole_cause != 1 else ''} scored red")
        if self.n_red:
            return (f"{self.label} reds {self.n_red} "
                    f"design{'s' if self.n_red != 1 else ''}, but never alone")
        return f"{self.label} is non-green on {self.n_non_green} designs"


def binding_gates(rows: Sequence[ScoredRow]) -> list[GateFailure]:
    """
    Tally every gate's contribution to the study's failures.

    Ordered by sole-cause count first, then total reds: the gate that is
    single-handedly responsible for the most failures is the one worth pricing,
    even if another gate is non-green more often.
    """
    tally: dict[str, GateFailure] = {}

    def _get(key: str) -> GateFailure:
        if key not in tally:
            tally[key] = GateFailure(key=key, label=gate_label(key))
        return tally[key]

    for row in rows:
        reds = row_failures(row, RED)
        oranges = row_failures(row, ORANGE)
        for key in reds:
            g = _get(key)
            g.n_red += 1
            g.n_non_green += 1
        for key in oranges:
            _get(key).n_non_green += 1
        if len(reds) == 1:
            _get(reds[0]).n_sole_cause += 1

    return sorted(tally.values(),
                  key=lambda g: (-g.n_sole_cause, -g.n_red, -g.n_non_green, g.key))


# ---------------------------------------------------------------------------
# Relaxation knobs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Knob:
    """A constraint that can be stepped one notch, and where it is written."""

    key: str
    label: str
    unit: str
    #: gate keys this knob can plausibly move — used to decide whether it is
    #: *active* in a given study.  Pricing an inert knob wastes a full re-run.
    gates: tuple[str, ...]
    #: ``(block, field)`` locations in the raw study dict.  All are written; see
    #: the module docstring on why constraints and manufacturing move together.
    locations: tuple[tuple[str, str], ...]
    step: Callable[[float], float]
    #: plain-English direction, for the report
    direction: str = "relax"

    def current(self, raw: dict[str, Any]) -> float | None:
        """The value in force, read from the first location that has one."""
        for block, field_name in self.locations:
            node = raw.get(block)
            if isinstance(node, dict) and node.get(field_name) is not None:
                try:
                    return float(node[field_name])
                except (TypeError, ValueError):
                    return None
        return None

    def apply(self, raw: dict[str, Any]) -> tuple[float, float] | None:
        """Step the knob in *raw* (mutating it).  Returns ``(before, after)``."""
        before = self.current(raw)
        if before is None:
            return None
        after = float(self.step(before))
        if after == before:
            return None
        for block, field_name in self.locations:
            node = raw.setdefault(block, {})
            if isinstance(node, dict):
                node[field_name] = after
        return before, after


#: The constraints worth pricing.  Each is a decision someone can actually take
#: — buy deeper etch capability, accept a bigger die, run at higher pressure —
#: not a physical constant.  ``regime_Ca`` deliberately has no knob: being
#: outside step-emulsification is physics, and no process change relaxes it.
KNOBS: tuple[Knob, ...] = (
    Knob(
        key="max_main_depth_um",
        label="main-channel depth cap",
        unit="µm",
        gates=("build:manufacturable", "uniformity_pct", "throughput_mlhr"),
        locations=(("constraints", "max_main_depth_um"),
                   ("manufacturing", "max_main_depth_um")),
        step=lambda v: v + 100.0,
    ),
    Knob(
        key="max_main_width_um",
        label="main-channel width cap",
        unit="µm",
        gates=("build:manufacturable", "uniformity_pct", "throughput_mlhr"),
        locations=(("constraints", "max_main_width_um"),
                   ("manufacturing", "max_main_width_um")),
        step=lambda v: v * 2.0,
    ),
    Knob(
        key="square_side_mm",
        label="die square side",
        unit="mm",
        gates=("build:fits_square", "throughput_mlhr"),
        locations=(("constraints", "square_side_mm"),
                   ("footprint", "square_side_mm"),
                   ("footprint", "feed_length_mm")),
        step=lambda v: v * 1.5,
    ),
    Knob(
        key="max_Po_mbar",
        label="drive-pressure ceiling",
        unit="mbar",
        gates=("throughput_mlhr", "operating_Po_mbar"),
        locations=(("constraints", "max_Po_mbar"),),
        step=lambda v: v * 2.0,
    ),
    Knob(
        key="min_wall_um",
        label="minimum wall / feature width",
        unit="µm",
        gates=("build:manufacturable", "build:no_crossing"),
        locations=(("constraints", "min_wall_um"),
                   ("manufacturing", "min_wall_um")),
        step=lambda v: v / 2.0,
        direction="tighten",
    ),
)


def knobs_for_gate(gate: str) -> list[Knob]:
    """Every knob that could plausibly move *gate* — empty means physics."""
    return [k for k in KNOBS if gate in k.gates]


# ---------------------------------------------------------------------------
# Gates that rest on thin evidence
# ---------------------------------------------------------------------------

#: Gates whose red is a *theory* red — the model says no, but the model has
#: barely been checked where it is saying it.
#:
#: `regime_Ca` is the case that matters. The SE ceiling we score against
#: (0.0125 green / 0.03 red) is borrowed from literature at λ ≈ 1
#: (@montessori2020-step-emulsification, @chakraborty2017-step-emulsification)
#: while we run at λ ≈ 0.015, and the highest Ca Peak has ever *measured* is
#: 0.0017 — 7x below the green bound (see families.base.CA_MEASURED_MAX). A
#: design red only on Ca has not been shown to fail; it has been shown to sit
#: somewhere we have never looked.
#:
#: This does not soften the gate. Worst-category-wins still makes the row red,
#: because a verdict that quietly downgraded an unmeasured risk would be worse
#: than no verdict. What it does is name the distinction so the decision is the
#: user's: a row red only on Ca is a **build-and-see candidate**, and a row red
#: because it does not fit the die is not.
EVIDENCE_THIN_GATES: frozenset[str] = frozenset({"regime_Ca"})


# ---------------------------------------------------------------------------
# γ-robustness of the Ca verdict
# ---------------------------------------------------------------------------

#: The plausible band for the oil/water interfacial tension of the Peak system,
#: in **N/m**.  Deliberately wide, because γ has never been measured here: the
#: configs in this repo variously assume 5, 15 and 0 mN/m, and the value picked
#: in `comp_interfacial_inversion` (9 mN/m) was a literature figure for the
#: wrong fluid pair. 3–20 mN/m spans SDS well above CMC against a vegetable oil
#: without pretending to more precision than we have.
#:
#: This is a statement of our ignorance, not a measurement. Narrow it the day a
#: pendant-drop number exists — that is the point of writing it down as a band.
DEFAULT_GAMMA_RANGE_NM: tuple[float, float] = (0.003, 0.020)


@dataclass
class CaGammaRobustness:
    """How much of a row's exit-Ca verdict survives our ignorance about γ."""

    gamma_ref: float           # the γ the study was solved at [N/m]
    gamma_lo: float            # plausible band, low end [N/m]
    gamma_hi: float            # plausible band, high end [N/m]
    ca_ref: float              # exit Ca as scored, at gamma_ref
    ca_at_lo: float            # Ca if γ were at the low end (worst case)
    ca_at_hi: float            # Ca if γ were at the high end (best case)
    verdict_lo: str            # category at the low-γ end
    verdict_hi: str            # category at the high-γ end
    #: γ above which the row would stop being red, or None if it never is / always is
    gamma_to_clear_red: float | None = None

    @property
    def is_robust(self) -> bool:
        """The verdict is the same across the whole plausible band."""
        return self.verdict_lo == self.verdict_hi

    @property
    def robustly_red(self) -> bool:
        """Red no matter what γ turns out to be — believe this one."""
        return self.verdict_lo == RED and self.verdict_hi == RED

    @property
    def robustly_ok(self) -> bool:
        """Never red across the band."""
        return self.verdict_lo != RED and self.verdict_hi != RED

    def describe(self) -> str:
        lo, hi = self.gamma_lo * 1e3, self.gamma_hi * 1e3
        if self.robustly_red:
            over = self.ca_at_hi
            return (f"red across the whole plausible γ band ({lo:g}–{hi:g} mN/m) — "
                    f"even at γ = {hi:g} mN/m the exit Ca is {over:.3g}. "
                    f"This one is genuinely out of regime.")
        if self.robustly_ok:
            return (f"never red across the plausible γ band ({lo:g}–{hi:g} mN/m) — "
                    f"the Ca verdict does not depend on the γ we assume.")
        g = self.gamma_to_clear_red
        return (f"red only for γ below {g * 1e3:.3g} mN/m; above that it clears. "
                f"The verdict turns on a constant we have never measured "
                f"(band {lo:g}–{hi:g} mN/m).")


def ca_gamma_robustness(
    row: ScoredRow,
    scoring: dict[str, Any],
    *,
    gamma_ref: float,
    gamma_range: tuple[float, float] = DEFAULT_GAMMA_RANGE_NM,
) -> CaGammaRobustness | None:
    """
    Re-evaluate a row's exit-Ca verdict across the plausible range of γ.

    **This costs nothing and needs no re-solve.** γ enters the studio families in
    exactly one place — the ``regime_Ca`` diagnostic, ``Ca = µ·v/γ`` — and never
    the hydraulic solve, so ``Ca ∝ 1/γ`` exactly and the whole band can be swept
    analytically from the single solved value.

    Why it exists: γ has never been measured for the Peak fluid system, so a hard
    red on Ca is a hard verdict resting on a guessed constant. A design that is
    red at every plausible γ is genuinely out of step-emulsification; a design
    that is red only at the pessimistic end of the band is telling you about our
    ignorance rather than about itself. Those deserve to be distinguished, and
    until now were not.

    Returns ``None`` when the row has no Ca to reason about.
    """
    cell = row.cells.get("regime_Ca")
    spec = scoring.get("regime_Ca")
    if cell is None or cell.value is None or spec is None or gamma_ref <= 0:
        return None

    lo, hi = float(gamma_range[0]), float(gamma_range[1])
    ca_ref = float(cell.value)
    # Ca ∝ 1/γ: low γ is the pessimistic end
    ca_at_lo = ca_ref * gamma_ref / lo
    ca_at_hi = ca_ref * gamma_ref / hi

    v_lo = _score_threshold(ca_at_lo, spec)
    v_hi = _score_threshold(ca_at_hi, spec)

    # γ at which Ca falls to the red boundary (the `orange` bound, past which it
    # is red): Ca(γ) = ca_ref·gamma_ref/γ = bound  ->  γ = ca_ref·gamma_ref/bound
    gamma_clear: float | None = None
    if v_lo == RED and v_hi != RED:
        bound = float(spec["orange"])
        if bound > 0:
            gamma_clear = ca_ref * gamma_ref / bound

    return CaGammaRobustness(
        gamma_ref=gamma_ref, gamma_lo=lo, gamma_hi=hi,
        ca_ref=ca_ref, ca_at_lo=ca_at_lo, ca_at_hi=ca_at_hi,
        verdict_lo=v_lo, verdict_hi=v_hi,
        gamma_to_clear_red=gamma_clear,
    )


def study_gamma(study: Study) -> float:
    """
    The interfacial tension a study was solved at [N/m], 0 if none given.

    ``fluids:`` may be a single block **or a list of blocks** — the list form is
    how a study carries several fluid systems (o/w and w/o, say) without the
    Cartesian product crossing their viscosities into combinations that do not
    exist.  Reading it as a dict raised ``AttributeError`` *after* every point
    had been solved, losing the whole run to a summary step.

    With several blocks there is no single study γ.  Returning 0 disables the
    γ-robustness overlay rather than asserting one system's γ over another's —
    Ca ∝ 1/γ, so the wrong γ would produce a confident and wrong verdict.  The
    per-row γ on ``CommonMetrics.gamma_Nm`` is the right source when the caller
    can use it.
    """
    fluids = (study.raw or {}).get("fluids") or {}
    if isinstance(fluids, list):
        gammas = set()
        for block in fluids:
            if isinstance(block, dict):
                try:
                    gammas.add(float(block.get("gamma", 0.0) or 0.0))
                except (TypeError, ValueError):
                    continue
        return gammas.pop() if len(gammas) == 1 else 0.0
    try:
        return float(fluids.get("gamma", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def theory_limited_rows(rows: Sequence[ScoredRow]) -> list[int]:
    """
    Indices of rows that are red **only** on evidence-thin gates.

    These are the designs that pass every gate resting on something we have
    measured or can compute exactly — geometry, fabrication limits, hydraulics —
    and fail only where the model is guessing. They are the honest shortlist for
    an experiment: building one is how the gate stops being a guess.
    """
    out: list[int] = []
    for i, row in enumerate(rows):
        if row.overall != RED or row.metrics.error:
            continue
        reds = set(row_failures(row, RED))
        if reds and reds <= EVIDENCE_THIN_GATES:
            out.append(i)
    return out


def active_knobs(
    raw: dict[str, Any],
    failures: Sequence[GateFailure],
    *,
    limit: int = MAX_PRICED_KNOBS,
) -> list[Knob]:
    """
    The knobs worth pricing for this study, most promising first.

    A knob is *active* when it owns a gate that is actually failing and it has a
    value to step in this study's raw dict.  Ranked by the sole-cause count of
    the gates it owns — relaxing a constraint that is never the sole cause of a
    failure changes nothing on its own, and reporting it as a price would be
    misleading.
    """
    weight = {f.key: (f.n_sole_cause * 1000 + f.n_red) for f in failures}
    scored: list[tuple[int, Knob]] = []
    for knob in KNOBS:
        score = sum(weight.get(g, 0) for g in knob.gates)
        if score <= 0:
            continue
        if knob.current(raw) is None:
            continue
        scored.append((score, knob))
    scored.sort(key=lambda t: (-t[0], t[1].key))
    return [k for _, k in scored[:limit]]


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

@dataclass
class RelaxationPrice:
    """What one notch of one constraint buys."""

    knob: str
    label: str
    unit: str
    before: float
    after: float
    red_before: int
    red_after: int
    green_before: int
    green_after: int
    n_rows: int
    error: str | None = None

    @property
    def reds_cleared(self) -> int:
        return self.red_before - self.red_after

    @property
    def greens_gained(self) -> int:
        return self.green_after - self.green_before

    @property
    def is_worth_it(self) -> bool:
        return self.reds_cleared > 0 or self.greens_gained > 0

    def describe(self) -> str:
        if self.error:
            return f"{self.label} {self.before:g} → {self.after:g} {self.unit}: {self.error}"
        head = f"relax {self.label} {self.before:g} → {self.after:g} {self.unit}"
        if not self.is_worth_it:
            return f"{head}: nothing changes — this is not what is binding"
        return (f"{head}: {self.red_before} red → {self.red_after} red, "
                f"{self.green_before} green → {self.green_after} green")


def _counts(rows: Sequence[ScoredRow]) -> tuple[int, int]:
    return (sum(1 for r in rows if r.overall == RED),
            sum(1 for r in rows if r.overall == GREEN))


def price_relaxations(
    study: Study,
    scored: Sequence[ScoredRow],
    knobs: Sequence[Knob],
    *,
    progress: bool = False,
) -> list[RelaxationPrice]:
    """
    Re-run *study* once per knob with that constraint stepped one notch.

    Each re-run goes through :func:`stepgen.studio.study.build_study` on a
    mutated copy of the raw dict, so an intent study regenerates its whole grid
    from the relaxed constraint — which is the point: a deeper permitted etch
    should change the geometry that gets tried, not merely the gate that judges
    it.
    """
    from stepgen.studio.run import run_study

    red_before, green_before = _counts(scored)
    prices: list[RelaxationPrice] = []

    for knob in knobs:
        raw2 = copy.deepcopy(study.intent_raw or study.raw)
        stepped = knob.apply(raw2)
        if stepped is None:
            continue
        before, after = stepped
        price = RelaxationPrice(
            knob=knob.key, label=knob.label, unit=knob.unit,
            before=before, after=after,
            red_before=red_before, red_after=red_before,
            green_before=green_before, green_after=green_before,
            n_rows=len(scored),
        )
        try:
            study2 = build_study(raw2, source_path=study.source_path)
            result2 = run_study(study2, progress=progress)
            scored2 = score_result(result2, study2.scoring)
            price.red_after, price.green_after = _counts(scored2)
            price.n_rows = len(scored2)
        except Exception as exc:      # a knob that breaks the study is a result
            price.error = f"re-run failed: {exc}"
        prices.append(price)

    prices.sort(key=lambda p: (-p.reds_cleared, -p.greens_gained, p.label))
    return prices


# ---------------------------------------------------------------------------
# The whole diagnosis
# ---------------------------------------------------------------------------

@dataclass
class Diagnosis:
    """Why this study came back the way it did, and what would change it."""

    n_rows: int
    n_green: int
    n_orange: int
    n_red: int
    failures: list[GateFailure] = field(default_factory=list)
    prices: list[RelaxationPrice] = field(default_factory=list)
    priced: bool = False
    #: rows red *only* on an evidence-thin gate — buildable, and only our
    #: weakest theory says no (see EVIDENCE_THIN_GATES)
    theory_limited: list[int] = field(default_factory=list)
    #: labels for those rows, so the summary survives without the row list
    theory_limited_labels: list[str] = field(default_factory=list)
    #: of those, the ones red at EVERY plausible γ — the Ca verdict survives our
    #: ignorance about interfacial tension, so it should be believed
    robustly_red_ca: list[int] = field(default_factory=list)
    #: and the ones red only at part of the γ band — the verdict is an artefact
    #: of a constant nobody has measured. These are the real shortlist.
    gamma_dependent_ca: list[int] = field(default_factory=list)
    gamma_dependent_labels: list[str] = field(default_factory=list)
    #: the γ band used, in N/m, for the report
    gamma_range: tuple[float, float] = DEFAULT_GAMMA_RANGE_NM
    gamma_ref: float = 0.0
    #: build sub-gates that FAILED on rows but were demoted to a report because
    #: the user pinned the geometry (decision 10 / W2-4): ``gate -> row count``.
    #: These are deliberately not `failures` — they coloured nothing and no
    #: relaxation should be priced against them — but they must still be said out
    #: loud, or "relax the depth cap: nothing changes" is the only thing the
    #: reader hears about a design that is 200 µm over it.
    reported_not_gated: dict[str, int] = field(default_factory=dict)

    @property
    def infeasible(self) -> bool:
        """Nothing in the study is buildable."""
        return self.n_rows > 0 and self.n_red == self.n_rows

    @property
    def binding(self) -> GateFailure | None:
        """The gate single-handedly responsible for the most failures."""
        for f in self.failures:
            if f.is_binding:
                return f
        return self.failures[0] if self.failures else None

    @property
    def best_price(self) -> RelaxationPrice | None:
        """The relaxation that buys the most, if any buys anything."""
        for p in self.prices:
            if p.is_worth_it:
                return p
        return None

    @property
    def binding_is_physics(self) -> bool:
        """
        True when no process constraint owns the binding gate.

        This is the distinction the roadmap insists on: a hard physical limit is
        not the same thing as an untested extrapolation of the model, and
        neither is the same as a cap someone could buy their way past.  Being
        above the step-emulsification ceiling is the first kind — no etch depth,
        die size or pressure ceiling relaxes it.
        """
        b = self.binding
        return b is not None and not knobs_for_gate(b.key)

    def _theory_limited_sentence(self) -> str:
        from stepgen.families.base import CA_MEASURED_MAX

        n = len(self.theory_limited)
        out = (
            f"{n} design{'s' if n != 1 else ''} pass every gate except exit Ca "
            f"— buildable, and blocked only by the threshold resting on the "
            f"thinnest evidence we have (the highest Ca ever measured on a Peak "
            f"device is {CA_MEASURED_MAX:g}, against a 0.0125 green bound)."
        )
        # γ has never been measured, so split by whether the verdict survives it
        if self.gamma_dependent_ca or self.robustly_red_ca:
            lo, hi = self.gamma_range[0] * 1e3, self.gamma_range[1] * 1e3
            n_g, n_r = len(self.gamma_dependent_ca), len(self.robustly_red_ca)
            out += (
                f" Of those, {n_r} stay red at every plausible interfacial "
                f"tension ({lo:g}–{hi:g} mN/m) and should be believed, while "
                f"**{n_g} are red only at part of that band** — their verdict "
                f"turns on a constant nobody has measured. Those {n_g} are the "
                f"build-and-see shortlist."
            )
        else:
            out += (" Whether they work is a question the model cannot settle: "
                    "they are build-and-see candidates, not failures.")
        return out

    def _reported_sentence(self) -> str:
        """
        Name the breaches the user's own choices caused (decision 10 / W2-4).

        These are not constraints to relax — a relaxation cannot buy back a cap
        the user chose to breach — but they must be said. Without this the reader
        is told "relaxing the depth cap changes nothing", which is true and
        useless, and is never told that their pinned depth is over the cap.
        """
        if not self.reported_not_gated:
            return ""
        said = ", ".join(
            f"{gate_label('build:' + k)} on {n} design{'s' if n != 1 else ''}"
            for k, n in sorted(self.reported_not_gated.items(),
                               key=lambda kv: (-kv[1], kv[0]))
        )
        return (f"Reported, not gated — you set this geometry, so it did not fail "
                f"the row: {said}. Add `build: {{ <gate>: required }}` to gate it.")

    def headline(self) -> str:
        """The answer to 'why can't I have what I asked for?'"""
        if self.n_rows == 0:
            return "The study generated no design points."

        if not self.infeasible and self.n_green:
            parts = [f"{self.n_green} of {self.n_rows} designs scored green — "
                     f"this is a ranking problem, not a feasibility one."]
            if self.theory_limited:
                parts.append(self._theory_limited_sentence())
            # Green rows need this MORE than red ones do, not less: a design that
            # scored green while breaching a cap the user pinned is the exact
            # case where silence reads as approval.
            if (sentence := self._reported_sentence()):
                parts.append(sentence)
            return " ".join(parts)

        parts = ["Every design scored red." if self.infeasible
                 else f"{self.n_red} of {self.n_rows} designs scored red."]
        b = self.binding
        if b is not None:
            d = b.describe()
            parts.append(f"{d[0].upper()}{d[1:]}.")

        # The most useful thing to say when the only thing wrong is our weakest
        # theory: these designs are buildable, and whether they work is a
        # question the model cannot settle.
        if self.theory_limited:
            parts.append(self._theory_limited_sentence())

        if (sentence := self._reported_sentence()):
            parts.append(sentence)

        if self.binding_is_physics:
            parts.append(
                f"No process constraint relaxes {b.label} — no etch depth, die "
                f"size or pressure ceiling moves it. It is a design lever, not a "
                f"purchasable one: it falls when each DFU runs slower, which "
                f"means more of them at lower drive pressure, paid for in ΔP "
                f"flatness. That trade is in the table above."
            )
        elif (p := self.best_price) is not None:
            d = p.describe()
            parts.append(f"{d[0].upper()}{d[1:]}.")
        elif self.priced:
            parts.append("None of the constraints priced would change the "
                         "verdict on its own.")
        return " ".join(parts)

    def to_json(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_green": self.n_green,
            "n_orange": self.n_orange,
            "n_red": self.n_red,
            "infeasible": self.infeasible,
            "binding_is_physics": self.binding_is_physics,
            "theory_limited": self.theory_limited_labels,
            # gamma has never been measured; record which Ca verdicts survive that
            "gamma_ref_Nm": self.gamma_ref,
            "gamma_range_Nm": list(self.gamma_range),
            "ca_red_at_every_gamma": [
                self.theory_limited_labels[self.theory_limited.index(i)]
                for i in self.robustly_red_ca if i in self.theory_limited
            ],
            "ca_red_only_at_some_gamma": self.gamma_dependent_labels,
            # decision 10: gates that FAILED but were the user's own choice, so
            # they were reported rather than allowed to colour the row
            "reported_not_gated": dict(self.reported_not_gated),
            "headline": self.headline(),
            "binding": (None if self.binding is None else {
                "gate": self.binding.key,
                "label": self.binding.label,
                "n_red": self.binding.n_red,
                "n_sole_cause": self.binding.n_sole_cause,
            }),
            "failures": [
                {"gate": f.key, "label": f.label, "n_red": f.n_red,
                 "n_non_green": f.n_non_green, "n_sole_cause": f.n_sole_cause}
                for f in self.failures
            ],
            "relaxation_prices": [
                {"knob": p.knob, "label": p.label, "unit": p.unit,
                 "from": p.before, "to": p.after,
                 "red_before": p.red_before, "red_after": p.red_after,
                 "green_before": p.green_before, "green_after": p.green_after,
                 "describe": p.describe(), "error": p.error}
                for p in self.prices
            ],
            "priced": self.priced,
        }


def diagnose(
    study: Study,
    scored: Sequence[ScoredRow],
    *,
    price: str = "auto",
    limit: int = MAX_PRICED_KNOBS,
    progress: bool = False,
    gamma_range: tuple[float, float] = DEFAULT_GAMMA_RANGE_NM,
) -> Diagnosis:
    """
    Diagnose a scored study.

    *price* is ``"auto"`` (price only when nothing is green — an infeasible
    answer owes the user a way forward), ``"always"`` or ``"never"``.  Pricing
    costs one full re-run per knob, so ``auto`` is the sensible default: a study
    that already has green rows does not need to be told what to relax.

    *gamma_range* is the plausible band for interfacial tension, used to test
    how much of each exit-Ca verdict survives the fact that γ has never been
    measured for this fluid system.  Free — see :func:`ca_gamma_robustness`.
    """
    scored = list(scored)
    failures = binding_gates(scored)
    n_green = sum(1 for r in scored if r.overall == GREEN)
    n_orange = sum(1 for r in scored if r.overall == ORANGE)
    n_red = sum(1 for r in scored if r.overall == RED)

    theory_limited = theory_limited_rows(scored)

    # γ has never been measured for the Peak system, so a hard red on Ca is a
    # hard verdict resting on a guessed constant. Split the Ca-only reds by
    # whether the verdict survives the plausible γ band — free, because Ca
    # scales exactly as 1/γ and γ enters nothing else.
    gamma_ref = study_gamma(study)
    robust: list[int] = []
    dependent: list[tuple[float, int]] = []
    for i in theory_limited:
        rb = ca_gamma_robustness(scored[i], study.scoring, gamma_ref=gamma_ref,
                                 gamma_range=gamma_range)
        if rb is None:
            continue
        if rb.robustly_red:
            robust.append(i)
        else:
            # order by how little γ it takes to clear: a design that needs only
            # 6 mN/m is a far better bet than one needing 19, and the second is
            # barely distinguishable from robustly red
            dependent.append((rb.gamma_to_clear_red or 0.0, i))
    dependent.sort()
    dependent_idx = [i for _, i in dependent]

    # Build sub-gates that failed but were demoted to a report because the user
    # pinned the geometry (decision 10 / W2-4). Counted, never priced: a
    # relaxation cannot buy back a constraint the user chose to breach.
    reported: dict[str, int] = {}
    for row in scored:
        cell = row.cells.get("build")
        for gate in (getattr(cell, "reported", None) or ()):
            reported[gate] = reported.get(gate, 0) + 1

    diag = Diagnosis(
        n_rows=len(scored), n_green=n_green, n_orange=n_orange, n_red=n_red,
        failures=failures,
        reported_not_gated=reported,
        theory_limited=theory_limited,
        theory_limited_labels=[scored[i].metrics.label for i in theory_limited],
        robustly_red_ca=robust,
        gamma_dependent_ca=dependent_idx,
        gamma_dependent_labels=[scored[i].metrics.label for i in dependent_idx],
        gamma_range=gamma_range,
        gamma_ref=gamma_ref,
    )

    wants_price = (price == "always") or (price == "auto" and n_green == 0 and scored)
    if wants_price:
        raw = study.intent_raw or study.raw
        knobs = active_knobs(raw, failures, limit=limit)
        if knobs:
            diag.prices = price_relaxations(study, scored, knobs, progress=progress)
        diag.priced = True

    return diag
