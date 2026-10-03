"""The Audere surge and the chosen ultimate as narratable events (#4101 Task 7)."""

from unittest import mock

from django.db import DatabaseError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind
from world.gm.models import GMPrompt
from world.magic.audere import _announce_surge
from world.magic.factories import AudereThresholdFactory, CharacterSurgeTextFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction


def _placed_sheet():
    """A sheet whose character stands in its own room with its own active scene.

    Factory characters default to location=None, and ``active_for_room(None)``
    matches EVERY location-less active scene, so ``.first()`` would be arbitrary
    once a class creates more than one. A room per test makes the scene unambiguous.
    """
    room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
    sheet = CharacterSheetFactory()
    sheet.character.location = room
    sheet.character.save()
    return sheet, SceneFactory(location=room)


class SurgeNarrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.threshold = AudereThresholdFactory(surge_manifestation_text="{name} blazes.")

    def test_no_gm_emits_tier_line(self):
        sheet, _scene = _placed_sheet()
        _announce_surge(sheet.character, self.threshold)
        name = sheet.primary_persona.name
        self.assertTrue(
            Interaction.objects.filter(
                content=f"{name} blazes.", mode=InteractionMode.EMIT
            ).exists()
        )

    def test_prepared_surge_line_wins(self):
        sheet, _scene = _placed_sheet()
        CharacterSurgeTextFactory(character_sheet=sheet, surge_text="{name} burns gold.")
        _announce_surge(sheet.character, self.threshold)
        self.assertTrue(
            Interaction.objects.filter(content=f"{sheet.primary_persona.name} burns gold.").exists()
        )

    def test_gm_present_prompts_instead(self):
        sheet, scene = _placed_sheet()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        _announce_surge(sheet.character, self.threshold)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.AUDERE_SURGE, addressed_to=gm)
        self.assertEqual(prompt.room_text, f"{sheet.primary_persona.name} blazes.")
        self.assertFalse(Interaction.objects.filter(content=prompt.room_text).exists())

    def test_blank_line_no_gm_stays_silent(self):
        blank = AudereThresholdFactory.build(surge_manifestation_text="")
        sheet, _scene = _placed_sheet()
        before = Interaction.objects.count()
        _announce_surge(sheet.character, blank)
        self.assertEqual(Interaction.objects.count(), before)

    def test_surging_players_own_gm_account_is_excluded_default_line_goes_out(self):
        """The surging character's own player, who also GMs the scene, is never
        addressed about their own surge (#4101 fix round 1, mirrors the
        Crossing's M5 exclusion) -- the default room line still goes out
        unprompted since there is then no OTHER GM to prompt."""
        sheet, scene = _placed_sheet()
        own_account = AccountFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=own_account),
            end_date=None,
        )
        SceneGMParticipationFactory(scene=scene, account=own_account)

        _announce_surge(sheet.character, self.threshold)

        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.AUDERE_SURGE).exists())
        name = sheet.primary_persona.name
        self.assertTrue(
            Interaction.objects.filter(
                content=f"{name} blazes.", mode=InteractionMode.EMIT
            ).exists()
        )

    def test_routing_database_error_falls_back_to_unprompted_delivery_once(self):
        """#4101 fix round 1: with TWO candidate GMs, the SECOND
        ``GMPrompt.objects.create`` raises -- proving ``route_narratable_event``'s
        atomic wrap rolls the whole batch back (the first GM's already-created
        prompt doesn't survive as an orphan). No GM notify fires, and the
        fallback delivers the default line exactly once."""
        sheet, scene = _placed_sheet()
        gm = AccountFactory()
        second_gm = AccountFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        SceneGMParticipationFactory(scene=scene, account=second_gm)

        original_create = GMPrompt.objects.create
        calls = {"n": 0}

        def _raise_on_second(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                msg = "boom"
                raise DatabaseError(msg)
            return original_create(*args, **kwargs)

        with mock.patch.object(GMPrompt.objects, "create", side_effect=_raise_on_second):
            with mock.patch("world.gm.prompt_services.notify_gm_prompt") as notify:
                _announce_surge(sheet.character, self.threshold)

        notify.assert_not_called()
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.AUDERE_SURGE).exists())
        name = sheet.primary_persona.name
        self.assertEqual(
            Interaction.objects.filter(
                content=f"{name} blazes.", mode=InteractionMode.EMIT
            ).count(),
            1,
        )
