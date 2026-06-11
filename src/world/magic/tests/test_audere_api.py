"""API tests for the Audere offer REST surface (#873): inbox + respond.

Covers:
    1. List scoped to the authenticated account's own offers
    2. advisory_text computed live and verbatim at corruption stage 3+
    3. Detail retrieval of a foreign account's offer is a 404 (queryset-scoped)
    4. Respond accept — 200 with bonuses applied, offer row deleted
    5. Respond decline — 200 with no bonuses, offer row deleted, state unchanged
    6. Respond rejects an offer belonging to another account (400, row survives)
    7. Respond on a stale offer — 400 with stale user_message, row deleted
    8. Unauthenticated requests rejected
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from evennia.objects.models import ObjectDB
from rest_framework.test import APITestCase

from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import (
    PendingAudereOffer,
    corruption_advisory_for_character,
    maybe_create_audere_offer,
)
from world.magic.exceptions import AudereOfferStaleError
from world.magic.factories import CharacterAnimaFactory, ResonanceFactory
from world.magic.tests.audere_test_helpers import (
    AudereGateFixture,
    build_audere_gate_fixture,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.roster.factories import RosterTenureFactory

_PENDING_URL = "/api/magic/audere/pending/"
_RESPOND_URL = "/api/magic/audere/respond/"


def _open_gate_for_tenure(tenure, gate: AudereGateFixture) -> PendingAudereOffer:
    """Wire the full Audere eligibility gate for a tenure's character and fire an offer.

    Seeds CharacterAnima, a CHALLENGE CharacterEngagement, and a Soulfray
    ConditionInstance at the gate's minimum stage, then creates the pending
    offer via maybe_create_audere_offer (the real service entry point).
    """
    sheet = tenure.roster_entry.character_sheet
    character = sheet.character
    CharacterAnimaFactory(character=character, current=10, maximum=50)
    obj_ct = ContentType.objects.get_for_model(ObjectDB)
    CharacterEngagement.objects.create(
        character=character,
        engagement_type=EngagementType.CHALLENGE,
        source_content_type=obj_ct,
        source_id=character.pk,
    )
    ConditionInstanceFactory(
        target=character,
        condition=gate.soulfray_template,
        current_stage=gate.soulfray_stage,
    )
    offer = maybe_create_audere_offer(character, runtime_intensity=20)
    assert offer is not None, "Audere gate fixture failed to open the eligibility gate"
    return offer


def _give_stage3_corruption(character: ObjectDB, resonance_name: str) -> None:
    """Attach a corruption_resonance condition at stage 3 to the character.

    Mirrors the fixture approach in test_audere_corruption_advisory.
    """
    resonance = ResonanceFactory(name=resonance_name)
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name})",
        has_progression=True,
        corruption_resonance=resonance,
    )
    stages = [
        ConditionStageFactory(
            condition=template,
            stage_order=i,
            severity_threshold=threshold,
        )
        for i, threshold in enumerate([50, 200, 500, 1000, 1500], start=1)
    ]
    ConditionInstanceFactory(
        target=character,
        condition=template,
        current_stage=stages[2],  # stage_order=3
    )


class PendingAudereOfferListTests(APITestCase):
    """GET /api/magic/audere/pending/ — account-scoped inbox."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gate = build_audere_gate_fixture(tier_suffix="api_list")
        cls.my_tenure = RosterTenureFactory()
        cls.other_tenure = RosterTenureFactory()
        cls.my_account = cls.my_tenure.player_data.account

    def test_list_scoped_to_own_offers(self) -> None:
        """My offer appears in the list; another account's offer does not."""
        my_offer = _open_gate_for_tenure(self.my_tenure, self.gate)
        other_offer = _open_gate_for_tenure(self.other_tenure, self.gate)

        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(my_offer.pk, result_ids)
        self.assertNotIn(other_offer.pk, result_ids)

    def test_advisory_text_present_and_verbatim_at_stage_3(self) -> None:
        """Stage-3+ corruption surfaces the live character-loss advisory verbatim."""
        my_offer = _open_gate_for_tenure(self.my_tenure, self.gate)
        character = my_offer.character_sheet.character
        _give_stage3_corruption(character, "Wild Hunt")

        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(_PENDING_URL)

        self.assertEqual(response.status_code, 200, response.content)
        rows = [row for row in response.data["results"] if row["id"] == my_offer.pk]
        self.assertEqual(len(rows), 1)
        advisory = rows[0]["advisory_text"]
        self.assertIn("character loss", advisory)
        self.assertEqual(advisory, corruption_advisory_for_character(character))

    def test_retrieve_foreign_offer_404(self) -> None:
        """Detail retrieval of another account's offer is a 404 (queryset-scoped)."""
        foreign_offer = _open_gate_for_tenure(self.other_tenure, self.gate)

        self.client.force_authenticate(user=self.my_account)
        response = self.client.get(f"{_PENDING_URL}{foreign_offer.pk}/")

        self.assertEqual(response.status_code, 404, response.content)

    def test_list_unauthenticated_rejected(self) -> None:
        """Unauthenticated GET returns 401 or 403."""
        response = self.client.get(_PENDING_URL)
        self.assertIn(response.status_code, (401, 403))


