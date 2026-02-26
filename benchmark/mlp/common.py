"""Common utilities for MLP benchmarks."""

from __future__ import annotations

from numbers import Number
from typing import Any, Dict, List

from benchmark.shared.results import (
    BenchmarkResult,
    format_results,
    format_stats,
    measure,
    render_table,
)

__all__ = [
    'BenchmarkResult',
    'format_results',
    'format_stats',
    'format_grouped_results',
    'measure',
]


def _build_diagnostic_string(diagnostics: Dict, prefix: str | None) -> str:
    """Build diagnostic string from diagnostics dict with optional prefix for fwd/bwd."""
    parts = []

    # Determine key prefix
    key_prefix = f'{prefix}_' if prefix else ''

    # Value ranges
    ref_min = diagnostics.get(f'{key_prefix}ref_min')
    ref_max = diagnostics.get(f'{key_prefix}ref_max')
    test_min = diagnostics.get(f'{key_prefix}test_min')
    test_max = diagnostics.get(f'{key_prefix}test_max')

    if ref_min is not None and ref_max is not None:
        parts.append(f'ref:[{ref_min:.2e},{ref_max:.2e}]')
    if test_min is not None and test_max is not None:
        parts.append(f'test:[{test_min:.2e},{test_max:.2e}]')

    # Sample mismatches (show first 2 to keep compact)
    sample_diffs = diagnostics.get(f'{key_prefix}sample_diffs', [])
    if sample_diffs:
        sample_strs = []
        for idx_tuple, ref_val, test_val in sample_diffs[:2]:
            # Shorten index display for readability
            idx_str = ','.join(map(str, idx_tuple))
            sample_strs.append(f'[{idx_str}]:{ref_val:.2e}→{test_val:.2e}')
        if sample_strs:
            parts.append(f'samples: {" ".join(sample_strs)}')

    return ' '.join(parts) if parts else 'unknown error'


def _format_extra_value(value: Any) -> str:
    """Render misc extras safely for the details column."""
    if isinstance(value, Number) and not isinstance(value, bool):
        return f'{value:.2e}'

    if isinstance(value, str):
        return value

    if isinstance(value, (list, tuple)):
        if not value:
            return '[]'

        # Preview numeric sequences compactly, fall back to length otherwise.
        if all(isinstance(item, Number) for item in value):
            preview = ','.join(f'{item:.2e}' for item in value[:3])
            if len(value) > 3:
                preview += ',…'
            return f'[{preview}]'

        return f'len={len(value)}'

    return str(value)


