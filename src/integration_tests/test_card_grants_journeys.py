"""Journeys: the grants the held cards reconcile at finalize (#4852, slice 6 of #4813).

Maud holds no card with a grant behind it, so Final Touches asks her nothing of the kind.
She takes Explosive Drama, With Honors and Capable Mentor through the distinctions sync,
and the draft asks for the story behind the drama, for the organization that takes her
in (the realm's one admitting organization is the only choice), and shows the line naming
her Path's stronger Aspect. She answers, and finalize pays each card: -300 prestige on her
primary persona with her story on the pick, an active membership at the lodge's entry rank
through the membership choke point, and a +5 modifier on Warfare sourced to Capable
Mentor. The expected shapes come from the parent's rulings (a negative starting prestige is
valid, decision 3; no Legend rows from creation, decision 6; the ties and prompts are
optional, decision 5) and the slice's design.
"""

from __future__ import annotations

import json

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import (
    PRESTIGE_STORY_MAX_LENGTH,
    FinalTouchesPrompt,
    OfferArrival,
    OfferChapter,
)
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.classes.factories import (
    AspectFactory,
    DistinctionPathAspectGrantFactory,
    PathAspectFactory,
)
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.mechanics.models import CharacterModifier
from world.societies.factories import (
    DistinctionOrganizationGrantFactory,
    DistinctionPrestigeGrantFactory,
    OrganizationFactory,
    SocietyFactory,
)
from world.societies.membership_services import active_membership_for_persona
from world.societies.models import LegendEntry, OrganizationMembership

STORY = "They say the duel over me emptied a chapel. It was a tavern, and I was not there."
CATALOG_URL = "/api/distinctions/distinctions/?draft={pk}"


