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

from django.test import TestCase, override_settings

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.checks.types import ExtraTraitTerm
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
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
    CharacterAnimaFactory,
    FuryTierFactory,
    MagicActivitySkillFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.scenes.factories import SceneFactory
from world.skills.factories import SkillFactory
from world.skills.models import Skill
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.worship.rite_services import perform_worship_rite
from world.worship.tests.test_favor_invocation import (
    InvocationTestBase,
    _make_chosen as make_chosen,
)
from world.worship.tests.test_rites import RiteTestBase

SKILL_WEIGHT = Decimal("0.50")


def terms_for(skill: Skill) -> tuple[ExtraTraitTerm, ...]:
    """The one term a ``skill`` mapped at ``SKILL_WEIGHT`` adds to a roll."""
    return (ExtraTraitTerm(trait=skill.trait, weight=SKILL_WEIGHT),)


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
        cls.expected = terms_for(cls.skill)

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

    def assert_no_terms(
        self,
        target: str,
        activity: MagicActivity,
        drive: Callable[[], object],
        *,
        passes_terms: bool = True,
    ) -> None:
        """The activity is mapped, yet this roll carries no term.

        A site that always passes ``extra_traits`` must pass an empty tuple; one that never
        does (``passes_terms=False``) must not pass the keyword at all.
        """
        self.map_activity(activity)
        with roll_recorded(target) as calls, self.assertRaises(RollReached):
            drive()
        self.assertEqual(len(calls), 1)
        if passes_terms:
            self.assertEqual(calls[0]["extra_traits"], ())
        else:
            self.assertNotIn("extra_traits", calls[0])


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
        from world.magic.factories import TechniqueRemovedConditionFactory
        from world.magic.services.condition_application import remove_technique_conditions

        cure = CheckTypeFactory()
        condition = ConditionTemplateFactory(
            can_be_dispelled=True, cure_check_type=cure, cure_difficulty=5
        )
        target = CharacterSheetFactory().character
        ConditionInstanceFactory(target=target, condition=condition)
        source = CharacterSheetFactory().character
        row = TechniqueRemovedConditionFactory(condition=condition)

        self.assert_terms_reach(
            "world.magic.services.condition_application.perform_check_with_modifiers",
            MagicActivity.DISPELLING,
            lambda: remove_technique_conditions(
                technique=row.technique,
                success_level=1,
                eff_intensity=1,
                targets_by_kind={row.target_kind: [target]},
                source_character=source,
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


class ConditionRollSiteTests(ActivityTermTestCase):
    """Resist and break-free rolls add loss-of-self skills only for a marked category."""

    def template(self, *, marked: bool, **fields: object):
        category = ConditionCategoryFactory(adds_loss_of_self_skills=marked)
        return ConditionTemplateFactory(category=category, **fields)

    def test_loss_of_self_terms_only_for_marked_category(self) -> None:
        from world.conditions.services import loss_of_self_terms

        self.map_activity(MagicActivity.RESISTING_LOSS_OF_SELF)

        self.assertEqual(loss_of_self_terms(self.template(marked=True)), self.expected)
        self.assertEqual(loss_of_self_terms(self.template(marked=False)), ())

    def test_application_resist_marked(self) -> None:
        from world.conditions.services import _check_application_resist

        template = self.template(marked=True, resist_check_type=CheckTypeFactory())
        target = CharacterSheetFactory().character

        self.assert_terms_reach(
            "world.conditions.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: _check_application_resist(target, template),
        )

    def test_application_resist_unmarked(self) -> None:
        from world.conditions.services import _check_application_resist

        template = self.template(marked=False, resist_check_type=CheckTypeFactory())
        target = CharacterSheetFactory().character

        self.assert_no_terms(
            "world.conditions.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: _check_application_resist(target, template),
        )

    def test_stage_advance_resist_marked(self) -> None:
        from world.conditions.services import _perform_advancement_resist_check

        template = self.template(marked=True, has_progression=True)
        stage = ConditionStageFactory(condition=template, resist_check_type=CheckTypeFactory())
        instance = ConditionInstanceFactory(
            condition=template, target=CharacterSheetFactory().character
        )

        self.assert_terms_reach(
            "world.conditions.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: _perform_advancement_resist_check(instance, stage),
        )

    def test_break_free_marked(self) -> None:
        from world.conditions.constants import BreakFreeMode
        from world.conditions.services import attempt_break_free

        template = self.template(
            marked=True,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(),
            break_free_difficulty=10,
        )
        instance = ConditionInstanceFactory(
            condition=template, target=CharacterSheetFactory().character, is_aware=True
        )

        self.assert_terms_reach(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: attempt_break_free(instance, in_combat_tick=True),
        )

    def test_break_free_unmarked(self) -> None:
        from world.conditions.constants import BreakFreeMode
        from world.conditions.services import attempt_break_free

        template = self.template(
            marked=False,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(),
            break_free_difficulty=10,
        )
        instance = ConditionInstanceFactory(
            condition=template, target=CharacterSheetFactory().character, is_aware=True
        )

        self.assert_no_terms(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: attempt_break_free(instance, in_combat_tick=True),
        )

    def reveal_setup(self, *, marked: bool):
        template = self.template(marked=marked, break_free_check_type=CheckTypeFactory())
        template.category.alters_behavior = True
        template.category.save(update_fields=["alters_behavior"])
        target = CharacterSheetFactory().character
        ConditionInstanceFactory(condition=template, target=target, is_aware=False)
        return CharacterSheetFactory().character, target

    def test_reveal_condition_senses_a_loss_of_self(self) -> None:
        """Spotting a marked hold is sensing magic, not resisting it."""
        from actions.definitions.conditions import RevealConditionAction

        actor, target = self.reveal_setup(marked=True)
        MagicActivitySkillFactory(
            activity=MagicActivity.RESISTING_LOSS_OF_SELF, skill=self.other_skill
        )

        self.assert_terms_reach(
            "world.checks.services.perform_check",
            MagicActivity.SENSING_MAGIC,
            lambda: RevealConditionAction().execute(actor, target=target),
        )

    def test_reveal_condition_unmarked_adds_nothing(self) -> None:
        from actions.definitions.conditions import RevealConditionAction

        actor, target = self.reveal_setup(marked=False)

        self.assert_no_terms(
            "world.checks.services.perform_check",
            MagicActivity.SENSING_MAGIC,
            lambda: RevealConditionAction().execute(actor, target=target),
        )

    def test_rally_adds_no_loss_of_self_skill(self) -> None:
        """The rally roll is the helper's persuasion; the target's skills come in on the
        break-free that a critical rally triggers."""
        from actions.definitions.conditions import RallyAction
        from world.conditions.constants import BreakFreeMode

        template = self.template(
            marked=True,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(),
            break_free_difficulty=10,
        )
        template.category.alters_behavior = True
        template.category.save(update_fields=["alters_behavior"])
        target = CharacterSheetFactory().character
        ConditionInstanceFactory(condition=template, target=target, is_aware=True)
        actor = CharacterSheetFactory().character

        self.assert_no_terms(
            "world.checks.services.perform_check",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: RallyAction().execute(actor, target=target),
            passes_terms=False,
        )

    def peril(self, *, marked: bool):
        """A peril instance on a stage that rolls a resist check, with a one-row pool."""
        template = self.template(marked=marked, has_progression=True)
        stage = ConditionStageFactory(
            condition=template, resist_check_type=CheckTypeFactory(), resist_difficulty=5
        )
        sheet = CharacterSheetFactory()
        instance = ConditionInstanceFactory(
            condition=template, target=sheet.character, current_stage=stage
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=ConsequenceFactory())
        return sheet, instance, pool

    def test_peril_stage_resist_marked(self) -> None:
        from world.vitals.services import _resolve_peril_via_pool

        sheet, instance, pool = self.peril(marked=True)

        self.assert_terms_reach(
            "world.checks.consequence_resolution.perform_check",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: _resolve_peril_via_pool(sheet, instance, pool, death_permitted=False),
        )

    def test_peril_stage_resist_unmarked(self) -> None:
        from world.vitals.services import _resolve_peril_via_pool

        sheet, instance, pool = self.peril(marked=False)

        self.assert_no_terms(
            "world.checks.consequence_resolution.perform_check",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: _resolve_peril_via_pool(sheet, instance, pool, death_permitted=False),
        )

    def staged_peril(self, name: str, *, marked: bool) -> CharacterSheet:
        """A character on the first of two stages of the peril condition called ``name``.

        The per-round advance rolls the first stage's resist; the second stage keeps it
        non-terminal, so the terminal pool roll is not reached.
        """
        template = self.template(marked=marked, name=name, has_progression=True)
        first = ConditionStageFactory(
            condition=template,
            stage_order=1,
            resist_check_type=CheckTypeFactory(),
            resist_difficulty=5,
        )
        ConditionStageFactory(condition=template, stage_order=2)
        # Bleeding Out and Surrounded are found by designation (#4739), not by name.
        from world.conditions.constants import BLEED_OUT_SEED_TEMPLATE_NAME
        from world.vitals.peril_designations import designate_unset_peril_conditions

        if name == BLEED_OUT_SEED_TEMPLATE_NAME:
            designate_unset_peril_conditions(bleed_out=template)
        else:
            designate_unset_peril_conditions(surrounded=template)
        sheet = CharacterSheetFactory()
        ConditionInstanceFactory(condition=template, target=sheet.character, current_stage=first)
        return sheet

    def test_bleed_out_round_resist_marked(self) -> None:
        from world.conditions.constants import BLEED_OUT_SEED_TEMPLATE_NAME
        from world.vitals.services import advance_bleed_out

        sheet = self.staged_peril(BLEED_OUT_SEED_TEMPLATE_NAME, marked=True)

        self.assert_terms_reach(
            "world.vitals.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: advance_bleed_out(sheet),
        )

    def test_bleed_out_round_resist_unmarked(self) -> None:
        from world.conditions.constants import BLEED_OUT_SEED_TEMPLATE_NAME
        from world.vitals.services import advance_bleed_out

        sheet = self.staged_peril(BLEED_OUT_SEED_TEMPLATE_NAME, marked=False)

        self.assert_no_terms(
            "world.vitals.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: advance_bleed_out(sheet),
        )

    def test_surrounded_round_resist_marked(self) -> None:
        from world.battles.services import create_battle
        from world.conditions.constants import SURROUNDED_SEED_TEMPLATE_NAME
        from world.vitals.services import advance_surrounded

        sheet = self.staged_peril(SURROUNDED_SEED_TEMPLATE_NAME, marked=True)
        battle = create_battle(name="Round Resist Skills")

        self.assert_terms_reach(
            "world.vitals.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: advance_surrounded(sheet, battle=battle),
        )

    def test_surrounded_round_resist_unmarked(self) -> None:
        from world.battles.services import create_battle
        from world.conditions.constants import SURROUNDED_SEED_TEMPLATE_NAME
        from world.vitals.services import advance_surrounded

        sheet = self.staged_peril(SURROUNDED_SEED_TEMPLATE_NAME, marked=False)
        battle = create_battle(name="Round Resist Skills")

        self.assert_no_terms(
            "world.vitals.services.perform_check_with_modifiers",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: advance_surrounded(sheet, battle=battle),
        )

    def surrounded_entry(self, *, marked: bool):
        """An isolated battle participant, with the Surrounded entry content seeded."""
        from world.battles.constants import BattleSideRole
        from world.battles.services import add_place, add_side, create_battle, enlist_participant
        from world.vitals.factories import ensure_surrounded_content

        content = ensure_surrounded_content()
        category = content["condition"].category
        category.adds_loss_of_self_skills = marked
        category.save(update_fields=["adds_loss_of_self_skills"])
        battle = create_battle(name="Entry Skills")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        participant = enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=side, place=place
        )
        return SimpleNamespace(participant=participant)

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_surrounded_entry_resist_marked(self) -> None:
        from world.battles.resolution import _maybe_apply_surrounded

        declaration = self.surrounded_entry(marked=True)

        self.assert_terms_reach(
            "world.checks.consequence_resolution.perform_check",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: _maybe_apply_surrounded(declaration),
        )

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_surrounded_entry_resist_unmarked(self) -> None:
        from world.battles.resolution import _maybe_apply_surrounded

        declaration = self.surrounded_entry(marked=False)

        self.assert_no_terms(
            "world.checks.consequence_resolution.perform_check",
            MagicActivity.RESISTING_LOSS_OF_SELF,
            lambda: _maybe_apply_surrounded(declaration),
        )


class TreatmentRollSiteTests(ActivityTermTestCase):
    """A magical treatment adds the Magical treatment skills; mundane first aid does not."""

    def setUp(self) -> None:
        from world.conditions.constants import TreatmentTargetKind

        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.scene = SceneFactory(is_active=True)
        self.condition = ConditionTemplateFactory()
        self.wound = ConditionInstanceFactory(
            condition=self.condition, target=self.target_sheet.character
        )
        self.treatment = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=self.condition,
            scene_required=False,
            once_per_scene_per_helper=False,
            check_type=CheckTypeFactory(),
        )
        CharacterAnimaFactory(character=self.helper_sheet)

    def test_technique_treatment_adds_the_magical_treatment_skills(self) -> None:
        from world.magic.models.techniques import ConditionTargetKind, TechniqueTreatment
        from world.magic.services.condition_application import apply_technique_treatments

        technique = TechniqueFactory()
        TechniqueTreatment.objects.create(
            technique=technique,
            treatment_template=self.treatment,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )

        self.assert_terms_reach(
            "world.conditions.services.perform_check_with_modifiers",
            MagicActivity.MAGICAL_TREATMENT,
            lambda: apply_technique_treatments(
                technique=technique,
                success_level=3,
                eff_intensity=5,
                targets_by_kind={ConditionTargetKind.ALLY: [self.target_sheet.character]},
                source_character=self.helper_sheet.character,
                scene=self.scene,
            ),
        )

    def treat_through_the_scene_action(self, treatment) -> Callable[[], object]:
        """The ``treat_condition`` scene action's resolver, fed a request for ``treatment``."""
        from world.scenes.action_services import _resolve_treatment_request

        request = SimpleNamespace(
            treatment=treatment,
            target_condition_instance=self.wound,
            target_pending_alteration=None,
            initiator_persona=SimpleNamespace(character_sheet=self.helper_sheet),
            target_persona=SimpleNamespace(character_sheet=self.target_sheet),
            scene=self.scene,
            thread_used=None,
        )
        return lambda: _resolve_treatment_request(request)

    def test_zero_cost_bondless_scene_treatment_adds_no_skills(self) -> None:
        self.assert_no_terms(
            "world.conditions.services.perform_check_with_modifiers",
            MagicActivity.MAGICAL_TREATMENT,
            self.treat_through_the_scene_action(self.treatment),
        )

    def test_anima_costing_scene_treatment_adds_the_skills(self) -> None:
        self.treatment.anima_cost = 1
        self.treatment.save(update_fields=["anima_cost"])

        self.assert_terms_reach(
            "world.conditions.services.perform_check_with_modifiers",
            MagicActivity.MAGICAL_TREATMENT,
            self.treat_through_the_scene_action(self.treatment),
        )

    def test_bonded_and_resonance_costing_treatments_are_magical(self) -> None:
        from world.conditions.services import _treatment_skill_terms

        self.map_activity(MagicActivity.MAGICAL_TREATMENT)
        bonded = TreatmentTemplateFactory(requires_bond=True)
        resonant = TreatmentTemplateFactory(requires_bond=True, resonance_cost=2)

        self.assertEqual(_treatment_skill_terms(bonded, technique_driven=False), self.expected)
        self.assertEqual(_treatment_skill_terms(resonant, technique_driven=False), self.expected)
        self.assertEqual(_treatment_skill_terms(self.treatment, technique_driven=False), ())
        self.assertEqual(
            _treatment_skill_terms(self.treatment, technique_driven=True), self.expected
        )


