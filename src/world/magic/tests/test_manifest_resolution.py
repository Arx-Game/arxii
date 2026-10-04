"""A manifesting technique brings the caster's bound entity into the fight (#4118)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from evennia.utils.create import create_object

from typeclasses.companions import CompanionObject
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import place_in_position, position_of
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
    CombatOpponentFactory,
    CombatParticipantFactory,
    OpponentTierTemplateFactory,
)
from world.combat.models import CombatOpponent, CombatRoundAction
from world.combat.services import CombatTechniqueResolver
from world.companions.defeat_content import SAVAGED_CONDITION_NAME
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.conditions.models import ConditionCategory, ConditionTemplate
from world.conditions.services import apply_condition
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
from world.scenes.constants import RoundStatus
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence

_ADD_OPPONENT = "world.combat.services.add_opponent"


class ManifestResolutionBase(TestCase):
    def setUp(self):
        # Setup places bodies with ``location =``, not ``move_to``: a ``move_to`` here
        # leaves state behind that breaks later modules' Evennia object creation.
        super().setUp()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK)
        OpponentTierTemplateFactory(tier=OpponentTier.BOSS, base_health=200)
        self.encounter = CombatEncounterFactory(round_number=1)
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        self.technique = TechniqueFactory(
            gift=GiftFactory(), effect_type=EffectTypeFactory(name="Attack", base_power=20)
        )
        self.avatar_sheet = CharacterSheetFactory()
        self.being = WorshippedBeingFactory(avatar_sheet=self.avatar_sheet)

        self.sheet.character.location = self.encounter.room

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

    def _cast(self, success_level=2):
        with patch("world.combat.services.perform_check") as perform:
            perform.return_value = MagicMock(success_level=success_level)
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


class ManifestFailedRollTests(ManifestResolutionBase):
    def test_failed_roll_manifests_nothing(self):
        self._bond_being()
        self._manifest_being()
        self._cast(success_level=0)
        self.assertFalse(self._allies().exists())

    def test_botched_roll_manifests_nothing(self):
        self._bond_being()
        self._manifest_being()
        self._cast(success_level=-1)
        self.assertFalse(self._allies().exists())

    def test_minimal_success_manifests(self):
        self._bond_being()
        self._manifest_being()
        self._cast(success_level=1)
        self.assertEqual(self._allies().count(), 1)


class ManifestIntegrityTests(ManifestResolutionBase):
    def test_option_of_another_technique_manifests_nothing(self):
        self._bond_being()
        foreign_option = TechniqueManifestOptionFactory(being=self.being, tier=OpponentTier.BOSS)
        CharacterManifestationFactory(
            character=self.sheet,
            technique=self.technique,
            option=foreign_option,
        )
        self._cast()
        self.assertFalse(self._allies().exists())


class ManifestAvatarElsewhereTests(ManifestResolutionBase):
    def setUp(self):
        super().setUp()
        self._bond_being()
        self._manifest_being()
        self.avatar = self.avatar_sheet.character
        self.other_encounter = CombatEncounterFactory(round_number=1)
        CombatOpponentFactory(
            encounter=self.other_encounter,
            objectdb_id=self.avatar.pk,
            objectdb_is_ephemeral=False,
        )

    def test_avatar_in_another_running_fight_is_not_pulled_out(self):
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_avatar_in_a_completed_fight_arrives(self):
        self.other_encounter.status = RoundStatus.COMPLETED
        self.other_encounter.save(update_fields=["status"])
        self._cast()
        self.assertEqual(self._allies().count(), 1)

    def test_avatar_whose_other_row_is_defeated_arrives(self):
        row = CombatOpponent.objects.get(encounter=self.other_encounter)
        row.status = OpponentStatus.DEFEATED
        row.save(update_fields=["status"])
        self._cast()
        self.assertEqual(self._allies().count(), 1)


class ManifestMoveDoesNotLandTests(ManifestResolutionBase):
    def test_avatar_that_cannot_be_moved_manifests_nothing(self):
        self._bond_being()
        self._manifest_being()
        avatar = self.avatar_sheet.character
        avatar.location = PositionFactory().room
        with patch.object(type(avatar), "move_to", return_value=False):
            self._cast()
        self.assertFalse(self._allies().exists())


class ManifestPositionedCasterTests(ManifestResolutionBase):
    """The caster stands on a real Position, so the arriving avatar must share the room."""

    def setUp(self):
        super().setUp()
        self.room = self.encounter.room
        self.position = PositionFactory(room=self.room)
        self.caster = self.sheet.character
        self.caster.location = self.room
        place_in_position(self.caster, self.position)
        self.avatar = self.avatar_sheet.character
        self._bond_being()
        self._manifest_being()

    def _assert_arrived(self):
        opponent = self._allies().get()
        self.assertEqual(opponent.objectdb, self.avatar)
        self.assertEqual(self.avatar.db_location, self.room)
        self.assertEqual(position_of(self.avatar), self.position)

    def test_avatar_with_no_location_arrives(self):
        self.avatar.location = None
        self._cast()
        self._assert_arrived()

    def test_avatar_in_other_room_is_moved_in(self):
        self.avatar.location = PositionFactory().room
        self._cast()
        self._assert_arrived()

    def test_avatar_already_in_room_arrives(self):
        self.avatar.location = self.room
        self._cast()
        self._assert_arrived()

    def test_caster_without_location_adds_nothing(self):
        self.caster.location = None
        result = manifest_bound_entity(participant=self.participant, technique=self.technique)
        self.assertIsNone(result)
        self.assertFalse(self._allies().exists())


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

    def _positioned_caster(self):
        room = self.encounter.room
        position = PositionFactory(room=room)
        self.sheet.character.location = room
        place_in_position(self.sheet.character, position)
        return room, position

    def _assert_companion_arrived(self, companion, room, position):
        opponent = self._allies().get()
        self.assertEqual(opponent.objectdb, companion.objectdb)
        self.assertEqual(companion.objectdb.db_location, room)
        self.assertEqual(position_of(companion.objectdb), position)

    def test_companion_with_no_location_arrives_beside_positioned_caster(self):
        companion = self._manifest_companion()
        room, position = self._positioned_caster()
        self._cast()
        self._assert_companion_arrived(companion, room, position)

    def test_companion_in_other_room_is_moved_in(self):
        companion = self._manifest_companion()
        room, position = self._positioned_caster()
        companion.objectdb.location = PositionFactory().room
        self._cast()
        self._assert_companion_arrived(companion, room, position)

    def test_companion_already_in_room_arrives(self):
        companion = self._manifest_companion()
        room, position = self._positioned_caster()
        companion.objectdb.location = room
        self._cast()
        self._assert_companion_arrived(companion, room, position)

    def test_caster_without_location_manifests_no_companion(self):
        self._manifest_companion()
        self.sheet.character.location = None
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_companion_that_cannot_be_moved_manifests_nothing(self):
        companion = self._manifest_companion()
        self._positioned_caster()
        companion.objectdb.location = PositionFactory().room
        with patch.object(type(companion.objectdb), "move_to", return_value=False):
            self._cast()
        self.assertFalse(self._allies().exists())

    def test_savaged_companion_manifests_nothing(self):
        companion = self._manifest_companion()
        category = ConditionCategory.objects.create(
            name="Companion Injury", description="Test category text."
        )
        savaged = ConditionTemplate.objects.create(
            name=SAVAGED_CONDITION_NAME, category=category, description="Test description."
        )
        apply_condition(companion.objectdb, savaged)
        self._cast()
        self.assertFalse(self._allies().exists())

    def test_second_cast_does_not_duplicate_companion(self):
        self._manifest_companion()
        self._cast()
        self._cast()
        self.assertEqual(self._allies().count(), 1)
