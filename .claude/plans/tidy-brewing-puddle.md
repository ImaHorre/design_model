# Obsidian Documentation Plan for Numerical Model Project

## Context

This plan addresses the need to document the current thought process and conceptual understanding of the v3 stage-wise numerical model. The goal is to create clear, interconnected conceptual documentation that builds upon existing notes (like "Droplet generation stage timings") while streamlining ideas and directing research focus. The model is still in development, so emphasis is on conceptual understanding rather than user instructions or detailed implementation mechanics.

The numerical model conceptualizes droplet generation in microfluidic devices using a two-stage physics approach:
- **Stage 1**: Oil meniscus movement from reset position to junction edge (hydraulic flow driven)
- **Stage 2**: Droplet bulb formation, necking, and pinch-off (geometry and surface tension driven)

This is built on top of a nodal network analysis framework that models the entire fluidic system as pressure, flow, and resistance networks.

## Proposed Obsidian Documentation Structure

**Note**: All new notes will be created in a temporary staging folder (`03_Research/Numerical Model/TEMP_STAGING/`) for review before integration into the main vault structure.

### Priority Phase 1: Core Physics Concepts

#### 1. **Two-Stage Physics Integration and Extensions.md**
**Purpose**: Build upon existing [[Droplet generation stage timings]] note with v3 conceptual advances
**Content**:
- Reference and extend existing stage timing work (avoid duplication)
- New v3 insights: DP_rung vs P_j pressure variable distinction
- Advanced conceptual connections to nodal network pressure distributions
- Integration of experimental V5.30 correlations with v3 physics framework
- Focus on conceptual advances not already covered in existing notes
**Links to**: [[Droplet generation stage timings]], [[Nodal Network Framework]], [[Pressure Variables]]

#### 2. **Nodal Network Conceptual Framework.md**
**Purpose**: Foundational thinking about device-scale hydraulic modeling
**Content**:
- Device as distributed pressure/flow network concept
- Ladder-network physics intuition (two parallel channels, connecting rungs)
- How local DFU conditions emerge from global network behavior
- Conceptual bridge between design parameters and local operating conditions
**Links to**: [[Device Geometry]], [[Pressure Distribution]], [[Network Physics]]

#### 3. **Pressure Variable Physics Distinction.md**
**Purpose**: Key conceptual breakthrough in separating Stage 1 vs Stage 2 driving forces
**Content**:
- DP_rung (pressure difference across rung) drives Stage 1 refill physics
- P_j (preneck junction pressure) drives Stage 2 droplet formation
- Why this distinction matters for physics accuracy
- Conceptual connection to experimental timing variations
**Links to**: [[Two-Stage Physics]], [[Experimental Validation]], [[Pressure Variables]]

### Priority Phase 2: Conceptual Background and Connections

#### 4. **Microfluidic Flow Regime Concepts.md**
**Purpose**: Fundamental physics concepts underlying the model
**Content**:
- Capillary number as key dimensionless parameter
- Dripping vs jetting regime conceptual boundaries
- Role of geometry, viscosity, and surface tension in regime transitions
- Connection between regimes and droplet formation mechanisms
**Links to**: [[Surface Tension]], [[Device Design]], [[Flow Regimes]]

#### 5. **Surface Effects and Wetting Conceptual Framework.md**
**Purpose**: Surface chemistry connections to droplet formation physics
**Content**:
- Dynamic contact angle effects on meniscus movement (Stage 1 connection)
- Surface tension variations and their impact on critical radius (Stage 2 connection)
- Surfactant effects on both wetting dynamics and necking physics
- Why surface effects explain Stage 1 "slowdown" observations (~3-5× factor)
**Links to**: [[Contact Angle]], [[Fluid Formulation]], [[Surface Effects]]

#### 6. **Device Geometry and Physics Scaling Concepts.md**
**Purpose**: How device design parameters connect to physics performance
**Content**:
- Rung geometry influence on resistance and droplet size
- Channel aspect ratio effects on pressure distribution uniformity
- Scaling laws connecting device size to operating conditions
- Geometric control of Stage 1 vs Stage 2 timescale separation
**Links to**: [[Device Designs]], [[Manufacturing]], [[Geometry Scaling]]

