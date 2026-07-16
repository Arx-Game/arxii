"""Tests for magic stage validation with cantrip selection."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from actions.constants import ActionCategory
from evennia_extensions.factories import AccountFactory
from world.achievements.constants import AccessChangeSource
from world.character_creation.constants import CG_MODIFIER_CATEGORY, STARTING_TECHNIQUE_PICKS_TARGET
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import finalize_magic_data
from world.character_creation.validators import compute_magic_errors
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.fatigue.models import FatiguePool
from world.magic.factories import (
    CantripFactory,
    FacetFactory,
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import CharacterAnima, Technique
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery


class MagicFinalizationActionCategoryTest(TestCase):
    """finalize_magic_data derives the technique's action_category from the Path."""

    def test_technique_action_category_derives_from_path(self):
        path = PathFactory(action_category=ActionCategory.MENTAL)
        cantrip = CantripFactory()
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            selected_path=path,
            draft_data={"selected_cantrip_id": cantrip.id},
        )
        finalize_magic_data(draft, sheet)
        technique = Technique.objects.get(source_cantrip=cantrip, creator=sheet)
        self.assertEqual(technique.action_category, ActionCategory.MENTAL)


class MagicStageValidationTest(TestCase):
    """Test compute_magic_errors with cantrip-based validation."""

    @classmethod
    def setUpTestData(cls):
        cls.innate_cantrip = CantripFactory(
            name="Danger Sense",
            requires_facet=False,
        )
        cls.manifested_cantrip = CantripFactory(
            name="Elemental Strike",
            requires_facet=True,
            facet_prompt="Choose your element",
        )
        fire = FacetFactory(name="Fire")
        ice = FacetFactory(name="Ice")
        cls.manifested_cantrip.allowed_facets.add(fire, ice)
        cls.fire = fire
        cls.unrelated_facet = FacetFactory(name="Wolf")
        cls.resonance = ResonanceFactory()

    def test_no_cantrip_selected_returns_error(self):
        draft = CharacterDraftFactory()
        errors = compute_magic_errors(draft)
        assert "Select a cantrip" in errors

    def test_innate_cantrip_selected_passes(self):
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.innate_cantrip.id,
                "selected_gift_resonance_id": self.resonance.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert errors == []

    def test_manifested_cantrip_without_facet_fails(self):
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": self.manifested_cantrip.id},
        )
        errors = compute_magic_errors(draft)
        assert any(
            "element" in e.lower() or "facet" in e.lower() or "type" in e.lower() for e in errors
        )

    def test_manifested_cantrip_with_valid_facet_passes(self):
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.manifested_cantrip.id,
                "selected_facet_id": self.fire.id,
                "selected_gift_resonance_id": self.resonance.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert errors == []

    def test_manifested_cantrip_with_invalid_facet_fails(self):
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.manifested_cantrip.id,
                "selected_facet_id": self.unrelated_facet.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert len(errors) > 0

    def test_inactive_cantrip_fails(self):
        inactive = CantripFactory(is_active=False)
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": inactive.id},
        )
        errors = compute_magic_errors(draft)
        assert len(errors) > 0

    def test_cantrip_without_resonance_fails(self):
        """Resonance is required — anchors the latent GIFT thread (#1620)."""
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": self.innate_cantrip.id},
        )
        errors = compute_magic_errors(draft)
        assert "Select a gift resonance" in errors

    def test_cantrip_with_resonance_passes(self):
        """Valid cantrip + facet + resonance produces no errors."""
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.innate_cantrip.id,
                "selected_gift_resonance_id": self.resonance.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert errors == []


