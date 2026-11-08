"""Journeys for vow perks that answer a busy or distracted enemy (#5020).

Mira and Tomas are played fighters in one declaring round-1 encounter on "The Road", against
a Bandit Captain and a Bandit Guard. Ilse fights beside them but is in no covenant. Mira's
engaged vow carries a power perk of +10 tenths per thread level, scaled by the STRIKER's own
thread total. Mira and Tomas (her covenant-mate, with his own engaged vow) each hold one thread
shown at level 3 and stored at 30 (#4585), so a firing adds 30 x 10 / 10 = 30 power to the
striker's technique (the "vow situational power" line of the round's power breakdown) and
announces itself.

Mira declares her technique at the captain through dispatch and the round resolves. What the
captain is doing this round is set the way staff or a simulation sets it before resolution: an
attack row aimed at someone, a telegraphed wind-up, or nothing at all.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    PendingOpponentAttackFactory,
    ThreatPoolEntryFactory,
)
from world.combat.services import resolve_round
from world.conditions.factories import ConditionInstanceFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
    engage_vow_with_thread,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.fatigue.constants import EffortLevel
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.scenes.constants import RoundStatus
from world.scenes.models import InteractionPowerLedgerEntry
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from collections.abc import Iterator

    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatOpponent, CombatParticipant

PAYOFF = 30
VOW_LABEL = "vow situational power"


@contextmanager
def every_check_succeeds() -> Iterator[None]:
    """Every combat check in the block lands at Success."""
    outcome = CheckOutcome.objects.get(name="Success")

    def forced(*args: object, **kwargs: object) -> object:
        with force_check_outcome(outcome):
            return perform_check(*args, **kwargs)

    with patch("world.combat.services.perform_check", side_effect=forced):
        yield


class _BanditFight(JourneyCase):
    """The road, the fighters, the bandits and Mira's vow; subclasses author the perk."""

    SITUATION: str = ""
    BENEFICIARY: str = PerkBeneficiary.SELF
    ANNOUNCE = "vow finds the opening!"

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.road = self.make_room("The Road")
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.strike = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.road
        )
        self.seats: dict[ObjectDB, CombatParticipant] = {}
        self.mira = self.fighter("Mira")
        self.tomas = self.fighter("Tomas")
        self.ilse = self.fighter("Ilse")
        self.captain = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit Captain", health=500, max_health=500
        )
        self.guard = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit Guard", health=500, max_health=500
        )

        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        mira_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(self.mira.sheet_data, mira_role, covenant=covenant, thread_level=3)
        perk = VowSituationalPerkFactory(
            covenant_role=mira_role,
            beneficiary=self.BENEFICIARY,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=10,
            announce_template="{holder}'s " + self.ANNOUNCE,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=self.SITUATION)
        tomas_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(self.tomas.sheet_data, tomas_role, covenant=covenant, thread_level=3)
        self.watch(self.mira, self.tomas)

    def fighter(self, name: str) -> ObjectDB:
        """A played character on the road, in the fight, who knows the strike."""
        player = self.make_player(name, room=self.road)
        sheet = player.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterTechniqueFactory(character=sheet, technique=self.strike)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        self.seats[player] = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        return player

    def bandit_attacks(
        self,
        bandit: CombatOpponent,
        *,
        at: tuple[ObjectDB, ...] = (),
        at_bandits: tuple[CombatOpponent, ...] = (),
    ) -> None:
        """The bandit's attack this round, aimed at these fighters or other bandits."""
        attack = CombatOpponentActionFactory(
            opponent=bandit,
            round_number=1,
            threat_entry=ThreatPoolEntryFactory(pool=bandit.threat_pool),
        )
        attack.targets.set([self.seats[player] for player in at])
        attack.opponent_targets.set(at_bandits)

    def strikes(self, striker: ObjectDB, target: CombatOpponent) -> int:
        """``striker`` declares the strike at ``target`` through dispatch; the round resolves.

        Returns the vow line of the striker's power breakdown (0 when the vow added nothing).
        """
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=self.strike.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            striker,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": target.pk},
        )
        self.assertTrue(declared.deferred, declared)
        with every_check_succeeds():
            resolve_round(self.encounter)
        return sum(
            InteractionPowerLedgerEntry.objects.filter(
                interaction__persona=striker.sheet_data.primary_persona,
                source_label=VOW_LABEL,
            ).values_list("amount", flat=True)
        )


