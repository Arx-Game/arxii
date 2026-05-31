"""Constants for the societies system."""

from django.db import models


class OrganizationKind(models.TextChoices):
    """Discriminator for Organization. Each kind has a corresponding row in the
    OrganizationType catalog (admin-editable rank titles) and an optional
    per-kind details model (e.g., Covenant for COVENANT, NobleHouse for NOBLE
    when that ships).

    Adding a new kind: add an enum member here AND seed an OrganizationType
    fixture row (or create one via admin). Per-kind details models ship
    separately when their consumers materialize.
    """

    NOBLE = "noble", "Noble"
    BUSINESS = "business", "Business"
    GUILD = "guild", "Guild"
    GANG = "gang", "Gang"
    SECRET_SOCIETY = "secret_society", "Secret Society"
    COMMONER_FAMILY = "commoner_family", "Commoner Family"
    COVENANT = "covenant", "Covenant"
    DEVOTIONAL = "devotional", "Devotional"
    OTHER = "other", "Other"


# Map legacy OrganizationType.name values (pre-refactor) to their new
# OrganizationKind value. Used by the data migration in Task A4.
LEGACY_ORG_TYPE_NAME_TO_KIND = {
    "noble_family": OrganizationKind.NOBLE,
    "business": OrganizationKind.BUSINESS,
    "guild": OrganizationKind.GUILD,
    "gang": OrganizationKind.GANG,
    "secret_society": OrganizationKind.SECRET_SOCIETY,
    "commoner_family": OrganizationKind.COMMONER_FAMILY,
    # covenant/devotional/other are new — no legacy rows existed.
}