class MagicFinalizationCGSeedingTest(TestCase):
    """finalize_magic_data seeds CharacterAnima and FatiguePool at CG completion (Phase 12)."""

    def _make_draft_and_sheet(self):
        cantrip = CantripFactory()
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": cantrip.id},
        )
        return draft, sheet

    def test_finalize_seeds_character_anima_row(self):
        """finalize_magic_data creates a CharacterAnima row for the new character."""
        draft, sheet = self._make_draft_and_sheet()
        self.assertFalse(
            CharacterAnima.objects.filter(character=sheet.character).exists(),
            "CharacterAnima must not exist before finalize",
        )
        finalize_magic_data(draft, sheet)
        self.assertTrue(
            CharacterAnima.objects.filter(character=sheet.character).exists(),
            "CharacterAnima should be seeded by finalize_magic_data",
        )

    def test_finalize_seeds_fatigue_pool_row(self):
        """finalize_magic_data creates a FatiguePool row for the new character sheet."""
        draft, sheet = self._make_draft_and_sheet()
        self.assertFalse(
            FatiguePool.objects.filter(character_sheet=sheet).exists(),
            "FatiguePool must not exist before finalize",
        )
        finalize_magic_data(draft, sheet)
        self.assertTrue(
            FatiguePool.objects.filter(character_sheet=sheet).exists(),
            "FatiguePool should be seeded by finalize_magic_data",
        )

    def test_finalize_character_anima_defaults(self):
        """Seeded CharacterAnima has sensible defaults (current=10, maximum=10)."""
        draft, sheet = self._make_draft_and_sheet()
        finalize_magic_data(draft, sheet)
        anima = CharacterAnima.objects.get(character=sheet.character)
        self.assertEqual(anima.current, 10)
        self.assertEqual(anima.maximum, 10)

    def test_seeding_is_idempotent_via_get_or_create(self):
        """CharacterAnima and FatiguePool use get_or_create — second call is a no-op."""
        from world.fatigue.services import get_or_create_fatigue_pool

        draft, sheet = self._make_draft_and_sheet()
        finalize_magic_data(draft, sheet)
        # Calling the seeding helpers again must not raise or create duplicates.
        CharacterAnima.objects.get_or_create(
            character=sheet.character,
            defaults={"current": 10, "maximum": 10},
        )
        get_or_create_fatigue_pool(sheet)
        self.assertEqual(CharacterAnima.objects.filter(character=sheet.character).count(), 1)
        self.assertEqual(FatiguePool.objects.filter(character_sheet=sheet).count(), 1)


class CantripGrantNotificationTest(TestCase):
    """Cantrip grant during magic-stage finalization queues an ABILITY NarrativeMessage (#1606)."""

    def _make_draft_and_sheet(self):
        cantrip = CantripFactory(name="Phantom Step")
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": cantrip.id},
        )
        return draft, sheet, cantrip

    def test_cantrip_grant_queues_ability_narrative_message(self):
        """finalize_magic_data with a cantrip queues an ABILITY message naming the technique."""
        draft, sheet, cantrip = self._make_draft_and_sheet()
        finalize_magic_data(draft, sheet)

        deliveries = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=sheet)
        ability_deliveries = [
            d for d in deliveries if d.message.category == NarrativeCategory.ABILITY
        ]
        self.assertTrue(
            ability_deliveries,
            "Expected at least one ABILITY NarrativeMessage queued for the new character.",
        )
        body = ability_deliveries[0].message.body
        self.assertIn(
            cantrip.name,
            body,
            f"Expected technique name '{cantrip.name}' in message body: {body!r}",
        )

    def test_cantrip_grant_message_has_character_creation_source_label(self):
        """The queued message body references the CHARACTER_CREATION source label."""
        draft, sheet, _cantrip = self._make_draft_and_sheet()
        finalize_magic_data(draft, sheet)

        deliveries = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=sheet)
        ability_deliveries = [
            d for d in deliveries if d.message.category == NarrativeCategory.ABILITY
        ]
        self.assertTrue(ability_deliveries, "Expected an ABILITY NarrativeMessage.")
        source_label = AccessChangeSource.CHARACTER_CREATION.label
        body = ability_deliveries[0].message.body
        self.assertIn(
            source_label,
            body,
            f"Expected source label '{source_label}' in message body: {body!r}",
        )

    def test_no_cantrip_produces_no_ability_message(self):
        """finalize_magic_data without a cantrip produces no ABILITY NarrativeMessage."""
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(draft_data={})
        finalize_magic_data(draft, sheet)

        deliveries = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=sheet)
        ability_deliveries = [
            d for d in deliveries if d.message.category == NarrativeCategory.ABILITY
        ]
        self.assertFalse(
            ability_deliveries,
            "No ABILITY message should be queued when no cantrip is selected.",
        )


class StartingTechniquePicksTest(TestCase):
    """CharacterDraft.starting_technique_picks — base 1 + distinction bonus (#2426)."""

    def test_no_distinctions_defaults_to_one(self):
        draft = CharacterDraftFactory()
        self.assertEqual(draft.starting_technique_picks, 1)

    def test_distinction_bonus_adds_to_base(self):
        category = ModifierCategoryFactory(name=CG_MODIFIER_CATEGORY)
        target = ModifierTargetFactory(name=STARTING_TECHNIQUE_PICKS_TARGET, category=category)
        distinction = DistinctionFactory()
        DistinctionEffectFactory(distinction=distinction, target=target, value_per_rank=1)

        draft = CharacterDraftFactory(
            draft_data={"distinctions": [{"distinction_id": distinction.id, "rank": 2}]}
        )
        self.assertEqual(draft.starting_technique_picks, 3)


