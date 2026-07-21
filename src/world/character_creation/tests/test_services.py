"""
Tests for character creation services.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia.accounts.models import AccountDB

from world.character_creation.models import Beginnings, CharacterDraft, StartingArea
from world.character_creation.services import DraftIncompleteError, finalize_character
from world.character_sheets.models import CharacterSheet, Gender
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.forms.models import Build, HeightBand
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.realms.models import Realm
from world.roster.models import Roster
from world.skills.factories import SkillFactory
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.models import CharacterTraitValue, Trait, TraitType

# Shared stats dict used by all finalization tests (12 stats, 1-5 scale, sum=24)
DEFAULT_STATS = {
    "strength": 2,
    "agility": 2,
    "stamina": 2,
    "charm": 2,
    "presence": 2,
    "composure": 2,
    "intellect": 2,
    "wits": 2,
    "stability": 2,
    "luck": 2,
    "perception": 2,
    "willpower": 2,
}


class FinalizationTestMixin:
    """Shared setup and helpers for character finalization test classes."""

    @staticmethod
    def _flush_common_caches() -> None:
        """Flush SharedMemoryModel caches to prevent test pollution."""
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

    @staticmethod
    def _setup_finalization_base(
        target: object, *, prefix: str, height_min: int, height_max: int
    ) -> None:
        """Create common CG prerequisites on target (cls or self).

        Sets: realm, area, species, gender, tarot_card, beginnings,
        height_band, build, path, technique_style, effect_type, resonance, tradition.
        """
        slug = prefix.lower().replace(" ", "_")

        target.realm = Realm.objects.create(name=f"{prefix} Realm", description="Test")
        target.area = StartingArea.objects.create(
            name=f"{prefix} Area",
            description="Test",
            realm=target.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        target.species = Species.objects.create(name=f"{prefix} Species", description="Test")
        target.gender, _ = Gender.objects.get_or_create(
            key=f"{slug}_gender", defaults={"display_name": f"{prefix} Gender"}
        )
        target.tarot_card = TarotCard.objects.create(
            name=f"{prefix} Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Fatui",
        )
        target.beginnings = Beginnings.objects.create(
            name=f"{prefix} Beginnings",
            description="Test",
            starting_area=target.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        target.beginnings.allowed_species.add(target.species)
        target.height_band = HeightBand.objects.create(
            name=f"{slug}_band",
            display_name=f"{prefix} Band",
            min_inches=height_min,
            max_inches=height_max,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        target.build = Build.objects.create(
            name=f"{slug}_build",
            display_name=f"{prefix} Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )
        for stat_name in DEFAULT_STATS:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={"trait_type": TraitType.STAT, "description": stat_name},
            )
        Roster.objects.get_or_create(name="Available Characters")
        target.path = PathFactory(name=f"{prefix} Path", stage=PathStage.PROSPECT, minimum_level=1)
        target.technique_style = TechniqueStyleFactory()
        target.effect_type = EffectTypeFactory()
        target.resonance = ResonanceFactory()
        target.tradition = TraditionFactory()

        # Gift-stage validator fixtures (#2426): a gift available for (tradition, path)
        # with a pool technique, plus a Skill for the anima check.
        target.gift = GiftFactory(name=f"{prefix} Gift")
        path_grant = PathGiftGrantFactory(path=target.path, gift=target.gift)
        target.technique = TechniqueFactory(
            gift=target.gift, style=target.technique_style, effect_type=target.effect_type
        )
        path_grant.starter_techniques.set([target.technique])
        TraditionGiftGrantFactory(tradition=target.tradition, gift=target.gift)
        target.skill = SkillFactory()
        target.stat_trait = Trait.objects.get(name="strength")

    def _create_complete_magic(self, draft: CharacterDraft) -> None:
        """Create complete magic data for a draft (Gift-stage validators, #2426).

        Populates the keys ``compute_magic_errors`` requires so ``draft.can_submit()``
        (the finalize gate) passes.
        """
        draft.draft_data["selected_gift_id"] = self.gift.id
        draft.draft_data["selected_technique_ids"] = [self.technique.id]
        draft.draft_data["selected_gift_resonance_id"] = self.resonance.id
        draft.draft_data["anima_check_stat_id"] = self.stat_trait.id
        draft.draft_data["anima_check_skill_id"] = self.skill.id
        draft.save(update_fields=["draft_data"])

    def _create_base_draft(
        self,
        *,
        first_name: str = "Test",
        height_inches: int | None = None,
        **extra_draft_data: object,
    ) -> CharacterDraft:
        """Create a complete draft for finalization testing.

        Override draft_data fields via extra_draft_data kwargs (e.g., stats=..., quote=...).
        """
        if height_inches is None:
            height_inches = (self.height_band.min_inches + self.height_band.max_inches) // 2

        base_data = {
            "first_name": first_name,
            "description": "A test character",
            "stats": DEFAULT_STATS,
            "lineage_is_orphan": True,
            "tarot_card_name": self.tarot_card.name,
            "tarot_reversed": False,
            "traits_complete": True,
        }
        base_data.update(extra_draft_data)

        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            selected_tradition=self.tradition,
            age=25,
            height_band=self.height_band,
            height_inches=height_inches,
            build=self.build,
            draft_data=base_data,
        )
        self._create_complete_magic(draft)
        return draft


class CharacterFinalizationTests(FinalizationTestMixin, TestCase):
    """Test character finalization with stats."""

    def setUp(self):
        """Set up test data."""
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="testuser")
        self._setup_finalization_base(self, prefix="Service Test", height_min=700, height_max=800)
        # Store stat Trait objects by name for value assertions
        self.stats = {
            t.name: t
            for t in Trait.objects.filter(name__in=DEFAULT_STATS, trait_type=TraitType.STAT)
        }

    def _create_complete_draft(self, stats=None, first_name="Test"):
        """Thin wrapper around _create_base_draft for backward compat."""
        return self._create_base_draft(first_name=first_name, stats=stats or DEFAULT_STATS)

    def test_finalize_creates_character_trait_values(self):
        """Test that finalization creates CharacterTraitValue records."""
        draft = self._create_complete_draft(stats=DEFAULT_STATS)

        character = finalize_character(draft, add_to_roster=True)

        # Verify character was created (tarot surname derived from latin_name "Stultus")
        assert character is not None
        assert character.db_key == "Test Fatui"

        # Verify trait values were created (12 stats)
        trait_values = CharacterTraitValue.objects.filter(character=character)
        assert trait_values.count() == 12

        # Verify specific values directly from database (1-5 scale)
        strength_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["strength"]
        )
        assert strength_value.value == 2

        agility_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["agility"]
        )
        assert agility_value.value == 2

        willpower_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["willpower"]
        )
        assert willpower_value.value == 2

    def test_staff_add_to_roster_stamps_staff_provenance(self):
        """add_to_roster (staff direct-add) records STAFF provenance + the actor (#1506)."""
        from world.roster.models.choices import CreationProvenance

        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        character = finalize_character(draft, add_to_roster=True, created_by_account=self.account)
        entry = character.sheet_data.roster_entry
        assert entry.creation_provenance == CreationProvenance.STAFF
        assert entry.created_by_account == self.account

    def test_player_finalize_stamps_player_provenance(self):
        """The normal self-creation path records PLAYER provenance (an OC) (#1506)."""
        from world.roster.models.choices import CreationProvenance

        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        character = finalize_character(draft)  # add_to_roster=False → Pending roster
        entry = character.sheet_data.roster_entry
        assert entry.creation_provenance == CreationProvenance.PLAYER
        assert entry.created_by_account == draft.account

    def test_finalize_bulk_creates_trait_values(self):
        """Test that finalization uses bulk operations (no N+1)."""
        draft = self._create_complete_draft(
            stats=DEFAULT_STATS,
            first_name="Bulk Test",
        )

        # Count queries during finalization
        with CaptureQueriesContext(connection) as queries:
            finalize_character(draft, add_to_roster=True)

        # Check that we're not doing 8 individual creates
        # Should be: 1 fetch traits + 1 bulk_create
        # (Plus some queries for character/sheet creation)
        # This is a rough check - the key is we're NOT doing 16 queries
        # (8 trait lookups + 8 creates)
        create_queries = [
            q for q in queries if "INSERT" in q["sql"] and "traits_charactertraitvalue" in q["sql"]
        ]

        # Should be 1 bulk insert, not 8 individual inserts
        assert len(create_queries) == 1, f"Expected 1 bulk insert, got {len(create_queries)}"

    def test_finalize_rejects_incomplete_draft(self):
        """Test that finalization properly rejects incomplete drafts."""
        # Create a draft without stats (incomplete attributes stage)
        # Include appearance data to isolate the attributes stage test
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            age=25,
            height_band=self.height_band,
            height_inches=750,
            build=self.build,
            draft_data={
                "first_name": "Incomplete",
                "lineage_is_orphan": True,  # Complete heritage/lineage
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": False,
                "path_skills_complete": True,
                "traits_complete": True,
                "magic_complete": True,
                # No stats field - attributes stage incomplete
            },
        )

        # Should raise DraftIncompleteError
        with self.assertRaises(DraftIncompleteError) as cm:
            finalize_character(draft, add_to_roster=True)

        assert "Attributes" in str(cm.exception)

    def test_finalize_creates_character_sheet(self):
        """Test that finalization creates CharacterSheet with stats."""
        draft = self._create_complete_draft(
            stats=DEFAULT_STATS,
            first_name="Sheet Test",
        )

        character = finalize_character(draft, add_to_roster=True)

        # Verify character sheet exists
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet is not None

        # Verify stats were created with correct values (1-5 scale)
        strength_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["strength"]
        )
        assert strength_value.value == 2

        willpower_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["willpower"]
        )
        assert willpower_value.value == 2

    def test_finalize_origin_story_from_slots(self) -> None:
        """Finalize assembles Profile.background from origin slots (#2478)."""
        from world.character_creation.models import (
            CharacterOriginSlot,
            OriginTemplate,
            OriginTemplateSlot,
        )

        template = OriginTemplate.objects.create(
            beginning=self.beginnings,
            name="Escape",
            frame_narrative="Your story begins with escape from Salvation.",
        )
        slot = OriginTemplateSlot.objects.create(
            template=template, name="Who helped?", prompt="Who aided your flight?"
        )

        draft = self._create_complete_draft(first_name="Origin Test")
        draft.draft_data["origin_slots"] = {str(slot.id): "Mira cut the lock."}
        draft.save(update_fields=["draft_data"])

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        assert "escape from Salvation" in sheet.background
        assert "Mira cut the lock" in sheet.background
        assert CharacterOriginSlot.objects.filter(sheet=sheet).count() == 1

    def test_finalize_legacy_background_still_works(self) -> None:
        """A draft with legacy draft_data['background'] and no origin slots
        still writes background verbatim (backward compat)."""
        draft = self._create_base_draft(
            first_name="Legacy BG",
            background="A plain free-text background.",
        )
        draft.draft_data.pop("origin_slots", None)
        draft.save(update_fields=["draft_data"])

        character = finalize_character(draft, add_to_roster=True)
        assert character.sheet_data.background == "A plain free-text background."

    def test_finalize_converts_unspent_cg_points_to_xp(self):
        """Test that unspent CG points are converted to locked XP."""
        from world.progression.models import CharacterXP, CharacterXPTransaction

        stats = DEFAULT_STATS
        # Set beginnings cost so 10 CG points are spent
        self.beginnings.cg_point_cost = 10
        self.beginnings.save(update_fields=["cg_point_cost"])

        draft = self._create_complete_draft(stats)

        character = finalize_character(draft, add_to_roster=True)

        # Remaining = 100 - 10 = 90, XP = 90 * 2 = 180
        xp = CharacterXP.objects.get(
            character=character,
            transferable=False,
        )
        assert xp.total_earned == 180
        assert xp.current_available == 180

        txn = CharacterXPTransaction.objects.get(character=character)
        assert txn.amount == 180
        assert txn.reason == "cg_conversion"
        assert txn.transferable is False

    def test_finalize_no_xp_when_all_points_spent(self):
        """Test no XP created when CG points fully spent."""
        from world.character_creation.models import CGPointBudget
        from world.progression.models import CharacterXP

        stats = DEFAULT_STATS
        budget = CGPointBudget.get_active_budget()
        # Spend all points via beginnings cost
        self.beginnings.cg_point_cost = budget
        self.beginnings.save(update_fields=["cg_point_cost"])

        draft = self._create_complete_draft(stats)

        character = finalize_character(draft, add_to_roster=True)

        assert not CharacterXP.objects.filter(
            character=character,
        ).exists()

    def test_finalize_populates_physical_stats(self):
        """Test that finalization populates height, build, and weight on CharacterSheet."""
        from world.forms.models import Build, HeightBand

        # Create height band and build for physical stats directly to avoid factory issues
        # Use unique height range outside all default bands (default bands end at 600)
        height_band = HeightBand.objects.create(
            name="finalize_test_band",
            display_name="Finalize Test Band",
            min_inches=700,
            max_inches=800,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        build = Build.objects.create(
            name="finalize_test_build",
            display_name="Finalize Test Build",
            weight_factor=Decimal("1.0"),  # Simple factor for easy verification
            is_cg_selectable=True,
        )

        # Create a complete draft with physical stats
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            selected_tradition=self.tradition,
            age=25,
            height_band=height_band,
            height_inches=750,  # Use height within unique band (700-800)
            build=build,
            draft_data={
                "first_name": "Physical",
                "description": "A test character with physical stats",
                "stats": DEFAULT_STATS,
                "lineage_is_orphan": True,
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": False,
                "traits_complete": True,
            },
        )
        # Add required magic data
        self._create_complete_magic(draft)

        character = finalize_character(draft, add_to_roster=True)

        # Verify character sheet has physical stats populated
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.true_height_inches == 750
        assert sheet.build == build
        # Weight calculated as height_inches * weight_factor = 750 * 1.0 = 750
        assert sheet.weight_pounds == 750

    def test_finalize_sets_heritage_from_beginnings(self):
        """Heritage should come from the Beginnings model, not be hardcoded."""
        from world.character_sheets.models import Heritage

        sleeper_heritage = Heritage.objects.create(
            name="Sleeper",
            description="Awakened from magical slumber.",
            is_special=True,
            family_known=False,
        )
        self.beginnings.heritage = sleeper_heritage
        self.beginnings.save()

        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.heritage == sleeper_heritage

    def test_finalize_defaults_to_normal_heritage_when_beginnings_has_none(self):
        """When Beginnings has no heritage FK, fall back to 'Normal'."""
        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.heritage is not None
        assert sheet.heritage.name == "Normal"

    def test_finalize_creates_true_form_from_form_traits(self):
        """Form traits from draft_data should be saved as a true form."""
        from world.forms.models import CharacterForm, FormType

        hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        black_option = FormTraitOptionFactory(trait=hair_trait, name="black", display_name="Black")
        eye_trait = FormTraitFactory(name="eye_color", display_name="Eye Color")
        blue_option = FormTraitOptionFactory(trait=eye_trait, name="blue", display_name="Blue")

        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        draft.draft_data["form_traits"] = {
            "hair_color": black_option.id,
            "eye_color": blue_option.id,
        }
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        true_form = CharacterForm.objects.get(character=character, form_type=FormType.TRUE)
        values = {v.trait.name: v.option.name for v in true_form.values.all()}
        assert values == {"hair_color": "black", "eye_color": "blue"}

    def test_finalize_skips_form_traits_when_empty(self):
        """No true form created when form_traits is empty or missing."""
        from world.forms.models import CharacterForm

        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        character = finalize_character(draft, add_to_roster=True)
        assert not CharacterForm.objects.filter(character=character).exists()

    def test_finalize_skips_invalid_form_trait_names(self):
        """Invalid trait names in form_traits are silently skipped."""
        from world.forms.models import CharacterForm, FormType

        hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        black_option = FormTraitOptionFactory(trait=hair_trait, name="black", display_name="Black")

        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        draft.draft_data["form_traits"] = {
            "hair_color": black_option.id,
            "nonexistent_trait": 999,
        }
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        true_form = CharacterForm.objects.get(character=character, form_type=FormType.TRUE)
        values = list(true_form.values.all())
        assert len(values) == 1
        assert values[0].trait.name == "hair_color"

    def test_finalize_skips_mismatched_trait_option_pairs(self):
        """An option belonging to a different trait should be silently skipped."""
        from world.forms.models import CharacterForm, FormType

        FormTraitFactory(name="hair_color", display_name="Hair Color")
        eye_trait = FormTraitFactory(name="eye_color", display_name="Eye Color")
        blue_option = FormTraitOptionFactory(trait=eye_trait, name="blue", display_name="Blue")

        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        # hair_color mapped to blue (eye_color option) — mismatched
        # eye_color mapped to blue (correct)
        draft.draft_data["form_traits"] = {
            "hair_color": blue_option.id,
            "eye_color": blue_option.id,
        }
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        true_form = CharacterForm.objects.get(character=character, form_type=FormType.TRUE)
        values = {v.trait.name: v.option.name for v in true_form.values.all()}
        # hair_color should be skipped (blue belongs to eye_color, not hair_color)
        assert values == {"eye_color": "blue"}

    def test_finalize_saves_quote_from_draft_data(self):
        """Quote from draft_data should be saved to CharacterSheet."""
        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        draft.draft_data["quote"] = "Steel remembers what flesh forgets."
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.quote == "Steel remembers what flesh forgets."

    def test_finalize_saves_concept_from_draft_data(self):
        """Concept from draft_data should be saved to CharacterSheet."""
        draft = self._create_complete_draft(stats=DEFAULT_STATS)
        draft.draft_data["concept"] = "Ruthless pragmatist"
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.concept == "Ruthless pragmatist"


