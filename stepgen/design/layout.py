"""
stepgen.design.layout
=====================
Schematic layout preview for serpentine chip packing.

Computes how many serpentine lanes are needed to route the two main channels
within the chip footprint, and whether the device fits.

No microchannel-level geometry is rendered — this is a block-level estimate
intended for footprint feasibility checks and comparative design sweeps.

Serpentine geometry model
--------------------------
The oil and water main channels run side by side in each straight lane.
The pair is folded back and forth (serpentine / meander) to fit in a compact
footprint.

Chip dimensions (from FootprintConfig, area_m2 = footprint_area_cm2 × 1e-4):

    W = sqrt(area_m2 × AR)       longest chip dimension [m]
    H = sqrt(area_m2 / AR)       shortest chip dimension [m]

Usable routing extent (after subtracting border on both sides):

    L_useful = W − 2 × reserve_border
    H_useful = H − 2 × reserve_border

Lane geometry:

    lane_length     = L_useful
    lane_pair_width = 2 × Mcw + lane_spacing   (both channels side by side)
    lane_pitch      = lane_pair_width + 2 × turn_radius  (centre-to-centre)

Serpentine result:

    num_lanes    = ceil(Mcl / lane_length)
    total_height = (num_lanes − 1) × lane_pitch + lane_pair_width

    fits_footprint    = total_height ≤ H_useful  (and lane_length > 0)
    footprint_area_used = (total_height + 2×border) × (lane_length + 2×border)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


@dataclass(frozen=True)
class LayoutResult:
    """
    Schematic serpentine layout result.

    Attributes
    ----------
    fits_footprint      : True if the device fits within the chip area.
    num_lanes           : Number of straight serpentine segments.
    lane_length         : Length of each straight segment [m].
    lane_pair_width     : Combined width of both main channels per lane [m].
    lane_pitch          : Centre-to-centre perpendicular spacing of lanes [m].
    total_height        : Total perpendicular extent of all lanes [m].
    footprint_area_used : Bounding-box area of the occupied chip region [m²].
    """
    fits_footprint: bool
    num_lanes: int
    lane_length: float          # m
    lane_pair_width: float      # m
    lane_pitch: float           # m
    total_height: float         # m
    footprint_area_used: float  # m²


def compute_layout(config: "DeviceConfig") -> LayoutResult:
    """
    Compute the serpentine layout for both main channels.

    Parameters
    ----------
    config : DeviceConfig

    Returns
    -------
    LayoutResult
    """
    fp   = config.footprint
    geom = config.geometry

    # ── Chip dimensions ────────────────────────────────────────────────────
    area_m2 = fp.footprint_area_cm2 * 1e-4
    AR      = fp.footprint_aspect_ratio
    W       = math.sqrt(area_m2 * AR)
    H       = math.sqrt(area_m2 / AR)

    # ── Usable routing extents ─────────────────────────────────────────────
    L_useful = W - 2.0 * fp.reserve_border
    H_useful = H - 2.0 * fp.reserve_border

    # ── Lane geometry ──────────────────────────────────────────────────────
    lane_pair_width = 2.0 * geom.main.Mcw + fp.lane_spacing
    lane_pitch      = lane_pair_width + 2.0 * fp.turn_radius

    if L_useful <= 0.0:
        # Reserve borders consume all usable width — cannot route.
        return LayoutResult(
            fits_footprint=False,
            num_lanes=0,
            lane_length=0.0,
            lane_pair_width=lane_pair_width,
            lane_pitch=lane_pitch,
            total_height=0.0,
            footprint_area_used=(2.0 * fp.reserve_border) ** 2,
        )

    lane_length = L_useful
    num_lanes   = math.ceil(geom.main.Mcl / lane_length)

    # ── Total perpendicular extent ─────────────────────────────────────────
    # N lanes need N−1 inter-lane gaps (each gap = lane_pitch − lane_pair_width
    # = 2×turn_radius), plus the pair width of the last lane.
    total_height = (num_lanes - 1) * lane_pitch + lane_pair_width

    fits_footprint = (total_height <= H_useful)

    # ── Bounding-box area (includes border) ────────────────────────────────
    footprint_area_used = (
        (total_height + 2.0 * fp.reserve_border) *
        (lane_length  + 2.0 * fp.reserve_border)
    )

    return LayoutResult(
        fits_footprint=fits_footprint,
        num_lanes=num_lanes,
        lane_length=lane_length,
        lane_pair_width=lane_pair_width,
        lane_pitch=lane_pitch,
        total_height=total_height,
        footprint_area_used=footprint_area_used,
    )
