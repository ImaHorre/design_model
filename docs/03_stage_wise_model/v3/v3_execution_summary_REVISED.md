# Stage-Wise Model v3: Execution Summary

**Date**: March 13, 2026
**Status**: Ready for Implementation
**Total Estimated Timeline**: 8-12 weeks



We are implementing a controlled v3 update to the stage-wise model.

This is not a greenfield rewrite.

Preserve existing interfaces where practical and use previous code as reference, not authority.



\## Authoritative document order



When documents conflict, use this order:



1\. `stage\_wise\_v3\_consolidated\_physics\_plan\_REVISED.md`

2\. `stage\_wise\_v3\_implementation\_plan\_REVISED.md`

3\. `v3\_execution\_summary\_REVISED.md`

4\. previous v2 docs and existing codebase as reference only



Do not average conflicting physics assumptions across documents.

Do not reintroduce older assumptions if they conflict with the revised v3 physics plan.



\## Core v3 implementation rules



Baseline physics for initial implementation:



\- Stage 1 baseline is two-fluid Washburn refill

\- Stage 2 snap-off is controlled by `Rcrit`

\- Neck-state variables are tracked for diagnostics and warning logic only

\- Grouped rung simulation is required

\- Regime classification is warning/diagnostic logic and does not override baseline snap-off

\- Deferred extensions must not delay the first working implementation



Deferred extensions for later phases unless explicitly requested:



\- full mechanism auto-selection

\- predictive neck-instability snap-off

\- full adsorption kinetics

\- full dynamic hydraulic network

\- design optimization tooling



\## Phase execution protocol



Work strictly phase-by-phase according to:

`stage\_wise\_v3\_implementation\_plan\_REVISED.md`



For each phase:



1\. restate the phase objective

2\. inspect relevant existing code before editing

3\. implement only the scoped changes for that phase

4\. run targeted tests for that phase

5\. summarize:

&#x20;  - files changed

&#x20;  - tests run

&#x20;  - results

&#x20;  - unresolved issues

&#x20;  - recommended next step

6\. update the implementation plan doc with progress notes and results

7\. STOP and wait for explicit user continuation before starting the next phase



Do not continue automatically to the next phase.



\## Testing rules



After each phase:



\- run the smallest relevant test set first

\- then run any broader regression checks that are safe and fast

\- if tests fail, debug before proposing phase completion

\- do not declare a phase complete without reporting actual test results



Always distinguish:

\- implemented

\- partially implemented

\- not yet implemented



\## Documentation and progress logging



Use `stage\_wise\_v3\_implementation\_plan\_REVISED.md` as the main progress tracker.



For each completed phase, append a progress log section including:



\- date/time

\- phase name

\- summary of implementation

\- files modified

\- tests run

\- test outcomes

\- deviations from plan

\- follow-up risks or notes



Do not overwrite earlier plan content.

Append progress notes clearly under a dedicated progress log heading.



\## Code-change policy



Prefer minimal, controlled edits over broad rewrites.

Preserve backward compatibility where reasonable.

Avoid introducing speculative abstractions unless they are directly needed for the current phase.

Keep module boundaries clean and aligned with the revised implementation plan.



\## Existing codebase usage



Before implementing any phase:



\- inspect the current v2 code and surrounding utilities

\- identify reusable components

\- reuse stable working logic where it does not conflict with v3 physics

\- explicitly note where v3 departs from v2



\## Session hygiene



Use fresh context for each major phase if the session becomes noisy.

When switching to a substantially different task, consider clearing session context and re-reading this file plus the three v3 docs first.



\## Commands



Document and use the project’s actual test/build commands.

If commands are missing, find them from the repo before making assumptions.

## 📋 Complete Planning Package

### 1\. **Consolidated Physics Plan** ✅

**File**: `stage\_wise\_v3\_consolidated\_physics\_plan.md`

**What**: Unified physics modeling strategy combining:

* **11 Resolved Physics Issues** (critical decisions from step-by-step analysis)
* **4 Strategic v3 Improvements (now classified as deferred extensions unless explicitly enabled)** (competing mechanisms, outer-phase necking, multi-factor regime, design optimization)
* **Integrated physics architecture** ready for implementation

**Key Achievement**: Preserves ALL critical physics resolutions while providing coherent strategic improvements framework.

### 2\. **Implementation Plan** ✅

**File**: `stage\_wise\_v3\_implementation\_plan.md`

**What**: Phase-by-phase development roadmap that:

* **Implements resolved physics** in correct dependency order
* **Addresses v2 code review issues** (50KB file → modular architecture)
* **Provides validation framework** for each physics component
* **Maintains backward compatibility** with existing system

**Key Achievement**: Executable development plan with clear success criteria and risk mitigation.

\---

## 🎯 Critical Physics Decisions to Preserve

The following **11 resolved issues** are the foundation of v3 and must be implemented exactly as resolved:

