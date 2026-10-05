"""Gallery services (#4151): looks, the worn look, character art, deleting and hiding."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from evennia_extensions.factories import MediaFactory
from evennia_extensions.models import Media
from world.character_sheets.factories import MoodOptionFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterTenureFactory,
    TenureMediaFactory,
)
from world.roster.models import HiddenCharacterArt, TenureMedia
from world.roster.services.gallery import (
    DeleteOutcome,
    LookNotAllowedError,
    PictureNotYoursError,
    ReorderMismatchError,
    add_pictures,
    clear_look,
    delete_picture,
    gallery_for,
    hidden_ids,
    hide_character_art,
    look_url,
    media_usage,
    reorder_pictures,
    set_look,
    show_character_art,
    update_picture,
    wear_look,
    worn_look,
)

CLOUD_URL = "https://res.cloudinary.com/arx/image/upload/v17/char_1/abc.jpg"


def _look(link: TenureMedia, *, x: int = 0, y: int = 0, width: int = 200) -> TenureMedia:
    link.crop_x, link.crop_y, link.crop_width = x, y, width
    link.save()
    return link


class LookUrlTests(TestCase):
    """One cropped URL that every surface reads."""

    def test_a_look_gets_its_crop_inserted_after_upload(self) -> None:
        link = _look(TenureMediaFactory(media__cloudinary_url=CLOUD_URL), x=10, y=20, width=200)
        assert look_url(link) == (
            "https://res.cloudinary.com/arx/image/upload/c_crop,x_10,y_20,w_200,h_250/"
            "v17/char_1/abc.jpg"
        )

    def test_a_picture_without_a_crop_keeps_its_own_url(self) -> None:
        link = TenureMediaFactory(media__cloudinary_url=CLOUD_URL)
        assert look_url(link) == CLOUD_URL

    def test_a_url_that_is_not_cloudinary_is_left_alone(self) -> None:
        link = _look(TenureMediaFactory(media__cloudinary_url="https://example.com/a.png"))
        assert look_url(link) == "https://example.com/a.png"

    def test_no_picture_is_no_url(self) -> None:
        assert look_url(None) is None


class SetLookTests(TestCase):
    """Cropping a picture into a look."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.mood = MoodOptionFactory(name="Furious")

    def test_the_crop_and_mood_are_saved(self) -> None:
        link = TenureMediaFactory(media__width=1000, media__height=1000)
        set_look(link, x=100, y=50, width=400, mood=self.mood)
        link.refresh_from_db()
        assert (link.crop_x, link.crop_y, link.crop_width) == (100, 50, 400)
        assert link.crop_height == 500
        assert link.look == self.mood

    def test_a_frame_past_the_image_is_pulled_back_inside(self) -> None:
        link = TenureMediaFactory(media__width=600, media__height=1000)
        set_look(link, x=500, y=900, width=400, mood=None)
        assert (link.crop_x, link.crop_y, link.crop_width) == (200, 500, 400)

    def test_a_frame_bigger_than_the_image_shrinks_to_fit(self) -> None:
        link = TenureMediaFactory(media__width=400, media__height=400)
        set_look(link, x=0, y=0, width=900, mood=None)
        # The largest 4:5 frame in a 400x400 image is 320 wide (400 tall).
        assert (link.crop_x, link.crop_y, link.crop_width) == (0, 0, 320)

    def test_a_tiny_frame_is_refused(self) -> None:
        link = TenureMediaFactory(media__width=1000, media__height=1000)
        with self.assertRaises(LookNotAllowedError):
            set_look(link, x=0, y=0, width=10, mood=None)

    def test_an_nsfw_picture_cannot_be_a_look(self) -> None:
        link = TenureMediaFactory(media__is_nsfw=True)
        with self.assertRaises(LookNotAllowedError):
            set_look(link, x=0, y=0, width=200, mood=None)

    def test_without_known_size_the_crop_is_kept_as_sent(self) -> None:
        link = TenureMediaFactory(media__width=None, media__height=None)
        set_look(link, x=5, y=6, width=300, mood=None)
        assert (link.crop_x, link.crop_y, link.crop_width) == (5, 6, 300)


