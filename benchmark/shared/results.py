"""Shared result dataclasses and formatting utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple

import torch


@dataclass
class BenchmarkResult:
    name: str
    time_ms: float
    gbps: float
    bytes_moved: float
    matches: bool | None = None
    max_abs_diff: float | None = None
    mean_abs_diff: float | None = None
    peak_mem_gb: float | None = None
    extras: Dict[str, float | bool] = field(default_factory=dict)  # Performance metadata only
    diagnostics: Dict[str, Any] = field(default_factory=dict)  # Validation diagnostics only


def measure(fn, *, repeats: int = 50, warmup: int = 10) -> float:
    """Return the average runtime in milliseconds for ``fn``."""
    torch.cuda.synchronize()
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()

    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)

    start.record()
    for _ in range(repeats):
        fn()
    end.record()

    torch.cuda.synchronize()
    return start.elapsed_time(end) / repeats


def _fmt_cell(text: str, width: int, alignment: str) -> str:
    if alignment == 'right':
        content = text.rjust(width)
    elif alignment == 'center':
        pad_total = width - len(text)
        left = pad_total // 2
        right = pad_total - left
        content = ' ' * left + text + ' ' * right
    else:
        content = text.ljust(width)
    return f" {content} "


def _render_table(
    headers: List[str],
    rows: Iterable[Iterable[str]],
    *,
    align: Iterable[str],
) -> str:
    rows_list = [list(row) for row in rows]
    widths = [len(h) for h in headers]
    for row in rows_list:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    header_border = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'
    header_border_bold = '+' + '+'.join('=' * (w + 2) for w in widths) + '+'

    header_line = '|' + '|'.join(
        _fmt_cell(headers[i], widths[i], 'center') for i in range(len(headers))
    ) + '|'

    alignments = list(align)
    lines = [header_border, header_line, header_border_bold]
    for row in rows_list:
        line = '|' + '|'.join(
            _fmt_cell(row[i], widths[i], alignments[i]) for i in range(len(row))
        ) + '|'
        lines.append(line)
    lines.append(header_border)
    return "\n".join(lines)


def render_table(headers: List[str], rows: Iterable[Iterable[str]], *, align: Iterable[str]) -> str:
    """Public wrapper for table rendering (shared by MLP and permutation)."""
    return _render_table(headers, rows, align=align)


def format_results(results: List[BenchmarkResult]) -> Tuple[str, str]:
    """Format results into two tables: performance and validation."""
    perf_table = _format_performance_table(results)
    val_table = _format_validation_table(results)
    return perf_table, val_table


def _format_performance_table(results: List[BenchmarkResult]) -> str:
    show_peak = any(res.peak_mem_gb is not None for res in results)
    headers = ['kernel', 'time (ms)', 'GB/s', 'GB moved']
    align = ['left', 'right', 'right', 'right']
    if show_peak:
        headers.append('peak (GB)')
        align.append('right')
    headers.append('match')
    align.append('center')

    rows = []
    for res in results:
        bytes_gb = res.bytes_moved / 1e9
        match_str = 'n/a'
        if res.matches is True:
            match_str = 'yes'
        elif res.matches is False:
            match_str = 'NO'

        row = [
            res.name,
            f"{res.time_ms:6.3f}",
            f"{res.gbps:6.2f}",
            f"{bytes_gb:5.2f}",
        ]
        if show_peak:
            peak = res.peak_mem_gb
            row.append(f"{peak:5.2f}" if peak is not None else '   — ')
        row.append(match_str)
        rows.append(row)

    return _render_table(headers, rows, align=align)


def _format_validation_table(results: List[BenchmarkResult]) -> str:
    """Format the validation details table."""
    VALIDATION_METRICS = {
        'max|Δ|',
        'fwd_diff',
        'grad_diff',
        'fwd_mean',
        'grad_mean',
        'mean_diff',
        'grad_w_match',
        'grad_w_max',
    }

    val_columns = set()
    for res in results:
        if res.max_abs_diff is not None:
            val_columns.add('max|Δ|')
        for key in res.extras.keys():
            if key in VALIDATION_METRICS:
                val_columns.add(key)

    if not val_columns:
        return ''

    ordered_cols = []
    if 'max|Δ|' in val_columns:
        ordered_cols.append('max|Δ|')

    for metric in ['fwd_diff', 'fwd_mean', 'grad_diff', 'grad_mean', 'mean_diff', 'grad_w_max', 'grad_w_match']:
        if metric in val_columns:
            ordered_cols.append(metric)

    headers = ['kernel'] + ordered_cols
    align = ['left'] + ['right'] * len(ordered_cols)

    rows = []
    for res in results:
        row = [res.name]

        for col in ordered_cols:
            if col == 'max|Δ|':
                if res.max_abs_diff is not None:
                    row.append(f"{res.max_abs_diff:.2e}")
                else:
                    row.append('—')
            elif col in res.extras:
                value = res.extras[col]
                if isinstance(value, bool):
                    row.append('yes' if value else 'NO')
                else:
                    row.append(f"{value:.2e}")
            else:
                row.append('—')

        rows.append(row)

    return _render_table(headers, rows, align=align)


def format_stats(stats: Dict[str, Dict[str, float]]) -> str:
    lines: List[str] = []
    if 'weights' in stats:
        w = stats['weights']
        lines.append(
            f"weights -> min {w['min']:.3f}, max {w['max']:.3f}, mean {w['mean']:.3f}, std {w['std']:.3f}"
        )
    if 'compile' in stats:
        c = stats['compile']
        parts = []
        if 'available' in c:
            parts.append(f"available {int(c['available'])}")
        if 'failures' in c:
            parts.append(f"failures {int(c['failures'])}")
        if parts:
            lines.append('compile -> ' + ', '.join(parts))
    return '\n'.join(lines)
