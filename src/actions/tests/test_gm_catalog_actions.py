"""Tests for the GM scenario catalog Actions (#2127).

Covers ``FindSituationAction`` (STARTING-tier browse, breadth gating on
``SituationKind.minimum_gm_level``) and ``SubmitCatalogSuggestionAction``
(STARTING-tier submission, proposal_kind tiered by GM level per Decision 9) --
plus the negative that no code path here ever writes a live
``consequence_pool`` FK.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from actions.definitions.gm_catalog import FindSituationAction, SubmitCatalogSuggestionAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.gm.constants import CatalogSuggestionProposalKind, GMLevel
from world.gm.factories import (
    CheckTypeSituationFitFactory,
    ConsequencePoolGuideFactory,
    GMProfileFactory,
    SituationDifficultyGuideFactory,
    SituationKindFactory,
)
from world.gm.models import CatalogSuggestion
from world.mechanics.factories import SituationTemplateFactory
from world.player_submissions.constants import SubmissionStatus
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import DifficultyChoice
from world.societies.constants import RenownRisk


def _make_room(key: str = "The Catalog Room") -> object:
    return create_object("typeclasses.rooms.Room", key=key, nohome=True)


class GMCatalogActionsTestBase(TestCase):
    """Shared actor helpers -- staff, non-GM, and GM-at-level characters."""

    def _staff_character(self, *, db_key: str = "cat-staff") -> object:
        account = AccountFactory(is_staff=True, username=f"{db_key}-acct")
        character = CharacterFactory(db_key=db_key, location=_make_room())
        character.db_account = account
        return character

    def _nonstaff_character(self, *, db_key: str = "cat-onlooker") -> object:
        account = AccountFactory(is_staff=False, username=f"{db_key}-acct")
        character = CharacterFactory(db_key=db_key, location=_make_room())
        character.db_account = account
        return character

    def _gm_character(self, level: str, *, db_key: str = "cat-gm") -> object:
        """Return a Character with a live roster tenure + GMProfile at ``level``.

        Also stamps ``db_account`` to the tenure's account -- mirroring what a
        real live puppet session sets -- so ``actor.account`` (the OOC
        submitter identity ``SubmitCatalogSuggestionAction`` resolves) matches
        ``actor.active_account`` (the roster-tenure identity
        ``MinimumGMLevelPrerequisite`` gates on), the same as it would for an
        actual playing GM.
        """
        character = CharacterFactory(db_key=db_key, location=_make_room())
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        GMProfileFactory(account=tenure.player_data.account, level=level)
        character.db_account = tenure.player_data.account
        return character


class FindSituationActionPermissionTests(GMCatalogActionsTestBase):
    def test_non_gm_is_refused(self) -> None:
        actor = self._nonstaff_character()
        result = FindSituationAction().run(actor=actor, query="")
        assert result.success is False

    def test_starting_gm_can_browse(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = FindSituationAction().run(actor=actor, query="")
        assert result.success is True

    def test_staff_bypasses_gate(self) -> None:
        actor = self._staff_character()
        result = FindSituationAction().run(actor=actor, query="")
        assert result.success is True


class FindSituationActionSearchTests(GMCatalogActionsTestBase):
    def test_empty_catalog_reports_empty(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = FindSituationAction().run(actor=actor, query="zzz-no-such-thing")
        assert result.success is True
        assert "No situation templates matched" in result.message

    def test_template_found_by_name(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        template = SituationTemplateFactory(name="The Rooftop Chase")
        result = FindSituationAction().run(actor=actor, query="Rooftop")
        assert result.success is True
        assert template.name in result.message

    def test_template_found_by_description(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        template = SituationTemplateFactory(
            name="Sealed Vault", description_template="a heist gone loud"
        )
        result = FindSituationAction().run(actor=actor, query="heist gone loud")
        assert result.success is True
        assert template.name in result.message

    def test_kind_found_by_name_shows_guidance(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        kind = SituationKindFactory(name="Chase", minimum_gm_level=GMLevel.STARTING)
        category = CheckCategoryFactory()
        check_type = CheckTypeFactory(name="Sprint", category=category)
        CheckTypeSituationFitFactory(
            situation_kind=kind, check_type=check_type, fit_notes="footspeed"
        )
        SituationDifficultyGuideFactory(
            situation_kind=kind,
            risk=RenownRisk.MODERATE,
            recommended_difficulty=DifficultyChoice.NORMAL,
            guidance_text="a real chase",
        )
        pool_guide = ConsequencePoolGuideFactory(situation_kind=kind, is_default=True)

        result = FindSituationAction().run(actor=actor, query="Chase")

        assert result.success is True
        assert "Kind: Chase" in result.message
        assert "Sprint" in result.message
        assert "footspeed" in result.message
        assert "Normal" in result.message
        assert "a real chase" in result.message
        assert pool_guide.pool.name in result.message
        assert "advisory only" in result.message

    def test_risk_filters_difficulty_guide_to_one_row(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        kind = SituationKindFactory(name="Negotiation", minimum_gm_level=GMLevel.STARTING)
        SituationDifficultyGuideFactory(
            situation_kind=kind, risk=RenownRisk.LOW, recommended_difficulty=DifficultyChoice.EASY
        )
        SituationDifficultyGuideFactory(
            situation_kind=kind,
            risk=RenownRisk.EXTREME,
            recommended_difficulty=DifficultyChoice.HARROWING,
        )

        result = FindSituationAction().run(actor=actor, query="Negotiation", risk=RenownRisk.LOW)

        assert result.success is True
        assert "Easy" in result.message
        assert "Harrowing" not in result.message

    def test_invalid_risk_is_rejected(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = FindSituationAction().run(actor=actor, query="", risk="not-a-risk")
        assert result.success is False

    def test_starting_gm_filtered_out_of_senior_only_kind(self) -> None:
        """Breadth gating (Decision 9): a SENIOR-only kind never surfaces to a
        STARTING GM, even on an exact name match -- server-side filter, never a
        client-side hide."""
        SituationKindFactory(name="Deep Cover Op", minimum_gm_level=GMLevel.SENIOR)
        actor = self._gm_character(GMLevel.STARTING)

        result = FindSituationAction().run(actor=actor, query="Deep Cover Op")

        assert result.success is True
        assert "Kind: Deep Cover Op" not in result.message
        assert "No situation kind matched" in result.message

    def test_staff_sees_senior_only_kind(self) -> None:
        SituationKindFactory(name="Deep Cover Op", minimum_gm_level=GMLevel.SENIOR)
        actor = self._staff_character()

        result = FindSituationAction().run(actor=actor, query="Deep Cover Op")

        assert result.success is True
        assert "Kind: Deep Cover Op" in result.message

    def test_senior_gm_sees_senior_only_kind(self) -> None:
        SituationKindFactory(name="Deep Cover Op", minimum_gm_level=GMLevel.SENIOR)
        actor = self._gm_character(GMLevel.SENIOR)

        result = FindSituationAction().run(actor=actor, query="Deep Cover Op")

        assert result.success is True
        assert "Kind: Deep Cover Op" in result.message

    def test_never_writes_a_consequence_pool_fk(self) -> None:
        """Structurally absent: browsing never selects/writes a live consequence_pool."""
        from actions.models import ConsequencePool

        actor = self._gm_character(GMLevel.STARTING)
        kind = SituationKindFactory(name="Chase", minimum_gm_level=GMLevel.STARTING)
        ConsequencePoolGuideFactory(situation_kind=kind)
        pool_count_before = ConsequencePool.objects.count()

        FindSituationAction().run(actor=actor, query="Chase")

        assert ConsequencePool.objects.count() == pool_count_before


class SubmitCatalogSuggestionActionPermissionTests(GMCatalogActionsTestBase):
    def test_non_gm_is_refused(self) -> None:
        actor = self._nonstaff_character()
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.OTHER,
            proposal_text="Add a heist kind.",
        )
        assert result.success is False
        assert CatalogSuggestion.objects.count() == 0

    def test_starting_gm_can_submit_new_situation(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.NEW_SITUATION,
            proposal_text="A dockside smuggling situation.",
        )
        assert result.success is True
        assert CatalogSuggestion.objects.count() == 1

    def test_starting_gm_refused_difficulty_guide(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.DIFFICULTY_GUIDE,
            proposal_text="Chase should be harder at HIGH risk.",
        )
        assert result.success is False
        assert "GM" in result.message
        assert CatalogSuggestion.objects.count() == 0

    def test_junior_gm_refused_pool_guide(self) -> None:
        actor = self._gm_character(GMLevel.JUNIOR)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.POOL_GUIDE,
            proposal_text="Use the Mishap pool for failed infiltrations.",
        )
        assert result.success is False
        assert CatalogSuggestion.objects.count() == 0

    def test_gm_tier_can_submit_difficulty_guide(self) -> None:
        actor = self._gm_character(GMLevel.GM)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.DIFFICULTY_GUIDE,
            proposal_text="Chase should be harder at HIGH risk.",
        )
        assert result.success is True

    def test_gm_tier_still_refused_pool_guide(self) -> None:
        actor = self._gm_character(GMLevel.GM)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.POOL_GUIDE,
            proposal_text="Use the Mishap pool for failed infiltrations.",
        )
        assert result.success is False

    def test_experienced_tier_can_submit_pool_guide(self) -> None:
        actor = self._gm_character(GMLevel.EXPERIENCED)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.POOL_GUIDE,
            proposal_text="Use the Mishap pool for failed infiltrations.",
        )
        assert result.success is True

    def test_staff_bypasses_every_tier(self) -> None:
        actor = self._staff_character()
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.POOL_GUIDE,
            proposal_text="Use the Mishap pool for failed infiltrations.",
        )
        assert result.success is True


class SubmitCatalogSuggestionActionValidationTests(GMCatalogActionsTestBase):
    def test_invalid_proposal_kind_is_rejected(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind="not_a_real_kind",
            proposal_text="Something.",
        )
        assert result.success is False
        assert CatalogSuggestion.objects.count() == 0

    def test_blank_proposal_text_is_rejected(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.OTHER,
            proposal_text="   ",
        )
        assert result.success is False
        assert CatalogSuggestion.objects.count() == 0

    def test_creates_suggestion_with_open_status(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.CHECK_FIT,
            proposal_text="Athletics fits Chase.",
        )
        suggestion = CatalogSuggestion.objects.get()
        assert suggestion.status == SubmissionStatus.OPEN
        assert suggestion.proposal_kind == CatalogSuggestionProposalKind.CHECK_FIT
        assert suggestion.submitted_by == actor.active_account

    def test_situation_kind_ref_resolves_by_name(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        kind = SituationKindFactory(name="Chase")
        SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.CHECK_FIT,
            proposal_text="Athletics fits Chase.",
            situation_kind_ref="Chase",
        )
        suggestion = CatalogSuggestion.objects.get()
        assert suggestion.situation_kind == kind

    def test_unknown_situation_kind_ref_fails_cleanly(self) -> None:
        actor = self._gm_character(GMLevel.STARTING)
        result = SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.CHECK_FIT,
            proposal_text="Athletics fits Chase.",
            situation_kind_ref="No Such Kind",
        )
        assert result.success is False
        assert CatalogSuggestion.objects.count() == 0

    def test_never_writes_a_consequence_pool_fk(self) -> None:
        """Structurally absent: a suggestion is a proposal, never a live catalog write."""
        from actions.models import ConsequencePool

        actor = self._gm_character(GMLevel.EXPERIENCED)
        pool_count_before = ConsequencePool.objects.count()

        SubmitCatalogSuggestionAction().run(
            actor=actor,
            proposal_kind=CatalogSuggestionProposalKind.POOL_GUIDE,
            proposal_text="Use the Mishap pool for failed infiltrations.",
        )

        assert ConsequencePool.objects.count() == pool_count_before
