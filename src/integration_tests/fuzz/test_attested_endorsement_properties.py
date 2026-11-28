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

from actions.constants import ActionCategory
from evennia_extensions.factories import AccountFactory
from web.admin.being_service.live import resonance_context
from world.character_sheets.models import CharacterSheet
from world.fatigue.services import get_fatigue_capacity, get_or_create_fatigue_pool
from world.fatigue.tests import setup_stat
from world.game_clock.week_services import get_current_game_week
from world.magic.constants import GainSource, ReflectionChoice
from world.magic.exceptions import EndorsementValidationError, ResonanceUndoError
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTypeFactory,
    PoseEndorsementFactory,
    PoseResonanceReachFactory,
    RecordedActFactory,
    ResonanceFactory,
    SceneEntryEndorsementFactory,
    StylePresentationEndorsementFactory,
    ensure_conversion_pairs,
)
from world.magic.models import (
    Affinity,
    CharacterResonance,
    DramaticMomentTag,
    PoseEndorsement,
    Reflection,
    Resonance,
    ResonanceGrant,
)
from world.magic.services.gain import (
    accept_pose_proposal,
    account_for_sheet,
    change_pose_endorsement,
    create_dramatic_moment_tag,
    create_entry_flourish,
    create_pose_endorsement,
    decline_pose_proposal,
    get_resonance_gain_config,
    resonance_weekly_settlement_tick,
    settle_weekly_pot,
)
from world.magic.services.impulses import earned_in_scene
from world.magic.services.marking import weekly_percent_paid
from world.magic.services.reflection import record_reflection, reflectable_for
from world.magic.services.resonance import grant_resonance
from world.magic.services.undo import may_undo_grant, undo_resonance_grant
from world.narrative.models import NarrativeMessageDelivery
from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory, RosterTenureFactory
from world.scenes.constants import InteractionVisibility
from world.scenes.factories import (
    InteractionFactory,
    InteractionTargetPersonaFactory,
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
    SceneParticipationFactory,
)
from world.scenes.models import Interaction, Scene
from world.traits.factories import StatTraitFactory
from world.traits.models import TraitCategory
from world.worship.factories import (
    BeingResonanceFactory,
    DevotionStandingFactory,
    WorshippedBeingFactory,
)

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

        # The endorser may not answer for the poser, whoever else may.
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

    @settings(max_examples=20, deadline=None)
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
        # The week exists before the grants, as in play: a fresh table starts one at "now".
        get_current_game_week()
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
        standing = weekly_percent_paid(sheet)
        self.assertEqual((standing.gained, standing.marks), (2 * undone_amount, 2))
        # The staff page that counts a being's recent grants to its worshippers is a reader too.
        being_row = BeingResonanceFactory(
            being=WorshippedBeingFactory(), resonance=self.resonances[key]
        )
        DevotionStandingFactory(being=being_row.being, character_sheet=sheet)
        self.assertTrue(resonance_context(being_row.being)[being_row.pk].grants.startswith("2 "))

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
        standing = weekly_percent_paid(sheet)
        self.assertEqual((standing.gained, standing.marks), (0, 0))
        self.assertEqual(resonance_context(being_row.being)[being_row.pk].grants, "none yet")

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

    @settings(max_examples=15, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), amount=st.integers(1, 80))
    def test_an_undone_reward_is_not_something_she_earned_in_the_scene(
        self, key: str, amount: int
    ) -> None:
        """Maintainer: "we could nullify it and chide them". The Compulsion that lifts when she
        earns the resonance it wants reads the ledger, so a reward that was undone must no longer
        count as earned: the penalty comes back."""
        self.no_bonus_check()
        sheet, account = self.player()
        scene = self.scene_with(account)
        grant = self.marked_grant(sheet, key, amount)
        RecordedActFactory(character_sheet=sheet, marked_grant=grant)
        resonance = self.resonances[key]
        self.assertTrue(earned_in_scene(sheet, resonance, scene))

        undo_resonance_grant(grant, self.staff)

        self.assertFalse(earned_in_scene(sheet, resonance, scene))


