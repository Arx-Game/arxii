"""Tests for companion bridge Actions (#1873, #3652)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from evennia.utils.create import create_object

from actions.definitions.companions import (
    CompanionEmoteAction,
    CompanionFightAction,
    DeployCompanionAction,
)
from actions.registry import ACTIONS_BY_KEY
from actions.types import TargetType
from typeclasses.companions import CompanionObject
from world.character_sheets.factories import CharacterSheetFactory
from world.companions.defeat_content import SAVAGED_CONDITION_NAME
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.models import Companion
from world.conditions.constants import DurationType
from world.conditions.models import ConditionCategory, ConditionInstance, ConditionTemplate
from world.conditions.services import apply_condition, has_condition


class BridgeActionRegistrationTests(TestCase):
    def test_companion_fight_registered(self):
        self.assertIn("companion_fight", ACTIONS_BY_KEY)

    def test_deploy_companion_registered(self):
        self.assertIn("deploy_companion", ACTIONS_BY_KEY)

    def test_actions_target_self(self):
        self.assertEqual(CompanionFightAction().target_type, TargetType.SELF)
        self.assertEqual(DeployCompanionAction().target_type, TargetType.SELF)

    def test_actions_in_companions_category(self):
        self.assertEqual(CompanionFightAction().category, "companions")
        self.assertEqual(DeployCompanionAction().category, "companions")


def _present_companion(**kwargs) -> Companion:
    """A CompanionFactory instance with a live CompanionObject (fight/deploy-eligible)."""
    companion = CompanionFactory(**kwargs)
    obj = create_object(CompanionObject, key=companion.name, nohome=True)
    companion.objectdb = obj
    companion.save(update_fields=["objectdb"])
    return companion


class CompanionFitToFightPrerequisiteTests(TestCase):
    """A savaged companion cannot be sent back into a fight (#3652).

    The gate is narrow: it blocks companion fight and companion deploy only.
    An unsavaged companion is still accepted by both (the regression guard - a
    prerequisite that always fails would pass a refusal-only suite), and a
    savaged companion is still accepted by companion emote, proving the gate
    stayed narrow.
    """

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.owner = self.sheet.character
        self.archetype = CompanionArchetypeFactory()
        self.companion = _present_companion(owner=self.sheet, archetype=self.archetype)

        category = ConditionCategory.objects.create(
            name="Companion Injury", description="Test category text."
        )
        self.savaged = ConditionTemplate.objects.create(
            name=SAVAGED_CONDITION_NAME,
            category=category,
            description="Test description text.",
        )

    def _savage(self) -> None:
        apply_condition(self.companion.objectdb, self.savaged)

    def test_savaged_companion_refused_by_fight(self):
        self._savage()

        result = CompanionFightAction().run(actor=self.owner, companion_id=self.companion.pk)

        self.assertFalse(result.success)
        self.assertIn("is in no shape to fight", result.message)

    def test_savaged_companion_refused_by_deploy(self):
        self._savage()

        result = DeployCompanionAction().run(actor=self.owner, companion_id=self.companion.pk)

        self.assertFalse(result.success)
        self.assertIn("is in no shape to fight", result.message)

    def test_unsavaged_companion_accepted_by_fight(self):
        from world.combat.constants import RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.models import CombatParticipant, ParticipantStatus

        room = create_object("typeclasses.rooms.Room", key="Fight Room")
        self.owner.location = room
        self.owner.save()
        encounter = CombatEncounterFactory(room=room, risk_level=RiskLevel.LOW)
        CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )

        result = CompanionFightAction().run(actor=self.owner, companion_id=self.companion.pk)

        self.assertTrue(result.success, result.message)

    def test_unsavaged_companion_accepted_by_deploy(self):
        from world.battles.factories import BattleFactory, BattleSideFactory
        from world.battles.models import BattleParticipant, BattleParticipantStatus
        from world.combat.constants import RiskLevel

        battle = BattleFactory(risk_level=RiskLevel.LOW)
        side = BattleSideFactory(battle=battle)
        BattleParticipant.objects.create(
            battle=battle,
            character_sheet=self.sheet,
            side=side,
            status=BattleParticipantStatus.ACTIVE,
        )

        result = DeployCompanionAction().run(actor=self.owner, companion_id=self.companion.pk)

        self.assertTrue(result.success, result.message)

    def test_savaged_companion_still_accepted_by_emote(self):
        room = create_object("typeclasses.rooms.Room", key="Emote Room")
        self.owner.location = room
        self.owner.save()
        self.companion.objectdb.location = room
        self.companion.objectdb.save()
        self._savage()

        result = CompanionEmoteAction().run(
            actor=self.owner,
            companion_id=self.companion.pk,
            text="pads in a slow circle.",
        )

        self.assertTrue(result.success, result.message)


class SavagedExpirySweepTests(TestCase):
    """Spec Testing item (final review, minor finding): a Savaged instance whose
    expires_at has passed is swept on read and the companion may fight again.

    Unlike CompanionFitToFightPrerequisiteTests' setUp, this template is built
    with default_duration_type=INGAME_TIME (mirroring defeat_content.py's
    authored row) - the sweep inside get_active_conditions only ever fires for
    that duration type (world/conditions/services.py), so a ROUNDS-typed test
    template (the default) would never exercise it.
    """

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.owner = self.sheet.character
        self.archetype = CompanionArchetypeFactory()
        self.companion = _present_companion(owner=self.sheet, archetype=self.archetype)

        category = ConditionCategory.objects.create(
            name="Companion Injury", description="Test category text."
        )
        self.savaged = ConditionTemplate.objects.create(
            name=SAVAGED_CONDITION_NAME,
            category=category,
            description="Test description text.",
            default_duration_type=DurationType.INGAME_TIME,
            default_duration_value=72,
        )

    def test_expired_savaged_instance_is_swept_and_fight_is_allowed_again(self):
        apply_condition(self.companion.objectdb, self.savaged)
        self.assertTrue(has_condition(self.companion.objectdb, self.savaged))

        instance = ConditionInstance.objects.get(
            target=self.companion.objectdb, condition=self.savaged
        )
        instance.expires_at = timezone.now() - timedelta(hours=1)
        instance.save(update_fields=["expires_at"])

        self.assertFalse(has_condition(self.companion.objectdb, self.savaged))
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.companion.objectdb, condition=self.savaged
            ).exists()
        )

        from world.combat.constants import RiskLevel
        from world.combat.factories import CombatEncounterFactory
        from world.combat.models import CombatParticipant, ParticipantStatus

        room = create_object("typeclasses.rooms.Room", key="Fight Room")
        self.owner.location = room
        self.owner.save()
        encounter = CombatEncounterFactory(room=room, risk_level=RiskLevel.LOW)
        CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )

        result = CompanionFightAction().run(actor=self.owner, companion_id=self.companion.pk)

        self.assertTrue(result.success, result.message)
