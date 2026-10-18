"""Every non-technique magical roll adds the skills staff mapped to its activity (#4450).

Each test maps one skill to one ``MagicActivity``, drives the site's own function up to its
roll, and checks that exactly that skill's term reached the check entry point the site calls.
The recorder stops the site at the roll: what the site does with the result is covered by
that site's own tests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.types import ExtraTraitTerm
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.constants import (
    ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME,
    AffinityInteractionKind,
    MagicActivity,
    ResonanceDirection,
    ResonanceValence,
    RitualExecutionKind,
)
from world.magic.factories import (
    AffinityInteractionFactory,
    FuryTierFactory,
    MagicActivitySkillFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.skills.factories import SkillFactory

SKILL_WEIGHT = Decimal("0.50")


class RollReached(Exception):
    """Raised by the recorder so a site stops at its roll."""


@contextmanager
def roll_recorded(target: str) -> Iterator[list[dict]]:
    """Patch the check entry point at ``target``; yield the kwargs of each call it gets.

    The patched entry point records its call and raises :class:`RollReached`, so the site
    under test stops at its roll.
    """
    calls: list[dict] = []

    def record(*args: object, **kwargs: object) -> None:
        calls.append(kwargs)
        raise RollReached

    with patch(target, side_effect=record):
        yield calls


class ActivityTermTestCase(TestCase):
    """Maps one skill to the activity under test and one to an activity that must not leak."""

    activity: MagicActivity

    @classmethod
    def setUpTestData(cls) -> None:
        cls.skill = SkillFactory()
        cls.other_skill = SkillFactory()
        cls.expected = (ExtraTraitTerm(trait=cls.skill.trait, weight=SKILL_WEIGHT),)

    def map_activity(self, activity: MagicActivity) -> None:
        MagicActivitySkillFactory(activity=activity, skill=self.skill, weight=SKILL_WEIGHT)
        other = next(a for a in MagicActivity if a != activity)
        MagicActivitySkillFactory(activity=other, skill=self.other_skill)

    def assert_terms_reach(
        self, target: str, activity: MagicActivity, drive: Callable[[], object]
    ) -> None:
        """``drive`` runs a site; its roll at ``target`` must carry ``activity``'s terms."""
        self.map_activity(activity)
        with roll_recorded(target) as calls, self.assertRaises(RollReached):
            drive()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["extra_traits"], self.expected)


