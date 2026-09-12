"""Tests for CompanionEmoteAction and CompanionPresentPrerequisite (#3294).

Covers the presence gate (owned + active + co-located, mirroring
``_resolve_owned_companion``'s owner/active/objectdb standard plus the
room-presence check an emote additionally needs) and the Action's
cosmetic-attribution contract: the recorded Interaction's ``persona`` stays
the owner's own worn face, never the companion.
"""

from __future__ import annotations

from unittest.mock import patch
import uuid

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


class CompanionEmoteActionIdempotencyTests(TestCase):
    """#3782 — CompanionEmoteAction routes through idempotent_record_interaction
    when a client_request_id is present, mirroring PoseAction's own wiring
    (#3760 Task 5)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Emote Idempotency Room")
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()
        self.companion = _make_companion(self.sheet, self.room)

    def test_is_idempotent_on_client_request_id(self) -> None:
        from actions.definitions.companions import CompanionEmoteAction
        from world.scenes.constants import InteractionMode
        from world.scenes.models import Interaction

        request_id = uuid.uuid4()
        kwargs = {
            "companion_id": self.companion.pk,
            "text": "grooms itself.",
            "client_request_id": request_id,
        }

        actor = self.sheet.character
        with patch.object(self.room, "msg_contents"):
            first = CompanionEmoteAction().execute(actor=actor, context=None, **kwargs)
            second = CompanionEmoteAction().execute(actor=actor, context=None, **kwargs)

        self.assertTrue(first.success, first.message)
        self.assertTrue(second.success, second.message)
        interactions = Interaction.objects.filter(mode=InteractionMode.POSE)
        self.assertEqual(interactions.count(), 1)
        self.assertEqual(interactions.get().attributed_companion_id, self.companion.pk)

    def test_conflict_on_reused_id_with_different_text(self) -> None:
        from actions.definitions.companions import CompanionEmoteAction
        from world.scenes.constants import InteractionMode
        from world.scenes.models import Interaction

        request_id = uuid.uuid4()

        with patch.object(self.room, "msg_contents"):
            first = CompanionEmoteAction().execute(
                actor=self.sheet.character,
                context=None,
                companion_id=self.companion.pk,
                text="grooms itself.",
                client_request_id=request_id,
            )
            second = CompanionEmoteAction().execute(
                actor=self.sheet.character,
                context=None,
                companion_id=self.companion.pk,
                text="growls at a passerby.",
                client_request_id=request_id,
            )

        self.assertTrue(first.success, first.message)
        self.assertFalse(second.success)
        self.assertEqual(Interaction.objects.filter(mode=InteractionMode.POSE).count(), 1)

    def test_conflict_on_reused_id_with_different_companion(self) -> None:
        """Same text, different companion attribution -- not a legitimate
        replay (mirrors PoseAction's target-identity comparison, #3760
        review Finding 1)."""
        from actions.definitions.companions import CompanionEmoteAction
        from world.scenes.constants import InteractionMode
        from world.scenes.models import Interaction

        other_companion = _make_companion(self.sheet, self.room, name="Claw")
        request_id = uuid.uuid4()

        with patch.object(self.room, "msg_contents"):
            first = CompanionEmoteAction().execute(
                actor=self.sheet.character,
                context=None,
                companion_id=self.companion.pk,
                text="growls.",
                client_request_id=request_id,
            )
            second = CompanionEmoteAction().execute(
                actor=self.sheet.character,
                context=None,
                companion_id=other_companion.pk,
                text="growls.",
                client_request_id=request_id,
            )

        self.assertTrue(first.success, first.message)
        self.assertFalse(second.success)
        self.assertEqual(Interaction.objects.filter(mode=InteractionMode.POSE).count(), 1)

    def test_retry_broadcasts_via_message_location_only_once(self) -> None:
        """A retry must not double-broadcast even though the DB side is
        correctly deduped (mirrors PoseAction/SayAction's equivalent test)."""
        from actions.definitions.companions import CompanionEmoteAction

        request_id = uuid.uuid4()
        kwargs = {
            "companion_id": self.companion.pk,
            "text": "grooms itself.",
            "client_request_id": request_id,
        }

        with patch("flows.service_functions.communication.message_location") as mock_broadcast:
            CompanionEmoteAction().execute(actor=self.sheet.character, context=None, **kwargs)
            CompanionEmoteAction().execute(actor=self.sheet.character, context=None, **kwargs)

        self.assertEqual(mock_broadcast.call_count, 1)

    def test_no_client_request_id_still_records_non_idempotent_pose(self) -> None:
        """Backward compatibility: a caller that omits client_request_id (an
        untouched pre-#3782 caller) still goes through the plain
        record_interaction path unchanged."""
        from actions.definitions.companions import CompanionEmoteAction
        from world.scenes.constants import InteractionMode
        from world.scenes.models import Interaction

        with patch.object(self.room, "msg_contents"):
            result = CompanionEmoteAction().execute(
                actor=self.sheet.character,
                context=None,
                companion_id=self.companion.pk,
                text="grooms itself.",
            )

        self.assertTrue(result.success, result.message)
        self.assertEqual(Interaction.objects.filter(mode=InteractionMode.POSE).count(), 1)
