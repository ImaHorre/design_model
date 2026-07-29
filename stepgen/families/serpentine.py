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


def solve_config(
    config,
    *,
    Po_mbar: float,
    Qw_mlhr: float,
    params: dict[str, Any] | None = None,
    label: str = "",
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
