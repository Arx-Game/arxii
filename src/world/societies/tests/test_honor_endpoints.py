"""DRF tests for the Rite of Honors web API (#3466 Task 9).

``GET /api/societies/deeds/{id}/`` (deed detail + honors + ``can_honor``),
``POST /api/societies/deeds/{id}/honor/`` (amplify), and
``POST /api/societies/events/{id}/establish/`` (mint a fresh deed).

Both write actions dispatch through ``PerformRitualAction`` (the same seam
telnet's ``ritual`` command uses), so the honorer needs a magical profile
(``hedge_accessible=False`` on the seeded ritual) — every fixture here mirrors
``test_honors_ritual.py``'s setup for that reason.
"""

from __future__ import annotations

import json

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.currency.services import mint_favor_token
from world.magic.factories import CharacterAuraFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.societies.constants import DeedKnowledgeSource
from world.societies.factories import (
    LegendEntryFactory,
    LegendEventFactory,
    LegendHonorFactory,
    LegendLevelCalibrationFactory,
    OrganizationFactory,
)
from world.societies.knowledge_services import grant_deed_knowledge
from world.societies.models import LegendEntry, LegendHonor, LegendLevelCalibration
from world.societies.seeds import ensure_rite_of_honors_ritual


def _active_primary_persona(*, account):
    """Create a character sheet + active tenure and return its primary persona.

    Mirrors ``test_org_appeal_api.py``'s helper of the same name — ``_active_persona_
    for_request`` (``world/societies/views.py``) walks the roster tenure, so a bare
    ``CharacterSheetFactory()`` with no tenure resolves to no active persona at all.
    """
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    roster = RosterFactory()
    entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
    player_data = PlayerData.objects.create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    entry.invalidate_tenure_cache()
    return sheet.primary_persona


