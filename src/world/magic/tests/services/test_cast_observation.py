"""Cast observation — style concealment and per-observer detection (#2710)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia import create_object
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.models import CheckType
from world.classes.factories import CharacterClassLevelFactory, PathFactory
from world.magic.constants import DETECT_CAST_CHECK_NAME, TechniqueReach
from world.magic.factories import GiftFactory, TechniqueFactory, TechniqueStyleFactory
from world.magic.models import Technique
from world.magic.services.cast_observation import resolve_cast_audience
from world.progression.models import CharacterPathHistory
from world.scenes.models import Persona
from world.scenes.services import active_persona_for_sheet
from world.traits.factories import CheckSystemSetupFactory


class CastConcealmentFieldTests(TestCase):
    """The content-authored dial on TechniqueStyle."""

    def test_style_defaults_to_no_concealment(self) -> None:
        """Every existing style is overt until content says otherwise."""
        style = TechniqueStyleFactory(name="Manifestation")
        self.assertEqual(style.cast_concealment, 0)

    def test_style_stores_an_authored_concealment_rating(self) -> None:
        """Concealment is a magnitude, not a flag."""
        style = TechniqueStyleFactory(name="Subtle", cast_concealment=25)
        style.refresh_from_db()
        self.assertEqual(style.cast_concealment, 25)


# ---------------------------------------------------------------------------
# Fixture helpers — module level per the task-3 brief.
#
# Follows world/scenes/tests/cast_test_helpers.py's pattern (evennia.create_object
# for the room; CheckSystemSetupFactory.create() for the check-resolution scaffold)
# and world/magic/factories.py's TechniqueStyleFactory. CharacterSheetFactory's own
# post-generation hook auto-creates the PRIMARY Persona for each sheet (see
# world/character_sheets/factories.py), so no separate PersonaFactory call is needed
# here — active_persona_for_sheet falls back to it.
# ---------------------------------------------------------------------------


def _caster_on_path_with_style(*, cast_concealment: int, level: int = 1) -> ObjectDB:
    """A character, physically in a room, on a Path whose style carries concealment.

    Builds a CharacterFactory character placed in a fresh room, its CharacterSheet
    (which auto-creates the PRIMARY Persona), a Path carrying a TechniqueStyle with
    the given cast_concealment, a CharacterPathHistory row so
    current_path_for_character resolves it, a CharacterClassLevel at `level` so
    get_character_path_level resolves it, and the "Perception" CheckType via the
    shared check-resolution scaffold.
    """
    room = create_object("typeclasses.rooms.Room", key="Cast Observation Room", nohome=True)
    caster = CharacterFactory()
    caster.location = room
    caster.save()
    sheet = CharacterSheetFactory(character=caster)
    style = TechniqueStyleFactory(cast_concealment=cast_concealment)
    path = PathFactory(style=style)
    CharacterPathHistory.objects.create(character=sheet, path=path)
    CharacterClassLevelFactory(character=sheet, level=level, is_primary=True)
    CheckSystemSetupFactory.create()
    CheckTypeFactory(name=DETECT_CAST_CHECK_NAME)
    return caster


def _observer_in_room_with(caster: ObjectDB) -> ObjectDB:
    """A sheet-bearing character standing in the same room as `caster`."""
    observer = CharacterFactory()
    observer.location = caster.location
    observer.save()
    CharacterSheetFactory(character=observer)
    return observer


def _ranged_technique(*, has_perceptible_effect: bool = True) -> Technique:
    """A concealable working: worked at range, so contact never gives the caster away."""
    return TechniqueFactory(reach=TechniqueReach.ANY, has_perceptible_effect=has_perceptible_effect)


def _persona_of(character: ObjectDB) -> Persona:
    """The persona resolve_cast_audience would attribute this character's cast to."""
    return active_persona_for_sheet(character.sheet_data)


def _check_result_with_success_level(level: int) -> MagicMock:
    """A stub CheckResult carrying only the attribute resolve_cast_audience reads."""
    result = MagicMock()
    result.success_level = level
    return result


