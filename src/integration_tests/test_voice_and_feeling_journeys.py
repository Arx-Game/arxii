"""Journeys through feeling, speaking out of character and speaking a tongue (#3657, tranche 23).

Ysmay declares a mood nobody sees and Wren reads it with an earned empathy; Ysmay
steps out of character with ``ooc``; Ysmay speaks a tongue Hobb has and Bram has
not. Each journey types what a player types through the command handler (or sends
the web's own dispatch) and asserts what each of them was told and what the rows
hold.
"""

from __future__ import annotations

from actions.definitions.communication import OOC_USAGE
from actions.definitions.mood import MOOD_SENSE_CHECK_TYPE_NAME
from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import PlayerData
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory, MoodOptionFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
    UnconsciousConditionFactory,
)
from world.conditions.services import expire_scene_scoped_conditions
from world.mechanics.models import ModifierTarget
from world.progression.factories import DevelopmentPointsFactory
from world.progression.models import TraitRatingUnlock
from world.progression.models.rewards import (
    DevelopmentPoints,
    DevelopmentTransaction,
    cumulative_dp_for_level,
)
from world.progression.types import DevelopmentSource
from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory
from world.scenes.models import Interaction, Mute
from world.scenes.mute_services import set_mute
from world.seeds.checks import seed_check_resolution_tables
from world.skills.factories import CharacterSpecializationValueFactory, SpecializationFactory
from world.species.factories import (
    LanguageFactory,
    make_language_with_target,
    make_understanding_condition,
)
from world.species.language_progression import get_language_training_config
from world.species.models import LanguageTrainingConfig
from world.traits.models import CharacterTraitValue, CheckOutcome, Trait, TraitCategory, TraitType

NO_SUCH_MOOD = "There is no mood called '{}'."
NO_SUCH_TONGUE = "There is no language called '{}'."
UNKNOWN_TONGUE = "You don't know that tongue."


