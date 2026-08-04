"""
stepgen.studio.workbook
======================
Render a scored :class:`StudyResult` into one **self-contained HTML chapter**
(the "book" is a directory of such chapters).

A chapter has:
  * a decision panel — per-axis winners, the Pareto set, the all-round and
    safest picks, and the weights they rest on;
  * a diagnosis panel when the study is not simply feasible — which gate is
    binding, and what relaxing each active constraint would buy;
  * an overview scored table — traffic-light cells (worst-category-wins) with
    reason chips, sortable, click a row to drill into its params + raw metrics;
  * standard plots (base64 PNG), each with a plain-English "what this means IRL"
    caption, and a best-3 toggle on the tradeoff scatter;
  * a constants / provenance panel (git hash, verbatim config, resolved values).

It also emits ``<chapter>.json`` (the scored rows) so other chapters and the
book index can cross-reference this study's devices.

Everything is inlined (CSS, a little vanilla JS, base64 images) — no external
requests, no build step.
"""

from __future__ import annotations

import base64
import html
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from stepgen.studio.diagnosis import Diagnosis, diagnose
from stepgen.studio.grouping import (
    Axis, Grouping, build_grouping, format_axis_value, row_axis_values,
)
from stepgen.studio.ranking import (
    Decision, ValueAxis, axis_value, decide, decide_subset,
)
from stepgen.studio.run import StudyResult, resolved_constants
from stepgen.studio.scoring import ScoredRow, score_result

_CAT_COLOR = {"green": "#1a7f37", "orange": "#bf8700", "red": "#cf222e", "grey": "#8b949e"}
_CONF_LABEL = {
    "validated": ("validated", "#1a7f37", "compared against experiment"),
    "calibrated": ("calibrated", "#bf8700", "empirical fit, evaluated in range"),
    "extrapolation": ("extrapolated", "#cf222e", "model not checked in this regime"),
}

# columns shown in the overview table: (metric key, header, format spec)
#
# The format spec is not decoration.  A table that prints 12.6666666 next to
# 0.000513 in the same column of a 350-row sweep cannot be read at a glance, and
# a number nobody reads is a number nobody checks.  Percentages and mL/hr get one
# decimal, counts get thousands separators, and only the genuinely small-scale
# quantities (Ca, stage times) keep significant-figure formatting.
_COLUMNS: list[tuple[str, str, str]] = [
    ("throughput_mlhr", "Throughput (mL/hr)", "f1"),
    ("N_dfu", "N DFU", "int"),
    ("droplet_um", "Droplet (µm)", "f1"),
    ("frequency_hz", "Freq (Hz)", "freq"),
    ("uniformity_pct", "ΔP flatness (%)", "f1"),
    ("operating_Po_mbar", "Po (mbar)", "int"),
    # Qw and the emulsion fraction it produces: both are *inputs* when
    # operating.Qw_mlhr is given and *solved outputs* when
    # operating.target_emulsion_pct is, so they have to be visible either way —
    # a derived operating point that never appears in the table is one nobody
    # can audit.
    ("Qw_mlhr", "Qw (mL/hr)", "f1"),
    ("emulsion_pct", "Emulsion (%)", "f1"),
    ("dP_rung_mbar", "ΔP rung (mbar)", "f1"),
    ("t_stage1_s", "t Stage-1 (s)", "g3"),
    ("t_cycle_s", "t cycle (s)", "g3"),
    ("regime_Ca", "Exit Ca", "ca"),
    ("hub_budget_pct", "Hub ΔP (%)", "f1"),
    ("area_used_cm2", "Area (cm²)", "f1"),
]

_FMT_BY_KEY = {key: spec for key, _, spec in _COLUMNS}

#: swept-axis path -> the metric column it makes redundant.  When the study
#: *sets* Po, the solved ``operating_Po_mbar`` is the same number twice; when the
#: study sets a target emulsion fraction instead, ``Qw_mlhr`` is solved and has
#: to stay.  Only an axis that is literally the input is dropped.
_AXIS_DUPLICATES = {
    "operating.Po_mbar": "operating_Po_mbar",
    "operating.Qw_mlhr": "Qw_mlhr",
}


def fmt_metric(value: Any, spec: str = "g3") -> str:
    """
    Render one metric under *spec*.

    ``f1`` one decimal · ``int`` thousands-separated whole number · ``freq``
    whole numbers once past 100 Hz · ``ca`` four decimals (exit Ca spans
    0.0003–0.7 and the leading zeros are the information) · ``g3`` three
    significant figures for quantities that cross orders of magnitude.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if f != f:
        return "—"
    if spec == "f1":
        return f"{f:,.1f}"
    if spec == "int":
        return f"{f:,.0f}"
    if spec == "freq":
        return f"{f:,.0f}" if abs(f) >= 100 else f"{f:,.1f}"
    if spec == "ca":
        return f"{f:.4f}" if abs(f) < 1 else f"{f:,.2f}"
    if spec == "pct0":
        return f"{f * 100:.0f}%"
    return f"{f:.3g}"


# ---------------------------------------------------------------------------
# Ranking / best-3
# ---------------------------------------------------------------------------

def _best_indices(
    scored: list[ScoredRow],
    goal: str = "",
    n: int = 3,
    spec: dict[str, Any] | None = None,
) -> list[int]:
    """
    The highlight set for plots: top *n* by the decide layer's composite.

    Signature kept from the single-goal era so existing callers keep working;
    ``goal`` is now a one-axis shorthand handled inside ``ranking.resolve_axes``.
    """
    from stepgen.studio.ranking import best_indices

    return best_indices(scored, spec, goal, n)


# ---------------------------------------------------------------------------
# Plots -> base64 data URIs
# ---------------------------------------------------------------------------

def _fig_to_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# reference-series marker styling by kind
_REF_STYLE = {
    "modelled":     dict(marker="X", s=130, c="#0d1117", edgecolors="white", linewidths=1.2),
    "experimental": dict(marker="D", s=60,  c="none",    edgecolors="#8250df", linewidths=1.6),
    "chapter":      dict(marker="s", s=70,  c="none",    edgecolors="#0969da", linewidths=1.6),
}


def _draw_refs(ax, refs, xattr, yattr) -> bool:
    """Overlay each reference series' points where both x and y are known."""
    drew = False
    seen: set[str] = set()
    for rs in refs or []:
        if rs.error:
            continue
        style = dict(_REF_STYLE.get(rs.kind, _REF_STYLE["chapter"]))
        for p in rs.points:
            x = getattr(p, xattr, None)
            y = getattr(p, yattr, None)
            if x is None or y is None:
                continue
            lbl = rs.label if rs.label not in seen else None
            seen.add(rs.label)
            ax.scatter(x, y, zorder=5, label=lbl, **style)
            drew = True
    return drew


def _scatter(scored, xattr, yattr, xlabel, ylabel, title, highlight=None, refs=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    highlight = set(highlight or [])
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    plotted = False
    for i, sr in enumerate(scored):
        x = getattr(sr.metrics, xattr, None)
        y = getattr(sr.metrics, yattr, None)
        if x is None or y is None:
            continue
        plotted = True
        ax.scatter(x, y, s=90 if i in highlight else 45,
                   c=_CAT_COLOR.get(sr.overall, "#8b949e"),
                   edgecolors="#0d1117" if i in highlight else "none",
                   linewidths=1.6 if i in highlight else 0, zorder=3 if i in highlight else 2)
        if i in highlight:
            ax.annotate(sr.metrics.label, (x, y), fontsize=7,
                        xytext=(4, 4), textcoords="offset points")
    drew_refs = _draw_refs(ax, refs, xattr, yattr)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.25)
    if drew_refs:
        ax.legend(fontsize=7.5, framealpha=0.85, loc="best")
    if not plotted and not drew_refs:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
    return _fig_to_uri(fig)


def _variant_plot(scored, goal, refs, *, xattr, yattr, xlabel, ylabel, title,
                  caption, with_best=False):
    """
    Build one plot with (best-3, references) toggle variants.

    Returns {title, caption, has_best, has_ref, variants:{key->uri}} where key is
    one of base / best / ref / bestref (only the reachable ones are rendered).
    """
    best = _best_indices(scored, goal) if with_best else []
    has_ref = any((not rs.error) and _series_hits(rs, xattr, yattr) for rs in (refs or []))

    variants: dict[str, str] = {
        "base": _scatter(scored, xattr, yattr, xlabel, ylabel, title),
    }
    if with_best:
        variants["best"] = _scatter(scored, xattr, yattr, xlabel, ylabel,
                                     title + " — best 3", highlight=best)
    if has_ref:
        variants["ref"] = _scatter(scored, xattr, yattr, xlabel, ylabel,
                                    title, refs=refs)
        if with_best:
            variants["bestref"] = _scatter(scored, xattr, yattr, xlabel, ylabel,
                                           title + " — best 3", highlight=best, refs=refs)
    return {"title": title, "caption": caption, "variants": variants,
            "has_best": with_best, "has_ref": has_ref}


def _series_hits(rs, xattr, yattr) -> bool:
    return any(getattr(p, xattr, None) is not None and getattr(p, yattr, None) is not None
               for p in rs.points)


