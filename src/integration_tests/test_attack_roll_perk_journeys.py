"""Journeys for a vow perk that applies to attack rolls only (#5092).

Hobb holds an engaged vow at thread level 3 whose role carries one check-bonus perk of 10
tenths, with no situation, so it answers every roll its scope allows. The perk scales by the
stored thread level (stored 30, #4585): 30 x 10 / 10 = +30 points on a roll it reaches.

The perk's "Applies to" is set to "Attack rolls" (owner ruling, 2026-11-12): once per attack
on an opponent. A plain Strike's hit roll takes it, an attack technique's roll takes it, and
an enchanted Strike's technique roll takes it while its hit roll does not (one boost per
attack, ADR-5026's counted-once table). A parry against a blow that round never takes it,
and a check type set beside the scope narrows it further (AND).

Each journey plays the same round twice: first with the perk scoped to a check type nothing
here rolls (so it never answers), then with the scope under test ("Applies to: Attack rolls",
or "Any roll" as the control). Every roll is forced
to Success, Hobb starts each round rested, and the difference between the two rounds on each
roll is what the perk added. Expected values come from the owner's ruling and the perk's
authored magnitude, not from the code.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from django.test import override_settings

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from integration_tests.test_thrown_and_enchanted_strike_journeys import _ThrowingField
from world.areas.positioning.models import Position
from world.areas.positioning.services import place_in_position
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    ActionCategory,
    EngagementLockStatus,
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    EngagementLockFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
    engage_vow_with_thread,
)
from world.covenants.perks.constants import (
    PerkBeneficiary,
    PerkEffectKind,
    PerkRollKind,
    Situation,
)
from world.fatigue.constants import EffortLevel
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models.modifier_level import CastPowerLevel
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome, Trait
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities

if TYPE_CHECKING:
    from collections.abc import Iterator

    from world.checks.models import CheckType

PAYOFF = 30
VOW_ANSWERS = "vow answers the attack!"


class _AttackRollPerkField(_ThrowingField):
    """Hobb, his thrown dagger and the archer, plus a vow perk scoped by the journey."""

    def setUp(self) -> None:
        super().setUp()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            self.sheet,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=3,
        )
        self.never_rolled = CheckTypeFactory(name="Never rolled here")
        self.perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=self.never_rolled,
            announce_template="{holder}'s vow answers the attack!",
        )
        self.watch(self.hobb)

    def scope(self, *, roll_kind: str, check_type: CheckType | None = None) -> None:
        """Staff's edit of the perk: its check type and its "Applies to"."""
        self.perk.check_type = check_type
        self.perk.roll_kind = roll_kind
        self.perk.full_clean()
        self.perk.save()

    @contextmanager
    def rolls_at_success(self) -> Iterator[tuple[list[tuple[CheckType, int]], Any]]:
        """Every roll in the block lands at Success. Yields the list of Hobb's rolls (check
        type, points) and the forced roll, for the defense seam to use too."""
        outcome = CheckOutcome.objects.get(name="Success")
        rolled: list[tuple[CheckType, int]] = []

        def forced(character: Any, check_type: CheckType, *args: Any, **kw: Any):
            with force_check_outcome(outcome):
                result = perform_check(character, check_type, *args, **kw)
            if character == self.hobb:
                rolled.append((check_type, result.total_points))
            return result

        with patch("world.combat.services.perform_check", side_effect=forced):
            yield rolled, forced

    def play_round(self, declare) -> list[tuple[str, int]]:
        """Hobb starts rested, ``declare`` declares his action, the round resolves; his
        rolls in order, by check type name."""
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.physical_current = 0
        pool.mental_current = 0
        pool.save(update_fields=["physical_current", "mental_current"])
        declare()
        with self.rolls_at_success() as (rolled, forced):
            resolve_round(self.encounter, defense_check_fn=forced)
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        return [(check_type.name, points) for check_type, points in rolled]

    def added(self, declare, *, roll_kind: str = PerkRollKind.ATTACK, check_type=None):
        """Play the round with the perk off, then with the given scope; per roll, in the
        order rolled, its check type's name and the points the perk added."""
        before = self.play_round(declare)
        self.assertNotTold(self.hobb, VOW_ANSWERS)
        self.scope(roll_kind=roll_kind, check_type=check_type)
        after = self.play_round(declare)
        self.assertEqual([n for n, _ in before], [n for n, _ in after])
        return [(name, a - b) for (name, b), (_, a) in zip(before, after, strict=True)]

    def throw(self, **kwargs: Any) -> None:
        result = self.web(
            self.hobb,
            "combat_strike",
            opponent_id=self.archer.pk,
            weapon_id=self.dagger.pk,
            thrown=True,
            **kwargs,
        )
        self.assertTrue(result.detail.success, result.detail.message)