class CombatAndSpeciesRollSiteTests(ActivityTermTestCase):
    def test_court_petition(self) -> None:
        from world.combat.pull_helpers import _resolve_emergency_draw
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CovenantFactory,
            make_engaged_member,
            wire_court_grant_petition_content,
            wire_court_role_powers_catalog,
        )
        from world.magic.constants import TargetKind
        from world.magic.factories import CharacterResonanceFactory
        from world.magic.models import Thread
        from world.magic.types.pull import CastPullDeclaration

        servant = CharacterSheetFactory()
        covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=CharacterSheetFactory())
        role, rows = wire_court_role_powers_catalog()
        resonance = rows[0].resonance
        make_engaged_member(character_sheet=servant, covenant=covenant, covenant_role=role)
        thread = Thread.objects.create(
            owner=servant,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            level=0,
            developed_points=0,
            name="Cord of the Shadowblade",
        )
        CharacterResonanceFactory(character_sheet=servant, resonance=resonance, balance=20)
        wire_court_grant_petition_content()
        declaration = CastPullDeclaration(
            resonance=resonance, tier=1, threads=(thread,), beseech_bonus=8
        )

        self.assert_terms_reach(
            "world.checks.services.perform_check",
            MagicActivity.COURT_PETITION,
            lambda: _resolve_emergency_draw(servant, declaration),
        )

    def test_sustaining_magic(self) -> None:
        from world.combat.constants import CONCENTRATION_CHECK_TYPE_NAME
        from world.combat.factories import CombatParticipantFactory
        from world.combat.services.encounter.sustained_absorption import (
            roll_sustained_absorption_budget,
        )

        CheckTypeFactory(name=CONCENTRATION_CHECK_TYPE_NAME)
        participant = CombatParticipantFactory()

        self.assert_terms_reach(
            "world.combat.services.encounter.sustained_absorption.perform_check_with_modifiers",
            MagicActivity.SUSTAINING_MAGIC,
            lambda: roll_sustained_absorption_budget(participant),
        )

    def test_moon_control(self) -> None:
        from world.species.moon_sensitivity import _control_holds

        sheet = CharacterSheetFactory()

        self.assert_terms_reach(
            "world.checks.services.perform_check",
            MagicActivity.MOON_CONTROL,
            lambda: _control_holds(sheet.character, sheet, 1, 1),
        )


