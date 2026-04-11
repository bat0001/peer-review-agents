# Personas

Each agent is assigned a persona that shapes its tone, disposition, and interaction style.

Current personas: `optimistic`, `pessimistic`, `agreeable`, `disagreeable`, `contrarian`, `lone_wolf`, `social`, `old_school`, `modern`, `empiricist`, `theorist`, `trendy`.

Each persona is a JSON file with:
- `trait_vector` — scored -1/0/1 on axes: assertiveness, politeness, skepticism, verbosity, social_influence, big_picture, objectivity
- `behavioral_rules` — what the agent should do
- `forbidden_behaviors` — what the agent must not do

Personas are converted to prompt text by `cli/reva/compiler.py:persona_to_markdown()` and injected as the `persona` section of the agent system prompt.
