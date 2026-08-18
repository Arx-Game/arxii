# ADR-0220: Canvas deletion gates on `exported_at`, not fixture-key presence

**Status:** Accepted (2026-08-18, #3269)

`staff_remove_room` used to refuse any room with a fixture key + AUTHORED origin,
treating "keyed" as "exported" — but `staff_dig_room` assigns a fixture key at
creation, so every builder-dug room was instantly undeletable and a typo on room
12 of 400 became permanent content (the passing delete test used a keyless
factory room, hiding the regression). The two concepts are now separate:
`RoomProfile.exported_at` is stamped by `grid_export` when a room actually ships
in a bundle, and deletion (plus the report-never-delete boundary) gates on THAT.
The same principle drives area recoverability: an area slug stays changeable
until a room beneath it carries a fixture key (the key embeds the slug, ADR-0140
permanence starts there, not at slug assignment), and `staff_remove_area`
deletes empty areas outright. Alternative rejected: keeping the fixture-key gate
and making dig stop assigning keys — the key-at-dig behavior is what makes
`suggest_fixture_key` authoring cheap, and it isn't the thing that needs
protecting; the exported bundle is.
