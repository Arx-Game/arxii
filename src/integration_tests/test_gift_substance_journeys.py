"""Journeys for a gift's substance and the Primum it draws on (#5018, #5125).

Mira works a fire gift: staff gave it the substance fire, which grows with rising heat. Her
GIFT thread on it is at level 100 (rung 10, full strength), and her technique costs 4 anima
at intensity 6 and control 6; outside a fight the social-scene control bonus applies. The
tuning is the starter rows (``seed_primum_tuning``): Trace from 1 Primum (2 points), Some from
10 (4), Rich from 30 (7), Massive from 100 (10); the power curve gives 2 at 2 points, 4 at 4,
6 at 7, 8 at 10, 10 at 15, 11 at 20; a call-up costs 3 anima, related substances count half.

Tomas stands in the room to see the room line. Names are invented.
"""

from __future__ import annotations

from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.checks import services as check_services
from world.classes.factories import CharacterClassLevelFactory
from world.combat.factories import CombatEncounterFactory
from world.events.constants import EventStatus
from world.events.factories import EventFactory
from world.events.services import complete_event
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemSubstanceFactory
from world.locations.constants import StatKey
from world.locations.services import (
    felt_exposure,
    felt_reading,
    felt_readings,
    set_room_stat_modifier,
)
from world.magic.constants import (
    RestrictionKind,
    SubstanceDirection,
    SubstanceRelationKind,
    TargetKind,
)
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    GiftFactory,
    PlacePrimumFactory,
    PrimumSightingFactory,
    ResonanceFactory,
    RestrictionFactory,
    SubstanceFactory,
    SubstanceRelationFactory,
    ThreadFactory,
    ensure_canonical_affinities,
    seed_primum_tuning,
)
from world.magic.models import (
    Affinity,
    CharacterAnima,
    CharacterResonance,
    PrimumCallUp,
    PrimumStep,
    SubstancePowerStep,
    Thread,
)
from world.magic.services.primum import power_for_points
from world.magic.services.resonance_environment import get_resonance_environment_config
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.tests.cast_test_helpers import grant_technique, make_benign_castable_technique
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals
from world.weather.factories import WeatherTypeExposureFactory, WeatherTypeFactory
from world.weather.services import roll_region_weather

MANIFEST = "Mira begins to manifest fire in the area."


def _lighting(room) -> int:
    return felt_exposure(room, stat_key=StatKey.LIGHTING)


