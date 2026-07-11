"""Journey test for the read-only battle aggregate API (#2009).

Mirrors world/combat/tests/test_views.py's account/scene setup: an account
is granted read access to a Battle's backing scene via SceneParticipation
(Scene.objects.viewable_by is the single source of truth for scene
visibility, world/scenes/managers.py), staff bypass it entirely.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status as http_status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.battles.constants import (
    BattleOutcome,
    BattlePosture,
    BattleSideRole,
    BattleUnitStatus,
    FortificationKind,
    TerrainType,
    UnitQuality,
    VehicleKind,
)
from world.battles.factories import (
    BattleFactory,
    BattlePlaceFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
    BattleVehicleFactory,
    FortificationFactory,
)
from world.battles.resolution import resolve_battle_round
from world.battles.services import begin_battle_round, conclude_battle, enlist_participant
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.covenants.factories import CovenantFactory
from world.roster.factories import PlayerMediaFactory
from world.scenes.constants import RoundStatus, ScenePrivacyMode
from world.scenes.factories import SceneParticipationFactory
from world.societies.factories import LegendEntryFactory, LegendSourceTypeFactory


class BattleApiJourneyTest(TestCase):
    """Covers list/detail shape, scene visibility, and the ?scene= filter."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.covenant = CovenantFactory(name="The Iron Vanguard")
        cls.battle = BattleFactory(name="Siege of the Gate")
        # Battle.save() auto-creates a PUBLIC scene; force PRIVATE so scene
        # visibility actually gates the API (mirrors combat's precedent).
        cls.battle.scene.privacy_mode = ScenePrivacyMode.PRIVATE
        cls.battle.scene.save(update_fields=["privacy_mode"])

        cls.attacker_side = BattleSideFactory(
            battle=cls.battle,
            role=BattleSideRole.ATTACKER,
            covenant=cls.covenant,
            victory_points=4,
            victory_threshold=10,
            posture=BattlePosture.BALANCED,
        )
        cls.defender_side = BattleSideFactory(
            battle=cls.battle,
            role=BattleSideRole.DEFENDER,
        )

        cls.place_ford = BattlePlaceFactory(
            battle=cls.battle,
            name="The Ford",
            terrain_type=TerrainType.FLOODED,
            movement_cost=2,
            controlled_by=cls.attacker_side,
            x=Decimal("10.5"),
            y=Decimal("-3.0"),
            footprint_radius=Decimal("2.0"),
        )
        cls.fortification = FortificationFactory(
            place=cls.place_ford,
            defending_side=cls.defender_side,
            kind=FortificationKind.WALL,
            integrity=5,
            max_integrity=8,
            breached=False,
        )
        cls.vehicle = BattleVehicleFactory(
            unit__battle=cls.battle,
            unit__side=cls.attacker_side,
            place=cls.place_ford,
            vehicle_kind=VehicleKind.SHIP,
            is_structural=True,
        )

        cls.encounter = CombatEncounterFactory()
        cls.place_yard = BattlePlaceFactory(
            battle=cls.battle,
            name="Statue Yard",
            combat_encounter=cls.encounter,
        )

        cls.ground_unit = BattleUnitFactory(
            battle=cls.battle,
            side=cls.attacker_side,
            place=cls.place_ford,
            name="Vanguard Pikes",
            descriptor="pike-and-shot",
            quality=UnitQuality.VETERAN,
            status=BattleUnitStatus.ACTIVE,
            strength=80,
            morale=60,
            individual_count=1,
        )
        cls.defender_unit = BattleUnitFactory(
            battle=cls.battle,
            side=cls.defender_side,
            place=cls.place_yard,
            name="Garrison Levy",
            descriptor="militia",
            quality=UnitQuality.MILITIA,
            status=BattleUnitStatus.ACTIVE,
            strength=50,
            morale=40,
        )

        cls.round = BattleRoundFactory(battle=cls.battle, round_number=3, status="declaring")

        cls.pc_sheet = CharacterSheetFactory()
        cls.pc_account = AccountFactory(username="battle_pc")
        SceneParticipationFactory(scene=cls.battle.scene, account=cls.pc_account)
        cls.participant = enlist_participant(
            battle=cls.battle,
            character_sheet=cls.pc_sheet,
            side=cls.attacker_side,
            place=cls.place_ford,
        )

        cls.staff_account = AccountFactory(username="battle_staff", is_staff=True)
        cls.other_account = AccountFactory(username="battle_outsider")

    def _assert_detail_shape(self, data: dict) -> None:
        self.assertEqual(data["id"], self.battle.pk)
        self.assertEqual(data["name"], "Siege of the Gate")
        self.assertEqual(data["outcome"], self.battle.outcome)
        self.assertEqual(data["risk_level"], self.battle.risk_level)
        self.assertIs(data["is_paused"], False)
        self.assertEqual(data["round"], {"number": 3, "status": "declaring"})

        self._assert_sides_shape(data["sides"])
        self._assert_places_shape(data["places"])
        self._assert_units_shape(data["units"])
        self._assert_participants_shape(data["participants"])

        # Writeup fields (#1735)
        self.assertEqual(data["scene_id"], self.battle.scene_id)
        self.assertIsNotNone(data["created_at"])
        self.assertIsNone(data["concluded_at"])  # not concluded yet
        self.assertIsNone(data["campaign_story_id"])  # no story linked
        self.assertEqual(data["deeds"], [])  # no deeds yet

    def _assert_sides_shape(self, sides: list[dict]) -> None:
        sides_by_role = {side["role"]: side for side in sides}
        attacker = sides_by_role["attacker"]
        self.assertEqual(attacker["id"], self.attacker_side.pk)
        self.assertEqual(attacker["victory_points"], 4)
        self.assertEqual(attacker["victory_threshold"], 10)
        self.assertEqual(attacker["posture"], "balanced")
        self.assertEqual(attacker["covenant_id"], self.covenant.pk)
        self.assertEqual(attacker["covenant_name"], "The Iron Vanguard")
        defender = sides_by_role["defender"]
        self.assertIsNone(defender["covenant_id"])
        self.assertIsNone(defender["covenant_name"])

    def _assert_places_shape(self, places: list[dict]) -> None:
        places_by_name = {place["name"]: place for place in places}
        ford = places_by_name["The Ford"]
        self.assertEqual(ford["id"], self.place_ford.pk)
        self.assertEqual(ford["terrain_type"], "flooded")
        self.assertEqual(ford["movement_cost"], 2)
        self.assertIsInstance(ford["x"], float)
        self.assertIsInstance(ford["y"], float)
        self.assertIsInstance(ford["footprint_radius"], float)
        self.assertEqual(ford["x"], 10.5)
        self.assertEqual(ford["y"], -3.0)
        self.assertEqual(ford["footprint_radius"], 2.0)
        self.assertEqual(ford["controlled_by_id"], self.attacker_side.pk)
        self.assertIsNone(ford["encounter_scene_id"])
        self.assertIsNotNone(ford["vehicle"])
        self.assertEqual(ford["vehicle"]["unit_id"], self.vehicle.unit_id)
        self.assertEqual(ford["vehicle"]["vehicle_kind"], "ship")
        self.assertIs(ford["vehicle"]["is_structural"], True)
        self.assertEqual(len(ford["fortifications"]), 1)
        fort = ford["fortifications"][0]
        self.assertEqual(fort["id"], self.fortification.pk)
        self.assertEqual(fort["kind"], "wall")
        self.assertEqual(fort["integrity"], 5)
        self.assertEqual(fort["max_integrity"], 8)
        self.assertIs(fort["breached"], False)
        self.assertEqual(fort["defending_side_id"], self.defender_side.pk)

        yard = places_by_name["Statue Yard"]
        self.assertEqual(yard["encounter_scene_id"], self.encounter.scene_id)
        self.assertIsNone(yard["vehicle"])
        self.assertEqual(yard["fortifications"], [])
        self.assertIn("encounter_roster", yard)

    def _assert_units_shape(self, units: list[dict]) -> None:
        units_by_name = {unit["name"]: unit for unit in units}
        vanguard = units_by_name["Vanguard Pikes"]
        self.assertEqual(vanguard["descriptor"], "pike-and-shot")
        self.assertEqual(vanguard["quality"], "veteran")
        self.assertEqual(vanguard["status"], "active")
        self.assertEqual(vanguard["strength"], 80)
        self.assertEqual(vanguard["morale"], 60)
        self.assertEqual(vanguard["individual_count"], 1)
        self.assertEqual(vanguard["side_id"], self.attacker_side.pk)
        self.assertEqual(vanguard["place_id"], self.place_ford.pk)
        garrison = units_by_name["Garrison Levy"]
        self.assertEqual(garrison["side_id"], self.defender_side.pk)
        self.assertEqual(garrison["place_id"], self.place_yard.pk)
        # The vehicle's own unit is present too, with no place (#1714 invariant).
        vehicle_unit = next(u for u in units if u["id"] == self.vehicle.unit_id)
        self.assertIsNone(vehicle_unit["place_id"])

    def _assert_participants_shape(self, participants: list[dict]) -> None:
        self.assertEqual(len(participants), 1)
        participant_data = participants[0]
        self.assertEqual(participant_data["id"], self.participant.pk)
        self.assertEqual(participant_data["status"], "active")
        self.assertEqual(participant_data["side_id"], self.attacker_side.pk)
        self.assertEqual(participant_data["place_id"], self.place_ford.pk)
        self.assertEqual(participant_data["persona"]["id"], self.pc_sheet.primary_persona.pk)
        self.assertEqual(participant_data["persona"]["name"], self.pc_sheet.primary_persona.name)
        self.assertIsNone(participant_data["persona"]["thumbnail_url"])
        self.assertIsNone(participant_data["persona"]["thumbnail_media_url"])
        self.assertNotIn("account", participant_data["persona"])
        self.assertNotIn("username", participant_data["persona"])

    def test_participant_can_retrieve_full_detail_shape(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.pc_account)
        response = client.get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self._assert_detail_shape(response.data)

    def test_encounter_roster_reflects_live_participants(self) -> None:
        from world.combat.services import join_encounter

        sheet = CharacterSheetFactory()
        join_encounter(self.encounter, sheet)
        opponent = CombatOpponentFactory(encounter=self.encounter, name="Yard Brute")

        client = APIClient()
        client.force_authenticate(user=self.pc_account)
        response = client.get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        yard = next(p for p in response.data["places"] if p["id"] == self.place_yard.pk)
        roster = yard["encounter_roster"]
        self.assertIsNotNone(roster)
        self.assertEqual(roster["status"], self.encounter.get_status_display())
        self.assertIsNone(roster["outcome"])
        self.assertEqual(len(roster["participants"]), 1)
        self.assertEqual(roster["participants"][0]["character_name"], sheet.character.db_key)
        self.assertEqual(len(roster["opponents"]), 1)
        self.assertEqual(roster["opponents"][0]["name"], opponent.name)
        self.assertEqual(roster["opponents"][0]["status"], opponent.get_status_display())

    def test_encounter_roster_is_none_when_no_encounter_bound(self) -> None:
        empty_place = BattlePlaceFactory(battle=self.battle, name="Empty Front")

        client = APIClient()
        client.force_authenticate(user=self.pc_account)
        response = client.get(f"/api/battles/{self.battle.pk}/")

        place = next(p for p in response.data["places"] if p["id"] == empty_place.pk)
        self.assertIsNone(place["encounter_roster"])

    def test_staff_can_retrieve_detail(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.battle.pk)

    def test_non_participant_detail_is_404_not_403(self) -> None:
        """No existence oracle — a private battle 404s for a non-viewer, not 403."""
        client = APIClient()
        client.force_authenticate(user=self.other_account)
        response = client.get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_list_excludes_battle_for_non_participant(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.other_account)
        response = client.get("/api/battles/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertNotIn(self.battle.pk, ids)

    def test_deeds_section_includes_only_this_battles_scene_deeds(self) -> None:
        """LegendEntry deeds scoped to the battle's backing scene appear in detail."""
        source_type = LegendSourceTypeFactory(name="Combat")
        # A deed on the battle's scene — should appear
        LegendEntryFactory(
            persona=self.pc_sheet.primary_persona,
            title="Slew the enemy commander",
            description="A decisive strike.",
            base_value=50,
            source_type=source_type,
            scene=self.battle.scene,
            is_active=True,
        )
        # A deed on a different scene — must NOT appear
        other_battle = BattleFactory(name="Other Battle")
        LegendEntryFactory(
            persona=self.pc_sheet.primary_persona,
            title="Unrelated deed",
            base_value=10,
            source_type=source_type,
            scene=other_battle.scene,
            is_active=True,
        )

        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        deeds = response.data["deeds"]
        self.assertEqual(len(deeds), 1)
        deed = deeds[0]
        self.assertEqual(deed["title"], "Slew the enemy commander")
        self.assertEqual(deed["description"], "A decisive strike.")
        self.assertEqual(deed["base_value"], 50)
        self.assertIsNotNone(deed["persona"])
        self.assertEqual(deed["persona"]["name"], self.pc_sheet.primary_persona.name)
        self.assertNotIn("account", deed["persona"])
        self.assertNotIn("username", deed["persona"])

    def test_deeds_do_not_cause_n_plus_1_queries(self) -> None:
        """Deeds prefetch must not scale query count with deed count."""
        source_type = LegendSourceTypeFactory(name="Heroism")
        for i in range(3):
            LegendEntryFactory(
                persona=self.pc_sheet.primary_persona,
                title=f"Deed {i}",
                base_value=10,
                source_type=source_type,
                scene=self.battle.scene,
                is_active=True,
            )

        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        # Warm up on a throwaway battle (one-time caching costs)
        warmup = BattleFactory(name="Warmup")
        client.get(f"/api/battles/{warmup.pk}/")

        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data["deeds"]), 3)
        query_count = len(ctx)
        self.assertLess(
            query_count,
            15,
            f"Expected deeds prefetch to keep queries flat; got {query_count} queries "
            "-- the deeds SerializerMethodField may be issuing per-deed queries (N+1).",
        )

    def _build_battle_with_participants(self, num_participants: int):
        """A standalone battle (own scene/side) enlisting `num_participants` PCs.

        Kept separate from `self.battle`/setUpTestData deliberately: idmapper
        caches model instances by pk process-wide, and Django's `to_attr`
        prefetch skips re-fetching a lookup that's already set on an instance
        (``is_to_attr_fetched`` in django/db/models/query.py) -- refetching the
        *same* Battle pk within one test would let the second request's
        prefetch silently no-op against the first request's cached attribute.
        Two distinct Battle rows sidestep that entirely.
        """
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        for _ in range(num_participants):
            enlist_participant(battle=battle, character_sheet=CharacterSheetFactory(), side=side)
        return battle

    def test_participant_persona_query_count_does_not_scale_with_participant_count(
        self,
    ) -> None:
        """Regression guard for the N+1 the review on #2009 caught: the detail
        view's participants Prefetch must nest a ``character_sheet__personas``
        Prefetch (to_attr ``cached_payload_personas``) so
        ``BattleParticipantSerializer._primary_persona`` never issues a
        per-participant query. Query count must stay flat as participants grow.
        """
        client = APIClient()
        client.force_authenticate(user=self.staff_account)

        battle_one = self._build_battle_with_participants(1)
        battle_many = self._build_battle_with_participants(3)

        # Warm up on a third, throwaway battle first: the very first request
        # in a test pays one-time costs (permission/content-type caching)
        # that a naive first-vs-second comparison would misread as N+1 growth.
        warmup_battle = self._build_battle_with_participants(1)
        client.get(f"/api/battles/{warmup_battle.pk}/")

        with CaptureQueriesContext(connection) as ctx_one:
            response_one = client.get(f"/api/battles/{battle_one.pk}/")
        self.assertEqual(response_one.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response_one.data["participants"]), 1)
        queries_one = len(ctx_one)

        with CaptureQueriesContext(connection) as ctx_many:
            response_many = client.get(f"/api/battles/{battle_many.pk}/")
        self.assertEqual(response_many.status_code, http_status.HTTP_200_OK)
        participants = response_many.data["participants"]
        self.assertEqual(len(participants), 3)
        for participant_data in participants:
            self.assertIsNotNone(participant_data["persona"])
        queries_many = len(ctx_many)

        self.assertEqual(
            queries_one,
            queries_many,
            f"Query count grew from {queries_one} (1 participant) to "
            f"{queries_many} (3 participants) -- the participants Prefetch is "
            "issuing a per-row persona query (N+1 regression).",
        )

    def test_participant_persona_thumbnail_media_url_resolves_uploaded_portrait(self) -> None:
        """Mirrors combat's ``get_thumbnail_media_url`` parity (#2009 review):
        the uploaded ``PlayerMedia`` portrait FK, not just the legacy URLField."""
        media = PlayerMediaFactory()
        persona = self.pc_sheet.primary_persona
        persona.thumbnail = media
        persona.save(update_fields=["thumbnail"])

        client = APIClient()
        client.force_authenticate(user=self.pc_account)
        response = client.get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        participant_data = response.data["participants"][0]
        self.assertEqual(participant_data["persona"]["thumbnail_media_url"], media.cloudinary_url)

    def test_scene_filter_returns_exactly_this_battle_for_participant(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.pc_account)
        response = client.get(f"/api/battles/?scene={self.battle.scene_id}")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.battle.pk)
        self.assertEqual(results[0]["scene_id"], self.battle.scene_id)


