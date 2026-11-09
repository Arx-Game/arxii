"""Journeys for a gift's substance (#5018).

Mira works a shadow gift: staff gave it a substance, the room's lighting falling, with a full
measure of 2 steps and the line "The shadows in the room deepen.". Her GIFT thread on it is
at level 10 and she holds 10 abyssal resonance. Her shadow technique costs 4 anima at
intensity 6 and control 6; outside a fight the social-scene control bonus of 10 applies.
With the default tuning (+10 power at a full measure, present at half a measure, 5 anima and
2 resonance a measure, a 50% place cap) the spec's numbers follow:

- pitch dark (-2): "+10", nothing called up;
- ordinary light (0), a social scene: one step called up, covered by her control: cost 0;
- the same in a fight: 3 anima and 1 resonance on top of the cast's own 4;
- blinding with no resonance left: no call-up and "-10", never a refusal.

Tomas stands in the room to see the room line, which never names her. Names are invented.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status

from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.checks import services as check_services
from world.checks.constants import ModifierLane
from world.checks.modifier_models import ModifierLevelBaseline
from world.combat.constants import ParticipantStatus, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.models import CombatRoundAction
from world.events.constants import EventStatus
from world.events.factories import EventFactory
from world.events.services import complete_event
from world.locations.constants import StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import felt_exposure, set_room_stat_modifier
from world.magic.constants import (
    AffinityInteractionKind,
    ResonanceValence,
    RestrictionKind,
    SubstanceDirection,
    TargetKind,
)
from world.magic.factories import (
    AffinityInteractionFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
    RestrictionFactory,
    ThreadFactory,
    ensure_canonical_affinities,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterAnima,
    CharacterResonance,
    GiftSubstance,
    Thread,
)
from world.magic.services.gain import tag_room_resonance
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

ARRIVAL = "The shadows in the room deepen."
SURROUNDINGS = "Surroundings: shadow"


def _lighting(room) -> int:
    return felt_exposure(room, stat_key=StatKey.LIGHTING)


class _ShadowField(ResonanceCacheIsolationMixin, JourneyCase):
    """Mira, a level-10 shadow caster, and Tomas, in a hall with a scene running."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        from world.magic.factories import _make_resist_corruption_check_type

        _make_resist_corruption_check_type()
        accrue = patch("world.scenes.action_services.accrue")
        accrue.start()
        self.addCleanup(accrue.stop)
        Affinity.objects.clear_cache()
        _celestial, _primal, abyssal = ensure_canonical_affinities()

        self.room = self.make_room("The Long Hall")
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.sheet = self.mira.sheet_data
        CharacterAnimaFactory(character=self.sheet, current=30, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        self.scene = SceneFactory(room=self.room)

        self.abyssal = ResonanceFactory(name="Umbral", affinity=abyssal)
        self.gift = GiftFactory(name="Shadowcraft")
        self.gift.resonances.add(self.abyssal)
        self.substance = GiftSubstance.objects.create(
            gift=self.gift,
            label="shadow",
            stat_key=StatKey.LIGHTING,
            direction=SubstanceDirection.FALLING,
            full_at=2,
            arrival_line=ARRIVAL,
        )
        ThreadFactory(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=self.gift,
            resonance=self.abyssal,
            level=100,
        )
        self.balance = CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.abyssal, balance=10, lifetime_earned=10
        )
        self.technique = make_benign_castable_technique()
        self.technique.name = "Veil of Night"
        self.technique.gift = self.gift
        self.technique.anima_cost = 4
        self.technique.intensity = 6
        self.technique.control = 6
        self.technique.save()
        grant_technique(self.sheet.primary_persona, self.technique)
        self.mira.threads.invalidate()
        self.watch(self.mira, self.tomas)

    # -- the room ---------------------------------------------------------------

    def set_lighting(self, value: int, *, room=None) -> None:
        """The builder sets the room's own lighting reading."""
        room = room or self.room
        set_room_stat_modifier(room.room_profile, StatKey.LIGHTING, source="builder", value=value)

    # -- what Mira holds ----------------------------------------------------------

    def anima(self) -> int:
        return CharacterAnima.objects.get(character=self.sheet).current

    def resonance(self) -> int:
        return CharacterResonance.objects.get(pk=self.balance.pk).balance

    # -- seams ----------------------------------------------------------------------

    def cast(self) -> dict:
        """Mira casts Veil of Night through the scene's web cast endpoint."""
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
        """The scene panel's card for Veil of Night: its ``cast_preview``."""
        response = self.api(self.account_of(self.mira)).get(
            reverse("sceneactionrequest-castable-techniques"),
            {"initiator_persona": self.sheet.primary_persona.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        (row,) = [r for r in response.json() if r["id"] == self.technique.pk]
        return row["cast_preview"]

    @staticmethod
    def surroundings_line(result: dict) -> int | None:
        for entry in result["power_ledger"]["entries"]:
            if entry["source_label"] == SURROUNDINGS:
                return entry["amount"]
        return None


class ACasterIsStrongerInTheDarkAndWeakerInTheLight(_ShadowField):
    def test_pitch_dark_gives_ten_and_calls_nothing_up(self) -> None:
        self.set_lighting(-2)

        self.assertEqual(self.card()["effective_anima_cost"], 0)
        result = self.cast()

        self.assertEqual(self.surroundings_line(result), 10)
        self.assertIsNone(result["technique_result"]["substance_call_up"])
        self.assertNotTold(self.tomas, ARRIVAL)

    def test_a_blinding_room_with_no_resonance_left_costs_power_and_never_refuses(self) -> None:
        self.set_lighting(2)
        self.balance.balance = 0
        self.balance.save(update_fields=["balance"])

        lines = {line["kind"]: line["text"] for line in self.card()["surroundings"]}
        result = self.cast()

        self.assertEqual(lines["blocked"], "Too little resonance to call up shadow")
        self.assertEqual(self.surroundings_line(result), -10)
        self.assertEqual(_lighting(self.room), 2)


class HerCastCallsUpItsSubstance(_ShadowField):
    def test_in_a_social_scene_her_control_covers_it_and_the_room_darkens(self) -> None:
        preview = self.card()
        result = self.cast()

        self.assertEqual(preview["effective_anima_cost"], 0)
        self.assertIn(
            {
                "kind": "call_up",
                "text": "Calls up shadow",
                "amount": 0,
                "anima": 0,
                "resonance": 0,
                "detail": "free, your control covers it",
            },
            preview["surroundings"],
        )
        self.assertEqual(result["technique_result"]["anima_spent"], 0)
        self.assertEqual((self.anima(), self.resonance()), (30, 10))
        self.assertEqual(self.surroundings_line(result), 5)
        self.assertEqual(_lighting(self.room), -1)
        self.assertTold(self.tomas, ARRIVAL)
        (arrival,) = [line for line in self.said(self.tomas).splitlines() if ARRIVAL in line]
        self.assertNotIn("Mira", arrival)
        # Her substance is not the place's resonance (found by real testing, #5018).
        self.assertNotTold(self.tomas, "the place's resonance swells")

    def test_leaving_the_room_takes_her_shadow_with_her(self) -> None:
        self.cast()
        self.assertEqual(self.card()["surroundings"][0]["text"], "Shadow here")

        self.mira.move_to(self.make_room("The Yard"), quiet=True)

        self.assertEqual(_lighting(self.room), 0)
        self.assertFalse(LocationValueModifier.objects.filter(source__startswith="substance:"))
        self.mira.move_to(self.room, quiet=True)
        self.assertEqual(self.card()["surroundings"][0]["text"], "Calls up shadow")

    def test_in_a_fight_it_costs_anima_and_resonance_on_top_of_the_cast(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, room=self.room)
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)

        preview = self.card()

        self.assertEqual(preview["effective_anima_cost"], 7)
        self.assertIn(
            ("Calls up shadow", "3 anima, 1 Umbral resonance"),
            [(line["text"], line["detail"]) for line in preview["surroundings"]],
        )
        # She casts as the card said: 7 anima, 1 resonance, the room dims, "+5".
        result = self.cast()
        self.assertEqual(result["technique_result"]["anima_spent"], 7)
        self.assertEqual(
            result["technique_result"]["substance_call_up"],
            {
                "label": "shadow",
                "anima": 3,
                "resonance": 1,
                "resonance_name": "Umbral",
                "blocked": "",
            },
        )
        self.assertEqual((self.anima(), self.resonance()), (23, 9))
        self.assertEqual(_lighting(self.room), -1)
        self.assertEqual(self.surroundings_line(result), 5)


class CallingUpWithNoTechnique(_ShadowField):
    def test_in_a_social_scene_it_is_free_and_the_room_sees_it(self) -> None:
        self.assertIn(
            "Your gift: shadow (free, your control covers it here)",
            self.telnet(self.mira, "callup"),
        )

        told = self.telnet(self.mira, "callup shadow")

        self.assertIn("You call up shadow. Cost: free.", told)
        self.assertEqual((self.anima(), self.resonance()), (30, 10))
        self.assertEqual(_lighting(self.room), -1)
        self.assertTold(self.tomas, ARRIVAL)
        self.assertIn(
            "Shadow is already here. Nothing to call up.", self.telnet(self.mira, "callup shadow")
        )

    def test_the_scene_panel_lists_it_and_the_web_button_calls_it_up(self) -> None:
        offers = (
            self.api(self.account_of(self.mira))
            .get(
                reverse("sceneactionrequest-call-up-offers"),
                {"initiator_persona": self.sheet.primary_persona.pk},
            )
            .json()
        )

        self.assertEqual(offers[0]["label"], "shadow")
        self.assertEqual(offers[0]["cost_line"], "free, your control covers it")
        self.assertEqual(
            offers[0]["balance_line"], "Anima: 30 · after: 30 · Umbral resonance after: unchanged"
        )
        result = self.web(self.mira, "call_up_substance", gift_id=offers[0]["gift_id"])
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You call up shadow. Cost: free.")
        self.assertEqual(_lighting(self.room), -1)

    def test_in_a_fight_it_is_once_a_round_and_not_her_action(self) -> None:
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        seat = CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)
        declared = CombatRoundActionFactory(
            participant=seat, round_number=1, focused_action=self.technique
        )

        told = self.telnet(self.mira, "callup shadow")

        self.assertIn("You call up shadow. Cost: 3 anima, 1 Umbral resonance.", told)
        self.assertEqual((self.anima(), self.resonance()), (27, 9))
        # Her declared action for the round is the one she had: still there, unchanged.
        self.assertEqual(
            list(CombatRoundAction.objects.filter(participant=seat).values_list("pk", flat=True)),
            [declared.pk],
        )
        self.assertEqual(
            CombatRoundAction.objects.get(pk=declared.pk).focused_action, self.technique
        )
        self.set_lighting(2)  # a light caster brightens the room again
        self.assertIn(
            "You have already called up your gift this round.",
            self.telnet(self.mira, "callup shadow"),
        )
        self.assertEqual(self.anima(), 27)

    def test_with_too_little_anima_in_a_lethal_fight_it_still_goes(self) -> None:
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            room=self.room,
            risk_level=RiskLevel.LETHAL,
        )
        CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)
        anima = CharacterAnima.objects.get(character=self.sheet)
        anima.current = 1
        anima.save(update_fields=["current"])

        told = self.telnet(self.mira, "callup shadow")

        self.assertIn("You call up shadow. Cost: 3 anima", told)
        self.assertEqual(self.anima(), 0)
        self.assertEqual(_lighting(self.room), -1)


