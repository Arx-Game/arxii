"""Shared test helpers for the dreams test suite (#3003)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.character_sheets.services import create_character_with_sheet
from world.conditions.services import apply_condition, remove_condition
from world.dreams.models import DreamReflection
from world.dreams.services import get_dream_space

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet


class DreamSleeperTestMixin:
    """Sleeping-sheet construction helpers shared across the dreams test suite.

    Callers must set ``self.template`` (the Sleeping ``ConditionTemplate`` row)
    in their own ``setUp`` — typically right after ``ensure_sleeping_condition()``
    — since some suites need extra seed setup interleaved with it (#3003).
    """

    template: object

    def _sleeping_sheet(self, key: str = "Sleeper") -> CharacterSheet:
        """A sleeping character in their own room, with a real dream reflection."""
        char, sheet, _ = create_character_with_sheet(
            character_key=key,
            primary_persona_name=key,
        )
        room = ObjectDBFactory(db_key=f"{key} Room", db_typeclass_path="typeclasses.rooms.Room")
        char.location = room
        char.save()
        self._give_reflection(room)
        apply_condition(target=char, condition=self.template)
        return sheet

    def _give_reflection(self, waking_room: ObjectDB) -> None:
        """Attach a real DreamReflection to ``waking_room``.

        Without this, get_dream_space() falls back to the liminal room and
        every sheet placed in a fresh room would resolve to the SAME
        dreamspace regardless of dreamwalk state, masking bugs in
        dreamspace_for(). The dream room is a real ``Room`` typeclass (not the
        factory's generic ``Object`` default) — its ``scene_data`` is the
        cached_property Room override; a plain Object inherits the generic
        ObjectParent version, which delegates to *its own* location and
        returns None for a topmost room, breaking ``send_room_state()``.
        """
        dream_profile = RoomProfileFactory(
            objectdb=ObjectDBFactory(
                db_key=f"Dream of {waking_room.db_key}",
                db_typeclass_path="typeclasses.rooms.Room",
            )
        )
        DreamReflection.objects.create(
            waking_room=RoomProfileFactory(objectdb=waking_room),
            dream_room=dream_profile,
        )

    def _two_sleepers_in_different_rooms(self) -> tuple[CharacterSheet, CharacterSheet]:
        walker = self._sleeping_sheet("Walker")
        host = self._sleeping_sheet("Host")
        return walker, host

    def _dream_room_of(self, room: ObjectDB) -> ObjectDB | None:
        return get_dream_space(room=room)

    def _wake(self, sheet: CharacterSheet) -> None:
        remove_condition(sheet.character, self.template)
