"""Journeys for #4323: how a character ends a standoff shapes her resonance and her name.

Only the terms that settle the last group pay, so a long press earns nothing. What they pay
follows the roll's result tier through the staff-authored ending table; a legend deed is
written only when another player's character was on the scene list; two characters one
account plays pay each other nothing; and the existing kindling path feeds the same ending.
Each line is typed the way a player types it."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import CauseKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.conditions.factories import ConditionTemplateFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    KindlingSituationFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
    teach_ritual,
)
from world.magic.models import CharacterResonance, KindledDeedAward, ResonanceGrant
from world.magic.models.dramatic_moment import DramaticMomentTag
from world.mechanics.factories import PropertyFactory
from world.roster.models import RosterTenure
from world.scenes.factories import SceneParticipationFactory
from world.societies.factories import PhilosophicalArchetypeFactory
from world.societies.models import LegendEntry
from world.standoffs.constants import StandoffGroupState
from world.standoffs.factories import (
    StandoffApproachFactory,
    StandoffEndingAwardFactory,
    StandoffGroupFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import CharacterStandoffProfile, StandoffConfig, StandoffEndingAward
from world.standoffs.services.state import open_standoff
from world.traits.factories import CheckOutcomeFactory

TERMS_LINE = "standoff terms Spare Them (journey) Roadside Toughs"
PRESS_LINE = "standoff press Hard Stare (journey) Roadside Toughs"


class StandoffEndingBase(JourneyCase):
    """Ysmay faces the Roadside Toughs at the river gate; Corin stands watching."""

    def setUp(self) -> None:
        super().setUp()
        seed_scaling_defaults()
        self.gate = self.make_room("The River Gate")
        self.ysmay = self.make_player("Ysmay", room=self.gate)
        self.corin = self.make_player("Corin", room=self.gate)
        self.sheet = self.ysmay.sheet_data
        self.watch(self.corin)
        self.connect_telnet(self.ysmay)  # she is online, so her private lines reach her
        config = StandoffConfig.load()
        config.read_check_type = CheckTypeFactory()
        config.terms_check_type = CheckTypeFactory()
        config.pass_condition = ConditionTemplateFactory()
        config.save()
        self.stare = StandoffApproachFactory(name="Hard Stare (journey)")
        self.mercy = PhilosophicalArchetypeFactory(name="Mercy (journey)")
        self.spare = StandoffTermsFactory(name="Spare Them (journey)")
        self.spare.archetypes.add(self.mercy)
        self.toughs = CreatureTemplateFactory(name="Roadside Toughs", cause=CauseKind.NONE)
        self.encounter = CombatEncounterFactory(room=self.gate)
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        CombatOpponentFactory(
            encounter=self.encounter, creature_template=self.toughs, name="a tough"
        )
        open_standoff(self.encounter)
        # Her own resonance, the way an anima ritual records it (never the type's).
        self.mercy_resonance = ResonanceFactory(name="Mercy resonance (journey)")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.mercy_resonance)
        # The anima ritual is hers through her roster entry (#5280), as creation writes it.
        anima_ritual = RitualCheckConfigFactory(primal_resonance=self.mercy_resonance).ritual
        teach_ritual(anima_ritual, self.sheet)
        # Staff's table: the better the result, the more the ending pays.
        self.critical = CheckOutcomeFactory(name="Ending critical (journey)", success_level=2)
        self.success = CheckOutcomeFactory(name="Ending success (journey)", success_level=1)
        self.partial = CheckOutcomeFactory(name="Ending partial (journey)", success_level=0)
        for outcome, amount, magnitude, legend in (
            (self.critical, 30, "moderate", 400),
            (self.success, 15, "small", 200),
            (self.partial, 5, "small", 0),
        ):
            StandoffEndingAwardFactory(
                outcome_tier=outcome,
                legend_value=legend,
                moment_type=DramaticMomentTypeFactory(
                    label=f"Standoff ending {outcome.success_level} (journey)",
                    resonance=None,
                    resonance_amount=amount,
                    magnitude=magnitude,
                ),
            )

    def witness(self) -> None:
        """Put Corin on the scene list: another player's character who is there."""
        SceneParticipationFactory(scene=self.encounter.scene, account=self.account_of(self.corin))

    def say(self, outcome, line: str = TERMS_LINE, *, who=None) -> str:
        """Type ``line`` with the next roll forced; the after-commit lines are sent too."""
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(outcome):
            return self.telnet(who or self.ysmay, line)

    def assertNotShown(self, who, needle: str) -> None:  # noqa: N802 - unittest style
        """``who`` was pushed no row containing ``needle``."""
        rows = self.mailbox(who).rows
        self.assertFalse([row for row in rows if needle in row], rows)

    def assertNoCredit(self) -> None:  # noqa: N802 - unittest style
        """The room was pushed no line crediting an ending."""
        self.assertNotShown(self.corin, "ends it with")

    def earned(self) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.mercy_resonance
        ).lifetime_earned

    def deeds(self):
        return LegendEntry.objects.filter(persona=self.sheet.primary_persona)


