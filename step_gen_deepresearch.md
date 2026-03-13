# Alternative Droplet Generation Mechanics in Step-Emulsification and EDGE Systems

## Executive summary

Your two internal documents frame droplet generation in your **step-emulsification (STE) microfluidic device** as a **two-dominant-stage cycle**: a **hydraulically controlled confined displacement stage** (strongly dependent on inlet oil pressure \(P_o\)) followed by a **capillary-controlled droplet growth/necking stage** (weakly dependent on \(P_o\)); pinch-off is assumed “fast” and negligible in the timing budget. fileciteturn0file0 fileciteturn0file1

Deep literature review shows that this “hydraulic + capillary” decomposition is strongly consistent with multiple **peer-reviewed step-emulsification models** and data, but the literature also contains **at least four alternative explanations** for a pressure-sensitive “Stage 1” besides *pure channel hydraulics*: (i) **continuous-phase backflow/“gutter” refilling** driven by curvature/pressure imbalance (a central mechanism in confinement-gradient and step devices), citeturn6view0turn3view0 (ii) **surfactant adsorption/dynamic interfacial tension (Marangoni-enabled) lag** that delays meniscus motion in spontaneous/EDGE devices, citeturn39view0 (iii) **collective effects** (droplet crowding, droplet–droplet interactions, boundary-layer-like hydraulic coupling) that introduce new time scales and regimes in arrays, citeturn6view2turn41view0 and (iv) **jetting/dripping regime changes** controlled by local \(\mathrm{Ca}\), \(\mathrm{We}\), geometry (\(w/h\)) and dynamic pressure stabilization, which can suppress breakup or dramatically alter sizes/frequencies. citeturn3view0turn43search0

For droplet size, many step-emulsification experiments and simulations show a **geometry-dominated droplet size** (often \(d \sim \mathcal{O}(h)\)) within a low-\(\mathrm{Ca}\) dripping regime, with transitions to jetting at higher \(\mathrm{Ca}\) or unfavorable geometry. citeturn6view2turn3view0turn37view1 EDGE devices (edge-based droplet generation) exhibit **pressure stability windows** and droplet sizes scaling primarily with plateau height, but are extremely sensitive to **wettability and surface/interface interactions**. citeturn35view0turn41view1

The most discriminating near-term path is a **targeted experiment set** that separates (a) hydraulic refilling vs (b) curvature-driven backflow vs (c) adsorption/dynamic-\(\gamma\) lag vs (d) regime transition/jetting vs (e) electric-field effects. A prioritized *8-experiment plan* is provided below with expected outcomes for each competing theory.

## Authoritative inputs from your two documents

### What is specified and should be treated as given

Both documents describe a step-emulsification system with many parallel high-resistance channels feeding a step into a reservoir and assert a **three-stage physical picture**: fileciteturn0file0

- **Stage 1 (Confined displacement)**: meniscus/interface motion in a high-resistance confined channel, dominated by hydraulic resistance and interfacial/meniscus dynamics; **strong dependence** on inlet oil pressure. fileciteturn0file0
- **Stage 2 (Bulb growth + necking)**: once oil reaches the step, a bulb grows and necks; droplet pressure set by Laplace pressure \(P_{drop}=P_w+2\gamma/R\); as \(R\) increases, Laplace pressure decreases, increasing the driving pressure into the droplet → “accelerating growth”; **weak dependence** on inlet pressure. fileciteturn0file0turn0file1
- **Stage 3 (Pinch-off)**: rapid, capillary-instability-driven, negligible duration. fileciteturn0file0turn0file1
- A key modeling assumption in the “ideas” document is that **junction pressure \(P_j\) is roughly constant** when \(P_o\) changes because most pressure drop occurs along the long narrow channel. fileciteturn0file1
- The suggested practical implication is a **capillary-limited maximum frequency**: increasing \(P_o\) beyond a point only shortens Stage 1, while Stage 2 sets an upper limit. fileciteturn0file1

### What is *not* specified (must be treated as unknown)

