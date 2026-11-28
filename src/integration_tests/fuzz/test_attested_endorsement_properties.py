"""Fuzz: endorsements, the proposals that wait for the poser, and undoing a reward (#5327).

Each class below holds one rule of the design, quoted in the maintainer's words from the issue.
Every example builds its players, scene and poses fresh with factories and calls our own
functions (``create_pose_endorsement``, ``change_pose_endorsement``, ``accept_pose_proposal``,
``settle_weekly_pot``, ``undo_resonance_grant``) or the real endpoint; nothing is patched. The
shared catalog (six resonances under the three affinities, one staff account) lives once in
``setUpTestData``: a Hypothesis test's own ``setUp`` runs outside any transaction, so it would
leak rows between examples, while each example's own rows roll back with it.

A pose is endorsed by another player present in its scene. ``player`` gives a character held
by its own account, which is what the alt-guard and the scene checks read.

Left to the coordinator's live run: the weekly mark table, fatigue, pledge favor and
achievements are not touched by undo, and this file checks the part of that the ledger shows
(fatigue, balance, lifetime and the reflection), not favor or achievements, which need an
authored pledge and an authored achievement to be worth reading.
"""

from __future__ import annotations

from evennia.accounts.models import AccountDB
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.models import CharacterSheet
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.constants import GainSource, ReflectionChoice
from world.magic.exceptions import EndorsementValidationError, ResonanceUndoError
from world.magic.factories import (
    CharacterResonanceFactory,
    PoseResonanceReachFactory,
    RecordedActFactory,
    ResonanceFactory,
    ensure_conversion_pairs,
)
from world.magic.models import (
    CharacterResonance,
    PoseEndorsement,
    Reflection,
    ResonanceGrant,
)
from world.magic.services.gain import (
    accept_pose_proposal,
    account_for_sheet,
    change_pose_endorsement,
    create_pose_endorsement,
    decline_pose_proposal,
    get_resonance_gain_config,
    resonance_weekly_settlement_tick,
    settle_weekly_pot,
)
from world.magic.services.reflection import record_reflection, reflectable_for
from world.magic.services.resonance import grant_resonance
from world.magic.services.undo import may_undo_grant, undo_resonance_grant
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import InteractionVisibility
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)
from world.scenes.models import Interaction, Scene

# Two resonances per affinity. The key is what a strategy draws.
RESONANCE_KEYS = ("heroic 1", "heroic 2", "primal 1", "primal 2", "villain 1", "villain 2")
AFFINITY_OF = {
    "heroic 1": "celestial",
    "heroic 2": "celestial",
    "primal 1": "primal",
    "primal 2": "primal",
    "villain 1": "abyssal",
    "villain 2": "abyssal",
}
# A pose can be left at its default, read only by those who perceived it, or very private.
VISIBILITIES = (
    InteractionVisibility.DEFAULT,
    InteractionVisibility.PERCEIVED_ONLY,
    InteractionVisibility.VERY_PRIVATE,
)


class _Table:
    """The shared builder for the properties below (a mixin for the test classes)."""

    @classmethod
    def setUpTestData(cls) -> None:
        celestial, primal, abyssal = ensure_conversion_pairs()
        affinities = {"celestial": celestial, "primal": primal, "abyssal": abyssal}
        cls.resonances = {
            key: ResonanceFactory(name=key.title(), affinity=affinities[AFFINITY_OF[key]])
            for key in RESONANCE_KEYS
        }
        cls.staff = AccountFactory(username="attested_staff", is_staff=True)

    def no_bonus_check(self) -> None:
        """Turn the bonus check off: the gain config is an idmapper singleton an earlier
        example may have changed."""
        cfg = get_resonance_gain_config()
        cfg.bonus_check_type = None
        cfg.save()

    def player(self) -> tuple[CharacterSheet, AccountDB]:
        """A character held by its own account."""
        sheet = RosterTenureFactory().roster_entry.character_sheet
        account = account_for_sheet(sheet)
        assert account is not None
        return sheet, account

    def scene_with(self, *accounts: AccountDB) -> Scene:
        """A scene every one of ``accounts`` has joined as a plain participant."""
        scene = SceneFactory()
        for account in accounts:
            SceneParticipationFactory(scene=scene, account=account)
        return scene

    def pose(
        self,
        scene: Scene,
        poser: CharacterSheet,
        visibility: str = InteractionVisibility.DEFAULT,
    ) -> Interaction:
        return InteractionFactory(scene=scene, persona=poser.primary_persona, visibility=visibility)

    def marked_grant(self, sheet: CharacterSheet, key: str, amount: int) -> ResonanceGrant:
        """One gain a mark would have paid, written through ``grant_resonance``."""
        ledger: list[ResonanceGrant] = []
        grant_resonance(
            sheet,
            self.resonances[key],
            amount,
            source=GainSource.MARKED_ACT,
            ledger_out=ledger,
        )
        return ledger[-1]

    def grants_of(self, sheet: CharacterSheet) -> list[ResonanceGrant]:
        return list(ResonanceGrant.objects.filter(character_sheet=sheet))


