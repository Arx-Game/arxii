"""Tests for Task 6 (#2993): SetLanguageAction, TrainLanguageAction, per-say tag parse."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.language import (
    SELF_STUDY_DP_PER_SESSION,
    TEACHER_DP_PER_SESSION,
    SetLanguageAction,
    TrainLanguageAction,
)
from commands.evennia_overrides.communication import CmdSay
from commands.exceptions import CommandError
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.models.rewards import DevelopmentPoints, DevelopmentTransaction
from world.progression.types import DevelopmentSource
from world.species.factories import LanguageFactory
from world.traits.models import CharacterTraitValue, Trait, TraitCategory, TraitType


def _make_room():
    return ObjectDBFactory(db_key="LanguageActionRoom", db_typeclass_path="typeclasses.rooms.Room")


def _make_cmd(cls, caller, args=""):
    """Mirror commands/tests/test_dispatchers.py's `_make_cmd` helper."""
    cmd = cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd.key} {args}"
    cmd.cmdname = cmd.key
    return cmd


class LanguageActionTestCase(TestCase):
    """Shared fixture: a language with a real LANGUAGE trait, a sheeted-character helper."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.trait = Trait.objects.create(
            name="Task6TestTongue",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.language = LanguageFactory(name="Task6TestTongue", trait=cls.trait)

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def _sheeted_character(self, room, *, key, fluency=None):
        character = CharacterFactory(db_key=key, location=room)
        sheet = CharacterSheetFactory(character=character)
        if fluency is not None:
            CharacterTraitValue.objects.create(character=sheet, trait=self.trait, value=fluency)
        return character, sheet


class SetLanguageActionTests(LanguageActionTestCase):
    def test_happy_path_sets_current_language(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Speaker", fluency=50)

        result = SetLanguageAction().run(speaker, language_id=self.language.pk)

        assert result.success is True
        assert result.message == f"You will now speak {self.language.name}."
        sheet.refresh_from_db()
        assert sheet.current_language_id == self.language.pk

    def test_unknown_language_id_rejected(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Speaker", fluency=50)

        result = SetLanguageAction().run(speaker, language_id=999999)

        assert result.success is False
        assert result.message == "You don't know that tongue."
        sheet.refresh_from_db()
        assert sheet.current_language_id is None

    def test_no_fluency_rejected(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Speaker")

        result = SetLanguageAction().run(speaker, language_id=self.language.pk)

        assert result.success is False
        assert result.message == "You don't know that tongue."
        sheet.refresh_from_db()
        assert sheet.current_language_id is None

    def test_omitted_language_id_resets_to_universal(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Speaker", fluency=50)
        sheet.current_language = self.language
        sheet.save(update_fields=["current_language"])

        result = SetLanguageAction().run(speaker)

        assert result.success is True
        assert result.message == "You will now speak the universal tongue."
        sheet.refresh_from_db()
        assert sheet.current_language_id is None


class TrainLanguageActionTests(LanguageActionTestCase):
    def test_self_study_awards_practice_amount(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Student")

        result = TrainLanguageAction().run(speaker, language_id=self.language.pk)

        assert result.success is True
        assert result.data["amount"] == SELF_STUDY_DP_PER_SESSION
        assert result.data["self_study"] is True
        dev = DevelopmentPoints.objects.get(character_sheet=sheet, trait=self.trait)
        assert dev.total_earned == SELF_STUDY_DP_PER_SESSION
        txn = DevelopmentTransaction.objects.get(character_sheet=sheet, trait=self.trait)
        assert txn.source == DevelopmentSource.PRACTICE
        assert txn.amount == SELF_STUDY_DP_PER_SESSION

    def test_fluent_co_located_teacher_awards_training_amount(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Student")
        teacher, _teacher_sheet = self._sheeted_character(room, key="Teacher", fluency=100)

        result = TrainLanguageAction().run(
            speaker, language_id=self.language.pk, teacher_id=teacher.pk
        )

        assert result.success is True
        assert result.data["amount"] == TEACHER_DP_PER_SESSION
        assert result.data["self_study"] is False
        dev = DevelopmentPoints.objects.get(character_sheet=sheet, trait=self.trait)
        assert dev.total_earned == TEACHER_DP_PER_SESSION
        txn = DevelopmentTransaction.objects.get(character_sheet=sheet, trait=self.trait)
        assert txn.source == DevelopmentSource.TRAINING
        assert txn.amount == TEACHER_DP_PER_SESSION

    def test_teacher_not_fluent_falls_back_to_self_study(self) -> None:
        room = _make_room()
        speaker, _sheet = self._sheeted_character(room, key="Student")
        teacher, _teacher_sheet = self._sheeted_character(room, key="Teacher", fluency=10)

        result = TrainLanguageAction().run(
            speaker, language_id=self.language.pk, teacher_id=teacher.pk
        )

        assert result.success is True
        assert result.data["self_study"] is True
        assert result.data["amount"] == SELF_STUDY_DP_PER_SESSION

    def test_teacher_not_co_present_falls_back_to_self_study(self) -> None:
        room = _make_room()
        elsewhere = ObjectDBFactory(
            db_key="ElsewhereRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        speaker, _sheet = self._sheeted_character(room, key="Student")
        teacher, _teacher_sheet = self._sheeted_character(elsewhere, key="Teacher", fluency=100)

        result = TrainLanguageAction().run(
            speaker, language_id=self.language.pk, teacher_id=teacher.pk
        )

        assert result.success is True
        assert result.data["self_study"] is True

    def test_second_session_same_week_fails(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Student")

        first = TrainLanguageAction().run(speaker, language_id=self.language.pk)
        second = TrainLanguageAction().run(speaker, language_id=self.language.pk)

        assert first.success is True
        assert second.success is False
        assert second.message == f"You've already studied {self.language.name} this week."
        dev = DevelopmentPoints.objects.get(character_sheet=sheet, trait=self.trait)
        # Only the first session's dp landed.
        assert dev.total_earned == SELF_STUDY_DP_PER_SESSION

    def test_teacher_and_self_study_sessions_both_gate_on_the_same_week(self) -> None:
        """PRACTICE and TRAINING share one weekly slot per (sheet, trait)."""
        room = _make_room()
        speaker, _sheet = self._sheeted_character(room, key="Student")
        teacher, _teacher_sheet = self._sheeted_character(room, key="Teacher", fluency=100)

        first = TrainLanguageAction().run(speaker, language_id=self.language.pk)
        second = TrainLanguageAction().run(
            speaker, language_id=self.language.pk, teacher_id=teacher.pk
        )

        assert first.success is True
        assert second.success is False

    def test_unknown_language_id_rejected(self) -> None:
        room = _make_room()
        speaker, _sheet = self._sheeted_character(room, key="Student")

        result = TrainLanguageAction().run(speaker, language_id=999999)

        assert result.success is False
        assert result.message == "There is no such language."

    def test_level_up_crossing_raises_character_trait_value(self) -> None:
        """A session that crosses a dp threshold levels the fluency trait up."""
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Student")
        teacher, _teacher_sheet = self._sheeted_character(room, key="Teacher", fluency=100)
        # 93 + TEACHER_DP_PER_SESSION (15) = 108 >= cumulative_dp_for_level(11) (100).
        DevelopmentPoints.objects.create(character_sheet=sheet, trait=self.trait, total_earned=93)

        result = TrainLanguageAction().run(
            speaker, language_id=self.language.pk, teacher_id=teacher.pk
        )

        assert result.success is True
        assert result.data["level_ups"] == [(10, 11)]
        trait_value = CharacterTraitValue.objects.get(character=sheet, trait=self.trait)
        assert trait_value.value == 11
        assert "fluency deepens to 11" in result.message


class RestrictedTrainLanguageActionTests(TestCase):
    """Restricted tongues (#3162): teacher can bootstrap from zero, self-study cannot."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.trait = Trait.objects.create(
            name="RestrictedTestTongue",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.language = LanguageFactory(
            name="RestrictedTestTongue", trait=cls.trait, restricted=True
        )

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def _sheeted_character(self, room, *, key, fluency=None):
        character = CharacterFactory(db_key=key, location=room)
        sheet = CharacterSheetFactory(character=character)
        if fluency is not None:
            CharacterTraitValue.objects.create(character=sheet, trait=self.trait, value=fluency)
        return character, sheet

    def test_zero_fluency_no_teacher_fails(self) -> None:
        room = _make_room()
        speaker, _sheet = self._sheeted_character(room, key="Student")

        result = TrainLanguageAction().run(speaker, language_id=self.language.pk)

        assert result.success is False
        assert result.message == (
            f"No one can teach you {self.language.name}, and it is not a tongue "
            "you can puzzle out alone."
        )

    def test_zero_fluency_with_fluent_teacher_succeeds_at_training_rate(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Student")
        teacher, _teacher_sheet = self._sheeted_character(room, key="Teacher", fluency=100)

        result = TrainLanguageAction().run(
            speaker, language_id=self.language.pk, teacher_id=teacher.pk
        )

        assert result.success is True
        assert result.data["amount"] == TEACHER_DP_PER_SESSION
        assert result.data["self_study"] is False
        dev = DevelopmentPoints.objects.get(character_sheet=sheet, trait=self.trait)
        assert dev.total_earned == TEACHER_DP_PER_SESSION
        txn = DevelopmentTransaction.objects.get(character_sheet=sheet, trait=self.trait)
        assert txn.source == DevelopmentSource.TRAINING

    def test_existing_fluency_self_study_succeeds_at_practice_rate(self) -> None:
        room = _make_room()
        speaker, sheet = self._sheeted_character(room, key="Student", fluency=1)

        result = TrainLanguageAction().run(speaker, language_id=self.language.pk)

        assert result.success is True
        assert result.data["amount"] == SELF_STUDY_DP_PER_SESSION
        assert result.data["self_study"] is True
        dev = DevelopmentPoints.objects.get(character_sheet=sheet, trait=self.trait)
        assert dev.total_earned == SELF_STUDY_DP_PER_SESSION
        txn = DevelopmentTransaction.objects.get(character_sheet=sheet, trait=self.trait)
        assert txn.source == DevelopmentSource.PRACTICE

    def test_unrestricted_language_self_study_from_zero_still_succeeds(self) -> None:
        """Regression: unrestricted behavior is byte-identical to pre-#3162."""
        room = _make_room()
        unrestricted_trait = Trait.objects.create(
            name="UnrestrictedTestTongue",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        unrestricted_language = LanguageFactory(
            name="UnrestrictedTestTongue", trait=unrestricted_trait, restricted=False
        )
        speaker = CharacterFactory(db_key="Student", location=room)
        CharacterSheetFactory(character=speaker)

        result = TrainLanguageAction().run(speaker, language_id=unrestricted_language.pk)

        assert result.success is True
        assert result.data["amount"] == SELF_STUDY_DP_PER_SESSION
        assert result.data["self_study"] is True


class CmdSayLanguageTagTests(TestCase):
    """Unit tests for CmdSay.resolve_action_args' per-say language tag (#2993)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.trait = Trait.objects.create(
            name="Task6TagTongue",
            trait_type=TraitType.LANGUAGE,
            category=TraitCategory.GENERAL,
        )
        cls.language = LanguageFactory(name="Task6TagTongue", trait=cls.trait)

    def test_tag_resolves_language_id_and_strips_tag(self) -> None:
        room = _make_room()
        caller = ObjectDBFactory(
            db_key="Tagger",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        cmd = _make_cmd(CmdSay, caller, args=f" ({self.language.name}) hello there")

        kwargs = cmd.resolve_action_args()

        assert kwargs["language_id"] == self.language.pk
        assert kwargs["text"] == "hello there"

    def test_unknown_tongue_tag_raises_naming_it(self) -> None:
        room = _make_room()
        caller = ObjectDBFactory(
            db_key="Tagger",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        cmd = _make_cmd(CmdSay, caller, args=" (Nonexistentia) hello there")

        with self.assertRaises(CommandError) as ctx:
            cmd.resolve_action_args()
        assert "Nonexistentia" in str(ctx.exception)

    def test_no_tag_leaves_kwargs_unchanged(self) -> None:
        room = _make_room()
        caller = ObjectDBFactory(
            db_key="Tagger",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        cmd = _make_cmd(CmdSay, caller, args=" hello there")

        kwargs = cmd.resolve_action_args()

        assert "language_id" not in kwargs
        assert kwargs["text"] == "hello there"
