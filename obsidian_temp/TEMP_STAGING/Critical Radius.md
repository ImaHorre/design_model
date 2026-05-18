# Critical Radius

*Geometry-dependent snap-off condition for Stage 2 droplet formation*

## Core Concept

**Definition**: Droplet radius at which snap-off occurs, determined by channel geometry and [[Surface Tension]] balance

**V3 Model Implementation**:
- **High aspect ratio** (w/h > 3): R_crit ≈ 0.7 × h (height-limited)
- **Normal aspect ratio**: R_crit ≈ 0.7 × √(w×h) (geometric mean)
- **Low aspect ratio** (w/h < 0.3): R_crit ≈ 0.7 × w (width-limited)

## Key Connections

**[[Stage 2 Physics]]**:
- Determines droplet formation timing and final size
- Less sensitive to [[Nodal Network]] pressure variations
- Geometry-controlled mechanism

**[[Device Geometry]]**:
- Channel dimensions directly control R_crit
- Aspect ratio scaling laws for different geometries
- Design parameter for droplet size control

**[[Pressure Variables]]**:
- P_j influences approach to critical radius
- Critical radius achieved when capillary forces balance viscous forces
- Snap-off timing depends on critical radius achievement

**Experimental Connections**:
- [[V5.30 Data]] Stage 2 timing uniformity
- Droplet size consistency across device positions
- Geometry scaling validation studies

---

**Related**: [[Stage 2 Physics]] | [[Device Geometry]] | [[Surface Tension]] | [[Droplet Size Control]]