"""Tests for ClassLevelAdvancement witness recording (#1700).

Verifies that scene attendees (via Interaction) are recorded as official
witnesses on the ClassLevelAdvancement receipt when fire_session runs
advance_class_level_via_session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory, PathFactory
from world.classes.models import PathStage
from world.magic.factories import RitualOfTheDuranceFactory
from world.magic.services.sessions import accept_session, draft_session, fire_session
from world.progression.models import CharacterPathHistory
from world.progression.models.unlocks import CharacterUnlock, ClassLevelUnlock
from world.scenes.factories import SceneFactory

_CHECK = "world.progression.services.spends.check_requirements_for_unlock"


class DuranceWitnessTests(TestCase):
    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        self.officiant = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=self.officiant.character,
            character_class=CharacterClassFactory(),
            level=10,
            is_primary=True,
        )
        CharacterPathHistory.objects.create(character=self.officiant, path=self.path)
        self.cls = CharacterClassFactory()
        self.inductee = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=self.inductee.character,
            character_class=self.cls,
            level=2,
            is_primary=True,
        )
        CharacterPathHistory.objects.create(character=self.inductee, path=self.path)
        ClassLevelUnlock.objects.create(character_class=self.cls, target_level=3)
        CharacterUnlock.objects.create(
            character=self.inductee,
            character_class=self.cls,
            target_level=3,
        )
        # Witness friend, co-located, posing into the active scene.
        self.friend = CharacterSheetFactory()
        self.friend.character.location = self.inductee.character.location
        self.friend.character.save()
        self.scene = SceneFactory(location=self.inductee.character.location, is_active=True)

    def _interact(self, sheet: CharacterSheet) -> None:
        # Minimal Interaction so scene_witness_personas counts the friend's persona.
        from world.scenes.models import Interaction

        Interaction.objects.create(
            scene=self.scene,
            persona=sheet.primary_persona,
            content="bears witness",
            pose_kind="standard",
        )

    def test_scene_attendee_recorded_as_witness(self) -> None:
        self._interact(self.friend)
        self._interact(self.inductee)
        session = draft_session(
            ritual=RitualOfTheDuranceFactory(),
            initiator=self.officiant,
            proposed_terms="",
            session_kwargs={},
            invitee_sheets=[self.inductee],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        part = session.participants.get(character_sheet=self.inductee)
        accept_session(
            participant=part,
            participant_kwargs={"testament": "I am ready."},
            references=[],
        )
        with mock.patch(_CHECK, return_value=(True, [])):
            receipts = fire_session(session=session)
        witnesses = list(receipts[0].witnesses.all())
        self.assertIn(self.friend.primary_persona, witnesses)
        self.assertNotIn(self.inductee.primary_persona, witnesses)
