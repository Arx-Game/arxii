"""Impulses (#5177): the pull of corruption a character carries, for a Sinner and a Sineater.

Four behaviours, each proved at the service level where the journeys in
``integration_tests/test_impulse_journeys.py`` prove them through the real seams:

    1. Intrusive Thoughts: the condition reads "Intrusive Thoughts: <resonance>", and the
       resonance's impulse words are sent once per scene while its situation is present.
    2. Compulsion: the condition reads "Compulsion: <resonance>", a scene-scoped condition
       penalizes the character's rolls, a deed of the resonance lifts it and adds a little
       corruption (and to the Sineater's largest holding), and settling lifts it too.
    3. A Sinner at the same stages of their own corruption gets the same.
    4. Trace 2: a Sineater near the top of the Compulsion stage takes on only what fits, and
       is refused when nothing fits.

Numbers use the starting values: stages begin at 50, 200 and 500 corruption, the Intrusive
Thoughts stage is 1, the Compulsion stage is 2, a Sineater's cap is stage 2, and giving in adds
5 corruption. One unit of Sineating moves 60.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.serializers import ConditionInstanceSerializer
from world.conditions.services import get_check_modifier, get_condition_instance
from world.covenants.perks.constants import Situation
from world.magic.constants import GainSource, ImpulseKind
from world.magic.exceptions import SineatingValidationError
from world.magic.factories import (
    KindlingSituationFactory,
    MireHoldingFactory,
    PoseEndorsementFactory,
    ReflectionFactory,
    SettlingRiteFactory,
    author_compulsion_condition,
)
from world.magic.models import ImpulseShown, MireHolding
from world.magic.models.aura import CharacterResonance
from world.magic.models.corruption_config import CorruptionConfig
from world.magic.services.impulses import corruption_display_name, impulses_now, refresh_impulses
from world.magic.services.resonance import grant_resonance
from world.magic.services.sineating import request_sineating
from world.magic.tests.test_kindling import _tiers
from world.magic.tests.test_sineating import SineatingCase
from world.mechanics.factories import PropertyFactory
from world.relationships.models import CharacterRelationship

IMPULSE_TEXT = "The hunger is yours; feed it."


@override_settings(SEED_SAMPLE_CONTENT=True)
class _ImpulseCase(SineatingCase):
    """A tethered pair in a live scene, with a Compulsion condition and a situation that holds
    while the bearer carries "Dread". Subclasses name who bears the corruption."""

    bears_own = True  # True: the Sinner; False: the Sineater carrying for the Sinner

    def setUp(self) -> None:
        super().setUp()
        _tiers()
        self.check_type = CheckTypeFactory()
        self.compulsion = author_compulsion_condition(self.check_type, penalty=-3)
        feeling = PropertyFactory()
        self.resonance.feeling = feeling
        self.resonance.impulse_text = IMPULSE_TEXT
        self.resonance.save()
        self.situation = KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.OWN_FEELING, strength=1
        )
        self.dread = ConditionTemplateFactory(name="Dread")
        self.dread.properties.add(feeling)
        self.bearer = self.sinner if self.bears_own else self.sineater
        self.template = ConditionTemplate.objects.get(corruption_resonance=self.resonance)

    def carry(self, stage: int) -> ConditionInstance:
        """Make the bearer carry exactly the threshold of ``stage`` in the resonance."""
        stage_row = self.template.stages.get(stage_order=stage)
        row, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.bearer, resonance=self.resonance
        )
        row.corruption_current = stage_row.severity_threshold
        row.save(update_fields=["corruption_current"])
        instance = ConditionInstance.objects.filter(
            target=self.bearer.character, condition=self.template
        ).first()
        if instance is None:
            return ConditionInstanceFactory(
                target=self.bearer.character,
                condition=self.template,
                current_stage=stage_row,
                severity=stage_row.severity_threshold,
            )
        instance.current_stage = stage_row
        instance.severity = stage_row.severity_threshold
        instance.save()
        return instance

    def hold_situation(self) -> None:
        """Something this resonance cares about is here: the bearer carries Dread."""
        ConditionInstanceFactory(target=self.bearer.character, condition=self.dread)
        self.bearer.character.conditions.invalidate()

    def refresh(self):
        """Refresh the bearer's impulses; returns the result and the lines they were sent."""
        with (
            patch.object(self.bearer.character, "msg") as msg,
            patch.object(self.bearer.character.sessions, "all", return_value=[object()]),
        ):
            result = refresh_impulses(self.bearer, self.scene)
        return result, [call.args[0] for call in msg.call_args_list]

    def penalty(self) -> int:
        return get_check_modifier(self.bearer, self.check_type).total_modifier

    def compulsion_instance(self) -> ConditionInstance | None:
        return get_condition_instance(self.bearer.character, self.compulsion)

    def deed(self):
        """A deed of the resonance: the grant a chosen mission option pays (a situation alone
        pays nothing, #5327)."""
        with (
            patch.object(self.bearer.character, "msg") as msg,
            self.captureOnCommitCallbacks(execute=True),
        ):
            grant_resonance(
                self.bearer,
                self.resonance,
                10,
                source=GainSource.KINDLED_DEED,
                kindling_situation=self.situation,
                deed_label="Fed the hunger",
            )
        return [call.args[0] for call in msg.call_args_list]

    def grant_not_made_by_the_character(self, source: str) -> list[str]:
        """A grant of the compelled resonance that is not a deed of the bearer's own."""
        if source == GainSource.POSE_ENDORSEMENT:
            kwargs = {
                "pose_endorsement": PoseEndorsementFactory(
                    endorser_sheet=self.sineater if self.bears_own else self.sinner,
                    endorsee_sheet=self.bearer,
                    resonance=self.resonance,
                )
            }
        else:
            kwargs = {
                "settling_rite": SettlingRiteFactory(character_sheet=self.bearer),
                "reflection": ReflectionFactory(
                    character_sheet=self.bearer, resonance=self.resonance
                ),
            }
        with (
            patch.object(self.bearer.character, "msg") as msg,
            self.captureOnCommitCallbacks(execute=True),
        ):
            grant_resonance(self.bearer, self.resonance, 10, source=source, **kwargs)
        return [call.args[0] for call in msg.call_args_list]


