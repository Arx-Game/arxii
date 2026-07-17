"""End-to-end regression for #1306: a CG-finalized character can cast a starter
technique standalone, and the cast rolls the CASTER'S per-character magic check.

Issue #1306: standalone casts previously raised "Technique is not castable
standalone" because starter-catalog techniques carried no action_template, and
even once they did, the cast rolled the template's fallback check rather than the
character's personal anima-ritual check.

This suite proves both halves of the fix on a real finalized character:

1. ``request_technique_cast`` for a self-target cast RESOLVES (no ValidationError).
2. The resolution rolls ``get_character_cast_check(character)`` — the per-character
   CheckType named ``character_magic_check_type_name(sheet)`` — NOT the shared
   "Technique Cast" fallback. Verified by spying the ``check_type`` argument passed
   into ``start_action_resolution``.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from evennia import create_object
from evennia.accounts.models import AccountDB

from world.character_creation.models import Beginnings, CharacterDraft, StartingArea
from world.character_creation.services import finalize_character
from world.character_sheets.models import CharacterSheet, Gender
from world.classes.factories import PathFactory
from world.classes.models import PathStage
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
from world.magic.models import CharacterTechnique
from world.magic.seeds_cast import TECHNIQUE_CAST_CHECK_TYPE_NAME, get_standalone_cast_template
from world.magic.seeds_checks import character_magic_check_type_name
from world.magic.services.anima import get_character_cast_check
from world.realms.models import Realm
from world.roster.models import Roster
from world.scenes import cast_services
from world.scenes.cast_services import request_technique_cast
from world.scenes.factories import PersonaFactory, SceneFactory
from world.skills.factories import SkillFactory
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CharacterTraitValue, Trait, TraitType

_STATS = {
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


class CastUsesPerCharacterCheckTests(TestCase):
    """A finalized character casts a starter technique using their personal check."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Full check system (outcomes/charts/ranks + stat traits) so perform_check
        # can resolve and so the cast pipeline runs end-to-end.
        CheckSystemSetupFactory.create()
        for stat_name in _STATS:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={"trait_type": TraitType.STAT, "description": stat_name},
            )
        cls.anima_stat = Trait.objects.get(name="willpower")
        Roster.objects.get_or_create(name="Available Characters")

        realm = Realm.objects.create(name="CastPC Realm", description="Test")
        cls.area = StartingArea.objects.create(
            name="CastPC Area",
            description="Test",
            realm=realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        cls.species = Species.objects.create(name="CastPC Species", description="Test")
        cls.gender, _ = Gender.objects.get_or_create(
            key="castpc_gender",
            defaults={"display_name": "CastPC Gender"},
        )
        cls.tarot = TarotCard.objects.create(
            name="CastPC Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=97,
            latin_name="FatuiPC",
        )
        cls.beginnings = Beginnings.objects.create(
            name="CastPC Beginnings",
            description="Test",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        cls.beginnings.allowed_species.add(cls.species)
        cls.height_band = HeightBand.objects.create(
            name="castpc_band",
            display_name="CastPC Band",
            min_inches=6000,
            max_inches=6100,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        cls.build = Build.objects.create(
            name="castpc_build",
            display_name="CastPC Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )
        cls.path = PathFactory(name="CastPC Path", stage=PathStage.PROSPECT, minimum_level=1)
        TechniqueStyleFactory()
        EffectTypeFactory()
        ResonanceFactory()
        cls.resonance = ResonanceFactory()
        cls.tradition = TraditionFactory()
        # Skill so provision_player_anima_ritual finds a default and doesn't skip.
        cls.skill = SkillFactory(trait__name="CastPCRitualism")

        # Gift-stage draft contract (#2426): a catalog Gift + Technique the player
        # picks, granted for this (path, tradition) via PathGiftGrant/TraditionGiftGrant.
        # The technique carries the shared standalone cast template so the
        # finalized CharacterTechnique is immediately castable.
        cls.gift = GiftFactory()
        cls.gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(
            gift=cls.gift, action_template=get_standalone_cast_template()
        )
        path_grant = PathGiftGrantFactory(path=cls.path, gift=cls.gift)
        path_grant.starter_techniques.set([cls.technique])
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)

    def setUp(self) -> None:
        CharacterSheet.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

    def _finalize_caster(self) -> tuple[object, CharacterSheet, AccountDB]:
        """Run a full CG finalization, returning (character, sheet, account).

        Sets ``character.db_account`` to model the logged-in/runtime state — the
        cast-check resolver keys on ``character.db_account`` and ``finalize_character``
        does not puppet the character (Task 3 finding).
        """
        account = AccountDB.objects.create(username=f"castpc_run_{id(self)}")
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
            height_inches=6050,
            build=self.build,
            draft_data={
                "first_name": "CastPC",
                "description": "A test character",
                "stats": _STATS,
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
        # Model the runtime/logged-in state: the resolver queries
        # author_account=character.db_account.
        character.db_account = account
        character.save(update_fields=["db_account"])
        return character, sheet, account

    def test_finalized_character_casts_with_personal_check(self) -> None:
        """A CG-finalized character can self-cast their starter technique, and the
        cast rolls their per-character magic check rather than the fallback."""
        character, sheet, _account = self._finalize_caster()

        # The catalog pick finalized into a linked CharacterTechnique with the
        # default cast template.
        char_technique = CharacterTechnique.objects.filter(character=sheet).first()
        self.assertIsNotNone(
            char_technique, "Finalized character should know a starter-catalog technique"
        )
        technique = char_technique.technique
        self.assertIsNotNone(
            technique.action_template_id,
            "Starter-catalog technique must carry the default cast template (Task 6)",
        )

        # The personal check exists and is what we expect the cast to roll.
        personal_check = get_character_cast_check(character)
        self.assertIsNotNone(
            personal_check, "Finalized character must have a per-character cast check"
        )
        expected_name = character_magic_check_type_name(sheet)
        self.assertEqual(personal_check.name, expected_name)

        # A persona on this finalized sheet, in an active scene, to cast through.
        room = create_object("typeclasses.rooms.Room", key="CastPC Room", nohome=True)
        scene = SceneFactory(location=room)
        caster_persona = PersonaFactory(character_sheet=sheet)

        # Spy the real start_action_resolution (``wraps`` keeps the cast resolving)
        # to capture the check_type forwarded — proving the per-character override
        # was applied rather than the template fallback.
        with patch.object(
            cast_services,
            "start_action_resolution",
            wraps=cast_services.start_action_resolution,
        ) as spy:
            # CORE REGRESSION: a self-target cast must RESOLVE (no
            # "Technique is not castable standalone" ValidationError).
            cast_result = request_technique_cast(
                scene=scene,
                initiator_persona=caster_persona,
                target_persona=None,
                technique=technique,
            )

        self.assertIsNotNone(cast_result)
        self.assertIsNotNone(cast_result.result, "Immediate self-cast should return a result")

        # The cast rolled the CASTER'S per-character check, not the shared fallback.
        spy.assert_called_once()
        rolled = spy.call_args.kwargs.get("check_type")
        self.assertIsNotNone(rolled, "cast must forward an explicit per-character check_type")
        self.assertEqual(rolled.pk, personal_check.pk)
        self.assertEqual(rolled.name, expected_name)
        self.assertNotEqual(rolled.name, TECHNIQUE_CAST_CHECK_TYPE_NAME)
