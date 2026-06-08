"""get_spreadable_deeds + spread value formula (#745 — Spread a Tale Phase 1a)."""

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    LegendEntryFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)
from world.societies.spread_services import compute_spread_value, get_spreadable_deeds


class GetSpreadableDeedsTest(TestCase):
    def setUp(self) -> None:
        self.persona = PersonaFactory()
        self.society = SocietyFactory()
        org = OrganizationFactory(society=self.society)
        OrganizationMembershipFactory(persona=self.persona, organization=org)

    def test_returns_deed_known_to_my_society(self) -> None:
        deed = LegendEntryFactory()
        deed.societies_aware.add(self.society)
        self.assertIn(deed, list(get_spreadable_deeds(self.persona)))

    def test_excludes_unknown_and_inactive(self) -> None:
        unknown = LegendEntryFactory()
        inactive = LegendEntryFactory(is_active=False)
        inactive.societies_aware.add(self.society)
        deeds = list(get_spreadable_deeds(self.persona))
        self.assertNotIn(unknown, deeds)
        self.assertNotIn(inactive, deeds)


class ComputeSpreadValueTest(TestCase):
    def test_solid_success_at_baseline(self) -> None:
        # base 100, success_level 1 (~10%), multiplier 1.0 -> ~10
        self.assertEqual(compute_spread_value(base_value=100, success_level=1, multiplier=1.0), 10)

    def test_failure_yields_zero(self) -> None:
        self.assertEqual(compute_spread_value(base_value=100, success_level=-1, multiplier=2.0), 0)

    def test_overwhelming_in_thronging_is_large(self) -> None:
        self.assertGreater(
            compute_spread_value(base_value=100, success_level=4, multiplier=2.2), 100
        )


class SeedFastPathTest(TestCase):
    """The seed-on-first-use helpers must not re-seed (or re-write) once seeded."""

    def test_template_seeded_once_and_fast_path_is_cheap(self) -> None:
        from actions.models.action_templates import ActionTemplate
        from world.societies.spread_services import get_or_create_spread_a_tale_template

        first = get_or_create_spread_a_tale_template()
        second = get_or_create_spread_a_tale_template()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ActionTemplate.objects.filter(name="Spread a Tale").count(), 1)
        # Steady state: a single fetch, not the full chain of get_or_creates.
        with self.assertNumQueries(1):
            get_or_create_spread_a_tale_template()

    def test_ensure_skills_idempotent(self) -> None:
        from world.skills.models import Specialization
        from world.societies.spread_services import ensure_spread_skills

        ensure_spread_skills()
        ensure_spread_skills()
        self.assertEqual(
            Specialization.objects.filter(
                name__in=["Oratory", "Prose", "Singing", "Propaganda"]
            ).count(),
            4,
        )
