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

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.npc_services.constants import DrawMode, OfferKind


class NPCStanding(SharedMemoryModel):
    """Per-(PC persona, NPC persona) durable disposition.

    Used by every kind of NPC service to gate offers on standing /
    affection. Class-1 nameless functionary interactions do NOT create
    rows; class-2+ named NPCs do. Standing and cooldown are deliberately
    orthogonal — cooldown lives on :class:`OfferCooldown` (per-offer per-
    persona) so it works for every offer kind, not just NPC-rooted ones.
    """

    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="npc_standings",
        help_text="The PC's persona that holds this standing.",
    )
    npc_persona = models.ForeignKey(
        "scenes.Persona",
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


class NPCRole(SharedMemoryModel):
    """A kind of NPC role — a bundle of `NPCServiceOffer` rows.

    One role can be instantiated across the world as multiple class-1 NPCs
    (every Builders Guild Clerk in every guild hall) or attached to a
    specific class-2+ named NPC. Offers are authored on the role; per-NPC
    overrides are a follow-up.
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
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npc_roles",
        help_text=(
            "Optional org this role fronts for (e.g., Builders Guild Clerk → "
            "Builders Guild Organization). Used by org-scoped permission filters."
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

    def __str__(self) -> str:
        return self.name


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
        "scenes.Persona",
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
        "scenes.Persona",
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
    mission_template = models.ForeignKey(
        "missions.MissionTemplate",
        on_delete=models.CASCADE,
        related_name="offer_details",
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

    class Meta:
        verbose_name_plural = "Mission offer details"
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "mission_template"],
                name="unique_mod_offer_template",
            ),
        ]

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
        help_text="The NPCServiceOffer row this details model decorates.",
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