def _build_plots(scored: list[ScoredRow], goal: str, refs=None) -> list[dict[str, Any]]:
    """Return the standard plot set, each with toggle variants + references."""
    refs = refs or []
    return [
        _variant_plot(
            scored, goal, refs,
            xattr="throughput_mlhr", yattr="uniformity_pct",
            xlabel="Throughput (mL/hr)", ylabel="ΔP flatness (%) — lower is flatter",
            title="Throughput vs flatness tradeoff",
            caption=("IRL: down-left is a flat, gentle device (every DFU works, but "
                     "modest output); up-right pushes more oil but starves the far rungs. "
                     "The green points pass every gate. Radial rows have automatic flatness "
                     "(N-A) so they do not appear on this axis."),
            with_best=True,
        ),
        _variant_plot(
            scored, goal, refs,
            xattr="operating_Po_mbar", yattr="throughput_mlhr",
            xlabel="Drive pressure Po (mbar)", ylabel="Throughput (mL/hr)",
            title="Throughput vs drive pressure",
            caption=("IRL: how hard you have to push to get the flow you want. "
                     "Cheaper, more robust devices sit to the left."),
            with_best=True,
        ),
        _variant_plot(
            scored, goal, refs,
            xattr="N_dfu", yattr="throughput_mlhr",
            xlabel="N DFU", ylabel="Throughput (mL/hr)",
            title="Throughput vs DFU count",
            caption=("IRL: more parallel DFUs generally means more oil — until the far "
                     "ones starve or reverse and extra DFUs stop paying their way."),
            with_best=True,
        ),
        _variant_plot(
            scored, goal, refs,
            xattr="operating_Po_mbar", yattr="droplet_um",
            xlabel="Drive pressure Po (mbar)", ylabel="Droplet diameter (µm)",
            title="Droplet size vs drive pressure",
            caption=("IRL: the size you actually make vs how hard you drive. Click-in "
                     "experimental / modelled references overlay here — the model line is "
                     "regime-blind, so treat wide gaps to experiment as a size-model caveat."),
            with_best=False,
        ),
    ]


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value != value:  # NaN
            return "—"
        return f"{value:.3g}"
    return html.escape(str(value))


def _light(cat: str) -> str:
    return (f'<span class="dot" style="background:{_CAT_COLOR.get(cat, "#8b949e")}" '
            f'title="{cat}"></span>')


# ---------------------------------------------------------------------------
# Decision panel
# ---------------------------------------------------------------------------

def _pick_card(title: str, sub: str, row: ScoredRow | None, extra: str = "") -> str:
    if row is None:
        return (f'<div class="pick"><h4>{html.escape(title)}</h4>'
                f'<div class="picksub">{html.escape(sub)}</div>'
                f'<div class="pickname">—</div>'
                f'<div class="pickwhy">no row can be compared on this</div></div>')
    return (f'<div class="pick"><h4>{html.escape(title)}</h4>'
            f'<div class="picksub">{html.escape(sub)}</div>'
            f'<div class="pickname">{_light(row.overall)}'
            f'{html.escape(row.metrics.label)}</div>'
            f'<div class="pickwhy">{extra}</div></div>')


def _axis_cell(row: ScoredRow, axis: ValueAxis) -> str:
    value = axis_value(row, axis)
    if value is None:
        return "—"
    if axis.key == "margin":
        return f"{value * 100:.0f}%"
    return f"{fmt_metric(value, _FMT_BY_KEY.get(axis.source, 'g3'))}{axis.unit}"


def _decision_html(scored: list[ScoredRow], dec: Decision) -> str:
    """
    The decide layer, rendered above the table.

    Per-axis winners come first and always appear: that the flattest design is a
    different device from the highest-throughput one *is* the finding, and a
    composite that hid it would be worse than no composite (PRD §5).
    """
    if not scored:
        return ""

    # ── per-axis winners ────────────────────────────────────────────────────
    cards = []
    for axis in dec.axes:
        i = dec.per_axis.get(axis.key)
        row = scored[i] if i is not None else None
        detail = _axis_cell(row, axis) if row is not None else ""
        # never .lower() the label — it would turn "ΔP spread" into "δp spread"
        cards.append(_pick_card(f"Best: {axis.label}", "per-axis winner",
                                row, html.escape(detail)))
    axis_cards = f'<div class="picks">{"".join(cards)}</div>'

    # ── all-round + safest ──────────────────────────────────────────────────
    wtxt = ", ".join(f"{k} {v:.2f}" for k, v in dec.weights.items())
    all_round_row = scored[dec.all_round] if dec.all_round is not None else None
    all_round_why = (f"composite {dec.composite.get(dec.all_round, 0):.3f} "
                     f"&mdash; weights: {html.escape(wtxt)}"
                     if all_round_row is not None else "")

    safest_row = scored[dec.safest] if dec.safest is not None else None
    safest_why = ""
    if safest_row is not None:
        m = safest_row.min_margin_discounted
        weak = safest_row.weakest_metric or "—"
        safest_why = (f"discounted margin {m * 100:.0f}% "
                      f"&mdash; weakest link: {html.escape(weak)}")

    summary_cards = (
        '<div class="picks">'
        + _pick_card("All-round", "weighted composite", all_round_row, all_round_why)
        + _pick_card("Safest to build first", "confidence-discounted margin",
                     safest_row, safest_why)
        + '</div>'
    )

    # ── Pareto ──────────────────────────────────────────────────────────────
    if dec.pareto:
        head = "".join(f"<th>{html.escape(a.label)}</th>" for a in dec.axes)
        body = "".join(
            "<tr><td><b>" + html.escape(scored[i].metrics.label) + "</b></td>"
            + "".join(f"<td>{_axis_cell(scored[i], a)}</td>" for a in dec.axes)
            + "</tr>"
            for i in dec.pareto
        )
        pareto_html = (
            f'<h3>Pareto set — {len(dec.pareto)} design'
            f'{"s" if len(dec.pareto) != 1 else ""} not beaten on everything</h3>'
            f'<table class="pareto"><thead><tr><th>Config</th>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table>'
        )
    else:
        pareto_html = ('<h3>Pareto set</h3><p class="muted">No design can be '
                       'compared across all declared axes — some axis is N-A for '
                       'every row.</p>')

    # Rows that cannot be placed on every axis are left out rather than given a
    # substituted value (DR-4). Say so — a silently short Pareto set is worse
    # than a stated exclusion.
    incomparable = [i for i in dec.candidates if i not in set(dec.pareto)
                    and any(axis_value(scored[i], a) is None for a in dec.axes)]
    if incomparable:
        missing = sorted({a.label for i in incomparable for a in dec.axes
                          if axis_value(scored[i], a) is None})
        names = ", ".join(html.escape(scored[i].metrics.label) for i in incomparable[:6])
        more = f" (+{len(incomparable) - 6} more)" if len(incomparable) > 6 else ""
        pareto_html += (
            f'<p class="muted">{len(incomparable)} design'
            f'{"s" if len(incomparable) != 1 else ""} could not be placed on the '
            f'Pareto front — N-A on {html.escape(", ".join(missing))}: '
            f'{names}{more}. They are compared on the axes they do have, but a '
            f'design that cannot be measured on an axis cannot be called '
            f'non-dominated across all of them.</p>'
        )

    # ── honesty notes ───────────────────────────────────────────────────────
    notes: list[str] = []
    if dec.all_red:
        notes.append("<b>Every design scored red.</b> Picks below are the least-bad "
                     "of an unbuildable set, not recommendations.")
    elif len(dec.candidates) < len(scored):
        n_ex = len(scored) - len(dec.candidates)
        notes.append(f"{n_ex} red row{'s' if n_ex != 1 else ''} excluded from "
                     f"selection — a winner should be buildable.")
    if dec.is_conflicted():
        notes.append("The axes disagree: no single design wins on everything. "
                     "The Pareto set is the honest answer here.")

    # verdicts resting on extrapolated numbers
    flagged = []
    for name, i in (("all-round", dec.all_round), ("safest", dec.safest)):
        if i is None:
            continue
        keys = [k for k in scored[i].extrapolated_keys if k != "validity"]
        if keys:
            flagged.append(f"the <b>{name}</b> pick rests on extrapolated "
                           f"{html.escape(', '.join(keys))}")
    if flagged:
        notes.append("⚠ " + "; ".join(flagged)
                     + " — the model has not been checked in that regime.")

    # Breaches shared by every row are a property of the study — the fluid
    # system's viscosity ratio, say — not a way to tell designs apart. Stating
    # them once keeps them honest without making every row orange for the same
    # reason and drowning the breaches that actually discriminate.
    for c in dec.caveats:
        notes.append("⚠ <b>Applies to every design in this study:</b> "
                     + html.escape(c))

    notes_html = ("".join(f'<li>{n}</li>' for n in notes))
    notes_html = f'<ul class="decnotes">{notes_html}</ul>' if notes else ""

    return (
        '<section class="decision">'
        '<h2>Decision</h2>'
        f'{axis_cards}{summary_cards}{pareto_html}{notes_html}'
        '</section>'
    )


# ---------------------------------------------------------------------------
# Diagnosis panel
# ---------------------------------------------------------------------------

