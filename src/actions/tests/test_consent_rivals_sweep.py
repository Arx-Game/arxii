"""The batched RIVALS sweep of the consent exclusions (#3957).

The single-tenure gate (``consent_blocks_targeting`` under the rivals mode: a stranger
blocked, a one-sided hostile label still blocked, a mutual open pair admitted) is typed
in ``integration_tests/test_membership_and_consent_journeys.py``
(``KeepingHandsOffHerBody``) through ``consent category body-handling=rivals``,
``relationship declare`` from each side and ``carry_body``. What stays here is the
batched sweep ``_load_category_consent_data`` runs for the target picker, whose
``rival_owner_ids`` no reply reads back directly.
"""

from __future__ import annotations

import django.test

from actions.player_interface import _load_category_consent_data
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import SocialConsentCategoryFactory
from world.relationships.constants import LabelAwareness, TypeValence
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.services import declare_label, get_or_create_side
from world.roster.factories import grant_test_tenure


class ConsentRivalsSweepTest(django.test.TestCase):
    """``_load_category_consent_data``'s ``rival_owner_ids`` (#3957)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rival = RelationshipTypeFactory(name="RivalSweep", valence=TypeValence.HOSTILE)

    def _declare(self, *, source, target, tenure, awareness=LabelAwareness.PUBLIC) -> None:
        declare_label(
            side=get_or_create_side(source=source, target=target),
            type=self.rival,
            awareness=awareness,
            tenure=tenure,
        )

    def test_mutual_pair_with_open_tenures_is_included(self) -> None:
        owner_sheet = CharacterSheetFactory()
        actor_sheet = CharacterSheetFactory()
        owner_tenure = grant_test_tenure(owner_sheet)
        actor_tenure = grant_test_tenure(actor_sheet)
        category = SocialConsentCategoryFactory(
            key="sweep-mutual", default_mode=ConsentMode.EVERYONE
        )

        self._declare(source=owner_sheet, target=actor_sheet, tenure=owner_tenure)
        self._declare(source=actor_sheet, target=owner_sheet, tenure=actor_tenure)

        data = _load_category_consent_data({}, [owner_tenure.pk], category, actor_tenure)
        self.assertEqual(data.rival_owner_ids, {owner_tenure.pk})

    def test_one_sided_pair_is_excluded(self) -> None:
        owner_sheet = CharacterSheetFactory()
        actor_sheet = CharacterSheetFactory()
        owner_tenure = grant_test_tenure(owner_sheet)
        actor_tenure = grant_test_tenure(actor_sheet)
        category = SocialConsentCategoryFactory(
            key="sweep-one-sided", default_mode=ConsentMode.EVERYONE
        )

        # Only owner -> actor; actor never declares the owner hostile back.
        self._declare(source=owner_sheet, target=actor_sheet, tenure=owner_tenure)

        data = _load_category_consent_data({}, [owner_tenure.pk], category, actor_tenure)
        self.assertEqual(data.rival_owner_ids, set())

    def test_label_under_a_closed_tenure_is_excluded(self) -> None:
        owner_sheet = CharacterSheetFactory()
        actor_sheet = CharacterSheetFactory()
        owner_tenure = grant_test_tenure(owner_sheet)
        actor_tenure = grant_test_tenure(actor_sheet)
        category = SocialConsentCategoryFactory(
            key="sweep-closed", default_mode=ConsentMode.EVERYONE
        )

        self._declare(source=owner_sheet, target=actor_sheet, tenure=owner_tenure)
        self._declare(source=actor_sheet, target=owner_sheet, tenure=actor_tenure)
        # The actor's reciprocal label was declared under a tenure that has since closed:
        # known_label_q requires declared_by_tenure__end_date__isnull=True, so this direction
        # no longer counts as "known," and the pair is no longer mutual.
        actor_tenure.end_date = actor_tenure.start_date
        actor_tenure.save(update_fields=["end_date"])

        data = _load_category_consent_data({}, [owner_tenure.pk], category, actor_tenure)
        self.assertEqual(data.rival_owner_ids, set())