class GainsWithNoActTireTheirPayer(_Table, HypothesisTestCase):
    """An endorsed pose, an accepted pick and a GM's tag tire whoever pays, as a mark does.

    Maintainer: "for primal, the person getting it, for abyssal their victim, for celestial the
    caster". These gains point at no act, so the pose's single named target is the victim, and a
    pose that names none or several has none. A payer who is low pays what they can and the gain
    shrinks to match; one with nothing left pays nothing and the gain is not paid.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # The fatigue capacity of a character comes from these two stats.
        StatTraitFactory(name="composure", category=TraitCategory.SOCIAL)
        StatTraitFactory(name="willpower", category=TraitCategory.META)

    def worn_player(self, worn: int) -> tuple[CharacterSheet, AccountDB]:
        """A character with set-up stats and ``worn`` social fatigue taken (inside capacity)."""
        sheet, account = self.player()
        setup_stat(sheet.character, "composure", 20, TraitCategory.SOCIAL)
        setup_stat(sheet.character, "willpower", 20, TraitCategory.META)
        capacity = get_fatigue_capacity(sheet, ActionCategory.SOCIAL)
        pool = get_or_create_fatigue_pool(sheet)
        pool.set_current(ActionCategory.SOCIAL, worn % (capacity + 1))
        pool.save()
        return sheet, account

    def social(self, sheet: CharacterSheet) -> int:
        return get_or_create_fatigue_pool(sheet).get_current(ActionCategory.SOCIAL)

    def payer_and_room(
        self,
        *,
        key: str,
        gainer: CharacterSheet,
        targets: list[CharacterSheet],
        before: dict[int, int],
    ) -> tuple[CharacterSheet | None, int | None]:
        """Who pays and how much room she has (capacity minus what is taken minus one, never
        below 0), from the spec's rule alone. No payer is None: an Abyssal gain from a pose
        that names no one or several has no victim."""
        payer: CharacterSheet | None = gainer
        if AFFINITY_OF[key] == "abyssal":
            payer = targets[0] if len(targets) == 1 else None
        if payer is None:
            return None, None
        capacity = get_fatigue_capacity(payer, ActionCategory.SOCIAL)
        return payer, max(0, capacity - before[payer.pk] - 1)

    def setup_gain(
        self, key: str, cost: int, pot: int, worn: tuple[int, int, int], target_count: int
    ) -> tuple[CharacterSheet, CharacterSheet, list[CharacterSheet], Interaction, Scene]:
        """A poser (the gainer), an endorser, the pose's targets and the pose they stand in."""
        self.no_bonus_check()
        cfg = get_resonance_gain_config()
        cfg.weekly_pot_per_character = pot
        cfg.save()
        # The row the code under test reads is the identity-mapped one, not the copy Django
        # hands a test method from ``setUpTestData``.
        affinity = Affinity.objects.get(pk=self.resonances[key].affinity_id)
        affinity.gain_fatigue = cost
        affinity.earn_rate_percent = 100
        affinity.save()
        poser, poser_account = self.worn_player(worn[0])
        endorser, endorser_account = self.player()
        targets = [self.worn_player(worn[1 + i])[0] for i in range(target_count)]
        scene = self.scene_with(poser_account, endorser_account)
        pose = self.pose(scene, poser)
        for target in targets:
            InteractionTargetPersonaFactory(interaction=pose, persona=target.primary_persona)
        return poser, endorser, targets, pose, scene

    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        cost=st.integers(1, 12),
        pot=st.integers(1, 60),
        worn=st.tuples(st.integers(0, 60), st.integers(0, 60), st.integers(0, 60)),
        target_count=st.integers(0, 2),
    )
    def test_an_endorsement_tires_the_payer_and_shrinks_to_what_they_can_pay(
        self,
        key: str,
        cost: int,
        pot: int,
        worn: tuple[int, int, int],
        target_count: int,
    ) -> None:
        """The payer follows the affinity and ends below capacity, nothing else is tired, and the
        endorsement pays the weekly share, or less when the payer has little room, or nothing at
        no room, in which case it is left unsettled for next week."""
        poser, endorser, targets, pose, _scene = self.setup_gain(key, cost, pot, worn, target_count)
        PoseResonanceReachFactory(interaction=pose, resonance=self.resonances[key])
        endorsement = create_pose_endorsement(endorser, pose)
        everyone = [poser, *targets]
        before = {sheet.pk: self.social(sheet) for sheet in everyone}
        payer, room = self.payer_and_room(key=key, gainer=poser, targets=targets, before=before)

        with self.captureOnCommitCallbacks(execute=True):
            settle_weekly_pot(endorser)

        endorsement.refresh_from_db()
        grants = self.grants_of(poser)
        paid = sum(g.amount for g in grants)
        self.assertLessEqual(paid, pot)
        if payer is None or room >= cost:
            self.assertEqual(paid, pot)
        if room == 0:
            self.assertEqual(paid, 0)
        # An endorsement that paid nothing stays unsettled (the endorser cannot make the same one
        # twice, so next week's settlement tries it again); one that paid is settled.
        self.assertEqual(endorsement.settled_at is None, paid == 0)
        self.assertEqual(len(grants), 1 if paid else 0)
        for sheet in everyone:
            pool = get_or_create_fatigue_pool(sheet)
            pool.refresh_from_db()
            if payer is None or sheet.pk != payer.pk:
                self.assertEqual(pool.get_current(ActionCategory.SOCIAL), before[sheet.pk])
        if payer is not None:
            self.assertLess(self.social(payer), get_fatigue_capacity(payer, ActionCategory.SOCIAL))
            if paid == 0:
                self.assertEqual(self.social(payer), before[payer.pk])
        if paid == 0:
            # Her player is told, even offline, that it will be tried again.
            told = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=poser)
            self.assertIn("next week's settlement", " ".join(d.message.body for d in told))
            self.assertTrue(self.settles_after_rest(endorsement, payer))

    def settles_after_rest(self, endorsement: PoseEndorsement, payer: CharacterSheet) -> bool:
        """Rest the payer and settle again: the endorsement is tried again and, her room now
        covering the cost (capacity is 26 here and a cost is at most 12), is settled."""
        pool = get_or_create_fatigue_pool(payer)
        pool.set_current(ActionCategory.SOCIAL, 0)
        pool.save()
        settle_weekly_pot(endorsement.endorser_sheet)
        endorsement.refresh_from_db()
        return endorsement.settled_at is not None

    @settings(max_examples=12, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        cost=st.integers(1, 12),
        pot=st.integers(1, 60),
        worn=st.tuples(st.integers(0, 60), st.integers(0, 60), st.integers(0, 60)),
        target_count=st.integers(0, 2),
    )
    def test_a_gms_tag_tires_the_payer_and_an_unpayable_tag_pays_nothing(
        self,
        key: str,
        cost: int,
        pot: int,
        worn: tuple[int, int, int],
        target_count: int,
    ) -> None:
        """A tag's payer follows the affinity and ends below capacity, nothing else is tired, and
        the tag pays at most its amount and all of it when the payer's room covers the cost. A
        payer with nothing left refuses it before any row exists, and once she has rested the
        same tag is not blocked by the refused one."""
        poser, _endorser, targets, pose, scene = self.setup_gain(key, cost, pot, worn, target_count)
        moment = DramaticMomentTypeFactory(resonance_amount=pot)
        everyone = [poser, *targets]
        before = {sheet.pk: self.social(sheet) for sheet in everyone}
        payer, room = self.payer_and_room(key=key, gainer=poser, targets=targets, before=before)

        def make_tag() -> DramaticMomentTag:
            return create_dramatic_moment_tag(
                character_sheet=poser,
                moment_type=moment,
                tagged_by=self.staff,
                scene=scene,
                interaction=pose,
                # The identity-mapped row, whose affinity carries the cost set above.
                resonance=Resonance.objects.get(pk=self.resonances[key].pk),
            )

        try:
            make_tag()
            refused = False
        except EndorsementValidationError:
            refused = True

        if room == 0:
            self.assertTrue(refused)
        if refused:
            # Refused before any row exists: no tag, no renown, no grant, no fatigue, and the
            # scene's cap for this type is not spent.
            self.assertFalse(DramaticMomentTag.objects.exists())
            self.assertEqual(self.grants_of(poser), [])
            for sheet in everyone:
                self.assertEqual(self.social(sheet), before[sheet.pk])
            # Once the payer has rested (capacity is 26 here and a cost is at most 12), the same
            # tag is no longer blocked and pays in full.
            pool = get_or_create_fatigue_pool(payer)
            pool.set_current(ActionCategory.SOCIAL, 0)
            pool.save()
            self.assertIsNotNone(make_tag().pk)
            self.assertEqual(sum(g.amount for g in self.grants_of(poser)), pot)
        else:
            paid = sum(g.amount for g in self.grants_of(poser))
            self.assertLessEqual(paid, pot)
            if payer is None or room >= cost:
                self.assertEqual(paid, pot)
            for sheet in everyone:
                if payer is None or sheet.pk != payer.pk:
                    self.assertEqual(self.social(sheet), before[sheet.pk])
            if payer is not None:
                self.assertLess(
                    self.social(payer), get_fatigue_capacity(payer, ActionCategory.SOCIAL)
                )

    @settings(max_examples=12, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        cost=st.integers(1, 12),
        pot=st.integers(1, 60),
        worn=st.tuples(st.integers(0, 60), st.integers(0, 60), st.integers(0, 60)),
    )
    def test_an_outcome_the_game_pays_charges_no_fatigue_and_pays_in_full(
        self, key: str, cost: int, pot: int, worn: tuple[int, int, int]
    ) -> None:
        """A standoff's ending is a system outcome, not a person's tag: nobody pays fatigue for
        it, even a payer with nothing left, and it is not refused for a character her own
        account plays (the account that tags is the account that plays her)."""
        poser, _endorser, targets, pose, scene = self.setup_gain(key, cost, pot, worn, 1)
        poser_account = account_for_sheet(poser)
        moment = DramaticMomentTypeFactory(
            resonance=Resonance.objects.get(pk=self.resonances[key].pk), resonance_amount=pot
        )
        CharacterResonanceFactory(character_sheet=poser, resonance=moment.resonance)
        everyone = [poser, *targets]
        before = {sheet.pk: self.social(sheet) for sheet in everyone}

        create_dramatic_moment_tag(
            character_sheet=poser,
            moment_type=moment,
            tagged_by=poser_account,
            scene=scene,
            interaction=pose,
            by_system=True,
        )

        paid = self.grants_of(poser)
        self.assertEqual(sum(g.amount for g in paid), pot)
        for sheet in everyone:
            self.assertEqual(self.social(sheet), before[sheet.pk])


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

        # The endpoint agrees: nothing for a co-owner, the GM only for a pose she can read. A
        # grant that is not hers to undo is a 404, a pose she cannot read included, so the
        # answer never says the reward exists.
        client = APIClient()
        url = f"/api/magic/resonance-grants/{grant.pk}/undo/"
        for outsider in (owner, guest, stranger, poser_account):
            client.force_authenticate(user=outsider)
            self.assertEqual(client.post(url).status_code, 404)
        client.force_authenticate(user=gm)
        status_for_gm = client.post(url).status_code
        self.assertEqual(status_for_gm, 200 if readable else 404)
        grant.refresh_from_db()
        self.assertEqual(grant.nullified_by, gm if readable else None)


