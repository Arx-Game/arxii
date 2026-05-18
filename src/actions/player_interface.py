"""Unified player action availability — merges challenge, combat, and registry backends.

``get_player_actions`` is the single read path for the action picker UI.  It is
recomputed on every call (no caching) so that GM-spawned challenges and encounter
state changes appear immediately on the next request.

Backend resolution:
- CHALLENGE  -- delegates to ``world.mechanics.services.get_available_actions``; adapts
  each ``AvailableAction`` (which already carries resolved ``check_type_resolved`` and
  ``action_template_resolved`` instances populated by the prefetch chain) into a
  ``PlayerAction``.
- COMBAT      -- only when ``get_active_round_context`` returns a ``CombatRoundContext``;
  enumerates the character's known techniques that have an ``action_template``
  (= combat-ready techniques) and emits one ``PlayerAction`` per technique.
- REGISTRY    -- ``get_actions_for_target_type`` returns registry ``Action`` singletons;
  these have no ``ActionTemplate`` / ``check_type`` so ALL current registry actions are
  excluded.  (Noted in the module docstring for visibility.)

Registry exclusion note:
  Every registry ``Action`` in ``actions.registry`` is a pure Python singleton with no
  database model and no associated ``ActionTemplate``.  The ``PlayerAction`` descriptor
  requires a resolved ``CheckType`` instance (the unifying resolution anchor), which
  cannot be provided for registry actions until they are backed by ``ActionTemplate``
  rows.  They are excluded rather than emitted with a placeholder to avoid confusing the
  dispatch layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.constants import ActionBackend
from actions.round_context import get_active_round_context
from actions.types import ActionRef, PlayerAction
from world.combat.round_context import CombatRoundContext
from world.magic.models import CharacterTechnique
from world.mechanics.services import get_available_actions

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


def get_player_actions(character: ObjectDB) -> list[PlayerAction]:
    """Return all available ``PlayerAction`` descriptors for *character*.

    Merges the challenge, combat, and registry backends into a single homogeneous
    list.  Recomputed on every call — no caching.

    Args:
        character: The character's ``ObjectDB`` instance (the game object, not
            ``CharacterSheet``).  The character's ``db_location`` is used to look
            up active challenges.

    Returns:
        A list of ``PlayerAction`` instances sorted by backend then by their
        natural order within each backend.  Never ``None``; empty list if no
        actions are available.
    """
    actions: list[PlayerAction] = []

    actions.extend(_challenge_actions(character))
    actions.extend(_combat_actions(character))
    # Registry backend: all current actions excluded (no ActionTemplate / check_type)
    # — see module docstring.  When registry actions gain ActionTemplate backing,
    # uncomment and implement _registry_actions(character).

    return actions


# ---------------------------------------------------------------------------
# Private backend adapters
# ---------------------------------------------------------------------------


def _challenge_actions(character: ObjectDB) -> list[PlayerAction]:
    """Adapt ``AvailableAction`` list from the mechanics service into ``PlayerAction``s."""
    location = character.db_location  # ObjectDB.db_location (FK)
    if location is None:
        return []

    available = get_available_actions(character, location)
    result: list[PlayerAction] = []

    for avail in available:
        check_type = avail.check_type_resolved
        if check_type is None:
            # Defensive: should not happen because _match_approaches always populates
            # check_type_resolved, but skip gracefully if it ever does.
            continue

        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=avail.challenge_instance_id,
            approach_id=avail.approach_id,
        )
        result.append(
            PlayerAction(
                backend=ActionBackend.CHALLENGE,
                check_type=check_type,
                display_name=avail.display_name,
                ref=ref,
                action_template=avail.action_template_resolved,
                description=avail.custom_description,
                difficulty=avail.difficulty_indicator,
                prerequisite_met=avail.prerequisite_met,
                prerequisite_reasons=avail.prerequisite_reasons,
            )
        )

    return result


def _combat_actions(character: ObjectDB) -> list[PlayerAction]:
    """Return COMBAT ``PlayerAction``s when the character is in an active declaring round.

    Only produces actions when:
    1. The character has a ``CharacterSheet`` (required to resolve combat participation).
    2. ``get_active_round_context`` returns a ``CombatRoundContext`` (encounter in DECLARING
       or other active status).

    Enumerates the character's known techniques that are combat-ready (have an
    ``action_template`` FK set) and emits one ``PlayerAction`` per such technique.
    """
    # Resolve CharacterSheet from the character ObjectDB
    sheet = _get_character_sheet(character)
    if sheet is None:
        return []

    ctx = get_active_round_context(sheet)
    if ctx is None or not isinstance(ctx, CombatRoundContext):
        return []

    # Enumerate techniques the character knows that have an action_template.
    # select_related ensures no per-technique queries for action_template + check_type.
    grants = CharacterTechnique.objects.filter(
        character=sheet,
        technique__action_template__isnull=False,
    ).select_related(
        "technique",
        "technique__action_template",
        "technique__action_template__check_type",
    )

    result: list[PlayerAction] = []
    for grant in grants:
        technique = grant.technique
        template = technique.action_template  # guaranteed non-None by filter above
        if template is None:
            continue  # defensive; filter above excludes None

        check_type = template.check_type
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=technique.pk,
        )
        result.append(
            PlayerAction(
                backend=ActionBackend.COMBAT,
                check_type=check_type,
                display_name=technique.name,
                ref=ref,
                action_template=template,
            )
        )

    return result


def _get_character_sheet(character: ObjectDB) -> CharacterSheet | None:
    """Return the ``CharacterSheet`` for *character*, or ``None`` if unavailable.

    Uses the reverse OneToOne relation ``sheet_data`` that ``CharacterSheet``
    attaches to ``ObjectDB`` via ``CharacterSheet.character`` (related_name="sheet_data").
    """
    try:
        return character.sheet_data  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — DoesNotExist or AttributeError both mean no sheet
        return None
