"""Tests for effect handlers in the mechanics app."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.captivity.constants import CaptivityStatus
from world.captivity.models import Captivity
from world.captivity.services import capture_character
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.combat.interpose_content import ensure_interpose_content
from world.conditions.factories import ConditionTemplateFactory, DamageTypeFactory
from world.conditions.models import ConditionInstance
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.mechanics.effect_handlers import _resolve_target, apply_effect
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance
from world.missions.services.run import grant_rescue_mission
from world.scenes.factories import SceneFactory
from world.scenes.models import PendingSuddenHarm
from world.societies.factories import OrganizationFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import CharacterVitals


class ResolveTargetTests(TestCase):
    """Tests for _resolve_target covering SELF, TARGET, and LOCATION."""

    def test_self_returns_context_character(self) -> None:
        effect = MagicMock(target=EffectTarget.SELF)
        character = MagicMock()
        context = MagicMock(character=character)
        assert _resolve_target(effect, context) is character

    def test_target_returns_context_target(self) -> None:
        effect = MagicMock(target=EffectTarget.TARGET)
        target_char = MagicMock()
        context = MagicMock(target=target_char)
        assert _resolve_target(effect, context) is target_char

    def test_target_falls_back_to_character_when_target_is_none(self) -> None:
        effect = MagicMock(target=EffectTarget.TARGET)
        character = MagicMock()
        context = MagicMock(target=None, character=character)
        assert _resolve_target(effect, context) is character


class MagicalScarsHandlerTests(TestCase):
    """Tests for the MAGICAL_SCARS effect handler.

    The handler now creates a PendingAlteration rather than directly applying
    a condition. Full coverage lives in world.magic.tests.test_alteration_handler.
    This suite covers the skip paths exercised via the mechanics test DB.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Character with no CharacterSheet — exercises the skip path.
        cls.character = CharacterFactory()
        cls.consequence = ConsequenceFactory()
        cls.effect = ConsequenceEffectFactory(
            consequence=cls.consequence,
            effect_type=EffectType.MAGICAL_SCARS,
        )

    def test_magical_scars_skips_without_sheet(self) -> None:
        """MAGICAL_SCARS handler returns applied=False when target has no CharacterSheet."""
        context = ResolutionContext(character=self.character)
        result = apply_effect(self.effect, context)
        assert not result.applied
        assert result.skip_reason is not None


