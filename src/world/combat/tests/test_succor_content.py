"""Tests for the Succor production-seed content (#1744).

Mirrors test_interpose_content.py: covers ChallengeTemplate creation, the
succorable Property attached via ChallengeTemplateProperty, one
ChallengeApproach per _SUCCOR_CAPABILITIES entry, and idempotency of
ensure_succor_content().
"""

from django.test import TestCase

from world.combat.succor_content import (
    _SUCCOR_CAPABILITIES,
    SUCCOR_CHALLENGE_NAME,
    ensure_succor_content,
)
from world.mechanics.models import (
    ChallengeApproach,
    ChallengeTemplate,
    ChallengeTemplateProperty,
)


class EnsureSuccorContentIdempotencyTests(TestCase):
    """ensure_succor_content() is safe to call repeatedly (#1744)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_creates_exactly_one_challenge_template(self) -> None:
        ensure_succor_content()
        ensure_succor_content()
        self.assertEqual(
            ChallengeTemplate.objects.filter(name=SUCCOR_CHALLENGE_NAME).count(),
            1,
        )

    def test_succorable_property_attached(self) -> None:
        ensure_succor_content()
        ensure_succor_content()
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
        self.assertEqual(
            ChallengeTemplateProperty.objects.filter(
                challenge_template=template,
                property__name="succorable",
            ).count(),
            1,
        )

    def test_one_challenge_approach_per_capability(self) -> None:
        ensure_succor_content()
        ensure_succor_content()
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
        approach_count = ChallengeApproach.objects.filter(challenge_template=template).count()
        self.assertEqual(approach_count, len(_SUCCOR_CAPABILITIES))

    def test_telekinesis_capability_not_duplicated(self) -> None:
        """ensure_succor_content() reuses the shared telekinesis CapabilityType row."""
        from world.conditions.models import CapabilityType

        ensure_succor_content()
        ensure_succor_content()
        self.assertEqual(
            CapabilityType.objects.filter(name="telekinesis").count(),
            1,
        )

    def test_all_capabilities_present(self) -> None:
        """Each capability name from _SUCCOR_CAPABILITIES has a ChallengeApproach."""
        ensure_succor_content()
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
        approach_capability_names = set(
            ChallengeApproach.objects.filter(challenge_template=template)
            .select_related("application__capability")
            .values_list("application__capability__name", flat=True)
        )
        expected = {cap_name for cap_name, *_ in _SUCCOR_CAPABILITIES}
        self.assertEqual(approach_capability_names, expected)
