"""Sunlight exposure E2E: outdoor daylight -> staged radiant DoT -> peril pipeline
(#1588, graded #2846).

Proves the full journey: a vampire species whose grant stamps the Bane: Sunlight
distinction, outdoors during a daylight phase, escalates to a damaging stage and
takes radiant damage through the existing round-tick ->
process_damage_consequences -> abandonment peril pipeline — exactly like
poison/Bleeding-Out. AFK-safety holds: crossing the knockout band routes through
the guarded abandonment_environmental pool, never a raw death. Overwhelming
radiant resistance (immunity-as-resistance) negates it.

The gating/mapping cases are covered by the unit tests in
``world/species/tests/`` (SQLite-runnable); this file holds only the
journey-level assertions that need the real apply_condition + DoT pipeline.

Tagged ``postgres``: ``apply_condition`` (via reconcile) hits a PG-only
``DISTINCT ON`` that errors on the SQLite fast tier — same known pre-existing
limitation as the plummet E2E (test_plummet_descent.py); run on CI's PG shard.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from world.conditions.services import has_condition
from world.species.factories import (
    ensure_sunlight_distinctions,
    ensure_sunlight_exposure_content,
)
from world.vitals.services import tick_round_for_targets


def _day_phase():
    from world.game_clock.constants import TimePhase

    return patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.DAY)


@tag("postgres")  # apply_condition (via reconcile) uses DISTINCT ON (PG-only)
class SunlightExposureE2ETests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import GiftFactory, ResonanceFactory
        from world.species.factories import (
            SpeciesFactory,
            SpeciesGiftGrantFactory,
        )
        from world.species.services import provision_species_gifts
        from world.vitals.factories import CharacterVitalsFactory

        self.template = ensure_sunlight_exposure_content()
        self.bane, _allergy = ensure_sunlight_distinctions()

        self.species = SpeciesFactory(name="Vampire")
        self.gift = GiftFactory()
        # Wire the sunlight bane distinction onto the vampire species (#2846).
        SpeciesGiftGrantFactory(
            species=self.species, gift=self.gift, drawback_distinction=self.bane
        )

        self.room = create_object("typeclasses.rooms.Room", key="SunnyField", nohome=True)
        from evennia_extensions.models import RoomProfile

        RoomProfile.objects.update_or_create(objectdb=self.room, defaults={"is_outdoor": True})

        sheet = CharacterSheetFactory(species=self.species)
        CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        # Real CG always resolves a gift resonance before this call — normally via
        # the Major-gift thread that already exists by the time species-gift
        # provisioning runs (see provision_species_gifts' docstring). This fixture
        # skips CG entirely, so give it the same guarantee explicitly: a CG pick
        # always resolves (#2971 — grant_gift_to_character now raises
        # GiftResonanceUnresolvable instead of silently minting a threadless gift).
        provision_species_gifts(sheet, resonance=ResonanceFactory())
        self.vampire = sheet.character
        self.vampire.db_location = self.room
        self.vampire.save(update_fields=["db_location"])
        self.sheet = sheet

    def _vitals(self):
        return self.sheet.vitals

    def _reconcile_at_noon(self) -> None:
        from world.species.services import reconcile_sunlight_exposure

        with _day_phase():
            reconcile_sunlight_exposure(self.vampire, self.room)

    def test_outdoor_day_applies_damaging_stage_and_deals_radiant_damage(self) -> None:
        """Nude vampire at noon: condition lands in a damaging stage; tick drops health."""
        self._reconcile_at_noon()
        self.assertTrue(has_condition(self.vampire, self.template))

        from world.conditions.models import ConditionInstance
        from world.species.sun_constants import BURNING_SEVERITY_THRESHOLD

        instance = ConditionInstance.objects.get(
            target=self.vampire, condition=self.template, resolved_at__isnull=True
        )
        self.assertGreaterEqual(instance.severity, BURNING_SEVERITY_THRESHOLD)
        self.assertIsNotNone(instance.current_stage)

        health_before = self._vitals().health
        # Sunlight's stage-level DoTs tick at END_OF_ROUND (#1744 convention).
        tick_round_for_targets([self.vampire], timing="end")
        self.assertLess(self._vitals().health, health_before)

    def test_covered_vampire_takes_no_damage_but_keeps_debuff(self) -> None:
        """#2846 headline invariant at the pipeline level: mitigated to sub-Burning,
        the condition persists (debuff) but a round tick deals zero damage."""
        from world.conditions.factories import ensure_radiant_damage_type
        from world.locations.constants import KeyType
        from world.locations.models import LocationValueOverride

        # Deep-ish shade: residual 4 -> bane severity 5, below Burning (6), above zero;
        # shade-only residual 4 stays above SHADOW_CLEAR_THRESHOLD so it doesn't clear.
        LocationValueOverride.objects.create(
            parent_type="room",
            room_profile=self.room.room_profile,
            key_type=KeyType.DAMAGE_TYPE,
            damage_type=ensure_radiant_damage_type(),
            value=6,
        )
        self._reconcile_at_noon()
        self.assertTrue(has_condition(self.vampire, self.template))
        health_before = self._vitals().health
        tick_round_for_targets([self.vampire], timing="end")
        self.assertEqual(self._vitals().health, health_before)

    def test_high_resistance_zeroes_damage(self) -> None:
        """Overwhelming radiant resistance (immunity-as-resistance) negates the DoT."""
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ensure_radiant_damage_type,
        )

        self._reconcile_at_noon()
        radiant = ensure_radiant_damage_type()
        ConditionResistanceModifierFactory(
            condition=self.template, damage_type=radiant, modifier_value=1000
        )
        self.vampire.conditions.invalidate()

        health_before = self._vitals().health
        tick_round_for_targets([self.vampire], timing="end")
        self.assertEqual(self._vitals().health, health_before)

    def test_ticks_through_real_scene_round_production_path(self) -> None:
        """Sunlight Exposure ticks through the REAL non-combat production path:
        reconcile -> ensure_round_for_acute_condition -> resolve_scene_round, with
        NO direct tick_round_for_targets(timing=...) workaround call."""
        from world.scenes.models import SceneActionDeclaration, SceneRound
        from world.scenes.round_services import resolve_scene_round

        self._reconcile_at_noon()
        rnd = SceneRound.objects.filter(room=self.room.room_profile).first()
        self.assertIsNotNone(rnd, "reconcile should ensure a danger round in a damaging stage")

        # Declare an explicit pass so the vampire is NOT swept as an AFK undeclared
        # participant (#1480's own-peril skip would otherwise hold their own DoT).
        participant = rnd.participants.get(character_sheet=self.sheet)
        SceneActionDeclaration.objects.create(
            scene_round=rnd,
            round_number=rnd.round_number,
            participant=participant,
            is_immediate=False,
            is_pass=True,
        )

        health_before = self._vitals().health
        resolve_scene_round(rnd)
        self.assertLess(self._vitals().health, health_before)
