"""
stepgen.studio.run
==================
Run an expanded study: dispatch each design point to its family and collect the
shared :class:`CommonMetrics`, capturing provenance (git hash, verbatim config
snapshot, resolved constants) so the workbook is fully auditable.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from stepgen.families import CommonMetrics, get_family
from stepgen.studio.study import Study


@dataclass
class Provenance:
    """Everything needed to reproduce a study run."""
    git_hash: str
    timestamp: str
    source_path: str | None
    source_text: str | None
    n_points: int


@dataclass
class StudyResult:
    study: Study
    metrics: list[CommonMetrics]
    provenance: Provenance
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)


def _git_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "(unknown)"
    except Exception:
        return "(unknown)"


def run_study(study: Study, *, progress: bool = False) -> StudyResult:
    """
    Evaluate every :class:`StudyPoint` in *study* through its family.

    A single failing point is captured as a CommonMetrics with an ``error`` and
    never aborts the run.
    """
    metrics: list[CommonMetrics] = []
    points = study.points
    iterator = points
    if progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(points, desc="study", unit="point")
        except Exception:
            iterator = points

    for point in iterator:
        try:
            family = get_family(point.family)
        except KeyError as exc:
            metrics.append(CommonMetrics(
                family=point.family, label=point.label, params=point.params,
                notes=[f"error: {exc}"], error=str(exc),
            ))
            continue
        cm = family.evaluate(
            point.params,
            fluids=point.fluids,
            footprint=point.footprint,
            manufacturing=point.manufacturing,
            operating=point.operating,
            label=point.label,
        )
        metrics.append(cm)

    provenance = Provenance(
        git_hash=_git_hash(),
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        source_path=study.source_path,
        source_text=study.source_text,
        n_points=len(points),
    )

    frame = pd.DataFrame([cm.to_row() for cm in metrics])
    if "_raw" in frame.columns:
        frame = frame.drop(columns=["_raw"])   # keep the tabular frame light

    return StudyResult(study=study, metrics=metrics, provenance=provenance, frame=frame)


def fill_production_thresholds(result: StudyResult, *, progress: bool = False) -> int:
    """
    Fill ``Po_min_production_mbar`` on every row, computing it **once per design**.

    The lowest drive pressure at which *every* DFU produces is a property of the
    design at a given Qw, and does not depend on the operating Po — so a 350-point
    pressure sweep needs it computed a handful of times, not 350.  It costs ~40
    network solves each (see :func:`serpentine.production_threshold_mbar`), which
    is why it is a post-pass rather than part of the solve: opt in when you want
    the column, and pay for the designs rather than the points.

    Returns the number of distinct designs actually solved for.

    Two things worth knowing before turning it on:

    * **Only serpentine has a threshold model.**  Radial and manifold rows are
      left ``None`` (grey / N-A) rather than given a borrowed number.
    * **``target_emulsion_pct`` defeats the caching, by construction.**  When Qw
      is *derived* per point it differs at every pressure, so the (design, Qw)
      key is unique per row and the cost goes back to ~40 solves per point.  That
      is not a bug — the threshold genuinely differs there — but it is the
      difference between seconds and minutes, so it is said out loud.
    """
    import json

    from stepgen.families import get_family

    points = result.study.points
    cache: dict[tuple, float | None] = {}

    def key_for(point, qw: float) -> tuple:
        # Built from the compile inputs, not from the label: a label is a display
        # string and two designs that render the same must not share an answer.
        return (
            point.family,
            json.dumps(point.params, sort_keys=True, default=str),
            json.dumps(point.fluids, sort_keys=True, default=str),
            json.dumps(point.footprint, sort_keys=True, default=str),
            json.dumps(point.manufacturing, sort_keys=True, default=str),
            round(float(qw), 9),
        )

    for point, cm in zip(points, result.metrics):
        if cm.error or cm.Qw_mlhr is None:
            continue
        if point.family != "serpentine":
            continue
        k = key_for(point, cm.Qw_mlhr)
        if k not in cache:
            from stepgen.families.serpentine import production_threshold_mbar
            try:
                family = get_family(point.family)
                compiled = family.compile(point.params, fluids=point.fluids,
                                          footprint=point.footprint,
                                          manufacturing=point.manufacturing)
                cache[k] = production_threshold_mbar(
                    compiled, Qw_mlhr=float(cm.Qw_mlhr))
            except Exception as exc:                  # never abort a solved study
                cm.notes.append(f"production threshold unavailable: {exc}")
                cache[k] = None
            if progress:
                print(f"  production threshold {len(cache)}: "
                      f"{'never (>2000 mbar)' if cache[k] is None else f'{cache[k]:.0f} mbar'}")
        cm.Po_min_production_mbar = cache[k]

    if cache:
        result.frame = pd.DataFrame([cm.to_row() for cm in result.metrics])
        if "_raw" in result.frame.columns:
            result.frame = result.frame.drop(columns=["_raw"])
    return len(cache)


def resolved_constants(study: Study) -> dict[str, Any]:
    """
    The reference block of every constant used — for the provenance panel.

    For an intent study most of these were *generated* rather than written, which
    is exactly why they have to be recorded: the audit trail is worthless if the
    values that produced a chapter only ever existed inside a fab preset.
    """
    raw = study.raw
    out = {
        "fluids": raw.get("fluids", {}),
        "footprint": raw.get("footprint", {}),
        "manufacturing": raw.get("manufacturing", {}),
        "operating": raw.get("operating", {}),
        "scoring": raw.get("scoring", {}),
    }
    if study.from_intent:
        out["intent"] = raw.get("intent", {})
        out["constraints"] = raw.get("constraints", {})   # preset spelled out
    return out
