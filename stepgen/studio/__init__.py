"""
stepgen.studio
==============
The unified design-study pipeline: one declarative config -> a fixed pipeline
-> the same standardized, scored HTML workbook every time (no per-study code).

Flow
----
    load_study(path)        parse study.yaml
        -> Study, StudyPoint[]   (grid expanded across families + swept axes)
    run_study(study)        dispatch each point to its family -> StudyResult
    score_result(...)       traffic-light scoring (worst-category-wins)
    write_workbook(...)     one self-contained HTML chapter + chapter.json

Public API
----------
    from stepgen.studio import load_study, run_study, write_workbook
"""

from __future__ import annotations

from stepgen.studio.study import (
    Study,
    StudyPoint,
    expand_grid,
    load_study,
    load_study_text,
)
from stepgen.studio.run import StudyResult, run_study
from stepgen.studio.scoring import ScoredRow, score_metrics, score_result
from stepgen.studio.references import (
    ReferencePoint,
    ReferenceSeries,
    resolve_references,
)
from stepgen.studio.workbook import write_book_index, write_workbook

__all__ = [
    "Study",
    "StudyPoint",
    "StudyResult",
    "ScoredRow",
    "ReferencePoint",
    "ReferenceSeries",
    "expand_grid",
    "load_study",
    "load_study_text",
    "run_study",
    "score_metrics",
    "score_result",
    "resolve_references",
    "write_workbook",
    "write_book_index",
]
