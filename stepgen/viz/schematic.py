"""
stepgen.viz.schematic
=====================
The universal to-scale device renderer.

Phase 3 of the Design Studio.  You cannot check a packing model by reading its
output number — the manifold arm pitch was wrong by 10-20x and every metric
derived from it looked entirely reasonable.  You check it by drawing the device
to scale and looking at it.

The split
---------
This module is the **drawing engine**, and it is topology-agnostic.  It knows
about rectangles, annular sectors, repeated-unit zones and dimension arrows in
device coordinates (metres, y-up).  It knows nothing about serpentines, hubs or
combs.

The **shape declaration** lives with each family, behind
``Family.render_schematic(compiled, view)``, and is emitted from *the same
compiled object the solver consumed*.  That is the anti-drift guarantee: there
is exactly one source of geometry, so a change to a family's packing maths
changes its drawing automatically.  A renderer that re-derived geometry from the
YAML would be a second packing model free to disagree with the first — which is
the very failure this phase exists to catch.

Honesty rules
-------------
1. **Draw only what the solver used.**  Anything added for legibility that the
   model does not actually compute goes in :attr:`Schematic.inventions` and is
   listed under the drawing.  A schematic that quietly infills plausible
   geometry looks right and lies.
2. **Never fake resolution.**  At 11,550 DFUs the individual features are far
   below a pixel.  A :class:`Zone` collapses to a labelled density band rather
   than drawing 11,550 unreadable rectangles; the zoom view is where real
   individual units are drawn, at true scale.
3. **State the scale.**  Every drawing carries a scale bar and its extent, so
   "to scale" is checkable rather than asserted.

Coordinates
-----------
Device coordinates are **metres, y-up, origin at the die's bottom-left**.  The
renderer converts to SVG user units of **millimetres, y-down** at emit time.

Public API
----------
    Rect / Arc / Zone / Dim / Label   primitives
    Schematic                         one drawing (prims + extent + provenance)
    PackingCapacity                   how full the die is, and what limits it
    to_svg(schematic)                 self-contained inline SVG
    to_interactive_html(schematic)    SVG + vanilla pan/zoom, no external libs
    ROLE_STYLE                        the shared role -> colour table
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from typing import Iterable, Literal, Sequence

__all__ = [
    "Rect", "Arc", "Zone", "AnnularZone", "Circle", "Dim", "Label",
    "Schematic", "PackingCapacity",
    "to_svg", "to_interactive_html", "schematic_block", "panzoom_js",
    "ROLE_STYLE", "MAX_DRAWN_UNITS",
]


# ---------------------------------------------------------------------------
# Level of detail
# ---------------------------------------------------------------------------

#: Above this many repeated units in a single zone, the zone is drawn as a
#: hatched density band with a count label instead of individual features.
#: Chosen so a 63.5 mm die still resolves each unit at ~0.15 mm on screen —
#: below that the drawing is a grey smear that merely *looks* detailed.
MAX_DRAWN_UNITS = 240

#: A unit narrower than this fraction of the drawing extent is never drawn
#: individually regardless of count — it would be sub-pixel.
MIN_UNIT_FRACTION = 1.5e-3


# ---------------------------------------------------------------------------
# Role styling — one table, shared by every family and both views
# ---------------------------------------------------------------------------

#: role -> (fill, stroke, opacity, hatch)
#: Colours are chosen to stay legible on white and on the dark Streamlit theme;
#: the SVG paints its own light background so it never depends on the host.
ROLE_STYLE: dict[str, tuple[str, str, float, bool]] = {
    # dispersed (oil) side — warm
    "oil_main":   ("#e8871a", "#a85f0d", 0.85, False),
    "spine":      ("#e8871a", "#a85f0d", 0.85, False),
    "arm":        ("#f0a04b", "#a85f0d", 0.80, False),
    "hub":        ("#c96a10", "#8a4708", 0.90, False),
    # continuous (water) side — cool
    "water_main": ("#2f7fc1", "#1d5182", 0.85, False),
    "cont_phase": ("#5aa4d8", "#1d5182", 0.70, False),
    # the droplet-forming units themselves — green
    "dfu":        ("#3f9e57", "#256b39", 0.75, True),
    "exit":       ("#1f7a3a", "#124a23", 0.95, False),
    # structure
    "wall":       ("#9aa0a6", "#6b7075", 0.55, False),
    "turn":       ("#c4c9ce", "#8d9297", 0.45, False),
    "die":        ("none",    "#202124", 1.00, False),
    "border":     ("none",    "#9aa0a6", 1.00, False),
    "overflow":   ("#d93025", "#a52318", 0.25, False),
}

_FALLBACK_STYLE = ("#b0b6bb", "#71767a", 0.6, False)

#: human-readable legend names, in drawing order
ROLE_LABEL: dict[str, str] = {
    "oil_main": "oil main (dispersed)",
    "spine": "primary spine (dispersed)",
    "arm": "arm (dispersed)",
    "hub": "hub / inlet",
    "water_main": "water main (continuous)",
    "cont_phase": "continuous-phase collection",
    "dfu": "DFU / rung array",
    "exit": "junction exit",
    "wall": "separating wall",
    "turn": "turn allowance",
    "overflow": "outside the die",
}


def _style(role: str) -> tuple[str, str, float, bool]:
    return ROLE_STYLE.get(role, _FALLBACK_STYLE)


# ---------------------------------------------------------------------------
# Primitives — all lengths in METRES, device coordinates, y-up
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle. ``(x, y)`` is the bottom-left corner."""
    x: float
    y: float
    w: float
    h: float
    role: str
    label: str | None = None
    dashed: bool = False