1. **Dynamic Reduced-Order Hydraulic Network** ⭐⭐⭐
2. **Pre-Neck Junction Pressure Definition (Pj)** ⭐⭐⭐
3. **Two-Fluid Washburn Refill Model** ⭐⭐⭐
4. **Critical Size + Neck State Tracking** ⭐⭐⭐
5. **Continuous-Phase Pressure Treatment** ⭐⭐
6. **Monodisperse Size Back-Calculation** ⭐⭐
7. **Independent Droplet Generators** ⭐
8. **Multi-Factor Transition Warning System** ⭐⭐
9. **Grouped Rung Iteration Architecture** ⭐⭐
10. **Effective Interfacial Properties** ⭐

**Success Metric**: All 11 issues correctly implemented and validated against physics basis.

\---

## 🔧 Strategic v3 Improvements

Building on the resolved foundation, implement these physics upgrades:

1. **Competing Mechanism Selection (deferred extension — baseline uses two‑fluid Washburn)** for Stage 1 (hydraulic/interface/adsorption/backflow)
2. **Outer-Phase Necking Physics (diagnostic extension — snap-off still governed by Rcrit)** (literature-corrected from v2)
3. **Multi-Factor Regime Classification (warning/diagnostic system only)** (beyond single Ca threshold)
4. **Design-Oriented Diagnostics (deferred extension)** (actionable optimization guidance)

\---

## 📈 Implementation Phases

### Phase 1: Foundation \[2-3 weeks]

* ✅ Architecture redesign (address 50KB file issue)
* ✅ Configuration simplification
* ✅ Dynamic hydraulic network (Issue 1)
* ✅ Junction pressure definition (Issue 2)

### Phase 2: Stage 1 Physics \[1-2 weeks]

* ✅ Two-fluid Washburn implementation (Issue 3A)
* ✅ Competing mechanism selection (Strategic)

### Phase 3: Stage 2 Physics \[1-2 weeks]

* ✅ Critical size + neck tracking (Issue 4)
* ✅ Outer-phase necking (Strategic)

### Phase 4: Regime System \[1-2 weeks]

* ✅ Multi-factor classification (Strategic)
* ✅ Transition warning system (Issue 9)

### Phase 5: Design Optimization \[1-2 weeks]

* ✅ Design guidance framework (Strategic)

### Phase 6: Integration \[2 weeks]

* ✅ Grouped rung iteration (Issue 10)
* ✅ Physics validation framework

### Phase 7: Quality \& Integration \[1 week]

* ✅ Error handling, documentation
* ✅ CLI integration, backward compatibility

\---

## ⚡ Immediate Next Steps

### 1\. **Review \& Approve Plans**

* \[ ] Review consolidated physics plan for completeness
* \[ ] Approve implementation phase structure
* \[ ] Confirm timeline and resource allocation

### 2\. **Setup Development Environment**

* \[ ] Create `stepgen/models/stage\_wise\_v3/` directory structure
* \[ ] Setup validation datasets for mechanism testing
* \[ ] Establish experimental data for back-calculated parameters

### 3\. **Begin Phase 1 Implementation**

* \[ ] Start with file architecture redesign
* \[ ] Implement simplified configuration system
* \[ ] Begin dynamic hydraulic network module

\---

## 🏆 Success Criteria Summary

### Physics Accuracy

* Two-fluid Washburn improves Stage 1 predictions vs Poiseuille
* Outer-phase necking aligns with literature (Eggers \& Villermaux)
* Mechanism selection validated against experimental regimes
* Multi-factor classification reduces false transitions

### Code Quality

* Modular architecture: each file <300 lines
* Comprehensive error handling and validation
* Clear physics separation aligned with resolved issues
* Full test coverage for all components

### Integration

* Backward compatible with existing CLI
* Performance within 2x of v2
* All 11 resolved issues correctly implemented
* Design optimization experimentally actionable

\---

## 🚨 Critical Success Factors

1. **Strict adherence to resolved physics issues** - these represent core insights that must drive v3
2. **Validation at each phase** - test physics components against literature/experimental data
3. **Clean architecture from start** - don't repeat v2's 50KB file complexity issue
4. **Preserve existing interfaces** - maintain user workflow compatibility

\---

## 📖 Key Supporting Documents

### Background Context

* `step\_gen\_deepresearch.md` - Literature review of alternative mechanisms
* `two\_phase\_washburn.typ` - Mathematical derivation for Stage 1
* `v2code-review.md` - Code quality issues to address

### v2 Reference

* `stage\_wise\_technical\_overview.md` - Current v2 implementation details
* `/stepgen/models/stage\_wise.py` - Existing v2 codebase (50KB)

### Implementation Ready

* `stage\_wise\_v3\_consolidated\_physics\_plan.md` - **Complete physics strategy**
* `stage\_wise\_v3\_implementation\_plan.md` - **Executable development plan**

\---

**Ready for Implementation**: All planning complete, physics resolved, implementation roadmap defined.

**Next Action**: Begin Phase 1 architecture redesign and dynamic hydraulic network implementation.