class TheEndingPaysByTheResult(StandoffEndingBase):
    def test_a_witnessed_critical_ending_pays_her_own_resonance_renown_and_a_deed(self) -> None:
        self.witness()
        self.connect_telnet(self.corin)
        told = self.say(self.critical)
        self.assertIn("Critical success", told)
        self.assertEqual(self.encounter.standoff_groups.get().state, StandoffGroupState.SETTLED)
        self.assertEqual(self.earned(), 30)
        self.assertEqual(DramaticMomentTag.objects.filter(character_sheet=self.sheet).count(), 1)
        # Her name grows by the moderate tier's renown (the renown table's 150 fame).
        persona = self.sheet.primary_persona
        persona.refresh_from_db()
        self.assertEqual(persona.fame_points, 150)
        deed = self.deeds().get()
        self.assertEqual(deed.title, "Spare Them (journey): Roadside Toughs")
        self.assertEqual(deed.base_value, 400)
        self.assertEqual(list(deed.archetypes.all()), [self.mercy])
        # The room reads one credit line, naming the face she presents and the deed; the
        # resonance that grew is told to her alone.
        self.assertShownRow(self.corin, "Ysmay ends it with Spare Them (journey)")
        self.assertShownRow(self.corin, "it is written into their legend")
        self.assertTold(self.corin, "Ysmay ends it with Spare Them (journey)")
        self.assertNotShown(self.corin, "Mercy resonance (journey)")
        self.assertTold(self.ysmay, "You earned 30 Mercy resonance (journey)")
        self.assertNotTold(self.corin, "You earned")

    def test_a_partial_ending_pays_less_and_writes_no_deed(self) -> None:
        self.witness()
        self.say(self.partial)
        self.assertEqual(self.earned(), 5)
        self.assertFalse(self.deeds().exists())
        self.assertShownRow(self.corin, "their name carries further")
        self.assertTold(self.ysmay, "You earned 5 Mercy resonance (journey)")

    def test_an_unwitnessed_ending_pays_resonance_and_renown_but_writes_no_deed(self) -> None:
        # Only the actor and the system narrator (who wrote her press line) are on the
        # scene: nobody saw it.
        self.say(self.success, PRESS_LINE)
        self.say(self.success)
        self.assertEqual(self.earned(), 15)
        self.assertFalse(self.deeds().exists())
        self.assertShownRow(self.corin, "their name carries further")
        self.assertTold(self.ysmay, "You earned 15 Mercy resonance (journey)")

    def test_a_result_with_no_row_pays_nothing(self) -> None:
        self.witness()
        self.say(CheckOutcomeFactory(name="Ending untabled (journey)", success_level=1))
        self.assertEqual(self.earned(), 0)
        self.assertFalse(self.deeds().exists())
        self.assertFalse(DramaticMomentTag.objects.exists())
        self.assertNoCredit()


class ASpentCapPaysNothingFromTheTable(StandoffEndingBase):
    def test_a_moment_the_scene_already_paid_her_is_not_paid_again(self) -> None:
        self.witness()
        # A GM's hand-tag of the same moment type in this scene spent its per-scene cap.
        DramaticMomentTagFactory(
            moment_type=StandoffEndingAward.objects.get(outcome_tier=self.success).moment_type,
            character_sheet=self.sheet,
            scene=self.encounter.scene,
        )
        self.say(self.success)
        self.assertEqual(self.encounter.standoff_groups.get().state, StandoffGroupState.SETTLED)
        self.assertEqual(self.earned(), 0)
        self.assertFalse(self.deeds().exists())
        self.assertNoCredit()


class OnlyTheEndingPays(StandoffEndingBase):
    def test_a_long_press_and_a_settled_first_group_earn_nothing(self) -> None:
        self.witness()
        # A second band stays live, so settling the toughs does not end the standoff.
        wolves = CreatureTemplateFactory(name="Hungry Wolves", cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=wolves, name="a wolf")
        StandoffGroupFactory(encounter=self.encounter, creature_template=wolves)
        for _ in range(3):
            self.say(self.success, PRESS_LINE)
        self.assertEqual(self.earned(), 0)
        self.say(self.success)
        self.assertEqual(self.earned(), 0)
        self.assertFalse(DramaticMomentTag.objects.exists())
        self.assertFalse(self.deeds().exists())
        self.assertNoCredit()
        # The terms that settle the last band end it, and those pay.
        self.say(self.success, "standoff terms Spare Them (journey) Hungry Wolves")
        self.assertEqual(self.earned(), 15)
        self.assertEqual(DramaticMomentTag.objects.filter(character_sheet=self.sheet).count(), 1)
        self.assertShownRow(self.corin, "Ysmay ends it with Spare Them (journey)")


