"""Expiry is a completion (#3558): pool, stakes, activation, ledger."""

from datetime import timedelta
from unittest import mock

from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.gm.factories import GMTableFactory, GMTableMembershipFactory
from world.societies.factories import LegendSourceTypeFactory, SocietyFactory
from world.societies.models import LegendEvent, SocietyReputation
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    StakeOutcomeMethod,
    StakeResolutionColumn,
    StakeSubjectKind,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    GroupStoryProgressFactory,
    StakeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryProgressFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import BeatCompletion, StakeOutcome
from world.stories.services.beats import (
    _fire_pool_with_context,
    complete_beat_expired,
    expire_beat,
    expire_overdue_beats,
)
from world.stories.services.stakes import activate_stakes_contract, get_open_activation
from world.stories.services.transitions import get_eligible_transitions


def _pool_with_condition_and_legend(template):
    """A pool whose one consequence applies ``template`` to SELF and awards legend."""
    # apply_pool_deterministically fires every pool row unconditionally, so the
    # Consequence's own outcome_tier is irrelevant here; use the factory default
    # (Consequence.outcome_tier is NOT NULL).
    consequence = ConsequenceFactory()
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.APPLY_CONDITION,
        condition_template=template,
    )
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.LEGEND_AWARD,
        legend_base_value=10,
        legend_source_type=LegendSourceTypeFactory(),
        legend_description_template="Too slow.",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    return pool


def _pool_with_legend_only():
    """A pool whose one consequence only awards legend (no character-targeted effect).

    Used where no participant/character is resolvable (GROUP scope, no
    participants) — a character-targeted effect (e.g. APPLY_CONDITION to SELF)
    would fail against the unsaved stub ObjectDB that _fire_pool_with_context
    falls back to in that case, which is a pre-existing, unrelated constraint.
    """
    consequence = ConsequenceFactory()
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.LEGEND_AWARD,
        legend_base_value=10,
        legend_source_type=LegendSourceTypeFactory(),
        legend_description_template="Too slow.",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    return pool


class SkipEffectTypesTests(EvenniaTestCase):
    def test_skip_legend_fires_other_effects_and_no_legend(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        beat = BeatFactory(episode=EpisodeFactory(chapter=ChapterFactory(story=story)))
        progress = StoryProgressFactory(story=story, character_sheet=sheet)
        template = ConditionTemplateFactory()
        pool = _pool_with_condition_and_legend(template)

        _fire_pool_with_context(
            pool=pool,
            beat=beat,
            progress=progress,
            scope=StoryScope.CHARACTER,
            participants=[sheet.primary_persona],
            skip_effect_types=frozenset({EffectType.LEGEND_AWARD}),
        )

        assert ConditionInstance.objects.filter(target=sheet.character, condition=template).exists()
        assert not LegendEvent.objects.exists()

    def test_skip_legend_needs_no_participants(self) -> None:
        """With LEGEND_AWARD skipped the participant guard must not raise."""
        story = StoryFactory(scope=StoryScope.GROUP)
        beat = BeatFactory(episode=EpisodeFactory(chapter=ChapterFactory(story=story)))
        pool = _pool_with_legend_only()

        _fire_pool_with_context(
            pool=pool,
            beat=beat,
            progress=None,
            scope=StoryScope.GROUP,
            participants=[],
            skip_effect_types=frozenset({EffectType.LEGEND_AWARD}),
        )
        assert not LegendEvent.objects.exists()


def _past(hours: int = 1):
    return timezone.now() - timedelta(hours=hours)


def _character_beat(**beat_kwargs):
    sheet = CharacterSheetFactory()
    story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
    episode = EpisodeFactory(chapter=ChapterFactory(story=story))
    beat = BeatFactory(episode=episode, deadline=_past(), **beat_kwargs)
    progress = StoryProgressFactory(story=story, character_sheet=sheet)
    return sheet, beat, progress


class CompleteBeatExpiredTests(EvenniaTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_risk_calibrations()

    def test_fires_expired_pool_and_writes_completion(self) -> None:
        template = ConditionTemplateFactory()
        pool = _pool_with_condition_and_legend(template)
        sheet, beat, _progress = _character_beat(expired_consequences=pool)

        completion = complete_beat_expired(beat)

        beat.refresh_from_db()
        assert beat.outcome == BeatOutcome.EXPIRED
        assert completion is not None
        assert completion.outcome == BeatOutcome.EXPIRED
        assert completion.character_sheet_id == sheet.pk
        assert completion.gm_notes == "Deadline passed."
        assert ConditionInstance.objects.filter(target=sheet.character, condition=template).exists()
        assert not LegendEvent.objects.exists()  # expiry earns no legend

    def test_resolves_stakes_loss_and_closes_activation(self) -> None:
        sheet, beat, _progress = _character_beat()
        stake = StakeFactory(beat=beat)
        loss = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.LOSS)
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        activation = activate_stakes_contract(beat, [sheet])

        complete_beat_expired(beat)

        outcome = StakeOutcome.objects.get(stake=stake)
        assert outcome.column == StakeResolutionColumn.LOSS
        assert outcome.method == StakeOutcomeMethod.MACHINE
        assert outcome.resolution_id == loss.pk
        assert outcome.activation_id == activation.pk
        assert get_open_activation(beat) is None

    def test_faction_standing_delta_applies_once_on_character_scope(self) -> None:
        """Regression: CHARACTER-scope expiry must not double-credit the persona.

        _expiry_participants returns [] for CHARACTER scope (the completion tail's
        _character_scope_participants already prepends the primary persona itself);
        a stake writer that iterates participants (subject_standing_delta) must
        apply exactly once, not twice.
        """
        sheet, beat, _progress = _character_beat()
        persona = sheet.primary_persona
        society = SocietyFactory()
        stake = StakeFactory(
            beat=beat, subject_kind=StakeSubjectKind.FACTION, subject_society=society
        )
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, subject_standing_delta=-5
        )
        StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WIN)
        activate_stakes_contract(beat, [sheet])

        complete_beat_expired(beat)

        rep = SocietyReputation.objects.get(persona=persona, society=society)
        assert rep.value == -5

    def test_no_active_progress_flips_only(self) -> None:
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=CharacterSheetFactory())
        beat = BeatFactory(
            episode=EpisodeFactory(chapter=ChapterFactory(story=story)), deadline=_past()
        )

        assert complete_beat_expired(beat) is None
        beat.refresh_from_db()
        assert beat.outcome == BeatOutcome.EXPIRED
        assert not BeatCompletion.objects.filter(beat=beat).exists()

    def test_group_scope_uses_table_members(self) -> None:
        story = StoryFactory(scope=StoryScope.GROUP)
        table = GMTableFactory()
        member = GMTableMembershipFactory(table=table)
        GMTableMembershipFactory(table=table, left_at=timezone.now())  # gone; excluded
        GroupStoryProgressFactory(story=story, gm_table=table)
        template = ConditionTemplateFactory()
        pool = _pool_with_condition_and_legend(template)
        beat = BeatFactory(
            episode=EpisodeFactory(chapter=ChapterFactory(story=story)),
            predicate_type=BeatPredicateType.GM_MARKED,
            deadline=_past(),
            expired_consequences=pool,
        )

        completion = complete_beat_expired(beat)

        assert completion is not None
        assert completion.gm_table_id == table.pk
        assert ConditionInstance.objects.filter(
            target=member.persona.character_sheet.character, condition=template
        ).exists()
        assert not LegendEvent.objects.exists()


