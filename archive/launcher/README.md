# launcher/ — archived

This directory is superseded by the `reva` CLI in `cli/`. Do not add new functionality here.

It contains useful reference implementations:
- `sampler.py` — stratified/random sampling over role × interests × persona
- `prepare_agents.py` — generates agent directories with compiled prompts
- `run_agents.py` — parallel agent launch via threading
- `backends/claude_code.py` — Claude Code backend

See the root `README.md` and `cli/readme.md` for the current workflow.
