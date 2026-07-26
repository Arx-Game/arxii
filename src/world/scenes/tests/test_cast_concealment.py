"""Concealed-cast privacy (#2710) — the PERCEIVED_ONLY visibility tier.

ADR-0033: the privacy guarantee ships in the same increment as the feature. These
tests assert the tier from the reader's side — what each viewer's scene log returns.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.magic.narration import render_vague_cast_narration
from world.magic.services.cast_observation import CastAudience
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.cast_services import request_technique_cast
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    ReactionWindowKind,
    ScenePrivacyMode,
)
from world.scenes.factories import PersonaFactory, SceneFactory, SceneParticipationFactory
from world.scenes.interaction_permissions import CanViewInteraction
from world.scenes.interaction_services import can_view_interaction, create_interaction
from world.scenes.models import Interaction
from world.scenes.reaction_services import (
    ReactionChoice,
    ReactionKindConfig,
    open_reaction_window,
    react_to_window,
    register_reaction_kind,
)
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)
from world.scenes.tests.test_reaction_windows import make_participant

# Per-persona account cache for _account_playing (module-level so repeated calls
# within a test — or across tests sharing a persona via setUpTestData — return the
# same account instead of minting a fresh one each time).
_PERSONA_ACCOUNTS: dict[int, AccountFactory] = {}


def _account_playing(persona):
    """The account currently playing *persona*, creating the roster wiring on first ask.

    Mints an ``AccountFactory`` + ``PlayerDataFactory`` + a current (``end_date=None``)
    ``RosterTenureFactory`` bound to *persona*'s existing ``RosterEntry`` — or creates
    that ``RosterEntry`` too, since ``PersonaFactory`` does not provision one. Cached
    per persona pk so repeated calls return the same account.
    """
    if persona.pk in _PERSONA_ACCOUNTS:
        return _PERSONA_ACCOUNTS[persona.pk]
    account = AccountFactory()
    player_data = PlayerDataFactory(account=account)
    roster_entry = RosterEntryFactory(character_sheet=persona.character_sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry, end_date=None)
    _PERSONA_ACCOUNTS[persona.pk] = account
    return account


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


def _can_view_object(interaction, persona, *, is_staff: bool = False) -> bool:
    """Ask ``CanViewInteraction`` directly, bypassing the queryset-level ``visible_to`` filter.

    ``InteractionViewSet.get_queryset`` already filters through ``visible_to`` before
    this permission class ever runs on the live ``interaction-detail`` endpoint, so a
    REST client call can't distinguish the ordering bug (#2710 review) from the fix --
    unit-testing the permission class directly, like ``test_action_delivery.py``'s
    ``_can_view`` helper, is the only way to prove it.
    """
    request = MagicMock()
    request.user.is_staff = is_staff
    request.user.is_authenticated = True
    with patch(
        "world.scenes.interaction_permissions.get_account_personas",
        return_value=[persona.pk],
    ):
        return CanViewInteraction().has_object_permission(request, MagicMock(), interaction)


class CanViewInteractionPublicSceneOrderingTests(TestCase):
    """#2710 review: ``_requires_receiver_check`` must run before the public-scene branch.

    Directed and escalated-visibility content (whisper, place-scoped table talk,
    PERCEIVED_ONLY) is not made public merely because its scene is public -- and a
    concealed cast happening in a PUBLIC scene is the common case. Before this fix,
    ``CanViewInteraction.has_object_permission`` checked "public scene -> everyone"
    BEFORE ``_requires_receiver_check``, so that branch always won first and every one
    of these tiers was dead code for any interaction sitting in a public scene.
    """

    def setUp(self) -> None:
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        self.writer_account, self.writer = _played_persona()
        self.receiver_account, self.receiver = _played_persona()
        self.outsider_account, self.outsider = _played_persona()
        self.perceived_only = create_interaction(
            persona=self.writer,
            content="Ilyra works something subtle.",
            mode=InteractionMode.OUTCOME,
            scene=self.scene,
            receivers=[self.receiver],
            visibility=InteractionVisibility.PERCEIVED_ONLY,
        )
        self.whisper = create_interaction(
            persona=self.writer,
            content="Psst -- did you see that?",
            mode=InteractionMode.WHISPER,
            scene=self.scene,
            receivers=[self.receiver],
        )

    def test_perceived_only_denied_to_non_receiver(self) -> None:
        self.assertFalse(_can_view_object(self.perceived_only, self.outsider))

    def test_perceived_only_allowed_to_receiver(self) -> None:
        self.assertTrue(_can_view_object(self.perceived_only, self.receiver))

    def test_perceived_only_allowed_to_writer(self) -> None:
        self.assertTrue(_can_view_object(self.perceived_only, self.writer))

    def test_perceived_only_allowed_to_staff(self) -> None:
        self.assertTrue(_can_view_object(self.perceived_only, self.outsider, is_staff=True))

    def test_whisper_in_public_scene_denied_to_outsider(self) -> None:
        """Regression: the pre-existing bug this review found -- same leak class."""
        self.assertFalse(_can_view_object(self.whisper, self.outsider))


class ConcealedCastJourneyTests(CastScenarioMixin):
    """Concealment at the real seam: request_technique_cast end to end.

    The audience is stubbed, not rolled — Task 3's suite owns the dice. What is under
    test here is that a resolved cast writes BOTH of its interactions to exactly the
    audience it was given, and nothing to anyone else.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        room = cls.scene.location
        cls.detector = PersonaFactory()
        cls.marginal = PersonaFactory()
        cls.bystander = PersonaFactory()
        # The mixin does not place characters; resolve_cast_audience reads
        # location.contents, so put every participant in the room explicitly.
        for persona in (cls.caster, cls.detector, cls.marginal, cls.bystander):
            character = persona.character_sheet.character
            character.location = room
            character.save()
            # Pin each persona's account BEFORE any cast happens: create_interaction
            # resolves receiver accounts (accounts_for_personas) via RosterTenure at
            # write time, off whatever tenure exists then — an account minted only
            # later, inside _log_for, would leave the receiver row's account_id NULL
            # and the reader-side party filter (receivers__account_id=) would never
            # match it.
            _account_playing(persona)
        cls.technique = make_benign_castable_technique()
        grant_technique(cls.caster, cls.technique)

    def _cast(self, audience: CastAudience):
        """Resolve a self-targeted cast with a stubbed audience; return the request."""
        with patch(
            "world.magic.services.cast_observation.resolve_cast_audience",
            return_value=audience,
        ):
            return request_technique_cast(
                scene=self.scene,
                initiator_persona=self.caster,
                technique=self.technique,
            ).request

    def _log_for(self, persona) -> list[Interaction]:
        """What this persona's scene log actually returns — the reader's side."""
        account = _account_playing(persona)
        return list(
            Interaction.objects.visible_to(account, persona_ids=[persona.pk]).filter(
                scene=self.scene
            )
        )

    def _concealed_audience(self, *, full, vague):
        return CastAudience(concealed=True, full=list(full), vague=list(vague))

    def test_detector_sees_the_full_outcome_pose(self) -> None:
        """A strong detector reads exactly what an overt cast would have shown."""
        self._cast(self._concealed_audience(full=[self.caster, self.detector], vague=[]))
        contents = [i.content for i in self._log_for(self.detector)]
        self.assertTrue(any(self.technique.name in c for c in contents))

    def test_marginal_detector_gets_only_the_vague_line(self) -> None:
        """They know something was worked — not by whom, not what."""
        self._cast(self._concealed_audience(full=[self.caster], vague=[self.marginal]))
        contents = [i.content for i in self._log_for(self.marginal)]
        self.assertEqual(contents, [render_vague_cast_narration()])

    def test_bystander_sees_neither_interaction(self) -> None:
        """The whole point. Nothing in their scene log, ever."""
        self._cast(
            self._concealed_audience(full=[self.caster, self.detector], vague=[self.marginal])
        )
        self.assertEqual(self._log_for(self.bystander), [])

    def test_the_action_interaction_is_concealed_too(self) -> None:
        """The caster's ACTION row carries the technique name on its own.

        Asserts both directions: the negative (a bystander never sees it) AND the
        positive (the caster and a full-detail detector CAN read it back). The positive
        leg matters because create_action_interaction_core never pins writer_account_id
        (unlike create_interaction) -- the caster's own read access rests entirely on
        being included in the receiver rows the concealment block bulk-creates.
        """
        request = self._cast(self._concealed_audience(full=[self.caster, self.detector], vague=[]))
        action_interaction = request.action_interaction
        self.assertEqual(action_interaction.visibility, InteractionVisibility.PERCEIVED_ONLY)
        self.assertIn(action_interaction, self._log_for(self.caster))
        self.assertIn(action_interaction, self._log_for(self.detector))
        self.assertNotIn(action_interaction, self._log_for(self.bystander))

    def test_vague_line_names_neither_caster_nor_technique(self) -> None:
        """The attribution boundary, asserted on content rather than on tier."""
        line = render_vague_cast_narration()
        self.assertNotIn(self.caster.name, line)
        self.assertNotIn(self.technique.name, line)

    def test_no_vague_interaction_when_nobody_marginally_detected(self) -> None:
        """One interaction, not two, when the vague tier is empty."""
        self._cast(self._concealed_audience(full=[self.caster], vague=[]))
        outcomes = Interaction.objects.filter(scene=self.scene, mode=InteractionMode.OUTCOME)
        self.assertEqual(outcomes.count(), 1)

    def test_unconcealed_cast_is_unchanged(self) -> None:
        """Zero concealment: DEFAULT visibility, no receiver rows, room-heard."""
        self._cast(CastAudience(concealed=False, full=[], vague=[]))
        pose = Interaction.objects.get(scene=self.scene, mode=InteractionMode.OUTCOME)
        self.assertEqual(pose.visibility, InteractionVisibility.DEFAULT)
        self.assertFalse(pose.receivers.exists())
        self.assertIn(pose, self._log_for(self.bystander))
