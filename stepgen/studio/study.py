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
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# keys that carry study-level metadata and must not be treated as swept axes
_META_KEYS = frozenset({"title", "goal", "family", "scoring", "reference"})

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
    raw: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None
    source_text: str | None = None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _label_for(family: str, params: dict[str, Any], operating: dict[str, Any]) -> str:
    """A short, stable, human-readable label from the point's swept params."""
    bits: list[str] = [family]
    main = params.get("main", {}) if isinstance(params.get("main"), dict) else {}
    rung = params.get("rung", {}) if isinstance(params.get("rung"), dict) else {}
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
    if "target_droplet_um" in params:
        bits.append(f"d{params['target_droplet_um']:g}um")
    bits.append(f"Po{int(operating.get('Po_mbar', 0))}")
    return "_".join(bits)


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
    return points


def load_study(path: str | Path) -> Study:
    """Load and expand a study YAML file into a :class:`Study`."""
    text = Path(path).read_text(encoding="utf-8")
    raw: dict[str, Any] = yaml.safe_load(text) or {}

    points = build_points(raw)
    return Study(
        title=str(raw.get("title", "Untitled study")),
        goal=str(raw.get("goal", "")),
        families=_as_list(raw.get("family", "serpentine")),
        scoring=raw.get("scoring", {}) or {},
        references=list(raw.get("reference", []) or []),
        points=points,
        raw=raw,
        source_path=str(path),
        source_text=text,
    )
