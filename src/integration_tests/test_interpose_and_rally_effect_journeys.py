"""Journeys for Interpose and Rally reading the maneuver effect catalog (#4783).

Interpose: Hobb and Mara stand in a yard against a brute whose swing hits Hobb for 40. Mara
declares Interpose for Hobb through the web client (``combat_interpose``), and her interpose
roll lands as a partial: not a clean block, not a failure. What is read back is Hobb's health
after the round resolves. The catalog default stops 50% on a partial, so 20 of the 40 lands.
A +10 on Mara's Interpose partial protection (her vow, +10 per level at thread level 1) stops
60%, so 16 lands. Only the interposer's own number counts.

Rally: Mira rallies Tomas through ``combat rally Tomas`` and her roll is a great success at
success level 3. An ally summon at 30 morale gains success level x the Rally morale value:
the catalog's 15 gives 45; a +5 on Mira's Rally morale (her vow at thread level 1) gives
3 x 20 = 60.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from django.test import override_settings

from integration_tests.harness import JourneyCase
from integration_tests.test_surge_rolls_journeys import _SurgeField
from world.areas.positioning.plummet_content import ensure_catch_content
from world.checks.types import CheckResult
from world.combat.constants import (
    RALLY_GREAT_SUCCESS_LEVEL,
    CombatAllegiance,
    ParticipantStatus,
    SurgeTriggerKind,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    ThreatRecordFactory,
)
from world.combat.interpose_content import ensure_interpose_content
from world.combat.services import resolve_round
from world.conditions.factories import ConditionCapabilityEffectFactory, ConditionTemplateFactory
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, engage_vow_with_thread
from world.covenants.models import VowStatScaling
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.scenes.constants import RoundStatus
from world.seeds.combat_checks import seed_combat_check_content
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitType,
)
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatOpponent

HEALTH = 100
SWING = 40
STOPPED_BY_DEFAULT = 20  # 50% of 40
STOPPED_WITH_TEN_MORE = 24  # 60% of 40
# Above the break threshold (25), so the hound stays to be rallied; 100 caps nothing here.
HOUND_MORALE = 30
CHALLENGE_PERFORM_CHECK = "world.mechanics.challenge_resolution.perform_check"


def give_effect_bonus(character: ObjectDB, key: str, bonus: int) -> None:
    """The character's vow adds ``bonus`` to maneuver effect ``key`` (thread level 1)."""
    target = ModifierTargetFactory(
        category=ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME),
        name=f"{key} vow {character.key}",
        scope_maneuver_effect=get_maneuver_effect(key),
    )
    role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
    engage_vow_with_thread(
        character.sheet_data,
        role,
        covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
        thread_level=1,
    )
    VowStatScaling.objects.create(covenant_role=role, modifier_target=target, bonus_per_level=bonus)


