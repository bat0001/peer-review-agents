import triton
import triton.language as tl
from typing import Optional

BLOCK_M = 128
ALLOW_TF32 = False # why would scattermoe use true though?



@triton.jit