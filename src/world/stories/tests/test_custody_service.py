"""Tests for the custody check service seam (#2001).

Covers check_subject_custody's own/participant/staff/clearance-stub rules,
custody_verdict_for_stake's intended-scope derivation, and that
is_death_prevented_by_story (moved into custody.py, re-exported from
npc_protection.py) is unchanged behaviorally — its own dedicated coverage
lives in test_npc_protection.py and stays green unmodified.
"""

from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.stories.constants import (
    BeatOutcome,
    CustodyScope,
    StakeResolutionColumn,
    StakeSubjectKind,
)
from world.stories.factories import (
    BeatFactory,
    StakeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryParticipationFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.services.boundaries import _subject_identity
from world.stories.services.custody import check_subject_custody, custody_verdict_for_stake
from world.stories.types import StoryStatus


def _account_playing(character_sheet):
    """An AccountDB currently playing character_sheet's character (live tenure)."""
    entry = RosterEntryFactory(character_sheet=character_sheet)
    player_data = PlayerDataFactory()
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return player_data.account


class CheckSubjectCustodyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.npc_sheet = CharacterSheetFactory()
        cls.subject_identity = _subject_identity(
            StakeSubjectKind.NPC_FATE, cls.npc_sheet.pk, None, None, None, ""
        )

    def test_no_protection_allowed(self):
        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=None,
            scope=CustodyScope.REMOVE,
        )
        self.assertTrue(verdict.allowed)
        self.assertIsNone(verdict.requires_scope)
        self.assertIsNone(verdict.custodian_gm_username)
        self.assertIsNone(verdict.protecting_subject_id)

    def test_none_actor_blocked_when_protected(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=None,
            scope=CustodyScope.APPEAR,
        )
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.APPEAR)

    def test_staff_actor_allowed_despite_protection(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        staff_account = AccountFactory(is_staff=True)
        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=staff_account,
            scope=CustodyScope.REMOVE,
        )
        self.assertTrue(verdict.allowed)

    def test_non_participant_blocked_with_custodian_and_subject_id(self):
        from world.gm.factories import GMProfileFactory, GMTableFactory

        gm_profile = GMProfileFactory()
        table = GMTableFactory(gm=gm_profile)
        self.story.primary_table = table
        self.story.save(update_fields=["primary_table"])
        protection = StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)

        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.HARM,
        )
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.HARM)
        self.assertEqual(verdict.custodian_gm_username, gm_profile.account.username)
        self.assertEqual(verdict.protecting_subject_id, protection.pk)

    def test_orphaned_story_custodian_none(self):
        # primary_table stays null (orphaned story) per factory default.
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.APPEAR,
        )
        self.assertFalse(verdict.allowed)
        self.assertIsNone(verdict.custodian_gm_username)

    def test_participant_allowed(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        participant_sheet = CharacterSheetFactory()
        participant_account = _account_playing(participant_sheet)
        StoryParticipationFactory(story=self.story, character=participant_sheet.character)

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=participant_account,
            scope=CustodyScope.REMOVE,
        )
        self.assertTrue(verdict.allowed)

    def test_acting_story_bypasses_without_participation(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.REMOVE,
            acting_story=self.story,
        )
        self.assertTrue(verdict.allowed)

    def test_beat_window_resolved_protection_lifted(self):
        beat = BeatFactory(episode__chapter__story=self.story, outcome=BeatOutcome.SUCCESS)
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet, beat=beat)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=outsider_account,
            scope=CustodyScope.APPEAR,
        )
        self.assertTrue(verdict.allowed)

    def test_blocked_by_second_story_when_participant_in_only_first(self):
        story_b = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        protection_b = StoryProtectedSubjectFactory(story=story_b, subject_sheet=self.npc_sheet)

        actor_sheet = CharacterSheetFactory()
        actor_account = _account_playing(actor_sheet)
        StoryParticipationFactory(story=self.story, character=actor_sheet.character)
        # Not a participant in story_b.

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=actor_account,
            scope=CustodyScope.REMOVE,
        )
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.protecting_subject_id, protection_b.pk)

    def test_participant_in_every_protecting_story_allowed(self):
        story_b = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        StoryProtectedSubjectFactory(story=story_b, subject_sheet=self.npc_sheet)

        actor_sheet = CharacterSheetFactory()
        actor_account = _account_playing(actor_sheet)
        StoryParticipationFactory(story=self.story, character=actor_sheet.character)
        StoryParticipationFactory(story=story_b, character=actor_sheet.character)

        verdict = check_subject_custody(
            subject_identity=self.subject_identity,
            actor_account=actor_account,
            scope=CustodyScope.REMOVE,
        )
        self.assertTrue(verdict.allowed)


class CustodyVerdictForStakeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.story = StoryFactory(status=StoryStatus.ACTIVE)
        cls.beat = BeatFactory(episode__chapter__story=cls.story)
        cls.npc_sheet = CharacterSheetFactory()

    def _stake(self):
        return StakeFactory(
            beat=self.beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=self.npc_sheet,
        )

    def test_appear_scope_default_no_resolutions(self):
        stake = self._stake()
        verdict = custody_verdict_for_stake(stake, None)
        self.assertTrue(verdict.allowed)  # no protection at all yet
        # Force a block (on a DIFFERENT story than the stake's own — a
        # protection owned by the stake's own story never blocks it, see
        # test_acting_story_from_stakes_own_beat_bypasses_protection) to
        # inspect the derived scope.
        other_story = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)
        blocked = custody_verdict_for_stake(stake, outsider_account)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.requires_scope, CustodyScope.APPEAR)

    def test_derives_remove_scope_from_lifecycle_write(self):
        stake = self._stake()
        StakeResolutionFactory(
            stake=stake,
            column=StakeResolutionColumn.LOSS,
            sets_subject_lifecycle=LifecycleState.DEAD,
        )
        other_story = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = custody_verdict_for_stake(stake, outsider_account)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.REMOVE)

    def test_derives_remove_scope_from_forfeit(self):
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        item = ItemInstanceFactory(template=ItemTemplateFactory())
        stake = StakeFactory(beat=self.beat, subject_kind=StakeSubjectKind.ITEM, subject_item=item)
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, forfeits_subject_item=True
        )
        other_story = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(
            story=other_story,
            subject_kind=StakeSubjectKind.ITEM,
            subject_sheet=None,
            subject_item=item,
        )
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = custody_verdict_for_stake(stake, outsider_account)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.REMOVE)

    def test_derives_harm_scope_from_standing_delta(self):
        stake = self._stake()
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, subject_standing_delta=-3
        )
        other_story = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = custody_verdict_for_stake(stake, outsider_account)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.HARM)

    def test_derives_harm_scope_from_loss_consequence_pool(self):
        pool = ConsequencePoolFactory()
        stake = self._stake()
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, consequence_pool=pool
        )
        other_story = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = custody_verdict_for_stake(stake, outsider_account)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.HARM)

    def test_win_column_consequence_pool_does_not_count_as_harm(self):
        pool = ConsequencePoolFactory()
        stake = self._stake()
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN, consequence_pool=pool)
        other_story = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = custody_verdict_for_stake(stake, outsider_account)
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.APPEAR)

    def test_explicit_intended_scope_overrides_derivation(self):
        stake = self._stake()
        other_story = StoryFactory(status=StoryStatus.ACTIVE)
        StoryProtectedSubjectFactory(story=other_story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        verdict = custody_verdict_for_stake(
            stake, outsider_account, intended_scope=CustodyScope.REMOVE
        )
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.requires_scope, CustodyScope.REMOVE)

    def test_acting_story_from_stakes_own_beat_bypasses_protection(self):
        stake = self._stake()
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        # The protecting story IS the stake's own story (beat.episode.chapter.story),
        # so no clearance/participation is needed.
        verdict = custody_verdict_for_stake(stake, outsider_account)
        self.assertTrue(verdict.allowed)


class NpcProtectionShimTests(TestCase):
    """Confirms npc_protection.py re-exports the exact function moved into custody.py."""

    def test_shim_reexports_same_function_object(self):
        from world.stories.npc_protection import is_death_prevented_by_story as via_shim
        from world.stories.services.custody import is_death_prevented_by_story as via_custody

        self.assertIs(via_shim, via_custody)