class TheCardGrantsAtFinalize(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.room = self.make_room("The Lodge Steps")
        self.player = self.make_player("Maud", room=self.room)
        self.account = self.account_of(self.player)
        self._setup_finalization_base(self, prefix="Grants", height_min=700, height_max=800)
        self.society = SocietyFactory(name="The People of the Grants", realm=self.realm)
        self.lodge = OrganizationFactory(
            name="The Honor Lodge", society=self.society, admits_player_characters=True
        )
        self.closed_house = OrganizationFactory(name="A Closed House", society=self.society)
        self.warfare = AspectFactory(name="Warfare")
        self.martial = AspectFactory(name="Martial")
        PathAspectFactory(character_path=self.path, aspect=self.warfare, weight=2)
        PathAspectFactory(character_path=self.path, aspect=self.martial, weight=1)

        self.drama = DistinctionFactory(name="Explosive Drama", cost_per_rank=-10, max_rank=1)
        DistinctionPrestigeGrantFactory(distinction=self.drama, amount=-300)
        self.honors = DistinctionFactory(name="With Honors", cost_per_rank=5, max_rank=1)
        self.honors_grant = DistinctionOrganizationGrantFactory(distinction=self.honors)
        self.mentor = DistinctionFactory(name="Capable Mentor", cost_per_rank=10, max_rank=1)
        DistinctionPathAspectGrantFactory(distinction=self.mentor, value=5)
        self.offers = {
            card: DistinctionOfferFactory(
                distinction=card,
                chapter=OfferChapter.ACTORS_SHEET,
                arrives_as=OfferArrival.CHOICE,
                prompt=prompt,
            )
            for card, prompt in (
                (self.drama, "never_do"),
                (self.honors, "protect"),
                (self.mentor, "fear"),
            )
        }
        self.draft = self._create_base_draft(first_name="Maud")
        self.client = self.api(self.account)

    def _draft_url(self) -> str:
        return f"/api/character-creation/drafts/{self.draft.pk}/"

    def _sync(self, *cards) -> object:
        return self.client.put(
            f"/api/distinctions/drafts/{self.draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": card.pk, "rank": 1, "offer_id": self.offers[card].pk} for card in cards
                ]
            },
            format="json",
        )

    def _patch(self, draft_data: dict) -> object:
        return self.client.patch(self._draft_url(), {"draft_data": draft_data}, format="json")

    def test_the_held_cards_ask_at_final_touches_and_finalize_pays_each_grant(self) -> None:
        # Nothing with a grant behind it: no ask, no organization list.
        payload = self.client.get(self._draft_url()).json()
        self.assertEqual(payload["final_touches_prompts"], [])
        self.assertEqual(payload["final_touches_cards"], [])
        self.assertEqual(payload["organization_choices"], [])

        # The catalog prices each grant in words beside the card.
        catalog = self.client.get(CATALOG_URL.format(pk=self.draft.pk))
        self.assertEqual(catalog.status_code, 200, catalog.content)
        lines = {
            row["name"]: [effect["text"] for effect in row["effects_summary"]]
            for row in catalog.json()
        }
        self.assertIn("Starts with -300 prestige", lines["Explosive Drama"])
        self.assertIn(
            "Opens a membership in an organization of your realm, your pick at Final Touches",
            lines["With Honors"],
        )
        self.assertIn("+5 to your Path's stronger Aspect", lines["Capable Mentor"])

        # The three cards taken: each ask arrives, in enum order, naming its card.
        response = self._sync(self.drama, self.honors, self.mentor)
        self.assertEqual(response.status_code, 200, response.content)
        payload = self.client.get(self._draft_url()).json()
        self.assertEqual(
            payload["final_touches_prompts"],
            [
                FinalTouchesPrompt.PRESTIGE_STORY.value,
                FinalTouchesPrompt.ORGANIZATION.value,
                FinalTouchesPrompt.PATH_ASPECT.value,
            ],
        )
        self.assertEqual(
            payload["final_touches_cards"],
            [
                {
                    "distinction_id": self.drama.pk,
                    "name": "Explosive Drama",
                    "prompt": "prestige_story",
                    "detail": "",
                    "choices": [],
                },
                {
                    "distinction_id": self.honors.pk,
                    "name": "With Honors",
                    "prompt": "organization",
                    "detail": "",
                    # The ask carries its choices too since #4856, the same list as below.
                    "choices": [
                        {"id": self.lodge.pk, "name": "The Honor Lodge", "is_covert": False}
                    ],
                },
                {
                    "distinction_id": self.mentor.pk,
                    "name": "Capable Mentor",
                    "prompt": "path_aspect",
                    "detail": "Warfare",
                    "choices": [],
                },
            ],
        )
        self.assertEqual(
            payload["organization_choices"],
            [{"id": self.lodge.pk, "name": "The Honor Lodge", "is_covert": False}],
        )

        # The answers: the limits are named, an organization outside the list is refused.
        too_long = {str(self.drama.pk): "x" * (PRESTIGE_STORY_MAX_LENGTH + 1)}
        response = self._patch({"prestige_stories": too_long})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(str(PRESTIGE_STORY_MAX_LENGTH), response.content.decode())
        response = self._patch({"organizations": {str(self.honors.pk): self.closed_house.pk}})
        self.assertEqual(response.status_code, 400, response.content)
        response = self._patch(
            {
                "prestige_stories": {str(self.drama.pk): STORY},
                "organizations": {str(self.honors.pk): self.lodge.pk},
            }
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Finalize pays each grant once.
        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        sheet = character.sheet_data
        primary = sheet.primary_persona
        primary.refresh_from_db()
        self.assertEqual(primary.prestige_from_deeds, -300)
        self.assertEqual(primary.total_prestige, -300)
        self.assertFalse(LegendEntry.objects.filter(persona=primary).exists())
        pick = CharacterDistinction.objects.get(character=sheet, distinction=self.drama)
        self.assertEqual(pick.notes, STORY)
        membership = active_membership_for_persona(self.lodge, primary)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.rank.tier, 5)
        self.assertEqual(OrganizationMembership.objects.filter(persona=primary).count(), 1)
        (bonus,) = CharacterModifier.objects.filter(
            character=sheet, target__target_aspect=self.warfare
        )
        self.assertEqual(bonus.value, 5)
        self.assertEqual(bonus.source.source_display, "Distinction: Capable Mentor")
        self.assertFalse(
            CharacterModifier.objects.filter(character=sheet, target__target_aspect=self.martial)
        )

        # The story is the player's own words about the card, and reads on the sheet.
        staff = self.api(AccountFactory(is_staff=True))
        response = staff.get(f"/api/character-sheets/{sheet.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(STORY, json.dumps(response.json()))

    def test_an_unanswered_organization_seats_nothing(self) -> None:
        response = self._sync(self.honors)
        self.assertEqual(response.status_code, 200, response.content)
        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        primary = character.sheet_data.primary_persona
        self.assertFalse(OrganizationMembership.objects.filter(persona=primary).exists())

    def test_a_grant_with_its_own_organization_asks_nothing_and_seats_it(self) -> None:
        self.honors_grant.organization = self.closed_house
        self.honors_grant.save()
        response = self._sync(self.honors)
        self.assertEqual(response.status_code, 200, response.content)
        payload = self.client.get(self._draft_url()).json()
        self.assertEqual(payload["final_touches_prompts"], [])
        self.assertEqual(payload["organization_choices"], [])
        catalog = self.client.get(CATALOG_URL.format(pk=self.draft.pk)).json()
        (honors,) = [row for row in catalog if row["name"] == "With Honors"]
        self.assertIn(
            "Opens a membership in A Closed House",
            [effect["text"] for effect in honors["effects_summary"]],
        )
        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        primary = character.sheet_data.primary_persona
        self.assertIsNotNone(active_membership_for_persona(self.closed_house, primary))
