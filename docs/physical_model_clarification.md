# Step-Emulsification Device – Hydraulic Model Clarification

## 1. Topology

The device consists of:

- An oil main channel (dead-end manifold)
- A water main channel (through-flow manifold)
- N identical microchannels ("rungs") connecting oil → water

Oil is injected at the upstream end of the oil rail.
Water is injected at the upstream end of the water rail.
All oil must exit the system by passing through the rungs into the water rail.

There is NO downstream oil outlet.

---

## 2. Oil Main Channel Boundary Condition

The oil rail is a dead-end manifold.

Physical condition at downstream end:

    Q_main_oil(N-2 → N-1) = 0

Which implies:

    P_oil[N-1] = P_oil[N-2]

This is a zero-flux (Neumann) boundary condition.

There is no Dirichlet pressure boundary at the oil outlet.

---

## 3. Water Main Channel Boundary Condition

Water rail is through-flow and exits the device.

At downstream end:

    P_water[N-1] = P_out

This is a fixed-pressure (Dirichlet) condition.

---

## 4. Mass Conservation

Oil inlet flow satisfies:

    Q_oil_in = Σ Q_rung[i]

Axial oil flow decreases monotonically along the rail:

    Q_main_oil(x) = Q_oil_in − Σ_{k ≤ i(x)} Q_rung[k]

At the downstream end:

    Q_main_oil(end) = 0

---

## 5. Ideal Uniform Case

If:
- All rungs have identical resistance
- ΔP_i is constant across device

Then:

    Q_rung[i] = constant
    Q_main_oil decreases linearly
    Last rung flow equals all other rungs
    Axial oil flow after final rung = 0

---

## 6. Reverse Flow Scenario

If water pressure rises locally such that:

    ΔP_i = P_oil[i] − P_water[i] < 0

Then reverse invasion can occur in that region.

This typically begins mid-device where:
- Oil pressure has decayed
- Water pressure has increased
- Rung resistance is high enough to amplify sensitivity

Reverse bands represent local violation of uniformity.

---

## 7. Implication for Solver

The mixed-BC solver must:

- Treat oil downstream end as zero-flux (Neumann)
- Treat water downstream end as fixed-pressure (Dirichlet)
- Ensure conservation: Q_oil_in = Σ Q_rungs
- Not artificially pin oil outlet pressure

Any future threshold/hysteresis model (Stage D onward)
must operate on top of this physically correct topology.