def _intent_html(study) -> str:
    """What the user asked for, when they asked for a target instead of a grid."""
    plan = study.intent_plan
    if plan is None:
        return ""
    s = plan.summary()
    facts = [
        ("Droplet target", f"{s['droplet_um']:g} µm"),
        ("Throughput target", f"{s['throughput_mlhr']:g} mL/hr"),
        ("Pressure ceiling", f"{s['max_Po_mbar']:g} mbar"),
        ("Fab preset", f"{s['fab']} — depth ≤ {s['max_main_depth_um']:g} µm, "
                       f"width ≤ {s['max_main_width_um']:g} µm, "
                       f"min wall {s['min_wall_um']:g} µm"),
        ("Die square", f"{s['square_side_mm']:g} mm"),
        ("Explored", ", ".join(s["explore"])),
    ]
    rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>"
                   for k, v in facts)

    gen = ", ".join(s["generated_blocks"]) or "none"
    user = ", ".join(s["user_supplied_blocks"]) or "none"
    notes = (f'<p class="muted">Blocks generated from this intent: '
             f'<b>{html.escape(gen)}</b>. Written by hand and left untouched: '
             f'<b>{html.escape(user)}</b>.</p>')
    if s["skipped_families"]:
        skipped = "; ".join(f"{k}: {v}" for k, v in s["skipped_families"].items())
        notes += (f'<p class="muted">⚠ Families skipped — no geometry was '
                  f'invented on their behalf: {html.escape(skipped)}</p>')

    return (
        '<section class="decision">'
        '<h2>Intent</h2>'
        '<p class="muted">This study was generated from a target, not written as '
        'a grid. The junction exit is derived from the droplet target through the '
        'shared inverse solve, so every family below is answering the same '
        'question with the same exit.</p>'
        f'<table class="pareto"><tbody>{rows}</tbody></table>{notes}'
        '</section>'
    )


def _diagnosis_html(diag: Diagnosis | None) -> str:
    """
    Why the study came back the way it did — rendered only when it is a finding.

    A study where most designs are green does not need this panel: the question
    there is which one to pick, and the decision panel above already answers it.
    """
    if diag is None or diag.n_rows == 0:
        return ""
    if diag.n_green and not diag.prices and not diag.theory_limited:
        return ""

    head = f'<p class="dhead">{html.escape(diag.headline())}</p>'

    # ── buildable, blocked only by our weakest theory ───────────────────────
    # These rows deserve to be named, not buried in a red table. Every gate
    # resting on something measurable passes; the only objection comes from a
    # threshold no Peak device has been within an order of magnitude of.
    if diag.theory_limited:
        lo, hi = diag.gamma_range[0] * 1e3, diag.gamma_range[1] * 1e3
        head += (
            '<h3>Build-and-see candidates — green on everything except exit Ca</h3>'
            '<p class="muted">These pass every gate that rests on geometry, '
            'fabrication limits or hydraulics. The only thing standing against '
            'them is the step-emulsification ceiling, which is borrowed from '
            'literature at λ ≈ 1 while we run at λ ≈ 0.015, and which no Peak '
            'device has operated within 7× of. The verdict stays red — an '
            'unmeasured risk must not be quietly downgraded — but whether these '
            'work is a question the model cannot settle.</p>'
        )

        # γ has never been measured, so Ca is a verdict resting on a guess.
        # Split by whether the verdict survives the plausible band.
        if diag.gamma_dependent_ca or diag.robustly_red_ca:
            head += (
                f'<p class="muted">Exit Ca scales as 1/γ, and the interfacial '
                f'tension of this fluid system has never been measured — the '
                f'configs in this repo variously assume 5, 15 and 0 mN/m. Each '
                f'Ca verdict below is therefore re-evaluated across a plausible '
                f'band of <b>{lo:g}–{hi:g} mN/m</b>. That costs nothing: γ enters '
                f'the model only in this diagnostic and never in the flow solve, '
                f'so the whole band follows analytically from the one solved '
                f'value.</p>'
            )
            if diag.gamma_dependent_labels:
                items = "".join(
                    f"<li><code>{html.escape(lbl)}</code></li>"
                    for lbl in diag.gamma_dependent_labels[:12])
                more = (f'<li class="muted">…and '
                        f'{len(diag.gamma_dependent_labels) - 12} more</li>'
                        if len(diag.gamma_dependent_labels) > 12 else "")
                head += (
                    f'<h4>Red only at part of the γ band — the real shortlist '
                    f'({len(diag.gamma_dependent_labels)})</h4>'
                    f'<p class="muted">Ordered by how little γ it takes to clear, '
                    f'best first. These are red because of a constant nobody has '
                    f'measured, not because of anything about the design.</p>'
                    f'<ul class="candidates">{items}{more}</ul>'
                )
            if diag.robustly_red_ca:
                head += (
                    f'<h4>Red at every plausible γ ({len(diag.robustly_red_ca)})'
                    f'</h4><p class="muted">These stay above the ceiling even at '
                    f'{hi:g} mN/m. Their Ca verdict survives our ignorance about '
                    f'γ, so believe it — they are genuinely out of regime.</p>'
                )
        else:
            items = "".join(
                f"<li><code>{html.escape(lbl)}</code></li>"
                for lbl in diag.theory_limited_labels[:12])
            more = (f'<li class="muted">…and '
                    f'{len(diag.theory_limited_labels) - 12} more</li>'
                    if len(diag.theory_limited_labels) > 12 else "")
            head += f'<ul class="candidates">{items}{more}</ul>'

    # ── which gate is in the way ────────────────────────────────────────────
    shown = [f for f in diag.failures if f.n_red or f.n_sole_cause][:8]
    if shown:
        body = "".join(
            f"<tr><td><b>{html.escape(f.label)}</b></td>"
            f"<td>{f.n_sole_cause}</td><td>{f.n_red}</td><td>{f.n_non_green}</td>"
            f"<td>{'physics — no process knob' if not _knobs_for(f.key) else html.escape(', '.join(_knobs_for(f.key)))}</td></tr>"
            for f in shown
        )
        gates_html = (
            '<h3>What is in the way</h3>'
            '<table class="pareto"><thead><tr><th>Gate</th><th>Sole cause of red</th>'
            '<th>Red</th><th>Non-green</th><th>Relaxable by</th></tr></thead>'
            f'<tbody>{body}</tbody></table>'
            '<p class="muted">“Sole cause” counts the rows where this gate is the '
            '<i>only</i> red one — relaxing it alone would change those verdicts. '
            'A gate that reds many rows but is never the sole cause is a symptom, '
            'not the constraint.</p>'
        )
    else:
        gates_html = ""

    # ── what relaxing would buy ─────────────────────────────────────────────
    if diag.prices:
        rows = []
        for p in diag.prices:
            if p.error:
                delta = f'<td colspan="2">{html.escape(p.error)}</td>'
            else:
                sign = "+" if p.greens_gained >= 0 else ""
                delta = (f'<td>{p.red_before} → {p.red_after} '
                         f'({-p.reds_cleared:+d})</td>'
                         f'<td>{p.green_before} → {p.green_after} '
                         f'({sign}{p.greens_gained})</td>')
            rows.append(
                f'<tr><td><b>{html.escape(p.label)}</b></td>'
                f'<td>{p.before:g} → {p.after:g} {html.escape(p.unit)}</td>{delta}</tr>'
            )
        prices_html = (
            '<h3>What relaxing each constraint would buy</h3>'
            '<table class="pareto"><thead><tr><th>Constraint</th><th>One notch</th>'
            '<th>Red</th><th>Green</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            '<p class="muted">Each row is a full re-run of the study with that one '
            'constraint stepped. For an intent study the whole grid is regenerated '
            'from the relaxed constraint, so a deeper permitted etch changes the '
            'geometry that gets tried — not merely the gate that judges it. This is '
            'what a process decision costs, in designs.</p>'
        )
    elif diag.priced:
        prices_html = ('<h3>What relaxing each constraint would buy</h3>'
                       '<p class="muted">No constraint in this study owns a gate '
                       'that is failing — there was nothing to price.</p>')
    else:
        prices_html = ""

    return (f'<section class="decision diagnosis"><h2>Diagnosis</h2>'
            f'{head}{gates_html}{prices_html}</section>')


def _knobs_for(gate: str) -> list[str]:
    from stepgen.studio.diagnosis import knobs_for_gate
    return [k.label for k in knobs_for_gate(gate)]


def _margin_cell(sr: ScoredRow) -> str:
    """Weakest-link margin, with the metric that sets it and its trust tier."""
    m = sr.min_margin_discounted
    if m is None:
        return '<td data-v="-1e18">—</td>'
    raw = sr.min_margin or 0.0
    weak = sr.weakest_metric or ""
    cell = sr.cells.get(weak)
    tier = cell.confidence if cell else "validated"
    label, colour, tip = _CONF_LABEL.get(tier, _CONF_LABEL["validated"])
    # marginal = under a fifth of the green->red span left
    style = ' style="color:#cf222e;font-weight:600"' if m < 0.2 else ""
    return (f'<td data-v="{m}"{style} title="raw margin {raw*100:.0f}%, '
            f'discounted to {m*100:.0f}% because {html.escape(weak)} is '
            f'{html.escape(label)} ({html.escape(tip)})">'
            f'{m*100:.0f}% <span class="tier" style="color:{colour}">'
            f'{html.escape(weak)}&nbsp;·&nbsp;{html.escape(label)}</span></td>')


