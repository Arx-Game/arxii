from decimal import Decimal

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.models import Beginnings, StartingArea
from world.character_creation.services import finalize_character
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet, Gender
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.forms.models import Build, HeightBand
from world.magic.constants import RitualExecutionKind
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
from world.magic.models.ritual_check_config import RitualCheckConfig
from world.magic.models.rituals import Ritual
from world.magic.seeds_cast import get_standalone_cast_template
from world.magic.seeds_checks import (
    MAGIC_CHECK_CATEGORY_NAME,
    character_magic_check_type_name,
    ensure_character_magic_check_type,
)
from world.realms.models import Realm
from world.roster.models import Roster
from world.skills.factories import SkillFactory
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.factories import TraitFactory
from world.traits.models import CharacterTraitValue, Trait, TraitType


class CharacterMagicCheckTypeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.other = CharacterSheetFactory()
        cls.willpower = TraitFactory(name="willpower", trait_type=TraitType.STAT)
        cls.skill = SkillFactory(trait__name="ritualism")

    def test_synthesizes_per_character_check_weighted_on_stat_and_skill(self):
        ct = ensure_character_magic_check_type(self.sheet, stat=self.willpower, skill=self.skill)
        self.assertEqual(ct.category.name, MAGIC_CHECK_CATEGORY_NAME)
        trait_names = {t.trait.name for t in ct.traits.all()}
        self.assertEqual(trait_names, {"willpower", "ritualism"})
        self.assertTrue(ct.aspects.filter(aspect__name="Arcana").exists())

    def test_distinct_rows_per_character_and_idempotent(self):
        a1 = ensure_character_magic_check_type(self.sheet, stat=self.willpower, skill=self.skill)
        a2 = ensure_character_magic_check_type(self.sheet, stat=self.willpower, skill=self.skill)
        b = ensure_character_magic_check_type(self.other, stat=self.willpower, skill=self.skill)
        self.assertEqual(a1.pk, a2.pk)
        self.assertNotEqual(a1.pk, b.pk)


