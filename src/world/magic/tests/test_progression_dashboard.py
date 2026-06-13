from django.test import TestCase

from world.magic.constants import MagicMilestoneKind, MilestoneDiscoveryTier, MilestoneEligibility


class MilestoneEnumTests(TestCase):
    def test_kinds_cover_unlock_order(self):
        values = set(MagicMilestoneKind.values)
        assert {"resonance_discovery", "thread_weaving", "motif",
                "technique_development", "anima_ritual", "second_gift",
                "stage_crossing"} <= values

    def test_tiers_and_eligibility(self):
        assert set(MilestoneDiscoveryTier.values) == {"known", "uncovered", "unknown"}
        assert set(MilestoneEligibility.values) == {"already_have", "eligible", "locked"}


class MagicProgressionMilestoneModelTests(TestCase):
    def test_milestone_links_stage_kind_and_codex_entry(self):
        from world.classes.models import PathStage
        from world.magic.constants import MagicMilestoneKind
        from world.magic.factories import MagicProgressionMilestoneFactory

        m = MagicProgressionMilestoneFactory(
            stage=PathStage.POTENTIAL, kind=MagicMilestoneKind.THREAD_WEAVING
        )
        assert m.stage == PathStage.POTENTIAL
        assert m.kind == MagicMilestoneKind.THREAD_WEAVING
        assert m.codex_entry is not None
        assert str(m)
