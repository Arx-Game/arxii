"""Tests for mounted combat — CHARGE, JOUST, and the unmounted-lance penalty (#1843)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from world.areas.positioning.services import (
    connect_positions,
    create_position,
    place_in_position,
    position_of,
)
from world.combat.constants import (
    CHARGE_DAMAGE_BONUS,
    JOUST_DECISIVE_MARGIN,
    CombatManeuver,
    EncounterType,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import (
    _equipped_weapon_archetype,
    _resolve_charge_movement,
    _resolve_joust_pass,
    declare_charge,
    declare_joust,
)
from world.combat.tests.test_combat_technique_resolver import _build_resolver
from world.companions.mount_content import (
    MOUNTED_CONDITION_NAME,
    UNHORSED_CONDITION_NAME,
    ensure_mount_conditions,
)
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition, has_condition
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import EquippedItem
from world.magic.factories import TechniqueDamageProfileFactory
from world.scenes.constants import RoundStatus


def _mount(character) -> None:
    ensure_mount_conditions()
    apply_condition(character, ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME))


def _mount_with_companion(sheet):
    """Mount *sheet* on a real, live-objectdb Companion (dismount-capable).

    Unlike ``_mount`` (which stamps the Mounted condition directly), this
    goes through the real ``mount_companion`` service so a JOUST's decisive
    unhorsing can exercise the actual ``dismount_companion`` force-dismount.
    """
    from evennia.utils.create import create_object

    from typeclasses.companions import CompanionObject
    from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
    from world.companions.services import mount_companion

    archetype = CompanionArchetypeFactory(is_mount=True)
    companion = CompanionFactory(owner=sheet, archetype=archetype)
    obj = create_object(CompanionObject, key=companion.name, nohome=True)
    companion.objectdb = obj
    companion.save(update_fields=["objectdb"])
    mount_companion(sheet, companion)
    return companion


def _equip_weapon(character, *, archetype, damage=6, durability=10):
    template = ItemTemplateFactory(
        weapon=True,
        gear_archetype=archetype,
        base_weapon_damage=damage,
        max_durability=durability,
    )
    inst = ItemInstanceFactory(template=template, durability=durability)
    EquippedItem.objects.create(
        character=character,
        item_instance=inst,
        body_region=BodyRegion.RIGHT_HAND,
        equipment_layer=EquipmentLayer.BASE,
    )
    character.equipped_items.invalidate()
    return inst


class MountedCombatConstantsTests(TestCase):
    def test_charge_and_joust_maneuvers_exist(self):
        assert CombatManeuver.CHARGE == "charge"
        assert CombatManeuver.JOUST == "joust"


class DeclareChargeTests(TestCase):
    def setUp(self) -> None:
        ensure_mount_conditions()
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.rider = self.participant.character_sheet.character
        self.rider.move_to(self.encounter.room, quiet=True)

    def _technique(self):
        resolver = _build_resolver()
        return resolver.action.focused_action

    def test_rejected_when_not_mounted(self):
        with self.assertRaises(ValueError):
            declare_charge(self.participant, self._technique(), self.opponent)

    def test_rejected_when_target_already_within_reach(self):
        _mount(self.rider)
        room = self.encounter.room
        pos = create_position(room, "Same Spot")
        place_in_position(self.rider, pos)
        place_in_position(self.opponent.objectdb, pos)
        with self.assertRaises(ValueError):
            declare_charge(self.participant, self._technique(), self.opponent)

    def test_rejected_against_defeated_opponent(self):
        from world.combat.constants import OpponentStatus

        _mount(self.rider)
        self.opponent.status = OpponentStatus.DEFEATED
        self.opponent.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            declare_charge(self.participant, self._technique(), self.opponent)

    def test_happy_path_declares_charge(self):
        _mount(self.rider)
        room = self.encounter.room
        rider_pos = create_position(room, "Rider Spot")
        target_pos = create_position(room, "Target Spot")
        connect_positions(rider_pos, target_pos)
        place_in_position(self.rider, rider_pos)
        place_in_position(self.opponent.objectdb, target_pos)

        technique = self._technique()
        action = declare_charge(self.participant, technique, self.opponent)
        self.assertEqual(action.maneuver, CombatManeuver.CHARGE)
        self.assertEqual(action.focused_opponent_target_id, self.opponent.pk)
        self.assertEqual(action.focused_action_id, technique.pk)


class ChargeMovementTests(TestCase):
    def test_resolve_charge_movement_moves_rider_onto_target_position(self):
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        opponent = CombatOpponentFactory(encounter=encounter)
        rider = participant.character_sheet.character
        rider.move_to(encounter.room, quiet=True)

        room = encounter.room
        rider_pos = create_position(room, "Rider Spot")
        target_pos = create_position(room, "Target Spot")
        connect_positions(rider_pos, target_pos)
        place_in_position(rider, rider_pos)
        place_in_position(opponent.objectdb, target_pos)

        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            maneuver=CombatManeuver.CHARGE,
            focused_opponent_target=opponent,
        )
        _resolve_charge_movement(participant, action)

        self.assertEqual(position_of(rider).pk, target_pos.pk)


class ChargeDispatchSeamTests(TestCase):
    """CHARGE declares through the same dispatch_player_action seam telnet/web use."""

    def test_charge_declares_through_dispatch(self):
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        opponent = CombatOpponentFactory(encounter=encounter)
        rider = participant.character_sheet.character
        rider.move_to(encounter.room, quiet=True)
        _mount(rider)

        room = encounter.room
        rider_pos = create_position(room, "Rider Spot")
        target_pos = create_position(room, "Target Spot")
        connect_positions(rider_pos, target_pos)
        place_in_position(rider, rider_pos)
        place_in_position(opponent.objectdb, target_pos)

        technique = _build_resolver().action.focused_action

        result = dispatch_player_action(
            rider,
            ActionRef(backend=ActionBackend.REGISTRY, registry_key="combat_charge"),
            {"opponent_id": opponent.pk, "technique_id": technique.pk},
        )
        self.assertTrue(result.detail.success, result.detail.message)
        action = CombatRoundAction.objects.get(participant=participant, round_number=1)
        self.assertEqual(action.maneuver, CombatManeuver.CHARGE)
        self.assertEqual(action.focused_opponent_target_id, opponent.pk)


class ChargeBonusInjectionTests(TestCase):
    """CHARGE_CHECK_BONUS/CHARGE_DAMAGE_BONUS are folded in at the shared modifier seam."""

    def setUp(self) -> None:
        from world.conditions.factories import DamageSuccessLevelMultiplierFactory

        ensure_mount_conditions()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )

    def _resolver(self, *, maneuver=None, uses_equipped_weapon=False):
        resolver = _build_resolver(base_power=20)
        resolver.action.focused_action.damage_profiles.all().delete()
        TechniqueDamageProfileFactory(
            technique=resolver.action.focused_action,
            base_damage=0,
            damage_type=None,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=0,
            minimum_success_level=1,
            uses_equipped_weapon=uses_equipped_weapon,
        )
        if maneuver is not None:
            resolver.action.maneuver = maneuver
            resolver.action.save(update_fields=["maneuver"])
        return resolver

    def _extra_modifiers(self, resolver) -> int:
        captured = {}

        def _spy(character, check_type, **kwargs):
            captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            return MagicMock(success_level=2)

        with patch("world.combat.services.perform_check", side_effect=_spy):
            resolver._roll_check()
        return captured["extra_modifiers"]

    def test_charge_check_bonus_applied(self):
        baseline = self._resolver()
        charged = self._resolver(maneuver=CombatManeuver.CHARGE)
        delta = self._extra_modifiers(charged) - self._extra_modifiers(baseline)
        from world.combat.constants import CHARGE_CHECK_BONUS

        self.assertEqual(delta, CHARGE_CHECK_BONUS)

    def test_charge_check_bonus_doubled_for_lance(self):
        charged = self._resolver(maneuver=CombatManeuver.CHARGE)
        without_lance = self._extra_modifiers(charged)

        charged_lance = self._resolver(maneuver=CombatManeuver.CHARGE)
        lance_character = charged_lance.participant.character_sheet.character
        _equip_weapon(lance_character, archetype=GearArchetype.LANCE)
        # Mounted so LANCE_UNMOUNTED_PENALTY doesn't also confound the delta.
        _mount(lance_character)
        with_lance = self._extra_modifiers(charged_lance)

        from world.combat.constants import CHARGE_CHECK_BONUS

        self.assertEqual(with_lance - without_lance, CHARGE_CHECK_BONUS)

    def test_charge_damage_bonus_applied(self):
        resolver = self._resolver(maneuver=CombatManeuver.CHARGE)
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check, eff_intensity=0)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].damage_dealt, CHARGE_DAMAGE_BONUS)

    def test_charge_damage_bonus_doubled_for_lance(self):
        resolver = self._resolver(maneuver=CombatManeuver.CHARGE)
        _equip_weapon(resolver.participant.character_sheet.character, archetype=GearArchetype.LANCE)
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check, eff_intensity=0)
        self.assertEqual(results[0].damage_dealt, CHARGE_DAMAGE_BONUS * 2)


class LanceUnmountedPenaltyTests(TestCase):
    def setUp(self) -> None:
        ensure_mount_conditions()

    def _resolver(self):
        return _build_resolver(base_power=20)

    def test_penalty_applied_when_unmounted_with_lance(self):
        resolver = self._resolver()
        _equip_weapon(resolver.participant.character_sheet.character, archetype=GearArchetype.LANCE)

        captured = {}

        def _spy(character, check_type, **kwargs):
            captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            return MagicMock(success_level=2)

        with patch("world.combat.services.perform_check", side_effect=_spy):
            resolver._roll_check()

        baseline_resolver = self._resolver()
        baseline_captured = {}

        def _spy_baseline(character, check_type, **kwargs):
            baseline_captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            return MagicMock(success_level=2)

        with patch("world.combat.services.perform_check", side_effect=_spy_baseline):
            baseline_resolver._roll_check()

        from world.combat.constants import LANCE_UNMOUNTED_PENALTY

        self.assertEqual(
            captured["extra_modifiers"] - baseline_captured["extra_modifiers"],
            LANCE_UNMOUNTED_PENALTY,
        )

    def test_no_penalty_when_mounted_with_lance(self):
        resolver = self._resolver()
        character = resolver.participant.character_sheet.character
        _equip_weapon(character, archetype=GearArchetype.LANCE)
        _mount(character)

        captured = {}

        def _spy(char, check_type, **kwargs):
            captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            return MagicMock(success_level=2)

        with patch("world.combat.services.perform_check", side_effect=_spy):
            resolver._roll_check()

        baseline_resolver = self._resolver()
        baseline_captured = {}

        def _spy_baseline(char, check_type, **kwargs):
            baseline_captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            return MagicMock(success_level=2)

        with patch("world.combat.services.perform_check", side_effect=_spy_baseline):
            baseline_resolver._roll_check()

        # Mounted + lance: no unmounted-lance penalty, so the delta is 0.
        self.assertEqual(
            captured["extra_modifiers"] - baseline_captured["extra_modifiers"],
            0,
        )

    def test_equipped_weapon_archetype_helper(self):
        resolver = self._resolver()
        character = resolver.participant.character_sheet.character
        self.assertIsNone(_equipped_weapon_archetype(character))
        _equip_weapon(character, archetype=GearArchetype.LANCE)
        self.assertEqual(_equipped_weapon_archetype(character), GearArchetype.LANCE)


class DeclareJoustTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, encounter_type=EncounterType.PARTY_COMBAT
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )

    def _technique(self):
        resolver = _build_resolver()
        return resolver.action.focused_action

    def test_rejected_outside_duel(self):
        with self.assertRaises(ValueError):
            declare_joust(self.participant, self._technique())

    def test_rejected_without_second_duelist(self):
        duel = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, encounter_type=EncounterType.DUEL
        )
        solo = CombatParticipantFactory(encounter=duel, status=ParticipantStatus.ACTIVE)
        with self.assertRaises(ValueError):
            declare_joust(solo, self._technique())

    def test_rejected_when_not_both_mounted_and_lanced(self):
        duel = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, encounter_type=EncounterType.DUEL
        )
        a = CombatParticipantFactory(encounter=duel, status=ParticipantStatus.ACTIVE)
        CombatParticipantFactory(encounter=duel, status=ParticipantStatus.ACTIVE)
        _mount(a.character_sheet.character)
        _equip_weapon(a.character_sheet.character, archetype=GearArchetype.LANCE)
        # The second duelist is neither mounted nor lanced.
        with self.assertRaises(ValueError):
            declare_joust(a, self._technique())

    def test_happy_path_declares_joust(self):
        duel = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, encounter_type=EncounterType.DUEL
        )
        a = CombatParticipantFactory(encounter=duel, status=ParticipantStatus.ACTIVE)
        b = CombatParticipantFactory(encounter=duel, status=ParticipantStatus.ACTIVE)
        for combatant in (a, b):
            _mount(combatant.character_sheet.character)
            _equip_weapon(combatant.character_sheet.character, archetype=GearArchetype.LANCE)

        technique = self._technique()
        action = declare_joust(a, technique)
        self.assertEqual(action.maneuver, CombatManeuver.JOUST)


class JoustResolutionTests(TestCase):
    """_resolve_joust_pass grades the opposed pass by the success_level gap."""

    def _duel_pair(self):
        ensure_mount_conditions()
        duel = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, encounter_type=EncounterType.DUEL
        )
        a = CombatParticipantFactory(encounter=duel, status=ParticipantStatus.ACTIVE)
        b = CombatParticipantFactory(encounter=duel, status=ParticipantStatus.ACTIVE)
        mirror_a = CombatOpponentFactory(encounter=duel)
        mirror_b = CombatOpponentFactory(encounter=duel)
        mirror_a.mirrors_participant = a
        mirror_a.save(update_fields=["mirrors_participant"])
        mirror_b.mirrors_participant = b
        mirror_b.save(update_fields=["mirrors_participant"])

        for combatant in (a, b):
            _mount_with_companion(combatant.character_sheet)
            _equip_weapon(combatant.character_sheet.character, archetype=GearArchetype.LANCE)

        resolver = _build_resolver()
        technique = resolver.action.focused_action
        from actions.factories import ActionTemplateFactory

        technique.action_template = ActionTemplateFactory()
        technique.save(update_fields=["action_template"])

        action_a = CombatRoundAction.objects.create(
            participant=a,
            round_number=1,
            maneuver=CombatManeuver.JOUST,
            focused_action=technique,
        )
        action_b = CombatRoundAction.objects.create(
            participant=b,
            round_number=1,
            maneuver=CombatManeuver.JOUST,
            focused_action=technique,
        )
        return a, action_a, mirror_a, b, action_b, mirror_b

    def test_decisive_margin_unhorses_loser(self):
        a, action_a, _mirror_a, b, action_b, mirror_b = self._duel_pair()
        with patch(
            "world.combat.services.perform_check",
            side_effect=[
                MagicMock(success_level=4),  # a
                MagicMock(success_level=0),  # b — gap 4, well past decisive
            ],
        ):
            _resolve_joust_pass(a, action_a, b, action_b)

        mirror_b.refresh_from_db()
        # Decisive: loser takes the winner's lance weapon damage x2.
        self.assertLess(mirror_b.health, mirror_b.max_health)
        loser_sheet = b.character_sheet
        self.assertTrue(
            has_condition(
                loser_sheet.character, ConditionTemplate.get_by_name(UNHORSED_CONDITION_NAME)
            )
        )
        self.assertFalse(
            has_condition(
                loser_sheet.character, ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
            )
        )

    def test_narrow_margin_deals_damage_without_unhorsing(self):
        a, action_a, _mirror_a, b, action_b, _mirror_b = self._duel_pair()
        gap = JOUST_DECISIVE_MARGIN - 1  # narrow band, guaranteed >= JOUST_NARROW_MARGIN (==1)
        with patch(
            "world.combat.services.perform_check",
            side_effect=[
                MagicMock(success_level=gap),
                MagicMock(success_level=0),
            ],
        ):
            _resolve_joust_pass(a, action_a, b, action_b)

        loser_sheet = b.character_sheet
        self.assertFalse(
            has_condition(
                loser_sheet.character, ConditionTemplate.get_by_name(UNHORSED_CONDITION_NAME)
            )
        )
        # Still mounted — kept the saddle.
        self.assertTrue(
            has_condition(
                loser_sheet.character, ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
            )
        )

    def test_tie_jars_both_with_no_damage(self):
        a, action_a, _mirror_a, b, action_b, _mirror_b = self._duel_pair()
        with patch(
            "world.combat.services.perform_check",
            side_effect=[
                MagicMock(success_level=2),
                MagicMock(success_level=2),
            ],
        ):
            _resolve_joust_pass(a, action_a, b, action_b)

        # Both still mounted — a tie is jarring, not unhorsing.
        for combatant in (a, b):
            self.assertTrue(
                has_condition(
                    combatant.character_sheet.character,
                    ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME),
                )
            )