class DealDamageHandlerTests(TestCase):
    """Tests for the DEAL_DAMAGE effect handler."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.character = CharacterFactory(db_key="damage_target")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.vitals = CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=100,
            max_health=100,
        )
        cls.damage_type = DamageTypeFactory(name="fire")
        cls.consequence = ConsequenceFactory()
        cls.effect = ConsequenceEffectFactory(
            consequence=cls.consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=30,
            damage_type=cls.damage_type,
        )

    def setUp(self) -> None:
        """Reset vitals health before each test."""
        CharacterVitals.objects.filter(pk=self.vitals.pk).update(health=100)
        self.vitals.refresh_from_db()

    @patch("world.mechanics.effect_handlers.process_damage_consequences", autospec=True)
    def test_applies_damage_to_vitals(self, mock_pipeline: MagicMock) -> None:
        """DEAL_DAMAGE handler reduces health on CharacterVitals."""
        context = ResolutionContext(character=self.character)
        result = apply_effect(self.effect, context)
        self.vitals.refresh_from_db()
        assert result.applied is True
        assert self.vitals.health == 70
        mock_pipeline.assert_called_once_with(
            character_sheet=self.sheet,
            damage_dealt=30,
            damage_type=self.damage_type,
        )

    def test_returns_applied_true_with_description(self) -> None:
        """Successful damage returns applied=True with a descriptive message."""
        with patch("world.mechanics.effect_handlers.process_damage_consequences", autospec=True):
            context = ResolutionContext(character=self.character)
            result = apply_effect(self.effect, context)
        assert result.applied is True
        assert "30" in result.description
        assert "fire" in result.description
        assert result.effect_type == EffectType.DEAL_DAMAGE

    def test_skips_when_no_vitals(self) -> None:
        """Target without vitals gets applied=False."""
        char_no_vitals = CharacterFactory(db_key="no_vitals_char")
        CharacterSheetFactory(character=char_no_vitals)
        # No CharacterVitals created for this character
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=10,
            damage_type=self.damage_type,
        )
        context = ResolutionContext(character=char_no_vitals)
        result = apply_effect(effect, context)
        assert result.applied is False
        assert "no charactervitals" in result.skip_reason.lower()

    def test_skips_when_no_sheet(self) -> None:
        """Target without a CharacterSheet gets applied=False."""
        char_no_sheet = CharacterFactory(db_key="no_sheet_char")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=10,
            damage_type=self.damage_type,
        )
        context = ResolutionContext(character=char_no_sheet)
        result = apply_effect(effect, context)
        assert result.applied is False

    def test_defers_when_bystander_present(self) -> None:
        """A conscious bystander present holds the harm for a reactive Interpose beat.

        Above SceneRoundDefaultsConfig.sudden_harm_interpose_threshold (default 10),
        with a bystander present, _deal_damage must NOT drop health immediately —
        it defers via arm_or_apply_sudden_harm (#1316).
        """
        ensure_interpose_content()
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.character.db_location = room
        self.character.save(update_fields=["db_location"])

        bystander = CharacterFactory(db_key="bystander")
        bystander_sheet = CharacterSheetFactory(character=bystander)
        CharacterVitalsFactory(character_sheet=bystander_sheet)
        bystander.db_location = room
        bystander.save(update_fields=["db_location"])

        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=15,
            damage_type=self.damage_type,
        )
        context = ResolutionContext(character=self.character)
        with patch("world.mechanics.effect_handlers.process_damage_consequences", autospec=True):
            result = apply_effect(effect, context)

        self.vitals.refresh_from_db()
        assert self.vitals.health == 100
        assert result.applied is True
        assert PendingSuddenHarm.objects.filter(target_sheet=self.sheet).exists()


def _captive_loop_template(name: str):
    """Minimal grantable template: entry node → one BRANCH option to a terminal."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    second = MissionNodeFactory(template=template, key="second")
    MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER try the door",
        branch_target=second,
    )
    return template


