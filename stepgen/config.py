"""
stepgen.config
==============
YAML config loading into frozen dataclasses.

All internal storage is SI (m, Pa, m³/s, Pa·s).
User-facing YAML fields use convenient units (mbar, mL/hr); SI equivalents
are exposed as read-only properties.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def mbar_to_pa(mbar: float) -> float:
    """Millibar → Pascal."""
    return mbar * 100.0


def mlhr_to_m3s(mlhr: float) -> float:
    """mL/hr → m³/s."""
    return mlhr * (1e-6 / 3600.0)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FluidConfig:
    mu_continuous: float       # Pa·s  water (continuous phase)
    mu_dispersed: float        # Pa·s  oil  (dispersed phase — forms droplets)
    emulsion_ratio: float      # Q_oil / Q_water  (dimensionless)
    gamma: float = 0.0          # N/m  interfacial tension (optional)
    temperature_C: float = 25.0 # °C (informational)


@dataclass(frozen=True)
class MainChannelConfig:
    Mcd: float   # depth  [m]
    Mcw: float   # width  [m]
    Mcl: float   # routed length [m]


@dataclass(frozen=True)
class MicrochannelSection:
    """One section of a piecewise microchannel profile."""
    length: float  # [m]
    width: float   # [m]
    depth: float   # [m]


@dataclass(frozen=True)
class RungConfig:
    mcd: float               # depth  [m]
    mcw: float               # width  [m]
    mcl: float               # length [m]
    pitch: float             # pitch along main channel [m]
    constriction_ratio: float
    profile: tuple[MicrochannelSection, ...] = ()  # optional piecewise sections


@dataclass(frozen=True)
class JunctionConfig:
    exit_width: float            # [m]
    exit_depth: float            # [m]
    junction_type: str = "step"


@dataclass(frozen=True)
class GeometryConfig:
    main: MainChannelConfig
    rung: RungConfig
    junction: JunctionConfig
    Nmc_override: int | None = None  # if set, overrides floor(Mcl/pitch)

    @property
    def Nmc(self) -> int:
        """Number of microchannels. Uses Nmc_override if set, else floor(Mcl/pitch)."""
        if self.Nmc_override is not None:
            return self.Nmc_override
        return int(math.floor(self.main.Mcl / self.rung.pitch))


@dataclass(frozen=True)
class FootprintConfig:
    footprint_area_cm2: float = 10.0
    footprint_aspect_ratio: float = 1.5
    lane_spacing: float = 500e-6   # [m]
    turn_radius: float = 500e-6    # [m]
    reserve_border: float = 2e-3   # [m]


@dataclass(frozen=True)
class ManufacturingConfig:
    max_main_depth: float = 200e-6     # [m]
    min_feature_width: float = 0.5e-6  # [m]
    max_main_width: float = 1000e-6    # [m]


@dataclass(frozen=True)
class OperatingConfig:
    """Operating point. User-facing units stored; SI equivalents as properties."""
    Po_in_mbar: float           # oil inlet pressure [mbar]
    Qw_in_mlhr: float           # water inlet flow [mL/hr]
    P_out_mbar: float = 0.0     # outlet reference pressure [mbar]
    mode: str = "A"             # "A" = pressure+flow BC; "B" = flow+flow BC
    Qo_in_mlhr: float | None = None  # Mode B: oil inlet flow [mL/hr]

    @property
    def Po_in_Pa(self) -> float:
        return mbar_to_pa(self.Po_in_mbar)

    @property
    def Qw_in_m3s(self) -> float:
        return mlhr_to_m3s(self.Qw_in_mlhr)

    @property
    def P_out_Pa(self) -> float:
        return mbar_to_pa(self.P_out_mbar)


@dataclass(frozen=True)
class DropletModelConfig:
    """Power-law droplet diameter model: D = k * w^a * h^b.

    Calibrated from empirical data (SI units throughout):
      w=0.3µm, h=1µm  → D=1µm
      w=30µm,  h=10µm → D=25µm
      w=15µm,  h=5µm  → D=12µm

    where w = junction exit_width, h = junction exit_depth.
    Depth exponent b > width exponent a: depth dominates droplet size,
    consistent with Rayleigh-Plateau step-emulsification scaling.
    """
    k: float = 3.3935  # SI units (m^(1-a-b)); calibrated from empirical data
    a: float = 0.3390  # power on exit_width
    b: float = 0.7198  # power on exit_depth
    dP_cap_ow_mbar: float = 50.0   # oil→water capillary threshold [mbar]
    dP_cap_wo_mbar: float = 30.0   # water→oil reverse threshold [mbar]

    @property
    def dP_cap_ow_Pa(self) -> float:
        return mbar_to_pa(self.dP_cap_ow_mbar)

    @property
    def dP_cap_wo_Pa(self) -> float:
        return mbar_to_pa(self.dP_cap_wo_mbar)


@dataclass(frozen=True)
class DeviceConfig:
    fluids: FluidConfig
    geometry: GeometryConfig
    operating: OperatingConfig
    footprint: FootprintConfig = field(default_factory=FootprintConfig)
    manufacturing: ManufacturingConfig = field(default_factory=ManufacturingConfig)
    droplet_model: DropletModelConfig = field(default_factory=DropletModelConfig)


# ---------------------------------------------------------------------------
# Design-search specification dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DesignTargets:
    """Target performance specs for the design-from-targets search."""
    target_droplet_um: float       # desired droplet diameter [µm]
    target_emulsion_ratio: float   # Q_oil / Q_water (dimensionless)
    Qw_in_mlhr: float = 10.0       # water inlet flow used for Mode-B evaluation


@dataclass(frozen=True)
class DesignHardConstraints:
    """Manufacturing hard limits (non-negotiable — candidates that fail are excluded)."""
    max_main_depth_um: float = 200.0
    max_main_width_um: float = 1000.0
    min_feature_width_um: float = 0.5
    max_collapse_index: float = 8.0           # Mcw / Mcd
    min_junction_aspect_ratio: float = 2.5    # exit_width / exit_depth (lower bound)
    max_junction_aspect_ratio: float = 3.0    # exit_width / exit_depth (upper bound)
    min_Po_in_mbar: float = 0.0               # minimum derived Po [mbar]; 0 = disabled
    max_Po_in_mbar: float = 1000.0            # absolute pressure ceiling [mbar]
    max_delam_line_load_N_per_m: float | None = None  # P_peak × Mcw [N/m]; None = disabled


@dataclass(frozen=True)
class DesignSoftConstraints:
    """Soft performance limits (failing keeps candidate in results but flags it)."""
    max_Q_uniformity_pct: float = 20.0
    max_freq_uniformity_pct: float = 20.0
    max_Po_in_mbar: float = 500.0
    min_active_fraction: float = 0.95


@dataclass(frozen=True)
class SweepRanges:
    """Grid of geometry values to sweep in the design search."""
    Mcd_um: tuple[float, ...]
    Mcw_um: tuple[float, ...]
    junction_ar: tuple[float, ...]   # exit_width / exit_depth; derives mcd and pitch
    mcw_um: tuple[float, ...]
    mcl_rung_um: tuple[float, ...]


@dataclass(frozen=True)
class DesignSearchSpec:
    """
    Complete specification for a design-from-targets parameter sweep.

    Loaded from a ``design_search.yaml`` file by ``load_design_search()``.
    """
    design_targets: DesignTargets
    footprint: FootprintConfig
    hard_constraints: DesignHardConstraints
    soft_constraints: DesignSoftConstraints
    optimization_target: str         # "max_throughput" or "max_window_width"
    sweep_ranges: SweepRanges
    fluids: FluidConfig
    droplet_model: DropletModelConfig
    manufacturing: ManufacturingConfig


# ---------------------------------------------------------------------------
# Parsing helpers (private)
# ---------------------------------------------------------------------------

def _parse_fluids(d: dict[str, Any]) -> FluidConfig:
    return FluidConfig(
        mu_continuous=float(d["mu_continuous"]),
        mu_dispersed=float(d["mu_dispersed"]),
        emulsion_ratio=float(d["emulsion_ratio"]),
        gamma=float(d.get("gamma", 0.0)),
        temperature_C=float(d.get("temperature_C", 25.0)),
    )


def _parse_geometry(d: dict[str, Any]) -> GeometryConfig:
    m = d["main"]
    main = MainChannelConfig(
        Mcd=float(m["Mcd"]),
        Mcw=float(m["Mcw"]),
        Mcl=float(m["Mcl"]),
    )

    r = d["rung"]
    raw_sections = r.get("microchannel_profile", {}).get("sections", [])
    profile = tuple(
        MicrochannelSection(
            length=float(s["length"]),
            width=float(s["width"]),
            depth=float(s["depth"]),
        )
        for s in raw_sections
    )
    rung = RungConfig(
        mcd=float(r["mcd"]),
        mcw=float(r["mcw"]),
        mcl=float(r["mcl"]),
        pitch=float(r["pitch"]),
        constriction_ratio=float(r["constriction_ratio"]),
        profile=profile,
    )

    j = d.get("junction", {})
    junction = JunctionConfig(
        exit_width=float(j.get("exit_width", r["mcw"])),
        exit_depth=float(j.get("exit_depth", r["mcd"])),
        junction_type=str(j.get("junction_type", "step")),
    )

    nmc_override_raw = d.get("Nmc_override", None)
    nmc_override = int(nmc_override_raw) if nmc_override_raw is not None else None

    return GeometryConfig(main=main, rung=rung, junction=junction, Nmc_override=nmc_override)


def _parse_operating(d: dict[str, Any]) -> OperatingConfig:
    qo_raw = d.get("Qo_in_mlhr", None)
    return OperatingConfig(
        Po_in_mbar=float(d["Po_in_mbar"]),
        Qw_in_mlhr=float(d["Qw_in_mlhr"]),
        P_out_mbar=float(d.get("P_out_mbar", 0.0)),
        mode=str(d.get("mode", "A")),
        Qo_in_mlhr=float(qo_raw) if qo_raw is not None else None,
    )


def _parse_footprint(d: dict[str, Any]) -> FootprintConfig:
    return FootprintConfig(
        footprint_area_cm2=float(d.get("footprint_area_cm2", 10.0)),
        footprint_aspect_ratio=float(d.get("footprint_aspect_ratio", 1.5)),
        lane_spacing=float(d.get("lane_spacing", 500e-6)),
        turn_radius=float(d.get("turn_radius", 500e-6)),
        reserve_border=float(d.get("reserve_border", 2e-3)),
    )


def _parse_manufacturing(d: dict[str, Any]) -> ManufacturingConfig:
    return ManufacturingConfig(
        max_main_depth=float(d.get("max_main_depth", 200e-6)),
        min_feature_width=float(d.get("min_feature_width", 0.5e-6)),
        max_main_width=float(d.get("max_main_width", 1000e-6)),
    )


def _parse_droplet_model(d: dict[str, Any]) -> DropletModelConfig:
    return DropletModelConfig(
        k=float(d.get("k", 1.2)),
        a=float(d.get("a", 0.5)),
        b=float(d.get("b", 0.3)),
        dP_cap_ow_mbar=float(d.get("dP_cap_ow_mbar", 50.0)),
        dP_cap_wo_mbar=float(d.get("dP_cap_wo_mbar", 30.0)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> DeviceConfig:
    """Load a YAML config file and return a DeviceConfig."""
    with open(path, "r") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)

    return DeviceConfig(
        fluids=_parse_fluids(raw["fluids"]),
        geometry=_parse_geometry(raw["geometry"]),
        operating=_parse_operating(raw["operating"]),
        footprint=_parse_footprint(raw.get("footprint", {})),
        manufacturing=_parse_manufacturing(raw.get("manufacturing", {})),
        droplet_model=_parse_droplet_model(raw.get("droplet_model", {})),
    )


def load_design_search(path: str | Path) -> "DesignSearchSpec":
    """
    Load a design-search YAML file and return a DesignSearchSpec.

    The YAML schema has top-level keys: design_targets, fluids, footprint,
    hard_constraints, soft_constraints, optimization_target, sweep_ranges,
    and optionally droplet_model / manufacturing.
    """
    with open(path, "r") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)

    dt = raw["design_targets"]
    targets = DesignTargets(
        target_droplet_um=float(dt["target_droplet_um"]),
        target_emulsion_ratio=float(dt["target_emulsion_ratio"]),
        Qw_in_mlhr=float(dt.get("Qw_in_mlhr", 10.0)),
    )

    hc = raw.get("hard_constraints", {})
    _delam_raw = hc.get("max_delam_line_load_N_per_m", None)
    hard = DesignHardConstraints(
        max_main_depth_um=float(hc.get("max_main_depth_um", 200.0)),
        max_main_width_um=float(hc.get("max_main_width_um", 1000.0)),
        min_feature_width_um=float(hc.get("min_feature_width_um", 0.5)),
        max_collapse_index=float(hc.get("max_collapse_index", 8.0)),
        min_junction_aspect_ratio=float(hc.get("min_junction_aspect_ratio", 2.5)),
        max_junction_aspect_ratio=float(hc.get("max_junction_aspect_ratio", 3.0)),
        min_Po_in_mbar=float(hc.get("min_Po_in_mbar", 0.0)),
        max_Po_in_mbar=float(hc.get("max_Po_in_mbar", 1000.0)),
        max_delam_line_load_N_per_m=float(_delam_raw) if _delam_raw is not None else None,
    )

    sc = raw.get("soft_constraints", {})
    soft = DesignSoftConstraints(
        max_Q_uniformity_pct=float(sc.get("max_Q_uniformity_pct", 20.0)),
        max_freq_uniformity_pct=float(sc.get("max_freq_uniformity_pct", 20.0)),
        max_Po_in_mbar=float(sc.get("max_Po_in_mbar", 500.0)),
        min_active_fraction=float(sc.get("min_active_fraction", 0.95)),
    )

    sr = raw["sweep_ranges"]
    ranges = SweepRanges(
        Mcd_um=tuple(float(v) for v in sr["Mcd_um"]),
        Mcw_um=tuple(float(v) for v in sr["Mcw_um"]),
        junction_ar=tuple(float(v) for v in sr.get("junction_ar", [2.5, 3.0])),
        mcw_um=tuple(float(v) for v in sr["mcw_um"]),
        mcl_rung_um=tuple(float(v) for v in sr["mcl_rung_um"]),
    )

    opt_target = str(raw.get("optimization_target", "max_throughput"))

    return DesignSearchSpec(
        design_targets=targets,
        footprint=_parse_footprint(raw.get("footprint", {})),
        hard_constraints=hard,
        soft_constraints=soft,
        optimization_target=opt_target,
        sweep_ranges=ranges,
        fluids=_parse_fluids(raw.get("fluids", {
            "mu_continuous": 0.00089,
            "mu_dispersed":  0.03452,
            "emulsion_ratio": targets.target_emulsion_ratio,
        })),
        droplet_model=_parse_droplet_model(raw.get("droplet_model", {})),
        manufacturing=_parse_manufacturing(raw.get("manufacturing", {})),
    )
