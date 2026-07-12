from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from world.scenes.constants import SceneAction
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.scenes.models import Persona, Scene

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet, Profile
    from world.forms.models import CharacterForm
    from world.scenes.models import PersonaDiscovery

ActionType = SceneAction


class MissingPrimaryPersonaError(LookupError):
    """A played Character is missing a CharacterSheet or PRIMARY persona.

    Per ``character_sheets/CLAUDE.md`` every played character has a
    CharacterSheet with a PRIMARY persona — that's a load-bearing repo
    invariant. Hitting this exception means something upstream broke that
    invariant (character_creation didn't finalize, test scaffolding skipped
    sheet setup, etc.) and we fail loud rather than silently bypass gates
    that depend on the persona.

    Lives here (not on ``npc_services``) because the resolver is general —
    NPCStanding, item-ownership audit snapshots, and mission flavor all
    want a PC's primary persona, and none of those callers should depend
    on the npc_services app.
    """

    def __init__(self, character: Character) -> None:
        super().__init__(
            f"Character {character!r} has no PRIMARY persona — required invariant "
            "(see character_sheets/CLAUDE.md). Check character_creation finalize "
            "or test setup."
        )
        self.character = character


def persona_for_character(character: Character) -> Persona:
    """Return the PC's PRIMARY persona; raise loud on missing sheet/persona.

    A played character without a sheet or PRIMARY persona is a programmer
    error per ``character_sheets/CLAUDE.md``; we surface that loudly rather
    than silently bypassing any gate that needs the persona (cooldown,
    standing, item ownership, etc.).
    """
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        raise MissingPrimaryPersonaError(character)
    try:
        return sheet.primary_persona
    except Exception as exc:
        raise MissingPrimaryPersonaError(character) from exc


class ActivePersonaError(ValueError):
    """A ``set_active_persona`` call targeting a persona that isn't this sheet's.

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``) so the
    switch endpoint can surface a safe string without leaking object ids.
    """

    user_message = "That isn't one of this character's identities."


def active_persona_for_sheet(sheet: CharacterSheet) -> Persona:
    """The face a character is currently presenting as (#981).

    Returns the durable ``active_persona`` when set, else the PRIMARY persona.
    This is THE answer to "which persona is this character on right now" — gate
    every IC-meaningful read on this, never on ``primary_persona`` directly, so
    presenting as an ESTABLISHED alt or a TEMPORARY mask is honoured and a
    player's other faces never leak. Pure; never mutates. (Propagates the loud
    ``Persona.DoesNotExist`` only when the PRIMARY invariant is itself broken —
    the request-level resolver is the fail-closed boundary that maps that to a
    safe deny.)
    """
    active = sheet.active_persona
    if active is not None:
        return active
    return sheet.primary_persona


def set_active_persona(sheet: CharacterSheet, persona: Persona) -> None:
    """Set the character's active face (#981) — the ONLY mutator.

    Both doors that may change the face go through here: an explicit player
    switch, and an IC-forced swap (e.g. the TEMPORARY-mask system restoring the
    covered face via ``set_active_persona(sheet, covered_face)``). Validates the
    persona is one of *this* character's own faces — a foreign persona raises
    ``ActivePersonaError`` and never silently crosses identities.
    """
    if persona.character_sheet_id != sheet.pk:
        raise ActivePersonaError
    sheet.active_persona = persona
    sheet.save(update_fields=["active_persona"])


class PersonaCreationError(ValueError):
    """An invalid persona-creation request (#1127).

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``) so the creation
    endpoint surfaces a safe string. The specific reason is set per-raise.
    """

    user_message = "That identity can't be created."

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        if user_message is not None:
            self.user_message = user_message


def create_persona(
    sheet: CharacterSheet,
    *,
    name: str,
    persona_type: str,
    is_fake_name: bool = False,
    bypass_cap: bool = False,
) -> Persona:
    """Create a new ESTABLISHED or TEMPORARY persona for a character (#1127).

    The designed, validated creation path that replaces the removed raw ``ModelViewSet`` create
    (an identity-security-critical surface). Rules:

    - **PRIMARY is never created here** — it's minted once at character creation.
    - **System personas are never created here** (OOC narrator/GM identities).
    - **ESTABLISHED is capped** per sheet (``settings.MAX_ESTABLISHED_PERSONAS_PER_SHEET``); staff
      pass ``bypass_cap=True``. TEMPORARY masks are uncapped (throwaway).

    Enforces the **descriptor-never-auto-attach privacy invariant** (#1109) *structurally*: this
    creates the persona and **nothing else** — no ``PersonaTraitDescriptor`` is copied from a
    sibling face, so a new persona always starts with a blank descriptor set. Deliberate reuse is a
    later explicit author action, never a creation-time default.
    """
    from django.conf import settings  # noqa: PLC0415

    from world.scenes.constants import PersonaType  # noqa: PLC0415

    cleaned_name = (name or "").strip()
    if not cleaned_name:
        msg = "Persona name is required."
        raise PersonaCreationError(msg, user_message="A name is required.")

    if persona_type not in (PersonaType.ESTABLISHED, PersonaType.TEMPORARY):
        msg = f"persona_type {persona_type!r} cannot be created via the player flow."
        user_msg = "You can only create established identities or temporary masks."
        raise PersonaCreationError(msg, user_message=user_msg)

    if persona_type == PersonaType.ESTABLISHED and not bypass_cap:
        cap = settings.MAX_ESTABLISHED_PERSONAS_PER_SHEET
        existing = Persona.objects.filter(
            character_sheet=sheet, persona_type=PersonaType.ESTABLISHED
        ).count()
        if existing >= cap:
            msg = f"established-persona cap reached ({existing}/{cap})"
            user_msg = f"You already hold the most established identities allowed ({cap})."
            raise PersonaCreationError(msg, user_message=user_msg)

    return Persona.objects.create(
        character_sheet=sheet,
        name=cleaned_name,
        persona_type=persona_type,
        is_fake_name=is_fake_name,
    )


