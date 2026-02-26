"""CORE evaluation (nanochat style)."""

from __future__ import annotations

import csv
import json
import random
import shutil
import tempfile
import zipfile
from pathlib import Path

import torch
import torch.distributed as dist
from jinja2 import Template
import yaml

from src.utils.download import download_file_with_lock, resolve_base_dir

EVAL_BUNDLE_URL = "https://karpathy-public.s3.us-west-2.amazonaws.com/eval_bundle.zip"


# -----------------------------------------------------------------------------
# Prompt rendering utilities


def render_prompts_mc(item, continuation_delimiter, fewshot_examples=None):
    template_str = """
{%- for example in fewshot_examples -%}
{{ example.query }}{{ continuation_delimiter }}{{ example.choices[example.gold] }}

{% endfor -%}
{{ item.query }}{{ continuation_delimiter }}{{ choice }}""".strip()
    template = Template(template_str)
    fewshot_examples = fewshot_examples or []
    context = {
        "fewshot_examples": fewshot_examples,
        "continuation_delimiter": continuation_delimiter,
        "item": item,
    }
    prompts = [template.render(choice=choice, **context) for choice in item["choices"]]
    return prompts


def render_prompts_schema(item, continuation_delimiter, fewshot_examples=None):
    template_str = """
{%- for example in fewshot_examples -%}
{{ example.context_options[example.gold] }}{{ continuation_delimiter }}{{ example.continuation }}

{% endfor -%}
{{ context }}{{ continuation_delimiter }}{{ item.continuation }}""".strip()
    template = Template(template_str)
    fewshot_examples = fewshot_examples or []
    context = {
        "fewshot_examples": fewshot_examples,
        "continuation_delimiter": continuation_delimiter,
        "item": item,
    }
    prompts = [template.render(context=context_option, **context)
               for context_option in item["context_options"]]
    return prompts


def render_prompts_lm(item, continuation_delimiter, fewshot_examples=None):
    template_str = """
{%- for example in fewshot_examples -%}
{{ example.context | trim }}{{ continuation_delimiter }}{{ example.continuation }}

{% endfor -%}
{{ item.context | trim }}{{ continuation_delimiter }}{% if include_continuation %}{{ item.continuation }}{% endif %}""".strip()
    template = Template(template_str)
    fewshot_examples = fewshot_examples or []
    context = {
        "fewshot_examples": fewshot_examples,
        "continuation_delimiter": continuation_delimiter,
        "item": item,
    }
    prompt_without = template.render(include_continuation=False, **context)
    prompt_with = template.render(include_continuation=True, **context)
    prompt_without = prompt_without.strip()
    return [prompt_without, prompt_with]


def find_common_length(token_sequences, direction="left"):
    min_len = min(len(seq) for seq in token_sequences)
    indices = {
        "left": range(min_len),
        "right": range(-1, -min_len - 1, -1),
    }[direction]
    for i, idx in enumerate(indices):
        token = token_sequences[0][idx]
        if not all(seq[idx] == token for seq in token_sequences):
            return i
    return min_len


def stack_sequences(tokens, pad_token_id):
    bsz, seq_len = len(tokens), max(len(x) for x in tokens)
    input_ids = torch.full((bsz, seq_len), pad_token_id, dtype=torch.long)
    for i, x in enumerate(tokens):
        input_ids[i, :len(x)] = torch.tensor(x, dtype=torch.long)
    return input_ids


def batch_sequences_mc(tokenizer, prompts):
    tokens = tokenizer(prompts, prepend=tokenizer.get_bos_token_id())
    answer_start_idx = find_common_length(tokens, direction="left")
    start_indices = [answer_start_idx] * len(prompts)
    end_indices = [len(x) for x in tokens]
    return tokens, start_indices, end_indices


def batch_sequences_schema(tokenizer, prompts):
    tokens = tokenizer(prompts, prepend=tokenizer.get_bos_token_id())
    suffix_length = find_common_length(tokens, direction="right")
    end_indices = [len(x) for x in tokens]
    start_indices = [ei - suffix_length for ei in end_indices]
    return tokens, start_indices, end_indices


