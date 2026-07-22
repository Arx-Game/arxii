"""Unified NPC service framework models.

`NPCServiceOffer` is the single offer surface across every kind of "ask NPC
for thing" interaction — permits today; missions, loans, training, favors,
etc. as their per-kind details models + effect handlers register.

`NPCStanding` is the per-(PC persona, NPC persona) durable disposition row,
shared across every kind of NPC service. Relocated here from
`world.missions` (was `MissionGiverStanding`) — missions imports it back for
mission-availability gates.

Per-kind 1:1 details models (e.g., `PermitOfferDetails`) mirror the
`ItemFacet` composition pattern. Plan 3 (#668) fills in the permit-specific
fields + the real effect handler body.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.descriptors import ReverseOneToOneOrNone
from core.managers import ArxSharedMemoryManager
from core.mixins import DiscriminatorMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.npc_services.constants import (
    DrawMode,
    NpcRegardEventReason,
    OfferKind,
    RecordedProfileStatus,
    RegardTargetType,
    SummonsStatus,
)

# Cross-app FK string for the Persona model, referenced by several fields below.
# Centralized to avoid the duplicated-literal SonarCloud smell (python:S1192).
_PERSONA_FK = "scenes.Persona"
_ORG_MODEL_PATH = "societies.Organization"
_NPC_OFFER_DETAILS_HELP_TEXT = "The NPCServiceOffer row this details model decorates."
_REGARD_EVENT_CONFIG_LABEL = "Regard Event Config"


class NPCStanding(SharedMemoryModel):
    """Per-(PC persona, NPC persona) durable disposition.

    Used by every kind of NPC service to gate offers on standing /
    affection. Class-1 nameless functionary interactions do NOT create
    rows; class-2+ named NPCs do. Standing and cooldown are deliberately
    orthogonal — cooldown lives on :class:`OfferCooldown` (per-offer per-
    persona) so it works for every offer kind, not just NPC-rooted ones.
    """

    persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="npc_standings",
        help_text="The PC's persona that holds this standing.",
    )
    npc_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="standings_held_by",
        help_text="The NPC's persona the standing is with.",
    )
    affection = models.IntegerField(
        default=0,
        help_text=(
            "Per-persona-pair standing / affection. Predicate gate "
            "`min_npc_standing` reads this. Negative values mean disliked. "
            "Movement mechanic (flirt/seduce/cultivation checks) is adjacent "
            "gameplay work that mutates this value; the model just carries it."
        ),
    )
    last_interaction_summary = models.TextField(
        blank=True,
        help_text=(
            "Free-text summary of the last interaction; used by both mission "
            "and functionary contexts to surface 'why we left off where we did'."
        ),
    )
    debt = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Outstanding debt owed to this NPC from over-ceiling emergency draws "
            "(#1718). Generic: any future petition-style NPC feature may reuse this "
            "field, not just Court grant negotiation."
        ),
    )
    debt_baseline_affection = models.IntegerField(
        default=0,
        help_text=(
            "Snapshot of `affection` at the moment `debt` was last incurred. Debt "
            "repays on read as affection grows past this baseline (#1718)."
        ),
    )
    debt_baseline_missions_completed = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Snapshot of the caller-supplied completed-mission count at the moment "
            "`debt` was last incurred. Debt repays on read as that count grows past "
            "this baseline (#1718)."
        ),
    )
    consecutive_failed_petitions = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Consecutive failed/botched petition-style checks against this NPC "
            "(#1718). Increments on failure, resets to 0 on success. Mirrors "
            "`Contract.consecutive_missed` (world.currency)."
        ),
    )
    consecutive_refused_summons = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Consecutive refused/expired summonses from this NPC (#2050). "
            "Increments on decline/expire, resets to 0 on acceptance. Mirrors "
            "`consecutive_failed_petitions` — generic per ADR-0085."
        ),
    )
    last_changed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "npc_persona"],
                name="unique_npcstanding_persona_npc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona} ↔ {self.npc_persona} (affection={self.affection})"


class NPCRole(NaturalKeyMixin, SharedMemoryModel):
    """A kind of NPC role — a bundle of `NPCServiceOffer` rows.

    One role can be instantiated across the world as multiple class-1 NPCs
    (every Builders Guild Clerk in every guild hall) or attached to a
    specific class-2+ named NPC. Offers are authored on the role; per-NPC
    overrides are a follow-up.

    Carries `NaturalKeyMixin` (#2266 review fix) so the content pipeline's
    emitted fixture JSON (natural-key format, no "pk" key) resolves an
    existing same-name row on `loaddata` instead of blind-INSERTing into it
    and raising `IntegrityError` on the unique `name` constraint. Per #946,
    `loaddata` on a `SharedMemoryModel` can INSERT via a natural key but
    cannot UPDATE — the identity map returns the cached instance before the
    new field values land. `core_management.content_fixtures.load_entries`
    (`update_or_create`) remains the only update-safe path; the emitted
    fixture JSON is fresh-DB/insert-or-resolve only.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name; e.g., 'Builders Guild Clerk', 'Town Guard'.",
    )
    description = models.TextField(
        blank=True,
        help_text="Admin-editable flavor; what this role does in the world.",
    )
    default_description_template = models.TextField(
        blank=True,
        help_text=(
            "Fallback flavor description rendered when a class-1 nameless NPC "
            "of this role is presented to the player. Class-2+ NPCs use their "
            "persona's description instead."
        ),
    )
    default_rapport_starting_value = models.IntegerField(
        default=0,
        help_text=(
            "Initial in-interaction rapport for class-1 interactions. "
            "Class-2/3/4 interactions start at `default + NPCStanding.affection`."
        ),
    )
    faction_affiliation = models.ForeignKey(
        _ORG_MODEL_PATH,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npc_roles",
        help_text=(
            "Optional org this role fronts for (e.g., Builders Guild Clerk → "
            "Builders Guild Organization). Used by org-scoped permission filters."
        ),
    )
    teaches_tradition = models.ForeignKey(
        "magic.Tradition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="teaching_npc_roles",
        help_text=(
            "Optional: the Tradition this role's trainer teaches signature "
            "techniques for (#2440). Gates TRAIN-offer signature-technique "
            "availability to learners who belong to the same Tradition "
            "(CharacterTradition membership). Blank = the role only trains "
            "shared (Path × Gift) pool techniques, no tradition signatures."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Master on/off switch for the role (#686). When False, no offer on "
            "this role is eligible in available_offers, regardless of per-offer "
            "state. Staff use this to disable a role without deleting it; "
            "migrated value from the legacy `MissionGiver.is_active`."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class Functionary(SharedMemoryModel):
    """A **class-1** NPC placed in a room — the abstracted, non-piloted anchor for a room's
    gameplay loops: mission-giving, permit approval, mission-reporting, and future services
    (#1766).

    A Functionary is a *placement* of an :class:`NPCRole` in a specific room. Because it has
    no ObjectDB and no ``scenes.Persona`` (those are the class-2 **Standing NPC** / class-3-4
    **Story NPC** rungs), it carries its own ``room`` FK so the world knows where it stands —
    where a player must be to interact with it. One role has many Functionary placements (a
    Builders Guild Clerk in every guild hall). Promotion of a Functionary into a named, owned
    **asset** (class-1 → class-2) is the Asset/Companion system's job (#672); a Functionary is
    the rung-1 base that promotion stands on, and it deliberately carries no owner here.
    """

    role = models.ForeignKey(
        NPCRole,
        on_delete=models.CASCADE,
        related_name="functionaries",
        help_text="The NPC role this placement fronts (its offers, faction, rapport default).",
    )
    room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="functionaries",
        help_text="The room this Functionary serves — where a player must be to interact.",
    )
    name_override = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Optional placement-specific name shown instead of the role name (e.g. "
            "'Old Marta' for a Barkeep role). Blank → the role's name."
        ),
    )
    description_override = models.TextField(
        blank=True,
        help_text=(
            "Optional placement-specific flavor shown instead of the role's "
            "default_description_template. Blank → the role default."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this placement is currently present. False hides it without deleting.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "room"],
                name="unique_functionary_role_room",
            ),
        ]
        verbose_name = "Functionary"
        verbose_name_plural = "Functionaries"

    @property
    def display_name(self) -> str:
        """The name shown to players — the placement override, else the role name."""
        return self.name_override or self.role.name

    def __str__(self) -> str:
        return f"{self.display_name} @ room {self.room_id}"


