"""forces_attack_on_source conditions narrow an NPC's target to the source (#4584)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatAllegiance,
    EncounterType,
    EngagementLockStatus,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EngagementLockFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    ThreatRecordFactory,
)
from world.combat.services import select_npc_actions
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.services import provoking_source_by_target
from world.scenes.constants import RoundStatus


class ProvokingSourceByTargetTests(TestCase):
    """The batched helper maps a bearer to the newest active, sourced provoke."""

    @classmethod
    def setUpTestData(cls):
        cls.bearer = ObjectDBFactory(db_key="Bearer4584")
        cls.other = ObjectDBFactory(db_key="Other4584")
        cls.first = ObjectDBFactory(db_key="FirstSource4584")
        cls.second = ObjectDBFactory(db_key="SecondSource4584")
        cls.provoke = ConditionTemplateFactory(name="Provoke 4584", forces_attack_on_source=True)
        cls.plain = ConditionTemplateFactory(name="Plain 4584", forces_attack_on_source=False)
        cls.later = ConditionTemplateFactory(name="Later 4584", forces_attack_on_source=True)

    def test_maps_bearer_to_source_in_one_query(self):
        ConditionInstanceFactory(
            target=self.bearer, condition=self.provoke, source_character=self.first
        )
        ConditionInstanceFactory(
            target=self.other, condition=self.plain, source_character=self.first
        )

        with self.assertNumQueries(1):
            result = provoking_source_by_target([self.bearer, self.other])

        self.assertEqual(result, {self.bearer.pk: self.first.pk})

    def test_newest_instance_wins(self):
        ConditionInstanceFactory(
            target=self.bearer, condition=self.provoke, source_character=self.first
        )
        ConditionInstanceFactory(
            target=self.bearer, condition=self.later, source_character=self.second
        )

        self.assertEqual(
            provoking_source_by_target([self.bearer]), {self.bearer.pk: self.second.pk}
        )

    def test_suppressed_instance_is_skipped(self):
        ConditionInstanceFactory(
            target=self.bearer,
            condition=self.provoke,
            source_character=self.first,
            is_suppressed=True,
        )

        self.assertEqual(provoking_source_by_target([self.bearer]), {})

    def test_sourceless_instance_is_skipped(self):
        ConditionInstanceFactory(
            target=self.bearer, condition=self.provoke, source_character=self.first
        )
        ConditionInstanceFactory(target=self.bearer, condition=self.later, source_character=None)

        self.assertEqual(provoking_source_by_target([self.bearer]), {self.bearer.pk: self.first.pk})

    def test_no_targets_runs_no_query(self):
        with self.assertNumQueries(0):
            self.assertEqual(provoking_source_by_target([]), {})


class ProvokeTargetingTests(TestCase):
    """select_npc_actions narrows a provoked opponent to the one who provoked it."""

    @classmethod
    def setUpTestData(cls):
        cls.provoke = ConditionTemplateFactory(name="Called Out 4584", forces_attack_on_source=True)
        cls.plain = ConditionTemplateFactory(name="Pointed At 4584", forces_attack_on_source=False)

    def _encounter(self, selection, mode=TargetingMode.SINGLE):
        enc = CombatEncounterFactory(
            encounter_type=EncounterType.PARTY_COMBAT,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool, targeting_mode=mode, target_selection=selection, weight=10
        )
        opp = CombatOpponentFactory(encounter=enc, threat_pool=pool)
        return enc, opp

    def _provoke(self, opp, source_participant, condition=None):
        ConditionInstanceFactory(
            target=opp.objectdb,
            condition=condition or self.provoke,
            source_character=source_participant.character_sheet.character,
        )

    def _setup_hated_and_warden(self):
        enc, opp = self._encounter(TargetSelection.HIGHEST_THREAT)
        hated = CombatParticipantFactory(encounter=enc)
        warden = CombatParticipantFactory(encounter=enc)
        ThreatRecordFactory(encounter=enc, opponent=opp, participant=hated, threat_value=90)
        return enc, opp, hated, warden

    def test_a_provoked_opponent_attacks_only_its_source(self):
        enc, opp, _hated, warden = self._setup_hated_and_warden()
        self._provoke(opp, warden)

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [warden])

    def test_an_unflagged_condition_from_the_same_source_changes_nothing(self):
        enc, opp, hated, warden = self._setup_hated_and_warden()
        self._provoke(opp, warden, self.plain)

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [hated])

    def test_a_provoke_narrows_an_all_targets_swing_to_the_source(self):
        enc, opp = self._encounter(TargetSelection.HIGHEST_THREAT, TargetingMode.ALL)
        CombatParticipantFactory(encounter=enc)
        CombatParticipantFactory(encounter=enc)
        warden = CombatParticipantFactory(encounter=enc)
        self._provoke(opp, warden)

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [warden])

    def test_an_engagement_lock_wins_over_a_provoke(self):
        enc, opp, hated, warden = self._setup_hated_and_warden()
        self._provoke(opp, warden)
        EngagementLockFactory(
            encounter=enc,
            opponent=opp,
            participant=hated,
            status=EngagementLockStatus.ACTIVE,
        )

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [hated])

    def test_a_provoke_whose_source_is_down_falls_back(self):
        enc, opp, hated, warden = self._setup_hated_and_warden()
        self._provoke(opp, warden)
        warden.status = ParticipantStatus.FLED
        warden.save(update_fields=["status"])

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [hated])

    def test_a_provoke_from_someone_outside_the_fight_is_ignored(self):
        enc, opp, hated, _warden = self._setup_hated_and_warden()
        ConditionInstanceFactory(
            target=opp.objectdb,
            condition=self.provoke,
            source_character=CharacterSheetFactory().character,
        )

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [hated])

    def test_an_opponent_with_no_provoke_still_picks_normally(self):
        enc, _opp, hated, _warden = self._setup_hated_and_warden()

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [hated])

    def test_an_ally_summon_ignores_a_provoke(self):
        enc, enemy = self._encounter(TargetSelection.HIGHEST_THREAT)
        pc = CombatParticipantFactory(encounter=enc)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, targeting_mode=TargetingMode.SINGLE, weight=10)
        summon = CombatOpponentFactory(
            encounter=enc, threat_pool=pool, allegiance=CombatAllegiance.ALLY
        )
        self._provoke(summon, pc)

        actions = [a for a in select_npc_actions(enc) if a.opponent_id == summon.pk]

        self.assertTrue(actions)
        for action in actions:
            self.assertEqual(list(action.targets.all()), [])
            self.assertEqual(list(action.opponent_targets.all()), [enemy])

    def test_the_newest_provoke_wins(self):
        enc, opp, hated, warden = self._setup_hated_and_warden()
        second = ConditionTemplateFactory(
            name="Called Out Again 4584", forces_attack_on_source=True
        )
        self._provoke(opp, hated)
        self._provoke(opp, warden, second)

        self.assertEqual(list(select_npc_actions(enc)[0].targets.all()), [warden])
