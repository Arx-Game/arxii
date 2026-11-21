"""The Distinction list's "Offer on the Identity stage" action (#5255).

The Identity chapter takes no opener, so staff place many cards there at once from the
Distinction list instead of opening the Distinction Builder once per card. A migration may
not create these rows (content is authored by a person), so this action is how the
personality cards production already holds reach the stage.
"""

from __future__ import annotations

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from evennia_extensions.factories import AccountFactory
from web.admin.authoring.contributors import link_contributor
from web.admin.tuning import required_content as rc
from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.models import DistinctionOffer
from world.distinctions.factories import DistinctionFactory


class OfferOnIdentityActionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = AccountFactory(is_staff=True, is_superuser=True)
        cls.writer = link_contributor(cls.author, name="Scribe")
        cls.indolent = DistinctionFactory(name="Indolent")
        cls.tireless = DistinctionFactory(name="Tireless")
        cls.proud = DistinctionFactory(name="Proud")
        cls.url = reverse("admin:arxii_distinction_changelist")

    def _run(self, *cards):
        return self.client.post(
            self.url,
            {"action": "offer_on_identity", "_selected_action": [card.pk for card in cards]},
            follow=True,
        )

    def test_the_selected_cards_get_an_identity_line_each_credited_and_in_name_order(self):
        self.client.force_login(self.author)
        response = self._run(self.tireless, self.indolent)
        self.assertEqual(response.status_code, 200)
        lines = list(DistinctionOffer.objects.filter(chapter=OfferChapter.IDENTITY))
        self.assertEqual([line.distinction.name for line in lines], ["Indolent", "Tireless"])
        for line in lines:
            line.full_clean()
            self.assertEqual(line.arrives_as, OfferArrival.CHOICE)
            self.assertEqual(line.set_openers, [])
            self.assertTrue(line.is_active)
            self.assertEqual(line.written_by, self.writer)
        self.assertFalse(DistinctionOffer.objects.filter(distinction=self.proud).exists())
        said = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(said, ["Now offered on the Identity stage: Indolent, Tireless."])

    def test_a_card_already_placed_is_left_alone_and_named(self):
        """A line staff switched off stays off: running the action again is no way around it."""
        existing = DistinctionOfferFactory(
            distinction=self.indolent, chapter=OfferChapter.IDENTITY, is_active=False, sort_order=4
        )
        self.client.force_login(self.author)
        response = self._run(self.indolent, self.proud)
        lines = DistinctionOffer.objects.filter(chapter=OfferChapter.IDENTITY)
        self.assertEqual(lines.count(), 2)
        existing.refresh_from_db()
        self.assertFalse(existing.is_active)
        # The new line sorts after the ones already there.
        self.assertEqual(lines.get(distinction=self.proud).sort_order, 5)
        said = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(
            said,
            [
                "Now offered on the Identity stage: Proud.",
                "Already placed on the Identity stage: Indolent.",
            ],
        )

    def test_the_content_dashboard_flags_an_identity_stage_with_no_card(self):
        rows = {dep.key: dep for dep in rc.build_registry(rc._declarations())}
        row = rows["character_creation.identity_cards"]
        self.assertEqual(row.tier, rc.DependencyTier.REQUIRED)
        self.assertFalse(row.probe.resolve(None).present)
        DistinctionOfferFactory(
            distinction=self.indolent, chapter=OfferChapter.IDENTITY, is_active=False
        )
        self.assertFalse(row.probe.resolve(None).present)
        self.client.force_login(self.author)
        self._run(self.proud)
        self.assertTrue(row.probe.resolve(None).present)
