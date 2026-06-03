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

from world.missions.constants import MissionStatus
from world.missions.models import MissionInstance, MissionParticipant
from world.missions.services.resolution import enter_node
from world.npc_services.constants import OfferKind
from world.npc_services.effects import EffectResult

if TYPE_CHECKING:
    from world.missions.models import MissionNode, MissionTemplate
    from world.npc_services.models import NPCServiceOffer
    from world.scenes.models import Persona


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

    instance = MissionInstance.objects.create(template=template, source_offer=offer)
    MissionParticipant.objects.create(
        instance=instance,
        character=character,
        is_contract_holder=True,
    )
    enter_node(instance, _entry_node(template))

    cooldown_duration = details.role_cooldown_duration or template.cooldown
    NPCRoleCooldown.objects.update_or_create(
        role=offer.role,
        persona=persona,
        defaults={"available_at": timezone.now() + cooldown_duration},
    )

    return EffectResult(
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
