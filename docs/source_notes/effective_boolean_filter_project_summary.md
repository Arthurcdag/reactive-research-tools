# Effective Boolean Filter project summary

## Core thesis

Truth/effect is not only the word "yes"; it is the preserved effect of a tested structure.

The system treats:

```text
yes = no(no)
```

only when the negations are tracked, scoped, and applied to the same object.

## Main rule

```text
No untracked polarity shifts.
```

## Why this matters

The system should distinguish:

```text
not not P -> effective_yes
```

from:

```text
no evidence against P -> unknown
```

because the second is epistemic absence of disproof, not ontological proof.

## Architecture

```text
raw argument
-> structured claim extraction
-> deterministic polarity/scope/contradiction engine
-> reactive probe generation
-> scoring
-> report
```

## Output

The report should contain:
- effective polarity,
- bogusness score,
- effectiveness score,
- polarity trace,
- detected issues,
- recommended probes,
- score breakdown.

## Scientific framing

AI generates a large space of candidate hypotheses. The scientific part is the filter:
which candidates preserve structure, survive probes, produce measurable effects, and remain useful across contexts.
