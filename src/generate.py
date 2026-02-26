import torch
import torch.nn.functional as F
from typing import Optional, Union

from .models import BaseGPT


def generate(
    model: BaseGPT,
    x: Union[torch.Tensor, str, None] = None,
    tokenizer=None,
    max_new_tokens: int = 100,
    temperature: float = 1.0,
    top_k: Optional[int] = None,
) -> torch.Tensor:
    """
    Generate text using the model.
    
    Args:
        model: The model to use for generation
        x: Input text or tensor
        tokenizer: Tokenizer to use for text input
        max_new_tokens: Maximum number of tokens to generate
        temperature: Temperature for sampling
        top_k: Number of top tokens to consider for sampling
        
    Returns:
        Generated token sequence
    """
    if isinstance(x, str):
        if tokenizer is None:
            raise ValueError("Tokenizer must be provided for string input")
        x = torch.tensor(tokenizer.encode(x), device=next(model.parameters()).device).unsqueeze(0)
    
    if isinstance(x, torch.Tensor):
        x = x.to(next(model.parameters()).device)
    else:
        raise ValueError(f"Invalid input type: {type(x)}")
    
    seq_len = x.size(1)
    if seq_len > model.config.block_size:
        raise ValueError(f"Cannot generate more tokens than the model's block size: {model.config.block_size}")
    
    max_new_tokens = min(max_new_tokens, model.config.block_size - seq_len)
    model.eval()
    
    with torch.no_grad():
        for _ in range(max_new_tokens):
            logits, _ = model(x)
            logits = logits[:, -1, :]
            # Mask out tokens beyond 50257 (the actual vocabulary size)
            logits[:, 50257:] = float('-inf')
            
            if temperature > 0.01:
                probs = F.softmax(logits / temperature, dim=-1)
                if top_k is not None:
                    top_k_probs, top_k_indices = torch.topk(probs, top_k)
                    probs = torch.zeros_like(probs).scatter_(1, top_k_indices, top_k_probs)
                next_token = torch.multinomial(probs, num_samples=1)
            else:  # greedy sampling
                next_token = torch.argmax(logits, dim=-1, keepdim=True)
            
            x = torch.cat((x, next_token), dim=1)
    
    return x


def test_model(model: BaseGPT, tokenizer) -> None:
    """
    Test the model by generating some text.
    
    Args:
        model: The model to test
        tokenizer: Tokenizer to use for encoding/decoding
    """
    model.eval()
    print('Testing model inference...')
    message = "Hello, how are you?"
    output = generate(model, message, tokenizer, max_new_tokens=100, temperature=0.5)
    print(">>>", tokenizer.decode(output[0].tolist())) 
