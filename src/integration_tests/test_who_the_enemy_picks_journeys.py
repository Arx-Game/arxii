"""Journeys for who an enemy picks, and who an area technique lands on (#4811).

Brenna (a warden), Cassian (her ward) and Ilse stand against a brute whose one swing goes
to whoever it hates most. A fighter wrapped in a concealing condition drops out of its
choice; a bound oath from Brenna makes it spare her and everyone she guards; and Ilse's
area cry, limited to bleeding enemies, shakes only the guards a bleeding condition marks.

Every expected number is an authored value on a row built in ``setUp`` or the test:

- Each player has 100 health. The brute's one entry swings for 12 at its highest threat,
  and every defence roll is fixed at success level 0, which takes the swing in full.
- Threat with the brute: Cassian 30, Brenna 20, Ilse 10. So unbound it hits Cassian.
- "Bound Oath" spares its source. Its source is Brenna.
- "Bodyguard's Watch" (the source guards the bearer) sits on Cassian from Brenna.
- "Shadowed" belongs to a category that conceals from perception.
- Ilse's "Cry of the Hunt" is an area technique limited to targets with the "bleeding"
  property. At Critical Success it removes 30 + 10 morale, from guards at 70 morale.
  "Open Wound" grants "bleeding" from its template; "Torn Artery" grants it from its
  current stage only.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.combat.constants import (
    ActionCategory,
    OpponentTier,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    SpectacleConfigFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    ThreatRecordFactory,
)
from world.combat.models import CombatOpponent, CombatOpponentAction, CombatParticipant
from world.combat.services import resolve_round
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueMoraleEffectFactory,
)
from world.mechanics.constants import PropertyHolder
from world.mechanics.factories import PrerequisiteFactory, PropertyFactory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

PC_HEALTH = 100
BRUTE_SWING = 12
GUARD_MORALE = 70
CRY_MORALE = 40  # 30 base + 10 for the one success level past the minimum


def _full_swing(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll fixed at success level 0, which takes the swing at full strength."""
    return MagicMock(success_level=0)


@contextmanager
def every_check_at(outcome_name: str) -> Iterator[None]:
    """Every combat check in the block lands at the named ``CheckOutcome``."""
    outcome = CheckOutcome.objects.get(name=outcome_name)

    def forced(*args: object, **kwargs: object) -> CheckResult:
        with force_check_outcome(outcome):
            return perform_check(*args, **kwargs)

    with patch("world.combat.services.perform_check", side_effect=forced):
        yield


class _TheYard(JourneyCase):
    """Three players and a brute in the yard, with the readings each journey needs."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.yard = self.make_room("The Yard")
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.brenna, self.brenna_seat = self.fighter("Brenna")
        self.cassian, self.cassian_seat = self.fighter("Cassian")
        self.ilse, self.ilse_seat = self.fighter("Ilse")

        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            base_damage=BRUTE_SWING,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        self.brute = CombatOpponentFactory(
            encounter=self.encounter, threat_pool=pool, health=50, max_health=50, soak_value=0
        )
        for seat, threat in ((self.cassian_seat, 30), (self.brenna_seat, 20), (self.ilse_seat, 10)):
            ThreatRecordFactory(
                encounter=self.encounter, opponent=self.brute, participant=seat, threat_value=threat
            )

    def fighter(self, name: str) -> tuple[ObjectDB, CombatParticipant]:
        character = self.make_player(name, room=self.yard)
        CharacterVitals.objects.create(
            character_sheet=character.sheet_data,
            health=PC_HEALTH,
            max_health=PC_HEALTH,
            base_max_health=PC_HEALTH,
        )
        seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=character.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        return character, seat

    def health(self, player: ObjectDB) -> int:
        return CharacterVitals.objects.get(character_sheet=player.sheet_data).health

    def swing_targets(self) -> list[CombatParticipant]:
        action = CombatOpponentAction.objects.filter(opponent=self.brute, round_number=1).first()
        return [] if action is None else list(action.targets.all())

    def brute_round(self) -> None:
        resolve_round(self.encounter, defense_check_fn=_full_swing)

    def lay(self, template, *, on: ObjectDB, source: ObjectDB | None = None) -> None:
        ConditionInstanceFactory(target=on, condition=template, source_character=source)


class TheBruteChooses(_TheYard):
    """Concealment and a bound oath both take a fighter out of the brute's choice."""

    def setUp(self) -> None:
        super().setUp()
        self.shadowed = ConditionTemplateFactory(
            name="Shadowed",
            category=ConditionCategoryFactory(name="Hidden 4811", conceals_from_perception=True),
        )
        self.oath = ConditionTemplateFactory(name="Bound Oath", spares_source=True)
        self.watch = ConditionTemplateFactory(name="Bodyguard's Watch", source_guards_bearer=True)
        self.called_out = ConditionTemplateFactory(name="Called Out", forces_attack_on_source=True)

    def test_unbound_the_brute_hits_the_one_it_hates_most(self) -> None:
        self.brute_round()

        self.assertEqual(self.swing_targets(), [self.cassian_seat])
        self.assertEqual(self.health(self.cassian), PC_HEALTH - BRUTE_SWING)

    def test_a_concealed_fighter_is_not_picked(self) -> None:
        self.lay(self.shadowed, on=self.cassian)

        self.brute_round()

        self.assertEqual(self.swing_targets(), [self.brenna_seat])
        self.assertEqual(self.health(self.cassian), PC_HEALTH)
        self.assertEqual(self.health(self.brenna), PC_HEALTH - BRUTE_SWING)

    def test_with_everyone_concealed_the_brute_swings_at_nobody(self) -> None:
        for player in (self.brenna, self.cassian, self.ilse):
            self.lay(self.shadowed, on=player)

        self.brute_round()

        self.assertEqual(self.swing_targets(), [])
        for player in (self.brenna, self.cassian, self.ilse):
            self.assertEqual(self.health(player), PC_HEALTH)

    def test_a_bound_oath_spares_its_source_and_her_ward(self) -> None:
        self.lay(self.watch, on=self.cassian, source=self.brenna)
        self.lay(self.oath, on=self.brute.objectdb, source=self.brenna)

        self.brute_round()

        self.assertEqual(self.swing_targets(), [self.ilse_seat])
        self.assertEqual(self.health(self.ilse), PC_HEALTH - BRUTE_SWING)
        self.assertEqual(self.health(self.cassian), PC_HEALTH)
        self.assertEqual(self.health(self.brenna), PC_HEALTH)

    def test_an_oath_does_not_spare_someone_she_does_not_guard(self) -> None:
        self.lay(self.oath, on=self.brute.objectdb, source=self.brenna)

        self.brute_round()

        self.assertEqual(self.swing_targets(), [self.cassian_seat])

    def test_the_oath_beats_her_own_provoke(self) -> None:
        self.lay(self.oath, on=self.brute.objectdb, source=self.brenna)
        self.lay(self.called_out, on=self.brute.objectdb, source=self.brenna)

        self.brute_round()

        self.assertEqual(self.swing_targets(), [self.cassian_seat])

    def test_a_provoke_from_someone_unspared_still_wins(self) -> None:
        self.lay(self.oath, on=self.brute.objectdb, source=self.brenna)
        self.lay(self.called_out, on=self.brute.objectdb, source=self.ilse)

        self.brute_round()

        self.assertEqual(self.swing_targets(), [self.ilse_seat])

    def test_sparing_everyone_leaves_the_brute_nobody_to_swing_at(self) -> None:
        self.lay(self.watch, on=self.cassian, source=self.brenna)
        self.lay(self.watch, on=self.ilse, source=self.brenna)
        self.lay(self.oath, on=self.brute.objectdb, source=self.brenna)

        self.brute_round()

        self.assertEqual(self.swing_targets(), [])


