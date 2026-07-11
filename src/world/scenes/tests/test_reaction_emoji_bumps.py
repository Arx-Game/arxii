"""Tests for valenced reaction bumps + the reaction-emoji catalog endpoint (#1699)."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign, TrackSystemKey
from world.relationships.factories import RelationshipTrackFactory
from world.relationships.models import RelationshipBump
from world.scenes.constants import ReactionValence
from world.scenes.factories import InteractionFactory
from world.scenes.interaction_views import InteractionReactionViewSet, ReactionEmojiViewSet
from world.scenes.models import InteractionReaction, ReactionEmoji


class ValencedReactionBumpTests(TestCase):
    """A valenced catalog emoji fires a bump at the pose's author; neutral doesn't."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        RelationshipTrackFactory(
            name="Regard", sign=TrackSign.POSITIVE, system_key=TrackSystemKey.REGARD
        )
        RelationshipTrackFactory(
            name="Friction", sign=TrackSign.NEGATIVE, system_key=TrackSystemKey.FRICTION
        )
        self.warm_emoji = ReactionEmoji.objects.create(
            emoji="❤️", valence=ReactionValence.POSITIVE, sort_order=1
        )
        ReactionEmoji.objects.create(
            emoji="\U0001f44d", valence=ReactionValence.NEUTRAL, sort_order=0
        )
        self.account = AccountFactory()
        self.reactor_character = CharacterFactory()
        self.reactor_sheet = CharacterSheetFactory(character=self.reactor_character)
        self.author_sheet = CharacterSheetFactory()
        self.interaction = InteractionFactory(persona=self.author_sheet.primary_persona)
        self.factory = APIRequestFactory()

    def _post_reaction(self, emoji: str, interaction=None):
        """POST a reaction as ``self.account`` puppeting ``self.reactor_character``."""
        target = interaction if interaction is not None else self.interaction
        request = self.factory.post(
            "/api/interaction-reactions/",
            {"interaction": target.pk, "emoji": emoji},
            format="json",
        )
        force_authenticate(request, user=self.account)
        with patch.object(
            type(self.account),
            "puppet",
            new_callable=PropertyMock,
            return_value=self.reactor_character,
        ):
            return InteractionReactionViewSet.as_view({"post": "create"})(request)

    def test_valenced_emoji_applies_bump(self) -> None:
        response = self._post_reaction("❤️")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["bump_applied"])
        bump = RelationshipBump.objects.get()
        self.assertEqual(bump.valence, 1)
        self.assertEqual(bump.relationship.source, self.reactor_sheet)
        self.assertEqual(bump.relationship.target, self.author_sheet)
        self.assertEqual(bump.source_emoji.emoji, "❤️")

    def test_toggle_cycle_never_double_bumps(self) -> None:
        first = self._post_reaction("❤️")
        self.assertTrue(first.data["bump_applied"])
        removed = self._post_reaction("❤️")
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(RelationshipBump.objects.count(), 1)
        again = self._post_reaction("❤️")
        self.assertEqual(again.status_code, status.HTTP_201_CREATED)
        self.assertFalse(again.data["bump_applied"])
        self.assertEqual(RelationshipBump.objects.count(), 1)

    def test_neutral_emoji_is_cosmetic_only(self) -> None:
        response = self._post_reaction("\U0001f44d")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["bump_applied"])
        self.assertEqual(RelationshipBump.objects.count(), 0)
        self.assertTrue(InteractionReaction.objects.exists())

    def test_uncataloged_emoji_is_cosmetic_only(self) -> None:
        response = self._post_reaction("\U0001f9c4")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["bump_applied"])
        self.assertEqual(RelationshipBump.objects.count(), 0)

    def test_self_reaction_never_bumps(self) -> None:
        own_pose = InteractionFactory(persona=self.reactor_sheet.primary_persona)
        response = self._post_reaction("❤️", interaction=own_pose)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["bump_applied"])
        self.assertEqual(RelationshipBump.objects.count(), 0)

    def test_bump_message_reaches_response(self) -> None:
        """A successful valenced-emoji bump's response includes bump_message."""
        response = self._post_reaction(emoji=self.warm_emoji.emoji)
        self.assertTrue(response.data["bump_applied"])
        self.assertIsNotNone(response.data["bump_message"])
        self.assertIn("warms", response.data["bump_message"])


class ReactionEmojiCatalogTests(TestCase):
    """GET /api/reaction-emoji/ lists the active catalog in sort order."""

    def setUp(self) -> None:
        ReactionEmoji.objects.create(emoji="❤️", valence=ReactionValence.POSITIVE, sort_order=1)
        ReactionEmoji.objects.create(
            emoji="\U0001f44d", valence=ReactionValence.NEUTRAL, sort_order=0
        )
        ReactionEmoji.objects.create(
            emoji="\U0001f620",
            valence=ReactionValence.NEGATIVE,
            sort_order=2,
            is_active=False,
        )
        self.factory = APIRequestFactory()

    def test_lists_active_in_sort_order(self) -> None:
        request = self.factory.get("/api/reaction-emoji/")
        force_authenticate(request, user=AccountFactory())
        response = ReactionEmojiViewSet.as_view({"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emoji = [row["emoji"] for row in response.data["results"]]
        self.assertEqual(emoji, ["\U0001f44d", "❤️"])