class BareReachPaysOnlyWhenEndorsed(_Table, HypothesisTestCase):
    """A pose that reaches and points at no act pays nothing until another player endorses it.

    Maintainer: "pose with no action probably should only pay when endorsed".
    """

    @settings(max_examples=25, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), poser_has_it=st.booleans())
    def test_a_reach_pays_nothing_at_once_and_only_a_settled_endorsement_pays_it(
        self, key: str, poser_has_it: bool
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        endorser, endorser_account = self.player()
        scene = self.scene_with(poser_account, endorser_account)
        pose = self.pose(scene, poser)
        PoseResonanceReachFactory(interaction=pose, resonance=self.resonances[key])
        if poser_has_it:
            CharacterResonanceFactory(character_sheet=poser, resonance=self.resonances[key])

        # The reach alone pays nothing.
        self.assertEqual(self.grants_of(poser), [])

        # The poser's own endorsement is refused, and so is another character of her player.
        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(poser, pose)
        alt = RosterTenureFactory(
            player_data=poser.roster_entry.tenures.first().player_data
        ).roster_entry.character_sheet
        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(alt, pose)
        self.assertFalse(PoseEndorsement.objects.exists())

        # Another player's endorsement confirms the resonance she named and does not wait.
        endorsement = create_pose_endorsement(endorser, pose)
        self.assertEqual(endorsement.resonance, self.resonances[key])
        self.assertFalse(endorsement.awaiting_acceptance)
        self.assertEqual(self.grants_of(poser), [])

        # The weekly settlement is what pays it.
        result = settle_weekly_pot(endorser)
        self.assertEqual(result.endorsements_settled, 1)
        paid = self.grants_of(poser)
        self.assertEqual(len(paid), 1)
        self.assertEqual(paid[0].source, GainSource.POSE_ENDORSEMENT)
        self.assertEqual(paid[0].resonance, self.resonances[key])
        self.assertGreater(paid[0].amount, 0)

    @settings(max_examples=20, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), amount=st.integers(1, 80))
    def test_a_pose_whose_mark_already_paid_cannot_also_be_endorsed(
        self, key: str, amount: int
    ) -> None:
        """A pose pays once: the endorsement half of "they point to an act" (the mark paid)."""
        self.no_bonus_check()
        poser, poser_account = self.player()
        endorser, endorser_account = self.player()
        scene = self.scene_with(poser_account, endorser_account)
        pose = self.pose(scene, poser)
        grant = self.marked_grant(poser, key, amount)
        RecordedActFactory(character_sheet=poser, marked_grant=grant, marked_interaction=pose)

        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, pose, self.resonances[key])
        self.assertFalse(PoseEndorsement.objects.exists())


