from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from world.magic.models.dramatic_moment import DramaticMomentTag, DramaticMomentType


class DramaticMomentAdminTest(TestCase):
    def test_type_is_registered_and_editable(self):
        self.assertIn(DramaticMomentType, django_admin.site._registry)
        User = get_user_model()
        superuser = User.objects.create_superuser("dm_admin", "dm@example.com", "pw")
        request = RequestFactory().get("/")
        request.user = superuser
        type_admin = django_admin.site._registry[DramaticMomentType]
        self.assertTrue(type_admin.has_add_permission(request))

    def test_tag_admin_is_read_only(self):
        tag_admin = django_admin.site._registry[DramaticMomentTag]
        self.assertFalse(tag_admin.has_add_permission(None))
        self.assertFalse(tag_admin.has_change_permission(None))
