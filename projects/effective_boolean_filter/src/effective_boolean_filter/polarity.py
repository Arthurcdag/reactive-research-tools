"""Deterministic polarity / negation-parity engine.

Spec section 4. The reduction

    N^k(P) = P     if k is even
    N^k(P) = not P if k is odd

is allowed only when the invariants hold: same object, same scope, same
definition, same context, same negation type. This module is the
authoritative trace producer; nothing here is advisory.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schemas import ClaimNode, Issue, Polarity, TransformationStep


INVARIANT_FIELDS = (
    ("object_id", "object"),
    ("scope", "scope"),
    ("definition_id", "definition"),
    ("context_id", "context"),
    ("negation_type", "negation_type"),
)


@dataclass
class PolarityVerdict:
    polarity: Polarity
    invariants_held: bool
    transformation_steps: list[TransformationStep]
    issues: list[Issue]


def _invariant_diffs(a: ClaimNode, b: ClaimNode) -> list[str]:
    diffs: list[str] = []
    for attr, label in INVARIANT_FIELDS:
        va, vb = getattr(a, attr), getattr(b, attr)
        if va == vb:
            continue
        # treat 'unknown' / 'general' / 'default' as wildcards — they carry
        # no information and should not be counted as shifts
        wildcards = {"unknown", "general", "default"}
        if va in wildcards or vb in wildcards:
            continue
        diffs.append(f"{label}: {va!r} -> {vb!r}")
    return diffs


def reduce_negation_parity(node: ClaimNode) -> tuple[Polarity, TransformationStep]:
    """Apply N^k reduction to a single node based on its negation_count.

    A node carries one negation_type. If the count is even, it reduces to the
    base proposition (effective_yes). If odd, it reduces to a single negation
    (effective_no).
    """
    base_obj = node.object_id
    if node.negation_type == "epistemic":
        # epistemic forms are never reduced — they pass through unchanged.
        return (
            "unknown",
            TransformationStep(
                from_node=node.id,
                to_node=node.id,
                transformation_type="epistemic_to_ontological_shift",
                tracked=True,
                reason=(
                    "epistemic negation (e.g. 'no evidence', 'not known') is "
                    "absence-of-evidence and must not collapse to ontological yes"
                ),
                invariants_held=True,
            ),
        )

    if node.negation_count == 0:
        return (
            "effective_yes",
            TransformationStep(
                from_node=node.id,
                to_node=node.id,
                transformation_type="valid_inference",
                tracked=True,
                reason=f"no negations on {base_obj!r}; identity",
            ),
        )

    if node.negation_count % 2 == 0:
        return (
            "effective_yes",
            TransformationStep(
                from_node=node.id,
                to_node=node.id,
                transformation_type="double_negation",
                tracked=True,
                reason=(
                    f"N^{node.negation_count}({base_obj!r}) reduces to "
                    f"{base_obj!r} (even parity, single negation_type)"
                ),
            ),
        )

    return (
        "effective_no",
        TransformationStep(
            from_node=node.id,
            to_node=node.id,
            transformation_type="negation",
            tracked=True,
            reason=(
                f"N^{node.negation_count}({base_obj!r}) reduces to "
                f"not({base_obj!r}) (odd parity)"
            ),
        ),
    )


def cross_node_invariants(
    nodes: list[ClaimNode],
) -> tuple[list[TransformationStep], list[Issue]]:
    """Detect untracked shifts when one node is supposed to reuse another.

    A node is "supposed to reuse another" when both refer to the same
    object_id but disagree on at least one other invariant. That's the
    signature of an untracked shift.
    """
    steps: list[TransformationStep] = []
    issues: list[Issue] = []
    seen: dict[str, ClaimNode] = {}
    for node in nodes:
        if node.object_id == "":
            continue
        prior = seen.get(node.object_id)
        if prior is None:
            seen[node.object_id] = node
            continue
        diffs = _invariant_diffs(prior, node)
        if not diffs:
            continue

        # specialised classifications
        ttype = "context_shift"
        if any(d.startswith("scope:") for d in diffs):
            ttype = "scope_shift"
        if any(d.startswith("definition:") for d in diffs):
            ttype = "definition_shift"
        if any(d.startswith("negation_type:") for d in diffs):
            ttype = "epistemic_to_ontological_shift" if (
                "epistemic" in (prior.negation_type, node.negation_type)
            ) else "modal_shift"

        steps.append(
            TransformationStep(
                from_node=prior.id,
                to_node=node.id,
                transformation_type=ttype,
                tracked=False,
                reason="invariant changed without bridging premise: " + "; ".join(diffs),
                invariants_held=False,
            )
        )
        issues.append(
            Issue(
                code="untracked_shift",
                message=(
                    f"untracked {ttype} on object {node.object_id!r}: "
                    + "; ".join(diffs)
                ),
                severity="error",
                related_node_ids=[prior.id, node.id],
            )
        )
        seen[node.object_id] = node
    return steps, issues


def evaluate_polarity(
    premises: list[ClaimNode],
    conclusion: ClaimNode | None,
) -> PolarityVerdict:
    """Combine per-node parity reduction with cross-node invariant tracking."""
    nodes = list(premises) + ([conclusion] if conclusion else [])
    steps: list[TransformationStep] = []
    issues: list[Issue] = []

    for n in nodes:
        pol, step = reduce_negation_parity(n)
        # mutate the node's polarity to the reduced value when tracked
        n.polarity = pol
        steps.append(step)

    cross_steps, cross_issues = cross_node_invariants(nodes)
    steps.extend(cross_steps)
    issues.extend(cross_issues)

    invariants_held = all(s.invariants_held for s in steps)

    if conclusion is None:
        # bare claim
        polarity = nodes[0].polarity if nodes else "unknown"
    else:
        if any(s.transformation_type == "epistemic_to_ontological_shift" and s.from_node != s.to_node for s in steps):
            polarity = "untracked_shift"
        elif not invariants_held:
            polarity = "untracked_shift"
        elif _conclusion_uses_only_epistemic_premises(premises, conclusion):
            polarity = "untracked_shift"
            issues.append(
                Issue(
                    code="epistemic_to_ontological_shift",
                    message=(
                        "conclusion is ontological but is supported only by "
                        "epistemic absence-of-evidence premises"
                    ),
                    severity="error",
                    related_node_ids=[conclusion.id],
                )
            )
        else:
            polarity = conclusion.polarity

    return PolarityVerdict(
        polarity=polarity,
        invariants_held=invariants_held,
        transformation_steps=steps,
        issues=issues,
    )


def _conclusion_uses_only_epistemic_premises(
    premises: list[ClaimNode],
    conclusion: ClaimNode,
) -> bool:
    """Return True if the conclusion is ontological and is supported by an
    epistemic absence-of-disproof premise.

    We fire on a single epistemic premise (not just the all-epistemic case)
    because the burden-of-proof problem is local to that one premise."""
    if not premises:
        return False
    if conclusion.negation_type == "epistemic":
        return False
    return any(p.negation_type == "epistemic" for p in premises)
