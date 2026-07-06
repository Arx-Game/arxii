"""ORGANIZATION_CAPABILITY project kind — resolver + details model.

When a project of this kind completes, it creates an OrganizationGiftGrant
linking the org to the project's gift, with the project's anchor_cap.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.projects.models import Project


class OrganizationCapabilityProjectDetails(SharedMemoryModel):
    """Per-kind details for ORGANIZATION_CAPABILITY projects.

    Carries the gift to grant, the anchor cap, and the commissioning org.
    """

    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name="org_capability_details",
    )
    gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        related_name="capability_project_details",
    )
    anchor_cap = models.PositiveSmallIntegerField(
        help_text="Ceiling on thread level for this capability.",
    )
    organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="capability_projects",
    )

    def __str__(self) -> str:
        return f"OrgCapability: {self.organization.name} → {self.gift.name}"


def resolve_organization_capability(project: Project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Project resolver: create the OrganizationGiftGrant on completion.

    Idempotent — if the grant already exists (e.g. project re-resolved),
    does nothing.
    """
    from world.societies.models import OrganizationGiftGrant  # noqa: PLC0415

    details = project.org_capability_details
    OrganizationGiftGrant.objects.get_or_create(
        organization=details.organization,
        gift=details.gift,
        defaults={
            "project": project,
            "anchor_cap": details.anchor_cap,
        },
    )