class _IntrusiveThoughts:
    def test_the_condition_is_named_and_the_words_are_sent_once_per_scene(self) -> None:
        instance = self.carry(1)

        # Stage 1 reads Intrusive Thoughts; the template's own name is never shown.
        data = ConditionInstanceSerializer(instance).data
        self.assertEqual(data["name"], f"Intrusive Thoughts: {self.resonance.name}")
        self.assertEqual(
            corruption_display_name(self.template, 0, self.resonance), self.template.name
        )

        # Nothing she cares about is here: nothing is sent.
        _, told = self.refresh()
        self.assertEqual(told, [])
        self.assertFalse(impulses_now(self.bearer)[0].present)

        # It is here: the words are sent once, privately, and no condition is applied.
        self.hold_situation()
        result, told = self.refresh()
        self.assertEqual(told, [IMPULSE_TEXT])
        self.assertFalse(result.impulses[0].is_compulsion)
        self.assertIsNone(self.compulsion_instance())
        self.assertEqual(self.penalty(), 0)

        # A second pose in the same scene says nothing more.
        _, told = self.refresh()
        self.assertEqual(told, [])
        self.assertEqual(
            ImpulseShown.objects.filter(kind=ImpulseKind.INTRUSIVE, scene=self.scene).count(), 1
        )

    def test_a_character_with_no_session_is_not_told_and_nothing_is_spent(self) -> None:
        self.carry(1)
        self.hold_situation()

        with (
            patch.object(self.bearer.character, "msg") as msg,
            patch.object(self.bearer.character.sessions, "all", return_value=[]),
        ):
            result = refresh_impulses(self.bearer, self.scene)

        self.assertEqual(result.told, ())
        msg.assert_not_called()
        self.assertFalse(ImpulseShown.objects.filter(scene=self.scene).exists())
        # Once they are back at a session, the line is still theirs to be sent.
        self.assertEqual(self.refresh()[1], [IMPULSE_TEXT])

    def test_blank_words_fall_back_to_a_plain_line(self) -> None:
        self.resonance.impulse_text = ""
        self.resonance.save()
        self.carry(1)
        self.hold_situation()
        _, told = self.refresh()
        self.assertEqual(told, [f"Your {self.resonance.name} stirs at what is in front of you."])


