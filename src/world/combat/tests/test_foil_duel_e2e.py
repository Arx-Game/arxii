"""E2E journey: foil duel within a group fight (#2020).

Tests the full DoD: 3 PCs + boss + foil; foil locked to PC-2 ->
foil provably targets PC-2 across rounds; damage creates threat;
auto-lock from threshold; foil defeat breaks lock with reason=DEFEAT.

#3386 extends this journey to the player-callable entry points that were
missing a telnet/web surface: EngageAction/DisengageAction (the same
dispatch_player_action seam both telnet and web reach), plus the
FLEE-breaks-lock lifecycle close-out.
"""

from django.test import TestCase

from actions.definitions.combat_maneuvers import DisengageAction, EngageAction
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    EngagementLockStatus,
    LockBreakReason,
    LockInitiator,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.engagement_locks import (
    break_engagement_lock,
    check_auto_lock_formation,
    create_engagement_lock,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    ThreatRecordFactory,
)
from world.combat.models import EngagementLock, FleeConfig, ThreatRecord
from world.combat.services import (
    apply_damage_to_opponent,
    declare_flee,
    resolve_round,
    select_npc_actions,
)
from world.covenants.factories import CovenantRoleFactory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


class FoilDuelE2ETests(TestCase):
    """Full journey: foil pairing, provable targeting, interference, defeat."""

    def setUp(self):
        self.enc = CombatEncounterFactory(
            encounter_type="party_combat",
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        # Three PCs
        self.pc1 = CombatParticipantFactory(encounter=self.enc)
        self.pc2 = CombatParticipantFactory(encounter=self.enc)
        self.pc3 = CombatParticipantFactory(encounter=self.enc)
        # Boss (normal targeting)
        boss_pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=boss_pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.RANDOM,
            weight=10,
        )
        self.boss = CombatOpponentFactory(encounter=self.enc, threat_pool=boss_pool)
        # Foil (authored, has_foil_behavior, low threshold)
        foil_pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=foil_pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            weight=10,
        )
        self.foil = CombatOpponentFactory(
            encounter=self.enc,
            threat_pool=foil_pool,
            has_foil_behavior=True,
            auto_lock_threshold=20,
        )

    def test_gm_locks_foil_to_pc2_and_npc_targets_pc2(self):
        """GM declares the foil locks to PC-2 -> foil provably targets PC-2."""
        create_engagement_lock(
            self.enc, self.foil, self.pc2, initiated_by=LockInitiator.GM_DECLARED
        )
        actions = select_npc_actions(self.enc)
        foil_action = next(a for a in actions if a.opponent_id == self.foil.pk)
        self.assertEqual(list(foil_action.targets.all()), [self.pc2])

    def test_foil_targets_pc2_across_multiple_rounds(self):
        """Lock persists — foil targets PC-2 on round 2 as well."""
        create_engagement_lock(
            self.enc, self.foil, self.pc2, initiated_by=LockInitiator.GM_DECLARED
        )
        select_npc_actions(self.enc)
        self.enc.round_number = 2
        self.enc.save(update_fields=["round_number"])
        actions = select_npc_actions(self.enc)
        foil_action = next(a for a in actions if a.opponent_id == self.foil.pk)
        self.assertEqual(list(foil_action.targets.all()), [self.pc2])

    def test_damage_creates_threat_record(self):
        """PC-2 dealing damage to the foil creates a ThreatRecord."""
        apply_damage_to_opponent(self.foil, 10, source_sheet=self.pc2.character_sheet)
        record = ThreatRecord.objects.get(
            encounter=self.enc, opponent=self.foil, participant=self.pc2
        )
        self.assertGreater(record.threat_value, 0)

    def test_auto_lock_formation_from_threat(self):
        """Pre-seeded threat crossing threshold creates an autonomous lock."""
        ThreatRecordFactory(
            encounter=self.enc, opponent=self.foil, participant=self.pc2, threat_value=50
        )
        check_auto_lock_formation(self.enc)
        lock = EngagementLock.objects.get(encounter=self.enc, opponent=self.foil)
        self.assertEqual(lock.initiated_by, LockInitiator.THREAT)

    def test_foil_defeat_breaks_lock_and_narrates(self):
        """Foil falling to PC-2 breaks the lock with reason=DEFEAT."""
        lock = create_engagement_lock(
            self.enc, self.foil, self.pc2, initiated_by=LockInitiator.GM_DECLARED
        )
        break_engagement_lock(lock, reason=LockBreakReason.DEFEAT)
        lock.refresh_from_db()
        self.assertEqual(lock.status, EngagementLockStatus.BROKEN)
        self.assertEqual(lock.break_reason, LockBreakReason.DEFEAT)

    def test_engage_action_challenges_foil_and_locks_via_next_npc_pass(self):
        """EngageAction (#3386) — the player-callable entry point — spikes threat past
        the foil's auto_lock_threshold; the lock forms (and targeting narrows) on the
        next select_npc_actions pass, the same seam both telnet and the web reach
        through dispatch_player_action.
        """
        actor = self.pc2.character_sheet.character
        result = EngageAction().run(actor=actor, opponent_id=self.foil.pk)
        self.assertTrue(result.success)

        actions = select_npc_actions(self.enc)  # runs check_auto_lock_formation first

        lock = EngagementLock.objects.get(
            encounter=self.enc, opponent=self.foil, status=EngagementLockStatus.ACTIVE
        )
        self.assertEqual(lock.participant_id, self.pc2.pk)
        # NOTE: create_engagement_lock_for_challenge only spikes threat (unchanged,
        # pre-existing #2020 mechanism); lock formation always runs through
        # check_auto_lock_formation, which stamps THREAT regardless of what
        # triggered the crossing — LockInitiator.PC_CHALLENGE is a declared enum
        # value with no real call site (verified: only a model-level fixture test
        # assigns it directly). The provable-targeting guarantee holds either way.
        self.assertEqual(lock.initiated_by, LockInitiator.THREAT)

        foil_action = next(a for a in actions if a.opponent_id == self.foil.pk)
        self.assertEqual(list(foil_action.targets.all()), [self.pc2])

    def test_disengage_action_breaks_lock_and_widens_targeting(self):
        """DisengageAction (#3386) breaks the caller's active lock; the foil's
        targeting is no longer forced onto that PC afterward.
        """
        actor = self.pc2.character_sheet.character
        EngageAction().run(actor=actor, opponent_id=self.foil.pk)
        select_npc_actions(self.enc)  # forms the lock, narrowing to pc2

        result = DisengageAction().run(actor=actor)
        self.assertTrue(result.success)

        lock = EngagementLock.objects.get(
            encounter=self.enc, opponent=self.foil, participant=self.pc2
        )
        self.assertEqual(lock.status, EngagementLockStatus.BROKEN)
        self.assertEqual(lock.break_reason, LockBreakReason.DISENGAGE)

        # PC-1 now carries the highest threat — proves the foil's target pool
        # widened past being forced onto PC-2 (while locked it could never be free
        # to pick anyone else).
        ThreatRecordFactory(
            encounter=self.enc, opponent=self.foil, participant=self.pc1, threat_value=999
        )
        self.enc.round_number = 2
        self.enc.save(update_fields=["round_number"])
        actions = select_npc_actions(self.enc)
        foil_action = next(a for a in actions if a.opponent_id == self.foil.pk)
        self.assertEqual(list(foil_action.targets.all()), [self.pc1])


