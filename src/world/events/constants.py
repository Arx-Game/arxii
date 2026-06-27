from django.db import models


class EventStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SCHEDULED = "scheduled", "Scheduled"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class InvitationTargetType(models.TextChoices):
    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
    SOCIETY = "society", "Society"


class InvitationResponse(models.TextChoices):
    """An invitee's RSVP to a persona-targeted event invitation.

    Group (org/society) invitations have no per-member response row — only
    PERSONA invitations carry an RSVP. PENDING is the default until the invitee
    responds; the host can then distinguish a real DECLINE from mere silence.
    """

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"


# Player-facing RSVP verbs (the short ``accept`` / ``decline`` input forms the
# telnet command and the web ``respond`` endpoint accept) → InvitationResponse.
# Distinct from the enum *values* ("accepted"/"declined") so the verbs stay a
# stable player surface even if the stored value changes.
RSVP_VERB_TO_RESPONSE: dict[str, str] = {
    "accept": InvitationResponse.ACCEPTED,
    "decline": InvitationResponse.DECLINED,
}