class AStrikeTakesTheBoostOnce(_AttackRollPerkField):
    def test_a_plain_strike_hit_roll_takes_it(self) -> None:
        added = self.added(self.throw)

        self.assertEqual(added[0], (self.thrown_check.name, PAYOFF))
        self.assertTold(self.hobb, VOW_ANSWERS)

    def test_an_enchanted_strike_boosts_its_technique_roll_not_its_hit_roll(self) -> None:
        technique = self.wreathe_the_blade(anima=30)

        added = self.added(lambda: self.throw(technique_id=technique.pk))

        self.assertEqual(added[:2], [("Fire Magic Cast", PAYOFF), (self.thrown_check.name, 0)])
        self.assertTold(self.hobb, VOW_ANSWERS)

    def test_an_unscoped_perk_stays_on_the_enchanted_strike_hit_roll(self) -> None:
        """The control: "Any roll" keeps today's place, the hit roll, and never reaches the
        technique roll, so one attack is boosted once either way."""
        technique = self.wreathe_the_blade(anima=30)

        added = self.added(
            lambda: self.throw(technique_id=technique.pk), roll_kind=PerkRollKind.ANY
        )

        self.assertEqual(added[:2], [("Fire Magic Cast", 0), (self.thrown_check.name, PAYOFF)])


class AnAttackTechniqueTakesItAndADodgeDoesNot(_AttackRollPerkField):
    """Hobb casts a bolt at a blade beside him while the blade swings at him."""

    def setUp(self) -> None:
        super().setUp()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # the movement capability
            ensure_foundational_capabilities()
        CharacterAnimaFactory(character=self.sheet, current=30, maximum=30)
        CastPowerLevel.objects.create(min_power=0, level=1)
        self.bolt_check = CheckTypeFactory(name="Bolt Cast")
        CheckTypeTraitFactory(check_type=self.bolt_check, trait=Trait.objects.get(name="strength"))
        self.bolt = TechniqueFactory(
            name="Ember bolt",
            gift=GiftFactory(name="Cinder"),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.bolt_check),
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.bolt)
        self.parry = CheckTypeFactory(name="Parry")
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=500, base_soak=0)
        pool = ThreatPoolFactory(name="Blade attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name="Blade swing",
            base_damage=1,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.parry,
        )
        self.blade = spawn_from_creature_template(
            self.encounter,
            CreatureTemplateFactory(
                name="Blade", tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=0
            ),
        )
        lane = Position.objects.get(room=self.steading, name="Lane")
        place_in_position(self.blade.objectdb, lane)

    def cast_bolt(self) -> None:
        declared = dispatch_player_action(
            self.hobb,
            ActionRef(
                backend=ActionBackend.COMBAT, technique_id=self.bolt.pk, action_slot="focused"
            ),
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.blade.pk},
        )
        self.assertTrue(declared.deferred, declared)

    def test_the_bolt_takes_it_and_the_parry_that_round_does_not(self) -> None:
        added = self.added(self.cast_bolt)

        self.assertEqual(sorted(added), [("Bolt Cast", PAYOFF), ("Parry", 0)])
        self.assertTold(self.hobb, VOW_ANSWERS)

    def test_an_unscoped_perk_does_reach_the_parry(self) -> None:
        """The control: the parry reads perks, so "Attack rolls" is what keeps it out."""
        added = self.added(self.cast_bolt, roll_kind=PerkRollKind.ANY)

        self.assertEqual(sorted(added), [("Bolt Cast", PAYOFF), ("Parry", PAYOFF)])

    def test_a_check_type_beside_it_narrows_it_further(self) -> None:
        """Attack rolls AND the thrown check: the bolt is an attack on another check."""
        added = self.added(self.cast_bolt, check_type=self.thrown_check)

        self.assertEqual(sorted(added), [("Bolt Cast", 0), ("Parry", 0)])