def _partial_interpose(*_args: object, **_kwargs: object) -> CheckResult:
    """An interpose roll that lands as a partial: success level 0."""
    return CheckResult(
        check_type=None,
        outcome=CheckOutcomeFactory(name="Partial interpose", success_level=0),
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


def _full_swing(*_args: object, **_kwargs: object) -> MagicMock:
    """Hobb's own defence roll at success level 0: the swing lands at full strength."""
    return MagicMock(success_level=0)


def _no_offense(*_args: object, **_kwargs: object) -> MagicMock:
    return MagicMock(success_level=0)


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_interpose_content gates on #2698
class InterposeReadsTheCatalog(JourneyCase):
    """Mara steps into the brute's swing at Hobb, and her block is a partial."""

    def setUp(self) -> None:
        seed_combat_check_content()
        ensure_interpose_content()
        ensure_catch_content()
        super().setUp()
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()
        ensure_maneuver_effects()
        for trait_type in (TraitType.STAT, TraitType.SKILL):
            PointConversionRange.objects.get_or_create(
                trait_type=trait_type,
                min_value=1,
                defaults={"max_value": 100, "points_per_level": 1},
            )
        self.yard = self.make_room("The Brute's Yard")
        self.hobb = self.make_player("Hobb", room=self.yard)
        self.mara = self.make_player("Mara", room=self.yard)
        for character in (self.hobb, self.mara):
            CharacterVitals.objects.create(
                character_sheet=character.sheet_data,
                health=HEALTH,
                max_health=HEALTH,
                base_max_health=HEALTH,
            )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.hobb_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.hobb.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.mara.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            base_damage=SWING,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        brute = CombatOpponentFactory(
            encounter=self.encounter, threat_pool=pool, health=50, max_health=50, soak_value=0
        )
        ThreatRecordFactory(
            encounter=self.encounter, opponent=brute, participant=self.hobb_seat, threat_value=20
        )
        # Mara can interpose through telekinesis, a seeded Interpose capability, and is built
        # for Reflexes.
        telekinetic = ConditionTemplateFactory(name="Telekinetic Reach")
        ConditionCapabilityEffectFactory(
            condition=telekinetic,
            capability=CapabilityType.objects.get(name="telekinesis"),
            value=10,
        )
        apply_condition(self.mara, telekinetic)
        for name, value in (("wits", 30), ("agility", 1), ("Melee Combat", 1)):
            CharacterTraitValue.objects.create(
                character=self.mara.sheet_data, trait=Trait.objects.get(name=name), value=value
            )

    def hobb_health(self) -> int:
        return CharacterVitals.objects.get(character_sheet=self.hobb.sheet_data).health

    def interpose_and_resolve(self) -> None:
        result = self.web(self.mara, "combat_interpose", ally_participant_id=self.hobb_seat.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        with patch(CHALLENGE_PERFORM_CHECK, side_effect=_partial_interpose):
            resolve_round(
                self.encounter, defense_check_fn=_full_swing, offense_check_fn=_no_offense
            )

    def test_unmodified_partial_interpose_halves_the_hit(self) -> None:
        self.interpose_and_resolve()

        self.assertEqual(self.hobb_health(), HEALTH - (SWING - STOPPED_BY_DEFAULT))

    def test_partial_protection_modifier_on_interpose(self) -> None:
        give_effect_bonus(self.mara, ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION, 10)

        self.interpose_and_resolve()

        self.assertEqual(self.hobb_health(), HEALTH - (SWING - STOPPED_WITH_TEN_MORE))

    def test_the_protected_character_s_own_number_is_not_read(self) -> None:
        give_effect_bonus(self.hobb, ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION, 10)

        self.interpose_and_resolve()

        self.assertEqual(self.hobb_health(), HEALTH - (SWING - STOPPED_BY_DEFAULT))

    def test_a_succor_modifier_does_not_reach_interpose(self) -> None:
        give_effect_bonus(self.mara, ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION, 10)

        self.interpose_and_resolve()

        self.assertEqual(self.hobb_health(), HEALTH - (SWING - STOPPED_BY_DEFAULT))


class RallyMoraleReadsTheCatalog(_SurgeField):
    """Mira's great-success rally restores morale to the side's summoned ally."""

    def setUp(self) -> None:
        super().setUp()
        ensure_maneuver_effects()
        self.enter_combat(self.mira, self.tomas)
        self.author_tuning(SurgeTriggerKind.RALLIED, "Rally", partial=1, success=1)
        self.great_success = CheckOutcomeFactory(
            name="Great rally", success_level=RALLY_GREAT_SUCCESS_LEVEL
        )
        self.hound: CombatOpponent = CombatOpponentFactory(
            encounter=self.encounter,
            name="Summoned hound",
            allegiance=CombatAllegiance.ALLY,
            morale=HOUND_MORALE,
            max_morale=100,
        )

    def rally_and_resolve(self) -> int:
        """Mira rallies Tomas at a great success; returns the morale the hound gained."""
        told = self.telnet(self.mira, "combat rally Tomas")
        self.assertIn("You rally your ally.", told)
        self.resolve(self.great_success)
        self.hound.refresh_from_db()
        return self.hound.morale - HOUND_MORALE

    def test_rally_morale_reads_catalog(self) -> None:
        self.assertEqual(self.rally_and_resolve(), RALLY_GREAT_SUCCESS_LEVEL * 15)

    def test_rally_morale_modifier_adds_per_success_level(self) -> None:
        give_effect_bonus(self.mira, ManeuverEffectKey.RALLY_MORALE, 5)

        self.assertEqual(self.rally_and_resolve(), RALLY_GREAT_SUCCESS_LEVEL * 20)

    def test_edited_base_value_is_used(self) -> None:
        row = get_maneuver_effect(ManeuverEffectKey.RALLY_MORALE)
        row.base_value = 10
        row.save()

        self.assertEqual(self.rally_and_resolve(), RALLY_GREAT_SUCCESS_LEVEL * 10)
