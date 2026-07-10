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
    diameter, mirroring ``design_search._derive_mcd_from_ar`` /
    ``_derive_junction_geometry``.

    With exit_depth = mcd and exit_width = ar·mcd:
        D = k · (ar·mcd)^a · mcd^b = k · ar^a · mcd^(a+b)
        mcd = (D / (k · ar^a))^(1/(a+b))
    """
    k, a, b = droplet_model.k, droplet_model.a, droplet_model.b
    D = D_um * 1e-6
    mcd = (D / (k * aspect_ratio ** a)) ** (1.0 / (a + b))
    exit_depth = mcd
    exit_width = aspect_ratio * mcd
    return exit_width, exit_depth


@register_family
class SerpentineFamily(Family):
    name = "serpentine"

    def applicable_metrics(self) -> set[str]:
        # Serpentine exposes all shared gates. regime_Ca is only meaningful when
        # an interfacial tension is given; otherwise the value is None -> grey.
        return {"throughput_mlhr", "uniformity_pct", "operating_Po_mbar",
                "regime_Ca", "build"}

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
        area_used_cm2=float(row["footprint_area_used"]) * 1e4,
        fits_square=bool(row["fits_footprint"]),
        manufacturable=manufacturable,
        no_crossing=None,  # N-A for serpentine (single folded pair, planar by construction)
        notes=notes,
        raw=row,
    )