Your documents **do not specify** (so this report treats them parametrically): channel cross-section dimensions, step height, terrace/plateau geometry, channel length distribution, number of channels/nozzles, fluid viscosities/densities, interfacial tension, surfactant formulation and adsorption kinetics, contact angle/wettability, continuous-phase flow profile near the step (quiescent vs crossflow), applied electric field/voltage/current (if any), or measured droplet size/frequency ranges. fileciteturn0file0turn0file1

## Literature synthesis of step-emulsification and EDGE droplet formation

Step emulsification and EDGE devices are typically categorized as **spontaneous/interfacial-tension-driven** droplet generators, contrasted with shear-driven junctions (T-junction, flow focusing) where both phases’ flow rates strongly set size. citeturn3view2turn37view1 The literature broadly supports the key empirical hallmark you are leveraging: **droplet size can be weakly dependent on flow rate over a sizable operational window**, which is exactly why these devices are attractive for massive parallelization. citeturn37view1turn3view3

### Quasi-static curvature/geometry mechanism for step emulsification

A foundational and widely cited theoretical framework is that step emulsification is triggered when a **quasi-static curvature balance becomes impossible** between the confined tongue in the inlet and the expanding “bulb” downstream. Dangla et al. (J. Phys. D, 2013) propose a geometric model: confinement imposes a minimum achievable curvature upstream, while bulb curvature decreases with bulb size; beyond a critical bulb radius \(R^\*\), static equilibrium is lost and the system “collapses” into a droplet. citeturn28view0

This model also predicts that the detached droplet size is **bounded from below** (set by geometry) and increases **slowly** with flow rate due to additional volume injected during a finite necking time; the paper explicitly discusses how “necking time” converts flow rate into extra drop size. citeturn28view0

### Backflow of continuous phase and “gutter” refilling as a breakup trigger

A closely related but more explicitly hydrodynamic mechanism appears in confinement-gradient devices and is directly connected to step emulsification. Dangla et al. (PNAS, 2013) show that when the downstream tongue curvature drops below a confinement-limited threshold, Laplace pressure imbalance can drive **reverse flow of the continuous phase into the corners/gutters**, inducing necking upstream and eventual rupture (with Rayleigh–Plateau invoked once the thread becomes sufficiently slender). citeturn6view0

Independent 3D time-dependent simulations (Montessori et al., published as Phys. Rev. Fluids 2018; accessible preprint) similarly point to (i) an **adverse pressure gradient** that drives continuous-phase backflow into the nozzle and (ii) **jet striction** and rupture, and argue that rupture can be delayed/suppressed at higher flow speeds via **dynamic pressure stabilization**, motivating a dripping–jetting criterion needing \(\mathrm{Ca}\) plus \(\mathrm{We}\) or \(\mathrm{Re}\). citeturn3view0

### Necking-time scaling and maximum production rate concepts

Experiments on step emulsification arrays (Mittal et al., Phys. Fluids 2014) identify the **necking time** as an intrinsic timescale governing drop formation and find it scales mainly with **outer viscosity to interfacial tension**, with a smaller correction from viscosity ratio, i.e. a form \(\tau_n \sim (1+\alpha \eta_i/\eta_o)\eta_o/\gamma\). citeturn6view2 They also describe a **transition** in fragmentation regime linked to a critical ratio of necking time to overall period, implying a practical **maximum production rate** for “small-drop” operation. citeturn6view2

Related work on breakup at the end of rectangular tubes (Crestel et al., Phys. Rev. Fluids 2019) reports (i) a low-flow regime where drop size varies slowly with flow rate and connects to pinching time, and (ii) a transition at a critical capillary number, with strong sensitivity to tube aspect ratio because the forming drop can hinder continuous-phase counterflow for low aspect ratios. citeturn19view0

### Co-flow / Hele–Shaw models and “critical capillary number” transition

