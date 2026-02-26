"""Tests for draft application service functions."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import ApplicationStatus, CommentType
from world.character_creation.factories import (
    CharacterDraftFactory,
    DraftApplicationFactory,
)
from world.character_creation.models import (
    Beginnings,
    DraftApplication,
    DraftApplicationComment,
    StartingArea,
)
from world.character_creation.services import (
    CharacterCreationError,
    add_application_comment,
    approve_application,
    claim_application,
    deny_application,
    request_revisions,
    resubmit_draft,
    submit_draft_for_review,
    unsubmit_draft,
    withdraw_draft,
)
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.magic.factories import (
    EffectTypeFactory,
    ResonanceModifierTypeFactory,
    TechniqueStyleFactory,
    TraditionFactory,
)
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard


class SubmitDraftForReviewTests(TestCase):
    """Tests for submit_draft_for_review service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def _make_submittable_draft(self):
        draft = CharacterDraftFactory(account=self.account)
        draft.can_submit = lambda: True
        return draft

    def test_creates_application(self):
        """Creates a DraftApplication with SUBMITTED status and submission notes."""
        draft = self._make_submittable_draft()
        app = submit_draft_for_review(draft, submission_notes="Please review!")

        self.assertIsInstance(app, DraftApplication)
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertEqual(app.submission_notes, "Please review!")
        self.assertEqual(app.draft, draft)

    def test_creates_status_change_comment(self):
        """Creates 1 STATUS_CHANGE comment saying 'Application submitted for review.'"""
        draft = self._make_submittable_draft()
        app = submit_draft_for_review(draft)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, "Application submitted for review.")
        self.assertIsNone(comment.author)

    def test_raises_if_already_has_application(self):
        """Raises CharacterCreationError if draft already has an application."""
        draft = self._make_submittable_draft()
        DraftApplicationFactory(draft=draft)

        with self.assertRaises(CharacterCreationError):
            submit_draft_for_review(draft)

    def test_raises_if_draft_cannot_submit(self):
        """Raises CharacterCreationError if draft.can_submit() returns False."""
        draft = CharacterDraftFactory(account=self.account)
        draft.can_submit = lambda: False

        with self.assertRaises(CharacterCreationError):
            submit_draft_for_review(draft)


class UnsubmitDraftTests(TestCase):
    """Tests for unsubmit_draft service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def test_unsubmit_returns_to_editable(self):
        """Sets status to REVISIONS_REQUESTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        unsubmit_draft(app)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.REVISIONS_REQUESTED)

    def test_creates_status_change_comment(self):
        """Creates STATUS_CHANGE 'Player resumed editing.'"""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        unsubmit_draft(app)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, "Player resumed editing.")
        self.assertIsNone(comment.author)

    def test_raises_if_not_submitted(self):
        """Raises CharacterCreationError if status is not SUBMITTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.IN_REVIEW
        )

        with self.assertRaises(CharacterCreationError):
            unsubmit_draft(app)


class ResubmitDraftTests(TestCase):
    """Tests for resubmit_draft service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def test_resubmit_sets_submitted(self):
        """Sets status to SUBMITTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.REVISIONS_REQUESTED
        )
        resubmit_draft(app)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)

    def test_creates_message_and_status_comments(self):
        """Creates MESSAGE (if comment provided) + STATUS_CHANGE."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.REVISIONS_REQUESTED
        )
        resubmit_draft(app, comment="Fixed the backstory.")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment should be the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Fixed the backstory.")
        self.assertEqual(comments[0].author, self.account)

        # Second comment should be the STATUS_CHANGE
        self.assertEqual(comments[1].comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comments[1].text, "Application resubmitted for review.")
        self.assertIsNone(comments[1].author)

    def test_resubmit_without_comment(self):
        """Only creates STATUS_CHANGE, no MESSAGE."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.REVISIONS_REQUESTED
        )
        resubmit_draft(app)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, "Application resubmitted for review.")

    def test_raises_if_not_revisions_requested(self):
        """Raises CharacterCreationError if status is not REVISIONS_REQUESTED."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )

        with self.assertRaises(CharacterCreationError):
            resubmit_draft(app)


