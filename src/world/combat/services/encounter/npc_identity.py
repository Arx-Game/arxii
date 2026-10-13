"""Identifying combat NPC typeclasses and persistent identity."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.combat.models import CombatOpponent

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Identity guard helpers
# ---------------------------------------------------------------------------


def is_combat_npc_typeclass(objectdb: ObjectDB) -> bool:
    """Return True iff the ObjectDB's typeclass is the CombatNPC class."""
    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415

    return isinstance(objectdb, CombatNPC)


def has_persistent_identity_references(objectdb: ObjectDB) -> bool:
    """Return True if this ObjectDB is referenced by any model that signals
    persistent identity (Persona, RosterEntry, CharacterSheet, etc.).

    Single source of truth for "is this an ObjectDB any persistent system
    cares about?" — when a new persistent-identity model is added, this
    function adds the corresponding check.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    if CharacterSheet.objects.filter(character=objectdb).exists():
        return True
    if Persona.objects.filter(character_sheet_id=objectdb.pk).exists():
        return True
    if RosterEntry.objects.filter(character_sheet_id=objectdb.pk).exists():
        return True
    return False


def delete_ephemeral_npc(opponent: CombatOpponent) -> bool:
    """Guarded delete of one ephemeral combat NPC's ``ObjectDB``.

    Layer 5 of the multi-layer guard: a defensive re-check right before the
    delete, in case a corrupt row escaped Layers 1-4.

    ``ObjectDB`` isn't an ``ArxSharedMemoryModel``, so its ``delete()`` nulls
    referrers' FKs via a bulk ``SET_NULL`` UPDATE outside
    ``core.deletion.IdentityMapCollector`` — the cached ``opponent`` would
    otherwise keep reporting the deleted ``objectdb`` forever. Setting the
    field and saving on THIS held instance is enough: idmapper's identity map
    means there is only one cached ``CombatOpponent`` per pk in the process,
    so no further cache flush is needed afterward (fix round 3 — a bare
    ``flush_instance_cache()`` call here previously evicted the ENTIRE class
    cache, including every other live encounter's cached opponents, once per
    mob in the cleanup loop). Mirrors ``release_companion``'s identical
    objectdb-nulling fix (``world/companions/services.py`` — that one keeps
    its own narrower flush; unrelated to this fix).

    Shared by this module's own ``cleanup_completed_encounter`` ephemeral
    sweep and ``world.combat.won_over.delete_won_over_npc`` (#4091 fix round
    2) — one guard, one identity-map fix, not two copies of either.
    """
    objectdb = opponent.objectdb
    if objectdb is None or not opponent.objectdb_is_ephemeral:
        return False
    if not is_combat_npc_typeclass(objectdb):
        logger.error("Refusing to delete: %s is not a CombatNPC typeclass", objectdb)
        return False
    if has_persistent_identity_references(objectdb):
        logger.error("Refusing to delete: %s has persistent identity references", objectdb)
        return False
    objectdb.delete()
    opponent.objectdb = None
    opponent.save(update_fields=["objectdb"])
    return True