def batch_sequences_lm(tokenizer, prompts):
    tokens = tokenizer(prompts, prepend=tokenizer.get_bos_token_id())
    tokens_without, tokens_with = tokens
    start_idx, end_idx = len(tokens_without), len(tokens_with)
    if start_idx >= end_idx:
        raise ValueError("prompt without must be a strict prefix of prompt with continuation")
    if tokens_without != tokens_with[:start_idx]:
        raise ValueError("prompt without must be a prefix of prompt with continuation")
    return [tokens_with], [start_idx], [end_idx]


def _get_max_seq_len(model):
    max_seq_len = getattr(model, "max_seq_len", None)
    if max_seq_len is None and hasattr(model, "config"):
        max_seq_len = getattr(model.config, "block_size", None)
    return max_seq_len


def _crop_tokens_to_max(tokens, start_idxs, end_idxs, max_seq_len):
    if max_seq_len is None:
        return tokens, start_idxs, end_idxs
    new_tokens, new_start_idxs, new_end_idxs = [], [], []
    for t, s, e in zip(tokens, start_idxs, end_idxs):
        if len(t) > max_seq_len:
            num_to_crop = len(t) - max_seq_len
            t = t[-max_seq_len:]
            s -= num_to_crop
            e -= num_to_crop
            if s < 0 or e < 0:
                raise ValueError("cropped indices went negative")
        new_tokens.append(t)
        new_start_idxs.append(s)
        new_end_idxs.append(e)
    return new_tokens, new_start_idxs, new_end_idxs


def _build_example_inputs(idx, model, tokenizer, data, device, task_meta):
    item = data[idx]
    task_type = task_meta["task_type"]
    num_fewshot = task_meta["num_fewshot"]
    continuation_delimiter = task_meta["continuation_delimiter"]

    fewshot_examples = []
    if num_fewshot > 0:
        rng = random.Random(1234 + idx)
        available_indices = [i for i in range(len(data)) if i != idx]
        fewshot_indices = rng.sample(available_indices, num_fewshot)
        fewshot_examples = [data[i] for i in fewshot_indices]

    if task_type == "multiple_choice":
        prompts = render_prompts_mc(item, continuation_delimiter, fewshot_examples)
        tokens, start_idxs, end_idxs = batch_sequences_mc(tokenizer, prompts)
    elif task_type == "schema":
        prompts = render_prompts_schema(item, continuation_delimiter, fewshot_examples)
        tokens, start_idxs, end_idxs = batch_sequences_schema(tokenizer, prompts)
    elif task_type == "language_modeling":
        prompts = render_prompts_lm(item, continuation_delimiter, fewshot_examples)
        tokens, start_idxs, end_idxs = batch_sequences_lm(tokenizer, prompts)
    else:
        raise ValueError(f"Unsupported task type: {task_type}")

    max_seq_len = _get_max_seq_len(model)
    tokens, start_idxs, end_idxs = _crop_tokens_to_max(tokens, start_idxs, end_idxs, max_seq_len)

    pad_token_id = tokenizer.get_bos_token_id()
    input_ids = stack_sequences(tokens, pad_token_id).to(device)

    meta = {
        "task_type": task_type,
        "start_idxs": start_idxs,
        "end_idxs": end_idxs,
        "gold": item.get("gold", None),
    }
    return input_ids, meta


def _compute_correctness(losses, predictions, input_ids, meta):
    task_type = meta["task_type"]
    start_idxs = meta["start_idxs"]
    end_idxs = meta["end_idxs"]

    if task_type == "language_modeling":
        si = start_idxs[0]
        ei = end_idxs[0]
        predicted_tokens = predictions[0, si - 1:ei - 1]
        actual_tokens = input_ids[0, si:ei]
        return bool(torch.all(predicted_tokens == actual_tokens).item())
    if task_type in {"multiple_choice", "schema"}:
        mean_losses = [
            losses[i, si - 1:ei - 1].mean().item()
            for i, (si, ei) in enumerate(zip(start_idxs, end_idxs))
        ]
        pred_idx = mean_losses.index(min(mean_losses))
        return pred_idx == meta["gold"]
    raise ValueError(f"Unsupported task type: {task_type}")


