"""Concealed-cast privacy (#2710) — the PERCEIVED_ONLY visibility tier.

ADR-0033: the privacy guarantee ships in the same increment as the feature. These
tests assert the tier from the reader's side — what each viewer's scene log returns.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction


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