#: Maximum drill-down rows that carry an embedded schematic.
#: Each drawing pair costs ~28 KB of inline SVG, so a 216-point intent study
#: would add ~6 MB to a chapter that is otherwise ~750 KB.  The starred (best)
#: rows are always drawn; the rest fill the remaining budget in table order, and
#: any row that misses out says so rather than silently showing nothing.
MAX_SCHEMATIC_ROWS = 60


def _schematic_rows(scored: list[ScoredRow], best: set[int]) -> set[int]:
    """Which row indices get an embedded drawing — best first, then in order."""
    chosen = set(i for i in best if i < len(scored))
    for i in range(len(scored)):
        if len(chosen) >= MAX_SCHEMATIC_ROWS:
            break
        chosen.add(i)
    return chosen


def _panzoom_js() -> str:
    """One copy of the schematic pan/zoom initialiser for the whole chapter."""
    from stepgen.viz.schematic import panzoom_js
    return panzoom_js()


def _schematic_omitted(drawable: bool) -> str:
    """Say why a row has no drawing, rather than leaving a silent gap."""
    if not drawable:
        return ""
    return (
        f'<div style="grid-column:1/-1"><h4>Layout — to scale</h4>'
        f'<p class="muted">Omitted to bound chapter size — only the best rows and '
        f'the first {MAX_SCHEMATIC_ROWS} are drawn. Open this study in '
        f'<code>stepgen studio-ui</code> to see any point drawn live.</p></div>'
    )


def _schematic_html(sr: ScoredRow, study) -> str:
    """
    To-scale device + zoom drawings for one row's drill-down.

    Compiles the matching :class:`StudyPoint` — the same object the solver used
    — and draws it.  Returns ``""`` when the point cannot be found or the family
    declines to draw, so a chapter never fails over a picture.
    """
    if study is None:
        return ""
    point = next((p for p in getattr(study, "points", []) if p.label == sr.metrics.label),
                 None)
    if point is None:
        return ""
    try:
        from stepgen.families import get_family
        from stepgen.viz.schematic import schematic_block

        family = get_family(point.family)
        compiled = family.compile(
            point.params, fluids=point.fluids, footprint=point.footprint,
            manufacturing=point.manufacturing,
        )
        cap = family.packing_capacity(compiled)
        blocks = "".join(
            f'<div style="flex:1;min-width:330px">'
            f'{schematic_block(family.render_schematic(compiled, v), width_px=430, uid=f"sch-{v}-{id(sr)}")}'
            f'</div>'
            for v in ("device", "zoom")
        )
    except Exception as exc:                      # never break a chapter over a drawing
        return f'<div><h4>Layout</h4><p class="muted">no schematic: {html.escape(str(exc))}</p></div>'

    cap_html = ""
    if cap:
        more = cap.n_max - cap.n_current
        cap_html = (
            f'<p class="muted" style="margin:2px 0 8px">'
            f'{cap.n_current:,} DFUs configured &middot; this footprint holds '
            f'{cap.n_max:,} ({cap.utilisation:.0%} used) &middot; limited by '
            f'{html.escape(cap.limited_by)}'
            + (f' &middot; room for {more:,} more' if more > 0 else "")
            + '</p>'
        )
    return (f'<div style="grid-column:1/-1"><h4>Layout — to scale</h4>{cap_html}'
            f'<div style="display:flex;gap:18px;flex-wrap:wrap">{blocks}</div></div>')


# ---------------------------------------------------------------------------
# Designs vs conditions
# ---------------------------------------------------------------------------

def _conditions_text(
    values: dict[str, Any],
    axes: Sequence[Axis],
    row: ScoredRow | None = None,
) -> str:
    """
    ``Main length 160 mm · Po 1000 mbar · N 1,333 DFUs`` — how a row was run.

    N is appended rather than being an axis of its own because nobody sets it:
    it falls out of main length ÷ pitch, so the same length means a different
    ladder on every design in this study.  Naming the length without the count
    it bought makes the winner cards unreadable — 40 mm is 333 DFUs on a 120 µm
    pitch and 133 on a 300 µm one, and that is the whole comparison.
    """
    bits = [f"{a.label} {a.show(values.get(a.path))}" for a in axes]
    n = getattr(row.metrics, "N_dfu", None) if row is not None else None
    if n is not None:
        bits.append(f"N {int(n):,} DFUs")
    return " · ".join(bits)


def _axis_values_text(axis: Axis) -> str:
    """``Main length: 20, 40, 80, 160 mm`` / ``Po: 25 … 1,000 mbar (11 values)``."""
    shown = [format_axis_value(v, axis.spec) for v in axis.values]
    if len(shown) <= 6:
        return f"{axis.label}: {', '.join(shown)} {axis.unit}".strip()
    span = f"{shown[0]} … {shown[-1]} {axis.unit}".strip()
    return f"{axis.label}: {span} ({len(shown)} values)"


def _n_range(scored: Sequence[ScoredRow], indices: Sequence[int]) -> str:
    """``N 166 → 1,333 DFUs`` across a design's conditions, or "" if fixed/N-A."""
    counts = sorted({int(scored[i].metrics.N_dfu) for i in indices
                     if scored[i].metrics.N_dfu is not None})
    if not counts:
        return ""
    if len(counts) == 1:
        return f"N {counts[0]:,} DFUs"
    return f"N {counts[0]:,} → {counts[-1]:,} DFUs"


def _counts(scored: Sequence[ScoredRow], indices: Sequence[int]) -> tuple[int, int, int]:
    cats = [scored[i].overall for i in indices]
    return (cats.count("green"), cats.count("orange"), cats.count("red"))


def _verdict_bar(scored: Sequence[ScoredRow], indices: Sequence[int]) -> str:
    g, o, r = _counts(scored, indices)
    return (f'<span class="vbar">{_light("green")}{g} {_light("orange")}{o} '
            f'{_light("red")}{r}</span>')


def _pick_card_for(
    axis: ValueAxis,
    index: int | None,
    scored: Sequence[ScoredRow],
    leaves: dict[int, dict[str, Any]],
    cond_axes: Sequence[Axis],
) -> str:
    """A per-axis winner card that also says *at what operating point* it won."""
    if index is None:
        return _pick_card(f"Best {axis.label}", "no comparable row", None)
    row = scored[index]
    value = _axis_cell(row, axis)
    where = html.escape(_conditions_text(leaves.get(index, {}), cond_axes, row))
    return (f'<div class="pick"><h4>Best {html.escape(axis.label)}</h4>'
            f'<div class="pickval">{_light(row.overall)}{value}</div>'
            f'<div class="pickwhy">at {where}</div>'
            f'<div class="picksub" title="{html.escape(row.metrics.label)}">'
            f'row #{index + 1}</div></div>')


def _lever_cell(step, key: str) -> str:
    """One measured effect, coloured by whether it helped or hurt."""
    eff = step.effect_on(key)
    if eff is None:
        return '<td class="num muted">—</td>'
    text = eff.amount()
    if eff.delta == 0:
        return '<td class="num muted" title="unchanged">·</td>'
    colour = {"better": _CAT_COLOR["green"],
              "worse": _CAT_COLOR["red"]}.get(eff.direction, "")
    style = f' style="color:{colour}"' if colour else ""
    tip = f"median absolute change {eff.delta:+,.4g} over {eff.n} pairs"
    return f'<td class="num"{style} title="{html.escape(tip)}">{text}</td>'


def _levers_table(steps: Sequence[Any], watches: Sequence[Any], title: str) -> str:
    if not steps:
        return ""
    head = "".join(f"<th>{html.escape(w.label)}</th>" for w in watches)
    body = "".join(
        f'<tr><td class="lev">{html.escape(s.label)}</td>'
        f'<td class="num muted">{s.n_pairs}</td>'
        + "".join(_lever_cell(s, w.key) for w in watches) + "</tr>"
        for s in steps
    )
    return (f'<table class="pareto levers"><thead><tr><th>{html.escape(title)}</th>'
            f'<th title="matched row pairs behind the median">pairs</th>{head}</tr>'
            f'</thead><tbody>{body}</tbody></table>')


