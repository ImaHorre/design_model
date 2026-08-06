"""
stepgen.studio.form
===================
The structured study builder behind the Studio front door (plan C2).

Three regions, and the whole point of the split is which of them *multiplies*:

    DESIGNS (set, concatenated)     30x10 | 60x20 | 30x20 | 15x10
    FLUIDS  (set, concatenated)     µ_dispersed / µ_continuous  + o/w<->w/o label
    AXES    (grid, crossed)         Po 200..1200 (6 levels), main length
                                    points = 4 x 2 x 6 = 48

**Sets and axes are the same YAML construct in two positions.**  ``expand_grid``
treats a list as "the options for this slot" everywhere; a list of *whole
blocks* under ``serpentine:`` or ``fluids:`` therefore concatenates, while a
list of *scalars inside* a block multiplies with its siblings.  A form that let
you type ``mu_dispersed: [0.06, 0.00089]`` next to a matching ``mu_continuous``
list would cross them, and half the resulting points would be fluids that do not
exist (µ_dispersed == µ_continuous).  So fluids are whole blocks here, never
independent viscosity lists — the same reason exits live in the design region
and never on the dial.

This module writes the YAML shape ``configs/study_my_designs.yaml`` already
uses.  It deliberately does **not** use YAML anchors: the ``<<: *rung`` merge is
shallow, so writing ``rung: { upstream_width_um: 40 }`` under a ``<<: *ladder``
design replaces the whole rung block and silently drops the rest.  That is a
hazard worth documenting for a human editing a file by hand and a hazard worth
simply not having in generated output, so every block is emitted in full.

The generated text is the deliverable, not an internal representation: it goes
into the form's textarea, where it can be hand-tuned before running, and it is
what ``load_study_text`` parses.  Nothing here solves anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Which phase a label claims is dispersed, and therefore which viscosity should
#: be the larger one.  This is the *only* thing the o/w <-> w/o toggle knows.
#:
#: ``phase_system`` branches no physics — all twelve reads of it are display
#: (``config.channel_labels``, two CLI prints, a plot title, studio grouping) and
#: nothing in the ladder solve consults it.  But ``study._fluid_tag`` makes it the
#: row discriminator, and ``decide.group_by`` is what separates a design from a
#: condition, so a label disagreeing with its viscosities changes how rows
#: **group** even though every solved number is right.
#:
#: Hence: the toggle sets the label, the µ fields set the physics, and the two
#: are checked against each other rather than derived from each other.  "Which
#: phase is dispersed" is not recoverable from magnitudes in general — it happens
#: to be here only because one phase is always oil and one is always water.
PHASE_SYSTEMS = ("o/w", "w/o")


@dataclass
class FormDesign:
    """One whole design — a set member, never crossed with another design."""

    exit_width_um: float
    exit_depth_um: float
    pitch_um: float
    upstream_width_um: float
    #: rung (DFU) length [mm]; per design because it is geometry, not a condition
    rung_length_mm: float = 4.0
    label: str = ""

    def as_block(self, main: dict[str, Any]) -> dict[str, Any]:
        return {
            "main": dict(main),
            "rung": {
                "length_mm": self.rung_length_mm,
                "upstream_width_um": self.upstream_width_um,
            },
            "junction": {
                "exit_width_um": self.exit_width_um,
                "exit_depth_um": self.exit_depth_um,
                "pitch_um": self.pitch_um,
            },
        }


@dataclass
class FormFluid:
    """
    One whole fluid system — a set member.

    ``mu_dispersed`` and ``mu_continuous`` are the entire hydraulic control:
    ``resistance.py`` builds the rung and the dispersed main from
    ``mu_dispersed`` and the continuous main from ``mu_continuous``, and nothing
    else in the ladder reads a fluid property.

    ``gamma`` is live — it enters the exit capillary number and stage 2 — but it
    gates nothing, because the operating gate is ``v_vs_demonstrated``, a ratio
    of exit velocities in which γ cancels exactly.  It is unmeasured for the Peak
    system, so it is optional here and carries that caveat rather than a default
    that looks authoritative.

    Density and contact angle are deliberately absent: ``rho_continuous`` is not
    a ``FluidConfig`` field at all (both uses are
    ``getattr(config.fluids, 'rho_continuous', 1000.0)``, so they silently always
    get water) and both call sites are diagnostic-only.  A field for either would
    be inert.
    """

    mu_dispersed: float          # Pa·s
    mu_continuous: float         # Pa·s
    phase_system: str = "o/w"    # LABEL ONLY — see PHASE_SYSTEMS
    gamma: float | None = None   # N/m; omitted from the YAML when None

    def as_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {
            "mu_dispersed": self.mu_dispersed,
            "mu_continuous": self.mu_continuous,
        }
        if self.gamma is not None:
            block["gamma"] = self.gamma
        block["phase_system"] = self.phase_system
        return block

    @property
    def label_matches_viscosities(self) -> bool:
        """
        Does the label agree with which viscosity is larger?

        o/w means oil is dispersed, so ``mu_dispersed`` should be the larger.
        w/o means water is dispersed, so it should be the smaller.  Equal
        viscosities agree with nothing and are reported separately.
        """
        if self.mu_dispersed == self.mu_continuous:
            return False
        oil_is_dispersed = self.mu_dispersed > self.mu_continuous
        return oil_is_dispersed == (self.phase_system == "o/w")


@dataclass
class FormAxes:
    """
    The crossed region.  Every list here multiplies the point count.

    ``Po_mbar`` is the dial.  Exits are **not** here and must never be: a
    4-exit × fluid-swap study written as crossed axes produced 64 points of
    which 32 were fluid systems that do not exist.
    """

    Po_mbar: list[float] = field(default_factory=list)
    main_length_mm: list[float] = field(default_factory=list)
    #: give exactly one of these two — the engine raises if both are set
    Qw_mlhr: float | None = 5.0
    target_emulsion_pct: float | None = None

    @property
    def n_crossed(self) -> int:
        return max(1, len(self.Po_mbar)) * max(1, len(self.main_length_mm))


@dataclass
class StudyForm:
    """The whole form: three regions plus the house blocks it starts from."""

    title: str = "Untitled study"
    designs: list[FormDesign] = field(default_factory=list)
    fluids: list[FormFluid] = field(default_factory=list)
    axes: FormAxes = field(default_factory=FormAxes)
    main_depth_um: float = 400.0
    main_width_um: float = 2000.0
    footprint: dict[str, Any] = field(default_factory=dict)
    manufacturing: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        """
        Exact, because ``len(study.points)`` is known before anything is solved.

        designs x fluids x (crossed axes) — sets add, axes multiply.
        """
        return (max(1, len(self.designs))
                * max(1, len(self.fluids))
                * self.axes.n_crossed)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FormIssue:
    """One problem with a form. ``blocking`` decides whether it stops a run."""

    level: str        # "error" | "warning"
    where: str        # "designs" | "fluids" | "axes" | "form"
    message: str

    @property
    def blocking(self) -> bool:
        return self.level == "error"


def validate(form: StudyForm) -> list[FormIssue]:
    """
    Everything wrong with *form*, worst first.

    **Errors block; warnings do not.**  The line between them is whether
    proceeding would produce something meaningless or merely something the user
    may have meant.  An empty design region cannot produce a study at all; a
    label that disagrees with its viscosities produces a perfectly correct solve
    under a name that will group it oddly, and that is the user's call to make.
    """
    issues: list[FormIssue] = []

    if not form.designs:
        issues.append(FormIssue("error", "designs", "add at least one design"))
    if not form.fluids:
        issues.append(FormIssue("error", "fluids", "add at least one fluid system"))

    axes = form.axes
    if not axes.Po_mbar:
        issues.append(FormIssue("error", "axes", "the pressure axis needs at least one level"))
    if axes.Qw_mlhr is not None and axes.target_emulsion_pct is not None:
        issues.append(FormIssue(
            "error", "axes",
            "give Qw OR target emulsion %, never both — the solve raises on both"))
    if axes.Qw_mlhr is None and axes.target_emulsion_pct is None:
        issues.append(FormIssue(
            "error", "axes", "give one of Qw or target emulsion %"))

    for i, d in enumerate(form.designs, 1):
        for name, value in (("exit width", d.exit_width_um),
                            ("exit depth", d.exit_depth_um),
                            ("pitch", d.pitch_um),
                            ("upstream width", d.upstream_width_um)):
            if value <= 0:
                issues.append(FormIssue(
                    "error", "designs", f"design {i}: {name} must be positive"))
        if d.pitch_um < d.exit_width_um:
            issues.append(FormIssue(
                "warning", "designs",
                f"design {i}: pitch {d.pitch_um:g} µm is under the exit width "
                f"{d.exit_width_um:g} µm — the DFUs overlap"))

    for i, f in enumerate(form.fluids, 1):
        if f.mu_dispersed <= 0 or f.mu_continuous <= 0:
            issues.append(FormIssue(
                "error", "fluids", f"fluid {i}: viscosities must be positive"))
            continue
        if f.phase_system not in PHASE_SYSTEMS:
            issues.append(FormIssue(
                "error", "fluids",
                f"fluid {i}: phase system must be one of {', '.join(PHASE_SYSTEMS)}"))
        if f.mu_dispersed == f.mu_continuous:
            issues.append(FormIssue(
                "warning", "fluids",
                f"fluid {i}: both phases at {f.mu_dispersed * 1e3:g} cP — that is "
                f"one fluid, not an emulsion"))
        elif not f.label_matches_viscosities:
            # WARN, NEVER BLOCK.  phase_system branches no physics, so a mismatch
            # cannot make a solved number wrong — only the row's grouping label.
            # And the check is a heuristic that holds here only because one phase
            # is always oil and one always water; two oils of similar viscosity
            # would trip it correctly-labelled. Refusing a study on a heuristic
            # the code itself says is not general would be the tool overruling a
            # choice the user made.
            dispersed = "oil" if f.phase_system == "o/w" else "water"
            issues.append(FormIssue(
                "warning", "fluids",
                f"fluid {i}: labelled {f.phase_system} (so {dispersed} is dispersed) "
                f"but µ_dispersed {f.mu_dispersed * 1e3:g} cP is "
                f"{'higher' if f.mu_dispersed > f.mu_continuous else 'lower'} than "
                f"µ_continuous {f.mu_continuous * 1e3:g} cP. The label sets no "
                f"physics — the solve uses the viscosities as typed — but it does "
                f"decide how rows group. Check which phase you meant."))

    if len(form.fluids) > 1:
        seen: dict[tuple, int] = {}
        for i, f in enumerate(form.fluids, 1):
            key = (f.mu_dispersed, f.mu_continuous, f.phase_system)
            if key in seen:
                issues.append(FormIssue(
                    "warning", "fluids",
                    f"fluid {i} is identical to fluid {seen[key]} — it doubles the "
                    f"point count and answers nothing new"))
            else:
                seen[key] = i

    issues.sort(key=lambda x: 0 if x.level == "error" else 1)
    return issues


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------

def _num(x: float) -> str:
    """Shortest faithful rendering — 400 not 400.0, 0.00089 not 8.9e-04."""
    f = float(x)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return f"{f:.10g}"


def _list(values: list[float]) -> str:
    return "[" + ", ".join(_num(v) for v in values) + "]"


def _scalar(v: Any) -> str:
    """One YAML scalar.  Bools first — ``bool`` is a subclass of ``int``, and
    emitting Python's ``True`` where YAML wants ``true`` is the kind of thing
    that parses under YAML 1.1 and stops parsing the day it does not."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return _num(v)
    return str(v)