class ACryForTheBleeding(_TheYard):
    """Ilse's area cry, limited to bleeding enemies, shakes only the guards that bleed."""

    def setUp(self) -> None:
        super().setUp()
        SpectacleConfigFactory()
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        bleeding = PropertyFactory(name="bleeding")
        self.cry = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            target_type=ActionTargetType.AREA,
            action_category=ActionCategory.SOCIAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        TechniqueMoraleEffectFactory(
            technique=self.cry,
            base_morale=30,
            morale_per_extra_sl=10,
            minimum_success_level=1,
            morale_intensity_multiplier=Decimal(0),
        )
        self.cry.target_prerequisites.add(
            PrerequisiteFactory(
                name="Bleeding target 4811",
                property=bleeding,
                property_holder=PropertyHolder.TARGET,
                minimum_value=1,
            )
        )
        sheet = self.ilse.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=self.cry)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)

        open_wound = ConditionTemplateFactory(name="Open Wound")
        open_wound.properties.add(bleeding)
        torn_artery = ConditionTemplateFactory(name="Torn Artery", has_progression=True)
        spurting = ConditionStageFactory(condition=torn_artery, stage_order=1, name="Spurting")
        spurting.properties.add(bleeding)
        bruised = ConditionTemplateFactory(name="Bruised")

        self.cut = self.guard("Guard Hale")
        self.lay(open_wound, on=self.cut.objectdb)
        self.gashed = self.guard("Guard Rook")
        ConditionInstanceFactory(
            target=self.gashed.objectdb, condition=torn_artery, current_stage=spurting
        )
        self.whole = self.guard("Guard Wren")
        self.lay(bruised, on=self.whole.objectdb)

    def guard(self, name: str) -> CombatOpponent:
        return CombatOpponentFactory(
            encounter=self.encounter, name=name, tier=OpponentTier.MOOK, morale=GUARD_MORALE
        )

    def morale(self, opponent: CombatOpponent) -> int:
        opponent.refresh_from_db()
        return opponent.morale

    def test_the_cry_shakes_only_the_bleeding_guards(self) -> None:
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=self.cry.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            self.ilse,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.cut.pk},
        )
        self.assertTrue(declared.deferred, declared)

        with every_check_at("Critical Success"):
            resolve_round(self.encounter)

        self.assertEqual(self.morale(self.cut), GUARD_MORALE - CRY_MORALE)
        self.assertEqual(self.morale(self.gashed), GUARD_MORALE - CRY_MORALE)
        self.assertEqual(self.morale(self.whole), GUARD_MORALE)