class TheAnnounceNamesTheAllyAndTheFoe(JourneyCase):
    """Mira holds the Bandit Captain; Tomas's vow answers his bolt at it, aloud (#5092).

    Tomas's engaged vow carries "Press the Held Foe", a check bonus on attack rolls when an
    enemy is held by an ally, whose line reads "{ally} holds {target} for {holder} to
    strike!". Mira, his covenant-mate, holds the captain; Ilse watches from the road.
    """

    LINE = "Press the Held Foe: Mira holds Bandit Captain for Tomas to strike!"

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=road)
        self.tomas = self.make_player("Tomas", room=road)
        self.ilse = self.make_player("Ilse", room=road)
        check_type = CheckTypeFactory(name="Bolt Cast")
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.bolt = TechniqueFactory(
            name="Ember bolt",
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=road
        )
        participants = {}
        for player in (self.mira, self.tomas, self.ilse):
            sheet = player.sheet_data
            CharacterVitals.objects.create(
                character_sheet=sheet, health=100, max_health=100, base_max_health=100
            )
            CharacterTechniqueFactory(character=sheet, technique=self.bolt)
            CharacterAnimaFactory(character=sheet, current=20, maximum=30)
            participants[player.key] = CombatParticipantFactory(
                encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
            )
        self.captain = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit Captain", health=500, max_health=500
        )
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(self.tomas.sheet_data, role, covenant=covenant, thread_level=3)
        CharacterCovenantRoleFactory(
            character_sheet=self.mira.sheet_data,
            covenant=covenant,
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
        )
        self.mira.covenant_roles.invalidate()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            name="Press the Held Foe",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
            roll_kind=PerkRollKind.ATTACK,
            announce_template="{ally} holds {target} for {holder} to strike!",
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.ENEMY_HELD_BY_ALLY)
        self.mira_participant = participants["Mira"]
        self.watch(self.tomas, self.ilse)

    def bolt_the_captain(self) -> None:
        declared = dispatch_player_action(
            self.tomas,
            ActionRef(
                backend=ActionBackend.COMBAT, technique_id=self.bolt.pk, action_slot="focused"
            ),
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.captain.pk},
        )
        self.assertTrue(declared.deferred, declared)
        with patch(
            "world.combat.services.perform_check",
            side_effect=lambda *a, **kw: _forced_success(*a, **kw),
        ):
            resolve_round(self.encounter)

    def test_the_room_hears_who_holds_which_foe(self) -> None:
        EngagementLockFactory(
            encounter=self.encounter,
            participant=self.mira_participant,
            opponent=self.captain,
            status=EngagementLockStatus.ACTIVE,
        )

        self.bolt_the_captain()

        self.assertTold(self.ilse, self.LINE)
        self.assertTold(self.tomas, self.LINE)

    def test_with_nobody_holding_it_the_vow_stays_quiet(self) -> None:
        self.bolt_the_captain()

        self.assertNotTold(self.ilse, "Press the Held Foe")


def _forced_success(*args: Any, **kwargs: Any):
    with force_check_outcome(CheckOutcome.objects.get(name="Success")):
        return perform_check(*args, **kwargs)