TAGGERS = ("gm", "owner", "staff", "bystander", "self")


class OnlyTheSceneGMAndStaffNameATagsResonance(_Table, HypothesisTestCase):
    """A dramatic-moment tag lets only the scene's GM and staff name any resonance, and nobody
    tags a character she plays.

    An accepted default, not the maintainer's own words: every player present when a scene
    starts is one of its owners, so a tag that let an owner name any resonance would let any
    player pay any resonance to any character, herself included. An owner who is not the GM
    keeps what she could do before: the moment type's own resonance, or one the character
    already has.
    """

    def tag_scene(self, tagger: str, poser_account: AccountDB) -> Scene:
        """A scene the poser's player joined: as one of its owners when she is the one tagging
        (every player present at the start is), else as a plain participant."""
        if tagger != "self":
            return self.scene_with(poser_account)
        scene = SceneFactory()
        SceneOwnerParticipationFactory(scene=scene, account=poser_account)
        return scene

    def tagger_account(
        self, tagger: str, scene: Scene, poser_account: AccountDB, tag: int
    ) -> AccountDB:
        """The account that tags, in the role ``tagger`` names."""
        if tagger == "self":
            return poser_account
        if tagger == "staff":
            return self.staff
        account = AccountFactory(username=f"tagger_{tagger}_{tag}")
        if tagger == "gm":
            SceneGMParticipationFactory(scene=scene, account=account)
        elif tagger == "owner":
            SceneOwnerParticipationFactory(scene=scene, account=account)
        return account

    def expected_resonance(self, tagger: str, named: str, type_key: str, *, in_aura: bool) -> str:
        """What a tag pays, from the rule alone: a GM or staff member's choice always, an
        owner's choice only when the character already has it, else the type's own."""
        if tagger in ("gm", "staff") or in_aura or named == type_key:
            return named
        return type_key

    @settings(max_examples=40, deadline=None)
    @given(
        tagger=st.sampled_from(TAGGERS),
        named=st.sampled_from(RESONANCE_KEYS),
        type_key=st.sampled_from(RESONANCE_KEYS),
        in_aura=st.booleans(),
    )
    def test_the_service_lets_only_gm_and_staff_name_any_resonance(
        self, tagger: str, named: str, type_key: str, in_aura: bool
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        scene = self.tag_scene(tagger, poser_account)
        by = self.tagger_account(tagger, scene, poser_account, poser.pk)
        CharacterResonanceFactory(character_sheet=poser, resonance=self.resonances[type_key])
        if in_aura and named != type_key:
            CharacterResonanceFactory(character_sheet=poser, resonance=self.resonances[named])
        moment = DramaticMomentTypeFactory(resonance=self.resonances[type_key])
        pose = self.pose(scene, poser)
        call = {
            "character_sheet": poser,
            "moment_type": moment,
            "tagged_by": by,
            "scene": scene,
            "interaction": pose,
            "resonance": Resonance.objects.get(pk=self.resonances[named].pk),
        }

        if tagger == "self":
            with self.assertRaises(EndorsementValidationError):
                create_dramatic_moment_tag(**call)
            self.assertFalse(DramaticMomentTag.objects.exists())
            self.assertEqual(self.grants_of(poser), [])
        else:
            create_dramatic_moment_tag(**call)

            grants = self.grants_of(poser)
            self.assertEqual(len(grants), 1)
            self.assertEqual(
                grants[0].resonance,
                self.resonances[self.expected_resonance(tagger, named, type_key, in_aura=in_aura)],
            )

    @settings(max_examples=25, deadline=None)
    @given(
        tagger=st.sampled_from(TAGGERS),
        named=st.sampled_from(RESONANCE_KEYS),
        type_key=st.sampled_from(RESONANCE_KEYS),
        in_aura=st.booleans(),
    )
    def test_the_endpoint_refuses_a_stranger_and_herself_and_never_names_the_character(
        self, tagger: str, named: str, type_key: str, in_aura: bool
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        scene = self.tag_scene(tagger, poser_account)
        by = self.tagger_account(tagger, scene, poser_account, poser.pk)
        CharacterResonanceFactory(character_sheet=poser, resonance=self.resonances[type_key])
        if in_aura and named != type_key:
            CharacterResonanceFactory(character_sheet=poser, resonance=self.resonances[named])
        moment = DramaticMomentTypeFactory(resonance=self.resonances[type_key])
        pose = self.pose(scene, poser)
        client = APIClient()
        client.force_authenticate(user=by)
        body = {
            "moment_type": moment.pk,
            "interaction": pose.pk,
            "resonance": self.resonances[named].pk,
        }

        response = client.post("/api/magic/dramatic-moment-tags/", body, format="json")

        if tagger == "bystander":
            self.assertEqual(response.status_code, 403)
            self.assertFalse(DramaticMomentTag.objects.exists())
        elif tagger == "self":
            # Her own account is a participant, so the permission passes and the service
            # refuses a tag on a character she plays.
            self.assertEqual(response.status_code, 400)
            self.assertFalse(DramaticMomentTag.objects.exists())
        else:
            self.assertEqual(response.status_code, 201)
            # Only staff read who stands behind the pose or which account tagged it.
            for field in ("character_sheet", "tagged_by"):
                self.assertEqual(field in response.json(), tagger == "staff")
            grants = self.grants_of(poser)
            self.assertEqual(
                [g.resonance for g in grants],
                [
                    self.resonances[
                        self.expected_resonance(tagger, named, type_key, in_aura=in_aura)
                    ]
                ],
            )

    @settings(max_examples=15, deadline=None)
    @given(visibility=st.sampled_from(VISIBILITIES))
    def test_a_stranger_learns_nothing_from_ids_and_a_pose_fixes_its_scene(
        self, visibility: str
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        outsider_sheet, outsider_account = self.player()
        scene = self.scene_with(poser_account)
        other_scene = self.scene_with(poser_account)
        gm = AccountFactory(username=f"tag_scene_gm_{poser.pk}")
        stranger = AccountFactory(username=f"tag_stranger_{poser.pk}")
        SceneGMParticipationFactory(scene=scene, account=gm)
        SceneGMParticipationFactory(scene=other_scene, account=gm)
        moment = DramaticMomentTypeFactory(resonance=self.resonances["primal 1"])
        CharacterResonanceFactory(character_sheet=poser, resonance=self.resonances["primal 1"])
        pose = self.pose(scene, poser, visibility)
        url = "/api/magic/dramatic-moment-tags/"
        client = APIClient()

        # A stranger gets the same refusal for ids that exist and ids that do not.
        client.force_authenticate(user=stranger)
        real = client.post(url, {"moment_type": moment.pk, "interaction": pose.pk}, format="json")
        absent = client.post(url, {"moment_type": 0, "interaction": 0}, format="json")
        self.assertEqual((real.status_code, absent.status_code), (403, 403))
        self.assertEqual(real.json(), absent.json())

        # The GM of both scenes cannot tag a pose into the other, nor a character outside it.
        client.force_authenticate(user=gm)
        wrong_scene = {"moment_type": moment.pk, "interaction": pose.pk, "scene": other_scene.pk}
        wrong_sheet = {
            "moment_type": moment.pk,
            "interaction": pose.pk,
            "character_sheet": outsider_sheet.pk,
        }
        # The outsider's player never joined the scene, so she is not part of it.
        self.assertEqual(client.post(url, wrong_scene, format="json").status_code, 400)
        self.assertEqual(client.post(url, wrong_sheet, format="json").status_code, 400)
        self.assertFalse(DramaticMomentTag.objects.exists())

        # A pose the GM cannot read is not hers to tag.
        readable = visibility != InteractionVisibility.VERY_PRIVATE
        ok = client.post(url, {"moment_type": moment.pk, "interaction": pose.pk}, format="json")
        self.assertEqual(ok.status_code, 201 if readable else 400)
        self.assertEqual(DramaticMomentTag.objects.count(), 1 if readable else 0)

        # The list holds the tags of scenes the requester GMs or owns, and nobody else's.
        self.assertEqual(
            len(client.get(url).json()["results"]),
            1 if readable else 0,
        )
        for outside in (stranger, outsider_account):
            client.force_authenticate(user=outside)
            self.assertEqual(client.get(url).json()["results"], [])
        # Filtering by character is staff's alone.
        client.force_authenticate(user=gm)
        self.assertEqual(client.get(url, {"character_sheet": poser.pk}).json()["results"], [])
        client.force_authenticate(user=self.staff)
        staff_rows = client.get(url, {"character_sheet": poser.pk}).json()["results"]
        self.assertEqual(len(staff_rows), 1 if readable else 0)


class AWaitingPickIsAnsweredByTheRightPeople(_Table, HypothesisTestCase):
    """The poser, her scene's GM and staff answer a waiting pick, nobody answers her own, and a
    lent NPC is answered by its borrower, not by the player who lent it away.

    An accepted default, not the maintainer's own words: a GM who proposed a resonance
    cannot also accept it, and a GM who cannot read the pose cannot answer a pick on it.
    """

    @settings(max_examples=20, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        visibility=st.sampled_from(VISIBILITIES),
        accept=st.booleans(),
    )
    def test_the_endorser_never_answers_and_a_gm_answers_only_a_pose_she_can_read(
        self, key: str, visibility: str, accept: bool
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        endorser, endorser_account = self.player()
        gm = AccountFactory(username=f"answer_gm_{poser.pk}")
        scene = self.scene_with(poser_account)
        SceneGMParticipationFactory(scene=scene, account=gm)
        # The endorser is also a GM of the scene: a GM who proposed it cannot accept it.
        SceneGMParticipationFactory(scene=scene, account=endorser_account)
        pose = self.pose(scene, poser, visibility)
        readable = visibility != InteractionVisibility.VERY_PRIVATE
        proposal = create_pose_endorsement(endorser, pose, self.resonances[key])
        answer = accept_pose_proposal if accept else decline_pose_proposal

        with self.assertRaises(EndorsementValidationError):
            answer(proposal, endorser_account)
        if readable:
            answer(proposal, gm)

            self.assertEqual(
                PoseEndorsement.objects.filter(pk=proposal.pk, awaiting_acceptance=False).exists(),
                accept,
            )
            self.assertEqual(PoseEndorsement.objects.filter(pk=proposal.pk).exists(), accept)
        else:
            with self.assertRaises(EndorsementValidationError):
                answer(proposal, gm)
            self.assertTrue(PoseEndorsement.objects.get(pk=proposal.pk).awaiting_acceptance)

    @settings(max_examples=12, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), accept=st.booleans())
    def test_a_lent_npcs_borrower_answers_and_its_holder_does_not(
        self, key: str, accept: bool
    ) -> None:
        self.no_bonus_check()
        endorser, endorser_account = self.player()
        npc, holder = self.player()
        borrower = AccountFactory(username=f"borrower_{npc.pk}")
        NPCLoanFactory(
            roster_entry=npc.roster_entry,
            borrower=borrower,
            offered_by=holder,
            status=NPCLoanStatus.ACTIVE,
        )
        scene = self.scene_with(endorser_account, borrower)
        # The borrower is the one who posed it, so her account is the pose's writer.
        pose = InteractionFactory(scene=scene, persona=npc.primary_persona, writer_account=borrower)
        proposal = create_pose_endorsement(endorser, pose, self.resonances[key])
        answer = accept_pose_proposal if accept else decline_pose_proposal
        url = f"/api/magic/pose-endorsements/{proposal.pk}/{'accept' if accept else 'decline'}/"
        client = APIClient()

        # The holder lent it away, so it is not hers to answer, and the route does not find it.
        with self.assertRaises(EndorsementValidationError):
            answer(proposal, holder)
        client.force_authenticate(user=holder)
        self.assertEqual(client.post(url).status_code, 404)
        self.assertTrue(PoseEndorsement.objects.get(pk=proposal.pk).awaiting_acceptance)

        client.force_authenticate(user=borrower)
        self.assertEqual(client.post(url).status_code, 200 if accept else 204)
        self.assertEqual(PoseEndorsement.objects.filter(pk=proposal.pk).exists(), accept)

    @settings(max_examples=12, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), settled=st.booleans())
    def test_only_the_endorser_deletes_and_every_other_answer_is_a_404(
        self, key: str, settled: bool
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        endorser, endorser_account = self.player()
        _witness, witness_account = self.player()
        scene = self.scene_with(poser_account, endorser_account, witness_account)
        pose = self.pose(scene, poser)
        endorsement = PoseEndorsementFactory(
            endorser_sheet=endorser,
            endorsee_sheet=poser,
            interaction=pose,
            resonance=self.resonances[key],
            awaiting_acceptance=True,
        )
        if settled:
            endorsement.settled_at = endorsement.created_at
            endorsement.save(update_fields=["settled_at"])
        url = f"/api/magic/pose-endorsements/{endorsement.pk}/"
        client = APIClient()

        # Another player's waiting pick answers exactly as a missing one does.
        for other in (witness_account, poser_account):
            client.force_authenticate(user=other)
            self.assertEqual(client.delete(url).status_code, 404)
            self.assertEqual(client.delete("/api/magic/pose-endorsements/0/").status_code, 404)
        self.assertTrue(PoseEndorsement.objects.filter(pk=endorsement.pk).exists())

        client.force_authenticate(user=endorser_account)
        self.assertEqual(client.delete(url).status_code, 404 if settled else 204)
        self.assertEqual(PoseEndorsement.objects.filter(pk=endorsement.pk).exists(), settled)


SIX_REWARDS = ("mark", "pose endorsement", "tag", "entry endorsement", "style", "flourish")


class AGMUndoesEverySceneBoundReward(_Table, HypothesisTestCase):
    """The scene's GM undoes each of the six rewards that belong to a scene, and the answer
    shows her nothing of whom it paid.

    An accepted default, not the maintainer's own words: the rewards a mark, a pose endorsement,
    a tag, an entrance endorsement, an outfit endorsement and an entry flourish pay all happen
    in a scene, so the GM of that scene may undo them; every other source is staff's.
    """

    def reward(self, kind: str, poser: CharacterSheet, scene: Scene, pose: Interaction, key: str):
        """One reward of ``kind``, written the way play writes it, and the grant it paid."""
        resonance = self.resonances[key]
        other, _account = self.player()
        if kind == "mark":
            grant = self.marked_grant(poser, key, 9)
            RecordedActFactory(character_sheet=poser, marked_grant=grant, marked_interaction=pose)
            return grant
        if kind == "tag":
            tag = create_dramatic_moment_tag(
                character_sheet=poser,
                moment_type=DramaticMomentTypeFactory(resonance=resonance),
                tagged_by=self.staff,
                scene=scene,
                interaction=pose,
                resonance=resonance,
            )
            return ResonanceGrant.objects.get(source_dramatic_moment=tag)
        if kind == "flourish":
            record = create_entry_flourish(poser, resonance, scene=scene)
            return ResonanceGrant.objects.get(source_entry_flourish=record)
        kwargs: dict[str, object]
        if kind == "pose endorsement":
            source = GainSource.POSE_ENDORSEMENT
            kwargs = {
                "pose_endorsement": PoseEndorsementFactory(
                    endorser_sheet=other,
                    endorsee_sheet=poser,
                    interaction=pose,
                    resonance=resonance,
                )
            }
        elif kind == "entry endorsement":
            source = GainSource.SCENE_ENTRY
            kwargs = {
                "scene_entry_endorsement": SceneEntryEndorsementFactory(
                    endorser_sheet=other,
                    endorsee_sheet=poser,
                    scene=scene,
                    entry_interaction=pose,
                    entry_interaction_timestamp=pose.timestamp,
                    resonance=resonance,
                )
            }
        else:
            source = GainSource.STYLE_PRESENTATION
            kwargs = {
                "style_presentation_endorsement": StylePresentationEndorsementFactory(
                    endorser_sheet=other, endorsee_sheet=poser, scene=scene, resonance=resonance
                )
            }
        ledger: list[ResonanceGrant] = []
        grant_resonance(poser, resonance, 9, source=source, ledger_out=ledger, **kwargs)
        return ledger[-1]

    @settings(max_examples=24, deadline=None)
    @given(
        kind=st.sampled_from(SIX_REWARDS),
        key=st.sampled_from(RESONANCE_KEYS),
        visibility=st.sampled_from(VISIBILITIES),
    )
    def test_the_gm_staff_and_nobody_else_undo_each_one(
        self, kind: str, key: str, visibility: str
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        scene = self.scene_with(poser_account)
        gm = AccountFactory(username=f"six_gm_{poser.pk}")
        owner = AccountFactory(username=f"six_owner_{poser.pk}")
        SceneGMParticipationFactory(scene=scene, account=gm)
        SceneOwnerParticipationFactory(scene=scene, account=owner)
        pose = self.pose(scene, poser, visibility)
        grant = self.reward(kind, poser, scene, pose, key)
        url = f"/api/magic/resonance-grants/{grant.pk}/undo/"
        client = APIClient()

        # A reward no pose carries is the GM's whatever the pose's privacy; one a pose carries
        # needs a pose she can read, and without one the route answers 404.
        carried = kind in ("mark", "pose endorsement", "tag", "entry endorsement")
        gm_may = not (carried and visibility == InteractionVisibility.VERY_PRIVATE)
        for outsider in (owner, poser_account):
            client.force_authenticate(user=outsider)
            self.assertEqual(client.post(url).status_code, 404)

        client.force_authenticate(user=gm)
        response = client.post(url)

        self.assertEqual(response.status_code, 200 if gm_may else 404)
        grant.refresh_from_db()
        if gm_may:
            # Nothing but the id and when: not the amount, the sheet or the staff account.
            self.assertEqual(set(response.json()), {"id", "nullified_at"})
            self.assertEqual(grant.nullified_by, gm)
        else:
            self.assertIsNone(grant.nullified_at)
            client.force_authenticate(user=self.staff)
            self.assertEqual(client.post(url).status_code, 200)


class PrivateLinesReachAPlayerWhoIsOffline(_Table, HypothesisTestCase):
    """The lines the proposal, the tag and the undo send are stored for a player who is not
    connected, so she reads them at her next login.

    An accepted default, not the maintainer's own words: a bare message to a character reaches
    only a connected session, and these lines carry what happened to her resonance.
    """

    def lines_for(self, sheet: CharacterSheet) -> str:
        deliveries = NarrativeMessageDelivery.objects.filter(recipient_character_sheet=sheet)
        return " ".join(d.message.body for d in deliveries)

    @settings(max_examples=10, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), other=st.sampled_from(RESONANCE_KEYS))
    def test_a_proposal_a_tag_and_an_undo_are_each_stored_for_the_player(
        self, key: str, other: str
    ) -> None:
        self.no_bonus_check()
        poser, poser_account = self.player()
        endorser, endorser_account = self.player()
        scene = self.scene_with(poser_account, endorser_account)
        pose = self.pose(scene, poser)

        # Her witness proposes a resonance on her pose.
        with self.captureOnCommitCallbacks(execute=True):
            create_pose_endorsement(endorser, pose, self.resonances[key])
        self.assertIn(f"proposed {self.resonances[key].name} on your pose", self.lines_for(poser))

        # A GM tags the pose and names a resonance.
        gm = AccountFactory(username=f"offline_gm_{poser.pk}")
        SceneGMParticipationFactory(scene=scene, account=gm)
        moment = DramaticMomentTypeFactory(resonance=self.resonances[other])
        with self.captureOnCommitCallbacks(execute=True):
            tag = create_dramatic_moment_tag(
                character_sheet=poser,
                moment_type=moment,
                tagged_by=gm,
                scene=scene,
                interaction=pose,
                resonance=Resonance.objects.get(pk=self.resonances[other].pk),
            )
        self.assertIn(f"It paid you {self.resonances[other].name}", self.lines_for(poser))
        self.assertIn("The scene's GM tagged your pose", self.lines_for(poser))

        # Staff undo the tag's reward.
        grant = ResonanceGrant.objects.get(source_dramatic_moment=tag)
        with self.captureOnCommitCallbacks(execute=True):
            undo_resonance_grant(grant, self.staff)
        self.assertIn("Staff undid your", self.lines_for(poser))