class FleeBreaksEngagementLockTest(TestCase):
    """A locked PC who successfully flees has their lock released (#3386).

    Closes the LockBreakReason.FLEE gap: before this fix a PC who fled while
    locked kept status ACTIVE on their EngagementLock forever (until the NPC
    was later defeated by someone else).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Lower speed rank than the NPC's default → the fleer resolves first.
        cls.fast_role = CovenantRoleFactory(speed_rank=3)

    def test_flee_breaks_active_engagement_lock(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=self.fast_role,
        )
        opponent = CombatOpponentFactory(encounter=encounter)
        lock = create_engagement_lock(
            encounter, opponent, participant, initiated_by=LockInitiator.GM_DECLARED
        )

        FleeConfig.objects.filter(pk=1).delete()
        FleeConfig.objects.create(pk=1, check_type=CheckTypeFactory(), base_difficulty=1)
        declare_flee(participant)

        success = CheckOutcomeFactory(name="FleeE2ESuccess", success_level=0)
        with force_check_outcome(success):
            resolve_round(encounter)

        participant.refresh_from_db()
        self.assertEqual(participant.status, ParticipantStatus.FLED)

        lock.refresh_from_db()
        self.assertEqual(lock.status, EngagementLockStatus.BROKEN)
        self.assertEqual(lock.break_reason, LockBreakReason.FLEE)
