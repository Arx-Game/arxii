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

Leaf resolvers assume the acting character has a CharacterSheet (true for
every played character per character_sheets/CLAUDE.md); a sheet-less
character is a programmer error and the sheet-keyed resolvers will raise
CharacterSheet.DoesNotExist loudly rather than silently gate.

Phase 0.3 adds the leaf-resolver registry: a mapping of leaf name to a
callable ``(character, **params) -> bool`` that tests the acting
character's own durable state, plus a concrete ``CharacterPredicateContext``
that dispatches ``has_leaf`` through the registry. Resolvers only exist for
descriptor models whose shape was verified by reading the code. The
``min_society_standing`` resolver is stub-sealed: ``world.societies``
reputation is keyed by ``scenes.Persona`` (not character/sheet) and
"standing" is ambiguous, so it raises ``NotImplementedError`` until the
model is confirmed.
"""

from evennia.objects.models import ObjectDB

from world.missions.types import LeafRegistry, LeafResolver, PredicateContext

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
        ValueError: If a node carries an unknown ``op``, or a ``NOT`` node
            does not have exactly one operand.
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
            if len(of) != 1:
                msg = f"NOT requires exactly one operand, got {len(of)}"
                raise ValueError(msg)
            return not evaluate(of[0], ctx)
        msg = f"unknown predicate op {op!r}"
        raise ValueError(msg)
    return ctx.has_leaf(rule[KEY_LEAF], **rule.get(KEY_PARAMS, {}))


# ---------------------------------------------------------------------------
# Leaf resolvers — each tests one slice of the acting character's own durable
# state. ``character`` is the acting Character (ObjectDB). Params are the
# leaf's authored params and are keyword-only. Resolvers must never inspect a
# target's sheet — only the acting character's durable state.
#
# Invariant: the acting character is assumed to have a CharacterSheet (true
# for every played character per character_sheets/CLAUDE.md). A sheet-less
# character is a programmer error: sheet-keyed resolvers (has_achievement,
# has_thread, min_thread_level) access ``character.sheet_data`` and will
# raise CharacterSheet.DoesNotExist loudly rather than silently gate. No
# defensive guard is added on purpose — silently returning False would hide
# the bug.
# ---------------------------------------------------------------------------


def _resolve_has_distinction(character: ObjectDB, *, slug: str) -> bool:
    """True if the character has the Distinction with this slug."""
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    return CharacterDistinction.objects.filter(
        character=character,
        distinction__slug=slug,
    ).exists()


def _resolve_has_achievement(character: ObjectDB, *, slug: str) -> bool:
    """True if the character has earned the Achievement with this slug.

    CharacterAchievement is keyed by CharacterSheet; ``sheet_data`` is the
    OneToOne reverse accessor (shared pk with the character).
    """
    from world.achievements.models import CharacterAchievement  # noqa: PLC0415

    return CharacterAchievement.objects.filter(
        character_sheet=character.sheet_data,
        achievement__slug=slug,
    ).exists()


def _resolve_has_condition(character: ObjectDB, *, key: str) -> bool:
    """True if the character has an active (non-suppressed) condition.

    ``key`` is the (unique) ConditionTemplate.name. Delegates to the
    canonical ``conditions.services.has_condition`` so suppressed instances
    (a row still exists, but its effects don't apply) correctly gate False.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import has_condition  # noqa: PLC0415

    template = ConditionTemplate.objects.filter(name=key).first()
    if template is None:
        return False
    return has_condition(character, template)


def _resolve_has_capability(character: ObjectDB, *, name: str) -> bool:
    """True if the character effectively possesses the named capability.

    Capabilities are additive modifiers granted/removed by active
    conditions. ``conditions.services.get_capability_value`` aggregates them
    and floors at 0, where "0 == effectively blocked / not possessed".
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.conditions.services import get_capability_value  # noqa: PLC0415

    capability = CapabilityType.objects.filter(name=name).first()
    if capability is None:
        return False
    return get_capability_value(character, capability) > 0


def _resolve_has_thread(character: ObjectDB) -> bool:
    """True if the character owns at least one non-retired Thread.

    Thread.owner is a CharacterSheet (``sheet_data`` on the character).
    Retired threads (``retired_at`` set) are excluded from all live paths.
    """
    from world.magic.models import Thread  # noqa: PLC0415

    return Thread.objects.filter(
        owner=character.sheet_data,
        retired_at__isnull=True,
    ).exists()


def _resolve_min_thread_level(character: ObjectDB, *, level: int) -> bool:
    """True if any non-retired Thread the character owns is at >= ``level``."""
    from world.magic.models import Thread  # noqa: PLC0415

    return Thread.objects.filter(
        owner=character.sheet_data,
        retired_at__isnull=True,
        level__gte=level,
    ).exists()


def _resolve_min_trait(character: ObjectDB, *, trait: str, value: int) -> bool:
    """True if the character's value in the named trait is >= ``value``.

    Trait lookup is case-insensitive (``Trait.get_by_name``).
    """
    from world.traits.models import CharacterTraitValue, Trait  # noqa: PLC0415

    trait_obj = Trait.get_by_name(trait)
    if trait_obj is None:
        return False
    ctv = CharacterTraitValue.objects.filter(
        character=character,
        trait=trait_obj,
    ).first()
    return ctv is not None and ctv.value >= value


def _resolve_has_skill(character: ObjectDB, *, skill: str) -> bool:
    """True if the character has a positive value in the named skill trait."""
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415

    trait_obj = Trait.get_by_name(skill)
    if trait_obj is None or trait_obj.trait_type != TraitType.SKILL:
        return False
    ctv = CharacterTraitValue.objects.filter(
        character=character,
        trait=trait_obj,
    ).first()
    return ctv is not None and ctv.value > 0


def _resolve_min_society_standing(character: ObjectDB, **_params: object) -> bool:
    """Stub-sealed resolver for society standing.

    world.societies reputation (SocietyReputation / OrganizationReputation)
    is keyed by ``scenes.Persona``, not by the character or CharacterSheet,
    and "standing" is ambiguous (society reputation vs. organization
    reputation vs. membership rank) with no defined character->persona
    selection rule. Resolving it correctly requires a design decision.
    """
    # DESIGN §4: verify world.societies standing model before wiring
    msg = "min_society_standing resolver pending societies-standing model verification"
    raise NotImplementedError(msg)


# Leaf-name -> resolver. The structural evaluator never reads this; only
# CharacterPredicateContext dispatches through it.
LEAF_RESOLVERS: LeafRegistry = {
    "has_distinction": _resolve_has_distinction,
    "has_achievement": _resolve_has_achievement,
    "has_condition": _resolve_has_condition,
    "has_capability": _resolve_has_capability,
    "has_thread": _resolve_has_thread,
    "min_thread_level": _resolve_min_thread_level,
    "min_trait": _resolve_min_trait,
    "has_skill": _resolve_has_skill,
    "min_society_standing": _resolve_min_society_standing,
}


class CharacterPredicateContext:
    """Concrete ``PredicateContext`` bound to one acting character.

    ``has_leaf`` dispatches the leaf name through ``LEAF_RESOLVERS`` and
    passes the leaf's authored params straight through. An unknown leaf name
    is a programmer/authoring error and raises ``KeyError`` rather than
    silently evaluating False.
    """

    def __init__(self, character: ObjectDB) -> None:
        self.character = character

    def has_leaf(self, leaf: str, **params: object) -> bool:
        resolver: LeafResolver = LEAF_RESOLVERS[leaf]
        return resolver(self.character, **params)
