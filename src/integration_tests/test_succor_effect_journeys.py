"""Journeys for Succor reading the maneuver effect catalog, in a fight and in a scene round (#4783).

Hobb stands in the open with a burning hazard on him that deals 40 a round at the end of the
round. Mara shelters him with Succor (``combat_succor`` in a fight, ``scene succor Hobb`` in a
strict scene round) and her shelter lands as a partial: not a clean block, not a failure. What
is read back is Hobb's health after the round resolves.

Expected values are the catalog default and the spec: a partial stops 50% of the hazard, so 20
of the 40 lands. A +10 on Mara's Succor partial protection (her vow, at thread level 1) stops
60%, so 16 lands. The catalog row is the same one in both rounds, and only the sheltering
character's own number counts.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings

from integration_tests.harness import JourneyCase
from world.checks.types import CheckResult
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatParticipant
from world.combat.services import resolve_round
from world.combat.succor_content import ensure_succor_content
from world.conditions.factories import (
    ConditionCapabilityEffectFactory,
    ConditionDamageOverTimeFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, engage_vow_with_thread
from world.covenants.models import VowStatScaling
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    EffectKind,
    ManeuverEffectKey,
)
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.scenes.constants import RoundStatus
from world.scenes.models import SceneRound
from world.scenes.round_services import ensure_round_for_acute_condition
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.vitals.models import CharacterVitals

HAZARD = 40
STOPPED_BY_DEFAULT = 20
STOPPED_WITH_TEN_MORE = 24


def _partial_check_result() -> CheckResult:
    """A Succor roll that lands as a partial: success level 0, neither clean nor failed."""
    return CheckResult(
        check_type=None,
        outcome=CheckOutcomeFactory(name="Partial shelter", success_level=0),
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


class _SuccorField(JourneyCase):
    """Hobb under a burning hazard, and Mara, who can shelter him."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        ensure_succor_content()
        ensure_maneuver_effects()
        self.field = self.make_room("The Scorched Yard")
        self.hobb = self.make_player("Hobb", room=self.field)
        self.mara = self.make_player("Mara", room=self.field)
        for character in (self.hobb, self.mara):
            CharacterVitals.objects.create(
                character_sheet=character.sheet_data,
                health=100,
                max_health=100,
                base_max_health=100,
            )
        # Mara can shelter an ally through telekinesis, a seeded Succor capability.
        gift = ConditionTemplateFactory(name="Telekinetic shelter")
        ConditionCapabilityEffectFactory(
            condition=gift, capability=CapabilityType.objects.get(name="telekinesis"), value=10
        )
        apply_condition(self.mara, gift)
        # Hobb burns for HAZARD at the end of every round.
        hazard = ConditionTemplateFactory(name="Burning yard")
        ConditionDamageOverTimeFactory(condition=hazard, base_damage=HAZARD)
        apply_condition(self.hobb, hazard)
        patcher = patch(
            "world.mechanics.challenge_resolution.perform_check",
            side_effect=lambda *_a, **_k: _partial_check_result(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def hobb_health(self) -> int:
        return CharacterVitals.objects.get(character_sheet=self.hobb.sheet_data).health

    def give_partial_protection_bonus(self, character, bonus: int) -> None:
        """The character's vow adds ``bonus`` to every partial protection (thread level 1)."""
        category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        target = ModifierTargetFactory(
            category=category,
            name=f"Partial protection vow {character.key}",
            scope_effect_kind=EffectKind.PARTIAL_PROTECTION,
        )
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            character.sheet_data,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=1,
        )
        VowStatScaling.objects.create(
            covenant_role=role, modifier_target=target, bonus_per_level=bonus
        )

    def give_partial_protection_distinction(self, character, bonus: int) -> None:
        """Grant ``character`` a real distinction through the game's grant service.

        The distinction carries one flat (unsized) ``+bonus`` effect on a target scoped to the
        KIND partial protection, so it reaches Succor through ``CharacterModifier`` and not
        through a vow.
        """
        category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        target = ModifierTargetFactory(
            category=category,
            name=f"Partial protection gift {character.key}",
            scope_effect_kind=EffectKind.PARTIAL_PROTECTION,
        )
        distinction = DistinctionFactory(name=f"Sheltering hands {character.key}")
        DistinctionEffectFactory(distinction=distinction, target=target, value_per_rank=bonus)
        grant_distinction(character.sheet_data, distinction, origin=DistinctionOrigin.GM_AWARD)


class _FightRound(_SuccorField):
    """Mara declares Succor for Hobb; the round resolves with the hazard ticking."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.field
        )
        CombatOpponentFactory(encounter=self.encounter)
        self.participants: dict[str, CombatParticipant] = {}
        for character in (self.hobb, self.mara):
            self.participants[character.key] = CombatParticipantFactory(
                encounter=self.encounter,
                character_sheet=character.sheet_data,
                status=ParticipantStatus.ACTIVE,
            )

    def shelter_and_resolve(self) -> None:
        result = self.web(
            self.mara,
            "combat_succor",
            ally_participant_id=self.participants[self.hobb.key].pk,
        )
        self.assertTrue(result.detail.success, result.detail.message)
        resolve_round(self.encounter)


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_succor_content gates on #2698
class SuccorInAFight(_FightRound):
    """Succor in a fight, with a vow and the catalog default as the sources."""

    def test_unmodified_partial_halves_the_hazard(self) -> None:
        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - STOPPED_BY_DEFAULT))

    def test_partial_protection_modifier_in_combat(self) -> None:
        self.give_partial_protection_bonus(self.mara, 10)

        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - STOPPED_WITH_TEN_MORE))

    def test_the_shelterers_own_number_is_the_one_read(self) -> None:
        self.give_partial_protection_bonus(self.hobb, 10)

        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - STOPPED_BY_DEFAULT))

    def test_edited_base_value_is_used(self) -> None:
        row = get_maneuver_effect(ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION)
        row.base_value = 25
        row.save()

        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - 10))


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_succor_content gates on #2698
class SuccorFromADistinctionInAFight(_FightRound):
    """A granted distinction, not a vow, adds to the same partial protection (#4783)."""

    def test_a_granted_distinction_changes_a_partial_succor(self) -> None:
        self.give_partial_protection_distinction(self.mara, 10)

        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - STOPPED_WITH_TEN_MORE))


