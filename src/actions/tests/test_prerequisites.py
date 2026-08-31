"""Tests for action prerequisite classes."""

from django.test import TestCase, tag

from actions.prerequisites import (
    BuildWarrantPrerequisite,
    IsSceneGMPrerequisite,
    MinimumGMLevelPrerequisite,
    PendingRitualEffectPrerequisite,
)
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import AreaBuildGrantFactory, GMProfileFactory
from world.locations.constants import LocationParentType
from world.magic.constants import RitualExecutionKind
from world.magic.factories import CharacterResonanceFactory, RitualFactory
from world.magic.models import PendingRitualEffect
from world.narrative.factories import AmbientEmoteLineFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _gm_actor(level: str, *, db_key: str = "GMActor") -> object:
    """Return a Character with a live roster tenure + GMProfile at ``level``.

    Mirrors ``world/scenes/tests/test_scene_admin_services.py``'s
    ``_create_pc_with_account`` helper -- ``active_account`` requires a real
    ``RosterTenure``, not just ``char.db_account``.
    """
    char = CharacterFactory(db_key=db_key)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    GMProfileFactory(account=account, level=level)
    return char


def _plain_actor(*, db_key: str = "PlainActor", is_staff: bool = False) -> object:
    """Return a Character connected to a plain (non-GM) account."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"account_{db_key}", is_staff=is_staff)
    char.db_account = account
    char.save()
    return char


class MinimumGMLevelPrerequisiteTests(TestCase):
    """MinimumGMLevelPrerequisite (#2117) -- staff bypass + GMProfile.level tier compare."""

    def test_staff_bypasses_regardless_of_gm_profile(self) -> None:
        actor = _plain_actor(db_key="StaffBypass", is_staff=True)
        met, reason = MinimumGMLevelPrerequisite(GMLevel.SENIOR).is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_missing_gm_profile_is_refused_even_at_starting_tier(self) -> None:
        actor = _plain_actor(db_key="NoProfile")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.STARTING).is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "GM trust required.")

    def test_actor_with_no_account_is_refused(self) -> None:
        actor = CharacterFactory(db_key="NoAccount")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.STARTING).is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "GM trust required.")

    def test_gm_at_exact_tier_passes(self) -> None:
        actor = _gm_actor(GMLevel.JUNIOR, db_key="ExactTier")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.JUNIOR).is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_gm_above_tier_passes(self) -> None:
        actor = _gm_actor(GMLevel.SENIOR, db_key="AboveTier")
        met, _reason = MinimumGMLevelPrerequisite(GMLevel.JUNIOR).is_met(actor)
        self.assertTrue(met)

    def test_gm_below_tier_is_refused_with_tier_specific_message(self) -> None:
        actor = _gm_actor(GMLevel.STARTING, db_key="BelowTier")
        met, reason = MinimumGMLevelPrerequisite(GMLevel.JUNIOR).is_met(actor)
        self.assertFalse(met)
        self.assertIn("Junior GM", reason)


def _room(*, db_key: str = "PrereqRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _actor_in_room(room: object, *, db_key: str = "Actor") -> tuple[object, object]:
    """Return (Character, Account) -- the character is located in *room*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account


class IsSceneGMPrerequisiteTests(TestCase):
    """IsSceneGMPrerequisite (#2118) -- staff bypass + Scene.is_gm on the actor's active scene."""

    def setUp(self) -> None:
        self.room = _room()
        self.scene = SceneFactory(location=self.room)

    def test_staff_bypasses_regardless_of_scene_gm_status(self) -> None:
        actor = _plain_actor(db_key="StaffCheckBypass", is_staff=True)
        met, reason = IsSceneGMPrerequisite().is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_scene_gm_passes(self) -> None:
        actor, account = _actor_in_room(self.room, db_key="SceneGM")
        SceneParticipationFactory(scene=self.scene, account=account, is_gm=True)
        met, reason = IsSceneGMPrerequisite().is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_non_gm_scene_participant_is_refused(self) -> None:
        actor, account = _actor_in_room(self.room, db_key="NonGMParticipant")
        SceneParticipationFactory(scene=self.scene, account=account, is_gm=False)
        met, reason = IsSceneGMPrerequisite().is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "Only the scene's GM or staff can do that.")

    def test_scene_co_owner_without_gm_flag_is_refused(self) -> None:
        """Administering a scene (co-owner) does not by itself grant adjudication power."""
        actor, account = _actor_in_room(self.room, db_key="CoOwner")
        SceneParticipationFactory(scene=self.scene, account=account, is_owner=True, is_gm=False)
        met, reason = IsSceneGMPrerequisite().is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "Only the scene's GM or staff can do that.")

    def test_no_active_scene_is_refused(self) -> None:
        empty_room = _room(db_key="EmptyPrereqRoom")
        actor, _account = _actor_in_room(empty_room, db_key="NoSceneActor")
        met, reason = IsSceneGMPrerequisite().is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "Only the scene's GM or staff can do that.")


