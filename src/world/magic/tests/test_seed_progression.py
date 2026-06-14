from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CharacterCodexKnowledge, CodexEntry, PathCodexGrant
from world.magic.constants import MagicMilestoneKind, MilestoneDiscoveryTier
from world.magic.factories import seed_magic_progression
from world.magic.models import MagicProgressionMilestone
from world.roster.factories import RosterEntryFactory


class SeedMagicProgressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prospect = PathFactory(name="Awakening", stage=PathStage.PROSPECT, is_active=True)
        cls.inactive = PathFactory(name="Retired", stage=PathStage.PROSPECT, is_active=False)

    def test_creates_14_milestones_with_distribution(self):
        seed_magic_progression()
        assert MagicProgressionMilestone.objects.count() == 14
        by_stage = {}
        for m in MagicProgressionMilestone.objects.all():
            by_stage.setdefault(m.stage, set()).add(m.kind)
        assert by_stage[PathStage.PROSPECT] == {
            MagicMilestoneKind.RESONANCE_DISCOVERY,
            MagicMilestoneKind.THREAD_WEAVING,
            MagicMilestoneKind.MOTIF,
            MagicMilestoneKind.TECHNIQUE_DEVELOPMENT,
            MagicMilestoneKind.ANIMA_RITUAL,
        }
        assert by_stage[PathStage.TRANSCENDENT] == {MagicMilestoneKind.STAGE_CROSSING}
        for stage in (PathStage.POTENTIAL, PathStage.PUISSANT, PathStage.TRUE, PathStage.GRAND):
            assert by_stage[stage] == {
                MagicMilestoneKind.SECOND_GIFT,
                MagicMilestoneKind.STAGE_CROSSING,
            }

    def test_creates_11_entries_and_public_flags(self):
        seed_magic_progression()
        assert CodexEntry.objects.filter(subject__name="The Mage's Journey").count() == 11
        public = set(
            CodexEntry.objects.filter(
                subject__name="The Mage's Journey", is_public=True
            ).values_list("name", flat=True)
        )
        assert public == {"Your Resonance", "Your Motif"}
        assert "Weaving Threads" not in public

    def test_second_gift_shares_one_entry(self):
        seed_magic_progression()
        sg = MagicProgressionMilestone.objects.filter(kind=MagicMilestoneKind.SECOND_GIFT)
        entry_ids = {m.codex_entry_id for m in sg}
        assert len(entry_ids) == 1

    def test_grants_gated_entries_to_active_prospect_paths_only(self):
        seed_magic_progression()
        granted_paths = set(PathCodexGrant.objects.values_list("path__name", flat=True))
        assert granted_paths == {"Awakening"}
        assert PathCodexGrant.objects.filter(path=self.prospect).count() == 9

    def test_idempotent(self):
        seed_magic_progression()
        seed_magic_progression()
        assert MagicProgressionMilestone.objects.count() == 14
        assert CodexEntry.objects.filter(subject__name="The Mage's Journey").count() == 11
        assert PathCodexGrant.objects.filter(path=self.prospect).count() == 9

    def test_reseed_updates_milestone_route(self):
        seed_magic_progression()
        m = MagicProgressionMilestone.objects.get(
            stage=PathStage.PROSPECT, kind=MagicMilestoneKind.THREAD_WEAVING
        )
        m.route_name = "/stale"
        m.save()
        seed_magic_progression()
        m.refresh_from_db()
        assert m.route_name == "/threads"

    def test_e2e_dashboard_reveal(self):
        """Grant → knowledge → dashboard reveal: full end-to-end path."""
        from world.magic.services.progression_dashboard import build_progression_dashboard

        seed_magic_progression()

        # Build a sheet with a resolving roster_entry (mirrors reference test pattern).
        sheet = CharacterSheetFactory()
        roster_entry = RosterEntryFactory(character_sheet=sheet)

        # --- Before knowledge grants ---
        result = build_progression_dashboard(sheet)
        prospect_view = next(sv for sv in result if sv.stage == PathStage.PROSPECT)

        # Public entries (resonance_discovery, motif) are KNOWN even with no knowledge row.
        tier_by_kind = {mv.kind: mv.tier for mv in prospect_view.milestones}
        assert (
            tier_by_kind.get(MagicMilestoneKind.RESONANCE_DISCOVERY) == MilestoneDiscoveryTier.KNOWN
        )
        assert tier_by_kind.get(MagicMilestoneKind.MOTIF) == MilestoneDiscoveryTier.KNOWN

        # Gated entry (thread_weaving) is UNKNOWN → collapsed, not in milestones list.
        assert MagicMilestoneKind.THREAD_WEAVING not in tier_by_kind
        assert prospect_view.has_undiscovered is True

        # --- Grant codex knowledge for all entries on self.prospect ---
        granted_entry_ids = list(
            PathCodexGrant.objects.filter(path=self.prospect).values_list("entry_id", flat=True)
        )
        for entry_id in granted_entry_ids:
            CharacterCodexKnowledge.objects.create(
                roster_entry=roster_entry,
                entry_id=entry_id,
                status=CodexKnowledgeStatus.KNOWN,
            )

        # --- After knowledge grants ---
        result2 = build_progression_dashboard(sheet)
        prospect_view2 = next(sv for sv in result2 if sv.stage == PathStage.PROSPECT)

        tier_by_kind2 = {mv.kind: mv.tier for mv in prospect_view2.milestones}
        assert tier_by_kind2.get(MagicMilestoneKind.THREAD_WEAVING) == MilestoneDiscoveryTier.KNOWN
