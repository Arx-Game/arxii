"""Idempotent role + offer seeding helpers.

These functions live here (not in a committed fixture) per repo discipline:
fixtures are gitignored and reserved for data seeding via admin/shared
storage, not version-controlled bootstraps (see #683). Tests use these
helpers directly from setUp; staff tooling will eventually call them too.

The Builders Guild Clerk is the first concrete `NPCRole` and ships with a
small menu of permit-issuance offers. Plan 3 (#668) wires the real
PermitOfferDetails fields + ward eligibility rules; Plan 2 ships the
offers with empty eligibility_rule so the framework is end-to-end
testable today.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    PermitOfferDetails,
    TrainOfferDetails,
)

if TYPE_CHECKING:
    from world.achievements.models import Achievement
    from world.buildings.models import BuildingKind
    from world.magic.models import Technique

BUILDERS_GUILD_CLERK_ROLE_NAME = "Builders Guild Clerk"


_CLERK_OFFER_LABELS: frozenset[str] = frozenset(
    {
        "Apply for a Cottage permit",
        "Apply for a House permit",
        "Apply for a Tavern permit",
        "Apply for a Shop permit",
        "Apply for a Workshop permit",
        "Apply for a Guild Hall permit",
        "Apply for a Warehouse permit",
        "Negotiate a discount on permit fees",
        "Request expedited processing",
    }
)


def ensure_builders_guild_clerk_role() -> NPCRole:
    """Get-or-create the Builders Guild Clerk role + its permit offers.

    Idempotent. Safe to call from test setUp, app startup, or staff
    tooling. Each PERMIT offer is explicitly wired to a BuildingKind
    via ``PermitOfferDetails.building_kind``. Old-label offers from
    prior seed versions are cleaned up on each invocation.
    """
    from world.buildings.models import BuildingKind  # noqa: PLC0415
    from world.buildings.seeds import (  # noqa: PLC0415
        ensure_house_kind,
        ensure_urban_building_kinds,
    )

    ensure_urban_building_kinds()
    ensure_house_kind()

    role, _ = NPCRole.objects.get_or_create(
        name=BUILDERS_GUILD_CLERK_ROLE_NAME,
        defaults={
            "description": (
                "Issues building permits on behalf of the Builders Guild. "
                "Manages ward-level eligibility and negotiated permit terms."
            ),
            "default_description_template": (
                "A clerk of the Builders Guild sits behind a worn oak desk, "
                "ledgers stacked in tidy columns."
            ),
            "default_rapport_starting_value": 0,
        },
    )

    # Idempotent cleanup: delete any offers on this role whose labels
    # are not in the current expected set (handles migration from old
    # seed labels like "Apply for a small residential permit").
    NPCServiceOffer.objects.filter(role=role).exclude(label__in=_CLERK_OFFER_LABELS).delete()

    _ensure_offer(
        role=role,
        label="Apply for a Cottage permit",
        building_kind=BuildingKind.objects.get(name="Cottage"),
        max_target_size=2,
    )
    _ensure_offer(
        role=role,
        label="Apply for a House permit",
        building_kind=BuildingKind.objects.get(name="House"),
        max_target_size=3,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Tavern permit",
        building_kind=BuildingKind.objects.get(name="Tavern"),
        max_target_size=5,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Shop permit",
        building_kind=BuildingKind.objects.get(name="Shop"),
        max_target_size=4,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Workshop permit",
        building_kind=BuildingKind.objects.get(name="Workshop"),
        max_target_size=4,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Guild Hall permit",
        building_kind=BuildingKind.objects.get(name="Guild Hall"),
        max_target_size=6,
    )
    _ensure_offer(
        role=role,
        label="Apply for a Warehouse permit",
        building_kind=BuildingKind.objects.get(name="Warehouse"),
        max_target_size=5,
    )
    _ensure_offer(
        role=role,
        label="Negotiate a discount on permit fees",
        rapport_requirement=5,
        is_final=False,
        rapport_delta_success=2,
        rapport_delta_failure=-3,
    )
    _ensure_offer(
        role=role,
        label="Request expedited processing",
        rapport_requirement=10,
    )
    return role


def _ensure_offer(
    role: NPCRole,
    label: str,
    *,
    building_kind: BuildingKind | None = None,
    max_target_size: int | None = None,
    **overrides: object,
) -> NPCServiceOffer:
    """Inner helper: idempotent (role, label)-keyed offer + details row.

    ``overrides`` accepts any NPCServiceOffer field (rapport_requirement,
    is_final, rapport_delta_success/failure, etc.). Defaults to a final
    PERMIT MENU offer with zero rapport requirement and zero deltas.

    When ``building_kind`` is provided, it is set on the offer's
    ``PermitOfferDetails`` row at creation time. When ``max_target_size``
    is provided, it overrides the default (10) on the details row.
    """
    defaults: dict[str, object] = {
        "kind": OfferKind.PERMIT,
        "draw_mode": DrawMode.MENU,
        "eligibility_rule": {},  # Plan 3 fills in ward-permit predicates.
        "rapport_requirement": 0,
        "is_final": True,
        "rapport_delta_success": 0,
        "rapport_delta_failure": 0,
    }
    defaults.update(overrides)
    offer, created = NPCServiceOffer.objects.get_or_create(
        role=role, label=label, defaults=defaults
    )
    if created:
        details_defaults: dict[str, object] = {}
        if building_kind is not None:
            details_defaults["building_kind"] = building_kind
        if max_target_size is not None:
            details_defaults["default_max_target_size"] = max_target_size
        PermitOfferDetails.objects.create(offer=offer, **details_defaults)
    return offer


# --- Great Archive self-study (#2440 ruling 5) ------------------------------

GREAT_ARCHIVE_LIBRARIAN_ROLE_NAME = "Great Archive Librarian"

#: PLACEHOLDER quest-completion flag gating Archive self-study TRAIN offers.
#: The real quest ("a short/easy low-level quest") is lore-repo authored
#: content (#2440 ruling 5, "Out of scope" section) — this seed ships only
#: the Achievement row the quest grants and the gate that reads it, mirroring
#: the ``discovery_achievement`` pattern (``world.achievements.models.
#: DiscoverableContent``) the closest other content in the repo uses to gate
#: on "has this character earned X".
GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG = "great-archive-self-study"

#: One representative (gift_name, technique_name) pair per starter Gift (the
#: "attack" row of the starter Gift/Technique catalog — real lore-repo content,
#: loaded via ``load_world_content()``; formerly a synthetic 5x5 grid seeded
#: in-repo by the now-retired ``seed_starter_gift_catalog()``, #2474) — a
#: small, symmetric self-study sample so the TRAIN-offer-gated-by-achievement
#: substrate is walkable on a fresh DB. Real Archive curriculum content
#: (which/how many techniques) is a lore-repo authoring pass (#2440's spec,
#: "Out of scope" — "trainer NPC content"); staff/content can add or replace
#: offers freely, this seed never overwrites a staff-adjusted row
#: (get_or_create) and only prunes labels it itself minted.
#:
#: Paired with its Gift (not a bare technique-name tuple) per #2474 review
#: fix: ``Technique.name`` is NOT globally unique (only ``(gift, name)`` is,
#: per ``unique_technique_gift_name``) — lore reuse or a player-crafted
#: technique (``Technique.creator``) could share one of these names on a
#: DIFFERENT gift, and an unscoped ``name__in=`` lookup would silently pick
#: whichever row the DB happened to return, mis-wiring
#: ``TrainOfferDetails.technique`` to the wrong gift's technique.
_SELF_STUDY_STARTER_TECHNIQUES: tuple[tuple[str, str], ...] = (
    ("Emberwork", "Burning Strike"),
    ("Shadowcraft", "Shadow Blade"),
    ("Resonant Chorus", "Shattering Chorus"),
    ("Sacred Communion", "Smiting Light"),
    ("Glyphwork", "Force Sigil"),
)


def _resolve_starter_techniques(pairs: tuple[tuple[str, str], ...]) -> dict[str, Technique]:
    """Look up starter Techniques by (gift_name, technique_name) pair (#2474).

    The starter Gift/Technique catalog is real lore-repo content, loaded via
    ``core_management.content_fixtures.load_world_content()`` — this seed no
    longer authors it (the retired ``seed_starter_gift_catalog()`` used to).

    Each pair is resolved with its Gift scoping the lookup
    (``gift__name=gift_name, name=technique_name``) rather than a bare
    ``name__in=`` filter — ``Technique.name`` is not globally unique, so an
    unscoped lookup could silently alias onto a same-named technique on a
    different gift (lore reuse, or a player-crafted row via
    ``Technique.creator``) and mis-wire ``TrainOfferDetails.technique``.

    Raises ``ContentError`` (Decision 5 on #2474: content-dependent seeding
    fails loudly, no silent skips) when NONE of ``pairs`` resolve — that means
    the content repo hasn't been loaded. Every ``seed_dev_database()`` test in
    the repo that reaches this code path seeds its stub content root with the
    real starter catalog (``world.seeds.tests.content_stub.stub_content_root``)
    precisely so this raise is never hit outside a genuinely missing content
    repo. Individual missing pairs (a partially-loaded or edited catalog) are
    tolerated by the caller, which skips a pair it can't find.
    """
    from core_management.content_fixtures import ContentError  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415

    techniques: dict[str, Technique] = {}
    for gift_name, technique_name in pairs:
        technique = Technique.objects.filter(gift__name=gift_name, name=technique_name).first()
        if technique is not None:
            techniques[technique_name] = technique
    if not techniques:
        message = (
            f"Starter Gift/Technique catalog not found (no rows matched {pairs!r}). "
            "Content repo not loaded — run the Big Button (seed_dev_database()) / "
            "load_world_content() to load the arx2-lore content repo before seeding NPC "
            "roles that reference starter techniques."
        )
        raise ContentError(message)
    return techniques


def ensure_great_archive_self_study_achievement() -> Achievement:
    """Get-or-create the PLACEHOLDER Achievement gating Archive self-study (#2440).

    Never overwrites a staff-adjusted row (get_or_create). Granting this
    achievement to a character is the lore-repo quest's job, not this seed's —
    this function only ensures the row the quest (and the gate) can point at
    exists on a fresh DB.
    """
    from world.achievements.constants import NotificationLevel  # noqa: PLC0415
    from world.achievements.models import Achievement  # noqa: PLC0415

    achievement, _ = Achievement.objects.get_or_create(
        slug=GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG,
        defaults={
            "name": "Keeper of the Archive",
            "description": (
                "PLACEHOLDER: earned by completing a short introductory quest at "
                "the Great Archive. Unlocks self-study TRAIN offers from the "
                "Archive librarian — the post-Vanishing path for characters whose "
                "tradition has no living trainer (#2440 ruling 5). Real quest "
                "content is a lore-repo authoring pass."
            ),
            "hidden": True,
            "notification_level": NotificationLevel.PERSONAL,
            "is_active": True,
        },
    )
    return achievement


def ensure_great_archive_librarian_role() -> NPCRole:
    """Get-or-create the Great Archive Librarian role + its self-study TRAIN offers (#2440).

    Mirrors ``ensure_builders_guild_clerk_role``'s shape: idempotent
    get-or-create role + offers, with stale-label cleanup on each call.

    Gate mechanism: reuses ``NPCServiceOffer.eligibility_rule`` — already THE
    predicate gate for offer visibility/selectability (``services.
    _is_offer_eligible``) — with the ``has_achievement`` leaf
    (``world.predicates.predicates``), rather than adding a new
    ``required_achievement`` FK. Verified against code first (anti-reinvention):
    ``has_achievement`` is already BUILT & WIRED into every NPCServiceOffer's
    visibility check, so authoring the predicate is the closest existing
    mechanism — a bespoke FK would duplicate it. No migration is needed for
    the gate itself; the level-2 requirement type is this task's only new field.

    Fronted by the Shroudwatch Academy org (``faction_affiliation``) — same as
    every other Academy trainer — so the Hare is redeemed to the Academy
    regardless of self-study, matching ``run_train_offer``'s "Hares are
    Academy-specific venue tokens" ruling. ``teaches_tradition`` is left null:
    self-study teaches the shared (Path x Gift) pool only. Tradition-signature
    self-teaching for orphaned traditions (#2428) would need a role to serve
    every orphaned tradition's signature list simultaneously, which a single
    ``teaches_tradition`` FK can't express — deferred, not this task's scope.
    """
    from world.seeds.character_creation import ensure_shroudwatch_academy  # noqa: PLC0415

    academy = ensure_shroudwatch_academy()
    starter_techniques = _resolve_starter_techniques(_SELF_STUDY_STARTER_TECHNIQUES)
    achievement = ensure_great_archive_self_study_achievement()

    role, _ = NPCRole.objects.get_or_create(
        name=GREAT_ARCHIVE_LIBRARIAN_ROLE_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: the archivist who lets a Prospect who has earned "
                "the Archive's trust teach themselves from its shelves. Real "
                "Great Archive prose/rooms are a lore-repo authoring pass (#2440)."
            ),
            "default_description_template": (
                "A hooded archivist sits amid towering shelves, guarding what the "
                "Academy's living trainers can no longer teach in person."
            ),
            "default_rapport_starting_value": 0,
            "faction_affiliation": academy,
            "teaches_tradition": None,
        },
    )

    eligibility_rule = {"leaf": "has_achievement", "params": {"slug": achievement.slug}}
    expected_labels: set[str] = set()
    for _gift_name, technique_name in _SELF_STUDY_STARTER_TECHNIQUES:
        technique = starter_techniques.get(technique_name)
        if technique is None:
            continue
        label = f"Self-study: {technique.name}"
        expected_labels.add(label)
        offer, _ = NPCServiceOffer.objects.get_or_create(
            role=role,
            label=label,
            defaults={
                "kind": OfferKind.TRAIN,
                "draw_mode": DrawMode.MENU,
                "is_final": True,
                "ap_cost": 0,
                "eligibility_rule": eligibility_rule,
            },
        )
        if offer.eligibility_rule != eligibility_rule:
            offer.eligibility_rule = eligibility_rule
            offer.save(update_fields=["eligibility_rule"])
        TrainOfferDetails.objects.get_or_create(
            offer=offer,
            defaults={"technique": technique, "learn_ap_cost": 5, "gold_cost": 0},
        )

    # Idempotent cleanup mirroring ensure_builders_guild_clerk_role: drop any
    # offers this seed minted under an old label set no longer in current use.
    NPCServiceOffer.objects.filter(role=role, kind=OfferKind.TRAIN).exclude(
        label__in=expected_labels
    ).delete()

    return role


# --- Academy Registrar: settle the entrance debt (#2428 whole-branch fix) --

ACADEMY_REGISTRAR_ROLE_NAME = "Academy Registrar"

_REGISTRAR_SETTLE_OFFER_LABEL = "Settle your Academy debt"


def ensure_academy_registrar_role() -> NPCRole:
    """Get-or-create the Academy Registrar role + its ungated SETTLE_OBLIGATION offer.

    Closes the whole-branch-review Critical finding on #2428:
    ``world.societies.obligation_services.settle_obligation`` was authored (Task 1)
    with no live caller, so an Unbound Prospect had no in-game way to ever pay off
    their Academy entrance debt — the cluster's headline loop dead-ended. This is
    that caller's front door: a class-1 Functionary "bursar" role, fronted by the
    Shroudwatch Academy org (``faction_affiliation``, same convention every other
    Academy role uses), with one ungated offer (no rapport/achievement gate — a
    Prospect who owes the debt should always be able to find someone to pay it to)
    that dispatches ``world.npc_services.effects.run_settle_obligation_offer``.

    PLACEHOLDER description/flavor — real Registrar prose is a lore-repo authoring
    pass, same as every other Academy NPC role seeded here.

    Idempotent (get_or_create + stale-label cleanup), mirroring
    ``ensure_builders_guild_clerk_role``'s shape.
    """
    from world.seeds.character_creation import ensure_shroudwatch_academy  # noqa: PLC0415

    academy = ensure_shroudwatch_academy()

    role, _ = NPCRole.objects.get_or_create(
        name=ACADEMY_REGISTRAR_ROLE_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: keeps the Academy's entrance ledger. Takes a Golden "
                "Hare in hand and marks a Prospect's debt paid. Real Registrar "
                "prose/room is a lore-repo authoring pass (#2428)."
            ),
            "default_description_template": (
                "A bursar sits behind a ledger stand thick with entrance records, "
                "quill ready to strike a debt paid."
            ),
            "default_rapport_starting_value": 0,
            "faction_affiliation": academy,
            "teaches_tradition": None,
        },
    )

    offer, created = NPCServiceOffer.objects.get_or_create(
        role=role,
        label=_REGISTRAR_SETTLE_OFFER_LABEL,
        defaults={
            "kind": OfferKind.SETTLE_OBLIGATION,
            "draw_mode": DrawMode.MENU,
            "eligibility_rule": {},  # Ungated — anyone who owes can pay.
            "is_final": True,
            "ap_cost": 0,
        },
    )
    if not created and offer.kind != OfferKind.SETTLE_OBLIGATION:
        offer.kind = OfferKind.SETTLE_OBLIGATION
        offer.save(update_fields=["kind"])

    # Idempotent cleanup mirroring the other role seeds: drop any offer this
    # seed itself minted under an old label no longer in current use.
    NPCServiceOffer.objects.filter(role=role, kind=OfferKind.SETTLE_OBLIGATION).exclude(
        label=_REGISTRAR_SETTLE_OFFER_LABEL
    ).delete()

    return role


# --- Academy Trainer: ungated generalist (#2428 whole-branch fix) ----------

ACADEMY_GENERALIST_TRAINER_ROLE_NAME = "Academy Trainer"

#: Same one-per-starter-Gift sample as the Great Archive librarian's self-study
#: list (``_SELF_STUDY_STARTER_TECHNIQUES``) — deliberately identical set: both
#: seeds exist to prove the (Path x Gift) pool is reachable, this one just
#: without the achievement gate, so a fresh-DB character can complete their
#: starter pool without first doing the Archive's quest. Real Academy
#: curriculum content is a lore-repo authoring pass (#2440's spec, "Out of
#: scope") — staff/content can add or replace offers freely; this seed never
#: overwrites a staff-adjusted row (get_or_create) and only prunes labels it
#: itself minted.
_GENERALIST_TRAINER_STARTER_TECHNIQUES: tuple[tuple[str, str], ...] = _SELF_STUDY_STARTER_TECHNIQUES


def ensure_academy_generalist_trainer_role() -> NPCRole:
    """Get-or-create the ungated Academy generalist trainer + its TRAIN offers.

    Closes the whole-branch-review Important finding on #2428: without this seed,
    the only fresh-DB TRAIN offers were the Great Archive librarian's
    achievement-gated self-study rows — a brand-new Unbound Prospect had no
    reachable trainer at all until they completed a quest that doesn't exist yet
    outside a PLACEHOLDER Achievement row. This role mirrors
    ``ensure_great_archive_librarian_role``'s shape exactly (same technique
    sample, same TRAIN offer authoring) but with NO ``eligibility_rule`` gate —
    a fresh Prospect can walk up and learn from their own (Path x Gift) starter
    pool immediately. ``teaches_tradition=None``: like the librarian, this trainer
    teaches the shared pool only, not any tradition's signature list (a single
    ``teaches_tradition`` FK can't serve every tradition's signature list at
    once — a per-tradition trainer role is lore-repo content, not this seed's job).

    Fronted by Shroudwatch Academy (``faction_affiliation``) — the Hare a learner
    spends here redeems to the Academy, same as every other Academy TRAIN offer.

    PLACEHOLDER description/flavor. Idempotent (get_or_create + stale-label
    cleanup), mirroring ``ensure_great_archive_librarian_role``.
    """
    from world.seeds.character_creation import ensure_shroudwatch_academy  # noqa: PLC0415

    academy = ensure_shroudwatch_academy()
    starter_techniques = _resolve_starter_techniques(_GENERALIST_TRAINER_STARTER_TECHNIQUES)

    role, _ = NPCRole.objects.get_or_create(
        name=ACADEMY_GENERALIST_TRAINER_ROLE_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: an Academy instructor who teaches any Prospect the "
                "basics of their own Path's starter Gift — no sponsorship, no "
                "quest, just AP, coin, and a Golden Hare. Real Academy trainer "
                "prose/rooms are a lore-repo authoring pass (#2440)."
            ),
            "default_description_template": (
                "An Academy instructor waits by a practice circle, ready to walk "
                "any Prospect through the fundamentals."
            ),
            "default_rapport_starting_value": 0,
            "faction_affiliation": academy,
            "teaches_tradition": None,
        },
    )

    expected_labels: set[str] = set()
    for _gift_name, technique_name in _GENERALIST_TRAINER_STARTER_TECHNIQUES:
        technique = starter_techniques.get(technique_name)
        if technique is None:
            continue
        label = f"Learn: {technique.name}"
        expected_labels.add(label)
        offer, created = NPCServiceOffer.objects.get_or_create(
            role=role,
            label=label,
            defaults={
                "kind": OfferKind.TRAIN,
                "draw_mode": DrawMode.MENU,
                "is_final": True,
                "ap_cost": 0,
                "eligibility_rule": {},  # Ungated.
            },
        )
        if not created and offer.eligibility_rule:
            offer.eligibility_rule = {}
            offer.save(update_fields=["eligibility_rule"])
        TrainOfferDetails.objects.get_or_create(
            offer=offer,
            defaults={"technique": technique, "learn_ap_cost": 5, "gold_cost": 0},
        )

    # Idempotent cleanup mirroring ensure_great_archive_librarian_role.
    NPCServiceOffer.objects.filter(role=role, kind=OfferKind.TRAIN).exclude(
        label__in=expected_labels
    ).delete()

    return role
