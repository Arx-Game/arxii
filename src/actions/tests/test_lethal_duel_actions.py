"""Tests for ProposeLethalDuelAction (#3068) — the telnet/GM-verb face of a
GM-initiated lethal duel proposal, and the accept/decline consent loop it
feeds into.

Scenarios covered:
  (a) GM (scene participation is_gm=True) proposes → PENDING is_lethal
      DuelChallenge created, no encounter yet.
  (b) Staff proposes even without scene participation.
  (c) Non-GM PC is refused; no challenge created.
  (d) Target must be present in the actor's room.
  (e) Bad tier (not ELITE/BOSS/HERO_KILLER) is refused.
  (f) Full loop: propose → AcceptChallengeAction (the player's own consent
      step) → lethal CombatEncounter created.
  (g) Full loop: propose → DeclineChallengeAction → no encounter created.
"""

from __future__ import annotations

import django.test

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import DuelChallengeStatus, OpponentTier
from world.combat.factories import OpponentTierTemplateFactory, ThreatPoolFactory
from world.combat.models import CombatEncounter, DuelChallenge
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _make_room() -> object:
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


def _make_pc(name: str, room: object) -> tuple:
    """Return (actor ObjectDB, CharacterSheet, AccountDB) with an active RosterTenure."""
    account = AccountFactory(username=name)
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data__account=account)
    return actor, sheet, account


class ProposeLethalDuelActionGMGateTests(django.test.TestCase):
    """GM/staff standing gates ProposeLethalDuelAction."""

    def setUp(self) -> None:
        self.room = _make_room()
        self.gm_actor, self.gm_sheet, self.gm_account = _make_pc("GmChar", self.room)
        self.target_actor, self.target_sheet, self.target_account = _make_pc(
            "TargetChar", self.room
        )
        self.scene = SceneFactory(location=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        self.threat_pool = ThreatPoolFactory()

    def _run(self, actor: object, **kwargs: object):
        from actions.registry import get_action

        defaults = {
            "character_sheet_id": str(self.target_sheet.pk),
            "opponent_name": "TheWidowAshgrave",
            "tier": OpponentTier.ELITE,
            "threat_pool_id": str(self.threat_pool.pk),
        }
        defaults.update(kwargs)
        return get_action("propose_lethal_duel").run(actor, **defaults)

    def test_scene_gm_proposes_creates_pending_lethal_challenge(self) -> None:
        result = self._run(self.gm_actor)

        self.assertTrue(result.success, msg=result.message)
        challenge = DuelChallenge.objects.get(challenged_sheet=self.target_sheet)
        self.assertTrue(challenge.is_lethal)
        self.assertIsNone(challenge.challenger_sheet_id)
        self.assertEqual(challenge.status, DuelChallengeStatus.PENDING)
        self.assertEqual(CombatEncounter.objects.count(), 0)

    def test_staff_proposes_without_scene_participation(self) -> None:
        staff_actor, _staff_sheet, staff_account = _make_pc("StaffChar", self.room)
        staff_account.is_staff = True
        staff_account.save(update_fields=["is_staff"])

        result = self._run(staff_actor)

        self.assertTrue(result.success, msg=result.message)
        self.assertTrue(
            DuelChallenge.objects.filter(
                challenged_sheet=self.target_sheet, is_lethal=True
            ).exists()
        )

    def test_non_gm_pc_refused(self) -> None:
        outsider_actor, _sheet, _account = _make_pc("OutsiderChar", self.room)

        result = self._run(outsider_actor)

        self.assertFalse(result.success)
        self.assertFalse(DuelChallenge.objects.filter(is_lethal=True).exists())

    def test_target_must_be_present_in_room(self) -> None:
        elsewhere = _make_room()
        _stranger_actor, stranger_sheet, _account = _make_pc("StrangerChar", elsewhere)

        result = self._run(self.gm_actor, character_sheet_id=str(stranger_sheet.pk))

        self.assertFalse(result.success)
        self.assertFalse(DuelChallenge.objects.filter(is_lethal=True).exists())

    def test_mook_tier_refused(self) -> None:
        result = self._run(self.gm_actor, tier=OpponentTier.MOOK)

        self.assertFalse(result.success)
        self.assertFalse(DuelChallenge.objects.filter(is_lethal=True).exists())


class ProposeLethalDuelAcceptDeclineLoopTests(django.test.TestCase):
    """The full GM-proposes → player-consents loop (#3068)."""

    def setUp(self) -> None:
        self.room = _make_room()
        self.gm_actor, self.gm_sheet, self.gm_account = _make_pc("GmChar2", self.room)
        self.target_actor, self.target_sheet, self.target_account = _make_pc(
            "TargetChar2", self.room
        )
        self.scene = SceneFactory(location=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        self.threat_pool = ThreatPoolFactory()
        # accept_challenge's opponent_kwargs carries no max_health — auto-scale
        # mode — which needs an authored OpponentTierTemplate row for ELITE.
        OpponentTierTemplateFactory(tier=OpponentTier.ELITE)

        from actions.registry import get_action

        propose_result = get_action("propose_lethal_duel").run(
            self.gm_actor,
            character_sheet_id=str(self.target_sheet.pk),
            opponent_name="TheWidowAshgrave",
            tier=OpponentTier.ELITE,
            threat_pool_id=str(self.threat_pool.pk),
        )
        self.assertTrue(propose_result.success, msg=propose_result.message)
        self.challenge = DuelChallenge.objects.get(challenged_sheet=self.target_sheet)

    def test_target_accepts_creates_lethal_encounter(self) -> None:
        from actions.registry import get_action

        result = get_action("accept").run(self.target_actor, challenge_id=self.challenge.pk)

        self.assertTrue(result.success, msg=result.message)
        encounter = CombatEncounter.objects.get(pk=result.data["encounter_id"])
        self.assertTrue(encounter.is_lethal)
        self.assertEqual(encounter.participants.get().character_sheet_id, self.target_sheet.pk)
        opponent = encounter.opponents.get()
        self.assertEqual(opponent.name, "TheWidowAshgrave")

    def test_target_declines_creates_no_encounter(self) -> None:
        from actions.registry import get_action

        result = get_action("decline").run(self.target_actor, challenge_id=self.challenge.pk)

        self.assertTrue(result.success, msg=result.message)
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, DuelChallengeStatus.DECLINED)
        self.assertEqual(CombatEncounter.objects.count(), 0)

    def test_gm_cannot_accept_on_the_players_behalf(self) -> None:
        """Only the challenged PC may accept — the GM has no accept standing (#3068)."""
        from actions.registry import get_action

        result = get_action("accept").run(self.gm_actor, challenge_id=self.challenge.pk)

        self.assertFalse(result.success)
        self.assertEqual(CombatEncounter.objects.count(), 0)
