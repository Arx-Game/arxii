"""The player's writes to a face: a mask's description and portrait (#4033, #4889).

A face is a ``Persona`` or an ``AlternateSelf``. A portrait is always a private copy or a
new upload stored under ``FACE_PORTRAIT_FOLDER``, so its web address carries no player or
character number, and both routes go through the one shared upload limit
(``world.roster.services.gallery_services.enforce_player_media_limits``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import QuerySet

from evennia_extensions.models import Media, MediaType, PlayerData
from server.conf.mush_markup import normalize_mush_markup
from world.forms.models import AlternateSelf
from world.roster.models import TenureMedia
from world.roster.services.gallery_services import FACE_PORTRAIT_FOLDER, CloudinaryGalleryService
from world.scenes.constants import PersonaType
from world.scenes.models import Persona

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

# The longest a mask's description may be; the real description has no cap, and this keeps
# ``look`` readable.
MAX_FACE_DESCRIPTION_CHARS = 4000


class FaceError(ValueError):
    """A refused write to a face, carrying a fixed message safe to show the player."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def pickable_portrait_media(player_data: PlayerData | None) -> QuerySet[Media]:
    """The player's own pictures a portrait may be copied from.

    Never another player's, never one the owner marked NSFW (the rule that keeps it from
    being a look), and never a face copy this feature stored: picking one would only copy a
    copy. The one queryset the picker lists and the request serializer validates against.
    """
    if player_data is None:
        return Media.objects.none()
    return Media.objects.filter(player_data=player_data, is_nsfw=False).exclude(
        cloudinary_public_id__startswith=f"{FACE_PORTRAIT_FOLDER}/"
    )


def sync_persona_portrait(persona: Persona, media: Media | None) -> None:
    """Set both copies of a persona's portrait: the ``thumbnail`` link and its text copy.

    Poses and the combat and battle lists read the text, room state and the sheet read the
    link, so every writer of one sets both here, the admin included.
    """
    persona.thumbnail = media
    persona.thumbnail_url = media.cloudinary_url if media is not None else ""
    persona.save(update_fields=["thumbnail", "thumbnail_url"])


def _require_face_editable(sheet: CharacterSheet) -> None:
    """Refuse an edit while the character cannot act at all (#4889).

    The same state gate ``set_active_persona`` runs: a dead, unconscious, captured, retired
    or unaccounted-for character's player cannot reach into their faces either. It is keyed
    on the persona-swap action because editing a face is the same family of act; the gate's
    other prerequisite for a swap, that the face is one of the character's own, is the
    ownership check each write already makes.
    """
    from actions.constants import OffscreenActState  # noqa: PLC0415
    from actions.offscreen_gate import offscreen_act_state  # noqa: PLC0415

    gate = offscreen_act_state(sheet, "set_active_persona")
    if gate.state != OffscreenActState.ALLOWED:
        raise FaceError(gate.reason or "That cannot be done now.")


def set_persona_description(persona: Persona, text: str) -> None:
    """Write the mask's own description; blank clears it. PRIMARY is refused."""
    _require_face_editable(persona.character_sheet)
    if persona.persona_type == PersonaType.PRIMARY:
        msg = "Your true face is described on your character sheet."
        raise FaceError(msg)
    persona.description = normalize_mush_markup(text)
    persona.save(update_fields=["description"])


def set_face_portrait(
    face: Persona | AlternateSelf,
    *,
    player_data: PlayerData,
    media: Media | None = None,
    image_file: UploadedFile | None = None,
    clear: bool = False,
) -> None:
    """Pick, upload or remove the portrait of a persona or an alternate self.

    Exactly one of ``media`` (a copy of one of the player's own pictures), ``image_file``
    (a new upload) and ``clear`` is given. The writer sets every copy of the picture in one
    place: a persona's ``thumbnail`` and ``thumbnail_url`` together (poses read the text,
    room state reads the link), an alternate self's ``thumbnail`` and its persona's two
    fields, and, for an alternate self's persona, each alternate self wearing it. A copy the
    face held before is deleted when nothing else uses it; a staff-authored picture is never
    deleted, so staff can restore it in the admin.

    Raises:
        FaceError: The write is refused, with a message safe to show.
    """
    if sum([media is not None, image_file is not None, clear]) != 1:
        msg = "Choose a picture, upload one, or remove the portrait."
        raise FaceError(msg)
    persona = face if isinstance(face, Persona) else face.persona
    if persona is not None and persona.persona_type == PersonaType.PRIMARY:
        msg = "Your true face takes its portrait from your gallery."
        raise FaceError(msg)
    if media is not None and (media.player_data_id != player_data.pk or media.is_nsfw):
        msg = "That picture can't be used as a portrait."
        raise FaceError(msg)

    if (
        isinstance(face, AlternateSelf)
        and persona is not None
        and persona.character_sheet_id != face.character_id
    ):
        msg = "That portrait cannot be set on this form."
        raise FaceError(msg)
    _require_face_editable(persona.character_sheet if persona is not None else face.character)
    selves = _selves_rewritten(face, persona)
    with transaction.atomic():
        replaced = _replaced_pictures(persona, selves)
        # What the swap frees is counted in the quota check, inside the lock, so a portrait
        # can be replaced when the new one fits once the old copy is gone; the old copy is
        # deleted only after the new one is stored.
        freed = sum(
            old.file_size_bytes or 0
            for old in replaced
            if _is_unused_face_copy(old, player_data, persona, selves)
        )
        new_media = _stored_portrait(
            player_data, media=media, image_file=image_file, freed_bytes=freed
        )
        _write_portrait(persona, selves, new_media)
        for old in replaced:
            if _is_unused_face_copy(old, player_data, persona, selves):
                CloudinaryGalleryService.delete_media(old)


