"""Per-viewer persona display resolution (#1109, slice 2).

How a persona's name renders to a given viewer:

- **Your own faces** — any persona on a character_sheet your account currently plays — and
  **named public faces** render by their real name. You are never restricted from your own
  identities (the owning player always sees the truth).
- **Anonymous faces** (`is_fake_name`) you have **discovered** (via any of your characters)
  render as ``"<mask> (<real>)"`` — the presented face, with the real identity you've pierced
  in parens. The parens are load-bearing: presenting under a mask is easy to lose track of, and
  a GM running a scene needs to know who they're actually looking at.
- **Anonymous faces** you have not discovered render as a composed **sdesc**, unless one of
  your characters **sees through** that kind of disguise (#4396): a positive ``disguise_sight``
  lever total on the kind (``world.forms.services.identification.pierced_disguise_kinds``)
  reveals the face as ``"<mask> (<real>)"`` with no discovery row and no identification check.

``build_persona_display_map`` resolves a whole page of personas in O(1) discovery queries, so
the interaction feed stays query-bounded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from world.scenes.constants import PersonaType
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

    A full-concealment disguise overlay (#1272) forces ``"person"`` regardless of the
    character's real gender — a feature-concealing robe hides gender.
    """
    from world.forms.models import ConcealmentLevel  # noqa: PLC0415

    sheet = persona.character_sheet
    character = sheet.character
    noun = "person"

    # Full concealment forces "person" regardless of gender (#1272).
    form_state = character.form_state_or_none
    is_full_concealment = (
        form_state is not None
        and form_state.active_fake_overlay_id is not None
        and form_state.active_fake_overlay.concealment_level == ConcealmentLevel.FULL
    )
    if not is_full_concealment:
        gender_key = sheet.gender.key if sheet.gender_id is not None else None
        noun = _GENDER_NOUN.get(gender_key, "person")
    return f"a {noun} wearing a {persona.name}"


def _build_revealed_map(
    fake_ids: list[int],
    viewer_sheet_ids: set[int],
) -> dict[int, Persona]:
    """Query PersonaDiscovery rows and return a mapping of fake persona pk → revealed persona."""
    if not fake_ids or not viewer_sheet_ids:
        return {}
    rows = PersonaDiscovery.objects.filter(
        Q(persona_id__in=fake_ids) | Q(linked_to_id__in=fake_ids),
        discovered_by_id__in=viewer_sheet_ids,
    ).select_related("persona", "linked_to")
    revealed: dict[int, Persona] = {}
    for discovery in rows:
        if discovery.persona_id in fake_ids:
            revealed[discovery.persona_id] = discovery.linked_to
        if discovery.linked_to_id in fake_ids:
            revealed[discovery.linked_to_id] = discovery.persona
    return revealed


def _staff_reveal(persona: Persona) -> tuple[str, bool]:
    """Staff always see the real identity behind a mask (#1279).

    Staff are treated as universal discoverers: a fake-name persona renders as
    ``"<mask> (<real>)"`` where ``<real>`` is the character sheet's primary persona
    — the same reveal format a player gets after discovery, without needing a
    PersonaDiscovery row.
    """
    primary = persona.character_sheet.primary_persona
    if primary is not None and primary.pk != persona.pk:
        return f"{persona.name} ({primary.name})", True
    return persona.name, False


def _sight_reveal(persona: Persona, pierced_kinds: set[str]) -> tuple[str, bool] | None:
    """``"<mask> (<real>)"`` when the viewer sees through this face's kind of disguise (#4396).

    None when nothing is pierced or the face hides nothing a sight could pierce. The real
    name is the sheet's primary, the same reveal a staff viewer gets.
    """
    if not pierced_kinds:
        return None
    from world.forms.services.identification import presented_disguise_kind  # noqa: PLC0415

    kind = presented_disguise_kind(persona)
    if kind is None or kind not in pierced_kinds:
        return None
    return _staff_reveal(persona)


def _resolve_single_display(
    persona: Persona,
    viewer_persona_ids: set[int],
    revealed: dict[int, Persona],
    *,
    is_staff: bool = False,
    pierced_kinds: set[str] | None = None,
) -> tuple[str, bool, bool]:
    """Return ``(display_name, is_discovered, reveal_allowed)`` for one persona.

    ``reveal_allowed`` is the identity-reveal predicate (#2378): True whenever the viewer may
    know who is really behind this persona — their own face, a barefaced (non-anonymous)
    persona, staff, or a discovered mask — and False only for the composed-sdesc fallback
    (an undiscovered mask to a non-staff, non-owning viewer). Consumers that need to gate a
    *different* piece of identity-linked data (e.g. the shared character-sheet id behind an
    endorsement target) key off this flag rather than ``is_discovered``, since a barefaced
    persona is revealed (``reveal_allowed=True``) without ever going through discovery
    (``is_discovered=False``).
    """
    if persona.pk in viewer_persona_ids or not persona.is_fake_name:
        return persona.name, False, True
    if is_staff:
        name, is_discovered = _staff_reveal(persona)
        return name, is_discovered, True
    if persona.pk in revealed:
        return f"{persona.name} ({revealed[persona.pk].name})", True, True
    seen = _sight_reveal(persona, pierced_kinds or set())
    if seen is not None:
        name, is_discovered = seen
        return name, is_discovered, True
    return compose_sdesc(persona), False, False


