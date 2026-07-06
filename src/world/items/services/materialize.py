"""Materialize a row-only ItemInstance as a physical Evennia object (#1909).

Row-only ItemInstances (``game_object`` null) are an established pattern for
narrative grants and permits (``narrative_grants.py``) — those items live in
menus and detail panes, not rooms. Physical money is different: a minted coin
cache must be droppable, givable, stowable, and stealable, all of which route
through ``ItemState.is_in_possession`` / ``is_reachable_by`` and therefore
require a real ``ObjectDB`` with a location. The mint services call this
right after creating the instance so coin is born physical in the minter's
inventory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia.utils.create import create_object

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance

# Plain object typeclass — the same one item ObjectDBs use throughout the
# test factories (``evennia_extensions.factories.ObjectDBFactory`` default);
# items have no bespoke typeclass in this codebase.
ITEM_TYPECLASS_PATH = "typeclasses.objects.Object"


def materialize_item_game_object(
    instance: ItemInstance,
    holder_sheet: CharacterSheet,
) -> ObjectDB | None:
    """Create + link the physical ``ObjectDB`` for ``instance`` in the holder's inventory.

    Mirrors the ``ObjectDBFactory`` creation pattern (``create_object`` with
    an explicit typeclass and ``nohome=True``) as a production service. The
    object is placed on the holder's character (location = the character
    ObjectDB) and the character's ``carried_items`` cache is invalidated so
    the next inventory read sees the new item.

    Returns ``None`` (leaving the instance row-only, the narrative-grant
    behavior) when the sheet has no character object to place the item on —
    a defensive guard; ``CharacterSheet.character`` is the PK so a live sheet
    always has one.
    """
    character = getattr(holder_sheet, "character", None)  # noqa: GETATTR_LITERAL
    if character is None:
        return None
    game_object = create_object(
        typeclass=ITEM_TYPECLASS_PATH,
        key=instance.display_name,
        location=character,
        nohome=True,
    )
    instance.game_object = game_object
    instance.save(update_fields=["game_object"])
    if hasattr(character, "carried_items"):
        character.carried_items.invalidate()
    return game_object
