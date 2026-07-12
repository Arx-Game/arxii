"""Filters for the magic system API."""

from django.db.models import QuerySet
import django_filters
from rest_framework.exceptions import ValidationError

from actions.models import ConsequencePool
from world.magic.constants import GainSource, ParticipationRule
from world.magic.models import (
    Cantrip,
    CharacterAnima,
    CharacterAura,
    CharacterGift,
    CharacterResonance,
    ResonanceGrant,
    Thread,
    ThreadWeavingTeachingOffer,
)
from world.magic.models.sessions import RitualSession


class ConsequencePoolCatalogFilter(django_filters.FilterSet):
    """Filter for the consequence-pool flavor catalog listing (#1995).

    ``action_category=physical`` narrows to the combat offense catalog's flavors;
    any other valid ``ActionCategory`` value narrows to the magic technique-cast
    catalog's; absent keeps the flat union of both (the technique builder's
    category-agnostic picker default). The CG cantrip picker can pass the draft's
    derived category so players are only offered flavors their technique can
    legally keep at finalize time (``resolve_cast_action_template`` enforces the
    same split at submit/finalize).
    """

    action_category = django_filters.CharFilter(method="filter_by_action_category")

    class Meta:
        model = ConsequencePool
        fields = ["action_category"]

    def filter_by_action_category(
        self, queryset: QuerySet[ConsequencePool], name: str, value: str
    ) -> QuerySet[ConsequencePool]:
        """Narrow the catalog to the category-matching base pool's children."""
        from actions.constants import ActionCategory  # noqa: PLC0415
        from world.combat.seeds_offense import get_melee_offense_pool  # noqa: PLC0415
        from world.magic.seeds_cast import get_standalone_cast_pool  # noqa: PLC0415

        valid = {c.value for c in ActionCategory}
        if value not in valid:
            raise ValidationError({"action_category": "Invalid action category."})
        if value == ActionCategory.PHYSICAL:
            return queryset.filter(parent=get_melee_offense_pool())
        return queryset.filter(parent=get_standalone_cast_pool())


class CantripFilter(django_filters.FilterSet):
    """Filter for Cantrip list views."""

    path_id = django_filters.NumberFilter(method="filter_by_path")

    class Meta:
        model = Cantrip
        fields = ["path_id"]

    def filter_by_path(
        self, queryset: QuerySet[Cantrip], name: str, value: int
    ) -> QuerySet[Cantrip]:
        """Filter cantrips by path's allowed styles."""
        from world.classes.models import Path  # noqa: PLC0415

        try:
            Path.objects.get(pk=value, is_active=True)
        except (Path.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"path_id": "Invalid or inactive path."}) from None
        return queryset.filter(style__allowed_paths__id=value)


class ThreadFilter(django_filters.FilterSet):
    """Filter for Thread list views (Spec A §4.5)."""

    resonance = django_filters.NumberFilter(field_name="resonance_id")
    target_kind = django_filters.CharFilter(field_name="target_kind")

    class Meta:
        model = Thread
        fields = ["resonance", "target_kind"]


class CharacterAuraFilter(django_filters.FilterSet):
    """Filter for CharacterAura. Allows narrowing to a specific character."""

    character = django_filters.NumberFilter(field_name="character_id")

    class Meta:
        model = CharacterAura
        fields = ["character"]


class CharacterResonanceFilter(django_filters.FilterSet):
    """Filter for CharacterResonance. Narrows to a specific character_sheet."""

    character_sheet = django_filters.NumberFilter(field_name="character_sheet_id")
    resonance = django_filters.NumberFilter(field_name="resonance_id")

    class Meta:
        model = CharacterResonance
        fields = ["character_sheet", "resonance"]


class CharacterGiftFilter(django_filters.FilterSet):
    """Filter for CharacterGift. Narrows to a specific character."""

    character = django_filters.NumberFilter(field_name="character_id")
    gift = django_filters.NumberFilter(field_name="gift_id")

    class Meta:
        model = CharacterGift
        fields = ["character", "gift"]


