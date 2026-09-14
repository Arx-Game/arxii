"""Direct-mutation regression for ``cached_reaction_windows``/``cached_reaction_rows``
(#3816, Defect B).

``open_reaction_window`` mutates ``interaction.cached_reaction_windows`` directly at its
write site, and ``react_to_window`` mutates ``window.cached_reaction_rows`` directly at
its write site, rather than relying on a later Prefetch to pick up the new row -- so a
warm cache reflects the new row with no extra query, and a cold cache is left alone
(the next real read recomputes fresh from the DB).
"""

from django.test import TestCase

from world.magic.services.gain import account_for_sheet
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.reaction_models import ReactionWindow, WindowReaction
from world.scenes.reaction_services import open_reaction_window, react_to_window
from world.scenes.tests.test_reaction_windows import make_participant


class OpenReactionWindowCachedPropertyTests(TestCase):
    """``cached_reaction_windows`` reflects a write-site mutation without a requery.

    ``setUp`` (not ``setUpTestData``) deliberately builds a fresh ``Interaction`` per
    test: these are idmapper ``SharedMemoryModel`` rows, so a shared class-level
    instance mutated by ``open_reaction_window`` in one test would carry a warmed (and,
    post-rollback, zombie-pk'd) ``cached_reaction_windows`` list into the next test
    rather than resetting with the transaction.
    """

    def setUp(self) -> None:
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        self.writer = make_participant(self.scene)
        self.interaction = InteractionFactory(persona=self.writer, scene=self.scene)

    def test_open_window_updates_cache_without_requery(self) -> None:
        _ = self.interaction.cached_reaction_windows  # warm the cache to []

        open_reaction_window(interaction=self.interaction, kind=ReactionWindowKind.KUDOS)

        with self.assertNumQueries(0):
            cached = self.interaction.cached_reaction_windows

        self.assertEqual(len(cached), 1)
        self.assertIsInstance(cached[0], ReactionWindow)
        self.assertEqual(cached[0].kind, ReactionWindowKind.KUDOS)

    def test_open_window_is_idempotent_on_a_warm_cache(self) -> None:
        """A second open of the same kind must not double-append the cache."""
        window = open_reaction_window(interaction=self.interaction, kind=ReactionWindowKind.KUDOS)
        _ = self.interaction.cached_reaction_windows  # warm

        again = open_reaction_window(interaction=self.interaction, kind=ReactionWindowKind.KUDOS)

        self.assertEqual(again.pk, window.pk)
        self.assertEqual(len(self.interaction.cached_reaction_windows), 1)

    def test_open_window_does_not_mutate_a_cold_cache(self) -> None:
        """A cold cache is left alone -- the next real read recomputes fresh."""
        open_reaction_window(interaction=self.interaction, kind=ReactionWindowKind.KUDOS)

        self.assertNotIn("cached_reaction_windows", self.interaction.__dict__)
        self.assertEqual(len(self.interaction.cached_reaction_windows), 1)


class ReactToWindowCachedPropertyTests(TestCase):
    """``cached_reaction_rows`` reflects a write-site mutation without a requery."""

    def setUp(self) -> None:
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        self.writer = make_participant(self.scene)
        self.reactor = make_participant(self.scene)
        # KUDOS_KIND's on_reaction (world.progression.reaction_kinds._award_pose_kudos)
        # awards to window.interaction.persona.character_sheet.character.db_account --
        # Evennia's live-puppet link, a separate thing from the roster/tenure chain
        # make_participant already builds. Mirrors
        # world.progression.tests.test_kudos_reaction_kind.make_participant's
        # link_account step.
        writer_character = self.writer.character_sheet.character
        writer_character.db_account = account_for_sheet(self.writer.character_sheet)
        writer_character.save()
        self.interaction = InteractionFactory(persona=self.writer, scene=self.scene)
        self.window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.KUDOS
        )

    def test_react_updates_cache_without_requery(self) -> None:
        _ = self.window.cached_reaction_rows  # warm the cache to []

        react_to_window(window=self.window, reactor_persona=self.reactor, choice="kudos")

        with self.assertNumQueries(0):
            cached = self.window.cached_reaction_rows

        self.assertEqual(len(cached), 1)
        self.assertIsInstance(cached[0], WindowReaction)
        self.assertEqual(cached[0].reactor_persona_id, self.reactor.pk)

    def test_react_does_not_mutate_a_cold_cache(self) -> None:
        """A cold cache is left alone -- the next real read recomputes fresh."""
        react_to_window(window=self.window, reactor_persona=self.reactor, choice="kudos")

        self.assertNotIn("cached_reaction_rows", self.window.__dict__)
        self.assertEqual(len(self.window.cached_reaction_rows), 1)
