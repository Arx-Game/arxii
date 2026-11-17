"""Journeys for what the room frame, ``look`` and the fight panel say about Primum (#5125).

The Ashmouth Caldera is a lair holding Massive fire Primum (100) and a Trace of earth (1).
Mira works a fire gift, so she always senses the fire. Tomas works no gift: he senses nothing
until a sighting (a Magesight check) names the fire, and he never names the earth. The steps
are the starter ones (Trace from 1, Some from 10, Rich from 30, Massive from 100). Names are
invented.
"""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

from django.db import connection
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import CharacterFactory
from flows.service_functions.serializers.room_state import build_room_state_payload
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CreatureTemplateFactory,
)
from world.items.factories import ItemTemplateFactory, QualityTierFactory
from world.locations.constants import StatKey
from world.magic.constants import SubstanceDirection
from world.magic.factories import (
    CharacterGiftFactory,
    CreaturePrimumFactory,
    GiftFactory,
    HarvestOutcomeFactory,
    PlacePrimumFactory,
    PrimumSightingFactory,
    SubstanceFactory,
    ensure_canonical_affinities,
    seed_primum_tuning,
)
from world.magic.models import Affinity
from world.magic.services.resonance_environment import get_resonance_environment_config
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.skills.factories import MagicSkillFactory
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory

NO_PRIMUM = {"sensed": [], "line": "", "harvestable": []}
FIRE_LINE = "You sense fire Primum: Massive."


