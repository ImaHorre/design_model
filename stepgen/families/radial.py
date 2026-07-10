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

from stepgen.families.base import CommonMetrics, Family, register_family

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


@register_family
class RadialFamily(Family):
    name = "radial"

    def applicable_metrics(self) -> set[str]:
        # Uniformity is automatic (grey / N-A). Radial-specific gates are the exit
        # Ca regime and the hub pressure budget.
        return {"throughput_mlhr", "operating_Po_mbar", "regime_Ca",
                "hub_budget_pct", "build"}

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

        return RadialCompiled(
            radius_m=radius,
            upstream_width_m=w_up,
            exit_width_m=exit_w,
            exit_depth_m=exit_d,
            pitch_m=pitch,
            inlet_radius_m=r_inlet,
            t_min_m=t_min,
            square_side_m=side,
            mu_oil=float(fluids.get("mu_dispersed", 0.06)),
            gamma=float(fluids.get("gamma", 0.0)),
            min_feature_m=float(manufacturing.get("min_wall_um", 0.5)) * 1e-6,
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
    fits_square = bool(diameter <= c.square_side_m)
    area_used_cm2 = math.pi * R ** 2 * 1e4
    manufacturable = bool(
        w >= c.min_feature_m
        and c.exit_width_m >= c.min_feature_m
        and h >= c.min_feature_m
        and c.t_min_m >= c.min_feature_m
    )

    notes: list[str] = []
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
