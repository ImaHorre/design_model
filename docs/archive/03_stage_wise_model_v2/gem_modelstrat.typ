#set page(paper: "a4", margin: 2cm)
#set text(font: "DejaVu Sans", size: 10pt)
#show heading: set text(navy)

= Simulation Plan: Microfluidic Step-Emulsification (STE) Model
*File Name:* `gem_plan.typ` \
*Objective:* Develop a Python-based Lumped Parameter Model (LPM) to simulate droplet generation frequencies and sizes in multi-channel devices.

---

== 1. Core Simulation Strategy
The agent should implement a **two-dominant-stage cycle** model that couples global device hydraulics with local interfacial physics. The simulation must solve for the time-dependent pressure at the nozzle junction ($P_j$) and use it to drive the interface motion.

== 2. Explicit Physical Insights (Constraints)
To ensure accuracy, the model must adhere to these specific findings:
- *Stage 1 (Filling):* Displacement is dominated by hydraulic resistance in the narrow channels and is strongly dependent on inlet pressure $P_o$.
- *Stage 2 (Growth):* Once the meniscus reaches the step, growth is driven by the decreasing Laplace pressure of the expanding bulb ($P_"drop" = P_w + 2 gamma / R$).
- *Breakup Trigger:* Rupture occurs when the bulb reaches a critical radius $R^*$, determined by the step height and geometry curvature limits (The Dangla Criterion).
- *Saturation Effect:* Total cycle time $T_"cycle" approx T_"disp" + T_"growth"$. As $P_o$ increases, $T_"disp" arrow 0$, but $T_"growth"$ remains relatively constant, creating a frequency ceiling.
- *Alternative Mechanisms:* - If surfactants are used, the agent should allow for an "adsorption lag" time $\tau$ where the meniscus remains static until $\gamma(t)$ drops.
  - The model should flag "Jetting" if the Capillary Number ($Ca$) exceeds a critical threshold based on nozzle aspect ratio.

== 3. Mathematical Framework

=== Stage 1: Meniscus Displacement Time
The time to refill the nozzle is modeled via Poiseuille resistance:
$ T_"disp" = (L times R_"hyd") / (P_o - P_j) $

=== Stage 2: Accelerating Bulb Growth
The volume growth rate is determined by the pressure difference across the junction:
$ (d V) / (d t) = (P_j - (P_w + (2 gamma) / R(t))) / R_"total" $

=== Necking and Inflation
The final droplet volume $V_f$ includes the volume at trigger $V^*$ plus the "inflation" volume added during the finite necking time $\tau_n$:
$ V_f = V^* + Q_"avg" times \tau_n $

== 4. Configurable Variables (User Inputs)

#table(
  columns: (1fr, 1fr, 2fr),
  inset: 6pt,
  align: horizon,
  [*Category*], [*Variable*], [*Description*],
  [Geometry], [$w, h, L, H_"step"$], [Nozzle and step dimensions.],
  [Fluids], [$\eta_o, \eta_w, \gamma$], [Viscosities and interfacial tension.],
  [Operating], [$P_o, Q_w$], [Oil inlet pressure and water crossflow.],
  [Kinetics], [$\tau_"ads"$], [Surfactant adsorption lag time (optional).],
)

== 5. Implementation Roadmap for Claude Code
1. *Define Hydraulics:* Calculate $R_"hyd"$ for rectangular channels based on aspect ratio $w/h$.
2. *Iterative Solver:* Use a `while` loop to track $V(t)$ during Stage 2 until $R(t) = R^*$.
3. *Regime Mapping:* Output a warning if $Ca$ or $We$ suggests a transition to jetting or backflow-driven polydispersity.
4. *Visualization:* Generate plots for $P_o$ vs. Frequency and Droplet Diameter vs. $P_o$.