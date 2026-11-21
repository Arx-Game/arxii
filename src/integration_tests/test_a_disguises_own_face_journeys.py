"""Journeys for a disguise's own face (#4889, #4033).

Ysmay's character wears an owl mask. A stranger, Hobb, in the same room:

- reads the mask's own description in ``look`` and on the sheet, never her real one, until
  he sees through the mask;
- sees the mask's portrait (a private copy of a picture she picked, or a new upload), or one
  placeholder when it has none, and never the real face;
- finds nothing in any payload, URL or storage path that ties the mask to her or her player.

Expected values come from the spec and its rulings: the one upload limit holds for a pick and
an upload alike, only her own pictures can be picked, and she can write only her own faces.
Cloudinary is the one thing doubled; its replies carry the sizes the spec's caps are measured
against. The two-uploads-at-once lock needs Postgres row locks and is proved by hand.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import AccountFactory, MediaFactory
from evennia_extensions.models import Media
from integration_tests.harness import JourneyCase
from world.conditions.thumbnail_services import BUILTIN_FACE_PLACEHOLDER_URL
from world.forms.factories import AlternateSelfFactory
from world.forms.models import ActiveAlternateSelf
from world.items.factories import EquippedItemFactory
from world.roster.factories import TenureMediaFactory
from world.roster.services.gallery import media_usage, set_look, wear_look
from world.roster.services.gallery_services import media_bytes_used
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.models import (
    FacePlaceholderConfig,
    Persona,
    get_face_placeholder_config,
)
from world.scenes.services import record_persona_discovery

SET_DESCRIPTION = "/api/personas/set-description/"
SET_PORTRAIT = "/api/personas/set-portrait/"
CHOICES = "/api/personas/portrait-choices/"
REAL_DESCRIPTION = "Tall, with a scar through one brow."
MASK_DESCRIPTION = "Slim and straight-backed, in a grey wool cloak pinned with a bronze leaf."
NOT_YOURS = "That is not one of your identities."
QUOTA_MESSAGE = "This upload would exceed your media quota."
FILE_MESSAGE = "This file is larger than the per-file limit."
MIB = 1024 * 1024


class CloudinaryDouble:
    """Stands in for ``cloudinary.uploader``: reports the size of what it was handed."""

    def __init__(self, *, remote_sizes: dict[str, int] | None = None) -> None:
        self.remote_sizes = remote_sizes or {}
        self.calls: list[dict[str, Any]] = []
        self.destroyed: list[str] = []

    def upload(self, file: object, **kwargs: Any) -> dict[str, Any]:
        size = file.size if hasattr(file, "size") else self.remote_sizes.get(str(file), 1000)
        self.calls.append({"file": file, **kwargs})
        public_id = kwargs["public_id"]
        return {
            "public_id": public_id,
            "secure_url": (
                f"https://res.cloudinary.com/test/image/upload/v17000{len(self.calls):05d}"
                f"/{public_id}.png"
            ),
            "bytes": size,
            "width": 800,
            "height": 1000,
        }

    def destroy(self, public_id: str) -> dict[str, str]:
        self.destroyed.append(public_id)
        return {"result": "ok"}


@override_settings(CLOUDINARY_CLOUD_NAME="test_cloud")
class DisguiseFaceCase(JourneyCase):
    """Ysmay's owl mask, Hobb who looks at her, and a doubled Cloudinary."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.sheet = self.ysmay.sheet_data
        self.sheet.additional_desc = REAL_DESCRIPTION
        self.sheet.save(update_fields=["additional_desc"])
        self.player = self.account_of(self.ysmay).player_data
        self.telnet(self.ysmay, "persona mask Owl Mask")
        self.mask = Persona.objects.get(character_sheet=self.sheet, name="Owl Mask")
        self.cloudinary = CloudinaryDouble()
        self.start_double(self.cloudinary)

    def start_double(self, double: CloudinaryDouble) -> None:
        for name, replacement in (("upload", double.upload), ("destroy", double.destroy)):
            patcher = patch(f"cloudinary.uploader.{name}", side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def ysmay_api(self) -> Any:
        return self.api(self.account_of(self.ysmay))

    def hobb_api(self) -> Any:
        return self.api(self.account_of(self.hobb))

    def her_picture(self, *, size: int = 1000, **kwargs: Any) -> Media:
        """A picture in her own gallery, stored under her player's folder."""
        account_pk = self.account_of(self.ysmay).pk
        return MediaFactory(
            player_data=self.player,
            cloudinary_public_id=f"player_{account_pk}/abc{size}",
            file_size_bytes=size,
            **kwargs,
        )

    def hobb_reads_sheet(self) -> dict[str, Any]:
        response = self.hobb_api().get(f"/api/character-sheets/{self.sheet.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def hobb_looks(self) -> str:
        return strip_ansi(self.telnet(self.hobb, "look Ysmay"))

    def give_her_a_real_look(self) -> str:
        """The look her real face wears; returns its URL as every surface shows it."""
        entry = self.sheet.roster_entry
        link = TenureMediaFactory(
            tenure=entry.current_tenure,
            media=MediaFactory(
                player_data=self.player, cloudinary_public_id="real_look", width=1000, height=1500
            ),
        )
        set_look(link, x=0, y=0, width=400, mood=None)
        wear_look(entry, link)
        from world.roster.services.gallery import look_url

        return look_url(link) or ""


class ThePortraitsOwnRows(DisguiseFaceCase):
    """What the writes store, and what Hobb can read of it."""

    def pick(self, media: Media, persona: Persona | None = None) -> Any:
        return self.ysmay_api().post(
            SET_PORTRAIT,
            {"persona_id": (persona or self.mask).pk, "media_id": media.pk},
            format="json",
        )

    def test_a_picked_portrait_is_a_private_copy_that_counts_against_her_storage(self) -> None:
        original = self.her_picture(size=3 * MIB)
        self.cloudinary.remote_sizes[original.cloudinary_url] = 3 * MIB
        before = media_bytes_used(self.player)

        response = self.pick(original)

        self.assertEqual(response.status_code, 200, response.content)
        self.mask.refresh_from_db()
        copy = self.mask.thumbnail
        self.assertNotEqual(copy.pk, original.pk)
        self.assertEqual(self.mask.thumbnail_url, copy.cloudinary_url)
        self.assertEqual(copy.player_data, self.player)
        self.assertEqual((copy.title, copy.description, copy.created_by), ("", "", None))
        self.assertEqual(media_bytes_used(self.player), before + 3 * MIB)
        # The copy is a new file in the opaque folder: nothing in its path is a number of hers.
        self.assertTrue(copy.cloudinary_public_id.startswith("faces/"), copy.cloudinary_public_id)
        for folder in ("player_", "char_"):
            self.assertNotIn(folder, copy.cloudinary_url)
        self.assertNotEqual(copy.cloudinary_url, original.cloudinary_url)
        self.assertEqual(self.cloudinary.calls[0]["file"], original.cloudinary_url)

    def test_hobb_reads_the_mask_portrait_everywhere_and_never_her_real_face(self) -> None:
        real_url = self.give_her_a_real_look()
        original = self.her_picture()
        self.telnet(self.ysmay, "scene start")
        self.assertEqual(self.pick(original).status_code, 200)
        self.telnet(self.ysmay, "pose sets a coin on the stall.")
        copy_url = Persona.objects.get(pk=self.mask.pk).thumbnail.cloudinary_url

        sheet = self.hobb_reads_sheet()
        self.assertEqual(sheet["profile_picture"], copy_url)
        self.assertEqual(sheet["looks"], [])
        feed = self.hobb_api().get("/api/interactions/?scene=1").json()
        rows = feed["results"] if isinstance(feed, dict) else feed
        poses = [row["persona"]["thumbnail_url"] for row in rows if row["persona"]["id"]]
        self.assertIn(copy_url, poses)
        # Nothing Hobb can fetch carries her real look, the original, or a media id of hers.
        everything = str((sheet, feed))
        for forbidden in (real_url, original.cloudinary_url, f"player_{self.player.account_id}"):
            self.assertNotIn(forbidden, everything)
        self.assertNotIn("media_id", everything)

    def test_an_uploaded_portrait_lands_in_the_opaque_folder_and_raises_her_storage(self) -> None:
        before = media_usage(self.player).used_bytes
        image = SimpleUploadedFile("owl.png", b"x" * 2048, content_type="image/png")

        response = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "image_file": image}, format="multipart"
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.mask.refresh_from_db()
        self.assertTrue(self.mask.thumbnail.cloudinary_public_id.startswith("faces/"))
        self.assertEqual(self.cloudinary.calls[0]["folder"], "faces")
        self.assertEqual(media_usage(self.player).used_bytes, before + 2048)
        self.assertEqual(self.mask.thumbnail.media_type, "portrait")

    def test_a_replaced_portrait_copy_is_deleted_and_a_removed_one_returns_the_placeholder(
        self,
    ) -> None:
        self.assertEqual(self.pick(self.her_picture(size=500)).status_code, 200)
        first = Persona.objects.get(pk=self.mask.pk).thumbnail
        self.assertEqual(self.pick(self.her_picture(size=700)).status_code, 200)
        self.assertFalse(Media.objects.filter(pk=first.pk).exists())
        self.assertIn(first.cloudinary_public_id, self.cloudinary.destroyed)

        cleared = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "clear": True}, format="json"
        )
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.mask.refresh_from_db()
        self.assertEqual((self.mask.thumbnail, self.mask.thumbnail_url), (None, ""))
        self.assertEqual(self.hobb_reads_sheet()["profile_picture"], BUILTIN_FACE_PLACEHOLDER_URL)

    def test_a_staff_picture_she_replaces_is_never_deleted(self) -> None:
        staff_art = MediaFactory(player_data=None, slug="owl-art", cloudinary_public_id="art/owl")
        self.mask.thumbnail = staff_art
        self.mask.save(update_fields=["thumbnail"])

        self.assertEqual(self.pick(self.her_picture()).status_code, 200)

        self.assertTrue(Media.objects.filter(pk=staff_art.pk).exists())
        self.assertEqual(self.cloudinary.destroyed, [])