class FinalizeCharacterSkillsTests(FinalizationTestMixin, TestCase):
    """Tests for skill creation during character finalization."""

    @classmethod
    def setUpTestData(cls):
        from world.skills.factories import SkillFactory, SpecializationFactory
        from world.skills.models import CharacterSkillValue, CharacterSpecializationValue

        CharacterSkillValue.flush_instance_cache()
        CharacterSpecializationValue.flush_instance_cache()
        cls._setup_finalization_base(cls, prefix="Skill Test", height_min=900, height_max=1000)
        cls.melee_skill = SkillFactory(trait__name="Melee Combat")
        cls.defense_skill = SkillFactory(trait__name="Defense")
        cls.swords_spec = SpecializationFactory(name="Swords", parent_skill=cls.melee_skill)

    def setUp(self):
        from world.skills.models import CharacterSkillValue, CharacterSpecializationValue

        self._flush_common_caches()
        CharacterSkillValue.flush_instance_cache()
        CharacterSpecializationValue.flush_instance_cache()
        self.account = AccountDB.objects.create(username=f"skilltest_{id(self)}")

    def _create_complete_draft(self):
        return self._create_base_draft(first_name="SkillTest", skills={}, specializations={})

    def test_finalize_creates_skill_values(self):
        """Finalization should create CharacterSkillValue records."""
        from world.skills.models import CharacterSkillValue

        draft = self._create_complete_draft()
        draft.draft_data["skills"] = {str(self.melee_skill.pk): 30}
        draft.draft_data["specializations"] = {}
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        skill_value = CharacterSkillValue.objects.get(
            character=character,
            skill=self.melee_skill,
        )
        assert skill_value.value == 30
        assert skill_value.development_points == 0
        assert skill_value.rust_points == 0

    def test_finalize_creates_specialization_values(self):
        """Finalization should create CharacterSpecializationValue records."""
        from world.skills.models import CharacterSpecializationValue

        draft = self._create_complete_draft()
        draft.draft_data["skills"] = {str(self.melee_skill.pk): 30}
        draft.draft_data["specializations"] = {str(self.swords_spec.pk): 20}
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        spec_value = CharacterSpecializationValue.objects.get(
            character=character,
            specialization=self.swords_spec,
        )
        assert spec_value.value == 20
        assert spec_value.development_points == 0

    def test_finalize_skips_zero_value_skills(self):
        """Skills with value 0 should not create records."""
        from world.skills.models import CharacterSkillValue

        draft = self._create_complete_draft()
        draft.draft_data["skills"] = {str(self.melee_skill.pk): 0}
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        assert not CharacterSkillValue.objects.filter(
            character=character,
            skill=self.melee_skill,
        ).exists()


