"""Survivability journey tests for issue #3450.

These tests deliberately cross the combat round/service boundaries instead of
calling only individual vitals helpers. They prove the authored survivability
arcs remain executable after the underlying mechanics are changed.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings, tag
from django.utils import timezone
from evennia import create_object

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import OpponentTier
from world.combat.factories import LethalDuelFactory, ThreatPoolEntryFactory, ThreatPoolFactory
from world.combat.models import CombatOpponentAction, CombatRoundAction
from world.combat.services import acknowledge_encounter_risk, resolve_round
from world.conditions.constants import BLEED_OUT_CONDITION_NAME, UNCONSCIOUS_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance, TreatmentTemplate
from world.conditions.services import perform_treatment
from world.magic.factories import CharacterAnimaFactory
from world.scenes.factories import SceneFactory
from world.vitals.constants import WOUND_CRIPPLING_NAME, CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import WoundDetails
from world.vitals.services import advance_bleed_out, attempt_wake, retire_character


@tag("postgres")
@override_settings(SEED_SAMPLE_CONTENT=True)
class SurvivabilityJourneyTests(TestCase):
    """Exercise the three survivability arcs through their real service seams."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.vitals.seeds import seed_survivability_content

        seed_survivability_content()
        from world.traits.models import CheckOutcome

        cls.failure_outcome = CheckOutcome.objects.get(name="Failure")
        cls.success_outcome = CheckOutcome.objects.get(name="Success")

    def _lethal_duel(self, *, source_account: bool = True, base_damage: int = 40, health: int = 20):
        """Build a lethal duel whose NPC hit deals exactly 40 damage."""
        sheet = CharacterSheetFactory()
        if source_account:
            account = AccountFactory()
            sheet.character.db_account = account
            sheet.character.save(update_fields=["db_account"])
        room = create_object("typeclasses.rooms.Room", key="Survivability Room", nohome=True)
        pool = ThreatPoolFactory(name="Survivability Lethal Pool")
        entry = ThreatPoolEntryFactory(pool=pool, name="Lethal Strike", base_damage=base_damage)
        encounter = LethalDuelFactory.create(
            pc_sheet=sheet,
            room=room,
            tier=OpponentTier.ELITE,
            opponent_kwargs={
                "name": "Significant Executioner",
                "max_health": 200,
                "threat_pool": pool,
            },
        )
        participant = encounter.participants.get()
        opponent = encounter.opponents.get()
        opponent.health = 200
        opponent.save(update_fields=["health"])
        vitals = CharacterVitalsFactory(
            character_sheet=sheet,
            health=health,
            max_health=100,
            life_state=CharacterLifeState.ALIVE,
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        sheet.character.move_to(room, quiet=True)
        npc_action = CombatOpponentAction.objects.create(
            opponent=opponent, round_number=1, threat_entry=entry
        )
        npc_action.targets.add(participant)
        CombatRoundAction.objects.create(
            participant=participant, round_number=1, focused_action=None, focused_category=None
        )
        acknowledge_encounter_risk(encounter, sheet)
        return encounter, sheet, vitals

    def test_lethal_npc_damage_reaches_death_and_retirement(self) -> None:
        """A lethal NPC hit runs damage → bleed-out → death → retire."""
        encounter, sheet, vitals = self._lethal_duel()

        # The first real combat round applies the lethal source and authors the
        # Bleeding Out condition through the combat damage pipeline.
        with force_check_outcome(self.failure_outcome):
            resolve_round(encounter)
        vitals.refresh_from_db()
        self.assertLessEqual(vitals.health, 0)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=sheet.character, condition__name=BLEED_OUT_CONDITION_NAME
            ).exists()
        )
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)

        # Failed bleed-out resists advance the authored stages; the terminal
        # failure resolves the guarded death pool.
        for _ in range(5):
            with force_check_outcome(self.failure_outcome):
                advance_bleed_out(sheet)
            vitals.refresh_from_db()
            if vitals.life_state == CharacterLifeState.DEAD:
                break

        self.assertEqual(vitals.life_state, CharacterLifeState.DEAD)
        self.assertEqual(sheet.lifecycle_state, LifecycleState.DEAD)
        self.assertIsNotNone(vitals.died_at)

        retire_character(sheet)
        vitals.refresh_from_db()
        self.assertIsNotNone(vitals.retired_at)
        can_puppet, reason = sheet.character.db_account.can_puppet_character(sheet.character)
        self.assertFalse(can_puppet)
        self.assertEqual(reason, "That character has been laid to rest.")

    def test_pc_source_cannot_kill_with_identical_damage(self) -> None:
        """The same lethal damage from a PC source is filtered by ADR-0023."""
        _encounter, sheet, vitals = self._lethal_duel()
        attacker = CharacterSheetFactory()
        attacker_account = AccountFactory()
        attacker.character.db_account = attacker_account
        attacker.character.save(update_fields=["db_account"])

        from world.vitals.services import process_damage_consequences

        vitals.health = -20
        vitals.save(update_fields=["health"])
        with force_check_outcome(self.failure_outcome):
            result = process_damage_consequences(
                character_sheet=sheet,
                damage_dealt=40,
                damage_type=None,
                source_character=attacker.character,
            )

        vitals.refresh_from_db()
        self.assertTrue(result.dying)
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=sheet.character, condition__name=BLEED_OUT_CONDITION_NAME
            ).exists()
        )
        self.assertIsNone(vitals.died_at)

    def test_knockout_reaches_guaranteed_wake(self) -> None:
        """A combat KO applies Unconscious and the deadline wakes the character."""
        encounter, sheet, _ = self._lethal_duel(base_damage=5, health=10)
        with force_check_outcome(self.failure_outcome):
            resolve_round(encounter)

        instance = ConditionInstance.objects.get(
            target=sheet.character, condition__name=UNCONSCIOUS_CONDITION_NAME
        )
        instance.expires_at = timezone.now() - timedelta(seconds=1)
        instance.save(update_fields=["expires_at"])

        result = attempt_wake(sheet)

        self.assertTrue(result.woke)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=sheet.character, condition__name=UNCONSCIOUS_CONDITION_NAME
            ).exists()
        )
        vitals = sheet.vitals
        vitals.refresh_from_db()
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)

    def test_wound_treatment_mends_once_and_preserves_attrition(self) -> None:
        """Treatment mends a combat wound once per healer and never to full."""
        target = CharacterSheetFactory()
        helper = CharacterSheetFactory()
        target_vitals = CharacterVitalsFactory(character_sheet=target, health=40, max_health=100)
        CharacterAnimaFactory(character=helper, current=20, maximum=20)
        wound_template = ConditionTemplateFactory(name=WOUND_CRIPPLING_NAME)
        wound = ConditionInstanceFactory(target=target.character, condition=wound_template)
        WoundDetails.objects.create(condition_instance=wound, damage_taken=60)
        scene = SceneFactory()
        treatment = TreatmentTemplate.objects.get(key="treat_crippling_wound")
        treatment.scene_required = False
        treatment.once_per_scene_per_helper = False
        treatment.mend_on_success = 100
        treatment.reduction_on_success = 0
        treatment.save(
            update_fields=[
                "scene_required",
                "once_per_scene_per_helper",
                "mend_on_success",
                "reduction_on_success",
            ]
        )

        with force_check_outcome(self.success_outcome):
            first = perform_treatment(helper, target, scene, treatment, wound)
        self.assertEqual(first.health_mended, 45)
        target_vitals.refresh_from_db()
        self.assertEqual(target_vitals.health, 85)

        from world.conditions.exceptions import TreatmentAlreadyAttempted

        with self.assertRaises(TreatmentAlreadyAttempted):
            perform_treatment(helper, target, scene, treatment, wound)
