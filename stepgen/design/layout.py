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

Usable routing extent (see :func:`active_extent`):

    L_useful = W × √active_area_fraction
    H_useful = H × √active_area_fraction

Lane geometry (see :func:`lane_stackup` — the single implementation):

    lane_length     = L_useful
    lane_pair_width = 2 × Mcw + mcl
                        oil main (Mcw) | rung array (mcl) | water main (Mcw).
                        The rung length ``mcl`` IS the physical gap between the
                        oil and water mains — this is what the schematic draws.
    lane_pitch      = lane_pair_width + wall_width  (centre-to-centre)

Serpentine result:

    num_lanes    = ceil(Mcl / lane_length)
    total_height = (num_lanes − 1) × lane_pitch + lane_pair_width

    fits_footprint    = total_height ≤ H_useful  (and lane_length > 0)
    footprint_area_used = total_height × lane_length / active_area_fraction
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


def active_extent(fp) -> tuple[float, float]:
    """
    The routable box inside the die: ``(L_useful, H_useful)`` [m].

    **The one implementation.**  A real device does not get its whole die: the
    serpentine spends a dedicated 65.8 × 8 mm IO strip plus 13–15 mm margins,
    and the radial needs ~5 mm of margin around the wheel.  Measured on the
    built devices (``reference_devices/README.md``), what is left is

        serpentine  51%   V5-30 (69.0 × 74.0 mm) and V5-10 (68.6 × 74.0 mm)
        radial      64%   V6-30 (disc R = 45 mm)

    of a 100 × 100 mm die.  The box is that area laid out with the die's own
    aspect ratio, i.e. each side scaled by ``√active_area_fraction``.

    This **replaces** ``reserve_border``, which is why that field is now unused.
    A 2 mm border on a 100 mm die claims 96 × 96 mm is routable; it is not, and
    that single assumption was the entire source of the old 1.66× capacity
    over-prediction — the packing geometry itself was never wrong.  At 100 mm
    the fraction implies a ~14.3 mm serpentine margin, against the 13–15 mm
    measured.

    **Caveat (open question 5).**  0.51 and 0.64 were measured at a 100 mm die
    and an area *fraction* does not scale: the IO strip and the margins are
    absolute lengths.  Rows on a different die carry a note saying so.  The real
    fix is the deferred per-family IO/port model.
    """
    area_m2 = fp.footprint_area_cm2 * 1e-4
    AR = fp.footprint_aspect_ratio
    side_scale = math.sqrt(max(fp.active_area_fraction, 0.0))
    return (
        math.sqrt(area_m2 * AR) * side_scale,
        math.sqrt(area_m2 / AR) * side_scale,
    )


def lane_stackup(
    *,
    main_width_m: float,
    dfu_array_m: float,
    wall_width_m: float,
) -> tuple[float, float]:
    """
    The serpentine cross-lane stack-up: ``(lane_pair_width, lane_pitch)`` [m].

    **The one implementation.**  Measured on both built serpentines
    (``reference_devices/README.md``, which is ground truth here)::

        lane_pitch = 2 × main_width + DFU_array + wall
        V5-30:  1.0 + 4.0 + 1.0 + 1.0 = 7.00 mm
        V5-10:  1.0 + 2.8 + 1.0 + 1.0 = 5.80 mm

    Two terms this drops, both of which the GDS says are not there:

    * ``lane_spacing`` (500 µm) — spurious. Nothing on either device is 500 µm.
    * ``2 × turn_radius`` as the inter-lane gap. The measured wall is 1.0 mm and
      ``turn_radius`` also defaulted to 500 µm, so ``2 × 500 µm`` reproduced the
      wall by **coincidence** — it breaks the moment ``turn_radius`` moves. Per
      decision 9 the turn radius is reported, not a driver of the stack-up.

    Callers must not re-derive this. Four sites carried their own copy of the
    formula and three of them disagreed; the readout and the drawing have to
    agree or the picture stops meaning anything.
    """
    lane_pair_width = 2.0 * main_width_m + dfu_array_m
    return lane_pair_width, lane_pair_width + wall_width_m


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
    footprint_area_used : Die area this design consumes [m²] — the lane
                          bounding box grossed up by ``active_area_fraction``,
                          so it counts the IO and margin overhead the family
                          cannot route in.  A design that fills the routable
                          box consumes the whole die.
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

    # ── Usable routing extents ─────────────────────────────────────────────
    L_useful, H_useful = active_extent(fp)

    # ── Lane geometry ──────────────────────────────────────────────────────
    lane_pair_width, lane_pitch = lane_stackup(
        main_width_m=geom.main.Mcw,
        dfu_array_m=geom.rung.mcl,
        wall_width_m=fp.wall_width,
    )

    if L_useful <= 0.0:
        # No routable area at all — cannot route.
        return LayoutResult(
            fits_footprint=False,
            num_lanes=0,
            lane_length=0.0,
            lane_pair_width=lane_pair_width,
            lane_pitch=lane_pitch,
            total_height=0.0,
            footprint_area_used=0.0,
        )

    lane_length = L_useful
    num_lanes   = math.ceil(geom.main.Mcl / lane_length)

    # ── Total perpendicular extent ─────────────────────────────────────────
    # N lanes need N−1 inter-lane gaps (each gap = lane_pitch − lane_pair_width
    # = the wall), plus the pair width of the last lane.
    total_height = (num_lanes - 1) * lane_pitch + lane_pair_width

    fits_footprint = (total_height <= H_useful)

    # ── Die area consumed ──────────────────────────────────────────────────
    # The lane bounding box is active area; grossing it up by the family's
    # active fraction turns it into die area, which is what makes "area used"
    # comparable across families with genuinely different IO overhead (51% vs
    # 64%).  Compare raw active areas and the measured fractions would buy
    # nothing here — they would only ever move fits/capacity.
    frac = max(fp.active_area_fraction, 1e-12)
    footprint_area_used = (total_height * lane_length) / frac

    return LayoutResult(
        fits_footprint=fits_footprint,
        num_lanes=num_lanes,
        lane_length=lane_length,
        lane_pair_width=lane_pair_width,
        lane_pitch=lane_pitch,
        total_height=total_height,
        footprint_area_used=footprint_area_used,
    )