class _Caldera(ResonanceCacheIsolationMixin, JourneyCase):
    """The caldera, Mira (a fire gift), Tomas (no gift) and Odo (no gift, no sighting)."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        Affinity.objects.clear_cache()
        ensure_canonical_affinities()
        seed_primum_tuning()

        self.room = self.make_room("The Ashmouth Caldera")
        self.profile = self.room.room_profile
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.odo = self.make_player("Odo", room=self.room)
        self.fire = SubstanceFactory(
            name="fire", stat_key=StatKey.HEAT, direction=SubstanceDirection.RISING
        )
        self.earth = SubstanceFactory(name="earth")
        CharacterGiftFactory(
            character=self.mira.sheet_data, gift=GiftFactory(name="Pyromancy", substance=self.fire)
        )
        self.lair(self.fire, 100)
        self.lair(self.earth, 1)
        self.watch(self.mira, self.tomas, self.odo)

    def lair(self, substance, amount: int):
        return PlacePrimumFactory(
            room_profile=self.profile, substance=substance, capacity=amount, stored_amount=amount
        )

    def sense(self, who, substance=None) -> None:
        """A Magesight check names ``substance`` (fire by default) to ``who`` here."""
        PrimumSightingFactory(
            character_sheet=who.sheet_data,
            room_profile=self.profile,
            substance=substance or self.fire,
        )

    def frame(self, who) -> dict:
        """The ``primum`` block of the room frame ``who`` is sent, as the game builds it."""
        payload = build_room_state_payload(who.scene_state, self.room.scene_state)
        return payload["primum"]

    def slain_elemental(self, carries: int = 100):
        """A slain elemental in the caldera, a kind that carries ``carries`` fire Primum."""
        template = CreatureTemplateFactory(name="Cinder elemental")
        CreaturePrimumFactory(creature_template=template, substance=self.fire, amount=carries)
        return CombatOpponentFactory(
            encounter=CombatEncounterFactory(room=self.room),
            creature_template=template,
            name="elemental",
            status=OpponentStatus.DEFEATED,
        )

    def opponents_seen_by(self, who, encounter) -> dict[str, bool]:
        """Opponent name to whether it carries harvest offers, as ``who`` reads over REST."""
        return {name: bool(offers) for name, offers in self.offers_seen_by(who, encounter).items()}

    def offers_seen_by(self, who, encounter) -> dict[str, list[dict]]:
        """Opponent name to its ``harvest_offers`` in the encounter ``who`` reads over REST."""
        response = self.api(self.account_of(who)).get(f"/api/combat/{encounter.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return {row["name"]: row["harvest_offers"] for row in response.json()["opponents"]}


class TheRoomFrame(_Caldera):
    def test_room_frame_carries_the_sense_line_and_offers_only_where_perceived(self) -> None:
        self.assertEqual(self.frame(self.tomas), NO_PRIMUM)

        self.sense(self.tomas)
        block = self.frame(self.tomas)

        self.assertEqual(
            block["sensed"],
            [{"substance_id": self.fire.pk, "substance_name": "fire", "step_name": "Massive"}],
        )
        self.assertEqual(block["line"], FIRE_LINE)
        self.assertEqual(
            [(o["substance_name"], o["source"], o["step_name"]) for o in block["harvestable"]],
            [("fire", "place", "Massive")],
        )

    def test_a_mage_senses_her_own_substance_and_the_line_joins_every_one_she_senses(self) -> None:
        self.assertEqual(self.frame(self.mira)["line"], FIRE_LINE)

        self.sense(self.mira, self.earth)
        block = self.frame(self.mira)

        self.assertEqual([row["substance_name"] for row in block["sensed"]], ["earth", "fire"])
        self.assertEqual(
            block["line"], "You sense earth Primum: Trace. You sense fire Primum: Massive."
        )

    def test_two_viewers_see_different_payloads(self) -> None:
        self.sense(self.tomas, self.earth)

        mira, tomas, odo = (self.frame(who) for who in (self.mira, self.tomas, self.odo))

        self.assertEqual(mira["line"], FIRE_LINE)
        self.assertEqual(tomas["line"], "You sense earth Primum: Trace.")
        self.assertEqual(odo, NO_PRIMUM)

    def test_payload_never_names_an_unperceived_substance(self) -> None:
        self.sense(self.tomas)

        for who in (self.mira, self.tomas, self.odo):
            self.assertNotIn("earth", str(self.frame(who)).lower())
        self.assertNotIn("fire", str(self.frame(self.odo)).lower())

    def test_the_frame_costs_the_same_queries_however_many_substances_the_room_reads(
        self,
    ) -> None:
        def frame_queries() -> int:
            self.frame(self.mira)  # warm the identity map, as a live server already is
            with CaptureQueriesContext(connection) as queries:
                self.frame(self.mira)
            return len(queries)

        before = frame_queries()
        for name, stat_key in (
            ("ice", StatKey.COLD),
            ("water", StatKey.WET),
            ("air", StatKey.WIND),
            ("shadow", StatKey.NOISE),
        ):
            substance = SubstanceFactory(
                name=name, stat_key=stat_key, direction=SubstanceDirection.RISING
            )
            self.lair(substance, 10)
            self.sense(self.mira, substance)

        self.assertEqual(
            [row["substance_name"] for row in self.frame(self.mira)["sensed"]],
            ["air", "fire", "ice", "shadow", "water"],
        )
        self.assertLessEqual(frame_queries(), before)

    def test_the_frame_arrives_as_the_one_room_state_frame_with_the_block(self) -> None:
        with patch.object(type(self.mira), "has_account", new_callable=PropertyMock) as has:
            has.return_value = True
            self.mira.send_room_state()

        frames = [
            kwargs["room_state"]
            for _args, kwargs in self.mailbox(self.mira).calls
            if "room_state" in kwargs
        ]
        self.assertEqual(len(frames), 1)
        args, payload = frames[0]
        self.assertEqual(args, ())
        self.assertEqual(payload["primum"]["line"], FIRE_LINE)


class Looking(_Caldera):
    def test_look_ends_with_the_you_sense_line(self) -> None:
        self.sense(self.mira, self.earth)

        told = self.telnet(self.mira, "look")

        self.assertTrue(
            told.rstrip().endswith(
                "You sense earth Primum: Trace. You sense fire Primum: Massive."
            ),
            told,
        )

    def test_look_says_nothing_of_primum_to_someone_who_senses_none(self) -> None:
        self.assertNotIn("Primum", self.telnet(self.odo, "look"))


class TheFightPanel(_Caldera):
    def test_defeated_opponent_offers_harvest_only_to_a_perceiving_viewer(self) -> None:
        foe = self.slain_elemental()
        self.sense(self.tomas)

        self.assertEqual(self.opponents_seen_by(self.mira, foe.encounter), {"elemental": True})
        self.assertEqual(self.opponents_seen_by(self.tomas, foe.encounter), {"elemental": True})
        self.assertEqual(self.opponents_seen_by(self.odo, foe.encounter), {"elemental": False})
        (offer,) = self.offers_seen_by(self.tomas, foe.encounter)["elemental"]
        self.assertEqual(
            (offer["substance_name"], offer["opponent_id"], offer["character_id"]),
            ("fire", foe.pk, self.tomas.pk),
        )

    def test_a_foe_still_standing_or_already_harvested_is_not_offered(self) -> None:
        foe = self.slain_elemental()
        foe.status = OpponentStatus.ACTIVE
        foe.save(update_fields=["status"])

        self.assertEqual(self.opponents_seen_by(self.mira, foe.encounter), {"elemental": False})

    def test_an_account_sees_a_foe_harvestable_through_a_played_character_it_has_not_selected(
        self,
    ) -> None:
        foe = self.slain_elemental()
        vesna = CharacterFactory(db_key="Vesna", location=self.room)
        CharacterSheetFactory(character=vesna)
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet__character=vesna),
            player_data=self.account_of(self.odo).player_data,
            end_date=None,
        )
        self.sense(vesna)

        # The account's selected character is still Odo, who perceives nothing.
        self.assertEqual(self.opponents_seen_by(self.odo, foe.encounter), {"elemental": True})


class AfterAHarvest(_Caldera):
    def test_a_successful_extract_pushes_every_viewer_a_fresh_frame_with_the_new_step(self) -> None:
        self.sense(self.tomas)
        self.tune_harvest()
        self.connect_telnet(self.tomas)
        self.connect_telnet(self.odo)
        before = len(self.room_frames(self.tomas))

        with (
            patch.object(type(self.tomas), "has_account", new_callable=PropertyMock) as has,
            force_check_outcome(self.success),
        ):
            has.return_value = True
            told = self.telnet(self.mira, "extract fire")

        self.assertIn("You draw out", told)
        frames = self.room_frames(self.tomas)
        self.assertEqual(len(frames), before + 1)
        self.assertEqual(frames[-1]["primum"]["line"], "You sense fire Primum: Some.")
        # Odo perceives nothing, so his fresh frame carries no Primum at all.
        self.assertEqual(self.room_frames(self.odo)[-1]["primum"], NO_PRIMUM)

    def test_extracting_a_slain_foe_tells_every_open_fight_panel_to_refetch(self) -> None:
        foe = self.slain_elemental()
        self.sense(self.tomas)
        self.tune_harvest()
        self.connect_telnet(self.tomas)
        self.assertEqual(self.opponents_seen_by(self.tomas, foe.encounter), {"elemental": True})

        with (
            patch.object(type(self.tomas), "has_account", new_callable=PropertyMock) as has,
            force_check_outcome(self.success),
            self.captureOnCommitCallbacks(execute=True),
        ):
            has.return_value = True
            told = self.telnet(self.mira, "extract fire from elemental")

        self.assertIn("You draw out", told)
        pings = [
            kwargs["combat_encounter_state"][1]
            for _args, kwargs in self.mailbox(self.tomas).calls
            if "combat_encounter_state" in kwargs
        ]
        self.assertEqual([ping["encounter_id"] for ping in pings], [foe.encounter_id])
        self.assertEqual(self.opponents_seen_by(self.tomas, foe.encounter), {"elemental": False})

    def tune_harvest(self) -> None:
        """Staff set up harvesting: a check type, a skill, an item and one outcome."""
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        ItemTemplateFactory(
            name="Fire Primum", primum_substance=self.fire, is_stackable=True, max_stack_size=20
        )
        HarvestOutcomeFactory(
            outcome_tier=self.success,
            amount_taken=75,
            quantity=2,
            quality_tier=QualityTierFactory(name="Fine"),
        )
        config = get_resonance_environment_config()
        config.harvest_check_type = CheckTypeFactory(
            name="Harvest Primum", category=CheckCategoryFactory(name="Magic")
        )
        config.harvest_skill = MagicSkillFactory(name="Primum harvesting")
        config.save(update_fields=["harvest_check_type", "harvest_skill"])

    def room_frames(self, who) -> list[dict]:
        return [
            kwargs["room_state"][1]
            for _args, kwargs in self.mailbox(who).calls
            if "room_state" in kwargs
        ]
