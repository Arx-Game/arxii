"""Situations that read the state a target is in (#4759 slice 3, #4807).

Driven through ``applicable_perks`` with a live ``CombatRoundContext``: a
SELF-beneficiary perk carries one situation row, and the test asks whether
the perk fires for the holder's own declared attack.

Built in ``setUp`` rather than ``setUpTestData``: the factories create Evennia
``ObjectDB`` instances (``DbHolder``, not deepcopyable), the same rationale as
``test_perk_resolution.py``.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EngagementLockStatus, LockPcRole
from world.combat.factories import (
    ClashContributionFactory,
    ClashRoundFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
    EngagementLockFactory,
    LockClashFactory,
)
from world.combat.round_context import CombatRoundContext
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.covenants.perks.services import applicable_perks
from world.mechanics.factories import PropertyFactory


class _TargetStateCase(TestCase):
    """A holder in a covenant with a mate, both fighting; the holder attacks ``opponent``."""

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.holder = CharacterSheetFactory()
        self.mate = CharacterSheetFactory()
        self.stranger = CharacterSheetFactory()
        for sheet in (self.holder, self.mate):
            CharacterCovenantRoleFactory(
                character_sheet=sheet,
                covenant=self.covenant,
                covenant_role=self.role,
                engaged=True,
            )
        self.encounter = CombatEncounterFactory(round_number=1)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.holder
        )
        self.mate_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.mate
        )
        self.stranger_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.stranger
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        CombatRoundActionFactory(
            participant=self.participant,
            round_number=1,
            focused_opponent_target=self.opponent,
        )
        self.indulgence = PropertyFactory(name="Indulgence")
        self.perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )

    def _situation(self, situation: str, **params: object) -> None:
        VowSituationalPerkSituationFactory(perk=self.perk, situation=situation, **params)

    def _fires(self) -> bool:
        fired = applicable_perks(
            self.holder,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=CombatRoundContext(self.participant),
            target=None,
        )
        return any(firing.perk == self.perk for firing in fired)

    def _tipsy(self, bearer_objectdb_id: int, **kwargs: object) -> None:
        """Lay a condition carrying the Indulgence property on the bearer."""
        template = ConditionTemplateFactory(name="Tipsy")
        template.properties.add(self.indulgence)
        ConditionInstanceFactory(target_id=bearer_objectdb_id, condition=template, **kwargs)


class TargetHasConditionPropertyTests(_TargetStateCase):
    def test_fires_against_a_target_carrying_a_condition_with_the_property(self) -> None:
        self._situation(Situation.TARGET_HAS_CONDITION_PROPERTY, condition_property=self.indulgence)
        self._tipsy(self.opponent.objectdb_id, source_character=self.stranger.character)
        self.assertTrue(self._fires())

    def test_does_not_fire_without_the_property(self) -> None:
        self._situation(Situation.TARGET_HAS_CONDITION_PROPERTY, condition_property=self.indulgence)
        ConditionInstanceFactory(
            target_id=self.opponent.objectdb_id, condition=ConditionTemplateFactory(name="Sober")
        )
        self.assertFalse(self._fires())

    def test_a_resolved_condition_does_not_count(self) -> None:
        from django.utils import timezone

        self._situation(Situation.TARGET_HAS_CONDITION_PROPERTY, condition_property=self.indulgence)
        self._tipsy(self.opponent.objectdb_id, resolved_at=timezone.now())
        self.assertFalse(self._fires())

    def test_fires_on_a_stage_level_property(self) -> None:
        self._situation(Situation.TARGET_HAS_CONDITION_PROPERTY, condition_property=self.indulgence)
        stage = ConditionStageFactory(stage_order=2)
        stage.properties.add(self.indulgence)
        ConditionInstanceFactory(
            target_id=self.opponent.objectdb_id, condition=stage.condition, current_stage=stage
        )
        self.assertTrue(self._fires())

    def test_another_stage_of_the_same_condition_does_not_count(self) -> None:
        self._situation(Situation.TARGET_HAS_CONDITION_PROPERTY, condition_property=self.indulgence)
        tagged = ConditionStageFactory(stage_order=2)
        tagged.properties.add(self.indulgence)
        untagged = ConditionStageFactory(condition=tagged.condition, stage_order=1)
        ConditionInstanceFactory(
            target_id=self.opponent.objectdb_id,
            condition=tagged.condition,
            current_stage=untagged,
        )
        self.assertFalse(self._fires())

    def test_severity_threshold(self) -> None:
        self._situation(
            Situation.TARGET_HAS_CONDITION_PROPERTY,
            condition_property=self.indulgence,
            count_threshold=3,
        )
        self._tipsy(self.opponent.objectdb_id, severity=2)
        self.assertFalse(self._fires())

        condition = self.opponent.objectdb.condition_instances.get()
        condition.severity = 3
        condition.save()
        self.assertTrue(self._fires())

    def test_reads_a_sheet_backed_target(self) -> None:
        self._situation(Situation.TARGET_HAS_CONDITION_PROPERTY, condition_property=self.indulgence)
        self._tipsy(self.stranger.character_id)
        fired = applicable_perks(
            self.holder,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=None,
            target=self.stranger,
        )
        self.assertEqual([firing.perk for firing in fired], [self.perk])


class EnemiesWithConditionPropertyNearbyTests(_TargetStateCase):
    def setUp(self) -> None:
        super().setUp()
        self.second = CombatOpponentFactory(encounter=self.encounter)
        self.far = CombatOpponentFactory(encounter=self.encounter)
        for opponent in (self.opponent, self.second):
            EngagementLockFactory(
                encounter=self.encounter, participant=self.participant, opponent=opponent
            )

    def test_one_nearby_enemy_meets_the_default(self) -> None:
        self._situation(
            Situation.ENEMIES_WITH_CONDITION_PROPERTY_NEARBY, condition_property=self.indulgence
        )
        self._tipsy(self.second.objectdb_id)
        self.assertTrue(self._fires())

    def test_an_enemy_that_is_not_engaged_does_not_count(self) -> None:
        self._situation(
            Situation.ENEMIES_WITH_CONDITION_PROPERTY_NEARBY, condition_property=self.indulgence
        )
        self._tipsy(self.far.objectdb_id)
        self.assertFalse(self._fires())

    def test_count_threshold_counts_enemies(self) -> None:
        self._situation(
            Situation.ENEMIES_WITH_CONDITION_PROPERTY_NEARBY,
            condition_property=self.indulgence,
            count_threshold=2,
        )
        self._tipsy(self.opponent.objectdb_id)
        self.assertFalse(self._fires())

        template = ConditionTemplateFactory(name="Tipsy")
        ConditionInstanceFactory(target_id=self.second.objectdb_id, condition=template)
        self.assertTrue(self._fires())


class TargetLowHealthTests(_TargetStateCase):
    def test_default_threshold_is_half(self) -> None:
        self._situation(Situation.TARGET_LOW_HEALTH)
        self.opponent.health = 30
        self.opponent.save()
        self.assertFalse(self._fires())

        self.opponent.health = 20
        self.opponent.save()
        self.assertTrue(self._fires())

    def test_authored_threshold(self) -> None:
        self._situation(Situation.TARGET_LOW_HEALTH, threshold_percent=25)
        self.opponent.health = 20
        self.opponent.save()
        self.assertFalse(self._fires())

        self.opponent.health = 10
        self.opponent.save()
        self.assertTrue(self._fires())


class EnemyHeldByAllyTests(_TargetStateCase):
    def setUp(self) -> None:
        super().setUp()
        self._situation(Situation.ENEMY_HELD_BY_ALLY)
        self.binding = ConditionTemplateFactory(name="Bound in Roots", is_clash_lock=True)

    def test_nothing_holds_the_enemy(self) -> None:
        self.assertFalse(self._fires())

    def test_engagement_lock_still_counts(self) -> None:
        EngagementLockFactory(
            encounter=self.encounter,
            participant=self.mate_participant,
            opponent=self.opponent,
            status=EngagementLockStatus.ACTIVE,
        )
        self.assertTrue(self._fires())

    def test_held_by_a_mates_clash_lock_condition(self) -> None:
        ConditionInstanceFactory(
            target_id=self.opponent.objectdb_id,
            condition=self.binding,
            source_character=self.mate.character,
        )
        self.assertTrue(self._fires())

    def test_a_strangers_clash_lock_condition_does_not_count(self) -> None:
        ConditionInstanceFactory(
            target_id=self.opponent.objectdb_id,
            condition=self.binding,
            source_character=self.stranger.character,
        )
        self.assertFalse(self._fires())

    def test_a_mates_ordinary_condition_does_not_count(self) -> None:
        ConditionInstanceFactory(
            target_id=self.opponent.objectdb_id,
            condition=ConditionTemplateFactory(name="Bruised"),
            source_character=self.mate.character,
        )
        self.assertFalse(self._fires())

    def test_held_by_a_lock_clash_a_mate_started(self) -> None:
        LockClashFactory(encounter=self.encounter, npc_opponent=self.opponent, initiator=self.mate)
        self.assertTrue(self._fires())

    def test_held_by_a_lock_clash_a_mate_contributed_to(self) -> None:
        clash = LockClashFactory(
            encounter=self.encounter, npc_opponent=self.opponent, initiator=self.stranger
        )
        self.assertFalse(self._fires())

        ClashContributionFactory(clash_round=ClashRoundFactory(clash=clash), character=self.mate)
        self.assertTrue(self._fires())

    def test_an_escaping_lock_clash_does_not_count(self) -> None:
        """ESCAPING is the enemy holding a PC, not a PC holding the enemy."""
        LockClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            initiator=self.mate,
            lock_pc_role=LockPcRole.ESCAPING,
        )
        self.assertFalse(self._fires())
