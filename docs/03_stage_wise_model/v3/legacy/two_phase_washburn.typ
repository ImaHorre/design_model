#set document(title: "Two-Phase Washburn Equation in a Rectangular Microchannel")
#set page(margin: 2cm, numbering: "1")
#set par(justify: true)
#set text(font: "New Computer Modern", size: 11pt)
#show math.equation: set text(size: 11pt)

#align(center)[
  #text(size: 16pt, weight: "bold")[Two-Phase Washburn Equation in a Rectangular Microchannel]
  
  #v(0.5em)
  #text(size: 11pt, style: "italic")[Full derivation from first principles]
]

#v(1em)
#line(length: 100%)
#v(1em)

= 1. Problem Setup

Consider a rectangular microchannel of width $w$, height $h$, and total length $L_"tot"$, with aspect ratio $alpha = h\/w <= 1$. Two immiscible, incompressible Newtonian fluids are present:

- *Fluid 1* (displacing fluid): viscosity $mu_1$, occupying length $x(t)$ from the inlet
- *Fluid 2* (displaced fluid): viscosity $mu_2$, occupying length $L_"tot" - x(t)$

The meniscus (fluid 1 / fluid 2 interface) is located at position $x(t)$. We seek $dot(x)(t) = v(t)$, the meniscus velocity.

*Assumptions:*
- Fully developed laminar (Stokes) flow in both fluid segments — quasi-steady approximation
- Flat plug interface: no deformation along the channel axis
- No thin film deposition on walls (complete displacement)
- Incompressible flow: volumetric flow rate $Q$ is spatially uniform at any instant
- Inlet open to atmosphere: $P_"in" = P_0 = 0$ (gauge)
- Outlet open to atmosphere: $P_"out" = 0$ (gauge), or closed — specified below

= 2. Viscous Resistance of a Rectangular Channel

For a circular tube, Poiseuille's law gives $Delta P = 8 mu L Q \/ (pi r^4)$. For a rectangle this must be corrected via the exact Stokes solution.

The pressure drop across a rectangular channel of length $L$, carrying a fluid of viscosity $mu$ at flow rate $Q$, is:

$ Delta P_"visc" = frac(mu L Q, w h^3) dot f(alpha) $

where the *geometric resistance factor* $f(alpha)$ from Shah & London (1978) is:

$ f(alpha) = 12 left[ 1 - frac(192 alpha, pi^5) sum_(n=1,3,5,...)^infinity frac(tanh(n pi \/ 2 alpha), n^5) right]^(-1) $

For practical use, the series converges after 3–4 terms. Limiting values:

$ f(1) approx 14.23 quad "(square)" $
$ f(alpha -> 0) -> 12 quad "(wide, shallow slit)" $

A compact single-term approximation valid for $0 < alpha <= 1$:

$ f(alpha) approx frac(12, 1 - 0.630 alpha) $

It is useful to define the *hydraulic resistance per unit length* for each fluid segment:

$ cal(R)_i = frac(mu_i dot f(alpha), w h^3) quad ["Pa" dot "s" dot "m"^(-3)] $

so that the pressure drop across fluid segment $i$ of length $L_i$ carrying flow $Q$ is simply $Delta P_i = cal(R)_i L_i Q$.

= 3. Capillary Driving Pressure

The driving force is the Laplace pressure at the advancing meniscus (fluid 1 / fluid 2 interface). For a rectangular channel, the generalised Young–Laplace equation gives contributions from all four wetted walls. Assuming a uniform contact angle $theta_12$ between the two fluids on all walls:

$ Delta P_"cap" = gamma_12 cos theta_12 dot (frac(2, h) + frac(2, w)) dot frac(1, 2) dot 2 $

which simplifies to:

$ boxed(Delta P_"cap" = gamma_12 cos theta_12 left(frac(1, h) + frac(1, w)right)) $

where $gamma_12$ is the interfacial tension between fluids 1 and 2, and $theta_12$ is the contact angle of that interface on the channel walls (measured through fluid 2).

*Heterogeneous wall wettability:* In bonded microchips, the floor, ceiling, and sidewalls are often different materials (e.g. glass floor, PDMS sidewalls). In this case:

$ Delta P_"cap" = gamma_12 left[ frac(cos theta_"top" + cos theta_"bottom", h) + frac(2 cos theta_"sides", w) right] $

*Sign convention:* $Delta P_"cap" > 0$ drives fluid 1 into the channel (spontaneous imbibition). If $cos theta_12 < 0$, an external pressure must be applied.

*Note on the inlet interface:* If fluid 1 enters from a reservoir, a second meniscus (fluid 1 / air) exists at the inlet. Its capillary pressure contribution is:

$ Delta P_"inlet" = gamma_1 cos theta_1 left(frac(1, h) + frac(1, w)right) $

For cases where the inlet is submerged or the reservoir is large, $Delta P_"inlet" -> 0$ and can be neglected. The derivation below treats only the internal meniscus as the driver; add $Delta P_"inlet"$ to the right-hand side if relevant.

= 4. Pressure Balance (Quasi-Steady)

Under the quasi-steady assumption, inertia is neglected and the net driving pressure equals the total viscous dissipation at every instant:

$ Delta P_"cap" = Delta P_"visc,1" + Delta P_"visc,2" $

Substituting:

$ Delta P_"cap" = cal(R)_1 dot x(t) dot Q + cal(R)_2 dot (L_"tot" - x(t)) dot Q $

Since $Q = w h dot v(t) = w h dot dot(x)$:

$ Delta P_"cap" = left[ cal(R)_1 x + cal(R)_2 (L_"tot" - x) right] w h dot dot(x) $

Solving for the meniscus velocity:

$ boxed(v(t) = dot(x) = frac(Delta P_"cap", w h left[ cal(R)_1 x + cal(R)_2 (L_"tot" - x) right])) $

Expanding $cal(R)_i$:

$ boxed(dot(x) = frac(Delta P_"cap" dot w h^2, f(alpha) left[ mu_1 x + mu_2 (L_"tot" - x) right])) $

This is the *two-phase rectangular Washburn equation* for meniscus velocity.

= 5. Full ODE and Analytical Solution

== 5.1 The ODE

Rearranging into separated form:

$ left[ mu_1 x + mu_2 (L_"tot" - x) right] d x = frac(Delta P_"cap" dot w h^2, f(alpha)) d t $

Define the constant:

$ K = frac(Delta P_"cap" dot w h^2, f(alpha)) quad ["Pa" dot "m"^2] $

and expand the left-hand side:

$ left[ mu_2 L_"tot" + (mu_1 - mu_2) x right] d x = K d t $

== 5.2 Integration

Integrating from $x = 0$ at $t = 0$:

$ mu_2 L_"tot" x + frac(mu_1 - mu_2, 2) x^2 = K t $

This is the implicit solution $t(x)$. Inverting, the explicit solution for $x(t)$ is:

$ x(t) = frac(-mu_2 L_"tot" + sqrt((mu_2 L_"tot")^2 + 2(mu_1 - mu_2) K t), mu_1 - mu_2) quad (mu_1 != mu_2) $

For $mu_1 = mu_2 = mu$ (same viscosity), the equation reduces to the classical *Washburn result*:

$ x(t) = sqrt(frac(2 K t, mu)) = sqrt(frac(2 Delta P_"cap" w h^2, mu f(alpha)) dot t) $

recovering the characteristic $x proportional sqrt(t)$ scaling.

== 5.3 Meniscus Velocity from the Analytical Solution

Differentiating $x(t)$ with respect to time:

$ v(t) = dot(x) = frac(K, mu_2 L_"tot" + (mu_1 - mu_2) x(t)) $

which, when $x(t)$ is substituted from above, gives $v$ as an explicit function of time. In practice, solving numerically (e.g. Euler or RK4 on the ODE) is straightforward and avoids the square root singularity at $t = 0$.

= 6. Summary of the Governing Equation

Collecting all terms:

$ dot(x)(t) = underbrace(frac(gamma_12 cos theta_12 (1\/h + 1\/w), 1), "capillary driving pressure") dot underbrace(frac(w h^2, f(alpha)), "channel geometry") dot underbrace(frac(1, mu_1 x(t) + mu_2 (L_"tot" - x(t))), "cumulative viscous resistance") $

The key physical insights are:

- The driving pressure scales as $(1\/h + 1\/w)$, not $1\/r$ — both dimensions matter equally
- The resistance factor $f(alpha)$ corrects for the rectangular velocity profile; it is always $>= 12$, meaning a rectangle always has *higher* resistance than a slit of the same height
- The denominator grows linearly with $x$ when $mu_1 != mu_2$, so velocity is *not* simply $proportional 1\/sqrt(t)$ in the two-fluid case
- If $mu_1 < mu_2$ (less viscous fluid displacing more viscous), the denominator *decreases* with time and the meniscus *accelerates* — the opposite of single-fluid Washburn

= 7. Parameters and Notation

#table(
  columns: (auto, auto, auto),
  stroke: 0.5pt,
  inset: 6pt,
  [*Symbol*], [*Quantity*], [*Units*],
  [$w$], [Channel width], [m],
  [$h$], [Channel height ($<= w$)], [m],
  [$alpha = h\/w$], [Aspect ratio], [—],
  [$L_"tot"$], [Total channel length], [m],
  [$x(t)$], [Meniscus position], [m],
  [$v(t) = dot(x)$], [Meniscus velocity], [m/s],
  [$mu_1, mu_2$], [Dynamic viscosities], [Pa·s],
  [$gamma_12$], [Interfacial tension], [N/m],
  [$theta_12$], [Contact angle (through fluid 2)], [rad],
  [$f(alpha)$], [Shah & London resistance factor], [—],
  [$K$], [Lumped driving constant], [Pa·m²],
)

= 8. References

- Washburn, E.W. (1921). *The dynamics of capillary flow.* Physical Review, 17(3), 273.
- Shah, R.K. & London, A.L. (1978). *Laminar Flow Forced Convection in Ducts.* Academic Press.
- Berthier, J. & Silberzan, P. (2010). *Microfluidics for Biotechnology.* Artech House.
- Sauret, A. et al. (2019). Capillary flow in open microchannels. *Soft Matter.*
