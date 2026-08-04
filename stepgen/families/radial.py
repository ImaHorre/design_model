"""
stepgen.families.radial
========================
The radial ("wheel") family — a topology where oil enters at a central hub and
flows outward through N radial DFU channels to a rim, exiting as droplets into
an open continuous-phase bath at atmospheric pressure.

Physics origin
--------------
This wraps the analytic prototype ``designs/radial/radial_hydraulics.py``
(``RadialArray``, Ca-stability, P–Q) and the design notes
``designs/radial/design_notes.md``.  The pure Poiseuille primitives are ported
here (they are ~10-line closed forms) so the installable ``stepgen`` package
does not depend on the loose ``designs/`` script directory.  The two open
corrections from ``design_notes.md §11`` are applied here (the prototype module
is left uncorrected for its standalone plots):

  * **§11.2 effective length** — channels only exist for ``r > r_hub``, so the
    channel length is ``L_eff = R − r_hub`` with
    ``r_hub = R·(w_up + t_min)/pitch``.  Both ``N_DFU ∝ R`` and ``L_eff ∝ R`` so
    total flow stays radius-independent, but the magnitude rises by the factor
    ``pitch / (pitch − w_up − t_min)``.
  * **§11.3 hub pressure budget** — for a central point inlet the oil must spread
    outward through the hub disc (Hele–Shaw radial flow) to reach the channel
    entries.  This ΔP sits **in series** with the parallel channel array:
    ``ΔP_hub = (6µ·Q_total / (π·h³))·ln(r_hub / r_inlet)`` and
    ``ΔP_channels = P_supply − ΔP_hub``.  It does not break uniformity (radial
    symmetry) — it is a pressure-budget gate.

Comparability
-------------
Uniformity is **automatic** for a radial array (all channels share the hub
pressure and the P_atm exit), so ``uniformity_pct`` is left ``None`` → rendered
grey / N-A.  The radial-specific gates are the **exit Ca regime** and the
**hub pressure budget** (``hub_budget_pct`` = ΔP_hub as a % of supply).

Study geometry block (``radial:``)
----------------------------------
    radius_mm:          <R>                       # hub-to-rim radius
    upstream_width_um:  <w_up>                    # radial channel width (free var)
    exit: { width_um, depth_um, pitch_um }        # exit junction (default 30×10, pitch 60)
    inlet_radius_mm:    <r_inlet>   (default 1.0)  # central-inlet radius (hub-budget driver)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from stepgen.families.base import (
    RADIAL_ACTIVE_FRACTION, CommonMetrics, Family, active_fraction_note,
    register_family,
)
from stepgen.families.intent import (
    Constraints,
    Intent,
    ladder,
    plan_junction,
    rungs_for_ca_ceiling,
)

# throughput unit factor: m³/s -> mL/hr  (1 m³ = 1e6 mL, 1 hr = 3600 s)
_M3S_TO_MLHR = 1e6 * 3600.0
_MBAR_TO_PA = 100.0
_ASPECT_LIMIT = 1.0 / 0.63   # h/w must stay below this for the correction term


def _leaf(block: dict, *path, default=None):
    node: Any = block
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _corr(h: float, w: float) -> float:
    """Rectangular-channel shape correction ``1 − 0.63·h/w`` (see resistance model)."""
    ratio = h / w
    if ratio >= _ASPECT_LIMIT:
        raise ValueError(
            f"exit_depth/upstream_width = {ratio:.3f} exceeds the correction limit "
            f"({_ASPECT_LIMIT:.3f}); widen the upstream channel."
        )
    return 1.0 - 0.63 * ratio


@dataclass
class RadialCompiled:
    """Family-native config for a radial wheel design point."""
    radius_m: float
    upstream_width_m: float
    exit_width_m: float
    exit_depth_m: float
    pitch_m: float
    inlet_radius_m: float
    t_min_m: float                # minimum wall thickness (sets r_hub)
    square_side_m: float
    mu_oil: float
    gamma: float
    min_feature_m: float
    mu_water: float = 0.00089     # continuous phase; envelope reporting only
    #: routable fraction of the die -- measured, see families.base
    active_area_fraction: float = RADIAL_ACTIVE_FRACTION

    @property
    def max_radius_m(self) -> float:
        """
        Largest wheel the die holds: the disc whose area is the routable
        fraction of the die, ``R_max = side x sqrt(f/pi)``.

        At f = 0.64 on a 100 mm die this is 45.1 mm, which is the V6-30 disc to
        0.3%.  It replaces ``side/2`` -- a wheel touching the die edge on all
        four sides has nowhere to put its inlet.
        """
        return self.square_side_m * math.sqrt(
            max(self.active_area_fraction, 0.0) / math.pi)


@register_family
class RadialFamily(Family):
    name = "radial"

    def applicable_metrics(self) -> set[str]:
        # Uniformity is automatic (grey / N-A). Radial-specific gates are the exit
        # Ca regime and the hub pressure budget.
        return {"throughput_mlhr", "operating_Po_mbar", "regime_Ca",
                "hub_budget_pct", "build", "validity"}

    # -- intent ------------------------------------------------------------
    def grid_from_intent(
        self,
        intent: Intent,
        constraints: Constraints,
        *,
        fluids: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Radial geometry for a droplet + throughput target.

        The radius is **not** a throughput lever, and intent must not pretend
        otherwise.  Per §11.2, ``N_DFU = 2πR/pitch`` and ``L_eff ∝ R`` both scale
        with the radius, so they cancel::

            Q_total = N·ΔP/R_ch ∝ (R/pitch) · (1/R) = 1/pitch

        A bigger wheel is more DFUs each carrying proportionally less oil.  The
        levers that *do* move throughput are the upstream width, the exit depth
        (fixed here by the droplet target) and the drive pressure — so those are
        what get swept.  The radius sweep exists to trade **area and hub budget**
        against each other, which is a real trade the decide layer can rank.
        """
        plan = plan_junction(intent, constraints)
        r_max_mm = max(2.0, constraints.usable_side_mm / 2.0)

        # The Ca ceiling *does* set a radius floor, even though throughput does
        # not: exit velocity is capped, so each DFU carries at most
        # q_max = v_max·w·h and the array needs at least N_ca of them, which at
        # a fixed pitch means at least R = N_ca·pitch/2π.
        n_ca = rungs_for_ca_ceiling(
            throughput_mlhr=intent.throughput_mlhr,
            exit_width_m=plan.exit_width_um * 1e-6,
            exit_depth_m=plan.exit_depth_um * 1e-6,
            mu_dispersed=float(fluids.get("mu_dispersed", 0.06)),
            gamma=float(fluids.get("gamma", 0.0)),
            max_exit_Ca=constraints.max_exit_Ca,
        )
        r_ca_mm = n_ca * plan.pitch_um * 1e-3 / (2.0 * math.pi)

        radii = ladder(r_max_mm, factors=(0.25, 0.5, 1.0),
                       minimum=max(2.0, min(r_ca_mm, r_max_mm)),
                       maximum=r_max_mm, integer=False)
        return {
            "radius_mm": radii,
            "upstream_width_um": plan.upstream_width_um,
            "exit": {
                "width_um": plan.exit_width_um,
                "depth_um": plan.exit_depth_um,
                "pitch_um": plan.pitch_um,
            },
            # a central point inlet; where r_hub falls below this the family
            # already treats the hub drop as zero (ring / wide port)
            "inlet_radius_mm": 1.0,
        }

    # -- compile -----------------------------------------------------------
    def compile(
        self,
        params: dict[str, Any],
        *,
        fluids: dict[str, Any],
        footprint: dict[str, Any],
        manufacturing: dict[str, Any],
    ) -> RadialCompiled:
        radius = float(params.get("radius_mm", 63.5)) * 1e-3
        w_up = float(params.get("upstream_width_um", 20.0)) * 1e-6
        exit_w = float(_leaf(params, "exit", "width_um", default=30.0)) * 1e-6
        exit_d = float(_leaf(params, "exit", "depth_um", default=10.0)) * 1e-6
        pitch = float(_leaf(params, "exit", "pitch_um", default=60.0)) * 1e-6
        r_inlet = float(params.get("inlet_radius_mm", 1.0)) * 1e-3

        t_min = float(manufacturing.get("min_wall_um", 5.0)) * 1e-6
        side = float(footprint.get("square_side_mm", 63.5)) * 1e-3
        # 64% measured on V6-30: a R = 45 mm disc on a 100 mm die.  Radial feeds
        # from the centre and needs only ~5 mm of margin, which is why it beats
        # the serpentine's 51% (reference_devices/README.md).
        active_frac = float(
            footprint.get("active_area_fraction", RADIAL_ACTIVE_FRACTION))

        return RadialCompiled(
            radius_m=radius,
            upstream_width_m=w_up,
            exit_width_m=exit_w,
            exit_depth_m=exit_d,
            pitch_m=pitch,
            inlet_radius_m=r_inlet,
            t_min_m=t_min,
            square_side_m=side,
            active_area_fraction=active_frac,
            mu_oil=float(fluids.get("mu_dispersed", 0.06)),
            gamma=float(fluids.get("gamma", 0.0)),
            min_feature_m=float(manufacturing.get("min_wall_um", 0.5)) * 1e-6,
            mu_water=float(fluids.get("mu_continuous", 0.00089)),
        )

    # -- solve -------------------------------------------------------------
    def solve(
        self,
        compiled: RadialCompiled,
        operating: dict[str, Any],
        *,
        params: dict[str, Any],
        label: str,
    ) -> CommonMetrics:
        return solve_radial(
            compiled,
            Po_mbar=float(operating.get("Po_mbar", 200.0)),
            params=params,
            label=label,
        )

    # -- geometry rendering ------------------------------------------------
    def packing_capacity(self, compiled: RadialCompiled):
        """
        DFU capacity of the radial array.

        Two different limits, and which one binds is worth seeing.  At the
        configured radius the array holds ``N = 2πR/pitch`` spokes — that is not
        a choice, it is the circumference.  The *die* limit is the largest wheel
        the square can ROUTE, ``R_max = side·√(f/π)`` for the measured routable
        fraction f, giving ``N_max = 2πR_max/pitch``.  Not ``side/2``: a wheel
        touching the die edge on all four sides has nowhere to put its inlet.

        So unlike the serpentine, ``n_current`` here is already the maximum for
        its radius: growing the die only helps by permitting a bigger wheel.
        """
        from stepgen.viz.schematic import PackingCapacity

        if compiled.pitch_m <= 0:
            return None
        r_max = compiled.max_radius_m
        n_here = int(2.0 * math.pi * compiled.radius_m / compiled.pitch_m)
        n_max = int(2.0 * math.pi * r_max / compiled.pitch_m)
        fits = compiled.radius_m <= compiled.max_radius_m

        return PackingCapacity(
            n_current=n_here,
            n_max=n_max,
            utilisation=(n_here / n_max) if n_max else float("inf"),
            limited_by="circumference at this radius (die caps the radius)",
            fits=fits,
            detail={
                "radius_mm": compiled.radius_m * 1e3,
                "max_radius_mm": r_max * 1e3,
                "pitch_um": compiled.pitch_m * 1e6,
                "circumference_mm": 2.0 * math.pi * compiled.radius_m * 1e3,
            },
        )

    def render_schematic(self, compiled: RadialCompiled, view: str = "device"):
        """Radial wheel in the die square, or a zoomed arc of adjacent spokes."""
        if view == "zoom":
            return _radial_zoom(compiled)
        return _radial_device(compiled, self.packing_capacity(compiled))