For configurations with **co-flowing outer phase** and quasi-2D (Hele–Shaw) confinement, Li et al. develop a depth-averaged (Hele–Shaw) model and report a simple critical condition of the form \(\mathrm{Ca}^\* (w/b)=\text{const}\) for transition, and provide closed-form droplet size predictions in step-emulsification regimes. citeturn34view0 This is important because your system includes a water flow rate input \(Q_w\) (unspecified magnitude), so crossflow/shear may not be negligible. fileciteturn0file0

### EDGE devices: pressure windows, wettability, adsorption kinetics, and collective effects

EDGE (edge-based droplet generation) is explicitly distinguished from multi-nozzle microchannel emulsification (MCE): EDGE uses a **single very wide, shallow nozzle/plateau** where many droplets form simultaneously along an edge. citeturn3view3turn40search3

EDGE devices are often described in terms of **pressure windows**: a breakthrough pressure (formation begins) and a blow-up pressure (monodispersity fails). For example, a Scientific Reports study derives the invasion pressure from Young–Laplace considerations and reports that, in their regime, **droplet diameter scales with plateau height by a factor of \(\sim 6\)** at high viscosity ratio; it also shows that successful emulsification depends critically on **continuous-phase wetting** and on surfactant/protein adsorption to the solid surface (surface can be displaced or protected depending on chemistry). citeturn35view0turn3view2

Partitioned EDGE devices add geometry to improve pressure stability and can exhibit **two monodisperse regimes with distinct droplet sizes**. citeturn41view1turn41view0 A detailed Scientific Reports (2019) paper argues that (i) for “small droplets,” **continuous-phase inflow** into the droplet formation unit strongly affects droplet size and blow-up pressure, and (ii) for “large droplets,” monodispersity can arise from a **cascade of physical interactions between neighboring droplets** (a collective mechanism). citeturn41view0

Finally, a Lab on a Chip (2022) EDGE-based tensiometry paper provides an especially relevant alternative to your Stage 1: it decomposes each formation cycle into a **pore filling stage** and a **necking stage**, and in the *low-pressure regime* the pore-filling stage can be dominated by a **surfactant adsorption lag time** that must reduce dynamic \(\gamma(t)\) (and therefore Laplace pressure) before the meniscus can advance. citeturn39view0 This is a clear, experimentally grounded precedent for a “Stage 1 dominated by interfacial kinetics rather than hydraulic advection.”

## Alternative theoretical models and comparison to your proposed mechanism

This section enumerates plausible models that could reproduce similar phenomenology to your stage-flow concept, and then compares them directly.

### Competing models in a compact comparison table

Key dimensionless groups used below (definitions are standard; included here so your modeling can remain parametric):

- Reynolds: \(\mathrm{Re}=\rho U L/\mu\)
- Capillary: \(\mathrm{Ca}=\mu U/\gamma\) (specify which phase viscosity is used depending on model)
- Weber: \(\mathrm{We}=\rho U^2 L/\gamma\)
- Ohnesorge: \(\mathrm{Oh}=\mu/\sqrt{\rho \gamma L}\)
- Bond: \(\mathrm{Bo}=\Delta\rho g L^2/\gamma\) (gravity relevance; used explicitly in step theory) citeturn28view0
- Péclet: \(\mathrm{Pe}=v h/D\) (advection vs diffusion for surfactant transport; used explicitly for EDGE analysis) citeturn41view0
- Electric capillary number (one common form): \(\mathrm{Ca}_E \sim \epsilon E^2 L/\gamma\) (electric vs capillary stress; frequently used in EHD droplet/jet regimes) citeturn2search22turn36view0

