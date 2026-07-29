"""
stepgen.families.intent
=======================
The intent vocabulary — what a user *wants* and what they are allowed to spend
getting it — plus the shared inverse solves every family needs to turn that into
geometry.

This lives in the family layer, not the studio layer, because
:meth:`stepgen.families.base.Family.grid_from_intent` is part of the topology
contract: a family is the only thing that knows how to lay itself out for a
given droplet size and pressure ceiling.  The studio layer parses YAML into
these objects and assembles the resulting blocks into a study
(:mod:`stepgen.studio.intent`).

The inverse solve
-----------------
``D = k · w^a · h^b`` is the calibrated droplet power-law
(:class:`stepgen.config.DropletModelConfig`).  Fixing the junction aspect ratio
``ar = w / h`` closes it::

    D = k · (ar·h)^a · h^b = k · ar^a · h^(a+b)
    h = (D / (k · ar^a))^(1/(a+b))          w = ar · h

This is the same closed form ``design_search._derive_mcd_from_ar`` uses; that
function now delegates here so there is one implementation of the rule.

Honesty note
------------
The power-law is calibrated at h = 1, 5 and 10 µm.  Asking for a large droplet
therefore lands the *derived* junction well outside the fitted range — a 140 µm
target needs a ~51 µm exit depth.  Intent does not refuse to generate that
geometry; it generates it and lets the ``validity`` gate say, per row, that the
model has not been checked there.  Generating an honest-but-flagged design is
more useful than refusing to draw one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence


class IntentNotSupported(NotImplementedError):
    """Raised when a family cannot generate a grid from an intent."""


# ---------------------------------------------------------------------------
# Fabrication presets
# ---------------------------------------------------------------------------
#: Named process envelopes.  ``current`` is what the fab does today; the
#: ``relaxed_*`` entries exist so a study can *price* deeper etch capability
#: rather than argue about it (see stepgen.studio.diagnosis).
FAB_PRESETS: dict[str, dict[str, float]] = {
    "current": {
        "max_main_depth_um": 200.0,
        "max_main_width_um": 1000.0,
        "min_wall_um": 5.0,
    },
    "relaxed_300um": {
        "max_main_depth_um": 300.0,
        "max_main_width_um": 1000.0,
        "min_wall_um": 5.0,
    },
    "relaxed_500um": {
        "max_main_depth_um": 500.0,
        "max_main_width_um": 2000.0,
        "min_wall_um": 5.0,
    },
}

DEFAULT_FAB = "current"


# ---------------------------------------------------------------------------
# What the user wants
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Intent:
    """The design question, stated as a target rather than a grid."""

    #: target droplet diameter [µm] — the one field intent cannot do without,
    #: because it is what closes the junction inverse solve.
    droplet_um: float
    #: total dispersed-phase throughput wanted [mL/hr]; sizes the DFU count.
    throughput_mlhr: float = 5.0
    #: junction exit_width / exit_depth.  3.0 matches the design-search default
    #: and sits inside the fitted aspect-ratio range.
    junction_aspect_ratio: float = 3.0

    def __post_init__(self) -> None:
        if not self.droplet_um or self.droplet_um <= 0:
            raise ValueError("intent.droplet_um must be a positive diameter in µm")
        if self.throughput_mlhr <= 0:
            raise ValueError("intent.throughput_mlhr must be positive")
        if self.junction_aspect_ratio <= 0:
            raise ValueError("intent.junction_aspect_ratio must be positive")


@dataclass(frozen=True)
class Constraints:
    """What the design is allowed to spend — the bounds intent sweeps within."""

    #: drive-pressure ceiling [mbar].  The generated ``operating.Po_mbar`` sweep
    #: never exceeds it: "don't start production at 1000 mbar" is a constraint,
    #: not a preference to be traded away by a composite score.
    max_Po_mbar: float = 300.0
    max_main_depth_um: float = 200.0
    max_main_width_um: float = 1000.0
    min_wall_um: float = 5.0
    square_side_mm: float = 63.5
    reserve_border_mm: float = 2.0
    #: exit Ca the generated grid aims to stay under.  Defaults to the green
    #: bound of the step-emulsification ceiling — borrowed from literature at
    #: λ ≈ 1 (@montessori2020-step-emulsification) and, at time of writing, 7x
    #: above anything Peak has measured (see ``families.base.CA_MEASURED_MAX``).
    #: It bounds the sweep because Ca is what actually binds for deep DFUs, not
    #: because we are confident in the number.
    max_exit_Ca: float = 0.0125
    #: name of the :data:`FAB_PRESETS` entry the caps came from (provenance).
    fab: str = DEFAULT_FAB

    def as_block(self) -> dict[str, Any]:
        """
        The fully-resolved ``constraints:`` block, with the preset spelled out.

        Written back into the recorded question so that (a) the chapter records
        the caps actually in force rather than only the preset name, and (b)
        relaxation pricing has a value to step — a cap that only exists inside a
        preset is one diagnosis cannot see, let alone price.
        """
        return {
            "max_Po_mbar": self.max_Po_mbar,
            "max_main_depth_um": self.max_main_depth_um,
            "max_main_width_um": self.max_main_width_um,
            "min_wall_um": self.min_wall_um,
            "square_side_mm": self.square_side_mm,
            "reserve_border_mm": self.reserve_border_mm,
            "max_exit_Ca": self.max_exit_Ca,
            "fab": self.fab,
        }

    def as_manufacturing(self) -> dict[str, float]:
        """The ``manufacturing:`` block these caps imply."""
        return {
            "max_main_depth_um": self.max_main_depth_um,
            "max_main_width_um": self.max_main_width_um,
            "min_wall_um": self.min_wall_um,
        }

    def as_footprint(self) -> dict[str, float]:
        """The ``footprint:`` block these caps imply."""
        return {
            "square_side_mm": self.square_side_mm,
            "feed_length_mm": self.square_side_mm,
            "reserve_border_mm": self.reserve_border_mm,
        }

    @property
    def usable_side_mm(self) -> float:
        """Die side with the reserved border taken off both edges."""
        return max(0.0, self.square_side_mm - 2.0 * self.reserve_border_mm)


# ---------------------------------------------------------------------------
# Junction inverse solve  (D -> exit geometry)
# ---------------------------------------------------------------------------

def _droplet_model(droplet_model=None):
    if droplet_model is not None:
        return droplet_model
    from stepgen.config import DropletModelConfig
    return DropletModelConfig()


def depth_for_droplet(
    droplet_um: float, aspect_ratio: float = 3.0, droplet_model=None
) -> float:
    """
    Junction exit **depth** [m] that yields *droplet_um* at *aspect_ratio*.

    ``h = (D / (k · ar^a))^(1/(a+b))`` — see the module docstring.
    """
    dm = _droplet_model(droplet_model)
    D = float(droplet_um) * 1e-6
    return (D / (dm.k * aspect_ratio ** dm.a)) ** (1.0 / (dm.a + dm.b))


def junction_for_droplet(
    droplet_um: float, aspect_ratio: float = 3.0, droplet_model=None
) -> tuple[float, float]:
    """Junction ``(exit_width, exit_depth)`` in **metres** for a droplet target."""
    h = depth_for_droplet(droplet_um, aspect_ratio, droplet_model)
    return aspect_ratio * h, h


def droplet_for_junction(
    exit_width_m: float, exit_depth_m: float, droplet_model=None
) -> float:
    """Forward check: droplet diameter [µm] the power-law gives for a junction."""
    dm = _droplet_model(droplet_model)
    return dm.k * exit_width_m ** dm.a * exit_depth_m ** dm.b * 1e6


# ---------------------------------------------------------------------------
# Sizing the DFU count
# ---------------------------------------------------------------------------

#: Fraction of the supply pressure a *typical* rung actually sees once the
#: distribution channel has drooped and the continuous side has pushed back.
#: A screening number, not a solve — it only has to get the sweep into the right
#: decade, and the sweep brackets it four-fold either way.
DEFAULT_DROOP_FACTOR = 0.5


def rungs_for_throughput(
    *,
    throughput_mlhr: float,
    Po_mbar: float,
    rung_length_m: float,
    upstream_width_m: float,
    exit_depth_m: float,
    mu_dispersed: float,
    droop_factor: float = DEFAULT_DROOP_FACTOR,
) -> int:
    """
    Analytic first estimate of how many DFUs the throughput target needs.

    One rung at ``droop_factor · Po`` across its Poiseuille resistance carries
    ``q = ΔP / R_rung``; the count is ``Q_target / q``.  This is a **sizing
    estimate, not a prediction** — it ignores the distribution network entirely,
    which is exactly what the nodal solve then puts back.  Callers sweep a wide
    ladder around the answer rather than trusting it.

    Deep DFUs make this number small and that is the point: ``R_rung ∝ 1/h³``,
    so a 50 µm exit carries orders of magnitude more oil than a 10 µm one and
    the ladder that delivers a given throughput gets *shorter*.
    """
    from stepgen.config import mlhr_to_m3s
    from stepgen.models.resistance import hydraulic_resistance_rectangular

    R_rung = hydraulic_resistance_rectangular(
        mu_dispersed, rung_length_m, upstream_width_m, exit_depth_m
    )
    dP = droop_factor * float(Po_mbar) * 100.0     # mbar -> Pa
    q_rung = dP / R_rung                           # m³/s
    if q_rung <= 0:
        return 1
    return max(1, int(math.ceil(mlhr_to_m3s(float(throughput_mlhr)) / q_rung)))


def rungs_for_ca_ceiling(
    *,
    throughput_mlhr: float,
    exit_width_m: float,
    exit_depth_m: float,
    mu_dispersed: float,
    gamma: float,
    max_exit_Ca: float,
) -> int:
    """
    How many DFUs the throughput needs if none may exceed *max_exit_Ca*.

    The Ca ceiling caps the **exit velocity**, and it caps it at the same value
    for every geometry: ``v_max = Ca_max·γ/µ``.  Only the exit *area* differs, so
    the flow one DFU may carry is ``q_max = v_max · w · h`` and the count is
    ``Q_target / q_max``.

    This is the sizing that :func:`rungs_for_throughput` cannot see, and the two
    pull in opposite directions.  Throughput sizing asks "how few DFUs can
    deliver this at the pressure ceiling?" and answers by making each one run
    fast — which is exactly what drives Ca up.  For deep DFUs the gap is large:
    at a 140 µm droplet target the throughput answer is ~11 rungs and the Ca
    answer is ~172.  A grid generated from the first alone never visits the
    corner where the design actually works, which is the defect this function
    exists to close.

    Returns 1 when Ca cannot be evaluated (no interfacial tension given), so the
    caller falls back to throughput sizing rather than inventing a constraint.
    """
    from stepgen.config import mlhr_to_m3s

    if gamma <= 0 or max_exit_Ca <= 0 or mu_dispersed <= 0:
        return 1
    v_max = max_exit_Ca * gamma / mu_dispersed          # m/s, geometry-independent
    q_max = v_max * exit_width_m * exit_depth_m         # m³/s per DFU
    if q_max <= 0:
        return 1
    return max(1, int(math.ceil(mlhr_to_m3s(float(throughput_mlhr)) / q_max)))


def dfu_count_ladder(
    n_flow: int, n_ca: int, *, minimum: int = 4, maximum: float | None = None
) -> list[int]:
    """
    A count sweep spanning **both** sizing answers, not just one.

    ``n_flow`` is the fewest DFUs that deliver the throughput at the pressure
    ceiling; ``n_ca`` is the fewest that keep every exit under the Ca ceiling.
    The design space worth searching runs between them and a little past the
    larger, because that is where the flatness cost of a long ladder starts to
    trade against the Ca cost of a short one — a real conflict for the decide
    layer to rank, and one that a ladder anchored on either end alone hides.

    Geometric spacing, because the two ends can differ by more than an order of
    magnitude.
    """
    lo = max(minimum, min(n_flow, n_ca))
    hi = max(lo, max(n_flow, n_ca) * 2)
    if maximum is not None:
        hi = min(hi, max(float(lo), float(maximum)))
    if hi <= lo:
        return [int(lo)]
    steps = 4
    ratio = (hi / lo) ** (1.0 / (steps - 1))
    out: list[int] = []
    for k in range(steps):
        v = int(round(lo * ratio ** k))
        if v not in out:
            out.append(v)
    return sorted(out)


def ladder(
    centre: float,
    factors: Sequence[float] = (0.5, 1.0, 2.0, 4.0),
    *,
    minimum: float = 1.0,
    maximum: float | None = None,
    integer: bool = True,
) -> list[float]:
    """
    A short multiplicative sweep bracketing *centre*, clamped and de-duplicated.

    Intent sweeps in multiples rather than in fixed steps because the estimate it
    brackets is order-of-magnitude, not precise.
    """
    out: list[float] = []
    for f in factors:
        v = centre * f
        v = max(minimum, v)
        if maximum is not None:
            v = min(maximum, v)
        if integer:
            v = float(int(round(v)))
        else:
            v = float(f"{v:.4g}")
        if v not in out:
            out.append(v)
    return sorted(out)


def pressure_sweep(
    max_Po_mbar: float, fractions: Sequence[float] = (0.15, 0.4, 0.7, 1.0)
) -> list[float]:
    """
    The ``operating.Po_mbar`` sweep implied by a pressure ceiling.

    The low fraction is not decoration.  Exit Ca scales with per-DFU flow and so
    with drive pressure, so for deep DFUs the designs that stay inside
    step-emulsification live at the *bottom* of the pressure range — a sweep
    that only samples the top three-quarters of it misses them entirely.
    """
    out: list[float] = []
    for f in fractions:
        v = float(f"{max_Po_mbar * f:.4g}")
        if v > 0 and v not in out:
            out.append(v)
    return sorted(out)


# ---------------------------------------------------------------------------
# Shared junction/rung geometry every family derives the same way
# ---------------------------------------------------------------------------

#: Upstream-channel width as a multiple of the exit depth.  The rectangular
#: resistance correction ``1 − 0.63·h/w`` requires ``w > 0.63·h`` to stay
#: positive and the families require ``w > h`` outright, so a deep exit forces a
#: wide upstream channel.  1.5x and 2.5x straddle that constraint without
#: wasting in-plane width.
UPSTREAM_WIDTH_RATIOS: tuple[float, ...] = (1.5, 2.5)


@dataclass
class JunctionPlan:
    """The junction + rung geometry an intent implies, shared by all families."""

    exit_width_um: float
    exit_depth_um: float
    pitch_um: float
    upstream_width_um: list[float] = field(default_factory=list)
    rung_length_mm: list[float] = field(default_factory=list)

    @property
    def mid_upstream_m(self) -> float:
        """Representative upstream width [m] for the DFU-count estimate."""
        vals = self.upstream_width_um or [self.exit_depth_um * 2.0]
        return vals[len(vals) // 2] * 1e-6

    @property
    def mid_rung_length_m(self) -> float:
        vals = self.rung_length_mm or [2.0]
        return vals[len(vals) // 2] * 1e-3


def plan_junction(
    intent: Intent,
    constraints: Constraints,
    *,
    rung_length_mm: Sequence[float] = (1.0, 2.0),
    droplet_model=None,
) -> JunctionPlan:
    """
    Derive the junction and rung geometry an *intent* implies.

    Every family starts here, so a serpentine, a radial wheel and a comb
    manifold asked for the same droplet all get the *same* exit — which is what
    makes the resulting cross-family table a fair comparison.
    """
    w_m, h_m = junction_for_droplet(
        intent.droplet_um, intent.junction_aspect_ratio, droplet_model
    )
    w_um, h_um = w_m * 1e6, h_m * 1e6

    upstream = []
    for ratio in UPSTREAM_WIDTH_RATIOS:
        v = max(h_um * ratio, constraints.min_wall_um)
        v = float(f"{v:.4g}")
        if v not in upstream:
            upstream.append(v)

    return JunctionPlan(
        exit_width_um=float(f"{w_um:.4g}"),
        exit_depth_um=float(f"{h_um:.4g}"),
        pitch_um=float(f"{2.0 * w_um:.4g}"),
        upstream_width_um=sorted(upstream),
        rung_length_mm=[float(v) for v in rung_length_mm],
    )
