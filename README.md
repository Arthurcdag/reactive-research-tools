# Reactive Research Tools

This repository packages the work developed so far into two connected research/tooling tracks.

## 1. Effective Boolean Argument Filter

A traceable argument-effect filter. It is not a truth oracle. It checks whether an argument preserves its yes/no structure under negation, scope, context, contradiction containment, and reactive probes.

Core rule:

> No untracked polarity shifts.

The MVP distinguishes:

```text
not not P -> effective_yes
```

from:

```text
no evidence against P -> unknown, not effective_yes
```

because the second form is epistemic absence-of-disproof, not ontological double negation.

Location:

```text
projects/effective_boolean_filter
```

## 2. Xi–Jensen Certification Pipeline

A numerical/research workflow for fast exploratory scans plus progressively stronger certification.

The workflow evolved into:

```text
fast dashboard scan
-> verification/triage
-> scaled deepcheck
-> certified merge
-> certification batch
-> certified merge v2
-> certification status
-> repeat
```

The key lesson was that fast/numpy roots are useful as a candidate generator, while scaled high-precision deepcheck is the trusted certification layer.

Location:

```text
projects/xi_jensen_pipeline
```

## Repository layout

```text
.
├── docs/
│   ├── developer_briefs/
│   └── source_notes/
├── projects/
│   ├── effective_boolean_filter/
│   └── xi_jensen_pipeline/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
├── GITHUB_SETUP.md
├── requirements.txt
└── README.md
```

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

Run the Effective Boolean Filter MVP:

```bash
python projects/effective_boolean_filter/cli.py \
  --claim "This method proves X" \
  --argument "There is no evidence against X, therefore X is true" \
  --context "scientific argument"
```

Run the Xi–Jensen dashboard if the corresponding generated scripts and dependencies are present:

```bash
python projects/xi_jensen_pipeline/scripts/xi_jensen_frontier_dashboard.py --help
```

## Status

This repo is an initial research/workbench packaging. It contains:
- working MVP code for the argument filter,
- generated developer briefs,
- Xi–Jensen scripts developed during the research session,
- workflow notes,
- issue templates for implementation.

No final scientific claims should be treated as certified unless they pass the stated certification pipeline.
