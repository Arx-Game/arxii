from django.contrib import admin as django_admin
from django.test import TestCase

from world.magic.models.dramatic_moment import DramaticMomentTag, DramaticMomentType


class DramaticMomentAdminTest(TestCase):
    def test_type_is_registered_and_editable(self):
        self.assertIn(DramaticMomentType, django_admin.site._registry)
        self.assertTrue(django_admin.site._registry[DramaticMomentType].has_add_permission(None))

    def test_tag_admin_is_read_only(self):
        tag_admin = django_admin.site._registry[DramaticMomentTag]
        self.assertFalse(tag_admin.has_add_permission(None))
        self.assertFalse(tag_admin.has_change_permission(None))
