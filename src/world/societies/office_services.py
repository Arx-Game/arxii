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

from django.db import models

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


def can_oversee_org(persona: Persona, organization: Organization) -> bool:
    """Parent-org oversight over a child org (#2820): READ access, never command.

    True when ``organization`` has a parent and ``persona`` is either the
    parent's leadership (a ``can_manage_ranks`` rank) or holds the parent's
    ``spymaster`` office. The spymaster may be an honorific worn by the child
    org's own rank 1, or a coordinator above several child heads — either way
    command stays with the child's leadership; this grants visibility only.
    """
    from world.societies.constants import SPYMASTER_OFFICE  # noqa: PLC0415
    from world.societies.houses.services import is_org_leader  # noqa: PLC0415

    parent = organization.parent_org
    if parent is None:
        return False
    return is_org_leader(persona, parent) or holds_office(persona, parent, SPYMASTER_OFFICE)


def overseen_org_ids(persona: Persona) -> list[int]:
    """Ids of child orgs ``persona`` may read via parent oversight (#2820)."""
    from world.societies.constants import SPYMASTER_OFFICE  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    led_parents = models.Q(
        parent_org__memberships__persona=persona,
        parent_org__memberships__left_at__isnull=True,
        parent_org__memberships__exiled_at__isnull=True,
        parent_org__memberships__rank__can_manage_ranks=True,
    )
    spymaster_parents = models.Q(
        parent_org__offices__slug=SPYMASTER_OFFICE,
        parent_org__offices__holder=persona,
    )
    return list(
        Organization.objects.filter(led_parents | spymaster_parents)
        .values_list("pk", flat=True)
        .distinct()
    )