def delete_unused_face_copies(replaced: list[Media | None]) -> None:
    """Delete the private face copies a staff save in the admin stopped using (#4889).

    The admin's Thumbnail field replaces or clears a face's picture without going through
    ``set_face_portrait``, so the copy the player stored for that face would stay, still
    counting against her storage. Call this after the save with each picture the face held
    before: a private copy nothing else wears is deleted, the same rule a player's own
    replace follows; a staff-authored picture and a gallery picture are never touched.
    """
    for old in {media.pk: media for media in replaced if media is not None}.values():
        if old.player_data is not None and _is_unused_face_copy(old, old.player_data, None, []):
            CloudinaryGalleryService.delete_media(old)


def _stored_portrait(
    player_data: PlayerData,
    *,
    media: Media | None,
    image_file: UploadedFile | None,
    freed_bytes: int,
) -> Media | None:
    """The new private ``Media`` for a pick or an upload; None when the portrait is removed."""
    try:
        if media is not None:
            return CloudinaryGalleryService.copy_image(
                player_data,
                media,
                folder=FACE_PORTRAIT_FOLDER,
                media_type=MediaType.PORTRAIT,
                freed_bytes=freed_bytes,
            )
        if image_file is not None:
            return CloudinaryGalleryService.upload_image(
                player_data,
                image_file,
                media_type=MediaType.PORTRAIT,
                folder=FACE_PORTRAIT_FOLDER,
                freed_bytes=freed_bytes,
            )
    except ValidationError as exc:
        message = exc.messages[0] if exc.messages else "The upload failed."
        raise FaceError(str(message)) from exc
    return None


def _selves_rewritten(
    face: Persona | AlternateSelf, persona: Persona | None
) -> list[AlternateSelf]:
    """The alternate selves whose picture this write sets."""
    if isinstance(face, AlternateSelf):
        return [face]
    if persona is not None and persona.persona_type == PersonaType.ALTERNATE:
        return list(
            AlternateSelf.objects.filter(persona=persona, character=persona.character_sheet)
        )
    return []


def _replaced_pictures(persona: Persona | None, selves: list[AlternateSelf]) -> list[Media]:
    """The pictures this write replaces, each once: a persona and its form often share one."""
    held = ([persona.thumbnail] if persona is not None else []) + [
        alt_self.thumbnail for alt_self in selves
    ]
    return list({media.pk: media for media in held if media is not None}.values())


def _write_portrait(
    persona: Persona | None, selves: list[AlternateSelf], new_media: Media | None
) -> None:
    """Point every copy of the portrait at ``new_media``."""
    if persona is not None:
        sync_persona_portrait(persona, new_media)
    for alt_self in selves:
        alt_self.thumbnail = new_media
        alt_self.save(update_fields=["thumbnail"])


def _is_unused_face_copy(
    old: Media, player_data: PlayerData, persona: Persona | None, selves: list[AlternateSelf]
) -> bool:
    """Whether a replaced picture is this player's private face copy that nothing else uses.

    A staff-authored picture, a gallery picture and a copy another face still wears all stay.
    The faces this write rewrites do not count as users: they are about to stop wearing it.
    """
    is_face_copy = old.player_data_id == player_data.pk and old.cloudinary_public_id.startswith(
        f"{FACE_PORTRAIT_FOLDER}/"
    )
    if not is_face_copy:
        return False
    other_personas = Persona.objects.filter(thumbnail=old)
    if persona is not None:
        other_personas = other_personas.exclude(pk=persona.pk)
    other_selves = AlternateSelf.objects.filter(thumbnail=old).exclude(
        pk__in=[alt_self.pk for alt_self in selves]
    )
    return not (
        other_personas.exists()
        or other_selves.exists()
        or TenureMedia.objects.filter(media=old).exists()
    )