@contextmanager
def _forced_success_level(level: int) -> Iterator[MagicMock]:
    """Patch the service's own perform_check to always return `level`.

    Must patch world.magic.services.cast_observation.perform_check — the name as
    imported into the service's own module namespace — not world.checks.services.
    """
    with patch("world.magic.services.cast_observation.perform_check_with_modifiers") as rolled:
        rolled.return_value = _check_result_with_success_level(level)
        yield rolled


class ResolveCastAudienceTests(TestCase):
    """Who perceived the cast, and at what detail."""

    def test_zero_concealment_returns_unconcealed_without_rolling(self) -> None:
        """The hot path: an overt style runs no detection check at all.

        Patches the service's OWN bound name (not world.checks.services — that patch
        target can never intercept the call, since the service imports the name into
        its own module namespace) and puts an observer in the room, so the assertion
        actually discriminates: with the early return deleted, there would be somebody
        for perform_check to be called on.
        """
        caster = _caster_on_path_with_style(cast_concealment=0)
        _observer_in_room_with(caster)
        with patch("world.magic.services.cast_observation.perform_check_with_modifiers") as rolled:
            audience = resolve_cast_audience(caster=caster, technique=_ranged_technique())
        self.assertFalse(audience.concealed)
        rolled.assert_not_called()

    def test_contact_range_technique_is_never_concealed(self) -> None:
        """You have to be standing on someone to stab or touch them (#2734).

        Checked before the style lookup, so a melee action on a maximally concealed
        caster costs neither the path query nor a roll per observer.
        """
        caster = _caster_on_path_with_style(cast_concealment=25)
        _observer_in_room_with(caster)
        melee = TechniqueFactory(reach=TechniqueReach.SAME)
        with patch("world.magic.services.cast_observation.perform_check_with_modifiers") as rolled:
            audience = resolve_cast_audience(caster=caster, technique=melee)
        self.assertFalse(audience.concealed)
        rolled.assert_not_called()

    def test_no_path_is_treated_as_overt(self) -> None:
        """Pathless characters and NPCs behave exactly as they do today."""
        caster = CharacterFactory()
        audience = resolve_cast_audience(caster=caster, technique=_ranged_technique())
        self.assertFalse(audience.concealed)

    def test_cast_openly_waives_concealment(self) -> None:
        caster = _caster_on_path_with_style(cast_concealment=25)
        audience = resolve_cast_audience(
            caster=caster, technique=_ranged_technique(), cast_openly=True
        )
        self.assertFalse(audience.concealed)

    def test_caster_always_perceives_their_own_cast(self) -> None:
        caster = _caster_on_path_with_style(cast_concealment=25)
        audience = resolve_cast_audience(caster=caster, technique=_ranged_technique())
        self.assertTrue(audience.concealed)
        self.assertIn(_persona_of(caster), audience.full)

    def test_strong_detection_lands_in_full(self) -> None:
        caster = _caster_on_path_with_style(cast_concealment=25)
        observer = _observer_in_room_with(caster)
        with _forced_success_level(2):
            audience = resolve_cast_audience(caster=caster, technique=_ranged_technique())
        self.assertIn(_persona_of(observer), audience.full)
        self.assertNotIn(_persona_of(observer), audience.vague)
        self.assertNotIn(_persona_of(observer), audience.effect_only)

    def test_marginal_detection_lands_in_vague(self) -> None:
        caster = _caster_on_path_with_style(cast_concealment=25)
        observer = _observer_in_room_with(caster)
        with _forced_success_level(1):
            audience = resolve_cast_audience(caster=caster, technique=_ranged_technique())
        self.assertIn(_persona_of(observer), audience.vague)
        self.assertNotIn(_persona_of(observer), audience.full)
        self.assertNotIn(_persona_of(observer), audience.effect_only)

    def test_failed_detection_still_sees_what_happened(self) -> None:
        """The rework in one test: concealment hides attribution, not the event.

        Pre-#2734 this observer landed in no tier at all and the cast vanished from
        their feed — which in combat meant taking a wound with nothing to explain it.
        """
        caster = _caster_on_path_with_style(cast_concealment=25)
        observer = _observer_in_room_with(caster)
        with _forced_success_level(0):
            audience = resolve_cast_audience(caster=caster, technique=_ranged_technique())
        persona = _persona_of(observer)
        self.assertIn(persona, audience.effect_only)
        self.assertNotIn(persona, audience.full)
        self.assertNotIn(persona, audience.vague)

    def test_imperceptible_working_hides_outright_from_a_failed_roll(self) -> None:
        """The one case that still vanishes: nothing happened that anyone could see."""
        caster = _caster_on_path_with_style(cast_concealment=25)
        observer = _observer_in_room_with(caster)
        technique = _ranged_technique(has_perceptible_effect=False)
        with _forced_success_level(0):
            audience = resolve_cast_audience(caster=caster, technique=technique)
        persona = _persona_of(observer)
        self.assertNotIn(persona, audience.effect_only)
        self.assertNotIn(persona, audience.full)
        self.assertNotIn(persona, audience.vague)

    def test_difficulty_includes_the_casters_level_opposition(self) -> None:
        """Concealment is a floor; the caster's level is added on top (ADR-0166)."""
        caster = _caster_on_path_with_style(cast_concealment=25, level=4)
        _observer_in_room_with(caster)
        with (
            patch("world.magic.services.cast_observation.perform_check_with_modifiers") as rolled,
            patch("world.magic.services.cast_observation.level_opposition", return_value=20),
        ):
            rolled.return_value = _check_result_with_success_level(0)
            resolve_cast_audience(caster=caster, technique=_ranged_technique())
        self.assertEqual(rolled.call_args.kwargs["target_difficulty"], 45)

    def test_missing_detection_check_type_fails_closed_on_attribution_only(self) -> None:
        """ADR-0033: a misconfiguration must never leak *who cast it*.

        It must also not erase the event. Before #2734 an unauthored detection
        CheckType blinded the whole room, which in combat meant every participant's
        feed silently dropped the action.
        """
        caster = _caster_on_path_with_style(cast_concealment=25)
        observer = _observer_in_room_with(caster)
        CheckType.objects.filter(name=DETECT_CAST_CHECK_NAME).delete()
        audience = resolve_cast_audience(caster=caster, technique=_ranged_technique())
        self.assertTrue(audience.concealed)
        self.assertNotIn(_persona_of(observer), audience.full)
        self.assertNotIn(_persona_of(observer), audience.vague)
        self.assertIn(_persona_of(observer), audience.effect_only)

    def test_missing_check_type_hides_an_imperceptible_working_entirely(self) -> None:
        """Fail-closed keeps its old shape where there is genuinely nothing to see."""
        caster = _caster_on_path_with_style(cast_concealment=25)
        _observer_in_room_with(caster)
        CheckType.objects.filter(name=DETECT_CAST_CHECK_NAME).delete()
        audience = resolve_cast_audience(
            caster=caster, technique=_ranged_technique(has_perceptible_effect=False)
        )
        self.assertTrue(audience.concealed)
        self.assertEqual(audience.effect_only, [])

    def test_gift_style_concealment_overrides_caster_path_style(self) -> None:
        """A gift the character didn't choose sets its own casting manner (#2905)."""
        caster = _caster_on_path_with_style(cast_concealment=5)
        _observer_in_room_with(caster)
        gift_style = TechniqueStyleFactory(cast_concealment=25)
        technique = TechniqueFactory(reach=TechniqueReach.ANY, gift=GiftFactory(style=gift_style))
        with (
            patch("world.magic.services.cast_observation.perform_check_with_modifiers") as rolled,
            patch("world.magic.services.cast_observation.level_opposition", return_value=0),
        ):
            rolled.return_value = _check_result_with_success_level(0)
            resolve_cast_audience(caster=caster, technique=technique)
        self.assertEqual(rolled.call_args.kwargs["target_difficulty"], 25)

    def test_null_gift_style_falls_back_to_caster_path_style(self) -> None:
        """A gift that doesn't opt in keeps today's caster-derived behavior exactly (#2905)."""
        caster = _caster_on_path_with_style(cast_concealment=25)
        _observer_in_room_with(caster)
        technique = _ranged_technique()  # gift.style is unset (None) by default
        with (
            patch("world.magic.services.cast_observation.perform_check_with_modifiers") as rolled,
            patch("world.magic.services.cast_observation.level_opposition", return_value=0),
        ):
            rolled.return_value = _check_result_with_success_level(0)
            resolve_cast_audience(caster=caster, technique=technique)
        self.assertEqual(rolled.call_args.kwargs["target_difficulty"], 25)
