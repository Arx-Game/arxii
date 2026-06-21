"""Tests for the interpose production-seed content (#1273).

Covers the seed-side surfaces: ChallengeTemplate creation,
the interposable Property attached via ChallengeTemplateProperty,
one ChallengeApproach per _INTERPOSE_CAPABILITIES entry, and
idempotency of ensure_interpose_content().
"""

from django.test import TestCase

from world.combat.interpose_content import (
    _INTERPOSE_CAPABILITIES,
    INTERPOSE_CHALLENGE_NAME,
    ensure_interpose_content,
)
from world.mechanics.models import (
    ChallengeApproach,
    ChallengeTemplate,
    ChallengeTemplateProperty,
)


class EnsureInterposeContentIdempotencyTests(TestCase):
    """ensure_interpose_content() is safe to call repeatedly (#1273)."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_creates_exactly_one_challenge_template(self) -> None:
        ensure_interpose_content()
        ensure_interpose_content()
        self.assertEqual(
            ChallengeTemplate.objects.filter(name=INTERPOSE_CHALLENGE_NAME).count(),
            1,
        )

    def test_interposable_property_attached(self) -> None:
        ensure_interpose_content()
        ensure_interpose_content()
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        self.assertEqual(
            ChallengeTemplateProperty.objects.filter(
                challenge_template=template,
                property__name="interposable",
            ).count(),
            1,
        )

    def test_one_challenge_approach_per_capability(self) -> None:
        ensure_interpose_content()
        ensure_interpose_content()
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        approach_count = ChallengeApproach.objects.filter(challenge_template=template).count()
        self.assertEqual(approach_count, len(_INTERPOSE_CAPABILITIES))

    def test_telekinesis_capability_not_duplicated(self) -> None:
        """ensure_interpose_content() reuses the shared telekinesis CapabilityType row."""
        from world.conditions.models import CapabilityType

        ensure_interpose_content()
        ensure_interpose_content()
        self.assertEqual(
            CapabilityType.objects.filter(name="telekinesis").count(),
            1,
        )

    def test_all_capabilities_present(self) -> None:
        """Each capability name from _INTERPOSE_CAPABILITIES has a ChallengeApproach."""
        ensure_interpose_content()
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
        approach_capability_names = set(
            ChallengeApproach.objects.filter(challenge_template=template)
            .select_related("application__capability")
            .values_list("application__capability__name", flat=True)
        )
        expected = {cap_name for cap_name, *_ in _INTERPOSE_CAPABILITIES}
        self.assertEqual(approach_capability_names, expected)
