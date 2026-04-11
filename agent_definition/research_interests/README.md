# Research Interests

Each agent is given a research interest profile that biases which papers it selects and how it weighs its own expertise when reviewing.

Interest prompts are organized by **seniority level** × **topic area**:

```
generated_personas/
  junior/        # early-career familiarity
  mid/           # active researcher
  senior/        # deep domain expertise
  adjacent/      # surface-level exposure from neighboring subfield
```

Topics currently covered: foundation models, large language models, and subtopics (agents & tool use, alignment & RLHF, efficiency & compression, fine-tuning & adaptation, pre-training & architecture, reasoning & chain-of-thought, retrieval-augmented generation), plus deep learning, learning paradigms, probabilistic & statistical methods, reinforcement learning, and transfer & adaptation.

Interest prompts are injected as the `## Research Interests` section of the agent system prompt by `cli/reva/compiler.py:interests_to_markdown()`.

See `ml_taxonomy.json` for the full topic taxonomy and `generate_personas.py` for the generation pipeline.
