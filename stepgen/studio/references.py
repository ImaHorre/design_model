"""
stepgen.studio.references
=========================
Resolve a study's optional ``reference:`` block into overlay series that the
workbook draws **on top of** the scored scatter plots.  These are *click-in*
overlays, never an automatic baseline compare — a reference only appears
because the study explicitly asked for it.

Three reference kinds are supported:

``modelled``
    ``{ kind: modelled, config: <path.yaml>, label: ..., Po_mbar: <opt> }``
    Load a device config and solve it through the serpentine family at its own
    (or an overridden) operating point → one fully-populated overlay point.

``experimental``
    ``{ kind: experimental, csv: <path>, filter: {<col>: <val>}, label: ... }``
    Read a lab CSV, filter on its **original** column names, then adapt the
    columns to the canonical experiment schema
    (``stepgen.io.experiments`` names) via :data:`_COLUMN_ADAPTER`.  Each row
    becomes an overlay point carrying ``operating_Po_mbar`` and ``droplet_um``.

``chapter``
    ``{ kind: chapter, json: <book/other.json>, filter: {...}, label: ... }``
    Read another chapter's JSON sidecar and overlay its device rows — the
    cross-chapter reference mechanism.

Every resolver is defensive: a missing file or bad row yields a
:class:`ReferenceSeries` with an ``error`` note instead of aborting the study.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# stage_timings.csv (and similar lab exports) -> canonical experiment schema.
# Mirrors the adapter described in the studio plan.
_COLUMN_ADAPTER: dict[str, str] = {
    "DeviceID": "device_id",
    "DispPhasePressure": "Po_in_mbar",
    "ContPhaseFlow": "Qw_in_mlhr",
    "Droplet_diameter_um": "droplet_diameter_um",
}


@dataclass
class ReferencePoint:
    """One overlay marker with whatever comparable metrics are known for it."""
    label: str
    throughput_mlhr: float | None = None
    uniformity_pct: float | None = None
    operating_Po_mbar: float | None = None
    droplet_um: float | None = None
    N_dfu: float | None = None
    regime_Ca: float | None = None


@dataclass
class ReferenceSeries:
    """A named set of overlay points from one ``reference:`` entry."""
    label: str
    kind: str
    points: list[ReferencePoint] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------

def _resolve_modelled(entry: dict[str, Any], base: Path) -> ReferenceSeries:
    label = str(entry.get("label", entry.get("config", "modelled")))
    cfg_path = entry.get("config")
    if not cfg_path:
        return ReferenceSeries(label, "modelled", error="no 'config' given")
    path = _locate(cfg_path, base)
    if path is None:
        return ReferenceSeries(label, "modelled", error=f"config not found: {cfg_path}")
    try:
        from stepgen.config import load_config
        from stepgen.families.serpentine import solve_config

        cfg = load_config(path)
        Po = float(entry.get("Po_mbar", cfg.operating.Po_in_mbar))
        Qw = float(entry.get("Qw_mlhr", cfg.operating.Qw_in_mlhr))
        cm = solve_config(cfg, Po_mbar=Po, Qw_mlhr=Qw, label=label)
        pt = ReferencePoint(
            label=label,
            throughput_mlhr=cm.throughput_mlhr,
            uniformity_pct=cm.uniformity_pct,
            operating_Po_mbar=cm.operating_Po_mbar,
            droplet_um=cm.droplet_um,
            N_dfu=cm.N_dfu,
            regime_Ca=cm.regime_Ca,
        )
        return ReferenceSeries(label, "modelled", points=[pt])
    except Exception as exc:  # noqa: BLE001 — a bad reference must not kill the study
        return ReferenceSeries(label, "modelled", error=str(exc))


def _resolve_experimental(entry: dict[str, Any], base: Path) -> ReferenceSeries:
    label = str(entry.get("label", entry.get("csv", "experimental")))
    csv = entry.get("csv")
    if not csv:
        return ReferenceSeries(label, "experimental", error="no 'csv' given")
    path = _locate(csv, base)
    if path is None:
        return ReferenceSeries(label, "experimental", error=f"csv not found: {csv}")
    try:
        import pandas as pd

        df = pd.read_csv(path)
        # filter on ORIGINAL column names before adapting
        for col, val in (entry.get("filter") or {}).items():
            if col in df.columns:
                df = df[df[col].astype(str) == str(val)]
        df = df.rename(columns={k: v for k, v in _COLUMN_ADAPTER.items() if k in df.columns})

        points: list[ReferencePoint] = []
        for _, row in df.iterrows():
            Po = _num(row.get("Po_in_mbar"))
            D = _num(row.get("droplet_diameter_um"))
            if Po is None and D is None:
                continue
            points.append(ReferencePoint(label=label, operating_Po_mbar=Po, droplet_um=D))
        if not points:
            return ReferenceSeries(label, "experimental",
                                   error="no rows after filter/adapt")
        return ReferenceSeries(label, "experimental", points=points)
    except Exception as exc:  # noqa: BLE001
        return ReferenceSeries(label, "experimental", error=str(exc))


def _resolve_chapter(entry: dict[str, Any], base: Path) -> ReferenceSeries:
    import json

    label = str(entry.get("label", entry.get("json", "chapter")))
    jf = entry.get("json")
    if not jf:
        return ReferenceSeries(label, "chapter", error="no 'json' given")
    path = _locate(jf, base)
    if path is None:
        return ReferenceSeries(label, "chapter", error=f"chapter json not found: {jf}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        flt = entry.get("filter") or {}
        points: list[ReferencePoint] = []
        for r in data.get("rows", []):
            if any(str(r.get(k)) != str(v) for k, v in flt.items()):
                continue
            m = r.get("metrics", {})
            points.append(ReferencePoint(
                label=r.get("label", label),
                throughput_mlhr=_num(m.get("throughput_mlhr")),
                uniformity_pct=_num(m.get("uniformity_pct")),
                operating_Po_mbar=_num(m.get("operating_Po_mbar")),
                droplet_um=_num(m.get("droplet_um")),
                N_dfu=_num(m.get("N_dfu")),
                regime_Ca=_num(m.get("regime_Ca")),
            ))
        if not points:
            return ReferenceSeries(label, "chapter", error="no rows after filter")
        return ReferenceSeries(label, "chapter", points=points)
    except Exception as exc:  # noqa: BLE001
        return ReferenceSeries(label, "chapter", error=str(exc))


_RESOLVERS = {
    "modelled": _resolve_modelled,
    "experimental": _resolve_experimental,
    "chapter": _resolve_chapter,
}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f   # drop NaN


def _locate(path_str: str, base: Path) -> Path | None:
    """
    Find a referenced file, tolerating both conventions used in study configs:
    repo-root/CWD-relative (e.g. ``configs/v5_30.yaml``) and study-dir-relative
    (e.g. ``../experimental_workspaces/...``).  Returns the first that exists.
    """
    p = Path(path_str)
    candidates = [p] if p.is_absolute() else [Path.cwd() / p, base / p]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def resolve_references(study, *, base_dir: str | Path | None = None) -> list[ReferenceSeries]:
    """
    Resolve every entry in ``study.references`` into a :class:`ReferenceSeries`.

    Relative paths are resolved against *base_dir* (defaults to the directory of
    the study source file, else the current directory).
    """
    if base_dir is not None:
        base = Path(base_dir)
    elif getattr(study, "source_path", None):
        base = Path(study.source_path).resolve().parent
    else:
        base = Path.cwd()

    out: list[ReferenceSeries] = []
    for entry in getattr(study, "references", []) or []:
        kind = str(entry.get("kind", "")).lower()
        resolver = _RESOLVERS.get(kind)
        if resolver is None:
            out.append(ReferenceSeries(
                label=str(entry.get("label", kind or "reference")),
                kind=kind or "unknown",
                error=f"unknown reference kind '{kind}'",
            ))
            continue
        out.append(resolver(entry, base))
    return out
