"""Journeys through the pull of corruption a character carries: impulses (#5177).

Ysmay is a Sinner carrying 260 Ruin corruption (stage 2). Corvin is her Sineater, who carries
what he takes from her as the Mire. Hobb is the other player in the room. Ruin cares about
dread: a situation of Ruin holds while the character carries a "Dread" condition.

The stages begin at 50, 200 and 500 corruption. Intrusive Thoughts is stage 1 and Compulsion is
stage 2; a Sineater's cap is stage 2, so his corruption stops at 499 (500 - 1). The Compulsion
condition carries -3 on one check per point of severity; at stage 2 its severity is
2 - 2 + 1 = 1. Giving in adds 5 corruption. One unit of Sineating moves 60.

Numbers worked out by hand, not read from the code:

* Corvin takes on 2 units from Ysmay: 2 x 60 = 120 corruption. 120 is past 50 and short of
  200, so his Mire reads stage 1, and Ysmay drops 260 - 120 = 140.
* Corvin carrying 200 for her at stage 2 who gives in carries 200 + 5 = 205, and the 120 he
  holds for Ysmay becomes 120 + 5 = 125. Ysmay giving in carries 260 + 5 = 265.
* Corvin holding 450 with four units asked: 4 x 60 = 240 would move, but only 499 - 450 = 49
  fits, so Ysmay drops 260 - 49 = 211 and Corvin reads 499. Holding 499, nothing fits.
"""

from __future__ import annotations

from integration_tests.test_sineating_journeys import (
    SineatingJourneyCase,
    corruption,
)
from world.checks.factories import CheckTypeFactory
from world.checks.services import collect_check_modifiers
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import get_condition_instance
from world.covenants.perks.constants import Situation
from world.magic.constants import GainSource
from world.magic.factories import (
    KindledDeedAwardFactory,
    KindlingSituationFactory,
    MireHoldingFactory,
    RecordedActFactory,
    author_compulsion_condition,
)
from world.magic.models import MireHolding
from world.magic.models.aura import CharacterResonance
from world.magic.services.corruption import get_corruption_config
from world.magic.services.resonance import grant_resonance
from world.magic.tests.test_kindling import _tiers
from world.mechanics.factories import PropertyFactory
from world.relationships.models import CharacterRelationship

CONDITIONS = "/api/conditions/character/"
KINDLED = "/api/magic/kindled-resonances/"
IMPULSE = "The hunger is yours; feed it."
PULL = "Your Ruin pulls at you. Until you give in to it here, it clouds what you do."
GIVE_IN = (
    "You give in to your Ruin. It loosens its hold for now, and a little more of it stays with you."
)
TOO_MUCH = "You carry too much of the Mire to take on more. Settle some of it first."


class ImpulseJourneyCase(SineatingJourneyCase):
    """Ruin cares about dread; staff have authored a Compulsion that costs 3 a point."""

    def setUp(self) -> None:
        super().setUp()
        _tiers()
        self.check_type = CheckTypeFactory()
        self.compulsion = author_compulsion_condition(self.check_type, penalty=-3)
        feeling = PropertyFactory()
        self.ruin.feeling = feeling
        self.ruin.impulse_text = IMPULSE
        self.ruin.save()
        self.situation = KindlingSituationFactory(
            resonance=self.ruin, situation=Situation.OWN_FEELING, strength=1
        )
        self.dread = ConditionTemplateFactory(name="Dread")
        self.dread.properties.add(feeling)
        self.template = ConditionTemplate.objects.get(corruption_resonance=self.ruin)

    def carry(self, character, stage: int) -> None:
        """Make ``character`` carry exactly the threshold of ``stage`` in Ruin."""
        stage_row = self.template.stages.get(stage_order=stage)
        row, _ = CharacterResonance.objects.get_or_create(
            character_sheet=character.sheet_data, resonance=self.ruin
        )
        row.corruption_current = stage_row.severity_threshold
        row.save(update_fields=["corruption_current"])
        instance = ConditionInstance.objects.filter(target=character, condition=self.template)
        if instance.exists():
            instance.update(current_stage=stage_row, severity=stage_row.severity_threshold)
        else:
            ConditionInstanceFactory(
                target=character,
                condition=self.template,
                current_stage=stage_row,
                severity=stage_row.severity_threshold,
            )
        character.conditions.invalidate()

    def hold_dread(self, character) -> None:
        """Something Ruin cares about is here: the character carries Dread."""
        ConditionInstanceFactory(target=character, condition=self.dread)
        character.conditions.invalidate()

    def penalty(self, character) -> int:
        """What a roll of the Compulsion's check carries, from the aggregator every roll uses."""
        return collect_check_modifiers(character.sheet_data, self.check_type).total

    def compulsion_instance(self, character) -> ConditionInstance | None:
        return get_condition_instance(character, self.compulsion)

    def condition_names(self, account, character) -> list[str]:
        response = self.api(account).get(CONDITIONS, HTTP_X_CHARACTER_ID=str(character.pk))
        self.assertEqual(response.status_code, 200, response.content)
        return [row["name"] for row in response.json()]

    def deed(self, character) -> None:
        """A deed of Ruin: the grant a chosen mission option pays (a situation alone pays
        nothing, #5327; a marked act is the other way in, in the mark class below)."""
        with self.captureOnCommitCallbacks(execute=True):
            grant_resonance(
                character.sheet_data,
                self.ruin,
                10,
                source=GainSource.KINDLED_DEED,
                kindling_situation=self.situation,
                deed_label="Fed the hunger",
            )

    def holding(self) -> MireHolding:
        return MireHolding.objects.get(relationship__source=self.corvin.sheet_data)