class CharacterAnimaFilter(django_filters.FilterSet):
    """Filter for CharacterAnima. Narrows to a specific character."""

    character = django_filters.NumberFilter(field_name="character_id")

    class Meta:
        model = CharacterAnima
        fields = ["character"]


class ThreadWeavingTeachingOfferFilter(django_filters.FilterSet):
    """Filter for ThreadWeavingTeachingOffer list views (Spec A §4.5)."""

    target_kind = django_filters.CharFilter(field_name="unlock__target_kind")

    class Meta:
        model = ThreadWeavingTeachingOffer
        fields = ["target_kind"]


class ResonanceGrantFilterSet(django_filters.FilterSet):
    """Filter for ResonanceGrant read-only ledger (Spec C Task 25)."""

    source = django_filters.ChoiceFilter(choices=GainSource.choices)
    resonance = django_filters.NumberFilter(field_name="resonance_id")
    granted_after = django_filters.IsoDateTimeFilter(field_name="granted_at", lookup_expr="gte")
    granted_before = django_filters.IsoDateTimeFilter(field_name="granted_at", lookup_expr="lte")

    class Meta:
        model = ResonanceGrant
        fields = ["source", "resonance", "granted_after", "granted_before"]


class RitualSessionFilterSet(django_filters.FilterSet):
    """FilterSet for RitualSession list endpoint (Covenants Slice B §4.12).

    as_invitee=me — sessions where the requesting user is an INVITED participant.
    as_initiator=me — sessions where the requesting user is the initiator.
    ritual — filter by Ritual PK.
    participation_rule — filter by ParticipationRule enum value.
    scene — filter by the session's captured origin Scene PK (#2159).

    The as_invitee / as_initiator filters accept the literal value "me" (case-insensitive).
    Any other value is ignored (no-op filter).
    """

    as_invitee = django_filters.CharFilter(method="filter_as_invitee")
    as_initiator = django_filters.CharFilter(method="filter_as_initiator")
    ritual = django_filters.NumberFilter(field_name="ritual_id")
    participation_rule = django_filters.ChoiceFilter(
        field_name="ritual__participation_rule",
        choices=ParticipationRule.choices,
    )
    scene = django_filters.NumberFilter(field_name="scene_id")

    class Meta:
        model = RitualSession
        fields = ["as_invitee", "as_initiator", "ritual", "participation_rule", "scene"]

    def _my_sheet_ids(self) -> "list[int]":
        """Resolve the requesting user's active character sheet PKs."""
        from typing import cast  # noqa: PLC0415

        from evennia.accounts.models import AccountDB  # noqa: PLC0415

        from world.roster.models import RosterEntry  # noqa: PLC0415

        request = self.request
        if request is None or not request.user.is_authenticated:
            return []
        user = cast(AccountDB, request.user)
        return list(RosterEntry.objects.for_account(user).character_ids())

    def filter_as_invitee(
        self, queryset: QuerySet[RitualSession], name: str, value: str
    ) -> QuerySet[RitualSession]:
        """Filter to sessions where the requesting user is an invited participant."""
        if value.lower() != "me":  # noqa: STRING_LITERAL
            return queryset
        sheet_ids = self._my_sheet_ids()
        if not sheet_ids:
            return queryset.none()
        return queryset.filter(participants__character_sheet_id__in=sheet_ids).distinct()

    def filter_as_initiator(
        self, queryset: QuerySet[RitualSession], name: str, value: str
    ) -> QuerySet[RitualSession]:
        """Filter to sessions where the requesting user is the initiator."""
        if value.lower() != "me":  # noqa: STRING_LITERAL
            return queryset
        sheet_ids = self._my_sheet_ids()
        if not sheet_ids:
            return queryset.none()
        return queryset.filter(initiator_id__in=sheet_ids)