class FinalizeCharacterPathHistoryTests(FinalizationTestMixin, TestCase):
    """Tests for path history creation during character finalization."""

    @classmethod
    def setUpTestData(cls):
        cls._setup_finalization_base(
            cls, prefix="Path History Test", height_min=1100, height_max=1200
        )

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"pathhistorytest_{id(self)}")

    def _create_complete_draft(self):
        return self._create_base_draft(first_name="PathHistoryTest", skills={}, specializations={})

    def test_creates_path_history_on_finalize(self):
        """finalize_character creates CharacterPathHistory record."""
        from world.progression.models import CharacterPathHistory

        draft = self._create_complete_draft()

        character = finalize_character(draft, add_to_roster=True)

        history = CharacterPathHistory.objects.filter(character=character).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.path, self.path)


class FinalizeCharacterGoalsTests(FinalizationTestMixin, TestCase):
    """Tests for goal creation during character finalization."""

    @classmethod
    def setUpTestData(cls):
        from world.mechanics.models import ModifierCategory, ModifierTarget

        cls.goal_cat, _ = ModifierCategory.objects.get_or_create(name="goal")
        cls.standing, _ = ModifierTarget.objects.get_or_create(
            name="Standing", category=cls.goal_cat
        )
        cls.drives, _ = ModifierTarget.objects.get_or_create(name="Drives", category=cls.goal_cat)
        cls._setup_finalization_base(cls, prefix="Goals Test", height_min=1300, height_max=1400)

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"goalstest_{id(self)}")

    def _create_complete_draft(self):
        return self._create_base_draft(first_name="GoalsTest", skills={}, specializations={})

    def test_creates_goals_from_draft_data(self):
        """Goals in draft_data are created as CharacterGoal records."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()

        # Add goals to draft_data (using domain_id and notes as stored by serializer)
        draft.draft_data["goals"] = [
            {"domain_id": self.standing.id, "notes": "Become a knight", "points": 15},
            {"domain_id": self.drives.id, "notes": "Avenge my mentor", "points": 10},
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        assert goals.count() == 2

        standing_goal = goals.get(domain=self.standing)
        assert standing_goal.points == 15
        assert standing_goal.notes == "Become a knight"

        drives_goal = goals.get(domain=self.drives)
        assert drives_goal.points == 10
        assert drives_goal.notes == "Avenge my mentor"

    def test_no_goals_created_when_draft_has_none(self):
        """No goals created if draft_data has no goals."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()
        draft.draft_data.pop("goals", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        assert goals.count() == 0

    def test_skips_invalid_goal_domain_ids(self):
        """Invalid goal domain_ids are silently skipped (already validated by serializer)."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()

        # Add a goal with an invalid domain_id (nonexistent PK)
        draft.draft_data["goals"] = [
            {"domain_id": self.standing.id, "notes": "Valid goal", "points": 15},
            {"domain_id": 99999, "notes": "Invalid goal", "points": 10},
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        # Only the valid goal should be created
        assert goals.count() == 1
        assert goals.first().domain == self.standing

    def test_skips_zero_point_goals(self):
        """Goals with 0 points are skipped."""
        from world.goals.models import CharacterGoal

        draft = self._create_complete_draft()

        draft.draft_data["goals"] = [
            {"domain_id": self.standing.id, "notes": "Valid goal", "points": 15},
            {"domain_id": self.drives.id, "notes": "Zero point goal", "points": 0},
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        goals = CharacterGoal.objects.filter(character=character)
        assert goals.count() == 1
        assert goals.first().domain == self.standing


class FinalizeCharacterDistinctionsTests(FinalizationTestMixin, TestCase):
    """Tests for distinction creation during character finalization."""

    @classmethod
    def setUpTestData(cls):
        from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
        from world.distinctions.models import DistinctionEffect
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        cls.stat_category = ModifierCategoryFactory(name="distinction_test_stat")
        cls.strength_modifier = ModifierTargetFactory(
            name="distinction_test_strength", category=cls.stat_category
        )
        cls.dist_category = DistinctionCategoryFactory(name="Distinction Test Category")
        cls.simple_distinction = DistinctionFactory(
            name="Simple Distinction",
            category=cls.dist_category,
            cost_per_rank=5,
            max_rank=1,
            is_active=True,
        )
        cls.ranked_distinction = DistinctionFactory(
            name="Ranked Distinction",
            category=cls.dist_category,
            cost_per_rank=10,
            max_rank=3,
            is_active=True,
        )
        DistinctionEffect.objects.create(
            distinction=cls.ranked_distinction,
            target=cls.strength_modifier,
            value_per_rank=5,
        )
        cls._setup_finalization_base(
            cls, prefix="Distinction Test", height_min=1500, height_max=1600
        )

    def setUp(self):
        from world.mechanics.models import CharacterModifier

        self._flush_common_caches()
        CharacterModifier.flush_instance_cache()
        self.account = AccountDB.objects.create(username=f"distinctiontest_{id(self)}")

    def _create_complete_draft(self):
        return self._create_base_draft(first_name="DistinctionTest", skills={}, specializations={})

    def test_creates_distinctions_from_draft_data(self):
        """Distinctions in draft_data are created as CharacterDistinction records."""
        from world.distinctions.models import CharacterDistinction

        draft = self._create_complete_draft()
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": self.simple_distinction.id,
                "distinction_name": self.simple_distinction.name,
                "distinction_slug": self.simple_distinction.slug,
                "category_slug": self.dist_category.slug,
                "rank": 1,
                "cost": 5,
                "notes": "",
            },
            {
                "distinction_id": self.ranked_distinction.id,
                "distinction_name": self.ranked_distinction.name,
                "distinction_slug": self.ranked_distinction.slug,
                "category_slug": self.dist_category.slug,
                "rank": 2,
                "cost": 20,
                "notes": "Test note",
            },
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        char_distinctions = CharacterDistinction.objects.filter(character=character.sheet_data)
        assert char_distinctions.count() == 2

        simple = char_distinctions.get(distinction=self.simple_distinction)
        assert simple.rank == 1
        assert simple.origin == "character_creation"

        ranked = char_distinctions.get(distinction=self.ranked_distinction)
        assert ranked.rank == 2
        assert ranked.notes == "Test note"

    def test_secret_by_default_distinction_is_relocated_into_a_secret(self):
        """A ``secret_by_default`` kind auto-mints + links a Secret on finalize (#1334)."""
        from world.distinctions.factories import DistinctionFactory
        from world.distinctions.models import CharacterDistinction
        from world.secrets.constants import SecretLevel

        criminal = DistinctionFactory(
            name="Wanted Criminal",
            category=self.dist_category,
            secret_by_default=True,
            default_secret_level=SecretLevel.DANGEROUS,
        )
        draft = self._create_complete_draft()
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": criminal.id,
                "distinction_name": criminal.name,
                "distinction_slug": criminal.slug,
                "category_slug": self.dist_category.slug,
                "rank": 1,
                "cost": 5,
                "notes": "",
            },
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        cd = CharacterDistinction.objects.get(character=character.sheet_data, distinction=criminal)
        assert cd.is_secret is True
        assert cd.secret.level == SecretLevel.DANGEROUS
        assert cd.secret.subject_sheet_id == character.sheet_data.pk

    def test_creates_modifiers_for_distinction_effects(self):
        """Distinction effects create CharacterModifier records."""
        from world.mechanics.models import CharacterModifier

        draft = self._create_complete_draft()
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": self.ranked_distinction.id,
                "distinction_name": self.ranked_distinction.name,
                "distinction_slug": self.ranked_distinction.slug,
                "category_slug": self.dist_category.slug,
                "rank": 2,
                "cost": 20,
                "notes": "",
            },
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        # The ranked distinction has an effect: +5 per rank to strength_modifier
        # At rank 2, this should be value 10
        modifier = CharacterModifier.objects.get(
            character=character.sheet_data,
            target=self.strength_modifier,
        )
        assert modifier.value == 10  # 5 * rank 2

    def test_no_distinctions_created_when_draft_has_none(self):
        """No distinctions created if draft_data has no distinctions."""
        from world.distinctions.models import CharacterDistinction

        draft = self._create_complete_draft()
        draft.draft_data.pop("distinctions", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        assert not CharacterDistinction.objects.filter(character=character.sheet_data).exists()

    def test_skips_invalid_distinction_ids(self):
        """Invalid distinction IDs are silently skipped."""
        from world.distinctions.models import CharacterDistinction

        draft = self._create_complete_draft()
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": self.simple_distinction.id,
                "distinction_name": self.simple_distinction.name,
                "distinction_slug": self.simple_distinction.slug,
                "category_slug": self.dist_category.slug,
                "rank": 1,
                "cost": 5,
                "notes": "",
            },
            {
                "distinction_id": 99999,
                "distinction_name": "Nonexistent",
                "distinction_slug": "nonexistent",
                "category_slug": "fake",
                "rank": 1,
                "cost": 0,
                "notes": "",
            },
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        char_distinctions = CharacterDistinction.objects.filter(character=character.sheet_data)
        assert char_distinctions.count() == 1
        assert char_distinctions.first().distinction == self.simple_distinction