class TwoCharactersOfOneAccountPayNothing(StandoffEndingBase):
    def test_ending_a_standoff_against_her_own_players_other_character_pays_nothing(self) -> None:
        self.witness()
        maud = self.make_player("Maud", room=self.gate)
        # One account plays both Ysmay and Maud.
        ysmay_tenure = RosterTenure.objects.get(
            roster_entry=self.sheet.roster_entry, end_date__isnull=True
        )
        maud_tenure = RosterTenure.objects.get(
            roster_entry=maud.sheet_data.roster_entry, end_date__isnull=True
        )
        maud_tenure.player_data = ysmay_tenure.player_data
        maud_tenure.save()
        CharacterStandoffProfile.objects.create(sheet=maud.sheet_data, opted_in=True)
        CombatOpponentFactory(
            encounter=self.encounter,
            persona=maud.sheet_data.primary_persona,
            name="Maud",
        )
        StandoffGroupFactory(
            encounter=self.encounter,
            creature_template=None,
            persona=maud.sheet_data.primary_persona,
        )
        self.say(self.success)  # the toughs settle; Maud's group is still live
        self.say(self.success, "standoff terms Spare Them (journey) Maud")
        self.assertEqual(
            self.encounter.standoff_groups.filter(state=StandoffGroupState.SETTLED).count(), 2
        )
        self.assertEqual(self.earned(), 0)
        self.assertFalse(DramaticMomentTag.objects.exists())
        self.assertFalse(self.deeds().exists())
        self.assertNoCredit()


class TheEndingFeedsTheKindlingPath(StandoffEndingBase):
    def test_a_resonance_a_negotiation_kindles_earns_from_the_ending_by_the_result(self) -> None:
        # Staff authored: Mercy kindles in a negotiation and a kindled deed earns by result.
        KindledStrengthTierFactory(rank=1, earn_percent=100)
        KindlingSituationFactory(
            resonance=self.mercy_resonance, situation="during_negotiation", strength=1
        )
        KindledDeedAward.objects.all().delete()
        KindledDeedAwardFactory(outcome_tier=self.critical, amount=40)
        # No ending table row here: the kindling path pays on its own.
        StandoffEndingAward.objects.all().delete()
        self.say(self.critical)
        self.assertEqual(self.earned(), 40)
        grant = ResonanceGrant.objects.get(
            character_sheet=self.sheet, source=GainSource.KINDLED_DEED
        )
        self.assertEqual(grant.amount, 40)
        self.assertEqual(grant.deed_label, "Spare Them (journey): Roadside Toughs")
        self.assertTold(self.ysmay, "You earned 40")


class AnotherCharactersPressKindlesTheEndingForHer(StandoffEndingBase):
    """A parley-holder's press lays a feeling on the band; her ending then earns by it.

    Nothing here names a covenant or a role: staff author the kindling row, and what the
    other character does in the standoff (a press that lays a condition) is what makes it hold.
    """

    def setUp(self) -> None:
        super().setUp()
        awe = PropertyFactory(name="Awe (journey)")
        self.mercy_resonance.feeling = awe
        self.mercy_resonance.save()
        KindledStrengthTierFactory(rank=1, earn_percent=100)
        KindlingSituationFactory(
            resonance=self.mercy_resonance, situation="shared_feeling", strength=1
        )
        KindledDeedAward.objects.all().delete()
        KindledDeedAwardFactory(outcome_tier=self.success, amount=25)
        StandoffEndingAward.objects.all().delete()
        template = ConditionTemplateFactory(name="Awed (journey)")
        template.properties.add(awe)
        self.presence = StandoffApproachFactory(
            name="Commanding Presence (journey)", target_condition=template
        )
        self.corin_sheet = self.corin.sheet_data
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.corin_sheet)

    def kindled_grants(self):
        return ResonanceGrant.objects.filter(
            character_sheet=self.sheet, source=GainSource.KINDLED_DEED
        )

    def test_an_ending_with_the_band_not_awed_earns_no_kindled_resonance(self) -> None:
        self.say(self.success)
        self.assertFalse(self.kindled_grants().exists())
        self.assertNotTold(self.ysmay, "You earned")

    def test_corins_press_awes_the_band_and_her_ending_earns_by_it(self) -> None:
        pressed = self.say(
            self.success,
            "standoff press Commanding Presence (journey) Roadside Toughs",
            who=self.corin,
        )
        self.assertIn("Success", pressed)
        self.assertNotTold(self.ysmay, "You earned")
        self.say(self.success)
        grant = self.kindled_grants().get()
        self.assertEqual(grant.amount, 25)
        self.assertEqual(self.earned(), 25)
        self.assertTold(self.ysmay, "You earned 25")