class FeelingAndSensing(JourneyCase):
    """Ysmay declares a mood in silence; Wren, who has the empathy, reads it."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.wren = self.make_player("Wren", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.angry = MoodOptionFactory(name="Angry")
        MoodOptionFactory(name="Retired", is_active=False)

    def mood_of(self, character) -> int | None:
        character.sheet_data.refresh_from_db()
        return character.sheet_data.current_mood_id

    def give_empathy(self, character) -> None:
        CharacterSpecializationValueFactory(
            character=character.sheet_data,
            specialization=SpecializationFactory(name="Empathy"),
            value=10,
        )

    def test_a_mood_is_declared_changed_and_cleared_in_silence(self) -> None:
        self.watch(self.hobb)
        Interaction.objects.all().delete()

        self.assertIn("You feel angry.", self.telnet(self.ysmay, "feel Angry"))
        self.assertEqual(self.mood_of(self.ysmay), self.angry.pk)
        self.assertIn("You feel angry.", self.telnet(self.ysmay, "feel ANGRY"))
        self.assertIn("Your feelings settle.", self.telnet(self.ysmay, "feel"))
        self.assertIsNone(self.mood_of(self.ysmay))

        # Nothing is said to the room and no scene row is written, in every outcome.
        self.assertEqual(self.said(self.hobb), "")
        self.assertFalse(Interaction.objects.exists())

    def test_a_mood_that_is_not_there_is_named_back(self) -> None:
        self.assertIn(
            NO_SUCH_MOOD.format("nonexistentia"), self.telnet(self.ysmay, "feel nonexistentia")
        )
        # A retired mood is no mood at all, and the declared one is kept.
        self.telnet(self.ysmay, "feel Angry")
        self.assertIn(NO_SUCH_MOOD.format("Retired"), self.telnet(self.ysmay, "feel Retired"))
        self.assertEqual(self.mood_of(self.ysmay), self.angry.pk)

    def test_the_web_sets_a_mood_by_id_and_refuses_one_that_is_gone(self) -> None:
        result = self.web(self.ysmay, "set_mood", mood_id=self.angry.pk)
        self.assertTrue(result.detail.success)
        self.assertEqual(result.detail.message, "You feel angry.")
        self.assertEqual(self.mood_of(self.ysmay), self.angry.pk)

        retired = MoodOptionFactory(name="Gone", is_active=False)
        for mood_id in (retired.pk, 999999):
            refused = self.web(self.ysmay, "set_mood", mood_id=mood_id)
            self.assertFalse(refused.detail.success)
            self.assertEqual(refused.detail.message, "There is no such mood.")
        self.assertEqual(self.mood_of(self.ysmay), self.angry.pk)

        cleared = self.web(self.ysmay, "set_mood")
        self.assertEqual(cleared.detail.message, "Your feelings settle.")
        self.assertIsNone(self.mood_of(self.ysmay))

    def test_sensing_a_mood_needs_the_empathy_and_a_check_and_names_its_target(self) -> None:
        self.assertIn("Usage: sense <character>", self.telnet(self.wren, "sense"))
        self.assertIn("Could not find 'Nobody'.", self.telnet(self.wren, "sense Nobody"))
        self.assertIn("You lack the empathy to read others.", self.telnet(self.wren, "sense Ysmay"))

        self.give_empathy(self.wren)
        self.assertIn("isn't yours to draw on yet", self.telnet(self.wren, "sense Ysmay"))

        # Someone who is not here is not read.
        elsewhere = self.make_room("The Cellar")
        self.make_player("Bram", room=elsewhere)
        self.assertIn("Could not find 'Bram'.", self.telnet(self.wren, "sense Bram"))

    def test_a_sense_reads_the_mood_on_a_success_and_misses_on_a_failure(self) -> None:
        seed_check_resolution_tables()
        CheckTypeFactory(name=MOOD_SENSE_CHECK_TYPE_NAME)
        self.give_empathy(self.wren)
        self.watch(self.ysmay)

        # No declared mood: the read is of a settled heart.
        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            told = self.telnet(self.wren, "sense Ysmay")
        self.assertIn("You sense that Ysmay's feelings are settled.", told)

        self.telnet(self.ysmay, "feel Angry")
        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            told = self.telnet(self.wren, "sense Ysmay")
        self.assertIn("You sense that Ysmay feels angry.", told)

        with force_check_outcome(CheckOutcome.objects.get(name="Failure")):
            told = self.telnet(self.wren, "sense Ysmay")
        self.assertIn("You can't get a read on them right now.", told)
        self.assertNotIn("angry", told)

        # Ysmay was never told she was read, in any outcome.
        self.assertNotTold(self.ysmay, "sense")
        self.assertNotTold(self.ysmay, "Wren")

    def test_the_web_senses_a_persona_by_id(self) -> None:
        seed_check_resolution_tables()
        CheckTypeFactory(name=MOOD_SENSE_CHECK_TYPE_NAME)
        self.give_empathy(self.wren)
        self.telnet(self.ysmay, "feel Angry")
        persona = self.ysmay.sheet_data.primary_persona

        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            result = self.web(self.wren, "sense_mood", target_persona_id=persona.pk)
        self.assertTrue(result.detail.success)
        self.assertEqual(result.detail.message, "You sense that Ysmay feels angry.")

        self.assertEqual(
            self.web(self.hobb, "sense_mood", target_persona_id=persona.pk).detail.message,
            "You lack the empathy to read others.",
        )


class SpeakingOutOfCharacter(JourneyCase):
    """Ysmay says a thing as herself, not as her character, and the room hears it so."""

    LINE = "I think we need a GM to rule on this."

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.watch(self.hobb)

    def hobbs_player(self) -> PlayerData:
        return PlayerData.objects.get_or_create(account=self.hobb.account)[0]

    def test_the_room_hears_an_ooc_line_and_the_speaker_sees_her_own(self) -> None:
        told = self.telnet(self.ysmay, f"ooc   {self.LINE}  ")
        self.assertIn(f"<OOC> You say: {self.LINE}", told)
        self.assertTold(self.hobb, f"<OOC> Ysmay says: {self.LINE}")
        # Braces are just text.
        self.telnet(self.ysmay, "ooc {name} owes me {5} coins")
        self.assertTold(self.hobb, "<OOC> Ysmay says: {name} owes me {5} coins")

    def test_nothing_to_say_is_refused_and_nobody_hears_it(self) -> None:
        told = self.telnet(self.ysmay, "ooc")
        self.assertIn(OOC_USAGE, told)
        self.assertEqual(self.said(self.hobb), "")

    def test_an_ooc_mute_silences_the_line_and_an_ic_mute_does_not(self) -> None:
        persona = self.ysmay.sheet_data.primary_persona
        set_mute(owner=self.hobbs_player(), muted_persona=persona, ic=True, ooc=False)
        self.telnet(self.ysmay, "ooc first")
        self.assertTold(self.hobb, "<OOC> Ysmay says: first")

        set_mute(owner=self.hobbs_player(), muted_persona=persona, ic=False, ooc=True)
        told = self.telnet(self.ysmay, "ooc second")
        self.assertIn("<OOC> You say: second", told)
        self.assertNotTold(self.hobb, "second")

    def test_an_account_level_mute_hides_the_face_it_names_and_no_other(self) -> None:
        persona = self.ysmay.sheet_data.primary_persona
        set_mute(
            owner=self.hobbs_player(),
            muted_persona=persona,
            ic=False,
            ooc=True,
            account_level=True,
        )
        self.telnet(self.ysmay, "ooc hidden")
        self.assertNotTold(self.hobb, "hidden")

        # Ysmay's player now wears a different face than the one muted: hiding this line
        # from Hobb alone would tell him who is under it (ADR-0204), so it reaches him.
        Mute.objects.all().delete()
        player, _ = PlayerData.objects.get_or_create(account=self.ysmay.account)
        Mute.objects.create(
            owner=self.hobbs_player(),
            muted_persona=PersonaFactory(character_sheet=self.ysmay.sheet_data),
            muted_player=player,
            account_level=True,
            mute_ic=False,
            mute_ooc=True,
        )
        self.telnet(self.ysmay, "ooc revealed")
        self.assertTold(self.hobb, "<OOC> Ysmay says: revealed")

    def test_an_unconscious_listener_does_not_hear_the_waking_room(self) -> None:
        ConditionInstanceFactory(target=self.hobb, condition=UnconsciousConditionFactory())
        self.telnet(self.ysmay, "ooc anyone there")
        self.assertNotTold(self.hobb, "anyone there")


class SpeakingWithoutAStanding(JourneyCase):
    """A character the roster never saw, or one with no sheet, still speaks."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.watch(self.hobb)

    def test_a_sheet_with_no_roster_entry_speaks_ooc_and_in_character(self) -> None:
        shade = CharacterFactory(db_key="Shade", location=self.lantern)
        CharacterSheetFactory(character=shade)
        self.telnet(shade, "ooc is anyone there")
        self.assertTold(self.hobb, "<OOC> Shade says: is anyone there")
        self.telnet(shade, "say good evening")
        self.assertTold(self.hobb, 'Shade says "good evening"')
        self.telnet(shade, "whisper Hobb=psst")
        self.assertTold(self.hobb, "psst")

        # Hobb can mute a face the roster never seated; the line then stays unheard.
        hobbs_player = PlayerData.objects.get_or_create(account=self.hobb.account)[0]
        set_mute(
            owner=hobbs_player, muted_persona=shade.sheet_data.primary_persona, ic=False, ooc=True
        )
        self.telnet(shade, "ooc muted now")
        self.assertNotTold(self.hobb, "muted now")

    def test_a_character_with_no_sheet_says_a_plain_line(self) -> None:
        shade = CharacterFactory(db_key="Shade", location=self.lantern)
        self.telnet(shade, "say good evening")
        self.assertTold(self.hobb, 'Shade says "good evening"')

    def test_a_blank_ooc_sent_from_the_web_is_refused_in_the_same_words(self) -> None:
        refused = self.web(self.hobb, "ooc", text="   ")
        self.assertFalse(refused.detail.success)
        self.assertEqual(refused.detail.message, OOC_USAGE)


