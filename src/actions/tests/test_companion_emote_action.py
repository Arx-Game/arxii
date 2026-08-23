"""Tests for CompanionEmoteAction and CompanionPresentPrerequisite (#3294).

Covers the presence gate (owned + active + co-located, mirroring
``_resolve_owned_companion``'s owner/active/objectdb standard plus the
room-presence check an emote additionally needs) and the Action's
cosmetic-attribution contract: the recorded Interaction's ``persona`` stays
the owner's own worn face, never the companion.
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory


def _make_companion(owner_sheet, room, *, name="Fang"):
    from evennia import create_object

    from typeclasses.companions import CompanionObject
    from world.companions.factories import CompanionFactory

    obj = create_object(CompanionObject, key=name, location=room)
    return CompanionFactory(owner=owner_sheet, name=name, objectdb=obj)


class CompanionPresentPrerequisiteTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Emote Test Room")
        self.other_room = create_object("typeclasses.rooms.Room", key="Emote Test Room 2")
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()
        self.companion = _make_companion(self.sheet, self.room)

    def test_denied_without_companion_id(self) -> None:
        from actions.prerequisites import CompanionPresentPrerequisite

        met, _reason = CompanionPresentPrerequisite().is_met(
            self.sheet.character, context={"kwargs": {}}
        )
        self.assertFalse(met)

    def test_denied_for_unowned_companion(self) -> None:
        from actions.prerequisites import CompanionPresentPrerequisite

        other_sheet = CharacterSheetFactory()
        other_companion = _make_companion(other_sheet, self.room, name="Rex")

        met, reason = CompanionPresentPrerequisite().is_met(
            self.sheet.character,
            context={"kwargs": {"companion_id": other_companion.pk}},
        )
        self.assertFalse(met)
        self.assertIn("not your companion", reason)

    def test_denied_when_absent_from_room(self) -> None:
        from actions.prerequisites import CompanionPresentPrerequisite

        self.companion.objectdb.location = self.other_room
        self.companion.objectdb.save()

        met, reason = CompanionPresentPrerequisite().is_met(
            self.sheet.character,
            context={"kwargs": {"companion_id": self.companion.pk}},
        )
        self.assertFalse(met)
        self.assertIn("not here", reason)

    def test_denied_when_released(self) -> None:
        from actions.prerequisites import CompanionPresentPrerequisite

        self.companion.released_at = timezone.now()
        self.companion.save(update_fields=["released_at"])

        met, reason = CompanionPresentPrerequisite().is_met(
            self.sheet.character,
            context={"kwargs": {"companion_id": self.companion.pk}},
        )
        self.assertFalse(met)
        self.assertIn("no longer active", reason)

    def test_met_when_owned_active_and_present(self) -> None:
        from actions.prerequisites import CompanionPresentPrerequisite

        met, _reason = CompanionPresentPrerequisite().is_met(
            self.sheet.character,
            context={"kwargs": {"companion_id": self.companion.pk}},
        )
        self.assertTrue(met)


class CompanionEmoteActionTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Emote Action Room")
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()
        self.companion = _make_companion(self.sheet, self.room)

    def test_denied_without_text(self) -> None:
        from actions.definitions.companions import CompanionEmoteAction

        result = CompanionEmoteAction().run(
            actor=self.sheet.character, companion_id=self.companion.pk, text=""
        )
        self.assertFalse(result.success)

    def test_denied_without_companion_id(self) -> None:
        from actions.definitions.companions import CompanionEmoteAction

        result = CompanionEmoteAction().run(actor=self.sheet.character, text="growls.")
        self.assertFalse(result.success)

    def test_denied_when_companion_absent(self) -> None:
        from evennia import create_object

        from actions.definitions.companions import CompanionEmoteAction

        other_room = create_object("typeclasses.rooms.Room", key="Elsewhere")
        self.companion.objectdb.location = other_room
        self.companion.objectdb.save()

        result = CompanionEmoteAction().run(
            actor=self.sheet.character, companion_id=self.companion.pk, text="growls."
        )
        self.assertFalse(result.success)

    def test_records_pose_attributed_to_companion(self) -> None:
        from actions.definitions.companions import CompanionEmoteAction
        from world.scenes.constants import InteractionMode
        from world.scenes.models import Interaction

        result = CompanionEmoteAction().run(
            actor=self.sheet.character,
            companion_id=self.companion.pk,
            text="Fang growls at the intruder.",
        )

        self.assertTrue(result.success, result.message)
        interaction = Interaction.objects.get(content="Fang growls at the intruder.")
        self.assertEqual(interaction.mode, InteractionMode.POSE)
        self.assertEqual(interaction.attributed_companion_id, self.companion.pk)
        # Authorship (block/mute/consent) stays on the owner's own persona,
        # never the companion — the FK is purely cosmetic feed attribution.
        self.assertEqual(interaction.persona.character_sheet_id, self.sheet.pk)
