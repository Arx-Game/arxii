"""Tests for pull applicability computation and the applicable-pulls API.

See world/magic/services/pull_applicability.py and
world/magic/views.py:ApplicablePullsView.
"""

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import InapplicabilityReason, TargetKind
from world.magic.factories import ResonanceFactory, TechniqueFactory, ThreadFactory
from world.magic.services.pull_applicability import (
    PullActionContext,
    ThreadApplicability,
    compute_thread_applicability,
)


def _empty_context(**overrides: object) -> PullActionContext:
    """Return a context with all fields None, with optional overrides."""
    defaults: dict[str, object] = {
        "technique": None,
        "effect_type_id": None,
        "target_object_id": None,
        "target_persona_id": None,
        "scene_id": None,
    }
    defaults.update(overrides)
    return PullActionContext(**defaults)  # type: ignore[arg-type]


class ComputeThreadApplicabilityTests(TestCase):
    """Core tests for compute_thread_applicability."""

    def test_returns_one_row_per_thread(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        ThreadFactory(owner=sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 2)

    def test_returns_thread_applicability_instances(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertIsInstance(rows[0], ThreadApplicability)

    def test_retired_threads_excluded(self) -> None:
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet, retired_at=timezone.now())
        ThreadFactory(owner=sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)

    def test_threads_from_other_owners_excluded(self) -> None:
        sheet = CharacterSheetFactory()
        other_sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)
        ThreadFactory(owner=other_sheet)
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 1)

    def test_empty_result_when_no_threads(self) -> None:
        sheet = CharacterSheetFactory()
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(rows, [])

    def test_trait_thread_applicable_when_no_technique_in_context(self) -> None:
        """Non-TECHNIQUE threads are applicable when no technique is in context."""
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)  # TRAIT kind by default
        rows = compute_thread_applicability(sheet, _empty_context())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)


class AnchoredOnOtherTechniqueRuleTests(TestCase):
    """Tests for the ANCHORED_ON_OTHER_TECHNIQUE applicability rule."""

    def test_technique_thread_applicable_when_same_technique_in_context(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        technique = TechniqueFactory()
        thread = ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )
        context = _empty_context(technique=technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].thread, thread)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_technique_thread_inapplicable_when_different_technique_in_context(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        anchored_technique = TechniqueFactory()
        other_technique = TechniqueFactory()
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=anchored_technique,
        )
        context = _empty_context(technique=other_technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.ANCHORED_ON_OTHER_TECHNIQUE.value)

    def test_technique_thread_inapplicable_when_no_technique_in_context(self) -> None:
        """A TECHNIQUE-kind thread cannot apply when no technique is specified."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        technique = TechniqueFactory()
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )
        context = _empty_context()  # no technique
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.ANCHORED_ON_OTHER_TECHNIQUE.value)

    def test_non_technique_thread_unaffected_by_technique_in_context(self) -> None:
        """TRAIT-kind threads are not filtered by technique context."""
        sheet = CharacterSheetFactory()
        technique = TechniqueFactory()
        ThreadFactory(owner=sheet)  # TRAIT kind
        context = _empty_context(technique=technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)

    def test_mixed_threads_correct_applicability(self) -> None:
        """TECHNIQUE thread for the right technique + TRAIT thread both applicable."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        technique = TechniqueFactory()
        # Thread anchored to the context technique — should be applicable.
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )
        # TRAIT thread — always applicable regardless of technique context.
        ThreadFactory(owner=sheet)
        context = _empty_context(technique=technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.applicable for r in rows))

    def test_wrong_technique_and_trait_thread_mixed(self) -> None:
        """TECHNIQUE thread for the wrong technique is inapplicable; TRAIT is not."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        anchored_technique = TechniqueFactory()
        context_technique = TechniqueFactory()
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=anchored_technique,
        )
        ThreadFactory(owner=sheet)  # TRAIT — always applicable
        context = _empty_context(technique=context_technique)
        rows = compute_thread_applicability(sheet, context)
        self.assertEqual(len(rows), 2)
        applicable = [r for r in rows if r.applicable]
        inapplicable = [r for r in rows if not r.applicable]
        self.assertEqual(len(applicable), 1)
        self.assertEqual(len(inapplicable), 1)
        self.assertEqual(
            inapplicable[0].reason, InapplicabilityReason.ANCHORED_ON_OTHER_TECHNIQUE.value
        )


# =============================================================================
# View tests
# =============================================================================

_APPLICABLE_PULLS_URL = "/api/magic/applicable-pulls/"


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure."""
    from world.roster.factories import RosterEntryFactory, RosterTenureFactory

    character.account = account
    account.characters.add(character)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data=player_data,
    )


class ApplicablePullsViewTests(APITestCase):
    """Tests for POST /api/magic/applicable-pulls/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="applicable_pulls_test")
        cls.character = CharacterFactory(db_key="ApplicablePullsChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)
        cls.thread = ThreadFactory(owner=cls.sheet)

    def test_post_returns_applicability_rows(self) -> None:
        self.client.force_authenticate(user=self.account)
        resp = self.client.post(
            _APPLICABLE_PULLS_URL,
            {"character_sheet_id": self.sheet.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        rows = resp.data
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("thread_id", row)
        self.assertIn("applicable", row)
        self.assertIn("inapplicable_reason", row)
        self.assertEqual(row["thread_id"], self.thread.pk)
        self.assertTrue(row["applicable"])
        self.assertIsNone(row["inapplicable_reason"])

    def test_post_rejects_unowned_sheet(self) -> None:
        other_account = AccountFactory(username="applicable_pulls_other")
        other_char = CharacterFactory(db_key="ApplicablePullsOther")
        other_sheet = CharacterSheetFactory(character=other_char)
        _link_account_to_sheet(other_account, other_char, other_sheet)

        self.client.force_authenticate(user=self.account)
        resp = self.client.post(
            _APPLICABLE_PULLS_URL,
            {"character_sheet_id": other_sheet.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_rejects_unauthenticated(self) -> None:
        resp = self.client.post(
            _APPLICABLE_PULLS_URL,
            {"character_sheet_id": self.sheet.pk},
            format="json",
        )
        # Project returns 403 for unauthenticated requests (Evennia session auth).
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_post_excludes_retired_threads(self) -> None:
        self.client.force_authenticate(user=self.account)
        # Create a retired thread for this sheet — it should be excluded.
        ThreadFactory(owner=self.sheet, retired_at=timezone.now())
        resp = self.client.post(
            _APPLICABLE_PULLS_URL,
            {"character_sheet_id": self.sheet.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        # Only the non-retired thread from setUpTestData.
        self.assertEqual(len(resp.data), 1)

    def test_post_with_technique_id_marks_technique_thread_applicable(self) -> None:
        technique = TechniqueFactory()
        resonance = ResonanceFactory()
        technique_thread = ThreadFactory(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )
        self.client.force_authenticate(user=self.account)
        resp = self.client.post(
            _APPLICABLE_PULLS_URL,
            {"character_sheet_id": self.sheet.pk, "technique_id": technique.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        rows = {r["thread_id"]: r for r in resp.data}
        self.assertTrue(rows[technique_thread.pk]["applicable"])
        self.assertIsNone(rows[technique_thread.pk]["inapplicable_reason"])
