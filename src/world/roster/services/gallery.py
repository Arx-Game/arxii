"""A character's gallery (#4151): its pictures, its looks, the worn one, and character art.

A character's gallery is the current player's own uploads plus the character's art
(staff-commissioned pictures that belong to the roster entry, not to a tenure). A
picture with a crop is a **look**; one look is **worn**, which is
``RosterEntry.profile_picture``. These functions are the only writers of a look's crop,
the worn look, the gallery's order and hides, so the rules that keep the worn look
showable live in one place:

- a worn look is a look, is not NSFW, is not hidden by the current player, and is this
  character's: the current tenure's upload or the character's own art;
- anything that takes the worn look away (un-cropping it, flagging it NSFW, hiding it,
  deleting it) wears the next showable look in order, or none.

``CloudinaryGalleryService`` stays the file store; this module decides what a character
does with the files.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import models, transaction
from django.db.models import Max, Q

from evennia_extensions.models import Media, PlayerData
from world.roster.models import HiddenCharacterArt, RosterEntry, RosterTenure, TenureMedia
from world.roster.services.gallery_services import CloudinaryGalleryService, media_bytes_used
from world.roster.types import MediaUsage

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import MoodOption

logger = logging.getLogger(__name__)

# The plate's shape: every crop is LOOK_WIDTH:LOOK_HEIGHT.
LOOK_WIDTH = 4
LOOK_HEIGHT = 5
# Smallest crop width, in the file's own pixels. Below this a face is a smudge.
MIN_LOOK_WIDTH = 60

_UPLOAD_SEGMENT = "/upload/"


class GalleryError(Exception):
    """A gallery change the rules refuse. ``user_message`` is safe to show the player."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class LookNotAllowedError(GalleryError):
    """This picture cannot be (or be worn as) a look."""


class PictureNotYoursError(GalleryError):
    """The requester may not delete this picture."""


class ReorderMismatchError(GalleryError):
    """A reorder named pictures that are not exactly the gallery's own."""


class DeleteOutcome(models.TextChoices):
    """What a Delete did: removed the file, or only took it off this character."""

    DELETED = "deleted", "Deleted"
    UNLINKED = "unlinked", "Removed from this character"


class Unset:
    """Marks an argument the caller did not pass, where ``None`` is a real value."""


UNSET = Unset()


# ---------------------------------------------------------------- reading the gallery


def gallery_q(entry: RosterEntry) -> Q:
    """The links that belong in this character's gallery right now."""
    current = entry.current_tenure
    in_art = Q(roster_entry=entry)
    return in_art | Q(tenure=current) if current is not None else in_art


def hidden_ids(entry: RosterEntry) -> set[int]:
    """Character art the current player has hidden."""
    current = entry.current_tenure
    if current is None:
        return set()
    return set(
        HiddenCharacterArt.objects.filter(tenure=current).values_list("picture_id", flat=True)
    )


def gallery_for(entry: RosterEntry, *, include_hidden: bool) -> list[TenureMedia]:
    """The character's pictures in order: the current player's uploads and its art.

    Hidden character art is left out unless ``include_hidden``, which only the current
    player's own view asks for (they see it dimmed, to show it again).
    """
    links = list(TenureMedia.objects.filter(gallery_q(entry)).select_related("media", "look"))
    if include_hidden:
        return links
    hidden = hidden_ids(entry)
    return [link for link in links if link.pk not in hidden]


def _showable(entry: RosterEntry, link: TenureMedia, hidden: set[int]) -> bool:
    """May this character wear this link right now."""
    current = entry.current_tenure
    belongs = link.roster_entry_id == entry.pk or (
        current is not None and link.tenure_id == current.pk
    )
    return belongs and link.is_look and not link.media.is_nsfw and link.pk not in hidden


def worn_look(entry: RosterEntry) -> TenureMedia | None:
    """The worn look, or None when what is stored may no longer be shown.

    Reading through this rather than ``entry.profile_picture`` keeps a handed-over
    character from wearing the last player's upload before anything re-picks it.
    """
    link = entry.profile_picture
    if link is None:
        return None
    return link if _showable(entry, link, hidden_ids(entry)) else None


def look_url(link: TenureMedia | None) -> str | None:
    """The URL every surface shows for this picture: its 4:5 crop when it is a look.

    The crop is a Cloudinary transformation inserted after ``/upload/`` in the stored
    delivery URL, so no extra file is made and changing the crop is free. A URL that is
    not a Cloudinary delivery URL (staff-pasted art, test data) is returned as it is.
    """
    if link is None:
        return None
    url = link.media.cloudinary_url
    if not link.is_look or _UPLOAD_SEGMENT not in url:
        return url
    head, tail = url.split(_UPLOAD_SEGMENT, 1)
    crop = f"c_crop,x_{link.crop_x},y_{link.crop_y},w_{link.crop_width},h_{link.crop_height}"
    return f"{head}{_UPLOAD_SEGMENT}{crop}/{tail}"