class _SceneRound(_SuccorField):
    """No fight: a strict danger round at the yard, and Mara types ``scene succor Hobb``."""

    def setUp(self) -> None:
        super().setUp()
        self.scene_round: SceneRound = ensure_round_for_acute_condition(self.hobb.sheet_data)
        self.assertIsNotNone(self.scene_round)

    def shelter_and_resolve(self) -> None:
        told = self.telnet(self.mara, "scene succor Hobb")
        self.assertIn("You move to shelter your ally.", told)
        # An undeclared character's own peril does not tick (ADR-0004), so Hobb takes his turn,
        # and with both declared the round resolves on its own.
        self.assertEqual(self.web(self.hobb, "pass_round").detail.message, "You pass.")


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_succor_content gates on #2698
class SuccorInASceneRound(_SceneRound):
    """Succor in a scene round, with a vow and the catalog default as the sources."""

    def test_unmodified_partial_halves_the_hazard_in_a_scene_round(self) -> None:
        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - STOPPED_BY_DEFAULT))

    def test_partial_protection_modifier_in_a_scene_round(self) -> None:
        self.give_partial_protection_bonus(self.mara, 10)

        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - STOPPED_WITH_TEN_MORE))


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_succor_content gates on #2698
class SuccorFromADistinctionInASceneRound(_SceneRound):
    """The same granted distinction reaches a scene-round Succor (#4783)."""

    def test_a_granted_distinction_changes_a_partial_succor_in_a_scene_round(self) -> None:
        self.give_partial_protection_distinction(self.mara, 10)

        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100 - (HAZARD - STOPPED_WITH_TEN_MORE))
