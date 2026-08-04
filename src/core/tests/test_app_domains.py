from django.test import TestCase

from actions.models import ActionTemplate
from core.app_domains import domain_of
from world.magic.models import Technique


class DomainOfTest(TestCase):
    def test_world_subpackage_yields_its_own_name(self):
        self.assertEqual(domain_of(Technique), "magic")

    def test_non_world_first_party_app_yields_top_level_name(self):
        self.assertEqual(domain_of(ActionTemplate), "actions")

    def test_matches_app_label_before_the_collapse(self):
        # Behaviour-preserving guard: while the apps are still separate,
        # domain_of must agree with Django's own label for every model.
        for model in (Technique, ActionTemplate):
            self.assertEqual(domain_of(model), model._meta.app_label)
