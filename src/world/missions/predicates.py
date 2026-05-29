"""Shared predicate evaluator for the Missions engine (Phase 0 + Phase C).

A predicate is an AND/OR/NOT rule tree whose leaves test the *acting
character's own durable state* (never a target's sheet). The tree mirrors the
shape of ``world.distinctions.models.DistinctionPrerequisite.rule_json`` — a
JSONField AND/OR/NOT structure.

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

Phase C (2026-05-24) extended the resolver signature to take
``ResolverContext`` instead of a bare ``ObjectDB``. The context carries
``character`` (always present) plus ``presented_persona`` (the persona the
character is currently presenting as, or None). Persona-aware resolvers
(``min_society_standing``, ``min_org_reputation``, ``is_member_of_org``)
consult ``presented_persona``; non-persona resolvers ignore it. The caller
of ``CharacterPredicateContext`` provides the presented persona — for the
front-door availability surface that means ``offer_missions`` accepts and
forwards it.

Leaf resolvers assume the acting character has a CharacterSheet (true for
every played character per character_sheets/CLAUDE.md); a sheet-less
character is a programmer error and the sheet-keyed resolvers will raise
CharacterSheet.DoesNotExist loudly rather than silently gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from evennia.objects.models import ObjectDB

from world.missions.types import LeafRegistry, LeafResolver, PredicateContext, ResolverContext

if TYPE_CHECKING:
    from world.scenes.models import Persona


# Semantic type aliases for predicate-leaf params. The catalog endpoint
# reads the Annotated metadata to give the frontend builder enough info
# to render a domain-aware widget (e.g. a giver picker) instead of a
# bare number input. Keep these wrapping plain primitives so the resolver
# bodies stay typed in terms of the runtime type.
GiverId = Annotated[int, "giver_id"]

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
# Leaf resolvers — each tests one slice of the acting character's own state.
# Signature: ``(ctx: ResolverContext, **params: object) -> bool``. ``ctx``
# carries ``sheet`` (the CharacterSheet — canonical handle per project
# convention) and ``presented_persona`` (the mask, or None). Most
# resolvers read ``ctx.sheet`` directly. The few resolvers gating on
# models still keyed by ObjectDB (CharacterDistinction.character,
# ConditionInstance via has_condition service, CharacterTraitValue.
# character, MissionGiverStanding.character) walk ``ctx.character`` — the
# @property on ResolverContext that returns ``sheet.character``.
# Persona-aware resolvers consult ``ctx.presented_persona``.
#
# Resolvers must never inspect a target's sheet — only the acting
# character's durable state. Params are the leaf's authored params and
# are keyword-only.
#
# Invariant: the acting character is assumed to have a CharacterSheet
# (true for every played character per character_sheets/CLAUDE.md).
# CharacterPredicateContext walks ``character.sheet_data`` at dispatch
# time; a sheet-less character is a programmer error and the lookup
# raises CharacterSheet.DoesNotExist loudly rather than silently gate.
# ---------------------------------------------------------------------------


def _resolve_has_distinction(ctx: ResolverContext, *, slug: str) -> bool:
    """True if the character has the Distinction with this slug."""
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    return CharacterDistinction.objects.filter(
        character=ctx.character,
        distinction__slug=slug,
    ).exists()


def _resolve_has_achievement(ctx: ResolverContext, *, slug: str) -> bool:
    """True if the character has earned the Achievement with this slug.

    CharacterAchievement is keyed by CharacterSheet; ``sheet_data`` is the
    OneToOne reverse accessor (shared pk with the character).
    """
    from world.achievements.models import CharacterAchievement  # noqa: PLC0415

    return CharacterAchievement.objects.filter(
        character_sheet=ctx.sheet,
        achievement__slug=slug,
    ).exists()


def _resolve_has_condition(ctx: ResolverContext, *, key: str) -> bool:
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
    return has_condition(ctx.character, template)


def _resolve_has_capability(ctx: ResolverContext, *, name: str) -> bool:
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
    return get_capability_value(ctx.character, capability) > 0


def _resolve_has_thread(ctx: ResolverContext) -> bool:
    """True if the character owns at least one non-retired Thread."""
    from world.magic.models import Thread  # noqa: PLC0415

    return Thread.objects.filter(
        owner=ctx.sheet,
        retired_at__isnull=True,
    ).exists()


def _resolve_min_thread_level(ctx: ResolverContext, *, level: int) -> bool:
    """True if any non-retired Thread the character owns is at >= ``level``."""
    from world.magic.models import Thread  # noqa: PLC0415

    return Thread.objects.filter(
        owner=ctx.sheet,
        retired_at__isnull=True,
        level__gte=level,
    ).exists()


def _resolve_min_trait(ctx: ResolverContext, *, trait: str, value: int) -> bool:
    """True if the character's value in the named trait is >= ``value``.

    Trait lookup is case-insensitive (``Trait.get_by_name``).
    """
    from world.traits.models import CharacterTraitValue, Trait  # noqa: PLC0415

    trait_obj = Trait.get_by_name(trait)
    if trait_obj is None:
        return False
    ctv = CharacterTraitValue.objects.filter(
        character=ctx.character,
        trait=trait_obj,
    ).first()
    return ctv is not None and ctv.value >= value


def _resolve_has_skill(ctx: ResolverContext, *, skill: str) -> bool:
    """True if the character has a positive value in the named skill trait."""
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415

    trait_obj = Trait.get_by_name(skill)
    if trait_obj is None or trait_obj.trait_type != TraitType.SKILL:
        return False
    ctv = CharacterTraitValue.objects.filter(
        character=ctx.character,
        trait=trait_obj,
    ).first()
    return ctv is not None and ctv.value > 0


def _resolve_min_giver_standing(ctx: ResolverContext, *, giver_id: int, min_affection: int) -> bool:
    """True if the character's standing with the giver (by PK) is >= ``min_affection``.

    ``giver_id`` is the ``MissionGiver`` primary key. Standing is the
    giver's affection toward the character. No standing row means
    affection is implicitly 0. An unknown giver id fails closed
    (returns False). PK-keyed so giver renames don't silently break
    authored predicate rules.
    """
    from world.missions.models import MissionGiverStanding  # noqa: PLC0415

    standing = (
        MissionGiverStanding.objects.filter(giver_id=giver_id, character=ctx.character)
        .values_list("affection", flat=True)
        .first()
    )
    if standing is None:
        if not _giver_exists(giver_id):
            return False
        return min_affection <= 0
    return standing >= min_affection


def _giver_exists(giver_id: int) -> bool:
    """Internal helper: True if a MissionGiver with this PK exists."""
    from world.missions.models import MissionGiver  # noqa: PLC0415

    return MissionGiver.objects.filter(pk=giver_id).exists()


def _resolve_has_resonance(ctx: ResolverContext, *, name: str) -> bool:
    """True if the character has a CharacterResonance row for the named resonance.

    Per magic CLAUDE.md Resonance Pivot Spec A §2.2, row existence IS
    "this character is associated with this resonance".
    """
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    return CharacterResonance.objects.filter(
        character_sheet=ctx.sheet,
        resonance__name=name,
    ).exists()


def _resolve_has_codex_entry(ctx: ResolverContext, *, subject: str, name: str) -> bool:
    """True if the character has fully learned (KNOWN) the named codex entry.

    Identified by ``(subject, name)`` — neither alone is unique. UNCOVERED
    status does NOT satisfy the gate. Knowledge is keyed by ``RosterEntry``.
    """
    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        roster_entry = ctx.sheet.roster_entry
    except RosterEntry.DoesNotExist:
        return False
    return CharacterCodexKnowledge.objects.filter(
        roster_entry=roster_entry,
        entry__subject__name=subject,
        entry__name=name,
        status=CodexKnowledgeStatus.KNOWN,
    ).exists()


def _resolve_min_character_level(ctx: ResolverContext, *, level: int) -> bool:
    """True if the character's current level is >= ``level``."""
    return int(ctx.sheet.current_level) >= level


