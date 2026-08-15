"""Constants for the ceremonies framework (#2289)."""

from django.db import models


class CeremonyStatus(models.TextChoices):
    OPEN = "open", "Open"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"


class CeremonyTypeKey(models.TextChoices):
    """Handler discriminator for ceremony types.

    FUNERAL carries the full handler (dead honorees, ghost container, will seam);
    BLESSING and SERMON are renown/resonance-only. SEANCE (#2393) carries the third
    ghost container plus a consent-gated voice/puppet grant for its honorees.
    WEDDING (#2358/#2999) solemnizes an active Betrothal on finish. CONVERSION
    (#2361) repoints the convert's public WorshipDeclaration on finish — either a
    consent-gated PC-officiated rite (WorshipConversionOffer, mirrors the Seance
    offer) or a self-officiated solo rite (officiant IS the honoree, no offer
    needed). Coronation arrives as a new key + handler later.
    """

    FUNERAL = "funeral", "Funeral"
    BLESSING = "blessing", "Blessing"
    SERMON = "sermon", "Sermon"
    SEANCE = "seance", "Seance"
    WEDDING = "wedding", "Wedding"
    CONVERSION = "conversion", "Conversion"


class SeanceOfferStatus(models.TextChoices):
    """Answer state of a SeanceManifestationOffer (#2393)."""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"


class ConversionOfferStatus(models.TextChoices):
    """Answer state of a WorshipConversionOffer (#2361). Mirrors SeanceOfferStatus."""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