class WornLookTests(TestCase):
    """The worn look is always one the current player may show."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        self.entry = self.tenure.roster_entry
        self.first = _look(TenureMediaFactory(tenure=self.tenure, sort_order=0))
        self.second = _look(TenureMediaFactory(tenure=self.tenure, sort_order=1))
        wear_look(self.entry, self.first)

    def test_wearing_a_look_sets_the_profile_picture(self) -> None:
        assert worn_look(self.entry) == self.first

    def test_a_picture_that_is_not_a_look_cannot_be_worn(self) -> None:
        plain = TenureMediaFactory(tenure=self.tenure)
        with self.assertRaises(LookNotAllowedError):
            wear_look(self.entry, plain)

    def test_another_characters_look_cannot_be_worn(self) -> None:
        other = _look(TenureMediaFactory())
        with self.assertRaises(LookNotAllowedError):
            wear_look(self.entry, other)

    def test_clearing_the_worn_look_wears_the_next_one(self) -> None:
        clear_look(self.first)
        self.entry.refresh_from_db()
        assert self.entry.profile_picture == self.second

    def test_clearing_the_last_look_wears_nothing(self) -> None:
        clear_look(self.second)
        clear_look(self.first)
        self.entry.refresh_from_db()
        assert self.entry.profile_picture is None

    def test_flagging_the_worn_look_nsfw_takes_it_off(self) -> None:
        update_picture(self.first, is_nsfw=True)
        self.first.refresh_from_db()
        self.entry.refresh_from_db()
        assert not self.first.is_look
        assert self.entry.profile_picture == self.second

    def test_a_new_player_does_not_wear_the_last_players_upload(self) -> None:
        self._hand_over()
        assert worn_look(self.entry) is None

    def _hand_over(self) -> None:
        from django.utils import timezone

        self.tenure.end_date = timezone.now()
        self.tenure.save()
        RosterTenureFactory(roster_entry=self.entry, player_number=2)
        self.entry.invalidate_tenure_cache()


class CharacterArtTests(TestCase):
    """Staff art belongs to the character; a player can hide it, not delete it."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        self.entry = self.tenure.roster_entry
        self.own = TenureMediaFactory(tenure=self.tenure, sort_order=0)
        self.art = _look(TenureMediaFactory(tenure=None, roster_entry=self.entry, sort_order=1))

    def test_the_gallery_holds_the_players_uploads_and_the_characters_art(self) -> None:
        assert gallery_for(self.entry, include_hidden=False) == [self.own, self.art]

    def test_a_new_player_keeps_the_art_and_not_the_last_players_uploads(self) -> None:
        from django.utils import timezone

        self.tenure.end_date = timezone.now()
        self.tenure.save()
        RosterTenureFactory(roster_entry=self.entry, player_number=2)
        self.entry.invalidate_tenure_cache()
        assert gallery_for(self.entry, include_hidden=False) == [self.art]

    def test_hidden_art_is_gone_for_visitors_but_kept_for_the_player(self) -> None:
        hide_character_art(self.art, self.tenure)
        assert hidden_ids(self.entry) == {self.art.pk}
        assert gallery_for(self.entry, include_hidden=False) == [self.own]
        assert gallery_for(self.entry, include_hidden=True) == [self.own, self.art]

    def test_hiding_the_worn_art_takes_it_off(self) -> None:
        wear_look(self.entry, self.art)
        hide_character_art(self.art, self.tenure)
        self.entry.refresh_from_db()
        assert self.entry.profile_picture is None

    def test_hidden_art_cannot_be_worn(self) -> None:
        hide_character_art(self.art, self.tenure)
        with self.assertRaises(LookNotAllowedError):
            wear_look(self.entry, self.art)

    def test_the_next_player_sees_hidden_art_again(self) -> None:
        from django.utils import timezone

        hide_character_art(self.art, self.tenure)
        self.tenure.end_date = timezone.now()
        self.tenure.save()
        RosterTenureFactory(roster_entry=self.entry, player_number=2)
        self.entry.invalidate_tenure_cache()
        assert gallery_for(self.entry, include_hidden=False) == [self.art]

    def test_showing_it_again_removes_the_hide(self) -> None:
        hide_character_art(self.art, self.tenure)
        show_character_art(self.art, self.tenure)
        assert not HiddenCharacterArt.objects.exists()

    def test_a_player_cannot_delete_character_art(self) -> None:
        with self.assertRaises(PictureNotYoursError):
            delete_picture(self.art, by=self.tenure.player_data.account)


