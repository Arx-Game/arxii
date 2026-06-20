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

from world.scenes.models import PersonaDiscovery

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.scenes.models import Persona

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