class AudereRespondViewTests(APITestCase):
    """POST /api/magic/audere/respond/ — accept/decline a pending offer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gate = build_audere_gate_fixture(tier_suffix="api_respond")
        cls.my_tenure = RosterTenureFactory()
        cls.other_tenure = RosterTenureFactory()
        cls.my_account = cls.my_tenure.player_data.account

    def test_respond_accept_returns_result(self) -> None:
        """Accepting returns the applied bonuses and deletes the offer row."""
        offer = _open_gate_for_tenure(self.my_tenure, self.gate)

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "accept": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["accepted"])
        self.assertEqual(
            response.data["intensity_bonus_applied"],
            self.gate.threshold.intensity_bonus,
        )
        self.assertEqual(
            response.data["anima_pool_expanded_by"],
            self.gate.threshold.anima_pool_bonus,
        )
        self.assertFalse(PendingAudereOffer.objects.filter(pk=offer.pk).exists())

    def test_respond_decline_returns_result(self) -> None:
        """Declining returns accepted=False with no bonuses and deletes the offer row."""
        offer = _open_gate_for_tenure(self.my_tenure, self.gate)
        character = offer.character_sheet.character
        engagement = CharacterEngagement.objects.get(character=character)
        pre_decline_modifier = engagement.intensity_modifier

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "accept": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["accepted"])
        self.assertEqual(response.data["intensity_bonus_applied"], 0)
        self.assertFalse(PendingAudereOffer.objects.filter(pk=offer.pk).exists())
        engagement.refresh_from_db()
        self.assertEqual(engagement.intensity_modifier, pre_decline_modifier)

    def test_respond_rejects_foreign_offer(self) -> None:
        """An offer belonging to another account returns 400; the row survives."""
        foreign_offer = _open_gate_for_tenure(self.other_tenure, self.gate)

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": foreign_offer.pk, "accept": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(PendingAudereOffer.objects.filter(pk=foreign_offer.pk).exists())

    def test_respond_stale_offer_400(self) -> None:
        """A stale offer (engagement gone) returns 400 with the stale message; row deleted."""
        offer = _open_gate_for_tenure(self.my_tenure, self.gate)
        character = offer.character_sheet.character
        CharacterEngagement.objects.filter(character=character).delete()

        self.client.force_authenticate(user=self.my_account)
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "accept": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(AudereOfferStaleError.user_message, str(response.data))
        self.assertFalse(PendingAudereOffer.objects.filter(pk=offer.pk).exists())

    def test_respond_unauthenticated_401(self) -> None:
        """Unauthenticated POST returns 401 or 403."""
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": 1, "accept": True},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))