@override_settings(SEED_SAMPLE_CONTENT=True)
class HonorEndpointsTests(APITestCase):
    """Deed detail (+ ``can_honor``), the ``honor`` action, and the no-account-leak test."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rite = ensure_rite_of_honors_ritual()
        cls.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)
        # Both the honorer's own level (0, the CharacterSheetFactory default) and the
        # deed's station (also 0 here) need a calibration row: maybe_grant_deed_title
        # (world.achievements.services) runs at the end of EVERY successful honor_deed
        # call, keyed on the DEED's earned_at_level, not the honorer's.
        cls.calibration = LegendLevelCalibrationFactory(
            level=0, honor_hares_required=1, honor_value_added=10, deed_title_threshold=100
        )

    def setUp(self) -> None:
        self.client = APIClient()

        self.honorer_account = AccountFactory()
        self.honorer_persona = _active_primary_persona(account=self.honorer_account)
        self.honorer_sheet = self.honorer_persona.character_sheet
        # hedge_accessible=False (ruling): the performer needs a magical profile or
        # PerformRitualAction refuses the ritual outright, before honor_deed runs.
        CharacterAuraFactory(character=self.honorer_sheet)

        self.honoree_account = AccountFactory()
        self.honoree_persona = _active_primary_persona(account=self.honoree_account)

        self.scene = SceneFactory()
        self.event = LegendEventFactory(base_value=100, scene=self.scene)
        self.deed = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=20, earned_at_level=0
        )

        # The account with no persona at all: authenticated, but no CharacterSheet/
        # roster tenure behind it.
        self.no_persona_account = AccountFactory()

    def _mint_hare(self, sheet) -> None:
        mint_favor_token(self.academy, sheet, provenance_note="A deed done")

    def _grant_knowledge(self) -> None:
        grant_deed_knowledge(
            deed=self.deed,
            personas=[self.honorer_persona],
            source=DeedKnowledgeSource.WITNESSED,
        )

    def test_anonymous_is_refused(self) -> None:
        response = self.client.get(reverse("societies:deed-detail", args=[self.deed.pk]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_honor_false_without_active_persona(self) -> None:
        self.client.force_authenticate(user=self.no_persona_account)
        response = self.client.get(reverse("societies:deed-detail", args=[self.deed.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        can_honor = response.data["can_honor"]
        self.assertFalse(can_honor["allowed"])
        self.assertIsNotNone(can_honor["reason"])

    def test_post_honor_refused_without_active_persona(self) -> None:
        self.client.force_authenticate(user=self.no_persona_account)
        response = self.client.post(
            reverse("societies:deed-honor", args=[self.deed.pk]),
            {"journal_title": "A Great Deed", "journal_body": "They fought bravely and won."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(LegendHonor.objects.count(), 0)

    def test_can_honor_false_with_reason_when_viewer_lacks_knowledge(self) -> None:
        self._mint_hare(self.honorer_sheet)
        self.client.force_authenticate(user=self.honorer_account)
        response = self.client.get(reverse("societies:deed-detail", args=[self.deed.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        can_honor = response.data["can_honor"]
        self.assertFalse(can_honor["allowed"])
        self.assertIn("do not know", can_honor["reason"].lower())

    def test_can_honor_true_for_knowledgeable_viewer(self) -> None:
        self._mint_hare(self.honorer_sheet)
        self._grant_knowledge()
        self.client.force_authenticate(user=self.honorer_account)
        response = self.client.get(reverse("societies:deed-detail", args=[self.deed.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        can_honor = response.data["can_honor"]
        self.assertTrue(can_honor["allowed"])
        self.assertIsNone(can_honor["reason"])
        self.assertEqual(can_honor["hares_required"], 1)
        self.assertEqual(can_honor["value_added"], 10)

    def test_can_honor_reason_prioritizes_eligibility_over_unconfigured_level(self) -> None:
        """Review finding 1: eligibility beats "not configured", exactly mirroring

        ``honor_deed``'s own check order (world/societies/honors.py:207-229) —
        eligibility (own-deed/knowledge/already-honored) runs before price. A
        viewer who has ALREADY honored this deed AND whose level has no
        calibration row must be told "You have already honored this deed.",
        never sent to ask staff about configuration — that would be true but
        would name the wrong cause, and honor_deed itself never even reaches
        the calibration lookup for someone already ineligible.
        """
        CharacterClassLevelFactory(character=self.honorer_sheet, level=7)
        self.honorer_sheet.invalidate_class_level_cache()
        self.assertFalse(
            LegendLevelCalibration.objects.filter(level=7).exists(),
            "test fixture bug: a level-7 calibration row exists",
        )
        self._grant_knowledge()
        LegendHonorFactory(deed=self.deed, honorer=self.honorer_persona)
        self.client.force_authenticate(user=self.honorer_account)

        response = self.client.get(reverse("societies:deed-detail", args=[self.deed.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        can_honor = response.data["can_honor"]
        self.assertFalse(can_honor["allowed"])
        self.assertIn("already honored", can_honor["reason"].lower())
        self.assertIsNone(can_honor["hares_required"])
        self.assertIsNone(can_honor["value_added"])

    def test_post_honor_creates_legend_honor_and_returns_201(self) -> None:
        self._mint_hare(self.honorer_sheet)
        self._grant_knowledge()
        self.client.force_authenticate(user=self.honorer_account)
        response = self.client.post(
            reverse("societies:deed-honor", args=[self.deed.pk]),
            {"journal_title": "A Great Deed", "journal_body": "They fought bravely and won."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(LegendHonor.objects.count(), 1)
        honor = LegendHonor.objects.get()
        self.assertEqual(honor.deed_id, self.deed.pk)
        self.assertEqual(honor.honorer_id, self.honorer_persona.pk)
        self.assertEqual(response.data["honorer"]["id"], self.honorer_persona.pk)
        self.assertEqual(response.data["honorer"]["name"], self.honorer_persona.name)
        self.assertEqual(response.data["journal"]["title"], "A Great Deed")

    def test_post_honor_twice_returns_400_and_creates_nothing(self) -> None:
        self._mint_hare(self.honorer_sheet)
        self._mint_hare(self.honorer_sheet)
        self._grant_knowledge()
        self.client.force_authenticate(user=self.honorer_account)
        body = {"journal_title": "A Great Deed", "journal_body": "They fought bravely and won."}

        first = self.client.post(
            reverse("societies:deed-honor", args=[self.deed.pk]), body, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)

        second = self.client.post(
            reverse("societies:deed-honor", args=[self.deed.pk]), body, format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already honored", second.data["detail"].lower())
        self.assertEqual(LegendHonor.objects.count(), 1)

    def test_can_honor_false_when_viewers_level_has_no_calibration_row(self) -> None:
        """A brand-new player's level has no authored row (ruling, coordinator).

        ``CharacterSheet.current_level`` is 0 for any character with no class
        assignments — but a real gap can happen at ANY level a level design never
        got around to authoring, so this proves it with a level (7) nobody seeded
        a calibration row for, not level 0. The GET must still 200: an unrelated
        read surface must never 500 because a level's rite price is unauthored.
        """
        CharacterClassLevelFactory(character=self.honorer_sheet, level=7)
        self.honorer_sheet.invalidate_class_level_cache()
        self.assertFalse(
            LegendLevelCalibration.objects.filter(level=7).exists(),
            "test fixture bug: a level-7 calibration row exists",
        )
        self._grant_knowledge()
        self.client.force_authenticate(user=self.honorer_account)

        response = self.client.get(reverse("societies:deed-detail", args=[self.deed.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        can_honor = response.data["can_honor"]
        self.assertFalse(can_honor["allowed"])
        self.assertIsNotNone(can_honor["reason"])
        self.assertIsNone(can_honor["hares_required"])
        self.assertIsNone(can_honor["value_added"])

    def test_post_honor_still_fails_hard_when_calibration_row_missing(self) -> None:
        """The write path keeps the bare ``.get()`` — it must still fail hard, never 200/silently.

        Contrast with the read-path test above: ``can_honor`` degrades gracefully,
        but ``honor_deed``'s own calibration lookup (``world.societies.honors``,
        unchanged by this ruling) is deliberately still unguarded, so a POST against
        an unauthored level must propagate ``LegendLevelCalibration.DoesNotExist`` all
        the way to the API's generic exception handler (``web.api.exceptions.
        custom_exception_handler``, which turns any unhandled exception into a 500 —
        this repo's uniform "fails hard" shape for a server-side bug, distinct from
        the player-safe 400s ``HonorRefused`` maps to) rather than silently doing
        nothing or inventing a price.
        """
        CharacterClassLevelFactory(character=self.honorer_sheet, level=7)
        self.honorer_sheet.invalidate_class_level_cache()
        self._mint_hare(self.honorer_sheet)
        self._grant_knowledge()
        self.client.force_authenticate(user=self.honorer_account)

        response = self.client.post(
            reverse("societies:deed-honor", args=[self.deed.pk]),
            {"journal_title": "A Great Deed", "journal_body": "They fought bravely and won."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(LegendHonor.objects.count(), 0)

    def _assert_no_account_identifiers(self, response) -> None:
        body = json.dumps(response.data)
        self.assertNotIn(self.honorer_account.username, body)
        self.assertNotIn(self.honorer_account.email, body)
        self.assertNotIn(self.honoree_account.username, body)
        self.assertNotIn(self.honoree_account.email, body)

    def test_payload_contains_no_account_identifiers(self) -> None:
        """Covers all three response bodies this endpoint set can return.

        Same account-free serializer (``LegendHonorSerializer`` / persona id+name
        only) backs the GET deed-detail body and both POST honor bodies below — but
        this is the test guarding a privacy property, so it checks every body that
        shape reaches, not just one of them.
        """
        self._mint_hare(self.honorer_sheet)
        self._grant_knowledge()
        self.client.force_authenticate(user=self.honorer_account)
        honor_response = self.client.post(
            reverse("societies:deed-honor", args=[self.deed.pk]),
            {"journal_title": "A Great Deed", "journal_body": "They fought bravely and won."},
            format="json",
        )
        self.assertEqual(honor_response.status_code, status.HTTP_201_CREATED, honor_response.data)
        self._assert_no_account_identifiers(honor_response)

        detail_response = self.client.get(reverse("societies:deed-detail", args=[self.deed.pk]))
        self._assert_no_account_identifiers(detail_response)


@override_settings(SEED_SAMPLE_CONTENT=True)
class EstablishEndpointTests(APITestCase):
    """``POST /api/societies/events/{id}/establish/`` — mint a fresh deed."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rite = ensure_rite_of_honors_ritual()
        cls.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)
        cls.calibration = LegendLevelCalibrationFactory(
            level=0, honor_hares_required=1, honor_value_added=10, deed_title_threshold=100
        )

    def setUp(self) -> None:
        self.client = APIClient()

        self.honorer_account = AccountFactory()
        self.honorer_persona = _active_primary_persona(account=self.honorer_account)
        self.honorer_sheet = self.honorer_persona.character_sheet
        CharacterAuraFactory(character=self.honorer_sheet)
        mint_favor_token(self.academy, self.honorer_sheet, provenance_note="A deed done")

        self.honoree_account = AccountFactory()
        self.honoree_persona = _active_primary_persona(account=self.honoree_account)

        self.scene = SceneFactory()
        # An event that already minted SOMEONE's deed (proving it proved peril) but
        # nothing yet for the honoree — a live deed for the honoree on this same
        # event would trip HonoreeAlreadyAnchoredError.
        self.event = LegendEventFactory(base_value=100, scene=self.scene)
        LegendEntryFactory(persona=PersonaFactory(), event=self.event, base_value=10)
        # Presence: NotPresentToEstablishError otherwise.
        InteractionFactory(persona=self.honorer_persona, scene=self.scene)

    def test_establish_creates_deed_and_honor(self) -> None:
        deeds_before = LegendEntry.objects.count()
        self.client.force_authenticate(user=self.honorer_account)
        response = self.client.post(
            reverse("societies:legend-event-establish", args=[self.event.pk]),
            {
                "honoree_persona": self.honoree_persona.pk,
                "deed_title": "He Held the Door",
                "journal_title": "A Great Deed",
                "journal_body": "They fought bravely and won.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(LegendEntry.objects.count(), deeds_before + 1)
        self.assertTrue(response.data["established_deed"])
        honor = LegendHonor.objects.get(established_deed=True)
        new_deed = LegendEntry.objects.get(pk=honor.deed_id)
        self.assertEqual(new_deed.title, "He Held the Door")
        self.assertEqual(new_deed.persona_id, self.honoree_persona.pk)

        # Same account-free serializer as the deed-detail/honor bodies — the
        # establish POST response is the third body this endpoint set can
        # return, and the privacy test in HonorEndpointsTests only covers the
        # other two.
        body = json.dumps(response.data)
        self.assertNotIn(self.honorer_account.username, body)
        self.assertNotIn(self.honorer_account.email, body)
        self.assertNotIn(self.honoree_account.username, body)
        self.assertNotIn(self.honoree_account.email, body)
