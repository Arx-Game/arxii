"""Combat-side cast concealment (#2734).

The scene-side seam is covered by ``world.scenes.tests.test_cast_concealment``;
this suite covers the two pieces combat adds on top of it — the magical/mundane
gate, and routing the OUTCOME broadcast through a resolved audience.

``resolve_cast_audience`` itself is exercised in
``world.magic.tests.services.test_cast_observation`` and is patched here, so a
failure in this file points at combat's wiring rather than at detection.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from world.combat.factories import CombatEncounterFactory
from world.combat.interaction_services import broadcast_action_outcome
from world.magic.factories import GiftFactory, TechniqueFactory
from world.magic.services.cast_observation import CastAudience
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.models import Interaction
from world.scenes.place_models import InteractionReceiver

# The module the seam binds the name into, which is what a patch has to target --
# combat.services does `from ... import resolve_cast_audience` inside the function,
# so patching the definition site is what intercepts it.
_AUDIENCE_TARGET = "world.magic.services.cast_observation.resolve_cast_audience"


class ResolveCombatCastAudienceTests(TestCase):
    """The magical/mundane gate in front of the audience service."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.magical_gift = GiftFactory(name="Shadowcraft", is_magical=True)
        cls.mundane_gift = GiftFactory(name="Combat Stances", is_magical=False)

    def _participant(self):
        """A stub participant — the gate only reaches for character_sheet.character."""
        from unittest.mock import MagicMock

        participant = MagicMock()
        participant.character_sheet.character = MagicMock()
        return participant

    def test_mundane_technique_returns_none_without_consulting_the_service(self) -> None:
        """A Whispers adept's sword swing is plainly visible (Tehom's ruling).

        Asserting the service is never *called* — not merely that the result is
        unconcealed — is the point: a mundane action must not pay for a room-wide
        detection roll per observer.
        """
        from world.combat.services import _resolve_combat_cast_audience

        technique = TechniqueFactory(gift=self.mundane_gift)

        with patch(_AUDIENCE_TARGET) as mock_resolve:
            audience = _resolve_combat_cast_audience(self._participant(), technique)

        self.assertIsNone(audience)
        mock_resolve.assert_not_called()

    def test_magical_technique_delegates_to_the_audience_service(self) -> None:
        from world.combat.services import _resolve_combat_cast_audience

        technique = TechniqueFactory(gift=self.magical_gift)
        expected = CastAudience(concealed=True, full=[], vague=[])

        with patch(_AUDIENCE_TARGET, return_value=expected) as mock_resolve:
            audience = _resolve_combat_cast_audience(self._participant(), technique)

        self.assertIs(audience, expected)
        mock_resolve.assert_called_once()


class BroadcastActionOutcomeAudienceTests(TestCase):
    """``broadcast_action_outcome``'s audience routing."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.encounter = CombatEncounterFactory(scene=cls.scene)
        cls.detector = PersonaFactory()
        cls.marginal = PersonaFactory()

    def _outcomes(self):
        return Interaction.objects.filter(scene=self.scene, mode=InteractionMode.OUTCOME).order_by(
            "pk"
        )

    def test_no_audience_is_byte_identical_to_pre_2734(self) -> None:
        """The ~15 non-cast callers pass no audience and must be unaffected."""
        interaction = broadcast_action_outcome(
            encounter=self.encounter, narration="Corvin strikes."
        )

        assert interaction is not None
        self.assertEqual(interaction.visibility, InteractionVisibility.DEFAULT)
        self.assertFalse(InteractionReceiver.objects.filter(interaction=interaction).exists())
        self.assertEqual(self._outcomes().count(), 1)

    def test_unconcealed_audience_still_poses_room_wide(self) -> None:
        """An overt style resolves an audience with concealed=False; same as None."""
        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration="Corvin strikes.",
            audience=CastAudience(concealed=False, full=[], vague=[]),
        )

        assert interaction is not None
        self.assertEqual(interaction.visibility, InteractionVisibility.DEFAULT)
        self.assertFalse(InteractionReceiver.objects.filter(interaction=interaction).exists())

    def test_concealed_audience_restricts_the_pose_to_its_receivers(self) -> None:
        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration="Ilyra — Whisper of Binding.",
            audience=CastAudience(concealed=True, full=[self.detector], vague=[]),
        )

        assert interaction is not None
        self.assertEqual(interaction.visibility, InteractionVisibility.PERCEIVED_ONLY)
        self.assertEqual(
            list(
                InteractionReceiver.objects.filter(interaction=interaction).values_list(
                    "persona_id", flat=True
                )
            ),
            [self.detector.pk],
        )
        # One pose only: nobody detected marginally, so no vague line was authored.
        self.assertEqual(self._outcomes().count(), 1)

    def test_marginal_detection_gets_a_separate_unattributed_line(self) -> None:
        """The vague tier reads a second, different pose — never the full narration."""
        full_narration = "Ilyra — Whisper of Binding."
        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration=full_narration,
            audience=CastAudience(concealed=True, full=[self.detector], vague=[self.marginal]),
        )

        assert interaction is not None
        outcomes = list(self._outcomes())
        self.assertEqual(len(outcomes), 2)

        vague = outcomes[1]
        self.assertEqual(vague.visibility, InteractionVisibility.PERCEIVED_ONLY)
        self.assertNotEqual(vague.content, full_narration)
        self.assertEqual(
            list(
                InteractionReceiver.objects.filter(interaction=vague).values_list(
                    "persona_id", flat=True
                )
            ),
            [self.marginal.pk],
        )
        # The marginal detector must NOT also receive the attributed pose.
        self.assertFalse(
            InteractionReceiver.objects.filter(
                interaction=interaction, persona=self.marginal
            ).exists()
        )

    def test_empty_narration_still_returns_none_with_an_audience(self) -> None:
        """The empty-narration guard runs before any audience handling."""
        self.assertIsNone(
            broadcast_action_outcome(
                encounter=self.encounter,
                narration="",
                audience=CastAudience(concealed=True, full=[self.detector], vague=[]),
            )
        )
        self.assertEqual(self._outcomes().count(), 0)
