"""Journeys for an area cast's combat narration (#4842).

Hobb is a fighter in the Yard. He sweeps the room with an AREA technique of one Fire profile
of 6 (no intensity or extra-level scaling) and every check in the round is forced to Success,
so a profile deals exactly its 6 less the opponent's soak. The Hound has no soak, the Wyrm
soak 2 and the Drake soak 6, so the sweep costs them 6, 4 and 0.

Expected values come from the spec, not from running the code: the round's narration names
each opponent the sweep hurt with its own figure, the focused target first, and leaves out
the one that took nothing. A single-target strike keeps the one-figure line.
"""

from __future__ import annotations

from decimal import Decimal

from actions.constants import ActionBackend, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from integration_tests.test_vow_added_effects_in_combat_journeys import every_check_succeeds
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory, DamageTypeFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.models import Technique
from world.scenes.constants import InteractionMode, RoundStatus
from world.scenes.models import Interaction
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.vitals.models import CharacterVitals


class AreaCastNarration(JourneyCase):
    """Hobb in the Yard, sweeping three opponents with an area technique."""

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
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.hound = self.opponent("Hound", soak=0)
        self.wyrm = self.opponent("Wyrm", soak=2)
        self.drake = self.opponent("Drake", soak=6)

    def opponent(self, name: str, *, soak: int):
        return CombatOpponentFactory(
            encounter=self.encounter, name=name, health=200, max_health=200, soak_value=soak
        )

    def technique(self, target_type: str) -> Technique:
        """A Fire technique of 6 damage with the given reach."""
        technique = TechniqueFactory(
            gift=GiftFactory(name="Ember"),
            name="Sweep",
            target_type=target_type,
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )
        TechniqueDamageProfileFactory(
            technique=technique,
            base_damage=6,
            damage_type=self.fire,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=0,
            minimum_success_level=1,
            uses_equipped_weapon=False,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        return technique

    def cast_at(self, technique: Technique, focused) -> str:
        """Hobb casts ``technique`` focused on ``focused``; the round's outcome line."""
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            self.hobb,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": focused.pk},
        )
        self.assertTrue(declared.deferred, declared)
        with every_check_succeeds():
            resolve_round(self.encounter)
        return (
            Interaction.objects.filter(mode=InteractionMode.OUTCOME, content__contains="Sweep")
            .get()
            .content
        )

    def test_an_area_sweep_names_each_hurt_opponent_with_its_own_damage(self) -> None:
        # Hobb focuses the Wyrm. The Wyrm takes 6 - 2 = 4, the Hound 6 and the Drake
        # 6 - 6 = 0, so the room reads, the focused Wyrm first and the unhurt Drake left out:
        #   "Hobb’s Sweep strikes Wyrm for 4 damage and Hound for 6 damage."
        line = self.cast_at(self.technique(ActionTargetType.AREA), self.wyrm)

        self.assertEqual(line, "Hobb’s Sweep strikes Wyrm for 4 damage and Hound for 6 damage.")

    def test_a_single_target_strike_keeps_the_one_figure_line(self) -> None:
        # Only the Hound is struck, for 6:
        #   "Hobb’s Sweep strikes Hound for 6 damage."
        line = self.cast_at(self.technique(ActionTargetType.SINGLE), self.hound)

        self.assertEqual(line, "Hobb’s Sweep strikes Hound for 6 damage.")