def build_persona_display_map(
    personas: Iterable[Persona],
    *,
    viewer_persona_ids: set[int],
    viewer_sheet_ids: set[int],
    is_staff: bool = False,
) -> dict[int, tuple[str, bool, bool]]:
    """Map each persona's pk -> ``(display_name, is_discovered, reveal_allowed)`` (#1109, #2378).

    One discovery query covers every anonymous, non-owned persona in ``personas``. Owned and
    named-public personas resolve to their real name with no query. When ``is_staff`` is True,
    the discovery query is skipped entirely — staff are universal discoverers (#1279).
    ``reveal_allowed`` (see ``_resolve_single_display``) is the shared per-viewer identity-reveal
    predicate — reuse it instead of re-deriving reveal logic for any other identity-linked field.
    """
    unique = {p.pk: p for p in personas}
    # Owned faces are never restricted — resolved as the real name without a discovery lookup.
    fake_ids = [p.pk for p in unique.values() if p.is_fake_name and p.pk not in viewer_persona_ids]
    # Staff don't need discovery rows — they see through every mask (#1279).
    revealed = {} if is_staff else _build_revealed_map(fake_ids, viewer_sheet_ids)
    # Sight (#4396) is read once per page, and only when an undiscovered mask is left on it.
    pierced: set[str] = set()
    if not is_staff and any(pk not in revealed for pk in fake_ids):
        pierced = _pierced_kinds(viewer_sheet_ids)
    return {
        persona.pk: _resolve_single_display(
            persona, viewer_persona_ids, revealed, is_staff=is_staff, pierced_kinds=pierced
        )
        for persona in unique.values()
    }


def _pierced_kinds(viewer_sheet_ids: set[int]) -> set[str]:
    from world.forms.services.identification import pierced_disguise_kinds  # noqa: PLC0415

    return pierced_disguise_kinds(viewer_sheet_ids)


def resolve_display_for_viewer(
    persona: Persona,
    *,
    viewer_persona_ids: set[int],
    viewer_sheet_ids: set[int],
    is_staff: bool = False,
) -> tuple[str, bool]:
    """Resolve one persona's ``(display_name, is_discovered)`` for one viewer (#1109).

    The single-target form of ``build_persona_display_map`` — for the look / room-contents
    paths, which resolve one character at a time. Own faces and named-public faces render real;
    a discovered anonymous face reveals; otherwise the composed sdesc. One discovery query, and
    only for an anonymous, non-owned face. When ``is_staff`` is True, the discovery query is
    skipped — staff are universal discoverers (#1279).
    """
    if persona.pk in viewer_persona_ids or not persona.is_fake_name:
        return persona.name, False
    if is_staff:
        return _staff_reveal(persona)
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
            return f"{persona.name} ({linked.name})", True
        seen = _sight_reveal(persona, _pierced_kinds(viewer_sheet_ids))
        if seen is not None:
            return seen
    return compose_sdesc(persona), False


def identity_revealed_to_viewer(
    persona: Persona,
    *,
    viewer_persona_ids: set[int],
    viewer_sheet_ids: set[int],
    is_staff: bool = False,
) -> bool:
    """Whether this viewer may see the real character behind ``persona`` (#1325, #4030).

    The one rule for identity-linked prose (the free-text description on the sheet and in
    ``look``): the viewer's own face, staff, the PRIMARY public face, a discovered mask and a
    mask of a kind the viewer sees through (#4396) reveal; a named alt (its link to the
    primary stays hidden) and an undiscovered mask do not. One discovery query, only for an
    anonymous face the viewer doesn't own.
    """
    if persona.pk in viewer_persona_ids or is_staff:
        return True
    if not persona.is_fake_name:
        return persona.persona_type == PersonaType.PRIMARY
    _name, is_discovered = resolve_display_for_viewer(
        persona,
        viewer_persona_ids=viewer_persona_ids,
        viewer_sheet_ids=viewer_sheet_ids,
    )
    return is_discovered


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