class CaptureHandlerTests(TestCase):
    """Tests for the CAPTURE effect handler (#931).

    The handler fires the captivity service from a consequence pool. Full
    capture/release coverage lives in world.captivity.tests; this suite
    proves the seam: dispatch, authored fields, and the skip paths.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.site = ObjectDBFactory(
            db_key="Ambush Site",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def _captive_at_site(self, key: str):
        character = CharacterFactory(db_key=key)
        sheet = CharacterSheetFactory(character=character)
        character.move_to(self.site, quiet=True)
        return character, sheet

    def test_capture_takes_the_target_into_a_cell(self) -> None:
        character, sheet = self._captive_at_site("capture_target")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied
        sheet.refresh_from_db()
        assert sheet.lifecycle_state == LifecycleState.CAPTURED
        captivity = Captivity.objects.get(captive=sheet)
        assert captivity.status == CaptivityStatus.HELD
        # The capture site (the character's location) is where they'll return.
        assert captivity.cell.return_location == self.site
        assert captivity.offscreen_loss_allowed is False

    def test_capture_carries_authored_captor_and_offscreen_flag(self) -> None:
        character, sheet = self._captive_at_site("authored_target")
        org = OrganizationFactory()
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
            capture_captor_organization=org,
            capture_offscreen_loss_allowed=True,
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied
        captivity = Captivity.objects.get(captive=sheet)
        assert captivity.captor_organization == org
        assert captivity.offscreen_loss_allowed is True

    def test_capture_uses_the_effects_override_cell_flavor(self) -> None:
        # The per-capture override on the CAPTURE effect names the spawned cell,
        # proving override-then-default reaches the room the captive lands in.
        character, sheet = self._captive_at_site("flavored_target")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
            capture_cell_name="The Blood Crypt",
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied
        captivity = Captivity.objects.get(captive=sheet)
        assert captivity.cell.room.db_key == "The Blood Crypt"

    def test_capture_plants_a_rescue_clue_at_the_capture_site(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.clues.constants import ClueTargetKind
        from world.clues.models import RoomClue
        from world.missions.factories import MissionTemplateFactory

        room_profile = RoomProfileFactory()
        character = CharacterFactory(db_key="rescue_clue_target")
        sheet = CharacterSheetFactory(character=character)
        character.move_to(room_profile.objectdb, quiet=True)
        rescue_template = MissionTemplateFactory(name="rescue-clue-tmpl")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
            capture_rescue_template=rescue_template,
            capture_clue_name="Signs of a struggle",
            capture_clue_description="PLACEHOLDER",
            capture_clue_detect_difficulty=2,
        )

        result = apply_effect(effect, ResolutionContext(character=character))

        assert result.applied
        captivity = Captivity.objects.get(captive=sheet)
        assert captivity.rescue_template == rescue_template
        placement = RoomClue.objects.get(room_profile=room_profile)
        assert placement.clue.target_kind == ClueTargetKind.RESCUE
        assert placement.clue.target_captivity == captivity
        assert placement.detect_difficulty == 2

    def test_capture_grants_the_captive_their_loop(self) -> None:
        # With a captive template on the effect (override-then-default), the
        # captured character is handed their own escape + get-word-out run.
        character, _sheet = self._captive_at_site("looped_target")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
            capture_captive_template=_captive_loop_template("cell-loop"),
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied
        instance = MissionInstance.objects.get(template__name="cell-loop")
        assert instance.participants.filter(
            character=character,
            is_contract_holder=True,
        ).exists()

    def test_capture_without_a_template_grants_no_loop(self) -> None:
        # No template authored anywhere → capture still stands, no run created.
        character, _ = self._captive_at_site("loopless_target")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied
        assert MissionInstance.objects.count() == 0

    def test_capture_skips_without_sheet(self) -> None:
        bare = CharacterFactory(db_key="no_sheet_capture")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
        )
        context = ResolutionContext(character=bare)

        result = apply_effect(effect, context)

        assert result.applied is False
        assert result.skip_reason is not None
        assert Captivity.objects.count() == 0

    def test_capture_skips_when_already_held(self) -> None:
        character, sheet = self._captive_at_site("double_capture")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
        )
        context = ResolutionContext(character=character)
        apply_effect(effect, context)

        result = apply_effect(effect, context)

        assert result.applied is False
        assert result.skip_reason is not None
        assert Captivity.objects.filter(captive=sheet).count() == 1


class CaptureGroupingTests(TestCase):
    """The CAPTURE handler groups captives of one encounter into a shared cell (#982)."""

    @staticmethod
    def _capture_effect():
        return ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
        )

    def _capture(self, key: str, *, scene):
        character = CharacterFactory(db_key=key)
        sheet = CharacterSheetFactory(character=character)
        apply_effect(self._capture_effect(), ResolutionContext(character=character, scene=scene))
        return Captivity.objects.get(captive=sheet)

    def test_same_scene_captures_share_a_cell(self) -> None:
        scene = SceneFactory()

        first = self._capture("grp_same_a", scene=scene)
        second = self._capture("grp_same_b", scene=scene)

        assert first.cell_id == second.cell_id

    def test_different_scenes_do_not_share(self) -> None:
        first = self._capture("grp_diff_a", scene=SceneFactory())
        second = self._capture("grp_diff_b", scene=SceneFactory())

        assert first.cell_id != second.cell_id

    def test_no_scene_uses_separate_cells(self) -> None:
        first = self._capture("grp_none_a", scene=None)
        second = self._capture("grp_none_b", scene=None)

        assert first.cell_id != second.cell_id