class CGGiftOptionEndpointTest(TestCase):
    """GET /api/character-creation/gifts/?draft_id=<id> (#2426)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.path = PathFactory()
        cls.tradition = TraditionFactory()

        cls.available_gift = GiftFactory(name="Shadow Majesty")
        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.available_gift)
        path_grant.starter_techniques.set(TechniqueFactory.create_batch(2, gift=cls.available_gift))
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.available_gift)

        # Authored tradition grant, but neither pool nor signature techniques attached.
        cls.empty_gift = GiftFactory(name="Nothing Yet")
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.empty_gift)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_empty_before_tradition_and_path_selected(self):
        """No tradition/path on the draft yet -> empty list, not every Gift."""
        draft = CharacterDraftFactory(account=self.account)

        response = self.client.get("/api/character-creation/gifts/", {"draft_id": draft.id})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_lists_available_gifts_excludes_empty_ones(self):
        draft = CharacterDraftFactory(
            account=self.account,
            selected_path=self.path,
            selected_tradition=self.tradition,
        )

        response = self.client.get("/api/character-creation/gifts/", {"draft_id": draft.id})

        assert response.status_code == status.HTTP_200_OK
        gift_ids = [row["id"] for row in response.data]
        assert self.available_gift.id in gift_ids
        assert self.empty_gift.id not in gift_ids

    def test_missing_draft_id_returns_empty_list(self):
        response = self.client.get("/api/character-creation/gifts/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_other_accounts_draft_is_not_accessible(self):
        """draft_id scoped to the requesting account (get_object_or_404 account=)."""
        other_account = AccountFactory()
        draft = CharacterDraftFactory(
            account=other_account,
            selected_path=self.path,
            selected_tradition=self.tradition,
        )

        response = self.client.get("/api/character-creation/gifts/", {"draft_id": draft.id})

        assert response.status_code == status.HTTP_404_NOT_FOUND


class CGTechniqueOptionEndpointTest(TestCase):
    """GET /api/character-creation/technique-options/?draft_id=<id>&gift_id=<id> (#2426)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.path = PathFactory()
        cls.tradition = TraditionFactory()
        cls.gift = GiftFactory()

        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.gift)
        cls.pool_techniques = TechniqueFactory.create_batch(2, gift=cls.gift)
        path_grant.starter_techniques.set(cls.pool_techniques)

        tradition_grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        cls.signature_technique = TechniqueFactory(gift=cls.gift)
        tradition_grant.signature_techniques.set([cls.signature_technique])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _draft(self, **kwargs):
        defaults = {
            "account": self.account,
            "selected_path": self.path,
            "selected_tradition": self.tradition,
        }
        defaults.update(kwargs)
        return CharacterDraftFactory(**defaults)

    def test_pool_and_signature_techniques_listed_with_is_signature_flag(self):
        draft = self._draft()

        response = self.client.get(
            "/api/character-creation/technique-options/",
            {"draft_id": draft.id, "gift_id": self.gift.id},
        )

        assert response.status_code == status.HTTP_200_OK
        by_id = {row["id"]: row for row in response.data}
        assert set(by_id) == {
            *[t.id for t in self.pool_techniques],
            self.signature_technique.id,
        }
        assert by_id[self.signature_technique.id]["is_signature"] is True
        for pool_technique in self.pool_techniques:
            assert by_id[pool_technique.id]["is_signature"] is False

    def test_category_resolved_from_effect_type(self):
        draft = self._draft()
        technique = self.pool_techniques[0]

        response = self.client.get(
            "/api/character-creation/technique-options/",
            {"draft_id": draft.id, "gift_id": self.gift.id},
        )

        row = next(row for row in response.data if row["id"] == technique.id)
        assert row["category"] == technique.effect_type.category

    def test_empty_before_tradition_and_path_selected(self):
        draft = CharacterDraftFactory(account=self.account)

        response = self.client.get(
            "/api/character-creation/technique-options/",
            {"draft_id": draft.id, "gift_id": self.gift.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_missing_gift_id_returns_empty_list(self):
        draft = self._draft()

        response = self.client.get(
            "/api/character-creation/technique-options/", {"draft_id": draft.id}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
