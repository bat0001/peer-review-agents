"""FP32 index_add scatter for routed expert outputs."""

from typing import Optional

import torch
from torch import Tensor


class IndexAddScatterFP32:
    """Scatter routed/shared expert outputs with FP32 accumulation."""
    # TODO: This implementation is simple but inefficient (extra casts/materialization);
    # replace with a more fused/optimized scatter path.

    def __call__(
        self,
        h_flat: Tensor,
        indices_flat: Tensor,
        n_tokens: int,
        weights_flat: Tensor,
        shared_flat: Optional[Tensor] = None,
        shared_weights: Optional[Tensor] = None,
    ) -> Tensor:
        h_weighted = h_flat.float() * weights_flat.float().unsqueeze(-1)
        if shared_flat is not None and shared_weights is not None:
            output = shared_flat.float() * shared_weights.float().unsqueeze(-1)
        else:
            output = torch.zeros(
                n_tokens,
                h_flat.shape[1],
                device=h_flat.device,
                dtype=torch.float32,
            )

        output.index_add_(0, indices_flat, h_weighted)
        return output.to(h_flat.dtype)


__all__ = ["IndexAddScatterFP32"]
