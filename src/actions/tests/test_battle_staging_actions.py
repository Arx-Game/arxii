"""Tests for JUNIOR-gated GM battle-staging Actions (#2010).

Covers ``CreateBattleAction``, ``StageBattleMapAction``, ``SpawnBattleUnitsAction``,
``EnlistBattleParticipantAction``, ``BrowseBattleCatalogAction`` -- permission
journeys (sub-JUNIOR rejected by the ``MinimumGMLevelPrerequisite`` gate, JUNIOR
GM succeeds, a JUNIOR GM who isn't *this* battle's GM is rejected on the three
battle-scoped actions), the create -> stage -> spawn -> enlist happy path, and
catalog browsing (active-only, term filtering).
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.battles import (
    BrowseBattleCatalogAction,
    CreateBattleAction,
    EnlistBattleParticipantAction,
    SpawnBattleUnitsAction,
    StageBattleMapAction,
)
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.battles.constants import BattleSideRole
from world.battles.factories import (
    BattleMapBlueprintFactory,
    BattleUnitTemplateFactory,
    BlueprintBattlePlaceFactory,
)
from world.battles.models import Battle, BattleParticipant, BattlePlace, BattleUnit
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _room(db_key: str = "BattleStagingRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object, object]:
    """Return (Character, Account, CharacterSheet) with a live roster tenure."""
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account, sheet


class BattleStagingActionsTestBase(TestCase):
    """Shared fixture: JUNIOR GM, sub-JUNIOR (STARTING) GM, a second JUNIOR GM
    who never becomes a battle's own GM, plus one active blueprint + template.

    Built in ``setUp`` (per test), not ``setUpTestData`` -- Character
    typeclass instances hold an Evennia ``DbHolder`` attribute proxy that
    Django's ``setUpTestData`` cannot deepcopy for per-test isolation.
    """

    def setUp(self) -> None:
        self.room = _room()

        self.gm_actor, self.gm_account, self.gm_sheet = _pc_in_room(self.room, db_key="JuniorGM")
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)

        self.sub_junior_actor, self.sub_junior_account, _ = _pc_in_room(
            self.room, db_key="StartingGM"
        )
        GMProfileFactory(account=self.sub_junior_account, level=GMLevel.STARTING)

        # A second JUNIOR GM with no standing on any battle created below --
        # the "not the battle's own GM" case, distinct from below-JUNIOR trust.
        self.other_gm_actor, self.other_gm_account, _ = _pc_in_room(self.room, db_key="OtherGM")
        GMProfileFactory(account=self.other_gm_account, level=GMLevel.JUNIOR)

        self.blueprint = BattleMapBlueprintFactory(name="Ashwatch Gate")
        BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="The Gate")

        self.template = BattleUnitTemplateFactory(name="Levy Spearmen")


class CreateBattleActionTests(BattleStagingActionsTestBase):
    def test_sub_junior_rejected(self) -> None:
        result = CreateBattleAction().run(self.sub_junior_actor, name="Blocked Battle")
        self.assertFalse(result.success)
        self.assertFalse(Battle.objects.filter(name="Blocked Battle").exists())

    def test_junior_gm_can_create(self) -> None:
        result = CreateBattleAction().run(self.gm_actor, name="Siege of Ashwatch")
        self.assertTrue(result.success, result.message)
        battle = Battle.objects.get(pk=result.data["battle_id"])
        self.assertEqual(battle.name, "Siege of Ashwatch")
        self.assertEqual(battle.sides.count(), 2)
        # The creating account is recorded as the battle's own scene GM, so
        # later battle-scoped actions' _actor_may_gm_battle recognizes them.
        self.assertTrue(battle.scene.is_gm(self.gm_account))

    def test_binds_scene_location_to_actor_room(self) -> None:
        result = CreateBattleAction().run(self.gm_actor, name="Rooted Siege")
        self.assertTrue(result.success, result.message)
        battle = Battle.objects.get(pk=result.data["battle_id"])
        battle.scene.refresh_from_db()
        self.assertEqual(battle.scene.location, self.room)

    def test_create_from_blueprint_stages_places(self) -> None:
        result = CreateBattleAction().run(
            self.gm_actor, name="Blueprinted Battle", blueprint_id=self.blueprint.pk
        )
        self.assertTrue(result.success, result.message)
        battle = Battle.objects.get(pk=result.data["battle_id"])
        self.assertEqual(battle.places.count(), 1)

    def test_inactive_blueprint_id_rejected(self) -> None:
        self.blueprint.is_active = False
        self.blueprint.save(update_fields=["is_active"])
        result = CreateBattleAction().run(
            self.gm_actor, name="Should Fail", blueprint_id=self.blueprint.pk
        )
        self.assertFalse(result.success)
        self.assertFalse(Battle.objects.filter(name="Should Fail").exists())

    def test_blank_name_rejected(self) -> None:
        result = CreateBattleAction().run(self.gm_actor, name="   ")
        self.assertFalse(result.success)
        self.assertEqual(Battle.objects.count(), 0)

    def test_malformed_blueprint_id_rejected(self) -> None:
        result = CreateBattleAction().run(
            self.gm_actor, name="Malformed Blueprint", blueprint_id=""
        )
        self.assertFalse(result.success)
        self.assertFalse(Battle.objects.filter(name="Malformed Blueprint").exists())

    def test_malformed_campaign_story_id_rejected(self) -> None:
        result = CreateBattleAction().run(
            self.gm_actor, name="Malformed Story", campaign_story_id=""
        )
        self.assertFalse(result.success)
        self.assertFalse(Battle.objects.filter(name="Malformed Story").exists())

    def test_malformed_region_id_rejected(self) -> None:
        result = CreateBattleAction().run(self.gm_actor, name="Malformed Region", region_id="")
        self.assertFalse(result.success)
        self.assertFalse(Battle.objects.filter(name="Malformed Region").exists())


class StageBattleMapActionTests(BattleStagingActionsTestBase):
    def setUp(self) -> None:
        super().setUp()
        create_result = CreateBattleAction().run(self.gm_actor, name="Stagable Battle")
        self.battle = Battle.objects.get(pk=create_result.data["battle_id"])

    def test_sub_junior_rejected(self) -> None:
        result = StageBattleMapAction().run(
            self.sub_junior_actor, battle_id=self.battle.pk, blueprint_id=self.blueprint.pk
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.places.count(), 0)

    def test_non_gm_of_battle_junior_rejected(self) -> None:
        result = StageBattleMapAction().run(
            self.other_gm_actor, battle_id=self.battle.pk, blueprint_id=self.blueprint.pk
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.places.count(), 0)

    def test_gm_of_battle_can_stage(self) -> None:
        result = StageBattleMapAction().run(
            self.gm_actor, battle_id=self.battle.pk, blueprint_id=self.blueprint.pk
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(self.battle.places.count(), 1)

    def test_inactive_blueprint_id_rejected(self) -> None:
        self.blueprint.is_active = False
        self.blueprint.save(update_fields=["is_active"])
        result = StageBattleMapAction().run(
            self.gm_actor, battle_id=self.battle.pk, blueprint_id=self.blueprint.pk
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.places.count(), 0)

    def test_unknown_battle_id_rejected(self) -> None:
        result = StageBattleMapAction().run(
            self.gm_actor, battle_id=999999, blueprint_id=self.blueprint.pk
        )
        self.assertFalse(result.success)

    def test_malformed_battle_id_rejected(self) -> None:
        result = StageBattleMapAction().run(
            self.gm_actor, battle_id="", blueprint_id=self.blueprint.pk
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.places.count(), 0)

    def test_malformed_blueprint_id_rejected(self) -> None:
        result = StageBattleMapAction().run(
            self.gm_actor, battle_id=self.battle.pk, blueprint_id=""
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.places.count(), 0)


class SpawnBattleUnitsActionTests(BattleStagingActionsTestBase):
    def setUp(self) -> None:
        super().setUp()
        create_result = CreateBattleAction().run(self.gm_actor, name="Spawnable Battle")
        self.battle = Battle.objects.get(pk=create_result.data["battle_id"])
        self.side = self.battle.sides.get(role=BattleSideRole.ATTACKER)

    def test_sub_junior_rejected(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.sub_junior_actor,
            battle_id=self.battle.pk,
            template_id=self.template.pk,
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)

    def test_non_gm_of_battle_junior_rejected(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.other_gm_actor,
            battle_id=self.battle.pk,
            template_id=self.template.pk,
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)

    def test_gm_of_battle_can_spawn(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            template_id=self.template.pk,
            side_id=self.side.pk,
            count=3,
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(BattleUnit.objects.filter(battle=self.battle).count(), 3)

    def test_inactive_template_id_rejected(self) -> None:
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])
        result = SpawnBattleUnitsAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            template_id=self.template.pk,
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)

    def test_side_from_another_battle_rejected(self) -> None:
        other_battle = Battle.objects.get(
            pk=CreateBattleAction().run(self.gm_actor, name="Unrelated Battle").data["battle_id"]
        )
        other_side = other_battle.sides.get(role=BattleSideRole.ATTACKER)
        result = SpawnBattleUnitsAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            template_id=self.template.pk,
            side_id=other_side.pk,
        )
        self.assertFalse(result.success)

    def test_malformed_battle_id_rejected(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.gm_actor, battle_id="", template_id=self.template.pk, side_id=self.side.pk
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)

    def test_malformed_template_id_rejected(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.gm_actor, battle_id=self.battle.pk, template_id="", side_id=self.side.pk
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)

    def test_malformed_side_id_rejected(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.gm_actor, battle_id=self.battle.pk, template_id=self.template.pk, side_id=""
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)

    def test_malformed_place_id_rejected(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            template_id=self.template.pk,
            side_id=self.side.pk,
            place_id="",
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)

    def test_non_numeric_count_rejected(self) -> None:
        result = SpawnBattleUnitsAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            template_id=self.template.pk,
            side_id=self.side.pk,
            count="abc",
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.units.count(), 0)


class EnlistBattleParticipantActionTests(BattleStagingActionsTestBase):
    def setUp(self) -> None:
        super().setUp()
        create_result = CreateBattleAction().run(self.gm_actor, name="Enlistable Battle")
        self.battle = Battle.objects.get(pk=create_result.data["battle_id"])
        self.side = self.battle.sides.get(role=BattleSideRole.DEFENDER)
        _, _, self.recruit_sheet = _pc_in_room(self.room, db_key="Recruit")

    def test_sub_junior_rejected(self) -> None:
        result = EnlistBattleParticipantAction().run(
            self.sub_junior_actor,
            battle_id=self.battle.pk,
            character_sheet_id=self.recruit_sheet.pk,
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.participants.count(), 0)

    def test_non_gm_of_battle_junior_rejected(self) -> None:
        result = EnlistBattleParticipantAction().run(
            self.other_gm_actor,
            battle_id=self.battle.pk,
            character_sheet_id=self.recruit_sheet.pk,
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.participants.count(), 0)

    def test_gm_of_battle_can_enlist(self) -> None:
        result = EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            character_sheet_id=self.recruit_sheet.pk,
            side_id=self.side.pk,
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            BattleParticipant.objects.filter(
                battle=self.battle, character_sheet=self.recruit_sheet, side=self.side
            ).exists()
        )

    def test_duplicate_enlist_rejected(self) -> None:
        EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            character_sheet_id=self.recruit_sheet.pk,
            side_id=self.side.pk,
        )
        result = EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            character_sheet_id=self.recruit_sheet.pk,
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(
            BattleParticipant.objects.filter(
                battle=self.battle, character_sheet=self.recruit_sheet
            ).count(),
            1,
        )

    def test_malformed_battle_id_rejected(self) -> None:
        result = EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id="",
            character_sheet_id=self.recruit_sheet.pk,
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.participants.count(), 0)

    def test_malformed_character_sheet_id_rejected(self) -> None:
        result = EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            character_sheet_id="",
            side_id=self.side.pk,
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.participants.count(), 0)

    def test_malformed_side_id_rejected(self) -> None:
        result = EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            character_sheet_id=self.recruit_sheet.pk,
            side_id="",
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.participants.count(), 0)

    def test_malformed_place_id_rejected(self) -> None:
        result = EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id=self.battle.pk,
            character_sheet_id=self.recruit_sheet.pk,
            side_id=self.side.pk,
            place_id="",
        )
        self.assertFalse(result.success)
        self.assertEqual(self.battle.participants.count(), 0)


class CreateStageSpawnEnlistHappyPathTests(BattleStagingActionsTestBase):
    """The full staging pipeline, chained, mutates the expected rows end to end."""

    def test_full_pipeline_mutates_expected_rows(self) -> None:
        create_result = CreateBattleAction().run(self.gm_actor, name="Pipeline Battle")
        self.assertTrue(create_result.success, create_result.message)
        battle = Battle.objects.get(pk=create_result.data["battle_id"])

        stage_result = StageBattleMapAction().run(
            self.gm_actor, battle_id=battle.pk, blueprint_id=self.blueprint.pk
        )
        self.assertTrue(stage_result.success, stage_result.message)
        place = BattlePlace.objects.get(battle=battle)

        side = battle.sides.get(role=BattleSideRole.ATTACKER)
        spawn_result = SpawnBattleUnitsAction().run(
            self.gm_actor,
            battle_id=battle.pk,
            template_id=self.template.pk,
            side_id=side.pk,
            place_id=place.pk,
            count=2,
        )
        self.assertTrue(spawn_result.success, spawn_result.message)
        self.assertEqual(BattleUnit.objects.filter(battle=battle, place=place).count(), 2)

        _, _, recruit_sheet = _pc_in_room(self.room, db_key="PipelineRecruit")
        enlist_result = EnlistBattleParticipantAction().run(
            self.gm_actor,
            battle_id=battle.pk,
            character_sheet_id=recruit_sheet.pk,
            side_id=battle.sides.get(role=BattleSideRole.DEFENDER).pk,
        )
        self.assertTrue(enlist_result.success, enlist_result.message)
        self.assertTrue(
            BattleParticipant.objects.filter(battle=battle, character_sheet=recruit_sheet).exists()
        )


class BrowseBattleCatalogActionTests(BattleStagingActionsTestBase):
    def test_sub_junior_rejected(self) -> None:
        result = BrowseBattleCatalogAction().run(self.sub_junior_actor)
        self.assertFalse(result.success)

    def test_junior_gm_browses_all_active_catalog(self) -> None:
        result = BrowseBattleCatalogAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.assertIn(self.blueprint.name, result.message)
        self.assertIn(self.template.name, result.message)

    def test_term_filters_to_matching_entries(self) -> None:
        other_blueprint = BattleMapBlueprintFactory(name="Frostfield Line")
        result = BrowseBattleCatalogAction().run(self.gm_actor, term="Ashwatch")
        self.assertTrue(result.success, result.message)
        self.assertIn(self.blueprint.name, result.message)
        self.assertNotIn(other_blueprint.name, result.message)

    def test_inactive_rows_excluded(self) -> None:
        self.blueprint.is_active = False
        self.blueprint.save(update_fields=["is_active"])
        result = BrowseBattleCatalogAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.assertNotIn(self.blueprint.name, result.message)

    def test_term_filters_to_matching_template(self) -> None:
        other_template = BattleUnitTemplateFactory(name="Sellswords", descriptor="Grim Mercenaries")
        result = BrowseBattleCatalogAction().run(self.gm_actor, term="grim")
        self.assertTrue(result.success, result.message)
        self.assertIn(other_template.name, result.message)
        self.assertNotIn(self.blueprint.name, result.message)