def _pad_input_ids(input_ids, pad_token_id, target_len):
    if input_ids.size(1) == target_len:
        return input_ids
    padded = torch.full(
        (input_ids.size(0), target_len),
        pad_token_id,
        device=input_ids.device,
        dtype=input_ids.dtype,
    )
    padded[:, :input_ids.size(1)] = input_ids
    return padded


@torch.no_grad()
def _forward_eval_batch(model, input_ids, pad_token_id):
    if hasattr(model, "forward_eval_batch"):
        out = model.forward_eval_batch(input_ids, pad_token_id=pad_token_id)
        return out.losses, out.predictions, out.valid_rows

    if input_ids.numel() == 0:
        raise ValueError("input_ids cannot be empty when model has no forward_eval_batch")

    batch_size, seq_len = input_ids.size()
    outputs = model(input_ids)
    logits = outputs.logits if hasattr(outputs, "logits") else outputs
    target_ids = torch.roll(input_ids, shifts=-1, dims=1)
    losses = torch.nn.functional.cross_entropy(
        logits.view(batch_size * seq_len, -1),
        target_ids.view(batch_size * seq_len),
        reduction="none",
    ).view(batch_size, seq_len)
    losses[:, -1] = float("nan")
    predictions = logits.argmax(dim=-1)
    valid_rows = torch.ones(batch_size, dtype=torch.bool, device=input_ids.device)
    return losses, predictions, valid_rows


def _chunked(items, chunk_size):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def _build_microbatch_inputs(indices, model, tokenizer, data, device, task_meta):
    if not indices:
        raise ValueError("indices must be non-empty")

    pad_token_id = tokenizer.get_bos_token_id()
    example_inputs = []
    metas = []
    row_ranges = []
    max_seq_len = 0
    row_cursor = 0

    for idx in indices:
        input_ids, meta = _build_example_inputs(idx, model, tokenizer, data, device, task_meta)
        example_inputs.append(input_ids)
        metas.append(meta)
        row_start = row_cursor
        row_cursor += input_ids.size(0)
        row_ranges.append((row_start, row_cursor))
        max_seq_len = max(max_seq_len, input_ids.size(1))

    batch_input_ids = torch.cat(
        [
            _pad_input_ids(inp, pad_token_id, max_seq_len)
            if inp.size(1) != max_seq_len else inp
            for inp in example_inputs
        ],
        dim=0,
    )
    return batch_input_ids, example_inputs, metas, row_ranges


def evaluate_task(model, tokenizer, data, device, task_meta, eval_examples_per_forward=1):
    if eval_examples_per_forward <= 0:
        raise ValueError(f"eval_examples_per_forward must be > 0, got {eval_examples_per_forward}")

    rank = dist.get_rank() if dist.is_initialized() else 0
    world_size = dist.get_world_size() if dist.is_initialized() else 1
    correct_sum = torch.tensor(0.0, device=device)
    count = torch.tensor(0.0, device=device)

    local_indices = list(range(rank, len(data), world_size))
    local_batches = list(_chunked(local_indices, eval_examples_per_forward))

    expert_parallel = False
    if dist.is_initialized() and world_size > 1:
        expert_parallel = bool(getattr(getattr(model, "config", None), "expert_parallel", False))

    if expert_parallel and dist.is_initialized():
        local_steps = torch.tensor([len(local_batches)], device=device, dtype=torch.long)
        dist.all_reduce(local_steps, op=dist.ReduceOp.MAX)
        total_steps = int(local_steps.item())
    else:
        total_steps = len(local_batches)

    pad_token_id = tokenizer.get_bos_token_id()

    for step in range(total_steps):
        if step < len(local_batches):
            batch_input_ids, example_inputs, metas, row_ranges = _build_microbatch_inputs(
                local_batches[step], model, tokenizer, data, device, task_meta
            )
            real_rows = row_ranges[-1][1]
        else:
            batch_input_ids = torch.empty((0, 0), dtype=torch.long, device=device)
            example_inputs, metas, row_ranges = [], [], []
            real_rows = 0

        losses, predictions, valid_rows = _forward_eval_batch(
            model, batch_input_ids, pad_token_id=pad_token_id
        )

        if real_rows > 0 and not bool(valid_rows[:real_rows].all().item()):
            raise RuntimeError("Model marked real rows as invalid during eval forward")

        for input_ids_i, meta_i, (row_start, row_end) in zip(example_inputs, metas, row_ranges):
            is_correct = _compute_correctness(
                losses[row_start:row_end],
                predictions[row_start:row_end],
                input_ids_i,
                meta_i,
            )
            correct_sum += float(is_correct)
            count += 1.0

    if world_size > 1:
        dist.all_reduce(correct_sum, op=dist.ReduceOp.SUM)
        dist.all_reduce(count, op=dist.ReduceOp.SUM)

    if count.item() == 0:
        return float("nan")
    return (correct_sum / count).item()


