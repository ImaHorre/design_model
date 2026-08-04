"""
stepgen.studio.grouping
=======================
Split a study into **designs** and the **conditions** each design was run at.

A study config is one flat Cartesian product, so a point that differs by its
junction exit and a point that differs only by drive pressure arrive downstream
looking exactly alike — both are just rows with a long label.  That makes the
output unreadable in the one way that matters: "best throughput" gets answered
once, across every design *and* every operating point, when the question the
designer actually has is "for **this** design, which operating point is best, and
how does that compare with my other three designs".

This module draws that line.  Every leaf that varies across the study becomes an
:class:`Axis`; the axes are then split in two:

**design axes**
    what makes one design a different *device* — geometry.  Points sharing all
    design-axis values form one :class:`DesignGroup`.

**condition axes**
    what a single device can be *run* at, or made from — drive pressure, flow,
    fluid system, and any geometry axis the study explicitly declares as
    something to optimise over rather than something that defines a design.

Declaring it
------------
    decide:
      group_by: [junction.exit_width_um, junction.exit_depth_um]   # explicit
      # or
      within:   [main.length_mm]        # everything else geometric defines a design

With neither, every varying geometry axis defines a design and only
``operating:`` / ``fluids:`` count as conditions — the behaviour a study written
before this module gets for free.

Paths are dotted and namespaced by the block they live in: a bare path such as
``junction.exit_width_um`` reads the family geometry block, while
``operating.Po_mbar`` and ``fluids.gamma`` read the shared blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from stepgen.studio.study import Study, StudyPoint

#: shared blocks addressed by an explicit prefix; anything else is family geometry
_SHARED_NS = ("operating", "fluids", "footprint", "manufacturing")

#: conditions by default: how a device is *run*, not what it *is*
_DEFAULT_CONDITION_NS = ("operating", "fluids")

#: leaf name -> (human label, unit, format spec).  Anything not listed falls back
#: to a suffix rule, so a new geometry field still renders sensibly.
_AXIS_LOOKS: dict[str, tuple[str, str, str]] = {
    "main.depth_um":            ("Main depth", "µm", "int"),
    "main.width_um":            ("Main width", "µm", "int"),
    "main.length_mm":           ("Main length", "mm", "num1"),
    "rung.length_mm":           ("Rung length", "mm", "num1"),
    "rung.upstream_width_um":   ("Rung width", "µm", "int"),
    "rung.N":                   ("N per rung block", "", "int"),
    "junction.exit_width_um":   ("Exit width", "µm", "int"),
    "junction.exit_depth_um":   ("Exit depth", "µm", "int"),
    "junction.pitch_um":        ("Pitch", "µm", "int"),
    "target_droplet_um":        ("Droplet target", "µm", "num1"),
    "radius_mm":                ("Radius", "mm", "num1"),
    "upstream_width_um":        ("Upstream width", "µm", "int"),
    "arms.count":               ("Arms", "", "int"),
    "rungs_per_arm":            ("Rungs per arm", "", "int"),
    "operating.Po_mbar":        ("Po", "mbar", "int"),
    "operating.Qw_mlhr":        ("Qw", "mL/hr", "num1"),
    "operating.target_emulsion_pct": ("Target emulsion", "%", "num1"),
    "fluids.phase_system":      ("Phase", "", "text"),
    "fluids.mu_dispersed":      ("µ disp", "mPa·s", "visc"),
    "fluids.mu_continuous":     ("µ cont", "mPa·s", "visc"),
    "fluids.gamma":             ("γ", "mN/m", "tension"),
    "footprint.square_side_mm": ("Die side", "mm", "num1"),
}


def _looks(path: str) -> tuple[str, str, str]:
    """Human label, unit and format spec for a dotted *path*."""
    known = _AXIS_LOOKS.get(path)
    if known:
        return known
    leaf = path.rsplit(".", 1)[-1]
    for suffix, unit, spec in (("_um", "µm", "int"), ("_mm", "mm", "num1"),
                               ("_mbar", "mbar", "int"), ("_mlhr", "mL/hr", "num1"),
                               ("_pct", "%", "num1"), ("_hz", "Hz", "num1")):
        if leaf.endswith(suffix):
            return leaf[: -len(suffix)].replace("_", " ").capitalize(), unit, spec
    return leaf.replace("_", " ").capitalize(), "", "text"


def format_axis_value(value: Any, spec: str) -> str:
    """Render one axis value under its format *spec* (no unit appended)."""
    if value is None:
        return "—"
    if spec == "text" or isinstance(value, str) or isinstance(value, bool):
        return str(value)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:
        return "—"
    if spec == "visc":
        return f"{f * 1e3:g}"           # Pa·s -> mPa·s
    if spec == "tension":
        return f"{f * 1e3:g}"           # N/m -> mN/m
    if spec == "int":
        return f"{f:,.0f}"
    if spec == "num1":
        return f"{f:.1f}".rstrip("0").rstrip(".") if abs(f) < 1000 else f"{f:,.0f}"
    return f"{f:g}"


@dataclass(frozen=True)
class Axis:
    """One study leaf that takes more than one value."""

    path: str
    label: str
    unit: str
    spec: str
    values: tuple[Any, ...]          # distinct values, sorted where sortable
    namespace: str                   # "geometry" | "operating" | "fluids" | ...

    @property
    def is_numeric(self) -> bool:
        return all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in self.values)

    def show(self, value: Any) -> str:
        """Formatted value with its unit — e.g. ``80 mbar``."""
        text = format_axis_value(value, self.spec)
        return f"{text} {self.unit}".strip()

    def header(self) -> str:
        """Column header: label plus unit once, rather than on every cell."""
        return f"{self.label} ({self.unit})" if self.unit else self.label


def _walk(node: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    """Yield ``(dotted_path, leaf)`` for every scalar leaf of a nested dict."""
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk(value, path)
    elif isinstance(node, list):
        # a list that survived expansion is a leaf value in its own right
        yield prefix, tuple(node)
    else:
        yield prefix, node


def fluid_tag(fluids: dict[str, Any]) -> str:
    """
    One readable name for a whole fluid system.

    Fluid systems are declared as whole blocks (a list of dicts) precisely because
    their fields are not independent — phase, both viscosities and γ move
    together.  Spreading them across four table columns says four things vary
    when one thing does, so they collapse to a single axis whenever more than one
    of their fields differs across the study.
    """
    bits: list[str] = []
    phase = str(fluids.get("phase_system", "") or "").strip()
    if phase:
        bits.append(phase)
    mu_d, mu_c = fluids.get("mu_dispersed"), fluids.get("mu_continuous")
    if mu_d is not None and mu_c is not None:
        bits.append(f"µ {float(mu_d) * 1e3:g}/{float(mu_c) * 1e3:g}")
    elif mu_d is not None:
        bits.append(f"µ {float(mu_d) * 1e3:g}")
    gamma = fluids.get("gamma")
    if gamma:
        bits.append(f"γ {float(gamma) * 1e3:g}")
    return " · ".join(bits)


def point_leaves(point: StudyPoint) -> dict[str, Any]:
    """Every leaf of one point, keyed by namespaced dotted path."""
    out: dict[str, Any] = {}
    for path, value in _walk(point.params):
        out[path] = value
    for ns in _SHARED_NS:
        block = getattr(point, ns, None) or {}
        for path, value in _walk(block, ns):
            out[path] = value
    tag = fluid_tag(point.fluids or {})
    if tag:
        out["fluids"] = tag
    return out


def _sorted_values(values: set[Any]) -> tuple[Any, ...]:
    try:
        return tuple(sorted(values))
    except TypeError:
        return tuple(sorted(values, key=str))


def varying_axes(points: Sequence[StudyPoint]) -> list[Axis]:
    """
    Every path that takes more than one value across *points*, as an :class:`Axis`.

    A path missing from some points (families read different geometry blocks)
    counts as varying — the axis exists, it is simply N-A for those rows.
    """
    seen: dict[str, set[Any]] = {}
    for point in points:
        for path, value in point_leaves(point).items():
            try:
                hash(value)
            except TypeError:
                continue
            seen.setdefault(path, set()).add(value)

    axes: list[Axis] = []
    for path, values in seen.items():
        if len(values) < 2:
            continue
        if path == "fluids":
            axes.append(Axis(path="fluids", label="Fluid", unit="", spec="text",
                             values=_sorted_values(values), namespace="fluids"))
            continue
        label, unit, spec = _looks(path)
        ns = path.split(".", 1)[0] if path.split(".", 1)[0] in _SHARED_NS else "geometry"
        axes.append(Axis(path=path, label=label, unit=unit, spec=spec,
                         values=_sorted_values(values), namespace=ns))

    # the whole-system fluid axis replaces its own fields; see fluid_tag
    if any(a.path == "fluids" for a in axes):
        axes = [a for a in axes if not a.path.startswith("fluids.")]

    axes.sort(key=lambda a: (a.namespace != "geometry", a.path))
    return axes


# ---------------------------------------------------------------------------
# Design groups
# ---------------------------------------------------------------------------

@dataclass
class DesignGroup:
    """One design: the points that share every design-axis value."""

    gid: str                              # "D1" — short, stable, filterable
    key: tuple                            # design-axis values, in axis order
    values: dict[str, Any]                # path -> value
    indices: list[int] = field(default_factory=list)   # row indices in the study

    def label(self, axes: Sequence[Axis]) -> str:
        """Human name: the design axes spelled out, e.g. ``Exit 60x20 µm``."""
        bits = [f"{a.label} {a.show(self.values.get(a.path))}" for a in axes]
        return " · ".join(bits) if bits else "all designs"


@dataclass
class Grouping:
    """The full design/condition split of one study."""

    design_axes: list[Axis]
    condition_axes: list[Axis]
    groups: list[DesignGroup]
    group_of: dict[int, str]              # row index -> gid
    #: why the split came out this way, for the chapter to state plainly
    source: str = "auto"

    @property
    def is_split(self) -> bool:
        """True when there is more than one design to compare."""
        return len(self.groups) > 1

    def by_gid(self, gid: str) -> DesignGroup | None:
        return next((g for g in self.groups if g.gid == gid), None)


def _declared(decide: dict[str, Any], key: str) -> list[str]:
    raw = (decide or {}).get(key) or []
    return [str(p) for p in raw] if isinstance(raw, (list, tuple)) else [str(raw)]


def build_grouping(study: Study, points: Sequence[StudyPoint] | None = None) -> Grouping:
    """
    Split *study* into design groups and the conditions explored inside them.

    Precedence: an explicit ``decide.group_by`` wins; otherwise every varying
    geometry axis defines a design, minus anything listed in ``decide.within``.
    """
    points = list(points if points is not None else study.points)
    axes = varying_axes(points)
    by_path = {a.path: a for a in axes}

    group_by = _declared(study.decide, "group_by")
    within = set(_declared(study.decide, "within"))

    if group_by:
        design_paths = [p for p in group_by if p in by_path]
        source = "declared by decide.group_by"
        missing = [p for p in group_by if p not in by_path]
        if missing:
            source += f" (ignored, not varying: {', '.join(missing)})"
    else:
        design_paths = [a.path for a in axes
                        if a.namespace not in _DEFAULT_CONDITION_NS
                        and a.path not in within]
        source = ("geometry defines a design"
                  + (f"; optimised within: {', '.join(sorted(within))}" if within else ""))

    design_axes = [by_path[p] for p in design_paths]
    condition_axes = [a for a in axes if a.path not in set(design_paths)]

    groups: list[DesignGroup] = []
    index: dict[tuple, DesignGroup] = {}
    group_of: dict[int, str] = {}
    for i, point in enumerate(points):
        leaves = point_leaves(point)
        key = tuple(leaves.get(a.path) for a in design_axes)
        group = index.get(key)
        if group is None:
            group = DesignGroup(gid=f"D{len(groups) + 1}", key=key,
                                values={a.path: leaves.get(a.path) for a in design_axes})
            index[key] = group
            groups.append(group)
        group.indices.append(i)
        group_of[i] = group.gid

    return Grouping(design_axes=design_axes, condition_axes=condition_axes,
                    groups=groups, group_of=group_of, source=source)


def row_axis_values(point: StudyPoint, axes: Sequence[Axis]) -> dict[str, Any]:
    """This point's value on each of *axes* — the structured replacement for a label."""
    leaves = point_leaves(point)
    return {a.path: leaves.get(a.path) for a in axes}
