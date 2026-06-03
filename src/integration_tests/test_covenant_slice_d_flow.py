"""End-to-end integration test for Covenants Slice D.

Exercises the full pipeline:
  legend creation → credit fan-out → view refresh → covenant level recompute
  → narrative message delivery → sub-role promotion → anchor cap formula.
"""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantLevelThresholdFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.services import promote_to_subrole
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread
from world.magic.models.threads import TargetKind
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import CovenantLegendCredit, CovenantLegendSummary, LegendEntry
from world.societies.services import refresh_legend_views
from world.stories.constants import BeatOutcome, BeatPredicateType, EraStatus, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EraFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.beats import record_gm_marked_outcome


def _ensure_active_era():
    """Return an active Era, creating one if none exists."""
    from world.stories.models import Era

    active = Era.objects.get_active()
    if active is None:
        return EraFactory(status=EraStatus.ACTIVE)
    return active


class CovenantSliceDFlowIntegrationTest(TestCase):
    """End-to-end exercise of the Slice D loop.

    Asserts the entire pipeline: legend → credit fan-out → view refresh →
    covenant level recompute → narrative message delivery → sub-role
    promotion.
    """

    def test_full_legend_to_promotion_flow(self) -> None:  # noqa: PLR0915
        # ===== Phase 1: Setup =====
        _ensure_active_era()

        # Level thresholds (small numbers for the test)
        CovenantLevelThresholdFactory(level=1, required_legend=0)
        CovenantLevelThresholdFactory(level=2, required_legend=100)
        CovenantLevelThresholdFactory(level=3, required_legend=300)

        # Two engaged members in one covenant
        covenant = CovenantFactory()
        parent_role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        member1 = CharacterCovenantRoleFactory(
            covenant=covenant,
            covenant_role=parent_role,
            engaged=True,
        )
        member2 = CharacterCovenantRoleFactory(
            covenant=covenant,
            covenant_role=parent_role,
            engaged=True,
        )

        # Invalidate cached handlers so the fan-out sees the current state.
        member1.character_sheet.character.covenant_roles.invalidate()
        member2.character_sheet.character.covenant_roles.invalidate()

        # ===== Phase 2: Build the Story and Beat with a LEGEND_AWARD pool =====
        story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=member1.character_sheet,
        )
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)

        source_type = LegendSourceTypeFactory(name="story")
        consequence = ConsequenceFactory()
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=150,
            legend_source_type=source_type,
        )

        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            success_consequences=pool,
        )

        progress = StoryProgressFactory(story=story, character_sheet=member1.character_sheet)

        # ===== Phase 3: Resolve the beat as SUCCESS =====
        # CHARACTER scope: primary persona of member1.character_sheet is the participant.
        # extra_participants adds member2's primary persona.
        record_gm_marked_outcome(
            progress=progress,
            beat=beat,
            outcome=BeatOutcome.SUCCESS,
            extra_participants=[member2.character_sheet.primary_persona],
        )

        # ===== Phase 4: Assertions on legend creation =====
        # Two LegendEntry rows (one per participant persona)
        entries = LegendEntry.objects.filter(
            persona__character_sheet__in=[
                member1.character_sheet,
                member2.character_sheet,
            ]
        )
        self.assertEqual(entries.count(), 2, "Expected 2 LegendEntry rows (one per participant)")

        # CovenantLegendCredit fan-out: one credit per (entry, covenant)
        # Both engaged members credit the same covenant → 2 credits total
        credit_qs = CovenantLegendCredit.objects.filter(covenant=covenant)
        self.assertEqual(
            credit_qs.count(),
            2,
            "Expected 2 CovenantLegendCredit rows (one per engaged member's entry)",
        )

        # ===== Phase 5: Assert materialized view + covenant level =====
        refresh_legend_views()
        summary = CovenantLegendSummary.objects.get(pk=covenant.pk)
        # 2 entries × 150 base_value = 300
        self.assertEqual(
            summary.legend_total,
            300,
            f"Expected CovenantLegendSummary.legend_total == 300, got {summary.legend_total}",
        )

        covenant.refresh_from_db()
        self.assertEqual(
            covenant.level,
            3,
            f"Expected covenant.level == 3 (crossed 300 threshold), got {covenant.level}",
        )

        # ===== Phase 6: Assert NarrativeMessage delivery =====
        msgs = NarrativeMessage.objects.filter(category=NarrativeCategory.COVENANT)
        self.assertGreaterEqual(msgs.count(), 1, "Expected at least one COVENANT NarrativeMessage")
        msg = msgs.latest("id")
        self.assertIn(
            covenant.name,
            msg.body,
            f"Expected covenant name '{covenant.name}' in NarrativeMessage body",
        )
        self.assertIn(
            "level 3",
            msg.body.lower(),
            "Expected 'level 3' in NarrativeMessage body",
        )

        delivery_sheets = set(
            NarrativeMessageDelivery.objects.filter(message=msg).values_list(
                "recipient_character_sheet_id", flat=True
            )
        )
        self.assertIn(
            member1.character_sheet_id,
            delivery_sheets,
            "Expected member1 to receive the covenant level-up message",
        )
        self.assertIn(
            member2.character_sheet_id,
            delivery_sheets,
            "Expected member2 to receive the covenant level-up message",
        )

        # ===== Phase 7: Set up Thread for member1 to enable sub-role promotion =====
        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=member1.character_sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            level=3,
        )
        # Invalidate thread handler cache so promote_to_subrole sees the new thread.
        member1.character_sheet.character.threads.invalidate()

        # ===== Phase 8: Author the sub-role and promote =====
        sub_role = SubroleCovenantRoleFactory(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=3,
        )

        new_membership = promote_to_subrole(
            membership=member1,
            target_subrole=sub_role,
        )

        # ===== Phase 9: Assertions on promotion =====
        self.assertEqual(
            new_membership.covenant_role,
            sub_role,
            "Expected new membership to have the sub-role",
        )
        self.assertTrue(
            new_membership.engaged,
            "Expected promoted membership to preserve the engaged flag",
        )
        self.assertIsNone(
            new_membership.left_at,
            "Expected new membership to be active (left_at IS NULL)",
        )

        member1.refresh_from_db()
        self.assertIsNotNone(
            member1.left_at,
            "Expected old membership to be closed (left_at IS NOT NULL)",
        )

        # Anchor cap formula reads from historical rows — should still see
        # covenant.level for the parent role from the now-closed membership.
        handler = member1.character_sheet.character.covenant_roles
        handler.invalidate()
        max_level = handler.max_covenant_level_for_role(parent_role)
        self.assertEqual(
            max_level,
            covenant.level,
            f"Expected max_covenant_level_for_role to return {covenant.level}, got {max_level}",
        )