def _advice_html(
    dec_axes: Sequence[ValueAxis],
    spans: Sequence[Any],
    swept_paths: Sequence[str],
    scored: Sequence[ScoredRow] = (),
) -> str:
    """
    "To push this further, do X — and here is what X costs you."

    Measured first (the study's own numbers, from matched pairs), then the knobs
    the study did not sweep, which come from the model's scaling structure and
    the ingested literature and are labelled as such.
    """
    from stepgen.studio.levers import (
        OBJECTIVE_METRIC, best_step_for, structural_levers,
    )

    cards: list[str] = []
    for axis in dec_axes:
        metric = OBJECTIVE_METRIC.get(axis.key)
        bits: list[str] = []

        step = best_step_for(spans, metric, scored) if metric else None
        if step is not None:
            gain = step.effect_on(metric)
            costs = [e for k, e in step.effects.items()
                     if k != metric and e.direction == "worse" and e.delta != 0
                     and (e.rel is None or abs(e.rel) > 0.02)]
            cost_txt = ("costs " + ", ".join(e.text() for e in costs)
                        if costs else "no watched metric got worse")
            bits.append(
                f'<li><span class="tag measured">measured here</span> '
                f'<b>{html.escape(step.label)}</b> → {html.escape(gain.text())} '
                f'<span class="muted">(median of {step.n_pairs} matched pairs)</span>'
                f'<div class="cost">{html.escape(cost_txt)}</div></li>'
            )

        for lever in structural_levers(axis.key, swept_paths)[:3]:
            costs = "".join(f"<li>{html.escape(c)}</li>" for c in lever.costs)
            bits.append(
                f'<li><span class="tag model">not swept here</span> '
                f'<b>{html.escape(lever.headline)}</b> — {html.escape(lever.mechanism)}'
                f'<div class="cost"><b>Costs:</b><ul>{costs}</ul>'
                f'<span class="muted">{html.escape(lever.evidence)}</span></div></li>'
            )

        if not bits:
            continue
        cards.append(f'<div class="advice"><h4>To improve {html.escape(axis.label)}</h4>'
                     f'<ul>{"".join(bits)}</ul></div>')

    if not cards:
        return ""
    return ('<h3>How to push this design further</h3>'
            '<p class="muted">Every direction carries its cost — a lever with no '
            'downside would already be the default. "Measured here" is this study\'s '
            'own matched-pair result; "not swept here" comes from the model\'s scaling '
            'and the cited literature, and has not been evaluated in this run.</p>'
            f'<div class="advicegrid">{"".join(cards)}</div>')


def _design_sections_html(
    scored: list[ScoredRow],
    grouping: Grouping,
    leaves: dict[int, dict[str, Any]],
    decisions: dict[str, Decision],
    compare_html: str = "",
) -> str:
    """One decision panel per design, each ranking that design's own conditions."""
    from stepgen.studio.levers import WATCHED, measured_levers

    if not grouping.groups:
        return ""

    swept = [a.path for a in grouping.condition_axes]
    sections: list[str] = []
    for group in grouping.groups:
        dec = decisions[group.gid]
        cards = "".join(
            _pick_card_for(axis, dec.per_axis.get(axis.key), scored, leaves,
                           grouping.condition_axes)
            for axis in dec.axes
        )

        extra = []
        if dec.all_round is not None:
            extra.append(
                f'<b>All-round</b> (weighted composite within this design): '
                f'{html.escape(_conditions_text(leaves.get(dec.all_round, {}), grouping.condition_axes, scored[dec.all_round]))} '
                f'<span class="muted">row #{dec.all_round + 1}, '
                f'{scored[dec.all_round].overall}</span>')
        if dec.safest is not None:
            m = scored[dec.safest].min_margin_discounted or 0.0
            extra.append(
                f'<b>Safest</b> (discounted margin {m * 100:.0f}%): '
                f'{html.escape(_conditions_text(leaves.get(dec.safest, {}), grouping.condition_axes, scored[dec.safest]))} '
                f'<span class="muted">row #{dec.safest + 1}</span>')
        if dec.all_red:
            extra.append('<span class="warn">Every point of this design scored red — '
                         'the picks above are least-bad, not recommendations.</span>')
        extra_html = "".join(f"<li>{e}</li>" for e in extra)

        spans = measured_levers(scored, group.indices, leaves,
                                grouping.condition_axes, mode="span")
        notches = measured_levers(scored, group.indices, leaves,
                                  grouping.condition_axes, mode="adjacent")
        watches = [w for w in WATCHED
                   if any(s.effect_on(w.key) is not None for s in spans + notches)]
        levers_html = _levers_table(spans, watches, "Lever — full range")
        if notches and len(notches) > len(spans):
            levers_html += (
                '<details class="notches"><summary>notch by notch '
                f'({len(notches)} steps)</summary>'
                + _levers_table(notches, watches, "Lever — one notch")
                + '</details>')
        if levers_html:
            levers_html = (
                '<h3>What moves this design</h3>'
                '<p class="muted">Median change over row pairs that differ on this '
                'axis and nothing else. Green helped, red hurt; ΔP flatness is in '
                'percentage points, everything else relative.</p>' + levers_html)

        n_txt = _n_range(scored, group.indices)
        sections.append(
            f'<details class="dgroup" id="grp-{group.gid}" open>'
            f'<summary><span class="gid">{group.gid}</span> '
            f'<b>{html.escape(group.label(grouping.design_axes))}</b> '
            + (f'<span class="muted">· {html.escape(n_txt)}</span> ' if n_txt else "")
            + f'<span class="muted">· {len(group.indices)} points</span> '
            f'{_verdict_bar(scored, group.indices)}</summary>'
            f'<div class="gbody">'
            f'<p><button class="btn" onclick="filterToDesign(\'{group.gid}\')">'
            f'Show only this design in the table ↓</button></p>'
            f'<div class="picks">{cards}</div>'
            f'<ul class="decnotes">{extra_html}</ul>'
            f'{levers_html}'
            f'{_advice_html(dec.axes, spans, swept, scored)}'
            f'</div></details>'
        )

    return ('<section class="decision">'
            f'<h2>Per-design decisions — {len(grouping.groups)} designs</h2>'
            '<p class="muted">Each design is ranked against <b>its own</b> operating '
            'points, so "best throughput" here means the best way to run this device '
            f'— not the biggest device. Designs are defined by: '
            f'{html.escape(", ".join(a.label for a in grouping.design_axes)) or "—"} '
            f'({html.escape(grouping.source)}).</p>'
            '<p class="muted">Explored inside each design — '
            + (html.escape(" · ".join(_axis_values_text(a)
                                      for a in grouping.condition_axes))
               or "nothing")
            + '. N DFU is not swept: it is derived as main length ÷ pitch, so the '
              'same length buys a different ladder on every design here.</p>'
            f'{compare_html}{"".join(sections)}</section>')