def portrait_url(entry: RosterEntry) -> str | None:
    """The worn look's cropped URL for surfaces that list many characters.

    Query-free given ``profile_picture__media`` and ``profile_picture__tenure`` are
    selected: it skips the hides lookup ``worn_look`` makes, which is safe because hiding
    the worn look always re-picks it. What it still refuses is a look the last player
    uploaded (their tenure has ended), so a handed-over character shows no face rather
    than someone else's.
    """
    link = entry.profile_picture
    if link is None or not link.is_look or link.media.is_nsfw:
        return None
    if link.tenure_id is not None and link.tenure.end_date is not None:
        return None
    return look_url(link)


def media_usage(player_data: PlayerData) -> MediaUsage:
    """Storage used, and the player's quota."""
    return MediaUsage(
        used_bytes=media_bytes_used(player_data),
        quota_bytes=player_data.media_quota_bytes,
    )


# ---------------------------------------------------------------- the worn look


def _repick_worn(entry: RosterEntry) -> None:
    """Wear the first showable look in order, or none, if the worn one can't be shown."""
    if worn_look(entry) is not None:
        return
    hidden = hidden_ids(entry)
    replacement = next(
        (
            link
            for link in gallery_for(entry, include_hidden=True)
            if _showable(entry, link, hidden)
        ),
        None,
    )
    if entry.profile_picture_id != (replacement.pk if replacement else None):
        entry.profile_picture = replacement
        entry.save(update_fields=["profile_picture"])


def wear_look(entry: RosterEntry, link: TenureMedia) -> None:
    """Make ``link`` the face this character shows everywhere."""
    if not _showable(entry, link, hidden_ids(entry)):
        msg = f"TenureMedia {link.pk} cannot be worn by entry {entry.pk}"
        raise LookNotAllowedError(msg, user_message="That picture can't be worn as a look.")
    entry.profile_picture = link
    entry.full_clean()
    entry.save(update_fields=["profile_picture"])


# ---------------------------------------------------------------- looks


