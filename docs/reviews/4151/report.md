# Review evidence

- Reviewed revision: `cd4c895a926dcccee1daa55095352ec96f1bff8a`
- Reviewer: demo-fidelity-reviewer agent (three passes: the first against the rulings, finding D1 tools keyed on width, D3 a missing new-look capture and D4 lightbox type and close legibility; all fixed and re-captured; the second a full comparison against the demo's markup and CSS, finding the cropper's missing keys line, added and re-captured), with the implementing agent (Claude Code) writing this report from its checklist
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on private port 4183
- Environment: Linux devcontainer, Playwright Chromium headless without touch emulation; every `/api/**` response is a fixture and every Cloudinary image is a painted SVG (a `c_crop` URL answers the same picture cropped through its viewBox), no Django behind the preview build
- Viewports/themes: 1280x900 and 390x1100; the sheet's ember plate on Arx paper (the page has one theme)
- Approved design: the demo on issue #4151, https://claude.ai/artifact/HCXPNZQ715Xgdzvdg8k2Fe (version 4, 2026-10-05), with the spec's Decisions 1-18 and Screens 1-12; where the design conversation ruled after the demo (one Delete with its confirm, character art and Hide, the storage line, no Your files page), the ruling wins. Pictures and every title and caption are placeholder copy, so wording and imagery are never findings; structure, order, controls, treatment and who sees what are.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The owner's plate: the worn look, the strip with numbered moods and the Add tile](docs/reviews/4151/01-owner-plate-1280.png) ![The owner's Gallery: looks grid left, the tall frame and thumbnails right, storage line](docs/reviews/4151/02-owner-gallery-1280.png) ![Hover on a look: title, caption and tools](docs/reviews/4151/03-owner-hover-look-1280.png) ![Hover on the tall frame](docs/reviews/4151/04-owner-hover-picture-1280.png) ![The cropper on an existing look](docs/reviews/4151/05-cropper-1280.png) ![Picture details](docs/reviews/4151/06-details-1280.png) ![The one Delete](docs/reviews/4151/07-delete-confirm-1280.png) ![Hide for character art](docs/reviews/4151/08-hide-confirm-1280.png) ![Add a look](docs/reviews/4151/09-add-a-look-1280.png) ![The cropper on a new look](docs/reviews/4151/09b-new-look-cropper-1280.png) ![A stranger: the NSFW picture veiled](docs/reviews/4151/10-stranger-veiled-1280.png) ![A friend: the NSFW picture plain](docs/reviews/4151/11-friend-plain-1280.png) ![The lightbox](docs/reviews/4151/12-lightbox-1280.png) ![The owner's Gallery at phone width](docs/reviews/4151/13-owner-gallery-390.png)
- Comparison notes: Screen 1: the plate wears the cropped look; the strip labels each look by mood and numbers a repeat ("Furious 2"), with an owner-only Add tile and no instruction line. Screen 3: the Gallery header (eyebrow, count, the owner's storage line), the owner's drop zone with the demo's own copy, looks as a 4:5 grid on the left with the worn one gilt-edged, every other picture in a 3:5 frame with an inset hairline, arrows and 44px thumbnails on the right. Screen 5: words over the foot of a picture on hover only and only when written; tools on hover only, to the owner. Screens 6-7: the details card on light paper (Title, Caption, Mood it shows, NSFW with its rule) and the cropper on the plate's night ground (4:5 frame, dimmed outside, thirds grid, round corner and bar edge handles, Sheet / Look / Chip previews, mood select, the keys line, "Show it on the sheet now" for a new look). Screens 8b-8c: the Delete confirm names the space it frees; character art offers Hide, never Delete. Screen 8: Add a look offers non-NSFW pictures and an upload tile. Screens 10-11: a stranger gets no tools, no drop zone, no Add tile and no storage figure, and the NSFW picture blurred with NSFW / Click to reveal (thumbnail blurred too); a friend sees it plain. The lightbox opens a picture full size with arrows and its words. At 390px the grid is two columns with the viewer below and tools still hover-only. Differences, each ruled or out of scope and listed in the Requirement ledger: the looks strip keeps the #3898 strip's overlaid labels and accent outline rather than the demo's label-below (this change does not restyle the strip); the lightbox close sits at the content's corner rather than the viewport's; the details and Add a look cards carry the dialog primitive's close; the confirms and the storage line are rulings made after the demo.
- Tested interactions: open `/characters/1` as the owner, a stranger and a friend; open the Gallery tab; hover a look and the tall frame; open the cropper from a look's tool and from Add a look on a picked picture; open details; open the Delete confirm and the Hide confirm (character art, reached by its thumbnail); open Add a look from the plate; click through the NSFW veil as a stranger; open the lightbox; the Gallery at 390px. No page errors were raised. The vitest suites assert the requests the controls send (Hide POST, Delete DELETE).
- Fixture/live boundary: the page, router, plate, strip, Gallery panel, dialogs, cropper and bundle are real. Every `/api/**` response is a fixture shaped like the serializers: a nine-picture gallery (five looks, one NSFW, one piece of character art), the owner's storage, six moods, and a `CharacterSheetPayload` in three readings (owner, stranger, friend via `viewer_is_friend`). The server side (looks, the worn-look rules, character art and hides, the one Delete, reorder, the anonymous roster gate) is proved by `world.roster.tests.test_gallery_services`, `test_tenure_media_api`, `test_gallery_models` and `world.character_sheets.tests.test_viewset`, not by this harness.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Plate wears the worn look at its 4:5 crop | cropped portrait | MATCH | [01](docs/reviews/4151/01-owner-plate-1280.png) |
| Looks strip labels by mood, numbers repeats, owner Add tile | Furious, Furious 2, Add | MATCH | [01](docs/reviews/4151/01-owner-plate-1280.png) |
| No instruction line on the plate | none | MATCH | [01](docs/reviews/4151/01-owner-plate-1280.png) |
| Gallery tab after Magic, before the Yours only break | as ordered | MATCH | [02](docs/reviews/4151/02-owner-gallery-1280.png) |
| Header eyebrow, count, owner storage line | 9 pictures, 10.9 MB of 100.0 MB | MATCH | [02](docs/reviews/4151/02-owner-gallery-1280.png) |
| Owner drop zone with the demo's copy | present | MATCH | [02](docs/reviews/4151/02-owner-gallery-1280.png) |
| Looks grid left, worn look gilt-edged | 4 columns at 1280 | MATCH | [02](docs/reviews/4151/02-owner-gallery-1280.png) |
| Tall 3:5 frame with inset hairline, arrows, thumbnails | right column | MATCH | [02](docs/reviews/4151/02-owner-gallery-1280.png) |
| Words and tools on hover only, words only when written | as drawn | MATCH | [03](docs/reviews/4151/03-owner-hover-look-1280.png), [04](docs/reviews/4151/04-owner-hover-picture-1280.png) |
| Cropper on the plate ground, 4:5 frame, eight handles, thirds grid | as drawn | MATCH | [05](docs/reviews/4151/05-cropper-1280.png) |
| Cropper previews Sheet, Look, Chip; mood select; keys line | as drawn | MATCH | [05](docs/reviews/4151/05-cropper-1280.png) |
| New-look cropper with Show it on the sheet now and Save profile picture | checked by default | MATCH | [09b](docs/reviews/4151/09b-new-look-cropper-1280.png) |
| Details card: Title, Caption, Mood, NSFW with its rule | light paper | MATCH | [06](docs/reviews/4151/06-details-1280.png) |
| One Delete names the space it frees | This frees 2.4 MB | MATCH | [07](docs/reviews/4151/07-delete-confirm-1280.png) |
| Character art offers Hide, not Delete | stays for whoever plays next | MATCH | [08](docs/reviews/4151/08-hide-confirm-1280.png) |
| Add a look: pictures that can be looks, and an upload tile | NSFW excluded | MATCH | [09](docs/reviews/4151/09-add-a-look-1280.png) |
| Stranger: no tools, drop zone, Add or storage; NSFW veiled | as drawn | MATCH | [10](docs/reviews/4151/10-stranger-veiled-1280.png) |
| Friend: NSFW picture plain | no veil | MATCH | [11](docs/reviews/4151/11-friend-plain-1280.png) |
| Lightbox: full size, arrows, title and caption in the sheet's faces | as drawn | MATCH | [12](docs/reviews/4151/12-lightbox-1280.png) |
| Phone width: two-column grid, viewer below, tools hover-only | stacked | MATCH | [13](docs/reviews/4151/13-owner-gallery-390.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-looks-are-cropped-pictures | PASS | `TenureMedia.crop_*` with the all-or-none CHECK (`test_gallery_models`); `set_look` fit and minimum (`test_gallery_services`); `look_url`; captures 01, 05 | Decisions 2, 3 |
| R02-one-crop-every-surface | PASS | `portrait_url` read by the sheet, account payload and both roster serializers (`test_serializers`, `test_viewset`); avatar object-top | Decision 4 |
| R03-cropper-handles-and-keys | PASS | `cropMath.test.ts` (corner, edge, move, clamp, minimum); captures 05, 09b | Decision 3 |
| R04-gallery-layout-and-hover | PASS | `GalleryPanel.test.tsx`; captures 02-04 | Decision 9 |
| R05-nsfw-veil-for-non-friends | PASS | `viewer_is_friend` (`test_viewset`); `GalleryPanel.test.tsx` stranger and friend; captures 10, 11; NSFW cannot be a look (`test_gallery_services`) | Decision 6 |
| R06-one-delete-and-storage | PASS | `delete_picture` deleted/unlinked and quota (`test_gallery_services`, `test_tenure_media_api`); `MediaViewSet.perform_destroy`; capture 07 | Decision 14 |
| R07-character-art-and-hide | PASS | `test_gallery_services` and `test_tenure_media_api` (staff upload, player cannot delete, hide drops it for visitors, next tenure sees it); capture 08 | Decisions 17, 18 |
| R08-current-tenure-only | PASS | `test_a_new_player_keeps_the_art_and_not_the_last_players_uploads`; `portrait_url` refuses an ended tenure's look | Decision 13 |
| R09-signed-out-sees-no-art | PASS | `RosterPortraitTests`; media reads need an account (`test_permissions`); the sheet already needs one | Decision 11 |
| R10-galleries-and-media-page-retired | PASS | migrations 0203/0204 (prod dump 0 rows); `/profile/media` removed | Decisions 7, 8, 16 |
| R11-looks-strip-label-placement | OUT_OF_SCOPE | the strip keeps #3898's overlaid labels and accent outline; this change adds numbering and the Add tile only | #3898 strip as shipped; raised to ApostateCD on the PR |
| R12-reorder-and-drag-across | PASS | `reorder_pictures` exact-set rule (`test_tenure_media_api`); the drag wiring in `GalleryPanel.tsx`; no capture (a drag is not a still) | Decision 9 |

## Unresolved findings

- None