@dataclass(frozen=True)
class Arc:
    """
    An annular sector — the honest primitive for both serpentine turns and
    radial spokes.  Angles in radians, measured CCW from +x.
    """
    cx: float
    cy: float
    r_in: float
    r_out: float
    a0: float
    a1: float
    role: str
    label: str | None = None
    dashed: bool = False


@dataclass(frozen=True)
class Zone:
    """
    A band holding ``count`` identical units repeated along ``axis``.

    This is the level-of-detail primitive.  Below :data:`MAX_DRAWN_UNITS` the
    renderer draws every unit at true size; above it, a hatched band carrying
    the count.  Either way the *band* is at true scale — only the internal
    features collapse, and the label says so.
    """
    x: float
    y: float
    w: float
    h: float
    role: str
    count: int
    unit_w: float
    unit_h: float
    pitch: float
    axis: Literal["x", "y"] = "x"
    label: str | None = None


@dataclass(frozen=True)
class AnnularZone:
    """
    The polar counterpart of :class:`Zone` — ``count`` radial features spread
    around an annulus, as a radial spoke array is.

    Same level-of-detail contract: the annulus is always true-scale, the
    individual spokes collapse to a density fill once there are too many to
    resolve.  ``unit_w`` is the spoke's tangential width at the outer radius.
    """
    cx: float
    cy: float
    r_in: float
    r_out: float
    a0: float
    a1: float
    role: str
    count: int
    unit_w: float
    label: str | None = None


@dataclass(frozen=True)
class Circle:
    """A filled disc — hubs and inlet ports."""
    cx: float
    cy: float
    r: float
    role: str
    label: str | None = None


@dataclass(frozen=True)
class Dim:
    """A dimension annotation drawn as a double-headed arrow with a label."""
    x0: float
    y0: float
    x1: float
    y1: float
    label: str
    offset: float = 0.0          # perpendicular offset [m], for legibility


@dataclass(frozen=True)
class Label:
    """Free text pinned at a device coordinate."""
    x: float
    y: float
    text: str
    anchor: Literal["start", "middle", "end"] = "middle"
    size: float = 1.0            # relative to the base font size


Prim = Rect | Arc | Zone | AnnularZone | Circle | Dim | Label


# ---------------------------------------------------------------------------
# Packing capacity — the generative readout
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PackingCapacity:
    """
    How many DFUs this footprint actually holds, versus how many are configured.

    The layout model has historically been a *checker* — you write ``N`` and it
    reports whether the fold fits.  That answers "is this legal" but not "what
    could I have".  ``n_max`` inverts it: the largest DFU count this die holds at
    the current pitch and lane geometry, so growing the die square visibly buys
    you DFUs instead of merely turning a gate green.

    Attributes
    ----------
    n_current    : DFU count as configured.
    n_max        : largest DFU count that fits this footprint, same geometry.
    utilisation  : ``n_current / n_max`` (may exceed 1 when the design overflows).
    limited_by   : the dimension that binds — e.g. ``"die height (lane stack)"``.
    fits         : whether the configured design fits.
    detail       : free-form per-family numbers for the readout.
    """
    n_current: int
    n_max: int
    utilisation: float
    limited_by: str
    fits: bool
    detail: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The drawing
