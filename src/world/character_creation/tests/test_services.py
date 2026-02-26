"""
Tests for character creation services.
"""

from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia.accounts.models import AccountDB

from world.character_creation.factories import (
    DraftAnimaRitualFactory,
    DraftGiftFactory,
    DraftMotifFactory,
    DraftMotifResonanceAssociationFactory,
    DraftMotifResonanceFactory,
    DraftTechniqueFactory,
)
from world.character_creation.models import Beginnings, CharacterDraft, StartingArea
from world.character_creation.services import DraftIncompleteError, finalize_character
from world.character_sheets.models import CharacterSheet, Gender
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.forms.models import Build, HeightBand
from world.magic.factories import (
    EffectTypeFactory,
    ResonanceModifierTypeFactory,
    TechniqueStyleFactory,
    TraditionFactory,
)
from world.realms.models import Realm
from world.roster.models import Roster
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.models import CharacterTraitValue, Trait, TraitType

# Shared stats dict used by all finalization tests
DEFAULT_STATS = {
    "strength": 30,
    "agility": 30,
    "stamina": 30,
    "charm": 20,
    "presence": 20,
    "perception": 20,
    "intellect": 20,
    "wits": 30,
    "willpower": 30,
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
        target.resonance = ResonanceModifierTypeFactory()
        target.tradition = TraditionFactory()

    def _create_complete_magic(self, draft: CharacterDraft) -> None:
        """Create complete magic data (gift, technique, motif, ritual) for a draft."""
        resonance = self.magic_resonance if hasattr(self, "magic_resonance") else self.resonance
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(resonance)
        DraftTechniqueFactory(
            gift=gift,
            style=self.technique_style,
            effect_type=self.effect_type,
        )
        motif = DraftMotifFactory(draft=draft)
        motif_resonance = DraftMotifResonanceFactory(motif=motif, resonance=resonance)
        DraftMotifResonanceAssociationFactory(motif_resonance=motif_resonance)
        DraftAnimaRitualFactory(draft=draft)

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
        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )

        character = finalize_character(draft, add_to_roster=True)

        # Verify character was created (tarot surname derived from latin_name "Stultus")
        assert character is not None
        assert character.db_key == "Test Fatui"

        # Verify trait values were created
        trait_values = CharacterTraitValue.objects.filter(character=character)
        assert trait_values.count() == 9

        # Verify specific values directly from database
        strength_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["strength"]
        )
        # Debug: print actual value if assertion fails
        if strength_value.value != 30:
            print(f"Expected strength=30, got {strength_value.value}")
            trait_values = CharacterTraitValue.objects.filter(character=character)
            all_values = [(v.trait.name, v.value) for v in trait_values]
            print(f"All values: {all_values}")
        assert strength_value.value == 30

        agility_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["agility"]
        )
        assert agility_value.value == 30

        willpower_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["willpower"]
        )
        assert willpower_value.value == 30

    def test_finalize_bulk_creates_trait_values(self):
        """Test that finalization uses bulk operations (no N+1)."""
        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            },
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
            stats={
                "strength": 30,  # 3 points
                "agility": 30,  # 3 points
                "stamina": 30,  # 3 points
                "charm": 20,  # 2 points
                "presence": 20,  # 2 points
                "perception": 20,  # 2 points
                "intellect": 20,  # 2 points
                "wits": 30,  # 3 points
                "willpower": 30,  # 3 points
            },
            first_name="Sheet Test",
        )

        character = finalize_character(draft, add_to_roster=True)

        # Verify character sheet exists
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet is not None

        # Verify stats were created with correct values
        strength_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["strength"]
        )
        assert strength_value.value == 30

        willpower_value = CharacterTraitValue.objects.get(
            character=character, trait=self.stats["willpower"]
        )
        assert willpower_value.value == 30

    def test_finalize_converts_unspent_cg_points_to_xp(self):
        """Test that unspent CG points are converted to locked XP."""
        from world.progression.models import CharacterXP, CharacterXPTransaction

        stats = {
            "strength": 30,
            "agility": 30,
            "stamina": 30,
            "charm": 20,
            "presence": 20,
            "perception": 20,
            "intellect": 20,
            "wits": 30,
            "willpower": 30,
        }
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

        stats = {
            "strength": 30,
            "agility": 30,
            "stamina": 30,
            "charm": 20,
            "presence": 20,
            "perception": 20,
            "intellect": 20,
            "wits": 30,
            "willpower": 30,
        }
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
                "stats": {
                    "strength": 30,
                    "agility": 30,
                    "stamina": 30,
                    "charm": 20,
                    "presence": 20,
                    "perception": 20,
                    "intellect": 20,
                    "wits": 30,
                    "willpower": 30,
                },
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

        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.heritage == sleeper_heritage

    def test_finalize_defaults_to_normal_heritage_when_beginnings_has_none(self):
        """When Beginnings has no heritage FK, fall back to 'Normal'."""
        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
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

        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
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

        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
        character = finalize_character(draft, add_to_roster=True)
        assert not CharacterForm.objects.filter(character=character).exists()

    def test_finalize_skips_invalid_form_trait_names(self):
        """Invalid trait names in form_traits are silently skipped."""
        from world.forms.models import CharacterForm, FormType

        hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        black_option = FormTraitOptionFactory(trait=hair_trait, name="black", display_name="Black")

        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
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

        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
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
        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
        draft.draft_data["quote"] = "Steel remembers what flesh forgets."
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = CharacterSheet.objects.get(character=character)
        assert sheet.quote == "Steel remembers what flesh forgets."

    def test_finalize_saves_concept_from_draft_data(self):
        """Concept from draft_data should be saved to CharacterSheet."""
        draft = self._create_complete_draft(
            stats={
                "strength": 30,
                "agility": 30,
                "stamina": 30,
                "charm": 20,
                "presence": 20,
                "perception": 20,
                "intellect": 20,
                "wits": 30,
                "willpower": 30,
            }
        )
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
        from world.mechanics.models import ModifierCategory, ModifierType

        cls.goal_cat, _ = ModifierCategory.objects.get_or_create(name="goal")
        cls.standing, _ = ModifierType.objects.get_or_create(name="Standing", category=cls.goal_cat)
        cls.drives, _ = ModifierType.objects.get_or_create(name="Drives", category=cls.goal_cat)
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
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory

        cls.stat_category = ModifierCategoryFactory(name="distinction_test_stat")
        cls.strength_modifier = ModifierTypeFactory(
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

        char_distinctions = CharacterDistinction.objects.filter(character=character)
        assert char_distinctions.count() == 2

        simple = char_distinctions.get(distinction=self.simple_distinction)
        assert simple.rank == 1
        assert simple.origin == "character_creation"

        ranked = char_distinctions.get(distinction=self.ranked_distinction)
        assert ranked.rank == 2
        assert ranked.notes == "Test note"

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
            source__distinction_effect__target=self.strength_modifier,
        )
        assert modifier.value == 10  # 5 * rank 2

    def test_no_distinctions_created_when_draft_has_none(self):
        """No distinctions created if draft_data has no distinctions."""
        from world.distinctions.models import CharacterDistinction

        draft = self._create_complete_draft()
        draft.draft_data.pop("distinctions", None)
        draft.save()

        character = finalize_character(draft, add_to_roster=True)

        assert not CharacterDistinction.objects.filter(character=character).exists()

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

        char_distinctions = CharacterDistinction.objects.filter(character=character)
        assert char_distinctions.count() == 1
        assert char_distinctions.first().distinction == self.simple_distinction