| Model class | Governing physics | Key dimensionless control knobs | Typical regime / signature | Droplet size scaling (representative) | Frequency / timing scaling (representative) |
|---|---|---|---|---|---|
| Hydraulic + capillary two-stage (your “ideas”) | Stage 1 set by upstream hydraulic resistance and (assumed) nearly constant \(P_j\); Stage 2 set by Laplace pressure evolution in bulb/neck | \(\mathrm{Ca}\) (in-channel), geometry ratios, \(\mathrm{Bo}\) if gravity, wetting/contact angle (implicit) | Strong \(T_{disp}(P_o)\), weak \(T_{growth}(P_o)\), saturation of \(f(P_o)\) | Not specified in docs; expects geometry-dominated baseline and possible weak flow-rate dependence | \(T_{cycle}\approx T_{disp}(P_o)+T_{growth}\) with \(T_{disp}\downarrow\) strongly as \(P_o\uparrow\) fileciteturn0file0turn0file1 |
| Quasi-static curvature / equilibrium-loss (Dangla J. Phys. D 2013) | Curvature equilibrium must hold everywhere; confinement imposes minimum curvature upstream; bulb curvature decreases with growth → loss of equilibrium at \(R^\*\) | Geometry (step height, inlet height), \(\mathrm{Bo}\) assumed small; non-wetting with lubricating film | Critical bulb radius \(R^\*\) triggers collapse; predicts lower bound on drop size | \(R^\*\) set by geometry; final size \(R_\infty\ge R^\*\) and increases slowly with flow via volume injected during necking; discusses \((R_\infty-R^\*)\sim Q^{1/2}\) scaling assumption citeturn28view0 | Necking-time-mediated inflation adds flow dependence; quasi-static part predicts weak flow-rate sensitivity except through necking interval citeturn28view0 |
| Curvature-driven continuous-phase backflow / gutter refilling (Dangla PNAS 2013; Montessori PRF 2018) | Laplace pressure imbalance drives continuous phase into corners/gutters or back into nozzle; this striction induces rupture; dynamic pressure can stabilize at high speed | \(\mathrm{Ca}\), \(\mathrm{We}\), geometry, viscosity ratio; local pressure gradients | Observable backflow patterns and jet striction inside confined region; dripping–jetting transition depends on \(\mathrm{Ca}\) and inertia measures | Step emulsification often yields \(d/h\sim\) constant in dripping; simulations report \(d/h\sim4\) in a low-\(\mathrm{Ca}\) region citeturn3view0 | Breakup can be delayed/suppressed as flow speed increases (dynamic pressure stabilization), altering frequency and potentially producing jetting citeturn3view0turn43search0 |
| Viscocapillary necking-time control (Mittal Phys. Fluids 2014; Crestel PRF 2019) | A characteristic necking time \(\tau_n\) governs droplet formation; scales with \(\eta_o/\gamma\) (outer viscosity/interfacial tension), with viscosity ratio corrections; geometry sets baseline size | \(\mathrm{Ca}\) (inner or outer), viscosity ratio \(\lambda=\eta_i/\eta_o\), aspect ratio | Predicts intrinsic “speed limit” (max small-drop rate) and regime transition where drop size and \(\tau_n\) jump | Mittal reports droplet diameter roughly \(\sim 4h\) (order-of-magnitude) with inflation modifying size at higher flow citeturn6view2 | \(\tau_n\sim(1+\alpha\lambda)\eta_o/\gamma\) sets minimum \(T\); critical period/transition depends on \(\lambda\) citeturn6view2turn19view0 |
| Co-flow / Hele–Shaw tongue focusing (Li et al. 2014) | Depth-averaged (Hele–Shaw) hydrodynamics sets quasi-static tongue shape; transition when capillary focusing conditions fail; includes dependence on flow-rate ratio of phases | \(\mathrm{Ca}\), aspect ratio \(w/b\), flow-rate ratio (and viscosity ratio) | Three regimes described (step emulsification / balloon / jet-emulsification analogs); size robust across a range | Predicts droplet size \(d/b\) as a function of flow-rate ratio parameter; reports a transition criterion \(\mathrm{Ca}^\*(w/b)=\text{const}\) citeturn34view0 | Frequency can scale with flow while size stays ~constant in step regime (reported as a key “controllability” question) citeturn34view0 |
| EDGE pressure-window + wettability/surface interaction control (Sci Rep 2016) | Droplet start pressure from Young–Laplace; stable regime bounded by breakthrough/blow-up pressures; strong dependence on wettability and surfactant/protein adsorption to solid | Contact angle, \(\gamma\), viscosity ratio; geometry (plateau height) | Monodispersity only in a pressure window; failures often trace to wetting changes (oil films replacing surfactant layers) | Droplet diameter scales with plateau height (reported factor \(\sim 6\) at high viscosity ratio); droplet size weakly depends on \(\gamma\) but start pressure does citeturn35view0turn3view2 | Frequency linked to pressure stability window; wider stability allows higher frequency citeturn35view0 |
| Dynamic adsorption / Marangoni-limited “lag” (EDGE tensiometer, Lab Chip 2022) | Meniscus remains static until surfactant adsorption reduces \(\gamma_d(t)\) enough that Laplace pressure matches applied pressure; then flow proceeds; necking is fast | \(\mathrm{Pe}\) (transport), adsorption time scales, contact angle, applied \(\Delta P\) | Two-stage cycle: adsorption lag + pore flow; formation time approximates adsorption lag in low-pressure regime | Size may stay constant in low-pressure regime while time changes strongly with applied pressure and surfactant concentration citeturn39view0turn41view0 | Formation time dominated by surfactant-dependent lag \(\tau\) in low-pressure regime; \(t_{fill}\gg t_n\) citeturn39view0 |
| Electrohydrodynamic (EHD) tip streaming / cone-jet (Soft Matter 2020 review; Montanero & Gañán-Calvo review) | Maxwell electric stresses + capillarity + (often) leaky-dielectric charge transport → conical meniscus and thin jet emitting small droplets; distinct regime maps vs \(\mathrm{We}\) and \(\mathrm{Ca}_E\) | \(\mathrm{Ca}_E\), conductivity/permittivity ratios, charge relaxation times, \(\mathrm{Oh}\), \(\mathrm{We}\) | Charged droplets, measurable current; can produce orders-of-magnitude smaller droplets than nozzle scale | Scaling laws exist for droplet size and charge in EHD tip streaming and electrospray literature; reviews summarize regimes and scalings citeturn2search22turn36view0turn1search21 | Frequency and size can be tuned by electric field and flow; presence/absence of current and charging is diagnostic citeturn2search22turn36view0 |

