"""Cached handlers for the societies app (ADR-0093).

All lookups are list comprehensions against pre-fetched data — never
.filter()/.exists() in service functions.
"""

from django.utils.functional import cached_property


class OrganizationGiftGrantHandler:
    """Cached handler for an Organization's acquired gift grants (ADR-0093).

    Loads all OrganizationGiftGrant rows once with select_related on gift +
    gift__techniques. All lookups are list comprehensions against the cached list.
    """

    def __init__(self, organization) -> None:
        self._organization = organization

    @cached_property
    def _rows(self) -> list:
        from world.societies.models import OrganizationGiftGrant  # noqa: PLC0415

        return list(
            OrganizationGiftGrant.objects.filter(organization=self._organization).select_related(
                "gift"
            )
        )

    def acquired_gifts(self) -> list:
        """Return all Gifts the org has acquired."""
        return [grant.gift for grant in self._rows]

    def acquired_techniques_for(self, resonance) -> list:
        """Return techniques from gifts whose supported-resonance set contains the given resonance.

        Only gifts matching the thread's resonance are included, so a member
        weaving a Fire resonance thread does not get techniques from a
        Shadow-only gift.
        """
        techniques = []
        for grant in self._rows:
            gift = grant.gift
            if any(r.pk == resonance.pk for r in gift.cached_resonances):
                techniques.extend(gift.cached_techniques)
        return techniques

    def anchor_cap_for(self, resonance) -> int:
        """Return the max anchor_cap across grants matching the given resonance.

        An org may have multiple gifts whose supported sets contain the resonance.
        The most invested capability (highest anchor_cap) wins. Returns 0 if no
        matching grant exists.
        """
        caps = [
            grant.anchor_cap
            for grant in self._rows
            if any(r.pk == resonance.pk for r in grant.gift.cached_resonances)
        ]
        return max(caps, default=0)

    def invalidate(self) -> None:
        """Clear the cached grant list. Called when a grant is created or removed."""
        self.__dict__.pop("_rows", None)