# ---------------------------------------------------------------------------

@dataclass
class Schematic:
    """
    One to-scale drawing of one compiled design.

    Attributes
    ----------
    family      : family name that produced it.
    view        : ``"device"`` (whole die) or ``"zoom"`` (a few DFUs at true scale).
    prims       : the primitives, in draw order (later paints over earlier).
    extent      : ``(x0, y0, x1, y1)`` in metres — the drawn region.
    die_side_m  : die square side, drawn as the boundary. ``None`` if N-A.
    title       : heading for the drawing.
    subtitle    : one line of context (usually the design label).
    notes       : observations worth reading next to the picture.
    inventions  : things drawn for legibility that the model does NOT compute.
                  Rendered under the drawing, always visible. See module docs.
    fits        : whether the design fits its footprint (drives the overflow tint).
    capacity    : optional packing readout shown beside the drawing.
    """
    family: str
    view: Literal["device", "zoom"]
    prims: list[Prim]
    extent: tuple[float, float, float, float]
    die_side_m: float | None = None
    title: str = ""
    subtitle: str = ""
    notes: list[str] = field(default_factory=list)
    inventions: list[str] = field(default_factory=list)
    fits: bool | None = None
    capacity: PackingCapacity | None = None

    # -- convenience -------------------------------------------------------
    @property
    def width_m(self) -> float:
        return self.extent[2] - self.extent[0]

    @property
    def height_m(self) -> float:
        return self.extent[3] - self.extent[1]

    def roles_used(self) -> list[str]:
        """Roles actually present, in :data:`ROLE_LABEL` order (for the legend)."""
        present = set()
        for p in self.prims:
            role = getattr(p, "role", None)
            if role:
                present.add(role)
        return [r for r in ROLE_LABEL if r in present]


# ---------------------------------------------------------------------------
# SVG emission
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    """Format a millimetre value compactly, avoiding scientific notation."""
    if abs(v) < 1e-4:
        return "0"
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _nice_scale_length(span_mm: float) -> float:
    """Pick a round scale-bar length no more than ~a quarter of the span."""
    target = span_mm / 4.0
    if target <= 0:
        return 1.0
    exp = math.floor(math.log10(target))
    for mult in (5.0, 2.0, 1.0):
        cand = mult * (10.0 ** exp)
        if cand <= target:
            return cand
    return 10.0 ** exp