class TheGMMarksItPresent(_ShadowField):
    def setUp(self) -> None:
        super().setUp()
        self.gm = self.make_player("Garrow", room=self.room)
        SceneParticipationFactory(
            scene=self.scene, account=self.account_of(self.gm), is_gm=True, is_owner=True
        )

    def test_the_gm_marks_shadow_and_the_scene_ending_clears_it(self) -> None:
        self.assertIn(
            "Shadow is now present here for this scene.",
            self.telnet(self.gm, "stage present shadow"),
        )
        self.assertEqual(_lighting(self.room), -1)
        self.assertEqual(self.card()["effective_anima_cost"], 0)
        self.assertEqual(self.card()["surroundings"][0]["text"], "Shadow here")

        self.scene.finish_scene()

        self.assertEqual(_lighting(self.room), 0)
        self.assertFalse(LocationValueModifier.objects.filter(source__startswith="scene_mark:"))

    def test_the_gm_removes_it_and_a_player_may_not_mark_it(self) -> None:
        self.web(self.gm, "stage_substance", substance="shadow", present=True)
        self.assertIn("The mark on shadow is removed.", self.telnet(self.gm, "stage absent shadow"))
        self.assertEqual(_lighting(self.room), 0)

        refused = self.web(self.tomas, "stage_substance", substance="shadow")

        self.assertIn("Only the scene's GM, owner, or staff may", refused.detail.message)
        self.assertEqual(_lighting(self.room), 0)