class WithdrawDraftTests(TestCase):
    """Tests for withdraw_draft service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()

    def test_withdraw_sets_status_and_expiry(self):
        """Sets WITHDRAWN and non-null expires_at."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        withdraw_draft(app)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.WITHDRAWN)
        self.assertIsNotNone(app.expires_at)

    def test_expires_at_is_two_weeks_out(self):
        """expires_at is ~14 days from now."""
        app = DraftApplicationFactory(
            draft__account=self.account, status=ApplicationStatus.SUBMITTED
        )
        before = timezone.now()
        withdraw_draft(app)
        after = timezone.now()

        app.refresh_from_db()
        expected_min = before + timedelta(days=14)
        expected_max = after + timedelta(days=14)
        self.assertGreaterEqual(app.expires_at, expected_min)
        self.assertLessEqual(app.expires_at, expected_max)

    def test_raises_if_terminal(self):
        """Raises CharacterCreationError if already APPROVED/DENIED/WITHDRAWN."""
        for status in (
            ApplicationStatus.APPROVED,
            ApplicationStatus.DENIED,
            ApplicationStatus.WITHDRAWN,
        ):
            app = DraftApplicationFactory(draft__account=self.account, status=status)
            with self.assertRaises(CharacterCreationError):
                withdraw_draft(app)


# ── Staff Review Service Tests ──────────────────────────────────────────────


class ClaimApplicationTests(TestCase):
    """Tests for claim_application service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_claim_sets_in_review(self):
        """Sets status to IN_REVIEW and assigns reviewer."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        claim_application(app, reviewer=self.staff)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.IN_REVIEW)
        self.assertEqual(app.reviewer, self.staff)

    def test_claim_sets_reviewed_at(self):
        """Sets reviewed_at timestamp."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        before = timezone.now()
        claim_application(app, reviewer=self.staff)
        after = timezone.now()
        app.refresh_from_db()
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    def test_claim_creates_status_change_comment(self):
        """Creates STATUS_CHANGE comment: 'Claimed for review by {username}.'"""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        claim_application(app, reviewer=self.staff)

        comments = DraftApplicationComment.objects.filter(application=app)
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comment.text, f"Claimed for review by {self.staff.username}.")
        self.assertIsNone(comment.author)

    def test_raises_if_not_submitted(self):
        """Raises CharacterCreationError if status is not SUBMITTED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.REVISIONS_REQUESTED)
        with self.assertRaises(CharacterCreationError):
            claim_application(app, reviewer=self.staff)


class ApproveApplicationTests(TestCase):
    """Tests for approve_application service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    @patch("world.character_creation.services.RosterTenure")
    @patch("world.character_creation.services.finalize_character")
    def test_approve_finalizes_character(self, mock_finalize, mock_tenure_cls):  # noqa: ARG002
        """Calls finalize_character(draft, add_to_roster=False)."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff, comment="Looks great!")
        mock_finalize.assert_called_once_with(draft, add_to_roster=False)

    @patch("world.character_creation.services.RosterTenure")
    @patch("world.character_creation.services.finalize_character")
    def test_approve_sets_status(self, mock_finalize, mock_tenure_cls):  # noqa: ARG002
        """Sets status to APPROVED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff)
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.APPROVED)

    @patch("world.character_creation.services.RosterTenure")
    @patch("world.character_creation.services.finalize_character")
    def test_approve_sets_reviewer_and_reviewed_at(
        self,
        mock_finalize,  # noqa: ARG002
        mock_tenure_cls,  # noqa: ARG002
    ):
        """Sets reviewer and reviewed_at."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        approve_application(app, reviewer=self.staff)
        after = timezone.now()
        app.refresh_from_db()
        self.assertEqual(app.reviewer, self.staff)
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    @patch("world.character_creation.services.RosterTenure")
    @patch("world.character_creation.services.finalize_character")
    def test_approve_creates_message_comment_if_provided(
        self,
        mock_finalize,  # noqa: ARG002
        mock_tenure_cls,  # noqa: ARG002
    ):
        """Creates MESSAGE comment when comment text is provided."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff, comment="Great character!")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment is the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Great character!")
        self.assertEqual(comments[0].author, self.staff)

    @patch("world.character_creation.services.RosterTenure")
    @patch("world.character_creation.services.finalize_character")
    def test_approve_creates_status_change_comment(
        self,
        mock_finalize,  # noqa: ARG002
        mock_tenure_cls,  # noqa: ARG002
    ):
        """Creates STATUS_CHANGE comment: 'Application approved by {username}.'"""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        approve_application(app, reviewer=self.staff)

        comments = DraftApplicationComment.objects.filter(
            application=app, comment_type=CommentType.STATUS_CHANGE
        )
        self.assertEqual(comments.count(), 1)

        comment = comments.first()
        self.assertEqual(comment.text, f"Application approved by {self.staff.username}.")
        self.assertIsNone(comment.author)

    def test_raises_if_not_in_review(self):
        """Raises CharacterCreationError if status is not IN_REVIEW."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        with self.assertRaises(CharacterCreationError):
            approve_application(app, reviewer=self.staff)


