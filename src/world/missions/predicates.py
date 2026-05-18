"""Shared predicate evaluator for the Missions engine (Phase 0).

A predicate is an AND/OR/NOT rule tree whose leaves test the *acting
character's own durable state* (never a target's sheet). The tree mirrors the
shape of ``world.distinctions.models.DistinctionPrerequisite.rule_json`` — a
JSONField AND/OR/NOT structure. No evaluator existed for that model; this is
the first one.

The rule tree is the one sanctioned dynamic-JSON case in this codebase, so
``evaluate`` accepts a plain ``dict`` *input*. It never returns a bare dict.

Rule node grammar (recursive):
    {}                                  -> no gate, evaluates True
    {"op": "AND", "of": [<node>, ...]}  -> all() (empty AND is True)
    {"op": "OR",  "of": [<node>, ...]}  -> any() (empty OR is False)
    {"op": "NOT", "of": [<node>]}       -> not of[0]
    {"leaf": "<name>", "params": {...}} -> ctx.has_leaf(name, **params)

The structural layer here knows nothing about which leaves exist; leaf
resolution is delegated to a ``PredicateContext`` (see ``types.py`` and the
resolver registry below).
"""

from world.missions.types import PredicateContext

# Rule-tree schema keys (the sanctioned dynamic-JSON case — these name the
# structural keys of the AND/OR/NOT tree, not free-form identifiers).
KEY_OP = "op"
KEY_OF = "of"
KEY_LEAF = "leaf"
KEY_PARAMS = "params"

# Boolean-operator discriminator values for KEY_OP.
OP_AND = "AND"
OP_OR = "OR"
OP_NOT = "NOT"


def evaluate(rule: dict, ctx: PredicateContext) -> bool:
    """Evaluate a predicate rule tree against an acting-character context.

    Args:
        rule: An AND/OR/NOT rule-tree node (the sanctioned dynamic-JSON
            case). An empty dict means "no gate" and evaluates True.
        ctx: A read-only durable-state accessor for the acting character.

    Returns:
        Whether the acting character satisfies the rule.

    Raises:
        ValueError: If a node carries an unknown ``op``.
    """
    if not rule:  # {} == no gate
        return True
    if KEY_OP in rule:
        op, of = rule[KEY_OP], rule.get(KEY_OF, [])
        if op == OP_AND:
            return all(evaluate(r, ctx) for r in of)  # empty AND == True
        if op == OP_OR:
            return any(evaluate(r, ctx) for r in of)  # empty OR == False
        if op == OP_NOT:
            return not evaluate(of[0], ctx)
        msg = f"unknown predicate op {op!r}"
        raise ValueError(msg)
    return ctx.has_leaf(rule[KEY_LEAF], **rule.get(KEY_PARAMS, {}))
