"""Player-facing reasons for matched predicate leaves.

``matched_leaves`` says which leaves let a character through a rule; this turns
one of them into a short second-person line ("you are Cinderi") so a character's
special traits are never silently used. The text is composed from the authored
row's own display name: it displays an existing row, it designates no behavior.
"""

from __future__ import annotations

from collections.abc import Callable

from world.predicates.predicates import KEY_LEAF, KEY_PARAMS

_YOU_HAVE = "you have {}"
_YOU_ARE = "you are {}"
_UPBRINGING = "your upbringing: {}"
_BELONG = "you belong to {}"
_STANDING = "your standing in {}"


def _species(params: dict) -> str | None:
    from world.species.models import Species  # noqa: PLC0415

    row = Species.objects.filter(pk=params.get("species_id")).first()
    return _YOU_ARE.format(row.name) if row else None


def _upbringing(params: dict) -> str | None:
    from world.character_creation.models import OriginTemplate  # noqa: PLC0415

    row = OriginTemplate.objects.filter(pk=params.get("origin_template_id")).first()
    return _UPBRINGING.format(row.name) if row else None


def _distinction(params: dict) -> str | None:
    from world.distinctions.models import Distinction  # noqa: PLC0415

    row = Distinction.objects.filter(slug=params.get("slug")).first()
    return _YOU_HAVE.format(row.name) if row else None


def _achievement(params: dict) -> str | None:
    from world.achievements.models import Achievement  # noqa: PLC0415

    row = Achievement.objects.filter(slug=params.get("slug")).first()
    return _YOU_HAVE.format(row.name) if row else None


def _item(params: dict) -> str | None:
    from world.items.models import ItemTemplate  # noqa: PLC0415

    row = ItemTemplate.objects.filter(pk=params.get("template_id")).first()
    return _YOU_HAVE.format(row.name) if row else None


def _named(template: str, key: str) -> Callable[[dict], str | None]:
    """A leaf whose param already holds the row's display name."""

    def describe(params: dict) -> str | None:
        value = params.get(key)
        return template.format(value) if value else None

    return describe


_DESCRIBERS: dict[str, Callable[[dict], str | None]] = {
    "has_species": _species,
    "has_upbringing": _upbringing,
    "has_distinction": _distinction,
    "has_achievement": _achievement,
    "has_item": _item,
    "is_member_of_org": _named(_BELONG, "org"),
    "min_org_rank": _named(_BELONG, "org"),
    "is_member_of_society": _named(_STANDING, "society"),
    "min_society_standing": _named(_STANDING, "society"),
    "has_codex_entry": _named(_YOU_HAVE, "name"),
    "has_skill": _named(_YOU_HAVE, "skill"),
    "min_trait": _named(_YOU_HAVE, "trait"),
    "has_resonance": _named(_YOU_HAVE, "name"),
    "has_capability": _named(_YOU_HAVE, "name"),
}


def describe_leaf(leaf: dict) -> str | None:
    """A short second-person reason for a matched leaf, or None if it has none."""
    describer = _DESCRIBERS.get(leaf[KEY_LEAF])
    if describer is None:
        return None
    return describer(leaf.get(KEY_PARAMS, {}))


# --- Staff-facing reasons (#4361) -------------------------------------------------------
# The Faction Rules page's "test a character" picker says WHY a rule matched, including
# the hidden reputation tier and the association behind a match. Players never see these:
# a player sees only their angle, and the revealed text after a successful read.

_REGARD_HIGH = "high regard"
_REGARD_LOW = "low regard"
_REGARD_NONE = "no particular regard"


def _regard_words(tier: str) -> str:
    from world.predicates.predicates import _TIER_ORDER  # noqa: PLC0415

    middle = _TIER_ORDER.index("unknown")
    rank = _TIER_ORDER.index(tier)
    if rank > middle:
        return _REGARD_HIGH
    if rank < middle:
        return _REGARD_LOW
    return _REGARD_NONE


def _reputation_reason(persona: object, model: type, field: str, name: str) -> str | None:
    from world.societies.types import ReputationTier  # noqa: PLC0415

    if persona is None:
        return None
    row = model.objects.filter(persona=persona, **{f"{field}__name": name}).first()
    if row is None:
        return None
    tier = ReputationTier.from_value(row.value)
    reason = f"reputation: {name} holds you in {_regard_words(tier.value)} ({tier.value.title()})"
    return "\n".join([reason, *_recent_causes(row)])


def _recent_causes(row: object) -> list[str]:
    """Up to three recent recorded causes of an organization reputation, newest first (#4448).

    Staff only: names the cause and what it cites, which a player never sees. Each is its own
    line: "Moved by: ..." for the newest, "Earlier: ..." for each before it. A society's
    reputation has no change record, so it adds nothing.
    """
    from world.societies.constants import REASON_LINES_SHOWN  # noqa: PLC0415
    from world.societies.models import OrganizationReputation  # noqa: PLC0415

    if not isinstance(row, OrganizationReputation):
        return []
    events = list(row.events.all()[:REASON_LINES_SHOWN])
    lines = []
    for index, event in enumerate(events):
        if event.source_event_id:
            move = event.ripple_move()
        else:
            cited = event.cited(summary=True)
            detail = f" ({', '.join(cited)})" if cited else ""
            move = (
                f"{event.get_cause_display().lower()}{detail}, "
                f"{event.tier_before.title()} to {event.tier_after.title()}"
            )
        lines.append(f"{'Moved by' if index == 0 else 'Earlier'}: {move}")
        if event.source_event_id:
            lines.append(event.ripple_source())
    return lines


def _org_reputation(params: dict, persona: object) -> str | None:
    from world.societies.models import OrganizationReputation  # noqa: PLC0415

    return _reputation_reason(
        persona, OrganizationReputation, "organization", params.get("org", "")
    )


def _society_reputation(params: dict, persona: object) -> str | None:
    from world.societies.models import SocietyReputation  # noqa: PLC0415

    return _reputation_reason(persona, SocietyReputation, "society", params.get("society", ""))


def _org_association(params: dict, persona: object) -> str | None:
    from world.societies.association import association_with_org  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    org = Organization.objects.filter(name=params.get("org")).first()
    found = association_with_org(persona, org) if org else None
    return f"association: {found.detail}" if found else None


def _society_association(params: dict, persona: object) -> str | None:
    from world.societies.association import association_with_society  # noqa: PLC0415
    from world.societies.models import Society  # noqa: PLC0415

    society = Society.objects.filter(name=params.get("society")).first()
    found = association_with_society(persona, society) if society else None
    return f"association: {found.detail}" if found else None


_STAFF_EXPLAINERS: dict[str, Callable[[dict, object], str | None]] = {
    "min_org_reputation": _org_reputation,
    "max_org_reputation": _org_reputation,
    "min_society_standing": _society_reputation,
    "max_society_standing": _society_reputation,
    "associated_with_org": _org_association,
    "associated_with_society": _society_association,
}


def explain_leaf_for_staff(leaf: dict, presented_persona: object) -> str:
    """Why a matched leaf matched, for staff: names the hidden tier or association."""
    name = leaf[KEY_LEAF]
    params = leaf.get(KEY_PARAMS, {})
    explainer = _STAFF_EXPLAINERS.get(name)
    reason = explainer(params, presented_persona) if explainer else None
    if reason is None:
        reason = describe_leaf(leaf)
    if reason is None:
        values = ", ".join(str(value) for value in params.values())
        reason = f"{name}: {values}" if values else name
    return reason
