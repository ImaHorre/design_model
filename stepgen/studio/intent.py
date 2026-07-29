"""
stepgen.studio.intent
=====================
The intent layer — state a question, not a grid.

A study normally spells out every geometry block and every swept axis.  That is
the right primitive, but it is the wrong *front door*: it asks the user to
already know what geometry answers their question.  The intent layer inverts
that::

    intent:
      droplet_um: 140              # "deep DFUs, large droplets"
      throughput_mlhr: 5
    constraints:
      max_Po_mbar: 300             # "don't start production at 1000 mbar"
      fab: current                 # or: relaxed_300um
    explore: [serpentine, radial, manifold]

Everything below that is *generated*: the junction exit is derived from the
droplet target through the shared inverse solve, the sweep is bounded by the
constraints, and each family lays itself out behind
:meth:`stepgen.families.base.Family.grid_from_intent`.  The result is an
ordinary study dict, handed to the ordinary expansion path — there is no second
pipeline, and a generated study is inspectable and editable as YAML like any
other (:func:`generated_yaml`).

What generation will not do
---------------------------
* **Explicit wins.** Any block the user wrote is left exactly as written; intent
  only fills what is absent.  Writing ``serpentine:`` by hand in an intent study
  is a supported way to pin one family and generate the rest.
* **No silent substitution.** A family that cannot answer an intent raises
  :class:`~stepgen.families.intent.IntentNotSupported` and is reported as
  skipped, rather than being handed geometry the studio layer invented for it.
* **No refusing to draw.** A 140 µm droplet needs a ~51 µm exit, far outside the
  range the droplet power-law was fitted over.  Intent generates it anyway and
  lets the ``validity`` gate flag every resulting row.  That is the honest
  division of labour: intent decides what to try, scoring decides what to trust.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import yaml

from stepgen.families import get_family, list_families
from stepgen.families.intent import (
    DEFAULT_FAB,
    FAB_PRESETS,
    Constraints,
    Intent,
    IntentNotSupported,
    pressure_sweep,
)

#: Blocks intent may generate.  Anything the user wrote is never touched.
GENERATED_BLOCKS = ("fluids", "footprint", "manufacturing", "operating",
                    "scoring", "decide")

#: The house fluid system — sunflower oil dispersed in 2% SDS water.  Written
#: into the generated study rather than left to family defaults so that the
#: chapter records what was actually assumed.
DEFAULT_FLUIDS: dict[str, Any] = {
    "mu_dispersed": 0.06,        # Pa·s — sunflower oil
    "mu_continuous": 0.00089,    # Pa·s — 2% SDS water
    "gamma": 0.005,              # N/m  — 5 mN/m
    "emulsion_ratio": 0.10,
    "phase_system": "o/w",
}

#: The house scoring block.  An intent study that stated no thresholds would
#: score every cell grey, which is not an answer — so intent supplies the
#: standard ones and the chapter records them like any other config value.
DEFAULT_SCORING: dict[str, Any] = {
    "throughput_mlhr": {"green": 1, "orange": 0.1, "higher_better": True},
    "uniformity_pct": {"green": 20, "orange": 100},
    "operating_Po_mbar": {"green": 300, "orange": 600},
    # green ≤ 0.0125 = below the rectangular-nozzle SE→jetting threshold
    # (@montessori2020-step-emulsification); orange ≤ 0.03 = below the
    # axisymmetric SE→balloon ceiling (@chakraborty2017-step-emulsification).
    "regime_Ca": {"green": 0.0125, "orange": 0.03},
    "hub_budget_pct": {"green": 15, "orange": 50},
    "build": {"from": "manufacturing", "fits_square": "required",
              "no_crossing": "required"},
}

DEFAULT_QW_MLHR = 5.0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_intent(block: dict[str, Any] | None) -> Intent:
    """Parse the ``intent:`` block."""
    block = dict(block or {})
    if "droplet_um" not in block:
        raise ValueError(
            "intent: needs droplet_um — it is what closes the junction inverse "
            "solve. Add e.g. `intent: { droplet_um: 140, throughput_mlhr: 5 }`."
        )
    return Intent(
        droplet_um=float(block["droplet_um"]),
        throughput_mlhr=float(block.get("throughput_mlhr", DEFAULT_QW_MLHR)),
        junction_aspect_ratio=float(block.get("junction_aspect_ratio", 3.0)),
    )


def parse_constraints(block: dict[str, Any] | None) -> Constraints:
    """
    Parse the ``constraints:`` block, resolving the ``fab:`` preset first.

    Explicit caps override the preset, so ``fab: current`` plus an explicit
    ``max_main_depth_um: 300`` is a legitimate way to ask a what-if without
    inventing a preset for it.
    """
    block = dict(block or {})
    fab = str(block.get("fab", DEFAULT_FAB))
    if fab not in FAB_PRESETS:
        known = ", ".join(sorted(FAB_PRESETS))
        raise KeyError(f"unknown fab preset '{fab}'; known presets: {known}")

    caps = dict(FAB_PRESETS[fab])
    caps.update({k: float(v) for k, v in block.items()
                 if k in caps and v is not None})

    return Constraints(
        max_Po_mbar=float(block.get("max_Po_mbar", 300.0)),
        max_main_depth_um=caps["max_main_depth_um"],
        max_main_width_um=caps["max_main_width_um"],
        min_wall_um=caps["min_wall_um"],
        square_side_mm=float(block.get("square_side_mm", 63.5)),
        reserve_border_mm=float(block.get("reserve_border_mm", 2.0)),
        fab=fab,
    )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@dataclass
class IntentPlan:
    """What the intent layer generated, and what it left alone."""

    intent: Intent
    constraints: Constraints
    explore: list[str]
    #: block names intent wrote (families and shared blocks alike)
    generated: list[str] = field(default_factory=list)
    #: block names the user wrote, which intent left untouched
    user_supplied: list[str] = field(default_factory=list)
    #: family -> why it could not be generated
    skipped: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """A JSON-safe record for the chapter sidecar and the provenance panel."""
        return {
            "droplet_um": self.intent.droplet_um,
            "throughput_mlhr": self.intent.throughput_mlhr,
            "junction_aspect_ratio": self.intent.junction_aspect_ratio,
            "max_Po_mbar": self.constraints.max_Po_mbar,
            "fab": self.constraints.fab,
            "max_main_depth_um": self.constraints.max_main_depth_um,
            "max_main_width_um": self.constraints.max_main_width_um,
            "min_wall_um": self.constraints.min_wall_um,
            "square_side_mm": self.constraints.square_side_mm,
            "explore": list(self.explore),
            "generated_blocks": list(self.generated),
            "user_supplied_blocks": list(self.user_supplied),
            "skipped_families": dict(self.skipped),
        }


def has_intent(raw: dict[str, Any]) -> bool:
    """True when *raw* is an intent study (an ``intent:`` block is present)."""
    return bool(raw.get("intent"))


def expand_intent(raw: dict[str, Any]) -> tuple[dict[str, Any], IntentPlan | None]:
    """
    Turn an intent study into an ordinary study dict.

    Returns ``(raw, None)`` unchanged when there is no ``intent:`` block, so
    every caller can route through this without branching.
    """
    if not has_intent(raw):
        return raw, None

    intent = parse_intent(raw.get("intent"))
    constraints = parse_constraints(raw.get("constraints"))

    explore = raw.get("explore") or raw.get("family") or list_families()
    explore = [explore] if isinstance(explore, str) else list(explore)

    out = copy.deepcopy(raw)
    plan = IntentPlan(intent=intent, constraints=constraints, explore=explore)
    # spell the fab preset out, so the constraints recorded with the study are
    # the caps actually in force and diagnosis has values it can step
    out["constraints"] = constraints.as_block()

    # ── shared blocks: fill only what the user left out ─────────────────────
    defaults: dict[str, Any] = {
        "fluids": copy.deepcopy(DEFAULT_FLUIDS),
        "footprint": constraints.as_footprint(),
        "manufacturing": constraints.as_manufacturing(),
        "operating": {
            "Po_mbar": pressure_sweep(constraints.max_Po_mbar),
            "Qw_mlhr": DEFAULT_QW_MLHR,
        },
        "scoring": copy.deepcopy(DEFAULT_SCORING),
        "decide": {"axes": ["flatness", "throughput", "drive_pressure", "margin"]},
    }
    for block, value in defaults.items():
        if out.get(block):
            plan.user_supplied.append(block)
        else:
            out[block] = value
            plan.generated.append(block)

    fluids = out["fluids"]

    # ── per-family geometry ─────────────────────────────────────────────────
    kept: list[str] = []
    for name in explore:
        if out.get(name):
            plan.user_supplied.append(name)
            kept.append(name)
            continue
        try:
            family = get_family(name)
        except KeyError as exc:
            plan.skipped[name] = str(exc)
            continue
        try:
            out[name] = family.grid_from_intent(intent, constraints, fluids=fluids)
        except IntentNotSupported as exc:
            plan.skipped[name] = str(exc)
            continue
        plan.generated.append(name)
        kept.append(name)

    if not kept:
        raise ValueError(
            "intent generated no geometry: no explored family could answer it "
            f"({'; '.join(f'{k}: {v}' for k, v in plan.skipped.items()) or 'none explored'})"
        )

    out["family"] = kept
    out.setdefault(
        "title",
        f"Intent — {intent.droplet_um:g} µm droplets at {intent.throughput_mlhr:g} mL/hr "
        f"under {constraints.max_Po_mbar:g} mbar",
    )
    return out, plan


def generated_yaml(raw: dict[str, Any]) -> str:
    """
    The expanded study as YAML — the escape hatch out of the intent layer.

    Intent is a front door, not a lock-in: whatever it generates can be dumped,
    edited by hand and run as an ordinary study.  The UI shows this so a user
    can see exactly what their intent turned into.
    """
    expanded, _ = expand_intent(raw)
    return yaml.safe_dump(expanded, sort_keys=False, default_flow_style=False,
                          allow_unicode=True)
