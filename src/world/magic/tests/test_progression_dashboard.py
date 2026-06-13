from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import MagicMilestoneKind, MilestoneDiscoveryTier, MilestoneEligibility
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


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


# =============================================================================
# Progression Dashboard resolver tests
# =============================================================================


class ProgressionDashboardTests(TestCase):
    """Tests for build_progression_dashboard service function."""

    def setUp(self):
        from world.character_sheets.factories import CharacterSheetFactory

        self.sheet = CharacterSheetFactory()

    def _make_public_milestone(self, stage, kind, sort_order=0):
        """Create a milestone with a public CodexEntry (always KNOWN tier)."""
        from world.codex.factories import CodexEntryFactory
        from world.magic.factories import MagicProgressionMilestoneFactory

        entry = CodexEntryFactory(is_public=True, name=f"Public {kind}", summary="A summary.")
        return MagicProgressionMilestoneFactory(
            stage=stage,
            kind=kind,
            codex_entry=entry,
            sort_order=sort_order,
        )

    def _make_nonpublic_milestone(self, stage, kind, sort_order=0):
        """Create a milestone with a non-public CodexEntry (UNKNOWN tier for most chars)."""
        from world.codex.factories import CodexEntryFactory
        from world.magic.factories import MagicProgressionMilestoneFactory

        entry = CodexEntryFactory(is_public=False, name=f"Secret {kind}", summary="Hidden.")
        return MagicProgressionMilestoneFactory(
            stage=stage,
            kind=kind,
            codex_entry=entry,
            sort_order=sort_order,
        )

    def test_always_returns_six_stage_views(self):
        """build_progression_dashboard always returns exactly 6 StageViews."""
        from world.magic.services.progression_dashboard import build_progression_dashboard

        result = build_progression_dashboard(self.sheet)
        assert len(result) == 6

    def test_stages_are_ascending(self):
        """StageViews are ordered ascending by stage value."""
        from world.magic.services.progression_dashboard import build_progression_dashboard

        result = build_progression_dashboard(self.sheet)
        stages = [sv.stage for sv in result]
        assert stages == sorted(stages)

    def test_public_entry_is_known_without_knowledge_row(self):
        """A public codex entry → KNOWN tier even with no CharacterCodexKnowledge row."""
        from world.classes.models import PathStage
        from world.magic.services.progression_dashboard import build_progression_dashboard

        self._make_public_milestone(PathStage.PROSPECT, MagicMilestoneKind.RESONANCE_DISCOVERY)

        result = build_progression_dashboard(self.sheet)
        stage1 = next(sv for sv in result if sv.stage == PathStage.PROSPECT)
        assert len(stage1.milestones) == 1
        mv = stage1.milestones[0]
        assert mv.tier == MilestoneDiscoveryTier.KNOWN
        assert mv.eligibility is not None  # eligible or locked, not None

    def test_nonpublic_entry_no_knowledge_row_contributes_to_has_undiscovered(self):
        """Non-public entry with no knowledge row → UNKNOWN; not in milestones list."""
        from world.classes.models import PathStage
        from world.magic.services.progression_dashboard import build_progression_dashboard

        self._make_nonpublic_milestone(PathStage.PROSPECT, MagicMilestoneKind.THREAD_WEAVING)

        result = build_progression_dashboard(self.sheet)
        stage1 = next(sv for sv in result if sv.stage == PathStage.PROSPECT)
        # UNKNOWN milestones are NOT added to milestones list
        assert len(stage1.milestones) == 0
        # But has_undiscovered is True
        assert stage1.has_undiscovered is True

    def test_known_entry_stage_too_low_is_locked(self):
        """KNOWN tier but current_stage < milestone.stage → eligibility == locked."""
        from world.classes.models import PathStage
        from world.magic.services.progression_dashboard import build_progression_dashboard

        # Place milestone at PUISSANT (stage 3); sheet has no path history → stage 1
        self._make_public_milestone(PathStage.PUISSANT, MagicMilestoneKind.SECOND_GIFT)

        result = build_progression_dashboard(self.sheet)
        stage3 = next(sv for sv in result if sv.stage == PathStage.PUISSANT)
        assert len(stage3.milestones) == 1
        mv = stage3.milestones[0]
        assert mv.tier == MilestoneDiscoveryTier.KNOWN
        assert mv.eligibility == MilestoneEligibility.LOCKED
        assert len(mv.missing) > 0
        assert "Puissant" in mv.missing[0]

    def test_known_entry_stage_met_already_have_resonance(self):
        """KNOWN tier, stage met, resonance row exists → already_have."""
        from world.classes.models import PathStage
        from world.magic.factories import CharacterResonanceFactory
        from world.magic.services.progression_dashboard import build_progression_dashboard

        # Ensure sheet is at stage 1 (no path history needed — default is 1)
        self._make_public_milestone(PathStage.PROSPECT, MagicMilestoneKind.RESONANCE_DISCOVERY)
        CharacterResonanceFactory(character_sheet=self.sheet)

        result = build_progression_dashboard(self.sheet)
        stage1 = next(sv for sv in result if sv.stage == PathStage.PROSPECT)
        assert len(stage1.milestones) == 1
        mv = stage1.milestones[0]
        assert mv.eligibility == MilestoneEligibility.ALREADY_HAVE

    def test_sheet_with_no_roster_entry_nonpublic_entries_are_undiscovered(self):
        """Sheet with no roster_entry: non-public entries are UNKNOWN (no crash)."""
        from world.classes.models import PathStage
        from world.magic.services.progression_dashboard import build_progression_dashboard

        # Verify sheet has no roster_entry
        assert getattr(self.sheet, "roster_entry", None) is None

        self._make_nonpublic_milestone(PathStage.POTENTIAL, MagicMilestoneKind.MOTIF)

        result = build_progression_dashboard(self.sheet)
        stage2 = next(sv for sv in result if sv.stage == PathStage.POTENTIAL)
        assert len(stage2.milestones) == 0
        assert stage2.has_undiscovered is True

    def test_uncovered_entry_has_no_eligibility(self):
        """UNCOVERED tier (non-public entry with UNCOVERED knowledge row) → eligibility None."""
        from world.classes.models import PathStage
        from world.codex.constants import CodexKnowledgeStatus
        from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
        from world.magic.factories import MagicProgressionMilestoneFactory
        from world.magic.services.progression_dashboard import build_progression_dashboard
        from world.roster.factories import RosterEntryFactory

        # Create a roster entry for the sheet
        entry = CodexEntryFactory(is_public=False, name="Partially Known", summary="Teaser.")
        roster_entry = RosterEntryFactory(character_sheet=self.sheet)
        CharacterCodexKnowledgeFactory(
            roster_entry=roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        MagicProgressionMilestoneFactory(
            stage=PathStage.PROSPECT,
            kind=MagicMilestoneKind.TECHNIQUE_DEVELOPMENT,
            codex_entry=entry,
        )

        result = build_progression_dashboard(self.sheet)
        stage1 = next(sv for sv in result if sv.stage == PathStage.PROSPECT)
        assert len(stage1.milestones) == 1
        mv = stage1.milestones[0]
        assert mv.tier == MilestoneDiscoveryTier.UNCOVERED
        assert mv.eligibility is None
        assert mv.summary == ""

    def test_current_stage_marked_correctly(self):
        """The StageView whose stage matches current_stage has is_current=True."""
        from world.magic.services.progression_dashboard import build_progression_dashboard

        # No path history → current_stage == 1 == PROSPECT
        result = build_progression_dashboard(self.sheet)
        current_views = [sv for sv in result if sv.is_current]
        assert len(current_views) == 1
        assert current_views[0].stage == 1  # PathStage.PROSPECT

    def test_empty_milestones_stages_have_no_undiscovered(self):
        """Stages with no milestones at all have has_undiscovered=False."""
        from world.magic.services.progression_dashboard import build_progression_dashboard

        result = build_progression_dashboard(self.sheet)
        # No milestones created → all stages have empty milestones and no undiscovered
        for sv in result:
            assert sv.has_undiscovered is False
            assert sv.milestones == []


# =============================================================================
# Progression Dashboard API endpoint tests
# =============================================================================


_PROGRESSION_URL = "/api/magic/progression/"


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure."""
    character.account = account
    account.characters.add(character)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    return RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data=player_data,
    )


class MagicProgressionViewAuthTests(APITestCase):
    """Auth guard for GET /api/magic/progression/."""

    def test_requires_auth(self):
        """Unauthenticated GET returns 401 or 403."""
        response = self.client.get(_PROGRESSION_URL)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class MagicProgressionViewTests(APITestCase):
    """Tests for GET /api/magic/progression/?character_sheet_id=<pk>."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="prog_view_account")
        cls.character = CharacterFactory(db_key="ProgViewChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

    def test_returns_six_stages(self):
        """Authenticated GET returns 200 with stages list of length 6."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_PROGRESSION_URL, {"character_sheet_id": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK, response.data
        stages = response.data["stages"]
        assert len(stages) == 6

    def test_undiscovered_stage_does_not_leak_titles(self):
        """A stage with has_undiscovered True has no visible milestones in its list."""
        from world.classes.models import PathStage
        from world.codex.factories import CodexEntryFactory
        from world.magic.factories import MagicProgressionMilestoneFactory

        # Create a non-public milestone (UNKNOWN tier → omitted from milestones list)
        entry = CodexEntryFactory(is_public=False, name="Hidden Milestone", summary="Secret.")
        MagicProgressionMilestoneFactory(
            stage=PathStage.PROSPECT,
            kind=MagicMilestoneKind.THREAD_WEAVING,
            codex_entry=entry,
        )

        self.client.force_authenticate(user=self.account)
        response = self.client.get(_PROGRESSION_URL, {"character_sheet_id": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK, response.data

        stages = response.data["stages"]
        stage1 = next(s for s in stages if s["stage"] == PathStage.PROSPECT)
        assert stage1["has_undiscovered"] is True
        # UNKNOWN milestone must NOT appear in the milestones list
        assert len(stage1["milestones"]) == 0
