from django.contrib import admin
from django.test import TestCase

from world.magic.models.signature import SignatureMotifBonus


class SignatureAdminTests(TestCase):
    def test_signature_motif_bonus_is_registered(self):
        assert SignatureMotifBonus in admin.site._registry