def create_mask(
    sheet: CharacterSheet,
    *,
    name: str,
    disguise_form: CharacterForm | None = None,
    disguise_kind: str | None = None,
) -> Persona:
    """Create a TEMPORARY anonymous **mask** — the "put on a mask" path (#1127).

    A throwaway, identity-obscuring (``is_fake_name=True``) TEMPORARY persona. When a
    ``disguise_form`` is supplied it is applied as a fake overlay over the wearer's real form
    (#1110), tying the social mask to the physical disguise; the wearer's active face is switched
    to the mask. Without a disguise form it is a name-only mask (sdesc-rendered until discovered).
    """
    from world.forms.models import DisguiseKind  # noqa: PLC0415

    mask = create_persona(
        sheet,
        name=name,
        persona_type="temporary",
        is_fake_name=True,
    )
    if disguise_form is not None:
        from world.forms.services import apply_disguise  # noqa: PLC0415

        kind = DisguiseKind(disguise_kind) if disguise_kind else DisguiseKind.MUNDANE
        apply_disguise(sheet.character, disguise_form, kind=kind)
    set_active_persona(sheet, mask)
    return mask


class GuiseProfileError(ValueError):
    """An invalid Guise-Sheet authoring request (#1270).

    Carries a fixed ``user_message`` (per ``feedback_codeql_exceptions``) so the authoring surface
    surfaces a safe string. Raised when authoring a guise for the PRIMARY face (whose real bio is
    the sheet's ``true_profile``, edited through the sheet — never as a guise).
    """

    user_message = "You can't give your true face a cover bio — edit your real sheet instead."


def set_persona_profile(
    persona: Persona,
    *,
    concept: str | None = None,
    quote: str | None = None,
    personality: str | None = None,
    background: str | None = None,
) -> Profile:
    """Author the fabricated bio a non-primary persona presents — its **Guise Sheet** (#1270).

    A cover/established persona needs its OWN concept/quote/personality/background so the *absence*
    of a bio doesn't instantly out it as fake. This is the **sole mutator** of ``Persona.profile``:
    it attaches a fresh ``Profile`` the first time the persona is given a bio, then updates only the
    fields passed (``None`` leaves a field untouched, so callers can edit one field at a time).

    PRIMARY is rejected — the real face's bio is the sheet's ``true_profile``, edited through the
    sheet, never authored here. Only narrative text is set; **lineage stays display-only** (the
    sheet's forwarding properties keep every *mechanical* lineage read on the real ``true_profile``,
    so a fabricated guise can never leak into mechanics).
    """
    from world.character_sheets.models import Profile  # noqa: PLC0415
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    if persona.persona_type == PersonaType.PRIMARY:
        msg = "Cannot author a guise profile for a PRIMARY persona."
        raise GuiseProfileError(msg)

    profile = persona.profile
    created = profile is None
    if created:
        profile = Profile()
    updates = {
        "concept": concept,
        "quote": quote,
        "personality": personality,
        "background": background,
    }
    for field_name, value in updates.items():
        if value is not None:
            setattr(profile, field_name, value)
    profile.save()
    if created:
        persona.profile = profile
        persona.save(update_fields=["profile"])
    return profile


def broadcast_scene_message(scene: Scene, action: ActionType) -> None:
    """Send scene information to all accounts in the scene's location.

    The room caches its active scene when a scene starts or ends so that
    subsequent room state payloads can avoid extra database lookups.

    Args:
        scene: Scene to announce.
        action: Event type for the scene.
    """
    location = scene.location
    if location is None:
        return
    if action in (SceneAction.START, SceneAction.END):
        invalidate_active_scene_cache(location)
        cast(Any, location).active_scene = scene if action == SceneAction.START else None
    for obj in location.contents:
        try:
            account = obj.account
        except AttributeError:
            continue
        is_owner = scene.is_owner(account)
        payload = {
            "action": action,
            "scene": {
                "id": scene.id,
                "name": scene.name,
                "description": scene.description,
                "is_owner": is_owner,
            },
        }
        account.msg(scene=((), payload))