class BattleStatePingTest(TestCase):
    """BATTLE_STATE ping seam (#2009 Task 2).

    Battles are location-less (their backing scene has no ``location``), so the
    existing scene/room broadcast paths never reach participants -- this
    dedicated ping fills that gap on round transitions. Clients refetch the
    REST aggregate on receipt; the payload itself carries no battle data.
    """

    def setUp(self) -> None:
        self.battle = BattleFactory(name="Ping Battle")
        self.side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)

    def test_begin_battle_round_pings_connected_participant(self) -> None:
        sheet = CharacterSheetFactory()
        enlist_participant(battle=self.battle, character_sheet=sheet, side=self.side)
        character = sheet.character
        # Object.has_account reads session count, not db_account -- fake a
        # connected session so the ping's guard lets this participant through.
        character.sessions.count = lambda: 1

        with mock.patch.object(character, "msg") as mock_msg:
            # The ping is deferred via transaction.on_commit (#2009 review) so a
            # refetching client always sees committed state -- capture without
            # executing first to prove it hasn't fired mid-transaction.
            with self.captureOnCommitCallbacks() as callbacks:
                begin_battle_round(battle=self.battle)
            mock_msg.assert_not_called()
            self.assertEqual(len(callbacks), 1)

            for callback in callbacks:
                callback()

        mock_msg.assert_called_once_with(
            battle_state=((), {"battle_id": self.battle.pk, "round_number": 1})
        )

    def test_begin_battle_round_skips_participant_without_account(self) -> None:
        sheet = CharacterSheetFactory()
        enlist_participant(battle=self.battle, character_sheet=sheet, side=self.side)
        character = sheet.character

        # No session attached: has_account is False, so the guard must skip
        # this participant silently rather than erroring.
        with mock.patch.object(character, "msg") as mock_msg:
            with self.captureOnCommitCallbacks(execute=True):
                begin_battle_round(battle=self.battle)

        mock_msg.assert_not_called()

    def test_resolve_battle_round_pings_connected_participant(self) -> None:
        sheet = CharacterSheetFactory()
        enlist_participant(battle=self.battle, character_sheet=sheet, side=self.side)
        character = sheet.character
        # Object.has_account reads session count, not db_account -- fake a
        # connected session so the ping's guard lets this participant through.
        character.sessions.count = lambda: 1
        battle_round = BattleRoundFactory(
            battle=self.battle, round_number=1, status=RoundStatus.DECLARING
        )

        with mock.patch.object(character, "msg") as mock_msg:
            # Deferred via transaction.on_commit (same seam as begin_battle_round)
            # -- capture without executing first to prove it hasn't fired mid-transaction.
            with self.captureOnCommitCallbacks() as callbacks:
                resolve_battle_round(battle_round=battle_round)
            mock_msg.assert_not_called()
            self.assertEqual(len(callbacks), 1)

            for callback in callbacks:
                callback()

        # The round completes as part of resolution, so current_round is None
        # by the time the deferred ping reads it.
        mock_msg.assert_called_once_with(
            battle_state=((), {"battle_id": self.battle.pk, "round_number": None})
        )

    def test_conclude_battle_pings_connected_participant(self) -> None:
        sheet = CharacterSheetFactory()
        enlist_participant(battle=self.battle, character_sheet=sheet, side=self.side)
        character = sheet.character
        character.sessions.count = lambda: 1

        with mock.patch.object(character, "msg") as mock_msg:
            with self.captureOnCommitCallbacks() as callbacks:
                conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)
            mock_msg.assert_not_called()
            self.assertEqual(len(callbacks), 1)

            for callback in callbacks:
                callback()

        mock_msg.assert_called_once_with(
            battle_state=((), {"battle_id": self.battle.pk, "round_number": None})
        )