class WorshipRiteRollTests(RiteTestBase):
    """A worship rite's roll carries the Worship rite skills."""

    def test_worship_rite(self) -> None:
        skill = SkillFactory()
        MagicActivitySkillFactory(
            activity=MagicActivity.WORSHIP_RITE, skill=skill, weight=SKILL_WEIGHT
        )
        with force_check_outcome(self.success) as capture:
            perform_worship_rite(self.sheet, self.rite, scene=self.scene)

        self.assertEqual(capture.extra_traits, terms_for(skill))


class InvocationRollTests(InvocationTestBase):
    """An invocation's roll carries the Invocation skills."""

    def test_invocation(self) -> None:
        skill = SkillFactory()
        MagicActivitySkillFactory(
            activity=MagicActivity.INVOCATION, skill=skill, weight=SKILL_WEIGHT
        )
        make_chosen(self.sheet, self.being, favor=44)

        _result, capture = self._invoke(self.success)

        self.assertEqual(capture.extra_traits, terms_for(skill))


class CeremonyRollSiteTests(ActivityTermTestCase):
    """A speech and the rite that closes a ceremony both carry the Ceremony skills."""

    def open_funeral(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.ceremonies.constants import CeremonyTypeKey
        from world.ceremonies.factories import CeremonyTypeFactory
        from world.ceremonies.services import open_ceremony
        from world.worship.factories import WorshippedBeingFactory
        from world.worship.models import WorshipDeclaration

        CeremonyTypeFactory(key=CeremonyTypeKey.FUNERAL, name="Funeral")
        officiant = CharacterSheetFactory()
        WorshipDeclaration.objects.create(
            character_sheet=officiant, public_being=WorshippedBeingFactory()
        )
        dead = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=dead, life_state=CharacterLifeState.DEAD)
        return open_ceremony(
            officiant_persona=officiant.primary_persona,
            type_key=CeremonyTypeKey.FUNERAL,
            honoree_sheets=[dead],
            location_profile=RoomProfileFactory(),
        )

    def test_speech(self) -> None:
        from world.ceremonies.services import SPEECH_CHECK_TYPE_NAME, record_speech

        CheckTypeFactory(name=SPEECH_CHECK_TYPE_NAME)
        ceremony = self.open_funeral()
        speaker = CharacterSheetFactory().primary_persona

        self.assert_terms_reach(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.CEREMONY,
            lambda: record_speech(ceremony=ceremony, speaker_persona=speaker),
        )

    def test_finishing_rite(self) -> None:
        from world.ceremonies.services import CEREMONY_CHECK_TYPE_NAME, finish_ceremony

        CheckTypeFactory(name=CEREMONY_CHECK_TYPE_NAME)
        ceremony = self.open_funeral()

        self.assert_terms_reach(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.CEREMONY,
            lambda: finish_ceremony(ceremony=ceremony),
        )

    def test_leak_sensing(self) -> None:
        """A witness to a twisted rite rolls Search with the SENSING_MAGIC terms."""
        from world.ceremonies.factories import CeremonyFactory
        from world.ceremonies.leak import run_twisted_rite_leak
        from world.clues.constants import SEARCH_CHECK_TYPE_NAME
        from world.roster.factories import RosterEntryFactory
        from world.secrets.factories import SecretFactory
        from world.worship.factories import WorshipDeclarationFactory, WorshippedBeingFactory

        officiant = RosterEntryFactory().character_sheet
        WorshipDeclarationFactory(character_sheet=officiant, secret=SecretFactory())
        CheckTypeFactory(name=SEARCH_CHECK_TYPE_NAME)
        ceremony = CeremonyFactory(
            being=WorshippedBeingFactory(), presented_being=WorshippedBeingFactory()
        )
        witness = RosterEntryFactory().character_sheet.character
        witness.location = ceremony.location.objectdb

        self.assert_terms_reach(
            "world.checks.services.perform_check_with_modifiers",
            MagicActivity.SENSING_MAGIC,
            lambda: run_twisted_rite_leak(ceremony=ceremony, officiant_sheet=officiant),
        )


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_charm_content gates on #2698
class CompanionBindingRollSiteTests(ActivityTermTestCase):
    """Binding a summoned being as a companion rolls with the COMPANION_BINDING skills."""

    def test_bind_attempt(self) -> None:
        from evennia import create_object

        from world.combat.constants import CombatAllegiance, OpponentStatus
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatOpponentFactory,
            ThreatPoolFactory,
        )
        from world.companions.content import ensure_companion_content
        from world.companions.factories import CompanionArchetypeFactory
        from world.companions.services import promote_summon_to_companion
        from world.magic.constants import TargetKind
        from world.magic.models.threads import Thread
        from world.magic.specialization.services import grant_gift_to_character

        sheet = CharacterSheetFactory()
        sheet.character.location = create_object("typeclasses.rooms.Room", key="Bind Roll Room")
        sheet.character.save()
        gift = ensure_companion_content()
        grant_gift_to_character(sheet, gift, resonance=gift.resonances.first())
        thread = Thread.objects.get(owner=sheet, target_kind=TargetKind.GIFT, target_gift=gift)
        thread.level = 10
        thread.save(update_fields=["level"])
        archetype = CompanionArchetypeFactory(bind_difficulty=20, capacity_cost=5)
        opponent = CombatOpponentFactory(
            encounter=CombatEncounterFactory(), threat_pool=ThreatPoolFactory()
        )
        opponent.allegiance = CombatAllegiance.ALLY
        opponent.summoned_by = sheet
        opponent.status = OpponentStatus.ACTIVE
        opponent.save(update_fields=["allegiance", "summoned_by", "status"])

        self.assert_terms_reach(
            "world.checks.services.perform_check",
            MagicActivity.COMPANION_BINDING,
            lambda: promote_summon_to_companion(
                caster_sheet=sheet,
                combat_opponent=opponent,
                archetype=archetype,
                granting_gift=gift,
                name="Bound Roll",
            ),
        )