def _mapping(block: dict[str, Any]) -> str:
    return "{ " + ", ".join(f"{k}: {_scalar(v)}" for k, v in block.items()) + " }"


def _scoring_yaml(scoring: dict[str, Any], indent: str = "  ") -> list[str]:
    lines: list[str] = []
    for key, spec in scoring.items():
        if isinstance(spec, dict):
            lines.append(f"{indent}{key + ':':19s}{_mapping(spec)}")
        else:
            lines.append(f"{indent}{key}: {_scalar(spec)}")
    return lines


def build_yaml(form: StudyForm) -> str:
    """
    Render *form* as a study YAML that ``load_study_text`` parses.

    No anchors, by choice — see the module docstring.  Every design block is
    written out in full, so there is no shallow-merge trap to fall into and no
    way for one edit to silently empty another block.
    """
    designs = form.designs or []
    fluids = form.fluids or []
    axes = form.axes

    main: dict[str, Any] = {}
    if axes.main_length_mm:
        main["length_mm"] = axes.main_length_mm
    main["depth_um"] = form.main_depth_um
    main["width_um"] = form.main_width_um

    L: list[str] = []
    L.append("# Generated by the StepGen Design Studio form.")
    L.append("# Edit freely — this is a normal study config, and the textarea it")
    L.append("# came from is what actually gets run.")
    L.append("#")
    L.append("# THE SET-VS-AXIS RULE, which is the whole shape of this file:")
    L.append("#   `serpentine:` and `fluids:` are lists of WHOLE BLOCKS. They")
    L.append("#   CONCATENATE — 4 designs cost 4 points, not 4x anything.")
    L.append("#   A list INSIDE a block (main.length_mm, operating.Po_mbar) is an")
    L.append("#   AXIS and CROSSES with every other list.")
    L.append(f"#   {len(designs)} designs x {len(fluids)} fluids x "
             f"{axes.n_crossed} crossed = {form.n_points} points.")
    L.append("#")
    L.append("# No YAML anchors here on purpose. `<<:` merge is SHALLOW, so")
    L.append("# `rung: { upstream_width_um: 40 }` under a merged design REPLACES")
    L.append("# the whole rung block and silently drops the rest. Every block")
    L.append("# below is written out in full instead.")
    L.append("")
    L.append(f"title: {form.title!r}")
    L.append("")
    L.append("family: serpentine")
    L.append("")

    # ── designs: the set region ────────────────────────────────────────────
    L.append("# ── DESIGNS — a SET. Exits live here and never on an axis: a")
    L.append("#    4-exit x fluid-swap study written as crossed axes produced 64")
    L.append("#    points of which 32 were fluids that do not exist.")
    L.append("serpentine:")
    for d in designs:
        block = d.as_block(main)
        comment = f"    # {d.label}" if d.label else ""
        L.append(f"  - main: {{ length_mm: {_list(main['length_mm'])}, "
                 f"depth_um: {_num(main['depth_um'])}, "
                 f"width_um: {_num(main['width_um'])} }}"
                 if "length_mm" in main else
                 f"  - main: {{ depth_um: {_num(main['depth_um'])}, "
                 f"width_um: {_num(main['width_um'])} }}")
        L.append(f"    rung: {{ length_mm: {_num(block['rung']['length_mm'])}, "
                 f"upstream_width_um: {_num(block['rung']['upstream_width_um'])} }}")
        L.append(f"    junction: {{ exit_width_um: {_num(d.exit_width_um)}, "
                 f"exit_depth_um: {_num(d.exit_depth_um)}, "
                 f"pitch_um: {_num(d.pitch_um)} }}{comment}")
    L.append("")

    # ── fluids: the other set region ───────────────────────────────────────
    L.append("# ── FLUIDS — a SET of whole blocks, so a system's two viscosities")
    L.append("#    stay paired. Never `mu_dispersed: [a, b]` with a matching")
    L.append("#    mu_continuous list: those CROSS, and half the points become")
    L.append("#    fluids where the two phases are the same liquid.")
    L.append("#")
    L.append("#    mu_dispersed and mu_continuous are the WHOLE hydraulic control.")
    L.append("#    phase_system is a LABEL — it branches no physics, but it is the")
    L.append("#    row discriminator, so it decides how rows GROUP.")
    L.append("fluids:")
    for f in fluids:
        L.append(f"  - {_mapping(f.as_block())}")
    if any(f.gamma is not None for f in fluids):
        L.append("  # gamma is UNMEASURED for this system. Ca is proportional to 1/gamma,")
        L.append("  # so gamma alone would decide a Ca verdict — which is why the")
        L.append("  # operating gate is v_vs_demonstrated, where gamma cancels exactly.")
    L.append("")

    # ── the crossed region ─────────────────────────────────────────────────
    L.append("# ── AXES — everything here MULTIPLIES the point count.")
    L.append("operating:")
    L.append(f"  Po_mbar: {_list(axes.Po_mbar)}")
    if axes.Qw_mlhr is not None:
        L.append(f"  Qw_mlhr: {_num(axes.Qw_mlhr)}")
    if axes.target_emulsion_pct is not None:
        L.append(f"  target_emulsion_pct: {_num(axes.target_emulsion_pct)}")
    L.append("  # Give Qw_mlhr OR target_emulsion_pct, never both (the solve raises).")
    L.append("  # Fixed Qw is faster; a target emulsion % costs ~12 extra solves per")
    L.append("  # point but removes the bias of comparing designs at different")
    L.append("  # dispersed fractions.")
    L.append("")

    if form.footprint:
        L.append("footprint:")
        for k, v in form.footprint.items():
            L.append(f"  {k}: {_scalar(v)}")
        L.append("")
    if form.manufacturing:
        L.append("manufacturing:")
        for k, v in form.manufacturing.items():
            L.append(f"  {k}: {_scalar(v)}")
        L.append("")
    if form.scoring:
        L.append("scoring:")
        L.extend(_scoring_yaml(form.scoring))
        L.append("")

    # ── decide: what counts as one design ──────────────────────────────────
    L.append("# `group_by` names the axes that make a row a different DEVICE.")
    L.append("# Everything else that varies (main length, pressure, fluid) is a")
    L.append("# CONDITION explored inside each design — so each design is ranked")
    L.append("# against its own conditions rather than against a bigger exit run")
    L.append("# harder. Without this, sweeping main length would report the")
    L.append(f"# {len(designs)} designs as {len(designs) * max(1, len(axes.main_length_mm))}.")
    L.append("decide:")
    L.append("  axes: [throughput, flatness, drive_pressure, margin]")
    L.append("  group_by:")
    for key in ("junction.exit_width_um", "junction.exit_depth_um",
                "junction.pitch_um", "rung.upstream_width_um"):
        L.append(f"    - {key}")
    L.append("")

    return "\n".join(L)


