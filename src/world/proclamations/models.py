"""Proclamations & stances: philosophy-vector public statements (#2842).

Characters issue public proclamations aligned to authored stance archetypes.
The stance's six-axis principle vector dot-products against each society's
principles to produce asymmetric reputation deltas — aligned societies warm,
opposed societies are provoked — scaled by the check outcome tier.

Domain edicts ride proclamations: an ``EdictKind`` carries an inherent stance
(the social bill) plus a mechanical payload (income pct, unrest, upkeep) that
applies while a ``DomainEdict`` is active on a domain.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.societies.models import principle_validators


class StanceArchetype(NaturalKeyMixin, SharedMemoryModel):
    """An authored public position on the six principle axes.

    Sibling of ``PhilosophicalArchetype``: same field shape (six
    ``{axis}_delta`` fields, ±5 range) so the existing dot-product
    arithmetic works on it. Where ``PhilosophicalArchetype`` judges *deeds*,
    ``StanceArchetype`` labels *declared positions* — "Defense of the Old
    Ways", "Mercy for the Fallen", "The Strong Hand". Vocabularies grow
    independently; a stance is never also a deed-judgment archetype.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    mercy_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Compassion (+) ↔ Ruthlessness (-) axis contribution.",
    )
    method_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Honor (+) ↔ Cunning (-) axis contribution.",
    )
    status_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Humility (+) ↔ Ambition (-) axis contribution.",
    )
    change_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Progress (+) ↔ Tradition (-) axis contribution.",
    )
    allegiance_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Independence (+) ↔ Loyalty (-) axis contribution.",
    )
    power_delta = models.IntegerField(
        default=0,
        validators=principle_validators,
        help_text="Equality (+) ↔ Hierarchy (-) axis contribution.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class Proclamation(SharedMemoryModel):
    """A public statement issued by a persona, optionally on behalf of an org.

    The ``stance`` carries the six-axis principle vector that drives reputation
    deltas. ``prose`` is displayed verbatim on the public feed — it is never
    parsed by any mechanic (ADR-0178: vectors-not-prose). ``check_outcome``
    stores the CheckOutcome name from the oratory/persuasion roll so the tier
    can be referenced later without re-rolling.
    """

    issuer = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="proclamations",
    )
    org = models.ForeignKey(
        "societies.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="proclamations",
        help_text="Optional: speaking on behalf of this organization.",
    )
    stance = models.ForeignKey(
        StanceArchetype,
        on_delete=models.PROTECT,
        related_name="proclamations",
    )
    prose = models.TextField(
        blank=True,
        help_text="Player-authored text shown verbatim on the feed, never parsed.",
    )
    check_outcome = models.CharField(
        max_length=50,
        blank=True,
        help_text="Stored CheckOutcome name from the issue roll.",
    )
    issued_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self) -> str:
        return f"{self.issuer} proclaims {self.stance}"


class EdictKind(NaturalKeyMixin, SharedMemoryModel):
    """A catalog of domain edicts — the mechanical payload behind a proclamation.

    Each kind carries an inherent ``stance`` (the social bill) plus payload
    columns that apply while active: ``income_gross_pct`` scales the domain's
    gross income in ``accrue_income_stream``; ``weekly_unrest_delta`` and
    ``weekly_upkeep_coppers`` apply in the weekly rollover. Military knobs are
    deferred until positional troop state exists.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    stance = models.ForeignKey(
        StanceArchetype,
        on_delete=models.PROTECT,
        related_name="edict_kinds",
    )
    income_gross_pct = models.IntegerField(
        default=0,
        help_text="Percentage adjustment to domain gross income while active.",
    )
    weekly_unrest_delta = models.IntegerField(
        default=0,
        help_text="Weekly unrest change applied while this edict is active.",
    )
    weekly_upkeep_coppers = models.IntegerField(
        default=0,
        help_text="Additional weekly upkeep in coppers while this edict is active.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class DomainEdict(SharedMemoryModel):
    """An active or revoked edict on a domain.

    One active edict per domain — enacting replaces the current active edict
    (revoking the old one). The ``proclamation`` records the social bill (the
    roll + stance that justified it). Revocable; a revoked edict is history.
    """

    domain = models.ForeignKey(
        "societies.Domain",
        on_delete=models.CASCADE,
        related_name="edicts",
    )
    kind = models.ForeignKey(
        EdictKind,
        on_delete=models.PROTECT,
        related_name="domain_edicts",
    )
    proclamation = models.ForeignKey(
        Proclamation,
        on_delete=models.CASCADE,
        related_name="edicts",
    )
    enacted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-enacted_at"]

    @property
    def is_active(self) -> bool:
        """True when this edict has not been revoked."""
        return self.revoked_at is None

    def __str__(self) -> str:
        status = "active" if self.is_active else "revoked"
        return f"{self.kind} ({status}) on {self.domain}"
