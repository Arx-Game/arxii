"""Settling a charm through the scene social pipeline (#4091, task 8)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from actions.player_interface import _scene_actions
from evennia_extensions.factories import ObjectDBFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.models import CombatEncounter
from world.conditions.constants import Allegiance
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.npc_services import allegiance_outcomes
from world.npc_services.models import NpcRegardEvent
from world.scenes.action_services import create_action_request
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction
from world.scenes.narrator import NARRATOR_PERSONA_NAME
from world.scenes.services import active_persona_for_sheet
from world.seeds.game_content.characters import CharacterContent
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory


class SettleAllegianceTests(TestCase):
    """Settle resolves through the condition's settle pool, graded by roll tier."""

    @classmethod
    def setUpTestData(cls) -> None:
        setup = CheckSystemSetupFactory.create()
        cls.outcomes = setup["outcomes"]
        # Deliberately never added to any pool below (fix #2's oracle): an
        # authored-but-unpooled outcome whose synthetic fallback label must
        # never leak into a narration.
        cls.botch_outcome = CheckOutcomeFactory(name="Botch", success_level=-2)

        cls.template = ActionTemplateFactory(
            name="Settle a charm", category="social", settles_allegiance=True
        )

        template_pool = ConsequencePoolFactory(name="Enthralled settle (template)")
        cls.critical_row = ConsequenceFactory(
            outcome_tier=cls.outcomes["critical"], label="Template pool: critical"
        )
        cls.success_row = ConsequenceFactory(
            outcome_tier=cls.outcomes["success"], label="Template pool: success"
        )
        ConsequenceEffectFactory(
            consequence=cls.success_row,
            effect_type=EffectType.SHIFT_NPC_REGARD,
            target=EffectTarget.TARGET,
            npc_regard_amount=5,
        )
        cls.failure_row = ConsequenceFactory(
            outcome_tier=cls.outcomes["failure"], label="Template pool: failure"
        )
        for row in (cls.critical_row, cls.success_row, cls.failure_row):
            ConsequencePoolEntryFactory(pool=template_pool, consequence=row)

        cls.break_check_type = CheckTypeFactory(name="Allegiance Break 4091")
        cls.enthralled = ConditionTemplateFactory(
            name="Enthralled 4091",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=cls.break_check_type,
            settle_consequence_pool=template_pool,
        )

        stage_pool = ConsequencePoolFactory(name="Fraying settle (stage)")
        cls.stage_success_row = ConsequenceFactory(
            outcome_tier=cls.outcomes["success"], label="Stage pool: success"
        )
        # A distinct amount (9, vs. the template pool's 5) lets a test prove
        # WHICH row actually fired by reading the real NpcRegardEvent, rather
        # than spying on the selection call.
        ConsequenceEffectFactory(
            consequence=cls.stage_success_row,
            effect_type=EffectType.SHIFT_NPC_REGARD,
            target=EffectTarget.TARGET,
            npc_regard_amount=9,
        )
        ConsequencePoolEntryFactory(pool=stage_pool, consequence=cls.stage_success_row)
        cls.fraying_stage = ConditionStageFactory(
            condition=cls.enthralled,
            name="Fraying",
            stage_order=1,
            severity_multiplier=Decimal("0.50"),
            settle_consequence_pool=stage_pool,
        )

        cls.unpooled_condition = ConditionTemplateFactory(
            name="Calmed 4091",
            sets_allegiance=Allegiance.NEUTRAL,
            allegiance_break_check_type=cls.break_check_type,
            settle_consequence_pool=None,
        )
        cls.non_allegiance_condition = ConditionTemplateFactory(name="Winded 4091")

        cls.room = ObjectDBFactory(
            db_key="Settle Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        cls.scene = SceneFactory(is_active=True, location=cls.room)
        cls.wren_char, cls.wren = CharacterContent.create_base_social_character(name="Wren")
        cls.tamsin_char, cls.tamsin = CharacterContent.create_base_social_character(name="Tamsin")
        cls.npc_char, cls.npc = CharacterContent.create_base_social_character(
            name="Enthralled Herald"
        )
        cls.wren_char.location = cls.room
        cls.tamsin_char.location = cls.room
        cls.npc_char.location = cls.room

    def _regard_event(self) -> NpcRegardEvent:
        return NpcRegardEvent.objects.get(
            regard__holder_persona=self.npc, regard__target_persona=self.tamsin
        )

    def test_settle_by_non_charmer_picks_template_pool_tier(self) -> None:
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.enthralled,
            severity=6,
            source_character=self.wren_char,
        )
        with force_check_outcome(self.outcomes["success"]):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())
        # The template pool's success row fired (amount 5), not the stage pool's (9).
        self.assertEqual(self._regard_event().amount, 5)

    def test_stage_pool_beats_template_pool(self) -> None:
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.enthralled,
            severity=6,
            current_stage=self.fraying_stage,
            source_character=self.wren_char,
        )
        with force_check_outcome(self.outcomes["success"]):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())
        # The stage pool's success row fired (amount 9), not the template's (5).
        self.assertEqual(self._regard_event().amount, 9)

    def test_no_pool_means_the_charm_just_ends(self) -> None:
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.unpooled_condition,
            severity=4,
            source_character=self.wren_char,
        )
        with force_check_outcome(self.outcomes["success"]):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())
        self.assertFalse(NpcRegardEvent.objects.filter(regard__holder_persona=self.npc).exists())

    def test_faded_charm_adds_less(self) -> None:
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.enthralled,
            severity=6,
            current_stage=self.fraying_stage,
            source_character=self.wren_char,
        )
        faded = allegiance_outcomes.settle_contributions(self.npc_char)[0].value

        instance.current_stage = None
        instance.save(update_fields=["current_stage"])
        full = allegiance_outcomes.settle_contributions(self.npc_char)[0].value

        self.assertLess(faded, full)

    def test_settle_without_a_charm_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )

    def test_settle_against_a_non_allegiance_condition_is_refused(self) -> None:
        """A condition with no ``sets_allegiance`` is never a charm to settle."""
        ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.non_allegiance_condition,
            severity=2,
        )
        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )

    def test_double_settle_is_refused(self) -> None:
        """Settling the same charm twice: the second attempt finds nothing to settle."""
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.enthralled,
            severity=6,
            source_character=self.wren_char,
        )
        with force_check_outcome(self.outcomes["success"]):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())

        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )

    def test_no_tier_opens_an_encounter(self) -> None:
        for tier in ("critical", "success", "failure"):
            instance = ConditionInstanceFactory(
                target=self.npc_char,
                condition=self.enthralled,
                severity=6,
                source_character=self.wren_char,
            )
            with force_check_outcome(self.outcomes[tier]):
                create_action_request(
                    scene=self.scene,
                    initiator_persona=self.tamsin,
                    target_persona=self.npc,
                    action_key="settle",
                )
            self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())
            self.assertEqual(CombatEncounter.objects.count(), 0)

    def test_settle_appears_in_scene_actions(self) -> None:
        keys = [a.ref.registry_key for a in _scene_actions(self.tamsin_char)]
        self.assertIn("settle", keys)

    def test_settle_outcome_is_the_narrators_interaction_in_the_scene(self) -> None:
        ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.enthralled,
            severity=6,
            source_character=self.wren_char,
        )
        with force_check_outcome(self.outcomes["success"]):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )
        line = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertEqual(line.scene, self.scene)
        self.assertEqual(line.persona.name, NARRATOR_PERSONA_NAME)
        self.assertEqual(line.content, self.success_row.label)

    def test_unauthored_tier_does_not_broadcast_a_synthetic_label(self) -> None:
        """No row at the rolled tier -> the generic ending line, never the raw outcome name."""
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.enthralled,
            severity=6,
            source_character=self.wren_char,
        )
        with force_check_outcome(self.botch_outcome):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.tamsin,
                target_persona=self.npc,
                action_key="settle",
            )
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())
        line = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertNotIn("Botch", line.content)
        persona_name = active_persona_for_sheet(self.npc_char.character_sheet).name
        self.assertEqual(line.content, f"The {self.enthralled.name} on {persona_name} ends.")