def _design_compare_html(
    scored: list[ScoredRow],
    grouping: Grouping,
    leaves: dict[int, dict[str, Any]],
    decisions: dict[str, Decision],
    dec_axes: Sequence[ValueAxis],
) -> str:
    """One row per design: its own best on each axis, side by side."""
    if not grouping.is_split:
        return ""
    head = ("".join(f"<th>{html.escape(a.label)}</th>" for a in grouping.design_axes)
            + '<th title="derived from main length ÷ pitch, over the swept lengths">'
              'N DFU</th>'
            # never .lower() a label — it turns "ΔP spread" into "δp spread"
            + "".join(f"<th>Best {html.escape(a.label)}</th>" for a in dec_axes))
    body = []
    for group in grouping.groups:
        dec = decisions[group.gid]
        cells = [f'<td>{html.escape(a.show(group.values.get(a.path)))}</td>'
                 for a in grouping.design_axes]
        cells.append(f'<td class="num">{html.escape(_n_range(scored, group.indices))}</td>')
        for axis in dec_axes:
            i = dec.per_axis.get(axis.key)
            if i is None:
                cells.append("<td>—</td>")
                continue
            where = _conditions_text(leaves.get(i, {}), grouping.condition_axes, scored[i])
            cells.append(f'<td title="{html.escape(where)}">{_axis_cell(scored[i], axis)}'
                         f'<span class="tier">{html.escape(where)}</span></td>')
        body.append(f'<tr><td><b>{group.gid}</b></td>{"".join(cells)}</tr>')
    return (
        '<h3>Design vs design — each at its own best</h3>'
        '<p class="muted">Every cell is that design run at whichever of its own '
        'operating points wins that column, with the point named underneath. Reading '
        'across a row shows what one device can and cannot do at once; reading down a '
        'column compares devices fairly, each at its own best.</p>'
        f'<table class="pareto compare"><thead><tr><th>Design</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


# ---------------------------------------------------------------------------
# Filter bar + overview table
# ---------------------------------------------------------------------------

def _filters_html(grouping: Grouping, axes: Sequence[Axis]) -> str:
    """Client-side filters — one control per axis that actually varies."""
    controls: list[str] = []
    if grouping.is_split:
        opts = "".join(
            f'<option value="{html.escape(g.gid)}">{html.escape(g.gid)} — '
            f'{html.escape(g.label(grouping.design_axes))}</option>'
            for g in grouping.groups)
        controls.append(
            '<label>Design<select id="f-gid" data-key="gid" onchange="applyFilters()">'
            f'<option value="">All designs</option>{opts}</select></label>')

    for j, axis in enumerate(axes):
        opts = "".join(f'<option value="{html.escape(str(v))}">'
                       f'{html.escape(axis.show(v))}</option>' for v in axis.values)
        controls.append(
            f'<label>{html.escape(axis.header())}'
            f'<select data-key="a{j}" onchange="applyFilters()">'
            f'<option value="">Any</option>{opts}</select></label>')

    controls.append(
        '<label>Verdict<select data-key="verdict" onchange="applyFilters()">'
        '<option value="">Any</option><option value="green">green</option>'
        '<option value="orange">orange</option><option value="red">red</option>'
        '</select></label>')
    controls.append(
        '<label>Search<input id="f-text" type="search" placeholder="label, reason…" '
        'oninput="applyFilters()"></label>')
    controls.append('<button class="btn" onclick="resetFilters()">Reset</button>')
    controls.append('<span id="filtercount" class="muted"></span>')
    return f'<div class="filters" id="filters">{"".join(controls)}</div>'


def _table_html(
    scored: list[ScoredRow],
    best: set[int],
    study=None,
    grouping: Grouping | None = None,
    leaves: dict[int, dict[str, Any]] | None = None,
) -> str:
    leaves = leaves or {}
    axes: list[Axis] = []
    if grouping is not None:
        axes = list(grouping.design_axes) + list(grouping.condition_axes)

    # A column of dashes is a column nobody reads: drop metrics no family in this
    # study can compute (hub ΔP in a serpentine-only run) and metrics that merely
    # repeat a swept axis already shown to their left.
    duplicated = {_AXIS_DUPLICATES[a.path] for a in axes if a.path in _AXIS_DUPLICATES}
    columns = [
        (key, header, spec) for key, header, spec in _COLUMNS
        if key not in duplicated
        and any(getattr(sr.metrics, key, None) is not None for sr in scored)
    ]

    families = sorted({sr.metrics.family for sr in scored})
    head = ["#"]
    if grouping is not None and grouping.is_split:
        head.append("Design")
    head += [a.header() for a in axes]
    if len(families) > 1:
        head.append("Family")
    head += ["Verdict"] + [c[1] for c in columns] + \
            ["Margin (weakest link)", "Build", "Valid", "Reasons"]
    thead = "".join(
        f'<th onclick="sortTable({i})">{html.escape(h)}</th>'
        for i, h in enumerate(head)
    )

    draw_rows = _schematic_rows(scored, best) if study is not None else set()

    rows_html: list[str] = []
    for i, sr in enumerate(scored):
        m = sr.metrics
        vals = leaves.get(i, {})
        gid = grouping.group_of.get(i, "") if grouping is not None else ""

        attrs = [f'data-gid="{html.escape(gid)}"',
                 f'data-verdict="{sr.overall}"',
                 f'data-txt="{html.escape((m.label + " " + " ".join(sr.chips)).lower())}"']
        for j, axis in enumerate(axes):
            attrs.append(f'data-a{j}="{html.escape(str(vals.get(axis.path)))}"')

        star = '<span class="star" title="best all-round">★</span>' if i in best else ""
        cells = [f'<td data-v="{i}">{i + 1}{star}</td>']
        if grouping is not None and grouping.is_split:
            cells.append(f'<td data-v="{html.escape(gid)}"><span class="gid">'
                         f'{html.escape(gid)}</span></td>')
        for axis in axes:
            value = vals.get(axis.path)
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            sort_v = value if numeric else html.escape(str(value))
            cells.append(f'<td class="{"num" if numeric else "axv"}" data-v="{sort_v}">'
                         f'{html.escape(format_axis_value(value, axis.spec))}</td>')
        if len(families) > 1:
            cells.append(f'<td data-v="{html.escape(m.family)}">{html.escape(m.family)}</td>')
        cells.append(
            f'<td data-v="{ {"green":0,"orange":1,"red":2}.get(sr.overall,3) }">'
            f'{_light(sr.overall)}{sr.overall}</td>')

        for key, _, spec in columns:
            value = getattr(m, key, None)
            cell = sr.cells.get(key)
            color = _CAT_COLOR.get(cell.category, "") if cell else ""
            sort_v = value if isinstance(value, (int, float)) and value == value else -1e18
            style = f' style="color:{color};font-weight:600"' if cell and cell.category in ("orange", "red") else ""
            cells.append(f'<td class="num" data-v="{sort_v}"{style}>'
                         f'{fmt_metric(value, spec)}</td>')
        cells.append(_margin_cell(sr))
        build_cell = sr.cells.get("build")
        bcat = build_cell.category if build_cell else "grey"
        cells.append(f'<td data-v="{ {"green":0,"orange":1,"red":2}.get(bcat,3) }">{_light(bcat)}</td>')
        val_cell = sr.cells.get("validity")
        vcat = val_cell.category if val_cell else "grey"
        vtip = val_cell.reason if val_cell and val_cell.reason else vcat
        cells.append(f'<td data-v="{ {"green":0,"orange":1,"red":2}.get(vcat,3) }" '
                     f'title="{html.escape(vtip)}">{_light(vcat)}</td>')
        # Reasons stay on one line: a wrapping chip stack triples the height of
        # every red row, and in a 350-row table that is the difference between
        # scanning it and scrolling it. The full text is in the tooltip and,
        # unabridged, in the drill-down.
        chips = " ".join(f'<span class="chip">{html.escape(c)}</span>' for c in sr.chips)
        cells.append(f'<td data-v="0" class="reasons" '
                     f'title="{html.escape(" · ".join(sr.chips))}">{chips}</td>')

        rows_html.append(
            f'<tr class="mainrow" {" ".join(attrs)} onclick="toggleDrill({i})">'
            + "".join(cells) + "</tr>"
        )
        rows_html.append(_drilldown_row(i, sr, len(head),
                                        study if i in draw_rows else None,
                                        drawable=(study is not None)))

    return (f'<div class="tablewrap"><table id="scoretable"><thead><tr>{thead}</tr></thead>'
            f'<tbody>{"".join(rows_html)}</tbody></table></div>')


def _drilldown_row(i: int, sr: ScoredRow, ncols: int, study=None,
                   *, drawable: bool = False) -> str:
    m = sr.metrics
    params = json.dumps(m.params, indent=2, default=str)
    raw = {k: v for k, v in (m.raw or {}).items() if not k.startswith("_")}
    raw_txt = json.dumps(raw, indent=2, default=str)
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in m.notes) or "<li>—</li>"
    reasons = "".join(f"<li>{html.escape(c)}</li>" for c in sr.chips) or "<li>all green</li>"
    body = (
        f'<div class="drillgrid">'
        f'<div><h4>Config</h4><code class="cfglabel">{html.escape(m.label)}</code>'
        f'<h4>Swept params</h4><pre>{html.escape(params)}</pre></div>'
        f'<div><h4>Score reasons</h4><ul>{reasons}</ul>'
        f'<h4>Notes</h4><ul>{notes}</ul></div>'
        f'<div><h4>Raw metrics</h4><pre>{html.escape(raw_txt)}</pre></div>'
        f'{_schematic_html(sr, study) if study is not None else _schematic_omitted(drawable)}'
        f'</div>'
    )
    return (f'<tr id="drill{i}" class="drill" style="display:none">'
            f'<td colspan="{ncols}">{body}</td></tr>')