def _fit_crop(media: Media, x: int, y: int, width: int) -> tuple[int, int, int]:
    """Shrink and move a 4:5 frame until it lies inside the image, when its size is known."""
    if media.width is None or media.height is None:
        return x, y, width
    max_width = min(media.width, media.height * LOOK_WIDTH // LOOK_HEIGHT)
    width = min(width, max_width)
    height = round(width * LOOK_HEIGHT / LOOK_WIDTH)
    x = min(max(x, 0), media.width - width)
    y = min(max(y, 0), media.height - height)
    return x, y, width


def set_look(
    link: TenureMedia,
    *,
    x: int,
    y: int,
    width: int,
    mood: MoodOption | None,
) -> TenureMedia:
    """Crop ``link`` into a look (or re-crop it), tagged with the mood it shows."""
    if link.media.is_nsfw:
        msg = f"TenureMedia {link.pk} is NSFW"
        raise LookNotAllowedError(msg, user_message="An NSFW picture can't be a look.")
    x, y, width = _fit_crop(link.media, x, y, width)
    if width < MIN_LOOK_WIDTH:
        msg = f"crop width {width} below {MIN_LOOK_WIDTH}"
        raise LookNotAllowedError(msg, user_message="That frame is too small to show a face.")
    link.crop_x, link.crop_y, link.crop_width = x, y, width
    link.look = mood
    link.save(update_fields=["crop_x", "crop_y", "crop_width", "look"])
    return link


def _entry_of(link: TenureMedia) -> RosterEntry:
    if link.roster_entry_id is not None:
        return link.roster_entry
    return link.tenure.roster_entry


@transaction.atomic
def clear_look(link: TenureMedia) -> None:
    """Make ``link`` a plain picture again; if it was worn, wear the next look."""
    link.crop_x = link.crop_y = link.crop_width = None
    link.save(update_fields=["crop_x", "crop_y", "crop_width"])
    _repick_worn(_entry_of(link))


@transaction.atomic
def update_picture(
    link: TenureMedia,
    *,
    title: str | None = None,
    caption: str | None = None,
    is_nsfw: bool | None = None,
    mood: MoodOption | None | Unset = UNSET,
) -> TenureMedia:
    """Change what a picture says about itself. Flagging a look NSFW un-crops it."""
    media = link.media
    changed: list[str] = []
    if title is not None:
        media.title = title
        changed.append("title")
    if caption is not None:
        media.description = caption
        changed.append("description")
    if is_nsfw is not None:
        media.is_nsfw = is_nsfw
        changed.append("is_nsfw")
    if changed:
        media.save(update_fields=changed)
    if not isinstance(mood, Unset):
        link.look = mood
        link.save(update_fields=["look"])
    if media.is_nsfw and link.is_look:
        clear_look(link)
    return link


def reorder_pictures(entry: RosterEntry, link_ids: Sequence[int]) -> None:
    """Put the gallery in this order. ``link_ids`` must be exactly its pictures."""
    own = {link.pk: link for link in gallery_for(entry, include_hidden=True)}
    if len(link_ids) != len(own) or set(link_ids) != set(own):
        msg = f"reorder ids {list(link_ids)} != gallery {sorted(own)}"
        raise ReorderMismatchError(msg, user_message="The gallery changed; reload and try again.")
    with transaction.atomic():
        for index, pk in enumerate(link_ids):
            link = own[pk]
            if link.sort_order != index:
                link.sort_order = index
                link.save(update_fields=["sort_order"])


# ---------------------------------------------------------------- adding and removing


def add_pictures(
    entry: RosterEntry,
    files: Iterable[UploadedFile],
    *,
    by: AccountDB,
) -> list[TenureMedia]:
    """Upload files into the character's gallery, at the end of its order.

    The current player's uploads join their tenure. Staff uploading to a character they
    are not playing add character art (#4151): it belongs to the character and costs
    nobody any storage, since the quota counts the uploader and staff are exempt.
    """
    current = entry.current_tenure
    as_art = bool(by.is_staff) and (current is None or current.player_data.account_id != by.pk)
    if not as_art and current is None:
        msg = f"entry {entry.pk} has no current tenure"
        raise PictureNotYoursError(msg, user_message="Nobody is playing this character.")
    last = TenureMedia.objects.filter(gallery_q(entry)).aggregate(top=Max("sort_order"))["top"]
    next_order = 0 if last is None else last + 1
    links: list[TenureMedia] = []
    for image_file in files:
        try:
            media = CloudinaryGalleryService.upload_image(
                player_data=by.player_data,
                image_file=image_file,
            )
        except ValidationError as exc:
            message = exc.messages[0] if exc.messages else "The upload failed."
            raise GalleryError(str(message), user_message=str(message)) from exc
        links.append(
            TenureMedia.objects.create(
                media=media,
                tenure=None if as_art else current,
                roster_entry=entry if as_art else None,
                sort_order=next_order,
            )
        )
        next_order += 1
    return links


def can_manage_gallery(account: AccountDB, entry: RosterEntry) -> bool:
    """May this account change this character's gallery: its current player, or staff."""
    if not account.is_authenticated:
        return False
    if account.is_staff:
        return True
    current = entry.current_tenure
    return current is not None and current.player_data.account_id == account.pk


def entry_of(link: TenureMedia) -> RosterEntry:
    """The character a picture belongs to, whichever owner it hangs off."""
    return _entry_of(link)


def may_delete_picture(link: TenureMedia, by: AccountDB) -> bool:
    """Players delete their own files; staff delete anything, character art included."""
    if by.is_staff:
        return True
    if link.is_character_art:
        return False
    return link.media.player_data_id is not None and link.media.player_data.account_id == by.pk


def delete_picture(link: TenureMedia, *, by: AccountDB) -> DeleteOutcome:
    """The gallery's one Delete.

    Deletes the file, freeing its storage, unless another character's gallery also
    holds it; then it only comes off this one. Players may delete only their own files;
    character art is staff's to delete (a player hides it instead).
    """
    if not may_delete_picture(link, by):
        msg = f"account {by.pk} may not delete TenureMedia {link.pk}"
        raise PictureNotYoursError(msg, user_message="You can't delete that picture.")
    entry = _entry_of(link)
    media = link.media
    shared = TenureMedia.objects.filter(media=media).exclude(pk=link.pk).exists()
    with transaction.atomic():
        # Take it off first: the delete's SET_NULL reaches the row, but the entry may
        # still hold the deleted link as a cached relation and go on "wearing" it.
        if entry.profile_picture_id == link.pk:
            entry.profile_picture = None
            entry.save(update_fields=["profile_picture"])
        link.delete()
        _repick_worn(entry)
    if shared:
        return DeleteOutcome.UNLINKED
    # Outside the transaction: Cloudinary is not transactional, and delete_media removes
    # the row even when the remote call fails (logging the orphaned asset).
    CloudinaryGalleryService.delete_media(media)
    return DeleteOutcome.DELETED


def hide_character_art(link: TenureMedia, tenure: RosterTenure) -> None:
    """The current player stops showing this piece of character art."""
    hide = HiddenCharacterArt(tenure=tenure, picture=link)
    hide.full_clean(validate_constraints=False)
    with transaction.atomic():
        HiddenCharacterArt.objects.get_or_create(tenure=tenure, picture=link)
        _repick_worn(tenure.roster_entry)


def show_character_art(link: TenureMedia, tenure: RosterTenure) -> None:
    """Show hidden character art again."""
    HiddenCharacterArt.objects.filter(tenure=tenure, picture=link).delete()