class PendingRitualEffectPrerequisiteTests(TestCase):
    def setUp(self):
        self.cr = CharacterResonanceFactory()
        self.sheet = self.cr.character_sheet
        self.character = self.sheet.character
        self.ritual = RitualFactory(
            name="Rite of Weaving",
            execution_kind=RitualExecutionKind.CEREMONY,
            service_function_path="",
        )
        self.prereq = PendingRitualEffectPrerequisite("Rite of Weaving")

    def test_not_met_without_pending_effect(self):
        met, msg = self.prereq.is_met(self.character)
        self.assertFalse(met)
        self.assertIn("Rite of Weaving", msg)

    def test_met_when_pending_effect_exists(self):
        PendingRitualEffect.objects.create(character=self.sheet, ritual=self.ritual)
        met, msg = self.prereq.is_met(self.character)
        self.assertTrue(met)
        self.assertEqual(msg, "")

    def test_not_met_when_ritual_missing(self):
        prereq = PendingRitualEffectPrerequisite("Nonexistent Ritual")
        met, msg = prereq.is_met(self.character)
        self.assertFalse(met)
        self.assertIn("Nonexistent Ritual", msg)


def _gm_actor_and_account(level: str = GMLevel.STARTING, *, db_key: str = "BuildWarrantGM"):
    """Return (Character, AccountDB) -- the tenure wiring ``BuildWarrantPrerequisite``
    needs to resolve ``actor.active_account`` (same shape as this module's ``_gm_actor``,
    which discards the account; this variant keeps it so a test can attach an
    ``AreaBuildGrant`` to the exact account the prerequisite will resolve).
    """
    char = CharacterFactory(db_key=db_key)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    GMProfileFactory(account=account, level=level)
    return char, account


