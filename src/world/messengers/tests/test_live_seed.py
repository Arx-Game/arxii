"""The missives live-server seed (#3289) writes what `frontend/e2e/missives.spec.ts` reads.

The real-test CI job runs ``seed_missive_spec`` against a throwaway Postgres database; this
runs it on the SQLite tier so a broken seed shows up before that job does.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from integration_tests.live_seeds import seed_missive_spec
from world.currency.services import get_or_create_purse
from world.messengers.constants import AttachmentResolution
from world.messengers.models import MissiveAttachment
from world.messengers.services import visible_missives_for
from world.roster.models import RosterEntry


class MissiveLiveSeedTests(TestCase):
    def test_seed_is_idempotent_and_the_letter_waits_for_quill(self) -> None:
        AccountFactory(username="e2e_test_account")

        first = seed_missive_spec(username="e2e_test_account")
        second = seed_missive_spec(username="e2e_test_account")

        self.assertEqual(first, second)
        sheet = RosterEntry.objects.get(pk=first.roster_entry_id).character_sheet
        self.assertEqual(sheet.character.db_key, "Quill Lettersend")
        self.assertEqual(sheet.active_persona.name, "the Inkwell")
        self.assertEqual(get_or_create_purse(sheet).balance, 1000)
        self.assertEqual(
            [item.display_name for item in sheet.character.carried_items.all()],
            ["brass locket"],
        )

        [letter] = visible_missives_for(sheet)
        self.assertEqual(letter.pk, first.received_missive_id)
        self.assertEqual(letter.sender_persona.name, "the Lantern Man")
        self.assertEqual(letter.recipient_persona, sheet.primary_persona)
        self.assertEqual(letter.method.name, "Courier")
        self.assertEqual(
            list(
                MissiveAttachment.objects.filter(missive=letter).values_list(
                    "coin_amount", "resolution"
                )
            ),
            [(25, AttachmentResolution.PENDING)],
        )
