"""The line formatter (#3858): the demo's grammar table, one case per row."""

from django.test import SimpleTestCase

from world.scenes.constants import InteractionMode
from world.scenes.line_rendering import render_line


class RenderLineTests(SimpleTestCase):
    def test_a_pose_opens_with_the_name(self) -> None:
        line = render_line("Apostate", InteractionMode.POSE, "stops at the edge of the plaza.")
        assert line == "Apostate stops at the edge of the plaza."

    def test_a_semipose_glues_onto_the_name(self) -> None:
        assert (
            render_line("Apostate", InteractionMode.POSE, "'s cloak drips on the stones.")
            == "Apostate's cloak drips on the stones."
        )
        assert (
            render_line("Apostate", InteractionMode.POSE, ", tired, sits.")
            == "Apostate, tired, sits."
        )

    def test_a_pose_that_already_names_the_actor_is_left_alone(self) -> None:
        assert (
            render_line("Apostate", InteractionMode.POSE, "Apostate looks up.")
            == "Apostate looks up."
        )
        assert (
            render_line("Apostate", InteractionMode.POSE, "Apostate's hood is up.")
            == "Apostate's hood is up."
        )

    def test_a_longer_name_sharing_the_prefix_is_not_the_actor(self) -> None:
        assert (
            render_line("Rose", InteractionMode.POSE, "Rosemary waves.") == "Rose Rosemary waves."
        )

    def test_the_bare_name_alone_is_still_prefixed(self) -> None:
        assert render_line("Apostate", InteractionMode.POSE, "Apostate") == "Apostate Apostate"

    def test_an_empty_pose_stays_empty(self) -> None:
        assert render_line("Apostate", InteractionMode.POSE, "") == ""

    def test_a_say_is_quoted_with_the_verb(self) -> None:
        assert render_line("Apostate", InteractionMode.SAY, "Rain again.") == (
            'Apostate says, "Rain again."'
        )

    def test_a_say_in_a_language_names_it(self) -> None:
        assert render_line(
            "Apostate", InteractionMode.SAY, "Quietly, now.", language_name="Arvani"
        ) == ('Apostate says in Arvani, "Quietly, now."')

    def test_whisper_mutter_and_shout_take_their_verbs(self) -> None:
        assert (
            render_line("Nyx", InteractionMode.WHISPER, "Not here.") == 'Nyx whispers, "Not here."'
        )
        assert render_line("Nyx", InteractionMode.MUTTER, "the gate") == 'Nyx mutters, "the gate"'
        assert render_line("Nyx", InteractionMode.SHOUT, "Hold!") == 'Nyx shouts, "Hold!"'

    def test_an_emit_is_the_text_as_written(self) -> None:
        assert render_line("Nyx", InteractionMode.EMIT, "The bells go quiet.") == (
            "The bells go quiet."
        )

    def test_action_and_outcome_rows_are_untouched(self) -> None:
        assert render_line("Nyx", InteractionMode.ACTION, "[Strike] -- Success") == (
            "[Strike] -- Success"
        )
        assert render_line("Narrator", InteractionMode.OUTCOME, "The blow lands.") == (
            "The blow lands."
        )

    def test_the_telnet_placeholder_is_just_a_name(self) -> None:
        # message_location's mapping resolves ``{caller}`` per looker afterwards.
        assert render_line("{caller}", InteractionMode.POSE, "waves.") == "{caller} waves."
