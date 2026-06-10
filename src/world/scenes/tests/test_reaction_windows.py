"""Reaction-window primitive: models, registry, react service (#904)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.reaction_models import ReactionWindow, WindowReaction
from world.scenes.reaction_services import (
    ReactionChoice,
    ReactionKindConfig,
    get_reaction_kind,
    open_reaction_window,
    react_to_window,
    register_reaction_kind,
    settle_windows_for_scene,
)


def make_participant(scene):
    """Account-backed persona participating in ``scene`` (full roster chain)."""
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    SceneParticipationFactory(scene=scene, account=account)
    return roster_entry.character_sheet.primary_persona


_BINARY = [
    ReactionChoice(slug="acclaim", label="Acclaim"),
    ReactionChoice(slug="disdain", label="Disdain"),
]


def _binary_kind(*, on_reaction=None, on_settle=None) -> ReactionKindConfig:
    return ReactionKindConfig(
        choices_for=lambda window: _BINARY,  # noqa: ARG005
        on_reaction=on_reaction or (lambda window, reaction: None),  # noqa: ARG005
        on_settle=on_settle,
    )


class ReactionWindowModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.writer = PersonaFactory()
        cls.interaction = InteractionFactory(persona=cls.writer, scene=cls.scene)

    def test_window_defaults(self) -> None:
        window = ReactionWindow.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            scene=self.scene,
            kind=ReactionWindowKind.ENTRANCE,
        )
        assert window.settled_at is None
        assert window.opened_at is not None

    def test_one_window_per_interaction_and_kind(self) -> None:
        ReactionWindow.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            scene=self.scene,
            kind=ReactionWindowKind.ENTRANCE,
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            ReactionWindow.objects.create(
                interaction=self.interaction,
                timestamp=self.interaction.timestamp,
                scene=self.scene,
                kind=ReactionWindowKind.ENTRANCE,
            )

    def test_one_reaction_per_persona_per_window(self) -> None:
        window = ReactionWindow.objects.create(
            interaction=self.interaction,
            timestamp=self.interaction.timestamp,
            scene=self.scene,
            kind=ReactionWindowKind.ENTRANCE,
        )
        reactor = PersonaFactory()
        WindowReaction.objects.create(window=window, reactor_persona=reactor, choice="1")
        with transaction.atomic(), self.assertRaises(IntegrityError):
            WindowReaction.objects.create(window=window, reactor_persona=reactor, choice="2")


class ReactToWindowTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.writer = make_participant(cls.scene)
        cls.reactor = make_participant(cls.scene)
        cls.interaction = InteractionFactory(persona=cls.writer, scene=cls.scene)

    def setUp(self) -> None:
        # The registry is module-global process state — snapshot the real
        # entrance config (registered by MagicConfig.ready) and restore it so
        # this module's stub kinds never leak into later test modules.
        from world.scenes.reaction_services import _KIND_REGISTRY

        original = _KIND_REGISTRY.get(ReactionWindowKind.ENTRANCE)
        if original is not None:
            self.addCleanup(register_reaction_kind, ReactionWindowKind.ENTRANCE, original)
        register_reaction_kind(ReactionWindowKind.ENTRANCE, _binary_kind())
        self.window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
        )

    def test_open_window_is_idempotent(self) -> None:
        again = open_reaction_window(interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE)
        assert again.pk == self.window.pk

    def test_registry_roundtrip(self) -> None:
        assert get_reaction_kind(ReactionWindowKind.ENTRANCE).public is True

    def test_happy_path_records_reaction_and_fires_handler(self) -> None:
        fired: list[str] = []
        register_reaction_kind(
            ReactionWindowKind.ENTRANCE,
            _binary_kind(on_reaction=lambda window, reaction: fired.append(reaction.choice)),  # noqa: ARG005
        )
        reaction = react_to_window(
            window=self.window, reactor_persona=self.reactor, choice="acclaim"
        )
        assert reaction.choice == "acclaim"
        assert fired == ["acclaim"]

    def test_writer_cannot_react_to_own_event(self) -> None:
        with self.assertRaises(ValidationError):
            react_to_window(window=self.window, reactor_persona=self.writer, choice="acclaim")

    def test_non_participant_cannot_react(self) -> None:
        outsider = PersonaFactory()
        with self.assertRaises(ValidationError):
            react_to_window(window=self.window, reactor_persona=outsider, choice="acclaim")

    def test_invalid_choice_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            react_to_window(window=self.window, reactor_persona=self.reactor, choice="bogus")

    def test_duplicate_reaction_rejected(self) -> None:
        react_to_window(window=self.window, reactor_persona=self.reactor, choice="acclaim")
        with self.assertRaises(ValidationError):
            react_to_window(window=self.window, reactor_persona=self.reactor, choice="disdain")

    def test_settled_window_rejects_reactions(self) -> None:
        settle_windows_for_scene(self.scene)
        with self.assertRaises(ValidationError):
            react_to_window(window=self.window, reactor_persona=self.reactor, choice="acclaim")

    def test_handler_failure_rolls_back_reaction(self) -> None:
        def failing_handler(window, reaction) -> None:
            msg = "domain says no"
            raise ValidationError(msg)

        register_reaction_kind(
            ReactionWindowKind.ENTRANCE, _binary_kind(on_reaction=failing_handler)
        )
        with self.assertRaises(ValidationError):
            react_to_window(window=self.window, reactor_persona=self.reactor, choice="acclaim")
        assert WindowReaction.objects.filter(window=self.window).count() == 0

    def test_scene_finish_settles_windows(self) -> None:
        """on_scene_finished closes open windows (#904 wiring)."""
        from world.progression.services.scene_rewards import on_scene_finished

        on_scene_finished(self.scene)
        self.window.refresh_from_db()
        assert self.window.settled_at is not None

    def test_settle_fires_on_settle_and_stamps(self) -> None:
        settled: list[int] = []
        register_reaction_kind(
            ReactionWindowKind.ENTRANCE,
            _binary_kind(on_settle=lambda window: settled.append(window.pk)),
        )
        count = settle_windows_for_scene(self.scene)
        assert count == 1
        assert settled == [self.window.pk]
        self.window.refresh_from_db()
        assert self.window.settled_at is not None
