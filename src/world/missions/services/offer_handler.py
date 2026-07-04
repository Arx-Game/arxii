"""MISSION effect handler for ``NPCServiceOffer`` (#686).

Registered with ``world.npc_services.effects.OFFER_EFFECT_HANDLERS`` at
``MissionsConfig.ready()``. Wraps the existing accept-mission lifecycle —
``MissionInstance`` + ``MissionParticipant`` + ``enter_node`` — but with the
unified ``(offer, persona) -> EffectResult`` signature the framework expects.

Cooldown semantics (#686 spec AD#1): the handler writes BOTH
- a per-(offer, persona) ``OfferCooldown`` row (so the same mission can't be
  immediately re-rolled by the same persona; gated by
  ``NPCServiceOffer.cooldown`` set at the framework level), AND
- a per-(role, persona) ``NPCRoleCooldown`` row (so OTHER missions on the
  role are also blocked for the cooldown window).

Both are written here; the framework's ``resolve_offer`` also writes the
``OfferCooldown`` for any offer with a non-null ``cooldown`` (idempotent —
``update_or_create``). Role cooldown duration is sourced from
``MissionOfferDetails.role_cooldown_duration`` and falls back to
``MissionTemplate.cooldown``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.missions.constants import MISSION_RISK_ACK_TIER, MissionStatus
from world.missions.models import MissionInstance, MissionParticipant, MissionRiskAcknowledgement
from world.missions.services.resolution import enter_node
from world.missions.services.run import anchor_room_for
from world.npc_services.constants import OfferKind
from world.npc_services.effects import EffectResult
from world.npc_services.services import ResolveOfferError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.missions.models import MissionNode, MissionTemplate
    from world.npc_services.models import NPCServiceOffer
    from world.scenes.models import Persona


class MissionRiskUnacknowledgedError(ResolveOfferError):
    """A risky mission was accepted without an on-record acknowledgement (#1770 PR4).

    Carries the template's ``risk_tier`` and the player-visible stake
    summaries (empty today — offers carry no beat link yet, see
    ``_require_risk_acknowledgement``) so the player surface can show what
    is being committed to and instruct re-running with
    ``acknowledge_risk=yes``.
    """

    user_message = "This job is dangerous; you must acknowledge the risk before accepting."

    def __init__(
        self,
        msg: str,
        *,
        risk_tier: int,
        stake_summaries: Iterable[str] = (),
    ) -> None:
        super().__init__(msg)
        self.risk_tier = risk_tier
        self.stake_summaries = tuple(stake_summaries)


def acknowledge_mission_risk(
    offer: NPCServiceOffer,
    persona: Persona,
) -> MissionRiskAcknowledgement | None:
    """Idempotently record that a persona acknowledged an offer's mission risk.

    Mirrors ``combat.services.acknowledge_encounter_risk`` (get_or_create;
    the tier is snapshotted at first acknowledgement). Returns None for
    offers that are not mission-kind (nothing to acknowledge).
    """
    from world.npc_services.models import MissionOfferDetails  # noqa: PLC0415

    details = MissionOfferDetails.objects.filter(offer=offer).first()
    if details is None:
        return None
    ack, _created = MissionRiskAcknowledgement.objects.get_or_create(
        offer=offer,
        persona=persona,
        defaults={"acknowledged_risk_tier": details.mission_template.risk_tier},
    )
    return ack


def _require_risk_acknowledgement(
    offer: NPCServiceOffer,
    persona: Persona,
    template: MissionTemplate,
) -> None:
    """The mission-accept risk gate (#1770 PR4).

    A template at or above ``MISSION_RISK_ACK_TIER`` requires a
    ``MissionRiskAcknowledgement`` row before the run is created. Offers
    carry no story-beat link today (``source_beat`` is only set on
    beat-launched runs, never by this handler), so the "linked beat has
    stakes" leg of the gate has nothing to check at offer time — it lives in
    ``activate_stakes_for_instance``, which runs whenever a beat link exists.
    """
    if template.risk_tier < MISSION_RISK_ACK_TIER:
        return
    if MissionRiskAcknowledgement.objects.filter(offer=offer, persona=persona).exists():
        return
    msg = (
        f"Offer {offer.pk} (template {template.pk!r}, risk_tier {template.risk_tier}) "
        f"requires a MissionRiskAcknowledgement from persona {persona.pk}."
    )
    raise MissionRiskUnacknowledgedError(msg, risk_tier=template.risk_tier)


def _entry_node(template: MissionTemplate) -> MissionNode:
    """Return the template's unique entry node (mirrors run._entry_node)."""
    from world.missions.models import MissionNode  # noqa: PLC0415

    return MissionNode.objects.get(template=template, is_entry=True)


@transaction.atomic
def issue_mission(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """MISSION effect handler: instantiate ``offer.mission_offer_details.mission_template``.

    Side effects (atomic):
      * Create a :class:`MissionInstance` (status ACTIVE) carrying
        ``source_offer = offer`` so the PC-cap counter walks the FK.
      * Create one :class:`MissionParticipant` for the persona's character,
        ``is_contract_holder=True``.
      * Phase-3 ``enter_node`` writes the entry-node snapshot and sets
        ``instance.current_node``.
      * Upsert ``NPCRoleCooldown(role=offer.role, persona, available_at=now+duration)``.
        Duration: ``MissionOfferDetails.role_cooldown_duration`` or fallback
        ``MissionTemplate.cooldown``.

    Returns an ``EffectResult`` carrying the new instance pk so the
    interaction state machine can render a closing message.
    """
    from world.npc_services.models import NPCRoleCooldown  # noqa: PLC0415

    details = offer.mission_offer_details
    template = details.mission_template
    character = persona.character_sheet.character

    # #1770 PR4: risky work needs an on-record acknowledgement BEFORE any
    # state is written (the atomic block would roll back anyway; gating first
    # keeps the state machine honest).
    _require_risk_acknowledgement(offer, persona, template)

    instance = MissionInstance.objects.create(
        template=template,
        source_offer=offer,
        accepted_as_persona=persona,
        source_beat=details.source_beat,
        # #885: the NPC interaction happens where the character stands —
        # that room is the run's anchor for ANCHOR-mode nodes.
        anchor_room=anchor_room_for(character),
    )
    MissionParticipant.objects.create(
        instance=instance,
        character=character,
        is_contract_holder=True,
    )
    enter_node(instance, _entry_node(template))

    # #1770 PR4 / #1780: mission acceptance is the stakes commit moment
    # (pillar 9) — lock any staked linked beat's contract for the accepting
    # party. Live for offer-issued runs whose MissionOfferDetails.source_beat
    # names a staked beat; a no-op for free or unstaked runs.
    from world.missions.services.beat import activate_stakes_for_instance  # noqa: PLC0415

    activate_stakes_for_instance(instance, [persona.character_sheet])

    # ``template.cooldown`` is NOT NULL at the schema level, so the
    # ``or`` fallback can never resolve to None; no guard needed.
    cooldown_duration = details.role_cooldown_duration or template.cooldown
    NPCRoleCooldown.objects.update_or_create(
        role=offer.role,
        persona=persona,
        defaults={"available_at": timezone.now() + cooldown_duration},
    )

    return EffectResult(
        # ty quirk: see comment in MissionsConfig.ready for the str() wrapper.
        kind=str(OfferKind.MISSION.value),
        object_pk=instance.pk,
        object_label=template.name,
        message=f"Mission '{template.name}' accepted.",
        payload={
            "instance_pk": instance.pk,
            "template_pk": template.pk,
            "persona_pk": persona.pk,
            "offer_pk": offer.pk,
        },
    )


def _is_mission_active(instance: MissionInstance) -> bool:
    """Identity-map-safe check that an instance is still considered "in flight" (#686).

    The per-(persona × role) gate filters on ``status=ACTIVE``; this helper
    centralises the predicate so the same definition is used everywhere
    (mission completion / abandonment that flips status will free the slot).
    """
    return instance.status == MissionStatus.ACTIVE