class FinalizeCharacterDistinctionResonanceTests(FinalizationTestMixin, TestCase):
    """CG wiring of distinction resonance grants + the aura-ordering fix (#1834, US3).

    "A Predatory distinction means you carry that vibe from the start, it shows in
    your aura" — a distinction carrying a ``DistinctionResonanceGrant`` must, at CG,
    claim the character's resonance, write a DISTINCTION seed ledger row, and (since
    ``CharacterAura`` is created later in ``finalize_magic_data``, after distinctions
    are materialized) have that seed reflected in the starting aura.
    """

    @classmethod
    def setUpTestData(cls):
        from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
        from world.distinctions.models import DistinctionEffect
        from world.magic.factories import (
            AffinityFactory,
            DistinctionResonanceGrantFactory,
            ResonanceFactory,
        )
        from world.mechanics.constants import RESONANCE_CATEGORY_NAME
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        cls.dist_category = DistinctionCategoryFactory(name="Resonance Test Category")

        # "Predatory": seeds an Abyssal resonance via the DistinctionResonanceGrant
        # sidecar — no DistinctionEffect involved, so this exercises the reconcile
        # wiring on its own.
        cls.abyssal_affinity = AffinityFactory(name="Abyssal")
        cls.abyssal_resonance = ResonanceFactory(name="Predation", affinity=cls.abyssal_affinity)
        cls.predatory_distinction = DistinctionFactory(
            name="Predatory",
            category=cls.dist_category,
            cost_per_rank=5,
            max_rank=1,
            is_active=True,
        )
        DistinctionResonanceGrantFactory(
            distinction=cls.predatory_distinction,
            resonance=cls.abyssal_resonance,
            flat_amount_per_rank=10,
        )

        # "Serene": a resonance-CATEGORY-targeted DistinctionEffect (the dead #1834
        # write path) — must produce no CharacterModifier at CG.
        resonance_category = ModifierCategoryFactory(name=RESONANCE_CATEGORY_NAME)
        cls.serenity_resonance = ResonanceFactory(name="Serenity", affinity=cls.abyssal_affinity)
        cls.serenity_target = ModifierTargetFactory(
            name="Serenity Target",
            category=resonance_category,
            target_resonance=cls.serenity_resonance,
        )
        cls.serene_distinction = DistinctionFactory(
            name="Serene",
            category=cls.dist_category,
            cost_per_rank=5,
            max_rank=1,
            is_active=True,
        )
        DistinctionEffect.objects.create(
            distinction=cls.serene_distinction,
            target=cls.serenity_target,
            value_per_rank=10,
        )

        cls._setup_finalization_base(cls, prefix="Resonance Test", height_min=1500, height_max=1600)

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"resonancetest_{id(self)}")

    def _create_complete_draft(self):
        return self._create_base_draft(first_name="ResonanceTest", skills={}, specializations={})

    def test_cg_distinction_seeds_resonance_and_recomputes_starting_aura(self):
        """A CG distinction carrying a resonance grant claims the resonance, writes a
        DISTINCTION seed ledger row, and the starting CharacterAura reflects it — the
        load-bearing assertion proving the CG aura-ordering fix.
        """
        from world.distinctions.models import CharacterDistinction
        from world.magic.constants import GainSource
        from world.magic.models import CharacterAura, CharacterResonance, ResonanceGrant
        from world.mechanics.constants import RESONANCE_CATEGORY_NAME
        from world.mechanics.models import CharacterModifier

        draft = self._create_complete_draft()
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": self.predatory_distinction.id,
                "distinction_name": self.predatory_distinction.name,
                "distinction_slug": self.predatory_distinction.slug,
                "category_slug": self.dist_category.slug,
                "rank": 1,
                "cost": 5,
                "notes": "",
            },
            {
                "distinction_id": self.serene_distinction.id,
                "distinction_name": self.serene_distinction.name,
                "distinction_slug": self.serene_distinction.slug,
                "category_slug": self.dist_category.slug,
                "rank": 1,
                "cost": 5,
                "notes": "",
            },
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        char_dist = CharacterDistinction.objects.get(
            character=sheet, distinction=self.predatory_distinction
        )

        # The CharacterResonance is claimed.
        character_resonance = CharacterResonance.objects.get(
            character_sheet=sheet, resonance=self.abyssal_resonance
        )
        assert character_resonance.lifetime_earned == 10

        # The DISTINCTION seed ledger row exists.
        assert ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=char_dist,
            resonance=self.abyssal_resonance,
        ).exists()

        # The stored CharacterAura reflects the seeded resonance.
        aura = CharacterAura.objects.get(character=character)
        assert aura.abyssal > 0

        # The resonance-category-targeted DistinctionEffect on "Serene" produces NO
        # resonance-category CharacterModifier at CG (dead write path removed).
        assert not CharacterModifier.objects.filter(
            character=sheet,
            target__category__name=RESONANCE_CATEGORY_NAME,
        ).exists()


