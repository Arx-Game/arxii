"""Tests for BeatSerializer's nested ``staged_battle`` (#3569).

Covers the create path (a staged battle with unit lines written in one POST),
the update path's id-based diff on unit lines and the omitted/null sentinel
split, and the validate()-level invariants that mirror BeatStagedBattle.clean()
as 400 responses: only an ENCOUNTER beat may stage a battle, and a beat may
carry either opponent_lines or a staged battle, never both.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.battles.constants import BattleSideRole
from world.battles.factories import BattleMapBlueprintFactory, BattleUnitTemplateFactory
from world.combat.factories import CreatureTemplateFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import BeatKind, BeatOutcome, BeatPredicateType, BeatVisibility
from world.stories.factories import (
    BeatFactory,
    BeatStagedBattleFactory,
    BeatStagedBattleUnitFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
)
from world.stories.models import Beat, BeatStagedBattle


class BeatStagedBattleAPITest(APITestCase):
    """Nested staged_battle create/update/validation on BeatSerializer (#3569)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)
        cls.story = StoryFactory(owners=[cls.lead_gm_account], primary_table=cls.gm_table)
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.creature = CreatureTemplateFactory()
        cls.blueprint = BattleMapBlueprintFactory()
        cls.template = BattleUnitTemplateFactory()

    def _base_payload(self, kind: str) -> dict:
        return {
            "episode": self.episode.id,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "outcome": BeatOutcome.UNSATISFIED,
            "visibility": BeatVisibility.HINTED,
            "internal_description": "Test beat description",
            "order": 1,
            "kind": kind,
        }

    def test_create_encounter_beat_with_a_staged_battle(self) -> None:
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            **self._base_payload(kind=BeatKind.ENCOUNTER),
            "staged_battle": {
                "blueprint": self.blueprint.pk,
                "name": "Hold the gate",
                "party_side_role": BattleSideRole.DEFENDER,
                "unit_lines": [
                    {
                        "template": self.template.pk,
                        "side_role": BattleSideRole.ATTACKER,
                        "place_name": "Outer Gate",
                        "count": 3,
                        "order": 0,
                    },
                ],
            },
        }
        response = self.client.post(reverse("beat-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        staged = response.data["staged_battle"]
        self.assertEqual(staged["blueprint"], self.blueprint.pk)
        self.assertEqual(staged["blueprint_name"], self.blueprint.name)
        self.assertEqual(staged["unit_lines"][0]["place_name"], "Outer Gate")
        beat = Beat.objects.get(pk=response.data["id"])
        self.assertEqual(beat.staged_battle.unit_lines.count(), 1)

    def test_patch_replaces_unit_lines_by_id_and_null_deletes(self) -> None:
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        staged = BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        keep = BeatStagedBattleUnitFactory(staged_battle=staged, count=1)
        BeatStagedBattleUnitFactory(staged_battle=staged, count=9)
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.patch(
            reverse("beat-detail", args=[beat.pk]),
            {
                "staged_battle": {
                    "blueprint": self.blueprint.pk,
                    "unit_lines": [
                        {"id": keep.pk, "template": keep.template_id, "count": 5},
                        {
                            "template": self.template.pk,
                            "side_role": BattleSideRole.DEFENDER,
                            "count": 2,
                        },
                    ],
                }
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        counts = sorted(staged.unit_lines.values_list("count", flat=True))
        self.assertEqual(counts, [2, 5])
        response = self.client.patch(
            reverse("beat-detail", args=[beat.pk]), {"staged_battle": None}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(BeatStagedBattle.objects.filter(beat=beat).exists())
        self.assertIsNone(response.data["staged_battle"])

    def test_omitted_staged_battle_is_untouched(self) -> None:
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.patch(
            reverse("beat-detail", args=[beat.pk]),
            {"internal_description": "renamed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(BeatStagedBattle.objects.filter(beat=beat).exists())

    def test_situation_beat_with_staged_battle_is_rejected(self) -> None:
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            **self._base_payload(kind=BeatKind.SITUATION),
            "staged_battle": {"blueprint": self.blueprint.pk, "unit_lines": []},
        }
        response = self.client.post(reverse("beat-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("staged_battle", response.data)

    def test_opponent_lines_and_staged_battle_together_are_rejected(self) -> None:
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            **self._base_payload(kind=BeatKind.ENCOUNTER),
            "opponent_lines": [
                {
                    "creature_template": self.creature.pk,
                    "count": 1,
                    "position_name": "",
                    "order": 0,
                }
            ],
            "staged_battle": {"blueprint": self.blueprint.pk, "unit_lines": []},
        }
        response = self.client.post(reverse("beat-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_kind_change_away_from_encounter_with_a_staged_battle_is_rejected(self) -> None:
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.patch(
            reverse("beat-detail", args=[beat.pk]),
            {"kind": BeatKind.SITUATION},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_adding_opponent_lines_to_a_battle_beat_is_rejected(self) -> None:
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.patch(
            reverse("beat-detail", args=[beat.pk]),
            {
                "opponent_lines": [
                    {
                        "creature_template": self.creature.pk,
                        "count": 1,
                        "position_name": "",
                        "order": 0,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_switching_from_battle_to_opponents_in_one_patch_is_allowed(self) -> None:
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.patch(
            reverse("beat-detail", args=[beat.pk]),
            {
                "staged_battle": None,
                "opponent_lines": [
                    {
                        "creature_template": self.creature.pk,
                        "count": 1,
                        "position_name": "",
                        "order": 0,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(beat.opponent_lines.count(), 1)
        self.assertFalse(BeatStagedBattle.objects.filter(beat=beat).exists())