class NPCServiceOffer(SharedMemoryModel):
    """One offerable thing on an NPC role, of a specific kind.

    The unified offer model. Kind discriminator routes to a per-kind 1:1
    details model (e.g., `PermitOfferDetails`) for kind-specific parameters
    and to a registered effect handler (see `world.npc_services.effects`)
    that produces the downstream object when the offer is granted.

    `eligibility_rule` is THE predicate gate — visibility and selectability
    are the same concept. If the predicate fails, the offer doesn't appear.
    Progressive disclosure happens through how staff author predicates, not
    through a separate visibility layer.
    """

    # Reverse-OneToOne safe accessor (#2386): missing row -> None.
    permit_offer_details_or_none = ReverseOneToOneOrNone("permit_offer_details")

    role = models.ForeignKey(
        NPCRole,
        on_delete=models.CASCADE,
        related_name="offers",
    )
    kind = models.CharField(
        max_length=32,
        choices=OfferKind.choices,
        help_text=(
            "Discriminator: routes to per-kind details model + effect handler "
            "registered in `world.npc_services.effects.OFFER_EFFECT_HANDLERS`."
        ),
    )
    label = models.CharField(
        max_length=200,
        help_text="UI display text for the menu option.",
    )
    draw_mode = models.CharField(
        max_length=8,
        choices=DrawMode.choices,
        default=DrawMode.MENU,
        help_text=(
            "MENU = deterministic option always shown if eligible. POOL = NPC "
            "draws from a pool per visit (mission-style; #686)."
        ),
    )
    eligibility_rule = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Predicate JSON evaluated via `world.missions.predicates.evaluate`. "
            "Empty dict = no gate. Drives both visibility and selectability — "
            "if it fails, the offer doesn't appear in the menu."
        ),
    )
    rapport_requirement = models.IntegerField(
        default=0,
        help_text=(
            "Minimum in-interaction rapport to see/select this option. Separate "
            "from durable eligibility; 0 = no rapport gate."
        ),
    )
    is_final = models.BooleanField(
        default=True,
        help_text=(
            "Final actions resolve + end the interaction. Non-final actions "
            "adjust rapport and re-render the menu (e.g., flattery/negotiation)."
        ),
    )
    rapport_delta_success = models.IntegerField(
        default=0,
        help_text="Rapport delta on success of a non-final check-based action.",
    )
    rapport_delta_failure = models.IntegerField(
        default=0,
        help_text="Rapport delta on failure of a non-final check-based action.",
    )
    cooldown = models.DurationField(
        null=True,
        blank=True,
        help_text=(
            "Per-(offer, persona) throttle applied after a final-action grant. "
            "When set, `OfferCooldown.available_at = now + cooldown` blocks "
            "re-selection until it elapses. Null = no cooldown."
        ),
    )
    ap_cost = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Action points charged to the resolving character before the effect "
            "dispatches (#930 — collection/improvement dispatches cost AP; the "
            "generic knob is available to every kind). 0 = free."
        ),
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Optional: if set, non-final actions roll `perform_check` against "
            "this check type and `check_difficulty`. Success → "
            "`rapport_delta_success`; failure → `rapport_delta_failure`. "
            "Final actions ignore this — the effect IS the payoff."
        ),
    )
    check_difficulty = models.IntegerField(
        default=0,
        help_text=(
            "Target difficulty passed to `perform_check` when `check_type` is "
            "set. Meaningless when `check_type` is null."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "label"],
                name="unique_offer_role_label",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role.name}: {self.label} [{self.kind}]"