class _Emitter:
    """
    Accumulates SVG in device->mm coordinates with a single y-flip.

    Device metres are converted to millimetres, and y is flipped once here
    (``y_svg = top_mm - y_mm``) so every primitive can be written in natural
    y-up terms.
    """

    def __init__(self, extent: tuple[float, float, float, float], pad_frac: float = 0.06):
        x0, y0, x1, y1 = extent
        w = max(x1 - x0, 1e-9)
        h = max(y1 - y0, 1e-9)
        pad = max(w, h) * pad_frac
        self.x0_mm = (x0 - pad) * 1e3
        self.y0_mm = (y0 - pad) * 1e3
        self.w_mm = (w + 2 * pad) * 1e3
        self.h_mm = (h + 2 * pad) * 1e3
        self.top_mm = self.y0_mm + self.h_mm
        # A stroke that reads the same regardless of how big the device is.
        self.hair = max(self.w_mm, self.h_mm) * 0.0012
        self.font = max(self.w_mm, self.h_mm) * 0.016
        self.parts: list[str] = []

    # -- coordinate transform ---------------------------------------------
    def X(self, x_m: float) -> float:
        return x_m * 1e3

    def Y(self, y_m: float) -> float:
        """Device y (metres, up) -> SVG y (mm, down)."""
        return self.top_mm - y_m * 1e3

    def add(self, svg: str) -> None:
        self.parts.append(svg)

    # -- primitive writers -------------------------------------------------
    def rect(self, r: Rect) -> None:
        fill, stroke, op, hatch = _style(r.role)
        x, y = self.X(r.x), self.Y(r.y + r.h)     # SVG rect anchors top-left
        w, h = r.w * 1e3, r.h * 1e3
        dash = f' stroke-dasharray="{_fmt(self.hair * 4)},{_fmt(self.hair * 3)}"' if r.dashed else ""
        self.add(
            f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
            f'fill="{fill}" fill-opacity="{op}" stroke="{stroke}" '
            f'stroke-width="{_fmt(self.hair)}"{dash} />'
        )
        if hatch:
            self.add(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'fill="url(#hatch)" stroke="none" />'
            )
        if r.label:
            self.text(r.x + r.w / 2, r.y + r.h / 2, r.label, size=0.8)

    def arc(self, a: Arc) -> None:
        fill, stroke, op, _ = _style(a.role)
        large = 1 if abs(a.a1 - a.a0) > math.pi else 0
        sweep_out, sweep_in = 1, 0
        # SVG y is flipped, so a CCW device sweep is CW on screen.
        p0o = (self.X(a.cx + a.r_out * math.cos(a.a0)), self.Y(a.cy + a.r_out * math.sin(a.a0)))
        p1o = (self.X(a.cx + a.r_out * math.cos(a.a1)), self.Y(a.cy + a.r_out * math.sin(a.a1)))
        p1i = (self.X(a.cx + a.r_in * math.cos(a.a1)), self.Y(a.cy + a.r_in * math.sin(a.a1)))
        p0i = (self.X(a.cx + a.r_in * math.cos(a.a0)), self.Y(a.cy + a.r_in * math.sin(a.a0)))
        ro, ri = a.r_out * 1e3, a.r_in * 1e3
        dash = f' stroke-dasharray="{_fmt(self.hair * 4)},{_fmt(self.hair * 3)}"' if a.dashed else ""
        d = (
            f"M {_fmt(p0o[0])} {_fmt(p0o[1])} "
            f"A {_fmt(ro)} {_fmt(ro)} 0 {large} {sweep_out} {_fmt(p1o[0])} {_fmt(p1o[1])} "
            f"L {_fmt(p1i[0])} {_fmt(p1i[1])} "
            f"A {_fmt(ri)} {_fmt(ri)} 0 {large} {sweep_in} {_fmt(p0i[0])} {_fmt(p0i[1])} Z"
        )
        self.add(
            f'<path d="{d}" fill="{fill}" fill-opacity="{op}" stroke="{stroke}" '
            f'stroke-width="{_fmt(self.hair)}"{dash} />'
        )

    def zone(self, z: Zone, extent_m: float) -> None:
        """
        Draw a repeated-unit band, collapsing to a density band when the units
        would be unreadable.  The band itself is always at true scale.
        """
        fill, stroke, op, _ = _style(z.role)
        draw_units = (
            z.count <= MAX_DRAWN_UNITS
            and z.unit_w >= extent_m * MIN_UNIT_FRACTION
            and z.pitch > 0
        )

        # the containing band, always true-scale, faint
        self.add(
            f'<rect x="{_fmt(self.X(z.x))}" y="{_fmt(self.Y(z.y + z.h))}" '
            f'width="{_fmt(z.w * 1e3)}" height="{_fmt(z.h * 1e3)}" '
            f'fill="{fill}" fill-opacity="{op * 0.25:.3f}" stroke="{stroke}" '
            f'stroke-width="{_fmt(self.hair)}" />'
        )

        if draw_units:
            for i in range(z.count):
                if z.axis == "x":
                    ux = z.x + i * z.pitch
                    uy = z.y + (z.h - z.unit_h) / 2.0
                    if ux + z.unit_w > z.x + z.w + 1e-12:
                        break
                else:
                    ux = z.x + (z.w - z.unit_w) / 2.0
                    uy = z.y + i * z.pitch
                    if uy + z.unit_h > z.y + z.h + 1e-12:
                        break
                self.add(
                    f'<rect x="{_fmt(self.X(ux))}" y="{_fmt(self.Y(uy + z.unit_h))}" '
                    f'width="{_fmt(z.unit_w * 1e3)}" height="{_fmt(z.unit_h * 1e3)}" '
                    f'fill="{fill}" fill-opacity="{op}" stroke="none" />'
                )
        else:
            self.add(
                f'<rect x="{_fmt(self.X(z.x))}" y="{_fmt(self.Y(z.y + z.h))}" '
                f'width="{_fmt(z.w * 1e3)}" height="{_fmt(z.h * 1e3)}" '
                f'fill="url(#dense)" stroke="none" />'
            )

        if z.label:
            self.text(z.x + z.w / 2, z.y + z.h / 2, z.label, size=0.75)

    def annular_zone(self, z: AnnularZone) -> None:
        """Polar LOD: true-scale annulus, spokes drawn only while resolvable."""
        fill, stroke, op, _ = _style(z.role)
        # faint true-scale band
        self.arc(Arc(z.cx, z.cy, z.r_in, z.r_out, z.a0, z.a1, z.role))

        span = abs(z.a1 - z.a0)
        r_mid = (z.r_in + z.r_out) / 2.0
        arclen = span * r_mid
        draw = (
            z.count <= MAX_DRAWN_UNITS
            and z.count > 0
            and z.unit_w >= (self.w_mm * 1e-3) * MIN_UNIT_FRACTION
        )
        if draw and r_mid > 0:
            half = (z.unit_w / r_mid) / 2.0          # angular half-width
            for i in range(z.count):
                a = z.a0 + span * (i + 0.5) / z.count
                self.arc(Arc(z.cx, z.cy, z.r_in, z.r_out,
                             a - half, a + half, "exit"))
        elif z.count > 0:
            # density ring — the band is real, the individual spokes are not drawn
            p0 = (self.X(z.cx + z.r_out * math.cos(z.a0)), self.Y(z.cy + z.r_out * math.sin(z.a0)))
            p1 = (self.X(z.cx + z.r_out * math.cos(z.a1)), self.Y(z.cy + z.r_out * math.sin(z.a1)))
            p1i = (self.X(z.cx + z.r_in * math.cos(z.a1)), self.Y(z.cy + z.r_in * math.sin(z.a1)))
            p0i = (self.X(z.cx + z.r_in * math.cos(z.a0)), self.Y(z.cy + z.r_in * math.sin(z.a0)))
            large = 1 if span > math.pi else 0
            ro, ri = z.r_out * 1e3, z.r_in * 1e3
            d = (f"M {_fmt(p0[0])} {_fmt(p0[1])} A {_fmt(ro)} {_fmt(ro)} 0 {large} 1 "
                 f"{_fmt(p1[0])} {_fmt(p1[1])} L {_fmt(p1i[0])} {_fmt(p1i[1])} "
                 f"A {_fmt(ri)} {_fmt(ri)} 0 {large} 0 {_fmt(p0i[0])} {_fmt(p0i[1])} Z")
            self.add(f'<path d="{d}" fill="url(#dense)" stroke="none" />')

        if z.label:
            am = (z.a0 + z.a1) / 2.0
            self.text(z.cx + r_mid * math.cos(am), z.cy + r_mid * math.sin(am),
                      z.label, size=0.75)

    def circle(self, c: Circle) -> None:
        fill, stroke, op, _ = _style(c.role)
        self.add(
            f'<circle cx="{_fmt(self.X(c.cx))}" cy="{_fmt(self.Y(c.cy))}" '
            f'r="{_fmt(c.r * 1e3)}" fill="{fill}" fill-opacity="{op}" '
            f'stroke="{stroke}" stroke-width="{_fmt(self.hair)}" />'
        )
        if c.label:
            self.text(c.cx, c.cy, c.label, size=0.75)

    def dim(self, d: Dim) -> None:
        x0, y0 = self.X(d.x0), self.Y(d.y0)
        x1, y1 = self.X(d.x1), self.Y(d.y1)
        self.add(
            f'<line x1="{_fmt(x0)}" y1="{_fmt(y0)}" x2="{_fmt(x1)}" y2="{_fmt(y1)}" '
            f'stroke="#5f6368" stroke-width="{_fmt(self.hair)}" '
            f'marker-start="url(#a0)" marker-end="url(#a1)" />'
        )
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        vertical = abs(y1 - y0) > abs(x1 - x0)
        dx = -self.font * 0.4 if vertical else 0.0
        dy = 0.0 if vertical else -self.font * 0.4
        anchor = "end" if vertical else "middle"
        self.add(
            f'<text x="{_fmt(mx + dx)}" y="{_fmt(my + dy)}" text-anchor="{anchor}" '
            f'dominant-baseline="middle" font-size="{_fmt(self.font * 0.8)}" '
            f'fill="#3c4043" font-family="ui-monospace,SFMono-Regular,Menlo,monospace">'
            f'{_esc(d.label)}</text>'
        )

    def text(self, x_m: float, y_m: float, s: str, *,
             anchor: str = "middle", size: float = 1.0, colour: str = "#202124") -> None:
        self.add(
            f'<text x="{_fmt(self.X(x_m))}" y="{_fmt(self.Y(y_m))}" '
            f'text-anchor="{anchor}" dominant-baseline="middle" '
            f'font-size="{_fmt(self.font * size)}" fill="{colour}" '
            f'font-family="ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif">'
            f'{_esc(s)}</text>'
        )