class SpeakingATongue(JourneyCase):
    """Ysmay and Hobb share Khatic; Bram, who has none, hears the shape of it only."""

    TEXT = "the caravan leaves at dawn through the salt gate"

    def setUp(self) -> None:
        super().setUp()
        ModifierTarget.clear_trait_cache()
        CharacterTraitValue.flush_instance_cache()
        DevelopmentPoints.flush_instance_cache()
        LanguageTrainingConfig.objects.flush_singleton_cache()
        self.trait = Trait.objects.create(
            name="Khatic", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        self.khatic = LanguageFactory(name="Khatic", trait=self.trait)
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.know(self.ysmay, 100)
        self.know(self.hobb, 100)
        self.watch(self.hobb, self.bram)

    def know(self, character, fluency: int, trait: Trait | None = None) -> None:
        CharacterTraitValue.objects.update_or_create(
            character=character.sheet_data,
            trait=trait or self.trait,
            defaults={"value": fluency},
        )

    def spoken(self) -> Interaction:
        return Interaction.objects.get(content=self.TEXT)

    def test_a_tagged_say_is_heard_in_full_by_the_fluent_and_garbled_by_the_rest(self) -> None:
        told = self.telnet(self.ysmay, f"say (Khatic) {self.TEXT}")
        self.assertIn(f'You say in Khatic, "{self.TEXT}"', told)
        self.assertTold(self.hobb, f'Ysmay says in Khatic, "{self.TEXT}"')
        heard = self.said(self.bram)
        self.assertIn("Ysmay says in Khatic,", heard)
        self.assertNotIn(self.TEXT, heard)
        self.assertIn("...", heard)
        self.assertEqual(self.spoken().language_id, self.khatic.pk)

    def test_a_tongue_the_speaker_lacks_or_that_is_not_one_is_refused(self) -> None:
        self.assertIn(
            NO_SUCH_TONGUE.format("Nonexistentia"),
            self.telnet(self.ysmay, "say (Nonexistentia) hello there"),
        )
        told = self.telnet(self.bram, f"say (Khatic) {self.TEXT}")
        self.assertIn(UNKNOWN_TONGUE, told)
        self.assertFalse(Interaction.objects.filter(content=self.TEXT).exists())
        self.assertNotTold(self.hobb, self.TEXT)

    def test_speak_sets_a_default_tongue_a_tag_beats_it_and_a_bare_speak_resets_it(self) -> None:
        other_trait = Trait.objects.create(
            name="Lowspeech", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        other = LanguageFactory(name="Lowspeech", trait=other_trait)
        self.know(self.ysmay, 100, other_trait)

        self.assertIn("You will now speak Khatic.", self.telnet(self.ysmay, "speak khatic"))
        self.ysmay.sheet_data.refresh_from_db()
        self.assertEqual(self.ysmay.sheet_data.current_language_id, self.khatic.pk)
        self.telnet(self.ysmay, f"say {self.TEXT}")
        self.assertEqual(self.spoken().language_id, self.khatic.pk)

        Interaction.objects.filter(content=self.TEXT).delete()
        self.telnet(self.ysmay, f"say (Lowspeech) {self.TEXT}")
        self.assertEqual(self.spoken().language_id, other.pk)

        self.assertIn("You will now speak the universal tongue.", self.telnet(self.ysmay, "speak"))
        self.ysmay.sheet_data.refresh_from_db()
        self.assertIsNone(self.ysmay.sheet_data.current_language_id)

        self.assertIn(NO_SUCH_TONGUE.format("Nope"), self.telnet(self.ysmay, "speak Nope"))
        self.assertIn(UNKNOWN_TONGUE, self.telnet(self.bram, "speak Khatic"))
        self.bram.sheet_data.refresh_from_db()
        self.assertIsNone(self.bram.sheet_data.current_language_id)

    def test_the_web_sets_the_tongue_by_id(self) -> None:
        result = self.web(self.ysmay, "set_language", language_id=self.khatic.pk)
        self.assertEqual(result.detail.message, "You will now speak Khatic.")
        for who, language_id in ((self.bram, self.khatic.pk), (self.ysmay, 999999)):
            refused = self.web(who, "set_language", language_id=language_id)
            self.assertFalse(refused.detail.success)
            self.assertEqual(refused.detail.message, UNKNOWN_TONGUE)

    def test_a_universal_tongue_is_the_untagged_say(self) -> None:
        universal_trait = Trait.objects.create(
            name="Common", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        LanguageFactory(name="Common", trait=universal_trait, is_universal=True)
        # No fluency needed, and the row says nothing of a tongue.
        self.telnet(self.bram, f"say (Common) {self.TEXT}")
        self.assertIsNone(self.spoken().language_id)
        self.assertTold(self.hobb, f'Bram says "{self.TEXT}"')

    def test_a_whisper_and_a_mutter_keep_the_tongue_on_the_full_text_only(self) -> None:
        self.telnet(self.ysmay, "speak Khatic")
        self.telnet(self.ysmay, "whisper Hobb=secret")
        self.assertTold(self.hobb, "secret")
        self.assertEqual(Interaction.objects.get(content="secret").language_id, self.khatic.pk)

        self.telnet(self.ysmay, "mutter Hobb=the plan is set")
        full, fragment = Interaction.objects.filter(mode=InteractionMode.MUTTER).order_by("pk")
        self.assertEqual(full.content, "the plan is set")
        self.assertEqual(full.language_id, self.khatic.pk)
        self.assertIsNone(fragment.language_id)

        # A speaker without the tongue cannot whisper or mutter in it.
        self.bram.sheet_data.current_language = self.khatic
        self.bram.sheet_data.save(update_fields=["current_language"])
        self.assertIn(UNKNOWN_TONGUE, self.telnet(self.bram, "whisper Hobb=hush"))
        self.assertIn(UNKNOWN_TONGUE, self.telnet(self.bram, "mutter Hobb=the plan is set"))

    def test_poses_and_emits_are_never_in_a_tongue(self) -> None:
        self.telnet(self.ysmay, "speak Khatic")
        self.telnet(self.ysmay, "pose sets both hands flat on the table.")
        self.telnet(self.ysmay, "emit A bell tolls somewhere below.")
        for content in ("sets both hands flat on the table.", "A bell tolls somewhere below."):
            self.assertIsNone(Interaction.objects.get(content__contains=content).language_id)
        self.assertTold(self.bram, "A bell tolls somewhere below.")

    def test_an_unconscious_listener_does_not_overhear_a_tongue(self) -> None:
        ConditionInstanceFactory(target=self.hobb, condition=UnconsciousConditionFactory())
        self.telnet(self.ysmay, f"say (Khatic) {self.TEXT}")
        self.assertNotTold(self.hobb, "Khatic")
        self.assertTold(self.bram, "Ysmay says in Khatic,")

    def test_the_viewer_sees_the_same_row_the_telnet_line_describes(self) -> None:
        self.telnet(self.ysmay, f"say (Khatic) {self.TEXT}")
        self.assertShownRow(self.hobb, self.TEXT)


class UnderstandingATongue(JourneyCase):
    """A condition Wren carries lifts her comprehension of a tongue she has none of."""

    TEXT = "the north gate opens at the second bell so bring the lamp oil"

    def setUp(self) -> None:
        super().setUp()
        ModifierTarget.clear_trait_cache()
        CharacterTraitValue.flush_instance_cache()
        self.language, self.target = make_language_with_target("LiveCompTongue")
        self.condition = make_understanding_condition("Placeholder Live Understanding", self.target)
        self.lantern = self.make_room("The Lantern")
        self.envoy = self.make_player("Envoy", room=self.lantern)
        CharacterTraitValue.objects.create(
            character=self.envoy.sheet_data, trait=self.language.trait, value=100
        )
        self.wren = self.make_player("Wren", room=self.lantern)
        self.watch(self.wren)

    def heard(self) -> str:
        start = len(self.mailbox(self.wren).lines)
        self.telnet(self.envoy, f"say (LiveCompTongue) {self.TEXT}")
        return "\n".join(self.mailbox(self.wren).lines[start:])

    def test_without_the_condition_wren_hears_only_the_shape(self) -> None:
        self.assertIn(f'Envoy says in {self.language.name}, "..."', self.heard())

    def test_a_strong_condition_reads_clear_and_a_weak_one_partly(self) -> None:
        instance = ConditionInstanceFactory(target=self.wren, condition=self.condition, severity=4)
        self.assertIn(f'Envoy says in {self.language.name}, "{self.TEXT}"', self.heard())

        instance.severity = 2
        instance.save(update_fields=["severity"])
        heard = self.heard()
        prefix = f'Envoy says in {self.language.name}, "'
        self.assertIn(prefix, heard)
        words = set(heard.split(prefix, 1)[1].split('"', 1)[0].split())
        self.assertTrue(words & set(self.TEXT.split()))
        self.assertIn("...", words)

    def test_understanding_does_not_let_wren_speak_it(self) -> None:
        ConditionInstanceFactory(target=self.wren, condition=self.condition, severity=4)
        self.assertIn(UNKNOWN_TONGUE, self.telnet(self.wren, "say (LiveCompTongue) hello"))

    def test_a_condition_on_the_speaker_does_not_lift_the_speakers_band(self) -> None:
        trained = CharacterTraitValue.objects.get(
            character=self.envoy.sheet_data, trait=self.language.trait
        )
        trained.value = 20
        trained.save(update_fields=["value"])
        ConditionInstanceFactory(target=self.envoy, condition=self.condition, severity=4)
        CharacterTraitValue.objects.create(
            character=self.wren.sheet_data, trait=self.language.trait, value=100
        )
        heard = self.heard()
        self.assertIn("...", heard)
        self.assertNotIn(self.TEXT, heard)

    def test_a_scene_sweep_ends_the_effect(self) -> None:
        scene_condition = ConditionTemplateFactory(
            name="Placeholder Scene Understanding", default_duration_type=DurationType.SCENE
        )
        ConditionModifierEffectFactory(
            condition=scene_condition, modifier_target=self.target, value=80
        )
        ConditionInstanceFactory(target=self.wren, condition=scene_condition)
        self.assertIn(self.TEXT, self.heard())
        expire_scene_scoped_conditions([self.wren])
        self.assertNotIn(self.TEXT, self.heard())


class StudyingATongue(JourneyCase):
    """Ysmay studies Khatic once a week, alone or beside Hobb who is fluent."""

    def setUp(self) -> None:
        super().setUp()
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        LanguageTrainingConfig.objects.flush_singleton_cache()
        self.trait = Trait.objects.create(
            name="Khatic", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        self.khatic = LanguageFactory(name="Khatic", trait=self.trait)
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        CharacterTraitValue.objects.create(
            character=self.hobb.sheet_data, trait=self.trait, value=100
        )

    def earned(self) -> int:
        return DevelopmentPoints.objects.get(
            character_sheet=self.ysmay.sheet_data, trait=self.trait
        ).total_earned

    def test_self_study_earns_the_practice_rate_once_a_week(self) -> None:
        config = get_language_training_config()
        told = self.telnet(self.ysmay, "train_language Khatic")
        self.assertIn("through self-study", told)
        self.assertEqual(self.earned(), config.self_study_dp_per_session)
        txn = DevelopmentTransaction.objects.get(
            character_sheet=self.ysmay.sheet_data, trait=self.trait
        )
        self.assertEqual(txn.source, DevelopmentSource.PRACTICE)

        # PRACTICE and TRAINING share one weekly slot.
        for line in ("train_language Khatic", "train_language Khatic=Hobb"):
            self.assertIn("You've already studied Khatic this week.", self.telnet(self.ysmay, line))
        self.assertEqual(self.earned(), config.self_study_dp_per_session)

    def test_a_fluent_teacher_here_earns_the_training_rate(self) -> None:
        config = get_language_training_config()
        told = self.telnet(self.ysmay, "train_language Khatic=Hobb")
        self.assertIn("with a teacher", told)
        self.assertEqual(self.earned(), config.teacher_dp_per_session)
        txn = DevelopmentTransaction.objects.get(
            character_sheet=self.ysmay.sheet_data, trait=self.trait
        )
        self.assertEqual(txn.source, DevelopmentSource.TRAINING)

    def test_a_teacher_who_is_not_fluent_is_only_self_study(self) -> None:
        config = get_language_training_config()
        hobbs = CharacterTraitValue.objects.get(character=self.hobb.sheet_data, trait=self.trait)
        hobbs.value = 10
        hobbs.save(update_fields=["value"])
        self.assertIn("through self-study", self.telnet(self.ysmay, "train_language Khatic=Hobb"))
        self.assertEqual(self.earned(), config.self_study_dp_per_session)

    def test_a_teacher_in_another_room_is_only_self_study(self) -> None:
        elsewhere = self.make_room("The Cellar")
        self.hobb.location = elsewhere
        self.hobb.save()
        self.assertIn(
            "Could not find 'Hobb'.", self.telnet(self.ysmay, "train_language Khatic=Hobb")
        )
        # Sent by id, a teacher who has left the room is quietly not a teacher.
        result = self.web(
            self.ysmay, "train_language", language_id=self.khatic.pk, teacher_id=self.hobb.pk
        )
        self.assertTrue(result.detail.data["self_study"])

    def test_usage_and_an_unknown_tongue_are_named_back(self) -> None:
        self.assertIn(
            "Usage: train_language <language>[=<teacher>].",
            self.telnet(self.ysmay, "train_language"),
        )
        self.assertIn(NO_SUCH_TONGUE.format("Nope"), self.telnet(self.ysmay, "train_language Nope"))
        refused = self.web(self.ysmay, "train_language", language_id=999999)
        self.assertEqual(refused.detail.message, "There is no such language.")

    def test_the_admin_edited_rates_are_the_rates(self) -> None:
        LanguageTrainingConfig.objects.create(
            pk=1, teacher_dp_per_session=40, self_study_dp_per_session=21
        )
        self.telnet(self.ysmay, "train_language Khatic")
        self.assertEqual(self.earned(), 21)

    def test_a_session_that_crosses_a_threshold_raises_the_fluency(self) -> None:
        # 93 + the default teacher rate (15) = 108 >= cumulative_dp_for_level(11) (100).
        DevelopmentPoints.objects.create(
            character_sheet=self.ysmay.sheet_data, trait=self.trait, total_earned=93
        )
        result = self.web(
            self.ysmay, "train_language", language_id=self.khatic.pk, teacher_id=self.hobb.pk
        )
        self.assertEqual(result.detail.data["level_ups"], [(10, 11)])
        self.assertIn("fluency deepens to 11", result.detail.message)
        value = CharacterTraitValue.objects.get(
            character=self.ysmay.sheet_data, trait=self.trait
        ).value
        self.assertEqual(value, 11)

    def test_a_session_parked_at_a_lock_says_so_and_gains_nothing(self) -> None:
        sheet = self.ysmay.sheet_data
        CharacterTraitValue.objects.create(character=sheet, trait=self.trait, value=19)
        DevelopmentPointsFactory(
            character_sheet=sheet, trait=self.trait, total_earned=cumulative_dp_for_level(19)
        )
        TraitRatingUnlock.objects.create(trait=self.trait, target_rating=20)

        result = self.web(self.ysmay, "train_language", language_id=self.khatic.pk)
        self.assertEqual(result.detail.data["breakthrough_rating"], 20)
        self.assertEqual(result.detail.data["level_ups"], [])
        self.assertIn("breakthrough", result.detail.message)
        self.assertIn("training maintains, does not advance", result.detail.message)
        self.assertNotIn("development points", result.detail.message)
        self.assertEqual(self.earned(), cumulative_dp_for_level(19))
        self.assertEqual(
            CharacterTraitValue.objects.get(character=sheet, trait=self.trait).value, 19
        )

    def test_a_restricted_tongue_cannot_be_puzzled_out_alone(self) -> None:
        trait = Trait.objects.create(
            name="Sealed", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        LanguageFactory(name="Sealed", trait=trait, restricted=True)
        told = self.telnet(self.ysmay, "train_language Sealed")
        self.assertIn(
            "No one can teach you Sealed, and it is not a tongue you can puzzle out alone.", told
        )
        CharacterTraitValue.objects.create(character=self.hobb.sheet_data, trait=trait, value=100)
        self.assertIn("with a teacher", self.telnet(self.ysmay, "train_language Sealed=Hobb"))

    def test_a_restricted_tongue_already_begun_can_be_studied_alone(self) -> None:
        trait = Trait.objects.create(
            name="Sealed", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        LanguageFactory(name="Sealed", trait=trait, restricted=True)
        CharacterTraitValue.objects.create(character=self.ysmay.sheet_data, trait=trait, value=1)
        self.assertIn("through self-study", self.telnet(self.ysmay, "train_language Sealed"))
