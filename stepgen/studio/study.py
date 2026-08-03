"""
stepgen.studio.study
====================
Parse a unified study config and expand it into a grid of design points.

Schema (``configs/study_template.yaml``)
----------------------------------------
Any leaf value may be a scalar (fixed) or a list (swept) — the swept axes form
a Cartesian product.  ``family:`` is itself sweepable, so a single device is
just "a sweep of one".  Only the geometry sub-block of the *selected* family is
read for a given point.

Meta keys (``title``, ``goal``, ``scoring``, ``reference``) are pulled out
before expansion — they are never swept.

An ``intent:`` block short-circuits the front of this: the study is *generated*
from a droplet/throughput target and its constraints
(:mod:`stepgen.studio.intent`) and the generated dict then goes through exactly
this expansion.  There is one pipeline, not two.
"""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# keys that carry study-level metadata and must not be treated as swept axes
_META_KEYS = frozenset({"title", "goal", "family", "scoring", "reference",
                        "decide", "intent", "constraints", "explore"})

# per-family geometry blocks are named after the family; these shared blocks are
# expanded together with the selected family's geometry
_SHARED_BLOCKS = ("fluids", "footprint", "manufacturing", "operating")


def expand_grid(node: Any) -> list[Any]:
    """
    Cartesian-expand a nested structure so no leaf is a list.

    A ``dict`` expands the product of its expanded values.  A ``list`` is a
    swept axis: each element becomes an option.  Scalars pass through.

    >>> expand_grid({"a": [1, 2], "b": 9})
    [{'a': 1, 'b': 9}, {'a': 2, 'b': 9}]
    """
    if isinstance(node, dict):
        keys = list(node.keys())
        options_per_key = [expand_grid(node[k]) for k in keys]
        return [dict(zip(keys, combo)) for combo in itertools.product(*options_per_key)]
    if isinstance(node, list):
        out: list[Any] = []
        for element in node:
            out.extend(expand_grid(element))
        return out
    return [node]


@dataclass(frozen=True)
class StudyPoint:
    """One fully-resolved design point (all scalars) ready to hand to a family."""

    family: str
    label: str
    params: dict[str, Any]          # resolved family geometry block
    fluids: dict[str, Any]
    footprint: dict[str, Any]
    manufacturing: dict[str, Any]
    operating: dict[str, Any]


@dataclass
class Study:
    """A parsed study: metadata, defaults, scoring, references, expanded points."""

    title: str
    goal: str
    families: list[str]
    scoring: dict[str, Any]
    references: list[dict[str, Any]]
    points: list[StudyPoint]
    #: the ``decide:`` block (value axes + composite weights).  Empty means fall
    #: back to ``goal:`` as a one-axis shorthand — see studio.ranking.
    decide: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None
    source_text: str | None = None
    #: what the intent layer generated, or ``None`` for a hand-written study.
    #: ``raw`` is the *expanded* dict either way, so everything downstream sees
    #: one shape; ``intent_raw`` keeps the question the user actually asked.
    intent_plan: Any = None
    intent_raw: dict[str, Any] = field(default_factory=dict)

    @property
    def from_intent(self) -> bool:
        """True when this study was generated from an ``intent:`` block."""
        return self.intent_plan is not None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _label_for(family: str, params: dict[str, Any], operating: dict[str, Any]) -> str:
    """A short, stable, human-readable label from the point's swept params."""
    bits: list[str] = [family]
    main = params.get("main", {}) if isinstance(params.get("main"), dict) else {}
    rung = params.get("rung", {}) if isinstance(params.get("rung"), dict) else {}
    # serpentine / manifold main + rung axes
    if "depth_um" in main:
        bits.append(f"D{int(main['depth_um'])}")
    if "width_um" in main:
        bits.append(f"W{int(main['width_um'])}")
    if "length_mm" in rung:
        bits.append(f"L{rung['length_mm']:g}")
    if "upstream_width_um" in rung:
        bits.append(f"U{int(rung['upstream_width_um'])}")
    if "N" in rung:
        bits.append(f"N{int(rung['N'])}")
    # manifold axes (arms count + rungs per arm)
    arms = params.get("arms", {}) if isinstance(params.get("arms"), dict) else {}
    if "count" in arms:
        bits.append(f"M{int(arms['count'])}")
    if "rungs_per_arm" in params:
        bits.append(f"n{int(params['rungs_per_arm'])}")
    # radial axes (radius + upstream channel width)
    if "radius_mm" in params:
        bits.append(f"R{params['radius_mm']:g}")
    if "upstream_width_um" in params:
        bits.append(f"U{int(params['upstream_width_um'])}")
    if "target_droplet_um" in params:
        bits.append(f"d{params['target_droplet_um']:g}um")
    # Junction exit — the axis that changes the physics per point, so it must be
    # visible in the label.  Without it a study of "same ladder, four different
    # exits" produced four identical labels, which silently collapsed the rows
    # of every downstream group-by.
    junction = params.get("junction", {}) if isinstance(params.get("junction"), dict) else {}
    if "exit_width_um" in junction or "exit_depth_um" in junction:
        ew = junction.get("exit_width_um")
        ed = junction.get("exit_depth_um")
        bits.append(f"E{ew:g}x{ed:g}" if ew is not None and ed is not None
                    else f"E{(ew if ew is not None else ed):g}")
    bits.append(f"Po{int(operating.get('Po_mbar', 0))}")
    return "_".join(bits)