class ASineatersMireAtTheFirstStage(ImpulseJourneyCase):
    """Intrusive Thoughts: a name on the condition, and the words once per scene."""

    def test_the_condition_is_named_and_the_words_arrive_once_with_no_penalty(self) -> None:
        self.entreat()
        self.perform(self.corvin)
        self.assertEqual(corruption(self.ysmay, self.ruin), 140)
        self.assertEqual(corruption(self.corvin, self.ruin), 120)

        names = self.condition_names(self.account_of(self.corvin), self.corvin)
        self.assertIn("Intrusive Thoughts: Ruin", names)
        self.assertNotIn(self.template.name, names)

        # Nothing Ruin cares about is here, so a pose says nothing of it.
        told = self.telnet(self.corvin, "pose waits by the door.")
        self.assertNotIn(IMPULSE, told)

        # Dread is here: the next pose sends the words once; the one after sends none.
        self.hold_dread(self.corvin)
        told = self.telnet(self.corvin, "pose watches the room.")
        self.assertIn(IMPULSE, told)
        told = self.telnet(self.corvin, "pose watches it still.")
        self.assertNotIn(IMPULSE, told)
        self.assertNotTold(self.hobb, IMPULSE)

        # No condition was applied, and a roll carries nothing.
        self.assertIsNone(self.compulsion_instance(self.corvin))
        self.assertEqual(self.penalty(self.corvin), 0)

        # The resonances panel shows it too.
        panel = self.telnet(self.corvin, "resonances")
        self.assertIn("Impulses", panel)
        self.assertIn("Intrusive Thoughts: Ruin - here now", panel)


class ASineatersMireAtTheSecondStage(ImpulseJourneyCase):
    """Compulsion: the penalty lands on a roll while Dread is here, and giving in lifts it."""

    def test_the_penalty_applies_and_a_deed_lifts_it_and_adds_to_the_mire(self) -> None:
        # Corvin carries 200 for Ysmay (stage 2); 120 of it is hers.
        self.carry(self.corvin, 2)
        relationship = CharacterRelationship.objects.get(
            source=self.corvin.sheet_data, target=self.ysmay.sheet_data
        )
        MireHoldingFactory(relationship=relationship, resonance=self.ruin, amount=120)
        self.hold_dread(self.corvin)
        self.assertIn(
            "Compulsion: Ruin", self.condition_names(self.account_of(self.corvin), self.corvin)
        )

        told = self.telnet(self.corvin, "pose steadies himself.")

        # Severity 2 - 2 + 1 = 1, so the roll carries -3 x 1.
        self.assertIn(PULL, told)
        self.assertEqual(self.compulsion_instance(self.corvin).severity, 1)
        self.assertEqual(self.penalty(self.corvin), -3)

        # Giving in: the deed lifts it for the scene and adds exactly 5 to what he carries.
        self.deed(self.corvin)
        self.assertTold(self.corvin, GIVE_IN)
        self.assertIsNone(self.compulsion_instance(self.corvin))
        self.assertEqual(self.penalty(self.corvin), 0)
        self.assertEqual(corruption(self.corvin, self.ruin), 205)
        self.assertEqual(self.holding().amount, 125)

        # It stays lifted for the rest of the scene.
        self.telnet(self.corvin, "pose breathes out.")
        self.assertIsNone(self.compulsion_instance(self.corvin))
        self.assertNotTold(self.hobb, PULL)


