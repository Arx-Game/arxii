"""Journeys: earned displays shake witnesses through real round resolution (#4147)."""

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ActionCategory, OpponentStatus, OpponentTier, SpectacleKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponentAction,
    CombatRoundAction,
    OpponentTierTemplate,
    SpectacleConfig,
    SpectacleRecord,
)
from world.combat.services import resolve_round
from world.combat.spectacle import encounter_for_character
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.conditions.models import ConditionInstance
from world.magic.audere import AUDERE_CONDITION_NAME, offer_audere
from world.magic.audere_majora import cross_threshold
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.tests.majora_fixtures import build_crossing_world
from world.magic.tests.test_audere_surge_broadcast import (
    _make_lifecycle_character,
    _make_threshold,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import InteractionMode, RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction, Persona
from world.vitals.models import CharacterVitals

PATH_LEVEL = "world.combat.spectacle.get_character_path_level"


def _check(success_level: int) -> SimpleNamespace:
    return SimpleNamespace(
        success_level=success_level,
        outcome=SimpleNamespace(success_level=success_level),
    )


class SpectacleWiringTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )
        cls.config, _ = SpectacleConfig.objects.get_or_create(pk=1)

    def setUp(self) -> None:
        # The identity map outlives a rolled-back test; restore the shared config.
        self.config.critical_technique_min_intensity = 6
        self.config.critical_technique_min_success_level = 5
        self.config.devastating_action_force_percent = 40
        self.config.save()
        patcher = mock.patch(PATH_LEVEL, return_value=6)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _encounter(self, *, ultimate=False, bandit_health=50, bandits=3):
        scene = SceneFactory()
        encounter = CombatEncounterFactory(
            scene=scene, status=RoundStatus.DECLARING, round_number=1
        )
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=1)
        template = OpponentTierTemplate.objects.filter(tier=OpponentTier.MOOK).first()
        if template is not None:
            template.has_morale = True
            template.save(update_fields=["has_morale"])
        opponents = [
            CombatOpponentFactory(
                encounter=encounter,
                tier=OpponentTier.MOOK,
                level=3,
                health=bandit_health,
                max_health=bandit_health,
                morale=70,
                max_morale=70,
                threat_pool=pool,
                name="bandit",
            )
            for _ in range(bandits)
        ]
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(
            character=sheet,
            engagement_type=EngagementType.COMBAT,
            source_content_type=ContentType.objects.get_for_model(CombatEncounter),
            source_id=encounter.pk,
        )
        room = ObjectDBFactory(db_key="SpectacleRoom", db_typeclass_path="typeclasses.rooms.Room")
        sheet.character.location = room
        sheet.character.save()
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
            is_ultimate=ultimate,
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponents[0],
        )
        for opponent in opponents:
            npc_action = CombatOpponentAction.objects.create(
                opponent=opponent, round_number=1, threat_entry=entry
            )
            npc_action.targets.add(participant)
        return encounter, opponents, sheet, technique

    def _resolve(self, encounter, success_level=2):
        resolve_round(encounter, offense_check_fn=lambda *_args, **_kwargs: _check(success_level))

    def _morale(self, opponents):
        return [type(o).objects.get(pk=o.pk).morale for o in opponents]

    def _spectacle_outcomes(self, encounter):
        return Interaction.objects.filter(scene=encounter.scene, mode=InteractionMode.OUTCOME)

    def test_ultimate_shakes_witnesses_and_posts_credit_line(self) -> None:
        encounter, opponents, sheet, _ = self._encounter(ultimate=True)
        self._resolve(encounter)
        self.assertTrue(
            SpectacleRecord.objects.filter(kind=SpectacleKind.ULTIMATE, caster=sheet).exists()
        )
        self.assertTrue(any(m < 70 for m in self._morale(opponents)))
        name = sheet.primary_persona.name
        self.assertTrue(any(name in o.content for o in self._spectacle_outcomes(encounter)))

    def test_ordinary_success_earns_nothing(self) -> None:
        encounter, opponents, _, _ = self._encounter(bandit_health=500)
        self._resolve(encounter)
        self.assertFalse(SpectacleRecord.objects.exists())
        self.assertEqual(self._morale(opponents), [70, 70, 70])

    def test_critical_cast_records_critical_technique(self) -> None:
        self.config.critical_technique_min_intensity = 0
        self.config.save()
        encounter, _, _, _ = self._encounter(bandit_health=500)
        self._resolve(encounter, success_level=5)
        self.assertTrue(
            SpectacleRecord.objects.filter(kind=SpectacleKind.CRITICAL_TECHNIQUE).exists()
        )

    def test_devastating_action_shakes_survivors_only(self) -> None:
        self.config.devastating_action_force_percent = 30
        self.config.save()
        # One 20-damage hit removes a 15-health bandit: a third of the enemy side's health.
        encounter, opponents, _, _ = self._encounter(bandit_health=15)
        self._resolve(encounter)
        records = SpectacleRecord.objects.filter(kind=SpectacleKind.DEVASTATING_ACTION)
        self.assertEqual(records.count(), 2)
        defeated = [
            o.pk for o in opponents if type(o).objects.get(pk=o.pk).status != OpponentStatus.ACTIVE
        ]
        self.assertEqual(len(defeated), 1)
        self.assertFalse(records.filter(opponent_id__in=defeated).exists())


class AudereEntryWiringTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config, _ = SpectacleConfig.objects.get_or_create(pk=1)
        cls.threshold = _make_threshold(surge_text="", tier_name="Spectacle_surge")

    def setUp(self) -> None:
        patcher = mock.patch(PATH_LEVEL, return_value=6)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fighter(self):
        character = _make_lifecycle_character("SpectacleSurger")
        encounter = CombatEncounterFactory(scene=SceneFactory())
        opponents = [
            CombatOpponentFactory(
                encounter=encounter, level=3, morale=70, max_morale=70, name="bandit"
            )
            for _ in range(2)
        ]
        engagement = CharacterEngagement.objects.get(character_id=character.pk)
        engagement.engagement_type = EngagementType.COMBAT
        engagement.source_content_type = ContentType.objects.get_for_model(CombatEncounter)
        engagement.source_id = encounter.pk
        engagement.save()
        return character, encounter, opponents

    def test_audere_entry_shakes_enemies_and_posts_credit(self) -> None:
        character, encounter, _opponents = self._fighter()
        self.assertEqual(encounter_for_character(character), encounter)
        with self.captureOnCommitCallbacks(execute=True):
            offer_audere(character, accept=True)
        self.assertTrue(
            SpectacleRecord.objects.filter(
                encounter=encounter, kind=SpectacleKind.AUDERE_ENTRY
            ).exists()
        )
        self.assertTrue(
            Interaction.objects.filter(scene=encounter.scene, mode=InteractionMode.OUTCOME).exists()
        )

    def test_no_encounter_is_a_quiet_no_op(self) -> None:
        character = _make_lifecycle_character("SpectacleLoner")
        self.assertIsNone(encounter_for_character(character))
        with self.captureOnCommitCallbacks(execute=True):
            offer_audere(character, accept=True)
        self.assertFalse(SpectacleRecord.objects.exists())

    def test_failing_spectacle_never_undoes_the_acceptance(self) -> None:
        character, _encounter, _opponents = self._fighter()
        # robust=True: the callback's failure is logged, never raised into the acceptance.
        with (
            mock.patch(
                "world.combat.spectacle.active_persona_for_sheet",
                side_effect=Persona.DoesNotExist,
            ),
            self.assertLogs("django.test", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = offer_audere(character, accept=True)
        self.assertTrue(result.accepted)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=character, condition__name=AUDERE_CONDITION_NAME
            ).exists()
        )
        self.assertFalse(SpectacleRecord.objects.exists())

    def test_rolled_back_acceptance_posts_nothing(self) -> None:
        character, _encounter, _opponents = self._fighter()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            offer_audere(character, accept=True)
        # Nothing ran before commit: a rolled-back acceptance never reaches the room.
        self.assertFalse(SpectacleRecord.objects.exists())
        self.assertTrue(callbacks)


class CrossingWiringTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        SpectacleConfig.objects.get_or_create(pk=1)
        wire_audere_power_multipliers()
        (
            cls.character,
            cls.sheet,
            cls.threshold,
            _prospect,
            cls.puissant_path,
            _offer,
        ) = build_crossing_world(boundary_level=30, suffix="_spectacle")

    def setUp(self) -> None:
        patcher = mock.patch(PATH_LEVEL, return_value=6)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_crossing_shakes_witnesses_and_posts_credit(self) -> None:
        encounter = CombatEncounterFactory(scene=SceneFactory())
        CombatOpponentFactory(encounter=encounter, level=3, morale=70, max_morale=70)
        engagement = CharacterEngagement.objects.get(character_id=self.character.pk)
        engagement.engagement_type = EngagementType.COMBAT
        engagement.source_content_type = ContentType.objects.get_for_model(CombatEncounter)
        engagement.source_id = encounter.pk
        engagement.save()
        with self.captureOnCommitCallbacks(execute=True):
            cross_threshold(
                self.sheet,
                self.threshold,
                self.puissant_path,
                declaration_text="I cross the threshold.",
            )
        self.assertTrue(
            SpectacleRecord.objects.filter(
                encounter=encounter, kind=SpectacleKind.CROSSING
            ).exists()
        )
        self.assertTrue(
            Interaction.objects.filter(scene=encounter.scene, mode=InteractionMode.OUTCOME).exists()
        )
