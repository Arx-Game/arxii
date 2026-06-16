"""Tests for effect handlers in the mechanics app."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from world.captivity.constants import CaptivityStatus
from world.captivity.models import Captivity
from world.captivity.services import capture_character
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.conditions.factories import DamageTypeFactory
from world.mechanics.effect_handlers import _resolve_target, apply_effect
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance
from world.scenes.factories import SceneFactory
from world.societies.factories import OrganizationFactory
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
        cls.site = ObjectDB.objects.create(
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