def _defs(em: _Emitter) -> str:
    """Hatch/density patterns and dimension arrowheads."""
    a = em.hair * 6
    return (
        "<defs>"
        f'<pattern id="hatch" width="{_fmt(a)}" height="{_fmt(a)}" '
        f'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="{_fmt(a)}" stroke="#256b39" '
        f'stroke-width="{_fmt(em.hair * 0.8)}" stroke-opacity="0.5"/></pattern>'
        f'<pattern id="dense" width="{_fmt(a * 0.6)}" height="{_fmt(a * 0.6)}" '
        f'patternUnits="userSpaceOnUse">'
        f'<rect width="{_fmt(a * 0.3)}" height="{_fmt(a * 0.6)}" fill="#3f9e57" '
        f'fill-opacity="0.55"/></pattern>'
        f'<marker id="a0" markerWidth="6" markerHeight="6" refX="5" refY="3" '
        f'orient="auto"><path d="M6,0 L6,6 L0,3 z" fill="#5f6368"/></marker>'
        f'<marker id="a1" markerWidth="6" markerHeight="6" refX="1" refY="3" '
        f'orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#5f6368"/></marker>'
        "</defs>"
    )


def _chrome(em: _Emitter, sch: Schematic) -> str:
    """Scale bar + legend + extent caption, in the padding margin."""
    out: list[str] = []
    bar_mm = _nice_scale_length(max(em.w_mm, em.h_mm))
    bx = em.x0_mm + em.w_mm * 0.02
    by = em.y0_mm + em.h_mm * 0.965
    fs = em.font * 0.85

    out.append(
        f'<line x1="{_fmt(bx)}" y1="{_fmt(by)}" x2="{_fmt(bx + bar_mm)}" y2="{_fmt(by)}" '
        f'stroke="#202124" stroke-width="{_fmt(em.hair * 2)}" />'
    )
    for ex in (bx, bx + bar_mm):
        out.append(
            f'<line x1="{_fmt(ex)}" y1="{_fmt(by - em.h_mm * 0.008)}" '
            f'x2="{_fmt(ex)}" y2="{_fmt(by + em.h_mm * 0.008)}" '
            f'stroke="#202124" stroke-width="{_fmt(em.hair * 2)}" />'
        )
    bar_lbl = f"{bar_mm:g} mm" if bar_mm >= 1 else f"{bar_mm * 1e3:g} µm"
    out.append(
        f'<text x="{_fmt(bx + bar_mm / 2)}" y="{_fmt(by - em.h_mm * 0.016)}" '
        f'text-anchor="middle" font-size="{_fmt(fs)}" fill="#202124" '
        f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace">{bar_lbl}</text>'
    )

    # legend, top-left of the margin
    lx = em.x0_mm + em.w_mm * 0.02
    ly = em.y0_mm + em.h_mm * 0.035
    sw = em.w_mm * 0.018
    for i, role in enumerate(sch.roles_used()):
        fill, stroke, op, _ = _style(role)
        yy = ly + i * fs * 1.55
        out.append(
            f'<rect x="{_fmt(lx)}" y="{_fmt(yy - fs * 0.6)}" width="{_fmt(sw)}" '
            f'height="{_fmt(fs * 0.9)}" fill="{fill}" fill-opacity="{op}" '
            f'stroke="{stroke}" stroke-width="{_fmt(em.hair)}" />'
        )
        out.append(
            f'<text x="{_fmt(lx + sw * 1.4)}" y="{_fmt(yy)}" font-size="{_fmt(fs)}" '
            f'dominant-baseline="middle" fill="#3c4043" '
            f'font-family="ui-sans-serif,system-ui,sans-serif">'
            f'{_esc(ROLE_LABEL.get(role, role))}</text>'
        )

    # extent caption, bottom-right — makes "to scale" checkable
    out.append(
        f'<text x="{_fmt(em.x0_mm + em.w_mm * 0.98)}" y="{_fmt(by)}" text-anchor="end" '
        f'font-size="{_fmt(fs)}" fill="#5f6368" '
        f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace">'
        f'view {sch.width_m * 1e3:.3g} x {sch.height_m * 1e3:.3g} mm</text>'
    )
    return "".join(out)


