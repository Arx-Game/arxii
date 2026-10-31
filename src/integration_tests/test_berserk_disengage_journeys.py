"""Journeys for a raging character who flees or parleys (#4738, part B).

Berserk no longer refuses flee or parley. Mira, raging, types ``combat flee`` or
``combat parley Bandit Captain`` and the declaration stands; the round then rolls her
check carrying whatever ConditionCheckModifier staff authored on the Berserk template.
Only walking away (``combat_leave``) is still refused, with a pointer at fleeing.

Expected values are the rows built here: a -7 on the flee check and a -4 on the parley
check, read back from the modifier breakdown the real roll gathered.
"""

from __future__ import annotations

from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.services import collect_check_modifiers
from world.combat.constants import CombatManeuver, EncounterType, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    SocialManeuverConfigFactory,
)
from world.combat.models import CombatRoundAction, FleeConfig
from world.combat.services import resolve_round
from world.conditions.factories import ConditionCheckModifierFactory, ConditionInstanceFactory
from world.magic.factories import BerserkConditionTemplateFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

FLEE_PENALTY = -7
PARLEY_PENALTY = -4


class _RagingMira(JourneyCase):
    """Mira, raging under Berserk, in a fight with a Bandit Captain."""

    def setUp(self) -> None:
        super().setUp()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        CharacterVitals.objects.create(
            character_sheet=self.mira.sheet_data, health=100, max_health=100, base_max_health=100
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.road
        )
        self.seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.mira.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.captain = CombatOpponentFactory(encounter=self.encounter, name="Bandit Captain")
        self.flee_check = CheckTypeFactory(name="Run for it")
        self.parley_check = CheckTypeFactory(name="Talk them down")
        FleeConfig.objects.filter(pk=1).delete()
        FleeConfig.objects.create(pk=1, check_type=self.flee_check)
        SocialManeuverConfigFactory(parley_check_type=self.parley_check)
        self.berserk = BerserkConditionTemplateFactory()
        ConditionInstanceFactory(target=self.mira, condition=self.berserk)
        self.watch(self.mira)

    def author_penalty(self, check_type, value: int) -> None:
        ConditionCheckModifierFactory(
            condition=self.berserk, stage=None, check_type=check_type, modifier_value=value
        )

    def condition_terms_of_the_round(self, check_type) -> list[int]:
        """Every condition modifier the real seam gathered for ``check_type`` this round."""
        gathered: list[int] = []

        def spy(sheet, rolled_type, **kwargs):
            breakdown = collect_check_modifiers(sheet, rolled_type, **kwargs)
            if rolled_type == check_type:
                gathered.extend(
                    c.value
                    for c in breakdown.contributions
                    if c.source_kind == ModifierSourceKind.CONDITION
                )
            return breakdown

        # Flee reaches the seam through the combat services namespace, the social
        # verbs through world.checks.services; both are the one real function.
        with (
            patch("world.combat.services.collect_check_modifiers", side_effect=spy),
            patch("world.checks.services.collect_check_modifiers", side_effect=spy),
        ):
            resolve_round(self.encounter)
        return gathered


class ARagingCharacterMayFlee(_RagingMira):
    def test_the_flee_declaration_stands(self) -> None:
        told = self.telnet(self.mira, "combat flee")

        self.assertNotIn("rage", told.lower())
        action = CombatRoundAction.objects.get(participant=self.seat, round_number=1)
        self.assertEqual(action.maneuver, CombatManeuver.FLEE)

    def test_the_authored_penalty_lands_on_the_flee_roll(self) -> None:
        self.author_penalty(self.flee_check, FLEE_PENALTY)
        self.telnet(self.mira, "combat flee")

        terms = self.condition_terms_of_the_round(self.flee_check)

        self.assertIn(FLEE_PENALTY, terms)


class ARagingCharacterMayParley(_RagingMira):
    def setUp(self) -> None:
        super().setUp()
        self.captain.morale = 0
        self.captain.save()

    def test_the_parley_declaration_stands(self) -> None:
        told = self.telnet(self.mira, "combat parley Bandit Captain")

        self.assertNotIn("rage", told.lower())
        action = CombatRoundAction.objects.get(participant=self.seat, round_number=1)
        self.assertEqual(action.maneuver, CombatManeuver.PARLEY)

    def test_the_authored_penalty_lands_on_the_parley_roll(self) -> None:
        self.author_penalty(self.parley_check, PARLEY_PENALTY)
        self.telnet(self.mira, "combat parley Bandit Captain")

        terms = self.condition_terms_of_the_round(self.parley_check)

        self.assertIn(PARLEY_PENALTY, terms)


class ARagingCharacterWillNotWalkAway(_RagingMira):
    def test_leaving_is_refused_with_a_pointer_at_fleeing(self) -> None:
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.encounter_type = EncounterType.OPEN_ENCOUNTER
        self.encounter.save()

        result = self.web(self.mira, "combat_leave")

        self.assertFalse(result.detail.success)
        self.assertEqual(
            result.detail.message, "The rage will not walk away. You can still try to flee."
        )
