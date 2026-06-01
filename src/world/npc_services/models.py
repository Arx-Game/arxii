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

    Used by every kind of NPC service to gate offers on standing/affection
    and to enforce per-NPC cooldowns where applicable. Class-1 nameless
    functionary interactions do NOT create rows; class-2+ named NPCs do.
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
    available_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Cooldown gate (mission accept sets this; non-mission consumers "
            "leave null). availability filters exclude rows with "
            "`available_at > now`."
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

    def __str__(self) -> str:
        return f"{self.role.name}: {self.label} [{self.kind}]"


class PermitOfferDetails(SharedMemoryModel):
    """Per-kind details for `NPCServiceOffer` rows of kind=PERMIT.

    Stub for Plan 2's framework wiring; Plan 3 (#668) fills in the
    permit-specific fields (which ItemTemplate to issue, default
    `approved_wards`, default `max_scope`, etc.).
    """

    offer = models.OneToOneField(
        NPCServiceOffer,
        on_delete=models.CASCADE,
        related_name="permit_offer_details",
        help_text="The NPCServiceOffer row this details model decorates.",
    )

    def __str__(self) -> str:
        return f"PermitOfferDetails for {self.offer}"
