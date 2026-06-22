"""Filters for the secret-tab API (#1334)."""

import django_filters

from world.secrets.models import SecretKnowledge


class KnownSecretFilter(django_filters.FilterSet):
    """Filter a viewer's known secrets — by ``subject`` (a CharacterSheet pk) for one tab."""

    subject = django_filters.NumberFilter(field_name="secret__subject_sheet_id")

    class Meta:
        model = SecretKnowledge
        fields = ["subject"]
