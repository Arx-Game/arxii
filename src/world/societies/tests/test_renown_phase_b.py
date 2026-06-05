"""Phase B tests for the Renown system (#676).

Covers ``fire_renown_award`` — the single entry point that bundles
Magnitude / Risk / Archetypes / Reach into one call and writes through
every renown axis.

Phase A's decay primitives + Phase B's event firing together give us the
full "renown deeds happen, fame buffer fills, reputation moves, legend
records" loop. Org-inflow and persona-outflow lands in Phase C.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.constants import (
    MAGNITUDE_FAME_AWARDS,
    MAGNITUDE_PRESTIGE_AWARDS,
    RISK_LEGEND_AWARDS,
    FameTier,
    RenownMagnitude,
    RenownReach,
    RenownRisk,
)
from world.societies.factories import SocietyFactory
from world.societies.models import LegendEntry, PhilosophicalArchetype, SocietyReputation
from world.societies.renown import fire_renown_award


def _make_primary_persona():
    """Build a Character + sheet + PRIMARY persona."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_temporary_persona(character_sheet):
    """A TEMPORARY persona on an existing sheet (can't hold reputation)."""
    return PersonaFactory(
        character_sheet=character_sheet,
        persona_type=PersonaType.TEMPORARY,
    )


def _make_archetype(**deltas) -> PhilosophicalArchetype:
    """Build an archetype with the six principle deltas (defaults to 0)."""
    fields = {
        "mercy_delta": 0,
        "method_delta": 0,
        "status_delta": 0,
        "change_delta": 0,
        "allegiance_delta": 0,
        "power_delta": 0,
    }
    fields.update(deltas)
    return PhilosophicalArchetype.objects.create(name=f"Archetype-{id(deltas)}", **fields)