class CaptureBrigRoutingTests(TestCase):
    """Tests for CAPTURE effect routing to a ship's Brig (#1862)."""

    @staticmethod
    def _capture_effect():
        return ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.CAPTURE,
        )

    def _make_brig_in_building(self):
        """Create a building with a Brig room feature; return (brig_room, building)."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.areas.factories import AreaFactory
        from world.buildings.factories import BuildingFactory
        from world.room_features.constants import (
            BRIG_CAPACITY_PER_LEVEL,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.factories import RoomFeatureKindFactory
        from world.room_features.models import BrigDetails

        area = AreaFactory(level=10)
        building = BuildingFactory(area=area)
        brig_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        brig_profile = RoomProfileFactory(objectdb=brig_room, area=area)
        kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.BRIG,
        )
        from world.room_features.models import RoomFeatureInstance

        instance = RoomFeatureInstance.objects.create(
            room_profile=brig_profile,
            feature_kind=kind,
            level=1,
        )
        BrigDetails.objects.create(
            feature_instance=instance,
            max_prisoners=BRIG_CAPACITY_PER_LEVEL,
        )
        return brig_room, building

    def test_capture_routes_to_brig_when_available(self) -> None:
        brig_room, building = self._make_brig_in_building()
        # The captor stands in a room of the same building.
        captor_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        from evennia_extensions.factories import RoomProfileFactory

        RoomProfileFactory(objectdb=captor_room, area=building.area)
        character = CharacterFactory(db_key="brig_captive")
        sheet = CharacterSheetFactory(character=character)
        character.move_to(captor_room, quiet=True)

        result = apply_effect(self._capture_effect(), ResolutionContext(character=character))

        assert result.applied
        sheet.refresh_from_db()
        assert sheet.lifecycle_state == LifecycleState.CAPTURED
        captivity = Captivity.objects.get(captive=sheet)
        assert captivity.cell is None
        assert captivity.holding_room == brig_room
        assert character.location == brig_room

    def test_capture_falls_back_to_instanced_cell_when_no_brig(self) -> None:
        # No Brig in the building — falls back to the instanced-cell path.
        from evennia_extensions.factories import RoomProfileFactory
        from world.areas.factories import AreaFactory
        from world.buildings.factories import BuildingFactory

        area = AreaFactory(level=10)
        BuildingFactory(area=area)
        captor_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        RoomProfileFactory(objectdb=captor_room, area=area)
        character = CharacterFactory(db_key="no_brig_captive")
        sheet = CharacterSheetFactory(character=character)
        character.move_to(captor_room, quiet=True)

        result = apply_effect(self._capture_effect(), ResolutionContext(character=character))

        assert result.applied
        captivity = Captivity.objects.get(captive=sheet)
        assert captivity.cell is not None
        assert captivity.holding_room is None

    def test_capture_skipped_when_brig_at_capacity(self) -> None:
        brig_room, building = self._make_brig_in_building()
        # Fill the Brig to capacity (BRIG_CAPACITY_PER_LEVEL = 2).
        from evennia_extensions.factories import RoomProfileFactory

        for i in range(2):
            c = CharacterFactory(db_key=f"filler_{i}")
            s = CharacterSheetFactory(character=c)
            capture_character(captive=s, holding_room=brig_room)

        # Now try to capture a third.
        captor_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        RoomProfileFactory(objectdb=captor_room, area=building.area)
        character = CharacterFactory(db_key="overflow_captive")
        sheet = CharacterSheetFactory(character=character)
        character.move_to(captor_room, quiet=True)

        result = apply_effect(self._capture_effect(), ResolutionContext(character=character))

        assert result.applied is False
        assert result.skip_reason == "Brig at capacity"
        assert not Captivity.objects.filter(captive=sheet).exists()


class GrantDistinctionHandlerTests(TestCase):
    """Tests for the GRANT_DISTINCTION effect handler (#2037 Decision 7).

    Mirrors the ADD_PROPERTY handler's shape: this suite proves the seam (dispatch,
    authored fields, skip paths) — full grant/rank-up mechanics live in
    world.distinctions.tests.test_services.
    """

    def _character_with_sheet(self, key: str):
        character = CharacterFactory(db_key=key)
        sheet = CharacterSheetFactory(character=character)
        return character, sheet

    def test_grant_distinction_grants_the_distinction(self) -> None:
        character, _sheet = self._character_with_sheet("grant_dist_target")
        distinction = DistinctionFactory(name="Silver Tongue_eff", max_rank=3)
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.GRANT_DISTINCTION,
            distinction=distinction,
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied is True
        cd = CharacterDistinction.objects.get(
            character=character.sheet_data, distinction=distinction
        )
        assert cd.rank == 1
        assert cd.origin == DistinctionOrigin.CONSEQUENCE_POOL

    def test_null_distinction_rank_steps_the_rank(self) -> None:
        character, _sheet = self._character_with_sheet("grant_dist_step")
        distinction = DistinctionFactory(name="Silver Tongue_step", max_rank=3)
        CharacterDistinctionFactory(character=character.sheet_data, distinction=distinction, rank=1)
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.GRANT_DISTINCTION,
            distinction=distinction,
            distinction_rank=None,
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied is True
        cd = CharacterDistinction.objects.get(
            character=character.sheet_data, distinction=distinction
        )
        assert cd.rank == 2

    def test_explicit_distinction_rank_sets_that_rank(self) -> None:
        character, _sheet = self._character_with_sheet("grant_dist_explicit")
        distinction = DistinctionFactory(name="Silver Tongue_explicit", max_rank=5)
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.GRANT_DISTINCTION,
            distinction=distinction,
            distinction_rank=3,
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied is True
        cd = CharacterDistinction.objects.get(
            character=character.sheet_data, distinction=distinction
        )
        assert cd.rank == 3

    def test_grant_distinction_skips_without_sheet(self) -> None:
        bare = CharacterFactory(db_key="no_sheet_grant_dist")
        distinction = DistinctionFactory(name="Silver Tongue_nosheet")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.GRANT_DISTINCTION,
            distinction=distinction,
        )
        context = ResolutionContext(character=bare)

        result = apply_effect(effect, context)

        assert result.applied is False
        assert result.skip_reason
        assert not CharacterDistinction.objects.filter(distinction=distinction).exists()

    def test_exclusion_conflict_skips_without_crashing(self) -> None:
        character, _sheet = self._character_with_sheet("grant_dist_conflict")
        alpha = DistinctionFactory(name="Alpha_eff")
        beta = DistinctionFactory(name="Beta_eff")
        alpha.mutually_exclusive_with.add(beta)
        CharacterDistinctionFactory(character=character.sheet_data, distinction=alpha, rank=1)
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.GRANT_DISTINCTION,
            distinction=beta,
        )
        context = ResolutionContext(character=character)

        result = apply_effect(effect, context)

        assert result.applied is False
        assert result.skip_reason
        assert not CharacterDistinction.objects.filter(
            character=character.sheet_data, distinction=beta
        ).exists()


class EscapeCaptivityHandlerTests(TestCase):
    """The ESCAPE_CAPTIVITY effect frees the target from their own captivity (#931)."""

    def _effect(self):
        return ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.ESCAPE_CAPTIVITY,
        )

    def test_escape_frees_a_held_captive(self) -> None:
        character = CharacterFactory(db_key="escapee")
        sheet = CharacterSheetFactory(character=character)
        capture_character(captive=sheet)

        result = apply_effect(self._effect(), ResolutionContext(character=character))

        assert result.applied
        sheet.refresh_from_db()
        assert sheet.lifecycle_state == LifecycleState.ALIVE
        captivity = Captivity.objects.get(captive=sheet)
        assert captivity.status == CaptivityStatus.ESCAPED

    def test_escape_skips_when_target_not_held(self) -> None:
        character = CharacterFactory(db_key="free_already")
        CharacterSheetFactory(character=character)

        result = apply_effect(self._effect(), ResolutionContext(character=character))

        assert result.applied is False
        assert result.skip_reason is not None

    def test_escape_skips_without_sheet(self) -> None:
        bare = CharacterFactory(db_key="no_sheet_escape")

        result = apply_effect(self._effect(), ResolutionContext(character=bare))

        assert result.applied is False
        assert result.skip_reason is not None


