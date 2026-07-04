"""Sunlight exposure E2E: outdoor daylight -> radiant DoT -> peril pipeline (#1588).

Proves the full journey: a vampire whose species grants a Sunlight-Exposure
drawback, outdoors during a daylight phase, takes radiant damage through the
existing round-tick -> process_damage_consequences -> abandonment peril
pipeline — exactly like poison/Bleeding-Out. AFK-safety holds: crossing the
knockout band routes through the guarded abandonment_environmental pool, never
a raw death. Overwhelming radiant resistance (immunity-as-resistance) negates it.

The indoor/night gating cases are covered by the unit tests in
``test_sunlight_exposure.py`` (SQLite-runnable); this file holds only the
journey-level assertions that need the real apply_condition + DoT pipeline.

Tagged ``postgres``: ``apply_condition`` (via reconcile) hits a PG-only
``DISTINCT ON`` that errors on the SQLite fast tier — same known pre-existing
limitation as the plummet E2E (test_plummet_descent.py); run on CI's PG shard.
"""

from __future__ import annotations

from django.test import TestCase, tag

from world.conditions.services import has_condition
from world.species.factories import ensure_sunlight_exposure_content
from world.vitals.services import tick_round_for_targets


@tag("postgres")  # apply_condition (via reconcile) uses DISTINCT ON (PG-only)
class SunlightExposureE2ETests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import GiftFactory
        from world.species.factories import (
            SpeciesFactory,
            SpeciesGiftGrantFactory,
        )
        from world.vitals.factories import CharacterVitalsFactory

        self.template = ensure_sunlight_exposure_content()

        self.species = SpeciesFactory(name="Vampire")
        self.gift = GiftFactory()
        # Wire the sunlight drawback onto the vampire species.
        SpeciesGiftGrantFactory(
            species=self.species, gift=self.gift, drawback_condition=self.template
        )

        self.room = create_object("typeclasses.rooms.Room", key="SunnyField", nohome=True)
        # Mark the room outdoor via its RoomProfile.
        from evennia_extensions.models import RoomProfile

        RoomProfile.objects.update_or_create(objectdb=self.room, defaults={"is_outdoor": True})

        sheet = CharacterSheetFactory(species=self.species)
        CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        self.vampire = sheet.character
        self.vampire.db_location = self.room
        self.vampire.save(update_fields=["db_location"])
        self.sheet = sheet

    def _vitals(self):
        return self.sheet.vitals

    def test_outdoor_day_applies_condition_and_deals_radiant_damage(self) -> None:
        """Exposure -> condition applied -> round-tick deals radiant damage (health drops)."""
        from unittest.mock import patch

        from world.game_clock.constants import TimePhase

        with patch(
            "world.species.services.get_ic_phase",
            return_value=TimePhase.DAY,
        ):
            from world.species.services import reconcile_sunlight_exposure

            reconcile_sunlight_exposure(self.vampire, self.room)

        # Condition is now active.
        self.assertTrue(has_condition(self.vampire, self.template))

        health_before = self._vitals().health
        # The round tick processes the radiant ConditionDamageOverTime. Sunlight
        # Exposure's DoT ticks at END_OF_ROUND (#1744) — matching poison's
        # convention and the only timing Succor's cover window / non-combat
        # resolve_scene_round can actually reach.
        tick_round_for_targets([self.vampire], timing="end")

        # Health dropped by the DoT (base 5 radiant, reduced by any resistance).
        self.assertLess(self._vitals().health, health_before)

    def test_high_resistance_zeroes_damage(self) -> None:
        """Overwhelming radiant resistance (immunity-as-resistance) negates the DoT."""
        from unittest.mock import patch

        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
        )
        from world.conditions.services import apply_condition
        from world.game_clock.constants import TimePhase

        # Apply the condition directly (bypassing reconcile's apply_condition DISTINCT ON).
        # Then attach a large +radiant resistance modifier on the template.
        apply_condition(self.vampire, self.template)
        radiant = self.template.conditiondamageovertime_set.first().damage_type
        ConditionResistanceModifierFactory(
            condition=self.template, damage_type=radiant, modifier_value=1000
        )
        # Invalidate the condition handler cache so the new modifier is seen.
        self.vampire.conditions.invalidate()

        health_before = self._vitals().health
        with patch(
            "world.species.services.get_ic_phase",
            return_value=TimePhase.DAY,
        ):
            tick_round_for_targets([self.vampire], timing="end")

        # Immunity-as-resistance: 5 radiant - 1000 resistance = clamped to 0.
        self.assertEqual(self._vitals().health, health_before)

    def test_ticks_through_real_scene_round_production_path(self) -> None:
        """Sunlight Exposure ticks through the REAL non-combat production path (#1744):
        apply_condition -> ensure_round_for_acute_condition -> resolve_scene_round, with
        NO direct tick_round_for_targets(timing=...) workaround call. Proves the
        resolve_scene_round gap (which only ever fires timing="end") is genuinely closed
        for a hazard once left at the old START_OF_ROUND model default (flipped to
        END_OF_ROUND in #1762), now explicitly seeded as END_OF_ROUND.
        """
        from world.conditions.services import apply_condition
        from world.scenes.models import SceneActionDeclaration
        from world.scenes.round_services import (
            ensure_round_for_acute_condition,
            resolve_scene_round,
        )

        apply_condition(self.vampire, self.template)

        rnd = ensure_round_for_acute_condition(self.sheet)
        self.assertIsNotNone(rnd)

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
