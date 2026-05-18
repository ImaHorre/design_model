# stepgen_seed

This is a small 'seed' refactor of the original monolithic ladder-network script into importable modules.

Files:
- stepgen_seed/resistance.py: parameter definitions + resistance formulas + design-mode flow calculation
- stepgen_seed/hydraulics.py: sparse ladder matrix builder + solver + post-processing
- stepgen_seed/example_run.py: minimal executable example

This is intentionally minimal to give Claude Code a correct baseline to preserve when building `stepgen/`.