class MagicServiceRollSiteTests(ActivityTermTestCase):
    def test_anima_ritual(self) -> None:
        from world.magic.services.anima import perform_anima_ritual
        from world.scenes.factories import SceneFactory

        sheet = CharacterSheetFactory()
        account = AccountFactory()
        sheet.character.db_account = account
        sheet.character.save(update_fields=["db_account"])
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=account,
        )
        RitualCheckConfigFactory(ritual=ritual)
        scene = SceneFactory()

        with patch("world.magic.services.anima._scene_participant", return_value=True):
            self.assert_terms_reach(
                "world.checks.services.perform_check_with_modifiers",
                MagicActivity.ANIMA_RITUAL,
                lambda: perform_anima_ritual(sheet, scene),
            )

    def test_technique_learning_rolls_and_rates_the_teacher_with_the_terms(self) -> None:
        from world.magic.models import TechniqueProgress
        from world.magic.services.technique_training import resolve_training_check

        CheckTypeFactory(name="Technique Training")
        learner = CharacterSheetFactory()
        teacher = SimpleNamespace(character=CharacterSheetFactory().character)
        progress = TechniqueProgress.objects.create(
            character_sheet=learner,
            technique=TechniqueFactory(),
            total_required=50,
            source="gift_acquisition",
        )
        self.map_activity(MagicActivity.TECHNIQUE_LEARNING)
        rating_calls: list[dict] = []

        def rating(*args: object, **kwargs: object) -> int:
            rating_calls.append(kwargs)
            return 0

        with (
            patch(
                "world.magic.services.technique_training.compute_check_rating",
                side_effect=rating,
            ),
            roll_recorded(
                "world.magic.services.technique_training.perform_check_with_modifiers"
            ) as roll_calls,
            self.assertRaises(RollReached),
        ):
            resolve_training_check(learner, progress, ap_to_invest=1, teacher=teacher)

        self.assertEqual(rating_calls[0]["extra_traits"], self.expected)
        self.assertEqual(roll_calls[0]["extra_traits"], self.expected)

    def test_ritual_working_check(self) -> None:
        from world.magic.services.ritual_checks import perform_ritual_check

        ritual = RitualFactory(execution_kind=RitualExecutionKind.SERVICE)
        RitualCheckConfigFactory(ritual=ritual)
        character = CharacterSheetFactory().character

        self.assert_terms_reach(
            "world.checks.services.perform_check",
            MagicActivity.RITUAL_WORKING,
            lambda: perform_ritual_check(ritual.name, character),
        )

    def test_ritual_working_pool_gate(self) -> None:
        from world.magic.services.ritual_pool import resolve_pool_gate

        ritual = RitualFactory(anima_requirement=50)
        RitualCheckConfigFactory(ritual=ritual)
        sheet = CharacterSheetFactory()

        self.assert_terms_reach(
            "world.checks.services.perform_check",
            MagicActivity.RITUAL_WORKING,
            lambda: resolve_pool_gate(ritual=ritual, performer_sheet=sheet, pool=10),
        )

    def test_dispelling(self) -> None:
        from world.magic.services.condition_application import _attempt_removal

        cure = CheckTypeFactory()
        condition = ConditionTemplateFactory(
            can_be_dispelled=True, cure_check_type=cure, cure_difficulty=5
        )
        target = CharacterSheetFactory().character
        ConditionInstanceFactory(target=target, condition=condition)
        source = CharacterSheetFactory().character

        self.assert_terms_reach(
            "world.magic.services.condition_application.perform_check_with_modifiers",
            MagicActivity.DISPELLING,
            lambda: _attempt_removal(
                target=target,
                condition=condition,
                remove_all_stacks=False,
                source_character=source,
                cure_power_multiplier=Decimal(0),
                eff_intensity=1,
            ),
        )

    def test_soulfray_resilience(self) -> None:
        from world.magic.services.soulfray import _fire_stage_consequence_pool

        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=ConsequenceFactory())
        stage = ConditionStageFactory(consequence_pool=pool)
        config = SoulfrayConfigFactory()
        character = CharacterSheetFactory().character

        self.assert_terms_reach(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.SOULFRAY_RESILIENCE,
            lambda: _fire_stage_consequence_pool(
                character=character,
                current_stage=stage,
                soulfray_config=config,
                technique_check_result=None,
                lethal=True,
            ),
        )

    def test_soul_tether_rescue(self) -> None:
        from world.magic.seeds_checks import MAGICAL_ENDURANCE_CHECK_TYPE_NAME
        from world.magic.services.soul_tether import _perform_rescue_check

        CheckTypeFactory(name=MAGICAL_ENDURANCE_CHECK_TYPE_NAME)
        sheet = CharacterSheetFactory()

        self.assert_terms_reach(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.SOUL_TETHER_RESCUE,
            lambda: _perform_rescue_check(sheet),
        )

    def test_fury_control(self) -> None:
        from world.magic.services.fury import run_fury_for_action

        character = CharacterSheetFactory().character
        anchor = CharacterSheetFactory()
        tier = FuryTierFactory()

        self.assert_terms_reach(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.FURY_CONTROL,
            lambda: run_fury_for_action(
                character=character, fury_commitment=tier, fury_anchor=anchor
            ),
        )

    def test_enduring_hostile_resonance(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import CharacterAuraFactory
        from world.magic.services.resonance_environment import (
            ResonanceEnvironmentEffect,
            resonance_environment_for_cast,
        )

        CheckTypeFactory(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME)
        interaction = AffinityInteractionFactory(
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            consequence_pool=ConsequencePoolFactory(),
            caster_dominance_defiles=False,
        )
        effect = ResonanceEnvironmentEffect(
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            direction=ResonanceDirection.ENVIRONMENT_DOMINANT,
            magnitude=20,
            source_affinity=interaction.source_affinity,
            environment_affinity=interaction.environment_affinity,
            interaction=interaction,
            backfire_difficulty=30,
        )
        sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=sheet)
        room_profile = RoomProfileFactory()

        self.assert_terms_reach(
            "world.magic.services.resonance_environment.perform_check_with_modifiers",
            MagicActivity.ENDURING_HOSTILE_RESONANCE,
            lambda: resonance_environment_for_cast(
                caster_sheet=sheet,
                room_profile=room_profile,
                technique=None,
                effect=effect,
            ),
        )

    def test_feeding_restraint(self) -> None:
        from world.magic.services.feeding import RESTRAINT_CHECK_NAME, _restraint_holds

        CheckTypeFactory(name=RESTRAINT_CHECK_NAME)
        sheet = CharacterSheetFactory()

        self.assert_terms_reach(
            "world.checks.services.perform_check",
            MagicActivity.FEEDING_RESTRAINT,
            lambda: _restraint_holds(sheet),
        )

    def test_sensing_magic_cast_observation(self) -> None:
        from world.magic.services.cast_observation import _roll_cast_audience
        from world.magic.tests.services.test_cast_observation import (
            _caster_on_path_with_style,
            _observer_in_room_with,
            _ranged_technique,
        )

        caster = _caster_on_path_with_style(cast_concealment=10)
        _observer_in_room_with(caster)
        technique = _ranged_technique()

        self.assert_terms_reach(
            "world.magic.services.cast_observation.perform_check_with_modifiers",
            MagicActivity.SENSING_MAGIC,
            lambda: _roll_cast_audience(caster, technique, concealment=10),
        )