# ---------------------------------------------------------------------------
# Starting point
# ---------------------------------------------------------------------------

def po_levels(lo: float, hi: float, n: int) -> list[float]:
    """
    *n* pressures from *lo* to *hi* inclusive — the coarse/fine dial.

    Rounded to whole mbar because the gate can only quote a pressure that was
    actually simulated, and a level of 233.3333 mbar reads as false precision on
    a number nobody set.
    """
    n = max(1, int(n))
    if n == 1:
        return [round(float(lo))]
    step = (float(hi) - float(lo)) / (n - 1)
    return [round(float(lo) + step * i) for i in range(n)]


def form_from_defaults(defaults: Any = None) -> StudyForm:
    """
    The form as it first loads, seeded from ``configs/studio_defaults.yaml``.

    The house file is the single reviewable place those numbers live (plan C3);
    this reads it rather than restating any of it, so changing that file changes
    what a new study starts from and nothing here has to be kept in step.
    """
    if defaults is None:
        from stepgen.studio.defaults import load_defaults
        defaults = load_defaults()

    sweep = defaults.sweep_defaults or {}
    fluid_block = dict(sweep.get("fluids", {}) or {})
    operating = dict(sweep.get("operating", {}) or {})

    mu_d = float(fluid_block.get("mu_dispersed", 0.06))
    mu_c = float(fluid_block.get("mu_continuous", 0.00089))
    gamma = fluid_block.get("gamma")
    phase = str(fluid_block.get("phase_system", "o/w"))

    po = [float(p) for p in _as_list(operating.get("Po_mbar", [200.0]))]

    return StudyForm(
        title="Untitled study",
        designs=[
            FormDesign(exit_width_um=30, exit_depth_um=10, pitch_um=60,
                       upstream_width_um=8, label="30x10"),
        ],
        fluids=[
            FormFluid(mu_dispersed=mu_d, mu_continuous=mu_c,
                      phase_system=phase,
                      gamma=None if gamma is None else float(gamma)),
        ],
        axes=FormAxes(
            Po_mbar=po,
            main_length_mm=[40.0],
            Qw_mlhr=(None if operating.get("Qw_mlhr") is None
                     else float(operating["Qw_mlhr"])),
            target_emulsion_pct=(None if operating.get("target_emulsion_pct") is None
                                 else float(operating["target_emulsion_pct"])),
        ),
        footprint=dict(sweep.get("footprint", {}) or {}),
        manufacturing=dict(sweep.get("manufacturing", {}) or {}),
        scoring=dict(sweep.get("scoring", {}) or {}),
    )


