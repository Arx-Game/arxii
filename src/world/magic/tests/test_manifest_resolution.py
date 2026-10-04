"""A manifesting technique brings the caster's bound entity into the fight (#4118)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from evennia.utils.create import create_object

from typeclasses.companions import CompanionObject
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ActionCategory,
    CombatAllegiance,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    OpponentTierTemplateFactory,
)
from world.combat.models import CombatOpponent, CombatRoundAction
from world.combat.services import CombatTechniqueResolver
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterManifestationFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueManifestOptionFactory,
)
from world.magic.services.effect_handlers import manifest_bound_entity
from world.magic.types.power_ledger import PowerLedger
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence

_ADD_OPPONENT = "world.combat.services.add_opponent"


class ManifestResolutionBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK)
        OpponentTierTemplateFactory(tier=OpponentTier.BOSS, base_health=200)
        cls.encounter = CombatEncounterFactory(round_number=1)
        cls.sheet = CharacterSheetFactory()
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter, character_sheet=cls.sheet
        )
        cls.technique = TechniqueFactory(
            gift=GiftFactory(), effect_type=EffectTypeFactory(name="Attack", base_power=20)
        )
        cls.avatar_sheet = CharacterSheetFactory()
        cls.being = WorshippedBeingFactory(avatar_sheet=cls.avatar_sheet)

    def _bond_being(self, being=None):
        return DevotionStandingFactory(
            character_sheet=self.sheet,
            being=being or self.being,
            valence=PatronageValence.DEVOTIONAL,
        )

    def _manifest_being(self, tier=OpponentTier.BOSS, being=None):
        option = TechniqueManifestOptionFactory(
            technique=self.technique, being=being or self.being, tier=tier
        )
        return CharacterManifestationFactory(
            character=self.sheet, technique=self.technique, option=option
        )

    def _resolver(self):
        action, _ = CombatRoundAction.objects.get_or_create(
            participant=self.participant,
            round_number=1,
            defaults={
                "focused_category": ActionCategory.PHYSICAL,
                "focused_action": self.technique,
                "effort_level": EffortLevel.MEDIUM,
            },
        )
        return CombatTechniqueResolver(
            participant=self.participant,
            action=action,
            pull_flat_bonus=0,
            fatigue_category=ActionCategory.PHYSICAL,
            offense_check_type=CheckTypeFactory(),
            offense_check_fn=None,
        )

    def _cast(self):
        with patch("world.combat.services.perform_check") as perform:
            perform.return_value = MagicMock(success_level=2)
            return self._resolver()(power=5, ledger=PowerLedger(entries=(), total=5))

    def _allies(self):
        return CombatOpponent.objects.filter(
            encounter=self.encounter, allegiance=CombatAllegiance.ALLY
        )


class ManifestBeingTests(ManifestResolutionBase):
    def test_being_option_brings_avatar_in_as_ally(self):
        self._bond_being()
        self._manifest_being()
        self._cast()
        opponent = self._allies().get()
        self.assertEqual(opponent.objectdb, self.avatar_sheet.character)
        self.assertEqual(opponent.summoned_by, self.sheet)
        self.assertEqual(opponent.tier, OpponentTier.BOSS)
        self.assertIsNone(opponent.bond_expires_round)

    def test_no_manifestation_row_adds_nothing(self):
        self._bond_being()
        TechniqueManifestOptionFactory(technique=self.technique, being=self.being)
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_lapsed_patronage_adds_nothing(self):
        standing = self._bond_being()
        self._manifest_being()
        standing.released_at = timezone.now()
        standing.save(update_fields=["released_at"])
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_being_without_avatar_adds_nothing(self):
        being = WorshippedBeingFactory(avatar_sheet=None)
        self._bond_being(being)
        self._manifest_being(being=being)
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_caster_no_longer_active_in_encounter_returns_none(self):
        self._bond_being()
        self._manifest_being()
        self.participant.status = ParticipantStatus.FLED
        self.participant.save(update_fields=["status"])
        result = manifest_bound_entity(participant=self.participant, technique=self.technique)
        self.assertIsNone(result)
        self.assertFalse(self._allies().exists())

    def test_second_cast_does_not_duplicate_active_avatar(self):
        self._bond_being()
        self._manifest_being()
        self._cast()
        self._cast()
        self.assertEqual(self._allies().count(), 1)

    def test_defeated_avatar_is_not_re_added(self):
        self._bond_being()
        self._manifest_being()
        self._cast()
        avatar_row = self._allies().get()
        avatar_row.status = OpponentStatus.DEFEATED
        avatar_row.save(update_fields=["status"])
        self._cast()
        rows = CombatOpponent.objects.filter(
            encounter=self.encounter, objectdb=self.avatar_sheet.character
        )
        self.assertEqual(rows.count(), 1)

    def test_technique_without_options_is_untouched(self):
        with patch(_ADD_OPPONENT) as add:
            self._cast()
        add.assert_not_called()


class ManifestCompanionTests(ManifestResolutionBase):
    def _manifest_companion(self, **companion_overrides):
        archetype = CompanionArchetypeFactory()
        companion = CompanionFactory(owner=self.sheet, archetype=archetype, **companion_overrides)
        companion.objectdb = create_object(CompanionObject, key=companion.name, nohome=True)
        companion.save(update_fields=["objectdb"])
        option = TechniqueManifestOptionFactory(
            technique=self.technique, being=None, archetype=archetype
        )
        CharacterManifestationFactory(
            character=self.sheet, technique=self.technique, option=option, companion=companion
        )
        return companion

    def test_archetype_option_materializes_companion(self):
        companion = self._manifest_companion()
        self._cast()
        opponent = self._allies().get()
        self.assertEqual(opponent.name, companion.name)
        self.assertEqual(opponent.allegiance, CombatAllegiance.ALLY)

    def test_released_companion_adds_nothing(self):
        companion = self._manifest_companion()
        companion.released_at = timezone.now()
        companion.save(update_fields=["released_at"])
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_companion_without_objectdb_adds_nothing(self):
        companion = self._manifest_companion()
        companion.objectdb = None
        companion.save(update_fields=["objectdb"])
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_second_cast_does_not_duplicate_companion(self):
        self._manifest_companion()
        self._cast()
        self._cast()
        self.assertEqual(self._allies().count(), 1)