class FinalizeGiftAndTechniquesTests(TestCase):
    """finalize_magic_data links the CG-chosen catalog Gift/Techniques (#2426 Task 6).

    Supersedes the old CG-creates-a-new-technique contract: the Gift and
    Techniques are staff-authored catalog rows the player picked via the CG
    option endpoints;
    finalize only links them (CharacterGift/CharacterTechnique + the latent GIFT
    thread), it never mints new Gift/Technique rows.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import (
            GiftFactory,
            ResonanceFactory,
            TechniqueFactory,
            TraditionFactory,
        )
        from world.skills.factories import SkillFactory
        from world.traits.factories import StatTraitFactory

        cls.tradition = TraditionFactory()
        cls.resonance = ResonanceFactory()
        cls.other_resonance = ResonanceFactory()
        cls.gift = GiftFactory(name="Shadow Majesty")
        cls.gift.resonances.add(cls.resonance, cls.other_resonance)
        cls.technique_one = TechniqueFactory(gift=cls.gift, name="Umbral Step")
        cls.technique_two = TechniqueFactory(gift=cls.gift, name="Umbral Veil")
        cls.stat_trait = StatTraitFactory(name="Focus")
        cls.skill = SkillFactory()

    def test_character_gift_links_catalog_gift_without_creating_new_row(self) -> None:
        """CharacterGift links the existing catalog Gift; no new Gift row is minted."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterGift, Gift

        gift_count_before = Gift.objects.count()
        sheet = CharacterSheetFactory()
        draft = self._create_draft()

        finalize_magic_data(draft, sheet)

        assert Gift.objects.count() == gift_count_before
        char_gift = CharacterGift.objects.get(character=sheet)
        assert char_gift.gift == self.gift

    def test_character_technique_rows_created_for_each_selected_technique(self) -> None:
        """CharacterTechnique links every selected catalog Technique — no others."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterTechnique

        sheet = CharacterSheetFactory()
        draft = self._create_draft(technique_ids=[self.technique_one.id, self.technique_two.id])

        finalize_magic_data(draft, sheet)

        linked = set(
            CharacterTechnique.objects.filter(character=sheet).values_list(
                "technique_id", flat=True
            )
        )
        assert linked == {self.technique_one.id, self.technique_two.id}

    def test_latent_gift_thread_carries_chosen_resonance(self) -> None:
        """The provisioned latent GIFT thread's resonance matches the CG pick."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        sheet = CharacterSheetFactory()
        draft = self._create_draft(resonance=self.other_resonance)

        finalize_magic_data(draft, sheet)

        thread = Thread.objects.get(owner=sheet, target_kind=TargetKind.GIFT, target_gift=self.gift)
        assert thread.resonance == self.other_resonance

    def test_ritual_check_config_matches_anima_check_choice(self) -> None:
        """The provisioned anima Ritual's check_config stat/skill match the CG pick."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models.ritual_check_config import RitualCheckConfig
        from world.roster.factories import RosterEntryFactory

        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=sheet)
        draft = self._create_draft()

        finalize_magic_data(draft, sheet)

        config = RitualCheckConfig.objects.get(ritual__author_account=draft.account)
        assert config.stat == self.stat_trait
        assert config.skill == self.skill

    def test_ritual_name_honors_anima_ritual_name(self) -> None:
        """draft_data['anima_ritual_name'], when set, names the provisioned Ritual."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models.rituals import Ritual
        from world.roster.factories import RosterEntryFactory

        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=sheet)
        draft = self._create_draft(anima_ritual_name="Sunrise Devotions")

        finalize_magic_data(draft, sheet)

        ritual = Ritual.objects.get(author_account=draft.account)
        assert ritual.name == "Sunrise Devotions"

    def test_ritual_name_defaults_to_first_name_possessive(self) -> None:
        """Without anima_ritual_name, the Ritual falls back to "<first_name>'s Anima Ritual"."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models.rituals import Ritual
        from world.roster.factories import RosterEntryFactory

        sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=sheet)
        draft = self._create_draft()
        draft.draft_data["first_name"] = "Marcus"
        draft.save(update_fields=["draft_data"])

        finalize_magic_data(draft, sheet)

        ritual = Ritual.objects.get(author_account=draft.account)
        assert ritual.name == "Marcus's Anima Ritual"

    def test_character_tradition_created_unconditionally(self) -> None:
        """CharacterTradition is always created — compute_magic_errors requires it."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterTradition

        sheet = CharacterSheetFactory()
        draft = self._create_draft()

        finalize_magic_data(draft, sheet)

        char_tradition = CharacterTradition.objects.get(character=sheet)
        assert char_tradition.tradition == self.tradition

    def test_aura_created_with_defaults(self) -> None:
        """finalize_magic_data creates CharacterAura with default values."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterAura

        sheet = CharacterSheetFactory()
        draft = self._create_draft()

        finalize_magic_data(draft, sheet)

        aura = CharacterAura.objects.get(character=sheet.character)
        assert aura.celestial == Decimal("0.00")
        assert aura.primal == Decimal("80.00")
        assert aura.abyssal == Decimal("20.00")
        assert aura.glimpse_story == ""

    def test_aura_saves_glimpse_story(self) -> None:
        """glimpse_story from draft_data is saved on CharacterAura."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterAura

        sheet = CharacterSheetFactory()
        draft = self._create_draft(glimpse_story="I first saw the threads at age twelve.")

        finalize_magic_data(draft, sheet)

        aura = CharacterAura.objects.get(character=sheet.character)
        assert aura.glimpse_story == "I first saw the threads at age twelve."

    def test_no_gift_selected_no_ops_gift_and_technique_linking(self) -> None:
        """Legacy/test-only draft_data missing selected_gift_id links nothing."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterGift, CharacterTechnique

        sheet = CharacterSheetFactory()
        draft = self._create_draft()
        draft.draft_data.pop("selected_gift_id")
        draft.save(update_fields=["draft_data"])

        finalize_magic_data(draft, sheet)

        assert not CharacterGift.objects.filter(character=sheet).exists()
        assert not CharacterTechnique.objects.filter(character=sheet).exists()

    def _create_draft(
        self,
        *,
        tradition: object | None = None,
        technique_ids: list[int] | None = None,
        resonance: object | None = None,
        glimpse_story: str = "",
        anima_ritual_name: str = "",
    ) -> CharacterDraft:
        """Create a minimal draft with catalog gift/technique picks for testing."""
        from evennia_extensions.factories import AccountFactory
        from world.character_creation.factories import CharacterDraftFactory

        draft_data: dict = {
            "selected_gift_id": self.gift.id,
            "selected_technique_ids": technique_ids or [self.technique_one.id],
            "selected_gift_resonance_id": (resonance or self.resonance).id,
            "anima_check_stat_id": self.stat_trait.id,
            "anima_check_skill_id": self.skill.id,
        }
        if glimpse_story:
            draft_data["glimpse_story"] = glimpse_story
        if anima_ritual_name:
            draft_data["anima_ritual_name"] = anima_ritual_name

        return CharacterDraftFactory(
            account=AccountFactory(),
            draft_data=draft_data,
            selected_tradition=self.tradition if tradition is None else tradition,
        )


class UnboundSurchargeThroughRealCGFinalizeTests(FinalizationTestMixin, TestCase):
    """The Unbound magic-learning AP surcharge (#2442), proven end-to-end through the
    REAL CG flow (review-requested — the "Important" test): a draft built via the same
    finalization helpers as the rest of this file selects the Unbound tradition through
    the real ``select-tradition`` endpoint (which auto-adds the "Unbound" drawback
    distinction, #2442), is finalized via ``finalize_character``, and the resulting
    character pays the surcharge on a live technique acquisition.

    This exercises the full chain the unit-level surcharge tests
    (``world.magic.tests.test_gift_acquisition_service
    .UnboundMagicLearningApSurchargeTest``) stub out: draft -> select-tradition ->
    finalize_character -> ``_create_distinction_modifiers_bulk`` ->
    ``world.mechanics.services.get_modifier_total`` -> ``charge_and_learn``'s surcharge
    read.
    """

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"unboundsurcharge_{id(self)}")
        self._setup_finalization_base(
            self, prefix="Unbound CG Surcharge", height_min=2500, height_max=2600
        )

    def test_finalize_via_real_select_tradition_pays_ap_surcharge_on_acquisition(self):
        import math

        from rest_framework import status as drf_status
        from rest_framework.test import APIClient

        from world.action_points.models import ActionPointPool
        from world.character_creation.constants import UNBOUND_TRADITION_NAME
        from world.magic.constants import (
            MAGIC_LEARNING_AP_COST_TARGET_NAME,
            MAGIC_MODIFIER_CATEGORY_NAME,
        )
        from world.magic.models import TechniqueTeachingOffer
        from world.magic.services.gift_acquisition import accept_technique_offer
        from world.mechanics.models import ModifierTarget
        from world.mechanics.services import get_modifier_total
        from world.roster.factories import RosterTenureFactory
        from world.seeds.character_creation import seed_beginning_traditions

        # Seed the real "Unbound" Tradition + wire it to this test's own Gift, then run
        # the real seeder to author the BeginningTradition gate (required_distinction=
        # the real "unbound" drawback, #2442) for this test's own Beginnings row.
        unbound_tradition = TraditionFactory(name=UNBOUND_TRADITION_NAME)
        TraditionGiftGrantFactory(tradition=unbound_tradition, gift=self.gift)
        seed_beginning_traditions()

        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            age=25,
            height_band=self.height_band,
            height_inches=(self.height_band.min_inches + self.height_band.max_inches) // 2,
            build=self.build,
            draft_data={
                "first_name": "Solitary",
                "description": "A test character",
                "stats": DEFAULT_STATS,
                "lineage_is_orphan": True,
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": False,
                "traits_complete": True,
            },
        )

        # Real select-tradition endpoint — auto-adds the "Unbound" drawback distinction
        # to the draft (#2442's one deliberate exception; see
        # TraditionViewSet.select_tradition's docstring).
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            f"/api/character-creation/drafts/{draft.id}/select-tradition/",
            {"tradition_id": unbound_tradition.id},
            format="json",
        )
        assert response.status_code == drf_status.HTTP_200_OK
        draft.refresh_from_db()
        assert draft.selected_tradition == unbound_tradition
        distinction_ids = {
            entry.get("distinction_id") for entry in draft.draft_data.get("distinctions", [])
        }
        assert distinction_ids, "select-tradition should have auto-added the Unbound drawback"

        # Complete the Gift stage against the (now-selected) Unbound tradition.
        self._create_complete_magic(draft)
        # CharacterDraft is a SharedMemoryModel: the select-tradition response
        # serializer already computed stage errors on this same idmapper-shared
        # instance, BEFORE the Gift keys above existed. Drop the per-instance memo
        # so finalize re-validates the now-complete draft.
        if hasattr(draft, "_cached_stage_errors"):
            del draft._cached_stage_errors

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        # draft -> finalize -> _create_distinction_modifiers_bulk -> get_modifier_total:
        # the live post-CG CharacterModifier resolution path charge_and_learn reads.
        target = ModifierTarget.objects.get(
            name=MAGIC_LEARNING_AP_COST_TARGET_NAME,
            category__name=MAGIC_MODIFIER_CATEGORY_NAME,
        )
        assert get_modifier_total(sheet, target) == 50

        # Drive one technique acquisition through the shared charge_and_learn seam
        # (accept_technique_offer front door) and assert the AP charged is
        # ceil(base_ap_cost * 1.5).
        teacher_tenure = RosterTenureFactory()
        ActionPointPool.get_or_create_for_character(teacher_tenure.character)
        learner_pool = ActionPointPool.get_or_create_for_character(character)
        learner_pool.current = 200
        learner_pool.save()

        second_technique = TechniqueFactory(gift=self.gift)
        base_ap_cost = 5
        offer = TechniqueTeachingOffer.objects.create(
            teacher=teacher_tenure,
            technique=second_technique,
            pitch="A second lesson, the hard way",
            learn_ap_cost=base_ap_cost,
            banked_ap=1,
        )

        accept_technique_offer(sheet, offer)

        learner_pool.refresh_from_db()
        expected_cost = math.ceil(base_ap_cost * 1.5)
        assert expected_cost == 8  # sanity: ceil(5 * 1.5) == 8
        assert learner_pool.current == 200 - expected_cost


class FinalizeCharacterTarotTests(FinalizationTestMixin, TestCase):
    """Tests for tarot surname derivation and tarot data transfer during finalization."""

    @classmethod
    def setUpTestData(cls):
        cls._setup_finalization_base(
            cls, prefix="Tarot Finalize Test", height_min=1700, height_max=1800
        )
        # Additional tarot cards for specific tests
        cls.major_card = TarotCard.objects.create(
            name="The Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Fatui",
        )
        cls.swords_card = TarotCard.objects.create(
            name="Three of Swords",
            arcana_type=ArcanaType.MINOR,
            suit="swords",
            rank=3,
        )

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"tarottest_{id(self)}")

    def _create_complete_draft(self, *, first_name="Marcus", tarot_card=None, tarot_reversed=False):
        card = tarot_card or self.major_card
        return self._create_base_draft(
            first_name=first_name,
            tarot_card_name=card.name,
            tarot_reversed=tarot_reversed,
        )

    def test_finalize_with_tarot_sets_surname(self):
        """Major Arcana upright tarot card sets latin_name as surname."""
        draft = self._create_complete_draft(
            first_name="Marcus",
            tarot_card=self.major_card,
            tarot_reversed=False,
        )

        character = finalize_character(draft, add_to_roster=True)

        assert character.db_key == "Marcus Fatui"
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.tarot_card == self.major_card
        assert sheet.tarot_reversed is False

    def test_finalize_with_reversed_tarot(self):
        """Major Arcana reversed tarot card sets N'-prefixed latin_name as surname."""
        draft = self._create_complete_draft(
            first_name="Marcus",
            tarot_card=self.major_card,
            tarot_reversed=True,
        )

        character = finalize_character(draft, add_to_roster=True)

        assert character.db_key == "Marcus N'Fatui"
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.tarot_card == self.major_card
        assert sheet.tarot_reversed is True

    def test_finalize_with_minor_arcana(self):
        """Minor Arcana upright tarot card sets singular suit name as surname."""
        draft = self._create_complete_draft(
            first_name="Marcus",
            tarot_card=self.swords_card,
            tarot_reversed=False,
        )

        character = finalize_character(draft, add_to_roster=True)

        assert character.db_key == "Marcus Sword"
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.tarot_card == self.swords_card
        assert sheet.tarot_reversed is False

    def test_finalize_tarot_is_best_effort(self):
        """Finalization succeeds even if tarot card ID is invalid."""
        draft = self._create_complete_draft(first_name="Marcus")
        # Override with nonexistent tarot_card_name
        draft.draft_data["tarot_card_name"] = "Nonexistent Card"
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        # Character created with just first name (no surname)
        assert character.db_key == "Marcus"
        # Sheet should not have tarot card set
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.tarot_card is None


class FinalizeMagicAuraTests(FinalizationTestMixin, TestCase):
    """Test aura and glimpse story finalization."""

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="aura_test_user")
        self._setup_finalization_base(self, prefix="Aura Test", height_min=2100, height_max=2200)

    def _create_draft(self, **extra_draft_data):
        return self._create_base_draft(first_name="AuraTest", **extra_draft_data)

    def test_finalize_creates_character_aura_with_defaults(self):
        """Finalization should create a CharacterAura record."""
        from world.magic.models import CharacterAura

        draft = self._create_draft()
        character = finalize_character(draft, add_to_roster=True)

        aura = CharacterAura.objects.get(character=character)
        assert aura.celestial == Decimal("0.00")
        assert aura.primal == Decimal("80.00")
        assert aura.abyssal == Decimal("20.00")

    def test_finalize_saves_glimpse_story(self):
        """glimpse_story from draft_data should be saved on the CharacterAura."""
        from world.magic.models import CharacterAura

        draft = self._create_draft(glimpse_story="I first saw the threads at age twelve.")
        character = finalize_character(draft, add_to_roster=True)

        aura = CharacterAura.objects.get(character=character)
        assert aura.glimpse_story == "I first saw the threads at age twelve."

    def test_finalize_aura_without_glimpse_story(self):
        """Aura is created even when glimpse_story is not provided."""
        from world.magic.models import CharacterAura

        draft = self._create_draft()
        character = finalize_character(draft, add_to_roster=True)

        aura = CharacterAura.objects.get(character=character)
        assert aura.glimpse_story == ""

    def test_finalize_persists_glimpse_tags_and_state(self):
        """glimpse_tag_ids from draft_data become CharacterGlimpseTag rows."""
        from world.magic.constants import GlimpseState, GlimpseTagAxis
        from world.magic.factories import GlimpseTagFactory
        from world.magic.models import CharacterAura, CharacterGlimpseTag

        tone = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="fin-tone")
        consequence = GlimpseTagFactory(axis=GlimpseTagAxis.CONSEQUENCE, slug="fin-consequence")
        draft = self._create_draft(glimpse_tag_ids=[tone.pk, consequence.pk])
        character = finalize_character(draft, add_to_roster=True)

        aura = CharacterAura.objects.get(character=character)
        assert aura.glimpse_state == GlimpseState.TAGS_ONLY
        assert CharacterGlimpseTag.objects.filter(aura=aura).count() == 2

    def test_finalize_with_tags_and_prose_is_complete(self):
        """Both tags and prose present should compute COMPLETE glimpse_state."""
        from world.magic.constants import GlimpseState, GlimpseTagAxis
        from world.magic.factories import GlimpseTagFactory
        from world.magic.models import CharacterAura

        tone = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="fin-tone-2")
        draft = self._create_draft(
            glimpse_tag_ids=[tone.pk],
            glimpse_story="I burned the barn down.",
        )
        character = finalize_character(draft, add_to_roster=True)
        aura = CharacterAura.objects.get(character=character)
        assert aura.glimpse_state == GlimpseState.COMPLETE

    def test_finalize_links_glimpse_distinctions(self):
        """Chosen distinctions listed in glimpse_linked_distinction_ids get from_glimpse."""
        from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
        from world.distinctions.models import CharacterDistinction
        from world.magic.models import CharacterAura

        category = DistinctionCategoryFactory(name="Glimpse Test Category")
        distinction = DistinctionFactory(
            name="Glimpse Test Distinction",
            category=category,
            cost_per_rank=5,
            max_rank=1,
            is_active=True,
        )
        draft = self._create_draft(
            distinctions=[
                {
                    "distinction_id": distinction.id,
                    "distinction_name": distinction.name,
                    "distinction_slug": distinction.slug,
                    "category_slug": category.slug,
                    "rank": 1,
                    "cost": 5,
                    "notes": "",
                },
            ],
            glimpse_linked_distinction_ids=[distinction.pk],
        )
        character = finalize_character(draft, add_to_roster=True)

        aura = CharacterAura.objects.get(character=character)
        cd = CharacterDistinction.objects.get(
            character=character.sheet_data, distinction=distinction
        )
        assert cd.from_glimpse_id == aura.pk

    def test_finalize_ignores_unknown_linked_distinction_ids(self):
        """Ids that never materialized as CharacterDistinction rows are skipped."""
        from world.magic.models import CharacterAura

        draft = self._create_draft(glimpse_linked_distinction_ids=[999999])
        character = finalize_character(draft, add_to_roster=True)
        assert CharacterAura.objects.filter(character=character).exists()


class FinalizeGMCharacterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.gm.factories import GMProfileFactory, GMTableFactory

        cls.gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.gm)

    def _make_gm_draft(self, **overrides) -> CharacterDraft:
        from world.character_creation.factories import CharacterDraftFactory

        defaults = {
            "account": self.gm.account,
            "is_gm_creation": True,
            "target_table": self.table,
            "story_title": "The Grand Design",
            "story_description": "A story of intrigue and power.",
            # CharacterTradition creation is unconditional in finalize_magic_data
            # (#2426) — a tradition is required even for GM-created drafts.
            "selected_tradition": TraditionFactory(),
            "draft_data": {"first_name": "Aurelius"},
        }
        defaults.update(overrides)
        return CharacterDraftFactory(**defaults)

    def test_creates_roster_entry_on_available(self) -> None:
        from world.character_creation.services import finalize_gm_character

        draft = self._make_gm_draft()
        entry, _ = finalize_gm_character(draft)
        assert entry.pk is not None
        assert entry.roster.name == "Available"

    def test_stamps_gm_table_provenance(self) -> None:
        """The roster entry records GM_TABLE provenance + the authoring GM + table (#1506)."""
        from world.character_creation.services import finalize_gm_character
        from world.roster.models.choices import CreationProvenance

        draft = self._make_gm_draft()
        entry, _ = finalize_gm_character(draft)
        assert entry.creation_provenance == CreationProvenance.GM_TABLE
        assert entry.created_by_account == self.gm.account
        assert entry.created_for_table == self.table

    def test_creates_story_linked_to_target_table(self) -> None:
        from world.character_creation.services import finalize_gm_character

        draft = self._make_gm_draft()
        _, story = finalize_gm_character(draft)
        assert story.primary_table == self.table
        assert story.title == "The Grand Design"
        assert self.gm.account in story.owners.all()

    def test_creates_active_story_participation(self) -> None:
        from world.character_creation.services import finalize_gm_character
        from world.stories.models import StoryParticipation

        draft = self._make_gm_draft()
        entry, story = finalize_gm_character(draft)
        participation = StoryParticipation.objects.get(
            story=story, character=entry.character_sheet.character
        )
        assert participation.is_active is True

    def test_no_tenure_created(self) -> None:
        from world.character_creation.services import finalize_gm_character

        draft = self._make_gm_draft()
        entry, _ = finalize_gm_character(draft)
        assert entry.tenures.count() == 0

    def test_draft_deleted_on_success(self) -> None:
        from world.character_creation.models import CharacterDraft
        from world.character_creation.services import finalize_gm_character

        draft = self._make_gm_draft()
        draft_pk = draft.pk
        finalize_gm_character(draft)
        assert not CharacterDraft.objects.filter(pk=draft_pk).exists()

    def test_rejects_non_gm_draft(self) -> None:
        from django.core.exceptions import ValidationError

        from world.character_creation.services import finalize_gm_character

        draft = self._make_gm_draft(is_gm_creation=False)
        with self.assertRaises(ValidationError):
            finalize_gm_character(draft)

    def test_rejects_missing_target_table(self) -> None:
        from django.core.exceptions import ValidationError

        from world.character_creation.services import finalize_gm_character

        draft = self._make_gm_draft(target_table=None)
        with self.assertRaises(ValidationError):
            finalize_gm_character(draft)

    def test_rejects_missing_story_title(self) -> None:
        from django.core.exceptions import ValidationError

        from world.character_creation.services import finalize_gm_character

        draft = self._make_gm_draft(story_title="")
        with self.assertRaises(ValidationError):
            finalize_gm_character(draft)

    def test_rejects_target_table_owned_by_other_gm(self) -> None:
        from django.core.exceptions import ValidationError

        from world.character_creation.services import finalize_gm_character
        from world.gm.factories import GMProfileFactory, GMTableFactory

        other_gm = GMProfileFactory()
        other_table = GMTableFactory(gm=other_gm)
        draft = self._make_gm_draft(target_table=other_table)
        with self.assertRaises(ValidationError):
            finalize_gm_character(draft)

    def test_creates_story_progress_for_cg_character(self) -> None:
        """CG finalization creates exactly one StoryProgress with current_episode=None."""
        from world.character_creation.services import finalize_gm_character
        from world.stories.models import StoryProgress

        draft = self._make_gm_draft()
        entry, story = finalize_gm_character(draft)
        sheet = entry.character_sheet

        progress_qs = StoryProgress.objects.filter(story=story, character_sheet=sheet)
        assert progress_qs.count() == 1, "Exactly one StoryProgress should be created"
        progress = progress_qs.get()
        assert progress.current_episode is None, "current_episode should be None at CG time"


