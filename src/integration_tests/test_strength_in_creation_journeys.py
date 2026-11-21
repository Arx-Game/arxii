"""Journeys for choosing what gives a character strength in creation (#5231).

In the Gift stage a character draws strength from one Primal feeling and may add one
Celestial or Abyssal resonance for what she does to others. The draft refuses a spread that
breaks that rule in the rule's own words, finalizes the even split and the single feeling the
way the spec says (a tie reads Primal; one feeling is wholly Primal), and shows a draft saved
under the old several-picks rule as incomplete. Staff pick a resonance's colour with the
browser's colour picker, and the resonance list the Gift stage reads carries that colour.

A character settled on her feeling is unsettled only when an affinity other than her main one
grows past the range its side is read at: staff grants grow her resonances, and the aura list
reads whether she is unsettled and what made her so.

Driven over the REST seam the browser uses: the draft PATCH and detail, staff adding the draft
to the roster, the aura and resonance lists, and the admin change form.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from evennia.objects.models import ObjectDB
from rest_framework import status

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from integration_tests.test_mending_a_wound_journeys import _filled
from integration_tests.test_several_resonances_journeys import _aura_payload, _share_rows
from world.character_creation.models import CharacterDraft
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models import Resonance
from world.magic.services.drift import drift_for
from world.magic.services.resonance import grant_resonance
from world.roster.models import RosterEntry
from world.seeds.modifier_values import seed_pool_and_cap_lanes

DRAFTS = "/api/character-creation/drafts/"
RESONANCES = "/api/magic/resonances/"

NO_FEELING = "Pick the feeling that gives you strength."
TWO_FEELINGS = "Pick one feeling."
TOO_MANY_OTHERS = "Pick one resonance for what you do to others, or none."


class ChoosingWhatGivesACharacterStrength(FinalizationTestMixin, JourneyCase):
    """Fury and Wonder are Primal, Serenity is Celestial and Domination is Abyssal."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_pool_and_cap_lanes()
        cls._setup_finalization_base(cls, prefix="Strength", height_min=700, height_max=800)
        cls.staff = AccountFactory(is_staff=True)
        cls.celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()
        cls.fury = ResonanceFactory(name="Fury", affinity=cls.primal)
        cls.wonder = ResonanceFactory(name="Wonder", affinity=cls.primal)
        cls.serenity = ResonanceFactory(name="Serenity", affinity=cls.celestial)
        cls.domination = ResonanceFactory(name="Domination", affinity=cls.abyssal)

    def setUp(self) -> None:
        super().setUp()
        self.account = self.staff
        self.client = self.api(self.staff)

    # -- the seams ------------------------------------------------------------

    @staticmethod
    def _weights(*picks: tuple[Resonance, int]) -> list[dict[str, int]]:
        return [{"resonance_id": resonance.pk, "weight": weight} for resonance, weight in picks]

    def _patch(self, draft: CharacterDraft, *picks: tuple[Resonance, int]):
        return self.client.patch(
            f"{DRAFTS}{draft.pk}/",
            {"draft_data": {"gift_resonance_weights": self._weights(*picks)}},
            format="json",
        )

    def _gift_errors(self, draft: CharacterDraft) -> list[str]:
        response = self.client.get(f"{DRAFTS}{draft.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.json()["stage_errors"][str(CharacterDraft.Stage.GIFT)]

    def _finalized_with(self, *picks: tuple[Resonance, int]) -> ObjectDB:
        draft = self._create_base_draft(first_name="Strength")
        self.assertEqual(self._patch(draft, *picks).status_code, status.HTTP_200_OK)
        added = self.client.post(f"{DRAFTS}{draft.pk}/add-to-roster/", {}, format="json")
        self.assertEqual(added.status_code, status.HTTP_200_OK, added.content)
        return ObjectDB.objects.get(pk=added.json()["character_id"])

    # -- the rule -------------------------------------------------------------

    def test_a_draft_with_no_feeling_is_refused_with_the_reason(self) -> None:
        draft = self._create_base_draft(first_name="Strength")

        # Saved partway: a second pick may be made before the feeling.
        self.assertEqual(self._patch(draft, (self.domination, 10)).status_code, 200)

        self.assertEqual(self._gift_errors(draft), [NO_FEELING])

    def test_a_draft_with_no_feeling_cannot_be_added_to_the_roster(self) -> None:
        draft = self._create_base_draft(first_name="Strength")
        self.assertEqual(self._patch(draft, (self.domination, 10)).status_code, 200)
        entries_before = RosterEntry.objects.count()

        added = self.client.post(f"{DRAFTS}{draft.pk}/add-to-roster/", {}, format="json")

        # Refused: no character was made, the draft is still there, and the Gift stage still
        # says why in the words the player reads.
        self.assertEqual(added.status_code, status.HTTP_400_BAD_REQUEST, added.content)
        self.assertNotIn("character_id", added.json())
        self.assertEqual(RosterEntry.objects.count(), entries_before)
        self.assertTrue(CharacterDraft.objects.filter(pk=draft.pk).exists())
        self.assertEqual(self._gift_errors(draft), [NO_FEELING])

    def test_two_feelings_and_a_third_pick_are_refused(self) -> None:
        draft = self._create_base_draft(first_name="Strength")

        two = self._patch(draft, (self.fury, 5), (self.wonder, 5))
        three = self._patch(draft, (self.fury, 4), (self.serenity, 3), (self.domination, 3))

        self.assertEqual(two.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(TWO_FEELINGS, two.content.decode())
        self.assertEqual(three.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(TOO_MANY_OTHERS, three.content.decode())

    def test_a_draft_saved_under_the_old_rule_reads_incomplete(self) -> None:
        draft = self._create_base_draft(first_name="Strength")
        draft.draft_data["gift_resonance_weights"] = self._weights(
            (self.fury, 6), (self.serenity, 1), (self.domination, 3)
        )
        draft.save(update_fields=["draft_data"])

        self.assertEqual(self._gift_errors(draft), [TOO_MANY_OTHERS])

        # The commonest old draft: two Primal picks. It loads and reads incomplete too.
        draft.draft_data["gift_resonance_weights"] = self._weights((self.fury, 5), (self.wonder, 5))
        draft.save(update_fields=["draft_data"])

        self.assertEqual(self._gift_errors(draft), [TWO_FEELINGS])

    # -- what finalize writes -------------------------------------------------

    def test_an_even_split_finalizes_primal(self) -> None:
        character = self._finalized_with((self.fury, 5), (self.serenity, 5))

        payload = _aura_payload(self.client, character)

        self.assertEqual(
            _share_rows(payload),
            {"Primal": (Decimal(50), Decimal(50)), "Celestial": (Decimal(50), Decimal(50))},
        )
        self.assertEqual(payload["dominant_affinity"], "Primal")
        self.assertEqual(drift_for(character.sheet_data).main_affinity, self.primal)

    def test_one_feeling_and_no_second_pick_finalizes_wholly_primal(self) -> None:
        character = self._finalized_with((self.fury, 10))

        payload = _aura_payload(self.client, character)

        self.assertEqual(_share_rows(payload), {"Primal": (Decimal(100), Decimal(100))})
        self.assertEqual(payload["dominant_affinity"], "Primal")
        self.assertIs(payload["unsettled"], False)

    # -- the colour -----------------------------------------------------------

    def test_a_colour_staff_pick_in_admin_is_the_colour_the_list_sends(self) -> None:
        staff = get_user_model().objects.create_user(
            username="colourist", password="pw", is_staff=True, is_superuser=True
        )
        admin_client = Client()
        admin_client.force_login(staff)
        url = reverse("admin:arxii_resonance_change", args=[self.fury.pk])

        page = admin_client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn('type="color"', page.content.decode())
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            data.update(_filled(inline.formset.management_form))
            for form in inline.formset.forms:
                data.update(_filled(form))
        data["color_hex"] = "#C0392B"
        saved = admin_client.post(url, data)
        self.assertEqual(saved.status_code, 302, saved.content[:2000])

        listed = self.client.get(RESONANCES)
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.content)
        colours = {row["name"]: row["color_hex"] for row in listed.json()}
        self.assertEqual(colours["Fury"], "#C0392B")
        self.assertEqual(colours["Wonder"], "#8C8C8C")


class TheAuraReadsUnsettledOnlyPastTheRangeOfASide(JourneyCase):
    """Staff grants grow a character's resonances; the aura list reads whether she is unsettled.

    Hope is Celestial, Fury is Primal and Domination is Abyssal. A character's lifetime
    resonance in each is what her aura's current share is read from, and her aura as it was
    settled is who she is. Her main affinity is the largest settled share. The range before
    Unsettled is 5 percentage points, and a Primal character reads the side she leans toward
    at the own-side range of 15. Hand-worked from the shipped numbers:

    * Primal 80 (settled 10 Celestial, 80 Primal, 10 Abyssal, earned the same): 100 granted
      to Fury makes Primal 180 of 200, 90 percent. Primal is her main affinity and is never
      read, and the other two only shrink. She stays settled.
    * Celestial 80 (settled 80 Celestial, 10 Primal, 10 Abyssal, earned the same): 90 granted
      to Fury makes Primal 100 of 190, 52.6 percent, which stands 52.6 - 10 - 5 = 37.6 past
      its settled share and range. She is unsettled, and Fury made her so.
    * Primal 70 leaning Abyssal (settled 10 Celestial, 70 Primal, 20 Abyssal, earned the same):
      the Abyssal side is read at 15. 20 granted to Domination makes Abyssal 40 of 120, 33.3
      percent, 33.3 - 20 - 15 = -1.7: still inside the range and settled. 10 more makes it 50
      of 130, 38.5 percent, 38.5 - 20 - 15 = 3.5 past: unsettled, and Domination did it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.hope = ResonanceFactory(name="Hope", affinity=self.celestial)
        self.fury = ResonanceFactory(name="Fury", affinity=self.primal)
        self.domination = ResonanceFactory(name="Domination", affinity=self.abyssal)
        self.room = self.make_room("The Lantern")
        self.client = self.api(AccountFactory(is_staff=True))

    def a_character(self, name: str, shares: tuple[int, int, int]):
        """A character settled at ``shares`` (Celestial, Primal, Abyssal), earned the same."""
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        celestial, primal, abyssal = shares
        set_aura_split(
            CharacterAuraFactory(character=sheet),
            celestial=str(celestial),
            primal=str(primal),
            abyssal=str(abyssal),
        )
        for resonance, earned in (
            (self.hope, celestial),
            (self.fury, primal),
            (self.domination, abyssal),
        ):
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=resonance, lifetime_earned=earned
            )
        return character

    @staticmethod
    def staff_grant(character, resonance, amount: int) -> None:
        grant_resonance(character.sheet_data, resonance, amount, source=GainSource.STAFF_GRANT)

    def reading(self, character) -> tuple[bool, str]:
        payload = _aura_payload(self.client, character)
        return payload["unsettled"], payload["unsettled_line"]

    def test_a_primal_character_growing_primal_is_not_unsettled(self) -> None:
        ysmay = self.a_character("Ysmay", (10, 80, 10))
        self.assertEqual(self.reading(ysmay), (False, ""))

        self.staff_grant(ysmay, self.fury, 100)

        self.assertEqual(self.reading(ysmay), (False, ""))

    def test_a_celestial_character_growing_primal_is_unsettled_by_it(self) -> None:
        hobb = self.a_character("Hobb", (80, 10, 10))
        self.assertEqual(self.reading(hobb), (False, ""))

        self.staff_grant(hobb, self.fury, 90)

        self.assertEqual(
            self.reading(hobb),
            (True, "Your Fury has grown strong enough to make you unsettled."),
        )

    def test_a_primal_character_leaning_abyssal_is_unsettled_only_past_the_own_side_range(
        self,
    ) -> None:
        wren = self.a_character("Wren", (10, 70, 20))

        self.staff_grant(wren, self.domination, 20)
        inside = self.reading(wren)
        self.staff_grant(wren, self.domination, 10)
        past = self.reading(wren)

        self.assertEqual(inside, (False, ""))
        self.assertEqual(
            past, (True, "Your Domination has grown strong enough to make you unsettled.")
        )