class OfferCooldown(SharedMemoryModel):
    """Per-(offer, persona) cooldown row.

    Written by ``services.resolve_offer`` when a final-action grant
    consumes an offer whose ``cooldown`` is set. ``services.available_offers``
    filters offers whose cooldown row has ``available_at > now``.

    Persona-keyed because every PC who can take an offer has a persona;
    cooldown is meaningfully per-PC-per-offer.
    """

    offer = models.ForeignKey(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="cooldowns",
    )
    persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="offer_cooldowns",
    )
    available_at = models.DateTimeField(
        help_text="Earliest time `persona` can select this offer again.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "persona"],
                name="unique_offercooldown_offer_persona",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.offer} cooldown for {self.persona} until {self.available_at:%Y-%m-%d %H:%M}"


class NPCRoleCooldown(SharedMemoryModel):
    """Per-(role, persona) cooldown row (#686).

    Distinct from ``OfferCooldown`` (per-offer): a role-level cooldown blocks
    EVERY offer on the role for the persona until ``available_at``. The MISSION
    effect handler writes both an ``OfferCooldown`` (so the same mission can't
    be immediately re-rolled by the same persona) AND an ``NPCRoleCooldown``
    (so OTHER missions on the role are also gated). Other offer kinds
    (permits, training, favors) typically only write ``OfferCooldown`` — their
    semantics are per-offer, not per-role.

    The duration is sourced per-offer via ``MissionOfferDetails.role_cooldown_duration``
    (defaults to ``MissionTemplate.cooldown``).
    """

    role = models.ForeignKey(
        NPCRole,
        on_delete=models.CASCADE,
        related_name="role_cooldowns",
    )
    persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="role_cooldowns",
    )
    available_at = models.DateTimeField(
        help_text="Earliest time `persona` can take ANY offer on this role again.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "persona"],
                name="unique_rolecooldown_role_persona",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.role.name} cooldown for {self.persona} until {self.available_at:%Y-%m-%d %H:%M}"
        )