### Agreements, contradictions, and missing predictions relative to your “ideas” mechanism

**Strong agreements (literature ⇄ your mechanism)**  
Your Stage 2 “capillary-controlled growth/necking” is consistent with:
- The quasi-static curvature/equilibrium-loss picture where geometry and Laplace pressure balance determine a critical bulb state. citeturn28view0
- The view that step emulsification is driven by Laplace-pressure differences at/near the step and that droplet size can be primarily geometry-controlled in a dripping regime. citeturn37view1turn3view0
- The idea of an intrinsic capillary/viscous timescale limiting maximum production rate (necking time \(\tau_n\sim \eta_o/\gamma\)). citeturn6view2turn19view0

**Key contradictions / alternative explanations you should explicitly rule in/out**  
Your Stage 1 is framed primarily as *hydraulic resistance controlled* and your “ideas” assume \(P_j\) changes little with \(P_o\). fileciteturn0file1 Literature suggests at least three mechanisms that can violate or complicate this:

- **Backflow and counterflow are not optional details** in many step/gradient-of-confinement models; they are central to the necking mechanism and can introduce their own time scales and dependencies. citeturn6view0turn3view0 If Stage 1 visually corresponds to “refilling/advancing,” it may actually be “refilling forced by backflow” rather than purely by upstream pressure-driven advection.
- **Dynamic interfacial tension (surfactant adsorption)** can dominate the “filling” part of a cycle in spontaneous devices: in low-pressure regimes, the lag time is set by adsorption needed to lower Laplace pressure. citeturn39view0 If your system uses surfactants (unspecified), this can masquerade as a hydraulic pressure dependence.
- **Collective multi-nozzle effects**: arrays can experience droplet crowding near outlets, extra hydraulic resistance, boundary-layer effects, and even cascade-like droplet–droplet interactions that generate new “regimes” and set times/frequencies. citeturn6view2turn41view0turn37view0