class ExpireBeatTests(EvenniaTestCase):
    def test_guard_future_deadline(self) -> None:
        _sheet, beat, _progress = _character_beat()
        beat.deadline = timezone.now() + timedelta(hours=1)
        beat.save(update_fields=["deadline"])
        assert expire_beat(beat) is None
        beat.refresh_from_db()
        assert beat.outcome == BeatOutcome.UNSATISFIED

    def test_idempotent(self) -> None:
        _sheet, beat, _progress = _character_beat()
        first = expire_beat(beat)
        second = expire_beat(beat)
        assert first is not None
        assert second is None
        assert BeatCompletion.objects.filter(beat=beat).count() == 1


class NotifyDeferralTests(EvenniaTestCase):
    """complete_beat_expired defers notify to transaction.on_commit (review finding).

    complete_beat_expired and expire_beat are both @transaction.atomic, so the
    _create_completion_and_fire_pool tail runs inside a savepoint, not a top-level
    commit. defer_notify=True schedules the notify via transaction.on_commit so it
    fires only when the outer transaction actually commits, and so a notify failure
    can't roll back the completion. EvenniaTestCase subclasses django.test.TestCase,
    so captureOnCommitCallbacks is available directly.
    """

    def test_notify_runs_only_after_the_outer_transaction_commits(self) -> None:
        _sheet, beat, progress = _character_beat()
        with mock.patch("world.stories.services.beats._notify_beat_completion") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                completion = complete_beat_expired(beat)
                assert notify.call_count == 0
            assert notify.call_count == 1
        notify.assert_called_once_with(completion, progress)

    def test_notify_failure_does_not_roll_back_the_completion(self) -> None:
        _sheet, beat, _progress = _character_beat()
        with (
            mock.patch(
                "world.stories.services.beats._notify_beat_completion",
                side_effect=RuntimeError("boom"),
            ),
            self.assertRaises(RuntimeError),
            self.captureOnCommitCallbacks(execute=True),
        ):
            complete_beat_expired(beat)

        beat.refresh_from_db()
        assert beat.outcome == BeatOutcome.EXPIRED
        assert BeatCompletion.objects.filter(beat=beat).exists()


class ExpirySitesTests(EvenniaTestCase):
    def test_cron_fires_pool(self) -> None:
        template = ConditionTemplateFactory()
        pool = _pool_with_condition_and_legend(template)
        sheet, _beat, _progress = _character_beat(expired_consequences=pool)

        assert expire_overdue_beats() == 1
        assert ConditionInstance.objects.filter(target=sheet.character, condition=template).exists()

    def test_lazy_transition_expiry_fires_pool(self) -> None:
        template = ConditionTemplateFactory()
        pool = _pool_with_condition_and_legend(template)
        _sheet, beat, progress = _character_beat(expired_consequences=pool)
        progress.current_episode = beat.episode
        progress.save(update_fields=["current_episode"])

        get_eligible_transitions(progress)

        beat.refresh_from_db()
        assert beat.outcome == BeatOutcome.EXPIRED
        assert BeatCompletion.objects.filter(beat=beat, outcome=BeatOutcome.EXPIRED).exists()

    def test_one_failure_does_not_stop_the_batch(self) -> None:
        _, first, _ = _character_beat()
        _, second, _ = _character_beat()
        real = complete_beat_expired

        def boom(beat):
            if beat.pk == first.pk:
                msg = "boom"
                raise RuntimeError(msg)
            return real(beat)

        with mock.patch("world.stories.services.beats.complete_beat_expired", side_effect=boom):
            count = expire_overdue_beats()

        second.refresh_from_db()
        first.refresh_from_db()
        assert count == 1
        assert second.outcome == BeatOutcome.EXPIRED
        assert first.outcome == BeatOutcome.UNSATISFIED
