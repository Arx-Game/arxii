"""The player's writes to a face: a mask's description and portrait (#4033, #4889).

A face is a ``Persona`` or an ``AlternateSelf``. A portrait is always a private copy or a
new upload stored under ``FACE_PORTRAIT_FOLDER``, so its web address carries no player or
character number, and both routes go through the one shared upload limit
(``world.roster.services.gallery_services.enforce_player_media_limits``).
"""

from __future__ import annotations

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


def set_persona_description(persona: Persona, text: str) -> None:
    """Write the mask's own description; blank clears it. PRIMARY is refused."""
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

    with transaction.atomic():
        new_media = _stored_portrait(player_data, media=media, image_file=image_file)
        previous = _write_portrait(face, persona, new_media)
        # One picture often sits on both a persona and its alternate self; it is deleted once.
        for old in {media.pk: media for media in previous}.values():
            _delete_if_unused_face_copy(old, player_data)


def _stored_portrait(
    player_data: PlayerData, *, media: Media | None, image_file: UploadedFile | None
) -> Media | None:
    """The new private ``Media`` for a pick or an upload; None when the portrait is removed."""
    try:
        if media is not None:
            return CloudinaryGalleryService.copy_image(
                player_data, media, folder=FACE_PORTRAIT_FOLDER, media_type=MediaType.PORTRAIT
            )
        if image_file is not None:
            return CloudinaryGalleryService.upload_image(
                player_data,
                image_file,
                media_type=MediaType.PORTRAIT,
                folder=FACE_PORTRAIT_FOLDER,
            )
    except ValidationError as exc:
        message = exc.messages[0] if exc.messages else "The upload failed."
        raise FaceError(str(message)) from exc
    return None


def _write_portrait(
    face: Persona | AlternateSelf, persona: Persona | None, new_media: Media | None
) -> list[Media]:
    """Point every copy of the portrait at ``new_media``; return the pictures it replaced."""
    previous: list[Media] = []
    if persona is not None:
        if persona.thumbnail is not None:
            previous.append(persona.thumbnail)
        sync_persona_portrait(persona, new_media)

    if isinstance(face, AlternateSelf):
        selves = [face]
    elif persona is not None and persona.persona_type == PersonaType.ALTERNATE:
        selves = list(
            AlternateSelf.objects.filter(persona=persona, character=persona.character_sheet)
        )
    else:
        selves = []
    for alt_self in selves:
        if alt_self.thumbnail is not None:
            previous.append(alt_self.thumbnail)
        alt_self.thumbnail = new_media
        alt_self.save(update_fields=["thumbnail"])
    return previous


def _delete_if_unused_face_copy(old: Media, player_data: PlayerData) -> None:
    """Delete a replaced picture only when it is this player's private face copy.

    A staff-authored picture, a gallery picture and a copy another face still wears all stay.
    """
    is_face_copy = old.player_data_id == player_data.pk and old.cloudinary_public_id.startswith(
        f"{FACE_PORTRAIT_FOLDER}/"
    )
    if not is_face_copy:
        return
    in_use = (
        Persona.objects.filter(thumbnail=old).exists()
        or AlternateSelf.objects.filter(thumbnail=old).exists()
        or TenureMedia.objects.filter(media=old).exists()
    )
    if not in_use:
        CloudinaryGalleryService.delete_media(old)
