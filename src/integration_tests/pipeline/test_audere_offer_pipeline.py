"""End-to-end pipeline test for the Audere offer surface (#873).

User story:
    As a player whose character is mid-encounter with a frayed soul, casting a
    high-intensity technique opens the Audere gate. I see the offer (with a
    live corruption advisory) in my web inbox, accept it for an intensity and
    anima surge, and when the encounter ends every Audere bonus is reverted.

Walks the full done-when loop through the real seams:

    1. ``use_technique`` (real orchestrator, stub resolve_fn) fires the gate
       and persists a ``PendingAudereOffer`` row.
    2. ``GET /api/magic/audere/pending/`` as the owning account lists the
       offer with the stage-3 corruption advisory ("character loss") inline.
    3. ``POST /api/magic/audere/respond/`` accept=True applies the
       engagement-intensity and anima-pool bonuses, installs the Audere
       ConditionInstance, and deletes the offer row.
    4. ``cleanup_completed_encounter`` reverts both bonuses, strips the
       Audere condition, and leaves no pending offers behind.

Unit coverage for each seam lives in world/magic/tests/test_audere_offer_surface.py,
world/magic/tests/test_audere_api.py, and world/combat/tests/test_audere_cleanup.py;
this module proves the wiring between them.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from evennia.objects.models import ObjectDB
from rest_framework.test import APITestCase

from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import cleanup_completed_encounter
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.magic.audere import AUDERE_CONDITION_NAME, PendingAudereOffer
from world.magic.factories import (
    CharacterAnimaFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.tests.test_audere_offer_surface import build_audere_gate_fixture
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.roster.factories import RosterTenureFactory

_PENDING_URL = "/api/magic/audere/pending/"
_RESPOND_URL = "/api/magic/audere/respond/"


class TestAudereOfferPipeline(APITestCase):
    """Cast → pending offer → API inbox → accept → encounter cleanup."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gate = build_audere_gate_fixture(tier_suffix="pipeline")

        # Account-owned character: RosterTenure gives the API auth path
        # (account → player_data → tenure → roster_entry → character_sheet).
        cls.tenure = RosterTenureFactory()
        cls.account = cls.tenure.player_data.account
        cls.sheet = cls.tenure.roster_entry.character_sheet
        cls.character = cls.sheet.character

        cls.anima = CharacterAnimaFactory(character=cls.character, current=50, maximum=50)
        obj_ct = ContentType.objects.get_for_model(ObjectDB)
        cls.engagement = CharacterEngagement.objects.create(
            character=cls.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=obj_ct,
            source_id=cls.character.pk,
        )
        ConditionInstanceFactory(
            target=cls.character,
            condition=cls.gate.soulfray_template,
            current_stage=cls.gate.soulfray_stage,
        )

        # intensity=20 resolves to the major tier (threshold 15) → passes the
        # gate; control=30 keeps the cast clean even after the tier's -5.
        cls.technique = TechniqueFactory(intensity=20, control=30, anima_cost=3)

        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter, character_sheet=cls.sheet
        )

        # Stage-3 corruption on an unrelated resonance so the advisory fires.
        resonance = ResonanceFactory(name="Pipeline Doom")
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
            target=cls.character,
            condition=template,
            current_stage=stages[2],  # stage_order=3
        )

    def test_cast_offer_accept_cleanup_loop(self) -> None:
        """The full Audere loop: cast fires the offer; web accept applies the
        surge; encounter cleanup reverts everything."""
        # ------------------------------------------------------------------
        # Step 1 — qualifying cast creates the pending offer
        # ------------------------------------------------------------------
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=lambda *, power, ledger: None,  # noqa: ARG005
        )
        self.assertTrue(result.confirmed)
        self.assertTrue(PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists())
        offer = PendingAudereOffer.objects.get(character_sheet=self.sheet)
        self.assertEqual(offer.fired_intensity, 20)

        # ------------------------------------------------------------------
        # Step 2 — the owning account sees the offer with the live advisory
        # ------------------------------------------------------------------
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_PENDING_URL)
        self.assertEqual(response.status_code, 200, response.content)
        rows = [row for row in response.data["results"] if row["id"] == offer.pk]
        self.assertEqual(len(rows), 1)
        self.assertIn("character loss", rows[0]["advisory_text"])

        # ------------------------------------------------------------------
        # Step 3 — accepting applies the surge and consumes the offer
        # ------------------------------------------------------------------
        pre_accept_modifier = self.engagement.intensity_modifier
        pre_accept_maximum = self.anima.maximum
        response = self.client.post(
            _RESPOND_URL,
            {"offer_id": offer.pk, "accept": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["accepted"])

        self.engagement.refresh_from_db()
        self.anima.refresh_from_db()
        self.assertEqual(
            self.engagement.intensity_modifier,
            pre_accept_modifier + self.gate.threshold.intensity_bonus,
        )
        self.assertEqual(
            self.anima.maximum,
            pre_accept_maximum + self.gate.threshold.anima_pool_bonus,
        )
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.character, condition__name=AUDERE_CONDITION_NAME
            ).exists()
        )
        self.assertFalse(PendingAudereOffer.objects.filter(pk=offer.pk).exists())

        # ------------------------------------------------------------------
        # Step 4 — encounter cleanup reverts every Audere bonus
        # ------------------------------------------------------------------
        cleanup_completed_encounter(self.encounter)

        self.engagement.refresh_from_db()
        self.anima.refresh_from_db()
        self.assertEqual(self.engagement.intensity_modifier, pre_accept_modifier)
        self.assertEqual(self.anima.maximum, pre_accept_maximum)
        self.assertIsNone(self.anima.pre_audere_maximum)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.character, condition__name=AUDERE_CONDITION_NAME
            ).exists()
        )
        self.assertFalse(PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists())