def to_svg(sch: Schematic, *, width_px: int = 760, chrome: bool = True) -> str:
    """
    Render a :class:`Schematic` to a self-contained inline ``<svg>`` string.

    No external stylesheet, font or script is referenced, so the same output
    drops into the HTML workbook and the Streamlit UI unchanged.

    Parameters
    ----------
    sch      : the schematic to draw.
    width_px : nominal on-screen width; height follows the true aspect ratio.
    chrome   : draw the scale bar, legend and extent caption.
    """
    em = _Emitter(sch.extent)
    extent_m = max(sch.width_m, sch.height_m)

    # die square first, so everything paints over it
    if sch.die_side_m:
        em.add(
            f'<rect x="0" y="{_fmt(em.Y(sch.die_side_m))}" '
            f'width="{_fmt(sch.die_side_m * 1e3)}" height="{_fmt(sch.die_side_m * 1e3)}" '
            f'fill="none" stroke="#202124" stroke-width="{_fmt(em.hair * 2.5)}" '
            f'stroke-dasharray="{_fmt(em.hair * 8)},{_fmt(em.hair * 5)}" />'
        )

    dims: list[Dim] = []
    labels: list[Label] = []
    for p in sch.prims:
        if isinstance(p, Rect):
            em.rect(p)
        elif isinstance(p, Arc):
            em.arc(p)
        elif isinstance(p, Zone):
            em.zone(p, extent_m)
        elif isinstance(p, AnnularZone):
            em.annular_zone(p)
        elif isinstance(p, Circle):
            em.circle(p)
        elif isinstance(p, Dim):
            dims.append(p)
        elif isinstance(p, Label):
            labels.append(p)
    # annotations last so they are never painted over
    for d in dims:
        em.dim(d)
    for lb in labels:
        em.text(lb.x, lb.y, lb.text, anchor=lb.anchor, size=lb.size)

    body = "".join(em.parts)
    chrome_svg = _chrome(em, sch) if chrome else ""
    height_px = int(width_px * em.h_mm / max(em.w_mm, 1e-9))

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{_fmt(em.x0_mm)} {_fmt(em.y0_mm)} {_fmt(em.w_mm)} {_fmt(em.h_mm)}" '
        f'width="{width_px}" height="{height_px}" '
        f'style="max-width:100%;height:auto;background:#fbfbfa;border-radius:6px" '
        f'role="img" aria-label="{_esc(sch.title or sch.family)}">'
        f'{_defs(em)}<g id="scene">{body}</g>{chrome_svg}</svg>'
    )


