"""Tests for opponent portrait fields on OpponentSerializer (#554).

The portrait is resolved through the opponent's IDENTITY
(``CombatOpponent.persona``), not a dedicated field — ``Persona`` already
owns the thumbnail. ``OpponentSerializer`` mirrors ``PersonaSerializer``'s
``thumbnail_url`` / ``thumbnail_media_url`` semantics so opponents and
personas behave identically on the frontend.

Built in ``setUp`` rather than ``setUpTestData``: ``CombatOpponentFactory``
caches an Evennia ObjectDB on the model (a ``DbHolder``), which is not
deepcopyable — so storing opponent instances as class attributes breaks the
``setUpTestData`` deepcopy. See the factory docstring.
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.serializers import OpponentSerializer
from world.roster.factories import PlayerMediaFactory
from world.scenes.factories import PersonaFactory


class OpponentPortraitSerializerTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()

    def test_persona_with_thumbnail_exposes_media_and_direct_url(self) -> None:
        media = PlayerMediaFactory()
        persona = PersonaFactory(
            thumbnail=media,
            thumbnail_url="https://cdn.example/direct.png",
        )
        opponent = CombatOpponentFactory(encounter=self.encounter, persona=persona)

        data = OpponentSerializer(opponent).data
        self.assertEqual(data["thumbnail_media_url"], media.cloudinary_url)
        self.assertEqual(data["thumbnail_url"], "https://cdn.example/direct.png")

    def test_persona_without_thumbnail_returns_none_media_url(self) -> None:
        persona = PersonaFactory(thumbnail=None, thumbnail_url="")
        opponent = CombatOpponentFactory(encounter=self.encounter, persona=persona)

        data = OpponentSerializer(opponent).data
        self.assertIsNone(data["thumbnail_media_url"])
        # Matches PersonaSerializer: thumbnail_url is the model URLField,
        # which is "" (blank) when unset.
        self.assertEqual(data["thumbnail_url"], "")

    def test_persona_less_opponent_returns_none_for_both(self) -> None:
        # Factory default: persona=None (ephemeral MOOK).
        opponent = CombatOpponentFactory(encounter=self.encounter)

        data = OpponentSerializer(opponent).data
        self.assertIsNone(data["thumbnail_media_url"])
        self.assertIsNone(data["thumbnail_url"])
