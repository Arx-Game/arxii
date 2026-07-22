"""Services for the intake Ritual of the Durance (#2479).

The intake rite is the registration ceremony that enters a new Gifted into
the Durance arc. It is structurally similar to the level-advancement Durance
rite, but instead of advancing a class level it enrolls the character in an
intake cohort and sets their ``durance_entered_at`` marker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

_UNBOUND_TRADITION_NAME = "Unbound"
_DURANCE_ANTIPHON_SPONSORED = "durance_antiphon_sponsored"
_DURANCE_ANTIPHON_UNSponsored = "durance_antiphon_unsponsored"

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.sessions import RitualSession
    from world.progression.models.durance_cohort import CohortEnrollment, DuranceCohort
    from world.scenes.models import Persona, Scene
    from world.societies.models import Organization


def get_or_create_open_academy_cohort(
    academy: Organization, scene: Scene | None = None
) -> DuranceCohort:
    """Return the current open intake cohort for the Academy, creating one if needed.

    A cohort is considered open while ``closed_at`` is NULL. There should be at most
    one open cohort per Academy; this function lazily creates it.
    """
    from world.progression.models.durance_cohort import DuranceCohort

    cohort = DuranceCohort.objects.filter(organization=academy, closed_at__isnull=True).first()
    if cohort is None:
        cohort = DuranceCohort.objects.create(organization=academy, enrollment_scene=scene)
    return cohort


def enroll_in_durance_cohort(
    *,
    persona: Persona,
    cohort: DuranceCohort,
    scene: Scene | None = None,
) -> CohortEnrollment:
    """Idempotently enroll a persona in a Durance cohort.

    Updates the cached ``CharacterSheet.durance_cohort`` FK for cheap reads.
    """
    from world.progression.models.durance_cohort import CohortEnrollment

    enrollment, _ = CohortEnrollment.objects.get_or_create(
        cohort=cohort,
        persona=persona,
        defaults={"enrollment_scene": scene},
    )
    sheet = persona.character_sheet
    if sheet.durance_cohort_id != cohort.pk:
        sheet.durance_cohort = cohort
        sheet.save(update_fields=["durance_cohort"])
    return enrollment


def _compose_testament(sheet: CharacterSheet) -> str:
    """Compose the intake testament from Glimpse story + origin prose + name."""
    from world.character_creation.services import assemble_origin_prose
    from world.magic.models import CharacterAura

    parts = [f"I am {sheet.character.key}."]
    try:
        aura = CharacterAura.objects.get(character_sheet=sheet)
    except CharacterAura.DoesNotExist:
        aura = None
    if aura and aura.glimpse_story:
        parts.append(aura.glimpse_story)
    origin = assemble_origin_prose(sheet)
    if origin:
        parts.append(origin)
    return "\n\n".join(parts)


def _post_testament(
    inductee_sheet: CharacterSheet, *, testament: str
) -> tuple[Scene | None, object | None]:
    """Post the testament oration as a POSE via the active-scene helper."""
    from world.magic.audere_majora import _post_declaration

    text = (testament or "").strip()
    if not text:
        text = _compose_testament(inductee_sheet)
    return _post_declaration(inductee_sheet.character, text)


def _record_witnesses(
    session: RitualSession,
    scene: Scene | None,
    inductee: CharacterSheet,
) -> list[Persona]:
    """Record scene witnesses for the registration rite."""
    from world.societies.knowledge_services import scene_witness_personas

    if scene is None:
        return []
    excluded = {inductee.pk, session.initiator_id}
    return [p for p in scene_witness_personas(scene) if p.character_sheet_id not in excluded]


def _fire_enrollment_antiphon(inductee: CharacterSheet, scene: Scene | None) -> None:
    """Emit the enrollment antiphon as a room message.

    Sponsored = tradition != Unbound; unsponsored = Unbound. Actual text is
    authored in the lore repo and delivered via the content pipeline. This
    machinery only dispatches the emit with a content key.
    """
    if scene is None or scene.location is None:
        return

    from world.magic.models import CharacterTradition

    try:
        tradition = CharacterTradition.objects.get(character_sheet=inductee)
        sponsored = tradition.tradition.name != _UNBOUND_TRADITION_NAME
    except CharacterTradition.DoesNotExist:
        sponsored = False

    key = _DURANCE_ANTIPHON_SPONSORED if sponsored else _DURANCE_ANTIPHON_UNSponsored
    text = f"[{key}]"
    scene.location.msg_contents(text)


def register_durance_via_session(*, session: RitualSession) -> dict:
    """Fire handler for the intake Ritual of the Durance.

    Dispatched by ``fire_session`` inside the session's transaction. For each
    ACCEPTED inductee (participant who is not the initiator):
    - Skip if already registered (``durance_entered_at`` set).
    - Compose the testament from Glimpse story + origin prose.
    - Post it as a POSE in the active scene.
    - Enroll the active persona in the current open Academy cohort.
    - Set ``CharacterSheet.durance_entered_at``.
    - Record witnesses from the scene.
    - Fire the enrollment antiphon (sponsored vs unsponsored) as a room emit.

    Returns a dict with ``enrolled``, ``already_registered``, ``witnessed`` lists.
    """
    from world.magic.constants import ParticipantState

    result = {"enrolled": [], "already_registered": [], "witnessed": []}

    accepted = session.participants.filter(state=ParticipantState.ACCEPTED)
    inductees = [p for p in accepted if p.character_sheet_id != session.initiator_id]
    if not inductees:
        return result

    academy = _get_shroudwatch_academy()
    if academy is None:
        return result

    cohort = get_or_create_open_academy_cohort(academy, scene=session.scene)

    for participant in inductees:
        inductee = participant.character_sheet
        persona = inductee.primary_persona
        if inductee.durance_entered_at is not None:
            result["already_registered"].append(persona)
            continue
        testament = participant.participant_kwargs.get("testament", "").strip()
        scene, _interaction = _post_testament(inductee, testament=testament)

        enroll_in_durance_cohort(persona=persona, cohort=cohort, scene=scene)

        inductee.durance_entered_at = timezone.now()
        inductee.save(update_fields=["durance_entered_at"])

        witnesses = _record_witnesses(session, scene, inductee)
        result["witnessed"].extend(witnesses)

        _fire_enrollment_antiphon(inductee, scene)

        result["enrolled"].append(persona)

    return result


def _get_shroudwatch_academy() -> Organization | None:
    """Resolve the Shroudwatch Academy organization, if seeded."""
    from world.societies.models import Organization

    return Organization.objects.filter(name="Shroudwatch Academy").first()