class MissionOfferDetails(SharedMemoryModel):
    """Per-kind details for `NPCServiceOffer` rows of kind=MISSION (#686).

    Captures the mission-specific knobs that don't fit on the unified
    ``NPCServiceOffer`` itself: which template this offer wraps, an optional
    per-offer weight override, an additional eligibility predicate
    AND-composed with the offer's own ``eligibility_rule``, and the duration
    written into ``NPCRoleCooldown`` on accept.

    Catalog uniqueness: at most one MissionOfferDetails row per
    ``(NPCServiceOffer.role, mission_template)`` — a role offers any given
    template at most once. **This is a catalog-row constraint, NOT a
    gameplay one-shot.** One template fuels many ``MissionInstance`` rows
    over time; each acceptance spawns a fresh instance with auto-generated
    per-instance details.
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="mission_offer_details",
    )
    # Denormalized mirror of ``offer.role`` so the catalog uniqueness can be
    # enforced as a native DB constraint on ``(role, mission_template)``. The
    # save() override below keeps this in sync from ``offer.role`` on every
    # write; clean() validates it for direct ORM/admin edits.
    role = models.ForeignKey(
        NPCRole,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=(
            "Denormalized from offer.role to enforce (role, mission_template) "
            "catalog uniqueness. Kept in sync via save()."
        ),
    )
    mission_template = models.ForeignKey(
        "missions.MissionTemplate",
        on_delete=models.CASCADE,
        related_name="offer_details",
    )
    source_beat = models.ForeignKey(
        "stories.Beat",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Optional: the staked Beat this offer resolves. When set, accepting "
            "the offer copies it onto MissionInstance.source_beat, arming the "
            "#1770-PR4 stakes gate + contract activation. Independent of "
            "Beat.required_mission (ADR-0010). SET_NULL on Beat delete."
        ),
    )
    target_project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Optional: the live Project this offer's missions advance (#2045). "
            "When set, accepting the offer copies it onto MissionInstance."
            "target_project at issuance — exactly how source_beat works. "
            "SET_NULL on Project delete (a cancelled project unbinds the offer; "
            "issuing then refuses)."
        ),
    )
    weight = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Per-offer weight override for POOL draw. Null falls back to "
            "MissionTemplate.base_weight."
        ),
    )
    requirements_override = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Predicate JSON AND-composed with MissionTemplate.availability_rule "
            "and NPCServiceOffer.eligibility_rule at evaluation time. Empty "
            "dict = no additional gate."
        ),
    )
    role_cooldown_duration = models.DurationField(
        null=True,
        blank=True,
        help_text=(
            "Duration written into NPCRoleCooldown on accept (blocks OTHER "
            "missions on the role for this persona). Null falls back to "
            "MissionTemplate.cooldown."
        ),
    )
    draw_priority = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "POOL-draw priority tier (#726). The highest tier present is drawn "
            "first with guaranteed inclusion (up to the pool count); lower tiers "
            "fill any remaining slots via the weighted draw. Give chain-unlock / "
            "high-stakes follow-up missions a positive value so they surface "
            "ahead of the general pool. 0 = general pool."
        ),
    )

    class Meta:
        verbose_name_plural = "Mission offer details"
        constraints = [
            # Catalog uniqueness per spec AD#6: a role offers any given
            # template at most once. Enforced via the denormalized ``role``
            # FK above; ``save()``/``clean()`` keep that mirror tight.
            models.UniqueConstraint(
                fields=["role", "mission_template"],
                name="unique_mod_role_template",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.offer_id is not None and self.role_id != self.offer.role_id:
            raise ValidationError(
                {"role": "MissionOfferDetails.role must equal offer.role."},
            )

    def save(self, *args: object, **kwargs: object) -> None:
        if self.offer_id is not None:
            # Mirror offer.role onto the denormalized field on every write so
            # the unique-constraint promise holds even when callers forget to
            # set it explicitly.
            self.role_id = self.offer.role_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"MissionOffer: {self.offer.label} → {self.mission_template_id}"


class PermitOfferDetails(SharedMemoryModel):
    """Per-kind details for `NPCServiceOffer` rows of kind=PERMIT.

    Filled in Plan 3 (#668). Defines which BuildingKind this offer
    authorizes, which wards the issued permit defaults to, and the size
    cap. The PERMIT effect handler in ``effects.py`` reads these fields
    to construct the BuildingPermit ItemInstance + BuildingPermitDetails
    row at grant time.
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="permit_offer_details",
        help_text=_NPC_OFFER_DETAILS_HELP_TEXT,
    )
    building_kind = models.ForeignKey(
        "buildings.BuildingKind",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="offered_by",
        help_text=(
            "Which BuildingKind this offer issues permits for. Required "
            "for kind=PERMIT offers in Plan 3 (nullable in the schema so "
            "existing rows can migrate; runtime issuance asserts non-null)."
        ),
    )
    default_approved_wards = models.ManyToManyField(
        "areas.Area",
        related_name="default_permits_offered",
        blank=True,
        help_text=(
            "Default set of wards the issued permit is valid in. Snapshotted "
            "onto BuildingPermitDetails.approved_wards at issuance time."
        ),
    )
    default_max_target_size = models.PositiveSmallIntegerField(
        default=10,
        help_text=(
            "Default cap on ``target_size`` for buildings constructed under "
            "permits from this offer."
        ),
    )
    permit_cost_currency = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Currency cost of the permit (approval fee — distinct from "
            "construction cost). Charged to the PC's account at grant time."
        ),
    )

    def __str__(self) -> str:
        return f"PermitOfferDetails for {self.offer}"


class LoanOfferDetails(SharedMemoryModel):
    """Per-kind details for ``NPCServiceOffer`` rows of kind=LOAN (#930).

    The Blighton-representative loop: a summoned creditor rep offers fixed
    terms; accepting extends a fiat loan (``currency.extend_loan``) to the
    organization whose books the PC keeps. Negotiated terms (charm with
    backfire chances) await the specialized-check foundation — these rows
    are the menu of fixed offers until then.
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="loan_offer_details",
        help_text=_NPC_OFFER_DETAILS_HELP_TEXT,
    )
    principal = models.PositiveBigIntegerField(
        help_text="Coppers lent on acceptance. PLACEHOLDER magnitudes."
    )
    interest_bps_monthly = models.PositiveSmallIntegerField(
        default=50,
        help_text="Monthly interest in basis points. PLACEHOLDER magnitudes.",
    )
    creditor_organization = models.ForeignKey(
        _ORG_MODEL_PATH,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="loan_offers",
        help_text=(
            "The lender. Blank falls back to the role's faction_affiliation "
            "(the org the representative works for)."
        ),
    )

    def __str__(self) -> str:
        return f"LoanOffer: {self.offer.label} ({self.principal} @ {self.interest_bps_monthly}bps)"


class TrainOfferDetails(SharedMemoryModel):
    """Per-kind details for ``NPCServiceOffer`` rows of kind=TRAIN (#2440).

    One offer row per teachable technique — the smallest shape consistent
    with the existing MENU/POOL selection modes: a role's Academy trainer
    authors one TRAIN offer (mirroring how MISSION/PERMIT rows enumerate one
    row per template/kind) for each technique they can teach, and
    ``available_offers``' normal eligibility-rule filtering already handles
    per-learner availability (whether the technique is in that character's
    (Path × Gift) pool or their Tradition's signature list — see
    ``world.npc_services.effects.run_train_offer``). No richer per-offer
    parameterization (a picker of several techniques on one offer) is
    needed: MENU-mode already surfaces every eligible offer as its own menu
    line, one per technique, which reads naturally as "the trainer's
    curriculum."

    ``learn_ap_cost``/``gold_cost`` mirror ``TechniqueTeachingOffer``'s
    fields — the same shared ``charge_and_learn`` seam
    (``world.magic.services.gift_acquisition``) consumes both. Unlike the
    teaching-offer path, TRAIN also always charges exactly one unredeemed
    Golden Hare (``currency.FavorTokenDetails``) issued by the Academy —
    the venue, per the #2428 ruling that Hares are Academy-specific
    regardless of the trainer's own taught Tradition. Deliberately does
    NOT use ``NPCServiceOffer.ap_cost`` (the generic pre-dispatch AP charge
    used by COLLECTION/IMPROVEMENT, applied unconditionally by
    ``services._charge_offer_ap`` before the handler runs) — the
    has-gift/major-gift AP multiplier logic in ``charge_and_learn`` would
    double-charge against that flat knob, so TRAIN offers are authored with
    ``NPCServiceOffer.ap_cost=0`` (``clean()`` below enforces it; see also
    ``world.npc_services.effects.TrainOfferMisconfiguredError``, the
    runtime backstop for authoring paths that skip ``full_clean()``).
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="train_offer_details",
        help_text=_NPC_OFFER_DETAILS_HELP_TEXT,
    )
    technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.PROTECT,
        related_name="train_offers",
        help_text="The technique this trainer teaches on this offer.",
    )
    learn_ap_cost = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Base AP the learner pays to accept, before the has-gift/"
            "major-gift multiplier (mirrors TechniqueTeachingOffer.learn_ap_cost)."
        ),
    )
    gold_cost = models.PositiveIntegerField(
        default=0,
        help_text="Coin charged to the learner's purse, credited to the Academy's treasury.",
    )

    def clean(self) -> None:
        """Reject a nonzero ``offer.ap_cost`` — see the class docstring."""
        if self.offer_id is not None and self.offer.ap_cost != 0:
            msg = (
                "TRAIN offers must author NPCServiceOffer.ap_cost=0 — the AP charge "
                "flows entirely through learn_ap_cost via charge_and_learn; a nonzero "
                "ap_cost would double-charge the learner."
            )
            raise ValidationError({"offer": msg})

    def __str__(self) -> str:
        return f"TrainOffer: {self.offer.label} teaches {self.technique.name}"


