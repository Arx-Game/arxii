"""Natural keys for the situation content models (#2865).

Every model that enters ``CONTENT_MODELS`` must have ``NaturalKeyMixin`` with a
stable, non-pk natural key. ``SituationTemplate`` already keyed on name; its two
link tables did not, so registering them for lore-repo export needed keys (and,
for the trap link, a uniqueness constraint the key could stand on). These tests
prove both round-trip through ``get_by_natural_key`` and serialize with natural
FK keys rather than raw pks — the property export/import relies on.
"""

from django.core import serializers
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.mechanics.factories import (
    ChallengeTemplateFactory,
    SituationChallengeLinkFactory,
    SituationTemplateFactory,
    SituationTrapLinkFactory,
)
from world.mechanics.models import SituationChallengeLink, SituationTrapLink


class SituationChallengeLinkNaturalKeyTest(TestCase):
    def test_natural_key_is_the_two_templates(self) -> None:
        situation = SituationTemplateFactory(name="The Sealed Passage")
        challenge = ChallengeTemplateFactory(name="A Barred Way")
        link = SituationChallengeLinkFactory(
            situation_template=situation, challenge_template=challenge
        )

        assert link.natural_key() == ("The Sealed Passage", "A Barred Way")

    def test_round_trip(self) -> None:
        link = SituationChallengeLinkFactory()

        found = SituationChallengeLink.objects.get_by_natural_key(*link.natural_key())

        assert found.pk == link.pk

    def test_serializes_with_natural_keys(self) -> None:
        link = SituationChallengeLinkFactory(
            situation_template__name="Serialized Situation",
            challenge_template__name="Serialized Challenge",
        )

        data = serializers.serialize(
            "json", [link], use_natural_foreign_keys=True, use_natural_primary_keys=True
        )

        assert "Serialized Situation" in data
        assert "Serialized Challenge" in data
        # The FKs serialize as their natural keys, never as raw pks.
        assert f'"situation_template": {link.situation_template_id}' not in data
        assert f'"challenge_template": {link.challenge_template_id}' not in data


class SituationTrapLinkNaturalKeyTest(TestCase):
    def test_natural_key_is_situation_and_name(self) -> None:
        link = SituationTrapLinkFactory(
            situation_template__name="Trapped Vault", name="the pressure plate"
        )

        assert link.natural_key() == ("Trapped Vault", "the pressure plate")

    def test_round_trip(self) -> None:
        link = SituationTrapLinkFactory(name="the tripwire")

        found = SituationTrapLink.objects.get_by_natural_key(*link.natural_key())

        assert found.pk == link.pk

    def test_duplicate_name_on_one_situation_is_rejected(self) -> None:
        """The uniqueness the natural key stands on (#2865)."""
        first = SituationTrapLinkFactory(name="the pressure plate")

        with transaction.atomic(), self.assertRaises(IntegrityError):
            SituationTrapLinkFactory(
                situation_template=first.situation_template, name="the pressure plate"
            )

    def test_same_name_on_a_different_situation_is_fine(self) -> None:
        SituationTrapLinkFactory(name="the pressure plate")
        other = SituationTrapLinkFactory(name="the pressure plate")

        assert SituationTrapLink.objects.filter(name="the pressure plate").count() == 2
        assert other.pk is not None