# Ordered low → high — see world.societies.types.ReputationTier. Index in
# this tuple IS the rank for ``>=`` comparison in min_org_reputation /
# min_society_standing. Synced manually with societies.types; if a new tier
# lands, this tuple must be updated.
_TIER_ORDER: tuple[str, ...] = (
    "reviled",
    "despised",
    "disliked",
    "disfavored",
    "unknown",
    "favored",
    "liked",
    "honored",
    "revered",
)


def _tier_rank(tier_value: str) -> int:
    """Return the rank index for a tier-string ``tier_value``.

    Raises ``KeyError`` for unknown tier values — authoring error (mission
    template references a nonexistent tier). Predicates fail closed on data,
    but bad authoring surfaces loudly.
    """
    try:
        return _TIER_ORDER.index(tier_value)
    except ValueError as exc:
        msg = f"unknown reputation tier {tier_value!r}; expected one of {_TIER_ORDER}"
        raise KeyError(msg) from exc


def _resolve_min_org_reputation(ctx: ResolverContext, *, org: str, tier: str) -> bool:
    """True if the presented persona's reputation tier with the org is >= ``tier``.

    Persona-aware: reads ``ctx.presented_persona``. Tiers are ordered
    REVILED < DESPISED < DISLIKED < DISFAVORED < UNKNOWN < FAVORED <
    LIKED < HONORED < REVERED. When no OrganizationReputation row exists
    for (presented_persona, org), the gate fails closed (we can't claim
    standing without a row). When ``presented_persona`` is None, also fails.
    """
    if ctx.presented_persona is None:
        return False
    from world.societies.models import OrganizationReputation  # noqa: PLC0415
    from world.societies.types import ReputationTier  # noqa: PLC0415

    threshold_rank = _tier_rank(tier)
    row = OrganizationReputation.objects.filter(
        persona=ctx.presented_persona,
        organization__name=org,
    ).first()
    if row is None:
        return False
    current_tier = ReputationTier.from_value(row.value).value
    return _tier_rank(current_tier) >= threshold_rank