REGARD_MIN = -1000
REGARD_MAX = 1000
regard_validators = [MinValueValidator(REGARD_MIN), MaxValueValidator(REGARD_MAX)]


class NpcRegard(DiscriminatorMixin, SharedMemoryModel):
    """A notable NPC's signed opinion of a persona, an Organization, or a Society.

    General opinion axis — positive is favor, negative is hostility. There is
    no separate "enemy" flag; a strongly negative row IS the enemy declaration.
    Deliberately kept separate from NPCStanding (PC-target-only, offer-eligibility
    gating value with different callers) — see ADR-0085.

    Historical rows (``ended_at IS NOT NULL``) are kept as audit trail, mirroring
    ``LocationOwnership``/``CourtPact``. Uses three separate partial-unique
    constraints (one per target column) rather than one compound constraint,
    because Postgres never treats ``NULL = NULL`` as a match — a single
    constraint across all three nullable columns would let duplicates through.
    """

    DISCRIMINATOR_FIELD = "target_type"
    DISCRIMINATOR_MAP = {
        RegardTargetType.PERSONA: "target_persona",
        RegardTargetType.ORGANIZATION: "target_organization",
        RegardTargetType.SOCIETY: "target_society",
    }

    holder_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="regards_held",
        help_text="The notable NPC's persona whose opinion this is.",
    )
    target_type = models.CharField(
        max_length=12,
        choices=RegardTargetType.choices,
        help_text="Selects which target FK (persona, organization, society) is active.",
    )
    target_persona = models.ForeignKey(
        _PERSONA_FK,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="regards_as_target",
        help_text="Any persona (PC or NPC) this opinion is about. Set iff target_type=PERSONA.",
    )
    target_organization = models.ForeignKey(
        _ORG_MODEL_PATH,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="regards_as_target",
        help_text="Set iff target_type=ORGANIZATION.",
    )
    target_society = models.ForeignKey(
        "societies.Society",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="regards_as_target",
        help_text="Set iff target_type=SOCIETY.",
    )
    value = models.IntegerField(
        default=0,
        validators=regard_validators,
        help_text=f"Signed opinion ({REGARD_MIN} to {REGARD_MAX}). Negative = hostile.",
    )
    reason = models.TextField(
        blank=True,
        help_text="Narrative/GM-facing flavor for why this opinion exists.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this opinion was resolved/retracted. NULL = currently active.",
    )

    class Meta:
        verbose_name = "NPC Regard"
        verbose_name_plural = "NPC Regards"
        constraints = [
            models.UniqueConstraint(
                fields=["holder_persona", "target_persona"],
                condition=models.Q(target_persona__isnull=False) & models.Q(ended_at__isnull=True),
                name="unique_active_regard_target_persona",
            ),
            models.UniqueConstraint(
                fields=["holder_persona", "target_organization"],
                condition=(
                    models.Q(target_organization__isnull=False) & models.Q(ended_at__isnull=True)
                ),
                name="unique_active_regard_target_organization",
            ),
            models.UniqueConstraint(
                fields=["holder_persona", "target_society"],
                condition=models.Q(target_society__isnull=False) & models.Q(ended_at__isnull=True),
                name="unique_active_regard_target_society",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.holder_persona} -> {self.get_active_target_name()} ({self.value:+d})"


class CourtGrantOfferDetails(SharedMemoryModel):
    """Per-kind details for ``NPCServiceOffer`` rows of kind=COURT_GRANT (#1718).

    Names which Court covenant this petition offer belongs to — the effect
    handler (``world.npc_services.effects.raise_court_grant``) only receives
    ``(offer, persona)``, so the covenant can't be derived from the session's
    ``npc_persona``; it must be explicit here, same shape as
    ``LoanOfferDetails.creditor_organization``.
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="court_grant_offer_details",
        help_text=_NPC_OFFER_DETAILS_HELP_TEXT,
    )
    covenant = models.ForeignKey(
        "covenants.Covenant",
        on_delete=models.CASCADE,
        related_name="court_grant_offer_details",
        help_text="The Court covenant this petition raises the servant's grant in.",
    )

    def __str__(self) -> str:
        return f"CourtGrantOfferDetails for {self.offer} ({self.covenant})"


class OfferSummons(SharedMemoryModel):
    """A directed offer — a master's wish aimed at a specific servant (#2050).

    Rides the existing offer rails: accepting delegates to ``resolve_offer``
    → ``issue_mission`` (eligibility + risk-ack intact). Declining or letting
    it lapse is an explicit, recorded act the master remembers: affection
    drops, a refusal streak climbs, and past the threshold the master's
    escalation pool fires.

    Generic per ADR-0010/ADR-0085 — any ``NPCRole`` can direct an offer at a
    persona. The Court layer contributes its escalation config on top.
    """

    offer = models.ForeignKey(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="summonses",
        help_text="The offer this summons directs at a target.",
    )
    target_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="summonses_received",
        help_text="The persona this summons is directed at.",
    )
    message = models.TextField(
        blank=True,
        help_text="IC text — what the servant learns of the master's wish.",
    )
    status = models.CharField(
        max_length=10,
        choices=SummonsStatus.choices,
        default=SummonsStatus.PENDING,
        db_index=True,
        help_text="Lifecycle state of this summons.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this summons lapses if unanswered. Null = no expiry.",
    )
    created_by = models.ForeignKey(
        "gm.GMProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="summonses_created",
        help_text="The GM who created this summons. Null for staff-created.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the summons was accepted, declined, or expired.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "target_persona"],
                condition=models.Q(status="pending"),
                name="unique_pending_summons_per_offer_persona",
            ),
        ]
        ordering = ["-created_at"]

    def clean(self) -> None:
        """Validate that the offer is MISSION-kind (v1 scope)."""
        if self.offer_id is not None and self.offer.kind != OfferKind.MISSION:
            msg = "Summonses are limited to MISSION-kind offers in v1 (#2050)."
            raise ValidationError({"offer": msg})

    def __str__(self) -> str:
        return f"Summons: {self.target_persona} ← {self.offer} ({self.status})"


class RegardEventConfig(SharedMemoryModel):
    """Singleton tuning surface (pk=1) for NpcRegardEvent buildup (#2039).

    Access via ``get_regard_event_config()`` — singleton-by-convention, no DB-level
    uniqueness constraint (mirrors ``BondCombatConfig``, ``SoulTetherConfig``).
    """

    objects = ArxSharedMemoryManager()

    max_event_delta = models.PositiveSmallIntegerField(
        default=100,
        help_text="Cap on |amount| for a single NpcRegardEvent — buildup is gradual.",
    )
    combat_defeat_amount = models.SmallIntegerField(
        default=-15,
        help_text="Regard delta when a PC defeats a notable NPC opponent in combat.",
    )
    combat_harm_amount = models.SmallIntegerField(
        default=-15,
        help_text="Regard delta when a notable NPC critically harms a PC in combat.",
    )
    story_vital_threshold = models.PositiveSmallIntegerField(
        default=200,
        help_text="|NpcRegard.value| at or above this marks the bond as story-vital.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _REGARD_EVENT_CONFIG_LABEL
        verbose_name_plural = _REGARD_EVENT_CONFIG_LABEL

    def __str__(self) -> str:
        return _REGARD_EVENT_CONFIG_LABEL


class NpcRegardEvent(SharedMemoryModel):
    """One typed, evidence-backed cause event feeding an NpcRegard's buildup (#2039).

    Mirrors justice's HeatSource/PersonaHeat ledger shape. Unlike HeatSource's
    optional LegendEntry citation, a PC-attributed reason here MUST cite a real,
    structured, resolved record — never a freetext claim. clean() enforces the
    citation matrix documented on NpcRegardEventReason.
    """

    regard = models.ForeignKey(
        NpcRegard,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="The NpcRegard row this event moved.",
    )
    reason = models.CharField(
        max_length=20,
        choices=NpcRegardEventReason.choices,
        help_text="Typed cause category — determines which citation field(s) are valid.",
    )
    amount = models.SmallIntegerField(
        help_text=(
            "Signed delta applied to NpcRegard.value. Clamped to RegardEventConfig.max_event_delta."
        ),
    )
    source_pc_combat_action = models.ForeignKey(
        "combat.CombatRoundAction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npc_regard_events",
        help_text="Set for PC_FOILED_NPC_PLAN: the PC's resolved combat action that caused this.",
    )
    source_npc_combat_action = models.ForeignKey(
        "combat.CombatOpponentAction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npc_regard_events",
        help_text=(
            "Set for NPC_HARMED_PC_INTEREST: the NPC's resolved combat action that caused this."
        ),
    )
    source_scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npc_regard_events",
        help_text="Set for SOCIAL_ACTION_RESOLVED: the scene the structured effect resolved in.",
    )
    source_stake_resolution = models.ForeignKey(
        "stories.StakeResolution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npc_regard_events",
        help_text="Set for STAKE_RESOLUTION: the pre-authored branch that fired this.",
    )
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "NPC Regard Event"
        verbose_name_plural = "NPC Regard Events"
        ordering = ["-created_date"]
        indexes = [
            models.Index(fields=["regard", "-created_date"]),
        ]

    _CITED_REASONS = {
        NpcRegardEventReason.NPC_HARMED_PC_INTEREST: ("source_npc_combat_action", "source_scene"),
        NpcRegardEventReason.PC_FOILED_NPC_PLAN: ("source_pc_combat_action", "source_scene"),
        NpcRegardEventReason.SOCIAL_ACTION_RESOLVED: ("source_scene",),
        NpcRegardEventReason.STAKE_RESOLUTION: ("source_stake_resolution",),
    }
    _ALL_CITATION_FIELDS = (
        "source_pc_combat_action",
        "source_npc_combat_action",
        "source_scene",
        "source_stake_resolution",
    )

    def clean(self) -> None:
        super().clean()
        set_fields = [f for f in self._ALL_CITATION_FIELDS if getattr(self, f"{f}_id")]
        if self.reason == NpcRegardEventReason.DISTINCTION_SEED:
            if set_fields:
                raise ValidationError(
                    {"reason": "DISTINCTION_SEED events must not cite any source."}
                )
            return
        if self.reason == NpcRegardEventReason.GM_MANUAL_ADJUSTMENT:
            if len(set_fields) > 1:
                raise ValidationError(
                    {"reason": "GM_MANUAL_ADJUSTMENT may cite at most one source."}
                )
            return
        allowed = self._CITED_REASONS[self.reason]
        cited_allowed = [f for f in set_fields if f in allowed]
        cited_disallowed = [f for f in set_fields if f not in allowed]
        if cited_disallowed:
            raise ValidationError(
                {
                    "reason": (
                        f"{self.get_reason_display()} cannot cite {cited_disallowed} — "
                        f"only {list(allowed)} are valid for this reason."
                    )
                }
            )
        if len(cited_allowed) != 1:
            raise ValidationError(
                {"reason": f"{self.get_reason_display()} must cite exactly one of {list(allowed)}."}
            )

    def __str__(self) -> str:
        return (
            f"NpcRegardEvent({self.get_reason_display()}, {self.amount:+d}) "
            f"on regard {self.regard_id}"
        )


class DistinctionRegardSeed(SharedMemoryModel):
    """Lookup sidecar: a Distinction pre-attaches a bond to a specific notable NPC (#2039).

    Mirrors DistinctionResonanceGrant's shape (magic/models/grants.py) and
    placement rationale (ADR-0010): lives in the dependent app npc_services, not
    in distinctions — the general Distinction primitive must not import every
    consumer that references it. Materialized onto a real NpcRegard/NpcRegardEvent
    pair at chargen by reconcile_distinction_regard_seeds().
    """

    distinction = models.ForeignKey(
        "distinctions.Distinction",
        on_delete=models.CASCADE,
        related_name="npc_regard_seeds",
    )
    npc_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="regard_seeds_from_distinctions",
        help_text="The specific notable NPC this distinction pre-attaches a bond to.",
    )
    starting_value = models.SmallIntegerField(
        validators=regard_validators,
        help_text="Initial NpcRegard.value applied at chargen.",
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="GM-facing flavor for the seed, e.g. 'Marked by the Choir'.",
    )

    class Meta:
        verbose_name = "Distinction Regard Seed"
        verbose_name_plural = "Distinction Regard Seeds"
        constraints = [
            models.UniqueConstraint(
                fields=["distinction", "npc_persona"], name="unique_distinction_regard_seed"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.distinction} seeds regard with {self.npc_persona}"


class AssignmentRole(models.TextChoices):
    """The role an NPC serves when assigned to a room.

    GUARD is the first implemented behavior (post-arrival detection).
    DOORMAN is reserved for pre-traversal announcement (needs-design).
    SERVANT is reserved for the follow-up servant-fetch issue.
    """

    GUARD = "guard", "Guard"
    DOORMAN = "doorman", "Doorman"
    SERVANT = "servant", "Servant"


class NPCSourceType(models.TextChoices):
    """Discriminator: which kind of NPC is assigned."""

    FUNCTIONARY = "functionary", "Functionary"
    NPC_ASSET = "npc_asset", "NPC Asset"


class NPCAssignment(SharedMemoryModel, DiscriminatorMixin):
    """An NPC posted to a room in a specific role by an owner persona (#2178).

    A join model with a discriminator FK to either a Functionary (class-1
    placement) or an NPCAsset (promoted/owned NPC). One active GUARD per room
    (partial unique constraint); retired assignments stay as audit history.

    Guard detection reads ``NPCAssignment.objects.filter(room=profile,
    assignment_role=GUARD, is_active=True)`` — a single query regardless of
    NPC class.
    """

    source_type = models.CharField(
        max_length=20,
        choices=NPCSourceType.choices,
        help_text="Discriminator: which kind of NPC is assigned.",
    )
    functionary = models.ForeignKey(
        Functionary,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assignments",
        help_text="The class-1 Functionary placement (set when source_type=FUNCTIONARY).",
    )
    npc_asset = models.ForeignKey(
        "assets.NPCAsset",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assignments",
        help_text="The promoted NPCAsset (set when source_type=NPC_ASSET).",
    )
    room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="npc_assignments",
        help_text="The room this NPC is posted to.",
    )
    assignment_role = models.CharField(
        max_length=20,
        choices=AssignmentRole.choices,
        help_text="What role the NPC serves: GUARD, DOORMAN, SERVANT.",
    )
    assigned_by = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="npc_assignments_made",
        help_text="The persona who made the assignment (audit trail, not a permission gate).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this assignment is currently active. False = retired.",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this assignment was retired. Null while active.",
    )

    DISCRIMINATOR_FIELD = "source_type"
    DISCRIMINATOR_MAP = {
        NPCSourceType.FUNCTIONARY: "functionary",
        NPCSourceType.NPC_ASSET: "npc_asset",
    }

    def clean(self) -> None:
        """Validate the source_type discriminator (exactly one FK set)."""
        super().clean()
        errors = self._validate_discriminator(self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP)
        if errors:
            raise ValidationError(errors)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room", "assignment_role"],
                condition=models.Q(is_active=True),
                name="unique_active_npc_assignment_per_room_role",
            ),
        ]
        ordering = ["-assigned_at"]

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"{target} as {self.assignment_role} @ room {self.room_id}"


class StylingOfferDetails(SharedMemoryModel):
    """Per-kind details for ``NPCServiceOffer`` rows of kind=STYLING (#2632).

    Menu-driven NPC styling: one offer row per (trait, option) — "Dye hair
    crimson", "Braid hair" — because the interaction machinery has no free
    input channel, and a menu of concrete services reads naturally anyway.
    The same ``change_appearance`` seam PC stylists use applies the change;
    only ``is_cosmetic`` traits validate (the offer IS the gate, mirroring
    ``ItemTemplateAppearanceEffect``).
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="styling_offer_details",
        help_text=_NPC_OFFER_DETAILS_HELP_TEXT,
    )
    trait = models.ForeignKey(
        "forms.FormTrait",
        on_delete=models.PROTECT,
        related_name="styling_offers",
        help_text="The cosmetic trait this service restyles.",
    )
    target_option = models.ForeignKey(
        "forms.FormTraitOption",
        on_delete=models.PROTECT,
        related_name="styling_offers",
        help_text="The value the trait is set to.",
    )
    price_coppers = models.PositiveBigIntegerField(
        help_text="Coppers charged from the PC's purse. PLACEHOLDER magnitudes."
    )

    class Meta:
        verbose_name = "Styling Offer Details"
        verbose_name_plural = "Styling Offer Details"

    def __str__(self) -> str:
        return f"StylingOfferDetails({self.trait_id}->{self.target_option_id}, o{self.offer_id})"

    def clean(self) -> None:
        """Option must belong to the trait; the trait must be cosmetic."""
        super().clean()
        if self.target_option_id is not None and self.target_option.trait_id != self.trait_id:
            raise ValidationError({"target_option": "Option does not belong to this trait."})
        if self.trait_id is not None and not self.trait.is_cosmetic:
            raise ValidationError({"trait": "Only cosmetic traits can be restyled."})


class ProfileRecordingOfferDetails(SharedMemoryModel):
    """Per-kind details for kind=PROFILE_RECORDING (#2632) — an Archive sitting.

    Paying resolves the offer into a COMMISSIONED ``RecordedProfile``; the
    player completes the write-up afterwards (the scholar "delivers" it),
    which sets the character's description and archives the text forever.
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="profile_recording_offer_details",
        help_text=_NPC_OFFER_DETAILS_HELP_TEXT,
    )
    price_coppers = models.PositiveBigIntegerField(
        help_text="Coppers charged from the PC's purse. PLACEHOLDER magnitudes."
    )

    class Meta:
        verbose_name = "Profile Recording Offer Details"
        verbose_name_plural = "Profile Recording Offer Details"

    def __str__(self) -> str:
        return f"ProfileRecordingOfferDetails(offer {self.offer_id})"


class RecordedProfile(SharedMemoryModel):
    """A profile recorded at the Great Archive (or a similar institution) (#2632).

    The diegetic description archive: an NPC scholar "writes" the character's
    profile (the player authors the prose and pays for the privilege), the
    text becomes the character's current description, and every recorded
    profile persists forever — desc history, in-world. Persona-scoped (never
    account): a cover face sits for its own profile.
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="recorded_profiles",
        help_text="The persona whose profile was recorded.",
    )
    status = models.CharField(
        max_length=20,
        choices=RecordedProfileStatus.choices,
        default=RecordedProfileStatus.COMMISSIONED,
        db_index=True,
    )
    text = models.TextField(
        blank=True,
        default="",
        help_text="The recorded profile prose (player-written, diegetically NPC-authored).",
    )
    recorded_by_label = models.CharField(
        max_length=200,
        help_text="Display name of the recording scholar/institution.",
    )
    price_paid = models.PositiveBigIntegerField(help_text="Coppers paid for the sitting.")
    created_at = models.DateTimeField(auto_now_add=True)
    recorded_at = models.DateTimeField(null=True, blank=True)
    ic_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="IC datetime when the write-up was finalized.",
    )
    era = models.ForeignKey(
        "stories.Era",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recorded_profiles",
        help_text="The active Era (season) at recording time.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Recorded Profile"
        verbose_name_plural = "Recorded Profiles"

    def __str__(self) -> str:
        return f"RecordedProfile({self.persona_id}, {self.status}, #{self.pk})"
