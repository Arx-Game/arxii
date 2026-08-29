"""Tests for BeatSerializer's #3425 session-prep nested child rows.

Covers the create path (nested opponent_lines/staged_templates written in one
POST) and, the hardest piece per the approved spec, the update path's
id-based diff: create-missing / update-matched / delete-absent, with the XOR
invariant enforced on staged templates.
"""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.combat.factories import CreatureTemplateFactory
from world.mechanics.factories import ChallengeTemplateFactory, SituationTemplateFactory
from world.stories.constants import BeatKind, BeatOutcome, BeatPredicateType, BeatVisibility
from world.stories.factories import (
    BeatFactory,
    BeatOpponentLineFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
)
from world.stories.models import BeatOpponentLine, BeatStagedTemplate


class BeatSessionPrepCreateTest(APITestCase):
    """Nested opponent_lines/staged_templates are written on create."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.creature = CreatureTemplateFactory()
        cls.situation = SituationTemplateFactory()

    def _base_beat_data(self, kind: str) -> dict:
        return {
            "episode": self.episode.id,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "outcome": BeatOutcome.UNSATISFIED,
            "visibility": BeatVisibility.HINTED,
            "internal_description": "Test beat description",
            "order": 1,
            "kind": kind,
        }

    def test_create_encounter_beat_with_opponent_lines(self):
        """POSTing an ENCOUNTER beat with opponent_lines creates the child rows."""
        self.client.force_authenticate(user=self.staff)
        data = {
            **self._base_beat_data(BeatKind.ENCOUNTER),
            "opponent_lines": [
                {"creature_template": self.creature.pk, "count": 2, "position_name": "front"},
            ],
        }
        response = self.client.post(
            reverse("beat-list"), json.dumps(data), content_type="application/json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        beat_id = response.data["id"]
        lines = list(BeatOpponentLine.objects.filter(beat_id=beat_id))
        assert len(lines) == 1
        assert lines[0].creature_template_id == self.creature.pk
        assert lines[0].count == 2
        assert lines[0].position_name == "front"

    def test_create_situation_beat_with_staged_template(self):
        """POSTing a SITUATION beat with staged_templates creates the child row."""
        self.client.force_authenticate(user=self.staff)
        data = {
            **self._base_beat_data(BeatKind.SITUATION),
            "staged_templates": [{"situation_template": self.situation.pk}],
        }
        response = self.client.post(
            reverse("beat-list"), json.dumps(data), content_type="application/json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        beat_id = response.data["id"]
        lines = list(BeatStagedTemplate.objects.filter(beat_id=beat_id))
        assert len(lines) == 1
        assert lines[0].situation_template_id == self.situation.pk
        assert lines[0].challenge_template_id is None

    @suppress_permission_errors
    def test_staged_template_rejects_both_set(self):
        """Neither-nor-both: a staged template row with BOTH template FKs is a 400."""
        challenge = ChallengeTemplateFactory()
        self.client.force_authenticate(user=self.staff)
        data = {
            **self._base_beat_data(BeatKind.SITUATION),
            "staged_templates": [
                {
                    "situation_template": self.situation.pk,
                    "challenge_template": challenge.pk,
                }
            ],
        }
        response = self.client.post(
            reverse("beat-list"), json.dumps(data), content_type="application/json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @suppress_permission_errors
    def test_staged_template_rejects_neither_set(self):
        """A staged template row with NEITHER template FK set is a 400."""
        self.client.force_authenticate(user=self.staff)
        data = {
            **self._base_beat_data(BeatKind.SITUATION),
            "staged_templates": [{}],
        }
        response = self.client.post(
            reverse("beat-list"), json.dumps(data), content_type="application/json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class BeatSessionPrepUpdateTest(APITestCase):
    """PATCH id-based diff: create-missing / update-matched / delete-absent."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.creature_a = CreatureTemplateFactory()
        cls.creature_b = CreatureTemplateFactory()

    def _patch(self, beat_id: int, data: dict):
        self.client.force_authenticate(user=self.staff)
        url = reverse("beat-detail", kwargs={"pk": beat_id})
        return self.client.patch(url, json.dumps(data), content_type="application/json")

    def test_update_edits_matched_id_and_creates_new_row(self):
        """An id present + a row with no id: one edit, one new row; nothing else changes."""
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        kept = BeatOpponentLineFactory(
            beat=beat, creature_template=self.creature_a, count=1, order=0
        )
        response = self._patch(
            beat.pk,
            {
                "opponent_lines": [
                    {"id": kept.pk, "count": 3, "creature_template": self.creature_a.pk},
                    {"creature_template": self.creature_b.pk, "count": 1},
                ]
            },
        )
        assert response.status_code == status.HTTP_200_OK
        lines = list(BeatOpponentLine.objects.filter(beat=beat).order_by("creature_template_id"))
        assert len(lines) == 2
        kept.refresh_from_db()
        assert kept.count == 3

    def test_update_deletes_row_absent_from_payload(self):
        """An existing line whose id is omitted from the PATCH payload is deleted."""
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        survivor = BeatOpponentLineFactory(beat=beat, creature_template=self.creature_a)
        doomed = BeatOpponentLineFactory(beat=beat, creature_template=self.creature_b)
        response = self._patch(
            beat.pk,
            {
                "opponent_lines": [
                    {"id": survivor.pk, "creature_template": self.creature_a.pk, "count": 1},
                ]
            },
        )
        assert response.status_code == status.HTTP_200_OK
        remaining_ids = set(BeatOpponentLine.objects.filter(beat=beat).values_list("id", flat=True))
        assert remaining_ids == {survivor.pk}
        assert not BeatOpponentLine.objects.filter(pk=doomed.pk).exists()

    def test_patch_omitting_opponent_lines_leaves_them_untouched(self):
        """A PATCH that doesn't mention opponent_lines at all doesn't wipe the roster."""
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        BeatOpponentLineFactory(beat=beat, creature_template=self.creature_a)
        response = self._patch(beat.pk, {"visibility": BeatVisibility.VISIBLE})
        assert response.status_code == status.HTTP_200_OK
        assert BeatOpponentLine.objects.filter(beat=beat).count() == 1

    def test_patch_empty_list_clears_all_lines(self):
        """An explicit empty list clears every existing line (a real, deliberate write)."""
        beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        BeatOpponentLineFactory(beat=beat, creature_template=self.creature_a)
        response = self._patch(beat.pk, {"opponent_lines": []})
        assert response.status_code == status.HTTP_200_OK
        assert BeatOpponentLine.objects.filter(beat=beat).count() == 0