def _fluid_tag(fluids: dict[str, Any]) -> str:
    """Compact discriminator for a fluid system: phase + dispersed viscosity."""
    bits: list[str] = []
    phase = str(fluids.get("phase_system", "") or "").replace("/", "")
    if phase:
        bits.append(phase)
    mu_d = fluids.get("mu_dispersed")
    if mu_d is not None:
        bits.append(f"mud{float(mu_d) * 1e3:g}")
    mu_c = fluids.get("mu_continuous")
    if mu_c is not None:
        bits.append(f"muc{float(mu_c) * 1e3:g}")
    gamma = fluids.get("gamma")
    if gamma:
        bits.append(f"g{float(gamma) * 1e3:g}")
    return "_".join(bits)


def _disambiguate(points: list["StudyPoint"]) -> None:
    """
    Make every label unique, in place.

    Geometry and Po go into the label at construction, but the *shared* blocks
    (fluids above all) do not — so a study that holds geometry fixed and sweeps
    the fluid system produces one label repeated N times.  Anything that groups
    or joins on label then silently merges rows that are not the same design.

    Only collided labels are touched, so studies that never sweep fluids keep
    exactly the labels they had.
    """
    from collections import defaultdict

    groups: dict[str, list[StudyPoint]] = defaultdict(list)
    for p in points:
        groups[p.label].append(p)

    for label, grp in groups.items():
        if len(grp) < 2:
            continue
        tags = [_fluid_tag(p.fluids) for p in grp]
        if len(set(tags)) == len(grp):                  # fluids explain it
            for p, tag in zip(grp, tags):
                object.__setattr__(p, "label", f"{label}__{tag}")
            continue
        # Fluids alone are not enough (footprint/manufacturing also swept, or a
        # genuine duplicate). Keep the fluid tag where it helps and add an index
        # so the label is still unique and still says what differs.
        for i, (p, tag) in enumerate(zip(grp, tags), start=1):
            suffix = f"{tag}__v{i}" if tag else f"v{i}"
            object.__setattr__(p, "label", f"{label}__{suffix}")


def build_points(raw: dict[str, Any]) -> list[StudyPoint]:
    """Expand a parsed study dict into the full list of :class:`StudyPoint`."""
    families = _as_list(raw.get("family", "serpentine"))
    shared = {b: raw.get(b, {}) for b in _SHARED_BLOCKS}

    points: list[StudyPoint] = []
    for family in families:
        geom_block = raw.get(family, {})
        # Expand the family's geometry + shared blocks together (each may sweep).
        space = {"geom": geom_block, **shared}
        for combo in expand_grid(space):
            params = combo["geom"] or {}
            operating = combo.get("operating", {}) or {}
            points.append(StudyPoint(
                family=family,
                label=_label_for(family, params, operating),
                params=params,
                fluids=combo.get("fluids", {}) or {},
                footprint=combo.get("footprint", {}) or {},
                manufacturing=combo.get("manufacturing", {}) or {},
                operating=operating,
            ))
    _disambiguate(points)
    return points


def build_study(
    raw: dict[str, Any],
    *,
    source_path: str | Path | None = None,
    source_text: str | None = None,
) -> Study:
    """
    Build a :class:`Study` from an already-parsed study *dict*.

    The intent layer runs first, so a study written as ``intent:`` +
    ``constraints:`` + ``explore:`` and one written out longhand converge on the
    same expanded dict before a single point is generated.

    Exposed separately from :func:`load_study_text` because relaxation pricing
    (:mod:`stepgen.studio.diagnosis`) rebuilds a study from a *mutated* raw dict
    — it has no text to re-parse, and round-tripping through YAML just to change
    one number would be a way to introduce differences.
    """
    from stepgen.studio.intent import expand_intent

    intent_raw = copy.deepcopy(raw)
    expanded, plan = expand_intent(raw)
    if plan is not None:
        # keep the recorded question complete: the resolved caps, not just the
        # preset name they came from (see Constraints.as_block)
        intent_raw["constraints"] = plan.constraints.as_block()

    return Study(
        title=str(expanded.get("title", "Untitled study")),
        goal=str(expanded.get("goal", "")),
        families=_as_list(expanded.get("family", "serpentine")),
        scoring=expanded.get("scoring", {}) or {},
        references=list(expanded.get("reference", []) or []),
        points=build_points(expanded),
        decide=expanded.get("decide", {}) or {},
        raw=expanded,
        source_path=None if source_path is None else str(source_path),
        source_text=source_text,
        intent_plan=plan,
        intent_raw=intent_raw if plan is not None else {},
    )


def load_study_text(text: str, source_path: str | Path | None = None) -> Study:
    """
    Expand a study YAML *string* into a :class:`Study`.

    This is the parse core shared by :func:`load_study` (file) and the
    interactive Studio UI (a live-edited text buffer), so both go through
    exactly the same expansion and metadata handling.
    """
    raw: dict[str, Any] = yaml.safe_load(text) or {}
    return build_study(raw, source_path=source_path, source_text=text)


def load_study(path: str | Path) -> Study:
    """Load and expand a study YAML file into a :class:`Study`."""
    text = Path(path).read_text(encoding="utf-8")
    return load_study_text(text, source_path=path)