class FinalizeRitualKnowledgeTests(FinalizationTestMixin, TestCase):
    """Tests for ritual knowledge reconciliation during character finalization (Phase 8)."""

    @classmethod
    def setUpTestData(cls):
        from world.skills.factories import SkillFactory

        cls._setup_finalization_base(
            cls, prefix="Ritual Knowledge Test", height_min=3100, height_max=3200
        )
        # Skill needed so provision_player_anima_ritual doesn't log + skip.
        cls.combat_skill = SkillFactory(trait__name="RKTMelee")

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"ritualktest_{id(self)}")

    def _create_complete_draft(self) -> CharacterDraft:
        return self._create_base_draft(
            first_name="RitualKTest",
            skills={str(self.combat_skill.pk): 20},
        )

    def test_finalize_creates_player_anima_ritual(self) -> None:
        """finalize_character creates a SCENE_ACTION Ritual authored by the player account."""
        from world.magic.constants import RitualExecutionKind
        from world.magic.models.rituals import Ritual

        draft = self._create_complete_draft()
        finalize_character(draft, add_to_roster=True)

        ritual = Ritual.objects.filter(
            author_account=self.account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        ).first()
        assert ritual is not None, "Expected a SCENE_ACTION Ritual authored by the player account"
        assert "RitualKTest" in ritual.name

    def test_finalize_creates_ritual_check_config(self) -> None:
        """finalize_character creates RitualCheckConfig pointing at the per-character CheckType."""
        from world.magic.constants import RitualExecutionKind
        from world.magic.models.ritual_check_config import RitualCheckConfig
        from world.magic.models.rituals import Ritual
        from world.magic.seeds_checks import character_magic_check_type_name

        draft = self._create_complete_draft()
        character = finalize_character(draft, add_to_roster=True)

        ritual = Ritual.objects.filter(
            author_account=self.account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        ).first()
        assert ritual is not None
        config = RitualCheckConfig.objects.filter(ritual=ritual).first()
        assert config is not None, "Expected a RitualCheckConfig for the player anima ritual"
        assert config.check_type is not None, (
            "Provisioning should wire check_type to the per-character CheckType"
        )
        assert config.check_type.name == character_magic_check_type_name(character.sheet_data)

    def test_finalize_creates_ritual_knowledge_row(self) -> None:
        """finalize_character creates CharacterRitualKnowledge for the player anima ritual."""
        from world.magic.constants import RitualExecutionKind
        from world.magic.models import CharacterRitualKnowledge
        from world.magic.models.rituals import Ritual

        draft = self._create_complete_draft()
        character = finalize_character(draft, add_to_roster=True)

        ritual = Ritual.objects.filter(
            author_account=self.account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        ).first()
        assert ritual is not None
        roster_entry = character.sheet_data.roster_entry
        assert CharacterRitualKnowledge.objects.filter(
            roster_entry=roster_entry,
            ritual=ritual,
        ).exists(), "Expected CharacterRitualKnowledge for the player anima ritual"

    def test_finalize_grants_path_rituals(self) -> None:
        """finalize_character reconciles PathRitualGrant → CharacterRitualKnowledge rows."""
        from world.magic.factories import RitualFactory
        from world.magic.models import CharacterRitualKnowledge
        from world.magic.models.grants import PathRitualGrant

        granted_ritual = RitualFactory()
        PathRitualGrant.objects.create(path=self.path, ritual=granted_ritual)

        draft = self._create_complete_draft()
        character = finalize_character(draft, add_to_roster=True)

        roster_entry = character.sheet_data.roster_entry
        assert CharacterRitualKnowledge.objects.filter(
            roster_entry=roster_entry,
            ritual=granted_ritual,
        ).exists(), "Expected CharacterRitualKnowledge for the path-granted ritual"

    def test_finalize_grants_beginnings_rituals(self) -> None:
        """finalize_character grants BeginningsRitualGrant rituals directly (Option A)."""
        from world.magic.factories import RitualFactory
        from world.magic.models import CharacterRitualKnowledge
        from world.magic.models.grants import BeginningsRitualGrant

        granted_ritual = RitualFactory()
        BeginningsRitualGrant.objects.create(
            beginnings=self.beginnings,
            ritual=granted_ritual,
        )

        draft = self._create_complete_draft()
        character = finalize_character(draft, add_to_roster=True)

        roster_entry = character.sheet_data.roster_entry
        assert CharacterRitualKnowledge.objects.filter(
            roster_entry=roster_entry,
            ritual=granted_ritual,
        ).exists(), "Expected CharacterRitualKnowledge for the beginnings-granted ritual"


