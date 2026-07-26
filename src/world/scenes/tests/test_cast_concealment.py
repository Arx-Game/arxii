"""Concealed-cast privacy (#2710) — the PERCEIVED_ONLY visibility tier.

ADR-0033: the privacy guarantee ships in the same increment as the feature. These
tests assert the tier from the reader's side — what each viewer's scene log returns.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    ReactionWindowKind,
    ScenePrivacyMode,
)
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import can_view_interaction, create_interaction
from world.scenes.models import Interaction
from world.scenes.reaction_services import (
    ReactionChoice,
    ReactionKindConfig,
    open_reaction_window,
    react_to_window,
    register_reaction_kind,
)
from world.scenes.tests.test_reaction_windows import make_participant


def _played_persona():
    """An account playing a fresh character; returns (account, persona)."""
    account = AccountFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=CharacterFactory())
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry, end_date=None)
    return account, roster_entry.character_sheet.primary_persona


class PerceivedOnlyVisibilityTests(TestCase):
    """A PERCEIVED_ONLY interaction reaches its receivers, staff, and the scene GM."""

    def setUp(self) -> None:
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        self.writer_account, self.writer = _played_persona()
        self.detector_account, self.detector = _played_persona()
        self.bystander_account, self.bystander = _played_persona()
        self.interaction = create_interaction(
            persona=self.writer,
            content="Ilyra works something subtle.",
            mode=InteractionMode.OUTCOME,
            scene=self.scene,
            receivers=[self.detector],
            visibility=InteractionVisibility.PERCEIVED_ONLY,
        )

    def _visible_ids(self, account, persona_ids):
        return set(
            Interaction.objects.visible_to(account, persona_ids=persona_ids).values_list(
                "pk", flat=True
            )
        )

    def test_receiver_sees_it(self) -> None:
        visible = self._visible_ids(self.detector_account, [self.detector.pk])
        self.assertIn(self.interaction.pk, visible)

    def test_bystander_in_a_public_scene_does_not_see_it(self) -> None:
        """The crux: a public scene does not make a concealed cast public."""
        visible = self._visible_ids(self.bystander_account, [self.bystander.pk])
        self.assertNotIn(self.interaction.pk, visible)

    def test_staff_sees_it(self) -> None:
        staff = AccountFactory(is_staff=True)
        self.assertIn(self.interaction.pk, self._visible_ids(staff, []))

    def test_scene_gm_sees_it(self) -> None:
        gm_account, gm_persona = _played_persona()
        SceneParticipationFactory(scene=self.scene, account=gm_account, is_gm=True)
        visible = self._visible_ids(gm_account, [gm_persona.pk])
        self.assertIn(self.interaction.pk, visible)


class PerceivedOnlyReactionGateTests(TestCase):
    """``can_view_interaction`` (#2710): the witness gate behind ``react_to_window``.

    Before this fix, ``can_view_interaction`` had no ``PERCEIVED_ONLY`` branch, so the
    cascade fell through to "public scene -> everyone" for a concealed cast -- a
    bystander who never perceived the event could still react to its pose, and
    reacting is itself an IC act that confirms to the room that something happened.
    This is the leak class ADR-0033 makes non-deferrable (retracted Step 9 of the
    task-2 brief; see task-2-report.md's fix section).
    """

    def setUp(self) -> None:
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        self.writer = make_participant(self.scene)
        self.detector = make_participant(self.scene)
        self.bystander = make_participant(self.scene)
        self.interaction = create_interaction(
            persona=self.writer,
            content="Ilyra works something subtle.",
            mode=InteractionMode.OUTCOME,
            scene=self.scene,
            receivers=[self.detector],
            visibility=InteractionVisibility.PERCEIVED_ONLY,
        )

        from world.scenes.reaction_services import _KIND_REGISTRY

        original = _KIND_REGISTRY.get(ReactionWindowKind.ENTRANCE)
        if original is not None:
            self.addCleanup(register_reaction_kind, ReactionWindowKind.ENTRANCE, original)
        register_reaction_kind(
            ReactionWindowKind.ENTRANCE,
            ReactionKindConfig(
                choices_for=lambda window: [ReactionChoice(slug="acclaim", label="Acclaim")],  # noqa: ARG005
                on_reaction=lambda window, reaction: None,  # noqa: ARG005
            ),
        )
        self.window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
        )

    def test_receiver_can_react(self) -> None:
        reaction = react_to_window(
            window=self.window, reactor_persona=self.detector, choice="acclaim"
        )
        self.assertEqual(reaction.choice, "acclaim")

    def test_non_receiver_cannot_react(self) -> None:
        with self.assertRaisesMessage(ValidationError, "You did not witness that."):
            react_to_window(window=self.window, reactor_persona=self.bystander, choice="acclaim")

    def test_staff_passes_can_view_interaction(self) -> None:
        """``react_to_window`` has no staff concept -- exercise the gate directly."""
        self.assertTrue(can_view_interaction(self.interaction, self.bystander, is_staff=True))