class WallsAndRoofsKeepTheWeatherOut(JourneyCase):
    """A moonless night with rain over a region: the street, a walled hall, a cellar.

    Kept as a unit of the felt reading (U-keep): it walks the enclosure by source table
    (weather row, the room's own row, open air, roof, walls) that no single player surface
    enumerates; the caster journeys above read the same reading through the cast card.
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


class ATechniqueThatNeedsOtherSurroundings(_ShadowField):
    """A storm technique of her gift that needs wet air, cast in a dry room."""

    def setUp(self) -> None:
        super().setUp()
        self.set_lighting(-2)
        self.needs_wet = RestrictionFactory(
            name="Needs wet air",
            kind=RestrictionKind.DESIGN,
            surroundings_stat=StatKey.WET,
            surroundings_min=1,
        )
        self.technique.restrictions.add(self.needs_wet)
        self.technique.__dict__.pop("cached_restrictions", None)
        # Staff's typical roll at her level: what the penalty is a share of.
        ModifierLevelBaseline.objects.create(lane=ModifierLane.CHECK, level=0, baseline=58)

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
        self.assertEqual(self.labels()["Surroundings: Needs wet air (here: dry)"], -58)

    def test_on_a_gift_whose_own_substance_it_names_it_does_nothing(self) -> None:
        self.substance.stat_key = StatKey.WET
        self.substance.direction = SubstanceDirection.RISING
        self.substance.save()

        self.assertNotIn("Surroundings: Needs wet air (here: dry)", self.labels())


class AuthoringShapes(JourneyCase):
    """U-keep: the validation branches staff meet in admin (the live admin pass is in the
    PR's real-testing report); no player journey reaches them."""

    def test_a_substance_must_fit_its_reading(self) -> None:
        falling_wet = GiftSubstance(
            gift=GiftFactory(),
            label="water",
            stat_key=StatKey.WET,
            direction=SubstanceDirection.FALLING,
            full_at=2,
            arrival_line="Mist gathers.",
        )
        with self.assertRaises(ValidationError) as raised:
            falling_wet.full_clean()
        self.assertIn("cannot go below ordinary", raised.exception.message_dict["direction"][0])

        too_far = GiftSubstance(
            gift=GiftFactory(),
            label="shadow",
            stat_key=StatKey.LIGHTING,
            direction=SubstanceDirection.FALLING,
            full_at=5,
            arrival_line="The shadows deepen.",
        )
        with self.assertRaises(ValidationError) as raised:
            too_far.full_clean()
        self.assertIn("only goes 2 steps", raised.exception.message_dict["full_at"][0])

    def test_a_surroundings_restriction_needs_sane_bounds(self) -> None:
        restriction = RestrictionFactory(name="Needs dark", kind=RestrictionKind.DESIGN)
        restriction.surroundings_stat = StatKey.LIGHTING
        restriction.surroundings_min = 3
        restriction.surroundings_max = 2
        with self.assertRaises(ValidationError) as raised:
            restriction.full_clean()
        self.assertEqual(
            raised.exception.message_dict["surroundings_min"], ["This reading runs from -2 to 2."]
        )
        self.assertEqual(
            raised.exception.message_dict["surroundings_max"],
            ["'At most' cannot be below 'at least'."],
        )


class TheThreadLevelScalesIt(_ShadowField):
    """A novice: her gift thread at level 1 feels a tenth of what a level-10 caster does."""

    def setUp(self) -> None:
        super().setUp()
        thread = Thread.objects.get(owner=self.sheet, target_gift=self.gift)
        thread.level = 10  # stored x10: shown level 1
        thread.save(update_fields=["level"])
        self.mira.threads.invalidate()

    def test_pitch_dark_gives_one_and_blinding_takes_one(self) -> None:
        self.set_lighting(-2)
        self.assertEqual(self.surroundings_line(self.cast()), 1)

    def test_blinding_with_no_resonance_takes_one(self) -> None:
        self.set_lighting(2)
        self.balance.balance = 0
        self.balance.save(update_fields=["balance"])
        self.assertEqual(self.surroundings_line(self.cast()), -1)


class ASecondCasterAndLeaving(_ShadowField):
    """Tomas is a shadow caster too; what Mira calls up is his to use while she stays."""

    def setUp(self) -> None:
        super().setUp()
        tomas_sheet = self.tomas.sheet_data
        CharacterAnimaFactory(character=tomas_sheet, current=30, maximum=30)
        ThreadFactory(
            owner=tomas_sheet,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=self.gift,
            resonance=self.abyssal,
            level=100,
        )
        self.tomas.threads.invalidate()

    def tomas_offer(self) -> dict:
        return (
            self.api(self.account_of(self.tomas))
            .get(
                reverse("sceneactionrequest-call-up-offers"),
                {"initiator_persona": self.tomas.sheet_data.primary_persona.pk},
            )
            .json()[0]
        )

    def test_he_finds_it_already_there_until_she_logs_out(self) -> None:
        self.cast()
        self.assertTrue(self.tomas_offer()["already_present"])

        self.mira._leave_the_grid()  # her last session leaves

        self.assertEqual(_lighting(self.room), 0)
        self.assertEqual(self.tomas_offer()["cost_line"], "free, your control covers it")


class ThePlaceMovesTheCost(_ShadowField):
    """A place of abyssal magic makes calling up shadow cheaper; a celestial one dearer."""

    def setUp(self) -> None:
        super().setUp()
        AffinityInteraction.objects.clear_cache()
        CharacterAuraFactory(
            character=self.sheet,
            celestial=Decimal("0.00"),
            primal=Decimal("0.00"),
            abyssal=Decimal("100.00"),
        )
        self.set_lighting(2)
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, room=self.room)
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)

    def place(self, affinity, valence, kind) -> None:
        resonance = ResonanceFactory(affinity=affinity)
        mod = tag_room_resonance(self.room.room_profile, resonance)
        mod.value = 200
        mod.save(update_fields=["value"])
        AffinityInteractionFactory(
            source_affinity=self.abyssal.affinity,
            environment_affinity=affinity,
            valence=valence,
            kind=kind,
            severity_multiplier=Decimal("1.00"),
        )
        AffinityInteraction.objects.clear_cache()

    def call_up_line(self) -> tuple[int, str, str]:
        preview = self.card()
        (line,) = [x for x in preview["surroundings"] if x["kind"] == "call_up"]
        return preview["effective_anima_cost"], line["text"], line["detail"]

    def test_against_the_light_with_no_place_magic(self) -> None:
        self.assertEqual(
            self.call_up_line(),
            (12, "Calls up shadow against the light", "8 anima, 3 Umbral resonance"),
        )

    def test_a_place_of_abyssal_magic_halves_it(self) -> None:
        self.place(self.abyssal.affinity, ResonanceValence.ALIGNED, AffinityInteractionKind.AMPLIFY)
        self.assertEqual(
            self.call_up_line(),
            (8, "Calls up shadow, the place makes it cheaper", "4 anima, 2 Umbral resonance"),
        )

    def test_a_place_of_celestial_magic_raises_it(self) -> None:
        celestial = Affinity.objects.get(name="Celestial")
        self.place(celestial, ResonanceValence.OPPOSED, AffinityInteractionKind.REJECT)
        self.assertEqual(
            self.call_up_line(),
            (16, "Calls up shadow, the place makes it dearer", "12 anima, 5 Umbral resonance"),
        )


