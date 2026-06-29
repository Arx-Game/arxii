"""Service functions for authoring Character Secrets (#1334).

Slice 1 covers authoring (the content surface). The held/partial-knowledge record, the
clue-target discovery wiring, evidence-as-sharing, and the action-anchored minting (blackmail/
murder/affair/crime → Secret + Evidence) are later slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.secrets.constants import (
    DEFAULT_VICTIM_SEVERITY_BY_LEVEL,
    SecretLevel,
    SecretProvenance,
)
from world.secrets.models import Secret, SecretKnowledge

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.relationships.models import GrievanceOption, RelationshipCapstone, RelationshipTrack
    from world.roster.models import RosterEntry
    from world.scenes.models import Persona
    from world.secrets.models import SecretCategory
    from world.societies.models import Society


class SecretError(Exception):
    """A secret could not be authored as requested (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


def author_secret(  # noqa: PLR0913 — keyword-only; each arg is a distinct secret field
    *,
    subject_sheet: CharacterSheet,
    provenance: str,
    level: int = SecretLevel.UNCOMMON_KNOWLEDGE,
    content: str = "",
    category: SecretCategory | None = None,
    consequences: str = "",
    author_persona: Persona | None = None,
) -> Secret:
    """Author a secret about ``subject_sheet``, enforcing the anchor-scales-with-level rule.

    Raises ``SecretError`` if the request violates the invariant (e.g. a player-flavor secret
    above Level 1). The model's ``clean`` is the single source of truth for that rule; this
    surface just translates its ``ValidationError`` into a typed, user-facing error.
    """
    secret = Secret(
        subject_sheet=subject_sheet,
        provenance=provenance,
        level=level,
        content=content,
        category=category,
        consequences=consequences,
        author_persona=author_persona,
    )
    try:
        secret.full_clean()
    except ValidationError as exc:
        msg = "; ".join(exc.messages)
        raise SecretError(msg, user_message=msg) from exc
    secret.save()
    return secret


def author_player_flavor_secret(
    *,
    subject_sheet: CharacterSheet,
    author_persona: Persona,
    content: str,
    category: SecretCategory | None = None,
) -> Secret:
    """Author a Level-1 player-flavor secret (the only tier a player may free-write).

    Capped at Level 1 by construction — flavor has no mechanical effect, so its truth is moot
    and it can never be mistaken for canon (the OOC author attribution rides on
    ``author_persona``).
    """
    return author_secret(
        subject_sheet=subject_sheet,
        provenance=SecretProvenance.PLAYER_FLAVOR,
        level=SecretLevel.UNCOMMON_KNOWLEDGE,
        content=content,
        category=category,
        author_persona=author_persona,
    )


def grant_secret_knowledge(
    *,
    roster_entry: RosterEntry,
    secret: Secret,
    knows_category: bool = False,
    knows_consequences: bool = False,
) -> SecretKnowledge:
    """Record that a character knows a secret, unlocking the given layers (idempotent).

    Holding the row is the **fact** layer; ``knows_category`` / ``knows_consequences`` unlock the
    extra layers. Monotonic — re-granting only ever unlocks more, never re-hides. This is the
    single entry point discovery surfaces (clue acquisition, evidence-sharing, GM grant) call.
    """
    held, created = SecretKnowledge.objects.get_or_create(roster_entry=roster_entry, secret=secret)
    updates: list[str] = []
    if knows_category and not held.knows_category:
        held.knows_category = True
        updates.append("knows_category")
    if knows_consequences and not held.knows_consequences:
        held.knows_consequences = True
        updates.append("knows_consequences")
    if updates:
        held.save(update_fields=updates)
    if created:
        # First time this character learns the fact — if they are the *victim* of it and a
        # player runs them, prompt them so they can decide a relationship effect (#1429).
        _notify_secret_victim_on_learn(secret, roster_entry)
    return held


# Authored by Dan (2026-06-23) — the framing line shown after the now-known secret's text. (Not
# PLACEHOLDER: dictated wording.) The telnet "+grievance" pointer is telnet-specific; the web
# routes to the grievance widget instead — see the bridge note (FE follow-up).
_VICTIM_LEARN_PROMPT = (
    "A now public secret implies you have been wronged. "
    "If you would like to respond, use +grievance"
)


def _notify_secret_victim_on_learn(secret: Secret, roster_entry: RosterEntry) -> None:
    """Notify a learner who is this secret's victim, so they may register a grudge (#1429).

    The persona-victim *effect* is **decided by the victim**, never auto-applied: the
    relationship system is consent-gated and player-driven, so we only *prompt* — the victim then
    uses the normal relationship flow toward the perpetrator at their discretion. Fires only when
    the learner is a registered ``SecretVictim`` of this secret **and** the character is run by an
    account (``get_account_for_character``); NPC victims have no one to decide, so nothing fires.
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415
    from world.roster.selectors import get_account_for_character  # noqa: PLC0415
    from world.secrets.models import SecretVictim  # noqa: PLC0415

    sheet = roster_entry.character_sheet
    is_victim = SecretVictim.objects.filter(secret=secret, persona__character_sheet=sheet).exists()
    if not is_victim or get_account_for_character(sheet.character) is None:
        return
    # Send the now-known secret's own text, then the prompt to respond.
    body = f"{secret.content}\n\n{_VICTIM_LEARN_PROMPT}" if secret.content else _VICTIM_LEARN_PROMPT
    send_narrative_message(recipients=[sheet], body=body, category=NarrativeCategory.SYSTEM)


def secret_known_to(secret: Secret, roster_entry: RosterEntry) -> bool:
    """Whether this character already holds the fact of this secret (#1334)."""
    return SecretKnowledge.objects.filter(secret=secret, roster_entry=roster_entry).exists()


def register_secret_grievance(  # noqa: PLR0913 — keyword-only; each arg is a distinct field
    *,
    roster_entry: RosterEntry,
    secret: Secret,
    option: GrievanceOption | None = None,
    custom_points: int | None = None,
    custom_track: RelationshipTrack | None = None,
    writeup: str = "",
) -> RelationshipCapstone:
    """A secret's victim registers a grievance against its subject (#1429).

    The shared seam both the web endpoint and the telnet ``+grievance`` command call. The viewing
    character must be a registered ``SecretVictim`` of ``secret`` **and** already hold the fact —
    you can't grudge a wrong you haven't learned. Source is the victim's sheet, target the secret's
    subject (the perpetrator); the chosen swing is applied via ``relationships.register_grievance``.
    Raises ``SecretError`` if the caller isn't an entitled victim.
    """
    from world.relationships.services import register_grievance  # noqa: PLC0415 — avoid cycle
    from world.secrets.models import SecretGrievance, SecretVictim  # noqa: PLC0415

    sheet = roster_entry.character_sheet
    is_victim = SecretVictim.objects.filter(secret=secret, persona__character_sheet=sheet).exists()
    if not is_victim:
        msg = "You are not a wronged party to this secret."
        raise SecretError(msg, user_message=msg)
    if not secret_known_to(secret, roster_entry):
        msg = "You have not learned this secret."
        raise SecretError(msg, user_message=msg)
    # One grievance per secret per victim — answering is a one-time choice; no stacking grudges.
    if SecretGrievance.objects.filter(secret=secret, victim_sheet=sheet).exists():
        msg = "You have already answered this secret."
        raise SecretError(msg, user_message=msg)
    capstone = register_grievance(
        source=sheet,
        target=secret.subject_sheet,
        option=option,
        custom_points=custom_points,
        custom_track=custom_track,
        writeup=writeup,
    )
    SecretGrievance.objects.create(secret=secret, victim_sheet=sheet, capstone=capstone)
    return capstone


# --- Reputation bridge (#1429) ------------------------------------------------------------


@dataclass(frozen=True)
class SecretExposureResult:
    """What a secret's exposure did to reputation (#1429).

    ``society_reputation_deltas`` is the **diffuse** channel (archetype · each society's
    principles); ``organization_victim_deltas`` is the **relational** channel (direct hits to
    victim orgs, independent of their philosophy). ``notified_persona_victim_ids`` are PC victims
    who, on the secret going public, were granted the knowledge and prompted to decide a
    relationship effect of their own (never auto-applied — the relationship flow is player-driven).
    """

    newly_exposed_society_ids: tuple[int, ...] = ()
    society_reputation_deltas: dict[int, int] = field(default_factory=dict)
    organization_victim_deltas: dict[int, int] = field(default_factory=dict)
    notified_persona_victim_ids: tuple[int, ...] = ()


def _apply_relational_exposure(
    secret: Secret, persona: Persona
) -> tuple[dict[int, int], list[int]]:
    """Apply the first-exposure **relational** channel (direct victim hits) (#1429).

    Returns ``(organization_victim_deltas, notified_persona_victim_ids)``. Organization victims
    take an ``OrganizationReputation`` delta independent of philosophy; persona victims are granted
    the knowledge (prompting a player-driven relationship decision) and recorded. Helper for
    ``expose_secret`` — only called on the first exposure of a secret.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415 — cross-app, avoid cycle at load
    from world.societies.renown import (  # noqa: PLC0415 — cross-app, avoid import cycle at load
        bump_organization_reputation,
    )

    org_deltas: dict[int, int] = {}
    notified_persona_ids: list[int] = []
    default_severity = DEFAULT_VICTIM_SEVERITY_BY_LEVEL.get(secret.level, 0)
    for victim in secret.victims.select_related("organization", "persona__character_sheet"):
        if victim.organization_id:
            severity = victim.severity if victim.severity is not None else default_severity
            new_value = bump_organization_reputation(persona, victim.organization, -severity)
            if new_value is not None:
                org_deltas[victim.organization_id] = new_value
        elif victim.persona_id:
            # Going public reaches the victim too: grant a PC victim the knowledge, which
            # prompts them (via grant_secret_knowledge) to decide a relationship effect.
            victim_entry = RosterEntry.objects.filter(
                character_sheet=victim.persona.character_sheet
            ).first()
            if victim_entry is not None:
                grant_secret_knowledge(roster_entry=victim_entry, secret=secret)
                notified_persona_ids.append(victim.persona_id)
    return org_deltas, notified_persona_ids


def expose_secret(secret: Secret, *, societies: Iterable[Society]) -> SecretExposureResult:
    """Fire the reputation consequences of a secret becoming known to ``societies`` (#1429).

    The reveal→reputation bridge. A secret is just an unrevealed fact; exposing it to a society
    feeds the existing renown engine:

    - **Diffuse channel** — each newly-exposed society reads the secret's ``archetypes`` through
      its own principles (so an ambition-prizing society and a pious one net opposite signs).
      Fired one-shot per society via ``societies_exposed`` (re-exposure never double-fires).
    - **Relational channel** — on the *first* exposure, each victim takes a direct hit
      **independent of their philosophy**: organization victims get an ``OrganizationReputation``
      delta (``severity`` or, if null, the level default); persona victims are recorded only
      (their personal-grudge effect is deferred — see ``SecretVictim``).

    Reputation is attributed to the subject's primary persona (only established/primary identities
    accrue reputation, enforced downstream). Idempotent across re-exposure.
    """
    from world.societies.renown import (  # noqa: PLC0415 — cross-app, avoid import cycle at load
        apply_archetype_society_reputation,
    )

    persona = secret.subject_sheet.primary_persona
    already_exposed = set(secret.societies_exposed.values_list("pk", flat=True))
    newly = [society for society in societies if society.pk not in already_exposed]
    first_exposure = not already_exposed and bool(newly)

    society_deltas: dict[int, int] = {}
    if newly:
        secret.societies_exposed.add(*newly)
        society_deltas = apply_archetype_society_reputation(persona, newly, secret.archetypes.all())

    org_deltas: dict[int, int] = {}
    notified_persona_ids: list[int] = []
    if first_exposure:
        org_deltas, notified_persona_ids = _apply_relational_exposure(secret, persona)

    return SecretExposureResult(
        newly_exposed_society_ids=tuple(society.pk for society in newly),
        society_reputation_deltas=society_deltas,
        organization_victim_deltas=org_deltas,
        notified_persona_victim_ids=tuple(notified_persona_ids),
    )


# --- Listing (shared by the web viewset + the telnet +secrets command) -------------------
# Sort keys, mapped to ordering tuples. Same keys for both shelves; the field paths differ
# because "your own" lists Secret rows and "known about others" lists SecretKnowledge rows.
_OWN_SORTS: dict[str, tuple[str, ...]] = {
    "level": ("-level", "-created_date"),
    "recent": ("-created_date",),
    "category": ("category__name", "-level"),
}
_KNOWN_SORTS: dict[str, tuple[str, ...]] = {
    "level": ("-secret__level", "-found_at"),
    "recent": ("-found_at",),
    "category": ("secret__category__name", "-secret__level"),
    "subject": ("secret__subject_sheet__character__db_key", "-secret__level"),
}
SECRET_SORT_KEYS: tuple[str, ...] = tuple(_KNOWN_SORTS)


def secrets_owned_by(sheet: CharacterSheet, *, sort: str = "level") -> QuerySet[Secret]:
    """The secrets a character **owns** — its own shelf (#1334).

    Single-owner: ``subject_sheet`` is the sole owner, and the owner knows their own secrets in
    full (no Unknown layers). ``sort`` is one of ``_OWN_SORTS`` (defaults to most-dangerous-first).
    """
    order = _OWN_SORTS.get(sort, _OWN_SORTS["level"])
    return (
        Secret.objects.filter(subject_sheet=sheet)
        .select_related("category", "author_persona")
        .order_by(*order)
    )


def known_secrets_for(
    roster_entry: RosterEntry,
    *,
    subject_sheet: CharacterSheet | None = None,
    sort: str = "recent",
) -> QuerySet[SecretKnowledge]:
    """The secrets a character has **learned about others** — held records (#1334).

    Optionally scoped to one ``subject_sheet`` (a single person's tab). Partial-knowledge layers
    stay locked per the held row; the serializer/command renders locked layers as "Unknown".
    Query-free downstream: pulls the subject name + category + author. ``sort`` ∈ ``_KNOWN_SORTS``.
    """
    qs = SecretKnowledge.objects.filter(roster_entry=roster_entry).select_related(
        "secret",
        "secret__category",
        "secret__author_persona",
        "secret__subject_sheet__character",
    )
    if subject_sheet is not None:
        qs = qs.filter(secret__subject_sheet=subject_sheet)
    order = _KNOWN_SORTS.get(sort, _KNOWN_SORTS["recent"])
    return qs.order_by(*order)
