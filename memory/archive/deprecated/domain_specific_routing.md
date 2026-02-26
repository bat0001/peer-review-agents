# Domain-Specific Routing Analysis (Future Work)

## Overview

Qualitative analysis showing actual token sequences with their routing patterns across different domains. This is **separate infrastructure** from the main visualization system - not part of regular training evaluation.

## Purpose

Understand if routing patterns correlate with:
- **Domain type**: Code, math, prose, dialogue
- **Linguistic properties**: Syntax, semantics, pragmatics
- **Task difficulty**: Factual recall vs reasoning
- **Domain transitions**: Where domain changes mid-sequence

## Visualization Design

### Format
Interactive table or grid showing:
- **Token sequence** (context window of ~50 tokens)
- **Per-token expert activation** (heatmap: rows = layers, columns = tokens)
- **Expert IDs** that activated for each token
- **Domain label** and **difficulty score** (if available)

### Selection Criteria
Choose representative examples based on:
- High-fanout tokens (4+ experts consistently)
- Low-fanout tokens (0-1 experts consistently)
- Domain transitions (where domain changes mid-sequence)
- High-loss tokens (model struggled)
- Low-loss tokens (model confident)

### Example Output

```
Domain: Code (Python)
Difficulty: Medium
Tokens: [50 tokens showing a function definition]

Layer 0: ████░░░░████░░░░░░░░░████████░░░░░░░░░░████░░░░░░
Layer 1: ░░████░░░░░░████████░░░░░░████░░░░████░░░░████░░░
Layer 2: ██░░░░████░░░░░░░░████░░░░░░░░████░░░░░░░░░░████
...

Token 15: "def" → Experts [0, 3, 7] (3 experts)
Token 16: "calculate" → Experts [1, 4] (2 experts)
Token 17: "(" → Experts [2] (1 expert)
...
```

## Data Requirements

### Domain-Labeled Datasets

Need evaluation sets with domain annotations:
- **Code**: The Stack, GitHub code
- **Math**: MATH dataset, GSM8K
- **Prose**: Books corpus, news articles
- **Dialogue**: Reddit, conversational data

### Per-Token Routing Data

For each token in selected sequences:
- Expert activation mask (which experts processed it)
- Router weights/logits per expert
- Per-token loss
- Per-token entropy (prediction uncertainty)

## Implementation Approach

### Separate Evaluation Script

**Not part of main training loop** - Too heavy for regular eval_step:
- Run separately on domain-labeled validation sets
- Can be done post-training for analysis
- Or during dedicated analysis checkpoints

### Components

1. **Data loader**: Load domain-labeled datasets with annotations
2. **Routing capture**: Collect full per-token routing decisions for all layers
3. **Sequence selector**: Choose representative sequences based on criteria
4. **Visualization generator**: Create HTML/interactive visualizations

### Output Format

**Interactive HTML** with embedded data:
- Hover over tokens to see routing details
- Toggle layers on/off
- Filter by domain/difficulty
- Export selected sequences

**Or JSON + viewer tool**:
- Save data in structured JSON
- Separate viewer for exploration

**Storage**: ~1-10MB per domain analysis

## When to Build This

Priority: **Future work**, after:
1. ✅ Base visualization system is working (completed)
2. ⬜ We have domain-labeled evaluation sets
3. ⬜ Need qualitative analysis for paper/debugging
4. ⬜ Want to understand domain-specific routing patterns

## Design Questions to Resolve

Before implementation:
1. **Dataset selection**: Which domain-labeled datasets to use?
2. **Annotation granularity**: Per-sequence or per-token domain labels?
3. **Visualization format**: Interactive HTML vs static plots vs separate viewer?
4. **Integration**: Standalone script vs integrated into trainer?
5. **Scope**: All layers or representative layers only?
6. **Memory**: Can we fit full-sequence routing data for all layers in memory?

## Related Work

This complements the main visualization system:
- **Main system**: Aggregate statistics over full validation set
- **This system**: Qualitative examples showing specific sequences

Both are needed for complete understanding of routing behavior.
