"""Tests for the web impact-tier request-loop seam (#3304).

``StoryViewSet.perform_update`` wires ``ensure_canon_review_for_story`` into
the generic PATCH /api/stories/{id}/ path whenever ``impact_tier`` changes —
the web half of the seam telnet's ``story impact`` covers on the other side
(``commands/tests/test_canon_review_command.py::StoryImpactRequestsReviewTests``).

PATCH on this endpoint is staff-only today (``IsStoryOwnerOrStaff.
has_permission`` gates every non-safe method to staff — a pre-existing
constraint, not something this issue changes), so these tests authenticate
as staff throughout.
"""

from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.stories.constants import CanonReviewStatus, ImpactTier
from world.stories.factories import StoryFactory
from world.stories.models import CanonReview


class StoryImpactUpdateViewSetTest(APITestCase):
    """PATCH /api/stories/{id}/ with a raised impact_tier requests a review."""

    @classmethod
    def setUpTestData(cls):
        seed_default_gm_level_caps()
        cls.staff_account = AccountFactory(is_staff=True)

    def _patch(self, story, body):
        url = reverse("story-detail", kwargs={"pk": story.pk})
        return self.client.patch(url, body, format="json")

    def test_raising_to_world_creates_pending_review(self):
        story = StoryFactory(impact_tier=ImpactTier.TABLE)
        self.client.force_authenticate(user=self.staff_account)

        response = self._patch(story, {"impact_tier": "world"})

        assert response.status_code == 200, response.data
        review = CanonReview.objects.get(story=story)
        assert review.status == CanonReviewStatus.PENDING
        assert review.tier == ImpactTier.WORLD

    def test_raising_to_regional_with_no_actor_gm_profile_stays_pending(self):
        """A staff actor has no GMProfile — auto-clear never applies to them."""
        story = StoryFactory(impact_tier=ImpactTier.TABLE)
        self.client.force_authenticate(user=self.staff_account)

        response = self._patch(story, {"impact_tier": "regional"})

        assert response.status_code == 200, response.data
        review = CanonReview.objects.get(story=story)
        assert review.status == CanonReviewStatus.PENDING

    def test_raising_to_regional_auto_clears_for_experienced_staff_gm(self):
        """A staff account that also holds an EXPERIENCED GMProfile auto-clears."""
        GMProfileFactory(account=self.staff_account, level=GMLevel.EXPERIENCED)
        story = StoryFactory(impact_tier=ImpactTier.TABLE)
        self.client.force_authenticate(user=self.staff_account)

        response = self._patch(story, {"impact_tier": "regional"})

        assert response.status_code == 200, response.data
        review = CanonReview.objects.get(story=story)
        assert review.status == CanonReviewStatus.CLEARED
        assert review.reviewer is None
        assert review.notes == "auto-cleared by GM level cap"

    def test_unchanged_tier_creates_no_review(self):
        story = StoryFactory(impact_tier=ImpactTier.TABLE)
        self.client.force_authenticate(user=self.staff_account)

        response = self._patch(story, {"title": "Renamed"})

        assert response.status_code == 200, response.data
        assert not CanonReview.objects.filter(story=story).exists()
