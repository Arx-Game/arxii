"""API tests for the budget-based technique builder (#537).

Covers:
- POST /api/magic/techniques/price/  — dry-run pricing, no rows created
- POST /api/magic/techniques/author/ — player path (enforced) + staff path (advisory)
- POST /api/magic/techniques/        — base create locked to staff (non-staff → 403)
- Referential validation (bad gift_id / bad style_id → 400)
- Player gift-ownership enforcement
- Staff over-budget authoring returns 201 unbound with advisory breakdown
- Server-resolved policy (non-staff cannot escalate via client-sent context)
- representative_level stamping on authored technique
- §9: invalid payload FK → 400 (not 500), no rows created
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import (
    CharacterGiftFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueStyleFactory,
)
from world.magic.models import CharacterTechnique, Technique
from world.roster.factories import RosterTenureFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure.

    Mirrors the helper in test_api.py — the canonical pattern for wiring
    RosterEntry.for_account() in tests.
    """
    character.account = account
    account.characters.add(character)
    RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
    )


class TechniqueBuilderAPITests(APITestCase):
    """End-to-end API tests for the technique builder endpoints."""

    @classmethod
    def setUpTestData(cls):
        # Player account + character + sheet (linked via RosterTenure)
        cls.account = AccountFactory(username="tech_builder_player")
        cls.character = CharacterFactory(db_key="TechBuilderChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        # Gift owned by the player's character
        cls.gift = GiftFactory(creator=cls.sheet)
        CharacterGiftFactory(character=cls.sheet, gift=cls.gift)

        cls.style = TechniqueStyleFactory()
        cls.effect = EffectTypeFactory()

        # Staff account (no character linkage required)
        cls.staff_account = AccountFactory(username="tech_builder_staff", is_staff=True)
        # Staff gift can be any gift; reuse cls.gift
        cls.staff_gift = GiftFactory()  # unowned by anyone, staff-accessible

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.account)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _payload(self, **override):
        body = {
            "name": "Spark",
            "description": "",
            "gift_id": self.gift.id,
            "style_id": self.style.id,
            "effect_type_id": self.effect.id,
            "action_category": "physical",
            "tier": 1,
            "intensity": 3,
            "control": 2,
            "anima_cost": 2,
            "character_id": self.sheet.pk,
        }
        body.update(override)
        return body

    # ------------------------------------------------------------------
    # price (dry-run)
    # ------------------------------------------------------------------

    def test_price_returns_breakdown_and_creates_no_rows(self):
        url = reverse("magic:technique-price")
        res = self.client.post(url, self._payload(), format="json")
        assert res.status_code == status.HTTP_200_OK, res.data
        assert "within_budget" in res.data
        assert res.data["within_budget"] is True
        assert "lines" in res.data
        assert Technique.objects.count() == 0

    def test_price_over_budget_still_returns_200_with_breakdown(self):
        """price is always advisory: even over-budget returns 200 (not 400)."""
        url = reverse("magic:technique-price")
        res = self.client.post(url, self._payload(intensity=100, control=100), format="json")
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data["within_budget"] is False
        assert Technique.objects.count() == 0

    # ------------------------------------------------------------------
    # author — player path (enforced)
    # ------------------------------------------------------------------

    def test_author_within_budget_creates_technique_and_binds(self):
        url = reverse("magic:technique-author")
        res = self.client.post(url, self._payload(), format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert "breakdown" in res.data
        assert res.data["breakdown"]["within_budget"] is True
        # CharacterTechnique row must exist for the player's sheet
        assert CharacterTechnique.objects.filter(character=self.sheet).count() == 1

    def test_author_over_budget_returns_400_and_no_rows(self):
        url = reverse("magic:technique-author")
        before = Technique.objects.count()
        res = self.client.post(url, self._payload(intensity=100, control=100), format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        assert "breakdown" in res.data
        assert Technique.objects.count() == before  # atomic rollback

    def test_author_stamps_representative_level(self):
        """Authored technique level equals tier's representative_level (default tier 1 → 1)."""
        url = reverse("magic:technique-author")
        res = self.client.post(url, self._payload(tier=1), format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.data
        technique = Technique.objects.get(pk=res.data["id"])
        assert technique.level == 1  # tier 1 representative_level = 1

    # ------------------------------------------------------------------
    # author — staff path (advisory, unbound)
    # ------------------------------------------------------------------

    def test_staff_over_budget_returns_201_unbound_with_advisory_breakdown(self):
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("magic:technique-author")
        payload = {
            "name": "StaffSpell",
            "description": "",
            "gift_id": self.staff_gift.id,
            "style_id": self.style.id,
            "effect_type_id": self.effect.id,
            "action_category": "physical",
            "tier": 1,
            "intensity": 100,
            "control": 100,
            "anima_cost": 0,
        }
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert res.data["breakdown"]["within_budget"] is False  # over budget but advisory
        tech = Technique.objects.get(pk=res.data["id"])
        # Staff technique is unbound — no CharacterTechnique row
        assert not CharacterTechnique.objects.filter(technique=tech).exists()

    # ------------------------------------------------------------------
    # base CRUD — non-staff must be rejected
    # ------------------------------------------------------------------

    def test_base_create_locked_to_staff_returns_403(self):
        url = reverse("magic:technique-list")
        res = self.client.post(url, {"name": "X"}, format="json")
        assert res.status_code == status.HTTP_403_FORBIDDEN, res.data

    def test_base_create_staff_allowed(self):
        """Staff can still use the base POST if they want raw create."""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("magic:technique-list")
        payload = {
            "name": "RawStaffTech",
            "gift": self.staff_gift.id,
            "style": self.style.id,
            "effect_type": self.effect.id,
            "level": 1,
            "intensity": 1,
            "control": 0,
            "anima_cost": 0,
            "action_category": "physical",
            "description": "",
        }
        res = self.client.post(url, payload, format="json")
        # Staff should get through (may be 201 or 400 depending on field validation,
        # but NOT 403)
        assert res.status_code != status.HTTP_403_FORBIDDEN, res.data

    # ------------------------------------------------------------------
    # Referential validation — clean 400, not 500
    # ------------------------------------------------------------------

    def test_bad_gift_id_returns_400(self):
        url = reverse("magic:technique-author")
        res = self.client.post(url, self._payload(gift_id=999999), format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data

    def test_bad_style_id_returns_400(self):
        url = reverse("magic:technique-author")
        res = self.client.post(url, self._payload(style_id=999999), format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data

    def test_player_unowned_gift_returns_400(self):
        """A gift the player doesn't own should return 400 (not 500)."""
        other_gift = GiftFactory()  # not granted to cls.sheet
        url = reverse("magic:technique-author")
        res = self.client.post(url, self._payload(gift_id=other_gift.id), format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data

    # ------------------------------------------------------------------
    # Server-resolved policy — client cannot escalate
    # ------------------------------------------------------------------

    def test_non_staff_cannot_escalate_via_context_field(self):
        """A non-staff user passing a context-escalation field in the payload
        should still be treated as PlayerPolicy (enforced)."""
        url = reverse("magic:technique-author")
        # Attempt to "escalate" by including a policy field — the server ignores this
        payload = self._payload(intensity=100, control=100)
        payload["policy"] = "staff"  # ignored by server
        res = self.client.post(url, payload, format="json")
        # Must be 400 (player over-budget) not 201 (staff advisory)
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        assert Technique.objects.count() == 0

    # ------------------------------------------------------------------
    # price endpoint — staff path
    # ------------------------------------------------------------------

    def test_price_staff_path_returns_200(self):
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("magic:technique-price")
        payload = {
            "name": "StaffPriceCheck",
            "description": "",
            "gift_id": self.staff_gift.id,
            "style_id": self.style.id,
            "effect_type_id": self.effect.id,
            "action_category": "physical",
            "tier": 1,
            "intensity": 100,
            "control": 100,
            "anima_cost": 0,
        }
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK, res.data
        assert "within_budget" in res.data
        assert res.data["within_budget"] is False  # over budget
        assert Technique.objects.count() == 0  # dry run, no rows


# =============================================================================
# §9 payload FK validation tests
# =============================================================================


class TechniqueBuilderPayloadFKTests(APITestCase):
    """§9: invalid payload FK id → 400, no rows (not an IntegrityError/500)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="pk_fk_player")
        cls.character = CharacterFactory(db_key="PKFKChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.gift = GiftFactory(creator=cls.sheet)
        CharacterGiftFactory(character=cls.sheet, gift=cls.gift)

        cls.style = TechniqueStyleFactory()
        cls.effect = EffectTypeFactory()

        cls.capability = CapabilityTypeFactory()

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.account)

    def _base_payload(self, **override):
        body = {
            "name": "Test",
            "description": "",
            "gift_id": self.gift.id,
            "style_id": self.style.id,
            "effect_type_id": self.effect.id,
            "action_category": "physical",
            "tier": 1,
            "intensity": 3,
            "control": 2,
            "anima_cost": 2,
            "character_id": self.sheet.pk,
        }
        body.update(override)
        return body

    def test_invalid_capability_id_returns_400_no_rows(self):
        """A capability_grants entry with a nonexistent capability_id must yield 400,
        not an IntegrityError/500, and must not create any Technique rows."""
        url = reverse("magic:technique-author")
        before = Technique.objects.count()
        payload = self._base_payload(
            capability_grants=[
                {"capability_id": 999999, "base_value": 0, "intensity_multiplier": 0.0}
            ]
        )
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        assert Technique.objects.count() == before

    def test_valid_capability_id_succeeds(self):
        """A capability_grants entry with a real capability_id must create the technique."""
        url = reverse("magic:technique-author")
        payload = self._base_payload(
            capability_grants=[
                {
                    "capability_id": self.capability.id,
                    "base_value": 1,
                    "intensity_multiplier": 0.0,
                }
            ]
        )
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.data