def _as_list(v: Any) -> list[Any]:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


# ---------------------------------------------------------------------------
# The wire format the form posts
# ---------------------------------------------------------------------------

def form_from_payload(payload: dict[str, Any]) -> StudyForm:
    """Build a :class:`StudyForm` from the JSON the browser posts."""
    designs = [
        FormDesign(
            exit_width_um=float(d.get("exit_width_um", 0)),
            exit_depth_um=float(d.get("exit_depth_um", 0)),
            pitch_um=float(d.get("pitch_um", 0)),
            upstream_width_um=float(d.get("upstream_width_um", 0)),
            rung_length_mm=float(d.get("rung_length_mm", 4.0)),
            label=str(d.get("label", "") or ""),
        )
        for d in payload.get("designs", []) or []
    ]
    fluids = [
        FormFluid(
            mu_dispersed=float(f.get("mu_dispersed", 0)),
            mu_continuous=float(f.get("mu_continuous", 0)),
            phase_system=str(f.get("phase_system", "o/w")),
            gamma=(None if f.get("gamma") in (None, "")
                   else float(f["gamma"])),
        )
        for f in payload.get("fluids", []) or []
    ]
    raw_axes = payload.get("axes", {}) or {}
    axes = FormAxes(
        Po_mbar=[float(p) for p in raw_axes.get("Po_mbar", []) or []],
        main_length_mm=[float(m) for m in raw_axes.get("main_length_mm", []) or []],
        Qw_mlhr=(None if raw_axes.get("Qw_mlhr") in (None, "")
                 else float(raw_axes["Qw_mlhr"])),
        target_emulsion_pct=(None if raw_axes.get("target_emulsion_pct") in (None, "")
                             else float(raw_axes["target_emulsion_pct"])),
    )
    base = form_from_defaults()
    return StudyForm(
        title=str(payload.get("title") or "Untitled study"),
        designs=designs,
        fluids=fluids,
        axes=axes,
        main_depth_um=float(payload.get("main_depth_um", base.main_depth_um)),
        main_width_um=float(payload.get("main_width_um", base.main_width_um)),
        footprint=base.footprint,
        manufacturing=base.manufacturing,
        scoring=base.scoring,
    )
