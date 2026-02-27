"""Shared representative-layer selection helpers."""


def _filter_valid_layers(candidates: set[int], n_layer: int) -> set[int]:
    """Keep only valid layer indices in [0, n_layer)."""
    if n_layer <= 0:
        return set()
    return {idx for idx in candidates if 0 <= idx < n_layer}


def get_repr_layers(n_layer: int) -> set[int]:
    """Representative layers used for detailed routing metrics."""
    return _filter_valid_layers(
        {
            0,
            1,
            n_layer // 4,
            n_layer // 2,
            3 * n_layer // 4,
            n_layer - 1,
        },
        n_layer,
    )


def get_first_last_layers(n_layer: int) -> set[int]:
    """First/last subset used for first-expert and last-expert cutoffs."""
    return _filter_valid_layers({0, 1, n_layer - 1}, n_layer)