def register_unseen_observer(scene: Scene, observer: CharacterSheet, source_label: str) -> None:
    """Record that observer can unseen-witness scene; broadcast the OOC state if new.

    Mechanism-agnostic (#1225): any unseen-observation grant (physical concealment
    today, a future scrying/remote-viewing feature later) calls this. The broadcast
    payload never carries observer identity — see _broadcast_unseen_observer_state.
    """
    from world.scenes.models import SceneUnseenObserver  # noqa: PLC0415

    _, created = SceneUnseenObserver.objects.get_or_create(
        scene=scene, observer=observer, defaults={"source_label": source_label}
    )
    if created:
        _broadcast_unseen_observer_state(scene)


def clear_unseen_observer(scene: Scene, observer: CharacterSheet) -> None:
    """Clear observer's unseen-observation grant on scene; broadcast if it changed
    whether any unseen observer remains (#1225)."""
    from world.scenes.models import SceneUnseenObserver  # noqa: PLC0415

    deleted, _ = SceneUnseenObserver.objects.filter(scene=scene, observer=observer).delete()
    if deleted:
        _broadcast_unseen_observer_state(scene)


def has_unseen_observers(scene: Scene) -> bool:
    """Whether any unseen-observation grant is currently active on scene (#1225)."""
    from world.scenes.models import SceneUnseenObserver  # noqa: PLC0415

    return SceneUnseenObserver.objects.filter(scene=scene).exists()


def _normalized_persona_pair(
    persona: Persona | None, linked: Persona | None
) -> tuple[Persona, Persona] | None:
    """Normalize a persona pair to ``(lower pk, higher pk)``, matching ``PersonaDiscovery``'s own
    ``persona_discovery_normalized_order`` check constraint. ``None`` when the pair is degenerate
    — either side missing, or they're literally the same persona (nothing to link)."""
    if persona is None or linked is None or persona.pk == linked.pk:
        return None
    return (persona, linked) if persona.pk < linked.pk else (linked, persona)


def persona_discovery_between(
    persona: Persona | None, linked: Persona | None, discovered_by: CharacterSheet
) -> PersonaDiscovery | None:
    """The existing ``PersonaDiscovery`` row for this (unordered) persona pair + discoverer, if
    any — a pure read, never writes. ``None`` for a degenerate pair (see
    ``_normalized_persona_pair``) or when no such row exists yet."""
    from world.scenes.models import PersonaDiscovery  # noqa: PLC0415

    pair = _normalized_persona_pair(persona, linked)
    if pair is None:
        return None
    lower, higher = pair
    return PersonaDiscovery.objects.filter(
        persona=lower, linked_to=higher, discovered_by=discovered_by
    ).first()


def record_persona_discovery(
    persona: Persona | None, linked: Persona | None, discovered_by: CharacterSheet
) -> PersonaDiscovery | None:
    """Record that ``discovered_by`` learned ``persona`` and ``linked`` are the same person.

    The single writer of ``PersonaDiscovery`` rows — shared by ``world.clues.services``'s
    GM-authored clue-piercing path (``_grant_persona_link_target``, #2120) and
    ``world.forms.services.identification.attempt_identification``'s rolled-check path (#1107
    slice 5), so the normalization logic isn't duplicated between them. Idempotent
    (``get_or_create``) — attempting the same pair again is a no-op, not a duplicate row. Returns
    ``None`` without writing for a degenerate pair (see ``_normalized_persona_pair``) — e.g. the
    presented persona already IS the true persona, so there's nothing to pierce.
    """
    from world.scenes.models import PersonaDiscovery  # noqa: PLC0415

    pair = _normalized_persona_pair(persona, linked)
    if pair is None:
        return None
    lower, higher = pair
    discovery, _ = PersonaDiscovery.objects.get_or_create(
        persona=lower, linked_to=higher, discovered_by=discovered_by
    )
    return discovery


def _broadcast_unseen_observer_state(scene: Scene) -> None:
    """Re-send room_state to every occupant of scene's location, so the
    identity-free ``has_unseen_observer`` flag on the scene payload (#1225) is
    fresh for everyone present — routes through the same, already-wired
    ``room_state`` channel every login/move already uses (rather than a bespoke
    payload key with no frontend consumer and no resend-on-reconnect), so a
    player who reconnects or walks in while a grant is already active also
    sees the current state without a separate re-sync mechanism."""
    location = scene.location
    if location is None:
        return
    location._broadcast_room_state()  # noqa: SLF001
