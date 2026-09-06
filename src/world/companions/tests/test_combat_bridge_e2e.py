"""E2E journey tests for companion combat bridges (#1873).

Exercises the full Action.run() -> service -> bridge path for both
duel-scale and battle-scale, plus the defeat-consequence gate.
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.content import ensure_companion_content
from world.companions.defeat_content import SAVAGED_CONDITION_NAME
from world.companions.factories_combat import create_companion_defeat_pool
from world.magic.specialization.services import grant_gift_to_character


def _force_pool_draw(pool, label: str) -> None:
    """Zero every other consequence's weight so *label* is always drawn.

    Uses ConsequencePoolEntry.weight_override rather than patching the RNG:
    ConsequencePoolEntry.Meta has no ordering, so a cumulative-weight boundary
    computed from iteration order is not guaranteed to hold (it would pass on
    SQLite and could flake on Postgres). Call this before anything reads
    pool.cached_consequences - it is a cached_property, so once computed it
    will not reflect these overrides.
    """
    from actions.models import ConsequencePoolEntry

    entries = ConsequencePoolEntry.objects.filter(pool=pool).select_related("consequence")
    for entry in entries:
        if entry.consequence.label != label:
            entry.weight_override = 0
            entry.save(update_fields=["weight_override"])


class CompanionCombatBridgeE2ETests(EvenniaTestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.conditions.models import ConditionCategory, ConditionTemplate

        self.pool = create_companion_defeat_pool()
        category = ConditionCategory.objects.create(
            name="Companion Injury",
            description="Staff-authored category text that must survive.",
        )
        ConditionTemplate.objects.create(
            name=SAVAGED_CONDITION_NAME,
            category=category,
            description="Torn up badly enough that another fight would finish it.",
        )
        self.room = create_object("typeclasses.rooms.Room", key="Combat Room")
        self.sheet = CharacterSheetFactory()
        self.owner = self.sheet.character
        self.owner.location = self.room
        self.owner.save()
        self.gift = ensure_companion_content()
        self.resonance = self.gift.resonances.first()
        grant_gift_to_character(self.sheet, self.gift, resonance=self.resonance)

        from world.magic.constants import TargetKind
        from world.magic.models.threads import Thread

        self.thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        self.thread.level = 20
        self.thread.save(update_fields=["level"])

    def test_duel_bridge_journey(self):
        """A bound companion commits to a duel via CompanionFightAction."""
        from actions.definitions.companions import BindCompanionAction, CompanionFightAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import CombatAllegiance, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.models import CombatOpponent, CombatParticipant, ParticipantStatus
        from world.companions.models import Companion, CompanionArchetype
        from world.traits.factories import CheckOutcomeFactory

        # Bind a companion.
        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Duel Success", success_level=5)
        with force_check_outcome(success):
            result = BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        self.assertTrue(result.success, result.message)
        companion = Companion.objects.get(name="Skree")

        # Create an encounter and add the owner as a participant.
        encounter = CombatEncounterFactory(room=self.room, risk_level=RiskLevel.LOW)
        encounter.risk_level = RiskLevel.LOW
        encounter.save(update_fields=["risk_level"])
        CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )

        # Commit the companion to the fight.
        result = CompanionFightAction().run(
            actor=self.owner,
            companion_id=companion.pk,
        )
        self.assertTrue(result.success, result.message)

        # The companion is now an ALLY opponent sourced from the archetype.
        opponent = CombatOpponent.objects.get(pk=result.data["opponent_id"])
        self.assertEqual(opponent.allegiance, CombatAllegiance.ALLY)
        self.assertEqual(opponent.summoned_by, self.sheet)
        self.assertIsNone(opponent.bond_expires_round)
        self.assertEqual(opponent.max_health, hawk.max_health)

    def test_duel_lethal_defeat_journey(self):
        """At LETHAL risk, a defeated companion may die (be released)."""
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype
        from world.companions.services import resolve_companion_defeat
        from world.traits.factories import CheckOutcomeFactory

        # Bind a companion.
        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Lethal Success", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        # Simulate defeat at LETHAL risk — run until death occurs.
        released = False
        for _ in range(50):
            test_companion = Companion.objects.get(pk=companion.pk)
            if not test_companion.is_active:
                break
            died = resolve_companion_defeat(test_companion, RiskLevel.LETHAL)
            if died:
                released = True
                test_companion.refresh_from_db()
                self.assertFalse(test_companion.is_active)
                self.assertIsNotNone(test_companion.released_at)
                break

        self.assertTrue(released, "Expected at least one lethal defeat to release the companion")

    def test_duel_low_risk_defeat_journey(self):
        """At LOW risk, a defeated companion is NOT released."""
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype
        from world.companions.services import resolve_companion_defeat
        from world.traits.factories import CheckOutcomeFactory

        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Low Success", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        died = resolve_companion_defeat(companion, RiskLevel.LOW)
        self.assertFalse(died)
        companion.refresh_from_db()
        self.assertTrue(companion.is_active)

    def test_battle_bridge_journey(self):
        """A bound companion deploys into a battle via DeployCompanionAction."""
        from actions.definitions.companions import BindCompanionAction, DeployCompanionAction
        from world.battles.constants import VehicleKind
        from world.battles.factories import BattleFactory, BattleSideFactory
        from world.battles.models import BattleParticipant, BattleParticipantStatus
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype, CompanionDeployment
        from world.traits.factories import CheckOutcomeFactory

        # Bind a companion with custom strength.
        hawk = CompanionArchetype.objects.get(name="Hawk")
        hawk.strength = 25
        hawk.save(update_fields=["strength"])
        success = CheckOutcomeFactory(name="E2E Battle Success", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        # Create a battle and enlist the owner.
        battle = BattleFactory(risk_level=RiskLevel.LOW)
        side = BattleSideFactory(battle=battle)
        BattleParticipant.objects.create(
            battle=battle,
            character_sheet=self.sheet,
            side=side,
            status=BattleParticipantStatus.ACTIVE,
        )

        # Deploy the companion.
        result = DeployCompanionAction().run(
            actor=self.owner,
            companion_id=companion.pk,
        )
        self.assertTrue(result.success, result.message)

        # The companion is now a COMPANION-kind non-structural vehicle.
        from world.battles.models import BattleVehicle

        vehicle = BattleVehicle.objects.get(pk=result.data["vehicle_id"])
        self.assertEqual(vehicle.vehicle_kind, VehicleKind.COMPANION)
        self.assertFalse(vehicle.is_structural)
        self.assertEqual(vehicle.unit.strength, 25)

        # CompanionDeployment links the persistent companion.
        deployment = CompanionDeployment.objects.get(companion=companion)
        self.assertEqual(deployment.vehicle, vehicle)
        self.assertEqual(deployment.battle, battle)

    def test_battle_low_risk_defeat_journey(self):
        """At LOW risk, a destroyed companion vehicle does NOT release the companion."""
        from actions.definitions.companions import BindCompanionAction
        from world.checks.test_helpers import force_check_outcome
        from world.combat.constants import RiskLevel
        from world.companions.models import Companion, CompanionArchetype
        from world.companions.services import resolve_companion_defeat
        from world.traits.factories import CheckOutcomeFactory

        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E Battle Low", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        died = resolve_companion_defeat(companion, RiskLevel.LOW)
        self.assertFalse(died)
        companion.refresh_from_db()
        self.assertTrue(companion.is_active)

    def test_no_companion_fails_gracefully(self):
        """CompanionFightAction fails gracefully with no companion_id."""
        from actions.definitions.companions import CompanionFightAction

        result = CompanionFightAction().run(actor=self.owner)
        self.assertFalse(result.success)

    def test_no_active_encounter_fails_gracefully(self):
        """CompanionFightAction fails when the owner is not in combat."""
        from actions.definitions.companions import BindCompanionAction, CompanionFightAction
        from world.checks.test_helpers import force_check_outcome
        from world.companions.models import Companion, CompanionArchetype
        from world.traits.factories import CheckOutcomeFactory

        hawk = CompanionArchetype.objects.get(name="Hawk")
        success = CheckOutcomeFactory(name="E2E No Combat", success_level=5)
        with force_check_outcome(success):
            BindCompanionAction().run(
                actor=self.owner, gift_id=self.gift.pk, archetype_id=hawk.pk, name="Skree"
            )
        companion = Companion.objects.get(name="Skree")

        result = CompanionFightAction().run(actor=self.owner, companion_id=companion.pk)
        self.assertFalse(result.success)
        self.assertIn("not in active combat", result.message)

    def _bridge_companion(self, encounter):
        """Bridge a fresh, present Companion into *encounter* as an ALLY opponent."""
        from evennia.utils.create import create_object

        from typeclasses.companions import CompanionObject
        from world.companions.factories import CompanionFactory
        from world.companions.services import materialize_companion_as_combat_opponent

        companion = CompanionFactory(owner=self.sheet)
        obj = create_object(CompanionObject, key=companion.name, nohome=True)
        companion.objectdb = obj
        companion.save(update_fields=["objectdb"])
        opponent = materialize_companion_as_combat_opponent(companion, encounter)
        return companion, opponent

    def test_complete_encounter_lethal_die_releases_companion_and_narrates(self):
        """#3652: LETHAL + die forced -> the companion is released and mourned."""
        from world.combat.constants import EncounterOutcome, OpponentStatus, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.services import complete_encounter
        from world.companions.factories_combat import COMPANION_DIE_LABEL
        from world.scenes.models import Interaction

        _force_pool_draw(self.pool, COMPANION_DIE_LABEL)
        encounter = CombatEncounterFactory(room=self.room, risk_level=RiskLevel.LETHAL)
        companion, opponent = self._bridge_companion(encounter)
        companion_name = companion.name
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        companion.refresh_from_db()
        self.assertIsNotNone(companion.released_at)
        self.assertIsNone(companion.objectdb)
        self.assertTrue(
            Interaction.objects.filter(
                scene=encounter.scene, content__icontains=companion_name
            ).exists()
        )

    def test_complete_encounter_lethal_stay_incapacitated_forced(self):
        """#3652: LETHAL + stay_incapacitated forced -> companion survives, Savaged."""
        from world.combat.constants import EncounterOutcome, OpponentStatus, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.services import complete_encounter
        from world.companions.factories_combat import COMPANION_STAY_INCAPACITATED_LABEL
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import has_condition

        _force_pool_draw(self.pool, COMPANION_STAY_INCAPACITATED_LABEL)
        encounter = CombatEncounterFactory(room=self.room, risk_level=RiskLevel.LETHAL)
        companion, opponent = self._bridge_companion(encounter)
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        companion.refresh_from_db()
        self.assertTrue(companion.is_active)
        savaged = ConditionTemplate.get_by_name(SAVAGED_CONDITION_NAME)
        self.assertTrue(has_condition(companion.objectdb, savaged))

    def test_complete_encounter_low_risk_leaves_companion_untouched(self):
        """#3652: LOW risk -> the hook does nothing, no interaction narrated."""
        from world.combat.constants import EncounterOutcome, OpponentStatus, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.services import complete_encounter
        from world.scenes.models import Interaction

        encounter = CombatEncounterFactory(room=self.room, risk_level=RiskLevel.LOW)
        companion, opponent = self._bridge_companion(encounter)
        companion_name = companion.name
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        companion.refresh_from_db()
        self.assertTrue(companion.is_active)
        self.assertIsNotNone(companion.objectdb)
        self.assertFalse(
            Interaction.objects.filter(
                scene=encounter.scene, content__icontains=companion_name
            ).exists()
        )

    def test_complete_encounter_abandoned_at_lethal_leaves_companion_untouched(self):
        """#3652: a GM ending a scene (ABANDONED) must not kill anyone's companion."""
        from world.combat.constants import EncounterOutcome, OpponentStatus, RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.services import complete_encounter
        from world.companions.factories_combat import COMPANION_DIE_LABEL

        _force_pool_draw(self.pool, COMPANION_DIE_LABEL)
        encounter = CombatEncounterFactory(room=self.room, risk_level=RiskLevel.LETHAL)
        companion, opponent = self._bridge_companion(encounter)
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])

        complete_encounter(encounter, outcome=EncounterOutcome.ABANDONED)

        companion.refresh_from_db()
        self.assertTrue(companion.is_active)
        self.assertIsNone(companion.released_at)
        self.assertIsNotNone(companion.objectdb)

    def test_complete_encounter_plain_summon_defeated_at_lethal_does_not_crash(self):
        """#3652: an ordinary ALLY summon with no Companion behind it is left alone."""
        from world.combat.constants import (
            CombatAllegiance,
            EncounterOutcome,
            OpponentStatus,
            RiskLevel,
        )
        from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
        from world.combat.services import complete_encounter

        encounter = CombatEncounterFactory(room=self.room, risk_level=RiskLevel.LETHAL)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            status=OpponentStatus.DEFEATED,
            allegiance=CombatAllegiance.ALLY,
            summoned_by=self.sheet,
        )

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        opponent.refresh_from_db()
        self.assertEqual(opponent.status, OpponentStatus.DEFEATED)