class RescueCaptiveHandlerTests(TestCase):
    """The RESCUE_CAPTIVE effect frees the run's rescue_target (#931 Phase 4)."""

    def _effect(self):
        return ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.RESCUE_CAPTIVE,
        )

    def _rescue_instance(self, captive_sheet):
        rescuer = CharacterFactory(db_key="rescuer")
        CharacterSheetFactory(character=rescuer)
        template = _captive_loop_template("rescue-run")
        return rescuer, grant_rescue_mission(template, rescuer, captive_sheet)

    def test_rescue_frees_the_runs_target(self) -> None:
        captive = CharacterSheetFactory()
        capture_character(captive=captive)
        rescuer, instance = self._rescue_instance(captive)

        result = apply_effect(
            self._effect(),
            ResolutionContext(character=rescuer, mission_instance=instance),
        )

        assert result.applied
        captive.refresh_from_db()
        assert captive.lifecycle_state == LifecycleState.ALIVE
        captivity = Captivity.objects.get(captive=captive)
        assert captivity.status == CaptivityStatus.RESCUED

    def test_rescue_skips_off_the_mission_path(self) -> None:
        # No mission_instance on the context (e.g. a non-mission resolution).
        rescuer = CharacterFactory(db_key="lone_rescuer")
        CharacterSheetFactory(character=rescuer)

        result = apply_effect(self._effect(), ResolutionContext(character=rescuer))

        assert result.applied is False
        assert result.skip_reason is not None

    def test_rescue_skips_when_target_not_held(self) -> None:
        # A rescue run whose target was already freed before the route fired.
        captive = CharacterSheetFactory()
        rescuer, instance = self._rescue_instance(captive)

        result = apply_effect(
            self._effect(),
            ResolutionContext(character=rescuer, mission_instance=instance),
        )

        assert result.applied is False
        assert result.skip_reason is not None


class ApplyConditionSourceCharacterTests(TestCase):
    """source_character on ResolutionContext is forwarded to ConditionInstance (#1479 Task 1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.victim = CharacterFactory(db_key="condition_victim")
        cls.attacker = CharacterFactory(db_key="condition_attacker")
        cls.condition_template = ConditionTemplateFactory()
        cls.effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=cls.condition_template,
        )

    def test_source_character_is_stored_on_condition_instance(self) -> None:
        """When context.source_character is set, the created ConditionInstance carries it."""
        context = ResolutionContext(
            character=self.victim,
            source_character=self.attacker,
        )

        result = apply_effect(self.effect, context)

        assert result.applied is True
        instance = ConditionInstance.objects.get(
            target=self.victim,
            condition=self.condition_template,
        )
        assert instance.source_character == self.attacker

    def test_source_character_none_when_not_provided(self) -> None:
        """When context.source_character is None, ConditionInstance.source_character is None."""
        context = ResolutionContext(character=self.victim)

        result = apply_effect(self.effect, context)

        assert result.applied is True
        instance = ConditionInstance.objects.get(
            target=self.victim,
            condition=self.condition_template,
        )
        assert instance.source_character is None
