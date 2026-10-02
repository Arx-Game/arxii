"""Audere offer dialog titles are admin-editable copy (#4101, Task 5).

Covers:
    1. AudereThreshold.offer_title/offer_strip_label/offer_body_text and
       AudereMajoraThreshold.offer_title ship with a PLACEHOLDER marker by
       model field default (never a seed migration).
    2. The required-content probe reports the placeholder fields as missing.
    3. The probe clears once staff author real copy over every field.
"""

from __future__ import annotations

from django.test import TestCase

from web.admin.tuning.required_content import _probe_audere_offer_copy
from world.magic.factories import AudereMajoraThresholdFactory, AudereThresholdFactory


class AudereOfferCopyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.threshold = AudereThresholdFactory()
        cls.majora = AudereMajoraThresholdFactory()

    def test_new_fields_ship_placeholder(self):
        self.assertIn("PLACEHOLDER", self.threshold.offer_title)
        self.assertIn("PLACEHOLDER", self.threshold.offer_strip_label)
        self.assertIn("{intensity}", self.threshold.offer_body_text)
        self.assertIn("PLACEHOLDER", self.majora.offer_title)

    def test_probe_reports_placeholders(self):
        result = _probe_audere_offer_copy()
        self.assertFalse(result.present)
        self.assertIn("offer_title", result.missing)

    def test_probe_clears_when_authored(self):
        self.threshold.offer_title = "Authored"
        self.threshold.offer_strip_label = "Authored"
        self.threshold.offer_body_text = "Authored {intensity}"
        self.threshold.save()
        self.majora.offer_title = "Authored"
        self.majora.save()
        self.assertTrue(_probe_audere_offer_copy().present)
