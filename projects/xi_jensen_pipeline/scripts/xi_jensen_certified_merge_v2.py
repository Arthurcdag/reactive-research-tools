#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open('r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fields = list(rows[0].keys())
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def key(row: dict) -> tuple[str, str, str]:
    return (str(row['c']), str(row['n']), str(row['d']))


def as_int(x, default=0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def as_float_or_none(x):
    try:
        if x in ('', None):
            return None
        return float(x)
    except Exception:
        return None


def choose_deepcheck_rows(paths: list[Path]) -> dict[tuple[str, str, str], dict]:
    """Choose best deepcheck row per (c,n,d). Prefer ok rows, then lower residual."""
    scored: dict[tuple[str, str, str], tuple[tuple, dict]] = {}
    ordinal = 0

    def score(r: dict, ordinal: int):
        ok_rank = 0 if r.get('status') == 'ok' else 1
        res = as_float_or_none(r.get('max_rel_residual', ''))
        if res is None:
            res = float('inf')
        return (ok_rank, res, -ordinal)

    for path in paths:
        for row in load_csv(path):
            ordinal += 1
            k = key(row)
            s = score(row, ordinal)
            if k not in scored or s < scored[k][0]:
                scored[k] = (s, row)

    return {k: r for k, (_, r) in scored.items()}


def current_certified_label(row: dict) -> dict:
    has_cert = 'certified_real_root_deficit' in row
    return {
        'deficit': row.get('certified_real_root_deficit', row.get('real_root_deficit', '')),
        'state': row.get('certified_endpoint_state', row.get('endpoint_state', '')),
        'location': row.get('certified_defect_location', row.get('defect_location', '')),
        'source': row.get('certified_source', 'fast_numpy' if not has_cert else ''),
        'status': row.get('certified_status', 'unverified'),
        'reason': row.get('certified_reason', 'initial_fast_label' if not has_cert else ''),
    }


def merge_rows(base_rows: list[dict], deep_map: dict[tuple[str, str, str], dict], *, residual_gate: float | None) -> list[dict]:
    merged = []

    for row in base_rows:
        rr = dict(row)
        cur = current_certified_label(rr)
        drow = deep_map.get(key(rr))

        cert_deficit = cur['deficit']
        cert_state = cur['state']
        cert_loc = cur['location']
        cert_source = cur['source'] or 'fast_numpy'
        cert_status = cur['status'] or 'unverified'
        cert_reason = cur['reason'] or 'preserved_existing_certification'

        latest_status = ''
        latest_error = ''
        latest_method = ''
        latest_max_res = ''
        latest_median_res = ''
        latest_seconds = ''
        latest_match_previous = ''

        rr.setdefault('deep_source', '')
        rr.setdefault('deep_real_root_deficit', '')
        rr.setdefault('deep_endpoint_state', '')
        rr.setdefault('deep_defect_location', '')
        rr.setdefault('deep_match_lo', '')
        rr.setdefault('deep_match_old_hi', '')

        if drow is not None:
            latest_status = drow.get('status', '')
            latest_error = drow.get('error', '')
            latest_method = drow.get('method', '')
            latest_max_res = drow.get('max_rel_residual', '')
            latest_median_res = drow.get('median_rel_residual', '')
            latest_seconds = drow.get('seconds', '')

            rr['deep_source'] = drow.get('source', '')
            rr['deep_real_root_deficit'] = drow.get('deep_real_root_deficit', '')
            rr['deep_endpoint_state'] = drow.get('deep_endpoint_state', '')
            rr['deep_defect_location'] = drow.get('deep_defect_location', '')
            rr['deep_match_lo'] = drow.get('match_lo', '')
            rr['deep_match_old_hi'] = drow.get('match_old_hi', '')

            if drow.get('status') != 'ok':
                if cert_status == 'unverified':
                    cert_status = 'deepcheck_failed'
                    cert_reason = latest_error or 'deepcheck_failed'
                else:
                    cert_reason = f'preserved_existing_after_failed_deepcheck: {latest_error}'
            else:
                max_res_f = as_float_or_none(latest_max_res)
                residual_ok = residual_gate is None or (max_res_f is not None and max_res_f <= residual_gate)

                deep_deficit = drow.get('deep_real_root_deficit', '')
                deep_state = drow.get('deep_endpoint_state', '')
                deep_loc = drow.get('deep_defect_location', '')

                latest_match_previous = (
                    str(deep_deficit) == str(cert_deficit)
                    and str(deep_state) == str(cert_state)
                    and str(deep_loc) == str(cert_loc)
                )

                if residual_ok:
                    cert_deficit = deep_deficit
                    cert_state = deep_state
                    cert_loc = deep_loc
                    cert_source = 'deep_scaled_polyroots'
                    cert_status = 'deepcheck_ok'
                    cert_reason = 'accepted_latest_deepcheck'
                else:
                    if cert_status == 'unverified':
                        cert_status = 'deepcheck_residual_rejected'
                        cert_reason = f'max_rel_residual={latest_max_res}'
                    else:
                        cert_reason = f'preserved_existing_after_residual_rejection: max_rel_residual={latest_max_res}'

        rr['latest_deepcheck_status'] = latest_status
        rr['latest_deepcheck_error'] = latest_error
        rr['latest_deepcheck_method'] = latest_method
        rr['latest_deepcheck_max_rel_residual'] = latest_max_res
        rr['latest_deepcheck_median_rel_residual'] = latest_median_res
        rr['latest_deepcheck_seconds'] = latest_seconds
        rr['latest_deepcheck_match_previous_cert'] = latest_match_previous

        rr['certified_real_root_deficit'] = cert_deficit
        rr['certified_endpoint_state'] = cert_state
        rr['certified_defect_location'] = cert_loc
        rr['certified_source'] = cert_source
        rr['certified_status'] = cert_status
        rr['certified_reason'] = cert_reason

        merged.append(rr)

    return merged


def frontier_from_rows(rows: list[dict]) -> list[dict]:
    by_c = defaultdict(list)
    for r in rows:
        by_c[str(r['c'])].append(r)

    out = []
    for c, grp in sorted(by_c.items(), key=lambda kv: float(kv[0])):
        grp = sorted(grp, key=lambda r: int(float(r['n'])))
        defects = [r for r in grp if as_int(r.get('certified_real_root_deficit')) > 0]
        first = defects[0] if defects else None

        status_counts = Counter(r.get('certified_status', '') for r in grp)
        source_counts = Counter(r.get('certified_source', '') for r in grp)
        loc_counts = Counter(r.get('certified_defect_location', '') for r in defects)

        out.append({
            'c': c,
            'row_count': len(grp),
            'defect_rows': len(defects),
            'first_defect_n': '' if first is None else first['n'],
            'first_defect_d': '' if first is None else first['d'],
            'first_defect_deficit': '' if first is None else first['certified_real_root_deficit'],
            'first_defect_location': '' if first is None else first['certified_defect_location'],
            'certified_status_counts': json.dumps(dict(status_counts), sort_keys=True),
            'certified_source_counts': json.dumps(dict(source_counts), sort_keys=True),
            'certified_location_counts': json.dumps(dict(loc_counts), sort_keys=True),
        })

    return out


def write_markdown(summary: dict, frontier: list[dict], path: Path) -> None:
    lines = ['# Xi-Jensen certified merge v2 report', '', '## Summary', '']
    for k, v in summary.items():
        if k != 'config':
            lines.append(f'- `{k}`: `{v}`')
    lines += ['', '## Config', '']
    for k, v in summary['config'].items():
        lines.append(f'- `{k}`: `{v}`')
    lines += ['', '## Frontier', '', '| c | rows | defects | first n | first d | first deficit | first loc | source counts | status counts |', '|---:|---:|---:|---:|---:|---:|---|---|---|']
    for r in frontier:
        lines.append(
            f"| {r['c']} | {r['row_count']} | {r['defect_rows']} | {r['first_defect_n']} | {r['first_defect_d']} | {r['first_defect_deficit']} | {r['first_defect_location']} | `{r['certified_source_counts']}` | `{r['certified_status_counts']}` |"
        )
    path.write_text('\n'.join(lines), encoding='utf-8')


def parse_args():
    p = argparse.ArgumentParser(description='Iteration-safe certified merge for Xi-Jensen rows')
    p.add_argument('--rows', default='xi_jensen_certified_rows.csv')
    p.add_argument('--deepcheck', nargs='+', required=True, help='One or more deepcheck/certification batch result CSVs')
    p.add_argument('--prefix', default='xi_jensen_certified_v2')
    p.add_argument('--residual-gate', type=float, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    base_rows = load_csv(Path(args.rows))
    if not base_rows:
        raise SystemExit(f'No rows found in {args.rows}')

    deep_paths = [Path(p) for p in args.deepcheck]
    deep_map = choose_deepcheck_rows(deep_paths)

    merged = merge_rows(base_rows, deep_map, residual_gate=args.residual_gate)
    frontier = frontier_from_rows(merged)

    prefix = Path(args.prefix)
    rows_out = prefix.with_name(prefix.name + '_rows.csv')
    frontier_out = prefix.with_name(prefix.name + '_frontier.csv')
    summary_out = prefix.with_name(prefix.name + '_summary.json')
    report_out = prefix.with_name(prefix.name + '_report.md')

    write_csv(merged, rows_out)
    write_csv(frontier, frontier_out)

    accepted_deep = [r for r in merged if r.get('certified_source') == 'deep_scaled_polyroots']
    unverified = [r for r in merged if r.get('certified_status') == 'unverified']
    failed = [r for r in merged if r.get('certified_status') == 'deepcheck_failed']
    latest_changed = [r for r in merged if str(r.get('latest_deepcheck_match_previous_cert')).lower() == 'false']

    summary = {
        'base_rows': len(base_rows),
        'deepcheck_keys_loaded': len(deep_map),
        'accepted_deep_total': len(accepted_deep),
        'unverified_rows': len(unverified),
        'deepcheck_failed_rows': len(failed),
        'latest_changed_previous_cert': len(latest_changed),
        'frontier_c_count': len(frontier),
        'config': {
            'rows': args.rows,
            'deepcheck': args.deepcheck,
            'prefix': args.prefix,
            'residual_gate': args.residual_gate,
        },
    }

    summary_out.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    write_markdown(summary, frontier, report_out)

    print(json.dumps({'summary': summary, 'outputs': {'rows': str(rows_out), 'frontier': str(frontier_out), 'summary': str(summary_out), 'report': str(report_out)}}, indent=2))


if __name__ == '__main__':
    main()
