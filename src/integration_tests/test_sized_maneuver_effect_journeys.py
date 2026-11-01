"""Journeys for a sized distinction on a damage, to-hit or partial protection effect (#4876).

Hobb, a level 11 rider, charges a bandit through the web dispatch, as in the Charge journeys;
Mara, a level 11 shelterer, covers Hobb with Succor against a 40-a-round hazard, as in the
Succor journeys. Each holds a distinction granted through the game's grant service, and staff
author the effect on the distinction effect admin page.

Expected values come from the seeded example ladders (``world/seeds/modifier_values.py``) and
the owner's ruling on #4824: damage, to-hit and partial protection take a size, valued at the
holder's level; every other kind takes flat amounts only.

* A Large modifier at level 11 is worth 6 damage, 16 to hit (the check lane's number: to-hit
  is check points) and 10 percentage points of protection.
* Charge does 5 damage and adds 10 to hit with no modifier, so a Large Charge damage
  distinction makes it 11 damage and a Large Charge to-hit distinction makes it +26.
* Succor's partial stops 50% of 40; a Large protection distinction makes it 60%, so 16 lands.
  With the base raised to 95, the same distinction stops everything: 100% is the cap.
* With the damage lane's table emptied the same distinction counts its flat +1: 6 damage.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from integration_tests.test_charge_effect_journeys import DAMAGE, TO_HIT, _ChargeField
from integration_tests.test_succor_effect_journeys import HAZARD, _FightRound
from world.checks.constants import ModifierLane, ModifierSize
from world.checks.modifier_models import ModifierValue
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.models import MANEUVER_EFFECT_SIZE_REFUSAL, DistinctionEffect
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    EffectKind,
    ManeuverEffectKey,
)
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import get_maneuver_effect
from world.mechanics.models import ModifierCategory, ModifierTarget
from world.seeds.modifier_values import seed_modifier_value_tables

LEVEL = 11
LARGE_DAMAGE_AT_11 = 6
LARGE_TO_HIT_AT_11 = 16
LARGE_PROTECTION_AT_11 = 10


def _at_level(character, level: int = LEVEL) -> None:
    CharacterClassLevelFactory(
        character=character.sheet_data,
        character_class=CharacterClassFactory(),
        level=level,
        is_primary=True,
    )
    character.sheet_data.invalidate_class_level_cache()


def _effect_target(name: str, **scope) -> ModifierTarget:
    category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
    return ModifierTargetFactory(category=category, name=name, **scope)


def _grant_sized(character, target: ModifierTarget, *, size: int | None, name: str) -> None:
    """A distinction whose one effect is +1 on ``target``, at ``size``, granted for real."""
    distinction = DistinctionFactory(name=name)
    DistinctionEffectFactory(
        distinction=distinction, target=target, value_per_rank=1, modifier_size=size
    )
    grant_distinction(character.sheet_data, distinction, origin=DistinctionOrigin.GM_AWARD)


class SizedChargeModifiers(_ChargeField):
    """Hobb's Charge with a sized distinction on its damage or its to-hit."""

    def setUp(self) -> None:
        super().setUp()
        seed_modifier_value_tables()
        _at_level(self.hobb)
        self.damage_target = _effect_target(
            "Charge: damage",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE),
        )

    def test_a_large_damage_distinction_adds_the_damage_lanes_value(self) -> None:
        _grant_sized(self.hobb, self.damage_target, size=ModifierSize.LARGE, name="Trampler")

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + LARGE_DAMAGE_AT_11)
        self.assertEqual(to_hit, TO_HIT)

    def test_the_same_distinction_unsized_adds_its_flat_amount(self) -> None:
        _grant_sized(self.hobb, self.damage_target, size=None, name="Trampler")

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + 1)

    def test_with_the_damage_lane_emptied_a_size_counts_flat(self) -> None:
        ModifierValue.objects.filter(lane=ModifierLane.DAMAGE).delete()
        _grant_sized(self.hobb, self.damage_target, size=ModifierSize.LARGE, name="Trampler")

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + 1)

    def test_a_large_to_hit_distinction_adds_the_to_hit_lanes_value(self) -> None:
        target = _effect_target(
            "Charge: to hit",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_TO_HIT),
        )
        _grant_sized(self.hobb, target, size=ModifierSize.LARGE, name="Lancer's Eye")

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(to_hit, TO_HIT + LARGE_TO_HIT_AT_11)
        self.assertEqual(damage, DAMAGE)


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_succor_content gates on #2698
class SizedSuccorProtection(_FightRound):
    """Mara's Succor partial with a sized distinction on partial protection."""

    def setUp(self) -> None:
        super().setUp()
        seed_modifier_value_tables()
        _at_level(self.mara)
        target = _effect_target(
            "Partial protection, any maneuver",
            scope_effect_kind=EffectKind.PARTIAL_PROTECTION,
        )
        _grant_sized(self.mara, target, size=ModifierSize.LARGE, name="Sheltering Hands")

    def test_a_large_protection_distinction_stops_the_lanes_share_more(self) -> None:
        self.shelter_and_resolve()

        stopped = HAZARD * (50 + LARGE_PROTECTION_AT_11) // 100
        self.assertEqual(self.hobb_health(), 100 - (HAZARD - stopped))

    def test_protection_still_stops_at_all_of_the_damage(self) -> None:
        row = get_maneuver_effect(ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION)
        row.base_value = 95
        row.save()

        self.shelter_and_resolve()

        self.assertEqual(self.hobb_health(), 100)


class SizesOnTheEffectAdminPage(_ChargeField):
    """Staff author a sized effect on the distinction effect admin page."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.distinction = DistinctionFactory(name="Trampler")

    def save_effect(self, target: ModifierTarget, size: int):
        return self.client.post(
            reverse("admin:arxii_distinctioneffect_add"),
            {
                "distinction": self.distinction.pk,
                "target": target.pk,
                "value_per_rank": "1",
                "amplifies_sources_by": "",
                "modifier_size": str(size),
                "description": "",
                "rank_sizes-TOTAL_FORMS": "0",
                "rank_sizes-INITIAL_FORMS": "0",
                "rank_sizes-MIN_NUM_FORMS": "0",
                "rank_sizes-MAX_NUM_FORMS": "1000",
            },
        )

    def test_a_size_on_a_damage_effect_saves(self) -> None:
        target = _effect_target(
            "Charge: damage",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE),
        )

        response = self.save_effect(target, ModifierSize.LARGE)

        self.assertEqual(response.status_code, 302, response.content)
        effect = DistinctionEffect.objects.get(distinction=self.distinction, target=target)
        self.assertEqual(effect.modifier_size, ModifierSize.LARGE)

    def test_a_size_on_reach_or_morale_is_refused(self) -> None:
        reach = _effect_target(
            "Charge: reach",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_REACH),
        )
        morale = _effect_target("Morale, any maneuver", scope_effect_kind=EffectKind.MORALE)
        for target in (reach, morale):
            with self.subTest(target=target.name):
                response = self.save_effect(target, ModifierSize.LARGE)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, MANEUVER_EFFECT_SIZE_REFUSAL)
                self.assertFalse(DistinctionEffect.objects.filter(target=target).exists())
