#!/usr/bin/env python3
"""
xi_jensen_fast_campaign.py

Batch campaign runner for the fast Xi–Jensen experiment stack.

What it does
------------
Runs a list of presets from xi_jensen_fast_experiments.py, writes:
- one CSV per preset
- one JSON summary per preset
- one combined campaign summary JSON
- one human-readable markdown report

This is meant to be the "leave it running and inspect later" entry point.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import xi_jensen_fast_experiments as EXP


CAMPAIGNS: dict[str, list[str]] = {
    "core": [
        "client_full",
        "c070_extended",
        "c060_extended",
    ],
    "threshold": [
        "threshold_band_extended",
    ],
    "all": [
        "client_full",
        "c070_extended",
        "c060_extended",
        "threshold_band_extended",
    ],
}


def run_preset(preset: str, verify_sensitive_override: bool | None = None) -> dict:
    cfg = EXP.PRESETS[preset].copy()
    if cfg["max_gamma_index"] is None:
        cfg["max_gamma_index"] = EXP.auto_max_gamma_index(cfg["c_values"], cfg["n_values"])

    if verify_sensitive_override is not None:
        cfg["verify_sensitive"] = verify_sensitive_override

    out_csv = Path(cfg["out_csv"])
    summary_json = out_csv.with_suffix(".summary.json")

    print(f"\n=== Running preset: {preset} ===")
    print("Config:", cfg)

    gammas = EXP.F.xi_gammas_cached(
        max_index=cfg["max_gamma_index"],
        dps=cfg["dps"],
        cache_dir=".gamma_cache",
        verbose=False,
    )

    rows = []
    for c in cfg["c_values"]:
        rows.extend(
            EXP.scan_ray_detailed(
                gammas,
                c,
                cfg["n_values"],
                verify_sensitive=cfg["verify_sensitive"],
                verify_factor=50.0,
                hi_dps=150,
            )
        )

    if rows:
        EXP.write_detailed_csv(rows, out_csv)

    summary = {
        "preset": preset,
        "config": cfg,
        "summary": EXP.summarize_detailed_rows(rows),
        "out_csv": str(out_csv),
        "out_csv_md5_normalized": EXP.md5_normalized_csv(out_csv) if rows else None,
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_csv}")
    print(f"Wrote {summary_json}")
    return summary


def write_markdown_report(campaign_name: str, results: list[dict], path: Path) -> None:
    lines = []
    lines.append(f"# Xi–Jensen fast campaign report: {campaign_name}")
    lines.append("")
    for result in results:
        preset = result["preset"]
        cfg = result["config"]
        s = result["summary"]
        lines.append(f"## {preset}")
        lines.append("")
        lines.append(f"- output CSV: `{result['out_csv']}`")
        lines.append(f"- normalized MD5: `{result['out_csv_md5_normalized']}`")
        lines.append(f"- row count: `{s['row_count']}`")
        lines.append(f"- defect rows: `{s['defect_rows']}`")
        lines.append(f"- sensitive rows: `{s['sensitive_rows']}`")
        lines.append(f"- verified rows: `{s['verified_rows']}`")
        lines.append(f"- verification mismatches: `{s['verification_mismatches']}`")
        lines.append(f"- c-values: `{cfg['c_values']}`")
        lines.append(f"- n-range: `{cfg['n_values'][0]}..{cfg['n_values'][-1]}`")
        lines.append(f"- max_gamma_index: `{cfg['max_gamma_index']}`")
        if s["first_defect"] is not None:
            fd = s["first_defect"]
            lines.append(
                f"- first defect: `c={fd['c']}, n={fd['n']}, d={fd['d']}, "
                f"deficit={fd['real_root_deficit']}, "
                f"loc={fd['defect_location']}`"
            )
        lines.append("")
        if "by_c" in s:
            lines.append("### by c")
            lines.append("")
            for c_key, cs in s["by_c"].items():
                lines.append(
                    f"- c={c_key}: rows={cs['row_count']}, defects={cs['defect_rows']}, "
                    f"sensitive={cs['sensitive_rows']}, verified={cs['verified_rows']}, "
                    f"mismatches={cs['verification_mismatches']}"
                )
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description="Batch campaign runner for xi_jensen_fast_experiments")
    p.add_argument("--campaign", choices=sorted(CAMPAIGNS.keys()), default="core")
    p.add_argument("--no-verify-sensitive", action="store_true", help="Disable targeted verification for every preset")
    return p.parse_args()


def main():
    args = parse_args()
    presets = CAMPAIGNS[args.campaign]

    verify_override = False if args.no_verify_sensitive else None

    results = []
    for preset in presets:
        results.append(run_preset(preset, verify_sensitive_override=verify_override))

    combined = {
        "campaign": args.campaign,
        "presets": presets,
        "results": results,
    }

    combined_json = Path(f"xi_jensen_campaign_{args.campaign}.json")
    combined_md = Path(f"xi_jensen_campaign_{args.campaign}.md")

    combined_json.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    write_markdown_report(args.campaign, results, combined_md)

    print(f"\nWrote {combined_json}")
    print(f"Wrote {combined_md}")


if __name__ == "__main__":
    main()
