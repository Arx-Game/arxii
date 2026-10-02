"""Shared test helpers for a price's real cost (#4099)."""

from evennia_extensions.factories import ObjectDBFactory
from world.items.factories import ItemInstanceFactory
from world.items.models import ItemInstance
from world.magic.factories import CharacterAnimaFactory
from world.mechanics.factories import CharacterEngagementFactory


def make_caster():
    """A caster with full anima and an engagement, ready for ``use_technique``."""
    anima = CharacterAnimaFactory(current=50, maximum=50)
    sheet = anima.character
    CharacterEngagementFactory(character=sheet)
    return sheet.character, sheet


def carry(character, template, quantity: int = 1) -> ItemInstance:
    """Put ``quantity`` of ``template`` in ``character``'s carried inventory."""
    obj = ObjectDBFactory(
        db_key=f"carried {template.name}", db_typeclass_path="typeclasses.objects.Object"
    )
    obj.location = character
    obj.save()
    instance = ItemInstanceFactory(template=template, quantity=quantity, game_object=obj)
    character.carried_items.invalidate()
    return instance