**Missing predictions you may want to add to your mechanism**  
To make your model discriminating (not just descriptive), the literature indicates you should add at least:

- A prediction for the necking time scaling \(\tau_n(\eta_o,\eta_i,\gamma)\) (even if semi-empirical), because it strongly affects both maximum frequency and drop inflation with flow. citeturn6view2turn19view0  
- A criterion for transition to **jetting (breakup suppressed)** based on local \(\mathrm{Ca}\) and possibly \(\mathrm{We}\) (dynamic pressure stabilization), because increasing \(P_o\) to “go faster” can push you into a different regime that breaks the assumed saturation picture. citeturn3view0turn43search0  
- A wettability/contact-angle dependence path, since both step and EDGE systems can fail or shift regimes when wall wetting changes. citeturn35view0turn39view0  

### Decision-tree diagram for model discrimination

```mermaid
flowchart TD
  A[Observed: droplet cycle has Stage 1 + Stage 2 timing] --> B{Any applied electric field? \n measurable current/charged droplets?}
  B -- Yes --> EHD[EHD cone-jet / tip streaming class\nCheck Ca_E, current, charge]
  B -- No / Unknown --> C{Droplet size ~ geometry and weakly depends on flow in dripping regime?}
  C -- Yes --> D{Does Stage 1 time change strongly with surfactant type/concentration?}
  D -- Yes --> ADS[Dynamic adsorption / Marangoni-limited lag\n(dynamic γ(t), Pe, adsorption τ)]
  D -- No --> H1[Hydraulic refilling / channel resistance dominated Stage 1]
  C -- No --> J{Evidence of jetting: long filament, satellites,\nloss of monodispersity above a threshold?}
  J -- Yes --> JET[Jetting / Rayleigh-Plateau breakup\nCheck Ca, We, w/h threshold]
  J -- No --> K{High-speed imaging shows continuous-phase backflow into nozzle / gutters?}
  K -- Yes --> BF[Curvature-driven backflow & striction\n(adverse pressure gradient)]
  K -- No --> COL{Array effects: droplet crowding / cascade interactions?}
  COL -- Yes --> ARR[Collective coupling (boundary layer, interactions)\nPartitioned EDGE-like behaviors]
  COL -- No --> QS[Quasi-static curvature equilibrium-loss model\n(geometry-driven snap-off)]
```

## Targeted experiments and measurements to discriminate models

The table below prioritizes **8 experiments** that, together, separate the most plausible competing mechanisms. Parameter ranges are suggested as *representative* because your actual geometry/fluids are unspecified; the idea is to map behavior in dimensionless terms where possible.