class PastHerAnima(_ShadowField):
    """Never refused for anima. In a lethal fight her card shows the whole cost; a scene
    cast is never lethal, so its card and its charge both stop at what she has."""

    def setUp(self) -> None:
        super().setUp()
        self.set_lighting(2)
        anima = CharacterAnima.objects.get(character=self.sheet)
        anima.current = 5
        anima.save(update_fields=["current"])

    def test_in_a_lethal_fight_the_card_shows_twelve_and_offers_it(self) -> None:
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, room=self.room, risk_level=RiskLevel.LETHAL
        )
        CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)

        response = self.api(self.account_of(self.mira)).get(
            f"/api/actions/characters/{self.mira.pk}/available/", {"page_size": 100}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        (card,) = [
            row["cast_preview"]
            for row in response.json()["results"]
            if row.get("ref", {}).get("technique_id") == self.technique.pk
            and row.get("cast_preview")
        ]
        self.assertEqual(card["effective_anima_cost"], 12)

    def test_a_scene_cast_with_five_left_is_offered_and_charges_five(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, room=self.room)
        begin_engagement(self.mira, EngagementType.COMBAT, source=encounter)
        self.assertEqual(self.card()["effective_anima_cost"], 5)
        result = self.cast()

        self.assertEqual(result["technique_result"]["anima_spent"], 5)
        self.assertEqual(self.anima(), 0)
        self.assertEqual(_lighting(self.room), -1)


class AnEventEndingClearsTheMark(_ShadowField):
    """A scene that ends because its event completes clears the GM's mark too."""

    def test_completing_the_event_clears_the_mark(self) -> None:
        gm = self.make_player("Garrow", room=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.account_of(gm), is_gm=True)
        event = EventFactory(location=self.room.room_profile, status=EventStatus.ACTIVE)
        self.scene.event = event
        self.scene.save()
        self.telnet(gm, "stage present shadow")
        self.assertEqual(_lighting(self.room), -1)

        complete_event(event)

        self.assertEqual(_lighting(self.room), 0)


class AWaterCasterIndoors(JourneyCase):
    """A water caster in a roofed cellar: her called-up water counts under the roof."""

    def test_her_water_counts_under_a_roof(self) -> None:
        CheckSystemSetupFactory.create()
        from world.magic.factories import _make_resist_corruption_check_type

        _make_resist_corruption_check_type()
        accrue = patch("world.scenes.action_services.accrue")
        accrue.start()
        self.addCleanup(accrue.stop)
        Affinity.objects.clear_cache()
        _c, primal, _a = ensure_canonical_affinities()
        cellar = self.make_room("The Cellar")
        profile = cellar.room_profile
        profile.enclosure = RoomEnclosure.ROOFED
        profile.save()
        nerys = self.make_player("Nerys", room=cellar)
        sheet = nerys.sheet_data
        CharacterAnimaFactory(character=sheet, current=30, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        scene = SceneFactory(room=cellar)
        tide = ResonanceFactory(name="Tide", affinity=primal)
        gift = GiftFactory(name="Tidecraft")
        gift.resonances.add(tide)
        GiftSubstance.objects.create(
            gift=gift,
            label="water",
            stat_key=StatKey.WET,
            direction=SubstanceDirection.RISING,
            full_at=20,
            opposed_by=StatKey.DRY,
            arrival_line="Water beads on the walls.",
        )
        ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=gift,
            resonance=tide,
            level=100,
        )
        CharacterResonanceFactory(character_sheet=sheet, resonance=tide, balance=10)
        technique = make_benign_castable_technique()
        technique.gift = gift
        technique.anima_cost = 4
        technique.intensity = 6
        technique.control = 6
        technique.save()
        grant_technique(sheet.primary_persona, technique)
        nerys.threads.invalidate()

        response = self.api(self.account_of(nerys)).post(
            reverse("sceneactionrequest-cast"),
            {
                "scene": scene.pk,
                "initiator_persona": sheet.primary_persona.pk,
                "technique_id": technique.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        entries = response.json()["result"]["power_ledger"]["entries"]
        self.assertIn(
            ("Surroundings: water", 5), [(e["source_label"], e["amount"]) for e in entries]
        )
        self.assertEqual(felt_exposure(cellar, stat_key=StatKey.WET), 10)
