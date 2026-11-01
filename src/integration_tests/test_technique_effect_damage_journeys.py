"""Journeys for a modifier on a technique's damage (#4822).

Hobb is a fighter in the Yard against a bandit with 200 health and no resistances. Every check
in the round is forced to Success (success level 1, damage multiplier 1), and each technique's
damage profile has no intensity or extra-level scaling, so a profile deals exactly its
``base_damage``. Hobb declares a technique through the web client's combat dispatch, the round
resolves, and the bandit's lost health is what the hit dealt. A "+N damage" modifier is a
ModifierTarget in the maneuver effect category with the damage effect kind, granted to Hobb
through a distinction.

Expected values come from the spec, not from running the code:

* A "+4 damage" modifier scoped to gift Ember and to Fire adds 4 to a Fire hit from an Ember
  technique (6 + 4 = 10). A Fire hit from another gift stays 6, and a Cold hit from an Ember
  technique stays 6 (4 is not added when any scope fails to match).
* A kind-only "+2 damage" modifier counts once per damage profile, like a vow's damage bonus:
  a technique with a Fire profile of 6 and a Cold profile of 4 deals 6 + 2 + 4 + 2 = 14.
* An area technique applies the modifier to each opponent it hits: a Fire profile of 6 with a
  kind-only "+2 damage" costs each of two opponents 8.
* A "-50 damage" modifier cannot heal: a hit of 6 deals 0.
* Untyped damage is Physical. A "+3 damage, Physical" modifier lifts an untyped profile of 5 to
  8, and leaves a Fire hit of 6 alone.
* A charge reads its own damage target for the catalog's Charge damage (5, with +3 on a target
  scoped to Charge damage itself). A kind-only "+3 damage" modifier already reaches a charge
  through the technique's damage, so a charge technique with no damage of its own deals
  5 + 3 = 8: the +3 is counted once, not twice.
"""

from __future__ import annotations

from decimal import Decimal

from actions.constants import ActionBackend, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from integration_tests.test_charge_effect_journeys import _ChargeField
from integration_tests.test_vow_added_effects_in_combat_journeys import every_check_succeeds
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory, DamageTypeFactory
from world.distinctions.factories import DistinctionEffectFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.models import Gift, Technique
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, EffectKind
from world.mechanics.factories import (
    CharacterModifierFactory,
    DistinctionModifierSourceFactory,
    ModifierTargetFactory,
)
from world.mechanics.models import ModifierCategory, ModifierTarget
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.vitals.models import CharacterVitals
from world.vitals.services import get_vitals_consequence_config


def grant_damage_modifier(sheet, name: str, value: int, **scopes: object) -> ModifierTarget:
    """``sheet`` holds a ``value`` modifier on a damage target scoped by ``scopes``."""
    category = ModifierCategory.objects.get_or_create(name=MANEUVER_EFFECT_CATEGORY_NAME)[0]
    target = ModifierTargetFactory(
        category=category, name=name, scope_effect_kind=EffectKind.DAMAGE, **scopes
    )
    CharacterModifierFactory(
        character=sheet,
        target=target,
        value=value,
        source=DistinctionModifierSourceFactory(
            distinction_effect=DistinctionEffectFactory(target=target)
        ),
    )
    return target