# ---------------------------------------------------------------------------
# Interactive wrapper — live pan/zoom, no external libraries
# ---------------------------------------------------------------------------

_PANZOOM_BODY = """
(function(){
  if(window.__stepgenPanzoom) { window.__stepgenPanzoomScan(); return; }
  function attach(root){
    if(root.__pz) return; root.__pz = 1;
    var svg = root.querySelector('svg'); if(!svg) return;
    var vb = svg.getAttribute('viewBox').split(/\\s+/).map(Number);
    var cur = vb.slice();
    var readout = root.querySelector('.zoomlbl');
    function apply(){
      svg.setAttribute('viewBox', cur.join(' '));
      if(readout){ readout.textContent = (vb[2]/cur[2]).toFixed(1) + 'x'; }
    }
    svg.addEventListener('wheel', function(e){
      e.preventDefault();
      var r = svg.getBoundingClientRect();
      var fx = (e.clientX - r.left)/r.width, fy = (e.clientY - r.top)/r.height;
      var k = e.deltaY < 0 ? 0.85 : 1/0.85;
      var nw = cur[2]*k, nh = cur[3]*k;
      if(nw > vb[2]*4 || nw < vb[2]/4000) return;
      cur[0] += (cur[2]-nw)*fx; cur[1] += (cur[3]-nh)*fy;
      cur[2] = nw; cur[3] = nh; apply();
    }, {passive:false});
    var drag=false, px=0, py=0;
    svg.addEventListener('pointerdown', function(e){
      drag=true; px=e.clientX; py=e.clientY;
      try{ svg.setPointerCapture(e.pointerId); }catch(_){}
      svg.style.cursor='grabbing';
    });
    svg.addEventListener('pointermove', function(e){
      if(!drag) return;
      var r = svg.getBoundingClientRect();
      cur[0] -= (e.clientX-px)*cur[2]/r.width;
      cur[1] -= (e.clientY-py)*cur[3]/r.height;
      px=e.clientX; py=e.clientY; apply();
    });
    function end(){ drag=false; svg.style.cursor='grab'; }
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointerleave', end);
    var rb = root.querySelector('.resetbtn');
    if(rb) rb.addEventListener('click', function(){ cur = vb.slice(); apply(); });
    svg.style.cursor='grab'; svg.style.touchAction='none';
  }
  function scan(){
    var els = document.querySelectorAll('[data-panzoom]');
    for(var i=0;i<els.length;i++) attach(els[i]);
  }
  window.__stepgenPanzoom = attach;
  window.__stepgenPanzoomScan = scan;
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', scan);
  } else { scan(); }
})();
"""


