"""
stepgen.families.serpentine
===========================
The serpentine family — the current V5 design style.

This wraps the EXISTING, validated path unchanged:
    * ``stepgen.design.sweep.evaluate_candidate``  (ladder solve + metrics)
    * ``stepgen.design.layout.compute_layout``     (serpentine fold)

The only thing added here is a **fits-in-square** feasibility gate: the study's
``footprint.square_side_mm`` defines a square die, and ``compute_layout`` tells
us whether the folded serpentine fits inside it.

Study geometry block (``serpentine:``)
--------------------------------------
    main:     { depth_um, width_um }              # oil-main depth / width
    rung:     { length_mm, upstream_width_um, N }  # DFU span, width, count
    junction: { exit_width_um, exit_depth_um, pitch_um }
    # OR, instead of an explicit junction:
    target_droplet_um: <D>    # derive junction geometry from a droplet target

The routed main length ``Mcl`` is derived as ``N × pitch`` (N given), so the
count is exact; the rung depth equals the exit depth (single-etch step).
"""

from __future__ import annotations

import math
from typing import Any

from stepgen.families.base import CommonMetrics, Family, register_family
from stepgen.families.intent import (
    Constraints,
    Intent,
    dfu_count_ladder,
    junction_for_droplet,
    plan_junction,
    rungs_for_ca_ceiling,
    rungs_for_throughput,
)

# throughput unit factor: m³/s -> mL/hr  (1 m³ = 1e6 mL, 1 hr = 3600 s)
_M3S_TO_MLHR = 1e6 * 3600.0


def _leaf(block: dict, *path, default=None):
    """Fetch a nested value by path, returning ``default`` if missing."""
    node: Any = block
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _derive_junction_from_droplet(
    droplet_model, D_um: float, aspect_ratio: float = 3.0
) -> tuple[float, float]:
    """
    Derive junction (exit_width, exit_depth) in metres from a target droplet
    diameter.

    Thin wrapper kept for readability at the call site; the closed form lives in
    :func:`stepgen.families.intent.junction_for_droplet`, which
    ``design_search._derive_mcd_from_ar`` also delegates to, so there is one
    implementation of the inverse solve.
    """
    return junction_for_droplet(D_um, aspect_ratio, droplet_model)