def solve_radial(
    c: RadialCompiled,
    *,
    Po_mbar: float,
    params: dict[str, Any] | None = None,
    label: str = "",
) -> CommonMetrics:
    """
    Solve one radial wheel at a supply pressure ``Po_mbar`` -> CommonMetrics,
    applying the §11.2 (L_eff) and §11.3 (series hub ΔP) corrections.

    Exposed as a module function so tests can drive it directly (mirrors
    ``serpentine.solve_config``).
    """
    R = c.radius_m
    w = c.upstream_width_m
    h = c.exit_depth_m
    pitch = c.pitch_m
    mu = c.mu_oil
    gamma = c.gamma

    corr = _corr(h, w)

    # ── §11.1/§11.2 hub radius + effective channel length ───────────────────
    # Channels can only carry walls beyond r_hub; below it the hub is a forced
    # open plenum. If the channel + minimum wall already exceed the pitch, the
    # channels overlap everywhere and the geometry is infeasible.
    if (w + c.t_min_m) >= pitch:
        raise ValueError(
            f"upstream_width + min_wall ({(w + c.t_min_m)*1e6:.1f} µm) >= pitch "
            f"({pitch*1e6:.1f} µm): channels overlap, no radial array is realizable."
        )
    r_hub = R * (w + c.t_min_m) / pitch
    L_eff = R - r_hub
    n_dfu = int(2.0 * math.pi * R / pitch)

    # ── channel conductance (parallel array) ───────────────────────────────
    r_dfu = 12.0 * mu * L_eff / (w * h ** 3 * corr)   # Pa·s/m³ per channel
    C_total = n_dfu / r_dfu                            # m³/s per Pa (whole array)

    # ── §11.3 series hub resistance (Hele–Shaw radial spreading) ────────────
    P_supply = Po_mbar * _MBAR_TO_PA
    if r_hub > c.inlet_radius_m:
        A_hub = (6.0 * mu / (math.pi * h ** 3)) * math.log(r_hub / c.inlet_radius_m)
    else:
        A_hub = 0.0   # ring / wide inlet at ≥ r_hub: no radial hub flow

    # series solve: P_supply = ΔP_ch + ΔP_hub, ΔP_hub = A·C·ΔP_ch
    dP_channels = P_supply / (1.0 + A_hub * C_total)
    q_total = C_total * dP_channels          # m³/s
    q_per_dfu = q_total / n_dfu if n_dfu else 0.0
    dP_hub = P_supply - dP_channels
    hub_budget_pct = 100.0 * dP_hub / P_supply if P_supply > 0 else None

    throughput_mlhr = q_total * _M3S_TO_MLHR

    # ── exit capillary number (uses the ACTUAL channel drop + L_eff) ────────
    regime_Ca: float | None = None
    if gamma > 0 and c.exit_width_m > 0 and h > 0 and q_per_dfu > 0:
        v_exit = q_per_dfu / (c.exit_width_m * h)
        regime_Ca = mu * v_exit / gamma

    # ── droplet size / frequency (same power-law as serpentine; regime-blind) ─
    from stepgen.config import DropletModelConfig
    dm = DropletModelConfig()
    D_m = dm.k * (c.exit_width_m ** dm.a) * (h ** dm.b)
    v_drop = (math.pi / 6.0) * D_m ** 3
    freq = q_per_dfu / v_drop if v_drop > 0 else 0.0

    # ── layout + fabrication gates ──────────────────────────────────────────
    diameter = 2.0 * R
    fits_square = bool(R <= c.max_radius_m)
    # die area consumed, not disc area: the wheel's own overhead is grossed up
    # by the routable fraction so "area used" means the same thing here as it
    # does for the serpentine, whose overhead is a third larger.
    area_used_cm2 = math.pi * R ** 2 * 1e4 / max(c.active_area_fraction, 1e-12)
    manufacturable = bool(
        w >= c.min_feature_m
        and c.exit_width_m >= c.min_feature_m
        and h >= c.min_feature_m
        and c.t_min_m >= c.min_feature_m
    )

    notes: list[str] = []
    area_caveat = active_fraction_note(
        c.square_side_m * 1e3, "radial", c.active_area_fraction)
    if area_caveat:
        notes.append(area_caveat)
    if h * 1e6 > 12.0:
        notes.append(
            "deep exit: power-law droplet size extrapolated (~2x) — size/frequency not trusted"
        )
    if A_hub == 0.0:
        notes.append("hub ΔP = 0: inlet assumed at/around r_hub (ring or wide port)")
    else:
        notes.append(
            f"hub delivery from r_inlet={c.inlet_radius_m*1e3:.2g} mm; "
            f"ΔP_hub={dP_hub/_MBAR_TO_PA:.0f} mbar of {Po_mbar:.0f} supply"
        )

    return CommonMetrics(
        family="radial",
        label=label,
        params=dict(params or {}),
        throughput_mlhr=throughput_mlhr,
        N_dfu=n_dfu,
        droplet_um=D_m * 1e6,
        frequency_hz=freq,
        uniformity_pct=None,          # automatic flatness -> N-A (grey)
        operating_Po_mbar=Po_mbar,
        regime_Ca=regime_Ca,
        exit_width_um=c.exit_width_m * 1e6,
        exit_depth_um=h * 1e6,
        lambda_visc=(c.mu_water / c.mu_oil) if c.mu_oil else None,
        # the γ `regime_Ca` above was computed at.  Ca ∝ 1/γ exactly, so a Ca
        # verdict travelling without its γ is a number nobody can re-check.
        gamma_Nm=(c.gamma if c.gamma > 0 else None),
        hub_budget_pct=hub_budget_pct,
        area_used_cm2=area_used_cm2,
        fits_square=fits_square,
        manufacturable=manufacturable,
        no_crossing=None,             # open bath: no phase crossing by construction
        notes=notes,
        raw={
            "radius_mm": R * 1e3,
            "upstream_width_um": w * 1e6,
            "n_dfu": n_dfu,
            "r_hub_mm": r_hub * 1e3,
            "L_eff_mm": L_eff * 1e3,
            "L_eff_factor": pitch / (pitch - w - c.t_min_m),
            "r_dfu_Pa_s_m3": r_dfu,
            "dP_channels_mbar": dP_channels / _MBAR_TO_PA,
            "dP_hub_mbar": dP_hub / _MBAR_TO_PA,
            "Q_total_uL_hr": q_total * 1e9 * 3600.0,
            "Q_per_dfu_nL_hr": q_per_dfu * 1e12 * 3600.0,
        },
    )


