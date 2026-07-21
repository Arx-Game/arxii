"""Tests for magic stage validation (Gift-stage picks, #2426) and finalize linking."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.achievements.constants import AccessChangeSource
from world.character_creation.constants import (
    CG_MODIFIER_CATEGORY,
    SHROUDWATCH_ACADEMY_NAME,
    STARTING_TECHNIQUE_PICKS_TARGET,
    UNBOUND_TRADITION_NAME,
)
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import (
    _finalize_academy_entrance_obligation,
    finalize_magic_data,
)
from world.character_creation.validators import compute_magic_errors
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.fatigue.models import FatiguePool
from world.magic.constants import GlimpseTagAxis
from world.magic.factories import (
    GiftFactory,
    GlimpseTagDistinctionSuggestionFactory,
    GlimpseTagFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import CharacterAnima
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.skills.factories import SkillFactory
from world.societies.constants import ObligationOrigin, ObligationState
from world.societies.factories import OrganizationFactory
from world.societies.models import OrganizationObligation
from world.traits.factories import SkillTraitFactory, StatTraitFactory


class MagicStageValidationTest(TestCase):
    """Test compute_magic_errors — Gift-stage validation (#2426).

    Error branches, in return-first order: tradition -> gift -> techniques ->
    gift resonance -> anima check (stat + skill).
    """

    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory()
        cls.tradition = TraditionFactory()
        cls.gift = GiftFactory(name="Shadow Majesty")

        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.gift)
        cls.pool_techniques = TechniqueFactory.create_batch(2, gift=cls.gift)
        path_grant.starter_techniques.set(cls.pool_techniques)

        tradition_grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        cls.signature_technique = TechniqueFactory(gift=cls.gift)
        tradition_grant.signature_techniques.set([cls.signature_technique])

        # A gift with no TraditionGiftGrant for this tradition — never a valid pick.
        cls.other_gift = GiftFactory(name="Not Granted")

        # A technique belonging to the gift but attached to neither the pool nor
        # the signature set — outside the (path, gift, tradition) availability set.
        cls.unavailable_technique = TechniqueFactory(gift=cls.gift)

        cls.resonance = ResonanceFactory()
        cls.stat_trait = StatTraitFactory(name="strength")
        cls.other_trait = SkillTraitFactory(name="not a stat")
        cls.skill = SkillFactory()
        cls.inactive_skill = SkillFactory(is_active=False)

    def _draft(self, **draft_data_overrides):
        draft_data = {
            "selected_gift_id": self.gift.id,
            "selected_technique_ids": [self.pool_techniques[0].id],
            "selected_gift_resonance_id": self.resonance.id,
            "anima_check_stat_id": self.stat_trait.id,
            "anima_check_skill_id": self.skill.id,
        }
        draft_data.update(draft_data_overrides)
        return CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
            draft_data=draft_data,
        )

    def test_no_tradition_selected_returns_error(self):
        draft = CharacterDraftFactory(selected_tradition=None)
        errors = compute_magic_errors(draft)
        assert errors == ["Select a tradition"]

    def test_no_gift_selected_returns_error(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
            draft_data={},
        )
        errors = compute_magic_errors(draft)
        assert errors == ["Select a gift"]

    def test_gift_not_available_for_tradition_fails(self):
        draft = self._draft(selected_gift_id=self.other_gift.id)
        errors = compute_magic_errors(draft)
        assert errors == ["Select a valid gift for your tradition"]

    def test_no_techniques_selected_returns_error(self):
        draft = self._draft(selected_technique_ids=[])
        errors = compute_magic_errors(draft)
        assert errors == ["Select at least one technique"]

    def test_technique_outside_availability_set_fails(self):
        draft = self._draft(selected_technique_ids=[self.unavailable_technique.id])
        errors = compute_magic_errors(draft)
        assert errors == ["Selected technique is not available"]

    def test_signature_technique_is_available(self):
        """Signature techniques (tradition grant) are pickable, not just pool ones."""
        draft = self._draft(selected_technique_ids=[self.signature_technique.id])
        errors = compute_magic_errors(draft)
        assert errors == []

    def test_too_many_techniques_fails(self):
        """starting_technique_picks defaults to 1 — picking 2 is over budget."""
        draft = self._draft(
            selected_technique_ids=[t.id for t in self.pool_techniques],
        )
        errors = compute_magic_errors(draft)
        assert errors == ["You may select at most 1 techniques"]

    def test_no_gift_resonance_fails(self):
        """Resonance is required — anchors the latent GIFT thread (#1620)."""
        draft = self._draft(selected_gift_resonance_id=None)
        errors = compute_magic_errors(draft)
        assert errors == ["Select a gift resonance"]

    def test_no_anima_check_stat_fails(self):
        draft = self._draft(anima_check_stat_id=None)
        errors = compute_magic_errors(draft)
        assert errors == ["Choose the stat and skill your magic rolls (your Anima Check)"]

    def test_anima_check_stat_wrong_trait_type_fails(self):
        """anima_check_stat_id must reference a Trait with trait_type=STAT."""
        draft = self._draft(anima_check_stat_id=self.other_trait.id)
        errors = compute_magic_errors(draft)
        assert errors == ["Choose the stat and skill your magic rolls (your Anima Check)"]

    def test_no_anima_check_skill_fails(self):
        draft = self._draft(anima_check_skill_id=None)
        errors = compute_magic_errors(draft)
        assert errors == ["Choose the stat and skill your magic rolls (your Anima Check)"]

    def test_inactive_anima_check_skill_fails(self):
        draft = self._draft(anima_check_skill_id=self.inactive_skill.id)
        errors = compute_magic_errors(draft)
        assert errors == ["Choose the stat and skill your magic rolls (your Anima Check)"]

    def test_fully_valid_draft_passes(self):
        draft = self._draft()
        errors = compute_magic_errors(draft)
        assert errors == []


class MagicFinalizationCGSeedingTest(TestCase):
    """finalize_magic_data seeds CharacterAnima and FatiguePool at CG completion (Phase 12)."""

    def _make_draft_and_sheet(self):
        sheet = CharacterSheetFactory()
        # CharacterTradition creation is unconditional (#2426) — a tradition is
        # required even though this test only cares about the Anima/Fatigue seeding.
        draft = CharacterDraftFactory(selected_tradition=TraditionFactory())
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


class AcademyEntranceObligationTest(TestCase):
    """finalize_magic_data's Golden Hare Academy entrance hook (#2428).

    Unbound Prospects (no Tradition sponsor) start OWED to Shroudwatch
    Academy; every other tradition is sponsored and starts SETTLED_BY_SPONSOR.
    Resolved by name — a defensive, logged skip covers an unseeded Academy.
    """

    def _make_draft_and_sheet(self, *, tradition_name: str):
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(selected_tradition=TraditionFactory(name=tradition_name))
        return draft, sheet

    def test_unbound_tradition_creates_owed_obligation(self):
        academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME, tradition=None)
        draft, sheet = self._make_draft_and_sheet(tradition_name=UNBOUND_TRADITION_NAME)

        finalize_magic_data(draft, sheet)

        obligation = OrganizationObligation.objects.get(debtor=sheet, creditor=academy)
        self.assertEqual(obligation.origin, ObligationOrigin.ACADEMY_ENTRANCE)
        self.assertEqual(obligation.state, ObligationState.OWED)
        self.assertIsNone(obligation.settled_at)
        self.assertIsNone(obligation.settled_by_token)

    def test_sponsored_tradition_creates_settled_by_sponsor_obligation(self):
        academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME, tradition=None)
        draft, sheet = self._make_draft_and_sheet(tradition_name="Khati Ancestral Rite")

        finalize_magic_data(draft, sheet)

        obligation = OrganizationObligation.objects.get(debtor=sheet, creditor=academy)
        self.assertEqual(obligation.origin, ObligationOrigin.ACADEMY_ENTRANCE)
        self.assertEqual(obligation.state, ObligationState.SETTLED_BY_SPONSOR)
        self.assertIsNotNone(obligation.settled_at)
        self.assertIsNone(
            obligation.settled_by_token,
            "Sponsor's Hare is lore-recorded, not a minted item at CG time (#2428).",
        )

    def test_no_academy_seeded_skips_without_crash(self):
        draft, sheet = self._make_draft_and_sheet(tradition_name=UNBOUND_TRADITION_NAME)

        with self.assertLogs("world.character_creation.services", level="WARNING") as logs:
            finalize_magic_data(draft, sheet)

        self.assertFalse(OrganizationObligation.objects.exists())
        self.assertTrue(
            any(SHROUDWATCH_ACADEMY_NAME in message for message in logs.output),
            f"Expected a logged skip naming {SHROUDWATCH_ACADEMY_NAME!r}: {logs.output}",
        )

    def test_idempotent_second_call_creates_no_duplicate(self):
        OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME, tradition=None)
        draft = CharacterDraftFactory(
            selected_tradition=TraditionFactory(name=UNBOUND_TRADITION_NAME)
        )
        sheet = CharacterSheetFactory()

        _finalize_academy_entrance_obligation(draft, sheet)
        _finalize_academy_entrance_obligation(draft, sheet)

        self.assertEqual(
            OrganizationObligation.objects.filter(
                debtor=sheet, creditor__name=SHROUDWATCH_ACADEMY_NAME
            ).count(),
            1,
        )