class AProposalWaitsForThePoser(_Table, HypothesisTestCase):
    """A witness's pick on a pose that named no resonance pays only once the poser accepts it.

    Maintainer: "I'd probably have it accepted if the player agrees"; "One list, she accepts,
    but make it easy for an endorser to change when they make a mistake: it'll be pretty common
    for someone to click on the wrong one imo".
    """

    @settings(max_examples=25, deadline=None)
    @given(
        first=st.sampled_from(RESONANCE_KEYS),
        second=st.sampled_from(RESONANCE_KEYS),
        poser_has_first=st.booleans(),
        answerer=st.sampled_from(("poser", "gm", "staff")),
    )
    def test_any_pick_waits_and_settles_only_after_an_answer_and_a_change_waits_again(
        self, first: str, second: str, poser_has_first: bool, answerer: str
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        endorser, endorser_account = self.player()
        gm_account = AccountFactory(username=f"attested_gm_{poser.pk}")
        scene = self.scene_with(poser_account, endorser_account)
        SceneGMParticipationFactory(scene=scene, account=gm_account)
        pose = self.pose(scene, poser)
        if poser_has_first:
            CharacterResonanceFactory(character_sheet=poser, resonance=self.resonances[first])
        answers = {"poser": poser_account, "gm": gm_account, "staff": self.staff}[answerer]

        # Any resonance is accepted as a pick, in her aura or not, and it waits.
        proposal = create_pose_endorsement(endorser, pose, self.resonances[first])
        self.assertTrue(proposal.awaiting_acceptance)
        self.assertEqual(proposal.resonance, self.resonances[first])

        # A waiting row never settles: not by the pot, not by the weekly tick.
        result = settle_weekly_pot(endorser)
        self.assertEqual((result.endorsements_settled, result.total_granted), (0, 0))
        summary = resonance_weekly_settlement_tick()
        self.assertEqual(summary.total_endorsements_settled, 0)
        self.assertEqual(self.grants_of(poser), [])
        proposal.refresh_from_db()
        self.assertIsNone(proposal.settled_at)

        # The endorser may not answer for the poser, nor may a player with no part in the scene.
        with self.assertRaises(EndorsementValidationError):
            accept_pose_proposal(proposal, endorser_account)
        with self.assertRaises(EndorsementValidationError):
            decline_pose_proposal(proposal, endorser_account)
        self.assertTrue(PoseEndorsement.objects.get(pk=proposal.pk).awaiting_acceptance)

        # Accepted, it is no longer waiting. Changing the pick sends it back to waiting.
        accepted = accept_pose_proposal(proposal, answers)
        self.assertFalse(accepted.awaiting_acceptance)
        changed = change_pose_endorsement(accepted, self.resonances[second], endorser_account)
        self.assertEqual(changed.resonance, self.resonances[second])
        self.assertEqual(changed.awaiting_acceptance, first != second)
        if first != second:
            self.assertEqual(settle_weekly_pot(endorser).endorsements_settled, 0)
            self.assertEqual(self.grants_of(poser), [])
            accept_pose_proposal(changed, answers)

        # Once answered it settles, and pays the pick it holds now.
        self.assertEqual(settle_weekly_pot(endorser).endorsements_settled, 1)
        paid = self.grants_of(poser)
        self.assertEqual(len(paid), 1)
        self.assertEqual(paid[0].resonance, self.resonances[second])
        self.assertEqual(paid[0].source, GainSource.POSE_ENDORSEMENT)

        # A settled row can no longer change.
        with self.assertRaises(EndorsementValidationError):
            change_pose_endorsement(changed, self.resonances[first], endorser_account)

    @settings(max_examples=15, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS))
    def test_a_declined_pick_is_gone_and_pays_nothing(self, key: str) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        endorser, endorser_account = self.player()
        scene = self.scene_with(poser_account, endorser_account)
        pose = self.pose(scene, poser)
        proposal = create_pose_endorsement(endorser, pose, self.resonances[key])

        decline_pose_proposal(proposal, poser_account)

        self.assertFalse(PoseEndorsement.objects.exists())
        self.assertEqual(settle_weekly_pot(endorser).endorsements_settled, 0)
        self.assertEqual(self.grants_of(poser), [])