class RequestRevisionsTests(TestCase):
    """Tests for request_revisions service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_sets_revisions_requested(self):
        """Sets status to REVISIONS_REQUESTED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        request_revisions(app, reviewer=self.staff, comment="Please fix backstory.")
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.REVISIONS_REQUESTED)

    def test_sets_reviewed_at(self):
        """Sets reviewed_at timestamp."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        request_revisions(app, reviewer=self.staff, comment="Please fix backstory.")
        after = timezone.now()
        app.refresh_from_db()
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    def test_creates_message_and_status_comments(self):
        """Creates MESSAGE with feedback + STATUS_CHANGE comment."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        request_revisions(app, reviewer=self.staff, comment="Please fix backstory.")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment is the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Please fix backstory.")
        self.assertEqual(comments[0].author, self.staff)

        # Second comment is the STATUS_CHANGE
        self.assertEqual(comments[1].comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comments[1].text, f"Revisions requested by {self.staff.username}.")
        self.assertIsNone(comments[1].author)

    def test_raises_if_not_in_review(self):
        """Raises CharacterCreationError if status is not IN_REVIEW."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        with self.assertRaises(CharacterCreationError):
            request_revisions(app, reviewer=self.staff, comment="Fix it.")

    def test_raises_if_comment_empty(self):
        """Raises CharacterCreationError if comment is empty."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        with self.assertRaises(CharacterCreationError):
            request_revisions(app, reviewer=self.staff, comment="")