| Priority experiment | Practical setup notes | Expected outcome if “hydraulic + capillary stage” is correct | Expected outcome if **adsorption/dynamic \(\gamma(t)\)** dominates Stage 1 | Expected outcome if **backflow/continuous-phase counterflow** dominates | Expected outcome if **jetting/instability transition** dominates |
|---|---|---|---|---|---|
| Pressure sweep with stage-resolved timing | High-speed imaging near step; stage segmentation by interface position; sweep \(P_o\) over wide range (e.g., 0.1–5 bar if hardware allows) | \(T_{disp}\) decreases strongly with \(P_o\); \(T_{growth}\) ~ constant; \(f\) saturates at \(1/T_{growth}\) fileciteturn0file1 | Strong dependence of “Stage 1” on surfactant concentration/type even at fixed \(P_o\); “Stage 1” resembles lag before meniscus motion citeturn39view0 | Stage timing correlates with onset/extent of backflow features in imaging; may not fit simple \(1/P_o\) scaling citeturn6view0turn3view0 | Above critical \(P_o\) (or \(\mathrm{Ca}\)), regime change: filaments/jetting, polydispersity, loss of saturation picture citeturn3view0turn37view1 |
| Interfacial tension sweep (surfactant concentration/type) | Use tensiometer or inferred \(\gamma\); keep viscosities fixed; vary SDS/Tween/protein where relevant | \(T_{growth}\) scales inversely with \(\gamma\) if capillary-controlled; droplet size baseline stays geometry-linked | Stage 1 time changes dramatically with surfactant (adsorption kinetics), strongest at low pressures; dynamic-\(\gamma\) signatures citeturn39view0 | Backflow persists but may shift thresholds as \(\gamma\) changes (curvature imbalance) citeturn6view0turn28view0 | Critical \(\mathrm{Ca}\) / onset of jetting shifts with \(\gamma\) via \(\mathrm{Ca}=\mu U/\gamma\) |
| Outer-phase viscosity sweep | Add glycerol in water; track \(\eta_o\) and keep \(\gamma\) as constant as possible | \(T_{growth}\propto \eta_o/\gamma\) (necking-time scaling) citeturn6view2turn19view0 | If adsorption-lag dominates, viscosity affects pore-flow substage but lag remains surfactant-controlled | Counterflow/backflow and vortical patterns may strengthen/weaken; critical \(\mathrm{Ca}^\*\) may shift slightly | Jetting threshold shifts through \(\mathrm{Ca}\), \(\mathrm{Oh}\) |
| Junction pressure measurement \(P_j(t)\) | Add micro pressure sensor at manifold/junction or infer from flow+calibrated resistance; high bandwidth if possible | \(P_j\) weakly dependent on \(P_o\) across range; \(P_j(t)\) oscillations bounded fileciteturn0file1 | If adsorption lag dominates, you may see long “flat” periods where \(P_j\) stays below required Laplace until sudden motion | Backflow model predicts pressure transients tied to adverse gradients and backflow onset citeturn3view0turn6view0 | Jetting regime shows markedly different \(P_j(t)\) structure, possibly higher mean due to dynamic pressure |
| High-speed imaging of necking (≥50–200 kfps) | Similar to step emulsification wetting studies; focus on neck radius vs time | Neck-thinning resembles viscocapillary pinch-off, with “fast” Stage 3; can estimate \(\tau_n\) | Adsorption-lag model: necking may remain fast and similar across conditions; time shifts mostly pre-necking | Expect visible continuous-phase intrusion and striction preceding rupture; neck may form upstream of step citeturn6view0turn3view0 | In jetting, necking may occur far downstream; satellite drops possible; pinch-off physics shifts to jet breakup (Rayleigh–Plateau) |
| Micro-PIV / tracer flow mapping near step | Seed continuous phase; micro-PIV or streakline imaging in reservoir and in nozzle entrance | If Stage 1 is hydraulic advance of dispersed phase, continuous-phase near-step flow should be comparatively passive | Adsorption-lag: minimal flow during lag, then sudden motion; strong coupling to interface motion | Direct signature: continuous-phase **backflow into nozzle/gutters**, vortices near meniscus (reported in related geometries) citeturn6view0turn19view0 | Jetting shows sustained high-speed core flow and different outer-phase circulation |
| Continuous-phase flow rate \(Q_w\) sweep | Vary water crossflow/shear while holding \(P_o\) fixed | Weak effect on droplet size in spontaneous regime; may mainly clear droplets | Adsorption-lag: crossflow can enhance surfactant transport (convective adsorption) and shorten lag citeturn39view0turn41view0 | Strong crossflow changes counterflow patterns and detachment thresholds | Shear can switch breakup mode; if droplet size becomes strongly \(Q_w\)-dependent, you’re in a shear-assisted regime |
| Geometry perturbation / nozzle aspect ratio study | Fabricate/test a few \(w/h\), step heights; micro-CT or profilometry for actual dimensions | Should preserve two-stage timing form; Stage 2 sets ceiling if still dripping | Adsorption-lag persists but scales with meniscus curvature and surface area | Backflow and breakup can disappear below critical \(w/h\) (~2.6 reported) citeturn43search0turn19view0 | Jetting/dripping transition boundary shifts strongly; monodispersity may fail for certain geometries |

### Theoretical scaling charts for your stage-based model