class FinalizeVitalsTests(FinalizationTestMixin, TestCase):
    """Tests that finalize_character initialises CharacterVitals at full health."""

    @classmethod
    def setUpTestData(cls):
        cls._setup_finalization_base(cls, prefix="Vitals Test", height_min=3300, height_max=3400)

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"vitalstest_{id(self)}")

    def _create_complete_draft(self) -> CharacterDraft:
        return self._create_base_draft(first_name="VitalsTest")

    def test_finalize_initializes_vitals_at_full_health(self):
        """finalize_character must create CharacterVitals with health == max_health > 0."""
        from world.vitals.models import CharacterVitals

        draft = self._create_complete_draft()
        character = finalize_character(draft, add_to_roster=True)

        sheet = character.sheet_data
        vitals = CharacterVitals.objects.get(character_sheet=sheet)
        self.assertGreater(vitals.max_health, 0, "max_health must be > 0 after finalization")
        self.assertEqual(
            vitals.health,
            vitals.max_health,
            "health must equal max_health (full health) at character creation",
        )


class FinalizeResidenceTests(FinalizationTestMixin, TestCase):
    """Journey 7 (#2036): CG auto-residence via StartingArea.grants_residence_tenancy.

    finalize_character grants a LocationTenancy at the starting room (auto-defaulting
    current_residence via maybe_default_residence) when the chosen StartingArea authors
    it. A False toggle or a missing starting room is a graceful no-op — matching the
    pre-#2036 behavior of only ever setting Evennia ``home`` directly.
    """

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username=f"residencetest_{id(self)}")
        self._setup_finalization_base(self, prefix="Residence Test", height_min=700, height_max=800)

    def test_finalize_grants_residence_tenancy_when_area_authors_it(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.locations.models import LocationTenancy

        room_profile = RoomProfileFactory()
        self.area.default_starting_room = room_profile
        self.area.grants_residence_tenancy = True
        self.area.save()
        draft = self._create_base_draft()

        character = finalize_character(draft)

        sheet = character.sheet_data
        persona = sheet.primary_persona
        self.assertTrue(
            LocationTenancy.objects.filter(
                tenant_persona=persona, room_profile=room_profile
            ).exists()
        )
        sheet.refresh_from_db()
        self.assertEqual(sheet.current_residence, room_profile)
        self.assertEqual(character.home, room_profile.objectdb)

    def test_finalize_no_tenancy_when_area_does_not_grant_it(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.locations.models import LocationTenancy

        room_profile = RoomProfileFactory()
        self.area.default_starting_room = room_profile
        self.area.grants_residence_tenancy = False
        self.area.save()
        draft = self._create_base_draft()

        character = finalize_character(draft)

        sheet = character.sheet_data
        self.assertFalse(LocationTenancy.objects.filter(room_profile=room_profile).exists())
        sheet.refresh_from_db()
        self.assertIsNone(sheet.current_residence)
        # Evennia home is still set directly — unaffected, matching pre-#2036 behavior.
        self.assertEqual(character.home, room_profile.objectdb)

    def test_finalize_with_no_starting_room_is_a_graceful_no_op(self):
        from world.locations.models import LocationTenancy

        self.area.default_starting_room = None
        self.area.grants_residence_tenancy = True
        self.area.save()
        draft = self._create_base_draft()

        character = finalize_character(draft)

        sheet = character.sheet_data
        self.assertIsNone(sheet.current_residence)
        self.assertFalse(LocationTenancy.objects.exists())


class FinalizeCharacterPreludeMissionTests(FinalizationTestMixin, TestCase):
    """Prelude-mission auto-grant at CG finalization (#2470)."""

    def setUp(self):
        from evennia_extensions.factories import RoomProfileFactory

        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="preludemissiontestuser")
        self._setup_finalization_base(
            self, prefix="Prelude Mission Test", height_min=700, height_max=800
        )
        # _grant_prelude_mission only runs when a starting room resolves (nested
        # under finalize_character's `if starting_room is not None:` block) — the
        # mixin's default StartingArea has no default_starting_room, so give it
        # one, matching the residence-tenancy tests' pattern above.
        self.area.default_starting_room = RoomProfileFactory()
        self.area.save()

    def test_finalize_grants_prelude_mission_when_set(self):
        from world.missions.constants import MissionStatus
        from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
        from world.missions.models import MissionInstance

        template = MissionTemplateFactory(name="Prelude Grant Test Template")
        MissionNodeFactory(template=template, key="entry", is_entry=True)
        self.beginnings.prelude_mission = template
        self.beginnings.save(update_fields=["prelude_mission"])

        draft = self._create_base_draft()
        character = finalize_character(draft, add_to_roster=True)

        instance = MissionInstance.objects.get(template=template)
        assert instance.status == MissionStatus.ACTIVE
        holder = instance.participants.get(is_contract_holder=True)
        assert holder.character_id == character.id
        assert instance.accepted_as_persona_id == character.sheet_data.primary_persona.id

    def test_finalize_is_a_no_op_when_beginnings_has_no_prelude_mission(self):
        from world.missions.models import MissionInstance

        # self.beginnings.prelude_mission is None by default (Task 1's factory default).
        draft = self._create_base_draft()
        finalize_character(draft, add_to_roster=True)
        assert not MissionInstance.objects.exists()

    def test_finalize_raises_when_prelude_mission_has_no_entry_node(self):
        from world.missions.factories import MissionTemplateFactory
        from world.missions.models import MissionNode

        template = MissionTemplateFactory(name="Broken Prelude Test Template")
        # Deliberately no MissionNodeFactory call — no entry node authored.
        self.beginnings.prelude_mission = template
        self.beginnings.save(update_fields=["prelude_mission"])

        draft = self._create_base_draft()
        sheet_count_before = CharacterSheet.objects.count()

        with self.assertRaises(MissionNode.DoesNotExist):
            finalize_character(draft, add_to_roster=True)

        # Whole-transaction rollback: no Character/CharacterSheet left behind.
        assert CharacterSheet.objects.count() == sheet_count_before