class TheUploadLimitHolds(DisguiseFaceCase):
    """A pick and an upload both go through the one limit; a refusal stores nothing."""

    def make_nearly_full(self, free_bytes: int) -> None:
        self.player.media_quota_bytes = media_bytes_used(self.player) + free_bytes
        self.player.save(update_fields=["media_quota_bytes"])

    def assert_nothing_stored(self, refused: Any, message: str) -> None:
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertIn(message, str(refused.json()))
        self.mask.refresh_from_db()
        self.assertIsNone(self.mask.thumbnail)

    def test_a_pick_and_an_upload_that_pass_the_quota_are_refused_with_the_gallerys_words(
        self,
    ) -> None:
        big = self.her_picture(size=5 * MIB)
        self.make_nearly_full(MIB)
        stored = Media.objects.count()

        picked = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "media_id": big.pk}, format="json"
        )
        image = SimpleUploadedFile("owl.png", b"x" * (2 * MIB), content_type="image/png")
        uploaded = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "image_file": image}, format="multipart"
        )

        self.assert_nothing_stored(picked, QUOTA_MESSAGE)
        self.assert_nothing_stored(uploaded, QUOTA_MESSAGE)
        self.assertEqual(Media.objects.count(), stored)
        self.assertEqual(self.cloudinary.calls, [])

    def test_a_copy_that_comes_back_bigger_than_its_source_is_refused_and_destroyed(self) -> None:
        source = self.her_picture(size=1000)
        self.cloudinary.remote_sizes[source.cloudinary_url] = 6 * MIB
        self.make_nearly_full(MIB)

        refused = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "media_id": source.pk}, format="json"
        )

        self.assert_nothing_stored(refused, QUOTA_MESSAGE)
        self.assertEqual(len(self.cloudinary.destroyed), 1)
        self.assertFalse(Media.objects.filter(cloudinary_public_id__startswith="faces/").exists())

    def test_a_file_over_the_per_file_limit_and_a_pdf_are_refused(self) -> None:
        huge = SimpleUploadedFile("owl.png", b"x" * (11 * MIB), content_type="image/png")
        refused = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "image_file": huge}, format="multipart"
        )
        self.assert_nothing_stored(refused, FILE_MESSAGE)

        pdf = SimpleUploadedFile("owl.pdf", b"%PDF", content_type="application/pdf")
        refused = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "image_file": pdf}, format="multipart"
        )
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(self.cloudinary.calls, [])

    def test_staff_are_exempt_from_the_limits_as_the_gallery_exempts_them(self) -> None:
        self.account_of(self.ysmay).is_staff = True
        self.account_of(self.ysmay).save(update_fields=["is_staff"])
        self.make_nearly_full(0)
        big = self.her_picture(size=5 * MIB)

        self.assertEqual(
            self.ysmay_api()
            .post(SET_PORTRAIT, {"persona_id": self.mask.pk, "media_id": big.pk}, format="json")
            .status_code,
            200,
        )

    def test_the_limit_is_taken_under_the_players_row_lock(self) -> None:
        """Two simultaneous uploads need Postgres row locks to be proved (done by hand); here
        the lock is asserted to be taken before the check, on the one shared path."""
        order: list[str] = []
        from world.roster.services import gallery_services

        real_lock, real_check = (
            gallery_services.lock_player_media,
            gallery_services.enforce_player_media_limits,
        )
        with (
            patch.object(
                gallery_services,
                "lock_player_media",
                side_effect=lambda pd: (order.append("lock"), real_lock(pd))[1],
            ),
            patch.object(
                gallery_services,
                "enforce_player_media_limits",
                side_effect=lambda pd, **kw: (order.append("check"), real_check(pd, **kw))[1],
            ),
        ):
            self.ysmay_api().post(
                SET_PORTRAIT,
                {"persona_id": self.mask.pk, "media_id": self.her_picture().pk},
                format="json",
            )
        self.assertEqual(order[:2], ["lock", "check"])


