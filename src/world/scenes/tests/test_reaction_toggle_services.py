"""Unit tests for interaction favorite/reaction toggle services (#1341)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.models import InteractionFavorite, InteractionReaction
from world.scenes.reaction_toggle_services import (
    toggle_interaction_favorite,
    toggle_interaction_reaction,
)


class ToggleFavoriteServiceTests(TestCase):
    def setUp(self) -> None:
        self.scene = SceneFactory()
        self.entry = RosterEntryFactory()
        self.interaction = InteractionFactory(
            scene=self.scene,
            persona=self.entry.character_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_toggle_on_creates_favorite(self) -> None:
        created, fav = toggle_interaction_favorite(
            interaction=self.interaction, roster_entry=self.entry
        )
        self.assertTrue(created)
        self.assertIsNotNone(fav)
        self.assertEqual(fav.roster_entry, self.entry)
        self.assertEqual(fav.interaction, self.interaction)
        self.assertEqual(fav.timestamp, self.interaction.timestamp)

    def test_toggle_off_removes_favorite(self) -> None:
        toggle_interaction_favorite(interaction=self.interaction, roster_entry=self.entry)
        created, fav = toggle_interaction_favorite(
            interaction=self.interaction, roster_entry=self.entry
        )
        self.assertFalse(created)
        self.assertIsNone(fav)
        self.assertEqual(InteractionFavorite.objects.count(), 0)

    def test_toggle_is_independent_per_roster_entry(self) -> None:
        other_entry = RosterEntryFactory()
        toggle_interaction_favorite(interaction=self.interaction, roster_entry=self.entry)
        created, _ = toggle_interaction_favorite(
            interaction=self.interaction, roster_entry=other_entry
        )
        self.assertTrue(created)
        self.assertEqual(InteractionFavorite.objects.count(), 2)


class ToggleReactionServiceTests(TestCase):
    def setUp(self) -> None:
        self.scene = SceneFactory()
        self.account = AccountFactory()
        self.interaction = InteractionFactory(scene=self.scene, mode=InteractionMode.POSE)

    def test_toggle_on_creates_reaction(self) -> None:
        created, rxn = toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f44d"
        )
        self.assertTrue(created)
        self.assertEqual(rxn.account, self.account)
        self.assertEqual(rxn.emoji, "\U0001f44d")
        self.assertEqual(rxn.timestamp, self.interaction.timestamp)

    def test_toggle_off_removes_reaction(self) -> None:
        toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f44d"
        )
        created, rxn = toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f44d"
        )
        self.assertFalse(created)
        self.assertIsNone(rxn)
        self.assertEqual(InteractionReaction.objects.count(), 0)

    def test_toggle_independent_per_emoji(self) -> None:
        toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f44d"
        )
        created, _ = toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f389"
        )
        self.assertTrue(created)
        self.assertEqual(InteractionReaction.objects.count(), 2)