def panzoom_js() -> str:
    """
    The pan/zoom initialiser, as a bare script body.

    Emit it **once per document** and every ``[data-panzoom]`` container on the
    page becomes interactive.  The workbook needs this: a chapter can carry
    hundreds of drill-down rows, and one script per drawing would bloat the file
    for no benefit.
    """
    return _PANZOOM_BODY


def schematic_block(sch: Schematic, *, width_px: int = 760, uid: str = "sch",
                    show_notes: bool = True, controls: bool = True) -> str:
    """
    The drawing plus its caption, notes and inventions — **without** a script.

    Pair with a single :func:`panzoom_js` on the page.  :func:`to_interactive_html`
    is this plus its own inline script, for standalone use.
    """
    svg = to_svg(sch, width_px=width_px)
    head = (
        f'<div style="font:600 14px ui-sans-serif,system-ui,sans-serif;color:#202124;'
        f'margin:0 0 2px">{_esc(sch.title)}</div>'
        f'<div style="font:12px ui-monospace,Menlo,monospace;color:#5f6368;margin:0 0 8px">'
        f'{_esc(sch.subtitle)}</div>'
    ) if (sch.title or sch.subtitle) else ""

    bar = (
        f'<div style="display:flex;gap:10px;align-items:center;margin:6px 0 0;'
        f'font:12px ui-monospace,Menlo,monospace;color:#5f6368">'
        f'<button class="resetbtn" style="font:12px ui-sans-serif,system-ui,sans-serif;'
        f'padding:3px 10px;border:1px solid #d2d5d9;border-radius:5px;background:#fff;'
        f'cursor:pointer">reset view</button>'
        f'<span>zoom <span class="zoomlbl">1.0x</span></span>'
        f'<span style="color:#9aa0a6">scroll to zoom &middot; drag to pan</span></div>'
    ) if controls else ""

    tail = ""
    if show_notes:
        blocks = []
        if sch.notes:
            items = "".join(f"<li>{_esc(n)}</li>" for n in sch.notes)
            blocks.append(
                f'<div style="margin-top:10px"><div style="font:600 12px ui-sans-serif,'
                f'system-ui,sans-serif;color:#3c4043">Notes</div>'
                f'<ul style="margin:4px 0 0 18px;padding:0;font:12px ui-sans-serif,'
                f'system-ui,sans-serif;color:#3c4043">{items}</ul></div>'
            )
        if sch.inventions:
            items = "".join(f"<li>{_esc(n)}</li>" for n in sch.inventions)
            blocks.append(
                f'<div style="margin-top:10px;padding:8px 10px;background:#fff8e1;'
                f'border-left:3px solid #f0ad4e;border-radius:0 4px 4px 0">'
                f'<div style="font:600 12px ui-sans-serif,system-ui,sans-serif;color:#7a5b12">'
                f'Drawn but not modelled</div>'
                f'<ul style="margin:4px 0 0 18px;padding:0;font:12px ui-sans-serif,'
                f'system-ui,sans-serif;color:#7a5b12">{items}</ul></div>'
            )
        tail = "".join(blocks)

    return (
        f'<div id="{_esc(uid)}" data-panzoom '
        f'style="font-family:ui-sans-serif,system-ui,sans-serif">'
        f'{head}{svg}{bar}{tail}</div>'
    )


def to_interactive_html(
    sch: Schematic,
    *,
    width_px: int = 760,
    uid: str = "sch",
    show_notes: bool = True,
) -> str:
    """
    Render the schematic with live wheel-zoom and drag-pan.

    Self-contained: inline SVG plus a short vanilla script, no external
    dependency.  Suitable for both ``st.components.v1.html`` and the workbook.

    The **inventions** list is rendered under the drawing and is not optional —
    if a family drew something the model does not compute, the reader sees it
    next to the picture.
    """
    block = schematic_block(sch, width_px=width_px, uid=uid, show_notes=show_notes)
    return f"{block}<script>{panzoom_js()}</script>"
