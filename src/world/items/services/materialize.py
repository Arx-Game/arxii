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
    from world.items.models import ItemInstance, ItemTemplate

# Plain object typeclass — the same one item ObjectDBs use throughout the
# test factories (``evennia_extensions.factories.ObjectDBFactory`` default);
# items have no bespoke typeclass in this codebase.
ITEM_TYPECLASS_PATH = "typeclasses.objects.Object"


def apply_template_properties(obj: ObjectDB, item_template: ItemTemplate) -> None:  # noqa: OBJECTDB_PARAM
    """Copy ``item_template``'s declared default Properties onto ``obj``.

    Bridge-object half of #2503: a bare object's affordances (flammable,
    heavy, ...) come from its template's authored ``ItemTemplateProperty``
    rows, read by the same oracle that reads granted-technique Properties
    (``mechanics.ObjectProperty``). Upserts per-property
    (``update_or_create``, mirroring ``effect_handlers._add_property``) so
    re-materializing the same instance never duplicates rows. A template
    with no declared rows is a no-op — no writes issued.
    """
    from world.mechanics.models import ObjectProperty  # noqa: PLC0415

    for template_property in item_template.default_properties.select_related("property").all():
        ObjectProperty.objects.update_or_create(
            object=obj,
            property=template_property.property,
            defaults={"value": template_property.value},
        )


def _create_item_object_db(instance: ItemInstance, location: ObjectDB) -> ObjectDB:  # noqa: OBJECTDB_PARAM
    """Create + link the physical ``ObjectDB`` for ``instance`` at ``location``.

    The shared chokepoint underlying both public materialize functions below —
    mirrors the ``ObjectDBFactory`` creation pattern (``create_object`` with an
    explicit typeclass and ``nohome=True``), links ``instance.game_object`` back,
    and applies the template's default ``ObjectProperty`` rows
    (``apply_template_properties``). ``location`` may be a character (inventory
    placement) or a room (GM-staged prop, #2503) — this function doesn't care
    which, which is the point: there is exactly one place an ``ItemInstance``
    gains a physical ``ObjectDB``.
    """
    game_object = create_object(
        typeclass=ITEM_TYPECLASS_PATH,
        key=instance.display_name,
        location=location,
        nohome=True,
    )
    instance.game_object = game_object
    instance.save(update_fields=["game_object"])
    apply_template_properties(game_object, instance.template)
    return game_object


def materialize_item_game_object(
    instance: ItemInstance,
    holder_sheet: CharacterSheet,
) -> ObjectDB | None:
    """Create + link the physical ``ObjectDB`` for ``instance`` in the holder's inventory.

    The object is placed on the holder's character (location = the character
    ObjectDB) and the character's ``carried_items`` cache is invalidated so
    the next inventory read sees the new item.

    Returns ``None`` (leaving the instance row-only, the narrative-grant
    behavior) when the sheet has no character object to place the item on —
    a defensive guard; ``CharacterSheet.character`` is the PK so a live sheet
    always has one.
    """
    character = holder_sheet.character
    if character is None:
        return None
    game_object = _create_item_object_db(instance, character)
    if hasattr(character, "carried_items"):
        character.carried_items.invalidate()
    return game_object


def materialize_item_game_object_in_room(instance: ItemInstance, room: ObjectDB) -> ObjectDB:  # noqa: OBJECTDB_PARAM
    """Create + link the physical ``ObjectDB`` for ``instance`` directly in ``room``.

    The GM stage-prop path (#2503) — a conjured torch belongs to the room itself,
    not to any character's inventory, so there is no holder/carried-items step
    (unlike ``materialize_item_game_object``). Always returns an ``ObjectDB``
    (``room`` is caller-resolved and never ``None``, unlike the holder-sheet
    defensive-``None`` case above).
    """
    return _create_item_object_db(instance, room)
