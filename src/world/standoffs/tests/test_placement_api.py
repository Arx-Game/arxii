"""The beat dialog's and mission studio's placement fields, over the real API (#4361)."""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.combat.constants import CauseKind
from world.combat.factories import CreatureTemplateFactory
from world.mechanics.factories import PropertyFactory
from world.societies.factories import OrganizationFactory
from world.standoffs.constants import DriveStrength
from world.standoffs.factories import CreatureDriveFactory, FactionRuleFactory
from world.standoffs.models import OpponentLineDrive, OpponentLineFactionRuleSuppression
from world.stories.constants import BeatKind, BeatOutcome, BeatPredicateType, BeatVisibility
from world.stories.factories import ChapterFactory, EpisodeFactory, StoryFactory
from world.stories.models import BeatOpponentLine


class BeatPlacementApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.episode = EpisodeFactory(chapter=ChapterFactory(story=cls.story))
        cls.company = OrganizationFactory(name="PLACEHOLDER Company")
        cls.creature = CreatureTemplateFactory(cause=CauseKind.ORDERS, organization=cls.company)
        cls.greedy = PropertyFactory(name="PLACEHOLDER Greedy")
        CreatureDriveFactory(
            creature_template=cls.creature, property=cls.greedy, strength=DriveStrength.MAJOR
        )
        cls.company_rule = FactionRuleFactory(
            creature_template=None, organization=cls.company, rule={}
        )

    def _post(self, line: dict) -> object:
        self.client.force_authenticate(user=self.staff)
        data = {
            "episode": self.episode.id,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "outcome": BeatOutcome.UNSATISFIED,
            "visibility": BeatVisibility.HINTED,
            "internal_description": "PLACEHOLDER",
            "order": 1,
            "kind": BeatKind.ENCOUNTER,
            "opponent_lines": [{"creature_template": self.creature.pk, "count": 6, **line}],
        }
        return self.client.post(
            reverse("beat-list"), json.dumps(data), content_type="application/json"
        )

    def test_the_beat_dialog_saves_every_placement_field(self) -> None:
        response = self._post(
            {
                "opens_as_standoff": True,
                "cause_override": CauseKind.PREDATION,
                "cause_margin_override": 20,
                "drive_edits": [{"property": self.greedy.pk, "strength": DriveStrength.DEFINING}],
                "suppressed_faction_rules": [self.company_rule.pk],
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        line = BeatOpponentLine.objects.get()
        self.assertEqual(
            (line.cause_override, line.cause_margin_override), (CauseKind.PREDATION, 20)
        )
        self.assertEqual(
            list(OpponentLineDrive.objects.values_list("property_id", "strength")),
            [(self.greedy.pk, DriveStrength.DEFINING)],
        )
        self.assertTrue(OpponentLineFactionRuleSuppression.objects.filter(beat_line=line).exists())
        echoed = response.data["opponent_lines"][0]
        self.assertEqual(echoed["suppressed_faction_rules"], [self.company_rule.pk])
        self.assertEqual(
            echoed["drive_edits"],
            [{"property": self.greedy.pk, "strength": DriveStrength.DEFINING}],
        )

    def test_switching_off_a_rule_the_line_does_not_inherit_is_a_400(self) -> None:
        stranger = FactionRuleFactory(rule={})
        response = self._post({"suppressed_faction_rules": [stranger.pk]})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(BeatOpponentLine.objects.exists())

    def test_the_placement_context_lists_the_template_and_inherited_rules(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("combat:creature-template-placement-context", args=[self.creature.pk])
        data = self.client.get(url).data
        self.assertEqual(data["cause"], CauseKind.ORDERS)
        self.assertEqual(data["organization_name"], self.company.name)
        self.assertEqual(
            [(d["property"], d["strength"]) for d in data["drives"]],
            [(self.greedy.pk, DriveStrength.MAJOR)],
        )
        self.assertEqual(
            [(r["faction_rule_id"], r["source"]) for r in data["inherited_rules"]],
            [(self.company_rule.pk, self.company.name)],
        )
        other = OrganizationFactory()
        data = self.client.get(url, {"organization": other.pk}).data
        self.assertEqual(data["inherited_rules"], [])

    def test_a_player_cannot_read_the_placement_context(self) -> None:
        self.client.force_authenticate(user=AccountFactory())
        url = reverse("combat:creature-template-placement-context", args=[self.creature.pk])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)