# ---------------------------------------------------------------------------
# Schematics (Phase 3)
# ---------------------------------------------------------------------------

def _hub_radius(c: RadialCompiled) -> float:
    """
    ``r_hub = R·(w_up + t_min)/pitch`` — §11.2.

    The same expression :func:`solve_radial` uses.  Drawing it from anywhere
    else would let the picture and the hydraulics disagree about where the
    channels begin, which is exactly what the schematic exists to prevent.
    """
    return c.radius_m * (c.upstream_width_m + c.t_min_m) / c.pitch_m


def _radial_device(c: RadialCompiled, capacity=None):
    """Whole-device view: the wheel inside the die square."""
    from stepgen.viz.schematic import AnnularZone, Circle, Dim, Label, Rect, Schematic

    side = c.square_side_m
    cx = cy = side / 2.0
    R = c.radius_m
    r_hub = _hub_radius(c)
    n_dfu = int(2.0 * math.pi * R / c.pitch_m) if c.pitch_m > 0 else 0
    fits = (2.0 * R) <= side

    prims: list = [Rect(0.0, 0.0, side, side, "die", dashed=True)]

    # the spoke array — true-scale annulus, individual spokes while resolvable
    prims.append(AnnularZone(
        cx, cy, r_hub, R, 0.0, 2.0 * math.pi, "dfu",
        count=n_dfu, unit_w=c.upstream_width_m,
        label=(f"{n_dfu:,} spokes" if n_dfu > 240 else None),
    ))
    # the forced-manifold core: below r_hub there is no room for walls
    prims.append(Circle(cx, cy, r_hub, "hub"))
    prims.append(Circle(cx, cy, c.inlet_radius_m, "oil_main", label="inlet"))

    prims += [
        Dim(cx, cy, cx + R, cy, f"R {R * 1e3:.2f} mm"),
        Dim(cx, cy - r_hub, cx, cy, f"r_hub {r_hub * 1e3:.2f} mm"),
        Label(cx, cy + R + side * 0.03,
              f"{n_dfu:,} DFUs at {c.pitch_m * 1e6:.0f} um pitch"),
    ]

    notes = [
        f"N = 2piR/pitch = {n_dfu:,}; the count is the circumference, not a "
        f"free choice.",
        f"Channels exist only beyond r_hub = {r_hub * 1e3:.2f} mm "
        f"({r_hub / R * 100:.0f}% of R) — inside it the wall thickness cannot "
        f"fit between neighbours, so the core is a forced open manifold.",
        f"Effective channel length L_eff = R - r_hub = {(R - r_hub) * 1e3:.2f} mm.",
    ]
    if not fits:
        notes.append(
            f"Wheel diameter {2 * R * 1e3:.1f} mm exceeds the {side * 1e3:.1f} mm die."
        )

    span = max(2.0 * R, side)
    m = (side - span) / 2.0
    return Schematic(
        family="radial", view="device", prims=prims,
        extent=(min(0.0, m), min(0.0, m), max(side, cx + R), max(side, cy + R)),
        title="Radial - whole device",
        subtitle=f"R {R * 1e3:.2f} mm in a {side * 1e3:.1f} mm die",
        notes=notes,
        inventions=[
            "Spokes are drawn straight and radial at uniform angular pitch. The "
            "model assumes exactly this, so the drawing adds nothing — but it "
            "also means no inlet routing to the hub is shown, because none is "
            "modelled.",
            "The collection reservoir outside the rim is not drawn; the model "
            "treats the exit as discharging to a fixed outlet pressure.",
        ],
        fits=fits,
        capacity=capacity,
    )


