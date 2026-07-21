"""Ghost-tutor summoning service (#2460).

SERVICE-dispatch target for the 'Summon Ghostly Tutor' Ritual. Validates
membership and idempotency, creates a GhostTutelage record that makes the
tradition's signature techniques available through the existing TRAIN offer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Ritual, Tradition


def summon_ghost_tutor(
    *,
    character_sheet: CharacterSheet,
    ritual: Ritual,  # noqa: ARG001
    tradition: Tradition,
    **kwargs: Any,  # noqa: ARG001
) -> dict[str, Any]:
    """Summon a ghostly tutor for an orphaned tradition.

    Validates the performer has an active CharacterTradition membership for
    the target tradition (members-only), creates a GhostTutelage record.
    Raises on re-summon so the transaction rolls back (components refunded).

    Args:
        character_sheet: The CharacterSheet of the ritual performer.
        ritual: The Ritual being performed (forwarded by _dispatch_service).
        tradition: The Tradition whose tutor to summon.

    Returns:
        A dict with ``created=True`` and the tutelage pk.

    Raises:
        NotTraditionMemberError: Performer is not an active member of the tradition.
        GhostTutelageAlreadyExistsError: A tutelage already exists (re-summon).
    """
    from world.magic.exceptions import (  # noqa: PLC0415
        GhostTutelageAlreadyExistsError,
        NotTraditionMemberError,
    )
    from world.magic.models import GhostTutelage  # noqa: PLC0415

    # Members-only: must have an active CharacterTradition for this tradition.
    is_member = character_sheet.character_traditions.filter(
        tradition=tradition, left_at__isnull=True
    ).exists()
    if not is_member:
        raise NotTraditionMemberError

    # Idempotent re-summon: raise so the transaction rolls back (components refunded).
    existing = GhostTutelage.objects.filter(
        character_sheet=character_sheet, tradition=tradition
    ).first()
    if existing is not None:
        raise GhostTutelageAlreadyExistsError

    tutelage = GhostTutelage.objects.create(
        character_sheet=character_sheet,
        tradition=tradition,
    )
    return {"created": True, "ghost_tutelage_pk": tutelage.pk}
