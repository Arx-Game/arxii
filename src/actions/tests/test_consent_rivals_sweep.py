"""Tests for the #3957 consent RIVALS sweep.

Covers ``actions.player_interface._load_category_consent_data``'s batched RIVALS branch
(``rival_owner_ids``) and the single-tenure ``world.consent.services.consent_blocks_targeting``
gate end-to-end, both reading mutual hostile ``RelationshipLabel`` rows instead of the deleted
``scenes.Rivalry`` model (#3957). Neither had direct unit coverage before this file (the two
tests closest to this path, ``actions/tests/test_social_consent_enforcement.py``, exercise the
single-tenure ``_tenure_blocks_actor`` only, never the batched sweep).
"""

from __future__ import annotations

import django.test

from actions.player_interface import _load_category_consent_data
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.consent.services import consent_blocks_targeting
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
        # The actor's reciprocal label was declared under a tenure that has since closed —
        # known_label_q requires declared_by_tenure__end_date__isnull=True, so this direction
        # no longer counts as "known," and the pair is no longer mutual.
        actor_tenure.end_date = actor_tenure.start_date
        actor_tenure.save(update_fields=["end_date"])

        data = _load_category_consent_data({}, [owner_tenure.pk], category, actor_tenure)
        self.assertEqual(data.rival_owner_ids, set())


class ConsentBlocksTargetingRivalsModeTest(django.test.TestCase):
    """End-to-end through ``world.consent.services.consent_blocks_targeting`` (#3957)."""

    def test_only_the_mutual_open_pair_is_allowed(self) -> None:
        owner_sheet = CharacterSheetFactory()
        actor_sheet = CharacterSheetFactory()
        owner_tenure = grant_test_tenure(owner_sheet)
        actor_tenure = grant_test_tenure(actor_sheet)
        rival = RelationshipTypeFactory(name="RivalE2E", valence=TypeValence.HOSTILE)
        category = SocialConsentCategoryFactory(key="sweep-e2e", default_mode=ConsentMode.EVERYONE)
        pref = SocialConsentPreferenceFactory(tenure=owner_tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=category, mode=ConsentMode.RIVALS
        )

        def _blocked() -> bool:
            return consent_blocks_targeting(
                owner_tenure=owner_tenure, category=category, actor_tenure=actor_tenure
            )

        # No labels yet: RIVALS mode blocks a non-rival.
        self.assertTrue(_blocked())

        # One-sided hostile label: still blocked — mutual_hostile requires both directions.
        declare_label(
            side=get_or_create_side(source=owner_sheet, target=actor_sheet),
            type=rival,
            awareness=LabelAwareness.PUBLIC,
            tenure=owner_tenure,
        )
        self.assertTrue(_blocked())

        # Mutual, both tenures open: allowed.
        declare_label(
            side=get_or_create_side(source=actor_sheet, target=owner_sheet),
            type=rival,
            awareness=LabelAwareness.PUBLIC,
            tenure=actor_tenure,
        )
        self.assertFalse(_blocked())
