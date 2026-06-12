"""API tests for the Audere Majora (Crossing) offer REST surface (#543).

Covers:
    1. List returns own offer with all fields (vision_text, boundary_level,
       target_stage_display, risk_text verbatim, eligible_paths, advisory_text)
    2. List excludes another account's offers
    3. intended_path_id: eligible → pk; ineligible → None; absent → None
    4. Respond accept happy path — 200; body matches result serializer;
       offer deleted; level advanced
    5. Respond accept missing path_id — 400; blank declaration_text — 400
    6. Respond decline — 200 accepted=false
    7. Respond on another account's offer — 400 (ownership check fails)
    8. Unknown offer_id — 400 with "No pending Crossing offer found."
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.audere_majora import PendingAudereMajoraOffer
from world.magic.exceptions import AudereMajoraOfferNotFoundError
from world.magic.factories import IntensityTierFactory, wire_audere_power_multipliers
from world.magic.tests.majora_fixtures import build_crossing_world
from world.progression.models import PathIntent
from world.roster.factories import RosterEntryFactory, RosterTenureFactory

_PENDING_URL = "/api/magic/audere-majora/pending/"
_RESPOND_URL = "/api/magic/audere-majora/respond/"

_RISK_TEXT = "This is permanent. The crossing cannot be undone — and survival is not promised."


def _wire_tenure_to_sheet(tenure, sheet) -> None:
    """Replace the tenure's roster_entry with one pointing at the given sheet.

    We swap out the auto-created roster_entry so the ViewSet's account-scoped
    queryset can resolve sheet → roster_entry → tenures → account.
    """
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure.roster_entry = entry
    tenure.save(update_fields=["roster_entry"])


def _build_owned_crossing_fixture(  # noqa: PLR0913 — fixture requires all named rows
    boundary_level: int,
    suffix: str,
    tenure,
    *,
    intensity_tier=None,
    soulfray_template=None,
    soulfray_stage=None,
):
    """Build a fully-eligible Crossing character wired to an account via ``tenure``.

    Accepts optional shared authored rows (intensity_tier, soulfray_template,
    soulfray_stage) to avoid UNIQUE constraint collisions when building multiple
    fixtures in a single setUp. Creates them fresh when not provided.

    Returns (character, sheet, threshold, prospect_path, puissant_path, offer).
    """
    character, sheet, threshold, prospect_path, puissant_path, offer = build_crossing_world(
        boundary_level,
        f"_api{suffix}",
        intensity_tier=intensity_tier,
        soulfray_template=soulfray_template,
        soulfray_stage=soulfray_stage,
        fired_intensity=boundary_level * 2 + 15,  # > intensity_tier.threshold
        vision_text=f"[VISION PLACEHOLDER {boundary_level}{suffix}]",
        manifestation_text=f"[MANIFESTATION {boundary_level}{suffix}]",
        intensity_tier_threshold=boundary_level * 2 + 10,
    )
    _wire_tenure_to_sheet(tenure, sheet)
    return character, sheet, threshold, prospect_path, puissant_path, offer


class PendingAudereMajoraOfferListTests(APITestCase):
    """GET /api/magic/audere-majora/pending/ — account-scoped inbox."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        self.my_tenure = RosterTenureFactory()
        self.other_tenure = RosterTenureFactory()
        self.my_account = self.my_tenure.player_data.account

        # Shared authored rows to avoid UNIQUE constraint collision
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME, has_progression=True
        )
        ConditionStageFactory(condition=soulfray_template, stage_order=1, name="Fraying_list")
        ConditionStageFactory(condition=soulfray_template, stage_order=2, name="Tearing_list")
        soulfray_stage = ConditionStageFactory(
            condition=soulfray_template, stage_order=3, name="Ripping_list"
        )
        intensity_tier = IntensityTierFactory(name="Major_list", threshold=10)

        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.my_offer,
        ) = _build_owned_crossing_fixture(
            5,
            "_list_own",
            self.my_tenure,
            intensity_tier=intensity_tier,
            soulfray_template=soulfray_template,
            soulfray_stage=soulfray_stage,
        )

        (
            self.other_character,
            self.other_sheet,
            _,
            _,
            _,
            self.other_offer,
        ) = _build_owned_crossing_fixture(
            6,
            "_list_other",
            self.other_tenure,
            intensity_tier=intensity_tier,
            soulfray_template=soulfray_template,
            soulfray_stage=soulfray_stage,
        )

    def test_list_returns_own_offer(self) -> None:
        """My offer appears in the list."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.my_offer.pk, result_ids)

    def test_list_excludes_other_accounts_offers(self) -> None:
        """Another account's offer is not included in the list."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.other_offer.pk, result_ids)

    def test_list_fields_vision_text(self) -> None:
        """vision_text equals the threshold's stored placeholder text."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.my_offer.pk]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vision_text"], self.threshold.vision_text)

    def test_list_fields_boundary_level(self) -> None:
        """boundary_level matches the threshold's boundary_level."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.my_offer.pk]
        self.assertEqual(rows[0]["boundary_level"], self.threshold.boundary_level)

    def test_list_fields_target_stage_display(self) -> None:
        """target_stage_display is a non-empty string."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.my_offer.pk]
        self.assertIsInstance(rows[0]["target_stage_display"], str)
        self.assertTrue(rows[0]["target_stage_display"])

    def test_list_fields_risk_text_verbatim(self) -> None:
        """risk_text matches the approved fixed copy exactly."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.my_offer.pk]
        self.assertEqual(rows[0]["risk_text"], _RISK_TEXT)

    def test_list_fields_eligible_paths_present(self) -> None:
        """eligible_paths contains the eligible puissant path with expected keys."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.my_offer.pk]
        paths = rows[0]["eligible_paths"]
        self.assertGreater(len(paths), 0)
        path_ids = {p["id"] for p in paths}
        self.assertIn(self.puissant_path.pk, path_ids)
        first = next(p for p in paths if p["id"] == self.puissant_path.pk)
        for key in ("id", "name", "stage", "stage_display", "description"):
            self.assertIn(key, first)

    def test_list_fields_advisory_text_present(self) -> None:
        """advisory_text field is present (empty string is acceptable)."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.my_offer.pk]
        self.assertIn("advisory_text", rows[0])

    def test_list_unauthenticated_rejected(self) -> None:
        """Unauthenticated GET returns 401 or 403."""
        response = self.client.get(_PENDING_URL)
        self.assertIn(response.status_code, (401, 403))

    def test_retrieve_foreign_offer_404(self) -> None:
        """Detail retrieval of another account's offer is a 404 (queryset-scoped)."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(f"{_PENDING_URL}{self.other_offer.pk}/")
        self.assertEqual(response.status_code, 404, response.content)


class PendingAudereMajoraIntendedPathTests(APITestCase):
    """intended_path_id: eligible → pk; ineligible → None; absent → None."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        self.my_tenure = RosterTenureFactory()
        self.my_account = self.my_tenure.player_data.account

        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_owned_crossing_fixture(7, "_intent", self.my_tenure)

    def test_intended_path_id_eligible(self) -> None:
        """When intent points to an eligible path, intended_path_id returns its pk."""
        PathIntent.objects.create(
            character_sheet=self.sheet,
            intended_path=self.puissant_path,
        )

        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        rows = [r for r in response.data["results"] if r["id"] == self.offer.pk]
        self.assertEqual(rows[0]["intended_path_id"], self.puissant_path.pk)

    def test_intended_path_id_ineligible(self) -> None:
        """When intent points to a path not in eligible_paths, intended_path_id is None."""
        ineligible = PathFactory(name="Ineligible_intent_path", stage=PathStage.PUISSANT)
        PathIntent.objects.create(
            character_sheet=self.sheet,
            intended_path=ineligible,
        )

        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.offer.pk]
        self.assertIsNone(rows[0]["intended_path_id"])

    def test_intended_path_id_no_intent(self) -> None:
        """When no PathIntent exists, intended_path_id is None."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        rows = [r for r in response.data["results"] if r["id"] == self.offer.pk]
        self.assertIsNone(rows[0]["intended_path_id"])


class AudereMajoraRespondViewTests(APITestCase):
    """POST /api/magic/audere-majora/respond/ — accept/decline a pending Crossing offer."""

    def setUp(self) -> None:
        self.my_tenure = RosterTenureFactory()
        self.other_tenure = RosterTenureFactory()
        self.my_account = self.my_tenure.player_data.account

    def _build_my_offer(self, boundary_level: int, suffix: str):
        """Build + wire a fully-eligible Crossing character to self.my_tenure."""
        wire_audere_power_multipliers()
        return _build_owned_crossing_fixture(boundary_level, suffix, self.my_tenure)

    def test_respond_accept_happy_path(self) -> None:
        """Accepting returns 200 with accepted=true, levels, chosen_path_name; offer deleted."""
        _character, sheet, threshold, _prospect, puissant_path, offer = self._build_my_offer(
            15, "_accept_happy"
        )

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {
                "offer_id": offer.pk,
                "accept": True,
                "path_id": puissant_path.pk,
                "declaration_text": "I step beyond the threshold and claim my becoming.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["accepted"])
        self.assertEqual(response.data["level_before"], threshold.boundary_level)
        self.assertEqual(response.data["level_after"], threshold.boundary_level + 1)
        self.assertEqual(response.data["chosen_path_name"], puissant_path.name)
        # Offer is deleted
        self.assertFalse(PendingAudereMajoraOffer.objects.filter(pk=offer.pk).exists())
        # Level advanced on the CharacterClassLevel row
        sheet.invalidate_class_level_cache()
        self.assertEqual(sheet.current_level, threshold.boundary_level + 1)

    def test_respond_accept_missing_path_id_400(self) -> None:
        """Accept without path_id returns 400."""
        _character, _sheet, _threshold, _prospect, _puissant_path, offer = self._build_my_offer(
            16, "_no_path"
        )

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {
                "offer_id": offer.pk,
                "accept": True,
                "declaration_text": "I step beyond.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_respond_accept_blank_declaration_400(self) -> None:
        """Accept with blank declaration_text returns 400."""
        _character, _sheet, _threshold, _prospect, puissant_path, offer = self._build_my_offer(
            17, "_blank_decl"
        )

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {
                "offer_id": offer.pk,
                "accept": True,
                "path_id": puissant_path.pk,
                "declaration_text": "   ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_respond_decline_returns_accepted_false(self) -> None:
        """Declining returns 200 with accepted=false; offer deleted."""
        _character, _sheet, _threshold, _prospect, _puissant, offer = self._build_my_offer(
            18, "_decline"
        )

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "accept": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["accepted"])
        self.assertFalse(PendingAudereMajoraOffer.objects.filter(pk=offer.pk).exists())

    def test_respond_foreign_offer_400(self) -> None:
        """Responding to another account's offer returns 400; row survives."""
        wire_audere_power_multipliers()
        _character, _sheet, _threshold, _prospect, puissant_path, offer = (
            _build_owned_crossing_fixture(19, "_foreign", self.other_tenure)
        )

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {
                "offer_id": offer.pk,
                "accept": True,
                "path_id": puissant_path.pk,
                "declaration_text": "I step beyond.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        # Offer row survives the ownership rejection
        self.assertTrue(PendingAudereMajoraOffer.objects.filter(pk=offer.pk).exists())

    def test_respond_unknown_offer_id_400(self) -> None:
        """An unknown offer_id returns 400 with 'No pending Crossing offer found.'."""
        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": 999999, "accept": False},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(
            AudereMajoraOfferNotFoundError.user_message,
            str(response.data),
        )