def format_grouped_results(
    results: List[BenchmarkResult], groups: Dict[str, List[str]]
) -> str:
    """Format results grouped by reference implementation with separate performance and validation tables."""
    lines = []

    for ref_name, group_members in groups.items():
        # Get results for this group
        group_results = [r for r in results if r.name in group_members]
        if not group_results:
            continue

        # Determine group label
        if 'shared' in ref_name:
            group_label = 'GEC_SHARED (with shared expert, reduced routed capacity)'
        else:
            group_label = 'GEC (no shared expert, full routed capacity)'

        # Group separator with clear label
        lines.append('')
        lines.append('=' * 88)
        lines.append(f'{group_label}')
        lines.append('=' * 88)
        lines.append('')
        lines.append('PERFORMANCE:')

        perf_headers = ['kernel', 'time (ms)', 'GB/s', 'GB moved']
        perf_align = ['left', 'right', 'right', 'right']

        # Check if any result has peak memory
        show_peak = any(r.peak_mem_gb is not None for r in group_results)
        if show_peak:
            perf_headers.append('peak (GB)')
            perf_align.append('right')

        perf_headers.append('details')
        perf_align.append('left')

        perf_rows = []
        for res in group_results:
            bytes_gb = res.bytes_moved / 1e9

            # Details column (performance metadata from extras)
            details = []
            for key, value in res.extras.items():
                if isinstance(value, bool):
                    details.append(f'{key}={"yes" if value else "NO"}')
                else:
                    details.append(f'{key}={_format_extra_value(value)}')
            detail_str = '; '.join(details) if details else '—'

            row = [
                res.name,
                f'{res.time_ms:6.3f}',
                f'{res.gbps:6.2f}',
                f'{bytes_gb:5.2f}',
            ]
            if show_peak:
                peak = res.peak_mem_gb
                row.append(f'{peak:5.2f}' if peak is not None else '   — ')
            row.append(detail_str)
            perf_rows.append(row)

        lines.append(render_table(perf_headers, perf_rows, align=perf_align))

        # Skip validation table for self-referencing groups
        if len(group_members) <= 1:
            continue

        lines.append('')
        lines.append('VALIDATION:')

        # Check if we have forward/backward specific validation
        has_fwd_bwd = any('fwd_max_diff' in r.diagnostics for r in group_results)

        if has_fwd_bwd:
            val_headers = ['kernel', 'fwd', 'grad', 'max|Δ|', 'mean|Δ|', 'fwd|Δ|', 'bwd|Δ|']
            val_align = ['left', 'center', 'center', 'center', 'center', 'center', 'center']
        else:
            val_headers = ['kernel', 'fwd', 'max|Δ|', 'mean|Δ|']
            val_align = ['left', 'center', 'center', 'center']

        val_headers.append('notes')
        val_align.append('left')

        val_rows = []
        for res in group_results:
            # Forward match column
            if res.name == ref_name:
                fwd_match_str = '—'
            elif res.matches is True:
                fwd_match_str = '✓'
            elif res.matches is False:
                fwd_match_str = '✗'
            else:
                fwd_match_str = '—'

            # Max diff column (overall)
            if res.name == ref_name:
                max_diff_str = '—'
                mean_diff_str = '—'
            elif res.max_abs_diff is not None:
                max_diff_str = f'{res.max_abs_diff:.2e}'
                mean_diff_str = f'{res.mean_abs_diff:.2e}' if res.mean_abs_diff is not None else '—'
            else:
                max_diff_str = '—'
                mean_diff_str = '—'

            # Build row based on mode
            if has_fwd_bwd:
                # Autograd mode: kernel, forward_match, grad_match, max|Δ|, mean|Δ|, fwd_max|Δ|, bwd_max|Δ|
                fwd_max_diff = res.diagnostics.get('fwd_max_diff')
                fwd_mean_diff = res.diagnostics.get('fwd_mean_diff')
                bwd_diff = res.diagnostics.get('bwd_max_diff')
                grad_match = res.diagnostics.get('grad_match')

                if res.name == ref_name:
                    grad_match_str = '—'
                elif grad_match is True:
                    grad_match_str = '✓'
                elif grad_match is False:
                    grad_match_str = '✗'
                else:
                    grad_match_str = '—'

                fwd_diff_str = f'{fwd_max_diff:.2e}' if fwd_max_diff is not None and res.name != ref_name else '—'
                bwd_diff_str = f'{bwd_diff:.2e}' if bwd_diff is not None and res.name != ref_name else '—'

                row = [res.name, fwd_match_str, grad_match_str, max_diff_str, mean_diff_str, fwd_diff_str, bwd_diff_str]
            else:
                # Forward only mode: kernel, forward_match, max|Δ|, mean|Δ|
                row = [res.name, fwd_match_str, max_diff_str, mean_diff_str]

            # Notes column - minimal info
            if res.name == ref_name:
                notes_str = 'reference'
            elif res.matches is True:
                notes_str = '—'
            elif res.matches is False:
                notes_str = 'FAIL'
            else:
                notes_str = '—'

            row.append(notes_str)
            val_rows.append(row)

        lines.append(render_table(val_headers, val_rows, align=val_align))

    return '\n'.join(lines)