@override_settings(SEED_SAMPLE_CONTENT=True)
class DreamPerilRollSiteTests(ActivityTermTestCase):
    """A dream's peril resist rolls with the DREAM_PERIL skills."""

    def test_peril_resist(self) -> None:
        from world.character_sheets.services import create_character_with_sheet
        from world.dreams.conditions import ensure_dream_conditions
        from world.dreams.peril import get_dream_peril_config, resolve_dream_peril_collapse
        from world.vitals.factories import create_dream_peril_pool
        from world.vitals.seeds import seed_survivability_content

        seed_survivability_content()
        ensure_dream_conditions()
        create_dream_peril_pool()
        config = get_dream_peril_config()
        config.resist_check_type = CheckTypeFactory()
        config.save(update_fields=["resist_check_type"])
        _char, sheet, _ = create_character_with_sheet(
            character_key="Roll Dreamer", primary_persona_name="Roll Dreamer"
        )

        self.assert_terms_reach(
            "world.checks.consequence_resolution.perform_check",
            MagicActivity.DREAM_PERIL,
            lambda: resolve_dream_peril_collapse(sheet),
        )


class NewActivityUnmappedTests(ActivityTermTestCase):
    """With no row for an activity, its roll adds nothing, whatever else is mapped (#4477)."""

    def test_unmapped_activities_add_nothing(self) -> None:
        from world.magic.services.magic_skills import activity_skill_terms

        MagicActivitySkillFactory(
            activity=MagicActivity.CEREMONY, skill=self.skill, weight=SKILL_WEIGHT
        )

        for activity in (MagicActivity.COMPANION_BINDING, MagicActivity.DREAM_PERIL):
            with self.subTest(activity=activity):
                self.assertEqual(activity_skill_terms(activity), ())


