"""Organization office appointment — the delegation identity layer (#2239).

An :class:`~world.societies.models.OrganizationOffice` is a named portfolio a
leader appoints and vacates independently of rank. These services are the whole
public surface: appoint/vacate mutate the holder, ``office_holder``/``holds_office``
read it. Domain management (``world.societies.houses.services``) gates on
``holds_office`` for the ``domain-steward`` slug; other systems can reuse the same
model for their own offices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.societies.models import OrganizationOffice

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.models import Organization
    from world.traits.models import Trait


def appoint_office(
    *,
    organization: Organization,
    slug: str,
    holder: Persona,
    title: str = "",
    feeds_check: Trait | None = None,
) -> OrganizationOffice:
    """Install ``holder`` in the ``slug`` office of ``organization`` (idempotent).

    Creates the office on first appointment and updates the holder on later ones —
    an office is a singleton per (organization, slug), so re-appointing simply
    replaces the sitting holder. ``title``/``feeds_check`` are set on create and
    refreshed when provided, so a re-appoint can also correct them.
    """
    office, created = OrganizationOffice.objects.get_or_create(
        organization=organization,
        slug=slug,
        defaults={"holder": holder, "title": title, "feeds_check": feeds_check},
    )
    if not created:
        office.holder = holder
        if title:
            office.title = title
        if feeds_check is not None:
            office.feeds_check = feeds_check
        office.save(update_fields=["holder", "title", "feeds_check"])
    return office


def vacate_office(*, organization: Organization, slug: str) -> None:
    """Clear the holder of the ``slug`` office, leaving the office row intact.

    A no-op when the office does not exist — vacating an absent office is not an
    error, it is already vacant.
    """
    office = OrganizationOffice.objects.filter(organization=organization, slug=slug).first()
    if office is not None and office.holder_id is not None:
        office.holder = None
        office.save(update_fields=["holder"])


def office_holder(organization: Organization, slug: str) -> Persona | None:
    """Return the persona holding the ``slug`` office, or ``None`` if vacant/absent."""
    office = OrganizationOffice.objects.filter(organization=organization, slug=slug).first()
    return office.holder if office is not None else None


def holds_office(persona: Persona, organization: Organization, slug: str) -> bool:
    """Whether ``persona`` currently holds the ``slug`` office of ``organization``."""
    return OrganizationOffice.objects.filter(
        organization=organization, slug=slug, holder=persona
    ).exists()
