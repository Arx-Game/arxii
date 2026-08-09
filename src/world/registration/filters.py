"""FilterSets for the registration API."""

from django.db.models import QuerySet
from django.utils import timezone
import django_filters

from world.registration.constants import InviteStatus
from world.registration.models import AccountInvite


class AccountInviteFilter(django_filters.FilterSet):
    """Filter staff invite listings by email substring or derived status."""

    email = django_filters.CharFilter(field_name="email", lookup_expr="icontains")
    status = django_filters.ChoiceFilter(choices=InviteStatus.choices, method="filter_status")

    class Meta:
        model = AccountInvite
        fields: list[str] = ["email", "status"]

    def filter_status(
        self, queryset: QuerySet[AccountInvite], name: str, value: str
    ) -> QuerySet[AccountInvite]:
        """Status is derived (never stored) — mirror ``AccountInvite.status`` in SQL."""
        now = timezone.now()
        if value == InviteStatus.REVOKED:
            return queryset.filter(revoked_at__isnull=False)
        if value == InviteStatus.REDEEMED:
            return queryset.filter(revoked_at__isnull=True, redeemed_at__isnull=False)
        if value == InviteStatus.EXPIRED:
            return queryset.filter(
                revoked_at__isnull=True, redeemed_at__isnull=True, expires_at__lte=now
            )
        if value == InviteStatus.PENDING:
            return queryset.filter(
                revoked_at__isnull=True, redeemed_at__isnull=True, expires_at__gt=now
            )
        return queryset