def _resolve_is_member_of_org(ctx: ResolverContext, *, org: str) -> bool:
    """True if the character's currently-presented persona belongs to the org.

    Persona-aware: reads ``ctx.presented_persona`` (the persona the
    character is wearing right now — a mask). Per societies CLAUDE.md, only
    PRIMARY/ESTABLISHED personas can hold memberships, so TEMPORARY masks
    naturally fail (no membership row can exist). When ``presented_persona``
    is None (caller didn't specify), the gate fails closed — predicates
    are advisory gates, and a missing persona signal is ambiguous.
    """
    if ctx.presented_persona is None:
        return False
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        persona=ctx.presented_persona,
        organization__name=org,
    ).exists()


def _resolve_min_society_standing(ctx: ResolverContext, *, society: str, tier: str) -> bool:
    """True if the presented persona's reputation tier with the society is >= ``tier``.

    Persona-aware sibling of ``min_org_reputation`` against Society (not
    Organization). Tier ordering and fail-closed semantics are identical:
    no presented persona → False; no SocietyReputation row → False; unknown
    tier string → KeyError (authoring error).

    Per the user's call: a character traveling under a mask uses THAT
    persona's reputation (or lack thereof). TEMPORARY masks never have
    reputation rows by model constraint, so they fail closed naturally —
    masked characters must un-mask to satisfy this gate.
    """
    if ctx.presented_persona is None:
        return False
    from world.societies.models import SocietyReputation  # noqa: PLC0415
    from world.societies.types import ReputationTier  # noqa: PLC0415

    threshold_rank = _tier_rank(tier)
    row = SocietyReputation.objects.filter(
        persona=ctx.presented_persona,
        society__name=society,
    ).first()
    if row is None:
        return False
    current_tier = ReputationTier.from_value(row.value).value
    return _tier_rank(current_tier) >= threshold_rank


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
    "min_character_level": _resolve_min_character_level,
    "has_codex_entry": _resolve_has_codex_entry,
    "has_resonance": _resolve_has_resonance,
    "min_giver_standing": _resolve_min_giver_standing,
    "is_member_of_org": _resolve_is_member_of_org,
    "min_org_reputation": _resolve_min_org_reputation,
    "min_society_standing": _resolve_min_society_standing,
}


class CharacterPredicateContext:
    """Concrete ``PredicateContext`` bound to one acting character.

    ``has_leaf`` dispatches the leaf name through ``LEAF_RESOLVERS`` and
    passes the leaf's authored params straight through. An unknown leaf
    name is a programmer/authoring error and raises ``KeyError`` rather
    than silently evaluating False.

    ``presented_persona`` is the persona the character is currently
    presenting as (a mask, including TEMPORARY masks) at offer time. None
    means "no mask information available" — persona-aware resolvers gate
    accordingly (typically: fail closed for persona-keyed checks that
    require a specific persona). The offering surface
    (``services.availability.offer_missions``) forwards this from its
    caller.
    """

    def __init__(
        self,
        character: ObjectDB,
        presented_persona: Persona | None = None,
    ) -> None:
        self.character = character
        self.presented_persona = presented_persona

    def has_leaf(self, leaf: str, **params: object) -> bool:
        resolver: LeafResolver = LEAF_RESOLVERS[leaf]
        # ResolverContext carries the CharacterSheet (canonical handle per
        # project convention); the optional ``character`` ObjectDB walk is
        # available via the dataclass's @property for the few legacy-keyed
        # models that still FK ObjectDB.
        ctx = ResolverContext(
            sheet=self.character.sheet_data,
            presented_persona=self.presented_persona,
        )
        return resolver(ctx, **params)