class FireRenownAwardMagnitudeTests(TestCase):
    """Magnitude drives fame + prestige_from_deeds."""

    def test_no_magnitude_no_fame_or_prestige(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(persona=persona)
        self.assertEqual(result.fame_awarded, 0)
        self.assertEqual(result.prestige_awarded, 0)
        persona.refresh_from_db()
        self.assertEqual(persona.fame_points, 0)
        self.assertEqual(persona.prestige_from_deeds, 0)

    def test_moderate_magnitude_awards_fame_and_prestige(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(persona=persona, magnitude=RenownMagnitude.MODERATE)
        self.assertEqual(result.fame_awarded, MAGNITUDE_FAME_AWARDS["moderate"])
        self.assertEqual(result.prestige_awarded, MAGNITUDE_PRESTIGE_AWARDS["moderate"])
        persona.refresh_from_db()
        self.assertEqual(persona.fame_points, MAGNITUDE_FAME_AWARDS["moderate"])
        self.assertEqual(persona.prestige_from_deeds, MAGNITUDE_PRESTIGE_AWARDS["moderate"])

    def test_very_high_magnitude_pushes_to_household_name(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(persona=persona, magnitude=RenownMagnitude.VERY_HIGH)
        self.assertTrue(result.fame_tier_changed)
        persona.refresh_from_db()
        # Very High awards 12k fame, threshold for Household Name is 10k.
        self.assertEqual(persona.fame_tier, FameTier.HOUSEHOLD_NAME.value)

    def test_prestige_from_deeds_updates_total_prestige(self) -> None:
        persona = _make_primary_persona()
        fire_renown_award(persona=persona, magnitude=RenownMagnitude.HIGH)
        persona.refresh_from_db()
        # total_prestige denormalizes the four sources — only deeds has a value here.
        self.assertEqual(persona.total_prestige, MAGNITUDE_PRESTIGE_AWARDS["high"])

    def test_repeated_awards_accumulate(self) -> None:
        persona = _make_primary_persona()
        fire_renown_award(persona=persona, magnitude=RenownMagnitude.MODERATE)
        fire_renown_award(persona=persona, magnitude=RenownMagnitude.MODERATE)
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_deeds, 2 * MAGNITUDE_PRESTIGE_AWARDS["moderate"])


class FireRenownAwardRiskTests(TestCase):
    """Risk drives legend; creates a LegendEntry if Risk > NONE."""

    def test_no_risk_no_legend_entry(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(persona=persona, magnitude=RenownMagnitude.HIGH)
        self.assertEqual(result.legend_awarded, 0)
        self.assertIsNone(result.legend_entry_id)
        self.assertFalse(LegendEntry.objects.filter(persona=persona).exists())

    def test_none_risk_no_legend_entry(self) -> None:
        # Explicit NONE behaves the same as missing risk (0 legend, no entry).
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.HIGH,
            risk=RenownRisk.NONE,
        )
        self.assertEqual(result.legend_awarded, 0)
        self.assertIsNone(result.legend_entry_id)

    def test_extreme_risk_creates_legend_entry(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(persona=persona, risk=RenownRisk.EXTREME)
        self.assertEqual(result.legend_awarded, RISK_LEGEND_AWARDS["extreme"])
        self.assertIsNotNone(result.legend_entry_id)
        entry = LegendEntry.objects.get(pk=result.legend_entry_id)
        self.assertEqual(entry.persona, persona)
        self.assertEqual(entry.base_value, RISK_LEGEND_AWARDS["extreme"])


class FireRenownAwardReachTests(TestCase):
    """Reach defaults from Magnitude; override wins. Awareness is binary per Realm."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.home_realm = RealmFactory(name="Home Realm")
        cls.other_realm = RealmFactory(name="Other Realm")
        cls.continent = AreaFactory(
            name="Home Continent",
            level=AreaLevel.CONTINENT,
            realm=cls.home_realm,
        )
        cls.home_city = AreaFactory(
            name="Home City",
            level=AreaLevel.CITY,
            realm=cls.home_realm,
            parent=cls.continent,
        )
        cls.home_society = SocietyFactory(name="Home Society", realm=cls.home_realm)
        cls.other_society = SocietyFactory(name="Other Society", realm=cls.other_realm)
        cls.archetype = PhilosophicalArchetype.objects.create(
            name="TestHeroic", mercy_delta=1, method_delta=1
        )

    def test_local_reach_only_home_realm_aware(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.SMALL,
            archetypes=[self.archetype],
            origin_area=self.home_city,
        )
        # Small magnitude defaults to LOCAL reach → only home realm hears.
        self.assertIn(self.home_society.pk, result.aware_society_ids)
        self.assertNotIn(self.other_society.pk, result.aware_society_ids)

    def test_world_reach_every_realm_aware(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.VERY_HIGH,
            archetypes=[self.archetype],
            origin_area=self.home_city,
        )
        # Very High defaults to WORLD reach → all realms hear.
        self.assertIn(self.home_society.pk, result.aware_society_ids)
        self.assertIn(self.other_society.pk, result.aware_society_ids)

    def test_explicit_reach_override_wins_over_magnitude_default(self) -> None:
        persona = _make_primary_persona()
        # Small magnitude (LOCAL default) + explicit WORLD reach → everyone hears.
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.SMALL,
            archetypes=[self.archetype],
            origin_area=self.home_city,
            reach=RenownReach.WORLD,
        )
        self.assertIn(self.other_society.pk, result.aware_society_ids)

    def test_no_origin_area_with_non_world_reach_no_awareness(self) -> None:
        persona = _make_primary_persona()
        # No origin → can't resolve home realm → LOCAL reach finds nothing.
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.MODERATE,
            archetypes=[self.archetype],
        )
        self.assertEqual(result.aware_society_ids, ())

    def test_no_origin_area_with_world_reach_all_societies_aware(self) -> None:
        persona = _make_primary_persona()
        # WORLD reach doesn't need origin — everyone hears regardless.
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.VERY_HIGH,
            archetypes=[self.archetype],
        )
        self.assertIn(self.home_society.pk, result.aware_society_ids)
        self.assertIn(self.other_society.pk, result.aware_society_ids)


class FireRenownAwardArchetypeTests(TestCase):
    """Archetype dot product produces SocietyReputation deltas."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Archetype Test Realm")
        # Two societies with opposite principle values to exercise positive
        # and negative deltas on the same event.
        cls.honorable_society = SocietyFactory(
            name="Honor",
            realm=cls.realm,
            mercy=2,
            method=3,  # Honor (positive method)
            status=0,
            change=0,
            allegiance=0,
            power=0,
        )
        cls.cunning_society = SocietyFactory(
            name="Cunning",
            realm=cls.realm,
            mercy=-2,
            method=-3,  # Cunning (negative method)
            status=0,
            change=0,
            allegiance=0,
            power=0,
        )

    def test_no_archetypes_no_reputation_change(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.HIGH,
            origin_area=None,
            reach=RenownReach.WORLD,
        )
        self.assertEqual(result.reputation_deltas, {})

    def test_heroic_archetype_helps_honor_hurts_cunning(self) -> None:
        # Heroic = +mercy +method.
        heroic = _make_archetype(mercy_delta=2, method_delta=2)
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            archetypes=[heroic],
            reach=RenownReach.WORLD,
        )
        # Honor society: (2 * 2) + (2 * 3) = 10 → positive rep.
        # Cunning society: (2 * -2) + (2 * -3) = -10 → negative rep.
        self.assertEqual(result.reputation_deltas[self.honorable_society.pk], 10)
        self.assertEqual(result.reputation_deltas[self.cunning_society.pk], -10)
        # SocietyReputation rows reflect the writes.
        rep_honor = SocietyReputation.objects.get(persona=persona, society=self.honorable_society)
        self.assertEqual(rep_honor.value, 10)
        rep_cunning = SocietyReputation.objects.get(persona=persona, society=self.cunning_society)
        self.assertEqual(rep_cunning.value, -10)

    def test_multiple_archetypes_sum_vectors(self) -> None:
        # Two archetypes combined: heroic + reformist (positive change).
        heroic = _make_archetype(mercy_delta=2, method_delta=1)
        reformist = _make_archetype(mercy_delta=0, method_delta=1, change_delta=1)
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            archetypes=[heroic, reformist],
            reach=RenownReach.WORLD,
        )
        # Honor society: mercy (2+0)*2 + method (1+1)*3 + change (0+1)*0 = 4 + 6 = 10.
        self.assertEqual(result.reputation_deltas[self.honorable_society.pk], 10)

    def test_society_override_replaces_computed_delta(self) -> None:
        # Even with a heroic event, override forces a specific value for one society.
        heroic = _make_archetype(mercy_delta=2, method_delta=2)
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            archetypes=[heroic],
            reach=RenownReach.WORLD,
            society_overrides={self.honorable_society: -50},
        )
        self.assertEqual(result.reputation_deltas[self.honorable_society.pk], -50)

    def test_temporary_persona_skips_reputation(self) -> None:
        primary = _make_primary_persona()
        temp = _make_temporary_persona(primary.character_sheet)
        heroic = _make_archetype(mercy_delta=2, method_delta=2)
        result = fire_renown_award(
            persona=temp,
            archetypes=[heroic],
            reach=RenownReach.WORLD,
        )
        # Reputation deltas are gated on is_established_or_primary.
        self.assertEqual(result.reputation_deltas, {})
        self.assertFalse(SocietyReputation.objects.filter(persona=temp).exists())

    def test_temporary_persona_still_earns_fame_and_legend(self) -> None:
        # Temporary personas can still accumulate fame + legend for themselves,
        # they just can't hold reputation per the existing system rule.
        primary = _make_primary_persona()
        temp = _make_temporary_persona(primary.character_sheet)
        result = fire_renown_award(
            persona=temp,
            magnitude=RenownMagnitude.MODERATE,
            risk=RenownRisk.HIGH,
        )
        self.assertEqual(result.fame_awarded, MAGNITUDE_FAME_AWARDS["moderate"])
        self.assertEqual(result.legend_awarded, RISK_LEGEND_AWARDS["high"])
        temp.refresh_from_db()
        self.assertEqual(temp.fame_points, MAGNITUDE_FAME_AWARDS["moderate"])