class _FireField(ResonanceCacheIsolationMixin, JourneyCase):
    """Mira, a level-100 fire caster, and Tomas, in a hall with a scene running."""

    SUBSTANCE = "fire"
    STAT = StatKey.HEAT

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        from world.magic.factories import _make_resist_corruption_check_type

        _make_resist_corruption_check_type()
        accrue = patch("world.scenes.action_services.accrue")
        accrue.start()
        self.addCleanup(accrue.stop)
        Affinity.objects.clear_cache()
        _celestial, primal, _abyssal = ensure_canonical_affinities()
        seed_primum_tuning()

        self.room = self.make_room("The Long Hall")
        self.profile = self.room.room_profile
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.sheet = self.mira.sheet_data
        CharacterAnimaFactory(character=self.sheet, current=30, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        self.scene = SceneFactory(room=self.room)

        self.ember = ResonanceFactory(name="Ember", affinity=primal)
        self.substance = SubstanceFactory(
            name=self.SUBSTANCE, stat_key=self.STAT, direction=SubstanceDirection.RISING
        )
        self.gift = GiftFactory(name="Pyrecraft", substance=self.substance)
        self.gift.resonances.add(self.ember)
        ThreadFactory(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=self.gift,
            resonance=self.ember,
            level=100,
        )
        self.balance = CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.ember, balance=10, lifetime_earned=10
        )
        self.technique = make_benign_castable_technique()
        self.technique.name = "Kindle"
        self.technique.gift = self.gift
        self.technique.anima_cost = 4
        self.technique.intensity = 6
        self.technique.control = 6
        self.technique.save()
        grant_technique(self.sheet.primary_persona, self.technique)
        self.mira.threads.invalidate()
        self.watch(self.mira, self.tomas)

    # -- the place ---------------------------------------------------------------

    def stock(self, substance, amount: int) -> None:
        """A lair's Primum of ``substance`` in the hall."""
        PlacePrimumFactory(
            room_profile=self.profile,
            substance=substance,
            capacity=max(amount, 1),
            stored_amount=amount,
        )

    def anima(self) -> int:
        return CharacterAnima.objects.get(character=self.sheet).current

    def resonance(self) -> int:
        return CharacterResonance.objects.get(pk=self.balance.pk).balance

    def called_up(self) -> list[int]:
        return list(
            PrimumCallUp.objects.filter(caster=self.sheet).values_list("amount_added", flat=True)
        )

    # -- seams ----------------------------------------------------------------------

    def cast(self) -> dict:
        """Mira casts Kindle through the scene's web cast endpoint."""
        response = self.api(self.account_of(self.mira)).post(
            reverse("sceneactionrequest-cast"),
            {
                "scene": self.scene.pk,
                "initiator_persona": self.sheet.primary_persona.pk,
                "technique_id": self.technique.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        return response.json()["result"]

    def card(self) -> dict:
        """The scene panel's card for Kindle: its ``cast_preview``."""
        response = self.api(self.account_of(self.mira)).get(
            reverse("sceneactionrequest-castable-techniques"),
            {"initiator_persona": self.sheet.primary_persona.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        (row,) = [r for r in response.json() if r["id"] == self.technique.pk]
        return row["cast_preview"]

    def card_rows(self) -> list[tuple[str, str, int]]:
        return [
            (line["kind"], line["text"], line["amount"]) for line in self.card()["surroundings"]
        ]

    def offers(self) -> list[dict]:
        return (
            self.api(self.account_of(self.mira))
            .get(
                reverse("sceneactionrequest-call-up-offers"),
                {"initiator_persona": self.sheet.primary_persona.pk},
            )
            .json()
        )

    @staticmethod
    def primum_lines(result: dict) -> dict[str, int]:
        """The cast's ENVIRONMENT ledger lines from Primum, by label."""
        return {
            entry["source_label"]: entry["amount"]
            for entry in result["power_ledger"]["entries"]
            if entry["source_label"] != "resonance environment" and entry["stage"] == "environment"
        }


class TheBonusGrowsWithThePrimumHere(_FireField):
    def test_fire_mage_in_a_forge_gets_trace_benefit(self) -> None:
        set_room_stat_modifier(self.profile, StatKey.HEAT, source="builder", value=5)

        result = self.cast()

        self.assertEqual(self.primum_lines(result), {"Surroundings: fire": 2})
        self.assertIsNone(result["technique_result"]["substance_call_up"])
        self.assertEqual(self.called_up(), [])

    def test_enchanted_lair_gives_a_large_bonus(self) -> None:
        self.stock(self.substance, 100)  # Massive

        lines = self.primum_lines(self.cast())

        self.assertEqual(lines, {"Surroundings: fire": power_for_points(10)})
        self.assertEqual(lines["Surroundings: fire"], 8)
        self.assertGreater(lines["Surroundings: fire"], 2)

    def test_two_sources_taper_and_cap(self) -> None:
        self.stock(self.substance, 10)  # Some: 4 points
        some = PrimumStep.objects.get(rank=2)
        held = ItemSubstanceFactory(
            item_instance=ItemInstanceFactory(custom_name="Ash brand"),
            substance=self.substance,
            step=some,
        )
        EquippedItemFactory(
            character=self.sheet,
            item_instance=held.item_instance,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.OVER,
        )

        lines = self.primum_lines(self.cast())

        # 8 points reach 6 on the curve, less than twice the 4 that one source gives.
        self.assertEqual(lines, {"Surroundings: fire": 3, "Ash brand (fire)": 3})
        self.assertEqual(sum(lines.values()), power_for_points(8))

        massive = PrimumStep.objects.get(rank=4)
        held.step = massive
        held.save(update_fields=["step"])
        PrimumCallUp.objects.create(
            room_profile=self.profile, substance=self.substance, caster=self.sheet, amount_added=90
        )
        config = get_resonance_environment_config()
        config.substance_power_cap = 9
        config.save(update_fields=["substance_power_cap"])

        lines = self.primum_lines(self.cast())

        self.assertEqual(sum(lines.values()), 9, lines)


class _IceField(_FireField):
    """Mira works ice instead; a lair of fire works against her."""

    SUBSTANCE = "ice"
    STAT = StatKey.COLD

    def setUp(self) -> None:
        super().setUp()
        self.fire = SubstanceFactory(
            name="fire", stat_key=StatKey.HEAT, direction=SubstanceDirection.RISING
        )
        SubstanceRelationFactory(
            substance_a=self.substance, substance_b=self.fire, kind=SubstanceRelationKind.OPPOSED
        )


class AnOpposedSubstanceWorksAgainstHer(_IceField):
    def test_ice_mage_hindered_and_unrelated_unchanged(self) -> None:
        self.stock(self.fire, 10)  # Some fire: 4 points against her
        self.stock(SubstanceFactory(name="stone"), 100)  # unrelated: nothing

        lines = self.primum_lines(self.cast())

        # Her cast called ice up to Trace (+2); the fire takes 4 away; together -2.
        self.assertEqual(
            lines, {"Surroundings: ice": 2, "Something here works against your ice": -4}
        )

        PrimumCallUp.objects.filter(caster=self.sheet).delete()
        self.profile.primum.filter(substance=self.fire).delete()
        steam = SubstanceFactory(name="steam")
        SubstanceRelationFactory(
            substance_a=self.substance, substance_b=steam, kind=SubstanceRelationKind.RELATED
        )
        self.stock(steam, 10)  # Some steam: half of 4 points

        lines = self.primum_lines(self.cast())

        # Steam is not hers and she has not sensed it, so it is never named.
        self.assertEqual(lines["Something here strengthens your ice"], 2)
        self.assertFalse(any("steam" in label for label in lines))
        self.assertEqual(
            self.card_rows(),
            [
                ("heading", "Ice around you", 0),
                ("source", "The Long Hall · Trace", 2),
                ("source", "Something here strengthens your ice", 2),
                ("power", "Around you adds", 4),
            ],
        )

        PrimumSightingFactory(
            character_sheet=self.sheet, room_profile=self.profile, substance=steam
        )

        self.assertEqual(
            self.card_rows(),
            [
                ("heading", "Ice around you", 0),
                ("source", "The Long Hall · Trace", 2),
                ("source", "The Long Hall · Some steam, related to ice", 2),
                ("power", "Around you adds", 4),
            ],
        )
        self.assertEqual([offer["label"] for offer in self.offers()], ["ice"])
        refused = self.telnet(self.mira, "callup steam")
        self.assertIn("Which gift's substance?", refused)

    def test_unperceived_opposed_substance_is_never_named(self) -> None:
        self.stock(self.fire, 30)  # Rich fire

        texts = [line["text"] for line in self.card()["surroundings"]]
        lines = self.primum_lines(self.cast())

        self.assertIn("Something here works against your ice", texts)
        self.assertIn("Something here works against your ice", lines)
        self.assertFalse(any("fire" in text.lower() for text in [*texts, *lines]))

        PrimumSightingFactory(
            character_sheet=self.sheet, room_profile=self.profile, substance=self.fire
        )

        texts = [line["text"] for line in self.card()["surroundings"]]
        self.assertIn("Ice around you", texts)
        self.assertTrue(any(text.endswith("Rich fire, opposed to ice") for text in texts), texts)
        self.assertIn("Around you adds", texts)


class CallingUp(_FireField):
    def test_call_up_raises_one_step_for_one_anima_amount_no_resonance(self) -> None:
        told = self.telnet(self.mira, "callup fire")

        self.assertIn("You call up fire. Cost: free.", told)
        self.assertEqual(self.called_up(), [1])  # nothing to Trace
        self.assertTold(self.tomas, MANIFEST)

        seen_by_telnet = self.said(self.tomas).count(MANIFEST)
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, room=self.room)
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)
        result = self.web(self.mira, "call_up_substance", gift_id=self.gift.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You call up fire. Cost: 3 anima.")
        self.assertGreater(self.said(self.tomas).count(MANIFEST), seen_by_telnet)
        self.assertEqual(self.called_up(), [10])  # Trace to Some
        self.assertEqual((self.anima(), self.resonance()), (27, 10))

        self.web(self.mira, "call_up_substance", gift_id=self.gift.pk)  # Rich
        self.web(self.mira, "call_up_substance", gift_id=self.gift.pk)  # Massive
        self.assertEqual(self.called_up(), [100])
        at_top = self.web(self.mira, "call_up_substance", gift_id=self.gift.pk)
        self.assertEqual(at_top.detail.message, "No more fire can be called up here.")
        self.assertEqual(self.called_up(), [100])
        self.assertEqual(self.resonance(), 10)

    def test_call_up_in_a_room_that_already_leans_lands_on_the_next_step_start(self) -> None:
        set_room_stat_modifier(self.profile, StatKey.HEAT, source="builder", value=5)

        told = self.telnet(self.mira, "callup fire")

        self.assertIn("You call up fire.", told)
        some = PrimumStep.objects.get(rank=2)
        # Held Primum, not the lean's Trace floor, is what the step is measured from.
        self.assertEqual(self.called_up(), [some.starts_at])

    def test_cast_calls_up_only_to_trace(self) -> None:
        result = self.cast()

        self.assertEqual(
            result["technique_result"]["substance_call_up"],
            {"label": "fire", "anima": 0, "blocked": ""},
        )
        self.assertEqual(self.primum_lines(result), {"Surroundings: fire": 2})
        self.assertEqual(self.called_up(), [1])
        self.assertTold(self.tomas, MANIFEST)

        again = self.cast()

        self.assertIsNone(again["technique_result"]["substance_call_up"])
        self.assertEqual(self.called_up(), [1])

        self.mira.move_to(self.make_room("The Yard"), quiet=True)
        self.assertEqual(self.called_up(), [])

    def test_a_cast_past_anima_is_never_refused(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, room=self.room)
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)
        anima = CharacterAnima.objects.get(character=self.sheet)
        anima.current = 1
        anima.save(update_fields=["current"])

        self.assertGreater(self.card()["effective_anima_cost"], 0)
        result = self.cast()

        self.assertEqual(result["technique_result"]["anima_spent"], 1)
        self.assertEqual(self.anima(), 0)
        self.assertEqual(self.called_up(), [1])


class TheGMMarksItPresent(_FireField):
    def setUp(self) -> None:
        super().setUp()
        self.gm = self.make_player("Garrow", room=self.room)
        SceneParticipationFactory(
            scene=self.scene, account=self.account_of(self.gm), is_gm=True, is_owner=True
        )

    def scene_marks(self) -> list[int]:
        return list(
            PrimumCallUp.objects.filter(scene=self.scene).values_list("amount_added", flat=True)
        )

    def test_gm_mark_raises_place_to_trace_until_scene_ends(self) -> None:
        self.assertIn(
            "Fire is now present here for this scene.",
            self.telnet(self.gm, "stage present fire"),
        )
        self.assertEqual(self.scene_marks(), [1])
        card = self.card()
        self.assertEqual(
            [(line["kind"], line["text"], line["amount"]) for line in card["surroundings"]],
            [
                ("heading", "Fire around you", 0),
                ("source", "The Long Hall · Trace", 2),
                ("power", "Fire adds", 2),
            ],
        )

        self.scene.finish_scene()

        self.assertEqual(self.scene_marks(), [])

    def test_the_gm_removes_it_and_a_player_may_not_mark_it(self) -> None:
        self.web(self.gm, "stage_substance", substance="fire", present=True)
        self.assertIn("The mark on fire is removed.", self.telnet(self.gm, "stage absent fire"))
        self.assertEqual(self.scene_marks(), [])

        refused = self.web(self.tomas, "stage_substance", substance="fire")

        self.assertIn("Only the scene's GM, owner, or staff may", refused.detail.message)
        self.assertEqual(self.scene_marks(), [])

    def test_completing_the_event_clears_the_mark(self) -> None:
        event = EventFactory(location=self.profile, status=EventStatus.ACTIVE)
        self.scene.event = event
        self.scene.save()
        self.telnet(self.gm, "stage present fire")
        self.assertEqual(self.scene_marks(), [1])

        complete_event(event)

        self.assertEqual(self.scene_marks(), [])


class NothingToReadAddsNoLine(_FireField):
    def test_cast_with_no_tuning_rows_adds_no_line(self) -> None:
        self.stock(self.substance, 100)
        PrimumStep.objects.all().delete()
        SubstancePowerStep.objects.all().delete()

        self.assertEqual(self.card()["surroundings"], [])
        result = self.cast()

        self.assertEqual(self.primum_lines(result), {})
        self.assertIsNone(result["technique_result"]["substance_call_up"])
        self.assertEqual(self.called_up(), [])

    def test_no_thread_or_no_substance_gift_gets_no_line(self) -> None:
        self.stock(self.substance, 100)
        self.gift.substance = None
        self.gift.save(update_fields=["substance"])

        self.assertEqual(self.primum_lines(self.cast()), {})

        self.gift.substance = self.substance
        self.gift.save(update_fields=["substance"])
        thread = Thread.objects.get(owner=self.sheet, target_gift=self.gift)
        thread.retired_at = timezone.now()
        thread.save(update_fields=["retired_at"])
        self.mira.threads.invalidate()

        self.assertEqual(self.primum_lines(self.cast()), {})
        self.assertEqual(self.called_up(), [])


class WallsAndRoofsKeepTheWeatherOut(JourneyCase):
    """A moonless night with rain over a region: the street, a walled hall, a cellar.

    Kept as a unit of the felt reading (U-keep): it walks the enclosure by source table
    (weather row, the room's own row, open air, roof, walls) that no single player surface
    enumerates.
    """

    def setUp(self) -> None:
        super().setUp()
        self.region = AreaFactory(level=AreaLevel.BARONY)
        night = WeatherTypeFactory(name="Moonless Rain")
        WeatherTypeExposureFactory(weather_type=night, stat_key=StatKey.LIGHTING, value=-2)
        WeatherTypeExposureFactory(weather_type=night, stat_key=StatKey.WET, value=40)
        self.street = self.room_in("The Street", RoomEnclosure.OPEN_AIR)
        self.hall = self.room_in("The Hall", RoomEnclosure.WALLED)
        self.cellar = self.room_in("The Cellar", RoomEnclosure.ROOFED)
        roll_region_weather(self.region, weather_type=night)

    def room_in(self, name: str, enclosure: str):
        ward = AreaFactory(level=AreaLevel.WARD, parent=self.region, name=f"{name} Ward")
        profile = RoomProfileFactory(area=ward, enclosure=enclosure)
        room = profile.objectdb
        room.db_key = name
        room.save()
        return room

    def test_the_night_stops_at_walls_but_the_rooms_own_darkness_counts(self) -> None:
        self.assertEqual(_lighting(self.street), -2)
        self.assertEqual(_lighting(self.hall), 0)
        set_room_stat_modifier(self.hall.room_profile, StatKey.LIGHTING, source="builder", value=-2)
        self.assertEqual(_lighting(self.hall), -2)

    def test_a_roof_keeps_out_the_rain_but_not_the_cellars_own_water(self) -> None:
        self.assertEqual(felt_exposure(self.street, stat_key=StatKey.WET), 40)
        self.assertEqual(felt_exposure(self.cellar, stat_key=StatKey.WET), 0)
        set_room_stat_modifier(self.cellar.room_profile, StatKey.WET, source="builder", value=30)
        self.assertEqual(felt_exposure(self.cellar, stat_key=StatKey.WET), 30)
        self.assertEqual(_lighting(self.cellar), -2)  # a roof alone lets the night in
        # The many-axis read a room's substances use gives what one-axis reads give.
        axes = [StatKey.WET, StatKey.LIGHTING, StatKey.HEAT]
        for room in (self.street, self.hall, self.cellar):
            self.assertEqual(
                felt_readings(room, axes), {key: felt_reading(room, stat_key=key) for key in axes}
            )


class ATechniqueThatNeedsOtherSurroundings(_FireField):
    """A storm technique of her gift that needs wet air, cast in a dry room."""

    def setUp(self) -> None:
        super().setUp()
        self.needs_wet = RestrictionFactory(
            name="Needs wet air",
            kind=RestrictionKind.DESIGN,
            surroundings_stat=StatKey.WET,
            surroundings_min=1,
        )
        self.technique.restrictions.add(self.needs_wet)
        self.technique.__dict__.pop("cached_restrictions", None)
        # The penalty is a share of a typical roll at her character level, so she holds one:
        # level 10 is baseline 18 + 8 x 9 = 90, and this database seeds no level tiers.
        CharacterClassLevelFactory(character=self.sheet, level=10, is_primary=True)
        self.sheet.invalidate_class_level_cache()

    def labels(self) -> dict[str, int]:
        real = check_services.collect_check_modifiers
        seen = []

        def spy(*args, **kwargs):
            breakdown = real(*args, **kwargs)
            seen.append(breakdown)
            return breakdown

        with patch.object(check_services, "collect_check_modifiers", side_effect=spy):
            self.cast()
        self.assertTrue(seen, "the cast gathered its roll modifiers")
        return {c.source_label: c.value for b in seen for c in b.contributions}

    def test_unmet_it_is_a_heavy_named_penalty_never_a_refusal(self) -> None:
        lines = [line["text"] for line in self.card()["surroundings"]]

        self.assertIn("Needs wet air: very heavy penalty here", lines)
        self.assertEqual(self.labels()["Surroundings: Needs wet air (here: dry)"], -90)

    def test_on_a_gift_whose_own_substance_it_names_it_does_nothing(self) -> None:
        self.substance.stat_key = StatKey.WET
        self.substance.direction = SubstanceDirection.RISING
        self.substance.save()

        self.assertNotIn("Surroundings: Needs wet air (here: dry)", self.labels())


class SurroundingsRestrictionShape(JourneyCase):
    """U-keep: the validation branch staff meet in admin; no player journey reaches it."""

    def test_a_surroundings_restriction_needs_sane_bounds(self) -> None:
        from django.core.exceptions import ValidationError

        restriction = RestrictionFactory(name="Needs dark", kind=RestrictionKind.DESIGN)
        restriction.surroundings_stat = StatKey.LIGHTING
        restriction.surroundings_min = 3
        restriction.surroundings_max = 2
        with self.assertRaises(ValidationError) as raised:
            restriction.full_clean()
        self.assertEqual(
            raised.exception.message_dict["surroundings_min"],
            ["This room condition runs from -2 to 2."],
        )
        self.assertEqual(
            raised.exception.message_dict["surroundings_max"],
            ["'At most' cannot be below 'at least'."],
        )