class FinalizeMagicDataReincarnationTest(TestCase):
    """Test that finalize_magic_data creates Reincarnation for Old Soul gifts."""

    @classmethod
    def setUpTestData(cls):
        from world.distinctions.factories import DistinctionFactory

        cls.old_soul = DistinctionFactory(
            name="Old Soul",
            slug="old-soul-finalize-test",
        )

    def test_reincarnation_created_for_old_soul_gift(self):
        """finalize_magic_data creates Reincarnation when gift has source_distinction."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import Reincarnation

        draft = self._create_draft_with_magic()
        # Create an Atavism DraftGift with source_distinction
        draft_gift = DraftGiftFactory(
            draft=draft,
            source_distinction=self.old_soul,
            name="Atavism",
            max_techniques=1,
            bonus_resonance_value=0,
        )
        # Add a technique to the atavism gift so convert_to_real_version works
        DraftTechniqueFactory(gift=draft_gift)
        sheet = CharacterSheetFactory()

        finalize_magic_data(draft, sheet)

        reincarnation = Reincarnation.objects.filter(character=sheet).first()
        self.assertIsNotNone(reincarnation)
        self.assertEqual(reincarnation.gift.name, "Atavism")

    def test_no_reincarnation_for_normal_gift(self):
        """finalize_magic_data does NOT create Reincarnation for normal gifts."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import Reincarnation

        draft = self._create_draft_with_magic()
        sheet = CharacterSheetFactory()

        finalize_magic_data(draft, sheet)

        self.assertFalse(Reincarnation.objects.filter(character=sheet).exists())

    def test_resonance_bonus_applied(self):
        """Bonus resonance value is applied to CharacterResonanceTotal at finalization."""
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterResonanceTotal

        resonance_type = ResonanceModifierTypeFactory(name="test-bonus-resonance")
        draft = self._create_draft_with_magic()
        draft_gift = DraftGiftFactory(
            draft=draft,
            source_distinction=self.old_soul,
            name="Atavism",
            bonus_resonance_value=25,
        )
        draft_gift.resonances.add(resonance_type)
        DraftTechniqueFactory(gift=draft_gift)
        sheet = CharacterSheetFactory()

        finalize_magic_data(draft, sheet)

        total = CharacterResonanceTotal.objects.filter(
            character=sheet,
            resonance=resonance_type,
        ).first()
        self.assertIsNotNone(total)
        self.assertEqual(total.total, 25)

    def _create_draft_with_magic(self):
        """Create a draft that has a base gift with technique (for finalize to process)."""
        from evennia_extensions.factories import AccountFactory
        from world.character_creation.factories import CharacterDraftFactory

        draft = CharacterDraftFactory(account=AccountFactory())
        # Create the base gift with a technique
        base_gift = DraftGiftFactory(draft=draft, name="Base Gift")
        DraftTechniqueFactory(gift=base_gift)
        # Create a motif and ritual so finalization doesn't fail
        DraftMotifFactory(draft=draft)
        DraftAnimaRitualFactory(draft=draft)
        return draft


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
