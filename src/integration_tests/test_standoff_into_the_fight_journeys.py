"""Journeys for slice 4 of #4759 (#4808): what a party does in a standoff carries into the
fight. A press that succeeds lays its approach's conditions; the party springing the fight
makes round one an ambush; and a vow perk that answers during a negotiation reaches the
standoff's own rolls. Each line is typed the way a player types it."""

from __future__ import annotations

from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.services import _compute_check_breakdown, perform_check
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import CauseKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.combat.round_context import CombatRoundContext
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import has_condition
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks import evaluators
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.covenants.perks.context import NO_PARAMS, SituationContext
from world.magic.factories import ThreadFactory
from world.mechanics.factories import PropertyFactory
from world.scenes.interaction_services import get_active_scene
from world.standoffs.constants import StandoffGroupState
from world.standoffs.factories import CreatureDriveFactory, StandoffApproachFactory
from world.standoffs.models import StandoffConfig
from world.standoffs.services.state import open_standoff
from world.traits.factories import CheckOutcomeFactory

SPY = "world.standoffs.services.verbs.perform_check"
PERK_BONUS = 10  # magnitude_tenths 10 at thread level 10


class StandoffJourneyBase(JourneyCase):
    """Ysmay faces a band of Roadside Toughs at the river gate, one tough standing."""

    def setUp(self) -> None:
        super().setUp()
        seed_scaling_defaults()
        self.gate = self.make_room("The River Gate")
        self.ysmay = self.make_player("Ysmay", room=self.gate)
        self.sheet = self.ysmay.sheet_data
        config = StandoffConfig.load()
        config.read_check_type = CheckTypeFactory()
        config.terms_check_type = CheckTypeFactory()
        config.save()
        self.read_check = config.read_check_type
        self.unnerved = ConditionTemplateFactory(name="Unnerved (journey)")
        self.steadied = ConditionTemplateFactory(name="Steadied (journey)")
        self.menace = StandoffApproachFactory(
            name="Bored Menace (journey)",
            target_condition=self.unnerved,
            ally_condition=self.steadied,
        )
        self.toughs = CreatureTemplateFactory(name="Roadside Toughs", cause=CauseKind.NONE)
        CreatureDriveFactory(
            creature_template=self.toughs, property=PropertyFactory(name="Greedy (journey)")
        )
        self.encounter = CombatEncounterFactory(room=self.gate)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        self.tough = CombatOpponentFactory(
            encounter=self.encounter, creature_template=self.toughs, name="a tough"
        )
        open_standoff(self.encounter)
        self.success = CheckOutcomeFactory(name="Standoff success (journey)", success_level=1)

    def press(self, outcome) -> str:
        with force_check_outcome(outcome):
            return self.telnet(self.ysmay, "standoff press Bored Menace (journey) Roadside Toughs")


class PressCarriesIntoTheAmbush(StandoffJourneyBase):
    def test_a_successful_press_unnerves_them_and_springing_it_is_an_ambush(self) -> None:
        told = self.press(self.success)
        self.assertIn("Success", told)
        self.assertTrue(has_condition(self.tough.objectdb, self.unnerved))
        self.assertTrue(has_condition(self.ysmay, self.steadied))

        told = self.telnet(self.ysmay, "standoff fight")
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.round_number, 1, told)
        self.assertTrue(self.encounter.initiated_by_pc_side)
        self.assertTrue(self.encounter.opened_from_parley)
        self.assertEqual(
            set(self.encounter.standoff_groups.values_list("state", flat=True)),
            {StandoffGroupState.FIGHTING},
        )
        # Round one: the tough is still unnerved, and the ambush perk's situation holds
        # for Ysmay's round-one resolution.
        self.assertTrue(has_condition(self.tough.objectdb, self.unnerved))
        ctx = SituationContext(
            holder=self.sheet,
            subject=self.sheet,
            target=None,
            resolution=CombatRoundContext(self.participant),
        )
        self.assertTrue(evaluators.ambush_underway(ctx, NO_PARAMS))
        self.assertTrue(evaluators.combat_opened_from_parley(ctx, NO_PARAMS))

    def test_a_failed_or_botched_press_lays_nothing(self) -> None:
        for level in (0, -1, -2):
            outcome = CheckOutcomeFactory(
                name=f"Standoff tier {level} (journey)", success_level=level
            )
            told = self.press(outcome)
            self.assertNotIn("Success.", told)
            self.assertFalse(has_condition(self.tough.objectdb, self.unnerved), level)
            self.assertFalse(has_condition(self.ysmay, self.steadied), level)


class NegotiationPerkReachesTheRead(StandoffJourneyBase):
    """Ysmay's vow answers during a negotiation, and a standoff read is one."""

    def setUp(self) -> None:
        super().setUp()
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=CovenantFactory(), covenant_role=role, engaged=True
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.DURING_NEGOTIATION)
        ThreadFactory(owner=self.sheet, level=10)

    def _read_total(self) -> tuple[int, int]:
        """The read's rolled total, and the total the same roll has with no situation."""
        captured: list[tuple[int, dict]] = []

        def spy(*args, **kwargs):
            result = perform_check(*args, **kwargs)
            captured.append((result.total_points, kwargs))
            return result

        with force_check_outcome(self.success), patch(SPY, side_effect=spy):
            told = self.telnet(self.ysmay, "standoff read Roadside Toughs")
        self.assertIn("You study them", told)
        total, kwargs = captured[0]
        baseline = _compute_check_breakdown(
            self.ysmay,
            self.read_check,
            target_difficulty=kwargs["target_difficulty"],
            extra_modifiers=kwargs["extra_modifiers"],
            effort_level=None,
            fatigue_penalty=0,
            specialization=None,
            situation_ctx=None,
        ).total_points
        return total, baseline

    def test_the_negotiation_perk_raises_the_read(self) -> None:
        # The standoff's own encounter scene is the active scene at the gate, so the
        # read is a negotiation with no extra setup.
        self.assertEqual(get_active_scene(self.gate), self.encounter.scene)
        total, baseline = self._read_total()
        self.assertEqual(total, baseline + PERK_BONUS)
