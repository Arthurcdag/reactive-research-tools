#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def degree_bucket(d: int, width: int = 10) -> str:
    lo = (d // width) * width
    hi = lo + width - 1
    return f"{lo:03d}-{hi:03d}"


def row_key(r: dict) -> tuple[str, str, str]:
    return (str(r.get("c")), str(r.get("n")), str(r.get("d")))


def analyze(results: list[dict], original_rows: list[dict] | None = None) -> dict:
    ok = [r for r in results if r.get("status") == "ok"]
    failed = [r for r in results if r.get("status") == "failed"]
    mismatches = [r for r in ok if str(r.get("verified_match")).lower() == "false"]
    matches = [r for r in ok if str(r.get("verified_match")).lower() == "true"]

    by_c = defaultdict(lambda: Counter())
    by_d_bucket = defaultdict(lambda: Counter())
    mismatch_type = Counter()
    failures_by_error = Counter()

    for r in results:
        c = str(r.get("c"))
        d = int(float(r.get("d")))
        bucket = degree_bucket(d)

        if r.get("status") == "failed":
            by_c[c]["failed"] += 1
            by_d_bucket[bucket]["failed"] += 1
            failures_by_error[str(r.get("error", ""))[:160]] += 1
            continue

        if str(r.get("verified_match")).lower() == "true":
            by_c[c]["match"] += 1
            by_d_bucket[bucket]["match"] += 1
        else:
            by_c[c]["mismatch"] += 1
            by_d_bucket[bucket]["mismatch"] += 1

            if str(r.get("lo_real_root_deficit")) != str(r.get("hi_real_root_deficit")):
                mismatch_type["deficit"] += 1
            if str(r.get("lo_endpoint_state")) != str(r.get("hi_endpoint_state")):
                mismatch_type["endpoint_state"] += 1
            if str(r.get("lo_defect_location")) != str(r.get("hi_defect_location")):
                mismatch_type["defect_location"] += 1

    original_map = {}
    if original_rows is not None:
        original_map = {row_key(r): r for r in original_rows}

    enriched_mismatches = []
    for r in mismatches:
        entry = dict(r)
        orig = original_map.get(row_key(r))
        if orig:
            entry["original_min_nonreal_abs_imag"] = orig.get("min_nonreal_abs_imag")
            entry["original_sensitive"] = orig.get("sensitive")
        enriched_mismatches.append(entry)

    return {
        "total_results": len(results),
        "ok": len(ok),
        "matches": len(matches),
        "mismatches": len(mismatches),
        "failed": len(failed),
        "mismatch_type": dict(mismatch_type),
        "by_c": {k: dict(v) for k, v in sorted(by_c.items())},
        "by_d_bucket": {k: dict(v) for k, v in sorted(by_d_bucket.items())},
        "failures_by_error": dict(failures_by_error),
        "first_20_mismatches": enriched_mismatches[:20],
        "first_20_failures": failed[:20],
    }


def write_markdown(summary: dict, path: Path) -> None:
    lines = []
    lines.append("# Xi-Jensen verification triage")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- total results: `{summary['total_results']}`")
    lines.append(f"- ok: `{summary['ok']}`")
    lines.append(f"- matches: `{summary['matches']}`")
    lines.append(f"- mismatches: `{summary['mismatches']}`")
    lines.append(f"- failed: `{summary['failed']}`")
    lines.append("")
    lines.append("## Mismatch types")
    lines.append("")
    if summary["mismatch_type"]:
        for k, v in summary["mismatch_type"].items():
            lines.append(f"- `{k}`: `{v}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## By c")
    lines.append("")
    for c, counts in summary["by_c"].items():
        lines.append(f"- c=`{c}`: `{counts}`")
    lines.append("")
    lines.append("## By degree bucket")
    lines.append("")
    for b, counts in summary["by_d_bucket"].items():
        lines.append(f"- d=`{b}`: `{counts}`")
    lines.append("")
    lines.append("## Failure errors")
    lines.append("")
    if summary["failures_by_error"]:
        for e, count in summary["failures_by_error"].items():
            lines.append(f"- `{count}` x `{e}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## First mismatches")
    lines.append("")
    if summary["first_20_mismatches"]:
        for r in summary["first_20_mismatches"]:
            lines.append(
                f"- c={r.get('c')}, n={r.get('n')}, d={r.get('d')}: "
                f"deficit {r.get('lo_real_root_deficit')}->{r.get('hi_real_root_deficit')}, "
                f"state {r.get('lo_endpoint_state')}->{r.get('hi_endpoint_state')}, "
                f"loc {r.get('lo_defect_location')}->{r.get('hi_defect_location')}, "
                f"min_im={r.get('original_min_nonreal_abs_imag', '')}"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## First failures")
    lines.append("")
    if summary["first_20_failures"]:
        for r in summary["first_20_failures"]:
            lines.append(f"- c={r.get('c')}, n={r.get('n')}, d={r.get('d')}: `{r.get('error')}`")
    else:
        lines.append("- none")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_rows(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted(set().union(*(r.keys() for r in rows)))
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def parse_args():
    p = argparse.ArgumentParser(description="Analyze xi_jensen_verify_queue results")
    p.add_argument("--verify-results", default="xi_jensen_verify_queue_results.csv")
    p.add_argument("--rows", default=None, help="Optional original dashboard rows CSV")
    p.add_argument("--prefix", default="xi_jensen_verify_triage")
    return p.parse_args()


def main():
    args = parse_args()
    results = load_csv(Path(args.verify_results))
    original = load_csv(Path(args.rows)) if args.rows else None

    summary = analyze(results, original)

    prefix = Path(args.prefix)
    json_path = prefix.with_suffix(".summary.json")
    md_path = prefix.with_suffix(".md")
    mismatches_path = prefix.with_name(prefix.name + "_mismatches.csv")
    failures_path = prefix.with_name(prefix.name + "_failures.csv")

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(summary, md_path)

    mismatches = [r for r in results if r.get("status") == "ok" and str(r.get("verified_match")).lower() == "false"]
    failures = [r for r in results if r.get("status") == "failed"]

    write_rows(mismatches, mismatches_path)
    write_rows(failures, failures_path)

    print(json.dumps({
        "total_results": summary["total_results"],
        "ok": summary["ok"],
        "matches": summary["matches"],
        "mismatches": summary["mismatches"],
        "failed": summary["failed"],
        "outputs": {
            "summary_json": str(json_path),
            "markdown": str(md_path),
            "mismatches_csv": str(mismatches_path),
            "failures_csv": str(failures_path),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