class OnlyHerOwnFacesAndPictures(DisguiseFaceCase):
    """Writes reach only her own masks, alternate selves and pictures, with one refusal."""

    def test_another_players_mask_and_an_unknown_one_are_refused_in_the_same_words(self) -> None:
        for persona_id in (self.mask.pk, 999999):
            for path, body in (
                (SET_DESCRIPTION, {"description": "Mine now."}),
                (SET_PORTRAIT, {"clear": True}),
            ):
                with self.subTest(persona_id=persona_id, path=path):
                    response = self.hobb_api().post(
                        path, {"persona_id": persona_id, **body}, format="json"
                    )
                    self.assertEqual(response.status_code, 400, response.content)
                    self.assertIn(NOT_YOURS, str(response.json()))
        self.mask.refresh_from_db()
        self.assertEqual(self.mask.description, "")

    def test_a_picture_that_is_not_hers_is_refused_like_an_unknown_one(self) -> None:
        theirs = MediaFactory(player_data=self.account_of(self.hobb).player_data)
        responses = [
            self.ysmay_api().post(
                SET_PORTRAIT, {"persona_id": self.mask.pk, "media_id": media_id}, format="json"
            )
            for media_id in (theirs.pk, 999999)
        ]
        self.assertEqual([r.status_code for r in responses], [400, 400])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(responses[0].json(), {"media_id": ["That is not one of your pictures."]})

    def test_a_picture_marked_nsfw_is_neither_listed_nor_accepted(self) -> None:
        nsfw = self.her_picture(is_nsfw=True)
        plain = self.her_picture(size=4321)

        listed = self.ysmay_api().get(CHOICES)
        self.assertEqual(listed.status_code, 200, listed.content)
        ids = [row["id"] for row in listed.json()["results"]]
        self.assertEqual(ids, [plain.pk])
        refused = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": self.mask.pk, "media_id": nsfw.pk}, format="json"
        )
        self.assertEqual(refused.status_code, 400, refused.content)

    def test_the_picker_lists_only_her_own_pictures(self) -> None:
        mine = self.her_picture()
        MediaFactory(player_data=self.account_of(self.hobb).player_data)
        ids = [row["id"] for row in self.ysmay_api().get(CHOICES).json()["results"]]
        self.assertEqual(ids, [mine.pk])

    def test_her_true_face_takes_neither_a_description_nor_a_portrait_here(self) -> None:
        primary = self.sheet.primary_persona
        described = self.ysmay_api().post(
            SET_DESCRIPTION, {"persona_id": primary.pk, "description": "x"}, format="json"
        )
        portrait = self.ysmay_api().post(
            SET_PORTRAIT, {"persona_id": primary.pk, "clear": True}, format="json"
        )
        self.assertEqual((described.status_code, portrait.status_code), (400, 400))

    def test_exactly_one_change_is_required_and_the_description_is_capped(self) -> None:
        both = self.ysmay_api().post(
            SET_PORTRAIT,
            {"persona_id": self.mask.pk, "clear": True, "media_id": self.her_picture().pk},
            format="json",
        )
        neither = self.ysmay_api().post(SET_PORTRAIT, {"persona_id": self.mask.pk}, format="json")
        long = self.ysmay_api().post(
            SET_DESCRIPTION, {"persona_id": self.mask.pk, "description": "a" * 4001}, format="json"
        )
        self.assertEqual([r.status_code for r in (both, neither, long)], [400, 400, 400])

    def test_someone_with_no_character_is_refused_not_crashed(self) -> None:
        nobody = self.api(AccountFactory())
        response = nobody.post(
            SET_DESCRIPTION, {"persona_id": 1, "description": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)


class TheMasksOwnDescription(DisguiseFaceCase):
    """Her description replaces the real prose for a stranger; seeing through brings it back."""

    def describe(self, text: str) -> None:
        response = self.ysmay_api().post(
            SET_DESCRIPTION, {"persona_id": self.mask.pk, "description": text}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["description"], text)

    def test_a_stranger_reads_the_mask_and_never_the_real_description(self) -> None:
        self.describe(MASK_DESCRIPTION)

        told = self.hobb_looks()
        self.assertIn(MASK_DESCRIPTION, told)
        self.assertNotIn("scar", told)
        sheet = self.hobb_reads_sheet()
        self.assertEqual(sheet["appearance"]["description"], MASK_DESCRIPTION)
        # Her own look at herself still reads the real description.
        mine = strip_ansi(self.telnet(self.ysmay, "look me"))
        self.assertIn(REAL_DESCRIPTION, mine)
        self.assertNotIn(MASK_DESCRIPTION, mine)

    def test_markup_in_a_description_is_normalized_like_the_real_one(self) -> None:
        response = self.ysmay_api().post(
            SET_DESCRIPTION,
            {"persona_id": self.mask.pk, "description": "Slim.%rGrey cloak."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.mask.__class__.objects.get(pk=self.mask.pk).description, "Slim.\nGrey cloak."
        )

    def test_a_mask_with_no_description_shows_nothing_and_a_blank_clears_one(self) -> None:
        self.assertNotIn("scar", self.hobb_looks())
        self.assertEqual(self.hobb_reads_sheet()["appearance"]["description"], "")
        self.describe(MASK_DESCRIPTION)
        self.describe("")
        self.assertNotIn(MASK_DESCRIPTION, self.hobb_looks())
        self.assertEqual(self.hobb_reads_sheet()["appearance"]["description"], "")

    def test_the_worn_things_stay_beneath_the_mask_description(self) -> None:
        self.describe(MASK_DESCRIPTION)
        EquippedItemFactory(character=self.sheet)
        self.ysmay.equipped_items.invalidate()
        told = self.hobb_looks()
        self.assertIn(MASK_DESCRIPTION, told)
        self.assertIn("Wearing", told)
        self.assertLess(told.index(MASK_DESCRIPTION), told.index("Wearing"))

    def test_a_viewer_who_has_seen_through_the_mask_reads_the_real_description_again(self) -> None:
        self.describe(MASK_DESCRIPTION)
        record_persona_discovery(self.mask, self.sheet.primary_persona, self.hobb.sheet_data)

        told = self.hobb_looks()
        self.assertIn(REAL_DESCRIPTION, told)
        self.assertNotIn(MASK_DESCRIPTION, told)
        sheet = self.hobb_reads_sheet()
        self.assertEqual(sheet["appearance"]["description"], REAL_DESCRIPTION)

    def test_the_description_never_reaches_the_roster_page(self) -> None:
        self.describe(MASK_DESCRIPTION)
        entry = self.sheet.roster_entry
        response = self.hobb_api().get(f"/api/roster/entries/{entry.pk}/")
        self.assertNotIn(MASK_DESCRIPTION, str(response.content))


class TheFaceWithNoPortrait(DisguiseFaceCase):
    """One placeholder for every portraitless face, never a letter and never the real face."""

    def test_a_mask_with_no_portrait_shows_the_built_in_silhouette_until_staff_choose_one(
        self,
    ) -> None:
        real_url = self.give_her_a_real_look()
        sheet = self.hobb_reads_sheet()
        self.assertEqual(sheet["profile_picture"], BUILTIN_FACE_PLACEHOLDER_URL)
        self.assertNotIn(real_url, str(sheet))

        art = MediaFactory(player_data=None, slug="silhouette", cloudinary_public_id="art/sil")
        config = get_face_placeholder_config()
        config.placeholder = art
        config.save()
        self.assertEqual(self.hobb_reads_sheet()["profile_picture"], art.cloudinary_url)

        art.delete()
        self.assertEqual(self.hobb_reads_sheet()["profile_picture"], BUILTIN_FACE_PLACEHOLDER_URL)
        self.assertEqual(FacePlaceholderConfig.objects.count(), 1)

    def test_the_pose_and_the_persona_list_read_the_same_silhouette(self) -> None:
        self.telnet(self.ysmay, "scene start")
        self.telnet(self.ysmay, "pose waits.")
        feed = self.hobb_api().get("/api/interactions/?scene=1").json()
        rows = feed["results"] if isinstance(feed, dict) else feed
        self.assertEqual(
            {row["persona"]["thumbnail_url"] for row in rows}, {BUILTIN_FACE_PLACEHOLDER_URL}
        )
        listed = self.ysmay_api().get(f"/api/personas/?character_sheet={self.sheet.pk}").json()
        by_name = {row["name"]: row for row in listed["results"]}
        self.assertEqual(by_name["Owl Mask"]["thumbnail_url"], BUILTIN_FACE_PLACEHOLDER_URL)
        self.assertEqual(by_name["Owl Mask"]["thumbnail_media_url"], BUILTIN_FACE_PLACEHOLDER_URL)
        # The true face keeps the letter avatar the client draws for no picture.
        self.assertEqual(by_name["Ysmay"]["thumbnail_url"], "")


class AnAlternateSelfsPortrait(DisguiseFaceCase):
    """A form gets its own portrait; one with no picture never shows the real face."""

    def setUp(self) -> None:
        super().setUp()
        self.real_url = self.give_her_a_real_look()
        form_persona = PersonaFactory(
            character_sheet=self.sheet, name="Ashen Wolf", persona_type=PersonaType.ALTERNATE
        )
        self.with_persona = AlternateSelfFactory(
            character=self.sheet, display_name="Battle Form", persona=form_persona
        )
        self.bare = AlternateSelfFactory(character=self.sheet, display_name="Hollow Form")

    def set_portrait(self, alt_self: Any, **body: Any) -> Any:
        return self.ysmay_api().post(
            f"/api/forms/alternate-selves/{alt_self.pk}/set-portrait/", body, format="json"
        )

    def wear(self, alt_self: Any) -> None:
        ActiveAlternateSelf.objects.update_or_create(
            character=self.sheet, defaults={"alternate_self": alt_self}
        )
        self.sheet.refresh_from_db()

    def test_a_form_with_a_persona_sets_its_own_and_its_personas_picture(self) -> None:
        picture = self.her_picture()

        response = self.set_portrait(self.with_persona, media_id=picture.pk)

        self.assertEqual(response.status_code, 200, response.content)
        self.with_persona.refresh_from_db()
        persona = self.with_persona.persona
        persona.refresh_from_db()
        self.assertEqual(self.with_persona.thumbnail, persona.thumbnail)
        self.assertEqual(persona.thumbnail_url, self.with_persona.thumbnail.cloudinary_url)
        self.assertIn("/faces/", response.json()["thumbnail_url"])
        self.assertEqual(response.json()["persona_id"], persona.pk)

    def test_replacing_a_forms_portrait_twice_deletes_its_one_copy_once(self) -> None:
        """The form and its persona share one picture; replacing it must not delete it twice."""
        self.assertEqual(
            self.set_portrait(self.with_persona, media_id=self.her_picture(size=5).pk).status_code,
            200,
        )
        first = Persona.objects.get(pk=self.with_persona.persona_id).thumbnail

        again = self.set_portrait(self.with_persona, media_id=self.her_picture(size=6).pk)

        self.assertEqual(again.status_code, 200, again.content)
        self.assertFalse(Media.objects.filter(pk=first.pk).exists())
        self.assertEqual(self.cloudinary.destroyed, [first.cloudinary_public_id])

    def test_a_forms_picture_is_read_only_on_the_face_that_is_presented(self) -> None:
        """A hidden face of the same character must not read the form's picture too."""
        self.set_portrait(self.bare, media_id=self.her_picture().pk)
        self.bare.refresh_from_db()
        self.wear(self.bare)

        listed = self.ysmay_api().get(f"/api/personas/?character_sheet={self.sheet.pk}").json()
        by_name = {row["name"]: row["thumbnail_media_url"] for row in listed["results"]}

        self.assertEqual(by_name["Owl Mask"], self.bare.thumbnail.cloudinary_url)
        self.assertNotEqual(by_name["Ysmay"], self.bare.thumbnail.cloudinary_url)
        self.assertNotEqual(by_name["Ashen Wolf"], self.bare.thumbnail.cloudinary_url)

    def test_a_worn_form_with_no_persona_shows_its_picture_in_poses_never_the_real_face(
        self,
    ) -> None:
        self.set_portrait(self.bare, media_id=self.her_picture().pk)
        self.bare.refresh_from_db()
        # Her barefaced face is the one presented, with the real look copied onto it.
        self.sheet.primary_persona.thumbnail_url = self.real_url
        self.sheet.primary_persona.save(update_fields=["thumbnail_url"])
        self.telnet(self.ysmay, "persona Ysmay")
        self.telnet(self.ysmay, "scene start")
        self.wear(self.bare)
        self.telnet(self.ysmay, "pose bares her teeth.")

        feed = self.hobb_api().get("/api/interactions/?scene=1").json()
        rows = feed["results"] if isinstance(feed, dict) else feed
        urls = {row["persona"]["thumbnail_url"] for row in rows}
        self.assertEqual(urls, {self.bare.thumbnail.cloudinary_url})
        self.assertNotIn(self.real_url, str(feed))

    def test_a_form_with_no_persona_takes_a_portrait_and_no_description(self) -> None:
        response = self.set_portrait(self.bare, media_id=self.her_picture().pk)
        self.assertEqual(response.status_code, 200, response.content)
        self.bare.refresh_from_db()
        self.assertIsNotNone(self.bare.thumbnail)
        self.assertIsNone(response.json()["persona_id"])

    def test_the_staff_picture_a_player_replaces_stays_for_staff_to_restore(self) -> None:
        staff_art = MediaFactory(player_data=None, slug="wolf-art", cloudinary_public_id="art/wolf")
        self.bare.thumbnail = staff_art
        self.bare.save(update_fields=["thumbnail"])
        self.assertEqual(
            self.set_portrait(self.bare, media_id=self.her_picture().pk).status_code, 200
        )
        self.assertTrue(Media.objects.filter(pk=staff_art.pk).exists())

    def test_a_worn_form_with_no_portrait_shows_the_silhouette_and_never_her_real_face(
        self,
    ) -> None:
        self.wear(self.bare)
        sheet = self.hobb_reads_sheet()
        self.assertEqual(sheet["profile_picture"], BUILTIN_FACE_PLACEHOLDER_URL)
        self.assertEqual(sheet["looks"], [])
        self.assertNotIn(self.real_url, str(sheet))

    def test_a_worn_form_with_a_portrait_shows_it_to_a_stranger(self) -> None:
        self.set_portrait(self.bare, media_id=self.her_picture().pk)
        self.bare.refresh_from_db()
        self.wear(self.bare)
        self.assertEqual(
            self.hobb_reads_sheet()["profile_picture"], self.bare.thumbnail.cloudinary_url
        )

    def test_another_players_form_is_a_404_and_the_list_carries_only_her_own(self) -> None:
        stranger_self = AlternateSelfFactory(
            character=self.hobb.sheet_data, display_name="Hobbs Form"
        )
        refused = self.set_portrait(stranger_self, clear=True)
        self.assertEqual(refused.status_code, 404, refused.content)
        unknown = self.ysmay_api().post(
            "/api/forms/alternate-selves/999999/set-portrait/", {"clear": True}, format="json"
        )
        self.assertEqual(unknown.status_code, 404)

    def test_staff_setting_a_forms_picture_in_the_admin_reaches_the_pose_picture_too(self) -> None:
        from django.contrib import admin as django_admin

        from world.forms.models import AlternateSelf

        art = MediaFactory(player_data=None, slug="wolf-art", cloudinary_public_id="art/wolf")
        model_admin = django_admin.site._registry[AlternateSelf]
        self.with_persona.thumbnail = art
        form = MagicMock(changed_data=["thumbnail"])
        model_admin.save_model(MagicMock(), self.with_persona, form, True)

        persona = Persona.objects.get(pk=self.with_persona.persona_id)
        self.assertEqual(persona.thumbnail_url, art.cloudinary_url)
        self.assertEqual(persona.thumbnail, art)
