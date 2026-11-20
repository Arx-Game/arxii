"""Journeys for choosing what gives a character strength in creation (#5231).

In the Gift stage a character draws strength from one Primal feeling and may add one
Celestial or Abyssal resonance for what she does to others. The draft refuses a spread that
breaks that rule in the rule's own words, finalizes the even split and the single feeling the
way the spec says (a tie reads Primal; one feeling is wholly Primal), and shows a draft saved
under the old several-picks rule as incomplete. Staff pick a resonance's colour with the
browser's colour picker, and the resonance list the Gift stage reads carries that colour.

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
from world.magic.factories import ResonanceFactory, ensure_canonical_affinities
from world.magic.models import Resonance
from world.magic.services.drift import drift_for
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
