"""Per-viewer persona display resolution (#1109, slice 2).

How a persona's name renders to a given viewer:

- **Your own faces** — any persona on a character_sheet your account currently plays — and
  **named public faces** render by their real name. You are never restricted from your own
  identities (the owning player always sees the truth).
- **Anonymous faces** (`is_fake_name`) you have **discovered** (via any of your characters)
  render as ``"<real> (as <mask>)"``.
- **Anonymous faces** you have not discovered render as a composed **sdesc**.

``build_persona_display_map`` resolves a whole page of personas in O(1) discovery queries, so
the interaction feed stays query-bounded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from world.scenes.models import Persona, PersonaDiscovery

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.accounts.models import AccountDB

# Apparent gender for the anonymous-face short description (#1109): from the character's real
# gender; non-binary / unset render as "person". (A slice-3 disguise that conceals gender will
# force "person" regardless — e.g. a feature-concealing robe.)
_GENDER_NOUN = {"male": "man", "female": "woman"}


def compose_sdesc(persona: Persona) -> str:
    """An anonymous face's short description: ``"a man/woman/person wearing a <mask name>"``.

    This is the *mask* case — the mask label is the player-authored persona name. Slice 3
    (disguises) will let other concealment types supply their own phrasing and conceal traits
    (e.g. ``"a person wearing a feature-concealing robe"``), continuing into the trait-driven
    auto-description; for now an anonymous persona is rendered as a worn mask.
    """
    sheet = persona.character_sheet
    gender_key = sheet.gender.key if sheet.gender_id is not None else None
    noun = _GENDER_NOUN.get(gender_key, "person")
    return f"a {noun} wearing a {persona.name}"


def build_persona_display_map(
    personas: Iterable[Persona],
    *,
    viewer_persona_ids: set[int],
    viewer_sheet_ids: set[int],
) -> dict[int, tuple[str, bool]]:
    """Map each persona's pk -> ``(display_name, is_discovered)`` for one viewer (#1109).

    One discovery query covers every anonymous, non-owned persona in ``personas``. Owned and
    named-public personas resolve to their real name with no query.
    """
    unique = {p.pk: p for p in personas}
    # Owned faces are never restricted — resolved as the real name without a discovery lookup.
    fake_ids = [p.pk for p in unique.values() if p.is_fake_name and p.pk not in viewer_persona_ids]

    revealed: dict[int, Persona] = {}
    if fake_ids and viewer_sheet_ids:
        rows = PersonaDiscovery.objects.filter(
            Q(persona_id__in=fake_ids) | Q(linked_to_id__in=fake_ids),
            discovered_by_id__in=viewer_sheet_ids,
        ).select_related("persona", "linked_to")
        for discovery in rows:
            # A discovery links two faces; map the masked one to the other (the revealed one).
            if discovery.persona_id in fake_ids:
                revealed[discovery.persona_id] = discovery.linked_to
            if discovery.linked_to_id in fake_ids:
                revealed[discovery.linked_to_id] = discovery.persona

    display: dict[int, tuple[str, bool]] = {}
    for persona in unique.values():
        if persona.pk in viewer_persona_ids or not persona.is_fake_name:
            display[persona.pk] = (persona.name, False)
        elif persona.pk in revealed:
            display[persona.pk] = (f"{revealed[persona.pk].name} (as {persona.name})", True)
        else:
            display[persona.pk] = (compose_sdesc(persona), False)
    return display


def resolve_display_for_viewer(
    persona: Persona,
    *,
    viewer_persona_ids: set[int],
    viewer_sheet_ids: set[int],
) -> tuple[str, bool]:
    """Resolve one persona's ``(display_name, is_discovered)`` for one viewer (#1109).

    The single-target form of ``build_persona_display_map`` — for the look / room-contents
    paths, which resolve one character at a time. Own faces and named-public faces render real;
    a discovered anonymous face reveals; otherwise the composed sdesc. One discovery query, and
    only for an anonymous, non-owned face.
    """
    if persona.pk in viewer_persona_ids or not persona.is_fake_name:
        return persona.name, False
    if viewer_sheet_ids:
        discovery = (
            PersonaDiscovery.objects.filter(
                Q(persona_id=persona.pk) | Q(linked_to_id=persona.pk),
                discovered_by_id__in=viewer_sheet_ids,
            )
            .select_related("persona", "linked_to")
            .first()
        )
        if discovery is not None:
            linked = (
                discovery.linked_to if discovery.persona_id == persona.pk else discovery.persona
            )
            return f"{linked.name} (as {persona.name})", True
    return compose_sdesc(persona), False


def viewer_context_for_account(account: AccountDB) -> tuple[set[int], set[int]]:
    """The viewer's ``(owned_persona_ids, owned_sheet_ids)`` for a look (no request) (#1109).

    Owned = personas on the character sheets the account *currently* plays. Both sets feed
    ``resolve_display_for_viewer`` — owned for self-ownership, sheets for the discovery lookup.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    sheet_ids = set(
        RosterEntry.objects.for_account(account).values_list("character_sheet_id", flat=True)
    )
    if not sheet_ids:
        return set(), set()
    persona_ids = set(
        Persona.objects.filter(character_sheet_id__in=sheet_ids).values_list("id", flat=True)
    )
    return persona_ids, sheet_ids