class _DamageField(JourneyCase):
    """Hobb in the Yard, striking a bandit with techniques of his own. Holds no tests, so a
    journey module that builds on it does not rerun these."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("1.00"), label="Full"
        )
        self.yard = self.make_room("The Yard")
        self.hobb = self.make_player("Hobb", room=self.yard)
        self.sheet = self.hobb.sheet_data
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=30)
        self.check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=self.check_type, trait=StatTraitFactory(), weight=1)
        self.fire = DamageTypeFactory(name="Fire")
        self.cold = DamageTypeFactory(name="Cold")
        self.ember = GiftFactory(name="Ember")
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.bandit = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit", health=200, max_health=200
        )

    def technique(
        self,
        gift: Gift,
        *profiles: tuple[int, object],
        target_type: str = ActionTargetType.SINGLE,
    ) -> Technique:
        """A technique of ``gift`` with one damage profile per ``(damage, type)`` given."""
        technique = TechniqueFactory(
            gift=gift,
            target_type=target_type,
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )
        for damage, damage_type in profiles:
            TechniqueDamageProfileFactory(
                technique=technique,
                base_damage=damage,
                damage_type=damage_type,
                damage_intensity_multiplier=Decimal(0),
                damage_per_extra_sl=0,
                minimum_success_level=1,
                uses_equipped_weapon=False,
            )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        return technique

    def strike(self, technique: Technique) -> int:
        """Hobb strikes the bandit with ``technique`` for a round; the damage dealt."""
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            self.hobb,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.bandit.pk},
        )
        self.assertTrue(declared.deferred, declared)
        before = self.bandit_health()
        with every_check_succeeds():
            resolve_round(self.encounter)
        damage = before - self.bandit_health()
        begin_declaration_phase(self.encounter)
        return damage

    def bandit_health(self) -> int:
        return CombatOpponent.objects.get(pk=self.bandit.pk).health

    def health_of(self, opponent: CombatOpponent) -> int:
        return CombatOpponent.objects.get(pk=opponent.pk).health

    def designate_physical(self) -> None:
        config = get_vitals_consequence_config()
        config.physical_damage_type = DamageTypeFactory(name="Physical")
        config.save(update_fields=["physical_damage_type"])


class TechniqueDamageModifiers(_DamageField):
    def test_gift_and_type_scoped_bonus_raises_matching_hit(self) -> None:
        grant_damage_modifier(
            self.sheet, "Ember fire", 4, scope_gift=self.ember, scope_damage_type=self.fire
        )
        ember_fire = self.technique(self.ember, (6, self.fire))
        frost_fire = self.technique(GiftFactory(name="Frost"), (6, self.fire))
        ember_cold = self.technique(self.ember, (6, self.cold))

        self.assertEqual(self.strike(ember_fire), 6 + 4)
        self.assertEqual(self.strike(frost_fire), 6)
        self.assertEqual(self.strike(ember_cold), 6)

    def test_bonus_applies_per_profile(self) -> None:
        grant_damage_modifier(self.sheet, "Any damage", 2)
        twin = self.technique(self.ember, (6, self.fire), (4, self.cold))

        self.assertEqual(self.strike(twin), (6 + 2) + (4 + 2))

    def test_bonus_raises_the_hit_on_every_opponent_of_an_area_technique(self) -> None:
        grant_damage_modifier(self.sheet, "Any damage", 2)
        second = CombatOpponentFactory(
            encounter=self.encounter, name="Archer", health=200, max_health=200
        )
        sweep = self.technique(self.ember, (6, self.fire), target_type=ActionTargetType.AREA)

        self.strike(sweep)

        self.assertEqual(200 - self.bandit_health(), 6 + 2)
        self.assertEqual(200 - self.health_of(second), 6 + 2)

    def test_a_large_negative_modifier_floors_the_hit_at_nothing(self) -> None:
        grant_damage_modifier(self.sheet, "Dulled", -50)
        blow = self.technique(self.ember, (6, self.fire))

        self.assertEqual(self.strike(blow), 0)

    def test_untyped_profile_matches_physical_scope(self) -> None:
        self.designate_physical()
        grant_damage_modifier(
            self.sheet,
            "Physical damage",
            3,
            scope_damage_type=get_vitals_consequence_config().physical_damage_type,
        )
        untyped = self.technique(self.ember, (5, None))
        fire = self.technique(self.ember, (6, self.fire))

        self.assertEqual(self.strike(untyped), 5 + 3)
        self.assertEqual(self.strike(fire), 6)


class ChargeCountsAKindWideDamageTargetOnce(_ChargeField):
    def test_charge_counts_kind_damage_once(self) -> None:
        grant_damage_modifier(self.sheet, "Any damage", 3)

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, 5 + 3)
        self.assertEqual(to_hit, 10)
