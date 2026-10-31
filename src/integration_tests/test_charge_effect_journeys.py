"""Journeys for a charge that reads the maneuver effect catalog (#4783).

Hobb is a mounted rider in a fight at the Steading, three positions in a row (Lane - Barn -
Yard); the bandit stands in the Barn. He charges with ``combat_charge`` through the web
dispatch, the round resolves with every check forced to Success, and the numbers read back are
what his charge added to the roll (the ``extra_modifiers`` the attack check was rolled with)
and what it did to the bandit's health. His technique does no damage of its own, so the bandit's
lost health is the charge's own damage.

Expected values are the catalog's defaults and the spec: a charge adds +10 to hit and +5
damage, doubled by a lance (the base only; a modifier is never doubled); its reach is 5 hops.
A vow's stat scaling of +1 a level on a Charge damage target, at shown thread level 3, adds 3
(a lance does not double it: 5 x 2 + 3 = 13). Staff change a base on the Maneuver effect admin
page and the next charge uses it.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.areas.positioning.services import (
    connect_positions,
    create_position,
    place_in_position,
)
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import resolve_round
from world.combat.tests.test_mounted_combat import _equip_weapon, _mount
from world.companions.mount_content import ensure_mount_conditions
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, engage_vow_with_thread
from world.covenants.models import VowStatScaling
from world.items.constants import GearArchetype
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    ManeuverEffectKey,
)
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from collections.abc import Iterator

TO_HIT = 10
DAMAGE = 5
NOT_REACHABLE = "Cannot charge: the target is not reachable."


class _ChargeField(JourneyCase):
    """Hobb, mounted at the Lane, and a bandit in the Barn with a Yard behind it."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        ensure_mount_conditions()
        ensure_maneuver_effects()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("1.00"), label="Full"
        )
        self.steading = self.make_room("The Steading")
        self.hobb = self.make_player("Hobb", room=self.steading)
        self.sheet = self.hobb.sheet_data
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=30)

        self.attack_check = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=self.attack_check, trait=StatTraitFactory(), weight=1)
        # A technique with no damage of its own: what the bandit loses is the charge's.
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.attack_check),
        )
        TechniqueDamageProfileFactory(
            technique=self.technique,
            base_damage=0,
            damage_type=None,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=0,
            minimum_success_level=1,
            uses_equipped_weapon=False,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.steading
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.bandit = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit", health=200, max_health=200
        )
        self.lane = create_position(self.steading, "Lane")
        self.barn = create_position(self.steading, "Barn")
        self.yard = create_position(self.steading, "Yard")
        connect_positions(self.lane, self.barn)
        connect_positions(self.barn, self.yard)
        place_in_position(self.hobb, self.lane)
        place_in_position(self.bandit.objectdb, self.barn)
        _mount(self.hobb)

    def charge(self):
        return self.web(
            self.hobb,
            "combat_charge",
            opponent_id=self.bandit.pk,
            technique_id=self.technique.pk,
        )

    @contextmanager
    def success_recording_to_hit(self) -> Iterator[list[int]]:
        """Every check lands at Success; the list gets what each attack was rolled with."""
        outcome = CheckOutcome.objects.get(name="Success")
        rolled: list[int] = []

        def forced(character, check_type, *args, **kwargs):
            if check_type == self.attack_check:
                rolled.append(kwargs["extra_modifiers"])
            with force_check_outcome(outcome):
                return perform_check(character, check_type, *args, **kwargs)

        with patch("world.combat.services.perform_check", side_effect=forced):
            yield rolled

    def charge_and_resolve(self) -> tuple[int, int]:
        """Declare the charge, resolve the round; return (what it added to hit, damage)."""
        result = self.charge()
        self.assertTrue(result.detail.success, result.detail.message)
        before = CombatOpponent.objects.get(pk=self.bandit.pk).health
        with self.success_recording_to_hit() as rolled:
            resolve_round(self.encounter)
        after = CombatOpponent.objects.get(pk=self.bandit.pk).health
        self.assertEqual(len(rolled), 1)
        return rolled[0], before - after

    def swear_to_charge_harder(self, bonus_per_level: int = 1, thread_level: int = 3) -> None:
        """Hobb engages a vow at shown ``thread_level`` that scales Charge damage per level."""
        category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        target = ModifierTargetFactory(
            category=category,
            name="Charge damage vow",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE),
        )
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            self.sheet,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=thread_level,
        )
        VowStatScaling.objects.create(
            covenant_role=role, modifier_target=target, bonus_per_level=bonus_per_level
        )


class ChargeReadsTheCatalog(_ChargeField):
    def test_unmodified_charge_matches_today(self) -> None:
        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(to_hit, TO_HIT)
        self.assertEqual(damage, DAMAGE)

    def test_unmodified_lance_charge_doubles_both(self) -> None:
        _equip_weapon(self.hobb, archetype=GearArchetype.LANCE)

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(to_hit, 2 * TO_HIT)
        self.assertEqual(damage, 2 * DAMAGE)

    def test_vow_scaled_charge_damage(self) -> None:
        self.swear_to_charge_harder()

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + 3)
        self.assertEqual(to_hit, TO_HIT)

    def test_a_lance_doubles_only_the_base_not_the_vow(self) -> None:
        self.swear_to_charge_harder()
        _equip_weapon(self.hobb, archetype=GearArchetype.LANCE)

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, 2 * DAMAGE + 3)
        self.assertEqual(to_hit, 2 * TO_HIT)

    def test_a_negative_vow_is_floored_once_on_a_lances_whole_total(self) -> None:
        self.swear_to_charge_harder(bonus_per_level=-8, thread_level=1)  # a -8 modifier
        _equip_weapon(self.hobb, archetype=GearArchetype.LANCE)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, 2 * DAMAGE - 8)

    def test_a_negative_vow_floors_an_unlanced_charge_at_nothing(self) -> None:
        self.swear_to_charge_harder(bonus_per_level=-8, thread_level=1)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, 0)

    def test_edited_base_value_is_used(self) -> None:
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        row = get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE)

        response = self.client.post(
            reverse("admin:arxii_maneuvereffect_change", args=[row.pk]),
            {"base_value": "7", "notes": ""},
        )
        self.assertEqual(response.status_code, 302, response.content)

        _to_hit, damage = self.charge_and_resolve()
        self.assertEqual(damage, 7)

    def test_charge_reach_reads_catalog(self) -> None:
        place_in_position(self.bandit.objectdb, self.yard)  # two hops from the Lane
        reach = get_maneuver_effect(ManeuverEffectKey.CHARGE_REACH)
        reach.base_value = 1
        reach.save()

        refused = self.charge()

        self.assertFalse(refused.detail.success)
        self.assertEqual(refused.detail.message, NOT_REACHABLE)

    def test_the_default_reach_still_covers_two_hops(self) -> None:
        place_in_position(self.bandit.objectdb, self.yard)

        result = self.charge()

        self.assertTrue(result.detail.success, result.detail.message)