class _Compulsion:
    def test_the_penalty_applies_giving_in_lifts_it_and_adds_a_little(self) -> None:
        instance = self.carry(2)
        corruption_before = 200  # stage 2 begins at 200
        self.assertEqual(
            ConditionInstanceSerializer(instance).data["name"],
            f"Compulsion: {self.resonance.name}",
        )
        holding = self._holding()

        # Present: the condition lands at severity 2 - 2 + 1 = 1, so the roll carries
        # -3 x 1 = -3, and she is told once.
        self.hold_situation()
        result, told = self.refresh()
        self.assertTrue(result.compulsion_applied)
        self.assertEqual(self.compulsion_instance().severity, 1)
        self.assertEqual(self.penalty(), -3)
        self.assertEqual(
            told,
            [
                f"Your {self.resonance.name} pulls at you. "
                "Until you give in to it here, it clouds what you do."
            ],
        )
        self.assertEqual(self.refresh()[1], [])
        self.assertEqual(self.penalty(), -3)

        # Giving in: a deed of the resonance lifts it for the scene and adds exactly 5.
        lines = self.deed()
        self.assertIsNone(self.compulsion_instance())
        self.assertEqual(self.penalty(), 0)
        self.assertEqual(self._corruption(), corruption_before + 5)
        self.assertIn(
            f"You give in to your {self.resonance.name}. It loosens its hold for now, "
            "and a little more of it stays with you.",
            lines,
        )
        if holding is not None:
            holding.refresh_from_db()
            self.assertEqual(holding.amount, 120 + 5)

        # It stays lifted: the next pose does not lay it again, and a second deed adds nothing.
        self.refresh()
        self.assertIsNone(self.compulsion_instance())
        self.deed()
        self.assertEqual(self._corruption(), corruption_before + 5)

    def test_only_a_deed_the_character_did_gives_in(self) -> None:
        self.carry(2)
        self.hold_situation()
        self.refresh()
        corruption_before = self._corruption()
        holding = self._holding()

        # A peer's endorsement and succumbing to the Mire grow the resonance, but the
        # character did not give in: the Compulsion stays, no corruption is added, no line is sent.
        for source in (GainSource.POSE_ENDORSEMENT, GainSource.SUCCUMBED):
            lines = self.grant_not_made_by_the_character(source)
            self.assertFalse([line for line in lines if line.startswith("You give in")], source)
            self.assertIsNotNone(self.compulsion_instance(), source)
            self.assertEqual(self._corruption(), corruption_before, source)
        # The next refresh still finds the resonance unearned and the Compulsion applies.
        result, _ = self.refresh()
        self.assertFalse(result.compulsion_lifted)
        self.assertEqual(self.penalty(), -3)
        if holding is not None:
            holding.refresh_from_db()
            self.assertEqual(holding.amount, 120)

        # A kindled deed still lifts it, adds the corruption and sends the line.
        lines = self.deed()
        self.assertIsNone(self.compulsion_instance())
        self.assertEqual(self._corruption(), corruption_before + 5)
        self.assertTrue([line for line in lines if line.startswith("You give in")])

    def test_a_deeper_stage_costs_more_and_settling_below_it_lifts_it(self) -> None:
        self.carry(2)
        self.hold_situation()
        self.refresh()
        self.assertEqual(self.penalty(), -3)

        # Stage 3 is severity 3 - 2 + 1 = 2: -3 x 2 = -6.
        self.carry(3)
        self.refresh()
        self.assertEqual(self.compulsion_instance().severity, 2)
        self.assertEqual(self.penalty(), -6)

        # Settled down to stage 1, nothing compels her any more.
        self.carry(1)
        result, _ = self.refresh()
        self.assertTrue(result.compulsion_lifted)
        self.assertIsNone(self.compulsion_instance())

    def test_an_unset_compulsion_condition_applies_nothing(self) -> None:
        from world.magic.services.corruption import get_corruption_config

        cfg = get_corruption_config()
        cfg.compulsion_condition = None
        cfg.save()
        self.carry(2)
        self.hold_situation()
        result, told = self.refresh()
        self.assertFalse(result.compulsion_applied)
        self.assertEqual(self.penalty(), 0)
        self.assertEqual(len(told), 1)

    def _corruption(self) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.bearer, resonance=self.resonance
        ).corruption_current

    def _holding(self) -> MireHolding | None:
        """The Sineater carries 120 of it for the Sinner; a Sinner holds for no one."""
        if self.bears_own:
            return None
        relationship = CharacterRelationship.objects.get(source=self.sineater, target=self.sinner)
        return MireHoldingFactory(relationship=relationship, resonance=self.resonance, amount=120)