@register_family
class SerpentineFamily(Family):
    name = "serpentine"

    def applicable_metrics(self) -> set[str]:
        # Serpentine exposes all shared gates. regime_Ca is only meaningful when
        # an interfacial tension is given; otherwise the value is None -> grey.
        return {"throughput_mlhr", "uniformity_pct", "operating_Po_mbar",
                "regime_Ca", "build", "validity"}

    # -- intent ------------------------------------------------------------
    def grid_from_intent(
        self,
        intent: Intent,
        constraints: Constraints,
        *,
        fluids: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Serpentine geometry for a droplet + throughput target.

        Free variables and how they are bounded:

        * **junction** — fully determined by the droplet target (shared inverse
          solve), so every family in the study gets the same exit.
        * **main** — pinned at the fab caps.  Depth costs no in-plane area, so
          the deepest permitted main is always the right starting point; the
          relaxation pricing in :mod:`stepgen.studio.diagnosis` is what asks
          whether a deeper one would be worth buying.
        * **rung** — length and upstream width swept over the small ladders the
          junction plan implies.
        * **N** — swept across *both* sizing answers: the fewest rungs that
          deliver the throughput at the pressure ceiling, and the fewest that
          keep every exit under the Ca ceiling.  For deep DFUs those differ by
          more than an order of magnitude and pull in opposite directions, so a
          ladder anchored on either alone searches the wrong corner.
        """
        plan = plan_junction(intent, constraints, rung_length_mm=(1.0, 2.0))
        mu = float(fluids.get("mu_dispersed", 0.06))
        n_flow = rungs_for_throughput(
            throughput_mlhr=intent.throughput_mlhr,
            Po_mbar=constraints.max_Po_mbar,
            rung_length_m=plan.mid_rung_length_m,
            upstream_width_m=plan.mid_upstream_m,
            exit_depth_m=plan.exit_depth_um * 1e-6,
            mu_dispersed=mu,
        )
        n_ca = rungs_for_ca_ceiling(
            throughput_mlhr=intent.throughput_mlhr,
            exit_width_m=plan.exit_width_um * 1e-6,
            exit_depth_m=plan.exit_depth_um * 1e-6,
            mu_dispersed=mu,
            gamma=float(fluids.get("gamma", 0.0)),
            max_exit_Ca=constraints.max_exit_Ca,
        )
        # a lane can hold at most (usable side / pitch) rungs before folding, and
        # the fold itself is what the fits_square gate then judges
        n_cap = max(4.0, constraints.usable_side_mm * 1e3 / plan.pitch_um * 20.0)

        return {
            "main": {
                "depth_um": constraints.max_main_depth_um,
                "width_um": constraints.max_main_width_um,
            },
            "rung": {
                "length_mm": plan.rung_length_mm,
                "upstream_width_um": plan.upstream_width_um,
                "N": dfu_count_ladder(n_flow, n_ca, minimum=4, maximum=n_cap),
            },
            "junction": {
                "exit_width_um": plan.exit_width_um,
                "exit_depth_um": plan.exit_depth_um,
                "pitch_um": plan.pitch_um,
            },
        }

    # -- compile -----------------------------------------------------------
    def compile(
        self,
        params: dict[str, Any],
        *,
        fluids: dict[str, Any],
        footprint: dict[str, Any],
        manufacturing: dict[str, Any],
    ):
        from stepgen.config import (
            DeviceConfig, FluidConfig, GeometryConfig, MainChannelConfig,
            RungConfig, JunctionConfig, OperatingConfig, FootprintConfig,
            ManufacturingConfig, DropletModelConfig,
        )

        droplet_model = DropletModelConfig()  # calibrated power-law defaults

        # ── junction: explicit, or derived from a droplet target ────────────
        target = params.get("target_droplet_um")
        if target is not None:
            ar = float(params.get("junction_aspect_ratio", 3.0))
            exit_w, exit_d = _derive_junction_from_droplet(droplet_model, float(target), ar)
            pitch = 2.0 * exit_w
        else:
            exit_w = float(_leaf(params, "junction", "exit_width_um", default=30.0)) * 1e-6
            exit_d = float(_leaf(params, "junction", "exit_depth_um", default=10.0)) * 1e-6
            pitch_um = _leaf(params, "junction", "pitch_um")
            pitch = float(pitch_um) * 1e-6 if pitch_um is not None else 2.0 * exit_w

        # ── main + rung geometry ────────────────────────────────────────────
        Mcd = float(_leaf(params, "main", "depth_um", default=200.0)) * 1e-6
        Mcw = float(_leaf(params, "main", "width_um", default=1000.0)) * 1e-6
        rung_len = float(_leaf(params, "rung", "length_mm", default=4.0)) * 1e-3
        upstream_w = float(_leaf(params, "rung", "upstream_width_um", default=15.0)) * 1e-6
        N = int(_leaf(params, "rung", "N", default=1000))
        constriction = float(_leaf(params, "rung", "constriction_ratio", default=1.0))

        # Rung depth == exit depth (single-etch step). Mcl derived from N × pitch
        # so the count is exact (Nmc_override pins it too).
        Mcl = N * pitch

        # ── fluids ──────────────────────────────────────────────────────────
        fl = FluidConfig(
            mu_continuous=float(fluids.get("mu_continuous", 0.00089)),
            mu_dispersed=float(fluids.get("mu_dispersed", 0.06)),
            emulsion_ratio=float(fluids.get("emulsion_ratio", 0.1)),
            gamma=float(fluids.get("gamma", 0.0)),
            phase_system=str(fluids.get("phase_system", "o/w")),
        )

        # ── footprint from the square-die target ────────────────────────────
        side_mm = float(footprint.get("square_side_mm", 63.5))
        area_cm2 = (side_mm * 0.1) ** 2   # mm -> cm, squared
        fp = FootprintConfig(
            footprint_area_cm2=area_cm2,
            footprint_aspect_ratio=1.0,   # a square die
            lane_spacing=float(footprint.get("lane_spacing_um", 500.0)) * 1e-6,
            turn_radius=float(footprint.get("turn_radius_um", 500.0)) * 1e-6,
            reserve_border=float(footprint.get("reserve_border_mm", 2.0)) * 1e-3,
        )

        mfg = ManufacturingConfig(
            max_main_depth=float(manufacturing.get("max_main_depth_um", 200.0)) * 1e-6,
            max_main_width=float(manufacturing.get("max_main_width_um", 1000.0)) * 1e-6,
            min_feature_width=float(manufacturing.get("min_wall_um", 0.5)) * 1e-6,
        )

        cfg = DeviceConfig(
            fluids=fl,
            geometry=GeometryConfig(
                main=MainChannelConfig(Mcd=Mcd, Mcw=Mcw, Mcl=Mcl),
                rung=RungConfig(
                    mcd=exit_d, mcw=upstream_w, mcl=rung_len,
                    pitch=pitch, constriction_ratio=constriction,
                ),
                junction=JunctionConfig(exit_width=exit_w, exit_depth=exit_d),
                Nmc_override=N,
            ),
            operating=OperatingConfig(Po_in_mbar=100.0, Qw_in_mlhr=5.0),
            footprint=fp,
            manufacturing=mfg,
            droplet_model=droplet_model,
        )
        return cfg

    # -- solve -------------------------------------------------------------
    def solve(
        self,
        compiled,
        operating: dict[str, Any],
        *,
        params: dict[str, Any],
        label: str,
    ) -> CommonMetrics:
        return solve_config(
            compiled,
            Po_mbar=float(operating.get("Po_mbar", compiled.operating.Po_in_mbar)),
            Qw_mlhr=float(operating.get("Qw_mlhr", compiled.operating.Qw_in_mlhr)),
            params=params,
            label=label,
        )

    # -- geometry rendering ------------------------------------------------
    def packing_capacity(self, compiled):
        """
        Largest DFU count this die holds at the current lane geometry.

        Inverts :func:`stepgen.design.layout.compute_layout`.  That function
        goes ``N -> Mcl -> num_lanes -> total_height -> fits?``; here we ask how
        many lanes fit the die height, and convert back to a rung count::

            n_lanes_max = floor((H_useful - pair_w) / lane_pitch) + 1
            N_max       = n_lanes_max * floor(lane_length / pitch)

        Note what this exposes: ``num_lanes`` depends on ``Mcl`` and
        ``lane_length`` only — **not** on ``turn_radius``.  Shrinking the turn
        radius lowers ``total_height`` and so helps an overflowing stack fit,
        but it never adds a lane.  The drawing and this readout agree on that,
        which is the point.
        """
        from stepgen.design.layout import compute_layout
        from stepgen.viz.schematic import PackingCapacity

        fp, geom = compiled.footprint, compiled.geometry
        lay = compute_layout(compiled)

        area_m2 = fp.footprint_area_cm2 * 1e-4
        H = math.sqrt(area_m2 / fp.footprint_aspect_ratio)
        H_useful = H - 2.0 * fp.reserve_border

        pitch = geom.rung.pitch
        n_current = int(geom.Nmc_override or 0) or int(round(geom.main.Mcl / pitch))

        if lay.lane_pitch <= 0 or pitch <= 0 or lay.lane_length <= 0:
            return None

        lanes_max = int(math.floor((H_useful - lay.lane_pair_width) / lay.lane_pitch)) + 1
        lanes_max = max(lanes_max, 0)
        per_lane = int(math.floor(lay.lane_length / pitch))
        n_max = max(lanes_max * per_lane, 0)

        if lanes_max <= 0:
            limited_by = "die height — a single lane pair does not fit"
        elif lay.num_lanes > lanes_max:
            limited_by = "die height (lane stack overflows)"
        else:
            limited_by = "die height (lane stack)"

        return PackingCapacity(
            n_current=n_current,
            n_max=n_max,
            utilisation=(n_current / n_max) if n_max else float("inf"),
            limited_by=limited_by,
            fits=bool(lay.fits_footprint),
            detail={
                "lanes_current": float(lay.num_lanes),
                "lanes_max": float(lanes_max),
                "dfu_per_lane": float(per_lane),
                "lane_length_mm": lay.lane_length * 1e3,
                "lane_pitch_mm": lay.lane_pitch * 1e3,
                "turn_radius_um": fp.turn_radius * 1e6,
            },
        )

    def render_schematic(self, compiled, view: str = "device"):
        """Serpentine device fold, or a zoomed group of adjacent DFUs."""
        if view == "zoom":
            return _serpentine_zoom(compiled)
        return _serpentine_device(compiled, self.packing_capacity(compiled))


def production_threshold_mbar(
    config,
    *,
    Qw_mlhr: float,
    Po_max_mbar: float = 2000.0,
    active_fraction_min: float = 1.0,
    coarse_step_mbar: float = 50.0,
    tol_mbar: float = 5.0,
) -> float | None:
    """
    Lowest drive pressure at which *every* DFU produces — the minimum P for
    production.

    A rung is ACTIVE only once its ΔP clears the oil→water capillary threshold
    (``droplet_model.dP_cap_ow_mbar``); below that it is OFF or REVERSE.  Because
    the ladder is not flat, the far end of the device clears last, so the
    threshold for *full* production is set by the worst-placed DFU rather than by
    the mean ΔP.  That is exactly the number a build needs to be driven above.

    Coarse scan up to the first pressure meeting *active_fraction_min*, then
    bisect down to *tol_mbar*.  Returns ``None`` if the device never reaches the
    required active fraction at or below *Po_max_mbar*.

    Costs ~40 network solves, and the answer is a property of the *design* at a
    given Qw — it does not depend on the operating Po.  Call it once per design,
    not once per swept pressure point; that is why ``solve_config`` leaves it off
    unless asked (``with_production_threshold=True``).
    """
    from stepgen.design.sweep import evaluate_candidate

    def active_at(po: float) -> float:
        try:
            return float(evaluate_candidate(
                config, Po_in_mbar=po, Qw_in_mlhr=Qw_mlhr,
            )["active_fraction"])
        except Exception:
            return 0.0

    po = coarse_step_mbar
    hit: float | None = None
    while po <= Po_max_mbar:
        if active_at(po) >= active_fraction_min:
            hit = po
            break
        po += coarse_step_mbar
    if hit is None:
        return None

    lo = max(hit - coarse_step_mbar, 0.0)
    hi = hit
    while hi - lo > tol_mbar:
        mid = 0.5 * (lo + hi)
        if active_at(mid) >= active_fraction_min:
            hi = mid
        else:
            lo = mid
    return hi


def solve_config(
    config,
    *,
    Po_mbar: float,
    Qw_mlhr: float,
    params: dict[str, Any] | None = None,
    label: str = "",
    with_production_threshold: bool = False,
) -> CommonMetrics:
    """
    Solve a serpentine ``DeviceConfig`` at (Po, Qw) and map the validated
    ``evaluate_candidate`` row onto :class:`CommonMetrics`.

    Exposed as a module function so the anchor test can compare a directly
    loaded config against ``evaluate_candidate`` without going through
    ``compile``.
    """
    from stepgen.design.sweep import evaluate_candidate

    row = evaluate_candidate(config, Po_in_mbar=Po_mbar, Qw_in_mlhr=Qw_mlhr)

    geom = config.geometry
    exit_w = geom.junction.exit_width
    exit_d = geom.junction.exit_depth
    gamma = config.fluids.gamma

    # ── exit capillary number (diagnostic; the size model is regime-blind) ──
    regime_Ca: float | None = None
    q_per_rung = row.get("Q_per_rung_avg", 0.0) or 0.0
    if gamma > 0 and exit_w > 0 and exit_d > 0 and q_per_rung > 0:
        v_exit = q_per_rung / (exit_w * exit_d)
        regime_Ca = config.fluids.mu_dispersed * v_exit / gamma

    notes: list[str] = []
    # Honesty flag: the power-law droplet size is not trusted for deep exits
    # (see the droplet-model-regime-blind note). Flag ~2x extrapolation.
    if exit_d * 1e6 > 12.0:
        notes.append(
            "deep exit: power-law droplet size extrapolated (~2x) — size/frequency not trusted"
        )

    # manufacturable = within fab caps (depth / width / min wall). Kept separate
    # from the fits-square gate (which is layout, not fabrication).
    mfg = config.manufacturing
    manufacturable = bool(
        geom.main.Mcd <= mfg.max_main_depth
        and geom.main.Mcw <= mfg.max_main_width
        and geom.rung.mcw >= mfg.min_feature_width
        and geom.rung.mcd >= mfg.min_feature_width
    )

    q_oil = row.get("Q_oil_total", None)
    throughput = float(q_oil) * _M3S_TO_MLHR if q_oil is not None else None

    # ── cycle timings, all off the one network rung flow ────────────────────
    # t_S1    = V_reset / Q   (V_reset = sqrt(w·h)·w·h)
    # t_cycle = V_drop  / Q   (conservation: one droplet per cycle)
    # Validated against the V5-8-1 Po sweep — t_S1 to -2% at 200/300 mbar,
    # t_cycle to ~6% with no pressure drift.  See stage1_physics.
    dP_rung_mbar = t_stage1 = t_cycle = stage1_fraction = None
    dP_rung_Pa = row.get("dP_avg", 0.0) or 0.0
    q_rung = row.get("Q_per_rung_avg", 0.0) or 0.0
    if dP_rung_Pa > 0:
        dP_rung_mbar = dP_rung_Pa / 100.0
    if q_rung > 0:
        from stepgen.models.stage_wise_v3 import StageWiseV3Config
        from stepgen.models.stage_wise_v3.stage1_physics import solve_stage1_physics

        from stepgen.models.droplets import refill_volume

        v3_cfg = getattr(config, "stage_wise_v3", None) or StageWiseV3Config()
        t_stage1 = solve_stage1_physics(dP_rung_Pa, q_rung, config, v3_cfg).t_displacement
        # Per-cycle volume must match the one behind `frequency_hz`
        # (droplets.droplet_frequency = Q / (V_drop + V_refill)) or t_cycle and
        # 1/frequency_hz would silently disagree whenever a config enables refill.
        V_cycle = math.pi / 6.0 * float(row["D_pred"]) ** 3 + refill_volume(config)
        t_cycle = V_cycle / q_rung
        if t_cycle > 0 and math.isfinite(t_stage1):
            stage1_fraction = t_stage1 / t_cycle

    return CommonMetrics(
        family="serpentine",
        label=label,
        params=dict(params or {}),
        throughput_mlhr=throughput,
        N_dfu=int(row["Nmc"]),
        droplet_um=float(row["D_pred"]) * 1e6,
        frequency_hz=float(row.get("f_pred_mean", 0.0)),
        uniformity_pct=float(row.get("dP_spread_pct", math.nan)),
        operating_Po_mbar=float(row["Po_in_mbar"]),
        dP_rung_mbar=dP_rung_mbar,
        t_stage1_s=t_stage1,
        t_cycle_s=t_cycle,
        stage1_fraction=stage1_fraction,
        Po_min_production_mbar=(
            production_threshold_mbar(config, Qw_mlhr=Qw_mlhr)
            if with_production_threshold else None
        ),
        regime_Ca=regime_Ca,
        exit_width_um=exit_w * 1e6,
        exit_depth_um=exit_d * 1e6,
        lambda_visc=(config.fluids.mu_continuous / config.fluids.mu_dispersed
                     if config.fluids.mu_dispersed else None),
        area_used_cm2=float(row["footprint_area_used"]) * 1e4,
        fits_square=bool(row["fits_footprint"]),
        manufacturable=manufacturable,
        no_crossing=None,  # N-A for serpentine (single folded pair, planar by construction)
        notes=notes,
        raw=row,
    )


# ---------------------------------------------------------------------------
# Schematics (Phase 3)
# ---------------------------------------------------------------------------
# Both functions read the compiled ``DeviceConfig`` — the object the solver
# consumes — so the drawing cannot drift from the packing maths.

def _serpentine_device(config, capacity=None):
    """
    Whole-device view: the folded lane stack inside the die square.

    Lane block heights are the real ones (``Mcw`` for each main, ``mcl`` for the
    rung array between them), the fold is drawn as an annular sector at the true
    ``turn_radius``, and lanes that overflow the die are tinted and dashed.
    """
    from stepgen.viz.schematic import Arc, Dim, Label, Rect, Schematic, Zone

    fp, geom = config.footprint, config.geometry

    area_m2 = fp.footprint_area_cm2 * 1e-4
    chip_W = math.sqrt(area_m2 * fp.footprint_aspect_ratio)
    chip_H = math.sqrt(area_m2 / fp.footprint_aspect_ratio)
    bd = fp.reserve_border
    tr = fp.turn_radius

    Mcw, mcl = geom.main.Mcw, geom.rung.mcl
    mcw, pitch = geom.rung.mcw, geom.rung.pitch

    lane_len = max(chip_W - 2.0 * bd, 0.0)
    pair_w = 2.0 * Mcw + mcl + fp.lane_spacing
    lane_pitch = pair_w + 2.0 * tr
    n_total = int(geom.Nmc_override or 0) or int(round(geom.main.Mcl / pitch))
    n_lanes = max(math.ceil(geom.main.Mcl / lane_len), 1) if lane_len > 0 else 1
    per_lane_cap = int(math.floor(lane_len / pitch)) if pitch > 0 else 0

    prims: list = [Rect(0.0, 0.0, chip_W, chip_H, "die", dashed=True)]
    remaining = n_total

    for i in range(n_lanes):
        y0 = bd + i * lane_pitch
        inside = (y0 + pair_w) <= (chip_H - bd + 1e-12)
        here = min(remaining, per_lane_cap) if per_lane_cap else 0
        remaining -= here

        prims.append(Rect(bd, y0, lane_len, Mcw, "oil_main", dashed=not inside))
        prims.append(Zone(
            bd, y0 + Mcw, lane_len, mcl, "dfu",
            count=here, unit_w=mcw, unit_h=mcl, pitch=pitch, axis="x",
            label=(f"{here:,} DFUs" if here > 240 else None),
        ))
        prims.append(Rect(bd, y0 + Mcw + mcl, lane_len, Mcw, "water_main", dashed=not inside))

        if not inside:
            prims.append(Rect(bd, y0, lane_len, pair_w, "overflow"))

        # the fold — drawn at the true turn radius, alternating ends
        if i < n_lanes - 1:
            cy = y0 + pair_w + tr
            if i % 2 == 0:
                prims.append(Arc(bd + lane_len, cy, tr, tr + pair_w,
                                 -math.pi / 2, math.pi / 2, "turn"))
            else:
                prims.append(Arc(bd, cy, tr, tr + pair_w,
                                 math.pi / 2, 3 * math.pi / 2, "turn"))

    total_h = (n_lanes - 1) * lane_pitch + pair_w
    fits = total_h <= (chip_H - 2.0 * bd)

    # dimension the first lane so the block heights are checkable
    prims.append(Dim(bd - chip_W * 0.012, bd, bd - chip_W * 0.012, bd + Mcw,
                     f"Mcw {Mcw * 1e6:.0f} um"))
    prims.append(Dim(bd - chip_W * 0.045, bd + Mcw, bd - chip_W * 0.045, bd + Mcw + mcl,
                     f"mcl {mcl * 1e3:.2f} mm"))
    if n_lanes > 1:
        prims.append(Dim(bd + lane_len * 0.5, bd + pair_w,
                         bd + lane_len * 0.5, bd + lane_pitch,
                         f"2*r_turn {2 * tr * 1e6:.0f} um"))
    prims.append(Label(bd + lane_len / 2, chip_H - bd * 0.4,
                       f"{n_lanes} lane{'s' if n_lanes != 1 else ''} - "
                       f"{n_total:,} DFUs - pitch {pitch * 1e6:.0f} um"))

    notes = [
        f"{n_lanes} lane pair(s) of {lane_len * 1e3:.1f} mm; stack height "
        f"{total_h * 1e3:.1f} mm against {(chip_H - 2 * bd) * 1e3:.1f} mm usable.",
        f"Turn radius {tr * 1e6:.0f} um against a {pair_w * 1e6:.0f} um lane pair "
        f"(ratio {tr / pair_w:.2f}) - below ~0.5 the fold is tighter than the "
        f"channel bundle it carries.",
    ]
    if not fits:
        notes.append(f"Overflows the die by {(total_h - (chip_H - 2 * bd)) * 1e3:.1f} mm.")
    if per_lane_cap and n_total > per_lane_cap * n_lanes:
        notes.append(
            f"{n_total:,} DFUs exceeds the {per_lane_cap * n_lanes:,} that these "
            f"lanes hold at {pitch * 1e6:.0f} um pitch."
        )

    return Schematic(
        family="serpentine", view="device", prims=prims,
        extent=(0.0, 0.0, chip_W, max(chip_H, total_h + 2 * bd)),
        title="Serpentine - whole device",
        subtitle=f"die {chip_W * 1e3:.1f} x {chip_H * 1e3:.1f} mm",
        notes=notes,
        inventions=[
            "The fold is drawn as an annular sector at the configured turn "
            "radius. The model reserves 2*r_turn of lane pitch for it but does "
            "not model the turn's channel path, its length or its pressure drop.",
            "Rungs are shown filling each lane in order; the model treats the "
            "ladder as one sequence and does not assign rungs to lanes.",
        ],
        fits=fits,
        capacity=capacity,
    )


def _serpentine_zoom(config, n_show: int | None = None):
    """
    Zoomed DFU group: adjacent rungs at true scale, dimensioned.

    Draws what a plan view can honestly show.  Exit *depth* is out of plane, so
    it is annotated rather than drawn — a plan view that rendered depth as a
    length would be inventing geometry.

    ``n_show`` defaults to whatever keeps the drawing roughly square.  Rungs are
    typically 15-30x longer than the pitch is wide, so a fixed count would give
    a 7:1 sliver on a real V5 geometry — the aspect ratio has to follow the
    geometry, not the other way round.
    """
    from stepgen.viz.schematic import Dim, Label, Rect, Schematic

    geom = config.geometry
    Mcw, mcl = geom.main.Mcw, geom.rung.mcl
    mcw, pitch = geom.rung.mcw, geom.rung.pitch
    exit_w = geom.junction.exit_width
    exit_d = geom.junction.exit_depth
    wall = pitch - mcw

    if n_show is None:
        drawn_h = 2.0 * Mcw + 1.65 * mcl
        n_show = int(round(drawn_h / pitch)) - 1 if pitch > 0 else 5
    n = int(min(max(n_show, 4), 40))
    span = n * pitch
    exit_len = mcl * 0.08          # drawing-only; see inventions

    prims: list = [
        Rect(-pitch * 0.5, -Mcw, span + pitch, Mcw, "oil_main", label="oil main"),
    ]
    for i in range(n):
        x = i * pitch
        prims.append(Rect(x, 0.0, mcw, mcl - exit_len, "dfu"))
        prims.append(Rect(x + (mcw - exit_w) / 2.0, mcl - exit_len, exit_w, exit_len, "exit"))
    prims.append(Rect(-pitch * 0.5, mcl, span + pitch, Mcw, "water_main",
                      label="continuous phase / collection"))

    prims += [
        Dim(0.0, -mcl * 0.10, pitch, -mcl * 0.10, f"pitch {pitch * 1e6:.0f} um"),
        Dim(0.0, -mcl * 0.22, mcw, -mcl * 0.22, f"w_up {mcw * 1e6:.1f} um"),
        Dim(mcw, -mcl * 0.34, pitch, -mcl * 0.34, f"wall {wall * 1e6:.1f} um"),
        Dim(-pitch * 0.30, 0.0, -pitch * 0.30, mcl, f"rung {mcl * 1e3:.2f} mm"),
        Dim((n - 1) * pitch + (mcw - exit_w) / 2.0, mcl + mcl * 0.06,
            (n - 1) * pitch + (mcw + exit_w) / 2.0, mcl + mcl * 0.06,
            f"exit w {exit_w * 1e6:.0f} um"),
        Label(span * 0.5, mcl * 1.30,
              f"exit depth {exit_d * 1e6:.0f} um (out of plane) - "
              f"main depth {geom.main.Mcd * 1e6:.0f} um", size=0.9),
    ]

    return Schematic(
        family="serpentine", view="zoom", prims=prims,
        extent=(-pitch * 0.6, -Mcw - mcl * 0.45, span + pitch * 0.6, mcl + Mcw + mcl * 0.2),
        title="Serpentine - DFU group at true scale",
        subtitle=f"{n} adjacent rungs - pitch {pitch * 1e6:.0f} um - "
                 f"exit {exit_w * 1e6:.0f} x {exit_d * 1e6:.0f} um",
        notes=[
            f"Wall between rungs is {wall * 1e6:.1f} um at {mcw * 1e6:.1f} um upstream "
            f"width - the pitch is {pitch / mcw:.1f}x the channel width.",
            f"Exit is {exit_w / mcw:.1f}x the upstream width "
            f"({'widening' if exit_w > mcw else 'narrowing'} into the step).",
        ],
        inventions=[
            "The junction exit is drawn with a nominal length (8% of the rung). "
            "The model treats the exit as a cross-section - width x depth - and "
            "assigns it no length.",
            "Exit and main depths are annotated, not drawn: this is a plan view.",
        ],
    )