_PROVISION_STATS = {
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


class ProvisionUsesPerCharacterCheckTests(TestCase):
    """Provisioned anima ritual's check_config points to the per-character CheckType."""

    @classmethod
    def setUpTestData(cls):
        for stat_name in _PROVISION_STATS:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={"trait_type": TraitType.STAT, "description": stat_name},
            )
        Roster.objects.get_or_create(name="Available Characters")

        realm = Realm.objects.create(name="ProvisionCheck Realm", description="Test")
        area = StartingArea.objects.create(
            name="ProvisionCheck Area",
            description="Test",
            realm=realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        species = Species.objects.create(name="ProvisionCheck Species", description="Test")
        gender, _ = Gender.objects.get_or_create(
            key="provisioncheck_gender",
            defaults={"display_name": "ProvisionCheck Gender"},
        )
        tarot = TarotCard.objects.create(
            name="ProvCheck Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=99,
            latin_name="Fatui",
        )
        beginnings = Beginnings.objects.create(
            name="ProvisionCheck Beginnings",
            description="Test",
            starting_area=area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        beginnings.allowed_species.add(species)
        height_band = HeightBand.objects.create(
            name="pc_band",
            display_name="ProvisionCheck Band",
            min_inches=4000,
            max_inches=4100,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        build = Build.objects.create(
            name="pc_build",
            display_name="ProvisionCheck Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )
        path = PathFactory(name="ProvisionCheck Path", stage=PathStage.PROSPECT, minimum_level=1)
        TechniqueStyleFactory()
        EffectTypeFactory()
        ResonanceFactory()
        cls.resonance = ResonanceFactory()
        tradition = TraditionFactory()

        # Skill needed so provision_player_anima_ritual doesn't log + skip.
        cls.skill = SkillFactory(trait__name="PCProvisionMelee")

        # Gift-stage draft contract (#2426): a catalog Gift + Technique the player
        # picks, granted for this (path, tradition) via PathGiftGrant/TraditionGiftGrant.
        gift = GiftFactory()
        gift.resonances.add(cls.resonance)
        technique = TechniqueFactory(gift=gift, action_template=get_standalone_cast_template())
        path_grant = PathGiftGrantFactory(path=path, gift=gift)
        path_grant.starter_techniques.set([technique])
        TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        cls.anima_stat = Trait.objects.get(name="willpower")

        cls.area = area
        cls.beginnings = beginnings
        cls.species = species
        cls.gender = gender
        cls.tarot = tarot
        cls.height_band = height_band
        cls.build = build
        cls.path = path
        cls.tradition = tradition
        cls.gift = gift
        cls.technique = technique

    def setUp(self):
        CharacterSheet.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

    def test_provisioned_ritual_uses_per_character_check_type(self):
        """provision_player_anima_ritual wires check_type to the per-character CheckType."""
        from world.character_creation.models import CharacterDraft

        account = AccountDB.objects.create(username=f"provcheck_run_{id(self)}")
        draft = CharacterDraft.objects.create(
            account=account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            selected_tradition=self.tradition,
            age=25,
            height_band=self.height_band,
            height_inches=4050,
            build=self.build,
            draft_data={
                "first_name": "ProvCheck",
                "description": "A test character",
                "stats": _PROVISION_STATS,
                "lineage_is_orphan": True,
                "tarot_card_name": self.tarot.name,
                "tarot_reversed": False,
                "traits_complete": True,
                "selected_gift_id": self.gift.id,
                "selected_technique_ids": [self.technique.id],
                "selected_gift_resonance_id": self.resonance.id,
                "anima_check_stat_id": self.anima_stat.id,
                "anima_check_skill_id": self.skill.id,
                "skills": {str(self.skill.pk): 20},
            },
        )

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        ritual = Ritual.objects.filter(
            author_account=account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        ).first()
        self.assertIsNotNone(ritual, "Expected a SCENE_ACTION Ritual authored by the account")

        config = RitualCheckConfig.objects.filter(ritual=ritual).first()
        self.assertIsNotNone(config)
        self.assertIsNotNone(config.check_type)
        self.assertEqual(
            config.check_type.name,
            character_magic_check_type_name(sheet),
        )


class GetCharacterCastCheckTests(TestCase):
    """Tests for get_character_cast_check resolver."""

    @classmethod
    def setUpTestData(cls):
        for stat_name in _PROVISION_STATS:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={"trait_type": TraitType.STAT, "description": stat_name},
            )
        Roster.objects.get_or_create(name="Available Characters")

        realm = Realm.objects.create(name="CastCheck Realm", description="Test")
        area = StartingArea.objects.create(
            name="CastCheck Area",
            description="Test",
            realm=realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        species = Species.objects.create(name="CastCheck Species", description="Test")
        gender, _ = Gender.objects.get_or_create(
            key="castcheck_gender",
            defaults={"display_name": "CastCheck Gender"},
        )
        tarot = TarotCard.objects.create(
            name="CastCheck Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=98,
            latin_name="Fatui2",
        )
        beginnings = Beginnings.objects.create(
            name="CastCheck Beginnings",
            description="Test",
            starting_area=area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        beginnings.allowed_species.add(species)
        height_band = HeightBand.objects.create(
            name="cc_band",
            display_name="CastCheck Band",
            min_inches=5000,
            max_inches=5100,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        build = Build.objects.create(
            name="cc_build",
            display_name="CastCheck Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )
        path = PathFactory(name="CastCheck Path", stage=PathStage.PROSPECT, minimum_level=1)
        TechniqueStyleFactory()
        EffectTypeFactory()
        ResonanceFactory()
        cls.resonance = ResonanceFactory()
        tradition = TraditionFactory()
        cls.skill = SkillFactory(trait__name="CCProvisionMelee")

        # Gift-stage draft contract (#2426): a catalog Gift + Technique the player
        # picks, granted for this (path, tradition) via PathGiftGrant/TraditionGiftGrant.
        gift = GiftFactory()
        gift.resonances.add(cls.resonance)
        technique = TechniqueFactory(gift=gift, action_template=get_standalone_cast_template())
        path_grant = PathGiftGrantFactory(path=path, gift=gift)
        path_grant.starter_techniques.set([technique])
        TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        cls.anima_stat = Trait.objects.get(name="willpower")

        cls.area = area
        cls.beginnings = beginnings
        cls.species = species
        cls.gender = gender
        cls.tarot = tarot
        cls.height_band = height_band
        cls.build = build
        cls.path = path
        cls.tradition = tradition
        cls.gift = gift
        cls.technique = technique

    def setUp(self):
        CharacterSheet.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

    def test_returns_none_without_ritual(self):
        from world.magic.services.anima import get_character_cast_check

        sheet = CharacterSheetFactory()
        self.assertIsNone(get_character_cast_check(sheet.character))

    def test_returns_per_character_check_after_provision(self):
        from world.character_creation.models import CharacterDraft
        from world.magic.services.anima import get_character_cast_check

        account = AccountDB.objects.create(username=f"castcheck_run_{id(self)}")
        draft = CharacterDraft.objects.create(
            account=account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            selected_tradition=self.tradition,
            age=25,
            height_band=self.height_band,
            height_inches=5050,
            build=self.build,
            draft_data={
                "first_name": "CastCheck",
                "description": "A test character",
                "stats": _PROVISION_STATS,
                "lineage_is_orphan": True,
                "tarot_card_name": self.tarot.name,
                "tarot_reversed": False,
                "traits_complete": True,
                "selected_gift_id": self.gift.id,
                "selected_technique_ids": [self.technique.id],
                "selected_gift_resonance_id": self.resonance.id,
                "anima_check_stat_id": self.anima_stat.id,
                "anima_check_skill_id": self.skill.id,
                "skills": {str(self.skill.pk): 20},
            },
        )

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        # Puppet the character to the account so db_account is set,
        # mirroring the runtime path where get_character_anima_ritual queries
        # author_account=character.db_account.
        character.db_account = account
        character.save(update_fields=["db_account"])

        ct = get_character_cast_check(sheet.character)
        self.assertIsNotNone(ct)
        self.assertEqual(ct.name, character_magic_check_type_name(sheet))


class ResolveCastCheckTypeTests(TestCase):
    """Precedence: personal check -> template check -> None (ADR-0096)."""

    @classmethod
    def setUpTestData(cls):
        from actions.factories import ActionTemplateFactory

        cls.sheet = CharacterSheetFactory()
        cls.template = ActionTemplateFactory()

    def test_unprovisioned_falls_back_to_template_check(self):
        from world.magic.services.anima import resolve_cast_check_type

        ct = resolve_cast_check_type(self.sheet.character, self.template)
        self.assertEqual(ct, self.template.check_type)

    def test_no_template_and_unprovisioned_returns_none(self):
        from world.magic.services.anima import resolve_cast_check_type

        self.assertIsNone(resolve_cast_check_type(self.sheet.character, None))

    def test_provisioned_personal_check_wins_over_template(self):
        from world.magic.factories import RitualCheckConfigFactory
        from world.magic.services.anima import resolve_cast_check_type

        account = AccountDB.objects.create(username=f"resolve_cc_{id(self)}")
        ritual = Ritual.objects.create(
            name=f"resolve_cc_ritual_{id(self)}",
            author_account=account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        config = RitualCheckConfigFactory(ritual=ritual)
        self.sheet.character.db_account = account
        self.sheet.character.save(update_fields=["db_account"])

        ct = resolve_cast_check_type(self.sheet.character, self.template)
        self.assertEqual(ct, config.check_type)
        self.assertNotEqual(ct, self.template.check_type)