class SinnerIntrusiveThoughtsTests(_IntrusiveThoughts, _ImpulseCase):
    bears_own = True


class SineaterIntrusiveThoughtsTests(_IntrusiveThoughts, _ImpulseCase):
    bears_own = False


class SinnerCompulsionTests(_Compulsion, _ImpulseCase):
    bears_own = True


class SineaterCompulsionTests(_Compulsion, _ImpulseCase):
    bears_own = False


@override_settings(SEED_SAMPLE_CONTENT=True)
class SineaterCapTests(SineatingCase):
    """Trace 2. The cap is stage 2, so the Sineater's corruption stops at 499 (stage 3 begins
    at 500). One unit moves 60 and there is no resistance yet."""

    def hold(self, amount: int) -> None:
        row, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.sineater, resonance=self.resonance
        )
        row.corruption_current = amount
        row.save(update_fields=["corruption_current"])

    def test_the_ritual_takes_on_only_what_fits_below_the_top_of_the_stage(self) -> None:
        # Holding 450 leaves 499 - 450 = 49 of room. Four units ask for 240; 49 move.
        self.hold(450)
        request_sineating(self.sinner, self.sineater, 4)

        result = self.perform(4)

        self.assertTrue(result.cut_by_ceiling)
        self.assertEqual((result.corruption_left_sinner, result.corruption_taken), (49, 49))
        self.assertEqual(self.corruption(self.sinner), 500 - 49)
        self.assertEqual(self.corruption(self.sineater), 499)
        self.assertEqual(MireHolding.objects.get(relationship__source=self.sineater).amount, 49)

    def test_the_ritual_refuses_when_nothing_fits(self) -> None:
        self.hold(499)
        request_sineating(self.sinner, self.sineater, 2)

        with self.assertRaises(SineatingValidationError) as ctx:
            self.perform(2)

        self.assertEqual(
            ctx.exception.user_message,
            "You carry too much of the Mire to take on more. Settle some of it first.",
        )
        self.assertEqual(self.corruption(self.sinner), 500)
        self.assertEqual(self.corruption(self.sineater), 499)


class CorruptionConfigCleanTests(TestCase):
    def test_the_compulsion_cannot_begin_before_intrusive_thoughts(self) -> None:
        config = CorruptionConfig(
            intrusive_thoughts_stage=3, compulsion_stage=2, sineater_max_stage=3
        )

        with self.assertRaises(ValidationError) as ctx:
            config.clean()

        self.assertEqual(list(ctx.exception.message_dict), ["compulsion_stage"])

    def test_the_starting_stages_are_valid(self) -> None:
        CorruptionConfig(
            intrusive_thoughts_stage=1, compulsion_stage=2, sineater_max_stage=2
        ).clean()
