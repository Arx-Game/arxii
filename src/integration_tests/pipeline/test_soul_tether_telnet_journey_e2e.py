"""Telnet E2E: form a Soul Tether via the ritual session lifecycle (#1449).

Drives the full draft → join → fire journey through CmdRitual against
full-fidelity eligible-pair fixtures (mirroring test_soul_tether_flow.py's
_make_eligible_pair) and asserts the real bond forms in the DB — proving
the bonding loop runs end-to-end via telnet, converging on the same
draft_session / accept_session / fire_session service seam the web uses.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from commands.ritual import CmdRitual
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.models import ConditionInstance
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
)
from world.magic.models import Thread
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import CharacterRelationship

_ABYSSAL = "Abyssal"
_PRIMAL = "Primal"


def _run(cmd_cls: type, caller: object, args: str = "") -> object:
    """Helper: build and run a command instance (mirrors ritual-session E2E)."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


def _set_aura(sheet: object, *, celestial: str, primal: str, abyssal: str) -> None:
    char = sheet.character
    defaults = {
        "celestial": Decimal(celestial),
        "primal": Decimal(primal),
        "abyssal": Decimal(abyssal),
    }
    try:
        aura = char.aura
        for key, value in defaults.items():
            setattr(aura, key, value)
        aura.save()
    except AttributeError:
        CharacterAuraFactory(character=char, **defaults)


def _grant_track_unlock(sheet: object, track: object) -> object:
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        unlock_trait=None,
    )
    return CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _make_active_relationship(source: object, target: object) -> object:
    CharacterRelationshipFactory(source=source, target=target, is_pending=False)
    return CharacterRelationshipFactory(source=target, target=source, is_pending=False)


class SoulTetherTelnetJourneyTests(TestCase):
    """draft → join → fire through CmdRitual forms a real Soul Tether."""

    def setUp(self) -> None:
        # setUp (not setUpTestData) avoids the DbHolder deepcopy flake in CI shards.
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()
        self.abyssal_affinity = AffinityFactory(name=_ABYSSAL)
        self.resonance = ResonanceFactory(affinity=self.abyssal_affinity)

        # Sinner: Abyssal-primary with a RELATIONSHIP_TRACK ThreadWeavingUnlock.
        self.sinner_char = CharacterFactory(db_key="JourneySinner")
        self.sinner_sheet = CharacterSheetFactory(character=self.sinner_char)
        _set_aura(self.sinner_sheet, celestial="10.00", primal="10.00", abyssal="80.00")
        _grant_track_unlock(self.sinner_sheet, self.track)
        # Sinner must have claimed the resonance (accept_soul_tether resonance gate).
        CharacterResonanceFactory(character_sheet=self.sinner_sheet, resonance=self.resonance)

        # Sineater: Primal-primary.
        self.sineater_char = CharacterFactory(db_key="JourneySineater")
        self.sineater_sheet = CharacterSheetFactory(character=self.sineater_char)
        _set_aura(self.sineater_sheet, celestial="10.00", primal="80.00", abyssal="10.00")

        _make_active_relationship(self.sinner_sheet, self.sineater_sheet)

    def test_formation_journey(self) -> None:
        """draft (Sinner, role=sinner) → join (Sineater, role=sineater) → fire forms bond."""
        # 1. Sinner drafts the soul-tether session.
        cmd = _run(
            CmdRitual,
            self.sinner_char,
            f"draft accept_soul_tether invite=JourneySineater "
            f"role=sinner resonance={self.resonance.name} writeup=A bond sworn in shadow",
        )
        cmd.caller.search = MagicMock(return_value=self.sineater_char)
        cmd.func()
        from world.magic.models.sessions import RitualSession

        session = RitualSession.objects.get(ritual__name="accept_soul_tether")
        self.assertEqual(session.initiator, self.sinner_sheet)
        self.assertEqual(session.session_kwargs["resonance_id"], self.resonance.pk)
        self.assertEqual(session.session_kwargs["writeup"], "A bond sworn in shadow")
        initiator_part = session.participants.get(character_sheet=self.sinner_sheet)
        self.assertEqual(
            initiator_part.participant_kwargs["soul_tether_role"], SoulTetherRole.SINNER
        )

        # 2. Sineater joins, declaring their role.
        cmd = _run(CmdRitual, self.sineater_char, f"join {session.pk} role=sineater")
        cmd.func()
        invitee_part = session.participants.get(character_sheet=self.sineater_sheet)
        self.assertEqual(
            invitee_part.participant_kwargs["soul_tether_role"], SoulTetherRole.SINEATER
        )

        # 3. Sinner fires — the real bond forms.
        cmd = _run(CmdRitual, self.sinner_char, f"fire {session.pk}")
        cmd.func()

        rel_out = CharacterRelationship.objects.get(
            source=self.sinner_sheet, target=self.sineater_sheet
        )
        rel_in = CharacterRelationship.objects.get(
            source=self.sineater_sheet, target=self.sinner_sheet
        )
        self.assertTrue(rel_out.is_soul_tether)
        self.assertTrue(rel_in.is_soul_tether)
        self.assertEqual(rel_out.soul_tether_role, SoulTetherRole.SINNER)
        self.assertEqual(rel_in.soul_tether_role, SoulTetherRole.SINEATER)

        # Sinner's RELATIONSHIP_CAPSTONE Thread exists, anchored to this bond + resonance.
        capstone = rel_out.capstones.filter(is_ritual_capstone=True).first()
        self.assertIsNotNone(capstone)
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sinner_sheet,
                target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
                target_capstone=capstone,
                resonance=self.resonance,
                retired_at__isnull=True,
            ).exists()
        )

        # The bond's ritual capstone record formed.
        self.assertTrue(
            rel_out.capstones.filter(
                is_ritual_capstone=True, ritual__name="accept_soul_tether"
            ).exists()
        )

        # SoulTetherActive condition installed on the Sinner.
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.sinner_char, condition__name="Soul Tether Active"
            ).exists()
        )

        # Session is consumed on successful fire.
        self.assertFalse(RitualSession.objects.filter(pk=session.pk).exists())
