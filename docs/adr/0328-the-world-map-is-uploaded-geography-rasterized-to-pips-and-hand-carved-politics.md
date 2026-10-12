# 0328 — The world map is uploaded geography rasterized to pips, and hand-carved politics

**Status:** accepted (2026-10-11 and 2026-10-12, ApostateCD on #4242)

The Almanach plants domains on a realm's ladder (ADR-0309), but a domain had no shape
on the Atlas, which drew every area as one cell. **The ruling:** the overland map is
stored as 10-mile **pips**, one row per pip, on one world grid; the 100-mile cell is
only the lens the Atlas views them through. A **barony is one pip**, a county roughly a
hundred, a realm the union of its duchies, and boundaries are never cell-shaped.
**Geography comes from an uploaded Fantasy Map Generator file**, rasterized on our side
from the file's grid arrays (height, temperature, precipitation, features) and its river
paths; the Atlas never reads the file format, the pips are the contract. **Politics is
carved by hand**: the generator's states and provinces are ignored, and a domain's
footprint is a set of pips (`AreaFootprintPip`, one row per pip per area at every tier,
a pip's holder being the lowest area containing it, derived on read). **Hand edits
survive and uploads are append-only**: every terrain pip records its source, a
re-rasterize rewrites only the generator's pips, and every uploaded file is kept whole
in the database (`RegionMapUpload.file_bytes`, gzip), because production has no
persistent media disk, the image host caps raw files below the file's size, and
ADR-0237 makes the database the master copy of authored content. **Many region maps
tile one world grid**, each with an anchor cell and a width in cells; seams are stitched
by staff paint. **Open ground is real**: unheld pips are rows, so claiming virgin land
is a later column, not a re-rasterize. **Rejected:** (a) hosting a pinned fork of the
generator with an "Arx" storage provider: one provider file, but the app pushes most
days and the rasterize step and the stored map row are identical in both shapes;
(b) run-length terrain per cell: a rasterized coastline degenerates the ranges exactly
where the map matters and every hand edit splits one; (c) one world file: it forces the
whole world to be drawn at once; (d) a footprint as width and height on `Area`: counties
are not rectangles; (e) a footprint as a many-to-many onto the terrain rows: a
re-rasterize deletes the rows it would point at. Related: ADR-0309 (rungs are real
Atlas levels), ADR-0325 (the ladder is sizes only), ADR-0120 (connectivity is exits; a
pip is ground, never a route), ADR-0237 (durability), ADR-0007 (no JSON columns; the
file is binary, nothing is queried inside it).