@patch("world.roster.services.gallery.CloudinaryGalleryService.delete_media")
class DeletePictureTests(TestCase):
    """One Delete: the file goes and frees storage, unless another character uses it."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        self.player = self.tenure.player_data
        self.link = TenureMediaFactory(tenure=self.tenure)

    def test_deleting_your_upload_deletes_the_file(self, delete_media) -> None:
        assert delete_picture(self.link, by=self.player.account) == DeleteOutcome.DELETED
        delete_media.assert_called_once_with(self.link.media)

    def test_a_file_on_another_character_only_comes_off_this_one(self, delete_media) -> None:
        elsewhere = TenureMediaFactory(media=self.link.media)
        outcome = delete_picture(self.link, by=self.player.account)
        assert outcome == DeleteOutcome.UNLINKED
        delete_media.assert_not_called()
        assert TenureMedia.objects.filter(pk=elsewhere.pk).exists()
        assert not TenureMedia.objects.filter(pk=self.link.pk).exists()

    def test_someone_else_cannot_delete_it(self, delete_media) -> None:
        stranger = PlayerDataFactory()
        with self.assertRaises(PictureNotYoursError):
            delete_picture(self.link, by=stranger.account)
        delete_media.assert_not_called()

    def test_staff_can_delete_character_art(self, delete_media) -> None:
        art = TenureMediaFactory(tenure=None, roster_entry=self.tenure.roster_entry)
        staff = PlayerDataFactory(account__is_staff=True)
        assert delete_picture(art, by=staff.account) == DeleteOutcome.DELETED
        delete_media.assert_called_once_with(art.media)

    def test_deleting_the_worn_look_wears_the_next_one(self, delete_media) -> None:
        worn = _look(self.link)
        nxt = _look(TenureMediaFactory(tenure=self.tenure, sort_order=5))
        wear_look(self.tenure.roster_entry, worn)
        delete_media.side_effect = lambda media: media.delete()
        delete_picture(worn, by=self.player.account)
        entry = self.tenure.roster_entry
        entry.refresh_from_db()
        assert entry.profile_picture == nxt


class ReorderTests(TestCase):
    """Reordering takes exactly the gallery's own pictures."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenure = RosterTenureFactory()
        cls.entry = cls.tenure.roster_entry
        cls.a = TenureMediaFactory(tenure=cls.tenure, sort_order=0)
        cls.b = TenureMediaFactory(tenure=cls.tenure, sort_order=1)

    def test_the_new_order_is_kept(self) -> None:
        reorder_pictures(self.entry, [self.b.pk, self.a.pk])
        assert gallery_for(self.entry, include_hidden=False) == [self.b, self.a]

    def test_a_partial_list_is_refused(self) -> None:
        with self.assertRaises(ReorderMismatchError):
            reorder_pictures(self.entry, [self.b.pk])

    def test_another_characters_picture_is_refused(self) -> None:
        foreign = TenureMediaFactory()
        with self.assertRaises(ReorderMismatchError):
            reorder_pictures(self.entry, [self.a.pk, self.b.pk, foreign.pk])


class AddPicturesTests(TestCase):
    """Uploads land in the player's tenure, or on the character when staff add art."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        self.entry = self.tenure.roster_entry
        TenureMediaFactory(tenure=self.tenure, sort_order=3)

    def _upload(self, player_data, **_kwargs) -> Media:
        return MediaFactory(player_data=player_data, title="")

    def test_a_players_upload_joins_their_tenure_at_the_end(self) -> None:
        files = [SimpleUploadedFile("a.png", b"x"), SimpleUploadedFile("b.png", b"y")]
        with patch(
            "world.roster.services.gallery.CloudinaryGalleryService.upload_image",
            side_effect=self._upload,
        ):
            links = add_pictures(self.entry, files, by=self.tenure.player_data.account)
        assert [link.tenure for link in links] == [self.tenure, self.tenure]
        assert [link.sort_order for link in links] == [4, 5]

    def test_a_staff_upload_on_someone_elses_character_is_character_art(self) -> None:
        staff = PlayerDataFactory(account__is_staff=True)
        with patch(
            "world.roster.services.gallery.CloudinaryGalleryService.upload_image",
            side_effect=self._upload,
        ):
            (link,) = add_pictures(
                self.entry, [SimpleUploadedFile("c.png", b"z")], by=staff.account
            )
        assert link.is_character_art
        assert link.roster_entry == self.entry

    def test_an_upload_refused_by_the_store_says_why(self) -> None:
        from world.roster.services.gallery import GalleryError

        with (
            patch(
                "world.roster.services.gallery.CloudinaryGalleryService.upload_image",
                side_effect=ValidationError("This upload would exceed your media quota."),
            ),
            self.assertRaises(GalleryError) as caught,
        ):
            add_pictures(
                self.entry, [SimpleUploadedFile("d.png", b"z")], by=self.tenure.player_data.account
            )
        assert caught.exception.user_message == "This upload would exceed your media quota."


class MediaUsageTests(TestCase):
    """Storage used is what the player's own files take."""

    def test_usage_sums_the_players_files(self) -> None:
        player = PlayerDataFactory(media_quota_bytes=1000)
        MediaFactory(player_data=player, file_size_bytes=100)
        MediaFactory(player_data=player, file_size_bytes=250)
        MediaFactory(player_data=PlayerDataFactory(), file_size_bytes=999)
        usage = media_usage(player)
        assert (usage.used_bytes, usage.quota_bytes) == (350, 1000)
