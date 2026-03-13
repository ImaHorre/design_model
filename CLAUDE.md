\# CLAUDE.md



\## Project context



This repository uses a phase-gated implementation workflow.



Claude must stop after each phase, run tests, document results,

and wait for explicit user continuation before proceeding.



This repository contains the stage-wise droplet model and related hydraulic modeling code.



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

6b. git commit and push - see git workflow below. 

7\. STOP and wait for explicit user continuation before starting the next phase



Do not continue automatically to the next phase.



\## Git Workflow



This repository uses Git for version control. Git is already configured for this repository.



Claude should follow this workflow when implementing updates.



\### Phase-based commits



After completing each implementation phase:



1\. Ensure tests for that phase have been executed.

2\. Confirm the phase summary and results have been written to the progress log in:

&#x20;  `stage\_wise\_v3\_implementation\_plan\_REVISED.md`

3\. Stage only the files that were intentionally modified.



\### Commit procedure



Use the following process:



1\. Review changed files

2\. Stage relevant files

3\. Create a commit with a structured message

4\. Push to the repository





\### Safety rules



Claude must:



\- Never use `git add .` unless explicitly instructed

\- Review `git status` before committing

\- Never force push

\- Never rewrite history

\- Never delete branches



\### Phase completion workflow



After finishing a phase:



1\. Run tests

2\. Update implementation progress log

3\. Commit changes

4\. Push to repository

5\. Stop and wait for user approval before starting the next phase





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