class BuildWarrantPrerequisiteTests(TestCase):
    """BuildWarrantPrerequisite (#3477) -- staff bypass, else an AreaBuildGrant.

    Only the direct-area-match cases run here untagged (SQLite-safe, see
    ``has_build_warrant``'s docstring); subtree descent is covered by
    ``world.gm.tests.test_area_build_grant`` under ``@tag("postgres")``.
    """

    def test_staff_bypasses_with_no_kwargs_and_no_grants(self) -> None:
        actor = _plain_actor(db_key="BuildWarrantStaff", is_staff=True)
        met, reason = BuildWarrantPrerequisite().is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_no_area_kwarg_non_staff_refused_like_staff_only(self) -> None:
        actor, _account = _gm_actor_and_account(db_key="NoAreaKwarg")
        met, reason = BuildWarrantPrerequisite().is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "Staff only.")

    def test_actor_with_no_resolvable_account_refused(self) -> None:
        actor = CharacterFactory(db_key="NoAccountBuildWarrant")
        area = AreaFactory(level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite().is_met(
            actor, context={"kwargs": {"area_id": area.pk}}
        )
        self.assertFalse(met)
        self.assertEqual(reason, "Staff only.")

    def test_area_id_kwarg_no_grant_refused(self) -> None:
        actor, _account = _gm_actor_and_account(db_key="NoGrantAreaId")
        area = AreaFactory(level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite().is_met(
            actor, context={"kwargs": {"area_id": area.pk}}
        )
        self.assertFalse(met)
        self.assertEqual(reason, "No build grant covers this area.")

    def test_area_id_kwarg_direct_grant_passes(self) -> None:
        actor, account = _gm_actor_and_account(db_key="DirectGrantAreaId")
        area = AreaFactory(level=AreaLevel.WARD)
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite().is_met(
            actor, context={"kwargs": {"area_id": area.pk}}
        )
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_room_id_kwarg_resolves_area_via_room_profile(self) -> None:
        actor, account = _gm_actor_and_account(db_key="DirectGrantRoomId")
        area = AreaFactory(level=AreaLevel.WARD)
        room_profile = RoomProfileFactory(area=area)
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite().is_met(
            actor, context={"kwargs": {"room_id": room_profile.objectdb_id}}
        )
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_line_param_kwarg_resolves_room_scoped_line(self) -> None:
        """#3477 Task 3 fix round 1 -- a room-scoped line resolves via room_profile.area."""
        actor, account = _gm_actor_and_account(db_key="LineParamRoomScoped")
        area = AreaFactory(level=AreaLevel.WARD)
        room_profile = RoomProfileFactory(area=area)
        line = AmbientEmoteLineFactory(room_profile=room_profile)
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite(line_param="line_id").is_met(
            actor, context={"kwargs": {"line_id": line.pk}}
        )
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_line_param_kwarg_resolves_area_scoped_line_directly(self) -> None:
        """An AREA-scoped line (no room_profile) resolves via its own ``area`` FK."""
        actor, account = _gm_actor_and_account(db_key="LineParamAreaScoped")
        area = AreaFactory(level=AreaLevel.WARD)
        line = AmbientEmoteLineFactory(
            parent_type=LocationParentType.AREA, area=area, room_profile=None
        )
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite(line_param="line_id").is_met(
            actor, context={"kwargs": {"line_id": line.pk}}
        )
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_line_param_kwarg_no_grant_refused(self) -> None:
        """A GM with no covering grant is refused, same as the room_id/area_id paths."""
        actor, _account = _gm_actor_and_account(db_key="LineParamNoGrant")
        area = AreaFactory(level=AreaLevel.WARD)
        room_profile = RoomProfileFactory(area=area)
        line = AmbientEmoteLineFactory(room_profile=room_profile)
        met, reason = BuildWarrantPrerequisite(line_param="line_id").is_met(
            actor, context={"kwargs": {"line_id": line.pk}}
        )
        self.assertFalse(met)
        self.assertEqual(reason, "No build grant covers this area.")

    def test_line_param_no_kwarg_refused_like_staff_only(self) -> None:
        """No ``line_id`` kwarg present -- falls through exactly like the base class does
        with no ``area_id``/``room_id``."""
        actor, _account = _gm_actor_and_account(db_key="LineParamMissingKwarg")
        met, reason = BuildWarrantPrerequisite(line_param="line_id").is_met(actor)
        self.assertFalse(met)
        self.assertEqual(reason, "Staff only.")

    def test_line_param_staff_bypasses_regardless_of_line_kwarg(self) -> None:
        """Staff pass unconditionally, same as every other BuildWarrantPrerequisite shape."""
        actor = _plain_actor(db_key="LineParamStaffBypass", is_staff=True)
        met, reason = BuildWarrantPrerequisite(line_param="line_id").is_met(actor)
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_level_param_ceiling_refuses_direct_match(self) -> None:
        """A BUILDING-capped grant can't authorize a WARD-level ``level`` kwarg."""
        actor, account = _gm_actor_and_account(db_key="LevelCeiling")
        area = AreaFactory(level=AreaLevel.WARD)
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.BUILDING)
        met, reason = BuildWarrantPrerequisite(level_param="level").is_met(
            actor, context={"kwargs": {"area_id": area.pk, "level": int(AreaLevel.WARD)}}
        )
        self.assertFalse(met)
        self.assertEqual(reason, "No build grant covers this area.")

    def test_level_param_no_kwarg_checks_areas_current_level(self) -> None:
        """No ``level`` kwarg present -- checked against the area's OWN current level,

        not a fixed floor (#3477 fix round 1): a BUILDING-capped grant on a WARD-level
        area is refused even for an edit that never touches ``level`` -- editing an
        area already above your ceiling is refused, not just raising it further.
        """
        actor, account = _gm_actor_and_account(db_key="LevelParamNoKwargAboveCeiling")
        area = AreaFactory(level=AreaLevel.WARD)
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.BUILDING)
        met, reason = BuildWarrantPrerequisite(level_param="level").is_met(
            actor, context={"kwargs": {"area_id": area.pk}}
        )
        self.assertFalse(met)
        self.assertEqual(reason, "No build grant covers this area.")

    def test_level_param_no_kwarg_within_ceiling_passes(self) -> None:
        """No ``level`` kwarg present, area's current level is within the grant's cap."""
        actor, account = _gm_actor_and_account(db_key="LevelParamNoKwargWithinCeiling")
        area = AreaFactory(level=AreaLevel.BUILDING)
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.BUILDING)
        met, reason = BuildWarrantPrerequisite(level_param="level").is_met(
            actor, context={"kwargs": {"area_id": area.pk}}
        )
        self.assertTrue(met)
        self.assertEqual(reason, "")

    def test_level_param_kwarg_cannot_exceed_ceiling_even_below_areas_level(self) -> None:
        """A grant covering the area's current (higher) level still can't raise it further.

        Area is already WARD; grant is capped at WARD (covers the area as-is); sending
        ``level=WORLD`` must still be refused -- the incoming kwarg is the stricter side
        of the max() here, not the area's current level.
        """
        actor, account = _gm_actor_and_account(db_key="LevelParamKwargAboveCeiling")
        area = AreaFactory(level=AreaLevel.WARD)
        AreaBuildGrantFactory(account=account, area=area, max_level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite(level_param="level").is_met(
            actor, context={"kwargs": {"area_id": area.pk, "level": int(AreaLevel.WORLD)}}
        )
        self.assertFalse(met)
        self.assertEqual(reason, "No build grant covers this area.")

    @tag("postgres")  # closure descent -- see world.gm.tests.test_area_build_grant
    def test_area_id_kwarg_descent_passes(self) -> None:
        actor, account = _gm_actor_and_account(db_key="DescentAreaId")
        ward = AreaFactory(level=AreaLevel.WARD)
        building = AreaFactory(level=AreaLevel.BUILDING, parent=ward)
        AreaBuildGrantFactory(account=account, area=ward, max_level=AreaLevel.WARD)
        met, reason = BuildWarrantPrerequisite().is_met(
            actor, context={"kwargs": {"area_id": building.pk}}
        )
        self.assertTrue(met)
        self.assertEqual(reason, "")