def _plots_html(plots: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for j, p in enumerate(plots):
        variants = p["variants"]
        # data-* attributes carry every rendered variant for JS composition
        data_attrs = " ".join(f'data-{k}="{uri}"' for k, uri in variants.items())
        img = (f'<img id="plotimg{j}" src="{variants["base"]}" {data_attrs} '
               f'alt="{html.escape(p["title"])}">')
        toggles: list[str] = []
        if p.get("has_best"):
            toggles.append(f'<label class="toggle"><input type="checkbox" '
                           f'onchange="composePlot({j})" data-role="best"> best-3</label>')
        if p.get("has_ref"):
            toggles.append(f'<label class="toggle"><input type="checkbox" '
                           f'onchange="composePlot({j})" data-role="ref"> references</label>')
        toggle_html = " ".join(toggles)
        blocks.append(
            f'<figure class="plot" id="plotfig{j}">{img}'
            f'<figcaption><b>{html.escape(p["title"])}</b> {toggle_html}'
            f'<br>{html.escape(p["caption"])}</figcaption></figure>'
        )
    return '<div class="plots">' + "".join(blocks) + "</div>"


def _provenance_html(result: StudyResult, refs=None) -> str:
    prov = result.provenance
    consts = resolved_constants(result.study)
    consts_txt = json.dumps(consts, indent=2, default=str)
    cfg = html.escape(prov.source_text or "(config text unavailable)")
    refs = refs or []
    items = []
    for rs in refs:
        if rs.error:
            status = f'<span style="color:#cf222e">could not resolve — {html.escape(rs.error)}</span>'
        else:
            status = f'{len(rs.points)} overlay point(s)'
        items.append(f"<li>{html.escape(rs.label)} <code>{html.escape(rs.kind)}</code> — {status}</li>")
    refs_html = "".join(items) or "<li>none declared</li>"
    return (
        f'<h2>Constants &amp; provenance</h2>'
        f'<p><b>Model commit:</b> <code>{html.escape(prov.git_hash)}</code> · '
        f'<b>Run:</b> {html.escape(prov.timestamp)} · '
        f'<b>Points:</b> {prov.n_points} · '
        f'<b>Source:</b> <code>{html.escape(prov.source_path or "")}</code></p>'
        f'<h4>Declared references</h4><ul>{refs_html}</ul>'
        f'<details><summary>Resolved constants (every value used)</summary>'
        f'<pre>{html.escape(consts_txt)}</pre></details>'
        f'<details><summary>Verbatim study config</summary><pre>{cfg}</pre></details>'
    )


_JS = """
// main rows and their drill-down partner, kept together through sort + filter
function rowPairs(){
  var tb=document.getElementById('scoretable').tBodies[0];
  var out=[];
  for(var i=0;i<tb.rows.length;i++){
    var r=tb.rows[i];
    if(!r.classList.contains('mainrow')) continue;
    var d=tb.rows[i+1];
    out.push([r, (d && d.classList.contains('drill')) ? d : null]);
  }
  return out;
}
function sortTable(col){
  var t=document.getElementById('scoretable');
  var tb=t.tBodies[0];
  var pairs=rowPairs();
  var dir=t.getAttribute('data-sort')===String(col)&&t.getAttribute('data-dir')==='asc'?-1:1;
  t.setAttribute('data-dir',dir===1?'asc':'desc');
  t.setAttribute('data-sort',String(col));
  pairs.sort(function(a,b){
    var x=a[0].cells[col].getAttribute('data-v');
    var y=b[0].cells[col].getAttribute('data-v');
    var nx=parseFloat(x),ny=parseFloat(y);
    if(!isNaN(nx)&&!isNaN(ny))return (nx-ny)*dir;
    return (''+x).localeCompare(''+y)*dir;
  });
  pairs.forEach(function(g){tb.appendChild(g[0]); if(g[1])tb.appendChild(g[1]);});
}
function toggleDrill(i){
  var r=document.getElementById('drill'+i);
  if(!r) return;
  r.style.display = r.style.display==='none' ? 'table-row' : 'none';
}
function applyFilters(){
  var box=document.getElementById('filters');
  if(!box) return;
  var sels=box.querySelectorAll('select');
  var input=document.getElementById('f-text');
  var q=(input && input.value ? input.value : '').toLowerCase().trim();
  var shown=0, total=0;
  rowPairs().forEach(function(g){
    var r=g[0], ok=true;
    for(var i=0;i<sels.length;i++){
      var s=sels[i];
      if(!s.value) continue;
      var key=s.getAttribute('data-key');
      if(r.getAttribute('data-'+key)!==s.value){ok=false;break;}
    }
    if(ok && q && (r.getAttribute('data-txt')||'').indexOf(q)<0) ok=false;
    total++;
    r.style.display = ok ? '' : 'none';
    if(g[1]) g[1].style.display='none';
    if(ok) shown++;
  });
  var c=document.getElementById('filtercount');
  if(c) c.textContent = shown===total ? (total+' rows') : ('showing '+shown+' of '+total+' rows');
}
function resetFilters(){
  var box=document.getElementById('filters');
  if(!box) return;
  box.querySelectorAll('select').forEach(function(s){s.value='';});
  var input=document.getElementById('f-text');
  if(input) input.value='';
  applyFilters();
}
function filterToDesign(gid){
  var s=document.getElementById('f-gid');
  if(s){ s.value=gid; applyFilters(); }
  var t=document.getElementById('overview');
  if(t) t.scrollIntoView({behavior:'smooth'});
}
document.addEventListener('DOMContentLoaded', applyFilters);
function composePlot(j){
  var fig=document.getElementById('plotfig'+j);
  var img=document.getElementById('plotimg'+j);
  var best=false, ref=false;
  fig.querySelectorAll('input[type=checkbox]').forEach(function(cb){
    if(cb.getAttribute('data-role')==='best') best=cb.checked;
    if(cb.getAttribute('data-role')==='ref')  ref=cb.checked;
  });
  var key = best && ref ? 'bestref' : best ? 'best' : ref ? 'ref' : 'base';
  var uri = img.getAttribute('data-'+key) || img.getAttribute('data-base');
  img.src = uri;
}
"""


def _css() -> str:
    return """
:root{color-scheme:light dark;}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
     margin:0;padding:2rem;max-width:1460px;margin:auto;line-height:1.5;
     font-variant-numeric:tabular-nums;}
h1{margin-bottom:.2rem;} .goal{color:#8b949e;margin-top:0;}
table{border-collapse:collapse;width:100%;font-size:13px;margin:1rem 0;}
th,td{border:1px solid #d0d7de;padding:5px 8px;text-align:left;white-space:nowrap;}
td.num,th{white-space:nowrap;}
td.num{text-align:right;}
.tablewrap{overflow-x:auto;border-radius:8px;}
th{background:#f6f8fa;cursor:pointer;position:sticky;top:0;user-select:none;}
tr.mainrow{cursor:pointer;}
#scoretable tr.mainrow:hover td{background:rgba(9,105,218,.14);}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle;}
.chip{display:inline-block;background:rgba(207,34,46,.12);border:1px solid rgba(207,34,46,.3);
      border-radius:10px;padding:0 7px;margin:1px;font-size:11px;white-space:nowrap;}
.drill td{background:rgba(127,127,127,.06);text-align:left;white-space:normal;}
.drillgrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;}
.drillgrid pre{background:rgba(127,127,127,.1);padding:.5rem;border-radius:6px;overflow:auto;font-size:11px;max-height:320px;}
.plots{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:1.5rem;}
figure.plot{margin:0;} figure.plot img{max-width:100%;border:1px solid #d0d7de;border-radius:6px;}
figcaption{font-size:12px;color:#57606a;margin-top:.4rem;}
.toggle{font-size:12px;margin-left:.5rem;}
.legend span{margin-right:1rem;font-size:12px;}
pre{white-space:pre-wrap;}
.decision{border:1px solid #d0d7de;border-radius:10px;padding:1rem 1.2rem;margin:1.5rem 0;}
.decision h2{margin-top:0;}
.decision h3{font-size:14px;margin:1.2rem 0 .4rem;}
.picks{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.8rem;margin-bottom:.8rem;}
.pick{border:1px solid #d0d7de;border-radius:8px;padding:.6rem .7rem;}
.pick h4{margin:0;font-size:13px;}
.picksub{font-size:11px;color:#57606a;margin-bottom:.35rem;}
.pickname{font-size:13px;font-weight:600;word-break:break-word;}
.pickwhy{font-size:11px;color:#57606a;margin-top:.25rem;}
table.pareto{font-size:12px;width:auto;}
.diagnosis{border-left:4px solid #bf8700;}
.dhead{font-size:14px;font-weight:600;margin:.2rem 0 .8rem;}
ul.candidates{font-size:12px;columns:2;margin:.4rem 0;padding-left:1.1rem;}
ul.candidates code{font-size:11px;}
.decnotes{font-size:12px;margin:.8rem 0 0;padding-left:1.1rem;}
.decnotes li{margin:.25rem 0;}
.muted{font-size:12px;color:#57606a;}
.tier{font-size:10px;display:block;font-weight:400;color:#57606a;}
.warn{color:#bf8700;font-weight:600;}
.star{color:#bf8700;margin-left:3px;}
.reasons{max-width:340px;overflow:hidden;text-overflow:ellipsis;}
#scoretable tbody tr:nth-of-type(4n+1) td{background:rgba(127,127,127,.045);}
#scoretable td{padding:3px 8px;}
.cfglabel{font-size:11px;word-break:break-all;display:block;margin:.2rem 0 .6rem;}

/* ── filter bar ─────────────────────────────────────────────────────────── */
.filters{display:flex;flex-wrap:wrap;gap:.6rem .9rem;align-items:flex-end;
  border:1px solid #d0d7de;border-radius:10px;padding:.7rem .9rem;margin:.8rem 0;
  background:rgba(127,127,127,.05);position:sticky;top:0;z-index:5;
  backdrop-filter:blur(6px);}
.filters label{display:flex;flex-direction:column;font-size:11px;color:#57606a;gap:2px;}
.filters select,.filters input{font-size:12px;padding:3px 6px;border-radius:6px;
  border:1px solid #d0d7de;background:transparent;color:inherit;max-width:230px;}
.btn{font-size:12px;padding:4px 10px;border-radius:6px;border:1px solid #d0d7de;
  background:transparent;color:inherit;cursor:pointer;}
.btn:hover{background:rgba(127,127,127,.12);}

/* ── design groups ──────────────────────────────────────────────────────── */
.gid{display:inline-block;background:#0969da;color:#fff;border-radius:5px;
  padding:0 6px;font-size:11px;font-weight:700;margin-right:.4rem;}
details.dgroup{border:1px solid #d0d7de;border-radius:8px;margin:.8rem 0;padding:.2rem .8rem;}
details.dgroup>summary{cursor:pointer;padding:.5rem 0;font-size:13px;}
details.dgroup>summary::marker{color:#8b949e;}
.gbody{padding:.2rem 0 .8rem;}
.vbar{margin-left:.6rem;font-size:12px;color:#57606a;}
.pickval{font-size:15px;font-weight:700;margin:.15rem 0;}
table.compare td .tier{max-width:260px;white-space:normal;}
table.levers td.lev{font-weight:600;}
details.notches{margin:.4rem 0 0;font-size:12px;}
details.notches summary{cursor:pointer;color:#57606a;}

/* ── improvement advice ─────────────────────────────────────────────────── */
.advicegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem;}
.advice{border:1px solid #d0d7de;border-radius:8px;padding:.6rem .8rem;}
.advice h4{margin:.1rem 0 .5rem;font-size:13px;}
.advice ul{margin:0;padding-left:1.1rem;font-size:12px;}
.advice>ul>li{margin-bottom:.7rem;}
.cost{color:#57606a;font-size:11.5px;margin-top:.2rem;}
.cost ul{padding-left:1rem;margin:.15rem 0;}
.tag{display:inline-block;border-radius:9px;padding:0 6px;font-size:10px;
  font-weight:700;text-transform:uppercase;letter-spacing:.02em;margin-right:.3rem;}
.tag.measured{background:rgba(26,127,55,.15);color:#1a7f37;}
.tag.model{background:rgba(130,80,223,.15);color:#8250df;}

@media (prefers-color-scheme:dark){
  th{background:#161b22;} th,td{border-color:#30363d;} .goal,figcaption{color:#8b949e;}
  .decision,.pick,.advice,.filters,details.dgroup{border-color:#30363d;}
  .picksub,.pickwhy,.muted,.tier,.cost,.vbar,.filters label{color:#8b949e;}
  .filters select,.filters input,.btn{border-color:#30363d;}
}
"""


def write_workbook(
    result: StudyResult,
    out_path: str | Path,
    *,
    diagnosis: Diagnosis | None = None,
    price: str = "auto",
) -> Path:
    """
    Render *result* to a self-contained HTML chapter and emit its JSON sidecar.

    Pass an already-computed *diagnosis* to avoid re-running the analysis (the
    UI does); otherwise one is computed here, with *price* controlling whether
    relaxation pricing runs (``auto`` = only when nothing scored green).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scored = score_result(result, result.study.scoring)
    goal = result.study.goal
    dec = decide(scored, result.study.decide, goal)
    best = set(_best_indices(scored, goal, spec=result.study.decide))
    if diagnosis is None:
        diagnosis = diagnose(result.study, scored, price=price)

    # ── designs vs the conditions they were run at ──────────────────────────
    # Row order out of run_study is point order, so a StudyPoint and its scored
    # row share an index — no label join, and nothing to go stale if labels
    # change.  Guarded anyway: a family that failed to solve still produces a row.
    points = list(result.study.points)
    grouping = build_grouping(result.study, points) if len(points) == len(scored) \
        else build_grouping(result.study, points[:0])
    all_axes = list(grouping.design_axes) + list(grouping.condition_axes)
    leaves = {i: row_axis_values(p, all_axes) for i, p in enumerate(points)} \
        if len(points) == len(scored) else {}
    decisions = {g.gid: decide_subset(scored, g.indices, result.study.decide, goal)
                 for g in grouping.groups}

    # resolve click-in reference overlays (modelled / experimental / chapter)
    from stepgen.studio.references import resolve_references
    refs = resolve_references(result.study)

    plots = _build_plots(scored, goal, refs)
    plots_html = _plots_html(plots)

    n_green = sum(1 for s in scored if s.overall == "green")
    n_orange = sum(1 for s in scored if s.overall == "orange")
    n_red = sum(1 for s in scored if s.overall == "red")

    doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(result.study.title)}</title>
<style>{_css()}</style></head>
<body>
<h1>{html.escape(result.study.title)}</h1>
<p class="goal">Deciding on: <b>{html.escape(", ".join(a.key for a in dec.axes))}</b> ·
  Families: {html.escape(", ".join(result.study.families))} ·
  {len(grouping.groups)} design{"s" if len(grouping.groups) != 1 else ""} ·
  {len(scored)} configs</p>
<p class="legend">
  <span>{_light("green")}green {n_green}</span>
  <span>{_light("orange")}orange {n_orange}</span>
  <span>{_light("red")}red {n_red}</span>
  <span>★ = best {len(best)} all-round</span>
</p>

{_intent_html(result.study)}

{_design_sections_html(scored, grouping, leaves, decisions,
                       _design_compare_html(scored, grouping, leaves, decisions, dec.axes))}

{_decision_html(scored, dec)}

{_diagnosis_html(diagnosis)}

<h2 id="overview">Overview — scored comparison</h2>
<p style="font-size:12px;color:#57606a">Filter with the bar below; click a header to sort;
click a row to drill in. Verdict is <b>worst-category-wins</b> across every applicable gate;
grey = N-A for that family.
<b>Margin</b> is how far the weakest applicable metric sits from its red boundary, as a
fraction of the green→red span, discounted by how much the model is trusted for that
number. <b>Valid</b> is orange when the design sits outside the envelope the model has
been checked in — never green there, and never red on those grounds alone.</p>
{_filters_html(grouping, all_axes)}
{_table_html(scored, best, result.study, grouping, leaves)}

<h2>Standard plots</h2>
{plots_html}

{_provenance_html(result, refs)}

<script>{_JS}</script>
<script>{_panzoom_js()}</script>
</body></html>
"""
    out_path.write_text(doc, encoding="utf-8")

    # JSON sidecar for cross-chapter reference
    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(_chapter_json(result, scored, dec, diagnosis), indent=2, default=str),
        encoding="utf-8")
    return out_path