class ASinnersOwnCorruptionAtTheSecondStage(ImpulseJourneyCase):
    """The same pull on a Sinner's own corruption: 260 is stage 2."""

    def test_the_sinner_feels_the_same_and_giving_in_adds_five(self) -> None:
        self.hold_dread(self.ysmay)
        self.assertIn(
            "Compulsion: Ruin", self.condition_names(self.account_of(self.ysmay), self.ysmay)
        )

        told = self.telnet(self.ysmay, "pose clenches her hands.")

        self.assertIn(PULL, told)
        self.assertEqual(self.penalty(self.ysmay), -3)

        self.deed(self.ysmay)
        self.assertTold(self.ysmay, GIVE_IN)
        self.assertIsNone(self.compulsion_instance(self.ysmay))
        self.assertEqual(self.penalty(self.ysmay), 0)
        self.assertEqual(corruption(self.ysmay, self.ruin), 265)

    def test_a_pose_posted_on_the_web_pulls_at_her_the_same_way(self) -> None:
        self.hold_dread(self.ysmay)

        response = self.web_pose(self.ysmay_web, self.ysmay, "clenches her hands.")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTold(self.ysmay, PULL)
        self.assertEqual(self.penalty(self.ysmay), -3)

        # The panel's list carries the same impulse beside the resonances.
        listed = self.ysmay_web.get(KINDLED, {"character_sheet": self.ysmay.sheet_data.pk})
        self.assertEqual(listed.status_code, 200, listed.content)
        (impulse,) = listed.json()["impulses"]
        self.assertEqual(
            (impulse["label"], impulse["resonance_name"], impulse["present"]),
            ("Compulsion: Ruin", "Ruin", True),
        )
        self.assertTrue(impulse["is_compulsion"])


class MarkingAnActLiftsTheCompulsionButActingDoesNot(ImpulseJourneyCase):
    """Ysmay's Compulsion lifts when she marks a gain in Ruin in the scene (#5327), not when she
    acts: an act pays nothing by itself, so one she has not marked leaves the penalty in place
    and adds no corruption."""

    def test_acting_alone_keeps_it_and_marking_the_act_lifts_it_and_adds_five(self) -> None:
        success = self.outcomes["Success"]
        KindledDeedAwardFactory(outcome_tier=success, amount=10)
        act = RecordedActFactory(
            character_sheet=self.ysmay.sheet_data, outcome=success, label="Fed the hunger"
        )
        self.hold_dread(self.ysmay)

        told = self.telnet(self.ysmay, "pose clenches her hands.")

        self.assertIn(PULL, told)
        self.assertEqual(self.penalty(self.ysmay), -3)

        # Posing again, with her act still unmarked, changes nothing: no corruption is added.
        self.telnet(self.ysmay, "pose paces the floor.")
        self.assertEqual(self.penalty(self.ysmay), -3)
        self.assertEqual(corruption(self.ysmay, self.ruin), 260)
        self.assertNotTold(self.ysmay, GIVE_IN)

        # Marking the act with Ruin is giving in: the penalty lifts and 5 is added.
        with self.captureOnCommitCallbacks(execute=True):
            self.telnet(self.ysmay, f"pose/reach Ruin:{act.pk}=gives in to the hunger.")
        self.assertTold(self.ysmay, GIVE_IN)
        self.assertIsNone(self.compulsion_instance(self.ysmay))
        self.assertEqual(self.penalty(self.ysmay), 0)
        self.assertEqual(corruption(self.ysmay, self.ruin), 265)


class ASineatersCapIsTheTopOfTheCompulsionStage(ImpulseJourneyCase):
    """Trace 2: the ritual takes on only what fits below 500, and refuses when nothing does."""

    def test_the_ritual_takes_on_only_what_fits(self) -> None:
        self.assertEqual(get_corruption_config().sineater_max_stage, 2)
        self.carry(self.corvin, 2)
        row = CharacterResonance.objects.get(
            character_sheet=self.corvin.sheet_data, resonance=self.ruin
        )
        row.corruption_current = 450
        row.save(update_fields=["corruption_current"])
        self.entreat(units=4)

        told = self.perform(self.corvin, units=4)

        self.assertIn("You could take on only part of it", told)
        self.assertEqual(corruption(self.ysmay, self.ruin), 260 - 49)
        self.assertEqual(corruption(self.corvin, self.ruin), 499)
        self.assertEqual(self.holding().amount, 49)

    def test_the_ritual_refuses_when_nothing_fits(self) -> None:
        self.carry(self.corvin, 2)
        row = CharacterResonance.objects.get(
            character_sheet=self.corvin.sheet_data, resonance=self.ruin
        )
        row.corruption_current = 499
        row.save(update_fields=["corruption_current"])
        self.entreat()

        told = self.perform(self.corvin)

        self.assertIn(TOO_MUCH, told)
        self.assertEqual(corruption(self.ysmay, self.ruin), 260)
        self.assertEqual(corruption(self.corvin, self.ruin), 499)
        self.assertFalse(MireHolding.objects.exists())