# -----------------------------------------------------------------------------
# Bundle IO + evaluation driver


def _place_eval_bundle(file_path: str, bundle_dir: Path) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            zip_ref.extractall(tmpdir)
        extracted_bundle_dir = Path(tmpdir) / "eval_bundle"
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        shutil.move(str(extracted_bundle_dir), str(bundle_dir))


def evaluate_model(
    model,
    tokenizer,
    device: torch.device,
    max_per_task: int = -1,
    eval_examples_per_forward: int = 1,
    bundle_url: str = EVAL_BUNDLE_URL,
    bundle_dir: str | None = None,
    base_dir: str | None = None,
) -> dict:
    base_dir_path = resolve_base_dir(base_dir)
    eval_bundle_dir = Path(bundle_dir) if bundle_dir else base_dir_path / "eval_bundle"

    if not eval_bundle_dir.exists():
        eval_bundle_dir.parent.mkdir(parents=True, exist_ok=True)
        download_file_with_lock(
            bundle_url,
            "eval_bundle.zip",
            postprocess_fn=lambda path: _place_eval_bundle(path, eval_bundle_dir),
            base_dir=str(eval_bundle_dir.parent),
        )

    config_path = eval_bundle_dir / "core.yaml"
    data_base_path = eval_bundle_dir / "eval_data"
    eval_meta_data = eval_bundle_dir / "eval_meta_data.csv"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    tasks = config["icl_tasks"]

    random_baselines = {}
    with open(eval_meta_data, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            task_name = row["Eval Task"]
            random_baselines[task_name] = float(row["Random baseline"])

    was_training = model.training
    model.eval()

    results = {}
    centered_results = {}

    for task in tasks:
        label = task["label"]
        task_meta = {
            "task_type": task["icl_task_type"],
            "dataset_uri": task["dataset_uri"],
            "num_fewshot": task["num_fewshot"][0],
            "continuation_delimiter": task.get("continuation_delimiter", " "),
        }

        data_path = data_base_path / task_meta["dataset_uri"]
        with open(data_path, "r", encoding="utf-8") as f:
            data = [json.loads(line.strip()) for line in f]

        shuffle_rng = random.Random(1337)
        shuffle_rng.shuffle(data)
        if max_per_task > 0:
            data = data[:max_per_task]

        accuracy = evaluate_task(
            model,
            tokenizer,
            data,
            device,
            task_meta,
            eval_examples_per_forward=eval_examples_per_forward,
        )

        results[label] = accuracy
        random_baseline = random_baselines[label]
        centered_result = (accuracy - 0.01 * random_baseline) / (1.0 - 0.01 * random_baseline)
        centered_results[label] = centered_result

    core_metric = sum(centered_results.values()) / len(centered_results)

    if was_training:
        model.train()

    return {
        "results": results,
        "centered_results": centered_results,
        "core_metric": core_metric,
    }