### Supplementary Conceptual Notes

#### 7. **V3 Model Evolution and Key Insights.md**
**Purpose**: Conceptual journey and resolved physics understanding
**Content**:
- Key conceptual breakthroughs from v2 to v3 (11 resolved physics issues)
- Why modular physics approach emerged as necessary
- Deferred concepts and future research directions
- Lessons learned about physics modeling approach
**Links to**: [[Model Evolution]], [[Research Priorities]], [[Physics Breakthroughs]]

#### 8. **Experimental Validation Conceptual Framework.md**
**Purpose**: How experimental observations validate and guide conceptual understanding
**Content**:
- V5.30 Flow-stage_timings.xlsx key insights and what they reveal about physics
- DFU position effects and their connection to network pressure concepts
- Experimental-theoretical feedback loop in model development
- Areas where experiments reveal physics gaps
**Links to**: [[V5.30 Data]], [[Flow-stage timings]], [[Model Validation]]

#### 9. **Research Directions and Conceptual Frontiers.md**
**Purpose**: Forward-looking conceptual development priorities
**Content**:
- Surface activation mechanisms and Stage 1 physics refinement
- Predictive neck instability concepts for Stage 2 enhancement
- Multi-device interaction and system-level effects
- Integration with process optimization conceptual framework
**Links to**: [[Research Projects]], [[Development Priorities]], [[Physics Frontiers]]

## Implementation Strategy

### Staging Approach
**All new notes created in**: `03_Research/Numerical Model/TEMP_STAGING/`
- Allows inspection and revision before integration
- Preserves existing vault structure and notes
- Enables iterative refinement of conceptual framework

### Conceptual Integration Principles
- **Build upon existing work**: Reference and extend current stage timing notes rather than replacing
- **Maintain conceptual focus**: Emphasize understanding over implementation details
- **Cross-link thoughtfully**: Connect related concepts while avoiding information overload
- **Support research direction**: Help streamline thinking and focus development efforts

### Writing Approach
- **Engineering-level depth**: Key principles and relationships without full mathematical derivations
- **Conceptual clarity**: Clear explanations accessible to broader team while maintaining technical accuracy
- **Research-oriented**: Support ongoing model development rather than end-user documentation
- **Experimental connection**: Always link concepts back to observable phenomena and data

## Cross-linking and Organization Strategy

### Wiki-style Linking System
- Use `[[Note Name]]` format for all cross-references rather than hashtags
- Create "node notes" as conceptual connectors (e.g., [[Contact Angle]], [[Surface Tension]]) that may contain minimal content but serve as linking hubs
- Node notes act as conceptual bridges between detailed content notes
- Enable easy navigation between related concepts without rigid hierarchical structure

### Cross-linking Strategy
- Each conceptual note links to relevant existing notes via `[[Existing Note Name]]`
- Physics concepts connect through node notes (e.g., [[Contact Angle]] links [[Stage 1 Physics]] to [[Surface Effects]])
- Create conceptual maps through interlinking rather than categorical tagging
- Node notes allow flexible relationship mapping between concepts

## Quality and Integration Protocol

### Content Development and Duplication Prevention
- **Critical: Avoid duplication**: Carefully review existing [[Droplet generation stage timings]] content before creating any new notes
- **Build upon existing work**: Reference and extend current notes rather than repeating concepts
- **Reorganize, don't repeat**: If concepts overlap, reorganize existing content with better cross-linking rather than duplicating
- **Node-based organization**: Create minimal "node notes" ([[Contact Angle]], [[Surface Tension]], etc.) that serve as linking hubs without detailed content
- Extract conceptual insights from v3 authoritative documents without implementation details
- Emphasize physical understanding over mathematical formulation
- Connect concepts to experimental observations and research directions
- Maintain focus on thought process streamlining rather than user instruction

### Review and Integration Process
1. Create all notes in TEMP_STAGING folder
2. User review and feedback on conceptual content and organization
3. Refinement based on feedback
4. Integration into main vault structure with proper linking
5. Update of existing notes with cross-references to new conceptual framework

This approach ensures that conceptual understanding is captured and organized effectively while supporting ongoing research and development priorities without disrupting existing documentation or prematurely documenting implementation details.