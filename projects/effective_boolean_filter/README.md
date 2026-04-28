# Effective Boolean Argument Filter

A traceable filter for arguments, claims, and generated hypotheses.

It is designed for an AI-assisted hypothesis pipeline where AI generates many candidate arguments, but acceptance depends on measurable structural preservation and reactive performance.

## Core principle

```text
No untracked polarity shifts.
```

An argument should only get credit for a yes/no conclusion if the transformations that produce that conclusion are tracked.

Examples:

```text
not not P -> effective_yes
```

but:

```text
no evidence against P -> unknown
```

because `no evidence against P` is closer to:

```text
not known(not P)
```

not:

```text
not not P
```

## MVP CLI

```bash
python cli.py \
  --claim "This method proves X" \
  --argument "There is no evidence against X, therefore X is true" \
  --context "scientific argument"
```

## Output concepts

- `effective_yes`
- `effective_no`
- `unknown`
- `unstable`
- `untracked_shift`
- `contradiction`

## Scoring dimensions

- negation consistency
- scope preservation
- definition stability
- context fit
- contradiction containment
- reactive performance
- testability
- implementation relevance

## Dev milestones

1. Core schema and polarity parser
2. Scope and contradiction handling
3. Reactive probe generator
4. API wrapper
5. Benchmark set and calibration