class GiftGrantNotificationTest(TestCase):
    """Gift/technique grant during magic-stage finalization queues an ABILITY
    NarrativeMessage (#1606, updated to the catalog gift/technique contract #2426).
    """

    def _make_draft_and_sheet(self):
        gift = GiftFactory(name="Umbral Sight")
        technique = TechniqueFactory(gift=gift, name="Phantom Step")
        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            selected_tradition=TraditionFactory(),
            draft_data={
                "selected_gift_id": gift.id,
                "selected_technique_ids": [technique.id],
                "selected_gift_resonance_id": resonance.id,
            },
        )
        return draft, sheet, technique

    def test_gift_grant_queues_ability_narrative_message(self):
        """finalize_magic_data with a gift queues an ABILITY message naming the technique."""
        draft, sheet, technique = self._make_draft_and_sheet()
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
            technique.name,
            body,
            f"Expected technique name '{technique.name}' in message body: {body!r}",
        )

    def test_gift_grant_message_has_character_creation_source_label(self):
        """The queued message body references the CHARACTER_CREATION source label."""
        draft, sheet, _technique = self._make_draft_and_sheet()
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

    def test_no_gift_selected_produces_no_ability_message(self):
        """finalize_magic_data without a selected gift produces no ABILITY NarrativeMessage."""
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(selected_tradition=TraditionFactory(), draft_data={})
        finalize_magic_data(draft, sheet)

        deliveries = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=sheet)
        ability_deliveries = [
            d for d in deliveries if d.message.category == NarrativeCategory.ABILITY
        ]
        self.assertFalse(
            ability_deliveries,
            "No ABILITY message should be queued when no gift is selected.",
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

    def test_malformed_draft_id_returns_empty_list(self):
        """Non-numeric draft_id is treated as absent, never a 500 (review finding)."""
        response = self.client.get("/api/character-creation/gifts/", {"draft_id": "abc"})

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

    def test_tradition_selected_but_no_path_returns_empty_list(self):
        draft = CharacterDraftFactory(account=self.account, selected_tradition=self.tradition)

        response = self.client.get("/api/character-creation/gifts/", {"draft_id": draft.id})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_path_selected_but_no_tradition_returns_empty_list(self):
        draft = CharacterDraftFactory(account=self.account, selected_path=self.path)

        response = self.client.get("/api/character-creation/gifts/", {"draft_id": draft.id})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


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

    def test_malformed_draft_id_returns_empty_list(self):
        """Non-numeric draft_id is treated as absent, never a 500 (review finding)."""
        response = self.client.get(
            "/api/character-creation/technique-options/",
            {"draft_id": "abc", "gift_id": self.gift.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_malformed_gift_id_returns_empty_list(self):
        """Non-numeric gift_id is treated as absent, never a 500 (review finding)."""
        draft = self._draft()

        response = self.client.get(
            "/api/character-creation/technique-options/",
            {"draft_id": draft.id, "gift_id": "abc"},
        )

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

        response = self.client.get(
            "/api/character-creation/technique-options/",
            {"draft_id": draft.id, "gift_id": self.gift.id},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class CGGlimpseTagEndpointTest(TestCase):
    """GET /api/character-creation/glimpse-tags/ (#2427)."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_lists_active_tags_ordered_axis_then_sort_order(self):
        tone_b = GlimpseTagFactory(
            axis=GlimpseTagAxis.TONE, slug="tone-b", sort_order=2, name="Tone B"
        )
        tone_a = GlimpseTagFactory(
            axis=GlimpseTagAxis.TONE, slug="tone-a", sort_order=1, name="Tone A"
        )
        consequence_a = GlimpseTagFactory(
            axis=GlimpseTagAxis.CONSEQUENCE, slug="consequence-a", sort_order=1
        )
        GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-inactive", is_active=False)

        response = self.client.get("/api/character-creation/glimpse-tags/")

        assert response.status_code == status.HTTP_200_OK
        slugs = [row["slug"] for row in response.data]
        assert "tone-inactive" not in slugs
        # Meta.ordering = ["axis", "sort_order", "name"] — CONSEQUENCE < TONE alphabetically.
        assert slugs == [consequence_a.slug, tone_a.slug, tone_b.slug]

    def test_embeds_suggested_distinctions(self):
        tag = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-x")
        distinction = DistinctionFactory(name="Fated")
        GlimpseTagDistinctionSuggestionFactory(tag=tag, distinction=distinction)

        response = self.client.get("/api/character-creation/glimpse-tags/")

        assert response.status_code == status.HTTP_200_OK
        row = next(r for r in response.data if r["slug"] == "tone-x")
        assert row["suggested_distinctions"] == [{"id": distinction.id, "name": "Fated"}]

    def test_axis_filter(self):
        GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-only")
        GlimpseTagFactory(axis=GlimpseTagAxis.CONSEQUENCE, slug="consequence-only")

        response = self.client.get(
            "/api/character-creation/glimpse-tags/", {"axis": GlimpseTagAxis.TONE}
        )

        assert response.status_code == status.HTTP_200_OK
        slugs = {row["slug"] for row in response.data}
        assert slugs == {"tone-only"}

    def test_anonymous_request_rejected(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/character-creation/glimpse-tags/")

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_query_count_constant_as_tags_grow(self):
        """Prefetch guard: same query count with 2 tags (+suggestions) as with 6.

        ``GlimpseTag``/``GlimpseTagDistinctionSuggestion`` are SharedMemoryModel
        (idmapper) rows — once an instance is fetched with its prefetch populated,
        re-fetching the *same* identity-mapped row skips the prefetch query
        entirely (a feature, not a bug: see the ``sharedmemory-model`` skill).
        That would make the second capture look artificially cheaper rather than
        reflecting the view's real query shape, so the identity map is flushed
        between captures to keep the comparison apples-to-apples.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from world.magic.models import GlimpseTag, GlimpseTagDistinctionSuggestion

        url = "/api/character-creation/glimpse-tags/"

        # Warmup: the very first authenticated request in a test also creates the
        # session row (extra SELECT/INSERT/UPDATE) — prime it (with an empty
        # catalog) before creating any tags, so neither capture pays that cost.
        self.client.get(url)

        tag_a = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="qc-a")
        tag_b = GlimpseTagFactory(axis=GlimpseTagAxis.CONSEQUENCE, slug="qc-b")
        GlimpseTagDistinctionSuggestionFactory(tag=tag_a, distinction=DistinctionFactory())
        GlimpseTagDistinctionSuggestionFactory(tag=tag_b, distinction=DistinctionFactory())

        with CaptureQueriesContext(connection) as small:
            response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

        for i in range(4):
            tag = GlimpseTagFactory(axis=GlimpseTagAxis.WITNESS, slug=f"qc-extra-{i}")
            GlimpseTagDistinctionSuggestionFactory(tag=tag, distinction=DistinctionFactory())

        GlimpseTag.flush_instance_cache()
        GlimpseTagDistinctionSuggestion.flush_instance_cache()

        with CaptureQueriesContext(connection) as big:
            response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

        assert len(big.captured_queries) == len(small.captured_queries)

    def test_path_filter_excludes_tags_not_on_path(self):
        """Tags with a non-empty paths M2M not containing path_id are excluded."""
        path_a = PathFactory(name="Path of Steel")
        path_b = PathFactory(name="Path of Shadows")
        GlimpseTagFactory(axis=GlimpseTagAxis.TRIGGER, slug="trauma")
        restricted_to_a = GlimpseTagFactory(axis=GlimpseTagAxis.TRIGGER, slug="patron-chose-you")
        restricted_to_a.paths.add(path_a)

        response = self.client.get("/api/character-creation/glimpse-tags/", {"path_id": path_b.id})

        assert response.status_code == status.HTTP_200_OK
        slugs = {row["slug"] for row in response.data}
        assert "trauma" in slugs
        assert "patron-chose-you" not in slugs

    def test_path_filter_includes_tags_on_matching_path(self):
        """Tags restricted to the requested path are included."""
        path_a = PathFactory(name="Path of Steel")
        restricted = GlimpseTagFactory(axis=GlimpseTagAxis.TRIGGER, slug="patron-chose-you")
        restricted.paths.add(path_a)

        response = self.client.get("/api/character-creation/glimpse-tags/", {"path_id": path_a.id})

        assert response.status_code == status.HTTP_200_OK
        slugs = {row["slug"] for row in response.data}
        assert "patron-chose-you" in slugs

    def test_no_path_filter_returns_all_tags(self):
        """Omitting path_id returns all active tags (post-CG editor mode)."""
        path_a = PathFactory(name="Path of Steel")
        restricted = GlimpseTagFactory(axis=GlimpseTagAxis.TRIGGER, slug="patron-chose-you")
        restricted.paths.add(path_a)

        response = self.client.get("/api/character-creation/glimpse-tags/")

        assert response.status_code == status.HTTP_200_OK
        slugs = {row["slug"] for row in response.data}
        assert "patron-chose-you" in slugs
