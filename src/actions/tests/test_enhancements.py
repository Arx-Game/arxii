"""Tests for the ActionEnhancement system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.base import Action
from actions.constants import EnhancementSourceType
from actions.definitions.communication import SayAction, WhisperAction
from actions.enhancements import get_involuntary_enhancements
from actions.models import ActionEnhancement
from actions.types import ActionContext, ActionResult, TargetType
from evennia_extensions.factories import ObjectDBFactory
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import TechniqueFactory


@dataclass
class EnhanceableTestAction(Action):
    """Test action that reads modifiers from context."""

    key: str = "test_enhanceable"
    name: str = "Test Enhanceable"
    icon: str = "test"
    category: str = "test"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: object,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        bonus = 0
        if context:
            bonus = context.modifiers.get("check_bonus", 0)
        return ActionResult(success=True, message=f"bonus={bonus}")


class ActionContextTests(TestCase):
    """Test that ActionContext is built and passed correctly during run()."""

    def test_run_builds_context_and_passes_to_execute(self) -> None:
        action = EnhanceableTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        result = action.run(actor)
        assert result.success is True
        assert result.message == "bonus=0"

    def test_run_passes_kwargs_through_context(self) -> None:
        @dataclass
        class KwargsReaderAction(Action):
            key: str = "kwargs_reader"
            name: str = "KR"
            icon: str = "test"
            category: str = "test"
            target_type: TargetType = TargetType.SELF

            def execute(
                self,
                actor: object,
                context: ActionContext | None = None,
                **kwargs: Any,
            ) -> ActionResult:
                return ActionResult(success=True, message=kwargs.get("text", ""))

        action = KwargsReaderAction()
        actor = ObjectDBFactory(db_key="Alice")
        result = action.run(actor, text="hello")
        assert result.message == "hello"


class VoluntaryEnhancementTests(TestCase):
    """Test that voluntary enhancements (passed explicitly) modify context."""

    def test_voluntary_enhancement_modifies_context(self) -> None:
        action = EnhanceableTestAction()
        actor = ObjectDBFactory(db_key="Alice")

        # Mock enhancement whose apply() adds a check bonus via modifiers
        mock_enh = MagicMock(spec=ActionEnhancement)
        mock_enh.apply = lambda ctx: ctx.modifiers.update({"check_bonus": 5})

        result = action.run(actor, enhancements=[mock_enh])
        assert result.success is True
        assert result.message == "bonus=5"

    def test_voluntary_enhancement_modifies_kwargs(self) -> None:
        @dataclass
        class TextAction(Action):
            key: str = "text_action"
            name: str = "Text"
            icon: str = "test"
            category: str = "test"
            target_type: TargetType = TargetType.AREA

            def execute(
                self,
                actor: object,
                context: ActionContext | None = None,
                **kwargs: Any,
            ) -> ActionResult:
                return ActionResult(success=True, message=kwargs.get("text", ""))

        action = TextAction()
        actor = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
        )
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor.location = room
        actor.save()

        # Mock enhancement whose apply() uppercases kwargs["text"]
        mock_enh = MagicMock(spec=ActionEnhancement)
        mock_enh.apply = lambda ctx: ctx.kwargs.update({"text": ctx.kwargs.get("text", "").upper()})

        result = action.run(actor, enhancements=[mock_enh], text="hello")
        assert result.message == "HELLO"


class PostEffectsTests(TestCase):
    """Test that post-effects are executed after the action."""

    def test_post_effects_run_after_execution(self) -> None:
        action = EnhanceableTestAction()
        actor = ObjectDBFactory(db_key="Alice")

        effects_log: list[str] = []

        def mock_apply(ctx: ActionContext) -> None:
            def post_effect(ctx: ActionContext) -> None:
                effects_log.append(f"result_was={ctx.result.success}")

            ctx.post_effects.append(post_effect)

        mock_enh = MagicMock(spec=ActionEnhancement)
        mock_enh.apply = mock_apply

        action.run(actor, enhancements=[mock_enh])
        assert effects_log == ["result_was=True"]

    def test_multiple_post_effects_run_in_order(self) -> None:
        action = EnhanceableTestAction()
        actor = ObjectDBFactory(db_key="Alice")

        order: list[int] = []

        def mock_apply(ctx: ActionContext) -> None:
            ctx.post_effects.append(lambda ctx: order.append(1))  # noqa: ARG005
            ctx.post_effects.append(lambda ctx: order.append(2))  # noqa: ARG005

        mock_enh = MagicMock(spec=ActionEnhancement)
        mock_enh.apply = mock_apply

        action.run(actor, enhancements=[mock_enh])
        assert order == [1, 2]


class InvoluntaryEnhancementQueryTests(TestCase):
    """Test get_involuntary_enhancements filtering logic."""

    def test_no_enhancements_returns_empty(self) -> None:
        actor = ObjectDBFactory(db_key="Alice")
        result = get_involuntary_enhancements("say", actor)
        assert result == []

    def test_filters_by_action_key_and_involuntary(self) -> None:
        actor = ObjectDBFactory(db_key="Alice")
        distinction = DistinctionFactory(name="Fire Tongue", slug="fire-tongue")

        # Involuntary enhancement for "say"
        enh = ActionEnhancement.objects.create(
            base_action_key="say",
            variant_name="Fiery Speech",
            is_involuntary=True,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )

        # Voluntary enhancement for "say" (should not be returned)
        ActionEnhancement.objects.create(
            base_action_key="say",
            variant_name="Whispered Speech",
            is_involuntary=False,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )

        # Involuntary enhancement for different action (should not be returned)
        ActionEnhancement.objects.create(
            base_action_key="look",
            variant_name="Dark Vision",
            is_involuntary=True,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )

        # Mock should_apply_enhancement on the Distinction model
        with patch.object(
            type(distinction),
            "should_apply_enhancement",
            create=True,
            return_value=True,
        ):
            results = get_involuntary_enhancements("say", actor)

        assert len(results) == 1
        assert results[0].pk == enh.pk

    def test_source_rejects_enhancement(self) -> None:
        actor = ObjectDBFactory(db_key="Alice")
        distinction = DistinctionFactory(name="Frost Voice", slug="frost-voice")

        ActionEnhancement.objects.create(
            base_action_key="say",
            variant_name="Icy Speech",
            is_involuntary=True,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )

        with patch.object(
            type(distinction),
            "should_apply_enhancement",
            create=True,
            return_value=False,
        ):
            results = get_involuntary_enhancements("say", actor)

        assert results == []

    def test_source_property_returns_distinction(self) -> None:
        distinction = DistinctionFactory(name="Eagle Eye", slug="eagle-eye")
        enh = ActionEnhancement.objects.create(
            base_action_key="look",
            variant_name="Enhanced Sight",
            is_involuntary=False,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )
        assert enh.source == distinction


class InvoluntaryEnhancementIntegrationTests(TestCase):
    """Test that involuntary enhancements are applied during run()."""

    def test_involuntary_enhancement_applied_during_run(self) -> None:
        action = EnhanceableTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        distinction = DistinctionFactory(name="Fire Curse", slug="fire-curse")

        # effect_parameters uses the standard vocabulary: add_modifiers
        ActionEnhancement.objects.create(
            base_action_key="test_enhanceable",
            variant_name="Fire Bonus",
            effect_parameters={"add_modifiers": {"check_bonus": 10}},
            is_involuntary=True,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=distinction,
        )

        # Only need should_apply_enhancement — apply() is on the ActionEnhancement
        with patch.object(
            type(distinction),
            "should_apply_enhancement",
            create=True,
            return_value=True,
        ):
            result = action.run(actor)

        assert result.success is True
        assert result.message == "bonus=10"


class LoudDistinctionScenarioTests(TestCase):
    """Scenario: A character with the 'Loud' distinction automatically shouts.

    The 'Loud' distinction is involuntary — the character doesn't choose it.
    When they say something, the enhancement fires automatically and uppercases
    their speech text. This tests the full database-driven involuntary workflow:

    1. Distinction exists in DB
    2. ActionEnhancement record links it to "say" as involuntary
    3. Character performs say action
    4. System queries involuntary enhancements, finds "Loud"
    5. Distinction confirms it applies to this actor
    6. Enhancement modifies kwargs["text"] to uppercase
    7. SayAction.execute() sees the modified text
    """

    def test_loud_distinction_uppercases_say_text(self) -> None:
        room = ObjectDBFactory(
            db_key="Tavern",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Grog",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        loud = DistinctionFactory(name="Loud", slug="loud")

        # effect_parameters uses standard vocabulary: modify_kwargs with "uppercase" transform
        ActionEnhancement.objects.create(
            base_action_key="say",
            variant_name="Booming Voice",
            effect_parameters={"modify_kwargs": {"text": "uppercase"}},
            is_involuntary=True,
            source_type=EnhancementSourceType.DISTINCTION,
            distinction=loud,
        )

        with (
            patch.object(
                type(loud),
                "should_apply_enhancement",
                create=True,
                return_value=True,
            ),
            patch.object(room, "msg_contents") as mock_msg,
        ):
            result = SayAction().run(actor, text="hello friends")

        assert result.success is True
        # The enhancement should have uppercased the text before execute() saw it.
        # msg_contents receives the formatted string — verify it contains "HELLO FRIENDS"
        mock_msg.assert_called_once()
        broadcast_text = mock_msg.call_args[0][0]
        assert "HELLO FRIENDS" in broadcast_text


class AlluringVoiceTechniqueScenarioTests(TestCase):
    """Scenario: A character activates 'Alluring Voice' before whispering.

    The player has the 'Alluring Voice' technique. Before whispering to someone,
    they select this technique as a voluntary enhancement. The workflow:

    1. Technique exists in DB
    2. ActionEnhancement record links it to "whisper" as voluntary
    3. Player selects the enhancement (UI passes it to action.run())
    4. Enhancement's apply_enhancement queues a post-effect
    5. WhisperAction.execute() sends the whisper normally
    6. Post-effect fires: applies a "charmed" modifier to the target

    The post-effect represents the charm taking hold after the whisper lands.
    In a full system this would trigger a check or apply a condition — here
    we verify the mechanics by tracking that the effect fires with the right
    context (correct target, after successful execution).
    """

    def test_alluring_voice_adds_charm_post_effect(self) -> None:
        room = ObjectDBFactory(
            db_key="Garden",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = ObjectDBFactory(
            db_key="Siren",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Mark",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        technique = TechniqueFactory(name="Alluring Voice")

        # effect_parameters uses standard vocabulary: post_effect with charm_check type
        enh = ActionEnhancement.objects.create(
            base_action_key="whisper",
            variant_name="Alluring Whisper",
            effect_parameters={"post_effect": "charm_check", "charm_strength": 3},
            is_involuntary=False,
            source_type=EnhancementSourceType.TECHNIQUE,
            technique=technique,
        )

        with patch.object(target, "msg"):
            result = WhisperAction().run(
                actor,
                enhancements=[enh],
                target=target,
                text="you look lovely tonight",
            )

        assert result.success is True
        # The post-effect should have fired after execution, writing to result.data
        post_effects = result.data.get("post_effects_applied", [])
        assert len(post_effects) == 1
        assert post_effects[0]["type"] == "charm_check"
        assert post_effects[0]["target"] == target
        assert post_effects[0]["charm_strength"] == 3
        assert post_effects[0]["action_succeeded"] is True
