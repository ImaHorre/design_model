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
