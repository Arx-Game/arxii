from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Scene


class SceneVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.public = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.private = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        cls.member = AccountFactory()
        cls.outsider = AccountFactory()
        cls.staff = AccountFactory(is_staff=True)
        SceneParticipationFactory(scene=cls.private, account=cls.member)

    def test_predicate_public_visible_to_anyone(self):
        self.assertTrue(self.public.is_viewable_by(self.outsider))
        self.assertTrue(self.public.is_viewable_by(None))

    def test_predicate_private_visible_to_member_and_staff_only(self):
        self.assertTrue(self.private.is_viewable_by(self.member))
        self.assertTrue(self.private.is_viewable_by(self.staff))
        self.assertFalse(self.private.is_viewable_by(self.outsider))
        self.assertFalse(self.private.is_viewable_by(None))

    def test_queryset_authed_member(self):
        pks = set(Scene.objects.viewable_by(self.member).values_list("pk", flat=True))
        self.assertEqual(pks, {self.public.pk, self.private.pk})

    def test_queryset_outsider_public_only(self):
        pks = set(Scene.objects.viewable_by(self.outsider).values_list("pk", flat=True))
        self.assertEqual(pks, {self.public.pk})

    def test_queryset_staff_sees_all(self):
        pks = set(Scene.objects.viewable_by(self.staff).values_list("pk", flat=True))
        self.assertTrue({self.public.pk, self.private.pk} <= pks)

    def test_queryset_anonymous_public_only(self):
        pks = set(Scene.objects.viewable_by(None).values_list("pk", flat=True))
        self.assertEqual(pks, {self.public.pk})


class SceneViewSetConvergenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.public = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.private = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        cls.member = AccountFactory()
        cls.outsider = AccountFactory()
        SceneParticipationFactory(scene=cls.private, account=cls.member)

    def test_list_member_sees_public_and_own_private(self):
        client = APIClient()
        client.force_authenticate(self.member)
        resp = client.get("/api/scenes/")
        ids = {row["id"] for row in resp.data["results"]}
        self.assertEqual(ids, {self.public.id, self.private.id})

    def test_list_outsider_sees_public_only(self):
        client = APIClient()
        client.force_authenticate(self.outsider)
        resp = client.get("/api/scenes/")
        ids = {row["id"] for row in resp.data["results"]}
        self.assertEqual(ids, {self.public.id})

    def test_retrieve_private_outsider_denied(self):
        client = APIClient()
        client.force_authenticate(self.outsider)
        resp = client.get(f"/api/scenes/{self.private.id}/")
        self.assertIn(resp.status_code, (403, 404))
