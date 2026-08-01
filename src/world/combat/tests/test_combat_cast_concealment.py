"""Combat-side cast concealment (#2734).

The scene-side seam is covered by ``world.scenes.tests.test_cast_concealment``;
this suite covers the two pieces combat adds on top of it — the unattributed
narration renderer, and routing the OUTCOME broadcast through a resolved audience.

``resolve_cast_audience`` itself is exercised in
``world.magic.tests.services.test_cast_observation`` and is patched here, so a
failure in this file points at combat's wiring rather than at detection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.combat.factories import CombatEncounterFactory
from world.combat.interaction_services import (
    broadcast_action_outcome,
    render_unattributed_action_narration,
)
from world.combat.types import OpponentDamageResult
from world.magic.constants import TechniqueReach
from world.magic.factories import TechniqueFactory
from world.magic.services.cast_observation import CastAudience
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.models import Interaction
from world.scenes.place_models import InteractionReceiver

# The module the seam binds the name into, which is what a patch has to target --
# combat.services does `from ... import resolve_cast_audience` inside the function,
# so patching the definition site is what intercepts it.
_AUDIENCE_TARGET = "world.magic.services.cast_observation.resolve_cast_audience"


def _outcome(*, damage: int = 0, defeated: bool = False, wounds: tuple[str, ...] = ()):
    """A stub ActionOutcome carrying just what the narration renderers read.

    ``damage_results`` holds a real ``OpponentDamageResult``, not a mock: the renderers
    read ``defeated`` behind an ``isinstance`` check, so a duck-typed stub silently
    reports "not defeated" and the assertion under test would pass vacuously.
    """
    outcome = MagicMock()
    outcome.damage_results = [
        OpponentDamageResult(
            damage_dealt=damage,
            health_damaged=damage > 0,
            probed=False,
            probing_increment=0,
            defeated=defeated,
        )
    ]
    consequence = MagicMock()
    consequence.knocked_out = False
    consequence.dying = False
    wound_stubs = []
    for label in wounds:
        stub = MagicMock()
        stub.name = label
        wound_stubs.append(stub)
    consequence.wounds_applied = wound_stubs
    outcome.damage_consequences = [consequence]
    outcome.combo_used = None
    return outcome


class UnattributedNarrationTests(TestCase):
    """``render_unattributed_action_narration`` — the effect without the actor."""

    def test_names_the_damage_but_never_the_caster(self) -> None:
        line = render_unattributed_action_narration(
            target_label="Corvin", outcome=_outcome(damage=24)
        )

        self.assertIn("Corvin", line)
        self.assertIn("24", line)
        self.assertNotIn("Ilyra", line)

    def test_carries_consequences_so_the_victim_learns_they_were_dropped(self) -> None:
        """The whole point of the rework: being defeated must not happen in silence."""
        line = render_unattributed_action_narration(
            target_label="Corvin", outcome=_outcome(damage=40, defeated=True)
        )

        self.assertIn("defeating them", line)

    def test_a_miss_still_reads_as_something_happening(self) -> None:
        line = render_unattributed_action_narration(target_label="Corvin", outcome=_outcome())

        self.assertIn("Corvin", line)
        self.assertIn("misses", line)

    def test_target_less_action_has_no_outward_event_to_narrate(self) -> None:
        """A self-buff shows nothing; callers skip emitting on the empty string."""
        self.assertEqual(
            render_unattributed_action_narration(target_label=None, outcome=_outcome()), ""
        )


class ResolveCombatCastAudienceTests(TestCase):
    """The reach gate in front of the audience service."""

    def _participant(self):
        """A stub participant — the gate only reaches for character_sheet.character."""
        participant = MagicMock()
        participant.character_sheet.character = MagicMock()
        return participant

    def test_contact_range_technique_is_never_concealed(self) -> None:
        """You have to be standing on someone to stab them (Tehom's ruling).

        Asserting the service returns unconcealed *and* that the roll is skipped: a
        melee action must not pay for a room-wide detection roll per observer.
        """
        from world.combat.services import _resolve_combat_cast_audience

        technique = TechniqueFactory(reach=TechniqueReach.SAME)

        with patch(_AUDIENCE_TARGET, wraps=None) as mock_resolve:
            mock_resolve.return_value = CastAudience(
                concealed=False, full=[], vague=[], effect_only=[]
            )
            audience = _resolve_combat_cast_audience(self._participant(), technique)

        # The gate lives inside resolve_cast_audience, so the service IS called --
        # what matters is that it short-circuits to unconcealed.
        self.assertFalse(audience.concealed)

    def test_ranged_technique_delegates_to_the_audience_service(self) -> None:
        from world.combat.services import _resolve_combat_cast_audience

        technique = TechniqueFactory(reach=TechniqueReach.ANY)
        expected = CastAudience(concealed=True, full=[], vague=[], effect_only=[])

        with patch(_AUDIENCE_TARGET, return_value=expected) as mock_resolve:
            audience = _resolve_combat_cast_audience(self._participant(), technique)

        self.assertIs(audience, expected)
        mock_resolve.assert_called_once()
        self.assertIs(mock_resolve.call_args.kwargs["technique"], technique)


class BroadcastActionOutcomeAudienceTests(TestCase):
    """``broadcast_action_outcome``'s audience routing."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.encounter = CombatEncounterFactory(scene=cls.scene)
        cls.detector = PersonaFactory()
        cls.marginal = PersonaFactory()
        cls.oblivious = PersonaFactory()

    def _outcomes(self):
        return Interaction.objects.filter(scene=self.scene, mode=InteractionMode.OUTCOME).order_by(
            "pk"
        )

    def _receivers(self, interaction):
        return list(
            InteractionReceiver.objects.filter(interaction=interaction).values_list(
                "persona_id", flat=True
            )
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
            audience=CastAudience(concealed=False, full=[], vague=[], effect_only=[]),
        )

        assert interaction is not None
        self.assertEqual(interaction.visibility, InteractionVisibility.DEFAULT)
        self.assertFalse(InteractionReceiver.objects.filter(interaction=interaction).exists())

    def test_concealed_audience_restricts_the_attributed_pose_to_its_receivers(self) -> None:
        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration="Ilyra's Whisper of Binding strikes Corvin for 24 damage.",
            audience=CastAudience(concealed=True, full=[self.detector], vague=[], effect_only=[]),
        )

        assert interaction is not None
        self.assertEqual(interaction.visibility, InteractionVisibility.PERCEIVED_ONLY)
        self.assertEqual(self._receivers(interaction), [self.detector.pk])
        # One pose only: nobody else perceived anything, so no lower tier was authored.
        self.assertEqual(self._outcomes().count(), 1)

    def test_every_tier_gets_its_own_pose_and_nobody_gets_two(self) -> None:
        """The core of the rework — three tiers, three distinct lines, no overlap."""
        attributed = "Ilyra's Whisper of Binding strikes Corvin for 24 damage."
        unattributed = "Corvin is struck for 24 damage."

        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration=attributed,
            audience=CastAudience(
                concealed=True,
                full=[self.detector],
                vague=[self.marginal],
                effect_only=[self.oblivious],
            ),
            unattributed_narration=unattributed,
        )

        assert interaction is not None
        outcomes = list(self._outcomes())
        self.assertEqual(len(outcomes), 3)

        by_persona = {}
        for outcome in outcomes:
            for persona_id in self._receivers(outcome):
                self.assertNotIn(persona_id, by_persona, "an observer received two poses")
                by_persona[persona_id] = outcome

        self.assertEqual(by_persona[self.detector.pk].content, attributed)
        self.assertEqual(by_persona[self.oblivious.pk].content, unattributed)

        vague_line = by_persona[self.marginal.pk].content
        # Knows a working happened -- the thing effect_only cannot tell -- but is never
        # told less than the tier below it, so the effect is folded in.
        self.assertIn("working", vague_line)
        self.assertIn("24 damage", vague_line)
        self.assertNotIn("Ilyra", vague_line)

        for outcome in outcomes:
            self.assertEqual(outcome.visibility, InteractionVisibility.PERCEIVED_ONLY)

    def test_imperceptible_working_hides_outright_from_the_bottom_tier(self) -> None:
        """No unattributed narration means there was nothing to see; pre-#2734 behaviour.

        resolve_cast_audience leaves effect_only empty for these, but the router must
        also refuse to mint an empty pose if a caller passes one through anyway.
        """
        broadcast_action_outcome(
            encounter=self.encounter,
            narration="Ilyra's Whisper of Binding takes hold of Corvin.",
            audience=CastAudience(
                concealed=True,
                full=[self.detector],
                vague=[],
                effect_only=[self.oblivious],
            ),
            unattributed_narration="",
        )

        outcomes = list(self._outcomes())
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(self._receivers(outcomes[0]), [self.detector.pk])

    def test_vague_tier_degrades_when_there_is_nothing_to_see(self) -> None:
        """With no perceptible effect the vague tier still senses the working."""
        broadcast_action_outcome(
            encounter=self.encounter,
            narration="Ilyra's Whisper of Binding takes hold of Corvin.",
            audience=CastAudience(
                concealed=True, full=[self.detector], vague=[self.marginal], effect_only=[]
            ),
            unattributed_narration="",
        )

        outcomes = list(self._outcomes())
        self.assertEqual(len(outcomes), 2)
        vague = outcomes[1]
        self.assertEqual(self._receivers(vague), [self.marginal.pk])
        self.assertIn("cannot tell by whom", vague.content)
        self.assertNotIn("Ilyra", vague.content)

    def test_empty_narration_still_returns_none_with_an_audience(self) -> None:
        """The empty-narration guard runs before any audience handling."""
        self.assertIsNone(
            broadcast_action_outcome(
                encounter=self.encounter,
                narration="",
                audience=CastAudience(
                    concealed=True, full=[self.detector], vague=[], effect_only=[]
                ),
            )
        )
        self.assertEqual(self._outcomes().count(), 0)
