#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, Counter
from pathlib import Path


def load_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def key(row: dict) -> tuple[str, str, str]:
    return (str(row["c"]), str(row["n"]), str(row["d"]))


def as_int(x, default=0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def as_float_or_none(x):
    try:
        if x in ("", None):
            return None
        return float(x)
    except Exception:
        return None


def merge_rows(base_rows: list[dict], deep_rows: list[dict], *, residual_gate: float | None) -> list[dict]:
    deep_map = {key(r): r for r in deep_rows}
    merged = []

    for r in base_rows:
        rr = dict(r)
        drow = deep_map.get(key(rr))

        base_deficit = rr.get("real_root_deficit", "")
        base_state = rr.get("endpoint_state", "")
        base_loc = rr.get("defect_location", "")

        cert_source = "fast_numpy"
        cert_status = "unverified"
        cert_deficit = base_deficit
        cert_state = base_state
        cert_loc = base_loc
        cert_reason = "no_deepcheck_available"

        rr.update({
            "deep_source": "",
            "deep_real_root_deficit": "",
            "deep_endpoint_state": "",
            "deep_defect_location": "",
            "deep_match_lo": "",
            "deep_match_old_hi": "",
            "deep_method": "",
            "deep_max_rel_residual": "",
            "deep_median_rel_residual": "",
            "deep_seconds": "",
        })

        if drow is not None:
            max_res = drow.get("max_rel_residual", "")
            rr.update({
                "deep_source": drow.get("source", ""),
                "deep_real_root_deficit": drow.get("deep_real_root_deficit", ""),
                "deep_endpoint_state": drow.get("deep_endpoint_state", ""),
                "deep_defect_location": drow.get("deep_defect_location", ""),
                "deep_match_lo": drow.get("match_lo", ""),
                "deep_match_old_hi": drow.get("match_old_hi", ""),
                "deep_method": drow.get("method", ""),
                "deep_max_rel_residual": max_res,
                "deep_median_rel_residual": drow.get("median_rel_residual", ""),
                "deep_seconds": drow.get("seconds", ""),
            })

            if drow.get("status") != "ok":
                cert_status = "deepcheck_failed"
                cert_reason = drow.get("error", "deepcheck_failed")
            else:
                max_res_f = as_float_or_none(max_res)
                residual_ok = residual_gate is None or (max_res_f is not None and max_res_f <= residual_gate)

                if residual_ok:
                    cert_source = "deep_scaled_polyroots"
                    cert_status = "deepcheck_ok"
                    cert_deficit = drow.get("deep_real_root_deficit", base_deficit)
                    cert_state = drow.get("deep_endpoint_state", base_state)
                    cert_loc = drow.get("deep_defect_location", base_loc)
                    cert_reason = "accepted_deepcheck"
                else:
                    cert_status = "deepcheck_residual_rejected"
                    cert_reason = f"max_rel_residual={max_res}"

        rr["certified_real_root_deficit"] = cert_deficit
        rr["certified_endpoint_state"] = cert_state
        rr["certified_defect_location"] = cert_loc
        rr["certified_source"] = cert_source
        rr["certified_status"] = cert_status
        rr["certified_reason"] = cert_reason

        merged.append(rr)

    return merged


def frontier_from_rows(rows: list[dict]) -> list[dict]:
    by_c = defaultdict(list)
    for r in rows:
        by_c[str(r["c"])].append(r)

    out = []
    for c, grp in sorted(by_c.items(), key=lambda kv: float(kv[0])):
        grp = sorted(grp, key=lambda r: int(float(r["n"])))
        defects = [r for r in grp if as_int(r.get("certified_real_root_deficit")) > 0]
        first = defects[0] if defects else None

        status_counts = Counter(r.get("certified_status", "") for r in grp)
        source_counts = Counter(r.get("certified_source", "") for r in grp)
        loc_counts = Counter(r.get("certified_defect_location", "") for r in defects)

        out.append({
            "c": c,
            "row_count": len(grp),
            "defect_rows": len(defects),
            "first_defect_n": "" if first is None else first["n"],
            "first_defect_d": "" if first is None else first["d"],
            "first_defect_deficit": "" if first is None else first["certified_real_root_deficit"],
            "first_defect_location": "" if first is None else first["certified_defect_location"],
            "certified_status_counts": json.dumps(dict(status_counts), sort_keys=True),
            "certified_source_counts": json.dumps(dict(source_counts), sort_keys=True),
            "certified_location_counts": json.dumps(dict(loc_counts), sort_keys=True),
        })

    return out


def write_markdown(summary: dict, frontier: list[dict], path: Path) -> None:
    lines = []
    lines.append("# Xi-Jensen certified merge report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for k, v in summary.items():
        if k != "config":
            lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for k, v in summary["config"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Certified frontier")
    lines.append("")
    lines.append("| c | rows | defects | first n | first d | first deficit | first loc | source counts | status counts |")
    lines.append("|---:|---:|---:|---:|---:|---:|---|---|---|")
    for r in frontier:
        lines.append(
            f"| {r['c']} | {r['row_count']} | {r['defect_rows']} | "
            f"{r['first_defect_n']} | {r['first_defect_d']} | {r['first_defect_deficit']} | "
            f"{r['first_defect_location']} | `{r['certified_source_counts']}` | `{r['certified_status_counts']}` |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description="Merge fast dashboard rows with deepcheck rows into certified output")
    p.add_argument("--rows", default="xi_jensen_dashboard_rows.csv", help="Fast dashboard rows CSV")
    p.add_argument("--deepcheck", default="xi_jensen_deepcheck_results.csv", help="Deepcheck results CSV")
    p.add_argument("--prefix", default="xi_jensen_certified")
    p.add_argument("--residual-gate", type=float, default=None, help="Accept deepcheck only if max residual <= gate")
    return p.parse_args()


def main():
    args = parse_args()

    base_rows = load_csv(Path(args.rows))
    deep_rows = load_csv(Path(args.deepcheck))

    if not base_rows:
        raise SystemExit(f"No base rows found in {args.rows}")
    if not deep_rows:
        raise SystemExit(f"No deepcheck rows found in {args.deepcheck}")

    merged = merge_rows(base_rows, deep_rows, residual_gate=args.residual_gate)
    frontier = frontier_from_rows(merged)

    prefix = Path(args.prefix)
    rows_out = prefix.with_name(prefix.name + "_rows.csv")
    frontier_out = prefix.with_name(prefix.name + "_frontier.csv")
    summary_out = prefix.with_name(prefix.name + "_summary.json")
    report_out = prefix.with_name(prefix.name + "_report.md")

    write_csv(merged, rows_out)
    write_csv(frontier, frontier_out)

    deep_ok = [r for r in deep_rows if r.get("status") == "ok"]
    deep_failed = [r for r in deep_rows if r.get("status") == "failed"]
    accepted_deep = [r for r in merged if r.get("certified_source") == "deep_scaled_polyroots"]
    unverified = [r for r in merged if r.get("certified_status") == "unverified"]

    summary = {
        "base_rows": len(base_rows),
        "deepcheck_rows": len(deep_rows),
        "deepcheck_ok": len(deep_ok),
        "deepcheck_failed": len(deep_failed),
        "accepted_deep_rows": len(accepted_deep),
        "unverified_rows": len(unverified),
        "frontier_c_count": len(frontier),
        "config": {
            "rows": args.rows,
            "deepcheck": args.deepcheck,
            "prefix": args.prefix,
            "residual_gate": args.residual_gate,
        },
    }

    summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(summary, frontier, report_out)

    print(json.dumps({
        "summary": summary,
        "outputs": {
            "rows": str(rows_out),
            "frontier": str(frontier_out),
            "summary": str(summary_out),
            "report": str(report_out),
        }
    }, indent=2))


if __name__ == "__main__":
    main()