class DenyApplicationTests(TestCase):
    """Tests for deny_application service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_deny_sets_status(self):
        """Sets status to DENIED."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.DENIED)

    def test_deny_sets_reviewer_and_reviewed_at(self):
        """Sets reviewer and reviewed_at."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")
        after = timezone.now()
        app.refresh_from_db()
        self.assertEqual(app.reviewer, self.staff)
        self.assertIsNotNone(app.reviewed_at)
        self.assertGreaterEqual(app.reviewed_at, before)
        self.assertLessEqual(app.reviewed_at, after)

    def test_deny_sets_expires_at(self):
        """Sets expires_at to ~14 days from now."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        before = timezone.now()
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")
        after = timezone.now()
        app.refresh_from_db()
        self.assertIsNotNone(app.expires_at)
        self.assertGreaterEqual(app.expires_at, before + timedelta(days=14))
        self.assertLessEqual(app.expires_at, after + timedelta(days=14))

    def test_deny_creates_message_and_status_comments(self):
        """Creates MESSAGE with denial reason + STATUS_CHANGE comment."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        deny_application(app, reviewer=self.staff, comment="Concept doesn't fit.")

        comments = list(
            DraftApplicationComment.objects.filter(application=app).order_by("created_at")
        )
        self.assertEqual(len(comments), 2)

        # First comment is the MESSAGE
        self.assertEqual(comments[0].comment_type, CommentType.MESSAGE)
        self.assertEqual(comments[0].text, "Concept doesn't fit.")
        self.assertEqual(comments[0].author, self.staff)

        # Second comment is the STATUS_CHANGE
        self.assertEqual(comments[1].comment_type, CommentType.STATUS_CHANGE)
        self.assertEqual(comments[1].text, f"Application denied by {self.staff.username}.")
        self.assertIsNone(comments[1].author)

    def test_raises_if_not_in_review(self):
        """Raises CharacterCreationError if status is not IN_REVIEW."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.SUBMITTED)
        with self.assertRaises(CharacterCreationError):
            deny_application(app, reviewer=self.staff, comment="No.")

    def test_raises_if_comment_empty(self):
        """Raises CharacterCreationError if comment is empty."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )
        with self.assertRaises(CharacterCreationError):
            deny_application(app, reviewer=self.staff, comment="")


class AddApplicationCommentTests(TestCase):
    """Tests for add_application_comment service function."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.account = AccountFactory()

    def test_creates_message_comment(self):
        """Creates a MESSAGE comment with given text and author."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.IN_REVIEW)
        comment = add_application_comment(app, author=self.staff, text="Looking good so far.")

        self.assertIsInstance(comment, DraftApplicationComment)
        self.assertEqual(comment.application, app)
        self.assertEqual(comment.author, self.staff)
        self.assertEqual(comment.text, "Looking good so far.")
        self.assertEqual(comment.comment_type, CommentType.MESSAGE)

    def test_raises_if_text_empty(self):
        """Raises CharacterCreationError if text is empty."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.IN_REVIEW)
        with self.assertRaises(CharacterCreationError):
            add_application_comment(app, author=self.staff, text="")

    def test_returns_created_comment(self):
        """Returns the created DraftApplicationComment instance."""
        draft = CharacterDraftFactory(account=self.account)
        app = DraftApplicationFactory(draft=draft, status=ApplicationStatus.IN_REVIEW)
        result = add_application_comment(app, author=self.account, text="Player question.")

        self.assertEqual(result.pk, DraftApplicationComment.objects.get(application=app).pk)


