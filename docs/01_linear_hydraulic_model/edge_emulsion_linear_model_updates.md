
# Step / EDGE Emulsification Model Updates – Linear Model Improvements

## Purpose
This document summarizes the reasoning and proposed updates to the existing linear hydraulic model used to predict droplet production in a step‑emulsification / EDGE microfluidic device.

The goal is to improve prediction accuracy without immediately moving to a full time‑state simulation, while still incorporating the key physical mechanisms observed experimentally.

---

# 1. Correct Pressure Condition for DFU Activation

The original model assumed a DFU becomes active when:

Po > Pcap

However the correct physical condition is based on the local pressure difference across the interface:

ΔP_local = Po(local) − Pw(local)

The DFU activates when:

ΔP_local > Pcap

Once activated, the viscous driving pressure available for flow is:

ΔP_visc = Po(local) − Pw(local) − Pcap

This corresponds to the idea that the system must “pay the capillary price” first before viscous flow can occur.

Thus the steady flow relation becomes:

Q_open = (Po(local) − Pw(local) − Pcap) / R_DFU

---

# 2. Observed Discrepancy in the Current Model

Experimentally:

• Droplet diameter predicted by the model matches measurements  
• Droplet frequency is overpredicted by ~5–6×

This implies that the predicted oil flow rate through each rung is too high, meaning the real system contains additional constraints not present in the steady model.

---

# 3. Observed Droplet Formation Cycle

Video observations show the droplet generation cycle consists of:

1. Droplet pinch‑off  
2. Meniscus retreat upstream into the DFU channel  
3. Refill phase (meniscus advances back to junction)  
4. Droplet balloon growth  
5. Neck formation  
6. Pinch‑off

The current linear model assumes continuous flow through the DFU, but in reality the cycle includes phases where droplet growth is not occurring.

---

# 4. Refill Volume Mechanism

After pinch‑off, the oil meniscus retreats a distance L.

Before the next droplet can form, the meniscus must advance back to the junction edge.

This requires displacing a volume of continuous phase equal to:

V_refill = A_channel × L

Where

A_channel = DFU cross‑sectional area

During this refill phase oil pushes the aqueous phase ahead of it.

This introduces an additional per‑cycle volume requirement beyond the droplet volume.

---

# 5. Updated Linear Frequency Model (Refill Included)

The original model assumes:

T_cycle = V_drop / Q_open

Therefore

f = Q_open / V_drop

Including refill volume:

T_cycle = (V_drop + V_refill) / Q_open

Thus

f = Q_open / (V_drop + V_refill)

This provides a simple linear‑model correction that accounts for refill mechanics without requiring time‑resolved simulation.

---

# 6. Neck Formation and Pinch‑Off Resistance

During droplet pinch‑off the neck radius decreases significantly.

Because hydraulic resistance scales strongly with channel radius, the neck region can create a temporary very high resistance.

Even though the neck length is short, the reduction in radius can increase resistance dramatically.

However the more accurate way to represent this is not as a small extra resistance but as a short time period where the DFU is effectively blocked.

---

# 7. Blocked Time During Pinch‑Off

Introduce a cycle dead‑time term:

T_block

This represents the period during neck thinning and interface reset where effective oil flow is near zero.

Cycle time becomes:

T_cycle = (V_drop + V_refill) / Q_open + T_block

Thus the corrected frequency becomes:

f = 1 / ((V_drop + V_refill)/Q_open + T_block)

or equivalently

f = Q_open / (V_drop + V_refill + Q_open × T_block)

---

# 8. Connection to Duty Factor Concept

The model originally overpredicts droplet frequency by roughly 5–6×.

This is equivalent to saying the DFU is only effectively productive for a fraction of the cycle.

Define a duty factor:

φ = f_actual / f_steady

In the improved formulation:

φ = V_drop / (V_drop + V_refill + Q_open × T_block)

Thus the duty factor emerges naturally from refill and blocked‑time effects.

---

# 9. Experimental Observations Supporting This Model

Measured pressures required to hold the meniscus near the junction:

Qw = 1 mL/hr → Po ≈ 30 mbar  
Qw = 5 mL/hr → Po ≈ 50 mbar

This indicates that the local water pressure at the junction increases with Qw, and the correct activation condition must use:

Po(local) − Pw(local)

rather than Po alone.

Additionally droplet frequency increases gradually with oil pressure above the capillary threshold:

~30 mbar → meniscus pinned  
~50 mbar → rare droplets (~0.1 Hz)  
~100 mbar → robust droplet production

This suggests droplet generation onset is not a hard threshold, but increases progressively with available overpressure.

---

# 10. Recommended Linear Model Upgrade Path

1. Keep existing ladder hydraulic solver unchanged.
2. Use local pressure difference for DFU activation.
3. Compute steady rung flow:

Q_open = (Po(local) − Pw(local) − Pcap) / R_DFU

4. Compute refill volume:

V_refill = A_channel × L

5. Compute droplet volume:

V_drop = sphere approximation (or improved estimate)

6. Optionally include blocked time term.

7. Predict droplet frequency using:

f = Q_open / (V_drop + V_refill + Q_open × T_block)

---

# 11. Advantages of This Approach

This upgrade:

• Preserves the linear hydraulic solver  
• Introduces physically meaningful parameters (L and T_block)  
• Explains why frequency is overpredicted  
• Bridges the gap toward a future time‑state model

---

# 12. Future Model Extensions

The eventual full model would include:

• time‑dependent DFU conductance  
• droplet growth dynamics  
• neck formation physics  
• cycle‑resolved pressure evolution

However the refill‑volume + blocked‑time approach captures the dominant missing mechanisms while maintaining computational simplicity.

---

End of document.
