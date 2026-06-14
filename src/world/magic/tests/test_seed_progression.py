from django.test import TestCase

from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.codex.models import CodexEntry, PathCodexGrant
from world.magic.constants import MagicMilestoneKind
from world.magic.factories import seed_magic_progression
from world.magic.models import MagicProgressionMilestone


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
