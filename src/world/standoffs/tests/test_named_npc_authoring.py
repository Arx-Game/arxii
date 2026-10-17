"""Authoring named NPC lines: the story's cast, the beat dialog API and the picker (#4373)."""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CreatureTemplateFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.mechanics.factories import PropertyFactory
from world.standoffs.constants import DriveStrength
from world.standoffs.services.placement import PERSONA_DRIVE_EDIT_ERROR
from world.stories.constants import (
    BeatKind,
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    StakeSubjectKind,
)
from world.stories.factories import (
    BeatFactory,
    BeatOpponentLineFactory,
    ChapterFactory,
    EpisodeFactory,
    StakeFactory,
    StoryFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.models import BeatOpponentLine
from world.stories.services.cast import story_npc_personas


class StoryCastTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.story = StoryFactory()
        cls.beat = BeatFactory(episode=EpisodeFactory(chapter=ChapterFactory(story=cls.story)))
        cls.protected = CharacterSheetFactory()
        cls.staked = CharacterSheetFactory()
        cls.placed = CharacterSheetFactory()
        cls.stranger = CharacterSheetFactory()
        StoryProtectedSubjectFactory(story=cls.story, subject_sheet=cls.protected)
        StakeFactory(
            beat=cls.beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=cls.staked,
            subject_label="",
        )
        BeatOpponentLineFactory(beat=cls.beat, persona=cls.placed.primary_persona)

    def test_the_story_uses_its_protected_staked_and_placed_npcs(self) -> None:
        personas = set(story_npc_personas(self.story))
        self.assertEqual(
            personas,
            {
                self.protected.primary_persona,
                self.staked.primary_persona,
                self.placed.primary_persona,
            },
        )

    def test_another_story_uses_none_of_them(self) -> None:
        self.assertFalse(story_npc_personas(StoryFactory()).exists())


class BeatLinePersonaApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm = AccountFactory(username="named_npc_author_gm")
        GMProfileFactory(account=cls.gm, level=GMLevel.JUNIOR)
        cls.story = StoryFactory(owners=[cls.gm])
        cls.episode = EpisodeFactory(chapter=ChapterFactory(story=cls.story))
        cls.creature = CreatureTemplateFactory()
        cls.npc = CharacterSheetFactory()
        cls.persona = cls.npc.primary_persona
        StoryProtectedSubjectFactory(story=cls.story, subject_sheet=cls.npc)
        cls.stranger = CharacterSheetFactory().primary_persona

    def _post(self, line: dict) -> object:
        self.client.force_authenticate(user=self.gm)
        data = {
            "episode": self.episode.id,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "outcome": BeatOutcome.UNSATISFIED,
            "visibility": BeatVisibility.HINTED,
            "internal_description": "PLACEHOLDER",
            "order": 1,
            "kind": BeatKind.ENCOUNTER,
            "opponent_lines": [{"creature_template": self.creature.pk, "count": 1, **line}],
        }
        return self.client.post(
            reverse("beat-list"), json.dumps(data), content_type="application/json"
        )

    def test_a_gm_places_a_named_npc_the_story_uses(self) -> None:
        response = self._post({"persona": self.persona.pk, "opens_as_standoff": True})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(BeatOpponentLine.objects.get().persona, self.persona)
        self.assertEqual(response.data["opponent_lines"][0]["persona_name"], self.persona.name)

    def test_a_persona_the_story_does_not_use_is_refused(self) -> None:
        response = self._post({"persona": self.stranger.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not a named NPC this story uses", str(response.data))

    def test_a_named_npc_line_spawns_one(self) -> None:
        response = self._post({"persona": self.persona.pk, "count": 3})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_named_npc_line_cannot_edit_drives(self) -> None:
        prop = PropertyFactory()
        response = self._post(
            {
                "persona": self.persona.pk,
                "drive_edits": [{"property": prop.pk, "strength": DriveStrength.MAJOR}],
            }
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(PERSONA_DRIVE_EDIT_ERROR, str(response.data))


class PlacementPersonaPickerTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm = AccountFactory(username="named_npc_picker_gm")
        GMProfileFactory(account=cls.gm, level=GMLevel.JUNIOR)
        cls.other_gm = AccountFactory(username="named_npc_picker_other")
        GMProfileFactory(account=cls.other_gm, level=GMLevel.JUNIOR)
        cls.staff = AccountFactory(username="named_npc_picker_staff", is_staff=True)
        cls.story = StoryFactory(owners=[cls.gm])
        cls.npc = CharacterSheetFactory()
        StoryProtectedSubjectFactory(story=cls.story, subject_sheet=cls.npc)
        cls.stranger = CharacterSheetFactory()

    def _names(self, user: object, **params: object) -> list[str]:
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse("combat:placement-persona-list"), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [row["name"] for row in response.data["results"]]

    def test_the_owner_sees_the_story_cast(self) -> None:
        self.assertEqual(self._names(self.gm, story=self.story.pk), [self.npc.primary_persona.name])

    def test_another_gm_sees_nothing_of_it(self) -> None:
        self.assertEqual(self._names(self.other_gm, story=self.story.pk), [])

    def test_staff_without_a_story_can_search_every_persona(self) -> None:
        names = self._names(self.staff, search=self.stranger.primary_persona.name)
        self.assertIn(self.stranger.primary_persona.name, names)
