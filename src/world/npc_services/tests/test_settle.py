"""Settling a charm through the scene social pipeline (#4091, task 8)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from actions.player_interface import _scene_actions
from world.checks import consequence_resolution
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
from world.scenes.action_services import create_action_request
from world.scenes.factories import SceneFactory
from world.seeds.game_content.characters import CharacterContent
from world.traits.factories import CheckSystemSetupFactory


class SettleAllegianceTests(TestCase):
    """Settle resolves through the condition's settle pool, graded by roll tier."""

    @classmethod
    def setUpTestData(cls) -> None:
        setup = CheckSystemSetupFactory.create()
        cls.outcomes = setup["outcomes"]

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

        cls.scene = SceneFactory(is_active=True)
        cls.wren_char, cls.wren = CharacterContent.create_base_social_character(name="Wren")
        cls.tamsin_char, cls.tamsin = CharacterContent.create_base_social_character(name="Tamsin")
        cls.npc_char, cls.npc = CharacterContent.create_base_social_character(
            name="Enthralled Herald"
        )

    def setUp(self) -> None:
        super().setUp()
        # Spy on the real tier-selection call so tests can assert which pool row
        # was actually chosen, without depending on whether the selected
        # consequence's effect goes on to apply live (ResolutionContext here
        # carries no scene, same documented gap the rest of the social scene
        # pipeline has — see action_services._resolve_action_against_persona).
        self._captured_selections: list = []
        original = consequence_resolution.select_consequence_from_result

        def _spy(*args: object, **kwargs: object):
            pending = original(*args, **kwargs)
            self._captured_selections.append(pending)
            return pending

        patcher = mock.patch.object(
            consequence_resolution, "select_consequence_from_result", side_effect=_spy
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _selected(self, consequence) -> bool:
        return any(p.selected_consequence.pk == consequence.pk for p in self._captured_selections)

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
        self.assertTrue(self._selected(self.success_row))

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
        self.assertTrue(self._selected(self.stage_success_row))
        self.assertFalse(self._selected(self.success_row))

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
        self.assertEqual(self._captured_selections, [])

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
