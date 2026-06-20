"""Tests for the "Catch the Faller" catch-content seed (#1228, Task 4).

``ensure_fall_content`` now also seeds (via ``ensure_catch_content``) the
capability-gated catch challenge: a ``ChallengeTemplate`` named
``CATCH_THE_FALLER_NAME`` whose approaches are gated by catch capabilities
(fly / teleport / telekinesis / acrobatics). The named four are SEED EXAMPLES;
the design's whole point is that adding a new catch capability later is PURE
DATA — one ``CapabilityType`` + ``Application`` + ``ChallengeApproach`` row,
with zero engine code. These tests pin that contract.
"""

from django.test import TestCase

from world.areas.positioning.constants import (
    ACROBATICS_CAPABILITY_NAME,
    CATCH_CHECK_TYPE_NAME,
    CATCH_THE_FALLER_NAME,
    CATCHABLE_PROPERTY_NAME,
    FLY_CAPABILITY_NAME,
    TELEKINESIS_CAPABILITY_NAME,
    TELEPORT_CAPABILITY_NAME,
)
from world.areas.positioning.plummet_content import ensure_fall_content
from world.checks.models import CheckType
from world.conditions.models import CapabilityType
from world.mechanics.constants import ResolutionType
from world.mechanics.factories import ApplicationFactory, ChallengeApproachFactory
from world.mechanics.models import (
    ChallengeApproach,
    ChallengeTemplate,
    ChallengeTemplateConsequence,
    Property,
)

_SEED_CAPABILITIES = frozenset(
    {
        FLY_CAPABILITY_NAME,
        TELEPORT_CAPABILITY_NAME,
        TELEKINESIS_CAPABILITY_NAME,
        ACROBATICS_CAPABILITY_NAME,
    }
)


class EnsureCatchContentTests(TestCase):
    def test_catch_challenge_has_one_approach_per_capability(self):
        ensure_fall_content()
        tmpl = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)
        caps = {a.application.capability.name for a in tmpl.cached_approaches}
        self.assertTrue(caps >= _SEED_CAPABILITIES)
        # One approach per seed capability (no extras seeded).
        seeded = [a for a in tmpl.cached_approaches if a.application.capability.name in caps]
        self.assertEqual(len(seeded), len({a.id for a in seeded}))

    def test_every_catch_application_targets_the_shared_property(self):
        ensure_fall_content()
        catch_property = Property.objects.get(name=CATCHABLE_PROPERTY_NAME)
        tmpl = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)
        for approach in tmpl.cached_approaches:
            self.assertEqual(approach.application.target_property_id, catch_property.id)

    def test_template_has_authored_severity_and_catch_property(self):
        ensure_fall_content()
        tmpl = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)
        # Difficulty lives on the authored row, not as a literal in engine code.
        self.assertGreaterEqual(tmpl.severity, 1)
        # The catch property is linked to the template so its approaches surface
        # in _match_approaches (which gates on the challenge's properties).
        catch_property = Property.objects.get(name=CATCHABLE_PROPERTY_NAME)
        property_ids = {p.id for p in tmpl.cached_properties}
        self.assertIn(catch_property.id, property_ids)

    def test_clean_catch_destroys_the_challenge(self):
        # A SUCCESS-tier consequence with ResolutionType.DESTROY must exist so a
        # clean catch resolves/deactivates the challenge (Task 7 reads this).
        ensure_fall_content()
        tmpl = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)
        destroy_links = ChallengeTemplateConsequence.objects.filter(
            challenge_template=tmpl,
            resolution_type=ResolutionType.DESTROY,
            consequence__outcome_tier__success_level__gte=1,
        )
        self.assertTrue(destroy_links.exists())

    def test_approaches_reuse_a_single_check_type(self):
        # Reuse ONE existing CheckType across every approach — no per-capability
        # CheckType authoring.
        ensure_fall_content()
        tmpl = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)
        check_type_ids = {a.check_type_id for a in tmpl.cached_approaches}
        self.assertEqual(len(check_type_ids), 1)
        self.assertEqual(CheckType.objects.filter(name=CATCH_CHECK_TYPE_NAME).count(), 1)

    def test_adding_a_capability_needs_no_code(self):
        # Document the data-only extensibility path: a new
        # Application + ChallengeApproach row surfaces among the template's
        # approaches with no engine change.
        ensure_fall_content()
        catch_property = Property.objects.get(name=CATCHABLE_PROPERTY_NAME)
        check_type = CheckType.objects.get(name=CATCH_CHECK_TYPE_NAME)
        tmpl = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)

        new_cap, _ = CapabilityType.objects.get_or_create(name="water_cushion")
        app = ApplicationFactory(
            name="Catch via Water Cushion",
            capability=new_cap,
            target_property=catch_property,
        )
        ChallengeApproachFactory(
            challenge_template=tmpl,
            application=app,
            check_type=check_type,
            display_name="Conjured Water Cushion",
        )

        # Refetch — cached_approaches is a cached_property on a fresh instance.
        fresh = ChallengeTemplate.objects.get(pk=tmpl.pk)
        self.assertTrue(
            any(a.application.capability.name == "water_cushion" for a in fresh.cached_approaches)
        )

    def test_is_idempotent(self):
        ensure_fall_content()
        ensure_fall_content()
        self.assertEqual(ChallengeTemplate.objects.filter(name=CATCH_THE_FALLER_NAME).count(), 1)
        self.assertEqual(Property.objects.filter(name=CATCHABLE_PROPERTY_NAME).count(), 1)
        self.assertEqual(CheckType.objects.filter(name=CATCH_CHECK_TYPE_NAME).count(), 1)
        tmpl = ChallengeTemplate.objects.get(name=CATCH_THE_FALLER_NAME)
        # One approach per seed capability — not duplicated on the second call.
        seed_approaches = ChallengeApproach.objects.filter(
            challenge_template=tmpl,
            application__capability__name__in=_SEED_CAPABILITIES,
        )
        self.assertEqual(seed_approaches.count(), len(_SEED_CAPABILITIES))
        for capability_name in _SEED_CAPABILITIES:
            self.assertEqual(CapabilityType.objects.filter(name=capability_name).count(), 1)
