"""
stepgen.studio
==============
The unified design-study pipeline: one declarative config -> a fixed pipeline
-> the same standardized, scored HTML workbook every time (no per-study code).

Flow
----
    load_study(path)        parse study.yaml
        expand_intent(...)      an `intent:` block generates the grid first
        -> Study, StudyPoint[]   (grid expanded across families + swept axes)
    run_study(study)        dispatch each point to its family -> StudyResult
    score_result(...)       traffic-light scoring (worst-category-wins)
    build_grouping(...)     split designs from the conditions they were run at
    decide(...)             per-axis winners, Pareto, all-round, safest
    decide_subset(...)      the same, per design
    measured_levers(...)    what one notch of each swept axis actually moved
    diagnose(...)           binding constraint + what relaxing it would buy
    write_workbook(...)     one self-contained HTML chapter + chapter.json

Public API
----------
    from stepgen.studio import load_study, run_study, write_workbook
"""

from __future__ import annotations

from stepgen.studio.study import (
    Study,
    StudyPoint,
    build_study,
    expand_grid,
    load_study,
    load_study_text,
)
from stepgen.studio.intent import IntentPlan, expand_intent, generated_yaml, has_intent
from stepgen.studio.grouping import (
    Axis,
    DesignGroup,
    Grouping,
    build_grouping,
    varying_axes,
)
from stepgen.studio.levers import (
    LeverStep,
    StructuralLever,
    measured_levers,
    structural_levers,
)
from stepgen.studio.ranking import decide, decide_subset
from stepgen.studio.run import StudyResult, run_study
from stepgen.studio.scoring import ScoredRow, score_metrics, score_result
from stepgen.studio.diagnosis import Diagnosis, binding_gates, diagnose
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
    "Axis",
    "DesignGroup",
    "Grouping",
    "Diagnosis",
    "IntentPlan",
    "LeverStep",
    "ReferencePoint",
    "ReferenceSeries",
    "StructuralLever",
    "binding_gates",
    "build_grouping",
    "build_study",
    "decide",
    "decide_subset",
    "diagnose",
    "measured_levers",
    "structural_levers",
    "varying_axes",
    "expand_grid",
    "expand_intent",
    "generated_yaml",
    "has_intent",
    "load_study",
    "load_study_text",
    "run_study",
    "score_metrics",
    "score_result",
    "resolve_references",
    "write_workbook",
    "write_book_index",
]
