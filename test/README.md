# Tests

Test scripts for GEC project.

## Test Files

### `test_metrics_logging.py`
Validates metrics logging across different model types (EC, GEC, GEC_shared).

**Usage:**
```bash
python test/test_metrics_logging.py
```

**What it tests:**
- Runs each model type (ec, gec, gec_shared) for 100 steps
- Verifies all metrics are collected correctly
- Checks logging output

### `test_visualizations.py`
Quick test to verify eval visualizations work correctly.

**Usage:**
```bash
python test/test_visualizations.py
```

**What it tests:**
- Runs GEC model for 10 steps with visualizations enabled
- Checks JSON logs are created (expert_counts.json, weight_percentiles.json)
- Verifies plot directories and files are generated at correct intervals
- Validates output structure

**Output checked:**
- `outputs/test_viz/test_viz/eval_logs/` - JSON time-series logs
- `outputs/test_viz/test_viz/visualizations/step_N/` - PNG plots

## Running Tests

Run from project root:
```bash
# Single test
python test/test_metrics_logging.py
python test/test_visualizations.py

# Or make them executable and run directly
chmod +x test/*.py
test/test_visualizations.py
```

## Dependencies

Tests require:
- PyTorch
- matplotlib (for visualizations)
- Standard GEC dependencies

Install visualization dependencies:
```bash
pip install matplotlib
```
