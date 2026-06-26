"""Tests for alteration API endpoints."""

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.definitions.alterations import ResolveAlterationAction
from actions.types import ActionResult
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import (
    MIN_ALTERATION_DESCRIPTION_LENGTH,
    AlterationTier,
    PendingAlterationStatus,
)
from world.magic.factories import (
    AffinityFactory,
    MagicalAlterationTemplateFactory,
    PendingAlterationFactory,
    ResonanceFactory,
)


class PendingAlterationViewSetTests(APITestCase):
    """Test the PendingAlteration API."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.character.db_account = cls.account
        cls.character.save()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.account)

    def test_list_pending_alterations(self):
        """GET returns the character's open pending alterations."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        url = reverse("magic:pending-alteration-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_list_excludes_resolved_by_default(self):
        """GET list excludes resolved and staff-cleared alterations unless ?status= is given."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.OPEN,
        )
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.RESOLVED,
        )
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.STAFF_CLEARED,
        )
        url = reverse("magic:pending-alteration-list")

        # Default: only OPEN rows returned.
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

        # Explicit ?status=resolved: only RESOLVED rows returned.
        response = self.client.get(url, {"status": PendingAlterationStatus.RESOLVED})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_resolve_author_from_scratch(self):
        """POST resolve action creates template and applies condition."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )
        url = reverse("magic:pending-alteration-resolve", args=[pending.pk])
        response = self.client.post(
            url,
            {
                "name": "Voice of Many",
                "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                "weakness_magnitude": 0,
                "resonance_bonus_magnitude": 1,
                "social_reactivity_magnitude": 1,
                "is_visible_at_rest": False,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        pending.refresh_from_db()
        assert pending.status == PendingAlterationStatus.RESOLVED

    def test_resolve_library_path(self):
        """POST resolve action using a library entry delegates through the action."""
        from world.conditions.factories import ConditionTemplateFactory

        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )
        library_template = MagicalAlterationTemplateFactory(
            condition_template=ConditionTemplateFactory(
                name="Library Scar",
                player_description="Player sees this.",
                observer_description="Observer sees this.",
            ),
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            is_library_entry=True,
        )

        with patch.object(ResolveAlterationAction, "run") as mock_run:
            mock_run.return_value = ActionResult(
                success=True,
                message="Resolved via library.",
                data={"event_id": 42, "status": "RESOLVED"},
            )
            url = reverse("magic:pending-alteration-resolve", args=[pending.pk])
            response = self.client.post(
                url,
                {"library_template_id": library_template.pk},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["status"] == "resolved"
        assert response.data["event_id"] == 42
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["pending_id"] == pending.pk
        assert call_kwargs["library_template_id"] == library_template.pk
        assert call_kwargs["actor"] == self.character

    def test_resolve_action_failure_returns_400(self):
        """A failed action result maps to a 400 {'detail': ...} response."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )

        with patch.object(ResolveAlterationAction, "run") as mock_run:
            mock_run.return_value = ActionResult(
                success=False,
                message="You can't resolve that Mage Scar right now.",
            )
            url = reverse("magic:pending-alteration-resolve", args=[pending.pk])
            response = self.client.post(
                url,
                {
                    "name": "Voice of Many",
                    "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                    "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.data
        assert response.data["detail"] == "You can't resolve that Mage Scar right now."
        mock_run.assert_called_once()

    def test_resolve_uses_action_result_event_id(self):
        """The 200 response event_id is taken directly from the action result."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )

        with patch.object(ResolveAlterationAction, "run") as mock_run:
            mock_run.return_value = ActionResult(
                success=True,
                message="Done.",
                data={"event_id": 12345, "status": "RESOLVED"},
            )
            url = reverse("magic:pending-alteration-resolve", args=[pending.pk])
            response = self.client.post(
                url,
                {
                    "name": "Echo Scar",
                    "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                    "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data == {
            "status": "resolved",
            "event_id": 12345,
        }

    def test_library_browse(self):
        """GET library action returns tier-matched library entries."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )
        MagicalAlterationTemplateFactory(
            tier=AlterationTier.MARKED,
            is_library_entry=True,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        MagicalAlterationTemplateFactory(
            tier=AlterationTier.TOUCHED,  # wrong tier
            is_library_entry=True,
        )
        url = reverse("magic:pending-alteration-library", args=[pending.pk])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1  # only tier-matched entry

    def test_list_includes_character_attribution(self):
        """List rows carry character_id + character_name for multi-character accounts."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        url = reverse("magic:pending-alteration-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        row = response.data["results"][0]
        assert row["character_id"] == self.sheet.pk
        assert row["character_name"] == self.sheet.primary_persona.name