class UndoTakesBackWhatTheRewardPaid(_Table, HypothesisTestCase):
    """Undoing a reward lowers the totals by what it paid, never below nothing, and keeps the row.

    Maintainer, on the rules for undo: "4. Sounds fine."; "we could nullify it and chide them".
    """

    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        amount=st.integers(1, 80),
        balance_before=st.integers(0, 150),
        lifetime_before=st.integers(0, 150),
        fatigue=st.integers(0, 40),
    )
    def test_both_totals_fall_by_the_amount_and_stop_at_zero(
        self, key: str, amount: int, balance_before: int, lifetime_before: int, fatigue: int
    ) -> None:
        self.no_bonus_check()
        sheet, _account = self.player()
        reflected = self.marked_grant(sheet, key, amount)
        waiting = self.marked_grant(sheet, key, amount)
        for grant in (reflected, waiting):
            RecordedActFactory(character_sheet=sheet, marked_grant=grant)
        record_reflection(sheet, writing=None, grant=reflected, choice=ReflectionChoice.EMBRACE)
        # What she has now: some already spent, some lowered by an earlier conversion.
        held = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.resonances[key])
        held.balance = balance_before
        held.lifetime_earned = lifetime_before
        held.save(update_fields=["balance", "lifetime_earned"])
        pool = get_or_create_fatigue_pool(sheet)
        pool.physical_current = fatigue
        pool.save(update_fields=["physical_current"])
        ledger_rows = ResonanceGrant.objects.filter(character_sheet=sheet).count()
        undone_amount = reflected.amount
        self.assertIn(waiting.pk, [d.grant.pk for d in reflectable_for(sheet).deeds])

        undo_resonance_grant(reflected, self.staff)
        undo_resonance_grant(waiting, self.staff)

        held.refresh_from_db()
        self.assertEqual(held.balance, max(0, balance_before - 2 * undone_amount))
        self.assertEqual(held.lifetime_earned, max(0, lifetime_before - 2 * undone_amount))
        # The ledger keeps every row, stamped, and the act stays spent so it cannot pay again.
        self.assertEqual(ResonanceGrant.objects.filter(character_sheet=sheet).count(), ledger_rows)
        for grant in (reflected, waiting):
            grant.refresh_from_db()
            self.assertIsNotNone(grant.nullified_at)
            self.assertEqual(grant.nullified_by, self.staff)
            self.assertEqual(grant.amount, undone_amount)
            self.assertEqual(grant.marked_act.marked_grant_id, grant.pk)
        # Fatigue stays, a waiting reflection is withdrawn, and the deed drops out of the list.
        pool.refresh_from_db()
        self.assertEqual(pool.physical_current, fatigue)
        self.assertFalse(Reflection.objects.filter(grant=reflected).exists())
        self.assertEqual(reflectable_for(sheet).deeds, ())

    @settings(max_examples=15, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), amount=st.integers(1, 80))
    def test_a_reward_cannot_be_undone_twice(self, key: str, amount: int) -> None:
        self.no_bonus_check()
        sheet, _account = self.player()
        grant = self.marked_grant(sheet, key, amount)
        undo_resonance_grant(grant, self.staff)
        held = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.resonances[key])
        totals = (held.balance, held.lifetime_earned)

        with self.assertRaises(ResonanceUndoError):
            undo_resonance_grant(grant, self.staff)

        held.refresh_from_db()
        self.assertEqual((held.balance, held.lifetime_earned), totals)


class OnlyStaffAndTheSceneGMUndo(_Table, HypothesisTestCase):
    """Only staff and the scene's own GM undo a reward; a co-owner who is not its GM cannot.

    An accepted default, not the maintainer's own words: "Undo belongs to staff and the scene's
    actual GM, not co-owners" (every player present at scene start is an owner today).
    """

    @settings(max_examples=20, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        amount=st.integers(1, 80),
        visibility=st.sampled_from(VISIBILITIES),
    )
    def test_the_gm_and_staff_undo_and_nobody_else_does(
        self, key: str, amount: int, visibility: str
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        scene = self.scene_with(poser_account)
        gm = AccountFactory(username=f"attested_scene_gm_{poser.pk}")
        owner = AccountFactory(username=f"attested_scene_owner_{poser.pk}")
        guest = AccountFactory(username=f"attested_scene_guest_{poser.pk}")
        stranger = AccountFactory(username=f"attested_stranger_{poser.pk}")
        SceneGMParticipationFactory(scene=scene, account=gm)
        SceneOwnerParticipationFactory(scene=scene, account=owner)
        SceneParticipationFactory(scene=scene, account=guest)
        pose = self.pose(scene, poser, visibility)
        grant = self.marked_grant(poser, key, amount)
        RecordedActFactory(character_sheet=poser, marked_grant=grant, marked_interaction=pose)

        # The GM undoes it unless the pose is one nobody outside it may read; staff always do.
        readable = visibility != InteractionVisibility.VERY_PRIVATE
        self.assertEqual(may_undo_grant(gm, grant), readable)
        self.assertTrue(may_undo_grant(self.staff, grant))
        for outsider in (owner, guest, stranger, poser_account):
            self.assertFalse(may_undo_grant(outsider, grant))
            with self.assertRaises(ResonanceUndoError):
                undo_resonance_grant(grant, outsider)
        grant.refresh_from_db()
        self.assertIsNone(grant.nullified_at)

        # The endpoint agrees: nothing for a co-owner, the GM only for a pose she can read.
        client = APIClient()
        url = f"/api/magic/resonance-grants/{grant.pk}/undo/"
        for outsider in (owner, guest, stranger, poser_account):
            client.force_authenticate(user=outsider)
            self.assertIn(client.post(url).status_code, (403, 404))
        client.force_authenticate(user=gm)
        status_for_gm = client.post(url).status_code
        self.assertEqual(status_for_gm, 200 if readable else 403)
        grant.refresh_from_db()
        self.assertEqual(grant.nullified_by, gm if readable else None)