def _chapter_json(
    result: StudyResult,
    scored: list[ScoredRow],
    dec: Decision | None = None,
    diagnosis: Diagnosis | None = None,
) -> dict[str, Any]:
    dec = dec or decide(scored, result.study.decide, result.study.goal)
    plan = result.study.intent_plan
    return {
        "title": result.study.title,
        "goal": result.study.goal,
        "families": result.study.families,
        "git_hash": result.provenance.git_hash,
        "timestamp": result.provenance.timestamp,
        # the question as asked, when it was asked as a target rather than a grid
        "intent": None if plan is None else plan.summary(),
        # why the answer came out this way, and what would change it
        "diagnosis": None if diagnosis is None else diagnosis.to_json(),
        # the decide layer, recorded so the verdict can be audited later — most
        # of all the weights, which are meaningless if they are not written down
        "decision": {
            "axes": [a.key for a in dec.axes],
            "weights": dec.weights,
            "per_axis_winner": {
                k: (scored[i].metrics.label if i is not None else None)
                for k, i in dec.per_axis.items()
            },
            "pareto": [scored[i].metrics.label for i in dec.pareto],
            "all_round": (scored[dec.all_round].metrics.label
                          if dec.all_round is not None else None),
            "safest": (scored[dec.safest].metrics.label
                       if dec.safest is not None else None),
            "all_red": dec.all_red,
            "study_wide_caveats": dec.caveats,
        },
        "rows": [
            {
                "label": sr.metrics.label,
                "family": sr.metrics.family,
                "overall": sr.overall,
                "chips": sr.chips,
                "params": sr.metrics.params,
                "composite": dec.composite.get(i),
                "min_margin": sr.min_margin,
                "min_margin_discounted": sr.min_margin_discounted,
                "weakest_metric": sr.weakest_metric,
                "extrapolated": sr.extrapolated_keys,
                "confidence": {k: c.confidence for k, c in sr.cells.items()
                               if c.category != "grey"},
                "metrics": {
                    "throughput_mlhr": sr.metrics.throughput_mlhr,
                    "N_dfu": sr.metrics.N_dfu,
                    "droplet_um": sr.metrics.droplet_um,
                    "frequency_hz": sr.metrics.frequency_hz,
                    "uniformity_pct": sr.metrics.uniformity_pct,
                    "operating_Po_mbar": sr.metrics.operating_Po_mbar,
                    "regime_Ca": sr.metrics.regime_Ca,
                    "hub_budget_pct": sr.metrics.hub_budget_pct,
                    "area_used_cm2": sr.metrics.area_used_cm2,
                    "fits_square": sr.metrics.fits_square,
                    "manufacturable": sr.metrics.manufacturable,
                    "exit_width_um": sr.metrics.exit_width_um,
                    "exit_depth_um": sr.metrics.exit_depth_um,
                    "lambda_visc": sr.metrics.lambda_visc,
                },
            }
            for i, sr in enumerate(scored)
        ],
    }


def write_book_index(book_dir: str | Path) -> Path:
    """Write ``book/index.html`` linking every ``*.json`` chapter in *book_dir*."""
    book_dir = Path(book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)
    chapters = []
    for jf in sorted(book_dir.glob("*.json")):
        if jf.name == "index.json":
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        chapters.append((jf.with_suffix(".html").name, data))

    items = []
    for html_name, data in chapters:
        rows = data.get("rows", [])
        greens = sum(1 for r in rows if r.get("overall") == "green")
        fams = ", ".join(data.get("families", []) or [])
        items.append(
            f'<li><a href="{html.escape(html_name)}">{html.escape(data.get("title","(untitled)"))}</a>'
            f' — goal <b>{html.escape(str(data.get("goal","")))}</b>, '
            f'families <i>{html.escape(fams)}</i>, '
            f'{len(rows)} configs, {greens} green '
            f'<span style="color:#8b949e">[{html.escape(str(data.get("git_hash",""))[:8])}]</span></li>'
        )
    body = "".join(items) or "<li>no chapters yet</li>"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StepGen Design Studio — book</title><style>{_css()}</style></head>
<body><h1>StepGen Design Studio — book</h1>
<p class="goal">Chapters tie together here; each is a self-contained scored study. Generated {ts}.</p>
<ul>{body}</ul></body></html>"""
    index = book_dir / "index.html"
    index.write_text(doc, encoding="utf-8")
    return index