class StrikingAnEnemyBusyWithSomeoneElse(_BanditFight):
    """Mira's perk answers "Target Focused Elsewhere"."""

    SITUATION = Situation.TARGET_FOCUSED_ELSEWHERE

    def test_the_captain_swinging_at_tomas_pays_off(self) -> None:
        self.bandit_attacks(self.captain, at=(self.tomas,))

        self.assertEqual(self.strikes(self.mira, self.captain), PAYOFF)
        self.assertTold(self.mira, self.ANNOUNCE)

    def test_the_captain_swinging_at_mira_pays_nothing(self) -> None:
        self.bandit_attacks(self.captain, at=(self.mira,))

        self.assertEqual(self.strikes(self.mira, self.captain), 0)
        self.assertNotTold(self.mira, self.ANNOUNCE)

    def test_the_captain_swinging_at_both_pays_nothing(self) -> None:
        self.bandit_attacks(self.captain, at=(self.mira, self.tomas))

        self.assertEqual(self.strikes(self.mira, self.captain), 0)
        self.assertNotTold(self.mira, self.ANNOUNCE)

    def test_a_captain_with_no_attack_this_round_pays_nothing(self) -> None:
        self.bandit_attacks(self.guard, at=(self.tomas,))

        self.assertEqual(self.strikes(self.mira, self.captain), 0)
        self.assertNotTold(self.mira, self.ANNOUNCE)

    def test_the_captain_winding_up_on_tomas_pays_off(self) -> None:
        PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.captain,
            threat_entry=ThreatPoolEntryFactory(pool=self.captain.threat_pool, windup_rounds=1),
            target=self.seats[self.tomas],
            declared_round=1,
            resolves_round=2,
        )

        self.assertEqual(self.strikes(self.mira, self.captain), PAYOFF)
        self.assertTold(self.mira, self.ANNOUNCE)

    def test_the_captain_winding_up_on_mira_pays_nothing(self) -> None:
        PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.captain,
            threat_entry=ThreatPoolEntryFactory(pool=self.captain.threat_pool, windup_rounds=1),
            target=self.seats[self.mira],
            declared_round=1,
            resolves_round=2,
        )

        self.assertEqual(self.strikes(self.mira, self.captain), 0)
        self.assertNotTold(self.mira, self.ANNOUNCE)

    def test_the_captain_swinging_at_another_bandit_pays_off(self) -> None:
        self.bandit_attacks(self.captain, at_bandits=(self.guard,))

        self.assertEqual(self.strikes(self.mira, self.captain), PAYOFF)
        self.assertTold(self.mira, self.ANNOUNCE)


class ACovenantMateStrikesAnEnemyBusyElsewhere(_BanditFight):
    """Mira's perk rewards her covenant-mates' strikes; "elsewhere" means not on the striker."""

    SITUATION = Situation.TARGET_FOCUSED_ELSEWHERE
    BENEFICIARY = PerkBeneficiary.COVENANT_ALLIES

    def test_tomas_striking_the_captain_swinging_at_mira_pays_off(self) -> None:
        self.bandit_attacks(self.captain, at=(self.mira,))

        self.assertEqual(self.strikes(self.tomas, self.captain), PAYOFF)
        self.assertTold(self.tomas, self.ANNOUNCE)

    def test_tomas_striking_the_captain_swinging_at_him_pays_nothing(self) -> None:
        self.bandit_attacks(self.captain, at=(self.tomas,))

        self.assertEqual(self.strikes(self.tomas, self.captain), 0)
        self.assertNotTold(self.tomas, self.ANNOUNCE)


class _DistractedCaptain(_BanditFight):
    """A distraction laid on the captain's own body by a DISTRACTION-tagged technique."""

    def distract_captain(self, by: ObjectDB) -> None:
        trick = TechniqueFactory(gift=GiftFactory())
        TechniqueFunctionTagFactory(technique=trick, function=TechniqueFunction.DISTRACTION)
        ConditionInstanceFactory(
            target=self.captain.objectdb, source_technique=trick, source_character=by
        )


class StrikingADistractedEnemy(_DistractedCaptain):
    """Mira's perk answers "Target Distracted"."""

    SITUATION = Situation.TARGET_DISTRACTED

    def test_a_distracted_captain_pays_off(self) -> None:
        self.distract_captain(by=self.ilse)

        self.assertEqual(self.strikes(self.mira, self.captain), PAYOFF)
        self.assertTold(self.mira, self.ANNOUNCE)

    def test_an_undistracted_captain_pays_nothing(self) -> None:
        self.assertEqual(self.strikes(self.mira, self.captain), 0)
        self.assertNotTold(self.mira, self.ANNOUNCE)


class StrikingAnEnemySwayedByAnAlly(_DistractedCaptain):
    """Mira's perk answers "Target Swayed by Ally"."""

    SITUATION = Situation.TARGET_SWAYED_BY_ALLY

    def test_a_captain_tomas_distracted_pays_off(self) -> None:
        self.distract_captain(by=self.tomas)

        self.assertEqual(self.strikes(self.mira, self.captain), PAYOFF)
        self.assertTold(self.mira, self.ANNOUNCE)

    def test_a_captain_ilse_distracted_pays_nothing(self) -> None:
        self.distract_captain(by=self.ilse)

        self.assertEqual(self.strikes(self.mira, self.captain), 0)
        self.assertNotTold(self.mira, self.ANNOUNCE)
