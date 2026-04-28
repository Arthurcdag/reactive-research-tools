#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_csv(path: Path) -> list[dict]:
    with path.open('r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def as_int(x, default=0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def bucket(d: int, width: int = 10) -> str:
    lo = (d // width) * width
    return f'{lo:03d}-{lo + width - 1:03d}'


def candidate_score(row: dict) -> tuple:
    status = row.get('certified_status', '')
    unverified_rank = 0 if status == 'unverified' else 1
    d = as_int(row.get('d'))
    n = as_int(row.get('n'))
    try:
        min_im = float(row.get('min_nonreal_abs_imag', 'inf'))
    except Exception:
        min_im = float('inf')
    return (unverified_rank, -d, min_im, n)


def analyze(rows: list[dict], *, limit: int) -> tuple[dict, list[dict]]:
    status_counts = Counter(r.get('certified_status', '') for r in rows)
    source_counts = Counter(r.get('certified_source', '') for r in rows)

    by_c = defaultdict(lambda: Counter())
    by_bucket = defaultdict(lambda: Counter())

    for r in rows:
        c = str(r.get('c'))
        d = as_int(r.get('d'))
        status = r.get('certified_status', '')
        by_c[c][status] += 1
        by_bucket[bucket(d)][status] += 1

    pool = [r for r in rows if r.get('certified_status', '') in {'unverified', 'deepcheck_failed', 'deepcheck_residual_rejected'}]
    candidates = sorted(pool, key=candidate_score)[:limit]

    summary = {
        'row_count': len(rows),
        'status_counts': dict(status_counts),
        'source_counts': dict(source_counts),
        'by_c': {k: dict(v) for k, v in sorted(by_c.items(), key=lambda kv: float(kv[0]))},
        'by_d_bucket': {k: dict(v) for k, v in sorted(by_bucket.items())},
        'candidate_count_total': len(pool),
        'candidate_preview_count': len(candidates),
    }
    return summary, candidates


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fields = list(rows[0].keys())
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_markdown(summary: dict, candidates: list[dict], path: Path) -> None:
    lines = []
    lines.append('# Xi-Jensen certification status')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append(f"- rows: `{summary['row_count']}`")
    lines.append(f"- status counts: `{summary['status_counts']}`")
    lines.append(f"- source counts: `{summary['source_counts']}`")
    lines.append(f"- total remaining candidates: `{summary['candidate_count_total']}`")
    lines.append('')
    lines.append('## By c')
    lines.append('')
    for c, counts in summary['by_c'].items():
        lines.append(f'- c=`{c}`: `{counts}`')
    lines.append('')
    lines.append('## By degree bucket')
    lines.append('')
    for b, counts in summary['by_d_bucket'].items():
        lines.append(f'- d=`{b}`: `{counts}`')
    lines.append('')
    lines.append('## Candidate preview')
    lines.append('')
    for r in candidates:
        lines.append(
            f"- c={r.get('c')} n={r.get('n')} d={r.get('d')} "
            f"status={r.get('certified_status')} loc={r.get('certified_defect_location')} "
            f"min_im={r.get('min_nonreal_abs_imag')}"
        )
    path.write_text('\n'.join(lines), encoding='utf-8')


def parse_args():
    p = argparse.ArgumentParser(description='Summarize certification coverage and propose next candidates')
    p.add_argument('--rows', default='xi_jensen_certified_rows.csv')
    p.add_argument('--prefix', default='xi_jensen_certification_status')
    p.add_argument('--limit', type=int, default=50)
    return p.parse_args()


def main():
    args = parse_args()
    rows = load_csv(Path(args.rows))
    summary, candidates = analyze(rows, limit=args.limit)

    prefix = Path(args.prefix)
    json_path = prefix.with_suffix('.summary.json')
    md_path = prefix.with_suffix('.md')
    candidates_path = prefix.with_name(prefix.name + '_candidates.csv')

    json_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    write_markdown(summary, candidates, md_path)
    write_csv(candidates, candidates_path)

    print(json.dumps({
        'summary': summary,
        'outputs': {
            'summary_json': str(json_path),
            'markdown': str(md_path),
            'candidates': str(candidates_path),
        },
    }, indent=2))


if __name__ == '__main__':
    main()