class TechniqueEnhancedConditionEffectTests(ActivityTermTestCase):
    """A condition effect's roll adds the technique skill only for a technique source (#4477)."""

    def drive(self, enhancement, *, remove: bool) -> list[dict]:
        """Run the apply or remove handler for ``enhancement``; return its roll's kwargs."""
        from actions.effects.conditions import (
            handle_condition_on_check,
            handle_remove_condition_on_check,
        )
        from actions.models import ConditionOnCheckConfig, RemoveConditionOnCheckConfig
        from actions.types import ActionContext

        context = ActionContext(
            action=SimpleNamespace(),
            actor=CharacterSheetFactory().character,
            target=CharacterSheetFactory().character,
            kwargs={},
            scene_data=SimpleNamespace(),
        )
        fields = {
            "enhancement": enhancement,
            "check_type": CheckTypeFactory(),
            "condition": ConditionTemplateFactory(),
            "target_difficulty": 10,
        }
        if remove:
            handler, config = (
                handle_remove_condition_on_check,
                RemoveConditionOnCheckConfig(**fields),
            )
        else:
            handler, config = handle_condition_on_check, ConditionOnCheckConfig(**fields)
        with roll_recorded("actions.effects.conditions.perform_check") as calls:
            with self.assertRaises(RollReached):
                handler(context, config)
        self.assertEqual(len(calls), 1)
        return calls

    def technique_enhancement(self, **technique_fields: object):
        from actions.factories import ActionEnhancementFactory

        return ActionEnhancementFactory(technique=TechniqueFactory(**technique_fields))

    def test_technique_source_adds_its_skill(self) -> None:
        enhancement = self.technique_enhancement(skill=self.skill)
        technique_terms = (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("1.00")),)

        for remove in (False, True):
            with self.subTest(remove=remove):
                calls = self.drive(enhancement, remove=remove)
                self.assertEqual(calls[0]["extra_traits"], technique_terms)

    def test_technique_without_a_skill_adds_nothing(self) -> None:
        enhancement = self.technique_enhancement()

        for remove in (False, True):
            with self.subTest(remove=remove):
                self.assertEqual(self.drive(enhancement, remove=remove)[0]["extra_traits"], ())

    def test_non_technique_source_adds_nothing(self) -> None:
        from actions.constants import EnhancementSourceType
        from actions.factories import ActionEnhancementFactory

        enhancement = ActionEnhancementFactory(
            source_type=EnhancementSourceType.CONDITION,
            technique=None,
            condition=ConditionTemplateFactory(),
        )

        for remove in (False, True):
            with self.subTest(remove=remove):
                self.assertEqual(self.drive(enhancement, remove=remove)[0]["extra_traits"], ())