def _radial_zoom(c: RadialCompiled, n_show: int = 7):
    """Zoomed rim arc: a few adjacent spokes and their exits, at true scale."""
    from stepgen.viz.schematic import AnnularZone, Dim, Label, Schematic

    R = c.radius_m
    pitch, w = c.pitch_m, c.upstream_width_m
    wall = pitch - w
    show_len = min(max(pitch * 6.0, 0.3e-3), max(R - _hub_radius(c), 1e-4))

    # Local frame: rim at y = 0, centre far below at (0, -R).
    half = (n_show * pitch / R) / 2.0
    prims: list = [AnnularZone(
        0.0, -R, R - show_len, R,
        math.pi / 2 - half, math.pi / 2 + half,
        "dfu", count=n_show, unit_w=w,
    )]

    x_span = n_show * pitch / 2.0
    prims += [
        Dim(-x_span, -show_len * 1.18, -x_span + pitch, -show_len * 1.18,
            f"pitch {pitch * 1e6:.0f} um"),
        Dim(-x_span, -show_len * 1.35, -x_span + w, -show_len * 1.35,
            f"w_up {w * 1e6:.1f} um"),
        Dim(-x_span + w, -show_len * 1.52, -x_span + pitch, -show_len * 1.52,
            f"wall {wall * 1e6:.1f} um"),
        Dim(x_span * 1.12, -show_len, x_span * 1.12, 0.0,
            f"{show_len * 1e3:.2f} mm of {(R - _hub_radius(c)) * 1e3:.2f} mm"),
        Label(0.0, show_len * 0.22,
              f"exit {c.exit_width_m * 1e6:.0f} x {c.exit_depth_m * 1e6:.0f} um "
              f"(depth out of plane) - rim at R = {R * 1e3:.2f} mm", size=0.9),
    ]

    return Schematic(
        family="radial", view="zoom", prims=prims,
        extent=(-x_span * 1.35, -show_len * 1.7, x_span * 1.35, show_len * 0.35),
        title="Radial - rim spokes at true scale",
        subtitle=f"{n_show} adjacent spokes - pitch {pitch * 1e6:.0f} um",
        notes=[
            f"Wall between spokes at the rim is {wall * 1e6:.1f} um "
            f"(min feature {c.t_min_m * 1e6:.1f} um).",
            f"Spokes converge inward: the wall vanishes at r_hub, which is what "
            f"sets it at {_hub_radius(c) * 1e3:.2f} mm.",
        ],
        inventions=[
            "Only the outer {:.0%} of each spoke is shown; the array continues "
            "inward to r_hub.".format(show_len / max(R - _hub_radius(c), 1e-12)),
            "Exit depth is annotated, not drawn: this is a plan view.",
        ],
    )
