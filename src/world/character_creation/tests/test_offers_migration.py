"""Test for migration 0107's ``forwards`` backfill (#3675).

Imports ``forwards`` from the migration module by path and calls it against the
real app registry, then asserts the resulting rows. This is not a
``MigratorTestCase`` replay (the models are not gone by the time this test
runs), just a direct call of the one function the migration runs.
"""

import importlib

import django.apps
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import Stage, TraditionState
from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
)
from world.character_creation.models import BeginningTradition, CharacterDraft, DistinctionOffer
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import DistinctionTag
from world.magic.factories import GlimpseTagDistinctionSuggestionFactory, TraditionFactory

_forwards = importlib.import_module("world.migrations.0107_distinction_offers_data").forwards


class DistinctionOffersMigrationTests(TestCase):
    def test_forwards_creates_offers_and_stamps_slate_and_stage(self):
        beginning = BeginningsFactory()

        distinction_a = DistinctionFactory(name="Marked by the Glimpse")
        distinction_b = DistinctionFactory(name="Also Marked")
        suggestion_a = GlimpseTagDistinctionSuggestionFactory(
            distinction=distinction_a, sort_order=1
        )
        GlimpseTagDistinctionSuggestionFactory(distinction=distinction_b, sort_order=2)

        bundled_distinction = DistinctionFactory(name="Bundled Kin")
        choice = OriginTemplateSlotChoiceFactory(grants_distinction=bundled_distinction)

        unbound = TraditionFactory(name="Unbound")
        slate_row = BeginningTraditionFactory(beginning=beginning, tradition=unbound)

        account = AccountFactory()
        draft = CharacterDraftFactory(account=account, current_stage=Stage.DISTINCTIONS)
        other_draft = CharacterDraftFactory(account=AccountFactory(), current_stage=Stage.PATH)

        _forwards(django.apps.apps, None)

        assert DistinctionOffer.objects.count() == 3

        glimpse_offer = DistinctionOffer.objects.get(distinction=distinction_a, chapter="glimpse")
        assert glimpse_offer.glimpse_tag_id == suggestion_a.tag_id
        assert glimpse_offer.arrives_as == "choice"
        assert glimpse_offer.name == distinction_a.name

        lineage_offer = DistinctionOffer.objects.get(
            distinction=bundled_distinction, chapter="lineage"
        )
        assert lineage_offer.origin_choice_id == choice.id
        assert lineage_offer.arrives_as == "bundled"

        # BeginningTradition is a SharedMemoryModel (idmapper); a bulk .update()
        # leaves this cached instance stale even after refresh_from_db(), so
        # re-fetch the raw column via .values() instead (mirrors the seed tests).
        db_state = (
            BeginningTradition.objects.filter(pk=slate_row.pk)
            .values_list("state", flat=True)
            .first()
        )
        assert db_state == TraditionState.SELF_TAUGHT

        # CharacterDraft is also idmapper-cached; read the raw column, not a
        # refreshed cached instance.
        draft_stage = (
            CharacterDraft.objects.filter(pk=draft.pk)
            .values_list("current_stage", flat=True)
            .first()
        )
        assert draft_stage == Stage.PATH

        other_draft_stage = (
            CharacterDraft.objects.filter(pk=other_draft.pk)
            .values_list("current_stage", flat=True)
            .first()
        )
        assert other_draft_stage == Stage.PATH

    def test_forwards_backfills_teachers_gone_from_the_orphaned_marker_tag(self):
        """A slate row whose ``required_distinction`` carries the pre-#3675
        ``orphaned-tradition-marker`` tag ends up TEACHERS_GONE."""
        beginning = BeginningsFactory()
        marker_tag, _ = DistinctionTag.objects.get_or_create(
            slug="orphaned-tradition-marker",
            defaults={"name": "Orphaned Tradition Marker"},
        )
        drawback = DistinctionFactory(name="Orphaned Tradition")
        drawback.tags.add(marker_tag)
        orphaned_tradition = TraditionFactory(name="Metallic Order")
        slate_row = BeginningTraditionFactory(
            beginning=beginning,
            tradition=orphaned_tradition,
            required_distinction=drawback,
        )

        _forwards(django.apps.apps, None)

        db_state = (
            BeginningTradition.objects.filter(pk=slate_row.pk)
            .values_list("state", flat=True)
            .first()
        )
        assert db_state == TraditionState.TEACHERS_GONE

    def test_forwards_is_idempotent(self):
        distinction = DistinctionFactory(name="Repeat Offer")
        GlimpseTagDistinctionSuggestionFactory(distinction=distinction)
        OriginTemplateFactory()

        _forwards(django.apps.apps, None)
        _forwards(django.apps.apps, None)

        assert DistinctionOffer.objects.filter(distinction=distinction).count() == 1