class FireRenownAwardBundleTests(TestCase):
    """End-to-end smoke: a full bundle writes through every axis."""

    def test_full_bundle_writes_all_axes(self) -> None:
        realm = RealmFactory(name="Bundle Realm")
        society = SocietyFactory(name="Bundle Society", realm=realm, mercy=2, method=2)
        area = AreaFactory(name="Bundle City", level=AreaLevel.CITY, realm=realm)
        archetype = PhilosophicalArchetype.objects.create(
            name="BundleHeroic", mercy_delta=1, method_delta=1
        )
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.HIGH,
            risk=RenownRisk.MODERATE,
            archetypes=[archetype],
            origin_area=area,
        )
        # Persona-side axes all moved.
        self.assertGreater(result.fame_awarded, 0)
        self.assertGreater(result.prestige_awarded, 0)
        self.assertGreater(result.legend_awarded, 0)
        self.assertIsNotNone(result.legend_entry_id)
        self.assertIn(society.pk, result.aware_society_ids)
        self.assertEqual(result.reputation_deltas[society.pk], 4)  # (1*2)+(1*2)
        # LegendEntry has societies_aware populated.
        entry = LegendEntry.objects.get(pk=result.legend_entry_id)
        self.assertIn(society, entry.societies_aware.all())


class FireRenownAwardClampsTests(TestCase):
    """Reputation value is clamped to [-1000, +1000] (existing system rule)."""

    def test_reputation_clamps_at_negative_thousand(self) -> None:
        realm = RealmFactory(name="Clamp Realm")
        # Big negative society principles to drive a strong negative delta.
        society = SocietyFactory(
            name="Clamp Hostile",
            realm=realm,
            mercy=-5,
            method=-5,
            status=-5,
            change=-5,
            allegiance=-5,
            power=-5,
        )
        archetype = PhilosophicalArchetype.objects.create(
            name="ClampHeroic",
            mercy_delta=5,
            method_delta=5,
            status_delta=5,
            change_delta=5,
            allegiance_delta=5,
            power_delta=5,
        )
        persona = _make_primary_persona()
        # Pre-seed at -990 to test clamping near the floor.
        SocietyReputation.objects.create(persona=persona, society=society, value=-990)
        fire_renown_award(
            persona=persona,
            archetypes=[archetype],
            reach=RenownReach.WORLD,
        )
        # Dot product = 5*-5 * 6 = -150. -990 + -150 = -1140, clamped to -1000.
        rep = SocietyReputation.objects.get(persona=persona, society=society)
        self.assertEqual(rep.value, -1000)


class RenownAwardResultShapeTests(TestCase):
    """The return dataclass captures everything callers need."""

    def test_result_carries_persona_id_and_all_deltas(self) -> None:
        persona = _make_primary_persona()
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.MODERATE,
            risk=RenownRisk.LOW,
        )
        self.assertEqual(result.persona_id, persona.pk)
        self.assertGreater(result.fame_awarded, 0)
        self.assertGreater(result.prestige_awarded, 0)
        self.assertGreater(result.legend_awarded, 0)
        self.assertIsNotNone(result.legend_entry_id)