The following plots are **parametric illustrations** of your proposed timing law
\[
T_{cycle}(P_o)\approx T_{disp}(P_o)+T_{growth},
\]
showing how saturation (a maximum frequency) naturally emerges if \(T_{growth}\) is approximately pressure-independent. fileciteturn0file1

(See the two figures immediately above in this conversation: cycle time components vs pressure, and frequency vs pressure.)

## Recommended next steps for a rigorous, design-usable model

A predictive engineering model that remains faithful to your stage concept but can survive contact with competing theories usually needs three coupled layers:

First, formalize a **hydraulic network model** for your device (all channels + manifolds) that produces \(P_j(t)\) and per-nozzle flow rate \(Q_i(t)\) under an imposed inlet pressure \(P_o\). Your “ideas” already motivate this separation of \(P_o\), \(P_j\), and channel resistance. fileciteturn0file1 Pair this with measured (or CFD-derived) effective resistances in (i) single-phase oil flow and (ii) two-phase meniscus motion if the nozzle refill is two-phase.

Second, embed a **local droplet-formation law** at each nozzle that can switch between competing physics based on parameters:
- Quasi-static equilibrium loss gives a geometry-driven “trigger” condition \(R \to R^\*\). citeturn28view0
- A necking-time law \(\tau_n(\eta_o,\eta_i,\gamma)\) sets the minimum achievable period and the inflation correction with flow. citeturn6view2turn19view0
- A regime map in \((\mathrm{Ca},\mathrm{We},w/h)\) sets when breakup is suppressed or becomes jetting-like. citeturn3view0turn43search0

Third, add the two most common “hidden variables” that often break overly simple models in spontaneous devices:
- **Dynamic interfacial tension / adsorption kinetics** (and associated Marangoni stresses), which can dominate early-cycle timing in low-pressure conditions. citeturn39view0turn41view0
- **Collective coupling in arrays** (droplet boundary layers, crowding, neighbor interactions), which can create new monodisperse regimes or new bottlenecks. citeturn6view2turn41view0turn37view0

### Key primary sources and reviews cited

To support fast navigation, here are DOI/links in a code block (clickable citations appear throughout the report):

```text
Dangla et al., “The physical mechanisms of step emulsification,” J. Phys. D: Appl. Phys. 46, 114003 (2013). (PDF via Polytechnique) 
Mittal et al., “Dynamics of step-emulsification…,” Phys. Fluids 26, 082109 (2014). (PDF via LCMD/ESPCI)
Dangla et al., “Droplet microfluidics driven by gradients of confinement,” PNAS 110, 853–858 (2013). (PDF mirror)
Montessori et al., “Elucidating the mechanism of step-emulsification,” Phys. Rev. Fluids 3, 072202 (2018). (accessible preprint)
Li et al., “Step-emulsification in nanofluidic device,” arXiv:1405.1923 (2014). (PDF)
Crestel et al., “Emulsification with rectangular tubes,” Phys. Rev. Fluids 4, 073602 (2019). (PDF via LCMD/ESPCI)
Sahin & Schroën, “Partitioned EDGE devices…,” Lab Chip 15, 2486 (2015). (RSC landing)
Klooster et al., “Monodisperse droplet formation… partitioned EDGE,” Sci. Rep. 9:7820 (2019). (PDF)
Sahin et al., “Microfluidic EDGE emulsification… interface interactions,” Sci. Rep. 6:26407 (2016). (PDF)
Lab Chip (2022), “Capillary pressure-based measurement of dynamic interfacial tension in a spontaneous microfluidic sensor,” DOI:10.1039/D2LC00545J
Soft Matter review (2020), “Electrohydrodynamics of droplets and jets in multiphase microsystems,” DOI:10.1039/D0SM01357A
Montanero & Gañán-Calvo review preprint (2020), arXiv:1909.02073v2 (tip streaming, dripping/jetting, EHD, surfactants)
Eggers & Villermaux, “Physics of liquid jets,” Rep. Prog. Phys. 71, 036601 (2008). (PDF via Bristol)
```

