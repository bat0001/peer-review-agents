import os
import math
import torch
import torch.distributed

def get_lr(step: int, max_steps: int, learning_rate: float, schedule_type: str) -> float:
    """Get learning rate based on schedule."""
    warmup_steps = max_steps // 20
    
    if step < warmup_steps:
        return learning_rate * step / warmup_steps
        
    if schedule_type == 'cosine':
        decay_ratio = (step - warmup_steps) / (max_steps - warmup_steps)
        return learning_rate * 0.5 * (1.0 + math.cos(math.pi * decay_ratio))
    elif schedule_type == 'trapezoid':
        decay_ratio = (step - warmup_steps) / (max_steps - warmup_steps)
        if decay_ratio < 0.5:
            return learning_rate
        else:
            return learning_rate * (1.0 - (decay_ratio - 0.5) * 2)
    else:
        raise ValueError(f"Unknown schedule type: {schedule_type}")

def setup_distributed_training():
    """Setup distributed training environment."""
    local_rank = int(os.environ.get("LOCAL_RANK", -1))
    rank = int(os.environ.get("RANK", -1))
    world_size = int(os.environ.get("WORLD_SIZE", -1))
    
    if world_size > 1 and not torch.distributed.is_initialized():
        torch.cuda.set_device(local_rank)
        torch.distributed.init_process_group(backend='nccl')
    
    is_master = rank in [-1, 0]
    ddp = world_size > 1
    
    return ddp, rank, world_size, local_rank, is_master

def setup_torch_backend(device: str) -> None:
    """Setup PyTorch backend optimizations."""
    if device.startswith('cuda'):
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True 