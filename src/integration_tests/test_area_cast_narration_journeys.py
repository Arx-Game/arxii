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

from django.db import connection
from django.test.utils import CaptureQueriesContext

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
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
)
from world.combat.models import CombatRoundAction
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
    TechniqueStyleFactory,
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

    def opponent(self, name: str, *, soak: int, health: int = 200):
        return CombatOpponentFactory(
            encounter=self.encounter, name=name, health=health, max_health=200, soak_value=soak
        )

    def technique(self, target_type: str, *, style=None) -> Technique:
        """A Fire technique of 6 damage with the given reach (and casting style, if any)."""
        technique = TechniqueFactory(
            gift=GiftFactory(name="Ember", style=style),
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

    def declare_and_resolve(self, technique: Technique, focused) -> None:
        """Hobb casts ``technique`` focused on ``focused`` and the round resolves."""
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

    def cast_at(self, technique: Technique, focused) -> str:
        """Hobb casts ``technique`` focused on ``focused``; the round's outcome line."""
        self.declare_and_resolve(technique, focused)
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

    def test_an_area_hit_that_defeats_one_opponent_names_it(self) -> None:
        # The Wyrm has 3 health left, so its 4 damage drops it; the Hound (200 health) takes
        # its 6 and stands. The tail names who fell, not "them":
        #   "Hobb’s Sweep strikes Wyrm for 4 damage and Hound for 6 damage, defeating Wyrm."
        wyrm = self.opponent("Marsh Wyrm", soak=2, health=3)
        self.wyrm.delete()

        line = self.cast_at(self.technique(ActionTargetType.AREA), wyrm)

        self.assertEqual(
            line,
            "Hobb’s Sweep strikes Marsh Wyrm for 4 damage and Hound for 6 damage, "
            "defeating Marsh Wyrm.",
        )

    def test_a_concealed_area_cast_splits_the_same_way(self) -> None:
        # Hobb's gift has a concealing style and Mira is in the Yard; with no detection check
        # authored nobody can name the caster, so Mira reads the effect with no caster in it,
        # split the same way, the focused Wyrm first:
        #   "Wyrm is struck for 4 damage and Hound for 6 damage."
        # while Hobb himself still reads the attributed line.
        self.make_player("Mira", room=self.yard)
        style = TechniqueStyleFactory(name="Veiled", cast_concealment=3)

        self.declare_and_resolve(self.technique(ActionTargetType.AREA, style=style), self.wyrm)

        lines = sorted(
            Interaction.objects.filter(mode=InteractionMode.OUTCOME).values_list(
                "content", flat=True
            )
        )
        self.assertEqual(
            lines,
            [
                "Hobb’s Sweep strikes Wyrm for 4 damage and Hound for 6 damage.",
                "Wyrm is struck for 4 damage and Hound for 6 damage.",
            ],
        )

    def opponent_name_queries(self, technique: Technique, focused) -> int:
        """How many times the round selects only (id, name) from the opponent table."""
        table = connection.ops.quote_name(self.hound._meta.db_table)
        names_only = f'{table}."id" AS "pk", {table}."name" AS "name" FROM {table}'
        with CaptureQueriesContext(connection) as queries:
            self.declare_and_resolve(technique, focused)
        return sum(1 for q in queries.captured_queries if names_only in q["sql"])

    def test_the_label_lookup_is_one_query_only_for_a_multi_opponent_hit(self) -> None:
        # Two opponents hurt: the names are fetched in one query. One opponent hurt: none.
        area = self.technique(ActionTargetType.AREA)
        self.assertEqual(self.opponent_name_queries(area, self.wyrm), 1)

        self.encounter.refresh_from_db()
        solo_encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        CombatParticipantFactory(
            encounter=solo_encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save()
        self.encounter = solo_encounter
        only = self.opponent("Lone Hound", soak=0)
        self.assertEqual(self.opponent_name_queries(area, only), 0)

    def test_an_npc_attack_keeps_the_one_figure_line(self) -> None:
        # The Hound mauls Hobb for a flat 7 (no soak on Hobb); an opponent's attack on a
        # participant is never split, so the room reads the single-figure line:
        #   "Hound’s Maul strikes Hobb for 7 damage."
        entry = ThreatPoolEntryFactory(name="Maul", base_damage=7)
        action = CombatOpponentActionFactory(
            opponent=self.hound, round_number=1, threat_entry=entry
        )
        participant = self.encounter.participants.get()
        action.targets.add(participant)
        CombatRoundAction.objects.create(
            participant=participant, round_number=1, focused_action=None, focused_category=None
        )

        with every_check_succeeds():
            resolve_round(self.encounter)

        line = (
            Interaction.objects.filter(mode=InteractionMode.OUTCOME, content__contains="Maul")
            .get()
            .content
        )
        self.assertEqual(line, "Hound’s Maul strikes Hobb for 7 damage.")