class ApproveApplicationIntegrationTests(TestCase):
    """Integration tests for approve_application with real finalize_character.

    These tests exercise the full approve → finalize → roster → tenure flow
    without mocking finalize_character. Requires complete draft seed data.
    """

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from world.character_sheets.models import Gender
        from world.forms.models import Build, HeightBand
        from world.realms.models import Realm
        from world.species.models import Species
        from world.traits.models import Trait, TraitType

        cls.staff = AccountFactory(is_staff=True)

        cls.realm = Realm.objects.create(
            name="Approve Integration Realm",
            description="Test realm",
        )
        cls.area = StartingArea.objects.create(
            name="Approve Integration Area",
            description="Test area",
            realm=cls.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        cls.species = Species.objects.create(
            name="Approve Integration Species",
            description="Test species",
        )
        cls.gender, _ = Gender.objects.get_or_create(
            key="approve_int_gender",
            defaults={"display_name": "Approve Integration Gender"},
        )
        cls.tarot_card = TarotCard.objects.create(
            name="Approve Integration Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Approbatus",
        )
        cls.beginnings = Beginnings.objects.create(
            name="Approve Integration Beginnings",
            description="Test beginnings",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        cls.beginnings.allowed_species.add(cls.species)

        cls.height_band = HeightBand.objects.create(
            name="approve_int_band",
            display_name="Approve Integration Band",
            min_inches=1900,
            max_inches=2000,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        cls.build = Build.objects.create(
            name="approve_int_build",
            display_name="Approve Integration Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )

        for stat_name in [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "perception",
            "intellect",
            "wits",
            "willpower",
        ]:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={"trait_type": TraitType.STAT},
            )

        cls.path = PathFactory(
            name="Approve Integration Path",
            stage=PathStage.PROSPECT,
            minimum_level=1,
        )
        cls.technique_style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        cls.resonance = ResonanceModifierTypeFactory()
        cls.tradition = TraditionFactory()

    def setUp(self):
        from world.traits.models import CharacterTraitValue, Trait

        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

        self.account = AccountFactory()

    def _create_complete_magic(self, draft):
        """Helper to create complete magic data for a draft."""
        from world.character_creation.factories import (
            DraftAnimaRitualFactory,
            DraftGiftFactory,
            DraftMotifFactory,
            DraftMotifResonanceAssociationFactory,
            DraftMotifResonanceFactory,
            DraftTechniqueFactory,
        )

        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance)
        DraftTechniqueFactory(gift=gift, style=self.technique_style, effect_type=self.effect_type)
        motif = DraftMotifFactory(draft=draft)
        motif_resonance = DraftMotifResonanceFactory(motif=motif, resonance=self.resonance)
        DraftMotifResonanceAssociationFactory(motif_resonance=motif_resonance)
        DraftAnimaRitualFactory(draft=draft)

    def _create_approved_application(self):
        """Create a complete draft, submit, claim, and return the IN_REVIEW application."""
        from world.character_creation.models import CharacterDraft

        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            selected_tradition=self.tradition,
            age=25,
            height_band=self.height_band,
            height_inches=1950,
            build=self.build,
            draft_data={
                "first_name": "ApproveTest",
                "stats": {
                    "strength": 30,
                    "agility": 30,
                    "stamina": 30,
                    "charm": 20,
                    "presence": 20,
                    "perception": 20,
                    "intellect": 20,
                    "wits": 30,
                    "willpower": 30,
                },
                "lineage_is_orphan": True,
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": False,
                "traits_complete": True,
            },
        )
        self._create_complete_magic(draft)

        return DraftApplicationFactory(
            draft=draft, status=ApplicationStatus.IN_REVIEW, reviewer=self.staff
        )

    def test_approve_creates_roster_tenure(self):
        """Approval creates a RosterTenure linking the player to the character."""
        from world.roster.models import RosterTenure

        app = self._create_approved_application()
        approve_application(app, reviewer=self.staff)

        tenure = RosterTenure.objects.filter(
            player_data__account=self.account,
        ).first()
        self.assertIsNotNone(tenure)
        self.assertEqual(tenure.player_number, 1)
        self.assertTrue(tenure.is_current)
        self.assertIsNotNone(tenure.approved_date)
        self.assertEqual(tenure.approved_by.account, self.staff)

    def test_approve_moves_to_active_roster(self):
        """Approval moves the RosterEntry from Pending to the Active roster."""
        from world.roster.models import RosterEntry

        app = self._create_approved_application()
        approve_application(app, reviewer=self.staff)

        entry = RosterEntry.objects.filter(
            character__db_key__startswith="ApproveTest",
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.roster.name, "Active")
        self.assertTrue(entry.roster.is_active)

    def test_approve_creates_character_with_tenure(self):
        """Approval creates a RosterTenure with a character attached."""
        from world.roster.models import RosterTenure

        app = self._create_approved_application()
        approve_application(app, reviewer=self.staff)

        tenure = RosterTenure.objects.get(player_data__account=self.account)
        character = tenure.roster_entry.character
        self.assertIsNotNone(character)

    def test_approve_preserves_application_record(self):
        """Approval preserves the DraftApplication and its comments after draft deletion."""
        app = self._create_approved_application()
        # Add a comment before approval
        DraftApplicationComment.objects.create(
            application=app,
            author=self.staff,
            text="Looks good!",
            comment_type=CommentType.MESSAGE,
        )

        approve_application(app, reviewer=self.staff)

        # Application record survives draft deletion
        self.assertTrue(
            DraftApplication.objects.filter(
                status=ApplicationStatus.APPROVED,
            ).exists()
        )
        app.refresh_from_db()
        self.assertIsNone(app.draft)
        self.assertIsNotNone(app.player_account)
        self.assertTrue(app.character_name)
        # Comments survive
        self.assertGreaterEqual(app.comments.count(), 2)  # our message + status change
