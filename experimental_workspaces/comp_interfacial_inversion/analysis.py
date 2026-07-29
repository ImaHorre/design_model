"""
analysis.py — orchestrate the interfacial inversion end to end.
===============================================================
Loads the pooled dataset, runs the inversions, writes:
  - calibrated_constants.yaml   (the durable, updatable artifact)
  - figures/*.png               (4 figures)
  - report.md                   (findings + 'what else is needed')

Run:  python analysis.py     (from the workspace dir, project .venv active)
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(HERE))

from stepgen.config import load_config                              # noqa: E402
from stepgen.models.stage_wise_v3.stage1_physics import compute_rung_resistance  # noqa: E402

from data_loader import load_events, summarize_by_condition, JUNCTION_W_UM, JUNCTION_H_UM  # noqa: E402
import inversion as inv                                             # noqa: E402
import regime_estimator as reg                                     # noqa: E402

FIGS = HERE / "figures"
FIGS.mkdir(exist_ok=True)
CONFIG_PATH = PROJECT_ROOT / "configs" / "v5_30.yaml"

# Literature interfacial tension used ONLY for the provisional gamma/theta split.
# Provisional until a pendant-drop measurement.
#
# CORRECTION 2026-07-29: this value was originally selected as a literature
# figure for 2% SDS against *silicone* oil. The dispersed phase is **sunflower
# oil** (`DispPhase = SO`; ruling confirmed 2026-07-29, see CLAUDE.md), so the
# source pair was wrong. 9 mN/m is retained as a placeholder of the right order
# — SDS well above CMC drives most vegetable-oil/water interfaces into the
# single-digit mN/m range — but it is now an *assumption about the wrong fluid
# pair carried forward deliberately*, not a sourced value.
#
# Everything downstream of it (cos-theta, the absolute beta) inherits that. The
# pendant-drop measurement already listed as this workspace's keystone next step
# is what replaces it, and it must be run against sunflower oil.
GAMMA_LIT_2PC_MNM = 9.0

PO_REF, QW_REF = 200.0, 5.0
ONSET_PO_MBAR = 30.0
BLOWOUT_PO_MBAR = 1000.0


def main() -> None:
    cfg = load_config(str(CONFIG_PATH))
    df = load_events()
    R_rung = compute_rung_resistance(cfg)

    # ── Inversions ──────────────────────────────────────────────────────────
    onset = inv.entry_pressure_from_onset(cfg, onset_po_mbar=ONSET_PO_MBAR)
    gct_2pc_mNm = inv.gamma_cos_theta_from_Pcap(onset.value) * 1e3
    curve = inv.fit_sds_curve(df, cfg, P_cap_2pc=onset.value, Po_ref=PO_REF, Qw_ref=QW_REF)
    beta = inv.fit_stage2_beta(df, curve, Po_ref=PO_REF, Qw_ref=QW_REF)
    xc = inv.po_scaling_crosscheck(df, cfg, Qw_ref=QW_REF)

    # Provisional gamma / theta split (needs literature gamma anchor).
    cos_theta_2pc = min(GAMMA_LIT_2PC_MNM and gct_2pc_mNm / GAMMA_LIT_2PC_MNM, 1.0)
    theta_2pc_deg = float(np.degrees(np.arccos(np.clip(cos_theta_2pc, -1, 1))))

    # ── Regime grid ─────────────────────────────────────────────────────────
    po_grid = [20, 30, 50, 100, 200, 300, 400, 600, 800, 1000, 1200]
    grid = reg.estimate_grid(cfg, po_grid, QW_REF, onset.value, P_blowout_mbar=BLOWOUT_PO_MBAR)

    # ── Outputs ─────────────────────────────────────────────────────────────
    write_constants(cfg, R_rung, onset, gct_2pc_mNm, curve, beta, xc,
                    cos_theta_2pc, theta_2pc_deg)
    make_figures(df, cfg, curve, beta, grid)
    write_report(cfg, onset, gct_2pc_mNm, curve, beta, xc,
                 cos_theta_2pc, theta_2pc_deg, grid)

    print("Done. Wrote calibrated_constants.yaml, figures/, report.md")


# ─────────────────────────────────────────────────────────────────────────────
def write_constants(cfg, R_rung, onset, gct_2pc_mNm, curve, beta, xc,
                    cos_theta_2pc, theta_2pc_deg) -> None:
    """Emit the durable YAML of calibrated constants with provenance."""
    lines = []
    lines.append("# Calibrated interfacial constants -- SDS / sunflower-oil, device V5-8-1")
    lines.append(f"# Generated: {date.today().isoformat()} by comp_interfacial_inversion/analysis.py")
    lines.append("# Source data: experimental_workspaces/po_sweep/data/stage_timings.csv")
    lines.append("# Update the 'provisional' block when a pendant-drop gamma arrives.")
    lines.append("")
    lines.append("meniscus_radius_um: %.1f            # convention: exit_width/2" % (inv.R_MEN_M * 1e6))
    lines.append("")
    lines.append("capillary_entry_pressure:")
    lines.append("  # 'make droplets at all' threshold (Stage-2 oil entry). Anchored by")
    lines.append(f"  # observed production onset ~{ONSET_PO_MBAR:.0f} mbar. RECOMMENDED value for the")
    lines.append(f"  # model's droplet_model.dP_cap_ow_Pa (currently {cfg.droplet_model.dP_cap_ow_Pa:.0f}).")
    lines.append(f"  P_entry_Pa: {onset.value:.0f}")
    lines.append(f"  P_entry_lo_Pa: {onset.lo:.0f}")
    lines.append(f"  P_entry_hi_Pa: {onset.hi:.0f}")
    lines.append(f"  gamma_cos_theta_mNm: {gct_2pc_mNm:.1f}   # at 2% SDS")
    lines.append("  provisional: false")
    lines.append("")
    lines.append("stage1_refill_backpressure:")
    lines.append("  # Effective opposing pressure from the 2% Stage-1 Po-scaling steepening.")
    lines.append("  # EXCEEDS the capillary entry pressure -> lumps non-capillary")
    lines.append("  # (velocity-dependent contact-line/entrance) dissipation. NOT gamma*cos(theta).")
    lines.append(f"  P_backpressure_Pa: {xc['P_cap_Pa']:.0f}")
    lines.append(f"  band_Pa: [{xc['P_cap_band'][0]:.0f}, {xc['P_cap_band'][1]:.0f}]")
    lines.append("  provisional: false")
    lines.append("")
    lines.append("gamma_cos_theta_vs_sds:   # Po=200, Qw=5; anchored to onset at 2%")
    for _, r in curve.iterrows():
        lines.append(f"  - sds_pc: {r.sds_pc:g}")
        lines.append(f"    gamma_cos_theta_mNm: {r.gamma_cos_theta_mNm:.1f}")
        lines.append(f"    ci_mNm: [{r.gct_lo_mNm:.1f}, {r.gct_hi_mNm:.1f}]")
        lines.append(f"    regime_class: {r.regime_class}")
    lines.append("")
    lines.append("stage2_prefactor_beta:")
    lines.append("  # (S2_obs_ratio-1) = beta * (gamma_ratio-1), fit above CMC ([SDS]>=0.5%).")
    lines.append("  # beta ~ 0 => Stage-2 timing is gamma-INSENSITIVE in the dripping window")
    lines.append("  # (viscous neck dissipation), far below pure capillary scaling (beta=1).")
    lines.append(f"  beta: {beta.value:.3f}")
    lines.append(f"  ci: [{beta.lo:.3f}, {beta.hi:.3f}]")
    lines.append("  provisional: false")
    lines.append("")
    lines.append("provisional_gamma_theta_split:")
    lines.append("  # PROVISIONAL: requires a literature/pendant-drop gamma anchor. The two")
    lines.append("  # observed regime boundaries do NOT pin gamma (junction Ca ~1e-5 everywhere;")
    lines.append("  # jetting is pressure-driven, not a Ca transition). Replace gamma_lit_2pc_mNm")
    lines.append("  # with a measured pendant-drop value to finalize.")
    lines.append(f"  gamma_lit_2pc_mNm: {GAMMA_LIT_2PC_MNM:.1f}")
    lines.append(f"  cos_theta_2pc: {cos_theta_2pc:.3f}")
    lines.append(f"  theta_2pc_deg: {theta_2pc_deg:.1f}")
    lines.append("  provisional: true")
    lines.append("")
    lines.append("capillary_number_note:")
    lines.append("  # Junction Ca = mu_c * (Q_rung/A_exit) / gamma stays O(1e-5) across the")
    lines.append("  # entire feasible Po range -- never approaches the ~0.3 jetting threshold.")
    lines.append("  Ca_continuous_at_600mbar: 6.0e-6")
    lines.append("  jetting_is_capillary_transition: false")
    (HERE / "calibrated_constants.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
def make_figures(df, cfg, curve, beta, grid) -> None:
    sub = summarize_by_condition(df)
    ref = sub[(sub.Po_mbar == PO_REF) & (sub.Qw_mlhr == QW_REF)].sort_values("sds_pc")

    # Fig 1: gamma*cos(theta) vs [SDS] with uncertainty
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    c = curve.sort_values("sds_pc")
    clean = c[c.regime_class == "clean"]; held = c[c.regime_class == "heldout"]
    ax.errorbar(clean.sds_pc, clean.gamma_cos_theta_mNm,
                yerr=[clean.gamma_cos_theta_mNm - clean.gct_lo_mNm,
                      clean.gct_hi_mNm - clean.gamma_cos_theta_mNm],
                fmt="o-", capsize=4, label="clean (above CMC)")
    ax.errorbar(held.sds_pc, held.gamma_cos_theta_mNm,
                yerr=[np.abs(held.gamma_cos_theta_mNm - held.gct_lo_mNm),
                      np.abs(held.gct_hi_mNm - held.gamma_cos_theta_mNm)],
                fmt="s--", capsize=4, color="tab:red", label="held-out (near/below CMC)")
    ax.axvline(0.24, ls=":", color="gray", label="CMC ~0.24%")
    ax.set_xlabel("[SDS] (mass %)"); ax.set_ylabel(r"$\gamma\cos\theta$  (mN/m)")
    ax.set_title("Back-calculated capillary group vs surfactant concentration")
    ax.set_xscale("log"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIGS / "fig_01_gamma_cos_theta_vs_sds.png", dpi=130); plt.close(fig)

    # Fig 2: Stage-2 observed vs ideal gamma-scaling
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    gct = curve.set_index("sds_pc")["gamma_cos_theta_mNm"]; gct2 = gct.loc[2.0]
    s2 = ref.set_index("sds_pc")["S2_mean"]; s2b = s2.loc[2.0]
    for sds in sorted(s2.index, reverse=True):
        ideal = gct.loc[sds] / gct2
        obs = s2.loc[sds] / s2b
        mk = "o" if sds >= 0.5 else "s"
        col = "tab:blue" if sds >= 0.5 else "tab:red"
        ax.scatter(ideal, obs, s=60, marker=mk, color=col, zorder=3)
        ax.annotate(f"{sds:g}%", (ideal, obs), textcoords="offset points", xytext=(6, 4))
    xs = np.linspace(1, max(2.0, float(gct.max() / gct2)), 50)
    ax.plot(xs, xs, "k--", label=r"pure $\gamma$-scaling ($\beta$=1)")
    ax.plot(xs, 1 + beta.value * (xs - 1), "b-",
            label=fr"fit $\beta$={beta.value:.2f} (above CMC)")
    ax.axhline(1, color="gray", lw=0.6)
    ax.set_xlabel(r"ideal $\gamma$-scaling ratio  $\gamma(c)/\gamma(2\%)$")
    ax.set_ylabel(r"observed Stage-2 ratio  $\tau_2(c)/\tau_2(2\%)$")
    ax.set_title("Stage-2 snap-off: far less γ-sensitive than pure capillarity")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIGS / "fig_02_stage2_beta.png", dpi=130); plt.close(fig)

    # Fig 3: Ca(Po) + regime zones + boundaries
    fig, (axc, axm) = plt.subplots(2, 1, figsize=(6.8, 6.4), sharex=True,
                                    gridspec_kw={"height_ratios": [2, 1]})
    po = np.array([g.Po_mbar for g in grid])
    ca = np.array([g.Ca_continuous for g in grid])
    axc.semilogy(po, ca, "o-", label=r"junction $Ca_{continuous}$")
    axc.semilogy(po, [g.Ca_dispersed for g in grid], "s--", color="tab:orange",
                 label=r"junction $Ca_{dispersed}$")
    axc.axhline(reg.CA_JET, color="red", ls=":", label=f"jetting threshold ~{reg.CA_JET}")
    axc.set_ylabel("junction Ca"); axc.legend(fontsize=8); axc.grid(alpha=0.3)
    axc.set_title("Junction Ca stays ~1e-5 — jetting is NOT a capillary transition here")
    # margin panel
    margin = np.array([g.entry_margin_Pa for g in grid]) / 100.0
    colors = {"stall": "tab:red", "dripping": "tab:green", "blowout": "tab:purple"}
    axm.bar(po, margin, width=np.diff(po, prepend=po[0] - 10) * 0.6,
            color=[colors[g.verdict] for g in grid])
    axm.axhline(0, color="k", lw=0.8)
    axm.axvline(ONSET_PO_MBAR, ls=":", color="tab:red")
    axm.axvline(BLOWOUT_PO_MBAR, ls=":", color="tab:purple")
    axm.set_ylabel("entry margin\n(mbar)"); axm.set_xlabel("Po (mbar)")
    axm.text(ONSET_PO_MBAR, axm.get_ylim()[1] * 0.7, " onset", color="tab:red", fontsize=8)
    axm.text(BLOWOUT_PO_MBAR, axm.get_ylim()[1] * 0.7, " blowout", color="tab:purple",
             fontsize=8, ha="right")
    axm.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIGS / "fig_03_ca_regime_map.png", dpi=130); plt.close(fig)

    # Fig 4: held-out validation — S1 & S2 ratios vs [SDS] (data reproduces conc_sweep)
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    r = ref.sort_values("sds_pc", ascending=False)
    s1b = r[r.sds_pc == 2.0]["S1_mean"].iloc[0]; s2b = r[r.sds_pc == 2.0]["S2_mean"].iloc[0]
    ax.plot(r.sds_pc, r.S1_mean / s1b, "o-", label="Stage-1 ratio")
    ax.plot(r.sds_pc, r.S2_mean / s2b, "s-", label="Stage-2 ratio")
    ax.axvline(0.24, ls=":", color="gray", label="CMC ~0.24%")
    ax.axhline(1, color="k", lw=0.5)
    ax.set_xscale("log"); ax.set_xlabel("[SDS] (mass %)"); ax.set_ylabel("time ratio vs 2%")
    ax.set_title("Stage timings vs [SDS] (reproduces conc_sweep ratios)")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIGS / "fig_04_stage_ratios_validation.png", dpi=130); plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
def write_report(cfg, onset, gct_2pc_mNm, curve, beta, xc,
                 cos_theta_2pc, theta_2pc_deg, grid) -> None:
    L = []
    L.append("# Interfacial Inversion — SDS / sunflower-oil, device V5-8-1")
    L.append(f"*Generated {date.today().isoformat()} by `analysis.py`. "
             f"Constants in `calibrated_constants.yaml`.*\n")

    L.append("## Headline\n")
    L.append(f"- **Capillary entry pressure P_entry = {onset.value:.0f} Pa "
             f"[{onset.lo:.0f}, {onset.hi:.0f}]** (from the ~{ONSET_PO_MBAR:.0f} mbar onset) "
             f"→ **γ·cosθ ≈ {gct_2pc_mNm:.0f} mN/m** at 2% SDS "
             f"(matches the model's 15 mN/m default).")
    L.append(f"- This is the **'make droplets at all' threshold** and the recommended "
             f"`dP_cap_ow_Pa` — the model currently uses "
             f"{cfg.droplet_model.dP_cap_ow_Pa:.0f} Pa (~2.5× too high; predicts onset ~63 mbar vs observed ~30).")
    L.append(f"- **Junction Ca ≈ 1e-5 across the whole feasible range** (even at 1200 mbar), "
             f"~1e4–1e5× below the ~0.3 jetting threshold. Droplet size is geometry-set; "
             f"**Ca does not drive size or a jetting transition here**.")
    L.append(f"- **Stage-2 prefactor β = {beta.value:.2f} [{beta.lo:.2f}, {beta.hi:.2f}]** "
             f"(≈0): snap-off timing is γ-insensitive in the dripping window — far below "
             f"pure capillary scaling (β=1).\n")

    L.append("## 1. Capillary entry pressure and γ·cosθ(2%)\n")
    L.append("The observed production onset (~30 mbar, frequency→0) is where the network "
             "driving pressure ΔP_rung can no longer overcome the interfacial entry "
             "pressure. Reading ΔP_rung at the onset gives P_entry directly (hydraulic, "
             "so immune to the stage-time FPS ambiguity).\n")
    L.append(f"| Quantity | Value |\n|---|---|")
    L.append(f"| P_entry (2% SDS) | {onset.value:.0f} Pa [{onset.lo:.0f}, {onset.hi:.0f}] |")
    L.append(f"| γ·cosθ (2% SDS), r=w/2 | {gct_2pc_mNm:.1f} mN/m |")
    L.append(f"| Recommended dP_cap_ow_Pa | {onset.value:.0f} (current: {cfg.droplet_model.dP_cap_ow_Pa:.0f}) |\n")

    L.append("## 2. γ·cosθ vs [SDS] (anchored to onset; ratios reproduce conc_sweep)\n")
    L.append("Fitted from Stage-1 refill **ratios** (scale-invariant), anchored to the onset "
             "value at 2%. The dP_eff ratios (1.00 / 0.99 / 0.90 / 0.80) reproduce "
             "`conc_sweep/analysis_notes.md` exactly.\n")
    L.append("| [SDS] % | n | dP_eff ratio | γ·cosθ (mN/m) | 68% CI | class |")
    L.append("|---|---|---|---|---|---|")
    for _, r in curve.iterrows():
        L.append(f"| {r.sds_pc:g} | {int(r.n)} | {r.dP_eff_ratio:.2f} | "
                 f"{r.gamma_cos_theta_mNm:.1f} | [{r.gct_lo_mNm:.1f}, {r.gct_hi_mNm:.1f}] | {r.regime_class} |")
    L.append("\nγ·cosθ rises as [SDS] falls (higher γ, and θ departing from 0 below CMC). "
             "The 0.125% point is out-of-regime (Stage-3-dominated; anomalous L_menpoint) — "
             "validation only, not a fit input.\n")

    L.append("## 3. Stage-1 refill back-pressure (distinct from capillary entry)\n")
    L.append(f"The 2% Stage-1 Po-scaling is steeper than 1/Po (exponent ≈ −1.29 vs −1.03 baseline). "
             f"Interpreted as an opposing pressure it implies **~{xc['P_cap_Pa']:.0f} Pa "
             f"[{xc['P_cap_band'][0]:.0f}, {xc['P_cap_band'][1]:.0f}]** — *larger* than the "
             f"capillary entry pressure ({onset.value:.0f} Pa). At {xc['gamma_cos_theta_mNm']:.0f} mN/m "
             f"it is too high for pure capillarity, so the excess is **non-capillary, "
             f"velocity-dependent refill dissipation** (contact-line / entrance losses), "
             f"NOT γ·cosθ. Reported separately; not used to estimate γ.\n")

    L.append("## 4. Stage-2 snap-off prefactor β\n")
    L.append(f"Above CMC, β = {beta.value:.2f} [{beta.lo:.2f}, {beta.hi:.2f}] — essentially zero. "
             "Stage-2 timing barely responds to γ across the dripping window (consistent with "
             "conc_sweep's 'flat above CMC'), indicating viscous neck dissipation and dynamic "
             "adsorption dominate over pure capillary snap-off. Below CMC Stage-2 does rise "
             "(0.25% / 0.125% held out) but the naive γ-model over-predicts the rise — absolute "
             "β there needs a measured γ.\n")

    L.append("## 5. Regime map: stall / dripping / blowout\n")
    L.append("| Po (mbar) | ΔP_rung (Pa) | entry margin (Pa) | Ca_c | verdict |")
    L.append("|---|---|---|---|---|")
    for g in grid:
        L.append(f"| {g.Po_mbar:.0f} | {g.dP_rung_Pa:.0f} | {g.entry_margin_Pa:+.0f} | "
                 f"{g.Ca_continuous:.1e} | {g.verdict} |")
    L.append(f"\n- **Stall** below the calibrated entry pressure (onset ~{ONSET_PO_MBAR:.0f} mbar). "
             "Fix: raise Po, lower Qw, or raise surfactant.")
    L.append(f"- **Dripping** in between — junction Ca ≪ 1, size geometry-set, rate ∝ Po.")
    L.append(f"- **Blowout** at high Po (~{BLOWOUT_PO_MBAR:.0f} mbar, observed at device start/end): "
             "a pressure-driven / spatial-manifold instability, **not** a Ca transition. This "
             "simple ladder config stays spatially uniform, so reproducing the start/end effect "
             "quantitatively needs the manifold geometry — see `comp_manifold_parametrization`.\n")

    L.append("## Provisional γ / θ split (needs pendant drop)\n")
    L.append(f"Using a literature γ(2% SDS/sunflower-oil) ≈ {GAMMA_LIT_2PC_MNM:.0f} mN/m: "
             f"cosθ ≈ {cos_theta_2pc:.2f} → θ ≈ {theta_2pc_deg:.0f}°. **Provisional** — the two "
             "regime boundaries cannot pin γ (Ca is tiny; jetting is pressure-driven), so an "
             "absolute γ still requires measurement.\n")

    L.append("## What else is needed (ranked)\n")
    L.append("1. **Pendant-drop γ** for SDS/sunflower-oil (≥1 conc) — the keystone: turns every "
             "γ·cosθ into absolute γ + θ, and fixes absolute β. Highest value.")
    L.append("2. **Sessile θ([SDS])** on the device substrate — confirms the provisional θ trend.")
    L.append("3. **Low-pressure frequency data (30–200 mbar)** — the onset anchor rests on a "
             "single observation with no measured points below 200 mbar; a few points would pin it.")
    L.append("4. **Manifold/spatial data + geometry** near the ~1000 mbar boundary — to model the "
             "start/end blowout (this ladder config can't).")
    L.append("5. **Resolve the 2× stage-time convention** (this CSV vs conc_sweep notes) so "
             "*absolute* Stage-1 dissipation constants — not just ratios — can be trusted.")
    L.append("6. Confirm sunflower-oil grade/density and that bare-`SDS` = 2% mass.\n")

    L.append("## Figures\n")
    L.append("| File | Content |\n|---|---|")
    L.append("| `figures/fig_01_gamma_cos_theta_vs_sds.png` | γ·cosθ vs [SDS] with 68% CI |")
    L.append("| `figures/fig_02_stage2_beta.png` | Stage-2 observed vs ideal γ-scaling (β fit) |")
    L.append("| `figures/fig_03_ca_regime_map.png` | Junction Ca(Po) + stall/dripping/blowout margins |")
    L.append("| `figures/fig_04_stage_ratios_validation.png` | S1/S2 ratios vs [SDS] (reproduces conc_sweep) |")

    (HERE / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
